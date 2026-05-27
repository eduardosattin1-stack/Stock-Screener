#!/usr/bin/env python3
"""
paper_strategy_runner_speculair.py
==================================
Speculair Apex Basket paper-tracking runner.

Reads the Speculair Apex Basket from speculair_baskets.json (GCS),
tracks entry/exit prices, computes mark-to-market PnL with SPY benchmark.

Lifecycle:
  - Monthly rebalance (aligned with debate pipeline runs)
  - Apex Basket: 5-7 positions from Director allocation
  - SPY benchmark for relative performance

Usage:
  export FMP_API_KEY=...
  python3 paper_strategy_runner_speculair.py [--dry-run] [--force-rotate]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import time
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("speculair_runner")

# ─────────────────────────────────────────────────────────────────────────
FMP_KEY = os.environ.get("FMP_API_KEY", "")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")

STRATEGY_VERSION = "speculair-apex-v1.0-2026-05-27"
TOP_N = 7                       # max basket size (5-7)
REBALANCE_DAYS = 28             # monthly rebalance cadence

SPECULAIR_BASKETS_PATH = "scans/speculair_baskets.json"
HISTORY_PATH = "strategies/speculair/strategy_history_speculair.json"
BASKET_SNAPSHOT_PREFIX = "strategies/speculair/baskets/"

FMP_BASE = "https://financialmodelingprep.com/stable"


# ─────────────────────────────────────────────────────────────────────────
# GCS read/write (same pattern as compounder runner)
# ─────────────────────────────────────────────────────────────────────────
def gcs_read(path: str, default=None):
    url = f"https://storage.googleapis.com/{GCS_BUCKET}/{path}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return default
        log.warning(f"GCS read {path} → HTTP {r.status_code}")
    except Exception as e:
        log.warning(f"GCS read {path} failed: {e}")
    return default


def gcs_write(path: str, data: dict, dry_run: bool = False):
    if dry_run:
        log.info(f"[DRY-RUN] Would write {path} ({len(json.dumps(data))} bytes)")
        return True
    try:
        tok_resp = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=3,
        )
        token = tok_resp.json().get("access_token", "")
        if not token:
            log.error(f"GCS write {path}: no access token from metadata server")
            return False
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o"
        r = requests.post(
            url,
            params={"uploadType": "media", "name": path, "cacheControl": "no-cache, max-age=0"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            data=json.dumps(data, default=str, indent=2),
            timeout=20,
        )
        if r.status_code in (200, 201):
            log.info(f"Wrote gs://{GCS_BUCKET}/{path}")
            return True
        log.error(f"GCS write {path}: HTTP {r.status_code} → {r.text[:200]}")
        return False
    except Exception as e:
        log.error(f"GCS write {path} failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────
# FMP price fetch
# ─────────────────────────────────────────────────────────────────────────
def fmp_quote(symbol: str) -> Optional[float]:
    if not FMP_KEY:
        return None
    try:
        r = requests.get(f"{FMP_BASE}/quote-short",
                         params={"symbol": symbol, "apikey": FMP_KEY},
                         timeout=15)
        if r.status_code == 200:
            d = r.json()
            if isinstance(d, list) and d and d[0].get("price"):
                return float(d[0]["price"])
    except Exception as e:
        log.warning(f"FMP quote {symbol}: {e}")
    return None


def fmp_quote_batch(symbols: list[str]) -> dict[str, float]:
    if not symbols: return {}
    out: dict[str, float] = {}
    for i in range(0, len(symbols), 25):
        chunk = symbols[i:i+25]
        try:
            r = requests.get(f"{FMP_BASE}/batch-quote-short",
                             params={"symbols": ",".join(chunk), "apikey": FMP_KEY},
                             timeout=20)
            if r.status_code == 200 and isinstance(r.json(), list):
                for row in r.json():
                    s = row.get("symbol"); p = row.get("price")
                    if s and p: out[s] = float(p)
        except Exception as e:
            log.warning(f"batch-quote chunk {i}: {e}")
        time.sleep(0.1)
    for s in symbols:
        if s not in out:
            p = fmp_quote(s)
            if p: out[s] = p
            time.sleep(0.05)
    return out


# ─────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────
def empty_history() -> dict:
    return {
        "region": "speculair",
        "strategy_version": STRATEGY_VERSION,
        "inception_date": None,
        "spy_inception_price": None,
        "current_basket": [],
        "rotations": [],
        "weekly_marks": [],
        "summary": None,
        "last_rotation_date": None,
        "updated_at": None,
    }


# ─────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────
def build_basket_from_speculair(baskets_data: dict) -> list[dict]:
    """Extract apex basket picks from speculair_baskets.json."""
    apex = baskets_data.get("apex_basket", [])
    if not apex:
        log.warning("No apex_basket in speculair data")
        return []
    
    picks = []
    for p in apex:
        sym = p.get("symbol", "")
        if not sym:
            continue
        picks.append({
            "symbol": sym,
            "conviction": p.get("conviction", 5),
            "entry_price": p.get("entry_price", 0),
            "entry_date": p.get("entry_date", ""),
            "source_methodologies": p.get("source_methodologies", []),
            "sector": p.get("sector", ""),
        })
    
    return picks[:TOP_N]


def open_first_basket(scan_date: str, picks: list[dict]) -> tuple[list, float]:
    spy = fmp_quote("SPY") or 0.0
    
    # Get current prices for all picks
    syms = [p["symbol"] for p in picks]
    quotes = fmp_quote_batch(syms)
    
    positions = []
    for p in picks:
        price = quotes.get(p["symbol"]) or p.get("entry_price", 0)
        if price <= 0:
            continue
        positions.append({
            "symbol": p["symbol"],
            "sector": p.get("sector", ""),
            "entry_price": round(price, 4),
            "entry_date": scan_date,
            "conviction": p.get("conviction", 5),
            "source_methodologies": p.get("source_methodologies", []),
            "last_price": round(price, 4),
            "last_marked": scan_date,
            "return_pct": 0.0,
        })
    
    log.info(f"  Opened {len(positions)} positions")
    return positions, spy


def rotate_basket(scan_date: str, current: list[dict],
                  new_picks: list[dict]) -> tuple[list, list, list]:
    """Rotate: keep positions still in apex, add new, remove dropped."""
    new_syms = {p["symbol"] for p in new_picks}
    cur_syms = {p["symbol"] for p in current}
    
    # Keep existing positions still in apex
    keep = [p for p in current if p["symbol"] in new_syms]
    to_remove = [p for p in current if p["symbol"] not in new_syms]
    
    # Get exit prices
    removed_log = []
    if to_remove:
        quotes = fmp_quote_batch([p["symbol"] for p in to_remove])
        for p in to_remove:
            exit_price = quotes.get(p["symbol"], p.get("last_price", p["entry_price"]))
            ret = (exit_price - p["entry_price"]) / p["entry_price"] if p["entry_price"] > 0 else 0
            removed_log.append({
                "symbol": p["symbol"],
                "entry_price": round(p["entry_price"], 4),
                "exit_price": round(exit_price, 4),
                "entry_date": p["entry_date"],
                "exit_date": scan_date,
                "return_pct": round(ret * 100, 4),
            })
            log.info(f"  ROTATED OUT {p['symbol']}: {ret*100:+.2f}%")
    
    # Add new positions
    added_log = []
    to_add = [p for p in new_picks if p["symbol"] not in cur_syms]
    if to_add:
        quotes = fmp_quote_batch([p["symbol"] for p in to_add])
        for p in to_add:
            price = quotes.get(p["symbol"]) or p.get("entry_price", 0)
            if price <= 0:
                continue
            new_pos = {
                "symbol": p["symbol"],
                "sector": p.get("sector", ""),
                "entry_price": round(price, 4),
                "entry_date": scan_date,
                "conviction": p.get("conviction", 5),
                "source_methodologies": p.get("source_methodologies", []),
                "last_price": round(price, 4),
                "last_marked": scan_date,
                "return_pct": 0.0,
            }
            keep.append(new_pos)
            added_log.append({
                "symbol": p["symbol"],
                "entry_price": round(price, 4),
            })
            log.info(f"  ROTATED IN  {p['symbol']}: entry ${price:.2f}")
    
    return keep, removed_log, added_log


def mark_to_market(positions: list[dict], scan_date: str) -> tuple[list, list]:
    if not positions:
        return positions, []
    syms = [p["symbol"] for p in positions]
    quotes = fmp_quote_batch(syms)
    updated = []
    rets = []
    for p in positions:
        cur = quotes.get(p["symbol"])
        if cur and p["entry_price"] > 0:
            ret = (cur - p["entry_price"]) / p["entry_price"]
            updated.append({
                **p,
                "last_price": round(cur, 4),
                "last_marked": scan_date,
                "return_pct": round(ret * 100, 4),
            })
            rets.append(ret)
        else:
            updated.append(p)
            if "return_pct" in p:
                rets.append(p["return_pct"] / 100.0)
    return updated, rets


def add_weekly_mark(history: dict, scan_date: str, rets: list[float]) -> Optional[dict]:
    if not rets:
        return None
    basket_avg = sum(rets) / len(rets) * 100.0
    spy_now = fmp_quote("SPY") or 0
    spy_inc = history.get("spy_inception_price") or 0
    spy_ret = (spy_now - spy_inc) / spy_inc * 100.0 if spy_inc > 0 else 0.0
    
    inception = history.get("inception_date")
    days = 0
    if inception:
        try:
            days = (dt.date.fromisoformat(scan_date) - dt.date.fromisoformat(inception)).days
        except Exception:
            pass
    
    mark = {
        "date": scan_date,
        "basket_avg_return_pct": round(basket_avg, 4),
        "spy_return_pct": round(spy_ret, 4),
        "alpha_pp": round(basket_avg - spy_ret, 4),
        "spy_price": round(spy_now, 4),
        "n_positions": len(rets),
        "days_since_inception": days,
    }
    log.info(f"Mark: basket {basket_avg:+.2f}%, SPY {spy_ret:+.2f}%, alpha {mark['alpha_pp']:+.2f}pp")
    return mark


def should_rebalance(history: dict, scan_date: str, force: bool = False) -> bool:
    if force or not history.get("current_basket"):
        return True
    last = history.get("last_rotation_date") or history.get("inception_date")
    if not last:
        return True
    try:
        delta = (dt.date.fromisoformat(scan_date) - dt.date.fromisoformat(last)).days
    except Exception:
        return True
    if delta >= REBALANCE_DAYS:
        log.info(f"  Rebalance: {delta} days since last rotation ≥ {REBALANCE_DAYS}")
        return True
    log.info(f"  Rebalance: {delta} days < {REBALANCE_DAYS} → mark only")
    return False


def recompute_summary(history: dict) -> dict:
    rotations = history.get("rotations", [])
    closed = [rem for r in rotations for rem in r.get("removed", [])]
    current = history.get("current_basket", [])
    marks = history.get("weekly_marks", [])
    
    if closed:
        rets = [p["return_pct"] for p in closed]
        realized_avg = sum(rets) / len(rets)
        win_rate = sum(1 for r in rets if r > 0) / len(rets)
    else:
        realized_avg = win_rate = 0
    
    open_rets = [p.get("return_pct", 0) for p in current]
    open_avg = sum(open_rets) / len(open_rets) if open_rets else 0
    
    last = marks[-1] if marks else None
    return {
        "weeks_tracked": len(marks),
        "n_positions_open": len(current),
        "n_rotations": len(rotations),
        "n_positions_closed": len(closed),
        "open_avg_return_pct": round(open_avg, 4),
        "realized_avg_return_pct": round(realized_avg, 4),
        "realized_win_rate": round(win_rate, 4),
        "cum_basket_return_pct": round(last["basket_avg_return_pct"], 4) if last else 0,
        "cum_spy_return_pct": round(last["spy_return_pct"], 4) if last else 0,
        "cum_alpha_pp": round(last["alpha_pp"], 4) if last else 0,
    }


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def run(dry_run: bool = False, force_rotate: bool = False):
    today = dt.date.today().isoformat()
    log.info(f"SPECULAIR runner starting {today}")
    
    # 1. Load state
    history = gcs_read(HISTORY_PATH, empty_history())
    if not isinstance(history, dict) or "current_basket" not in history:
        history = empty_history()
    
    # 2. Load speculair baskets
    baskets = gcs_read(SPECULAIR_BASKETS_PATH)
    if not baskets:
        log.error("Could not read speculair_baskets.json — aborting")
        return False
    
    picks = build_basket_from_speculair(baskets)
    if not picks:
        log.error("No apex basket picks — aborting")
        return False
    
    log.info(f"Apex basket: {[p['symbol'] for p in picks]}")
    
    # 3. Lifecycle
    current = history.get("current_basket", [])
    is_first = len(current) == 0
    rotate_now = should_rebalance(history, today, force=force_rotate)
    
    if is_first:
        positions, spy = open_first_basket(today, picks)
        history["inception_date"] = today
        history["spy_inception_price"] = spy
        history["current_basket"] = positions
        history["last_rotation_date"] = today
        positions, rets = mark_to_market(positions, today)
        history["current_basket"] = positions
        mark = add_weekly_mark(history, today, rets)
        if mark:
            history["weekly_marks"].append(mark)
    else:
        if rotate_now:
            new_basket, removed, added = rotate_basket(today, current, picks)
            if removed or added:
                history["rotations"].append({
                    "date": today,
                    "n_removed": len(removed),
                    "n_added": len(added),
                    "removed": removed,
                    "added": added,
                })
            history["last_rotation_date"] = today
            current = new_basket
        
        current, rets = mark_to_market(current, today)
        history["current_basket"] = current
        mark = add_weekly_mark(history, today, rets)
        if mark:
            history["weekly_marks"].append(mark)
    
    history["summary"] = recompute_summary(history)
    history["updated_at"] = today
    
    # 4. Write
    gcs_write(HISTORY_PATH, history, dry_run=dry_run)
    gcs_write(f"{BASKET_SNAPSHOT_PREFIX}{today}_speculair.json", {
        "date": today,
        "current_basket": history.get("current_basket"),
        "summary": history.get("summary"),
    }, dry_run=dry_run)
    
    # 5. Log
    if history["current_basket"]:
        log.info(f"FINAL BASKET ({len(history['current_basket'])} positions):")
        for p in history["current_basket"]:
            log.info(f"  {p['symbol']:<6} entry ${p['entry_price']:.2f} → "
                     f"${p.get('last_price', 0):.2f} ({p.get('return_pct', 0):+.2f}%)")
    if history["summary"]:
        s = history["summary"]
        log.info(f"SUMMARY: {s['weeks_tracked']} weeks, "
                 f"alpha {s['cum_alpha_pp']:+.2f}pp")
    
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-rotate", action="store_true")
    args = ap.parse_args()
    
    if not FMP_KEY:
        log.error("FMP_API_KEY not set; aborting")
        sys.exit(1)
    
    ok = run(dry_run=args.dry_run, force_rotate=args.force_rotate)
    sys.exit(0 if ok else 1)
