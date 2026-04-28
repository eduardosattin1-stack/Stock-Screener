#!/usr/bin/env python3
"""
paper_strategy_runner.py
=========================
BORING strategy: top-10 SP500.QUALITY_PIO_7 stocks ranked by ps_ratio ascending,
26-week hold, equal-weighted, weekly mid-hold mark-to-market vs SPY.

Runs Friday 06:30 CET (after the SP500 scan completes ~06:57 CET — wait,
actually after, so schedule for 07:00 CET to be safe). Walks the lifecycle:

  1. Read existing strategy_history_boring.json from GCS
  2. Read latest_sp500.json from GCS (this Friday's scan output)
  3. Pull SPY close for today and (if needed) entry date prices

  IF no open basket (first run, or last basket just closed):
    - Filter scan: piotroski >= 7, ps_ratio not null
    - Sort by ps_ratio ascending, take top 10
    - Open basket: record entry prices, scan_date as inception
    - Append empty weekly_marks list

  IF open basket exists AND today < inception + 26 weeks:
    - Fetch current FMP prices for the 10 held symbols
    - Fetch current SPY price
    - Append weekly mark: {date, basket_value, spy_value, alpha_pp, days_held}

  IF open basket exists AND today >= inception + 26 weeks:
    - Fetch exit prices for held positions + SPY
    - Compute basket_return, spy_return, alpha
    - Append closed cycle to weeks[]
    - Open NEW basket using this scan's data
    - Reset weekly_marks for new basket

  4. Recompute summary stats
  5. Write strategy_history_boring.json back to GCS
  6. Write paper_basket_{date}.json snapshot for audit trail

Output schema mirrors existing strategy_history_{region}.json so the
frontend Performance page can swap GCS source paths and reuse rendering.

Usage:
  export FMP_API_KEY=...
  export GCS_BUCKET=screener-signals-carbonbridge
  python3 paper_strategy_runner.py [--dry-run] [--force-rebalance]
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
log = logging.getLogger("boring_runner")

# ─────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────
FMP_KEY = os.environ.get("FMP_API_KEY", "")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")

# Strategy constants — FROZEN FOR PAPER TRACK 2026-04-28
STRATEGY_VERSION = "boring-v1.0-2026-04-28"
PIOTROSKI_MIN = 7
TOP_N = 10
HOLD_WEEKS = 26
HOLD_DAYS = HOLD_WEEKS * 7  # 182 days exact

# GCS paths
LATEST_SCAN_PATH = "scans/latest_sp500.json"
HISTORY_PATH = "performance/strategy_history_boring.json"
BASKET_SNAPSHOT_PREFIX = "performance/baskets/"

FMP_BASE = "https://financialmodelingprep.com/stable"


# ─────────────────────────────────────────────────────────────────────────
# GCS read/write helpers (public-read bucket; writes via auth library)
# ─────────────────────────────────────────────────────────────────────────
def gcs_read(path: str, default=None):
    """Public read."""
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
    """Authenticated write via google-cloud-storage."""
    if dry_run:
        log.info(f"[DRY-RUN] Would write {path} ({len(json.dumps(data))} bytes)")
        return True
    try:
        from google.cloud import storage  # type: ignore
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(path)
        blob.cache_control = "no-cache, max-age=0"
        blob.upload_from_string(
            json.dumps(data, default=str, indent=2),
            content_type="application/json",
        )
        log.info(f"Wrote gs://{GCS_BUCKET}/{path}")
        return True
    except Exception as e:
        log.error(f"GCS write {path} failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────
# FMP price fetcher
# ─────────────────────────────────────────────────────────────────────────
def fmp_quote(symbol: str) -> Optional[float]:
    """Latest price."""
    if not FMP_KEY:
        log.error("FMP_API_KEY not set")
        return None
    try:
        r = requests.get(f"{FMP_BASE}/quote-short",
                         params={"symbol": symbol, "apikey": FMP_KEY},
                         timeout=15)
        if r.status_code != 200: return None
        d = r.json()
        if isinstance(d, list) and d and d[0].get("price"):
            return float(d[0]["price"])
    except Exception as e:
        log.warning(f"FMP quote-short {symbol}: {e}")
    return None


def fmp_quote_batch(symbols: list[str]) -> dict[str, float]:
    """Batch quote. Returns {sym: price}, missing = absent."""
    if not symbols: return {}
    out: dict[str, float] = {}
    # Batch in chunks of 25 (FMP limit varies; conservative)
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
    # Fill missing via single quote
    for s in symbols:
        if s not in out:
            p = fmp_quote(s)
            if p: out[s] = p
            time.sleep(0.05)
    return out


def fmp_ratios_ttm(symbols: list[str]) -> dict[str, float]:
    """Fetch priceToSalesRatioTTM for each symbol via /ratios-ttm.
    The scan output does NOT include ps_ratio, so the runner computes it
    on the fly for the Pio≥7 candidate universe. ~290 calls per Friday.
    Returns {sym: ps_ratio}.
    """
    out: dict[str, float] = {}
    n = len(symbols)
    if n == 0: return out
    log.info(f"Fetching priceToSalesRatioTTM for {n} candidates...")
    for i, sym in enumerate(symbols):
        try:
            r = requests.get(f"{FMP_BASE}/ratios-ttm",
                             params={"symbol": sym, "apikey": FMP_KEY},
                             timeout=15)
            if r.status_code == 200:
                d = r.json()
                if isinstance(d, list) and d:
                    ps = d[0].get("priceToSalesRatioTTM")
                    if ps is not None and ps > 0:
                        out[sym] = float(ps)
        except Exception as e:
            log.warning(f"ratios-ttm {sym}: {e}")
        if (i + 1) % 50 == 0 or i == n - 1:
            log.info(f"  ratios-ttm progress: {i+1}/{n} ({len(out)} valid)")
        time.sleep(0.04)
    return out


def fmp_price_on(symbol: str, date_iso: str) -> Optional[float]:
    """Closing price on or just after a specific date (next trading day)."""
    try:
        target = dt.date.fromisoformat(date_iso)
        end = (target + dt.timedelta(days=10)).isoformat()
        r = requests.get(f"{FMP_BASE}/historical-price-eod/light",
                         params={"symbol": symbol, "from": date_iso, "to": end,
                                 "apikey": FMP_KEY},
                         timeout=15)
        if r.status_code != 200: return None
        d = r.json()
        if not isinstance(d, list) or not d: return None
        # FMP returns newest first; sort and pick first >= target
        d.sort(key=lambda x: x.get("date", ""))
        for row in d:
            if row.get("date", "") >= date_iso and row.get("price"):
                return float(row["price"])
    except Exception as e:
        log.warning(f"price_on {symbol} {date_iso}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────
# Schema helpers
# ─────────────────────────────────────────────────────────────────────────
def empty_history() -> dict:
    return {
        "region": "boring",
        "strategy_version": STRATEGY_VERSION,
        "inception_date": None,
        "open_basket": None,
        "weeks": [],
        "summary": None,
        "updated_at": None,
    }


def select_basket(scan_data: dict) -> list[dict]:
    """Filter scan stocks → top-10 by ps_ratio within Pio≥7.

    The scan output does NOT include ps_ratio (only piotroski). So we:
      1. Filter scan to candidates with piotroski >= 7
      2. Fetch ps_ratio (priceToSalesRatioTTM) from FMP for those candidates
      3. Sort by ps_ratio ascending, take top 10
    """
    stocks = scan_data.get("stocks", []) if isinstance(scan_data, dict) else []
    if not stocks:
        log.error("Scan has no stocks")
        return []

    # Step 1: Pio≥7 candidates from the scan
    candidates_raw = []
    for s in stocks:
        # In live scans, piotroski is at top-level (verified 2026-04-28)
        # In factor_lab data, it's at factors.piotroski
        pio = s.get("piotroski") or (s.get("factors") or {}).get("piotroski")
        if pio is None or pio < PIOTROSKI_MIN:
            continue
        price = s.get("price")
        if not price or price <= 0:
            continue
        candidates_raw.append({
            "symbol": s.get("symbol", "").upper(),
            "piotroski": int(pio),
            "price": float(price),
        })

    log.info(f"Pio≥{PIOTROSKI_MIN} candidates from scan: {len(candidates_raw)}")
    if len(candidates_raw) < TOP_N:
        log.error(f"Not enough Pio≥{PIOTROSKI_MIN} stocks (got {len(candidates_raw)}, "
                  f"need {TOP_N})")
        return []

    # Step 2: Fetch ps_ratio for all candidates
    syms = [c["symbol"] for c in candidates_raw]
    ps_map = fmp_ratios_ttm(syms)
    log.info(f"  ps_ratio coverage: {len(ps_map)}/{len(syms)} candidates have ps_ratio")

    # Step 3: Attach ps_ratio, drop those without
    qualifying = []
    for c in candidates_raw:
        ps = ps_map.get(c["symbol"])
        if ps is None or ps <= 0:
            continue
        qualifying.append({
            **c,
            "ps_ratio": ps,
        })

    if len(qualifying) < TOP_N:
        log.error(f"Not enough stocks with ps_ratio (got {len(qualifying)}, "
                  f"need {TOP_N})")
        return []

    # Step 4: Sort ascending, take top 10
    qualifying.sort(key=lambda x: x["ps_ratio"])
    basket = qualifying[:TOP_N]

    log.info(f"Selected basket: {[b['symbol'] for b in basket]}")
    log.info(f"  ps_ratios: {[round(b['ps_ratio'], 2) for b in basket]}")
    log.info(f"  piotroskis: {[b['piotroski'] for b in basket]}")
    return basket


def open_new_basket(scan_date: str, picks: list[dict]) -> dict:
    """Build the open_basket structure with entry prices."""
    spy_entry = fmp_quote("SPY")
    if not spy_entry:
        log.error("Failed to fetch SPY entry price")
        spy_entry = 0.0  # will not crash but alpha will be bogus until SPY fetches OK

    # Normalize: scan_date may be "2026-04-26" or "2026-04-26T06:13:33.188660"
    scan_date_clean = scan_date[:10]

    return {
        "scan_date": scan_date_clean,
        "inception_date": scan_date_clean,
        "scheduled_exit_date": (
            dt.date.fromisoformat(scan_date_clean) + dt.timedelta(days=HOLD_DAYS)
        ).isoformat(),
        "spy_entry_price": spy_entry,
        "basket": [
            {
                "symbol": p["symbol"],
                "entry_price": p["price"],
                "ps_ratio_at_entry": p["ps_ratio"],
                "piotroski_at_entry": p["piotroski"],
            }
            for p in picks
        ],
        "weekly_marks": [],
    }


def add_weekly_mark(open_basket: dict, today: str) -> Optional[dict]:
    """Mark-to-market the open basket vs SPY. Append to weekly_marks."""
    if not open_basket: return None

    syms = [b["symbol"] for b in open_basket["basket"]]
    quotes = fmp_quote_batch(syms)
    if not quotes:
        log.error("Could not fetch any quotes for mark-to-market")
        return None

    # Equal-weighted basket return
    rets = []
    for b in open_basket["basket"]:
        sym = b["symbol"]; entry = b["entry_price"]
        cur = quotes.get(sym)
        if cur and entry > 0:
            rets.append((cur - entry) / entry)
    if not rets:
        log.error("No prices fetched")
        return None

    basket_return_pct = (sum(rets) / len(rets)) * 100.0

    # SPY return since entry
    spy_now = fmp_quote("SPY")
    spy_entry = open_basket.get("spy_entry_price") or 0
    if spy_now and spy_entry > 0:
        spy_return_pct = (spy_now - spy_entry) / spy_entry * 100.0
    else:
        spy_return_pct = 0.0
        spy_now = 0.0

    inception = dt.date.fromisoformat(open_basket["inception_date"])
    days_held = (dt.date.fromisoformat(today) - inception).days

    mark = {
        "date": today,
        "basket_return_pct": round(basket_return_pct, 4),
        "spy_return_pct": round(spy_return_pct, 4),
        "alpha_pp": round(basket_return_pct - spy_return_pct, 4),
        "spy_price": round(spy_now, 4),
        "days_held": days_held,
        "n_priced": len(rets),
    }
    log.info(f"Weekly mark @{today}: basket {basket_return_pct:+.2f}% / "
             f"SPY {spy_return_pct:+.2f}% / alpha {mark['alpha_pp']:+.2f}pp / "
             f"day {days_held}/{HOLD_DAYS}")
    return mark


def close_basket(open_basket: dict, exit_date: str) -> dict:
    """Compute final closed-cycle entry per StrategyWeekClosed schema."""
    syms = [b["symbol"] for b in open_basket["basket"]]
    quotes = fmp_quote_batch(syms)

    positions = []
    rets = []
    for b in open_basket["basket"]:
        sym = b["symbol"]; entry = b["entry_price"]
        exit_p = quotes.get(sym)
        if exit_p and entry > 0:
            r = (exit_p - entry) / entry
            positions.append({
                "symbol": sym,
                "entry": round(entry, 4),
                "exit": round(exit_p, 4),
                "return_pct": round(r * 100, 4),
            })
            rets.append(r)
        else:
            positions.append({
                "symbol": sym,
                "entry": round(entry, 4),
                "exit": None,
                "return_pct": None,
            })

    basket_return = (sum(rets) / len(rets)) * 100.0 if rets else 0.0

    spy_exit = fmp_quote("SPY") or 0.0
    spy_entry = open_basket.get("spy_entry_price") or 0
    spy_return = (spy_exit - spy_entry) / spy_entry * 100.0 if spy_entry > 0 else 0.0

    return {
        "entry_date": open_basket["inception_date"],
        "exit_date": exit_date,
        "n_positions": len(positions),
        "basket_return_pct": round(basket_return, 4),
        "spy_return_pct": round(spy_return, 4),
        "alpha_pp": round(basket_return - spy_return, 4),
        "spy_entry_price": round(open_basket.get("spy_entry_price") or 0, 4),
        "spy_exit_price": round(spy_exit, 4),
        "positions": positions,
    }


def recompute_summary(history: dict) -> Optional[dict]:
    """Recompute summary stats from closed weeks."""
    weeks = history.get("weeks", [])
    if not weeks:
        return None

    # Cumulative compounding
    cum_strategy = 1.0
    cum_spy = 1.0
    alphas = []
    for w in weeks:
        cum_strategy *= 1 + (w["basket_return_pct"] / 100.0)
        cum_spy *= 1 + (w["spy_return_pct"] / 100.0)
        alphas.append(w["alpha_pp"])

    inception = history.get("inception_date")
    today = dt.date.today()
    if inception:
        years = max((today - dt.date.fromisoformat(inception)).days / 365.25, 0.001)
        ann_return = (cum_strategy ** (1/years) - 1) * 100.0
        ann_spy = (cum_spy ** (1/years) - 1) * 100.0
        ann_alpha = ann_return - ann_spy
    else:
        ann_return = ann_spy = ann_alpha = 0.0

    pos_alpha = sum(1 for a in alphas if a > 0)
    win_rate = pos_alpha / len(alphas) if alphas else 0.0

    return {
        "weeks_closed": len(weeks),
        "cum_strategy_return_pct": round((cum_strategy - 1) * 100, 4),
        "cum_spy_return_pct": round((cum_spy - 1) * 100, 4),
        "cum_alpha_pp": round((cum_strategy - cum_spy) * 100, 4),
        "annualized_return_pct": round(ann_return, 4),
        "annualized_alpha_pp": round(ann_alpha, 4),
        "weeks_positive_alpha": pos_alpha,
        "win_rate": round(win_rate, 4),
        "best_week_alpha_pp": round(max(alphas), 4),
        "worst_week_alpha_pp": round(min(alphas), 4),
    }


# ─────────────────────────────────────────────────────────────────────────
# Main lifecycle
# ─────────────────────────────────────────────────────────────────────────
def run(dry_run: bool = False, force_rebalance: bool = False):
    today = dt.date.today().isoformat()
    log.info(f"BORING runner starting {today}")
    log.info(f"  Strategy: {STRATEGY_VERSION}, Pio>={PIOTROSKI_MIN}, "
             f"top-{TOP_N} by ps_ratio, hold {HOLD_WEEKS}w")

    # 1. Read state
    history = gcs_read(HISTORY_PATH, empty_history())
    if not isinstance(history, dict) or "weeks" not in history:
        log.warning("History malformed — resetting")
        history = empty_history()

    # 2. Read this week's scan
    scan = gcs_read(LATEST_SCAN_PATH)
    if not scan:
        log.error(f"Could not read {LATEST_SCAN_PATH} from GCS — aborting")
        return False
    raw_scan_date = scan.get("scan_date") or scan.get("date") or today
    # Normalize ISO datetime ("2026-04-26T06:13:33.188660") to date ("2026-04-26")
    scan_date = raw_scan_date[:10]
    log.info(f"Scan loaded: {scan_date} (raw: {raw_scan_date}), "
             f"{len(scan.get('stocks', []))} stocks")

    # 3. Determine action
    open_basket = history.get("open_basket")
    action = "noop"

    if not open_basket:
        action = "open_first"
    else:
        inception = dt.date.fromisoformat(open_basket["inception_date"])
        days_held = (dt.date.today() - inception).days
        if days_held >= HOLD_DAYS or force_rebalance:
            action = "close_and_open"
        else:
            action = "weekly_mark"

    log.info(f"Action: {action}")

    # 4. Execute
    if action == "open_first":
        picks = select_basket(scan)
        if not picks:
            log.error("Cannot open basket — aborting")
            return False
        history["inception_date"] = scan_date
        history["open_basket"] = open_new_basket(scan_date, picks)

    elif action == "weekly_mark":
        mark = add_weekly_mark(history["open_basket"], today)
        if mark:
            history["open_basket"]["weekly_marks"].append(mark)

    elif action == "close_and_open":
        # Close current
        closed = close_basket(history["open_basket"], today)
        history["weeks"].append(closed)
        log.info(f"Closed cycle: basket {closed['basket_return_pct']:+.2f}% vs "
                 f"SPY {closed['spy_return_pct']:+.2f}% → "
                 f"alpha {closed['alpha_pp']:+.2f}pp")

        # Open new
        picks = select_basket(scan)
        if not picks:
            log.error("Cannot open new basket — leaving open_basket empty")
            history["open_basket"] = None
        else:
            history["open_basket"] = open_new_basket(scan_date, picks)

    history["summary"] = recompute_summary(history)
    history["updated_at"] = today

    # 5. Write back
    gcs_write(HISTORY_PATH, history, dry_run=dry_run)

    # 6. Snapshot for audit
    snapshot_path = f"{BASKET_SNAPSHOT_PREFIX}{today}_boring.json"
    gcs_write(snapshot_path, {
        "date": today,
        "action": action,
        "open_basket": history.get("open_basket"),
        "summary": history.get("summary"),
    }, dry_run=dry_run)

    # 7. Final summary log
    if history["open_basket"]:
        ob = history["open_basket"]
        log.info(f"OPEN BASKET ({ob['inception_date']} → "
                 f"{ob['scheduled_exit_date']}): "
                 f"{[b['symbol'] for b in ob['basket']]}")
        if ob["weekly_marks"]:
            last = ob["weekly_marks"][-1]
            log.info(f"  Last mark: {last['date']} → "
                     f"basket {last['basket_return_pct']:+.2f}% / "
                     f"SPY {last['spy_return_pct']:+.2f}% / "
                     f"alpha {last['alpha_pp']:+.2f}pp")
    if history["summary"]:
        s = history["summary"]
        log.info(f"SUMMARY: {s['weeks_closed']} cycles, cum alpha "
                 f"{s['cum_alpha_pp']:+.2f}pp, win rate {s['win_rate']*100:.0f}%")

    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-rebalance", action="store_true",
                    help="Close current basket and open new (testing only)")
    args = ap.parse_args()

    if not FMP_KEY:
        log.error("FMP_API_KEY not set; aborting")
        sys.exit(1)

    ok = run(dry_run=args.dry_run, force_rebalance=args.force_rebalance)
    sys.exit(0 if ok else 1)
