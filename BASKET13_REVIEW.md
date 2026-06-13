# Basket 13 — Catalyst Sleeve · Agent Comments for Review

*Generated 2026-06-13 · 10 held seats (55.5% invested) · last run 2026-06-13 · paper basket, nothing executed*

Pipeline: enriched board → entry/staging filter → **Catalyst-CRO** (attacks ONLY the trade — live edge / tradeability / window↔expression / driver tag; catalyst reality settled upstream by the scan→deep→skeptic tier; value/quality attacks forbidden) → **Director** (selection + sizing under HARD caps: ≤2/driver, ≤40 NAV weight-points/super-cluster, 8–12 names, risk-to-floor ≤1.5% NAV, binaries defined-risk ≤2%, staging equity-only half-weight; held seats run to resolution and consume combined-cap headroom) → deterministic cap validator → tracker stamps at CRO-verified live prices.

---
## 1 · The basket (10 held)

### GDOT — Green Dot Corporation
`14% · equity · merger_arb · Deal_close_generic (Deal-completion) · score 7.0 · edge M · entry 2026-06-10 @ 12.75 (cro_live_check)`
- **Expected:** R:R 1.56:1 · milestone 2026-09-30 · review: Expected close 2026-09-30; review on close or any delay/regulatory notice before then.
- **Risk-to-floor (computed):** 1.043% of NAV (cap 1.5)
- **Director — why this seat:** Cleanest ratio carry in the pool: 11.6% gross spread to the $14.23 deal value over ~112 days (~38% annualized) with zero price drift since the dossier and the tightest floor in the basket (-7.5%). Top weight because the floor distance is smallest — 14% weight risks only ~1.04% NAV to floor.
- **Director — what kills it:** Deal termination or a material regulatory objection; price through the $11.80 floor signals the market pricing a break.

**CRO verdict: TRADE**
- **1 · Edge at entry (live re-check):** Live $12.75 (FMP batch-quote 2026-06-10) — unchanged from the dossier price, zero drift since valuation_asof 2026-06-08. Spread to $14.23 deal value = +11.6% gross; downside to $11.80 floor = -7.5%; R:R = 1.48/0.95 = 1.56, identical to the dossier's computed_rr. Edge fully intact; ~11.6% over ~112 days is ~38% annualized on the spread.
- **2 · Tradeability:** Stock expression on a NYSE name: ~438k shares / ~$5.6M traded today, $723M market cap, listed options also available if a collar is ever wanted. Standard arb size executes without friction. No short leg, no borrow question.
- **3 · Window ↔ expression:** Milestone 2026-09-30 (112 days). Expression is common stock held through close — no expiry to clear, window satisfied by construction. If close slips past Q3 the position simply carries; only cost is annualized-return decay, not a structural loss.
- **4 · Driver tag:** Deal_close_generic — confirmed; unique driver in this batch, no collision.

### UNF — UniFirst Corporation
`8% · equity · merger_arb · US_antitrust (Deal-completion) · score 7.0 · edge M · entry 2026-06-13 @ 267.0 (cro_live_check)`
- **Expected:** R:R 1.86:1 · milestone 2026-11-30 · review: Antitrust clearance checkpoints into the 2026-11-30 expected close; re-confirm timeline before any size-up.
- **Hedge leg:** -0.772 CTAS per share, ref $176.28
- **Risk-to-floor (computed):** 0.272% of NAV (cap 1.5)
- **Director — why this seat:** Cash + 0.7720 CTAS deal worth ~$293.86 vs $270.48 leaves an 8.6% gross spread to the 11/30 close; recorded with the CRO entry limit <= $267 and the 0.7720 CTAS short hedge to isolate the spread. Held to 8% (well under the floor-math cap) because live R:R compressed to 1.86 after the pop and a break would overshoot the $257.91 standalone floor.
- **Director — what kills it:** HSR second request that materially derails the timeline, or deal repriced/terminated — a break trades well below the symmetric floor (200d avg $209).

**CRO verdict: TRADE_WITH_CONDITIONS**
- **1 · Edge at entry (live re-check):** Deal = $155 cash + 0.7720 CTAS. CTAS live $179.87 (FMP) -> deal value $293.86. UNF live $270.48 (FMP, +2.4% today). Gross spread $23.38 = 8.6% to the 11/30 close (~18% annualized). Vs dossier 6/08 the spread was ~10.2% ($27 on $264) - modest compression. But the symmetric live R:R to the standalone floor $257.91 = 23.38/12.57 = 1.86 vs dossier 4.38 (below half), driven by today's UNF pop against a close floor.
- **2 · Tradeability:** Both legs deeply liquid: UNF ADV ~297k sh (~$80M/day) tight-spread, CTAS very liquid. Caution: the $257.91 floor is generous - a deal break likely overshoots well below it (UNF 200d avg $209, 52w low $148), so size for break risk larger than the symmetric R:R implies.
- **3 · Window ↔ expression:** Stock / merger-arb expression - no option expiry to clear. 11/30 expected close (173d); an antitrust second-request slip only erodes annualized return, it does not break the position. Tradeable as equity.
- **4 · Driver tag:** US_antitrust (Cintas-UniFirst HSR review). Confirmed; sole name on this driver in the batch - no clash.
- ⚠ **Condition:** Use a limit; do not chase today's +2.4% pop - enter UNF <= ~$267 to keep gross spread >=~10% and lift live R:R back toward the dossier
- ⚠ **Condition:** Hedge the share-ratio leg: short 0.7720 CTAS per UNF to isolate the ~$23/sh cash+spread
- ⚠ **Condition:** Re-confirm the HSR/antitrust timeline still supports the 11/30 close before sizing

### FIP — FTAI Infrastructure Inc.
`10% · equity · distressed · Refi_restructuring (Idiosyncratic) · score 8.0 · edge M · entry 2026-06-10 @ 4.56 (cro_live_check)`
- **Expected:** R:R 6.73:1 · milestone 2026-09-30 · review: 2026-09-30 refi/de-levering milestone; interim review on any debt-removal announcement.
- **Risk-to-floor (computed):** 1.447% of NAV (cap 1.5)
- **Director — why this seat:** Highest ratio edge among survivors — live R:R 6.73 to the $9 de-levering target against a market-tested $3.90 floor (the 52-week low), on a dated Q3-2026 refi milestone. Equity-only per CRO (options chain is dead); live $4.56 sits comfortably under the $4.80 entry limit, and 10% weight risks 1.45% NAV to floor.
- **Director — what kills it:** Refi/de-levering fails to materialize in Q3, or price loses the $3.90 floor — the one market-tested level in the thesis; the $0.66 denominator makes the edge hypersensitive above ~$4.80.

**CRO verdict: TRADE_WITH_CONDITIONS**
- **1 · Edge at entry (live re-check):** Live $4.56 (FMP batch-quote 2026-06-10, +0.9%; IBKR last $4.56 at close) vs dossier $4.52. Recomputed recovery R:R = (9 - 4.56) / (4.56 - 3.90) = 6.73 (dossier 7.23). Edge intact. Caution: the floor $3.90 is exactly the 52-week low and the R:R denominator is only $0.66, so the ratio is hypersensitive to entry price — at $4.85 it is already down to ~4.3.
- **2 · Tradeability:** Equity ADV is the constraint: only $4.6M/day 90d USD volume (IBKR), and the resting book is thin (last quote $4.44 x $4.76, 7% wide off-hours). A position must be worked over multiple sessions on limits. The dossier's optional Q3/Q4-2026 call overlay is NOT tradeable: avg option volume is ~32 calls / 42 puts per day — a dead chain. Equity-only.
- **3 · Window ↔ expression:** Milestone 2026-09-30 (112 days), refi/de-levering event. Expression is common equity — no expiry, window clears by construction. The call-overlay window question is moot since the chain fails tradeability.
- **4 · Driver tag:** Refi_restructuring — confirmed; unique driver in this batch, no collision.
- ⚠ **Condition:** Equity only — drop the Q3/Q4 call overlay entirely (avg ~74 option contracts/day total, no executable OI)
- ⚠ **Condition:** Entry limit <= $4.80; above that the recomputed R:R falls below ~4.4 (versus 7.23 dossier) and the denominator sensitivity bites
- ⚠ **Condition:** Size <= ~10-15% of ADV per day (~$500-700k/day max working rate against $4.6M ADV); no market orders
- ⚠ **Condition:** Re-check the floor if price approaches $3.90 — floor equals the 52-week low, the one market-tested level in the thesis

### FIG — Figma, Inc.
`5% · equity · forced_seller · Forced_divest_flow (Idiosyncratic) · score 4.0 · edge H · STAGING · entry 2026-06-10 @ 20.49 (cro_live_check)`
- **Expected:** R:R 3.85:1 · milestone soft/undated · review: Verify and review at the final lockup expiration date (per CRO condition, confirm the exact date and remaining share count).
- **Risk-to-floor (computed):** 0.73% of NAV (cap 1.5)
- **Director — why this seat:** Post-IPO lockup supply-clearing mean-reversion: live R:R improved to ~3.85 at $20.49 vs the $17.50 floor, and at ~$340M/day ADV it is the most executable flow trade in the pool. Staging half-weight equity; thesis is supply clearing, so exit near FV $32, not an open-ended re-rate.
- **Director — what kills it:** Final-unlock date slips materially or remaining locked supply is larger than modeled; close below the $17.50 floor kills the mean-reversion setup.

**CRO verdict: TRADE_WITH_CONDITIONS**
- **1 · Edge at entry (live re-check):** Live 20.49 (FMP batch-quote, ts 2026-06-10) vs dossier 21.10 asof 2026-06-08 — down 2.9%, edge IMPROVED. R:R recomputed at 20.49: upside to FV 32 = +56%, downside to floor 17.5 = -14.6%, ~3.85:1 vs dossier computed_rr 3.02.
- **2 · Tradeability:** Highly liquid — ADV ~16.6M sh x $20.5 = ~$340M/day, large cap ~$10B; listed US options confirmed (IBKR contract 802794976, NYSE). Equity expression trivially tradeable; no spread/borrow concern for a long.
- **3 · Window ↔ expression:** dated_milestone=null, staging=true, but the real driver is the IPO lockup / forced-divest supply clearing (IPO'd ~2025, now 20.49 vs 52-wk high 142.92, sitting near 50d 20.55). Equity mean-reversion hold THROUGH final unlock — not a positive re-rate. Confirm the actual final-unlock date before sizing; if it has slipped or supply is larger than modeled, reassess. No option-expiry constraint since equity.
- **4 · Driver tag:** Forced_divest_flow confirmed (forced_seller lane) — supply-clearing/lockup mechanics consistent with the post-IPO collapse and activist (Findell 5/28) backdrop. Unique driver in this batch (no second forced-seller); no cluster conflict.
- ⚠ **Condition:** Express as EQUITY (own the suppressed underlying)
- ⚠ **Condition:** Entry limit <= ~$21 to keep R:R >= ~3:1 (do not chase post-unlock bounce)
- ⚠ **Condition:** Verify the final-unlock date and remaining lock-up share count before sizing; if unlock slips materially, re-adjudicate window
- ⚠ **Condition:** Thesis is mean-reversion after supply clears, not a fundamental re-rate — exit near FV 32, not open-ended

### BLCO — Bausch + Lomb (BHC 88% overhang)
`5% · equity · forced_seller · Forced_divest_flow (Idiosyncratic) · score 5.0 · edge H · STAGING · entry 2026-06-10 @ 15.65 (cro_live_check)`
- **Expected:** R:R 2.94:1 · milestone soft/undated · review: Any BHC stake-disposition or strategic-review announcement; quarterly re-check of the overhang status.
- **Risk-to-floor (computed):** 1.23% of NAV (cap 1.5)
- **Director — why this seat:** BHC's 88% stake suppresses a $26.97 SOP value vs $15.65 live — R:R 2.94 with 84% of dossier edge retained. Takes the second Forced_divest seat after MGNI was passed on edge compression; staging half-weight equity, accumulation-only with limits per CRO (covered-call overlay dropped — the chain is near-dead).
- **Director — what kills it:** BHC restructures around the stake with no disposition path (overhang becomes permanent), or the $11.80 floor breaks.

**CRO verdict: TRADE_WITH_CONDITIONS**
- **1 · Edge at entry (live re-check):** Live $15.65 (FMP/IBKR 6/9 close) vs dossier mark $15.18 (asof 6/8). Recomputed SOP R:R = (26.97-15.65)/(15.65-11.80) = 2.94 vs dossier 3.49 — 84% of dossier R:R retained, well above the half line. Edge intact; R:R stays >= 3.0 at entries <= $15.55.
- **2 · Tradeability:** Equity leg: only $7.4M avg 90d USD volume (IBKR) — thin for a $5.6B name because BHC holds 88% and the public float is ~12%; cap the position so it's <= ~5-10% of ADV and expect poor off-hours depth (pre-market quote was 14.71/15.98). Covered-call leg FAILS the cost test: avg option volume is 90 calls / 1 put per DAY — the chain is near-dead, spreads will be a large fraction of premium. The 'sell covered calls while waiting' overlay does not exist at acceptable cost.
- **3 · Window ↔ expression:** Undated milestone — BHC's 88% stake disposition has no fixed date (it's an overhang-resolution flow trade). Staging rule maps to equity; no expiry to clear. The CC overlay, if ever written, has no window constraint but fails on liquidity regardless.
- **4 · Driver tag:** CONFIRMED: Forced_divest_flow — BHC's 88% stake disposition/distribution is genuine forced-divest flow in BLCO shares. FLAG: MGNI in this batch carries the same tag — Director cap applies as-tagged, though MGNI is arguably mistagged (antitrust remedy, not seller flow), in which case the true overlap dissolves.
- ⚠ **Condition:** Equity-only expression: drop the covered-call overlay (avg OI/volume ~90 calls/day cannot fill at acceptable cost); if a CC is ever written, limit-at-mid only and only where strike OI > 100
- ⚠ **Condition:** Size to <= ~5-10% of the $7.4M/day ADV (float is ~12% of shares out); accumulate with limits, no market orders
- ⚠ **Condition:** Director must adjudicate the Forced_divest_flow dupe with MGNI

### CELC — Celcuity Inc.
`1.5% · debit spread exp 2026-09-18 · bio_convergence · FDA_clinical_readout (FDA/biotech) · score 8.0 · edge H · entry 2026-06-10 @ 92.59 (cro_live_check)`
- **Expected:** EV 50.1% · milestone 2026-07-17 · review: 2026-07-17 clinical readout.
- **Director — why this seat:** Highest-score H-grade unconditional TRADE in the batch: p=0.85 to $153 on the 7/17 readout, live EV +50% after the pop. The Sep-18 95/155 call spread defines risk and sells back the ~80% event IV the CRO flagged on outright calls, clearing the milestone with +1 monthly margin; premium sized at 1.5% because its EV is roughly half EYPT/VRDN's.
- **Director — what kills it:** Primary-endpoint miss on the 7/17 readout — spread premium is the full and only loss.

**CRO verdict: TRADE**
- **1 · Edge at entry (live re-check):** Live $92.59 (FMP batch-quote 2026-06-10, +5.9% on the day; IBKR real-time last $92.70) vs dossier $87.43. Recomputed: upside to $153 = +65.2%, downside to $60 = -35.2%, payoff 1.85 (dossier 2.39), EV = 0.85*0.652 - 0.15*0.352 = +50.1% (dossier +59.0%). ~15% EV compression after today's pop — still far above the half-R:R kill line. Edge intact.
- **2 · Tradeability:** Equity expression, and it is the most liquid name in the batch: $110M/day 90d USD ADV (IBKR), 1.37M shares today. Any realistic sleeve position is a rounding error vs ADV. Options are active (avg ~2,337 calls / 1,177 puts daily) but annual IV ~80% — dossier's own note that July/Aug calls carry rich event IV is confirmed; equity is the right expression.
- **3 · Window ↔ expression:** Milestone 2026-07-17, 37 days out. Equity has no expiry — window clears by construction. No slippage history concern for the expression.
- **4 · Driver tag:** FDA_clinical_readout — confirmed. FLAG: same driver as AMLX and DFTX (three names, one driver) — Director cap applies; this is the strongest of the three on edge grade (H) and tradeability.

### VRDN — Viridian Therapeutics, Inc.
`2% · debit spread exp 2026-08-21 · bio_convergence · FDA_approval_decision (FDA/biotech) · score 6.0 · edge H · entry 2026-06-10 @ 16.31 (cro_live_check)`
- **Expected:** EV 105.0% · milestone 2026-06-30 · review: 2026-06-30 FDA approval decision.
- **Director — why this seat:** Nearest hard catalyst in the basket — 6/30 FDA decision in 20 days at p=0.9, EV ~+105%, with equity still near its 52-week low and the only genuinely liquid options chain among the dated binaries. Aug-21 expiry gives +1 monthly margin past the decision; 2% premium-at-risk.
- **Director — what kills it:** CRL or negative FDA decision on 6/30 — premium is the full loss.

**CRO verdict: TRADE**
- **1 · Edge at entry (live re-check):** Live $16.31 (FMP, +3.7% today) vs dossier $15.73 - edge intact; still far under 200d $24.25 and near 52w low $13.18. Binary EV unchanged: ~90% to $35 / $8 floor, payoff ~2.5x. No compression.
- **2 · Tradeability:** Most tradeable binary in the batch: ~$46M ADV, stock spread $15.80/$16.25 (~2.8%), avg ~585 calls/day (today 631), IV ~91%. Options genuinely liquid; equity trivially so.
- **3 · Window ↔ expression:** Milestone 6/30 (20d). Equity = clean expression, no window risk. Option route: July monthly (7/17) is only the first expiry past 6/30 - use Aug (8/21) for +1 monthly margin against an FDA date slip.
- **4 · Driver tag:** FDA_approval_decision (veligrotug TED BLA, PDUFA 6/30). Confirmed. CLASH FLAG: ZYME in this same batch also resolves on FDA_approval_decision - flag the pair to the Director for the driver cap.

### AQST — Aquestive Therapeutics, Inc.
`4.5% · equity · bio_convergence · FDA_approval_decision (FDA/biotech) · score 6.5 · edge H · STAGING · entry 2026-06-10 @ 3.99 (cro_live_check)`
- **Expected:** EV 69.8% · milestone 2026-09-30 · review: Anaphylm resubmission by 2026-09-30; then re-stage for the FDA action window (Q1-2027).
- **Risk-to-floor (computed):** 1.398% of NAV (cap 1.5)
- **Director — why this seat:** Strongest live edge in the batch per the CRO check (+69.8% EV, payoff 3.6x) into the Q3 Anaphylm resubmission. Staging-rule equity (the thin chain cannot offer the Apr-2027+ expiries the post-resubmission window requires); 4.5% weight is jointly bound by the half-weight rule and a 1.49% risk-to-floor.
- **Director — what kills it:** Resubmission slips past Q3-2026 or a new CRL-grade deficiency is disclosed; price through the $2.75 floor.

**CRO verdict: TRADE**
- **1 · Edge at entry (live re-check):** Live $3.99 (FMP/IBKR 6/9 close) vs dossier mark $3.91 (asof 6/8). Recomputed: payoff (8.5-3.99)/(3.99-2.75)=3.64 vs dossier 3.96 (92% retained); binary EV=(6.775-P)/P = 69.8% vs dossier 73.3%. Edge intact — strongest live edge in the batch.
- **2 · Tradeability:** Equity (the dossier's primary instrument): $6.1M avg 90d USD volume on a $396M cap — fine for a small sleeve position with limits; quote 3.90/3.99. Options: avg 368 calls / 817 puts per day — too thin for long-dated calls at acceptable cost on a $4 stock; I disagree with the dossier's 'long-dated calls viable' aside — equity only.
- **3 · Window ↔ expression:** Milestone 2026-09-30 (~112d) is the Anaphylm RESUBMISSION — a milestone, not the FDA verdict (the dossier says so itself), and this path has already slipped once (original filing drew a CRL). Equity clears trivially with no expiry. Any optionality would need to clear the post-resubmission FDA action window (Class 1/2 review = ~2-6 months after, i.e. into Q1-2027) — requiring Apr-2027+ expiry the thin chain can't offer at cost. Equity-only resolves the window cleanly.
- **4 · Driver tag:** CONFIRMED: FDA_approval_decision (terminal driver is the FDA action on the Anaphylm resubmission; the 9/30 date is the resubmission gate on that path). FLAG: RARE in this same batch also resolves on FDA_approval_decision — Director same-driver cap applies to the pair.

### WVE — Wave Life Sciences Ltd.
`3.5% · equity · bio_convergence · FDA_pathway_feedback (FDA/biotech) · score 6.0 · edge H · STAGING · entry 2026-06-10 @ 5.78 (cro_live_check)`
- **Expected:** EV 20.6% · milestone 2026-07-31 · review: Mid-2026 FDA pathway feedback (soft) — hard review end-August 2026 if no communication has landed.
- **Risk-to-floor (computed):** 1.381% of NAV (cap 1.5)
- **Director — why this seat:** Mid-2026 FDA feedback on the WVE-006 accelerated-approval pathway — re-tagged FDA_pathway_feedback per the CRO's explicit condition (regulatory inflection, not an approval verdict), which adds a distinct driver lane to the FDA cluster. The soft date forces staging-equity treatment despite usable option liquidity; 3.5% weight risks 1.38% NAV to the $3.50 floor.
- **Director — what kills it:** FDA declines the accelerated pathway or the AATD program is deprioritized; floor break at $3.50.

**CRO verdict: TRADE_WITH_CONDITIONS**
- **1 · Edge at entry (live re-check):** Live $5.78 (FMP batch-quote, ts 2026-06-10) vs dossier $5.70 — moved +1.4%, edge intact. Recomputed to FV $11 = +90% upside; R:R = 5.22 up : 2.28 down = ~2.29:1 (vs dossier payoff 2.41). No compression.
- **2 · Tradeability:** BEST option liquidity in the batch: avg 1290 call / 135 put per day (today 3123 call), 90d ADV ~$27.8M, annual IV ~90%, OI put/call ~0.52. Both equity and a long call are genuinely tradeable; a protective put market exists. This is the one name where capping downside via a long call is realistic.
- **3 · Window ↔ expression:** DATE/DRIVER MIS-STATED. The mid-2026 event is FDA FEEDBACK on a potential ACCELERATED-APPROVAL PATHWAY for WVE-006 (AATD) — a regulatory engagement / inflection, NOT a PDUFA approval decision, and 'mid-2026' is SOFT, not a hard Jul 31. A July option could easily miss a soft, slip-prone feedback timeline. Use Aug/Sep-2026+ expiry or equity.
- **4 · Driver tag:** CORRECTION: tagged FDA_approval_decision but it is really an FDA_regulatory/clinical inflection (accelerated-approval pathway FEEDBACK on WVE-006), not an approval decision. DUPLICATE FLAG: as currently tagged it duplicates BBIO's FDA_approval_decision; on the corrected tag it instead sits closer to the clinical_readout cluster. Either way, flag for the Director cap.
- ⚠ **Condition:** Re-tag the driver: this is FDA pathway-feedback / regulatory inflection, not an approval decision
- ⚠ **Condition:** Do NOT use a July expiry against a soft 'mid-2026' window — use Aug/Sep 2026 or later, or equity
- ⚠ **Condition:** Given real put liquidity, a long call to cap the micro-cap binary downside is acceptable here

### AMLX — Amylyx Pharmaceuticals, Inc.
`2% · defined risk option exp 2026-10 or 2026-11 monthly (clears Q3 readout +1) · bio_convergence · FDA_clinical_readout (FDA/biotech) · score 6.0 · edge M · entry 2026-06-13 @ 14.59 (cro_structured)`
- **Expected:** EV 45.1% · milestone 2026-09-30 · review: LUCIDITY avexitide PBH Phase 3 topline, Q3 2026 (conservative milestone 2026-09-30); confirm option leg OI/spread at open before lifting.
- **Director — why this seat:** Only FDA_clinical_readout survivor that is hard-dated (Q3-2026 LUCIDITY avexitide topline, 109d) AND non-staging, so the mandated defined-risk option for a dated binary is actually constructible; ev_pct 0.4512 at win 0.62 with edge surviving the +12% run-up (payoff still >half-dossier).
- **Director — what kills it:** Negative or ambiguous LUCIDITY topline (PBH avexitide miss) drives equity toward the $4 floor; defined premium is the max loss. Also killed if a clean defined-risk call cannot be built at acceptable OI/spread and the only path is naked equity exposure to the floor.

**CRO verdict: TRADE_WITH_CONDITIONS**
- **1 · Edge at entry (live re-check):** Live $14.59 (FMP Fri 6/12 close; NASDAQ shut, this is the executable last print) vs dossier asof $13.01 = +12.1% run-up BEFORE the event. Binary EV name, not a spread: dossier ev_pct 0.4512, payoff 1.66, win 0.62, FV $28 / floor $4. Recomputed off the higher entry: win upside now ~+92% (28/14.59) vs loss ~-73% (4/14.59); the +12% pre-pay erodes the payoff multiple from 1.66 toward ~1.27, still >half dossier R:R so edge survives but is thinner. EV remains clearly positive at win_prob 0.62.
- **2 · Tradeability:** Equity is clean: 90d ADV ~$16.8M (FMP), $1.21B mkt cap — supports a real position. Options exist but are THIN: avg ~160 call / 66 put contracts/day (IBKR underlying option volume), so a long-call binary expression will pay a wide spread and have shallow OI at strikes near $28. Define-risk via calls only if a specific contract shows acceptable spread/OI; otherwise size in equity.
- **3 · Window ↔ expression:** LUCIDITY avexitide PBH Phase 3 enrollment COMPLETE (last pt dosed Mar 2026), topline confirmed Q3 2026 (Amylyx/BioSpace 6/2026; Goldman 6/10/26). Dossier milestone 2026-09-30 is the conservative end of Q3 (~109d). If using options, buy >=1 monthly PAST end-Q3, i.e. Oct or Nov 2026 expiry, since Q3 readout could land anytime Jul-Sep; do NOT use a Sep expiry.
- **4 · Driver tag:** FDA_clinical_readout — CONFIRMED (avexitide LUCIDITY PBH Phase 3 topline). CLUSTER FLAG: shares the identical FDA_clinical_readout driver with DFTX and EYPT in this batch (3 of 5) — Director should enforce single-driver concentration cap.
- ⚠ **Condition:** Equity entry limit <= $14.75 (do not chase further above Fri close; >half dossier payoff requires a contained entry)
- ⚠ **Condition:** If expressing via options, use Oct-2026 or later expiry (clears Q3 readout +1 monthly); only if a near-$28 call shows OI > ~100 and ask-bid spread < ~20% of mid
- ⚠ **Condition:** Prefer equity unless the chosen call's spread/OI passes the above; binary downside to $4 must be position-sized, not naked-call-financed beyond defined premium

---
## 2 · CRO kills this run — NO_TRADE (7)

*Killed on trade grounds only (edge gone / untradeable / window fails) — catalyst reality was settled upstream.*

### DFTX — Definium Therapeutics, Inc.
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live $24.75 (FMP Fri 6/12 close) vs dossier asof $23.02 = +7.5% run-up into the event. This is the killer: dossier edge was already paper-thin — ev_pct 0.0165 (~1.6%), payoff 0.86 (<1.0 = LOSING skew, you risk more than you make), win 0.55. After a +7.5% pre-pay, the residual EV goes negative: upside to FV $36 is now ~+45% vs downside to floor $8 is ~-68%, an even worse-than-dossier asymmetry, and the 0.0165 EV margin is fully consumed by the move. Edge has compressed below half the (already sub-1) dossier R:R.
- **2 · Tradeability:** Tradeability is the ONE thing that's good here: most options-liquid name in the batch — IBKR avg ~1,429 call / 425 put contracts/day, today ~10,700 calls / 2,620 puts; 90d ADV ~$47.7M. BUT annual IV ~152% (IBKR implied_vol_underlying 1.52) means the binary is already richly priced into premium — a Jun/Jul straddle or calls pays full event vol, so the negative-skew dossier payoff gets worse net of premium. Liquid does not mean cheap.
- **3 · Window ↔ expression:** Note ticker is the rebranded MindMed -> Definium Therapeutics (FMP batch-quote still shows old name; CIK 1813814, CEO Barrow, DT120/ex-MM120). Emerge (MDD) Phase 3 FULLY ENROLLED (149 pts), topline late Q2 2026 (per 8-K/MarketBeat) = matches dossier 2026-06-30 (~17d). Jul monthly expiry would clear; window is fine. Window is not the problem — the math is.
- **4 · Driver tag:** FDA_clinical_readout — CONFIRMED (DT120/lysergide Emerge Phase 3 MDD topline, late Q2). CLUSTER FLAG: same FDA_clinical_readout driver as AMLX and EYPT.

### PRX.AS — Prosus N.V. (forced seller of Delivery Hero)
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live EUR 39.295 (FMP Fri 6/12, Amsterdam close) vs dossier asof EUR 40.07: price is -1.9%, near the 52w low (37.365). computed_rr 2.27 to recovery target 46.21 / floor 37.365. But this is a holdco NAV-discount 'recovery,' not a perishable event spread — there is no dated catalyst to re-price it. The dossier's own instrument note concedes 'the re-rate is on the underlying (DHER), already fired.' No live event edge to verify.
- **2 · Tradeability:** Underlying is hyper-liquid (EUR 85.8B mkt cap, ADV in millions of shares) so tradeability is trivially fine — but that is not the issue. There is no event expression to put on.
- **3 · Window ↔ expression:** dated_milestone = null, days_to_milestone = null, staging = true (WATCH). No catalyst date to clear; the holdco discount is perennial/structural, not a dated milestone. Fails the window<->expression test by construction — nothing to straddle.
- **4 · Driver tag:** Forced_divest_flow — driver is DISTINCT from the FDA cluster, but the flow (Delivery Hero/DHER divestment re-rate) has already fired per the dossier. No forward-dated forced-seller event remains to trade.

### RARE — Ultragenyx (UX111 PDUFA — FDA cleared the data)
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** FMP live last 24.35 (prev close 23.98, +1.5%), up from dossier entry 21.59 (+12.8%) as of 2026-06-13. Recomputed R:R: upside to target 30 = +23.2% (was +39.0%), downside to floor 18 = -26.1% (was -16.6%). Reward:risk has FLIPPED from a favorable ~2.34:1 to an UNFAVORABLE ~0.89:1 — the stock ran into the thesis and now risks more than it can make to the stated levels. Edge has compressed well below half the dossier R:R. That alone is a NO_TRADE on surface 1.
- **2 · Tradeability:** Equity itself is liquid (~$43.4M ADV). But the options tape is flashing risk: today 3,009 puts vs only 97 calls (avg 472c/202p) — heavy put-buying consistent with the active Kuehn-Law securities investigation over setrusumab fracture-data disclosure. IV ~59%. The expression is tradeable but the market is positioning defensively, not for the upside the dossier needs.
- **3 · Window ↔ expression:** The dossier itself flags the swing as a 'manufacturing-facility re-inspection (NOT yet passed)' for the UX111 PDUFA — undated, and re-inspection timing is FDA-gated and historically slip-prone. No dated_milestone / days_to_milestone in the record and none confirmed in 2026-04..06 news flow. An undated, not-yet-passed re-inspection is exactly the 'catalyst too slow / unconfirmed timing' case the window check is meant to catch.
- **4 · Driver tag:** FDA_approval_decision — confirmed. SAME-DRIVER-TAG COLLISION FLAG: shares the 'FDA_approval_decision' tag with BBIO in this batch (Director cap applies). Underlying events differ (UX111 manufacturing re-inspection vs BBIO BBP-418 LGMD2I PDUFA), so not truly correlated, but the tag collides — flag for the cap.

### DBVT — DBV Technologies S.A.
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live $17.42 (FMP quote, NASDAQ ADR, 2026-06-12 close) vs dossier valuation_asof $16.00 — +8.8%. Edge largely intact on paper: upside to FV $34 = +95%, downside to floor $9.50 = -45%, R:R ~2.1 vs dossier payoff 2.77 (~76% retained). The thesis is NOT killed on edge — it is killed on tradeability.
- **2 · Tradeability:** DISQUALIFYING: IBKR search returns only STK and CFD sections for DBVT — NO listed US OPT chain (it is a sponsored ADR of a French Euronext issuer). The dossier itself flagged 'options likely illiquid'; the broker confirms there is effectively no options expression at all. Equity is an ADR with thin liquidity (~0.25-1.0M ADV, ~$417M cap, wide quotes). A binary biotech with -45% downside and NO options to cap risk and NO liquid equity to size into is not a clean trade.
- **3 · Window ↔ expression:** Soft/undated. Catalyst is a rolling Phase 3 VITESSE readout (positive subgroup data already printing June 2026) plus THRIVE Phase 2 which only just screened its first participant (2026-06-02). No single hard binary date; no option expiry to clear even if a chain existed. The forward event most likely to move it (BLA/regulatory path on VITESSE) is undated and could slip.
- **4 · Driver tag:** FDA_clinical_readout — confirmed. SAME-DRIVER CLUSTER FLAG: shares FDA_clinical_readout with RLMD, AVIR, GLUE. Of the four FDA names this is the weakest expression, so it is the natural one to drop for cluster-cap purposes. Indication (peanut-allergy immunotherapy) is idiosyncratic.

### VIR — Vir Biotechnology, Inc.
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live VIR $8.61 (FMP regular-session quote, ts 2026-06-13; range 8.52-8.86, prev close 8.52) vs dossier live_price $8.45 — +1.9%, edge essentially unchanged and still wide on paper (~+132% to FV $20 vs ~-36% to floor $5.5). Edge is NOT the disqualifier here; the window is.
- **2 · Tradeability:** Equity liquid enough (90d ADV ~$15M, 1.1M sh today). Options thin: IBKR avg ~180 contracts/day (167 calls / 13 puts), annual IV ~67% — the dossier's 'long call into the readout' would be a thin, high-IV, theta-heavy bet with little OI to clear at the strikes needed for a $20 target.
- **3 · Window ↔ expression:** DECISIVE: dossier frames a 'Q4-2026 readout' but the actual binary is later and slipped — ECLIPSE 1 reaches primary endpoint Q4-2026 with TOPLINE DATA Q1-2027, and ECLIPSE 2/3 topline also Q1-2027 (Vir guidance). That is ~7-9 months out and undated within the quarter. To clear it with the mandated +1 monthly margin a call needs Mar/Apr-2027+ expiries on a ~180-contract/day chain — long-dated, illiquid, IV-bleed. staging:true / dated_milestone:null confirms there is no hard date to size an expiry around. A correct thesis on an instrument too slow/thin for its option = the loss-with-correct-thesis case the mandate forbids paying for.
- **4 · Driver tag:** Confirmed FDA_clinical_readout — chronic hepatitis delta ECLIPSE Phase 3 (tobevibart + elebsiran) registrational topline, Q1-2027. SAME-DRIVER CLUSTER FLAG: shares FDA_clinical_readout / FDA-biotech super_cluster with PVLA and NKTR in this batch.

### DJT — Trump Media & Technology Group Corp.
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live DJT $7.80 (FMP regular-session quote, ts 2026-06-13; range 7.80-8.26, prev close 8.25, DOWN -5.4% on the day) vs dossier live_price $8.15. Edge was already razor-thin (dossier ev_pct 0.6%, payoff 1.54x) and the underpinning catalyst has been removed, so the recomputed edge is effectively gone/negative.
- **2 · Tradeability:** Equity is liquid (3.76M sh today, ~$2.16B mkt cap) and options exist, so tradeability is not the binding issue — the driver is.
- **3 · Window ↔ expression:** staging:true, dated_milestone:null. No spin date to clear, and now no spin at all. Remaining corporate event is a TAE reverse merger guided to Q4-2026 'or sooner' — a different, undated, dilution-laden situation that the dossier did not underwrite.
- **4 · Driver tag:** DRIVER INVALIDATED: resolution_driver 'Spin_index_flow' (spinoff -> index flow) NO LONGER EXISTS. On 2026-06-10 Trump Media & TAE Technologies announced they will NOT spin off Truth Social / TMTG media assets into a new listed company (Reuters, Forbes, GlobeNewswire 2026-06-10); they are instead completing the TAE fusion reverse-merger (Q4-2026 target). The settled-upstream catalyst that this name was flagged on is dead, the spin-index-flow payoff cannot occur, and the stock is selling off on the news. This is a clean NO_TRADE on driver collapse, independent of any value view.

### NKTR — Nektar Therapeutics
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live NKTR $59.38 (FMP regular-session quote, ts 2026-06-13; range 58.88-60.75, prev close 59.21) vs dossier live_price $56.62 — +4.9% ABOVE the dossier mark. Paper R:R from here is still wide (~+136% to FV $140 vs ~-63% to floor $22), so headline edge is intact, but the dossier's own instrument note concedes 'no near-term event to size around' — the perishable-edge test cannot anchor to a dated catalyst.
- **2 · Tradeability:** Most liquid name of the group: equity 90d ADV ~$59M; options avg ~2,150 contracts/day (1,475 calls / 672 puts), annual IV ~70%. So an expression CAN be built cheaply relative to the others — tradeability is not the blocker; the absence of a window is.
- **3 · Window ↔ expression:** DECISIVE: staging:true, dated_milestone:null, and the dossier itself states 'no near-term event to size around' — REZPEG Phase 3 atopic-dermatitis durability data is a Q4-2026+ / 2027 story with no hard date. There is no catalyst date for any expiry to clear with the mandated +1-monthly margin, so the window<->expression test fails by construction. A long-dated call here is paying ~70% IV theta against an undated readout; that is the 'real catalyst too slow for its option' loss-with-correct-thesis the mandate forbids.
- **4 · Driver tag:** Confirmed FDA_clinical_readout — REZPEG (rezpegaldesleukin) Treg therapy, Phase 3 atopic dermatitis/alopecia durability. SAME-DRIVER CLUSTER FLAG: third name in this batch on FDA_clinical_readout / FDA-biotech super_cluster (with PVLA and VIR) — Director should enforce the cluster cap; if forced to choose within the drug-readout cluster, NKTR is the weakest because it has no datable window at all.

---
## 3 · Non-selections (29) — recorded counterfactuals

*CRO survivors the Director passed on, plus stamp-time exclusions; recorded for selection-calibration.*

| Symbol | Lane | Driver | Edge | Passed because |
|---|---|---|---|---|
| **AMLX** | bio_convergence | FDA_clinical_readout | M | FDA_clinical_readout driver cap (2) taken by CELC (score 8, H-grade TRADE) and EYPT (highest EV in pool). AMLX is the weaker holder of the seat: M-grade, EV already 12% compressed, a soft quarter-end date, and a thin chain whose conditions (Nov+ expiry, OI>=300, spread<=12%) degrade the only acceptable defined-risk expression — full-size equity is explicitly barred on a -70% floor. |
| **ZYME** | bio_convergence | FDA_approval_decision | M | FDA_approval_decision driver cap (2) taken by VRDN and AQST. Thinnest EV in the batch (23.5%) on a low-payoff/high-prob binary with little room for entry slippage — worst EV-per-premium of the dated binaries. |
| **BBIO** | bio_convergence | FDA_approval_decision | H | FDA_approval_decision driver cap — lost the second seat to AQST (EV 69.8% vs ~45%) with VRDN holding the first (p=0.9, 20-day hard date). Also rule-conflicted: staging=true forces equity-only under the basket rules while the CRO's preferred expression is Jan-2027 calls. Strong name; first alternate if an approval seat opens. |
| **VIR** | bio_convergence | FDA_clinical_readout | H | Closest cut in the basket. FDA_clinical_readout driver cap — best live staging edge (+63.4% EV, fully intact) but lost the two seats to CELC (dated 37d, score 8, TRADE) and EYPT (EV +116%, dated); VIR's Q4-2026 readout is soft/undated. First alternate if a readout seat opens. |
| **RARE** | bio_convergence | FDA_approval_decision | H | FDA_approval_decision driver cap. Live EV down to 16.9% after the conference pop (vs AQST 69.8% / VRDN ~105%), score 4, and the catalyst path has already slipped once onto a facility re-inspection gate. |
| **MGNI** | forced_seller | Forced_divest_flow | M | Edge >90% compressed: +8% unexplained move leaves binary EV at ~0.7% at market vs 8% dossier — below the half-R:R kill line per the CRO's own check. Trade only exists on a pullback to <=$15.19 that cannot be assumed at record time. Passing MGNI also resolves the CRO's Forced_divest_flow dupe adjudication in favor of BLCO. |
| **ANNX** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver cap, and the lowest EV of the readout candidates (21.8%) on an H2-2026 placeholder date (12/31) with a chain that traded 8 contracts today — the option expression the dossier leaned on is a verified window flaw. |
| **OLMA** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver cap. The +4.9% pop compressed R:R from 4.06 to 3.43 on an undated fall-2026 readout; behind CELC/EYPT/VIR in the same-driver queue on both edge and dating. |
| **RLMD** | bio_convergence | FDA_clinical_readout | H | Most degraded live entry in the batch: +9.6% pop took R:R from 2.38 to ~1.71, valid only at/below $5.72 per the CRO limit. Ph3 only initiating mid-2026 (year-end readout, high slip risk) and no put market exists to cap the binary. Driver cap full regardless. |
| **CLVT** | forced_seller | Forced_divest_flow | H | Forced_divest_flow driver cap (2) taken by FIG (most executable, R:R 3.85) and BLCO (H-grade, clearer disposition path). CLVT's 40% floor distance caps it at ~3.7% weight anyway, and the binary deal-materialization thesis is the most speculative of the flow trades. |
| **DBVT** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver cap, plus a hard practical ceiling: no options exist on the ADR and the CRO caps equity at ~$350-400K notional working across sessions — too small to carry a meaningful sleeve weight even on paper parity. Edge intact; liquidity, not edge, is the disqualifier. |
| **GLUE** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver cap. EV 35.8% sits below VIR and PVLA among same-driver staging peers; undated soft H2-2026 window and a near-dead chain (4 calls/day) leave nothing the seats don't already cover better. |
| **PVLA** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver cap. Solid edge (EV 60.5%) but undated H1-2027 window, and the CRO flagged an unexplained 562-put anomaly (vs 109/day avg) that must be cleared before entry — an open condition I cannot verify at record time. |
| **CERS** | bio_convergence | FDA_approval_decision | H | FDA_approval_decision driver cap. Score 4, fully undated (no FDA decision visible in recent flow), with proxy-fight and refi noise around the story; EV 37.5% is well below both chosen approval seats. |
| **NKTR** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver cap. No near-term event to size around (REZPEG durability ~Q4-2026) and a 60.9% floor distance caps weight at ~2.5% — minimal contribution even if a seat were open; CERS/NKTR cluster pairing concern is mooted by passing both. |
| **EYPT** | bio_convergence | FDA_clinical_readout | H | EXCLUDED AT STAMP: blocking CRO condition failed/unverifiable at stamp time (= order time): required chosen-strike OI > 500 on the Oct-16 12.5/35 calls; the read-only feed has no per-strike chain endpoint and the whole EYPT chain averages 42 calls/day (148 traded 6/10, IBKR) — an OI>500 strike cannot be evidenced. PVLA standard applied (same class of unverifiable condition, same treatment); the equity fallback is barred by the binaries-defined-risk hard cap (non-staging binary_prob). |
| **EYPT** | bio_convergence | FDA_clinical_readout | H | Highest edge in the batch (ev 1.1572, grade H) but the single FDA_clinical_readout slot is finite and EYPT fails the binary expression gate: options are explicitly untradeable at acceptable cost (avg ~62 calls/day, today 33/0, near-zero OI at $37.5 FV), leaving only equity — which is NOT a defined-risk structure for a binary and would carry undefined ~-58% drawdown to the $5.5 floor. Cannot build the mandated defined-risk leg, so the seat goes to the one dated binary (AMLX) where defined-risk is constructible. |
| **AMLX_note** | None | None | None | SELECTED — listed in picks, not a non-selection. |
| **ANNX** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout slot already taken by AMLX (driver at cap 2 after held CELC + AMLX). Also staging=true (equity-only, half-weight) on an undated Q4 binary with ~80% IV and dead options (today 12 calls/0) — a weaker, undated, equity-only fit than the dated AMLX even before the cap bound. |
| **OLMA** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver at cap after AMLX. Staging=true, undated 'fall 2026' OPERA-01 readout, options too thin (~88% IV, today 7 calls/46 puts) — equity-only undated name, outranked by the dated AMLX for the lone slot. |
| **RLMD** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver at cap after AMLX. Also weakest of the staging set on a live basis: catalyst is a trial START not a readout (no resolution clock), and the +16% run-up already compressed edge ~45% (R:R ~1.38, just above the half-R:R line). Undated, equity-only — does not displace the dated AMLX. |
| **AVIR** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver at cap after AMLX. Decent live edge (ev 0.572, mid-2026 C-BEYOND HCV readout) but lowest score in the pool (5), micro-cap ($359M) with rich-IV/moderate-OI options needing live verification, and would still be the 2nd same-driver name — the cap permits only one, and AMLX's cleaner dated-option fit takes it. |
| **GLUE** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver at cap after AMLX. Staging=true, undated H2-2026 GFORCE-1 readout, dossier itself notes 'no liquid catalyst-dated options chain confirmed'; edge ~30% compressed. Equity-only undated name, outranked for the single slot. |
| **PVLA** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver at cap after AMLX. Staging=true and the near-term event is an NDA SUBMISSION (2H2026), not a value-resolving approval (H1-2027+); listed options are effectively dead (avg ~240 contracts, ~0 usable OI). Undated, equity-only multi-quarter hold — does not displace the dated AMLX. |
| **ZYME** | bio_convergence | FDA_approval_decision | M | FDA_approval_decision driver is FULL — held book already uses 2 of 2 (AQST + VRDN). Cannot add regardless of its clean live edge (entry came in -4.4%, ~2.1:1 asymmetry). |
| **BBIO** | bio_convergence | FDA_approval_decision | H | FDA_approval_decision driver is FULL (held AQST + VRDN = 2/2). Strong dated PDUFA (2026-11-27, grade H, best tradeability) but the combined per-driver cap blocks any new approval-decision seat. |
| **CERS** | bio_convergence | FDA_approval_decision | H | FDA_approval_decision driver is FULL (held AQST + VRDN = 2/2). Micro-cap with non-functional options; blocked by the per-driver cap independent of merit. |
| **MGNI** | forced_seller | Forced_divest_flow | M | Forced_divest_flow driver is FULL — held book already uses 2 of 2 (FIG + BLCO). Staging/undated (no dated milestone) with ~22% edge compression after the run-up; blocked by the per-driver cap regardless. |
| **CLVT** | forced_seller | Forced_divest_flow | H | Forced_divest_flow driver is FULL (held FIG + BLCO = 2/2). Cheap, high-R:R deep-value optionality (R:R ~5.0) but no dated catalyst and the combined per-driver cap blocks any new forced-seller seat. |

---
## 4 · Latest Director memo (verbatim)

Headroom was the whole story. The locked held book already maxes FDA_approval_decision (AQST+VRDN) and Forced_divest_flow (FIG+BLCO) at 2/2 each, which kills 5 survivors outright (ZYME, BBIO, CERS, MGNI, CLVT). Of the remaining 8, ALL share the single open driver FDA_clinical_readout (held CELC leaves exactly 1 slot), so at most ONE new seat is addable — the per-driver cap, not edge or cluster weight (FDA/biotech had 28.5 pts free), is binding. Within that pool I took AMLX over the higher-edge EYPT because the mandate forces binaries into a DEFINED-RISK structure: EYPT's (and most of the pool's) options are untradeable, leaving only naked equity exposure to the floor — which fails the gate. AMLX is the one hard-dated (Q3-2026, 109d), non-staging binary where a defined_risk_option clearing the milestone by +1 monthly (Oct/Nov-2026) is actually constructible, sized at the 2% premium-at-risk cap off ev_pct 0.4512. Result: 1 new seat (10/12 total), FDA/biotech cluster 11.5→13.5 of 40, FDA_clinical_readout now 2/2. Shape stays a small, defined-risk biotech-binary tail-add on top of a held book that already carries the deal-completion and idiosyncratic weight — no cluster concentration, no cap breach, no forced seat.

---
*Caps at last stamp: 0 violations · 1 added · 0 pending · 0 excluded-at-stamp. Auto-generated by backend/_basket13_review.py.*
