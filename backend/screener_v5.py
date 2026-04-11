#!/usr/bin/env python3
"""
Stock Screener v5 — Buffett Value + Technical + Analyst
All FMP endpoints verified against stable REST API on 2026-04-11.
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

RATE_LIMIT = 0.12  # seconds between API calls (3000/min on Ultimate)
RISK_FREE = 0.045  # 10yr treasury ~4.5%
TOP_N = 15
SIGNAL_LOG = os.environ.get("SIGNAL_LOG", "signal_history.json")

# Currency conversion cache
_fx_cache: dict[str, float] = {}

def get_fx_rate(from_ccy: str, to_ccy: str) -> float:
    """Get exchange rate. Returns 1.0 if same currency or lookup fails."""
    if from_ccy == to_ccy:
        return 1.0
    key = f"{from_ccy}{to_ccy}"
    if key in _fx_cache:
        return _fx_cache[key]
    data = fmp("forex", {"symbol": f"{from_ccy}/{to_ccy}"})
    if data and data[0].get("price"):
        rate = float(data[0]["price"])
        _fx_cache[key] = rate
        log.info(f"FX {from_ccy}→{to_ccy}: {rate:.4f}")
        return rate
    # Fallback hardcoded rates for common mismatches
    fallback = {"CNYUSD": 0.14, "USDCNY": 7.1, "EURUSD": 1.08, "USDEUR": 0.93,
                "GBPUSD": 1.27, "USDGBP": 0.79, "JPYUSD": 0.0067, "USDJPY": 150.0}
    rate = fallback.get(key, 1.0)
    _fx_cache[key] = rate
    if rate != 1.0:
        log.info(f"FX {from_ccy}→{to_ccy}: {rate:.4f} (fallback)")
    return rate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v5")

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
    macd_signal: str = ""     # "bullish_cross", "bearish_cross", "bullish", "bearish"
    adx: float = 0.0
    bb_pct: float = 0.5       # Bollinger %B
    stoch_rsi: float = 50.0
    obv_trend: str = ""       # "rising", "falling", "flat"
    bull_score: int = 0       # 0-10

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
    roe_consistent: bool = False  # >15% all years
    roic_avg: float = 0.0
    gross_margin: float = 0.0
    gross_margin_trend: str = ""  # "expanding", "stable", "contracting"
    piotroski: int = 0
    altman_z: float = 0.0
    dcf_value: float = 0.0
    owner_earnings_yield: float = 0.0
    intrinsic_buffett: float = 0.0  # earnings growth method
    intrinsic_avg: float = 0.0      # average of all methods
    margin_of_safety: float = 0.0   # (intrinsic - price) / price
    value_score: float = 0.0        # 0-1

    # Composite
    composite: float = 0.0
    signal: str = "HOLD"
    classification: str = ""  # "VALUE", "DEEP_VALUE", "GROWTH", "SPECULATIVE", etc.
    reasons: list = field(default_factory=list)

# ---------------------------------------------------------------------------
# 1. Stock Discovery (dynamic via company-screener)
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
    "global": None,  # combines sp500 + europe + asia
}

def get_symbols(region: str) -> list[str]:
    """Discover stocks dynamically from FMP company-screener."""
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
            "exchange": exchange,
            "marketCapMoreThan": min_cap,
            "isActivelyTrading": "true",
            "isEtf": "false",
            "isFund": "false",
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
    q = data[0]
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
    # Try batch first (10 per call)
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

# ---------------------------------------------------------------------------
# 3. Technicals — computed from OHLCV chart data
# ---------------------------------------------------------------------------

def get_chart(sym: str, days: int = 200) -> Optional[list]:
    """Fetch daily OHLCV data. Returns oldest→newest."""
    start = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    data = fmp("historical-price-eod/full", {"symbol": sym, "from": start, "to": end})
    if not data or len(data) < 30:
        return None
    # FMP returns newest first; reverse to oldest→newest
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
    """MACD (12, 26, 9). Returns signal status."""
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
    """Average Directional Index."""
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
    """Bollinger %B: (price - lower) / (upper - lower)."""
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
    """Stochastic RSI."""
    if len(closes) < rsi_period + stoch_period:
        return 50.0
    # Compute RSI series
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
    """Compute all technical indicators from chart + quote data."""
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

    # SMA20 from chart
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else closes[-1]

    # Bull score: 10 signals
    score = 0
    reasons = []

    # 1. Price > SMA50
    if price > sma50 > 0:
        score += 1; reasons.append(">SMA50")
    # 2. SMA50 > SMA200 (golden cross)
    if sma50 > sma200 > 0:
        score += 1; reasons.append("Golden cross")
    # 3. RSI momentum (40-70 sweet spot)
    if 40 < rsi < 70:
        score += 1; reasons.append(f"RSI {rsi:.0f}")
    # 4. MACD bullish
    if macd["signal"] in ("bullish", "bullish_cross"):
        score += 1; reasons.append(f"MACD {macd['signal']}")
    # 5. ADX > 20 (trending)
    if adx > 20:
        score += 1; reasons.append(f"ADX {adx:.0f}")
    # 6. Bollinger %B 0.3-0.8
    if 0.3 < bb_pct < 0.8:
        score += 1; reasons.append(f"BB%B {bb_pct:.2f}")
    # 7. Price > SMA20 (short-term trend)
    if price > sma20:
        score += 1; reasons.append(">SMA20")
    # 8. Stochastic RSI not overbought
    if 20 < stoch < 80:
        score += 1; reasons.append(f"StochRSI {stoch:.0f}")
    # 9. OBV rising
    if obv == "rising":
        score += 1; reasons.append("OBV rising")
    # 10. Near 52wk high (within 15%)
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
              "grade_buy": 0, "grade_total": 0, "eps_beats": 0, "eps_total": 0}

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

    # Earnings beats
    earnings = fmp("earnings", {"symbol": sym, "limit": 8})
    if earnings:
        for e in earnings:
            actual = e.get("epsActual")
            est = e.get("epsEstimated")
            if actual is not None and est is not None:
                result["eps_total"] += 1
                if float(actual) >= float(est):
                    result["eps_beats"] += 1

    return result

# ---------------------------------------------------------------------------
# 5. Value / Buffett Layer
# ---------------------------------------------------------------------------

def safe_cagr(start, end, years):
    if not start or not end or start <= 0 or end <= 0 or years <= 0:
        return 0.0
    return (end / start) ** (1 / years) - 1

def get_value(sym: str, price: float, price_currency: str = "USD") -> dict:
    """Full Buffett value analysis."""
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
    if inc and len(inc) >= 2:
        inc.sort(key=lambda x: x.get("date", ""))  # oldest first
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

        # Gross margin
        if revs[-1] > 0 and gp_list[-1] > 0:
            v["gross_margin"] = gp_list[-1] / revs[-1]
        # Trend
        margins = [gp / rev if rev > 0 else 0 for gp, rev in zip(gp_list, revs)]
        if len(margins) >= 3:
            if margins[-1] > margins[-3] + 0.02:
                v["gross_margin_trend"] = "expanding"
            elif margins[-1] < margins[-3] - 0.02:
                v["gross_margin_trend"] = "contracting"
            else:
                v["gross_margin_trend"] = "stable"

    # Key metrics (5 years for ROE/ROIC consistency)
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

    # Financial scores (Piotroski, Altman Z)
    scores = fmp("financial-scores", {"symbol": sym})
    if scores:
        v["piotroski"] = int(scores[0].get("piotroskiScore", 0))
        v["altman_z"] = float(scores[0].get("altmanZScore", 0))

    # DCF
    dcf = fmp("discounted-cash-flow", {"symbol": sym})
    if dcf:
        v["dcf_value"] = float(dcf[0].get("dcf", 0))

    # Owner earnings (annualize from quarterly)
    oe = fmp("owner-earnings", {"symbol": sym, "limit": 4})
    if oe:
        annual_oe_ps = sum(float(x.get("ownersEarningsPerShare", 0)) for x in oe)
        if price > 0:
            v["owner_earnings_yield"] = annual_oe_ps / price

    # Intrinsic value — Buffett earnings growth method
    if inc and len(inc) >= 2:
        inc.sort(key=lambda x: x.get("date", ""))
        latest_eps = float(inc[-1].get("epsDiluted", 0))
        if latest_eps > 0:
            # Project 5 years with decelerating growth
            base_growth = min(v["revenue_cagr_3y"], 0.30)  # cap at 30%
            growth_rates = [base_growth * (0.8 ** i) for i in range(5)]
            future_eps = latest_eps
            for g in growth_rates:
                future_eps *= (1 + max(g, 0.03))  # floor at 3%
            terminal_pe = min(max(15, 1 / max(RISK_FREE, 0.03)), 30)
            future_price = future_eps * terminal_pe
            v["intrinsic_buffett"] = future_price / (1.10 ** 5)

    # Average intrinsic value — with currency normalization
    # Detect reporting currency from financial statements
    reported_ccy = "USD"
    if inc and inc[-1].get("reportedCurrency"):
        reported_ccy = inc[-1]["reportedCurrency"]
    fx = get_fx_rate(reported_ccy, price_currency)
    # DCF and Buffett intrinsic are in reporting currency → convert to price currency
    if fx != 1.0:
        log.info(f"  {sym}: converting intrinsic {reported_ccy}→{price_currency} (×{fx:.4f})")
        if v["dcf_value"] > 0:
            v["dcf_value"] *= fx
        if v["intrinsic_buffett"] > 0:
            v["intrinsic_buffett"] *= fx

    methods = [v["dcf_value"], v["intrinsic_buffett"]]
    valid = [m for m in methods if m > 0]
    if valid:
        v["intrinsic_avg"] = sum(valid) / len(valid)
        v["margin_of_safety"] = (v["intrinsic_avg"] - price) / price

    # Value score (0-1)
    vs = 0.0
    # Margin of safety (0-0.3)
    mos = v["margin_of_safety"]
    vs += min(max(mos, 0), 0.5) * 0.6  # up to 0.3 for 50%+ MOS

    # Quality (0-0.4)
    if v["roe_consistent"]:
        vs += 0.1
    if v["roe_avg"] > 0.15:
        vs += 0.05
    if v["roic_avg"] > 0.12:
        vs += 0.05
    if v["gross_margin"] > 0.40:
        vs += 0.05
    if v["gross_margin_trend"] == "expanding":
        vs += 0.05
    if v["piotroski"] >= 7:
        vs += 0.05
    elif v["piotroski"] >= 5:
        vs += 0.02
    if v["altman_z"] > 3.0:
        vs += 0.05
    elif v["altman_z"] > 1.8:
        vs += 0.02

    # Growth (0-0.2)
    if v["revenue_cagr_3y"] > 0.15:
        vs += 0.1
    elif v["revenue_cagr_3y"] > 0.08:
        vs += 0.05
    if v["eps_cagr_3y"] > 0.15:
        vs += 0.1
    elif v["eps_cagr_3y"] > 0.08:
        vs += 0.05

    # Owner earnings vs risk-free (0-0.1)
    if v["owner_earnings_yield"] > RISK_FREE:
        vs += 0.1
    elif v["owner_earnings_yield"] > RISK_FREE * 0.5:
        vs += 0.05

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
        # Negative MoS alone doesn't mean SPECULATIVE if fundamentals are strong
        v["classification"] = "SPECULATIVE"
    else:
        v["classification"] = "NEUTRAL"

    return v

# ---------------------------------------------------------------------------
# 6. Composite Score & Signal
# ---------------------------------------------------------------------------

def compute_composite(tech: dict, analyst: dict, value: dict, price: float) -> tuple:
    """Returns (composite_score, signal, reasons)."""

    # Technical (30%)
    t_score = tech["bull_score"] / 10  # normalize to 0-1
    t_weighted = t_score * 0.30

    # Value (50%)
    v_weighted = value["value_score"] * 0.50

    # Analyst (20%)
    a_score = 0.0
    if analyst["target"] > 0 and price > 0:
        upside = (analyst["target"] - price) / price
        a_score += min(max(upside, 0), 0.5) * 0.6  # upside component
    a_score += analyst["grade_score"] * 0.3  # grade component
    if analyst["eps_total"] > 0:
        beat_rate = analyst["eps_beats"] / analyst["eps_total"]
        a_score += beat_rate * 0.1
    a_weighted = min(a_score, 1.0) * 0.20

    composite = t_weighted + v_weighted + a_weighted

    # Catastrophe penalty
    penalty = 0
    reasons = []
    if value["altman_z"] > 0 and value["altman_z"] < 1.8:
        penalty += 0.10; reasons.append("⚠️ Altman Z < 1.8 (distress)")
    if value["piotroski"] <= 2:
        penalty += 0.05; reasons.append("⚠️ Piotroski ≤ 2")
    if tech["rsi"] > 85:
        penalty += 0.05; reasons.append("⚠️ RSI > 85 (extreme)")
    if analyst["eps_total"] >= 3 and analyst["eps_beats"] == 0:
        penalty += 0.05; reasons.append("⚠️ 0 EPS beats in 3+ quarters")

    composite = max(composite - penalty, 0)

    # Signal classification
    bull = tech["bull_score"]
    mos = value["margin_of_safety"]

    if composite > 0.60 and (mos > 0.10 or bull >= 7):
        signal = "BUY"
    elif composite > 0.50 and (mos > 0.05 or bull >= 5):
        signal = "WATCH"
    elif composite < 0.25 or bull <= 2:
        signal = "SELL"
    else:
        signal = "HOLD"

    return composite, signal, reasons

# ---------------------------------------------------------------------------
# 7. Main Screening Loop
# ---------------------------------------------------------------------------

def screen(symbols: list[str]) -> list[Stock]:
    results = []
    total = len(symbols)
    skips = {"quote": 0, "analyst": 0, "tech": 0}

    log.info(f"Starting v5 screen of {total} symbols")

    # Pre-fetch all quotes in batches of 10
    all_quotes = get_quotes_batch(symbols)

    for i, sym in enumerate(symbols):
        if (i + 1) % 10 == 0:
            log.info(f"  Progress: {i+1}/{total} (passed: {len(results)})")

        # Quote (from batch, fallback to single)
        q = all_quotes.get(sym)
        if not q:
            skips["quote"] += 1
            continue

        price = q["price"]

        # Analyst
        a = get_analyst(sym)
        if a["target"] > 0:
            a["upside"] = (a["target"] - price) / price * 100

        # Technicals
        t = get_technicals(sym, q)
        if not t:
            skips["tech"] += 1
            continue

        # Value (Buffett) — only for stocks that pass basic screening
        # Skip deep value analysis for stocks with no momentum AND no analyst interest
        if t["bull_score"] <= 1 and a["target"] <= 0:
            continue

        v = get_value(sym, price, q["currency"])

        # Composite
        composite, signal, penalty_reasons = compute_composite(t, a, v, price)

        s = Stock(
            symbol=sym, price=price, currency=q["currency"],
            sma50=q["sma50"], sma200=q["sma200"],
            year_high=q["year_high"], year_low=q["year_low"],
            market_cap=q["market_cap"], volume=q["volume"],
            rsi=t["rsi"], macd_signal=t["macd_signal"], adx=t["adx"],
            bb_pct=t["bb_pct"], stoch_rsi=t["stoch_rsi"], obv_trend=t["obv_trend"],
            bull_score=t["bull_score"],
            target=a["target"], upside=a["upside"], grade_score=a["grade_score"],
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
            composite=composite, signal=signal,
            classification=v["classification"],
            reasons=t.get("bull_reasons", []) + penalty_reasons,
        )
        results.append(s)

    results.sort(key=lambda x: x.composite, reverse=True)
    log.info(f"Screen complete: {len(results)} scored | Skipped: {skips}")
    return results

# ---------------------------------------------------------------------------
# 8. Report Formatting
# ---------------------------------------------------------------------------

def format_report(stocks: list[Stock], region: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"{'='*90}",
        f"  STOCK SCREENER v5 — {region.upper()} — {now}",
        f"  Methodology: 50% Buffett Value + 30% Technical + 20% Analyst",
        f"{'='*90}\n",
    ]

    # Group by signal
    for signal_group in ["BUY", "WATCH", "HOLD", "SELL"]:
        group = [s for s in stocks if s.signal == signal_group]
        if not group:
            continue
        emoji = {"BUY": "🟢", "WATCH": "🟠", "HOLD": "🟡", "SELL": "🔴"}[signal_group]
        lines.append(f"  {emoji} {signal_group} ({len(group)} stocks)")
        lines.append(f"  {'─'*85}")

        for s in group[:TOP_N]:
            lines.append(f"\n  {s.symbol:<12} {s.currency} {s.price:>8.2f}  │  Composite: {s.composite:.2f}  │  {s.classification}")
            lines.append(f"    Technical:  Bull {s.bull_score}/10  RSI {s.rsi:.0f}  MACD {s.macd_signal}  ADX {s.adx:.0f}")
            lines.append(f"    Value:      MoS {s.margin_of_safety:+.0%}  ROE {s.roe_avg:.0%}  GM {s.gross_margin:.0%}({s.gross_margin_trend})")
            lines.append(f"                Piotroski {s.piotroski}/9  Altman {s.altman_z:.1f}  RevCAGR {s.revenue_cagr_3y:.0%}  EPSCAGR {s.eps_cagr_3y:.0%}")

            iv_str = f"DCF ${s.dcf_value:.0f}" if s.dcf_value else "N/A"
            buf_str = f"Buffett ${s.intrinsic_buffett:.0f}" if s.intrinsic_buffett else "N/A"
            oe_str = f"OE Yield {s.owner_earnings_yield:.1%}" if s.owner_earnings_yield else "N/A"
            lines.append(f"                Intrinsic: {iv_str} | {buf_str} | {oe_str}")

            lines.append(f"    Analyst:    Target ${s.target:.0f} ({s.upside:+.1f}%)  Grades {s.grade_buy}/{s.grade_total} buy  EPS {s.eps_beats}/{s.eps_total} beats")
            if s.reasons:
                lines.append(f"    Signals:    {', '.join(s.reasons[:8])}")
        lines.append("")

    # Summary stats
    buy_count = sum(1 for s in stocks if s.signal == "BUY")
    watch_count = sum(1 for s in stocks if s.signal == "WATCH")
    lines.append(f"  SUMMARY: {len(stocks)} screened → {buy_count} BUY, {watch_count} WATCH")
    lines.append(f"  Top value:     {stocks[0].symbol if stocks else 'none'} (composite {stocks[0].composite:.2f})" if stocks else "")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 9. Email
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
# 10. Signal History
# ---------------------------------------------------------------------------

def load_signals() -> dict:
    try:
        with open(SIGNAL_LOG) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")

def gcs_upload(path: str, data: dict):
    """Upload JSON to GCS using default service account (works on Cloud Run)."""
    try:
        # Get access token from metadata server
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
        log.warning(f"GCS: {e}")  # non-fatal, scan still works without GCS

def save_scan_to_gcs(stocks: list, region: str):
    """Save full scan results to GCS for dashboard consumption."""
    today = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "scan_date": datetime.now().isoformat(),
        "region": region,
        "version": "v5",
        "summary": {
            "total": len(stocks),
            "buy": sum(1 for s in stocks if s.signal == "BUY"),
            "watch": sum(1 for s in stocks if s.signal == "WATCH"),
            "hold": sum(1 for s in stocks if s.signal == "HOLD"),
            "sell": sum(1 for s in stocks if s.signal == "SELL"),
        },
        "stocks": [asdict(s) for s in stocks],
    }
    # Write latest (dashboard reads this)
    gcs_upload("scans/latest.json", payload)
    # Write daily archive
    gcs_upload(f"scans/{today}.json", payload)

def save_signals(data: dict):
    with open(SIGNAL_LOG, "w") as f:
        json.dump(data, f, indent=2)

def update_signal_history(stocks: list[Stock]):
    history = load_signals()
    today = datetime.now().strftime("%Y-%m-%d")
    daily_signals = {}
    for s in stocks:
        key = s.symbol
        if key not in history:
            history[key] = {"entries": []}
        entry = {
            "date": today, "price": s.price, "signal": s.signal,
            "composite": round(s.composite, 3), "bull": s.bull_score,
            "mos": round(s.margin_of_safety, 3),
        }
        history[key]["entries"].append(entry)
        # Keep last 60 entries
        history[key]["entries"] = history[key]["entries"][-60:]
        daily_signals[key] = entry
    save_signals(history)
    # Persist daily signals to GCS for tracking entry prices over time
    gcs_upload(f"signals/{today}.json", daily_signals)

# ---------------------------------------------------------------------------
# 11. Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stock Screener v5")
    parser.add_argument("--region", default=os.environ.get("SCREEN_INDEX", "nasdaq100"),
                        help="nasdaq100, sp500, europe, asia, global, or exchange code")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols (override region)")
    parser.add_argument("--top", type=int, default=TOP_N)
    parser.add_argument("--email", action="store_true")
    args = parser.parse_args()

    if not FMP_KEY:
        log.error("FMP_API_KEY not set!")
        sys.exit(1)

    # Get symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_symbols(args.region)

    if not symbols:
        log.error("No symbols to screen!")
        return "No symbols found."

    # Screen
    results = screen(symbols)

    # Report
    report = format_report(results[:args.top * 3], args.region)
    print(report)

    # Save signals
    update_signal_history(results)

    # Save to GCS for dashboard
    save_scan_to_gcs(results, args.region)

    # Email
    today = datetime.now().strftime("%Y-%m-%d")
    if args.email or SMTP_USER:
        send_email(f"Screener v5: {args.region.upper()} — {today}", report)

    return report

if __name__ == "__main__":
    main()
