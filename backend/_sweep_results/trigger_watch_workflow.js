export const meta = {
  name: 'trigger-watch',
  description: 'Daily trigger-calendar micro-check: re-verify board names whose dated milestone is imminent or just past',
  phases: [{ title: 'Check' }],
}
const DUE = [
 {
  "symbol": "CAPR",
  "catalyst": "The FDA must act on Capricor's deramiocel BLA for Duchenne muscular dystrophy by 2026-11-22. The date was extended after a major amendment added 24-month HOPE-3 open-label extension data, and the 07-29 advisory panel voted 9-3 against efficacy.",
  "milestone": "PDUFA target action date 2026-11-22 (approval or CRL). After that, the securities class action covering the 12/17/2025-7/26/2026 class period moves to the lead-plaintiff stage, and the Q3 10-Q is due in mid-November.",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-11-22"
 },
 {
  "symbol": "CMPS",
  "catalyst": "COMP360 (psilocybin, TRD) rolling NDA is due to be fully filed in Q4-26 under an FDA Commissioner's National Priority Voucher, which targets a 1-2 month review. That points to an FDA decision around Q1/H1-27, followed by DEA rescheduling and launch.",
  "milestone": "2026-11-17 (slipped; was: Next date: the Q3-26 results and call on 2026-11-03, where NDA completion status should be updated. Then the rolling NDA should be complete in Q4-26, with a CNPV-speed FDA action likely in Q1/Q2-27 an)",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-11-17"
 },
 {
  "symbol": "INBX",
  "catalyst": "FDA action on the ozekibart (INBRX-109) BLA for unresectable/metastatic conventional chondrosarcoma, PDUFA goal date 2027-04-14. The BLA was accepted with no filing review issues. Updated PFS and subgroup data come first, at CTOS on 2026-11-20.",
  "milestone": "2026-11-20 CTOS oral presentation (updated PFS and subgroups, ChonDRAgon), then the PDUFA goal date of 2027-04-14. Also in between: Q3 10-Q (Nov 2026) for cash and Oxford covenant terms.",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-11-20"
 },
 {
  "symbol": "SVRA",
  "catalyst": "FDA action on the MOLBREEVI (molgramostim, inhaled GM-CSF) BLA for autoimmune PAP, with PDUFA goal date 2026-11-22 after the April 2026 major-amendment 3-month extension; FDA approval also unlocks up to $150M of non-dilutive capital.",
  "milestone": "2026-11-22 FDA PDUFA action date (a Sunday, so the decision may come on Fri 11-20 or earlier). Next: UK MHRA decision in Q4 2026, then EMA decision in Q1 2027.",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-11-22"
 },
 {
  "symbol": "BIP",
  "catalyst": "BIP and BIPC combine into one Canadian corporation, BIP Inc. BIP unitholders approved it on 2026-10-14. A BC Supreme Court final-order hearing is expected around 2026-11-03, with close targeted for Q4-2026. Brookfield's case rests on \"increased index demand\" and \"potential additional index inclusion",
  "milestone": "2026-11-19 (slipped; was: Next date: BC Supreme Court final-order hearing on or about 2026-11-03. Before that, the BIPC shareholder vote was on 2026-10-29 (adjourned from 10-14) and its result is unconfirmed. Close is targeted)",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-11-19"
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
  agent(`Today is 2026-11-19. TRIGGER CHECK (fast, <=3 lookups via WebSearch/WebFetch + FMP MCP via ToolSearch). Board name ${n.symbol} carries: catalyst "${n.catalyst}" / milestone "${n.milestone}" (score ${n.score}, tier ${n.tier}). The milestone date ${n.trigger} is imminent or just passed. Determine ONLY: did the event FIRE (and favorably or adversely), SLIP (new date?), or is it still FORWARD? Do not re-underwrite the thesis. OUTCOME RULES: FIRED_GOOD/FIRED_BAD are TERMINAL only (deal closed/broke, approval/CRL issued, verdict entered, tender settled); if the situation CONTINUES with a new date -- even after an adverse interim event (TRO granted, extension, second request) -- use SLIPPED with new_date and describe the tilt in the note. Deliverable = a SINGLE StructuredOutput call: {symbol, still_forward, fired, outcome (FORWARD/FIRED_GOOD/FIRED_BAD/SLIPPED/RESOLVED_OTHER/UNCLEAR), new_date (ISO or empty), note (1-2 sentences, cite source+date)}.`,
    { label: `trig:${n.symbol}`, phase: 'Check', schema: SCHEMA })
))).filter(Boolean)
return { checked: results.length, results }
