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


def _months_back(date_str: str, n: int) -> str:
    """'2026-08-01', 12 -> '2025-08-01' (month-start keys, as FMP/BLS date monthly rows)."""
    y, m = int(date_str[:4]), int(date_str[5:7])
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}-01"


def cpi_measures(cpi_values: list) -> Optional[dict]:
    """Headline-CPI inflation read for the regime + quadrant (2026-10-12 rebuild).

    LEVEL = year-over-year %, TREND = 6-month annualized vs that YoY (> +0.3pp =
    accelerating, < -0.3pp = decelerating). Lookbacks are matched BY DATE, not by list
    index: the previous version took cpi_values[2] as "3 months ago" (it is 2) and scored
    a 3-month annualized rate, so one month decided the axis (June 2026's -0.42% print
    alone turned a 3.35% YoY tape into "target inflation"). Needs 13 monthly points for
    YoY; with 7-12 the 6m annualized rate stands in as the level and `level_basis` says so.
    Returns None when there is too little data to say anything (< 7 points)."""
    pts = {}
    for d, v in cpi_values or []:
        try:
            pts[str(d)[:7] + "-01"] = float(v)
        except (TypeError, ValueError):
            continue
    if len(pts) < 7:
        return None
    newest = max(pts)
    v0 = pts[newest]

    def _ann(months):
        prev = pts.get(_months_back(newest, months))
        if not prev or prev <= 0:
            return None
        return ((v0 / prev) ** (12.0 / months) - 1) * 100

    ann_3m, ann_6m = _ann(3), _ann(6)
    prev_12 = pts.get(_months_back(newest, 12))
    yoy = (v0 / prev_12 - 1) * 100 if prev_12 else None
    if ann_6m is None:
        return None
    level, level_basis = (yoy, "yoy") if yoy is not None else (ann_6m, "6m_annualized")

    if level <= 2.0:
        score = 1.0      # at target
    elif level <= 3.0:
        score = 0.75
    elif level <= 4.0:
        score = 0.50
    elif level <= 5.0:
        score = 0.30
    elif level <= 7.0:
        score = 0.15
    else:
        score = 0.0      # stagflation territory
    trend = "stable"
    if yoy is not None:
        if ann_6m > yoy + 0.3:
            trend = "accelerating"
        elif ann_6m < yoy - 0.3:
            trend = "decelerating"
    if trend == "accelerating":
        score *= 0.7
    return {"score": round(max(0.0, min(1.0, score)), 4), "latest": newest,
            "yoy_pct": round(yoy, 2) if yoy is not None else None,
            "ann_6m_pct": round(ann_6m, 2),
            "ann_3m_pct": round(ann_3m, 2) if ann_3m is not None else None,
            "level_basis": level_basis, "trend": trend, "n_points": len(pts)}


def _score_cpi_trend(cpi_values: list) -> float:
    """
    CPI trend: is inflation accelerating or decelerating? (good-is-high: 1.0 = at target.)
    Thin wrapper over cpi_measures(); no usable data -> 0.5 neutral. A 0.5 from this
    branch is NOT a reading - callers that need to know (the quadrant) check
    cpi_measures() / the inputs provenance instead of trusting the number.
    """
    m = cpi_measures(cpi_values)
    return m["score"] if m else 0.5


def _score_gdp_momentum(gdp_values: list, annualize: bool = False) -> float:
    """
    GDP growth momentum. Input: list of (date, value) sorted newest first.
    At least 2 quarters needed. Positive & accelerating = risk-on.

    annualize=True (the LIVE paths since 2026-10-12, fed REAL GDP): QoQ growth is
    compounded to an annual rate before banding, so ">3" means 3% a year - the bands
    below read naturally. The historical/backtest callers still pass nominal GDP with
    annualize=False (raw QoQ %) and are deliberately left as they were.
    """
    if len(gdp_values) < 2:
        return 0.5  # no data → neutral

    latest = gdp_values[0][1]
    prev = gdp_values[1][1]

    if prev <= 0:
        return 0.5

    def _g(a, b):
        q = (a - b) / b
        return ((1 + q) ** 4 - 1) * 100 if annualize else q * 100

    # QoQ growth rate (annualized when asked)
    growth = _g(latest, prev)

    # Acceleration check
    if len(gdp_values) >= 3:
        prev2 = gdp_values[2][1]
        if prev2 > 0:
            prev_growth = _g(prev, prev2)
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

def growth_inflation_quadrant(sub_scores: dict, inputs: Optional[dict] = None) -> dict:
    """JPM-style growth x inflation 2x2 over the classifier's own sub-scores (2026-07-16,
    after JPM's agentic regime work): the single risk-axis `regime` label cannot distinguish
    STAGFLATION (growth down, inflation hot -> pricing power / real assets) from a
    disinflationary RISK_OFF slowdown (both down -> quality / duration / floors), nor
    GOLDILOCKS from REFLATION on the way up — and those quadrants want different books.
    Both axes were always measured (gdp_momentum, cpi_trend); this just stops collapsing
    them onto one line. cpi_trend is scored good-is-high, so >= 0.5 = inflation cooling.
    The basis string carries the raw scores so a mid-band read (e.g. 'sticky' label with
    cpi 0.55) stays transparent."""
    g = sub_scores.get("gdp_momentum")
    c = sub_scores.get("cpi_trend")
    if not isinstance(g, (int, float)) or not isinstance(c, (int, float)):
        return {"quadrant": "UNKNOWN", "quadrant_basis": "missing growth/inflation sub-scores"}
    # 2026-10-12: a defaulted or stale axis is NOT a reading. From the day this shipped
    # (2026-07-16) to 2026-10-12 cpi was the 0.5 no-data default and gdp a hardcoded
    # Q4-2025 seed, and the 2x2 printed GOLDILOCKS every week. Fail-open instead:
    # UNKNOWN = loosest entry floor, no quadrant playbook - and the caller FAIL-LOUDs.
    if inputs is not None and not inputs.get("ok", False):
        return {"quadrant": "UNKNOWN",
                "quadrant_basis": "quadrant inputs not usable - " + "; ".join(inputs.get("problems") or ["no provenance"])}
    growth_up = g >= 0.5
    inflation_cooling = c >= 0.5
    if growth_up and inflation_cooling:
        q = "GOLDILOCKS"
    elif growth_up:
        q = "REFLATION"
    elif inflation_cooling:
        q = "RISK_OFF"   # disinflationary slowdown — JPM's risk-off quadrant
    else:
        q = "STAGFLATION"
    basis = (f"growth {'up' if growth_up else 'down'} (gdp {g:.2f}) x "
             f"inflation {'cooling' if inflation_cooling else 'hot/sticky'} (cpi {c:.2f})")
    if inputs is not None:
        ci, gi = inputs.get("cpi") or {}, inputs.get("gdp") or {}
        if ci.get("yoy_pct") is not None:
            basis += (f" | CPI {ci['yoy_pct']:+.2f}% y/y, {ci.get('ann_6m_pct'):+.2f}% 6m ann., "
                      f"{ci.get('trend')} (through {ci.get('latest', '?')[:7]})")
        if gi.get("ann_growth_pct") is not None:
            basis += f" | real GDP {gi['ann_growth_pct']:+.2f}% ann. ({gi.get('latest', '?')[:7]})"
    return {"quadrant": q, "quadrant_basis": basis}


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

    # 2. VIX quote (PATCHED to use Massive API Technical Indicators when available)
    vix_price = 20.0
    vix_sma200 = None
    
    try:
        from massive_indicators import get_index_price, get_index_sma
        massive_vix = get_index_price("I:VIX")
        massive_sma = get_index_sma("I:VIX", 200, "day")
        if massive_vix and massive_sma:
            vix_price = massive_vix
            vix_sma200 = massive_sma
            log.info("  VIX: Fetched from Massive API (Indices Technical Indicators)")
    except Exception as e:
        log.debug(f"  VIX: Massive API fallback to FMP: {e}")

    # Fallback to FMP if Massive is not configured or fails
    if not vix_sma200:
        vix_data = fmp_func("quote", {"symbol": "^VIX"})
        sleep()
        if vix_data and isinstance(vix_data, list) and len(vix_data) > 0:
            vix_price = float(vix_data[0].get("price", 20))
            vix_sma200 = float(vix_data[0].get("priceAvg200", 0)) or None

    # 3+4. CPI + REAL GDP (2026-10-12 rebuild). Needs 13+ monthly CPI points (y/y level +
    # 6m trend, see cpi_measures) and 3+ quarters of REAL GDP (nominal GDP counts inflation
    # as growth, so a hot-inflation quarter could never read as stagflation).
    # _fetch_monthly_series backfills with point queries when FMP drops the window - it
    # had been doing so since at least 2026-07-17, leaving CPI on its 0.5 default and GDP
    # on the hardcoded seed below this comment's predecessor. The GCS last-known-good is
    # now only REFRESHED by a complete series and only USED (source stamped) when the
    # live fetch comes back thin. The hardcoded seeds are gone on purpose: a missing axis
    # must publish UNKNOWN with a FAIL-LOUD, never a number that looks like a reading.
    today = datetime.now()
    today_s = today.strftime("%Y-%m-%d")
    _macro_cache = _load_macro_cache()

    def _series(name, from_days, freq, min_points):
        vals = _fetch_monthly_series(
            fmp_func, name, (today - timedelta(days=from_days)).strftime("%Y-%m-%d"),
            today_s, freq=freq)
        sleep()
        src = (_FETCH_META.get(name) or {}).get("source", "fmp")
        if len(vals) >= min_points:
            _macro_cache[name] = [[d, v] for d, v in vals]
            return vals, src, True
        cached = _macro_cache.get(name) or []
        if len(cached) > len(vals):
            log.warning(f"  {name}: FMP returned {len(vals)} point(s), using GCS last-known-good "
                        f"({len(cached)} points)")
            return [(d, v) for d, v in cached], "gcs_cache", False
        log.warning(f"  {name}: {len(vals)} point(s) from FMP (below the {min_points}-point cache "
                    f"refresh) and no fuller cache - quadrant_inputs decides if it is usable")
        return vals, (src if vals else "none"), False

    # 11, not 13: BLS never published October 2025 (federal shutdown), so a full year
    # of CPI is 12 points until that hole rolls out of the window in late 2026.
    cpi_values, cpi_src, cpi_fresh = _series("CPI", 430, "M", 11)
    gdp_values, gdp_src, gdp_fresh = _series("realGDP", 560, "Q", 3)
    if cpi_fresh or gdp_fresh:
        _save_macro_cache(_macro_cache)
    inputs = quadrant_inputs(cpi_values, gdp_values, cpi_src, gdp_src, today)
    if not inputs["ok"]:
        log.warning("  QUADRANT INPUTS NOT USABLE: " + "; ".join(inputs["problems"]))

    return _attach_debt_cycle(
        _compute_regime(rates, vix_price, vix_sma200, cpi_values, gdp_values,
                        inputs=inputs, gdp_annualize=True), fmp_func)

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
                    cpi_values: list, gdp_values: list,
                    inputs: Optional[dict] = None, gdp_annualize: bool = False) -> dict:
    """
    Compute macro regime from raw data.
    Returns dict with regime, score, features (for ML), tilts.

    inputs (live path only): quadrant_inputs() provenance - stamped onto the result as
    `quadrant_inputs` and used to publish UNKNOWN instead of a defaulted quadrant.
    gdp_annualize: True when gdp_values is the live REAL GDP series (see
    _score_gdp_momentum); the historical callers keep the old nominal QoQ behaviour.
    """
    # Sub-scores (each 0.0–1.0, higher = more risk-on)
    s_curve = _score_yield_curve(rates)
    s_level = _score_yield_level(rates)
    s_vix = _score_vix(vix_price, vix_sma200)
    s_cpi = _score_cpi_trend(cpi_values)
    s_gdp = _score_gdp_momentum(gdp_values, annualize=gdp_annualize)

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

    # Map quantitative sub-scores (0.0 to 1.0) to explicit English labels 
    # to feed directly into the AI Persona JSON input:
    regime_detail = {
        "growth": "accelerating" if s_gdp > 0.6 else ("decelerating" if s_gdp < 0.4 else "stable"),
        "inflation": "decelerating" if s_cpi > 0.6 else ("accelerating" if s_cpi < 0.4 else "sticky"),
        "rates": "accommodative" if s_level > 0.6 else ("restrictive" if s_level < 0.4 else "neutral"),
        "credit": "complacent" if s_vix > 0.6 else ("fearful" if s_vix < 0.4 else "stable")
    }

    return {
        "regime":     regime,
        "score":      round(macro_score, 4),
        "sub_scores": sub_scores,
        "regime_detail": regime_detail,
        # growth x inflation 2x2 — the risk-axis regime label collapses two measured axes;
        # the quadrant keeps them apart (GOLDILOCKS | REFLATION | STAGFLATION | RISK_OFF).
        **growth_inflation_quadrant(sub_scores, inputs=inputs),
        **({"quadrant_inputs": inputs} if inputs is not None else {}),
        "features":   features,
        "tilts":      REGIME_TILTS[regime],
        "rates":      rates,
        # Dalio debt-cycle phase (backend/debt_cycle.py, 2026-07-27) — third axis, spliced
        # by _attach_debt_cycle in the fetchers, NOT computed here (this function is pure).
    }


def _attach_debt_cycle(result: dict, fmp_func) -> dict:
    """Splice the Dalio debt-cycle phase (backend/debt_cycle.py) onto a regime result.
    Read-only (advance=False): only the weekly publish ticks the state machine.
    Deliberately called from BOTH the v7 and v8 fetchers so a future v8 switch cannot
    strip this axis the way it would have stripped the quadrant. Fail-soft."""
    try:
        from debt_cycle import fetch_debt_cycle
        result["debt_cycle"] = fetch_debt_cycle(fmp_func, advance=False)
    except Exception as e:
        log.debug(f"  debt_cycle splice skipped: {e}")
        result["debt_cycle"] = {"debt_cycle_phase": "UNKNOWN", "fallback": True}
    return result


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

# Provenance of the last fetch per series name -> {"source", "n", "latest"}. Module-level
# so _fetch_monthly_series keeps its plain-list return type for the backtest callers; the
# live fetchers read it to stamp `quadrant_inputs` (2026-10-12).
_FETCH_META: dict = {}


def _period_starts(from_date: str, to_date: str, freq: str = "M") -> list:
    """Month-start (freq="M") or quarter-start ("Q") dates inside [from_date, to_date]."""
    y, m = int(from_date[:4]), int(from_date[5:7])
    step = 3 if freq == "Q" else 1
    if freq == "Q":
        m = ((m - 1) // 3) * 3 + 1
    lo, hi, out = from_date[:7] + "-01", to_date[:10], []
    while True:
        d = f"{y:04d}-{m:02d}-01"
        if d > hi:
            return out
        if d >= lo or freq == "Q":
            out.append(d)
        m += step
        if m > 12:
            m -= 12
            y += 1


def _fetch_monthly_series(
    fmp_func, name: str, from_date: str, to_date: str,
    as_of_date: Optional[str] = None, pub_lag_days: int = 14, freq: str = "M",
) -> list:
    """
    Fetch a named monthly (freq="M") or quarterly (freq="Q") economic indicator from
    FMP. Returns a list of (date, value) tuples, newest first.

    If `as_of_date` is provided, we restrict to rows where:
        date + pub_lag_days <= as_of_date
    This guards against look-ahead — the backtest on date D only "sees"
    values that WOULD have been publicly released by D.

    2026-10-12: FMP's stable economic-indicators no longer honours a from/to WINDOW -
    a 13-month CPI window returns one row, a GDP window none, sentiment/recession one -
    while a POINT query (from == to == the period start) returns that period reliably.
    Every macro sub-score fed by this helper had been sitting on its 0.5 no-data
    default or a seed. So: keep the window call (cheap when it works) and backfill the
    periods it dropped with point queries (~15 calls for a 15-month series).
    """
    raw = fmp_func("economic-indicators", {
        "name": name, "from": from_date, "to": to_date,
    })
    rows = list(raw) if isinstance(raw, list) else []
    source = "fmp_window"
    expected = _period_starts(from_date, to_date, freq)
    have = {(r.get("date") or "")[:10] for r in rows if isinstance(r, dict)}
    if expected and len(have & set(expected)) < 0.75 * len(expected):
        for d in expected:
            if d in have:
                continue
            pt = fmp_func("economic-indicators", {"name": name, "from": d, "to": d})
            if isinstance(pt, list):
                rows.extend(x for x in pt if isinstance(x, dict))
        source = "fmp_points"
    if not rows:
        _FETCH_META[name] = {"source": "none", "n": 0, "latest": None}
        return []

    values = []
    seen = set()
    for r in rows:
        if not isinstance(r, dict) or (r.get("date") or "")[:10] in seen:
            continue
        seen.add((r.get("date") or "")[:10])
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
    _FETCH_META[name] = {"source": source if values else "none", "n": len(values),
                         "latest": values[0][0] if values else None}
    return values


# Freshness limits for the quadrant inputs (days from the period START to today).
# CPI for month M publishes ~mid M+1, so the newest point is normally 45-75 days old;
# real GDP for quarter Q publishes ~4 weeks after it ends, so up to ~210 days. Past
# these the series has stopped updating and must not be read as current.
_CPI_MAX_AGE_DAYS = 100
_GDP_MAX_AGE_DAYS = 230


def quadrant_inputs(cpi_values: list, gdp_values: list, cpi_source: str, gdp_source: str,
                    today: Optional[datetime] = None) -> dict:
    """Provenance + freshness verdict for the two quadrant axes (2026-10-12). `ok` is
    False when either axis is defaulted, seeded, cached-stale or too thin to measure -
    growth_inflation_quadrant then publishes UNKNOWN and _write_macro_regime FAIL-LOUDs.
    This is the alert that did not exist while the quadrant ran on a default + a seed."""
    today = today or datetime.now()
    problems = []
    cm = cpi_measures(cpi_values)
    cpi = {"source": cpi_source, "n_points": len(cpi_values or [])}
    if cm:
        cpi.update(cm)
    else:
        problems.append(f"CPI too thin to measure ({len(cpi_values or [])} points, source {cpi_source})")
    gdp = {"source": gdp_source, "n_points": len(gdp_values or []),
           "latest": gdp_values[0][0] if gdp_values else None}
    if len(gdp_values or []) >= 2 and gdp_values[1][1] > 0:
        q = gdp_values[0][1] / gdp_values[1][1] - 1
        gdp["ann_growth_pct"] = round(((1 + q) ** 4 - 1) * 100, 2)
    else:
        problems.append(f"real GDP too thin ({len(gdp_values or [])} points, source {gdp_source})")
    for label, d, src, limit in (("CPI", cpi.get("latest"), cpi_source, _CPI_MAX_AGE_DAYS),
                                 ("real GDP", gdp.get("latest"), gdp_source, _GDP_MAX_AGE_DAYS)):
        if src in ("seed", "none", "default"):
            problems.append(f"{label} from {src}, not a live read")
        if d:
            try:
                age = (today - datetime.strptime(str(d)[:10], "%Y-%m-%d")).days
            except ValueError:
                age = None
            if age is not None:
                (cpi if label == "CPI" else gdp)["age_days"] = age
                if age > limit:
                    problems.append(f"{label} newest point {str(d)[:7]} is {age}d old (limit {limit}d)")
    return {"ok": not problems, "problems": problems, "cpi": cpi, "gdp": gdp}


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

    # --- Load GCS cache up-front (used for BOTH fallback on failure AND
    #     write-on-success). Prior v8 only wrote to cache; never read from
    #     it on failure, which meant any transient FMP 404/empty response
    #     caused the 5 sub-scores to default to 0.50 neutral with no recovery.
    #     v7.2.2 Apr 22 — fixed by matching v7's fallback pattern. ---
    cache = _load_macro_cache()

    def _fetch_or_cache(name: str, from_date: str, freq: str = "M", min_points: int = 4) -> list:
        """Fetch a fresh series (point-query backfilled, see _fetch_monthly_series); fall
        back to the GCS cache when it comes back thin. The cache is refreshed only by a
        series with >= min_points rows - a 1-row FMP answer used to overwrite it, which
        is how the 'last-known-good' itself went bad (2026-10-12)."""
        vals = _fetch_monthly_series(fmp_func, name, from_date, today_str, freq=freq)
        sleep()
        if len(vals) >= min_points:
            cache[name] = [[d, v] for d, v in vals]  # refresh cache
            return vals
        cached = cache.get(name) or []
        if len(cached) > len(vals):
            log.warning(
                f"  {name}: FMP returned {len(vals)} row(s), using GCS last-known-good "
                f"({len(cached)} rows)"
            )
            return [(d, v) for d, v in cached]
        if not vals:
            log.warning(f"  {name}: FMP empty AND GCS cache empty — neutral defaults will apply")
        return vals

    # --- CPI: 13+ months for the y/y level (cpi_measures) ---
    cpi_from = (today - timedelta(days=430)).strftime("%Y-%m-%d")
    cpi_values = _fetch_or_cache("CPI", cpi_from, min_points=11)   # Oct-2025 never published

    # --- REAL GDP, annualized in _compute_regime_v8 (2026-10-12: was nominal QoQ) ---
    gdp_from = (today - timedelta(days=560)).strftime("%Y-%m-%d")
    gdp_values = _fetch_or_cache("realGDP", gdp_from, freq="Q", min_points=3)

    # --- NEW v8 series ---
    unemp_from = (today - timedelta(days=240)).strftime("%Y-%m-%d")
    unemp_values = _fetch_or_cache("unemploymentRate", unemp_from)

    sent_from = (today - timedelta(days=240)).strftime("%Y-%m-%d")
    sent_values = _fetch_or_cache("consumerSentiment", sent_from)

    rec_from = (today - timedelta(days=240)).strftime("%Y-%m-%d")
    rec_values = _fetch_or_cache("smoothedUSRecessionProbabilities", rec_from)

    # Persist the cache (updated in-place by successful fetches above)
    try:
        _save_macro_cache(cache)
    except Exception:
        pass

    return _attach_debt_cycle(_compute_regime_v8(
        rates=rates,
        vix_price=vix_price, vix_sma200=vix_sma200,
        cpi_values=cpi_values, gdp_values=gdp_values,
        unemp_values=unemp_values,
        sent_values=sent_values,
        rec_values=rec_values,
        gdp_annualize=True,
    ), fmp_func)


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
        as_of_date=as_of_date, pub_lag_days=30, freq="Q",
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
    gdp_annualize: bool = False,
) -> dict:
    """Compute v8 regime from raw inputs. gdp_annualize: live path passes REAL GDP and
    True (see _score_gdp_momentum); the historical path keeps nominal QoQ."""
    s_curve = _score_yield_curve(rates)
    s_curve_3m = _score_yield_curve_3m(rates)
    s_level = _score_yield_level(rates)
    s_vix = _score_vix(vix_price, vix_sma200)
    s_cpi = _score_cpi_trend(cpi_values)
    s_gdp = _score_gdp_momentum(gdp_values, annualize=gdp_annualize)
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
# Alpha Compounder PIT convenience wrapper
# ---------------------------------------------------------------------------

def classify_pit(as_of_date: str, fmp_func=None) -> str:
    """Return the macro regime label at a historical date.

    Convenience wrapper for the Alpha Compounder pipeline (agent_a).
    Uses fetch_macro_regime_historical() under the hood.

    Args:
        as_of_date: "YYYY-MM-DD" string
        fmp_func: FMP API caller. If None, imports from screener_v6.

    Returns:
        Regime label: "RISK_ON", "NEUTRAL", "CAUTIOUS", or "RISK_OFF"
    """
    if fmp_func is None:
        try:
            from screener_v6 import fmp as fmp_func
        except ImportError:
            return "NEUTRAL"  # safe fallback
    result = fetch_macro_regime_historical(fmp_func, as_of_date)
    return result.get("regime", "NEUTRAL")


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
