"""
Phase 2: Reproduce the EXACT walk-forward backtest from validation.py
and cross-check per-fold CAGRs. Then compare methodology vs B15/B17.
"""
import pandas as pd
import numpy as np
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

df = pd.read_parquet("master_features.parquet")
df["scan_date"] = pd.to_datetime(df["scan_date"])

# HMM regime
print("Training HMM regimes...")
if "regime" not in df.columns:
    try:
        from b10_dual_engine import train_hmm_regimes
        regime_df = train_hmm_regimes(df)
        df = pd.merge(df, regime_df, on="scan_date", how="inner")
        print(f"  Regime distribution: {df['regime'].value_counts().to_dict()}")
    except Exception as e:
        print(f"  FAILED: {e} -- defaulting to BULL")
        df["regime"] = "BULL"

# Import the EXACT walk_forward_backtest function
from alpha_compounder.agent_e.validation import (
    walk_forward_backtest,
    compound_cagr_from_fold_returns,
    arithmetic_mean_of_returns,
)

# Approved parameters
params = {
    "min_margin_a": 0.05,
    "min_margin_b": 0.04,
    "min_roe_a": 0.20,
    "min_roe_b": 0.15,
    "min_roic_a": 0.10,
    "max_positions_a": 15,
    "max_positions_b": 25,
    "transaction_cost_bps": 15,
    "regime_weights_a": {
        "BULL": {"dcf": 0.5411365425074178, "epv": 0.26206632189098356, "acq": 0.19679713560159853},
        "BEAR": {"acq": 0.4829171589770169, "dcf": 0.35924016236978706, "epv": 0.15784267865319607},
        "SIDEWAYS": {"epv": 0.4493859954216343, "acq": 0.25242311100462295, "dcf": 0.2981908935737427}
    }
}

folds = [
    {"label": "Fold 1 (2021)", "val_start": "2021-01-01", "val_end": "2021-12-31"},
    {"label": "Fold 2 (2022)", "val_start": "2022-01-01", "val_end": "2022-12-31"},
    {"label": "Fold 3 (2023)", "val_start": "2023-01-01", "val_end": "2023-12-31"},
    {"label": "Fold 4 (2024)", "val_start": "2024-01-01", "val_end": "2024-12-31"},
]

print("\n" + "=" * 70)
print("  WALK-FORWARD FOLD REPRODUCTION")
print("=" * 70)

fold_cagrs = []
for fold in folds:
    cagr = walk_forward_backtest(df, fold["val_start"], fold["val_end"], params)
    fold_cagrs.append(cagr)
    print(f"  {fold['label']:15s}: CAGR = {cagr*100:.2f}%")

compound = compound_cagr_from_fold_returns(fold_cagrs, years_per_fold=1.0)
arithmetic = arithmetic_mean_of_returns(fold_cagrs)
print(f"\n  Compound CAGR:   {compound*100:.2f}%")
print(f"  Arithmetic Mean: {arithmetic*100:.2f}%")
print(f"  Target:          20.00%")
print(f"  Match approved:  {abs(compound - 0.2091) < 0.005}")

# --- SPY benchmark ---
print("\n" + "=" * 70)
print("  SPY BENCHMARK COMPARISON (same fold windows)")
print("=" * 70)
# Approximate SPY annual returns for comparison
spy_returns = {
    2021: 0.286,   # S&P 500 total return 2021
    2022: -0.182,  # S&P 500 total return 2022
    2023: 0.262,   # S&P 500 total return 2023
    2024: 0.250,   # S&P 500 total return 2024
}
for fold, cagr in zip(folds, fold_cagrs):
    year = int(fold["val_start"][:4])
    spy = spy_returns.get(year, 0)
    alpha = cagr - spy
    marker = "++ ALPHA" if alpha > 0 else "-- UNDERPERFORM"
    print(f"  {fold['label']:15s}: Strategy={cagr*100:+.2f}%  SPY={spy*100:+.2f}%  Alpha={alpha*100:+.2f}pp  {marker}")

spy_compound = compound_cagr_from_fold_returns(list(spy_returns.values()), 1.0)
print(f"\n  Strategy compound CAGR: {compound*100:.2f}%")
print(f"  SPY compound CAGR:      {spy_compound*100:.2f}%")
print(f"  Alpha over SPY:         {(compound - spy_compound)*100:.2f}pp")

# --- Methodology comparison vs B17 ---
print("\n" + "=" * 70)
print("  METHODOLOGY COMPARISON: Alpha Compounder vs B15/B17")
print("=" * 70)
print("""
  | Dimension          | Alpha Compounder (Agent E)       | B15/B17 (backtest_v9)           |
  |--------------------|----------------------------------|---------------------------------|
  | Period             | 4 x 1yr folds (2021-2024)        | Full 2016-2025 continuous       |
  | CAGR reported      | Geometric chain of 4 fold CAGRs  | Single-pass equity curve CAGR   |
  | Universe           | 904 symbols, weekly rebalance    | Same 904-symbol parquet         |
  | Positions          | 15 (A) + 25 (B) = 40 total      | 20-30 positions (varies)        |
  | Transaction costs  | 15 bps per trade                 | 15 bps per trade                |
  | Stop-loss          | -15% (bull), -20% (bear)         | -12% to -15% (varies)           |
  | Regime scoring     | 3-weight regime-adaptive (DCF/   | Fixed or HMM-based              |
  |                    | EPV/Acquirers)                   |                                 |
  | Parameter search   | Optimized IN-SAMPLE on same      | Walk-forward or fixed           |
  |                    | validation folds                  |                                 |

  CRITICAL METHODOLOGICAL FLAGS:
""")

# --- KEY FINDING: parameter optimization ---
print("  FLAG 1: IN-SAMPLE PARAMETER OPTIMIZATION")
print("  The Alpha Compounder ran a 'parameter search' (per the walkthrough)")
print("  to find parameters that cross the 20% CAGR threshold on the SAME")
print("  4 validation folds used for the final CAGR report.")
print("  This is in-sample optimization -- NOT true out-of-sample validation.")
print("  The reported 20.91% CAGR is an IN-SAMPLE FITTED result.")
print()

# --- KEY FINDING: 4 years vs 10 years ---
print("  FLAG 2: SURVIVORSHIP WINDOW")
print("  Alpha Compounder validates on 2021-2024 (4 years).")
print("  B15/B17 run 2016-2025 (10 years).")
print("  The 2021-2024 window captures the strongest bull market in")
print("  recent history (ex-2022). A 4-year window is too short for")
print("  investment-grade validation.")
print()

# --- KEY FINDING: fold CAGR chaining ---
print("  FLAG 3: FOLD CAGR CHAINING")
print("  Each fold runs an independent portfolio from $100K.")
print("  The 4 fold CAGRs are then chained geometrically.")
print("  This is NOT the same as a continuous equity curve.")
print("  Each fold starts fresh -- no drawdown carryover,")
print("  no position continuity, no timing-sequence risk.")
print()

# --- KEY FINDING: no regime coverage ---
print("  FLAG 4: REGIME COVERAGE")
regime_by_year = {}
for year in [2021, 2022, 2023, 2024]:
    ydf = df[df["scan_date"].dt.year == year]
    if "regime" in ydf.columns:
        dominant = ydf["regime"].mode()[0] if not ydf.empty else "UNKNOWN"
        counts = ydf.groupby("scan_date")["regime"].first().value_counts().to_dict()
        regime_by_year[year] = counts
        print(f"  {year}: {counts}")

print("\n" + "=" * 70)
print("  VERDICT")
print("=" * 70)
print("""
  The 20.91% compound CAGR from the Alpha Compounder is NOT directly
  comparable to the B15 (11.3%) / B17 (15.0%) results because:

  1. IN-SAMPLE OPTIMIZATION: Parameters were searched to maximize CAGR
     on the SAME 4 folds used to report the final number. This is a
     classic overfitting risk. A true out-of-sample test would use folds
     NOT seen during parameter selection.

  2. SHORTER WINDOW: 4 years (2021-2024) vs 10 years (2016-2025).
     Removing 2016-2020 drops the GFC recovery and COVID crash periods.

  3. FOLD INDEPENDENCE: Each fold starts fresh at $100K. No drawdown
     carryover means the geometric chain overstates what a continuous
     portfolio would achieve through 2022's -18% drawdown.

  4. DUAL-ENGINE CONCENTRATION: 40 positions (15+25) with aggressive
     quality filters on a 904-symbol universe can produce high returns
     in strong markets but may not survive regime stress at scale.

  CLASSIFICATION: Flaw (in-sample fitted, not investment-grade).
  RECOMMENDED FIX: Add a held-out 5th fold (2025 or 2016-2020) that
  the parameter optimizer NEVER sees. Report that fold's CAGR as the
  true out-of-sample result.
""")
