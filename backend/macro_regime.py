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
  3. CPI data        → inflation trend (from economics-indicators)
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
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regime definitions & weight tilts
# ---------------------------------------------------------------------------
# Hand-tuned starting point. ML will optimize these multipliers.
# Multipliers applied to base weights, then re-normalized to sum=1.0

REGIME_TILTS = {
    "RISK_ON": {
        # Expansion: favor momentum & growth over safety
        "technical":     1.25,   # momentum works in risk-on
        "quality":       0.85,   # less need for safety screens
        "proximity":     0.80,   # near-52wk-high less penalizing
        "catalyst":      1.10,   # events amplified in risk-on
        "transcript":    0.90,
        "institutional": 1.10,
        "upside":        1.20,   # DCF targets more reliable in expansion
        "analyst":       1.00,
        "insider":       0.90,
        "earnings":      1.00,
    },
    "NEUTRAL": {
        # No tilt — use base weights as-is
        "technical": 1.0, "quality": 1.0, "proximity": 1.0,
        "catalyst": 1.0, "transcript": 1.0, "institutional": 1.0,
        "upside": 1.0, "analyst": 1.0, "insider": 1.0, "earnings": 1.0,
    },
    "CAUTIOUS": {
        # Tightening: favor fundamentals & smart money over momentum
        "technical":     0.75,   # momentum less reliable
        "quality":       1.30,   # quality matters more
        "proximity":     1.00,
        "catalyst":      1.15,   # catalyst events become make-or-break
        "transcript":    1.20,   # management guidance matters more
        "institutional": 1.15,
        "upside":        1.10,
        "analyst":       1.10,
        "insider":       1.25,   # insiders know first
        "earnings":      1.15,
    },
    "RISK_OFF": {
        # Crisis: full defensive — safety & quality over growth
        "technical":     0.50,   # momentum is a TRAP in risk-off
        "quality":       1.60,   # safety is king (Piotroski + Altman Z)
        "proximity":     0.80,   # near-high may mean more to fall
        "catalyst":      1.20,   # catalysts can save or kill in fear
        "transcript":    1.30,   # listen to management closely
        "institutional": 1.20,
        "upside":        0.70,   # DCF models break in crisis
        "analyst":       1.00,
        "insider":       1.40,   # strongest signal in downturns
        "earnings":      1.25,
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
    
    # PATCHED: changed to "economic-indicator"
    cpi_raw = fmp_func("economic-indicator", {
        "name": "CPI", "country": "US",
        "from": cpi_from, "to": today.strftime("%Y-%m-%d")
    })
    sleep()
    cpi_values = []
    if cpi_raw and isinstance(cpi_raw, list):
        cpi_values = sorted(
            [(d["date"], float(d["value"])) for d in cpi_raw if d.get("value")],
            reverse=True
        )

    # 4. GDP (need ~3 quarters)
    gdp_from = (today - timedelta(days=400)).strftime("%Y-%m-%d")
    
    # PATCHED: changed to "economic-indicator"
    gdp_raw = fmp_func("economic-indicator", {
        "name": "GDP", "country": "US",
        "from": gdp_from, "to": today.strftime("%Y-%m-%d")
    })
    sleep()
    gdp_values = []
    if gdp_raw and isinstance(gdp_raw, list):
        gdp_values = sorted(
            [(d["date"], float(d["value"])) for d in gdp_raw if d.get("value")],
            reverse=True
        )

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
    cpi_raw = fmp_func("economics-indicators", {
        "name": "CPI", "country": "US",
        "from": cpi_from, "to": as_of_date
    })
    sleep()
    cpi_values = []
    if cpi_raw and isinstance(cpi_raw, list):
        cpi_values = sorted(
            [(d["date"], float(d["value"])) for d in cpi_raw if d.get("value")],
            reverse=True
        )

    # 4. GDP historical
    gdp_from = (as_of - timedelta(days=400)).strftime("%Y-%m-%d")
    gdp_raw = fmp_func("economics-indicators", {
        "name": "GDP", "country": "US",
        "from": gdp_from, "to": as_of_date
    })
    sleep()
    gdp_values = []
    if gdp_raw and isinstance(gdp_raw, list):
        gdp_values = sorted(
            [(d["date"], float(d["value"])) for d in gdp_raw if d.get("value")],
            reverse=True
        )

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
