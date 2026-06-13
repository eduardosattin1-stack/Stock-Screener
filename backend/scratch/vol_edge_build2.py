#!/usr/bin/env python3
"""Corrected vol-adjusted edge: baseline = mean MODEL-PRED by vol bin (not actual
touch rate), so the metric is calibration-free and isolates within-vol ranking.

edge(stock) = p_model - E[p_model | vol]   (>0 => model ranks it above vol peers)
"""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import joblib
from google.cloud import storage

PARQUET, CUTOFF, N = "time_model_training_data.parquet", "2025-06-01", 20
REG = {"p10_30": ("clf_10pct_30d", "hit_prob_10pct_30d"),
       "p20_60": ("clf_20pct_60d", "hit_prob_60d")}

m = joblib.load("time_model_v4.pkl")
feats, medians = m["features"], m["medians"]
hm = m.get("models_holdout_v3") or m["models_v3"]

df = pd.read_parquet(PARQUET, columns=list(dict.fromkeys(feats + ["scan_date", "f_vol_60d"])))
df["scan_date"] = df["scan_date"].astype(str)
hold = df[df["scan_date"] >= CUTOFF].copy()
X = hold[feats].copy()
for c in feats:
    X[c] = X[c].fillna(medians.get(c, 0.0))
Xv = X.values
vol = hold["f_vol_60d"].values


def proba(key):
    folds = hm[key]
    folds = folds if isinstance(folds, (list, tuple)) else [folds]
    return np.mean([f.predict_proba(Xv)[:, 1] for f in folds], axis=0)


vol_baseline = {}
for regime, (clf, _) in REG.items():
    p = proba(clf)
    qs = np.quantile(vol, np.linspace(0, 1, N + 1))
    edges = [round(float(x), 6) for x in qs[1:-1]]
    idx = np.searchsorted(edges, vol, side="right")
    rate = [round(float(p[idx == i].mean()), 4) if (idx == i).any() else 0.0 for i in range(N)]
    vol_baseline[regime] = {"edges": edges, "rate": rate}
    print(f"{regime} mean-pred baseline by vol bin: {rate}")


def p_vol(regime, v):
    vb = vol_baseline[regime]
    return vb["rate"][int(np.searchsorted(vb["edges"], v, side="right"))]


# cohort: recovered vols + live probs + deciles
prev = json.load(open("scratch/_vol_edge_jun11.json"))
vols = {s: d["f_vol_60d"] for s, d in prev["edges"].items()}
c = storage.Client(); b = c.bucket("screener-signals-carbonbridge")
arch = {s["symbol"]: s for s in json.loads(b.blob("scans/2026-06-11_global.json").download_as_text())["stocks"]}
out, badge = {}, {"p10_30": 0, "p20_60": 0}
dist = {"p10_30": [], "p20_60": []}
dec = {}
for regime in REG:
    st = json.loads(b.blob(f"calibration_tracking/v2/{regime}/open_state.json").download_as_text())
    dec[regime] = {r["symbol"]: r.get("decile") for r in st["records"]}

for sym, v in vols.items():
    s = arch.get(sym, {})
    rec = {"f_vol_60d": round(v, 4)}
    for regime, (_, pf) in REG.items():
        p = s.get(pf)
        if p is None:
            continue
        e = round(float(p) - p_vol(regime, v), 4)
        rec[f"edge_{regime}"] = e
        dist[regime].append(e)
        if e >= 0.10 and (dec[regime].get(sym) or 0) >= 8:
            badge[regime] += 1
    out[sym] = rec

for regime in REG:
    a = np.array(dist[regime])
    print(f"{regime}: edge p10/p50/p90 = {np.percentile(a,10):+.3f}/{np.percentile(a,50):+.3f}/{np.percentile(a,90):+.3f}"
          f"   frac>0: {(a>0).mean():.0%}   STRICT badges (>=.10 & dec>=8): {badge[regime]}   edge>=.05: {(a>=.05).sum()}")

json.dump({"vol_baseline": vol_baseline, "edges": out}, open("scratch/_vol_edge_jun11_v2.json", "w"), indent=2)
print("wrote scratch/_vol_edge_jun11_v2.json")
