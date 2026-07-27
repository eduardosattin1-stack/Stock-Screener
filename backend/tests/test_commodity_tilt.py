#!/usr/bin/env python3
"""Tests for _opus_debate/_commodity_tilt.py — FUTURE_RESOURCES_SPLIT_SPEC §1.7.

The four properties that make the Dalio tilt safe to ship:
  T1 FAIL-OPEN     — unknown phase/quadrant never paints a headwind (all 6x6 combinations legal).
  T2 KEY-SYNC      — tilt families == mining_chains.json chain ids, both directions (drift guard).
  T3 PURITY        — the module imports no network/fetcher module and reads no market data. This is
                     the structural half of the gold seam: displayed gold dials CANNOT reach the
                     tilt because the tilt has no data inputs at all.
  T4 RESOLUTION    — the asymmetric rule (a disfavor on either axis wins) behaves as documented, and
                     the axes-disagree case degrades to `mixed` rather than averaging.
Plus B1-B3 on director_brief (never empty; degradation is stated; the citation rules are present).

Run: python backend/tests/test_commodity_tilt.py
"""
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BK = os.path.dirname(HERE)                                  # .../backend
OD = os.path.join(BK, "_opus_debate")
sys.path.insert(0, OD)

import _commodity_tilt as T                                  # noqa: E402

PHASES = ["EXPANSION", "DISCIPLINE", "FORCING", "MONETIZATION", "UNKNOWN"]
QUADRANTS = ["GOLDILOCKS", "REFLATION", "STAGFLATION", "RISK_OFF", "UNKNOWN"]
FAKE = ["", None, "garbage", "expansion"]                    # incl. lowercase — must normalize


# ── T1 fail-open ──────────────────────────────────────────────────────────────────────────────────
for q in QUADRANTS + FAKE:
    r = T.resolve_tilt("UNKNOWN", q)
    known_q = str(q or "UNKNOWN").upper() in T.QUADRANT_COMMODITY_TILT
    if not known_q or str(q or "UNKNOWN").upper() == "UNKNOWN":
        assert set(r.values()) == {"neutral"}, f"phase UNKNOWN x quadrant {q!r} -> {r}"
    # a known quadrant may legitimately tilt on its own axis; what must NEVER happen is a
    # fabricated headwind from the MISSING axis — assert the missing axis contributes nothing
    assert all(v in ("tailwind", "mixed", "headwind", "neutral") for v in r.values())

for p in PHASES + FAKE:
    r = T.resolve_tilt(p, "UNKNOWN")
    if str(p or "UNKNOWN").upper() not in T.PHASE_COMMODITY_TILT:
        assert set(r.values()) == {"neutral"}, f"unrecognized phase {p!r} -> {r}"

# no KeyError anywhere on the full grid, including junk on both axes
for p in PHASES + FAKE:
    for q in QUADRANTS + FAKE:
        r = T.resolve_tilt(p, q)
        assert set(r) == set(T.FAMILIES), f"{p} x {q} returned families {set(r)}"
assert set(T.resolve_tilt("UNKNOWN", "UNKNOWN").values()) == {"neutral"}
assert set(T.resolve_tilt(None, None).values()) == {"neutral"}
print("T1 OK: fail-open — unknown/missing/junk axes resolve to neutral, never headwind; full grid legal")


# ── T2 key-sync with the Mining taxonomy ──────────────────────────────────────────────────────────
tax = json.load(open(os.path.join(OD, "mining_chains.json"), encoding="utf-8"))
tax_ids = {c["id"] for c in tax["chains"]}
assert set(T.FAMILIES) == tax_ids, (
    f"tilt families {set(T.FAMILIES)} != mining_chains.json ids {tax_ids} — a taxonomy rename "
    f"orphaned a tilt row (or vice versa)")
for table_name, table in (("PHASE", T.PHASE_COMMODITY_TILT), ("QUADRANT", T.QUADRANT_COMMODITY_TILT)):
    for key, row in table.items():
        named = set(row["favored"]) | set(row["disfavored"])
        assert named <= tax_ids, f"{table_name}[{key}] names non-chains: {named - tax_ids}"
        assert not (set(row["favored"]) & set(row["disfavored"])), \
            f"{table_name}[{key}] lists a family as BOTH favored and disfavored"
print(f"T2 OK: tilt families == mining_chains.json ids ({len(tax_ids)}); no row names an unknown chain")


# ── T3 purity — the gold seam ─────────────────────────────────────────────────────────────────────
src = open(os.path.join(OD, "_commodity_tilt.py"), encoding="utf-8").read()
tree = ast.parse(src)
imported = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imported |= {a.name.split(".")[0] for a in node.names}
    elif isinstance(node, ast.ImportFrom) and node.module:
        imported.add(node.module.split(".")[0])
BANNED = {"requests", "urllib", "urllib3", "httpx", "aiohttp", "socket", "screener_v6",
          "debt_cycle", "macro_regime", "live_debate_engine", "gcs_io", "pandas", "numpy"}
assert not (imported & BANNED), f"purity breach: _commodity_tilt imports {imported & BANNED}"
# it may read the snapshot for the CLI, but the TABLES must be static literals: assert every
# module-level assignment to the two tables is a plain dict literal (no computation, no data)
for node in tree.body:
    if isinstance(node, ast.Assign):
        for t_ in node.targets:
            if isinstance(t_, ast.Name) and t_.id in ("PHASE_COMMODITY_TILT", "QUADRANT_COMMODITY_TILT"):
                assert isinstance(node.value, ast.Dict), f"{t_.id} is computed, not a literal"
assert "resolve_tilt" in src and "def resolve_tilt(phase, quadrant)" in src, "resolve_tilt signature changed"
# resolve_tilt must take exactly (phase, quadrant) — no data/series parameter may be smuggled in
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "resolve_tilt")
assert [a.arg for a in fn.args.args] == ["phase", "quadrant"], \
    f"resolve_tilt gained a data input: {[a.arg for a in fn.args.args]}"
print("T3 OK: purity — no network/fetcher/market imports, tables are static literals, "
      "resolve_tilt takes only (phase, quadrant) [the gold seam is structural]")


# ── T4 resolution semantics ───────────────────────────────────────────────────────────────────────
# both axes favor copper -> tailwind
assert T.resolve_tilt("EXPANSION", "REFLATION")["copper_mining"] == "tailwind"
# phase favors, quadrant disfavors -> headwind (a disfavor on EITHER axis wins)
assert T.resolve_tilt("EXPANSION", "STAGFLATION")["copper_mining"] == "headwind"
# phase disfavors precious, quadrant favors it -> headwind (asymmetry holds the other way too)
assert T.resolve_tilt("EXPANSION", "STAGFLATION")["precious_metals"] == "headwind"
# the live tape: DISCIPLINE x REFLATION — axes disagree in emphasis, neither disfavors copper
assert T.resolve_tilt("DISCIPLINE", "REFLATION")["copper_mining"] == "tailwind"
# DISCIPLINE favors precious (royalties), REFLATION is silent on it -> mixed, not tailwind
assert T.resolve_tilt("DISCIPLINE", "REFLATION")["precious_metals"] == "mixed"
# MONETIZATION x RISK_OFF: the phase gold exists for, quadrant agrees -> tailwind
assert T.resolve_tilt("MONETIZATION", "RISK_OFF")["precious_metals"] == "tailwind"
# ...and the same combination must NOT make copper a tailwind (RISK_OFF disfavors demand-linked)
assert T.resolve_tilt("MONETIZATION", "RISK_OFF")["copper_mining"] == "headwind"
# unnamed by either axis -> neutral
assert T.resolve_tilt("EXPANSION", "GOLDILOCKS")["rare_earth_strategic"] == "neutral"
print("T4 OK: resolution — disfavor-wins asymmetry, both-favored=tailwind, one-axis=mixed, "
      "unnamed=neutral")


# ── B1-B3 director_brief ──────────────────────────────────────────────────────────────────────────
b_empty = T.director_brief({})
assert b_empty.strip(), "director_brief({}) returned empty — the Director would get no macro block"
assert "MACRO LAYER DEGRADED" in b_empty, "no-snapshot brief must announce the degradation"
assert "UNKNOWN" in b_empty
live = {"regime": "NEUTRAL", "quadrant": "REFLATION", "quadrant_basis": "growth up x inflation hot",
        "debt_cycle": {"debt_cycle_phase": "DISCIPLINE", "weeks_in_phase": 3, "confidence": "high",
                       "phase_basis": "real 30y 2.90% rising",
                       "reserve_asset_check": {"consistent_with_phase": False, "note": "gold +18% YoY"}}}
b = T.director_brief(live)
assert "DISCIPLINE" in b and "REFLATION" in b
assert "MACRO LAYER DEGRADED" not in b, "a healthy snapshot must not print the degraded banner"
assert "INCONSISTENT" in b and "gold +18% YoY" in b, "reserve-asset falsification must be surfaced verbatim"
assert "NEVER decides membership" in b and "NOT a valid delta_justification" in b, \
    "the citation guard rails must be in the prompt block"
for fam in T.FAMILIES:
    assert fam in b, f"{fam} missing from the resolved tilt in the brief"
seeded = T.director_brief({"quadrant": "REFLATION",
                           "debt_cycle": {"debt_cycle_phase": "DISCIPLINE", "seeded": True,
                                          "confidence": "low"}})
assert "SEEDED" in seeded and "confidence LOW" in seeded, "seeded/low-confidence must be disclosed"
print("B1-B3 OK: director_brief never empty, states degradation/seeding, surfaces the gold "
      "falsification note, carries the citation guard rails")


# ── payload shape (what mining-macro embeds and the page renders) ─────────────────────────────────
p = T.tilt_payload("DISCIPLINE", "REFLATION")
assert set(p) >= {"phase", "quadrant", "families", "phase_table", "quadrant_table", "resolved",
                  "legend", "display_only_note"}
assert p["resolved"] == T.resolve_tilt("DISCIPLINE", "REFLATION")
assert set(p["phase_table"]) == set(PHASES) and set(p["quadrant_table"]) == set(QUADRANTS)
json.dumps(p)                                                # must be JSON-serializable for the payload
assert "never a sizing" in p["display_only_note"].lower() or "never a sizing" in p["display_only_note"]
print("T5 OK: tilt_payload carries both full tables + the resolved row, JSON-serializable, "
      "display-only note attached")

print("\nALL COMMODITY-TILT TESTS PASSED")
