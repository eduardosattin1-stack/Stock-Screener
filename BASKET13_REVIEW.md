# Basket 13 — Catalyst Sleeve · Agent Comments for Review

*Generated 2026-07-20 · 14 held seats (72.0% invested) + 3 resolved · last run 2026-07-20 · paper basket, nothing executed*

Pipeline: enriched board → entry/staging filter → **Catalyst-CRO** (attacks ONLY the trade — live edge / tradeability / window↔expression / driver tag; catalyst reality settled upstream by the scan→deep→skeptic tier; value/quality attacks forbidden) → **Director** (selection + sizing under HARD caps: ≤2/driver, ≤40 NAV weight-points/super-cluster, 8–12 names, risk-to-floor ≤1.5% NAV, binaries defined-risk ≤2%, staging equity-only half-weight; held seats run to resolution and consume combined-cap headroom) → deterministic cap validator → tracker stamps at CRO-verified live prices.

---
## 1 · The basket (14 held)

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

### FIG — 
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

### CELC — 
`1.5% · debit spread exp 2026-09-18 · bio_convergence · FDA_clinical_readout (FDA/biotech) · score 8.0 · edge H · entry 2026-06-10 @ 92.59 (cro_live_check)`
- **Expected:** EV 50.1% · milestone 2026-07-17 · review: 2026-07-17 clinical readout.
- **Director — why this seat:** Highest-score H-grade unconditional TRADE in the batch: p=0.85 to $153 on the 7/17 readout, live EV +50% after the pop. The Sep-18 95/155 call spread defines risk and sells back the ~80% event IV the CRO flagged on outright calls, clearing the milestone with +1 monthly margin; premium sized at 1.5% because its EV is roughly half EYPT/VRDN's.
- **Director — what kills it:** Primary-endpoint miss on the 7/17 readout — spread premium is the full and only loss.

**CRO verdict: TRADE**
- **1 · Edge at entry (live re-check):** Live $92.59 (FMP batch-quote 2026-06-10, +5.9% on the day; IBKR real-time last $92.70) vs dossier $87.43. Recomputed: upside to $153 = +65.2%, downside to $60 = -35.2%, payoff 1.85 (dossier 2.39), EV = 0.85*0.652 - 0.15*0.352 = +50.1% (dossier +59.0%). ~15% EV compression after today's pop — still far above the half-R:R kill line. Edge intact.
- **2 · Tradeability:** Equity expression, and it is the most liquid name in the batch: $110M/day 90d USD ADV (IBKR), 1.37M shares today. Any realistic sleeve position is a rounding error vs ADV. Options are active (avg ~2,337 calls / 1,177 puts daily) but annual IV ~80% — dossier's own note that July/Aug calls carry rich event IV is confirmed; equity is the right expression.
- **3 · Window ↔ expression:** Milestone 2026-07-17, 37 days out. Equity has no expiry — window clears by construction. No slippage history concern for the expression.
- **4 · Driver tag:** FDA_clinical_readout — confirmed. FLAG: same driver as AMLX and DFTX (three names, one driver) — Director cap applies; this is the strongest of the three on edge grade (H) and tradeability.

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

### AAUC — Allied Gold Corporation
`7% · equity · merger_arb · Foreign_regulator (Deal-completion) · score 7.0 · edge M · entry 2026-06-30 @ 23.4 (cro_structured)`
- **Expected:** R:R 20.35:1 · milestone 2026-07-29 · review: July 29 2026 outside date for deal close / host-country approval (29d); a second mutual extension stretches the timeline rather than breaking the deal.
- **Risk-to-floor (computed):** 0.12% of NAV (cap 1.5)
- **Director — why this seat:** Clean cash-merger arb at ~US$23.40 vs C$44.00 (~US$30.98 at live FX) = +32% gross spread on the only non-bio, non-FDA driver available (Foreign_regulator, brand-new to the basket), resolving on host-country regulatory approval rather than the tape. Sized moderate, not hero, because the downside floor cushion is ~zero (pure deal-break risk) and ADV is thin at ~$3.8M/day.
- **Director — what kills it:** Deal breaks (financing/regulatory failure) or a definitive termination — price collapses toward standalone gold-tape value below the ~$23 floor with no cushion.

**CRO verdict: TRADE_WITH_CONDITIONS**
- **1 · Edge at entry (live re-check):** Live US$23.40 (FMP batch-quote, 2026-06-29 close, NYSE). Cash payout recomputed at live FX: C$44.00 x 0.70399 (USDCAD 1.42065) = US$30.98 (dossier's $31.54 used a weaker CAD). Spread to cash = +32.4% (~$7.58 up) vs floor ~$23 = -1.7% (~$0.40 down). Spread is WIDE and intact (wider than the dossier's ~$25.26 entry); but the downside floor cushion is now essentially zero - this is pure deal-break risk, not a cushioned arb.
- **2 · Tradeability:** Equity only. Liquidity is the constraint: ADV ~163K sh x $23.4 ~ $3.8M/day on the NYSE line (float 93M sh) - thin. A sizable position would be a large share of ADV; build with limit orders. Listed options not a sensible expression for a 32% cash-deal spread.
- **3 · Window ↔ expression:** Equity, not options - July 29 2026 outside date is 29 days out. Date HAS slipped once already (May 29 -> July 29); a second mutual extension is possible if a host-country approval lags (stretches timeline / compresses annualized return, does not break deal). Hold expectation must tolerate a slip past July 29.
- **4 · Driver tag:** Foreign_regulator (Zijin Gold C$44 cash arrangement; remaining Mali/Cote d'Ivoire/Ethiopia/Egypt host-country sign-offs) - confirmed. ICA (hardest gate) cleared May 29; both parties reaffirmed July 29 2026 outside date in the June 10 update. No duplicate driver in batch.
- ⚠ **Condition:** Express in equity via limit orders near/below $23.40 given thin ~$3.8M/day ADV; do not chase
- ⚠ **Condition:** Accept near-zero downside cushion (floor -1.7%) - this is deal-break/gold-tape risk, size accordingly
- ⚠ **Condition:** Tolerate a possible second extension past the July 29 2026 outside date (one slip already occurred)

### FUN — Six Flags Entertainment (Jana sale push)
`4% · equity · activist · Activist_process (Idiosyncratic) · score 5.0 · edge H · STAGING · entry 2026-06-30 @ 20.56 (cro_structured)`
- **Expected:** R:R 2.57:1 · milestone 2027-03-31 · review: 2027-03-31 process milestone (274d); interim — any board strategic-review update or formal sale-process announcement.
- **Risk-to-floor (computed):** 0.79% of NAV (cap 1.5)
- **Director — why this seat:** High-grade activist/sale-process bet (Jana) at $20.56 with +50.8% to FV $31 vs -19.7% to the $16.50 floor (R:R 2.57), a brand-new Activist_process driver in Idiosyncratic that diversifies away from the FDA-heavy held book. Staging=true (undated process) forces equity-only at half a normal weight; entry is if anything cheaper than dossier asof after today's -6.6%.
- **Director — what kills it:** Jana stands down / board rejects a sale and reaffirms standalone, or a leveraged-balance-sheet stress event re-rates the equity toward/through the $16.50 floor.

**CRO verdict: TRADE**
- **1 · Edge at entry (live re-check):** Live $20.56 (FMP batch-quote, 2026-06-30) == dossier live_price $20.56; edge fully intact. R:R from $20.56: upside to FV $31 = +$10.44 (+50.8%), downside to floor $16.50 = -$4.06 (-19.7%), R:R = 2.57x, matching dossier computed_rr 2.57. No compression. Note stock -6.6% today and below 50d avg ($20.74), so entry is if anything cheaper than dossier asof.
- **2 · Tradeability:** Equity is the correct expression and is highly tradeable: ADV ~3.3M sh x $20.56 = ~$66M/day, ample for any realistic sleeve position, no borrow leg. Options route is NOT viable: Jan-2027 $25 call shows OI 169 / 2 contracts today / no live two-sided bid-ask; $20 call OI 1,623 but zero volume and empty bid-ask. Thin, no usable quotes near thesis strikes.
- **3 · Window ↔ expression:** Milestone 2027-03-31 (274d). Option expiries run monthly only through Jan-2027 then jump straight to Jan-2028 LEAP — there is NO expiry between Jan-2027 and Jan-2028, so no contract clears 2027-03-31 with the required +1-monthly margin except the illiquid Jan-2028 LEAP. Window does not fit options; staging=true soft activist process confirms equity. No date to slip (undated process), so equity carries no theta-decay risk.
- **4 · Driver tag:** Activist_process (Jana sale push) confirmed; no new activist/sale headline in feed (recent news all operational), but process is the driver and reality is settled upstream. Idiosyncratic, no same-driver twin in this batch.

### ZYME — Zymeworks Inc.
`2% · debit spread exp 2026-10-16 · merger_arb · FDA_approval_decision (Deal-completion) · score 7.0 · edge M · entry 2026-07-02 @ 26.31 (cro_structured)`
- **Expected:** EV 12.4% · milestone 2026-08-25 · review: FDA PDUFA target action date 2026-08-25.
- **Director — why this seat:** Fresh verdict-A/conviction-5 debate on a hard, binding 2026-08-25 PDUFA (RTOR, Priority Review, Breakthrough) with the $250M Jazz milestone still unpaid; live EV +12.4% with only mild compression. Binary_prob name, so defined-risk only: a 26/31 call debit spread capped at 2% NAV premium-at-risk, on the Oct-16 monthly to clear the PDUFA by a full monthly cycle and absorb the extension tail the Sep line would not.
- **Director — what kills it:** CRL or a 3-month PDUFA extension pushing action past the Oct-16 expiry (skeptic flags a real RTOR-pushback/AdCom tail), or the Jazz milestone terms being disputed.

**CRO verdict: TRADE**
- **1 · Edge at entry (live re-check):** FMP real-time quote 2026-07-02: $26.31 (dossier $25.91, asof 06-08). Recomputed binary EV = 0.88x$31 + 0.12x$19 = $29.56 -> +12.4% vs dossier +14.1%; payoff ratio 0.64 vs 0.74. Mild compression only, far above the half-R:R kill threshold. Edge intact.
- **2 · Tradeability:** Equity expression, NASDAQ, ~531k shares/day = ~$14M dollar ADV; a paper-sleeve position is a rounding error of daily volume. No options leg needed and none desired given the skeptic's note that the $19 floor leans on a Royalty Pharma-encumbered royalty stream (soft-ish floor argues for equity, not short puts).
- **3 · Window ↔ expression:** PDUFA 2026-08-25 is 54 days out; instrument is equity so no expiry to clear. Weekly diagnosis is FRESH (3.4d): catalyst PENDING_HARD, skeptic CONFIRMED_WITH_CORRECTIONS (not fired, $250M Jazz milestone unpaid), conviction cap 60. RTOR review reduces slip risk but a 3-month extension tail exists — irrelevant for equity.
- **4 · Driver tag:** CORRECTED: Deal_close_generic is wrong — the resolving event is the FDA PDUFA action (which contractually triggers the $250M Jazz milestone), so the true driver is FDA_approval_decision. FLAG: this collides with GERN's FDA_approval_decision driver in this same batch — Director must apply the same-driver cap across ZYME/GERN.

### DDL — 
`3% · equity · distressed · Refi_restructuring (Idiosyncratic) · score 7.0 · edge M · entry 2026-07-02 @ 1.94 (cro_structured)`
- **Expected:** R:R 18.69:1 · milestone 2026-12-31 · review: The refi print itself (event-driven, undated); formal re-check at the 2026-12-31 placeholder milestone or any capital-structure 8-K/6-K.
- **Risk-to-floor (computed):** 0.062% of NAV (cap 1.5)
- **Director — why this seat:** Capital-return/refi name where the $1.90 floor sits ~2% below live — an 18.7 R:R by construction, so risk-to-floor is only 0.10% NAV even at 3%. Weight deliberately held below what the floor allows because the ~$0.5M/day ADV is the binding constraint; entry recorded at limit <= $1.97 per CRO conditions.
- **Director — what kills it:** A refi/restructuring executed on terms that impair the ADS (dilution or subordination), a break and hold below the $1.90 floor, or no refi print materializing by the year-end placeholder.

**CRO verdict: TRADE_WITH_CONDITIONS**
- **1 · Edge at entry (live re-check):** Live $1.94 (FMP quote, 2026-07-02) vs dossier valuation_asof $1.965 — -1%, capital-return R:R intact: FV target $3.18 (~+64%) vs floor $1.90 (~-2% below live). computed_rr 18.69 preserved; downside is thin by construction. No compression.
- **2 · Tradeability:** LIQUIDITY IS THE CONSTRAINT: NYSE ADS trades only ~265k sh/day x ~$1.94 = ~$0.5M ADV. A realistic sleeve position must be a small fraction of that and worked with limits — market orders will move the tape. No short leg / no borrow needed (long).
- **3 · Window ↔ expression:** Refi/restructuring is undated/soft (dated_milestone 2026-12-31 placeholder, ~182d) — equity hold, no option window to clear. Resolution is event-driven, not calendar-hard; monitor for the refi print.
- **4 · Driver tag:** Refi_restructuring — CONFIRMED. Unique driver in this batch (no cap conflict).
- ⚠ **Condition:** Cap position to a small fraction of the ~$0.5M/day ADV; accumulate with limit orders, do not use market orders.
- ⚠ **Condition:** Limit entry <= ~$1.97 (floor $1.90 leaves only ~2% downside cushion — entering above ~$2.00 erodes the asymmetry).

### LBTYK — Liberty Global plc
`2.5% · equity · spinoff · Spin_index_flow (Idiosyncratic) · score 7.0 · edge M · STAGING · entry 2026-07-02 @ 10.9 (cro_structured)`
- **Expected:** R:R 5.07:1 · milestone 2027-06-30 · review: VodafoneZiggo 50% buy-in close, targeted July 2026 — the near-term confirming step and the add-tranche trigger.
- **Risk-to-floor (computed):** 0.321% of NAV (cap 1.5)
- **Director — why this seat:** SoP special-sit with the R:R having WIDENED to ~5.1 at live $10.90, a fresh verdict-A debate, and a committed Ziggo listing/spin path — but the skeptic is right that the $9.50 floor is a holdco-discount construct, so this enters at staging size (half a normal seat) per the CRO's stage-in condition and the conviction cap of 60. Second tranche only after the VodafoneZiggo 50% buy-in actually closes.
- **Director — what kills it:** VodafoneZiggo buy-in failing regulatory approval, or management walking back the committed H2-2027 Ziggo Euronext listing/spin — without the forcing function this reverts to a chronic holdco discount.

**CRO verdict: TRADE_WITH_CONDITIONS**
- **1 · Edge at entry (live re-check):** FMP real-time quote 2026-07-02: $10.90 (dossier $10.99). Recomputed SoP R:R = ($18.00-$10.90)/($10.90-$9.50) = 7.10/1.40 = 5.07 vs dossier 4.70 — the edge has WIDENED slightly. No compression issue.
- **2 · Tradeability:** LBTYK common, ~734k shares/day (~$8M notional) — fine for the sleeve. Equity is the right expression: no listed option chain reaches the H2-2027 spin with acceptable liquidity, and the fresh skeptic confirms the $9.50 floor is a holdco-discount SoP construct, NOT a hard cash backstop — so defined-risk option structures would be built on a fictional floor anyway.
- **3 · Window ↔ expression:** Milestone 2027-06-30 is ~363 days out; equity clears any window by construction. Fresh weekly diagnosis (3.4d): PENDING_HARD, verdict A, skeptic CONFIRMED_WITH_CORRECTIONS with conviction cap 60 — catalyst live and NOT fired, but it is a voluntary self-restructuring with slip risk (regulatory close July/H2 2026, listing H2 2027) and no mechanical forcing function if the holdco discount persists.
- **4 · Driver tag:** Spin_index_flow confirmed (Ziggo Euronext listing + 90% spin creates the index/flow event). FLAG: MSGS in this same batch carries the identical Spin_index_flow driver — second name on one driver; Director cap applies (moot if MSGS stays NO_TRADE, but flagging per protocol).
- ⚠ **Condition:** Stage-in only: open at no more than half target weight now; add the second tranche only AFTER the VodafoneZiggo 50% buy-in actually closes (targeted July 2026) — that is the near-term confirming step that hardens the 2027 spin
- ⚠ **Condition:** Limit <= $11.00 (do not chase above; the recomputed 5.07 R:R degrades below the dossier's 4.7 above ~$11.05)
- ⚠ **Condition:** Respect the skeptic's conviction cap of 60 in sizing — the $9.50 floor is soft (SoP construct, not a deal-break price), so size to a realistic drawdown through the floor if the discount persists

---
## 1b · Resolved (3)
- **VRDN** FIRED_WIN · 2026-06-10→2026-07-06 (26d) · 16.31→19.42 · realized +19.1% (exp EV 105.0%) · FDA approved Lumvoa (veligrotug) 6/26/26, 4 days ahead of the 6/30 PDUFA; immediate launch. Captured +19.1% of the modeled re-rate; residual to the $35 win-leg is launch-execution, tracked post-resolution.
- **THRM** THESIS_BROKEN · 2026-07-02→2026-07-06 (4d) · 33.88→34.13 · realized +0.7% (exp R:R 2.87:1) · Board dossier misread the RMT: stock-for-stock, THRM is the ACQUIRER, no consideration flows to holders - the 30% spread to $44 never existed. HSR fired 3/26 pre-valuation. Fable dossier + CRO NO_TRADE 7/06.
- **LZM** EDGE_GONE · 2026-07-02→2026-07-06 (4d) · 3.73→3.88 · realized +4.0% (exp R:R 2.93:1) · Mid-2026 FID slipped to late-2026; spot-marked target $4.95 puts entry R:R ~0.95, below the kill line (deck target $7.04 conditional on nickel recovering toward $8.49/lb). Catalyst real but edge gone at tape; RKAB 7/31 + StanChart term-sheet tracked post-resolution.

---
## 2 · CRO kills this run — NO_TRADE (3)

*Killed on trade grounds only (edge gone / untradeable / window fails) — catalyst reality was settled upstream.*

### EYPT — EyePoint Pharmaceuticals, Inc.
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live EYPT 13.35 (bid/ask 13.33/13.39, IBKR SMART; prior close 13.30). WEEKLY DIAGNOSIS OVERRIDE controls: the fresh (age 3.6d) adversarial skeptic verdict is REFUTED. It kills the ONLY reason the file recommends the bet — the 'strictly more favorable Phase 3' odds anchor is false (LUGANO enrolls treatment-naive AND previously-treated eyes; the enabling DAVIO-2 Phase 2 was previously-treated ONLY, so DURAVYU has zero Phase 2 NI evidence in the naive/higher-VEGF-burden segment — exactly where Kodiak's KSI-301 missed NI in DAZZLE), and the bull's single confidence tell is backwards (Q1-26 10-Q Note 8: management DREW ~$5.7M on a live ATM at $14.75 into its own binary). Honest p collapses toward the market-implied ~0.30-0.35, at which the ~+6% EV is noise on an unfloored overnight-gap binary. The catalyst is real and unfired, but the EDGE is refuted. The inject layer hard-rejects a REFUTED name; do not spend a nomination.
- **3 · Window ↔ expression:** Board's 2026-07-31 'hard' date is unsourced/fabricated per the dossier; realistic LUGANO topline is a soft Aug-Oct 2026 window. Moot given the REFUTED verdict.
- **4 · Driver tag:** FDA_clinical_readout — confirmed. NOTE FOR DIRECTOR: shares this driver (and bio_convergence lane / FDA-biotech cluster) with OLMA in this batch; here it is moot since EYPT is NO_TRADE.

### PRX.AS — Prosus N.V. (forced seller of Delivery Hero)
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live PRX.AS EUR39.78 (bid/ask 39.78/39.785, IBKR AEB; prior close 38.505). fresh_dossier catalyst_status = FIRED and the weekly skeptic is REFUTED (both age 3.6d). The forced-seller premise resolved 2026-07-16 when Uber launched its EUR41.50/sh cash offer for Delivery Hero and Prosus gave an irrevocable undertaking to tender its residual ~16.8%. The event is spent AND was never a needle-mover: the incremental NAV contribution above the live DH mark is ~EUR0.07/sh (~0.1% of NAV) on a ~EUR40 stock. What remains is wrong-signed (the irrevocable binds Prosus, not Uber; Uber's H2-2027 close is conditional) and a structural ~39% discount-to-NAV that is ~79% Tencent beta — a value case, not an event. Edge GONE.
- **3 · Window ↔ expression:** The 2026-10-11 EC divestment deadline and Uber's H2-2027 close are risk/compliance dates, not opportunity dates — the load-bearing milestone (irrevocable undertaking) already fired 2026-07-16.
- **4 · Driver tag:** Forced_divest_flow tag retained but MISAPPLIED — the archetype rewards a register absorbing forced supply, whereas Prosus IS the seller (and its own largest buyer). The live merger-arb sits on Delivery Hero's register (DHER.DE vs EUR41.50), not on this ticker.

### DBVT — DBV Technologies S.A.
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live $14.30 (IBKR bid/ask 14.21/14.38, ~$3.7M/day ADV). At defensible axes (floor ~$5, approval-case ~$25) the tape implies (14.30-5)/(25-5)=46.5% odds vs the dossier's ~49% win_prob -- essentially FAIR, no spread. The board's payoff=3.71/ev=+56% was an artifact of the phantom $9.50 floor (~3.2x the verified ~$2.95/ADS net cash). No edge at entry.
- **2 · Tradeability:** IBKR lists STK/CFD only for DBVT -- NO listed equity options, so the instrument note's 'long-dated Q4-26/Q1-27 calls' leg does not exist here. Equity spread ~1.2% on thin ~$3.7M/day ADV. Moot given the kill.
- **3 · Window ↔ expression:** No dated approval milestone exists: no BLA filed -> no acceptance, no PDUFA clock. Nearest gate is a company-controlled BLA filing now guided Q3 2026 (slipped from 1H 2026), then ~60d to acceptance (~Nov-Dec 2026), then ~10mo review => approval decision ~Q3-Q4 2027, >1yr out. Runway only 'into Q3 2027' so a dilutive raise ahead of resolution is near-arithmetic.
- **4 · Driver tag:** FDA_approval_decision (confirmed). Distinct from KDP's Spin_index_flow -- no same-driver cap conflict in this batch.

---
## 3 · Non-selections (45) — recorded counterfactuals

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
| **DFTX** | bio_convergence | FDA_clinical_readout | M | Edge is negligible on merit, independent of headroom: ev_pct 0.0165 (payoff 0.86, barely positive) and live recompute compressed the upside leg further (FV $36 = +45.5% vs floor $8 = -67.7%, a true coin-flip with sub-1x net payoff). Would skip even with a free lane + driver seat. (Also double-capped: bio lane 5/5 and FDA_clinical_readout 2/2.) |
| **RARE** | bio_convergence | FDA_approval_decision | H | Edge collapsed on the +12.8% run to $24.35: R:R flipped from ~2.3:1 to roughly symmetric (~+23% upside / ~-26% downside, ~0.9:1). Entry is chasing here; undated manufacturing re-inspection (staging) with no enforced date. Skip on merit regardless of headroom. (Also double-capped: bio lane 5/5 and FDA_approval_decision 2/2.) |
| **ANNX** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver is 2/2 full (held CELC + AMLX) AND it is a true coin-flip (win_prob 0.45) competing with OLMA/RLMD for the same single hypothetical freed clinical-readout seat; on merit it ranks below VIR/PVLA/AVIR already on the watchlist, so it would be displaced even if the lane freed. Skip rather than on-deck. |
| **OLMA** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver 2/2 full and win_prob only 0.40 (real chance of the floor on a ~4:1 gross payoff); undated/soft single-event binary. Competes with ANNX/RLMD for one seat and ranks below the watchlist clinical names on win-prob-adjusted edge. Skip on merit. |
| **RLMD** | bio_convergence | FDA_clinical_readout | H | FDA_clinical_readout driver 2/2 full; edge eroded most in batch on the +16.3% run (R:R fell ~2.4:1 -> ~1.4:1), needs a limit <= $6.00 to be viable, and option market is unverified on a $6 small-cap. Marginal even on merit; behind the on-deck clinical names. Skip. |
| **CERS** | bio_convergence | FDA_approval_decision | H | Score 4, micro-cap (~$513M), win_prob 0.45 coin-flip; FDA_approval_decision driver 2/2 full. Equity-only, no options edge. Weaker than BBIO/ZYME for any hypothetical freed approval seat. Skip on merit. |
| **NKTR** | bio_convergence | FDA_clinical_readout | H | Score 4, M-grade, win_prob 0.45; dossier itself flags 'no near-term event to size around' (undated Q4-2026 durability play). FDA_clinical_readout driver 2/2 full and it ranks below the watchlist clinical names. Undated theta risk even via liquid options. Skip on merit. |
| **ZYME** | bio_convergence | FDA_approval_decision | M | Skip on merit regardless of headroom: thinnest R:R in the batch (~1.35) and only M grade — shallowest asymmetry — plus an active ZYME.TEN/ZYME.EXC tender/exchange corporate action that muddies the binary. Even if its FDA_approval_decision driver and the bio lane freed, the compressed edge does not earn a seat. |
| **IMCR** | bio_convergence | FDA_clinical_readout | H | Undated open-ended binary (PRISM-MEL-301 Phase 3 with no fixed topline date) and a low 0.40 win-prob; no review milestone to anchor a position. Dateless low-conviction binary in a saturated lane — a merit skip, not just a headroom block. |
| **DBVT** | bio_convergence | FDA_approval_decision | H | Undated AND just-slipped milestone (VIASKIN Peanut BLA not yet filed, now anticipated Q3 2026+, review clock starts only at filing) on a deteriorating timeline, plus a thin ~$8M/day small-cap ADR. A demonstrably lengthening, dateless catalyst is a merit skip irrespective of cap headroom. |
| **ANNX** | bio_convergence | FDA_clinical_readout | M | The FDA_clinical_readout watchlist is already at its 5-name cap with strictly stronger carried claims (EYPT +77% EV, BBIO, VIR, PVLA, AVIR all above it), and ANNX's +13.6% EV at 0.45 win-prob against a -63% floor and a soft placeholder date is the weakest of the cohort — passed on relative merit, not headroom alone. |
| **ALTI** | forced_seller | Forced_divest_flow | M | No quantified edge exists (fair_value_target, downside_floor, and R:R all null; score 5), so it is unsizeable under Kelly-lite even if the full Forced_divest_flow driver opened — and CLVT and MGNI are strictly stronger, quantified claims on that same driver's queue. Re-submit once the deep pass produces a target/floor. |
| **AXTA** | merger_arb | Foreign_regulator | M | Merger-arb whose only real edge is the hedged pair (long AXTA / short 0.6539 AKZO). The fresh dossier debunked the board's $42.64 target to $34.80 (netting AkzoNobel's EUR2.5B pre-completion distribution AXTA holders don't receive), collapsing R:R from a claimed 2.48 to ~0.61 as a naked long, and the CRO confirms this. Basket 13 cannot record the short-AKZO leg, so the expressible position is a sub-1 R:R euro/coatings-beta long into ~30-country antitrust with a possible 2027 slip. Foreign_regulator seat is open, but the edge as expressible fails on merit. |
| **MP** | supply_timing | Supply_timing | H | Hard idiosyncratic catalyst (DoD public-private partnership) already FIRED and closed July 11, 2025; the residual is an undated, long-dated (~2028 10X-campus commissioning) commodity / China-export-policy tape proxy that the CRO itself flags as 'not a Basket-13 idiosyncratic special situation.' EV is intact at the live ~$44.61 tape (+25.9%), but it is macro/tape EV rather than bounded-catalyst edge — wrong kind of edge for an event-driven calibration sleeve despite the open Supply_timing driver and cluster room. |
| **KDP** | spinoff | Spin_index_flow | M | Undated, board-discretionary spin: no Form 10, no record/effective date, already slipped late-2026 to early-2027 (Jun 23 8-K), explicitly gated on 'appropriate leverage levels' AND 'supportive market conditions,' with the hard JDE Peet's leg already fired (no live deal spread). Fresh skeptic verdict CONFIRMED the kill (no forcing function, sub-1:1 R:R on a breakable staples-valuation 'floor,' coffee-unit CEO departing end-July). Spin_index_flow seat is open, but the asymmetry does not survive on merit — a watch item, not a dated special situation. |
| **OLMA** | bio_convergence | FDA_clinical_readout | H | Strong single-date binary (H-grade, EV +18.3% at live $11.41; win $24 / lose $6.50 / p=0.40) but routed to passed by queue discipline, not weakness: FDA_clinical_readout is 2/2 in the held book (CELC + AMLX) and its watchlist queue is already at the 5-name cap with carried on-deck names ahead of it (VIR/EYPT/BBIO/PVLA/AVIR), plus the bio_convergence lane is full. Kept off the queue so one abundant driver cannot monopolize it; first to reconsider if an FDA_clinical_readout/bio slot frees ahead of the carried queue. Staging=true, so equity-only if it ever seats. |

---
## 4 · Latest Director memo (verbatim)

No new seats this run — picks:[]. All four CRO survivors fail either on merit or on combined caps, and forcing a seat would either breach queue/cap discipline or record a sub-threshold edge. AXTA, MP and KDP are merit passes despite having open drivers: AXTA's real edge lives in a short-AKZO leg the basket can't record (naked-long R:R ~0.61 after the target was debunked); MP's hard catalyst fired a year ago leaving an undated ~2028 commodity tape proxy the CRO itself disowns as a Basket-13 fit; KDP is an undated, twice-slipped, discretionary spin the fresh skeptic CONFIRMED as sub-1:1 with no forcing function. OLMA is the only cap/queue casualty — a genuinely strong binary blocked by a 2/2 FDA_clinical_readout driver and a full bio lane, and bumped to passed only because that driver's 5-name watchlist queue is already occupied by carried names. The held book stays 14/20 seats, clusters unchanged (Deal-completion 31 / Idiosyncratic 29.5 / FDA-biotech 11.5), all combined caps intact. The on-deck book carries all 9 prior nominations forward unchanged (5 FDA_clinical_readout, 2 FDA_approval_decision, 2 Forced_divest_flow) — every one still blocked solely by a full held driver, first-in-line the moment CELC/AMLX, AQST/ZYME, or FIG/BLCO resolves and frees its cap.

---
*Caps at last stamp: 0 violations · 0 added · 0 pending · 0 excluded-at-stamp. Auto-generated by backend/_basket13_review.py.*
