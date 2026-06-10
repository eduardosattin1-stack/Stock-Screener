#!/usr/bin/env python3
"""Basket 13 — daily NAV mark (the track-record series).

Appends today's mark to _basket13_tracker.json -> marks[] (idempotent: re-running
the same day overwrites that day's mark). Marks are computed on the UNDERLYING
equity prices (paper-tracking convention — option expressions are not re-priced):
  seat return = live/entry - 1 (open seats; resolved seats freeze at exit_price)
  basket return = sum(weight_pct/100 x seat_ret)   (cash drag included: weights are %NAV)
  nav = 100 x (1 + basket_ret)                     (indexed to 100 at inception)

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
    open_syms = [e["symbol"] for e in entries if not e.get("resolution")]
    quotes = fetch_live_quotes(open_syms)
    today = datetime.date.today().isoformat()

    seats, basket_ret = {}, 0.0
    missing = []
    for e in entries:
        sym, w, ep = e["symbol"], (e.get("weight_pct") or 0), e.get("entry_price")
        res = e.get("resolution")
        if res:                                   # resolved: frozen at exit
            px, ret = res.get("exit_price"), res.get("realized_return_pct")
        else:
            px = quotes.get(sym.upper())
            ret = (px / ep - 1) if (px and ep) else None
            if ret is None:
                missing.append(sym)
        if ret is not None:
            basket_ret += (w / 100.0) * ret
            seats[sym] = {"price": px, "ret_pct": round(ret * 100, 2)}

    mark = {"date": today, "nav": round(100 * (1 + basket_ret), 3),
            "basket_ret_pct": round(basket_ret * 100, 3), "seats": seats}
    marks = [m for m in t.get("marks", []) if m.get("date") != today]   # idempotent per day
    marks.append(mark)
    t["marks"] = sorted(marks, key=lambda m: m["date"])
    json.dump(t, open(TRK, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"MARKED {today}: NAV {mark['nav']}  basket {mark['basket_ret_pct']:+.2f}%  "
          f"({len(seats)} seats{'; missing quotes: ' + ','.join(missing) if missing else ''})  -> marks[{len(t['marks'])}]")


if __name__ == "__main__":
    main()
