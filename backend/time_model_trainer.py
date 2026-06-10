#!/usr/bin/env python3
"""
Time-Model Trainer — Purged Walk-Forward ML training with Anti-Overfitting Harness.
==================================================================================
Trains 4 classification models (P10/P20 touch probabilities) + 2 regression models
(max drawdown) using the parquet training data built by time_model_data_steward.py.

Guarantees zero-leakage, unique-weighting correction, and strict validation.
"""

import os
import sys
import json
import hashlib
import logging
import argparse
import joblib
from datetime import datetime
import numpy as np
import pandas as pd

from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, brier_score_loss, r2_score, mean_absolute_error

# Import anti-overfitting harness
from anti_overfitting_harness import (
    PurgedEmbargoedWalkForwardCV,
    compute_sample_uniqueness,
    symbol_disjoint_split,
    evaluate_trivial_baselines
)

# v4 shared feature spec (the declared keep-list replaces column sweeping)
from time_model_features import FEATURES_V4, FEATURE_SPEC_VERSION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("TimeModel-Trainer")

BACKEND = os.path.dirname(os.path.abspath(__file__))

# Exclude metadata and non-features
EXCLUDE_COLS = {
    "symbol", "scan_date", "price", "sector", "industry", "country",
    "hit_10pct_30d", "hit_10pct_60d", "hit_20pct_30d", "hit_20pct_60d",
    "max_dd_30d", "max_dd_60d", "days_to_20pct", "max_gain_60d",
    "bars_to_10pct", "bars_to_20pct",
    "scan_date_str", "target_valid"
}

# Targets mapping
CLF_TARGETS = {
    "clf_10pct_30d": "hit_10pct_30d",
    "clf_10pct_60d": "hit_10pct_60d",
    "clf_20pct_30d": "hit_20pct_30d",
    "clf_20pct_60d": "hit_20pct_60d",
}

REG_TARGETS = {
    "reg_dd_30d": "max_dd_30d",
    "reg_dd_60d": "max_dd_60d",
}

# LGBM Hyperparameters
CLF_PARAMS = dict(
    objective="binary",
    n_estimators=150,
    max_depth=5,
    learning_rate=0.03,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_samples=30,
    reg_alpha=0.1,
    reg_lambda=1.0,
    random_state=42,
    verbosity=-1
)

REG_PARAMS = dict(
    objective="regression",
    n_estimators=150,
    max_depth=5,
    learning_rate=0.03,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_samples=30,
    reg_alpha=0.1,
    reg_lambda=1.0,
    random_state=42,
    verbosity=-1
)

N_SPLITS = 6
OOS_CUTOFF = "2025-06-01"
MIN_HOLDOUT_ROWS = 500

# Purge at the holdout boundary: rows whose 60-trading-bar label window can
# cross OOS_CUTOFF are excluded from holdout-model training. 90 calendar days
# ~= 60 trading bars (same convention as PurgedEmbargoedWalkForwardCV;
# may undercount a bar or two across long holiday stretches).
PURGE_CAL_DAYS = 90
PURGE_TRADING_BARS = 60

# Time-to-touch CDF regimes persisted in the v4 artifact:
# clf key -> (bars-to-first-touch column, horizon K in trading bars)
TOUCH_CDF_SPECS = {
    "clf_10pct_30d": ("bars_to_10pct", 30),
    "clf_20pct_60d": ("bars_to_20pct", 60),
}

HORIZON_CONVENTION = (
    "trading bars, entry bar excluded, bars 1-indexed from the first bar "
    "after entry; targets use intraday high >= entry_close*(1+threshold); "
    "touch_cdf F_d(k) = unconditional P(first touch <= bar k | decile d) on "
    "the holdout slice, so F_d(K) == the decile hit_rate; holdout purge uses "
    "90 calendar days ~= 60 trading bars (may undercount a bar or two across "
    "long holiday stretches)"
)


def identify_features(df: pd.DataFrame) -> list:
    """Identify feature columns from the dataframe."""
    candidates = []
    for c in df.columns:
        if c in EXCLUDE_COLS:
            continue
        if c.startswith("f_") or c.startswith("opt_"):
            candidates.append(c)
    candidates.sort()
    log.info(f"Identified {len(candidates)} feature columns")
    return candidates


def compute_decile_lift(y_true, y_prob, w_test=None):
    """Verify monotonic touch rate across predicted probability deciles."""
    df_lift = pd.DataFrame({"y_true": y_true, "y_prob": y_prob})
    if w_test is not None:
        df_lift["weight"] = w_test
    else:
        df_lift["weight"] = 1.0
        
    df_lift["decile"] = pd.qcut(df_lift["y_prob"], 10, labels=False, duplicates="drop")
    
    decile_rates = []
    for d, grp in df_lift.groupby("decile"):
        rate = np.average(grp["y_true"], weights=grp["weight"])
        decile_rates.append((d, rate))
        
    decile_rates.sort(key=lambda x: x[0])
    rates = [r[1] for r in decile_rates]
    
    # Check if generally increasing (correlation with decile number > 0.85)
    if len(rates) >= 2:
        corr = np.corrcoef(range(len(rates)), rates)[0, 1]
        is_monotonic = bool(corr > 0.85)
    else:
        corr = 1.0
        is_monotonic = True
        
    return rates, corr, is_monotonic


def _predict_calibrated(model, calibrator, X: np.ndarray) -> np.ndarray:
    """Calibrated probabilities from a single model or a 1+-element ensemble."""
    if isinstance(model, list):
        probs = np.column_stack([m.predict_proba(X)[:, 1] for m in model])
        raw = probs.mean(axis=1)
    else:
        raw = model.predict_proba(X)[:, 1]
    if calibrator is not None:
        raw = calibrator.predict(raw)
    return raw


def compute_holdout_decile_table(df, models, calibrators, features, medians, oos_cutoff,
                                 deploy_models=None, deploy_calibrators=None):
    """Score the FULL df slice scan_date >= oos_cutoff with the HOLDOUT models
    (trained strictly pre-cutoff) + holdout isotonic calibrators, derive edges
    from a 10-way equal-count rank partition, then RE-ASSIGN deciles via the
    live-tracker mapping (searchsorted(edges, p, side='right') + 1) and compute
    all per-decile stats from that assignment.

    Returns (decile_table, touch_cdf, holdout_n, holdout_range) where:
      decile_table[clf_key] = {
        "edges":     [9 floats]  - min calibrated p of deciles 2..10
                                   (drop-in for signal_tracker _decile),
        "hit_rate":  [10 floats] - observed target rate per decile (asc) —
                                   the OFFICIAL baselines,
        "mean_pred": [10 floats] - mean calibrated p per decile,
        "count":     [10 ints],
        "deploy_score_quantiles": {"quantiles": [0.1..0.9],
                                   "values": [9 floats]} | None
                                   - deploy-model score quantiles on the same
                                     slice, for deploy-vs-holdout drift checks,
      }
      touch_cdf[clf_key] = {"pooled": [K floats],
                            "by_decile": {"1".."10": [K floats]}}
        with F(k) = unconditional P(first touch <= bar k); index k-1 = bar k,
        and F(K) == the decile hit_rate (asserted).
    """
    df_h = df[df["scan_date"] >= oos_cutoff].copy().reset_index(drop=True)
    if df_h.empty:
        raise ValueError(f"No holdout rows with scan_date >= {oos_cutoff}")
    for bars_col, _ in TOUCH_CDF_SPECS.values():
        if bars_col not in df_h.columns:
            raise ValueError(
                f"Column '{bars_col}' missing from training data — run "
                f"patch_parquet_bars_to_touch.py (or rebuild the parquet) first."
            )

    log.info("\n── Holdout decile table (scan_date >= %s, %s rows) ──",
             oos_cutoff, f"{len(df_h):,}")

    Xdf = df_h[features].astype(np.float64).replace([np.inf, -np.inf], np.nan)
    for f in features:
        Xdf[f] = Xdf[f].fillna(medians.get(f, 0.0))
    X = np.clip(Xdf.values, -100, 100)

    decile_table = {}
    touch_cdf = {}

    for model_key, target_col in CLF_TARGETS.items():
        model = models.get(model_key)
        calibrator = calibrators.get(model_key)
        if model is None or calibrator is None:
            raise ValueError(f"Holdout model/calibrator missing for {model_key} — "
                             "cannot build the v4 decile table.")
        if target_col not in df_h.columns:
            raise ValueError(f"Target column {target_col} missing from data.")

        p = _predict_calibrated(model, calibrator, X)
        y = df_h[target_col].fillna(0).astype(int).values

        # Equal-count rank deciles (scratch/compute_deciles.py pattern) —
        # used ONLY to derive the edges (min calibrated p of deciles 2..10).
        qcut_deciles = (pd.qcut(pd.Series(p).rank(method="first"), 10, labels=False) + 1).values

        edges = []
        for d in range(2, 11):
            mask = qcut_deciles == d
            edges.append(float(p[mask].min()) if mask.any() else 0.0)

        # Isotonic calibration produces tied p-values; equal consecutive
        # edges collapse adjacent deciles under the live mapping — shout.
        tied = [i for i in range(1, len(edges)) if edges[i] == edges[i - 1]]
        if tied:
            log.warning(
                "  %s: TIED DECILE EDGES (isotonic ties) at edge positions %s: %s "
                "— adjacent deciles collapse under the live searchsorted mapping; "
                "decile counts will be unequal.",
                model_key, tied, [round(e, 6) for e in edges])

        # Re-assign deciles with the SAME mapping the live tracker uses
        # (calibration_tracker._decile_from_edges: bisect_right(edges, p) + 1
        # == np.searchsorted(edges, p, side='right') + 1 -> deciles 1..10) so
        # the artifact stats below match exactly how live p-values map.
        deciles = np.searchsorted(np.asarray(edges), p, side="right") + 1

        hit_rate, mean_pred, count = [], [], []
        for d in range(1, 11):
            mask = deciles == d
            n_d = int(mask.sum())
            count.append(n_d)
            hit_rate.append(float(y[mask].mean()) if n_d else 0.0)
            mean_pred.append(float(p[mask].mean()) if n_d else 0.0)

        # Deploy-model score quantiles on the same slice (drift monitor)
        deploy_q = None
        if deploy_models and model_key in deploy_models:
            dp = _predict_calibrated(
                deploy_models[model_key],
                (deploy_calibrators or {}).get(model_key),
                X,
            )
            qs = [round(i / 10.0, 1) for i in range(1, 10)]
            deploy_q = {
                "quantiles": qs,
                "values": [float(np.quantile(dp, q)) for q in qs],
            }

        # Log-loud monotonicity check
        rates, lift_corr, is_monotonic = compute_decile_lift(y, p)
        if is_monotonic:
            log.info("  %s: decile hit rates %s (lift corr %.3f) — monotonic ✓",
                     model_key, [f"{r:.1%}" for r in hit_rate], lift_corr)
        else:
            log.warning("  %s: DECILE HIT RATES NOT MONOTONIC (lift corr %.3f < 0.85): %s "
                        "— holdout ranking is unreliable; investigate before deploying.",
                        model_key, lift_corr, [f"{r:.1%}" for r in hit_rate])

        decile_table[model_key] = {
            "edges": edges,
            "hit_rate": hit_rate,
            "mean_pred": mean_pred,
            "count": count,
            "deploy_score_quantiles": deploy_q,
        }

        # Time-to-touch CDFs for the two tracked regimes
        if model_key in TOUCH_CDF_SPECS:
            bars_col, K = TOUCH_CDF_SPECS[model_key]
            bars = df_h[bars_col].values.astype(np.int32)

            def _cdf(mask):
                b = bars[mask]
                n = max(len(b), 1)
                return [float(((b >= 1) & (b <= k)).sum()) / n for k in range(1, K + 1)]

            pooled = _cdf(np.ones(len(df_h), dtype=bool))
            by_decile = {}
            for d in range(1, 11):
                cdf_d = _cdf(deciles == d)
                # Consistency: unconditional F_d(K) must equal the decile hit rate
                if abs(cdf_d[K - 1] - hit_rate[d - 1]) > 1e-6:
                    raise AssertionError(
                        f"{model_key} decile {d}: touch_cdf F({K})={cdf_d[K-1]:.6f} != "
                        f"hit_rate={hit_rate[d-1]:.6f} — {bars_col} is inconsistent with "
                        f"{target_col}; re-run patch_parquet_bars_to_touch.py."
                    )
                by_decile[str(d)] = cdf_d
            touch_cdf[model_key] = {"pooled": pooled, "by_decile": by_decile}
            log.info("  %s: touch CDF over %d bars (pooled F(K)=%.3f)",
                     model_key, K, pooled[K - 1])

    holdout_n = int(len(df_h))
    holdout_range = [str(df_h["scan_date"].min()), str(df_h["scan_date"].max())]
    return decile_table, touch_cdf, holdout_n, holdout_range


class _NumpyEncoder(json.JSONEncoder):
    """JSON encoder for numpy scalars/arrays (validator save_report pattern)."""
    def default(self, o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, np.bool_):
            return bool(o)
        return super().default(o)


def meta_sidecar_path(output_path: str) -> str:
    """Meta sidecar path derived from the output pkl path, so a staging run
    never writes the FINAL sidecar name (the pipeline promotes both together):
      time_model_v4.pkl         -> time_model_v4_meta.json
      time_model_v4.pkl.staging -> time_model_v4_meta.json.staging
    """
    base, suffix = output_path, ""
    if base.endswith(".staging"):
        base, suffix = base[: -len(".staging")], ".staging"
    if base.endswith(".pkl"):
        base = base[:-4]
    return base + "_meta.json" + suffix


def train_classification(df_cv: pd.DataFrame, df_disjoint: pd.DataFrame, features: list,
                         target_col: str, model_name: str, w_cv: pd.Series, w_disjoint: pd.Series) -> dict:
    """Train classification model under the robust anti-overfitting harness."""
    log.info(f"\n  ── Training {model_name} (target={target_col}) ──")
    
    y = df_cv[target_col].values.astype(int)
    X = df_cv[features].values.astype(np.float32)
    dates = df_cv["scan_date"].values
    weights = w_cv.values
    
    pos_rate = np.average(y, weights=weights)
    log.info(f"  Uniqueness-weighted base rate: {pos_rate:.1%}")
    
    # Walk-forward CV
    cv = PurgedEmbargoedWalkForwardCV(n_splits=N_SPLITS)
    
    all_oos_probs = []
    all_oos_labels = []
    all_oos_weights = []
    fold_aucs = []
    fold_baselines = []
    
    for fold, (train_idx, test_idx) in enumerate(cv.split(df_cv)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        w_train, w_test = weights[train_idx], weights[test_idx]
        
        # Impute missing values fold-internally
        medians = np.nanmedian(X_train, axis=0)
        medians = np.nan_to_num(medians, nan=0.0)
        
        X_train = np.nan_to_num(X_train, nan=medians)
        X_test = np.nan_to_num(X_test, nan=medians)
        
        # Clip extreme values
        X_train = np.clip(X_train, -100, 100)
        X_test = np.clip(X_test, -100, 100)
        
        # Train model
        clf = LGBMClassifier(**CLF_PARAMS)
        clf.fit(X_train, y_train, sample_weight=w_train)
        
        probs = clf.predict_proba(X_test)[:, 1]
        all_oos_probs.extend(probs)
        all_oos_labels.extend(y_test)
        all_oos_weights.extend(w_test)
        
        auc = roc_auc_score(y_test, probs, sample_weight=w_test)
        fold_aucs.append(auc)
        
        # Evaluate baseline
        baselines = evaluate_trivial_baselines(X_train, y_train, X_test, y_test, w_train, w_test)
        fold_baselines.append(baselines["base_rate_auc"])
        
        log.info(f"    Fold {fold}: AUC={auc:.4f} (BaseRate AUC={baselines['base_rate_auc']:.2f}), "
                 f"TrainSize={len(train_idx):,}, TestSize={len(test_idx):,}")
                 
    if not fold_aucs:
        log.warning(f"  No valid folds for {model_name}")
        return None
        
    oos_probs = np.array(all_oos_probs)
    oos_labels = np.array(all_oos_labels)
    oos_weights = np.array(all_oos_weights)
    
    cv_auc = roc_auc_score(oos_labels, oos_probs, sample_weight=oos_weights)
    cv_brier = brier_score_loss(oos_labels, oos_probs, sample_weight=oos_weights)
    auc_std = np.std(fold_aucs)
    max_fold_contrib = max(fold_aucs) / sum(fold_aucs)
    
    log.info(f"  CV Out-of-Sample: AUC={cv_auc:.4f}, Brier={cv_brier:.4f}, AUC Std={auc_std:.4f}")
    
    # Isotonic calibration on purged CV predictions
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(oos_probs, oos_labels, sample_weight=oos_weights)
    
    cal_probs = iso.predict(oos_probs)
    cal_auc = roc_auc_score(oos_labels, cal_probs, sample_weight=oos_weights)
    cal_brier = brier_score_loss(oos_labels, cal_probs, sample_weight=oos_weights)
    log.info(f"  Calibrated: AUC={cal_auc:.4f}, Brier={cal_brier:.4f}")
    
    # Realized decile lift check
    decile_rates, lift_corr, is_monotonic = compute_decile_lift(oos_labels, cal_probs, oos_weights)
    log.info(f"  Decile Touch Rates: {[f'{r:.1%}' for r in decile_rates]} (Lift Correlation: {lift_corr:.3f})")
    
    # Train deployment models on all CV data
    medians_all = np.nanmedian(X, axis=0)
    medians_all = np.nan_to_num(medians_all, nan=0.0)
    X_clean = np.nan_to_num(X, nan=medians_all)
    X_clean = np.clip(X_clean, -100, 100)
    
    deploy_clf = LGBMClassifier(**CLF_PARAMS)
    deploy_clf.fit(X_clean, y, sample_weight=weights)
    
    # Evaluate on disjoint symbols (symbol generalization check)
    disjoint_auc = 0.5
    if not df_disjoint.empty:
        y_dis = df_disjoint[target_col].values.astype(int)
        X_dis = df_disjoint[features].values.astype(np.float32)
        X_dis = np.nan_to_num(X_dis, nan=medians_all)
        X_dis = np.clip(X_dis, -100, 100)
        w_dis = w_disjoint.values
        
        dis_probs = deploy_clf.predict_proba(X_dis)[:, 1]
        dis_probs_cal = iso.predict(dis_probs)
        disjoint_auc = roc_auc_score(y_dis, dis_probs_cal, sample_weight=w_dis)
        log.info(f"  Symbol-Disjoint OOS AUC: {disjoint_auc:.4f} (CV OOS AUC gap: {abs(cv_auc - disjoint_auc):.4f})")
        
    # Feature importance
    importances = deploy_clf.feature_importances_ / deploy_clf.feature_importances_.sum()
    top_feats = sorted(zip(features, importances), key=lambda x: -x[1])[:15]
    log.info("  Top Features:")
    for feat, imp in top_feats:
        bar = "█" * int(imp * 100)
        log.info(f"    {feat:<30} {imp:.4f}  {bar}")
        
    return {
        "models": [deploy_clf],  # Expose list for backward compatibility
        "calibrator": iso,
        "oos_auc": round(cv_auc, 6),
        "oos_brier": round(cv_brier, 6),
        "cal_auc": round(cal_auc, 6),
        "cal_brier": round(cal_brier, 6),
        "auc_std": round(auc_std, 6),
        "max_fold_contrib": round(max_fold_contrib, 4),
        "fold_aucs": [round(a, 4) for a in fold_aucs],
        "disjoint_auc": round(disjoint_auc, 6),
        "decile_rates": [round(r, 4) for r in decile_rates],
        "is_monotonic": is_monotonic,
        "importances": dict(top_feats),
        "max_importance": round(float(importances.max()), 4),
        "positive_rate": round(pos_rate, 4),
    }


def train_regression(df_cv: pd.DataFrame, df_disjoint: pd.DataFrame, features: list,
                      target_col: str, model_name: str, w_cv: pd.Series, w_disjoint: pd.Series) -> dict:
    """Train regression model for drawdown under walk-forward purged CV."""
    log.info(f"\n  ── Training {model_name} (target={target_col}) ──")
    
    y = np.abs(df_cv[target_col].values.astype(np.float32))
    X = df_cv[features].values.astype(np.float32)
    weights = w_cv.values
    
    cv = PurgedEmbargoedWalkForwardCV(n_splits=N_SPLITS)
    all_oos_preds = []
    all_oos_actual = []
    all_oos_weights = []
    
    for fold, (train_idx, test_idx) in enumerate(cv.split(df_cv)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        w_train, w_test = weights[train_idx], weights[test_idx]
        
        medians = np.nanmedian(X_train, axis=0)
        medians = np.nan_to_num(medians, nan=0.0)
        X_train = np.nan_to_num(X_train, nan=medians)
        X_test = np.nan_to_num(X_test, nan=medians)
        
        reg = LGBMRegressor(**REG_PARAMS)
        reg.fit(X_train, y_train, sample_weight=w_train)
        
        preds = reg.predict(X_test)
        all_oos_preds.extend(preds)
        all_oos_actual.extend(y_test)
        all_oos_weights.extend(w_test)
        
    oos_preds = np.array(all_oos_preds)
    oos_actual = np.array(all_oos_actual)
    oos_weights = np.array(all_oos_weights)
    
    cv_r2 = r2_score(oos_actual, oos_preds, sample_weight=oos_weights)
    cv_mae = mean_absolute_error(oos_actual, oos_preds, sample_weight=oos_weights)
    log.info(f"  CV Out-of-Sample: R²={cv_r2:.4f}, MAE={cv_mae:.2f}%")
    
    # Train deployment model
    medians_all = np.nanmedian(X, axis=0)
    medians_all = np.nan_to_num(medians_all, nan=0.0)
    X_clean = np.nan_to_num(X, nan=medians_all)
    X_clean = np.clip(X_clean, -100, 100)
    
    deploy_reg = LGBMRegressor(**REG_PARAMS)
    deploy_reg.fit(X_clean, y, sample_weight=weights)
    
    importances = deploy_reg.feature_importances_ / deploy_reg.feature_importances_.sum()
    top_feats = sorted(zip(features, importances), key=lambda x: -x[1])[:15]
    
    return {
        "model": deploy_reg,
        "oos_r2": round(cv_r2, 6),
        "oos_mae": round(cv_mae, 4),
        "importances": dict(top_feats),
        "max_importance": round(float(importances.max()), 4),
    }


class TimeModelTrainer:
    def __init__(
        self,
        data_path: str = "time_model_training_data.parquet",
        output_path: str = "time_model_v4.pkl",
        all_features: bool = False,
    ):
        self.data_path = os.path.join(BACKEND, data_path) if not os.path.isabs(data_path) else data_path
        self.output_path = os.path.join(BACKEND, output_path) if not os.path.isabs(output_path) else output_path
        self.all_features = all_features

        # Hard safety: the v4 trainer must never clobber the deployed v3 artifact.
        if os.path.basename(self.output_path) == "time_model_v3.pkl":
            raise ValueError(
                "Refusing to write to time_model_v3.pkl — the v4 trainer must "
                "emit a new artifact (default: time_model_v4.pkl)."
            )

    def train(self) -> str:
        log.info("=" * 70)
        log.info("  TIME MODEL TRAINER — v4 Pipeline (feature spec %s)", FEATURE_SPEC_VERSION)
        log.info("=" * 70)

        # 1. Load training data
        df = pd.read_parquet(self.data_path)
        log.info(f"Loaded: {df.shape[0]:,} rows × {df.shape[1]} columns")
        df = df.sort_values("scan_date").reset_index(drop=True)

        # 2. Feature list: the declared v4 keep-list (FEATURES_V4) by default;
        #    --all-features falls back to column sweeping for A/B runs.
        if self.all_features:
            log.warning("--all-features: sweeping parquet columns instead of the v4 keep-list")
            features = identify_features(df)
        else:
            missing = [f for f in FEATURES_V4 if f not in df.columns]
            assert not missing, f"keep-list features absent from parquet: {missing}"
            features = sorted(FEATURES_V4)
            log.info(f"Using declared v4 keep-list: {len(features)} features")
        df[features] = df[features].replace([np.inf, -np.inf], np.nan)

        # Medians over the PRE-CUTOFF slice only, so serving fills carry no
        # post-cutoff information.
        pre_cutoff_mask = df["scan_date"] < OOS_CUTOFF
        medians = df.loc[pre_cutoff_mask, features].median().fillna(0.0).to_dict()
        log.info(f"Medians computed over scan_date < {OOS_CUTOFF} "
                 f"({int(pre_cutoff_mask.sum()):,} rows)")

        # 3. Symbol-Disjoint Split (Hold out 15% of symbols entirely)
        df_cv, df_disjoint = symbol_disjoint_split(df, test_size=0.15, random_seed=42)
        df_cv = df_cv.reset_index(drop=True)
        df_disjoint = df_disjoint.reset_index(drop=True)

        # 4. Marcos Lopez de Prado's Sample-Uniqueness Weighting
        w_cv = compute_sample_uniqueness(df_cv, label_window=60)
        w_disjoint = pd.Series(1.0, index=df_disjoint.index)
        if not df_disjoint.empty:
            w_disjoint = compute_sample_uniqueness(df_disjoint, label_window=60)

        # ─── Train classification models ───
        clf_results = {}
        for model_name, target_col in CLF_TARGETS.items():
            if target_col not in df_cv.columns:
                continue
            res = train_classification(df_cv, df_disjoint, features, target_col, model_name, w_cv, w_disjoint)
            if res:
                clf_results[model_name] = res

        # ─── Train regression models ───
        reg_results = {}
        for model_name, target_col in REG_TARGETS.items():
            if target_col not in df_cv.columns:
                continue
            res = train_regression(df_cv, df_disjoint, features, target_col, model_name, w_cv, w_disjoint)
            if res:
                reg_results[model_name] = res

        # ─── Train HOLDOUT models (trained purely on scan_date < purge_cut) ───
        # Evaluated strictly on the true holdout >= OOS_CUTOFF slice.
        # PURGED boundary: rows within PURGE_CAL_DAYS (~60 trading bars) of the
        # cutoff have label windows that extend into the holdout slice — they
        # must not train the holdout models (label leakage at the boundary).
        holdout_models = {}
        holdout_calibrators = {}

        purge_cut = (pd.Timestamp(OOS_CUTOFF) - pd.Timedelta(days=PURGE_CAL_DAYS)).strftime("%Y-%m-%d")

        df_pre = df_cv[df_cv["scan_date"] < purge_cut].copy()
        w_pre = w_cv[df_cv["scan_date"] < purge_cut].copy()

        df_dis_pre = df_disjoint[df_disjoint["scan_date"] < purge_cut].copy() if not df_disjoint.empty else pd.DataFrame()
        w_dis_pre = w_disjoint[df_disjoint["scan_date"] < purge_cut].copy() if not df_disjoint.empty else pd.Series(dtype=np.float32)

        log.info(f"\n── Training holdout models (scan_date < {purge_cut} = "
                 f"cutoff {OOS_CUTOFF} - {PURGE_CAL_DAYS}d purge) ──")
        if len(df_pre) < MIN_HOLDOUT_ROWS:
            log.warning(f"Too few pre-cutoff rows ({len(df_pre)}) — skipping holdout models.")
        else:
            log.info(f"Pre-cutoff rows: {len(df_pre):,}")
            for model_name, target_col in CLF_TARGETS.items():
                res = train_classification(df_pre, df_dis_pre, features, target_col, f"{model_name}_holdout", w_pre, w_dis_pre)
                if res:
                    holdout_models[model_name] = res["models"]
                    holdout_calibrators[model_name] = res["calibrator"]
                    
            for model_name, target_col in REG_TARGETS.items():
                res = train_regression(df_pre, df_dis_pre, features, target_col, f"{model_name}_holdout", w_pre, w_dis_pre)
                if res:
                    holdout_models[model_name] = res["model"]

        # ─── Save pickle payload ───
        models_dict = {}
        calibrators_dict = {}
        oos_metrics = {}

        for name, res in clf_results.items():
            models_dict[name] = res["models"]
            calibrators_dict[name] = res["calibrator"]
            oos_metrics[name] = {
                "auc": res["oos_auc"],
                "brier": res["oos_brier"],
                "cal_auc": res["cal_auc"],
                "cal_brier": res["cal_brier"],
                "disjoint_auc": res["disjoint_auc"],
                "auc_std": res["auc_std"],
                "max_fold_contrib": res.get("max_fold_contrib"),
                "fold_aucs": res.get("fold_aucs"),
                "max_importance": res["max_importance"],
                "positive_rate": res["positive_rate"],
            }

        for name, res in reg_results.items():
            models_dict[name] = res["model"]
            oos_metrics[name] = {
                "r2": res["oos_r2"],
                "mae": res["oos_mae"],
                "max_importance": res["max_importance"],
            }

        primary = clf_results.get("clf_20pct_30d", {})
        legacy_models = primary.get("models", [])
        legacy_calibrator = primary.get("calibrator")

        # ─── Holdout-derived decile thresholds + time-to-touch CDFs ───
        missing_holdout = [k for k in CLF_TARGETS if k not in holdout_models]
        if missing_holdout:
            raise RuntimeError(
                f"Holdout models missing for {missing_holdout} — the v4 artifact "
                "requires holdout-derived decile thresholds and touch CDFs; "
                "cannot proceed."
            )
        decile_table, touch_cdf, holdout_n, holdout_range = compute_holdout_decile_table(
            df, holdout_models, holdout_calibrators, features, medians, OOS_CUTOFF,
            deploy_models=models_dict, deploy_calibrators=calibrators_dict,
        )

        # Cheap parquet fingerprint: sha256 of the first 1 MB + row count
        sha = hashlib.sha256()
        with open(self.data_path, "rb") as fh:
            sha.update(fh.read(1024 * 1024))
        sha.update(str(len(df)).encode("utf-8"))
        data_sha = sha.hexdigest()

        trained_at = datetime.utcnow().isoformat()
        train_period = f"{df['scan_date'].min()} → {df['scan_date'].max()}"

        # Self-describing v4 metadata — also mirrored to a JSON sidecar so the
        # calibration tracker / frontend read thresholds, baselines and CDFs
        # WITHOUT unpickling sklearn objects.
        meta_v4 = {
            "version": "v4.0",
            "features": features,
            "n_features": len(features),
            "oos_cutoff": OOS_CUTOFF,
            "purge_calendar_days": PURGE_CAL_DAYS,
            "purge_trading_bars": PURGE_TRADING_BARS,
            "horizon_convention": HORIZON_CONVENTION,
            "decile_table": decile_table,
            "touch_cdf": touch_cdf,
            "holdout_n": holdout_n,
            "holdout_range": holdout_range,
            "trained_at": trained_at,
            "train_period": train_period,
            "train_samples": len(df),
            "data_sha": data_sha,
        }

        payload = {
            "models_v3": models_dict,
            "calibrators_v3": calibrators_dict,
            "oos_metrics": oos_metrics,

            "models_holdout_v3": holdout_models,
            "calibrators_holdout_v3": holdout_calibrators,
            "oos_cutoff": OOS_CUTOFF,

            "models": legacy_models,
            "calibrator": legacy_calibrator,
            "features": features,
            "medians": medians,

            "version": "v4.0",
            "meta_v4": meta_v4,
            "targets_v3": {
                name: CLF_TARGETS.get(name, REG_TARGETS.get(name, ""))
                for name in list(CLF_TARGETS.keys()) + list(REG_TARGETS.keys())
            },
            "oos_auc": primary.get("oos_auc", 0.0),
            "oos_brier": primary.get("oos_brier", 0.0),
            "train_samples": len(df),
            "train_period": train_period,
            "theta_universe_size": df["symbol"].nunique(),
            "trained_at": trained_at,
        }

        # Backup old pickle if it exists
        if os.path.exists(self.output_path):
            backup_path = self.output_path + ".bak"
            os.replace(self.output_path, backup_path)
            log.info(f"Backed up existing pickle to: {backup_path}")

        joblib.dump(payload, self.output_path)
        log.info(f"\nSaved time model to: {self.output_path} ({os.path.getsize(self.output_path) / 1e6:.1f} MB)")

        # JSON sidecar next to the pickle, name derived from the output path
        # (a .staging output yields a .staging sidecar — never the final name)
        meta_path = meta_sidecar_path(self.output_path)
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta_v4, fh, indent=2, cls=_NumpyEncoder)
        log.info(f"Saved v4 metadata sidecar to: {meta_path}")

        log.info("\n" + "=" * 70)
        log.info("  TRAINING SUMMARY")
        log.info("=" * 70)
        for name, m in oos_metrics.items():
            if "auc" in m:
                log.info(f"  {name:20s}: AUC={m['auc']:.4f}, Disjoint AUC={m['disjoint_auc']:.4f}, CalAUC={m['cal_auc']:.4f}")
            else:
                log.info(f"  {name:20s}: R²={m['r2']:.4f}, MAE={m['mae']:.2f}%")
        log.info("=" * 70)

        return self.output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Time Model Trainer (v4)")
    parser.add_argument("--data", default="time_model_training_data.parquet")
    parser.add_argument("--output", default="time_model_v4.pkl")
    parser.add_argument("--all-features", action="store_true",
                        help="A/B fallback: sweep parquet f_*/opt_* columns instead of the v4 keep-list")
    args = parser.parse_args()

    trainer = TimeModelTrainer(data_path=args.data, output_path=args.output,
                               all_features=args.all_features)
    trainer.train()
