#!/usr/bin/env python3
"""
strategy_tracker.py
====================
Maintains a rolling history of strategy basket performance.

Schema written to gs://.../performance/strategy_history_{region}.json:

  {
    "region": "midcap",
    "strategy_version": "1.0",
    "inception_date": "2026-04-20",
    "open_basket": { ... full basket payload ... },     // currently held positions
    "weeks": [                                            // closed weeks, oldest first
      {
        "entry_date": "2026-04-20",
        "exit_date":  "2026-04-27",
        "n_positions": 10,
        "basket_return_pct": 2.26,
        "spy_return_pct": 4.12,
        "alpha_pp": -1.86,
        "positions": [
          {"symbol": "ALGM", "entry": 40.65, "exit": 41.27, "return_pct": 1.53}
          ...
        ]
      },
      ...
    ],
    "summary": {
      "weeks_closed": 13,
      "cum_strategy_return_pct": 21.5,
      "cum_spy_return_pct": 7.2,
      "cum_alpha_pp": 14.3,
      "annualized_return_pct": 92.3,
      "annualized_alpha_pp": 57.2,
      "weeks_positive_alpha": 9,
      "win_rate": 0.69,
      "best_week_alpha_pp": 4.7,
      "worst_week_alpha_pp": -3.2
    },
    "updated_at": "2026-04-27T06:00:00Z"
  }

Run modes:
  Inline from screener_v6 after strategy_basket.generate() completes:
      from strategy_tracker import update_history
      update_history("midcap")
      update_history("sp500")

  CLI for testing or backfilling:
      python3 strategy_tracker.py --region midcap
      python3 strategy_tracker.py --region midcap --reset
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import logging
import math
import os
import sys
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

try:
    from google.cloud import storage  # type: ignore
    HAS_GCS = True
except Exception:
    HAS_GCS = False

log = logging.getLogger(__name__)

BUCKET_NAME = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")
FMP_KEY     = os.environ.get("FMP_KEY", "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA")
FMP_BASE    = "https://financialmodelingprep.com/stable"

WEEKS_PER_YEAR = 52


# ---------------------------------------------------------------------------
# GCS I/O
# ---------------------------------------------------------------------------

def _gcs():
    if not HAS_GCS:
        raise RuntimeError("google-cloud-storage not installed")
    return storage.Client().bucket(BUCKET_NAME)


def _read_json(path: str) -> Optional[dict]:
    bucket = _gcs()
    blob = bucket.blob(path)
    if not blob.exists():
        return None
    try:
        return json.loads(blob.download_as_text())
    except Exception as e:
        log.warning(f"[tracker] failed to parse {path}: {e}")
        return None


def _write_json(path: str, payload: dict) -> str:
    bucket = _gcs()
    blob = bucket.blob(path)
    blob.upload_from_string(
        json.dumps(payload, indent=2),
        content_type="application/json",
    )
    return f"gs://{BUCKET_NAME}/{path}"


def _read_scan(region: str) -> List[dict]:
    """Read latest_{region}.json from scans/."""
    data = _read_json(f"scans/latest_{region}.json")
    if data is None:
        return []
    if isinstance(data, dict):
        return data.get("results") or data.get("stocks") or []
    return data


def _read_basket(region: str) -> Optional[dict]:
    return _read_json(f"scans/strategy_basket_{region}.json")


def _read_history(region: str) -> dict:
    """Return existing history file or initialize a new empty structure."""
    h = _read_json(f"performance/strategy_history_{region}.json")
    if h:
        return h
    return {
        "region": region,
        "strategy_version": "1.0",
        "inception_date": None,
        "open_basket": None,
        "weeks": [],
        "summary": _empty_summary(),
        "updated_at": None,
    }


def _write_history(region: str, payload: dict) -> str:
    return _write_json(f"performance/strategy_history_{region}.json", payload)


def _empty_summary() -> dict:
    return {
        "weeks_closed": 0,
        "cum_strategy_return_pct": 0.0,
        "cum_spy_return_pct": 0.0,
        "cum_alpha_pp": 0.0,
        "annualized_return_pct": 0.0,
        "annualized_alpha_pp": 0.0,
        "weeks_positive_alpha": 0,
        "win_rate": 0.0,
        "best_week_alpha_pp": 0.0,
        "worst_week_alpha_pp": 0.0,
    }


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------

def _fmp_get(endpoint: str, **params) -> Optional[list]:
    params["apikey"] = FMP_KEY
    qs = urllib.parse.urlencode(params)
    url = f"{FMP_BASE}/{endpoint}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log.warning(f"[tracker] fmp {endpoint} {params} -> {e}")
        return None


def _spy_close_on(date_str: str) -> Optional[float]:
    """Close price of SPY on a given date (or nearest prior trading day)."""
    end = dt.date.fromisoformat(date_str)
    start = end - dt.timedelta(days=10)
    rows = _fmp_get("historical-price-eod-light",
                    symbol="SPY",
                    **{"from": start.isoformat(), "to": end.isoformat()})
    if not rows or not isinstance(rows, list):
        return None
    rows.sort(key=lambda r: r.get("date", ""))
    target = end.isoformat()
    cand = [r for r in rows if r.get("date", "") <= target]
    if not cand:
        return None
    return float(cand[-1].get("price") or cand[-1].get("close") or 0)


def _fetch_symbol_close(symbol: str, date_str: str) -> Optional[float]:
    """Fallback price lookup for symbols that left the live scan."""
    end = dt.date.fromisoformat(date_str)
    start = end - dt.timedelta(days=10)
    rows = _fmp_get("historical-price-eod-light",
                    symbol=symbol,
                    **{"from": start.isoformat(), "to": end.isoformat()})
    if not rows or not isinstance(rows, list):
        return None
    rows.sort(key=lambda r: r.get("date", ""))
    target = end.isoformat()
    cand = [r for r in rows if r.get("date", "") <= target]
    if not cand:
        return None
    return float(cand[-1].get("price") or cand[-1].get("close") or 0)


# ---------------------------------------------------------------------------
# Week closure
# ---------------------------------------------------------------------------

def _close_week(prev_basket: dict, exit_date: str, scan_results: List[dict]) -> dict:
    """Compute realized P&L for prev_basket using prices from the new scan."""
    # Build symbol -> exit_price map from the new scan
    price_lookup: Dict[str, float] = {}
    for r in scan_results:
        sym = (r.get("symbol") or "").upper()
        px  = r.get("price")
        if sym and px is not None:
            price_lookup[sym] = float(px)

    positions = []
    rets_pct = []
    for pick in prev_basket.get("basket", []):
        sym = pick["symbol"].upper()
        entry_price = pick.get("price")
        if entry_price is None:
            continue

        exit_price = price_lookup.get(sym)
        if exit_price is None:
            # Symbol fell off the scan — fetch from FMP
            exit_price = _fetch_symbol_close(sym, exit_date)

        if exit_price is None or entry_price <= 0:
            log.warning(f"[tracker] {sym}: missing exit price, skipping in P&L")
            continue

        ret = (exit_price / entry_price - 1.0) * 100.0
        rets_pct.append(ret)
        positions.append({
            "symbol": sym,
            "entry": round(entry_price, 4),
            "exit":  round(exit_price, 4),
            "return_pct": round(ret, 4),
        })

    # Equal-weight basket return
    basket_return = sum(rets_pct) / len(rets_pct) if rets_pct else 0.0

    # SPY return same period
    entry_date = prev_basket.get("scan_date")
    spy_entry = _spy_close_on(entry_date) if entry_date else None
    spy_exit  = _spy_close_on(exit_date)
    if spy_entry and spy_exit and spy_entry > 0:
        spy_return = (spy_exit / spy_entry - 1.0) * 100.0
    else:
        spy_return = 0.0

    return {
        "entry_date": entry_date,
        "exit_date":  exit_date,
        "n_positions": len(positions),
        "basket_return_pct": round(basket_return, 4),
        "spy_return_pct":    round(spy_return, 4),
        "alpha_pp":          round(basket_return - spy_return, 4),
        "positions": positions,
    }


# ---------------------------------------------------------------------------
# Summary stats
# ---------------------------------------------------------------------------

def _compute_summary(weeks: List[dict]) -> dict:
    if not weeks:
        return _empty_summary()

    rs = [w["basket_return_pct"] / 100.0 for w in weeks]
    ss = [w["spy_return_pct"]    / 100.0 for w in weeks]
    alphas_pp = [w["alpha_pp"] for w in weeks]

    cum_strat = 1.0
    cum_spy   = 1.0
    for r, s in zip(rs, ss):
        cum_strat *= (1.0 + r)
        cum_spy   *= (1.0 + s)

    n = len(weeks)
    annualized_strat = (cum_strat ** (WEEKS_PER_YEAR / n) - 1.0) * 100.0 if n > 0 else 0.0
    annualized_spy   = (cum_spy   ** (WEEKS_PER_YEAR / n) - 1.0) * 100.0 if n > 0 else 0.0

    pos_count = sum(1 for a in alphas_pp if a > 0)

    return {
        "weeks_closed": n,
        "cum_strategy_return_pct": round((cum_strat - 1.0) * 100.0, 4),
        "cum_spy_return_pct":      round((cum_spy   - 1.0) * 100.0, 4),
        "cum_alpha_pp":            round((cum_strat - cum_spy) * 100.0, 4),
        "annualized_return_pct":   round(annualized_strat, 4),
        "annualized_alpha_pp":     round(annualized_strat - annualized_spy, 4),
        "weeks_positive_alpha":    pos_count,
        "win_rate":                round(pos_count / n, 4) if n > 0 else 0.0,
        "best_week_alpha_pp":      round(max(alphas_pp), 4),
        "worst_week_alpha_pp":     round(min(alphas_pp), 4),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def update_history(region: str) -> dict:
    """
    Idempotently update strategy_history_{region}.json.

    - First call ever: initialise with current basket as open position.
    - Same scan_date as last call: no-op.
    - New scan_date: close the prior week, append to weeks[], make the new
      basket the open position.
    """
    history = _read_history(region)
    latest  = _read_basket(region)
    if not latest:
        log.warning(f"[tracker] {region}: no basket found, skipping")
        return history

    if latest.get("strategy_version") != history.get("strategy_version", "1.0"):
        log.warning(f"[tracker] {region}: strategy version changed "
                    f"({history.get('strategy_version')} -> {latest.get('strategy_version')}); "
                    f"continuing but consider --reset")

    open_basket = history.get("open_basket")

    # First time: just record the open position
    if open_basket is None:
        history["open_basket"] = latest
        history["inception_date"] = latest.get("scan_date")
        history["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        url = _write_history(region, history)
        log.info(f"[tracker] {region}: initialized at {history['inception_date']}, wrote {url}")
        return history

    # Same scan as before — nothing to do
    if open_basket.get("scan_date") == latest.get("scan_date"):
        log.info(f"[tracker] {region}: no new week (scan_date unchanged), skipping")
        return history

    # Close the previous week
    scan_results = _read_scan(region)
    if not scan_results:
        log.warning(f"[tracker] {region}: scan results unavailable, skipping close")
        return history

    week = _close_week(open_basket, latest["scan_date"], scan_results)
    history["weeks"].append(week)
    history["open_basket"] = latest
    history["summary"] = _compute_summary(history["weeks"])
    history["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    url = _write_history(region, history)
    log.info(f"[tracker] {region}: closed week {week['entry_date']} -> {week['exit_date']} "
             f"(basket {week['basket_return_pct']:+.2f}%, spy {week['spy_return_pct']:+.2f}%, "
             f"alpha {week['alpha_pp']:+.2f}pp); wrote {url}")
    return history


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _reset(region: str) -> None:
    """Wipe the history file (CAREFUL — irreversible)."""
    bucket = _gcs()
    blob = bucket.blob(f"performance/strategy_history_{region}.json")
    if blob.exists():
        blob.delete()
        print(f"[tracker] reset: deleted gs://{BUCKET_NAME}/performance/strategy_history_{region}.json")
    else:
        print(f"[tracker] reset: nothing to delete for {region}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, choices=["midcap", "sp500"])
    ap.add_argument("--reset", action="store_true",
                    help="delete the history file and start over")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.reset:
        confirm = input(f"Delete strategy_history_{args.region}.json? (yes/no) ")
        if confirm.lower() != "yes":
            print("aborted")
            sys.exit(1)
        _reset(args.region)
        return

    h = update_history(args.region)
    s = h.get("summary") or {}
    print(json.dumps({
        "region": h.get("region"),
        "inception": h.get("inception_date"),
        "open_basket_date": (h.get("open_basket") or {}).get("scan_date"),
        "weeks_closed": s.get("weeks_closed", 0),
        "cum_alpha_pp": s.get("cum_alpha_pp", 0),
        "annualized_alpha_pp": s.get("annualized_alpha_pp", 0),
        "win_rate": s.get("win_rate", 0),
    }, indent=2))


if __name__ == "__main__":
    main()
