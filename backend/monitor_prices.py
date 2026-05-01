#!/usr/bin/env python3
"""
monitor_prices.py — Daily price refresh
========================================
Runs Mon-Fri 22:00 CET (after US close). Refreshes `last_price` and
display-only return fields on every open position across:
  - portfolio/state.json
  - performance/strategy_history_boring.json
  - performance/strategy_history_composite.json
  - performance/strategy_history_momentum.json
  - performance/strategy_history_fa.json

Touches ONLY display/aggregate fields. Does NOT touch:
  - weekly_marks (runner only)
  - rotations (runner only)
  - inception_date / spy_inception_price (runner only)
  - realized stats (n_positions_closed, realized_avg, realized_win_rate)

For weekly-rotation strategies (composite/momentum/fa), recomputes:
  - current_basket[].last_price + return_pct + last_marked
  - summary.open_avg_return_pct
  - summary.cum_basket_return_pct  (mark-to-market vs spy_inception_price)
  - summary.cum_spy_return_pct
  - summary.cum_alpha_pp
  - summary.annualized_return_pct + annualized_alpha_pp
NOTE: cum_basket_return_pct here is "average open-position return since
inception" — the same calc the runner does in its weekly mark. Realized
positions (closed in rotations) are NOT reflected; they live in
realized_avg_return_pct which the runner owns.

For BORING (26w hold), refreshes:
  - open_basket.basket positions: NO last_price field exists in schema,
    so we add a daily_marks structure: open_basket.daily_last_marks[symbol]
    = {price, ts}. Frontend reads this if present, falls back to entry.
  - That keeps the existing schema untouched while adding fresh display.

For portfolio:
  - positions[].last_price + last_updated + pnl_pct (last - entry)/entry

Idempotent. Safe to rerun. Single FMP batch call for the unioned symbol set.

Usage:
  export FMP_API_KEY=...
  python3 monitor_prices.py [--dry-run]
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
log = logging.getLogger("monitor")

FMP_KEY = os.environ.get("FMP_API_KEY", "")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")
FMP_BASE = "https://financialmodelingprep.com/stable"

# All files we touch — list at top so it's clear at a glance
PORTFOLIO_PATH = "portfolio/state.json"
STRATEGY_PATHS = {
    "boring":    "performance/strategy_history_boring.json",
    "composite": "performance/strategy_history_composite.json",
    "momentum":  "performance/strategy_history_momentum.json",
    "fa":        "performance/strategy_history_fa.json",
}


# ─────────────────────────────────────────────────────────────────────────
# GCS helpers
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
# FMP price fetch (same pattern as runners, batched)
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
    # Fallback to single-quote for misses
    for s in symbols:
        if s not in out:
            p = fmp_quote(s)
            if p: out[s] = p
            time.sleep(0.05)
    return out


# ─────────────────────────────────────────────────────────────────────────
# Per-file refreshers
# ─────────────────────────────────────────────────────────────────────────
def collect_symbols_from_portfolio(state: Optional[dict]) -> set[str]:
    if not state: return set()
    positions = state.get("positions") or state.get("open") or []
    return {(p.get("symbol") or "").upper() for p in positions if p.get("symbol")}


def collect_symbols_from_strategy(history: Optional[dict], kind: str) -> set[str]:
    """kind in {boring, composite, momentum, fa}."""
    if not history: return set()
    if kind == "boring":
        ob = history.get("open_basket") or {}
        basket = ob.get("basket") or []
        return {(p.get("symbol") or "").upper() for p in basket if p.get("symbol")}
    # composite/momentum/fa
    basket = history.get("current_basket") or []
    return {(p.get("symbol") or "").upper() for p in basket if p.get("symbol")}


def refresh_portfolio(state: Optional[dict], quotes: dict[str, float], today: str) -> Optional[dict]:
    """Update portfolio/state.json open positions with last_price/pnl_pct."""
    if not state:
        return None
    positions = state.get("positions") or state.get("open") or []
    if not positions:
        log.info("[portfolio] no open positions")
        return state
    n_updated = 0
    for p in positions:
        sym = (p.get("symbol") or "").upper()
        if not sym:
            continue
        cur = quotes.get(sym)
        entry = p.get("entry_price") or p.get("entry") or 0
        if cur is None:
            continue
        try:
            entry_f = float(entry)
        except Exception:
            continue
        if entry_f <= 0:
            continue
        p["last_price"] = round(cur, 4)
        p["last_updated"] = today
        p["pnl_pct"] = round((cur - entry_f) / entry_f * 100, 4)
        n_updated += 1
    log.info(f"[portfolio] refreshed {n_updated}/{len(positions)} positions")
    state["last_monitor_run"] = today
    return state


def refresh_strategy_rotation(history: Optional[dict], quotes: dict[str, float],
                              today: str, kind: str) -> Optional[dict]:
    """Update composite/momentum/fa current_basket + recompute open-basket
    aggregates (Option A). Does NOT touch weekly_marks or rotations."""
    if not history:
        return None
    basket = history.get("current_basket") or []
    if not basket:
        log.info(f"[{kind}] empty basket — only updating last_monitor_run")
        history["last_monitor_run"] = today
        return history

    n_updated = 0
    rets: list[float] = []
    for p in basket:
        sym = (p.get("symbol") or "").upper()
        cur = quotes.get(sym)
        entry = p.get("entry_price") or 0
        if cur is None or entry <= 0:
            # Keep existing return_pct in computation if we can't refresh
            try:
                rets.append(float(p.get("return_pct") or 0) / 100.0)
            except Exception:
                pass
            continue
        ret = (cur - entry) / entry
        p["last_price"] = round(cur, 4)
        p["last_marked"] = today
        p["return_pct"] = round(ret * 100, 4)
        rets.append(ret)
        n_updated += 1
    log.info(f"[{kind}] refreshed {n_updated}/{len(basket)} basket positions")

    # Option A: recompute open-basket aggregates so KPI cards reflect today
    # SPY for cum_alpha denominator
    spy_now = quotes.get("SPY")
    spy_inception = history.get("spy_inception_price") or 0
    if spy_now and spy_inception > 0:
        cum_spy_pct = (spy_now - spy_inception) / spy_inception * 100.0
    else:
        cum_spy_pct = (history.get("summary") or {}).get("cum_spy_return_pct") or 0

    open_avg = (sum(rets) / len(rets) * 100.0) if rets else 0.0
    cum_basket_pct = open_avg  # daily mark = open_avg, same as runner does
    cum_alpha_pp = cum_basket_pct - cum_spy_pct

    # Annualization (only if we have inception date)
    inception = history.get("inception_date")
    ann_strategy = ann_alpha = 0.0
    if inception:
        try:
            days = max((dt.date.fromisoformat(today) -
                        dt.date.fromisoformat(inception)).days, 1)
            years = days / 365.25
            if years > 0.05:
                ann_strategy = ((1 + cum_basket_pct / 100) ** (1 / years) - 1) * 100
                ann_spy = ((1 + cum_spy_pct / 100) ** (1 / years) - 1) * 100
                ann_alpha = ann_strategy - ann_spy
        except Exception:
            pass

    summary = history.get("summary") or {}
    summary["open_avg_return_pct"] = round(open_avg, 4)
    summary["cum_basket_return_pct"] = round(cum_basket_pct, 4)
    summary["cum_spy_return_pct"] = round(cum_spy_pct, 4)
    summary["cum_alpha_pp"] = round(cum_alpha_pp, 4)
    summary["annualized_return_pct"] = round(ann_strategy, 4)
    summary["annualized_alpha_pp"] = round(ann_alpha, 4)
    history["summary"] = summary
    history["last_monitor_run"] = today

    log.info(f"[{kind}] aggregates: open_avg {open_avg:+.2f}%, "
             f"SPY {cum_spy_pct:+.2f}%, alpha {cum_alpha_pp:+.2f}pp")
    return history


def refresh_strategy_boring(history: Optional[dict], quotes: dict[str, float],
                            today: str) -> Optional[dict]:
    """BORING is 26w hold. Add a daily_last_marks side-dict so the
    schema isn't disturbed (frontend can adopt this when convenient).
    Also recompute open_basket.weekly_marks LAST entry's return_pct
    in-place so the KPI card sees today's mark — does NOT append a new
    weekly_mark (that's the runner's job)."""
    if not history:
        return None
    ob = history.get("open_basket")
    if not ob or not ob.get("basket"):
        log.info("[boring] no open basket")
        history["last_monitor_run"] = today
        return history

    basket = ob["basket"]
    rets: list[float] = []
    daily_marks: dict[str, dict] = {}
    for p in basket:
        sym = (p.get("symbol") or "").upper()
        cur = quotes.get(sym)
        entry = p.get("entry_price") or 0
        if cur is None or entry <= 0:
            continue
        ret = (cur - entry) / entry
        rets.append(ret)
        daily_marks[sym] = {"price": round(cur, 4), "return_pct": round(ret * 100, 4),
                            "ts": today}
    ob["daily_last_marks"] = daily_marks
    log.info(f"[boring] refreshed {len(daily_marks)}/{len(basket)} positions")

    # Recompute the LAST weekly_mark (display-only) — but only if it's
    # today's date OR we add a "today" interim mark. To avoid polluting
    # weekly_marks (runner-owned), we instead store a separate
    # `today_interim_mark` on open_basket. Frontend can prefer this if
    # present and newer than the latest weekly_mark.
    spy_now = quotes.get("SPY")
    spy_entry = ob.get("spy_entry_price") or 0
    spy_pct = (spy_now - spy_entry) / spy_entry * 100.0 if (spy_now and spy_entry > 0) else 0.0
    basket_pct = (sum(rets) / len(rets) * 100.0) if rets else 0.0

    try:
        days_held = (dt.date.fromisoformat(today) -
                     dt.date.fromisoformat(ob["inception_date"])).days
    except Exception:
        days_held = 0

    ob["today_interim_mark"] = {
        "date": today,
        "basket_return_pct": round(basket_pct, 4),
        "spy_return_pct": round(spy_pct, 4),
        "alpha_pp": round(basket_pct - spy_pct, 4),
        "spy_price": round(spy_now, 4) if spy_now else None,
        "days_held": days_held,
        "n_priced": len(rets),
        "_note": "Interim daily mark from monitor_prices.py — runner owns weekly_marks",
    }
    log.info(f"[boring] interim mark: basket {basket_pct:+.2f}%, "
             f"SPY {spy_pct:+.2f}%, alpha {basket_pct - spy_pct:+.2f}pp")

    history["last_monitor_run"] = today
    return history


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def run(dry_run: bool = False):
    today = dt.date.today().isoformat()
    log.info(f"Monitor starting — {today}, dry_run={dry_run}")

    # Read all 5 files
    portfolio = gcs_read(PORTFOLIO_PATH)
    histories = {kind: gcs_read(path) for kind, path in STRATEGY_PATHS.items()}

    # Collect symbol union
    symbols: set[str] = set()
    symbols |= collect_symbols_from_portfolio(portfolio)
    for kind, h in histories.items():
        symbols |= collect_symbols_from_strategy(h, kind)
    symbols.add("SPY")  # benchmark for strategy aggregates

    log.info(f"Unioned symbol universe: {len(symbols)} unique tickers")
    if not symbols:
        log.warning("No symbols to refresh — nothing to do")
        return True

    # Single batch fetch
    quotes = fmp_quote_batch(sorted(symbols))
    log.info(f"Fetched {len(quotes)}/{len(symbols)} prices from FMP")
    if "SPY" not in quotes:
        log.warning("SPY price fetch failed — strategy aggregates may be stale")

    # Refresh + write each file
    if portfolio is not None:
        portfolio = refresh_portfolio(portfolio, quotes, today)
        if portfolio is not None:
            gcs_write(PORTFOLIO_PATH, portfolio, dry_run=dry_run)

    for kind, history in histories.items():
        if history is None:
            log.info(f"[{kind}] no history file — skipping")
            continue
        if kind == "boring":
            updated = refresh_strategy_boring(history, quotes, today)
        else:
            updated = refresh_strategy_rotation(history, quotes, today, kind)
        if updated is not None:
            gcs_write(STRATEGY_PATHS[kind], updated, dry_run=dry_run)

    log.info("Monitor complete")
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
