"""
Forensic audit: compare Alpha Compounder validation gate CAGR (20.91%)
vs B15/B16/B17 backtest CAGRs (11-15%) from the multi-agent project.
"""
import pandas as pd
import numpy as np
import json, os

df = pd.read_parquet("master_features.parquet")
df["scan_date"] = pd.to_datetime(df["scan_date"])

print("=" * 70)
print("  FORENSIC CAGR AUDIT — Alpha Compounder vs Multi-Agent Backtests")
print("=" * 70)

# ─── 1. Data Universe ───
print("\n1. DATA UNIVERSE")
print(f"   Rows: {len(df):,}")
print(f"   Symbols: {df['symbol'].nunique()}")
print(f"   Date range: {df['scan_date'].min().date()} -> {df['scan_date'].max().date()}")
print(f"   Scan dates: {df['scan_date'].nunique()}")

# ─── 2. Feature availability (scoring columns) ───
print("\n2. FEATURE AVAILABILITY (key scoring columns)")
key_cols = ["iv15_discount", "acquirers_multiple", "epv_to_ev",
            "net_margin", "roe", "roic", "eps_growth_3y", "price"]
total = len(df)
for c in key_cols:
    if c in df.columns:
        nn = df[c].notna().sum()
        nz = ((df[c].notna()) & (df[c] != 0)).sum()
        print(f"   {c:35s}: {nn:>7,}/{total:,} non-null ({nn/total*100:.1f}%), {nz:>7,} non-zero ({nz/total*100:.1f}%)")
    else:
        print(f"   {c:35s}: MISSING FROM DATASET")

# ─── 3. Validate fold periods vs actual data ───
print("\n3. WALK-FORWARD FOLD DATA COVERAGE")
folds = [
    {"label": "Fold 1 (2021)", "start": "2021-01-01", "end": "2021-12-31"},
    {"label": "Fold 2 (2022)", "start": "2022-01-01", "end": "2022-12-31"},
    {"label": "Fold 3 (2023)", "start": "2023-01-01", "end": "2023-12-31"},
    {"label": "Fold 4 (2024)", "start": "2024-01-01", "end": "2024-12-31"},
]
for fold in folds:
    fdf = df[(df["scan_date"] >= fold["start"]) & (df["scan_date"] <= fold["end"])]
    syms = fdf["symbol"].nunique()
    dates = fdf["scan_date"].nunique()
    print(f"   {fold['label']:15s}: {len(fdf):>6,} rows, {syms:>4} symbols, {dates:>3} dates")

# ─── 4. Replicate the backtest CAGR per fold ───
print("\n4. REPLICATE FOLD CAGRs (approved parameters)")

# Load approved params
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
        "BULL": {"dcf": 0.5411, "epv": 0.2621, "acq": 0.1968},
        "BEAR": {"acq": 0.4829, "dcf": 0.3592, "epv": 0.1578},
        "SIDEWAYS": {"epv": 0.4494, "acq": 0.2524, "dcf": 0.2982}
    }
}

# Check: does `regime` column exist already?
has_regime = "regime" in df.columns
print(f"   Regime column present: {has_regime}")

if not has_regime:
    # Default to BULL for analysis
    df["regime"] = "BULL"
    print("   WARNING: No regime column — defaulting all to BULL")

# ─── 5. Critical bug hunt: check .get() on Series ───
print("\n5. BUG HUNT: pandas .get() on DataFrame columns")
test_date = df["scan_date"].unique()[100]
test_df = df[df["scan_date"] == test_date].copy()
test_df.set_index("symbol", inplace=True)
test_df = test_df[~test_df.index.duplicated(keep="first")]

for c in ["net_margin", "eps_growth_3y", "roe", "roic",
          "acquirers_multiple", "iv15_discount", "epv_to_ev"]:
    result = test_df.get(c, 0)
    if isinstance(result, (int, float)):
        print(f"   test_df.get('{c}', 0) -> scalar {result} (COLUMN MISSING — returns default)")
    else:
        print(f"   test_df.get('{c}', 0) -> Series len={len(result)}, non-null={result.notna().sum()}, "
              f"non-zero={(result != 0).sum()}")

# ─── 6. Check the mask logic ───
print("\n6. ENGINE A/B CANDIDATE POOL SIZES (per fold)")
for fold in folds:
    fdf = df[(df["scan_date"] >= fold["start"]) & (df["scan_date"] <= fold["end"])].copy()
    if fdf.empty:
        print(f"   {fold['label']}: NO DATA")
        continue

    dates = sorted(fdf["scan_date"].unique())
    total_a_cands = 0
    total_b_cands = 0
    rebalance_count = 0
    last_month = None

    for dt in dates:
        m = pd.to_datetime(dt).month
        if m == last_month:
            continue
        last_month = m
        rebalance_count += 1

        td = fdf[fdf["scan_date"] == dt].copy()
        td.set_index("symbol", inplace=True)
        td = td[~td.index.duplicated(keep="first")]

        # Engine A mask
        mask_a = (
            (td.get("net_margin", 0) >= params["min_margin_a"]) &
            (td.get("eps_growth_3y", 0) > 0) &
            (td.get("roe", 0) > params["min_roe_a"]) &
            (td.get("roic", 0) > params["min_roic_a"]) &
            (td.get("acquirers_multiple", 999) > 0) &
            (td.get("iv15_discount", 999) > 0) &
            (td.get("epv_to_ev", 0) > 0)
        )
        if isinstance(mask_a, pd.Series):
            total_a_cands += mask_a.sum()
        
        # Engine B mask
        mask_b = (
            (td.get("net_margin", 0) >= params["min_margin_b"]) &
            (td.get("roe", 0) > params["min_roe_b"]) &
            (td.get("eps_growth_3y", 0) > -0.50) &
            (td.get("acquirers_multiple", 999) > 0) &
            (td.get("iv15_discount", 999) > 0) &
            (td.get("epv_to_ev", 0) > 0) &
            (td["price"] > 0)
        )
        if isinstance(mask_b, pd.Series):
            total_b_cands += mask_b.sum()

    avg_a = total_a_cands / rebalance_count if rebalance_count > 0 else 0
    avg_b = total_b_cands / rebalance_count if rebalance_count > 0 else 0
    print(f"   {fold['label']:15s}: {rebalance_count} rebalances, "
          f"Avg A candidates: {avg_a:.0f}, Avg B candidates: {avg_b:.0f}")

# ─── 7. Critical: check if `today_data.get('col', 0) >= X` is always True ───
print("\n7. CRITICAL: .get() with default 0 — False-positive filter pass check")
sample_dt = sorted(df["scan_date"].unique())[200]
td = df[df["scan_date"] == sample_dt].copy()
td.set_index("symbol", inplace=True)
td = td[~td.index.duplicated(keep="first")]

for c in ["acquirers_multiple", "iv15_discount", "epv_to_ev"]:
    val = td.get(c, 0)
    if isinstance(val, (int, float)):
        # Column missing, .get returns scalar 0
        print(f"   '{c}' -> .get returns SCALAR 0 -> (0 > 0) is FALSE -> filter BLOCKS correctly")
    else:
        zeros = (val == 0).sum()
        nulls = val.isna().sum()
        pos = (val > 0).sum()
        neg = (val < 0).sum()
        total = len(val)
        print(f"   '{c}' -> {total} rows: {pos} positive, {neg} negative, {zeros} zero, {nulls} null")

# ─── 8. Check "missing stock" exit at 0.5x ───
print("\n8. MISSING-STOCK EXIT PENALTY (0.5x entry price)")
for fold in folds:
    fdf = df[(df["scan_date"] >= fold["start"]) & (df["scan_date"] <= fold["end"])].copy()
    dates = sorted(fdf["scan_date"].unique())
    if len(dates) < 2:
        continue
    first_syms = set(fdf[fdf["scan_date"] == dates[0]]["symbol"])
    last_syms = set(fdf[fdf["scan_date"] == dates[-1]]["symbol"])
    disappeared = first_syms - last_syms
    appeared = last_syms - first_syms
    print(f"   {fold['label']:15s}: {len(disappeared)} symbols disappeared, "
          f"{len(appeared)} appeared, persistence={len(first_syms & last_syms)/len(first_syms)*100:.1f}%")

# ─── 9. Key question: is eps_growth_3y == eps_growth_3y column or something else? ───
print("\n9. COLUMN NAMING: eps_growth_3y vs eps_growth_1y")
for c in ["eps_growth_3y", "eps_growth_1y", "eps_growth_3y"]:
    if c in df.columns:
        vals = df[c].dropna()
        print(f"   {c}: median={vals.median():.4f}, mean={vals.mean():.4f}, "
              f"std={vals.std():.4f}, min={vals.min():.4f}, max={vals.max():.4f}")

# ─── 10. Final: compound CAGR from approved_strategy.json ───
print("\n10. APPROVED STRATEGY CAGR BREAKDOWN")
strat_path = os.path.join("synthesis", "approved_strategy.json")
if os.path.exists(strat_path):
    with open(strat_path) as f:
        strat = json.load(f)
    perf = strat.get("approved_strategy", {}).get("performance", {})
    print(f"   overall_cagr (compound):           {perf.get('overall_cagr', 'N/A')}")
    print(f"   arithmetic_mean_of_fold_returns:    {perf.get('arithmetic_mean_of_fold_returns', 'N/A')}")
    print(f"   rolling_5yr_cagrs:                  {perf.get('rolling_5yr_cagrs', 'N/A')}")
    print(f"   regime_cagrs:                       {perf.get('regime_cagrs', 'N/A')}")

    # Check Jensen's inequality
    compound = perf.get("overall_cagr", 0)
    arithmetic = perf.get("arithmetic_mean_of_fold_returns", 0)
    if compound > 0 and arithmetic > 0:
        gap = arithmetic - compound
        print(f"\n   Jensen gap (arith - compound): {gap*100:.2f}pp")
        if compound > arithmetic:
            print("   !! VIOLATION: compound > arithmetic (impossible)")
        else:
            print(f"   OK: compound ({compound*100:.2f}%) <= arithmetic ({arithmetic*100:.2f}%)")

print("\n" + "=" * 70)
print("  AUDIT COMPLETE")
print("=" * 70)
