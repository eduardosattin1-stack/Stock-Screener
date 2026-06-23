#!/usr/bin/env python3
"""Generate a Workflow JS that fans out subagents to pull LIVE IBKR options
analytics (read-only) for every symbol on the sweep board. Output -> _opt_fetch_workflow.js.
Run: python _options_fetch_gen.py   then launch the JS via the Workflow tool."""
import json, os
BASE = os.path.dirname(os.path.abspath(__file__))
BOARD_F = os.path.join(BASE, "_sweep_board.json")
OUT = os.path.join(BASE, "_opt_fetch_workflow.js")

board = json.load(open(BOARD_F, encoding="utf-8"))
names = [{"symbol": b["symbol"], "company_name": b.get("company_name", b["symbol"])} for b in board]

JS = r'''export const meta = {
  name: 'ibkr-options-fetch',
  description: 'Fetch LIVE IBKR options analytics (read-only) for sweep board names',
  phases: [ { title: 'Fetch' } ],
}
const NAMES = __NAMES__
const OPT_SCHEMA = { type:'object', properties:{ results:{ type:'array', items:{ type:'object', properties:{
  symbol:{type:'string'}, ok:{type:'boolean'}, last:{type:'number'}, annual_iv:{type:'number'},
  iv_pctile_52w:{type:'number'}, hist_vol_annual:{type:'number'},
  today_call_vol:{type:'number'}, today_put_vol:{type:'number'}, avg_call_vol:{type:'number'}, avg_put_vol:{type:'number'}
}, required:['symbol','ok'] } } }, required:['results'] }
function fetchPrompt(batch){ return `Today is 2026-06-08. You pull LIVE options analytics from an IBKR brokerage MCP. READ-ONLY: never call any create/modify/delete order tool.
STEP 1 load tools: ToolSearch query EXACTLY: select:mcp__f1d0e029-9094-4cea-8baa-3bf15c3864ea__search_contracts,mcp__f1d0e029-9094-4cea-8baa-3bf15c3864ea__get_price_snapshot
For EACH name:
 a. search_contracts(query=symbol, security_type="STK"). Pick the PRIMARY US listing: country_code "US" on a US equity exchange (NASDAQ/NYSE/ARCA/AMEX/BATS), the real operating company. IGNORE foreign listings, ".TEN"/tender entries, bonds, warrants. Take its underlying_contract_id. If no US listing -> record {symbol, ok:false} and move on.
 b. get_price_snapshot(contract_id=<id>, exchange="SMART", market_data_names=["last","implied-vol-underlying","implied-volatility-percentile","historical-vol","underlying-today-option-volume","underlying-avg-option-volume"]).
 c. Record numbers: last=last.price; annual_iv=implied-vol-underlying.annual_iv; iv_pctile_52w=implied-volatility-percentile.high_52w; hist_vol_annual=historical-vol.annual_pct; today_call_vol=underlying-today-option-volume.callVolume; today_put_vol=underlying-today-option-volume.putVolume; avg_call_vol=underlying-avg-option-volume.avgCallVolume; avg_put_vol=underlying-avg-option-volume.avgPutVolume. ok=true if annual_iv is present (name has listed options), else ok=false. OMIT any field that is unavailable (do not invent).
Your ONLY deliverable is ONE StructuredOutput call {results:[...]} with EXACTLY one object per symbol in this batch (include ok:false ones). ~2 MCP calls/name; do not over-explore.
NAMES (${batch.length}): ${JSON.stringify(batch)}` }
const BATCH=13
const batches=[]; for(let i=0;i<NAMES.length;i+=BATCH) batches.push(NAMES.slice(i,i+BATCH))
phase('Fetch')
log(`IBKR options fetch: ${NAMES.length} names in ${batches.length} batches of ${BATCH}`)
const CONC=6
const all=[]
for(let i=0;i<batches.length;i+=CONC){
  const sub=batches.slice(i,i+CONC)
  const r=await parallel(sub.map((b,bi)=>()=>agent(fetchPrompt(b),{label:`opt:b${i+bi}`,phase:'Fetch',schema:OPT_SCHEMA,model:'sonnet'})))
  r.filter(Boolean).forEach(x=>{ if(x&&x.results) all.push(...x.results) })
  log(`batch group ${Math.floor(i/CONC)+1} done; ${all.length} names fetched so far`)
}
const ok=all.filter(x=>x&&x.ok&&x.annual_iv!=null).length
return { fetched: all.length, with_iv: ok, results: all }
'''

js = JS.replace("__NAMES__", json.dumps(names, ensure_ascii=False))
open(OUT, "w", encoding="utf-8").write(js)
print(f"WROTE {OUT} ({len(names)} names, {(len(names)+12)//13} batches)")
print(OUT)
