# Basket audit — `graham_revised` (November 2026)

Scan audited: 2026-11-07 (3,430 names). Picks file: 2026-11-07. Pack: `packs/graham_revised.json`.
All code references are to `backend/screener_v6.py`. "CONFIRMED" means I reproduced it from the scan
row and/or a live FMP statement; "SUSPECTED" means the numbers point that way but I did not open the
statement.

## 1. Verdict

**UNSOUND.** The basket does pick cheap-looking stocks, but the number it ranks on is not a margin of
safety and is not Graham's revised formula.

1. **The growth term decides everything and it is a broken input.** Growth is the raw 3-year change
   in reported earnings per share between two single years, capped at 20% a year. 21 of the 30 picks
   sit exactly at that cap (28 of 30 are at 14% or more), which values them at 48.5 times earnings.
   The median pick is "worth" 5.7 times its price. Strip the growth term and only 10 of the 30 picks
   would still make the top 30.
2. **The "normalised" earnings figure can be inflated many times over by one-off gains, and has a
   sign bug.** The number-one pick, SPB, is valued on $93.93 of normalised earnings per share against
   $3.86 reported. At least 8 of the 30 picks are there because of a disposal gain, a tax credit, a
   stock split or a non-operating windfall — including **DUE.DE, the value-book seat**.
3. **Most of the turnover since 2026-09-22 was data, not valuation.** Of 9 logged exits, 4 were
   tickers that vanished from the scan (three of them were secondary share classes valued on the
   main class's earnings), 1 was a sign-bug pick (ALNY, −32%), and 1 was a one-off gain rolling out
   of the growth window (GEF).

What is right: currency handling is clean for all 30 picks, the sector gate keeps banks and insurers
out, there are no ties at the cut-off, the 0.95 cap binds on only one pick, and the tracked return
matches the picks' price moves.

## 2. What the rule actually computes

`fair value = earnings base x (8.5 + 2 x g)`, then `margin of safety = 1 − price / fair value`,
clipped to the range −1.0 to +0.95 (lines 3011–3017).

- **g** is `eps_cagr_3y x 100`, floored at 0 and capped at 20 (line 3011). `eps_cagr_3y` is the
  compound growth between the diluted earnings per share four annual reports ago and the latest one
  (line 2200) — two single years, no smoothing, one-offs included. If either year is not positive,
  g is 0.
- **Earnings base** is "normalised" earnings per share (lines 2844–2846): the 10-year median
  operating margin times latest revenue, multiplied by the ratio of 3-year average net income to
  3-year average operating income, divided by shares. If that comes out zero or negative the code
  falls back to the latest reported earnings per share (line 3014).
- **There is no bond-yield term at all.** Graham's 1974 revision multiplies by `4.4 / Y`, where Y is
  the current yield on top-grade corporate bonds. The code implements the older, unrevised formula
  under the "revised" name. The local 10-year yield table at lines 98–103 is used only by the
  earnings-yield-gap basket (line 6522); nothing in the Graham path reads it. So the answer to
  "which yield, how current, local or US" is: none.
- Gates applied at selection (lines 6889–6928): not a bank or insurer; no structural break; at least
  5 years of history; forward earnings not falling 25% or more; net debt under 3 times operating
  profit before depreciation; Piotroski score of 3 or more; names flagged as at a cyclical peak are
  re-scored; incumbents get +0.05; at most 9 names per sector.

I rebuilt the selection from the scan with these rules and reproduced the 30 picks exactly.

## 3. Findings, most serious first

### F1 — The growth input is saturated and driven by base-year troughs and end-year one-offs. HIGH, CONFIRMED

- Lines 2200, 2896, 3011. The cap of 20 gives a multiple of 48.5; zero growth gives 8.5. That is a
  5.7-fold swing in fair value from one input.
- 21 of 30 picks are at the cap; 28 of 30 have g of 14 or more; the lowest is 8.4 (2333.HK).
- In the whole eligible pool (924 names after the gates) 324 are at the cap. With the growth term,
  519 eligible names show a positive margin of safety; at zero growth only 71 do.
- Re-ranking the eligible pool at zero growth keeps only 10 of the 30 current picks in the top 30,
  and 12 of the 30 would show a negative margin of safety.
- The code's own comment at lines 2898–2908 says this growth figure is "fake ~70–80%" for CMCSA
  because it is measured off a 2022 trough, fixes it for the IV15 method, and states "Graham et al.
  keep the raw eps_growth_3y". CMCSA is a pick here: 2022 earnings per share $1.21 (impairment
  year) to $5.39 gives 64.5% a year, capped to 20, and a fair value of $240 against a $24 price.
- Affects: all 30 picks to some degree; decisive for the 20 that drop out of the top 30 at zero growth.
- Fix: use the de-peaked growth already computed for IV15 (`iv15_eps_growth`, line 2917), take the
  lower of that and forward growth, and cap g at about 7–10 (Graham's own working range). Do not
  let a single input move fair value more than about two-fold.

### F2 — "Normalised" earnings: unbounded ratio, sign bug, and a fallback that undoes the normalisation. HIGH, CONFIRMED

Lines 2844–2846 and 3014.

- **Unbounded ratio.** Net income divided by operating income is not limited. A disposal gain in any
  of the last three years inflates it. SPB: average net income $675.4m (FY2023 includes $2,035m from
  discontinued operations) over average operating income $30.0m gives a ratio of 22.5. Normalised
  earnings per share $93.93 against $3.86 reported; fair value $4,556 against an $86.68 price. In
  the scan, 132 qualifiers have a base more than twice reported earnings and 35 more than five times.
- **Two negatives make a positive.** If average net income is negative while average operating
  income is slightly positive, and the 10-year median margin is negative, the product is a large
  positive number. ALNY: average net income −$134.9m, average operating income +$14.2m (ratio −9.5),
  median margin negative, giving roughly $330 of "normalised" earnings per share against $2.33
  reported and a margin of safety of 0.94. ALNY was a pick from August until 2026-10-31 and lost 32%.
- **Fallback to the latest year.** When the normalised figure is zero or negative the code uses the
  latest reported figure, which is the peak-year route the normalisation was written to close. 68
  qualifiers take this route, 38 with a positive margin of safety, 2 current picks (OTEC.OL, VAL).
- Net income includes discontinued operations and tax credits. The base never checks
  `netIncomeFromContinuingOperations`.
- Fix: build the base from continuing operations; clamp the net-to-operating ratio to between 0 and
  1; if the normalised figure is not positive, score the name −1.0 instead of falling back.

### F3 — At least 8 of 30 picks are one-off or unit artefacts; 2 more ride a distorted growth base. HIGH, CONFIRMED

| Pick | Margin of safety | What is really driving it (FMP statements) |
|---|---|---|
| SPB | 0.95 (rank 1) | FY2023 $2,035m discontinued-operations gain inside the 3-year ratio; base 24 times reported earnings |
| SBSP3.SA | 0.94 | Stock split not reflected: earnings per share 12.37 on 684m shares, price on about 3,517m shares (market cap / price). Real price-to-earnings about 11, not 2.2. Corrected margin about 0.69, below the cut-off |
| OTEC.OL | 0.94 | Zero-revenue holding company. FY2025 profit is $58m of "other income". Normalised figure is zero, so falls back to latest earnings, then 48.5 times |
| VAL | 0.88 | FY2025 net income $983m includes a $427m tax credit (FY2023: $783m). Normalised figure not positive, falls back to latest $13.86 |
| MNC.WA | 0.85 | FY2025 net income PLN 498m includes PLN 424m non-operating; earnings per share 9.77 against 1.53 the year before |
| DUE.DE | 0.84 | FY2025 net income EUR 204m is EUR 256m from discontinued operations; continuing operations lost EUR 50m. **Holds a seat in both books** |
| BYD | 0.84 | FY2025 net income $1,843m includes $1,453m non-operating; earnings per share 22.56 against 6.19 |
| GNS.L | 0.75 | FY2026 net income GBP 285m includes GBP 223m non-operating; earnings per share 4.25 against 0.29. Also see F5 |
| CMCSA | 0.90 | Growth measured off the FY2022 impairment year (F1) |
| INVA | 0.87 | Earnings per share 3.30 against 0.36 on a +$163m swing in non-operating items |

SUSPECTED, not opened: GHC (base 1.81 times reported), COLR.BR (1.89 times), SSRM (3-year average
operating income is 2% of the latest year, base 1.44 times).

The other 17 (WWI.OL, KGN.WA, 0175.HK, JET2.L, 2333.HK, DVL.WA, 9022.T, BETS-B.ST, 1378.HK, A2A.MI,
ELEC.PA, 012330.KS, JD.L, UHS, DBC.WA, 2382.HK, 2883.HK) look like genuinely low price-to-earnings
names (median about 7), but their fair values are still inflated by F1.

Predictable consequence: SPB filed FY2026 on 2026-11-12. The FY2023 gain leaves the 3-year window
and the growth endpoint becomes FY2023's $45.65, so growth turns negative. By my estimate the fair
value falls from $4,556 to roughly $35 and the margin of safety from +0.95 to −1.0 at the next scan,
with no change in the business.

### F4 — No check that earnings per share and price refer to the same share. HIGH, CONFIRMED

- SBSP3.SA above (split, 5.14 times).
- Three names held on 2026-09-22 were secondary share classes valued on the main class's per-share
  earnings. Their entry metrics equal `1 − own price / main-class fair value` almost exactly:
  50GP.L (Croda 5.9% preference share, GBP 49m market cap, entry metric 0.9397; Croda ordinary now
  scores −1.0), UHRN.SW (Swatch registered share, one-fifth of the bearer share; 0.9146 against
  0.525 for UHR.SW), LISP.SW (Lindt participation certificate, one-tenth of the registered share;
  0.8999 against −0.096 for LISN.SW).
- WWIB.OL was held alongside WWI.OL: the same company in two of 30 seats.
- All four are gone from the 2026-11-07 scan, but the global universe pull does not set
  `includeAllShareClasses=false` (only the sp500 region does, line 1425), so nothing stops them
  returning. Across the scan, 34 names with a positive Graham margin show a share count implied by
  market cap that differs from the statement count by more than 1.5 times.
- Fix: compare statement shares times price with market cap; rescale or drop when they differ by
  more than about 1.5 times; exclude preference and secondary lines at the universe build.

### F5 — The cyclical-peak adjustment raises the score when it should lower it. MEDIUM, CONFIRMED

- Line 6936: `1 − (1 − mos) / norm_scale`. When a name is flagged at a peak by the margin test but
  its `norm_scale` is above 1, the score goes up. 28 of 383 peak-flagged Graham qualifiers are in
  that position. GNS.L: 0.753 becomes 0.808. It would still be held this week on the +0.05
  incumbency alone, but on raw score it ranks 153rd in the scan.
- The Graham base is already built on the mid-cycle margin, so peak names with `norm_scale` below 1
  are marked down twice.
- Fix: apply `min(norm_scale, 1.0)`, and skip the second adjustment for Graham.

### F6 — The method is mislabelled; no bond-yield term. MEDIUM, CONFIRMED

- Lines 3008–3017 contain no yield. The local-yield table (98–103) is undated, hand-entered, lacks
  PL, KR, CN and BE (10 picks' countries fall back to the US rate) and is not used here anyway.
- With top-grade yields above 4.4% the missing factor would lower every fair value; for Brazil
  (13.9% in the table) it would cut SBSP3.SA's by about two-thirds.
- Fix: add `4.4 / Y` with a dated, refreshed yield and a sensible clamp, or rename the basket.

### F7 — Structural-break gate looks back 15 years. LOW, CONFIRMED

- Lines 2823–2836 scan every annual report fetched (15 years, line 2128). A share-count jump in
  2012–2014 excludes a name from all earnings-based baskets today (LEG.DE, CQP, VTOL, ALUP3.SA
  among the top 110 by raw score). VTOL left this basket on 2026-09-22 with a higher metric than it
  entered on.
- Fix: limit the look-back to the window the methods use.

### F8 — Variables used before they are set. LOW, CONFIRMED

- Line 2846 uses `shares` and `eps_latest`, which are assigned for this block at lines 2856 and
  2859. The values used come from earlier blocks (lines 2365, 2385, 2514, 2556), which lack the
  basic-share fallback. Usually the same number; fragile.

### Checked and clean

- **Currency.** All 30 picks: price currency, reporting currency and `fx_to_price` are consistent.
  Scan rates match live FMP (USD/NOK 9.45 against 9.56; USD/CNY 6.67 against 6.67; EUR/SEK 11.03
  against 11.08). Pence-quoted UK names carry the factor of 100. No residue of the August bug.
- **Cap.** 9 names in the scan sit at 0.95; 8 are removed by the gates, 1 is a pick (SPB). No ties
  at the cut-off (0.7833); 52 distinct values in the top 60.
- **Selectivity.** 1,882 qualifiers, 924 after gates, 519 above zero, 30 seats. Numerically
  selective; the problem is what it selects on.

## 4. Rotation since 2026-09-22

| Date | Out | Why | In |
|---|---|---|---|
| 09-22 | VTOL (0.80), EVN.VI (0.78), 2382.HK (0.78) | Reconstruction rebalance. VTOL now carries a 2012 structural-break flag. Cause not reproducible | GNS.L (0.78), 2333.HK, 1378.HK |
| 10-19/24 | 50GP.L | Left the scan (preference share, no longer actively trading). Unpriced exit | DVL.WA |
| 10-31 | ALNY (0.94) | Forward-earnings gate. The pick itself was the sign bug (F2). −32% | 012330.KS |
| 11-07 | WWIB.OL, UHRN.SW, LISP.SW | Left the scan (secondary share classes). Unpriced exits | DBC.WA, 2382.HK, 2883.HK |
| 11-07 | GEF (0.80 to 0.035) | New annual report: earnings per share −70%, growth turned negative, multiple fell from 48.5 to 8.5. SUSPECTED a one-off gain rolling off | SSRM |

- Of 9 exits, 1 (GEF) followed a real change in the metric, and that change was the growth cliff.
  4 were tickers disappearing, 1 a gate on an artefact pick, 3 belong to the reconstruction.
- GNS.L entered on 09-22 with a raw metric below all three names that left; consistent with F5.
- 2382.HK left at 0.7825 and came back six weeks later at 0.7938: churn at the margin.
- Incumbency: the 24 names held since 09-22 moved by a median of 0.009. The +0.05 boost is worth
  about 20 rank places here (rank 30 is 0.783, rank 45 is 0.751). It does damp turnover, but it also
  keeps artefact picks in place until the statement that created them rolls off.
- After exit: mean excess return against ACWI +0.4 points (pack figure). No sign that exits were
  costly or well timed.

## 5. What it contributes to the debate

- Grades of the 30 picks: 1 A (0175.HK), 19 B, 10 C. The forensic gate excluded 3; the numeric gate
  rejected or excluded 5.
- The screen's median discount is 83%; the debate's median discount for the same names is 9.6%.
  8 of 28 are at or above the debate's fair value; only 4 show 30% or more.
- The debate's gates caught SBSP3.SA, BYD and INVA. They did not catch SPB, OTEC.OL, GNS.L, MNC.WA,
  VAL or DUE.DE (numeric gate PASS or WARN).
- Seats: 0175.HK (regime) and DUE.DE (regime and value). Both are also in `dcf_fcff` and
  `rd_capitalized_dcf`, so this basket was not their only route in. 0175.HK's low price-to-earnings
  is real (7.6 on flat reported earnings of CNY 1.63). DUE.DE's screen signal is the disposal gain;
  the pack shows its last full debate as 2026-08-24.
- Overlap: 12 of 30 picks are in no other basket; the largest overlaps are 7 names each with
  `earnings_yield_gap` and `rd_capitalized_dcf`. It is a distinct lens — in practice "low
  price-to-earnings with a recent jump in reported earnings", which is also why it attracts one-offs.

## 6. The record

- Tracker NAV 105.19 on 09-22 to 104.70 on 11-07 (−0.5%). My equal-weight rebuild from the daily
  closes gives about 0.0% over the same seven weeks, within half a point; five of seven weeks match
  to 0.2 points or better.
- The 50GP.L vendor series flips between pence and pounds (0.8475, 84.75, 77, 0.77, 74.75). The
  tracker did not book that; it used scan prices 77.5 and 74.75.
- Mean return of current picks since entry +1.5%, +3.4 points over ACWI, 63% beating it (pack).
  Seven weeks is too short to read anything into.

## 7. Fixes, in order

1. Replace the growth input and lower its cap (F1).
2. Rebuild the earnings base on continuing operations, clamp the ratio, remove the fallback (F2, F3).
3. Add a share-count consistency check and exclude secondary share lines (F4).
4. Fix the direction of the peak adjustment and stop applying it twice (F5).
5. Add the bond-yield factor with a dated yield, or rename the basket (F6).
6. Treat any fair value above about three times price as a data flag, not a top rank.
7. Shorten the structural-break look-back (F7); move the two assignments above line 2844 (F8).

## 8. What I could not check

- The scans before 2026-11-07 are not on disk, so the 09-22 and 10-31 selections are judged from the
  logged metrics, not re-run.
- Why WWIB.OL, UHRN.SW and LISP.SW left the 2026-11-07 universe.
- The current top-grade corporate bond yield, so the size of the missing factor in F6 is approximate.
- GEF, GHC, COLR.BR and SSRM statements (suspected only). KGN.WA, JET2.L, UHS and the other "clean"
  names were judged from scan fields, not statements.
- How many scan names besides ALNY hit the two-negatives case: the scan does not store average net
  income.
- A 0.7-point gap between tracker and price rebuild in the week to 11-07.
- Whether the 4 brokers (6099.HK and others) stored as `sector_class: operating` in the scan are
  excluded at selection by the sector fallback; the picks are consistent with that.
- Dividends: the tracker and my rebuild are price-only.
