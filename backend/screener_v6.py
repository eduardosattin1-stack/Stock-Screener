#!/usr/bin/env python3
"""
Stock Screener v7.2 — 13-Factor Honest Scoring + Composite-Band Signals
Architecture: Two-pass (cheap screen → expensive enrichment)

Changes from v7.1:
  - Weights re-optimized on 45,338-sample backtest (2022-2025, 48 monthly windows)
    Top-20 portfolio: +35.4%/yr, +25.2% alpha vs S&P, positive in all 4 years
  - Technical cap lowered 35→25% (sweep showed 25% optimal across regimes)
  - Added 3 factors to schema: institutional_flow, sector_momentum, congressional
    (compute functions not yet implemented — factors return None and weight
    redistributes to the 10 evaluated factors until wired up)
  - Tightened signal thresholds (24% STRONG BUY was too many):
    STRONG BUY ≥0.90 | BUY ≥0.80 | WATCH ≥0.65 | HOLD ≥0.50 | SELL <0.50
  - DCF and intrinsic-value guards: skip valuation methods for financially
    weak companies (piotroski<3, altman_z<1.8, or negative ROE) — fixes
    DHER.DE-style false DCF values on junk balance sheets

Factors (13 — 3 pending compute functions, weight redistributes):
  Technical 25% | Upside 14% | Quality 12% | Proximity 12% | InstFlow 9%*
  Transcript 6% | Earnings 5% | Catalyst 5% | Institutional 3%
  SectorMom 3%* | Analyst 3% | Insider 2% | Congressional 1%*
  (* = compute function pending; weight redistributes to evaluated factors)

Modes:
  --screen (default): Full universe screen → signals
  --monitor:          Re-score portfolio positions → HOLD/TRIM/SELL/ADD actions
"""

import os, sys, json, math, time, logging, smtplib, argparse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Optional

import requests

# Macro regime overlay (imported after logging init below)
HAS_MACRO = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP = "https://financialmodelingprep.com/stable"
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_KEY", "")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", SMTP_USER)

RATE_LIMIT = 0.04  # seconds between API calls (3000/min on Ultimate)
RISK_FREE = 0.045  # 10yr treasury ~4.5%
TOP_N = 15
ENRICH_TOP_N = 30  # how many stocks get expensive enrichment (transcripts)
SIGNAL_LOG = os.environ.get("SIGNAL_LOG", "signal_history.json")

# ---------------------------------------------------------------------------
# FX conversion — fallback table only (forex endpoint is NOT on REST stable)
# ---------------------------------------------------------------------------

_FX_TO_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CHF": 1.12,
    "JPY": 0.0067, "CNY": 0.14, "TWD": 0.031, "KRW": 0.00073,
    "HKD": 0.128, "INR": 0.012, "SGD": 0.75, "AUD": 0.65,
    "CAD": 0.73, "NZD": 0.60, "SEK": 0.097, "NOK": 0.093,
    "DKK": 0.145, "BRL": 0.18, "MXN": 0.058, "ZAR": 0.055,
    "THB": 0.029, "IDR": 0.000063, "MYR": 0.22, "PHP": 0.018,
    "PLN": 0.25, "CZK": 0.043, "ILS": 0.28, "SAR": 0.27,
    "AED": 0.27, "TRY": 0.031, "HUF": 0.0027,
}

def get_fx_rate(from_ccy: str, to_ccy: str) -> float:
    """Get exchange rate using fallback table only."""
    if from_ccy == to_ccy:
        return 1.0
    from_usd = _FX_TO_USD.get(from_ccy)
    to_usd = _FX_TO_USD.get(to_ccy)
    if from_usd is None or to_usd is None:
        log.warning(f"FX {from_ccy}→{to_ccy}: unknown currency, using 1.0")
        return 1.0
    if to_usd == 0:
        return 1.0
    rate = from_usd / to_usd
    return rate

# Factor weights — v7.2 ML-optimized from 45,338-sample backtest (must sum to 1.0)
# Source: nasdaq100 + sp500 + europe + asia + brazil, 2022-01 → 2025-12 (48 monthly windows)
# Top-20 portfolio: +35.4%/yr, +25.2% alpha vs S&P, positive alpha every year.
# Tech cap sweep: 15% → +40.2%/yr | 25% → +35.4%/yr (chosen) | 35% → +31.1%/yr | 52% raw → +22.7%/yr
#   Lower tech = more weight on quality/upside/proximity = better picking across regimes.
# NOTE: institutional_flow, sector_momentum, congressional don't have compute
#   functions yet. Their combined 13% weight redistributes to the 10 evaluated
#   factors (see compute_composite_v7). Effective Tech today is ~0.25/0.87≈28.7%,
#   drops to 25% once the 3 new compute functions land.
WEIGHTS = {
    "technical":          0.25,   # capped (ML raw: 52% — sweep confirmed 25% optimal)
    "upside":             0.14,   # analyst targets + DCF (ML: 10.4%)
    "quality":            0.12,   # Piotroski + Altman Z + ROE + ROIC + GM (ML: 9.3%)
    "proximity":          0.12,   # 52wk position (ML: 7.5%)
    "institutional_flow": 0.09,   # NEW — 13F flow velocity (ML: 7.3%) — COMPUTE TBD
    "transcript":         0.06,   # Claude API earnings analysis (non-backtestable)
    "earnings":           0.05,   # EPS beat rate + surprise trend (ML: 4.0%)
    "catalyst":           0.05,   # Earnings calendar + news events + analyst moves (ML: 2.1%)
    "institutional":      0.03,   # 13F positions (non-backtestable)
    "sector_momentum":    0.03,   # NEW — sector-relative momentum (ML: 3.1%) — COMPUTE TBD
    "analyst":            0.03,   # Grades + consensus (ML: 2.9%)
    "insider":            0.02,   # Insider trade statistics (ML: 0.9%)
    "congressional":      0.01,   # NEW — Senate/House trading (placeholder, REST 404) — COMPUTE TBD
}
# Sum = 1.00. Removed news (ML: 0%) and catastrophe (ML: 0.2%) — zero predictive power.

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v7")

# Macro regime overlay — tilts weights based on yield curve, VIX, CPI, GDP
try:
    from macro_regime import fetch_macro_regime, apply_macro_tilt, get_risk_free_rate
    HAS_MACRO = True
    log.info("Macro regime module loaded")
except ImportError:
    HAS_MACRO = False
    log.info("macro_regime.py not found — running without macro overlay")

# ML probability model — predicts P(+10% in 60d) per stock
HAS_ML_MODEL = False
ML_MODEL = None
ML_FEATURES = None
try:
    import joblib
    import numpy as np
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "time_model_10pct.pkl")
    if os.path.exists(model_path):
        model_data = joblib.load(model_path)
        ML_MODEL = model_data["model"]
        ML_FEATURES = model_data["features"]
        HAS_ML_MODEL = True
        log.info(f"ML model loaded: {len(ML_FEATURES)} features, {model_path}")
    else:
        log.info("time_model_10pct.pkl not found — hit_prob will be 0")
except ImportError:
    log.info("joblib/numpy not installed — ML model disabled")
except Exception as e:
    log.warning(f"ML model load failed: {e}")


def predict_hit_prob(stock) -> float:
    """Predict P(+10% in 60d) using trained GBM model. Returns 0.0 if model unavailable."""
    if not HAS_ML_MODEL or ML_MODEL is None:
        return 0.0
    try:
        # Build feature vector matching backtest column names AND scales.
        # v7.2 fix: backtest stores RAW values for piotroski/altman_z/rsi/bull_score,
        # but prior code was sending normalized (0-1) values — a silent scale
        # mismatch that has been biasing hit_prob. Now matches backtest_full.py exactly.
        fs = stock.factor_scores or {}
        feature_map = {
            # Features stored as 0-1 in backtest (normalized factor scores)
            "f_technical": fs.get("technical", 0) or 0,
            "f_upside": fs.get("upside", 0) or 0,
            "f_analyst": fs.get("analyst", 0) or 0,
            "f_earnings": fs.get("earnings", 0) or 0,
            "f_insider": fs.get("insider", 0) or 0,
            "f_news": 0.5,  # removed factor — kept for old-pkl backward compat
            "f_proximity": fs.get("proximity", 0) or 0,
            "f_catastrophe": stock.catastrophe_score,  # removed from composite, kept for old pkls
            "f_transcript": fs.get("transcript", 0) or 0,
            "f_institutional": fs.get("institutional", 0) or 0,
            "f_quality": fs.get("quality", 0) or 0,
            # v7.2 NEW — all scored 0-1 in backtest
            "f_catalyst": fs.get("catalyst", 0) or 0,
            "f_institutional_flow": fs.get("institutional_flow", 0) or 0,
            "f_sector_momentum": fs.get("sector_momentum", 0) or 0,
            "f_congressional": fs.get("congressional", 0) or 0,  # may be constant in old data
            # Features stored RAW in backtest — v7.2 fix: match raw scale
            "f_bull_score_raw": float(stock.bull_score),          # was /10 (wrong)
            "f_rsi": float(stock.rsi),                            # was /100 (wrong)
            "f_piotroski": float(stock.piotroski),                # was /9 (wrong)
            "f_altman_z": float(stock.altman_z),                  # was min(/20, 1) (wrong)
            # These were already raw-matched
            "f_momentum_20d": (stock.price - stock.sma50) / stock.sma50 if stock.sma50 > 0 else 0,
            "f_trend_strength": (stock.sma50 - stock.sma200) / stock.sma200 if stock.sma200 > 0 else 0,
            "f_prox_raw": (stock.price - stock.year_low) / (stock.year_high - stock.year_low)
                          if stock.year_high > stock.year_low > 0 else 0.5,
        }
        X = np.array([[feature_map.get(f, 0) for f in ML_FEATURES]])
        prob = ML_MODEL.predict_proba(X)[0][1]  # probability of class 1 (hit +10%)
        return round(float(prob), 3)
    except Exception as e:
        log.debug(f"ML predict failed for {stock.symbol}: {e}")
        return 0.0

# Portfolio state path (GCS or local)
PORTFOLIO_STATE = os.environ.get("PORTFOLIO_STATE", "portfolio_state.json")

# ---------------------------------------------------------------------------
# FMP API Client — all stable endpoints use ?symbol= query params
# ---------------------------------------------------------------------------

def fmp(endpoint: str, params: dict = None) -> Optional[list]:
    """Call FMP stable API. Returns list or None."""
    time.sleep(RATE_LIMIT)
    url = f"{FMP}/{endpoint}"
    p = {"apikey": FMP_KEY}
    if params:
        p.update(params)
    try:
        r = requests.get(url, params=p, timeout=20)
        if r.status_code != 200:
            log.warning(f"FMP {r.status_code}: {endpoint} → {r.text[:120]}")
            return None
        data = r.json()
        if isinstance(data, dict) and "Error Message" in data:
            log.warning(f"FMP error: {endpoint} → {data['Error Message'][:80]}")
            return None
        if isinstance(data, dict):
            return [data]
        return data if isinstance(data, list) else None
    except Exception as e:
        log.warning(f"FMP exception {endpoint}: {e}")
        return None

# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------

@dataclass
class Stock:
    symbol: str = ""
    price: float = 0.0
    currency: str = "USD"

    # v7.2: exchange/country/sector (populated from company-screener at universe build)
    exchange: str = ""        # e.g. "NYSE", "NASDAQ", "XETRA", "LSE"
    country: str = ""         # ISO-2 e.g. "US", "DE", "GB", "NL"
    sector: str = ""          # e.g. "Healthcare", "Technology"

    # Quote
    sma50: float = 0.0
    sma200: float = 0.0
    year_high: float = 0.0
    year_low: float = 0.0
    market_cap: float = 0.0
    volume: int = 0

    # Technicals (computed from OHLCV)
    rsi: float = 50.0
    macd_signal: str = ""
    adx: float = 0.0
    bb_pct: float = 0.5
    stoch_rsi: float = 50.0
    obv_trend: str = ""
    bull_score: int = 0

    # Analyst
    target: float = 0.0
    upside: float = 0.0
    grade_buy: int = 0
    grade_total: int = 0
    grade_score: float = 0.5
    eps_beats: int = 0
    eps_total: int = 0

    # Value / Buffett
    revenue_cagr_3y: float = 0.0
    eps_cagr_3y: float = 0.0
    roe_avg: float = 0.0
    roe_consistent: bool = False
    roic_avg: float = 0.0
    gross_margin: float = 0.0
    gross_margin_trend: str = ""
    piotroski: int = 0
    altman_z: float = 0.0
    dcf_value: float = 0.0
    owner_earnings_yield: float = 0.0
    intrinsic_buffett: float = 0.0
    intrinsic_avg: float = 0.0
    margin_of_safety: float = 0.0
    value_score: float = 0.0

    # New v6 fields
    insider_buy_ratio: float = 0.0    # acquired/disposed ratio (recent 2 quarters)
    insider_net_buys: int = 0         # net purchase transactions
    insider_score: float = 0.5        # 0-1

    inst_holders_change: float = 0.0  # QoQ change in holder count
    inst_accumulation: float = 0.0    # net shares accumulated
    inst_score: float = 0.5           # 0-1

    transcript_sentiment: float = 0.0 # -1 to 1
    transcript_summary: str = ""
    transcript_score: float = 0.5     # 0-1

    news_sentiment: float = 0.0      # -1 to 1
    news_score: float = 0.5          # 0-1

    proximity_52wk: float = 0.5      # 0 = at low, 1 = at high
    proximity_score: float = 0.5     # 0-1

    catastrophe_score: float = 1.0   # 1 = no catastrophe, 0 = full divergence

    # Earnings momentum (separate from eps_beats)
    earnings_momentum: float = 0.0   # trend in EPS surprises
    earnings_score: float = 0.5      # 0-1

    # Upside (enhanced)
    upside_score: float = 0.0        # 0-1

    # NEW v7: Quality factor
    quality_score: float = 0.0       # 0-1 (Piotroski + Altman Z + ROE + ROIC + GM)

    # NEW v7: Catalyst factor
    catalyst_score: float = 0.5      # 0-1 (earnings calendar + news events + analyst moves)
    catalyst_flags: list = field(default_factory=list)
    has_catalyst: bool = False
    days_to_earnings: int = -1

    # Composite
    composite: float = 0.0
    signal: str = "HOLD"
    classification: str = ""
    reasons: list = field(default_factory=list)

    # ML probability prediction (GBM model, P(+10% in 60d))
    hit_prob: float = 0.0            # 0-1, from trained model; 0 if model not loaded

    # Factor breakdown for transparency
    factor_scores: dict = field(default_factory=dict)

    # v7.1: Factor coverage — how many factors had real data vs defaulting to neutral
    factor_coverage: int = 0               # count of factors with real evaluation (0-10)
    factor_coverage_pct: float = 0.0       # coverage as fraction (0.0-1.0)
    factors_evaluated: list = field(default_factory=list)   # names of factors with real data
    factors_missing: list = field(default_factory=list)     # names of factors with no data

# ---------------------------------------------------------------------------
# 1. Stock Discovery (unchanged from v5)
# ---------------------------------------------------------------------------

REGIONS = {
    "nasdaq100": [("NASDAQ", None, 5_000_000_000, 100)],
    "sp500": [
        ("NASDAQ", None, 1_000_000_000, 500), # Lowered to 1B for mid-cap growth (WIX)
        ("NYSE", None, 1_000_000_000, 500)
    ],
    "europe": [
        ("XETRA", "DE", 1_000_000_000, 100), # Lowered floor, higher stock limit (DHER)
        ("PAR", "FR", 1_000_000_000, 100),
        ("LSE", "UK", 1_000_000_000, 100),
        ("AMS", "NL", 1_000_000_000, 50),    # Raised from 500M — filters illiquid B-shares
        ("STO", "SE", 1_000_000_000, 50),    # Raised from 500M
        ("HEL", "FI", 1_000_000_000, 50),    # Raised from 500M
        ("OSL", "NO", 1_000_000_000, 50),    # Raised from 500M
        ("CPH", "DK", 1_000_000_000, 50),    # Raised from 500M
        ("MIL", "IT", 1_000_000_000, 50),
        ("SIX", "CH", 1_000_000_000, 50),
        ("BME", "ES", 1_000_000_000, 50),
    ],
    "asia": [
        ("JPX", "JP", 5_000_000_000, 100),
        # HKSE: no country filter — most major HKSE listings are mainland
        # Chinese companies (country=CN) e.g. 9988.HK (BABA), 0700.HK (Tencent),
        # 3690.HK (Meituan), 9618.HK (JD.com). Filtering by country=HK would
        # miss all of them. Limit raised to 200 since this universe is bigger.
        ("HKSE", None, 5_000_000_000, 200),
        ("KSC", "KR", 5_000_000_000, 50),
    ],
    "brazil": [("SAO", "BR", 1_000_000_000, 50)],
    "global": None,  # Will now include EVERY region above
}

# v7.2: module-level caches for sector data (populated at scan start, read many times)
SECTOR_MAP: dict[str, str] = {}           # {sym: "Technology"}  from company-screener
SECTOR_PERF_CACHE: dict[str, float] = {}  # {"Technology": 0.0842}  60d cumulative return
SECTOR_EXCHANGE_MAP: dict[str, str] = {}  # {sym: "NASDAQ"}  needed for sector perf calls
COUNTRY_MAP: dict[str, str] = {}          # {sym: "US"} ISO-2 country code, for filter/display
EARNINGS_CAL_CACHE: dict[str, list] = {}  # {sym: [events]} 90-day forward earnings, populated lazily

def get_symbols(region: str) -> list[str]:
    """Fetch universe of symbols for a region/index using FMP company-screener.
    v7.2: also populates SECTOR_MAP and SECTOR_EXCHANGE_MAP as a side effect."""
    # If "global", iterate through every defined list in REGIONS
    if region == "global":
        syms = []
        # Dynamically include every key that has a list of configs
        for r_name, config in REGIONS.items():
            if config is not None:
                syms.extend(get_symbols(r_name))
        return list(dict.fromkeys(syms))
    
    configs = REGIONS.get(region)
    if configs is None:
        configs = [(region.upper(), None, 1_000_000_000, 50)]
        
    symbols = []
    for exchange, country, min_cap, limit in configs:
        params = {
            "exchange": exchange, "marketCapMoreThan": min_cap,
            "volumeMoreThan": 100_000,     # filter illiquid stocks
            "priceMoreThan": 1,            # filter penny stocks
            "isActivelyTrading": "true", "isEtf": "false", "isFund": "false",
            "limit": limit,
        }
        if country: params["country"] = country
        data = fmp("company-screener", params)
        if data:
            batch = []
            for d in data:
                sym = d.get("symbol")
                if not sym:
                    continue
                batch.append(sym)
                # v7.2: preserve sector + exchange + country for scoring and UI filters
                sec = d.get("sector") or ""
                if sec:
                    SECTOR_MAP[sym] = sec
                SECTOR_EXCHANGE_MAP[sym] = d.get("exchangeShortName") or exchange
                co = d.get("country") or country or ""
                if co:
                    COUNTRY_MAP[sym] = co.upper()
            log.info(f"  {exchange}/{country or 'all'}: {len(batch)} stocks")
            symbols.extend(batch)
    return list(dict.fromkeys(symbols))

# ---------------------------------------------------------------------------
# v7.2: Sector performance bulk fetcher (1 call per sector, shared across universe)
# ---------------------------------------------------------------------------

def preload_sector_performance(days: int = 60):
    """Populate SECTOR_PERF_CACHE with cumulative N-day return per sector.
    Called once at scan start. ~11 API calls total for standard US sectors.
    For each sector present in SECTOR_MAP, fetch daily performance and sum changes."""
    from datetime import datetime, timedelta
    if not SECTOR_MAP:
        log.info("  Sector perf: no stocks in SECTOR_MAP yet, skipping preload")
        return
    sectors_needed = set(s for s in SECTOR_MAP.values() if s)
    if not sectors_needed:
        return
    # Only fetch NASDAQ performance — FMP endpoint is US-centric, and EU/Asia
    # sectors lack a reliable sector-performance endpoint on stable REST.
    # For non-NASDAQ stocks, sector_momentum will degrade to neutral (0.5).
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    for sector in sectors_needed:
        data = fmp("historical-sector-performance", {
            "sector": sector,
            "from": from_date, "to": to_date,
            "exchange": "NASDAQ",
        })
        if data and isinstance(data, list):
            # Sort newest-first, take last N trading days
            sorted_data = sorted(data, key=lambda x: x.get("date", ""), reverse=True)[:days]
            cumulative = sum(float(d.get("averageChange") or 0) for d in sorted_data) / 100
            SECTOR_PERF_CACHE[sector] = cumulative
    log.info(f"  Sector perf preloaded: {len(SECTOR_PERF_CACHE)} sectors "
             f"(range {min(SECTOR_PERF_CACHE.values()):+.1%} to "
             f"{max(SECTOR_PERF_CACHE.values()):+.1%})" if SECTOR_PERF_CACHE
             else "  Sector perf preloaded: empty")

# ---------------------------------------------------------------------------
# 2. Quote
# ---------------------------------------------------------------------------

def get_quote(sym: str) -> Optional[dict]:
    data = fmp("quote", {"symbol": sym})
    if not data:
        return None
    return _parse_quote(data[0])

def _parse_quote(q: dict) -> dict:
    return {
        "price": float(q.get("price", 0)),
        "sma50": float(q.get("priceAvg50", 0)),
        "sma200": float(q.get("priceAvg200", 0)),
        "year_high": float(q.get("yearHigh", 0)),
        "year_low": float(q.get("yearLow", 0)),
        "market_cap": float(q.get("marketCap", 0)),
        "volume": int(q.get("volume", 0)),
        "avg_volume": int(q.get("avgVolume", 0)),
        "currency": q.get("currency", "USD"),
    }

def get_quotes_batch(symbols: list[str]) -> dict[str, dict]:
    """Fetch quotes. Tries batch endpoint first, falls back to single quotes."""
    results = {}
    first_batch = symbols[:10]
    csv = ",".join(first_batch)
    test = fmp("batch-quote", {"symbols": csv})
    use_batch = test is not None and len(test) > 0

    if use_batch:
        log.info("batch-quote endpoint available — using batch mode")
        for q in test:
            sym = q.get("symbol", "")
            if sym and float(q.get("price", 0)) > 0:
                results[sym] = _parse_quote(q)
        for i in range(10, len(symbols), 10):
            batch = symbols[i:i+10]
            data = fmp("batch-quote", {"symbols": ",".join(batch)})
            if data:
                for q in data:
                    sym = q.get("symbol", "")
                    if sym and float(q.get("price", 0)) > 0:
                        results[sym] = _parse_quote(q)
    else:
        log.info("batch-quote not available — falling back to single quotes")
        for sym in symbols:
            q = get_quote(sym)
            if q and q["price"] > 0:
                results[sym] = q

    log.info(f"Quotes loaded: {len(results)}/{len(symbols)}")
    return results

# ---------------------------------------------------------------------------
# 3. Technicals — computed from OHLCV chart data
# ---------------------------------------------------------------------------

def get_chart(sym: str, days: int = 200) -> Optional[list]:
    start = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    data = fmp("historical-price-eod/full", {"symbol": sym, "from": start, "to": end})
    if not data or len(data) < 30:
        return None
    data.sort(key=lambda x: x.get("date", ""))
    return data

def compute_rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i-1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_macd(closes: list) -> dict:
    def ema(data, n):
        if len(data) < n:
            return data[:]
        result = [sum(data[:n]) / n]
        mult = 2 / (n + 1)
        for i in range(n, len(data)):
            result.append((data[i] - result[-1]) * mult + result[-1])
        return result
    if len(closes) < 35:
        return {"signal": "neutral", "histogram": 0}
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    min_len = min(len(ema12), len(ema26))
    macd_line = [ema12[-(min_len - i)] - ema26[-(min_len - i)] for i in range(min_len)]
    signal_line = ema(macd_line, 9)
    if len(signal_line) < 2 or len(macd_line) < 2:
        return {"signal": "neutral", "histogram": 0}
    hist_now = macd_line[-1] - signal_line[-1]
    hist_prev = macd_line[-2] - signal_line[-2] if len(macd_line) > 2 and len(signal_line) > 2 else hist_now
    if hist_prev < 0 and hist_now > 0:
        sig = "bullish_cross"
    elif hist_prev > 0 and hist_now < 0:
        sig = "bearish_cross"
    elif hist_now > 0:
        sig = "bullish"
    else:
        sig = "bearish"
    return {"signal": sig, "histogram": hist_now}

def compute_adx(highs, lows, closes, period=14):
    if len(closes) < period * 2:
        return 0.0
    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        h, l, pc = highs[i], lows[i], closes[i-1]
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
    def smooth(data, n):
        s = [sum(data[:n])]
        for i in range(n, len(data)):
            s.append(s[-1] - s[-1]/n + data[i])
        return s
    atr = smooth(tr_list, period)
    s_plus = smooth(plus_dm, period)
    s_minus = smooth(minus_dm, period)
    min_len = min(len(atr), len(s_plus), len(s_minus))
    if min_len < period:
        return 0.0
    dx_list = []
    for i in range(min_len):
        if atr[i] == 0:
            continue
        di_plus = 100 * s_plus[i] / atr[i]
        di_minus = 100 * s_minus[i] / atr[i]
        denom = di_plus + di_minus
        dx_list.append(abs(di_plus - di_minus) / denom * 100 if denom else 0)
    if len(dx_list) < period:
        return 0.0
    return sum(dx_list[-period:]) / period

def compute_bollinger(closes, period=20, std_mult=2):
    if len(closes) < period:
        return 0.5
    sma = sum(closes[-period:]) / period
    std = (sum((c - sma)**2 for c in closes[-period:]) / period) ** 0.5
    upper = sma + std_mult * std
    lower = sma - std_mult * std
    width = upper - lower
    if width == 0:
        return 0.5
    return (closes[-1] - lower) / width

def compute_stoch_rsi(closes, rsi_period=14, stoch_period=14):
    if len(closes) < rsi_period + stoch_period:
        return 50.0
    rsi_vals = []
    for i in range(rsi_period + 1, len(closes) + 1):
        rsi_vals.append(compute_rsi(closes[:i], rsi_period))
    if len(rsi_vals) < stoch_period:
        return 50.0
    recent = rsi_vals[-stoch_period:]
    lo, hi = min(recent), max(recent)
    if hi == lo:
        return 50.0
    return (rsi_vals[-1] - lo) / (hi - lo) * 100

def compute_obv_trend(closes, volumes, lookback=20):
    min_len = min(len(closes), len(volumes))
    if min_len < lookback + 1:
        return "flat"
    closes = closes[:min_len]
    volumes = volumes[:min_len]
    obv = [0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i-1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    if len(obv) < lookback:
        return "flat"
    recent = obv[-lookback:]
    slope = (recent[-1] - recent[0]) / max(abs(recent[0]), 1)
    if slope > 0.05:
        return "rising"
    elif slope < -0.05:
        return "falling"
    return "flat"

def get_technicals(sym: str, quote: dict) -> Optional[dict]:
    chart = get_chart(sym)
    if not chart:
        return None
    closes = [float(d.get("close", 0)) for d in chart if d.get("close")]
    highs = [float(d.get("high", 0)) for d in chart if d.get("high")]
    lows = [float(d.get("low", 0)) for d in chart if d.get("low")]
    volumes = [int(d.get("volume", 0)) for d in chart if d.get("volume")]
    if len(closes) < 30:
        return None

    price = quote["price"]
    sma50 = quote["sma50"]
    sma200 = quote["sma200"]
    rsi = compute_rsi(closes)
    macd = compute_macd(closes)
    adx = compute_adx(highs, lows, closes)
    bb_pct = compute_bollinger(closes)
    stoch = compute_stoch_rsi(closes)
    obv = compute_obv_trend(closes, volumes)
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else closes[-1]

    # Bull score: 10 signals
    score = 0
    reasons = []
    if price > sma50 > 0:
        score += 1; reasons.append(">SMA50")
    if sma50 > sma200 > 0:
        score += 1; reasons.append("Golden cross")
    if 40 < rsi < 70:
        score += 1; reasons.append(f"RSI {rsi:.0f}")
    if macd["signal"] in ("bullish", "bullish_cross"):
        score += 1; reasons.append(f"MACD {macd['signal']}")
    if adx > 20:
        score += 1; reasons.append(f"ADX {adx:.0f}")
    if 0.3 < bb_pct < 0.8:
        score += 1; reasons.append(f"BB%B {bb_pct:.2f}")
    if price > sma20:
        score += 1; reasons.append(">SMA20")
    if 20 < stoch < 80:
        score += 1; reasons.append(f"StochRSI {stoch:.0f}")
    if obv == "rising":
        score += 1; reasons.append("OBV rising")
    if quote["year_high"] > 0 and price > quote["year_high"] * 0.85:
        score += 1; reasons.append("Near 52wk high")

    return {
        "rsi": rsi, "macd_signal": macd["signal"], "adx": adx,
        "bb_pct": bb_pct, "stoch_rsi": stoch, "obv_trend": obv,
        "bull_score": score, "bull_reasons": reasons,
        # v7: include quote fields for signal classification
        "sma50": sma50, "sma200": sma200, "price": price,
        "year_high": quote.get("year_high", 0),
        "year_low": quote.get("year_low", 0),
    }

# ---------------------------------------------------------------------------
# 4. Analyst (targets + grades + earnings)
# ---------------------------------------------------------------------------

def get_analyst(sym: str) -> dict:
    result = {"target": 0, "upside": 0, "grade_score": 0.5, "_grade_evaluated": False,
              "grade_buy": 0, "grade_total": 0, "eps_beats": 0, "eps_total": 0,
              "eps_surprises": []}  # track individual surprise magnitudes

    # Price target consensus
    pt = fmp("price-target-consensus", {"symbol": sym})
    if pt and pt[0].get("targetConsensus"):
        result["target"] = float(pt[0]["targetConsensus"])

    # Grades (recent 90 days)
    grades = fmp("grades", {"symbol": sym, "limit": 30})
    if grades:
        cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        recent = [g for g in grades if g.get("date", "") >= cutoff]
        if recent:
            buy_grades = {"Buy", "Strong Buy", "Outperform", "Overweight", "Market Outperform", "Positive"}
            buys = sum(1 for g in recent if g.get("newGrade", "") in buy_grades)
            result["grade_buy"] = buys
            result["grade_total"] = len(recent)
            result["grade_score"] = buys / len(recent) if recent else 0.5
            result["_grade_evaluated"] = True

    # Earnings beats + surprise magnitudes
    earnings = fmp("earnings", {"symbol": sym, "limit": 8})
    if earnings:
        for e in earnings:
            actual = e.get("epsActual")
            est = e.get("epsEstimated")
            if actual is not None and est is not None:
                result["eps_total"] += 1
                act_f, est_f = float(actual), float(est)
                if act_f >= est_f:
                    result["eps_beats"] += 1
                # Store surprise % for momentum calculation
                if est_f != 0:
                    surprise_pct = (act_f - est_f) / abs(est_f)
                else:
                    surprise_pct = 1.0 if act_f > 0 else 0.0
                result["eps_surprises"].append(surprise_pct)

    return result

# ---------------------------------------------------------------------------
# 5. Value / Buffett Layer
# ---------------------------------------------------------------------------

def safe_cagr(start, end, years):
    if not start or not end or start <= 0 or end <= 0 or years <= 0:
        return 0.0
    return (end / start) ** (1 / years) - 1

def get_value(sym: str, price: float, price_currency: str = "USD") -> dict:
    """Full Buffett value analysis with FX-aware intrinsic value calculation."""
    v = {
        "revenue_cagr_3y": 0, "eps_cagr_3y": 0,
        "roe_avg": 0, "roe_consistent": False, "roic_avg": 0,
        "gross_margin": 0, "gross_margin_trend": "unknown",
        "piotroski": 0, "altman_z": 0,
        "dcf_value": 0, "owner_earnings_yield": 0,
        "intrinsic_buffett": 0, "intrinsic_bvps": 0, "intrinsic_avg": 0,
        "bvps_cagr_10y": 0.0, "bvps_consistency": 0.0, "bvps_recent_cagr": 0.0,
        "margin_of_safety": 0, "value_score": 0,
        "classification": "UNKNOWN",
    }
    if price <= 0:
        return v

    # Income statements (5 years)
    inc = fmp("income-statement", {"symbol": sym, "period": "annual", "limit": 5})

    # Detect reporting currency early
    reported_ccy = price_currency
    if inc and len(inc) >= 1:
        rc = inc[0].get("reportedCurrency") or inc[-1].get("reportedCurrency")
        if rc:
            reported_ccy = rc
    fx_to_report = get_fx_rate(price_currency, reported_ccy)
    fx_to_price = get_fx_rate(reported_ccy, price_currency)
    need_fx = reported_ccy != price_currency
    local_price = price * fx_to_report if need_fx else price
    if inc and len(inc) >= 2:
        inc.sort(key=lambda x: x.get("date", ""))
        revs = [float(x.get("revenue", 0)) for x in inc]
        eps_list = [float(x.get("epsDiluted", 0)) for x in inc]
        gp_list = [float(x.get("grossProfit", 0)) for x in inc]

        n = len(revs)
        if n >= 4 and revs[0] > 0:
            v["revenue_cagr_3y"] = safe_cagr(revs[-4], revs[-1], 3)
        elif n >= 2 and revs[0] > 0:
            v["revenue_cagr_3y"] = safe_cagr(revs[0], revs[-1], n - 1)
        if n >= 4 and eps_list[-4] > 0 and eps_list[-1] > 0:
            v["eps_cagr_3y"] = safe_cagr(eps_list[-4], eps_list[-1], 3)

        if revs[-1] > 0 and gp_list[-1] > 0:
            v["gross_margin"] = gp_list[-1] / revs[-1]
        margins = [gp / rev if rev > 0 else 0 for gp, rev in zip(gp_list, revs)]
        if len(margins) >= 3:
            if margins[-1] > margins[-3] + 0.02:
                v["gross_margin_trend"] = "expanding"
            elif margins[-1] < margins[-3] - 0.02:
                v["gross_margin_trend"] = "contracting"
            else:
                v["gross_margin_trend"] = "stable"

    # Key metrics
    km = fmp("key-metrics", {"symbol": sym, "period": "annual", "limit": 5})
    if km:
        km.sort(key=lambda x: x.get("date", ""))
        roes = [float(x.get("returnOnEquity", 0)) for x in km]
        roics = [float(x.get("returnOnInvestedCapital", 0)) for x in km]
        if roes:
            v["roe_avg"] = sum(roes) / len(roes)
            v["roe_consistent"] = all(r > 0.15 for r in roes)
        if roics:
            v["roic_avg"] = sum(roics) / len(roics)

    # ------------------- PATCHED: Financial scores (Bulletproofed for v7) -------------------
    scores = fmp("financial-scores", {"symbol": sym})
    if scores and scores[0]:
        v["piotroski"] = int(scores[0].get("piotroskiScore") or 0)
        v["altman_z"] = float(scores[0].get("altmanZScore") or 0)

    # ------------------- v7.2 PATCH: DCF Section (guarded) -------------------
    # FMP DCF is unguarded at source: returns large positive values for companies
    # that are unprofitable or have negative equity (e.g. DHER.DE showing €138 DCF
    # at €20 price). Gate DCF on baseline financial health.
    # Guard uses "known weak" semantic — if data is missing (piotroski=0 or
    # altman_z=0 from default init), we don't penalize; only skip when we have
    # positive evidence of weakness.
    dcf = fmp("discounted-cash-flow", {"symbol": sym})
    if dcf and dcf[0]:
        raw_dcf = float(dcf[0].get("dcf") or 0)
        weak_financial_health = (
            (0 < v["piotroski"] < 3) or
            (0 < v["altman_z"] < 1.8) or
            (v["roe_avg"] < 0)
        )
        if weak_financial_health and raw_dcf > 0:
            log.info(f"  {sym}: DCF guarded (piotroski={v['piotroski']}, "
                     f"altman_z={v['altman_z']:.2f}, roe={v['roe_avg']:.2%}) — "
                     f"raw DCF {raw_dcf:.2f} → 0")
            raw_dcf = 0
        if need_fx and raw_dcf > 0:
            ratio = raw_dcf / price if price > 0 else 0
            if 0.1 < ratio < 10:
                v["dcf_value"] = raw_dcf * fx_to_report
            else:
                v["dcf_value"] = raw_dcf
        else:
            v["dcf_value"] = raw_dcf

    # ------------------- PATCHED: Owner earnings Section (Bulletproofed) -------------------
    oe = fmp("owner-earnings", {"symbol": sym, "limit": 4})
    if oe:
        annual_oe_ps = sum(float(x.get("ownersEarningsPerShare") or 0) for x in oe)
        if local_price > 0:
            v["owner_earnings_yield"] = annual_oe_ps / local_price

    # Intrinsic value — Buffett earnings growth method (v7.2 — guarded)
    # Same guard as DCF: positive EPS alone isn't enough, also need baseline
    # health. Prevents speculative growth projections on distressed companies.
    if inc and len(inc) >= 2:
        inc.sort(key=lambda x: x.get("date", ""))
        latest_eps = float(inc[-1].get("epsDiluted", 0))
        weak_financial_health = (
            (0 < v["piotroski"] < 3) or
            (0 < v["altman_z"] < 1.8) or
            (v["roe_avg"] < 0)
        )
        if latest_eps > 0 and not weak_financial_health:
            base_growth = min(v["revenue_cagr_3y"], 0.30)
            growth_rates = [base_growth * (0.8 ** i) for i in range(5)]
            future_eps = latest_eps
            for g in growth_rates:
                future_eps *= (1 + max(g, 0.03))
            terminal_pe = min(max(15, 1 / max(RISK_FREE, 0.03)), 30)
            future_price = future_eps * terminal_pe
            v["intrinsic_buffett"] = future_price / (1.10 ** 5)
        elif latest_eps > 0 and weak_financial_health:
            log.info(f"  {sym}: Buffett intrinsic guarded (weak health) — "
                     f"skipping despite positive EPS")

    # ------------------- v7.2: BVPS Growth Method (third valuation) -------------------
    # Book-value-per-share compounding — Buffett's "retained earnings engine".
    # Requires 10 years of balance sheets. Unlike DCF/EPS-growth methods which
    # project cash flows, BVPS measures realized shareholder-equity compounding.
    # Guards: skip if BVPS declined 3+ years OR any year had negative equity OR
    # weightedAverageShsOutDil missing. Also skip for weak-health companies.
    bs = fmp("balance-sheet-statement", {"symbol": sym, "period": "annual", "limit": 10})
    if bs and len(bs) >= 5 and not weak_financial_health:
        bs.sort(key=lambda x: x.get("date", ""))  # oldest first
        bvps_series = []
        any_negative_equity = False
        for row in bs:
            equity = float(row.get("totalStockholdersEquity") or 0)
            shares = float(row.get("weightedAverageShsOutDil") or 0)
            if equity <= 0:
                any_negative_equity = True
                break
            if shares > 0:
                bvps_series.append((row.get("date", ""), equity / shares))

        if not any_negative_equity and len(bvps_series) >= 5:
            # Consistency: fraction of YoY periods with positive growth
            yoy_growth_flags = []
            for i in range(1, len(bvps_series)):
                prev_bvps = bvps_series[i - 1][1]
                curr_bvps = bvps_series[i][1]
                if prev_bvps > 0:
                    yoy_growth_flags.append(1 if curr_bvps > prev_bvps else 0)
            consistency = (sum(yoy_growth_flags) / len(yoy_growth_flags)
                           if yoy_growth_flags else 0)
            v["bvps_consistency"] = round(consistency, 3)

            # Skip if BVPS declined 3+ years (broken compounder)
            declines = len(yoy_growth_flags) - sum(yoy_growth_flags)
            if declines >= 3:
                log.info(f"  {sym}: BVPS method guarded (declined {declines} years "
                         f"of {len(yoy_growth_flags)}) — broken compounder")
            else:
                # Full-window CAGR
                years_span = len(bvps_series) - 1
                first_bvps = bvps_series[0][1]
                last_bvps = bvps_series[-1][1]
                full_cagr = safe_cagr(first_bvps, last_bvps, years_span)

                # Recent 3-year CAGR (captures acceleration/deceleration)
                recent_cagr = full_cagr
                if len(bvps_series) >= 4:
                    recent_start = bvps_series[-4][1]
                    recent_cagr = safe_cagr(recent_start, last_bvps, 3)

                v["bvps_cagr_10y"] = round(full_cagr, 4)
                v["bvps_recent_cagr"] = round(recent_cagr, 4)

                # Conservative projection: take min of three growth signals
                retention = 1.0  # default if dividend data unavailable
                if v["roe_avg"] > 0:
                    # Retention = 1 - (dividends paid / net income); approximate
                    # via owner-earnings yield proxy, capped conservatively
                    retention = 0.7  # typical mature-company retention
                roe_implied_growth = v["roe_avg"] * retention
                growth_rate = min(full_cagr, recent_cagr, roe_implied_growth, 0.15)
                growth_rate = max(growth_rate, 0.02)  # floor at 2%

                # Project 10 years forward
                future_bvps = last_bvps * ((1 + growth_rate) ** 10)
                # Terminal P/B: Buffett's ROE/required-return rule, capped at 5x
                required_return = 0.10
                terminal_pb = min(v["roe_avg"] / required_return, 5.0) if v["roe_avg"] > 0 else 1.5
                terminal_pb = max(terminal_pb, 1.0)
                future_price = future_bvps * terminal_pb
                # Discount back at 10%
                v["intrinsic_bvps"] = future_price / (1.10 ** 10)

    # Average intrinsic — all in reporting currency, MoS vs local_price
    # v7.2: now 3 methods (DCF + Buffett earnings + BVPS compounding)
    methods = [v["dcf_value"], v["intrinsic_buffett"], v["intrinsic_bvps"]]
    valid = [m for m in methods if m > 0]
    if valid and local_price > 0:
        v["intrinsic_avg"] = sum(valid) / len(valid)
        v["margin_of_safety"] = (v["intrinsic_avg"] - local_price) / local_price

    # Convert intrinsic values to price currency for display
    if need_fx:
        for key in ("dcf_value", "intrinsic_buffett", "intrinsic_bvps", "intrinsic_avg"):
            if v[key] > 0:
                v[key] *= fx_to_price

    # Sanity check: MoS should be between -1 and +10
    if abs(v["margin_of_safety"]) > 10:
        log.warning(f"  {sym}: MoS {v['margin_of_safety']:.0%} looks wrong, capping at ±500%")
        v["margin_of_safety"] = max(-5.0, min(5.0, v["margin_of_safety"]))

    # Value score (0-1)
    vs = 0.0
    mos = v["margin_of_safety"]
    vs += min(max(mos, 0), 0.5) * 0.6
    if v["roe_consistent"]: vs += 0.1
    if v["roe_avg"] > 0.15: vs += 0.05
    if v["roic_avg"] > 0.12: vs += 0.05
    if v["gross_margin"] > 0.40: vs += 0.05
    if v["gross_margin_trend"] == "expanding": vs += 0.05
    if v["piotroski"] >= 7: vs += 0.05
    elif v["piotroski"] >= 5: vs += 0.02
    if v["altman_z"] > 3.0: vs += 0.05
    elif v["altman_z"] > 1.8: vs += 0.02
    if v["revenue_cagr_3y"] > 0.15: vs += 0.1
    elif v["revenue_cagr_3y"] > 0.08: vs += 0.05
    if v["eps_cagr_3y"] > 0.15: vs += 0.1
    elif v["eps_cagr_3y"] > 0.08: vs += 0.05
    if v["owner_earnings_yield"] > RISK_FREE: vs += 0.1
    elif v["owner_earnings_yield"] > RISK_FREE * 0.5: vs += 0.05
    v["value_score"] = min(vs, 1.0)

    # Classification
    if v["margin_of_safety"] > 0.30 and v["roe_avg"] > 0.10:
        v["classification"] = "DEEP_VALUE"
    elif v["margin_of_safety"] > 0.10 and v["piotroski"] >= 5:
        v["classification"] = "VALUE"
    elif v["revenue_cagr_3y"] > 0.20 and v["gross_margin"] > 0.50:
        v["classification"] = "QUALITY_GROWTH"
    elif v["revenue_cagr_3y"] > 0.15:
        v["classification"] = "GROWTH"
    elif v["roe_avg"] < 0 or (v["margin_of_safety"] < -0.20
          and not (v["piotroski"] >= 7 and v["gross_margin"] > 0.50)):
        v["classification"] = "SPECULATIVE"
    else:
        v["classification"] = "NEUTRAL"

    return v

# ---------------------------------------------------------------------------
# 6. NEW: Insider Activity (FMP insider-trading/statistics)
# ---------------------------------------------------------------------------

def get_insider_activity(sym: str) -> dict:
    """Fetch insider trade statistics for recent 2 quarters. Returns insider score 0-1."""
    result = {"buy_ratio": 0.0, "net_buys": 0, "score": 0.5, "_evaluated": False}

    data = fmp("insider-trading/statistics", {"symbol": sym})
    if not data:
        return result

    # Use the most recent 2 quarters
    recent = data[:2] if len(data) >= 2 else data

    total_acquired = sum(d.get("totalAcquired", 0) for d in recent)
    total_disposed = sum(d.get("totalDisposed", 0) for d in recent)
    buy_tx = sum(d.get("acquiredTransactions", 0) for d in recent)
    sell_tx = sum(d.get("disposedTransactions", 0) for d in recent)

    # Acquired/Disposed ratio
    if total_disposed > 0:
        result["buy_ratio"] = total_acquired / total_disposed
    elif total_acquired > 0:
        result["buy_ratio"] = 5.0  # strong buy signal

    result["net_buys"] = buy_tx - sell_tx

    # Score 0-1: heavy buying = 1.0, heavy selling = 0.0
    # acquiredDisposedRatio: >1 = net buying, <1 = net selling
    ratios = [d.get("acquiredDisposedRatio", 0) for d in recent]
    avg_ratio = sum(ratios) / len(ratios) if ratios else 0

    if avg_ratio >= 2.0:
        result["score"] = 1.0  # strong insider buying
    elif avg_ratio >= 1.0:
        result["score"] = 0.75  # net insider buying
    elif avg_ratio >= 0.5:
        result["score"] = 0.5  # mixed
    elif avg_ratio >= 0.2:
        result["score"] = 0.3  # net selling
    else:
        result["score"] = 0.15  # heavy selling

    # Bonus: if insiders are buying with actual purchases (not just options exercises)
    total_purchases = sum(d.get("totalPurchases", 0) for d in recent)
    if total_purchases > 0:
        result["score"] = min(result["score"] + 0.15, 1.0)

    result["_evaluated"] = True
    return result

# ---------------------------------------------------------------------------
# 7. NEW: News Sentiment (FMP search-stock-news)
# ---------------------------------------------------------------------------

def get_news_sentiment(sym: str) -> dict:
    """Fetch recent stock news and estimate sentiment from title keywords."""
    result = {"sentiment": 0.0, "score": 0.5, "count": 0}

    data = fmp("news/stock", {"symbols": sym, "limit": 15})
    if not data:
        return result

    # Simple keyword-based sentiment (no external NLP needed)
    positive_words = {
        "upgrade", "beat", "beats", "surpass", "surge", "soar", "rally", "gain",
        "bullish", "growth", "profit", "outperform", "buy", "strong", "record",
        "breakout", "momentum", "expand", "raise", "boost", "optimistic",
        "dividend", "buyback", "innovation", "breakthrough", "approve", "launch",
    }
    negative_words = {
        "downgrade", "miss", "misses", "decline", "drop", "fall", "crash",
        "bearish", "loss", "underperform", "sell", "weak", "warning", "risk",
        "lawsuit", "investigation", "fraud", "bankruptcy", "layoff", "cut",
        "tariff", "sanction", "recall", "concern", "uncertainty", "plunge",
    }

    scores = []
    for article in data:
        title = (article.get("title", "") + " " + article.get("text", "")[:200]).lower()
        pos = sum(1 for w in positive_words if w in title)
        neg = sum(1 for w in negative_words if w in title)
        total = pos + neg
        if total > 0:
            scores.append((pos - neg) / total)
        else:
            scores.append(0)

    result["count"] = len(data)
    if scores:
        result["sentiment"] = sum(scores) / len(scores)  # -1 to 1
        # Map sentiment to 0-1 score
        result["score"] = min(max((result["sentiment"] + 1) / 2, 0), 1)

    return result

# ---------------------------------------------------------------------------
# 8. NEW: 52-Week Proximity
# ---------------------------------------------------------------------------

def compute_52wk_proximity(quote: dict) -> dict:
    """How close is price to 52wk high? Higher = more bullish."""
    result = {"proximity": 0.5, "score": 0.5}

    yh = quote.get("year_high", 0)
    yl = quote.get("year_low", 0)
    price = quote.get("price", 0)

    if yh > yl > 0 and price > 0:
        # 0 = at 52wk low, 1 = at 52wk high
        result["proximity"] = (price - yl) / (yh - yl)

        # Score: favor stocks near highs but not extreme
        prox = result["proximity"]
        if prox > 0.95:
            result["score"] = 0.7   # at high, might be stretched
        elif prox > 0.80:
            result["score"] = 1.0   # strong, near high
        elif prox > 0.60:
            result["score"] = 0.8   # healthy position
        elif prox > 0.40:
            result["score"] = 0.5   # mid-range
        elif prox > 0.20:
            result["score"] = 0.3   # near lows, might be catching a knife
        else:
            result["score"] = 0.15  # at bottom

    return result

# ---------------------------------------------------------------------------
# 9. NEW: Earnings Momentum
# ---------------------------------------------------------------------------

def compute_earnings_momentum(analyst: dict) -> dict:
    """Score based on EPS beat rate AND improving surprise trend."""
    result = {"momentum": 0.0, "score": 0.5, "_evaluated": False}

    eps_total = analyst.get("eps_total", 0)
    eps_beats = analyst.get("eps_beats", 0)
    surprises = analyst.get("eps_surprises", [])

    if eps_total == 0:
        return result

    # Beat rate component (60% of score)
    beat_rate = eps_beats / eps_total
    beat_component = beat_rate  # 0-1

    # Trend component (40%): are surprises getting bigger/more positive?
    trend_component = 0.5
    if len(surprises) >= 4:
        # surprises are newest-first from FMP, so reverse for chronological
        chron = list(reversed(surprises))
        recent_avg = sum(chron[-2:]) / 2
        earlier_avg = sum(chron[:2]) / 2
        if recent_avg > earlier_avg + 0.02:
            trend_component = 0.9  # improving
        elif recent_avg > earlier_avg - 0.02:
            trend_component = 0.5  # stable
        else:
            trend_component = 0.2  # deteriorating
        result["momentum"] = recent_avg - earlier_avg

    result["score"] = beat_component * 0.6 + trend_component * 0.4
    result["_evaluated"] = True
    return result

# ---------------------------------------------------------------------------
# 10. NEW: Upside Potential (enhanced with DCF cross-check)
# ---------------------------------------------------------------------------

def compute_upside_score(analyst: dict, value: dict, price: float) -> dict:
    """Score based on target upside cross-checked with intrinsic value."""
    result = {"score": 0.0, "consensus_upside": 0, "dcf_upside": 0, "_evaluated": False}

    if price <= 0:
        return result

    # Analyst target upside
    target = analyst.get("target", 0)
    if target > 0:
        result["consensus_upside"] = (target - price) / price * 100

    # DCF/intrinsic upside
    dcf = value.get("dcf_value", 0)
    intrinsic = value.get("intrinsic_avg", 0)
    if intrinsic > 0:
        result["dcf_upside"] = (intrinsic - price) / price * 100

    # Evaluated if we have at least one valuation anchor
    if target > 0 or intrinsic > 0:
        result["_evaluated"] = True

    # Cross-check scoring: both must agree for high score
    target_up = result["consensus_upside"]
    dcf_up = result["dcf_upside"]

    if target_up > 20 and dcf_up > 20:
        result["score"] = 1.0    # both say 20%+ upside
    elif target_up > 10 and dcf_up > 10:
        result["score"] = 0.8    # both say 10%+ upside
    elif target_up > 10 or dcf_up > 10:
        result["score"] = 0.6    # at least one says 10%+
    elif target_up > 0 and dcf_up > 0:
        result["score"] = 0.4    # both positive but modest
    elif target_up > 0 or dcf_up > 0:
        result["score"] = 0.25   # mixed signals
    elif target_up < -10 and dcf_up < -10:
        result["score"] = 0.0    # both say overvalued
    else:
        result["score"] = 0.15   # negative but not extreme

    return result

# ---------------------------------------------------------------------------
# 11. NEW: Catastrophe Detector (divergence-based)
# ---------------------------------------------------------------------------

def compute_catastrophe(tech: dict, value: dict, analyst: dict, insider: dict) -> dict:
    """
    Detects when multiple signals diverge dangerously.
    Returns score 0-1: 1.0 = healthy, 0.0 = catastrophe.
    Unlike v5 penalty, this is a standalone factor (5% weight).
    """
    result = {"score": 1.0, "flags": []}

    # Financial distress
    az = value.get("altman_z", 0)
    if 0 < az < 1.8:
        result["score"] -= 0.25
        result["flags"].append(f"Altman Z {az:.1f} (distress)")

    # Fundamental weakness
    pio = value.get("piotroski", 0)
    if pio <= 2:
        result["score"] -= 0.20
        result["flags"].append(f"Piotroski {pio}/9")

    # Technical extreme
    rsi = tech.get("rsi", 50)
    if rsi > 85:
        result["score"] -= 0.15
        result["flags"].append(f"RSI {rsi:.0f} (overbought)")
    elif rsi < 15:
        result["score"] -= 0.15
        result["flags"].append(f"RSI {rsi:.0f} (oversold)")

    # Earnings misses
    eps_total = analyst.get("eps_total", 0)
    eps_beats = analyst.get("eps_beats", 0)
    if eps_total >= 3 and eps_beats == 0:
        result["score"] -= 0.15
        result["flags"].append("0 EPS beats in 3+ quarters")

    # Insider exodus
    ins_score = insider.get("score", 0.5)
    if ins_score <= 0.15:
        result["score"] -= 0.15
        result["flags"].append("Heavy insider selling")

    # Bull-value divergence: technicals bearish but looks cheap, or vice versa
    bull = tech.get("bull_score", 5)
    mos = value.get("margin_of_safety", 0)
    if bull >= 8 and mos < -0.30:
        result["score"] -= 0.10
        result["flags"].append("Tech bullish but 30%+ overvalued")
    elif bull <= 2 and mos > 0.50:
        result["score"] -= 0.10
        result["flags"].append("Deep value but no momentum")

    result["score"] = max(result["score"], 0.0)
    return result

# ---------------------------------------------------------------------------
# 11b. NEW v7: Quality Factor (Piotroski + Altman Z + ROE + ROIC + GM)
# ---------------------------------------------------------------------------

def compute_quality_score(value: dict) -> dict:
    """
    Quality factor: combines financial health metrics into a single 0-1 score.
    ML backtest found this is the #2 predictor of outperformance.
    """
    result = {"score": 0.0}

    pio = value.get("piotroski", 5)
    az = value.get("altman_z", 5.0)
    roe = value.get("roe_avg", 0)
    roic = value.get("roic_avg", 0)
    gm = value.get("gross_margin", 0)

    # Piotroski (40% of quality) — strongest single predictor
    result["score"] += (pio / 9) * 0.40

    # Altman Z (20%) — bankruptcy risk filter
    result["score"] += min(az / 20, 1.0) * 0.20

    # ROE (15%) — profitability
    result["score"] += min(max(roe, 0) / 0.30, 1.0) * 0.15

    # ROIC (10%) — capital efficiency
    result["score"] += min(max(roic, 0) / 0.20, 1.0) * 0.10

    # Gross margin (15%) — competitive moat
    result["score"] += min(gm / 0.60, 1.0) * 0.15

    result["score"] = min(result["score"], 1.0)
    return result

# ---------------------------------------------------------------------------
# 11c. NEW v7: Catalyst Factor (event-driven scoring)
# ---------------------------------------------------------------------------

def compute_catalyst_score(sym: str, analyst: dict = None) -> dict:
    """
    Catalyst factor: detects upcoming events that could move the stock.
    Scans: earnings calendar, recent analyst moves, M&A/activist news,
    congressional trading, dividend changes.

    Returns score 0-1: 0.5 = neutral (no events), >0.6 = positive catalyst,
    <0.35 = negative catalyst (downgrades, miss-prone earnings).
    """
    result = {"score": 0.5, "flags": [], "has_catalyst": False,
              "is_risky": False, "days_to_earnings": -1, "_evaluated": False}
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    # ─── A) Upcoming Earnings ───────────────────────────────────
    # FMP /stable/earnings-calendar does NOT honor a symbol filter — it
    # returns the global calendar for a date range. Fetch 90 days forward
    # ONCE per scan and cache per-symbol. Use date() arithmetic (not datetime)
    # so a same-day scan doesn't read as "-1d" due to time-of-day drift.
    today_date = today.date()

    # Populate cache on first call: one global 90-day fetch, indexed by symbol
    if not EARNINGS_CAL_CACHE:
        end_date = (today + timedelta(days=90)).strftime("%Y-%m-%d")
        all_events = fmp("earnings-calendar", {"from": today_str, "to": end_date})
        if all_events and isinstance(all_events, list):
            for ev in all_events:
                s_ev = ev.get("symbol") or ""
                d_ev = ev.get("date") or ""
                if s_ev and d_ev >= today_str:
                    EARNINGS_CAL_CACHE.setdefault(s_ev, []).append(ev)
            for s_ev in EARNINGS_CAL_CACHE:
                EARNINGS_CAL_CACHE[s_ev].sort(key=lambda e: e.get("date", ""))
            log.info(f"  Earnings calendar cached: {len(EARNINGS_CAL_CACHE)} symbols with upcoming earnings in next 90d")
        else:
            # Mark as populated (empty) so we don't retry on every stock
            EARNINGS_CAL_CACHE["__empty_sentinel__"] = []

    sym_events = EARNINGS_CAL_CACHE.get(sym, [])
    if sym_events:
        e = sym_events[0]
        report_date = e.get("date", "")
        try:
            days_until = (datetime.strptime(report_date, "%Y-%m-%d").date() - today_date).days
        except:
            days_until = 999
        result["days_to_earnings"] = days_until

        if 0 <= days_until <= 14:
            # Check beat history from analyst data or fresh fetch
            eps_beats = (analyst or {}).get("eps_beats", 0)
            eps_total = (analyst or {}).get("eps_total", 0)

            if eps_total == 0:
                # Fetch if not provided
                hist = fmp("earnings", {"symbol": sym, "limit": 8})
                if hist:
                    for h in hist:
                        a, e2 = h.get("epsActual"), h.get("epsEstimated")
                        if a is not None and e2 is not None:
                            eps_total += 1
                            if float(a) >= float(e2):
                                eps_beats += 1

            beat_rate = eps_beats / eps_total if eps_total > 0 else 0.5

            if beat_rate >= 0.875:
                result["score"] += 0.30
                result["flags"].append(f"Earnings in {days_until}d, {eps_beats}/{eps_total} beat streak")
            elif beat_rate >= 0.75:
                result["score"] += 0.20
                result["flags"].append(f"Earnings in {days_until}d, {eps_beats}/{eps_total} beats")
            elif beat_rate >= 0.5:
                result["score"] += 0.10
                result["flags"].append(f"Earnings in {days_until}d, mixed history")
            else:
                result["score"] -= 0.10
                result["flags"].append(f"⚠ Earnings in {days_until}d, MISS-PRONE ({eps_beats}/{eps_total})")


    # ─── B) Recent Analyst Moves (last 7 days) ─────────────────
    grades = fmp("grades", {"symbol": sym, "limit": 10})
    if grades:
        cutoff = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        recent = [g for g in grades if g.get("date", "") >= cutoff]

        upgrades = sum(1 for g in recent if g.get("action") == "upgrade")
        downgrades = sum(1 for g in recent if g.get("action") == "downgrade")

        if upgrades >= 2:
            result["score"] += 0.20
            result["flags"].append(f"{upgrades} upgrades in 7d")
        elif upgrades == 1:
            result["score"] += 0.10
            result["flags"].append(f"1 upgrade in 7d")

        if downgrades >= 2:
            result["score"] -= 0.25
            result["flags"].append(f"⚠ {downgrades} downgrades in 7d")
        elif downgrades == 1:
            result["score"] -= 0.15
            result["flags"].append(f"⚠ 1 downgrade in 7d")

    # ─── C) M&A / Activist / Major Event News (last 14 days) ──
    news = fmp("news/stock", {"symbols": sym, "limit": 10})
    if news:
        cutoff = (today - timedelta(days=14)).strftime("%Y-%m-%d")
        ma_kw = {"acquisition", "acquire", "merger", "buyout", "takeover",
                 "activist", "stake", "bid", "offer", "deal", "spin-off", "spinoff"}
        pos_kw = {"approval", "fda", "patent", "contract", "partnership",
                  "launch", "breakthrough", "record revenue"}
        neg_kw = {"lawsuit", "investigation", "fraud", "recall",
                  "warning", "subpoena", "sec inquiry", "delisting"}

        for article in news:
            pub = article.get("publishedDate", "")[:10]
            if pub < cutoff:
                continue
            title = (article.get("title", "") + " " + article.get("text", "")[:300]).lower()

            if any(kw in title for kw in ma_kw):
                result["score"] += 0.25
                result["flags"].append("M&A/activist activity detected")
                break
            if any(kw in title for kw in pos_kw):
                result["score"] += 0.10
                result["flags"].append("Positive catalyst in news")
            if any(kw in title for kw in neg_kw):
                result["score"] -= 0.15
                result["flags"].append("⚠ Negative event in news")

    # ─── D) Congressional Trading (last 30 days) ──────────────

        pass

    # Clamp and set flags
    result["score"] = min(max(result["score"], 0.0), 1.0)
    result["has_catalyst"] = result["score"] > 0.65
    result["is_risky"] = result["score"] < 0.35

    # Catalyst is evaluated if ANY data source returned something
    # (even if no events found — absence of events IS information)
    result["_evaluated"] = bool(EARNINGS_CAL_CACHE or grades or news)

    return result

# ---------------------------------------------------------------------------
# 12. Transcript Sentiment (Claude API) — EXPENSIVE, pass-2 only
# ---------------------------------------------------------------------------

def get_transcript_sentiment(sym: str) -> dict:
    """Fetch latest earnings transcript and analyze with Claude API.
    
    Caching: results are stored in GCS keyed by {symbol}_{year}_Q{quarter}.
    Transcripts are quarterly — no need to re-analyze on every scan.
    At 30 runs/day × 30 stocks, this saves ~870 API calls/day after first run.
    """
    result = {"sentiment": 0.0, "summary": "", "score": 0.5, "_evaluated": False}

    if not ANTHROPIC_KEY:
        log.info(f"  {sym}: no ANTHROPIC_KEY, skipping transcript")
        return result

    # Get latest transcript
    now = datetime.now()
    year = now.year
    # Try current year quarters from most recent backward
    transcript = None
    transcript_year = None
    transcript_quarter = None
    for q in [4, 3, 2, 1]:
        for y in [year, year - 1]:
            data = fmp("earning-call-transcript", {"symbol": sym, "year": y, "quarter": q})
            if data and data[0].get("content"):
                transcript = data[0]
                transcript_year = y
                transcript_quarter = q
                break
        if transcript:
            break

    if not transcript:
        log.info(f"  {sym}: no transcript found")
        return result

    # ── Cache check: skip Claude API if we already analyzed this transcript ──
    cache_key = f"transcript_cache/{sym}_{transcript_year}_Q{transcript_quarter}.json"
    cached = gcs_download(cache_key)
    if cached and cached.get("_evaluated"):
        log.info(f"  {sym}: transcript cache HIT ({transcript_year} Q{transcript_quarter})")
        return cached

    # ── Cache miss: call Claude API ──
    content = transcript.get("content", "")[:8000]  # limit tokens

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": f"""Analyze this earnings call transcript for {sym}. Return ONLY a JSON object with:
- "sentiment": float from -1.0 (very bearish) to 1.0 (very bullish) based on management tone, guidance, and confidence
- "summary": string, one-sentence key takeaway (max 100 chars)
- "confidence_signals": list of 2-3 specific bullish/bearish signals you detected

Focus on: forward guidance strength, margin commentary, demand trends, management confidence vs hedging language.

Transcript excerpt:
{content}"""}],
            },
            timeout=30,
        )
        if resp.status_code == 200:
            api_data = resp.json()
            text = ""
            for block in api_data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")

            # Parse JSON from response
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            parsed = json.loads(text.strip())
            result["sentiment"] = float(parsed.get("sentiment", 0))
            result["summary"] = parsed.get("summary", "")[:100]
            result["confidence_signals"] = parsed.get("confidence_signals", [])
            # Map -1..1 to 0..1
            result["score"] = min(max((result["sentiment"] + 1) / 2, 0), 1)
            result["_evaluated"] = True
            result["_cached_at"] = now.isoformat()
            result["_transcript_period"] = f"{transcript_year} Q{transcript_quarter}"
            log.info(f"  {sym}: transcript sentiment={result['sentiment']:.2f} ({transcript_year} Q{transcript_quarter})")

            # ── Write to cache ──
            gcs_upload(cache_key, result)
        else:
            log.warning(f"  {sym}: Claude API {resp.status_code} — {resp.text[:120]}")
    except json.JSONDecodeError:
        log.warning(f"  {sym}: failed to parse Claude response")
    except Exception as e:
        log.warning(f"  {sym}: transcript analysis error: {e}")

    return result

# ---------------------------------------------------------------------------
# 13. NEW: Institutional Flows (FMP 13F symbol-positions-summary)
# ---------------------------------------------------------------------------

def get_institutional_flows(sym: str) -> dict:
    """Check institutional ownership changes. Score 0-1.

    v7.2 fix: 13F filings lag 45 days past quarter-end. Starting at CURRENT
    quarter always returns None. The positions-summary endpoint already
    contains QoQ change fields, so we only need ONE quarter's summary.

    Starts one quarter back (most recent that should be reported) and falls
    back further if empty.
    """
    result = {"holders_change": 0.0, "accumulation": 0.0, "score": 0.5, "_evaluated": False}

    now = datetime.now()
    cur_q_raw = (now.month - 1) // 3 + 1
    # Start one full quarter back (filings not yet available for current)
    q = cur_q_raw - 1 if cur_q_raw > 1 else 4
    y = now.year if cur_q_raw > 1 else now.year - 1

    data = fmp("institutional-ownership/symbol-positions-summary",
               {"symbol": sym, "year": y, "quarter": q})

    # If still empty (rare — e.g. very recent quarter still filing), try one more back
    if not data:
        q = q - 1 if q > 1 else 4
        y = y if q != 4 else y - 1
        data = fmp("institutional-ownership/symbol-positions-summary",
                   {"symbol": sym, "year": y, "quarter": q})

    # positions-summary returns a single SUMMARY object per quarter (not a
    # list of holders). Read pre-computed QoQ fields directly.
    if not data or not isinstance(data, list) or not data:
        return result  # non-US or unlisted

    d = data[0]
    # investorsHoldingChange = holder count change QoQ (absolute # of institutions)
    # ownershipPercentChange = institutional share of float change QoQ (percentage points)
    last_holders = float(d.get("lastInvestorsHolding") or 0)
    holders_delta = float(d.get("investorsHoldingChange") or 0)
    result["holders_change"] = (holders_delta / last_holders) if last_holders > 0 else 0.0

    # ownership % change as fractional accumulation proxy
    own_pct_delta = float(d.get("ownershipPercentChange") or 0)  # e.g. 2.85 = +2.85pp
    result["accumulation"] = own_pct_delta / 100.0

    # Score: combine holder-count trend + ownership-% trend
    acc = result["accumulation"]
    hc = result["holders_change"]
    if acc > 0.02 and hc > 0.05:       # broad + concentrated buying
        result["score"] = 1.0
    elif acc > 0.01 or hc > 0.05:
        result["score"] = 0.75
    elif acc > -0.01 and hc > -0.05:
        result["score"] = 0.5
    elif acc < -0.02 or hc < -0.10:
        result["score"] = 0.15
    else:
        result["score"] = 0.3

    result["_evaluated"] = True
    return result

# ---------------------------------------------------------------------------
# 13a. v7.2 NEW: Institutional Flow Factor (13F velocity, US-only)
# ---------------------------------------------------------------------------

def compute_institutional_flow(sym: str) -> dict:
    """Score QoQ flow velocity from 13F positions-summary.

    Distinct from `get_institutional_flows` (the "institutional" factor, 3%) —
    that scores static ownership accumulation. This scores FLOW VELOCITY:
    rate of new positions opening, closing, and ownership-% shifts.

    US-only: positions-summary returns empty for non-US stocks, so we
    gracefully return _evaluated=False and weight redistributes.

    Score components:
      - Net new/closed positions (40%): new - closed, normalized
      - Increased vs reduced positions (25%)
      - Ownership % change (25%): institutions taking more of the float
      - Put/call ratio change (10%, inverse): falling P/C = bullish options
    """
    result = {"score": 0.5, "_evaluated": False,
              "new_positions_change": 0, "closed_positions_change": 0,
              "ownership_pct_change": 0.0, "put_call_delta": 0.0}

    # Use most recent completed quarter (FMP data has ~45-day lag)
    now = datetime.now()
    cur_q = (now.month - 1) // 3 + 1
    target_q = cur_q - 1 if cur_q > 1 else 4
    target_y = now.year if cur_q > 1 else now.year - 1

    # Try current target quarter, fall back one more if empty
    data = fmp("institutional-ownership/symbol-positions-summary",
               {"symbol": sym, "year": target_y, "quarter": target_q})
    if not data:
        target_q = target_q - 1 if target_q > 1 else 4
        target_y = target_y if target_q != 4 else target_y - 1
        data = fmp("institutional-ownership/symbol-positions-summary",
                   {"symbol": sym, "year": target_y, "quarter": target_q})
    if not data or not isinstance(data, list) or not data:
        return result  # US-only or FMP returned empty

    d = data[0]
    # These fields come pre-computed as QoQ changes by FMP
    new_pos_change = float(d.get("newPositionsChange") or 0)
    closed_pos_change = float(d.get("closedPositionsChange") or 0)
    inc_pos_change = float(d.get("increasedPositionsChange") or 0)
    red_pos_change = float(d.get("reducedPositionsChange") or 0)
    own_pct_change = float(d.get("ownershipPercentChange") or 0)
    pc_ratio_change = float(d.get("putCallRatioChange") or 0)

    result["new_positions_change"] = new_pos_change
    result["closed_positions_change"] = closed_pos_change
    result["ownership_pct_change"] = own_pct_change
    result["put_call_delta"] = pc_ratio_change

    # ─── Score components (each 0-1, weighted into composite) ───
    # A) Net position flow: net new openings as fraction of openings
    net_pos = new_pos_change - closed_pos_change
    gross_pos = abs(new_pos_change) + abs(closed_pos_change)
    if gross_pos > 0:
        net_pos_score = 0.5 + 0.5 * max(-1, min(1, net_pos / gross_pos))
    else:
        net_pos_score = 0.5

    # B) Increased vs reduced: same logic
    net_change = inc_pos_change - red_pos_change
    gross_change = abs(inc_pos_change) + abs(red_pos_change)
    if gross_change > 0:
        change_score = 0.5 + 0.5 * max(-1, min(1, net_change / gross_change))
    else:
        change_score = 0.5

    # C) Ownership % change: institutions taking/giving up share of float
    # ±3 percentage points is a strong signal; scale linearly
    own_pct_score = 0.5 + max(-0.5, min(0.5, own_pct_change / 6.0))

    # D) Put/call ratio change (inverse — falling P/C = bullish options)
    # ±0.3 is a strong shift
    pc_score = 0.5 - max(-0.5, min(0.5, pc_ratio_change / 0.6))

    result["score"] = (
        net_pos_score * 0.40 +
        change_score * 0.25 +
        own_pct_score * 0.25 +
        pc_score * 0.10
    )
    result["score"] = max(0.0, min(1.0, result["score"]))
    result["_evaluated"] = True
    return result

# ---------------------------------------------------------------------------
# 13b. v7.2 NEW: Sector Momentum Factor (stock vs sector 60d return)
# ---------------------------------------------------------------------------

def compute_sector_momentum(sym: str, price: float, sma50: float,
                            sma200: float, year_high: float, year_low: float) -> dict:
    """Score stock's 60d momentum relative to its sector average.

    Requires SECTOR_MAP[sym] and SECTOR_PERF_CACHE[sector] to be populated
    (both handled in universe build + preload_sector_performance).

    Score interpretation:
      - Stock outperforms sector by >10%: score → 1.0 (leader)
      - Stock matches sector: score → 0.5 (neutral)
      - Stock lags sector by >10%: score → 0.0 (laggard)
    """
    result = {"score": 0.5, "_evaluated": False,
              "sector": "", "stock_60d": 0.0, "sector_60d": 0.0, "spread": 0.0}

    sector = SECTOR_MAP.get(sym, "")
    if not sector or sector not in SECTOR_PERF_CACHE:
        return result  # sector unknown or not preloaded (EU/Asia stocks)

    # Estimate stock 60d return from SMA50 (close proxy for 60-trading-day avg)
    # We don't have a direct 60d return without fetching history, but since SMA50
    # is already in the quote, using (price - sma50) / sma50 is a good stand-in.
    if sma50 <= 0 or price <= 0:
        return result
    stock_60d_proxy = (price - sma50) / sma50

    sector_60d = SECTOR_PERF_CACHE[sector]
    spread = stock_60d_proxy - sector_60d

    result["sector"] = sector
    result["stock_60d"] = round(stock_60d_proxy, 4)
    result["sector_60d"] = round(sector_60d, 4)
    result["spread"] = round(spread, 4)

    # Map spread to 0-1 score. ±20% spread is extreme; use tanh-like scaling.
    # spread = +0.20 → score ≈ 1.0 (sector leader)
    # spread =  0.00 → score = 0.5 (neutral)
    # spread = -0.20 → score ≈ 0.0 (sector laggard)
    result["score"] = 0.5 + max(-0.5, min(0.5, spread / 0.40))
    result["_evaluated"] = True
    return result

# ---------------------------------------------------------------------------
# 13c. v7.2 NEW: Congressional Trading Factor (Senate + House, US-only)
# ---------------------------------------------------------------------------

def compute_congressional(sym: str) -> dict:
    """Score recent Senate + House trading activity.

    FMP stable REST endpoints: `senate-trades` and `house-trades` (confirmed
    per FMP docs, Apr 2026). Earlier v7.2 used `senate-trading`/`house-trading`
    which returned 404 — fixed. Backtest data treated f_congressional as
    constant 0.5, so live signal is novel.

    Scoring:
      - Net buys > net sells, recent-weighted → bullish (>0.5)
      - Opposite → bearish (<0.5)
      - No recent activity → neutral (0.5), _evaluated=False
    """
    result = {"score": 0.5, "_evaluated": False,
              "net_buys": 0, "net_sells": 0, "days_since_last": -1}

    # Fetch both chambers; combine
    # FMP stable REST endpoints are `senate-trades` and `house-trades` (per FMP docs)
    # — NOT `senate-trading`/`house-trading` which return 404.
    senate = fmp("senate-trades", {"symbol": sym}) or []
    house = fmp("house-trades", {"symbol": sym}) or []
    if not isinstance(senate, list): senate = []
    if not isinstance(house, list): house = []
    all_trades = senate + house
    if not all_trades:
        return result  # no coverage, non-US, or no activity

    # Only count trades in the last 180 days, weight by recency
    today = datetime.now()
    cutoff = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    recent = [t for t in all_trades
              if (t.get("transactionDate") or "") >= cutoff]
    if not recent:
        # Activity exists but nothing recent — treat as no signal but evaluated
        return result

    # Compute days since most recent transaction for optional display
    try:
        latest_date = max(t.get("transactionDate", "") for t in recent)
        result["days_since_last"] = (today - datetime.strptime(latest_date, "%Y-%m-%d")).days
    except (ValueError, TypeError):
        pass

    # Weight each trade by: recency (exponential decay, 90-day half-life)
    # and buy/sell direction. "Purchase" → positive, "Sale"/"Sale (Partial)" → negative.
    bullish_weight = 0.0
    bearish_weight = 0.0
    for t in recent:
        t_date = t.get("transactionDate", "")
        t_type = (t.get("type") or "").lower()
        try:
            days_ago = (today - datetime.strptime(t_date, "%Y-%m-%d")).days
        except (ValueError, TypeError):
            continue
        decay = 0.5 ** (days_ago / 90.0)  # half-life 90 days

        if "purchase" in t_type:
            bullish_weight += decay
            result["net_buys"] += 1
        elif "sale" in t_type:
            bearish_weight += decay
            result["net_sells"] += 1

    total = bullish_weight + bearish_weight
    if total > 0:
        # Score: pure ratio of bullish weight to total weight
        result["score"] = bullish_weight / total
        result["_evaluated"] = True

    return result

# ---------------------------------------------------------------------------
# 14. Composite Score & Signal (v7.2 — honest scoring + composite-band signals)
# ---------------------------------------------------------------------------

ALL_FACTORS = ["technical", "quality", "upside", "proximity", "catalyst",
               "transcript", "institutional", "analyst", "insider", "earnings",
               # v7.2 additions — compute functions pending; return None for now
               "institutional_flow", "sector_momentum", "congressional"]

def compute_composite_v7(
    tech: dict, analyst: dict, value: dict, price: float,
    insider: dict, proximity: dict, earnings: dict,
    upside: dict, quality: dict = None,
    catalyst: dict = None, transcript: dict = None,
    institutional: dict = None,
    institutional_flow: dict = None,
    sector_momentum: dict = None,
    congressional: dict = None,
    weights: dict = None,
) -> tuple:
    """
    13-factor composite (v7.2). Returns (composite, signal, factor_scores, reasons, coverage).

    Factors with no real data are set to None and their weight is redistributed
    to evaluated factors. No free 0.5 for unevaluated factors.

    v7.2 additions (any missing will have weight redistributed):
      - institutional_flow: 13F velocity (US-only, pass-2)
      - sector_momentum: stock return vs sector 60d (requires SECTOR_PERF_CACHE)
      - congressional: Senate + House disclosures (US-only, pass-2)

    Coverage dict: {count, pct, evaluated: [...], missing: [...]}
    """
    base_weights = weights or WEIGHTS

    factors = {}

    # ─── Factor evaluation (None = no real data, weight will be redistributed) ───

    # 1. Technical (35%) — always available (from OHLCV chart)
    factors["technical"] = tech["bull_score"] / 10

    # 2. Quality (14%) — always available (from financial statements)
    if quality and quality.get("score") is not None:
        factors["quality"] = quality["score"]
    else:
        factors["quality"] = None

    # 3. Upside (10%) — available if analyst target OR DCF exists
    if upside.get("_evaluated", False):
        factors["upside"] = upside.get("score", 0)
    else:
        factors["upside"] = None

    # 4. Proximity (8%) — always available (from quote data)
    factors["proximity"] = proximity.get("score", 0.5)

    # 5. Catalyst (8%) — None if no API data returned
    if catalyst and catalyst.get("_evaluated", False):
        factors["catalyst"] = catalyst["score"]
    else:
        factors["catalyst"] = None

    # 6. Transcript (7%) — None if not fetched or Claude API failed
    if transcript and transcript.get("_evaluated", False):
        factors["transcript"] = transcript["score"]
    else:
        factors["transcript"] = None

    # 7. Institutional (5%) — None if not fetched (pass-2 only) or no data
    if institutional and institutional.get("_evaluated", False):
        factors["institutional"] = institutional["score"]
    else:
        factors["institutional"] = None

    # 8. Analyst (5%) — None if no recent grades in last 90 days
    if analyst.get("_grade_evaluated", False):
        factors["analyst"] = analyst["grade_score"]
    else:
        factors["analyst"] = None

    # 9. Insider (4%) — None if FMP returned no insider trade data
    if insider.get("_evaluated", False):
        factors["insider"] = insider["score"]
    else:
        factors["insider"] = None

    # 10. Earnings (4%) — None if no EPS history available
    if earnings.get("_evaluated", False):
        factors["earnings"] = earnings["score"]
    else:
        factors["earnings"] = None

    # ─── v7.2 NEW factors (13-factor composite) ─────────────────────
    # Each compute function sets _evaluated=True if it got real data;
    # otherwise the factor is None and weight redistributes to others.

    # 11. Institutional Flow (9%) — 13F velocity (US-only, pass-2 only)
    if institutional_flow and institutional_flow.get("_evaluated", False):
        factors["institutional_flow"] = institutional_flow["score"]
    else:
        factors["institutional_flow"] = None

    # 12. Sector Momentum (3%) — stock 60d return vs sector average
    if sector_momentum and sector_momentum.get("_evaluated", False):
        factors["sector_momentum"] = sector_momentum["score"]
    else:
        factors["sector_momentum"] = None

    # 13. Congressional (1%) — Senate + House trading (US-only, pass-2 only)
    if congressional and congressional.get("_evaluated", False):
        factors["congressional"] = congressional["score"]
    else:
        factors["congressional"] = None

    # ─── Coverage tracking ───
    evaluated = [f for f in ALL_FACTORS if factors.get(f) is not None]
    missing = [f for f in ALL_FACTORS if factors.get(f) is None]
    coverage = {
        "count": len(evaluated),
        "total": len(ALL_FACTORS),
        "pct": len(evaluated) / len(ALL_FACTORS),
        "evaluated": evaluated,
        "missing": missing,
    }

    # ─── Weight redistribution for missing factors ───
    active_weights = {}
    missing_weight = 0
    for factor, weight in base_weights.items():
        if factors.get(factor) is not None:
            active_weights[factor] = weight
        else:
            missing_weight += weight
            factors[factor] = 0.0  # placeholder (won't affect composite — weight is 0)

    if missing_weight > 0 and active_weights:
        total_active = sum(active_weights.values())
        for factor in active_weights:
            active_weights[factor] += missing_weight * (active_weights[factor] / total_active)
    else:
        active_weights = base_weights.copy()

    # Compute weighted composite (only evaluated factors contribute)
    composite = sum(factors[f] * active_weights.get(f, 0) for f in base_weights
                    if factors.get(f) is not None)

    # Set missing factors to None for frontend (radar chart renders null as dashed/gray)
    # This MUST happen AFTER composite calculation
    for f in missing:
        factors[f] = None

    # Collect reasons
    reasons = []
    if catalyst and catalyst.get("flags"):
        reasons.extend(catalyst["flags"])

    # ─── Signal Classification (v7.1 — composite-band driven) ───────────
    # Backtest proof (15,120 samples, 24 months):
    #   - Composite bands predict outcomes; categorical momentum rules don't
    #   - >0.90: 72% P(+10% 60d) | 0.85-0.90: 53% | 0.75-0.85: 53%
    #   - 0.65-0.75: 44% | <0.65: diminishing returns
    #   - Old v6 BUY/WATCH/HOLD labels all clustered at 56-57% — no differentiation
    # Bearish override remains as safety net for technical breakdowns.

    # Bearish safety net — catches stocks in freefall regardless of fundamentals
    sma50 = tech.get("sma50", 0)
    sma200 = tech.get("sma200", 0)
    price_val = tech.get("price", 0) or value.get("price", 0) or price
    trend_str = (sma50 - sma200) / sma200 if sma200 > 0 else 0
    momentum = (price_val - sma50) / sma50 if sma50 > 0 else 0
    yh = tech.get("year_high", 0)
    yl = tech.get("year_low", 0)
    prox_raw = (price_val - yl) / (yh - yl) if yh > yl > 0 else 0.5
    bull = tech["bull_score"]

    bearish_count = sum([
        trend_str < -0.05,          # downtrend
        momentum < -0.10,           # price well below SMA50
        prox_raw < 0.25,            # near 52wk low
        bull <= 2,                  # no technical support
        composite < 0.30,           # weak composite
    ])

    # ─── Coverage gate: thin-data stocks can't get BUY/STRONG BUY ───
    # Prevents stocks with only 3-4 evaluated factors from inflating via
    # weight redistribution. Requires 7+ factors for full composite range.
    # NOTE: total is 13 in v7.2 but 3 factors have no compute yet → cap is
    # effectively 10 evaluated max; gate still triggers when <7 of 10 have data.
    MIN_COVERAGE_FOR_FULL_SCORE = 7
    COVERAGE_CAP = 0.75  # max composite when coverage < threshold

    if coverage["count"] < MIN_COVERAGE_FOR_FULL_SCORE:
        composite = min(composite, COVERAGE_CAP)
        if composite == COVERAGE_CAP:
            reasons.append(f"COVERAGE CAP: only {coverage['count']}/{coverage['total']} factors evaluated")

    # ─── Signal Classification (v7.2 — tightened thresholds) ────────────
    # Backtest-calibrated P(+10% 60d) by composite band:
    #   ≥0.90: 72% hit | 0.85-0.90: 53% | 0.75-0.85: 44-53% | 0.65-0.75: 43%
    # Old v7.1 thresholds (0.85/0.70/0.55) put the 53%-tier in STRONG BUY,
    # producing 24% STRONG BUY rate. v7.2 reserves STRONG BUY for the
    # genuine 72%-hit tier and compresses intermediate bands accordingly.
    # Bearish override remains as safety net regardless of composite.
    if bearish_count >= 3 or composite < 0.30:
        signal = "SELL"
    elif composite >= 0.90:
        signal = "STRONG BUY"
    elif composite >= 0.80:
        signal = "BUY"
    elif composite >= 0.65:
        signal = "WATCH"
    elif composite >= 0.50:
        signal = "HOLD"
    else:
        signal = "SELL"

    # ─── Catalyst display annotation (NOT a signal override) ───
    has_catalyst = (catalyst or {}).get("has_catalyst", False)
    is_risky = (catalyst or {}).get("is_risky", False)
    if has_catalyst and signal in ("STRONG BUY", "BUY"):
        reasons.append("CATALYST: " + ", ".join((catalyst or {}).get("flags", [])))
    if is_risky and signal in ("STRONG BUY", "BUY", "WATCH"):
        reasons.append("⚠ RISK: " + ", ".join((catalyst or {}).get("flags", [])))

    return composite, signal, factors, reasons, coverage

# ---------------------------------------------------------------------------
# 15. Main Screening Loop (Two-Pass Architecture)
# ---------------------------------------------------------------------------

def screen(symbols: list[str], enrich_top_n: int = ENRICH_TOP_N,
           skip_transcripts: bool = False, min_coverage: int = 0) -> list[Stock]:
    results = []
    total = len(symbols)
    skips = {"quote": 0, "tech": 0}

    log.info(f"Starting v7 screen of {total} symbols")
    log.info(f"Pass 1: Cheap screen (quote + chart + fundamentals + grades + earnings + insiders + quality + catalyst)")

    # ─── Macro Regime (called ONCE, shared across all stocks) ───
    macro = {"regime": "NEUTRAL", "score": 0.5, "features": {}, "tilts": {}}
    active_weights = WEIGHTS.copy()
    if HAS_MACRO:
        try:
            log.info("Fetching macro regime data...")
            macro = fetch_macro_regime(fmp, rate_limit_func=lambda: time.sleep(RATE_LIMIT))
            active_weights = apply_macro_tilt(WEIGHTS, macro)
            log.info(f"Macro: {macro['regime']} (score={macro['score']:.3f}) — weights tilted")
            # Update RISK_FREE dynamically from treasury data
            global RISK_FREE
            rf = get_risk_free_rate(macro.get("rates", {}))
            if rf > 0:
                RISK_FREE = rf
                log.info(f"RISK_FREE updated to {RISK_FREE:.3f} from 10yr treasury")
        except Exception as e:
            log.warning(f"Macro regime fetch failed: {e} — using base weights")
            macro = {"regime": "NEUTRAL", "score": 0.5, "features": {}}
            active_weights = WEIGHTS.copy()

    # Pre-fetch all quotes in batches
    all_quotes = get_quotes_batch(symbols)

    # ═══════════════ PATCHED: PASS 1 with Error Resilience ═══════════════
    pass1_stocks = []

    for i, sym in enumerate(symbols):
        try:
            if (i + 1) % 10 == 0:
                log.info(f"  Pass 1: {i+1}/{total} (passed: {len(pass1_stocks)})")

            # Quote (from batch, fallback to single)
            q = all_quotes.get(sym)
            if not q or q["price"] <= 0:
                skips["quote"] += 1
                continue
            price = q["price"]

            # Technicals (from OHLCV chart)
            t = get_technicals(sym, q)
            if not t:
                skips["tech"] += 1
                continue

            # Analyst (targets + grades + earnings)
            a = get_analyst(sym)
            if a["target"] > 0:
                a["upside"] = (a["target"] - price) / price * 100

            # Skip deep analysis for stocks with no momentum AND no analyst interest
            if t["bull_score"] <= 1 and a["target"] <= 0:
                continue

            # Value / Buffett (FX-aware)
            v = get_value(sym, price, q["currency"])

            # Insider Activity (1 API call)
            ins = get_insider_activity(sym)

            # 52-week proximity (from existing quote data, no API call)
            prox = compute_52wk_proximity(q)

            # Earnings momentum (from existing analyst data, no API call)
            earn = compute_earnings_momentum(a)

            # Upside score (from existing data, no API call)
            ups = compute_upside_score(a, v, price)

            # Catastrophe detector (from existing data, no API call) — kept for display only
            cat = compute_catastrophe(t, v, a, ins)

            # NEW v7: Quality factor (from existing value data, no API call)
            qual = compute_quality_score(v)

            # NEW v7: Catalyst factor (2-3 API calls: earnings-calendar, grades, news, senate)
            cata = compute_catalyst_score(sym, analyst=a)

            # NEW v7.2: Sector momentum (no API call — uses SECTOR_PERF_CACHE + quote data)
            sec_mom = compute_sector_momentum(sym, price, q["sma50"], q["sma200"],
                                              q["year_high"], q["year_low"])

            # Compute pass-1 composite (no transcript, institutional, institutional_flow,
            # or congressional yet — those are pass-2 enrichment)
            composite, signal, factors, reasons, coverage = compute_composite_v7(
                t, a, v, price, ins, prox, earn, ups,
                quality=qual, catalyst=cata,
                transcript=None, institutional=None,
                institutional_flow=None, sector_momentum=sec_mom,
                congressional=None,
                weights=active_weights,
            )

            s = Stock(
                symbol=sym, price=price, currency=q["currency"],
                exchange=SECTOR_EXCHANGE_MAP.get(sym, ""),
                country=COUNTRY_MAP.get(sym, ""),
                sector=SECTOR_MAP.get(sym, ""),
                sma50=q["sma50"], sma200=q["sma200"],
                year_high=q["year_high"], year_low=q["year_low"],
                market_cap=q["market_cap"], volume=q["volume"],
                rsi=t["rsi"], macd_signal=t["macd_signal"], adx=t["adx"],
                bb_pct=t["bb_pct"], stoch_rsi=t["stoch_rsi"], obv_trend=t["obv_trend"],
                bull_score=t["bull_score"],
                target=a["target"], upside=a.get("upside", 0), grade_score=a["grade_score"],
                grade_buy=a["grade_buy"], grade_total=a["grade_total"],
                eps_beats=a["eps_beats"], eps_total=a["eps_total"],
                revenue_cagr_3y=v["revenue_cagr_3y"], eps_cagr_3y=v["eps_cagr_3y"],
                roe_avg=v["roe_avg"], roe_consistent=v["roe_consistent"],
                roic_avg=v["roic_avg"], gross_margin=v["gross_margin"],
                gross_margin_trend=v["gross_margin_trend"],
                piotroski=v["piotroski"], altman_z=v["altman_z"],
                dcf_value=v["dcf_value"], owner_earnings_yield=v["owner_earnings_yield"],
                intrinsic_buffett=v["intrinsic_buffett"], intrinsic_avg=v["intrinsic_avg"],
                margin_of_safety=v["margin_of_safety"], value_score=v["value_score"],
                insider_buy_ratio=ins["buy_ratio"], insider_net_buys=ins["net_buys"],
                insider_score=ins["score"],
                news_sentiment=0.0, news_score=0.0,  # removed from composite, kept for display
                proximity_52wk=prox["proximity"], proximity_score=prox["score"],
                earnings_momentum=earn["momentum"], earnings_score=earn["score"],
                upside_score=ups["score"],
                catastrophe_score=cat["score"],
                quality_score=qual["score"],
                catalyst_score=cata["score"],
                catalyst_flags=cata.get("flags", []),
                has_catalyst=cata.get("has_catalyst", False),
                days_to_earnings=cata.get("days_to_earnings", -1),
                composite=composite, signal=signal,
                classification=v["classification"],
                reasons=t.get("bull_reasons", []) + reasons,
                factor_scores=factors,
                factor_coverage=coverage["count"],
                factor_coverage_pct=coverage["pct"],
                factors_evaluated=coverage["evaluated"],
                factors_missing=coverage["missing"],
            )

            # Stash raw data for pass 2
            s._raw = {"tech": t, "analyst": a, "value": v, "price": price,
                       "insider": ins, "proximity": prox,
                       "earnings": earn, "upside": ups,
                       "quality": qual, "catalyst": cata, "quote": q,
                       "weights": active_weights}

            pass1_stocks.append(s)

        except Exception as e:
            log.warning(f"  {sym}: SKIPPING DUE TO ERROR - {e}")
            skips["tech"] += 1
            continue

    # Sort by pass-1 composite
    pass1_stocks.sort(key=lambda x: x.composite, reverse=True)
    log.info(f"Pass 1 complete: {len(pass1_stocks)} scored | Skipped: {skips}")

    # Coverage stats
    if pass1_stocks:
        avg_cov = sum(s.factor_coverage for s in pass1_stocks) / len(pass1_stocks)
        cov_dist = {}
        for s in pass1_stocks:
            cov_dist[s.factor_coverage] = cov_dist.get(s.factor_coverage, 0) + 1
        log.info(f"  Coverage: avg {avg_cov:.1f}/13 factors | distribution: {dict(sorted(cov_dist.items()))}")

    # Apply minimum coverage filter (default 0 = no filter)
    if min_coverage > 0:
        before = len(pass1_stocks)
        pass1_stocks = [s for s in pass1_stocks if s.factor_coverage >= min_coverage]
        log.info(f"  Coverage filter (>={min_coverage}/13): {before} → {len(pass1_stocks)} stocks")

    # ═══════════════ PASS 2: Expensive Enrichment ═══════════════
    top_n = min(enrich_top_n, len(pass1_stocks))
    log.info(f"Pass 2: Enriching top {top_n} with transcripts + institutional flows")

    for i, s in enumerate(pass1_stocks[:top_n]):
        if (i + 1) % 5 == 0:
            log.info(f"  Pass 2: {i+1}/{top_n}")

        raw = s._raw

        # Transcript sentiment (Claude API)
        if skip_transcripts:
            trans = {"sentiment": 0.0, "summary": "", "score": 0.5}
        else:
            trans = get_transcript_sentiment(s.symbol)
        s.transcript_sentiment = trans["sentiment"]
        s.transcript_summary = trans["summary"]
        s.transcript_score = trans["score"]

        # Institutional flows (2-3 API calls)
        inst = get_institutional_flows(s.symbol)
        s.inst_holders_change = inst["holders_change"]
        s.inst_accumulation = inst["accumulation"]
        s.inst_score = inst["score"]

        # v7.2: Institutional flow velocity (1 API call, US-only)
        inst_flow = compute_institutional_flow(s.symbol)

        # v7.2: Congressional trading (2 API calls: senate + house, US-only)
        cong = compute_congressional(s.symbol)

        # v7.2: re-evaluate sector_momentum (quote data may have been enriched
        # during pass 2; this is free since SECTOR_PERF_CACHE is in memory)
        sec_mom = compute_sector_momentum(s.symbol, raw["price"],
                                          raw["tech"].get("sma50", 0),
                                          raw["tech"].get("sma200", 0),
                                          raw["tech"].get("year_high", 0),
                                          raw["tech"].get("year_low", 0))

        # Recompute composite with all factors (13 total)
        composite, signal, factors, reasons, coverage = compute_composite_v7(
            raw["tech"], raw["analyst"], raw["value"], raw["price"],
            raw["insider"], raw["proximity"],
            raw["earnings"], raw["upside"],
            quality=raw["quality"], catalyst=raw["catalyst"],
            transcript=trans, institutional=inst,
            institutional_flow=inst_flow, sector_momentum=sec_mom,
            congressional=cong,
            weights=raw["weights"],
        )

        s.composite = composite
        s.signal = signal
        s.factor_scores = factors
        s.reasons = raw["tech"].get("bull_reasons", []) + reasons
        s.factor_coverage = coverage["count"]
        s.factor_coverage_pct = coverage["pct"]
        s.factors_evaluated = coverage["evaluated"]
        s.factors_missing = coverage["missing"]

    # Clean up raw data
    for s in pass1_stocks:
        if hasattr(s, '_raw'):
            del s._raw

    # Re-sort after pass 2
    pass1_stocks.sort(key=lambda x: x.composite, reverse=True)

    # ═══════════════ ML PROBABILITY PREDICTION ═══════════════
    if HAS_ML_MODEL:
        log.info("Running ML probability predictions...")
        for s in pass1_stocks:
            s.hit_prob = predict_hit_prob(s)
        top_probs = [(s.symbol, s.hit_prob) for s in pass1_stocks[:5]]
        log.info(f"  Top 5 hit_prob: {top_probs}")

    log.info(f"Screen complete: {len(pass1_stocks)} total scored")

    return pass1_stocks, macro

# ---------------------------------------------------------------------------
# 16. Report Formatting
# ---------------------------------------------------------------------------

def format_report(stocks: list[Stock], region: str, macro: dict = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"{'='*100}",
        f"  STOCK SCREENER v7.2 — {region.upper()} — {now}",
        f"  13-Factor Honest Scoring + Composite-Band Signals (45K-sample ML backtest, 2022-2025)",
        f"  Tech 25% | Upside 14% | Quality 12% | Proximity 12% | InstFlow 9%* | Transcript 6%",
        f"  Earnings 5% | Catalyst 5% | Institutional 3% | SectorMom 3%* | Analyst 3% | Insider 2% | Congressional 1%*",
        f"  Signals: STRONG BUY ≥0.90 | BUY ≥0.80 | WATCH ≥0.65 | HOLD ≥0.50 | SELL <0.50",
        f"  (* compute functions pending — weight redistributes to evaluated factors)",
    ]
    if macro and macro.get("regime"):
        r = macro
        lines.append(f"  Macro: {r['regime']} (score={r['score']:.3f}) — "
                     f"Curve={r.get('sub_scores',{}).get('yield_curve','?'):.2f} "
                     f"VIX={r.get('sub_scores',{}).get('vix','?'):.2f} "
                     f"CPI={r.get('sub_scores',{}).get('cpi_trend','?'):.2f} "
                     f"GDP={r.get('sub_scores',{}).get('gdp_momentum','?'):.2f}")
    lines.append(f"{'='*100}\n")

    for signal_group in ["STRONG BUY", "BUY", "WATCH", "HOLD", "SELL"]:
        group = [s for s in stocks if s.signal == signal_group]
        if not group:
            continue
        emoji = {"STRONG BUY": "🟣", "BUY": "🟢", "WATCH": "🟠", "HOLD": "🟡", "SELL": "🔴"}[signal_group]
        lines.append(f"  {emoji} {signal_group} ({len(group)} stocks)")
        lines.append(f"  {'─'*95}")

        for s in group[:TOP_N]:
            cov_str = f"[{s.factor_coverage}/13 factors]"
            lines.append(f"\n  {s.symbol:<12} {s.currency} {s.price:>8.2f}  │  Composite: {s.composite:.3f}  │  {s.classification}  │  {cov_str}")

            # Factor breakdown (v7.2 — show all 13 factors, mark missing with —)
            fs = s.factor_scores
            if fs:
                # Short abbreviations so the line wraps cleanly on mobile
                ABBR = {
                    "technical": "techn", "quality": "quali", "upside": "upsid",
                    "proximity": "proxi", "catalyst": "catal", "transcript": "trans",
                    "institutional": "instS", "institutional_flow": "instF",
                    "analyst": "analy", "insider": "insid", "earnings": "earni",
                    "sector_momentum": "secMm", "congressional": "congr",
                }
                factor_strs = []
                for f in ALL_FACTORS:
                    val = fs.get(f, 0.0)
                    abbr = ABBR.get(f, f[:5])
                    if f in s.factors_evaluated:
                        factor_strs.append(f"{abbr}:{val:.2f}")
                    else:
                        factor_strs.append(f"{abbr}:  — ")
                # Wrap 5 per line for readability on mobile
                for i in range(0, len(factor_strs), 5):
                    prefix = "    Factors:   " if i == 0 else "               "
                    lines.append(f"{prefix} {' | '.join(factor_strs[i:i+5])}")
            if s.factors_missing:
                lines.append(f"    Missing:    {', '.join(s.factors_missing)}")

            lines.append(f"    Technical:  Bull {s.bull_score}/10  RSI {s.rsi:.0f}  MACD {s.macd_signal}  ADX {s.adx:.0f}")
            lines.append(f"    Value:      MoS {s.margin_of_safety:+.0%}  ROE {s.roe_avg:.0%}  GM {s.gross_margin:.0%}({s.gross_margin_trend})")
            lines.append(f"                Piotroski {s.piotroski}/9  Altman {s.altman_z:.1f}  RevCAGR {s.revenue_cagr_3y:.0%}  EPSCAGR {s.eps_cagr_3y:.0%}")

            iv_str = f"DCF ${s.dcf_value:.0f}" if s.dcf_value else "N/A"
            buf_str = f"Buffett ${s.intrinsic_buffett:.0f}" if s.intrinsic_buffett else "N/A"
            oe_str = f"OE Yield {s.owner_earnings_yield:.1%}" if s.owner_earnings_yield else "N/A"
            lines.append(f"                Intrinsic: {iv_str} | {buf_str} | {oe_str}")

            lines.append(f"    Analyst:    Target ${s.target:.0f} ({s.upside:+.1f}%)  Grades {s.grade_buy}/{s.grade_total} buy  EPS {s.eps_beats}/{s.eps_total} beats")
            lines.append(f"    Insider:    Buy ratio {s.insider_buy_ratio:.2f}  Net buys: {s.insider_net_buys}  Score: {s.insider_score:.2f}")
            lines.append(f"    Quality:    Score {s.quality_score:.2f}  │  52wk: {s.proximity_52wk:.0%}")

            # v7: Catalyst info
            if s.catalyst_flags:
                lines.append(f"    Catalyst:   Score {s.catalyst_score:.2f} — {', '.join(s.catalyst_flags[:4])}")
            elif s.days_to_earnings >= 0:
                lines.append(f"    Catalyst:   Score {s.catalyst_score:.2f} — Earnings in {s.days_to_earnings}d")

            if s.transcript_summary:
                lines.append(f"    Transcript: {s.transcript_sentiment:+.2f} — {s.transcript_summary}")

            if s.reasons:
                lines.append(f"    Signals:    {', '.join(s.reasons[:8])}")
        lines.append("")

    buy_count = sum(1 for s in stocks if s.signal == "BUY")
    strong_buy_count = sum(1 for s in stocks if s.signal == "STRONG BUY")
    watch_count = sum(1 for s in stocks if s.signal == "WATCH")
    avg_cov = sum(s.factor_coverage for s in stocks) / len(stocks) if stocks else 0
    full_cov = sum(1 for s in stocks if s.factor_coverage >= 8)
    lines.append(f"  SUMMARY: {len(stocks)} screened → {strong_buy_count} STRONG BUY, {buy_count} BUY, {watch_count} WATCH")
    lines.append(f"  Coverage: avg {avg_cov:.1f}/13 factors | {full_cov} stocks with 8+ factors")
    if stocks:
        lines.append(f"  Top composite: {stocks[0].symbol} ({stocks[0].composite:.3f}, {stocks[0].factor_coverage}/13 factors)")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 17. Email
# ---------------------------------------------------------------------------

def send_email(subject: str, body: str):
    if not SMTP_USER or not SMTP_PASS:
        log.warning("Email creds not configured — skipping.")
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = EMAIL_TO
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        log.info(f"Email sent to {EMAIL_TO}")
    except Exception as e:
        log.warning(f"Email failed: {e}")

# ---------------------------------------------------------------------------
# 18. Signal History + GCS
# ---------------------------------------------------------------------------

def load_signals() -> dict:
    try:
        with open(SIGNAL_LOG) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")

def gcs_upload(path: str, data: dict):
    try:
        tok_resp = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=3
        )
        token = tok_resp.json().get("access_token", "")
        if not token:
            log.warning("GCS: no access token from metadata")
            return
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o"
        r = requests.post(url, params={"uploadType": "media", "name": path},
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                          data=json.dumps(data, default=str), timeout=15)
        if r.status_code in (200, 201):
            log.info(f"GCS: uploaded {path}")
        else:
            log.warning(f"GCS: {r.status_code} uploading {path} → {r.text[:100]}")
    except Exception as e:
        log.warning(f"GCS: {e}")

def gcs_download(path: str) -> Optional[dict]:
    """Download a JSON object from GCS. Returns None on any failure."""
    try:
        tok_resp = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=3
        )
        token = tok_resp.json().get("access_token", "")
        if not token:
            return None
        import urllib.parse
        encoded_path = urllib.parse.quote(path, safe="")
        url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET}/o/{encoded_path}?alt=media"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def save_scan_to_gcs(stocks: list, region: str, macro: dict = None):
    today = datetime.now().strftime("%Y-%m-%d")
    avg_cov = sum(s.factor_coverage for s in stocks) / len(stocks) if stocks else 0
    payload = {
        "scan_date": datetime.now().isoformat(),
        "region": region,
        "version": "v7.2",
        "weights": WEIGHTS,
        "macro": {
            "regime": (macro or {}).get("regime", "NEUTRAL"),
            "score": (macro or {}).get("score", 0.5),
            "sub_scores": (macro or {}).get("sub_scores", {}),
            "features": (macro or {}).get("features", {}),
        },
        "summary": {
            "total": len(stocks),
            "strong_buy": sum(1 for s in stocks if s.signal == "STRONG BUY"),
            "buy": sum(1 for s in stocks if s.signal == "BUY"),
            "watch": sum(1 for s in stocks if s.signal == "WATCH"),
            "hold": sum(1 for s in stocks if s.signal == "HOLD"),
            "sell": sum(1 for s in stocks if s.signal == "SELL"),
            "avg_factor_coverage": round(avg_cov, 1),
            "full_coverage_count": sum(1 for s in stocks if s.factor_coverage >= 8),
        },
        "stocks": [asdict(s) for s in stocks],
    }
    gcs_upload(f"scans/latest_{region}.json", payload)
    gcs_upload(f"scans/{today}_{region}.json", payload)
    gcs_upload("scans/latest.json", payload)
def save_signals(data: dict):
    with open(SIGNAL_LOG, "w") as f:
        json.dump(data, f, indent=2)

def update_signal_history(stocks: list[Stock]):
    history = load_signals()
    today = datetime.now().strftime("%Y-%m-%d")
    for s in stocks:
        key = s.symbol
        if key not in history:
            history[key] = {"entries": []}
        history[key]["entries"].append({
            "date": today, "price": s.price, "signal": s.signal,
            "composite": round(s.composite, 3), "bull": s.bull_score,
            "mos": round(s.margin_of_safety, 3),
            "insider": round(s.insider_score, 2),
            "transcript": round(s.transcript_score, 2),
            "quality": round(s.quality_score, 2),
            "catalyst": round(s.catalyst_score, 2),
            "target": s.target,
            "coverage": s.factor_coverage,
        })
        history[key]["entries"] = history[key]["entries"][-60:]
    save_signals(history)

# ---------------------------------------------------------------------------
# 19. Portfolio Monitor (v7 — daily re-scoring of held positions)
# ---------------------------------------------------------------------------

def load_portfolio_state() -> dict:
    """Load portfolio state from local file or GCS."""
    try:
        with open(PORTFOLIO_STATE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"positions": [], "history": []}

def save_portfolio_state(state: dict):
    with open(PORTFOLIO_STATE, "w") as f:
        json.dump(state, f, indent=2, default=str)
    # Also upload to GCS
    gcs_upload("portfolio/state.json", state)

def monitor_portfolio(skip_transcripts: bool = True) -> str:
    """
    Re-score all held positions. Called daily at market close.
    Returns formatted alert report.
    """
    state = load_portfolio_state()
    positions = state.get("positions", [])

    if not positions:
        log.info("No portfolio positions to monitor.")
        return "No positions."

    syms = [p["symbol"] for p in positions]
    log.info(f"Monitoring {len(syms)} positions: {', '.join(syms)}")

    # Get fresh quotes
    quotes = get_quotes_batch(syms)
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    actions = []

    for pos in positions:
        sym = pos["symbol"]
        q = quotes.get(sym)
        if not q or q["price"] <= 0:
            actions.append({"symbol": sym, "action": "ERROR", "reason": "No quote data"})
            continue

        price = q["price"]
        entry_price = pos.get("entry_price", price)
        entry_comp = pos.get("entry_composite", 0.5)
        entry_signal = pos.get("entry_signal", "BUY")
        entry_date = pos.get("entry_date", today_str)
        peak_price = pos.get("peak_price", price)

        # Compute fresh scores
        t = get_technicals(sym, q)
        if not t:
            actions.append({"symbol": sym, "action": "ERROR", "reason": "No chart data"})
            continue

        a = get_analyst(sym)
        if a["target"] > 0:
            a["upside"] = (a["target"] - price) / price * 100
        v = get_value(sym, price, q["currency"])
        ins = get_insider_activity(sym)
        prox = compute_52wk_proximity(q)
        earn = compute_earnings_momentum(a)
        ups = compute_upside_score(a, v, price)
        qual = compute_quality_score(v)
        cata = compute_catalyst_score(sym, analyst=a)

        # v7.2: full 13-factor scoring for held positions
        sec_mom = compute_sector_momentum(sym, price, q["sma50"], q["sma200"],
                                          q["year_high"], q["year_low"])
        inst_flow = compute_institutional_flow(sym)
        cong = compute_congressional(sym)

        composite, signal, factors, reasons, coverage = compute_composite_v7(
            t, a, v, price, ins, prox, earn, ups,
            quality=qual, catalyst=cata,
            institutional_flow=inst_flow, sector_momentum=sec_mom,
            congressional=cong,
        )

        # ─── Decision Rules ───
        price_change = (price - entry_price) / entry_price
        comp_change = (composite - entry_comp) / entry_comp if entry_comp > 0 else 0
        try:
            days_held = (today - datetime.strptime(entry_date, "%Y-%m-%d")).days
        except:
            days_held = 0

        action = "HOLD"
        urgency = "normal"
        action_reasons = []

        # RULE 1: Signal downgrade
        buy_signals = {"STRONG BUY", "BUY"}
        if entry_signal in buy_signals and signal in ("HOLD", "SELL"):
            action = "SELL"
            urgency = "high"
            action_reasons.append(f"Signal downgrade: {entry_signal} → {signal}")

        # RULE 2: Composite decay > 20%
        if comp_change < -0.20:
            action = "TRIM" if action != "SELL" else "SELL"
            urgency = "high"
            action_reasons.append(f"Composite decay: {entry_comp:.3f} → {composite:.3f} ({comp_change:+.0%})")

        # RULE 3: Stop-loss at -15%
        if price_change < -0.15:
            action = "SELL"
            urgency = "critical"
            action_reasons.append(f"Stop-loss: {price_change:+.1%} from entry ${entry_price:.2f}")

        # RULE 4: Trailing stop — gave back >50% of gains from peak
        if peak_price > entry_price:
            gain_from_entry = (peak_price - entry_price) / entry_price
            current_from_peak = (price - peak_price) / peak_price
            if gain_from_entry > 0.15 and current_from_peak < -0.10:
                if action == "HOLD":
                    action = "TRIM"
                action_reasons.append(f"Trailing stop: peak ${peak_price:.2f}, now {current_from_peak:+.0%} from peak")

        # RULE 5: Catalyst warning
        if cata.get("is_risky") and action == "HOLD":
            action = "TRIM"
            urgency = "medium"
            action_reasons.append(f"Catalyst warning: {', '.join(cata.get('flags', []))}")

        # RULE 6: Catalyst override (strong catalyst can save a dip)
        if cata.get("has_catalyst") and signal in ("BUY", "WATCH", "STRONG BUY"):
            if action in ("TRIM", "SELL") and comp_change > -0.30:
                action = "HOLD"
                action_reasons.append(f"Catalyst override: {', '.join(cata.get('flags', []))}")

        # RULE 7: Time decay
        if days_held > 90 and signal not in ("BUY", "STRONG BUY"):
            if action == "HOLD":
                action = "TRIM"
            action_reasons.append(f"Time decay: held {days_held}d, signal now {signal}")

        # RULE 8: Composite improving → ADD
        if comp_change > 0.15 and signal in ("BUY", "STRONG BUY") and price_change < 0.05:
            action = "ADD"
            action_reasons.append(f"Composite improving: {entry_comp:.3f} → {composite:.3f}")

        # Update peak price
        if price > peak_price:
            pos["peak_price"] = price

        # Update last monitor data
        pos["last_monitor"] = today_str
        pos["last_composite"] = round(composite, 3)
        pos["last_signal"] = signal

        actions.append({
            "symbol": sym,
            "action": action,
            "urgency": urgency,
            "current_price": price,
            "entry_price": entry_price,
            "pnl_pct": round(price_change * 100, 1),
            "entry_composite": entry_comp,
            "current_composite": round(composite, 3),
            "comp_change_pct": round(comp_change * 100, 1),
            "current_signal": signal,
            "days_held": days_held,
            "catalyst_score": round(cata.get("score", 0.5), 2),
            "catalyst_flags": cata.get("flags", []),
            "reasons": action_reasons,
        })

    # Save updated state
    save_portfolio_state(state)

    # Upload monitor results to GCS
    gcs_upload("portfolio/monitor.json", {
        "date": today_str, "actions": actions,
    })

    # Format alert report
    lines = [
        f"{'='*80}",
        f"  PORTFOLIO MONITOR — {today_str}",
        f"{'='*80}",
    ]

    for action_type in ["SELL", "TRIM", "ADD", "HOLD", "ERROR"]:
        group = [a for a in actions if a["action"] == action_type]
        if not group:
            continue
        emoji = {"SELL": "🔴", "TRIM": "🟡", "ADD": "⬆️", "HOLD": "🟢", "ERROR": "⚠️"}[action_type]
        lines.append(f"\n  {emoji} {action_type} ({len(group)}):")
        for a in group:
            lines.append(f"    {a['symbol']:<8} ${a['current_price']:>8.2f}  PnL: {a['pnl_pct']:>+6.1f}%  Comp: {a['current_composite']:.3f} ({a['comp_change_pct']:+.0f}%)  Signal: {a['current_signal']}")
            if a.get("reasons"):
                for r in a["reasons"]:
                    lines.append(f"      → {r}")

    # Summary
    total_pnl = sum(a["pnl_pct"] for a in actions if a.get("pnl_pct")) / len(actions) if actions else 0
    sells = sum(1 for a in actions if a["action"] == "SELL")
    trims = sum(1 for a in actions if a["action"] == "TRIM")
    adds = sum(1 for a in actions if a["action"] == "ADD")

    lines.append(f"\n  Summary: {len(actions)} positions | Avg PnL: {total_pnl:+.1f}%")
    if sells: lines.append(f"  ⚠️  {sells} SELL signal(s) — action required!")
    if trims: lines.append(f"  ⚠️  {trims} TRIM signal(s) — consider reducing")
    if adds: lines.append(f"  ⬆️  {adds} ADD signal(s) — consider increasing")

    report = "\n".join(lines)
    print(report)
    return report

# ---------------------------------------------------------------------------
# 20. Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stock Screener v7")
    parser.add_argument("--region", default=os.environ.get("SCREEN_INDEX", "global"),
                        help="Region: nasdaq100, sp500, europe, global (default)")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols")
    parser.add_argument("--top", type=int, default=TOP_N)
    parser.add_argument("--enrich", type=int, default=ENRICH_TOP_N,
                        help="How many top stocks get transcript/institutional enrichment")
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--no-transcripts", action="store_true",
                        help="Skip Claude API transcript analysis")
    parser.add_argument("--min-coverage", type=int, default=0,
                        help="Minimum factor coverage (0-10). E.g., 6 = only stocks scored on 6+ factors")
    parser.add_argument("--monitor", action="store_true",
                        help="Portfolio monitor mode: re-score held positions")
    args = parser.parse_args()

    if not FMP_KEY:
        log.error("FMP_API_KEY not set!")
        sys.exit(1)

    # ─── Monitor Mode ───
    if args.monitor:
        log.info("Running in PORTFOLIO MONITOR mode")
        report = monitor_portfolio(skip_transcripts=args.no_transcripts)
        today = datetime.now().strftime("%Y-%m-%d")
        if args.email or SMTP_USER:
            # Only email if there are non-HOLD actions
            if any(word in report for word in ["SELL", "TRIM", "ADD"]):
                send_email(f"⚠️ Portfolio Alert — {today}", report)
        return report

    # ─── Screen Mode (default) ───
    enrich_count = args.enrich
    skip_transcripts = args.no_transcripts
    min_cov = args.min_coverage

    # Get symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_symbols(args.region)

    if not symbols:
        log.error("No symbols to screen!")
        return "No symbols found."

    # v7.2: preload sector performance cache — populates SECTOR_PERF_CACHE
    # for compute_sector_momentum. Requires SECTOR_MAP (populated by get_symbols
    # or, when --symbols is used, populated lazily during pass 1 via quote lookups).
    # If --symbols was used, skip the preload (sector_momentum will degrade to
    # neutral _evaluated=False for those custom symbols, which is correct).
    if not args.symbols and SECTOR_MAP:
        preload_sector_performance(days=60)

    # Screen
    results, macro = screen(symbols, enrich_top_n=enrich_count,
                            skip_transcripts=skip_transcripts,
                            min_coverage=min_cov)

    # Report
    report = format_report(results[:args.top * 3], args.region, macro=macro)
    print(report)

    # Save signals
    update_signal_history(results)

    # Save to GCS (include macro metadata)
    save_scan_to_gcs(results, args.region, macro=macro)

    # Email
    today = datetime.now().strftime("%Y-%m-%d")
    if args.email or SMTP_USER:
        send_email(f"Screener v7: {args.region.upper()} — {today}", report)

    return report

if __name__ == "__main__":
    main()
