#!/usr/bin/env python3
"""weekly_opus_refresh.py — driver for the weekly all-Opus Speculair refresh.

`prep`  : source the candidate universe from PRODUCTION GCS (all 11 per_methodology_baskets
          + current apex), build per-name input bundles (metrics) + fetch FMP transcripts,
          dump the engine system prompts, and EMIT a self-contained debate workflow JS with
          the candidate list baked in (sidesteps the Workflow `args` delivery bug). Prints the
          scriptPath + candidate count for the scheduled run to hand to the Workflow tool.

The scheduled SKILL.md runs:
  python weekly_opus_refresh.py prep            (raw-screen universe + bundles + ledger re-check routing)
  -> Workflow({scriptPath: <printed>})          (Radar [sonnet] -> Debate [opus] -> Director [opus])
  -> python weekly_opus_refresh.py regime-skeptic -> Workflow(...)    (APEX kill-tier, opus; moat-aware, default REFUTED)
  -> python weekly_opus_refresh.py regime-post                        (apex: consume skeptic + moat-erosion + secular-theme caps)
  -> python _opus_debate/publish_to_frontend.py --gcs                 (regime/catalyst book; reads post-skeptic, capped apex)
  -> python weekly_opus_refresh.py value-input                        (value signals + funnel stats + ledger)
  -> [value Director agent, opus]
  -> python weekly_opus_refresh.py value-skeptic -> Workflow(...)     (independent kill-tier, opus)
  -> python weekly_opus_refresh.py value-post                         (deterministic safety layer; consumes skeptic)
  -> python weekly_opus_refresh.py value-csv / baskets-csv
  -> python weekly_opus_refresh.py value-publish --gcs                (value book + both NAV trackers)
Periodic verbs: control-sample (monthly funnel miss-rate), value-revalidate (stale-anchor pro-forma
re-debate — pending fold into a delta-mode trigger, see the pipeline-v3 plan).
FUTURE RESOURCES (FUTURE_RESOURCES_SPEC.md — separate two-lane commodity/power/machine book, NOT in
the weekly auto-run yet; monthly + Lane-A weekly, launched by hand until Bruno wires the cadence):
  fr-universe   (monthly Stage A/B two-lane screen -> future_resources/_candidates.json)
  fr-map        (Phase 2: emit the chunked Sonnet chain-map workflow -> future_resources/_fr_map.js)
  fr-map-merge  (Phase 2: merge chain-map shards -> chain_map/<SYM>.json + universe.json; royalty
                 bypass, physical-anchor + zero-map guards)
  fr-prep / fr-input / [FR Director agent] / fr-post / fr-csv / fr-publish
                (Phase 3: Lane A debate -> grade input -> Director -> deterministic post -> CSV/publish)
  torque metrics live in backend/_opus_debate/_resource_metrics.py (stamped by fr-input).
(shadow-debate/shadow-diff and the Disruptor Lens Phases 1-5 were deleted 2026-07-10 — dead since the
2026-06-13 Fable retirement and the 2026-07-02 Disruptor retirement respectively; see git history.)

Robust by construction: each name is a SINGLE-agent full Opus regime debate (Interrogator+
Architect+Moderator in one pass, schema-less, inline regime brief) — the pattern that proved
reliable; no fragile inter-stage handoff, no StructuredOutput dependency.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

BK = r"C:\Users\Bruno\Stock-Screener\backend"
if not os.path.isdir(BK):                       # portability fallback: run from this file's own dir
    BK = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BK); sys.path.insert(0, os.path.join(BK, "alpha_compounder"))
os.chdir(BK)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import live_debate_engine as E  # noqa: E402
import gcs_io  # noqa: E402
import requests  # noqa: E402
import _numeric_core  # noqa: E402  shared valuation arithmetic (2026-07-10 extraction)
from agent_voice import AGENT_VOICE  # noqa: E402  # house-voice preamble for the director prompts (prose only)

ROOT = Path("_opus_debate")
INP, TXT, RES = ROOT / "inputs", ROOT / "transcripts", ROOT / "results_regime"
for d in (INP, TXT, RES, ROOT / "dossiers"):
    d.mkdir(parents=True, exist_ok=True)

# ── Model seats (single source of truth; every workflow/agent pin reads these) ──
# Fable RETIRED 2026-07-10 (pipeline-v3 plan, Week 1) — this is the second and, per Bruno's
# directive ("Fable needs to be retired from the multi-agent debate"), the durable retirement:
# every reasoning seat in the weekly pipeline is now Opus/Sonnet/Haiku, no Fable seat anywhere.
# (History: Fable was retired once already 2026-06-13, revived 2026-07-01, and is retired again
# here — this time by explicit instruction, not an availability fallback, so it should stay put.)
# Director + Skeptic seats are Opus (money moves through these decisions — highest-scrutiny model);
# Radar stays Sonnet (cheap peer-comp sorting); the per-name Debate stays Opus.
# NOTE: the two Director self-descriptions (VALUE_DIRECTOR_PROMPT + the weekly workflow
# template) name the seat model in prose — keep them in sync when flipping these.
RADAR_MODEL = "sonnet"
DEBATE_MODEL = "opus"
DIRECTOR_MODEL = "opus"    # Fable retired 2026-07-10 (pipeline-v3 Week 1) — was fable 07-01→07-10
SKEPTIC_MODEL = "opus"     # Fable retired 2026-07-10 (pipeline-v3 Week 1) — was fable 07-01→07-10

# ── Director rotation discipline: the prior-decision ledger (continuity + anti-whipsaw) ──
# Each book persists every Director keep/drop/add for the YEAR in _decision_history.json so the
# next Director is CONFRONTED BY ITS OWN PRIOR CALLS. write_director_ledger() renders the per-book
# {year} ledger the Director reads BEFORE deciding; append_decision_history() records this run's
# decisions AFTER the Director writes the basket. Both best-effort — they NEVER raise, so a ledger
# bug can never break the debate/publish pipeline (callers also wrap defensively).
# 2026-07-10: DECISION_HISTORY/_book_apex/append_decision_history moved to the shared _ledger.py
# (backend/_ledger.py) — publish_to_frontend.py used to carry an inline copy of this exact logic
# solely to dodge this module's os.chdir() side-effect; _ledger.py has no side effects, so both
# callers now share one implementation.
from _ledger import DECISION_HISTORY, LEDGER_YEAR, _book_apex, load_decision_history as _load_decision_history, append_decision_history

def write_director_ledger(book, prior_basket_path, tracking_path):
    """Render _director_ledger_<book>.txt — the prior-decision ledger the Director must reconcile
    its new basket against. Returns (path, n_held, n_dropped). Best-effort; never raises."""
    try:
        out = ROOT / f"_director_ledger_{book}.txt"
        hist = _load_decision_history().get(book, {})
        try:
            pj = json.load(open(prior_basket_path, encoding="utf-8"))
            prior = {p.get("symbol"): p for p in _book_apex(pj) if isinstance(p, dict) and p.get("symbol")}
        except Exception:
            prior = {}
        try:
            track = json.load(open(tracking_path, encoding="utf-8")) or {}
        except Exception:
            track = {}
        positions = track.get("positions") or {}
        closed = [c for c in (track.get("closed") or []) if str(c.get("exit_date", "")).startswith(LEDGER_YEAR)]
        L = [f"PRIOR-DECISION LEDGER — {book} book, {LEDGER_YEAR}. YOU authored these calls; you must justify",
             "every KEEP / DROP / ADD / RE-ADD in this run AGAINST them (see ROTATION DISCIPLINE in the rubric).",
             f"\nHELD NOW ({len(prior)}) — drop one only on a BROKEN thesis or a strictly-better orthogonal name:"]
        for s, p in prior.items():
            pos = positions.get(s, {})
            ed = pos.get("entry_date") or p.get("entry_date") or "?"
            conv = p.get("director_conviction") or p.get("value_score") or p.get("conviction") or "?"
            rat = (p.get("director_rationale") or p.get("thesis") or "").strip().replace("\n", " ")
            # 2026-07-11 (Weeks 3-4 Director anchoring): the ledger carries the NUMBERS, not just
            # the verbs — prior conviction is the clamp anchor; size/ER/target expose drift.
            nums = []
            for key, lab in (("size_units", "units"), ("expected_return_pct", "ER%"),
                             ("target_px", "target"), ("entry_price", "entry")):
                v = p.get(key)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    nums.append(f"{lab} {v:g}")
            comp = p.get("computed") or {}
            if isinstance(comp.get("rr_ratio"), (int, float)):
                nums.append(f"rr {comp['rr_ratio']:g}")
            L.append(f"  • {s}: HELD since {ed} (conv {conv}"
                     + (", " + ", ".join(nums) if nums else "") + f") — {rat[:220]}")
        if closed:
            L.append(f"\nDROPPED in {LEDGER_YEAR} ({len(closed)}) — a RE-ADD requires a DOCUMENTED THESIS CHANGE since the drop:")
            for c in sorted(closed, key=lambda c: c.get("exit_date", ""))[-40:]:
                L.append(f"  • {c.get('symbol')}: DROPPED {c.get('exit_date')} (held from {c.get('entry_date','?')}, realized {c.get('return_pct','?')}%)")
        if hist:
            L.append("\nDECISION TIMELINE (date · decision · why):")
            for s, evs in hist.items():
                evs = [e for e in evs if str(e.get("date", "")).startswith(LEDGER_YEAR)]
                if not evs:
                    continue
                tl = "; ".join(f"{e.get('date')} {e.get('decision')}: {(e.get('rationale') or '')[:80]}" for e in evs[-6:])
                L.append(f"  • {s}: {tl}")
        out.write_text("\n".join(L), encoding="utf-8")
        print(f"director ledger ({book}): {len(prior)} held + {len(closed)} dropped {LEDGER_YEAR} -> {out.name}")
        return str(out), len(prior), len(closed)
    except Exception as e:
        print(f"WARN: write_director_ledger({book}) failed ({e})")
        return "", 0, 0

# ── Return objective (Apex + Disruptor only; the Value Lens stays pure-value/patient) ──
# The Apex + Disruptor Directors target this and set a macro-driven risk_stance (reach vs defend).
RETURN_GOAL = {"low_pct": 30, "high_pct": 50, "horizon_months": 12}


def _write_macro_regime():
    """Fetch the live macro classifier (macro_regime.py v8) and write it where the Apex + Disruptor
    Directors read it, so their risk_stance is anchored to a structured macro read (not just prose).
    Self-heals via fetch_macro_regime's GCS last-known-good cache; neutral fallback on hard failure."""
    out = ROOT / "macro_regime.json"
    from datetime import datetime as _dt
    try:
        import macro_regime
        from screener_v6 import fmp
        r = macro_regime.fetch_macro_regime(fmp) or {}
        feat = r.get("features", {}) or {}
        doc = {
            "regime": r.get("regime", "NEUTRAL"),
            "score": r.get("score", 0.5),
            "regime_detail": r.get("regime_detail", {}),
            # growth x inflation 2x2 (2026-07-16) — GOLDILOCKS|REFLATION|STAGFLATION|RISK_OFF;
            # the Director's quadrant playbook + the regime-read agent both key off this.
            "quadrant": r.get("quadrant", "UNKNOWN"),
            "quadrant_basis": r.get("quadrant_basis", ""),
            "features": {k: feat.get(k) for k in
                         ("macro_vix", "macro_yield_spread", "macro_recession_prob",
                          "macro_cpi", "macro_unemployment") if k in feat},
            "version": r.get("version", ""),
            "asof": _dt.now().strftime("%Y-%m-%d"),
        }
    except Exception as e:
        print(f"WARN: macro_regime fetch failed ({e}) — writing NEUTRAL fallback")
        doc = {"regime": "NEUTRAL", "score": 0.5, "regime_detail": {}, "features": {},
               "quadrant": "UNKNOWN", "quadrant_basis": "",
               "asof": _dt.now().strftime("%Y-%m-%d"), "fallback": True}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"macro_regime: {doc['regime']} (score {doc.get('score')}) -> {out.name}")
    return doc

# LEGACY-9 method set — used ONLY for signal typing (deep_value vs catalyst), never for selection.
DEEP_VAL = {"epv", "graham_revised", "iv15_deep_value", "acquirers_multiple",
            "earnings_yield_gap", "owner_earnings", "dcf_fcff", "rd_capitalized_dcf", "ev_gross_profit"}
# 8e: convergence (multi-model agreement — the purest value signal in the system) and the true
# EV/GP basket are VALUE signals too; without this they were branded "catalyst" and routed down
# the Moderator's catalyst lens.
VALUE_SIGNAL_METHS = DEEP_VAL | {"convergence", "ev_gp", "value_drawdown", "neglect_orphan"}

REGIME_FILE = "CATALYST_WATCH_REGIME.md"  # repo root; read live each run for the current regime


def _ttm_cash_block(sym):
    """PATCH (2026-06-05): the screener metrics feed FISCAL-YEAR-ANNUAL FCF/EPS, which anchors
    the debate to stale cash even when the latest quarter inflected (the CON defect). Pull the
    last 4 quarters from FMP and surface TTM FCF + TTM diluted EPS + latest-quarter EPS YoY,
    flagged as overriding the annual figures. Returns '' on any failure (degrade gracefully)."""
    key = E.get_key("FMP_API_KEY")
    if not key:
        return ""
    base = "https://financialmodelingprep.com/stable"
    try:
        cf = requests.get(base + "/cash-flow-statement",
                          params={"symbol": sym, "period": "quarter", "limit": 5, "apikey": key}, timeout=20).json()
        inc = requests.get(base + "/income-statement",
                           params={"symbol": sym, "period": "quarter", "limit": 8, "apikey": key}, timeout=20).json()
    except Exception:
        return ""
    if not (isinstance(cf, list) and isinstance(inc, list) and len(cf) >= 4 and len(inc) >= 4):
        return ""

    def num(d, *ks):
        for k in ks:
            v = d.get(k) if isinstance(d, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return v
        return None

    fcfs = [num(q, "freeCashFlow") for q in cf[:4]]
    if any(v is None for v in fcfs):  # fallback: OCF + capex (capex stored negative)
        fcfs = [(num(q, "operatingCashFlow") or 0) + (num(q, "capitalExpenditure") or 0) for q in cf[:4]]
    ttm_fcf = sum(v for v in fcfs if isinstance(v, (int, float))) if fcfs else None
    epss = [num(q, "epsDiluted", "epsdiluted", "eps") for q in inc[:4]]
    ttm_eps = sum(epss) if all(isinstance(v, (int, float)) for v in epss) else None
    q0 = num(inc[0], "epsDiluted", "epsdiluted", "eps")
    q4 = num(inc[4], "epsDiluted", "epsdiluted", "eps") if len(inc) >= 5 else None
    yoy = ((q0 - q4) / abs(q4) * 100) if (isinstance(q0, (int, float)) and isinstance(q4, (int, float)) and q4) else None

    def amt(v):
        a = abs(v)
        return f"{v/1e9:.2f}B" if a >= 1e9 else (f"{v/1e6:.0f}M" if a >= 1e6 else f"{v:.0f}")

    parts = []
    if isinstance(ttm_fcf, (int, float)):
        parts.append(f"TTM FCF {amt(ttm_fcf)}")
    if isinstance(ttm_eps, (int, float)):
        parts.append(f"TTM diluted EPS {ttm_eps:.2f}")
    if isinstance(yoy, (int, float)):
        parts.append(f"latest-Q EPS YoY {yoy:+.0f}%")
    if not parts:
        return ""
    asof = (cf[0].get("date") if isinstance(cf[0], dict) else "") or ""
    return ("=== TTM / LATEST QUARTER (FMP, as of " + asof + " — USE THESE OVER THE FISCAL-YEAR-ANNUAL "
            "FCF/EPS ABOVE WHEN THEY DIFFER) ===\n" + " | ".join(parts))


def _fmp_segments(sym):
    """Best-effort FMP product-segmentation -> compact 'Segment: revenue (share%)' block for segment SoP.
    Returns '' on any failure (degrade gracefully, like the transcript fetch)."""
    key = E.get_key("FMP_API_KEY")
    if not key:
        return ""
    try:
        r = requests.get("https://financialmodelingprep.com/stable/revenue-product-segmentation",
                         params={"symbol": sym, "period": "annual", "apikey": key}, timeout=20).json()
    except Exception:
        return ""
    if not (isinstance(r, list) and r and isinstance(r[0], dict)):
        return ""
    latest = r[0]
    data = latest.get("data")
    if not isinstance(data, dict):
        for v in latest.values():
            if isinstance(v, dict):
                data = v
                break
    if not isinstance(data, dict):
        return ""
    segs = [(k, float(v)) for k, v in data.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v]
    if len(segs) < 2:   # one "segment" = no SoP signal
        return ""
    segs.sort(key=lambda kv: -abs(kv[1]))
    total = sum(abs(v) for _, v in segs) or 1.0
    # COVERAGE GATE (2026-07-08, KBR incident): FMP's annual segmentation row can be an aggregation
    # of INCOMPLETE quarters — for KBR FY2025 it returned MTS $1.34B vs its true $5.58B (segments
    # summed to only 45% of revenue), silently INVERTING the mix and the whole SoP the debate built
    # on it. If the segment sum doesn't cover ~80% of the company's annual revenue, the block is
    # actively misleading — drop it (the debate falls back to whole-company intrinsic per its step 4).
    try:
        inc = requests.get("https://financialmodelingprep.com/stable/income-statement",
                           params={"symbol": sym, "period": "annual", "limit": 1, "apikey": key},
                           timeout=20).json()
        rev = float(inc[0].get("revenue") or 0) if isinstance(inc, list) and inc else 0.0
    except Exception:
        rev = 0.0
    if rev > 0 and total < 0.8 * rev:
        print(f"  segments[{sym}]: DROPPED — cover only {total / rev * 100:.0f}% of revenue "
              f"({total / 1e9:.2f}B of {rev / 1e9:.2f}B): incomplete FMP segmentation would invert the mix")
        return ""

    def _a(v):
        a = abs(v)
        return f"{v/1e9:.2f}B" if a >= 1e9 else (f"{v/1e6:.0f}M" if a >= 1e6 else f"{v:.0f}")
    body = " | ".join(f"{k}: {_a(v)} ({v/total*100:.0f}%)" for k, v in segs[:8])
    asof = latest.get("date") or latest.get("fiscalYear") or ""
    return ("\n\n=== SEGMENT REVENUE (FMP, " + str(asof) + " — build a TRUE segment Sum-of-Parts: "
            "value each segment by its peer multiple, then sum) ===\n" + body)


_RADAR_FIELDS = ("p_fcf", "dcf_fcff_mos", "epv_mos", "graham_revised_mos", "owner_earnings_mos",
                 "iv15_deep_value_mos", "revenue_yoy", "revenue_cagr_3y", "eps_yoy", "gross_margin",
                 "net_margin", "roic_avg", "altman_z", "sma200", "proximity_52wk", "sector_momentum")


# ── Peer-identity / live-multiple overrides (Radar mis-map backstop) ──────────
# The Sonnet Radar invents an identity for tickers it does not recognize (observed:
# PLX.PA mapped to "Plastic Omnium / TIC services" AND to "IT-services" on different
# runs — it is actually PLUXEE, the Sodexo employee-benefits/voucher spin-off). The
# debate agents then correct the identity by hand but supply the peer MULTIPLE from
# stale training memory (Edenred "20-25x FCF" — its PRE-shock multiple). Nothing in the
# pipeline injects a LIVE peer multiple, so the anchor silently goes stale and inflates
# the apparent idiosyncratic discount. This override forces the TRUE identity + peers,
# stamps a CURRENT peer multiple (live FMP when a key is present; else the curated,
# sourced figure below), and tags whether the discount is idiosyncratic (name-specific
# alpha) or sector_regulatory (shared-factor BETA — both names move on the same
# unresolved driver, so a correlation-stressed apex basket must DISCOUNT it, not credit
# it as edge). Applied deterministically at the end of merge_radar() every Radar phase.
PEER_OVERRIDES = {
    "PLX.PA": {
        "name": "Pluxee",
        "true_peers": ["EDEN.PA", "SW.PA"],   # Edenred (direct duopoly peer), Sodexo (former parent)
        "anchor_peer": "EDEN.PA",
        "convergence": "sector_regulatory",
        # Curated, sourced fallback used when the live FMP fetch is unavailable. Edenred
        # has DE-RATED on the identical Brazil PAT reform + Italy voucher shock: ~10.3x
        # 2026e P/E (Oddo BHF: ~60% below its 9-yr avg fwd multiple), <7x 2028E EPS vs a
        # 15-yr avg ~26x, ~4.1x EV/2026e EBITDA. The "20-25x" in older dossiers is the
        # PRE-shock multiple and must not be used as the anchor.
        "anchor_multiple": {"pe_fwd": 10.3, "ev_ebitda_fwd": 4.1, "asof": "2026-06",
                            "source": "Oddo BHF / sell-side 2026e (de-rated post-Brazil PAT + Italy reform)"},
        "note": ("Pluxee (PLX.PA) and Edenred (EDEN.PA) are the employee-benefits/voucher "
                 "near-duopoly and BOTH de-rated on the SAME regulatory shock — the Brazil "
                 "PAT reform + Italy voucher cap (Kepler cut PLX EUR28->EUR18 and EDEN "
                 "EUR40->EUR28 on the same event). Edenred now trades ~10x fwd P/E / ~4x "
                 "EV/2026e EBITDA, NOT its pre-shock 20-25x. Pluxee at ~5x P/FCF vs a ~10x "
                 "Edenred is a MODEST discount, largely justified by Pluxee's heavier Brazil "
                 "concentration (guided ~50% Brazil revenue drop; Edenred took an 8-12% group "
                 "EBITDA hit on the same reforms). The convergence is SECTOR-REGULATORY BETA "
                 "on a shared, unresolved factor — NOT idiosyncratic single-name alpha — which "
                 "is exactly what a correlation-stressed apex basket is built to discount."),
    },
}


def _live_peer_multiple(ticker):
    """Best-effort LIVE current multiple for a peer ticker via FMP stable (returns None if
    no key / endpoint unavailable). Trailing-TTM, used as a live sanity anchor ALONGSIDE the
    curated forward figure — both are 'current', which is the whole point: never a remembered
    pre-shock multiple."""
    try:
        import datetime
        import screener_v6 as S
        if not getattr(S, "FMP_KEY", ""):
            return None
        q = S.fmp("quote", {"symbol": ticker}) or []
        km = S.fmp("key-metrics-ttm", {"symbol": ticker}) or []
        rt = S.fmp("ratios-ttm", {"symbol": ticker}) or []
        q, km, rt = (q[0] if q else {}), (km[0] if km else {}), (rt[0] if rt else {})
        pe = q.get("pe") or rt.get("priceEarningsRatioTTM")
        ev_ebitda = km.get("enterpriseValueOverEBITDATTM") or km.get("evToEBITDATTM")
        if pe is None and ev_ebitda is None:
            return None
        return {"pe_ttm_live": round(pe, 1) if isinstance(pe, (int, float)) else None,
                "ev_ebitda_ttm_live": round(ev_ebitda, 1) if isinstance(ev_ebitda, (int, float)) else None,
                "live_asof": datetime.date.today().isoformat(), "live_source": "FMP stable TTM"}
    except Exception as e:
        print(f"  peer-override: live multiple for {ticker} unavailable ({e})")
        return None


def _apply_peer_overrides(out, pgd):
    """Force true identity + LIVE/curated peer multiple + convergence tag for Radar-mis-mapped
    names. Mutates `out` in place AND rewrites the per-symbol files. Idempotent: preserves the
    raw Radar output under _radar_* keys so re-runs don't compound. Returns the # of names fixed."""
    fixed = 0
    for sym, ov in PEER_OVERRIDES.items():
        if sym not in out:
            continue   # not in this run's universe
        e = dict(out[sym]) if isinstance(out.get(sym), dict) else {}
        # Preserve the raw Radar mapping ONCE (don't overwrite on re-stamp).
        e.setdefault("_radar_peers_raw", e.get("peers", []))
        e.setdefault("_radar_relative_comps_raw", e.get("relative_comps", ""))
        e.setdefault("_radar_verdict_raw", e.get("verdict", ""))
        anchor = dict(ov["anchor_multiple"])
        live = _live_peer_multiple(ov.get("anchor_peer", ""))
        if live:
            anchor.update(live)
        e["peers"] = list(ov["true_peers"])
        e["peer_override"] = True
        e["identity"] = ov["name"]
        e["convergence"] = ov["convergence"]
        e["anchor_peer"] = ov.get("anchor_peer", "")
        e["anchor_multiple"] = anchor
        e["convergence_note"] = ov["note"]
        ap = ov.get("anchor_peer", "peer")
        mult_txt = f"~{anchor.get('pe_fwd')}x fwd P/E / ~{anchor.get('ev_ebitda_fwd')}x EV/EBITDA"
        if anchor.get("pe_ttm_live"):
            mult_txt += f" (live TTM P/E ~{anchor['pe_ttm_live']}x)"
        e["relative_comps"] = (
            f"[PEER ANCHOR CORRECTED — Radar mis-mapped {sym} as "
            f"'{(e.get('_radar_relative_comps_raw') or '')[:48].strip()}…'] {ov['name']} ({sym}): "
            f"anchor peer {ap} now trades {mult_txt} ({anchor.get('source')}), NOT the pre-shock "
            f"20-25x cited from memory in older dossiers. {ov['note']}")
        e["verdict"] = "modest_discount_sector_beta" if ov["convergence"] == "sector_regulatory" else e.get("verdict", "")
        e["rationale"] = ov["note"]
        out[sym] = e
        try:
            (pgd / f"{sym}.json").write_text(json.dumps(e, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        fixed += 1
        print(f"  peer-override applied: {sym} -> {ov['name']} (anchor {ap} {mult_txt}; convergence={ov['convergence']})")
    return fixed


def merge_radar():
    """Merge the chunked Radar shards (_opus_debate/_pg_*.json) into peer_groups.json,
    deterministically. The Radar runs as N parallel Sonnet agents (one per sector chunk); merging by
    an LLM would force it to re-emit all ~160 entries in one response, which TRUNCATES — so it is a
    plain dict-update here. Invoked as the final step of the Radar phase via this allowlisted CLI."""
    import glob
    out, shards = {}, sorted(glob.glob(str(ROOT / "_pg_*.json")))
    for f in shards:
        try:
            d = json.load(open(f, encoding="utf-8"))
            if isinstance(d, dict):
                out.update(d)
        except Exception as e:
            print(f"  WARN: {os.path.basename(f)} skipped ({e})")
    # Also explode to per-symbol files: the combined 161-entry file is ~29k tokens, over the 25k Read
    # cap, so each debate agent reads ONLY its own small entry from peer_groups/<sym>.json.
    pgd = ROOT / "peer_groups"
    pgd.mkdir(exist_ok=True)
    # Backstop the Radar's identity mis-maps (PLX.PA etc.) with true peers + a LIVE/curated
    # multiple BEFORE writing, so the debate never reads an invented peer set or a stale anchor.
    n_ovr = _apply_peer_overrides(out, pgd)
    (ROOT / "peer_groups.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for _sym, _e in out.items():
        try:
            (pgd / f"{_sym}.json").write_text(json.dumps(_e, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    print(f"merged {len(shards)} Radar shards -> peer_groups.json ({len(out)} entries) "
          f"+ per-symbol files ({n_ovr} peer-override(s) applied)")
    return len(out)


def peer_overrides_restamp(push_frontend=False):
    """Deterministic re-stamp of PEER_OVERRIDES onto the EXISTING peer_groups (no Radar re-run) —
    so a corrected anchor lands now, ahead of the next weekly debate. Optionally syncs the frontend
    copy the stock-page peer-comps section reads."""
    import shutil
    pgf = ROOT / "peer_groups.json"
    if not pgf.exists():
        print("no peer_groups.json — nothing to re-stamp"); return 0
    out = json.load(open(pgf, encoding="utf-8"))
    pgd = ROOT / "peer_groups"; pgd.mkdir(exist_ok=True)
    n = _apply_peer_overrides(out, pgd)
    pgf.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if push_frontend:
        dst = Path(BK).parent / "frontend" / "public" / "peer_groups.json"
        try:
            shutil.copyfile(pgf, dst)
            print(f"  synced -> {dst}")
        except Exception as e:
            print(f"  frontend sync FAILED: {e}")
    print(f"peer-override re-stamp complete: {n} name(s) corrected")
    return n


def _val_money(s):
    """Parse a CRO fair-value string ('~$12-13', '$78-88 (base case ~$82)', '$12.5') to a float."""
    import re
    if s is None:
        return None
    txt = str(s)
    m = re.search(r'base[^$0-9]{0,14}\$?\s*([0-9]+(?:\.[0-9]+)?)', txt, re.I)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass
    vals = []
    for n in re.findall(r'([0-9]+(?:\.[0-9]+)?)', txt):
        try:
            vals.append(float(n))
        except Exception:
            pass
    if not vals:
        return None
    if len(vals) >= 2 and vals[1] <= vals[0] * 3:   # 'lo-hi' range -> midpoint
        return round((vals[0] + vals[1]) / 2, 2)
    return vals[0]


def _funded_leverage(symbols):
    """Net-funded-debt/EBITDA + interest coverage (TTM, FMP /stable/) per symbol, cached to
    funded_leverage.json. Funded debt = interest-bearing only, so settlement/payroll float and
    policyholder reserves are structurally excluded — a cleaner solvency test than Altman-Z (which
    uses total liabilities and over-penalizes float/reserve businesses)."""
    import concurrent.futures
    cache_p = ROOT / "funded_leverage.json"
    cache = {}
    if cache_p.exists():
        try:
            cache = json.load(open(cache_p, encoding="utf-8"))
        except Exception:
            cache = {}
    key = os.environ.get("FMP_API_KEY") or "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"
    todo = [s for s in symbols if s not in cache]

    def one(sym):
        nd = ic = None
        try:
            km = requests.get("https://financialmodelingprep.com/stable/key-metrics-ttm",
                              params={"symbol": sym, "apikey": key}, timeout=15).json()
            if isinstance(km, list) and km:
                nd = km[0].get("netDebtToEBITDATTM")
        except Exception:
            pass
        try:
            r = requests.get("https://financialmodelingprep.com/stable/ratios-ttm",
                             params={"symbol": sym, "apikey": key}, timeout=15).json()
            if isinstance(r, list) and r:
                ic = r[0].get("interestCoverageRatioTTM")
        except Exception:
            pass
        return sym, {"net_funded_debt_ebitda": nd, "interest_coverage": ic}

    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for sym, v in ex.map(one, todo):
                cache[sym] = v
        cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache


def _funded_solvency(sector, ndE, icov):
    """Bucket funded leverage: financials exempt; <0 or <=2x w/ healthy coverage = strong;
    <=3.5x w/ >=3x coverage = moderate; else weak (the joint-weakness near-veto candidates)."""
    if "financ" in (sector or "").lower():
        return "exempt_financial"
    if not isinstance(ndE, (int, float)):
        return "unknown"
    if ndE < 0 or (ndE <= 2.0 and (not isinstance(icov, (int, float)) or icov >= 4)):
        return "strong"
    if ndE <= 3.5 and (not isinstance(icov, (int, float)) or icov >= 3):
        return "moderate"
    return "weak"


# Moat durability / terminal-erosion classifier — extracted to backend/_moat.py so the regime
# post-processor (_opus_debate/_regime_post.py) reuses the SAME implementation without importing this
# (API-keyed) module. A SECOND family of teeth, ADDITIVE to the cyclical-peak/stale-anchor gates.
from _moat import moat_features as _moat_features  # noqa: E402


VALUE_DIRECTOR_PROMPT = AGENT_VOICE + """You are the SPECULAIR VALUE DIRECTOR (Claude Opus 4.8), allocating REAL capital on a PURE VALUE rubric with the CATALYST_WATCH_REGIME overlay FULLY REMOVED (a live catalyst is neither a plus nor a requirement). Read backend/_opus_debate/value_grade_input.json — one row per debated name, every field pre-computed.

SYSTEM OF RECORD (decisive — read FIRST). The multi-agent DEBATE already ran on each name. When the debate conflicts with the raw scan factors, THE DEBATE WINS:
  - `sop_mos_pct` (the CRO's reconciled sop_fair_value expressed as MoS vs price) is the SYSTEM-OF-RECORD margin of safety, NOT the 5-method `mos_spread` (that is the RAW scan MoS and can be built on stale/peak inputs). Where sop_mos_pct sits FAR BELOW the raw scan MoS (see `scan_headline_mos_pct`), the raw MoS is an ARTIFACT — trust sop_mos_pct.
  - `forensic_gate`: "EXCLUDE" => INELIGIBLE for the apex (interrogator credibility<=2 — a forensic red flag the factors miss). "CAP" => value_score capped at ~50 (DETERIORATING trajectory: credible but worsening). These are regime-INDEPENDENT forensics; a factor-cheap name NEVER overrides them.
  - `debate_verdict` letter: set partly under the (now-removed) catalyst regime, so it is NOT a blanket cap. BUT a verdict-C name is eligible ONLY if its CRO-normalized `sop_mos_pct` is genuinely positive AND it clears the forensic gate AND it is not a peak/stale artifact — otherwise the C is just confirming the raw MoS is fake. Name in the value_memo every verdict-C name you keep and justify it on pure-value grounds.
  - `value_conviction` (1-5, when present): the CRO's CATALYST-BLIND value score — judged on valuation + forensics with the regime overlay explicitly ignored. PREFER it over `debate_conviction` everywhere in this rubric (debate_conviction is regime-tilted and collapses to a constant in catalyst-light pools). Where value_conviction is null (older results), fall back to debate_conviction but say so.

RUBRIC — four pillars ~25 pts each, applied ONLY to names that clear the gate:
1. MARGIN OF SAFETY — primary = sop_mos_pct (CRO-normalized). Cross-check `mos_spread` AGREEMENT (4-5/5 models positive = high-confidence cheap) but DISCOUNT any model MoS on a name flagged peak/stale below. CRO-ONLY LEG: a name with <=2/5 positive model MoS AND a scan MoS below ~+10% (`scan_headline_mos_pct`) means your SoP is the SOLE evidence of cheapness — you may seat it, but you MUST set its `size_units` <= 0.5, tag it by name in the memo, and state in one sentence why your SoP beats five dissenting models.
2. CYCLICAL-PEAK vs DURABLE-GROWTH — apply BEFORE crediting any cheapness. `peak_flag`=true (eps_peak_ratio>=1.4 OR fcf_cagr_3y>=60%) means the latest earnings sit far above the multi-year base — you MUST distinguish two cases, because the flag fires on BOTH:
   (a) CYCLICAL PEAK / recovery artifact = peak_flag AND (`freshness_stale`=true [FY numerator > live TTM, or latest_q_eps_yoy<=-15%] OR weak/negative `revenue_cagr_3y` OR a commodity/cyclical end-market). Earnings are at a cycle high and ALREADY ROLLING OVER. NORMALIZE to mid-cycle (use `eps_normalized`, not `fy_eps`) and treat the headline multiple as FAKE-cheap. These are the BRBR/CALM artifacts (CALM eps_peak_ratio ~9 on the egg windfall; both rolling over). A low multiple on peak earnings is NOT value.
   (b) DURABLE GROWTH = peak_flag BUT `freshness_stale`=false (still growing, positive latest-Q YoY) AND durable positive `revenue_cagr_3y` AND healthy ROIC. The high ratio reflects a secular re-rate or a real turnaround (a brand compounding), NOT a cycle peak — do NOT normalize it away; credit it, but sanity-check the multiple vs true peers.
   In BOTH cases `sop_mos_pct` (the CRO's already-normalized fair value) is the ANCHOR: if the CRO normalized the name and STILL shows a positive MoS, the cheapness is real; if the CRO's MoS collapsed far below `scan_headline_mos_pct`, it was a peak artifact.
   (c) STALE ANCHOR: `freshness_stale`=true AND `eps_peak_ratio` >= ~1.8 AND the load-bearing catalyst already FIRED means the CRO fair value itself may be built on PRE-EVENT segments (pre-spin/pre-divestiture share count + EBITDA) — treat `sop_mos_pct` as PROVISIONAL, set `size_units` <= 0.5, and say so in the thesis (e.g. CMCSA post-Versant).
3. FUNDED-LEVERAGE SOLVENCY (this REPLACES raw Altman-Z, which uses total liabilities and over-penalizes float/reserve businesses). Judge solvency on FUNDED debt only — `net_funded_debt_ebitda` (net interest-bearing debt / EBITDA, so settlement/payroll float and policyholder reserves are structurally excluded) + `interest_coverage`; the `funded_solvency` field pre-buckets it. IGNORE raw `altman_z`.
   - `is_financial`=true (banks/insurers) OR `funded_solvency` in {exempt_financial, strong}: solvency is FINE — do NOT penalize. This clears EEFT/TNET (~0.8-1.6x funded, strong coverage), SCR.PA and the bank/insurer set on the RIGHT basis (their low Altman-Z was a float/reserve artifact), and any net-cash name.
   - REAL-funded-debt names (`funded_solvency` = moderate or weak): drop the Z number and near-VETO ONLY when the metrics are JOINTLY weak — high funded leverage (net_funded_debt_ebitda > ~3.5x) AND thin coverage (interest_coverage < ~3x) AND a near-term MATURITY WALL (check the name's dossier at backend/_opus_debate/dossiers/<SYM>.md for refinancing/maturity risk). ONE weak metric alone is NOT a veto: a 2-3x-levered name with healthy coverage and no wall is acceptable value — just note the leverage in the thesis. (Worked example: SAX.DE ~3.0x / 3.7x coverage = the book's most-levered name → keep only if the dossier shows no near maturity wall.)
   - `net_debt_exceeds_mktcap`=true remains a thin-equity flag — NEVER credit net debt as "net cash."
4. MULTIPLES vs TRUE PEERS (`peer_verdict`/`peer_relative_comps`) + GROWTH DURABILITY/QUALITY (durable positive revenue/EPS growth + ROIC>~8-10% SUPPORT value; negative 3yr revenue CAGR + sub-WACC ROIC + thin/eroding margins = a value trap even when optically cheap). When the peer entry carries `peer_override`/`anchor_multiple`, that is a LIVE, current peer multiple — use it, NEVER a remembered one (peer multiples de-rate). When `convergence`="sector_regulatory" (e.g. PLX.PA/Pluxee vs a now-~10x Edenred, both hit by the same Brazil PAT + Italy voucher reform), the discount-to-peer is SHARED-FACTOR SECTOR BETA, not idiosyncratic alpha: count it as a hidden-factor cluster in the correlation stress below, do NOT credit the gap as single-name edge, and prefer it as a sized/watch leg rather than a full-conviction apex seat.

ROTATION DISCIPLINE (continuity — you are ACCOUNTABLE TO YOUR OWN PRIOR CALLS): FIRST read backend/_opus_debate/_director_ledger_value.txt — it lists your currently-HELD names (entry date + why you picked each) and EVERY name you DROPPED in 2026. Treat this run as a ROTATION of last week's book, NOT a blank re-pick: (1) KEEP each held name UNLESS its thesis is BROKEN (price through thesis_break_px, a forensic/solvency flip, or confirmed moat terminal-erosion) OR you have a STRICTLY-BETTER orthogonal name for that seat — and say which. Re-grading a hair lower is NOT a reason to drop a held compounder. (2) You MAY RE-ADD a name you previously dropped, but ONLY by citing a DOCUMENTED THESIS CHANGE since the drop date (new filing/guidance, a materially lower price, a resolved overhang) — a merely-better grade is NOT a thesis change. You may override this, but you must OWN it in writing in whats_changed (do not exit a name only to re-add it days later with no new fact). (3) SECULAR-LOAD: this is a deep-value book, so it skews to structurally-challenged names — compute book_secular_load_pct = % of your apex carrying material/terminal secular_threat OR an ERODING moat; if it exceeds ~60% you MUST defend the whole-book decline beta in the memo (theme diversification does NOT remove the shared junk/flight-to-quality factor). Seat >=2 CLEAN ANCHORS (WIDE/NARROW moat + non-eroding trend + manageable/none threat, NTES-type) as ballast; if you cannot, justify it.

HARD CONSTRAINTS: <=3 names per sector. Every apex name must (a) clear forensic_gate, (b) survive cyclical-peak normalization with a STILL-POSITIVE normalized MoS, (c) be cheap on TRUE peers, (d) not be a value trap, (e) MATCH the moat terminal-erosion teeth in size: a `moat_erosion`="CAP" name (falling returns OR eroding margins + decelerating revenue) MUST carry `size_units` <= 0.5 (the deterministic post already half-caps it; your number must agree), and an `erosion_severity`="value-destroying" name (sub-cost-of-capital AND eroding — `roic_below_hurdle`=true) is apex-INELIGIBLE unless the skeptic CONFIRMS a durable moat. Use `moat`/`moat_trend`/`moat_score` as the moat read: a low multiple on a structurally-shrinking base (high-but-FALLING ROIC, eroding gross margin) is a value trap, NOT value — this is SEPARATE from the cyclical-peak gate (an earnings cycle high), which still applies.

HIDDEN-FACTOR CORRELATION STRESS (run over the final 10 BEFORE sizing — the <=3/sector cap is NOT a correlation control; GICS sectors miss shared real-world factors). Decompose the 10 on HIDDEN factors: (a) END-MARKET DEMAND CYCLE (consumer-discretionary / travel / housing), (b) REGULATORY or REIMBURSEMENT REGIME (e.g. US hospital Medicaid Directed-Payment-Program / a 2028 reimbursement ruling), (c) ADVERTISING CYCLE (cable & theme-park ad spend, out-of-home advertising), (d) RATE / CREDIT sensitivity, (e) a SINGLE shared macro (one commodity, one FX, one policy), (f) SECULAR-DISRUPTION THEME (each name carries a `secular_theme`: ai-displacement / payments-disintermediation / linear-media-decline / autonomous-mobility / labor-arbitrage-deflation / reimbursement-compression / retail-channel-shift / energy-transition-loser). NO secular_theme may carry >2 names — the live clusters to check are ai-displacement across ADBE/IT/GLOB and payments-disintermediation across EEFT/PLX.PA; "cheap vs peers" inside a cohort that is melting TOGETHER is sector beta, not alpha. A WIDE & non-eroding moat (e.g. ADBE: rising ROIC, expanding margin) counts at HALF toward the theme budget (a durable anchor that merely carries the narrative is not the tail risk), so a theme may seat one durable anchor + at most one eroding leg. FLAG every hidden factor carrying >=2 names. Known live clusters to check EXPLICITLY: THC+UHS (both ride the 2028 Medicaid-DPP / US hospital-reimbursement outcome); CMCSA+SAX.DE (both advertising-cycle — cable ads + theme-park spend, and out-of-home advertising); and any name whose peer entry is tagged `convergence`="sector_regulatory" (e.g. PLX.PA/Pluxee — its cheapness vs Edenred is shared Brazil-PAT/Italy-voucher REGULATORY beta, both names de-rated on the same factor, so it is sector beta NOT name-specific alpha and must be discounted here, not credited as edge). For each >=2 cluster, EITHER (i) DIVERSIFY: swap the lower-value leg for the best orthogonal eligible name / runner-up that does NOT re-cluster (note ARDT re-clusters with hospitals, SREN.SW with SCR.PA reinsurance), OR (ii) keep both ONLY with an explicit combined-size cap + written justification — no hidden factor may quietly carry two full-size legs. A single reimbursement ruling or an ad-recession must not hit two legs at once. Every keep-with-combined-size-cap resolution MUST appear in the output `combined_caps` as NUMBERS (not prose): combined_caps:[{names:[...], max_units(float), axis(str)}] — prose-only caps are a spec violation.

OUTPUT — Write VALID JSON to backend/_opus_debate/apex_basket_value.json = {apex_basket:[{symbol, sector, value_score(0-100), thesis(one sentence), mos_agreement(e.g. "4/5"), sop_mos_pct, net_funded_debt_ebitda, interest_coverage, funded_solvency, peer_verdict, growth_durability, peak_normalized(bool: did you have to discount peak/stale earnings), exposure_axes(list of the hidden factors this name carries, e.g. ["hospital-reimbursement","advertising-cycle"]), secular_theme(the name dominant secular-decline theme id from secular_themes.json or "" — used for the concentration cap), moat(WIDE|NARROW|ERODING|NONE), moat_score(int 0-100, from the input), size_units(float 0.1-1.5: 1.0=full unit, 0.5=half — the SAME sizing you justified in the memo; every CRO-only leg, stale anchor, moat_erosion="CAP" leg, and combined-cap member MUST carry its number here), thesis_break_px(number: the price at which the thesis is BROKEN, from your downside-to-break — below it the name exits at the next review), bear_fv_px(number: your adverse-SoP per-share value, used for the market stress test), entry_posture (one of: "enter_now_carry" | "scale_in" | "on_confirmation: <event>" | "wait_for_weakness" — WHEN a buyer steps in: a carry-paying compounder you enter now while the slow MoS re-rate plays out = enter_now_carry; a standard tranche-in = scale_in; a knife near the 52w low or a name to add only into a flush = wait_for_weakness; gated on a dated event = on_confirmation with that event), wheel (where a wheel SUITS this seat — a slow-re-rate income name you are happy to own at a discount, NOT an on_confirmation/event-risk name: {suits:true, csp_strike (your downside-to-break = thesis_break_px), cc_strike (the fair-value target where you cap upside once assigned), tenor_days (~30-45), rationale (one sentence: why selling the put pays you to wait for the re-rate)}; else {suits:false}), forensic_gate, trap_flag, decision('KEEP'|'ADD'|'RE-ADD' — vs the ledger), decision_rationale(one sentence reconciling this seat to the ledger), whats_changed(REQUIRED non-empty ONLY for RE-ADD: what materially changed since the drop; else "")}], runner_ups:[...~6], combined_caps:[{names:[...], max_units(float), axis(str)}], value_memo}. The value_memo MUST: (a) state the rubric weighting; (b) LIST the names EXCLUDED or CAPPED by the forensic gate and those down-rated as cyclical-peak/stale artifacts — call out BRBR and CALM EXPLICITLY with their CRO-normalized fair value vs the raw scan MoS; (c) give the name-by-name RISE/FALL vs the prior value apex (the caller specifies the prior apex in the run instruction; if none is given, read the existing backend/_opus_debate/apex_basket_value.json for the prior slate BEFORE you overwrite it); (d) a correlation_stress section naming EACH hidden-factor cluster of >=2 (INCLUDING the THC/UHS reimbursement and CMCSA/SAX.DE advertising pairs) AND each SECULAR-THEME cluster of >=2 (e.g. ai-displacement ADBE/IT/GLOB, payments-disintermediation EEFT/PLX.PA) and EXACTLY how you resolved it (diversified -> which swap and why; or kept-with-sizing -> the combined_caps entry with axis="secular-theme:<id>" and the justification, durable anchors counted at half); (e) a BEAR REBUTTAL subsection: ONE sentence per apex seat stating the STRONGEST reason that pick is wrong, written BEFORE final sizing — if you cannot articulate the bear in one sentence, you do not understand the position; (f) a ROTATION subsection reconciling to backend/_opus_debate/_director_ledger_value.txt — one line per KEEP/ADD/RE-ADD, the broken-thesis reason for every held name you DROPPED, and (for any RE-ADD) the documented thesis change; (g) a SECULAR-LOAD line: book_secular_load_pct + clean_anchor_count, with a defense if load>60% or anchors<2. ALSO emit, at top level alongside apex_basket, book_secular_load_pct(number) and clean_anchor_count(int). Reply exactly: DONE"""


# ── FUTURE RESOURCES Director rubric (spec §5, Phase 3) — Opus seat, AGENT_VOICE-prefixed like the
#    value/disruptor Directors. Valuation is a GUARD (CRO sop_mos_pct veto/cap, never the driver);
#    torque is SYMMETRIC (Do-NOT #7); the commodity-factor stress replaces the AI-capex stress. ──
FR_DIRECTOR_PROMPT = AGENT_VOICE + """You are the FUTURE RESOURCES DIRECTOR (Claude Opus 4.8), allocating REAL capital to LANE A of the Future Resources book — profitable producers, royalty/streamers and equipment toll-takers across six physical value chains (uranium fuel cycle, copper/electrification, rare earths & strategic metals, power-for-AI, robotics & physical AI, quantum) — with the catalyst regime overlay FULLY REMOVED (a live catalyst is neither a plus nor a requirement; Lane B owns catalysts) and with VALUATION AS A GUARD, NOT THE SCORE DRIVER. Read backend/_opus_debate/future_resources/fr_grade_input.json — one row per debated name, every field pre-computed. ALSO read FUTURE_RESOURCES_REGIME.md (repo root) — the per-chain cycle read; each row's `chain_regime` carries the machine-readable verdict per chain it rides.

SYSTEM OF RECORD (decisive — read FIRST). The multi-agent DEBATE already ran on each name. When the debate conflicts with the raw screen factors, THE DEBATE WINS:
  - `forensic_gate`: "EXCLUDE" => INELIGIBLE (interrogator credibility<=2 — mining is where promoters live; this gate is worth more here than in any other book). "CAP" => fr_score capped at ~50 (DETERIORATING trajectory: credible but worsening). A great cost-curve story NEVER overrides the forensic gate.
  - `sop_mos_pct` (the CRO's reconciled fair value vs price) is a GUARD input (pillar 4), not a ranking input: a deeply negative sop_mos_pct is a SIZE-CAP or VETO signal; a positive one is NOT extra score. Abnormal cheapness on a producer usually means the market is pricing the cost curve or the commodity leg against it — investigate, never bank it.
  - `physical_anchor` (from the chain map): every pick must have one — a name whose anchor line is empty or hand-wavy is a mapping error, not a seat (the anti-Visa rule, Do-NOT #11).

TORQUE IS SYMMETRIC (Do-NOT #7, enforced): `fcf_torque_10pct` is the % EBITDA swing per +/-10% commodity move — it cuts BOTH ways. Every seat whose thesis cites torque MUST carry the DOWNSIDE number in the same line (in `cost_curve` and in the memo's per-seat downside-torque list). A memo citing upside torque without the downside number is NON-CONFORMING: the run is rejected and re-run.

RUBRIC — four pillars ~25 pts each, applied ONLY to names that clear the gates:
1. COST-CURVE POSITION & TORQUE QUALITY — `ebitda_margin_ttm` + `ebitda_margin_band` (percentile within the chain cohort = the cost-curve-position proxy: highest margin at the same commodity price ~ lowest cost quartile), `fcf_torque_10pct` (SYMMETRIC — score torque QUALITY: torque from a low-cost position is compounding leverage, torque from a marginal high-cost position is a coin flip), `commodity_beta_2y` (the empirical cross-check: a "producer" with beta ~ 0 is hedged or mislabeled — reconcile before crediting torque; `beta_is_proxy`=true means an ETF regression, read it softer). The metrics are HONEST PROXIES (no AISC endpoint exists) — where the debate web-verified company-reported AISC/cost guidance and it DISAGREES with the proxy, the debate said so: trust the primary source and note it. Non-commodity chains (robotics_automation, quantum) score this pillar on `gm_trajectory` (the pricing-power lie detector: expanding GM on growing revenue = pricing power; compressing = commoditization), `rev_yoy`, `fcf_margin` — never on a pretended torque.
2. CONTRACTING CYCLE & RESERVE LIFE — from the debate: the contract book vs spot exposure (contracted volumes, realized-price mechanics), reserve/resource life with numbers, offtake counterparties (named, signed — an MoU is not a contract). Cross-read `chain_regime`: uranium term-contracting is the canonical cycle tell; a producer selling spot into a HEADWIND chain owns the downside torque with no cushion.
3. CAPITAL DISCIPLINE & BALANCE SHEET — the sector's besetting sin: capex history through the LAST cycle (did they build at the top?), buyback/dividend behavior at the top, `funded_solvency` (funded-debt basis; != weak is a hard gate) + `ndebt_ebitda` + `interest_coverage`. `growth_capex_fcf_negative`=true names (OCF-positive, FCF-negative mid-build) required the debate to verify the sustaining-vs-growth capex split — if it did not, treat the build as suspect.
4. GROWTH-ADJUSTED VALUATION GUARD — a GUARD, not a ranking pillar: full marks by default, DEDUCTIONS for danger. `sop_mos_pct` <= -40% => the CRO himself cannot get near the price: VETO or size_units <= 0.5 with explicit justification. `peak_flag`/`freshness_stale` on a commodity producer = the earnings sit on a price spike: normalize before crediting ANY cheapness (a low multiple on peak commodity earnings is the classic resources value trap). The guard can VETO or CAP; it must NEVER be the reason a name ranks above another that passed clean.

HARD CONSTRAINTS (the deterministic post layer re-checks every one — your numbers must agree):
  - EXACTLY 8 apex picks, ~5 runner_ups.
  - CHAIN CAPS: <=3 names per chain AND <=30% of basket weight per chain (by size_units share). A 2-chain name (UUUU-class) counts toward BOTH chains. State per-chain weights in chain_exposure.
  - `growth_capex_fcf_negative` => size_units <= 0.75 (the post clamps it deterministically).
  - HEADWIND chain (`chain_regime`) => size_units <= 0.5 OR a written `headwind_justification` naming the name-specific insulation (a contracted book, a bottom-quartile cost position bounding the downside). The post clamps any un-justified breach.
  - TORQUE x LEVERAGE QUADRANT: `fcf_torque_10pct` >= 0.5 AND `ndebt_ebitda` >= 2.5 is the blow-up quadrant => mandatory size_units <= 0.75, and if >=2 quadrant names sit in the basket, a combined_caps entry covering them (axis "torque-x-leverage").
  - Every pick clears forensic_gate, funded_solvency != weak, and carries a physical anchor.

COMMODITY-FACTOR STRESS (replaces the AI-capex stress; run over the final 8 BEFORE sizing): decompose EVERY run on the shared GLOBAL GROWTH + CHINA DEMAND axis — all four commodity/power chains ride it; a China demand shock or a global-growth downgrade hits copper, rare earths, power AND the industrial legs at once — then the chain-specific axes: uranium = ONE utility contracting cycle; power_for_ai = ONE hyperscaler PPA appetite; robotics = the industrial capex cycle; quantum + robotics TOGETHER = the long-duration-growth-multiple axis (rate-sensitive multiples compressing in sync — the axis the machine chains import into an otherwise commodity book). FLAG every axis carrying >=2 names. For each: EITHER (i) DIVERSIFY — swap the lower-scoring leg for the best orthogonal eligible runner-up that does NOT re-cluster, OR (ii) keep both ONLY with an explicit combined-size cap + written justification. Every keep-with-cap MUST appear in `combined_caps` as NUMBERS (not prose): combined_caps:[{names:[...], max_units(float), axis(str)}].

ROTATION DISCIPLINE: FIRST read backend/_opus_debate/_director_ledger_fr.txt (your currently-HELD names + every name you DROPPED this year; EMPTY on the maiden run — then every pick is an ADD and you say so). KEEP a held name UNLESS its thesis is BROKEN (price through thesis_break_px, a forensic/solvency flip, a cost-curve position lost, a chain tripwire breached) OR you have a STRICTLY-BETTER orthogonal name for that seat — say which. RE-ADD only on a DOCUMENTED THESIS CHANGE since the drop.

OUTPUT — Write VALID JSON to backend/_opus_debate/future_resources/apex_basket_fr.json = {apex_basket:[{symbol, sector, chains(all taxonomy ids), business_model, value_chain_position, physical_anchor(one line, from the chain map), fr_score(0-100), thesis(one sentence), cost_curve(one line WITH numbers: margin/band + the SYMMETRIC torque read including the downside number), contracting_reserve(one line: contract book + reserve life), capital_discipline(one line: last-cycle capex behavior + balance sheet), valuation_guard(one line, e.g. "sop_mos +18% — guard passes" or "sop_mos -45% — capped 0.5"), ebitda_margin_ttm, fcf_torque_10pct, commodity_beta_2y, ndebt_ebitda, interest_coverage, funded_solvency, sop_mos_pct, chain_regime(the sidecar verdict(s) this name rides, e.g. {"uranium_fuel_cycle":"TAILWIND"}), headwind_justification("" unless a HEADWIND-chain seat is sized > 0.5 — then the written name-specific insulation), growth_capex_fcf_negative(bool), torque_leverage_quadrant(bool), exposure_axes(list of the shared axes this name carries — include "global-growth-china-demand" wherever carried), size_units(float 0.1-1.5: 1.0=full unit; every capped name carries its clamped number HERE), thesis_break_px(number: the price at which the thesis is BROKEN — below it the name exits at the next review), bear_fv_px(number: your adverse-case per-share value assuming the chain regime turns against it — used for the market stress test), entry_posture(one of "enter_now_carry" | "scale_in" | "on_confirmation: <event>" | "wait_for_weakness"), wheel({suits:true, csp_strike(=thesis_break_px), cc_strike(the fair-value target), tenor_days(~30-45), rationale(one sentence)} | {suits:false} — usually false for a torque name whose upside you do not want to cap), forensic_gate, decision("KEEP"|"ADD"|"RE-ADD" vs the ledger), decision_rationale(one sentence), whats_changed(REQUIRED non-empty ONLY for RE-ADD; else "")}], runner_ups:[...~5], combined_caps:[{names:[...], max_units(float), axis(str)}], chain_exposure:{<chain_id>: weight_pct}, fr_memo}.
The fr_memo MUST: (a) state the rubric weighting and that valuation acted only as a guard; (b) LIST the names EXCLUDED or CAPPED by the forensic gate, the solvency gate, the valuation guard, and the HEADWIND rule — one-line reason each; (c) a PER-SEAT DOWNSIDE TORQUE list: one line per seat citing torque, with the DOWNSIDE number (a memo missing this list is non-conforming — reject and re-run, Do-NOT #7); (d) a commodity_factor_stress section naming EACH >=2-name axis (ALWAYS including the global-growth + China-demand decomposition, even if it carries <=1 name — say so) and EXACTLY how each was resolved (diversified -> which swap; or kept-with-cap -> the combined_caps numbers); (e) the name-by-name RISE/FALL vs the prior FR apex (read the existing backend/_opus_debate/future_resources/apex_basket_fr.json for the prior slate BEFORE you overwrite it; on the maiden run state that there is no prior); (f) a ROTATION subsection reconciling to backend/_opus_debate/_director_ledger_fr.txt — one line per KEEP/ADD/RE-ADD; (g) a BEAR REBUTTAL subsection: ONE sentence per apex seat stating the STRONGEST reason that pick is wrong, written BEFORE final sizing. Reply exactly: DONE"""


def value_input():
    """Build value_grade_input.json: per DEBATED name, the VALUE-rubric metrics PLUS the four
    robustness signal families the raw-MoS pillar was missing — (1) cyclical-peak/extrapolation
    (EPS-history peak ratio + FCF 3yr CAGR), (2) TTM-vs-FY freshness (stale numerator), (3) the
    forensic gate (interrogator credibility/trajectory + verdict), (4) the CRO sop_fair_value as the
    system-of-record MoS that overrides the raw scan MoS. Also writes value_director_prompt.txt so the
    value re-grade is one reproducible low-rate agent call."""
    import glob
    import re
    import statistics
    uni = {s["symbol"]: s for s in json.load(open(ROOT / "_radar_universe.json", encoding="utf-8"))}
    scan = gcs_io.gcs_read_json("scans/latest_global.json") or json.load(
        open("../frontend/public/latest_global.json", encoding="utf-8"))
    sc_by = {s.get("symbol"): s for s in scan.get("stocks", [])}
    res_files = sorted(glob.glob(str(ROOT / "results_regime" / "*.json")))
    fl = _funded_leverage([os.path.basename(f)[:-5] for f in res_files])
    out = []
    for f in res_files:
        try:
            r = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        sym = r.get("symbol") or os.path.basename(f)[:-5]
        u = uni.get(sym, {})
        s = sc_by.get(sym, {})
        pg = {}
        pgp = ROOT / "peer_groups" / f"{sym}.json"
        if pgp.exists():
            try:
                pg = json.load(open(pgp, encoding="utf-8"))
            except Exception:
                pg = {}
        ms = ""
        bp = ROOT / "inputs" / f"{sym}.json"
        if bp.exists():
            try:
                ms = json.load(open(bp, encoding="utf-8")).get("metrics_str", "")
            except Exception:
                ms = ""

        def _f(pat, cast=float):
            m = re.search(pat, ms)
            if not m:
                return None
            try:
                return cast(m.group(1))
            except Exception:
                return None

        ttm_note = (re.search(r'(TTM FCF[^\n]*)', ms) or [None])
        ttm_note = ttm_note.group(1).strip()[:160] if hasattr(ttm_note, "group") else ""
        ttm_eps = _f(r'TTM diluted EPS\s*(-?[0-9.]+)')
        lq_eps_yoy = _f(r'latest-Q EPS YoY\s*(-?[0-9.]+)%')
        scan_mos_head = _f(r'Margin of Safety\s*(-?[0-9.]+)%')
        fcf_cagr_3y = _f(r'FCF growth:[^\n]*3-yr CAGR\s*([+\-]?[0-9.]+)%')
        # EPS history (cyclical-peak) from the scan's buffett_history
        bh = (s.get("buffett_history") or {}).get("rows") or []
        eps_hist = [row.get("eps") for row in bh if isinstance(row.get("eps"), (int, float))]
        eps_latest = eps_hist[-1] if eps_hist else None
        eps_norm = eps_peak_ratio = None
        if len(eps_hist) >= 3:
            pos = [e for e in eps_hist[:-1] if e and e > 0]
            if pos:
                eps_norm = round(statistics.median(pos), 3)
                if eps_latest and eps_latest > 0 and eps_norm > 0:
                    eps_peak_ratio = round(eps_latest / eps_norm, 2)
        net_debt = s.get("net_debt")
        mktcap = s.get("market_cap")
        price = s.get("price") or u.get("price")
        net_debt_gt_mktcap = bool(isinstance(net_debt, (int, float)) and isinstance(mktcap, (int, float))
                                  and net_debt > 0 and net_debt > mktcap)
        sop_num = _val_money(r.get("sop_fair_value"))
        sop_mos = round((sop_num - price) / price * 100, 1) if (sop_num and isinstance(price, (int, float)) and price > 0) else None
        freshness_stale = False
        fresh_note = ""
        if isinstance(eps_latest, (int, float)) and isinstance(ttm_eps, (int, float)) and ttm_eps > 0 and eps_latest > ttm_eps * 1.15:
            freshness_stale = True
            fresh_note = f"FY EPS {eps_latest} vs live TTM {ttm_eps} (+{round((eps_latest/ttm_eps-1)*100)}%)"
        if isinstance(lq_eps_yoy, (int, float)) and lq_eps_yoy <= -15:
            freshness_stale = True
            fresh_note = (fresh_note + "; " if fresh_note else "") + f"latest-Q EPS YoY {lq_eps_yoy}%"
        peak_flag = bool((eps_peak_ratio and eps_peak_ratio >= 1.4)
                         or (isinstance(fcf_cagr_3y, (int, float)) and fcf_cagr_3y >= 60))
        iscore = r.get("interrogator_score")
        traj = (r.get("trajectory") or "").upper()
        verdict = (r.get("verdict") or "").upper()
        # Forensic gate = regime-INDEPENDENT veto (credibility + trajectory), NOT the verdict letter
        # (the A/B/C was set partly under the now-stripped catalyst regime). The verdict is surfaced
        # for the system-of-record reconciliation but is not a blanket cap.
        if isinstance(iscore, (int, float)) and iscore <= 2:
            gate = "EXCLUDE"            # credibility veto — a forensic red flag the factors miss
        elif iscore is None:
            # 8f: a malformed/missing CREDIBILITY_SCORE must NOT fail open as neutral —
            # cap it (fail toward caution) and say so, without nuking the name on a transient.
            gate = "CAP"
            print(f"WARN: {sym} interrogator_score missing/unparseable -> gate=CAP (fail-closed)")
        elif "DETERIORAT" in traj:
            gate = "CAP"               # deteriorating but credible -> mid-tier cap, not a veto
        else:
            gate = ""
        mos = {k: round(u[k], 3) for k in ("dcf_fcff_mos", "epv_mos", "graham_revised_mos",
                                           "owner_earnings_mos", "iv15_deep_value_mos")
               if isinstance(u.get(k), (int, float))}
        flv = fl.get(sym, {})
        ndE = flv.get("net_funded_debt_ebitda")
        icov = flv.get("interest_coverage")
        is_fin = "financ" in (r.get("sector", "") or "").lower()
        funded_solv = _funded_solvency(r.get("sector", ""), ndE, icov)
        mf = _moat_features(u, s, r)
        out.append({
            "symbol": sym, "sector": r.get("sector", ""),
            "mos_spread": mos, "altman_z": u.get("altman_z"), "p_fcf": u.get("p_fcf"),
            "revenue_yoy": u.get("revenue_yoy"), "revenue_cagr_3y": u.get("revenue_cagr_3y"),
            "eps_yoy": u.get("eps_yoy"), "roic_avg": u.get("roic_avg"),
            "net_margin": u.get("net_margin"), "gross_margin": u.get("gross_margin"),
            "peer_verdict": pg.get("verdict", ""),
            "peer_relative_comps": (pg.get("relative_comps", "") or "")[:400],
            # system of record: CRO fair value + debate forensics override the raw scan MoS
            "sop_fair_value": r.get("sop_fair_value", ""), "sop_mos_pct": sop_mos,
            "price": price, "scan_headline_mos_pct": scan_mos_head,
            "risk_reward": (r.get("risk_reward", "") or "")[:220],
            "debate_verdict": verdict, "debate_conviction": r.get("conviction"),
            # 8a: value_conviction = the CRO's catalyst-blind value score (decoupled from the
            # regime-tilted `conviction`); older results lack it -> None, Director falls back.
            "value_conviction": r.get("value_conviction"),
            "interrogator_score": iscore, "trajectory": r.get("trajectory", ""),
            "forensic_gate": gate,
            # cyclical-peak / extrapolation normalization (ahead of trusting MoS)
            "eps_history": eps_hist[-5:], "eps_normalized": eps_norm, "eps_peak_ratio": eps_peak_ratio,
            "fcf_cagr_3y": fcf_cagr_3y, "peak_flag": peak_flag,
            # TTM-vs-FY freshness (stale numerator)
            "ttm_note": ttm_note, "ttm_eps": ttm_eps, "fy_eps": eps_latest,
            "latest_q_eps_yoy": lq_eps_yoy, "freshness_stale": freshness_stale, "freshness_note": fresh_note,
            # solvency: funded-leverage (interest-bearing debt only; float/reserves netted out) replaces raw Altman-Z
            "net_funded_debt_ebitda": round(ndE, 2) if isinstance(ndE, (int, float)) else None,
            "interest_coverage": round(icov, 1) if isinstance(icov, (int, float)) else None,
            "is_financial": is_fin, "funded_solvency": funded_solv,
            # leverage (BRBR net-debt-not-net-cash)
            "net_debt": net_debt, "market_cap": mktcap, "net_debt_exceeds_mktcap": net_debt_gt_mktcap,
            # moat durability / terminal-erosion (deterministic, ADDITIVE to peak/stale gates) —
            # moat_erosion="CAP" => 0.5 size cap in post; erosion_severity drives the skeptic kill-tier
            "moat_score": mf["moat_score"], "moat_erosion": mf["moat_erosion"],
            "erosion_severity": mf["erosion_severity"], "roic_below_hurdle": mf["roic_below_hurdle"],
            "returns_trend": mf["returns_trend"], "net_margin_trend": mf["net_margin_trend"],
            "gross_margin_trend": mf["gross_margin_trend"], "revenue_trend": mf["revenue_trend"],
            "revenue_decelerating": mf["revenue_decelerating"],
            # agent-judged moat read (from the debate dossier/CRO) — cross-checks the deterministic gate
            "moat": r.get("moat", ""), "moat_trend": r.get("moat_trend", ""),
            # X5 carry-awareness: the value re-grade must SEE a carried (not re-debated) record —
            # its numbers date from carried_from, restamped only for price/as_of.
            "carried": bool(r.get("carried")), "carried_from": r.get("carried_from", ""),
            "secular_threat": r.get("secular_threat", ""), "secular_theme": r.get("secular_theme", ""),
        })
    # Freshness stamp (the proven lesson from the weekly TTM "as of" block, applied to the one path
    # that lacked it): every row carries as_of so the Director can never lean on an undated figure.
    _asof = datetime.now().strftime("%Y-%m-%d")
    for x in out:
        x["as_of"] = _asof
    (ROOT / "value_grade_input.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    # Director rotation discipline: render the prior-decision ledger (held names + 2026 drops) that
    # this Director must reconcile its new basket against. Best-effort — never blocks the run.
    try:
        write_director_ledger("value", ROOT / "apex_basket_value.json", E.FRONTEND_DIR / "public" / "speculair_value_tracking.json")
    except Exception as _e:
        print(f"WARN: value ledger build failed ({_e})")
    prompt_txt = f"AS OF {_asof} — every metric row in value_grade_input.json carries this date.\n\n" + VALUE_DIRECTOR_PROMPT
    pa = ROOT / "apex_basket_value.json"                # Fix 4 feed-forward: prior MEASURED correlations
    if pa.exists():
        try:
            pc = json.load(open(pa, encoding="utf-8")).get("correlation") or {}
            if pc.get("avg_pairwise") is not None:
                fl = pc.get("flagged_pairs") or []
                lines = [f"  {f['a']}-{f['b']}: {f['corr']}" + (" [BREACH]" if f.get("breach") else "") for f in fl[:12]]
                prompt_txt += ("\n\nPRIOR-RUN MEASURED CORRELATIONS (2y weekly log returns; argue your hidden-factor "
                               f"stress AGAINST these real numbers, do not merely assert 'barely co-move'). "
                               f"avg pairwise={pc.get('avg_pairwise')}, max={pc.get('max_pair')}. Pairs >=0.6:\n"
                               + ("\n".join(lines) if lines else "  (none >=0.6 last run)"))
        except Exception:
            pass
    (ROOT / "value_director_prompt.txt").write_text(prompt_txt, encoding="utf-8")
    npeak = sum(1 for x in out if x["peak_flag"])
    ngate = sum(1 for x in out if x["forensic_gate"])
    nstale = sum(1 for x in out if x["freshness_stale"])
    from collections import Counter as _C
    fs = _C(x["funded_solvency"] for x in out)
    print(f"value_grade_input.json: {len(out)} names | peak_flag={npeak} forensic_gate={ngate} freshness_stale={nstale}")
    print(f"  funded_solvency: {dict(fs)}")

    # ── 11a — weekly FUNNEL-QUALITY stats: is the scan's headline MoS a ranking signal or only a
    # membership filter? (Measured 2026-06-10: Spearman 0.41 overall but 0.15 in the scan top
    # quintile; 61% of scan-positive names cut >50% by the CRO — magnitude carries no in-funnel
    # ranking signal. These make that measurable EVERY week.) Pure-python Spearman, no scipy.
    def _spearman(pairs):
        if len(pairs) < 10:
            return None
        import statistics as _st

        def _ranks(vals):
            order = sorted(range(len(vals)), key=lambda i: vals[i])
            rk = [0.0] * len(vals)
            i = 0
            while i < len(order):
                j = i
                while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                    j += 1
                avg = (i + j) / 2 + 1
                for k in range(i, j + 1):
                    rk[order[k]] = avg
                i = j + 1
            return rk
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        try:
            return round(_st.correlation(_ranks(xs), _ranks(ys)), 3)
        except Exception:
            return None

    both = [(x["scan_headline_mos_pct"], x["sop_mos_pct"]) for x in out
            if isinstance(x.get("scan_headline_mos_pct"), (int, float)) and isinstance(x.get("sop_mos_pct"), (int, float))]
    sp_all = _spearman(both)
    topq = sorted(both, key=lambda p: -p[0])[:max(5, len(both) // 5)]
    sp_topq = _spearman(topq)
    pos = [p for p in both if p[0] > 0]
    collapse = sum(1 for p in pos if p[1] < p[0] * 0.5)
    artifact = sum(1 for p in pos if p[1] <= 0)
    rescues = [x["symbol"] for x in out
               if isinstance(x.get("scan_headline_mos_pct"), (int, float)) and isinstance(x.get("sop_mos_pct"), (int, float))
               and x["scan_headline_mos_pct"] <= 10 and x["sop_mos_pct"] >= 30]
    funnel_stats = {"n_both": len(both), "spearman_scan_vs_cro": sp_all, "spearman_top_quintile": sp_topq,
                    "collapse_rate_50": round(collapse / len(pos), 3) if pos else None,
                    "artifact_rate": round(artifact / len(pos), 3) if pos else None,
                    "cross_lens_rescues": {"n": len(rescues), "symbols": sorted(rescues)},
                    "note": "scan MoS = membership/divergence signal only; never a rank or weight"}
    (ROOT / "_funnel_stats.json").write_text(json.dumps(funnel_stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  funnel: spearman={sp_all} (top-quintile {sp_topq}) collapse>50%={funnel_stats['collapse_rate_50']} "
          f"artifact={funnel_stats['artifact_rate']} rescues={len(rescues)} {sorted(rescues)}")

    # ── 11c — FORENSIC LEDGER: persist EXCLUDE gates so prep() can route unexpired ones to a short
    # re-check instead of a full debate. A ledger_recheck re-affirmation does NOT extend the clock —
    # only a FULL debate that again scores <=2 restarts the 8-week TTL.
    from datetime import datetime as _dtt, timedelta as _td
    led_p = ROOT / "forensic_ledger.json"
    led = {}
    if led_p.exists():
        try:
            led = json.load(open(led_p, encoding="utf-8"))
        except Exception:
            led = {}
    today_s = _dtt.now().strftime("%Y-%m-%d")
    for x in out:
        if x["forensic_gate"] != "EXCLUDE":
            continue
        sym = x["symbol"]
        src = ""
        rf = ROOT / "results_regime" / f"{sym}.json"
        if rf.exists():
            try:
                src = json.load(open(rf, encoding="utf-8")).get("source", "")
            except Exception:
                src = ""
        if sym in led and src == "ledger_recheck":
            continue                                       # re-affirmation: keep the original clock
        led[sym] = {"gate": "EXCLUDE", "date": today_s,
                    "reason": f"interrogator credibility {x.get('interrogator_score')} | {x.get('trajectory', '')}",
                    "expires": (_dtt.now() + _td(days=56)).strftime("%Y-%m-%d"),
                    "days_to_earnings": (sc_by.get(sym) or {}).get("days_to_earnings")}
    led = {s: e for s, e in led.items() if (e.get("expires") or "") >= today_s}   # prune expired
    led_p.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  forensic ledger: {len(led)} unexpired EXCLUDE entr{'y' if len(led) == 1 else 'ies'} -> {led_p.name}")
    print(f"value_director_prompt.txt written ({len(VALUE_DIRECTOR_PROMPT)} chars)")
    return len(out)


def value_csv():
    """CSV of the VALUE apex (apex_basket_value.json) with the FULL output of every agent per name —
    Radar / Interrogator / Architect / Catalyst / CRO + the value-Director's per-name grade — plus the
    value_memo companion. Rows ordered by value_score desc; in_regime_apex flags cross-lens overlap."""
    import csv
    apex = json.load(open(ROOT / "apex_basket_value.json", encoding="utf-8"))
    picks = [p for p in apex.get("apex_basket", []) if isinstance(p, dict) and p.get("symbol")]
    regime = set()
    rapx = ROOT / "apex_basket_opus_regime.json"
    if rapx.exists():
        try:
            regime = {p.get("symbol") for p in json.load(open(rapx, encoding="utf-8")).get("apex_basket", []) if isinstance(p, dict)}
        except Exception:
            regime = set()
    gin = {}
    if (ROOT / "value_grade_input.json").exists():
        try:
            gin = {x["symbol"]: x for x in json.load(open(ROOT / "value_grade_input.json", encoding="utf-8"))}
        except Exception:
            gin = {}
    cols = ["rank", "symbol", "sector", "value_score", "in_regime_apex", "value_thesis", "mos_agreement",
            "altman_z", "net_funded_debt_ebitda", "interest_coverage", "funded_solvency",
            "sop_mos_pct", "scan_headline_mos_pct", "forensic_gate", "peak_normalized",
            "peak_flag", "eps_peak_ratio", "freshness_stale", "peer_verdict_director", "growth_durability", "exposure_axes",
            "size_units_effective", "weight_pct", "mos_agreement_n", "cro_only", "stale_anchor", "corr_flag", "entry_plan", "trap_flag",
            "debate_verdict", "debate_conviction", "catalyst_status", "sop_fair_value", "sop_breakdown",
            "risk_reward", "peer_comps_note", "radar_peers", "radar_relative_comps", "radar_verdict",
            "radar_rationale", "bull_thesis", "bear_thesis", "sop_bull", "sop_bear", "consensus_delta",
            "valley_of_death", "positioning_washout", "forcing_function", "moderator_conclusion",
            "interrogator_score", "trajectory", "interrogator_dossier"]
    rows = []
    for rank, p in enumerate(sorted(picks, key=lambda x: -(x.get("value_score") or 0)), 1):
        sym = p["symbol"]
        r = {}
        if (ROOT / "results_regime" / f"{sym}.json").exists():
            try:
                r = json.load(open(ROOT / "results_regime" / f"{sym}.json", encoding="utf-8"))
            except Exception:
                r = {}
        doss = ""
        if (ROOT / "dossiers" / f"{sym}.md").exists():
            doss = (ROOT / "dossiers" / f"{sym}.md").read_text(encoding="utf-8")
        pg = {}
        if (ROOT / "peer_groups" / f"{sym}.json").exists():
            try:
                pg = json.load(open(ROOT / "peer_groups" / f"{sym}.json", encoding="utf-8"))
            except Exception:
                pg = {}
        rows.append({
            "rank": rank, "symbol": sym, "sector": p.get("sector", ""), "value_score": p.get("value_score", ""),
            "in_regime_apex": sym in regime, "value_thesis": p.get("thesis", "") or p.get("value_thesis", ""),
            "mos_agreement": p.get("mos_agreement", ""), "altman_z": p.get("altman_z", ""),
            "net_funded_debt_ebitda": p.get("net_funded_debt_ebitda", gin.get(sym, {}).get("net_funded_debt_ebitda", "")),
            "interest_coverage": p.get("interest_coverage", gin.get(sym, {}).get("interest_coverage", "")),
            "funded_solvency": p.get("funded_solvency", gin.get(sym, {}).get("funded_solvency", "")),
            "sop_mos_pct": p.get("sop_mos_pct", gin.get(sym, {}).get("sop_mos_pct", "")),
            "scan_headline_mos_pct": gin.get(sym, {}).get("scan_headline_mos_pct", ""),
            "forensic_gate": p.get("forensic_gate", gin.get(sym, {}).get("forensic_gate", "")),
            "peak_normalized": p.get("peak_normalized", ""),
            "peak_flag": gin.get(sym, {}).get("peak_flag", ""),
            "eps_peak_ratio": gin.get(sym, {}).get("eps_peak_ratio", ""),
            "freshness_stale": gin.get(sym, {}).get("freshness_stale", ""),
            "peer_verdict_director": p.get("peer_verdict", ""), "growth_durability": p.get("growth_durability", ""),
            "exposure_axes": "; ".join(p["exposure_axes"]) if isinstance(p.get("exposure_axes"), list) else (p.get("exposure_axes", "") or ""),
            "size_units_effective": p.get("size_units_effective", ""), "weight_pct": p.get("weight_pct", ""),
            "mos_agreement_n": p.get("mos_agreement_n", ""), "cro_only": p.get("cro_only", ""),
            "stale_anchor": p.get("stale_anchor", ""), "corr_flag": p.get("corr_flag", ""),
            "entry_plan": p.get("entry_plan", ""),
            "trap_flag": p.get("trap_flag", ""),
            "debate_verdict": r.get("verdict", ""), "debate_conviction": r.get("conviction", ""),
            "catalyst_status": r.get("catalyst_status", ""), "sop_fair_value": r.get("sop_fair_value", ""),
            "sop_breakdown": r.get("sop_breakdown", ""), "risk_reward": r.get("risk_reward", ""),
            "peer_comps_note": r.get("peer_comps_note", ""),
            "radar_peers": ", ".join(pg.get("peers", [])) if isinstance(pg.get("peers"), list) else "",
            "radar_relative_comps": pg.get("relative_comps", ""), "radar_verdict": pg.get("verdict", ""),
            "radar_rationale": pg.get("rationale", ""), "bull_thesis": r.get("bull_thesis", ""),
            "bear_thesis": r.get("bear_thesis", ""), "sop_bull": r.get("sop_bull", ""), "sop_bear": r.get("sop_bear", ""),
            "consensus_delta": r.get("consensus_delta", ""), "valley_of_death": r.get("valley_of_death", ""),
            "positioning_washout": r.get("positioning_washout", ""), "forcing_function": r.get("forcing_function", ""),
            "moderator_conclusion": r.get("moderator_conclusion", ""), "interrogator_score": r.get("interrogator_score", ""),
            "trajectory": r.get("trajectory", ""), "interrogator_dossier": doss,
        })
    out = ROOT / "speculair_value_apex.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    mm = apex.get("value_memo", "")
    (ROOT / "speculair_value_apex_memo.txt").write_text(
        mm if isinstance(mm, str) else json.dumps(mm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(rows)} value-apex rows x {len(cols)} cols -> {out}")
    print(f"value_memo -> {ROOT / 'speculair_value_apex_memo.txt'}")
    return len(rows)


def baskets_csv():
    """One CSV joining BASKET MEMBERSHIP (regime apex/runner, value apex/runner, and the 11
    per-methodology baskets) with the FULL debate output (every agent) for ALL debated names —
    'all baskets + all debates' in a single file. Companion to the apex-specific CSVs."""
    import csv
    res_dir, doss_dir, pg_dir = ROOT / "results_regime", ROOT / "dossiers", ROOT / "peer_groups"

    def _roles(path):
        d = {}
        j = json.load(open(ROOT / path, encoding="utf-8")) if (ROOT / path).exists() else {}
        for p in j.get("apex_basket", []):
            if isinstance(p, dict) and p.get("symbol"):
                d[p["symbol"]] = {**p, "_role": "APEX"}
        for p in j.get("runner_ups", []):
            s = p.get("symbol") if isinstance(p, dict) else p
            if s and s not in d:
                d[s] = ({**p} if isinstance(p, dict) else {"symbol": s})
                d[s]["_role"] = "RUNNER_UP"
        return d

    reg = _roles("apex_basket_opus_regime.json")
    val = _roles("apex_basket_value.json")
    gin = {}
    if (ROOT / "value_grade_input.json").exists():
        try:
            gin = {x["symbol"]: x for x in json.load(open(ROOT / "value_grade_input.json", encoding="utf-8"))}
        except Exception:
            gin = {}
    meth_of = {}
    try:
        sb = json.load(open("../frontend/public/speculair_baskets.json", encoding="utf-8"))
        for meth, basket in (sb.get("per_methodology_baskets") or {}).items():
            picks = basket.get("picks") if isinstance(basket, dict) else basket
            for pk in (picks or []):
                s = pk.get("symbol") if isinstance(pk, dict) else pk
                if s:
                    meth_of.setdefault(s, []).append(meth)
    except Exception as e:
        print(f"WARN: per_methodology basket map failed ({e})")
    cols = ["symbol", "sector", "signal_type",
            "regime_role", "regime_director_conviction", "regime_lane", "regime_catalyst_status", "regime_forensic_cap", "regime_director_thesis",
            "value_role", "value_score", "value_thesis", "funded_solvency", "net_funded_debt_ebitda", "interest_coverage",
            "sop_mos_pct", "scan_headline_mos_pct", "forensic_gate", "peak_flag", "freshness_stale", "trap_flag",
            "n_methodology_baskets", "methodology_baskets",
            "verdict", "conviction", "catalyst_status", "sop_fair_value", "risk_reward", "trajectory", "interrogator_score",
            "radar_verdict", "radar_peers", "radar_relative_comps", "radar_rationale",
            "bull_thesis", "bear_thesis", "sop_bull", "sop_bear", "sop_breakdown",
            "consensus_delta", "valley_of_death", "positioning_washout", "forcing_function", "moderator_conclusion",
            "peer_comps_note", "interrogator_dossier"]
    rows = []
    for f in sorted(res_dir.glob("*.json")):
        try:
            r = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        sym = r.get("symbol") or f.stem
        rg, vl, gi = reg.get(sym, {}), val.get(sym, {}), gin.get(sym, {})
        doss = (doss_dir / f"{sym}.md").read_text(encoding="utf-8") if (doss_dir / f"{sym}.md").exists() else ""
        pg = {}
        if (pg_dir / f"{sym}.json").exists():
            try:
                pg = json.load(open(pg_dir / f"{sym}.json", encoding="utf-8"))
            except Exception:
                pg = {}
        mb = meth_of.get(sym, [])
        rows.append({
            "symbol": sym, "sector": r.get("sector", ""), "signal_type": r.get("signal_type", ""),
            "regime_role": rg.get("_role", ""), "regime_director_conviction": rg.get("director_conviction", ""),
            "regime_lane": rg.get("lane", ""), "regime_catalyst_status": rg.get("catalyst_status", r.get("catalyst_status", "")),
            "regime_forensic_cap": rg.get("forensic_cap", ""),
            "regime_director_thesis": rg.get("thesis", ""),
            "value_role": vl.get("_role", ""), "value_score": vl.get("value_score", ""), "value_thesis": vl.get("thesis", ""),
            "funded_solvency": gi.get("funded_solvency", ""), "net_funded_debt_ebitda": gi.get("net_funded_debt_ebitda", ""),
            "interest_coverage": gi.get("interest_coverage", ""), "sop_mos_pct": gi.get("sop_mos_pct", ""),
            "scan_headline_mos_pct": gi.get("scan_headline_mos_pct", ""), "forensic_gate": gi.get("forensic_gate", ""),
            "peak_flag": gi.get("peak_flag", ""), "freshness_stale": gi.get("freshness_stale", ""),
            "trap_flag": vl.get("trap_flag", ""),
            "n_methodology_baskets": len(mb), "methodology_baskets": ";".join(mb),
            "verdict": r.get("verdict", ""), "conviction": r.get("conviction", ""), "catalyst_status": r.get("catalyst_status", ""),
            "sop_fair_value": r.get("sop_fair_value", ""), "risk_reward": r.get("risk_reward", ""),
            "trajectory": r.get("trajectory", ""), "interrogator_score": r.get("interrogator_score", ""),
            "radar_verdict": pg.get("verdict", ""),
            "radar_peers": ", ".join(pg.get("peers", [])) if isinstance(pg.get("peers"), list) else "",
            "radar_relative_comps": pg.get("relative_comps", ""), "radar_rationale": pg.get("rationale", ""),
            "bull_thesis": r.get("bull_thesis", ""), "bear_thesis": r.get("bear_thesis", ""),
            "sop_bull": r.get("sop_bull", ""), "sop_bear": r.get("sop_bear", ""), "sop_breakdown": r.get("sop_breakdown", ""),
            "consensus_delta": r.get("consensus_delta", ""), "valley_of_death": r.get("valley_of_death", ""),
            "positioning_washout": r.get("positioning_washout", ""), "forcing_function": r.get("forcing_function", ""),
            "moderator_conclusion": r.get("moderator_conclusion", ""), "peer_comps_note": r.get("peer_comps_note", ""),
            "interrogator_dossier": doss,
        })
    role_rank = {"APEX": 0, "RUNNER_UP": 1, "": 2}
    rows.sort(key=lambda x: (role_rank.get(x["regime_role"], 2), role_rank.get(x["value_role"], 2),
                             -x["n_methodology_baskets"], x["symbol"]))
    out = ROOT / "speculair_baskets_debates.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    n_reg = sum(1 for x in rows if x["regime_role"])
    n_val = sum(1 for x in rows if x["value_role"])
    n_meth = sum(1 for x in rows if x["n_methodology_baskets"])
    print(f"wrote {len(rows)} rows x {len(cols)} cols -> {out}")
    print(f"  basket coverage: regime-tagged={n_reg} value-tagged={n_val} in>=1 methodology basket={n_meth}")
    return len(rows)


def value_publish(push_gcs=False):
    """Stage the public Value Lens payload (frontend/public/speculair_value_apex.json) AND maintain a
    live-forward NAV track record for the value book — a separate chained-NAV state file
    (speculair_value_tracking.json) from the apex, via the same _update_apex_tracking engine."""
    import datetime as _dt
    PUB = E.FRONTEND_DIR / "public"
    apx = json.load(open(ROOT / "apex_basket_value.json", encoding="utf-8"))
    # PUBLISH GATE (mirror of publish_to_frontend's): the 06-30 value book shipped with its largest
    # seat un-vetted + a stale-REFUTED name seated because publish ran without the post layer.
    if not apx.get("value_post_applied") and "--force" not in sys.argv:
        print("GUARD value publish gate: apex_basket_value.json has NO value_post_applied stamp — run "
              "`value-skeptic` (Workflow) then `value-post` first. Aborting (override: --force).")
        sys.exit(1)
    picks = [p for p in apx.get("apex_basket", []) if isinstance(p, dict) and p.get("symbol")]
    try:                                              # capture this run's Director decisions into the year ledger
        append_decision_history("value", apx)
    except Exception as _e:
        print(f"WARN: value decision-history capture failed ({_e})")
    track_in = [{**p, "conviction": p.get("value_score", 0)} for p in picks]   # value_score -> conviction log
    try:
        vt = E._update_apex_tracking(track_in, push_gcs=False,
                                     gcs_path="scans/speculair_value_tracking.json",
                                     local_name="speculair_value_tracking.json")
    except Exception as e:
        print(f"WARN: value tracking failed ({e})")
        vt = {}
    weights = apx.get("weights")                       # fix 5e: parallel WEIGHTED NAV (separate state file)
    vtw = {}
    if weights:
        try:
            vtw = E._update_apex_tracking(track_in, push_gcs=False, weights=weights,
                                          gcs_path="scans/speculair_value_tracking_weighted.json",
                                          local_name="speculair_value_tracking_weighted.json")
        except Exception as e:
            print(f"WARN: weighted value tracking failed ({e})")
    pos = {}
    tp = PUB / "speculair_value_tracking.json"
    if tp.exists():
        try:
            pos = json.load(open(tp, encoding="utf-8")).get("positions", {})
        except Exception:
            pos = {}
    for p in picks:                                   # attach entry for per-pick perf in the card
        pp = pos.get(p["symbol"], {})
        if pp:
            p["entry_price"] = pp.get("entry_price")
            p["entry_date"] = pp.get("entry_date")
    pool_stats = {}                                    # fix 6: honest pool-quality banner
    gp = ROOT / "value_grade_input.json"
    if gp.exists():
        try:
            from collections import Counter as _C
            gin = json.load(open(gp, encoding="utf-8"))
            vc = _C((x.get("debate_verdict") or "?") for x in gin)
            na = vc.get("A", 0)
            gin_by = {x.get("symbol"): x for x in gin}
            apex_verdicts = {(gin_by.get(p["symbol"]) or {}).get("debate_verdict") for p in picks}
            pool_stats = {"n_pool": len(gin), "verdict_counts": dict(vc), "n_verdict_a": na,
                          "apex_all_verdict_b": apex_verdicts == {"B"},
                          "banner": (f"Best-of-B basket: {na} verdict-A names in a {len(gin)}-name pool — "
                                     f"every apex pick is a verdict-B value name. Expect SLOW gap-closure: "
                                     f"margin-of-safety re-rating, no hard catalysts by design.")}
            fst = ROOT / "_funnel_stats.json"
            if fst.exists():
                try:
                    pool_stats["funnel"] = json.load(open(fst, encoding="utf-8"))   # 11a weekly stats
                except Exception:
                    pass
        except Exception:
            pool_stats = {}
    out = {"apex_basket": picks, "runner_ups": apx.get("runner_ups", []),
           "value_memo": apx.get("value_memo", ""), "value_tracking": vt,
           "value_tracking_weighted": vtw, "weights": weights,
           "stress_test": apx.get("stress_test"), "correlation": apx.get("correlation"),
           "exits": apx.get("exits"), "combined_caps": apx.get("combined_caps"),
           # rotation discipline: the Director's book-level secular-decline load + clean-anchor count (UI gauge)
           "book_secular_load_pct": apx.get("book_secular_load_pct"), "clean_anchor_count": apx.get("clean_anchor_count"),
           "pool_stats": pool_stats,
           "generated_at": _dt.date.today().isoformat(),
           "engine": "opus-4.8-value-funded-leverage", "rubric_version": "2026-07-vd1",
           "universe": (pool_stats or {}).get("n_pool")}
    (PUB / "speculair_value_apex.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"value_publish: {len(picks)} apex + {len(out['runner_ups'])} runners | tracking nav={vt.get('nav')} "
          f"since={vt.get('since_inception_pct')}% open={vt.get('n_open')} closed={vt.get('n_closed')} inception={vt.get('inception_date')}")
    if push_gcs:
        import subprocess
        for localf, key in [(PUB / "speculair_value_apex.json", "scans/speculair_value_apex.json"),
                            (PUB / "speculair_value_tracking.json", "scans/speculair_value_tracking.json"),
                            (PUB / "speculair_value_tracking_weighted.json", "scans/speculair_value_tracking_weighted.json")]:
            try:
                # shell=True so Windows resolves gcloud.cmd (and Linux/Cloud Run still works)
                r = subprocess.run(f'gcloud storage cp "{localf}" "gs://screener-signals-carbonbridge/{key}"',
                                   shell=True, capture_output=True, text=True, timeout=120)
                print(f"  GCS push {key}: {'OK' if r.returncode == 0 else 'FAILED ' + (r.stderr or '')[-140:]}")
            except Exception as e:
                print(f"  GCS push {key} ERR: {e}")
    return len(picks)


def finish_debate():
    """Emit _finish_debate.js: debate ONLY the not-yet-done names (universe minus results_regime),
    reusing the already-built bundles/peer_groups (Radar skipped), batched to dodge the rate limit,
    then the Director over ALL results. For completing a run a transient outage left partial."""
    import glob
    import re
    uni = [s["symbol"] for s in json.load(open(ROOT / "_radar_universe.json", encoding="utf-8"))]
    done = {os.path.basename(f)[:-5] for f in glob.glob(str(ROOT / "results_regime" / "*.json"))}
    missing = [s for s in uni if s not in done]
    fmp = [s for s in missing if (ROOT / "transcripts" / f"{s}.txt").exists()]
    online = [s for s in missing if not (ROOT / "transcripts" / f"{s}.txt").exists()]
    js = (ROOT / "_weekly_debate.js").read_text(encoding="utf-8")
    js = re.sub(r"const SYMS = \[[^\]]*\]", "const SYMS = " + json.dumps(fmp), js)
    js = re.sub(r"const ONLINE_SYMS = \[[^\]]*\]", "const ONLINE_SYMS = " + json.dumps(online), js)
    out = ROOT / "_finish_debate.js"
    out.write_text(js, encoding="utf-8", newline="\n")
    print(f"FINISH OK: {len(fmp)} FMP + {len(online)} online = {len(missing)} still-missing (of {len(uni)})")
    print(f"FINISH_SCRIPT={out.resolve()}")
    return len(missing)


def value_revalidate():
    """Fix 3 (revalidation half): emit _revalidate_debate.js to re-debate ONLY the stale-anchor
    value-apex names (stamped by _value_post: freshness_stale + eps_peak_ratio>=1.8 + catalyst FIRED)
    on POST-EVENT PRO-FORMA segments. Forces them through the ONLINE path so the agent web-fetches the
    post-spin/post-divestiture financials, and injects a pro-forma instruction into the debate BRIEF.
    The operator runs the emitted script via the Workflow tool; fresh results then flow into value-input
    -> Director. Mirrors finish_debate()."""
    import re
    apx = json.load(open(ROOT / "apex_basket_value.json", encoding="utf-8"))
    stale = [p["symbol"] for p in apx.get("apex_basket", []) if isinstance(p, dict) and p.get("stale_anchor")]
    if not stale:
        print("value_revalidate: no stale_anchor names stamped — nothing to revalidate (run value-post first).")
        return 0
    js = (ROOT / "_weekly_debate.js").read_text(encoding="utf-8")
    js = re.sub(r"const SYMS = \[[^\]]*\]", "const SYMS = []", js)                       # force all online
    js = re.sub(r"const ONLINE_SYMS = \[[^\]]*\]", "const ONLINE_SYMS = " + json.dumps(stale), js)
    instr = ("REVALIDATION RUN: this name's load-bearing STRUCTURAL EVENT has already FIRED — WebSearch the "
             "POST-EVENT PRO-FORMA financials (post-spin/post-divestiture share count + segment EBITDA + net "
             "debt from the most recent filing AFTER the event date) and rebuild the Sum-of-Parts on THOSE; do "
             "NOT reuse pre-event segment data. State the event date and the pro-forma basis explicitly. ")
    js = re.sub(r'(const BRIEF = ")', lambda m: m.group(1) + instr, js, count=1)
    out = ROOT / "_revalidate_debate.js"
    out.write_text(js, encoding="utf-8", newline="\n")
    print(f"value_revalidate: {len(stale)} stale-anchor name(s) {stale} -> online pro-forma re-debate")
    print(f"REVALIDATE_SCRIPT={out.resolve()}")
    return len(stale)


def _moat_hints(finalists):
    """Per-symbol moat terminal-erosion hints for the skeptic prompt. A value-destroying / sub-cost-of-
    capital eroding franchise enters the skeptic as a default-REFUTE candidate (refute_candidate=True).
    Computed FRESH from the scan + universe + debate result so it does not depend on value-input order."""
    try:
        uni = {x["symbol"]: x for x in json.load(open(ROOT / "_radar_universe.json", encoding="utf-8"))}
    except Exception:
        uni = {}
    scan = gcs_io.gcs_read_json("scans/latest_global.json")
    if not scan:
        try:
            scan = json.load(open("../frontend/public/latest_global.json", encoding="utf-8"))
        except Exception:
            scan = {}
    sc_by = {s.get("symbol"): s for s in (scan.get("stocks") or [])}
    hints = {}
    for sym in finalists:
        rf = ROOT / "results_regime" / f"{sym}.json"
        try:
            r = json.load(open(rf, encoding="utf-8")) if rf.exists() else {"sector": uni.get(sym, {}).get("sector", "")}
        except Exception:
            r = {"sector": uni.get(sym, {}).get("sector", "")}
        mf = _moat_features(uni.get(sym, {}), sc_by.get(sym, {}), r)
        hints[sym] = {
            "erosion": mf["moat_erosion"], "severity": mf["erosion_severity"],
            "roic_below": mf["roic_below_hurdle"], "returns_trend": mf["returns_trend"],
            "gross_margin_trend": mf["gross_margin_trend"],
            "refute_candidate": bool(mf["erosion_severity"] == "value-destroying"
                                     or (mf["moat_erosion"] == "CAP" and mf["roic_below_hurdle"])),
        }
    return hints


# ── UNIFIED SKEPTIC (2026-07-01, methodology review X1) ──────────────────────────────────────
# ONE generator for all three books (value / regime / disruptor — the highest-vol book never had a
# kill-tier at all). Per-LANE attack rubric (a compounder, an event-driven special-sit and a theme
# growth name fail in different ways); output is VERDICT-BASED ONLY — categorical
# correction_severity (minor|material) + kill_scope REPLACE the numeric value_conviction_cap
# (the numeric-cap-as-ceiling pattern is the proven bug class from the scale-out re-grade).
# Cross-book DEDUPE: the value book skips finalists already kill-checked fresh by the regime pass
# this run (their shards are carried across), so the net agent count DROPS while coverage grows.
_SKEPTIC_BOOKS = {
    "value": {"apex": "apex_basket_value.json", "shards": "_skeptic",
              "wf": "_skeptic_workflow.js", "env_line": "SKEPTIC_WORKFLOW"},
    "regime": {"apex": "apex_basket_opus_regime.json", "shards": "_skeptic_regime",
               "wf": "_regime_skeptic_workflow.js", "env_line": "REGIME_SKEPTIC_WORKFLOW"},
    "disruptor": {"apex": "disruptor/apex_basket_disruptor.json", "shards": "_skeptic_disruptor",
                  "wf": "_disruptor_skeptic_workflow.js", "env_line": "DISRUPTOR_SKEPTIC_WORKFLOW"},
}

_SKEPTIC_ATTACKS = {
    "value": "(a) STALE-ANCHOR - is the fair value built on pre-event financials (spin/divestiture/peak quarter)? (b) NUMBER TRUTH - do the load-bearing figures (segment EBITDA, net debt, share count, preferred stack) verify against the latest primary filing? (c) THESIS WEAKNESS / TERMINAL MOAT - is the claimed cheapness real edge, or priced/structural (melting business, AI/fintech/cord-cutting disruption, terminal multiple, returns BELOW cost of capital)? (d) HIDDEN DISQUALIFIER - litigation, covenant, dilution, regulatory action, a binary/soft catalyst dressed as hard.",
    "event": "(a) IS THE CATALYST GENUINELY LIVE + DATED + BINDING - or already fired / slipped / priced (the spread closed)? Confirm the exact date/terms from a primary source (8-K, merger agreement, FDA/regulator page). (b) IS THE TARGET REAL (deal terms / event-resolved value) or fantasy? (c) IS THE DOWNSIDE FLOOR REAL - what actually backstops the price if the event fails (deal-break, cash, recovery value), or does the floor break (going-concern, ATM/dilution, financing contingency)? (d) HIDDEN DISQUALIFIER - trading through terms, a second-request, single-binary with no floor.",
    "disruptor": "(a) STALE-ANCHOR - are the growth/backlog/design-win figures from an old quarter? Re-verify against the LATEST filing/release. (b) NUMBER TRUTH - do revenue growth, gross-margin trajectory, backlog/orders and the named customer wins verify against primary sources? (c) THESIS WEAKNESS - is the theme demand actually flowing to THIS name (share shifts, competitive entry, customer concentration, in-sourcing risk), or is the multiple pricing a steeper S-curve than the verified evidence supports? (d) HIDDEN DISQUALIFIER - dilution/SBC waves, channel stuffing, one-customer dependence, insider distribution. DATED-CALL GUIDANCE: attack DATED claims against DATED sources; an undated secular growth story is NOT auto-REFUTED for lacking a date - demand the CURRENT evidence verifies, and kill only on contradiction or unverifiable load-bearing claims.",
    # neglect lane (2026-07-17): the name reached the debate BECAUSE nobody is looking at it -
    # so the strongest bear case is that the neglect is deserved.
    "neglect_orphan": "(a) THE NEGLECT IS DESERVED - this name is here because the market stopped looking; hunt for the disqualifier the market already knows: controlled/dual-class governance, a fading end-market, a litigation/liability tail, delisting or index-mechanics overhang, controlling-holder overhang. (b) POST-EVENT NUMBER TRUTH - the headline financials are event-noised (IFRS-5 reclassification, stranded costs, carve-out allocations); rebuild the CLEAN continuing-operations numbers from the actual filings and verify the debate's normalized figures against them - do NOT accept 'one-off' labels for costs that recur. (c) STANDALONE VIABILITY - post-spin/post-event, does the remaining business have its own customers, systems and balance sheet, or is it a stub of stranded costs and dis-synergies dressed as a compounder? (d) HIDDEN DISQUALIFIER - parent retained-stake overhang, TSA cliffs, debt pushed onto the SpinCo, insider selling into the void.",
}


def skeptic_gen(book):
    """Emit the unified skeptic Workflow for `book`. Per-finalist lane resolution happens HERE
    (python, deterministic): a regime finalist whose record carries lane=equity_special_sit /
    source=opus_catalyst gets the EVENT rubric; disruptor finalists get the disruptor rubric;
    everything else the value/compounder rubric. Batch 6 (proven rate-limit ceiling)."""
    cfg = _SKEPTIC_BOOKS[book]
    apx = json.load(open(ROOT / cfg["apex"], encoding="utf-8"))
    finalists = [p["symbol"] for p in apx.get("apex_basket", []) if isinstance(p, dict) and p.get("symbol")]
    for r in apx.get("runner_ups", []):
        s = r.get("symbol") if isinstance(r, dict) else r
        if s and s not in finalists:
            finalists.append(s)
    shards_dir = ROOT / cfg["shards"]
    shards_dir.mkdir(parents=True, exist_ok=True)

    # cross-book dedupe: the value pass reuses FRESH regime shards (same name, same debate record,
    # same rubric) - carry the shard across (fresh mtime + provenance) instead of re-running it.
    carried = []
    if book == "value":
        reg_apex = ROOT / _SKEPTIC_BOOKS["regime"]["apex"]
        reg_mtime = reg_apex.stat().st_mtime if reg_apex.exists() else 0
        # 24h window matching _post_common.SKEPTIC_FRESH_WINDOW_S (the strict mtime-1 rule broke
        # every run: regime-post re-stamps the apex AFTER the skeptics write, so same-run shards
        # always looked "stale" and the dedupe carried 0)
        _fresh_win = 24 * 3600
        for s in list(finalists):
            sh = ROOT / _SKEPTIC_BOOKS["regime"]["shards"] / (s + ".json")
            if sh.exists() and sh.stat().st_mtime >= reg_mtime - _fresh_win:
                try:
                    d = json.load(open(sh, encoding="utf-8"))
                    d["carried_from_book"] = "regime"
                    (shards_dir / (s + ".json")).write_text(
                        json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
                    finalists.remove(s)
                    carried.append(s)
                except Exception:
                    pass
        if carried:
            print(f"skeptic dedupe: carried {len(carried)} fresh regime verdicts across: {carried}")

    # per-finalist lane + input paths
    lanes = {}
    for s in finalists:
        lane, res, doss = "value", f"results_regime/{s}.json", f"dossiers/{s}.md"
        if book == "disruptor":
            lane, res, doss = "disruptor", f"disruptor/results/{s}.json", f"disruptor/dossiers/{s}.md"
        elif book == "regime":
            try:
                rec = json.load(open(ROOT / "results_regime" / (s + ".json"), encoding="utf-8"))
                if rec.get("lane") == "equity_special_sit" or rec.get("source") == "opus_catalyst":
                    lane = "event"
                elif rec.get("lane") == "neglect_orphan":
                    lane = "neglect_orphan"
            except Exception:
                pass
        lanes[s] = {"lane": lane, "res": res, "doss": doss, "attack": _SKEPTIC_ATTACKS[lane]}
    hints = _moat_hints(finalists)

    js = (
        "export const meta = {\n"
        "  name: '__BOOK__-skeptic',\n"
        "  description: 'Unified skeptic kill-tier over the __BOOK__ finalists (default REFUTED, per-lane rubric, verdict-based only)',\n"
        "  phases: [{ title: 'Skeptic', model: '__SKEPTIC_MODEL__' }],\n"
        "}\n"
        "const DIR = 'backend/_opus_debate'\n"
        "const SYMS = __FINALISTS__\n"
        "const LANES = __LANES__\n"
        "const MOAT_HINTS = __MOAT_HINTS__\n"
        "phase('Skeptic')\n"
        "const BATCH = 6\n"
        "for (let b = 0; b < SYMS.length; b += BATCH) {\n"
        "  await parallel(SYMS.slice(b, b + BATCH).map(sym => () => agent(\n"
        "    'SKEPTIC tier for ' + sym + ' (__BOOK__ finalist; lane ' + LANES[sym].lane + '). Your job is to KILL this thesis; default verdict REFUTED unless you can independently confirm the load-bearing facts against a PRIMARY source (filings, the company IR site, regulator pages). You see ONLY the bear side - do NOT read or reconstruct the bull case.\\n' +\n"
        "    ((MOAT_HINTS[sym] || {}).refute_candidate && LANES[sym].lane === 'value' ? 'MOAT ALERT (deterministic screen): ' + sym + ' is a TERMINAL-EROSION candidate - erosion=' + (MOAT_HINTS[sym] || {}).erosion + ', severity=' + (MOAT_HINTS[sym] || {}).severity + ', earns_below_cost_of_capital=' + (MOAT_HINTS[sym] || {}).roic_below + ', returns ' + (MOAT_HINTS[sym] || {}).returns_trend + ', gross-margin ' + (MOAT_HINTS[sym] || {}).gross_margin_trend + '. The moat is ERODING by default: you must find PRIMARY-SOURCE proof of durable pricing power / rising returns to CONFIRM, else REFUTED with the moat erosion as the kill_fact.\\n' : '') +\n"
        "    '1. Read ' + DIR + '/' + LANES[sym].res + ' but USE ONLY: bear_thesis, sop_bear, risk_reward, catalyst_status (+ downside_floor/target_px for an event lane). Read the forensic dossier ' + DIR + '/' + LANES[sym].doss + ' if it exists.\\n' +\n"
        "    '2. Verify the CURRENT facts. FIRST reach for the paid FMP MCP tools via ToolSearch (keyword search e.g. \"FMP earnings transcript\", \"FMP statements\", \"FMP news\", \"FMP quote\") for the latest transcript / quarterly numbers / news / price - it is structured, licensed and reliable; fall back to WebSearch/WebFetch only for what FMP lacks, and do NOT scrape press-release PDFs by shell. Attack: ' + LANES[sym].attack + '\\n' +\n"
        "    '3. Verdict: CONFIRMED (bear attacked, thesis survives) | CONFIRMED_WITH_CORRECTIONS (survives but a load-bearing number/claim needed fixing - state it) | REFUTED (a kill_fact breaks the thesis). ALSO correction_severity: \"minor\" (footnote-level, thesis arithmetic intact) or \"material\" (a load-bearing number/date/anchor moved - the post layer haircuts sizing on material). AND kill_scope: which layer your strongest finding hits - \"thesis\" | \"numbers\" | \"catalyst\" | \"moat\". Do NOT emit any numeric conviction cap - verdicts and severity only.\\n' +\n"
        "    '4. Write (Write tool) VALID JSON to ' + DIR + '/__SHARDS__/' + sym + '.json = {symbol:\"' + sym + '\", verdict, kill_fact, corrections, correction_severity, kill_scope, evidence:[2-4 dated primary-source cites]}. Never fabricate. Reply exactly: DONE',\n"
        "    { label: '__BOOK__-skeptic:' + sym, phase: 'Skeptic', agentType: 'general-purpose', model: '__SKEPTIC_MODEL__' })))\n"
        "}\n"
        "return 'DONE'\n"
    )
    js = (js.replace("__FINALISTS__", json.dumps(finalists))
            .replace("__LANES__", json.dumps(lanes))
            .replace("__MOAT_HINTS__", json.dumps(hints))
            .replace("__SHARDS__", cfg["shards"])
            .replace("__BOOK__", book)
            .replace("__SKEPTIC_MODEL__", SKEPTIC_MODEL))
    out = ROOT / cfg["wf"]
    out.write_text(js, encoding="utf-8", newline="\n")
    n_ref = sum(1 for h in hints.values() if h.get("refute_candidate"))
    n_lanes = {ln: sum(1 for v in lanes.values() if v["lane"] == ln) for ln in ("value", "event", "disruptor")}
    print(f"{book}_skeptic (unified): {len(finalists)} to run (+{len(carried)} carried) | lanes={n_lanes} "
          f"| moat REFUTE-candidates={n_ref} | {SKEPTIC_MODEL} kill-tier")
    print(f"{cfg['env_line']}={out.resolve()}")
    return len(finalists)


def value_skeptic():
    """Unified-skeptic wrapper (X1) - the value book. Run AFTER regime_skeptic in the weekly order
    so the cross-book dedupe carries fresh regime verdicts instead of re-running them."""
    return skeptic_gen("value")


def regime_skeptic():
    """Unified-skeptic wrapper (X1) - the regime/apex book (special-sit seats get the EVENT rubric)."""
    return skeptic_gen("regime")


def control_sample():
    """11b — monthly FALSE-NEGATIVE estimate: debate N=8 random names from the scan that sit in NO
    methodology basket; report how many clear the forensic gate with CRO MoS >= 30% — the funnel's
    miss-rate on its own success metric. Tagged control=true; results land in results_control/ and
    NEVER feed baskets."""
    import random
    from datetime import datetime as _dtt
    scan = gcs_io.gcs_read_json("scans/latest_global.json") or json.load(
        open("../frontend/public/latest_global.json", encoding="utf-8"))
    mp = gcs_io.gcs_read_json("scans/methodology_picks.json") or {}
    in_basket = set()
    for meth in (mp.get("methodologies") or {}).values():
        picks_l = meth.get("picks") if isinstance(meth, dict) else meth     # dict-with-picks or bare list
        for p in (picks_l or []):
            s = p.get("symbol") if isinstance(p, dict) else p
            if s:
                in_basket.add(s)
    pool = [s for s in scan.get("stocks", [])
            if s.get("symbol") and s["symbol"] not in in_basket
            and isinstance(s.get("market_cap"), (int, float)) and s["market_cap"] >= 2e9]
    rng = random.Random(int(_dtt.now().strftime("%Y%m")))          # deterministic within the month
    picks = rng.sample(pool, min(8, len(pool)))
    (ROOT / "results_control").mkdir(exist_ok=True)
    syms = []
    for s in picks:
        sym = s["symbol"]
        syms.append(sym)
        ms = "\n".join(f"{k}: {s.get(k)}" for k in
                       ("price", "market_cap", "sector", "company_name", "revenue_yoy", "revenue_cagr_3y",
                        "eps_yoy", "gross_margin", "net_margin", "roic_avg", "altman_z", "p_fcf",
                        "dcf_fcff_mos", "epv_mos", "graham_revised_mos", "owner_earnings_mos",
                        "iv15_deep_value_mos", "net_debt", "days_to_earnings") if s.get(k) is not None)
        (ROOT / "inputs" / f"{sym}.json").write_text(json.dumps(
            {"symbol": sym, "company": s.get("company_name", ""), "sector": s.get("sector", ""),
             "signal_type": "control", "control": True,
             "metrics_str": "=== CONTROL SAMPLE (random non-basket name; scan fields) ===\n" + ms},
            ensure_ascii=False, indent=1), encoding="utf-8")
    js = (ROOT / "_weekly_debate.js").read_text(encoding="utf-8")
    import re
    js = re.sub(r"const RES = DIR \+ '/results_regime'", "const RES = DIR + '/results_control'", js)
    js = re.sub(r"const SYMS = \[[^\]]*\]", "const SYMS = []", js)
    js = re.sub(r"const ONLINE_SYMS = \[[^\]]*\]", "const ONLINE_SYMS = " + json.dumps(syms), js)
    js = re.sub(r"const RECHECK_SYMS = \[[^\]]*\]", "const RECHECK_SYMS = []", js)
    js = js.split("phase('Director')")[0] + "log('Control sample complete (no Director).')\nreturn 'DONE'\n"
    js = js.replace("name: 'speculair-opus-weekly'", "name: 'speculair-control-sample'")
    out = ROOT / "_control_debate.js"
    out.write_text(js, encoding="utf-8", newline="\n")
    print(f"control_sample: {len(syms)} random non-basket names {syms} -> results_control/")
    print(f"CONTROL_WORKFLOW={out.resolve()}")
    print("After the workflow: count results_control names with interrogator_score>=3 AND CRO MoS>=30% "
          "= the funnel's false-negative (miss) rate this month.")
    return len(syms)


FR_DIR = ROOT / "future_resources"
# Lane A debate subtree (Phase 3, clone of the disruptor D_* layout) — isolated so the FR chain never
# touches results_regime / the value or B13 surfaces (Do-NOT: never mutate other books' surfaces).
FR_INP = FR_DIR / "inputs"
FR_TXT = FR_DIR / "transcripts"
FR_RES = FR_DIR / "results"
FR_DOSS = FR_DIR / "dossiers"
FR_ARCH = FR_DIR / "_archive_prev"


def fr_universe():
    """FUTURE RESOURCES Stage A+B (FUTURE_RESOURCES_SPEC.md §1, monthly): deterministic FMP screen
    per chain -> two-lane gates. Lane A (producers/royalties): TTM FCF>0 OR TTM OCF>0 (tagged
    growth_capex_fcf_negative when OCF-only), TTM EBITDA>0, funded solvency != weak, mcap>=$500M,
    ADV>=$5M. Lane B (developers): mcap>=$150M, ADV>=$2M, NO profitability gate — cash-runway fields
    stamped here; the funded-through-milestone gate is asserted at Lane B candidate extraction.
    Anti-shrink (disruptor_universe lessons): re-screens FMP from scratch every run; never reads a
    prior universe/candidates file; STOPs loudly on thin screens. Gates cached by symbol+month."""
    import concurrent.futures
    import re
    from datetime import datetime as _dt
    tax = json.load(open(ROOT / "future_resources_chains.json", encoding="utf-8"))
    key = E.get_key("FMP_API_KEY")
    if not key:
        print("GUARD: no FMP_API_KEY — STOP")
        raise SystemExit(1)
    FR_DIR.mkdir(exist_ok=True)
    (FR_DIR / "chain_map").mkdir(exist_ok=True)
    base = "https://financialmodelingprep.com/stable"
    fa, fb = tax["floors"]["lane_a"], tax["floors"]["lane_b"]

    # ── Stage A — screen once at the WIDER lane-B floors; lane assignment happens after Stage B ──
    seen, hints, raw_total = {}, {}, 0
    for ch in tax["chains"]:
        ch_syms = set()
        for ind in ch.get("fmp_industries") or []:
            ind_rows = 0
            for exch in tax.get("exchanges") or ["NYSE", "NASDAQ", "AMEX"]:
                try:
                    rows = requests.get(base + "/company-screener", params={
                        "industry": ind, "exchange": exch,
                        "marketCapMoreThan": fb["market_cap_usd"],
                        "volumeMoreThan": 100_000, "priceMoreThan": fb["price_min"],
                        "isActivelyTrading": "true", "isEtf": "false", "isFund": "false",
                        "limit": 1000, "apikey": key}, timeout=25).json()
                except Exception:
                    rows = []
                if not isinstance(rows, list):
                    rows = []
                raw_total += len(rows)
                ind_rows += len(rows)
                for r in rows:
                    sym = r.get("symbol")
                    if not sym or "." in sym and not sym.replace(".", "").isalnum():
                        continue
                    seen.setdefault(sym, {"symbol": sym, "name": r.get("companyName", ""),
                                          "sector": r.get("sector", ""), "industry": r.get("industry", ""),
                                          "mcap": r.get("marketCap"), "price": r.get("price"),
                                          "volume": r.get("volume")})
                    ch_syms.add(sym)
                    hints.setdefault(sym, [])
                    if ch["id"] not in hints[sym]:
                        hints[sym].append(ch["id"])
            if ind_rows == 0:
                print(f"  WARN [{ch['id']}] industry '{ind}' returned 0 rows — "
                      f"misspelled/unverified industry string? (see spec §1.1 (verify) list)")
        print(f"  Stage A [{ch['id']}]: {len(ch_syms)} unique candidates")
    print(f"Stage A: {len(seen)} unique candidates from {raw_total} raw rows")
    if raw_total < 100:
        print("GUARD: FMP screen returned <100 raw rows (key/quota failure?) — STOP, not a silent small universe")
        raise SystemExit(1)
    n_uranium = sum(1 for s, hs in hints.items() if "uranium_fuel_cycle" in hs)
    if n_uranium == 0:
        print("GUARD: uranium_fuel_cycle mapped 0 candidates — the AMEX canary "
              "(NYSE-American cohort missing?) — STOP")
        raise SystemExit(1)

    # ── per-lane liquidity floors (free — from the screener rows) ──
    def _adv(c):
        p, v = c.get("price"), c.get("volume")
        return p * v if isinstance(p, (int, float)) and isinstance(v, (int, float)) else 0.0
    liquid = {s: c for s, c in seen.items() if _adv(c) >= fb["adv_usd"]}
    print(f"liquidity gate (lane-B ADV >= ${fb['adv_usd']/1e6:.0f}M): {len(liquid)} pass")

    # ── Stage B — financial gates, cached by symbol+month ──
    cache_p = FR_DIR / "_gates_cache.json"
    cache = {}
    if cache_p.exists():
        try:
            cache = json.load(open(cache_p, encoding="utf-8"))
        except Exception:
            cache = {}
    month = _dt.now().strftime("%Y-%m")

    def gates_for(sym):
        ck = f"{sym}|{month}"
        if ck in cache:
            return sym, cache[ck]
        g = {"ttm_fcf": None, "ttm_ocf": None, "ttm_capex": None, "ttm_ebitda": None,
             "ttm_revenue": None, "rev_yoy": None, "cash_sti": None, "balance_date": None,
             "balance_sheet_stale": None, "monthly_burn": None, "runway_months": None,
             "growth_capex_fcf_negative": False, "pass_cash": False, "pass_profit": False}
        try:
            cf = requests.get(base + "/cash-flow-statement",
                              params={"symbol": sym, "period": "quarter", "limit": 5, "apikey": key}, timeout=20).json()
            if isinstance(cf, list) and len(cf) >= 4:
                ocfs, capexs, fcfs = [], [], []
                for q in cf[:4]:
                    ocf = q.get("operatingCashFlow")
                    cap = q.get("capitalExpenditure")
                    v = q.get("freeCashFlow")
                    if not isinstance(v, (int, float)):
                        v = (ocf or 0) + (cap or 0)
                    ocfs.append(ocf if isinstance(ocf, (int, float)) else 0)
                    capexs.append(cap if isinstance(cap, (int, float)) else 0)
                    fcfs.append(v if isinstance(v, (int, float)) else 0)
                g["ttm_ocf"], g["ttm_capex"], g["ttm_fcf"] = sum(ocfs), sum(capexs), sum(fcfs)
        except Exception:
            pass
        try:
            qs = requests.get(base + "/income-statement",
                              params={"symbol": sym, "period": "quarter", "limit": 8, "apikey": key}, timeout=20).json()
            if isinstance(qs, list) and len(qs) >= 4:
                g["ttm_revenue"] = sum(q.get("revenue") or 0 for q in qs[:4])
                g["ttm_ebitda"] = sum(q.get("ebitda") or 0 for q in qs[:4])
                if len(qs) >= 8:
                    pri4 = sum(q.get("revenue") or 0 for q in qs[4:8])
                    if pri4 > 0:
                        g["rev_yoy"] = round(g["ttm_revenue"] / pri4 - 1, 4)
        except Exception:
            pass
        try:
            bs = requests.get(base + "/balance-sheet-statement",
                              params={"symbol": sym, "period": "quarter", "limit": 1, "apikey": key}, timeout=20).json()
            if isinstance(bs, list) and bs:
                b = bs[0]
                cash = b.get("cashAndShortTermInvestments")
                if not isinstance(cash, (int, float)):
                    cash = (b.get("cashAndCashEquivalents") or 0) + (b.get("shortTermInvestments") or 0)
                g["cash_sti"] = cash
                g["balance_date"] = b.get("date")
                try:
                    age_days = (_dt.now() - _dt.strptime(b.get("date", ""), "%Y-%m-%d")).days
                    g["balance_sheet_stale"] = bool(age_days > 185)   # >2 quarters: web-verify raises downstream
                except Exception:
                    g["balance_sheet_stale"] = None
        except Exception:
            pass
        # runway (lane B): burn = -(TTM OCF + TTM capex) when negative; FCF-positive names have no burn
        if isinstance(g["ttm_ocf"], (int, float)) and isinstance(g["ttm_capex"], (int, float)):
            fcf12 = g["ttm_ocf"] + g["ttm_capex"]
            burn = max(-fcf12, 0.0) / 12.0
            g["monthly_burn"] = round(burn, 0)
            if burn > 0 and isinstance(g["cash_sti"], (int, float)):
                g["runway_months"] = round(g["cash_sti"] / burn, 1)
        # lane A gate flags
        ocf_pos = isinstance(g["ttm_ocf"], (int, float)) and g["ttm_ocf"] > 0
        fcf_pos = isinstance(g["ttm_fcf"], (int, float)) and g["ttm_fcf"] > 0
        g["pass_cash"] = bool(fcf_pos or ocf_pos)
        g["growth_capex_fcf_negative"] = bool(ocf_pos and not fcf_pos)
        g["pass_profit"] = bool(isinstance(g["ttm_ebitda"], (int, float)) and g["ttm_ebitda"] > 0)
        cache[ck] = g
        return sym, g

    syms = sorted(liquid)
    print(f"Stage B: financial gates over {len(syms)} names (cached: {sum(1 for s in syms if f'{s}|{month}' in cache)})...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        done = 0
        for sym, g in ex.map(gates_for, syms):
            liquid[sym]["gates"] = g
            done += 1
            if done % 50 == 0:
                print(f"  ...{done}/{len(syms)}")
    cache_p.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    # ── lane assignment ──
    def _n(v):
        return v if isinstance(v, (int, float)) else 0
    lane_a_pre = [s for s, c in liquid.items()
                  if _n(c.get("mcap")) >= fa["market_cap_usd"] and _n(c.get("price")) >= fa["price_min"]
                  and _adv(c) >= fa["adv_usd"] and c["gates"]["pass_cash"] and c["gates"]["pass_profit"]]
    fl = _funded_leverage(lane_a_pre)                           # batch, shared cache — lane A only
    lane_a, lane_b = [], []
    for s, c in sorted(liquid.items()):
        g = c["gates"]
        g["adv_usd"] = round(_adv(c), 0)
        g["royalty_hint"] = bool(re.search(r"royalt|streaming", c.get("name", ""), re.I))
        c["chains_hint"] = hints.get(s, [])
        if s in lane_a_pre:
            flv = fl.get(s, {})
            solv = _funded_solvency(c.get("sector", ""), flv.get("net_funded_debt_ebitda"), flv.get("interest_coverage"))
            g["funded_solvency"] = solv
            g["net_funded_debt_ebitda"] = flv.get("net_funded_debt_ebitda")
            if solv != "weak":
                c["lane"] = "a"
                lane_a.append(c)
                continue
        if _n(c.get("mcap")) >= fb["market_cap_usd"] and _n(c.get("price")) >= fb["price_min"] \
                and _adv(c) >= fb["adv_usd"]:
            c["lane"] = "b"
            lane_b.append(c)
    by_chain = {ch["id"]: {"a": 0, "b": 0} for ch in tax["chains"]}
    for c in lane_a + lane_b:
        for cid in c["chains_hint"]:
            by_chain[cid][c["lane"]] += 1
    funnel = {"screened": len(seen), "liquid": len(liquid), "lane_a": len(lane_a), "lane_b": len(lane_b)}
    print(f"lane gates: lane_a={len(lane_a)} (cash+EBITDA+solvency+floors) | "
          f"lane_b={len(lane_b)} (floors+runway-stamped, milestone gate downstream)")
    print(f"by_chain x lane: {by_chain}")
    (FR_DIR / "_candidates.json").write_text(
        json.dumps({"built_at": _dt.now().isoformat(), "taxonomy_version": tax.get("version"),
                    "funnel_partial": funnel, "by_chain": by_chain,
                    "candidates": lane_a + lane_b}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"FR UNIVERSE STAGE A+B OK: screened={len(seen)} liquid={len(liquid)} "
          f"lane_a={len(lane_a)} lane_b={len(lane_b)} -> {FR_DIR / '_candidates.json'}")
    print("Next (Phase 2): fr chain-map workflow + fr-map-merge (business_model, commodity_revenue_share).")
    return len(lane_a) + len(lane_b)


def fr_map():
    """FUTURE RESOURCES Stage C — emit the chunked Sonnet CHAIN-MAP workflow (spec §2, monthly, Phase 2).
    Clone of the disruptor theme-map emitter (_dt_map.js): chunk _candidates.json <=20/agent into
    future_resources/_map_chunk_<i>.json and render future_resources/_fr_map.js (Sonnet seat). Two NEW
    required fields per symbol vs the disruptor pass — business_model (drives the royalty gate bypass +
    the developer-in-lane-A sanity check) and commodity_revenue_share (0-1, an LLM estimate feeding the
    deterministic fcf_torque formula). The PHYSICAL-ANCHOR rule is enforced HERE: each agent must state
    in one line the physical thing the company makes/moves/powers/instruments for its chain; no answer =>
    chain_fit_confidence=low regardless of industry (the anti-Visa gate). Run the Workflow, then fr-map-merge."""
    cand_f = FR_DIR / "_candidates.json"
    if not cand_f.exists():
        print("GUARD: no future_resources/_candidates.json — run fr-universe first. STOP")
        raise SystemExit(1)
    cd = json.load(open(cand_f, encoding="utf-8"))
    cands = [c for c in cd.get("candidates", []) if c.get("symbol")]
    if not cands:
        print("GUARD: _candidates.json has 0 candidates — STOP")
        raise SystemExit(1)
    FR_DIR.mkdir(exist_ok=True)
    (FR_DIR / "chain_map").mkdir(exist_ok=True)
    # slim per-symbol rows for the map agents (symbol/name/sector/industry/mcap + lane + gates)
    slim = [{"symbol": c["symbol"], "name": c.get("name", ""), "sector": c.get("sector", ""),
             "industry": c.get("industry", ""), "mcap": c.get("mcap"), "lane": c.get("lane", ""),
             "chains_hint": c.get("chains_hint", []), "gates": c.get("gates", {})} for c in cands]
    CH = 20
    chunks = [slim[i:i + CH] for i in range(0, len(slim), CH)]
    for i, ch in enumerate(chunks):
        (FR_DIR / f"_map_chunk_{i}.json").write_text(json.dumps(ch, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(chunks)
    # NB: apostrophe-free inside the JS single-quoted agent string (a stray ' breaks the generated JS).
    js = """export const meta = {
  name: 'future-resources-chain-map',
  description: 'Sonnet chain-mapping over the gated Future Resources candidates (Radar-style, chunked; physical-anchor enforced)',
  phases: [{ title: 'ChainMap', model: '__RADAR_MODEL__' }],
}
const N = __N__
phase('ChainMap')
await parallel(Array.from({ length: N }, (_, i) => () => agent(
  'You are the FUTURE RESOURCES CHAIN RADAR (chain-mapping + physical-anchor pass). Read backend/_opus_debate/future_resources_chains.json (the versioned chain taxonomy: ids, theses, value-chain layers, notes) and backend/_opus_debate/future_resources/_map_chunk_' + i + '.json (your candidate chunk: symbol/name/sector/industry/mcap + lane + Stage-B gates). For EACH symbol decide, skeptically:\\n' +
  '- physical_anchor: ONE line naming the PHYSICAL thing this company makes, moves, powers, or directly instruments for its chain (quantum hardware counts; a payments network never does). If you CANNOT name one, set chain_fit_confidence=low REGARDLESS of the industry or keyword hints (the anti-Visa rule; it binds hardest on the broad quantum and robotics filters).\\n' +
  '- chains: array of taxonomy ids this company GENUINELY rides (max 2; a name like UUUU legitimately carries uranium_fuel_cycle AND rare_earth_strategic; [] if none — an industry filter catches many non-chain names).\\n' +
  '- business_model: exactly one of producer | royalty_streamer | developer | equipment_services (royalty_streamer auto-passes the cash gates; a pre-FCF developer belongs in lane B, never lane A; equipment_services = the toll-taker selling into the chain).\\n' +
  '- commodity_revenue_share: a number 0-1 = the fraction of revenue exposed to the chain commodity (1.0 for a pure producer; a diversified miner like TECK gets your best estimate; an equipment/services or utility name is lower). This feeds a deterministic torque formula, so estimate it honestly.\\n' +
  '- value_chain_position: one line — which value-chain layer it occupies and what it sells.\\n' +
  '- true_competitors: 4-8 REAL competitor tickers (business-model comparables, in-universe or NOT — include foreign listings and private-adjacent public proxies).\\n' +
  '- chain_fit_confidence: high | medium | low (low = the FMP industry filter caught a name that is NOT really in this chain — a chemical company in the rare-earth screen, a generic hardware or software name in quantum, a non-chain royalty company, a legacy industrial). LOW-confidence names are DROPPED at merge, printed, never silent.\\n' +
  'Write (Write tool) VALID JSON to backend/_opus_debate/future_resources/_fr_' + i + '.json as {\"<SYM>\": {physical_anchor, chains, business_model, commodity_revenue_share, value_chain_position, true_competitors, chain_fit_confidence}, ...} covering EVERY symbol in your chunk. Reply exactly: DONE',
  { label: 'frmap:' + i, phase: 'ChainMap', model: '__RADAR_MODEL__' })))
return 'DONE'
"""
    js = js.replace("__N__", str(n)).replace("__RADAR_MODEL__", RADAR_MODEL)
    out = FR_DIR / "_fr_map.js"
    out.write_text(js, encoding="utf-8", newline="\n")
    print(f"FR CHAIN-MAP EMIT OK: {len(cands)} candidates -> {n} {RADAR_MODEL} map chunks")
    print(f"MAP_WORKFLOW={out.resolve()}")
    print("Next: run the Workflow, then: python backend/weekly_opus_refresh.py fr-map-merge")
    return n


def fr_map_merge():
    """FUTURE RESOURCES Stage C-merge (spec §2 + §1.3, monthly, Phase 2): merge the Sonnet chain-map
    shards, DROP chain_fit_confidence=low / chain-less / physical-anchor-less names (printed, never
    silent), explode per-symbol chain_map/<SYM>.json, apply the royalty_streamer Stage-B cash-gate
    bypass, and write future_resources/universe.json (built_at, taxonomy_version, funnel, by_chain x
    lane, members with gates blocks). GUARDS: a developer mapped into lane A is a printed mapping
    error; a chain with historically >=3 candidates that maps to 0 members STOPs (a systematic mapper
    failure, spec §1.3). The pre-rank cut to the debated set happens LATER in fr-prep, never here
    (deterministic code never picks members, Do-NOT #2)."""
    import glob as _g
    from datetime import datetime as _dt
    tax = json.load(open(ROOT / "future_resources_chains.json", encoding="utf-8"))
    cand_f = FR_DIR / "_candidates.json"
    if not cand_f.exists():
        print("GUARD: no future_resources/_candidates.json — run fr-universe first. STOP")
        raise SystemExit(1)
    cd = json.load(open(cand_f, encoding="utf-8"))
    cands = {c["symbol"]: c for c in cd.get("candidates", []) if c.get("symbol")}
    fa = tax["floors"]["lane_a"]
    valid_chain_ids = {ch["id"] for ch in tax["chains"]}
    shards = sorted(_g.glob(str(FR_DIR / "_fr_*.json")))
    mapped = {}
    for f in shards:
        try:
            mapped.update(json.load(open(f, encoding="utf-8")))
        except Exception as e:
            print(f"WARN: shard {os.path.basename(f)} unreadable ({e})")
    if not mapped:
        print("GUARD: no chain-map shards (_fr_*.json) — run the _fr_map.js workflow first. STOP")
        raise SystemExit(1)
    # DROP low-confidence / chain-less / physical-anchor-less (printed, never silent — spec §2)
    def _bad(m):
        conf = (m.get("chain_fit_confidence") or "").lower()
        chains = [c for c in (m.get("chains") or []) if c in valid_chain_ids]
        return conf == "low" or not chains or not (str(m.get("physical_anchor") or "").strip())
    low = sorted(s for s, m in mapped.items() if s in cands and _bad(m))
    keep = {s: m for s, m in mapped.items() if s in cands and s not in set(low)}
    print(f"fr-map-merge: {len(mapped)} mapped from {len(shards)} shards | "
          f"DROPPED low-confidence/chain-less/anchor-less ({len(low)}): {low}")
    # explode per-symbol chain_map/<SYM>.json
    for s, m in keep.items():
        chains = [c for c in (m.get("chains") or []) if c in valid_chain_ids][:2]
        (FR_DIR / "chain_map" / f"{s}.json").write_text(
            json.dumps({"symbol": s, **m, "chains": chains}, ensure_ascii=False, indent=1), encoding="utf-8")
    # ── build members: cand (lane/gates) + chain-map (chains/business_model/commodity_revenue_share/…) ──
    def _n(v):
        return v if isinstance(v, (int, float)) else 0
    members, mapping_errors, royalty_flips = [], [], []
    for s in sorted(keep):
        m, c = keep[s], cands[s]
        g = c.get("gates", {})
        bm = (m.get("business_model") or "").strip().lower()
        lane = c.get("lane", "")
        chains = [ci for ci in (m.get("chains") or []) if ci in valid_chain_ids][:2]
        # royalty_streamer bypass (spec §1.2): a streamer that fell to lane B on the FCF-light cash
        # gate flips to lane A if it clears the lane-A floors (royalty cos are structurally clean).
        royalty_bypass = False
        if bm == "royalty_streamer" and lane == "b" \
                and _n(c.get("mcap")) >= fa["market_cap_usd"] and _n(c.get("price")) >= fa["price_min"] \
                and _n(g.get("adv_usd")) >= fa["adv_usd"]:
            lane = "a"
            royalty_bypass = True
            royalty_flips.append(s)
        # GUARD: a developer mapped into lane A is a mapping error (a pre-FCF dev cannot be a producer);
        # print it loudly + flag it — the deterministic gates set the lane, so we surface, never silently move.
        mapping_error = bool(bm == "developer" and lane == "a")
        if mapping_error:
            mapping_errors.append(s)
        crs = m.get("commodity_revenue_share")
        try:
            crs = round(float(crs), 3) if crs is not None else None
        except (TypeError, ValueError):
            crs = None
        members.append({
            "symbol": s, "name": c.get("name", ""), "sector": c.get("sector", ""),
            "industry": c.get("industry", ""), "mcap": c.get("mcap"), "price": c.get("price"), "lane": lane,
            "chains": chains, "business_model": bm,
            "commodity_revenue_share": crs,
            "physical_anchor": (m.get("physical_anchor") or "").strip(),
            "value_chain_position": m.get("value_chain_position", ""),
            "true_competitors": m.get("true_competitors") or [],
            "chain_fit_confidence": (m.get("chain_fit_confidence") or "").lower(),
            "royalty_bypass": royalty_bypass, "mapping_error": mapping_error,
            "gates": g})
    if royalty_flips:
        print(f"royalty_streamer bypass: flipped lane B->A on cash-gate exempt streamers: {royalty_flips}")
    if mapping_errors:
        print(f"!!! MAPPING ERROR: developer(s) mapped into lane A (a pre-FCF dev is not a producer) — "
              f"surfaced, review the chain map: {mapping_errors}")
    # by_chain x lane counts + the zero-map STOP guard (spec §1.3)
    by_chain = {ch["id"]: {"a": 0, "b": 0} for ch in tax["chains"]}
    for mm in members:
        for cid in mm["chains"]:
            if mm["lane"] in ("a", "b"):
                by_chain[cid][mm["lane"]] += 1
    pre_by_chain = cd.get("by_chain") or {}              # candidate counts BEFORE the map
    zero_stops = []
    for ch in tax["chains"]:
        cid = ch["id"]
        pre = (pre_by_chain.get(cid) or {})
        pre_total = _n(pre.get("a")) + _n(pre.get("b"))
        post_total = by_chain[cid]["a"] + by_chain[cid]["b"]
        if pre_total >= 3 and post_total == 0:
            zero_stops.append(f"{cid} ({pre_total} candidates -> 0 mapped)")
    n_a = sum(1 for mm in members if mm["lane"] == "a")
    n_b = sum(1 for mm in members if mm["lane"] == "b")
    funnel = {**(cd.get("funnel_partial") or {}), "mapped": len(members),
              "mapped_lane_a": n_a, "mapped_lane_b": n_b}
    print(f"FUNNEL: screened={funnel.get('screened')} liquid={funnel.get('liquid')} "
          f"gated_a={funnel.get('lane_a')} gated_b={funnel.get('lane_b')} mapped={len(members)} "
          f"(lane_a={n_a} lane_b={n_b})")
    print(f"by_chain x lane: {by_chain}")
    if zero_stops:
        print(f"GUARD (spec §1.3): chain(s) with >=3 candidates mapped to 0 members {zero_stops} — a "
              f"systematic mapper failure. universe.json NOT written. STOP (do not reuse a prior month).")
        raise SystemExit(1)
    if n_a < 8:
        print(f"NOTE: only {n_a} lane-A members mapped — fr-prep will STOP if <25 mappable; a thin lane-A "
              f"is expected on the current small commodity cohorts, not a bug.")
    uni = {"built_at": _dt.now().isoformat(), "taxonomy_version": tax.get("version"),
           "funnel": funnel, "by_chain": by_chain, "members": members}
    (FR_DIR / "universe.json").write_text(json.dumps(uni, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"FR UNIVERSE OK: {len(members)} mapped members (lane_a={n_a} lane_b={n_b}) -> {FR_DIR / 'universe.json'}")
    print("Next (Phase 3): fr-prep (Lane A pre-rank + debate workflow), then fr-input / FR Director / fr-post.")
    return len(members)


# ═══════════════ FUTURE RESOURCES Phase 3 — Lane A debate / Director / post (spec §5) ═══════════════
# Clone lineage: the disruptor prep/input/csv/publish recipe (deleted 2026-07-10, recovered from
# git history 48daee82^) with the FR deltas — isolated future_resources/ subtree, chain-map join,
# §3 torque metrics in the bundle + grade input, the regime sidecar, and the typed valuation block
# (pipeline-v3 step 6b/7 schema) emitted from day one so _numeric_gate works on FR records.

def _fr_redebate_triggers(members):
    """Weekly re-debate triggers (disruptor §3.1 clone over the FR subtree). A member RE-DEBATES iff:
    (a) no cached result; (b) cached result > 28d old; (c) earnings since (transcript newer than the
    result); (d) |price move| >= 15% vs the debate's stamped price; (e) close < published
    thesis_break_px; (f) new entrant. Everything else keeps its cached debate and is RE-GRADED by the
    Director. FIRST RUN (no cache): all members re-debate. Returns (redebate, cached, reason_by_sym)."""
    from datetime import datetime as _dt
    quotes = {}
    try:
        key = E.get_key("FMP_API_KEY")
        if key:
            syms = [m["symbol"] for m in members]
            for i in range(0, len(syms), 50):
                rows = requests.get("https://financialmodelingprep.com/stable/batch-quote",
                                    params={"symbols": ",".join(syms[i:i + 50]), "apikey": key}, timeout=25).json()
                for q in (rows if isinstance(rows, list) else []):
                    if q.get("symbol") and isinstance(q.get("price"), (int, float)):
                        quotes[q["symbol"]] = q["price"]
    except Exception:
        quotes = {}
    tb_px = {}
    apx_f = E.FRONTEND_DIR / "public" / "speculair_future_resources.json"
    if apx_f.exists():
        try:
            for p in json.load(open(apx_f, encoding="utf-8")).get("apex_basket", []):
                if isinstance(p, dict) and p.get("symbol") and isinstance(p.get("thesis_break_px"), (int, float)):
                    tb_px[p["symbol"]] = p["thesis_break_px"]
        except Exception:
            tb_px = {}
    redebate, cached, why = set(), set(), {}
    now = _dt.now()
    for m in members:
        sym = m["symbol"]
        rf = FR_RES / f"{sym}.json"
        if not rf.exists():
            redebate.add(sym); why[sym] = "no-cache"
            continue
        try:
            r = json.load(open(rf, encoding="utf-8"))
        except Exception:
            redebate.add(sym); why[sym] = "unreadable-cache"; continue
        try:
            age_days = (now - _dt.fromtimestamp(rf.stat().st_mtime)).days
        except Exception:
            age_days = 999
        if age_days > 28:
            redebate.add(sym); why[sym] = f">28d ({age_days}d)"; continue
        tx = FR_TXT / f"{sym}.txt"
        if tx.exists():
            try:
                if tx.stat().st_mtime > rf.stat().st_mtime + 1:
                    redebate.add(sym); why[sym] = "earnings-since"; continue
            except Exception:
                pass
        px_now = quotes.get(sym)
        px_then = r.get("live_price") or (r.get("valuation") or {}).get("live_price") or m.get("price")
        if isinstance(px_now, (int, float)) and isinstance(px_then, (int, float)) and px_then > 0:
            if abs(px_now / px_then - 1) >= 0.15:
                redebate.add(sym); why[sym] = f"|move|>=15% ({round((px_now/px_then-1)*100)}%)"; continue
        tb = tb_px.get(sym)
        if isinstance(tb, (int, float)) and isinstance(px_now, (int, float)) and px_now < tb:
            redebate.add(sym); why[sym] = f"close<{tb} (thesis_break)"; continue
        cached.add(sym)
    return redebate, cached, why


def fr_prep():
    """FUTURE RESOURCES Lane A prep/bundle (spec §5, weekly — disruptor-prep clone over the isolated
    future_resources/ subtree). Steps: universe staleness self-gate (21d — how "monthly" fires) ->
    Lane A member selection + PRE-RANK cut (<=8/chain then <=40 global, held names protected; STOP if
    <25 mappable Lane A members — the pre-rank decides who gets DEBATED, never who gets PICKED,
    Do-NOT #2) -> §3.1-style re-debate triggers -> selective self-clean -> per-member input bundles
    (signal_type="future_resources", metrics via E._build_debate_metrics + _fmp_segments + the §3
    torque metrics + the chain-map row + the regime sidecar) -> transcripts via E.resolve_transcripts
    (no FMP -> ONLINE_SYMS) -> dump engine system prompts -> render _FR_WORKFLOW_TEMPLATE ->
    future_resources/_fr_debate.js (BATCH=8, typed valuation block emitted from day one).
    `--dry-logic` skips the network-heavy bundle/transcript/metric builds (cut+STOP+emission only)."""
    import shutil
    from datetime import datetime as _dt
    dry = "--dry-logic" in sys.argv
    E.load_api_keys()
    for d in (FR_INP, FR_TXT, FR_RES, FR_DOSS):
        d.mkdir(parents=True, exist_ok=True)

    # ── universe staleness self-gate (monthly rebuild fires through here) ──
    uni_f = FR_DIR / "universe.json"
    if not uni_f.exists():
        print("FR UNIVERSE STALE — run fr-universe, the _fr_map.js workflow, then fr-map-merge first. STOP")
        sys.exit(1)
    uni = json.load(open(uni_f, encoding="utf-8"))
    try:
        built = _dt.fromisoformat(uni.get("built_at", ""))
        age = (_dt.now() - built).days
    except Exception:
        age = 999
    if age > 21:
        print("FR UNIVERSE STALE (>21d) — run fr-universe / fr-map / fr-map-merge first. STOP")
        sys.exit(1)

    # ── Lane A members + held-name union (the ONLY carry-over, Do-NOT #3) ──
    lane_a = [m for m in uni.get("members", []) if m.get("symbol") and m.get("lane") == "a"]
    held = set()
    apx_f = E.FRONTEND_DIR / "public" / "speculair_future_resources.json"
    if apx_f.exists():
        try:
            held = {p.get("symbol") for p in json.load(open(apx_f, encoding="utf-8")).get("apex_basket", [])
                    if isinstance(p, dict) and p.get("symbol")}
        except Exception:
            held = set()
    for m in lane_a:
        m["held"] = m["symbol"] in held
    if len(lane_a) < 25:
        print(f"GUARD: only {len(lane_a)} mappable Lane A members (<25) — DEGRADED universe, STOP "
              f"(disruptor Stage-D precedent; do not debate a thin book, do not reuse a prior month)")
        sys.exit(1)

    # ── PRE-RANK cut: deterministic quality/torque ordering for the DEBATE BUDGET only (never
    #    membership): ebitda margin desc (cost-curve proxy), rev_yoy desc, funded leverage asc.
    #    <=8 per PRIMARY chain, then <=40 global; held names are never cut. ──
    def _prerank(m):
        g = m.get("gates", {})
        rev, ebitda = g.get("ttm_revenue"), g.get("ttm_ebitda")
        em = (ebitda / rev) if isinstance(rev, (int, float)) and rev > 0 and isinstance(ebitda, (int, float)) else -9
        yy = g.get("rev_yoy") if isinstance(g.get("rev_yoy"), (int, float)) else -9
        nd = g.get("net_funded_debt_ebitda") if isinstance(g.get("net_funded_debt_ebitda"), (int, float)) else 99
        return (-em, -yy, nd)

    by_chain = {}
    for m in lane_a:
        cid = (m.get("chains") or ["_unmapped"])[0]
        by_chain.setdefault(cid, []).append(m)
    selected = {m["symbol"] for m in lane_a if m["held"]}          # held: protected from every cut
    for cid, ms in by_chain.items():
        for m in sorted(ms, key=_prerank)[:8]:
            selected.add(m["symbol"])
    if len(selected) > 40:
        ranked = sorted([m for m in lane_a if m["symbol"] in selected and not m["held"]], key=_prerank)
        keep_n = max(0, 40 - sum(1 for m in lane_a if m["held"]))
        selected = {m["symbol"] for m in ranked[:keep_n]} | {m["symbol"] for m in lane_a if m["held"]}
    members = [m for m in lane_a if m["symbol"] in selected]
    print(f"fr-prep pre-rank: {len(lane_a)} Lane A mapped -> {len(members)} debated "
          f"(<=8/chain, <=40 global, held protected: {sorted(held & selected) or 'none'})")

    # ── §3.1 re-debate triggers (BEFORE the selective self-clean) ──
    redebate, cached, why = _fr_redebate_triggers(members)
    redebate &= selected                                            # only budgeted names debate

    # ── selective self-clean: archive ONLY re-debated results, keep fresh cached ones ──
    if FR_ARCH.exists():
        shutil.rmtree(FR_ARCH, ignore_errors=True)
    FR_ARCH.mkdir(parents=True, exist_ok=True)
    (FR_ARCH / "results").mkdir(exist_ok=True)
    (FR_ARCH / "dossiers").mkdir(exist_ok=True)
    for sym in sorted(redebate):
        for sub, ext in (("results", ".json"), ("dossiers", ".md")):
            src = FR_DIR / sub / f"{sym}{ext}"
            if src.exists():
                shutil.move(str(src), str(FR_ARCH / sub / f"{sym}{ext}"))
    print(f"selective self-clean: archived {len(redebate)} re-debate result(s), kept {len(cached & selected)} cached")

    if dry:
        fmp_syms, online_syms = [], sorted(redebate)
        print("DRY-LOGIC: bundle/transcript/torque-metric builds SKIPPED (all names emitted as online)")
    else:
        # ── §3 torque metrics for the bundles (chain-map commodity_revenue_share already on members) ──
        sys.path.insert(0, os.path.join(BK, "_opus_debate"))
        rm = {}
        try:
            import _resource_metrics as RM
            rm = RM.compute([m for m in members if m["symbol"] in redebate], offline=False)
        except Exception as _e:
            print(f"WARN: _resource_metrics compute failed ({_e}) — bundles ship without torque metrics")
        # ── bundles: per re-debated member, inputs/<SYM>.json. Scan firewall: scan_fin ONLY through
        #    E._SCAN_FIN_FIELDS (hit_prob/factor_scores excluded by design); off-scan members build
        #    scan_fin from the Stage-B gates (absent fields stay ABSENT, never zero-filled). ──
        scan = gcs_io.gcs_read_json("scans/latest_global.json") or json.load(
            open("../frontend/public/latest_global.json", encoding="utf-8"))
        scan_by_sym = {s.get("symbol"): s for s in scan.get("stocks", []) if s.get("symbol")}
        regime_state = {}
        rs_f = FR_DIR / "regime_state.json"
        if rs_f.exists():
            try:
                regime_state = (json.load(open(rs_f, encoding="utf-8")) or {}).get("chains", {})
            except Exception:
                regime_state = {}
        fmp_syms, online_syms = [], []
        for m in sorted(members, key=lambda x: x["symbol"]):
            sym = m["symbol"]
            if sym not in redebate:
                continue                                    # cached & fresh — Director re-grades as-is
            sc = scan_by_sym.get(sym, {})
            g = m.get("gates", {})
            if sc:
                scan_fin = {k: sc.get(k) for k in E._SCAN_FIN_FIELDS if sc.get(k) is not None}
                bh = sc.get("buffett_history") or {}
                rows = bh.get("rows")
                if isinstance(rows, list) and rows:
                    scan_fin["history_rows"] = [{"year": r.get("year"), "revenue_mm": r.get("revenue_mm"),
                                                 "net_income_mm": r.get("net_income_mm"), "eps": r.get("eps")} for r in rows[-6:]]
                    if isinstance(bh.get("cagrs"), dict):
                        scan_fin["history_cagrs"] = bh["cagrs"]
            else:
                scan_fin = {}
                for src_k, dst_k in (("rev_yoy", "revenue_yoy"), ("ttm_revenue", "revenue_ttm"),
                                     ("net_funded_debt_ebitda", "net_debt")):
                    v = g.get(src_k)
                    if v is not None:
                        scan_fin[dst_k] = v
            cand = {"symbol": sym, "sector": (sc.get("sector") or m.get("sector", "")), "price": sc.get("price"),
                    "fair_value": sc.get("buffett_fair_value"), "mos": sc.get("margin_of_safety")}
            try:
                metrics = E._build_debate_metrics(financials=cand, scan_fin=scan_fin)
            except Exception:
                metrics = "No financial metrics available."
            metrics = (metrics or "") + _fmp_segments(sym)
            chain_regime = {cid: (regime_state.get(cid) or {}).get("state", "NEUTRAL")
                            for cid in (m.get("chains") or [])}
            (FR_INP / f"{sym}.json").write_text(json.dumps({
                "symbol": sym, "sector": (sc.get("sector") or m.get("sector", "")),
                "signal_type": "future_resources",
                "company": sc.get("name") or sc.get("companyName") or m.get("name", ""),
                "metrics_str": metrics, "dossier": "",
                "chains": m.get("chains", []), "business_model": m.get("business_model", ""),
                "physical_anchor": m.get("physical_anchor", ""),
                "commodity_revenue_share": m.get("commodity_revenue_share"),
                "chain_regime": chain_regime,
                "resource_metrics": rm.get(sym) or {},
                "gates": g}, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                tx = E.resolve_transcripts(sym)
                real = [t for t in tx.get("all_transcripts", []) if len(t.get("content", "")) > 1000]
            except Exception:
                real = []
            if real:
                real.sort(key=lambda t: t["date"])
                (FR_TXT / f"{sym}.txt").write_text(
                    "\n\n".join("=== " + t["date"] + " ===\n" + E._slice_transcript(t["content"]) for t in real[-5:]),
                    encoding="utf-8")
                fmp_syms.append(sym)
            else:
                online_syms.append(sym)

    # ── dump the engine system prompts into future_resources/ (idempotent; standalone run) ──
    (FR_DIR / "interrogator_system.txt").write_text(E.INTERROGATOR_SYSTEM_PROMPT, encoding="utf-8")
    (FR_DIR / "architect_system.txt").write_text(E.ARCHITECT_SYSTEM_PROMPT, encoding="utf-8")
    (FR_DIR / "moderator_system.txt").write_text(E.MODERATOR_SYSTEM_PROMPT, encoding="utf-8")

    # ── render the workflow with __SYMS__/__ONLINE_SYMS__ baked in (the args-delivery workaround) ──
    js = (_FR_WORKFLOW_TEMPLATE
          .replace("__SYMS__", json.dumps(fmp_syms))
          .replace("__ONLINE_SYMS__", json.dumps(online_syms))
          .replace("__DEBATE_MODEL__", DEBATE_MODEL))
    out = FR_DIR / "_fr_debate.js"
    out.write_text(js, encoding="utf-8", newline="\n")
    total = len(fmp_syms) + len(online_syms)
    print(f"FR PREP OK: {len(fmp_syms)} FMP + {len(online_syms)} online = {total} total "
          f"(re-debating {len(redebate)}, cached {len(cached & selected)})")
    if why:
        print(f"  re-debate reasons: {dict(sorted((k, v) for k, v in why.items() if k in selected))}")
    print(f"FR_WORKFLOW_SCRIPT={out.resolve()}")
    print("Next: run the Workflow, then: fr-numeric-gate --enforce, fr-input, [FR Director agent], "
          "fr-post, fr-csv, fr-publish")
    return total


def fr_input():
    """FUTURE RESOURCES grade-input builder (spec §5/§3.2, mirrors value_input()/disruptor_input()).
    One row per future_resources/results/<SYM>.json: universe/chain-map join (chains, business_model,
    physical_anchor, commodity_revenue_share) + the §3 torque metrics (_resource_metrics, stamped
    deterministically) + chain_regime from the regime sidecar + gate tags (growth_capex_fcf_negative,
    funded_solvency, balance_sheet_stale) + the CRO sop_mos_pct + the forensic gate REUSED VERBATIM
    (iscore<=2 -> EXCLUDE; missing -> CAP fail-closed; DETERIORAT -> CAP). Writes fr_grade_input.json
    + fr_director_prompt.txt (FR_DIRECTOR_PROMPT + prior-run measured-correlation block + ledger)."""
    import glob
    E.load_api_keys()
    uni = {m["symbol"]: m for m in json.load(open(FR_DIR / "universe.json", encoding="utf-8")).get("members", [])}
    regime_state = {}
    rs_f = FR_DIR / "regime_state.json"
    if rs_f.exists():
        try:
            regime_state = (json.load(open(rs_f, encoding="utf-8")) or {}).get("chains", {})
        except Exception:
            regime_state = {}
    res_files = sorted(glob.glob(str(FR_RES / "*.json")))
    if not res_files:
        print("GUARD: no future_resources/results/ records — run fr-prep + the debate Workflow first. STOP")
        sys.exit(1)
    # §3 torque metrics over the debated members (chain-map commodity_revenue_share already joined)
    sys.path.insert(0, os.path.join(BK, "_opus_debate"))
    deb_syms = [os.path.basename(f)[:-5] for f in res_files]
    rm = {}
    try:
        import _resource_metrics as RM
        rm = RM.compute([uni[s] for s in deb_syms if s in uni], offline=("--offline" in sys.argv))
    except Exception as _e:
        print(f"WARN: _resource_metrics compute failed ({_e}) — grade input ships without torque metrics")
    fl = _funded_leverage(deb_syms)
    out = []
    n_gate = n_gcf = n_stale = 0
    for f in res_files:
        try:
            r = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        sym = r.get("symbol") or os.path.basename(f)[:-5]
        u = uni.get(sym, {})
        g = u.get("gates", {})
        mt = rm.get(sym) or {}
        val = r.get("valuation") or {}
        price = r.get("live_price") or val.get("live_price") or u.get("price")
        sop_num = _val_money(r.get("sop_fair_value")) or (val.get("base_fv_px") if isinstance(val.get("base_fv_px"), (int, float)) else None)
        sop_mos = round((sop_num - price) / price * 100, 1) if (sop_num and isinstance(price, (int, float)) and price > 0) else None
        iscore = r.get("interrogator_score")
        traj = (r.get("trajectory") or "").upper()
        # forensic gate REUSED VERBATIM from value_input (regime-independent credibility veto)
        if isinstance(iscore, (int, float)) and iscore <= 2:
            gate = "EXCLUDE"
        elif iscore is None:
            gate = "CAP"
            print(f"WARN: {sym} interrogator_score missing/unparseable -> gate=CAP (fail-closed)")
        elif "DETERIORAT" in traj:
            gate = "CAP"
        else:
            gate = ""
        if gate:
            n_gate += 1
        flv = fl.get(sym, {})
        ndE = flv.get("net_funded_debt_ebitda")
        icov = flv.get("interest_coverage")
        funded_solv = g.get("funded_solvency") or _funded_solvency(u.get("sector", ""), ndE, icov)
        gcf = bool(g.get("growth_capex_fcf_negative"))
        bss = g.get("balance_sheet_stale")
        n_gcf += int(gcf)
        n_stale += int(bool(bss))
        chains = u.get("chains") or []
        chain_regime = {cid: (regime_state.get(cid) or {}).get("state", "NEUTRAL") for cid in chains}
        _sev = {"HEADWIND": 2, "NEUTRAL": 1, "TAILWIND": 0}
        worst = max(chain_regime.values(), key=lambda s: _sev.get(s, 1)) if chain_regime else "NEUTRAL"
        row = {
            "symbol": sym, "sector": r.get("sector", "") or u.get("sector", ""),
            # universe / chain-map join
            "chains": chains, "business_model": u.get("business_model", ""),
            "physical_anchor": u.get("physical_anchor", ""),
            "value_chain_position": u.get("value_chain_position", ""),
            "true_competitors": u.get("true_competitors") or [],
            "commodity_revenue_share": u.get("commodity_revenue_share"),
            "royalty_bypass": bool(u.get("royalty_bypass")), "mapping_error": bool(u.get("mapping_error")),
            # §3 deterministic metrics (torque set or non-commodity set, per taxonomy)
            "torque_metrics": mt.get("torque_metrics"),
            "ebitda_margin_ttm": mt.get("ebitda_margin_ttm"), "ebitda_margin_band": mt.get("ebitda_margin_band"),
            "fcf_torque_10pct": mt.get("fcf_torque_10pct"),
            "commodity_beta_2y": mt.get("commodity_beta_2y"), "beta_benchmark": mt.get("beta_benchmark"),
            "beta_is_proxy": mt.get("beta_is_proxy"),
            "gm_trajectory": mt.get("gm_trajectory") or r.get("gm_trajectory", ""),
            "rev_yoy": g.get("rev_yoy"), "fcf_margin": mt.get("fcf_margin"),
            # regime overlay (HEADWIND => Director size rule; worst-of for 2-chain names)
            "chain_regime": chain_regime, "chain_regime_worst": worst,
            # gate tags
            "growth_capex_fcf_negative": gcf, "balance_sheet_stale": bss,
            "ndebt_ebitda": mt.get("ndebt_ebitda") if mt.get("ndebt_ebitda") is not None else (
                round(ndE, 2) if isinstance(ndE, (int, float)) else None),
            "net_funded_debt_ebitda": round(ndE, 2) if isinstance(ndE, (int, float)) else g.get("net_funded_debt_ebitda"),
            "interest_coverage": round(icov, 1) if isinstance(icov, (int, float)) else None,
            "funded_solvency": funded_solv,
            # system of record: CRO fair value + debate forensics
            "sop_fair_value": r.get("sop_fair_value", ""), "sop_mos_pct": sop_mos,
            "price": price, "price_currency": r.get("price_currency") or val.get("price_currency"),
            "risk_reward": (r.get("risk_reward", "") or "")[:220],
            "debate_verdict": (r.get("verdict") or "").upper(), "debate_conviction": r.get("conviction"),
            "value_conviction": r.get("value_conviction"),
            "interrogator_score": iscore, "trajectory": r.get("trajectory", ""),
            "forensic_gate": gate,
            "numeric_gate": r.get("numeric_gate", ""),
            "catalyst_status": r.get("catalyst_status", ""),
        }
        out.append(row)
    _asof = datetime.now().strftime("%Y-%m-%d")
    for x in out:
        x["as_of"] = _asof
    (FR_DIR / "fr_grade_input.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    # Director rotation ledger (best-effort; EMPTY on the maiden run — the prompt says so)
    try:
        write_director_ledger("fr", FR_DIR / "apex_basket_fr.json",
                              E.FRONTEND_DIR / "public" / "speculair_future_resources_tracking.json")
    except Exception as _e:
        print(f"WARN: fr ledger build failed ({_e})")
    prompt_txt = f"AS OF {_asof} — every metric row in fr_grade_input.json carries this date.\n\n" + FR_DIRECTOR_PROMPT
    pa = FR_DIR / "apex_basket_fr.json"                # feed-forward: prior MEASURED correlations
    if pa.exists():
        try:
            pc = json.load(open(pa, encoding="utf-8")).get("correlation") or {}
            if pc.get("avg_pairwise") is not None:
                fl_pairs = pc.get("flagged_pairs") or []
                lines = [f"  {p['a']}-{p['b']}: {p['corr']}" + (" [BREACH]" if p.get("breach") else "") for p in fl_pairs[:12]]
                prompt_txt += ("\n\nPRIOR-RUN MEASURED CORRELATIONS (2y weekly log returns; argue your commodity-factor "
                               f"stress AGAINST these real numbers, do not merely assert 'barely co-move'). "
                               f"avg pairwise={pc.get('avg_pairwise')}, max={pc.get('max_pair')}. Pairs >=0.6:\n"
                               + ("\n".join(lines) if lines else "  (none >=0.6 last run)"))
        except Exception:
            pass
    (FR_DIR / "fr_director_prompt.txt").write_text(prompt_txt, encoding="utf-8")
    from collections import Counter as _C
    fs = _C(x["funded_solvency"] for x in out)
    regs = _C(x["chain_regime_worst"] for x in out)
    print(f"fr_grade_input.json: {len(out)} names | forensic_gate={n_gate} growth_capex_fcf_negative={n_gcf} "
          f"balance_sheet_stale={n_stale}")
    print(f"  funded_solvency: {dict(fs)} | chain_regime_worst: {dict(regs)}")
    print(f"fr_director_prompt.txt written ({len(prompt_txt)} chars)")
    return len(out)


def fr_csv():
    """CSV of the FUTURE RESOURCES Lane A apex (apex_basket_fr.json) + memo — clone of value_csv()/
    disruptor_csv() over the future_resources/ subtree. Chain-flavored columns: chains/business_model/
    physical_anchor/cost_curve/contracting_reserve/capital_discipline + the §3 metric fields +
    chain_regime; drops the value-only mos_agreement*/cro_only columns."""
    import csv
    apex = json.load(open(FR_DIR / "apex_basket_fr.json", encoding="utf-8"))
    picks = [p for p in apex.get("apex_basket", []) if isinstance(p, dict) and p.get("symbol")]
    chain_exp = apex.get("chain_exposure") or {}
    gin = {}
    if (FR_DIR / "fr_grade_input.json").exists():
        try:
            gin = {x["symbol"]: x for x in json.load(open(FR_DIR / "fr_grade_input.json", encoding="utf-8"))}
        except Exception:
            gin = {}
    cols = ["rank", "symbol", "sector", "fr_score", "chains", "business_model", "physical_anchor",
            "value_chain_position", "fr_thesis", "cost_curve", "contracting_reserve", "capital_discipline",
            "valuation_guard", "ebitda_margin_ttm", "ebitda_margin_band", "fcf_torque_10pct",
            "commodity_beta_2y", "beta_benchmark", "ndebt_ebitda", "interest_coverage", "funded_solvency",
            "growth_capex_fcf_negative", "torque_leverage_quadrant", "balance_sheet_stale",
            "chain_regime", "headwind_justification", "sop_mos_pct", "forensic_gate", "numeric_gate",
            "exposure_axes", "chain_exposure_pct", "size_units_effective", "weight_pct", "corr_flag",
            "entry_plan", "thesis_break_px", "bear_fv_px",
            "debate_verdict", "debate_conviction", "catalyst_status", "sop_fair_value", "sop_breakdown",
            "risk_reward", "true_competitors", "bull_thesis", "bear_thesis", "sop_bull", "sop_bear",
            "consensus_delta", "moderator_conclusion", "interrogator_score", "trajectory", "interrogator_dossier"]
    rows = []
    for rank, p in enumerate(sorted(picks, key=lambda x: -(x.get("fr_score") or 0)), 1):
        sym = p["symbol"]
        r = {}
        if (FR_RES / f"{sym}.json").exists():
            try:
                r = json.load(open(FR_RES / f"{sym}.json", encoding="utf-8"))
            except Exception:
                r = {}
        doss = ""
        if (FR_DOSS / f"{sym}.md").exists():
            doss = (FR_DOSS / f"{sym}.md").read_text(encoding="utf-8")
        g = gin.get(sym, {})
        prim_chain = (p.get("chains") or [None])[0] or ""
        band = p.get("ebitda_margin_band", g.get("ebitda_margin_band", ""))
        rows.append({
            "rank": rank, "symbol": sym, "sector": p.get("sector", ""),
            "fr_score": p.get("fr_score", ""),
            "chains": "; ".join(p.get("chains", [])) if isinstance(p.get("chains"), list) else (p.get("chains", "") or ""),
            "business_model": p.get("business_model", "") or g.get("business_model", ""),
            "physical_anchor": p.get("physical_anchor", "") or g.get("physical_anchor", ""),
            "value_chain_position": p.get("value_chain_position", "") or g.get("value_chain_position", ""),
            "fr_thesis": p.get("thesis", ""), "cost_curve": p.get("cost_curve", ""),
            "contracting_reserve": p.get("contracting_reserve", ""),
            "capital_discipline": p.get("capital_discipline", ""),
            "valuation_guard": p.get("valuation_guard", ""),
            "ebitda_margin_ttm": p.get("ebitda_margin_ttm", g.get("ebitda_margin_ttm", "")),
            "ebitda_margin_band": (band or {}).get("band", "") if isinstance(band, dict) else (band or ""),
            "fcf_torque_10pct": p.get("fcf_torque_10pct", g.get("fcf_torque_10pct", "")),
            "commodity_beta_2y": p.get("commodity_beta_2y", g.get("commodity_beta_2y", "")),
            "beta_benchmark": g.get("beta_benchmark", ""),
            "ndebt_ebitda": p.get("ndebt_ebitda", g.get("ndebt_ebitda", "")),
            "interest_coverage": p.get("interest_coverage", g.get("interest_coverage", "")),
            "funded_solvency": p.get("funded_solvency", g.get("funded_solvency", "")),
            "growth_capex_fcf_negative": p.get("growth_capex_fcf_negative", g.get("growth_capex_fcf_negative", "")),
            "torque_leverage_quadrant": p.get("torque_leverage_quadrant", ""),
            "balance_sheet_stale": g.get("balance_sheet_stale", ""),
            "chain_regime": json.dumps(p.get("chain_regime", g.get("chain_regime", "")), ensure_ascii=False)
                            if isinstance(p.get("chain_regime", g.get("chain_regime")), dict)
                            else (p.get("chain_regime", g.get("chain_regime", "")) or ""),
            "headwind_justification": p.get("headwind_justification", ""),
            "sop_mos_pct": p.get("sop_mos_pct", g.get("sop_mos_pct", "")),
            "forensic_gate": p.get("forensic_gate", g.get("forensic_gate", "")),
            "numeric_gate": g.get("numeric_gate", ""),
            "exposure_axes": "; ".join(p["exposure_axes"]) if isinstance(p.get("exposure_axes"), list) else (p.get("exposure_axes", "") or ""),
            "chain_exposure_pct": chain_exp.get(prim_chain, ""),
            "size_units_effective": p.get("size_units_effective", ""), "weight_pct": p.get("weight_pct", ""),
            "corr_flag": p.get("corr_flag", ""), "entry_plan": p.get("entry_plan", ""),
            "thesis_break_px": p.get("thesis_break_px", ""), "bear_fv_px": p.get("bear_fv_px", ""),
            "debate_verdict": r.get("verdict", ""), "debate_conviction": r.get("conviction", ""),
            "catalyst_status": r.get("catalyst_status", ""), "sop_fair_value": r.get("sop_fair_value", ""),
            "sop_breakdown": r.get("sop_breakdown", ""), "risk_reward": r.get("risk_reward", ""),
            "true_competitors": ", ".join(g.get("true_competitors", [])) if isinstance(g.get("true_competitors"), list) else "",
            "bull_thesis": r.get("bull_thesis", ""), "bear_thesis": r.get("bear_thesis", ""),
            "sop_bull": r.get("sop_bull", ""), "sop_bear": r.get("sop_bear", ""),
            "consensus_delta": r.get("consensus_delta", ""),
            "moderator_conclusion": r.get("moderator_conclusion", ""),
            "interrogator_score": r.get("interrogator_score", ""), "trajectory": r.get("trajectory", ""),
            "interrogator_dossier": doss,
        })
    out = FR_DIR / "speculair_fr_apex.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    mm = apex.get("fr_memo", "")
    (FR_DIR / "speculair_fr_apex_memo.txt").write_text(
        mm if isinstance(mm, str) else json.dumps(mm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(rows)} FR-apex rows x {len(cols)} cols -> {out}")
    print(f"fr_memo -> {FR_DIR / 'speculair_fr_apex_memo.txt'}")
    return len(rows)


def fr_publish(push_gcs=False):
    """Stage the public Future Resources Lane A payload (frontend/public/speculair_future_resources.json)
    AND maintain the Lane A live-forward NAV (spec §7, mirrors value_publish/disruptor_publish).
    CONTRACT: the picks array key is `apex_basket` and the embedded tracking key is `fr_tracking` —
    the pre-staged nightly _mark_speculair_nav() tuple reads exactly those. Lane A NAV state files
    (speculair_future_resources_tracking.json + _weighted) are NEVER blended with any other book or
    with Lane B (Do-NOT #1). Degraded-publish guards (Do-NOT #10): <6 picks, a chain-cap breach after
    post, or a failed GCS push after one retry => report and stop. --gcs pushes 3 files + readback."""
    import datetime as _dt
    PUB = E.FRONTEND_DIR / "public"
    apx = json.load(open(FR_DIR / "apex_basket_fr.json", encoding="utf-8"))
    # PUBLISH GATE (mirror of value_publish's): never publish an un-posted basket.
    if not apx.get("fr_post_applied") and "--force" not in sys.argv:
        print("GUARD fr publish gate: apex_basket_fr.json has NO fr_post_applied stamp — run fr-post "
              "first. Aborting (override: --force).")
        sys.exit(1)
    picks = [p for p in apx.get("apex_basket", []) if isinstance(p, dict) and p.get("symbol")]
    # Do-NOT #10: never publish degraded — a thin book is a report-and-stop, not a small payload.
    if len(picks) < 6:
        print(f"GUARD fr publish: only {len(picks)} Lane A picks (<6) — DEGRADED, report and stop "
              f"(no payload written, no NAV chained, other books unaffected).")
        sys.exit(1)
    # Do-NOT #10: chain-cap breach after post = stop. Re-derive per-chain weight AND name count from
    # the FINAL weights (a 2-chain name counts toward both); weight tolerance 0.5pp for rounding.
    # The count cap (<=3/chain) cannot be fixed deterministically without changing membership (P1),
    # so a count breach stops HERE — the Director slate must be fixed and re-posted.
    weights = apx.get("weights") or {}
    chain_w, chain_n = {}, {}
    for p in picks:
        for cid in (p.get("chains") or []):
            chain_w[cid] = chain_w.get(cid, 0.0) + (weights.get(p["symbol"], 0) * 100)
            chain_n[cid] = chain_n.get(cid, 0) + 1
    breaches = {cid: round(w, 2) for cid, w in chain_w.items() if w > 30.0 + 0.5}
    count_breaches = {cid: n for cid, n in chain_n.items() if n > 3}
    if breaches or count_breaches:
        print(f"GUARD fr publish: chain cap breach AFTER post — weight {breaches} (>30%) / count "
              f"{count_breaches} (>3 names) — report and stop; fix the Director slate / re-run fr-post "
              f"before publishing.")
        sys.exit(1)
    try:                                              # capture this run's Director decisions into the year ledger
        append_decision_history("fr", apx)
    except Exception as _e:
        print(f"WARN: fr decision-history capture failed ({_e})")
    track_in = [{**p, "conviction": p.get("fr_score", 0)} for p in picks]   # fr_score -> conviction log
    # PRICE-COVERAGE CHECK: off-scan members (most miners) price via the _current_prices FMP fallback
    scan = gcs_io.gcs_read_json("scans/latest_global.json") or {}
    scan_syms = {s.get("symbol") for s in scan.get("stocks", []) if s.get("symbol")}
    off_scan = [p["symbol"] for p in picks if p["symbol"] not in scan_syms]
    print(f"off-scan members (FMP-quote fallback will price them): {off_scan}")
    try:
        dt = E._update_apex_tracking(track_in, push_gcs=False,
                                     gcs_path="scans/speculair_future_resources_tracking.json",
                                     local_name="speculair_future_resources_tracking.json")
    except Exception as e:
        print(f"WARN: fr tracking failed ({e})")
        dt = {}
    dtw = {}
    if weights:
        try:
            dtw = E._update_apex_tracking(track_in, push_gcs=False, weights=weights,
                                          gcs_path="scans/speculair_future_resources_tracking_weighted.json",
                                          local_name="speculair_future_resources_tracking_weighted.json")
        except Exception as e:
            print(f"WARN: weighted fr tracking failed ({e})")
    pos = {}
    tp = PUB / "speculair_future_resources_tracking.json"
    if tp.exists():
        try:
            pos = json.load(open(tp, encoding="utf-8")).get("positions", {})
        except Exception:
            pos = {}
    for p in picks:                                   # attach entry for per-pick perf in the card
        pp = pos.get(p["symbol"], {})
        if pp:
            p["entry_price"] = pp.get("entry_price")
            p["entry_date"] = pp.get("entry_date")
    # honest pool-quality banner (spec §7 text — Lane A NAV steps weekly, Lane B is a tracker)
    uni = {}
    if (FR_DIR / "universe.json").exists():
        try:
            uni = json.load(open(FR_DIR / "universe.json", encoding="utf-8"))
        except Exception:
            uni = {}
    taxonomy_version = uni.get("taxonomy_version") or apx.get("taxonomy_version") or "1.3"
    n_debated = None
    pool_stats = {}
    gp = FR_DIR / "fr_grade_input.json"
    if gp.exists():
        try:
            from collections import Counter as _C
            gin = json.load(open(gp, encoding="utf-8"))
            n_debated = len(gin)
            vc = _C((x.get("debate_verdict") or "?") for x in gin)
            regs = _C((x.get("chain_regime_worst") or "?") for x in gin)
            pool_stats = {
                "n_pool": len(gin), "verdict_counts": dict(vc), "chain_regime_counts": dict(regs),
                "taxonomy_version": taxonomy_version,
                "banner": ("Commodity-cyclical sleeve. Lane A NAV steps weekly until the nightly mark ships. "
                           "Lane B is an event tracker, not a NAV. US-listed names only — much developer "
                           "alpha lists on TSX/ASX and is out of scope. Never blended with any other book.")}
        except Exception:
            pool_stats = {}
    # XME/URA BENCHMARK LINE (disruptor SMH/QQQ precedent, benchmarks swapped to the chain betas):
    # anchors persist in a SIDECAR, measured from first-stamp forward — no back-fill. NOT the
    # tracking file: _update_apex_tracking rebuilds that file from a fresh state dict earlier in
    # THIS function, so an anchor stored there is wiped and re-stamped at today's prices on every
    # publish (benchmark pinned at ~0% forever). The book return comes from the RETURNED tracking
    # summary — the state file carries nav/positions/history but never since_inception_pct.
    bench = {}
    try:
        anch_f = FR_DIR / "_benchmark_anchors.json"
        _bpx = E._current_prices({"XME", "URA"})
        _anch = None
        if anch_f.exists():
            try:
                _anch = json.load(open(anch_f, encoding="utf-8"))
            except Exception:
                _anch = None
        if not _anch and _bpx.get("XME") and _bpx.get("URA"):
            _anch = {"XME": _bpx["XME"], "URA": _bpx["URA"], "date": _dt.date.today().isoformat()}
            anch_f.write_text(json.dumps(_anch, indent=2), encoding="utf-8")
            print(f"benchmark anchors stamped (measured from {_anch['date']} forward): XME {_anch['XME']} URA {_anch['URA']}")
        if _anch and _bpx.get("XME") and _bpx.get("URA"):
            _bret = 50 * (_bpx["XME"] / _anch["XME"] - 1) + 50 * (_bpx["URA"] / _anch["URA"] - 1)
            _book = dt.get("since_inception_pct")
            bench = {"blend": "50/50 XME+URA", "measured_from": _anch.get("date"),
                     "benchmark_return_pct": round(_bret, 2),
                     "active_return_pct": round(_book - _bret, 2) if isinstance(_book, (int, float)) else None}
            print(f"benchmark: 50/50 XME+URA {_bret:+.2f}% since {_anch.get('date')} | book "
                  f"{_book if _book is not None else '?'}% | ACTIVE {bench['active_return_pct']}%")
    except Exception as _e:
        print(f"WARN: benchmark line failed ({_e})")
    out = {"apex_basket": picks, "runner_ups": apx.get("runner_ups", []),
           "fr_memo": apx.get("fr_memo", ""),
           "fr_tracking": dt, "fr_tracking_weighted": dtw, "weights": weights,
           "stress_test": apx.get("stress_test"), "correlation": apx.get("correlation"),
           "exits": apx.get("exits"), "combined_caps": apx.get("combined_caps"),
           "chain_caps": apx.get("chain_caps"), "chain_exposure": apx.get("chain_exposure"),
           "pool_stats": pool_stats, "benchmark": bench,
           "generated_at": _dt.date.today().isoformat(),
           "engine": "opus-4.8-future-resources-lane-a-v1", "universe": n_debated,
           "taxonomy_version": taxonomy_version}
    (PUB / "speculair_future_resources.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"fr_publish: {len(picks)} apex + {len(out['runner_ups'])} runners | tracking nav={dt.get('nav')} "
          f"since={dt.get('since_inception_pct')}% open={dt.get('n_open')} closed={dt.get('n_closed')} inception={dt.get('inception_date')}")
    if push_gcs:
        import subprocess
        files = [(PUB / "speculair_future_resources.json", "scans/speculair_future_resources.json"),
                 (PUB / "speculair_future_resources_tracking.json", "scans/speculair_future_resources_tracking.json"),
                 (PUB / "speculair_future_resources_tracking_weighted.json", "scans/speculair_future_resources_tracking_weighted.json")]
        failed = []
        for localf, key in files:
            if not localf.exists():
                continue
            ok = False
            for attempt in (1, 2):                     # Do-NOT #10: one retry, then report and stop
                try:
                    r = subprocess.run(f'gcloud storage cp "{localf}" "gs://screener-signals-carbonbridge/{key}"',
                                       shell=True, capture_output=True, text=True, timeout=120)
                    ok = (r.returncode == 0)
                    print(f"  GCS push {key} (attempt {attempt}): {'OK' if ok else 'FAILED ' + (r.stderr or '')[-140:]}")
                except Exception as e:
                    print(f"  GCS push {key} (attempt {attempt}) ERR: {e}")
                if ok:
                    break
            if not ok:
                failed.append(key)
        if failed:
            print(f"GUARD fr publish: GCS push FAILED after one retry for {failed} — report and stop "
                  f"(the local payload is staged; other books unaffected).")
            sys.exit(1)
        # LIVE readback (the public URL can serve a stale cache right after a write)
        try:
            rb = subprocess.run('gcloud storage cat "gs://screener-signals-carbonbridge/scans/speculair_future_resources.json"',
                                shell=True, capture_output=True, text=True, timeout=120)
            if rb.returncode == 0:
                back = json.loads(rb.stdout)
                live_syms = [p.get("symbol") for p in back.get("apex_basket", []) if isinstance(p, dict)]
                print(f"  GCS LIVE readback: {len(live_syms)} apex symbols {live_syms}")
            else:
                print(f"  GCS LIVE readback FAILED: {(rb.stderr or '')[-140:]}")
        except Exception as e:
            print(f"  GCS LIVE readback ERR: {e}")
    return len(picks)


def fr_numeric_gate():
    """Run the shared numeric-integrity gate over the FR results subtree (the run() res_dir injection
    point — _numeric_gate.py itself is NOT edited). FR records carry the typed valuation block from
    day one, so --legacy is unnecessary but accepted. Flags passthrough: --dry-run/--enforce/--final/
    --offline/--symbol <SYM>."""
    sys.path.insert(0, os.path.join(BK, "_opus_debate"))
    import _numeric_gate as NG
    only = None
    if "--symbol" in sys.argv:
        try:
            only = sys.argv[sys.argv.index("--symbol") + 1]
        except IndexError:
            only = None
    dry = "--dry-run" in sys.argv
    enforce = "--enforce" in sys.argv
    if dry == enforce:
        print("fr-numeric-gate: pass exactly one of --dry-run (report only) or --enforce (stamp records).")
        sys.exit(1)
    NG.run(dry_run=dry, legacy=("--legacy" in sys.argv), only_symbol=only,
           offline=("--offline" in sys.argv), enforce=enforce, final=("--final" in sys.argv),
           res_dir=FR_RES)


# ── FR Lane A debate workflow template (disruptor-template clone; FR BRIEF; chain_map + §3 metrics
#    in the bundle; typed valuation block [pipeline-v3 step 6b/7] emitted from day one so
#    _numeric_gate works on FR records; BATCH=8; NO in-workflow Director — fr-input builds the grade
#    input AFTER the debates, then ONE Director agent grades it; NO skeptic tier for Lane A (§5)). ──
_FR_WORKFLOW_TEMPLATE = r"""export const meta = {
  name: 'speculair-future-resources-weekly',
  description: 'Weekly Future Resources Lane A debate (producers/royalties/toll-takers; chain map already produced competitors). Director runs separately after fr-input.',
  phases: [{ title: 'Debate', model: '__DEBATE_MODEL__' }],
}
const DIR = 'backend/_opus_debate/future_resources'
const RES = DIR + '/results'
const SYMS = __SYMS__               // have a bundled FMP transcript (read local file)
const ONLINE_SYMS = __ONLINE_SYMS__ // no FMP transcript — agent fetches the latest one online

// ── PHASE 1 — DEBATE: Interrogator -> Architect (bull/bear + Sum-of-Parts) -> web verification -> CRO. ──
// No Radar phase: the monthly chain map already produced true competitors. All names run as
// general-purpose agents so EVERY name (FMP + online) can web-verify its cost/contract facts.
function debatePrompt(sym, online) {
  const BRIEF = 'Read ' + DIR + '/chain_map/' + sym + '.json — this name has an assigned chain(s), business_model, physical anchor, value-chain position, commodity_revenue_share and true competitors. Its input bundle carries a resource_metrics block (deterministic cost-curve/torque proxies: ebitda_margin_ttm + cohort band, fcf_torque_10pct, commodity_beta_2y, ndebt_ebitda; or the non-commodity set gm_trajectory/rev_yoy/fcf_margin for robotics/quantum) and a chain_regime block (per-chain TAILWIND/NEUTRAL/HEADWIND from the regime sidecar). This is a RESOURCES LANE-A debate, not a catalyst debate: judge (1) COST-CURVE POSITION — the metrics are honest PROXIES; web-verify against company-reported AISC / unit-cost guidance where published, and SAY EXPLICITLY when the proxy and the company-reported figure disagree; (2) CONTRACTING and RESERVE LIFE — the contract book vs spot exposure, reserve/resource life with numbers, NAMED offtake counterparties (an MoU is not a contract); (3) CAPITAL DISCIPLINE — the sector besetting sin: capex history through the LAST cycle, buyback/dividend behavior at the top; (4) THE REGIME — read FUTURE_RESOURCES_REGIME.md (repo root) for this name chain section and apply the cycle read. A live catalyst is neither a plus nor a requirement (Lane B owns catalysts). TORQUE IS SYMMETRIC: the bear case MUST price the downside torque with the number (the same fcf_torque_10pct cuts both ways on a -10% move), not just assert commodity risk.'
  const step1 = online
    ? '1. Read ' + DIR + '/inputs/' + sym + '.json (fields metrics_str/sector/signal_type/company + chains/business_model/physical_anchor/commodity_revenue_share/chain_regime/resource_metrics/gates; metrics may include a SEGMENT REVENUE block). NO FMP transcript is bundled. FIRST try the paid FMP MCP tools via ToolSearch (keyword search e.g. "FMP earnings transcript", "FMP statements", "FMP news") for ' + sym + ' and its MOST RECENT earnings-call transcript and quarterly numbers; if FMP has nothing for this ticker, THEN use WebSearch + WebFetch to find the latest transcript / quarterly results / earnings release / management commentary / investor presentation (IR site, Tikr, Seeking Alpha, Investing.com, MarketScreener, plus the latest regulatory filing) — do NOT scrape press-release PDFs by shell. If genuinely nothing is findable, say so and reason from the fundamentals — never fabricate quotes or figures.\n'
    : '1. Read ' + DIR + '/inputs/' + sym + '.json (fields metrics_str/sector/signal_type + chains/business_model/physical_anchor/commodity_revenue_share/chain_regime/resource_metrics/gates; metrics may include a SEGMENT REVENUE block) and ' + DIR + '/transcripts/' + sym + '.txt.\n'
  return 'You run the COMPLETE multi-agent debate for ' + sym + ' as Claude Opus 4.8 — Interrogator, Architect, then CRO/Moderator — allocating REAL capital to a FUTURE RESOURCES Lane A name (profitable producer / royalty / equipment toll-taker in a physical value chain). Be skeptical and current-facts-driven; mining is where promoters live.\n' +
    step1 +
    '1b. LIVE PRICE (MANDATORY, BEFORE any valuation reasoning): if the metrics block does not state a current price, you MUST fetch the live quote via the FMP MCP tools (ToolSearch, keyword "FMP quote") and state the price + currency you are using. NEVER assume or infer where the stock trades — a fabricated price inverts the entire risk/reward. For dual-listed names state WHICH listing/currency your numbers are in.\n' +
    '2. INTERROGATOR: read ' + DIR + '/interrogator_system.txt; produce the full forensic dossier (8 sections + final "CREDIBILITY_SCORE: <1-5> | TRAJECTORY: <...>"); pay special attention to serial-diluter financing patterns, reserve-report inflation, and promoter language — the sector kill list. Write it to ' + DIR + '/dossiers/' + sym + '.md.\n' +
    '3. PEER COMPS: read ' + DIR + '/chain_map/' + sym + '.json (this name has assigned chain(s), value_chain_position and true_competitors) as the relative-value lever for the valuation below (skip if the file is absent).\n' +
    '4. ARCHITECT: read ' + DIR + '/architect_system.txt; produce bull_thesis and bear_thesis, AND a SUM-OF-PARTS valuation — value the business by its PARTS (segment SoP from the SEGMENT REVENUE block x peer multiples where present; else whole-company intrinsic via peer multiple / NAV where reserves support one), then apply overlays (net cash, announced asset-sales, streaming/royalty portfolios valued separately). The bear case MUST price the DOWNSIDE TORQUE with the number (a -10% commodity move through fcf_torque_10pct), not just assert commodity risk. Output sop_bull (favorable parts) and sop_bear (adverse parts, ASSUMING THE CHAIN REGIME TURNS AGAINST IT), each a per-share value + the parts breakdown.\n' +
    '5. COST/CONTRACT VERIFICATION (web, MANDATORY): identify the load-bearing cost-curve and contract facts (company-reported AISC or unit-cost guidance, contracted volumes and realized-price mechanics, reserve life, named offtakers) and verify their CURRENT status as of today — FIRST the paid FMP MCP tools via ToolSearch ("FMP statements", "FMP news", "FMP earnings transcript"), then WebSearch/WebFetch for what FMP lacks. Where the deterministic proxy metrics DISAGREE with company-reported figures, say so explicitly. Also emit catalyst_status = FIRED | ARB | PENDING_HARD | SOFT_EXTENDED | UNVERIFIABLE for the record (it must NOT drive the verdict — Lane B owns catalysts). Dated evidence; never fabricate — a spot price without a source does not appear.\n' +
    '6. CRO/MODERATOR: read ' + DIR + '/moderator_system.txt; ' + BRIEF + ' RECONCILE sop_bull/sop_bear into a base-case sop_fair_value (+ sop_breakdown) and risk_reward (downside-to-break vs upside-to-fair); judge the cost-curve position vs the verified figures; sanity-check the multiple against the chain_map true_competitors. Produce verdict (A/B/C), conviction (int 1-5), consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion. THEN, separately, value_conviction (int 1-5): the value case judged on valuation vs the SoP fair value + forensic quality ONLY. The two scores MUST be allowed to diverge.\n' +
    '6b. TYPED VALUATION BLOCK (MANDATORY — the numbers the pipeline checks and sizes on): distill your reconciliation into POINT NUMBERS per share, in the quote currency: bear_px (your adverse case — ONE number; your ranges stay in the prose), base_fv_px (base case), bull_px (favorable case), downside_floor_px (ONLY a structural floor — deal terms, net cash/share, tender; else null — a chart low or a dividend yield is NOT a floor), valuation_method ("sop"|"multiple"|"spread"|"recovery"), horizon_months (when the base case lands). ORDERING bear_px <= base_fv_px <= bull_px is REQUIRED. State LEVELS only: risk_reward ratios, expected-return %, and MoS % are COMPUTED BY THE PIPELINE from these numbers — any "N:1" or %-vs-% arithmetic you assert in prose will be overwritten by the computed values.\n' +
    '7. Write (Write tool) VALID, escaped JSON to ' + RES + '/' + sym + '.json with: symbol(="' + sym + '"), sector, signal_type(="future_resources"), chains(array, from chain_map), business_model, value_chain_position, live_price(number — the price you actually used), price_currency, valuation({live_price, price_currency, quote_listing(="' + sym + '"), bear_px, base_fv_px, bull_px, downside_floor_px, valuation_method, horizon_months, as_of(today YYYY-MM-DD)} — the step-6b numbers), cost_curve_verified(one line: proxy vs company-reported figure, agree/disagree), bull_thesis, bear_thesis, sop_bull, sop_bear, sop_fair_value, sop_breakdown, risk_reward, catalyst_status, peer_comps_note, verdict, conviction, value_conviction(int), consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion, interrogator_score(int), trajectory, source(="' + (online ? 'opus_fr_online' : 'opus_fr_mod') + '"), transcript_source(="' + (online ? 'web' : 'fmp') + '").\n' +
    'Reply exactly: DONE'
}

const ALL = SYMS.map(s => ({ sym: s, online: false }))
  .concat(ONLINE_SYMS.map(s => ({ sym: s, online: true })))
log(`Future Resources Lane A debate over ${ALL.length} names (${SYMS.length} FMP + ${ONLINE_SYMS.length} online-fetch); Director runs separately after fr-input.`)
phase('Debate')
const BATCH = 8   // rate-limit safety: run 8 web-heavy agents at a time (429s).
for (let b = 0; b < ALL.length; b += BATCH) {
  log(`Debate batch ${Math.floor(b / BATCH) + 1}/${Math.ceil(ALL.length / BATCH)} (names ${b + 1}-${Math.min(b + BATCH, ALL.length)} of ${ALL.length})`)
  await parallel(ALL.slice(b, b + BATCH).map(it => () => agent(
    debatePrompt(it.sym, it.online),
    { label: 'fr:' + it.sym + (it.online ? '(web)' : ''), phase: 'Debate', agentType: 'general-purpose', model: '__DEBATE_MODEL__' })))
}
// NO in-workflow Director: the Director grades fr_grade_input.json, which `fr-input` builds from
// THESE debate results AFTER this workflow (sequence: Workflow -> fr-numeric-gate --enforce ->
// fr-input -> Director agent -> fr-post). NO skeptic tier for Lane A (spec §5). Debate-only.
log('Future Resources debate complete (Director runs separately after fr-input).')
return 'DONE'
"""


def export_debate_csv():
    """Write a CSV of every debated name in results_regime/ with the FULL output of every agent in the
    chain — Radar (peer_groups), Interrogator (dossier+score+trajectory), Architect (bull/bear+SoP),
    Catalyst verification (catalyst_status), CRO/Moderator (verdict/conviction/SoP reconcile/etc.), and
    the Director's per-name assessment — plus a companion director_memo .txt. UTF-8 BOM for Excel."""
    import csv
    res_dir, doss_dir, pg_dir = ROOT / "results_regime", ROOT / "dossiers", ROOT / "peer_groups"
    apex = {}
    apx = ROOT / "apex_basket_opus_regime.json"
    if apx.exists():
        try:
            apex = json.load(open(apx, encoding="utf-8"))
        except Exception:
            apex = {}
    director = {}
    for p in apex.get("apex_basket", []):
        if isinstance(p, dict) and p.get("symbol"):
            director[p["symbol"]] = {**p, "_role": "APEX"}
    for p in apex.get("runner_ups", []):
        if isinstance(p, dict) and p.get("symbol"):
            director[p["symbol"]] = {**p, "_role": "RUNNER_UP"}
        elif isinstance(p, str):
            director[p] = {"_role": "RUNNER_UP"}
    cols = ["symbol", "sector", "signal_type", "source", "transcript_source",
            "verdict", "conviction", "catalyst_status", "sop_fair_value", "risk_reward",
            "trajectory", "interrogator_score",
            "director_role", "director_conviction", "director_thesis", "director_lane",
            "director_regime_fit", "director_exposure_axes",
            "radar_verdict", "radar_peers", "radar_relative_comps", "radar_rationale",
            "bull_thesis", "bear_thesis", "sop_bull", "sop_bear", "sop_breakdown",
            "consensus_delta", "valley_of_death", "positioning_washout", "forcing_function",
            "moderator_conclusion", "peer_comps_note", "interrogator_dossier"]
    rows = []
    for f in sorted(res_dir.glob("*.json")):
        try:
            r = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        sym = r.get("symbol") or f.stem
        doss = ""
        if (doss_dir / f"{sym}.md").exists():
            doss = (doss_dir / f"{sym}.md").read_text(encoding="utf-8")
        pg = {}
        if (pg_dir / f"{sym}.json").exists():
            try:
                pg = json.load(open(pg_dir / f"{sym}.json", encoding="utf-8"))
            except Exception:
                pg = {}
        dd = director.get(sym, {})
        rows.append({
            "symbol": sym, "sector": r.get("sector", ""), "signal_type": r.get("signal_type", ""),
            "source": r.get("source", ""), "transcript_source": r.get("transcript_source", ""),
            "verdict": r.get("verdict", ""), "conviction": r.get("conviction", ""),
            "catalyst_status": r.get("catalyst_status", ""), "sop_fair_value": r.get("sop_fair_value", ""),
            "risk_reward": r.get("risk_reward", ""), "trajectory": r.get("trajectory", ""),
            "interrogator_score": r.get("interrogator_score", ""),
            "director_role": dd.get("_role", ""), "director_conviction": dd.get("director_conviction", ""),
            "director_thesis": dd.get("thesis", ""), "director_lane": dd.get("lane", ""),
            "director_regime_fit": dd.get("regime_fit", ""),
            "director_exposure_axes": json.dumps(dd.get("exposure_axes", ""), ensure_ascii=False) if isinstance(dd.get("exposure_axes"), (list, dict)) else dd.get("exposure_axes", ""),
            "radar_verdict": pg.get("verdict", ""),
            "radar_peers": ", ".join(pg.get("peers", [])) if isinstance(pg.get("peers"), list) else "",
            "radar_relative_comps": pg.get("relative_comps", ""), "radar_rationale": pg.get("rationale", ""),
            "bull_thesis": r.get("bull_thesis", ""), "bear_thesis": r.get("bear_thesis", ""),
            "sop_bull": r.get("sop_bull", ""), "sop_bear": r.get("sop_bear", ""),
            "sop_breakdown": r.get("sop_breakdown", ""), "consensus_delta": r.get("consensus_delta", ""),
            "valley_of_death": r.get("valley_of_death", ""), "positioning_washout": r.get("positioning_washout", ""),
            "forcing_function": r.get("forcing_function", ""), "moderator_conclusion": r.get("moderator_conclusion", ""),
            "peer_comps_note": r.get("peer_comps_note", ""), "interrogator_dossier": doss,
        })
    out = ROOT / "speculair_debate_66.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    (ROOT / "speculair_debate_66_director_memo.txt").write_text(apex.get("director_memo", ""), encoding="utf-8")
    print(f"wrote {len(rows)} rows x {len(cols)} cols -> {out}")
    print(f"director_memo -> {ROOT / 'speculair_debate_66_director_memo.txt'}")
    return len(rows)


# ── CHANGE-DETECTION CARRY-FORWARD (2026-07-01, methodology review OPS-P2) ───────────────────
# ~149 full Opus debates/week mostly re-derive unchanged conclusions (the run needs 2-3 resume
# cycles). Re-debate a name ONLY when something debate-relevant changed; otherwise CARRY the prior
# record forward with a deterministic freshness restamp. The money-bearing layers stay weekly:
# finalists (apex + runners, both books) ALWAYS re-debate, and both skeptic kill-tiers run fresh.
CARRY_MAX_AGE_D = 21          # hard staleness ceiling (synthesis tightened the audit's 28d)
CARRY_PRICE_MOVE = 0.10       # |move| beyond this since the prior debate -> re-debate


FULL_REFRESH_D = 91           # T4: a seat gets a full re-underwrite at least quarterly (last_full_debate)


def _carry_or_debate(sym, sc, real_tx, prior_dir, seat_relevant):
    """Return ("debate", reason, prior_record_or_None) or ("carry", reason, prior_record).
    The prior record rides along on the DEBATE branch too (2026-07-08 continuity fix) so prep can
    embed it in the input bundle — a re-debated name must know what it said last week.
    2026-07-10 (two-tier, Week 2): seat-relevant names NO LONGER short-circuit — the gate keeps
    evaluating the REAL triggers first, so prep can route: seat WITH a trigger -> FULL re-debate;
    seat with NO trigger -> reason "seat-relevant-only" -> DELTA mode (anchored weekly update — the
    fix for the memoryless-re-roll churn the 2026-07-07 forensics identified). Non-seat behavior is
    unchanged (trigger -> debate, no trigger -> carry). Deterministic; fail-open to debate."""
    if os.environ.get("FORCE_FULL_DEBATE"):
        return "debate", "FORCE_FULL_DEBATE", None
    pf = prior_dir / f"{sym}.json"
    if not pf.exists():
        return "debate", "new to universe", None
    try:
        pr = json.load(open(pf, encoding="utf-8"))
    except Exception:
        return "debate", "prior record unreadable", None
    is_seat = sym in seat_relevant
    cs = (pr.get("catalyst_status") or "").upper()
    if cs.startswith("PENDING_HARD"):
        return "debate", "prior catalyst PENDING_HARD (dated events move weekly)", pr
    # T6 — an escalation raised last cycle (a delta agent that wanted to flip the verdict, or a
    # coverage refresh that found something material) forces the full debate it asked for.
    if pr.get("escalate_full_debate") or (pr.get("coverage_update") or {}).get("escalate"):
        return "debate", "escalated last cycle (delta/coverage flagged a material change)", pr
    # age ceiling: prior debated_at (fallback: file mtime)
    import time as _t
    age_d = None
    da = pr.get("debated_at") or pr.get("date")
    if da:
        try:
            age_d = ( _t.time() - datetime.fromisoformat(str(da)[:19]).timestamp() ) / 86400
        except Exception:
            age_d = None
    if age_d is None:
        age_d = (_t.time() - pf.stat().st_mtime) / 86400
    if age_d > CARRY_MAX_AGE_D:
        return "debate", f"record {age_d:.0f}d old (> {CARRY_MAX_AGE_D}d ceiling)", pr
    # T4 — quarterly full refresh for seats: delta mode restamps the record weekly so the age ceiling
    # never fires on a held name; last_full_debate (stamped by every FULL underwrite) is the honest
    # age of the actual thesis work. Absent on pre-two-tier records -> skipped gracefully (the first
    # full debate under the new schema starts the clock).
    lfd = pr.get("last_full_debate")
    if is_seat and lfd:
        try:
            lfd_age = (_t.time() - datetime.fromisoformat(str(lfd)[:19]).timestamp()) / 86400
            if lfd_age > FULL_REFRESH_D:
                return "debate", f"quarterly full refresh (last full underwrite {lfd_age:.0f}d ago)", pr
        except Exception:
            pass
    # new transcript since the prior debate. FIX 2026-07-11 (first tier-select run: seats-delta=0):
    # prior records never carry transcript_date (the debate schema doesn't write it), so the old
    # `latest > prior_tx=""` comparison fired for EVERY name with any transcript at all — spurious
    # full re-debates that defeated delta mode on its maiden run. Correct semantic: a transcript is
    # only NEW if it postdates the prior DEBATE — the prior debate already read anything older.
    if real_tx:
        latest = max((t.get("date") or "") for t in real_tx)
        prior_ref = str(pr.get("transcript_date") or "")[:10] \
            or str(pr.get("debated_at") or pr.get("as_of") or pr.get("date") or "")[:10] \
            or str((pr.get("valuation") or {}).get("as_of") or "")[:10]
        if not prior_ref:
            # pre-two-tier records carry NO date field at all — the file mtime is when the record
            # was written, and the prior debate had access to anything published before then
            prior_ref = datetime.fromtimestamp(pf.stat().st_mtime).strftime("%Y-%m-%d")
        if latest and prior_ref and latest > prior_ref:
            return "debate", f"new transcript {latest} (prior debate {prior_ref})", pr
    # price move vs the price the prior debate saw
    now_px = sc.get("price")
    old_px = pr.get("price") or pr.get("current_price") or pr.get("live_price") or pr.get("entry_price")
    if isinstance(now_px, (int, float)) and isinstance(old_px, (int, float)) and old_px > 0:
        mv = abs(now_px / old_px - 1)
        if mv > CARRY_PRICE_MOVE:
            return "debate", f"price moved {mv * 100:.0f}% (> {CARRY_PRICE_MOVE * 100:.0f}%)", pr
    if is_seat:
        return "debate", "seat-relevant-only", pr    # no real trigger -> DELTA mode under tiering
    return "carry", "no debate-relevant change", pr


def prep():
    E.load_api_keys()
    # SELF-CLEAN (2026-06-06): archive the PRIOR run's debate outputs so the Director only ever sees
    # ONE coherent debate pass. Mixing vintages (today's post-fix debates + last week's, built on
    # different metrics/universe) let stale or data-quality-contaminated theses win apex slots. Keeps
    # the previous run in _opus_debate/_archive_prev/ for one cycle (apex-rotation comparison), then
    # overwrites. The workflow-resume retry path does NOT call prep, so a mid-run re-invoke is safe.
    import shutil
    # PARTIAL-RUN GUARD (2026-07-01): a crash-then-re-prep used to overwrite _archive_prev (the last
    # GOOD week) with the crashed run's partial shards — both observed incidents (06-21, 06-28) would
    # have destroyed the good context on restart. A run only counts as COMPLETED when its apex JSON
    # exists alongside results_regime/; a partial tree goes to _archive_partial_<n>/ (capped at 2,
    # oldest pruned) and _archive_prev is left UNTOUCHED.
    apx = ROOT / "apex_basket_opus_regime.json"
    res = ROOT / "results_regime"
    has_results = res.exists() and any(res.iterdir())
    completed = has_results and apx.exists()
    if has_results and not completed:
        partials = sorted(ROOT.glob("_archive_partial_*"))
        for old in partials[:-1]:                      # keep at most 1 prior partial + this new one
            shutil.rmtree(old, ignore_errors=True)
        n = 1 + max([int(p.name.rsplit("_", 1)[-1]) for p in partials if p.name.rsplit("_", 1)[-1].isdigit()] or [0])
        arch = ROOT / f"_archive_partial_{n}"
        arch.mkdir(parents=True, exist_ok=True)
        print(f"prep self-clean: PARTIAL prior run (results present, apex missing) -> {arch.name}; "
              f"_archive_prev (last completed run) left untouched.")
    else:
        arch = ROOT / "_archive_prev"
        if arch.exists() and completed:
            shutil.rmtree(arch, ignore_errors=True)
        arch.mkdir(parents=True, exist_ok=True)
        if completed:
            print("prep self-clean: prior run COMPLETED -> archived to _archive_prev.")
    for sub in ("results_regime", "dossiers"):
        src = ROOT / sub
        if src.exists() and any(src.iterdir()):
            shutil.move(str(src), str(arch / sub))
        (ROOT / sub).mkdir(parents=True, exist_ok=True)
    if apx.exists():
        shutil.move(str(apx), str(arch / "apex_basket_opus_regime.json"))
    print(f"archived prior debate outputs -> {arch}")

    # PRIMARY SOURCE: the raw 11-methodology production screen (methodology_picks.json) — the
    # FULL opportunity set, re-read every week. Sourcing from the *curated* speculair_baskets.json
    # instead created a SHRINK LOOP: each run only re-debated last week's survivors, so the universe
    # degenerated over time (observed 2026-06-06: 8 methodologies, 15 names, apex=1 after a partial
    # 01:03 write). The raw screen breaks that loop. We still UNION-in the current apex (held names)
    # so a live position is never dropped just because it aged out of the raw screen.
    mp = gcs_io.gcs_read_json("scans/methodology_picks.json") or {}
    meth_src = mp.get("methodologies", {})
    print(f"raw screen methodology_picks.json: last_updated={mp.get('last_updated')} "
          f"methodologies={len(meth_src)}")
    sym_meths = {}
    for meth, b in meth_src.items():
        for p in (b.get("picks", b) if isinstance(b, dict) else b) or []:
            if isinstance(p, dict) and p.get("symbol"):
                sym_meths.setdefault(p["symbol"], []).append(meth)
    baskets = gcs_io.gcs_read_json("scans/speculair_baskets.json") or {}
    # Fallback: if the raw screen is unexpectedly thin, also fold in the curated baskets so a
    # transient screen problem can't starve the debate.
    if len(sym_meths) < 40:
        print(f"WARN: raw screen only yielded {len(sym_meths)} names — folding in curated baskets")
        for meth, b in baskets.get("per_methodology_baskets", {}).items():
            for p in (b.get("picks", b) if isinstance(b, dict) else b) or []:
                if isinstance(p, dict) and p.get("symbol"):
                    sym_meths.setdefault(p["symbol"], []).append(meth)
    for p in baskets.get("apex_basket", []):
        if p.get("symbol"):
            sym_meths.setdefault(p["symbol"], []).append("apex")

    scan = gcs_io.gcs_read_json("scans/latest_global.json") or json.load(
        open("../frontend/public/latest_global.json", encoding="utf-8"))
    scan_by_sym = {s.get("symbol"): s for s in scan.get("stocks", []) if s.get("symbol")}

    # ── VALUE DRAWDOWN INTAKE (2026-07-01, methodology review VB-P3 / SB#10) ────────────────────
    # The value book re-weights a priced-quality pool that (proven) contains no value alpha; the
    # evidence says the return lives in a DIFFERENTLY-COMPOSED funnel. Union a deterministic
    # quality-in-drawdown slice: positive FCF margin + (ROIC>=8% or quality>=0.55) + >=5y history,
    # trading >=25% off the 1y high AND in the bottom 15% of the 52w range (the scan's horizon —
    # the audit wanted 2y; 1y is what the scan carries, stated honestly). Hard cap 20/week in CODE
    # (red-team condition). Most weeks 0-3 names; a sector de-rate transforms the book — by design.
    VD_CAP = 20
    _vd = []
    for _s0 in scan.get("stocks", []):
        _sym0, _px, _yh = _s0.get("symbol"), _s0.get("price"), _s0.get("year_high")
        if not _sym0 or _sym0 in sym_meths:
            continue
        if not (isinstance(_px, (int, float)) and isinstance(_yh, (int, float)) and _yh > 0):
            continue
        _dd = _px / _yh - 1
        if _dd > -0.25:
            continue
        _prox = _s0.get("proximity_52wk")
        if not (isinstance(_prox, (int, float)) and _prox <= 0.15):
            continue
        _fm, _q, _roic = _s0.get("fcf_margin"), _s0.get("quality_score"), _s0.get("roic_avg")
        if not (isinstance(_fm, (int, float)) and _fm > 0):
            continue
        if not ((isinstance(_roic, (int, float)) and _roic >= 0.08)
                or (isinstance(_q, (int, float)) and _q >= 0.55)):
            continue
        if (_s0.get("years_history") or 0) < 5:
            continue
        _vd.append((_dd, -(_q or 0), _sym0))
    _vd.sort()                                            # deepest drawdown first, quality tiebreak
    _vd_syms = [t[2] for t in _vd[:VD_CAP]]
    for _sym0 in _vd_syms:
        sym_meths.setdefault(_sym0, []).append("value_drawdown")
    if _vd_syms:
        print(f"value-drawdown intake: {len(_vd_syms)} quality-in-drawdown names (cap {VD_CAP}): {_vd_syms}")
    else:
        print("value-drawdown intake: 0 qualified (no quality names >=25% down at the range bottom this week)")

    # ── NEGLECT-ORPHAN INTAKE (2026-07-17, funnel-gap fix) ──────────────────────────────────────
    # The 12 methodology screens rank on REPORTED fundamentals and the G2a gate (correctly) drops
    # structural breaks from the earnings baskets — so the neglect archetype (a recent spin/IPO
    # orphan with IFRS-5-noised headlines, a resolved B13 event name the crowd abandoned, or a
    # zero-coverage US business) had literally NEVER reached the debate: 0 of 366 input bundles
    # carried structural_break before this lane. The lane bypasses the RANKINGS only — the
    # debate/interrogator does the underwriting the screens can't, and every downstream gate
    # (skeptic w/ its own neglect attack, numeric gate, forensics, moat teeth) applies in full.
    # Three deterministic sources, priority-ordered; hard cap in CODE on FRESH underwrites only
    # (already-debated lane names re-enter as ~free carries, so the backlog drains ~NG_CAP/week
    # and names graduate out as the orphan window closes or a methodology basket adopts them):
    #   1. resolved B13 seats (resolution_type FIRED_*, <=90d) — post-event orphans the system
    #      already knows; the value window opens exactly when the event crowd leaves;
    #   2. dated-IPO/spin orphans: structural_break with an ipo_YYYY-MM reason 6-18 months old,
    #      USD mcap $300M-$15B (megacaps are not neglected; share_count_jump reasons are
    #      buyback/split artifacts and deliberately NOT used), positive gross profit;
    #   3. US coverage deserts: target_analyst_count == 0 (zero PTs printed last quarter —
    #      None = the scan didn't measure it, SKIPPED never guessed; self-activates once the
    #      field serializes), real fundamentals, share-class tickers excluded ('-' suffix:
    #      BF-B-style false deserts where FMP tracks the other class).
    import re as _ng_re
    NG_CAP = 3
    _ng, _ng_seen = [], set()
    _now = datetime.now()

    def _ng_add(sym, prio, why):
        if sym and sym not in sym_meths and sym not in _ng_seen:
            _ng_seen.add(sym)
            _ng.append((prio, sym, why))

    try:  # 1. B13-resolution handoff
        _trk = json.load(open(ROOT.parent / "_basket13_tracker.json", encoding="utf-8"))
        for _e in _trk.get("entries", []):
            _r = _e.get("resolution") or {}
            if not str(_r.get("resolution_type") or "").startswith("FIRED"):
                continue
            try:
                _age_d = (_now - datetime.strptime(_r["resolution_date"], "%Y-%m-%d")).days
            except Exception:
                continue
            if 0 <= _age_d <= 90:
                _ng_add(_e.get("symbol"), (0, _age_d, 0), f"b13-resolved {_r.get('resolution_type')} {_age_d}d")
    except Exception as _e:
        print(f"WARN: neglect intake could not read the B13 tracker ({_e}) — handoff leg skipped")

    for _s0 in scan.get("stocks", []):  # 2. dated-IPO/spin orphans
        _sym0 = _s0.get("symbol")
        if not _sym0 or not _s0.get("structural_break"):
            continue
        _m = _ng_re.search(r"ipo_(\d{4})-(\d{2})$", str(_s0.get("structural_break_reason") or ""))
        if not _m:
            continue
        _age_mo = (_now.year - int(_m.group(1))) * 12 + (_now.month - int(_m.group(2)))
        if not (6 <= _age_mo <= 18):
            continue
        _mc_usd = (_s0.get("market_cap") or 0) * (_s0.get("fx_to_price") or 1)  # scan mcap is LOCAL ccy
        if not (300e6 <= _mc_usd <= 15e9):
            continue
        if (_s0.get("gross_profit") or 0) <= 0:
            continue
        _profitable = 1 if ((_s0.get("fcf_margin") or 0) > 0 or (_s0.get("piotroski") or 0) >= 5) else 0
        _ng_add(_sym0, (1, -_profitable, -_mc_usd), f"ipo-orphan {_age_mo}mo")

    for _s0 in scan.get("stocks", []):  # 3. US coverage deserts (inert until target_analyst_count ships)
        _sym0 = _s0.get("symbol")
        if not _sym0 or _s0.get("country") != "US" or "-" in _sym0:
            continue
        if _s0.get("target_analyst_count") != 0:
            continue
        _mc = _s0.get("market_cap") or 0
        if not (500e6 <= _mc <= 20e9):
            continue
        if not ((_s0.get("fcf_margin") or 0) > 0 and (_s0.get("piotroski") or 0) >= 5):
            continue
        _ng_add(_sym0, (2, -_mc, 0), "coverage-desert 0 PTs")

    _ng.sort()
    _ng_old = [t for t in _ng if (RES / f"{t[1]}.json").exists()]      # carries: ~free, no cap
    _ng_new = [t for t in _ng if not (RES / f"{t[1]}.json").exists()][:NG_CAP]
    for _prio, _sym0, _why in _ng_old + _ng_new:
        sym_meths.setdefault(_sym0, []).append("neglect_orphan")
    if _ng_old or _ng_new:
        print(f"neglect-orphan intake: {len(_ng_new)} fresh (cap {NG_CAP}, {len(_ng)} qualified) "
              f"+ {len(_ng_old)} carried: "
              + ", ".join(f"{s} [{w}]" for _, s, w in (_ng_new + _ng_old)))
    else:
        print("neglect-orphan intake: 0 qualified this week")

    # SEAT-RELEVANT finalists (apex + runners, BOTH books) always re-debate — the money layer stays weekly.
    seat_relevant = set()
    for p in list(baskets.get("apex_basket") or []) + list(baskets.get("runner_ups") or []):
        s = p.get("symbol") if isinstance(p, dict) else p
        if s:
            seat_relevant.add(s)
    _vb = gcs_io.gcs_read_json("scans/speculair_value_apex.json") or {}
    for p in list(_vb.get("apex") or _vb.get("apex_basket") or []) + list(_vb.get("runner_ups") or []):
        s = p.get("symbol") if isinstance(p, dict) else p
        if s:
            seat_relevant.add(s)
    prior_res_dir = ROOT / "_archive_prev" / "results_regime"
    prior_doss_dir = ROOT / "_archive_prev" / "dossiers"
    _carry_reasons = {}

    # ── TWO-TIER (2026-07-10, pipeline-v3 Week 2) ────────────────────────────────────────────────
    # SPECULAIR_TIERING=off restores the legacy single-tier flow (every debate name gets a full
    # Opus debate, no delta/coverage phases, skeptic stays a separate post-Director verb).
    tiering = os.environ.get("SPECULAIR_TIERING", "on").lower() != "off"
    # B13 SEPARATION at the tier level: names in the Basket-13 universe are underwritten in the
    # catalyst workflow under the event rubric — they never enter Tier-U here (the tier-selection
    # enforcement of the 2026-07-08 rule; the old catalyst-seed write collision is structurally
    # impossible when the name never debates in this lane at all).
    b13set = set()
    if tiering:
        try:
            b13set = {c.get("symbol") for c in _b13_universe() if c.get("symbol")}
        except Exception as _e:
            print(f"WARN: _b13_universe unreadable ({_e}) — no B13 tier exclusion this run")
    debate_info = {}                                  # sym -> {reason, seat, has_tx, prior_exists, meths}
    b13_carried, b13_skipped = [], []
    COV_UPD = ROOT / "_coverage_updates"
    COV_UPD.mkdir(parents=True, exist_ok=True)
    for _f in COV_UPD.glob("*.json"):                 # clear stale updates from the prior run
        try:
            _f.unlink()
        except OSError:
            pass

    syms, no_tx, radar_universe, carried, _no_price = [], [], [], [], []
    for sym in sorted(sym_meths):
        sc = scan_by_sym.get(sym, {})
        scan_fin = {k: sc.get(k) for k in E._SCAN_FIN_FIELDS if sc.get(k) is not None}
        bh = sc.get("buffett_history") or {}
        rows = bh.get("rows")
        if isinstance(rows, list) and rows:
            scan_fin["history_rows"] = [{"year": r.get("year"), "revenue_mm": r.get("revenue_mm"),
                                         "net_income_mm": r.get("net_income_mm"), "eps": r.get("eps")} for r in rows[-6:]]
            if isinstance(bh.get("cagrs"), dict):
                scan_fin["history_cagrs"] = bh["cagrs"]
        cand = {"symbol": sym, "sector": sc.get("sector", ""), "price": sc.get("price"),
                "fair_value": sc.get("buffett_fair_value"), "mos": sc.get("margin_of_safety")}
        try:
            metrics = E._build_debate_metrics(financials=cand, scan_fin=scan_fin)
        except Exception:
            metrics = "No financial metrics available."
        # TTM/latest-quarter override is now appended inside E._build_debate_metrics (_ttm_block),
        # so it applies to BOTH the production debate and this Opus prep — no duplicate needed here.
        metrics = (metrics or "") + _fmp_segments(sym)   # segment revenue for a true SoP (best-effort)
        meths = sym_meths[sym]
        # Structured row for the Radar peer-clustering phase (relative-value lever, see _WORKFLOW_TEMPLATE).
        radar_universe.append({"symbol": sym, "sector": sc.get("sector", ""),
                               "industry": sc.get("industry", ""), "sector_class": sc.get("sector_class", ""),
                               "methodologies": meths,
                               **{k: sc.get(k) for k in _RADAR_FIELDS if sc.get(k) is not None}})
        signal = "deep_value" if all(m in VALUE_SIGNAL_METHS for m in meths if m != "apex") and any(m in VALUE_SIGNAL_METHS for m in meths) else "catalyst"
        try:
            tx = E.resolve_transcripts(sym)
            real = [t for t in tx.get("all_transcripts", []) if len(t.get("content", "")) > 1000]
        except Exception:
            real = []
        # CHANGE-DETECTION GATE (SB#8): carry the prior record forward unless something
        # debate-relevant changed. Carried records get a deterministic freshness restamp
        # (live price + as_of + provenance) — downstream (Director/skeptic/value re-grade/
        # publish) consumes results_regime/ unchanged; the value rubric sees `carried`.
        _decision, _reason, _prior = _carry_or_debate(sym, sc, real, prior_res_dir, seat_relevant)
        # B13 TIER EXCLUSION: a Basket-13 name never debates in this lane. With a prior record it
        # carries (restamped, so the stock page keeps a dated record); brand-new B13 names are
        # skipped outright — their underwriting lives in _catalyst_weekly.mjs, and their stock-page
        # depth view renders the B13 deep-dossier instead.
        if tiering and sym in b13set and _decision == "debate":
            if isinstance(_prior, dict):
                _decision, _reason = "carry", "b13-separated (underwritten in the catalyst workflow)"
                b13_carried.append(sym)
            else:
                b13_skipped.append(sym)
                continue
        # CONTINUITY (2026-07-08): a re-debated name gets a compact summary of its own prior record
        # so the fresh agent is a committee CONTINUING coverage, not re-rolling from scratch — the
        # debate-layer analog of the Director's rotation ledger (the 07-07 forensics: FIP A/5->B/3,
        # KBR A/4->refuted-B/3, AAUC A/4->C/2 in 5 days with ZERO new dated facts).
        _prior_compact = None
        if _decision == "debate" and isinstance(_prior, dict):
            _prior_compact = {
                "date": str(_prior.get("debated_at") or _prior.get("as_of") or _prior.get("date") or "")[:10],
                "verdict": _prior.get("verdict"), "conviction": _prior.get("conviction"),
                "value_conviction": _prior.get("value_conviction"),
                "catalyst_status": _prior.get("catalyst_status"),
                "sop_fair_value": _prior.get("sop_fair_value"),
                "price_seen": _prior.get("live_price") or _prior.get("price") or _prior.get("current_price"),
                "lane": _prior.get("lane") or "", "source": _prior.get("source") or "",
                "thesis": str(_prior.get("moderator_conclusion") or "")[:600]}
        if _decision == "debate" and not isinstance(sc.get("price"), (int, float)):
            _no_price.append(sym)          # price-blind bundle (off-scan name) — agent MUST quote-fetch
        (INP / f"{sym}.json").write_text(json.dumps({
            "symbol": sym, "sector": sc.get("sector", ""), "signal_type": signal,
            "company": sc.get("name") or sc.get("companyName") or "",
            "metrics_str": metrics, "dossier": "", "methodologies": meths,
            "prior_record": _prior_compact}, ensure_ascii=False, indent=2), encoding="utf-8")
        if _decision == "carry":
            _pr = _prior
            _pr["carried"] = True
            _pr["carried_from"] = str(_pr.get("debated_at") or "")[:10]
            _pr["carry_reason"] = _reason
            _pr["tier"] = "coverage"
            _pr["update_mode"] = "carry"
            if isinstance(sc.get("price"), (int, float)):
                _pr["live_price"] = sc.get("price")
            _pr["as_of"] = datetime.now().strftime("%Y-%m-%d")
            (RES / f"{sym}.json").write_text(json.dumps(_pr, ensure_ascii=False, indent=1), encoding="utf-8")
            _pd = prior_doss_dir / f"{sym}.md"
            if _pd.exists():                              # dossier rides along for skeptic/stock page
                (ROOT / "dossiers" / f"{sym}.md").write_text(_pd.read_text(encoding="utf-8"), encoding="utf-8")
            carried.append(sym)
            continue
        _carry_reasons[_reason] = _carry_reasons.get(_reason, 0) + 1
        debate_info[sym] = {"reason": _reason, "seat": sym in seat_relevant, "has_tx": bool(real),
                            "prior_exists": isinstance(_prior, dict), "meths": meths}
        if real:
            real.sort(key=lambda t: t["date"])
            # Cap to the last 5 quarters: 8 × 18k chars ~= 36k tokens, over the 25k Read cap an agent
            # hits when it reads transcripts/<sym>.txt. 5 × 18k ~= 22k tokens stays under it.
            (TXT / f"{sym}.txt").write_text(
                "\n\n".join("=== " + t["date"] + " ===\n" + E._slice_transcript(t["content"]) for t in real[-5:]),
                encoding="utf-8")
            syms.append(sym)
        else:
            no_tx.append(sym)
    if carried or _carry_reasons:
        print(f"change-detection gate: {len(syms) + len(no_tx)} DEBATE + {len(carried)} CARRIED "
              f"| debate reasons: {_carry_reasons}")
        if carried:
            print(f"  carried ({len(carried)}): {carried}")
    if _no_price:
        print(f"GUARD price-blind bundles ({len(_no_price)}): {_no_price} — off-scan names with NO "
              f"price in the input; the debate prompt REQUIRES these agents to fetch the FMP quote "
              f"first (AAUC 07-07 incident: an assumed price inverted a valid arb)")

    (ROOT / "_radar_universe.json").write_text(
        json.dumps(radar_universe, ensure_ascii=False, indent=2), encoding="utf-8")
    # Radar runs CHUNKED (one Sonnet agent per <=20-name sector chunk) — a single agent over the full
    # universe truncates its peer_groups output (observed at 161 names). Group by sector, split >20,
    # write _radar_groups.json (each chunk = [label, [syms]]); the workflow spawns one agent per index
    # and a deterministic merge (weekly_opus_refresh.py merge). Clear stale shards first.
    import glob as _glob
    for _f in _glob.glob(str(ROOT / "_pg_*.json")):
        try:
            os.remove(_f)
        except OSError:
            pass
    _by_sec = {}
    for _r in radar_universe:
        _by_sec.setdefault(_r.get("sector") or "Other", []).append(_r["symbol"])
    radar_groups = []
    for _sec in sorted(_by_sec, key=lambda s: -len(_by_sec[s])):
        _ss = sorted(_by_sec[_sec])
        for _i in range(0, len(_ss), 20):
            _lab = _sec if len(_ss) <= 20 else f"{_sec} ({_i // 20 + 1})"
            radar_groups.append([_lab, _ss[_i:_i + 20]])
    (ROOT / "_radar_groups.json").write_text(json.dumps(radar_groups, ensure_ascii=False), encoding="utf-8")
    (ROOT / "interrogator_system.txt").write_text(E.INTERROGATOR_SYSTEM_PROMPT, encoding="utf-8")
    (ROOT / "architect_system.txt").write_text(E.ARCHITECT_SYSTEM_PROMPT, encoding="utf-8")
    (ROOT / "moderator_system.txt").write_text(E.MODERATOR_SYSTEM_PROMPT, encoding="utf-8")
    _write_macro_regime()                                   # macro read for the Director's risk_stance

    # no_tx names have NO FMP transcript — instead of skipping (the user's explicit ask: "send agents
    # to fetch transcripts online so we don't skip any pick"), pass them as ONLINE_SYMS so the debate
    # agent WebSearch/WebFetches the latest transcript/results. Their input bundles (with metrics +
    # company name) were already written above, so they debate with full fundamentals grounding.
    # 11c — FORENSIC LEDGER: unexpired EXCLUDE names get a SHORT re-check, not a full
    # I->A->CRO debate (the weekly self-clean wipes all memory, so known frauds/red-flags were
    # burning a full debate every week to rediscover known facts). Entries expire after 8 weeks
    # or on an earnings rollover (days_to_earnings jumped up vs when the entry was written).
    recheck, recheck_info = [], {}
    led_p = ROOT / "forensic_ledger.json"
    if led_p.exists():
        try:
            from datetime import datetime as _dtt
            led = json.load(open(led_p, encoding="utf-8"))
            today_s = _dtt.now().strftime("%Y-%m-%d")
            uni_syms = set(syms) | set(no_tx)
            for s, ent in led.items():
                if ent.get("gate") != "EXCLUDE" or s not in uni_syms:
                    continue
                if (ent.get("expires") or "") < today_s:
                    continue                                   # TTL expired -> full debate again
                dte_now = next((x.get("days_to_earnings") for x in radar_universe if x.get("symbol") == s), None)
                dte_then = ent.get("days_to_earnings")
                if isinstance(dte_now, (int, float)) and isinstance(dte_then, (int, float)) and dte_now > dte_then + 14:
                    continue                                   # earnings happened since -> full debate again
                recheck.append(s)
                recheck_info[s] = {"date": ent.get("date", ""), "reason": ent.get("reason", "")}
        except Exception as _e:
            print(f"WARN: forensic ledger unreadable ({_e}) — all names get full debates")
    syms = [s for s in syms if s not in recheck]
    no_tx = [s for s in no_tx if s not in recheck]

    # ── TIER PARTITION (two-tier, Week 2) ────────────────────────────────────────────────────────
    # syms/no_tx currently hold EVERY name the change-detection gate routed to "debate". Under
    # tiering they split into: DELTA (untriggered seats — anchored Sonnet update, the churn fix),
    # FULL/UNDERWRITE (triggered seats + ranked new-candidate intake, Opus, hard cap U_CAP),
    # COVERAGE-REFRESH (trigger names that missed the cap but have a prior record — Sonnet update,
    # verdict INHERITED by code), and UNCOVERED (missed the cap, no prior record — skipped, printed).
    U_CAP = 40
    VD_U_CAP = 3                                       # value-drawdown names admitted to Tier-U per week
    NG_U_CAP = 3                                       # neglect-orphan names admitted to Tier-U per week
    delta_syms, coverage_syms, uncovered = [], [], []
    if tiering:
        debate_all = list(syms) + list(no_tx)
        delta_syms = [s for s in debate_all
                      if debate_info.get(s, {}).get("reason") == "seat-relevant-only"
                      and debate_info.get(s, {}).get("prior_exists")
                      and (prior_res_dir / f"{s}.json").exists()]
        seat_triggered = [s for s in debate_all
                          if s not in delta_syms and debate_info.get(s, {}).get("seat")]
        nonseat = [s for s in debate_all if s not in delta_syms and s not in seat_triggered]

        def _intake_rank(s):
            info = debate_info.get(s, {})
            r, meths = info.get("reason", ""), info.get("meths", [])
            score = 0
            if r == "new to universe":
                score += 3
            if len([m for m in meths if m not in ("apex", "value_drawdown")]) >= 2:
                score += 2
            if r.startswith("prior catalyst PENDING_HARD") or r.startswith("escalated"):
                score += 2
            if "value_drawdown" in meths:
                score += 1
            if "neglect_orphan" in meths:
                score += 1
            return (-score, -len(meths), s)            # deterministic: score desc, breadth desc, alpha

        room = max(0, U_CAP - len(delta_syms) - len(seat_triggered))
        ranked = sorted(nonseat, key=_intake_rank)
        intake, vd_used, ng_used = [], 0, 0
        for s in ranked:
            if len(intake) >= room:
                break
            _meths_s = debate_info.get(s, {}).get("meths", [])
            is_vd = "value_drawdown" in _meths_s
            is_ng = "neglect_orphan" in _meths_s
            if is_vd and vd_used >= VD_U_CAP:
                continue
            if is_ng and ng_used >= NG_U_CAP:
                continue
            intake.append(s)
            vd_used += 1 if is_vd else 0
            ng_used += 1 if is_ng else 0
        overflow = [s for s in nonseat if s not in intake]
        coverage_syms = [s for s in overflow if debate_info.get(s, {}).get("prior_exists")
                         and (prior_res_dir / f"{s}.json").exists()]
        uncovered = [s for s in overflow if s not in coverage_syms]
        full_set = set(seat_triggered) | set(intake)
        syms = [s for s in syms if s in full_set]
        no_tx = [s for s in no_tx if s in full_set]
        n_u = len(delta_syms) + len(full_set)
        print(f"tier-select: universe={len(sym_meths)} | U={n_u}/{U_CAP} [seats-delta={len(delta_syms)}, "
              f"seats-trigger-full={len(seat_triggered)}, intake-full={len(intake)} (vd={vd_used}, ng={ng_used})] "
              f"| C-refresh={len(coverage_syms)} | b13-excluded={len(b13_carried)} carried "
              f"+{len(b13_skipped)} skipped-new{' ' + str(b13_skipped) if b13_skipped else ''} "
              f"| uncovered-overflow={len(uncovered)}{' ' + str(uncovered) if uncovered else ''}")
        if n_u < 15:
            print(f"GUARD tier-select: Tier-U only {n_u} names (<15) — thin underwriting week; "
                  f"verify the screen/seat inputs before trusting the Director's pool")

    # Skeptic phase context (skeptic now runs BEFORE the Director, inside the same workflow, over all
    # of Tier-U). Lanes/hints computed at prep from prior records + the scan (same helpers the
    # standalone skeptic_gen uses); B13 is tier-excluded so every Tier-U lane is value/compounder.
    tier_u = delta_syms + syms + no_tx
    skeptic_lanes, skeptic_hints = {}, {}
    if tiering and tier_u:
        for s in tier_u:
            # neglect-lane names get the dedicated "the neglect is deserved" attack rubric;
            # everything else in Tier-U is value/compounder (B13 is tier-excluded above).
            _lane0 = ("neglect_orphan" if "neglect_orphan" in (debate_info.get(s, {}).get("meths") or [])
                      else "value")
            skeptic_lanes[s] = {"lane": _lane0, "res": f"results_regime/{s}.json",
                                "doss": f"dossiers/{s}.md", "attack": _SKEPTIC_ATTACKS[_lane0]}
        try:
            skeptic_hints = _moat_hints(tier_u)
        except Exception as _e:
            print(f"WARN: skeptic moat hints failed ({_e}) — skeptic runs without the moat alert")
            skeptic_hints = {}

    # Director rotation discipline: render the regime prior-decision ledger (the live apex book + its
    # tracking) that the Director must reconcile its new basket against. Best-effort — never blocks prep.
    try:
        _ptrk = gcs_io.gcs_read_json("scans/speculair_apex_tracking.json") or {}
        (ROOT / "_prior_regime_basket.json").write_text(json.dumps(baskets), encoding="utf-8")
        (ROOT / "_prior_regime_tracking.json").write_text(json.dumps(_ptrk), encoding="utf-8")
        write_director_ledger("regime", ROOT / "_prior_regime_basket.json", ROOT / "_prior_regime_tracking.json")
    except Exception as _e:
        print(f"WARN: regime ledger build failed ({_e})")
    js = (_WORKFLOW_TEMPLATE
          .replace("__SYMS__", json.dumps(syms))
          .replace("__ONLINE_SYMS__", json.dumps(no_tx))
          .replace("__RECHECK_SYMS__", json.dumps(recheck))
          .replace("__RECHECK_INFO__", json.dumps(recheck_info))
          .replace("__DELTA_SYMS__", json.dumps(delta_syms))
          .replace("__COVERAGE_SYMS__", json.dumps(coverage_syms))
          .replace("__SKEPTIC_SYMS__", json.dumps(tier_u if tiering else []))
          .replace("__SKEPTIC_LANES__", json.dumps(skeptic_lanes))
          .replace("__SKEPTIC_HINTS__", json.dumps(skeptic_hints))
          .replace("__PRIOR_SEATS__", json.dumps(sorted(seat_relevant)))
          .replace("__DIRECTOR_MODEL__", DIRECTOR_MODEL)
          .replace("__SKEPTIC_MODEL__", SKEPTIC_MODEL)
          .replace("__N_RADAR__", str(len(radar_groups))))
    out = ROOT / "_weekly_debate.js"
    out.write_text(js, encoding="utf-8", newline="\n")
    print(f"PREP OK: {len(syms)} full-debate w/ FMP transcripts + {len(no_tx)} full-debate online "
          f"+ {len(delta_syms)} DELTA seats + {len(coverage_syms)} coverage-refresh "
          f"+ {len(recheck)} ledger re-checks + {len(carried)} CARRIED "
          f"= {len(syms) + len(no_tx) + len(delta_syms) + len(coverage_syms) + len(recheck) + len(carried)} COVERED "
          f"(online: {no_tx}{'; recheck: ' + str(recheck) if recheck else ''})")
    print(f"WORKFLOW_SCRIPT={out.resolve()}")


_WORKFLOW_TEMPLATE = r"""export const meta = {
  name: 'speculair-opus-weekly',
  description: 'Two-tier weekly Speculair: Radar -> Coverage/Delta/Underwrite -> deterministic Gates -> Skeptic (pre-Director) -> Director',
  phases: [{ title: 'Radar', model: 'sonnet' }, { title: 'Coverage', model: 'sonnet' }, { title: 'Delta', model: 'sonnet' }, { title: 'Underwrite', model: 'opus' }, { title: 'Gates', model: 'haiku' }, { title: 'Skeptic', model: '__SKEPTIC_MODEL__' }, { title: 'Director', model: '__DIRECTOR_MODEL__' }],
}
const DIR = 'backend/_opus_debate'
const RES = DIR + '/results_regime'
const SYMS = __SYMS__               // full Opus underwrite, bundled FMP transcript
const ONLINE_SYMS = __ONLINE_SYMS__ // full Opus underwrite, no FMP transcript — agent fetches online
const DELTA_SYMS = __DELTA_SYMS__       // held seats, no trigger — anchored Sonnet delta update
const COVERAGE_SYMS = __COVERAGE_SYMS__ // Tier-C refresh — Sonnet update, verdict INHERITED by code
const SKEPTIC_SYMS = __SKEPTIC_SYMS__   // all of Tier-U — kill-tier runs BEFORE the Director
const SKEPTIC_LANES = __SKEPTIC_LANES__
const SKEPTIC_HINTS = __SKEPTIC_HINTS__
const PRIOR_SEATS = __PRIOR_SEATS__     // last week's apex+runners (both books) — skeptic never skips these
const BRIEF = "Read CATALYST_WATCH_REGIME.md (repo root) for the current market regime, then APPLY it: reward hard-dated catalysts inside the favorable window; PENALIZE Fed-cut/rate-rescue or past/out-of-window catalysts; favor structural special-sits in fat thin-coverage lanes (distressed/deleveraging > spinoffs > forced-sellers), deprioritize hard-binary/PDUFA; prize resolution-driver independence (wary of theses hinging on one shared macro factor like oil or AI-capex). Let this MOVE the conviction/verdict."

// ── PHASE 0 — RADAR (Sonnet, cheaper), CHUNKED by sector. A single agent over the full universe
// truncates its peer_groups output (observed at 161 names), so N parallel agents each tag <=20 names
// with their TRUE real-world competitors, then a deterministic merge combines the shards.
const N_RADAR = __N_RADAR__
phase('Radar')
await parallel(Array.from({ length: N_RADAR }, (_, i) => () => agent(
  'You are the RADAR (relative-value analyst). Read ' + DIR + '/_radar_groups.json — a JSON array; take element [' + i + '] = [label, [symbols]]. Those symbols are your ASSIGNMENT. Read ' + DIR + '/_radar_universe.json for their Speculair data (filter to your symbols).\n' +
  '1. For EACH assigned symbol, identify its TRUE business competitors / closest comparables — by business model, economics, end-market, value chain and capital intensity — REGARDLESS of whether the competitor is in this candidate universe. Name the ACTUAL competitors even if NOT screened here (e.g. a stainless-steel maker -> Outokumpu / Aperam; a broadcast-tower operator -> Cellnex / INWIT / American Tower). 4-8 real tickers each. CRITICAL: if you do NOT actually recognize the ticker/company, set verdict="unmapped" and say so in rationale — do NOT invent an identity or guess a peer set from the ticker letters (a wrong identity propagates a stale, wrong multiple all the way to the Director). A non-US suffix (.PA/.MC/.L/.SW/.OL/.DE) is a frequent mis-map trap — verify the actual company name from _radar_universe.json before clustering.\n' +
  '2. For EACH, relative_comps: where it ranks vs that TRUE peer set on VALUATION (p_fcf, the multi-method MoS spread), GROWTH (rev/eps), MARGINS (gross/net, roic) and TREND/MOMENTUM (price vs sma200, 52-wk position, sector_momentum) — cheap / in-line / rich, and whether the gap is JUSTIFIED by quality/growth or is a real mispricing. Use _radar_universe.json data for in-universe peers + your sector knowledge for the rest. 2-4 tight sentences each.\n' +
  '3. Write (Write tool) VALID JSON to ' + DIR + '/_pg_' + i + '.json = a map of SYMBOL to { peers:[...], relative_comps:"...", verdict:"cheap_vs_peers|in_line|rich_vs_peers", rationale:"why these are the real peers" } for ONLY your assigned symbols. Reply exactly: DONE',
  { label: 'radar:' + i, phase: 'Radar', model: 'sonnet' })))
await agent(
  'Run this exact command (it merges the Radar shards into peer_groups.json deterministically): python backend/weekly_opus_refresh.py merge\nConfirm the entry count it prints is > 0. Reply exactly: DONE',
  { label: 'radar-merge', phase: 'Radar', model: 'sonnet' })

// ── PHASE 1 — DEBATE: Interrogator -> Architect (bull/bear + Sum-of-Parts) -> CRO (reconcile). ──
// All names run as general-purpose agents so EVERY name (FMP + online) can web-verify its catalyst.
function debatePrompt(sym, online) {
  const step1 = online
    ? '1. Read ' + DIR + '/inputs/' + sym + ".json (fields metrics_str/sector/signal_type/company; metrics may include a SEGMENT REVENUE block). NO FMP transcript is bundled. FIRST try the paid FMP MCP tools via ToolSearch (keyword search e.g. \"FMP earnings transcript\", \"FMP statements\", \"FMP news\") for " + sym + "'s MOST RECENT earnings-call transcript and quarterly numbers; if FMP has nothing for this ticker, THEN use WebSearch + WebFetch to find the latest transcript / quarterly results / earnings release / management commentary / investor presentation (IR site, Tikr, Seeking Alpha, Investing.com, Simply Wall St, MarketScreener, plus the latest regulatory filing) — do NOT scrape press-release PDFs by shell. If genuinely nothing is findable, say so and reason from the fundamentals — never fabricate quotes or figures.\n"
    : '1. Read ' + DIR + '/inputs/' + sym + '.json (fields metrics_str/sector/signal_type; metrics may include a SEGMENT REVENUE block) and ' + DIR + '/transcripts/' + sym + '.txt.\n'
  return 'You run the COMPLETE multi-agent debate for ' + sym + ' as Claude Opus 4.8 — Interrogator, Architect, then CRO/Moderator — allocating REAL capital. Be skeptical and current-facts-driven.\n' +
    step1 +
    '1b. LIVE PRICE (MANDATORY, BEFORE any valuation reasoning): if the metrics block does not state a current price, you MUST fetch the live quote via the FMP MCP tools (ToolSearch, keyword "FMP quote") and state the price + currency you are using. NEVER assume or infer where the stock trades — a fabricated price inverts the entire risk/reward (the 2026-07-07 AAUC record assumed "near the C$44 offer" when the stock traded 31% below terms). For dual-listed names state WHICH listing/currency your numbers are in.\n' +
    '1c. CONTINUITY (when inputs/' + sym + '.json carries a non-null prior_record): you are the SAME committee CONTINUING coverage, not a fresh one. Read prior_record (your prior verdict/conviction/thesis dated prior_record.date). If your verdict or conviction will DIFFER, you MUST cite in whats_changed_since_prior the DATED fact(s) that emerged since prior_record.date that justify the change — a re-reading of already-known facts is NOT a justification. If nothing dated changed, INHERIT the prior verdict/conviction and update prices/status only. An A<->C verdict flip or a conviction move of >=2 without a dated fact is a DEFECT, not an opinion.\n' +
    '2. INTERROGATOR: read ' + DIR + '/interrogator_system.txt; produce the full forensic dossier (8 sections + final "CREDIBILITY_SCORE: <1-5> | TRAJECTORY: <...>"); Write it to ' + DIR + '/dossiers/' + sym + '.md.\n' +
    '3. PEER COMPS: read ' + DIR + '/peer_groups/' + sym + '.json (this name\'s peers + relative_comps + verdict) as an INDEPENDENT relative-value lever for the valuation below (skip if the file is absent). If the file carries `peer_override`/`anchor_multiple`, those are the CURRENT (live/de-rated) peer multiples — use THEM as the anchor and do NOT cite a peer multiple from memory (peer multiples de-rate; a stale anchor inflates the apparent discount — e.g. Edenred is ~10x fwd P/E today, NOT its pre-shock 20-25x). If `convergence`="sector_regulatory", the discount to that peer is shared-factor SECTOR BETA (both names move on the same unresolved driver), NOT idiosyncratic single-name alpha — say so explicitly in peer_comps_note and DO NOT credit the gap as name-specific edge.\n' +
    '4. ARCHITECT: read ' + DIR + '/architect_system.txt; produce bull_thesis and bear_thesis, AND a SUM-OF-PARTS valuation — value the business by its PARTS (segment SoP from the SEGMENT REVENUE block x peer multiples where present; else whole-company intrinsic via the methodology metric/peer multiple), then apply special-situation OVERLAYS where relevant (net cash, pending distributions [VERIFY whether already paid], announced asset-sales, tender/deal terms minus liabilities). Output sop_bull (favorable parts) and sop_bear (adverse parts), each a per-share value + the parts breakdown.\n' +
    '5. CATALYST VERIFICATION (MANDATORY for every name): identify the load-bearing catalyst(s) and verify their CURRENT status as of today — FIRST reach for the paid FMP MCP tools via ToolSearch (keyword search e.g. \"FMP news\", \"FMP earnings transcript\", \"FMP statements\", \"FMP quote\") since it is structured, licensed and reliable, then WebSearch/WebFetch only for what FMP lacks (do NOT scrape press-release PDFs by shell). catalyst_status = FIRED (already happened, re-rate spent) | ARB (deal terms fixed, tight merger-arb capped at the offer) | PENDING_HARD (dated, binding, real asymmetry) | SOFT_EXTENDED (non-binding / serially-extended / third-party / single-binary) | UNVERIFIABLE. Dated evidence; never fabricate.\n' +
    '6. CRO/MODERATOR: read ' + DIR + '/moderator_system.txt; ' + BRIEF + ' RECONCILE sop_bull/sop_bear into a base-case sop_fair_value (+ sop_breakdown) and risk_reward (downside-to-break vs upside-to-fair); DOWN-RATE conviction for FIRED/SOFT catalysts and size ARB to the spread; sanity-check the multiple against the peer comps. Produce verdict (A/B/C), conviction (int 1-5), consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion. THEN, separately, produce value_conviction (int 1-5): rate the VALUE case as if NO catalyst overlay existed — judged on valuation vs the SoP fair value + forensic quality ONLY, explicitly IGNORING catalyst_status and the regime tilt. The two scores MUST be allowed to diverge (a FIRED-catalyst name can be value_conviction 5; a hot-catalyst name can be value_conviction 1); do not default both to the same number. ALSO emit moat (WIDE|NARROW|ERODING|NONE — a high-but-FALLING ROIC/margin is ERODING, not WIDE), moat_trend (WIDENING|STABLE|ERODING), secular_threat (terminal|material|manageable|none) and ONE secular_theme id from ' + DIR + '/secular_themes.json (ai-displacement|payments-disintermediation|linear-media-decline|autonomous-mobility|labor-arbitrage-deflation|reimbursement-compression|retail-channel-shift|energy-transition-loser, or \"\"); an ERODING moat or TERMINAL secular threat CAPS value_conviction at 3 (a low multiple on a structurally-shrinking base is a value trap, not value).\n' +
    '6b. TYPED VALUATION BLOCK (MANDATORY — the numbers the pipeline checks and sizes on): distill your reconciliation into POINT NUMBERS per share, in the quote currency: bear_px (your adverse case — ONE number; your ranges stay in the prose), base_fv_px (base case), bull_px (favorable case), downside_floor_px (ONLY a structural floor — deal terms, net cash/share, tender; else null — a chart low or a dividend yield is NOT a floor), valuation_method ("sop"|"multiple"|"spread"|"recovery"), horizon_months (when the base case lands). ORDERING bear_px <= base_fv_px <= bull_px is REQUIRED. State LEVELS only: risk_reward ratios, expected-return %, and MoS % are COMPUTED BY THE PIPELINE from these numbers — any "N:1" or %-vs-% arithmetic you assert in prose will be overwritten by the computed values (the 2026-07-07 HNR1.DE record asserted "2:1" on a 6% dividend-"floor"; the pipeline now does this math).\n' +
    '7. Write (Write tool) VALID, escaped JSON to ' + RES + '/' + sym + '.json with: symbol(="' + sym + '"), sector, signal_type, live_price(number — the price you actually used), price_currency, valuation({live_price, price_currency, quote_listing(="' + sym + '"), bear_px, base_fv_px, bull_px, downside_floor_px, valuation_method, horizon_months, as_of(today YYYY-MM-DD)} — the step-6b numbers), whats_changed_since_prior(the dated fact(s) per step 1c; "" when no prior_record or unchanged), bull_thesis, bear_thesis, sop_bull, sop_bear, sop_fair_value, sop_breakdown, risk_reward, catalyst_status, peer_comps_note, verdict, conviction, value_conviction(int), moat, moat_trend, secular_threat, secular_theme, consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion, interrogator_score(int), trajectory, tier(="underwrite"), update_mode(="full"), last_full_debate(today YYYY-MM-DD), source(="' + (online ? 'opus_regime_online' : 'opus_regime_mod') + '"), transcript_source(="' + (online ? 'web' : 'fmp') + '").\n' +
    'Reply exactly: DONE'
}

// ── DELTA (Sonnet): held seats with NO trigger — an ANCHORED weekly update, not a re-debate. ──
// This is the churn fix: the committee that underwrote the seat updates its own record; a
// deterministic gate (continuity-gate v2) REVERTS any un-justified change, and a verdict flip is
// structurally impossible here (escalate_full_debate routes it to a full re-debate next cycle).
function deltaPrompt(sym) {
  return 'DELTA REVIEW for ' + sym + ' — you are the SAME committee that underwrote this seat. Your ANCHOR is ' + DIR + '/_archive_prev/results_regime/' + sym + '.json — READ IT FIRST, in full. This is a weekly anchored update, NOT a re-debate.\n' +
    '1. Also read ' + DIR + '/inputs/' + sym + '.json (fresh metrics + prior_record) and, if they exist, ' + DIR + '/transcripts/' + sym + '.txt and ' + DIR + '/peer_groups/' + sym + '.json.\n' +
    '2. Fetch the live quote via the FMP MCP tools (ToolSearch, keyword "FMP quote"); check the load-bearing catalyst status (FMP news first, WebSearch only for what FMP lacks).\n' +
    '3. RULES: you may freely update live_price / price_currency / as_of, the valuation block prices restated off the new quote, and catalyst_status (with a dated fact). You may move sop_fair_value / bear_px / base_fv_px / bull_px / conviction (max ±1) ONLY on a dated fact that emerged since the anchor date — every such move MUST appear in deltas:[{field, old, new, dated_fact}]. You may NOT flip the verdict: if you now believe the anchor verdict is wrong, KEEP it and set escalate_full_debate=true + escalate_reason (a full re-debate runs next cycle). Unjustified changes are REVERTED by a deterministic gate — do not waste them.\n' +
    '4. Write (Write tool) VALID JSON to ' + RES + '/' + sym + '.json = the FULL anchor schema updated per the rules (keep every field the anchor carries, incl. the typed valuation block with point numbers and NO asserted ratios). If the anchor has NO valuation block (pre-typed-schema record), CREATE it now from the numbers the anchor itself states, restated off the live quote: {live_price, price_currency, quote_listing, bear_px, base_fv_px, bull_px, downside_floor_px|null, valuation_method, horizon_months, as_of} — levels only, never ratios; this is a TRANSCRIPTION of the existing anchor bear/base/bull view, not a re-underwriting. PLUS: update_mode="delta", tier="underwrite", deltas:[...], whats_changed_since_prior, escalate_full_debate(bool), escalate_reason(""), last_full_debate(copy from the anchor if present, else the anchor debated_at/as_of date), source(keep the anchor source). Reply exactly: DONE'
}

// ── COVERAGE (Sonnet): Tier-C refresh — a structured update with NO grade fields at all. ──
// The verdict/conviction are INHERITED verbatim by code (coverage-merge); the agent physically
// cannot re-roll them because its output schema has no place for them.
function coveragePrompt(sym) {
  return 'COVERAGE REFRESH for ' + sym + ' (Tier-C — NOT a debate, NOT a grade). The standing record is ' + DIR + '/_archive_prev/results_regime/' + sym + '.json — read it and ' + DIR + '/inputs/' + sym + '.json.\n' +
    '1. Fetch the live quote via the FMP MCP tools (ToolSearch "FMP quote"); check the catalyst status via FMP news; scan for material dated developments since the standing record.\n' +
    '2. Write (Write tool) VALID JSON to ' + DIR + '/_coverage_updates/' + sym + '.json = {symbol:"' + sym + '", as_of(today YYYY-MM-DD), live_price(number), price_currency, whats_new:[{date:"YYYY-MM-DD", fact:"..."}], catalyst_status_check(one line: does the standing catalyst_status still hold?), thesis_update(<=80 words), escalate(bool — true ONLY if something material demands a full re-debate next cycle), escalate_reason("")}. There are NO verdict/conviction/sop fields in this schema — do not add any. Reply exactly: DONE'
}

// ── LEDGER RE-CHECKS: unexpired forensic-EXCLUDE names get a SHORT re-affirm pass, not a full debate ──
const RECHECK_SYMS = __RECHECK_SYMS__
const RECHECK_INFO = __RECHECK_INFO__
function recheckPrompt(sym) {
  const info = RECHECK_INFO[sym] || {}
  return 'LEDGER RE-CHECK for ' + sym + ' (Claude Opus 4.8). This name was forensically EXCLUDED on ' + (info.date || 'a prior run') + ' (interrogator credibility <= 2: ' + (info.reason || 'see ledger') + '). Do NOT run a full debate. Read ' + DIR + '/inputs/' + sym + '.json, then WebSearch ONLY for material changes since ' + (info.date || 'the exclusion') + ' (new filings, restatements, management change, resolved investigations, a transformed balance sheet). If NOTHING material changed, re-affirm the exclusion in one paragraph. If something material DID change, say so and recommend a full re-debate next run.\n' +
    'Write (Write tool) VALID JSON to ' + RES + '/' + sym + '.json with: symbol(="' + sym + '"), sector, signal_type, verdict(="C" unless materially changed), conviction(int, keep 1-2 unless changed), value_conviction(int), catalyst_status(="UNVERIFIABLE" unless verified), interrogator_score(int, keep <=2 unless the forensic picture genuinely changed), trajectory, moderator_conclusion(the one-paragraph re-affirmation or the change note), bull_thesis(""), bear_thesis(""), sop_bull(""), sop_bear(""), sop_fair_value(""), sop_breakdown(""), risk_reward(""), peer_comps_note(""), consensus_delta(""), valley_of_death(""), positioning_washout(""), forcing_function(""), source(="ledger_recheck"), transcript_source(="web"). Reply exactly: DONE'
}

const BATCH = 8   // rate-limit safety: run 8 web-heavy agents at a time, not the full universe burst (429s).

// ── PHASE 1 — COVERAGE (Sonnet): Tier-C names whose trigger fired but who missed the U_CAP. ──
phase('Coverage')
if (COVERAGE_SYMS.length) log(`Coverage refresh over ${COVERAGE_SYMS.length} Tier-C names (verdicts inherited by code).`)
for (let b = 0; b < COVERAGE_SYMS.length; b += BATCH) {
  await parallel(COVERAGE_SYMS.slice(b, b + BATCH).map(sym => () => agent(
    coveragePrompt(sym), { label: 'coverage:' + sym, phase: 'Coverage', agentType: 'general-purpose', model: 'sonnet' })))
}

// ── PHASE 2 — DELTA (Sonnet): held seats, anchored weekly update. ──
phase('Delta')
if (DELTA_SYMS.length) log(`Delta review over ${DELTA_SYMS.length} held seats (anchored on last week's records).`)
for (let b = 0; b < DELTA_SYMS.length; b += BATCH) {
  await parallel(DELTA_SYMS.slice(b, b + BATCH).map(sym => () => agent(
    deltaPrompt(sym), { label: 'delta:' + sym, phase: 'Delta', agentType: 'general-purpose', model: 'sonnet' })))
}

// ── PHASE 3 — UNDERWRITE (Opus): full debates — triggered seats + ranked new-candidate intake. ──
const ALL = SYMS.map(s => ({ sym: s, online: false, recheck: false }))
  .concat(ONLINE_SYMS.map(s => ({ sym: s, online: true, recheck: false })))
  .concat(RECHECK_SYMS.map(s => ({ sym: s, online: true, recheck: true })))
phase('Underwrite')
log(`Underwrite: ${ALL.length} full debates (${SYMS.length} FMP + ${ONLINE_SYMS.length} online + ${RECHECK_SYMS.length} ledger re-checks).`)
for (let b = 0; b < ALL.length; b += BATCH) {
  log(`Underwrite batch ${Math.floor(b / BATCH) + 1}/${Math.ceil(ALL.length / BATCH)} (names ${b + 1}-${Math.min(b + BATCH, ALL.length)} of ${ALL.length})`)
  await parallel(ALL.slice(b, b + BATCH).map(it => () => agent(
    it.recheck ? recheckPrompt(it.sym) : debatePrompt(it.sym, it.online),
    { label: (it.recheck ? 'recheck:' : 'debate:') + it.sym + (it.online && !it.recheck ? '(web)' : ''), phase: 'Underwrite', agentType: 'general-purpose', model: 'opus' })))
}

// ── PHASE 4 — GATES (Haiku runner): deterministic checks between the records and the money. ──
phase('Gates')
await agent(
  'Run these exact commands IN ORDER (each is a deterministic gate) and report each summary line verbatim:\n' +
  'python backend/weekly_opus_refresh.py coverage-merge\n' +
  'python backend/weekly_opus_refresh.py continuity-gate\n' +
  'python backend/weekly_opus_refresh.py lane-stamp\n' +   // neglect-lane provenance onto fresh records (2026-07-17)
  'python backend/weekly_opus_refresh.py numeric-gate --legacy --enforce\n' +   // enforcement flipped 2026-07-11 after the dry-run calibration week (Task: pipeline-v3 Weeks 3-4)
  'Reply with the four summary lines, then exactly: DONE',
  { label: 'gates', phase: 'Gates', model: 'haiku' })

// ── PHASE 5 — SKEPTIC (Opus, BEFORE the Director): kill-tier over all of Tier-U, so demotion ──
// evidence informs seating instead of vaporizing seats after the fact. Self-gate: a conviction<=2
// record that is NOT a current seat cannot seat anyway (eligibility floor is 3) — skip cheaply.
phase('Skeptic')
if (SKEPTIC_SYMS.length) log(`Skeptic kill-tier over ${SKEPTIC_SYMS.length} Tier-U names (pre-Director).`)
const SK_BATCH = 6
for (let b = 0; b < SKEPTIC_SYMS.length; b += SK_BATCH) {
  await parallel(SKEPTIC_SYMS.slice(b, b + SK_BATCH).map(sym => () => agent(
    'SKEPTIC tier for ' + sym + ' (regime Tier-U; lane ' + (SKEPTIC_LANES[sym] || {}).lane + '). Your job is to KILL this thesis; default verdict REFUTED unless you can independently confirm the load-bearing facts against a PRIMARY source (filings, the company IR site, regulator pages). You see ONLY the bear side - do NOT read or reconstruct the bull case.\n' +
    'SELF-GATE FIRST: read ' + DIR + '/results_regime/' + sym + '.json — if its conviction <= 2 AND ' + JSON.stringify(PRIOR_SEATS) + '.indexOf("' + sym + '") === -1, write ' + DIR + '/_skeptic_regime/' + sym + '.json = {symbol:"' + sym + '", verdict:"SKIPPED_LOW_CONVICTION"} and reply DONE (a conviction-2 non-seat cannot seat; no kill needed).\n' +
    (((SKEPTIC_HINTS[sym] || {}).refute_candidate) ? 'MOAT ALERT (deterministic screen): ' + sym + ' is a TERMINAL-EROSION candidate - erosion=' + (SKEPTIC_HINTS[sym] || {}).erosion + ', severity=' + (SKEPTIC_HINTS[sym] || {}).severity + ', earns_below_cost_of_capital=' + (SKEPTIC_HINTS[sym] || {}).roic_below + ', returns ' + (SKEPTIC_HINTS[sym] || {}).returns_trend + ', gross-margin ' + (SKEPTIC_HINTS[sym] || {}).gross_margin_trend + '. The moat is ERODING by default: you must find PRIMARY-SOURCE proof of durable pricing power / rising returns to CONFIRM, else REFUTED with the moat erosion as the kill_fact.\n' : '') +
    '1. From that record USE ONLY: bear_thesis, sop_bear, risk_reward, catalyst_status, valuation.bear_px/downside_floor_px. Read the forensic dossier ' + DIR + '/' + (SKEPTIC_LANES[sym] || {}).doss + ' if it exists.\n' +
    '2. Verify the CURRENT facts. FIRST reach for the paid FMP MCP tools via ToolSearch (keyword search e.g. "FMP earnings transcript", "FMP statements", "FMP news", "FMP quote") for the latest transcript / quarterly numbers / news / price - it is structured, licensed and reliable; fall back to WebSearch/WebFetch only for what FMP lacks, and do NOT scrape press-release PDFs by shell. Attack: ' + (SKEPTIC_LANES[sym] || {}).attack + '\n' +
    '3. Verdict: CONFIRMED (bear attacked, thesis survives) | CONFIRMED_WITH_CORRECTIONS (survives but a load-bearing number/claim needed fixing - state it) | REFUTED (a kill_fact breaks the thesis). ALSO correction_severity: "minor" (footnote-level, thesis arithmetic intact) or "material" (a load-bearing number/date/anchor moved - the post layer haircuts sizing on material). AND kill_scope: which layer your strongest finding hits - "thesis" | "numbers" | "catalyst" | "moat". Do NOT emit any numeric conviction cap - verdicts and severity only.\n' +
    '4. Write (Write tool) VALID JSON to ' + DIR + '/_skeptic_regime/' + sym + '.json = {symbol:"' + sym + '", verdict, kill_fact, corrections, correction_severity, kill_scope, evidence:[2-4 dated primary-source cites]}. Never fabricate. Reply exactly: DONE',
    { label: 'skeptic:' + sym, phase: 'Skeptic', agentType: 'general-purpose', model: '__SKEPTIC_MODEL__' })))
}

phase('RegimeRead')
await agent(
  'REGIME READ (context layer for the Director — NOT an override; the deterministic dials stay authoritative). Read backend/_opus_debate/macro_regime.json: regime RISK_ON|NEUTRAL|CAUTIOUS|RISK_OFF, score 0-1, quadrant GOLDILOCKS|REFLATION|STAGFLATION|RISK_OFF (growth x inflation 2x2) + quadrant_basis + growth/inflation/rates/credit detail.\n' +
  '1. State the quadrant per the dials and what it implies for a 12-month equity book (ONE sentence).\n' +
  '2. Argue AGAINST the dials: search for macro prints from the LAST 3 WEEKS that contradict the dial read — CPI/PCE, payrolls, PMIs, credit spreads, 10y moves. FIRST reach for the FMP MCP economic tools via ToolSearch (e.g. "FMP economic indicators", "FMP treasury"); fall back to WebSearch for what FMP lacks. Every claim carries a DATE. If nothing material contradicts, your view is AGREE.\n' +
  '3. Emit dated FALSIFIERS: 2-4 concrete checkable conditions that would flip this quadrant call, each with a check_by date (e.g. "core CPI >= 0.4% MoM in the next print (due ~Aug 12)" or "2s10s re-inverts below -20bp"). These are the ledger entries the NEXT run gets scored against — make them checkable, not vibes.\n' +
  '4. Write (Write tool) VALID JSON to backend/_opus_debate/regime_read.json = {asof, quadrant_per_dials, agent_view ("AGREE"|"CONTRADICT"), evidence: [2-4 dated one-liners], falsifiers: [{condition, check_by}], stance_note (one sentence for the Director), confidence ("LOW"|"MED"|"HIGH")}. A CONTRADICT with dated evidence may temper the Director stance ONE notch, never flip the dial. Never fabricate a print. Reply exactly: DONE',
  { label: 'regime-read', phase: 'RegimeRead', agentType: 'general-purpose', model: '__SKEPTIC_MODEL__' })

phase('Director')
await agent(
  'You are the SPECULAIR APEX DIRECTOR (Claude Opus 4.8). The CRO already reconciled each name to a Sum-of-Parts fair value + risk/reward + a LIVE catalyst_status, with Radar peer comps.\n' +
  'STEP 1 — Read CATALYST_WATCH_REGIME.md (repo root) IN FULL and apply its tilt. ALSO read backend/_opus_debate/macro_regime.json (the live macro classifier: regime RISK_ON|NEUTRAL|CAUTIOUS|RISK_OFF + score 0-1 + quadrant GOLDILOCKS|REFLATION|STAGFLATION|RISK_OFF (growth x inflation 2x2, with quadrant_basis) + growth/inflation/rates/credit detail) AND backend/_opus_debate/regime_read.json if present (an agent regime read run before you: agent_view AGREE|CONTRADICT vs the dials + dated evidence + falsifiers — the DIALS are authoritative; a CONTRADICT with dated evidence may temper your stance ONE notch, never flip the dial; carry its falsifiers into the memo so next week can check them). RETURN GOAL: this book targets +30-50% over ~12 months. QUADRANT PLAYBOOK for the RISK_STANCE: GOLDILOCKS => REACH for the goal (credible 12-month re-rate DRIVERS — dated catalyst, earnings inflection, live trend — accept more demand-cycle/AI-capex beta); REFLATION => favor PRICING POWER, cyclical value and real-asset re-rates over duration-sensitive growth (inflation eats long-duration multiples); STAGFLATION => pricing power + real assets ONLY on the reach side, SIZE DOWN demand-cycle beta and duration, favor carry; RISK_OFF (disinflationary slowdown) => DEFENSE — quality, balance sheet, FCF carry, structural floors, even if +30-50% becomes an 18-24mo story. State the risk_stance, the quadrant you applied, and a one-line macro read in the memo.\n' +
  'STEP 2 — Run: python backend/_opus_debate/compact_table.py results_regime — confirm the row count; also read ' + DIR + '/peer_groups.json for the relative-value picture. CONTINUITY FLAGS: any record carrying a continuity_flag field flipped its verdict/conviction vs last week WITHOUT citing a dated fact — treat that fresh record as UNRELIABLE for seat decisions on that name: fall back to your ledger + the prior grade (the flag text quotes it) rather than acting on an unjustified downgrade/upgrade, and say so in decision_rationale. SKEPTIC VERDICTS ARE ALREADY IN (this run, pre-seat — the kill-tier ran before you): for EVERY finalist you consider, read ' + DIR + '/_skeptic_regime/<SYM>.json — a REFUTED verdict is a HARD no-seat (if you were inclined to seat it, cite the kill_fact in the memo instead); CONFIRMED_WITH_CORRECTIONS with correction_severity="material" must temper your conviction and sizing for that seat; SKIPPED_LOW_CONVICTION just means the record graded too low to need a kill. Where an entry carries `peer_override`/`anchor_multiple`, that is a LIVE current peer multiple — trust it over any multiple quoted from memory in a dossier; where `convergence`="sector_regulatory", treat that name\'s discount-to-peer as a SHARED-FACTOR cluster in STEP 4, not as idiosyncratic edge.\n' +
  'STEP 3 — Eligible = conviction >= 3 AND numeric_gate NOT in (REJECT, EXCLUDE_ELIGIBILITY) (records stamped by the deterministic numeric gate — an excluded record\'s numbers failed arithmetic/price/floor checks and cannot support a seat regardless of the narrative). Select using sop_fair_value / risk_reward / catalyst_status AS PRIMARY LEVERS — and where a record carries a computed{} block (rr_ratio / expected_return_pct computed by the pipeline from the typed valuation numbers), TRUST THE COMPUTED NUMBERS over any prose arithmetic: a FIRED catalyst is NOT an asymmetric special-sit (re-rate it to a sized-to-spread ARB or a defensive anchor — do NOT size as conviction-4); a SOFT_EXTENDED catalyst is mid-conviction at best; prefer the widest COMPUTED risk_reward to a credible SoP fair value. Then regime fit, forcing-function datedness, consensus-delta width. You MAY Read individual ' + RES + '/<SYM>.json for finalists.\n' +
  'STEP 3b — BASKET-13 SEPARATION (HARD RULE, 2026-07-08): the Basket-13 catalyst book (merger-arb spreads, forced-seller recovery, SoP breakups, spins, FDA binaries — anything whose thesis is a dated EVENT rather than a franchise) is a FULLY SEPARATE book with its own funnel, debate, sizing and tracker. You may NOT seat any equity special-sit / event-driven name in this apex basket — no exceptions, no "sleeve". If a name in results_regime carries lane/source values like equity_special_sit / special_sit / opus_catalyst, or its thesis is primarily a dated corporate event, it is INELIGIBLE for a seat here (it may be a runner_up with an explicit note that it belongs to B13). This book seats COMPOUNDERS and value re-rates only: durable franchises where the value case stands without the event.\n' +
  'STEP 4 — CORRELATION/EXPOSURE STRESS over the proposed 10 (MANDATORY, beyond the <=3/sector cap): decompose on (a) DEMAND-CYCLE beta (cyclical industrials/consumption that de-rate together in a recession), (b) REGULATORY JURISDICTION (e.g. Italian/EU sign-off) — INCLUDING any peer entry tagged `convergence`="sector_regulatory" where the thesis is "cheap vs a peer" and BOTH names de-rated on the SAME regulatory factor (e.g. PLX.PA/Pluxee vs a now-~10x Edenred on the shared Brazil-PAT/Italy-voucher reform): that is sector BETA, so it must NOT be sized as idiosyncratic apex alpha — discount it or hold it as a watch/sized leg, (c) LIQUIDITY/POSITIONING (small-caps that de-gross together), (d) POSTURE (count of wait-for-the-flush entries — a correlated timing bet), (e) SECULAR-DISRUPTION THEME (each name carries a secular_theme from the debate: ai-displacement / payments-disintermediation / linear-media-decline / autonomous-mobility / labor-arbitrage-deflation / reimbursement-compression / retail-channel-shift / energy-transition-loser). No hidden factor may carry >3 names AND no secular_theme may carry >2 names; for any secular_theme with >=2 names you MUST emit a combined_caps entry {names, max_units, axis:"secular-theme:<id>"} (a WIDE non-eroding moat counts at HALF toward the theme budget — a durable anchor that merely carries the narrative is not the tail risk). Do NOT let one melting tail (e.g. AI-displacement across ADBE+IT+GLOB) carry the book. Stress the book against a EUROPEAN-CYCLICAL-RECESSION + CORRELATED-DE-GROSS scenario and diversify if it fails; sequence entries assuming flushes arrive together.\n' +
  'STEP 5 — FIRST read backend/_opus_debate/_director_ledger_regime.txt (your currently-HELD names with why + every name you DROPPED in 2026) and apply ROTATION DISCIPLINE: KEEP each held name UNLESS its thesis is BROKEN (price through thesis_break, a FIRED/elapsed catalyst with no fresh driver, a forensic/solvency flip, or confirmed moat terminal-erosion) OR you have a STRICTLY-BETTER orthogonal name for that seat — do NOT drop a held compounder merely because another name graded a hair higher; you may RE-ADD a previously-dropped name ONLY by citing a DOCUMENTED THESIS CHANGE since the drop date (a better grade is NOT a thesis change) — override allowed but you must OWN it in whats_changed. CONVICTION RUBRIC (0-100, BANDED — your conviction is anchored, not free-floating): 90-100 = table-pounding: computed expected return >= +40% to base_fv_px AND a structural floor or paid-to-wait carry AND a live dated 12-mo driver AND a clean skeptic; 70-89 = high conviction: computed ER +25-40%, credible driver, clean forensic; 50-69 = solid hold: ER +15-25%, or the driver is undated, or the record carries WARN/THIN_FLOOR flags; 30-49 = runner-up only; <30 = no seat. CONSISTENCY RULE: conviction >= 70 on a name whose COMPUTED expected return is < +15% requires an explicit carry justification (dividend/buyback floor) in goal_note, else it is a rubric violation. ANCHORING: the ledger shows your PRIOR conviction per held seat — emit conviction_prior (echo it) and conviction_delta (new minus prior) for every KEEP/RE-ADD; when |conviction_delta| > 10 you MUST fill delta_justification with the DATED fact that moved it (the deterministic post layer CLAMPS unjustified moves to prior ±10 — save yourself the clamp). Then for each pick: symbol, sector, director_conviction (0-100 per the rubric), conviction_prior (number or null for ADDs), conviction_delta (number or null), delta_justification (dated fact when |delta|>10; else ""), size_units (float 0.1-1.5 — your explicit seat size: 1.0=full unit, 1.4=max-conviction anchor, 0.5=half; sizing is decoupled from conviction, so SIZE the seat deliberately), one-sentence thesis, sop_fair_value, catalyst_status, lane, regime_fit, exposure_axes (hidden factors it carries), secular_theme (the name dominant secular-decline theme id from secular_themes.json or ""), moat (WIDE|NARROW|ERODING|NONE from the debate), entry_posture (one of: "enter_now_carry" | "scale_in" | "on_confirmation: <the dated event>" | "wait_for_weakness" — derive it from your STEP 4 SEQUENCING: a structural/carry anchor that needs no catalyst and pays you to wait = enter_now_carry; a standard tranche-in = scale_in; a leg gated on a dated/ARB event = on_confirmation with that event; a cyclical/de-gross tail or a knife-catch near the 52w low = wait_for_weakness), wheel (where a wheel SUITS this seat — a slow-re-rate income name you are happy to own at a discount, NOT an on_confirmation/event-risk name: {suits:true, csp_strike (your "happy to own" level — a support/downside-to-break below spot), cc_strike (the fair-value target where you cap upside once assigned), tenor_days (~30-45), rationale (one sentence: why selling the put pays you to wait)}; else {suits:false}), expected_return_pct (your base-case % upside to sop_fair_value from the current price), horizon_months (WHEN the bulk of that re-rate lands — tie it to the driver/catalyst/trend, not "eventually"), meets_goal (bool: can this credibly deliver ~+30-50% within ~12 months given your stance), goal_note (the 12-month driver; or, for a longer-horizon name you keep, why it still earns a seat), decision ("KEEP"|"ADD"|"RE-ADD" vs the ledger), decision_rationale (one sentence reconciling this seat to the ledger), whats_changed (REQUIRED non-empty ONLY for RE-ADD: what materially changed since the drop; else ""). Plus ~6 runner_ups and a director_memo stating the correlation-stress result. The director_memo MUST include a SECULAR-THEME CONCENTRATION subsection naming each >=2-name theme and how it was resolved (diversified -> the swap; or kept-with-cap -> the combined_caps numbers, durable WIDE anchors counted at half), AND end with a "BEAR REBUTTAL" subsection: ONE sentence per apex seat stating the STRONGEST reason that pick is wrong, written BEFORE final sizing — if you cannot articulate the bear in one sentence, you do not understand the position.\n' +
  'STEP 6 — Write (Write tool) VALID JSON to ' + DIR + '/apex_basket_opus_regime.json = {apex_basket:[...], director_memo, runner_ups:[...], combined_caps:[{names, max_units, axis}], risk_stance ("aggressive"|"balanced"|"defensive"), regime_quadrant (echo the quadrant you applied), macro_read (one sentence interpreting macro_regime.json + the regime read + the +30-50%/12mo goal)}. Reply exactly: DONE',
  { label: 'director', phase: 'Director', model: '__DIRECTOR_MODEL__' })
log('Radar + coverage + delta + underwrite + gates + skeptic + director complete.')
return 'DONE'
"""


# ── Apex EQUITY SPECIAL-SIT LANE (catalyst-framed B13 non-binaries) ────────────────────────────
# The apex is a held-equity, value-framed compounder book; it structurally can't score the
# event-driven asymmetry that lives in the Basket-13 catalyst funnel. This lane lets the apex seat
# the NON-BINARY equity special-sits (merger-arb spreads / forced-seller recovery / SoP / spins —
# FIP/BLCO/CLVT/KBR/UNF/AAUC ...) using the CATALYST-framed debate (so they aren't crushed by the
# value/moat gates) and FLOOR-sized (so they don't carry compounder tail risk). FDA binaries stay
# in B13 (defined-risk sized). Flow: catalyst-prep -> Workflow(_catalyst_weekly.mjs) -> catalyst-seed
# (after prep, before the main debate Workflow), then the relaxed STEP-3b gate lets the Director seat them.
_B13_BLOCKING = {"QUARANTINED", "NO_UPSIDE", "TRADING_THROUGH_TERMS", "FLOOR_GE_LIVE", "NO_BREAK_DOWNSIDE"}
_B13_SS_METHODS = {"spread", "recovery", "sop"}  # non-binary equity special-sits (NOT binary_prob)


def _b13_universe():
    """FULL B13 book for catalyst coverage = the candidate funnel UNION the held tracker SEATS.
    Held seats that entered from an EARLIER funnel snapshot (e.g. FIG/GDOT/WVE) are absent from the
    current _basket13_candidates.json, so debating only the candidates skipped them — that gap is why
    a held seat could show no debate on its stock page. (ROOT=backend/_opus_debate; both files in backend/.)"""
    out, seen = [], set()
    f = ROOT.parent / "_basket13_candidates.json"
    if f.exists():
        d = json.load(open(f, encoding="utf-8"))
        for c in (d if isinstance(d, list) else (d.get("candidates") or [])):
            if c.get("symbol"):
                out.append(c); seen.add(c["symbol"])
    t = ROOT.parent / "_basket13_tracker.json"
    if t.exists():
        trk = json.load(open(t, encoding="utf-8"))
        for e in (trk.get("entries") or []):
            s = e.get("symbol")
            if s and s not in seen and (e.get("status") or "OPEN") != "RESOLVED":
                e.setdefault("tier", "ACTIVE")
                out.append(e); seen.add(s)
    return out


def _b13_equity_special_sits():
    """Non-binary, unblocked, H/M-edge equity special-sits across the B13 universe — apex-lane eligible."""
    return [c for c in _b13_universe()
            if c.get("valuation_method") in _B13_SS_METHODS
            and c.get("edge_grade") in ("H", "M")
            and not (set(c.get("edge_flags") or []) & _B13_BLOCKING)]


def _cat_ctx(c):
    dm, dd = c.get("dated_milestone"), c.get("days_to_milestone")
    date = f"HARD DATE {dm} ({dd}d)" if dm and dd is not None else "UNDATED"
    return (f"{c.get('lane_canon','')} / {c.get('resolution_driver','')}; {date}; "
            f"live {c.get('live_price')} vs target {c.get('fair_value_target')} / floor {c.get('downside_floor')}; "
            f"{c.get('valuation_method')} R:R {c.get('computed_rr')}; edge {c.get('edge_grade')}, {c.get('tier')}")


def catalyst_prep():
    """Regenerate _catalyst_weekly.mjs over the non-binary B13 equity special-sits (reuse the prompts
    in _catalyst_debate.mjs, swap only the NAMES table). Prints WORKFLOW_SCRIPT= for the SKILL."""
    import re
    uni = _b13_universe()   # FULL book (candidates + held seats) — debate ALL for stock-page coverage
    if not uni:
        print("catalyst-prep: no B13 names (funnel + tracker) — skipping.")
        return
    rows = []
    for c in uni:
        co = (c.get("company_name") or c.get("symbol") or "")[:40]
        rows.append("  { sym:%s, co:%s, cluster:%s, label:%s, ctx:%s }," % (
            json.dumps(c.get("symbol")), json.dumps(co),
            json.dumps(c.get("super_cluster", "")), json.dumps(c.get("resolution_driver", "")),
            json.dumps(_cat_ctx(c))))
    names_js = "const NAMES = [\n" + "\n".join(rows) + "\n]"
    tmpl = (ROOT / "_catalyst_debate.mjs").read_text(encoding="utf-8")
    new = re.sub(r"const NAMES = \[.*?\n\]", names_js, tmpl, count=1, flags=re.DOTALL)
    out = ROOT / "_catalyst_weekly.mjs"
    out.write_text(new, encoding="utf-8")
    print(f"catalyst-prep: {len(uni)} B13 names (full book: candidates + held seats) -> {[c['symbol'] for c in uni]}")
    print("WORKFLOW_SCRIPT=" + str(out))


def catalyst_seed():
    """RETIRED 2026-07-08 (Bruno's directive after the 07-07 forensics): the B13 catalyst book is
    now FULLY SEPARATE from the apex — catalyst-framed results are never seeded into results_regime/.
    Why: the seed's survival assumption ("it writes other symbols; these survive") was FALSE for any
    special-sit the Director had seated — prep unions held apex names into the regime universe, the
    seat-relevant trigger forces a re-debate, and the price-blind regime record OVERWROTE the correct
    catalyst record (AAUC 07-07: a fabricated near-terms price flipped a valid A/4 arb to C/2). Two
    lanes writing one file under opposing rubrics also produced the FIP A/5->B/3 whiplash. The
    catalyst artifacts (_catalyst_results/ + _catalyst_skeptic/) remain the B13 entry gate +
    resolution radar, consumed by _basket13_gen/_basket13_inject/_basket13_mark directly."""
    print("catalyst-seed: RETIRED 2026-07-08 — B13 is fully separate from the apex; catalyst results "
          "are no longer seeded into results_regime/ (they remain the B13 gate/radar via "
          "_catalyst_results/). No-op.")


_DATED_FACT_RE = None  # compiled lazily in continuity_gate


def continuity_gate():
    """DETERMINISTIC anti-whipsaw gate (2026-07-08, runs between Debate and Director — the
    debate-layer analog of the Director's rotation ledger). Diffs each fresh results_regime/<S>.json
    against last week's _archive_prev/results_regime/<S>.json; a verdict A<->C flip or a conviction
    move >= 2 must cite a DATED fact (a YYYY-MM / 'Month YYYY' / YYYY-MM-DD reference) in
    whats_changed_since_prior (fallback: moderator_conclusion). Violators get a continuity_flag
    stamped INTO the record so the Director (and the stock page) can see the record is a re-roll,
    not an update. Flags only — never rewrites a verdict. Carried records are exempt (they ARE the
    prior record)."""
    import re as _re
    dated = _re.compile(r"\b20\d\d-\d\d(-\d\d)?\b|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s*20\d\d\b|\b(Q[1-4])\s*(FY)?\s*20\d\d\b",
                        _re.IGNORECASE)
    res, prior_dir = ROOT / "results_regime", ROOT / "_archive_prev" / "results_regime"
    if not res.exists() or not prior_dir.exists():
        print("continuity-gate: nothing to diff (missing results_regime/ or _archive_prev/). skipping.")
        return
    _rank = {"A": 3, "B": 2, "C": 1}
    checked = flagged = 0
    flags = []
    for f in sorted(res.glob("*.json")):
        try:
            cur = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if cur.get("carried"):
            continue
        pf = prior_dir / f.name
        if not pf.exists():
            continue
        try:
            pr = json.load(open(pf, encoding="utf-8"))
        except Exception:
            continue
        checked += 1
        # ── v2 (Week 2, 2026-07-10): DELTA records enforce their own contract by REVERSION, not by
        # flag. A delta update may only move a guarded field with a dated fact recorded in deltas[];
        # any other change is reverted to the anchor value (a delta that re-rolled is a bug, and
        # reverting it merely enforces what the prompt promised). A verdict change ALWAYS reverts —
        # the contract says flips escalate to a full re-debate instead. Full-debate records keep the
        # v1 flag-only behavior (reverting a fresh debate would hide real information).
        if cur.get("update_mode") == "delta":
            GUARDED = ("verdict", "conviction", "value_conviction", "catalyst_status", "sop_fair_value")
            justified = set()
            for d in (cur.get("deltas") or []):
                if isinstance(d, dict) and d.get("field") and dated.search(str(d.get("dated_fact") or "")):
                    justified.add(str(d["field"]))
            reverted = []
            for fld in GUARDED:
                if cur.get(fld) == pr.get(fld):
                    continue
                if fld == "verdict" or fld not in justified:
                    cur[fld] = pr.get(fld)
                    reverted.append(fld)
            if reverted:
                cur["delta_inherited"] = reverted
                cur["continuity_flag"] = (f"DELTA_REVERTED: {reverted} changed without a dated fact in "
                                          f"deltas[] (verdict changes always revert — escalate_full_debate "
                                          f"is the flip path) — anchor values restored")
                f.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
                flagged += 1
                flags.append(f"{f.stem} (delta-reverted: {','.join(reverted)})")
            continue
        cv, pv = _rank.get(str(cur.get("verdict") or "").strip()[:1].upper()), _rank.get(str(pr.get("verdict") or "").strip()[:1].upper())
        try:
            dconv = abs(int(cur.get("conviction")) - int(pr.get("conviction")))
        except (TypeError, ValueError):
            dconv = 0
        big_flip = (cv is not None and pv is not None and abs(cv - pv) >= 2) or dconv >= 2
        if not big_flip:
            continue
        justification = f"{cur.get('whats_changed_since_prior') or ''} {cur.get('moderator_conclusion') or ''}"
        if dated.search(justification) and (cur.get("whats_changed_since_prior") or "").strip():
            continue                              # flip carries a dated fact — legitimate update
        prior_date = str(pr.get("debated_at") or pr.get("as_of") or "")[:10]
        cur["continuity_flag"] = (f"UNJUSTIFIED_FLIP vs {prior_date or 'prior run'}: "
                                  f"{pr.get('verdict')}/{pr.get('conviction')} -> "
                                  f"{cur.get('verdict')}/{cur.get('conviction')} with no dated fact in "
                                  f"whats_changed_since_prior — treat this record as a re-roll, prefer the prior grade")
        f.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        flagged += 1
        flags.append(f"{f.stem} ({pr.get('verdict')}/{pr.get('conviction')}->{cur.get('verdict')}/{cur.get('conviction')})")
    print(f"continuity-gate: {checked} diffed vs prior week | {flagged} FLAGGED unjustified flips"
          + (f": {flags}" if flags else " — all changes carry dated facts or are within tolerance"))


def coverage_merge():
    """DETERMINISTIC Tier-C merge (Week 2): fold each _coverage_updates/<SYM>.json into
    results_regime/<SYM>.json by COPYING the standing record verbatim (verdict/conviction/sop are
    INHERITED — the coverage agent's schema has no grade fields, and this merge is the enforcement),
    restamping the live price/as_of, and appending the structured update block. escalate=true rides
    into the record so next week's change-detection gate (T6) routes the name to a full debate."""
    prior_dir = ROOT / "_archive_prev" / "results_regime"
    upd_dir = ROOT / "_coverage_updates"
    if not upd_dir.exists():
        print("coverage-merge: no _coverage_updates/ — nothing to merge.")
        return
    merged, escal, orphans = [], [], []
    for f in sorted(upd_dir.glob("*.json")):
        sym = f.stem
        try:
            upd = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            print(f"WARN coverage-merge: {f.name} unreadable ({e})")
            continue
        pf = prior_dir / f"{sym}.json"
        if not pf.exists():
            orphans.append(sym)                    # no standing record to inherit from — nothing to publish
            continue
        try:
            rec = json.load(open(pf, encoding="utf-8"))
        except Exception:
            orphans.append(sym)
            continue
        if isinstance(upd.get("live_price"), (int, float)):
            rec["live_price"] = upd["live_price"]
        rec["as_of"] = upd.get("as_of") or datetime.now().strftime("%Y-%m-%d")
        rec["tier"] = "coverage"
        rec["update_mode"] = "refresh"
        rec["carried_from"] = str(rec.get("debated_at") or rec.get("as_of") or "")[:10]
        rec["coverage_update"] = {k: upd.get(k) for k in
                                  ("as_of", "live_price", "price_currency", "whats_new",
                                   "catalyst_status_check", "thesis_update", "escalate", "escalate_reason")}
        (RES / f"{sym}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        merged.append(sym)
        if upd.get("escalate"):
            escal.append(sym)
    print(f"coverage-merge: {len(merged)} Tier-C records merged (grades inherited verbatim) | "
          f"escalations={escal or 'none'}"
          + (f" | orphans (no standing record, skipped): {orphans}" if orphans else ""))


# ── COHORT LEDGER (2026-07-10) — the accountability mechanism: does conviction/verdict/a skeptic
# kill actually predict forward returns? Local-only (NEVER Cloud Run, per standing rule); run as the
# LAST step of the weekly SKILL (after value-publish), so results_regime/ + both apex baskets +
# skeptic shards are this run's settled state (prep's self-clean archives them before the next run).
# "tier"/"mode" record TODAY's carry-vs-debate distinction (carried/debated/recheck); once the
# two-tier restructure ships they start writing underwrite/delta/coverage into the SAME fields —
# no ledger schema change needed.
COHORT_LEDGER = ROOT / "_cohort_ledger.jsonl"
COHORT_HORIZONS = {"4w": 28, "12w": 84, "26w": 182}   # trading-calendar-agnostic; deliberately simple


def _cohort_load():
    rows = []
    if COHORT_LEDGER.exists():
        for line in COHORT_LEDGER.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _cohort_write(rows):
    rows = sorted(rows, key=lambda r: (r.get("run_date") or "", r.get("symbol") or ""))
    COHORT_LEDGER.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return rows


def _cohort_seat_map():
    """symbol -> seat label (regime_apex/regime_runner/value_apex/value_runner/none), from both
    published apex baskets. A name in both books gets a combined label (e.g. 'regime_apex+value_apex')."""
    seat = {}

    def _add(path, apex_lbl, runner_lbl):
        try:
            d = json.load(open(ROOT / path, encoding="utf-8"))
        except Exception:
            return
        for p in (d.get("apex_basket") or []):
            s = p.get("symbol") if isinstance(p, dict) else p
            if s:
                seat[s] = apex_lbl if s not in seat else seat[s] + "+" + apex_lbl
        for p in (d.get("runner_ups") or []):
            s = p.get("symbol") if isinstance(p, dict) else p
            if s and s not in seat:
                seat[s] = runner_lbl
    _add("apex_basket_opus_regime.json", "regime_apex", "regime_runner")
    _add("apex_basket_value.json", "value_apex", "value_runner")
    return seat


def _cohort_skeptic_map():
    """symbol -> (verdict, kill_scope), regime shard preferred over value shard when both exist
    (the cross-book dedupe means a value finalist's shard is often just a carried copy of regime's)."""
    out = {}
    for d in ("_skeptic_regime", "_skeptic"):
        p = ROOT / d
        if not p.exists():
            continue
        for f in p.glob("*.json"):
            try:
                r = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            sym = r.get("symbol") or f.stem
            if sym not in out:
                out[sym] = (r.get("verdict") or "none", r.get("kill_scope") or "")
    return out


def cohort_mark():
    """Append this run's per-name snapshot (idempotent per run-date+symbol), fill any NOW-due forward-
    return horizon on existing rows using fresh FMP quotes, then print + write cohort_report.md."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    ledger = _cohort_load()
    already = {(r.get("run_date"), r.get("symbol")) for r in ledger}
    seat_map = _cohort_seat_map()
    skeptic_map = _cohort_skeptic_map()
    fmp_key = E.get_key("FMP_API_KEY")
    spy0 = (_numeric_core.fetch_live_quotes(["SPY"], fmp_key=fmp_key) or {}).get("SPY")

    new_rows = 0
    res_dir = ROOT / "results_regime"
    if res_dir.exists():
        for f in sorted(res_dir.glob("*.json")):
            sym = f.stem
            if (today, sym) in already:
                continue
            try:
                rec = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            skv, sksc = skeptic_map.get(sym, ("none", ""))
            carried = bool(rec.get("carried"))
            ledger.append({
                "run_date": today, "symbol": sym,
                "tier": "carried" if carried else "debated",
                "mode": "carry" if carried else ("recheck" if rec.get("source") == "ledger_recheck" else "full"),
                "verdict": rec.get("verdict"), "conviction": rec.get("conviction"),
                "value_conviction": rec.get("value_conviction"),
                "seat": seat_map.get(sym, "none"), "skeptic": skv, "kill_scope": sksc,
                "continuity_flag": bool(rec.get("continuity_flag")),
                "numeric_flag": None,          # populated once the numeric-integrity gate ships (Week 0.4+)
                "price0": rec.get("live_price"), "spy0": spy0,
                "px_4w": None, "r_4w": None, "px_12w": None, "r_12w": None, "px_26w": None, "r_26w": None,
                "xs_4w": None, "xs_12w": None, "xs_26w": None,
                "backfilled": False,
            })
            new_rows += 1

    # ---- fill any horizon that's now due, using fresh quotes (skip backfilled/price-less rows) ----
    due_syms = set()
    for r in ledger:
        if r.get("backfilled") or not isinstance(r.get("price0"), (int, float)):
            continue
        try:
            age_d = (_dt.date.today() - _dt.date.fromisoformat(r["run_date"])).days
        except Exception:
            continue
        if any(age_d >= days and r.get(f"r_{hz}") is None for hz, days in COHORT_HORIZONS.items()):
            due_syms.add(r["symbol"])
    quotes = _numeric_core.fetch_live_quotes(sorted(due_syms), fmp_key=fmp_key) if due_syms else {}
    spy_curr = (_numeric_core.fetch_live_quotes(["SPY"], fmp_key=fmp_key) or {}).get("SPY") if due_syms else None
    filled = 0
    for r in ledger:
        if r["symbol"] not in due_syms:
            continue
        px_now = quotes.get(str(r["symbol"]).upper())
        if px_now is None:
            continue
        try:
            age_d = (_dt.date.today() - _dt.date.fromisoformat(r["run_date"])).days
        except Exception:
            continue
        for hz, days in COHORT_HORIZONS.items():
            if age_d >= days and r.get(f"r_{hz}") is None:
                r[f"px_{hz}"] = px_now
                r[f"r_{hz}"] = round((px_now / r["price0"] - 1) * 100, 2)
                if r.get("spy0") and spy_curr:
                    r[f"xs_{hz}"] = round(r[f"r_{hz}"] - (spy_curr / r["spy0"] - 1) * 100, 2)
                filled += 1

    ledger = _cohort_write(ledger)
    print(f"cohort-mark: {new_rows} new row(s) appended | {filled} horizon(s) filled | "
          f"ledger={len(ledger)} rows -> {COHORT_LEDGER.name}")
    _cohort_report(ledger)


def _cohort_report(ledger):
    """forward return by conviction bucket / verdict / tier, and the KILL LEDGER (skeptic REFUTED vs
    CONFIRMED forward returns) — the pre-registered accountability check (see the pipeline-v3 plan):
    after ~12 weeks, if conviction 4-5 doesn't beat 1-2 on excess return AND kills don't underperform
    confirms, the debate layer is not earning its cost."""
    def _bucket(c):
        return "4-5" if isinstance(c, (int, float)) and c >= 4 else ("3" if c == 3 else ("1-2" if isinstance(c, (int, float)) else "?"))

    def _stats(rows, key):
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        if not vals:
            return "n=0 (not yet due)"
        vals.sort()
        return f"n={len(vals)} median={vals[len(vals) // 2]:+.1f}% mean={sum(vals) / len(vals):+.1f}%"

    lines = ["# Speculair Cohort Report", f"Generated from {len(ledger)} ledger rows "
             f"({sum(1 for r in ledger if r.get('backfilled'))} backfilled, no price/return data).\n"]
    for hz in ("4w", "12w", "26w"):
        lines.append(f"## {hz} excess return by conviction bucket")
        for b in ("1-2", "3", "4-5"):
            lines.append(f"  conviction {b}: {_stats([r for r in ledger if _bucket(r.get('conviction')) == b], f'xs_{hz}')}")
        lines.append(f"## {hz} excess return by verdict")
        for v in ("A", "B", "C"):
            lines.append(f"  verdict {v}: {_stats([r for r in ledger if r.get('verdict') == v], f'xs_{hz}')}")
        lines.append(f"## {hz} KILL LEDGER — skeptic verdict vs forward excess return")
        for sk in ("CONFIRMED", "CONFIRMED_WITH_CORRECTIONS", "REFUTED"):
            lines.append(f"  {sk}: {_stats([r for r in ledger if r.get('skeptic') == sk], f'xs_{hz}')}")
        lines.append("")
    out = ROOT / "cohort_report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"-> {out.name}")


def cohort_backfill():
    """Seed HISTORICAL verdict/conviction/tier rows from GCS speculair_debate_history/<SYM>.json
    (each carries up to 12 dated entries already, per the weekly append). These entries do NOT carry
    a price, so backfilled rows get price0=None + all forward-returns=None + backfilled=True — they
    feed the verdict/conviction distribution in the report but NEVER the return statistics (which
    would require fabricating a historical price). Idempotent on (run_date, symbol)."""
    ledger = _cohort_load()
    already = {(r.get("run_date"), r.get("symbol")) for r in ledger}
    hist_dir = E.FRONTEND_DIR / "public" / "speculair_debate_history"
    added = 0
    if hist_dir.exists():
        for f in hist_dir.glob("*.json"):
            sym = f.stem
            try:
                entries = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(entries, list):
                continue
            for e in entries:
                d = e.get("date")
                if not d or (d, sym) in already:
                    continue
                ledger.append({
                    "run_date": d, "symbol": sym, "tier": "n/a", "mode": "n/a",
                    "verdict": e.get("verdict"), "conviction": e.get("conviction"),
                    "value_conviction": e.get("value_conviction"),
                    "seat": "unknown", "skeptic": "none", "kill_scope": "",
                    "continuity_flag": False, "numeric_flag": None,
                    "price0": None, "spy0": None,
                    "px_4w": None, "r_4w": None, "px_12w": None, "r_12w": None, "px_26w": None, "r_26w": None,
                    "xs_4w": None, "xs_12w": None, "xs_26w": None,
                    "backfilled": True,
                })
                already.add((d, sym))
                added += 1
    ledger = _cohort_write(ledger)
    print(f"cohort-backfill: {added} historical row(s) seeded from speculair_debate_history/ "
          f"(verdict/conviction only, no price/return data) -> {len(ledger)} total ledger rows")


def lane_stamp():
    """Deterministic post-debate lane stamp (2026-07-17, neglect lane). Fresh debate records are
    written by the agents against the step-7 schema, which carries no lane field — so after the
    debate, stamp lane="neglect_orphan" onto results_regime/<SYM>.json wherever the prep bundle
    carried the tag. Zero prompt changes: value_input() and skeptic_gen() read the stamped field,
    and carries preserve it automatically (the carry-restamp copies the whole prior record).
    Idempotent; runs in the Gates phase alongside coverage-merge/continuity-gate."""
    n = 0
    for f in sorted(INP.glob("*.json")):
        try:
            b = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if "neglect_orphan" not in (b.get("methodologies") or []):
            continue
        rp = RES / f"{b.get('symbol')}.json"
        if not rp.exists():
            continue
        try:
            rec = json.load(open(rp, encoding="utf-8"))
        except Exception:
            continue
        if rec.get("lane") != "neglect_orphan":
            rec["lane"] = "neglect_orphan"
            rp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            n += 1
    print(f"lane-stamp: {n} results_regime record(s) stamped lane=neglect_orphan")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "prep"
    # DISRUPTOR LENS retired 2026-07-02 (FUTURE_RESOURCES_SPEC.md §10); its code was DELETED 2026-07-10
    # (pipeline-v3 redundancy removal — the functions themselves are gone, this is just a friendly
    # message so an operator who still types a disruptor-* command from habit/old docs gets a clear
    # explanation instead of "unknown mode". The old ALLOW_DISRUPTOR=1 escape hatch no longer does
    # anything (there is no archived pipeline left to force-run) — restore from git history if the
    # Disruptor Lens is ever needed forensically.
    if mode.replace("_", "-").startswith("disruptor"):
        print(f"DISRUPTOR LENS RETIRED 2026-07-02, code deleted 2026-07-10 (FUTURE_RESOURCES_SPEC.md "
              f"§10) — mode '{mode}' no longer exists. See git history to restore for forensic use.")
        sys.exit(0)
    if mode == "prep":
        prep()
    elif mode == "merge":
        merge_radar()
    elif mode in ("peer-overrides", "peer_overrides"):
        peer_overrides_restamp(push_frontend=("--frontend" in sys.argv or "--gcs" in sys.argv))
    elif mode == "export-csv":
        export_debate_csv()
    elif mode == "finish":
        finish_debate()
    elif mode == "value-input":
        value_input()
    elif mode == "value-csv":
        value_csv()
    elif mode == "baskets-csv":
        baskets_csv()
    elif mode in ("value-post", "value_post"):
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "_value_post.py")] + (["--offline"] if "--offline" in sys.argv else []), check=True)
    elif mode in ("regime-post", "regime_post"):
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "_regime_post.py")] + (["--offline"] if "--offline" in sys.argv else []), check=True)
    elif mode in ("numeric-gate", "numeric_gate"):
        import subprocess
        extra = [a for a in ("--legacy", "--dry-run", "--offline", "--enforce", "--final") if a in sys.argv]
        if "--dry-run" not in extra and "--enforce" not in extra:
            extra.append("--dry-run")   # safe default: report-only unless enforcement is explicitly asked for
        subprocess.run([sys.executable, str(ROOT / "_numeric_gate.py")] + extra, check=True)
    elif mode in ("lane-stamp", "lane_stamp"):
        lane_stamp()
    elif mode in ("value-revalidate", "value_revalidate"):
        value_revalidate()
    elif mode in ("fr-universe", "fr_universe"):
        fr_universe()
    elif mode in ("fr-map", "fr_map"):
        fr_map()
    elif mode in ("fr-map-merge", "fr_map_merge"):
        fr_map_merge()
    elif mode in ("fr-prep", "fr_prep"):
        fr_prep()
    elif mode in ("fr-input", "fr_input"):
        fr_input()
    elif mode in ("fr-numeric-gate", "fr_numeric_gate"):
        fr_numeric_gate()
    elif mode in ("fr-post", "fr_post"):
        # value-post pattern: the deterministic post layer runs as a subprocess with --offline passthrough
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "_fr_post.py")] + (["--offline"] if "--offline" in sys.argv else []), check=True)
    elif mode in ("fr-csv", "fr_csv"):
        fr_csv()
    elif mode == "fr-publish":
        fr_publish(push_gcs=("--gcs" in sys.argv))
    elif mode in ("value-skeptic", "value_skeptic"):
        value_skeptic()
    elif mode in ("regime-skeptic", "regime_skeptic"):
        regime_skeptic()
    elif mode in ("catalyst-prep", "catalyst_prep"):
        catalyst_prep()
    elif mode in ("catalyst-seed", "catalyst_seed"):
        catalyst_seed()
    elif mode in ("continuity-gate", "continuity_gate"):
        continuity_gate()
    elif mode in ("coverage-merge", "coverage_merge"):
        coverage_merge()
    elif mode in ("control-sample", "control_sample"):
        control_sample()
    elif mode in ("cohort-mark", "cohort_mark"):
        cohort_mark()
    elif mode in ("cohort-backfill", "cohort_backfill"):
        cohort_backfill()
    elif mode == "value-publish":
        value_publish(push_gcs=("--gcs" in sys.argv))
    else:
        print(f"unknown mode: {mode}")
        sys.exit(1)
