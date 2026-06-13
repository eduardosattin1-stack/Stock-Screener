#!/usr/bin/env python3
"""Self-test for the Basket 13 tracker (temp tracker; never touches the real one):
  1. a cap-violating fresh basket is rejected (programmatic cap assertion)
  2. a valid fresh basket injects + stamps at CRO live prices
  3. an incremental re-debate that breaches a COMBINED driver cap (held 2 + new 1) is rejected
  4. entry -> resolve -> report round-trip
Run: python _basket13_selftest.py"""
import json, os
import _basket13_candidates as C
import _basket13_inject as B

BASE = os.path.dirname(os.path.abspath(__file__))
C.main(exclude_held=False)                                  # ensure a FULL candidates file (all symbols present)
cands = {c["symbol"]: c for c in
         json.load(open(os.path.join(BASE, "_basket13_candidates.json"), encoding="utf-8"))["candidates"]}


def safe(sym):
    c = cands[sym]; live = c.get("live_price"); fl = c.get("downside_floor")
    vm = c.get("valuation_method"); st = c.get("staging"); days = c.get("days_to_milestone")
    if st:
        return {"type": "equity"}, 3.0
    if vm == "binary_prob":
        return {"type": "debit_spread"}, 1.5
    if isinstance(live, (int, float)) and isinstance(fl, (int, float)) and live > fl:
        w = min(1.4 * live / (live - fl), 10.0)
        return {"type": "defined_risk_option" if (days or 999) <= 183 else "equity"}, round(w, 2)
    return {"type": "equity"}, 4.0


def pick(sym, driver=None):
    c = cands[sym]; exp, w = safe(sym)
    return {"symbol": sym, "weight_pct": w, "expression": exp,
            "resolution_driver": driver or c.get("resolution_driver"), "super_cluster": c.get("super_cluster"),
            "entry_rationale": "synthetic", "invalidation": "synthetic",
            "expected_rr": 2.0 if c.get("valuation_method") != "binary_prob" else None,
            "expected_ev": c.get("ev_pct"), "review_trigger": c.get("dated_milestone")}


# 8 real names with live_price + verified fields; CELC & EYPT share FDA_clinical_readout
SEL = [s for s in ["CELC", "EYPT", "FIP", "GDOT", "UNF", "MGNI", "PRX.AS", "DJT"] if s in cands]
picks = [pick(s) for s in SEL]
cro = [{"symbol": s, "verdict": "TRADE", "live_price": cands[s].get("live_price")} for s in SEL]
valid = {"result": {"director": {"picks": picks, "passed": [], "memo": "synthetic"}, "cro": cro}}

tf = os.path.join(BASE, "_basket13_tracker_selftest.json")
B.TRK = tf
if os.path.exists(tf):
    os.remove(tf)


def run(obj):
    p = os.path.join(BASE, "_synth.json")
    json.dump(obj, open(p, "w", encoding="utf-8"))
    try:
        B.inject(p); return 0
    except SystemExit as e:
        return e.code or 1


print("== 1. cap-violating fresh basket rejected ==")
bad = json.loads(json.dumps(valid))
for q in bad["result"]["director"]["picks"][:3]:
    q["resolution_driver"] = "FDA_clinical_readout"          # 3 names, one driver
assert run(bad) == 1 and not os.path.exists(tf), "fresh cap-violating basket must be rejected, nothing stamped"
print("   OK")

print("== 2. valid fresh basket injects ==")
assert run(valid) == 0, "valid basket should inject"
t = json.load(open(tf, encoding="utf-8"))
assert len([e for e in t["entries"] if not e.get("resolution")]) == len(picks)
print(f"   OK: {len(t['entries'])} entries")

print("== 3. incremental breaching COMBINED driver cap rejected ==")
# held already has CELC+EYPT on FDA_clinical_readout (2/2); adding VIR (same driver) -> 3 combined
vir = "VIR" if "VIR" in cands else next((s for s in cands if cands[s].get("resolution_driver") == "FDA_clinical_readout" and s not in SEL), None)
assert vir, "need a spare FDA_clinical_readout candidate"
incr = {"result": {"director": {"picks": [pick(vir, "FDA_clinical_readout")], "passed": [], "memo": "incr"},
                   "cro": [{"symbol": vir, "verdict": "TRADE", "live_price": cands[vir].get("live_price")}]}}
assert run(incr) == 1, "incremental that makes 3-on-a-driver (combined) must be rejected"
t2 = json.load(open(tf, encoding="utf-8"))
assert len(t2["entries"]) == len(t["entries"]), "rejected incremental must not stamp"
print(f"   OK: {vir} rejected, book unchanged ({len(t2['entries'])} entries)")

print("== 4. resolve FIP FIRED_WIN + report ==")
fip = [x for x in t2["entries"] if x["symbol"] == "FIP"][0]
B.resolve("FIP", "FIRED_WIN", round((fip["entry_price"] or 10) * 1.25, 2), notes="synthetic")
B.report()

os.remove(tf)
sp = os.path.join(BASE, "_synth.json")
if os.path.exists(sp):
    os.remove(sp)
print("\nSELFTEST PASSED")
