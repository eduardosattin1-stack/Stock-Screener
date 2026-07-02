"""TradeBot entrypoint — one of three phases per invocation (Task Scheduler).

  python -m tradebot.run_bot --stage      12:00 CET (scan completes ~06:30 CET)
  python -m tradebot.run_bot --morning    15:25 CET (09:25 ET)
  python -m tradebot.run_bot --eod        22:15 CET (after the US close)
  python -m tradebot.run_bot --show       print the book + recent orders (read-only)
  python -m tradebot.run_bot --reset      archive + wipe the ledger (dry-run only;
                                          run once before flipping live to clear
                                          the paper rehearsal book)

Safety: dry-run unless the environment sets TRADEBOT_LIVE=1 — there is
deliberately no --live CLI flag, so a stray shell command can't go live.
Halt anytime: create the local file backend/tradebot/TRADEBOT_HALT or the GCS
blob tradebot/HALT (the supervisor uses the latter).
"""
import argparse
import dataclasses
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.config import BotConfig
from tradebot import execution
from tradebot.gcs_io import impl as gcs_impl

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("tradebot")


def main() -> int:
    ap = argparse.ArgumentParser(description="D10 sleeve trading bot")
    phase = ap.add_mutually_exclusive_group(required=True)
    phase.add_argument("--stage", action="store_true")
    phase.add_argument("--morning", action="store_true")
    phase.add_argument("--eod", action="store_true")
    phase.add_argument("--show", action="store_true")
    phase.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    cfg = BotConfig()
    if os.environ.get("TRADEBOT_LIVE") == "1":
        cfg = dataclasses.replace(cfg, dry_run=False)
    log.info(f"mode={'LIVE' if not cfg.dry_run else 'DRY-RUN'} account={cfg.ib_account}")

    if args.show:
        return show(cfg)
    if args.reset:
        return reset(cfg)
    if args.stage:
        out = execution.run_stage(cfg, gcs_impl)
    elif args.morning:
        out = execution.run_morning(cfg, gcs_impl)
    else:
        out = execution.run_eod(cfg, gcs_impl)
    log.info(f"done: {out}")
    return 0


def show(cfg: BotConfig) -> int:
    """Human view of the book + the most recent order/event rows."""
    import json
    from tradebot import ledger
    state = ledger.read_state(gcs_impl, cfg)
    opens = ledger.open_positions(state)
    closed = [p for p in state["positions"] if p.get("status") == "CLOSED"]
    eq = state["equity_history"][-1] if state["equity_history"] else None
    eq_txt = str(eq) if eq else f"no snapshot yet (paper sizing ${cfg.paper_equity_usd:,.0f})"
    print(f"\n=== TradeBot book ({'DRY-RUN' if cfg.dry_run else 'LIVE'}, {cfg.ib_account}) ===")
    print(f"equity: {eq_txt}")
    print(f"\nOPEN ({len(opens)}):")
    for p in sorted(opens, key=lambda x: x["entry_date"]):
        print(f"  {p['symbol']:6s} {p['qty']:>5d} @ {p['fill_price']:<8.2f} "
              f"tgt {p['target_price']:<8.2f} stop {p['stop_price']:<8.2f} "
              f"bar {p['bar_count']:>2d}/{cfg.window_bars}  {p['sector']} "
              f"(entered {p['entry_date']}, slip {p['entry_slippage_pct']:+.2f}%)")
    print(f"\nPENDING entries ({len(state['pending_entries'])}):")
    for p in state["pending_entries"]:
        print(f"  {p['symbol']:6s} {p['qty']:>5d} @ limit {p['limit_price']:<8.2f} "
              f"(scan close {p['scan_close']}, {p['sector']})")
    if closed:
        print(f"\nCLOSED ({len(closed)}):")
        for p in closed[-15:]:
            print(f"  {p['symbol']:6s} {p['exit_reason']:14s} {p['realized_pct']:+7.2f}%  "
                  f"({p['entry_date']} -> {p['exit_date']})")
    text = gcs_impl["read_text"](cfg.trades_path, "")
    rows = [r for r in text.strip().splitlines() if r][-20:]
    print(f"\nLast {len(rows)} log events:")
    for r in rows:
        d = json.loads(r)
        extras = {k: v for k, v in d.items() if k not in ("ts", "event")}
        print(f"  {d['ts'][:19]} {d['event']:14s} {json.dumps(extras)[:110]}")
    return 0


def reset(cfg: BotConfig) -> int:
    """Archive + wipe the ledger. Refused in live mode — the rehearsal book must
    be cleared BEFORE creating LIVE.flag, never after."""
    from tradebot import ledger
    if not cfg.dry_run:
        log.error("refusing --reset in LIVE mode; remove LIVE.flag first")
        return 1
    state = gcs_impl["read"](cfg.state_path, None)
    if state:
        stamp = ledger.now_iso()[:19].replace(":", "")
        gcs_impl["write"](f"tradebot/archive/state_{stamp}.json", state)
        text = gcs_impl["read_text"](cfg.trades_path, "")
        if text:
            gcs_impl["write"](f"tradebot/archive/trades_{stamp}.jsonl", text)
    gcs_impl["write"](cfg.state_path, {"positions": [], "pending_entries": [],
                                       "equity_history": [], "created": ledger.now_iso()})
    gcs_impl["write"](cfg.trades_path, "")
    log.info("ledger archived to tradebot/archive/ and reset")
    return 0


if __name__ == "__main__":
    sys.exit(main())
