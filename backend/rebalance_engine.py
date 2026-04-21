#!/usr/bin/env python3
"""
Rebalance Engine — CB Screener v7.2 Phase 1
============================================
Applies the backtested production strategy to current portfolio + latest scan,
produces an action list ("close X, open Y") for human execution in IBKR.

PRODUCTION STRATEGY (locked in from 45K-sample backtest, strategy_sweep_v3.py):
  Universe:         top-5 by composite, US SP500+NASDAQ (latest_sp500.json)
  Composite floor:  ≥ 0.80 at entry (quality gate — biggest marginal edge)
  Weighting:        equal-weight 20% each (size-5 differences between schemes inside noise)
  Stop loss:        -12% from entry price
  Take profit:      +20% from entry price
  Time stop:        60 days from entry
  Rotation:         daily exit check; new entries added as slots open
  Cash:             held when fewer than 5 qualifying positions available

Backtest result: +59% CAGR, -16% MaxDD, Sharpe 1.62, 67% win rate, 39d avg hold.
Realistic live expectation: +22-35% CAGR, -20-30% MaxDD, Sharpe 0.8-1.2.

This engine DOES NOT execute trades. It produces a report. Human reads the
weekly email and executes in IBKR. The constraint is intentional — it forces
you to see what the model is doing before capital moves.

Storage (GCS):
  rebalance/latest.json    full report (for frontend + audit)
  rebalance/history.json   append-only log of past rebalance actions
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strategy parameters (locked — do NOT change without a new backtest)
# ---------------------------------------------------------------------------
TARGET_PORTFOLIO_SIZE = 5
COMPOSITE_FLOOR = 0.80
STOP_LOSS_PCT = -0.12       # exit if position drops 12% from entry
TAKE_PROFIT_PCT = 0.20      # exit if position gains 20% from entry
TIME_STOP_DAYS = 60         # exit if position held 60 days without TP or SL

# GCS
GCS_BUCKET = "screener-signals-carbonbridge"
REBAL_LATEST_PATH = "rebalance/latest.json"
REBAL_HISTORY_PATH = "rebalance/history.json"

# Portfolio state path (shared with monitor_v7.py — same state file)
STATE_PATH = "portfolio/state.json"


# ---------------------------------------------------------------------------
# GCS I/O (reuses same pattern as signal_tracker.py and monitor_v7.py)
# ---------------------------------------------------------------------------
def _gcs_token() -> Optional[str]:
    import requests
    try:
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=3,
        )
        return r.json().get("access_token") if r.status_code == 200 else None
    except Exception:
        return None


def _gcs_read(path: str, default):
    import requests
    url = f"https://storage.googleapis.com/{GCS_BUCKET}/{path}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return default


def _gcs_write(path: str, data) -> bool:
    import requests
    tok = _gcs_token()
    if not tok:
        return False
    try:
        r = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o",
            params={"uploadType": "media", "name": path},
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            data=json.dumps(data, default=str), timeout=15,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Exit evaluation
# ---------------------------------------------------------------------------
def _evaluate_position_exit(pos: dict, current_price: float, today: datetime) -> Optional[dict]:
    """
    Decide whether a position should be closed based on the production rules.

    Returns None if position should stay open, else a dict with:
      {reason, exit_rule, pnl_pct, entry_price, exit_price, days_held}

    Rules checked in this order (first hit wins):
      1. Stop loss: current_price vs entry_price <= -12%
      2. Take profit: current_price vs entry_price >= +20%
      3. Time stop: days_held >= 60
    """
    entry_price = float(pos.get("entry_price", 0) or 0)
    if entry_price <= 0 or current_price <= 0:
        return None

    pnl_pct = (current_price - entry_price) / entry_price

    entry_date_str = pos.get("entry_date", "")
    try:
        entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d")
        days_held = (today - entry_date).days
    except Exception:
        days_held = 0

    if pnl_pct <= STOP_LOSS_PCT:
        return {
            "reason": f"Stop loss hit ({pnl_pct*100:.1f}% from entry)",
            "exit_rule": "STOP_LOSS",
            "pnl_pct": pnl_pct,
            "entry_price": entry_price,
            "exit_price": current_price,
            "days_held": days_held,
        }

    if pnl_pct >= TAKE_PROFIT_PCT:
        return {
            "reason": f"Take profit hit (+{pnl_pct*100:.1f}% from entry)",
            "exit_rule": "TAKE_PROFIT",
            "pnl_pct": pnl_pct,
            "entry_price": entry_price,
            "exit_price": current_price,
            "days_held": days_held,
        }

    if days_held >= TIME_STOP_DAYS:
        return {
            "reason": f"Time stop hit ({days_held} days held, {pnl_pct*100:+.1f}%)",
            "exit_rule": "TIME_STOP",
            "pnl_pct": pnl_pct,
            "entry_price": entry_price,
            "exit_price": current_price,
            "days_held": days_held,
        }

    return None


def _current_price_for(symbol: str, scan_stocks: list) -> Optional[float]:
    """Find current price in the scan output. Returns None if symbol not in scan."""
    symbol_u = symbol.upper()
    for s in scan_stocks:
        if str(s.get("symbol", "")).upper() == symbol_u:
            return float(s.get("price", 0) or 0) or None
    return None


# ---------------------------------------------------------------------------
# New entry selection
# ---------------------------------------------------------------------------
def _rank_candidates(scan_stocks: list, exclude_symbols: set) -> list:
    """Return list of candidate dicts (symbol, composite, price, signal, ...),
    sorted by composite desc, filtered by floor + not already held."""
    candidates = []
    for s in scan_stocks:
        sym = str(s.get("symbol", "")).upper()
        if not sym or sym in exclude_symbols:
            continue
        composite = float(s.get("composite", 0) or 0)
        if composite < COMPOSITE_FLOOR:
            continue
        price = float(s.get("price", 0) or 0)
        if price <= 0:
            continue
        candidates.append({
            "symbol": sym,
            "composite": composite,
            "price": price,
            "signal": s.get("signal", ""),
            "classification": s.get("classification", ""),
            "sector": s.get("sector", ""),
            "target": float(s.get("target", 0) or 0),
            "upside": float(s.get("upside", 0) or 0),
            "bull_score": int(s.get("bull_score", 0) or 0),
            "hit_prob": float(s.get("hit_prob", 0) or 0),
        })
    candidates.sort(key=lambda c: c["composite"], reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Core: produce rebalance report
# ---------------------------------------------------------------------------
def compute_rebalance(scan_stocks: list, portfolio_state: dict,
                      scan_date: Optional[str] = None) -> dict:
    """
    Compute the rebalance report for today.

    Args:
      scan_stocks: list of stock dicts from latest_sp500.json
      portfolio_state: dict from portfolio/state.json (has "positions", "history")
      scan_date: YYYY-MM-DD string, defaults to today

    Returns report dict with:
      date, strategy_params, closes, opens, cash_positions,
      portfolio_before, portfolio_after, summary
    """
    today_str = scan_date or datetime.now().strftime("%Y-%m-%d")
    today = datetime.strptime(today_str, "%Y-%m-%d")

    positions_before = list(portfolio_state.get("positions", []))
    positions_after = list(positions_before)

    # --- Step 1: check exits for all currently held positions ---
    closes = []
    for pos in positions_before:
        sym = pos["symbol"]
        current_price = _current_price_for(sym, scan_stocks)
        if current_price is None:
            # Not in today's scan — can't evaluate; skip silently.
            # Could happen for European/delisted symbols scanned in a
            # different region. Left in portfolio untouched.
            continue

        exit_info = _evaluate_position_exit(pos, current_price, today)
        if exit_info:
            closes.append({
                "symbol": sym,
                "entry_date": pos.get("entry_date"),
                "entry_price": exit_info["entry_price"],
                "exit_price": exit_info["exit_price"],
                "pnl_pct": round(exit_info["pnl_pct"], 4),
                "pnl_pct_display": f"{exit_info['pnl_pct']*100:+.1f}%",
                "days_held": exit_info["days_held"],
                "reason": exit_info["reason"],
                "exit_rule": exit_info["exit_rule"],
                "shares": pos.get("shares", 0),
                "entry_composite": pos.get("entry_composite"),
            })
            # Remove from future portfolio
            positions_after = [p for p in positions_after if p["symbol"] != sym]

    # --- Step 2: identify slots available for new entries ---
    current_size = len(positions_after)
    slots_open = TARGET_PORTFOLIO_SIZE - current_size

    # --- Step 3: rank candidates for new entries ---
    held_symbols = {p["symbol"].upper() for p in positions_after}
    candidates = _rank_candidates(scan_stocks, held_symbols)

    opens = []
    if slots_open > 0:
        for cand in candidates[:slots_open]:
            opens.append({
                "symbol": cand["symbol"],
                "entry_price": cand["price"],
                "composite": round(cand["composite"], 3),
                "signal": cand["signal"],
                "classification": cand["classification"],
                "sector": cand["sector"],
                "target": cand["target"],
                "upside_pct": round(cand["upside"], 1),
                "bull_score": cand["bull_score"],
                "hit_prob": round(cand["hit_prob"], 3),
                # Suggested order setup for IBKR
                "stop_loss_price": round(cand["price"] * (1 + STOP_LOSS_PCT), 2),
                "take_profit_price": round(cand["price"] * (1 + TAKE_PROFIT_PCT), 2),
                "time_stop_date": (today + timedelta(days=TIME_STOP_DAYS)).strftime("%Y-%m-%d"),
            })

    # --- Step 4: summary + diagnostics ---
    qualifying_count = sum(
        1 for s in scan_stocks
        if float(s.get("composite", 0) or 0) >= COMPOSITE_FLOOR
    )

    actions_required = len(closes) > 0 or len(opens) > 0
    cash_holding = TARGET_PORTFOLIO_SIZE - (len(positions_after) + len(opens))

    report = {
        "date": today_str,
        "strategy": "Phase 1: top-5 composite ≥ 0.80, -12% stop, +20% target, 60d time",
        "strategy_params": {
            "target_size": TARGET_PORTFOLIO_SIZE,
            "composite_floor": COMPOSITE_FLOOR,
            "stop_loss_pct": STOP_LOSS_PCT,
            "take_profit_pct": TAKE_PROFIT_PCT,
            "time_stop_days": TIME_STOP_DAYS,
        },
        "closes": closes,
        "opens": opens,
        "summary": {
            "positions_before": len(positions_before),
            "positions_after_close": len(positions_after),
            "positions_after_open": len(positions_after) + len(opens),
            "slots_open_before_entries": slots_open,
            "cash_slots_remaining": max(cash_holding, 0),
            "qualifying_in_universe": qualifying_count,
            "actions_required": actions_required,
            "has_closes": len(closes) > 0,
            "has_opens": len(opens) > 0,
        },
        "portfolio_before": [
            {
                "symbol": p["symbol"],
                "entry_date": p.get("entry_date"),
                "entry_price": p.get("entry_price"),
                "entry_composite": p.get("entry_composite"),
            } for p in positions_before
        ],
    }
    return report


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def save_rebalance_report(report: dict) -> bool:
    """Write to rebalance/latest.json and append to history."""
    ok1 = _gcs_write(REBAL_LATEST_PATH, report)
    # Append to history (load, add, save — not atomic, but history is advisory)
    try:
        history = _gcs_read(REBAL_HISTORY_PATH, {"entries": []})
        if not isinstance(history, dict) or "entries" not in history:
            history = {"entries": []}
        # Only append if there were actual actions
        if report.get("summary", {}).get("actions_required"):
            history["entries"].append({
                "date": report["date"],
                "closes_count": len(report.get("closes", [])),
                "opens_count": len(report.get("opens", [])),
                "closes": [c["symbol"] for c in report.get("closes", [])],
                "opens": [o["symbol"] for o in report.get("opens", [])],
            })
            # Keep last 365 entries
            history["entries"] = history["entries"][-365:]
        ok2 = _gcs_write(REBAL_HISTORY_PATH, history)
        return ok1 and ok2
    except Exception as e:
        log.warning(f"Rebalance history write failed: {e}")
        return ok1


# ---------------------------------------------------------------------------
# Convenience: run from a scan — called by run_scan_job.py after sp500 scan
# ---------------------------------------------------------------------------
def run_rebalance_from_scan(scan_stocks: list, region: str = "sp500") -> dict:
    """
    Entry point for post-scan rebalance evaluation.

    Only runs for region=sp500 since the production strategy is US-only.
    Returns the report dict (also persisted to GCS).
    """
    if region != "sp500":
        log.info(f"Rebalance skipped: region={region} (production strategy is US-only)")
        return {}

    if not scan_stocks:
        log.info("Rebalance skipped: empty scan")
        return {}

    # Load portfolio state
    state = _gcs_read(STATE_PATH, {"positions": [], "history": []})
    if not isinstance(state, dict):
        state = {"positions": [], "history": []}

    report = compute_rebalance(scan_stocks, state)
    save_rebalance_report(report)

    summary = report.get("summary", {})
    if summary.get("actions_required"):
        log.info(f"Rebalance: {len(report['closes'])} close(s), {len(report['opens'])} open(s)")
    else:
        log.info(f"Rebalance: no action required (holding {summary.get('positions_after_close', 0)}/5)")

    return report


# ---------------------------------------------------------------------------
# Reader for weekly report / frontend
# ---------------------------------------------------------------------------
def read_latest_rebalance() -> dict:
    """Return the most recent rebalance report, or empty stub if none."""
    return _gcs_read(REBAL_LATEST_PATH, {
        "date": None,
        "closes": [],
        "opens": [],
        "summary": {"actions_required": False},
    })
