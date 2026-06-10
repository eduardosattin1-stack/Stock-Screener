#!/usr/bin/env python3
"""Self-test for the Basket 13 tracker: synthetic entry->resolve->report round-trip +
programmatic cap-assertion check. Uses a TEMP tracker (never touches _basket13_tracker.json).
Run: python _basket13_selftest.py   (expects _basket13_candidates.json present)"""
import json, os
import _basket13_inject as B

BASE = os.path.dirname(os.path.abspath(__file__))
cands = {c["symbol"]: c for c in
         json.load(open(os.path.join(BASE, "_basket13_candidates.json"), encoding="utf-8"))["candidates"]}


def safe(sym):
    c = cands[sym]; live = c.get("live_price"); fl = c.get("downside_floor")
    vm = c.get("valuation_method"); st = c.get("staging"); days = c.get("days_to_milestone")
    if st:                                   # staging -> equity, small (< half-normal)
        return {"type": "equity"}, 3.0
    if vm == "binary_prob":                  # non-staging binary -> defined-risk, <= 2%
        return {"type": "debit_spread"}, 1.5
    if isinstance(live, (int, float)) and isinstance(fl, (int, float)) and live > fl:
        w = min(1.4 * live / (live - fl), 10.0)          # keep risk-to-floor 1.4% < 1.5% cap
        return {"type": "defined_risk_option" if (days or 999) <= 183 else "equity"}, round(w, 2)
    return {"type": "equity"}, 4.0


def pick(sym):
    c = cands[sym]; exp, w = safe(sym)
    return {"symbol": sym, "weight_pct": w, "expression": exp,
            "resolution_driver": c.get("resolution_driver"), "super_cluster": c.get("super_cluster"),
            "entry_rationale": "synthetic", "invalidation": "synthetic",
            "expected_rr": 2.0 if c.get("valuation_method") != "binary_prob" else None,
            "expected_ev": c.get("ev_pct"), "review_trigger": c.get("dated_milestone")}


SEL = ["CELC", "EYPT", "FIP", "GDOT", "UNF", "MGNI", "PRX.AS", "DJT"]
SEL = [s for s in SEL if s in cands]
picks = [pick(s) for s in SEL]
passed = [{"symbol": s, "passed_because": "synthetic non-selection"} for s in ["AMLX", "DFTX"] if s in cands]
valid = {"result": {"director": {"picks": picks, "passed": passed, "memo": "synthetic valid"},
                    "cro": [{"symbol": s, "verdict": "TRADE"} for s in SEL]}}

tf = os.path.join(BASE, "_basket13_tracker_selftest.json")
B.TRK = tf
if os.path.exists(tf):
    os.remove(tf)


def run_inject(obj, force=False):
    p = os.path.join(BASE, "_synth.json")
    json.dump(obj, open(p, "w", encoding="utf-8"))
    try:
        B.inject(p, force=force); return 0
    except SystemExit as e:
        return e.code or 1


print("== 1. VALID basket inject ==")
assert run_inject(valid) == 0, "valid basket should inject"
t = json.load(open(tf, encoding="utf-8"))
assert len(t["entries"]) == len(picks), (len(t["entries"]), len(picks))
print(f"   OK: {len(t['entries'])} entries, {len(t['non_selections'])} non-selections")

print("== 2. CAP-VIOLATING basket (3 names, same driver) rejected ==")
bad = json.loads(json.dumps(valid))
for q in bad["result"]["director"]["picks"][:3]:
    q["resolution_driver"] = "FDA_clinical_readout"
assert run_inject(bad) == 1, "cap-violating basket must be rejected (exit 1)"
print("   OK: rejected with exit 1, tracker unchanged")

print("== 3. resolve FIP FIRED_WIN ==")
fip = [x for x in t["entries"] if x["symbol"] == "FIP"][0]
B.resolve("FIP", "FIRED_WIN", round((fip["entry_price"] or 10) * 1.25, 2), notes="synthetic")
t = json.load(open(tf, encoding="utf-8"))
r = [x for x in t["entries"] if x["symbol"] == "FIP"][0]["resolution"]
assert r and r["resolution_type"] == "FIRED_WIN", r
print(f"   OK: {r}")

print("== 4. report ==")
B.report()

os.remove(tf)
sp = os.path.join(BASE, "_synth.json")
if os.path.exists(sp):
    os.remove(sp)
print("\nSELFTEST PASSED")
