export const meta = {
  name: 'trigger-watch',
  description: 'Daily trigger-calendar micro-check: re-verify board names whose dated milestone is imminent or just past',
  phases: [{ title: 'Check' }],
}
const DUE = [
 {
  "symbol": "WBD",
  "catalyst": "Judge Araceli Martinez-Olguin (N.D. Cal.) said she will rule by July 22, 2026 on the 12-state AG motion for a TRO blocking the Paramount Skydance acquisition of WBD at $31.00 cash plus ticking fee; a denial clears the last live obstacle to a Q3 close.",
  "milestone": "TRO ruling due by 2026-07-22; tender/exchange offer expiration extended to 2026-07-31 5:00pm ET; settlement anticipated Q3 2026",
  "score": 7,
  "tier": "ACTIVE",
  "trigger": "2026-07-22"
 },
 {
  "symbol": "ANAB",
  "catalyst": "Pending Delaware Chancery post-trial verdict in the AnaptysBio v. Tesaro/GSK dispute over whether GSK breached the Jemperli collaboration agreement, which could revert full Jemperli (dostarlimab) rights/royalties to Anaptys.",
  "milestone": "Trial concluded Jul 14-17, 2026; post-trial verdict pending (Chancery ruling expected within weeks-to-months) \u2014 no decision as of Jul 20, 2026.",
  "score": 6,
  "tier": "ACTIVE",
  "trigger": "2026-07-14"
 },
 {
  "symbol": "LBTYK",
  "catalyst": "Definitive Feb-18-2026 agreement to buy Vodafone's 50% of VodafoneZiggo (EUR1.0bn cash + 10% of NewCo), combining it with Telenet into Ziggo Group for a 2027 Euronext Amsterdam listing and spin of Liberty Global's remaining ~90% to holders.",
  "milestone": "2026-07-24 Q2-2026 results pre-market (deal-timing/Ziggo Group FCF-bridge update); then transaction close guided H2 2026 (regulatory approvals); then Euronext Amsterdam listing + ~90% spin during 2027",
  "score": 6,
  "tier": "ACTIVE",
  "trigger": "2026-07-24"
 },
 {
  "symbol": "RCI",
  "catalyst": "Rogers closes its C$4.35B buy-in of Kilmer Sports' remaining 25% of MLSE in Q4 2026 (league approvals pending), then sells a 20-30% minority stake in the consolidated sports/media/entertainment platform that management marks at >C$25B \u2014 a crystallization event well above what the ~US$18B-cap parent ",
  "milestone": "Announced July 6, 2026; MLSE 25% buy-in expected to close Q4 2026 subject to league (NHL/NBA/MLS/CFL) approvals; minority stake sale targeted within ~12 months (by mid-2027). Next date: Q2 2026 results and call, July 22, 2026 (pre-market) \u2014 first scheduled venue for stake-sale process detail and upd",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-07-22"
 },
 {
  "symbol": "CZR",
  "catalyst": "Signed $31.00/sh all-cash Fertitta Entertainment take-private (May 28, 2026) awaiting final Nevada Gaming Commission approval and FTC antitrust clearance, trading at a ~3.6% gross spread.",
  "milestone": "Nevada Gaming Commission final vote scheduled 2026-07-23 (next hard date); Q2 print 2026-07-28; FTC clearance and shareholder special meeting still undated.",
  "score": 4.5,
  "tier": "WATCH",
  "trigger": "2026-07-23"
 },
 {
  "symbol": "AVNS",
  "catalyst": "All-cash go-private by American Industrial Partners at $25.00/sh ($1.272B EV); all regulatory approvals received, stockholder vote 7/22, close by 7/27.",
  "milestone": "Stockholder special meeting vote July 22, 2026; expected close no later than July 27, 2026.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-07-22"
 },
 {
  "symbol": "DSX",
  "catalyst": "Diana Shipping's hostile all-shares tender for Genco at $27.34 ($24.80 cash + 1 DSX share) expires 5:00pm NY on July 24, 2026, with only 29.7% of non-Diana shares tendered and Genco's board unanimously recommending against it.",
  "milestone": "Tender expiration 2026-07-24 17:00 ET (already extended twice; further extension or lapse is the binary)",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-07-24"
 },
 {
  "symbol": "EA",
  "catalyst": "CFIUS national-security clearance of the PIF/Silver Lake/Affinity $210/share all-cash $55B take-private, with a contractual outside date of Sept 28, 2026 after the June 30 deadline was extended.",
  "milestone": "EU merger decision provisional deadline Jul 22, 2026 (FSR review running into late July); CFIUS outside date Sept 28, 2026",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-07-22"
 },
 {
  "symbol": "PSKY",
  "catalyst": "Judge Araceli Martinez-Olguin (N.D. Cal.) will rule by July 22, 2026 on the 12-state AG coalition's preliminary-injunction motion to block Paramount Skydance's ~$110B / $31.00-per-share cash acquisition of Warner Bros. Discovery, which PSKY has said it intends to close by end-September 2026.",
  "milestone": "2026-07-22 PI ruling deadline (N.D. Cal., State of California et al. v. Paramount Skydance, 4:26-cv-07116; hearing held 2026-07-17); secondary: 2026-09-30 outside-date after which WBD holders accrue a $0.25/share/quarter ticking fee",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-07-22"
 }
]
const SCHEMA = { type:'object', properties:{ symbol:{type:'string'}, still_forward:{type:'boolean'}, fired:{type:'boolean'}, outcome:{type:'string', enum:['FORWARD','FIRED_GOOD','FIRED_BAD','SLIPPED','RESOLVED_OTHER','UNCLEAR']}, new_date:{type:'string'}, note:{type:'string'} }, required:['symbol','still_forward','fired','outcome','note'] }
phase('Check')
const results = (await parallel(DUE.map(n => () =>
  agent(`Today is 2026-07-21. TRIGGER CHECK (fast, <=3 lookups via WebSearch/WebFetch + FMP MCP via ToolSearch). Board name ${n.symbol} carries: catalyst "${n.catalyst}" / milestone "${n.milestone}" (score ${n.score}, tier ${n.tier}). The milestone date ${n.trigger} is imminent or just passed. Determine ONLY: did the event FIRE (and favorably or adversely), SLIP (new date?), or is it still FORWARD? Do not re-underwrite the thesis. Deliverable = a SINGLE StructuredOutput call: {symbol, still_forward, fired, outcome (FORWARD/FIRED_GOOD/FIRED_BAD/SLIPPED/RESOLVED_OTHER/UNCLEAR), new_date (ISO or empty), note (1-2 sentences, cite source+date)}.`,
    { label: `trig:${n.symbol}`, phase: 'Check', schema: SCHEMA })
))).filter(Boolean)
return { checked: results.length, results }
