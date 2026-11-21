"""Disagreements between the two committees: what each is about, the ledger, and the capped re-debates.

Built 2026-11-19. usage:  python backend/tests/test_disagreements.py
"""
import json
import sys
import tempfile
from pathlib import Path

B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B / "gemini_confirm")); sys.path.insert(0, str(B))
import _disagree as DIS        # noqa: E402
import _seat_triggers as ST    # noqa: E402
import export_week as X        # noqa: E402

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def claude(base=950.0, verdict="A", as_of="2026-11-10", lfd="2026-11-10"):
    return {"verdict": verdict, "last_full_debate": lfd,
            "valuation": {"base_fv_px": base, "live_price": 640.0, "price_currency": "GBp", "as_of": as_of}}


def gemini(base=782.0, verdict="A", sources=()):
    return {"verdict": verdict, "valuation": {"base_fv_px": base, "live_price": 637.0, "price_currency": "GBp"},
            "gemini_meta": {"sources": list(sources)}}


# ---- classify: one kind per name, strongest first
k = DIS.classify(claude(), gemini(), {"verdict": "REFUTED", "kill_scope": "moat"})
check("kill: a refuted moat is a kill", k["kind"] == "kill")

FD = [{"fact": "Americas operating profit", "record_value": 285, "source_value": 230, "source": "FY25 results RNS",
       "source_date": "2026-03-03"}]
k = DIS.classify(claude(), gemini(), {"verdict": "CONFIRMED_WITH_CORRECTIONS", "kill_scope": "numbers", "fact_disputes": FD})
check("fact: a typed input dispute that moves the value is a fact dispute", k["kind"] == "fact" and k["disputes"][0]["source_value"] == 230)

legacy = DIS.fact_disputes({"fact_disputes": [{"fact": "net debt", "ours": 137, "theirs": 100}]})[0]
check("legacy Week-47 ours/theirs: theirs is our record, ours the source, flagged as assumed",
      legacy["record_value"] == 100 and legacy["source_value"] == 137 and legacy.get("orientation_assumed") is True)

# Week 47 calibration: disputes on every name, self-labelled "material", values within a few percent
k = DIS.classify(claude(base=100.0), gemini(base=104.0), {"verdict": "CONFIRMED_WITH_CORRECTIONS", "kill_scope": "numbers",
                                                          "correction_severity": "material", "revised_fv_px": 97.0,
                                                          "fact_disputes": FD})
check("agree: disputes that barely move the value are not a disagreement (self-label ignored)",
      k["kind"] == "agree" and len(k["disputes"]) == 1)
k = DIS.classify(claude(base=100.0), gemini(base=104.0), {"verdict": "CONFIRMED_WITH_CORRECTIONS", "revised_fv_px": 85.0,
                                                          "fact_disputes": FD})
check("fact: disputes whose revised value moves ours by more than 10%", k["kind"] == "fact")
k = DIS.classify(claude(base=100.0, verdict="A"), gemini(base=103.0, verdict="B"), {"verdict": "CONFIRMED"})
check("agree: buy-now vs wait on the same value is not a split", k["kind"] == "agree")

k = DIS.classify(claude(), gemini(), {"verdict": "REFUTED", "kill_scope": "numbers", "correction_severity": "material",
                                      "corrections_typed": [{"field": "base_fv_px", "from": 950, "to": 891}]})
check("fact: a refuted number in our record counts as a fact dispute", k["kind"] == "fact")
check("output-only corrections are not listed as disputed inputs", k["disputes"] == [])

k = DIS.classify(claude(as_of="2026-11-10"), gemini(sources=[{"what": "Q3 trading update", "date": "2026-11-12"}]),
                 {"verdict": "CONFIRMED", "kill_scope": ""})
check("new_fact: a source dated after our record, with a value gap", k["kind"] == "new_fact" and len(k["newer_facts"]) == 1)

k = DIS.classify(claude(), gemini(sources=[{"what": "H1 results", "date": "2026-07-28"}]), {"verdict": "CONFIRMED"})
check("judgement: same facts (older sources), 18% gap", k["kind"] == "judgement" and k["gap_pct"] == -17.7)
check("direction: their lower value reads more bearish", k["direction"] == "more_bearish")

k = DIS.classify(claude(base=100.0), gemini(base=105.0), {"verdict": "CONFIRMED"})
check("agree: within 15% and same grade", k["kind"] == "agree" and k["direction"] is None)

k = DIS.classify(claude(base=100.0, verdict="C"), gemini(base=104.0, verdict="A"), {"verdict": "CONFIRMED"})
check("grade split alone is a judgement, read more bullish when they grade higher",
      k["kind"] == "judgement" and k["direction"] == "more_bullish" and k["grade_split"])

check("dates inside a source title are found",
      DIS.dated_sources({"gemini_meta": {"sources": [{"title": "Q3 update RNS (2026-10-22)"}]}}) == [("2026-10-22", "Q3 update RNS (2026-10-22)")])

# ---- ledger: idempotent per week, resolved by our next full debate's typed check
with tempfile.TemporaryDirectory() as td:
    path = Path(td) / "_disagreements.jsonl"
    row = {"week": "2026-W47", "picked_up_at": "2026-11-21T09:00:00", "symbol": "INCH.L",
           "claude": {"base_fv_px": 950.0}, "resolution": None}
    DIS.update_ledger(path, "2026-W47", [row], {})
    DIS.update_ledger(path, "2026-W47", [dict(row)], {})
    check("ledger: re-running the same week does not duplicate rows", len(DIS.load_ledger(path)) == 1)

    stale = {"last_full_debate": "2026-11-16", "second_opinion_check": [{"outcome": "ADOPTED"}],
             "valuation": {"base_fv_px": 930.0}}
    rows, n = DIS.update_ledger(path, "2026-W48", [], {"INCH.L": stale})
    check("ledger: a debate BEFORE the row was opened does not resolve it", n == 0 and rows[0]["resolution"] is None)

    no_check = {"last_full_debate": "2026-11-23", "valuation": {"base_fv_px": 930.0}}
    rows, n = DIS.update_ledger(path, "2026-W48", [], {"INCH.L": no_check})
    check("ledger: a later debate without the typed check leaves it open", n == 0)

    done = {"last_full_debate": "2026-11-23", "valuation": {"base_fv_px": 930.0},
            "second_opinion_check": [{"field": "segment_operating_profit", "outcome": "ADOPTED", "source_date": "2026-03-03"},
                                     {"field": "shares_outstanding", "outcome": "REJECTED"},
                                     {"field": "net_debt", "outcome": "unverified"}]}
    rows, n = DIS.update_ledger(path, "2026-W48", [], {"INCH.L": done})
    res = rows[0]["resolution"] or {}
    check("ledger: our next full debate resolves the row",
          n == 1 and res.get("adopted") == 1 and res.get("rejected") == 1 and res.get("unverified") == 1)
    check("ledger: the resolution records how our value moved", res.get("base_move_pct") == -2.1)

# ---- priority and the capped non-seat trigger
check("priority: a fact dispute outranks a bigger judgement gap",
      DIS.priority({"disagreement_kind": "fact", "gap_pct": 5}) < DIS.priority({"disagreement_kind": "judgement", "gap_pct": 60}))

with tempfile.TemporaryDirectory() as td:
    pd = Path(td)
    for s in ("AAA", "BBB", "CCC", "HELD", "OLD"):
        (pd / f"{s}.json").write_text(json.dumps({"last_full_debate": "2026-11-09"}), encoding="utf-8")
    (pd / "OLD.json").write_text(json.dumps({"last_full_debate": "2026-11-30"}), encoding="utf-8")

    def blk(kind, status="disagreement", theirs=130.0):
        return {"generated_at": "2026-11-21", "status": status, "disagreement_kind": kind,
                "their_base_fv_px": theirs, "our_base_fv_px": 100.0}
    blocks = {"AAA": blk("fact", theirs=105.0), "BBB": blk("new_fact", theirs=160.0), "CCC": blk("judgement"),
              "HELD": blk("fact"), "OLD": blk("fact")}
    ok, deferred = ST.second_opinion_allowed(blocks, pd, seats={"HELD"}, cap=1)
    check("trigger: strongest evidence first under the cap (fact beats a larger new-fact gap)", ok == {"AAA"} and deferred == ["BBB"])
    ok, _ = ST.second_opinion_allowed(blocks, pd, seats={"HELD"}, cap=10)
    check("trigger: a pure judgement split never buys a non-seat re-debate", "CCC" not in ok)
    check("trigger: seats are left to their own trigger", "HELD" not in ok)
    check("trigger: a name already re-debated after the opinion does not fire", "OLD" not in ok)

    # 5/5 split (2026-11-21): upside disputes get half the slots even when kills outnumber them
    for s in ("K1", "K2", "K3", "UP1", "UP2", "DOWN"):
        (pd / f"{s}.json").write_text(json.dumps({"last_full_debate": "2026-11-09"}), encoding="utf-8")

    def blk2(kind, direction, theirs):
        return {"generated_at": "2026-11-21", "status": "disagreement", "disagreement_kind": kind,
                "disagreement_direction": direction, "their_base_fv_px": theirs, "our_base_fv_px": 100.0}
    b2 = {"K1": blk2("kill", "more_bearish", 80), "K2": blk2("kill", None, 98), "K3": blk2("kill", "more_bearish", 70),
          "UP1": blk2("fact", "more_bullish", 125), "UP2": blk2("new_fact", "more_bullish", 140),
          "DOWN": blk2("fact", "more_bearish", 60)}
    ok, deferred = ST.second_opinion_allowed(b2, pd, seats=set(), cap=4)
    check("split: half the slots go to upside disputes, biggest gap first", {"UP1", "UP2"} <= ok)
    check("split: the other half to kills, strongest first", len(ok & {"K1", "K2", "K3"}) == 2 and "DOWN" in deferred)
    ok, _ = ST.second_opinion_allowed({k: v for k, v in b2.items() if k != "UP1" and k != "UP2"}, pd, seats=set(), cap=4)
    check("split: with no upside candidates the protective side gets every slot", len(ok) == 4)
    ok, _ = ST.second_opinion_allowed({"UP1": b2["UP1"], "UP2": b2["UP2"], "K1": b2["K1"]}, pd, seats=set(), cap=4)
    check("split: unused protective slots are lent to upside", ok == {"UP1", "UP2", "K1"})

    b = ST.second_opinion_block({"status": "not_run"})
    check("block: a name Gemini never reached carries no second opinion", b is None)
    b = ST.second_opinion_block({"status": "repriced", "disagreement_kind": "fact",
                                 "skeptic_on_ours": {"corrections_typed": [{"field": "bear_px", "from": 1, "to": 2, "basis": "x" * 900}],
                                                     "fact_disputes": [{"fact": "net debt"}]}})
    check("block: carries the typed corrections (basis capped) and the input disputes",
          b["disagreement_kind"] == "fact" and len(b["skeptic_corrections_typed"][0]["basis"]) == 400
          and b["fact_disputes"] == [{"fact": "net debt"}])

# ---- universe export scope: every debated name, nothing about what we hold
with tempfile.TemporaryDirectory() as td:
    rd = Path(td)
    for s, r in {"FULL": {}, "DELTA": {"deltas": []}, "CARRY": {"carried": True},
                 "RECHK": {"source": "ledger_recheck"}}.items():
        (rd / f"{s}.json").write_text(json.dumps(r), encoding="utf-8")
    got = X.debated_this_run(rd)
    check("export scope: full debates and seat updates in, carried and re-checks out", got == {"FULL", "DELTA"})

print(f"\n{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILED: {FAILS}'}")
sys.exit(1 if FAILS else 0)
