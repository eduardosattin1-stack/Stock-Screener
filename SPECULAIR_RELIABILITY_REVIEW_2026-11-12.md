# Speculair reliability review — 12 November 2026

Scope: the weekly debate and the value book, reviewed as a system someone follows with real money.
This is a methodology audit, not investment advice. Nothing in the pipeline was changed.

Evidence used: the value and regime tracking files, 4,823 dated debate-history entries across 768
names (39 run dates, June to November), daily closes for all of them pulled fresh from FMP, this
week's grading input, the macro snapshot, the bi-weekly macro read, and the two Gemini pickups.

## 1. Verdict

The value book's result is real, but it is narrower than the headline suggests, and three things
make it less reliable than it could be: held seats are re-underwritten too rarely, the macro
inputs describe only the United States while five of seven seats are elsewhere, and every
concentration limit is advisory.

## 2. The track record

| Measure (8 June to 10 November) | Result |
|---|---|
| Value book, paper | +35.8% |
| Global shares (ACWI) | +0.5% |
| US large caps (SPY) | +1.4% |
| US value (IWD) | +10.7% |
| International value (EFV) | +4.4% |
| Closed trades | 43; 60% winners; average +5.8%, median +2.5% |
| Worst drawdown | -4.6% |

- **The paper prices are not flattering the record.** Re-pricing all 43 closed trades at the first
  daily close after each decision gives an average of +6.5% against the recorded +5.8%. Single
  trades differ by up to 15 points either way, so it is noise, not bias.
- **Half the gain came from three trades.** HRB (+52.7%), THC (+43.9%) and LNC (+27.1%) are 124 of
  the 249 summed return points. All three were US names opened in June or early July.
- **Most of it was earned early.** June to August: +30%. Since 1 September: +4.3%, against -3.2%
  for global shares. Still ahead, on a much smaller margin.
- **Short holds earned nothing.** 25 of 43 trades were held 21 days or less: average about +1%,
  under half winners. The 18 held longer averaged +12%, 83% winners. The churn was mostly June
  (the pipeline was being rebuilt) plus one bad-data week in August; since late August holds run
  3 to 8 weeks.
- **What the record does not include:** trading costs, stamp duties and transaction taxes, currency
  moves, dividends, and the rebalancing forced each time the seat count changed (it ranged from 4
  to 10, so one name was anywhere from 10% to 25% of the book).

## 3. Does the debate predict anything?

Scored over 34 run dates, forward 4 weeks, each group measured against the average of all names
debated the same week.

| Group | Names x weeks | Excess over 4 weeks | Beat the pool on |
|---|---|---|---|
| Grade A (buy now) | 119 | +1.5 pts | 8 of 15 dates |
| Grade B (wait) | 2,118 | +1.0 pts | 25 of 34 |
| Grade C (pass) | 1,820 | -1.3 pts | 8 of 34 |
| Value conviction 1 | 93 | -4.6 pts | 3 of 16 |
| Value conviction 2 | 1,301 | -0.8 pts | 7 of 20 |
| Value conviction 3 | 1,365 | +1.0 pts | 17 of 20 |
| Value conviction 4 | 409 | +0.4 pts | 8 of 20 |
| Record re-debated that week | 2,034 | +0.6 pts | 24 of 34 |
| Record carried forward | 2,023 | -0.6 pts | 3 of 20 |

- **The debate is good at saying no.** Pass grades and low conviction underperform consistently.
- **It does not rank the top.** Grade A is no better than B, and conviction 4 is no better than 3.
  Inside the value book the Director's score ran the wrong way: the higher-scored half of closed
  trades averaged +2.7%, the lower half +9.3%.
- **The typed fair-value gap looks like the best signal, on thin evidence.** Only two run dates
  have typed prices old enough to score. On both, names with the largest gap to fair value beat
  those with the smallest by about 9 points over 4 weeks, in order across five groups.
- **Carried records lag.** A view that was not re-debated that week did worse than one that was.
  That is partly selection (names get re-debated because something happened), but it argues
  against treating a carried view as a current buy signal.
- **Week-to-week stability is fine.** Between consecutive fresh debates the grade changed 11% of
  the time, almost always between wait and pass; fair value moved by a median of 0%.

Caveat on all of this: five months, one market regime, overlapping windows. Treat it as direction,
not proof.

## 4. Where the debate is weakest

1. **Held seats are the least-examined names in the book.** A held seat gets a light weekly update;
   a full re-underwrite is forced only by a trigger or at 91 days. Days since the last full debate:
   DUE.DE 78, INCH.L 29, 2618.HK 29. Those are the three seats where Gemini's value sits furthest
   below ours, and INCH.L and 2618.HK are the two Gemini repriced this week.
2. **The book holds names it would not buy.** Four of seven seats are graded "wait". The rotation
   rule keeps a held name unless its thesis breaks, which is sensible for turnover, but it means the
   book is a hold list, not a buy list, for anyone entering now.
3. **The Gemini check has never said no.** Across the two weeks picked up: 12 confirmed, 7 repriced,
   1 unverified, 0 disagreements out of 20. Several of its values are within 1% of ours, because it
   works from the same input bundle. It tests the reasoning, not the data. Its skeptic's corrections
   (share counts, segment profits, net debt) are the valuable part, and today they are discarded.
   Weeks 44 and 45 were never picked up.
4. **The screen feeding the debate is only loosely related to its conclusions.** This week the
   screen's margin of safety and the debate's reconciled one correlate at 0.28, and 71% of screen
   discounts shrink by more than half once debated.
5. **Silent failures in the weekly run.** This week a network timeout produced a Director ledger
   showing no held seats and dropped a live position from the universe without any stop; three runs
   wrote to the same folder at once; the debt-cycle auction input has been missing (defaulted) and
   20 AI names in a method basket have no debate.

## 5. Macro: what reaches the value book

- **The value book is macro-blind by design**, apart from one sentence on rate-sensitive balance
  sheets. Each name carries a macro-fit label, but it moves nothing.
- **Every measured macro input is American:** the Treasury curve, VIX, US inflation and GDP, the
  30-year real rate, US high-yield spreads, the Fed balance sheet and US interest costs. The value
  book is two Hong Kong, two UK, one German and two US names.
- **The numeric read and the written read disagree.** The risk dial says neutral. The bi-weekly
  macro read has three tripwires breached at once: oil (Brent above $110 for seven sessions), AI
  capital spending, and credit (the gap between the weakest and stronger junk bonds above 1,100bp).
  A December rate rise is about 85% priced; the US-China truce runs to 10 January.
- **Inputs are old.** Inflation is 70 days old and GDP 132 days old in the snapshot.
- **No currency view at all.** The record is in local currency. Since June the dollar, sterling and
  the Hong Kong dollar each gained about 3.3% against the euro, which a euro investor received on
  top; the reverse would have been invisible too.

## 6. Limits

All caps are advisory while books are equal-weighted, so the published weights are one-seventh each:

| Exposure in the published value book | Share |
|---|---|
| Hong Kong / China (1698.HK, 2618.HK) | 29% |
| UK and sterling (INCH.L, MGNS.L) | 29% |
| Global auto cycle (DUE.DE, INCH.L) | 29% |
| Weak funded solvency (DUE.DE, INCH.L) | 29% |
| Dollar-linked currencies (USD + HKD) | 57% |
| Outside the euro | 86% |

There is no hard limit per country, per currency, per hidden factor or per single name, no minimum
seat count and no cash seat. The two weak-balance-sheet seats are the same two auto-cycle seats, in
a period when the credit tripwire is breached. A 15% free-float floor exists; there is no trading
volume floor.

## 7. Recommended changes, in order

**A. Make the existing signal more reliable**
1. Full re-debate of every value seat at least every 28 days, and immediately when Gemini reprices
   it or its skeptic records a material numeric correction.
2. Feed Gemini's skeptic corrections into the next debate as dated facts, and run the pickup every
   week as part of the routine.
3. Rank candidates by the typed fair-value gap and stop using the Director's score as the bar for
   adding a seat; the score has not ranked outcomes. Keep scoring the gap each week so the two-date
   evidence either builds or fails.
4. Use the debate as a filter: never seat a pass grade or value conviction 2 or lower (already the
   practice), and treat a carried record as "no current view" for new entries.
5. Make the weekly run fail loudly: stop prep when the live-book read fails, check every held seat
   is in the universe, add a lock so two runs cannot share the folder, and restore the auction feed.

**B. Add the missing macro inputs**
6. A regional panel (euro area, UK, China/Hong Kong, Japan): policy rate, 10-year yield, inflation
   and a business survey each, so macro fit is judged against the economy the company sells into.
7. An energy-cost flag per name while the oil tripwire is breached.
8. Credit conditions passed to the solvency check, so a weak balance sheet is treated more strictly
   when the credit tripwire is breached.
9. Analyst estimate revisions over one and three months, to catch cheap names still being cut.
10. A dated policy calendar per seat (the December Fed meeting, the 10 January truce date).
11. A base-currency view: exposure by currency and the book's return in euros beside local.

**C. Turn the limits into rules**
12. A maximum single-name weight and a minimum seat count, with empty seats held as cash.
13. Hard caps per country, per currency bloc and per hidden factor, enforced by seat count while
    the book is equal-weighted.
14. At most one weak-solvency seat per hidden factor.
15. Record the frictions in the track record: costs and duties per trade, and the rebalancing each
    time the seat count changes.

## 8. What was not checked

- Your real account against the book.
- Tax treatment of any holding.
- Whether a wider book would have done better; the evidence that the top does not rank suggests it,
  but it was not back-tested.
- The regime, Future Resources, mining and disruptor books beyond the comparisons above.
