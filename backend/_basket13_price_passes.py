#!/usr/bin/env python3
"""Basket 13 — price the counterfactual ledger (one-time backfill + weekly pass recorder).

Two modes, both append/patch _basket13_tracker.json -> non_selections and NEVER touch
runs[] (appending a run would reset the bi-weekly re-debate self-gate):

  python _basket13_price_passes.py backfill
      Patch every existing non_selections row missing price0/spy0 with the historical
      EOD close (symbol and SPY) on the pass date, stamped backfilled:true. Turns the
      50 asserted counterfactuals into measurable ones. Idempotent: priced rows skip.

  python _basket13_price_passes.py record-run
      Read _opus_debate/_catalyst_director.json (the latest weekly Director) and append
      a non_selections row for every would_seat=false name NOT currently holding an
      open seat: date=asof, passed_because=binding_reason, price0/spy0 = live quotes,
      director_conviction carried. Idempotent per (symbol, date).

Prices come from the same FMP account as the marks (key via _post_board).
"""
import json, os, sys, datetime
import urllib.request, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
TRK = os.path.join(BASE, "_basket13_tracker.json")
DIRJ = os.path.join(BASE, "_opus_debate", "_catalyst_director.json")

from _post_board import FMP_KEY, fetch_live_quotes

FMP_STABLE = "https://financialmodelingprep.com/stable"


def eod_close(sym, date_iso, window_days=5):
    """EOD close for sym ON date_iso (or the first trading day before it, up to window_days back).
    Returns (close, actual_date) or (None, None). Uses the stable API — the account's v3
    access 403s (same reason _post_board pins FMP_BASE to /stable)."""
    frm = (datetime.date.fromisoformat(date_iso) - datetime.timedelta(days=window_days)).isoformat()
    url = (f"{FMP_STABLE}/historical-price-eod/full?symbol={urllib.parse.quote(sym)}"
           f"&from={frm}&to={date_iso}&apikey={FMP_KEY}")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            hist = json.load(r) or []
    except Exception as e:
        print(f"  WARN {sym}: historical fetch failed ({e})")
        return None, None
    # newest-first; the first row <= date_iso is the pass-day (or prior) close
    for row in hist:
        if row.get("date") and row["date"] <= date_iso and isinstance(row.get("close"), (int, float)):
            return row["close"], row["date"]
    return None, None


def backfill():
    t = json.load(open(TRK, encoding="utf-8"))
    ns = t.get("non_selections", [])
    todo = [n for n in ns if not isinstance(n.get("price0"), (int, float))]
    print(f"backfill: {len(todo)}/{len(ns)} pass rows lack price0")
    spy_cache = {}
    patched, failed = 0, []
    for n in todo:
        d = str(n.get("date"))[:10]
        px, pxd = eod_close(n["symbol"], d)
        if px is None:
            failed.append(n["symbol"])
            continue
        if d not in spy_cache:
            spy_cache[d] = eod_close("SPY", d)[0]
        n["price0"], n["spy0"] = px, spy_cache[d]
        n["price0_date"] = pxd
        n["backfilled"] = True
        patched += 1
    json.dump(t, open(TRK, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"backfilled {patched} rows" + (f"; FAILED: {','.join(failed)}" if failed else ""))
    if failed:
        print("  (failed rows keep price0=None — they stay visibly ungraded, never silently guessed)")


def record_run():
    t = json.load(open(TRK, encoding="utf-8"))
    dj = json.load(open(DIRJ, encoding="utf-8"))
    asof = str(dj.get("asof"))[:10]
    held = {e["symbol"] for e in t.get("entries", []) if not e.get("resolution")}
    already = {(n["symbol"], str(n.get("date"))[:10]) for n in t.get("non_selections", [])}
    passes = [a for a in dj.get("assessments", [])
              if not a.get("would_seat") and a.get("symbol") not in held
              and (a["symbol"], asof) not in already]
    if not passes:
        print(f"record-run {asof}: nothing to record "
              f"(all passes already ledgered or held)")
        return
    q = fetch_live_quotes(["SPY"] + [a["symbol"] for a in passes])
    spy0 = q.get("SPY")
    for a in passes:
        t.setdefault("non_selections", []).append({
            "symbol": a["symbol"], "date": asof,
            "passed_because": a.get("binding_reason", ""),
            "score": None, "edge_grade": None,
            "lane_canon": None, "resolution_driver": a.get("cluster"),
            "director_conviction": a.get("conviction"),
            "price0": q.get(a["symbol"].upper()), "spy0": spy0,
            "source": "weekly_director",
        })
    json.dump(t, open(TRK, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    unpriced = [a["symbol"] for a in passes if q.get(a["symbol"].upper()) is None]
    print(f"record-run {asof}: {len(passes)} passes ledgered with price0/spy0 (SPY {spy0})"
          + (f"; no live quote for: {','.join(unpriced)}" if unpriced else ""))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "backfill":
        backfill()
    elif mode == "record-run":
        record_run()
    else:
        print(__doc__)
        sys.exit(1)
