#!/usr/bin/env python3
"""Basket 13 — daily NAV mark (the track-record series).

Appends today's mark to _basket13_tracker.json -> marks[] (idempotent: re-running
the same day overwrites that day's mark). Marks are computed on the UNDERLYING
equity prices (paper-tracking convention — option expressions are not re-priced):
  seat return  = live/entry - 1 (open seats; resolved seats freeze at exit_price)
  hedged seats = ((px - ep) - ratio_pnl)/ep where ratio_pnl = |ratio| x (hedge_px - hedge_entry)
  basket ret   = sum(weight_pct/100 x seat_ret)   (cash drag included: weights are %NAV)
  nav          = 100 x (1 + basket_ret)           (indexed to 100 at inception)

PENDING_LIMIT entries (resting limit orders — no fiction fills) are EXCLUDED from NAV.
A pending entry FILLS when the day's close trades at/through its limit (conservative:
intraday touches that close back above are missed): entry_price = limit, entry_date =
mark date, hedge reference = that day's hedge close.

Run daily (PC-on cadence); the UI chart reads marks via _basket13_export.py.
Usage: python _basket13_mark.py
"""
import json, os, datetime
from _post_board import fetch_live_quotes

BASE = os.path.dirname(os.path.abspath(__file__))
TRK = os.path.join(BASE, "_basket13_tracker.json")


def main():
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    t = json.load(open(TRK, encoding="utf-8"))
    entries = t.get("entries", [])
    if not entries:
        print("no entries — nothing to mark")
        return
    unresolved = [e for e in entries if not e.get("resolution")]
    wl_state = t.get("watchlist_state", {})              # on-deck names tracked as a separate paper book
    syms = [e["symbol"] for e in unresolved]
    syms += [e["hedge"]["symbol"] for e in unresolved if e.get("hedge")]
    syms += [s for s in wl_state]                        # watchlist underlyings (one combined quote fetch)
    quotes = fetch_live_quotes(list(dict.fromkeys(syms)))
    today = datetime.date.today().isoformat()

    # 1. pending-limit fills (close at/through the limit)
    filled = []
    for e in unresolved:
        if e.get("status") != "PENDING_LIMIT":
            continue
        px = quotes.get(e["symbol"].upper())
        if px is not None and e.get("limit_price") and px <= e["limit_price"]:
            e["status"] = "OPEN"
            e["entry_price"] = e["limit_price"]          # limit order fills at the limit
            e["entry_date"] = today
            if e.get("hedge"):
                hpx = quotes.get(e["hedge"]["symbol"].upper())
                if hpx is not None:
                    e["hedge"]["price_at_entry"] = hpx   # hedge leg references fill-day close
            filled.append(f"{e['symbol']}@{e['limit_price']}")

    # 2. the mark
    seats, basket_ret, missing, pending = {}, 0.0, [], []
    for e in entries:
        sym, w, ep = e["symbol"], (e.get("weight_pct") or 0), e.get("entry_price")
        res = e.get("resolution")
        if res:                                          # resolved: frozen at exit
            px, ret = res.get("exit_price"), res.get("realized_return_pct")
        elif e.get("status") == "PENDING_LIMIT":         # resting limit: not held, no NAV impact
            pending.append(sym)
            continue
        else:
            px = quotes.get(sym.upper())
            ret = (px / ep - 1) if (px and ep) else None
            if ret is not None and e.get("hedge") and e["hedge"].get("price_at_entry"):
                hpx = quotes.get(e["hedge"]["symbol"].upper())
                if hpx is not None:
                    hedge_pnl = abs(e["hedge"]["ratio"]) * (hpx - e["hedge"]["price_at_entry"])
                    ret = ((px - ep) - hedge_pnl) / ep   # short hedge: rising hedge costs the seat
            if ret is None:
                missing.append(sym)
        if ret is not None:
            basket_ret += (w / 100.0) * ret
            seats[sym] = {"price": px, "ret_pct": round(ret * 100, 2)}

    mark = {"date": today, "nav": round(100 * (1 + basket_ret), 3),
            "basket_ret_pct": round(basket_ret * 100, 3), "seats": seats}
    if pending:
        mark["pending"] = pending
    marks = [m for m in t.get("marks", []) if m.get("date") != today]   # idempotent per day
    marks.append(mark)
    t["marks"] = sorted(marks, key=lambda m: m["date"])

    # 3. watchlist (on-deck) mark — a SEPARATE equal-weight cohort NAV (the on-deck names carry no
    # real allocation, so equal-weight measures "did the Director's watchlist move as expected").
    # Each name is marked from its own watchlist-entry price; departed names simply drop out.
    wl_seats, wl_ret, wl_n, wl_missing = {}, 0.0, 0, []
    live_entry_syms = {e["symbol"] for e in unresolved}      # OPEN/PENDING held positions — marked in the held book
    for sym, st in wl_state.items():
        if sym in live_entry_syms:                           # never double-count a name that's also a live seat
            continue
        ep, px = st.get("entry_price"), quotes.get(sym.upper())
        if ep and px:
            r = px / ep - 1
            wl_seats[sym] = {"price": px, "ret_pct": round(r * 100, 2)}
            wl_ret += r; wl_n += 1
        else:
            wl_missing.append(sym)
    if wl_n:
        wl_mark = {"date": today, "nav": round(100 * (1 + wl_ret / wl_n), 3),
                   "ret_pct": round(wl_ret / wl_n * 100, 3), "n": wl_n, "seats": wl_seats}
        wlm = [m for m in t.get("watchlist_marks", []) if m.get("date") != today]   # idempotent per day
        wlm.append(wl_mark)
        t["watchlist_marks"] = sorted(wlm, key=lambda m: m["date"])

    json.dump(t, open(TRK, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"MARKED {today}: NAV {mark['nav']}  basket {mark['basket_ret_pct']:+.2f}%  ({len(seats)} seats"
          + (f"; FILLED {','.join(filled)}" if filled else "")
          + (f"; pending {','.join(pending)}" if pending else "")
          + (f"; missing quotes: {','.join(missing)}" if missing else "")
          + f")  -> marks[{len(t['marks'])}]")
    if wl_n or wl_missing:
        wl_nav = t.get("watchlist_marks", [{}])[-1].get("nav") if wl_n else None
        print(f"  watchlist: NAV {wl_nav} ({wl_n} on-deck names, equal-weight)"
              + (f"; missing quotes: {','.join(wl_missing)}" if wl_missing else ""))


if __name__ == "__main__":
    main()
