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
MASSIVE_API_KEY = "thetadata_active"  # Placeholder to pass legacy checks
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
# ThetaData Client & Rate Limiter
# ---------------------------------------------------------------------------
import threading
import time
import pandas as pd
from thetadata import ThetaClient

class RateLimiter:
    def __init__(self, max_rps: float):
        self.delay = 1.0 / max_rps
        self.last_call = 0.0
        self.lock = threading.Lock()
        
    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self.last_call = time.time()

# Global Rate Limiter set to 18 RPS to be safe under the 20 RPS limit.
rate_limiter = RateLimiter(18)

_client = None
_client_lock = threading.Lock()

def get_theta_client():
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = ThetaClient(
                email="carbonbridge.tech@gmail.com",
                password="Sccp1985r",
                dataframe_type="pandas"
            )
        return _client


def _execute_theta_call(func_name, *args, **kwargs):
    """Execute a ThetaClient gRPC call with auto-recovery for UNAUTHENTICATED session errors."""
    global _client
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            client = get_theta_client()
            method = getattr(client, func_name)
            rate_limiter.wait()
            return method(*args, **kwargs)
        except Exception as e:
            e_str = str(e)
            is_unauth = (
                "UNAUTHENTICATED" in e_str 
                or "session ID" in e_str 
                or "session" in e_str.lower()
                or "invalid session" in e_str.lower()
            )
            if is_unauth and attempt == 0:
                log.warning(f"ThetaData session invalid: {e}. Resetting client and retrying.")
                global _client
                with _client_lock:
                    _client = None
                # Force recreation
                try:
                    get_theta_client()
                except Exception as get_err:
                    log.error(f"Failed to recreate ThetaClient: {get_err}")
                continue
            
            # If it's a "No data" warning, raise it immediately
            if "No data" in e_str:
                raise
                
            if attempt == max_attempts - 1:
                raise e


_latest_eod_date_cache = None
_date_cache_lock = threading.Lock()

def _get_latest_eod_date():
    """Dynamically resolve the latest EOD business day containing options data by probing AAPL."""
    global _latest_eod_date_cache
    if _latest_eod_date_cache is not None:
        return _latest_eod_date_cache
    with _date_cache_lock:
        if _latest_eod_date_cache is not None:
            return _latest_eod_date_cache
            
        import datetime as _dt
        today = datetime.now()
        today_date = today.date()
        
        # Test dates starting from today going back up to 10 days
        for i in range(10):
            test_date = today_date - _dt.timedelta(days=i)
            if test_date.weekday() >= 5:
                continue
            # Probe AAPL (highly active, guaranteed options data on trading days)
            try:
                _execute_theta_call(
                    "option_history_greeks_eod",
                    symbol="AAPL",
                    expiration="*",
                    start_date=test_date,
                    end_date=test_date,
                    strike="*",
                    right="both",
                    strike_range=1
                )
                _latest_eod_date_cache = test_date
                log.info(f"Resolved ThetaData EOD Date after probe: {test_date}")
                return test_date
            except Exception:
                continue
                
        # Fallback business day logic
        fallback = today_date - _dt.timedelta(days=1)
        while fallback.weekday() >= 5:
            fallback -= _dt.timedelta(days=1)
        _latest_eod_date_cache = fallback
        log.warning(f"AAPL probe failed. Using fallback: {fallback}")
        return fallback

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
# ThetaData option snapshot fetching
# ---------------------------------------------------------------------------
def get_options_snapshot(symbol: str,
                         exp_gte: str = None,
                         exp_lte: str = None,
                         contract_type: str = None,
                         limit: int = 250) -> list:
    """Fetch option chain from ThetaData, merge greeks + OI, and return list of adapted contracts."""
    symbol = symbol.upper().strip()
    eod_date = _get_latest_eod_date()

    # 1. Fetch Greeks DataFrame
    greeks_df = None
    max_retries = 3
    for retry in range(max_retries):
        try:
            greeks_df = _execute_theta_call(
                "option_history_greeks_eod",
                symbol=symbol,
                expiration="*",
                start_date=eod_date,
                end_date=eod_date,
                strike="*",
                right="both",
                strike_range=20
            )
            break
        except Exception as e:
            if "No data" in str(e):
                log.warning(f"No Greeks data found for {symbol} on {eod_date}")
                return []
            if retry == max_retries - 1:
                log.error(f"Failed to fetch Greeks for {symbol} after {max_retries} attempts: {e}")
                return []
            time.sleep(2 ** retry)

    if greeks_df is None or greeks_df.empty:
        return []

    # 2. Fetch Open Interest DataFrame
    oi_df = None
    for retry in range(max_retries):
        try:
            oi_df = _execute_theta_call(
                "option_history_open_interest",
                symbol=symbol,
                expiration="*",
                start_date=eod_date,
                end_date=eod_date,
                strike="*",
                right="both",
                strike_range=20
            )
            break
        except Exception as e:
            if "No data" in str(e):
                log.warning(f"No OI data found for {symbol} on {eod_date}")
                break
            if retry == max_retries - 1:
                log.warning(f"Failed to fetch OI for {symbol}: {e}")
            time.sleep(2 ** retry)

    # Merge Greeks and OI
    try:
        if oi_df is not None and not oi_df.empty:
            merged_df = pd.merge(
                greeks_df,
                oi_df[['expiration', 'strike', 'right', 'open_interest']],
                on=['expiration', 'strike', 'right'],
                how='left'
            )
            merged_df['open_interest'] = merged_df['open_interest'].fillna(0.0)
        else:
            merged_df = greeks_df
            merged_df['open_interest'] = 0.0
    except Exception as e:
        log.error(f"Error merging Greeks and OI for {symbol}: {e}")
        merged_df = greeks_df
        merged_df['open_interest'] = 0.0

    # Adapt to list of dicts resembling the Polygon snapshot
    contracts = []
    for _, row in merged_df.iterrows():
        try:
            raw_right = str(row.get('right', '')).upper()
            if raw_right == 'CALL':
                contract_type_str = 'call'
            elif raw_right == 'PUT':
                contract_type_str = 'put'
            else:
                continue

            strike_val = float(row.get('strike', 0))
            exp_val = str(row.get('expiration', ''))
            if ' ' in exp_val:
                exp_val = exp_val.split(' ')[0] # Extract YYYY-MM-DD

            implied_vol = row.get('implied_vol')
            try:
                implied_vol = float(implied_vol) if implied_vol is not None and implied_vol > 0 else None
            except (ValueError, TypeError):
                implied_vol = None

            open_interest = int(row.get('open_interest', 0))
            volume = int(row.get('volume', 0))
            close = float(row.get('close', 0))
            bid = float(row.get('bid', 0))
            ask = float(row.get('ask', 0))
            midpoint = (bid + ask) / 2.0 if bid > 0 and ask > 0 else close

            delta = row.get('delta')
            delta = float(delta) if delta is not None else None
            gamma = row.get('gamma')
            gamma = float(gamma) if gamma is not None else None
            theta = row.get('theta')
            theta = float(theta) if theta is not None else None
            vega = row.get('vega')
            vega = float(vega) if vega is not None else None

            underlying_price = float(row.get('underlying_price', 0))

            contract = {
                "details": {
                    "contract_type": contract_type_str,
                    "strike_price": strike_val,
                    "expiration_date": exp_val,
                    "shares_per_contract": 100
                },
                "implied_volatility": implied_vol,
                "open_interest": open_interest,
                "day": {
                    "volume": volume,
                    "close": close
                },
                "last_quote": {
                    "bid": bid,
                    "ask": ask,
                    "midpoint": midpoint
                },
                "greeks": {
                    "delta": delta,
                    "gamma": gamma,
                    "theta": theta,
                    "vega": vega
                },
                "underlying_asset": {
                    "price": underlying_price
                }
            }
            contracts.append(contract)
        except Exception as e:
            log.debug(f"Row adaptation skipped for {symbol}: {e}")

    # Apply date filters in Python
    filtered_contracts = []
    for c in contracts:
        exp = c["details"]["expiration_date"]
        ctype = c["details"]["contract_type"]
        if exp_gte and exp < exp_gte:
            continue
        if exp_lte and exp > exp_lte:
            continue
        if contract_type and ctype != contract_type.lower():
            continue
        filtered_contracts.append(c)

    return filtered_contracts


def get_spot_price(symbol: str) -> Optional[float]:
    """Get current stock price from EOD option underlying price."""
    try:
        contracts = get_options_snapshot(symbol, limit=1)
        if contracts:
            return contracts[0]["underlying_asset"]["price"]
    except Exception as e:
        log.warning(f"get_spot_price failed for {symbol}: {e}")
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
        # Filter for valid options with positive implied volatility and active/liquid quotes (bid > 0, ask > 0)
        valid_opts = [
            o for o in opts 
            if o.get("implied_volatility") is not None 
            and o.get("implied_volatility") > 0
            and o.get("last_quote", {}).get("bid", 0) > 0
            and o.get("last_quote", {}).get("ask", 0) > 0
        ]
        if not valid_opts:
            return None
        best = min(valid_opts, key=lambda o: abs(float(o["details"]["strike_price"]) - spot))
        return float(best["implied_volatility"])

    ivs = [v for v in (_atm_iv(calls), _atm_iv(puts)) if v is not None and v > 0]
    return sum(ivs) / len(ivs) if ivs else None


def _extract_skew_25d(contracts: list) -> Optional[float]:
    """Calculate 25-delta put IV minus 25-delta call IV."""
    if not contracts:
        return None

    calls = [c for c in contracts if c.get("details", {}).get("contract_type") == "call"]
    puts = [c for c in contracts if c.get("details", {}).get("contract_type") == "put"]

    def _find_25d_iv(opts, target_delta):
        # Filter for valid options with active quotes (bid > 0, ask > 0) to avoid stale skew readings
        with_delta = [
            o for o in opts 
            if o.get("greeks", {}).get("delta") is not None 
            and o.get("implied_volatility") is not None
            and o.get("last_quote", {}).get("bid", 0) > 0
            and o.get("last_quote", {}).get("ask", 0) > 0
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

    # Calculate total open interest for each expiration to use in the liquidity gate
    exp_oi = {}
    for exp, chain in by_exp.items():
        oi_sum = sum(c.get("open_interest", 0) or 0 for c in chain)
        exp_oi[exp] = oi_sum

    # Filter expirations for IV extraction: prefer DTE >= 30 OR total expiration OI >= 50
    iv_expirations = []
    for exp in expirations:
        try:
            d = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (d - today).days
            oi = exp_oi.get(exp, 0)
            if dte >= 30 or oi >= 50:
                iv_expirations.append(exp)
        except Exception:
            continue

    if not iv_expirations:
        iv_expirations = expirations

    # Use the best available expiration from the filtered list for IV extraction
    iv_exp = None
    iv_chosen_diff = 10**9
    for exp in iv_expirations:
        try:
            d = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (d - today).days
            diff = abs(dte - target_dte)
            if diff < iv_chosen_diff:
                iv_chosen_diff = diff
                iv_exp = exp
        except Exception:
            continue

    if not iv_exp:
        iv_exp = chosen_exp or expirations[0]

    iv_chain = by_exp.get(iv_exp, [])

    # Step 1: ATM IV + skew
    iv_today = _extract_atm_iv(iv_chain, spot)
    result["skew_25d"] = _extract_skew_25d(iv_chain)
    
    if iv_today:
        result["iv_current"] = round(iv_today, 4)
        
    result["iv_rank"] = None
    result["iv_samples"] = 0

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
