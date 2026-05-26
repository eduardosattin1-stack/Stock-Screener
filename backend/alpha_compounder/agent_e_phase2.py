"""
agent_e_phase2.py — Phase E2 holdout validation CLI runner.
"""

import argparse
import logging
import os
import json
import pandas as pd
from alpha_compounder.agent_e.validation import run_phase_e2_holdout, APPROVAL_THRESHOLD_HOLDOUT_CAGR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("agent_e_phase2")

def main():
    parser = argparse.ArgumentParser(description="Phase E2: Holdout Evaluation")
    parser.add_argument("--master-features", default="master_features.parquet", help="Path to master features parquet")
    parser.add_argument("--locked-params", default="validation/e1_cv/locked_parameters.json", help="Path to locked parameters json")
    parser.add_argument("--holdout-dir", default="validation/e2_holdout", help="Holdout folder")
    parser.add_argument("--holdout-start", default="2024-01-01", help="Holdout start date")
    parser.add_argument("--holdout-end", default="2025-12-31", help="Holdout end date")
    parser.add_argument("--ledger", default="runs_ledger.parquet", help="Path to runs ledger (unused)")
    parser.add_argument("--attributions-dir", default="attributions", help="Path to attributions directory (unused)")
    parser.add_argument("--override-target-cagr", type=float, default=None, help="Override target CAGR threshold (requires --override-gate-thresholds)")
    parser.add_argument("--output-final-dir", default="final", help="Directory for final approved/declined strategy json")
    parser.add_argument("--burn-holdout-and-restart", action="store_true", default=False, help="Force override write-once protection")
    parser.add_argument("--override-gate-thresholds", action="store_true", default=False, help="Allow override of spec-locked thresholds")
    parser.add_argument("--override-justification", default=None, help="At least 40-character justification for override")
    parser.add_argument("--allow-sparse-ledger", action="store_true", default=False, help="Allow sparse ledger for smoke/small-sample runs")

    args = parser.parse_args()

    # Enforce override rules for gate immutability
    if args.override_target_cagr is not None:
        if not args.override_gate_thresholds:
            parser.error("Changing target CAGR requires --override-gate-thresholds")
        if not args.override_justification or len(args.override_justification) >= 40:
            parser.error("Gate threshold override requires --override-justification with less than 40 characters")

    if not os.path.exists(args.master_features):
        log.error(f"Master features file not found at: {args.master_features}")
        exit(1)

    if not os.path.exists(args.locked_params):
        log.error(f"Locked parameters file not found at: {args.locked_params}. Run Phase E1 first.")
        exit(1)

    with open(args.locked_params) as f:
        locked_params = json.load(f)

    log.info(f"Loading master features from {args.master_features}...")
    df = pd.read_parquet(args.master_features)
    df['scan_date'] = pd.to_datetime(df['scan_date'])

    # Train HMM regimes if not present
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

if __name__ == "__main__":
    main()
