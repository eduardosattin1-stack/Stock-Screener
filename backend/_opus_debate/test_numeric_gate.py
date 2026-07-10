#!/usr/bin/env python3
"""Golden tests for _numeric_gate against FROZEN fixtures reproducing the 2026-07 forensics'
documented defects (HNR1.DE thin-floor-masquerading-as-2:1, KBR live_price:null, AAUC fabricated
price on a dual-listed name). Plain asserts, no pytest dependency (matches test_regime_post.py's
convention). Non-mutating: reads _numeric_gate_fixtures/*.json, never touches results_regime/.

Usage: python backend/_opus_debate/test_numeric_gate.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BK = HERE.parent
FIXTURES = HERE / "_numeric_gate_fixtures"
sys.path.insert(0, str(BK))
sys.path.insert(0, str(HERE))

import _numeric_gate as G  # noqa: E402
import _numeric_core as _nc  # noqa: E402


def _load_fixture(name):
    return json.load(open(FIXTURES / name, encoding="utf-8"))


def test_hnr1_de_thin_floor_excludes():
    """The user's specimen: a technically-correct '2:1 reward-to-risk' resting on a ~6.4% floor with
    no hard catalyst must EXCLUDE the name from eligibility -- not because the arithmetic is wrong
    (it isn't: (265-235)/(235-220) = 2.0, matching the asserted ratio exactly), but because a floor
    that thin under a SOFT_EXTENDED catalyst cannot support the confidence a clean '2:1' implies."""
    rec = _load_fixture("hnr1_de.json")
    rec["valuation"] = {"live_price": rec["live_price"], "price_currency": rec["price_currency"],
                         "base_fv_px": 265.0, "bear_px": 220.0, "bull_px": 300.0,
                         "valuation_method": "sop"}
    res = G.check_record(rec)
    assert res["gate"] == "EXCLUDE_ELIGIBILITY", f"expected EXCLUDE_ELIGIBILITY, got {res}"
    assert any("THIN_FLOOR" in r for r in res["reasons"]), res["reasons"]
    computed_rr = res["computed"].get("rr_ratio")
    assert computed_rr is not None and abs(computed_rr - 2.0) < 0.01, \
        f"the computed ratio should match the asserted 2.0 exactly (this fixture tests the THIN-FLOOR " \
        f"gate, not a bad-arithmetic gate) -- got {computed_rr}"
    floor_pct = res["computed"].get("floor_distance_pct")
    assert floor_pct is not None and 5.0 < floor_pct < 15.0, \
        f"floor_distance_pct should land in the THIN band (5-15%), got {floor_pct}"
    print(f"PASS hnr1_de: {res['gate']} | rr_ratio={computed_rr} (asserted 2.0, matches) | "
          f"floor_distance={floor_pct}% (THIN band) | reasons={res['reasons']}")


def test_hnr1_de_legacy_synthesis_recovers_base_fv():
    """Sanity: even without a typed valuation block, --legacy parsing recovers the base_fv_px (265)
    from sop_fair_value cleanly (a single number, the easy case) -- the hard part (documented
    separately) is the bear/bull legs, which live in multi-figure prose paragraphs."""
    rec = _load_fixture("hnr1_de.json")
    val = G.synthesize_legacy_valuation(rec)
    assert val["base_fv_px"] == 265.0, val
    assert val["live_price"] == 235.0, val
    print(f"PASS hnr1_de legacy synthesis: base_fv_px={val['base_fv_px']} | confidence={val['legacy_confidence']}")


def test_kbr_missing_price_rejects_at_g0():
    """KBR's REAL 2026-07-10 record has live_price:None -- G0 must REJECT before ANY downstream
    check (segment split, net debt, R:R) gets a chance to run on unverified numbers."""
    rec = _load_fixture("kbr.json")
    assert rec["live_price"] is None, "fixture must reproduce the real null-price incident"
    rec["valuation"] = G.synthesize_legacy_valuation(rec)
    res = G.check_record(rec)
    assert res["gate"] == "REJECT", f"expected REJECT, got {res}"
    assert res["reasons"] == ["G0_NO_LIVE_PRICE"], res["reasons"]
    print(f"PASS kbr: {res['gate']} | reasons={res['reasons']} (correctly blocks BEFORE any "
          f"segment/net-debt analysis runs on unverified data)")


def test_aauc_fabricated_price_rejects_on_reconcile():
    """The AAUC incident: an assumed price ('near C$44', ~42.5) vs the REAL FMP quote that day
    (US$23.68) diverges ~80% -- G1a must REJECT even though price_currency is unstated (the defect
    here is a wrong PRICE, not a wrong currency mapping -- bare 'AAUC' correctly implies USD)."""
    rec = _load_fixture("aauc.json")
    rec["valuation"] = G.synthesize_legacy_valuation(rec)
    assert rec["valuation"]["price_currency"] is None
    live_quotes = {"AAUC": 23.68}   # the REAL quote that day, per the forensic workflow's FMP call
    res = G.check_record(rec, live_quotes)
    assert res["gate"] == "REJECT", f"expected REJECT, got {res}"
    assert any("G1A_PRICE_MISMATCH" in r for r in res["reasons"]), res["reasons"]
    drift = res["computed"].get("price_drift_pct")
    assert drift is not None and drift > 50, f"expected a large drift (~80%), got {drift}"
    print(f"PASS aauc: {res['gate']} | drift={drift}% vs real quote 23.68 | reasons={res['reasons']}")


def test_implied_currency_dual_listing_mismatch():
    """G1b: a .TO-suffixed symbol (implies CAD) whose record wrongly states USD must REJECT --
    this is the currency-mismatch mechanism the AAUC fixture doesn't exercise (that one has no
    exchange suffix at all; this constructs the direct dual-listing case)."""
    rec = {"symbol": "AAUC.TO", "valuation": {"live_price": 33.59, "price_currency": "USD",
                                               "base_fv_px": 40.0}}
    res = G.check_record(rec)
    assert res["gate"] == "REJECT", f"expected REJECT, got {res}"
    assert any("G1B_CURRENCY_MISMATCH" in r for r in res["reasons"]), res["reasons"]
    print(f"PASS AAUC.TO currency mismatch: {res['gate']} | {res['reasons']}")

    # the correctly-stated version must pass this check cleanly
    rec_ok = {"symbol": "AAUC.TO", "valuation": {"live_price": 33.59, "price_currency": "CAD",
                                                  "base_fv_px": 40.0}}
    res_ok = G.check_record(rec_ok)
    assert not any("G1B" in r for r in res_ok["reasons"]), res_ok["reasons"]
    print(f"PASS AAUC.TO correct currency: {res_ok['gate']} | no G1B flags")


def test_ordering_and_plausibility_bands():
    """G2 (bear<=base<=bull) and G3 (base_fv within a sane multiple of live) on synthetic records --
    these are the pure-arithmetic checks that don't depend on any prose parsing."""
    # inverted ordering (bear above base) -> REJECT
    bad_order = {"symbol": "X", "valuation": {"live_price": 100.0, "price_currency": "USD",
                                               "base_fv_px": 110.0, "bear_px": 120.0, "bull_px": 150.0}}
    res = G.check_record(bad_order)
    assert res["gate"] == "REJECT" and any("G2_ORDERING" in r for r in res["reasons"]), res

    # absurd fair value (50x live) -> REJECT (the units/currency-chaos signature)
    absurd = {"symbol": "Y", "valuation": {"live_price": 10.0, "price_currency": "USD",
                                            "base_fv_px": 600.0}}
    res = G.check_record(absurd)
    assert res["gate"] == "REJECT" and any("G3_FV_IMPLAUSIBLE" in r for r in res["reasons"]), res

    # a mild outlier (3.5x live: inside the hard band [0.25x,4x], outside the soft band [0.4x,3x]) -> WARN only
    outlier = {"symbol": "Z", "valuation": {"live_price": 10.0, "price_currency": "USD",
                                             "base_fv_px": 35.0}}
    res = G.check_record(outlier)
    assert res["gate"] == "WARN" and any("G3_VALUATION_OUTLIER" in r for r in res["reasons"]), res
    print("PASS ordering/plausibility bands: inverted->REJECT, 60x->REJECT, 3.5x->WARN-only")


def test_clean_record_passes():
    """A well-formed record with a sane, non-thin R:R and no red flags must PASS cleanly (the gate
    should not cry wolf on healthy data)."""
    rec = {"symbol": "CLEAN", "valuation": {"live_price": 100.0, "price_currency": "USD",
                                             "base_fv_px": 140.0, "bear_px": 80.0, "bull_px": 170.0,
                                             "valuation_method": "sop"},
           "catalyst_status": "PENDING_HARD", "risk_reward": "roughly 2:1"}
    res = G.check_record(rec)
    assert res["gate"] == "PASS", f"expected PASS, got {res}"
    assert res["computed"]["rr_ratio"] == 2.0, res["computed"]
    print(f"PASS clean record: {res['gate']} | rr_ratio={res['computed']['rr_ratio']} | no flags")


def main():
    tests = [test_hnr1_de_thin_floor_excludes, test_hnr1_de_legacy_synthesis_recovers_base_fv,
             test_kbr_missing_price_rejects_at_g0, test_aauc_fabricated_price_rejects_on_reconcile,
             test_implied_currency_dual_listing_mismatch, test_ordering_and_plausibility_bands,
             test_clean_record_passes]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed" + (f" -- {failed} FAILED" if failed else " -- OK"))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
