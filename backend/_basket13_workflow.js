export const meta = {
  name: 'basket13-catalyst-debate',
  description: 'Basket 13 catalyst sleeve — Catalyst-CRO trade attack (4 surfaces) then Director selection+sizing under hard caps',
  phases: [ { title: 'CatalystCRO', model: 'opus' }, { title: 'Director', model: 'opus' } ],
}
const NAMES = [{"symbol": "BBIO", "company_name": "BridgeBio Pharma, Inc.", "tier": "ACTIVE", "staging": false, "lane_canon": "bio_convergence", "resolution_driver": "FDA_approval_decision", "super_cluster": "FDA/biotech", "edge_grade": "H", "valuation_method": "binary_prob", "computed_rr": null, "ev_pct": 0.3602, "payoff": 2.35, "win_prob": 0.85, "fair_value_target": 105.0, "downside_floor": 58.0, "live_price": 72.01, "dated_milestone": "2026-11-27", "days_to_milestone": 150, "instrument": "equity (BBIO common); event-vol favors long-dated calls/call spreads around the Nov 27 PDUFA", "valuation_asof": "2026-06-08", "score": 7.5}, {"symbol": "EYPT", "company_name": "EyePoint Pharmaceuticals, Inc.", "tier": "ACTIVE", "staging": false, "lane_canon": "bio_convergence", "resolution_driver": "FDA_clinical_readout", "super_cluster": "FDA/biotech", "edge_grade": "H", "valuation_method": "binary_prob", "computed_rr": null, "ev_pct": 0.7505, "payoff": 2.72, "win_prob": 0.6, "fair_value_target": 37.5, "downside_floor": 5.5, "live_price": 14.11, "dated_milestone": "2026-07-31", "days_to_milestone": 31, "instrument": "EYPT equity (NASDAQ); long-dated calls / straddle viable given defined binary", "valuation_asof": "2026-06-08", "score": 7.5}, {"symbol": "AAUC", "company_name": "Allied Gold Corporation", "tier": "ACTIVE", "staging": false, "lane_canon": "merger_arb", "resolution_driver": "Foreign_regulator", "super_cluster": "Deal-completion", "edge_grade": "M", "valuation_method": "spread", "computed_rr": 20.35, "ev_pct": null, "payoff": null, "win_prob": null, "fair_value_target": 31.54, "downside_floor": 23.0, "live_price": 23.4, "dated_milestone": "2026-07-29", "days_to_milestone": 29, "instrument": "equity", "valuation_asof": "2026-06-08", "score": 7.0}, {"symbol": "ZYME", "company_name": "Zymeworks Inc.", "tier": "ACTIVE", "staging": false, "lane_canon": "bio_convergence", "resolution_driver": "FDA_approval_decision", "super_cluster": "FDA/biotech", "edge_grade": "M", "valuation_method": "binary_prob", "computed_rr": null, "ev_pct": 0.2266, "payoff": 1.35, "win_prob": 0.88, "fair_value_target": 31.0, "downside_floor": 19.0, "live_price": 24.1, "dated_milestone": "2026-08-25", "days_to_milestone": 56, "instrument": "equity (defined-risk event position; binary regulatory bet, size accordingly)", "valuation_asof": "2026-06-08", "score": 7.0}, {"symbol": "PRX.AS", "company_name": "Prosus N.V. (forced seller of Delivery Hero)", "tier": "WATCH", "staging": true, "lane_canon": "forced_seller", "resolution_driver": "Forced_divest_flow", "super_cluster": "Idiosyncratic", "edge_grade": "M", "valuation_method": "recovery", "computed_rr": 7.67, "ev_pct": null, "payoff": null, "win_prob": null, "fair_value_target": 46.21, "downside_floor": 37.365, "live_price": 38.385, "dated_milestone": null, "days_to_milestone": null, "instrument": "Weak — holdco-discount is perennial, not a catalyst; the re-rate is on the underlying (DHER), already fired", "valuation_asof": "2026-06-08", "score": 4.5}, {"symbol": "FUN", "company_name": "Six Flags Entertainment (Jana sale push)", "tier": "WATCH", "staging": true, "lane_canon": "activist", "resolution_driver": "Activist_process", "super_cluster": "Idiosyncratic", "edge_grade": "H", "valuation_method": "spread", "computed_rr": 2.57, "ev_pct": null, "payoff": null, "win_prob": null, "fair_value_target": 31.0, "downside_floor": 16.5, "live_price": 20.56, "dated_milestone": "2027-03-31", "days_to_milestone": 274, "instrument": "Equity (high leverage = torque)", "valuation_asof": "2026-06-08", "score": 5.0}, {"symbol": "IMCR", "company_name": "Immunocore Holdings plc", "tier": "WATCH", "staging": true, "lane_canon": "bio_convergence", "resolution_driver": "FDA_clinical_readout", "super_cluster": "FDA/biotech", "edge_grade": "H", "valuation_method": "binary_prob", "computed_rr": null, "ev_pct": 0.2097, "payoff": 3.03, "win_prob": 0.4, "fair_value_target": 62.0, "downside_floor": 20.0, "live_price": 30.42, "dated_milestone": null, "days_to_milestone": null, "instrument": "equity", "valuation_asof": "2026-06-08", "score": 6.0}, {"symbol": "LHX", "company_name": "L3Harris Technologies, Inc.", "tier": "WATCH", "staging": true, "lane_canon": "spinoff", "resolution_driver": "Spin_index_flow", "super_cluster": "Idiosyncratic", "edge_grade": "M", "valuation_method": null, "computed_rr": null, "ev_pct": null, "payoff": null, "win_prob": null, "fair_value_target": null, "downside_floor": null, "live_price": null, "dated_milestone": null, "days_to_milestone": null, "instrument": "equity", "valuation_asof": null, "score": 6.0}, {"symbol": "ADPT", "company_name": "Adaptive Biotechnologies Corporation", "tier": "WATCH", "staging": true, "lane_canon": "spinoff", "resolution_driver": "Spin_index_flow", "super_cluster": "Idiosyncratic", "edge_grade": "M", "valuation_method": null, "computed_rr": null, "ev_pct": null, "payoff": null, "win_prob": null, "fair_value_target": null, "downside_floor": null, "live_price": null, "dated_milestone": null, "days_to_milestone": null, "instrument": "equity (ADPT common)", "valuation_asof": null, "score": 5.0}, {"symbol": "DBVT", "company_name": "DBV Technologies S.A.", "tier": "WATCH", "staging": true, "lane_canon": "bio_convergence", "resolution_driver": "FDA_approval_decision", "super_cluster": "FDA/biotech", "edge_grade": "H", "valuation_method": "binary_prob", "computed_rr": null, "ev_pct": 0.4359, "payoff": 2.77, "win_prob": 0.55, "fair_value_target": 34.0, "downside_floor": 9.5, "live_price": 16.0, "dated_milestone": null, "days_to_milestone": null, "instrument": "equity", "valuation_asof": "2026-06-08", "score": 5.0}, {"symbol": "TLK", "company_name": "Perusahaan Perseroan (Persero) PT Telekomunikasi Indonesia Tbk", "tier": "WATCH", "staging": true, "lane_canon": "spinoff", "resolution_driver": "Spin_index_flow", "super_cluster": "Idiosyncratic", "edge_grade": "M", "valuation_method": null, "computed_rr": null, "ev_pct": null, "payoff": null, "win_prob": null, "fair_value_target": null, "downside_floor": null, "live_price": null, "dated_milestone": null, "days_to_milestone": null, "instrument": "equity (NYSE ADR TLK / IDX TLKM)", "valuation_asof": null, "score": 5.0}]
const MODEL = 'opus'
const HELD = {"names": [{"symbol": "GDOT", "weight_pct": 14, "driver": "Deal_close_generic", "super_cluster": "Deal-completion", "status": "OPEN"}, {"symbol": "UNF", "weight_pct": 8, "driver": "US_antitrust", "super_cluster": "Deal-completion", "status": "OPEN"}, {"symbol": "FIP", "weight_pct": 10, "driver": "Refi_restructuring", "super_cluster": "Idiosyncratic", "status": "OPEN"}, {"symbol": "FIG", "weight_pct": 5, "driver": "Forced_divest_flow", "super_cluster": "Idiosyncratic", "status": "OPEN"}, {"symbol": "BLCO", "weight_pct": 5, "driver": "Forced_divest_flow", "super_cluster": "Idiosyncratic", "status": "OPEN"}, {"symbol": "CELC", "weight_pct": 1.5, "driver": "FDA_clinical_readout", "super_cluster": "FDA/biotech", "status": "OPEN"}, {"symbol": "VRDN", "weight_pct": 2, "driver": "FDA_approval_decision", "super_cluster": "FDA/biotech", "status": "OPEN"}, {"symbol": "AQST", "weight_pct": 4.5, "driver": "FDA_approval_decision", "super_cluster": "FDA/biotech", "status": "OPEN"}, {"symbol": "WVE", "weight_pct": 3.5, "driver": "FDA_pathway_feedback", "super_cluster": "FDA/biotech", "status": "OPEN"}, {"symbol": "AMLX", "weight_pct": 2, "driver": "FDA_clinical_readout", "super_cluster": "FDA/biotech", "status": "OPEN"}], "n_seats": 10, "by_driver": {"Deal_close_generic": 1, "US_antitrust": 1, "Refi_restructuring": 1, "Forced_divest_flow": 2, "FDA_clinical_readout": 2, "FDA_approval_decision": 2, "FDA_pathway_feedback": 1}, "by_cluster": {"Deal-completion": 22.0, "Idiosyncratic": 20.0, "FDA/biotech": 13.5}, "invested_pct": 55.5}

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

function croPrompt(batch){ return `Today is 2026-06-30. You are the CATALYST-CRO for "Basket 13", an event-driven special-situations sleeve. The catalyst's REALITY is ALREADY SETTLED upstream — a 3-tier scan->deep->skeptic pipeline already verified each event is real, dated, forward and idiosyncratic (it kills 40-50% of flags). DO NOT re-litigate whether the event is real. You adjudicate exactly ONE question: IS THE TRADE GOOD? — on these FOUR surfaces and NOTHING else:

1) EDGE AT ENTRY (perishable). Re-verify the spread / R:R against the LIVE price NOW (fetch the current quote via FMP/ToolSearch). The dossier built its edge at "valuation_asof"; a spread that was 8% last week can be 1% today. State the recomputed number + source in live_edge_check, AND emit the verified live underlying price as the NUMBER field live_price — the tracker stamps entries at YOUR verified price, so it must be exact. If the edge has compressed below ~half the dossier R:R, that alone is NO_TRADE or TRADE_WITH_CONDITIONS.
2) TRADEABILITY. Does the expression exist at acceptable cost? Options: quoted bid/ask spread, open interest, strikes near the thesis levels (fair_value_target / downside_floor) — read-only via IBKR/FMP/ToolSearch. Equity: ADV vs a realistic position; borrow if any short leg. A correct thesis in an instrument with a 15%-wide spread or no OI is NOT a trade — say so in tradeability_note.
3) WINDOW <-> EXPRESSION. Does a tradeable expiry clear the catalyst date ("dated_milestone", ~"days_to_milestone" days away) with margin — at least +1 monthly expiry PAST the milestone? Has this catalyst's date slipped before? A real catalyst too slow for its option is a loss with a correct thesis. Put the read in window_note. (Staging names are undated/soft -> equity; note that.)
4) DRIVER TAG. Confirm or correct "resolution_driver" in driver_confirmed; if a SECOND name in this batch resolves on the SAME driver, flag it (the Director enforces the cap; you just flag).

FORBIDDEN — do NOT attack on any of these (irrelevant by construction or already settled): margin of safety, valuation cheapness, quality/durability of the business, "would I own this for 5 years", balance-sheet quality as a thesis, or anything about whether the catalyst is real. A catalyst name is SUPPOSED to look bad on value/quality — "an expensive, mediocre business with a signed take-private at a 30% spread" is the sleeve's whole point.

Verdict per name: TRADE (clean on all four), TRADE_WITH_CONDITIONS (works only if conditions[] are met — list them concretely, e.g. "limit <= $X", "only if the Jul put OI > 500"), or NO_TRADE (edge gone / untradeable / window doesn't clear). ~3-6 live lookups/name; then emit ONE StructuredOutput {verdicts:[...]}, one object per symbol.

NAMES (${batch.length}): ${JSON.stringify(batch)}` }

function directorPrompt(survivors){ return `Today is 2026-06-30. You are the CATALYST DIRECTOR for "Basket 13", a tracked PAPER basket (a calibration sleeve — NO live orders; expression + size are RECORDED, not executed). You receive the Catalyst-CRO survivors (TRADE / TRADE_WITH_CONDITIONS), each with its native board fields + the CRO's live checks. Build the basket under HARD rules — constraints, not preferences:
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
OUTPUT: picks[] {symbol, weight_pct, expression{type, expiry?, strikes?}, entry_rationale (<=2 sentences), resolution_driver, super_cluster, expected_rr OR expected_ev (binaries), invalidation (what kills the trade), review_trigger (the next dated milestone)}. Then classify EVERY non-selected CRO survivor into EXACTLY ONE of: watchlist[] {symbol, blocked_by (which COMBINED cap is full: a specific driver / a super-cluster / the 12-seat count), would_enter_if (what frees a seat, e.g. "an FDA_clinical_readout seat opens when CELC or AMLX resolves"), intended_weight_pct, note} — for names you WOULD seat now but CANNOT solely because a combined cap is full (on-deck; first to enter when a held seat resolves and frees its cap) — OR passed[] {symbol, passed_because} — for names you'd skip on merit regardless of headroom (weaker/compressed edge, untradeable, undated). A name is on the WATCHLIST only if headroom is the ONLY thing stopping it; cap the watchlist at the 10 strongest on-deck names AND at most 5 per resolution_driver — once a driver hits 5 on the watchlist, route its remaining names to passed[] and fill the freed watchlist slots with the best on-deck names from OTHER drivers, so one abundant driver (e.g. FDA_clinical_readout) cannot monopolize the queue. Then a short memo (cluster mix + why this shape). RE-CHECK every cap before emitting. Emit ONE StructuredOutput {picks, watchlist, passed, memo}.

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
