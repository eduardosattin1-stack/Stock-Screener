"""Bot state + trade log on GCS. The bot is the single writer; the supervisor
and the /performance UI only read. Trade log is append-only JSONL.

Honesty metrics are recorded at the moment they're knowable:
- entry_slippage_pct: fill vs the scan close the model priced (DESIGN.md §7)
- every skip (gap beyond chase cap, gate block, corp-action guard) is logged,
  so the chase cap can be re-tuned from evidence instead of vibes.
"""
import copy
import logging
from datetime import datetime, timezone

from .config import BotConfig

log = logging.getLogger("tradebot.ledger")

EMPTY_STATE = {
    "positions": [],        # filled, live positions
    "pending_entries": [],  # entry orders working (tonight's candidates)
    "equity_history": [],   # [{date, equity, cash}] one row per --eod run
    "created": None,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_state(gcs, cfg: BotConfig) -> dict:
    state = gcs["read"](cfg.state_path, None)
    if state is None:
        state = copy.deepcopy(EMPTY_STATE)
        state["created"] = now_iso()
    for key, default in EMPTY_STATE.items():
        state.setdefault(key, copy.deepcopy(default) if default is not None else now_iso())
    return state


def write_state(gcs, cfg: BotConfig, state: dict) -> bool:
    return gcs["write"](cfg.state_path, state)


def log_event(gcs, cfg: BotConfig, event: str, **fields) -> None:
    """Append one row to the trade log (entries, exits, fills, skips, halts)."""
    row = {"ts": now_iso(), "event": event}
    row.update(fields)
    gcs["append_jsonl"](cfg.trades_path, [row])


def stage_pending(state: dict, candidate: dict, qty: int, limit_price: float,
                  scan_date: str) -> dict:
    entry = {
        "symbol": candidate["symbol"],
        "sector": candidate["sector"],
        "p": candidate["p"],
        "scan_close": candidate["price"],
        "scan_date": scan_date,
        "qty": qty,
        "limit_price": limit_price,
        "staged_at": now_iso(),
    }
    state["pending_entries"].append(entry)
    return entry


def record_fill(state: dict, cfg: BotConfig, symbol: str, fill_price: float,
                qty: int, fill_date: str) -> dict:
    """Pending -> position; computes targets and the entry-slippage honesty metric."""
    pending = next(p for p in state["pending_entries"] if p["symbol"] == symbol)
    state["pending_entries"] = [p for p in state["pending_entries"] if p["symbol"] != symbol]
    pos = {
        "symbol": symbol,
        "sector": pending["sector"],
        "p": pending["p"],
        "qty": qty,
        "fill_price": fill_price,
        "scan_close": pending["scan_close"],
        "scan_date": pending["scan_date"],
        "entry_date": fill_date,
        "target_price": round(fill_price * cfg.barrier_mult, 4),
        "stop_price": round(fill_price * (1.0 - cfg.disaster_stop_frac), 4),
        "bar_count": 0,          # trading bars since entry (entry bar excluded)
        "entry_slippage_pct": round((fill_price / pending["scan_close"] - 1.0) * 100, 3),
        "status": "OPEN",
    }
    state["positions"].append(pos)
    return pos


def close_position(state: dict, symbol: str, exit_price: float, exit_date: str,
                   reason: str) -> dict:
    """reason: TARGET | DISASTER_STOP | TERMINAL | MANUAL."""
    pos = next(p for p in state["positions"] if p["symbol"] == symbol and p["status"] == "OPEN")
    pos["status"] = "CLOSED"
    pos["exit_price"] = exit_price
    pos["exit_date"] = exit_date
    pos["exit_reason"] = reason
    pos["realized_pct"] = round((exit_price / pos["fill_price"] - 1.0) * 100, 3)
    return pos


def open_positions(state: dict) -> list:
    return [p for p in state["positions"] if p["status"] == "OPEN"]


def sector_counts(state: dict) -> dict:
    counts = {}
    for p in open_positions(state) + state["pending_entries"]:
        counts[p["sector"]] = counts.get(p["sector"], 0) + 1
    return counts


def equity_snapshot(state: dict, equity: float, cash: float, day: str) -> None:
    state["equity_history"] = [r for r in state["equity_history"] if r["date"] != day]
    state["equity_history"].append({"date": day, "equity": round(equity, 2),
                                    "cash": round(cash, 2)})
    state["equity_history"] = state["equity_history"][-400:]


def day_start_equity(state: dict, today: str) -> float:
    """Most recent snapshot strictly before today (yesterday's close equity)."""
    prior = [r for r in state["equity_history"] if r["date"] < today]
    return prior[-1]["equity"] if prior else 0.0
