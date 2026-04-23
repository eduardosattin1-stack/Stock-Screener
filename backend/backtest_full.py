#!/usr/bin/env python3
"""
Stock Screener v7.1 — FULL HISTORICAL BACKTEST + ML OPTIMIZER
===============================================================
Runs on Cloud Run / Cloud Shell alongside screener_v6.py

v7.1 additions (3 new features, all verified via MCP):
  - Sector momentum: historical-sector-performance (with exchange param for EU)
  - Congressional trading: senate-trades + house-trades (prefetched, filtered by disclosureDate)
  - Institutional flow v2: positions-summary (13F net new, put/call, ownership change)

13 factors total: technical 35% | quality 14% | upside 10% | proximity 7% |
  catalyst 7% | transcript 5% | sector_momentum 4% | institutional 4% |
  analyst 4% | insider 3% | earnings 3% | congressional 2% | institutional_flow 2%

Usage:
  # Full 4-year training (2022-2025):
  python backtest_full.py --region global --from 2022-01-01 --to 2025-12-31

  # Specific date range:
  python backtest_full.py --region sp500 --from 2024-06-01 --to 2025-06-30

  # Retrain ML from existing CSV:
  python backtest_full.py --train-only combined_training.csv

Architecture:
  For each monthly window in the date range:
    1. Get stock universe (same as v6 company-screener)
    2. For each stock:
       a. Get historical price on window START date (from chart)
       b. Get historical price on window END date (from chart)
       c. Get chart data (200d before start) → compute technicals AS OF start
       d. Get fundamentals (quarterly — cached, same within quarter)
       e. Compute all factor scores using start price
       f. Record: features + actual 1-month return + time-to-target metrics
    3. Output: training_data.csv with ~(stocks × windows) samples

Quarterly Retraining Cycle:
  Q1: Train on rolling 24 months → deploy weights
  Q2: Retrain with new quarter of data → update weights
  Repeat. Compare predicted vs actual each quarter.

Outputs:
  - training_data.csv: Full feature matrix + returns (for ML)
  - v7_weights.json: ML-optimized factor weights
  - backtest_report.txt: Human-readable performance analysis
  - Uploads to GCS: backtest/YYYY-MM-DD.json

Requirements: requests, scikit-learn (pip install scikit-learn)
"""

import os, sys, json, math, time, logging, argparse, csv, hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field, asdict

import requests

# ---------------------------------------------------------------------------
# Import v6 core functions (if available), otherwise define locally
# ---------------------------------------------------------------------------

try:
    from screener_v6 import (
        fmp, WEIGHTS, get_fx_rate, _FX_TO_USD, REGIONS,
        FMP_KEY, FMP, RATE_LIMIT, RISK_FREE,
    )
    log = logging.getLogger("backtest")
    log.info("Imported screener_v6 core functions")
    HAVE_V6 = True
except ImportError:
    HAVE_V6 = False
    log = logging.getLogger("backtest")
    log.warning("screener_v6.py not found — using built-in functions")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

if not HAVE_V6:
    FMP_KEY = os.environ.get("FMP_API_KEY", "")
    FMP = "https://financialmodelingprep.com/stable"
    RATE_LIMIT = 0.04
    RISK_FREE = 0.045

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backtest")

GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")

# ---------------------------------------------------------------------------
# FMP Client (fallback if v6 not imported)
# ---------------------------------------------------------------------------

if not HAVE_V6:
    _FX_TO_USD = {
        "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CHF": 1.12,
        "JPY": 0.0067, "CNY": 0.14, "TWD": 0.031, "KRW": 0.00073,
        "HKD": 0.128, "INR": 0.012, "SGD": 0.75, "AUD": 0.65,
        "CAD": 0.73, "SEK": 0.097, "BRL": 0.18,
    }

    def get_fx_rate(from_ccy, to_ccy):
        if from_ccy == to_ccy: return 1.0
        f = _FX_TO_USD.get(from_ccy, 1.0)
        t = _FX_TO_USD.get(to_ccy, 1.0)
        return f / t if t else 1.0

    def fmp(endpoint, params=None):
        time.sleep(RATE_LIMIT)
        url = f"{FMP}/{endpoint}"
        p = {"apikey": FMP_KEY}
        if params: p.update(params)
        try:
            r = requests.get(url, params=p, timeout=20)
            if r.status_code != 200: return None
            data = r.json()
            if isinstance(data, dict) and "Error Message" in data: return None
            if isinstance(data, dict): return [data]
            return data if isinstance(data, list) else None
        except:
            return None

    REGIONS = {
        "nasdaq100": [("NASDAQ", None, 20_000_000_000, 100)],
        "sp500": [("NASDAQ", None, 1_000_000_000, 500), ("NYSE", None, 1_000_000_000, 500)],
        # 2026-04-23: mid-cap universes. Market cap 2B-10B, country=US,
        # USD reporting filtered downstream in Altman Z compute.
        "midcap_nyse":   [("NYSE",   "US", 2_000_000_000, 10_000_000_000, 300)],
        "midcap_nasdaq": [("NASDAQ", "US", 2_000_000_000, 10_000_000_000, 300)],
        "europe": [
            ("XETRA", "DE", 5_000_000_000, 40), ("PAR", "FR", 5_000_000_000, 30),
            ("LSE", "UK", 5_000_000_000, 40), ("AMS", "NL", 5_000_000_000, 20),
            ("MIL", "IT", 5_000_000_000, 15), ("STO", "SE", 5_000_000_000, 15),
            ("SIX", "CH", 5_000_000_000, 15), ("BME", "ES", 5_000_000_000, 10),
        ],
        "global": None,
    }

# Always define our own get_symbols to ensure SYMBOL_META is populated
def get_symbols(region):
    if region == "global":
        syms = []
        for r in ["sp500", "europe"]:
            syms.extend(get_symbols(r))
        return list(dict.fromkeys(syms))
    if region == "midcap":
        # 2026-04-23: combined US mid-cap (NYSE + NASDAQ, $2-10B).
        syms = []
        for r in ["midcap_nyse", "midcap_nasdaq"]:
            syms.extend(get_symbols(r))
        return list(dict.fromkeys(syms))
    configs = REGIONS.get(region)
    if configs is None:
        configs = [(region.upper(), None, 5_000_000_000, 50)]
    symbols = []
    for cfg_tuple in configs:
        # Support both 4-tuple (existing: exchange, country, min_cap, limit)
        # and 5-tuple (new: exchange, country, min_cap, max_cap, limit).
        if len(cfg_tuple) == 5:
            exchange, country, min_cap, max_cap, limit = cfg_tuple
        else:
            exchange, country, min_cap, limit = cfg_tuple
            max_cap = None
        params = {
            "exchange": exchange, "marketCapMoreThan": min_cap,
            "isActivelyTrading": "true", "isEtf": "false", "isFund": "false",
            "limit": limit,
        }
        if max_cap is not None:
            params["marketCapLowerThan"] = max_cap
        if country: params["country"] = country
        data = fmp("company-screener", params)
        if data:
            batch = [d["symbol"] for d in data if "symbol" in d]
            # Cache sector and exchange per symbol for new features
            for d in data:
                if "symbol" in d:
                    SYMBOL_META[d["symbol"]] = {
                        "sector": d.get("sector", ""),
                        "exchange": d.get("exchangeShortName", exchange),
                    }
            log.info(f"  {exchange}/{country or 'all'}: {len(batch)} stocks")
            symbols.extend(batch)
    return list(dict.fromkeys(symbols))

# ---------------------------------------------------------------------------
# Cache for fundamentals (quarterly data — reuse within same quarter)
# ---------------------------------------------------------------------------

_CACHE = {}  # key: (sym, quarter_key) → data

# NEW v7.1: Additional caches for new features
SYMBOL_META = {}        # sym → {sector, exchange} — populated by get_symbols()
_CONGRESS_CACHE = {}    # sym → [trades] — ALL trades, fetched once per symbol
_SECTOR_MOM_CACHE = {}  # "sector|exchange|YYYY-MM" → score
_13F_CACHE = {}         # "sym|YYYY|Q" → data dict

def cache_key(sym, date_str):
    """Generate cache key based on stock + fiscal quarter."""
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    q = (dt.month - 1) // 3 + 1
    return f"{sym}:{dt.year}Q{q}"

def get_cached(sym, date_str, data_type):
    key = f"{cache_key(sym, date_str)}:{data_type}"
    return _CACHE.get(key)

def set_cached(sym, date_str, data_type, data):
    key = f"{cache_key(sym, date_str)}:{data_type}"
    _CACHE[key] = data

# ---------------------------------------------------------------------------
# Historical Price Fetching
# ---------------------------------------------------------------------------

_CHART_CACHE = {}  # sym → [(date, close, high, low, volume), ...]

def load_chart(sym, start_date="2024-10-01", end_date=None):
    """Load full chart data into cache. Called once per stock."""
    if sym in _CHART_CACHE:
        return _CHART_CACHE[sym]
    
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    data = fmp("historical-price-eod/full", {"symbol": sym, "from": start_date, "to": end_date})
    if not data:
        _CHART_CACHE[sym] = []
        return []
    
    chart = []
    for d in data:
        chart.append({
            "date": d.get("date", ""),
            "close": float(d.get("close", 0)),
            "high": float(d.get("high", 0)),
            "low": float(d.get("low", 0)),
            "volume": int(d.get("volume", 0)),
        })
    chart.sort(key=lambda x: x["date"])
    _CHART_CACHE[sym] = chart
    return chart

def get_price_on_date(sym, target_date):
    """Get closing price on or closest before target date."""
    chart = _CHART_CACHE.get(sym, [])
    best = None
    for d in chart:
        if d["date"] <= target_date:
            best = d
    return best

def get_chart_slice(sym, end_date, days=220):
    """Get chart data slice ending on end_date, going back `days` trading days."""
    chart = _CHART_CACHE.get(sym, [])
    filtered = [d for d in chart if d["date"] <= end_date]
    return filtered[-days:] if len(filtered) > days else filtered

# ---------------------------------------------------------------------------
# Compute technicals from historical chart slice
# ---------------------------------------------------------------------------

def compute_rsi(closes, period=14):
    if len(closes) < period + 1: return 50.0
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
    if avg_loss == 0: return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))

def compute_macd(closes):
    def ema(data, n):
        if len(data) < n: return data[:]
        result = [sum(data[:n]) / n]
        mult = 2 / (n + 1)
        for i in range(n, len(data)):
            result.append((data[i] - result[-1]) * mult + result[-1])
        return result
    if len(closes) < 35: return {"signal": "neutral", "histogram": 0}
    ema12, ema26 = ema(closes, 12), ema(closes, 26)
    ml = min(len(ema12), len(ema26))
    macd_line = [ema12[-(ml - i)] - ema26[-(ml - i)] for i in range(ml)]
    sig = ema(macd_line, 9)
    if len(sig) < 2 or len(macd_line) < 2: return {"signal": "neutral", "histogram": 0}
    h_now = macd_line[-1] - sig[-1]
    h_prev = macd_line[-2] - sig[-2] if len(macd_line) > 2 else h_now
    if h_prev < 0 and h_now > 0: s = "bullish_cross"
    elif h_prev > 0 and h_now < 0: s = "bearish_cross"
    elif h_now > 0: s = "bullish"
    else: s = "bearish"
    return {"signal": s, "histogram": h_now}

def compute_bollinger(closes, period=20):
    if len(closes) < period: return 0.5
    sma = sum(closes[-period:]) / period
    std = (sum((c - sma)**2 for c in closes[-period:]) / period) ** 0.5
    w = 2 * std * 2
    return (closes[-1] - (sma - 2*std)) / w if w else 0.5

def compute_obv_trend(closes, volumes, lookback=20):
    if len(closes) < lookback + 1: return "flat"
    obv = [0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]: obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i-1]: obv.append(obv[-1] - volumes[i])
        else: obv.append(obv[-1])
    recent = obv[-lookback:]
    slope = (recent[-1] - recent[0]) / max(abs(recent[0]), 1)
    if slope > 0.05: return "rising"
    elif slope < -0.05: return "falling"
    return "flat"

def compute_technicals_historical(sym, as_of_date):
    """Compute full technicals using chart data up to as_of_date."""
    chart = get_chart_slice(sym, as_of_date, 220)
    if not chart or len(chart) < 30:
        return None
    
    closes = [d["close"] for d in chart]
    highs = [d["high"] for d in chart]
    lows = [d["low"] for d in chart]
    volumes = [d["volume"] for d in chart]
    
    price = closes[-1]
    sma50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 20 else price
    sma200 = sum(closes[-200:]) / min(200, len(closes)) if len(closes) >= 50 else price
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else price
    
    # 52wk proxy
    yr_data = closes[-252:] if len(closes) >= 252 else closes
    year_high = max(yr_data)
    year_low = min(yr_data)
    
    rsi = compute_rsi(closes)
    macd = compute_macd(closes)
    bb_pct = compute_bollinger(closes)
    obv = compute_obv_trend(closes, volumes)
    
    # Bull score (same 10 signals as v6)
    score = 0
    if price > sma50 > 0: score += 1
    if sma50 > sma200 > 0: score += 1
    if 40 < rsi < 70: score += 1
    if macd["signal"] in ("bullish", "bullish_cross"): score += 1
    if 0.3 < bb_pct < 0.8: score += 1
    if price > sma20: score += 1
    if 20 < rsi < 80: score += 1  # stoch_rsi proxy
    if obv == "rising": score += 1
    if year_high > 0 and price > year_high * 0.85: score += 1
    # Bonus: momentum
    if len(closes) >= 20:
        mom20 = (closes[-1] - closes[-20]) / closes[-20]
        if mom20 > 0.05: score += 1
    
    return {
        "price": price, "sma50": sma50, "sma200": sma200,
        "year_high": year_high, "year_low": year_low,
        "rsi": rsi, "macd_signal": macd["signal"], "bb_pct": bb_pct,
        "obv_trend": obv, "bull_score": score,
        "currency": "USD",  # will be overridden by quote
    }

# ---------------------------------------------------------------------------
# Get fundamentals (with caching)
# ---------------------------------------------------------------------------

def safe_cagr(start, end, years):
    if not start or not end or start <= 0 or end <= 0 or years <= 0: return 0.0
    return (end / start) ** (1 / years) - 1

def get_fundamentals_cached(sym, as_of_date):
    """Get all fundamental data, cached by fiscal quarter."""
    cached = get_cached(sym, as_of_date, "fundamentals")
    if cached:
        return cached
    
    result = {
        "piotroski": 5, "altman_z": 5.0, "dcf_value": 0,
        "roe_avg": 0, "roe_consistent": False, "roic_avg": 0,
        "gross_margin": 0, "gross_margin_trend": "unknown",
        "revenue_cagr_3y": 0, "eps_cagr_3y": 0,
        "owner_earnings_yield": 0, "intrinsic_buffett": 0,
        "intrinsic_avg": 0, "margin_of_safety": 0, "value_score": 0,
        "classification": "NEUTRAL",
        "target": 0, "grade_score": 0.5, "grade_buy": 0, "grade_total": 0,
        "eps_beats": 0, "eps_total": 0, "eps_surprises": [],
        "insider_score": 0.5, "insider_buy_ratio": 0, "insider_net_buys": 0,
    }
    
    # Financial scores (Piotroski + Altman Z)
    scores = fmp("financial-scores", {"symbol": sym})
    if scores:
        # 2026-04-23: write None instead of silent default-to-5.
        # Previous behaviour meant every stock got quality-neutral 5 when
        # the key-metrics endpoint lacked these fields, masking real
        # Piotroski/Altman signal. Callers should treat None as "exclude".
        pio_raw = scores[0].get("piotroskiScore")
        az_raw = scores[0].get("altmanZScore")
        result["piotroski"] = int(pio_raw) if pio_raw is not None else None
        try:
            result["altman_z"] = float(az_raw) if az_raw is not None else None
        except (TypeError, ValueError):
            result["altman_z"] = None
    
    # Income statement (for margins, growth)
    inc = fmp("income-statement", {"symbol": sym, "period": "annual", "limit": 5})
    if inc and len(inc) >= 2:
        inc.sort(key=lambda x: x.get("date", ""))
        revs = [float(x.get("revenue") or 0) for x in inc]
        eps_list = [float(x.get("epsDiluted") or 0) for x in inc]
        gp_list = [float(x.get("grossProfit") or 0) for x in inc]
        
        n = len(revs)
        if n >= 4 and revs[0] > 0:
            result["revenue_cagr_3y"] = safe_cagr(revs[-4], revs[-1], 3)
        if n >= 4 and eps_list[-4] > 0 and eps_list[-1] > 0:
            result["eps_cagr_3y"] = safe_cagr(eps_list[-4], eps_list[-1], 3)
        if revs[-1] > 0 and gp_list[-1] > 0:
            result["gross_margin"] = gp_list[-1] / revs[-1]
        
        # Intrinsic value
        latest_eps = float(inc[-1].get("epsDiluted") or 0)
        if latest_eps > 0:
            base_growth = min(result["revenue_cagr_3y"], 0.30)
            future_eps = latest_eps
            for i in range(5):
                future_eps *= (1 + max(base_growth * (0.8 ** i), 0.03))
            terminal_pe = min(max(15, 1 / max(RISK_FREE, 0.03)), 30)
            result["intrinsic_buffett"] = future_eps * terminal_pe / (1.10 ** 5)
    
    # Key metrics (ROE, ROIC)
    km = fmp("key-metrics", {"symbol": sym, "period": "annual", "limit": 5})
    if km:
        km.sort(key=lambda x: x.get("date", ""))
        roes = [float(x.get("returnOnEquity") or 0) for x in km]
        roics = [float(x.get("returnOnInvestedCapital") or 0) for x in km]
        if roes:
            result["roe_avg"] = sum(roes) / len(roes)
            result["roe_consistent"] = all(r > 0.15 for r in roes)
        if roics:
            result["roic_avg"] = sum(roics) / len(roics)
    
    # DCF
    dcf = fmp("discounted-cash-flow", {"symbol": sym})
    if dcf:
        result["dcf_value"] = float(dcf[0].get("dcf") or 0)
    
    # Owner earnings
    oe = fmp("owner-earnings", {"symbol": sym, "limit": 4})
    if oe:
        annual_oe_ps = sum(float(x.get("ownersEarningsPerShare") or 0) for x in oe)
        result["_annual_oe_ps"] = annual_oe_ps
    
    # Analyst targets
    pt = fmp("price-target-consensus", {"symbol": sym})
    if pt and pt[0].get("targetConsensus"):
        result["target"] = float(pt[0]["targetConsensus"])
    
    # Grades
    grades = fmp("grades", {"symbol": sym, "limit": 20})
    if grades:
        buy_grades = {"Buy", "Strong Buy", "Outperform", "Overweight", "Market Outperform", "Positive"}
        buys = sum(1 for g in grades[:15] if g.get("newGrade", "") in buy_grades)
        result["grade_buy"] = buys
        result["grade_total"] = min(len(grades), 15)
        result["grade_score"] = buys / min(len(grades), 15) if grades else 0.5
    
    # Earnings
    earnings = fmp("earnings", {"symbol": sym, "limit": 8})
    if earnings:
        for e in earnings:
            actual = e.get("epsActual")
            est = e.get("epsEstimated")
            if actual is not None and est is not None:
                result["eps_total"] += 1
                if float(actual) >= float(est):
                    result["eps_beats"] += 1
                if float(est) != 0:
                    result["eps_surprises"].append((float(actual) - float(est)) / abs(float(est)))
    
    # Insider activity
    ins_data = fmp("insider-trading/statistics", {"symbol": sym})
    if ins_data:
        recent = ins_data[:2] if len(ins_data) >= 2 else ins_data
        total_acq = sum((d.get("totalAcquired") or 0) for d in recent)
        total_disp = sum((d.get("totalDisposed") or 0) for d in recent)
        result["insider_buy_ratio"] = total_acq / total_disp if total_disp > 0 else (5.0 if total_acq > 0 else 0)
        ratios = [(d.get("acquiredDisposedRatio") or 0) for d in recent]
        avg_r = sum(ratios) / len(ratios) if ratios else 0
        if avg_r >= 2.0: result["insider_score"] = 1.0
        elif avg_r >= 1.0: result["insider_score"] = 0.75
        elif avg_r >= 0.5: result["insider_score"] = 0.5
        elif avg_r >= 0.2: result["insider_score"] = 0.3
        else: result["insider_score"] = 0.15
    
    set_cached(sym, as_of_date, "fundamentals", result)
    return result

# ---------------------------------------------------------------------------
# Quality Factor (NEW — Piotroski + Altman Z + ROE composite)
# ---------------------------------------------------------------------------

def compute_quality_score(fundamentals):
    """Compute quality factor (0-1) from Piotroski, Altman Z, ROE, ROIC."""
    pio = fundamentals.get("piotroski", 5)
    az = fundamentals.get("altman_z", 5.0)
    roe = fundamentals.get("roe_avg", 0)
    roic = fundamentals.get("roic_avg", 0)
    gm = fundamentals.get("gross_margin", 0)
    
    score = 0.0
    # Piotroski (40% of quality)
    score += (pio / 9) * 0.40
    # Altman Z (20%)
    score += min(az / 20, 1.0) * 0.20
    # ROE (15%)
    score += min(max(roe, 0) / 0.30, 1.0) * 0.15
    # ROIC (10%)
    score += min(max(roic, 0) / 0.20, 1.0) * 0.10
    # Gross margin (15%)
    score += min(gm / 0.60, 1.0) * 0.15
    
    return min(score, 1.0)

# ---------------------------------------------------------------------------
# NEW v7.1: Sector Momentum (cached per sector/exchange/month)
# ---------------------------------------------------------------------------

def compute_sector_momentum_bt(sector, exchange, as_of_date):
    """
    Compute sector momentum score for backtest.
    Fetches 20-day sector performance ending on as_of_date.
    Cached per (sector, exchange, month).
    """
    if not sector:
        return 0.5
    
    dt = datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    cache_key = f"{sector}|{exchange}|{dt.strftime('%Y-%m')}"
    if cache_key in _SECTOR_MOM_CACHE:
        return _SECTOR_MOM_CACHE[cache_key]
    
    from_d = (dt - timedelta(days=35)).strftime("%Y-%m-%d")
    to_d = as_of_date[:10]
    
    params = {"sector": sector, "from": from_d, "to": to_d}
    if exchange and exchange not in ("NASDAQ", "NYSE"):
        params["exchange"] = exchange
    
    data = fmp("historical-sector-performance", params)
    if not data or len(data) < 5:
        _SECTOR_MOM_CACHE[cache_key] = 0.5
        return 0.5
    
    data.sort(key=lambda x: x.get("date", ""))
    changes = [d.get("averageChange", 0) for d in data]
    recent_20 = changes[-20:] if len(changes) >= 20 else changes
    cum_20d = sum(recent_20)
    
    if cum_20d > 5.0: score = 1.0
    elif cum_20d > 2.0: score = 0.80
    elif cum_20d > 0: score = 0.60
    elif cum_20d > -2.0: score = 0.40
    elif cum_20d > -5.0: score = 0.20
    else: score = 0.05
    
    _SECTOR_MOM_CACHE[cache_key] = score
    return score

# ---------------------------------------------------------------------------
# NEW v7.1: Congressional Trading (prefetched, filtered by date)
# ---------------------------------------------------------------------------

def prefetch_congressional(symbols):
    """
    Prefetch all congressional trades for all symbols.
    Called once at backtest start. ~1,800 API calls.
    NOTE: senate-trading/house-trading may be MCP-only on some FMP tiers.
    If REST returns None, gracefully sets empty list.
    """
    log.info(f"  Prefetching congressional data for {len(symbols)} symbols...")
    fetched = 0
    for i, sym in enumerate(symbols):
        if (i + 1) % 50 == 0:
            log.info(f"    Congressional: {i+1}/{len(symbols)} ({fetched} with data)")
        
        all_trades = []
        for endpoint in ("senate-trades", "house-trades"):
            data = fmp(endpoint, {"symbol": sym})
            if data:
                for t in data:
                    trade_type = (t.get("type", "") or "").lower()
                    is_buy = "purchase" in trade_type
                    is_sell = "sale" in trade_type
                    if is_buy or is_sell:
                        all_trades.append({
                            "disc": t.get("disclosureDate", ""),
                            "txn": t.get("transactionDate", ""),
                            "buy": is_buy,
                        })
        
        _CONGRESS_CACHE[sym] = all_trades
        if all_trades:
            fetched += 1
    
    log.info(f"  Congressional prefetch done: {fetched}/{len(symbols)} have trades")

def compute_congressional_score_bt(sym, as_of_date):
    """
    Compute congressional trading signal from prefetched data.
    Looks at trades disclosed in the 90 days before as_of_date.
    Uses disclosureDate (not transactionDate) to avoid look-ahead bias.
    """
    trades = _CONGRESS_CACHE.get(sym, [])
    if not trades:
        return 0.5  # no data = neutral
    
    dt = datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    cutoff = (dt - timedelta(days=90)).strftime("%Y-%m-%d")
    end = as_of_date[:10]
    
    buys = sum(1 for t in trades if t["buy"] and cutoff <= t["disc"] <= end)
    sells = sum(1 for t in trades if not t["buy"] and cutoff <= t["disc"] <= end)
    net = buys - sells
    total = buys + sells
    
    if total == 0: return 0.5
    elif net >= 3: return 1.0
    elif net >= 1: return 0.70
    elif net == 0: return 0.50
    elif net >= -2: return 0.30
    else: return 0.10

# ---------------------------------------------------------------------------
# NEW v7.1: Institutional Flow v2 (13F positions-summary, cached per quarter)
# ---------------------------------------------------------------------------

def compute_inst_flow_v2_bt(sym, as_of_date):
    """
    Compute institutional flow from 13F positions-summary.
    Uses the most recent quarter available before as_of_date (with 45-day lag).
    Cached per (symbol, year, quarter).
    Returns 0.5 for European stocks (no 13F data).
    """
    dt = datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    # 13F has ~45 day lag — use quarter from 60 days ago
    ref = dt - timedelta(days=60)
    q = (ref.month - 1) // 3 + 1
    y = ref.year
    
    cache_key = f"{sym}|{y}|Q{q}"
    if cache_key in _13F_CACHE:
        return _13F_CACHE[cache_key]
    
    data = fmp("institutional-ownership/symbol-positions-summary",
               {"symbol": sym, "year": y, "quarter": q})
    
    if not data or not isinstance(data, list) or len(data) == 0:
        # Try previous quarter
        q2 = q - 1 if q > 1 else 4
        y2 = y if q > 1 else y - 1
        cache_key2 = f"{sym}|{y2}|Q{q2}"
        if cache_key2 in _13F_CACHE:
            _13F_CACHE[cache_key] = _13F_CACHE[cache_key2]
            return _13F_CACHE[cache_key]
        data = fmp("institutional-ownership/symbol-positions-summary",
                    {"symbol": sym, "year": y2, "quarter": q2})
    
    if not data or not isinstance(data, list) or len(data) == 0:
        _13F_CACHE[cache_key] = 0.5
        return 0.5
    
    d = data[0]
    
    net_new = (d.get("newPositions", 0) or 0) - (d.get("closedPositions", 0) or 0)
    net_inc = (d.get("increasedPositions", 0) or 0) - (d.get("reducedPositions", 0) or 0)
    pcr = d.get("putCallRatio", 0) or 0
    own_chg = d.get("ownershipPercentChange", 0) or 0
    
    score = 0.5
    if net_new > 50: score += 0.20
    elif net_new > 10: score += 0.10
    elif net_new < -50: score -= 0.20
    elif net_new < -10: score -= 0.10
    
    if net_inc > 100: score += 0.15
    elif net_inc > 0: score += 0.05
    elif net_inc < -100: score -= 0.15
    
    if pcr > 2.0: score -= 0.10
    elif pcr < 0.5: score += 0.10
    
    if own_chg > 3: score += 0.05
    elif own_chg < -3: score -= 0.05
    
    result = max(0, min(1, score))
    _13F_CACHE[cache_key] = result
    return result

def compute_all_factors(sym, as_of_date, tech, fund, price):
    """Compute all v7.1 factor scores (13 factors) for a stock at a specific date."""
    if not tech or price <= 0:
        return None
    
    factors = {}
    
    # 1. Technical (35%)
    factors["technical"] = tech["bull_score"] / 10
    
    # 2. Upside (10%) — analyst target + intrinsic value vs price
    target = fund.get("target", 0)
    intrinsic = fund.get("intrinsic_buffett", 0)
    dcf = fund.get("dcf_value", 0)
    
    target_up = ((target - price) / price * 100) if target > 0 else 0
    intrinsic_up = ((intrinsic - price) / price * 100) if intrinsic > 0 else 0
    
    if target_up > 20 and intrinsic_up > 20: factors["upside"] = 1.0
    elif target_up > 10 and intrinsic_up > 10: factors["upside"] = 0.8
    elif target_up > 10 or intrinsic_up > 10: factors["upside"] = 0.6
    elif target_up > 0 and intrinsic_up > 0: factors["upside"] = 0.4
    elif target_up < -10 and intrinsic_up < -10: factors["upside"] = 0.0
    else: factors["upside"] = 0.25
    
    # 3. Quality (14%) — Piotroski + Altman Z + ROE + ROIC + GM
    factors["quality"] = compute_quality_score(fund)
    
    # 4. Proximity (7%) — 52-week position
    yh = tech.get("year_high", 0)
    yl = tech.get("year_low", 0)
    if yh > yl > 0:
        prox = (price - yl) / (yh - yl)
        if prox > 0.95: factors["proximity"] = 0.7
        elif prox > 0.80: factors["proximity"] = 1.0
        elif prox > 0.60: factors["proximity"] = 0.8
        elif prox > 0.40: factors["proximity"] = 0.5
        elif prox > 0.20: factors["proximity"] = 0.3
        else: factors["proximity"] = 0.15
    else:
        factors["proximity"] = 0.5
    
    # 5. Catalyst (7%) — simplified for backtest (earnings proximity)
    eps_total = fund.get("eps_total", 0)
    eps_beats = fund.get("eps_beats", 0)
    beat_rate = eps_beats / eps_total if eps_total > 0 else 0.5
    # Catalyst approximation: high beat rate + recent positive surprises
    surprises = fund.get("eps_surprises", [])
    recent_surprise = surprises[-1] if surprises else 0
    factors["catalyst"] = min(1.0, beat_rate * 0.5 + (0.5 if recent_surprise > 0.05 else 0.3))
    
    # 6. Transcript (5%) — skip for backtest, redistribute
    factors["transcript"] = None
    
    # 7. Analyst (4%)
    factors["analyst"] = fund.get("grade_score", 0.5)
    
    # 8. Institutional (4%) — original QoQ (skip for backtest, redistribute)
    factors["institutional"] = None
    
    # 9. Insider (3%)
    factors["insider"] = fund.get("insider_score", 0.5)
    
    # 10. Earnings (3%)
    factors["earnings"] = beat_rate * 0.6 + 0.4 * 0.5
    
    # 11. NEW: Sector momentum (4%) — from prefetched sector data
    meta = SYMBOL_META.get(sym, {})
    sector = meta.get("sector", "")
    exchange = meta.get("exchange", "NASDAQ")
    factors["sector_momentum"] = compute_sector_momentum_bt(sector, exchange, as_of_date)
    
    # 12. NEW: Congressional trading (2%) — from prefetched data
    factors["congressional"] = compute_congressional_score_bt(sym, as_of_date)
    
    # 13. NEW: Institutional flow v2 (2%) — 13F positions-summary
    factors["institutional_flow"] = compute_inst_flow_v2_bt(sym, as_of_date)
    
    # Composite (v7.1 weights — 13 factors)
    WEIGHTS_V71 = {
        "technical": 0.35, "quality": 0.14, "upside": 0.10, "proximity": 0.07,
        "catalyst": 0.07, "transcript": 0.05, "sector_momentum": 0.04,
        "institutional": 0.04, "analyst": 0.04, "insider": 0.03,
        "earnings": 0.03, "congressional": 0.02, "institutional_flow": 0.02,
    }
    active = {}
    missing_w = 0
    for f, w in WEIGHTS_V71.items():
        if factors.get(f) is not None:
            active[f] = w
        else:
            missing_w += w
            factors[f] = 0.5
    if missing_w > 0 and active:
        total_a = sum(active.values())
        for f in active: active[f] += missing_w * (active[f] / total_a)
    else:
        active = WEIGHTS_V71.copy()
    
    composite = sum(factors[f] * active.get(f, WEIGHTS_V71.get(f, 0)) for f in WEIGHTS_V71)
    
    # Signal (v7.1 — composite bands + ML-validated bearish safety net)
    bull = tech["bull_score"]
    sma50 = tech.get("sma50", 0)
    sma200 = tech.get("sma200", 0)
    trend_str = (sma50 - sma200) / sma200 if sma200 > 0 else 0
    momentum = (price - sma50) / sma50 if sma50 > 0 else 0
    prox_raw = (price - yl) / (yh - yl) if yh > yl > 0 else 0.5
    pio = fund.get("piotroski", 5)
    az = fund.get("altman_z", 5.0)
    
    momentum_score = sum([
        trend_str > 0.30, trend_str > 0.10, momentum > 0,
        momentum > 0.05, prox_raw > 0.75, prox_raw > 0.60, bull >= 6,
    ])
    quality_check = sum([
        factors.get("quality", 0.5) >= 0.6,
        composite > 0.55,
        factors.get("earnings", 0.5) >= 0.6,
    ])
    bearish_score = sum([
        trend_str < -0.05, momentum < -0.05, prox_raw < 0.30,
        bull <= 2, composite < 0.30,
    ])
    
    if momentum_score >= 5 and quality_check >= 1: signal = "BUY"
    elif momentum_score >= 4 and composite > 0.50: signal = "BUY"
    elif momentum_score >= 3 and composite > 0.45: signal = "WATCH"
    elif bearish_score >= 3: signal = "SELL"
    elif bearish_score >= 2 and composite < 0.35: signal = "SELL"
    else: signal = "HOLD"
    
    # STRONG BUY override
    has_catalyst = factors.get("catalyst", 0.5) >= 0.70
    if signal == "BUY" and has_catalyst:
        signal = "STRONG BUY"
    
    # Additional raw features for ML (these become f_* columns in CSV)
    factors["bull_score_raw"] = bull
    factors["momentum_20d"] = momentum
    factors["trend_strength"] = trend_str
    factors["rsi"] = tech["rsi"]
    factors["prox_raw"] = prox_raw
    factors["piotroski"] = pio
    factors["altman_z"] = az
    
    return {
        "composite": composite,
        "signal": signal,
        "factors": factors,
    }

# ---------------------------------------------------------------------------
# S&P 500 Benchmark
# ---------------------------------------------------------------------------

def get_sp500_prices(start="2024-10-01", end=None):
    """Fetch S&P 500 historical prices for benchmarking."""
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    data = fmp("historical-price-eod/full", {"symbol": "^GSPC", "from": start, "to": end})
    if not data:
        # Try index endpoint
        log.warning("Could not fetch ^GSPC, trying SPY as proxy")
        data = fmp("historical-price-eod/full", {"symbol": "SPY", "from": start, "to": end})
    if not data:
        return {}
    prices = {}
    for d in data:
        prices[d.get("date", "")] = float(d.get("close", 0))
    return prices

def get_closest_price(prices_dict, target_date, window=5):
    """Get price on or closest before target date."""
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    for i in range(window + 1):
        d = (dt - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in prices_dict:
            return prices_dict[d]
    # Try forward
    for i in range(1, window + 1):
        d = (dt + timedelta(days=i)).strftime("%Y-%m-%d")
        if d in prices_dict:
            return prices_dict[d]
    return None

# ---------------------------------------------------------------------------
# Generate Monthly Windows
# ---------------------------------------------------------------------------

def generate_windows(num_windows=12, from_date=None, to_date=None, window_days=30):
    """
    Generate monthly window pairs.
    
    If from_date and to_date are given: generates windows spanning that range.
    Otherwise: generates num_windows rolling back from today (original behavior).
    
    Each window is (start_date, end_date, label) where the stock is scored
    on start_date and the 1-month return is measured to end_date.
    """
    windows = []
    
    if from_date and to_date:
        # Date range mode: generate monthly windows from start to end
        start = datetime.strptime(from_date, "%Y-%m-%d")
        end = datetime.strptime(to_date, "%Y-%m-%d")
        
        cursor = start
        while cursor < end:
            # Window start: 10th of current month
            w_start = cursor.replace(day=10)
            
            # Window end: 10th of NEXT month
            if cursor.month == 12:
                w_end = cursor.replace(year=cursor.year + 1, month=1, day=10)
            else:
                w_end = cursor.replace(month=cursor.month + 1, day=10)
            
            # Don't go past end date + buffer
            if w_end > end + timedelta(days=15):
                break
            
            start_d = w_start.strftime("%Y-%m-%d")
            end_d = w_end.strftime("%Y-%m-%d")
            label = f"{w_start.strftime('%b%y')}→{w_end.strftime('%b%y')}"
            windows.append((start_d, end_d, label))
            
            # Advance cursor by 1 month
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year + 1, month=1)
            else:
                cursor = cursor.replace(month=cursor.month + 1)
    else:
        # Original mode: rolling back from today
        today = datetime.now()
        for i in range(num_windows):
            end = today - timedelta(days=window_days * i)
            start = end - timedelta(days=window_days)
            
            end_d = end.replace(day=min(10, end.day)).strftime("%Y-%m-%d")
            start_d = start.replace(day=min(10, start.day)).strftime("%Y-%m-%d")
            
            label = f"{start.strftime('%b%y')}→{end.strftime('%b%y')}"
            windows.append((start_d, end_d, label))
        
        windows.reverse()
    
    return windows

# ---------------------------------------------------------------------------
# MAIN BACKTEST
# ---------------------------------------------------------------------------

def run_backtest(region="nasdaq100", num_windows=6, from_date=None, to_date=None):
    log.info(f"Starting backtest: region={region}, windows={num_windows}, from={from_date}, to={to_date}")
    
    # 1. Get stock universe
    log.info("Step 1: Getting stock universe...")
    symbols = get_symbols(region)
    log.info(f"  Universe: {len(symbols)} stocks")
    
    if not symbols:
        log.error("No symbols found!")
        return []
    
    # 2. Generate windows
    windows = generate_windows(num_windows, from_date=from_date, to_date=to_date)
    log.info(f"Step 2: {len(windows)} monthly windows: {windows[0][2]} → {windows[-1][2]}")
    
    # 2b. NEW v7.1: Prefetch congressional trades (one-time, ~1,800 API calls)
    log.info("Step 2b: Prefetching congressional trading data...")
    prefetch_congressional(symbols)
    log.info(f"  Symbol metadata: {len(SYMBOL_META)} stocks have sector/exchange info")
    
    # 3. Fetch S&P 500 benchmark
    log.info("Step 3: Fetching S&P 500 benchmark...")
    earliest = windows[0][0]
    sp500_prices = get_sp500_prices(start=earliest)
    log.info(f"  S&P 500: {len(sp500_prices)} daily prices loaded")
    
    # 4. Pre-load chart data for all stocks (most expensive step)
    log.info(f"Step 4: Loading chart data for {len(symbols)} stocks...")
    chart_start = (datetime.strptime(earliest, "%Y-%m-%d") - timedelta(days=250)).strftime("%Y-%m-%d")
    loaded = 0
    for i, sym in enumerate(symbols):
        if (i + 1) % 25 == 0:
            log.info(f"  Charts: {i+1}/{len(symbols)} loaded ({loaded} with data)")
        chart = load_chart(sym, start_date=chart_start)
        if chart:
            loaded += 1
    log.info(f"  Charts loaded: {loaded}/{len(symbols)}")
    
    # 5. Run backtest across all windows
    training = []
    
    for w_idx, (start_d, end_d, label) in enumerate(windows):
        log.info(f"\nStep 5.{w_idx+1}: Window {label} ({start_d} → {end_d})")
        
        sp_start = get_closest_price(sp500_prices, start_d)
        sp_end = get_closest_price(sp500_prices, end_d)
        sp_return = ((sp_end - sp_start) / sp_start * 100) if sp_start and sp_end else 0
        
        window_results = 0
        skips = {"no_start": 0, "no_end": 0, "no_tech": 0, "no_fund": 0}
        
        for sym in symbols:
            # Get historical prices
            start_data = get_price_on_date(sym, start_d)
            end_data = get_price_on_date(sym, end_d)
            
            if not start_data or start_data["close"] <= 0:
                skips["no_start"] += 1
                continue
            if not end_data or end_data["close"] <= 0:
                skips["no_end"] += 1
                continue
            
            start_price = start_data["close"]
            end_price = end_data["close"]
            stock_return = (end_price - start_price) / start_price * 100
            
            # Compute technicals as of start date
            tech = compute_technicals_historical(sym, start_d)
            if not tech:
                skips["no_tech"] += 1
                continue
            
            # Get fundamentals (cached by quarter)
            fund = get_fundamentals_cached(sym, start_d)
            if not fund:
                skips["no_fund"] += 1
                continue
            
            # Compute margin of safety with historical price
            if fund.get("intrinsic_buffett", 0) > 0:
                fund["margin_of_safety"] = (fund["intrinsic_buffett"] - start_price) / start_price
            elif fund.get("dcf_value", 0) > 0:
                fund["margin_of_safety"] = (fund["dcf_value"] - start_price) / start_price
            else:
                fund["margin_of_safety"] = 0
            
            # Owner earnings yield with historical price
            if fund.get("_annual_oe_ps", 0) > 0 and start_price > 0:
                fund["owner_earnings_yield"] = fund["_annual_oe_ps"] / start_price
            
            # Compute all factors
            result = compute_all_factors(sym, start_d, tech, fund, start_price)
            if not result:
                continue
            
            # Record training sample
            sample = {
                "symbol": sym,
                "window": label,
                "start_date": start_d,
                "end_date": end_d,
                "start_price": start_price,
                "end_price": end_price,
                "return_pct": round(stock_return, 2),
                "sp500_return": round(sp_return, 2),
                "alpha": round(stock_return - sp_return, 2),
                "beat_sp500": 1 if stock_return > sp_return else 0,
                "signal": result["signal"],
                "composite": round(result["composite"], 4),
            }
            # Add all factor scores
            for f, v in result["factors"].items():
                if v is not None:
                    sample[f"f_{f}"] = round(v, 4) if isinstance(v, float) else v
            
            training.append(sample)
            window_results += 1
        
        log.info(f"  Window {label}: {window_results} scored | Skips: {skips}")
        log.info(f"  S&P 500: {sp_return:+.1f}%")
        
        if window_results > 0:
            avg_ret = sum(t["return_pct"] for t in training[-window_results:]) / window_results
            buys = [t for t in training[-window_results:] if t["signal"] == "BUY"]
            buy_avg = sum(t["return_pct"] for t in buys) / len(buys) if buys else 0
            log.info(f"  All stocks avg: {avg_ret:+.1f}% | BUY avg: {buy_avg:+.1f}% ({len(buys)} stocks)")
    
    log.info(f"\nBacktest complete: {len(training)} total training samples")
    return training

# ---------------------------------------------------------------------------
# ML TRAINING
# ---------------------------------------------------------------------------

def train_ml(training, output_dir="."):
    """Train ML models on the backtest data and output optimized weights."""
    log.info(f"\nTraining ML on {len(training)} samples...")
    
    try:
        import numpy as np
        from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
        from sklearn.linear_model import Ridge
        from sklearn.model_selection import cross_val_score
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        log.error("scikit-learn not installed! pip install scikit-learn")
        return None
    
    # Feature columns
    factor_cols = [c for c in training[0].keys() if c.startswith("f_")]
    log.info(f"  Features: {factor_cols}")
    
    X = np.array([[t.get(c, 0.5) for c in factor_cols] for t in training])
    y_return = np.array([t["return_pct"] for t in training])
    y_alpha = np.array([t["alpha"] for t in training])
    y_beat = np.array([t["beat_sp500"] for t in training])
    
    # Clean feature names
    feature_names = [c.replace("f_", "") for c in factor_cols]
    
    # Model 1: GBM for return prediction
    gbr = GradientBoostingRegressor(n_estimators=300, max_depth=4, learning_rate=0.03,
                                     min_samples_leaf=5, subsample=0.8, random_state=42)
    gbr.fit(X, y_return)
    
    # Model 2: GBM for alpha prediction
    gbr_alpha = GradientBoostingRegressor(n_estimators=300, max_depth=4, learning_rate=0.03,
                                           min_samples_leaf=5, subsample=0.8, random_state=42)
    gbr_alpha.fit(X, y_alpha)
    
    # Model 3: Classifier for outperformance
    gbc = GradientBoostingClassifier(n_estimators=300, max_depth=4, learning_rate=0.03,
                                      min_samples_leaf=5, subsample=0.8, random_state=42)
    gbc.fit(X, y_beat)
    
    # Cross-validation
    cv_k = min(10, len(X) // 5) if len(X) >= 20 else 3
    cv_scores = cross_val_score(gbr, X, y_return, cv=cv_k, scoring='r2')
    cv_alpha = cross_val_score(gbr_alpha, X, y_alpha, cv=cv_k, scoring='r2')
    
    # Ridge for interpretability
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)
    ridge = Ridge(alpha=1.0)
    ridge.fit(X_s, y_alpha)
    
    # ─── Report ───
    report = []
    report.append("=" * 100)
    report.append("  ML WEIGHT OPTIMIZATION REPORT")
    report.append(f"  Training samples: {len(training)}")
    report.append(f"  Features: {len(feature_names)}")
    report.append("=" * 100)
    
    report.append(f"\n  RETURN MODEL: R²={gbr.score(X, y_return):.3f} | CV R²={cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
    report.append(f"  ALPHA MODEL:  R²={gbr_alpha.score(X, y_alpha):.3f} | CV R²={cv_alpha.mean():.3f} ± {cv_alpha.std():.3f}")
    report.append(f"  CLASSIFIER:   Acc={gbc.score(X, y_beat):.3f}")
    
    # Feature importance (ensemble)
    ensemble_imp = (gbr.feature_importances_ + gbr_alpha.feature_importances_ + gbc.feature_importances_) / 3
    sorted_idx = np.argsort(ensemble_imp)[::-1]
    
    report.append(f"\n  ENSEMBLE FEATURE IMPORTANCE:")
    for i in sorted_idx:
        bar = "█" * int(ensemble_imp[i] * 60)
        report.append(f"    {feature_names[i]:<22} {ensemble_imp[i]:.4f}  {bar}")
    
    # Ridge coefficients
    report.append(f"\n  RIDGE COEFFICIENTS (standardized):")
    coeffs = sorted(zip(feature_names, ridge.coef_), key=lambda x: abs(x[1]), reverse=True)
    for name, coeff in coeffs[:15]:
        d = "📈" if coeff > 0 else "📉"
        report.append(f"    {d} {name:<22} {coeff:+.4f}")
    
    # ─── Generate v7 weights ───
    # Map ML features to v6 factor categories
    V6_FACTORS = {"technical", "upside", "analyst", "earnings", "insider", 
                  "proximity", "catastrophe", "quality", "news"}
    RAW_FEATURES = {"bull_score_raw", "momentum_20d", "trend_strength", "rsi", 
                    "prox_raw", "piotroski", "altman_z"}
    
    # Roll raw features into their parent factors
    factor_imp = {f: 0.0 for f in V6_FACTORS}
    raw_to_parent = {
        "bull_score_raw": "technical", "momentum_20d": "technical",
        "trend_strength": "technical", "rsi": "technical",
        "prox_raw": "proximity", "piotroski": "quality", "altman_z": "quality",
    }
    
    for i, fname in enumerate(feature_names):
        if fname in V6_FACTORS:
            factor_imp[fname] += ensemble_imp[i]
        elif fname in raw_to_parent:
            factor_imp[raw_to_parent[fname]] += ensemble_imp[i]
    
    # Add transcript/institutional/insider/news at reasonable defaults
    # (can't be backtested, so keep from v6)
    factor_imp["transcript"] = 0.08   # default
    factor_imp["institutional"] = 0.06  # default
    
    # Normalize
    total = sum(factor_imp.values())
    v7_weights = {f: v / total for f, v in factor_imp.items()}
    
    # Sort and print
    report.append(f"\n  RECOMMENDED v7 WEIGHTS:")
    report.append(f"  {'─' * 60}")
    v6_ref = {
        "technical": 0.15, "upside": 0.15, "analyst": 0.10, "transcript": 0.15,
        "institutional": 0.10, "insider": 0.10, "earnings": 0.10,
        "news": 0.05, "proximity": 0.05, "catastrophe": 0.05, "quality": 0.0,
    }
    sorted_v7 = sorted(v7_weights.items(), key=lambda x: x[1], reverse=True)
    report.append(f"  {'Factor':<18} {'v6':>8} {'v7 ML':>8} {'Change':>8}")
    for f, w in sorted_v7:
        v6 = v6_ref.get(f, 0)
        ch = w - v6
        arrow = "↑" if ch > 0.02 else "↓" if ch < -0.02 else "→"
        marker = " ★" if f == "quality" else ""
        report.append(f"  {f:<18} {v6:>7.1%} {w:>7.1%} {arrow}{ch:>+7.1%}{marker}")
    
    # ─── Signal performance ───
    report.append(f"\n  SIGNAL PERFORMANCE ACROSS ALL WINDOWS:")
    report.append(f"  {'─' * 60}")
    for sig in ["BUY", "WATCH", "HOLD", "SELL"]:
        group = [t for t in training if t["signal"] == sig]
        if not group: continue
        avg_ret = sum(t["return_pct"] for t in group) / len(group)
        avg_alpha = sum(t["alpha"] for t in group) / len(group)
        beat = sum(1 for t in group if t["beat_sp500"])
        report.append(f"  {sig:<6} ({len(group):>4} samples): Ret {avg_ret:>+6.1f}% | Alpha {avg_alpha:>+6.1f}% | Beat {beat}/{len(group)} ({beat/len(group)*100:.0f}%)")
    
    report_text = "\n".join(report)
    print(report_text)
    
    # Save outputs
    weights_path = os.path.join(output_dir, "v7_weights.json")
    with open(weights_path, "w") as f:
        json.dump(v7_weights, f, indent=2)
    log.info(f"  v7 weights saved to {weights_path}")
    
    report_path = os.path.join(output_dir, "backtest_report.txt")
    with open(report_path, "w") as f:
        f.write(report_text)
    log.info(f"  Report saved to {report_path}")
    
    return v7_weights

# ---------------------------------------------------------------------------
# GCS Upload
# ---------------------------------------------------------------------------

def gcs_upload(path, data):
    try:
        tok = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=3
        )
        token = tok.json().get("access_token", "")
        if not token: return
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o"
        r = requests.post(url, params={"uploadType": "media", "name": path},
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                          data=json.dumps(data, default=str), timeout=15)
        if r.status_code in (200, 201):
            log.info(f"  GCS: uploaded {path}")
    except:
        pass

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stock Screener v7 — Full Backtest + ML")
    parser.add_argument("--region", default=os.environ.get("SCREEN_INDEX", "nasdaq100"),
                        help="Region: nasdaq100, sp500, europe, global")
    parser.add_argument("--windows", type=int, default=6,
                        help="Number of monthly windows (used if --from/--to not given)")
    parser.add_argument("--from", dest="from_date", default="",
                        help="Start date YYYY-MM-DD (e.g. 2024-01-01)")
    parser.add_argument("--to", dest="to_date", default="",
                        help="End date YYYY-MM-DD (e.g. 2025-12-31)")
    parser.add_argument("--train-only", default="", help="CSV path to skip API and just train ML")
    parser.add_argument("--output", default=".", help="Output directory")
    args = parser.parse_args()
    
    if not FMP_KEY and not args.train_only:
        log.error("FMP_API_KEY not set!")
        sys.exit(1)
    
    os.makedirs(args.output, exist_ok=True)
    
    # Validate date args
    from_date = args.from_date if args.from_date else None
    to_date = args.to_date if args.to_date else None
    if from_date and not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")
        log.info(f"No --to given, using today: {to_date}")
    if to_date and not from_date:
        log.error("--to requires --from!")
        sys.exit(1)
    
    if from_date and to_date:
        # Calculate approximate number of windows for logging
        d1 = datetime.strptime(from_date, "%Y-%m-%d")
        d2 = datetime.strptime(to_date, "%Y-%m-%d")
        approx_windows = max(1, int((d2 - d1).days / 30))
        log.info(f"Date range: {from_date} → {to_date} (~{approx_windows} monthly windows)")
    
    if args.train_only:
        # Load existing training data
        log.info(f"Loading training data from {args.train_only}...")
        with open(args.train_only, "r") as f:
            reader = csv.DictReader(f)
            training = []
            for row in reader:
                # Convert numeric fields
                for k in row:
                    try: row[k] = float(row[k])
                    except: pass
                training.append(row)
        log.info(f"  Loaded {len(training)} samples")
    else:
        # Run full backtest
        training = run_backtest(
            region=args.region,
            num_windows=args.windows,
            from_date=from_date,
            to_date=to_date,
        )
        
        if not training:
            log.error("No training data generated!")
            return
        
        # Save training data CSV
        csv_path = os.path.join(args.output, "training_data.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=training[0].keys())
            writer.writeheader()
            writer.writerows(training)
        log.info(f"  Training data ({len(training)} samples) saved to {csv_path}")
        
        # Upload to GCS
        today = datetime.now().strftime("%Y-%m-%d")
        gcs_upload(f"backtest/{today}.json", {
            "date": today, "region": args.region, "windows": args.windows,
            "samples": len(training), "data": training,
        })
    
    # Train ML
    if len(training) >= 20:
        v7_weights = train_ml(training, output_dir=args.output)
        
        if v7_weights:
            # Upload weights to GCS
            gcs_upload("backtest/v7_weights.json", v7_weights)
    else:
        log.warning(f"Only {len(training)} samples — need at least 20 for ML training")
    
    log.info("\nDone!")

if __name__ == "__main__":
    main()
