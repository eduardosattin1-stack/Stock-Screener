#!/usr/bin/env python3
"""Vol-matched lift test for time_model v4 — is there edge beyond vol-scaling?

A fixed +X% barrier is mechanically easier to touch for high-vol names, so a
touch model will lean on volatility. This asks: AFTER conditioning on realized
vol (f_vol_60d), does the model still separate touchers from non-touchers?

Method (honest OOS — uses models_holdout_v3, trained pre-2025-06-01 w/ purge):
  1. Score the holdout slice (scan_date >= 2025-06-01) with the holdout ensemble.
  2. Marginal AUC(model) vs AUC(vol-only baseline = f_vol_60d as the score).
  3. Bucket holdout into vol quintiles; within each, AUC(model|bucket) and the
     top-vs-bottom model-decile touch-rate lift. Average conditional AUC is the
     verdict: >0.5 => signal beyond vol; ~0.5 => pure vol proxy.
"""
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

CUTOFF = "2025-06-01"
PARQUET = "time_model_training_data.parquet"
TARGETS = {"clf_10pct_30d": "hit_10pct_30d", "clf_20pct_60d": "hit_20pct_60d"}

m = joblib.load("time_model_v4.pkl")
feats = m["features"]
medians = m["medians"]
holdout_models = m.get("models_holdout_v3") or m["models_v3"]
which = "models_holdout_v3" if m.get("models_holdout_v3") else "models_v3 (fallback)"

cols = list(dict.fromkeys(feats + list(TARGETS.values()) + ["scan_date", "f_vol_60d"]))
df = pd.read_parquet(PARQUET, columns=cols)
df["scan_date"] = df["scan_date"].astype(str)
hold = df[df["scan_date"] >= CUTOFF].copy()
print(f"holdout rows (scan_date >= {CUTOFF}): {len(hold)}   scorer: {which}\n")

# Feature matrix with median fill (matches serving)
X = hold[feats].copy()
for c in feats:
    X[c] = X[c].fillna(medians.get(c, 0.0))
Xv = X.values


def ensemble_proba(model_key):
    folds = holdout_models[model_key]
    if not isinstance(folds, (list, tuple)):
        folds = [folds]
    ps = []
    for mdl in folds:
        try:
            ps.append(mdl.predict_proba(Xv)[:, 1])
        except Exception:
            ps.append(mdl.predict(Xv))
    return np.mean(ps, axis=0)


for key, tgt in TARGETS.items():
    y = hold[tgt].fillna(0).astype(int).values
    p = ensemble_proba(key)
    vol = hold["f_vol_60d"].fillna(hold["f_vol_60d"].median()).values

    auc_model = roc_auc_score(y, p)
    auc_vol = roc_auc_score(y, vol)                 # vol-only baseline
    print(f"=== {key}  (target {tgt}, base touch rate {y.mean():.3f}) ===")
    print(f"  MARGINAL AUC: model={auc_model:.4f}   vol-only(f_vol_60d)={auc_vol:.4f}")

    # Vol quintiles
    hold["_vq"] = pd.qcut(vol, 5, labels=False, duplicates="drop")
    cond_aucs, cond_lifts, rows = [], [], []
    for q in sorted(hold["_vq"].dropna().unique()):
        mask = (hold["_vq"] == q).values
        yq, pq, vq = y[mask], p[mask], vol[mask]
        if yq.sum() == 0 or yq.sum() == len(yq):
            continue
        a_model = roc_auc_score(yq, pq)
        a_vol = roc_auc_score(yq, vq)               # residual vol AUC inside band
        cond_aucs.append(a_model)
        # top vs bottom MODEL-decile touch rate inside this vol band
        dec = pd.qcut(pd.Series(pq).rank(method="first"), 10, labels=False)
        top = yq[(dec == 9).values].mean()
        bot = yq[(dec == 0).values].mean()
        cond_lifts.append(top - bot)
        rows.append((q, len(yq), yq.mean(), a_model, a_vol, bot, top))

    print(f"  {'volQ':>4} {'n':>7} {'touch%':>7} {'AUCmdl':>7} {'AUCvol':>7} {'botDec%':>8} {'topDec%':>8}")
    for q, n, tr, am, av, bot, top in rows:
        print(f"  {int(q):>4} {n:>7} {tr*100:>6.1f}% {am:>7.3f} {av:>7.3f} {bot*100:>7.1f}% {top*100:>7.1f}%")
    print(f"  CONDITIONAL (vol-matched) AUC avg: {np.mean(cond_aucs):.4f}   "
          f"avg within-band top-bot lift: {np.mean(cond_lifts)*100:.1f}pp")
    verdict = ("EDGE beyond vol" if np.mean(cond_aucs) > 0.55
               else "marginal edge" if np.mean(cond_aucs) > 0.52
               else "≈ vol proxy")
    print(f"  VERDICT: {verdict}\n")
