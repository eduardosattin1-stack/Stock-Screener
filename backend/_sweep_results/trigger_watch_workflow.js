export const meta = {
  name: 'trigger-watch',
  description: 'Daily trigger-calendar micro-check: re-verify board names whose dated milestone is imminent or just past',
  phases: [{ title: 'Check' }],
}
const DUE = [
 {
  "symbol": "AVEX",
  "catalyst": "Madison Dearborn's 180-day IPO lockup on AEVEX Corp expires 2026-10-13, freeing ~33.3M shares (144% of the 23.1M public float) from a sponsor that already demonstrated willingness to sell early via the June 1 waiver secondary \u2014 a supply event, not an upside event.",
  "milestone": "2026-10-13 lockup expiry (180 days from the 2026-04-16 prospectus). Adjacent dated prints: BlackSea Technologies acquisition close guided September 2026; class-action lead-plaintiff deadline 2026-10-20; Q3 print ~mid-November 2026. The real WATCH trigger is the first post-expiry marketed secondary (",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-10-13"
 },
 {
  "symbol": "KDP",
  "catalyst": "Board-approved tax-free separation of Keurig Dr Pepper into Beverage Co and Global Coffee Co following the Apr-1-2026 JDE Peet's close, with operational readiness targeted year-end 2026 and the split early 2027.",
  "milestone": "Chobani transactions ($800M stake repurchase + $125M Allentown PA facility) close in Q3-2026 (by 2026-09-30); Q3-26 earnings late Oct 2026; operational readiness target year-end 2026; Form 10 / separation early 2027.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-09-30"
 },
 {
  "symbol": "TMC",
  "catalyst": "NOAA has TMC USA's consolidated DSHMRA exploration-license + commercial-recovery-permit application in full compliance and published in the Federal Register, with a virtual public hearing 13-Oct-2026, comment close 19-Oct-2026, and a first-ever US commercial seabed-mining permit decision targeted by",
  "milestone": "2026-10-13 NOAA virtual public hearing (3-5pm ET); next hard dates 2026-10-19 comment close, then permit decision targeted before end-Q1-2027",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-10-13"
 }
]
const SCHEMA = { type:'object', properties:{ symbol:{type:'string'}, still_forward:{type:'boolean'}, fired:{type:'boolean'}, outcome:{type:'string', enum:['FORWARD','FIRED_GOOD','FIRED_BAD','SLIPPED','RESOLVED_OTHER','UNCLEAR']}, new_date:{type:'string'}, note:{type:'string'} }, required:['symbol','still_forward','fired','outcome','note'] }
phase('Check')
const results = (await parallel(DUE.map(n => () =>
  agent(`Today is 2026-10-12. TRIGGER CHECK (fast, <=3 lookups via WebSearch/WebFetch + FMP MCP via ToolSearch). Board name ${n.symbol} carries: catalyst "${n.catalyst}" / milestone "${n.milestone}" (score ${n.score}, tier ${n.tier}). The milestone date ${n.trigger} is imminent or just passed. Determine ONLY: did the event FIRE (and favorably or adversely), SLIP (new date?), or is it still FORWARD? Do not re-underwrite the thesis. OUTCOME RULES: FIRED_GOOD/FIRED_BAD are TERMINAL only (deal closed/broke, approval/CRL issued, verdict entered, tender settled); if the situation CONTINUES with a new date -- even after an adverse interim event (TRO granted, extension, second request) -- use SLIPPED with new_date and describe the tilt in the note. Deliverable = a SINGLE StructuredOutput call: {symbol, still_forward, fired, outcome (FORWARD/FIRED_GOOD/FIRED_BAD/SLIPPED/RESOLVED_OTHER/UNCLEAR), new_date (ISO or empty), note (1-2 sentences, cite source+date)}.`,
    { label: `trig:${n.symbol}`, phase: 'Check', schema: SCHEMA })
))).filter(Boolean)
return { checked: results.length, results }
