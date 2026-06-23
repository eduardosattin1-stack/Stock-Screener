"""
agent_e_phase1.py — Phase E1 validation optimization CLI runner.
"""

import argparse
import logging
import os
import pandas as pd
from alpha_compounder.agent_e.validation import run_phase_e1_optimization

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("agent_e_phase1")

def main():
    parser = argparse.ArgumentParser(description="Phase E1: CV Parameter Optimization")
    parser.add_argument("--master-features", default="master_features.parquet", help="Path to master features parquet")
    parser.add_argument("--synthesis-dir", default="synthesis", help="Directory where synthesis parameters reside")
    parser.add_argument("--validation-dir", default="validation/e1_cv", help="Validation output directory")
    parser.add_argument("--ledger", default="runs_ledger.parquet", help="Path to runs ledger (unused)")
    parser.add_argument("--attributions-dir", default="attributions", help="Path to attributions directory (unused)")
    parser.add_argument("--train-cv-start", default="2016-01-01", help="Train and CV start date")
    parser.add_argument("--train-cv-end", default="2023-12-31", help="Train and CV end date")
    parser.add_argument("--max-iterations", type=int, default=20, help="Max optimization iterations")
    parser.add_argument("--early-stop-improvement-threshold", type=float, default=0.02, help="Stall threshold")
    parser.add_argument("--early-stop-stalled-count", type=int, default=5, help="Iterations to wait before early stop")
    parser.add_argument("--rebalance-frequency", default="monthly", help="Rebalance frequency")
    parser.add_argument("--portfolio-size", type=int, default=20, help="Target portfolio size")
    parser.add_argument("--investigation-model", default="claude-opus-4-6", help="Heavy LLM for investigation")
    parser.add_argument("--wall-clock-cap-days", type=int, default=14, help="Wall clock time limit")

    args = parser.parse_args()

    if not os.path.exists(args.master_features):
        log.error(f"Master features file not found at: {args.master_features}")
        exit(1)

    log.info(f"Loading master features from {args.master_features}...")
    df = pd.read_parquet(args.master_features)
    df['scan_date'] = pd.to_datetime(df['scan_date'])

    # Train HMM regimes if not present
    if 'regime' not in df.columns:
        from b10_dual_engine import train_hmm_regimes
        regime_df = train_hmm_regimes(df)
        df = pd.merge(df, regime_df, on='scan_date', how='inner')

    # Locate initial parameters if any
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

if __name__ == "__main__":
    main()
