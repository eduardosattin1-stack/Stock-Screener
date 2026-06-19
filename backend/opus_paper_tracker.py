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


def _close_cash_expiry(legs: list, spot: float) -> float:
    cc = 0.0
    for lg in legs:
        intr = _intrinsic(lg["right"], lg["strike"], spot)
        cc += (intr if lg["action"] == "BUY" else -intr) * lg["qty"]
    return round(cc, 4)


def _open_new(ledger: dict):
    """Open paper positions for today's new non-skip strategies."""
    strfor = _gcs_read(STRATS, {}).get("strategies") or {}
    try:
        picks = {p["symbol"]: p for p in (json.load(open(INPUT, encoding="utf-8-sig")).get("picks") or [])}
    except Exception as e:
        log.warning("no local %s (%s) — can't open new positions tonight", INPUT, e); picks = {}
    have = {p["id"] for p in ledger["positions"]}
    opened = 0
    for sym, strat in strfor.items():
        if strat.get("structure") == "skip":
            continue
        exp = strat.get("expiration", "")
        pid = f"{sym}|{exp}"
        if pid in have or sym not in picks:
            continue
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
            "status": "open", "mark_date": None, "mark_cash": None,
            "pnl": None, "pnl_pct": None, "stale": False,
            "exit_date": None, "realized_pnl": None,
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
                    cc = _close_cash_mark(p["legs"], q)
                    if cc is None:
                        p["stale"] = True; continue
                    pnl = round((p["entry_cash"] + cc) * 100, 2)
                    p.update(mark_date=_today(), mark_cash=cc, pnl=pnl,
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


def _stats(ledger: dict) -> dict:
    pos = ledger["positions"]
    closed = [p for p in pos if p["status"] == "closed_expiry" and p.get("realized_pnl") is not None]
    opens = [p for p in pos if p["status"] == "open" and p.get("pnl") is not None]
    realized = sum(p["realized_pnl"] for p in closed)
    unreal = sum(p["pnl"] for p in opens)
    wins = sum(1 for p in closed if p["realized_pnl"] > 0)
    capital = sum(abs(p["max_loss"]) * 100 for p in pos if p.get("max_loss"))
    return {
        "n_total": len(pos), "n_open": sum(1 for p in pos if p["status"] == "open"),
        "n_closed": len(closed),
        "realized_pnl": round(realized, 2), "unrealized_pnl": round(unreal, 2),
        "total_pnl": round(realized + unreal, 2),
        "win_rate": round(wins / len(closed) * 100, 1) if closed else None,
        "avg_realized": round(realized / len(closed), 2) if closed else None,
        "best": round(max((p["realized_pnl"] for p in closed), default=0), 2) if closed else None,
        "worst": round(min((p["realized_pnl"] for p in closed), default=0), 2) if closed else None,
        "capital_at_risk": round(capital, 2),
        "return_on_capital_pct": round((realized + unreal) / capital * 100, 1) if capital else None,
    }


def main():
    ledger = _gcs_read(LEDGER, None)
    if not isinstance(ledger, dict) or "positions" not in ledger:
        ledger = {"positions": []}
    _open_new(ledger)
    _mark(ledger)
    ledger["stats"] = _stats(ledger)
    ledger["updated"] = datetime.now(timezone.utc).isoformat()
    if _gcs_write(LEDGER, ledger):
        s = ledger["stats"]
        log.info("paper book: %d pos (%d open / %d closed) · realized $%s · unrealized $%s · win %s%%",
                 s["n_total"], s["n_open"], s["n_closed"], s["realized_pnl"], s["unrealized_pnl"], s["win_rate"])
    else:
        raise SystemExit("ledger upload failed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    log.setLevel(logging.INFO)
    main()
