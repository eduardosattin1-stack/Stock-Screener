"""
opus_paper_tracker.py — forward-test (paper) the Opus option strategies.

This is the ACTUAL validator the EV column can't be. Each night, after publish:
  1. OPEN a paper position for every new non-skip strategy, priced at a REALISTIC
     entry fill (cross the bid/ask: buy@ask, sell@bid) from that night's chain.
  2. MARK every open position to market by re-quoting its exact legs via IBKR
     (close = sell longs@bid, buy shorts@ask — crossing again, conservative).
  3. SETTLE positions whose expiration has passed at intrinsic value.
  4. Accumulate realized P&L, win rate, return on capital-at-risk.

P&L convention (per share): entry_cash = sum(SELL:+fill, BUY:-fill); close_cash =
sum(BUY:+bid, SELL:-ask) when marking, or sum(BUY:+intrinsic, SELL:-intrinsic) at
expiry; pnl = entry_cash + close_cash; per-contract = *100. So a debit spread that
expires at max value gives pnl = -debit + width = max_gain (after BOTH spread
crossings on the way in). No real money — ledger lives at GCS scans/options_paper.json.

Run (gateway PC, after opus_strategist publish):  python opus_paper_tracker.py
"""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone, date

import ibkr_options
from ibkr_options import quote_legs, spot_price
from ibkr_options_batch import _gcs_read, _gcs_write, _map_contract
from opus_ev import _chain_legs, _fill

log = logging.getLogger("opus_paper")
LEDGER = "scans/options_paper.json"
STRATS = "scans/options_strategies.json"
INPUT = "strategy_input.json"   # today's chains, local (for entry fills)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _intrinsic(right: str, strike: float, spot: float) -> float:
    return max(0.0, spot - strike) if right == "C" else max(0.0, strike - spot)


def _entry_from_chain(strat: dict, pick: dict):
    """Realistic entry fills per leg + entry_cash (per share). None if unpriceable."""
    cl = _chain_legs(pick, strat.get("expiration", ""))
    legs, entry_cash = [], 0.0
    for lg in strat.get("legs") or []:
        k = round(float(lg.get("strike", 0)), 4); right = lg.get("right")
        side = (lg.get("action") or "").upper(); qty = float(lg.get("qty", 1) or 1)
        q = cl.get((k, right))
        if not q:
            return None
        px = _fill(q, side)
        if px is None:
            return None
        entry_cash += (-px if side == "BUY" else px) * qty   # pay for buys, collect for sells
        legs.append({"action": side, "right": right, "strike": k, "qty": qty, "entry_px": px})
    return legs, round(entry_cash, 4)


def _close_cash_mark(legs: list, quotes: dict):
    """Cash to close NOW, marked at MID (fair value). Entry already paid one spread
    crossing (realistic); marking interim at mid avoids double-counting the spread for
    positions held to expiry — at expiry we settle at intrinsic (no cross). None if a
    leg has no quote at all."""
    cc = 0.0
    for lg in legs:
        q = quotes.get((round(float(lg["strike"]), 4), lg["right"]))
        if not q:
            return None
        bid, ask = q.get("bid"), q.get("ask")
        mid = (bid + ask) / 2.0 if (bid and ask) else (bid or ask)  # prefer mid; fall back to one side
        if mid is None:
            return None
        cc += (mid if lg["action"] == "BUY" else -mid) * lg["qty"]
    return round(cc, 4)


def _close_cash_cross(legs: list, quotes: dict):
    """Cash to close NOW by CROSSING the spread (sell longs@bid, buy shorts@ask) —
    the realistic fill if you actually EXIT now (what an Opus close realizes). None
    if a leg lacks the side needed to close."""
    cc = 0.0
    for lg in legs:
        q = quotes.get((round(float(lg["strike"]), 4), lg["right"]))
        if not q:
            return None
        px = q.get("bid") if lg["action"] == "BUY" else q.get("ask")
        if px is None:
            return None
        cc += (px if lg["action"] == "BUY" else -px) * lg["qty"]
    return round(cc, 4)


def _close_cash_expiry(legs: list, spot: float) -> float:
    cc = 0.0
    for lg in legs:
        intr = _intrinsic(lg["right"], lg["strike"], spot)
        cc += (intr if lg["action"] == "BUY" else -intr) * lg["qty"]
    return round(cc, 4)


def _open_new(ledger: dict):
    """Open paper positions for today's new non-skip strategies."""
    strfor = (_gcs_read(STRATS, {}, fresh=True) or {}).get("strategies") or {}
    try:
        picks = {p["symbol"]: p for p in (json.load(open(INPUT, encoding="utf-8-sig")).get("picks") or [])}
    except Exception:
        # Expected on the intraday mark pass (open-new is nightly-only; the nightly gather writes
        # this file before the manage step). A genuinely missing file at the nightly run is caught
        # upstream by opus_strategist.ps1 step 1, so this is INFO, not a WARNING.
        log.info("no local %s — skipping open-new (expected intraday)", INPUT); picks = {}
    have = {p["id"] for p in ledger["positions"]}
    opened = 0
    for sym, strat in strfor.items():
        if strat.get("structure") == "skip":
            continue
        exp = strat.get("expiration", "")
        pid = f"{sym}|{exp}"
        if pid in have or sym not in picks:
            continue
        # Don't paper-trade an untradeable structure: if the crossed entry fill meets
        # or exceeds the spread width, max_gain_fill <= 0 — best case is a loss, you'd
        # never actually enter it. The executor (Opus) also closes any that slip through.
        mgf = strat.get("max_gain_fill")
        if mgf is not None and mgf <= 0:
            log.info("skip %s — untradeable at fill (max_gain_fill=%s)", sym, mgf); continue
        ent = _entry_from_chain(strat, picks[sym])
        if not ent:
            continue
        legs, entry_cash = ent
        m = _map_contract(sym) or (sym, "SMART", "USD")
        ledger["positions"].append({
            "id": pid, "symbol": sym, "ib_symbol": m[0], "exchange": m[1], "currency": m[2],
            "structure": strat.get("structure"), "decile": strat.get("decile"),
            "iv_rank": strat.get("iv_rank"), "entry_date": _today(), "expiration": exp,
            "entry_spot": (picks[sym].get("chain") or {}).get("spot") or picks[sym].get("price"),
            "legs": legs, "entry_cash": entry_cash,
            "max_gain": strat.get("max_gain_fill"), "max_loss": strat.get("max_loss_fill"),
            "breakeven": strat.get("breakeven_fill") or strat.get("breakeven"),
            "target_move_pct": strat.get("target_move_pct"), "conviction": strat.get("conviction"),
            "thesis": strat.get("thesis"), "risk_note": strat.get("risk_note"),
            "status": "open", "mark_date": None, "mark_cash": None, "exit_cash": None,
            "mark_spot": None, "pnl": None, "pnl_pct": None, "stale": False,
            "exit_date": None, "realized_pnl": None, "close_reason": None, "closed_by": None,
            "days_held": None,
        })
        opened += 1
    log.info("opened %d new paper position(s)", opened)
    return opened


def _mark(ledger: dict):
    """Mark open positions; settle expired ones. Returns (marked, settled)."""
    opens = [p for p in ledger["positions"] if p["status"] == "open"]
    if not opens:
        return 0, 0
    ib = ibkr_options._connect()
    marked = settled = 0
    today = date.fromisoformat(_today())
    try:
        for p in opens:
            try:
                if not ib.isConnected():
                    try: ib.disconnect()
                    except Exception: pass
                    ib = ibkr_options._connect()
                expired = p["expiration"] and date.fromisoformat(p["expiration"]) <= today
                if expired:
                    sp = spot_price(ib, p["ib_symbol"], p["exchange"], p["currency"])
                    if sp is None:
                        p["stale"] = True; continue
                    cc = _close_cash_expiry(p["legs"], sp)
                    pnl = round((p["entry_cash"] + cc) * 100, 2)
                    p.update(status="closed_expiry", mark_date=_today(), mark_cash=cc,
                             pnl=pnl, realized_pnl=pnl, exit_date=_today(), exit_spot=round(sp, 2),
                             pnl_pct=round(pnl / (abs(p["max_loss"]) * 100) * 100, 1) if p.get("max_loss") else None,
                             stale=False)
                    settled += 1
                else:
                    q = quote_legs(ib, p["ib_symbol"], p["exchange"], p["currency"], p["expiration"], p["legs"])
                    cc = _close_cash_mark(p["legs"], q)       # fair-value mark (mid)
                    if cc is None:
                        p["stale"] = True; continue
                    ex = _close_cash_cross(p["legs"], q)      # realistic exit (cross) for Opus closes
                    sp = spot_price(ib, p["ib_symbol"], p["exchange"], p["currency"])
                    pnl = round((p["entry_cash"] + cc) * 100, 2)
                    p.update(mark_date=_today(), mark_cash=cc, exit_cash=ex,
                             mark_spot=round(sp, 2) if sp else None, pnl=pnl,
                             pnl_pct=round(pnl / (abs(p["max_loss"]) * 100) * 100, 1) if p.get("max_loss") else None,
                             stale=False)
                    marked += 1
            except Exception as e:
                log.warning("mark %s failed: %s", p["id"], e); p["stale"] = True
    finally:
        try:
            if ib.isConnected(): ib.disconnect()
        except Exception:
            pass
    log.info("marked %d, settled %d", marked, settled)
    return marked, settled


CLOSED = ("closed_expiry", "closed_opus")


def _stats(ledger: dict) -> dict:
    pos = ledger["positions"]
    closed = [p for p in pos if p["status"] in CLOSED and p.get("realized_pnl") is not None]
    opens = [p for p in pos if p["status"] == "open" and p.get("pnl") is not None]
    realized = sum(p["realized_pnl"] for p in closed)
    unreal = sum(p["pnl"] for p in opens)
    wins = [p for p in closed if p["realized_pnl"] > 0]
    gross_win = sum(p["realized_pnl"] for p in wins)
    gross_loss = -sum(p["realized_pnl"] for p in closed if p["realized_pnl"] <= 0)
    capital = sum(abs(p["max_loss"]) * 100 for p in pos if p.get("max_loss"))
    holds = [p["days_held"] for p in closed if p.get("days_held") is not None]
    return {
        "n_total": len(pos), "n_open": sum(1 for p in pos if p["status"] == "open"),
        "n_closed": len(closed),
        "n_closed_opus": sum(1 for p in closed if p["status"] == "closed_opus"),
        "n_closed_expiry": sum(1 for p in closed if p["status"] == "closed_expiry"),
        "realized_pnl": round(realized, 2), "unrealized_pnl": round(unreal, 2),
        "total_pnl": round(realized + unreal, 2),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
        "avg_realized": round(realized / len(closed), 2) if closed else None,
        "profit_factor": (round(gross_win / gross_loss, 2) if gross_loss > 0 else (999.0 if gross_win > 0 else None)),
        "avg_hold_days": round(sum(holds) / len(holds), 1) if holds else None,
        "best": round(max((p["realized_pnl"] for p in closed), default=0), 2) if closed else None,
        "worst": round(min((p["realized_pnl"] for p in closed), default=0), 2) if closed else None,
        "capital_at_risk": round(capital, 2),
        "return_on_capital_pct": round((realized + unreal) / capital * 100, 1) if capital else None,
        "realized_return_pct": round(realized / capital * 100, 1) if capital else None,
    }


def _exec_input(ledger: dict) -> list:
    """Per open position, the live state Opus needs to decide CLOSE vs HOLD."""
    today = date.fromisoformat(_today())
    out = []
    for p in ledger["positions"]:
        if p["status"] != "open" or p.get("exit_cash") is None:
            continue
        held = (today - date.fromisoformat(p["entry_date"])).days
        dte = (date.fromisoformat(p["expiration"]) - today).days if p.get("expiration") else None
        out.append({
            "id": p["id"], "symbol": p["symbol"], "structure": p["structure"],
            "decile": p.get("decile"), "days_held": held, "days_to_expiry": dte,
            "entry_spot": p.get("entry_spot"), "mark_spot": p.get("mark_spot"),
            "breakeven": p.get("breakeven"), "target_move_pct": p.get("target_move_pct"),
            "max_gain_per_contract": round((p.get("max_gain") or 0) * 100, 0),
            "max_loss_per_contract": round(abs(p.get("max_loss") or 0) * 100, 0),
            "mark_pnl": p.get("pnl"),
            "exit_now_pnl": round((p["entry_cash"] + p["exit_cash"]) * 100, 2),
            "thesis": p.get("thesis"), "risk_note": p.get("risk_note"), "conviction": p.get("conviction"),
        })
    return out


EXEC_INPUT = "execution_input.json"


def main():
    ledger = _gcs_read(LEDGER, None, fresh=True)   # fresh: avoid the edge-cache stale read
    if not isinstance(ledger, dict) or "positions" not in ledger:
        ledger = {"positions": []}
    _open_new(ledger)
    _mark(ledger)
    ledger["stats"] = _stats(ledger)
    ledger["updated"] = datetime.now(timezone.utc).isoformat()
    if not _gcs_write(LEDGER, ledger):
        raise SystemExit("ledger upload failed")
    # Hand the open positions to the executor (Opus close/hold decisions next).
    with open(EXEC_INPUT, "w") as f:
        json.dump({"updated": ledger["updated"], "positions": _exec_input(ledger)}, f, indent=2, default=str)
    s = ledger["stats"]
    log.info("paper book: %d pos (%d open / %d closed) · realized $%s · unrealized $%s · win %s%% · wrote %s",
             s["n_total"], s["n_open"], s["n_closed"], s["realized_pnl"], s["unrealized_pnl"], s["win_rate"], EXEC_INPUT)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    log.setLevel(logging.INFO)
    main()
