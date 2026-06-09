#!/usr/bin/env python3
"""Generate a Workflow JS: Opus-4.8 deep-dossier VALUATION pass over the board.
Each agent reads filings and BUILDS the lane-appropriate fair-value model (SoP / spread /
binary / recovery / capital_return), emits the structured schema (target, floor, prob, the
SoP build, reference_price + reference_rr). Output sidecar -> _valuation_results.json, which
_valuation_inject.py folds into _valuation.json for _enrich_board/_post_board.

Usage:
  python _valuation_gen.py                 # all board (non-NONE) names
  python _valuation_gen.py --only MBGL,NSC,VERA
"""
import json, os, argparse
BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
OUT = os.path.join(BASE, "_valuation_workflow.js")

ap = argparse.ArgumentParser()
ap.add_argument("--only", default="")
args = ap.parse_args()

board = json.load(open(os.path.join(ROOT, "catalyst_candidates_231.json"), encoding="utf-8"))["candidates"]
names = []
only = {s.strip().upper() for s in args.only.split(",") if s.strip()}
for r in board:
    if r.get("tier") == "NONE":
        continue
    if only and r["symbol"].upper() not in only:
        continue
    names.append({"symbol": r["symbol"], "company_name": r.get("company_name", ""),
                  "lane": r.get("lane_canon") or "", "context": (r.get("analysis_summary") or "")[:260]})

JS = r'''export const meta = {
  name: 'catalyst-valuation',
  description: 'Opus-4.8 deep-dossier valuation pass (SoP / spread / binary / recovery / capital_return)',
  phases: [ { title: 'Value', model: 'opus' } ],
}
const NAMES = __NAMES__
const VAL_SCHEMA = { type:'object', properties:{ results:{ type:'array', items:{ type:'object', properties:{
  symbol:{type:'string'},
  valuation_method:{type:'string', enum:['sop','spread','binary_prob','recovery','capital_return']},
  units:{ type:'object', properties:{ money:{type:'string'}, per_share:{type:'string'}, shares:{type:'string'} } },
  fair_value_target:{type:'number'}, downside_floor:{type:'number'},
  valuation_basis:{type:'string'}, valuation_asof:{type:'string'},
  reference_price:{type:'number'}, reference_rr:{type:'number'},
  sop_components:{ type:'array', items:{ type:'object', properties:{ segment:{type:'string'}, driver_metric:{type:'string'}, metric_value:{type:'number'}, multiple:{type:'number'}, ownership:{type:'number'}, ev_contribution:{type:'number'}, basis:{type:'string'} }, required:['segment','ev_contribution'] } },
  net_debt:{type:'number'}, adjustments:{type:'number'}, shares_out:{type:'number'}, advocacy_target:{type:'number'},
  deal_price:{type:'number'}, undisturbed_price:{type:'number'}, expected_close_date:{type:'string'}, break_prob:{type:'number'},
  win_prob:{type:'number'}, target_on_win:{type:'number'}, downside_on_loss:{type:'number'}, prob_basis:{type:'string'},
  recovery_value:{type:'number'}, instrument_ref:{type:'string'},
  announced_return_per_share:{type:'number'}, residual_value:{type:'number'}
}, required:['symbol','valuation_method'] } } }, required:['results'] }

function valPrompt(batch){ return `Today is 2026-06-08. You are an event-driven VALUATION dossier agent for a special-situations book. For EACH name compute a POST-CATALYST fair value + a downside floor, then your own R:R. Read filings/news (WebSearch/WebFetch + FMP via ToolSearch); cite source+date in the basis.

METHOD BY LANE (the suggested method is in each name's "lane"; override only if the catalyst is clearly a different type):
- forced_seller / spinoff / activist -> "sop": build a SUM-OF-PARTS once-separated. Emit sop_components [{segment, driver_metric (EBITDA|sales|stake_mv), metric_value, multiple, ev_contribution, basis(cite the comp)}], net_debt, adjustments (pension/minority/holdco-discount/leakage, SIGNED), shares_out. fair_value_target = (sum ev_contribution - net_debt - adjustments)/shares_out and MUST equal that build within 5% (any premium = an explicit extra sop_components line or adjustment, NEVER asserted on top). If an activist has a public price target, put it in advocacy_target (a labeled CEILING, displayed only — NEVER your fair_value_target, NEVER in the R:R). downside_floor = the DE-RATED no-deal standalone (strip the deal/activist premium OUT of the price) — for an out-of-favor name this is often BELOW the 52-week low; do NOT pin it to the 52-wk chart low (it embeds the same hope).
- merger_arb -> "spread": deal_price (per-share consideration; for stock/mixed deals use the current acquirer price), undisturbed_price (pre-bid), expected_close_date, break_prob. fair_value_target=deal_price; downside_floor=undisturbed_price.
- bio_convergence -> "binary_prob": win_prob (CALIBRATED 0-1, cite prob_basis), target_on_win ($/sh post-approval), downside_on_loss ($/sh on failure ~ cash). This is a BARBELL not a ratio. (still set fair_value_target=target_on_win, downside_floor=downside_on_loss for storage.)
- distressed -> "recovery": recovery_value ($/sh post-emergence equity/recovery), instrument_ref. fair_value_target=recovery_value; downside_floor=current claim/equity level.
- capital_return -> "capital_return": announced_return_per_share, residual_value. fair_value_target=announced_return_per_share+residual_value; downside_floor=ex-return level.

GUARDRAILS (do not break): (1) fair_value_target is the POST-CATALYST value — what it re-rates to WHEN the event fires — NOT a generic standalone DCF. (2) SHOW THE WORK: sop_components with the multiple+basis per segment, the net-debt bridge, shares; for non-sop methods a one-line valuation_basis with the figures. (3) CITE THE COMP for every multiple; if no clean comp, say so and WIDEN the floor. (4) Emit reference_price = the live price you used, and reference_rr = your own (target-ref)/(ref-floor) at that price (for binary use EV%). valuation_asof = 2026-06-08. (5) TARGET != ADVOCACY: an activist's number is a book-talking ceiling, not your fair value — your fair_value_target is your OWN computed SoP/take-out; the activist figure goes in advocacy_target only. (6) The build MUST RECONCILE: fair_value_target == (sum ev_contribution - net_debt - adjustments)/shares_out within 5% — a deterministic guard OVERRIDES your R:R with the build if it doesn't. (7) FLOOR = de-rated no-deal standalone, NOT the chart low (for an out-of-favor name often 15-30% BELOW current). (8) UNITS — emit units={money:"usd_millions", per_share:"usd", shares:"millions"} and OBEY it: EV/net_debt/adjustments/metric_value in USD MILLIONS, fair_value_target/downside_floor/deal_price/per-share figures in USD, shares_out in MILLIONS. A mixed/undeclared-units build is REJECTED (quarantined, no number shown). (9) PER-ROW ARITHMETIC — each ev_contribution MUST equal metric_value x multiple (EBITDA/sales) OR metric_value x ownership (stake_mv, ownership 0-1). (10) MULTIPLES in band (EBITDA 4-25x, sales 0.5-12x) or cite a specific named comp. (11) NO PLACEHOLDERS — if the catalyst has played out and the stock sits at/above fair value, emit the HONEST fair_value_target and let it read NO_UPSIDE; NEVER set target=live.

Your ONLY deliverable is ONE StructuredOutput call {results:[...]}, one object per symbol. ~4-6 lookups/name; build the model, then STOP and emit.
NAMES (${batch.length}): ${JSON.stringify(batch)}` }

const BATCH=5
const batches=[]; for(let i=0;i<NAMES.length;i+=BATCH) batches.push(NAMES.slice(i,i+BATCH))
phase('Value')
log(`Valuation dossier: ${NAMES.length} names in ${batches.length} batches of ${BATCH} (Opus)`)
const CONC=6
const all=[]
for(let i=0;i<batches.length;i+=CONC){
  const sub=batches.slice(i,i+CONC)
  const r=await parallel(sub.map((b,bi)=>()=>agent(valPrompt(b),{label:`val:b${i+bi}`,phase:'Value',schema:VAL_SCHEMA,model:'opus'})))
  r.filter(Boolean).forEach(x=>{ if(x&&x.results) all.push(...x.results) })
  log(`group ${Math.floor(i/CONC)+1} done; ${all.length} valued so far`)
}
return { valued: all.length, results: all }
'''

js = JS.replace("__NAMES__", json.dumps(names, ensure_ascii=False))
open(OUT, "w", encoding="utf-8").write(js)
print(f"WROTE {OUT} ({len(names)} names, {(len(names)+4)//5} batches)" + (f" [filtered to {sorted(only)}]" if only else ""))
print(OUT)
