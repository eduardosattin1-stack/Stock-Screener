#!/usr/bin/env python3
"""
paper_strategy_runner_compounder_us.py
======================================
COMPOUNDER US strategy (v8): top-20 US-listed stocks by compounder_score_us,
equal-weight, monthly rotation with 50% sector cap and Top-40 hysteresis exit.

Universe (set in screener_v6.py compute_compounder_universe_scores):
  - country == "US" (excludes ADRs naturally — TSM/BABA have foreign country)
  - market_cap > $2B
  - sector NOT in {Financial Services, Insurance, Healthcare}
  - all 3 metrics (3y-avg ROE, P/B, OpMargin delta) populated
  - equity > 0 every year (built into the ROE-3y calc)

History (May 11 2026):
  - Original handover §3 spec was SP500 ex Fin/Ins/HC, 1-year PIT ROE.
  - Replaced SP500 gate with country=="US" + mcap>$2B because FMP's
    sp500-constituent endpoint missed MRVL and likely others.
  - Replaced 1-year PIT ROE with 3-year average ROE (per-year capped at 1.0)
    to dampen cyclical-rebound artifacts (CAG +231% NI, EXE margin recovery).
  - Both changes depart from the backtest-validated factor definition.
    Paper-track as DISCOVERY, not validation.

Lifecycle:
  - TOP_N = 20
  - Monthly rebalance (≥28d since last rotation)
  - 50% sector cap (max 10 per sector)
  - Top-40 hysteresis: positions kept if still in Top 40, dropped if outside
  - Sort by compounder_score_us DESC, filter signal_compounder_us=='QUALIFIED'

Output:
  - performance/strategy_history_compounder_us.json
  - performance/baskets/{date}_compounder_us.json

Usage:
  export FMP_API_KEY=...
  python3 paper_strategy_runner_compounder_us.py [--dry-run] [--force-rotate]
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
log = logging.getLogger("compounder_us_runner")

# ─────────────────────────────────────────────────────────────────────────
FMP_KEY = os.environ.get("FMP_API_KEY", "")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")

STRATEGY_VERSION = "compounder-us-v1.0-2026-05-11"
TOP_N = 20                      # target basket size
HYSTERESIS_TOP_N = 40           # current positions kept if still in top-40
SECTOR_CAP_FRACTION = 0.50      # max 50% of basket in any one sector
SECTOR_CAP_MAX = int(TOP_N * SECTOR_CAP_FRACTION)  # = 10
REBALANCE_DAYS = 28             # monthly rebalance cadence

LATEST_SCAN_PATH = "scans/latest_global.json"
HISTORY_PATH = "performance/strategy_history_compounder_us.json"
BASKET_SNAPSHOT_PREFIX = "performance/baskets/"

FMP_BASE = "https://financialmodelingprep.com/stable"


# ─────────────────────────────────────────────────────────────────────────
# GCS read/write — same pattern as composite/momentum/FA runners
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
    """Authenticated write via metadata-server token + REST upload."""
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
# FMP price fetch (used for SPY mark + position mark-to-market)
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
        "region": "compounder_us",
        "strategy_version": STRATEGY_VERSION,
        "inception_date": None,
        "spy_inception_price": None,
        "current_basket": [],
        "rotations": [],
        "weekly_marks": [],
        "summary": None,
        "last_rotation_date": None,   # tracks monthly cadence
        "updated_at": None,
    }


def select_qualified_cohort(scan_data: dict) -> tuple[list[dict], dict[str, dict]]:
    """Filter scan to qualified Compounder-US cohort (signal_compounder_us=
    'QUALIFIED' with a positive compounder_score_us and a usable price),
    sort by score DESC.

    Returns (sorted_picks, by_symbol_lookup).

    The lookup includes ALL qualified stocks (not just top-N); the caller uses
    it to enforce the Top-40 hysteresis.
    """
    stocks = scan_data.get("stocks", []) if isinstance(scan_data, dict) else []
    if not stocks:
        log.error("Scan has no stocks")
        return [], {}

    candidates = []
    for s in stocks:
        if s.get("signal_compounder_us") != "QUALIFIED":
            continue
        score = s.get("compounder_score_us")
        if score is None:
            continue
        price = s.get("price")
        if not price or price <= 0:
            continue
        candidates.append({
            "symbol": (s.get("symbol") or "").upper(),
            "compounder_score": float(score),
            "compounder_rank": s.get("compounder_rank_us"),
            "price": float(price),
            "sector": s.get("sector") or "",
            "market_cap": s.get("market_cap"),
            "roe_compounder": s.get("roe_compounder"),
            "pb_compounder": s.get("pb_compounder"),
            "opmargin_delta_compounder": s.get("opmargin_delta_compounder"),
            "piotroski": s.get("piotroski"),
        })

    candidates.sort(key=lambda x: -x["compounder_score"])
    by_sym = {c["symbol"]: c for c in candidates}
    log.info(f"Compounder-US cohort: {len(candidates)} qualified")
    if candidates:
        head = [(c["symbol"], round(c["compounder_score"], 3), c["sector"][:12])
                for c in candidates[:5]]
        log.info(f"  Top 5: {head}")
    return candidates, by_sym


# ─────────────────────────────────────────────────────────────────────────
# Sector cap helper
# ─────────────────────────────────────────────────────────────────────────
def fill_basket_with_sector_cap(picks: list[dict],
                                already_in: list[dict],
                                target_size: int,
                                cap_per_sector: int) -> tuple[list[dict], list[str]]:
    """Walk picks in order, adding to `already_in` until target_size or
    candidates exhausted, skipping any that would breach the per-sector cap.

    `already_in` items must have a 'sector' key. `picks` items must too.

    Returns (new_full_basket, list_of_skipped_symbols_due_to_cap).
    Note: existing positions in `already_in` are NOT trimmed even if they
    already exceed the cap (would create unwanted churn). The cap only
    constrains NEW additions during this rotation.
    """
    sector_count: dict[str, int] = {}
    for p in already_in:
        sec = p.get("sector") or ""
        sector_count[sec] = sector_count.get(sec, 0) + 1

    held_syms = {p["symbol"] for p in already_in}
    out = list(already_in)
    skipped = []

    for p in picks:
        if len(out) >= target_size:
            break
        if p["symbol"] in held_syms:
            continue
        sec = p.get("sector") or ""
        if sector_count.get(sec, 0) >= cap_per_sector:
            skipped.append(p["symbol"])
            continue
        out.append(p)
        held_syms.add(p["symbol"])
        sector_count[sec] = sector_count.get(sec, 0) + 1

    return out, skipped


# ─────────────────────────────────────────────────────────────────────────
# Lifecycle helpers
# ─────────────────────────────────────────────────────────────────────────
def open_first_basket(scan_date: str,
                      sorted_picks: list[dict]) -> tuple[list, float]:
    """First-run: pick top-N respecting sector cap. Returns (positions, spy)."""
    spy = fmp_quote("SPY") or 0.0

    # Build top-N from sorted picks with sector cap
    chosen, skipped = fill_basket_with_sector_cap(
        sorted_picks, already_in=[],
        target_size=TOP_N, cap_per_sector=SECTOR_CAP_MAX,
    )
    if skipped:
        log.info(f"  Sector cap skipped {len(skipped)} candidates: {skipped[:6]}...")

    positions = []
    for p in chosen:
        positions.append({
            "symbol": p["symbol"],
            "sector": p.get("sector", ""),
            "entry_price": p["price"],
            "entry_date": scan_date,
            "compounder_score_at_entry": round(p["compounder_score"], 4),
            "compounder_rank_at_entry": p.get("compounder_rank"),
            "piotroski_at_entry": p.get("piotroski"),
            "last_price": p["price"],
            "last_marked": scan_date,
            "return_pct": 0.0,
        })
    log.info(f"  Opened {len(positions)} positions "
             f"(target {TOP_N}, sector cap {SECTOR_CAP_MAX}/sector)")
    return positions, spy


def rotate_basket(scan_date: str,
                  current_positions: list[dict],
                  sorted_picks: list[dict],
                  by_symbol: dict[str, dict]) -> tuple[list, list, list]:
    """Apply Top-40 hysteresis exit + sector-capped fill from Top-20.

    Returns (new_basket, removed_log, added_log).

    - removed_log: positions dropped (out of Top 40 OR no longer qualified)
    - added_log:   new positions opened today
    - keeps:       current positions still in the Top-40 cohort
    """
    if not sorted_picks:
        log.warning("  No qualified picks this scan — nothing to add or remove")
        return current_positions, [], []

    # Symbols allowed to STAY: anything in the Top-N hysteresis window OR
    # anything still in the qualified cohort within Top HYSTERESIS_TOP_N.
    # Strict: stocks outside Top-40 or no longer qualified must be dropped.
    top_hysteresis_syms = {p["symbol"] for p in sorted_picks[:HYSTERESIS_TOP_N]}
    top_target_picks = sorted_picks[:TOP_N]

    # Stocks staying (in current basket AND still in Top-40)
    keep = []
    to_remove = []
    for p in current_positions:
        if p["symbol"] in top_hysteresis_syms:
            keep.append(p)
        else:
            to_remove.append(p)

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
            # Reason: dropped because either (a) no longer qualified, or
            # (b) qualified but ranked below HYSTERESIS_TOP_N.
            still_qualified = p["symbol"] in by_symbol
            reason = "dropped_below_top40" if still_qualified else "no_longer_qualified"
            removed_log.append({
                "symbol": p["symbol"],
                "sector": p.get("sector", ""),
                "entry_price": round(p["entry_price"], 4),
                "exit_price": round(exit_price, 4),
                "entry_date": p["entry_date"],
                "exit_date": scan_date,
                "return_pct": round(ret * 100, 4),
                "days_held": days_held,
                "compounder_score_at_entry": p.get("compounder_score_at_entry"),
                "exit_reason": reason,
            })
            log.info(f"  ROTATED OUT  {p['symbol']:<6} ({reason:<22}) "
                     f"entry ${p['entry_price']:.2f} → exit ${exit_price:.2f} "
                     f"({ret*100:+.2f}%, {days_held}d)")

    # Fill back to TOP_N from Top-20 picks, respecting sector cap.
    # `keep` items already have 'sector' from prior open; defensively pull
    # from by_symbol if missing (legacy positions written before this field
    # was tracked).
    for k in keep:
        if not k.get("sector") and k["symbol"] in by_symbol:
            k["sector"] = by_symbol[k["symbol"]].get("sector", "")

    new_basket_meta, skipped_cap = fill_basket_with_sector_cap(
        top_target_picks, already_in=keep,
        target_size=TOP_N, cap_per_sector=SECTOR_CAP_MAX,
    )
    if skipped_cap:
        log.info(f"  Sector cap skipped {len(skipped_cap)} candidates: {skipped_cap[:6]}...")

    # The fill result mixes existing-position dicts and pick dicts; convert
    # newly-added picks into full position records.
    keep_syms = {k["symbol"] for k in keep}
    added_log = []
    new_basket = []
    for entry in new_basket_meta:
        if entry["symbol"] in keep_syms:
            new_basket.append(entry)  # existing position dict
            continue
        # Newly added: entry is a pick dict
        new_pos = {
            "symbol": entry["symbol"],
            "sector": entry.get("sector", ""),
            "entry_price": entry["price"],
            "entry_date": scan_date,
            "compounder_score_at_entry": round(entry["compounder_score"], 4),
            "compounder_rank_at_entry": entry.get("compounder_rank"),
            "piotroski_at_entry": entry.get("piotroski"),
            "last_price": entry["price"],
            "last_marked": scan_date,
            "return_pct": 0.0,
        }
        new_basket.append(new_pos)
        added_log.append({
            "symbol": entry["symbol"],
            "sector": entry.get("sector", ""),
            "entry_price": round(entry["price"], 4),
            "compounder_score_at_entry": round(entry["compounder_score"], 4),
            "compounder_rank_at_entry": entry.get("compounder_rank"),
        })
        log.info(f"  ROTATED IN   {entry['symbol']:<6} entry ${entry['price']:.2f} "
                 f"(score {entry['compounder_score']:.3f}, "
                 f"sector {entry.get('sector', '')[:14]})")

    if len(new_basket) < TOP_N:
        log.warning(f"  Basket undersized: {len(new_basket)}/{TOP_N} "
                    f"(sector cap or thin cohort)")

    return new_basket, removed_log, added_log


def mark_to_market(positions: list[dict], scan_date: str) -> tuple[list, list]:
    """Update last_price + return_pct for every position. Returns
    (updated_positions, individual_returns)."""
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


def add_weekly_mark(history: dict, scan_date: str,
                    position_returns: list[float]) -> Optional[dict]:
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


def should_rebalance(history: dict, scan_date: str, force: bool = False) -> bool:
    """Monthly cadence check. True iff first run, force flag, or
    ≥REBALANCE_DAYS since last rotation."""
    if force:
        log.info(f"  Rebalance: forced via --force-rotate")
        return True
    if not history.get("current_basket"):
        log.info(f"  Rebalance: first run")
        return True
    last = history.get("last_rotation_date")
    if not last:
        # Backfill: history exists but the field was never set (e.g. legacy
        # data). Treat inception_date as the anchor.
        last = history.get("inception_date")
    if not last:
        log.info(f"  Rebalance: no last_rotation_date or inception_date — rotating")
        return True
    try:
        last_d = dt.date.fromisoformat(last)
        scan_d = dt.date.fromisoformat(scan_date)
        delta = (scan_d - last_d).days
    except Exception:
        log.warning(f"  Rebalance: date parse failed (last={last}, scan={scan_date}) — rotating")
        return True
    if delta >= REBALANCE_DAYS:
        log.info(f"  Rebalance: {delta} days since last rotation ≥ {REBALANCE_DAYS} → rotating")
        return True
    log.info(f"  Rebalance: {delta} days since last rotation < {REBALANCE_DAYS} → mark only")
    return False


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def run(dry_run: bool = False, force_rotate: bool = False):
    today = dt.date.today().isoformat()
    log.info(f"COMPOUNDER-US runner starting {today}")
    log.info(f"  Strategy: {STRATEGY_VERSION}")
    log.info(f"  Top-{TOP_N} by compounder_score_us, monthly rotation "
             f"({REBALANCE_DAYS}d), Top-{HYSTERESIS_TOP_N} hysteresis, "
             f"sector cap {SECTOR_CAP_MAX}/sector ({int(SECTOR_CAP_FRACTION*100)}%)")

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

    # 3. Build qualified cohort
    sorted_picks, by_symbol = select_qualified_cohort(scan)
    if not sorted_picks:
        log.error("No qualified Compounder-US picks — aborting")
        return False

    # 4. Lifecycle
    current = history.get("current_basket", [])
    is_first_run = len(current) == 0
    rotate_now = should_rebalance(history, scan_date, force=force_rotate)

    if is_first_run:
        log.info("First run — opening initial basket")
        positions, spy_inception = open_first_basket(scan_date, sorted_picks)
        history["inception_date"] = scan_date
        history["spy_inception_price"] = spy_inception
        history["current_basket"] = positions
        history["last_rotation_date"] = scan_date
        # Mark to market immediately (return = 0% on day 0)
        positions, rets = mark_to_market(positions, scan_date)
        history["current_basket"] = positions
        mark = add_weekly_mark(history, scan_date, rets)
        if mark:
            history["weekly_marks"].append(mark)
    else:
        log.info(f"Existing basket: {len(current)} positions")
        log.info(f"  Symbols: {[p['symbol'] for p in current]}")

        if rotate_now:
            new_basket, removed_log, added_log = rotate_basket(
                scan_date, current, sorted_picks, by_symbol)

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
                log.info("No rotations needed (all positions still in Top-40)")

            history["last_rotation_date"] = scan_date
            current = new_basket

        # Mark all current positions (every week, regardless of rotation)
        current, rets = mark_to_market(current, scan_date)
        history["current_basket"] = current

        mark = add_weekly_mark(history, scan_date, rets)
        if mark:
            history["weekly_marks"].append(mark)

    history["summary"] = recompute_summary(history)
    history["updated_at"] = today

    # 5. Write
    gcs_write(HISTORY_PATH, history, dry_run=dry_run)

    # 6. Snapshot
    snapshot_path = f"{BASKET_SNAPSHOT_PREFIX}{today}_compounder_us.json"
    gcs_write(snapshot_path, {
        "date": today,
        "scan_date": scan_date,
        "current_basket": history.get("current_basket"),
        "summary": history.get("summary"),
    }, dry_run=dry_run)

    # 7. Final log
    if history["current_basket"]:
        log.info(f"FINAL BASKET ({history['inception_date']} inception, "
                 f"{len(history['current_basket'])} positions, "
                 f"last rotated {history.get('last_rotation_date')}):")
        # Group by sector for at-a-glance cap diagnostic
        sector_counts: dict[str, int] = {}
        for p in history["current_basket"]:
            sec = p.get("sector") or "?"
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            log.info(f"  {p['symbol']:<6} ({sec[:14]:<14}) "
                     f"entry ${p['entry_price']:.2f} "
                     f"({p['entry_date']}) → ${p.get('last_price', 0):.2f} "
                     f"({p.get('return_pct', 0):+.2f}%)")
        log.info(f"  Sector breakdown: {sorted(sector_counts.items(), key=lambda x: -x[1])}")
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
    ap.add_argument("--force-rotate", action="store_true",
                    help="Override the monthly cadence and rotate this run")
    args = ap.parse_args()

    if not FMP_KEY:
        log.error("FMP_API_KEY not set; aborting")
        sys.exit(1)

    ok = run(dry_run=args.dry_run, force_rotate=args.force_rotate)
    sys.exit(0 if ok else 1)
