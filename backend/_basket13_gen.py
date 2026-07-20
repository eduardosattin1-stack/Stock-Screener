#!/usr/bin/env python3
"""Basket 13 — Catalyst sleeve: the two-phase catalyst-native debate generator.

Writes _basket13_workflow.js (run it with the Workflow tool). Patterned on _valuation_gen.py.

  Phase 0 — Deep-Dossier refresh (one agent per candidate): re-underwrites the board dossier's
            LOAD-BEARING fields (catalyst status/milestone, fair_value_target, downside_floor,
            driver, staging) from live sources BEFORE the trade stages consume them. The board
            dossier is a single-pass Sonnet backend scan and can be stale/wrong; this phase is
            the Claude-Code multi-agent replacement for trusting it. Corrected values REPLACE
            the board fields (originals kept under board_*); _basket13_inject.py applies the
            same overrides so validation + stamped entries match what the Director sized on.
  Phase 1 — Catalyst-CRO (one agent per candidate, batched ~5): attacks the TRADE on exactly
            FOUR surfaces — edge-at-entry, tradeability, window<->expression, driver-tag.
            It NEVER re-litigates whether the event is real (Phase 0 just settled that live)
            and NEVER attacks value/quality axes (a catalyst name is supposed to look bad on
            MoS/quality by construction).
  Phase 2 — Catalyst Director: selects + sizes from the CRO survivors under HARD caps.

Both phases run on Opus 4.8 (model:'opus') — Fable was retired from this seat 2026-07-10
(pipeline-v3 plan, Week 1: Fable retired from every seat in both the weekly Speculair
pipeline and B13). It ran on Fable 5 from 2026-06-xx to 2026-07-10; that leg is done.

The deterministic cap enforcement is NOT here — the Director does its best and
_basket13_inject.py re-asserts every cap before stamping (the LLM proposes, the inject
validates). Output capture: the workflow returns {cro, director, ...}; feed it to
_basket13_inject.py.

Usage:
  python _basket13_gen.py                 # all _basket13_candidates.json
  python _basket13_gen.py --only CELC,FIP,MGNI
"""
import json, os, argparse, datetime
BASE = os.path.dirname(os.path.abspath(__file__))
CAND = os.path.join(BASE, "_basket13_candidates.json")
OUT  = os.path.join(BASE, "_basket13_workflow.js")
ap = argparse.ArgumentParser()
ap.add_argument("--only", default="")
ap.add_argument("--model", default="opus",
                help="agent model alias for both phases (Fable retired from this seat 2026-07-10)")
ap.add_argument("--held-dossiers", action="store_true", dest="held_dossiers",
                help="HELD-BOOK REFRESH mode: candidates = the tracker's unresolved seats (rows built "
                     "from their stamped fields), workflow = DeepDossier phase ONLY (no CRO/Director, "
                     "no stamping). Feed the output to `_basket13_inject.py merge-dossiers` to update "
                     "the store + surface FIRED/SLIPPED alerts on held seats.")
ap.add_argument("--promote", default="",
                help="SYM — EVENT-TRIGGERED single-seat promotion (2026-07-14): a resolve freed cap "
                     "headroom and _basket13_inject.py's headroom scan named this on-deck first-in-line. "
                     "Same 3-phase workflow restricted to the one name; the Director is told it is a "
                     "promotion and re-nominates the rest of the on-deck book unchanged; inject "
                     "re-asserts every combined cap before stamping. Falls back to the persistent "
                     "on-deck cache when the name has rotated off the current board extract.")
args = ap.parse_args()
MODEL = args.model   # both phases; default opus (Fable retired from this seat 2026-07-10)

only = {s.strip().upper() for s in args.only.split(",") if s.strip()}
PROMOTE = args.promote.strip().upper()
if PROMOTE:
    only = {PROMOTE}
if args.held_dossiers:
    # held seats aren't in the candidates file (--exclude-held); build rows from the tracker
    _trk = json.load(open(os.path.join(BASE, "_basket13_tracker.json"), encoding="utf-8"))
    cands = [{"symbol": e["symbol"], "company_name": None, "tier": "held_seat",
              "staging": e.get("staging"), "lane_canon": e.get("lane_canon"),
              "resolution_driver": e.get("resolution_driver"), "super_cluster": e.get("super_cluster"),
              "edge_grade": e.get("edge_grade"), "valuation_method": e.get("valuation_method"),
              "computed_rr": e.get("computed_rr"), "ev_pct": e.get("ev_pct"), "payoff": None,
              "win_prob": None, "fair_value_target": e.get("fair_value_target"),
              "downside_floor": e.get("downside_floor"), "live_price": e.get("entry_price"),
              "dated_milestone": e.get("dated_milestone"), "days_to_milestone": None,
              "instrument": (e.get("expression") or {}).get("type"),
              "valuation_asof": e.get("entry_date"), "score": e.get("score")}
             for e in _trk.get("entries", []) if not e.get("resolution")]
else:
    cands = json.load(open(CAND, encoding="utf-8"))["candidates"]
if only:
    cands = [c for c in cands if c["symbol"].upper() in only]

if PROMOTE:
    _trk_p = json.load(open(os.path.join(BASE, "_basket13_tracker.json"), encoding="utf-8"))
    if any(e["symbol"] == PROMOTE and not e.get("resolution") for e in _trk_p.get("entries", [])):
        raise SystemExit(f"--promote {PROMOTE}: already a live held seat — nothing to promote")
    _stp = (_trk_p.get("watchlist_state") or {}).get(PROMOTE)
    if not _stp:
        raise SystemExit(f"--promote {PROMOTE}: not on the on-deck watchlist — promotion is only for "
                         "the Director's prior nominations (run `_basket13_inject.py headroom` for the queue)")
    if not cands:
        # rotated off the current board extract — synthesize the row from the persistent on-deck
        # cache (same pattern as --held-dossiers; the DeepDossier phase re-underwrites the
        # load-bearing fields from live sources anyway, so cache staleness is self-correcting)
        _wlp = next((w for w in _trk_p.get("watchlist", []) if w.get("symbol") == PROMOTE), {})
        cands = [{"symbol": PROMOTE, "company_name": None, "tier": "on_deck_promotion",
                  "staging": bool(_stp.get("staging")), "lane_canon": _stp.get("lane_canon"),
                  "resolution_driver": _stp.get("resolution_driver") or _wlp.get("resolution_driver"),
                  "super_cluster": _stp.get("super_cluster") or _wlp.get("super_cluster"),
                  "edge_grade": _wlp.get("edge_grade"), "valuation_method": _stp.get("valuation_method"),
                  "computed_rr": _stp.get("computed_rr"), "ev_pct": _stp.get("ev_pct"), "payoff": None,
                  "win_prob": None, "fair_value_target": None, "downside_floor": None,
                  "live_price": _stp.get("entry_price"), "dated_milestone": _stp.get("dated_milestone"),
                  "days_to_milestone": None, "instrument": (_stp.get("expression") or {}).get("type"),
                  "valuation_asof": _stp.get("entry_date"), "score": None}]

# compact field set the agents read
FIELDS = ["symbol", "company_name", "tier", "staging", "lane_canon", "resolution_driver",
          "super_cluster", "edge_grade", "valuation_method", "computed_rr", "ev_pct", "payoff",
          "win_prob", "fair_value_target", "downside_floor", "live_price", "dated_milestone",
          "days_to_milestone", "instrument", "valuation_asof", "score"]
names = [{k: c.get(k) for k in FIELDS} for c in cands]

# WEEKLY FULL-STACK CATALYST DIAGNOSIS join (2026-07-01): the weekly catalyst workflow already
# debates the WHOLE B13 book (Interrogator/Architect/CRO + adversarial Skeptic) — and B13 consumed
# none of it (GDOT sat OPEN at 14% with a Skeptic-REFUTED shard; AQST at 4.5% on a SOFT_EXTENDED
# catalyst). Attach each candidate's latest diagnosis so the CRO/Director SEE it; the inject layer
# (_basket13_inject.validate) additionally hard-rejects fresh REFUTED/FIRED at entry.
import time as _time
_CATRES = os.path.join(BASE, "_opus_debate", "_catalyst_results")
_CATSKP = os.path.join(BASE, "_opus_debate", "_catalyst_skeptic")
DIAG_FRESH_DAYS = 10   # ONE freshness window, shared with _basket13_inject (red-team condition)


def _diag_for(sym):
    out = {}
    for d, keys, tag in ((_CATRES, ("catalyst_status", "verdict", "conviction", "dated_milestone"), "debate"),
                         (_CATSKP, ("verdict", "kill_fact", "conviction_cap"), "skeptic")):
        f = os.path.join(d, f"{sym}.json")
        if not os.path.exists(f):
            continue
        try:
            j = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        age_d = (_time.time() - os.path.getmtime(f)) / 86400
        out[tag] = {k: j.get(k) for k in keys if j.get(k) is not None}
        out[tag]["age_days"] = round(age_d, 1)
        out[tag]["fresh"] = bool(age_d <= DIAG_FRESH_DAYS)
    return out or None


_n_diag = 0
for _n in names:
    _d = _diag_for(_n["symbol"])
    if _d:
        _n["weekly_diagnosis"] = _d
        _n_diag += 1
print(f"weekly catalyst diagnosis joined: {_n_diag}/{len(names)} candidates carry weekly_diagnosis")

# locked held book (any UNRESOLVED tracker entry): a re-debate ADDS new seats within the
# REMAINING combined-cap headroom; held names run to resolution and consume caps. The Director
# is told the headroom; _basket13_inject.py re-asserts the combined book deterministically.
TRK = os.path.join(BASE, "_basket13_tracker.json")
held = []
if os.path.exists(TRK):
    held = [e for e in json.load(open(TRK, encoding="utf-8")).get("entries", []) if not e.get("resolution")]
by_drv, by_clus = {}, {}
for e in held:
    by_drv[e.get("resolution_driver")] = by_drv.get(e.get("resolution_driver"), 0) + 1
    by_clus[e.get("super_cluster")] = round(by_clus.get(e.get("super_cluster"), 0.0) + (e.get("weight_pct") or 0), 2)
held_summary = {
    "names": [{"symbol": e["symbol"], "weight_pct": e.get("weight_pct"), "driver": e.get("resolution_driver"),
               "super_cluster": e.get("super_cluster"), "status": e.get("status", "OPEN")} for e in held],
    "n_seats": len(held), "by_driver": by_drv, "by_cluster": by_clus,
    "invested_pct": round(sum(e.get("weight_pct") or 0 for e in held), 1),
}

# PRIOR on-deck watchlist — the Director is ACCOUNTABLE to the names he nominated last run. The
# watchlist is a PERSISTENT book (_basket13_inject.build_watchlist): carried names are tracked to
# resolution, so the Director must reconcile his new nominations against them and JUSTIFY any stance
# change (de-prioritize / re-champion) — mirroring the Speculair _decision_history.json discipline.
# Compact fields only (symbol/stance/date/blocked_by), to bound token cost as the carried set grows.
prior_wl = []
if os.path.exists(TRK):
    for w in json.load(open(TRK, encoding="utf-8")).get("watchlist", []):
        prior_wl.append({"symbol": w["symbol"], "de_prioritized": bool(w.get("de_prioritized")),
                         "entry_date": w.get("entry_date"), "expected_pct": w.get("expected_pct"),
                         "prior_blocked_by": w.get("blocked_by")})
watchlist_ctx = {"n_on_deck": len(prior_wl), "names": prior_wl}

JS = r'''export const meta = {
  name: 'basket13-catalyst-debate',
  description: 'Basket 13 catalyst sleeve — Catalyst-CRO trade attack (4 surfaces) then Director selection+sizing under hard caps',
  phases: [ { title: 'DeepDossier', model: '__MODEL__' }, { title: 'CatalystCRO', model: '__MODEL__' }, { title: 'Director', model: '__MODEL__' } ],
}
const NAMES = __NAMES__
const MODEL = '__MODEL__'
const HELD = __HELD__
const WATCHLIST = __WATCHLIST__

const DOSSIER_SCHEMA = { type:'object', properties:{
  symbol:{type:'string'},
  catalyst_live:{type:'boolean'},
  catalyst_status:{type:'string', enum:['PENDING_HARD','PENDING_SOFT','SLIPPED','FIRED','BROKEN']},
  thesis_summary:{type:'string'},
  dated_milestone:{type:['string','null']},
  fair_value_target:{type:['number','null']},
  downside_floor:{type:['number','null']},
  valuation_method:{type:['string','null']},
  win_prob:{type:['number','null']},
  resolution_driver:{type:'string'},
  staging:{type:'boolean'},
  discrepancies:{type:'array', items:{type:'string'}},
  kill_risk:{type:['string','null']},
  dossier_note:{type:'string'}
}, required:['symbol','catalyst_live','catalyst_status','thesis_summary','resolution_driver','staging','discrepancies','dossier_note'] }

function dossierPrompt(n){ return `Today is __TODAY__. You are the DEEP-DOSSIER agent for "Basket 13", an event-driven special-situations sleeve. You handle ONE candidate. The board dossier below came from an older single-pass backend scan and may be stale or wrong; downstream, a CRO adjudicates the trade and a Director sizes seats ON YOUR NUMBERS — your corrected fields REPLACE the board's. Re-underwrite the load-bearing facts from LIVE sources (5-10 lookups via ToolSearch: FMP quote/news/press-releases/SEC filings/earnings calendar; WebSearch to confirm anything the feeds don't settle):

1) CATALYST REALITY & STATUS. Confirm the resolving event is real, forward-dated, UNFIRED, and idiosyncratic (resolves on its own facts, not the tape). Emit catalyst_status: PENDING_HARD (dated + binding), PENDING_SOFT (real but undated/soft), SLIPPED (timeline pushed — name from->to in dossier_note), FIRED (already resolved — edge spent), BROKEN (deal dead / thesis invalidated). catalyst_live=false for FIRED/BROKEN.
2) MILESTONE. Verify dated_milestone against the latest company/regulator communication; correct it if it slipped or firmed; null if genuinely undated (then staging=true).
3) VALUATION AXES. Re-derive fair_value_target and downside_floor under the dossier's valuation_method — spread: live deal terms incl. FX; sop/recovery: name the components; binary_prob: win/lose prices and win_prob. If you cannot reproduce a board number from the live record, CORRECT it and show the arithmetic in dossier_note. Only emit numbers you can defend. DECK-MARK GATE (commodity-linked SoP/NAV names): if the target rests on a feasibility-study or broker price deck, check the deck against the LIVE commodity tape; if spot is materially below deck, compute a SPOT-MARKED target variant (prefer the issuer's own published NPV sensitivity over margin-scaling — NPV compresses faster than margin) and state BOTH numbers plus the spot-deck R:R in dossier_note; the deck-price target is a conditional cap, not fair value.
4) DRIVER + STAGING. Confirm or correct resolution_driver and staging (dated hard event -> staging=false; soft/undated -> true). resolution_driver is a CANONICAL TAG consumed by a deterministic <=2-per-driver cap — keep the board's tag or correct it to ANOTHER canonical snake_case tag (e.g. FDA_clinical_readout, FDA_approval_decision, US_antitrust, Deal_close_generic, Refi_restructuring, Forced_divest_flow, Spin_index_flow, Activist_process, Supply_timing, Foreign_regulator); NEVER free prose — nuance goes in dossier_note.
5) SKEPTIC PASS on yourself. Take the single most load-bearing claim in your thesis_summary — try to refute it from the live record; put the honest residual risk in kill_risk (null only if nothing credible).

DO NOT: value/quality/moat opinions, trade verdicts, position sizing, or option-chain work — the CRO owns tradeability/window and the Director owns sizing. You own FACTS and VALUATION AXES only.
List every field you changed in discrepancies[] as "field: board X -> live Y — why". Then emit ONE StructuredOutput per the schema.

CANDIDATE (board dossier, may be stale): ${JSON.stringify(n)}` }

const CRO_SCHEMA = { type:'object', properties:{ verdicts:{ type:'array', items:{ type:'object', properties:{
  symbol:{type:'string'},
  verdict:{type:'string', enum:['TRADE','TRADE_WITH_CONDITIONS','NO_TRADE']},
  live_price:{type:'number'},
  live_edge_check:{type:'string'},
  tradeability_note:{type:'string'},
  window_note:{type:'string'},
  conditions:{type:'array', items:{type:'string'}},
  driver_confirmed:{type:'string'}
}, required:['symbol','verdict','live_edge_check'] } } }, required:['verdicts'] }

const DIRECTOR_SCHEMA = { type:'object', properties:{
  picks:{ type:'array', items:{ type:'object', properties:{
    symbol:{type:'string'},
    weight_pct:{type:'number'},
    expression:{ type:'object', properties:{ type:{type:'string', enum:['equity','leaps','defined_risk_option','debit_spread']}, expiry:{type:'string'}, strikes:{type:'string'} }, required:['type'] },
    entry_rationale:{type:'string'},
    resolution_driver:{type:'string'},
    super_cluster:{type:'string'},
    expected_rr:{type:['number','null']}, expected_ev:{type:['number','null']},
    invalidation:{type:'string'},
    review_trigger:{type:'string'},
    stance_change_rationale:{type:['string','null']}
  }, required:['symbol','weight_pct','expression','resolution_driver'] } },
  passed:{ type:'array', items:{ type:'object', properties:{ symbol:{type:'string'}, passed_because:{type:'string'} }, required:['symbol','passed_because'] } },
  watchlist:{ type:'array', items:{ type:'object', properties:{ symbol:{type:'string'}, blocked_by:{type:'string'}, would_enter_if:{type:'string'}, intended_weight_pct:{type:['number','null']}, note:{type:'string'}, stance_change_rationale:{type:['string','null']} }, required:['symbol','blocked_by'] } },
  memo:{type:'string'}
}, required:['picks','passed'] }

function croPrompt(batch){ return `Today is __TODAY__. You are the CATALYST-CRO for "Basket 13", an event-driven special-situations sleeve. The catalyst's REALITY is ALREADY SETTLED upstream — each name below was re-underwritten TODAY by a deep-dossier agent (see its fresh_dossier field: live-verified catalyst status, milestone, valuation axes; corrected values already REPLACE the stale board numbers, originals under board_*). DO NOT re-litigate whether the event is real — but a fresh_dossier.catalyst_status of FIRED or BROKEN means the edge is GONE: verdict NO_TRADE citing the dossier, no further work on that name. You adjudicate exactly ONE question: IS THE TRADE GOOD? — on these FOUR surfaces and NOTHING else:

1) EDGE AT ENTRY (perishable). Re-verify the spread / R:R against the LIVE price NOW (fetch the current quote via FMP/ToolSearch). The dossier built its edge at "valuation_asof"; a spread that was 8% last week can be 1% today. State the recomputed number + source in live_edge_check, AND emit the verified live underlying price as the NUMBER field live_price — the tracker stamps entries at YOUR verified price, so it must be exact. If the edge has compressed below ~half the dossier R:R, that alone is NO_TRADE or TRADE_WITH_CONDITIONS. DUAL-DECK KILL-LINE: if fresh_dossier carries a spot-marked target variant (commodity-deck SoP names), run the R:R test on BOTH the build-deck and spot-marked targets — passing deck-only while failing at spot is at best TRADE_WITH_CONDITIONS with an explicit deck condition (e.g. "valid only if <commodity> recovers toward the FS deck"), never a clean TRADE.
2) TRADEABILITY. Does the expression exist at acceptable cost? Options: quoted bid/ask spread, open interest, strikes near the thesis levels (fair_value_target / downside_floor) — read-only via IBKR/FMP/ToolSearch. Equity: ADV vs a realistic position; borrow if any short leg. A correct thesis in an instrument with a 15%-wide spread or no OI is NOT a trade — say so in tradeability_note.
3) WINDOW <-> EXPRESSION. Does a tradeable expiry clear the catalyst date ("dated_milestone", ~"days_to_milestone" days away) with margin — at least +1 monthly expiry PAST the milestone? Has this catalyst's date slipped before? A real catalyst too slow for its option is a loss with a correct thesis. Put the read in window_note. (Staging names are undated/soft -> equity; note that.)
4) DRIVER TAG. Confirm or correct "resolution_driver" in driver_confirmed; if a SECOND name in this batch resolves on the SAME driver, flag it (the Director enforces the cap; you just flag).
WEEKLY DIAGNOSIS OVERRIDE (the one exception to "reality is settled upstream"): where a name carries "weekly_diagnosis" (the weekly full-stack catalyst debate + adversarial skeptic over this very book), treat it as CURRENT catalyst intelligence — a FRESH skeptic verdict of REFUTED, or catalyst_status FIRED/ARB (trading through terms), means the event edge is GONE: verdict NO_TRADE with the diagnosis as the reason (the inject layer hard-rejects it anyway; do not waste a nomination).

FORBIDDEN — do NOT attack on any of these (irrelevant by construction or already settled): margin of safety, valuation cheapness, quality/durability of the business, "would I own this for 5 years", balance-sheet quality as a thesis, or anything about whether the catalyst is real. A catalyst name is SUPPOSED to look bad on value/quality — "an expensive, mediocre business with a signed take-private at a 30% spread" is the sleeve's whole point.

Verdict per name: TRADE (clean on all four), TRADE_WITH_CONDITIONS (works only if conditions[] are met — list them concretely, e.g. "limit <= $X", "only if the Jul put OI > 500"), or NO_TRADE (edge gone / untradeable / window doesn't clear). ~3-6 live lookups/name; then emit ONE StructuredOutput {verdicts:[...]}, one object per symbol.

NAMES (${batch.length}): ${JSON.stringify(batch)}` }

function directorPrompt(survivors){ return `Today is __TODAY__. You are the CATALYST DIRECTOR for "Basket 13", a tracked PAPER basket (a calibration sleeve — NO live orders; expression + size are RECORDED, not executed). You receive the Catalyst-CRO survivors (TRADE / TRADE_WITH_CONDITIONS), each with its native board fields + the CRO's live checks. Build the basket under HARD rules — constraints, not preferences:
${HELD.n_seats ? `
LOCKED HELD BOOK (${HELD.n_seats} seats, ${HELD.invested_pct}% invested — these run to resolution; do NOT re-select them, and they CONSUME cap headroom): ${JSON.stringify(HELD.names)}. ALREADY USED toward the COMBINED caps: per-driver ${JSON.stringify(HELD.by_driver)} (cap 2 each, EXCEPT the FDA drivers FDA_clinical_readout / FDA_approval_decision / FDA_pathway_feedback which are UNCAPPED as of 2026-07-20), per-cluster weight-points ${JSON.stringify(HELD.by_cluster)} (cap 40 each), seats ${HELD.n_seats}/20. You are ADDING NEW seats from the survivors below into the REMAINING headroom ONLY. If nothing fits at acceptable edge, return picks:[] — NEVER force a seat or breach a combined cap.
` : ``}${WATCHLIST.n_on_deck ? `
PRIOR ON-DECK WATCHLIST (${WATCHLIST.n_on_deck} names you nominated in a previous run — CARRIED FORWARD by default and tracked to resolution): ${JSON.stringify(WATCHLIST.names)}. You are ACCOUNTABLE to these prior calls. A carried name leaves the on-deck book ONLY when its catalyst resolves or it graduates into the held book — you may NOT silently drop it. For each carried name you must do exactly ONE of: (a) RE-NOMINATE it in watchlist[] (keeps it active; if it was de_prioritized, set a stance_change_rationale explaining what changed); (b) DE-PRIORITIZE it — still list it in watchlist[] but with a stance_change_rationale stating why you cooled on it (it stays tracked, flagged); or (c) DEMOTE it on merit to passed[] with a concrete passed_because. If you championed a name last run and now want it gone, you owe a one-sentence reason — that asymmetry (added then dismissed) is exactly what the rationale captures.
` : ``}
SELECTION: free choice among survivors; when two names are comparable, PREFER DRIVER DIVERSITY over raw score. Honor each name's "weekly_diagnosis" where present: a fresh skeptic REFUTED / catalyst FIRED is a hard pass (the inject layer rejects it), and a fresh verdict-A/conviction-5 debate is a strong tailwind worth a seat if the CRO's trade surfaces clear.
CAPS (hard, COMBINED with the locked held book above — a basket that breaks one is rejected by the downstream validator):
  - <= 2 names per resolution_driver (held + new) — EXCEPT FDA_clinical_readout / FDA_approval_decision / FDA_pathway_feedback, which carry NO per-driver cap (2026-07-20: the bio gate is lifted; quality gates are the only bio filter). There is NO bio_convergence lane cap either.
  - <= 40 NAV weight-points per super_cluster (held + new; e.g. held 22 -> only 18 left).
  - 8-20 names total (held + new).
SIZING (Kelly-lite on the bounded floor; weight_pct are % of basket NAV, target sum ~100):
  - weight proportional to edge x independence (independence = resolves on its OWN driver, not the tape).
  - RISK-TO-FLOOR per ratio name <= 1.5% NAV: weight_pct * (live_price - downside_floor)/live_price <= 1.5. (A name with a 20% floor-distance caps near 7.5% weight.)
  - BINARIES (valuation_method=binary_prob): DEFINED-RISK only; premium-at-risk <= 2% NAV per name (weight_pct <= 2 for a debit structure); size off ev_pct, NOT the payoff.
EXPRESSION:
  - dated <= 6 months (days_to_milestone <= ~183) -> defined_risk_option clearing the milestone by +1 monthly expiry.
  - 6-12 months / structural / staging -> equity (or leaps if liquid).
  - binaries -> debit_spread (or defined_risk_option); never naked.
  - STAGING names (staging=true): equity ONLY, weight <= HALF a normal weight (~ (100/N)/2) — no options on an undated catalyst (theta with no timeline).
__PROMO__OUTPUT: picks[] {symbol, weight_pct, expression{type, expiry?, strikes?}, entry_rationale (<=2 sentences), resolution_driver, super_cluster, expected_rr OR expected_ev (binaries), invalidation (what kills the trade), review_trigger (the next dated milestone)}. Then classify EVERY non-selected CRO survivor into EXACTLY ONE of: watchlist[] {symbol, blocked_by (which COMBINED cap is full: a specific driver / a super-cluster / the 12-seat count), would_enter_if (what frees a seat, e.g. "an FDA_clinical_readout seat opens when CELC or AMLX resolves"), intended_weight_pct, note} — for names you WOULD seat now but CANNOT solely because a combined cap is full (on-deck; first to enter when a held seat resolves and frees its cap) — OR passed[] {symbol, passed_because} — for names you'd skip on merit regardless of headroom (weaker/compressed edge, untradeable, undated). A name is on the WATCHLIST only if headroom is the ONLY thing stopping it; cap FRESH watchlist nominations at the 10 strongest on-deck names AND at most 5 per resolution_driver — once a driver hits 5 on the watchlist, route its remaining names to passed[] and fill the freed watchlist slots with the best on-deck names from OTHER drivers, so one abundant driver (e.g. FDA_clinical_readout) cannot monopolize the queue. ACCOUNTABILITY: for ANY name whose stance CHANGES vs the PRIOR ON-DECK WATCHLIST above — newly added, de-prioritized, or re-championed after being de-prioritized — emit a one-sentence stance_change_rationale (unchanged names leave it null); to remove a carried name on merit, route it to passed[] with a passed_because (never just omit it — a resolved catalyst or graduation is the only silent exit). Then a short memo (cluster mix + why this shape). RE-CHECK every cap before emitting. Emit ONE StructuredOutput {picks, watchlist, passed, memo}.

SURVIVORS (${survivors.length}): ${JSON.stringify(survivors)}` }

phase('DeepDossier')
log(`Basket 13 — Deep-Dossier refresh: ${NAMES.length} candidates, one agent each (${MODEL})`)
const DCONC=5   // rate-limit discipline: burst -> batch (same cap as the CRO groups)
const dossiers=[]
for(let i=0;i<NAMES.length;i+=DCONC){
  const sub=NAMES.slice(i,i+DCONC)
  const r=await parallel(sub.map(n=>()=>agent(dossierPrompt(n),{label:`dossier:${n.symbol}`,phase:'DeepDossier',schema:DOSSIER_SCHEMA,model:MODEL})))
  r.filter(Boolean).forEach(d=>dossiers.push(d))
  log(`dossier group ${Math.floor(i/DCONC)+1} done; ${dossiers.length}/${NAMES.length} refreshed`)
}
const dosBySym=Object.fromEntries(dossiers.map(d=>[d.symbol,d]))
// Corrected load-bearing fields REPLACE the board's (originals kept under board_* for the audit
// trail); the full dossier rides along as fresh_dossier. _basket13_inject.py applies the same
// overrides from the returned dossiers[] so validation matches what the Director sized on.
const OVERRIDE_KEYS=['fair_value_target','downside_floor','dated_milestone','valuation_method','resolution_driver','staging','win_prob']
const REFRESHED=NAMES.map(n=>{
  const d=dosBySym[n.symbol]
  if(!d) return n
  const out={...n, fresh_dossier:d}
  for(const k of OVERRIDE_KEYS){
    if(k==='resolution_driver' && typeof d[k]==='string' && /\s/.test(d[k])) continue  // cap tag, never prose
    if(d[k]!==undefined && d[k]!==null && d[k]!==n[k]){ out['board_'+k]=n[k]; out[k]=d[k] }
  }
  return out
})
const dead=dossiers.filter(d=>!d.catalyst_live).map(d=>`${d.symbol}(${d.catalyst_status})`)
if(dead.length) log(`dossier kills (catalyst FIRED/BROKEN): ${dead.join(', ')}`)

const BATCH=5
const batches=[]; for(let i=0;i<REFRESHED.length;i+=BATCH) batches.push(REFRESHED.slice(i,i+BATCH))
phase('CatalystCRO')
log(`Basket 13 — Catalyst-CRO: ${REFRESHED.length} candidates in ${batches.length} batches of ${BATCH} (${MODEL})`)
const CONC=5
const cro=[]
for(let i=0;i<batches.length;i+=CONC){
  const sub=batches.slice(i,i+CONC)
  const r=await parallel(sub.map((b,bi)=>()=>agent(croPrompt(b),{label:`cro:b${i+bi}`,phase:'CatalystCRO',schema:CRO_SCHEMA,model:MODEL})))
  r.filter(Boolean).forEach(x=>{ if(x&&x.verdicts) cro.push(...x.verdicts) })
  log(`CRO group ${Math.floor(i/CONC)+1} done; ${cro.length} verdicts so far`)
}
const bySym=Object.fromEntries(REFRESHED.map(n=>[n.symbol,n]))
const survivors=cro
  .filter(v=>v && bySym[v.symbol] && (v.verdict==='TRADE'||v.verdict==='TRADE_WITH_CONDITIONS'))
  .map(v=>({...bySym[v.symbol], cro_verdict:v.verdict, live_edge_check:v.live_edge_check,
            conditions:v.conditions||[], window_note:v.window_note, tradeability_note:v.tradeability_note}))
log(`CRO survivors: ${survivors.length}/${NAMES.length} (TRADE / TRADE_WITH_CONDITIONS)`)
phase('Director')
let director=null
if(survivors.length){
  director=await agent(directorPrompt(survivors),{label:'director',phase:'Director',schema:DIRECTOR_SCHEMA,model:MODEL})
}else{
  log('No CRO survivors — Director skipped.')
}
return { generated_for: NAMES.length, dossiers, cro, survivors: survivors.map(s=>s.symbol), director }
'''

assert JS.count("__WATCHLIST__") == 1, "expected exactly one __WATCHLIST__ token in the template"
assert JS.count("__PROMO__") == 1, "expected exactly one __PROMO__ token in the template"
promo_note = ""
if PROMOTE:
    _iw = next((w.get("intended_weight_pct") for w in _trk_p.get("watchlist", [])
                if w.get("symbol") == PROMOTE), None)
    promo_note = (
        f"PROMOTION MODE (event-triggered, single seat): a held seat resolved and freed combined-cap "
        f"headroom; {PROMOTE} is the on-deck FIRST-IN-LINE (your own prior nomination"
        + (f", intended ~{_iw}%" if _iw else "") + "). Seat it ONLY if it still deserves the capital at "
        "TODAY's price and window (the dossier + CRO above just re-checked it live) and it fits every "
        "combined cap of the LOCKED HELD BOOK; otherwise keep it in watchlist[] with a "
        "stance_change_rationale, or demote it to passed[] with a passed_because. This run is a "
        "PROMOTION, not a full re-debate: re-nominate every OTHER carried name from the PRIOR ON-DECK "
        "WATCHLIST unchanged in watchlist[] (stance_change_rationale null) — you were given no fresh "
        "dossiers on them, so you have no basis to change their stances. ")
js = (JS.replace("__NAMES__", json.dumps(names, ensure_ascii=False))
        .replace("__HELD__", json.dumps(held_summary, ensure_ascii=False))
        .replace("__WATCHLIST__", json.dumps(watchlist_ctx, ensure_ascii=False))
        .replace("__PROMO__", promo_note)
        .replace("__MODEL__", MODEL)
        .replace("__TODAY__", datetime.date.today().isoformat()))
if PROMOTE:
    js = js.replace("name: 'basket13-catalyst-debate'", "name: 'basket13-promotion'")
    _ret_old = "return { generated_for: NAMES.length, dossiers, cro, survivors: survivors.map(s=>s.symbol), director }"
    assert _ret_old in js, "promotion return-marker patch failed — template drifted"
    js = js.replace(_ret_old, "return { promotion: true, generated_for: NAMES.length, dossiers, cro, "
                              "survivors: survivors.map(s=>s.symbol), director }")
if args.held_dossiers:
    # dossier phase ONLY: cut everything from the CRO batching onward, return the dossiers
    js = (js[:js.index("const BATCH=5")]
          + "return { generated_for: NAMES.length, dossiers }\n")
    js = js.replace(
        "phases: [ { title: 'DeepDossier', model: '__MODEL' }, { title: 'CatalystCRO', model: '__MODEL' }, { title: 'Director', model: '__MODEL' } ],".replace("__MODEL", MODEL),
        f"phases: [ {{ title: 'DeepDossier', model: '{MODEL}' }} ],")
    js = js.replace("name: 'basket13-catalyst-debate'", "name: 'basket13-held-dossier-refresh'")
# newline="\n": Windows text-mode would write CRLF, which the Workflow tool's permission
# layer rejects ("script contains control characters") — LF-only is mandatory.
open(OUT, "w", encoding="utf-8", newline="\n").write(js)
print(f"WROTE {OUT}  ({len(names)} candidates, {(len(names)+4)//5} CRO batches, model={MODEL}"
      + (f", {held_summary['n_seats']} held locked" if held_summary['n_seats'] else "") + ")"
      + (f" [filtered to {sorted(only)}]" if only else ""))
print(OUT)
