#!/usr/bin/env python3
"""
Stock Screener v6 — 10-Factor Composite Scoring
Architecture: Two-pass (cheap screen → expensive enrichment)
Factors: Upside 15% | Tech 15% | Analyst 10% | Transcript 15% | Institutional 10%
         Insider 10% | Earnings 10% | News 5% | 52wk 5% | Catastrophe 5%
"""

import os, sys, json, math, time, logging, smtplib, argparse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP = "https://financialmodelingprep.com/stable"
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

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

# Factor weights (must sum to 1.0)
WEIGHTS = {
    "upside": 0.15,
    "technical": 0.15,
    "analyst": 0.10,
    "transcript": 0.15,
    "institutional": 0.10,
    "insider": 0.10,
    "earnings": 0.10,
    "news": 0.05,
    "proximity": 0.05,
    "catastrophe": 0.05,
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v6")

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

    # Composite
    composite: float = 0.0
    signal: str = "HOLD"
    classification: str = ""
    reasons: list = field(default_factory=list)

    # Factor breakdown for transparency
    factor_scores: dict = field(default_factory=dict)

# ---------------------------------------------------------------------------
# 1. Stock Discovery (unchanged from v5)
# ---------------------------------------------------------------------------

REGIONS = {
    "nasdaq100": [("NASDAQ", None, 20_000_000_000, 100)],
    "sp500": [("NASDAQ", None, 10_000_000_000, 250), ("NYSE", None, 10_000_000_000, 250)],
    "europe": [
        ("XETRA", "DE", 5_000_000_000, 40), ("PAR", "FR", 5_000_000_000, 30),
        ("LSE", "UK", 5_000_000_000, 40), ("AMS", "NL", 5_000_000_000, 20),
        ("MIL", "IT", 5_000_000_000, 15), ("STO", "SE", 5_000_000_000, 15),
        ("SIX", "CH", 5_000_000_000, 15), ("BME", "ES", 5_000_000_000, 10),
    ],
    "asia": [
        ("JPX", "JP", 20_000_000_000, 40), ("HKSE", "HK", 10_000_000_000, 30),
        ("KSC", "KR", 10_000_000_000, 20), ("SHH", "CN", 20_000_000_000, 30),
        ("SHZ", "CN", 20_000_000_000, 20), ("BSE", "IN", 20_000_000_000, 20),
        ("SES", "SG", 5_000_000_000, 10), ("ASX", "AU", 10_000_000_000, 20),
    ],
    "brazil": [("SAO", "BR", 5_000_000_000, 30)],
    "global": None,
}

def get_symbols(region: str) -> list[str]:
    if region == "global":
        syms = []
        for r in ["sp500", "europe", "asia"]:
            syms.extend(get_symbols(r))
        return list(dict.fromkeys(syms))
    configs = REGIONS.get(region)
    if configs is None:
        configs = [(region.upper(), None, 5_000_000_000, 50)]
    symbols = []
    for exchange, country, min_cap, limit in configs:
        params = {
            "exchange": exchange, "marketCapMoreThan": min_cap,
            "isActivelyTrading": "true", "isEtf": "false", "isFund": "false",
            "limit": limit,
        }
        if country:
            params["country"] = country
        data = fmp("company-screener", params)
        if data:
            batch = [d["symbol"] for d in data if "symbol" in d]
            log.info(f"  {exchange}/{country or 'all'}: {len(batch)} stocks (cap>{min_cap/1e9:.0f}B)")
            symbols.extend(batch)
        else:
            log.warning(f"  {exchange}: screener returned no data")
    return list(dict.fromkeys(symbols))

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
    if len(closes) < lookback + 1:
        return "flat"
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
    }

# ---------------------------------------------------------------------------
# 4. Analyst (targets + grades + earnings)
# ---------------------------------------------------------------------------

def get_analyst(sym: str) -> dict:
    result = {"target": 0, "upside": 0, "grade_score": 0.5,
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
        "intrinsic_buffett": 0, "intrinsic_avg": 0,
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

    # Financial scores
    scores = fmp("financial-scores", {"symbol": sym})
    if scores:
        v["piotroski"] = int(scores[0].get("piotroskiScore", 0))
        v["altman_z"] = float(scores[0].get("altmanZScore", 0))

    # DCF — FMP returns in REPORTING currency
    dcf = fmp("discounted-cash-flow", {"symbol": sym})
    if dcf:
        raw_dcf = float(dcf[0].get("dcf", 0))
        if need_fx and raw_dcf > 0:
            ratio = raw_dcf / price if price > 0 else 0
            if 0.1 < ratio < 10:
                v["dcf_value"] = raw_dcf * fx_to_report
            else:
                v["dcf_value"] = raw_dcf
        else:
            v["dcf_value"] = raw_dcf

    # Owner earnings — in REPORTING currency
    oe = fmp("owner-earnings", {"symbol": sym, "limit": 4})
    if oe:
        annual_oe_ps = sum(float(x.get("ownersEarningsPerShare", 0)) for x in oe)
        if local_price > 0:
            v["owner_earnings_yield"] = annual_oe_ps / local_price

    # Intrinsic value — Buffett earnings growth method
    if inc and len(inc) >= 2:
        inc.sort(key=lambda x: x.get("date", ""))
        latest_eps = float(inc[-1].get("epsDiluted", 0))
        if latest_eps > 0:
            base_growth = min(v["revenue_cagr_3y"], 0.30)
            growth_rates = [base_growth * (0.8 ** i) for i in range(5)]
            future_eps = latest_eps
            for g in growth_rates:
                future_eps *= (1 + max(g, 0.03))
            terminal_pe = min(max(15, 1 / max(RISK_FREE, 0.03)), 30)
            future_price = future_eps * terminal_pe
            v["intrinsic_buffett"] = future_price / (1.10 ** 5)

    # Average intrinsic — all in reporting currency, MoS vs local_price
    methods = [v["dcf_value"], v["intrinsic_buffett"]]
    valid = [m for m in methods if m > 0]
    if valid and local_price > 0:
        v["intrinsic_avg"] = sum(valid) / len(valid)
        v["margin_of_safety"] = (v["intrinsic_avg"] - local_price) / local_price

    # Convert intrinsic values to price currency for display
    if need_fx:
        for key in ("dcf_value", "intrinsic_buffett", "intrinsic_avg"):
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
    result = {"buy_ratio": 0.0, "net_buys": 0, "score": 0.5}

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

    return result

# ---------------------------------------------------------------------------
# 7. NEW: News Sentiment (FMP search-stock-news)
# ---------------------------------------------------------------------------

def get_news_sentiment(sym: str) -> dict:
    """Fetch recent stock news and estimate sentiment from title keywords."""
    result = {"sentiment": 0.0, "score": 0.5, "count": 0}

    data = fmp("search-stock-news", {"symbols": sym, "limit": 15})
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
    result = {"momentum": 0.0, "score": 0.5}

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
    return result

# ---------------------------------------------------------------------------
# 10. NEW: Upside Potential (enhanced with DCF cross-check)
# ---------------------------------------------------------------------------

def compute_upside_score(analyst: dict, value: dict, price: float) -> dict:
    """Score based on target upside cross-checked with intrinsic value."""
    result = {"score": 0.0, "consensus_upside": 0, "dcf_upside": 0}

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
# 12. NEW: Transcript Sentiment (Claude API) — EXPENSIVE, pass-2 only
# ---------------------------------------------------------------------------

def get_transcript_sentiment(sym: str) -> dict:
    """Fetch latest earnings transcript and analyze with Claude API."""
    result = {"sentiment": 0.0, "summary": "", "score": 0.5}

    if not ANTHROPIC_KEY:
        log.info(f"  {sym}: no ANTHROPIC_KEY, skipping transcript")
        return result

    # Get latest transcript
    now = datetime.now()
    year = now.year
    # Try current year quarters from most recent backward
    transcript = None
    for q in [4, 3, 2, 1]:
        for y in [year, year - 1]:
            data = fmp("earning-call-transcript", {"symbol": sym, "year": y, "quarter": q})
            if data and data[0].get("content"):
                transcript = data[0]
                break
        if transcript:
            break

    if not transcript:
        log.info(f"  {sym}: no transcript found")
        return result

    content = transcript.get("content", "")[:8000]  # limit tokens

    # Call Claude API for sentiment analysis
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
            # Map -1..1 to 0..1
            result["score"] = min(max((result["sentiment"] + 1) / 2, 0), 1)
            log.info(f"  {sym}: transcript sentiment={result['sentiment']:.2f}")
        else:
            log.warning(f"  {sym}: Claude API {resp.status_code}")
    except json.JSONDecodeError:
        log.warning(f"  {sym}: failed to parse Claude response")
    except Exception as e:
        log.warning(f"  {sym}: transcript analysis error: {e}")

    return result

# ---------------------------------------------------------------------------
# 13. NEW: Institutional Flows (FMP 13F symbol-positions-summary)
# ---------------------------------------------------------------------------

def get_institutional_flows(sym: str) -> dict:
    """Check institutional ownership changes. Score 0-1."""
    result = {"holders_change": 0.0, "accumulation": 0.0, "score": 0.5}

    now = datetime.now()
    # Current quarter
    cur_q = (now.month - 1) // 3 + 1
    cur_y = now.year
    # Previous quarter
    prev_q = cur_q - 1 if cur_q > 1 else 4
    prev_y = cur_y if cur_q > 1 else cur_y - 1

    cur_data = fmp("institutional-ownership/symbol-positions-summary",
                   {"symbol": sym, "year": cur_y, "quarter": cur_q})
    prev_data = fmp("institutional-ownership/symbol-positions-summary",
                    {"symbol": sym, "year": prev_y, "quarter": prev_q})

    if not cur_data and not prev_data:
        # Try one more quarter back
        pp_q = prev_q - 1 if prev_q > 1 else 4
        pp_y = prev_y if prev_q > 1 else prev_y - 1
        cur_data = prev_data
        prev_data = fmp("institutional-ownership/symbol-positions-summary",
                        {"symbol": sym, "year": pp_y, "quarter": pp_q})

    if cur_data and prev_data:
        cur_holders = len(cur_data) if isinstance(cur_data, list) else 0
        prev_holders = len(prev_data) if isinstance(prev_data, list) else 0

        if prev_holders > 0:
            result["holders_change"] = (cur_holders - prev_holders) / prev_holders

        # Check share accumulation trend
        cur_shares = sum(float(h.get("shares", 0)) for h in cur_data) if isinstance(cur_data, list) else 0
        prev_shares = sum(float(h.get("shares", 0)) for h in prev_data) if isinstance(prev_data, list) else 0

        if prev_shares > 0:
            result["accumulation"] = (cur_shares - prev_shares) / prev_shares

        # Score
        acc = result["accumulation"]
        hc = result["holders_change"]
        if acc > 0.10 and hc > 0.05:
            result["score"] = 1.0   # strong accumulation
        elif acc > 0.05 or hc > 0.05:
            result["score"] = 0.75  # moderate accumulation
        elif acc > -0.05 and hc > -0.05:
            result["score"] = 0.5   # neutral
        elif acc < -0.10 or hc < -0.10:
            result["score"] = 0.15  # distribution
        else:
            result["score"] = 0.3   # mild reduction

    elif cur_data:
        result["score"] = 0.5  # only current data, neutral

    return result

# ---------------------------------------------------------------------------
# 14. Composite Score & Signal (10-factor)
# ---------------------------------------------------------------------------

def compute_composite_v6(
    tech: dict, analyst: dict, value: dict, price: float,
    insider: dict, news: dict, proximity: dict, earnings: dict,
    upside: dict, catastrophe: dict, transcript: dict = None,
    institutional: dict = None,
) -> tuple:
    """
    10-factor composite. Returns (composite, signal, factor_scores, reasons).
    If transcript/institutional unavailable, redistribute their weight.
    """

    factors = {}

    # 1. Upside potential (15%)
    factors["upside"] = upside.get("score", 0)

    # 2. Technical bull score (15%)
    factors["technical"] = tech["bull_score"] / 10

    # 3. Analyst buy ratio (10%)
    factors["analyst"] = analyst.get("grade_score", 0.5)

    # 4. Transcript sentiment (15%) — may be None
    if transcript and transcript.get("score", 0.5) != 0.5:
        factors["transcript"] = transcript["score"]
    else:
        factors["transcript"] = None  # redistribute

    # 5. Institutional flows (10%) — may be None
    if institutional and institutional.get("score", 0.5) != 0.5:
        factors["institutional"] = institutional["score"]
    else:
        factors["institutional"] = None  # redistribute

    # 6. Insider activity (10%)
    factors["insider"] = insider.get("score", 0.5)

    # 7. Earnings momentum (10%)
    factors["earnings"] = earnings.get("score", 0.5)

    # 8. News sentiment (5%)
    factors["news"] = news.get("score", 0.5)

    # 9. 52-week proximity (5%)
    factors["proximity"] = proximity.get("score", 0.5)

    # 10. Catastrophe detector (5%) — inverted: high score = no catastrophe = good
    factors["catastrophe"] = catastrophe.get("score", 1.0)

    # Weight redistribution for missing factors
    active_weights = {}
    missing_weight = 0
    for factor, weight in WEIGHTS.items():
        if factors.get(factor) is not None:
            active_weights[factor] = weight
        else:
            missing_weight += weight
            factors[factor] = 0.5  # neutral placeholder

    # Redistribute missing weight proportionally to active factors
    if missing_weight > 0 and active_weights:
        total_active = sum(active_weights.values())
        for factor in active_weights:
            active_weights[factor] += missing_weight * (active_weights[factor] / total_active)
    else:
        active_weights = WEIGHTS.copy()

    # Compute weighted composite
    composite = sum(factors[f] * active_weights.get(f, WEIGHTS[f]) for f in WEIGHTS)

    # Collect reasons
    reasons = catastrophe.get("flags", [])

    # Signal classification
    bull = tech["bull_score"]
    mos = value.get("margin_of_safety", 0)
    ins = insider.get("score", 0.5)
    trans = factors.get("transcript", 0.5)

    # Multi-factor signal: require agreement across dimensions
    bullish_count = sum([
        composite > 0.60,
        bull >= 6,
        mos > 0.10,
        ins >= 0.6,
        factors["earnings"] >= 0.6,
    ])
    bearish_count = sum([
        composite < 0.30,
        bull <= 2,
        mos < -0.20,
        ins <= 0.2,
        factors["earnings"] <= 0.3,
    ])

    if bullish_count >= 4 and composite > 0.55:
        signal = "BUY"
    elif bullish_count >= 3 and composite > 0.45:
        signal = "WATCH"
    elif bearish_count >= 3 or composite < 0.25:
        signal = "SELL"
    else:
        signal = "HOLD"

    return composite, signal, factors, reasons

# ---------------------------------------------------------------------------
# 15. Main Screening Loop (Two-Pass Architecture)
# ---------------------------------------------------------------------------

def screen(symbols: list[str], enrich_top_n: int = ENRICH_TOP_N, skip_transcripts: bool = False) -> list[Stock]:
    results = []
    total = len(symbols)
    skips = {"quote": 0, "tech": 0}

    log.info(f"Starting v6 screen of {total} symbols")
    log.info(f"Pass 1: Cheap screen (quote + chart + fundamentals + grades + earnings + insiders + news)")

    # Pre-fetch all quotes in batches
    all_quotes = get_quotes_batch(symbols)

    # ═══════════════ PASS 1: Cheap Data ═══════════════
    pass1_stocks = []

    for i, sym in enumerate(symbols):
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

        # News Sentiment (1 API call)
        nws = get_news_sentiment(sym)

        # 52-week proximity (from existing quote data, no API call)
        prox = compute_52wk_proximity(q)

        # Earnings momentum (from existing analyst data, no API call)
        earn = compute_earnings_momentum(a)

        # Upside score (from existing data, no API call)
        ups = compute_upside_score(a, v, price)

        # Catastrophe detector (from existing data, no API call)
        cat = compute_catastrophe(t, v, a, ins)

        # Compute pass-1 composite (no transcript or institutional yet)
        composite, signal, factors, reasons = compute_composite_v6(
            t, a, v, price, ins, nws, prox, earn, ups, cat,
            transcript=None, institutional=None,
        )

        s = Stock(
            symbol=sym, price=price, currency=q["currency"],
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
            news_sentiment=nws["sentiment"], news_score=nws["score"],
            proximity_52wk=prox["proximity"], proximity_score=prox["score"],
            earnings_momentum=earn["momentum"], earnings_score=earn["score"],
            upside_score=ups["score"],
            catastrophe_score=cat["score"],
            composite=composite, signal=signal,
            classification=v["classification"],
            reasons=t.get("bull_reasons", []) + reasons,
            factor_scores=factors,
        )

        # Stash raw data for pass 2
        s._raw = {"tech": t, "analyst": a, "value": v, "price": price,
                   "insider": ins, "news": nws, "proximity": prox,
                   "earnings": earn, "upside": ups, "catastrophe": cat, "quote": q}

        pass1_stocks.append(s)

    # Sort by pass-1 composite
    pass1_stocks.sort(key=lambda x: x.composite, reverse=True)
    log.info(f"Pass 1 complete: {len(pass1_stocks)} scored | Skipped: {skips}")

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

        # Recompute composite with all 10 factors
        composite, signal, factors, reasons = compute_composite_v6(
            raw["tech"], raw["analyst"], raw["value"], raw["price"],
            raw["insider"], raw["news"], raw["proximity"],
            raw["earnings"], raw["upside"], raw["catastrophe"],
            transcript=trans, institutional=inst,
        )

        s.composite = composite
        s.signal = signal
        s.factor_scores = factors
        s.reasons = raw["tech"].get("bull_reasons", []) + reasons

    # Clean up raw data
    for s in pass1_stocks:
        if hasattr(s, '_raw'):
            del s._raw

    # Re-sort after pass 2
    pass1_stocks.sort(key=lambda x: x.composite, reverse=True)
    log.info(f"Screen complete: {len(pass1_stocks)} total scored")

    return pass1_stocks

# ---------------------------------------------------------------------------
# 16. Report Formatting
# ---------------------------------------------------------------------------

def format_report(stocks: list[Stock], region: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"{'='*95}",
        f"  STOCK SCREENER v6 — {region.upper()} — {now}",
        f"  10-Factor: Upside 15% | Tech 15% | Analyst 10% | Transcript 15%",
        f"             Institutional 10% | Insider 10% | Earnings 10% | News 5% | 52wk 5% | Catastrophe 5%",
        f"{'='*95}\n",
    ]

    for signal_group in ["BUY", "WATCH", "HOLD", "SELL"]:
        group = [s for s in stocks if s.signal == signal_group]
        if not group:
            continue
        emoji = {"BUY": "🟢", "WATCH": "🟠", "HOLD": "🟡", "SELL": "🔴"}[signal_group]
        lines.append(f"  {emoji} {signal_group} ({len(group)} stocks)")
        lines.append(f"  {'─'*90}")

        for s in group[:TOP_N]:
            lines.append(f"\n  {s.symbol:<12} {s.currency} {s.price:>8.2f}  │  Composite: {s.composite:.3f}  │  {s.classification}")

            # Factor breakdown
            fs = s.factor_scores
            if fs:
                factor_strs = []
                for f in ["upside", "technical", "analyst", "transcript", "insider",
                          "institutional", "earnings", "news", "proximity", "catastrophe"]:
                    val = fs.get(f, 0.5)
                    bar = "█" * int(val * 5)
                    factor_strs.append(f"{f[:5]}:{val:.2f}")
                lines.append(f"    Factors:    {' | '.join(factor_strs[:5])}")
                lines.append(f"                {' | '.join(factor_strs[5:])}")

            lines.append(f"    Technical:  Bull {s.bull_score}/10  RSI {s.rsi:.0f}  MACD {s.macd_signal}  ADX {s.adx:.0f}")
            lines.append(f"    Value:      MoS {s.margin_of_safety:+.0%}  ROE {s.roe_avg:.0%}  GM {s.gross_margin:.0%}({s.gross_margin_trend})")
            lines.append(f"                Piotroski {s.piotroski}/9  Altman {s.altman_z:.1f}  RevCAGR {s.revenue_cagr_3y:.0%}  EPSCAGR {s.eps_cagr_3y:.0%}")

            iv_str = f"DCF ${s.dcf_value:.0f}" if s.dcf_value else "N/A"
            buf_str = f"Buffett ${s.intrinsic_buffett:.0f}" if s.intrinsic_buffett else "N/A"
            oe_str = f"OE Yield {s.owner_earnings_yield:.1%}" if s.owner_earnings_yield else "N/A"
            lines.append(f"                Intrinsic: {iv_str} | {buf_str} | {oe_str}")

            lines.append(f"    Analyst:    Target ${s.target:.0f} ({s.upside:+.1f}%)  Grades {s.grade_buy}/{s.grade_total} buy  EPS {s.eps_beats}/{s.eps_total} beats")
            lines.append(f"    Insider:    Buy ratio {s.insider_buy_ratio:.2f}  Net buys: {s.insider_net_buys}  Score: {s.insider_score:.2f}")
            lines.append(f"    News:       Sentiment {s.news_sentiment:+.2f}  52wk: {s.proximity_52wk:.0%}")

            if s.transcript_summary:
                lines.append(f"    Transcript: {s.transcript_sentiment:+.2f} — {s.transcript_summary}")

            if s.reasons:
                lines.append(f"    Signals:    {', '.join(s.reasons[:8])}")
        lines.append("")

    buy_count = sum(1 for s in stocks if s.signal == "BUY")
    watch_count = sum(1 for s in stocks if s.signal == "WATCH")
    lines.append(f"  SUMMARY: {len(stocks)} screened → {buy_count} BUY, {watch_count} WATCH")
    if stocks:
        lines.append(f"  Top composite: {stocks[0].symbol} ({stocks[0].composite:.3f})")

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

def save_scan_to_gcs(stocks: list, region: str):
    today = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "scan_date": datetime.now().isoformat(),
        "region": region,
        "version": "v6",
        "weights": WEIGHTS,
        "summary": {
            "total": len(stocks),
            "buy": sum(1 for s in stocks if s.signal == "BUY"),
            "watch": sum(1 for s in stocks if s.signal == "WATCH"),
            "hold": sum(1 for s in stocks if s.signal == "HOLD"),
            "sell": sum(1 for s in stocks if s.signal == "SELL"),
        },
        "stocks": [asdict(s) for s in stocks],
    }
    gcs_upload("scans/latest.json", payload)
    gcs_upload(f"scans/{today}.json", payload)

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
            "target": s.target,
        })
        history[key]["entries"] = history[key]["entries"][-60:]
    save_signals(history)

# ---------------------------------------------------------------------------
# 19. Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stock Screener v6")
    parser.add_argument("--region", default=os.environ.get("SCREEN_INDEX", "nasdaq100"))
    parser.add_argument("--symbols", default="", help="Comma-separated symbols")
    parser.add_argument("--top", type=int, default=TOP_N)
    parser.add_argument("--enrich", type=int, default=ENRICH_TOP_N,
                        help="How many top stocks get transcript/institutional enrichment")
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--no-transcripts", action="store_true",
                        help="Skip Claude API transcript analysis")
    args = parser.parse_args()

    if not FMP_KEY:
        log.error("FMP_API_KEY not set!")
        sys.exit(1)

    enrich_count = args.enrich
    skip_transcripts = args.no_transcripts

    # Get symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_symbols(args.region)

    if not symbols:
        log.error("No symbols to screen!")
        return "No symbols found."

    # Screen
    results = screen(symbols, enrich_top_n=enrich_count, skip_transcripts=skip_transcripts)

    # Report
    report = format_report(results[:args.top * 3], args.region)
    print(report)

    # Save signals
    update_signal_history(results)

    # Save to GCS
    save_scan_to_gcs(results, args.region)

    # Email
    today = datetime.now().strftime("%Y-%m-%d")
    if args.email or SMTP_USER:
        send_email(f"Screener v6: {args.region.upper()} — {today}", report)

    return report

if __name__ == "__main__":
    main()
