#!/usr/bin/env python3
"""
paper_strategy_runner_momentum.py 
==================================
MOMENTUM strategy: top-10 SP500 stocks by composite_momentum (v8 momentum
mode), equal-weight, weekly rotation.

Runs Friday 06:30 CET after the SP500 scan, alongside the BORING and
COMPOSITE runners. Same lifecycle as composite runner — the only difference
is the pick rule reads composite_momentum/signal_momentum instead of
composite/signal_v8.

Lifecycle:
  1. Read existing strategy_history_momentum.json from GCS
  2. Read latest_sp500.json from GCS
  3. Filter scan: signal_momentum != "DISQUALIFIED" (passed momentum gate)
  4. Sort by composite_momentum DESC, take top-10 -> target_basket

  IF no current basket (first run):
    - Open all picks at today's prices
    - Save inception SPY price

  IF current basket exists:
    - Close any current position not in target (record return)
    - Open any target position not currently held
    - Stays-in: no action
    - Append weekly_mark with basket vs SPY

  4. Recompute summary
  5. Write strategy_history_momentum.json

Output schema mirrors paper_strategy_runner_composite.py exactly so the
frontend Performance page can reuse StrategyKPICard with no changes.

Usage:
  export FMP_API_KEY=...
  python3 paper_strategy_runner_momentum.py [--dry-run]
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
log = logging.getLogger("momentum_runner")

# ─────────────────────────────────────────────────────────────────────────
FMP_KEY = os.environ.get("FMP_API_KEY", "")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")

STRATEGY_VERSION = "momentum-v1.0-2026-05-02"
TOP_N = 10

LATEST_SCAN_PATH = "scans/latest_sp500.json"
HISTORY_PATH = "performance/strategy_history_momentum.json"
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
        log.warning(f"GCS read {path} -> HTTP {r.status_code}")
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
        log.error(f"GCS write {path}: HTTP {r.status_code} -> {r.text[:200]}")
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
        "region": "momentum",
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
    """Sort scan by composite_momentum DESC, take top-N. Skip disqualified."""
    stocks = scan_data.get("stocks", []) if isinstance(scan_data, dict) else []
    if not stocks:
        log.error("Scan has no stocks")
        return []

    candidates = []
    for s in stocks:
        comp_mom = s.get("composite_momentum")
        if comp_mom is None: continue
        sig_mom = s.get("signal_momentum")
        if sig_mom == "DISQUALIFIED": continue
        price = s.get("price")
        if not price or price <= 0: continue
        candidates.append({
            "symbol": s.get("symbol", "").upper(),
            "score": float(comp_mom),
            "price": float(price),
            "piotroski": s.get("piotroski"),
            "signal": sig_mom,
        })

    if len(candidates) < TOP_N:
        log.warning(f"Only {len(candidates)} candidates passed momentum gate (need {TOP_N})")

    candidates.sort(key=lambda x: -x["score"])
    picks = candidates[:TOP_N]
    log.info(f"Top-{len(picks)} by composite_momentum: {[p['symbol'] for p in picks]}")
    log.info(f"  scores: {[round(p['score'], 3) for p in picks]}")
    return picks


# ─────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────
def open_first_basket(scan_date: str, picks: list[dict]) -> tuple[list, float]:
    spy = fmp_quote("SPY") or 0.0
    positions = []
    for p in picks:
        positions.append({
            "entry_date": scan_date,
            "composite_at_entry": p["score"],
            "piotroski_at_entry": p["piotroski"],
            "signal_at_entry": p["signal"],
            "last_price": p["price"],
            "last_marked": scan_date,
            "return_pct": 0.0,
        })
    return positions, spy


def rotate_basket(scan_date: str,
                  current_positions: list[dict],
                  picks: list[dict]) -> tuple[list, list, list]:
    target_syms = {p["symbol"] for p in picks}
    current_syms = {p["symbol"] for p in current_positions}

    to_remove = [p for p in current_positions if p["symbol"] not in target_syms]
    to_add_picks = [p for p in picks if p["symbol"] not in current_syms]
    keep = [p for p in current_positions if p["symbol"] in target_syms]

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
                     f"entry ${p['entry_price']:.2f} -> exit ${exit_price:.2f} "
                     f"({ret*100:+.2f}%, {days_held}d)")

    added_log = []
    new_positions = []
    for p in to_add_picks:
        new_positions.append({
            "symbol": p["symbol"],
            "entry_price": p["price"],
            "entry_date": scan_date,
            "composite_at_entry": p["score"],
            "piotroski_at_entry": p["piotroski"],
            "signal_at_entry": p["signal"],
            "last_price": p["price"],
            "last_marked": scan_date,
            "return_pct": 0.0,
        })
        added_log.append({
            "symbol": p["symbol"],
            "entry_price": round(p["price"], 4),
            "composite_at_entry": round(p["score"], 4),
        })
        log.info(f"  ROTATED IN   {p['symbol']:<6} entry ${p['price']:.2f}")

    new_basket = keep + new_positions
    return new_basket, removed_log, added_log


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


def add_weekly_mark(history: dict, scan_date: str, position_returns: list[float]) -> Optional[dict]:
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

    basket_avg_return = (sum(position_returns) / len(position_returns) * 100.0
                         if position_returns else 0.0)

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
             f"day {days_since}, n={len(position_returns)}")
    return mark


def recompute_summary(history: dict) -> Optional[dict]:
    rotations = history.get("rotations", [])
    closed_positions = []
    for r in rotations:
        for rem in r.get("removed", []):
            closed_positions.append(rem)

    current = history.get("current_basket", [])
    weekly_marks = history.get("weekly_marks", [])

    if closed_positions:
        realized_returns = [p["return_pct"] for p in closed_positions]
        realized_avg = sum(realized_returns) / len(realized_returns)
        realized_wins = sum(1 for r in realized_returns if r > 0)
        realized_win_rate = realized_wins / len(realized_returns)
    else:
        realized_avg = 0
        realized_win_rate = 0
        realized_wins = 0

    open_returns = [p.get("return_pct", 0) for p in current]
    open_avg = sum(open_returns) / len(open_returns) if open_returns else 0

    last_mark = weekly_marks[-1] if weekly_marks else None
    cum_alpha = last_mark["alpha_pp"] if last_mark else 0
    cum_basket_return = last_mark["basket_avg_return_pct"] if last_mark else 0
    cum_spy_return = last_mark["spy_return_pct"] if last_mark else 0

    inception = history.get("inception_date")
    if inception and last_mark:
        days = max(last_mark["days_since_inception"], 1)
        years = days / 365.25
        if years > 0.05:
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
    log.info(f"MOMENTUM runner starting {today}")
    log.info(f"  Strategy: {STRATEGY_VERSION}, top-{TOP_N} by composite_momentum, weekly rotation")

    history = gcs_read(HISTORY_PATH, empty_history())
    if not isinstance(history, dict) or "current_basket" not in history:
        log.warning("History malformed - resetting")
        history = empty_history()

    scan = gcs_read(LATEST_SCAN_PATH)
    if not scan:
        log.error(f"Could not read {LATEST_SCAN_PATH} from GCS - aborting")
        return False
    raw_scan_date = scan.get("scan_date") or scan.get("date") or today
    scan_date = raw_scan_date[:10]
    log.info(f"Scan loaded: {scan_date} (raw: {raw_scan_date}), "
             f"{len(scan.get('stocks', []))} stocks")

    picks = select_top_n(scan)
    if not picks:
        log.error("Cannot select picks - aborting")
        return False

    is_first_run = history.get("inception_date") is None

    if is_first_run:
        log.info("First run - opening initial basket")
        positions, spy_inception = open_first_basket(scan_date, picks)
        history["inception_date"] = scan_date
        history["spy_inception_price"] = spy_inception
        history["current_basket"] = positions
        positions, rets = mark_to_market(positions, scan_date)
        history["current_basket"] = positions
        mark = add_weekly_mark(history, scan_date, rets)
        if mark:
            history["weekly_marks"].append(mark)
    else:
        current = history.get("current_basket", [])
        log.info(f"Existing basket: {len(current)} positions")
        log.info(f"  Symbols: {[p['symbol'] for p in current]}")

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

        new_basket, rets = mark_to_market(new_basket, scan_date)
        history["current_basket"] = new_basket

        mark = add_weekly_mark(history, scan_date, rets)
        if mark:
            history["weekly_marks"].append(mark)

    history["summary"] = recompute_summary(history)
    history["updated_at"] = today

    gcs_write(HISTORY_PATH, history, dry_run=dry_run)

    snapshot_path = f"{BASKET_SNAPSHOT_PREFIX}{today}_momentum.json"
    gcs_write(snapshot_path, {
        "date": today,
        "scan_date": scan_date,
        "current_basket": history.get("current_basket"),
        "summary": history.get("summary"),
    }, dry_run=dry_run)

    if history["current_basket"]:
        log.info(f"FINAL BASKET ({history['inception_date']} inception):")
        for p in history["current_basket"]:
            log.info(f"  {p['symbol']:<6} entry ${p['entry_price']:.2f} "
                     f"({p['entry_date']}) -> ${p.get('last_price', 0):.2f} "
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
