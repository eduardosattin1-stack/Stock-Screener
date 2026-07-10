#!/usr/bin/env python3
"""_numeric_gate.py — deterministic numeric-integrity gate for the weekly Speculair debate records.

Kills the pattern found in the 2026-07 forensics: HNR1.DE's CRO synthesis asserted "roughly 2:1
reward-to-risk" in prose while its own sop_bear text put the adverse case at "about the current
price" (a ~6% floor) — nothing recomputed the ratio or checked the floor was real; the name got
seated. KBR's record had live_price:null while its bear_thesis asserted a specific downside percent
off a price nobody had verified. AAUC's record had price_currency:null on a name that also trades in
CAD, and a hallucinated price inverted a valid arb.

DESIGN: agents write LEVELS (a live price, a bear/base/bull per-share estimate) and narratives; this
module computes every RATIO. No prose-asserted "N:1" or "X% upside vs Y% downside" is trusted.

TWO OPERATING MODES:
  --legacy   Today's results_regime/<SYM>.json records predate the typed `valuation` block this gate
             is designed to check (that block ships when the debate schema changes, Week 2 of the
             pipeline-v3 plan). --legacy synthesizes a best-effort valuation dict from the EXISTING
             prose fields (sop_fair_value/sop_bear/sop_bull) via _numeric_core.parse_money_prose, so
             today's real records can be scored NOW, for calibration — clearly marked low-confidence
             wherever the prose-parse produces an insane bracket (bear/bull inverted, way off base).
  --dry-run  Print a _post_board.py-style report table; write NOTHING (no numeric_gate field is
             stamped on any record, no REJECT/EXCLUDE takes effect). This is the ONLY mode wired into
             the dispatcher today — enforcement (writing numeric_gate: REJECT/EXCLUDE_ELIGIBILITY
             into records, gating the Director's eligibility) is a Week 2 activity per the plan, after
             this dry-run has calibrated the thresholds below against real data.

Usage: python backend/_opus_debate/_numeric_gate.py --legacy --dry-run
       python backend/_opus_debate/_numeric_gate.py --legacy --dry-run --symbol HNR1.DE   (one name)
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # .../backend/_opus_debate
BK = _HERE.parent                                # .../backend
ROOT = _HERE
sys.path.insert(0, str(BK))                      # backend on path for _numeric_core
sys.path.insert(0, str(_HERE))
import _numeric_core as _nc  # noqa: E402

RES_DIR = ROOT / "results_regime"

# ── Calibratable thresholds (tune against --legacy --dry-run output over real records before any
# enforcement ships) ──────────────────────────────────────────────────────────────────────────────
PRICE_WARN_PCT = 0.03      # live_price vs an independent FMP quote: within this -> pass silently
PRICE_REJECT_PCT = 0.08    # beyond this -> REJECT (the AAUC-class fabricated-price inversion)
FV_HARD_LOW, FV_HARD_HIGH = 0.25, 4.0     # base_fv_px outside [0.25x, 4x] live -> REJECT (units/currency chaos)
FV_SOFT_LOW, FV_SOFT_HIGH = 0.4, 3.0      # outside [0.4x, 3x] live -> WARN (VALUATION_OUTLIER)
RR_DIVERGE_PCT = 0.25      # asserted prose ratio vs computed ratio diverging beyond this -> kill the prose
ER_TOL_PTS = 5.0           # Director expected_return_pct vs recomputed -- beyond this -> overwrite + WARN


def check_record(rec, live_quotes=None):
    """Run G0-G8 against one results_regime-style record (with a `valuation` block, real or
    --legacy-synthesized). Returns {gate, reasons[], computed{}}. Never raises; a computation it
    cannot perform is a WARN with a stated reason, not a crash."""
    live_quotes = live_quotes or {}
    reasons = []
    val = rec.get("valuation") or {}
    sym = rec.get("symbol") or "?"

    # G0 — schema presence
    live = val.get("live_price")
    ccy = val.get("price_currency")
    base_fv = val.get("base_fv_px")
    bear = val.get("bear_px")
    bull = val.get("bull_px")
    if not isinstance(live, (int, float)):
        return {"gate": "REJECT", "reasons": ["G0_NO_LIVE_PRICE"], "computed": {}}
    if not ccy:
        reasons.append("G0_NO_CURRENCY")

    computed = {}

    # G1a — price reconcile vs an independent quote (when supplied)
    fmp_px = live_quotes.get(str(sym).upper())
    if isinstance(fmp_px, (int, float)) and fmp_px > 0:
        drift = abs(live / fmp_px - 1)
        computed["price_drift_pct"] = round(drift * 100, 2)
        if drift > PRICE_REJECT_PCT:
            return {"gate": "REJECT", "reasons": reasons + [f"G1A_PRICE_MISMATCH({drift*100:.0f}%)"],
                    "computed": computed}
        if drift > PRICE_WARN_PCT:
            reasons.append(f"G1A_PRICE_DRIFT({drift*100:.0f}%)")

    # G1b — currency implied by the exchange suffix vs what the record states
    implied = _nc.implied_currency(sym)
    if ccy and ccy != implied:
        return {"gate": "REJECT", "reasons": reasons + [f"G1B_CURRENCY_MISMATCH(stated={ccy},implied={implied})"],
                "computed": computed}
    if not ccy and implied != "USD":
        reasons.append(f"G1B_CURRENCY_UNSTATED(implied={implied})")

    # From here on we need a base_fv_px to do anything else
    if not isinstance(base_fv, (int, float)):
        reasons.append("NO_BASE_FV — cannot run G2-G8")
        return {"gate": "WARN" if not any("REJECT" in r for r in reasons) else "REJECT",
                "reasons": reasons, "computed": computed}

    # G3 — base-FV plausibility band vs live price
    ratio_to_live = base_fv / live if live else None
    if ratio_to_live is not None:
        computed["base_fv_to_live"] = round(ratio_to_live, 3)
        if not (FV_HARD_LOW <= ratio_to_live <= FV_HARD_HIGH):
            return {"gate": "REJECT", "reasons": reasons + [f"G3_FV_IMPLAUSIBLE({ratio_to_live:.2f}x live)"],
                    "computed": computed}
        if not (FV_SOFT_LOW <= ratio_to_live <= FV_SOFT_HIGH):
            reasons.append(f"G3_VALUATION_OUTLIER({ratio_to_live:.2f}x live)")

    have_bear = isinstance(bear, (int, float))
    have_bull = isinstance(bull, (int, float))

    # G2 — ordering (only checkable when we have the legs)
    if have_bear and have_bull:
        if not (bear <= base_fv <= bull):
            return {"gate": "REJECT", "reasons": reasons + ["G2_ORDERING_VIOLATION(bear<=base<=bull fails)"],
                    "computed": computed}
    elif have_bear and bear > base_fv:
        return {"gate": "REJECT", "reasons": reasons + ["G2_ORDERING_VIOLATION(bear>base)"], "computed": computed}

    # G4 — bear-above-spot (a "bear case" that isn't actually below today's price is not a floor)
    if have_bear:
        computed["bear_return_pct"] = round((bear / live - 1) * 100, 2)
        computed["floor_distance_pct"] = round((live - bear) / live * 100, 2) if live else None
        if bear >= live:
            reasons.append("G4_BEAR_ABOVE_SPOT")

    # G5 — R:R recompute + prose-ratio kill; G6 — expected-return arithmetic
    rr_flags = []
    er_pct = None
    if have_bear and live > bear:
        up = base_fv - live
        dn = live - bear
        if up > 0 and dn > 0:
            computed["rr_ratio"] = round(up / dn, 2)
            er_pct = round(up / live * 100, 2)
            computed["expected_return_pct"] = er_pct
            floor_pct = dn / live
            if floor_pct < _nc.TINY_FLOOR_PCT:
                rr_flags.append("TINY_FLOOR")
            elif floor_pct < _nc.THIN_FLOOR_PCT:
                rr_flags.append("THIN_FLOOR")
        elif up <= 0:
            rr_flags.append("NO_UPSIDE")
    elif base_fv is not None and live:
        er_pct = round((base_fv / live - 1) * 100, 2)
        computed["expected_return_pct"] = er_pct

    prose_rr = str(rec.get("risk_reward") or "")
    asserted = _parse_asserted_ratio(prose_rr)
    if asserted is not None and computed.get("rr_ratio") is not None:
        computed["asserted_rr"] = asserted
        if computed["rr_ratio"] > 0 and abs(asserted - computed["rr_ratio"]) / computed["rr_ratio"] > RR_DIVERGE_PCT:
            rr_flags.append(f"PROSE_RR_KILLED(asserted={asserted}, computed={computed['rr_ratio']})")
    reasons.extend(rr_flags)

    dir_er = rec.get("director_expected_return_pct") if isinstance(rec.get("director_expected_return_pct"), (int, float)) else None
    if dir_er is not None and er_pct is not None and abs(dir_er - er_pct) > ER_TOL_PTS:
        reasons.append(f"G6_ER_MISMATCH(director={dir_er}, computed={er_pct})")

    # G8 — eligibility teeth
    catalyst = str(rec.get("catalyst_status") or "").upper()
    tiny = any("TINY_FLOOR" in f for f in rr_flags)
    thin_soft = any("THIN_FLOOR" in f for f in rr_flags) and catalyst.startswith(("SOFT_EXTENDED", "FIRED", "UNVERIFIABLE"))
    if tiny or thin_soft:
        return {"gate": "EXCLUDE_ELIGIBILITY", "reasons": reasons, "computed": computed}

    if any(r.startswith("REJECT") or "MISMATCH" in r for r in reasons if r.startswith("G")):
        pass  # already returned above for true REJECT paths; anything left here is a WARN-level flag
    gate = "WARN" if reasons else "PASS"
    return {"gate": gate, "reasons": reasons, "computed": computed}


def _parse_asserted_ratio(prose):
    """Pull a 'N:1' / 'N to 1' / 'N-1' ratio the CRO prose asserts, e.g. 'roughly 2:1 reward-to-risk'.
    None if no such pattern is present (most records just narrate, without a clean N:1 token)."""
    import re
    m = re.search(r'\b([0-9]+(?:\.[0-9]+)?)\s*(?:[:x-]|to)\s*1\b', prose, re.I)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    return None


def synthesize_legacy_valuation(rec):
    """--legacy: best-effort `valuation` block from today's PROSE fields, for records that predate
    the typed schema. base_fv_px (from sop_fair_value) is fairly reliable — the same pattern already
    proven at weekly_opus_refresh._val_money / publish_to_frontend.target_px. bear_px/bull_px (from
    sop_bear/sop_bull, full paragraphs mixing many unrelated dollar figures — revenue, share counts,
    multiples) are LOW CONFIDENCE by construction; `legacy_confidence` records which legs parsed vs
    which are a guess, so the dry-run report can show the calibration gap honestly instead of hiding
    it. Never invents a currency: falls back to the exchange-implied one only when the record has
    none at all (rec.get("price_currency") wins if present)."""
    sym = rec.get("symbol") or ""
    live = rec.get("live_price")
    base_fv = _nc.parse_money_prose(rec.get("sop_fair_value"))
    bear = _nc.parse_money_prose(rec.get("sop_bear")) if rec.get("sop_bear") else None
    bull = _nc.parse_money_prose(rec.get("sop_bull")) if rec.get("sop_bull") else None
    confidence = {"base_fv_px": "prose_parsed" if base_fv is not None else "missing",
                  "bear_px": "prose_parsed_low_confidence" if bear is not None else "missing",
                  "bull_px": "prose_parsed_low_confidence" if bull is not None else "missing"}
    # sop_bear/sop_bull prose routinely yields a value ABOVE base_fv (it's grabbing the first dollar
    # figure in the paragraph, not necessarily the per-share adverse/favorable case) — when the
    # legacy-parsed bear/bull don't bracket base_fv sanely, drop them rather than feed a known-wrong
    # number into G2-G8 (a missing leg produces an honest WARN; a wrong leg produces a false REJECT).
    if base_fv is not None:
        if bear is not None and not (bear < base_fv):
            bear = None
            confidence["bear_px"] = "prose_parse_discarded_insane_bracket"
        if bull is not None and not (bull > base_fv):
            bull = None
            confidence["bull_px"] = "prose_parse_discarded_insane_bracket"
    val = {
        "live_price": live,
        "price_currency": rec.get("price_currency") or None,
        "base_fv_px": base_fv, "bear_px": bear, "bull_px": bull,
        "downside_floor_px": None, "valuation_method": "sop",
        "legacy_synthesized": True, "legacy_confidence": confidence,
    }
    return val


def run(dry_run=True, legacy=True, only_symbol=None, use_live_quotes=False):
    if not RES_DIR.exists():
        print("numeric-gate: no results_regime/ — nothing to check.")
        return
    files = sorted(RES_DIR.glob(f"{only_symbol}.json" if only_symbol else "*.json"))
    live_quotes = {}
    if use_live_quotes:
        import live_debate_engine as E  # noqa
        key = E.get_key("FMP_API_KEY")
        syms = []
        for f in files:
            try:
                syms.append(json.load(open(f, encoding="utf-8")).get("symbol") or f.stem)
            except Exception:
                continue
        live_quotes = _nc.fetch_live_quotes(syms, fmp_key=key)

    counts = {"PASS": 0, "WARN": 0, "REJECT": 0, "EXCLUDE_ELIGIBILITY": 0}
    reason_counts = {}
    rows = []
    for f in files:
        try:
            rec = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if legacy and "valuation" not in rec:
            rec = dict(rec)
            rec["valuation"] = synthesize_legacy_valuation(rec)
        result = check_record(rec, live_quotes)
        counts[result["gate"]] = counts.get(result["gate"], 0) + 1
        for r in result["reasons"]:
            key_r = r.split("(")[0]
            reason_counts[key_r] = reason_counts.get(key_r, 0) + 1
        rows.append((rec.get("symbol") or f.stem, result))

    print(f"{'='*72}\nNUMERIC GATE — {'--legacy --dry-run' if legacy and dry_run else ('--legacy' if legacy else '')}"
          f"{' --dry-run' if dry_run and not legacy else ''} | {len(rows)} records checked\n{'='*72}")
    print(f"gate outcomes: {counts}")
    print(f"reason frequency: {dict(sorted(reason_counts.items(), key=lambda kv: -kv[1]))}")
    print("\n--- REJECT / EXCLUDE_ELIGIBILITY (would-be seat-blocking) ---")
    blocked = [r for r in rows if r[1]["gate"] in ("REJECT", "EXCLUDE_ELIGIBILITY")]
    for sym, res in blocked[:40]:
        print(f"  {sym:10} {res['gate']:20} {res['reasons']}")
    if len(blocked) > 40:
        print(f"  ... and {len(blocked) - 40} more")
    print("\n--- legacy parse coverage (how many records can even be checked with today's prose) ---")
    if legacy:
        have_base = sum(1 for _, res in rows if res["computed"].get("base_fv_to_live") is not None
                         or "base_fv" in str(res.get("reasons")))
        have_rr = sum(1 for _, res in rows if "rr_ratio" in res["computed"])
        print(f"  base_fv parsed: {sum(1 for f in files if True)} attempted, {have_rr} got a full R:R "
              f"(bear leg parsed AND sane vs base_fv) — this gap is exactly why Week 2's typed "
              f"valuation block replaces prose-mining")
    if dry_run:
        print("\nDRY-RUN: nothing written. No record was stamped, no seat eligibility changed.")
    else:
        print("\nWARNING: --dry-run not set but enforcement write-back is NOT YET IMPLEMENTED "
              "(Week 2 activity) — this run was read-only regardless.")
    return rows


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--legacy", action="store_true", help="synthesize valuation from today's prose fields")
    p.add_argument("--dry-run", action="store_true", help="print only; write nothing (REQUIRED — enforcement isn't built yet)")
    p.add_argument("--symbol", default=None, help="check a single symbol")
    p.add_argument("--live-quotes", action="store_true", help="fetch independent FMP quotes for G1a (network)")
    args = p.parse_args()
    if not args.dry_run:
        print("numeric-gate: enforcement (writing numeric_gate onto records, REJECT/EXCLUDE eligibility) "
              "is a Week 2 activity and is NOT implemented — pass --dry-run to run the calibration check.")
        sys.exit(1)
    run(dry_run=True, legacy=args.legacy, only_symbol=args.symbol, use_live_quotes=args.live_quotes)
