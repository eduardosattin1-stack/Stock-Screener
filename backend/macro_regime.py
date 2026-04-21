#!/usr/bin/env python3
"""
Macro Regime Overlay — CB Screener v7
=======================================
Classifies the macro environment into 4 regimes and tilts factor weights.
Works both LIVE (screener) and HISTORICAL (backtest/ML training).

v7 changes: tilts updated for 10-factor set (removed news, catastrophe;
added quality, catalyst). Tilts are hand-tuned priors; ML will optimize.

Regimes:
  RISK_ON   — expansion, low vol, positive curve, falling inflation
  NEUTRAL   — baseline, mixed signals
  CAUTIOUS  — tightening, rising inflation, sentiment deteriorating
  RISK_OFF  — inversion/flat curve, high vol, recession risk

Data sources (4 API calls for live, cached for backtest):
  1. Treasury rates  → yield curve slope + level
  2. VIX quote       → volatility regime
  3. CPI data        → inflation trend (economic-indicators; hardcoded fallback for stable REST)
  4. GDP data        → growth momentum

Usage:
  # Live (screener_v7.py)
  regime = fetch_macro_regime(fmp_func)
  tilted = apply_macro_tilt(WEIGHTS, regime)

  # Historical (backtest_full.py)
  regime = fetch_macro_regime_historical(fmp_func, as_of_date="2025-06-15")
  features = regime["features"]  # dict of f_macro_* for ML training
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GCS last-known-good cache for macro indicators (v7.2)
# ---------------------------------------------------------------------------
# When FMP returns empty (brief API outages, rate limiting, etc.), we fall
# back to the last successful fetch cached on GCS instead of stale hardcoded
# values that drift quarterly. Fresh data always overwrites the cache.
#
# Cache path: gs://screener-signals-carbonbridge/macro/last_known_good.json
# Format: {"CPI": [[date, value], ...], "GDP": [[date, value], ...]}

_GCS_BUCKET = "screener-signals-carbonbridge"
_MACRO_CACHE_PATH = "macro/last_known_good.json"

def _gcs_token():
    """Get GCE/Cloud Run metadata token. Returns None when running locally."""
    try:
        import requests
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=2,
        )
        return r.json().get("access_token") if r.status_code == 200 else None
    except Exception:
        return None

def _load_macro_cache() -> dict:
    """Best-effort load of last-known-good macro values from GCS."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return {}
        r = requests.get(
            f"https://storage.googleapis.com/{_GCS_BUCKET}/{_MACRO_CACHE_PATH}",
            headers={"Authorization": f"Bearer {tok}"}, timeout=5,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.debug(f"  macro cache load skipped: {e}")
    return {}

def _save_macro_cache(cache: dict):
    """Best-effort save of last-known-good macro values to GCS."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return
        requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{_GCS_BUCKET}/o",
            params={"uploadType": "media", "name": _MACRO_CACHE_PATH},
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            data=json.dumps(cache), timeout=10,
        )
    except Exception as e:
        log.debug(f"  macro cache save skipped: {e}")

# ---------------------------------------------------------------------------
# Regime definitions & weight tilts
# ---------------------------------------------------------------------------
# Hand-tuned starting point. ML will optimize these multipliers.
# Multipliers applied to base weights, then re-normalized to sum=1.0

REGIME_TILTS = {
    "RISK_ON": {
        # Expansion: favor momentum & growth over safety
        "technical":          1.25,   # momentum works in risk-on
        "quality":            0.85,   # less need for safety screens
        "proximity":          0.80,   # near-52wk-high less penalizing
        "catalyst":           1.10,   # events amplified in risk-on
        "transcript":         0.90,
        "institutional":      1.10,
        "upside":             1.20,   # DCF targets more reliable in expansion
        "analyst":            1.00,
        "insider":            0.90,
        "earnings":           1.00,
        # v7.2 additions — neutral tilts initially, hand-tune after live data
        "institutional_flow": 1.15,   # flow velocity amplified in risk-on
        "sector_momentum":    1.15,   # sector rotation matters more when momentum works
        "congressional":      1.00,
    },
    "NEUTRAL": {
        # No tilt — use base weights as-is
        "technical": 1.0, "quality": 1.0, "proximity": 1.0,
        "catalyst": 1.0, "transcript": 1.0, "institutional": 1.0,
        "upside": 1.0, "analyst": 1.0, "insider": 1.0, "earnings": 1.0,
        "institutional_flow": 1.0, "sector_momentum": 1.0, "congressional": 1.0,
    },
    "CAUTIOUS": {
        # Tightening: favor fundamentals & smart money over momentum
        "technical":          0.75,   # momentum less reliable
        "quality":            1.30,   # quality matters more
        "proximity":          1.00,
        "catalyst":           1.15,   # catalyst events become make-or-break
        "transcript":         1.20,   # management guidance matters more
        "institutional":      1.15,
        "upside":             1.10,
        "analyst":            1.10,
        "insider":            1.25,   # insiders know first
        "earnings":           1.15,
        # v7.2 additions
        "institutional_flow": 1.20,   # smart money positioning matters more in tightening
        "sector_momentum":    0.85,   # sector trends less reliable
        "congressional":      1.10,
    },
    "RISK_OFF": {
        # Crisis: full defensive — safety & quality over growth
        "technical":          0.50,   # momentum is a TRAP in risk-off
        "quality":            1.60,   # safety is king (Piotroski + Altman Z)
        "proximity":          0.80,   # near-high may mean more to fall
        "catalyst":           1.20,   # catalysts can save or kill in fear
        "transcript":         1.30,   # listen to management closely
        "institutional":      1.20,
        "upside":             0.70,   # DCF models break in crisis
        "analyst":            1.00,
        "insider":            1.40,   # strongest signal in downturns
        "earnings":           1.25,
        # v7.2 additions
        "institutional_flow": 1.25,   # distribution/accumulation velocity critical
        "sector_momentum":    0.60,   # sectors crash together — noisy in crises
        "congressional":      1.15,
    },
}

# ---------------------------------------------------------------------------
# Sub-signal computations (each returns 0.0–1.0, higher = more risk-on)
# ---------------------------------------------------------------------------

def _score_yield_curve(rates: dict) -> float:
    """
    Yield curve slope: 10yr - 2yr spread.
    >150bp = very positive (1.0), 0bp = flat (0.3), inverted = (0.0)
    """
    y10 = rates.get("year10", 4.3)
    y2 = rates.get("year2", 3.8)
    spread_bp = (y10 - y2) * 100  # in basis points

    if spread_bp >= 150:
        return 1.0
    elif spread_bp >= 100:
        return 0.85
    elif spread_bp >= 50:
        return 0.70
    elif spread_bp >= 20:
        return 0.55
    elif spread_bp >= 0:
        return 0.35   # flat curve — cautious
    elif spread_bp >= -50:
        return 0.15   # mildly inverted
    else:
        return 0.0    # deeply inverted — recession signal


def _score_yield_level(rates: dict) -> float:
    """
    Absolute rate level: very high rates = tightening = less risk-on.
    Fed funds proxy: use month3 (≈ effective FFR).
    """
    ffr = rates.get("month3", 3.7)

    if ffr <= 2.0:
        return 1.0    # accommodative
    elif ffr <= 3.0:
        return 0.80
    elif ffr <= 4.0:
        return 0.60   # neutral
    elif ffr <= 5.0:
        return 0.40   # restrictive
    elif ffr <= 6.0:
        return 0.20
    else:
        return 0.0    # very tight


def _score_vix(vix_price: float, vix_sma200: float = None) -> float:
    """
    VIX level + relative to 200-day average.
    Low VIX = risk-on, high VIX = risk-off.
    """
    # Absolute level scoring
    if vix_price <= 12:
        abs_score = 1.0    # extreme complacency
    elif vix_price <= 16:
        abs_score = 0.85
    elif vix_price <= 20:
        abs_score = 0.65
    elif vix_price <= 25:
        abs_score = 0.40
    elif vix_price <= 30:
        abs_score = 0.20
    elif vix_price <= 40:
        abs_score = 0.10
    else:
        abs_score = 0.0    # panic

    # Relative scoring (VIX vs 200d average)
    if vix_sma200 and vix_sma200 > 0:
        ratio = vix_price / vix_sma200
        if ratio < 0.7:
            rel_score = 1.0    # VIX well below avg — calm
        elif ratio < 0.9:
            rel_score = 0.75
        elif ratio < 1.1:
            rel_score = 0.50   # around average
        elif ratio < 1.3:
            rel_score = 0.25
        else:
            rel_score = 0.0    # VIX spiking above avg
        return abs_score * 0.6 + rel_score * 0.4
    else:
        return abs_score


def _score_cpi_trend(cpi_values: list) -> float:
    """
    CPI trend: is inflation accelerating or decelerating?
    Input: list of (date, value) sorted newest first, at least 3 months.
    Accelerating inflation = risk-off, decelerating = risk-on.
    """
    if len(cpi_values) < 3:
        return 0.5  # no data → neutral

    # Compute YoY-ish change rate: 3-month annualized
    newest = cpi_values[0][1]
    three_mo_ago = cpi_values[2][1] if len(cpi_values) >= 3 else cpi_values[-1][1]
    six_mo_ago = cpi_values[5][1] if len(cpi_values) >= 6 else cpi_values[-1][1]

    if three_mo_ago <= 0 or six_mo_ago <= 0:
        return 0.5

    # 3-month annualized rate
    rate_3m = ((newest / three_mo_ago) ** 4 - 1) * 100
    # 6-month annualized rate (if available)
    rate_6m = ((newest / six_mo_ago) ** 2 - 1) * 100 if len(cpi_values) >= 6 else rate_3m

    # Trend: is recent rate higher than longer-term?
    is_accelerating = rate_3m > rate_6m + 0.3  # +0.3 tolerance

    # Score based on absolute level + trend
    if rate_3m <= 2.0:
        level_score = 1.0    # target inflation
    elif rate_3m <= 3.0:
        level_score = 0.75
    elif rate_3m <= 4.0:
        level_score = 0.50
    elif rate_3m <= 5.0:
        level_score = 0.30
    elif rate_3m <= 7.0:
        level_score = 0.15
    else:
        level_score = 0.0    # stagflation territory

    # Penalty for acceleration
    if is_accelerating:
        level_score *= 0.7

    return max(0, min(1, level_score))


def _score_gdp_momentum(gdp_values: list) -> float:
    """
    GDP growth momentum. Input: list of (date, value) sorted newest first.
    At least 2 quarters needed. Positive & accelerating = risk-on.
    """
    if len(gdp_values) < 2:
        return 0.5  # no data → neutral

    latest = gdp_values[0][1]
    prev = gdp_values[1][1]

    if prev <= 0:
        return 0.5

    # QoQ growth rate
    growth = (latest - prev) / prev * 100

    # Acceleration check
    if len(gdp_values) >= 3:
        prev2 = gdp_values[2][1]
        if prev2 > 0:
            prev_growth = (prev - prev2) / prev2 * 100
            is_accelerating = growth > prev_growth
        else:
            is_accelerating = False
    else:
        is_accelerating = growth > 0

    if growth > 3:
        score = 1.0
    elif growth > 2:
        score = 0.85
    elif growth > 1:
        score = 0.65
    elif growth > 0:
        score = 0.45
    elif growth > -1:
        score = 0.25  # mild contraction
    else:
        score = 0.05  # recession

    if is_accelerating:
        score = min(1.0, score + 0.10)

    return max(0, min(1, score))


# ---------------------------------------------------------------------------
# Regime classification
# ---------------------------------------------------------------------------

def classify_regime(macro_score: float) -> str:
    """Map composite macro score (0-1) to regime label."""
    if macro_score >= 0.65:
        return "RISK_ON"
    elif macro_score >= 0.45:
        return "NEUTRAL"
    elif macro_score >= 0.30:
        return "CAUTIOUS"
    else:
        return "RISK_OFF"


# ---------------------------------------------------------------------------
# LIVE: Fetch current macro data (for screener_v6.py)
# ---------------------------------------------------------------------------

def fetch_macro_regime(fmp_func, rate_limit_func=None) -> dict:
    """
    Fetch LIVE macro data and compute regime.

    Args:
        fmp_func: The screener's fmp() helper function
        rate_limit_func: Optional sleep function for rate limiting

    Returns:
        dict with keys: regime, score, sub_scores, features, tilts, rates
    """
    import time
    from datetime import datetime, timedelta
    sleep = rate_limit_func or (lambda: time.sleep(0.04))

    # 1. Treasury rates (latest)
    rates_raw = fmp_func("treasury-rates", {})
    sleep()
    rates = {}
    if rates_raw and isinstance(rates_raw, list) and len(rates_raw) > 0:
        rates = rates_raw[0]  # most recent day

    # 2. VIX quote (PATCHED)
    vix_data = fmp_func("quote", {"symbol": "^VIX"})
    sleep()
    vix_price = 20.0
    vix_sma200 = None
    if vix_data and isinstance(vix_data, list) and len(vix_data) > 0:
        vix_price = float(vix_data[0].get("price", 20))
        vix_sma200 = float(vix_data[0].get("priceAvg200", 0)) or None

    # 3. CPI (need ~6 months of history)
    today = datetime.now()
    cpi_from = (today - timedelta(days=270)).strftime("%Y-%m-%d")

    # v7.2 fix: removed country=US (FMP stable REST rejects unknown params,
    # returns 404). The economic-indicators endpoint DOES work on stable —
    # it only takes name + from + to.
    cpi_raw = fmp_func("economic-indicators", {
        "name": "CPI",
        "from": cpi_from, "to": today.strftime("%Y-%m-%d")
    })
    sleep()
    cpi_values = []
    if cpi_raw and isinstance(cpi_raw, list):
        cpi_values = sorted(
            [(d["date"], float(d["value"])) for d in cpi_raw if d.get("value")],
            reverse=True
        )

    # Persist fresh data to GCS on success; fall back to cache on failure
    _macro_cache = _load_macro_cache()
    if cpi_values:
        _macro_cache["CPI"] = [[d, v] for d, v in cpi_values]
        _save_macro_cache(_macro_cache)
    else:
        cached = _macro_cache.get("CPI") or []
        if cached:
            log.warning("  CPI: FMP returned empty, using GCS last-known-good")
            cpi_values = [(d, v) for d, v in cached]
        else:
            # Only falls through if FMP fails AND GCS cache is empty
            # (i.e. first run ever or running locally without GCS access).
            # Hardcoded values are a last-resort safety net; fresh FMP data
            # overwrites the GCS cache on every successful scan.
            log.warning("  CPI: no data from FMP or GCS cache, using hardcoded seed")
            cpi_values = [
                ("2026-03-01", 330.293), ("2026-02-01", 327.46),
                ("2026-01-01", 326.588), ("2025-12-01", 326.031),
                ("2025-11-01", 325.063), ("2025-09-01", 324.245),
            ]

    # 4. GDP (need ~3 quarters)
    gdp_from = (today - timedelta(days=400)).strftime("%Y-%m-%d")

    # v7.2 fix: same as CPI — removed country=US.
    gdp_raw = fmp_func("economic-indicators", {
        "name": "GDP",
        "from": gdp_from, "to": today.strftime("%Y-%m-%d")
    })
    sleep()
    gdp_values = []
    if gdp_raw and isinstance(gdp_raw, list):
        gdp_values = sorted(
            [(d["date"], float(d["value"])) for d in gdp_raw if d.get("value")],
            reverse=True
        )

    # Persist fresh data on success; fall back to cache on failure
    if gdp_values:
        _macro_cache["GDP"] = [[d, v] for d, v in gdp_values]
        _save_macro_cache(_macro_cache)
    else:
        cached = _macro_cache.get("GDP") or []
        if cached:
            log.warning("  GDP: FMP returned empty, using GCS last-known-good")
            gdp_values = [(d, v) for d, v in cached]
        else:
            log.warning("  GDP: no data from FMP or GCS cache, using hardcoded seed")
            gdp_values = [
                ("2025-10-01", 31422.526), ("2025-07-01", 31098.027),
                ("2025-04-01", 30485.729), ("2025-01-01", 30042.113),
            ]

    return _compute_regime(rates, vix_price, vix_sma200, cpi_values, gdp_values)

# ---------------------------------------------------------------------------
# HISTORICAL: Fetch macro data as of a past date (for backtest_full.py)
# ---------------------------------------------------------------------------

def fetch_macro_regime_historical(fmp_func, as_of_date: str, rate_limit_func=None) -> dict:
    """
    Fetch HISTORICAL macro data for backtest.

    Args:
        fmp_func: The backtest's fmp() helper function
        as_of_date: "YYYY-MM-DD" string
        rate_limit_func: Optional sleep function

    Returns:
        Same dict as fetch_macro_regime but using historical data
    """
    import time
    sleep = rate_limit_func or (lambda: time.sleep(0.04))

    as_of = datetime.strptime(as_of_date, "%Y-%m-%d")

    # 1. Treasury rates — get closest date before as_of
    tr_from = (as_of - timedelta(days=10)).strftime("%Y-%m-%d")
    rates_raw = fmp_func("treasury-rates", {"from": tr_from, "to": as_of_date})
    sleep()
    rates = {}
    if rates_raw and isinstance(rates_raw, list) and len(rates_raw) > 0:
        # Sorted newest first by FMP
        rates = rates_raw[0]

    # 2. VIX — use historical chart
    vix_from = (as_of - timedelta(days=250)).strftime("%Y-%m-%d")
    vix_chart = fmp_func("historical-price-eod/full", {
        "symbol": "^VIX", "from": vix_from, "to": as_of_date
    })
    sleep()
    vix_price = 20.0
    vix_sma200 = None
    if vix_chart and isinstance(vix_chart, list) and len(vix_chart) > 0:
        # Sorted newest first
        sorted_vix = sorted(vix_chart, key=lambda x: x.get("date", ""), reverse=True)
        vix_price = float(sorted_vix[0].get("close", 20))
        # Compute 200-day SMA from history
        closes = [float(d.get("close", 0)) for d in sorted_vix[:200] if d.get("close")]
        if len(closes) >= 50:
            vix_sma200 = sum(closes) / len(closes)

    # 3. CPI historical
    cpi_from = (as_of - timedelta(days=270)).strftime("%Y-%m-%d")
    cpi_raw = fmp_func("economic-indicators", {
        "name": "CPI",
        "from": cpi_from, "to": as_of_date
    })
    sleep()
    cpi_values = []
    if cpi_raw and isinstance(cpi_raw, list):
        cpi_values = sorted(
            [(d["date"], float(d["value"])) for d in cpi_raw if d.get("value")],
            reverse=True
        )
    if not cpi_values:
        # Fallback: FMP unavailable; hardcoded fallback for backtest
        # For backtest historical mode, use hardcoded recent values as approximation
        log.info("  CPI historical: using hardcoded fallback")
        cpi_values = [
            ("2026-03-01", 330.293), ("2026-02-01", 327.46),
            ("2026-01-01", 326.588), ("2025-12-01", 326.031),
            ("2025-11-01", 325.063), ("2025-09-01", 324.245),
        ]
        # Filter to only include values before as_of_date
        cpi_values = [(d, v) for d, v in cpi_values if d <= as_of_date]

    # 4. GDP historical
    gdp_from = (as_of - timedelta(days=400)).strftime("%Y-%m-%d")
    gdp_raw = fmp_func("economic-indicators", {
        "name": "GDP",
        "from": gdp_from, "to": as_of_date
    })
    sleep()
    gdp_values = []
    if gdp_raw and isinstance(gdp_raw, list):
        gdp_values = sorted(
            [(d["date"], float(d["value"])) for d in gdp_raw if d.get("value")],
            reverse=True
        )
    if not gdp_values:
        # Fallback: FMP unavailable; hardcoded fallback for backtest
        log.info("  GDP historical: using hardcoded fallback")
        gdp_values = [
            ("2025-10-01", 31422.526), ("2025-07-01", 31098.027),
            ("2025-04-01", 30485.729), ("2025-01-01", 30042.113),
        ]
        # Filter to only include values before as_of_date
        gdp_values = [(d, v) for d, v in gdp_values if d <= as_of_date]

    return _compute_regime(rates, vix_price, vix_sma200, cpi_values, gdp_values)


# ---------------------------------------------------------------------------
# Core computation (shared by live & historical)
# ---------------------------------------------------------------------------

def _compute_regime(rates: dict, vix_price: float, vix_sma200: float,
                    cpi_values: list, gdp_values: list) -> dict:
    """
    Compute macro regime from raw data.
    Returns dict with regime, score, features (for ML), tilts.
    """
    # Sub-scores (each 0.0–1.0, higher = more risk-on)
    s_curve = _score_yield_curve(rates)
    s_level = _score_yield_level(rates)
    s_vix = _score_vix(vix_price, vix_sma200)
    s_cpi = _score_cpi_trend(cpi_values)
    s_gdp = _score_gdp_momentum(gdp_values)

    sub_scores = {
        "yield_curve":  s_curve,
        "yield_level":  s_level,
        "vix":          s_vix,
        "cpi_trend":    s_cpi,
        "gdp_momentum": s_gdp,
    }

    # Weighted composite — yield curve and VIX are strongest signals
    SUB_WEIGHTS = {
        "yield_curve":  0.25,
        "yield_level":  0.15,
        "vix":          0.25,
        "cpi_trend":    0.20,
        "gdp_momentum": 0.15,
    }
    macro_score = sum(sub_scores[k] * SUB_WEIGHTS[k] for k in SUB_WEIGHTS)

    regime = classify_regime(macro_score)

    # Raw features for ML training (stored as f_macro_* in backtest)
    yield_spread = (rates.get("year10", 4.3) - rates.get("year2", 3.8)) * 100
    features = {
        "macro_regime_score":  round(macro_score, 4),
        "macro_yield_spread":  round(yield_spread, 2),        # 10yr-2yr in bp
        "macro_yield_level":   round(rates.get("month3", 3.7), 2),  # short rate
        "macro_vix":           round(vix_price, 2),
        "macro_vix_vs_avg":    round(vix_price / vix_sma200, 4) if vix_sma200 else 1.0,
        "macro_cpi_score":     round(s_cpi, 4),
        "macro_gdp_score":     round(s_gdp, 4),
    }

    log.info(f"  Macro regime: {regime} (score={macro_score:.3f})")
    log.info(f"    Curve={s_curve:.2f} Level={s_level:.2f} VIX={s_vix:.2f} "
             f"CPI={s_cpi:.2f} GDP={s_gdp:.2f}")
    log.info(f"    Spread={yield_spread:.0f}bp | VIX={vix_price:.1f} | "
             f"FFR≈{rates.get('month3', '?')}%")

    return {
        "regime":     regime,
        "score":      round(macro_score, 4),
        "sub_scores": sub_scores,
        "features":   features,
        "tilts":      REGIME_TILTS[regime],
        "rates":      rates,
    }


# ---------------------------------------------------------------------------
# Weight tilting
# ---------------------------------------------------------------------------

def apply_macro_tilt(base_weights: dict, regime_data: dict) -> dict:
    """
    Apply macro regime tilts to base factor weights.
    Multiplies each weight by the regime tilt, then re-normalizes to sum=1.0.

    Args:
        base_weights: dict like {"upside": 0.15, "technical": 0.15, ...}
        regime_data:  dict returned by fetch_macro_regime()

    Returns:
        New weights dict, same keys, summing to 1.0
    """
    tilts = regime_data.get("tilts", REGIME_TILTS["NEUTRAL"])
    regime = regime_data.get("regime", "NEUTRAL")

    # Apply multipliers
    tilted = {}
    for factor, weight in base_weights.items():
        multiplier = tilts.get(factor, 1.0)
        tilted[factor] = weight * multiplier

    # Re-normalize to sum=1.0
    total = sum(tilted.values())
    if total > 0:
        tilted = {k: round(v / total, 4) for k, v in tilted.items()}

    if regime != "NEUTRAL":
        changes = []
        for f in base_weights:
            delta = (tilted[f] - base_weights[f]) * 100
            if abs(delta) > 0.3:
                changes.append(f"{f} {delta:+.1f}pp")
        if changes:
            log.info(f"    Weight tilts ({regime}): {', '.join(changes)}")

    return tilted


# ---------------------------------------------------------------------------
# Dynamic RISK_FREE update
# ---------------------------------------------------------------------------

def get_risk_free_rate(rates: dict) -> float:
    """
    Get current risk-free rate from treasury data.
    Uses 10-year yield as base for DCF discount rate.
    Falls back to 4.5% if unavailable.
    """
    return rates.get("year10", 4.5) / 100


# ---------------------------------------------------------------------------
# Quick test
# ===========================================================================
# v8 ADDITIONS — Track B.4 (backtest redesign)
# ===========================================================================
# Expands the v7 regime classifier with 4 new backtest-safe inputs:
#   + unemploymentRate              (monthly, +7d publication lag)
#   + consumerSentiment             (monthly, +14d publication lag)
#   + smoothedUSRecessionProbabilities (monthly, +35d publication lag)
#   + 10y-3m treasury spread        (daily)
#
# The v7 API is preserved untouched. v8 entry points:
#   fetch_macro_regime_v8(fmp)
#   fetch_macro_regime_v8_historical(fmp, as_of_date)
#   regime_composite_floor(regime_data, base_floor)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Publication-lag guards (days) for monthly series — backtest only
# ---------------------------------------------------------------------------
_PUB_LAG_UNEMP = 7     # BLS releases first Friday of following month
_PUB_LAG_SENT = 14     # UMich preliminary mid-month, final end-of-month
_PUB_LAG_RECESSION = 35    # FRED smoothed recession prob lags a full month


# ---------------------------------------------------------------------------
# New sub-scores (each 0.0–1.0, higher = more RISK_ON)
# ---------------------------------------------------------------------------

def _score_unemployment_rate(values: list) -> float:
    """
    Unemployment rate level + trend.

    Input: list of (date, value) tuples, newest first.
            Values are percentages, e.g. 4.3 means 4.3%.

    Interpretation:
      - Low + falling     → strong labor market → RISK_ON
      - Low + rising      → peak of cycle, concerning → CAUTIOUS
      - High + falling    → recovery → NEUTRAL → RISK_ON
      - High + rising     → recession → RISK_OFF

    Scoring:
      Absolute level: <4% = strong, 4-5% = fine, 5-6% = weakening,
                      6-8% = recession risk, >8% = recession.
      Trend: 3-month change is the dominant kicker — rising ≥0.4pp
             over 3mo is a pre-recession signal.
    """
    if not values or len(values) < 1:
        return 0.5

    latest = values[0][1]

    # Absolute level
    if latest <= 3.5:
        level = 1.0
    elif latest <= 4.2:
        level = 0.85
    elif latest <= 5.0:
        level = 0.65
    elif latest <= 6.0:
        level = 0.40
    elif latest <= 7.5:
        level = 0.20
    else:
        level = 0.0

    # Trend: 3-month delta (if we have 4 points)
    trend_penalty = 0.0
    if len(values) >= 4:
        three_mo_ago = values[3][1]
        delta = latest - three_mo_ago    # positive = rising unemployment
        if delta >= 0.6:
            trend_penalty = 0.35        # Sahm-rule territory
        elif delta >= 0.4:
            trend_penalty = 0.20
        elif delta >= 0.2:
            trend_penalty = 0.10
        elif delta <= -0.3:
            trend_penalty = -0.10       # falling unemployment — bonus

    score = level - trend_penalty
    return max(0.0, min(1.0, score))


def _score_consumer_sentiment(values: list) -> float:
    """
    University of Michigan Consumer Sentiment Index.

    Long-run mean ~85. Values <60 indicate recessionary sentiment;
    values >100 indicate euphoric consumers.

    Scoring is LEVEL + TREND. Trend matters more than level for shorter
    horizons — collapsing sentiment from 80→55 in 3 months is a sharper
    signal than being stuck at 55.
    """
    if not values or len(values) < 1:
        return 0.5

    latest = values[0][1]

    # Absolute level
    if latest >= 95:
        level = 1.0
    elif latest >= 85:
        level = 0.85
    elif latest >= 75:
        level = 0.65
    elif latest >= 65:
        level = 0.45
    elif latest >= 55:
        level = 0.25
    else:
        level = 0.10    # <55 is deeply recessionary

    # Trend: 3-month change
    trend_delta = 0.0
    if len(values) >= 4:
        three_mo_ago = values[3][1]
        pct_change = (latest - three_mo_ago) / max(1.0, three_mo_ago)
        if pct_change >= 0.10:
            trend_delta = 0.15
        elif pct_change >= 0.05:
            trend_delta = 0.08
        elif pct_change <= -0.10:
            trend_delta = -0.15
        elif pct_change <= -0.05:
            trend_delta = -0.08

    score = level + trend_delta
    return max(0.0, min(1.0, score))


def _score_recession_prob(values: list) -> float:
    """
    FRED smoothedUSRecessionProbabilities (decimal 0.0–1.0).

    Direct inverse: higher recession prob → lower risk-on score.
    This is by construction the most RISK_OFF-biased signal in the
    composite; we dampen its influence via SUB_WEIGHTS_V8 below.
    """
    if not values or len(values) < 1:
        return 0.5

    latest = values[0][1]

    # Invert & compress
    # latest=0.00 → 1.0, latest=0.20 → 0.75, latest=0.50 → 0.30,
    # latest=0.80 → 0.10, latest=1.00 → 0.0
    if latest <= 0.05:
        return 1.0
    elif latest <= 0.15:
        return 0.85
    elif latest <= 0.30:
        return 0.65
    elif latest <= 0.50:
        return 0.40
    elif latest <= 0.75:
        return 0.20
    elif latest <= 0.90:
        return 0.10
    else:
        return 0.0


def _score_yield_curve_3m(rates: dict) -> float:
    """
    Classic NY-Fed recession indicator: 10y - 3m spread.

    Historically a more reliable US-recession predictor than 10y-2y
    (Estrella & Mishkin, 1996; updated by Engstrom & Sharpe, 2019).

    Input: `rates` dict from treasury-rates endpoint with keys
    `year10` and `month3` (percent).
    """
    y10 = rates.get("year10", 4.3)
    m3 = rates.get("month3", 3.7)
    spread_bp = (y10 - m3) * 100

    if spread_bp >= 200:
        return 1.0
    elif spread_bp >= 100:
        return 0.85
    elif spread_bp >= 50:
        return 0.70
    elif spread_bp >= 20:
        return 0.55
    elif spread_bp >= 0:
        return 0.35
    elif spread_bp >= -50:
        return 0.15
    else:
        return 0.0


# ---------------------------------------------------------------------------
# Composite weighting (v8)
# ---------------------------------------------------------------------------

# v7 used 5 sub-scores totaling 1.0. v8 adds 4 more. The 4 NEW sub-scores
# total 0.35 (drawn down from the old signals). Rationale:
#   - Unemployment & recession probability are direct recession signals;
#     they need enough weight to affect the regime. 0.10 + 0.08 = 0.18.
#   - Consumer sentiment is noisier but leads; 0.07.
#   - 10y-3m spread complements 10y-2y; 0.10.
SUB_WEIGHTS_V8 = {
    "yield_curve":   0.15,    # 10y - 2y (was 0.25)
    "yield_curve_3m": 0.10,   # NEW — 10y - 3m
    "yield_level":   0.10,    # was 0.15
    "vix":           0.18,    # was 0.25
    "cpi_trend":     0.12,    # was 0.20
    "gdp_momentum":  0.10,    # was 0.15
    "unemployment":  0.10,    # NEW
    "recession_prob": 0.08,   # NEW
    "consumer_sentiment": 0.07,   # NEW
}
# sanity: must sum to 1.0
# 0.15+0.10+0.10+0.18+0.12+0.10+0.10+0.08+0.07 = 1.00
assert abs(sum(SUB_WEIGHTS_V8.values()) - 1.0) < 1e-6, \
    f"SUB_WEIGHTS_V8 sums to {sum(SUB_WEIGHTS_V8.values())}, must be 1.0"


# ---------------------------------------------------------------------------
# Monthly-series fetch helpers (with backtest-safe lag filter)
# ---------------------------------------------------------------------------

def _fetch_monthly_series(
    fmp_func, name: str, from_date: str, to_date: str,
    as_of_date: Optional[str] = None, pub_lag_days: int = 14,
) -> list:
    """
    Fetch a named monthly economic indicator from FMP. Returns a list of
    (date, value) tuples, newest first.

    If `as_of_date` is provided, we restrict to rows where:
        date + pub_lag_days <= as_of_date
    This guards against look-ahead — the backtest on date D only "sees"
    values that WOULD have been publicly released by D.
    """
    raw = fmp_func("economics-indicators", {
        "name": name, "from": from_date, "to": to_date,
    })
    if not raw or not isinstance(raw, list):
        return []

    values = []
    for r in raw:
        d = (r.get("date") or "")[:10]
        v = r.get("value")
        if not d or v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if as_of_date:
            try:
                release_date = (
                    datetime.strptime(d, "%Y-%m-%d") + timedelta(days=pub_lag_days)
                ).strftime("%Y-%m-%d")
            except Exception:
                continue
            if release_date > as_of_date:
                continue
        values.append((d, v))

    values.sort(reverse=True)    # newest first
    return values


# ---------------------------------------------------------------------------
# LIVE fetch
# ---------------------------------------------------------------------------

def fetch_macro_regime_v8(fmp_func, rate_limit_func=None) -> dict:
    """
    v8 macro regime. Live mode.
    """
    import time
    from datetime import datetime, timedelta
    sleep = rate_limit_func or (lambda: time.sleep(0.04))

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    # --- Treasury rates ---
    rates_raw = fmp_func("treasury-rates", {})
    sleep()
    rates = rates_raw[0] if (rates_raw and isinstance(rates_raw, list)) else {}

    # --- VIX ---
    vix_data = fmp_func("quote", {"symbol": "^VIX"})
    sleep()
    vix_price = 20.0
    vix_sma200 = None
    if vix_data and isinstance(vix_data, list) and vix_data:
        vix_price = float(vix_data[0].get("price", 20))
        vix_sma200 = float(vix_data[0].get("priceAvg200", 0)) or None

    # --- CPI (v7 retained) ---
    cpi_from = (today - timedelta(days=270)).strftime("%Y-%m-%d")
    cpi_values = _fetch_monthly_series(fmp_func, "CPI", cpi_from, today_str)
    sleep()

    # --- GDP (v7 retained) ---
    gdp_from = (today - timedelta(days=400)).strftime("%Y-%m-%d")
    gdp_values = _fetch_monthly_series(fmp_func, "GDP", gdp_from, today_str)
    sleep()

    # --- NEW v8 series ---
    unemp_from = (today - timedelta(days=240)).strftime("%Y-%m-%d")
    unemp_values = _fetch_monthly_series(
        fmp_func, "unemploymentRate", unemp_from, today_str
    )
    sleep()

    sent_from = (today - timedelta(days=240)).strftime("%Y-%m-%d")
    sent_values = _fetch_monthly_series(
        fmp_func, "consumerSentiment", sent_from, today_str
    )
    sleep()

    rec_from = (today - timedelta(days=240)).strftime("%Y-%m-%d")
    rec_values = _fetch_monthly_series(
        fmp_func, "smoothedUSRecessionProbabilities", rec_from, today_str
    )
    sleep()

    # Persist any newly-fetched values to GCS last-known-good cache so the
    # v7 fallback still has fresh data (v7 cache is shared).
    cache = _load_macro_cache()
    if cpi_values:
        cache["CPI"] = [[d, v] for d, v in cpi_values]
    if gdp_values:
        cache["GDP"] = [[d, v] for d, v in gdp_values]
    if unemp_values:
        cache["unemploymentRate"] = [[d, v] for d, v in unemp_values]
    if sent_values:
        cache["consumerSentiment"] = [[d, v] for d, v in sent_values]
    if rec_values:
        cache["smoothedUSRecessionProbabilities"] = [[d, v] for d, v in rec_values]
    try:
        _save_macro_cache(cache)
    except Exception:
        pass

    return _compute_regime_v8(
        rates=rates,
        vix_price=vix_price, vix_sma200=vix_sma200,
        cpi_values=cpi_values, gdp_values=gdp_values,
        unemp_values=unemp_values,
        sent_values=sent_values,
        rec_values=rec_values,
    )


# ---------------------------------------------------------------------------
# HISTORICAL fetch (for backtest)
# ---------------------------------------------------------------------------

def fetch_macro_regime_v8_historical(
    fmp_func, as_of_date: str, rate_limit_func=None
) -> dict:
    """
    v8 macro regime. Backtest mode. Uses publication-lag guards on
    monthly series to prevent look-ahead.
    """
    import time
    sleep = rate_limit_func or (lambda: time.sleep(0.04))

    as_of = datetime.strptime(as_of_date, "%Y-%m-%d")

    # Treasury — daily; FMP accepts from/to
    tr_from = (as_of - timedelta(days=10)).strftime("%Y-%m-%d")
    rates_raw = fmp_func("treasury-rates", {"from": tr_from, "to": as_of_date})
    sleep()
    # FMP returns newest first
    rates = {}
    if rates_raw and isinstance(rates_raw, list):
        for row in rates_raw:
            d = (row.get("date") or "")[:10]
            if d and d < as_of_date:
                rates = row
                break

    # VIX — historical EOD chart
    vix_from = (as_of - timedelta(days=250)).strftime("%Y-%m-%d")
    vix_chart = fmp_func("historical-price-eod/full", {
        "symbol": "^VIX", "from": vix_from, "to": as_of_date,
    })
    sleep()
    vix_price = 20.0
    vix_sma200 = None
    if vix_chart and isinstance(vix_chart, list) and vix_chart:
        sorted_vix = sorted(
            [d for d in vix_chart if (d.get("date") or "")[:10] < as_of_date],
            key=lambda x: x.get("date", ""),
            reverse=True,
        )
        if sorted_vix:
            vix_price = float(sorted_vix[0].get("close", 20))
            closes = [float(x.get("close", 0)) for x in sorted_vix[:200]
                      if x.get("close")]
            if len(closes) >= 50:
                vix_sma200 = sum(closes) / len(closes)

    # CPI
    cpi_from = (as_of - timedelta(days=270)).strftime("%Y-%m-%d")
    cpi_values = _fetch_monthly_series(
        fmp_func, "CPI", cpi_from, as_of_date,
        as_of_date=as_of_date, pub_lag_days=14,
    )
    sleep()

    # GDP
    gdp_from = (as_of - timedelta(days=400)).strftime("%Y-%m-%d")
    gdp_values = _fetch_monthly_series(
        fmp_func, "GDP", gdp_from, as_of_date,
        as_of_date=as_of_date, pub_lag_days=30,
    )
    sleep()

    # v8 NEW series with proper lag guards
    unemp_from = (as_of - timedelta(days=240)).strftime("%Y-%m-%d")
    unemp_values = _fetch_monthly_series(
        fmp_func, "unemploymentRate", unemp_from, as_of_date,
        as_of_date=as_of_date, pub_lag_days=_PUB_LAG_UNEMP,
    )
    sleep()

    sent_from = (as_of - timedelta(days=240)).strftime("%Y-%m-%d")
    sent_values = _fetch_monthly_series(
        fmp_func, "consumerSentiment", sent_from, as_of_date,
        as_of_date=as_of_date, pub_lag_days=_PUB_LAG_SENT,
    )
    sleep()

    rec_from = (as_of - timedelta(days=240)).strftime("%Y-%m-%d")
    rec_values = _fetch_monthly_series(
        fmp_func, "smoothedUSRecessionProbabilities", rec_from, as_of_date,
        as_of_date=as_of_date, pub_lag_days=_PUB_LAG_RECESSION,
    )
    sleep()

    return _compute_regime_v8(
        rates=rates,
        vix_price=vix_price, vix_sma200=vix_sma200,
        cpi_values=cpi_values, gdp_values=gdp_values,
        unemp_values=unemp_values,
        sent_values=sent_values,
        rec_values=rec_values,
    )


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _compute_regime_v8(
    rates: dict,
    vix_price: float, vix_sma200: Optional[float],
    cpi_values: list, gdp_values: list,
    unemp_values: list, sent_values: list, rec_values: list,
) -> dict:
    """Compute v8 regime from raw inputs."""
    s_curve = _score_yield_curve(rates)
    s_curve_3m = _score_yield_curve_3m(rates)
    s_level = _score_yield_level(rates)
    s_vix = _score_vix(vix_price, vix_sma200)
    s_cpi = _score_cpi_trend(cpi_values)
    s_gdp = _score_gdp_momentum(gdp_values)
    s_unemp = _score_unemployment_rate(unemp_values)
    s_sent = _score_consumer_sentiment(sent_values)
    s_rec = _score_recession_prob(rec_values)

    sub_scores = {
        "yield_curve": s_curve,
        "yield_curve_3m": s_curve_3m,
        "yield_level": s_level,
        "vix": s_vix,
        "cpi_trend": s_cpi,
        "gdp_momentum": s_gdp,
        "unemployment": s_unemp,
        "consumer_sentiment": s_sent,
        "recession_prob": s_rec,
    }

    macro_score = sum(sub_scores[k] * SUB_WEIGHTS_V8[k] for k in SUB_WEIGHTS_V8)
    regime = classify_regime(macro_score)

    yield_spread_2y = (rates.get("year10", 4.3) - rates.get("year2", 3.8)) * 100
    yield_spread_3m = (rates.get("year10", 4.3) - rates.get("month3", 3.7)) * 100

    latest_unemp = unemp_values[0][1] if unemp_values else None
    latest_sent = sent_values[0][1] if sent_values else None
    latest_rec = rec_values[0][1] if rec_values else None

    features = {
        "macro_regime_score": round(macro_score, 4),
        "macro_yield_spread_2y": round(yield_spread_2y, 2),
        "macro_yield_spread_3m": round(yield_spread_3m, 2),
        "macro_yield_level": round(rates.get("month3", 3.7), 2),
        "macro_vix": round(vix_price, 2),
        "macro_vix_vs_avg": round(vix_price / vix_sma200, 4) if vix_sma200 else 1.0,
        "macro_cpi_score": round(s_cpi, 4),
        "macro_gdp_score": round(s_gdp, 4),
        "macro_unemployment": round(latest_unemp, 2) if latest_unemp is not None else None,
        "macro_unemp_score": round(s_unemp, 4),
        "macro_consumer_sentiment": round(latest_sent, 1) if latest_sent is not None else None,
        "macro_sent_score": round(s_sent, 4),
        "macro_recession_prob": round(latest_rec, 4) if latest_rec is not None else None,
        "macro_recession_score": round(s_rec, 4),
    }

    log.info(f"  Macro v8 regime: {regime} (score={macro_score:.3f})")
    log.info(f"    Curve2y={s_curve:.2f} Curve3m={s_curve_3m:.2f} "
             f"Level={s_level:.2f} VIX={s_vix:.2f} CPI={s_cpi:.2f} "
             f"GDP={s_gdp:.2f} U={s_unemp:.2f} Sent={s_sent:.2f} Rec={s_rec:.2f}")

    return {
        "regime": regime,
        "score": round(macro_score, 4),
        "sub_scores": sub_scores,
        "features": features,
        "tilts": REGIME_TILTS[regime],
        "rates": rates,
        "version": "v8",
    }


# ---------------------------------------------------------------------------
# Composite-floor modulation (per handoff spec)
# ---------------------------------------------------------------------------

def regime_composite_floor(regime_data: dict, base_floor: float = 0.80) -> float:
    """
    Modulate the entry composite floor based on regime.

    Per handoff spec:
      - RISK_OFF   → raise floor (demand stronger signals)
      - CAUTIOUS   → slight raise
      - NEUTRAL    → unchanged
      - RISK_ON    → slight lower (accept more candidates)
    """
    regime = regime_data.get("regime", "NEUTRAL")
    adjustments = {
        "RISK_ON":  -0.05,
        "NEUTRAL":   0.00,
        "CAUTIOUS": +0.03,
        "RISK_OFF": +0.05,
    }
    delta = adjustments.get(regime, 0.0)
    floor = max(0.50, min(0.95, base_floor + delta))
    return round(floor, 4)


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Test with current live data
    print("\n=== Macro Regime Test (hardcoded snapshot) ===\n")

    rates = {
        "month3": 3.69, "year2": 3.81, "year5": 3.94,
        "year10": 4.31, "year30": 4.91
    }
    result = _compute_regime(
        rates=rates,
        vix_price=19.2,
        vix_sma200=18.2,
        cpi_values=[
            ("2026-03-01", 330.293),
            ("2026-02-01", 327.46),
            ("2026-01-01", 326.588),
            ("2025-12-01", 326.031),
            ("2025-11-01", 325.063),
            ("2025-09-01", 324.245),
        ],
        gdp_values=[
            ("2025-10-01", 31422.526),
            ("2025-07-01", 31098.027),
            ("2025-04-01", 30485.729),
            ("2025-01-01", 30042.113),
        ]
    )

    print(f"\nRegime: {result['regime']}")
    print(f"Score:  {result['score']}")
    print(f"\nSub-scores:")
    for k, v in result['sub_scores'].items():
        print(f"  {k:20s}: {v:.3f}")
    print(f"\nML features:")
    for k, v in result['features'].items():
        print(f"  {k:25s}: {v}")

    # Show tilt impact on v7 weights
    from_weights = {
        "technical": 0.35, "quality": 0.15, "proximity": 0.12,
        "catalyst": 0.08, "transcript": 0.07, "institutional": 0.05,
        "upside": 0.06, "analyst": 0.05, "insider": 0.04, "earnings": 0.03,
    }
    tilted = apply_macro_tilt(from_weights, result)
    print(f"\nWeight comparison ({result['regime']}):")
    print(f"  {'Factor':20s}  {'Base':>6s}  {'Tilted':>6s}  {'Delta':>6s}")
    for f in from_weights:
        d = (tilted[f] - from_weights[f]) * 100
        marker = " ←" if abs(d) > 0.5 else ""
        print(f"  {f:20s}  {from_weights[f]:6.1%}  {tilted[f]:6.1%}  {d:+5.1f}pp{marker}")
