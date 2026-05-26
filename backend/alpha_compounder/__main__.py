"""
__main__.py — CLI entry point for the Alpha Compounder pipeline.

Usage:
  python -m alpha_compounder agent_a [options]
  python -m alpha_compounder attribution [options]
  python -m alpha_compounder synthesis [options]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

# Set offline mode globally for FMP caching/calls
os.environ["FMP_OFFLINE"] = "1"

# Add backend dir to path
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("alpha_compounder")


def _get_fmp_func():
    """Import and return the fmp() function from screener_v6."""
    try:
        from screener_v6 import fmp
        return fmp
    except ImportError:
        log.error("screener_v6.py not found — cannot access FMP API")
        sys.exit(1)


def cmd_agent_a(args):
    """Run Agent A: discover price runs."""
    from alpha_compounder.agent_a.discovery import run_discovery
    from alpha_compounder.config import GRID_CELLS

    window = args.window.split(":")
    window_start, window_end = window[0], window[1]

    fmp_func = _get_fmp_func()

    result = run_discovery(
        fmp_func=fmp_func,
        window_start=window_start,
        window_end=window_end,
        grid=GRID_CELLS,
        workers=args.workers,
        output_path=args.output or "runs_ledger.parquet",
        allow_sparse_ledger=getattr(args, "allow_sparse_ledger", False),
    )

    if result is not None:
        log.info(f"Agent A complete: {len(result)} runs in ledger")
    else:
        log.error("Agent A produced no runs")
        sys.exit(1)


def cmd_attribution(args):
    """Run B↔C adversarial attribution loop."""
    import pandas as pd
    from alpha_compounder.agents.base_agent import AttributionAgent
    from alpha_compounder.config import (
        LLM_MODEL_ATTRIBUTION,
        LLM_TEMPERATURE,
        PRIOR_B,
        PRIOR_C,
        BudgetConfig,
    )
    from alpha_compounder.factor_service import FactorService
    from alpha_compounder.orchestrator.loop import run_attribution_loop
    from alpha_compounder.schemas import RunRecord, Attribution

    fmp_func = _get_fmp_func()

    # Load ledger
    ledger_path = args.ledger or "runs_ledger.parquet"
    log.info(f"Loading ledger: {ledger_path}")
    df = pd.read_parquet(ledger_path)
    log.info(f"Ledger: {len(df)} runs")

    # Initialize components
    model = args.model or LLM_MODEL_ATTRIBUTION
    factor_service = FactorService(fmp_func)
    agent_b = AttributionAgent("B", PRIOR_B, model=model, temperature=LLM_TEMPERATURE)
    agent_c = AttributionAgent("C", PRIOR_C, model=model, temperature=LLM_TEMPERATURE)

    budget = BudgetConfig(
        max_tokens_per_run=args.max_tokens_per_run,
        max_seconds_per_run=args.max_seconds_per_run,
        max_rounds_per_run=args.max_rounds,
    )

    # Process runs
    results = []
    output_dir = args.output_dir or "attributions"
    os.makedirs(output_dir, exist_ok=True)

    # Build mapping from run_id to RunRecord from ledger
    run_records_by_id = {}
    for idx, row in df.iterrows():
        run = RunRecord(**row.to_dict())
        run_records_by_id[run.run_id] = run

    # 1. Index existing attributions by (symbol, start_date, end_date)
    existing_by_key = {}
    for run_id in os.listdir(output_dir):
        run_dir = os.path.join(output_dir, run_id)
        if os.path.isdir(run_dir):
            attr_file = os.path.join(run_dir, "attribution.json")
            if os.path.exists(attr_file):
                try:
                    with open(attr_file, encoding="utf-8") as f:
                        data = json.load(f)
                    attr = Attribution(**data)
                    if attr.run_id in run_records_by_id:
                        run = run_records_by_id[attr.run_id]
                        key = (run.symbol, run.t_start, run.t_end)
                        existing_by_key[key] = attr
                except Exception as e:
                    log.warning(f"Failed to parse cached attribution {run_id}: {e}")

    log.info(f"Indexed {len(existing_by_key)} existing attributions from cache.")

    # List of runs to process
    runs_to_process = []
    limit = getattr(args, "limit", None)
    new_runs_processed = 0

    for idx, row in df.iterrows():
        run = RunRecord(**row.to_dict())
        key = (run.symbol, run.t_start, run.t_end)

        # Check if exists in existing_by_key
        if key in existing_by_key:
            log.info(f"Skipping Run {idx + 1}/{len(df)}: {run.symbol} (attribution matches cached run)")
            attr = existing_by_key[key]
            # Write it under the new run_id folder for consistency
            new_run_dir = os.path.join(output_dir, run.run_id)
            os.makedirs(new_run_dir, exist_ok=True)
            with open(os.path.join(new_run_dir, "attribution.json"), "w", encoding="utf-8") as f:
                json.dump(attr.model_dump(mode="json"), f, indent=2, default=str)
            results.append(attr)
            continue

        if limit is not None and new_runs_processed >= limit:
            log.info(f"Skipping Run {idx + 1}/{len(df)}: {run.symbol} (new run limit reached: {limit})")
            continue

        runs_to_process.append((idx, run))
        new_runs_processed += 1

    log.info(f"Need to run attribution loop for {len(runs_to_process)} remaining runs.")

    # Helper function for worker thread
    def process_single(idx: int, run: RunRecord) -> Attribution | None:
        log.info(f"Starting Run {idx + 1}/{len(df)}: {run.symbol}...")
        try:
            attribution = run_attribution_loop(
                run=run,
                factor_service=factor_service,
                agent_b=agent_b,
                agent_c=agent_c,
                budget=budget,
            )
            # Write attribution to output directory
            run_dir = os.path.join(output_dir, run.run_id)
            os.makedirs(run_dir, exist_ok=True)
            with open(os.path.join(run_dir, "attribution.json"), "w", encoding="utf-8") as f:
                json.dump(attribution.model_dump(mode="json"), f, indent=2, default=str)

            log.info(f"Finished Run {idx + 1}/{len(df)}: {run.symbol} → {attribution.status.value} "
                     f"({attribution.rounds_used} rounds, "
                     f"F={attribution.fundamental_weight_total:.2f}, "
                     f"FL={attribution.flow_weight_total:.2f})")
            return attribution
        except Exception as e:
            log.error(f"Failed Run {idx + 1}/{len(df)}: {run.symbol}: {e}")
            return None

    parallelism = getattr(args, "parallelism", 1)
    if parallelism > 1 and len(runs_to_process) > 0:
        log.info(f"Running with parallelism of {parallelism} threads...")
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=parallelism) as executor:
            futures = {executor.submit(process_single, idx, run): (idx, run) for idx, run in runs_to_process}
            for fut in as_completed(futures):
                idx, run = futures[fut]
                res = fut.result()
                if res is not None:
                    results.append(res)
    else:
        for idx, run in runs_to_process:
            res = process_single(idx, run)
            if res is not None:
                results.append(res)

    # Summary
    from collections import Counter
    statuses = Counter(r.status.value for r in results)
    log.info(f"\n=== Attribution Summary ===")
    log.info(f"Total: {len(results)}/{len(df)}")
    for status, count in statuses.most_common():
        log.info(f"  {status}: {count}")

    if results:
        conv_rate = sum(1 for r in results if "CONVERGED" in r.status.value) / len(results)
        log.info(f"Convergence rate: {conv_rate:.1%}")


def cmd_synthesis(args):
    """Run Agent D: strategy synthesis."""
    from alpha_compounder.agent_d.synthesis import run_synthesis

    cross_validate = args.cross_validate.split(",") if args.cross_validate else None

    result = run_synthesis(
        ledger_path=args.ledger or "runs_ledger.parquet",
        attributions_dir=args.attributions_dir or "attributions",
        output_dir=args.output_dir or "synthesis",
        cross_validate=cross_validate,
    )

    log.info(f"Synthesis complete: convergence_rate={result['convergence_rate']:.1%}")


def cmd_validation(args):
    """Run Agent E: strategy validation gate."""
    from alpha_compounder.agent_e.validation import run_validation_gate, APPROVAL_THRESHOLD_HOLDOUT_CAGR

    parameters_path = getattr(args, "parameters", None)
    if not parameters_path:
        default_path = os.path.join("synthesis", "approved_parameters.json")
        if os.path.exists(default_path):
            parameters_path = default_path
            log.info(f"Using default synthesis parameters from: {parameters_path}")

    result = run_validation_gate(
        master_features_path=args.master_features or "master_features.parquet",
        target_cagr=args.override_target_cagr if args.override_target_cagr is not None else APPROVAL_THRESHOLD_HOLDOUT_CAGR,
        max_cycles=args.max_cycles,
        parameters_path=parameters_path,
        override_gate_thresholds=getattr(args, "override_gate_thresholds", False),
        override_justification=getattr(args, "override_justification", None),
        allow_sparse_ledger=getattr(args, "allow_sparse_ledger", False),
    )

    log.info(f"Validation complete: Status = {result['status']}, Final CAGR = {result['final_cagr']*100:.2f}%, Cycles = {result['cycles_used']}")


def cmd_agent_e_phase1(args):
    """Run Phase E1 CV Optimization."""
    import pandas as pd
    from alpha_compounder.agent_e.validation import run_phase_e1_optimization

    if not os.path.exists(args.master_features):
        log.error(f"Master features file not found at: {args.master_features}")
        sys.exit(1)

    log.info(f"Loading master features from {args.master_features}...")
    df = pd.read_parquet(args.master_features)
    df['scan_date'] = pd.to_datetime(df['scan_date'])

    if 'regime' not in df.columns:
        from b10_dual_engine import train_hmm_regimes
        regime_df = train_hmm_regimes(df)
        df = pd.merge(df, regime_df, on='scan_date', how='inner')

    initial_params_path = None
    presets = [
        os.path.join(args.synthesis_dir, "approved_parameters.json"),
        os.path.join(args.synthesis_dir, "forward_scorer_parameters.json"),
        os.path.join("synthesis", "approved_parameters.json"),
        "approved_parameters.json"
    ]
    for p in presets:
        if os.path.exists(p):
            initial_params_path = p
            break

    run_phase_e1_optimization(
        df=df,
        synthesis_dir=args.synthesis_dir,
        validation_dir=args.validation_dir,
        max_iterations=args.max_iterations,
        early_stop_stalled_count=args.early_stop_stalled_count,
        parameters_path=initial_params_path,
    )


def cmd_agent_e_phase2(args):
    """Run Phase E2 Holdout evaluation (Agent E)."""
    import pandas as pd
    from alpha_compounder.agent_e.validation import run_phase_e2_holdout, APPROVAL_THRESHOLD_HOLDOUT_CAGR

    if not os.path.exists(args.master_features):
        log.error(f"Master features file not found at: {args.master_features}")
        sys.exit(1)

    if not os.path.exists(args.locked_params):
        log.error(f"Locked parameters file not found at: {args.locked_params}. Run Phase E1 first.")
        sys.exit(1)

    with open(args.locked_params) as f:
        locked_params = json.load(f)

    log.info(f"Loading master features from {args.master_features}...")
    df = pd.read_parquet(args.master_features)
    df['scan_date'] = pd.to_datetime(df['scan_date'])

    if 'regime' not in df.columns:
        from b10_dual_engine import train_hmm_regimes
        regime_df = train_hmm_regimes(df)
        df = pd.merge(df, regime_df, on='scan_date', how='inner')

    run_phase_e2_holdout(
        df=df,
        locked_params=locked_params,
        holdout_dir=args.holdout_dir,
        output_final_dir=args.output_final_dir,
        target_cagr=args.override_target_cagr if args.override_target_cagr is not None else APPROVAL_THRESHOLD_HOLDOUT_CAGR,
        burn_holdout_and_restart=args.burn_holdout_and_restart,
        override_gate_thresholds=args.override_gate_thresholds,
        override_justification=args.override_justification,
        allow_sparse_ledger=args.allow_sparse_ledger,
    )


def cmd_preflight(args):
    """Run pre-run sanity check (preflight)."""
    from alpha_compounder.preflight import preflight_check

    log.info("Running Preflight Checks...")
    issues = preflight_check(args)

    criticals = [i for i in issues if i.level == "CRITICAL"]
    warnings = [i for i in issues if i.level == "WARNING"]

    if warnings:
        log.warning(f"Found {len(warnings)} preflight warning(s):")
        for w in warnings:
            log.warning(f"  - {w.message}")

    if criticals:
        log.error(f"HALTED: Found {len(criticals)} CRITICAL preflight issue(s):")
        for c in criticals:
            log.error(f"  - {c.message}")
        sys.exit(1)

    log.info("Preflight Checks Passed successfully.")


def cmd_postflight(args):
    """Run post-run independent validation (postflight)."""
    from pathlib import Path
    from alpha_compounder.postflight import postflight_check

    log.info(f"Running Postflight Checks on directory: {args.final_dir}")
    final_dir = Path(args.final_dir)

    report = postflight_check(final_dir)

    log.info(f"Postflight Decision: Approved = {report.approved}, Spec Compliant = {report.spec_compliant}")

    if report.findings:
        log.info("Findings:")
        for f in report.findings:
            if f.level == "VIOLATION":
                log.error(f"  [{f.level}] {f.message}")
            else:
                log.warning(f"  [{f.level}] {f.message}")

    if not report.spec_compliant:
        log.error("Postflight failed: Strategy validation is VOID because it is not spec compliant.")
        sys.exit(1)

    log.info("Postflight validation passed. Strategy is SPEC COMPLIANT.")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def main():
    # Load env variables from .env.local manually
    env_path = r"c:\Users\Bruno\Stock-Screener\frontend\.env.local"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip().replace('"', '')

    parser = argparse.ArgumentParser(
        prog="alpha_compounder",
        description="Alpha Compounder Discovery Pipeline",
    )
    sub = parser.add_subparsers(dest="command", help="Pipeline stage")

    # Agent A
    p_a = sub.add_parser("agent_a", help="Run Discovery")
    p_a.add_argument("--window", default="2018-01-01:2025-06-30",
                      help="Time window (start:end)")
    p_a.add_argument("--output", default=None, help="Output path for ledger")
    p_a.add_argument("--workers", type=int, default=8, help="Parallel workers")
    p_a.add_argument("--allow-sparse-ledger", action="store_true", help="Allow sparse ledger for smoke test")

    # Attribution
    p_attr = sub.add_parser("attribution", help="B/C Attribution Loop")
    p_attr.add_argument("--ledger", default=None, help="Path to runs_ledger.parquet")
    p_attr.add_argument("--output-dir", default=None, help="Output directory")
    p_attr.add_argument("--model", default=None, help="LLM model name")
    p_attr.add_argument("--max-rounds", type=int, default=100)
    p_attr.add_argument("--max-tokens-per-run", type=int, default=60000)
    p_attr.add_argument("--max-seconds-per-run", type=int, default=480)
    p_attr.add_argument("--parallelism", type=int, default=1)
    p_attr.add_argument("--limit", type=int, default=None, help="Limit number of new runs to process")

    # Synthesis
    p_d = sub.add_parser("synthesis", help="Strategy Synthesis (Agent D)")
    p_d.add_argument("--ledger", default=None)
    p_d.add_argument("--attributions-dir", default=None)
    p_d.add_argument("--output-dir", default=None)
    p_d.add_argument("--cross-validate", default=None,
                      help="Comma-separated: walk_forward,permutation,leave_one_regime_out")
    p_d.add_argument("--allow-sparse-ledger", action="store_true", help="Allow sparse ledger for smoke test")

    # Validation (Agent E)
    p_e = sub.add_parser("validation", help="Validation Gate (Agent E)")
    p_e.add_argument("--master-features", default="master_features.parquet")
    p_e.add_argument("--override-target-cagr", type=float, default=None, help="Override target CAGR threshold (requires --override-gate-thresholds)")
    p_e.add_argument("--max-cycles", type=int, default=5)
    p_e.add_argument("--parameters", default=None, help="Path to synthesis parameters JSON")
    p_e.add_argument("--override-gate-thresholds", action="store_true", default=False)
    p_e.add_argument("--override-justification", default=None)
    p_e.add_argument("--allow-sparse-ledger", action="store_true", help="Allow sparse ledger for smoke test")

    # Agent E Phase 1
    p_e1 = sub.add_parser("agent_e_phase1", help="Phase E1: CV Parameter Optimization (Agent E)")
    p_e1.add_argument("--master-features", default="master_features.parquet")
    p_e1.add_argument("--synthesis-dir", default="synthesis")
    p_e1.add_argument("--validation-dir", default="validation/e1_cv")
    p_e1.add_argument("--ledger", default="runs_ledger.parquet")
    p_e1.add_argument("--attributions-dir", default="attributions")
    p_e1.add_argument("--train-cv-start", default="2016-01-01")
    p_e1.add_argument("--train-cv-end", default="2023-12-31")
    p_e1.add_argument("--max-iterations", type=int, default=20)
    p_e1.add_argument("--early-stop-improvement-threshold", type=float, default=0.02)
    p_e1.add_argument("--early-stop-stalled-count", type=int, default=5)
    p_e1.add_argument("--rebalance-frequency", default="monthly")
    p_e1.add_argument("--portfolio-size", type=int, default=20)
    p_e1.add_argument("--investigation-model", default="claude-opus-4-6")
    p_e1.add_argument("--wall-clock-cap-days", type=int, default=14)
    p_e1.add_argument("--allow-sparse-ledger", action="store_true", help="Allow sparse ledger for smoke test")

    # Agent E Phase 2
    p_e2 = sub.add_parser("agent_e_phase2", help="Phase E2: Holdout Evaluation (Agent E)")
    p_e2.add_argument("--master-features", default="master_features.parquet")
    p_e2.add_argument("--locked-params", default="validation/e1_cv/locked_parameters.json")
    p_e2.add_argument("--holdout-dir", default="validation/e2_holdout")
    p_e2.add_argument("--holdout-start", default="2024-01-01")
    p_e2.add_argument("--holdout-end", default="2025-12-31")
    p_e2.add_argument("--ledger", default="runs_ledger.parquet")
    p_e2.add_argument("--attributions-dir", default="attributions")
    p_e2.add_argument("--override-target-cagr", type=float, default=None, help="Override target CAGR threshold (requires --override-gate-thresholds)")
    p_e2.add_argument("--output-final-dir", default="final")
    p_e2.add_argument("--burn-holdout-and-restart", action="store_true", default=False)
    p_e2.add_argument("--override-gate-thresholds", action="store_true", default=False)
    p_e2.add_argument("--override-justification", default=None)
    p_e2.add_argument("--allow-sparse-ledger", action="store_true", help="Allow sparse ledger for smoke test")

    # Preflight
    p_pref = sub.add_parser("preflight", help="Run Pre-run Sanity Checks")
    p_pref.add_argument("--config", default="production.yaml", help="Configuration file path")
    p_pref.add_argument("--window", default="2018-01-01:2025-06-30", help="Time window (start:end)")
    p_pref.add_argument("--cache-dir", default="fmp_cache", help="Cache directory")
    p_pref.add_argument("--override-target-cagr", type=float, default=None, help="Override target CAGR threshold (requires --override-gate-thresholds)")
    p_pref.add_argument("--override-gate-thresholds", action="store_true", default=False, help="Allow overriding gate thresholds")
    p_pref.add_argument("--override-justification", default=None, help="Justification for threshold override")
    p_pref.add_argument("--smoke-test", action="store_true", help="Bypass window length check for smoke testing")

    # Postflight
    p_post = sub.add_parser("postflight", help="Run Post-run Validation Checks")
    p_post.add_argument("--final-dir", default="synthesis", help="Directory containing final approved strategy")
    p_post.add_argument("--allow-sparse-ledger", action="store_true", help="Allow sparse ledger for testing")

    args = parser.parse_args()

    # Enforce override rules for gate immutability
    if getattr(args, "override_target_cagr", None) is not None:
        if not getattr(args, "override_gate_thresholds", False):
            parser.error("Changing target CAGR requires --override-gate-thresholds")
        justification = getattr(args, "override_justification", None)
        if not justification or len(justification) >= 40:
            parser.error("Gate threshold override requires --override-justification with less than 40 characters")

    if args.command == "agent_a":
        cmd_agent_a(args)
    elif args.command == "attribution":
        cmd_attribution(args)
    elif args.command == "synthesis":
        cmd_synthesis(args)
    elif args.command == "validation":
        cmd_validation(args)
    elif args.command == "agent_e_phase1":
        cmd_agent_e_phase1(args)
    elif args.command == "agent_e_phase2":
        cmd_agent_e_phase2(args)
    elif args.command == "preflight":
        cmd_preflight(args)
    elif args.command == "postflight":
        cmd_postflight(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
