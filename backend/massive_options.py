#!/usr/bin/env python3
"""
Massive Options Module — Drop-in replacement for tradier_options.py
===================================================================

Uses Massive (formerly Polygon.io) Option Chain Snapshot API to fetch
Greeks, IV, open interest, bid/ask in a SINGLE call per symbol — replacing
the 3-6 Tradier calls that tradier_options.enrich_stock() required.

Public API is identical to tradier_options.py so screener_v6.py can swap
imports with zero changes to its calling code.

ENVIRONMENT
  MASSIVE_API_KEY    API key from https://massive.com/dashboard

STORAGE (GCS) — same paths as tradier_options for continuity:
  options/iv_history/{SYMBOL}.json    append-only IV rank history
  options/latest_suggestions.json     today's spread candidates
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import requests

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "").strip()
MASSIVE_BASE = "https://api.polygon.io"

GCS_BUCKET = "screener-signals-carbonbridge"
IV_HISTORY_PREFIX = "options/iv_history"
SUGGESTIONS_PATH = "options/latest_suggestions.json"

DTE_TARGET = 35
DTE_TOLERANCE = 999  # Relaxed to always match closest expiration
TARGET_LONG_PCT = 0.05
TARGET_SHORT_PCT = 0.20

IV_HISTORY_KEEP_DAYS = 90
MIN_IV_SAMPLES_FOR_RANK = 20


# ---------------------------------------------------------------------------
# HTTP — Massive REST
# ---------------------------------------------------------------------------
def _get(path: str, params: dict = None) -> Optional[dict]:
    if not MASSIVE_API_KEY:
        log.warning("MASSIVE_API_KEY not set — Massive calls disabled")
        return None
    p = dict(params or {})
    p["apiKey"] = MASSIVE_API_KEY
    try:
        r = requests.get(f"{MASSIVE_BASE}{path}", params=p, timeout=30)
        if r.status_code == 200:
            return r.json()
        log.warning(f"Massive {path} returned {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        log.warning(f"Massive {path} failed: {e}")
        return None


# ---------------------------------------------------------------------------
# GCS helpers (identical to tradier_options — shared pattern)
# ---------------------------------------------------------------------------
def _gcs_token() -> Optional[str]:
    try:
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=3,
        )
        return r.json().get("access_token") if r.status_code == 200 else None
    except Exception:
        return None


def _gcs_read(path: str, default):
    url = f"https://storage.googleapis.com/{GCS_BUCKET}/{path}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return default


def _gcs_write(path: str, data) -> bool:
    tok = _gcs_token()
    if not tok:
        return False
    try:
        r = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o",
            params={"uploadType": "media", "name": path},
            headers={"Authorization": f"Bearer {tok}",
                     "Content-Type": "application/json"},
            data=json.dumps(data, default=str), timeout=15,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core Massive endpoint: Option Chain Snapshot
# ---------------------------------------------------------------------------
def get_options_snapshot(symbol: str,
                         exp_gte: str = None,
                         exp_lte: str = None,
                         contract_type: str = None,
                         limit: int = 250) -> list:
    """Fetch option chain snapshot — returns list of contract dicts.

    Each result contains: details (strike, type, expiration), greeks,
    implied_volatility, open_interest, day (volume/OHLC), last_quote
    (bid/ask/midpoint), underlying_asset (price).
    
    This single endpoint replaces Tradier's get_quote + get_expirations +
    get_chain (3-6 calls) with ONE call.
    """
    params = {"limit": limit, "order": "asc", "sort": "expiration_date"}
    if exp_gte:
        params["expiration_date.gte"] = exp_gte
    if exp_lte:
        params["expiration_date.lte"] = exp_lte
    if contract_type:
        params["contract_type"] = contract_type

    all_results = []
    path = f"/v3/snapshot/options/{symbol.upper()}"
    
    data = _get(path, params)
    if not data:
        return []
    
    all_results.extend(data.get("results", []))
    
    # Paginate if needed (Massive uses cursor-based pagination)
    next_url = data.get("next_url")
    pages = 0
    while next_url and pages < 5:  # cap at 5 pages to avoid runaway
        pages += 1
        try:
            sep = "&" if "?" in next_url else "?"
            r = requests.get(f"{next_url}{sep}apiKey={MASSIVE_API_KEY}", timeout=15)
            if r.status_code != 200:
                break
            page = r.json()
            all_results.extend(page.get("results", []))
            next_url = page.get("next_url")
        except Exception:
            break

    return all_results


def get_spot_price(symbol: str) -> Optional[float]:
    """Get current stock price from Massive stocks snapshot."""
    data = _get(f"/v2/aggs/ticker/{symbol.upper()}/prev")
    if not data:
        return None
    results = data.get("results", [])
    if results and len(results) > 0:
        return results[0].get("c")  # close price
    return None


# ---------------------------------------------------------------------------
# Derived analytics from snapshot data
# ---------------------------------------------------------------------------
def _extract_atm_iv(contracts: list, spot: float) -> Optional[float]:
    """Average the IV of the nearest-ATM call and put."""
    if not contracts or spot <= 0:
        return None

    calls = [c for c in contracts if c.get("details", {}).get("contract_type") == "call"]
    puts = [c for c in contracts if c.get("details", {}).get("contract_type") == "put"]

    def _atm_iv(opts):
        if not opts:
            return None
        best = min(opts, key=lambda o: abs(float(o["details"]["strike_price"]) - spot))
        iv = best.get("implied_volatility")
        return float(iv) if iv and iv > 0 else None

    ivs = [v for v in (_atm_iv(calls), _atm_iv(puts)) if v is not None and v > 0]
    return sum(ivs) / len(ivs) if ivs else None


def _extract_skew_25d(contracts: list) -> Optional[float]:
    """Calculate 25-delta put IV minus 25-delta call IV."""
    if not contracts:
        return None

    calls = [c for c in contracts if c.get("details", {}).get("contract_type") == "call"]
    puts = [c for c in contracts if c.get("details", {}).get("contract_type") == "put"]

    def _find_25d_iv(opts, target_delta):
        with_delta = [
            o for o in opts 
            if o.get("greeks", {}).get("delta") is not None 
            and o.get("implied_volatility") is not None
        ]
        if not with_delta:
            return None
        best = min(with_delta, key=lambda o: abs(float(o["greeks"]["delta"]) - target_delta))
        return float(best["implied_volatility"])

    call_iv = _find_25d_iv(calls, 0.25)
    put_iv = _find_25d_iv(puts, -0.25)
    
    if call_iv is not None and put_iv is not None:
        return round(put_iv - call_iv, 4)
    return None


def _compute_pc_ratios(contracts: list) -> dict:
    """Put/Call ratios based on both volume AND open interest.
    
    OI-based ratio is more reliable for institutional positioning (new with Massive).
    """
    call_vol, put_vol = 0.0, 0.0
    call_oi, put_oi = 0.0, 0.0
    
    for c in contracts:
        ct = c.get("details", {}).get("contract_type", "")
        vol = (c.get("day", {}) or {}).get("volume", 0) or 0
        oi = c.get("open_interest", 0) or 0
        
        if ct == "call":
            call_vol += vol
            call_oi += oi
        elif ct == "put":
            put_vol += vol
            put_oi += oi

    pc_volume = round(put_vol / call_vol, 3) if call_vol > 0 else None
    pc_oi = round(put_oi / call_oi, 3) if call_oi > 0 else None
    total_oi = int(call_oi + put_oi)
    
    return {"pc_volume": pc_volume, "pc_oi": pc_oi, "total_oi": total_oi}


def _compute_implied_earnings_move(contracts: list, spot: float) -> Optional[dict]:
    """ATM straddle mid-price / spot → implied absolute % move."""
    if not contracts or spot <= 0:
        return None

    strikes = set()
    for c in contracts:
        s = c.get("details", {}).get("strike_price")
        if s:
            strikes.add(float(s))
    if not strikes:
        return None
    atm_strike = min(strikes, key=lambda k: abs(k - spot))

    atm_call = next((c for c in contracts
                     if c.get("details", {}).get("strike_price") == atm_strike
                     and c.get("details", {}).get("contract_type") == "call"), None)
    atm_put = next((c for c in contracts
                    if c.get("details", {}).get("strike_price") == atm_strike
                    and c.get("details", {}).get("contract_type") == "put"), None)
    if not atm_call or not atm_put:
        return None

    def _mid(c):
        q = c.get("last_quote") or {}
        mid = q.get("midpoint")
        if mid and mid > 0:
            return mid
        b, a = q.get("bid", 0) or 0, q.get("ask", 0) or 0
        if b > 0 and a > 0:
            return (b + a) / 2.0
        return (c.get("day", {}) or {}).get("close", 0) or 0

    call_mid = _mid(atm_call)
    put_mid = _mid(atm_put)
    straddle = call_mid + put_mid
    if straddle <= 0:
        return None

    return {
        "pct": round(straddle / spot * 100, 2),
        "call_mid": round(call_mid, 2),
        "put_mid": round(put_mid, 2),
        "straddle": round(straddle, 2),
        "strike": atm_strike,
    }


# ---------------------------------------------------------------------------
# Spread builder
# ---------------------------------------------------------------------------
def _pick_strikes_from_snapshot(contracts: list, spot: float) -> Optional[dict]:
    """Pick ~5% OTM long call and ~20% OTM short call."""
    calls = [c for c in contracts
             if c.get("details", {}).get("contract_type") == "call"
             and c.get("details", {}).get("strike_price")]
    if len(calls) < 2:
        return None

    long_target = spot * (1.0 + TARGET_LONG_PCT)
    short_target = spot * (1.0 + TARGET_SHORT_PCT)

    long_call = min(calls, key=lambda o: abs(float(o["details"]["strike_price"]) - long_target))
    short_call = min(calls, key=lambda o: abs(float(o["details"]["strike_price"]) - short_target))

    ls = float(long_call["details"]["strike_price"])
    ss = float(short_call["details"]["strike_price"])
    if ls >= ss:
        return None

    return {"long": long_call, "short": short_call}


def _spread_economics(long_call: dict, short_call: dict, spot: float) -> dict:
    """Compute net debit, max gain/loss, break-even, risk-reward."""
    def mid(c):
        q = c.get("last_quote") or {}
        m = q.get("midpoint")
        if m and m > 0:
            return m
        b, a = q.get("bid", 0) or 0, q.get("ask", 0) or 0
        if b > 0 and a > 0:
            return (b + a) / 2
        return (c.get("day", {}) or {}).get("close", 0) or 0

    long_mid = mid(long_call)
    short_mid = mid(short_call)
    net_debit = long_mid - short_mid
    long_strike = float(long_call["details"]["strike_price"])
    short_strike = float(short_call["details"]["strike_price"])
    width = short_strike - long_strike
    max_gain = width - net_debit if net_debit > 0 else 0
    max_loss = net_debit
    break_even = long_strike + net_debit
    rr = (max_gain / max_loss) if max_loss > 0 else 0
    return {
        "long_strike": long_strike,
        "short_strike": short_strike,
        "long_mid": round(long_mid, 2),
        "short_mid": round(short_mid, 2),
        "net_debit": round(net_debit, 2),
        "width": round(width, 2),
        "max_gain_per_contract": round(max_gain * 100, 2),
        "max_loss_per_contract": round(max_loss * 100, 2),
        "break_even_price": round(break_even, 2),
        "break_even_move_pct": round((break_even - spot) / spot * 100, 2) if spot > 0 else 0,
        "risk_reward": round(rr, 2),
        "long_greeks": long_call.get("greeks"),
        "short_greeks": short_call.get("greeks"),
        "long_iv": long_call.get("implied_volatility"),
        "short_iv": short_call.get("implied_volatility"),
    }


# ---------------------------------------------------------------------------
# Main enrichment — drop-in replacement for tradier_options.enrich_stock()
# ---------------------------------------------------------------------------
def enrich_stock(symbol: str, composite: float, hit_prob: float,
                 earnings_date: Optional[str] = None,
                 collect_term_structure: bool = True,
                 collect_earnings_move: bool = True,
                 target_dte: int = 35) -> dict:
    """
    Called by screener_v6.py for each US stock with market cap > $1B.
    Returns dict with same keys as tradier_options.enrich_stock():

        iv_current, iv_rank, iv_samples, spread, pc_ratio,
        iv_30d, iv_60d, iv_90d, term_structure, implied_earnings_move

    Plus new fields only available from Massive:
        pc_oi_ratio, total_open_interest

    Uses 1-2 Massive API calls total (vs 3-6 from Tradier).
    """
    result = {
        "iv_current": None,
        "skew_25d": None,
        "iv_rank": None,
        "iv_samples": 0,
        "spread": None,
        "pc_ratio": None,
        "pc_oi_ratio": None,          # NEW: OI-based P/C ratio
        "total_open_interest": None,   # NEW: aggregate OI
        "iv_30d": None,
        "iv_60d": None,
        "iv_90d": None,
        "term_structure": None,
        "implied_earnings_move": None,
    }

    if not MASSIVE_API_KEY:
        return result

    # Compute date windows for the snapshot query
    today = datetime.now().date()
    # Fetch contracts expiring 14-100 days out — covers spread DTE + term structure
    exp_gte = (today + timedelta(days=14)).strftime("%Y-%m-%d")
    # Fetch up to 100 days normally, but if target_dte is larger (e.g. 60), ensure exp_lte is large enough
    exp_lte = (today + timedelta(days=max(100, target_dte + 40))).strftime("%Y-%m-%d")

    # ONE call — replaces Tradier's quote + expirations + chain(s)
    try:
        contracts = get_options_snapshot(symbol, exp_gte=exp_gte, exp_lte=exp_lte)
    except Exception as e:
        log.debug(f"Massive snapshot failed for {symbol}: {e}")
        return result

    if not contracts:
        return result

    # Extract spot price from the snapshot's underlying_asset field
    spot = None
    for c in contracts:
        ua = c.get("underlying_asset") or {}
        p = ua.get("price")
        if p and p > 0:
            spot = float(p)
            break
    if not spot:
        spot = get_spot_price(symbol)
    if not spot or spot <= 0:
        return result

    # Group contracts by expiration for term structure analysis
    by_exp: dict[str, list] = {}
    for c in contracts:
        exp = c.get("details", {}).get("expiration_date", "")
        if exp:
            by_exp.setdefault(exp, []).append(c)

    expirations = sorted(by_exp.keys())
    if not expirations:
        return result

    # Pick the expiration closest to target_dte for spread building
    chosen_exp = None
    chosen_diff = 10**9
    for exp in expirations:
        try:
            d = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (d - today).days
            diff = abs(dte - target_dte)
            if diff < chosen_diff:
                chosen_diff = diff
                chosen_exp = exp
        except Exception:
            continue

    if chosen_exp and chosen_diff > DTE_TOLERANCE:
        chosen_exp = None

    # Use best available expiration for IV extraction
    iv_exp = chosen_exp or expirations[0]
    iv_chain = by_exp.get(iv_exp, [])

    # Step 1: ATM IV + skew
    iv_today = _extract_atm_iv(iv_chain, spot)
    result["skew_25d"] = _extract_skew_25d(iv_chain)
    
    if iv_today:
        result["iv_current"] = round(iv_today, 4)
        
    # See if Polygon provides implied_volatility_rank on the underlying asset
    for c in contracts:
        ua = c.get("underlying_asset", {})
        if "implied_volatility_rank" in ua:
            result["iv_rank"] = round(float(ua["implied_volatility_rank"]), 1)
            break

    # Step 2: P/C ratios (volume + OI) — uses ALL contracts, no extra call
    pc_data = _compute_pc_ratios(contracts)
    result["pc_ratio"] = pc_data["pc_volume"]
    result["pc_oi_ratio"] = pc_data["pc_oi"]
    result["total_open_interest"] = pc_data["total_oi"]

    # Step 3: Term structure — NO extra API calls (all data from snapshot)
    if collect_term_structure:
        targets = {"iv_30d": 30, "iv_60d": 60, "iv_90d": 90}
        for key, target_dte in targets.items():
            best_exp = None
            best_diff = 10**9
            for exp in expirations:
                try:
                    d = datetime.strptime(exp, "%Y-%m-%d").date()
                    dte = (d - today).days
                    diff = abs(dte - target_dte)
                    if diff < 20 and diff < best_diff:
                        best_diff = diff
                        best_exp = exp
                except Exception:
                    continue
            if best_exp:
                chain_for_exp = by_exp.get(best_exp, [])
                iv = _extract_atm_iv(chain_for_exp, spot)
                result[key] = round(iv, 4) if iv else None

        ivs = [v for v in (result["iv_30d"], result["iv_60d"], result["iv_90d"]) if v]
        if len(ivs) >= 2:
            front = result["iv_30d"] or result["iv_60d"]
            back = result["iv_90d"] or result["iv_60d"]
            if front and back:
                spread_pct = (front - back) / back * 100
                if spread_pct > 5:
                    result["term_structure"] = "backwardation"
                elif spread_pct < -5:
                    result["term_structure"] = "contango"
                else:
                    result["term_structure"] = "flat"

    # Step 4: Implied earnings move
    if collect_earnings_move and earnings_date:
        try:
            earn_dt = datetime.strptime(earnings_date[:10], "%Y-%m-%d").date()
            # Find first expiration >= earnings date
            earn_exp = None
            for exp in expirations:
                try:
                    if datetime.strptime(exp, "%Y-%m-%d").date() >= earn_dt:
                        earn_exp = exp
                        break
                except Exception:
                    continue
            if earn_exp and earn_exp in by_exp:
                iem = _compute_implied_earnings_move(by_exp[earn_exp], spot)
                if iem:
                    iem["expiration"] = earn_exp
                    iem["earnings_date"] = earnings_date[:10]
                    result["implied_earnings_move"] = iem
        except Exception as e:
            log.debug(f"Massive earnings-move failed for {symbol}: {e}")

    # Step 5: Build spread
    spread_exp = chosen_exp
    if not spread_exp:
        spread_exp = iv_exp  # fallback

    spread_chain = by_exp.get(spread_exp, [])
    if spread_chain:
        strikes = _pick_strikes_from_snapshot(spread_chain, spot)
        if strikes:
            econ = _spread_economics(strikes["long"], strikes["short"], spot)
            dte = (datetime.strptime(spread_exp, "%Y-%m-%d").date() - today).days

            result["spread"] = {
                "strategy": "Bull call spread",
                "spot": round(spot, 2),
                "expiration": spread_exp,
                "dte": dte,
                "long_strike": econ["long_strike"],
                "short_strike": econ["short_strike"],
                "long_mid": econ["long_mid"],
                "short_mid": econ["short_mid"],
                "net_debit": econ["net_debit"],
                "max_gain_per_contract": econ["max_gain_per_contract"],
                "max_loss_per_contract": econ["max_loss_per_contract"],
                "break_even_price": econ["break_even_price"],
                "break_even_move_pct": econ["break_even_move_pct"],
                "risk_reward": econ["risk_reward"],
                "long_greeks": econ.get("long_greeks"),
                "short_greeks": econ.get("short_greeks"),
                "long_iv": econ.get("long_iv"),
                "short_iv": econ.get("short_iv"),
                "description": (
                    f"Long {econ['long_strike']}C / Short {econ['short_strike']}C @ "
                    f"{spread_exp} — debit ${econ['net_debit']:.2f}, max gain "
                    f"${econ['max_gain_per_contract']:.0f}/contract "
                    f"({econ['risk_reward']:.1f}:1 R/R), "
                    f"break-even +{econ['break_even_move_pct']:.1f}%"
                ),
            }
            log.info(f"  {symbol}: spread BUILT — {econ['long_strike']}/"
                     f"{econ['short_strike']}C @ {spread_exp}")
        else:
            log.info(f"  {symbol}: spread skipped — strike selection failed")
    else:
        log.info(f"  {symbol}: spread skipped — no chain for {spread_exp}")

    return result


# ---------------------------------------------------------------------------
# Public entries — same interface as tradier_options
# ---------------------------------------------------------------------------
def build_spread_suggestion(symbol: str, composite: float, hit_prob: float) -> Optional[dict]:
    """Compatibility wrapper — calls enrich_stock and extracts spread."""
    data = enrich_stock(symbol, composite, hit_prob)
    sp = data.get("spread")
    if sp:
        sp["composite"] = round(composite, 3)
        sp["hit_prob"] = round(hit_prob, 3)
        sp["iv_rank"] = data.get("iv_rank")
        sp["iv_samples"] = data.get("iv_samples", 0)
        sp["iv_current"] = data.get("iv_current")
        sp["pc_oi_ratio"] = data.get("pc_oi_ratio")
        sp["skew_25d"] = data.get("skew_25d")
        sp["skipped"] = False
        sp["symbol"] = symbol
        return sp
    return {"symbol": symbol, "skipped": True, "reason": "no spread from snapshot"}


def suggest_spreads_for_portfolio(rebalance_report: dict) -> dict:
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not MASSIVE_API_KEY:
        return {"date": today_str, "suggestions": [], "gated": [],
                "error": "MASSIVE_API_KEY not configured — options layer disabled"}

    candidates = []
    for o in rebalance_report.get("opens", []):
        candidates.append({
            "symbol": o["symbol"],
            "composite": o.get("composite", 0),
            "hit_prob": o.get("hit_prob", 0),
            "source": "new_open",
        })

    suggestions, gated = [], []
    for c in candidates:
        s = build_spread_suggestion(c["symbol"], c["composite"], c["hit_prob"])
        if s and s.get("skipped"):
            gated.append(s)
        elif s:
            s["source"] = c["source"]
            suggestions.append(s)

    result = {
        "date": today_str,
        "suggestions": suggestions,
        "gated": gated,
        "total_candidates": len(candidates),
    }
    _gcs_write(SUGGESTIONS_PATH, result)
    return result


def suggest_spreads_for_symbols(symbols_with_context: list) -> dict:
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not MASSIVE_API_KEY:
        return {"date": today_str, "suggestions": [], "gated": [],
                "error": "MASSIVE_API_KEY not configured"}

    suggestions, gated = [], []
    for c in symbols_with_context:
        s = build_spread_suggestion(c["symbol"], c.get("composite", 0),
                                    c.get("hit_prob", 0))
        if s and s.get("skipped"):
            gated.append(s)
        elif s:
            suggestions.append(s)

    return {
        "date": today_str,
        "suggestions": suggestions,
        "gated": gated,
        "total_candidates": len(symbols_with_context),
    }


def read_latest_suggestions() -> dict:
    return _gcs_read(SUGGESTIONS_PATH, {"date": None, "suggestions": [], "gated": []})
