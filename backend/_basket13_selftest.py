#!/usr/bin/env python3
"""Self-test for the Basket 13 tracker (temp tracker; never touches the real one):
  1. a cap-violating fresh basket is rejected (programmatic cap assertion)
  2. a valid fresh basket injects + stamps at CRO live prices
  3. an incremental re-debate that breaches a COMBINED driver cap (held 2 + new 1) is rejected
  4. entry -> resolve -> report round-trip
  5. a re-debate NEVER silently drops an un-resolved on-deck name (carry-forward + de-prioritized)
  5b. a re-surfacing name with a STALE resolution (seated+fired long ago) is not falsely pruned
  6. resolution & graduation DO remove a name from the watchlist (+ ledger events)
  6b. an on-deck-only name retires via wl-resolve (+ watchlist_resolutions + WL_RESOLVED)
  6c. event taxonomy ADDED->DEPRIORITIZED_NO_RATIONALE->RE_CHAMPIONED + entry-basis invariants
       + rationale attribution (PASSED_OFF_DECK / CAP_TRIMMED) + uncapped-carry + ledger coverage
Run: python _basket13_selftest.py"""
import json, os
import _basket13_inject as B

BASE = os.path.dirname(os.path.abspath(__file__))

# FIXED synthetic candidate universe — the selftest must be deterministic and board-independent
# (a live re-sweep used to drop the hardcoded SEL names and break test 2). All distinct super_clusters
# + a non-bio lane so the 8-name held book is cap-valid; FIP+ARBX share FDA_clinical_readout (2/2) and
# VIR is a spare on that driver (test 3); WCH* are distinct-driver watchlist spares; HERD* share one
# driver so the cap-trim path (6c-ii) can fire.
SHARED_DRV = "FDA_clinical_readout"


def _cand(sym, drv, clus, live=10.0):
    return {"symbol": sym, "company_name": f"{sym} Inc", "tier": "ACTIVE", "staging": False,
            "lane_canon": "special_sit", "resolution_driver": drv, "super_cluster": clus,
            "edge_grade": "H", "valuation_method": "ratio", "computed_rr": 2.5, "ev_pct": 0.30,
            "payoff": None, "win_prob": None, "fair_value_target": round(live * 1.3, 2),
            "downside_floor": round(live * 0.8, 2), "live_price": live, "dated_milestone": "2026-09-30",
            "days_to_milestone": 200, "instrument": "equity", "valuation_asof": "2026-06-30", "score": 80}


SEL = ["FIP", "ARBX", "DSTX", "SPNX", "RGAX", "CYCX", "ENGX", "MNAX"]   # FIP is resolved in test 4
_SYNTH = [
    _cand("FIP", SHARED_DRV, "c_fip"), _cand("ARBX", SHARED_DRV, "c_arbx"),   # 2/2 on the shared driver
    _cand("DSTX", "drv_dst", "c_dst"), _cand("SPNX", "drv_spn", "c_spn"),
    _cand("RGAX", "drv_rga", "c_rga"), _cand("CYCX", "drv_cyc", "c_cyc"),
    _cand("ENGX", "drv_eng", "c_eng"), _cand("MNAX", "drv_mna", "c_mna"),
    _cand("VIR", SHARED_DRV, "c_vir"),                                        # spare on the shared driver (test 3)
    _cand("WCHA", "drv_wa", "c_wa"), _cand("WCHB", "drv_wb", "c_wb"),         # distinct-driver watchlist spares
    _cand("WCHC", "drv_wc", "c_wc"), _cand("WCHD", "drv_wd", "c_wd"), _cand("WCHE", "drv_we", "c_we"),
] + [_cand(f"HERD{i}", "herd_drv", f"c_h{i}") for i in range(6)]             # one driver, 6 names -> cap trims
cands = {c["symbol"]: c for c in _SYNTH}

cf = os.path.join(BASE, "_basket13_candidates_selftest.json")
json.dump({"candidates": _SYNTH}, open(cf, "w", encoding="utf-8"))
B.CAND = cf                                                                  # inject reads candidates from here


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


picks = [pick(s) for s in SEL]                              # SEL defined in the synthetic fixture above
cro = [{"symbol": s, "verdict": "TRADE", "live_price": cands[s].get("live_price")} for s in SEL]
valid = {"result": {"director": {"picks": picks, "passed": [], "memo": "synthetic"}, "cro": cro}}

tf = os.path.join(BASE, "_basket13_tracker_selftest.json")
B.TRK = tf
if os.path.exists(tf):
    os.remove(tf)


def run(obj, force=False, date=None):
    p = os.path.join(BASE, "_synth.json")
    json.dump(obj, open(p, "w", encoding="utf-8"))
    try:
        B.inject(p, force=force, entry_date=date); return 0
    except SystemExit as e:
        return e.code or 1


def wl_item(sym, rationale=None):
    return {"symbol": sym, "blocked_by": "driver full", "would_enter_if": "a held seat resolves",
            "intended_weight_pct": 2.0, "note": "synthetic", "stance_change_rationale": rationale}


def debate(pick_syms=(), watchlist=(), passed=(), wl_rationale=None):
    """A synthetic Director output object. watchlist accepts symbols or (sym, rationale) tuples."""
    wl_rationale = wl_rationale or {}
    wl = []
    for w in watchlist:
        s = w if isinstance(w, str) else w[0]
        r = wl_rationale.get(s) if isinstance(w, str) else w[1]
        wl.append(wl_item(s, r))
    syms = list(pick_syms) + [w["symbol"] for w in wl]
    cro = [{"symbol": s, "verdict": "TRADE", "live_price": cands[s].get("live_price")} for s in syms]
    return {"result": {"director": {"picks": [pick(s) for s in pick_syms], "watchlist": wl,
                                    "passed": list(passed), "memo": "synthetic"}, "cro": cro}}


def spare_names(n, exclude, distinct_driver=True, same_driver=None):
    """n candidate symbols with a live_price, excluding `exclude`. Distinct drivers by default
    (so cap_watchlist keeps them all), or all sharing `same_driver` (to exercise the cap trim)."""
    seen, out = set(), []
    for s, c in cands.items():
        if s in exclude or c.get("live_price") is None:
            continue
        d = c.get("resolution_driver")
        if same_driver is not None and d != same_driver:
            continue
        if distinct_driver and same_driver is None and d in seen:
            continue
        seen.add(d); out.append(s)
        if len(out) == n:
            break
    return out


def load():
    return json.load(open(tf, encoding="utf-8"))


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

# watchlist tests use force=True: picks:[] trips the 8-name COUNT floor, which is irrelevant to the
# watchlist mechanism under test (the held book is already stamped from tests 2-4).
A, Bn, Cn = spare_names(3, set(SEL) | {"VIR", "FIP"})
assert A and Bn and Cn, "need 3 spare distinct-driver candidates for the watchlist tests"

print("== 5. re-debate never silently drops an un-resolved on-deck name ==")
assert run(debate(watchlist=[A, Bn, Cn]), force=True, date="2026-03-01") == 0
w = load()
syms = {x["symbol"] for x in w["watchlist"]}
assert {A, Bn, Cn} <= syms and {A, Bn, Cn} <= set(w["watchlist_state"]), "all 3 must land on-deck"
# second run omits Bn, Cn entirely (neither resolved nor graduated) -> they MUST carry, de-prioritized
assert run(debate(watchlist=[A]), force=True, date="2026-03-15") == 0
w = load()
syms = {x["symbol"] for x in w["watchlist"]}
assert Bn in syms and Cn in syms, f"REGRESSION: {Bn}/{Cn} silently dropped (the bug this fixes)"
assert Bn in w["watchlist_state"] and Cn in w["watchlist_state"], "carried names must keep their state"
byw = {x["symbol"]: x for x in w["watchlist"]}
assert byw[Bn]["de_prioritized"] and byw[Cn]["de_prioritized"], "omitted names must be flagged de-prioritized"
assert not byw[A]["de_prioritized"], "re-nominated name must stay active"
assert byw[Bn]["entry_date"] == "2026-03-01" and byw[Bn]["first_seen_date"] == "2026-03-01", "carry must not reset the marking basis"
print(f"   OK: {Bn},{Cn} carried+de-prioritized; {A} active")

print("== 5b. stale-resolution false-prune guard (FIP fired in test 4, now re-surfaces on-deck) ==")
assert run(debate(watchlist=["FIP"]), force=True, date="2026-03-20") == 0
w = load()
assert "FIP" in w["watchlist_state"], "a re-nominated name with an OLD resolved entry must NOT be pruned"
print("   OK: FIP re-surfaced on-deck despite a stale FIRED_WIN entry")

print("== 6. graduation removes from watchlist (+ GRADUATED event) ==")
# seat Cn (it's on the watchlist) -> it becomes a held entry -> must leave the on-deck book
assert run(debate(pick_syms=[Cn], watchlist=[A]), force=True, date="2026-04-01") == 0
w = load()
assert Cn not in w["watchlist_state"], "a graduated (now-held) name must leave the watchlist"
assert any(e["symbol"] == Cn and e["event"] == "GRADUATED" for e in w["watchlist_history"]), "GRADUATED event required"
print(f"   OK: {Cn} graduated off-deck with a logged event")

print("== 6b. on-deck-only resolution via wl-resolve ==")
B.wl_resolve(Bn, "EXPIRED", date="2026-04-02", notes="catalyst lapsed un-seated")
w = load()
assert Bn not in w["watchlist_state"] and not any(x["symbol"] == Bn for x in w["watchlist"]), "wl-resolve must drop the name"
assert w.get("watchlist_resolutions", {}).get(Bn, {}).get("resolution_type") == "EXPIRED", "watchlist_resolutions must record it"
assert any(e["symbol"] == Bn and e["event"] == "WL_RESOLVED" for e in w["watchlist_history"]), "WL_RESOLVED event required"
print(f"   OK: {Bn} retired on-deck via wl-resolve")

print("== 6c. event taxonomy + entry-basis invariant on add->deprio->re-champion ==")
D = spare_names(1, set(SEL) | {"VIR", "FIP", A, Bn, Cn})[0]
assert run(debate(watchlist=[D]), force=True, date="2026-05-01") == 0     # ADDED
d_entry = {x["symbol"]: x for x in load()["watchlist"]}[D]
ep0, fs0 = d_entry["entry_price"], d_entry["first_seen_date"]
assert run(debate(watchlist=[]), force=True, date="2026-05-10") == 0       # omitted -> DEPRIORITIZED_NO_RATIONALE
assert run(debate(watchlist=[(D, "edge re-opened after the pullback")]), force=True, date="2026-05-20") == 0  # RE_CHAMPIONED
w = load()
ev = [e["event"] for e in w["watchlist_history"] if e["symbol"] == D]
assert ev == ["ADDED", "DEPRIORITIZED_NO_RATIONALE", "RE_CHAMPIONED"], f"unexpected {D} timeline: {ev}"
rc = [e for e in w["watchlist_history"] if e["symbol"] == D and e["event"] == "RE_CHAMPIONED"][0]
assert rc["rationale"], "re-champion must carry a rationale"
dnow = {x["symbol"]: x for x in w["watchlist"]}[D]
assert dnow["entry_price"] == ep0 and dnow["first_seen_date"] == fs0, "re-champion must not reset entry_price/first_seen_date"
assert not dnow["de_prioritized"], "re-championed name is active again"
print(f"   OK: {D} ADDED->DEPRIORITIZED_NO_RATIONALE->RE_CHAMPIONED, basis preserved")

print("== 6c-ii. CAP_TRIMMED attribution (a fresh nom dropped by the cap, not the Director) ==")
herd = spare_names(B.MAX_WATCHLIST_PER_DRIVER + 1, set(SEL) | {"VIR", "FIP", A, Bn, Cn, D},
                   distinct_driver=False, same_driver=None)
# find a driver with enough names
from collections import Counter
drv_counts = Counter(cands[s].get("resolution_driver") for s in cands
                     if s not in (set(SEL) | {"VIR", "FIP"}) and cands[s].get("live_price") is not None)
big_drv = next((d for d, n in drv_counts.most_common() if n >= B.MAX_WATCHLIST_PER_DRIVER + 1), None)
if big_drv:
    herd = spare_names(B.MAX_WATCHLIST_PER_DRIVER + 1, set(SEL) | {"VIR", "FIP"}, same_driver=big_drv)
    assert run(debate(watchlist=herd), force=True, date="2026-06-01") == 0
    w = load()
    trimmed = [e["symbol"] for e in w["watchlist_history"] if e["event"] == "CAP_TRIMMED" and e["date"] == "2026-06-01"]
    assert trimmed, "the >cap nomination must produce a CAP_TRIMMED event"
    byw = {x["symbol"]: x for x in w["watchlist"]}
    for s in trimmed:
        assert byw[s]["de_prioritized"] and "cap" in (byw[s]["deprioritization_rationale"] or "").lower(), "CAP_TRIMMED rationale must cite the cap"
    print(f"   OK: cap trimmed {trimmed} (attributed to the cap, not the Director)")
else:
    print("   SKIP: no driver with enough spare candidates to exercise the cap")

print("== 6c-iii. ledger coverage — every de-prioritized name has a justifying event ==")
w = load()
_JUSTIFY = {"DEPRIORITIZED", "PASSED_OFF_DECK", "CAP_TRIMMED", "DEPRIORITIZED_NO_RATIONALE"}
for x in w["watchlist"]:
    if x.get("de_prioritized"):
        assert any(e["symbol"] == x["symbol"] and e["event"] in _JUSTIFY for e in w["watchlist_history"]), \
            f"{x['symbol']} de-prioritized with no justifying ledger event"
print("   OK: no un-logged de-prioritizations")

for f in (tf, cf, os.path.join(BASE, "_synth.json")):
    if os.path.exists(f):
        os.remove(f)
print("\nSELFTEST PASSED")
