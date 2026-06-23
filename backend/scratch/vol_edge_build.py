#!/usr/bin/env python3
"""Build the vol-adjusted-edge metric end-to-end and validate the strict badge.

edge(stock) = p_model - p_vol_baseline(f_vol_60d)
  p_vol_baseline = holdout touch rate as a function of realized vol (per regime).

Outputs:
  1. vol_baseline curves (per regime) -> ready to drop into time_model_v4_meta.json
  2. recomputes Jun-11 f_vol_60d for the live cohort via ThetaData
  3. edge per cohort pick + how many get the STRICT badge (edge>=0.10 AND decile>=8)

Writes scratch/_vol_edge_jun11.json (the per-symbol edges) for the backfill step.
"""
import json
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("THETA_EMAIL", "carbonbridge.tech@gmail.com")
os.environ.setdefault("THETA_PASSWORD", "$ccp1985R")

from google.cloud import storage
import calibration_tracker as ct

PARQUET = "time_model_training_data.parquet"
CUTOFF = "2025-06-01"
N_BINS = 20
# regime -> (model prob target col, live hit_prob field, decile field)
REGIMES = {
    "p10_30": ("hit_10pct_30d", "hit_prob_10pct_30d"),
    "p20_60": ("hit_20pct_60d", "hit_prob_60d"),
}

# ---- 1. vol_baseline curves from holdout -------------------------------------
df = pd.read_parquet(PARQUET, columns=["scan_date", "f_vol_60d", "hit_10pct_30d", "hit_20pct_60d"])
df["scan_date"] = df["scan_date"].astype(str)
hold = df[df["scan_date"] >= CUTOFF]
print(f"holdout rows: {len(hold)}\n")

vol_baseline = {}
for regime, (tgt, _) in REGIMES.items():
    v = hold["f_vol_60d"].values
    y = hold[tgt].fillna(0).astype(int).values
    qs = np.quantile(v, np.linspace(0, 1, N_BINS + 1))
    edges = list(np.round(qs[1:-1], 6))            # 19 internal boundaries
    idx = np.searchsorted(edges, v, side="right")
    rate = [round(float(y[idx == i].mean()), 4) if (idx == i).any() else 0.0
            for i in range(N_BINS)]
    vol_baseline[regime] = {"edges": edges, "rate": rate}
    print(f"{regime} vol_baseline rate by bin: {rate}")
print()


def p_vol(regime, vol):
    vb = vol_baseline[regime]
    return vb["rate"][int(np.searchsorted(vb["edges"], vol, side="right"))]


# ---- 2. recompute Jun-11 f_vol_60d for the cohort via ThetaData --------------
c = storage.Client()
b = c.bucket("screener-signals-carbonbridge")
arch = json.loads(b.blob("scans/2026-06-11_global.json").download_as_text())
astocks = {s.get("symbol"): s for s in arch.get("stocks", [])}
op = json.loads(b.blob("calibration_tracking/v2/p10_30/open_state.json").download_as_text())
syms = sorted({r["symbol"] for r in op.get("records", [])})
print(f"cohort symbols: {len(syms)}  — fetching Jun-11 trailing closes from ThetaData...")

theta = ct.get_theta_client()
SCAN = "2026-06-11"
START = "2026-01-15"   # ~100 trading days of runway for rolling-60


def realized_vol_60(sym):
    bars = ct._fetch_eod_bars(theta, sym, START, SCAN)
    bars = [bar for bar in bars if bar["date"] <= SCAN]
    if len(bars) < 61:
        return None
    close = pd.Series([bar["close"] for bar in bars], dtype=float)
    log_ret = np.log(close / close.shift(1)).fillna(0.0)
    fv = log_ret.rolling(60).std().fillna(0.0) * np.sqrt(252)
    return float(fv.iloc[-1])


vols = {}
miss = []
for i, sym in enumerate(syms):
    try:
        v = realized_vol_60(sym)
    except Exception:
        v = None
    if v is not None and v > 0:
        vols[sym] = v
    else:
        miss.append(sym)
print(f"  recovered vol for {len(vols)}/{len(syms)}  (missing {len(miss)}: {miss[:8]})\n")

# ---- 3. edge + strict badge count --------------------------------------------
out = {}
badge_count = {"p10_30": 0, "p20_60": 0}
edge_summary = {"p10_30": [], "p20_60": []}
for sym in syms:
    if sym not in vols:
        continue
    s = astocks.get(sym, {})
    rec = {}
    for regime, (_, pf) in REGIMES.items():
        p = s.get(pf)
        if p is None:
            continue
        e = round(float(p) - p_vol(regime, vols[sym]), 4)
        rec[f"edge_{regime}"] = e
        edge_summary[regime].append(e)
    out[sym] = {"f_vol_60d": round(vols[sym], 4), **rec}

# strict badge needs decile too — pull from open_state records
for regime in REGIMES:
    st = json.loads(b.blob(f"calibration_tracking/v2/{regime}/open_state.json").download_as_text())
    dec = {r["symbol"]: r.get("decile") for r in st.get("records", [])}
    for sym, rec in out.items():
        e = rec.get(f"edge_{regime}")
        if e is not None and e >= 0.10 and (dec.get(sym) or 0) >= 8:
            badge_count[regime] += 1

for regime in REGIMES:
    arr = np.array(edge_summary[regime])
    print(f"{regime}: edge p25/p50/p75 = {np.percentile(arr,25):+.3f}/{np.percentile(arr,50):+.3f}/{np.percentile(arr,75):+.3f}"
          f"   frac edge>0: {(arr>0).mean():.0%}   STRICT badges (edge>=.10 & dec>=8): {badge_count[regime]}")

with open("scratch/_vol_edge_jun11.json", "w") as f:
    json.dump({"vol_baseline": vol_baseline, "edges": out}, f, indent=2)
print("\nwrote scratch/_vol_edge_jun11.json")
