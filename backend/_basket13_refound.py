#!/usr/bin/env python3
"""Basket 13 — re-found the book under the EQUAL-WEIGHT model (2026-07-28, Bruno).

A one-time migration, kept in the repo as the auditable record of WHY the NAV series
restarts on 2026-07-28 rather than a number that silently changed.

WHAT IT DOES
  1. ARCHIVES the outgoing book (entries incl. every resolution, marks, final NAV) into
     tracker["book_archive"]. Nothing is deleted. The counterfactual ledger
     (non_selections, with price0/spy0) and the run/decision history are CROSS-BOOK
     ledgers and are CARRIED FORWARD untouched — they are the calibration record and a
     re-founding must not cost us them.
  2. REVERSES FIP's resolution. It was stamped THESIS_BROKEN on 2026-07-21; the
     2026-07-28 Director ranks it #3 (conviction 68, +113%, PENDING_HARD, scale-in) and
     says the catalyst is real and pending. Bruno's call: the resolution was a wrong
     assessment, not a real break. The bad stamp is NOT erased — it moves to
     tracker["corrections"] so the resolution-type calibration is not polluted by a
     phantom THESIS_BROKEN, and so the misjudgement itself stays countable.
  3. RE-STAMPS every carried seat at TODAY's live price with weight INVESTED_PCT/n.
     Entry prices must reset because the NAV resets: carrying old entries into a NAV
     re-based to 100 would book their existing P&L twice.
  4. Restarts marks[] at NAV 100 today.

WHAT IT DOES NOT DO
  - It does not choose seats. Membership is the outgoing open book + FIP; selection is
    the Director's job at the next re-debate.
  - It does not touch the candidate universe, the watchlist, or its cohort NAV.

Usage: python _basket13_refound.py [--dry-run]
"""
import json, os, sys, datetime, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
TRK = os.path.join(BASE, "_basket13_tracker.json")
DIRJ = os.path.join(BASE, "_opus_debate", "_catalyst_director.json")

sys.path.insert(0, BASE)
from _basket13_inject import INVESTED_PCT, equalize_weights
from _post_board import fetch_live_quotes

REVERSALS = {
    "FIP": ("2026-07-28 Director (conviction 68, rank 3 of 29, PENDING_HARD, posture scale-in) "
            "confirms the catalyst is real, contractual and pending. The 2026-07-21 THESIS_BROKEN "
            "stamp was a wrong assessment, not a real break — Bruno's call 2026-07-28."),
}


def main(dry=False):
    t = json.load(open(TRK, encoding="utf-8"))
    today = datetime.date.today().isoformat()
    entries = t.get("entries", [])
    open_seats = [e for e in entries if not e.get("resolution")]
    reversed_seats = [e for e in entries if e.get("resolution") and e["symbol"] in REVERSALS]

    print(f"outgoing book: {len(open_seats)} open, "
          f"{len([e for e in entries if e.get('resolution')])} resolved, "
          f"final NAV {(t.get('marks') or [{}])[-1].get('nav')}")
    for e in reversed_seats:
        r = e["resolution"]
        print(f"  REVERSING {e['symbol']}: {r.get('resolution_type')} @ {r.get('exit_price')} "
              f"({r.get('resolution_date')}) -> back to OPEN")

    carried = open_seats + reversed_seats
    if not carried:
        print("nothing to carry — aborting")
        return

    quotes = fetch_live_quotes([e["symbol"] for e in carried])
    missing = [e["symbol"] for e in carried if quotes.get(e["symbol"].upper()) is None]
    if missing:
        print(f"ABORT: no live quote for {','.join(missing)} — refusing to re-found on a "
              f"partial tape (a missing entry price would silently mis-state the new book)")
        return

    # ---- 1. archive (never delete) ----
    archive = {
        "closed": today,
        "reason": "re-founded under the equal-weight model (2026-07-28, Bruno): equal weight, "
                  "no head-count cap, biotech uncapped, debt-cycle advisory to the Director",
        "final_nav": (t.get("marks") or [{}])[-1].get("nav"),
        "n_entries": len(entries),
        "n_resolved": len([e for e in entries if e.get("resolution")]),
        "entries": json.loads(json.dumps(entries)),      # deep copy
        "marks": t.get("marks", []),
    }

    # ---- 2. record the reversal as a CORRECTION, not an erasure ----
    for e in reversed_seats:
        t.setdefault("corrections", []).append({
            "date": today, "symbol": e["symbol"], "type": "RESOLUTION_REVERSED",
            "reversed_resolution": e["resolution"],
            "reason": REVERSALS[e["symbol"]],
            "note": "counts as a resolution-stamping error, NOT as a realized outcome — exclude "
                    "from realized-return calibration, include in exit-discipline calibration.",
        })
        e.pop("resolution", None)
        e.pop("post_track", None)
        e.pop("post_track_status", None)
        e.pop("resolution_due", None)

    # ---- 3. re-stamp carried seats at today's price ----
    new_entries = []
    for e in carried:
        px = quotes[e["symbol"].upper()]
        prior = e.get("entry_price")
        n = dict(e)
        n.update({
            "status": "OPEN", "entry_date": today, "order_date": today,
            "entry_price": px, "entry_price_source": "refound_live_2026-07-28",
            "limit_price": None,
            "refounded_from": {"entry_date": e.get("entry_date"), "entry_price": prior,
                               "weight_pct": e.get("weight_pct")},
        })
        n.pop("resolution_due", None)
        new_entries.append(n)

    t["entries"] = new_entries
    n_eq = equalize_weights(t["entries"])
    w = round(INVESTED_PCT / n_eq, 4)

    # ---- 4. fresh NAV series ----
    t.setdefault("book_archive", []).append(archive)
    t["marks"] = [{"date": today, "nav": 100.0, "basket_ret_pct": 0.0, "seats": {},
                   "note": f"inception — book re-founded equal-weight ({n_eq} seats x {w}% "
                           f"= {INVESTED_PCT}% invested, {round(100 - INVESTED_PCT, 2)}% cash)"}]

    print(f"\nnew book: {n_eq} seats @ {w}% each = {INVESTED_PCT}% invested "
          f"({round(100 - INVESTED_PCT, 2)}% cash), NAV re-based to 100 on {today}")
    print(f"carried ledgers: {len(t.get('non_selections', []))} counterfactuals, "
          f"{len(t.get('runs', []))} runs, {len(t.get('watchlist', []))} on-deck (untouched)")

    # ---- 5. flag what the new structural gate would reject ----
    # Under equal weight the ONLY downside lever is the expression, so a binary held as plain
    # equity now risks its whole slice with no structural floor. Carried seats are exempt (they
    # were legal when stamped) but this must not pass silently.
    naked = [e for e in t["entries"]
             if e.get("valuation_method") == "binary_prob"
             and (e.get("expression") or {}).get("type") == "equity"]
    if naked:
        print(f"\n!! {len(naked)} BINARY seats are held as PLAIN EQUITY: "
              f"{', '.join(e['symbol'] for e in naked)}")
        print(f"   Each risks its full {w}% slice on a readout with no structural floor. The new "
              f"validator REQUIRES defined-risk on binaries, but carried seats are exempt (they "
              f"were legal when stamped at 2-4.5%). The next re-debate should re-express them or "
              f"drop them — this is the one place equal weight genuinely raises risk.")

    if dry:
        print("\n--dry-run: nothing written")
        return
    shutil.copy(TRK, TRK + f".pre-refound-{today}.bak")
    json.dump(t, open(TRK, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\nWROTE {os.path.relpath(TRK, BASE)} (backup: _basket13_tracker.json.pre-refound-{today}.bak)")


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
