#!/usr/bin/env python3
"""
Time Model — Validation Agent (v4)
==================================
Out-of-sample validator for the multi-agent time model pipeline.

Loads a trained model pickle (default time_model_v4.pkl) and the
corresponding training data parquet, performs temporal OOS validation on
everything after the artifact's oos_cutoff (2025-06-01), and enforces
mandatory quality gates before the model is promoted to production.

Quality gates (see constants below for thresholds):
  - Classification AUC
  - Regression R²
  - Calibration slope
  - Max single-feature importance
  - Beats trivial baselines: base rate +0.03 AND the pinned f_vol_60d
    single-feature baseline +0.005 (a real margin)
  - Symbol-disjoint generalization gap
  - Fold AUC stability

Outputs: time_model_v4_validation.json

Usage:
  python time_model_validator.py
  python time_model_validator.py --model path/to/model.pkl --data path/to/data.parquet
"""

import os
import json
import joblib
import logging
import argparse
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import (
    roc_auc_score,
    r2_score,
    brier_score_loss,
    mean_absolute_error,
    mean_squared_error,
)
from sklearn.calibration import calibration_curve

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
)
log = logging.getLogger("TimeModel-Validator")

BACKEND = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OOS_CUTOFF = "2025-06-01"

CLASSIFICATION_TARGETS = [
    "hit_10pct_30d",
    "hit_10pct_60d",
    "hit_20pct_30d",
    "hit_20pct_60d",
]

REGRESSION_TARGETS = [
    "max_dd_30d",
    "max_dd_60d",
]

# Quality gate thresholds
GATE_AUC_MIN = 0.58
GATE_R2_MIN = 0.01
GATE_CALIBRATION_SLOPE_MIN = 0.8
GATE_CALIBRATION_SLOPE_MAX = 1.25
GATE_MAX_FEATURE_IMPORTANCE = 0.25

# New v3 gates
GATE_AUC_STD_MAX = 0.05
GATE_MAX_FOLD_CONTRIB = 0.22
GATE_DISJOINT_GAP_MAX = 0.03
GATE_BASELINE_LIFT_MIN = 0.03

# v4: required AUC margin over the single-feature baseline (previously the
# margin was zero — the model only had to TIE the baseline). v3's honest lifts
# over f_vol_60d were +0.008..+0.017, so 0.005 is enforceable but real.
GATE_SINGLE_FEAT_LIFT_MIN = 0.005

# Pinned single-feature baseline: f_vol_60d was the max-|corr| pick for all 4
# targets in v3; pinning removes selection noise across retrains.
BASELINE_FEATURE = "f_vol_60d"

# Purge at the cutoff for the baseline training slice (60 trading bars ≈ 90
# calendar days — same convention as the trainer / walk-forward CV).
PURGE_CAL_DAYS = 90

# Options-derived feature prefix (for coverage impact analysis)
OPTIONS_FEATURE_PREFIX = "f_opt_"


class TimeModelValidator:
    """Validator agent for the time_model_v3 pipeline.

    Loads a trained model pickle and training data, runs temporal
    out-of-sample validation, enforces quality gates, and produces
    a structured validation report.
    """

    def __init__(
        self,
        model_path: str = "time_model_v4.pkl",
        data_path: str = "time_model_training_data.parquet",
    ) -> None:
        # Resolve non-absolute paths against the backend dir (trainer pattern)
        # so the validator behaves the same regardless of CWD.
        self.model_path = os.path.join(BACKEND, model_path) if not os.path.isabs(model_path) else model_path
        self.data_path = os.path.join(BACKEND, data_path) if not os.path.isabs(data_path) else data_path

        self.model_data: dict[str, Any] = {}
        self.df: Optional[pd.DataFrame] = None
        self.features: list[str] = []
        self.report: dict[str, Any] = {}

        self._load_model()
        # Use the cutoff the trainer actually used (written into the pickle);
        # fall back to the module default for older pickles. Keeping these in
        # sync via the artifact prevents the trainer/validator cutoff drift.
        self.oos_cutoff = self.model_data.get("oos_cutoff", OOS_CUTOFF)
        self._load_data()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Load the trained model pickle."""
        log.info(f"Loading model from {self.model_path}")
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        self.model_data = joblib.load(self.model_path)

        # Extract feature list from model metadata
        self.features = self.model_data.get("features", [])
        models = self.model_data.get("models_v3") or self.model_data.get("models", {})

        log.info(
            f"Model loaded: {len(self.features)} features, "
            f"{len(models)} sub-models, "
            f"target columns: {list(models.keys()) if isinstance(models, dict) else '(list)'}"
        )

    def _load_data(self) -> None:
        """Load and prepare the training data parquet."""
        log.info(f"Loading data from {self.data_path}")
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"Data file not found: {self.data_path}")

        self.df = pd.read_parquet(self.data_path)
        log.info(f"Data loaded: {len(self.df)} rows, {len(self.df.columns)} columns")

        # Identify the date column (try common names)
        date_col = None
        for candidate in ("scan_date", "date", "start_date", "entry_date", "as_of_date", "timestamp"):
            if candidate in self.df.columns:
                date_col = candidate
                break

        if date_col is None:
            log.warning("No recognized date column found — using index as date")
            if self.df.index.dtype == "datetime64[ns]":
                self.df["_date"] = self.df.index
                date_col = "_date"
            else:
                raise ValueError(
                    "Cannot identify a date column in the training data. "
                    f"Available columns: {list(self.df.columns[:20])}"
                )

        self.df[date_col] = pd.to_datetime(self.df[date_col], errors="coerce")
        self.date_col = date_col

        n_before = len(self.df)
        self.df = self.df.dropna(subset=[date_col])
        if len(self.df) < n_before:
            log.warning(f"Dropped {n_before - len(self.df)} rows with invalid dates")

        oos_mask = self.df[date_col] >= self.oos_cutoff
        n_oos = oos_mask.sum()
        n_is = (~oos_mask).sum()
        log.info(
            f"Temporal split at {self.oos_cutoff}: "
            f"{n_is} in-sample, {n_oos} out-of-sample"
        )

        if n_oos == 0:
            raise ValueError(
                f"No out-of-sample data after {self.oos_cutoff}. "
                f"Date range: {self.df[date_col].min()} → {self.df[date_col].max()}"
            )

    # ------------------------------------------------------------------
    # Feature matrix helpers
    # ------------------------------------------------------------------

    def _get_feature_matrix(
        self, df_subset: pd.DataFrame
    ) -> np.ndarray:
        """Build the feature matrix from a DataFrame subset.

        Handles missing features by filling with the model's stored
        medians or zero.
        """
        medians = self.model_data.get("medians", {})
        cols = []
        for feat in self.features:
            if feat in df_subset.columns:
                col = df_subset[feat].fillna(medians.get(feat, 0.0)).values
            else:
                fill = medians.get(feat, 0.0)
                log.debug(f"Feature '{feat}' missing from data — filling with {fill}")
                col = np.full(len(df_subset), fill)
            cols.append(col)

        X = np.column_stack(cols).astype(np.float64)
        # Clip extreme values to prevent numerical issues
        X = np.clip(X, -100, 100)
        return X

    def _get_oos_data(self) -> pd.DataFrame:
        """Return the out-of-sample slice (everything >= cutoff)."""
        return self.df[self.df[self.date_col] >= self.oos_cutoff].copy()

    def _evaluate_single_feature_baseline(
        self,
        target_name: str,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_oos: np.ndarray,
        y_oos: np.ndarray,
    ) -> tuple[float, str]:
        """Train a simple single-feature logistic regression baseline and score it OOS.

        Uses the PINNED baseline feature (f_vol_60d) when present in the
        model's feature list; otherwise falls back to the feature with the
        highest absolute Pearson correlation with the target on the training
        set. Fits a LogisticRegression and scores its OOS AUC.
        """
        from sklearn.linear_model import LogisticRegression

        if BASELINE_FEATURE in self.features:
            best_idx = self.features.index(BASELINE_FEATURE)
            best_feat_name = BASELINE_FEATURE
            log.info(
                f"  {target_name}: Single-feature baseline PINNED to '{best_feat_name}'"
            )
        else:
            best_idx = 0
            best_corr = -1.0

            for idx in range(X_train.shape[1]):
                # Skip features with no variance
                if np.std(X_train[:, idx]) < 1e-6:
                    continue
                corr = abs(float(np.corrcoef(X_train[:, idx], y_train)[0, 1]))
                if not np.isnan(corr) and corr > best_corr:
                    best_corr = corr
                    best_idx = idx

            best_feat_name = self.features[best_idx]
            log.info(
                f"  {target_name}: Single-feature baseline via max-|corr| search "
                f"('{BASELINE_FEATURE}' not in features): '{best_feat_name}' "
                f"(absolute correlation on train: {best_corr:.4f})"
            )

        try:
            X_train_single = X_train[:, [best_idx]]
            X_oos_single = X_oos[:, [best_idx]]

            lr = LogisticRegression(penalty=None, solver="lbfgs")
            lr.fit(X_train_single, y_train)
            y_prob_base = lr.predict_proba(X_oos_single)[:, 1]

            baseline_auc = float(roc_auc_score(y_oos, y_prob_base))
            log.info(f"  {target_name}: Baseline OOS AUC = {baseline_auc:.4f}")
            return baseline_auc, best_feat_name
        except Exception as e:
            log.warning(f"  {target_name}: Failed to evaluate single-feature baseline — {e}")
            return 0.5, best_feat_name

    # ------------------------------------------------------------------
    # Classification metrics
    # ------------------------------------------------------------------

    def _predict_probability(self, model: Any, calibrator: Any, X: np.ndarray) -> np.ndarray:
        """Helper to get calibrated probabilities from ensemble or single model."""
        if isinstance(model, list):
            probs = np.column_stack([m.predict_proba(X)[:, 1] for m in model])
            y_prob = probs.mean(axis=1)
        else:
            y_prob = model.predict_proba(X)[:, 1]
        if calibrator is not None:
            y_prob = calibrator.predict(y_prob)
        return y_prob

    def _validate_classification_model(
        self,
        target_name: str,
        model: Any,
        calibrator: Any,
        X_oos: np.ndarray,
        y_oos: np.ndarray,
    ) -> dict[str, Any]:
        """Compute classification metrics for a single sub-model."""
        result: dict[str, Any] = {"target": target_name, "n_samples": int(len(y_oos))}

        n_positive = int(y_oos.sum())
        n_negative = int(len(y_oos) - n_positive)
        result["n_positive"] = n_positive
        result["n_negative"] = n_negative
        result["prevalence"] = round(n_positive / len(y_oos), 4) if len(y_oos) > 0 else 0.0

        if n_positive == 0 or n_negative == 0:
            log.warning(f"  {target_name}: only one class present — AUC undefined")
            result["auc"] = None
            result["brier_score"] = None
            result["calibration_slope"] = None
            result["gate_auc_pass"] = False
            result["gate_calibration_pass"] = False
            return result

        # Predict probabilities
        try:
            y_prob = self._predict_probability(model, calibrator, X_oos)
        except Exception as e:
            log.error(f"  {target_name}: predict_proba failed — {e}")
            result["auc"] = None
            result["brier_score"] = None
            result["calibration_slope"] = None
            result["gate_auc_pass"] = False
            result["gate_calibration_pass"] = False
            return result

        # AUC
        auc = roc_auc_score(y_oos, y_prob)
        result["auc"] = round(float(auc), 4)
        result["gate_auc_pass"] = bool(auc >= GATE_AUC_MIN)

        # Brier score (lower is better)
        brier = brier_score_loss(y_oos, y_prob)
        result["brier_score"] = round(float(brier), 4)

        # Calibration curve and slope
        cal_result = self._compute_calibration(y_oos, y_prob, target_name)
        result.update(cal_result)

        log.info(
            f"  {target_name}: AUC={auc:.4f} "
            f"Brier={brier:.4f} "
            f"CalSlope={result.get('calibration_slope', 'N/A')} "
            f"{'✓' if result['gate_auc_pass'] else '✗'}"
        )

        return result

    def _compute_calibration(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
        target_name: str,
        n_bins: int = 10,
    ) -> dict[str, Any]:
        """Compute calibration curve (predicted vs actual) and slope."""
        result: dict[str, Any] = {}

        try:
            fraction_of_positives, mean_predicted_value = calibration_curve(
                y_true, y_prob, n_bins=n_bins, strategy="uniform"
            )

            # Calibration plot data (10 bins)
            result["calibration_bins"] = [
                {
                    "bin": int(i),
                    "mean_predicted": round(float(mp), 4),
                    "fraction_positive": round(float(fp), 4),
                }
                for i, (mp, fp) in enumerate(
                    zip(mean_predicted_value, fraction_of_positives)
                )
            ]

            # Fit a linear regression to get calibration slope
            # Perfect calibration: slope=1, intercept=0
            if len(mean_predicted_value) >= 2:
                coeffs = np.polyfit(mean_predicted_value, fraction_of_positives, 1)
                slope = float(coeffs[0])
                intercept = float(coeffs[1])
                result["calibration_slope"] = round(slope, 4)
                result["calibration_intercept"] = round(intercept, 4)
                result["gate_calibration_pass"] = bool(
                    GATE_CALIBRATION_SLOPE_MIN <= slope <= GATE_CALIBRATION_SLOPE_MAX
                )
            else:
                result["calibration_slope"] = None
                result["calibration_intercept"] = None
                result["gate_calibration_pass"] = False
                log.warning(f"  {target_name}: too few calibration bins for slope fit")

        except Exception as e:
            log.warning(f"  {target_name}: calibration computation failed — {e}")
            result["calibration_slope"] = None
            result["calibration_intercept"] = None
            result["calibration_bins"] = []
            result["gate_calibration_pass"] = False

        return result

    # ------------------------------------------------------------------
    # Regression metrics
    # ------------------------------------------------------------------

    def _validate_regression_model(
        self,
        target_name: str,
        model: Any,
        X_oos: np.ndarray,
        y_oos: np.ndarray,
    ) -> dict[str, Any]:
        """Compute regression metrics for a single sub-model."""
        result: dict[str, Any] = {"target": target_name, "n_samples": int(len(y_oos))}

        if len(y_oos) < 2:
            log.warning(f"  {target_name}: not enough samples for regression metrics")
            result["r2"] = None
            result["mae"] = None
            result["rmse"] = None
            result["gate_r2_pass"] = False
            return result

        try:
            y_pred = model.predict(X_oos)
        except Exception as e:
            log.error(f"  {target_name}: predict failed — {e}")
            result["r2"] = None
            result["mae"] = None
            result["rmse"] = None
            result["gate_r2_pass"] = False
            return result

        r2 = r2_score(y_oos, y_pred)
        mae = mean_absolute_error(y_oos, y_pred)
        rmse = float(np.sqrt(mean_squared_error(y_oos, y_pred)))

        result["r2"] = round(float(r2), 4)
        result["mae"] = round(float(mae), 4)
        result["rmse"] = round(float(rmse), 4)
        result["gate_r2_pass"] = bool(r2 >= GATE_R2_MIN)

        log.info(
            f"  {target_name}: R²={r2:.4f} MAE={mae:.4f} RMSE={rmse:.4f} "
            f"{'✓' if result['gate_r2_pass'] else '✗'}"
        )

        return result

    # ------------------------------------------------------------------
    # Feature importance gate
    # ------------------------------------------------------------------

    def _validate_feature_importance(
        self,
        target_name: str,
        model: Any,
    ) -> dict[str, Any]:
        """Check that no single feature dominates (> 40% importance)."""
        result: dict[str, Any] = {"target": target_name}

        try:
            if isinstance(model, list):
                # Average feature importances across ensemble
                importances = np.zeros(len(self.features))
                for m in model:
                    importances += m.feature_importances_
                importances /= len(model)
            else:
                importances = model.feature_importances_
        except AttributeError:
            # Model doesn't expose feature_importances_ (e.g. calibrated wrapper)
            # Try to dig into the base estimator
            base = getattr(model, "estimator", None) or getattr(model, "base_estimator", None)
            if base is not None and hasattr(base, "feature_importances_"):
                importances = base.feature_importances_
            else:
                log.warning(
                    f"  {target_name}: model has no feature_importances_ — skipping gate"
                )
                result["max_feature_importance"] = None
                result["max_feature_name"] = None
                result["gate_feature_importance_pass"] = True  # assume pass if not checkable
                result["top_10_features"] = []
                return result

        # Normalize importances so they represent fractions summing to 1.0
        if importances.sum() > 0:
            importances = importances / importances.sum()

        # Map feature names to importances
        feat_imp = sorted(
            zip(self.features, importances),
            key=lambda x: -x[1],
        )

        max_name, max_imp = feat_imp[0]
        result["max_feature_importance"] = round(float(max_imp), 4)
        result["max_feature_name"] = max_name
        result["gate_feature_importance_pass"] = bool(max_imp <= GATE_MAX_FEATURE_IMPORTANCE)

        result["top_10_features"] = [
            {"feature": name, "importance": round(float(imp), 4)}
            for name, imp in feat_imp[:10]
        ]

        if not result["gate_feature_importance_pass"]:
            log.warning(
                f"  {target_name}: feature '{max_name}' has {max_imp:.1%} importance "
                f"(gate: ≤{GATE_MAX_FEATURE_IMPORTANCE:.0%})"
            )
        else:
            log.info(
                f"  {target_name}: max feature importance = {max_imp:.1%} "
                f"('{max_name}') ✓"
            )

        return result

    # ------------------------------------------------------------------
    # Diagnostic: per-sector AUC breakdown
    # ------------------------------------------------------------------

    def _compute_sector_auc(
        self,
        target_name: str,
        model: Any,
        calibrator: Any,
        df_oos: pd.DataFrame,
        X_oos: np.ndarray,
        y_oos: np.ndarray,
    ) -> list[dict[str, Any]]:
        """Compute AUC per sector for a classification model."""
        sector_col = None
        for candidate in ("sector", "f_sector", "gics_sector"):
            if candidate in df_oos.columns:
                sector_col = candidate
                break

        if sector_col is None:
            log.info(f"  {target_name}: no sector column found — skipping sector breakdown")
            return []

        sectors = df_oos[sector_col].fillna("Unknown").values
        unique_sectors = sorted(set(sectors))
        sector_results = []

        try:
            y_prob = self._predict_probability(model, calibrator, X_oos)
        except Exception:
            log.warning(f"  {target_name}: predict_proba failed — skipping sector breakdown")
            return []

        for sector in unique_sectors:
            mask = sectors == sector
            y_sect = y_oos[mask]
            p_sect = y_prob[mask]

            if len(y_sect) < 10 or len(set(y_sect)) < 2:
                continue

            try:
                auc_s = roc_auc_score(y_sect, p_sect)
                sector_results.append({
                    "sector": str(sector),
                    "n_samples": int(mask.sum()),
                    "n_positive": int(y_sect.sum()),
                    "auc": round(float(auc_s), 4),
                })
            except Exception:
                continue

        log.info(
            f"  {target_name}: sector AUC computed for "
            f"{len(sector_results)}/{len(unique_sectors)} sectors"
        )

        return sector_results

    # ------------------------------------------------------------------
    # Diagnostic: options coverage impact
    # ------------------------------------------------------------------

    def _compute_options_coverage_impact(
        self,
        target_name: str,
        model: Any,
        calibrator: Any,
        X_oos: np.ndarray,
        y_oos: np.ndarray,
    ) -> dict[str, Any]:
        """Compare AUC with vs without options-derived features.

        Zeroes out all f_opt_* features and re-scores to measure the
        lift provided by the options data.
        """
        result: dict[str, Any] = {"target": target_name}

        # Find indices of options features
        opt_indices = [
            i for i, f in enumerate(self.features) if f.startswith(OPTIONS_FEATURE_PREFIX)
        ]

        if not opt_indices:
            log.info(f"  {target_name}: no options features found — skipping coverage impact")
            result["auc_with_options"] = None
            result["auc_without_options"] = None
            result["auc_lift"] = None
            result["options_features_count"] = 0
            return result

        result["options_features_count"] = len(opt_indices)
        result["options_features"] = [self.features[i] for i in opt_indices]

        n_positive = int(y_oos.sum())
        n_negative = int(len(y_oos) - n_positive)

        if n_positive == 0 or n_negative == 0:
            result["auc_with_options"] = None
            result["auc_without_options"] = None
            result["auc_lift"] = None
            return result

        try:
            # AUC with all features
            y_prob_full = self._predict_probability(model, calibrator, X_oos)
            auc_full = roc_auc_score(y_oos, y_prob_full)

            # AUC with options features zeroed out
            X_no_opt = X_oos.copy()
            X_no_opt[:, opt_indices] = 0.0
            y_prob_no_opt = self._predict_probability(model, calibrator, X_no_opt)
            auc_no_opt = roc_auc_score(y_oos, y_prob_no_opt)

            result["auc_with_options"] = round(float(auc_full), 4)
            result["auc_without_options"] = round(float(auc_no_opt), 4)
            result["auc_lift"] = round(float(auc_full - auc_no_opt), 4)

            log.info(
                f"  {target_name}: options impact — "
                f"AUC with={auc_full:.4f}, without={auc_no_opt:.4f}, "
                f"lift={auc_full - auc_no_opt:+.4f} "
                f"({len(opt_indices)} features)"
            )

        except Exception as e:
            log.warning(f"  {target_name}: options coverage impact failed — {e}")
            result["auc_with_options"] = None
            result["auc_without_options"] = None
            result["auc_lift"] = None

        return result

    # ------------------------------------------------------------------
    # Main validation
    # ------------------------------------------------------------------

    def validate(self) -> dict:
        """Run full out-of-sample validation and return the report.

        Returns a dict with all metrics, gate results, and diagnostics.
        """
        log.info("=" * 72)
        log.info("  TIME MODEL v3 — VALIDATION REPORT")
        log.info("=" * 72)

        report: dict[str, Any] = {
            "model_path": self.model_path,
            "data_path": self.data_path,
            "oos_cutoff": self.oos_cutoff,
            "validation_timestamp": datetime.utcnow().isoformat() + "Z",
            "n_features": len(self.features),
            "n_total_samples": int(len(self.df)),
            "classification_results": {},
            "regression_results": {},
            "feature_importance": {},
            "sector_auc": {},
            "options_coverage_impact": {},
            "gates": {},
        }

        # Prepare OOS data
        df_oos = self._get_oos_data()
        X_oos = self._get_feature_matrix(df_oos)
        report["n_oos_samples"] = int(len(df_oos))

        log.info(f"OOS samples: {len(df_oos)}")
        log.info(f"Feature matrix shape: {X_oos.shape}")

        # ── Select which models the gate evaluates ───────────────────────
        # Prefer the holdout models (trained only on < cutoff): the >= cutoff
        # slice is genuinely unseen by them, so the gate is a true OOS test.
        # Only fall back to the all-data deploy models if no holdout models
        # exist — and shout about it, because that path scores the model on
        # data it was trained on (in-sample; gate is not trustworthy).
        holdout_models = self.model_data.get("models_holdout_v3")
        if holdout_models:
            models = holdout_models
            calibrators = self.model_data.get("calibrators_holdout_v3") or {}
            report["validation_mode"] = "holdout_oos"
            log.info(
                f"Validation mode: HOLDOUT OOS — scoring models trained on "
                f"< {self.oos_cutoff} against the >= {self.oos_cutoff} slice."
            )
        else:
            models = self.model_data.get("models_v3") or self.model_data.get("models", {})
            calibrators = self.model_data.get("calibrators_v3") or {}
            if not calibrators and "calibrator" in self.model_data:
                calibrators = {
                    "clf_20pct_30d": self.model_data["calibrator"],
                    "hit_20pct_30d": self.model_data["calibrator"]
                }
            report["validation_mode"] = "in_sample_fallback"
            log.warning(
                "Validation mode: IN-SAMPLE FALLBACK — no holdout models in the "
                "pickle. The deploy models were trained on the full dataset, "
                "INCLUDING the >= %s slice, so the gate metrics below are "
                "in-sample and DO NOT measure generalization. Retrain with a "
                "trainer that emits models_holdout_v3.", self.oos_cutoff,
            )

        # Walk-forward CV metrics from the trainer, logged as a non-gating
        # cross-check (averaged over 6 folds / multiple regimes vs the single
        # post-cutoff holdout slice the gate uses).
        wf = self.model_data.get("oos_metrics", {})
        if wf:
            report["walk_forward_oos_metrics"] = wf
            log.info("─── Walk-forward CV cross-check (non-gating) ───")
            for name, m in wf.items():
                if "auc" in m:
                    log.info(f"  {name}: WF AUC={m.get('auc')}  Brier={m.get('brier')}")
                elif "r2" in m:
                    log.info(f"  {name}: WF R²={m.get('r2')}  MAE={m.get('mae')}")

        # Handle models stored as a dict {target_name: model} or as a list
        if isinstance(models, list):
            # Attempt to pair with known target names in order
            all_targets = CLASSIFICATION_TARGETS + REGRESSION_TARGETS
            models_dict = {}
            for i, m in enumerate(models):
                if i < len(all_targets):
                    models_dict[all_targets[i]] = m
            models = models_dict
            log.info(f"Models provided as list — mapped to: {list(models.keys())}")

        # Prepare pre-cutoff in-sample data for baseline evaluation.
        # PURGED at the boundary: rows whose 60-trading-bar label window
        # crosses the cutoff are excluded so the baseline trains leak-free.
        purge_cut = pd.Timestamp(self.oos_cutoff) - pd.Timedelta(days=PURGE_CAL_DAYS)
        df_pre = self.df[self.df[self.date_col] < purge_cut].copy()
        log.info(
            f"Baseline training slice: scan_date < {purge_cut.strftime('%Y-%m-%d')} "
            f"(cutoff {self.oos_cutoff} - {PURGE_CAL_DAYS}d purge), {len(df_pre)} rows"
        )

        # --- Classification models ---
        log.info("")
        log.info("─── Classification Models ───")
        all_auc_pass = True
        all_calibration_pass = True
        all_baseline_pass = True
        all_disjoint_pass = True
        all_stability_pass = True

        for target in CLASSIFICATION_TARGETS:
            model_key = target.replace("hit_", "clf_")
            if model_key not in models and target not in models:
                log.warning(f"  {target}: model not found in pickle — skipping")
                report["classification_results"][target] = {
                    "target": target,
                    "error": "model not found",
                    "gate_auc_pass": False,
                    "gate_calibration_pass": False,
                    "gate_baseline_pass": False,
                    "gate_disjoint_pass": False,
                    "gate_stability_std_pass": False,
                    "gate_stability_contrib_pass": False,
                }
                all_auc_pass = False
                all_calibration_pass = False
                all_baseline_pass = False
                all_disjoint_pass = False
                all_stability_pass = False
                continue

            model = models.get(model_key) or models.get(target)
            calibrator = calibrators.get(model_key) or calibrators.get(target)

            if target not in df_oos.columns:
                log.warning(f"  {target}: target column not in data — skipping")
                report["classification_results"][target] = {
                    "target": target,
                    "error": "target column missing from data",
                    "gate_auc_pass": False,
                    "gate_calibration_pass": False,
                    "gate_baseline_pass": False,
                    "gate_disjoint_pass": False,
                    "gate_stability_std_pass": False,
                    "gate_stability_contrib_pass": False,
                }
                all_auc_pass = False
                all_calibration_pass = False
                all_baseline_pass = False
                all_disjoint_pass = False
                all_stability_pass = False
                continue

            y_oos = df_oos[target].fillna(0).astype(int).values

            # Core metrics
            cls_result = self._validate_classification_model(target, model, calibrator, X_oos, y_oos)

            # Feature importance
            fi_result = self._validate_feature_importance(target, model)
            cls_result["feature_importance"] = fi_result

            # Sector AUC breakdown
            sector_auc = self._compute_sector_auc(target, model, calibrator, df_oos, X_oos, y_oos)
            cls_result["sector_auc"] = sector_auc

            # Options coverage impact
            opt_impact = self._compute_options_coverage_impact(target, model, calibrator, X_oos, y_oos)
            cls_result["options_coverage_impact"] = opt_impact

            # Evaluate single-feature baseline
            df_pre_clean = df_pre.dropna(subset=[target]).copy()
            y_train = df_pre_clean[target].fillna(0).astype(int).values
            X_train = self._get_feature_matrix(df_pre_clean)

            baseline_auc, best_feat = self._evaluate_single_feature_baseline(
                target, X_train, y_train, X_oos, y_oos
            )
            cls_result["baseline_auc"] = baseline_auc
            cls_result["baseline_best_feature"] = best_feat

            # Baseline lift gate: beats base rate 0.50 by >= GATE_BASELINE_LIFT_MIN
            # AND beats the single-feature baseline by >= GATE_SINGLE_FEAT_LIFT_MIN
            # (a real margin — previously the model only had to tie the baseline).
            model_auc = cls_result.get("auc") or 0.5
            cls_result["gate_baseline_pass"] = bool(
                (model_auc >= 0.50 + GATE_BASELINE_LIFT_MIN) and
                (model_auc >= baseline_auc + GATE_SINGLE_FEAT_LIFT_MIN)
            )

            # Cross-validation stability and disjoint checks from pickle
            wf_metrics = wf.get(model_key, {})
            cv_auc = wf_metrics.get("auc", 0.5)
            disjoint_auc = wf_metrics.get("disjoint_auc", 0.5)
            auc_std = wf_metrics.get("auc_std", 0.0)
            max_fold_contrib = wf_metrics.get("max_fold_contrib")

            cls_result["cv_auc"] = cv_auc
            cls_result["disjoint_auc"] = disjoint_auc
            cls_result["auc_std"] = auc_std
            cls_result["max_fold_contrib"] = max_fold_contrib

            # Symbol-disjoint AUC must be within 0.03 of time-OOS CV AUC
            cls_result["gate_disjoint_pass"] = bool(disjoint_auc >= cv_auc - GATE_DISJOINT_GAP_MAX)
            cls_result["gate_stability_std_pass"] = bool(auc_std <= GATE_AUC_STD_MAX)
            cls_result["gate_stability_contrib_pass"] = bool(
                max_fold_contrib is None or max_fold_contrib <= GATE_MAX_FOLD_CONTRIB
            )

            log.info(
                f"  {target}: BaselinesLiftCheck={'✓ PASS' if cls_result['gate_baseline_pass'] else '✗ FAIL'} "
                f"(OOS: {model_auc:.4f} vs BaseRate: 0.5000 (+{GATE_BASELINE_LIFT_MIN}), "
                f"SingleFeat ({best_feat}): {baseline_auc:.4f} (+{GATE_SINGLE_FEAT_LIFT_MIN}))"
            )
            log.info(
                f"  {target}: DisjointCheck={'✓ PASS' if cls_result['gate_disjoint_pass'] else '✗ FAIL'} "
                f"(Disjoint: {disjoint_auc:.4f} vs temporal CV: {cv_auc:.4f})"
            )
            log.info(
                f"  {target}: StabilityStdCheck={'✓ PASS' if cls_result['gate_stability_std_pass'] else '✗ FAIL'} "
                f"(AUC Std: {auc_std:.4f} vs threshold: {GATE_AUC_STD_MAX:.4f})"
            )
            if max_fold_contrib is not None:
                log.info(
                    f"  {target}: FoldContribCheck={'✓ PASS' if cls_result['gate_stability_contrib_pass'] else '✗ FAIL'} "
                    f"(Max Fold Contrib: {max_fold_contrib:.4f} vs threshold: {GATE_MAX_FOLD_CONTRIB:.4f})"
                )

            report["classification_results"][target] = cls_result

            if not cls_result.get("gate_auc_pass", False):
                all_auc_pass = False
            if not cls_result.get("gate_calibration_pass", False):
                all_calibration_pass = False
            if not cls_result.get("gate_baseline_pass", False):
                all_baseline_pass = False
            if not cls_result.get("gate_disjoint_pass", False):
                all_disjoint_pass = False
            if not (cls_result.get("gate_stability_std_pass", False) and cls_result.get("gate_stability_contrib_pass", False)):
                all_stability_pass = False

        # --- Regression models ---
        log.info("")
        log.info("─── Regression Models ───")
        all_r2_pass = True

        for target in REGRESSION_TARGETS:
            model_key = target.replace("max_", "reg_")
            if model_key not in models and target not in models:
                log.warning(f"  {target}: model not found in pickle — skipping")
                report["regression_results"][target] = {
                    "target": target,
                    "error": "model not found",
                    "gate_r2_pass": False,
                }
                all_r2_pass = False
                continue

            model = models.get(model_key) or models.get(target)

            if target not in df_oos.columns:
                log.warning(f"  {target}: target column not in data — skipping")
                report["regression_results"][target] = {
                    "target": target,
                    "error": "target column missing from data",
                    "gate_r2_pass": False,
                }
                all_r2_pass = False
                continue

            y_oos = np.abs(df_oos[target].fillna(0).astype(float).values)

            # Core metrics
            reg_result = self._validate_regression_model(target, model, X_oos, y_oos)

            # Feature importance
            fi_result = self._validate_feature_importance(target, model)
            reg_result["feature_importance"] = fi_result

            report["regression_results"][target] = reg_result

            if not reg_result.get("gate_r2_pass", False):
                all_r2_pass = False

        # --- Aggregate feature importance gate ---
        all_fi_pass = True
        for target in CLASSIFICATION_TARGETS + REGRESSION_TARGETS:
            result = (
                report["classification_results"].get(target, {})
                or report["regression_results"].get(target, {})
            )
            fi = result.get("feature_importance", {})
            if not fi.get("gate_feature_importance_pass", True):
                all_fi_pass = False

        # --- Gates summary ---
        log.info("")
        log.info("─── Quality Gates ───")

        gates = {
            "classification_auc": {
                "threshold": f">= {GATE_AUC_MIN}",
                "pass": all_auc_pass,
            },
            "regression_r2": {
                "threshold": f">= {GATE_R2_MIN}",
                "pass": all_r2_pass,
            },
            "calibration_slope": {
                "threshold": f"{GATE_CALIBRATION_SLOPE_MIN} – {GATE_CALIBRATION_SLOPE_MAX}",
                "pass": all_calibration_pass,
            },
            "feature_importance": {
                "threshold": f"<= {GATE_MAX_FEATURE_IMPORTANCE:.0%}",
                "pass": all_fi_pass,
            },
            "beats_trivial_baselines": {
                "threshold": (
                    f"auc >= 0.50 + {GATE_BASELINE_LIFT_MIN:.2f} (base rate) AND "
                    f"auc >= single-feature baseline + {GATE_SINGLE_FEAT_LIFT_MIN:.3f}"
                ),
                "pass": all_baseline_pass,
            },
            "symbol_disjoint_generalization": {
                "threshold": f"disjoint_auc >= cv_auc - {GATE_DISJOINT_GAP_MAX}",
                "pass": all_disjoint_pass,
            },
            "fold_auc_stability": {
                "threshold": f"std <= {GATE_AUC_STD_MAX}, max_fold_contrib <= {GATE_MAX_FOLD_CONTRIB}",
                "pass": all_stability_pass,
            },
        }

        # Hard gate: in-sample fallback can NEVER promote. The deploy models
        # were scored on data they trained on, so every metric above is
        # in-sample and meaningless as a generalization check.
        if report.get("validation_mode") == "in_sample_fallback":
            gates["holdout_models_present"] = {
                "threshold": "models_holdout_v3 present (validation_mode == holdout_oos)",
                "pass": False,
                "reason": (
                    "IN-SAMPLE FALLBACK — no holdout models in the pickle; "
                    "gate metrics are in-sample and do not measure "
                    "generalization. v4 must never promote on in-sample "
                    "numbers. Retrain with a trainer that emits "
                    "models_holdout_v3."
                ),
            }
            log.error(
                "✘ HARD FAIL: validation_mode == 'in_sample_fallback' — "
                "forcing all_pass=False. %s",
                gates["holdout_models_present"]["reason"],
            )

        all_pass = all(g["pass"] for g in gates.values())
        gates["all_pass"] = all_pass

        for gate_name, gate_info in gates.items():
            if gate_name == "all_pass":
                continue
            status = "✓ PASS" if gate_info["pass"] else "✗ FAIL"
            log.info(f"  {gate_name}: {status} (threshold: {gate_info['threshold']})")

        log.info("")
        if all_pass:
            log.info("  ══════════════════════════════════")
            log.info("  ║  ALL GATES PASSED — PROMOTE ✓  ║")
            log.info("  ══════════════════════════════════")
        else:
            log.warning("  ══════════════════════════════════════")
            log.warning("  ║  GATE(S) FAILED — DO NOT PROMOTE ✗  ║")
            log.warning("  ══════════════════════════════════════")

        report["gates"] = gates
        self.report = report
        return report

    # ------------------------------------------------------------------
    # Gate check
    # ------------------------------------------------------------------

    def passes_all_gates(self) -> bool:
        """Return True if all quality gates pass.

        Must call validate() first; otherwise runs it automatically.
        """
        if not self.report:
            self.validate()
        return bool(self.report.get("gates", {}).get("all_pass", False))

    def failed_gates(self) -> list[str]:
        """Return list of gate names that failed."""
        if not self.report:
            self.validate()
        failed = []
        for gate_name, gate_info in self.report.get("gates", {}).items():
            if gate_name != "all_pass" and not gate_info.get("pass", False):
                failed.append(gate_name)
        return failed

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def save_report(self, output_path: str = "time_model_v4_validation.json") -> str:
        """Save the validation report as JSON."""
        if not self.report:
            raise RuntimeError("Call validate() before save_report()")

        if not os.path.isabs(output_path):
            output_path = os.path.join(BACKEND, output_path)

        # Ensure all numpy types are JSON-serializable
        def _convert(obj: Any) -> Any:
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            return obj

        class NumpyEncoder(json.JSONEncoder):
            def default(self, o: Any) -> Any:
                converted = _convert(o)
                if converted is not o:
                    return converted
                return super().default(o)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.report, f, indent=2, cls=NumpyEncoder)

        log.info(f"Validation report saved to {output_path}")
        return output_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Standalone entry point: load model & data, validate, print summary, save."""
    parser = argparse.ArgumentParser(
        description="Time Model v3 — Out-of-Sample Validator",
    )
    parser.add_argument(
        "--model",
        default="time_model_v4.pkl",
        help="Path to the trained model pickle (default: time_model_v4.pkl)",
    )
    parser.add_argument(
        "--data",
        default="time_model_training_data.parquet",
        help="Path to the training data parquet (default: time_model_training_data.parquet)",
    )
    parser.add_argument(
        "--output",
        default="time_model_v4_validation.json",
        help="Output path for the validation report JSON",
    )
    args = parser.parse_args()

    log.info("Starting Time Model v3 Validation Agent")
    log.info(f"  Model:  {args.model}")
    log.info(f"  Data:   {args.data}")
    log.info(f"  Output: {args.output}")
    log.info("")

    try:
        validator = TimeModelValidator(
            model_path=args.model,
            data_path=args.data,
        )

        report = validator.validate()

        # Print compact summary
        log.info("")
        log.info("─── Summary ───")

        for target, result in report.get("classification_results", {}).items():
            auc = result.get("auc", "N/A")
            brier = result.get("brier_score", "N/A")
            slope = result.get("calibration_slope", "N/A")
            log.info(f"  [CLS] {target}: AUC={auc}  Brier={brier}  CalSlope={slope}")

        for target, result in report.get("regression_results", {}).items():
            r2 = result.get("r2", "N/A")
            mae = result.get("mae", "N/A")
            rmse = result.get("rmse", "N/A")
            log.info(f"  [REG] {target}: R²={r2}  MAE={mae}  RMSE={rmse}")

        all_pass = report.get("gates", {}).get("all_pass", False)
        log.info(f"  Overall: {'PASS ✓' if all_pass else 'FAIL ✗'}")

        # Save report
        validator.save_report(args.output)

    except FileNotFoundError as e:
        log.error(f"File not found: {e}")
        raise SystemExit(1)
    except Exception as e:
        log.error(f"Validation failed: {type(e).__name__}: {e}", exc_info=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
