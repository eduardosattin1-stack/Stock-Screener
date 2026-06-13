#!/usr/bin/env python3
"""Basket 13 — Catalyst sleeve: the two-phase catalyst-native debate generator.

Writes _basket13_workflow.js (run it with the Workflow tool). Patterned on _valuation_gen.py.

  Phase 1 — Catalyst-CRO (one agent per candidate, batched ~5): attacks the TRADE on exactly
            FOUR surfaces — edge-at-entry, tradeability, window<->expression, driver-tag.
            It NEVER re-litigates whether the event is real (the catalyst scan->deep->skeptic
            tier already settled that, killing 40-50% of flags) and NEVER attacks value/quality
            axes (a catalyst name is supposed to look bad on MoS/quality by construction).
  Phase 2 — Catalyst Director: selects + sizes from the CRO survivors under HARD caps.

Both phases run on Fable 5 (model:'fable') — this greenfield leg is the first step of the
staged Fable-5 migration; the v6 value debate stays on Opus 4.8 untouched. If the runner
rejects the 'fable' alias, set MODEL='opus' below and note it in the run log.

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
ap.add_argument("--model", default="fable",
                help="agent model alias for both phases; 'opus' is the documented fallback if 'fable' is unavailable")
args = ap.parse_args()
MODEL = args.model   # • both phases; default fable (the Fable-5 migration leg), opus fallback

only = {s.strip().upper() for s in args.only.split(",") if s.strip()}
cands = json.load(open(CAND, encoding="utf-8"))["candidates"]
if only:
    cands = [c for c in cands if c["symbol"].upper() in only]

# compact field set the agents read
FIELDS = ["symbol", "company_name", "tier", "staging", "lane_canon", "resolution_driver",
          "super_cluster", "edge_grade", "valuation_method", "computed_rr", "ev_pct", "payoff",
          "win_prob", "fair_value_target", "downside_floor", "live_price", "dated_milestone",
          "days_to_milestone", "instrument", "valuation_asof", "score"]
names = [{k: c.get(k) for k in FIELDS} for c in cands]

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

JS = r'''export const meta = {
  name: 'basket13-catalyst-debate',
  description: 'Basket 13 catalyst sleeve — Catalyst-CRO trade attack (4 surfaces) then Director selection+sizing under hard caps',
  phases: [ { title: 'CatalystCRO', model: '__MODEL__' }, { title: 'Director', model: '__MODEL__' } ],
}
const NAMES = __NAMES__
const MODEL = '__MODEL__'
const HELD = __HELD__

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
    review_trigger:{type:'string'}
  }, required:['symbol','weight_pct','expression','resolution_driver'] } },
  passed:{ type:'array', items:{ type:'object', properties:{ symbol:{type:'string'}, passed_because:{type:'string'} }, required:['symbol','passed_because'] } },
  watchlist:{ type:'array', items:{ type:'object', properties:{ symbol:{type:'string'}, blocked_by:{type:'string'}, would_enter_if:{type:'string'}, intended_weight_pct:{type:['number','null']}, note:{type:'string'} }, required:['symbol','blocked_by'] } },
  memo:{type:'string'}
}, required:['picks','passed'] }

function croPrompt(batch){ return `Today is __TODAY__. You are the CATALYST-CRO for "Basket 13", an event-driven special-situations sleeve. The catalyst's REALITY is ALREADY SETTLED upstream — a 3-tier scan->deep->skeptic pipeline already verified each event is real, dated, forward and idiosyncratic (it kills 40-50% of flags). DO NOT re-litigate whether the event is real. You adjudicate exactly ONE question: IS THE TRADE GOOD? — on these FOUR surfaces and NOTHING else:

1) EDGE AT ENTRY (perishable). Re-verify the spread / R:R against the LIVE price NOW (fetch the current quote via FMP/ToolSearch). The dossier built its edge at "valuation_asof"; a spread that was 8% last week can be 1% today. State the recomputed number + source in live_edge_check, AND emit the verified live underlying price as the NUMBER field live_price — the tracker stamps entries at YOUR verified price, so it must be exact. If the edge has compressed below ~half the dossier R:R, that alone is NO_TRADE or TRADE_WITH_CONDITIONS.
2) TRADEABILITY. Does the expression exist at acceptable cost? Options: quoted bid/ask spread, open interest, strikes near the thesis levels (fair_value_target / downside_floor) — read-only via IBKR/FMP/ToolSearch. Equity: ADV vs a realistic position; borrow if any short leg. A correct thesis in an instrument with a 15%-wide spread or no OI is NOT a trade — say so in tradeability_note.
3) WINDOW <-> EXPRESSION. Does a tradeable expiry clear the catalyst date ("dated_milestone", ~"days_to_milestone" days away) with margin — at least +1 monthly expiry PAST the milestone? Has this catalyst's date slipped before? A real catalyst too slow for its option is a loss with a correct thesis. Put the read in window_note. (Staging names are undated/soft -> equity; note that.)
4) DRIVER TAG. Confirm or correct "resolution_driver" in driver_confirmed; if a SECOND name in this batch resolves on the SAME driver, flag it (the Director enforces the cap; you just flag).

FORBIDDEN — do NOT attack on any of these (irrelevant by construction or already settled): margin of safety, valuation cheapness, quality/durability of the business, "would I own this for 5 years", balance-sheet quality as a thesis, or anything about whether the catalyst is real. A catalyst name is SUPPOSED to look bad on value/quality — "an expensive, mediocre business with a signed take-private at a 30% spread" is the sleeve's whole point.

Verdict per name: TRADE (clean on all four), TRADE_WITH_CONDITIONS (works only if conditions[] are met — list them concretely, e.g. "limit <= $X", "only if the Jul put OI > 500"), or NO_TRADE (edge gone / untradeable / window doesn't clear). ~3-6 live lookups/name; then emit ONE StructuredOutput {verdicts:[...]}, one object per symbol.

NAMES (${batch.length}): ${JSON.stringify(batch)}` }

function directorPrompt(survivors){ return `Today is __TODAY__. You are the CATALYST DIRECTOR for "Basket 13", a tracked PAPER basket (a calibration sleeve — NO live orders; expression + size are RECORDED, not executed). You receive the Catalyst-CRO survivors (TRADE / TRADE_WITH_CONDITIONS), each with its native board fields + the CRO's live checks. Build the basket under HARD rules — constraints, not preferences:
${HELD.n_seats ? `
LOCKED HELD BOOK (${HELD.n_seats} seats, ${HELD.invested_pct}% invested — these run to resolution; do NOT re-select them, and they CONSUME cap headroom): ${JSON.stringify(HELD.names)}. ALREADY USED toward the COMBINED caps: per-driver ${JSON.stringify(HELD.by_driver)} (cap 2 each), per-cluster weight-points ${JSON.stringify(HELD.by_cluster)} (cap 40 each), bio_convergence lane (cap 5 names), seats ${HELD.n_seats}/20. You are ADDING NEW seats from the survivors below into the REMAINING headroom ONLY. If nothing fits at acceptable edge, return picks:[] — NEVER force a seat or breach a combined cap.
` : ``}
SELECTION: free choice among survivors; when two names are comparable, PREFER DRIVER DIVERSITY over raw score.
CAPS (hard, COMBINED with the locked held book above — a basket that breaks one is rejected by the downstream validator):
  - <= 2 names per resolution_driver (held + new).
  - <= 5 names in the bio_convergence lane (held + new) — bio binaries are abundant; cap the lane.
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
OUTPUT: picks[] {symbol, weight_pct, expression{type, expiry?, strikes?}, entry_rationale (<=2 sentences), resolution_driver, super_cluster, expected_rr OR expected_ev (binaries), invalidation (what kills the trade), review_trigger (the next dated milestone)}. Then classify EVERY non-selected CRO survivor into EXACTLY ONE of: watchlist[] {symbol, blocked_by (which COMBINED cap is full: a specific driver / a super-cluster / the 12-seat count), would_enter_if (what frees a seat, e.g. "an FDA_clinical_readout seat opens when CELC or AMLX resolves"), intended_weight_pct, note} — for names you WOULD seat now but CANNOT solely because a combined cap is full (on-deck; first to enter when a held seat resolves and frees its cap) — OR passed[] {symbol, passed_because} — for names you'd skip on merit regardless of headroom (weaker/compressed edge, untradeable, undated). A name is on the WATCHLIST only if headroom is the ONLY thing stopping it; cap the watchlist at the 10 strongest on-deck names. Then a short memo (cluster mix + why this shape). RE-CHECK every cap before emitting. Emit ONE StructuredOutput {picks, watchlist, passed, memo}.

SURVIVORS (${survivors.length}): ${JSON.stringify(survivors)}` }

const BATCH=5
const batches=[]; for(let i=0;i<NAMES.length;i+=BATCH) batches.push(NAMES.slice(i,i+BATCH))
phase('CatalystCRO')
log(`Basket 13 — Catalyst-CRO: ${NAMES.length} candidates in ${batches.length} batches of ${BATCH} (${MODEL})`)
const CONC=5
const cro=[]
for(let i=0;i<batches.length;i+=CONC){
  const sub=batches.slice(i,i+CONC)
  const r=await parallel(sub.map((b,bi)=>()=>agent(croPrompt(b),{label:`cro:b${i+bi}`,phase:'CatalystCRO',schema:CRO_SCHEMA,model:MODEL})))
  r.filter(Boolean).forEach(x=>{ if(x&&x.verdicts) cro.push(...x.verdicts) })
  log(`CRO group ${Math.floor(i/CONC)+1} done; ${cro.length} verdicts so far`)
}
const bySym=Object.fromEntries(NAMES.map(n=>[n.symbol,n]))
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
return { generated_for: NAMES.length, cro, survivors: survivors.map(s=>s.symbol), director }
'''

js = (JS.replace("__NAMES__", json.dumps(names, ensure_ascii=False))
        .replace("__HELD__", json.dumps(held_summary, ensure_ascii=False))
        .replace("__MODEL__", MODEL)
        .replace("__TODAY__", datetime.date.today().isoformat()))
open(OUT, "w", encoding="utf-8").write(js)
print(f"WROTE {OUT}  ({len(names)} candidates, {(len(names)+4)//5} CRO batches, model={MODEL}"
      + (f", {held_summary['n_seats']} held locked" if held_summary['n_seats'] else "") + ")"
      + (f" [filtered to {sorted(only)}]" if only else ""))
print(OUT)
