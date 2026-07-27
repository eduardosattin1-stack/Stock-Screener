#!/usr/bin/env python3
"""Dalio commodity playbook — the phase/quadrant -> commodity-family TILT tables.

FUTURE_RESOURCES_SPLIT_SPEC.md §1 (the Dalio layer). This module is the SINGLE SOURCE OF TRUTH for
the tilt: `mining-macro` renders it into commodity_macro.json (which the /commodities page displays)
and `mining-input` injects `director_brief()` into the Mining Director prompt. Page and Director
therefore read ONE table and cannot drift — the first draft of this design hardcoded a second copy
in the frontend and it had already diverged before a line shipped.

WHAT THIS MODULE IS NOT (all deliberate, all load-bearing):
  - NOT a classifier. It computes no phase, no quadrant, no score. `backend/debt_cycle.py` stays the
    only phase authority and `weekly_opus_refresh._write_macro_regime` its only advancing call site.
  - NOT a data consumer. PURE CONSTANTS over (phase, quadrant) — it imports no requests/fetcher/
    network module and reads no market series. That is the structural guarantee behind the gold seam
    (CLAUDE.md: gold is a falsification check ONLY, never a scored input; the momentum-loop guard
    that would have bought the Jan-2026 top). Displayed gold dials CANNOT reach the tilt because the
    tilt has no inputs to smuggle them through. Test 3 asserts the import graph; keep it true.
  - NOT a sizing input. No deterministic consumer may map 'tailwind'/'headwind' to units, weights,
    floors or eligibility. The tilt reaches the book ONLY as Director judgement + display, via the
    FORK-2/B channels (advisory stance, entry-discount floor, horizon stretch, phase_fit).

FAIL-OPEN: an unknown/missing phase or quadrant yields `neutral`, never `headwind`. A data outage
must never paint a family bearish — the display analog of "a data gap must never tighten the book".

Usage:
    python _commodity_tilt.py            # resolved tilt for the current snapshot
    python _commodity_tilt.py brief      # the Director text block (what the Director will cite)
"""
import json
import os

# Family keys MUST equal the Mining chain ids in _opus_debate/mining_chains.json (test-enforced:
# set equality both directions, so a taxonomy rename can never silently orphan a tilt row).
FAMILIES = ("uranium_fuel_cycle", "copper_mining", "precious_metals",
            "rare_earth_strategic", "diversified_miners")

TAILWIND, MIXED, HEADWIND, NEUTRAL = "tailwind", "mixed", "headwind", "neutral"

# ── Axis 1: Dalio debt-cycle phase (backend/debt_cycle.py) ────────────────────────────────────────
PHASE_COMMODITY_TILT = {
    "EXPANSION": {
        "favored": ["copper_mining", "diversified_miners", "uranium_fuel_cycle"],
        "disfavored": ["precious_metals"],
        "gold_role": "Underweight — positive-but-CHOSEN real rates are gold's opportunity cost; "
                     "no monetary premium while credit is freely extended.",
        "dalio_note": "Borrowing is accommodated: own what a growing economy consumes, not what a "
                      "breaking one hedges.",
    },
    "DISCIPLINE": {
        "favored": ["diversified_miners", "copper_mining", "precious_metals"],
        "disfavored": [],
        "gold_role": "Headwind at the METAL level — imposed positive real rates compete with a "
                     "zero-yield asset. Royalties survive on FCF; the gold price does not have to "
                     "rise for them to pay.",
        "dalio_note": "Real rates are being imposed by the bond market: payback speed beats resource "
                      "optionality. Favor cash-generative producers and royalty/streaming models in "
                      "EVERY family; development-stage story names are the disfavored cohort here, "
                      "not any particular metal. Real assets NOT YET — that trade belongs to "
                      "MONETIZATION, and buying it early is the classic misread of this phase.",
    },
    "FORCING": {
        "favored": ["precious_metals", "diversified_miners"],
        "disfavored": ["rare_earth_strategic", "copper_mining"],
        "gold_role": "Two-sided — sold in the margin-call liquidation, then FIRST re-bid as the "
                     "market front-runs the monetization response.",
        "dalio_note": "Funding stress liquidates the complex indiscriminately; survivorship is the "
                      "only edge. Fortress balance sheets only — royalty/streamers (no debt, "
                      "contractual cash) and lowest-cost majors. Anything that needs capital markets "
                      "(juniors, developers, high-cost producers) is the wrong side of this phase. "
                      "Reaches suspended, not resized.",
    },
    "MONETIZATION": {
        "favored": ["precious_metals", "copper_mining", "diversified_miners", "uranium_fuel_cycle"],
        "disfavored": [],
        "gold_role": "THE phase gold exists for — real rates forced negative while the central bank "
                     "absorbs supply; the monetary premium expands.",
        "dalio_note": "The printing phase: currency debasement re-prices everything hard. Paper-claim "
                      "duration is the loser, not commodities. This is where the real-asset trade is "
                      "EARNED, not anticipated.",
    },
    "UNKNOWN": {
        "favored": [], "disfavored": [],
        "gold_role": "No phase read — no gold prior.",
        "dalio_note": "Fail-open: loosest caps, no tilt, banner on the page.",
    },
}

# ── Axis 2: growth x inflation quadrant (backend/macro_regime.py) ─────────────────────────────────
QUADRANT_COMMODITY_TILT = {
    "GOLDILOCKS": {
        "favored": ["copper_mining", "uranium_fuel_cycle"],
        "disfavored": ["precious_metals"],
        "note": "Growth up, inflation cooling — demand-linked metals carry on volume (electrification, "
                "AI power); monetary metals lack a driver.",
    },
    "REFLATION": {
        "favored": ["copper_mining", "diversified_miners", "rare_earth_strategic"],
        "disfavored": [],
        "note": "The classic commodity quadrant: growth up + inflation hot, industrial metals lead the "
                "complex; gold participates but does not lead.",
    },
    "STAGFLATION": {
        "favored": ["precious_metals"],
        "disfavored": ["copper_mining", "diversified_miners"],
        "note": "Pricing power and real assets only — decelerating growth hits volume-linked miners "
                "while sticky inflation feeds the monetary metals.",
    },
    "RISK_OFF": {
        "favored": ["precious_metals"],
        "disfavored": ["copper_mining", "diversified_miners", "uranium_fuel_cycle",
                       "rare_earth_strategic"],
        "note": "Disinflationary slowdown: falling real rates make gold a duration proxy (royalties "
                "especially, on FCF carry); the rest of the complex trades with recession odds.",
    },
    "UNKNOWN": {"favored": [], "disfavored": [], "note": "No quadrant read — axis omitted."},
}


def _axis(table, key):
    """A tilt row, fail-open: unknown/missing/None key -> the empty UNKNOWN row (no favored, no
    disfavored), so an outage degrades to `neutral` rather than inventing a headwind."""
    return table.get(str(key or "UNKNOWN").upper().strip(), table["UNKNOWN"])


def resolve_tilt(phase, quadrant):
    """{family: tailwind|mixed|headwind|neutral} for all five families.

    Resolution (deliberately asymmetric — a disfavor on EITHER axis wins):
      - disfavored on either axis                    -> headwind
      - favored on BOTH axes                         -> tailwind
      - favored on exactly one, disfavored on neither -> mixed
      - named by neither axis                        -> neutral
    Where the axes disagree (DISCIPLINE x REFLATION, say) the family lands `mixed` and the page
    highlights BOTH rows, so the tension stays visible instead of being averaged away.
    """
    p, q = _axis(PHASE_COMMODITY_TILT, phase), _axis(QUADRANT_COMMODITY_TILT, quadrant)
    pf, pd = set(p["favored"]), set(p["disfavored"])
    qf, qd = set(q["favored"]), set(q["disfavored"])
    out = {}
    for fam in FAMILIES:
        if fam in pd or fam in qd:
            out[fam] = HEADWIND
        elif fam in pf and fam in qf:
            out[fam] = TAILWIND
        elif fam in pf or fam in qf:
            out[fam] = MIXED
        else:
            out[fam] = NEUTRAL
    return out


def tilt_payload(phase, quadrant):
    """The block `mining-macro` embeds in commodity_macro.json — BOTH full tables plus the resolved
    row. The page renders from this and only this (there is no frontend copy of the playbook)."""
    return {
        "phase": str(phase or "UNKNOWN").upper(),
        "quadrant": str(quadrant or "UNKNOWN").upper(),
        "families": list(FAMILIES),
        "phase_table": PHASE_COMMODITY_TILT,
        "quadrant_table": QUADRANT_COMMODITY_TILT,
        "resolved": resolve_tilt(phase, quadrant),
        "legend": {
            "tailwind": "favored by both the debt-cycle phase and the growth/inflation quadrant",
            "mixed": "favored by one axis; the axes disagree or only one speaks",
            "headwind": "disfavored by at least one axis",
            "neutral": "named by neither axis (or no macro read — fail-open)",
        },
        "display_only_note": "Dalio playbook priors. DISPLAY + Director judgement ONLY — never a "
                             "sizing, eligibility or conviction input (FUTURE_RESOURCES_SPLIT_SPEC "
                             "§1.4). Gold reaches nothing here: this table has no data inputs.",
    }


def _snapshot(path=None):
    """The v7 macro snapshot written by weekly_opus_refresh._write_macro_regime. Missing/unreadable
    -> {} (callers then resolve UNKNOWN x UNKNOWN = all-neutral)."""
    p = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "macro_regime.json")
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def director_brief(snapshot):
    """Prompt-ready text injected verbatim into the Mining Director (mining-input builds it).

    States the live phase + quadrant, BOTH playbook rows, the resolved per-family tilt, gold's role,
    and the reserve-asset falsification note — then the citation rule. Never returns an empty string:
    with no snapshot it prints the UNKNOWN row and says the macro layer is degraded."""
    snap = snapshot or {}
    dc = snap.get("debt_cycle") or {}
    phase = dc.get("debt_cycle_phase") or "UNKNOWN"
    quadrant = snap.get("quadrant") or "UNKNOWN"
    p, q = _axis(PHASE_COMMODITY_TILT, phase), _axis(QUADRANT_COMMODITY_TILT, quadrant)
    res = resolve_tilt(phase, quadrant)
    rac = dc.get("reserve_asset_check") or {}
    consistent = rac.get("consistent_with_phase")
    rac_line = ("gold/reserve-asset falsification check: "
                + ("CONSISTENT with the phase call" if consistent is True
                   else "INCONSISTENT — the phase call may be early or late; treat it as a raised "
                        "falsifier, not a refutation" if consistent is False
                   else "skipped (no gold data)")
                + (f" — {rac['note']}" if rac.get("note") else ""))
    degraded = []
    if phase == "UNKNOWN" or snap.get("fallback"):
        degraded.append("no debt-cycle phase read")
    if quadrant == "UNKNOWN":
        degraded.append("no growth/inflation quadrant")
    if dc.get("seeded"):
        degraded.append("phase is a SEEDED prior, not yet earned by the state machine")
    if dc.get("confidence") == "low":
        degraded.append("phase confidence LOW (few live gauges)")

    lines = [
        "COMMODITY MACRO — THE DALIO PLAYBOOK (cited-only; see the citation rule at the end)",
        f"Live read: debt-cycle phase {phase} | growth x inflation quadrant {quadrant}"
        + (f" | risk regime {snap.get('regime')}" if snap.get("regime") else ""),
        f"  quadrant basis: {snap['quadrant_basis']}" if snap.get("quadrant_basis") else "",
        f"  phase basis: {dc['phase_basis']}" if dc.get("phase_basis") else "",
        f"  weeks in phase: {dc['weeks_in_phase']}" if dc.get("weeks_in_phase") is not None else "",
        "",
        f"PHASE ROW ({phase}):",
        f"  favored: {', '.join(p['favored']) or '(none)'}",
        f"  disfavored: {', '.join(p['disfavored']) or '(none)'}",
        f"  gold's role: {p['gold_role']}",
        f"  Dalio note: {p['dalio_note']}",
        "",
        f"QUADRANT ROW ({quadrant}):",
        f"  favored: {', '.join(q['favored']) or '(none)'}",
        f"  disfavored: {', '.join(q['disfavored']) or '(none)'}",
        f"  note: {q['note']}",
        "",
        "RESOLVED TILT (a disfavor on EITHER axis wins; both-favored = tailwind; axes disagreeing = mixed):",
    ]
    lines += [f"  {fam}: {res[fam].upper()}" for fam in FAMILIES]
    lines += [
        "",
        rac_line,
    ]
    if degraded:
        lines += ["",
                  "MACRO LAYER DEGRADED — " + "; ".join(degraded)
                  + ". Fail-open: treat unnamed families as NEUTRAL and do NOT read a headwind into "
                    "the gap. Say so in the memo."]
    lines += [
        "",
        "HOW TO USE THIS (hard rules — violating any is a non-conforming slate):",
        "  - CITE the tilt in your memo and in each pick's phase_fit. A story-duration developer "
        "seated in DISCIPLINE must say so and own it.",
        "  - The tilt NEVER decides membership and NEVER moves conviction. A HEADWIND family may "
        "absolutely be seated on name-specific merit — say why.",
        "  - A phase or tilt citation is NOT a valid delta_justification for a conviction move "
        "(_regime_post._dated_fact_outside_phase enforces this downstream; unjustified moves are "
        "reverted).",
        "  - The tilt reaches the book ONLY through: your risk_stance, the entry-discount floor, the "
        "horizon stretch, and phase_fit judgement. Nothing else.",
    ]
    return "\n".join(x for x in lines if x != "" or True).strip()


def main(argv=None):
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    snap = _snapshot()
    dc = snap.get("debt_cycle") or {}
    phase, quadrant = dc.get("debt_cycle_phase") or "UNKNOWN", snap.get("quadrant") or "UNKNOWN"
    if argv and argv[0] == "brief":
        print(director_brief(snap))
        return 0
    print(f"phase={phase} quadrant={quadrant}"
          + ("  (NO SNAPSHOT — showing the fail-open all-neutral resolution)" if not snap else ""))
    for fam, label in resolve_tilt(phase, quadrant).items():
        print(f"  {fam:<24} {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
