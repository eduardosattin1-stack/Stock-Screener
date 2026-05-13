#!/usr/bin/env python3 
"""
monitor_prices.py — Daily price refresh + portfolio alpha + composite tracking
====================================================================
Runs Mon-Fri 22:00 CET (after US close). Refreshes display fields on:
  - portfolio/state.json
  - performance/strategy_history_boring.json
  - performance/strategy_history_composite.json
  - performance/strategy_history_momentum.json
  - performance/strategy_history_fa.json

Per-position fields written to portfolio/state.json:
  - last_price, last_updated, pnl_pct  (existing)
  - peak_price                          (running max from daily samples)
  - drawdown_from_peak_pct              (always ≤ 0)
  - spy_price_at_entry                  (ONE-TIME backfill via FMP historical)
  - alpha_vs_spy_pct                    (pnl_pct − SPY_return_since_entry)
  - last_composite                      (from latest scan snapshot)
  - entry_composite                     (backfilled from scan if was 0)
  - composite_momentum                  (v8 momentum composite)
  - composite_fallen_angel              (v8 fallen angel composite)
  - compounder_score_us                 (compounder US cohort)
  - compounder_score_global             (compounder global cohort)
  - signal_momentum / signal_compounder_us / signal_compounder_global
  - smart_money_score                   (LTR-derived score)

Strategy histories — composite/momentum/fa: refreshes current_basket prices
and recomputes summary aggregates. BORING uses side-channel daily_last_marks
+ today_interim_mark.

NEVER touches: weekly_marks, rotations, realized stats, inception_date.
Idempotent. Safe to rerun.

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

PORTFOLIO_PATH = "portfolio/state.json"
STRATEGY_PATHS = {
    "compounder_us":     "performance/strategy_history_compounder_us.json",
    "compounder_global": "performance/strategy_history_compounder_global.json",
    "momentum":          "performance/strategy_history_momentum.json",
    "fa":                "performance/strategy_history_fa.json",
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


def fmp_historical_close(symbol: str, date_str: str) -> Optional[float]:
    """Fetch closing price on date_str (or nearest forward trading day if
    date_str fell on weekend/holiday). Used ONLY for one-time backfill of
    spy_price_at_entry. Idempotent — once stored, never refetched."""
    if not FMP_KEY:
        return None
    try:
        # 7-day window from entry_date forward to handle weekends & holidays
        end = (dt.date.fromisoformat(date_str) + dt.timedelta(days=7)).isoformat()
        r = requests.get(
            f"{FMP_BASE}/historical-price-eod/light",
            params={"symbol": symbol, "from": date_str, "to": end, "apikey": FMP_KEY},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                # FMP returns desc by date typically — normalize to asc
                rows = sorted(data, key=lambda x: x.get("date", ""))
                # First row at-or-after our date with a valid close
                for row in rows:
                    rd = (row.get("date") or "")[:10]
                    px = row.get("price") or row.get("close")
                    if rd >= date_str and px:
                        return float(px)
                # Fallback: any valid close in window
                for row in rows:
                    px = row.get("price") or row.get("close")
                    if px:
                        return float(px)
    except Exception as e:
        log.warning(f"FMP historical {symbol} {date_str}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────
# Scan-snapshot composite lookup
# ─────────────────────────────────────────────────────────────────────────
def _load_scan_composites() -> dict[str, dict]:
    """Read latest_{region}.json from GCS and build {SYMBOL: scores_dict}.

    Returns composite, composite_momentum, composite_fallen_angel,
    compounder_score_us, compounder_score_global, signal_momentum,
    signal_compounder_us, signal_compounder_global, factors_v8 for each symbol.
    Later regions overwrite earlier on collision (rare).
    """
    out: dict[str, dict] = {}
    for region in ("global", "nasdaq", "sp500"):
        data = gcs_read(f"scans/latest_{region}.json")
        if not data:
            log.info(f"[composites] scans/latest_{region}.json not found")
            continue
        stocks = data.get("stocks") if isinstance(data, dict) else data
        if not isinstance(stocks, list):
            continue
        n = 0
        for s in stocks:
            if not isinstance(s, dict):
                continue
            sym = s.get("symbol")
            if not sym:
                continue
            out[str(sym).upper()] = {
                "composite": s.get("composite"),
                "composite_momentum": s.get("composite_momentum"),
                "composite_fallen_angel": s.get("composite_fallen_angel"),
                "compounder_score_us": s.get("compounder_score_us"),
                "compounder_score_global": s.get("compounder_score_global"),
                "signal_momentum": s.get("signal_momentum"),
                "signal_compounder_us": s.get("signal_compounder_us"),
                "signal_compounder_global": s.get("signal_compounder_global"),
                "factors_v8": s.get("factors_v8"),
                "smart_money_score": s.get("smart_money_score"),
                "_region": region,
            }
            n += 1
        log.info(f"[composites] loaded {n} composites from scans/latest_{region}.json")
    return out


# ─────────────────────────────────────────────────────────────────────────
# Per-file refreshers
# ─────────────────────────────────────────────────────────────────────────
def collect_symbols_from_portfolio(state: Optional[dict]) -> set[str]:
    if not state: return set()
    positions = state.get("positions") or state.get("open") or []
    return {(p.get("symbol") or "").upper() for p in positions if p.get("symbol")}


def collect_symbols_from_strategy(history: Optional[dict], kind: str) -> set[str]:
    if not history: return set()
    if kind == "boring":
        ob = history.get("open_basket") or {}
        basket = ob.get("basket") or []
        return {(p.get("symbol") or "").upper() for p in basket if p.get("symbol")}
    basket = history.get("current_basket") or []
    return {(p.get("symbol") or "").upper() for p in basket if p.get("symbol")}


def refresh_portfolio(state: Optional[dict], quotes: dict[str, float],
                      today: str, scan_lookup: dict[str, dict] | None = None) -> Optional[dict]:
    """Per-position fields:
       - last_price, last_updated, pnl_pct       (always)
       - peak_price, drawdown_from_peak_pct      (always; peak grows over time)
       - spy_price_at_entry                      (lazy backfill, one-time)
       - alpha_vs_spy_pct                        (recomputed daily)
       - last_composite, composite_momentum, etc (from scan snapshots)
    """
    if not state:
        return None
    positions = state.get("positions") or state.get("open") or []
    if not positions:
        log.info("[portfolio] no open positions")
        state["last_monitor_run"] = today
        return state

    scan_lookup = scan_lookup or {}
    spy_now = quotes.get("SPY")
    n_updated = 0
    n_alpha_computed = 0
    n_spy_backfilled = 0
    n_composite_stamped = 0

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

        # ── 1. Existing: price + pnl ─────────────────────────────────────
        p["last_price"] = round(cur, 4)
        p["last_updated"] = today
        p["pnl_pct"] = round((cur - entry_f) / entry_f * 100, 4)

        # ── 2. Peak & drawdown ───────────────────────────────────────────
        prev_peak = p.get("peak_price")
        if not isinstance(prev_peak, (int, float)) or prev_peak <= 0:
            prev_peak = max(entry_f, cur)
        new_peak = max(float(prev_peak), cur)
        p["peak_price"] = round(new_peak, 4)
        if new_peak > 0:
            p["drawdown_from_peak_pct"] = round((cur - new_peak) / new_peak * 100, 4)
        else:
            p["drawdown_from_peak_pct"] = 0.0

        # ── 3. spy_price_at_entry — ONE-TIME backfill ────────────────────
        spy_at_entry = p.get("spy_price_at_entry")
        if not isinstance(spy_at_entry, (int, float)) or spy_at_entry <= 0:
            entry_date = (p.get("entry_date") or "")[:10]
            if entry_date:
                fetched = fmp_historical_close("SPY", entry_date)
                if fetched and fetched > 0:
                    p["spy_price_at_entry"] = round(fetched, 4)
                    spy_at_entry = fetched
                    n_spy_backfilled += 1
                    log.info(f"[portfolio] backfilled spy_price_at_entry for {sym}: ${fetched:.2f} on {entry_date}")

        # ── 4. alpha_vs_spy_pct ──────────────────────────────────────────
        if (isinstance(spy_at_entry, (int, float)) and spy_at_entry > 0
                and spy_now and spy_now > 0):
            spy_return_pct = (spy_now - float(spy_at_entry)) / float(spy_at_entry) * 100.0
            p["alpha_vs_spy_pct"] = round(p["pnl_pct"] - spy_return_pct, 4)
            n_alpha_computed += 1

        # ── 5. Composite scores from scan snapshots ──────────────────────
        # Stamp all strategy composites so the portfolio page can display
        # the correct score regardless of active mode. Also backfill
        # entry_composite if it was 0 (positions added after v8 cleanup).
        snap = scan_lookup.get(sym)
        if snap:
            comp = snap.get("composite")
            if isinstance(comp, (int, float)) and comp > 0:
                p["last_composite"] = round(float(comp), 4)
            # Backfill entry_composite if missing or 0
            if not p.get("entry_composite"):
                if isinstance(comp, (int, float)) and comp > 0:
                    p["entry_composite"] = round(float(comp), 4)
                    log.info(f"[portfolio] backfilled entry_composite for {sym}: {comp:.3f}")
            # Strategy-specific composites
            for field in ("composite_momentum", "composite_fallen_angel",
                          "compounder_score_us", "compounder_score_global",
                          "signal_momentum", "signal_compounder_us",
                          "signal_compounder_global", "smart_money_score"):
                val = snap.get(field)
                if val is not None:
                    p[field] = val
            n_composite_stamped += 1

        n_updated += 1

    log.info(f"[portfolio] refreshed {n_updated}/{len(positions)} positions "
             f"(alpha {n_alpha_computed}, spy backfill {n_spy_backfilled}, "
             f"composites {n_composite_stamped})")
    state["last_monitor_run"] = today
    return state


def refresh_strategy_rotation(history: Optional[dict], quotes: dict[str, float],
                              today: str, kind: str) -> Optional[dict]:
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

    spy_now = quotes.get("SPY")
    spy_inception = history.get("spy_inception_price") or 0
    if spy_now and spy_inception > 0:
        cum_spy_pct = (spy_now - spy_inception) / spy_inception * 100.0
    else:
        cum_spy_pct = (history.get("summary") or {}).get("cum_spy_return_pct") or 0

    open_avg = (sum(rets) / len(rets) * 100.0) if rets else 0.0
    cum_basket_pct = open_avg
    cum_alpha_pp = cum_basket_pct - cum_spy_pct

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


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def run(dry_run: bool = False):
    today = dt.date.today().isoformat()
    log.info(f"Monitor starting — {today}, dry_run={dry_run}")

    portfolio = gcs_read(PORTFOLIO_PATH)
    histories = {kind: gcs_read(path) for kind, path in STRATEGY_PATHS.items()}

    symbols: set[str] = set()
    symbols |= collect_symbols_from_portfolio(portfolio)
    for kind, h in histories.items():
        symbols |= collect_symbols_from_strategy(h, kind)
    symbols.add("SPY")

    log.info(f"Unioned symbol universe: {len(symbols)} unique tickers")
    if not symbols:
        log.warning("No symbols to refresh")
        return True

    quotes = fmp_quote_batch(sorted(symbols))
    log.info(f"Fetched {len(quotes)}/{len(symbols)} prices from FMP")
    if "SPY" not in quotes:
        log.warning("SPY price fetch failed — alpha & strategy aggregates may be stale")

    scan_lookup = _load_scan_composites()
    log.info(f"Scan composite lookup: {len(scan_lookup)} symbols indexed")

    if portfolio is not None:
        portfolio = refresh_portfolio(portfolio, quotes, today, scan_lookup=scan_lookup)
        if portfolio is not None:
            gcs_write(PORTFOLIO_PATH, portfolio, dry_run=dry_run)

    for kind, history in histories.items():
        if history is None:
            log.info(f"[{kind}] no history file — skipping")
            continue
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
