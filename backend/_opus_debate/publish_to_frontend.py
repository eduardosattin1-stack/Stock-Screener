#!/usr/bin/env python3
"""publish_to_frontend.py — write the Opus regime-aware apex basket into speculair_baskets.json.

Merges the Opus Director basket (apex_basket_opus_regime.json) + per-name regime-aware
debate records (results_regime/) + cached dossiers + scan financials into the EXACT
speculair_baskets.json schema the frontend renders. The merge BASE is the authoritative
GCS copy (preserving held-name entry data and every other section), and the apex track
record is updated via the engine's own _update_apex_tracking (logs realized exits for
rotated-out names, opens the new names, chains NAV from inception).

Writes LOCAL files only (frontend/public/speculair_baskets.json + speculair_apex_tracking.json).
Push to GCS is a separate explicit step (gcloud storage cp).
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BK = Path(__file__).resolve().parent
BACKEND = BK.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "alpha_compounder"))

import gcs_io  # noqa: E402
import live_debate_engine as E  # noqa: E402
from _ledger import append_decision_history  # noqa: E402  shared with weekly_opus_refresh.py (2026-07-10)
sys.path.insert(0, str(BK))  # so the sibling _wheel module resolves
from _wheel import stamp_wheel  # noqa: E402  CSP->CC wheel suggestion

RES = BK / "results_regime"
PUB = ROOT / "frontend" / "public"
BASKETS_LOCAL = PUB / "speculair_baskets.json"
TRACK_LOCAL = PUB / "speculair_apex_tracking.json"
LG = PUB / "latest_global.json"

ap = argparse.ArgumentParser()
ap.add_argument("--date", default=None)
ap.add_argument("--gcs", action="store_true", help="push speculair_baskets.json + tracking to production GCS via gcloud")
ap.add_argument("--force", action="store_true", help="override the un-post-processed publish gate (prints what was skipped)")
args = ap.parse_args()
TODAY = args.date or datetime.now(timezone.utc).date().isoformat()
E.load_api_keys()


def load(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


# ── Authoritative bases from GCS (fall back to local) ────────────────────
baskets = gcs_io.gcs_read_json_fresh("scans/speculair_baskets.json") or load(BASKETS_LOCAL, {}) or {}  # RMW base — generation-pinned
print(f"merge base: speculair_baskets.json generated_at={baskets.get('generated_at')} "
      f"apex={[p.get('symbol') for p in baskets.get('apex_basket', [])]}")

# ── Rebuild per_methodology_baskets from the raw 11-methodology screen, FILTERED to names
#    DEBATED this run (have a results_regime/<sym>.json), so every Speculair per-method pick
#    carries a fresh Opus overlay (no empty debate panels on stock pages) and the view reflects
#    the current opportunity set — not last week's curated survivors. Sourcing the weekly debate
#    from the curated baskets created a SHRINK LOOP that degraded this file (observed 2026-06-06:
#    8 methodologies / 15 names / apex=1). The raw screener's own view (methodology_picks.json) is
#    untouched; this only rebuilds the Speculair OVERLAY layer. Defensive: any failure keeps the
#    existing baskets so a transient screen problem can't blank the frontend.
try:
    _debated = {f.stem.upper() for f in RES.glob("*.json")}
    _mp = gcs_io.gcs_read_json("scans/methodology_picks.json") or {}
    _meth_src = _mp.get("methodologies", {})
    if _meth_src and _debated:
        _rebuilt = {}
        # RETIRED SCREENS (2026-07-21 apex-reassessment, Bruno's decision): fundamental_momentum
        # (-14.1% YTD vs +10-17% for the cash-earnings families) no longer refreshes — the basket
        # FREEZES at its last published state (terminal membership + banked ytd_return/exits) with
        # a retired stamp, so the track record stays honest and visible but nothing more accrues.
        # The production scan's own methodology_picks.json is untouched.
        _RETIRED_METHS = {"fundamental_momentum"}
        for _meth, _b in _meth_src.items():
            if _meth in _RETIRED_METHS:
                _old = (baskets.get("per_methodology_baskets") or {}).get(_meth)
                if isinstance(_old, dict):
                    _frozen = dict(_old)
                    _frozen["retired"] = True
                    _frozen.setdefault("retired_date", TODAY)
                    _rebuilt[_meth] = _frozen
                    print(f"  retired screen kept frozen: {_meth} (retired_date={_frozen['retired_date']}, "
                          f"final ytd={_frozen.get('ytd_return')})")
                continue
            _bd = _b if isinstance(_b, dict) else {"picks": _b}
            _picks = [p for p in (_bd.get("picks") or [])
                      if isinstance(p, dict) and p.get("symbol") and p["symbol"].upper() in _debated]
            if _picks:
                _nb = dict(_bd)        # preserve per-methodology tracking metadata (ytd_return, exits, ...)
                _nb["picks"] = _picks
                _rebuilt[_meth] = _nb
        if _rebuilt:
            baskets["per_methodology_baskets"] = _rebuilt
            print(f"rebuilt per_methodology_baskets from raw screen: {len(_rebuilt)} methodologies, "
                  f"{sum(len(v['picks']) for v in _rebuilt.values())} debated picks "
                  f"(of {len(_debated)} debated names)")
        else:
            print("WARN: raw-screen rebuild produced 0 picks — keeping existing per_methodology_baskets")
    else:
        print(f"per_methodology rebuild skipped (meth_src={len(_meth_src)} debated={len(_debated)}) — keeping existing")
except Exception as _e:
    print(f"WARN: per_methodology rebuild failed ({_e}) — keeping existing per_methodology_baskets")
# Refresh local tracking state from GCS so _update_apex_tracking chains from the authoritative NAV.
gcs_track = gcs_io.gcs_read_json_fresh("scans/speculair_apex_tracking.json")  # two-writer RMW — generation-pinned
if gcs_track:
    TRACK_LOCAL.write_text(json.dumps(gcs_track, indent=2), encoding="utf-8")
    print(f"refreshed local tracking from GCS: nav={gcs_track.get('nav')} positions={len(gcs_track.get('positions', {}))}")

director = load(BK / "apex_basket_opus_regime.json") or {}
picks = director.get("apex_basket", [])
if not picks:
    print("ERROR: apex_basket_opus_regime.json has no picks — aborting.")
    sys.exit(1)

# ── PUBLISH GATE (the 06-30 basket shipped live with NO skeptic pass and NO post-processor) ──
# HARD on the post stamp: _regime_post.py stamps moat_post_applied=True after consuming the skeptic,
# applying the moat/theme caps and building weights — publishing without it means raw, un-capped,
# un-vetted Director output reaches production. SOFT on skeptic coverage (partial runs are the ops
# norm; consume_skeptic already stamps MISSING + half-sizes). --force overrides, printing the skip.
if not director.get("moat_post_applied"):
    msg = ("GUARD publish gate: apex_basket_opus_regime.json has NO moat_post_applied stamp — run "
           "`python backend/weekly_opus_refresh.py regime-skeptic` (Workflow) then `regime-post` "
           "before publishing.")
    if args.force:
        print(f"WARN --force: {msg} — PUBLISHING ANYWAY (un-post-processed, un-capped weights).")
    else:
        print(f"{msg} Aborting (override with --force).")
        sys.exit(1)
# 2026-07-11 (Weeks 3-4): _regime_post now also runs the numeric layer (stress/correlation/exits
# parity + the conviction clamp + banded sizing) and stamps numeric_post_applied. Same hard gate,
# same --force override — publishing without it means unclamped conviction sized the book.
if not director.get("numeric_post_applied"):
    msg = ("GUARD publish gate: apex_basket_opus_regime.json has NO numeric_post_applied stamp — "
           "run `python backend/weekly_opus_refresh.py regime-post` (the Weeks-3/4 numeric layer) "
           "before publishing.")
    if args.force:
        print(f"WARN --force: {msg} — PUBLISHING ANYWAY (unclamped/unstressed weights).")
    else:
        print(f"{msg} Aborting (override with --force).")
        sys.exit(1)
# Coverage from the STAMPED verdicts (consume_skeptic writes them into the picks), NOT shard
# mtimes — regime-post rewrites the apex file after consuming, so every shard then looks older
# than the apex and an mtime check reads 0-coverage on a fully-vetted book (observed 2026-07-02).
_skep_cov = sum(1 for _p in picks if (_p.get("skeptic_verdict") or "") not in ("", "MISSING"))
if picks and _skep_cov / len(picks) < 0.7:
    print(f"WARN skeptic-coverage at publish: only {_skep_cov}/{len(picks)} apex seats carry a "
          f"skeptic verdict (MISSING seats are stamped + half-sized by the post; not blocking).")

scan = load(LG, {}) or {}
scan_by_sym = {s.get("symbol"): s for s in scan.get("stocks", []) if s.get("symbol")}
prior_apex = {p.get("symbol"): p for p in baskets.get("apex_basket", [])}


def dossier_for(sym):
    md = BK / "dossiers" / f"{sym}.md"
    if md.exists():
        return md.read_text(encoding="utf-8")
    return (load(BK / "inputs" / f"{sym}.json", {}) or {}).get("dossier", "")


def mos_fv(sc):
    meths = sc.get("source_methodologies") or []
    key = meths[0] if meths else "opus_regime"
    mos, fv = sc.get("margin_of_safety"), sc.get("buffett_fair_value")
    return ({key: mos} if isinstance(mos, (int, float)) else {},
            {key: fv} if isinstance(fv, (int, float)) else {},
            {key: True}, meths)


def derive_entry_posture(p, rec=None):
    """Deterministic fallback for entry TIMING when the Director didn't tag one (Director always wins).
    enter_now_carry can't be derived (needs the carry signal) -> scale_in (which also means 'enter now')."""
    cat = str((p.get("catalyst_status") or (rec or {}).get("catalyst_status") or "")).upper()
    if cat.startswith("PENDING_HARD") or cat.startswith("ARB"):
        return "on_confirmation"
    blob = (str(p.get("entry_plan") or "") + " "
            + " ".join(str(a) for a in (p.get("exposure_axes") or [])) + " "
            + str(p.get("lane") or "")).lower()
    if any(k in blob for k in ("knife", "demand-cycle", "cyclical", "de-gross", "degross")):
        return "wait_for_weakness"
    return "scale_in"


_SKEPTIC_OK = ("CONFIRMED", "CONFIRMED_WITH_CORRECTIONS")

_SKEP_DIR = BK / "_skeptic_regime"


def skeptic_shard(sym):
    """Skeptic verdict for a symbol from the raw shard, keyed to risk_badge's p-field names.
    Lets the badge fire on debated-but-not-seated names (overlay / history paths) — the full
    sweep found e.g. VNT eligible while off-board. {} when no shard (badge then stays None)."""
    try:
        d = load(_SKEP_DIR / f"{sym}.json", {}) or {}
    except Exception:
        d = {}
    return {"skeptic_verdict": d.get("verdict"),
            "correction_severity": d.get("correction_severity"),
            "skeptic_kill_scope": d.get("kill_scope")}


def risk_badge(rec, p=None):
    """Publish-time 'bounded downside' / 'dated catalyst' badge — computed HERE, once, from the
    numeric gate's machine-checked levels (rec['computed'], stamped by numeric-gate --enforce at an
    FMP-verified live price). Never from prose, never client-side. Returns None whenever the pick
    doesn't qualify OR the gate hasn't stamped computed{} (pre-v3 records, value/disruptor books):
    the badge simply doesn't render — honest default-off.

    PRIMARY (bounded_downside): gate PASS (excludes bear-above-spot/G4, price drift, FV outliers);
    asymmetry real but plausible (2 <= rr <= 5 — an rr>5 on a SOFT_EXTENDED name signals a
    mis-modeled base FV, not a gift); bear floor modest yet not manufactured (5% <= floor <= 20%,
    matching the gate's own TINY/THIN-floor philosophy); skeptic confirmed with NO material
    correction (on the 2026-07 board the one material correction was precisely the bear floor
    being restated); catalyst not already FIRED.

    SECONDARY (dated_catalyst_floor, supersedes — rarer by design, 0/10 on the current all-
    SOFT_EXTENDED board): a dated+binding catalyst (PENDING_HARD exact enum; ARB excluded —
    deal-break downside is bimodal, not bounded) with gate PASS, floor <= 15% and rr >= 1.5,
    unless the skeptic materially challenged the catalyst itself."""
    p = p or {}
    comp = rec.get("computed") or {}
    gate = rec.get("numeric_gate")
    rr, fd = comp.get("rr_ratio"), comp.get("floor_distance_pct")
    if gate != "PASS" or not isinstance(rr, (int, float)) or not isinstance(fd, (int, float)):
        return None
    sk = str(p.get("skeptic_verdict") or rec.get("skeptic_verdict") or "")
    if sk not in _SKEPTIC_OK:
        return None
    sev = str(p.get("correction_severity") or rec.get("correction_severity") or "")
    scope = str(p.get("skeptic_kill_scope") or rec.get("skeptic_kill_scope") or "")
    cat = str(rec.get("catalyst_status") or p.get("catalyst_status") or "").upper()
    base = {
        "downside_pct": comp.get("bear_return_pct"),
        "upside_pct": comp.get("expected_return_pct"),
        "rr_ratio": rr, "floor_distance_pct": fd,
        "numeric_gate": gate, "skeptic_verdict": sk,
    }
    if (cat.startswith("PENDING_HARD") and fd <= 15.0 and rr >= 1.5
            and not (sev == "material" and scope == "catalyst")):
        return {"kind": "dated_catalyst_floor", **base}
    if 2.0 <= rr <= 5.0 and 5.0 <= fd <= 20.0 and sev != "material" and not cat.startswith("FIRED"):
        return {"kind": "bounded_downside", **base}
    return None


def target_px(sop_fv):
    """Parse the CRO/Director fair-value prose ('~$44', '$78-88 (base ~$82)') to ONE number so the
    UI can draw expected-vs-realized per seat (the basket-13 convention). Base-case > range-midpoint."""
    if sop_fv is None:
        return None
    txt = str(sop_fv)
    m = re.search(r'base[^$0-9]{0,14}\$?\s*([0-9]+(?:\.[0-9]+)?)', txt, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:/sh\w*)?\s*\((?:range|vs)', txt, re.I)
    if m:                                          # '~$120 (range $105-135)' -> the leading base, not the range midpoint
        return float(m.group(1))
    vals = [float(x) for x in re.findall(r'([0-9]+(?:\.[0-9]+)?)', txt)]
    if not vals:
        return None
    if len(vals) >= 2 and vals[1] <= vals[0] * 3:
        return round((vals[0] + vals[1]) / 2, 2)
    return vals[0]


# Authoritative entry prices live in the apex tracking file's positions (mirrors value_publish).
# The prior-payload + scan-price fallback both yield 0 for a HELD non-US name absent from the US
# scan (e.g. PLX.PA), and the stale 0 then carries forward forever — so insert tracking as the
# middle fallback, BEFORE the scan price.
apex_pos = {}
try:
    if TRACK_LOCAL.exists():
        apex_pos = (json.load(open(TRACK_LOCAL, encoding="utf-8")) or {}).get("positions", {}) or {}
except Exception:
    apex_pos = {}

entries = []
for p in picks:
    sym = p.get("symbol")
    rec = load(RES / f"{sym}.json", {}) or {}
    sc = scan_by_sym.get(sym, {})
    doss = dossier_for(sym)
    m = re.search(r"CREDIBILITY_SCORE:\s*(\d+)", doss)
    interro = max(1, min(5, int(m.group(1)))) if m else (rec.get("interrogator_score") or 3)
    mt = re.search(r"TRAJECTORY:\s*([A-Z]+)", doss)
    traj = mt.group(1) if mt else rec.get("trajectory", "")
    mos_d, fv_d, meth_app, meths = mos_fv(sc)
    prior = prior_apex.get(sym, {})
    rationale = p.get("thesis", "")
    if p.get("lane"):
        rationale += f"  ·  Lane: {p['lane']}"
    if p.get("regime_fit"):
        rationale += f"  ·  Regime: {p['regime_fit']}"
    if p.get("phase_fit"):
        rationale += f"  ·  Cycle: {p['phase_fit']}"
    entries.append({
        "symbol": sym,
        "conviction": int(p.get("director_conviction", 0)),
        "debate_conviction": int(rec.get("conviction", 0) or 0),
        # catalyst-blind CRO value score (1-5) — the number the VALUE Director ranks on;
        # published so the UI can show it next to the regime-tilted debate conviction
        "value_conviction": rec.get("value_conviction"),
        # NEW names: leave entry_price 0 here so _update_apex_tracking stamps the LIVE quote
        # (it uses the current price when entry_price is falsy). The scan price is stale for
        # EU names (FRVIA/SCR.PA/CTSH all showed a spurious day-1 P&L), so it is NOT a fallback.
        # The backfill after the tracking update reads the live entry back into the displayed book.
        "entry_price": prior.get("entry_price") or apex_pos.get(sym, {}).get("entry_price") or 0,
        "entry_date": prior.get("entry_date") or apex_pos.get(sym, {}).get("entry_date") or TODAY,
        "held_since_prior": sym in prior_apex,
        "source_methodologies": meths,
        "director_rationale": rationale,
        # rotation-discipline (continuity): the Director's per-name call + why, vs the prior-decision ledger
        "decision": p.get("decision"),
        "decision_rationale": p.get("decision_rationale"),
        "whats_changed": p.get("whats_changed"),
        "consensus_delta": rec.get("consensus_delta", ""),
        "forcing_function": rec.get("forcing_function", "") or p.get("forcing_function", ""),
        "valley_of_death": rec.get("valley_of_death", ""),
        "positioning_washout": rec.get("positioning_washout", ""),
        "moderator_conclusion": rec.get("moderator_conclusion", ""),
        "bull_thesis": rec.get("bull_thesis", ""),
        "bear_thesis": rec.get("bear_thesis", ""),
        "interrogator_dossier": doss,
        "interrogator_score": interro,
        "trajectory": traj,
        "sop_fair_value": rec.get("sop_fair_value", "") or p.get("sop_fair_value", ""),
        "target_px": target_px(rec.get("sop_fair_value", "") or p.get("sop_fair_value", "")),
        "forensic_cap": bool(p.get("forensic_cap")),
        "sop_breakdown": rec.get("sop_breakdown", ""),
        "sop_bull": rec.get("sop_bull", ""), "sop_bear": rec.get("sop_bear", ""),
        "risk_reward": rec.get("risk_reward", ""),
        "catalyst_status": rec.get("catalyst_status", "") or p.get("catalyst_status", ""),
        "peer_comps_note": rec.get("peer_comps_note", ""),
        "sector": p.get("sector") or rec.get("sector") or sc.get("sector", ""),
        "mos": mos_d, "fair_value": fv_d,
        "cycle_flag": sc.get("cycle_flag", "NORMAL"),
        "peak_margin_sigma": sc.get("peak_margin_sigma", 0.0),
        "norm_scale": sc.get("norm_scale", 1.0),
        "mos_source": sc.get("mos_source", "opus_regime"),
        "years_history": sc.get("years_history", 99),
        "structural_break": sc.get("structural_break", False),
        "structural_break_reason": sc.get("structural_break_reason", ""),
        "forward_eps_growth": sc.get("forward_eps_growth", 0.0),
        "iv15_nogrowth_agreement": sc.get("iv15_nogrowth_agreement", True),
        "iv15_saturated": sc.get("iv15_saturated", False),
        "sector_class": sc.get("sector_class", "operating"),
        "methodology_applicable": meth_app,
        "lane": p.get("lane", ""), "regime_fit": p.get("regime_fit", ""),
        # Debt-cycle badge fields (FORK 2/B, 2026-07-27): the deterministic payback-speed
        # label + whether the phase duration cap trimmed this seat — a bound cap must be
        # VISIBLE on the pick, not inferred from weights.
        "phase_fit": p.get("phase_fit", ""),
        "duration_bucket": p.get("duration_bucket", ""),
        "duration_bucket_source": p.get("duration_bucket_source", ""),
        "duration_bucket_override_reason": p.get("duration_bucket_override_reason", ""),
        "cycle_capped": bool(p.get("cycle_capped")),
        "cycle_cap_note": p.get("cycle_cap_note", ""),
        "size_units": p.get("size_units"),
        "size_units_effective": p.get("size_units_effective"),
        # equity special-sit lane (catalyst-framed B13 non-binaries): downside floor for risk-to-floor
        # sizing. The typed debate schema nests it as valuation.downside_floor_px (the top-level key
        # was only ever written by the retired B13 catalyst-seed) — fall back to the nested field,
        # which is why this was null on every pick until 2026-07-16.
        "downside_floor": (rec.get("downside_floor") or p.get("downside_floor")
                           or (rec.get("valuation") or {}).get("downside_floor_px")),
        "live_price": rec.get("live_price") or sc.get("price"),
        # gate-checked asymmetry (numeric-gate --enforce stamps computed{} at an FMP-verified price;
        # absent on pre-v3 records → fields null, badge None — honest default-off)
        "downside_pct": (rec.get("computed") or {}).get("bear_return_pct"),
        "upside_pct": (rec.get("computed") or {}).get("expected_return_pct"),
        "rr_ratio": (rec.get("computed") or {}).get("rr_ratio"),
        "numeric_gate": rec.get("numeric_gate"),
        "risk_badge": risk_badge(rec, p),
        # apex skeptic + moat terminal-erosion (stamped by _regime_post) — surfaced per seat for the UI
        "skeptic_verdict": p.get("skeptic_verdict", ""),
        "skeptic_kill_fact": p.get("skeptic_kill_fact", ""),
        # unified skeptic (X1): categorical severity + scope replace the numeric cap (legacy field
        # still passed through for pre-X1 shards; new shards never emit a number)
        "skeptic_correction_severity": p.get("correction_severity", ""),
        "skeptic_kill_scope": p.get("skeptic_kill_scope", ""),
        "value_conviction_cap": p.get("value_conviction_cap"),
        "moat": p.get("moat", ""), "moat_score": p.get("moat_score"),
        "moat_erosion": p.get("moat_erosion", ""), "erosion_severity": p.get("erosion_severity", "none"),
        "secular_theme": p.get("secular_theme", ""),
        "entry_posture": p.get("entry_posture") or derive_entry_posture(p, rec),
        "expected_return_pct": p.get("expected_return_pct"),
        "horizon_months": p.get("horizon_months"),
        "meets_goal": p.get("meets_goal"),
        "goal_note": p.get("goal_note"),
        "wheel": p.get("wheel"),
        "engine": "opus-5-regime",
    })

# ── Wheel suggestions (CSP->CC) on the regime entries — Director-tag fallback + live CSP yield ──
stamp_wheel(entries, "regime", {e["symbol"]: {"price": scan_by_sym.get(e["symbol"], {}).get("price")} for e in entries})

# ── Update the apex track record for the rotation (reuses production logic) ──
try:
    track_summary = E._update_apex_tracking(entries, push_gcs=False)
except Exception as e:
    print(f"WARN: _update_apex_tracking failed ({e}); preserving prior tracking summary.")
    track_summary = baskets.get("apex_tracking", {})

# Backfill the displayed entry_price/date from the tracking the engine just stamped: genuinely-new
# names (entry_price left 0 above) now carry the LIVE quote, and held names keep their preserved
# entry. Without this the book shows the stale scan price / 0 and a fake day-1 P&L. Mirrors
# value_publish; best-effort so it can never break the publish.
try:
    _upos = (json.load(open(TRACK_LOCAL, encoding="utf-8")) or {}).get("positions", {}) or {}
    for e in entries:
        _pp = _upos.get(e["symbol"], {})
        if _pp.get("entry_price"):
            e["entry_price"] = _pp["entry_price"]
            e["entry_date"] = _pp.get("entry_date") or e.get("entry_date")
except Exception as _e:
    print(f"WARN: entry-price backfill from tracking failed ({_e})")

# ── Director-weighted NAV (parallel to equal-weight) ────────────────────────
# The regime Director risk-sizes the book in his memo (defensive anchors larger, cyclical tails
# "held smallest on purpose"). Weight basis = the Director's structured size_units when present,
# else his director_conviction (0-100) — his own per-seat scoring. Card shows this as primary;
# the equal-weight chain stays as the continuity series.
SS_RTF_CAP_PCT = 1.5      # equity special-sit: weight_pct * (live-floor)/live <= 1.5% NAV (mirrors B13)
SS_LANE_CAP = 0.15        # the equity special-sit lane in aggregate <= 15% of the book


from _post_common import banded_units as _banded_units  # noqa: E402  shared with _regime_post (one sizing map)


def _apex_weights(es):
    units = {}
    for e in es:
        eff = e.get("size_units_effective")   # post moat-erosion + secular-theme caps from _regime_post
        su = e.get("size_units")
        if isinstance(eff, (int, float)) and eff > 0:
            units[e["symbol"]] = float(eff)    # prefer the capped effective units when _regime_post ran
        elif isinstance(su, (int, float)) and 0.1 <= su <= 1.5:
            units[e["symbol"]] = float(su)
        else:
            units[e["symbol"]] = _banded_units(e.get("conviction"))
    tot = sum(units.values()) or 1.0
    w = {s: u / tot for s, u in units.items()}

    # FLOOR-SIZING for the equity special-sit lane (catalyst-framed B13 non-binaries): cap each seat
    # at SS_RTF_CAP_PCT risk-to-floor, and the lane in aggregate at SS_LANE_CAP; redistribute the
    # freed weight across the rest of the book proportionally to their units.
    bysym = {e["symbol"]: e for e in es}
    caps = {}
    for s, e in bysym.items():
        if "special_sit" in str(e.get("lane") or "").lower():   # normalized: any special-sit lane variant
            live, floor = e.get("live_price") or 0, e.get("downside_floor") or 0
            if live > 0 and 0 < floor < live:
                caps[s] = min(w.get(s, 0), (SS_RTF_CAP_PCT / 100.0) * live / (live - floor))
            else:                                  # no usable floor -> conservative hard cap
                caps[s] = min(w.get(s, 0), 0.05)
    if caps:
        if sum(caps.values()) > SS_LANE_CAP:       # aggregate lane cap
            sc_ = SS_LANE_CAP / sum(caps.values())
            caps = {s: v * sc_ for s, v in caps.items()}
        capped = sum(caps.values())
        free_u = sum(units[s] for s in w if s not in caps) or 1.0
        for s in list(w):
            w[s] = caps[s] if s in caps else (1 - capped) * units[s] / free_u
    return {s: round(x, 4) for s, x in w.items()}

apex_weights = _apex_weights(entries)
_wbasis = "size_units" if any(isinstance(e.get("size_units"), (int, float)) for e in entries) else "director_conviction"
for e in entries:
    e["weight_pct"] = round(apex_weights.get(e["symbol"], 0) * 100, 2)
try:
    track_summary_w = E._update_apex_tracking(entries, push_gcs=False, weights=apex_weights,
                                              gcs_path="scans/speculair_apex_tracking_weighted.json",
                                              local_name="speculair_apex_tracking_weighted.json")
except Exception as e:
    print(f"WARN: weighted apex tracking failed ({e})")
    track_summary_w = {}

# ── Assemble: swap apex_basket + memo, preserve everything else ──────────
baskets["apex_basket"] = entries

# Capture this run's Director decisions into the year ledger (continuity trail for next week's
# Director + the UI rotation panel). Shared with weekly_opus_refresh.py via _ledger.py (2026-07-10) —
# entries already carry "conviction" normalized from the raw director_conviction field, and
# append_decision_history's fallback chain (director_conviction -> value_score -> conviction) resolves
# to the same value, so this is a behavior-neutral consolidation of the two prior copies.
append_decision_history("regime", {"apex_basket": entries})
baskets["director_memo"] = director.get("director_memo", baskets.get("director_memo", ""))
# Director runner_ups (incl skeptic demotions, verdicts already stamped by consume_skeptic) never
# reached the frontend — the UI "Watch & Wait" list froze at its 2026-06-06 capitulation_watchlist.
# Publish them; the UI prefers runner_ups when present (dated), keeping the legacy list as fallback.
baskets["runner_ups"] = [r for r in (director.get("runner_ups") or []) if isinstance(r, dict)]
baskets["runner_ups_as_of"] = TODAY
baskets["regime_changes"] = director.get("regime_changes", "")
baskets["regime_basis"] = "CATALYST_WATCH_REGIME.md (2026-06-05 baseline)"
baskets["engine"] = "opus-5"  # Fable retired from the Director/Skeptic seats 2026-07-10 (pipeline-v3 Week 1) -- all-Opus again
if track_summary:
    baskets["apex_tracking"] = track_summary
baskets["weights"] = apex_weights
baskets["weights_basis"] = _wbasis
if track_summary_w:
    baskets["apex_tracking_weighted"] = track_summary_w

# ── Return goal + macro risk-stance (Apex book) — Director-authored, deterministic fallback ──
_macro = load(BK / "macro_regime.json", {"regime": "NEUTRAL", "score": 0.5}) or {"regime": "NEUTRAL"}
_goal = {"low_pct": 30, "high_pct": 50, "horizon_months": 12}
_exp_w = _exp_tot = _hor_w = _hor_tot = 0.0
for e in entries:
    px = scan_by_sym.get(e["symbol"], {}).get("price") or e.get("entry_price")
    if e.get("expected_return_pct") is None and isinstance(e.get("target_px"), (int, float)) and isinstance(px, (int, float)) and px > 0:
        e["expected_return_pct"] = round((e["target_px"] / px - 1) * 100, 1)
    w = apex_weights.get(e["symbol"], 0) or 0
    if isinstance(e.get("expected_return_pct"), (int, float)):
        _exp_tot += e["expected_return_pct"] * w; _exp_w += w
    if isinstance(e.get("horizon_months"), (int, float)):
        _hor_tot += e["horizon_months"] * w; _hor_w += w
_stance_map = {"RISK_ON": "aggressive", "NEUTRAL": "balanced", "CAUTIOUS": "balanced", "RISK_OFF": "defensive"}
baskets["return_goal"] = _goal
# Deterministic fallback stance now passes through the debt-cycle phase modifier
# (DISCIPLINE caps balanced / FORCING floors defensive / MONETIZATION unlocks aggressive)
# so a Director that omitted risk_stance still lands on a phase-consistent posture.
_cycle_pub = _macro.get("debt_cycle") or {}
_stance_raw = director.get("risk_stance") or _stance_map.get(_macro.get("regime"), "balanced")
try:
    from debt_cycle import apply_phase_to_stance as _apts
    _stance_eff, _stance_note = _apts(_stance_raw, _cycle_pub.get("debt_cycle_phase", "UNKNOWN"))
except Exception:
    _stance_eff, _stance_note = _stance_raw, ""
baskets["risk_stance"] = _stance_eff
if _stance_note and _stance_eff != _stance_raw:
    baskets["risk_stance_modifier_note"] = f"{_stance_raw} -> {_stance_eff}: {_stance_note}"
    print(f"  phase stance modifier: {baskets['risk_stance_modifier_note']}")
baskets["macro_read"] = director.get("macro_read", "")
baskets["phase_read"] = director.get("phase_read", "")
baskets["expected_horizon_months"] = director.get("expected_horizon_months")
baskets["macro_regime"] = {"regime": _macro.get("regime"), "score": _macro.get("score"),
                           "regime_detail": _macro.get("regime_detail", {}),
                           # growth x inflation 2x2 (2026-07-16) — the briefing's quadrant chip
                           "quadrant": _macro.get("quadrant"), "quadrant_basis": _macro.get("quadrant_basis", "")}
# Dalio debt-cycle block (2026-07-27) — the briefing's cycle chip + falsifier strip
baskets["debt_cycle"] = {k: _cycle_pub.get(k) for k in
                         ("debt_cycle_phase", "prior_phase", "weeks_in_phase", "cycle_score",
                          "confidence", "phase_basis", "phase_detail", "duration_caps",
                          "transition_blocked", "transition_implied", "reserve_asset_check",
                          "expected_horizon_months", "asof")}
baskets["debt_cycle"]["phase_applied_by_director"] = director.get("debt_cycle_phase")
# cap_binding / duration_caps_applied are stamped onto the director doc by _regime_post
baskets["debt_cycle"]["cap_binding"] = director.get("cap_binding") or []
baskets["debt_cycle"]["duration_caps_applied"] = director.get("duration_caps_applied") or {}
# Agent regime read (RegimeRead phase, weekly) — AGREE/CONTRADICT vs the dials + dated
# falsifiers. Published for the UI; the dials stay authoritative.
_rr = load(BK / "regime_read.json", {}) or {}
if _rr.get("agent_view"):
    baskets["regime_read"] = {k: _rr.get(k) for k in
                              ("asof", "quadrant_per_dials", "agent_view", "evidence",
                               "falsifiers", "stance_note", "confidence")}

# ── Regime-call ledger (2026-07-16, JPM-article adoption) — append-only record of every
# published run's macro read, so the regime dial earns a live-forward track record like every
# other paper book (score quarterly: did defensive stances precede drawdowns? did the agent's
# CONTRADICT calls beat the dials? did falsifiers fire?). One row per publish. ──
try:
    _ledger_row = {
        "date": TODAY, "book": "regime",
        "regime": _macro.get("regime"), "score": _macro.get("score"),
        "quadrant": _macro.get("quadrant"), "quadrant_basis": _macro.get("quadrant_basis"),
        "agent_view": _rr.get("agent_view"), "agent_confidence": _rr.get("confidence"),
        "falsifiers": _rr.get("falsifiers"),
        "risk_stance": baskets.get("risk_stance"),
        "regime_quadrant_applied": director.get("regime_quadrant"),
        "macro_read": baskets.get("macro_read"),
        "book_expected_return_pct": baskets.get("book_expected_return_pct"),
    }
    with open(BK / "_regime_ledger.jsonl", "a", encoding="utf-8") as _lf:
        _lf.write(json.dumps(_ledger_row, ensure_ascii=False) + "\n")
    print(f"  regime ledger += {TODAY} {_ledger_row.get('quadrant')} / {_ledger_row.get('risk_stance')}"
          f" / agent {_ledger_row.get('agent_view') or 'n/a'}")
except Exception as _e:
    print(f"WARN: regime ledger append failed ({_e})")

# ── Debt-cycle ledger (2026-07-27) — one row per publish so the phase dial earns a
# live-forward track record like the regime dial. The realized duration mix is the
# field that makes it scoreable: did DISCIPLINE precede story-vs-cash_now
# underperformance? did the cap bind, and did binding help or cost? did the state
# machine block a transition that should have happened (the hysteresis cost)? ──
try:
    _dur_mix = {}
    for _e2 in entries:
        _b = _e2.get("duration_bucket") or "unlabeled"
        _dur_mix[_b] = round(_dur_mix.get(_b, 0.0) + (apex_weights.get(_e2["symbol"], 0) or 0), 4)
    _cyc_row = {
        "date": TODAY, "book": "cycle",
        "debt_cycle_phase": _cycle_pub.get("debt_cycle_phase"),
        "prior_phase": _cycle_pub.get("prior_phase"),
        "weeks_in_phase": _cycle_pub.get("weeks_in_phase"),
        "cycle_score": _cycle_pub.get("cycle_score"),
        "cycle_sub_scores": _cycle_pub.get("cycle_sub_scores"),
        "transition_blocked": _cycle_pub.get("transition_blocked"),
        "transition_implied": _cycle_pub.get("transition_implied"),
        "reserve_asset_consistent": (_cycle_pub.get("reserve_asset_check") or {}).get("consistent_with_phase"),
        "agent_phase_view": _rr.get("phase_view"), "agent_confidence": _rr.get("confidence"),
        "phase_falsifiers": _rr.get("phase_falsifiers"),
        "risk_stance": baskets.get("risk_stance"),
        "risk_stance_modifier": baskets.get("risk_stance_modifier_note", ""),
        "phase_applied_by_director": director.get("debt_cycle_phase"),
        "expected_horizon_months": director.get("expected_horizon_months"),
        "duration_caps": director.get("duration_caps_applied") or {},
        "cap_binding": director.get("cap_binding") or [],
        "duration_mix": _dur_mix,
    }
    with open(BK / "_cycle_ledger.jsonl", "a", encoding="utf-8") as _lf:
        _lf.write(json.dumps(_cyc_row, ensure_ascii=False) + "\n")
    print(f"  cycle ledger += {TODAY} {_cyc_row.get('debt_cycle_phase')} "
          f"({_cyc_row.get('weeks_in_phase')}w) / mix {_dur_mix} / binding {_cyc_row['cap_binding'] or 'none'}")
except Exception as _e:
    print(f"WARN: cycle ledger append failed ({_e})")
baskets["book_expected_return_pct"] = round(_exp_tot / _exp_w, 1) if _exp_w > 0 else None
baskets["book_horizon_months"] = round(_hor_tot / _hor_w, 1) if _hor_w > 0 else None
# GOAL GATE (warn-only, never blocks): the Apex mandate is +30-50%/12mo — an under-goal book still
# publishes, but the Director must own the shortfall explicitly in the memo.
_ber = baskets["book_expected_return_pct"]
if isinstance(_ber, (int, float)) and _ber < _goal["low_pct"]:
    print(f"GOAL GATE WARN: book expected return {_ber:.1f}% < +30% mandate floor — "
          f"Director must own an under-goal book in the memo")
baskets["generated_at"] = datetime.now(timezone.utc).isoformat()
baskets["director_last_run"] = baskets["generated_at"]
baskets["rebalance_date"] = TODAY

# ── Overlay Opus debates onto every per-methodology basket pick (so all stock pages show Opus) ──
def _opus_overlay(sym):
    rec = load(RES / f"{sym}.json")
    # Accept graded-but-narrative-less records too (change-detection CARRY restamps have valid
    # verdict/conviction/value_conviction with an empty bull_thesis) — before 2026-07-17 those
    # 20+ picks published with NO grades at all and the UI rendered a blank "· /5" chip.
    if not rec or not (rec.get("bull_thesis") or rec.get("verdict")):
        return None
    d = dossier_for(sym)
    mm = re.search(r"CREDIBILITY_SCORE:\s*(\d+)", d)
    sc_i = max(1, min(5, int(mm.group(1)))) if mm else (rec.get("interrogator_score") or 3)
    tj = re.search(r"TRAJECTORY:\s*([A-Z]+)", d)
    return {
        "bull_thesis": rec.get("bull_thesis", ""), "bear_thesis": rec.get("bear_thesis", ""),
        "consensus_delta": rec.get("consensus_delta", ""), "valley_of_death": rec.get("valley_of_death", ""),
        "positioning_washout": rec.get("positioning_washout", ""), "moderator_conclusion": rec.get("moderator_conclusion", ""),
        "forcing_function": rec.get("forcing_function", ""), "conviction": int(rec.get("conviction", 0) or 0),
        "value_conviction": rec.get("value_conviction"),
        "verdict": rec.get("verdict", ""), "interrogator_dossier": d, "interrogator_score": sc_i,
        "trajectory": (tj.group(1) if tj else rec.get("trajectory", "")), "engine": "opus-5-regime",
        "sop_fair_value": rec.get("sop_fair_value", ""), "sop_breakdown": rec.get("sop_breakdown", ""),
        "sop_bull": rec.get("sop_bull", ""), "sop_bear": rec.get("sop_bear", ""),
        "risk_reward": rec.get("risk_reward", ""), "catalyst_status": rec.get("catalyst_status", ""),
        "peer_comps_note": rec.get("peer_comps_note", ""),
        # badge for debated-but-not-seated names: skeptic joined from the raw shard
        # (Director-pick skeptic fields don't exist off-board)
        "risk_badge": risk_badge(rec, skeptic_shard(sym)),
    }

overlaid, pm_missing = 0, []
for _meth, _b in (baskets.get("per_methodology_baskets") or {}).items():
    _picks = _b.get("picks") if isinstance(_b, dict) else _b
    if not isinstance(_picks, list):
        continue
    for _p in _picks:
        if not isinstance(_p, dict):
            continue
        _ov = _opus_overlay(_p.get("symbol"))
        if _ov:
            _p.update(_ov); overlaid += 1
        else:
            pm_missing.append(_p.get("symbol"))
print(f"  per-methodology picks overlaid with Opus debate: {overlaid} (no Opus debate yet: {pm_missing})")

BASKETS_LOCAL.write_text(json.dumps(baskets, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
# Radar peer-groups → public fallback (+ GCS below) so the stock page renders real comparable peers.
PEER_SRC = BK / "peer_groups.json"
PEER_LOCAL = PUB / "peer_groups.json"
if PEER_SRC.exists():
    PEER_LOCAL.write_text(PEER_SRC.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"  copied peer_groups.json -> {PEER_LOCAL}")
held = [e["symbol"] for e in entries if e["held_since_prior"]]
rotated_out = [s for s in prior_apex if s not in {e["symbol"] for e in entries}]
print(f"\nwrote {len(entries)} apex names -> {BASKETS_LOCAL}")
print(f"  new basket: {[e['symbol'] for e in entries]}")
print(f"  held (entry preserved): {held or 'none'}")
print(f"  rotated OUT (now closed in tracking): {rotated_out}")
print(f"tracking (equal-weight, legacy): nav={track_summary.get('nav')} since_inception={track_summary.get('since_inception_pct')}% "
      f"open={track_summary.get('n_open')} closed={track_summary.get('n_closed')}")
_tsw = track_summary_w or {}
print(f"tracking (DIRECTOR-WEIGHTED = the UI number): nav={_tsw.get('nav')} since_inception={_tsw.get('since_inception_pct')}% "
      f"open={_tsw.get('n_open')} closed={_tsw.get('n_closed')}")
print(f"  preserved: capitulation_watchlist({len(baskets.get('capitulation_watchlist', []))}), "
      f"per_methodology_baskets({len(baskets.get('per_methodology_baskets', {}))})")

# ── Debate HISTORY (per-symbol, dated) — append THIS run's debate to each name's history so the
#    stock page can show a timestamped dropdown of past debates. Per-symbol files keep each stock
#    page's load light (it fetches only its own ~100KB). Prior history is read from the local mirror
#    (the working copy that persists between runs), falling back to GCS for a name seen for the first
#    time on this machine. One entry per run-date (re-running today replaces today's), capped at 12.
HIST_DIR = PUB / "speculair_debate_history"
HIST_DIR.mkdir(exist_ok=True)
RUN_TS = datetime.now(timezone.utc).isoformat()


def _hist_entry(rec, dossier, date_str, ts):
    e = {
        "date": date_str, "timestamp": ts,
        "verdict": rec.get("verdict", ""), "conviction": int(rec.get("conviction", 0) or 0),
        "value_conviction": rec.get("value_conviction"),
        "trajectory": rec.get("trajectory", ""),
        "interrogator_score": int(rec.get("interrogator_score", 0) or 0),
        "transcript_source": rec.get("transcript_source", "fmp"), "source": rec.get("source", ""),
        "bull_thesis": rec.get("bull_thesis", ""), "bear_thesis": rec.get("bear_thesis", ""),
        "consensus_delta": rec.get("consensus_delta", ""), "forcing_function": rec.get("forcing_function", ""),
        "valley_of_death": rec.get("valley_of_death", ""), "positioning_washout": rec.get("positioning_washout", ""),
        "moderator_conclusion": rec.get("moderator_conclusion", ""),
        "sop_fair_value": rec.get("sop_fair_value", ""), "sop_breakdown": rec.get("sop_breakdown", ""),
        "risk_reward": rec.get("risk_reward", ""), "catalyst_status": rec.get("catalyst_status", ""),
        "peer_comps_note": rec.get("peer_comps_note", ""),
        "interrogator_dossier": dossier, "engine": "opus-5-regime",
        "risk_badge": risk_badge(rec, skeptic_shard(rec.get("symbol") or "")),
    }
    # Passthrough tags (when the engine stamped them): lane + carry provenance for the history view.
    # Additive only — dedup key (date) and entry ordering are untouched.
    for _k in ("lane", "carried"):
        if rec.get(_k) is not None:
            e[_k] = rec[_k]
    return e


hist_n = 0
for _f in sorted(RES.glob("*.json")):
    _sym = _f.stem
    _rec = load(_f)
    if not _rec or not _rec.get("bull_thesis"):
        continue
    _local = HIST_DIR / f"{_sym}.json"
    _prior = load(_local)
    if not isinstance(_prior, list):
        _prior = gcs_io.gcs_read_json_fresh(f"scans/speculair_debate_history/{_sym}.json")  # append RMW — generation-pinned
        if not isinstance(_prior, list):
            _prior = []
    _prior = [e for e in _prior if isinstance(e, dict) and e.get("date") != TODAY]  # one entry per run-date
    _prior.append(_hist_entry(_rec, dossier_for(_sym), TODAY, RUN_TS))
    _prior = _prior[-12:]                                                            # cap history depth
    _local.write_text(json.dumps(_prior, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    hist_n += 1
print(f"  debate history: appended {TODAY} to {hist_n} per-symbol files -> {HIST_DIR}")

if args.gcs:
    import subprocess
    print("  pushing to production GCS...")
    for local, remote in [(BASKETS_LOCAL, "scans/speculair_baskets.json"),
                          (TRACK_LOCAL, "scans/speculair_apex_tracking.json"),
                          (PUB / "speculair_apex_tracking_weighted.json", "scans/speculair_apex_tracking_weighted.json")]:
        try:
            # shell=True so Windows resolves gcloud.cmd (a batch shim) via cmd.exe
            cmd = f'gcloud storage cp "{local}" "gs://{gcs_io.GCS_BUCKET}/{remote}"'
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            print(f"  GCS push {remote}: {'OK' if r.returncode == 0 else 'FAILED ' + (r.stderr or '')[-200:]}")
        except Exception as e:
            print(f"  GCS push {remote}: ERROR {e}")
    # Push the per-symbol debate-history dir (recursive) so stock pages can load past debates.
    try:
        cmd = f'gcloud storage cp -r "{HIST_DIR}" "gs://{gcs_io.GCS_BUCKET}/scans/"'
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        print(f"  GCS push scans/speculair_debate_history/: {'OK' if r.returncode == 0 else 'FAILED ' + (r.stderr or '')[-200:]}")
    except Exception as e:
        print(f"  GCS push history dir: ERROR {e}")
    # Push the Radar peer-groups so the stock page can render true comparable peers + relative comps.
    try:
        if PEER_LOCAL.exists():
            cmd = f'gcloud storage cp "{PEER_LOCAL}" "gs://{gcs_io.GCS_BUCKET}/scans/peer_groups.json"'
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            print(f"  GCS push scans/peer_groups.json: {'OK' if r.returncode == 0 else 'FAILED ' + (r.stderr or '')[-200:]}")
    except Exception as e:
        print(f"  GCS push peer_groups: ERROR {e}")
    # Round-trip verify so the hands-off run self-confirms what is actually LIVE, without a separate
    # (non-allowlisted) gcloud-cat|python-c step. STEP 4 of the SKILL just reads this line.
    # Use `gcloud storage cat` (NOT gcs_io.gcs_read_json) — the public-URL read can hit a stale GCS/CDN
    # cache right after a write and report the OLD apex; the gcloud client reads through fresh.
    try:
        rb = subprocess.run(f'gcloud storage cat "gs://{gcs_io.GCS_BUCKET}/scans/speculair_baskets.json"',
                            shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        live = json.loads(rb.stdout) if (rb.returncode == 0 and rb.stdout) else {}
        print(f"  LIVE readback (fresh): apex={[p.get('symbol') for p in live.get('apex_basket', [])]} "
              f"engine={live.get('engine')} per_methodology_baskets={len(live.get('per_methodology_baskets', {}))}")
    except Exception as e:
        print(f"  LIVE readback failed: {e}")
