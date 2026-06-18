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
args = ap.parse_args()
TODAY = args.date or datetime.now(timezone.utc).date().isoformat()
E.load_api_keys()


def load(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


# ── Authoritative bases from GCS (fall back to local) ────────────────────
baskets = gcs_io.gcs_read_json("scans/speculair_baskets.json") or load(BASKETS_LOCAL, {}) or {}
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
        for _meth, _b in _meth_src.items():
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
gcs_track = gcs_io.gcs_read_json("scans/speculair_apex_tracking.json")
if gcs_track:
    TRACK_LOCAL.write_text(json.dumps(gcs_track, indent=2), encoding="utf-8")
    print(f"refreshed local tracking from GCS: nav={gcs_track.get('nav')} positions={len(gcs_track.get('positions', {}))}")

director = load(BK / "apex_basket_opus_regime.json") or {}
picks = director.get("apex_basket", [])
if not picks:
    print("ERROR: apex_basket_opus_regime.json has no picks — aborting.")
    sys.exit(1)

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
    entries.append({
        "symbol": sym,
        "conviction": int(p.get("director_conviction", 0)),
        "debate_conviction": int(rec.get("conviction", 0) or 0),
        "entry_price": prior.get("entry_price") or apex_pos.get(sym, {}).get("entry_price") or sc.get("price") or 0,
        "entry_date": prior.get("entry_date") or apex_pos.get(sym, {}).get("entry_date") or TODAY,
        "held_since_prior": sym in prior_apex,
        "source_methodologies": meths,
        "director_rationale": rationale,
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
        "size_units": p.get("size_units"),
        "size_units_effective": p.get("size_units_effective"),
        # apex skeptic + moat terminal-erosion (stamped by _regime_post) — surfaced per seat for the UI
        "skeptic_verdict": p.get("skeptic_verdict", ""),
        "skeptic_kill_fact": p.get("skeptic_kill_fact", ""),
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
        "engine": "opus-4.8-regime",
    })

# ── Wheel suggestions (CSP->CC) on the regime entries — Director-tag fallback + live CSP yield ──
stamp_wheel(entries, "regime", {e["symbol"]: {"price": scan_by_sym.get(e["symbol"], {}).get("price")} for e in entries})

# ── Update the apex track record for the rotation (reuses production logic) ──
try:
    track_summary = E._update_apex_tracking(entries, push_gcs=False)
except Exception as e:
    print(f"WARN: _update_apex_tracking failed ({e}); preserving prior tracking summary.")
    track_summary = baskets.get("apex_tracking", {})

# ── Director-weighted NAV (parallel to equal-weight) ────────────────────────
# The regime Director risk-sizes the book in his memo (defensive anchors larger, cyclical tails
# "held smallest on purpose"). Weight basis = the Director's structured size_units when present,
# else his director_conviction (0-100) — his own per-seat scoring. Card shows this as primary;
# the equal-weight chain stays as the continuity series.
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
            units[e["symbol"]] = max(0.1, (e.get("conviction") or 0) / 100.0)
    tot = sum(units.values()) or 1.0
    return {s: round(u / tot, 4) for s, u in units.items()}

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
baskets["director_memo"] = director.get("director_memo", baskets.get("director_memo", ""))
baskets["regime_changes"] = director.get("regime_changes", "")
baskets["regime_basis"] = "CATALYST_WATCH_REGIME.md (2026-06-05 baseline)"
baskets["engine"] = "opus-4.8-claude-code-subagents"
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
baskets["risk_stance"] = director.get("risk_stance") or _stance_map.get(_macro.get("regime"), "balanced")
baskets["macro_read"] = director.get("macro_read", "")
baskets["macro_regime"] = {"regime": _macro.get("regime"), "score": _macro.get("score"), "regime_detail": _macro.get("regime_detail", {})}
baskets["book_expected_return_pct"] = round(_exp_tot / _exp_w, 1) if _exp_w > 0 else None
baskets["book_horizon_months"] = round(_hor_tot / _hor_w, 1) if _hor_w > 0 else None
baskets["generated_at"] = datetime.now(timezone.utc).isoformat()
baskets["director_last_run"] = baskets["generated_at"]
baskets["rebalance_date"] = TODAY

# ── Overlay Opus debates onto every per-methodology basket pick (so all stock pages show Opus) ──
def _opus_overlay(sym):
    rec = load(RES / f"{sym}.json")
    if not rec or not rec.get("bull_thesis"):
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
        "verdict": rec.get("verdict", ""), "interrogator_dossier": d, "interrogator_score": sc_i,
        "trajectory": (tj.group(1) if tj else rec.get("trajectory", "")), "engine": "opus-4.8-regime",
        "sop_fair_value": rec.get("sop_fair_value", ""), "sop_breakdown": rec.get("sop_breakdown", ""),
        "sop_bull": rec.get("sop_bull", ""), "sop_bear": rec.get("sop_bear", ""),
        "risk_reward": rec.get("risk_reward", ""), "catalyst_status": rec.get("catalyst_status", ""),
        "peer_comps_note": rec.get("peer_comps_note", ""),
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
print(f"  apex_tracking: nav={track_summary.get('nav')} since_inception={track_summary.get('since_inception_pct')}% "
      f"open={track_summary.get('n_open')} closed={track_summary.get('n_closed')}")
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
    return {
        "date": date_str, "timestamp": ts,
        "verdict": rec.get("verdict", ""), "conviction": int(rec.get("conviction", 0) or 0),
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
        "interrogator_dossier": dossier, "engine": "opus-4.8-regime",
    }


hist_n = 0
for _f in sorted(RES.glob("*.json")):
    _sym = _f.stem
    _rec = load(_f)
    if not _rec or not _rec.get("bull_thesis"):
        continue
    _local = HIST_DIR / f"{_sym}.json"
    _prior = load(_local)
    if not isinstance(_prior, list):
        _prior = gcs_io.gcs_read_json(f"scans/speculair_debate_history/{_sym}.json")
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
