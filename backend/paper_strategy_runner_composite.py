#!/usr/bin/env python3
"""
paper_strategy_runner_composite.py
===================================
COMPOSITE strategy: top-10 SP500 stocks by composite score, equal-weight,
weekly rotation (replace anything that falls out of top-10).

Runs Friday 06:30 CET after the SP500 scan, in parallel with the BORING runner.

Lifecycle:
  1. Read existing strategy_history_composite.json from GCS
  2. Read latest_sp500.json from GCS
  3. Sort scan by composite DESC, take top-10 → target_basket

  IF no current basket (first run):
    - Open all 10 positions at today's prices
    - Save inception SPY price

  IF current basket exists:
    - For each currently held position NOT in target_basket:
        Close it. Record final return. Add to rotation log.
    - For each target position NOT currently held:
        Open it at today's price.
    - Stays-in positions: no action (entry_price unchanged)
    - Append weekly_mark with basket vs SPY

  4. Recompute summary
  5. Write strategy_history_composite.json

Output schema (mirrors BORING where possible):
  {
    region: "composite",
    strategy_version: "composite-v1.0-2026-04-28",
    inception_date: "2026-04-26",
    spy_inception_price: 712.45,
    current_basket: [
      {symbol, entry_price, entry_date, composite_at_entry,
       last_price, last_marked, return_pct}
    ],
    rotations: [
      {date, removed: [{symbol, entry_date, exit_date, entry_price,
        exit_price, return_pct, days_held}],
       added: [{symbol, entry_price}]}
    ],
    weekly_marks: [
      {date, basket_avg_return_pct, spy_return_pct, alpha_pp,
       n_positions, days_since_inception}
    ],
    summary: {...}
  }

Usage:
  export FMP_API_KEY=...
  python3 paper_strategy_runner_composite.py [--dry-run]
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
log = logging.getLogger("composite_runner")

# ─────────────────────────────────────────────────────────────────────────
FMP_KEY = os.environ.get("FMP_API_KEY", "")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")

STRATEGY_VERSION = "composite-v1.0-2026-04-28"
TOP_N = 10

LATEST_SCAN_PATH = "scans/latest_sp500.json"
HISTORY_PATH = "performance/strategy_history_composite.json"
BASKET_SNAPSHOT_PREFIX = "performance/baskets/"

FMP_BASE = "https://financialmodelingprep.com/stable"


# ─────────────────────────────────────────────────────────────────────────
# GCS read/write
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
    """Authenticated write via metadata-server token + REST upload.
    Matches the gcs_upload pattern in screener_v6.py (no google-cloud-storage dep)."""
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
        log.warning(f"FMP quote-short {symbol}: {e}")
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
            log.warning(f"batch-quote-short chunk {i}: {e}")
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
        "region": "composite",
        "strategy_version": STRATEGY_VERSION,
        "inception_date": None,
        "spy_inception_price": None,
        "current_basket": [],
        "rotations": [],
        "weekly_marks": [],
        "summary": None,
        "updated_at": None,
    }


def select_top_n(scan_data: dict) -> list[dict]:
    """Sort scan by composite DESC, take top-N. Returns picks with price + composite."""
    stocks = scan_data.get("stocks", []) if isinstance(scan_data, dict) else []
    if not stocks:
        log.error("Scan has no stocks")
        return []

    candidates = []
    for s in stocks:
        comp = s.get("composite")
        if comp is None: continue
        price = s.get("price")
        if not price or price <= 0: continue
        candidates.append({
            "symbol": s.get("symbol", "").upper(),
            "composite": float(comp),
            "price": float(price),
            "piotroski": s.get("piotroski"),
        })

    if len(candidates) < TOP_N:
        log.error(f"Not enough scan candidates with composite (got {len(candidates)})")
        return []

    candidates.sort(key=lambda x: -x["composite"])
    picks = candidates[:TOP_N]
    log.info(f"Top-{TOP_N} by composite: {[p['symbol'] for p in picks]}")
    log.info(f"  composites: {[round(p['composite'], 3) for p in picks]}")
    return picks


# ─────────────────────────────────────────────────────────────────────────
# Lifecycle helpers
# ─────────────────────────────────────────────────────────────────────────
def open_first_basket(scan_date: str, picks: list[dict]) -> tuple[list, float]:
    """First-run: open all 10. Returns (positions, spy_inception_price)."""
    spy = fmp_quote("SPY") or 0.0
    positions = []
    for p in picks:
        positions.append({
            "symbol": p["symbol"],
            "entry_price": p["price"],
            "entry_date": scan_date,
            "composite_at_entry": p["composite"],
            "piotroski_at_entry": p["piotroski"],
            "last_price": p["price"],
            "last_marked": scan_date,
            "return_pct": 0.0,
        })
    return positions, spy


def rotate_basket(scan_date: str,
                  current_positions: list[dict],
                  picks: list[dict]) -> tuple[list, list, list]:
    """Returns (new_basket, removed_log, added_log).
    
    removed_log: positions that were dropped (with full P&L since their entry)
    added_log:   new positions opened today
    """
    target_syms = {p["symbol"] for p in picks}
    current_syms = {p["symbol"] for p in current_positions}

    # Stocks that should be removed
    to_remove = [p for p in current_positions if p["symbol"] not in target_syms]
    # Stocks that should be added
    to_add_picks = [p for p in picks if p["symbol"] not in current_syms]
    # Stocks staying
    keep = [p for p in current_positions if p["symbol"] in target_syms]

    # Get exit prices for removed
    removed_log = []
    if to_remove:
        syms = [p["symbol"] for p in to_remove]
        quotes = fmp_quote_batch(syms)
        for p in to_remove:
            exit_price = quotes.get(p["symbol"])
            if exit_price and p["entry_price"] > 0:
                ret = (exit_price - p["entry_price"]) / p["entry_price"]
            else:
                exit_price = p.get("last_price") or p["entry_price"]
                ret = (exit_price - p["entry_price"]) / p["entry_price"] if p["entry_price"] > 0 else 0
            try:
                ed = dt.date.fromisoformat(p["entry_date"])
                xd = dt.date.fromisoformat(scan_date)
                days_held = (xd - ed).days
            except Exception:
                days_held = 0
            removed_log.append({
                "symbol": p["symbol"],
                "entry_price": round(p["entry_price"], 4),
                "exit_price": round(exit_price, 4),
                "entry_date": p["entry_date"],
                "exit_date": scan_date,
                "return_pct": round(ret * 100, 4),
                "days_held": days_held,
                "composite_at_entry": p.get("composite_at_entry"),
            })
            log.info(f"  ROTATED OUT  {p['symbol']:<6} "
                     f"entry ${p['entry_price']:.2f} → exit ${exit_price:.2f} "
                     f"({ret*100:+.2f}%, {days_held}d)")

    # Build added log
    added_log = []
    new_positions = []
    for p in to_add_picks:
        new_positions.append({
            "symbol": p["symbol"],
            "entry_price": p["price"],
            "entry_date": scan_date,
            "composite_at_entry": p["composite"],
            "piotroski_at_entry": p["piotroski"],
            "last_price": p["price"],
            "last_marked": scan_date,
            "return_pct": 0.0,
        })
        added_log.append({
            "symbol": p["symbol"],
            "entry_price": round(p["price"], 4),
            "composite_at_entry": round(p["composite"], 4),
        })
        log.info(f"  ROTATED IN   {p['symbol']:<6} entry ${p['price']:.2f}")

    new_basket = keep + new_positions
    return new_basket, removed_log, added_log


def mark_to_market(positions: list[dict], scan_date: str) -> tuple[list, list]:
    """Update last_price + return_pct for every position. Returns (updated_positions, individual_returns)."""
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
            # FMP failed — keep prior mark
            updated.append(p)
            if "return_pct" in p:
                rets.append(p["return_pct"] / 100.0)
    return updated, rets


def add_weekly_mark(history: dict, scan_date: str, position_returns: list[float]) -> Optional[dict]:
    """Append weekly mark to history.weekly_marks."""
    if not position_returns:
        return None
    basket_avg_return = sum(position_returns) / len(position_returns) * 100.0

    spy_now = fmp_quote("SPY") or 0
    spy_inception = history.get("spy_inception_price") or 0
    if spy_now and spy_inception > 0:
        spy_return = (spy_now - spy_inception) / spy_inception * 100.0
    else:
        spy_return = 0.0

    inception = history.get("inception_date")
    if inception:
        days_since = (dt.date.fromisoformat(scan_date) -
                      dt.date.fromisoformat(inception)).days
    else:
        days_since = 0

    mark = {
        "date": scan_date,
        "basket_avg_return_pct": round(basket_avg_return, 4),
        "spy_return_pct": round(spy_return, 4),
        "alpha_pp": round(basket_avg_return - spy_return, 4),
        "spy_price": round(spy_now, 4),
        "n_positions": len(position_returns),
        "days_since_inception": days_since,
    }
    log.info(f"Weekly mark: basket avg {basket_avg_return:+.2f}%, "
             f"SPY {spy_return:+.2f}%, alpha {mark['alpha_pp']:+.2f}pp, "
             f"day {days_since}")
    return mark


def recompute_summary(history: dict) -> Optional[dict]:
    """Aggregate stats from rotations + current basket."""
    rotations = history.get("rotations", [])
    closed_positions = []
    for r in rotations:
        for rem in r.get("removed", []):
            closed_positions.append(rem)

    current = history.get("current_basket", [])
    weekly_marks = history.get("weekly_marks", [])

    # Realized stats from closed-out positions
    if closed_positions:
        realized_returns = [p["return_pct"] for p in closed_positions]
        realized_avg = sum(realized_returns) / len(realized_returns)
        realized_wins = sum(1 for r in realized_returns if r > 0)
        realized_win_rate = realized_wins / len(realized_returns)
    else:
        realized_avg = 0
        realized_win_rate = 0
        realized_wins = 0

    # Open stats
    open_returns = [p.get("return_pct", 0) for p in current]
    open_avg = sum(open_returns) / len(open_returns) if open_returns else 0

    # Latest mark
    last_mark = weekly_marks[-1] if weekly_marks else None
    cum_alpha = last_mark["alpha_pp"] if last_mark else 0
    cum_basket_return = last_mark["basket_avg_return_pct"] if last_mark else 0
    cum_spy_return = last_mark["spy_return_pct"] if last_mark else 0

    # Annualized
    inception = history.get("inception_date")
    if inception and last_mark:
        days = max(last_mark["days_since_inception"], 1)
        years = days / 365.25
        if years > 0.05:  # at least ~3 weeks of data
            ann_strategy = ((1 + cum_basket_return / 100) ** (1 / years) - 1) * 100
            ann_spy = ((1 + cum_spy_return / 100) ** (1 / years) - 1) * 100
            ann_alpha = ann_strategy - ann_spy
        else:
            ann_strategy = ann_spy = ann_alpha = 0
    else:
        ann_strategy = ann_spy = ann_alpha = 0

    return {
        "weeks_tracked": len(weekly_marks),
        "n_positions_open": len(current),
        "n_rotations": len(rotations),
        "n_positions_closed": len(closed_positions),
        "open_avg_return_pct": round(open_avg, 4),
        "realized_avg_return_pct": round(realized_avg, 4),
        "realized_wins": realized_wins,
        "realized_win_rate": round(realized_win_rate, 4),
        "cum_basket_return_pct": round(cum_basket_return, 4),
        "cum_spy_return_pct": round(cum_spy_return, 4),
        "cum_alpha_pp": round(cum_alpha, 4),
        "annualized_return_pct": round(ann_strategy, 4),
        "annualized_alpha_pp": round(ann_alpha, 4),
    }


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def run(dry_run: bool = False):
    today = dt.date.today().isoformat()
    log.info(f"COMPOSITE runner starting {today}")
    log.info(f"  Strategy: {STRATEGY_VERSION}, top-{TOP_N} by composite, weekly rotation")

    # 1. State
    history = gcs_read(HISTORY_PATH, empty_history())
    if not isinstance(history, dict) or "current_basket" not in history:
        log.warning("History malformed — resetting")
        history = empty_history()

    # 2. Scan
    scan = gcs_read(LATEST_SCAN_PATH)
    if not scan:
        log.error(f"Could not read {LATEST_SCAN_PATH} from GCS — aborting")
        return False
    raw_scan_date = scan.get("scan_date") or scan.get("date") or today
    scan_date = raw_scan_date[:10]
    log.info(f"Scan loaded: {scan_date} (raw: {raw_scan_date}), "
             f"{len(scan.get('stocks', []))} stocks")

    # 3. Pick top-10
    picks = select_top_n(scan)
    if not picks:
        log.error("Cannot select picks — aborting")
        return False

    # 4. Lifecycle
    current = history.get("current_basket", [])
    is_first_run = len(current) == 0

    if is_first_run:
        log.info("First run — opening initial basket")
        positions, spy_inception = open_first_basket(scan_date, picks)
        history["inception_date"] = scan_date
        history["spy_inception_price"] = spy_inception
        history["current_basket"] = positions
        # Mark to market immediately (return = 0% on day 0, but populates last_price)
        positions, rets = mark_to_market(positions, scan_date)
        history["current_basket"] = positions
        mark = add_weekly_mark(history, scan_date, rets)
        if mark:
            history["weekly_marks"].append(mark)
    else:
        log.info(f"Existing basket: {len(current)} positions")
        log.info(f"  Symbols: {[p['symbol'] for p in current]}")

        # Rotate
        new_basket, removed_log, added_log = rotate_basket(scan_date, current, picks)

        if removed_log or added_log:
            history["rotations"].append({
                "date": scan_date,
                "n_removed": len(removed_log),
                "n_added": len(added_log),
                "removed": removed_log,
                "added": added_log,
            })
            log.info(f"Rotation: -{len(removed_log)} +{len(added_log)} positions")
        else:
            log.info("No rotations needed (basket unchanged)")

        # Mark all current positions
        new_basket, rets = mark_to_market(new_basket, scan_date)
        history["current_basket"] = new_basket

        # Weekly mark
        mark = add_weekly_mark(history, scan_date, rets)
        if mark:
            history["weekly_marks"].append(mark)

    history["summary"] = recompute_summary(history)
    history["updated_at"] = today

    # 5. Write
    gcs_write(HISTORY_PATH, history, dry_run=dry_run)

    # 6. Snapshot
    snapshot_path = f"{BASKET_SNAPSHOT_PREFIX}{today}_composite.json"
    gcs_write(snapshot_path, {
        "date": today,
        "scan_date": scan_date,
        "current_basket": history.get("current_basket"),
        "summary": history.get("summary"),
    }, dry_run=dry_run)

    # 7. Final log
    if history["current_basket"]:
        log.info(f"FINAL BASKET ({history['inception_date']} inception):")
        for p in history["current_basket"]:
            log.info(f"  {p['symbol']:<6} entry ${p['entry_price']:.2f} "
                     f"({p['entry_date']}) → ${p.get('last_price', 0):.2f} "
                     f"({p.get('return_pct', 0):+.2f}%)")
    if history["summary"]:
        s = history["summary"]
        log.info(f"SUMMARY: {s['weeks_tracked']} weeks, {s['n_rotations']} rotations, "
                 f"{s['n_positions_closed']} closed, "
                 f"open avg {s['open_avg_return_pct']:+.2f}%, "
                 f"cum alpha {s['cum_alpha_pp']:+.2f}pp")

    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not FMP_KEY:
        log.error("FMP_API_KEY not set; aborting")
        sys.exit(1)

    ok = run(dry_run=args.dry_run)
    sys.exit(0 if ok else 1)
