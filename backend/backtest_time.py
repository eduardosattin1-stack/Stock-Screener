#!/usr/bin/env python3
"""
PATCH: Add time-to-target measurements to backtest_full.py
==========================================================
Run AFTER the main backtest has generated training_data.csv.
Reads the CSV, pulls daily prices for 60 days after each entry,
measures time-to-threshold, and outputs enriched training data.

Usage:
  python backtest_time.py training_data.csv

Output: training_data_timed.csv (original + 12 new columns)

New columns:
  days_to_5pct, days_to_10pct, days_to_15pct, days_to_20pct,
  hit_5pct_30d, hit_10pct_30d, hit_10pct_60d, hit_20pct_60d,
  max_gain_pct, days_to_max, max_drawdown_pct, recovery_days
"""

import os, sys, csv, time, json, logging
from datetime import datetime, timedelta

import requests

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP = "https://financialmodelingprep.com/stable"
RATE = 0.04
LOOKFORWARD_DAYS = 90  # calendar days to fetch (~60 trading days)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("time_backtest")

# Cache charts to avoid re-fetching
CHART_CACHE = {}  # "SYM|from|to" → [{date, price}]

def fmp(endpoint, params=None):
    time.sleep(RATE)
    p = {"apikey": FMP_KEY}
    if params: p.update(params)
    try:
        r = requests.get(f"{FMP}/{endpoint}", params=p, timeout=20)
        if r.status_code != 200: return None
        d = r.json()
        if isinstance(d, dict) and "Error Message" in d: return None
        return [d] if isinstance(d, dict) else (d if isinstance(d, list) else None)
    except:
        return None

def get_daily_prices(sym, start_date, days=LOOKFORWARD_DAYS):
    """Get daily close prices for `days` calendar days after start_date."""
    cache_key = f"{sym}|{start_date}"
    if cache_key in CHART_CACHE:
        return CHART_CACHE[cache_key]

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = start + timedelta(days=days)
    from_str = start.strftime("%Y-%m-%d")
    to_str = end.strftime("%Y-%m-%d")

    data = fmp("historical-price-eod/full", {
        "symbol": sym, "from": from_str, "to": to_str
    })
    if not data:
        CHART_CACHE[cache_key] = []
        return []

    # Sort chronologically
    prices = sorted(
        [{"date": d["date"], "price": float(d.get("close", 0)),
          "high": float(d.get("high", 0)), "low": float(d.get("low", 0))}
         for d in data if d.get("close") and float(d.get("close", 0)) > 0],
        key=lambda x: x["date"]
    )
    CHART_CACHE[cache_key] = prices
    return prices

def measure_time_to_targets(entry_price, daily_prices):
    """
    Given an entry price and a list of daily prices after entry,
    measure time-to-threshold for various gain levels.

    Returns dict with all timing measurements.
    """
    result = {
        "days_to_5pct": -1,
        "days_to_10pct": -1,
        "days_to_15pct": -1,
        "days_to_20pct": -1,
        "hit_5pct_30d": 0,
        "hit_10pct_30d": 0,
        "hit_10pct_60d": 0,
        "hit_20pct_60d": 0,
        "max_gain_pct": 0.0,
        "days_to_max": 0,
        "max_drawdown_pct": 0.0,
        "recovery_days": -1,
    }

    if not daily_prices or entry_price <= 0:
        return result

    max_gain = 0
    max_dd = 0
    dd_start_day = -1
    thresholds = {5: "days_to_5pct", 10: "days_to_10pct",
                  15: "days_to_15pct", 20: "days_to_20pct"}

    for i, bar in enumerate(daily_prices):
        gain = (bar["price"] - entry_price) / entry_price * 100
        # Also check intraday high for threshold hits
        high_gain = (bar["high"] - entry_price) / entry_price * 100 if bar["high"] > 0 else gain
        low_gain = (bar["low"] - entry_price) / entry_price * 100 if bar["low"] > 0 else gain

        # Track max gain
        best = max(gain, high_gain)
        if best > max_gain:
            max_gain = best
            result["days_to_max"] = i

        # Track max drawdown
        worst = min(gain, low_gain)
        if worst < max_dd:
            max_dd = worst
            dd_start_day = i

        # Recovery from max drawdown
        if dd_start_day >= 0 and gain >= 0 and result["recovery_days"] == -1:
            result["recovery_days"] = i - dd_start_day

        # Threshold hits (using intraday high for precision)
        for pct, key in thresholds.items():
            if result[key] == -1 and high_gain >= pct:
                result[key] = i

        # 30-day hit rates
        if i <= 30:
            if high_gain >= 5: result["hit_5pct_30d"] = 1
            if high_gain >= 10: result["hit_10pct_30d"] = 1
        # 60-day hit rates
        if i <= 60:
            if high_gain >= 10: result["hit_10pct_60d"] = 1
            if high_gain >= 20: result["hit_20pct_60d"] = 1

    result["max_gain_pct"] = round(max_gain, 2)
    result["max_drawdown_pct"] = round(max_dd, 2)

    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: python backtest_time.py <training_data.csv>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = input_file.replace(".csv", "_timed.csv")

    if not FMP_KEY:
        print("Set FMP_API_KEY!")
        sys.exit(1)

    # Load training data
    log.info(f"Loading {input_file}...")
    with open(input_file) as f:
        reader = csv.DictReader(f)
        samples = list(reader)
    log.info(f"Loaded {len(samples)} samples")

    # Dedupe chart fetches: group by (symbol, start_date)
    unique_charts = set()
    for s in samples:
        unique_charts.add((s["symbol"], s["start_date"]))
    log.info(f"Need {len(unique_charts)} unique chart fetches")

    # Process each sample
    enriched = []
    for i, sample in enumerate(samples):
        sym = sample["symbol"]
        start_date = sample["start_date"]
        start_price = float(sample["start_price"])

        if (i + 1) % 50 == 0:
            log.info(f"Processing {i+1}/{len(samples)} ({sym} {start_date})")

        # Get daily prices for 60+ trading days after entry
        daily = get_daily_prices(sym, start_date)

        # Measure time-to-targets
        timing = measure_time_to_targets(start_price, daily)

        # Merge with original sample
        enriched_sample = dict(sample)
        enriched_sample.update(timing)
        enriched.append(enriched_sample)

    # Write enriched CSV
    if enriched:
        fieldnames = list(enriched[0].keys())
        with open(output_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(enriched)
        log.info(f"Saved {len(enriched)} enriched samples to {output_file}")

    # ─── Quick Analysis ───
    log.info("\n" + "="*80)
    log.info("  TIME-TO-TARGET ANALYSIS")
    log.info("="*80)

    for signal in ["BUY", "WATCH", "HOLD"]:
        group = [s for s in enriched if s.get("signal") == signal]
        if not group: continue

        hit_5_30 = sum(1 for s in group if int(s["hit_5pct_30d"]) == 1)
        hit_10_30 = sum(1 for s in group if int(s["hit_10pct_30d"]) == 1)
        hit_10_60 = sum(1 for s in group if int(s["hit_10pct_60d"]) == 1)
        hit_20_60 = sum(1 for s in group if int(s["hit_20pct_60d"]) == 1)
        avg_max = sum(float(s["max_gain_pct"]) for s in group) / len(group)
        avg_dd = sum(float(s["max_drawdown_pct"]) for s in group) / len(group)

        # Average days to thresholds (only for stocks that hit them)
        hits_5 = [int(s["days_to_5pct"]) for s in group if int(s["days_to_5pct"]) > 0]
        hits_10 = [int(s["days_to_10pct"]) for s in group if int(s["days_to_10pct"]) > 0]
        hits_20 = [int(s["days_to_20pct"]) for s in group if int(s["days_to_20pct"]) > 0]
        avg_5d = sum(hits_5) / len(hits_5) if hits_5 else -1
        avg_10d = sum(hits_10) / len(hits_10) if hits_10 else -1
        avg_20d = sum(hits_20) / len(hits_20) if hits_20 else -1

        log.info(f"\n  {signal} ({len(group)} samples):")
        log.info(f"    Hit +5% in 30d:   {hit_5_30}/{len(group)} ({hit_5_30/len(group)*100:.0f}%)")
        log.info(f"    Hit +10% in 30d:  {hit_10_30}/{len(group)} ({hit_10_30/len(group)*100:.0f}%)")
        log.info(f"    Hit +10% in 60d:  {hit_10_60}/{len(group)} ({hit_10_60/len(group)*100:.0f}%)")
        log.info(f"    Hit +20% in 60d:  {hit_20_60}/{len(group)} ({hit_20_60/len(group)*100:.0f}%)")
        log.info(f"    Avg days to +5%:  {avg_5d:.0f}d" if avg_5d > 0 else "    Avg days to +5%:  n/a")
        log.info(f"    Avg days to +10%: {avg_10d:.0f}d" if avg_10d > 0 else "    Avg days to +10%: n/a")
        log.info(f"    Avg days to +20%: {avg_20d:.0f}d" if avg_20d > 0 else "    Avg days to +20%: n/a")
        log.info(f"    Avg max gain:     {avg_max:+.1f}%")
        log.info(f"    Avg max drawdown: {avg_dd:+.1f}%")

    # ─── Train time model ───
    log.info("\n\nTraining time-to-target models...")

    try:
        from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
        from sklearn.model_selection import cross_val_score
        import numpy as np

        # Features (same as main backtest)
        feature_cols = [c for c in enriched[0].keys() if c.startswith("f_")]

        # Target 1: Will stock hit +10% in 60 days? (classification)
        X = np.array([[float(s.get(c, 0)) for c in feature_cols] for s in enriched])
        y_hit10 = np.array([int(s["hit_10pct_60d"]) for s in enriched])
        y_hit20 = np.array([int(s["hit_20pct_60d"]) for s in enriched])

        clf10 = GradientBoostingClassifier(n_estimators=100, max_depth=4, random_state=42)
        scores10 = cross_val_score(clf10, X, y_hit10, cv=5, scoring="accuracy")
        log.info(f"  Hit +10% in 60d classifier: Acc={scores10.mean():.3f} ± {scores10.std():.3f}")

        clf20 = GradientBoostingClassifier(n_estimators=100, max_depth=4, random_state=42)
        scores20 = cross_val_score(clf20, X, y_hit20, cv=5, scoring="accuracy")
        log.info(f"  Hit +20% in 60d classifier: Acc={scores20.mean():.3f} ± {scores20.std():.3f}")

        # Target 2: Days to +10% (regression, only for stocks that hit it)
        mask_10 = y_hit10 == 1
        if mask_10.sum() > 50:
            y_days10 = np.array([int(s["days_to_10pct"]) for s in enriched])[mask_10]
            X_10 = X[mask_10]
            reg10 = GradientBoostingRegressor(n_estimators=100, max_depth=4, random_state=42)
            scores_reg = cross_val_score(reg10, X_10, y_days10, cv=5, scoring="r2")
            log.info(f"  Days-to-10% regression: R²={scores_reg.mean():.3f} ± {scores_reg.std():.3f}")

            # Feature importance
            reg10.fit(X_10, y_days10)
            importances = sorted(zip(feature_cols, reg10.feature_importances_),
                               key=lambda x: -x[1])
            log.info(f"\n  Top features for predicting SPEED to +10%:")
            for feat, imp in importances[:10]:
                bar = "█" * int(imp * 50)
                log.info(f"    {feat:<25} {imp:.4f}  {bar}")

        # Target 3: Max drawdown (regression)
        y_dd = np.array([abs(float(s["max_drawdown_pct"])) for s in enriched])
        reg_dd = GradientBoostingRegressor(n_estimators=100, max_depth=4, random_state=42)
        scores_dd = cross_val_score(reg_dd, X, y_dd, cv=5, scoring="r2")
        log.info(f"  Max drawdown regression: R²={scores_dd.mean():.3f} ± {scores_dd.std():.3f}")

    except ImportError:
        log.info("  sklearn not available — install with: pip install scikit-learn")

    log.info("\nDone!")

if __name__ == "__main__":
    main()
