export const meta = {
  name: 'trigger-watch',
  description: 'Daily trigger-calendar micro-check: re-verify board names whose dated milestone is imminent or just past',
  phases: [{ title: 'Check' }],
}
const DUE = [
 {
  "symbol": "GERN",
  "catalyst": "Protocol-specified interim analysis of the registrational Phase 3 IMpactMF trial (imetelstat, overall-survival primary endpoint, relapsed/refractory myelofibrosis), company-guided to 2H 2026.",
  "milestone": "IMpactMF interim analysis guided to 2H 2026 (Geron FY2025 release, 2026-02-25, reiterated 2026-05-06); next hard date Q2 2026 results 2026-08-05, where the window is likely refined.",
  "score": 6,
  "tier": "ACTIVE",
  "trigger": "2026-08-05"
 },
 {
  "symbol": "OPFI",
  "catalyst": "OppFi's signed definitive agreement to buy BNCCORP/BNC National Bank for ~$130M ($19.375 cash + 1.90 OPFI Class A per BNCC share, ~93/7 pro forma split), targeted to close Q4 2026, converting OppFi from a bank-partnership lender into a deposit-funded national-charter bank holding company \u2014 with OCC/",
  "milestone": "Q2 2026 results + regulatory-timeline update Aug 10, 2026 (after close); BNCC stockholder vote on the S-4/proxy still pending; OCC/Fed/FDIC decisions and targeted transaction close in Q4 2026.",
  "score": 6,
  "tier": "ACTIVE",
  "trigger": "2026-08-10"
 },
 {
  "symbol": "SVRA",
  "catalyst": "FDA decision on the MOLBREEVI (molgramostim inhalation) BLA for autoimmune pulmonary alveolar proteinosis, a would-be first-in-class orphan approval, at a PDUFA goal date of Nov 22 2026.",
  "milestone": "PDUFA goal date Nov 22 2026 (extended Apr 15 2026 from Aug 22 2026 on a three-month major-amendment clock reset); ~110 days forward as of 2026-08-03.",
  "score": 5.5,
  "tier": "ACTIVE",
  "trigger": "2026-08-22"
 },
 {
  "symbol": "ZIM",
  "catalyst": "Signed all-cash merger at $35.00/sh with Hapag-Lloyd (announced Feb-16-2026, ~$4.2B), shareholder-approved, now hostage to the State of Israel's decision on transferring the Special State Share to FIMI's \"New ZIM\" \u2014 stock at $26.07 leaves a 34.3% gross spread into a guided late-2026 close.",
  "milestone": "State-of-Israel / Special State Share decision on the FIMI \"New ZIM\" transfer (undated \u2014 Defense Ministry opposed as of Jul-6-2026; Netanyahu said the sale is not on the cabinet agenda). Company continues to guide close by late 2026 (Q4). Next hard date: Q2-2026 results Wed 2026-08-19 pre-market, fi",
  "score": 5.5,
  "tier": "ACTIVE",
  "trigger": "2026-08-19"
 },
 {
  "symbol": "AVIR",
  "catalyst": "Phase 3 C-FORWARD topline (880+ treatment-naive HCV patients, 17 countries ex-North America, enrollment completed Jun 25 2026) due around year-end 2026, followed by an NDA filing for bemnifosbuvir/ruzasvir.",
  "milestone": "C-FORWARD Phase 3 topline \"around year-end 2026\" (company guidance, PR 2026-06-25); NDA submission after that. Next hard date: Q2-26 10-Q / cash update, ~2026-08-12.",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-08-12"
 },
 {
  "symbol": "ATII",
  "catalyst": "Archimedes Tech SPAC Partners II (ATII) must get its Forge Nano S-4 (File 333-295563, amended 24-Jul-2026) declared effective and win a shareholder vote before the Nov-2026 outside date to close the ~$1.2bn ALD-semis / defense-battery combination.",
  "milestone": "S-4 amendment #2 filed 24-Jul-2026, still not effective; Forge Nano Morrisville NC gigafactory groundbreaking 19-Aug-2026; SEC effectiveness -> DEFM14A -> vote expected Q3/Q4-2026; merger outside date Nov-2026.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-19"
 },
 {
  "symbol": "BLTE",
  "catalyst": "FDA filing decision on the tinlarebant NDA for Stargardt disease type 1 (rolling submission completed 2026-06-12) \u2014 acceptance plus the priority-review determination and assigned PDUFA date, the last procedural leg before an approval decision.",
  "milestone": "FDA 60-day filing decision due ~2026-08-11 (Day-74 letter with review-designation/PDUFA date by late Aug 2026); Q2-2026 results webcast expected mid/late Aug 2026. As of 2026-08-03 no acceptance PR has been issued (latest company release 2026-07-20).",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-11"
 },
 {
  "symbol": "CDZI",
  "catalyst": "BLM granted the Northern Pipeline right-of-way (2026-07-10) and Fenner Gap executed CMAR guaranteed-maximum-price construction contracts (2026-07-28) explicitly to support project financing, leaving the financing close (WIFIA application up to $194M + San Bernardino Water and Power Authority municip",
  "milestone": "Q2-2026 10-Q / earnings, expected ~2026-08-13 (Q1 landed 2026-05-14), the next hard date for WIFIA status, SBWPA bond progress and any construction-start date. The company has stated NO financing close date, NO construction start date and NO in-service date - the forward leg is real but undated.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-13"
 },
 {
  "symbol": "CMPS",
  "catalyst": "Compass has guided to completing the rolling NDA filing for COMP360 (synthetic psilocybin, treatment-resistant depression) by Q4 2026, with an FDA decision and 1H-2027 launch as the actual binary.",
  "milestone": "Q2/1H-2026 results call 2026-08-05 (guidance reaffirmation on the Q4 filing-completion date); rolling NDA submission completion targeted Q4 2026; FDA action / launch 2027.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-05"
 },
 {
  "symbol": "COTY",
  "catalyst": "Coty's long-running strategic review of Consumer Beauty (CoverGirl/Rimmel/Sally Hansen/Max Factor + Brazil, ~$1.6B sales) remains unresolved with no committed decision date, while the one hard leg of the flagged thesis - the $400M Gucci licence hand-back to Kering - already fired on 2026-07-07.",
  "milestone": "FY26 Q4/full-year results 2026-08-19 (confirmed on the earnings calendar, consensus EPS -$0.007 on $1.194B revenue) - a venue where management may update the review, not a committed decision date; the separation itself carries no deadline and has slipped for ~18 months.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-19"
 },
 {
  "symbol": "GILT",
  "catalyst": "Gilat is buying most of Comtech's Satellite &amp; Space Communications segment for $157.5M cash under a definitive agreement signed 2026-06-15, funded entirely from existing cash, expected to close by end-2026 pending CFIUS and HSR (FTC/DOJ) clearance.",
  "milestone": "2026-08-05 Q2-2026 results (first print with deal-progress/pro-forma commentary); Canaccord Growth Conference 2026-08-12; regulatory clearance and close \"by the end of 2026\" \u2014 no fixed closing date disclosed.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-12"
 },
 {
  "symbol": "KDP",
  "catalyst": "Tax-free separation of Keurig Dr Pepper into two independent listed companies \u2014 Beverage Co. and Global Coffee Co. \u2014 the second leg of the JDE Peet's two-step, now company-guided to \"early 2027\" and gated on post-JDEP deleveraging milestones.",
  "milestone": "Separation \"targeted for early 2027\" (reaffirmed 2026-06-23). Next hard date: Q2 2026 results before the open Thursday 2026-08-06 (three days out) \u2014 the checkpoint for net-leverage progress against the milestone that gates the split. Form 10 / investor-day disclosure of the two entities' standalone ",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-06"
 },
 {
  "symbol": "NN",
  "catalyst": "FCC draft NPRM to reconfigure the Lower 900 MHz band (902-928 MHz) for NextNav's terrestrial 5G PNT network has sat at OMB/OIRA interagency review since March 2026 and has not yet been released.",
  "milestone": "No dated regulatory milestone exists - OIRA review carries no statutory deadline and no FCC open-meeting item has been circulated (Communications Daily 2026-06-23: NPRM \"likely to come soon\"; SIA on 2026-05-12 expected it \"this summer\" - both undated). Nearest hard date is the Q2 2026 earnings call ",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-11"
 },
 {
  "symbol": "ROIV",
  "catalyst": "FDA action on Priovant's brepocitinib NDA in dermatomyositis, with a PDUFA target date in Q3 CY2026 and commercial launch guided for end-September 2026 \u2014 would be the first targeted therapy approved for DM.",
  "milestone": "PDUFA target action date in Q3 CY2026 (exact day not disclosed publicly); launch guided end-September 2026. Nearest hard date: Q1 FY27 earnings/business update Thursday 2026-08-06, which should refresh launch-readiness commentary.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-06"
 },
 {
  "symbol": "SID",
  "catalyst": "CSN Inova Ventures' any-and-all exchange of US$1.3bn 6.750% 2028 notes into 11.000% 2030 notes plus cash expires 10-Aug-2026 (70% / US$910mn minimum tender), running alongside an unsigned CSN Cimentos control sale plus CSN Infra Newco stake targeted to sign Q3/Q4-2026 for R$15-18bn against R$38.2bn ",
  "milestone": "2026-08-10 \u2014 exchange offer expiration, 5:00pm NY (consideration US$746.15 new 11% 2030s + US$253.85 cash per US$1,000; 70%/US$910mn minimum tender condition). Next equity-relevant date: unsigned CSN Cimentos control sale + Infra Newco stake, company-targeted to sign Q3/Q4-2026 \u2014 a target, not a sch",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-10"
 },
 {
  "symbol": "RDN",
  "catalyst": "Radian closed the sale of its Real Estate Services business to PLACE and signed a definitive agreement to sell its Title business to PLACE (expected Q4-2026 close, pending regulatory approval), completing the exit from non-insurance services into a pure multi-line specialty insurer.",
  "milestone": "Q2-2026 results 2026-08-05 after close (call 08-06 10:00 ET) is the first read on pro-forma segment reporting; Title sale to PLACE expected to close Q4-2026 pending regulatory approvals; new CEO Weinbach seated 2026-08-13.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-13"
 },
 {
  "symbol": "TMC",
  "catalyst": "NOAA found TMC USA's consolidated DSHMRA exploration-licence + commercial-recovery application in full compliance (announced 1-May-2026, determination 30-Apr-2026) over a ~65,000 km2 CCZ area, with the company guiding to an actual commercial-recovery permit before end-Q1-2027.",
  "milestone": "Q2-2026 corporate update 14-Aug-2026 (cash/burn check, not a catalyst); NOAA commercial-recovery permit decision guided \"before end of Q1 2027\" \u2014 company guidance, NOT a statutory NOAA deadline; ITLOS Cases 34/35 merits still pending after the 18/20-Jul-2026 provisional-measures orders.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-14"
 },
 {
  "symbol": "NAMS",
  "catalyst": "European Commission formal adoption of marketing authorization for Ubeslo (obicetrapib) and Evlarco (obicetrapib+ezetimibe FDC) in 2H-2026, following the CHMP positive opinion of 2026-07-24, with Menarini leading EU commercialization.",
  "milestone": "EC decision expected 2H-2026 (standard ~67 days post-CHMP, i.e. ~late Sept/Oct 2026); RUBENS topline year-end 2026; PREVAIL CVOT interim analysis Q4-2026 with results 1Q-2027; Investor Day 2026-08-05",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-08-05"
 }
]
const SCHEMA = { type:'object', properties:{ symbol:{type:'string'}, still_forward:{type:'boolean'}, fired:{type:'boolean'}, outcome:{type:'string', enum:['FORWARD','FIRED_GOOD','FIRED_BAD','SLIPPED','RESOLVED_OTHER','UNCLEAR']}, new_date:{type:'string'}, note:{type:'string'} }, required:['symbol','still_forward','fired','outcome','note'] }
phase('Check')
const results = (await parallel(DUE.map(n => () =>
  agent(`Today is 2026-08-19. TRIGGER CHECK (fast, <=3 lookups via WebSearch/WebFetch + FMP MCP via ToolSearch). Board name ${n.symbol} carries: catalyst "${n.catalyst}" / milestone "${n.milestone}" (score ${n.score}, tier ${n.tier}). The milestone date ${n.trigger} is imminent or just passed. Determine ONLY: did the event FIRE (and favorably or adversely), SLIP (new date?), or is it still FORWARD? Do not re-underwrite the thesis. OUTCOME RULES: FIRED_GOOD/FIRED_BAD are TERMINAL only (deal closed/broke, approval/CRL issued, verdict entered, tender settled); if the situation CONTINUES with a new date -- even after an adverse interim event (TRO granted, extension, second request) -- use SLIPPED with new_date and describe the tilt in the note. Deliverable = a SINGLE StructuredOutput call: {symbol, still_forward, fired, outcome (FORWARD/FIRED_GOOD/FIRED_BAD/SLIPPED/RESOLVED_OTHER/UNCLEAR), new_date (ISO or empty), note (1-2 sentences, cite source+date)}.`,
    { label: `trig:${n.symbol}`, phase: 'Check', schema: SCHEMA })
))).filter(Boolean)
return { checked: results.length, results }
