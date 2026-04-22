#!/usr/bin/env python3
"""
Tradier Options Module — CB Screener v7.2 Phase 2 scaffolding
==============================================================

Fetches option chains from Tradier (free sandbox tier — ORATS-sourced Greeks
and IV per Tradier docs). Builds bull call spread suggestions for high-
composite picks, maintains 60-day IV history in GCS for IV-rank computation.

This module is SCAFFOLDING — it produces suggestions, it does NOT execute.
Output lands in the weekly email under "Options overlay candidates" with
explicit "speculative / not validated" labels. Accumulate data through
July 2026 review, then decide whether this layer has edge.

ENVIRONMENT
  TRADIER_TOKEN      API token from https://web.tradier.com/user/api
  TRADIER_SANDBOX    set to "1" to use sandbox (delayed quotes, free). Default: production.

STORAGE (GCS)
  options/iv_history/{SYMBOL}.json    append-only (date, iv_30d_avg) for IV rank
  options/latest_suggestions.json     today's list of candidate spreads

PHASE 2 ENTRY GATES (applied before suggesting a spread):
  composite   ≥ 0.60
  hit_prob    ≥ 0.65  (p10 from ML model)
  IV rank     ≤ 40    (only enter when premium is cheap relative to 60d history)
  position    already open in cash equity (spread = overlay, not standalone)

SPREAD CONSTRUCTION:
  Long call at strike ≈ spot × 1.00 (nearest ATM)
  Short call at strike ≈ spot × 1.10 (matches backtested TP)
  Expiration: closest to 90 days out (leaves buffer beyond 60d model horizon)
  Size: 1-2% of portfolio per spread, max 5% total in options overlay

Tradier API docs: https://docs.tradier.com/
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
TRADIER_TOKEN = os.environ.get("TRADIER_TOKEN", "")
TRADIER_SANDBOX = os.environ.get("TRADIER_SANDBOX", "0") == "1"
TRADIER_BASE = ("https://sandbox.tradier.com/v1" if TRADIER_SANDBOX
                else "https://api.tradier.com/v1")

GCS_BUCKET = "screener-signals-carbonbridge"
IV_HISTORY_PREFIX = "options/iv_history"
SUGGESTIONS_PATH = "options/latest_suggestions.json"

# Phase 2 entry gates — tune carefully with live data
COMPOSITE_THRESHOLD = 0.60  # Lowered 2026-04-21 from 0.85 — wider overlay universe,
                            # relies on hit_prob + IV rank as primary filters.
                            # Reassess in July 2026 with live data.
HIT_PROB_THRESHOLD = 0.65
IV_RANK_MAX = 40        # only enter when IV is in bottom 40% of 60-day range
DTE_TARGET = 90         # days to expiration — matches backtest horizon + buffer
DTE_TOLERANCE = 25      # accept expirations within target ± 25 days
TARGET_UPSIDE_PCT = 0.10  # short leg at spot × (1 + this)

# IV history
IV_HISTORY_KEEP_DAYS = 90
MIN_IV_SAMPLES_FOR_RANK = 20  # below this, IV rank is unreliable


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _headers() -> dict:
    return {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json",
    }


def _get(path: str, params: dict) -> Optional[dict]:
    if not TRADIER_TOKEN:
        log.warning("TRADIER_TOKEN not set — Tradier calls disabled")
        return None
    try:
        r = requests.get(f"{TRADIER_BASE}/{path}", params=params,
                         headers=_headers(), timeout=10)
        if r.status_code == 200:
            return r.json()
        log.warning(f"Tradier {path} returned {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        log.warning(f"Tradier {path} failed: {e}")
        return None


# ---------------------------------------------------------------------------
# GCS helpers (same pattern as rebalance_engine / signal_tracker)
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
# Tradier endpoints
# ---------------------------------------------------------------------------
def get_expirations(symbol: str) -> list:
    """Return list of expiration date strings (YYYY-MM-DD)."""
    data = _get("markets/options/expirations",
                {"symbol": symbol, "includeAllRoots": "false", "strikes": "false"})
    if not data:
        return []
    exps = data.get("expirations", {})
    if not exps:
        return []
    dates = exps.get("date", [])
    if isinstance(dates, str):
        dates = [dates]
    return dates or []


def get_chain(symbol: str, expiration: str) -> list:
    """Return list of option contract dicts with Greeks + IV (if available)."""
    data = _get("markets/options/chains",
                {"symbol": symbol, "expiration": expiration, "greeks": "true"})
    if not data:
        return []
    options = data.get("options", {})
    if not options:
        return []
    chain = options.get("option", [])
    if isinstance(chain, dict):
        chain = [chain]
    return chain or []


def get_quote(symbol: str) -> Optional[dict]:
    """Return dict with last/bid/ask or None."""
    data = _get("markets/quotes", {"symbols": symbol, "greeks": "false"})
    if not data:
        return None
    q = data.get("quotes", {}).get("quote")
    if isinstance(q, list):
        q = q[0] if q else None
    return q


# ---------------------------------------------------------------------------
# IV history + IV rank
# ---------------------------------------------------------------------------
def _extract_atm_iv(chain: list, spot: float) -> Optional[float]:
    """Pull 30-day IV for the nearest-ATM call contract. Tradier's chain includes
    per-contract greeks including mid_iv. We average the ATM call and ATM put IV
    to get a stable single number per day."""
    if not chain or spot <= 0:
        return None

    calls = [o for o in chain if o.get("option_type") == "call"]
    puts = [o for o in chain if o.get("option_type") == "put"]

    def _atm(opts):
        if not opts:
            return None
        best = min(opts, key=lambda o: abs(float(o.get("strike", 0)) - spot))
        g = best.get("greeks") or {}
        iv = g.get("mid_iv") or g.get("bid_iv") or g.get("ask_iv")
        try:
            return float(iv) if iv else None
        except (ValueError, TypeError):
            return None

    atm_call_iv = _atm(calls)
    atm_put_iv = _atm(puts)

    ivs = [v for v in (atm_call_iv, atm_put_iv) if v is not None and v > 0]
    if not ivs:
        return None
    return sum(ivs) / len(ivs)


def update_iv_history(symbol: str, iv: float, today_str: Optional[str] = None) -> bool:
    """Append today's IV to symbol's history. Trim beyond 90 days."""
    if iv is None or iv <= 0:
        return False
    today_str = today_str or datetime.now().strftime("%Y-%m-%d")
    path = f"{IV_HISTORY_PREFIX}/{symbol.upper()}.json"
    history = _gcs_read(path, [])
    if not isinstance(history, list):
        history = []

    # Dedup: replace today's entry if it exists
    today_idx = next((i for i, row in enumerate(history)
                      if isinstance(row, list) and len(row) >= 1 and row[0] == today_str), -1)
    new_row = [today_str, round(iv, 4)]
    if today_idx >= 0:
        history[today_idx] = new_row
    else:
        history.append(new_row)

    # Trim
    cutoff = (datetime.now() - timedelta(days=IV_HISTORY_KEEP_DAYS)).strftime("%Y-%m-%d")
    history = [row for row in history
               if isinstance(row, list) and len(row) >= 1 and row[0] >= cutoff]

    return _gcs_write(path, history)


def compute_iv_rank(symbol: str) -> Optional[dict]:
    """IV rank = (current_iv - 60d_min) / (60d_max - 60d_min) × 100.

    Returns dict with iv_rank, current_iv, iv_min, iv_max, samples, or None
    if insufficient history.
    """
    path = f"{IV_HISTORY_PREFIX}/{symbol.upper()}.json"
    history = _gcs_read(path, [])
    if not isinstance(history, list) or len(history) < MIN_IV_SAMPLES_FOR_RANK:
        return None

    ivs = [float(row[1]) for row in history
           if isinstance(row, list) and len(row) >= 2 and row[1]]
    if len(ivs) < MIN_IV_SAMPLES_FOR_RANK:
        return None

    current = ivs[-1]
    lo, hi = min(ivs), max(ivs)
    if hi == lo:
        return {"iv_rank": 50.0, "current_iv": current, "iv_min": lo, "iv_max": hi, "samples": len(ivs)}

    rank = (current - lo) / (hi - lo) * 100.0
    return {
        "iv_rank": round(rank, 1),
        "current_iv": round(current, 4),
        "iv_min": round(lo, 4),
        "iv_max": round(hi, 4),
        "samples": len(ivs),
    }


# ---------------------------------------------------------------------------
# v7.2.3 Apr 22 — additional Tradier signals: PC ratio, term structure, earnings move
# ---------------------------------------------------------------------------
def _compute_pc_volume_ratio(chain: list) -> Optional[float]:
    """Total put volume / total call volume across the full chain.

    Interpretation:
      < 0.5  : heavy call buying, bullish speculation
      0.5-1.0: normal bullish / neutral
      1.0-1.5: mild put buying, hedging or light bearishness
      1.5-2.5: elevated put buying, fear or hedging
      > 2.5  : extreme fear / heavy hedging

    Returns None if no volume recorded.
    """
    call_vol = 0.0
    put_vol = 0.0
    for c in chain:
        v = c.get("volume") or 0
        if not v or v <= 0:
            continue
        opt_type = (c.get("option_type") or "").lower()
        if opt_type == "call":
            call_vol += v
        elif opt_type == "put":
            put_vol += v
    if call_vol <= 0:
        return None
    return round(put_vol / call_vol, 3)


def _pick_term_structure_expirations(expirations: list) -> dict:
    """Given sorted list of expiration date strings, return closest to 30d/60d/90d.
    Returns {'exp_30d': '2026-05-22', 'exp_60d': ..., 'exp_90d': ...} — each None if no match.
    """
    today = datetime.now().date()
    result = {"exp_30d": None, "exp_60d": None, "exp_90d": None}
    if not expirations:
        return result

    # Parse to (date, str) pairs with DTE
    parsed = []
    for e in expirations:
        try:
            d = datetime.strptime(e, "%Y-%m-%d").date()
            dte = (d - today).days
            if dte >= 5:  # avoid same-week expirations
                parsed.append((dte, e))
        except Exception:
            continue
    if not parsed:
        return result

    # Find closest to each target DTE
    for target, key in [(30, "exp_30d"), (60, "exp_60d"), (90, "exp_90d")]:
        best = min(parsed, key=lambda p: abs(p[0] - target))
        # Only use if within ±20 days of target (avoid assigning a 7-day as the 30d slot)
        if abs(best[0] - target) <= 20:
            result[key] = best[1]
    return result


def _compute_implied_earnings_move(chain: list, spot: float) -> Optional[dict]:
    """ATM straddle mid-price / spot → implied absolute % move.

    Input: chain from the FIRST post-earnings expiration.
    Output: {'pct': 4.5, 'call_mid': 6.20, 'put_mid': 5.80, 'straddle': 12.00}
    None if no ATM contracts or missing prices.
    """
    if not chain or spot <= 0:
        return None

    # Find ATM strike (closest to spot)
    strikes = set()
    for c in chain:
        s = c.get("strike")
        if s:
            strikes.add(float(s))
    if not strikes:
        return None
    atm_strike = min(strikes, key=lambda k: abs(k - spot))

    # Find ATM call + ATM put
    atm_call = next((c for c in chain
                     if c.get("strike") == atm_strike
                     and (c.get("option_type") or "").lower() == "call"), None)
    atm_put = next((c for c in chain
                    if c.get("strike") == atm_strike
                    and (c.get("option_type") or "").lower() == "put"), None)
    if not atm_call or not atm_put:
        return None

    def _mid(c):
        b, a = c.get("bid") or 0, c.get("ask") or 0
        if b > 0 and a > 0:
            return (b + a) / 2.0
        return c.get("last") or 0

    call_mid = _mid(atm_call)
    put_mid = _mid(atm_put)
    straddle = call_mid + put_mid
    if straddle <= 0:
        return None

    return {
        "pct": round(straddle / spot * 100, 2),  # implied absolute % move
        "call_mid": round(call_mid, 2),
        "put_mid": round(put_mid, 2),
        "straddle": round(straddle, 2),
        "strike": atm_strike,
    }


def _find_post_earnings_expiration(expirations: list, earnings_date_str: str) -> Optional[str]:
    """First expiration >= earnings date (so the straddle prices the actual event)."""
    try:
        earnings_dt = datetime.strptime(earnings_date_str[:10], "%Y-%m-%d").date()
    except Exception:
        return None
    for e in expirations:
        try:
            exp_dt = datetime.strptime(e, "%Y-%m-%d").date()
            if exp_dt >= earnings_dt:
                return e
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Bull call spread builder
# ---------------------------------------------------------------------------
def _pick_expiration(expirations: list, target_days: int = DTE_TARGET) -> Optional[str]:
    """Pick the expiration closest to target_days from today."""
    today = datetime.now().date()
    best = None
    best_diff = 10**9
    for exp in expirations:
        try:
            d = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        dte = (d - today).days
        if dte < 30:  # reject too-short — weeklies and such
            continue
        diff = abs(dte - target_days)
        if diff < best_diff:
            best_diff = diff
            best = exp
    if best_diff > DTE_TOLERANCE:
        return None
    return best


def _pick_strikes(chain: list, spot: float) -> Optional[dict]:
    """Pick ATM long call and ~10% OTM short call from the chain."""
    calls = [o for o in chain
             if o.get("option_type") == "call" and o.get("strike")]
    if len(calls) < 2:
        return None

    long_target = spot * 1.0
    short_target = spot * (1.0 + TARGET_UPSIDE_PCT)

    long_call = min(calls, key=lambda o: abs(float(o["strike"]) - long_target))
    short_call = min(calls, key=lambda o: abs(float(o["strike"]) - short_target))

    if float(long_call["strike"]) >= float(short_call["strike"]):
        return None  # strikes didn't separate — reject

    return {"long": long_call, "short": short_call}


def _spread_economics(long_call: dict, short_call: dict, spot: float) -> dict:
    """Compute net debit, max gain, max loss, break-even, risk-reward."""
    def mid(o):
        bid, ask = float(o.get("bid", 0) or 0), float(o.get("ask", 0) or 0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return float(o.get("last", 0) or 0)

    long_mid = mid(long_call)
    short_mid = mid(short_call)
    net_debit = long_mid - short_mid
    long_strike = float(long_call["strike"])
    short_strike = float(short_call["strike"])
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
        "max_gain_per_contract": round(max_gain * 100, 2),   # ×100 shares/contract
        "max_loss_per_contract": round(max_loss * 100, 2),
        "break_even_price": round(break_even, 2),
        "break_even_move_pct": round((break_even - spot) / spot * 100, 2) if spot > 0 else 0,
        "risk_reward": round(rr, 2),
    }


def build_spread_suggestion(symbol: str, composite: float, hit_prob: float) -> Optional[dict]:
    """Fetch chain, build bull call spread, return suggestion dict or None."""
    # Gate 1: composite + hit_prob
    if composite < COMPOSITE_THRESHOLD or hit_prob < HIT_PROB_THRESHOLD:
        return {"symbol": symbol, "skipped": True,
                "reason": f"gates not met (composite={composite:.2f}, p10={hit_prob:.2f})"}

    # Current spot
    quote = get_quote(symbol)
    if not quote or not quote.get("last"):
        return {"symbol": symbol, "skipped": True, "reason": "no Tradier quote"}
    spot = float(quote["last"])

    # Expirations → pick DTE target
    expirations = get_expirations(symbol)
    if not expirations:
        return {"symbol": symbol, "skipped": True, "reason": "no expirations available"}
    chosen_exp = _pick_expiration(expirations)
    if not chosen_exp:
        return {"symbol": symbol, "skipped": True,
                "reason": f"no expiration near {DTE_TARGET}±{DTE_TOLERANCE}d"}

    # Chain
    chain = get_chain(symbol, chosen_exp)
    if not chain:
        return {"symbol": symbol, "skipped": True, "reason": "empty chain"}

    # IV history update + rank
    iv_today = _extract_atm_iv(chain, spot)
    if iv_today:
        update_iv_history(symbol, iv_today)

    iv_data = compute_iv_rank(symbol)
    iv_rank = iv_data["iv_rank"] if iv_data else None

    # Gate 2: IV rank (only if we have enough history)
    if iv_data and iv_rank is not None and iv_rank > IV_RANK_MAX:
        return {
            "symbol": symbol, "skipped": True,
            "reason": f"IV rank too high ({iv_rank:.0f} > {IV_RANK_MAX})",
            "iv_data": iv_data,
        }

    # Build spread
    strikes = _pick_strikes(chain, spot)
    if not strikes:
        return {"symbol": symbol, "skipped": True, "reason": "strike selection failed"}

    econ = _spread_economics(strikes["long"], strikes["short"], spot)
    today = datetime.now().date()
    dte = (datetime.strptime(chosen_exp, "%Y-%m-%d").date() - today).days

    return {
        "symbol": symbol,
        "skipped": False,
        "strategy": "Bull call spread",
        "spot": round(spot, 2),
        "expiration": chosen_exp,
        "dte": dte,
        "composite": round(composite, 3),
        "hit_prob": round(hit_prob, 3),
        "iv_rank": iv_rank,
        "iv_samples": iv_data["samples"] if iv_data else 0,
        "iv_current": iv_data["current_iv"] if iv_data else None,
        "economics": econ,
        "description": (
            f"Long {strikes['long']['strike']}C / Short {strikes['short']['strike']}C @ "
            f"{chosen_exp} — debit ${econ['net_debit']:.2f}, max gain "
            f"${econ['max_gain_per_contract']:.0f}/contract ({econ['risk_reward']:.1f}:1 R/R), "
            f"break-even +{econ['break_even_move_pct']:.1f}%"
        ),
    }


# ---------------------------------------------------------------------------
# Screener enrichment — called for every US stock with mkt cap > $1B
# ---------------------------------------------------------------------------
def enrich_stock(symbol: str, composite: float, hit_prob: float,
                 earnings_date: Optional[str] = None,
                 collect_term_structure: bool = True,
                 collect_earnings_move: bool = True) -> dict:
    """
    Called by screener_v6.py for each US stock with market cap > $1B.
    Returns dict merged into stock's scan JSON:

        {
          "iv_current": 0.38 | None,              # ATM 30-day IV (decimal)
          "iv_rank": 42.0 | None,                 # 0-100, None if <20 samples
          "iv_samples": 25,                       # days of IV history
          "spread": {...} | None,                 # full spread suggestion
          "pc_ratio": 0.72 | None,                # put/call volume ratio (all contracts)
          "iv_30d": 0.35 | None,                  # ATM IV at ~30 DTE
          "iv_60d": 0.32 | None,                  # ATM IV at ~60 DTE
          "iv_90d": 0.30 | None,                  # ATM IV at ~90 DTE
          "term_structure": "backwardation"|"contango"|"flat"|None,
          "implied_earnings_move": {...} | None,  # ATM straddle around earnings
        }

    API cost per stock:
      - Base IV + spread:           3 calls (quote + expirations + one chain)
      - Term structure:             +2 chain calls (60d, 90d if different from 30d)
      - Implied earnings move:      +1 chain call (only if earnings_date within 60d)
    Total: 3-6 calls per stock.

    Always updates IV history (one sample per call per symbol per day).
    """
    result = {
        "iv_current": None,
        "iv_rank": None,
        "iv_samples": 0,
        "spread": None,
        "pc_ratio": None,
        "iv_30d": None,
        "iv_60d": None,
        "iv_90d": None,
        "term_structure": None,
        "implied_earnings_move": None,
    }

    if not TRADIER_TOKEN:
        return result

    # Step 1: Get spot from Tradier quote. If Tradier has no data for this
    # symbol (illiquid, OTC, foreign listing), return empty and move on.
    try:
        quote = get_quote(symbol)
    except Exception as e:
        log.debug(f"Tradier quote failed for {symbol}: {e}")
        return result
    if not quote or not quote.get("last"):
        return result
    spot = float(quote["last"])
    if spot <= 0:
        return result

    # Step 2: Get expirations. Pick the ~90-DTE one we'll use for the chain.
    try:
        expirations = get_expirations(symbol)
    except Exception as e:
        log.debug(f"Tradier expirations failed for {symbol}: {e}")
        return result
    if not expirations:
        return result
    chosen_exp = _pick_expiration(expirations)

    # If no suitable expiration (~90 DTE window), we can't build a spread.
    # But we can still fetch a nearer-dated chain to pull IV for the IV rank.
    iv_exp = chosen_exp
    if not iv_exp:
        # Fall back to the nearest future expiration that's >= 30 DTE
        today = datetime.now().date()
        valid = []
        for exp in expirations:
            try:
                d = datetime.strptime(exp, "%Y-%m-%d").date()
                if (d - today).days >= 30:
                    valid.append((exp, (d - today).days))
            except Exception:
                continue
        if valid:
            valid.sort(key=lambda x: x[1])
            iv_exp = valid[0][0]

    if not iv_exp:
        return result  # no usable expiration at all

    # Step 3: Get chain (with Greeks/IV)
    try:
        chain = get_chain(symbol, iv_exp)
    except Exception as e:
        log.debug(f"Tradier chain failed for {symbol}: {e}")
        return result
    if not chain:
        return result

    # Step 4: Extract ATM IV, update rolling history, compute IV rank
    iv_today = _extract_atm_iv(chain, spot)
    if iv_today:
        try:
            update_iv_history(symbol, iv_today)
        except Exception as e:
            log.debug(f"IV history write failed for {symbol}: {e}")

    iv_data = compute_iv_rank(symbol)
    if iv_data:
        result["iv_current"] = iv_data["current_iv"]
        result["iv_rank"] = iv_data["iv_rank"]
        result["iv_samples"] = iv_data["samples"]
    elif iv_today:
        result["iv_current"] = round(iv_today, 4)
        try:
            path = f"{IV_HISTORY_PREFIX}/{symbol.upper()}.json"
            history = _gcs_read(path, [])
            result["iv_samples"] = len(history) if isinstance(history, list) else 0
        except Exception:
            result["iv_samples"] = 1

    # Step 5: Put/call volume ratio — FREE (uses chain already fetched)
    result["pc_ratio"] = _compute_pc_volume_ratio(chain)

    # Step 6: IV term structure — 2 extra chain calls (30d / 60d / 90d)
    # Store iv_30d from the chain we already have (if it's in the 30d bucket)
    if collect_term_structure:
        term_exps = _pick_term_structure_expirations(expirations)

        def _get_atm_iv_for_exp(exp: Optional[str]) -> Optional[float]:
            """Fetch chain for exp (unless it's the one we already have) and extract ATM IV."""
            if not exp:
                return None
            if exp == iv_exp:
                return round(iv_today, 4) if iv_today else None
            try:
                c = get_chain(symbol, exp)
                v = _extract_atm_iv(c, spot) if c else None
                return round(v, 4) if v else None
            except Exception as e:
                log.debug(f"Tradier term-structure chain failed for {symbol} {exp}: {e}")
                return None

        result["iv_30d"] = _get_atm_iv_for_exp(term_exps.get("exp_30d"))
        result["iv_60d"] = _get_atm_iv_for_exp(term_exps.get("exp_60d"))
        result["iv_90d"] = _get_atm_iv_for_exp(term_exps.get("exp_90d"))

        # Classify the curve shape
        ivs = [v for v in (result["iv_30d"], result["iv_60d"], result["iv_90d"]) if v]
        if len(ivs) >= 2:
            front = result["iv_30d"] or result["iv_60d"]
            back = result["iv_90d"] or result["iv_60d"]
            if front and back:
                spread_pct = (front - back) / back * 100
                if spread_pct > 5:
                    result["term_structure"] = "backwardation"  # front > back (near-term event priced)
                elif spread_pct < -5:
                    result["term_structure"] = "contango"  # back > front (normal calm market)
                else:
                    result["term_structure"] = "flat"

    # Step 7: Implied earnings move — 1 extra chain call (only if earnings coming)
    if collect_earnings_move and earnings_date:
        earn_exp = _find_post_earnings_expiration(expirations, earnings_date)
        if earn_exp:
            try:
                # Reuse chain if possible
                if earn_exp == iv_exp:
                    earn_chain = chain
                else:
                    earn_chain = get_chain(symbol, earn_exp)
                if earn_chain:
                    iem = _compute_implied_earnings_move(earn_chain, spot)
                    if iem:
                        iem["expiration"] = earn_exp
                        iem["earnings_date"] = earnings_date[:10]
                        result["implied_earnings_move"] = iem
            except Exception as e:
                log.debug(f"Tradier earnings-move chain failed for {symbol}: {e}")

    # Step 8: Spread suggestion — only if gates pass and we have the ~90-DTE expiration
    if (chosen_exp is None
            or composite < COMPOSITE_THRESHOLD
            or hit_prob < HIT_PROB_THRESHOLD):
        return result

    # IV-rank gate only applies if we have enough samples
    if (result["iv_rank"] is not None
            and result["iv_samples"] >= MIN_IV_SAMPLES_FOR_RANK
            and result["iv_rank"] > IV_RANK_MAX):
        return result

    # If iv_exp != chosen_exp, we need the ~90-DTE chain for the spread
    if chosen_exp != iv_exp:
        try:
            chain = get_chain(symbol, chosen_exp)
        except Exception:
            return result
        if not chain:
            return result

    strikes = _pick_strikes(chain, spot)
    if not strikes:
        return result

    econ = _spread_economics(strikes["long"], strikes["short"], spot)
    today = datetime.now().date()
    dte = (datetime.strptime(chosen_exp, "%Y-%m-%d").date() - today).days

    result["spread"] = {
        "strategy": "Bull call spread",
        "spot": round(spot, 2),
        "expiration": chosen_exp,
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
        "description": (
            f"Long {strikes['long']['strike']}C / Short {strikes['short']['strike']}C @ "
            f"{chosen_exp} — debit ${econ['net_debit']:.2f}, max gain "
            f"${econ['max_gain_per_contract']:.0f}/contract ({econ['risk_reward']:.1f}:1 R/R), "
            f"break-even +{econ['break_even_move_pct']:.1f}%"
        ),
    }
    return result


# ---------------------------------------------------------------------------
# Public entry — called after rebalance_engine
# ---------------------------------------------------------------------------
def suggest_spreads_for_portfolio(rebalance_report: dict) -> dict:
    """Build option spread candidates for top picks (open positions + new opens).

    Returns dict: {date, suggestions: [...], gated: [...]} — gated entries show
    why we DIDN'T recommend a spread (useful for the email). All persisted to GCS.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")

    if not TRADIER_TOKEN:
        result = {"date": today_str, "suggestions": [], "gated": [],
                  "error": "TRADIER_TOKEN not configured — options layer disabled"}
        return result

    # Candidates: open positions (if composite high enough) + new entries
    candidates = []
    for o in rebalance_report.get("opens", []):
        candidates.append({
            "symbol": o["symbol"],
            "composite": o.get("composite", 0),
            "hit_prob": o.get("hit_prob", 0),
            "source": "new_open",
        })
    # Note: we don't add existing portfolio positions here because we lack their
    # current composite / p10. The scan stocks list would have that, but the
    # weekly report flow re-reads the latest scan separately and can cross-ref.

    suggestions = []
    gated = []
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
        "entry_gates": {
            "composite_min": COMPOSITE_THRESHOLD,
            "hit_prob_min": HIT_PROB_THRESHOLD,
            "iv_rank_max": IV_RANK_MAX,
            "dte_target": DTE_TARGET,
        },
    }
    _gcs_write(SUGGESTIONS_PATH, result)
    return result


def suggest_spreads_for_symbols(symbols_with_context: list) -> dict:
    """General-purpose entrypoint — takes [{symbol, composite, hit_prob}, ...]
    list and returns same result shape. Used if we want to run it against
    arbitrary picks (e.g. current portfolio holdings not just new opens).
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not TRADIER_TOKEN:
        return {"date": today_str, "suggestions": [], "gated": [],
                "error": "TRADIER_TOKEN not configured"}

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
    """For weekly report + frontend."""
    return _gcs_read(SUGGESTIONS_PATH, {"date": None, "suggestions": [], "gated": []})
