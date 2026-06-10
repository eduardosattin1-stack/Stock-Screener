#!/usr/bin/env python3
"""Basket 13 — apex constraint test (run after any regime-apex Director run).

Asserts the hard visibility constraint wired into the apex director prompt (STEP 3b in
weekly_opus_refresh.py): no apex pick may be a Basket-13 sleeve name whose
  valuation_method == "binary_prob", OR edge_grade == "L", OR carrying a blocking edge_flag
  (QUARANTINED / NO_UPSIDE / TRADING_THROUGH_TERMS / FLOOR_GE_LIVE / NO_BREAK_DOWNSIDE).

Non-sleeve apex picks are out of scope (the constraint binds only names the sleeve surfaced).
Exit 0 = clean; exit 1 = violation (print each).

Usage: python _basket13_apex_check.py [apex_basket.json]   (default: _opus_debate/apex_basket_opus_regime.json)
"""
import json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
APEX = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "_opus_debate", "apex_basket_opus_regime.json")
CAND = os.path.join(BASE, "_basket13_candidates.json")
BLOCKING = {"QUARANTINED", "NO_UPSIDE", "TRADING_THROUGH_TERMS", "FLOOR_GE_LIVE", "NO_BREAK_DOWNSIDE"}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not os.path.exists(APEX):
        print(f"SKIP: no apex basket at {APEX}")
        return
    if not os.path.exists(CAND):
        print(f"SKIP: no sleeve candidates at {CAND} (constraint binds only sleeve names)")
        return
    apex = json.load(open(APEX, encoding="utf-8"))
    picks = apex.get("apex_basket") or apex.get("picks") or []
    sleeve = {c["symbol"].upper(): c for c in json.load(open(CAND, encoding="utf-8"))["candidates"]}

    viol, checked = [], 0
    for p in picks:
        sym = str(p.get("symbol", "")).upper()
        c = sleeve.get(sym)
        if not c:
            continue                       # not a sleeve name -> constraint does not bind
        checked += 1
        if c.get("valuation_method") == "binary_prob":
            viol.append(f"{sym}: valuation_method=binary_prob (apex may not hold binaries)")
        if c.get("edge_grade") == "L":
            viol.append(f"{sym}: edge_grade=L")
        bad = set(c.get("edge_flags") or []) & BLOCKING
        if bad:
            viol.append(f"{sym}: blocking edge_flag {sorted(bad)}")

    print(f"APEX CONSTRAINT CHECK: {len(picks)} apex picks, {checked} are sleeve names")
    if viol:
        for v in viol:
            print("  X " + v)
        sys.exit(1)
    print("  OK — no binary_prob / edge-L / blocked-flag sleeve name in the apex selection")


if __name__ == "__main__":
    main()
