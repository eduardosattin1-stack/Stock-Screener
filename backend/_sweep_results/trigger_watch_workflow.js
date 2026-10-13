export const meta = {
  name: 'trigger-watch',
  description: 'Daily trigger-calendar micro-check: re-verify board names whose dated milestone is imminent or just past',
  phases: [{ title: 'Check' }],
}
const DUE = [
 {
  "symbol": "RCI",
  "catalyst": "Rogers now owns 100% of MLSE (closed 2026-10-01) and plans to sell a minority stake in its combined sports/media entity, which it values at more than C$25B, by H1 2027, using the cash to pay down debt. The sale would put a market price on the sports assets.",
  "milestone": "Kilmer 25% buyout CLOSED 2026-10-01 (announced 2026-07-06). Next: Q3 2026 results around late Oct 2026, for an update on the sale process; the minority-stake sale announcement is guided for H1 2027 (no buyer, terms or date yet).",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-10-01"
 },
 {
  "symbol": "MTN",
  "catalyst": "Oasis Management (about 6.5%, 13G switched to 13D) has nominated Chapek, Hudson, Roberts and Street for Vail's board at the 2026 annual meeting and argues the 42 resorts are undervalued against peers; the sale or strategic-review ask has no bid price attached, and Prince's standing offer for Park Ci",
  "milestone": "Done: 13D/notice 2026-09-10/16 and 13D/A 2026-09-29 (nominee agreements). Next: proxy filings by Vail and Oasis (not filed as of 2026-10-12), then the annual meeting, which is usually early December but has no announced date. Vail's own director search is set to finish in early 2027. Settlement risk",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-09-29"
 },
 {
  "symbol": "LNTH",
  "catalyst": "Curium US Holdings is buying Lantheus for $102.50/sh cash at close plus a non-transferable CVR worth up to $12/sh, tied to prostate, neurology and DEFINITY commercial milestones through 2030. Signed 2026-08-03, close guided to 1H27.",
  "milestone": "Special shareholder meeting on 2026-10-14 (majority of outstanding shares required). Next: FTC/HSR waiting period. The HSR notice was voluntarily pulled on 2026-09-17 and refiled to give the FTC more review time, refile date not confirmed. Close guided to 1H27.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-10-14"
 },
 {
  "symbol": "B",
  "catalyst": "Barrick plans a minority (about 10-15%) IPO of its North American gold business (NGM stake, Pueblo Viejo, Fourmile), targeted for year-end 2026, with Newmont's consent and settlement (a $1.95B payment to Barrick) already in hand and most net proceeds earmarked for shareholders.",
  "milestone": "Management repeated the year-end 2026 IPO target at Mining Forum Americas on 2026-09-29. Next dated checkpoint is the Q3 2026 results on 2026-11-09, which should bring an IPO timing update. The registration filing (F-1/S-1) is still unfiled as of 2026-10-12.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-09-29"
 }
]
const SCHEMA = { type:'object', properties:{ symbol:{type:'string'}, still_forward:{type:'boolean'}, fired:{type:'boolean'}, outcome:{type:'string', enum:['FORWARD','FIRED_GOOD','FIRED_BAD','SLIPPED','RESOLVED_OTHER','UNCLEAR']}, new_date:{type:'string'}, note:{type:'string'} }, required:['symbol','still_forward','fired','outcome','note'] }
phase('Check')
const results = (await parallel(DUE.map(n => () =>
  agent(`Today is 2026-10-13. TRIGGER CHECK (fast, <=3 lookups via WebSearch/WebFetch + FMP MCP via ToolSearch). Board name ${n.symbol} carries: catalyst "${n.catalyst}" / milestone "${n.milestone}" (score ${n.score}, tier ${n.tier}). The milestone date ${n.trigger} is imminent or just passed. Determine ONLY: did the event FIRE (and favorably or adversely), SLIP (new date?), or is it still FORWARD? Do not re-underwrite the thesis. OUTCOME RULES: FIRED_GOOD/FIRED_BAD are TERMINAL only (deal closed/broke, approval/CRL issued, verdict entered, tender settled); if the situation CONTINUES with a new date -- even after an adverse interim event (TRO granted, extension, second request) -- use SLIPPED with new_date and describe the tilt in the note. Deliverable = a SINGLE StructuredOutput call: {symbol, still_forward, fired, outcome (FORWARD/FIRED_GOOD/FIRED_BAD/SLIPPED/RESOLVED_OTHER/UNCLEAR), new_date (ISO or empty), note (1-2 sentences, cite source+date)}.`,
    { label: `trig:${n.symbol}`, phase: 'Check', schema: SCHEMA })
))).filter(Boolean)
return { checked: results.length, results }
