#!/usr/bin/env python3
"""
Signal Tracker — CB Screener v7.2
===================================
Two independent tracking systems that observe scan outputs forward in time.

SYSTEM 1 — Signal performance (composite model)
  Entry: first appearance of BUY or STRONG BUY
  Exit:  SELL signal (WATCH/HOLD do not end tracking)
  Result: what would have happened buying on BUY, selling on SELL
  Re-entry: separate row per BUY→SELL cycle

SYSTEM 2 — P(+10%) hit rate (ML time model)
  Entry: p10 > 0.60 AND not currently tracked
  Exit:  price hits +10% from entry OR 60 days elapsed
  Result: did the ML prediction materialize within the window
  Re-entry: only after current window closes

STORAGE (GCS)
  signal_tracking/open.json       currently open BUY tracks
  signal_tracking/closed.json     completed BUY→SELL cycles
  hit_rate_tracking/open.json     currently open p10 windows
  hit_rate_tracking/closed.json   completed p10 windows
  stock_history/{SYMBOL}.json     [date, price, composite] per scan (for stock-page chart)

Both systems consume the same scan JSON and rely on reused quote prices —
zero additional FMP calls per scan.

Invoked once per scan by run_scan_job.py after save_scan_to_gcs() completes.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GCS I/O (uses same bucket + metadata-token pattern as macro_regime.py)
# ---------------------------------------------------------------------------

GCS_BUCKET = "screener-signals-carbonbridge"

# Canonical paths. Changing these breaks existing tracked state — don't.
SIGNAL_OPEN_PATH   = "signal_tracking/open.json"
SIGNAL_CLOSED_PATH = "signal_tracking/closed.json"
HITRATE_OPEN_PATH   = "hit_rate_tracking/open.json"
HITRATE_CLOSED_PATH = "hit_rate_tracking/closed.json"
STOCK_HISTORY_PREFIX = "stock_history"

# Config
HIT_THRESHOLD_PCT = 10.0     # P(+10%) target
HIT_WINDOW_DAYS   = 60       # P(+10%) observation window
P10_INCLUSION     = 0.60     # Minimum ML p10 for hit-rate tracking
STOCK_HISTORY_KEEP_DAYS = 365  # Trim stock_history beyond this


def _gcs_token() -> Optional[str]:
    """GCE/Cloud Run metadata token. None when running locally."""
    try:
        import requests
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=2,
        )
        return r.json().get("access_token") if r.status_code == 200 else None
    except Exception:
        return None


def _gcs_read(path: str, default: dict | list) -> dict | list:
    """Read JSON from GCS. Returns default on any failure."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return default
        r = requests.get(
            f"https://storage.googleapis.com/{GCS_BUCKET}/{path}",
            headers={"Authorization": f"Bearer {tok}"}, timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return default
        log.warning(f"GCS read {path}: {r.status_code}")
    except Exception as e:
        log.warning(f"GCS read {path} failed: {e}")
    return default


def _gcs_write(path: str, data: dict | list) -> bool:
    """Write JSON to GCS. Returns True on success."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            log.debug(f"GCS write {path}: no token (local mode)")
            return False
        r = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o",
            params={"uploadType": "media", "name": path},
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            data=json.dumps(data, default=str), timeout=15,
        )
        if r.status_code in (200, 201):
            return True
        log.warning(f"GCS write {path}: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log.warning(f"GCS write {path} failed: {e}")
    return False


# ---------------------------------------------------------------------------
# System 1 — Signal performance (BUY/STRONG BUY → SELL)
# ---------------------------------------------------------------------------

def _update_signal_tracks(stocks: list, today_str: str, region: str) -> tuple[int, int, int]:
    """
    Update signal_tracking for System 1.

    - Add new entries for every BUY/STRONG BUY not currently tracked (this region).
    - Update max/min/last fields for currently tracked entries.
    - Close tracks when the stock appears with SELL signal.

    Returns: (new_tracks, closed_tracks, active_tracks_after)
    """
    open_data = _gcs_read(SIGNAL_OPEN_PATH, {"entries": []})
    closed_data = _gcs_read(SIGNAL_CLOSED_PATH, {"entries": []})

    open_entries = open_data.get("entries", [])
    closed_entries = closed_data.get("entries", [])

    # Index current open tracks by (symbol, region, entry_date) — a stock can
    # have multiple rows if it cycled through BUY→SELL→BUY. We only track the
    # latest-open one per (symbol, region) pair; earlier ones were already closed.
    open_by_sym_region: dict[tuple[str, str], dict] = {}
    for e in open_entries:
        key = (e["symbol"], e.get("region", "unknown"))
        # Keep the most recent entry_date if duplicates exist
        if key not in open_by_sym_region or e["entry_date"] > open_by_sym_region[key]["entry_date"]:
            open_by_sym_region[key] = e

    # Build today's scan lookup
    scan_by_sym = {s["symbol"]: s for s in stocks}

    new_count = 0
    closed_count = 0

    # ─── Update existing open tracks ───
    for (sym, reg), entry in list(open_by_sym_region.items()):
        if reg != region:
            continue  # other region's tracks — don't touch
        s = scan_by_sym.get(sym)
        if s is None:
            # Symbol not in today's scan. Could be delisted, filtered, or dropped
            # from universe. Keep the track open but don't update prices.
            continue

        price = s.get("price", 0) or 0
        composite = s.get("composite", 0) or 0
        signal = s.get("signal", "HOLD")

        # Update running extremes
        entry["last_price"] = price
        entry["last_composite"] = composite
        entry["last_signal"] = signal
        entry["last_updated"] = today_str
        entry["max_price"] = max(entry.get("max_price", price), price)
        entry["min_price"] = min(entry.get("min_price", price) or price, price)
        try:
            d0 = datetime.strptime(entry["entry_date"], "%Y-%m-%d")
            d1 = datetime.strptime(today_str, "%Y-%m-%d")
            entry["days_held"] = (d1 - d0).days
        except Exception:
            entry["days_held"] = entry.get("days_held", 0)

        # SELL terminates the track
        if signal == "SELL":
            ep = entry["entry_price"] or 0
            realized_pnl = ((price - ep) / ep * 100) if ep > 0 else 0.0
            max_gain = ((entry["max_price"] - ep) / ep * 100) if ep > 0 else 0.0
            max_dd   = ((entry["min_price"] - ep) / ep * 100) if ep > 0 else 0.0
            closed_entry = dict(entry)
            closed_entry.update({
                "exit_date":      today_str,
                "exit_price":     price,
                "exit_composite": composite,
                "exit_signal":    "SELL",
                "realized_pnl_pct": round(realized_pnl, 2),
                "max_gain_pct":     round(max_gain, 2),
                "max_dd_pct":       round(max_dd, 2),
            })
            closed_entries.append(closed_entry)
            # Remove from open set (drop from list below using a marker)
            entry["__closed__"] = True
            closed_count += 1

    # ─── Rebuild open list without closed entries ───
    open_entries = [e for e in open_entries if not e.pop("__closed__", False)]

    # ─── Identify new BUY/STRONG BUY entries ───
    # Key: anything in today's scan labeled BUY or STRONG BUY that doesn't
    # have an already-open track for (symbol, region).
    currently_open_keys = {(e["symbol"], e.get("region", "unknown")) for e in open_entries}

    for s in stocks:
        sig = s.get("signal")
        if sig not in ("BUY", "STRONG BUY"):
            continue
        key = (s["symbol"], region)
        if key in currently_open_keys:
            continue  # already tracking this BUY cycle

        price = s.get("price", 0) or 0
        composite = s.get("composite", 0) or 0
        if price <= 0:
            continue  # skip entries with no price

        new_entry = {
            "symbol":          s["symbol"],
            "region":          region,
            "entry_date":      today_str,
            "entry_price":     round(price, 4),
            "entry_composite": round(composite, 4),
            "entry_signal":    sig,
            "sector":          s.get("sector", ""),
            "industry":        s.get("industry", ""),
            "classification":  s.get("classification", ""),
            # Running fields
            "last_price":      round(price, 4),
            "last_composite":  round(composite, 4),
            "last_signal":     sig,
            "last_updated":    today_str,
            "max_price":       round(price, 4),
            "min_price":       round(price, 4),
            "days_held":       0,
        }
        open_entries.append(new_entry)
        new_count += 1

    # Cap closed history at 5000 entries to keep file size manageable
    if len(closed_entries) > 5000:
        closed_entries = closed_entries[-5000:]

    _gcs_write(SIGNAL_OPEN_PATH, {
        "entries": open_entries,
        "updated": datetime.utcnow().isoformat() + "Z",
    })
    _gcs_write(SIGNAL_CLOSED_PATH, {
        "entries": closed_entries,
        "updated": datetime.utcnow().isoformat() + "Z",
    })

    return new_count, closed_count, len(open_entries)


# ---------------------------------------------------------------------------
# System 2 — P(+10%) hit rate (60d windows)
# ---------------------------------------------------------------------------

def _update_hitrate_tracks(stocks: list, today_str: str, region: str) -> tuple[int, int, int]:
    """
    Update hit_rate_tracking for System 2.

    - Add new entries for stocks with p10 > 0.60 not currently tracked.
    - Update max_price for tracked entries.
    - Close windows that hit +10% OR exceed 60 days.

    Returns: (new_tracks, closed_tracks, active_tracks_after)
    """
    open_data = _gcs_read(HITRATE_OPEN_PATH, {"entries": []})
    closed_data = _gcs_read(HITRATE_CLOSED_PATH, {"entries": []})

    open_entries = open_data.get("entries", [])
    closed_entries = closed_data.get("entries", [])

    # Hit-rate tracking is region-independent (same stock same window no matter
    # which region scanned it), but we store the region for attribution. Use
    # symbol alone as the "currently tracked" key.
    open_by_sym: dict[str, dict] = {e["symbol"]: e for e in open_entries}
    scan_by_sym = {s["symbol"]: s for s in stocks}
    today = datetime.strptime(today_str, "%Y-%m-%d")

    new_count = 0
    closed_count = 0

    # ─── Update existing open windows ───
    for sym, entry in list(open_by_sym.items()):
        s = scan_by_sym.get(sym)
        if s is None:
            # Not in today's scan — still age the window though
            try:
                d0 = datetime.strptime(entry["entry_date"], "%Y-%m-%d")
                days_elapsed = (today - d0).days
            except Exception:
                days_elapsed = entry.get("days_elapsed", 0)
            entry["days_elapsed"] = days_elapsed

            # If window expired without update, close as "window_closed" with
            # no new price data. max_price stays at last known value.
            if days_elapsed >= HIT_WINDOW_DAYS:
                ep = entry["entry_price"] or 0
                max_gain = ((entry["max_price"] - ep) / ep * 100) if ep > 0 else 0.0
                closed_entry = dict(entry)
                closed_entry.update({
                    "exit_date":    today_str,
                    "exit_reason":  "window_closed",
                    "hit":          max_gain >= HIT_THRESHOLD_PCT,
                    "max_gain_pct": round(max_gain, 2),
                    "hit_date":     entry.get("hit_date"),
                })
                closed_entries.append(closed_entry)
                entry["__closed__"] = True
                closed_count += 1
            continue

        price = s.get("price", 0) or 0
        if price <= 0:
            continue

        ep = entry["entry_price"] or 0
        if price > entry.get("max_price", 0):
            entry["max_price"] = price
            # Record the first date we breach +10% (for reporting "days_to_hit")
            if ep > 0 and not entry.get("hit_date"):
                max_gain = (price - ep) / ep * 100
                if max_gain >= HIT_THRESHOLD_PCT:
                    entry["hit_date"] = today_str
        try:
            d0 = datetime.strptime(entry["entry_date"], "%Y-%m-%d")
            days_elapsed = (today - d0).days
        except Exception:
            days_elapsed = entry.get("days_elapsed", 0)
        entry["days_elapsed"] = days_elapsed
        entry["last_price"] = price
        entry["last_updated"] = today_str

        # ─── Exit conditions ───
        max_gain = ((entry["max_price"] - ep) / ep * 100) if ep > 0 else 0.0
        exit_reason = None
        if max_gain >= HIT_THRESHOLD_PCT:
            exit_reason = "hit_10pct"
        elif days_elapsed >= HIT_WINDOW_DAYS:
            exit_reason = "window_closed"

        if exit_reason:
            closed_entry = dict(entry)
            closed_entry.update({
                "exit_date":    today_str,
                "exit_reason":  exit_reason,
                "hit":          exit_reason == "hit_10pct",
                "max_gain_pct": round(max_gain, 2),
                "hit_date":     entry.get("hit_date"),
            })
            closed_entries.append(closed_entry)
            entry["__closed__"] = True
            closed_count += 1

    # ─── Rebuild open list ───
    open_entries = [e for e in open_entries if not e.pop("__closed__", False)]

    # ─── Identify new p10 > 0.60 entries ───
    currently_open_syms = {e["symbol"] for e in open_entries}

    for s in stocks:
        if s["symbol"] in currently_open_syms:
            continue
        p10 = s.get("hit_prob") or s.get("p10") or 0
        # hit_prob is stored as 0-1 in v7.2 JSONs
        if p10 is None or p10 < P10_INCLUSION:
            continue
        price = s.get("price", 0) or 0
        if price <= 0:
            continue

        new_entry = {
            "symbol":          s["symbol"],
            "region":          region,
            "entry_date":      today_str,
            "entry_price":     round(price, 4),
            "entry_composite": round(s.get("composite", 0) or 0, 4),
            "entry_signal":    s.get("signal", ""),
            "entry_p10":       round(p10, 4),
            "sector":          s.get("sector", ""),
            "industry":        s.get("industry", ""),
            "classification":  s.get("classification", ""),
            # Running fields
            "last_price":      round(price, 4),
            "last_updated":    today_str,
            "max_price":       round(price, 4),
            "days_elapsed":    0,
            "hit_date":        None,
        }
        open_entries.append(new_entry)
        new_count += 1

    # Cap closed history at 5000 entries
    if len(closed_entries) > 5000:
        closed_entries = closed_entries[-5000:]

    _gcs_write(HITRATE_OPEN_PATH, {
        "entries": open_entries,
        "updated": datetime.utcnow().isoformat() + "Z",
    })
    _gcs_write(HITRATE_CLOSED_PATH, {
        "entries": closed_entries,
        "updated": datetime.utcnow().isoformat() + "Z",
    })

    return new_count, closed_count, len(open_entries)


# ---------------------------------------------------------------------------
# Stock history (for the price+composite chart on stock page)
# ---------------------------------------------------------------------------

def _update_stock_history(stocks: list, today_str: str):
    """
    Append today's (date, price, composite) to per-symbol history files.
    One file per symbol. Limited to stocks with composite > 0 and price > 0.
    """
    cutoff_date = (datetime.strptime(today_str, "%Y-%m-%d")
                   - timedelta(days=STOCK_HISTORY_KEEP_DAYS)).strftime("%Y-%m-%d")

    # Throttle: only write history for stocks with composite coverage >= 6/13
    # (otherwise we're storing noise from half-evaluated scans).
    written = 0
    for s in stocks:
        sym = s["symbol"]
        price = s.get("price", 0) or 0
        composite = s.get("composite", 0) or 0
        coverage = s.get("factor_coverage", 0) or 0
        if price <= 0 or composite <= 0 or coverage < 6:
            continue

        path = f"{STOCK_HISTORY_PREFIX}/{sym}.json"
        history = _gcs_read(path, [])
        if not isinstance(history, list):
            history = []

        # Dedup: if today's date is already the last entry, replace it (handles
        # multiple scans per day — Europe + SP500 + Global).
        today_idx = next((i for i, row in enumerate(history)
                          if isinstance(row, list) and len(row) >= 1 and row[0] == today_str), -1)
        new_row = [today_str, round(price, 4), round(composite, 4)]
        if today_idx >= 0:
            history[today_idx] = new_row
        else:
            history.append(new_row)

        # Trim old entries
        history = [row for row in history
                   if isinstance(row, list) and len(row) >= 1 and row[0] >= cutoff_date]

        if _gcs_write(path, history):
            written += 1

    log.info(f"  Stock history: {written} symbols updated")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def update_from_scan(stocks: list, region: str, scan_date: str = None):
    """
    Update all tracking systems from a completed scan.

    Args:
        stocks: list of stock dicts as written to latest_{region}.json
        region: "sp500" | "europe" | "global" | etc.
        scan_date: YYYY-MM-DD string. Defaults to today.
    """
    if not stocks:
        log.info("signal_tracker: no stocks, skipping update")
        return

    today_str = scan_date or datetime.now().strftime("%Y-%m-%d")

    try:
        s1_new, s1_closed, s1_active = _update_signal_tracks(stocks, today_str, region)
        log.info(f"  Signal tracker (System 1): +{s1_new} new BUY, {s1_closed} closed, {s1_active} active")
    except Exception as e:
        log.error(f"signal_tracker System 1 failed: {e}", exc_info=True)

    try:
        s2_new, s2_closed, s2_active = _update_hitrate_tracks(stocks, today_str, region)
        log.info(f"  Hit-rate tracker (System 2): +{s2_new} new p10>0.60, {s2_closed} closed, {s2_active} active")
    except Exception as e:
        log.error(f"signal_tracker System 2 failed: {e}", exc_info=True)

    try:
        _update_stock_history(stocks, today_str)
    except Exception as e:
        log.error(f"stock_history update failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Standalone reader helpers (used by run_server.py HTTP endpoints)
# ---------------------------------------------------------------------------

def read_signal_tracks() -> dict:
    """Return {open: [...], closed: [...]} for /performance/signal-tracks."""
    return {
        "open":   _gcs_read(SIGNAL_OPEN_PATH, {"entries": []}).get("entries", []),
        "closed": _gcs_read(SIGNAL_CLOSED_PATH, {"entries": []}).get("entries", []),
    }


def read_hitrate_tracks() -> dict:
    """Return {open: [...], closed: [...]} for /performance/hit-rates."""
    return {
        "open":   _gcs_read(HITRATE_OPEN_PATH, {"entries": []}).get("entries", []),
        "closed": _gcs_read(HITRATE_CLOSED_PATH, {"entries": []}).get("entries", []),
    }


def read_stock_history(symbol: str) -> list:
    """Return [[date, price, composite], ...] for /stock/{SYMBOL}/history."""
    data = _gcs_read(f"{STOCK_HISTORY_PREFIX}/{symbol.upper()}.json", [])
    return data if isinstance(data, list) else []
