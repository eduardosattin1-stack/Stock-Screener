#!/usr/bin/env python3
"""
scratch/build_v2_config.py — one-off: build calibration_tracking/v2/config.json
================================================================================
Reads backend/time_model_v4_meta.json (the v4 artifact sidecar written by
time_model_trainer.py) and publishes the calibration tracker's config to
gs://screener-signals-carbonbridge/calibration_tracking/v2/config.json.

Regime mapping (v4 meta target -> tracker regime key):
  clf_10pct_30d -> p10_30   (hit_prob_10pct_30d, +10% barrier, 30 trading bars)
  clf_20pct_60d -> p20_60   (hit_prob_60d,       +20% barrier, 60 trading bars)

Usage (from anywhere; set PYTHONIOENCODING=utf-8 on Windows):
  python backend/scratch/build_v2_config.py --dry-run   # print, do not upload
  python backend/scratch/build_v2_config.py             # upload to GCS

Exits 1 with a clear message if time_model_v4_meta.json does not exist yet
(the v4 model has not been trained — Path A dependency).
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META_PATH = os.path.join(BACKEND_DIR, "time_model_v4_meta.json")

# v4 meta decile_table / touch_cdf key -> tracker regime key
REGIME_TO_CLF = {
    "p10_30": "clf_10pct_30d",
    "p20_60": "clf_20pct_60d",
}

# Tracker window length per regime — every touch-CDF array must have exactly
# this many entries (bar 1..K), or the tracker's q_i math silently breaks.
REGIME_WINDOW_BARS = {
    "p10_30": 30,
    "p20_60": 60,
}


def _cdf_violation(F, window_bars: int):
    """Reason string if F is not a valid touch CDF for this window, else None:
    must be a list of window_bars numbers, monotone non-decreasing, F[K-1] > 0."""
    if not isinstance(F, list) or len(F) != window_bars:
        got = len(F) if isinstance(F, list) else type(F).__name__
        return f"length {got} != window_bars {window_bars}"
    try:
        vals = [float(v) for v in F]
    except (TypeError, ValueError):
        return "non-numeric values"
    if any(b < a for a, b in zip(vals, vals[1:])):
        return "not monotone non-decreasing"
    if vals[-1] <= 0:
        return f"F[K-1] = {vals[-1]} (must be > 0)"
    return None


def build_config(meta: dict) -> dict:
    decile_thresholds = {}
    baselines = {}
    touch_cdf = {}
    for regime, clf in REGIME_TO_CLF.items():
        table = (meta.get("decile_table") or {}).get(clf)
        if not table:
            raise KeyError(f"time_model_v4_meta.json missing decile_table[{clf!r}]")
        edges = table.get("edges")
        hit_rate = table.get("hit_rate")
        if not edges or len(edges) != 9:
            raise ValueError(f"decile_table[{clf!r}].edges must be 9 floats, got {edges!r}")
        if not hit_rate or len(hit_rate) != 10:
            raise ValueError(f"decile_table[{clf!r}].hit_rate must be 10 floats")
        decile_thresholds[regime] = edges
        baselines[regime] = hit_rate

        cdf = (meta.get("touch_cdf") or {}).get(clf)
        if not cdf:
            raise KeyError(f"time_model_v4_meta.json missing touch_cdf[{clf!r}]")
        # Validate the CDFs hard — never upload a malformed config. The pooled
        # array is load-bearing (it is the tracker's fallback) so a violation
        # there FAILS the script; a violating by_decile entry is dropped with a
        # WARNING so the tracker's pooled fallback engages for that decile.
        K = REGIME_WINDOW_BARS[regime]
        pooled = cdf.get("pooled")
        reason = _cdf_violation(pooled, K)
        if reason:
            raise ValueError(f"touch_cdf[{clf!r}].pooled invalid: {reason}")
        by_decile = {}
        for dec, F in sorted((cdf.get("by_decile") or {}).items()):
            reason = _cdf_violation(F, K)
            if reason:
                print(f"WARNING: touch_cdf[{clf!r}].by_decile[{dec!r}] invalid ({reason}) — "
                      f"dropped; the tracker falls back to the pooled CDF for decile {dec}.")
                continue
            by_decile[dec] = F
        touch_cdf[regime] = {
            "pooled": pooled,
            "by_decile": by_decile,
        }

    holdout_range = meta.get("holdout_range")
    holdout_n = meta.get("holdout_n")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_version": meta.get("version", "v4.0"),
        "trained_through": meta.get("oos_cutoff"),
        "decile_threshold_source": (
            f"v4 OOS holdout {holdout_range} (n={holdout_n})"
            if holdout_range else "v4 OOS holdout"
        ),
        "decile_thresholds": decile_thresholds,
        "baselines": baselines,
        "touch_cdf": touch_cdf,
        "kill_switch": {"z_degraded": -3, "z_drifting": -2, "min_n_eff": 30},
        "universe_filter": "thetadata_us_coverage",
    }


def main():
    parser = argparse.ArgumentParser(description="Build + upload calibration v2 config.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the config instead of uploading it")
    args = parser.parse_args()

    if not os.path.exists(META_PATH):
        print(f"ERROR: {META_PATH} not found.")
        print("The v4 model has not been trained yet — run time_model_trainer.py (Path A) "
              "to produce time_model_v4.pkl + time_model_v4_meta.json first.")
        sys.exit(1)

    with open(META_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)

    try:
        config = build_config(meta)
    except (KeyError, ValueError) as e:
        print(f"ERROR: cannot build config from {META_PATH}: {e}")
        sys.exit(1)

    if args.dry_run:
        print(json.dumps(config, indent=2, default=str))
        print("\n--dry-run: nothing uploaded.")
        return

    sys.path.insert(0, BACKEND_DIR)
    import calibration_tracker

    path = f"{calibration_tracker.CAL_PREFIX}/config.json"
    ok = calibration_tracker._gcs_impl["write"](path, config)
    if not ok:
        print(f"ERROR: upload to gs://{calibration_tracker.GCS_BUCKET}/{path} failed "
              "(no GCS token? run `gcloud auth login` or execute on Cloud Run).")
        sys.exit(1)
    print(f"Uploaded gs://{calibration_tracker.GCS_BUCKET}/{path} "
          f"(model_version={config['model_version']}, trained_through={config['trained_through']})")


if __name__ == "__main__":
    main()
