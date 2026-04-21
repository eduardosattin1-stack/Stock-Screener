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
  composite   ≥ 0.85
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
COMPOSITE_THRESHOLD = 0.85
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
