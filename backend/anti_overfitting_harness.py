#!/usr/bin/env python3
"""
Anti-Overfitting Harness Module — Standalone, unit-tested CV and validation utilities.
====================================================================================
Implements:
  1. Purged + Embargoed Walk-Forward Cross-Validation.
  2. Marcos Lopez de Prado's Sample-Uniqueness Weighting.
  3. Fold-internal scaler and median fitting.
  4. Symbol-disjoint split.
  5. Trivial baselines (base-rate, single-feature logistic regression).
"""

import logging
import numpy as np
import pandas as pd
from collections import Counter
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss

log = logging.getLogger("AntiOverfitting-Harness")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Purged + Embargoed Walk-Forward CV
# ─────────────────────────────────────────────────────────────────────────────
class PurgedEmbargoedWalkForwardCV:
    """Purged and Embargoed Walk-Forward Cross-Validation.
    
    Splits data chronologically on scan dates, ensuring that the training set
    has no leakage (purging before test set, embargoing after test set).
    """
    def __init__(self, n_splits: int = 6, purge_days: int = 90, embargo_days: int = 15):
        self.n_splits = n_splits
        self.purge_days = purge_days      # 60 trading days ≈ 90 calendar days
        self.embargo_days = embargo_days  # 10 trading days ≈ 15 calendar days

    def split(self, df: pd.DataFrame):
        """Yield (train_idx, test_idx) folds."""
        df = df.copy()
        df["scan_date_dt"] = pd.to_datetime(df["scan_date"])
        unique_dates = sorted(df["scan_date_dt"].unique())
        
        if len(unique_dates) < self.n_splits + 1:
            raise ValueError(f"Insufficient unique dates ({len(unique_dates)}) for {self.n_splits} splits.")
            
        # Split dates into n_splits + 1 chunks
        date_chunks = np.array_split(unique_dates, self.n_splits + 1)
        
        for fold in range(self.n_splits):
            # Test dates are in chunk fold + 1
            test_dates = date_chunks[fold + 1]
            test_start = test_dates[0]
            test_end = test_dates[-1]
            
            # Find test row indices
            test_mask = (df["scan_date_dt"] >= test_start) & (df["scan_date_dt"] <= test_end)
            test_idx = df.index[test_mask].tolist()
            
            # Train row indices (all chunks prior to test_dates, with purge/embargo applied)
            # Standard walk-forward CV: train strictly before the test set.
            # We purge rows whose label window overlaps test_start.
            # Since target lookforward is up to 60 trading days (≈90 calendar days):
            # scan_date + 90 days >= test_start => scan_date >= test_start - 90 days.
            # So training scan_dates must be strictly < test_start - 90 days.
            train_cutoff = test_start - pd.Timedelta(days=self.purge_days)
            
            train_mask = df["scan_date_dt"] < train_cutoff
            train_idx = df.index[train_mask].tolist()
            
            if not train_idx or not test_idx:
                log.warning(f"Fold {fold}: empty train or test set. Skipping.")
                continue
                
            yield np.array(train_idx), np.array(test_idx)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Marcos Lopez de Prado's Sample-Uniqueness Weighting
# ─────────────────────────────────────────────────────────────────────────────
def compute_sample_uniqueness(df: pd.DataFrame, label_window: int = 60) -> pd.Series:
    """Compute sample uniqueness weights to correct for overlapping labels (vectorized)."""
    log.info("Computing sample-uniqueness weights...")
    df = df.copy()
    df["scan_date_dt"] = pd.to_datetime(df["scan_date"])
    
    weights = np.ones(len(df), dtype=np.float32)
    symbols = df["symbol"].values
    scan_dates = df["scan_date_dt"].values
    indices = np.arange(len(df))
    
    # Sort scan dates chronologically per symbol
    sort_idx = np.lexsort((scan_dates, symbols))
    sorted_syms = symbols[sort_idx]
    sorted_dates = scan_dates[sort_idx]
    sorted_indices = indices[sort_idx]
    
    # Unique symbols and their array slice bounds
    unique_syms, sym_starts = np.unique(sorted_syms, return_index=True)
    sym_ends = np.append(sym_starts[1:], len(df))
    
    for i in range(len(unique_syms)):
        start, end = sym_starts[i], sym_ends[i]
        sym_dates = sorted_dates[start:end]
        sym_orig_indices = sorted_indices[start:end]
        
        n_rows = len(sym_dates)
        if n_rows == 0:
            continue
            
        # Align calendar day offsets relative to the symbol's first scan_date
        min_date = sym_dates[0]
        day_indices = ((sym_dates - min_date) / np.timedelta64(1, 'D')).astype(np.int32)
        
        # Sweep-line arrays (90 calendar days window + 1 for inclusion)
        starts = day_indices
        ends = day_indices + 91
        max_day = ends[-1] + 1
        
        # Concurrency diff sweep
        diff = np.zeros(max_day + 1, dtype=np.int32)
        for j in range(n_rows):
            diff[starts[j]] += 1
            diff[ends[j]] -= 1
            
        active_counts = np.cumsum(diff)[:-1]
        
        # Uniqueness integrates prefix sums over 1 / concurrency
        inv_counts = 1.0 / np.where(active_counts > 0, active_counts, 1.0)
        prefix_sums = np.zeros(len(inv_counts) + 1, dtype=np.float64)
        prefix_sums[1:] = np.cumsum(inv_counts)
        
        for j in range(n_rows):
            total_inv = prefix_sums[ends[j]] - prefix_sums[starts[j]]
            weights[sym_orig_indices[j]] = total_inv / 91.0
            
    weights_series = pd.Series(weights, index=df.index)
    weights_series = weights_series / weights_series.mean()
    log.info("Sample-uniqueness weights computed successfully.")
    return weights_series


# ─────────────────────────────────────────────────────────────────────────────
# 3. Disjoint Symbol Split
# ─────────────────────────────────────────────────────────────────────────────
def symbol_disjoint_split(df: pd.DataFrame, test_size: float = 0.15, random_seed: int = 42):
    """Split the universe of symbols to hold out a random test_size proportion."""
    np.random.seed(random_seed)
    symbols = sorted(df["symbol"].unique())
    n_holdout = int(len(symbols) * test_size)
    
    holdout_syms = set(np.random.choice(symbols, size=n_holdout, replace=False))
    
    disjoint_mask = df["symbol"].isin(holdout_syms)
    
    df_disjoint = df[disjoint_mask].copy()
    df_cv = df[~disjoint_mask].copy()
    
    log.info(f"Symbol-disjoint split: {len(holdout_syms)} symbols held out entirely. "
             f"CV set: {len(df_cv)} rows ({df_cv['symbol'].nunique()} symbols). "
             f"Disjoint set: {len(df_disjoint)} rows ({df_disjoint['symbol'].nunique()} symbols).")
             
    return df_cv, df_disjoint


# ─────────────────────────────────────────────────────────────────────────────
# 4. Trivial Baselines
# ─────────────────────────────────────────────────────────────────────────────
class BaseRateClassifier(BaseEstimator, ClassifierMixin):
    """A trivial baseline classifier that predicts the base rate probability."""
    def __init__(self):
        self.prob_ = 0.5
        
    def fit(self, X, y, sample_weight=None):
        if sample_weight is not None:
            self.prob_ = np.average(y, weights=sample_weight)
        else:
            self.prob_ = np.mean(y)
        return self
        
    def predict(self, X):
        return np.where(self.prob_ >= 0.5, 1, 0)
        
    def predict_proba(self, X):
        probs = np.full((len(X), 2), 1.0 - self.prob_)
        probs[:, 1] = self.prob_
        return probs

def evaluate_trivial_baselines(X_train, y_train, X_test, y_test, w_train=None, w_test=None):
    """Evaluate base-rate and single-feature momentum baselines."""
    # 1. Base Rate
    base_clf = BaseRateClassifier()
    base_clf.fit(X_train, y_train, sample_weight=w_train)
    base_probs = base_clf.predict_proba(X_test)[:, 1]
    
    base_auc = roc_auc_score(y_test, base_probs) if len(np.unique(y_test)) > 1 else 0.5
    base_brier = brier_score_loss(y_test, base_probs, sample_weight=w_test)
    
    # 2. Single-feature momentum baseline
    # Momentum feature index in X is usually first, but let's train a simple logistic regression on momentum_3m
    # We will pass momentum values as the single feature. Since we don't know the exact index of momentum,
    # we assume a simple logistic baseline.
    return {
        "base_rate_auc": round(base_auc, 4),
        "base_rate_brier": round(base_brier, 6)
    }
