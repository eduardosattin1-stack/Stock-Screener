export const meta = {
  name: 'basket13-promotion',
  description: 'Basket 13 catalyst sleeve - Catalyst-CRO trade attack (4 surfaces) then Director selection+sizing under hard caps',
  phases: [ { title: 'DeepDossier', model: 'opus' }, { title: 'CatalystCRO', model: 'opus' }, { title: 'Director', model: 'opus' } ],
}
const NAMES = [{"symbol": "PVLA", "company_name": null, "tier": "on_deck_promotion", "staging": false, "lane_canon": null, "resolution_driver": null, "super_cluster": null, "edge_grade": null, "valuation_method": null, "computed_rr": null, "ev_pct": null, "payoff": null, "win_prob": null, "fair_value_target": null, "downside_floor": null, "live_price": 118.84, "dated_milestone": null, "days_to_milestone": null, "instrument": "equity", "valuation_asof": "2026-06-23", "score": null}]
const MODEL = 'opus'
const HELD = {"names": [{"symbol": "FIG", "weight_pct": 5.0, "driver": "Forced_divest_flow", "super_cluster": "Idiosyncratic", "status": "OPEN"}, {"symbol": "AQST", "weight_pct": 5.0, "driver": "FDA_approval_decision", "super_cluster": "FDA/biotech", "status": "OPEN"}, {"symbol": "WVE", "weight_pct": 5.0, "driver": "FDA_pathway_feedback", "super_cluster": "FDA/biotech", "status": "OPEN"}, {"symbol": "ZYME", "weight_pct": 5.0, "driver": "FDA_approval_decision", "super_cluster": "FDA/biotech", "status": "OPEN"}, {"symbol": "VIR", "weight_pct": 5.0, "driver": "FDA_clinical_readout", "super_cluster": "FDA/biotech", "status": "OPEN"}, {"symbol": "OLMA", "weight_pct": 5.0, "driver": "FDA_clinical_readout", "super_cluster": "FDA/biotech", "status": "OPEN"}, {"symbol": "AVIR", "weight_pct": 5.0, "driver": "FDA_clinical_readout", "super_cluster": "FDA/biotech", "status": "OPEN"}, {"symbol": "AGIO", "weight_pct": 5.0, "driver": "FDA_approval_decision", "super_cluster": "FDA/biotech", "status": "OPEN"}], "n_seats": 8, "by_driver": {"Forced_divest_flow": 1, "FDA_approval_decision": 3, "FDA_pathway_feedback": 1, "FDA_clinical_readout": 3}, "by_cluster": {"Idiosyncratic": 5.0, "FDA/biotech": 35.0}, "invested_pct": 40.0}
const WATCHLIST = {"n_on_deck": 7, "names": [{"symbol": "EYPT", "de_prioritized": false, "entry_date": "2026-06-13", "expected_pct": 89.6, "prior_blocked_by": "No combined cap blocks it. FDA_clinical_readout and FDA/biotech are both uncapped, there is no seat cap, and Idiosyncratic/Deal-completion sit at 5.0 of 40 weight points each. What holds it is that it produced no fresh CRO survivor dossier or live-price check this run, so there is no current underwrite to seat."}, {"symbol": "PVLA", "de_prioritized": false, "entry_date": "2026-06-23", "expected_pct": 59.1, "prior_blocked_by": "No combined cap blocks it. The 12-seat count that was cited against it in the prior run was abolished on 2026-07-28 (no head-count cap), and its cluster is uncapped. It is held only by the absence of a fresh CRO survivor dossier this run."}, {"symbol": "BBIO", "de_prioritized": false, "entry_date": "2026-06-13", "expected_pct": 46.6, "prior_blocked_by": "No combined cap blocks it. Its stated blocker - the 12-seat count - no longer exists; the head-count cap was removed on 2026-07-28 and dilution replaced it as the only cost. It now waits on a fresh CRO dossier, not on headroom."}, {"symbol": "DBVT", "de_prioritized": false, "entry_date": "2026-06-23", "expected_pct": 43.6, "prior_blocked_by": "No combined cap blocks it. Same as BBIO - the 12-seat count that de-prioritized it was removed on 2026-07-28, and FDA_clinical_readout / FDA-biotech carry no cap. It waits on a fresh CRO dossier."}, {"symbol": "GERN", "de_prioritized": false, "entry_date": "2026-07-02", "expected_pct": 45.7, "prior_blocked_by": "No combined cap blocks it. The 12-seat count cited against it was abolished on 2026-07-28; its driver and cluster are uncapped. It waits on a fresh CRO dossier."}, {"symbol": "CLVT", "de_prioritized": true, "entry_date": "2026-06-13", "expected_pct": null, "prior_blocked_by": "Forced_divest_flow driver (2/2 with FIG held)"}, {"symbol": "MGNI", "de_prioritized": true, "entry_date": "2026-06-23", "expected_pct": 8.0, "prior_blocked_by": "No fresh CRO survivor trade this run; the prior Forced_divest_flow cap (2/2) is now RELIEVED - FIG is the sole held Forced_divest_flow name (1/2) after CLVT's demotion."}]}

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

function dossierPrompt(n){ return `Today is 2026-08-04. You are the DEEP-DOSSIER agent for "Basket 13", an event-driven special-situations sleeve. You handle ONE candidate. The board dossier below came from an older single-pass backend scan and may be stale or wrong; downstream, a CRO adjudicates the trade and a Director sizes seats ON YOUR NUMBERS - your corrected fields REPLACE the board's. Re-underwrite the load-bearing facts from LIVE sources (5-10 lookups via ToolSearch: FMP quote/news/press-releases/SEC filings/earnings calendar; WebSearch to confirm anything the feeds don't settle):

1) CATALYST REALITY & STATUS. Confirm the resolving event is real, forward-dated, UNFIRED, and idiosyncratic (resolves on its own facts, not the tape). Emit catalyst_status: PENDING_HARD (dated + binding), PENDING_SOFT (real but undated/soft), SLIPPED (timeline pushed - name from->to in dossier_note), FIRED (already resolved - edge spent), BROKEN (deal dead / thesis invalidated). catalyst_live=false for FIRED/BROKEN.
2) MILESTONE. Verify dated_milestone against the latest company/regulator communication; correct it if it slipped or firmed; null if genuinely undated (then staging=true).
3) VALUATION AXES. Re-derive fair_value_target and downside_floor under the dossier's valuation_method - spread: live deal terms incl. FX; sop/recovery: name the components; binary_prob: win/lose prices and win_prob. If you cannot reproduce a board number from the live record, CORRECT it and show the arithmetic in dossier_note. Only emit numbers you can defend. DECK-MARK GATE (commodity-linked SoP/NAV names): if the target rests on a feasibility-study or broker price deck, check the deck against the LIVE commodity tape; if spot is materially below deck, compute a SPOT-MARKED target variant (prefer the issuer's own published NPV sensitivity over margin-scaling - NPV compresses faster than margin) and state BOTH numbers plus the spot-deck R:R in dossier_note; the deck-price target is a conditional cap, not fair value. TAKEOUT LENS (bio/pharma names only, added 2026-07-21): the 2026 biotech M&A regime is running at a record pace for LATE-STAGE, commercially-ready assets (37 biotechs taken out >=$1B YTD, $216B total). If this name has pivotal data in hand or is near approval, assess strategic scarcity, name 1-2 plausible acquirers, and check RECENT COMPARABLE takeout values; this may LIFT the win-leg fair_value_target ONLY with comp provenance (named deal, date, value) shown in dossier_note. NEVER create, extend, or substitute a milestone from takeout speculation - takeout is undated optionality on top of the dated event, not an event. The regime cuts both ways: XBI at a 5-year high also means market-implied win probabilities are richer and old max-fear floor prints may be stale-low - say so where it applies.
4) DRIVER + STAGING. Confirm or correct resolution_driver and staging (dated hard event -> staging=false; soft/undated -> true). resolution_driver is a CANONICAL TAG consumed by a deterministic <=2-per-driver cap - keep the board's tag or correct it to ANOTHER canonical snake_case tag (e.g. FDA_clinical_readout, FDA_approval_decision, US_antitrust, Deal_close_generic, Refi_restructuring, Forced_divest_flow, Spin_index_flow, Activist_process, Supply_timing, Foreign_regulator); NEVER free prose - nuance goes in dossier_note.
5) SKEPTIC PASS on yourself. Take the single most load-bearing claim in your thesis_summary - try to refute it from the live record; put the honest residual risk in kill_risk (null only if nothing credible).

DO NOT: value/quality/moat opinions, trade verdicts, position sizing, or option-chain work - the CRO owns tradeability/window and the Director owns sizing. You own FACTS and VALUATION AXES only.
List every field you changed in discrepancies[] as "field: board X -> live Y - why". Then emit ONE StructuredOutput per the schema.

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

function croPrompt(batch){ return `Today is 2026-08-04. You are the CATALYST-CRO for "Basket 13", an event-driven special-situations sleeve. The catalyst's REALITY is ALREADY SETTLED upstream - each name below was re-underwritten TODAY by a deep-dossier agent (see its fresh_dossier field: live-verified catalyst status, milestone, valuation axes; corrected values already REPLACE the stale board numbers, originals under board_*). DO NOT re-litigate whether the event is real - but a fresh_dossier.catalyst_status of FIRED or BROKEN means the edge is GONE: verdict NO_TRADE citing the dossier, no further work on that name. You adjudicate exactly ONE question: IS THE TRADE GOOD? - on these FOUR surfaces and NOTHING else:

1) EDGE AT ENTRY (perishable). Re-verify the spread / R:R against the LIVE price NOW (fetch the current quote via FMP/ToolSearch). The dossier built its edge at "valuation_asof"; a spread that was 8% last week can be 1% today. State the recomputed number + source in live_edge_check, AND emit the verified live underlying price as the NUMBER field live_price - the tracker stamps entries at YOUR verified price, so it must be exact. If the edge has compressed below ~half the dossier R:R, that alone is NO_TRADE or TRADE_WITH_CONDITIONS. DUAL-DECK KILL-LINE: if fresh_dossier carries a spot-marked target variant (commodity-deck SoP names), run the R:R test on BOTH the build-deck and spot-marked targets - passing deck-only while failing at spot is at best TRADE_WITH_CONDITIONS with an explicit deck condition (e.g. "valid only if <commodity> recovers toward the FS deck"), never a clean TRADE.
2) TRADEABILITY. Does the expression exist at acceptable cost? Options: quoted bid/ask spread, open interest, strikes near the thesis levels (fair_value_target / downside_floor) - read-only via IBKR/FMP/ToolSearch. Equity: ADV vs a realistic position; borrow if any short leg. A correct thesis in an instrument with a 15%-wide spread or no OI is NOT a trade - say so in tradeability_note.
3) WINDOW <-> EXPRESSION. Does a tradeable expiry clear the catalyst date ("dated_milestone", ~"days_to_milestone" days away) with margin - at least +1 monthly expiry PAST the milestone? Has this catalyst's date slipped before? A real catalyst too slow for its option is a loss with a correct thesis. Put the read in window_note. (Staging names are undated/soft -> equity; note that.)
4) DRIVER TAG. Confirm or correct "resolution_driver" in driver_confirmed; if a SECOND name in this batch resolves on the SAME driver, flag it (the Director enforces the cap; you just flag).
WEEKLY DIAGNOSIS OVERRIDE (the one exception to "reality is settled upstream"): where a name carries "weekly_diagnosis" (the weekly full-stack catalyst debate + adversarial skeptic over this very book), treat it as CURRENT catalyst intelligence - a FRESH skeptic verdict of REFUTED, or catalyst_status FIRED/ARB (trading through terms), means the event edge is GONE: verdict NO_TRADE with the diagnosis as the reason (the inject layer hard-rejects it anyway; do not waste a nomination).

FORBIDDEN - do NOT attack on any of these (irrelevant by construction or already settled): margin of safety, valuation cheapness, quality/durability of the business, "would I own this for 5 years", balance-sheet quality as a thesis, or anything about whether the catalyst is real. A catalyst name is SUPPOSED to look bad on value/quality - "an expensive, mediocre business with a signed take-private at a 30% spread" is the sleeve's whole point.

TAKEOUT OPTIONALITY (2026-07-21): where the fresh_dossier carries a comp-backed takeout-lifted win leg, treat it as FREE UPSIDE on a trade that already clears all four surfaces - it may sweeten a TRADE, but it must NEVER rescue a failing edge, window, or tradeability test (an undated maybe-acquisition is not a spread).
Verdict per name: TRADE (clean on all four), TRADE_WITH_CONDITIONS (works only if conditions[] are met - list them concretely, e.g. "limit <= $X", "only if the Jul put OI > 500"), or NO_TRADE (edge gone / untradeable / window doesn't clear). ~3-6 live lookups/name; then emit ONE StructuredOutput {verdicts:[...]}, one object per symbol.

NAMES (${batch.length}): ${JSON.stringify(batch)}` }

function directorPrompt(survivors){ return `Today is 2026-08-04. You are the CATALYST DIRECTOR for "Basket 13", a tracked PAPER basket (a calibration sleeve - NO live orders; expression + size are RECORDED, not executed). You receive the Catalyst-CRO survivors (TRADE / TRADE_WITH_CONDITIONS), each with its native board fields + the CRO's live checks. Build the basket under HARD rules - constraints, not preferences:
${HELD.n_seats ? `
LOCKED HELD BOOK (${HELD.n_seats} seats, ${HELD.invested_pct}% invested - these run to resolution; do NOT re-select them, and they CONSUME cap headroom): ${JSON.stringify(HELD.names)}. ALREADY USED toward the COMBINED caps: per-driver ${JSON.stringify(HELD.by_driver)} (cap 2 each, EXCEPT the FDA drivers FDA_clinical_readout / FDA_approval_decision / FDA_pathway_feedback which are UNCAPPED as of 2026-07-20), per-cluster weight-points ${JSON.stringify(HELD.by_cluster)} (cap 40 each, EXCEPT FDA/biotech which is uncapped), ${HELD.n_seats} seats held (NO seat cap). You are ADDING NEW seats from the survivors below. There is no headroom to run out of - the constraint is dilution: with ${HELD.n_seats} held, each new seat takes every seat to 50.0/(${HELD.n_seats}+k). If nothing clears the median seat you already hold, return picks:[] - NEVER force a seat or breach a combined cap.
` : ``}${WATCHLIST.n_on_deck ? `
PRIOR ON-DECK WATCHLIST (${WATCHLIST.n_on_deck} names you nominated in a previous run - CARRIED FORWARD by default and tracked to resolution): ${JSON.stringify(WATCHLIST.names)}. You are ACCOUNTABLE to these prior calls. A carried name leaves the on-deck book ONLY when its catalyst resolves or it graduates into the held book - you may NOT silently drop it. For each carried name you must do exactly ONE of: (a) RE-NOMINATE it in watchlist[] (keeps it active; if it was de_prioritized, set a stance_change_rationale explaining what changed); (b) DE-PRIORITIZE it - still list it in watchlist[] but with a stance_change_rationale stating why you cooled on it (it stays tracked, flagged); or (c) DEMOTE it on merit to passed[] with a concrete passed_because. If you championed a name last run and now want it gone, you owe a one-sentence reason - that asymmetry (added then dismissed) is exactly what the rationale captures.
` : ``}
REGIME CONTEXT (as of 2026-07; STALE after ~2026-10 - if today is materially past that, IGNORE this block and note it in the memo): biotech M&A is at a record pace (37 takeouts >=$1B YTD 2026, $216B total deal value; acquirers paying up for late-stage, commercially-ready assets - Nuvalent $10.6B pre-approval, Apogee $10.9B in Phase 3; patent-cliff-driven, FTC light-touch). Two-sided implication: comp-backed takeout optionality legitimately fattens the WIN leg of late-stage bio seats that clear the gates on their own - but the same hot tape (XBI at a 5-year high) means entry edges are more compressed and market-implied win probs richer than in a cold tape; do not loosen entry discipline because the regime is warm.
SELECTION: free choice among survivors; when two names are comparable, PREFER DRIVER DIVERSITY over raw score. FAST-RETURN HORIZON (2026-07-20): this sleeve prioritizes resolution WITHIN 2026 -- a name whose milestone or realistic resolution path lands in 2027+ is a PASS on merit (the validator hard-rejects dated milestones beyond 2026), and an undated staging name needs a plausible resolution path within ~2 quarters to deserve a seat. Honor each name's "weekly_diagnosis" where present: a fresh skeptic REFUTED / catalyst FIRED is a hard pass (the inject layer rejects it), and a fresh verdict-A/conviction-5 debate is a strong tailwind worth a seat if the CRO's trade surfaces clear.
DEBT-CYCLE PHASE (2026-07-28 - ADVISORY ONLY, read this carefully): the macro layer says we are in DISCIPLINE (4w in phase, confidence high; real 30y 2.98% (rising) x 30y-3m +144bp x auction demand score 0.22 x interest/receipts score 1.00). This is DIRECTION, NOT A GATE. It must NOT make any name eligible or ineligible, must NOT change conviction, and cannot change size (sizing is mechanical). Use it for exactly one thing: JUDGEMENT about which catalyst families actually get PAID in this phase, stated in your memo.
  - EXPANSION - cheap money; refinancing/levered-recap and growth-story catalysts complete easily; deal financing is available.
  - DISCIPLINE - the cost of waiting is punished. Catalysts that pay CASH SOON (approvals with launch revenue, closing deals, forced sellers, capital returns) are favoured; catalysts that only re-rate a distant terminal value are fighting the discount rate, however good the science. Deal financing is tighter, so financing-contingent milestones carry more slip risk.
  - FORCING - policy/regulator intervention dominates; forced-seller and mandated-divestiture drivers get more numerous and more reliable.
  - MONETIZATION - long-duration and story assets get paid again as the discount rate falls; distant terminal-value catalysts stop fighting the tape.
A phase citation is NEVER a reason to seat or skip a name on its own - the dated evidence is. If the phase argues against a name you still believe in, seat it and say so in the memo.
CAPS (hard, COMBINED with the locked held book above - a basket that breaks one is rejected by the downstream validator):
  - <= 2 names per resolution_driver (held + new) - EXCEPT FDA_clinical_readout / FDA_approval_decision / FDA_pathway_feedback, which carry NO per-driver cap (2026-07-20: the bio gate is lifted; quality gates are the only bio filter). There is NO bio_convergence lane cap either.
  - <= 40 NAV weight-points per super_cluster (held + new) - EXCEPT FDA/biotech, which is UNCAPPED as of 2026-07-28 (the last binding limit on biotech head-count, now removed).
  - NO head-count cap. Book size is your free choice; dilution is the only cost (see SIZING).
SIZING - NOT YOURS ANY MORE (2026-07-28, Bruno). The book is EQUAL WEIGHT: every unresolved seat carries 50.0/n of NAV, computed by the stamping layer, with the remainder held in cash. Do NOT size, do NOT rank by size, do NOT propose a weight you care about (emit weight_pct:0 and it will be overwritten). This mirrors the apex book, where conviction-proportional sizing was retired for carrying no predictive signal. Two consequences you MUST reason with:
  - DILUTION IS THE DISCIPLINE. There is no head-count cap any more. But every seat you add shrinks EVERY other seat, including your best one. So the only question per candidate is binary: does this name deserve to make the whole book smaller? If it is not at least as good as the median seat you already hold, it is a pass - that is now the entire cost model.
  - EXPRESSION IS YOUR ONLY RISK LEVER. Because you cannot size a name down, the way you control what a bad outcome costs is the STRUCTURE you choose. A defined-risk option caps the loss at the premium; equity does not. Use it deliberately, especially on binaries.
EXPRESSION (your lever - choose per name and say why in entry_rationale):
  - dated <= 6 months (days_to_milestone <= ~183) -> defined_risk_option clearing the milestone by +1 monthly expiry.
  - 6-12 months / structural / staging -> equity (or leaps if liquid).
  - BINARIES (valuation_method=binary_prob): DEFINED-RISK ONLY - debit_spread or defined_risk_option, never naked, never plain equity. This is a HARD validator gate, and it is the reason equal weight is survivable on a book this binary-heavy: the structure, not the size, is what bounds the loss.
  - STAGING names (staging=true): equity ONLY - no options on an undated catalyst (theta with no timeline).
PROMOTION MODE (event-triggered, single seat): a held seat resolved and freed combined-cap headroom; PVLA is the on-deck FIRST-IN-LINE (your own prior nomination). Seat it ONLY if it still deserves the capital at TODAY's price and window (the dossier + CRO above just re-checked it live) and it fits every combined cap of the LOCKED HELD BOOK; otherwise keep it in watchlist[] with a stance_change_rationale, or demote it to passed[] with a passed_because. This run is a PROMOTION, not a full re-debate: re-nominate every OTHER carried name from the PRIOR ON-DECK WATCHLIST unchanged in watchlist[] (stance_change_rationale null) - you were given no fresh dossiers on them, so you have no basis to change their stances. OUTPUT: picks[] {symbol, weight_pct, expression{type, expiry?, strikes?}, entry_rationale (<=2 sentences), resolution_driver, super_cluster, expected_rr OR expected_ev (binaries), invalidation (what kills the trade), review_trigger (the next dated milestone)}. Then classify EVERY non-selected CRO survivor into EXACTLY ONE of: watchlist[] {symbol, blocked_by (which COMBINED cap is full: a specific driver or a super-cluster - NOT a seat count, there is none), would_enter_if (what frees it, e.g. "a Deal-completion seat opens when DDL resolves"), intended_weight_pct, note} - for names you WOULD seat now but CANNOT solely because a combined cap is full (on-deck; first to enter when a held seat resolves and frees its cap) - OR passed[] {symbol, passed_because} - for names you'd skip on merit regardless of headroom (weaker/compressed edge, untradeable, undated). A name is on the WATCHLIST only if headroom is the ONLY thing stopping it; cap FRESH watchlist nominations at the 10 strongest on-deck names AND at most 5 per resolution_driver - once a driver hits 5 on the watchlist, route its remaining names to passed[] and fill the freed watchlist slots with the best on-deck names from OTHER drivers, so one abundant driver (e.g. FDA_clinical_readout) cannot monopolize the queue. ACCOUNTABILITY: for ANY name whose stance CHANGES vs the PRIOR ON-DECK WATCHLIST above - newly added, de-prioritized, or re-championed after being de-prioritized - emit a one-sentence stance_change_rationale (unchanged names leave it null); to remove a carried name on merit, route it to passed[] with a passed_because (never just omit it - a resolved catalyst or graduation is the only silent exit). Then a short memo (cluster mix + why this shape). RE-CHECK every cap before emitting. Emit ONE StructuredOutput {picks, watchlist, passed, memo}.

SURVIVORS (${survivors.length}): ${JSON.stringify(survivors)}` }

phase('DeepDossier')
log(`Basket 13 - Deep-Dossier refresh: ${NAMES.length} candidates, one agent each (${MODEL})`)
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
log(`Basket 13 - Catalyst-CRO: ${REFRESHED.length} candidates in ${batches.length} batches of ${BATCH} (${MODEL})`)
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
  log('No CRO survivors - Director skipped.')
}
return { promotion: true, generated_for: NAMES.length, dossiers, cro, survivors: survivors.map(s=>s.symbol), director }
