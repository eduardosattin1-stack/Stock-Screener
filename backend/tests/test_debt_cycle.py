#!/usr/bin/env python3
"""Tests for backend/debt_cycle.py — §8 fixture + state-machine legality.

Run: python backend/tests/test_debt_cycle.py
No network: exercises compute_debt_cycle / advance_state on fixed inputs only.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from debt_cycle import (  # noqa: E402
    compute_debt_cycle, advance_state, apply_phase_to_stance, duration_bucket,
    _parse_auction_rows, _score_auction_quality,
    PHASE_DURATION_CAPS, HYSTERESIS_PUBLISHES, _UNKNOWN_RESULT,
)

FAILURES = []


def check(name, cond, detail=""):
    status = "ok" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


# ── §8 worked fixture (market data 2026-07-24/26) ────────────────────────────
# 30y 5.16 / 3m 3.96 → 30y-3m +120bp; real 30y ≈ 5.16 - 2.26 = 2.90 (post-2010
# high); auctions meeting weaker demand; gold -27% from the Jan record.
FIXTURE = {
    "real_rate": 2.90, "real_delta_3m": +0.35,
    "rates_now": {"year30": 5.16, "month3": 3.96, "year10": 4.69, "year2": 4.33},
    "rates_3mo": {"year30": 4.82, "month3": 3.92, "year10": 4.41, "year2": 4.15},
    "auctions": [
        {"date": "2026-05-12", "term": "10y", "btc": 2.55, "indirect_pct": 0.68},
        {"date": "2026-05-13", "term": "30y", "btc": 2.42, "indirect_pct": 0.65},
        {"date": "2026-06-10", "term": "10y", "btc": 2.50, "indirect_pct": 0.66},
        {"date": "2026-06-11", "term": "30y", "btc": 2.38, "indirect_pct": 0.62},
        {"date": "2026-07-09", "term": "10y", "btc": 2.41, "indirect_pct": 0.61},
        {"date": "2026-07-10", "term": "30y", "btc": 2.30, "indirect_pct": 0.58},
    ],
    "debt_service_ratio": 0.19,
    "oas_now": 3.10, "oas_3mo": 2.85,       # HY OAS in percent (FRED style)
    "cb_pct_3m": -1.4,                       # QT continuing
    "gold_now": 4071.0, "gold_6mo": 5350.0,  # deep drawdown from the Jan record
}

print("\n=== §8 fixture — expected DISCIPLINE ===")
seed = {"phase": "DISCIPLINE", "weeks_in_phase": 21, "pending_target": None,
        "pending_count": 0, "seeded": False}
res, st = compute_debt_cycle(FIXTURE, seed, "2026-07-26", advance=True)
check("phase is DISCIPLINE", res["debt_cycle_phase"] == "DISCIPLINE", res["debt_cycle_phase"])
check("target is DISCIPLINE (no pending flap)", res["cycle_target"] == "DISCIPLINE", res["cycle_target"])
# 2026 tape maxes the discipline gauges (real rate, term premium, debt service)
# and can push the composite to ~0.70 — but with HY OAS ~310bp and auctions
# covering 2.3x there is NO live funding stress, so the FORCING gate must hold.
check("severe-DISCIPLINE composite with calm credit does NOT target FORCING",
      res["cycle_score"] >= 0.35 and res["cycle_target"] == "DISCIPLINE",
      f"score={res['cycle_score']} target={res['cycle_target']}")
check("weeks_in_phase ticked to 22", res["weeks_in_phase"] == 22, res["weeks_in_phase"])
check("confidence high (6/6 gauges live)", res["confidence"] == "high", res["confidence"])
check("gold drawdown reads CONSISTENT with DISCIPLINE",
      res["reserve_asset_check"]["consistent_with_phase"] is True, res["reserve_asset_check"])
check("caps: story<=20% cash_now>=35%",
      res["duration_caps"] == {"story_max": 0.20, "cash_now_min": 0.35}, res["duration_caps"])
check("horizon stretched to 18mo", res["expected_horizon_months"] == 18)
check("no transition blocked", res["transition_blocked"] is False)

print("\n=== state machine legality ===")
# DISCIPLINE + monetization-shaped dials → must route via FORCING, never jump
mon_inputs = dict(FIXTURE, real_delta_3m=-0.60, cb_pct_3m=+4.0,
                  oas_now=6.2, oas_3mo=4.0, debt_service_ratio=0.24)
st2 = {"phase": "DISCIPLINE", "weeks_in_phase": 30, "pending_target": None, "pending_count": 0}
r1, st2 = compute_debt_cycle(mon_inputs, st2, "2026-08-01", advance=True)
check("tick 1: hysteresis holds DISCIPLINE", r1["debt_cycle_phase"] == "DISCIPLINE", r1["debt_cycle_phase"])
check("tick 1: pending recorded", r1["pending_target"] == r1["cycle_target"] and r1["pending_count"] == 1,
      f"pending={r1['pending_target']}/{r1['pending_count']}")
r2, st2 = compute_debt_cycle(mon_inputs, st2, "2026-08-08", advance=True)
check("tick 2: moves ONE step only (to FORCING, not MONETIZATION)",
      r2["debt_cycle_phase"] == "FORCING", r2["debt_cycle_phase"])
if r2["cycle_target"] == "MONETIZATION":
    check("tick 2: illegal jump logged as blocked",
          r2["transition_blocked"] and r2["transition_implied"] == "MONETIZATION",
          f"blocked={r2['transition_blocked']} implied={r2['transition_implied']}")
check("tick 2: weeks_in_phase reset to 1", r2["weeks_in_phase"] == 1, r2["weeks_in_phase"])
check("tick 2: prior_phase recorded", r2["prior_phase"] == "DISCIPLINE", r2["prior_phase"])

# hysteresis: a one-tick flap must NOT move the state
st3 = {"phase": "EXPANSION", "weeks_in_phase": 10, "pending_target": None, "pending_count": 0}
calm = dict(FIXTURE, real_rate=0.4, real_delta_3m=0.0, debt_service_ratio=0.07,
            oas_now=2.6, oas_3mo=2.7, cb_pct_3m=0.0,
            rates_now={"year30": 3.4, "month3": 3.2}, rates_3mo={"year30": 3.4, "month3": 3.2},
            auctions=[dict(a, btc=2.6) for a in FIXTURE["auctions"]])
hot_once = dict(FIXTURE)
_, st3 = compute_debt_cycle(hot_once, st3, "2026-08-01", advance=True)   # 1 hot tick
rr, st3 = compute_debt_cycle(calm, st3, "2026-08-08", advance=True)      # back to calm
check(f"hysteresis needs {HYSTERESIS_PUBLISHES} consecutive — flap stays EXPANSION",
      rr["debt_cycle_phase"] == "EXPANSION", rr["debt_cycle_phase"])

print("\n=== fail-open + stance modifier + duration bucket ===")
check("UNKNOWN carries the loosest caps",
      _UNKNOWN_RESULT["duration_caps"] == PHASE_DURATION_CAPS["EXPANSION"] == {"story_max": 0.40})
check("DISCIPLINE caps aggressive→balanced", apply_phase_to_stance("aggressive", "DISCIPLINE")[0] == "balanced")
check("FORCING floors balanced→defensive", apply_phase_to_stance("balanced", "FORCING")[0] == "defensive")
check("MONETIZATION unlocks defensive→aggressive", apply_phase_to_stance("defensive", "MONETIZATION")[0] == "aggressive")
check("UNKNOWN phase is a stance no-op", apply_phase_to_stance("aggressive", "UNKNOWN")[0] == "aggressive")
check("EXPANSION leaves stance alone", apply_phase_to_stance("aggressive", "EXPANSION")[0] == "aggressive")

check("bucket: p_fcf 18 → cash_now", duration_bucket({"p_fcf": 18.0})["duration_bucket"] == "cash_now")
check("bucket: p_fcf 40 → payback_2_3y", duration_bucket({"p_fcf": 40.0})["duration_bucket"] == "payback_2_3y")
check("bucket: MEASURED negative FCF → story",
      duration_bucket({"p_fcf": 0.0, "fcf_margin": -0.1})["duration_bucket"] == "story")
# The fail-open split: screener_v6 defaults both fields to 0.0, so 'no data' and
# 'genuinely no FCF' are byte-identical. Only the latter may be capped.
check("bucket: NO FCF data → unknown (not story)",
      duration_bucket({})["duration_bucket"] == "unknown"
      and duration_bucket({"p_fcf": 0.0, "fcf_margin": 0.0})["duration_bucket"] == "unknown")
check("unknown carries a no_fcf_data provenance flag",
      duration_bucket({})["duration_bucket_source"] == "no_fcf_data")
_story_rec = {"p_fcf": 0.0, "fcf_margin": -0.08}
ov = duration_bucket(_story_rec, override="payback_2_3y", override_reason="consensus FCF+ Q2 FY27 (2026-07-20 guide)")
check("director override with justification honored + provenance kept",
      ov["duration_bucket"] == "payback_2_3y" and ov["duration_bucket_computed"] == "story"
      and ov["duration_bucket_source"] == "director_override")
ov2 = duration_bucket(_story_rec, override="cash_now", override_reason="")
check("override WITHOUT justification rejected",
      ov2["duration_bucket"] == "story" and ov2.get("duration_bucket_override_rejected") == "cash_now")

print("\n=== TreasuryDirect auction parser (FORK 3/A) ===")
# Realistic TA_WS payload: numbers arrive as STRINGS, and 10y/30y originals are sold
# quarterly then REOPENED monthly — a reopening's securityTerm is fractional, so
# matching securityTerm alone silently drops ~2/3 of the auctions that matter.
TD_PAYLOAD = [
    {"cusip": "91282CLM1", "securityType": "Note", "securityTerm": "10-Year",
     "originalSecurityTerm": "10-Year", "auctionDate": "2026-05-12",
     "bidToCoverRatio": "2.55", "indirectBidderAccepted": "26520000000", "totalAccepted": "39000000000"},
    {"cusip": "91282CLM1", "securityType": "Note", "securityTerm": "9-Year 10-Month",
     "originalSecurityTerm": "10-Year", "auctionDate": "2026-06-10",
     "bidToCoverRatio": "2.50", "indirectBidderAccepted": "25740000000", "totalAccepted": "39000000000"},
    {"cusip": "91282CLM1", "securityType": "Note", "securityTerm": "9-Year 9-Month",
     "originalSecurityTerm": "10-Year", "auctionDate": "2026-07-09",
     "bidToCoverRatio": "2.41", "indirectBidderAccepted": "23790000000", "totalAccepted": "39000000000"},
    {"cusip": "912810UF3", "securityType": "Bond", "securityTerm": "30-Year",
     "originalSecurityTerm": "30-Year", "auctionDate": "2026-05-13",
     "bidToCoverRatio": "2.42", "indirectBidderAccepted": "14300000000", "totalAccepted": "22000000000"},
    {"cusip": "912810UF3", "securityType": "Bond", "securityTerm": "29-Year 11-Month",
     "originalSecurityTerm": "30-Year", "auctionDate": "2026-06-11",
     "bidToCoverRatio": "2.38", "indirectBidderAccepted": "13640000000", "totalAccepted": "22000000000"},
    {"cusip": "912810UF3", "securityType": "Bond", "securityTerm": "29-Year 10-Month",
     "originalSecurityTerm": "30-Year", "auctionDate": "2026-07-10",
     "bidToCoverRatio": "2.30", "indirectBidderAccepted": "12760000000", "totalAccepted": "22000000000"},
    # must be ignored: wrong tenors
    {"cusip": "912797XX1", "securityType": "Bill", "securityTerm": "4-Week",
     "originalSecurityTerm": "4-Week", "auctionDate": "2026-07-21", "bidToCoverRatio": "2.90"},
    {"cusip": "91282CLL3", "securityType": "Note", "securityTerm": "2-Year",
     "originalSecurityTerm": "2-Year", "auctionDate": "2026-07-22", "bidToCoverRatio": "2.60"},
    {"cusip": "912828ZZ9", "securityType": "Note", "securityTerm": "20-Year",
     "originalSecurityTerm": "20-Year", "auctionDate": "2026-07-15", "bidToCoverRatio": "2.45"},
    # must be ignored: no bid-to-cover
    {"cusip": "91282CLM9", "securityType": "Note", "securityTerm": "10-Year",
     "originalSecurityTerm": "10-Year", "auctionDate": "2026-04-08", "bidToCoverRatio": ""},
]
parsed = _parse_auction_rows(TD_PAYLOAD)
check("keeps 10y+30y originals AND reopenings (6 rows)", len(parsed) == 6, f"{len(parsed)}")
check("reopenings retained and flagged",
      sum(1 for r in parsed if r["reopening"]) == 4, f"{[r['reopening'] for r in parsed]}")
check("2y / 20y / 4-week bills excluded",
      all(r["term"] in ("10y", "30y") for r in parsed), f"{[r['term'] for r in parsed]}")
check("term label is clean (10y / 30y, not '10-Yy')",
      sorted({r["term"] for r in parsed}) == ["10y", "30y"], f"{sorted({r['term'] for r in parsed})}")
check("string numerics coerced", isinstance(parsed[0]["btc"], float) and parsed[0]["btc"] > 0)
check("indirect share computed", abs(parsed[0]["indirect_pct"] - 0.68) < 0.01, f"{parsed[0]['indirect_pct']}")
check("auction with no bid-to-cover dropped", all(r["date"] != "2026-04-08" for r in parsed))
check("sorted oldest-first", [r["date"] for r in parsed] == sorted(r["date"] for r in parsed))
check("6 parsed rows clear the >=5 minimum the gauge needs",
      _score_auction_quality(parsed) is not None, "gauge returned None")
check("softening demand scores as DISCIPLINE evidence, not FORCING (<0.7)",
      0.4 < _score_auction_quality(parsed) < 0.7, f"{_score_auction_quality(parsed)}")
check("empty/garbage payload is safe",
      _parse_auction_rows([]) == [] and _parse_auction_rows(None) == []
      and _parse_auction_rows([{"junk": 1}]) == [])

print("\n=== duration cap (FORK 2/B) — portion control, not eligibility ===")
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_opus_debate"))
    import _regime_post as rp
    import _post_common as pc

    cap_picks = [
        {"symbol": "AAA", "director_conviction": 92, "size_units": 1.4, "duration_bucket": "cash_now"},
        {"symbol": "BBB", "director_conviction": 78, "size_units": 1.1, "duration_bucket": "cash_now"},
        {"symbol": "CCC", "director_conviction": 71, "size_units": 1.1, "duration_bucket": "payback_2_3y"},
        {"symbol": "DDD", "director_conviction": 85, "size_units": 1.1, "duration_bucket": "story"},
        {"symbol": "EEE", "director_conviction": 64, "size_units": 0.8, "duration_bucket": "story"},
        {"symbol": "FFF", "director_conviction": 55, "size_units": 0.8, "duration_bucket": "story"},
    ]
    apx = {"apex_basket": cap_picks}
    memo = {p["symbol"]: pc.banded_units(p["director_conviction"]) for p in cap_picks}
    cyc = {"debt_cycle_phase": "DISCIPLINE", "duration_caps": {"story_max": 0.20, "cash_now_min": 0.35}}
    # process() order: build_weights FIRST (the cap reads size_units_effective as its basis),
    # then derive caps, then re-run build_weights with them appended.
    pc.build_weights(apx, cap_picks, extra_caps=[], memo_units=memo, per_name_cap=pc.moat_per_name_cap)
    entries = rp.duration_cap_entries(apx, cap_picks, cyc)
    w = pc.build_weights(apx, cap_picks, extra_caps=entries, memo_units=memo,
                         per_name_cap=pc.moat_per_name_cap)
    story_share = sum(w[p["symbol"]] for p in cap_picks if p["duration_bucket"] == "story")
    story_units = sum(p["size_units_effective"] for p in cap_picks if p["duration_bucket"] == "story")
    tot_units = sum(p["size_units_effective"] for p in cap_picks)
    # The cap ALWAYS bites the units (the audit trail). Whether it reaches the PUBLISHED
    # weight depends on _post_common.EQUAL_WEIGHT_BOOKS (Bruno's 2026-07-24 call: every book
    # publishes 1/n because Director conviction showed no monotone relation to forward
    # return). Under equal weight the duration cap — like the secular-theme and correlation
    # caps — is auditable but does not move money. Assert both truths explicitly rather than
    # letting one silently mask the other.
    check("story UNITS trimmed to the DISCIPLINE cap (audit trail always bites)",
          story_units / tot_units <= 0.20 + 1e-6, f"{story_units / tot_units:.4f}")
    if getattr(pc, "EQUAL_WEIGHT_BOOKS", False):
        check("EQUAL_WEIGHT_BOOKS on => published weights stay 1/n (cap is ADVISORY)",
              all(abs(w[p["symbol"]] - 1.0 / len(cap_picks)) < 1e-3 for p in cap_picks),
              f"story weight share {story_share:.2f} vs units share {story_units / tot_units:.2f}")
        check("cap self-labels as advisory so the UI cannot imply weight moved",
              apx.get("duration_cap_effect") == "advisory"
              and all(p.get("cycle_cap_effect") == "advisory"
                      for p in cap_picks if p.get("cycle_capped")),
              f"{apx.get('duration_cap_effect')}")
        print("      note: duration cap does NOT move published weight while EQUAL_WEIGHT_BOOKS=True")
    else:
        check("story WEIGHT share trimmed to the DISCIPLINE cap",
              story_share <= 0.20 + 1e-6, f"{story_share:.4f}")
    check("cap emitted in the shared extra_caps schema",
          all(set(e) >= {"names", "max_units", "axis"} and e["axis"] == "duration:story" for e in entries))
    check("lowest-conviction story seats hit the 0.1u floor first",
          cap_picks[4]["size_units_effective"] == 0.1 and cap_picks[5]["size_units_effective"] == 0.1)
    check("highest-conviction story seat keeps the most",
          cap_picks[3]["size_units_effective"] > cap_picks[4]["size_units_effective"],
          f"DDD={cap_picks[3]['size_units_effective']} EEE={cap_picks[4]['size_units_effective']}")
    check("NO name demoted — cap is a weight action only", len(apx["apex_basket"]) == 6)
    check("trimmed seats badged for the UI",
          all(p.get("cycle_capped") and p.get("cycle_cap_note") for p in cap_picks[3:6]))
    check("untrimmed seats carry no badge", not any(p.get("cycle_capped") for p in cap_picks[:3]))
    check("cap_binding recorded", apx.get("cap_binding") == ["duration_story"])
    # NOTE: build_weights rounds each weight to 4dp, so the sum can land on 0.9999 for
    # units that don't divide cleanly. Pre-existing + shared with the value book (a bare
    # [1.4,1.1,0.8] basket drifts identically) — asserted at the repo's real guarantee.
    check("weights renormalize (4dp rounding tolerance)", abs(sum(w.values()) - 1.0) < 1e-3,
          f"{sum(w.values())}")

    # UNKNOWN phase = LOOSEST caps (40%), not "no caps" — it must trim strictly less
    # than DISCIPLINE on the identical book.
    def _fresh(phase, caps=None):
        ps = [dict(p) for p in cap_picks]
        for p in ps:
            p.pop("cycle_capped", None); p.pop("cycle_cap_note", None)
            p["size_units_effective"] = p["size_units"]
        a = {"apex_basket": ps}
        cy = {"debt_cycle_phase": phase}
        if caps:
            cy["duration_caps"] = caps
        return a, ps, rp.duration_cap_entries(a, ps, cy)

    _, u_picks, u_entries = _fresh("UNKNOWN")
    u_trim = sum(1 for p in u_picks if p.get("cycle_capped"))
    check("UNKNOWN phase uses the LOOSEST caps (trims less than DISCIPLINE)",
          u_trim < 3, f"UNKNOWN trimmed {u_trim} seats")

    # FAIL-OPEN REGRESSION (caught by test_regime_post 2026-07-27): a book whose scan
    # records carry NO cash-flow data must NOT be pinned to the floor. Before the
    # story/unknown split, every no-data name defaulted to 'story' and DISCIPLINE
    # slammed the whole book to 0.1u — a data gap tightening the book.
    nodata = []
    for p in cap_picks:
        q = {k: v for k, v in p.items() if k not in ("cycle_capped", "cycle_cap_note")}
        q["duration_bucket"] = duration_bucket({})["duration_bucket"]   # no scan FCF data
        q["size_units_effective"] = q["size_units"]
        nodata.append(q)
    check("no FCF data => 'unknown', never 'story'",
          all(p["duration_bucket"] == "unknown" for p in nodata), nodata[0]["duration_bucket"])
    nd_entries = rp.duration_cap_entries({"apex_basket": nodata}, nodata,
                                         {"debt_cycle_phase": "DISCIPLINE",
                                          "duration_caps": {"story_max": 0.20}})
    check("a no-FCF-data book is NOT trimmed by the story cap (fail-open)",
          nd_entries == [] and not any(p.get("cycle_capped") for p in nodata), f"{nd_entries}")
except Exception as e:  # pragma: no cover
    check("duration cap section importable", False, f"{type(e).__name__}: {e}")

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} — {FAILURES}")
    sys.exit(1)
print("ALL PASS")
