export const meta = {
  name: 'trigger-watch',
  description: 'Daily trigger-calendar micro-check: re-verify board names whose dated milestone is imminent or just past',
  phases: [{ title: 'Check' }],
}
const DUE = [
 {
  "symbol": "WFRD",
  "catalyst": "Weatherford moves its legal home from Ireland to Delaware on 2026-11-13 (Irish High Court approved 2026-10-27). That makes it eligible for the S&P Composite 1500, but S&P has not announced an add and no date is set.",
  "milestone": "Redomicile closes 2026-11-13 (company guidance, subject to customary conditions). The next scheduled S&P quarterly rebalance is effective around 2026-12-21, with the announcement around 2026-12-04. That date is my inference from S&P's usual calendar and is not confirmed for WFRD. S&P can also add it",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-11-13"
 },
 {
  "symbol": "MFIC",
  "catalyst": "Ares Capital (ARCC) signed a definitive agreement on 2026-10-27 to acquire MFIC for about $10.88/sh ($1.21 cash plus about $9.67 in ARCC stock, roughly $2.6B enterprise value); it closes after both shareholder votes.",
  "milestone": "Signed 2026-10-27. Next steps: S-4/joint proxy filing, then the MFIC and ARCC shareholder votes (dates not yet set; a 1H-2027 close is likely, typical for BDC-to-BDC mergers). The Q3 earnings call set for 2026-11-05 was cancelled.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-11-05"
 }
]
const SCHEMA = { type:'object', properties:{ symbol:{type:'string'}, still_forward:{type:'boolean'}, fired:{type:'boolean'}, outcome:{type:'string', enum:['FORWARD','FIRED_GOOD','FIRED_BAD','SLIPPED','RESOLVED_OTHER','UNCLEAR']}, new_date:{type:'string'}, note:{type:'string'} }, required:['symbol','still_forward','fired','outcome','note'] }
phase('Check')
const results = (await parallel(DUE.map(n => () =>
  agent(`Today is 2026-11-11. TRIGGER CHECK (fast, <=3 lookups via WebSearch/WebFetch + FMP MCP via ToolSearch). Board name ${n.symbol} carries: catalyst "${n.catalyst}" / milestone "${n.milestone}" (score ${n.score}, tier ${n.tier}). The milestone date ${n.trigger} is imminent or just passed. Determine ONLY: did the event FIRE (and favorably or adversely), SLIP (new date?), or is it still FORWARD? Do not re-underwrite the thesis. OUTCOME RULES: FIRED_GOOD/FIRED_BAD are TERMINAL only (deal closed/broke, approval/CRL issued, verdict entered, tender settled); if the situation CONTINUES with a new date -- even after an adverse interim event (TRO granted, extension, second request) -- use SLIPPED with new_date and describe the tilt in the note. Deliverable = a SINGLE StructuredOutput call: {symbol, still_forward, fired, outcome (FORWARD/FIRED_GOOD/FIRED_BAD/SLIPPED/RESOLVED_OTHER/UNCLEAR), new_date (ISO or empty), note (1-2 sentences, cite source+date)}.`,
    { label: `trig:${n.symbol}`, phase: 'Check', schema: SCHEMA })
))).filter(Boolean)
return { checked: results.length, results }
