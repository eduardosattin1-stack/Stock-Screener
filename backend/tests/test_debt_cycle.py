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
check("bucket: no FCF → story", duration_bucket({"p_fcf": 0.0, "fcf_margin": -0.1})["duration_bucket"] == "story")
ov = duration_bucket({"p_fcf": 0.0}, override="payback_2_3y", override_reason="consensus FCF+ Q2 FY27 (2026-07-20 guide)")
check("director override with justification honored + provenance kept",
      ov["duration_bucket"] == "payback_2_3y" and ov["duration_bucket_computed"] == "story"
      and ov["duration_bucket_source"] == "director_override")
ov2 = duration_bucket({"p_fcf": 0.0}, override="cash_now", override_reason="")
check("override WITHOUT justification rejected",
      ov2["duration_bucket"] == "story" and ov2.get("duration_bucket_override_rejected") == "cash_now")

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} — {FAILURES}")
    sys.exit(1)
print("ALL PASS")
