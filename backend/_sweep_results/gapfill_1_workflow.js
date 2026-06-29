export const meta = {
  name: 'catalyst-sweep-c1',
  description: 'Opus 3-tier catalyst sweep (chunk gapfill-1 (6 names)): scan -> deep -> skeptic',
  phases: [ { title:'Scan', model:'opus' }, { title:'Deep', model:'opus' }, { title:'Skeptic', model:'opus' } ],
}
const UNIVERSE = [{"symbol": "ASH", "company_name": "Ashland Inc."}, {"symbol": "ATAI", "company_name": "Atai Beckley N.V"}, {"symbol": "AVIR", "company_name": "Atea Pharmaceuticals, Inc."}, {"symbol": "AVTR", "company_name": "Avantor, Inc."}, {"symbol": "LQDA", "company_name": "Liquidia Corporation"}, {"symbol": "RPD", "company_name": "Rapid7, Inc."}]
const BATCH = 25
const DEEP_T = 5.0
const SCAN_SCHEMA = { type:'object', properties:{ names:{ type:'array', items:{ type:'object', properties:{ symbol:{type:'string'}, score:{type:'number'}, tier:{type:'string', enum:['ACTIVE','WATCH','NONE']}, lane:{type:'string'}, dated_catalyst:{type:'boolean'}, fired:{type:'boolean'}, one_line:{type:'string'} }, required:['symbol','score','tier','dated_catalyst','fired','one_line'] } } }, required:['names'] }
const DEEP_SCHEMA = { type:'object', properties:{ symbol:{type:'string'}, score:{type:'number'}, tier:{type:'string', enum:['ACTIVE','WATCH','NONE']}, lane:{type:'string'}, catalyst:{type:'string'}, dated_milestone:{type:'string'}, fired:{type:'boolean'}, instrument:{type:'string'}, bloom_gates:{type:'string'}, edge:{type:'string'}, analysis:{type:'string'}, primary_source:{type:'string'},
  // Phase-2 valuation (OPTIONAL on the fast sweep tier; the full SoP build is the dedicated valuation dossier).
  valuation_method:{type:'string', enum:['sop','spread','binary_prob','recovery','capital_return']}, fair_value_target:{type:'number'}, downside_floor:{type:'number'}, reference_price:{type:'number'}, reference_rr:{type:'number'}, valuation_basis:{type:'string'}, advocacy_target:{type:'number'} }, required:['symbol','score','tier','catalyst','fired','analysis'] }
const VERDICT_SCHEMA = { type:'object', properties:{ symbol:{type:'string'}, verdict:{type:'string', enum:['CONFIRMED','CONFIRMED_WITH_CORRECTIONS','REFUTED']}, final_score:{type:'number'}, kill_fact:{type:'string'}, confidence:{type:'string'} }, required:['symbol','verdict','final_score'] }
function scanPrompt(b){ return `Today is 2026-06-14. SCAN (triage) tier of a catalyst sweep for an event-driven / special-situations book. Verify live (WebSearch + FMP MCP via ToolSearch). For EACH name do a FAST triage (a couple of quick checks; do NOT deep-dive): does it have a REAL, DATED, FORWARD special-situation catalyst? Types: M&A / complicated merger-arb; spin-off; forced-seller OVERHANG clearing (own the suppressed underlying); distressed/restructuring/LME with a dated milestone; activist+structural (hardening trigger); capital-return (tender/special-div/dated deleveraging); supply-shortage+timing-moat; or a dated binary (PDUFA/ruling) WITH mispriced asymmetry.
GATE HARD: most names have NO near-term catalyst -> score 0-3, tier NONE. FORWARD-not-fired (already happened/re-rated => fired=true). NOT a macro bet. Rubric DEFAULT LOW: 0-2 none; 3-4 vague/priced/fired; 5-6 one real dated catalyst; 7-8 strong dated >=2 Bloom gates; 9-10 multiple imminent hard.
Return for EACH {symbol, score, tier, lane, dated_catalyst, fired, one_line}. Ruthless and fast; most should be NONE.
NAMES (${b.length}): ${JSON.stringify(b)}` }
function deepPrompt(n){ return `Today is 2026-06-14. DEEP tier. Verify ${n.symbol} (${n.company_name||''}). Triage flagged: "${n.one_line}" (tier ${n.tier}, score ${n.score}, lane ${n.lane||'?'}). Do FOCUSED verification — AT MOST ~6 lookups (WebSearch/WebFetch + FMP via ToolSearch), cite source+date. Gate STRICTLY: real+specific (Bloom G1 named counterparty / G2 concrete commitment / G3 specific currently-unpriced figure) + DATED + FORWARD (not fired/not re-rated) + NOT a macro bet.
CRITICAL: your ONLY deliverable is a SINGLE StructuredOutput call (no prose report). After ~6 lookups, STOP and call StructuredOutput; if not fully verifiable, still call it with your best assessment + note the gap in analysis. Fields {symbol, score (0-10), tier (ACTIVE/WATCH/NONE), lane, catalyst (1 sentence), dated_milestone (+next date), fired, instrument, bloom_gates (which of G1/G2/G3), edge (H/M/L+why), analysis (2-3 sentences), primary_source (+date)}. No real dated forward catalyst => tier NONE, score <=3.` }
function skepticPrompt(d){ return `Today is 2026-06-14. SKEPTIC tier. KILL this line; default REFUTED if you cannot independently confirm the load-bearing facts against a PRIMARY source. Verify live. Attack: (1) FIRED-not-forward; (2) date accuracy; (3) terms/magnitude truth; (4) thesis weakness (real edge vs priced/wrong/story); (5) tradeability + hidden disqualifier.
CRITICAL: your ONLY deliverable is a SINGLE StructuredOutput call (no prose). After ~6 lookups, call it.
LINE: ${d.symbol} — ${d.catalyst} | tier ${d.tier}, score ${d.score}, instrument: ${d.instrument||'?'} | ${d.analysis||''}
Fields {symbol, verdict (CONFIRMED/CONFIRMED_WITH_CORRECTIONS/REFUTED), final_score (0-10), kill_fact, confidence (H/M/L)}.` }
// retry transient errors (529 Overloaded / rate limits); only retries on THROW, passes nulls through, rethrows after n tries (parallel catches -> null, recoverable by resume)
async function aR(p,o,n){ n=n||6; let e; for(let t=0;t<n;t++){ try{ return await agent(p,o) }catch(err){ e=err } } throw e }
phase('Scan')
const batches=[]; for(let i=0;i<UNIVERSE.length;i+=BATCH) batches.push(UNIVERSE.slice(i,i+BATCH))
log(`Scanning ${UNIVERSE.length} names in ${batches.length} batches of ${BATCH} (Opus)`)
const scanned=(await parallel(batches.map((b,bi)=>()=>aR(scanPrompt(b),{label:`scan:b${bi}`,phase:'Scan',schema:SCAN_SCHEMA,model:'opus'})))).filter(Boolean).flatMap(r=>(r&&r.names)||[])
const survivors=scanned.filter(n=>n&&n.tier!=='NONE'&&n.score>=DEEP_T&&n.dated_catalyst&&!n.fired)
const dist={active:scanned.filter(n=>n.tier==='ACTIVE').length,watch:scanned.filter(n=>n.tier==='WATCH').length,none:scanned.filter(n=>n.tier==='NONE').length}
log(`Scan done: ${scanned.length} scored (A ${dist.active}/W ${dist.watch}/N ${dist.none}) -> ${survivors.length} survivors`)
phase('Deep')
const DEEP_CONC=4
const results=[]
for(let di=0;di<survivors.length;di+=DEEP_CONC){
  const sub=survivors.slice(di,di+DEEP_CONC)
  const subRes=await parallel(sub.map(s=>()=>aR(deepPrompt(s),{label:`deep:${s.symbol}`,phase:'Deep',schema:DEEP_SCHEMA,model:'opus'}).then(deep=>{ if(!deep) return null; if(deep.tier==='ACTIVE'&&!deep.fired){ return aR(skepticPrompt(deep),{label:`skeptic:${deep.symbol}`,phase:'Skeptic',schema:VERDICT_SCHEMA,model:'opus'}).then(v=>({...deep,verify:v,final_score:(v&&typeof v.final_score==='number')?v.final_score:deep.score})) } return {...deep,verify:null,final_score:deep.score} })))
  results.push(...subRes)
}
const verified=results.filter(Boolean)
const activeVerified=verified.filter(r=>r.tier==='ACTIVE'&&(!r.verify||r.verify.verdict!=='REFUTED'))
log(`Deep+Skeptic done: ${verified.length} dossiers; ${activeVerified.length} verified ACTIVE`)
return { chunk:'gapfill-1 (6 names)', scanned:scanned.length, scan_distribution:dist,
  survivors_flagged:survivors.map(s=>({symbol:s.symbol,score:s.score,tier:s.tier,lane:s.lane,one_line:s.one_line})),
  verified:verified.map(r=>({symbol:r.symbol,score:r.final_score,tier:r.tier,lane:r.lane,catalyst:r.catalyst,dated_milestone:r.dated_milestone,instrument:r.instrument,bloom_gates:r.bloom_gates,edge:r.edge,primary_source:r.primary_source,verdict:r.verify?r.verify.verdict:null,kill_fact:r.verify?r.verify.kill_fact:null,analysis:r.analysis})),
}