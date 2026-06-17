#!/usr/bin/env python3
"""Self-test for the Basket 13 tracker (temp tracker; never touches the real one):
  1. a cap-violating fresh basket is rejected (programmatic cap assertion)
  2. a valid fresh basket injects + stamps at CRO live prices
  3. an incremental re-debate that breaches a COMBINED driver cap (held 2 + new 1) is rejected
  4. entry -> resolve -> report round-trip
  5. an oversized on-deck watchlist is trimmed to MAX_WATCHLIST_PER_DRIVER (input order preserved)

The candidate basket (SEL) is built DYNAMICALLY from the live _basket13_candidates.json so the
test self-heals when the catalyst sweep refreshes the board — no hardcoded symbols to go stale.
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


# Build SEL DYNAMICALLY (robust to candidate-universe refreshes): exactly MIN_NAMES valid names
# drawn from `cands`, respecting EVERY hard cap in _basket13_inject.validate() so the "valid"
# basket genuinely passes. Greedy, preferring non-staging entry names that carry BOTH live_price
# and downside_floor — for those, safe() yields a defined-risk/equity weight whose risk-to-floor
# is 1.4*(live-fl)/live (uncapped) or 10*(live-fl)/live (when the 10.0 weight cap binds, which only
# happens once (live-fl)/live <= 0.14); either way <= RISK_TO_FLOOR_PCT. Caps tracked as we select:
#   <= MAX_PER_DRIVER per resolution_driver, <= MAX_PER_LANE[lane] per lane,
#   <= MAX_SUPER_PTS NAV weight-points per super_cluster (summing safe() weights).
def build_sel(n):
    sel, bydrv, bylane, bysc = [], {}, {}, {}

    def order_key(s):
        c = cands[s]
        has_fields = isinstance(c.get("live_price"), (int, float)) and isinstance(c.get("downside_floor"), (int, float))
        return (bool(c.get("staging")), not has_fields, s)   # non-staging + fully-priced first, then alpha

    for s in sorted(cands, key=order_key):
        if len(sel) >= n:
            break
        c = cands[s]
        _, w = safe(s)
        drv, lane, sc = c.get("resolution_driver"), c.get("lane_canon"), c.get("super_cluster")
        if bydrv.get(drv, 0) >= B.MAX_PER_DRIVER:
            continue
        if lane in B.MAX_PER_LANE and bylane.get(lane, 0) >= B.MAX_PER_LANE[lane]:
            continue
        if bysc.get(sc, 0.0) + w > B.MAX_SUPER_PTS + B.TOL:
            continue
        sel.append(s)
        bydrv[drv] = bydrv.get(drv, 0) + 1
        bylane[lane] = bylane.get(lane, 0) + 1
        bysc[sc] = bysc.get(sc, 0.0) + w
    return sel


SEL = build_sel(B.MIN_NAMES)
assert len(SEL) == B.MIN_NAMES, \
    f"could not assemble a valid {B.MIN_NAMES}-name basket from {len(cands)} candidates (got {SEL})"
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
# the book now holds MAX_PER_DRIVER names on some driver (e.g. AMLX+EYPT on FDA_clinical_readout);
# a re-debate that adds ONE more on that same driver -> held N + new 1 must be rejected on the
# COMBINED count. Find that driver dynamically + a SPARE candidate of it not already in SEL.
sel_by_drv = {}
for s in SEL:
    sel_by_drv.setdefault(cands[s].get("resolution_driver"), []).append(s)
breach_drv = next((d for d, names in sel_by_drv.items()
                   if len(names) >= B.MAX_PER_DRIVER
                   and any(cands[s].get("resolution_driver") == d and s not in SEL for s in cands)), None)
assert breach_drv, "need a driver held at the per-driver cap in SEL with a spare candidate"
spare = next(s for s in cands if cands[s].get("resolution_driver") == breach_drv and s not in SEL)
incr = {"result": {"director": {"picks": [pick(spare, breach_drv)], "passed": [], "memo": "incr"},
                   "cro": [{"symbol": spare, "verdict": "TRADE", "live_price": cands[spare].get("live_price")}]}}
assert run(incr) == 1, "incremental that breaches a driver cap (combined) must be rejected"
t2 = json.load(open(tf, encoding="utf-8"))
assert len(t2["entries"]) == len(t["entries"]), "rejected incremental must not stamp"
print(f"   OK: {spare} ({breach_drv}) rejected, book unchanged ({len(t2['entries'])} entries)")

print("== 4. resolve an open name FIRED_WIN + report ==")
res_e = next(x for x in t2["entries"]
             if not x.get("resolution") and isinstance(x.get("entry_price"), (int, float)))
B.resolve(res_e["symbol"], "FIRED_WIN", round((res_e["entry_price"] or 10) * 1.25, 2), notes="synthetic")
B.report()

print("== 5. oversized watchlist trimmed to MAX_WATCHLIST_PER_DRIVER (order preserved) ==")
if os.path.exists(tf):
    os.remove(tf)                                            # fresh book so the watchlist is the only variable
N_CROWD = B.MAX_WATCHLIST_PER_DRIVER + 2                     # > per-driver cap, all sharing ONE driver
crowd = [f"WLCAP{i}" for i in range(1, N_CROWD + 1)]         # synthetic names (not in cands) -> driver via w[]
others = [("WLOTH1", "US_antitrust"), ("WLOTH2", "Spin_index_flow")]
wl = [{"symbol": s, "resolution_driver": "FDA_clinical_readout", "blocked_by": "per-driver cap",
       "would_enter_if": "a slot frees", "intended_weight_pct": 1.0, "note": "synthetic"} for s in crowd]
wl += [{"symbol": s, "resolution_driver": d, "blocked_by": "queue", "would_enter_if": "—",
        "intended_weight_pct": 1.0, "note": "synthetic"} for s, d in others]
wlobj = {"result": {"director": {"picks": picks, "passed": [], "memo": "wl", "watchlist": wl}, "cro": cro}}
assert run(wlobj) == 0, "valid basket with an oversized-per-driver watchlist should still inject"
tw = json.load(open(tf, encoding="utf-8"))
stamped = [e["symbol"] for e in tw.get("watchlist", [])]
kept = [s for s in stamped if s in crowd]
assert len(kept) <= B.MAX_WATCHLIST_PER_DRIVER, \
    f"watchlist kept {len(kept)} on one driver > MAX_WATCHLIST_PER_DRIVER={B.MAX_WATCHLIST_PER_DRIVER}"
assert kept == crowd[:B.MAX_WATCHLIST_PER_DRIVER], \
    f"watchlist must keep the first {B.MAX_WATCHLIST_PER_DRIVER} of the driver in input order, got {kept}"
assert "WLOTH1" in stamped and "WLOTH2" in stamped, "other-driver watchlist names must still surface"
print(f"   OK: trimmed to {len(kept)}/driver {kept}; other-driver names {['WLOTH1', 'WLOTH2']} preserved")

os.remove(tf)
sp = os.path.join(BASE, "_synth.json")
if os.path.exists(sp):
    os.remove(sp)
print("\nSELFTEST PASSED")
