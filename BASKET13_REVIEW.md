# Basket 13 — Inaugural Run, Agent Comments for Review

*Run 2026-06-10 · generated 2026-06-11 · 29 candidates debated → 29 CRO verdicts → 25 survivors → 9 seats · paper basket (nothing executed)*

Pipeline: enriched board → entry/staging filter → **Catalyst-CRO** (attacks ONLY the trade: live edge, tradeability, window↔expression, driver tag — catalyst reality settled upstream by the scan→deep→skeptic tier; value/quality attacks forbidden) → **Director** (selection + sizing under hard caps: ≤2/driver, ≤40 NAV weight-points/super-cluster, 8–12 names, risk-to-floor ≤1.5% NAV, binaries defined-risk ≤2%, staging equity-only half-weight) → deterministic cap validator → tracker stamps.

**Stamp policy (2026-06-11 review):** entries stamped at the **CRO-verified live price** (source recorded per stamp), never the dossier reference; CRO entry limits enforced at stamp time — a live price above the limit stamps as a **resting limit, not held** (no fiction fills); hedge legs recorded on the entry; risk-to-floor **computed**, not quoted; driver re-tags logged. Cluster-cap basis pinned: ≤40 weight-points of NAV (the invested-share basis is unstable to exclusions; the memo's stricter invested-share read is reported alongside).

**Driver re-tags this run (logged, cap-relevant):** WVE: FDA_approval_decision → FDA_pathway_feedback (Director (CRO-conditioned))

---
## 1 · The basket (8 held seats, 45.5% invested; +1 resting limit, 8% reserved)

### GDOT — Green Dot Corporation
`14% · equity · merger_arb · Deal_close_generic (Deal-completion) · score 7.0 · edge M · entry 2026-06-10 @ 12.75 (cro_live_check)`
- **Risk-to-floor (computed):** 1.043% of NAV (cap 1.5%)
- **Expected:** R:R 1.56:1 · milestone 2026-09-30 (112d)
- **Director — why this seat:** Cleanest ratio carry in the pool: 11.6% gross spread to the $14.23 deal value over ~112 days (~38% annualized) with zero price drift since the dossier and the tightest floor in the basket (-7.5%). Top weight because the floor distance is smallest — 14% weight risks only ~1.04% NAV to floor.
- **Director — what kills it:** Deal termination or a material regulatory objection; price through the $11.80 floor signals the market pricing a break.
- **Review trigger:** Expected close 2026-09-30; review on close or any delay/regulatory notice before then.

**CRO verdict: TRADE**
- **1 · Edge at entry (live re-check):** Live $12.75 (FMP batch-quote 2026-06-10) — unchanged from the dossier price, zero drift since valuation_asof 2026-06-08. Spread to $14.23 deal value = +11.6% gross; downside to $11.80 floor = -7.5%; R:R = 1.48/0.95 = 1.56, identical to the dossier's computed_rr. Edge fully intact; ~11.6% over ~112 days is ~38% annualized on the spread.
- **2 · Tradeability:** Stock expression on a NYSE name: ~438k shares / ~$5.6M traded today, $723M market cap, listed options also available if a collar is ever wanted. Standard arb size executes without friction. No short leg, no borrow question.
- **3 · Window ↔ expression:** Milestone 2026-09-30 (112 days). Expression is common stock held through close — no expiry to clear, window satisfied by construction. If close slips past Q3 the position simply carries; only cost is annualized-return decay, not a structural loss.
- **4 · Driver tag:** Deal_close_generic — confirmed; unique driver in this batch, no collision.

### UNF — UniFirst Corporation  ⏳ PENDING
`8% · equity · merger_arb · US_antitrust (Deal-completion) · score 7.0 · edge M · RESTING LIMIT ≤ $267.0 since 2026-06-10 — NOT HELD`
- **Why not held:** live price at stamp exceeded the CRO entry limit — a real book does not fill this order. Fills automatically via the daily mark when the close trades ≤ $267.0.
- **Hedge leg (recorded):** -0.772 CTAS per share, reference $179.87 — Hedge the share-ratio leg: short 0.7720 CTAS per UNF to isolate the ~$23/sh cash+spread
- **Risk-to-floor (computed):** 0.272% of NAV (cap 1.5%)
- **Expected:** R:R 1.86:1 · milestone 2026-11-30 (173d)
- **Director — why this seat:** Cash + 0.7720 CTAS deal worth ~$293.86 vs $270.48 leaves an 8.6% gross spread to the 11/30 close; recorded with the CRO entry limit <= $267 and the 0.7720 CTAS short hedge to isolate the spread. Held to 8% (well under the floor-math cap) because live R:R compressed to 1.86 after the pop and a break would overshoot the $257.91 standalone floor.
- **Director — what kills it:** HSR second request that materially derails the timeline, or deal repriced/terminated — a break trades well below the symmetric floor (200d avg $209).
- **Review trigger:** Antitrust clearance checkpoints into the 2026-11-30 expected close; re-confirm timeline before any size-up.

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
- **Risk-to-floor (computed):** 1.447% of NAV (cap 1.5%)
- **Expected:** R:R 6.73:1 · milestone 2026-09-30 (112d)
- **Director — why this seat:** Highest ratio edge among survivors — live R:R 6.73 to the $9 de-levering target against a market-tested $3.90 floor (the 52-week low), on a dated Q3-2026 refi milestone. Equity-only per CRO (options chain is dead); live $4.56 sits comfortably under the $4.80 entry limit, and 10% weight risks 1.45% NAV to floor.
- **Director — what kills it:** Refi/de-levering fails to materialize in Q3, or price loses the $3.90 floor — the one market-tested level in the thesis; the $0.66 denominator makes the edge hypersensitive above ~$4.80.
- **Review trigger:** 2026-09-30 refi/de-levering milestone; interim review on any debt-removal announcement.

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
`5% · equity · forced_seller · Forced_divest_flow (Idiosyncratic) · score 4.0 · edge H · STAGING (half-weight, equity-only) · entry 2026-06-10 @ 20.49 (cro_live_check)`
- **Risk-to-floor (computed):** 0.73% of NAV (cap 1.5%)
- **Expected:** R:R 3.85:1 · milestone soft/undated
- **Director — why this seat:** Post-IPO lockup supply-clearing mean-reversion: live R:R improved to ~3.85 at $20.49 vs the $17.50 floor, and at ~$340M/day ADV it is the most executable flow trade in the pool. Staging half-weight equity; thesis is supply clearing, so exit near FV $32, not an open-ended re-rate.
- **Director — what kills it:** Final-unlock date slips materially or remaining locked supply is larger than modeled; close below the $17.50 floor kills the mean-reversion setup.
- **Review trigger:** Verify and review at the final lockup expiration date (per CRO condition, confirm the exact date and remaining share count).

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
`5% · equity · forced_seller · Forced_divest_flow (Idiosyncratic) · score 5.0 · edge H · STAGING (half-weight, equity-only) · entry 2026-06-10 @ 15.65 (cro_live_check)`
- **Risk-to-floor (computed):** 1.23% of NAV (cap 1.5%)
- **Expected:** R:R 2.94:1 · milestone soft/undated
- **Director — why this seat:** BHC's 88% stake suppresses a $26.97 SOP value vs $15.65 live — R:R 2.94 with 84% of dossier edge retained. Takes the second Forced_divest seat after MGNI was passed on edge compression; staging half-weight equity, accumulation-only with limits per CRO (covered-call overlay dropped — the chain is near-dead).
- **Director — what kills it:** BHC restructures around the stake with no disposition path (overhang becomes permanent), or the $11.80 floor breaks.
- **Review trigger:** Any BHC stake-disposition or strategic-review announcement; quarterly re-check of the overhang status.

**CRO verdict: TRADE_WITH_CONDITIONS**
- **1 · Edge at entry (live re-check):** Live $15.65 (FMP/IBKR 6/9 close) vs dossier mark $15.18 (asof 6/8). Recomputed SOP R:R = (26.97-15.65)/(15.65-11.80) = 2.94 vs dossier 3.49 — 84% of dossier R:R retained, well above the half line. Edge intact; R:R stays >= 3.0 at entries <= $15.55.
- **2 · Tradeability:** Equity leg: only $7.4M avg 90d USD volume (IBKR) — thin for a $5.6B name because BHC holds 88% and the public float is ~12%; cap the position so it's <= ~5-10% of ADV and expect poor off-hours depth (pre-market quote was 14.71/15.98). Covered-call leg FAILS the cost test: avg option volume is 90 calls / 1 put per DAY — the chain is near-dead, spreads will be a large fraction of premium. The 'sell covered calls while waiting' overlay does not exist at acceptable cost.
- **3 · Window ↔ expression:** Undated milestone — BHC's 88% stake disposition has no fixed date (it's an overhang-resolution flow trade). Staging rule maps to equity; no expiry to clear. The CC overlay, if ever written, has no window constraint but fails on liquidity regardless.
- **4 · Driver tag:** CONFIRMED: Forced_divest_flow — BHC's 88% stake disposition/distribution is genuine forced-divest flow in BLCO shares. FLAG: MGNI in this batch carries the same tag — Director cap applies as-tagged, though MGNI is arguably mistagged (antitrust remedy, not seller flow), in which case the true overlap dissolves.
- ⚠ **Condition:** Equity-only expression: drop the covered-call overlay (avg OI/volume ~90 calls/day cannot fill at acceptable cost); if a CC is ever written, limit-at-mid only and only where strike OI > 100
- ⚠ **Condition:** Size to <= ~5-10% of the $7.4M/day ADV (float is ~12% of shares out); accumulate with limits, no market orders
- ⚠ **Condition:** Director must adjudicate the Forced_divest_flow dupe with MGNI

### CELC — Celcuity Inc.
`1.5% · debit spread exp 2026-09-18 strikes buy $95C / sell $155C · bio_convergence · FDA_clinical_readout (FDA/biotech) · score 8.0 · edge H · entry 2026-06-10 @ 92.59 (cro_live_check)`
- **Expected:** EV 50.1% · milestone 2026-07-17 (37d)
- **Director — why this seat:** Highest-score H-grade unconditional TRADE in the batch: p=0.85 to $153 on the 7/17 readout, live EV +50% after the pop. The Sep-18 95/155 call spread defines risk and sells back the ~80% event IV the CRO flagged on outright calls, clearing the milestone with +1 monthly margin; premium sized at 1.5% because its EV is roughly half EYPT/VRDN's.
- **Director — what kills it:** Primary-endpoint miss on the 7/17 readout — spread premium is the full and only loss.
- **Review trigger:** 2026-07-17 clinical readout.

**CRO verdict: TRADE**
- **1 · Edge at entry (live re-check):** Live $92.59 (FMP batch-quote 2026-06-10, +5.9% on the day; IBKR real-time last $92.70) vs dossier $87.43. Recomputed: upside to $153 = +65.2%, downside to $60 = -35.2%, payoff 1.85 (dossier 2.39), EV = 0.85*0.652 - 0.15*0.352 = +50.1% (dossier +59.0%). ~15% EV compression after today's pop — still far above the half-R:R kill line. Edge intact.
- **2 · Tradeability:** Equity expression, and it is the most liquid name in the batch: $110M/day 90d USD ADV (IBKR), 1.37M shares today. Any realistic sleeve position is a rounding error vs ADV. Options are active (avg ~2,337 calls / 1,177 puts daily) but annual IV ~80% — dossier's own note that July/Aug calls carry rich event IV is confirmed; equity is the right expression.
- **3 · Window ↔ expression:** Milestone 2026-07-17, 37 days out. Equity has no expiry — window clears by construction. No slippage history concern for the expression.
- **4 · Driver tag:** FDA_clinical_readout — confirmed. FLAG: same driver as AMLX and DFTX (three names, one driver) — Director cap applies; this is the strongest of the three on edge grade (H) and tradeability.

### VRDN — Viridian Therapeutics, Inc.
`2% · debit spread exp 2026-08-21 strikes buy $17.5C / sell $35C · bio_convergence · FDA_approval_decision (FDA/biotech) · score 6.0 · edge H · entry 2026-06-10 @ 16.31 (cro_live_check)`
- **Expected:** EV 105.0% · milestone 2026-06-30 (20d)
- **Director — why this seat:** Nearest hard catalyst in the basket — 6/30 FDA decision in 20 days at p=0.9, EV ~+105%, with equity still near its 52-week low and the only genuinely liquid options chain among the dated binaries. Aug-21 expiry gives +1 monthly margin past the decision; 2% premium-at-risk.
- **Director — what kills it:** CRL or negative FDA decision on 6/30 — premium is the full loss.
- **Review trigger:** 2026-06-30 FDA approval decision.

**CRO verdict: TRADE**
- **1 · Edge at entry (live re-check):** Live $16.31 (FMP, +3.7% today) vs dossier $15.73 - edge intact; still far under 200d $24.25 and near 52w low $13.18. Binary EV unchanged: ~90% to $35 / $8 floor, payoff ~2.5x. No compression.
- **2 · Tradeability:** Most tradeable binary in the batch: ~$46M ADV, stock spread $15.80/$16.25 (~2.8%), avg ~585 calls/day (today 631), IV ~91%. Options genuinely liquid; equity trivially so.
- **3 · Window ↔ expression:** Milestone 6/30 (20d). Equity = clean expression, no window risk. Option route: July monthly (7/17) is only the first expiry past 6/30 - use Aug (8/21) for +1 monthly margin against an FDA date slip.
- **4 · Driver tag:** FDA_approval_decision (veligrotug TED BLA, PDUFA 6/30). Confirmed. CLASH FLAG: ZYME in this same batch also resolves on FDA_approval_decision - flag the pair to the Director for the driver cap.

### AQST — Aquestive Therapeutics, Inc.
`4.5% · equity · bio_convergence · FDA_approval_decision (FDA/biotech) · score 6.5 · edge H · STAGING (half-weight, equity-only) · entry 2026-06-10 @ 3.99 (cro_live_check)`
- **Risk-to-floor (computed):** 1.398% of NAV (cap 1.5%)
- **Expected:** EV 69.8% · milestone 2026-09-30 (112d)
- **Director — why this seat:** Strongest live edge in the batch per the CRO check (+69.8% EV, payoff 3.6x) into the Q3 Anaphylm resubmission. Staging-rule equity (the thin chain cannot offer the Apr-2027+ expiries the post-resubmission window requires); 4.5% weight is jointly bound by the half-weight rule and a 1.49% risk-to-floor.
- **Director — what kills it:** Resubmission slips past Q3-2026 or a new CRL-grade deficiency is disclosed; price through the $2.75 floor.
- **Review trigger:** Anaphylm resubmission by 2026-09-30; then re-stage for the FDA action window (Q1-2027).

**CRO verdict: TRADE**
- **1 · Edge at entry (live re-check):** Live $3.99 (FMP/IBKR 6/9 close) vs dossier mark $3.91 (asof 6/8). Recomputed: payoff (8.5-3.99)/(3.99-2.75)=3.64 vs dossier 3.96 (92% retained); binary EV=(6.775-P)/P = 69.8% vs dossier 73.3%. Edge intact — strongest live edge in the batch.
- **2 · Tradeability:** Equity (the dossier's primary instrument): $6.1M avg 90d USD volume on a $396M cap — fine for a small sleeve position with limits; quote 3.90/3.99. Options: avg 368 calls / 817 puts per day — too thin for long-dated calls at acceptable cost on a $4 stock; I disagree with the dossier's 'long-dated calls viable' aside — equity only.
- **3 · Window ↔ expression:** Milestone 2026-09-30 (~112d) is the Anaphylm RESUBMISSION — a milestone, not the FDA verdict (the dossier says so itself), and this path has already slipped once (original filing drew a CRL). Equity clears trivially with no expiry. Any optionality would need to clear the post-resubmission FDA action window (Class 1/2 review = ~2-6 months after, i.e. into Q1-2027) — requiring Apr-2027+ expiry the thin chain can't offer at cost. Equity-only resolves the window cleanly.
- **4 · Driver tag:** CONFIRMED: FDA_approval_decision (terminal driver is the FDA action on the Anaphylm resubmission; the 9/30 date is the resubmission gate on that path). FLAG: RARE in this same batch also resolves on FDA_approval_decision — Director same-driver cap applies to the pair.

### WVE — Wave Life Sciences Ltd.
`3.5% · equity · bio_convergence · FDA_pathway_feedback (FDA/biotech) · score 6.0 · edge H · STAGING (half-weight, equity-only) · entry 2026-06-10 @ 5.78 (cro_live_check)`
- **Risk-to-floor (computed):** 1.381% of NAV (cap 1.5%)
- **Expected:** EV 20.6% · milestone 2026-07-31 (51d)
- **Director — why this seat:** Mid-2026 FDA feedback on the WVE-006 accelerated-approval pathway — re-tagged FDA_pathway_feedback per the CRO's explicit condition (regulatory inflection, not an approval verdict), which adds a distinct driver lane to the FDA cluster. The soft date forces staging-equity treatment despite usable option liquidity; 3.5% weight risks 1.38% NAV to the $3.50 floor.
- **Director — what kills it:** FDA declines the accelerated pathway or the AATD program is deprioritized; floor break at $3.50.
- **Review trigger:** Mid-2026 FDA pathway feedback (soft) — hard review end-August 2026 if no communication has landed.

**CRO verdict: TRADE_WITH_CONDITIONS**
- **1 · Edge at entry (live re-check):** Live $5.78 (FMP batch-quote, ts 2026-06-10) vs dossier $5.70 — moved +1.4%, edge intact. Recomputed to FV $11 = +90% upside; R:R = 5.22 up : 2.28 down = ~2.29:1 (vs dossier payoff 2.41). No compression.
- **2 · Tradeability:** BEST option liquidity in the batch: avg 1290 call / 135 put per day (today 3123 call), 90d ADV ~$27.8M, annual IV ~90%, OI put/call ~0.52. Both equity and a long call are genuinely tradeable; a protective put market exists. This is the one name where capping downside via a long call is realistic.
- **3 · Window ↔ expression:** DATE/DRIVER MIS-STATED. The mid-2026 event is FDA FEEDBACK on a potential ACCELERATED-APPROVAL PATHWAY for WVE-006 (AATD) — a regulatory engagement / inflection, NOT a PDUFA approval decision, and 'mid-2026' is SOFT, not a hard Jul 31. A July option could easily miss a soft, slip-prone feedback timeline. Use Aug/Sep-2026+ expiry or equity.
- **4 · Driver tag:** CORRECTION: tagged FDA_approval_decision but it is really an FDA_regulatory/clinical inflection (accelerated-approval pathway FEEDBACK on WVE-006), not an approval decision. DUPLICATE FLAG: as currently tagged it duplicates BBIO's FDA_approval_decision; on the corrected tag it instead sits closer to the clinical_readout cluster. Either way, flag for the Director cap.
- ⚠ **Condition:** Re-tag the driver: this is FDA pathway-feedback / regulatory inflection, not an approval decision
- ⚠ **Condition:** Do NOT use a July expiry against a soft 'mid-2026' window — use Aug/Sep 2026 or later, or equity
- ⚠ **Condition:** Given real put liquidity, a long call to cap the micro-cap binary downside is acceptable here

---
## 2 · CRO kills — NO_TRADE (4)

*Killed on trade grounds only (edge gone / untradeable / window fails) — the catalyst itself was already verified upstream.*

### DFTX — Definium Therapeutics, Inc.  `ACTIVE · bio_convergence · edge M`
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Data hygiene flag first: FMP batch-quote misidentifies DFTX as 'Mind Medicine (MindMed) Inc.' at $22.95 — bad symbol mapping on FMP's side. IBKR resolves DFTX = Definium Therapeutics Inc, NASDAQ (contract 845905488), real-time last $21.87, not halted. Recomputed at $21.87: upside to $36 = +64.6%, downside to $8 = -63.4%, payoff 1.02, gross EV = 0.55*0.646 - 0.45*0.634 = +7.0%. The dossier's own asof EV was only +1.65% with payoff 0.86 — there was never edge here. Net of the live 5.1%-wide equity quote ($21.85 x $23.00), EV ~ +2%. A 55/45 binary risking -63% to make +65%, 20 days out, with ~zero net EV is not a trade.
- **2 · Tradeability:** Equity is liquid ($41.4M/day 90d USD ADV) but the live bid/ask is 5.1% wide — that alone consumes most of the gross EV. Options are active (avg ~875 calls / 596 puts daily) but annual IV is 139%: the market is fully pricing the binary, so the dossier's suggested Jun-Jul straddle buys the event at peak premium with ~zero modeled EV behind it. No expression survives transaction costs.
- **3 · Window ↔ expression:** Milestone 2026-06-30, 20 days out — June/July expiries exist and would clear, so the window is not the problem. The edge is.
- **4 · Driver tag:** FDA_clinical_readout — confirmed. FLAG: same driver as AMLX and CELC (three names, one driver); killing this name also relieves the Director's driver-cap pressure.

### PRX.AS — Prosus N.V. (forced seller of Delivery Hero)  `WATCH · forced_seller · edge M`
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live EUR 39.545 (FMP, -0.7%) vs dossier EUR 40.07 - drifting onto its own downside floor EUR 37.365 (= 52w low). 'Recovery' target EUR 46.21 is +16.9% / -5.5% to floor, but there is NO dated forcing event behind it.
- **2 · Tradeability:** Liquid enough as equity (AMS, ~1M sh/day), but tradeability is moot - there is no perishable event-driven edge to express. Belongs in the value sleeve, not Basket 13.
- **3 · Window ↔ expression:** WATCH/staging, dated_milestone = null. No dated catalyst -> nothing to clear and no event expiry to structure. Indefinite-hold value idea, not a catalyst trade.
- **4 · Driver tag:** Forced_divest_flow - but per the dossier's own note this is a perennial holdco discount, not an event; the Delivery Hero (DHER) re-rate that would close it has already fired.

### AVIR — Atea Pharmaceuticals, Inc.  `WATCH · bio_convergence · edge H`
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live $4.36 (FMP batch-quote, ts 2026-06-10) vs dossier $4.32 — edge nominally intact (+118% to FV $9.5; R:R = 5.14 up : 1.16 down = ~4.43:1). Thesis edge is fine; the trade fails on tradeability, not edge.
- **2 · Tradeability:** INSTRUMENT IS UNTRADEABLE. Equity 90d ADV only ~$1.58M/day (today vol 232k sh, $349M micro-cap) — a meaningful sleeve position would move the tape and be hard to exit around a binary. Options effectively DEAD: avg 48 call / 0 put per day, today 2 call / 0 put, underlying indicative spread $3.80/$5.30 (~28% wide). No put OI to cap the binary, no real call liquidity. A correct thesis in an instrument this illiquid is not a trade.
- **3 · Window ↔ expression:** STAGING/SOFT. C-BEYOND Ph3 HCV topline guided to MID-2026, C-FORWARD year-end 2026 — real and near, but undated and not a PDUFA. Equity would be the only expression, and ADV makes even that impractical at size.
- **4 · Driver tag:** FDA_clinical_readout CONFIRMED (Ph3 topline). DUPLICATE-DRIVER FLAG: OLMA and RLMD also FDA_clinical_readout (3 names same driver) — moot here given NO_TRADE, but noted for the Director cap.

### DJT — Trump Media & Technology Group Corp.  `WATCH · spinoff · edge M`
**CRO verdict: NO_TRADE**
- **1 · Edge at entry (live re-check):** Live 8.16 (FMP batch-quote, ts 2026-06-10) vs dossier 8.15 asof 2026-06-08 — flat, no edge creation. Dossier EV was already only +0.61% (payoff 1.54, win 0.40); recomputed at 8.16: upside to FV 13 = +59%, downside to floor 5 = -39%, EV ~ +0.2%. Negligible, negative-skew. This is at/below half the (already near-zero) dossier edge -> NO_TRADE on surface 1 alone.
- **2 · Tradeability:** Liquid (ADV ~4.8M sh x $8 = ~$39M/day, deep options) — tradeability is NOT the problem; the edge is. A correct-on-paper binary with ~0% EV and -39% downside is not a trade.
- **3 · Window ↔ expression:** dated_milestone=null, staging=true. No dated spin/index-inclusion event substantiated; stock at fresh 52-wk low (7.76), 200d 12.41, structural decline (Q1 rev $871K, $406M loss, Truth Social crypto-ETF pulled 5/20). Downside floor $5 is fragile, not a hard backstop.
- **4 · Driver tag:** resolution_driver 'Spin_index_flow' NOT supported by current evidence — no dated spin/index-flow catalyst found; DJT already public, recent corporate actions (fusion merger, ETF withdrawal) are dilutive/negative, not index-flow drivers. Driver tag is the weak point.

---
## 3 · Non-selections (16) — recorded counterfactuals

*CRO survivors the Director passed on, plus stamp-time exclusions; the tracker records these for selection-calibration (did the passes outperform the picks?).*

| Symbol | Lane | Driver | Edge | CRO verdict | Passed because |
|---|---|---|---|---|---|
| **AMLX** | bio_convergence | FDA_clinical_readout | M | TRADE_WITH_CONDITIONS | FDA_clinical_readout driver cap (2) taken by CELC (score 8, H-grade TRADE) and EYPT (highest EV in pool). AMLX is the weaker holder of the seat: M-grade, EV already 12% compressed, a soft quarter-end date, and a thin chain whose conditions (Nov+ expiry, OI>=300, spread<=12%) degrade the only acceptable defined-risk expression — full-size equity is explicitly barred on a -70% floor. |
| **ZYME** | bio_convergence | FDA_approval_decision | M | TRADE_WITH_CONDITIONS | FDA_approval_decision driver cap (2) taken by VRDN and AQST. Thinnest EV in the batch (23.5%) on a low-payoff/high-prob binary with little room for entry slippage — worst EV-per-premium of the dated binaries. |
| **BBIO** | bio_convergence | FDA_approval_decision | H | TRADE_WITH_CONDITIONS | FDA_approval_decision driver cap — lost the second seat to AQST (EV 69.8% vs ~45%) with VRDN holding the first (p=0.9, 20-day hard date). Also rule-conflicted: staging=true forces equity-only under the basket rules while the CRO's preferred expression is Jan-2027 calls. Strong name; first alternate if an approval seat opens. |
| **VIR** | bio_convergence | FDA_clinical_readout | H | TRADE | Closest cut in the basket. FDA_clinical_readout driver cap — best live staging edge (+63.4% EV, fully intact) but lost the two seats to CELC (dated 37d, score 8, TRADE) and EYPT (EV +116%, dated); VIR's Q4-2026 readout is soft/undated. First alternate if a readout seat opens. |
| **RARE** | bio_convergence | FDA_approval_decision | H | TRADE | FDA_approval_decision driver cap. Live EV down to 16.9% after the conference pop (vs AQST 69.8% / VRDN ~105%), score 4, and the catalyst path has already slipped once onto a facility re-inspection gate. |
| **MGNI** | forced_seller | Forced_divest_flow | M | TRADE_WITH_CONDITIONS | Edge >90% compressed: +8% unexplained move leaves binary EV at ~0.7% at market vs 8% dossier — below the half-R:R kill line per the CRO's own check. Trade only exists on a pullback to <=$15.19 that cannot be assumed at record time. Passing MGNI also resolves the CRO's Forced_divest_flow dupe adjudication in favor of BLCO. |
| **ANNX** | bio_convergence | FDA_clinical_readout | H | TRADE_WITH_CONDITIONS | FDA_clinical_readout driver cap, and the lowest EV of the readout candidates (21.8%) on an H2-2026 placeholder date (12/31) with a chain that traded 8 contracts today — the option expression the dossier leaned on is a verified window flaw. |
| **OLMA** | bio_convergence | FDA_clinical_readout | H | TRADE_WITH_CONDITIONS | FDA_clinical_readout driver cap. The +4.9% pop compressed R:R from 4.06 to 3.43 on an undated fall-2026 readout; behind CELC/EYPT/VIR in the same-driver queue on both edge and dating. |
| **RLMD** | bio_convergence | FDA_clinical_readout | H | TRADE_WITH_CONDITIONS | Most degraded live entry in the batch: +9.6% pop took R:R from 2.38 to ~1.71, valid only at/below $5.72 per the CRO limit. Ph3 only initiating mid-2026 (year-end readout, high slip risk) and no put market exists to cap the binary. Driver cap full regardless. |
| **CLVT** | forced_seller | Forced_divest_flow | H | TRADE_WITH_CONDITIONS | Forced_divest_flow driver cap (2) taken by FIG (most executable, R:R 3.85) and BLCO (H-grade, clearer disposition path). CLVT's 40% floor distance caps it at ~3.7% weight anyway, and the binary deal-materialization thesis is the most speculative of the flow trades. |
| **DBVT** | bio_convergence | FDA_clinical_readout | H | TRADE_WITH_CONDITIONS | FDA_clinical_readout driver cap, plus a hard practical ceiling: no options exist on the ADR and the CRO caps equity at ~$350-400K notional working across sessions — too small to carry a meaningful sleeve weight even on paper parity. Edge intact; liquidity, not edge, is the disqualifier. |
| **GLUE** | bio_convergence | FDA_clinical_readout | H | TRADE_WITH_CONDITIONS | FDA_clinical_readout driver cap. EV 35.8% sits below VIR and PVLA among same-driver staging peers; undated soft H2-2026 window and a near-dead chain (4 calls/day) leave nothing the seats don't already cover better. |
| **PVLA** | bio_convergence | FDA_clinical_readout | H | TRADE_WITH_CONDITIONS | FDA_clinical_readout driver cap. Solid edge (EV 60.5%) but undated H1-2027 window, and the CRO flagged an unexplained 562-put anomaly (vs 109/day avg) that must be cleared before entry — an open condition I cannot verify at record time. |
| **CERS** | bio_convergence | FDA_approval_decision | H | TRADE_WITH_CONDITIONS | FDA_approval_decision driver cap. Score 4, fully undated (no FDA decision visible in recent flow), with proxy-fight and refi noise around the story; EV 37.5% is well below both chosen approval seats. |
| **NKTR** | bio_convergence | FDA_clinical_readout | H | TRADE_WITH_CONDITIONS | FDA_clinical_readout driver cap. No near-term event to size around (REZPEG durability ~Q4-2026) and a 60.9% floor distance caps weight at ~2.5% — minimal contribution even if a seat were open; CERS/NKTR cluster pairing concern is mooted by passing both. |
| **EYPT** | bio_convergence | FDA_clinical_readout | H | TRADE_WITH_CONDITIONS | EXCLUDED AT STAMP: blocking CRO condition failed/unverifiable at stamp time (= order time): required chosen-strike OI > 500 on the Oct-16 12.5/35 calls; the read-only feed has no per-strike chain endpoint and the whole EYPT chain averages 42 calls/day (148 traded 6/10, IBKR) — an OI>500 strike cannot be evidenced. PVLA standard applied (same class of unverifiable condition, same treatment); the equity fallback is barred by the binaries-defined-risk hard cap (non-staging binary_prob). |

---
## 4 · Director memo (verbatim)

Basket 13 holds 10 names, 55.5% of NAV invested, balance cash by construction. Cluster mix on invested weight: Deal-completion 22.0 (39.6%), Idiosyncratic 20.0 (36.0%), FDA/biotech 13.5 (24.3%) — all under the 40% cap. Driver spread: 7 distinct drivers, none above 2 names. Shape: a floor-bounded ratio-carry core (GDOT 14, FIP 10, UNF 8, FIG 5, BLCO 5 — each sized to <=1.5% NAV risk-to-floor) funds a strip of dated defined-risk binaries (CELC/EYPT/VRDN debit spreads, 5.5 points of premium, each clearing its milestone by +1 monthly and sized off EV not payoff) plus two staging-equity binaries (AQST 4.5, WVE 3.5) held under the half-weight rule with floor-risk <=1.5% so their NAV-at-risk matches the binary premium cap. Why not ~100: the pool spans only 7 drivers, so the <=2-per-driver cap allows at most ~10 seats, and the binary 2% / staging half-weight / risk-to-floor caps bound those seats — the structural maximum is ~67 invested even stretching into weaker names (BBIO/VIR equity bulk over VRDN/EYPT); I took 55.5 with the stronger seats rather than bulk weight into thinner edge. Adjudications of record: MGNI/BLCO dupe resolved by passing MGNI (edge >90% compressed on an unexplained pop); WVE re-tagged FDA_pathway_feedback per explicit CRO condition, keeping the approval driver at two (VRDN, AQST); BBIO and VIR are the named first alternates if an approval or readout seat opens. Dated ratio names (GDOT/UNF/FIP, all <=6 months) are recorded as equity per CRO instruments — the defined-risk-option rule is enforced on the binaries, where the floor does not bound the loss; for the spreads/recovery names the deal floor is the risk definition and the 1.5% floor-risk cap is the binding control. CRO entry limits recorded where conditioned (UNF <=$267, FIP <=$4.80, EYPT OI/spread check at order time)."

---
*Caps at stamp time: 0 violations · 8 entries stamped · 16 non-selections recorded. Review doc auto-generated by backend/_basket13_review.py.*
