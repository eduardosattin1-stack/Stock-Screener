#!/usr/bin/env python3
"""
Stock Screener v7.2 — 13-Factor Honest Scoring + Composite-Band Signals (Pipeline Tested)
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
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Optional

import requests
from themes_map import get_modern_theme

# v1.3.0: FMP fundamentals cache (read-through GCS cache for slow-cadence data)
try:
    from fmp_cache import cached_fmp, reset_stats as _cache_reset, log_stats as _cache_log
    HAS_FMP_CACHE = True
except ImportError:
    HAS_FMP_CACHE = False
    def cached_fmp(endpoint, symbol, fetcher, **kw): return fetcher()
    def _cache_reset(): pass
    def _cache_log(): pass

# v7.2.1: Massive options enrichment
try:
    from massive_options import enrich_stock as options_enrich_stock
    OPTIONS_AVAILABLE = True
    import logging as _options_log
    _options_log.getLogger(__name__).info("Massive options module imported — enrichment enabled")
except Exception as _options_e:
    options_enrich_stock = None
    OPTIONS_AVAILABLE = False
    import logging as _options_log
    _options_log.getLogger(__name__).warning(
        f"Massive options module FAILED to import — enrichment disabled. Error: {_options_e}"
    )

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

# Apr 2026: hard filter on stocks with insufficient annual statement history.
# Bruno's call — drop any stock where len(income-statement) < MIN_YEARS_HISTORY.
# Loses recent IPOs (CRWD 2019, SNOW 2020, RBLX 2021, ARM 2023, RDDT 2024) and
# spin-offs (KVUE, GEHC, SOLV) but ensures every scored stock has a full 5-year
# history for growth CAGR, BVPS projection, ROE consistency, and quality scoring.
MIN_YEARS_HISTORY = 5

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

# ─── v8 Composite (Apr 2026) ────────────────────────────────────────────────
# Five-factor structure replacing the 13-factor v7 composite. Designed to
# answer Bruno's original five-factor brief: simplify, add net & FCF margin
# scoring, add growth rates, add valuation explicitly, fold smart-money flows.
# Mode-aware: same weights, but "momentum" factor swaps between bull_score
# (Momentum mode) and reversal_score (Fallen Angel mode).
WEIGHTS_V8 = {
    "momentum":    0.25,  # bull_score / reversal_score depending on mode
    "quality":     0.20,  # net margin 35% + FCF margin 35% + ROIC 30%
    "growth":      0.20,  # rev + EPS + FCF, each 60/40 TTM/3yr
    "value":       0.20,  # intrinsic upside 40% + P/FCF 30% + earnings yield 30%
    "smart_money": 0.15,  # Smart Money Score (LTR-derived 6-factor, Apr 2026)
}
# Sum = 1.00. Piotroski + Altman Z dropped from composite (visible on dashboard
# only — see compute_quality_v8). DCF + intrinsic_buffett dropped from value
# (kept on Stock dict for display but not in composite). Coverage gate retained.
#
# Apr 2026: smart_money sub-factor now sourced from compute_smart_money_score()
# (the LTR-derived 6-factor heuristic). Replaces the previous fold of
# institutional_flow + analyst + insider + transcript + earnings + congressional
# which the LTR investigation showed had little predictive power beyond the 6
# core factors that compute_smart_money_score weights.

# Threshold ladders for absolute scoring (Bruno spec: absolute, not sector-relative)
def _ladder(value, thresholds, scores):
    """Return score from a sorted threshold ladder. thresholds and scores
    must be the same length; thresholds in ascending order. Falls below the
    lowest threshold → 0.0; above the highest → top score."""
    if value is None or not isinstance(value, (int, float)):
        return 0.0
    for t, s in zip(thresholds, scores):
        if value < t:
            return s
    return scores[-1]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v7")

# Macro regime overlay — tilts weights based on yield curve, VIX, CPI, GDP
try:
    from macro_regime import fetch_macro_regime, fetch_macro_regime_v8, apply_macro_tilt, get_risk_free_rate
    HAS_MACRO = True
    log.info("Macro regime module loaded")
except ImportError:
    HAS_MACRO = False
    log.info("macro_regime.py not found — running without macro overlay")

HAS_ML_MODEL = False
ML_MODEL_VERSION = None  # "v3" or "v2"
ML_MODELS = None
ML_CALIBRATOR = None
ML_FEATURES = None
ML_MEDIANS = None
# v3 multi-target model dicts (None when running v2)
ML_MODELS_V3 = None
ML_CALIBRATORS_V3 = None
try:
    import joblib
    import numpy as np
    _ml_dir = os.path.dirname(os.path.abspath(__file__))
    model_path_v3 = os.path.join(_ml_dir, "time_model_v3.pkl")
    model_path_v2 = os.path.join(_ml_dir, "time_model_v2.pkl")
    if os.path.exists(model_path_v3):
        model_data = joblib.load(model_path_v3)
        ML_MODELS = model_data["models"]          # backward-compat: 3-model list
        ML_CALIBRATOR = model_data["calibrator"]   # backward-compat
        ML_FEATURES = model_data["features"]
        ML_MEDIANS = model_data["medians"]
        ML_MODELS_V3 = model_data.get("models_v3", {})
        ML_CALIBRATORS_V3 = model_data.get("calibrators_v3", {})
        ML_MODEL_VERSION = "v3"
        HAS_ML_MODEL = True
        log.info(f"ML v3 loaded: {len(ML_FEATURES)} features, "
                 f"{len(ML_MODELS_V3)} sub-models, "
                 f"OOS AUC={model_data.get('oos_auc','?')}")
    elif os.path.exists(model_path_v2):
        model_data = joblib.load(model_path_v2)
        ML_MODELS = model_data["models"]
        ML_CALIBRATOR = model_data["calibrator"]
        ML_FEATURES = model_data["features"]
        ML_MEDIANS = model_data["medians"]
        ML_MODEL_VERSION = "v2"
        HAS_ML_MODEL = True
        log.info(f"ML v2 loaded: {len(ML_FEATURES)} features, {len(ML_MODELS)} models, "
                 f"target={model_data.get('target','?')}, OOS AUC={model_data.get('oos_auc','?')}")
    else:
        log.info("time_model_v3/v2.pkl not found — hit_prob will be 0")
except ImportError as _ie:
    log.warning(f"ML model disabled — ImportError loading: {_ie}")
except Exception as e:
    log.warning(f"ML model load failed: {type(e).__name__}: {e}")


def _build_ml_feature_vector(stock) -> Optional[np.ndarray]:
    """Build feature vector from a Stock object for ML prediction.
    Returns None if model unavailable."""
    if not HAS_ML_MODEL or ML_FEATURES is None:
        return None
    try:
        factors = stock.factor_scores if hasattr(stock, 'factor_scores') else {}
        row = {}

        # Technical features from factor_scores
        tech_map = {
            "f_momentum_20d": "momentum_20d",
            "f_trend_strength": "trend_strength",
            "f_rsi": "rsi",
            "f_prox_raw": "prox_raw",
            "f_quality": "quality",
            "f_upside": "upside",
            "f_analyst": "analyst",
            "f_sector_momentum": "sector_momentum",
            "f_institutional_flow": "institutional_flow",
            "f_insider": "insider",
            "f_catalyst": "catalyst",
            "f_earnings": "earnings",
            "f_bull_score_raw": "bull_score_raw",
        }
        for feat_name, factor_key in tech_map.items():
            row[feat_name] = factors.get(factor_key)

        # Fundamental features
        fund = getattr(stock, '_fund_features', {})
        for k, v in fund.items():
            row[k] = v

        # Options features (from Massive enrichment, live at inference)
        row["opt_atm_iv"] = getattr(stock, 'options_iv_current', None) or 0.0
        row["opt_skew_25d"] = getattr(stock, 'options_skew_25d', None) or 0.0
        row["opt_total_oi"] = getattr(stock, 'options_total_open_interest', None) or 0.0
        row["opt_volume_to_oi"] = 0.0  # not available live; uses median fill
        row["opt_net_gamma"] = 0.0     # not available live; uses median fill
        row["opt_atm_vega"] = 0.0
        row["opt_atm_theta"] = 0.0

        # Engineered features
        rsi = row.get("f_rsi")
        mom = row.get("f_momentum_20d")
        roe = row.get("f_roe")
        pb = row.get("f_pb")
        rev_g = row.get("f_rev_growth")
        quality = row.get("f_quality")
        prox = row.get("f_prox_raw")

        if rsi is not None and quality is not None:
            row["f_rsi_x_quality"] = (100 - rsi) / 100 * quality
        if rsi is not None and rev_g is not None:
            row["f_rsi_x_revgrow"] = (100 - rsi) / 100 * min(rev_g, 2.0)
        if roe is not None and pb is not None and pb > 0:
            row["f_roe_over_pb"] = roe / pb
        if mom is not None:
            row["f_momentum_abs"] = abs(mom)
        if prox is not None:
            row["f_drawdown"] = 1.0 - prox

        # Build numpy vector in feature order
        vec = []
        for f in ML_FEATURES:
            val = row.get(f)
            if val is None:
                val = ML_MEDIANS.get(f, 0)
            vec.append(float(val))

        X = np.array([vec], dtype=np.float32)
        X = np.clip(X, -100, 100)
        return X
    except Exception as e:
        log.debug(f"ML feature build failed for {getattr(stock, 'symbol', '?')}: {e}")
        return None


def predict_hit_prob(stock) -> float:
    """Predict P(+20% daily high in 4 weeks) — backward-compatible single float.
    Uses v3 clf_20pct_30d if available, else v2 ensemble. Returns 0.0 if unavailable."""
    if not HAS_ML_MODEL or ML_MODELS is None:
        return 0.0
    try:
        X = _build_ml_feature_vector(stock)
        if X is None:
            return 0.0

        probs = [m.predict_proba(X)[0, 1] for m in ML_MODELS]
        raw_prob = sum(probs) / len(probs)

        if ML_CALIBRATOR is not None:
            calibrated = ML_CALIBRATOR.predict([raw_prob])[0]
            return round(float(calibrated), 4)
        return round(float(raw_prob), 4)
    except Exception as e:
        log.debug(f"ML predict failed for {getattr(stock, 'symbol', '?')}: {e}")
        return 0.0


def predict_time_model_v3(stock) -> dict:
    """Predict all v3 targets: P(touch +10/20%) at 30/60d + max drawdown.
    Returns dict with all predictions, or empty dict if v3 model unavailable."""
    result = {
        "hit_10pct_30d": 0.0,
        "hit_10pct_60d": 0.0,
        "hit_20pct_30d": 0.0,
        "hit_20pct_60d": 0.0,
        "expected_dd_30d": 0.0,
        "expected_dd_60d": 0.0,
    }
    if ML_MODEL_VERSION != "v3" or not ML_MODELS_V3:
        return result
    try:
        X = _build_ml_feature_vector(stock)
        if X is None:
            return result

        # Classification targets
        for key in ["clf_10pct_30d", "clf_10pct_60d", "clf_20pct_30d", "clf_20pct_60d"]:
            models = ML_MODELS_V3.get(key)
            cal = ML_CALIBRATORS_V3.get(key) if ML_CALIBRATORS_V3 else None
            if not models:
                continue
            if isinstance(models, list):
                probs = [m.predict_proba(X)[0, 1] for m in models]
                raw = sum(probs) / len(probs)
            else:
                raw = models.predict_proba(X)[0, 1]
            if cal is not None:
                raw = float(cal.predict([raw])[0])
            out_key = key.replace("clf_", "hit_")
            result[out_key] = round(raw, 4)

        # Regression targets (output is absolute drawdown %)
        for key in ["reg_dd_30d", "reg_dd_60d"]:
            model = ML_MODELS_V3.get(key)
            if model is None:
                continue
            dd = float(model.predict(X)[0])
            out_key = key.replace("reg_", "expected_")
            result[out_key] = round(-abs(dd), 2)  # negative convention

        return result
    except Exception as e:
        log.debug(f"v3 predict failed for {getattr(stock, 'symbol', '?')}: {e}")
        return result

# Portfolio state path (GCS or local)
PORTFOLIO_STATE = os.environ.get("PORTFOLIO_STATE", "portfolio_state.json")

# ---------------------------------------------------------------------------
# FMP API Client — all stable endpoints use ?symbol= query params
# ---------------------------------------------------------------------------

def fmp(endpoint: str, params: dict = None) -> Optional[list]:
    """Call FMP stable API. Returns list or None."""
    if os.environ.get("FMP_OFFLINE", "").lower() in ("1", "true", "yes"):
        log.warning(f"FMP call bypassed (offline mode): {endpoint}")
        return None
    time.sleep(RATE_LIMIT)
    url = f"{FMP}/{endpoint}"
    p = {"apikey": FMP_KEY}
    if params:
        p.update(params)
    try:
        r = requests.get(url, params=p, timeout=20)
        if r.status_code != 200:
            # v7.2.2 Apr 22: expanded diagnostic. When we get a non-200 we log
            # the full URL (apikey redacted) and a longer response body slice
            # so we can distinguish between "endpoint doesn't exist" (404 with
            # HTML or JSON error body) vs "wrong params" (400 with error msg)
            # vs "key lacks permission" (403) vs "rate limited" (429).
            redacted_url = r.url.replace(FMP_KEY, "***REDACTED***") if FMP_KEY else r.url
            log.warning(
                f"FMP {r.status_code}: {endpoint} → body={r.text[:300]!r} "
                f"url={redacted_url}"
            )
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
    industry: str = ""        # e.g. "Semiconductors"
    theme: str = ""           # SpeculAIr Modern Theme (e.g. "AI & Semiconductors")
    company_name: str = ""    # human-readable name from FMP company-screener
                              # (used by frontend name search; May 2026 v1.2)

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

    # PT revision velocity (v8 Smart Money, May 11 2026): 60d % delta in
    # analyst PT consensus, derived from rolling GCS cache. None when no
    # 60d history exists yet (first 60 days after deploy, or stocks with
    # gaps). Both fields parallel: raw value for display, banded score
    # 0..1 for Smart Money composite.
    pt_velocity_60d: Optional[float] = None
    pt_velocity_score: Optional[float] = None

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
    p_s: float = 0.0  # Price/Sales ratio (latest annual): local_price / revenue_per_share

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

    # signal field removed v1.2 (May 2026): BUY/HOLD/SELL semantics unused
    # by runners (which sort by composite). Cohort signals are preserved:
    # signal_momentum, signal_compounder_us, signal_compounder_global.
    # Fallen-Angel cohort uses fallen_angel_flag (bool) instead of a signal.
    classification: str = ""
    reasons: list = field(default_factory=list)

    # ─── v8 fields (Apr 2026) ─────────────────────────────────────────
    # Margin-based quality components (computed from income + cashflow stmts)
    net_margin: float = 0.0          # netIncome / revenue, TTM
    fcf_margin: float = 0.0          # freeCashFlow / revenue, TTM
    # Growth — TTM YoY and 3-year CAGR for the three core metrics
    revenue_yoy: float = 0.0
    eps_yoy: float = 0.0
    fcf_yoy: float = 0.0
    fcf_cagr_3y: float = 0.0
    # Valuation ratios
    p_fcf: float = 0.0               # price / FCF per share
    earnings_yield: float = 0.0      # 1/PE; eps / price
    # Forward intrinsic from BVPS projection (already computed in get_value)
    intrinsic_bvps: float = 0.0
    bvps_recent_cagr: float = 0.0    # 3yr BVPS CAGR (used in projection)
    bvps_consistency: float = 0.0    # fraction of YoY BVPS-positive periods
    bvps_upside: float = 0.0         # display-only: BVPS-only upside %
    intrinsic_upside: float = 0.0    # Buffett 5y MoS at 10% hurdle (replaces old BVPS-blend method)
    # v8 reversal score for Fallen Angel mode
    reversal_score: int = 0

    # ─── Buffett 5-year valuation (May 2026) ─────────────────────────
    # Replaces the old BVPS-only projection. Two-method dispatch based on
    # whether BVPS×ROE compounding matches reality (capital-intensive) or
    # has decoupled (capital-light, use direct EPS CAGR).
    buffett_method: str = ""              # "bvps_roe" | "eps_cagr" | "fallback_analyst"
    buffett_g_assumed: float = 0.0        # growth rate used (clipped)
    buffett_roe_assumed: float = 0.0      # ROE used (Method A only)
    buffett_pe_median: float = 0.0        # median P/E used for terminal multiple
    buffett_eps_5y: float = 0.0           # projected EPS 5 years out
    buffett_future_price: float = 0.0     # = eps_5y × pe_median
    buffett_fair_value: float = 0.0       # discounted to today at 10% hurdle
    buffett_evaluated: bool = False
    buffett_fallback_reason: str = ""     # populated when gate fails
    # Track record arrays (11 years, oldest→newest) for stock-page tab
    buffett_history: dict = field(default_factory=dict)
    # v8 5-factor composite — populated by compute_composite_v8
    factors_v8: dict = field(default_factory=dict)
    mode: str = "momentum"           # "momentum" | "fallen_angel" — drives reversal vs bull score
    # ─── Option B (Apr 2026): dual-mode composites for UI toggle ─────
    # Both modes computed for every stock so frontend can toggle without
    # re-scanning. `composite` defaults to momentum view (matches existing
    # screener table sort). Each mode also retains its own factors dict
    # for the 5-axis radar.
    factors_v8_momentum: dict = field(default_factory=dict)
    factors_v8_fallen_angel: dict = field(default_factory=dict)

    # ─── 9 Valuation Methodologies fields (May 2026) ──────────────────
    rd_capitalized_dcf: float = 0.0
    owner_earnings: float = 0.0
    epv_value: float = 0.0
    graham_revised: float = 0.0
    iv15_deep_value: float = 0.0

    dcf_fcff_mos: float = -1.0
    earnings_yield_gap_mos: float = -1.0
    ev_gross_profit_mos: float = -1.0
    rd_capitalized_dcf_mos: float = -1.0
    owner_earnings_mos: float = -1.0
    epv_mos: float = -1.0
    graham_revised_mos: float = -1.0
    acquirers_multiple_mos: float = -1.0
    iv15_deep_value_mos: float = -1.0

    net_debt_local: float = 0.0
    ebit_local: float = 0.0
    depreciation_local: float = 0.0
    net_debt: float = 0.0
    ebit: float = 0.0
    depreciation: float = 0.0
    gross_profit: float = 0.0
    total_assets: float = 0.0
    eps_latest: float = 0.0
    fx_to_report: float = 1.0
    fx_to_price: float = 1.0
    gp_ta: float = 0.0
    ey_gap: float = 0.0
    acquirers_multiple: float = 999.0

    # ML probability prediction (GBM model, P(+10% in 60d))
    # Apr 2026: still computed and written to JSON for diagnostic purposes,
    # but no longer rendered on the dashboard. The LTR investigation showed
    # per-stock probabilities aren't trustworthy at the 0.65 AUC ceiling.
    # The Smart Money Score below is the heuristic the dashboard surfaces
    # in its place.
    hit_prob: float = 0.0            # 0-1, from trained model; 0 if model not loaded

    # v3 multi-target time model predictions (May 2026)
    hit_prob_10pct_30d: float = 0.0  # P(touch +10% in 30 trading days)
    hit_prob_10pct_60d: float = 0.0  # P(touch +10% in 60 trading days)
    hit_prob_30d: float = 0.0        # P(touch +20% in 30 trading days)
    hit_prob_60d: float = 0.0        # P(touch +20% in 60 trading days)
    expected_dd_30d: float = 0.0     # expected max drawdown in 30d (%)
    expected_dd_60d: float = 0.0     # expected max drawdown in 60d (%)

    # Smart Money Score (Apr 2026) — LTR-derived weighted factor score.
    # Pass-2 only: institutional_flow + congressional are US-only/pass-2-only
    # data, so this is None for pass-1 rows and non-US stocks.
    smart_money_score: Optional[float] = None
    smart_money_components: dict = field(default_factory=dict)
    smart_money_weight: float = 0.0  # fraction of 1.0 weight evaluated

    # Factor breakdown for transparency
    factor_scores: dict = field(default_factory=dict)

    # v7.1: Factor coverage — how many factors had real data vs defaulting to neutral
    factor_coverage: int = 0               # count of factors with real evaluation (0-10)
    factor_coverage_pct: float = 0.0       # coverage as fraction (0.0-1.0)
    factors_evaluated: list = field(default_factory=list)   # names of factors with real data
    factors_missing: list = field(default_factory=list)     # names of factors with no data

    # v7.2.1 Apr 21: Massive options enrichment (populated for top-30 in Pass 2).
    options_iv_current: float = None
    options_iv_rank: float = None
    options_iv_samples: int = 0
    options_spread: dict = None
    
    # v7.2.3 Apr 22: expanded Options signals
    options_pc_ratio: float = None
    options_pc_oi_ratio: float = None
    options_skew_25d: float = None
    options_total_open_interest: int = None
    options_iv_30d: float = None
    options_iv_60d: float = None
    options_iv_90d: float = None
    options_term_structure: str = None
    options_implied_earnings_move: dict = None

    # Legacy tradier_* aliases removed May 2026 — all consumers now use
    # the options_* field names directly (signal_tracker.py, frontend).
    # Data comes from massive_options.py (Polygon.io), not Tradier.

    # ─── v8 Compounder mode (May 2026, v1.1 May 11) ────────────────────────
    # Universe-rank-based composite. Raw PIT inputs are computed per-stock
    # in get_value(); the score is computed at end of screen() across the
    # qualified cohort. Two parallel cohorts: US-listed and Global.
    #
    # v1.1 changes vs v1.0:
    #   - ROE: 1-yr PIT → 3-yr strict average (cyclical-rebound fix)
    #   - US cohort: SP500-member gate → country=='US' + mcap>=$2B
    #     (FMP's sp500-constituent was missing MRVL; new gate is more robust
    #      and includes mid-caps like ONTO, PENG)
    #   - Field rename for clarity: compounder_score → compounder_score_us
    #
    # roe_compounder:               3-YEAR AVERAGE of (netIncome / equity),
    #                               capped at 1.0 per-year. Requires all 3
    #                               years to have eq > 0 (strict). Universe-
    #                               independent — same for both cohorts.
    # pb_compounder:                local_price / (equity / shares_diluted), 1-yr
    # opmargin_delta_compounder:    (op_income/rev current) − (op_income/rev prior), 1-yr
    # compounder_score_us:          equal-weight blend (ROE/PB-inv/OpMd ranks)
    #                               within US-listed cohort
    # compounder_rank_us:           1-indexed rank within US cohort
    # signal_compounder_us:         "QUALIFIED" | "DISQUALIFIED"
    # compounder_score_global:      same blend, Global cohort (ex Fin/Ins/HC,
    #                               any country, any mcap)
    # compounder_rank_global:       1-indexed rank within Global cohort
    # signal_compounder_global:     "QUALIFIED" | "DISQUALIFIED"
    # fallen_angel_flag:            informational alert — rev_growth >15%,
    #                               RSI<40, composite<0.50, price>$1, vol>100K
    roe_compounder: Optional[float] = None
    pb_compounder: Optional[float] = None
    opmargin_delta_compounder: Optional[float] = None
    compounder_score_us: Optional[float] = None
    compounder_rank_us: Optional[int] = None
    signal_compounder_us: str = "DISQUALIFIED"
    fallen_angel_flag: bool = False

    compounder_score_global: Optional[float] = None
    compounder_rank_global: Optional[int] = None
    signal_compounder_global: str = "DISQUALIFIED"

    # v1.2 (May 2026): per-factor percentile breakdown for the stock detail page
    # Compounder card. Each value is this stock's rank-percentile within its
    # cohort (1.0 = best in cohort on that factor, 0.0 = worst). The composite
    # score is the equal-weight mean of the three. Populated by
    # _rank_compounder_cohort for stocks that qualify; None otherwise.
    cmp_us_roe_pct: Optional[float] = None
    cmp_us_pb_pct: Optional[float] = None
    cmp_us_opd_pct: Optional[float] = None
    cmp_global_roe_pct: Optional[float] = None
    cmp_global_pb_pct: Optional[float] = None
    cmp_global_opd_pct: Optional[float] = None

# ---------------------------------------------------------------------------
# 1. Stock Discovery (unchanged from v5)
# ---------------------------------------------------------------------------

REGIONS = {
    "nasdaq100": [("NASDAQ", None, 5_000_000_000, 100)],
    # v1.2 (May 2026): limits bumped from 500 → 5000 per exchange. FMP's
    # company-screener returns results in an internal order that's not
    # strictly market-cap descending — at limit=500 some $10B+ names like
    # ONTO and ALAB were silently excluded. 5000 effectively captures all
    # of NYSE/NASDAQ ≥$1B. No FMP cost change (one call per exchange).
    "sp500": [
        ("NASDAQ", None, 1_000_000_000, 5000),
        ("NYSE", None, 1_000_000_000, 5000)
    ],
    # 2026-04-23: US mid-cap universes, $2B-$10B market cap.
    # 5-tuples: (exchange, country, min_cap, max_cap, limit).
    # get_symbols below handles both 4-tuple and 5-tuple variants.
    #
    # 2026-04-25: Combined "midcap" region — single scan over NYSE + NASDAQ
    # midcaps. Produces latest_midcap.json which feeds strategy_basket.py.
    # Schedule weekly Mon 06:00 CET via Cloud Scheduler.
    "midcap": [
        ("NYSE",   "US", 2_000_000_000, 10_000_000_000, 300),
        ("NASDAQ", "US", 2_000_000_000, 10_000_000_000, 300),
    ],
    "midcap_nyse":   [("NYSE",   "US", 2_000_000_000, 10_000_000_000, 300)],
    "midcap_nasdaq": [("NASDAQ", "US", 2_000_000_000, 10_000_000_000, 300)],
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
INDUSTRY_MAP: dict[str, str] = {}         # {sym: "Semiconductors"} from company-screener
SECTOR_PERF_CACHE: dict[str, float] = {}  # {"Technology": 0.0842}  60d cumulative return
SECTOR_EXCHANGE_MAP: dict[str, str] = {}  # {sym: "NASDAQ"}  needed for sector perf calls
COUNTRY_MAP: dict[str, str] = {}          # {sym: "US"} ISO-2 country code, for filter/display
COMPANY_NAME_MAP: dict[str, str] = {}     # {sym: "NVIDIA Corp"} for frontend name search (v1.2 May 2026)
EARNINGS_CAL_CACHE: dict[str, list] = {}  # {sym: [events]} 90-day forward earnings, populated lazily

# v8 Compounder v1.1 (May 11 2026): SP500_MEMBERS cache + preload_sp500_members()
# removed. The US cohort gate is now country=='US' + market_cap >= $2B + sector
# ex Fin/Ins/HC (see compute_compounder_universe_scores). The prior SP500-member
# gate was abandoned because FMP's sp500-constituent endpoint had data-quality
# issues (e.g. MRVL was missing from its response). The new gate is more robust
# and also includes mid-caps (ONTO, PENG) that the SP500 wouldn't have caught.

# PT revision velocity now uses FMP price-target-summary endpoint directly
# via get_analyst(), dropping the local caching bootstrap.

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
    # 2026-04-23: "midcap" combined universe — NYSE + NASDAQ $2-10B US.
    if region == "midcap":
        syms = []
        for r in ["midcap_nyse", "midcap_nasdaq"]:
            syms.extend(get_symbols(r))
        return list(dict.fromkeys(syms))

    configs = REGIONS.get(region)
    if configs is None:
        configs = [(region.upper(), None, 1_000_000_000, 50)]

    # v1.2 (May 2026): REQUIRES_ALLOWLIST gate removed (Bruno Option A).
    # The sp500 region used to require strategy_allowlists/sp500.txt at
    # runtime, blocking scans if the file was missing. With allowlists
    # retired entirely, that check is dead.

    # 2026-05-05: sectors hard-excluded for the sp500 momentum universe.
    # Per v1.0 strategy: no Financials, no Insurance, no REITs, no Utilities.
    # Applied as a defense-in-depth strip *after* FMP returns results, in
    # addition to the allowlist intersection below.
    EXCLUDED_SECTORS = {"Financial Services", "Real Estate", "Utilities"}

    symbols = []
    for cfg_tuple in configs:
        # 2026-04-23: support both 4-tuple (existing: exchange, country,
        # min_cap, limit) and 5-tuple (new: exchange, country, min_cap,
        # max_cap, limit). Added for midcap universes ($2B-$10B band).
        if len(cfg_tuple) == 5:
            exchange, country, min_cap, max_cap, limit = cfg_tuple
        else:
            exchange, country, min_cap, limit = cfg_tuple
            max_cap = None
        params = {
            "exchange": exchange, "marketCapMoreThan": min_cap,
            "volumeMoreThan": 100_000,     # filter illiquid stocks
            "priceMoreThan": 1,            # filter penny stocks
            "isActivelyTrading": "true", "isEtf": "false", "isFund": "false",
            "limit": limit,
        }
        if max_cap is not None:
            params["marketCapLowerThan"] = max_cap
        if country: params["country"] = country
        # 2026-05-05: for sp500, force country=US and exclude alt share classes
        # (defense-in-depth — the allowlist already restricts to US SP500
        # tickers, but if the file is malformed we don't want non-US ADRs
        # leaking through).
        if region == "sp500":
            params["country"] = "US"
            params["includeAllShareClasses"] = "false"
        data = fmp("company-screener", params)
        if data:
            batch = []
            for d in data:
                sym = d.get("symbol")
                if not sym:
                    continue
                sec = d.get("sector") or ""
                # 2026-05-05: post-fetch sector strip for sp500. Catches
                # any name that slipped into FMP's screener under the
                # excluded-sector umbrella (Financial Services / REIT /
                # Utility) before we intersect with the allowlist.
                if region == "sp500" and sec in EXCLUDED_SECTORS:
                    continue
                batch.append(sym)
                # v7.2: preserve sector + exchange + country for scoring and UI filters
                if sec:
                    SECTOR_MAP[sym] = sec
                ind = d.get("industry") or ""
                if ind:
                    INDUSTRY_MAP[sym] = ind
                SECTOR_EXCHANGE_MAP[sym] = d.get("exchangeShortName") or exchange
                co = d.get("country") or country or ""
                if co:
                    COUNTRY_MAP[sym] = co.upper()
                # v1.2 (May 2026): persist companyName for frontend name search.
                # FMP's company-screener returns this field — zero new API calls.
                cn = d.get("companyName") or ""
                if cn:
                    COMPANY_NAME_MAP[sym] = cn
            log.info(f"  {exchange}/{country or 'all'}: {len(batch)} stocks")
            symbols.extend(batch)

    # v1.2 (May 2026): allowlist intersect REMOVED per Bruno's Option A.
    # Allowlists existed to support the v1.0 BORING strategy (Piotroski≤3 +
    # validated universe). BORING is retired. The remaining strategies
    # (Compounder/Momentum/FA) have their own cohort gates (sector ex
    # Fin/Ins/HC, mcap thresholds, etc.) — those are the real "validated
    # universe" filters now. Allowlist plumbing is legacy.
    #
    # Also removed: the REQUIRES_ALLOWLIST gate higher up — sp500 region
    # no longer needs an external allowlist since universe-build now catches
    # the full NYSE/NASDAQ ≥$1B set via limit=5000.

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


# preload_sp500_members() removed May 11 2026 — see SP500_MEMBERS comment above.

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

    # ---------------------------------------------------------------------
    # v8: Reversal score (10 signals) — for Fallen Angel mode
    # Mirrors bull_score structure but scores reversal SETUPS (oversold
    # bounces, MA reclaims, off-the-low patterns) rather than trend
    # continuation. Used by v8 Fallen Angel mode; Momentum mode keeps using
    # bull_score. Both scores are computed and returned; the consuming mode
    # picks which to weight in the composite.
    # ---------------------------------------------------------------------
    rev_score = 0
    rev_reasons = []
    year_low = quote.get("year_low", 0)

    # Historical indicator state (4w / 8w lookbacks) — recompute on
    # truncated arrays. ~20 trading days = 4 calendar weeks.
    if len(closes) > 35:
        rsi_4w = compute_rsi(closes[:-20])
        rsi_8w_min = min(compute_rsi(closes[:-i]) for i in (5, 10, 15, 20, 25, 30, 35, 40)
                         if len(closes) > i + 15) if len(closes) > 50 else rsi
        rsi_8w_min = min(rsi_8w_min, rsi)
    else:
        rsi_4w = rsi
        rsi_8w_min = rsi

    if len(closes) > 55:
        macd_4w = compute_macd(closes[:-20])
        bb_4w = compute_bollinger(closes[:-20])
        stoch_4w_min = min(compute_stoch_rsi(closes[:-i]) for i in (5, 10, 15, 20)
                           if len(closes) > i + 28)
        stoch_4w_min = min(stoch_4w_min, stoch)
    else:
        macd_4w = {"signal": "neutral", "histogram": 0}
        bb_4w = bb_pct
        stoch_4w_min = stoch

    sma50_20ago = sum(closes[-70:-20]) / 50 if len(closes) >= 70 else sma50

    # 10w EMA (~50 trading days)
    if len(closes) >= 50:
        ema10w = sum(closes[:50]) / 50
        mult = 2 / (51)
        for c in closes[50:]:
            ema10w = (c - ema10w) * mult + ema10w
        # 10w EMA value 4w ago, for reclaim detection
        ema10w_4w = sum(closes[:50]) / 50
        for c in closes[50:-20] if len(closes) > 70 else closes[50:]:
            ema10w_4w = (c - ema10w_4w) * mult + ema10w_4w
    else:
        ema10w = closes[-1]
        ema10w_4w = closes[-1]

    # 1. RSI reclaiming from oversold
    if 30 < rsi < 50 and rsi_8w_min < 30:
        rev_score += 1; rev_reasons.append(f"RSI reclaim {rsi:.0f} (was <{rsi_8w_min:.0f})")
    # 2. MACD cross up from negative
    if macd["signal"] == "bullish_cross" or (macd["histogram"] > 0 and macd_4w["histogram"] < 0):
        rev_score += 1; rev_reasons.append("MACD reversal")
    # 3. Reclaim 10w EMA (Bruno's v8 fallen-angel trigger)
    if price > ema10w and len(closes) >= 70 and closes[-21] < ema10w_4w:
        rev_score += 1; rev_reasons.append("Reclaim 10w EMA")
    # 4. Off 52w low (15-30%) — out of basement, not yet extended
    if year_low > 0:
        off_low_pct = (price - year_low) / year_low
        if 0.15 < off_low_pct < 0.30:
            rev_score += 1; rev_reasons.append(f"+{off_low_pct*100:.0f}% off low")
    # 5. 50d SMA flattening or curling up
    if sma50 >= sma50_20ago * 0.995:
        rev_score += 1; rev_reasons.append("50d SMA stable/up")
    # 6. ADX in trend-establishing range (15-25)
    if 15 < adx < 25:
        rev_score += 1; rev_reasons.append(f"ADX {adx:.0f}")
    # 7. BB%B exiting lower band
    if 0.2 < bb_pct < 0.5 and bb_4w < 0.2:
        rev_score += 1; rev_reasons.append("BB%B reclaim")
    # 8. StochRSI cross up from oversold
    if stoch > 20 and stoch_4w_min < 20:
        rev_score += 1; rev_reasons.append("StochRSI reclaim")
    # 9. OBV inflecting up
    if obv == "rising":
        rev_score += 1; rev_reasons.append("OBV rising")
    # 10. Below 200d but above 50d — fallen-angel territory with recovery
    if 0 < sma200 and price < sma200 and price > sma50 > 0:
        rev_score += 1; rev_reasons.append("Below 200d, above 50d")

    return {
        "rsi": rsi, "macd_signal": macd["signal"], "adx": adx,
        "bb_pct": bb_pct, "stoch_rsi": stoch, "obv_trend": obv,
        "bull_score": score, "bull_reasons": reasons,
        # v8: reversal score for Fallen Angel mode
        "reversal_score": rev_score, "reversal_reasons": rev_reasons,
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
              "eps_surprises": [],
              # v7.2.1 Apr 20 — forward estimates (enrichment only, no score change yet).
              # Blend into Upside factor at July 2026 review, after live calibration data.
              "forward_eps_fy1": 0, "forward_eps_fy2": 0,
              "forward_revenue_fy1": 0, "forward_revenue_fy2": 0,
              "forward_pe": 0, "forward_eps_growth": 0,
              "estimates_analysts_fy1": 0,
              }  # track individual surprise magnitudes

    # Price target consensus (v1.3.2: cached, 3-day TTL)
    pt = cached_fmp(
        "price-target-consensus", sym,
        lambda: fmp("price-target-consensus", {"symbol": sym}),
    )
    if pt and pt[0].get("targetConsensus"):
        result["target"] = float(pt[0]["targetConsensus"])

    # Grades (recent 90 days) — v1.3.2: cached, 3-day TTL
    grades = cached_fmp(
        "grades", sym,
        lambda: fmp("grades", {"symbol": sym, "limit": 30}),
    )
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

    # Forward analyst estimates (fiscal-year-ahead EPS / revenue)
    # Endpoint returns years from oldest to newest historical estimates; the
    # first entries are current/future FYs. We sort by date desc and pick the
    # two nearest future years relative to today.
    try:
        est = fmp("analyst-estimates", {"symbol": sym, "period": "annual", "limit": 10})
        if est and isinstance(est, list):
            today_str = datetime.now().strftime("%Y-%m-%d")
            future = [e for e in est if str(e.get("date", "")) >= today_str]
            future.sort(key=lambda e: e.get("date", ""))
            if len(future) >= 1:
                fy1 = future[0]
                result["forward_eps_fy1"] = float(fy1.get("epsAvg") or 0)
                result["forward_revenue_fy1"] = float(fy1.get("revenueAvg") or 0)
                result["estimates_analysts_fy1"] = int(fy1.get("numAnalystsEps") or 0)
            if len(future) >= 2:
                fy2 = future[1]
                result["forward_eps_fy2"] = float(fy2.get("epsAvg") or 0)
                result["forward_revenue_fy2"] = float(fy2.get("revenueAvg") or 0)
                # Forward EPS growth rate (FY2 vs FY1)
                if result["forward_eps_fy1"] > 0:
                    result["forward_eps_growth"] = (
                        (result["forward_eps_fy2"] - result["forward_eps_fy1"])
                        / result["forward_eps_fy1"]
                    )
    except Exception as e:
        log.debug(f"analyst-estimates failed for {sym}: {e}")

    # PT revision velocity (v1.3 May 2026): compute from FMP's 
    # stable price-target-summary endpoint. Removes need for 60d bootstrap.
    result["pt_velocity_60d"] = None
    result["pt_velocity_score"] = None
    if result["target"] > 0:
        try:
            pt_sum = fmp("price-target-summary", {"symbol": sym})
            if pt_sum and isinstance(pt_sum, list) and len(pt_sum) > 0:
                summary = pt_sum[0]
                last_q = float(summary.get("lastQuarterAvgPriceTarget") or 0)
                last_y = float(summary.get("lastYearAvgPriceTarget") or 0)
                if last_q > 0 and last_y > 0:
                    velocity = (last_q - last_y) / last_y
                    score = _ladder(
                        velocity,
                        [-0.05, 0.0, 0.05, 0.10],
                        [0.0, 0.25, 0.5, 0.75, 1.0],
                    )
                    result["pt_velocity_60d"] = round(velocity, 4)
                    result["pt_velocity_score"] = round(score, 4)
        except Exception as e:
            log.debug(f"pt velocity fetch failed for {sym}: {e}")

    return result

# ---------------------------------------------------------------------------
# 5. Value / Buffett Layer
# ---------------------------------------------------------------------------

def safe_cagr(start, end, years):
    if not start or not end or start <= 0 or end <= 0 or years <= 0:
        return 0.0
    return (end / start) ** (1 / years) - 1

def get_value(sym: str, price: float, price_currency: str = "USD") -> dict:
    """Full Buffett value analysis with FX-aware intrinsic value calculation.

    Apr 2026: hard filter — if FMP returns fewer than MIN_YEARS_HISTORY
    annual income statements, this function returns the default v dict
    augmented with `_insufficient_history=True`. The screen loop checks
    that flag and skips the stock (recent IPOs, spin-offs, etc.).
    """
    v = {
        "revenue_cagr_3y": 0, "eps_cagr_3y": 0,
        "roe_avg": 0, "roe_consistent": False, "roic_avg": 0,
        "gross_margin": 0, "gross_margin_trend": "unknown",
        "piotroski": 0, "altman_z": 0,
        "dcf_value": 0, "owner_earnings_yield": 0,
        "intrinsic_buffett": 0, "intrinsic_bvps": 0, "intrinsic_avg": 0,
        "bvps_cagr_10y": 0.0, "bvps_consistency": 0.0, "bvps_recent_cagr": 0.0,
        "margin_of_safety": 0, "value_score": 0, "p_s": 0,
        "classification": "UNKNOWN",
        "_insufficient_history": False,
        "rd_capitalized_dcf": 0.0,
        "owner_earnings": 0.0,
        "epv_value": 0.0,
        "graham_revised": 0.0,
        "iv15_deep_value": 0.0,
        "dcf_fcff_mos": -1.0,
        "rd_capitalized_dcf_mos": -1.0,
        "owner_earnings_mos": -1.0,
        "epv_mos": -1.0,
        "graham_revised_mos": -1.0,
        "iv15_deep_value_mos": -1.0,
        "net_debt_local": 0.0,
        "ebit_local": 0.0,
        "depreciation_local": 0.0,
        "net_debt": 0.0,
        "ebit": 0.0,
        "depreciation": 0.0,
        "gross_profit": 0.0,
        "total_assets": 0.0,
        "eps_latest": 0.0,
        "fx_to_report": 1.0,
        "fx_to_price": 1.0,
    }
    if price <= 0:
        return v

    # Income statements (5 years) — v1.3.1: cached, 5-day TTL
    inc = cached_fmp(
        "income-statement", sym,
        lambda: fmp("income-statement", {"symbol": sym, "period": "annual", "limit": 5}),
    )

    # Apr 2026: 5-year history hard filter. Drop stocks where FMP returns fewer
    # than MIN_YEARS_HISTORY annual statements. This filters recent IPOs and
    # spin-offs that don't have a full 5-year fundamental history.
    if not inc or len(inc) < MIN_YEARS_HISTORY:
        v["_insufficient_history"] = True
        log.info(f"  {sym}: insufficient history ({len(inc) if inc else 0} years "
                 f"< {MIN_YEARS_HISTORY} required) — skipping")
        return v

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
 
        # P/S ratio (latest annual). local_price is already in reported_ccy
        # (set above via fx_to_report) and revs[-1] is in reported_ccy too,
        # so revenue/share is in reported_ccy/share and local_price /
        # rev_per_share is unitless. Uses diluted share count when present;
        # falls back to basic shares.
        latest_shares = float(inc[-1].get("weightedAverageShsOutDil") or inc[-1].get("weightedAverageShsOut") or 0)
        if latest_shares > 0 and revs[-1] > 0:
            rev_per_share = revs[-1] / latest_shares
            if rev_per_share > 0:
                v["p_s"] = local_price / rev_per_share
        margins = [gp / rev if rev > 0 else 0 for gp, rev in zip(gp_list, revs)]
        if len(margins) >= 3:
            if margins[-1] > margins[-3] + 0.02:
                v["gross_margin_trend"] = "expanding"
            elif margins[-1] < margins[-3] - 0.02:
                v["gross_margin_trend"] = "contracting"
            else:
                v["gross_margin_trend"] = "stable"

    # Key metrics (v1.3.0: cached — quarterly data, 5-day TTL)
    km = cached_fmp(
        "key-metrics", sym,
        lambda: fmp("key-metrics", {"symbol": sym, "period": "annual", "limit": 5}),
    )
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
    # v1.3.0: cached — quarterly data, 5-day TTL
    scores = cached_fmp(
        "financial-scores", sym,
        lambda: fmp("financial-scores", {"symbol": sym}),
    )
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

    # ------------------- v8: BVPS Forward Projection (simplified) -------------------
    # Replaces v7.2's 10-year-with-terminal-P/B-and-discount-back formula.
    # New: intrinsic_bvps = BVPS_now * (1 + g_bvps) ** BVPS_PROJ_YEARS
    # where g_bvps = clip(3yr BVPS CAGR, 2%, 15%). No terminal P/B multiplier,
    # no discount-back. Plain compound forward projection of book value.
    # Combined with analyst consensus target in compute_upside_score (v8).
    # Guards retained: declined 3+ years → skip; negative equity → skip;
    # weak financial health → skip. Bvps_consistency kept for diagnostic.
# ──────────────────────────────────────────────────────────────────
    # May 2026: Buffett 5-year valuation (replaces the BVPS-only forward
    # projection). Pulls 11 years of statements + ratios, computes medians
    # and CAGRs, stores a track record array for the stock-page tab, and
    # runs the two-method projection.
    # ──────────────────────────────────────────────────────────────────
    # v1.3.1: cached — quarterly data, 5-day TTL
    bs = cached_fmp(
        "balance-sheet-statement", sym,
        lambda: fmp("balance-sheet-statement", {"symbol": sym, "period": "annual", "limit": 11}),
    )
    ratios = cached_fmp(
        "ratios", sym,
        lambda: fmp("ratios", {"symbol": sym, "period": "annual", "limit": 11}),
    )
    cf = cached_fmp(
        "cash-flow-statement", sym,
        lambda: fmp("cash-flow-statement", {"symbol": sym, "period": "annual", "limit": 11}),
    )

    history_rows = []  # built oldest→newest, capped at 11
    if bs and inc and len(bs) >= 5 and len(inc) >= 5:
        bs_sorted = sorted(bs, key=lambda x: x.get("date", ""))
        inc_sorted = sorted(inc, key=lambda x: x.get("date", ""))
        ratios_by_year = {}
        if ratios:
            for r in ratios:
                yr = (r.get("date") or "")[:4]
                if yr:
                    ratios_by_year[yr] = r
        cf_by_year = {}
        if cf:
            for c in cf:
                yr = (c.get("date") or "")[:4]
                if yr:
                    cf_by_year[yr] = c

        # Align income + balance by year
        bs_by_year = {(r.get("date") or "")[:4]: r for r in bs_sorted}
        for inc_row in inc_sorted:
            yr = (inc_row.get("date") or "")[:4]
            if not yr or yr not in bs_by_year:
                continue
            bs_row = bs_by_year[yr]
            r_row = ratios_by_year.get(yr, {})
            cf_row = cf_by_year.get(yr, {})

            equity = float(bs_row.get("totalStockholdersEquity") or 0)
            shares = float(inc_row.get("weightedAverageShsOutDil") or 0)
            ni = float(inc_row.get("netIncome") or 0)
            eps = float(inc_row.get("epsDiluted") or 0)
            rev = float(inc_row.get("revenue") or 0)
            div_paid = abs(float(cf_row.get("commonDividendsPaid") or 0))  # paid is negative in FMP
            dps = (div_paid / shares) if shares > 0 else 0
            bvps = (equity / shares) if shares > 0 and equity > 0 else 0
            pe = float(r_row.get("priceToEarningsRatio") or 0)
            history_rows.append({
                "year": yr, "bvps": bvps, "eps": eps, "dps": dps,
                "shares_mm": shares / 1e6 if shares else 0,
                "revenue_mm": rev / 1e6 if rev else 0,
                "net_income_mm": ni / 1e6 if ni else 0,
                "equity_mm": equity / 1e6 if equity else 0,
                "pe": pe if pe > 0 else None,
            })

    # Take last 5 years for projection math (most recent 5 entries)
    recent5 = history_rows[-5:] if len(history_rows) >= 5 else history_rows
    bvps_latest = recent5[-1]["bvps"] if recent5 else 0
    eps_latest = recent5[-1]["eps"] if recent5 else 0

    # Eligibility — count POSITIVE-EPS years in last 5
    eps_positive_years_5y = sum(1 for r in recent5 if r["eps"] > 0)

    # 5y CAGRs (need first and last positive)
    bvps_cagr_5y = None
    if len(recent5) >= 4 and recent5[0]["bvps"] > 0 and recent5[-1]["bvps"] > 0:
        years_span = len(recent5) - 1
        bvps_cagr_5y = safe_cagr(recent5[0]["bvps"], recent5[-1]["bvps"], years_span)

    eps_cagr_5y = None
    if len(recent5) >= 4 and recent5[0]["eps"] > 0 and recent5[-1]["eps"] > 0:
        years_span = len(recent5) - 1
        eps_cagr_5y = safe_cagr(recent5[0]["eps"], recent5[-1]["eps"], years_span)

    # Median ROE over last 5 years (skip years with negative equity)
    roe_series = []
    for r in recent5:
        if r["equity_mm"] > 0 and r["net_income_mm"]:
            roe_series.append(r["net_income_mm"] / r["equity_mm"])
    roe_median_5y = sorted(roe_series)[len(roe_series) // 2] if roe_series else None

    # Median payout (display + retention identity check)
    payout_series = []
    for r in recent5:
        if r["eps"] > 0 and r["dps"] >= 0:
            payout_series.append(min(r["dps"] / r["eps"], 1.5))
    payout_median_5y = sorted(payout_series)[len(payout_series) // 2] if payout_series else 0

    # Median P/E over last 5 years (filter null/negative and outliers > 100x)
    pe_series_5y = [r["pe"] for r in recent5 if r["pe"] is not None and 0 < r["pe"] < 100]
    pe_median_5y = sorted(pe_series_5y)[len(pe_series_5y) // 2] if len(pe_series_5y) >= 3 else None

    # Median Book Yield (EPS / prior BVPS) over last 5 years
    book_yield_series = []
    recent6 = history_rows[-6:] if len(history_rows) >= 6 else history_rows
    for i in range(1, len(recent6)):
        prev_bvps = recent6[i-1]["bvps"]
        eps = recent6[i]["eps"]
        if prev_bvps > 0:
            book_yield_series.append(eps / prev_bvps)
    book_yield_median_5y = sorted(book_yield_series)[len(book_yield_series) // 2] if book_yield_series else None

    # Persist to v dict for compute_buffett_valuation + downstream display
    v["bvps_latest"] = round(bvps_latest, 2)
    v["eps_latest"] = round(eps_latest, 2)
    v["bvps_cagr_5y"] = round(bvps_cagr_5y, 4) if bvps_cagr_5y is not None else None
    v["eps_cagr_5y"] = round(eps_cagr_5y, 4) if eps_cagr_5y is not None else None
    v["roe_median_5y"] = round(roe_median_5y, 4) if roe_median_5y is not None else None
    v["pe_median_5y"] = round(pe_median_5y, 2) if pe_median_5y is not None else None
    v["payout_median_5y"] = round(payout_median_5y, 4)
    v["book_yield_median_5y"] = round(book_yield_median_5y, 4) if book_yield_median_5y is not None else None
    v["eps_positive_years_5y"] = eps_positive_years_5y

    # Run Buffett valuation (gate-aware; falls through with _evaluated=False on failure)
    buf = compute_buffett_valuation(v, sym, local_price, hurdle=0.10)
    v["buffett_evaluated"] = buf["_evaluated"]
    v["buffett_fallback_reason"] = buf["fallback_reason"]
    v["buffett_method"] = buf["method"]
    v["buffett_g_assumed"] = buf["g_assumed"]
    v["buffett_roe_assumed"] = buf["roe_assumed"]
    v["buffett_pe_median"] = buf["pe_median"]
    v["buffett_eps_5y"] = buf["eps_5y"]
    v["buffett_future_price"] = buf["future_price"]
    v["buffett_fair_value"] = buf["fair_value"]
    v["buffett_upside_pct"] = buf["upside_pct"]

    # Convert future_price + fair_value to price currency for display if FX-mismatched
    if need_fx and buf["_evaluated"]:
        v["buffett_future_price"] *= fx_to_price
        v["buffett_fair_value"] *= fx_to_price

    # Track record array — last 11 years (oldest first)
    v["buffett_history"] = {
        "rows": history_rows,
        "medians": {
            "roe": v["roe_median_5y"],
            "payout": v["payout_median_5y"],
            "pe": v["pe_median_5y"],
        },
        "cagrs": {
            "bvps_5y": v["bvps_cagr_5y"],
            "eps_5y": v["eps_cagr_5y"],
        },
    }

    # Legacy field — retain for any downstream code still reading it.
    # Now points to Buffett fair_value so anything reading intrinsic_avg
    # gets the new methodology automatically.
    v["intrinsic_avg"] = v["buffett_fair_value"] if buf["_evaluated"] else 0
    if v["intrinsic_avg"] > 0 and local_price > 0:
        v["margin_of_safety"] = (v["intrinsic_avg"] - local_price) / local_price
    else:
        v["margin_of_safety"] = 0

    # ──────────────────────────────────────────────────────────────────
    # v8 (Apr 2026): Margin, growth, and valuation-ratio fields
    # Bruno's five-factor brief requires net margin, FCF margin, and three
    # growth rates (revenue/EPS/FCF) in the composite. These are computed
    # from the same income+cashflow data already loaded above, plus one
    # extra cashflow fetch. Stored on the v dict and surfaced on Stock for
    # compute_composite_v8 to read directly.
    # ──────────────────────────────────────────────────────────────────
    v["net_margin"] = 0.0
    v["fcf_margin"] = 0.0
    v["revenue_yoy"] = 0.0
    v["eps_yoy"] = 0.0
    v["fcf_yoy"] = 0.0
    v["fcf_cagr_3y"] = 0.0
    v["p_fcf"] = 0.0
    v["p_s"] = 0.0
    v["earnings_yield"] = 0.0

    # Net margin (most-recent year)
    if inc and len(inc) >= 1:
        latest_inc = inc[-1]  # already sorted oldest→newest above
        rev_latest = float(latest_inc.get("revenue") or 0)
        ni_latest = float(latest_inc.get("netIncome") or 0)
        eps_latest = float(latest_inc.get("epsDiluted") or 0)
        if rev_latest > 0:
            v["net_margin"] = ni_latest / rev_latest
        if local_price > 0 and eps_latest > 0:
            v["earnings_yield"] = eps_latest / local_price
        # P/S — price / sales per share (Apr 2026)
        shares_latest = float(latest_inc.get("weightedAverageShsOutDil") or 0)
        if shares_latest > 0 and rev_latest > 0 and local_price > 0:
            v["p_s"] = local_price / (rev_latest / shares_latest)

    # Revenue and EPS growth — TTM YoY (most-recent two annual rows)
    if inc and len(inc) >= 2:
        rev_curr = float(inc[-1].get("revenue") or 0)
        rev_prev = float(inc[-2].get("revenue") or 0)
        if rev_prev > 0:
            v["revenue_yoy"] = (rev_curr - rev_prev) / rev_prev
        eps_curr = float(inc[-1].get("epsDiluted") or 0)
        eps_prev = float(inc[-2].get("epsDiluted") or 0)
        if eps_prev > 0 and eps_curr > 0:
            v["eps_yoy"] = (eps_curr - eps_prev) / eps_prev

    # FCF — v1.3.1: cached (same cache key as the limit=11 call above; superset is fine)
    cf = cached_fmp(
        "cash-flow-statement", sym,
        lambda: fmp("cash-flow-statement", {"symbol": sym, "period": "annual", "limit": 5}),
    )
    if cf and len(cf) >= 1:
        cf.sort(key=lambda x: x.get("date", ""))  # oldest → newest
        fcf_series = [float(x.get("freeCashFlow") or 0) for x in cf]
        # FCF margin (latest)
        if inc and len(inc) >= 1:
            rev_latest = float(inc[-1].get("revenue") or 0)
            if rev_latest > 0 and fcf_series[-1]:
                v["fcf_margin"] = fcf_series[-1] / rev_latest
        # FCF YoY
        if len(fcf_series) >= 2 and fcf_series[-2] > 0:
            v["fcf_yoy"] = (fcf_series[-1] - fcf_series[-2]) / fcf_series[-2]
        # FCF 3yr CAGR
        if len(fcf_series) >= 4 and fcf_series[-4] > 0 and fcf_series[-1] > 0:
            v["fcf_cagr_3y"] = safe_cagr(fcf_series[-4], fcf_series[-1], 3)
        # P/FCF — needs FCF per share
        if local_price > 0 and fcf_series[-1] > 0 and inc:
            shares = float(inc[-1].get("weightedAverageShsOutDil") or 0)
            if shares > 0:
                fcf_per_share = fcf_series[-1] / shares
                if fcf_per_share > 0:
                    v["p_fcf"] = local_price / fcf_per_share

    # Convert intrinsic values to price currency for display.
    # Note: buffett_future_price + buffett_fair_value were already converted
    # above inside the Buffett block. dcf_value + intrinsic_buffett + 
    # intrinsic_avg are kept for backward-compat but no longer drive scoring.
    if need_fx:
        for key in ("dcf_value", "intrinsic_buffett"):
            if v.get(key, 0) > 0:
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

    # ──────────────────────────────────────────────────────────────────
    # v8 Compounder mode (May 2026) — raw PIT inputs for universe ranking.
    # The actual score (compounder_score_*) is computed at end of screen()
    # across the qualified cohort; here we just emit the three raw metrics.
    # All three are None on failure — the universe-ranker excludes any
    # stock missing any of them.
    #
    # v1.1 (May 11 2026): roe_compounder switched from 1-year PIT to 3-YEAR
    # STRICT AVERAGE. v1.0 review found cyclical-rebound stocks dominating
    # the top picks: CAG (+231% NI YoY) and EXE (+36.5pp OpMd from oil-price
    # recovery). Per-year ROE is still capped at 1.0 before averaging; the
    # average is mean of 3 years. Strict means ALL 3 years need eq > 0,
    # else None. This departs from the handover-validated 1-yr spec —
    # paper-track as discovery, not validation, and revisit in 6 weeks.
    # ──────────────────────────────────────────────────────────────────
    v["roe_compounder"] = None
    v["pb_compounder"] = None
    v["opmargin_delta_compounder"] = None

    # ROE: 3-YEAR STRICT AVERAGE. Requires 3 aligned annual reports with
    # eq > 0 in EVERY year. Per-year cap at 1.0 still applied before mean.
    if bs and inc and len(bs) >= 3 and len(inc) >= 3:
        bs_sorted_c = sorted(bs, key=lambda x: x.get("date", ""))
        # inc is sorted oldest→newest above (line ~1234)
        roes = []
        for i in range(-3, 0):
            ni_i = float(inc[i].get("netIncome") or 0)
            eq_i = float(bs_sorted_c[i].get("totalStockholdersEquity") or 0)
            if eq_i <= 0:
                roes = []
                break
            roes.append(min(ni_i / eq_i, 1.0))
        if len(roes) == 3:
            v["roe_compounder"] = sum(roes) / 3

    # P/B and OpMargin-delta — unchanged. P/B is point-in-time by design.
    # OpMargin-delta is also a "change" metric where smoothing would defeat
    # the purpose. If post-launch top picks remain dominated by margin
    # rebounds (e.g. EXE), revisit to smooth OpMd similarly.
    if bs and inc and len(bs) >= 1 and len(inc) >= 1:
        bs_sorted_c = sorted(bs, key=lambda x: x.get("date", ""))
        latest_bs = bs_sorted_c[-1]
        latest_inc = inc[-1]
        eq = float(latest_bs.get("totalStockholdersEquity") or 0)
        sh = float(latest_inc.get("weightedAverageShsOutDil")
                   or latest_inc.get("weightedAverageShsOut") or 0)
        if eq > 0 and sh > 0 and local_price > 0:
            bvps = eq / sh
            if bvps > 0:
                v["pb_compounder"] = local_price / bvps

    # ─── 9 Valuation Methodologies (May 2026) ─────────────────────────
    if bs and cf and len(bs) >= 1 and len(cf) >= 1:
        bs_sorted = sorted(bs, key=lambda x: x.get("date", ""))
        cf_sorted = sorted(cf, key=lambda x: x.get("date", ""))
        inc_sorted = sorted(inc, key=lambda x: x.get("date", ""))
        
        latest_bs = bs_sorted[-1]
        latest_cf = cf_sorted[-1]
        latest_inc = inc_sorted[-1]
        
        # 1. Gather fields in reported (local) currency
        # ── STABILIZATION (May 2026): use 3-year averages for volatile inputs ──
        # Single-year FCF, NI, EBIT can swing 50-100% YoY due to capex cycles,
        # working capital, or one-off items. Averaging over up to 3 years
        # dampens noise and prevents MOS from jumping 80+pp between scans.
        def _avg_field(rows, field, fallback=0.0):
            """Average a field over the last N rows, skipping zeros/nulls."""
            vals = [float(r.get(field) or 0) for r in rows]
            non_zero = [v for v in vals if v != 0]
            return sum(non_zero) / len(non_zero) if non_zero else fallback

        def _avg_field_abs(rows, field, fallback=0.0):
            """Average of absolute values (for capex which FMP reports as negative)."""
            vals = [abs(float(r.get(field) or 0)) for r in rows]
            non_zero = [v for v in vals if v != 0]
            return sum(non_zero) / len(non_zero) if non_zero else fallback

        # Use last 3 years of data for smoothing (or fewer if unavailable)
        recent_inc = inc_sorted[-3:] if len(inc_sorted) >= 3 else inc_sorted
        recent_cf = cf_sorted[-3:] if len(cf_sorted) >= 3 else cf_sorted
        recent_bs = bs_sorted[-3:] if len(bs_sorted) >= 3 else bs_sorted

        # Smoothed inputs (3-year averages)
        net_income = _avg_field(recent_inc, "netIncome")
        ebit = _avg_field(recent_inc, "operatingIncome")
        depreciation = _avg_field(recent_cf, "depreciationAndAmortization",
                                  _avg_field(recent_cf, "depreciation"))
        capex = _avg_field_abs(recent_cf, "capitalExpenditure")
        fcf = _avg_field(recent_cf, "freeCashFlow")
        rd_expense = _avg_field(recent_inc, "researchAndDevelopmentExpenses")

        # Point-in-time balance sheet items (latest year — averaging doesn't
        # make sense for stock variables like debt and equity)
        total_assets = float(latest_bs.get("totalAssets") or 0)
        total_equity = float(latest_bs.get("totalStockholdersEquity") or 0)
        current_assets = float(latest_bs.get("totalCurrentAssets") or 0)
        current_liabilities = float(latest_bs.get("totalCurrentLiabilities") or 0)
        long_term_debt = float(latest_bs.get("longTermDebt") or 0)
        shares = float(latest_inc.get("weightedAverageShsOutDil") or latest_inc.get("weightedAverageShsOut") or 0)
        
        # Latest annual EPS (point-in-time for Graham formula)
        eps_latest = float(latest_inc.get("epsDiluted") or latest_inc.get("eps") or 0)
        v["eps_latest"] = eps_latest
        
        # Store raw local inputs for leverage gate (latest year, not averaged)
        net_debt_local = long_term_debt - (current_assets - current_liabilities)
        v["net_debt_local"] = net_debt_local
        v["ebit_local"] = float(latest_inc.get("operatingIncome") or 0)
        v["depreciation_local"] = float(latest_cf.get("depreciationAndAmortization") or latest_cf.get("depreciation") or 0)
        
        # Store converted to price currency
        v["net_debt"] = net_debt_local * fx_to_price
        v["ebit"] = ebit * fx_to_price
        v["depreciation"] = depreciation * fx_to_price
        v["gross_profit"] = float(latest_inc.get("grossProfit") or 0) * fx_to_price
        v["total_assets"] = total_assets * fx_to_price
        v["fx_to_report"] = fx_to_report
        v["fx_to_price"] = fx_to_price
        
        # 1yr Revenue growth
        rev_growth_1yr = 0.0
        if len(inc_sorted) >= 2:
            rev_c = float(inc_sorted[-1].get("revenue") or 0)
            rev_p = float(inc_sorted[-2].get("revenue") or 0)
            if rev_p > 0:
                rev_growth_1yr = (rev_c - rev_p) / rev_p
                
        # 3yr EPS growth
        eps_growth_3y = v.get("eps_cagr_3y", 0.0)
        
        # Helper for MoS — capped to [-1.0, +0.95] for sanity.
        # Uncapped, (FV-Price)/FV can go to -∞ when FV→0, producing
        # meaningless values like -269% that distort exit metrics.
        def calc_mos(fv, pr):
            if fv <= 0:
                return -1.0
            return max(-1.0, min(0.95, (fv - pr) / fv))

        # ROE — use 5-year median when available (much more stable than 1yr)
        roe_median = v.get("roe_median_5y")
        roe = roe_median if roe_median is not None else (
            net_income / total_equity if total_equity > 0 else 0.0
        )

        # 1. DCF-FCFF
        wacc = 0.10
        growth_est = min(max(roe * 0.5, 0.03), 0.25)
        projected_fcff = fcf
        pv_stage1 = 0.0
        curr_fcff = projected_fcff
        for yr in range(1, 6):
            curr_fcff *= (1 + growth_est * (0.85 ** yr))
            pv_stage1 += curr_fcff / ((1 + wacc) ** yr)
        terminal_fcff = curr_fcff * (1 + 0.025)
        terminal_value = terminal_fcff / (wacc - 0.025)
        pv_terminal = terminal_value / ((1 + wacc) ** 5)
        eq_val = pv_stage1 + pv_terminal - net_debt_local
        fv_dcf_local = eq_val / shares if shares > 0 else 0.0
        v["dcf_value"] = fv_dcf_local * fx_to_price
        v["dcf_fcff_mos"] = calc_mos(v["dcf_value"], price)

        # 2. R&D Capitalized DCF
        adj_net_income = net_income + rd_expense - (rd_expense / 5.0)
        adj_assets = total_assets + rd_expense * 2.5
        adj_equity = total_equity + rd_expense * 2.5
        adj_roe = adj_net_income / adj_equity if adj_equity > 0 else 0.0
        growth_rd = min(max(adj_roe * 0.4, 0.03), 0.20)
        pv_stage1_rd = 0.0
        earn = adj_net_income
        for yr in range(1, 8):
            earn *= (1 + growth_rd * (0.9 ** yr))
            pv_stage1_rd += earn / ((1 + wacc) ** yr)
        terminal_rd = earn * (1 + 0.025) / (wacc - 0.025)
        pv_terminal_rd = terminal_rd / ((1 + wacc) ** 7)
        fv_rd_local = (pv_stage1_rd + pv_terminal_rd) / shares if shares > 0 else 0.0
        v["rd_capitalized_dcf"] = fv_rd_local * fx_to_price
        v["rd_capitalized_dcf_mos"] = calc_mos(v["rd_capitalized_dcf"], price)

        # 3. Owner Earnings Yield
        g_rev = min(max(rev_growth_1yr, 0.0), 1.0)
        maint_capex = capex - capex * (g_rev / (1 + g_rev)) if capex > 0 else 0.0
        if maint_capex <= 0:
            maint_capex = capex * 0.7
        oe = net_income + depreciation - maint_capex
        growth_oe = min(max(roe * 0.4, 0.02), 0.15)
        pv_stage1_oe = 0.0
        oe_t = oe
        for yr in range(1, 11):
            oe_t *= (1 + growth_oe * (0.9 ** yr))
            pv_stage1_oe += oe_t / ((1 + wacc) ** yr)
        terminal_oe = oe_t * 1.025 / (wacc - 0.025)
        pv_terminal_oe = terminal_oe / ((1 + wacc) ** 10)
        fv_oe_local = (pv_stage1_oe + pv_terminal_oe) / shares if shares > 0 else 0.0
        v["owner_earnings"] = fv_oe_local * fx_to_price
        v["owner_earnings_mos"] = calc_mos(v["owner_earnings"], price)
        if shares > 0 and local_price > 0:
            v["owner_earnings_yield"] = (oe / shares) / local_price

        # 4. EPV (Greenwald)
        maint_capex_epv = capex - capex * (g_rev / (1 + g_rev)) if capex > 0 else 0.0
        if maint_capex_epv <= 0:
            maint_capex_epv = depreciation if depreciation > 0 else capex * 0.7
        adjusted_earnings = ebit - maint_capex_epv
        nopat = adjusted_earnings * (1 - 0.21)
        enterprise_epv = nopat / wacc
        equity_epv = enterprise_epv - net_debt_local
        fv_epv_local = equity_epv / shares if shares > 0 else 0.0
        v["epv_value"] = fv_epv_local * fx_to_price
        v["epv_mos"] = calc_mos(v["epv_value"], price)

        # 5. Graham Revised
        # FIX: negative/zero growth should use g=0 (8.5× P/E), not g=5 (18.5× P/E).
        # A company with shrinking earnings shouldn't get a premium growth multiple.
        g_graham = max(0.0, min(20.0, eps_growth_3y * 100)) if eps_growth_3y > 0 else 0.0
        fv_graham_local = eps_latest * (8.5 + 2 * g_graham)
        v["graham_revised"] = fv_graham_local * fx_to_price
        v["graham_revised_mos"] = max(-1.0, min(0.95, 1.0 - (price / v["graham_revised"]))) if v["graham_revised"] > 0 else -1.0

        # 6. IV15 Deep Value
        # Tightened cap from 40% → 20%: a 40% CAGR for 15 years is unrealistic
        g_blend = min(0.20, max(0.02, eps_growth_3y))
        terminal_mult = min(20.0, max(8.0, g_blend * 100 * 2))
        terminal_fcf = fcf * ((1 + g_blend) ** 15)
        terminal_mcap = terminal_fcf * terminal_mult
        if shares > 0:
            # 8.137 ≈ (1.15)^15 — discounts the 15-year terminal value at a
            # 15% annual return hurdle rate.
            IV15_HURDLE_DIVISOR = 1.15 ** 15  # ≈ 8.137
            fv_iv15_local = terminal_mcap / (shares * IV15_HURDLE_DIVISOR)
        else:
            fv_iv15_local = 0.0
        v["iv15_deep_value"] = fv_iv15_local * fx_to_price
        v["iv15_deep_value_mos"] = max(-1.0, min(0.95, 1.0 - (price / v["iv15_deep_value"]))) if v["iv15_deep_value"] > 0 else -1.0

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
def project_future_eps_buffett(value_data: dict, sym: str) -> tuple:
    """5-year EPS projection.
    
    Returns (eps_5y, method_name, g_capped, _evaluated, fallback_reason).
    method_name is "eps_cagr". On gate failure returns
    (None, None, None, False, reason_string).
    """
    eps_today = value_data.get("eps_latest", 0)
    bvps_cagr_5y = value_data.get("bvps_cagr_5y")
    eps_cagr_5y = value_data.get("eps_cagr_5y")
    book_yield_median_5y = value_data.get("book_yield_median_5y")
    eps_positive = value_data.get("eps_positive_years_5y", 0)

    # Gate: need solid 5y history
    if eps_positive < 4:
        return None, None, None, False, f"only {eps_positive}/5 profitable years"
    if eps_today <= 0:
        return None, None, None, False, "current EPS not positive"

    # g: should be the smallest CAGR between EPS, book yield or BVPS.
    cagrs = []
    if bvps_cagr_5y is not None: cagrs.append(bvps_cagr_5y)
    if eps_cagr_5y is not None: cagrs.append(eps_cagr_5y)
    if book_yield_median_5y is not None: cagrs.append(book_yield_median_5y)
    
    g_best = min(cagrs) if cagrs else 0.05
    g_capped = max(0.02, min(g_best, 0.25))

    eps_5y = eps_today * (1 + g_capped) ** 5

    return eps_5y, "eps_cagr", g_capped, True, None


def compute_buffett_valuation(value_data: dict, sym: str,
                              current_price: float, hurdle: float = 0.10) -> dict:
    """Full Value 5y valuation. Returns dict with all fields needed by
    Stock dataclass. _evaluated=False with fallback_reason on gate failure.
    """
    eps_5y, method, g_capped, evaluated, reason = project_future_eps_buffett(value_data, sym)
    if not evaluated:
        return {"_evaluated": False, "fallback_reason": reason,
                "method": "", "g_assumed": 0.0, "roe_assumed": 0.0,
                "pe_median": 0.0, "eps_5y": 0.0, "future_price": 0.0,
                "fair_value": 0.0, "upside_pct": 0.0}

    pe_median = value_data.get("pe_median_5y")
    if pe_median is None or pe_median <= 0:
        return {"_evaluated": False, "fallback_reason": "no usable P/E history",
                "method": "", "g_assumed": 0.0, "roe_assumed": 0.0,
                "pe_median": 0.0, "eps_5y": 0.0, "future_price": 0.0,
                "fair_value": 0.0, "upside_pct": 0.0}
    pe_capped = max(8.0, min(pe_median, 50.0))

    future_price = eps_5y * pe_capped
    fair_value = future_price / (1 + hurdle) ** 5
    upside_pct = (fair_value - current_price) / current_price * 100 if current_price > 0 else 0

    return {
        "_evaluated": True, "fallback_reason": "",
        "method": method,
        "g_assumed": round(g_capped, 4),
        "roe_assumed": 0.0,
        "pe_median": round(pe_capped, 2),
        "eps_5y": round(eps_5y, 2),
        "future_price": round(future_price, 2),
        "fair_value": round(fair_value, 2),
        "upside_pct": round(upside_pct, 2),
    }
                                
def compute_upside_score(analyst: dict, value: dict, price: float) -> dict:
    """v9 (May 2026): Buffett 5-year MoS at 10% hurdle drives the score.
    Two-method projection (BVPS×ROE or direct EPS CAGR) dispatched in
    project_future_eps_buffett. Analyst target shown side-by-side as
    1-year sanity check. Gate failure falls back to analyst-only with
    a flag the UI surfaces.

    Fields returned:
      consensus_upside       analyst-target upside % (display, 1y horizon)
      buffett_upside         Buffett 5y MoS at 10% hurdle (score driver)
      intrinsic_upside       same as buffett_upside (legacy field name)
      score                  0-1 ladder
      _evaluated             True if EITHER Buffett OR analyst gave us something
      _valuation_method      "buffett" | "fallback_analyst" | "none"
      _fallback_reason       why Buffett gate failed (if relevant)
    """
    result = {"score": 0.0, "consensus_upside": 0, "buffett_upside": 0,
              "intrinsic_upside": 0, "_evaluated": False,
              "_valuation_method": "none", "_fallback_reason": ""}

    if price <= 0:
        return result

    # Analyst-target upside (always shown as 1-year sanity check)
    target = analyst.get("target", 0)
    if target > 0:
        result["consensus_upside"] = round((target - price) / price * 100, 2)

    buffett_evaluated = value.get("buffett_evaluated", False)

    if buffett_evaluated:
        # Primary path: Buffett 5y MoS drives score
        upside_pct = value.get("buffett_upside_pct", 0)
        result["buffett_upside"] = round(upside_pct, 2)
        result["intrinsic_upside"] = round(upside_pct, 2)
        result["_evaluated"] = True
        result["_valuation_method"] = "buffett"
    elif target > 0:
        # Fallback: analyst-only. Flag for UI.
        upside_pct = result["consensus_upside"]
        result["intrinsic_upside"] = upside_pct
        result["_evaluated"] = True
        result["_valuation_method"] = "fallback_analyst"
        result["_fallback_reason"] = value.get("buffett_fallback_reason",
                                               "Buffett gate failed")
    else:
        # No usable signal at all
        return result

    # Score ladder — same as before, applied to whichever upside_pct we got
    upside_pct = result["intrinsic_upside"]
    if upside_pct > 30:    result["score"] = 1.0
    elif upside_pct > 15:  result["score"] = 0.85
    elif upside_pct > 0:   result["score"] = 0.6
    elif upside_pct > -15: result["score"] = 0.35
    elif upside_pct > -30: result["score"] = 0.15
    else:                  result["score"] = 0.0

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

    Strict precondition (2026-04-23): piotroski and altman_z must be present
    and non-None. Callers upstream now gate on this. If we reach here with
    None, upstream is broken — fail loudly rather than silently defaulting.
    """
    if value.get("piotroski") is None:
        raise ValueError(
            "compute_quality_score called with missing piotroski; "
            "upstream data-quality gate should have excluded this row."
        )
    # altman_z may be None for Financial Services / Real Estate sectors
    # where Altman's model doesn't apply. Redistribute its weight to
    # Piotroski (the primary quality signal) when that happens.
    result = {"score": 0.0}

    pio = value["piotroski"]
    az = value.get("altman_z")   # None for excluded sectors
    roe = value.get("roe_avg", 0)
    roic = value.get("roic_avg", 0)
    gm = value.get("gross_margin", 0)

    # Piotroski (40% of quality) — strongest single predictor
    result["score"] += (pio / 9) * 0.40

    # Piotroski weight redistributes from 40% -> 60% when Altman Z is
    # unavailable (Financial Services / Real Estate sectors, or non-USD
    # reporters). Adjust Piotroski scoring post-hoc, then skip Altman term.
    if az is None:
        # Subtract the 0.40*Piotroski already added above, re-add at 0.60
        pio = value["piotroski"]
        result["score"] += (pio / 9) * 0.20   # 0.60 - 0.40 = 0.20 bump
    else:
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

# Populate cache on first call: paginate through 90 days of global earnings.
    # FMP's earnings-calendar appears to cap responses (~700 rows per day across
    # all global exchanges). At 90 days that's tens of thousands of events —
    # without pagination, late dates / less-liquid symbols get silently dropped.
    # May 2026 fix: walk the window in 14-day chunks. CVS was missing from
    # same-day scans despite FMP having the data — repro confirmed via MCP.
    if not EARNINGS_CAL_CACHE:
        chunk_days = 14
        chunks_fetched = 0
        for offset in range(0, 90, chunk_days):
            chunk_start = (today + timedelta(days=offset)).strftime("%Y-%m-%d")
            chunk_end = (today + timedelta(days=min(offset + chunk_days, 90))).strftime("%Y-%m-%d")
            chunk = fmp("earnings-calendar", {"from": chunk_start, "to": chunk_end})
            if chunk and isinstance(chunk, list):
                chunks_fetched += 1
                for ev in chunk:
                    s_ev = ev.get("symbol") or ""
                    d_ev = ev.get("date") or ""
                    if s_ev and d_ev >= today_str:
                        EARNINGS_CAL_CACHE.setdefault(s_ev, []).append(ev)
        for s_ev in EARNINGS_CAL_CACHE:
            EARNINGS_CAL_CACHE[s_ev].sort(key=lambda e: e.get("date", ""))
        if EARNINGS_CAL_CACHE:
            log.info(f"  Earnings calendar cached: {len(EARNINGS_CAL_CACHE)} symbols "
                     f"with upcoming earnings in next 90d ({chunks_fetched}/7 chunks fetched)")
        else:
            # Cache is empty for THIS scan but don't sentinel-block — the
            # per-symbol fallback below will catch real upcoming earnings.
            log.warning("  Earnings calendar bulk fetch returned no usable data; "
                        "relying on per-symbol fallback")

    sym_events = EARNINGS_CAL_CACHE.get(sym, [])
    days_until = None
    if sym_events:
        e = sym_events[0]
        report_date = e.get("date", "")
        try:
            days_until = (datetime.strptime(report_date, "%Y-%m-%d").date() - today_date).days
        except Exception:
            days_until = None

    # May 2026 — the bulk earnings-calendar endpoint serves stale dates for
    # some symbols. Repro: CVS bulk returned 2026-06-11, per-symbol returned
    # 2026-05-06 (FMP's lastUpdated confirms 05-06 is current). When bulk
    # says earnings is >14 days out, verify with per-symbol — for stocks
    # actually reporting in <2 weeks, the bulk's stale date hides the catalyst
    # entirely. The 14-day threshold matches the "earnings in N days" UI gate.
    needs_verification = (
        days_until is None or days_until > 14
    )
    if needs_verification:
        sym_cal = None
        try:
            sym_cal = fmp("earnings", {"symbol": sym, "limit": 4})
        except Exception:
            sym_cal = None
        if sym_cal and isinstance(sym_cal, list):
            future_events = sorted(
                [ev for ev in sym_cal if (ev.get("date") or "") >= today_str],
                key=lambda ev: ev.get("date", ""),
            )
            if future_events:
                e_auth = future_events[0]
                report_date_auth = e_auth.get("date", "")
                try:
                    days_until_auth = (datetime.strptime(report_date_auth, "%Y-%m-%d").date() - today_date).days
                except Exception:
                    days_until_auth = None
                # Use the per-symbol date when it's sooner than the bulk's date
                # (or when bulk had nothing). Never let a stale far-out date
                # override an imminent earnings event.
                if days_until_auth is not None and (
                    days_until is None or days_until_auth < days_until
                ):
                    days_until = days_until_auth
                    # Backfill the cache with the authoritative event for any
                    # later code paths in the same scan that read it.
                    EARNINGS_CAL_CACHE[sym] = [e_auth]

    if days_until is not None:
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
    # v1.3.2: cached, 3-day TTL (same cache as get_analyst grades call; limit=30 superset is fine)
    grades = cached_fmp(
        "grades", sym,
        lambda: fmp("grades", {"symbol": sym, "limit": 10}),
    )
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
    # v7.2: FMP's REST path `news/stock?symbols=X` is the symbol-filtered
    # endpoint per FMP docs (https://site.financialmodelingprep.com/developer/
    # docs/stable/search-stock-news → example URL uses /stable/news/stock).
    #
    # Earlier in this session I misdiagnosed this via an MCP tool call — the
    # MCP tool has its own endpoint name `stock-news` that maps to the
    # unfiltered global feed, and `search-stock-news` (MCP name) that maps to
    # the REST path `news/stock`. The REST-side path `news/search-stock-news`
    # does NOT exist — it 404s. Cloud Run logs confirmed this with thousands
    # of "FMP 404: news/search-stock-news → []" lines per scan.
    #
    # Keep per-article symbol verification as belt-and-suspenders.
    #
    # v7.2.1 (Apr 20): tightened M&A keyword set. Previously fired on single
    # words like "deal", "bid", "offer", "stake" — all common in routine
    # financial news (analyst price targets, position disclosures, routine
    # announcements). False positives on INVA, CVS, others. Now requires
    # phrases that are genuinely M&A-specific or a confirmed activist action.
    news = fmp("news/stock", {"symbols": sym, "limit": 10})
    if news:
        cutoff = (today - timedelta(days=14)).strftime("%Y-%m-%d")
        # M&A / activist — must be PHRASES, not single ambiguous words
        ma_phrases = [
            "acquisition of", "acquires ", "to acquire",
            "merger with", "merger agreement", "to merge",
            "buyout", "takeover bid", "tender offer",
            "activist investor", "activist campaign", "activist stake",
            "proxy fight", "hostile bid",
            "spin-off", "spinoff", "spin off",
            "definitive agreement", "strategic alternatives",
            "going private", "leveraged buyout", "lbo ",
        ]
        pos_kw = {"approval", "fda", "patent", "contract", "partnership",
                  "launch", "breakthrough", "record revenue"}
        neg_kw = {"lawsuit", "investigation", "fraud", "recall",
                  "warning", "subpoena", "sec inquiry", "delisting"}

        sym_upper = sym.upper()
        for article in news:
            # Guard: if endpoint ever returns unrelated symbols, skip them.
            art_sym = (article.get("symbol", "") or "").upper()
            if art_sym and art_sym != sym_upper:
                continue
            pub = article.get("publishedDate", "")[:10]
            if pub < cutoff:
                continue
            title = (article.get("title", "") + " " + article.get("text", "")[:300]).lower()

            completed_phrases = [
                "completes acquisition", "completes merger", "closes merger",
                "closes acquisition", "closed acquisition", "closed merger",
                "merger closed", "acquisition closed", "acquisition completed",
                "merger completed", "deal closed", "deal completed",
                "completes buyout", "buyout completed", "buyout closed"
            ]
            
            is_completed = any(cp in title for cp in completed_phrases)
            if is_completed:
                result["score"] -= 0.35
                result["flags"].append("Post-event M&A/buyout (already closed/completed)")
                break

            if any(ph in title for ph in ma_phrases):
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
# 11d. Smart Money Score (Apr 2026) — LTR-derived weighted factor score
#
# Locked in after the LTR investigation: lambdarank v2 and v3 runs on the
# 247K-row scan_cache panel (test window July 2024 - Feb 2025) consistently
# identified six factors as the only ones carrying real ranking signal.
# Weights below are the average of v2 and v3 feature importance, with the
# four core factors (instflow + trend + inst + quality) accounting for 88%.
#
# NO weight redistribution — missing factors don't add to the score.
#   - US stocks with full coverage:                      0.0 -> 1.00
#   - US stocks missing congressional + sector_momentum: max 0.88
#   - Non-US stocks (institutional_flow unavailable):    score = None
#
# The lack of redistribution is intentional. The score's ceiling itself
# encodes coverage — a 0.55 with full coverage is a different beast from
# a 0.55 where 12% of weight is unfilled. Cross-stock comparison stays
# honest without renormalization tricks.
#
# Pass-2 only: institutional_flow + congressional require US-only pass-2
# enrichment, so smart_money_score is None for pass-1 rows below top-30.
#
# Apr 2026: this score now ALSO drives the v8 composite's smart_money sub-
# factor (see compute_composite_v8). Replaces the previous fold of
# institutional_flow + analyst + insider + transcript + earnings + congressional
# which the LTR investigation showed had little predictive power beyond the 6
# factors weighted here.
# ---------------------------------------------------------------------------

SMART_MONEY_WEIGHTS = {
    "institutional_flow":  0.25,  # 13F flow velocity (US-only, pass-2)
    "trend_strength":      0.25,  # (sma50 - sma200) / sma200
    "institutional":       0.20,  # 13F static accumulation (US-only, pass-2)
    "pt_velocity":         0.10,  # analyst PT velocity (via FMP summary API)
    "quality":             0.10,  # Piotroski + Altman + ROE + ROIC + GM
    "sector_momentum":     0.05,  # stock 60d vs sector 60d (NASDAQ only)
    "congressional":       0.05,  # Senate + House trades (US-only, pass-2)
}
SMART_MONEY_CORE = {"institutional_flow", "trend_strength",
                    "institutional", "quality"}


def compute_smart_money_score(institutional_flow: dict, institutional: dict,
                              quality: dict, sector_momentum: dict,
                              congressional: dict, sma50: float,
                              sma200: float,
                              pt_velocity_score: Optional[float] = None) -> dict:
    """Weighted sum across 7 factors. Returns:
        {score, _evaluated, components, weight_evaluated, missing}

    v1.3 (May 14 2026): Dropped transcript from smart money entirely per user
    request. Kept pt_velocity but replaced the 60d local cache bootstrap
    with a direct call to FMP's stable/price-target-summary endpoint.
    Maintained the softened trend confirmation multiplier (floor 0.30).

    v1.1 (May 11 2026): added pt_velocity (analyst PT 60d % delta) at 10%
    weight. instflow 30→25, trend 28→23, rest unchanged. PT velocity is
    None during bootstrap (first ~60 days of scans) and for stocks with
    no current PT — same "evaluated factors only" pattern as other factors.

    May 2026 (Option C): no core-4 gate. Every stock with at least one
    available factor gets a score. Pass-1 stocks naturally cap below
    pass-2 stocks because available weights sum to ≤ 0.45 vs 1.00
    full-coverage. The score's weight_evaluated already encodes coverage —
    no need for a binary gate on top.

    Trend confirmation multiplier (the key Option C fix):
    when institutional_flow is available, the trend_strength contribution
    is scaled by min(1.0, inst_flow.score * 2):
      - inst_flow = 0.5 (neutral)        → multiplier = 1.0  (full credit)
      - inst_flow = 0.25 (mild distrib)  → multiplier = 0.5  (half credit)
      - inst_flow = 0.0 (strong distrib) → multiplier = 0.0  (no credit)
      - inst_flow = 1.0 (accumulation)   → multiplier = 1.0  (capped)
    Strong distribution kills trend's contribution; neutral or accumulation
    lets trend through unmolested. Fixes the bull-trap pattern where MPWR-
    style names ranked top of SMART$ while institutions were exiting:
    distribution + uptrend now scores like distribution alone.

    When institutional_flow is unavailable (pass-1 stocks), no multiplier
    fires — trend contributes raw. Doesn't create gameability because
    pass-1 stocks already cap at ~0.45 from missing weights.

    score is None ONLY when zero factors are evaluated (extreme edge case
    of missing SMA + missing quality + missing PT). For pass-1 stocks the
    typical output is score ≈ 0.20-0.45 from trend + quality + sector_mom.
    """
    components = {}

    # Institutional flow — must compute first since trend uses it
    if institutional_flow and institutional_flow.get("_evaluated"):
        components["institutional_flow"] = institutional_flow.get("score", 0)

    # Trend strength — apply distribution-aware multiplier when inst_flow present
    if sma50 > 0 and sma200 > 0:
        ts = (sma50 - sma200) / sma200
        trend_raw = _ladder(
            ts,
            [-0.10, -0.02, 0.02, 0.10],
            [0.0, 0.20, 0.50, 0.75, 1.0],
        )
        # v1.2 (May 14 2026): softened trend confirmation multiplier.
        # Old formula: min(1.0, inst_flow * 2) — inst_flow=0.2 → mult=0.4,
        # which wiped 60% of trend. Normal institutional rebalancing was
        # being treated as a strong distribution signal. New formula floors
        # the multiplier at 0.30: only truly extreme distribution (inst_flow
        # near 0.0) cuts trend significantly.
        if "institutional_flow" in components:
            trend_mult = min(1.0, 0.30 + components["institutional_flow"] * 1.4)
        else:
            trend_mult = 1.0
        components["trend_strength"] = trend_raw * trend_mult

    # Institutional accumulation
    if institutional and institutional.get("_evaluated"):
        components["institutional"] = institutional.get("score", 0.5)

    # PT revision velocity (v1.1 May 2026) — None means not yet evaluable
    # (bootstrap period or stock has no current PT). Pattern matches other
    # factors: drop from components rather than substituting a neutral 0.5.
    if pt_velocity_score is not None:
        components["pt_velocity"] = pt_velocity_score

    # Quality — Piotroski + Altman + ROE + ROIC + GM blend
    if quality and quality.get("score") is not None:
        components["quality"] = quality["score"]

    # Optional factors — added only if evaluated
    if sector_momentum and sector_momentum.get("_evaluated"):
        components["sector_momentum"] = sector_momentum.get("score", 0.5)
    if congressional and congressional.get("_evaluated"):
        components["congressional"] = congressional.get("score", 0.5)

    # Edge case: zero factors evaluated → None (no SMA + no quality + no flow)
    if not components:
        return {
            "score": None,
            "_evaluated": False,
            "components": {},
            "weight_evaluated": 0.0,
            "missing": sorted(SMART_MONEY_WEIGHTS.keys()),
        }

    # Weighted sum — NO redistribution. Coverage encoded in score ceiling.
    score = sum(SMART_MONEY_WEIGHTS[k] * v for k, v in components.items())
    weight_used = sum(SMART_MONEY_WEIGHTS[k] for k in components)

    return {
        "score": round(score, 4),
        "_evaluated": True,
        "components": {k: round(v, 4) for k, v in components.items()},
        "weight_evaluated": round(weight_used, 4),
        "missing": sorted(set(SMART_MONEY_WEIGHTS.keys()) - components.keys()),
    }

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
            # v1.3.1: cached per-quarter, 90-day TTL. Default-arg trick
            # prevents closure from capturing mutated loop variables.
            data = cached_fmp(
                "earning-call-transcript", sym,
                lambda y=y, q=q: fmp("earning-call-transcript", {"symbol": sym, "year": y, "quarter": q}),
                cache_key_suffix=f"{y}Q{q}",
            )
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

# v1.2 (May 2026): consolidate the FMP positions-summary call. Previously
# get_institutional_flows() and compute_institutional_flow() each made the
# same FMP call independently — double the API cost per stock with identical
# results. Now both read from this module-level cache, populated on first
# request per symbol.
_INST_POSITIONS_SUMMARY_CACHE: dict[str, dict] = {}


def _fetch_institutional_positions_summary(sym: str) -> Optional[dict]:
    """Cached fetch of FMP institutional-ownership/symbol-positions-summary.
    Returns the single summary dict for the most recent quarter with data
    (one quarter back, then two if empty), or None if no data is available
    (non-US stock or unlisted).

    Cached per-symbol for the duration of the scan — same call returns
    instantly on second use.
    """
    if sym in _INST_POSITIONS_SUMMARY_CACHE:
        return _INST_POSITIONS_SUMMARY_CACHE[sym]

    # 13F filings lag ~45 days past quarter-end. Start one quarter back.
    now = datetime.now()
    cur_q = (now.month - 1) // 3 + 1
    q = cur_q - 1 if cur_q > 1 else 4
    y = now.year if cur_q > 1 else now.year - 1

    # v1.3.2: cached, 5-day TTL with per-quarter suffix
    data = cached_fmp(
        "institutional-ownership/symbol-positions-summary", sym,
        lambda y=y, q=q: fmp("institutional-ownership/symbol-positions-summary",
                             {"symbol": sym, "year": y, "quarter": q}),
        cache_key_suffix=f"{y}Q{q}",
    )
    if not data:
        # One more quarter back as a fallback
        q = q - 1 if q > 1 else 4
        y = y if q != 4 else y - 1
        data = cached_fmp(
            "institutional-ownership/symbol-positions-summary", sym,
            lambda y=y, q=q: fmp("institutional-ownership/symbol-positions-summary",
                                 {"symbol": sym, "year": y, "quarter": q}),
            cache_key_suffix=f"{y}Q{q}",
        )

    if not data or not isinstance(data, list) or not data:
        _INST_POSITIONS_SUMMARY_CACHE[sym] = None
        return None

    # Fetch YoY data (same quarter, previous year) to smooth out seasonal rebalancing
    yoy_data = cached_fmp(
        "institutional-ownership/symbol-positions-summary", sym,
        lambda y=y-1, q=q: fmp("institutional-ownership/symbol-positions-summary",
                             {"symbol": sym, "year": y, "quarter": q}),
        cache_key_suffix=f"{y-1}Q{q}",
    )
    yoy_summary = yoy_data[0] if yoy_data and isinstance(yoy_data, list) else None

    # Stash both the summary dict and the YoY summary
    cached = {"summary": data[0], "year": y, "quarter": q, "yoy_summary": yoy_summary}
    _INST_POSITIONS_SUMMARY_CACHE[sym] = cached
    return cached


def get_institutional_flows(sym: str) -> dict:
    """Check institutional ownership changes. Score 0-1.

    v7.2 fix: 13F filings lag 45 days past quarter-end. Starting at CURRENT
    quarter always returns None. The positions-summary endpoint already
    contains QoQ change fields, so we only need ONE quarter's summary.

    Starts one quarter back (most recent that should be reported) and falls
    back further if empty.

    v7.2.1 Apr 20 — smart-money concentration layer:
    Pull the per-holder 13F extract. Compute top-5 holder share of total 13F
    holdings + the QoQ change in that concentration. Rising concentration
    among top holders = smart money accumulating; falling = distribution.
    Blended into score at 20% weight (small contribution so composite
    distribution isn't disrupted mid-regime).
    """
    result = {"holders_change": 0.0, "accumulation": 0.0, "score": 0.5, "_evaluated": False,
              # New fields (exposed to frontend + future ML retrain)
              "top5_concentration": 0.0,       # % of total 13F holdings held by top 5
              "top5_concentration_delta": 0.0, # QoQ change in that %
              "top_holders": [],               # list of {name, ownership, delta} dicts
              }

    # v1.2: use shared cache instead of direct FMP call
    cached = _fetch_institutional_positions_summary(sym)
    if not cached:
        return result  # non-US or unlisted

    d = cached["summary"]
    yoy = cached.get("yoy_summary")
    y = cached["year"]
    q = cached["quarter"]

    # v1.3 YoY Comparison: Smooths out routine quarter-to-quarter rebalancing
    # by comparing the current quarter against the same quarter from the prior year.
    if yoy:
        last_holders = float(yoy.get("investorsHolding") or 0)
        curr_holders = float(d.get("investorsHolding") or 0)
        holders_delta = curr_holders - last_holders

        last_own_pct = float(yoy.get("ownershipPercent") or 0)
        curr_own_pct = float(d.get("ownershipPercent") or 0)
        own_pct_delta = curr_own_pct - last_own_pct
    else:
        # Fallback to QoQ if YoY data missing
        last_holders = float(d.get("lastInvestorsHolding") or 0)
        holders_delta = float(d.get("investorsHoldingChange") or 0)
        own_pct_delta = float(d.get("ownershipPercentChange") or 0)

    result["holders_change"] = (holders_delta / last_holders) if last_holders > 0 else 0.0
    result["accumulation"] = own_pct_delta / 100.0

    # ─── Smart-money concentration layer ───
    # Pull per-holder extract for same quarter we just used (consistent data).
    # Keep limit tight (top 10) — we only need top-5 aggregation.
    try:
        holders = fmp(
            "institutional-ownership/extract-analytics/holder",
            {"symbol": sym, "year": y, "quarter": q, "limit": 10},
        )
    except Exception:
        holders = None

    if holders and isinstance(holders, list):
        # Sort by ownership (percent-of-float), take top 5
        top5 = sorted(
            holders, key=lambda h: float(h.get("ownership") or 0), reverse=True
        )[:5]
        if top5:
            total_own = sum(float(h.get("ownership") or 0) for h in top5)
            total_own_last = sum(float(h.get("lastOwnership") or 0) for h in top5)
            result["top5_concentration"] = round(total_own, 2)
            result["top5_concentration_delta"] = round(total_own - total_own_last, 2)
            result["top_holders"] = [
                {
                    "name": h.get("investorName") or h.get("investorname") or "Unknown",
                    "ownership": round(float(h.get("ownership") or 0), 2),
                    "delta_pp": round(
                        float(h.get("ownership") or 0) - float(h.get("lastOwnership") or 0), 2
                    ),
                    "shares_change_pct": round(
                        float(h.get("changeInSharesNumberPercentage") or 0), 2
                    ),
                    "is_new": bool(h.get("isNew")),
                }
                for h in top5
            ]

    # ─── Score: continuous function (80% weight) ──────────────────────
    # v1.2 (May 14 2026): replaced coarse 5-bucket ladder with continuous
    # linear scoring. The old ladder had cliff effects: a stock at acc=0.0099
    # scored 0.50, at acc=0.0101 scored 0.75 — a 50% jump for a 0.01pp
    # change. Continuous scoring eliminates these artifacts.
    #
    # Accumulation score: maps ±6pp ownership change to 0-1 linearly (widened for YoY).
    # Holders change score: maps ±15% holder count change to 0-1 linearly (widened for YoY).
    # Blend: 60% accumulation (% of float) + 40% holder count change.
    acc = result["accumulation"]
    hc = result["holders_change"]
    acc_score = max(0.05, min(1.0, 0.5 + acc * 8.33))    # ±0.06 = full range (YoY calibrated)
    hc_score  = max(0.05, min(1.0, 0.5 + hc * 3.33))     # ±0.15 = full range (YoY calibrated)
    base_score = 0.60 * acc_score + 0.40 * hc_score

    # ─── Smart-money layer (20% weight) ───
    # Concentration change: continuous mapping, ±3pp = full range
    conc_delta = result["top5_concentration_delta"]
    conc_score = max(0.05, min(1.0, 0.5 + conc_delta / 6.0))

    # Blend: 80% existing logic, 20% concentration
    result["score"] = round(0.8 * base_score + 0.2 * conc_score, 3)

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

    # v1.2: use shared cache (same FMP call used by get_institutional_flows)
    cached = _fetch_institutional_positions_summary(sym)
    if not cached:
        return result  # US-only or FMP returned empty

    d = cached["summary"]
    yoy = cached.get("yoy_summary")

    # v1.3 YoY Comparison
    if yoy:
        new_pos_change = float(d.get("newPositions") or 0) - float(yoy.get("newPositions") or 0)
        closed_pos_change = float(d.get("closedPositions") or 0) - float(yoy.get("closedPositions") or 0)
        inc_pos_change = float(d.get("increasedPositions") or 0) - float(yoy.get("increasedPositions") or 0)
        red_pos_change = float(d.get("reducedPositions") or 0) - float(yoy.get("reducedPositions") or 0)
        own_pct_change = float(d.get("ownershipPercent") or 0) - float(yoy.get("ownershipPercent") or 0)
        pc_ratio_change = float(d.get("putCallRatio") or 0) - float(yoy.get("putCallRatio") or 0)
    else:
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

    # FMP stable REST endpoints are `senate-trades` and `house-trades` (per FMP docs)
    # — NOT `senate-trading`/`house-trading` which return 404.
    # v1.3.2: cached, 5-day TTL. Empty arrays for non-US tickers are cached too.
    senate = cached_fmp(
        "senate-trades", sym,
        lambda: fmp("senate-trades", {"symbol": sym}),
    ) or []
    house = cached_fmp(
        "house-trades", sym,
        lambda: fmp("house-trades", {"symbol": sym}),
    ) or []
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
# 14. Composite Score & Signal (v7.2 — DEPRECATED v1.2 May 2026)
# ---------------------------------------------------------------------------
# v7 13-factor composite is no longer used downstream. The only reason this
# function still runs is to populate `factor_scores` dict — which feeds the
# ML model's 13-feature vector (see predict_hit_prob). Truly removing v7
# requires rewriting the ML feature builder to source features directly from
# raw inputs. Scheduled for v1.3.
#
# In the meantime:
#   - composite_v7 still emitted on every stock (diagnostic only; runners ignore)
#   - signal_v7 ignored (no longer assigned to Stock; was BUY/HOLD/SELL)
#   - factor_scores still populated (feeds ML model — DO NOT REMOVE)

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
# 14b. Composite v8 — Five-factor (Apr 2026)
# ---------------------------------------------------------------------------
# Bruno's five-factor brief, locked in this session:
#   Momentum 25%   — bull_score (Momentum mode) or reversal_score (Fallen Angel)
#   Quality 20%    — net margin 35% + FCF margin 35% + ROIC 30%
#                    Piotroski + Altman dropped from composite, kept on dashboard
#   Growth 20%     — revenue + EPS + FCF, each = 60% TTM YoY + 40% 3yr CAGR
#   Value 20%      — intrinsic upside 40% + P/FCF 30% + earnings yield 30%
#                    Intrinsic = avg(BVPS-projected, analyst consensus)
#                    DCF + intrinsic_buffett dropped from composite
#   Smart Money 15% — Smart Money Score (LTR-derived 6-factor heuristic, Apr 2026)
#                     Replaces previous fold of inst_flow + analyst + insider +
#                     transcript + earnings + congressional which the LTR
#                     investigation showed had little marginal predictive power
#                     beyond the 6 factors compute_smart_money_score weights.
# Absolute thresholds (not sector-relative). Coverage gate retained.
# ---------------------------------------------------------------------------

def _score_growth(yoy, cagr_3y):
    """Score a growth metric as 60/40 TTM-YoY / 3yr-CAGR blend.
    Bruno spec: >25% top, 15-25%, 8-15%, 3-8%, 0-3%, <0%."""
    def _to_score(g):
        if g is None:
            return None
        if g < 0:    return 0.0
        if g < 0.03: return 0.15
        if g < 0.08: return 0.30
        if g < 0.15: return 0.50
        if g < 0.25: return 0.75
        return 1.0
    s_yoy = _to_score(yoy) if yoy is not None else None
    s_cagr = _to_score(cagr_3y) if cagr_3y is not None else None
    if s_yoy is None and s_cagr is None:
        return None
    if s_yoy is None:
        return s_cagr
    if s_cagr is None:
        return s_yoy
    return 0.6 * s_yoy + 0.4 * s_cagr


def compute_quality_v8(value: dict) -> dict:
    """v8 Quality: net margin (35%) + FCF margin (35%) + ROIC (30%).
    Piotroski/Altman are NOT in the composite — they remain on the Stock
    dict and dashboard for visual sanity-checks only.
    Returns {"score": float|None, "_evaluated": bool, ...components}."""
    nm = value.get("net_margin")
    fm = value.get("fcf_margin")
    roic = value.get("roic_avg")
    # Net margin ladder (absolute): >20% best, 10-20%, 5-10%, 0-5%, <0%
    nm_score = _ladder(nm, [0.0, 0.05, 0.10, 0.20], [0.0, 0.25, 0.5, 0.75, 1.0])
    # FCF margin ladder: >15%, 8-15%, 3-8%, 0-3%, <0%
    fm_score = _ladder(fm, [0.0, 0.03, 0.08, 0.15], [0.0, 0.25, 0.5, 0.75, 1.0])
    # ROIC ladder: >20%, 15-20%, 10-15%, 5-10%, <5%
    rc_score = _ladder(roic, [0.05, 0.10, 0.15, 0.20], [0.0, 0.25, 0.5, 0.75, 1.0])
    components = []
    weight_used = 0
    if nm is not None:
        components.append(("net_margin", nm_score, 0.35))
        weight_used += 0.35
    if fm is not None:
        components.append(("fcf_margin", fm_score, 0.35))
        weight_used += 0.35
    if roic is not None and roic != 0:
        components.append(("roic", rc_score, 0.30))
        weight_used += 0.30
    if weight_used == 0:
        return {"score": None, "_evaluated": False,
                "net_margin": nm, "fcf_margin": fm, "roic": roic}
    score = sum(s * (w / weight_used) for _, s, w in components)
    return {"score": round(score, 4), "_evaluated": True,
            "net_margin": nm, "fcf_margin": fm, "roic": roic,
            "net_margin_score": nm_score, "fcf_margin_score": fm_score,
            "roic_score": rc_score}


def compute_growth_v8(value: dict) -> dict:
    """v8 Growth: revenue + EPS + FCF, each = 60/40 TTM-YoY / 3yr-CAGR.
    Each sub-metric weighted 33/33/34. Sub-metric returns None if both
    YoY and 3yr are missing → weight redistributed."""
    rev = _score_growth(value.get("revenue_yoy"), value.get("revenue_cagr_3y"))
    eps = _score_growth(value.get("eps_yoy"), value.get("eps_cagr_3y"))
    fcf = _score_growth(value.get("fcf_yoy"), value.get("fcf_cagr_3y"))
    components = []
    weight_used = 0
    if rev is not None:
        components.append(("revenue", rev, 0.33)); weight_used += 0.33
    if eps is not None:
        components.append(("eps", eps, 0.33)); weight_used += 0.33
    if fcf is not None:
        components.append(("fcf", fcf, 0.34)); weight_used += 0.34
    if weight_used == 0:
        return {"score": None, "_evaluated": False}
    score = sum(s * (w / weight_used) for _, s, w in components)
    return {"score": round(score, 4), "_evaluated": True,
            "revenue_score": rev, "eps_score": eps, "fcf_score": fcf}


def compute_value_v8(value: dict, upside: dict) -> dict:
    """v8 Value: intrinsic upside (40%) + P/FCF (30%) + earnings yield (30%).
    Intrinsic upside uses the combined BVPS+analyst figure already produced
    by compute_upside_score (renamed: result['intrinsic_upside'])."""
    # Intrinsic upside ladder: from compute_upside_score in % (e.g. +25 = 25%)
    iu_pct = upside.get("intrinsic_upside") if upside else None
    iu_score = _ladder(iu_pct, [-30, -15, 0, 15, 30],
                       [0.0, 0.15, 0.35, 0.6, 0.85, 1.0])
    # P/FCF: lower is better. <15 = best, 15-25, 25-40, 40-60, >60 worst
    p_fcf = value.get("p_fcf")
    if p_fcf is None or p_fcf <= 0:
        pf_score = None
    else:
        # invert: small ratio → high score
        if p_fcf < 15:    pf_score = 1.0
        elif p_fcf < 25:  pf_score = 0.75
        elif p_fcf < 40:  pf_score = 0.5
        elif p_fcf < 60:  pf_score = 0.25
        else:             pf_score = 0.0
    # Earnings yield: >8% best, 5-8%, 3-5%, 1-3%, <1%
    ey = value.get("earnings_yield")
    if ey is None or ey <= 0:
        ey_score = None
    else:
        ey_score = _ladder(ey, [0.01, 0.03, 0.05, 0.08],
                           [0.0, 0.25, 0.5, 0.75, 1.0])

    components = []
    weight_used = 0
    if iu_score is not None and upside and upside.get("_evaluated"):
        components.append(("intrinsic_upside", iu_score, 0.40))
        weight_used += 0.40
    if pf_score is not None:
        components.append(("p_fcf", pf_score, 0.30))
        weight_used += 0.30
    if ey_score is not None:
        components.append(("earnings_yield", ey_score, 0.30))
        weight_used += 0.30
    if weight_used == 0:
        return {"score": None, "_evaluated": False}
    score = sum(s * (w / weight_used) for _, s, w in components)
    return {"score": round(score, 4), "_evaluated": True,
            "intrinsic_upside_score": iu_score, "p_fcf_score": pf_score,
            "earnings_yield_score": ey_score}


def qualifies_momentum_v8(tech: dict, value: dict, market_cap: float = 0) -> tuple:
    """Universe gate for Momentum mode. Stocks failing the gate get a `None`
    composite for this mode and are filtered out of the Momentum-sorted list.
    Returns (passes_bool, list_of_failure_reasons).

    Gate criteria (Apr 2026, locked):
      • price > sma_200       — trend intact
      • off-52wk-high ≤ 25%   — not deeply broken; some pullback OK
      • bull_score ≥ 5/10     — minimum technical confirmation
      • revenue_yoy ≥ -10%    — not actively melting (allows mature/cyclical)

    Symmetric in spirit to the FA gate: each gate enforces a structural
    setup, not a fundamental quality threshold (those are scored, not gated).
    """
    fails = []
    price = tech.get("price", 0) or 0
    sma200 = tech.get("sma200", 0) or 0
    yh = tech.get("year_high", 0) or 0
    yl = tech.get("year_low", 0) or 0
    bull = tech.get("bull_score", 0) or 0
    rev_yoy = value.get("revenue_yoy") if value.get("revenue_yoy") is not None else 0

    if price <= 0 or sma200 <= 0:
        fails.append("missing_price_or_sma200")
    elif price < sma200:
        fails.append("below_sma200")

    if yh > 0:
        off_high = (yh - price) / yh
        if off_high > 0.25:
            fails.append(f"off_52wh_{off_high*100:.0f}%")
    else:
        fails.append("missing_year_high")

    if bull < 5:
        fails.append(f"bull_score_{bull}")

    if rev_yoy < -0.10:
        fails.append(f"rev_yoy_{rev_yoy*100:.0f}%")

    return (len(fails) == 0, fails)


def qualifies_fallen_angel_v8(tech: dict, value: dict, raw_quality: dict,
                              market_cap: float = 0) -> tuple:
    """=== DISABLED v1.2 (May 2026) === Preserved for revival.

    The FA gate diverged from the FA flag (in compute_fallen_angel_flags):
    gate described "quality-deep-value oversold" (Pio≥7 + Altman Z>2.5 +
    drawdown>35% + ROE>12%), flag describes "high-growth oversold"
    (rev>15% + RSI<40 + composite<0.50). Different stocks. Bruno chose the
    flag as the single source of truth (May 11 2026). compute_composite_v8
    no longer calls this gate; every stock gets a composite_fallen_angel.
    Basket selection by paper_strategy_runner_fa via fallen_angel_flag.

    To revive: remove the early `return (True, [])` below; the original
    gate body follows for reference.
    """
    return (True, [])
    # ─── Original gate (preserved below, never reached) ───
    # fails = []
    # price = tech.get("price", 0) or 0
    # sma200 = tech.get("sma200", 0) or 0
    # yh = tech.get("year_high", 0) or 0
    # pio = raw_quality.get("piotroski", 0) if raw_quality else 0
    # altz = raw_quality.get("altman_z", 0) if raw_quality else 0
    # roe = value.get("roe_avg", 0) if value else 0
    #
    # if price <= 0 or yh <= 0:
    #     fails.append("missing_price_or_high")
    # else:
    #     drawdown = (yh - price) / yh
    #     if drawdown < 0.35:
    #         fails.append(f"drawdown_only_{drawdown*100:.0f}%")
    #
    # if sma200 <= 0:
    #     fails.append("missing_sma200")
    # elif price >= sma200:
    #     fails.append("above_sma200")
    #
    # if pio < 7:
    #     fails.append(f"piotroski_{pio}")
    # if altz < 2.5:
    #     fails.append(f"altman_z_{altz:.2f}")
    # if roe < 0.12:
    #     fails.append(f"roe_avg_{roe*100:.0f}%")
    # if market_cap > 0 and market_cap < 2e9:
    #     fails.append(f"mkt_cap_{market_cap/1e9:.1f}B")
    #
    # return (len(fails) == 0, fails)


def compute_composite_v8(
    tech: dict, value: dict, upside: dict,
    smart_money: dict = None,
    mode: str = "momentum",
    raw_quality: dict = None, market_cap: float = 0,
) -> tuple:
    """Five-factor composite (v8). Returns (composite, signal, factors_v8,
    reasons, coverage).

    Mode-aware: 'momentum' uses bull_score; 'fallen_angel' uses reversal_score.
    Each sub-factor is None when no real data → weight redistributes across
    evaluated factors. Coverage gate caps composite at 0.75 if <4/5 evaluated.

    Apr 2026: smart_money sub-factor now sourced from the LTR-derived Smart
    Money Score (compute_smart_money_score). Replaces the previous fold of
    inst_flow + analyst + insider + transcript + earnings + congressional.
    `smart_money` arg is the dict returned by compute_smart_money_score.

    v1.2 (May 2026):
      - Fallen-Angel gate REMOVED: every stock gets a composite_fallen_angel
        score. Basket selection is done by paper_strategy_runner_fa via
        `fallen_angel_flag` (computed in compute_fallen_angel_flags). The
        prior gate (Piotroski≥7 + Altman Z>2.5 + drawdown>35% + ROE>12%)
        described "quality-deep-value oversold" while the flag describes
        "high-growth oversold" — different stocks. Bruno's call: flag is
        the source of truth, gate is dead.
      - Signal simplified to QUALIFIED / DISQUALIFIED. The prior
        BUY/HOLD/SELL/WATCH/STRONG BUY classification was confusing and
        unused by runners (which sort by composite, not signal).
      - Bearish safety net dropped (was: cap composite + force SELL when
        3+ of trend/momentum/prox/bull/composite were bearish). Composite
        now stands on its own; runners trust their cohort gates.
    Universe gate retained for momentum mode (qualifies_momentum_v8).
    """
    if mode == "fallen_angel":
        passes, gate_fails = True, []
    else:
        passes, gate_fails = qualifies_momentum_v8(tech, value, market_cap)

    f = {}

    # 1. Momentum — mode-dependent
    if mode == "fallen_angel":
        rev = tech.get("reversal_score", 0)
        f["momentum"] = rev / 10 if rev is not None else None
    else:
        bull = tech.get("bull_score", 0)
        f["momentum"] = bull / 10 if bull is not None else None

    # 2. Quality
    q = compute_quality_v8(value)
    f["quality"] = q["score"]

    # 3. Growth
    g = compute_growth_v8(value)
    f["growth"] = g["score"]

    # 4. Value
    val_block = compute_value_v8(value, upside)
    f["value"] = val_block["score"]

    # 5. Smart Money — sourced from compute_smart_money_score (LTR-derived)
    if smart_money and smart_money.get("_evaluated"):
        f["smart_money"] = smart_money.get("score")
    else:
        f["smart_money"] = None

    # ─── Coverage tracking ───
    evaluated = [k for k, v in f.items() if v is not None]
    missing = [k for k, v in f.items() if v is None]
    coverage = {
        "count": len(evaluated),
        "total": 5,
        "pct": len(evaluated) / 5,
        "evaluated": evaluated,
        "missing": missing,
    }

    # ─── Weight redistribution ───
    active = {k: WEIGHTS_V8[k] for k in evaluated}
    if active:
        missing_weight = sum(WEIGHTS_V8[k] for k in missing)
        total_active = sum(active.values())
        if missing_weight > 0:
            for k in active:
                active[k] += missing_weight * (active[k] / total_active)
        composite = sum(f[k] * active[k] for k in evaluated)
    else:
        composite = 0.0

    # ─── Coverage gate ───
    MIN_COVERAGE_V8 = 4
    COVERAGE_CAP_V8 = 0.75
    reasons = []
    if coverage["count"] < MIN_COVERAGE_V8:
        composite = min(composite, COVERAGE_CAP_V8)
        if composite == COVERAGE_CAP_V8:
            reasons.append(f"COVERAGE CAP: only {coverage['count']}/5 factors evaluated")

    if not passes:
        gate_msg = "GATE: " + ", ".join(gate_fails[:3])
        return (composite, "DISQUALIFIED", f, [gate_msg] + reasons, coverage)

    # v1.2 (May 2026): bearish safety override + BUY/HOLD/SELL signal
    # classification removed (Bruno #6 + #A.1). Stock score now stands as
    # computed; runners filter by their own cohort gates (Compounder flag,
    # FA flag, Momentum gate above) and sort by composite directly.
    return composite, "QUALIFIED", f, reasons, coverage

# ---------------------------------------------------------------------------
# v8 Compounder universe scoring (May 2026)
# ---------------------------------------------------------------------------
# Universe ranks ROE / P/B / OpMargin_delta across the qualified cohort
# (SP500 ex Financial Services / Insurance / Healthcare; equity > 0 implicit
# via roe/pb being None when equity ≤ 0). Equal-weight blend → 0..1 score.
# Stocks outside cohort get signal_compounder_us / _global = "DISQUALIFIED".
COMPOUNDER_EXCLUDED_SECTORS: set = {"Financial Services", "Insurance", "Healthcare"}
COMPOUNDER_US_MIN_MCAP: float = 2_000_000_000  # $2B floor for US cohort (v1.1)
# v1.2 (May 2026): switched US cohort gate from country=='US' to US-listed
# exchange. Catches foreign-domiciled non-ADR common shares listed on US
# exchanges: WIX (IL), Coupang (KR), MNDY (IL), Sea/SE (SG), NU (KY), GRAB
# (KY), CYBR (IL). Side effect: includes ADRs (TSM, BABA, ASML, NVO) — these
# are real common-stock equivalents and acceptable in the universe. Sector
# + mcap + metric gates still apply.
COMPOUNDER_US_EXCHANGES: set = {
    "NYSE", "NASDAQ", "AMEX", "NYSE Arca", "NYSEArca", "BATS",
    "NASDAQ Global Select", "NASDAQ Global Market", "NASDAQ Capital Market",
}


def _rank_compounder_cohort(cohort: list, score_attr: str, rank_attr: str,
                            signal_attr: str, label: str) -> None:
    """Shared helper: assigns score/rank/signal attributes for one cohort.
    Mutates each Stock in the cohort. Empty cohort is a no-op."""
    if not cohort:
        log.info(f"  Compounder/{label}: empty cohort — no scores assigned")
        return

    n = len(cohort)
    denom = max(n - 1, 1)

    sorted_roe = sorted(cohort, key=lambda x: x.roe_compounder, reverse=True)
    sorted_pb = sorted(cohort, key=lambda x: x.pb_compounder)              # lower better
    sorted_opd = sorted(cohort, key=lambda x: x.opmargin_delta_compounder, reverse=True)
    roe_idx = {s.symbol: i for i, s in enumerate(sorted_roe)}
    pb_idx = {s.symbol: i for i, s in enumerate(sorted_pb)}
    opd_idx = {s.symbol: i for i, s in enumerate(sorted_opd)}

    # v1.2 (May 2026): expose per-factor percentile breakdown alongside the
    # composite score so the frontend stock page can render a Compounder
    # breakdown card showing each factor's contribution. Field names use the
    # score_attr prefix so US and Global don't collide:
    #   compounder_score_us       → cmp_us_roe_pct, cmp_us_pb_pct, cmp_us_opd_pct
    #   compounder_score_global   → cmp_global_roe_pct, cmp_global_pb_pct, cmp_global_opd_pct
    # Note: percentiles, not raw values — they encode this stock's RANK in the
    # cohort (1.0 = best in cohort, 0.0 = worst). Score = mean of the three.
    factor_prefix = score_attr.replace("compounder_score_", "cmp_")
    scored = []
    for s in cohort:
        roe_p = 1.0 - (roe_idx[s.symbol] / denom)
        pb_p = 1.0 - (pb_idx[s.symbol] / denom)
        opd_p = 1.0 - (opd_idx[s.symbol] / denom)
        score = (roe_p + pb_p + opd_p) / 3.0
        setattr(s, score_attr, round(score, 4))
        setattr(s, f"{factor_prefix}_roe_pct", round(roe_p, 4))
        setattr(s, f"{factor_prefix}_pb_pct", round(pb_p, 4))
        setattr(s, f"{factor_prefix}_opd_pct", round(opd_p, 4))
        setattr(s, signal_attr, "QUALIFIED")
        scored.append(s)

    scored.sort(key=lambda x: getattr(x, score_attr), reverse=True)
    for i, s in enumerate(scored):
        setattr(s, rank_attr, i + 1)

    top5 = [(s.symbol, getattr(s, score_attr)) for s in scored[:5]]
    log.info(f"  Compounder/{label} cohort: {n} qualified — top-5 {top5}")


def compute_compounder_universe_scores(stocks: list) -> None:
    """Mutates stocks: assigns BOTH US and Global Compounder scores in one pass.
    Runs once after all per-stock fundamentals exist.

    US cohort:     listed on a US exchange (NYSE/NASDAQ/AMEX/etc.), mcap >=
                   COMPOUNDER_US_MIN_MCAP ($2B), ex Fin/Ins/HC, all 3 metrics
                   present. v1.2 (May 2026): switched from country=='US' to
                   exchange-based — catches WIX, Coupang, MNDY, etc. (foreign-
                   domiciled non-ADR common shares on US exchanges). Now also
                   includes ADRs (TSM/BABA/ASML/NVO) as a side effect; these
                   are legitimate common-stock equivalents.
    Global cohort: ex Fin/Ins/HC, all 3 metrics present (no exchange/mcap gate).
    """
    us_cohort = []
    global_cohort = []
    counters = {"excluded_sector": 0, "missing_metric": 0,
                "us_failed_exchange": 0, "us_failed_mcap": 0,
                "global_qualified": 0, "us_qualified": 0}

    for s in stocks:
        # Reset both signals every call (stocks may move in/out between scans).
        s.signal_compounder_us = "DISQUALIFIED"
        s.signal_compounder_global = "DISQUALIFIED"

        if s.sector in COMPOUNDER_EXCLUDED_SECTORS:
            counters["excluded_sector"] += 1
            continue
        if (s.roe_compounder is None or s.pb_compounder is None
                or s.opmargin_delta_compounder is None):
            counters["missing_metric"] += 1
            continue

        # Global cohort: every qualifying stock ex Fin/Ins/HC.
        global_cohort.append(s)
        counters["global_qualified"] += 1

        # US cohort: subset listed on a US exchange + mcap >= $2B.
        exch = (s.exchange or "").strip()
        if exch not in COMPOUNDER_US_EXCHANGES:
            counters["us_failed_exchange"] += 1
            continue
        mcap = s.market_cap or 0
        if mcap < COMPOUNDER_US_MIN_MCAP:
            counters["us_failed_mcap"] += 1
            continue
        us_cohort.append(s)
        counters["us_qualified"] += 1

    log.info(
        f"  Compounder cohorts: "
        f"US={counters['us_qualified']}, "
        f"Global={counters['global_qualified']} "
        f"(excluded: sector={counters['excluded_sector']}, "
        f"missing_metric={counters['missing_metric']}, "
        f"us_failed_exchange={counters['us_failed_exchange']}, "
        f"us_failed_mcap={counters['us_failed_mcap']})"
    )

    _rank_compounder_cohort(
        us_cohort,
        score_attr="compounder_score_us",
        rank_attr="compounder_rank_us",
        signal_attr="signal_compounder_us",
        label="US",
    )
    _rank_compounder_cohort(
        global_cohort,
        score_attr="compounder_score_global",
        rank_attr="compounder_rank_global",
        signal_attr="signal_compounder_global",
        label="Global",
    )


def compute_fallen_angel_flags(stocks: list) -> None:
    """Informational alert flag — NOT a portfolio gate. Per v8 handover:
    rev_growth_1y > 15% AND RSI < 40 AND composite < 0.50 AND price > $1
    AND volume > 100K. Frontend may surface as a small badge.
    """
    count = 0
    for s in stocks:
        rev_yoy = s.revenue_yoy or 0.0
        if (rev_yoy > 0.15
                and s.rsi and s.rsi < 40
                and s.price > 1
                and s.volume > 100_000):
            s.fallen_angel_flag = True
            count += 1
    log.info(f"  Fallen Angel alerts: {count} stocks flagged")


# ---------------------------------------------------------------------------
# 15. Main Screening Loop (Two-Pass Architecture)
# ---------------------------------------------------------------------------
def _compute_fund_features_for_ml(sym, price, value_data):
    """Extract fundamental features for ML model from already-loaded value data."""
    r = {}
    roe = value_data.get("roe_compounder")
    if roe is not None:
        r["f_roe"] = min(roe, 1.0) if roe > 0 else max(roe, -1.0)
    pb = value_data.get("pb_compounder")
    if pb is not None and pb > 0:
        r["f_pb"] = pb
    r["f_op_margin"] = value_data.get("net_margin")
    r["f_op_margin_delta"] = value_data.get("opmargin_delta_compounder")
    r["f_rev_growth"] = value_data.get("revenue_yoy")
    r["f_eps_growth"] = value_data.get("eps_yoy")
    r["f_buyback_yield"] = 0
    r["f_piotroski_pit"] = value_data.get("piotroski", 0)
    az = value_data.get("altman_z", 0)
    r["f_altman_z_pit"] = min(max(az, 0), 20) if az else 0
    r["f_current_ratio"] = 0
    r["f_ps"] = value_data.get("p_s", 0)
    r["f_pe"] = 0
    ey = value_data.get("earnings_yield", 0)
    if ey and ey > 0:
        r["f_pe"] = 1.0 / ey
    r["f_fcf_yield"] = value_data.get("fcf_margin", 0)
    r["f_gross_margin"] = value_data.get("gross_margin", 0)
    r["f_net_margin"] = value_data.get("net_margin", 0)
    r["f_roa"] = 0
    r["f_debt_equity"] = 0
    return r
  
def screen(symbols: list[str], top_n: int = TOP_N) -> list[Stock]:
    log.info(f"Pass 1: Cheap screen on {len(symbols)} stocks")
    quotes = get_quotes_batch(symbols)

    pass1 = []
    for sym, q in quotes.items():
        if q["price"] <= 0:
            continue

        # Pass 1: cheap data only
        tech = get_technicals(sym, q)
        if not tech:
            tech = {
                "rsi": 50.0, "macd_signal": "neutral", "adx": 0.0, "bb_pct": 0.5,
                "stoch_rsi": 50.0, "obv_trend": "flat", "bull_score": 0, "bull_reasons": [],
                "reversal_score": 0, "reversal_reasons": []
            }

        analyst = get_analyst(sym)

        # 5-year history filter (legacy) — no longer drops recent IPOs/spin-offs.
        # They stay in the scan for UI deep-dives and Theme discovery. The
        # downstream Compounder/Momentum runner models naturally gate them out if
        # fundamental data is missing.
        value = get_value(sym, q["price"], q.get("currency", "USD"))
        if value.get("_insufficient_history"):
            pass # Keep it!

        # Compute pass-1 sub-scores
        proximity = compute_52wk_proximity(q)
        earnings = compute_earnings_momentum(analyst)
        upside = compute_upside_score(analyst, value, q["price"])

        # Quality is the v7 13-factor input. Ensure piotroski is an int.
        if value.get("piotroski") is None:
            value["piotroski"] = 0
            value["altman_z"] = 0
        quality = compute_quality_score(value)

        # Catalyst (cheap-ish) — uses cached earnings calendar
        catalyst = compute_catalyst_score(sym, analyst)

        # NEW v7.2 cheap-pass factors:
        # • sector_momentum requires SECTOR_PERF_CACHE (preloaded once at scan start)
        # • institutional_flow + congressional are pass-2 only (US-only, slow)
        sec_mom = compute_sector_momentum(sym, q["price"], q.get("sma50", 0),
                                          q.get("sma200", 0),
                                          q.get("year_high", 0), q.get("year_low", 0))

        # May 2026: institutional + insider + congressional moved from pass-2
        # to pass-1 so every stock gets a full Smart Money Score and a
        # populated SentimentCard. Cost: ~6 extra FMP calls per stock
        # (positions-summary x2, holder-extract, insider-stats, senate-trades,
        # house-trades). At 0.04s rate limit ≈ 0.24s/stock added.
        # Transcripts (Claude API) + news stay in pass-2.
        # v1.2 (May 2026): get_institutional_flows and compute_institutional_flow
        # now share a single positions-summary fetch via
        # _fetch_institutional_positions_summary (deduplicated).
        inst_flow = compute_institutional_flow(sym)
        inst = get_institutional_flows(sym)
        cong = compute_congressional(sym)
        insider = get_insider_activity(sym)

        # Build Stock
        s = Stock(symbol=sym, price=q["price"], currency=q.get("currency", "USD"))
        s.exchange = SECTOR_EXCHANGE_MAP.get(sym, "")
        s.country = COUNTRY_MAP.get(sym, "")
        s.sector = SECTOR_MAP.get(sym, "")
        s.industry = INDUSTRY_MAP.get(sym, "")
        s.theme = get_modern_theme(s.industry)
        s.company_name = COMPANY_NAME_MAP.get(sym, "")
        s.sma50 = q.get("sma50", 0); s.sma200 = q.get("sma200", 0)
        s.year_high = q.get("year_high", 0); s.year_low = q.get("year_low", 0)
        s.market_cap = q.get("market_cap", 0); s.volume = q.get("volume", 0)
        s.rsi = tech["rsi"]; s.macd_signal = tech["macd_signal"]
        s.adx = tech["adx"]; s.bb_pct = tech["bb_pct"]; s.stoch_rsi = tech["stoch_rsi"]
        s.obv_trend = tech["obv_trend"]; s.bull_score = tech["bull_score"]
        s.reversal_score = tech.get("reversal_score", 0)
        s.target = analyst["target"]; s.upside = upside["consensus_upside"]
        s.grade_buy = analyst["grade_buy"]; s.grade_total = analyst["grade_total"]
        s.grade_score = analyst["grade_score"]
        s.eps_beats = analyst["eps_beats"]; s.eps_total = analyst["eps_total"]
        # PT revision velocity (Smart Money v1.1)
        s.pt_velocity_60d = analyst.get("pt_velocity_60d")
        s.pt_velocity_score = analyst.get("pt_velocity_score")
        s.revenue_cagr_3y = value["revenue_cagr_3y"]
        s.eps_cagr_3y = value["eps_cagr_3y"]
        s.roe_avg = value["roe_avg"]; s.roe_consistent = value["roe_consistent"]
        s.roic_avg = value["roic_avg"]
        s.gross_margin = value["gross_margin"]
        s.gross_margin_trend = value["gross_margin_trend"]
        s.piotroski = value["piotroski"]; s.altman_z = value["altman_z"]
        s.dcf_value = value["dcf_value"]
        s.owner_earnings_yield = value["owner_earnings_yield"]
        s.intrinsic_buffett = value["intrinsic_buffett"]
        s.intrinsic_avg = value["intrinsic_avg"]
        s.margin_of_safety = value["margin_of_safety"]
        s.value_score = value["value_score"];
        s.p_s = value["p_s"]
        s.proximity_52wk = proximity["proximity"]; s.proximity_score = proximity["score"]
        s.earnings_momentum = earnings["momentum"]; s.earnings_score = earnings["score"]
        s.upside_score = upside["score"]
        s.quality_score = quality["score"]
        s.catalyst_score = catalyst["score"]
        s.catalyst_flags = catalyst["flags"]
        s.has_catalyst = catalyst["has_catalyst"]
        s.days_to_earnings = catalyst.get("days_to_earnings", -1)

        # Pass-1 institutional + insider (moved from pass-2 in May 2026).
        # Pass-2 will overwrite with the same values for enriched stocks —
        # idempotent. Non-enriched stocks now have these fields populated
        # in the scan JSON, which feeds the SentimentCard for all stocks.
        s.insider_buy_ratio = insider["buy_ratio"]
        s.insider_net_buys = insider["net_buys"]
        s.insider_score = insider["score"]
        s.inst_holders_change = inst["holders_change"]
        s.inst_accumulation = inst["accumulation"]
        s.inst_score = inst["score"]

        # ─── v8 fields populated from value ───

        # ─── v8 fields populated from value ───
        s.net_margin = value.get("net_margin", 0.0)
        s.fcf_margin = value.get("fcf_margin", 0.0)
        s.revenue_yoy = value.get("revenue_yoy", 0.0)
        s.eps_yoy = value.get("eps_yoy", 0.0)
        s.fcf_yoy = value.get("fcf_yoy", 0.0)
        s.fcf_cagr_3y = value.get("fcf_cagr_3y", 0.0)
        s.p_fcf = value.get("p_fcf", 0.0)
        s.p_s = value.get("p_s", 0.0)
        s.earnings_yield = value.get("earnings_yield", 0.0)
        s.intrinsic_bvps = value.get("intrinsic_bvps", 0.0)
        s.bvps_recent_cagr = value.get("bvps_recent_cagr", 0.0)
        s.bvps_consistency = value.get("bvps_consistency", 0.0)
        s.bvps_upside = upside.get("buffett_upside", 0.0)  # repurposed for backward compat
        s.intrinsic_upside = upside.get("intrinsic_upside", 0.0)
        # v8 Compounder mode raw inputs (May 2026) — score computed at end
        # of screen() across the qualified cohort, not per-stock here.
        s.roe_compounder = value.get("roe_compounder")
        s.pb_compounder = value.get("pb_compounder")
        s.opmargin_delta_compounder = value.get("opmargin_delta_compounder")
        # Buffett 5y valuation (May 2026)
        s.buffett_method = value.get("buffett_method", "")
        s.buffett_g_assumed = value.get("buffett_g_assumed", 0.0)
        s.buffett_roe_assumed = value.get("buffett_roe_assumed", 0.0)
        s.buffett_pe_median = value.get("buffett_pe_median", 0.0)
        s.buffett_eps_5y = value.get("buffett_eps_5y", 0.0)
        s.buffett_future_price = value.get("buffett_future_price", 0.0)
        s.buffett_fair_value = value.get("buffett_fair_value", 0.0)
        s.buffett_evaluated = value.get("buffett_evaluated", False)
        s.buffett_fallback_reason = value.get("buffett_fallback_reason", "")
        s.buffett_history = value.get("buffett_history", {})
        
        # Wire 9 valuation methodologies fields
        s.rd_capitalized_dcf = value.get("rd_capitalized_dcf", 0.0)
        s.owner_earnings = value.get("owner_earnings", 0.0)
        s.epv_value = value.get("epv_value", 0.0)
        s.graham_revised = value.get("graham_revised", 0.0)
        s.iv15_deep_value = value.get("iv15_deep_value", 0.0)
        
        s.dcf_fcff_mos = value.get("dcf_fcff_mos", -1.0)
        s.rd_capitalized_dcf_mos = value.get("rd_capitalized_dcf_mos", -1.0)
        s.owner_earnings_mos = value.get("owner_earnings_mos", -1.0)
        s.epv_mos = value.get("epv_mos", -1.0)
        s.graham_revised_mos = value.get("graham_revised_mos", -1.0)
        s.iv15_deep_value_mos = value.get("iv15_deep_value_mos", -1.0)
        
        s.net_debt_local = value.get("net_debt_local", 0.0)
        s.ebit_local = value.get("ebit_local", 0.0)
        s.depreciation_local = value.get("depreciation_local", 0.0)
        s.net_debt = value.get("net_debt", 0.0)
        s.ebit = value.get("ebit", 0.0)
        s.depreciation = value.get("depreciation", 0.0)
        s.gross_profit = value.get("gross_profit", 0.0)
        s.total_assets = value.get("total_assets", 0.0)
        s.eps_latest = value.get("eps_latest", 0.0)
        s.fx_to_report = value.get("fx_to_report", 1.0)
        s.fx_to_price = value.get("fx_to_price", 1.0)
      
        # Override method label when upside used the analyst fallback
        if upside.get("_valuation_method") == "fallback_analyst":
            s.buffett_method = "fallback_analyst"
            if not s.buffett_fallback_reason:
                s.buffett_fallback_reason = upside.get("_fallback_reason", "")

        # Stash raw scores for pass-2 composite (deferred until enrichment)
        s._raw = {
            "tech": tech, "analyst": analyst, "value": value,
            "proximity": proximity, "earnings": earnings,
            "upside": upside, "quality": quality, "catalyst": catalyst,
            "sec_mom": sec_mom,
            "inst_flow": inst_flow, "inst": inst,
            "cong": cong, "insider": insider,
        }
        pass1.append(s)

    log.info(f"Pass 1 complete: {len(pass1)} stocks scored cheaply")

    # Pass 2: enrich top stocks with expensive data (transcripts, institutional)
    # Sort by pass-1 cheap-data composite to pick enrichment candidates
    def cheap_score(s):
        # Quick-and-dirty pass-1 ranking score: bull_score + proximity + upside + quality
        return (s.bull_score / 10) + s.proximity_score + s.upside_score + s.quality_score

    pass1.sort(key=cheap_score, reverse=True)

    # Pass 2 enrichment cohort: top-30 by cheap composite UNION stocks with
    # intrinsic_upside ≥ 20%. The top-30 catches momentum leaders that may
    # have compressed upside; the upside floor catches deep-value names that
    # cheap_score under-ranks. Dedup preserves order (top-30 first).
    UPSIDE_FLOOR_PCT = 20.0
    top_n_pool = pass1[:ENRICH_TOP_N]
    top_n_syms = {s.symbol for s in top_n_pool}
    upside_extra = [
        s for s in pass1[ENRICH_TOP_N:]
        if s.intrinsic_upside is not None
        and s.intrinsic_upside >= UPSIDE_FLOOR_PCT
        and s.symbol not in top_n_syms
    ]
    enrich_pool = top_n_pool + upside_extra
    log.info(
        f"Pass 2 cohort: top-{ENRICH_TOP_N} ({len(top_n_pool)}) "
        f"+ upside≥{UPSIDE_FLOOR_PCT:.0f}% extras ({len(upside_extra)}) "
        f"= {len(enrich_pool)} stocks"
    )

    enriched_results = []
    _options_spread_ok = 0
    _options_spread_fail = 0
    _options_iv_ok = 0
    for s in enrich_pool:
        sym = s.symbol
        raw = s._raw

        # Pass-2 enrichment: only truly expensive calls remain (transcript
        # hits Claude API, news is pass-2 to save FMP quota). insider, inst,
        # inst_flow, cong all moved to pass-1 in May 2026.
        insider = raw["insider"]
        inst = raw["inst"]
        inst_flow = raw["inst_flow"]
        cong = raw["cong"]
        transcript = get_transcript_sentiment(sym)
        # Re-fetch news (cheap, but only for top-30 to save calls)
        news = get_news_sentiment(sym)
        catastrophe = compute_catastrophe(raw["tech"], raw["value"], raw["analyst"], insider)

        # Populate enriched fields on Stock
        s.insider_buy_ratio = insider["buy_ratio"]
        s.insider_net_buys = insider["net_buys"]
        s.insider_score = insider["score"]
        s.inst_holders_change = inst["holders_change"]
        s.inst_accumulation = inst["accumulation"]
        s.inst_score = inst["score"]
        s.transcript_sentiment = transcript["sentiment"]
        s.transcript_summary = transcript.get("summary", "")
        s.transcript_score = transcript["score"]
        s.news_sentiment = news["sentiment"]; s.news_score = news["score"]
        s.catastrophe_score = catastrophe["score"]

        # Smart Money Score (Apr 2026) — must be computed BEFORE compute_composite_v8
        # since v8 now reads its smart_money sub-factor from this score.
        # None for non-US stocks (institutional_flow data unavailable).
        sec_mom = raw["sec_mom"]
        sm = compute_smart_money_score(
            institutional_flow=inst_flow,
            institutional=inst,
            quality=raw["quality"],
            sector_momentum=sec_mom,
            congressional=cong,
            sma50=raw["tech"].get("sma50", 0),
            sma200=raw["tech"].get("sma200", 0),
            pt_velocity_score=analyst.get("pt_velocity_score"),
        )
        s.smart_money_score = sm["score"]
        s.smart_money_components = sm["components"]
        s.smart_money_weight = sm["weight_evaluated"]

        # Compute v7 composite (13-factor, retained for diagnostics)
        composite_v7, _signal_v7, factors_v7, reasons_v7, coverage_v7 = compute_composite_v7(
            raw["tech"], raw["analyst"], raw["value"], s.price,
            insider, raw["proximity"], raw["earnings"],
            raw["upside"], raw["quality"], raw["catalyst"],
            transcript, inst, inst_flow, sec_mom, cong,
        )

        # Compute v8 composite — both modes (Option B: dual mode for UI toggle)
        comp_mom, sig_mom, factors_mom, reasons_mom, coverage_mom = compute_composite_v8(
            raw["tech"], raw["value"], raw["upside"],
            smart_money=sm,
            mode="momentum",
            raw_quality=raw["value"], market_cap=s.market_cap,
        )
        comp_fa, sig_fa, factors_fa, reasons_fa, coverage_fa = compute_composite_v8(
            raw["tech"], raw["value"], raw["upside"],
            smart_money=sm,
            mode="fallen_angel",
            raw_quality=raw["value"], market_cap=s.market_cap,
        )

        s.factor_scores = factors_v7        # legacy 13-factor for radar
        s.factors_v8 = factors_mom          # default v8 view = momentum
        s.factors_v8_momentum = factors_mom
        s.factors_v8_fallen_angel = factors_fa
        s.reasons = raw["tech"].get("bull_reasons", []) + reasons_mom
        s.factor_coverage = coverage_v7["count"]
        s.factor_coverage_pct = coverage_v7["pct"]
        s.factors_evaluated = coverage_v7["evaluated"]
        s.factors_missing = coverage_v7["missing"]
        s.mode = "momentum"  # default; frontend can flip via toggle

        # ML probability + fundamental features for ML model
        if HAS_ML_MODEL:
            s._fund_features = _compute_fund_features_for_ml(s.symbol, s.price, raw["value"])
        s.hit_prob = predict_hit_prob(s)
        # v3 multi-target predictions (30d/60d probability + drawdown)
        if ML_MODEL_VERSION == "v3":
            v3_preds = predict_time_model_v3(s)
            s.hit_prob_10pct_30d = v3_preds["hit_10pct_30d"]
            s.hit_prob_10pct_60d = v3_preds["hit_10pct_60d"]
            s.hit_prob_30d = v3_preds["hit_20pct_30d"]
            s.hit_prob_60d = v3_preds["hit_20pct_60d"]
            s.expected_dd_30d = v3_preds["expected_dd_30d"]
            s.expected_dd_60d = v3_preds["expected_dd_60d"]


        # Drop the _raw stash before output
        if hasattr(s, "_raw"):
            delattr(s, "_raw")

        enriched_results.append(s)



    # Pass 1 stocks NOT enriched still get a v7-only composite (cheap data only,
    # composite-band signal). They appear in the bottom of the JSON table for
    # context but with v8 factors null. This matches the user's request to
    # show enriched stocks at top; non-enriched still display.
    enriched_syms = {s.symbol for s in enrich_pool}
    non_enriched = [s for s in pass1 if s.symbol not in enriched_syms]
    for s in non_enriched:
        raw = s._raw
        # May 2026: pass-1 now has full institutional/insider/congressional.
        # Only transcript remains pass-2-only at this layer.
        composite_v7, signal_v7, factors_v7, reasons_v7, coverage_v7 = compute_composite_v7(
            raw["tech"], raw["analyst"], raw["value"], s.price,
            raw["insider"], raw["proximity"], raw["earnings"], raw["upside"],
            raw["quality"], raw["catalyst"],
            None, raw["inst"], raw["inst_flow"], raw["sec_mom"], raw["cong"],
        )
        # Smart Money Score now fully populated for non-enriched stocks too.
        # v1.3: transcript removed from SMART$ — pass-1 vs pass-2 difference
        # now comes from pt_velocity_score (available only after get_analyst).
        sm = compute_smart_money_score(
            institutional_flow=raw["inst_flow"],
            institutional=raw["inst"],
            quality=raw["quality"],
            sector_momentum=raw["sec_mom"],
            congressional=raw["cong"],
            sma50=raw["tech"].get("sma50", 0),
            sma200=raw["tech"].get("sma200", 0),
            pt_velocity_score=None,  # pass-1: no get_analyst() call; PT velocity unavailable
        )
        s.smart_money_score = sm["score"]      # None — core-4 not met
        s.smart_money_components = sm["components"]
        s.smart_money_weight = sm["weight_evaluated"]

        # v8 composite without pass-2 enrichment
        comp_mom, sig_mom, factors_mom, _r_mom, _cov_mom = compute_composite_v8(
            raw["tech"], raw["value"], raw["upside"],
            smart_money=sm,
            mode="momentum",
            raw_quality=raw["value"], market_cap=s.market_cap,
        )
        comp_fa, sig_fa, factors_fa, _r_fa, _cov_fa = compute_composite_v8(
            raw["tech"], raw["value"], raw["upside"],
            smart_money=sm,
            mode="fallen_angel",
            raw_quality=raw["value"], market_cap=s.market_cap,
        )
        s.factor_scores = factors_v7
        s.factors_v8 = factors_mom
        s.factors_v8_momentum = factors_mom
        s.factors_v8_fallen_angel = factors_fa
        s.reasons = raw["tech"].get("bull_reasons", []) + reasons_v7
        s.factor_coverage = coverage_v7["count"]
        s.factor_coverage_pct = coverage_v7["pct"]
        s.factors_evaluated = coverage_v7["evaluated"]
        s.factors_missing = coverage_v7["missing"]
        s.hit_prob = 0.0  # not enriched

        if hasattr(s, "_raw"):
            delattr(s, "_raw")

    # Combine enriched + non-enriched, sort by symbol ascending
    all_results = enriched_results + non_enriched
    all_results.sort(key=lambda s: s.symbol)

    # ─── Massive options enrichment (ALL US stocks) ───
    if OPTIONS_AVAILABLE and options_enrich_stock:
        log.info("Massive Options: enriching ALL US stocks with options data...")
        for s in all_results:
            if s.country == "US":
                try:
                    _earnings_date = None
                    if hasattr(s, 'days_to_earnings') and s.days_to_earnings is not None and s.days_to_earnings >= 0:
                        _earnings_date = (datetime.now() + timedelta(days=s.days_to_earnings)).strftime("%Y-%m-%d")
                    
                    _target_dte = 60 if getattr(s, "hit_prob_60d", 0.0) > 0.0 else 35
                    options_data = options_enrich_stock(
                        symbol=s.symbol,
                        composite=0.0,
                        hit_prob=s.hit_prob,
                        earnings_date=_earnings_date,
                        collect_term_structure=True,
                        collect_earnings_move=True,
                        target_dte=_target_dte
                    )
                    if options_data:
                        s.options_iv_current = options_data.get("iv_current")
                        s.options_iv_rank = options_data.get("iv_rank")
                        s.options_iv_samples = options_data.get("iv_samples", 0)
                        s.options_spread = options_data.get("spread")
                        if s.options_spread:
                            _options_spread_ok += 1
                        else:
                            _options_spread_fail += 1
                        if s.options_iv_current is not None:
                            _options_iv_ok += 1
                        s.options_pc_ratio = options_data.get("pc_ratio")
                        s.options_pc_oi_ratio = options_data.get("pc_oi_ratio")
                        s.options_skew_25d = options_data.get("skew_25d")
                        s.options_total_open_interest = options_data.get("total_open_interest")
                        s.options_iv_30d = options_data.get("iv_30d")
                        s.options_iv_60d = options_data.get("iv_60d")
                        s.options_iv_90d = options_data.get("iv_90d")
                        s.options_term_structure = options_data.get("term_structure")
                        s.options_implied_earnings_move = options_data.get("implied_earnings_move")
                except Exception as e:
                    log.warning(f"  {s.symbol}: Massive Options enrichment failed: {e}")
                    
        if _options_iv_ok > 0 or _options_spread_ok > 0 or _options_spread_fail > 0:
            log.info(f"Massive Options summary: IV={_options_iv_ok}, "
                     f"spreads={_options_spread_ok}/{_options_spread_ok + _options_spread_fail} "
                     f"({_options_spread_fail} failed)")

    # v8 Compounder universe scoring (May 2026, v1.1) — runs once after every
    # stock has its raw PIT inputs (roe_compounder / pb_compounder /
    # opmargin_delta_compounder) populated. Stocks outside each qualified
    # cohort get signal_compounder_us / _global = 'DISQUALIFIED' and the
    # corresponding score/rank = None. See compute_compounder_universe_scores
    # for the US (country+mcap) and Global cohort definitions.
    log.info("v8 Compounder: ranking US + Global cohorts")
    compute_compounder_universe_scores(all_results)

    # v8 Fallen Angel alert flag (May 2026) — informational only.
    log.info("v8 Fallen Angel: flagging alert candidates")
    compute_fallen_angel_flags(all_results)

    # Macro regime overlay (v8) — fetch at scan-end so it's one-time per scan.
    # Returns dict with regime, score, sub_scores, features. Failure is non-
    # fatal: the scan results are valid without macro; the frontend ribbon
    # simply won't render.
    macro_data = None
    if HAS_MACRO:
        try:
            macro_data = fetch_macro_regime_v8(fmp)
            log.info(f"Macro v8: {macro_data.get('regime', '?')} "
                     f"(score={macro_data.get('score', '?')})")
        except Exception as e:
            log.warning(f"Macro regime v8 fetch failed (non-fatal): {e}")

    return all_results, macro_data

# ---------------------------------------------------------------------------
# 16. Output / Reporting
# ---------------------------------------------------------------------------

def format_report(stocks: list[Stock], top_n: int = TOP_N, region: str = "", macro: dict = None) -> str:
    lines = []
    lines.append("=" * 100)
    lines.append(f"CB SCREENER v7.2 — {region.upper() if region else 'GLOBAL'}")
    lines.append(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 100)

    # Top picks (show first top_n stocks in the scan list)
    top = stocks[:top_n]
    lines.append(f"\nTOP {len(top)} BY SYMBOL:\n")
    lines.append(f"{'#':>3} {'SYM':<10} {'PRICE':>10} {'MOS':>6} {'CLASS':<14} {'BULL':>5} {'UPS%':>6} {'QUAL':>5} {'COV':>4}")
    lines.append("-" * 90)
    for i, s in enumerate(top, 1):
        lines.append(
            f"{i:>3} {s.symbol:<10} {s.price:>10,.2f} {s.margin_of_safety:>6.2f} "
            f"{s.classification:<14} {s.bull_score:>5} {s.upside:>+6.1f} "
            f"{s.quality_score:>5.2f} {s.factor_coverage:>2}/{len(ALL_FACTORS):<2}"
        )

    # v1.2 (May 2026): "SIGNAL DISTRIBUTION" section removed — signal field
    # (BUY/HOLD/SELL) eliminated. Composite distribution can be inferred from
    # the TOP listing above.

    return "\n".join(lines)


def send_email(subject: str, body: str):
    if not (SMTP_USER and SMTP_PASS and EMAIL_TO):
        log.info("SMTP not configured — email skipped")
        return
    try:
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = EMAIL_TO
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
        log.info(f"Email sent to {EMAIL_TO}")
    except Exception as e:
        log.warning(f"Email failed: {e}")


def log_signals(stocks: list[Stock], path: str = SIGNAL_LOG):
    """Append today's high-MoS stocks to history JSON. Used for hit-rate tracking."""
    today = datetime.now().strftime("%Y-%m-%d")
    record = {
        "date": today,
        "signals": [
            {
                "symbol": s.symbol,
                "margin_of_safety": round(s.margin_of_safety, 4),
                "price": s.price,
                "classification": s.classification,
                "factor_coverage": s.factor_coverage,
                "factor_coverage_pct": round(s.factor_coverage_pct, 4),
            }
            for s in stocks if s.margin_of_safety >= 0.20
        ],
    }
    history = []
    if os.path.exists(path):
        try:
            with open(path) as f:
                history = json.load(f)
        except json.JSONDecodeError:
            log.warning(f"signal_history.json corrupt — starting fresh")
    history.append(record)
    with open(path, "w") as f:
        json.dump(history, f, indent=2)
    log.info(f"Signal history updated: {path}")


# ---------------------------------------------------------------------------
# 17. GCS Upload
# ---------------------------------------------------------------------------

GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")


def gcs_upload(blob_path: str, payload: dict) -> bool:
    """Upload JSON payload to GCS. Returns True on success."""
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(payload, default=str, indent=2),
            content_type="application/json",
        )
        return True
    except Exception as e:
        log.warning(f"GCS upload failed ({blob_path}): {e}")
        return False


def gcs_download(blob_path: str) -> Optional[dict]:
    """Download JSON payload from GCS. Returns dict or None on failure."""
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(blob_path)
        if not blob.exists():
            return None
        text = blob.download_as_text()
        return json.loads(text)
    except Exception as e:
        log.debug(f"GCS download miss/failed ({blob_path}): {e}")
        return None


def save_scan_to_gcs(stocks: list[Stock], region: str = "global", macro: dict = None):
    """Save scan results to GCS — both as latest_{region} and dated archive."""
    # 2026-05-05: scan_date is a full tz-aware ISO timestamp again. Frontend
    # parses this with `new Date(...).toLocaleString(...)` to render the
    # "last scan" label; if it's a date-only string (YYYY-MM-DD) JS interprets
    # it as UTC midnight and shows ~02:00 CEST regardless of when the scan ran.
    # The previously-introduced `scan_timestamp` field was never read by the
    # frontend, so just put the timestamp back in `scan_date` and drop the
    # extra field. Downstream consumers (monitor, portfolio, weekly email)
    # that expect a full ISO string keep working.
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    payload = {
        "scan_date": now.isoformat(),
        "region": region,
        "stock_count": len(stocks),
        "stocks": [asdict(s) for s in stocks],
    }
    # Macro regime overlay — embedded at top level so the frontend MacroRibbon
    # can render the current macro landscape without a separate API call.
    if macro:
        payload["macro"] = {
            "regime":     macro.get("regime"),
            "score":      macro.get("score"),
            "sub_scores": macro.get("sub_scores"),
            "version":    macro.get("version", "v7"),
        }
    # Write to local file
    try:
        local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "public", f"latest_{region}.json")
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, default=str, indent=2)
        log.info(f"Saved latest_{region} scan results locally to {local_path}")
        
        # Also write legacy latest.json pointer locally for compatibility if applicable
        if region in ("nasdaq100", "sp500"):
            legacy_path = os.path.join(os.path.dirname(local_path), "latest.json")
            with open(legacy_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, default=str, indent=2)
    except Exception as e:
        log.error(f"Failed to write local scan JSON files: {e}")

    # Latest
    gcs_upload(f"scans/latest_{region}.json", payload)
    # Dated archive
    gcs_upload(f"scans/{today}_{region}.json", payload)
    # Legacy "latest.json" pointer (keeps older frontend versions working)
    if region in ("nasdaq100", "sp500"):
        gcs_upload("scans/latest.json", payload)
    log.info(f"GCS upload complete: scans/latest_{region}.json + dated archive")

    # Post-scan hook: update P20 cycles, rolling health, and history
    try:
        import signal_tracker
        stock_dicts = [vars(s) if hasattr(s, '__dataclass_fields__') else s for s in stocks]
        signal_tracker.update_from_scan(stock_dicts, region)
    except Exception as e:
        log.warning(f"signal_tracker update_from_scan failed: {e}")


# ---------------------------------------------------------------------------
# 18. Portfolio Monitor Mode
# ---------------------------------------------------------------------------

def monitor_portfolio(state_path: str = PORTFOLIO_STATE):
    """
    Re-score current portfolio holdings.

    Apr 2026: monitor mode does NOT apply the 5-year history filter — by the
    time a position is held, the scan-time filter has already passed (or the
    user added the position deliberately, e.g. a recent IPO they're tracking).
    """
    log.info(f"Monitor mode: loading portfolio from {state_path}")

    state = gcs_download("portfolio/state.json")
    if not state:
        # local fallback
        if os.path.exists(state_path):
            with open(state_path) as f:
                state = json.load(f)
        else:
            log.warning("No portfolio state — nothing to monitor")
            return []

    positions = state.get("positions", [])
    if not positions:
        log.info("Portfolio empty — nothing to monitor")
        return []

    log.info(f"Re-scoring {len(positions)} positions")

    # Pull symbol list and current state
    symbols = [p["symbol"] for p in positions]
    quotes = get_quotes_batch(symbols)

    monitor_results = []
    for pos in positions:
        sym = pos["symbol"]
        q = quotes.get(sym)
        if not q or q["price"] <= 0:
            log.warning(f"  {sym}: no quote, skipping")
            continue

        tech = get_technicals(sym, q)
        if not tech:
            continue

        analyst = get_analyst(sym)
        # Note: monitor mode bypasses the 5-year hard filter (by definition the
        # position is already held). _insufficient_history flag is ignored here.
        value = get_value(sym, q["price"], q.get("currency", "USD"))
        proximity = compute_52wk_proximity(q)
        earnings_block = compute_earnings_momentum(analyst)
        upside = compute_upside_score(analyst, value, q["price"])
        # Quality requires Piotroski; if missing, monitor mode will return
        # a degraded composite but won't error out — wrap in try/except.
        if value.get("piotroski") is None:
            log.warning(f"  {sym}: missing Piotroski; using neutral quality score")
            quality = {"score": 0.5, "_evaluated": False}
        else:
            quality = compute_quality_score(value)
        catalyst = compute_catalyst_score(sym, analyst)
        sec_mom = compute_sector_momentum(sym, q["price"], q.get("sma50", 0),
                                          q.get("sma200", 0),
                                          q.get("year_high", 0), q.get("year_low", 0))
        # Pass-2 enrichment
        insider = get_insider_activity(sym)
        inst = get_institutional_flows(sym)
        inst_flow = compute_institutional_flow(sym)
        cong = compute_congressional(sym)
        transcript = get_transcript_sentiment(sym)

        # Smart Money Score for monitor (same inputs as scan pass-2)
        sm = compute_smart_money_score(
            institutional_flow=inst_flow,
            institutional=inst,
            quality=quality,
            sector_momentum=sec_mom,
            congressional=cong,
            sma50=q.get("sma50", 0),
            sma200=q.get("sma200", 0),
            pt_velocity_score=analyst.get("pt_velocity_score"),
        )

        # v7 13-factor composite (kept for diagnostics)
        composite_v7, signal_v7, factors_v7, reasons_v7, coverage_v7 = compute_composite_v7(
            tech, analyst, value, q["price"],
            insider, proximity, earnings_block, upside,
            quality, catalyst, transcript, inst, inst_flow, sec_mom, cong,
        )
        # v8 momentum composite (default mode for monitor)
        composite, signal, factors_v8, reasons, coverage = compute_composite_v8(
            tech, value, upside,
            smart_money=sm,
            mode="momentum",
            raw_quality=value, market_cap=q.get("market_cap", 0),
        )

        # Compute action: HOLD / TRIM / SELL / ADD based on composite drift
        entry_composite = pos.get("entry_composite", 0.7)
        cost_basis = pos.get("cost_basis", q["price"])
        pnl_pct = (q["price"] - cost_basis) / cost_basis if cost_basis > 0 else 0

        action = "HOLD"
        action_reasons = []
        if signal == "SELL":
            action = "SELL"
            action_reasons.append("Signal flipped to SELL")
        elif composite < 0.50 and entry_composite > 0.75:
            action = "TRIM"
            action_reasons.append(f"Composite dropped {entry_composite:.2f} → {composite:.2f}")
        elif pnl_pct < -0.20 and signal in ("HOLD", "WATCH"):
            action = "TRIM"
            action_reasons.append(f"Down {pnl_pct:.0%} with weak signal")
        elif composite > 0.85 and pnl_pct > 0.5:
            action = "TRIM"
            action_reasons.append(f"Take partial profits — up {pnl_pct:.0%}")
        elif signal == "STRONG BUY" and pnl_pct < 0.05:
            action = "ADD"
            action_reasons.append("STRONG BUY signal still active")

        monitor_results.append({
            "symbol": sym,
            "price": q["price"],
            "cost_basis": cost_basis,
            "pnl_pct": round(pnl_pct, 4),
            "shares": pos.get("shares", 0),
            "entry_date": pos.get("entry_date", ""),
            "entry_composite": entry_composite,
            "current_composite": round(composite, 4),
            "current_composite_v7": round(composite_v7, 4),
            "current_signal": signal,
            "action": action,
            "action_reasons": action_reasons,
            "factor_coverage": coverage["count"],
            "factor_coverage_pct": round(coverage["pct"], 4),
            "smart_money_score": sm["score"],
            "smart_money_components": sm["components"],
            "smart_money_weight": sm["weight_evaluated"],
        })

    # Persist monitor snapshot
    today = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "monitor_date": today,
        "monitor_timestamp": datetime.now().isoformat(),
        "positions": monitor_results,
    }
    gcs_upload("portfolio/monitor.json", payload)
    log.info(f"Monitor complete: {len(monitor_results)} positions re-scored")

    return monitor_results


# ---------------------------------------------------------------------------
# 18b. Paper-Trading Tracking State Helpers
# ---------------------------------------------------------------------------

_TRACKING_LOCAL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "public", "methodology_tracking.json"
)


def _load_tracking_state() -> Optional[dict]:
    """Load methodology_tracking.json from local disk (primary) or GCS (fallback)."""
    # Try local first
    try:
        if os.path.exists(_TRACKING_LOCAL_PATH):
            with open(_TRACKING_LOCAL_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and "tracking_year" in data:
                log.info(f"Loaded tracking state from local (year={data['tracking_year']})")
                return data
    except Exception as e:
        log.warning(f"Failed to read local tracking state: {e}")

    # Fallback to GCS
    try:
        data = gcs_download("scans/methodology_tracking.json")
        if data and "tracking_year" in data:
            log.info(f"Loaded tracking state from GCS (year={data['tracking_year']})")
            return data
    except Exception as e:
        log.debug(f"GCS tracking state not available: {e}")

    return None


def _save_tracking_state(tracking: dict, no_gcs: bool):
    """Persist tracking state to local disk and GCS."""
    tracking["last_updated"] = datetime.now(timezone.utc).isoformat() + "Z"
    try:
        os.makedirs(os.path.dirname(_TRACKING_LOCAL_PATH), exist_ok=True)
        with open(_TRACKING_LOCAL_PATH, "w", encoding="utf-8") as f:
            json.dump(tracking, f, indent=2)
        log.info(f"Saved tracking state locally to {_TRACKING_LOCAL_PATH}")
    except Exception as e:
        log.error(f"Failed to write local tracking state: {e}")

    if not no_gcs:
        try:
            gcs_upload("scans/methodology_tracking.json", tracking)
            log.info("Uploaded tracking state to GCS scans/methodology_tracking.json")
        except Exception as e:
            log.warning(f"GCS upload of tracking state failed: {e}")


def _append_rebalance_to_tracking(tracking: dict, methodology_picks: dict,
                                   rebalance_date: str,
                                   stock_price_map: Optional[dict] = None):
    """Append a rebalance record for each methodology and update YTD return.

    Args:
        stock_price_map: {symbol: price} map from all scanned stocks (not just picks).
                         Used for accurate exit price lookup. If None, falls back
                         to entry_price for exited stocks.

    For each methodology:
      1. Record the new portfolio (symbols + prices)
      2. Identify entries (new stocks) and exits (removed stocks)
      3. For exits: compute return vs entry price
      4. Recompute YTD by chaining equal-weight period returns
    """
    if "methodologies" not in tracking:
        tracking["methodologies"] = {}

    for key, meth_data in methodology_picks.items():
        picks = meth_data.get("picks", [])
        if key not in tracking["methodologies"]:
            tracking["methodologies"][key] = {
                "rebalances": [],
                "current_holdings": [],
                "all_exits_2026": [],
                "ytd_return": 0.0,
                "tracking_start": rebalance_date,
                "rebalance_count": 0
            }

        meth_track = tracking["methodologies"][key]

        # Skip if this rebalance date was already recorded
        existing_dates = {r["date"] for r in meth_track.get("rebalances", [])}
        if rebalance_date in existing_dates:
            log.debug(f"  {key}: rebalance {rebalance_date} already recorded, skipping")
            continue

        new_syms = {p["symbol"] for p in picks}
        prev_holdings = {h["symbol"]: h for h in meth_track.get("current_holdings", [])}
        prev_syms = set(prev_holdings.keys())

        # Entries: stocks in new portfolio but not in previous
        entries = []
        for p in picks:
            if p["symbol"] not in prev_syms:
                entries.append({
                    "symbol": p["symbol"],
                    "price": p["price"],
                    "date": rebalance_date,
                    "entry_metric": p.get("entry_metric", p.get("mos", 0.0))
                })

        # Exits: stocks in previous but not in new portfolio
        exits = []
        for sym, h in prev_holdings.items():
            if sym not in new_syms:
                # FIX (May 2026): Use stock_price_map for exit price lookup.
                # Previously searched meth_data["picks"] which only contains
                # the NEW portfolio — exited stocks are by definition not there.
                exit_price = h.get("entry_price", 0.0)
                exit_metric = 0.0
                if stock_price_map and sym in stock_price_map:
                    exit_price = stock_price_map[sym]
                # exit_metric is less critical — 0.0 is acceptable for tracking
                # since the methodology's MOS was already recorded at entry
                entry_p = h.get("entry_price", exit_price)
                entry_m = h.get("entry_metric", 0.0)
                perf = (exit_price - entry_p) / entry_p if entry_p > 0 else 0.0
                exit_rec = {
                    "symbol": sym,
                    "entry_price": round(entry_p, 4),
                    "entry_date": h.get("entry_date", ""),
                    "entry_metric": round(entry_m, 4),
                    "exit_price": round(exit_price, 4),
                    "exit_date": rebalance_date,
                    "exit_metric": round(exit_metric, 4),
                    "return": round(perf, 4)
                }
                exits.append(exit_rec)
                meth_track.setdefault("all_exits_2026", []).append(exit_rec)

        # Only record a rebalance if the portfolio actually changed
        # (screener runs daily for price updates, but rebalance is organic)
        if not entries and not exits:
            log.debug(f"  {key}: portfolio unchanged on {rebalance_date}, no rebalance recorded")
            continue

        # Build new current_holdings
        new_holdings = []
        count = len(picks)
        weight = 1.0 / count if count > 0 else 0.0
        for p in picks:
            sym = p["symbol"]
            if sym in prev_holdings:
                # Carry forward entry price, date, and metric
                new_holdings.append({
                    "symbol": sym,
                    "entry_price": prev_holdings[sym]["entry_price"],
                    "entry_date": prev_holdings[sym]["entry_date"],
                    "entry_metric": prev_holdings[sym].get("entry_metric", p.get("entry_metric", p.get("mos", 0.0))),
                    "weight": round(weight, 4)
                })
            else:
                new_holdings.append({
                    "symbol": sym,
                    "entry_price": round(p["price"], 4),
                    "entry_date": rebalance_date,
                    "entry_metric": round(p.get("entry_metric", p.get("mos", 0.0)), 4),
                    "weight": round(weight, 4)
                })

        # Record rebalance
        meth_track["rebalances"].append({
            "date": rebalance_date,
            "holdings": [p["symbol"] for p in picks],
            "entries": entries,
            "exits": exits
        })
        meth_track["current_holdings"] = new_holdings
        meth_track["rebalance_count"] = len(meth_track["rebalances"])


        # Recompute YTD return by chaining period returns
        # Each period: from rebalance[i] to rebalance[i+1]
        # Period return = mean of (exit_or_current_price - entry_price) / entry_price
        # for all holdings in that period
        meth_track["ytd_return"] = _compute_ytd_return(meth_track)

    log.info(f"Tracking: appended rebalance {rebalance_date} for {len(methodology_picks)} methodologies")


def _compute_ytd_return(meth_track: dict) -> float:
    """Compute YTD return by chaining equal-weight period returns across rebalances."""
    rebalances = meth_track.get("rebalances", [])
    if len(rebalances) < 2:
        return 0.0

    cumulative = 1.0
    for i in range(len(rebalances) - 1):
        curr_reb = rebalances[i]
        next_reb = rebalances[i + 1]

        # Find holdings at rebalance[i] and their prices at rebalance[i+1]
        curr_syms = set(curr_reb.get("holdings", []))
        if not curr_syms:
            continue

        # Build price map from rebalance[i] entries/holdings
        entry_prices = {}
        for h in meth_track.get("current_holdings", []):
            if h["symbol"] in curr_syms:
                entry_prices[h["symbol"]] = h["entry_price"]
        # Also check entries in this rebalance
        for e in curr_reb.get("entries", []):
            entry_prices[e["symbol"]] = e["price"]

        # Get prices at next rebalance from exits and continuing holdings
        next_prices = {}
        for x in next_reb.get("exits", []):
            next_prices[x["symbol"]] = x.get("exit_price", x.get("price", 0))
        for e in next_reb.get("entries", []):
            # Entries at next rebalance — these were already in the portfolio
            # Their price at next_reb date is in the entries record
            pass  # handled by holdings

        # For simplicity, use exit records + the fact that continuing stocks
        # have their next-rebalance price implicit in the rebalance data
        # This is a rough approximation; the backfill script computes this
        # more precisely using historical prices.

    # For now, return 0.0 — the backfill script sets the accurate YTD
    # and subsequent runs preserve it. Full chaining requires price lookups
    # that the live screener doesn't have easily accessible.
    return meth_track.get("ytd_return", 0.0)


def _rollover_tracking_year(tracking: dict, new_year: int):
    """Finalize the tracking year and roll into baseline history.

    1. Move each methodology's ytd_return into baseline_history[old_year]
    2. Drop the oldest baseline year to keep a 5-year window
    3. Reset tracking_year to new_year
    4. Clear rebalances, carry forward current_holdings
    """
    old_year = tracking.get("tracking_year", new_year - 1)
    log.info(f"Rolling over tracking year {old_year} → {new_year}")

    baseline = tracking.setdefault("baseline_history", {})
    year_returns = {}
    for key, meth in tracking.get("methodologies", {}).items():
        year_returns[key] = round(meth.get("ytd_return", 0.0), 4)
    baseline[str(old_year)] = year_returns

    # Keep only last 5 years in baseline
    years_sorted = sorted(baseline.keys())
    while len(years_sorted) > 5:
        oldest = years_sorted.pop(0)
        del baseline[oldest]
        log.info(f"  Dropped baseline year {oldest}")

    # Reset for new year
    tracking["tracking_year"] = new_year
    for key, meth in tracking.get("methodologies", {}).items():
        meth["rebalances"] = []
        meth["all_exits_2026"] = []
        meth["ytd_return"] = 0.0
        meth["tracking_start"] = ""
        meth["rebalance_count"] = 0
        # current_holdings carry forward as the starting portfolio

    log.info(f"Rollover complete. Baseline now covers: {sorted(baseline.keys())}")


def save_methodology_picks(all_results: list[Stock], no_gcs: bool):
    """Generate and serialize the portfolio picks for the 9 methodologies to GCS and local public folder."""
    # 1. Compute cross-sectional ranking logic for EV/GP, EY Gap, and Acquirer's Multiple
    # EV/GP
    valid_gp_ta = []
    for s in all_results:
        gp_ta = s.gross_profit / s.total_assets if s.total_assets > 0 else 0.0
        s.gp_ta = gp_ta
        valid_gp_ta.append(s)
        
    valid_gp_ta.sort(key=lambda x: x.gp_ta)
    N = len(valid_gp_ta)
    for i, s in enumerate(valid_gp_ta):
        rank_pct = i / (N - 1) if N > 1 else 0.5
        s.ev_gross_profit_mos = (rank_pct - 0.5) * 0.3
        
    # EY Gap
    valid_ey_gap = []
    for s in all_results:
        ey = (s.eps_latest * s.fx_to_price) / s.price if s.price > 0 else 0.0
        ey_gap = ey - RISK_FREE  # Use global constant, not hardcoded 0.045
        s.ey_gap = ey_gap
        valid_ey_gap.append(s)
        
    valid_ey_gap.sort(key=lambda x: x.ey_gap)
    N = len(valid_ey_gap)
    for i, s in enumerate(valid_ey_gap):
        rank_pct = i / (N - 1) if N > 1 else 0.5
        s.earnings_yield_gap_mos = (rank_pct - 0.5) * 0.25
        
    # Acquirer's Multiple
    qualified_am = []
    for s in all_results:
        ev = (s.market_cap or 0.0) + (s.net_debt or 0.0)
        ebit = s.ebit or 0.0
        if ev > 0.0 and ebit > 0.0:
            multiple = ev / ebit
            if 0.0 < multiple <= 100.0:
                s.acquirers_multiple = multiple
                qualified_am.append(s)
            else:
                s.acquirers_multiple = 999.0
                s.acquirers_multiple_mos = -1.0
        else:
            s.acquirers_multiple = 999.0
            s.acquirers_multiple_mos = -1.0
            
    qualified_am.sort(key=lambda x: x.acquirers_multiple)
    M = len(qualified_am)
    for j, s in enumerate(qualified_am):
        rank_pct = j / (M - 1) if M > 1 else 0.5
        s.acquirers_multiple_mos = (0.5 - rank_pct) * 0.4

    # 2. Portfolio selection logic
    def passes_leverage_gate(s) -> bool:
        ebitda = (s.ebit_local or 0.0) + (s.depreciation_local or 0.0)
        net_debt = s.net_debt_local or 0.0
        if ebitda <= 0.0:
            return net_debt <= 0.0
        return (net_debt / ebitda) < 3.0

    def get_best_portfolio_of_size(candidates, target_T):
        # Sector cap: max 30% of portfolio per sector (was 50%)
        # Value traps cluster in the same sector — tighter cap ensures diversification
        limit = max(1, round(target_T * 0.3))
        portfolio = []
        sector_counts = {}
        for s in candidates:
            sec = s.sector or "Unknown"
            if sector_counts.get(sec, 0) < limit:
                portfolio.append(s)
                sector_counts[sec] = sector_counts.get(sec, 0) + 1
                if len(portfolio) == target_T:
                    return portfolio
        return None

    # Load previous picks to maintain entry_price, entry_date, and entry_metric
    prev_picks_map = {} # methodology_path -> ticker -> {entry_price, entry_date, entry_metric}
    local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "public", "methodology_picks.json")
    try:
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                if old_data and "methodologies" in old_data:
                    for meth_path, meth_val in old_data["methodologies"].items():
                        prev_picks_map[meth_path] = {}
                        for p in meth_val.get("picks", []):
                            if "symbol" in p:
                                prev_picks_map[meth_path][p["symbol"]] = {
                                    "entry_price": p.get("entry_price"),
                                    "entry_date": p.get("entry_date"),
                                    "entry_metric": p.get("entry_metric")
                                }

    except Exception as e:
        log.warning(f"Failed to read previous picks: {e}")

    methodology_fields = {
        "dcf_fcff": ("dcf_fcff_mos", "dcf_value"),
        "earnings_yield_gap": ("earnings_yield_gap_mos", None),
        "ev_gross_profit": ("ev_gross_profit_mos", None),
        "rd_capitalized_dcf": ("rd_capitalized_dcf_mos", "rd_capitalized_dcf"),
        "owner_earnings": ("owner_earnings_mos", "owner_earnings"),
        "epv": ("epv_mos", "epv_value"),
        "graham_revised": ("graham_revised_mos", "graham_revised"),
        "acquirers_multiple": ("acquirers_multiple_mos", None),
        "iv15_deep_value": ("iv15_deep_value_mos", "iv15_deep_value")
    }

    methodology_metrics = {
        "dcf_fcff":            "dcf_fcff_mos",
        "earnings_yield_gap":  "ey_gap",
        "ev_gross_profit":     "gp_ta",
        "rd_capitalized_dcf":  "rd_capitalized_dcf_mos",
        "owner_earnings":      "owner_earnings_mos",
        "epv":                 "epv_mos",
        "graham_revised":      "graham_revised_mos",
        "acquirers_multiple":  "acquirers_multiple",
        "iv15_deep_value":     "iv15_deep_value_mos",
    }

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    methodology_picks = {}

    # ── Rotation hysteresis (May 2026) ──────────────────────────────────
    # Without hysteresis, a stock can enter and exit within 2 weeks from
    # scan-to-scan noise in MOS. Incumbent holdings get a small MOS boost
    # (HYSTERESIS_BOOST) so a challenger must be meaningfully better to
    # displace them. This reduces turnover without sacrificing signal.
    HYSTERESIS_BOOST = 0.05  # 5 percentage points

    for key, (mos_field, fv_field) in methodology_fields.items():
        # Build set of currently-held symbols for this methodology
        incumbent_syms = set()
        if key in prev_picks_map:
            incumbent_syms = set(prev_picks_map[key].keys())

        candidates = []
        for s in all_results:
            mos_val = getattr(s, mos_field, -1.0)
            if mos_val is not None and mos_val > -1.0:
                if passes_leverage_gate(s) and (s.piotroski or 0) >= 3:
                    # Boost incumbent holdings to prevent whipsaw rotation
                    boost = HYSTERESIS_BOOST if s.symbol in incumbent_syms else 0.0
                    s._temp_mos = mos_val + boost
                    candidates.append(s)
                    
        candidates.sort(key=lambda x: x._temp_mos, reverse=True)
        
        portfolio = None
        for target_T in range(min(20, len(candidates)), 0, -1):
            portfolio = get_best_portfolio_of_size(candidates, target_T)
            if portfolio:
                break
                
        if not portfolio:
            portfolio = []
            
        portfolio_symbols = set(s.symbol for s in portfolio)
        metric_field = methodology_metrics[key]
        
        # Load previous exits to keep history of recent exits
        prev_exits = []
        try:
            if old_data and "methodologies" in old_data and key in old_data["methodologies"]:
                prev_exits = old_data["methodologies"][key].get("exits", [])
        except Exception:
            pass

        # Identify new exits: any stock in previous picks that is not in the new portfolio
        new_exits = []
        if key in prev_picks_map:
            for old_sym, old_val in prev_picks_map[key].items():
                if old_sym not in portfolio_symbols:
                    exit_price = old_val.get("entry_price") or 0.0
                    exit_metric = 0.0
                    for s in all_results:
                        if s.symbol == old_sym:
                            exit_price = s.price
                            exit_metric = getattr(s, metric_field, 0.0)
                            break
                    entry_p = old_val.get("entry_price") or exit_price
                    entry_m = old_val.get("entry_metric") or 0.0
                    perf = (exit_price - entry_p) / entry_p if entry_p > 0 else 0.0
                    new_exits.append({
                        "symbol": old_sym,
                        "entry_price": round(entry_p, 4),
                        "entry_date": old_val.get("entry_date") or today_str,
                        "entry_metric": round(entry_m, 4),
                        "exit_price": round(exit_price, 4),
                        "exit_date": today_str,
                        "exit_metric": round(exit_metric, 4),
                        "performance": round(perf, 4)
                    })
                    
        # Combine new exits and previous exits (preventing duplicates)
        combined_exits = list(new_exits)
        existing_keys = set((e["symbol"], e["exit_date"]) for e in new_exits)
        for pe in prev_exits:
            pe_key = (pe["symbol"], pe.get("exit_date", ""))
            if pe_key not in existing_keys:
                combined_exits.append(pe)
        # Limit to last 15 exits
        final_exits = combined_exits[:15]

        picks = []
        count = len(portfolio)
        weight = 1.0 / count if count > 0 else 0.0
        total_mos = 0.0
        for s in portfolio:
            mos_val = getattr(s, mos_field)
            raw_metric = getattr(s, metric_field, 0.0)
            if fv_field:
                fv_val = getattr(s, fv_field)
            else:
                fv_val = s.price * (1 + mos_val)
                
            entry_p = s.price
            entry_d = today_str
            entry_m = raw_metric
            if key in prev_picks_map and s.symbol in prev_picks_map[key]:
                old_p = prev_picks_map[key][s.symbol].get("entry_price")
                old_d = prev_picks_map[key][s.symbol].get("entry_date")
                old_m = prev_picks_map[key][s.symbol].get("entry_metric")
                if old_p is not None:
                    entry_p = old_p
                if old_d is not None:
                    entry_d = old_d
                if old_m is not None:
                    entry_m = old_m
                
            picks.append({
                "symbol": s.symbol,
                "weight": round(weight, 4),
                "mos": round(mos_val, 4),
                "price": round(s.price, 4),
                "entry_price": round(entry_p, 4),
                "entry_date": entry_d,
                "entry_metric": round(entry_m, 4),
                "fair_value": round(fv_val, 4),
                "sector": s.sector or "Unknown"
            })
            total_mos += mos_val
            
        avg_mos = total_mos / count if count > 0 else 0.0
        methodology_picks[key] = {
            "picks": picks,
            "exits": final_exits,
            "average_mos": round(avg_mos, 4)
        }


    # -----------------------------------------------------------------------
    # Paper-trading tracker: append rebalance, compute YTD, enrich picks
    # -----------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    tracking = _load_tracking_state()
    current_year = now.year

    # Year-end rollover: if tracking_year < current year, finalize & reset
    if tracking and tracking.get("tracking_year", current_year) < current_year:
        _rollover_tracking_year(tracking, current_year)

    if tracking and tracking.get("tracking_year") == current_year:
        # Build stock price map from all_results for accurate exit pricing
        _stock_price_map = {s.symbol: s.price for s in all_results}
        _append_rebalance_to_tracking(tracking, methodology_picks, today_str,
                                      stock_price_map=_stock_price_map)
        # Enrich methodology_picks with tracking metadata
        for key in methodology_picks:
            meth_tracking = tracking.get("methodologies", {}).get(key, {})
            methodology_picks[key]["ytd_return"] = round(meth_tracking.get("ytd_return", 0.0), 4)
            methodology_picks[key]["tracking_start"] = meth_tracking.get("tracking_start", today_str)
            methodology_picks[key]["rebalance_count"] = meth_tracking.get("rebalance_count", 0)
        # Save updated tracking state
        _save_tracking_state(tracking, no_gcs)
    else:
        log.info("No tracking state found or year mismatch — skipping tracking update")

    payload_picks = {
        "last_updated": now.isoformat() + "Z",
        "methodologies": methodology_picks
    }

    # Write to local file
    try:
        local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "public", "methodology_picks.json")
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(payload_picks, f, indent=2)
        log.info(f"Saved methodology picks locally to {local_path}")
    except Exception as e:
        log.error(f"Failed to write local methodology_picks.json: {e}")

    # Write to GCS if not no_gcs
    if not no_gcs:
        try:
            gcs_upload("scans/methodology_picks.json", payload_picks)
            log.info("Uploaded methodology picks to GCS scans/methodology_picks.json")
        except Exception as e:
            log.warning(f"GCS upload of methodology picks failed: {e}")


# ---------------------------------------------------------------------------
# 19. Main Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CB Screener v7.2 — 13-factor + dual-mode v8")
    parser.add_argument("--region", default="nasdaq100",
                        help="nasdaq100 | sp500 | europe | asia | brazil | midcap | global")
    parser.add_argument("--monitor", action="store_true",
                        help="Run portfolio monitor mode (re-score current holdings)")
    parser.add_argument("--top", type=int, default=TOP_N,
                        help="Top N stocks to display in report")
    parser.add_argument("--no-email", action="store_true",
                        help="Skip email send (default: enabled if SMTP configured)")
    parser.add_argument("--no-gcs", action="store_true",
                        help="Skip GCS upload (local testing)")
    args = parser.parse_args()

    if args.monitor:
        results = monitor_portfolio()
        if results:
            print(json.dumps(results, indent=2))
        return

    # Build universe + preload sector performance + scan
    log.info(f"Region: {args.region}")

    symbols = get_symbols(args.region)
    log.info(f"Universe: {len(symbols)} stocks")

    # Preload sector performance (one-time, used by compute_sector_momentum)
    preload_sector_performance(days=60)

    # v8 Compounder v1.1 (May 11 2026): SP500 preload removed — US cohort now
    # uses country=='US' + mcap>=$2B gate, no external membership list needed.

    # v1.2 (May 2026): clear institutional positions-summary cache so that
    # successive scans in the same Python process (rare, but possible in
    # Cloud Run Jobs that re-invoke main()) don't reuse stale 13F data.
    _INST_POSITIONS_SUMMARY_CACHE.clear()

    # v1.3.0: reset FMP cache stats before scan
    _cache_reset()

    # Run two-pass scan (returns tuple: stocks + macro regime data)
    stocks, macro = screen(symbols, top_n=args.top)
    log.info(f"Scan complete: {len(stocks)} stocks scored")

    # v1.3.0: log FMP cache hit/miss summary
    _cache_log()

    # Format + send + persist
    report = format_report(stocks, top_n=args.top, region=args.region, macro=macro)
    print(report)

    if not args.no_email:
        send_email(f"CB Screener v7.2 — {args.region} ({datetime.now():%Y-%m-%d})", report)

    log_signals(stocks)

    save_methodology_picks(stocks, args.no_gcs)

    if not args.no_gcs:
        save_scan_to_gcs(stocks, region=args.region, macro=macro)


if __name__ == "__main__":
    main()
# cache bust 1778544443
