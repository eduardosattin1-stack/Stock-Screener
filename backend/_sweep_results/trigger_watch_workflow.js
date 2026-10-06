export const meta = {
  name: 'trigger-watch',
  description: 'Daily trigger-calendar micro-check: re-verify board names whose dated milestone is imminent or just past',
  phases: [{ title: 'Check' }],
}
const DUE = [
 {
  "symbol": "ARI",
  "catalyst": "Apollo Commercial REF has sold its ~$9B CRE loan book to Athene, deleveraged from $8.16B to $371M of debt, and has a board-adopted Plan of Complete Liquidation going to a shareholder vote on 2026-09-29, with $3.70-4.00/sh of excess cash due within 30 days of approval and $7.75-8.50/sh total remainin",
  "milestone": "Special meeting / dissolution vote 2026-09-29 (next date, 23 days out); first liquidating distribution of $3.70-4.00/sh within 30 days of approval, i.e. by late Oct 2026; conversion to a liquidating trust (mgr fee cut to 0.50% of net assets) thereafter, ~2-year realization of the balance.",
  "score": 6.5,
  "tier": "ACTIVE",
  "trigger": "2026-09-29"
 },
 {
  "symbol": "GPCR",
  "catalyst": "Structure Therapeutics has company-guided, hard-dated aleniglipron readouts landing now \u2014 topline 72-week ACCESS open-label-extension data in Q3 2026, then body-composition, type-2-diabetes/obesity and SWITCH trial data in Q4 2026 \u2014 with Phase 3 ACCOMPLISH first patients already dosed.",
  "milestone": "Q3 2026 (by 2026-09-30, i.e. within ~3 weeks): topline 72-week ACCESS OLE data \u2014 \"Topline 72-week aleniglipron ACCESS OLE data on track for Q3 2026\" (8-K ex-99.1, 2026-08-06). Then Q4 2026: body composition + T2D/obesity + SWITCH readouts.",
  "score": 6,
  "tier": "WATCH",
  "trigger": "2026-09-30"
 },
 {
  "symbol": "IRDM",
  "catalyst": "Rocket Lab's definitive cash+stock acquisition of Iridium ($27.00 cash plus a collared RKLB exchange ratio, 0.2400-0.4000, banded $67.50-$112.50) goes to an Iridium shareholder vote on 2026-09-24 with FCC license-transfer and CFIUS clearance still outstanding for a mid-2027 close.",
  "milestone": "2026-09-24 Iridium special shareholder meeting (definitive proxy filed, RKLB 424B3 effective); next gate = FCC license-transfer docket with SpaceX opposition letter filed 2026-08-28; CFIUS + close targeted mid-2027",
  "score": 6,
  "tier": "ACTIVE",
  "trigger": "2026-09-24"
 },
 {
  "symbol": "VERA",
  "catalyst": "ORIGIN 3 pivotal eGFR final efficacy analysis, pulled forward from 2027 to Q3'26 under an FDA-aligned revised plan, which would convert TRUTAKNA's proteinuria-based accelerated approval into full approval and is the only event that can establish eGFR-slope differentiation versus the five prior IgAN ",
  "milestone": "ORIGIN 3 eGFR topline \u2014 guided Q3 2026, reaffirmed 10-Aug-2026, therefore due on or before 30-Sep-2026 (<=23 days from 07-Sep-2026); sBLA submission Q4 2026; potential full approval 2027. No exact day has been guided.",
  "score": 6,
  "tier": "WATCH",
  "trigger": "2026-09-30"
 },
 {
  "symbol": "CCOI",
  "catalyst": "Cogent monetizes the remaining 14 converted Sprint data centers (~55MW) and refinances the $750M 2027 unsecured notes with a smaller, secured issue, each tranche cutting the 6.23x net-leverage overhang on a $503M equity stub.",
  "milestone": "2027 unsecured notes refi guided to close in Q3 2026 (i.e. by 2026-09-30, ~24 days out; not yet launched or priced as of 2026-09-06); next tranche update at Q3 earnings, early Nov 2026. The remaining-14 data-center leg has NO date \u2014 management said \"over the next several quarters.\"",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-09-30"
 },
 {
  "symbol": "EVMN",
  "catalyst": "Evommune reports top-line Phase 2b data for oral MRGPRX2 antagonist EVO756 in moderate-to-severe atopic dermatitis, company-guided to September 2026 on a fully-enrolled N=120 dose-ranging trial with a 12-week percent-change-in-EASI primary endpoint.",
  "milestone": "EVO756 Phase 2b AD top-line \u2014 guided \"September 2026\" in the Q2 press release (2026-08-06), narrowed from the earlier \"Q3 2026\"; next date = on or before 2026-09-30, i.e. within ~3.5 weeks of today (2026-09-06). No release as of 2026-09-06 (last EVMN press release on the tape is the 2026-08-06 Q2 re",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-09-30"
 },
 {
  "symbol": "GRAL",
  "catalyst": "FDA's Molecular and Clinical Genetics Panel votes on GRAIL's Galleri multi-cancer early-detection PMA on 2026-09-23 \u2014 the first MCED test ever taken to an FDA advisory panel.",
  "milestone": "2026-09-23 panel vote (docketed in the Federal Register 2026-08-10); FDA briefing documents post ~2026-09-19, two business days ahead, and typically move the stock before the vote itself. The binding PMA approval decision is a separate, undated later event.",
  "score": 5,
  "tier": "WATCH",
  "trigger": "2026-09-23"
 },
 {
  "symbol": "ABUS",
  "catalyst": "Arbutus commenced a $230M modified Dutch-auction issuer bid at $5.00-$5.75, cash-funded from Moderna settlement proceeds (SC TO-I filed 2026-08-24), expiring ~2026-09-29.",
  "milestone": "2026-09-29 tender expiration (SC TO-I filed 2026-08-24), clearing price + proration factor announced within days after; separately the Moderna contingent payment (up to $1.3B) is appeal-event-gated with no date.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-09-29"
 },
 {
  "symbol": "DBVT",
  "catalyst": "DBV must submit the VIASKIN Peanut Patch BLA for children aged 4-7 by end of Q3-2026 (on or before 2026-09-30), with FDA filing/acceptance ~60 days later and a sister 1-3yr toddler BLA guided for 2H-2026.",
  "milestone": "BLA submission (ages 4-7) by 2026-09-30 per guidance reaffirmed in the Q2-2026 10-Q filed 2026-07-16; FDA 60-day filing/acceptance decision ~Nov-Dec 2026; COMFORT-Toddlers-supported 1-3yr BLA guided 2H-2026; PDUFA action date not until 2027.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-09-30"
 },
 {
  "symbol": "FIP",
  "catalyst": "FTAI Infrastructure's signed $1.52B sale of Long Ridge Energy & Power to MARA Holdings (definitive agreement 2026-04-29/30) is still unclosed pending FERC change-of-control and HSR clearance, and at close strips ~$1.16B of Long Ridge project debt plus ~$300M of corporate debt, leaving a rail/termina",
  "milestone": "FERC change-of-control approval guided \"middle of Q3\" (Q1 call, May 2026); reaffirmed on the 2026-08-05 Q2 print as closing by end of Q3 2026 \u2014 hard milestone 2026-09-30, then post-close capital-structure detail at the Q3 print (early Nov 2026).",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-09-30"
 },
 {
  "symbol": "GDOT",
  "catalyst": "Closing of the CommerceOne/Smith Ventures three-way separation \u2014 Green Dot Bank merges into a new listed bank holdco, the non-bank fintech is sold to Smith Ventures, and GDOT holders receive $8.11 cash plus 0.2215 shares of the new BankCo \u2014 with only Federal Reserve, Alabama State Banking Dept and U",
  "milestone": "Both shareholder votes passed 2026-06-23 (>99% of GDOT shares voted in favor, ~72% of shares outstanding); HSR early termination already granted; company guides to close in Q3 2026, i.e. by 2026-09-30 \u2014 ~24 days out. Next date: Fed/Alabama/Utah bank approval orders, expected before 2026-09-30.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-09-30"
 },
 {
  "symbol": "KDP",
  "catalyst": "Board-approved tax-free separation of Keurig Dr Pepper into Beverage Co and Global Coffee Co following the Apr-1-2026 JDE Peet's close, with operational readiness targeted year-end 2026 and the split early 2027.",
  "milestone": "Chobani transactions ($800M stake repurchase + $125M Allentown PA facility) close in Q3-2026 (by 2026-09-30); Q3-26 earnings late Oct 2026; operational readiness target year-end 2026; Form 10 / separation early 2027.",
  "score": 4,
  "tier": "WATCH",
  "trigger": "2026-09-30"
 }
]
const SCHEMA = { type:'object', properties:{ symbol:{type:'string'}, still_forward:{type:'boolean'}, fired:{type:'boolean'}, outcome:{type:'string', enum:['FORWARD','FIRED_GOOD','FIRED_BAD','SLIPPED','RESOLVED_OTHER','UNCLEAR']}, new_date:{type:'string'}, note:{type:'string'} }, required:['symbol','still_forward','fired','outcome','note'] }
phase('Check')
const results = (await parallel(DUE.map(n => () =>
  agent(`Today is 2026-10-06. TRIGGER CHECK (fast, <=3 lookups via WebSearch/WebFetch + FMP MCP via ToolSearch). Board name ${n.symbol} carries: catalyst "${n.catalyst}" / milestone "${n.milestone}" (score ${n.score}, tier ${n.tier}). The milestone date ${n.trigger} is imminent or just passed. Determine ONLY: did the event FIRE (and favorably or adversely), SLIP (new date?), or is it still FORWARD? Do not re-underwrite the thesis. OUTCOME RULES: FIRED_GOOD/FIRED_BAD are TERMINAL only (deal closed/broke, approval/CRL issued, verdict entered, tender settled); if the situation CONTINUES with a new date -- even after an adverse interim event (TRO granted, extension, second request) -- use SLIPPED with new_date and describe the tilt in the note. Deliverable = a SINGLE StructuredOutput call: {symbol, still_forward, fired, outcome (FORWARD/FIRED_GOOD/FIRED_BAD/SLIPPED/RESOLVED_OTHER/UNCLEAR), new_date (ISO or empty), note (1-2 sentences, cite source+date)}.`,
    { label: `trig:${n.symbol}`, phase: 'Check', schema: SCHEMA })
))).filter(Boolean)
return { checked: results.length, results }
