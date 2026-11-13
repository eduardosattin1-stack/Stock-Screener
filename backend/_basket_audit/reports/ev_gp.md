# Basket audit — `ev_gp` (enterprise value / gross profit, cheapest first)

Reviewer: independent, read-only. Scan 2026-11-07, picks and tracker snapshots of 2026-11-12,
the eight dated weekly scans 2026-09-22 … 2026-11-07 (read from GCS, nothing written).

## 1. Verdict

**UNSOUND.** The basket is not ranking on enterprise value to gross profit. It is ranking UK-listed
companies on a number that mixes pounds and pence.

1. **Pounds-against-pence error in the enterprise value.** For every London stock quoted in pence,
   market capitalisation is in pounds while net debt and gross profit are in pence (100 times
   larger). 29 of the 30 picks are such stocks. With the units put right, 4 of the 30 would still be
   picked and 7 sit in the *expensive* half of the market.
2. **Every exit since the rebuild is a data event.** All three names that left since 2026-09-22
   left because they dropped out of the weekly scan (market cap slipped under the 1bn universe
   floor), not because the multiple moved. None was logged in the picks file.
3. **The record is flattered.** Two of those three were booked at a 0% final-period return although
   they had fallen 12% and 10%. The tracker shows −2.38% since 2026-09-22; the picks actually did
   −3.15%.

## 2. What the rule computes

`_rank_ev_gp` (`screener_v6.py:6533-6560`): for every stock with positive gross profit and positive
market cap, `ev_gp = (market_cap + net_debt) / gross_profit`. Names are sorted cheapest first and
given `ev_gp_mos = (0.5 − rank_fraction) × 0.4`, so the cheapest name gets +0.20, the median 0 and
the dearest −0.20.

The selection loop (`:6875-6978`) then drops banks and insurers (`:892`, via the sector fallback in
`_sector_class`, `:875`), names with net debt above 3× EBITDA or a Piotroski score below 3
(`:6928`), adds +0.02 to names already held (`:6869-6873`), keeps only names above zero (`:6563`),
and takes the top 30 with at most 9 per sector (`:6646-6659`).

**What the "margin of safety" is.** It is not a discount to any value. It is the rank, rescaled.
One rank place is worth 0.000126. All 30 picks sit between 0.1891 and 0.1999, so the file's
`average_mos` of 0.1923 only says "these are in the cheapest 3%". The `fair_value` written for each
pick is `price × (1 + mos)` (`:7039`), i.e. price plus 19 to 20% for every pick — an invented
figure, not a valuation.

**Inputs.** `market_cap` is the vendor quote field, used raw (`:1551`, `:5251`). `net_debt` is
total debt minus cash and short-term investments from the latest annual balance sheet, multiplied
by `fx_to_price` (`:2866-2879`). `gross_profit` is the latest annual figure times `fx_to_price`
(`:2882`). `fx_to_price` converts the reporting currency into the *price* currency (`:2185`).

## 3. Findings

### F1 — HIGH — CONFIRMED — market cap in pounds, net debt and gross profit in pence

**What is wrong.** Since the currency fix of 2026-08-20 (commit `1acf48aa`, `:2166-2170`) the price
currency of a London stock is read as `GBp` (pence), so `fx_to_price` for a company reporting in
pounds is 100 (`:191`, `:2185`). Net debt and gross profit are therefore stored in pence
(`:2879`, `:2882`). The vendor's market cap for the same stock is in pounds and is never rescaled
(`:1551`). `_rank_ev_gp` adds the two (`:6549`).

The result for a UK stock is `EV/GP ≈ net debt / gross profit + (market cap / gross profit) / 100`.
The market cap almost vanishes. Any UK company whose net cash exceeds 1% of its market cap gets a
*negative* enterprise value and lands at the very top of the list.

**Evidence.**

- Unit test across the whole scan: market cap divided by the market cap implied by the scan's own
  price-to-sales and revenue. Median ratio by price currency: USD 0.99, EUR 1.00, SEK 1.00,
  HKD 1.00, JPY 0.99, CHF 1.00 … **GBp 0.0098** (178 names, 10th–90th percentile 0.0090–0.0103).
  Every pence-quoted name is off by 100; no other currency is off.
- Live check, MGNS.L: quote price 4,552 (pence), market cap 2,158,459,895 (pounds: 4,552p × about
  47.4m shares); profile currency `GBp`; balance sheet in GBP with net debt −£457.6m. The scan holds
  net debt −4.58e10 and gross profit 6.12e10, i.e. the pound figures × 100.
  Scan: (2.06e9 − 4.58e10) / 6.12e10 = **−0.71**. Correct: (2,060 − 458) / 612 = **2.62**.
- UK pence-quoted names are 178 of 3,430 scan names (5%) but 48 of the 88 cheapest, 47 of the 87
  negative-EV names, and **29 of the 30 picks**. Median EV/GP of those 178 names: 0.69 as stored,
  5.77 corrected (rest of the market: 7.30). Truly negative EV among them: 2, not 47.
- I rebuilt the selection from the scan fields and reproduced the live basket exactly (30 of 30,
  and the three rotations since 2026-09-22). Running the same selection on corrected units gives a
  basket that shares **4 names** with the live one (WISE.L, 9927.HK, CNA.L, JET2.L); with the
  incumbency boost applied, 6.

**Picks affected: 29 of 30** (all but 9927.HK), sorted by where they really rank:

| Pick | Industry | Gross margin | Net cash / market cap | EV/GP in scan | Rank in scan | EV/GP corrected | Corrected rank (of 3,183) | Debate grade | Debate discount |
|---|---|---|---|---|---|---|---|---|---|
| WISE.L | IT services (payments) | 58% | 298% | −20.41 | 2 | −13.61 | 3 | A | 19.2% |
| 9927.HK | Auto manufacturer | 29% | 137% | −0.47 | 61 | −0.47 | 35 | B | 11.6% |
| CNA.L | Independent power | 39% | 21% | −0.18 | 76 | 0.72 | 80 | C | 5.6% |
| JET2.L | Travel | 12% | 75% | −2.29 | 21 | 0.77 | 84 | B | 13.9% |
| HBR.L | Oil & gas E&P | 40% | 9% | −0.10 | 81 | 1.18 | 117 | B | −21.4% |
| CKN.L | Shipbroking | 93% | 29% | −0.68 | 53 | 1.70 | 202 | B | 2.8% |
| **MGNS.L** | Construction | 12% | 22% | −0.71 | 52 | 2.62 | 376 | B | 14.1% |
| EZJ.L | Airline | 17% | 12% | −0.32 | 66 | 2.66 | 386 | C | −4.3% |
| FOUR.L | Advertising | 32% | 8% | −0.25 | 70 | 3.39 | 572 | C | −9.6% |
| KIE.L | Construction | 8% | 4% | −0.12 | 80 | 3.66 | 648 | B | −1.7% |
| CCC.L | IT services | 12% | 9% | −0.33 | 65 | 3.87 | 699 | B | −12.9% |
| TW.L | Housebuilder | 17% | 11% | −0.42 | 63 | 3.92 | 708 | B | 10.0% |
| BTRW.L | Housebuilder | 14% | 16% | −0.78 | 48 | 4.37 | 842 | B | 2.2% |
| BWY.L | Housebuilder | 16% | 11% | −0.53 | 56 | 4.53 | 891 | B | 15.7% |
| BKG.L | Housebuilder | 25% | 11% | −0.55 | 54 | 4.94 | 1,009 | B | 14.6% |
| SCT.L | IT services | 31% | 5% | −0.21 | 73 | 5.24 | 1,092 | A | 24.4% |
| OXIG.L | Instruments | 54% | 5% | −0.22 | 72 | 5.56 | 1,190 | A | 30.1% |
| BYIT.L | IT services | 74% | 10% | −0.53 | 55 | 5.58 | 1,201 | B | 11.3% |
| TRST.L | Software | 78% | 2% | −0.08 | 84 | 6.37 | 1,402 | B | 11.3% |
| RSW.L | Machinery | 59% | 8% | −0.50 | 59 | 6.51 | 1,441 | B | 12.5% |
| PSN.L | Housebuilder | 16% | 2% | −0.09 | 82 | 6.64 | 1,466 | B | −3.4% |
| KNOS.L | Software | 46% | 5% | −0.31 | 67 | 6.75 | 1,492 | B | −11.4% |
| BBY.L | Construction | 5% | 21% | −1.76 | 27 | 6.92 | 1,524 | B | 3.3% |
| FEVR.L | Beverages | 33% | 9% | −0.72 | 51 | 8.63 | 1,877 | B | −8.9% |
| RMV.L | Internet | 100% | 1% | 0.01 | 88 | 9.32 | 1,980 | B | 3.5% |
| ROR.L | Machinery | 49% | 2% | −0.07 | 85 | 10.32 | 2,130 | C | 2.0% |
| GAW.L | Leisure | 73% | 2% | −0.15 | 78 | 10.85 | 2,188 | B | 2.6% |
| ONT.L | Biotech | 61% | 11% | −1.42 | 37 | 13.23 | 2,418 | B | −2.8% |
| RR.L | Aerospace | 28% | 2% | −0.20 | 74 | 17.24 | 2,687 | B | 11.0% |
| GDWN.L | Machinery | 48% | 1% | −0.06 | 86 | 32.82 | 3,026 | C | −0.6% |

Seven picks (FEVR, RMV, ROR, GAW, ONT, RR, GDWN) are dearer than the market median on the true
multiple. GDWN.L, at 32.8× gross profit, is in the most expensive 5%.

**What the basket really selects today:** UK companies with any net cash at all. That is a
balance-sheet filter restricted to one exchange, not a valuation screen.

**The same line is wrong in a second basket.** The acquirer's multiple builds enterprise value the
same way (`:6618`). A UK net-cash company gets EV ≤ 0 there and is thrown out (`:6620`) — MGNS.L
and WISE.L both carry `acquirers_multiple = 999`. 47 UK names have EV ≤ 0 as stored; the true
count is 2. UK names with net debt get an EV/EBIT of roughly net debt / EBIT. That is
for the `acquirers_multiple` reviewer, but one fix covers both.

**Fix.** Build enterprise value in one unit. Either rescale the quote's market cap into the price
currency's minor unit when that currency is `GBp`, `ZAc` or `ILA` (×100), or keep net debt and gross
profit in the major unit for the multiple. Do it in one helper used by both `:6549` and `:6618`.
Add a guard that runs every scan: market cap ÷ (price-to-sales × revenue) must lie between 0.5 and
2 for a name to enter an enterprise-value ranking; fail loudly per currency when the median leaves
that band. Expect about 26 of 30 seats to change on the first run after the fix — record it as a
method change, not as rotation.

### F2 — HIGH — CONFIRMED — rotation is driven by names dropping out of the scan, and is not logged

**What is wrong.** A held name that is missing from the week's scan is silently dropped from the
basket. The picks-file code then refuses to record the exit (`:6999-7002`, "exit not recorded").

**Evidence.** Replaying the selection on each weekly scan from the 2026-09-22 holdings reproduces
the live history exactly:

| Scan | Out | Why | In |
|---|---|---|---|
| 09-26, 10-03, 10-10, 10-19 | — | — | — |
| 10-24 | MPE.L | absent from scan (market cap 1.00e9 on 10-19, then price −6%) | FEVR.L |
| 10-31 | PTEC.L | absent from scan (1.04e9 on 10-24, price −4.5%); back on 11-07 at rank 90 | BWY.L |
| 11-07 | RPI.L | absent from scan (1.03e9 on 10-31, price −7%) | TRST.L |

All three still trade (closes through 2026-11-12 in the price cache). The smallest market cap in
every weekly scan is 1.00e9: the universe is built with `marketCapMoreThan = 1_000_000_000`
(`:1288`, `:1411`), and for London that field is in pounds. A held name that dips under £1bn
disappears; if it recovers it returns without its incumbency and is not re-seated (PTEC.L, rank 90,
would have kept its seat easily had it been in the 10-31 scan). Four current picks sit within 10%
of the floor: FEVR.L, BYIT.L, TRST.L (1.01e9 each) and GDWN.L (1.09e9). FEVR.L and TRST.L only
entered the scan on 10-19.

Not one exit since 2026-09-22 was caused by the multiple moving. The stored metric barely moves at
all: across the eight scans the largest change for any current pick is 0.0135 (BWY.L, a new annual
report); the next largest is 0.0017.

**Why the picks file shows 0 exits and the tracker 17.** 14 of the tracker's 17 are dated
2026-09-22: the tracker compared the reconstructed 2026-09-07 holdings with the first post-rebuild
picks. The picks file had no previous version to compare with on that day (its entry dates were all
reset to 09-22 — 27 picks carry that date, while the tracker dates 15 of the same holdings to
August), so it logged nothing. The other 3 are the names above: absent from the scan, so the
picks-file path skipped them, while the tracker books an absent name at its last known price and
flags it `unpriced_exit` (`:6338-6343`). `fundamental_momentum` aside, `ev_gp` is the only basket
with an empty exits list for this reason: its only exits are disappearances.

**Fix (shared code, flag to the machinery reviewer).** A held name missing from the scan should be
kept and re-priced from the daily close, or exited with a logged, priced record — never dropped
silently. Give held names a lower universe floor than new names so a 5% price move does not eject
them.

### F3 — MEDIUM — CONFIRMED — the tracked return is overstated

**What is wrong.** When a held name is absent from the scan on a rebalance day the tracker marks it
at its period-start price, a 0% contribution (`:6304-6311`). In this basket a name is absent
precisely because its price fell.

**Evidence.** Recomputing the three rebalance periods from scan prices with that rule gives −0.77%,
−1.83% and +0.21%, chaining to **−2.38%** — exactly the NAV path 103.72 → 102.92 → 101.04 → 101.25.
Using daily closes for all 30 holdings gives −0.81%, −2.24%, −0.12%, chaining to **−3.15%**. The
gap is two names: MPE.L booked at 0% for 10-10 → 10-24 (really −12.3%) and RPI.L booked at 0% for
10-24 → 11-07 (really −9.9%).

So the arithmetic is a correct equal-weight chain, but 0.77 points of loss in seven weeks were not
booked, and the direction of the error is systematic. The published year-to-date of +1.25% also
includes +3.72% carried in from the reconstruction, which cannot be checked.

**Fix.** Mark absent holdings at the last daily close, not at the period-start price.

### F4 — MEDIUM — CONFIRMED — cash that belongs to customers or suppliers counts as net cash

**What is wrong.** Net debt is total debt minus all cash (`:2866-2873`). Banks and insurers are
excluded for this reason (`:888-892`), but companies outside the Financial Services sector that
hold other people's money are not.

**Evidence.**
- WISE.L: cash and short-term investments £24.5bn against £23.3bn of "other non-current
  liabilities" (customer balances) and £0.37bn of debt. Own net cash is under £1bn; the scan uses
  £24.1bn, three times the market cap. It ranks 2nd as stored and 3rd after the unit fix. On own
  cash its multiple is roughly 6×, about the market median.
- 9927.HK (Seres): cash CNY 87.5bn against CNY 85.1bn of payables; net cash 137% of market cap.
  The formula is applied correctly, but the "cheapness" is supplier credit.

**Picks affected: 2** (WISE.L, 9927.HK). **Fix.** Make negative enterprise value ineligible, as the
acquirer's multiple already does (`:6620`), or cap net cash at a fraction of market cap.

### F5 — MEDIUM — CONFIRMED in the data, not yet biting the live basket — gross profit is not comparable

**The question asked: do low-margin businesses (distributors, contractors, retailers) dominate
because gross profit is not comparable?** Today, no. The live basket does hold 5 housebuilders,
3 contractors and 2 airlines with gross margins of 5–25%, but they are there because they are UK
companies with net cash (F1), not because of their margins. After the unit fix the evidence points
the other way:

| Gross margin band | Share of all eligible operating names | Share of the 100 cheapest (corrected) | Median EV/GP |
|---|---|---|---|
| under 15% | 14.7% | 10% | 8.95 |
| 15–30% | 25.8% | 21% | 6.99 |
| 30–50% | 28.5% | 28% | 6.93 |
| 50–90% | 27.7% | 27% | 7.90 |
| 90% and over | 3.4% | **14%** | 7.92 |

(2,787 names that pass the sector rule; units corrected.) Rank correlation between gross margin and
EV/GP rank is −0.02: no margin tilt overall. The real distortion is at the top end. 35 of those
names have a stored gross margin of 99.9% or more,
because the vendor's `grossProfit` equals revenue for them. Live check, VEI.OL (Veidekke, a
contractor): revenue 43,143m, cost of revenue 41,168m, `grossProfit` 43,143m. Its EV/GP is stored
as 0.59; on revenue minus cost of revenue it would be about 13. In the corrected basket 7 of 30
names carry a stored gross margin of 85–100% in businesses where that is implausible (contractors
VEI.OL, NRC.OL, BONHR.OL, MULTI.OL; freight broker HUBG; hospital operator UHS; POL.OL) — only
VEI.OL was checked live, the other six are SUSPECTED. CEC.DE and CECV.DE (two share classes of one
company) would both be seated.

**Fix.** Use revenue minus cost of revenue when the vendor's gross profit equals revenue; make a
name ineligible when cost of revenue is missing; keep one line per company.

### F6 — LOW — CONFIRMED — the incumbency boost is wider than the basket

The boost is 0.02 (`:6869-6873`). The 30 seats span 0.0104 of metric. One rank place is 0.000126,
so the boost is worth 159 rank places: a held name keeps its seat until it falls from the top 30
eligible names to about the 130th (overall rank about 245 of 3,182). Without the boost only 2 of
30 seats would differ today, so it is doing no harm now, but it means the basket cannot rotate on
valuation at all; combined with F2, disappearance from the scan is the only way out.

### F7 — LOW — CONFIRMED — the "missing balance sheet" guard cannot fire

`_rank_ev_gp` treats `net_debt is None` as ineligible (`:6548`), but the field defaults to 0.0
(`:1097`, `:2112`) and no scan row holds None. A name without a balance sheet would be ranked as
debt-free. One qualifier has net debt of exactly zero today (105560.KS, a bank, excluded anyway),
so the exposure is small.

### F8 — LOW — CONFIRMED — the stored `sector_class` disagrees with the one used for selection

Brokers such as 6886.HK, 8601.T and FTK.DE carry `sector_class: "operating"` in the scan file, yet
the selection excludes them through the sector fallback (`:875`). Selection is right; the stored
field is misleading for anyone reading the scan (it misled my first replication).

## 4. Rotation since 2026-09-22

- 2026-09-22: 14 in, 14 out in the tracker — the first post-rebuild basket against the
  reconstructed 09-07 holdings. The 14 that left have since returned +7.4% on average (median
  +8.4%); the 12 of their replacements still held have returned −1.2% over the same window.
  SUSPECTED cause of that swap: the 100× form of the unit error dates from the 2026-08-20 currency
  fix, after which UK net-cash names leapt up the ranking. The exits' metrics are consistent with
  that (non-UK names YELP, TDOC, CECV.DE fell roughly 85–140 rank places between August and 09-22), but the
  pre-rebuild scans are gone and I could not reproduce it.
- 09-26 to 10-19: no changes in four scans.
- 10-24, 10-31, 11-07: one out and one in each week; all three exits are scan disappearances (F2).
- Turnover caused by the multiple actually changing: none.
- After exit: MPE.L −0.7%, RPI.L +6.0%, PTEC.L −0.4% to 2026-11-12.

## 5. What it contributes to the debate

- 24 of the 30 picks are in no other basket. They are in the debate universe only because of this
  screen, and so because of F1. Overlap with others: 4 with the gross-profitability basket, 2 with
  EPV, 1 each with DCF, Graham, IV15 and the acquirer's multiple.
- Debate grades: 3 A, 22 B, 5 C. Numeric gate: 7 pass, 22 warn, 1 reject (FOUR.L). Value
  conviction: one 4, fourteen 3, thirteen 2, two 1.
- The screen says "about 19% margin of safety" for every pick; the debate's own median discount is
  3.4%, and 10 of the 30 are judged to trade above fair value. The debate is not finding the
  cheapness the screen claims — as expected, since the claim is a rank on a wrong number.
- Seats: none in the regime book, one in the value book — **MGNS.L**. It is in no other basket, so
  it reached the debate through this screen alone, on a stored multiple of −0.71 (rank 52). Its true
  multiple is 2.62 (rank 376 of 3,183; corrected EV/EBIT 9.2, rank 369 of 2,731), outside the 30
  seats of either enterprise-value basket. The seat itself rests on the debate's own work (grade B,
  value conviction 4, numeric gate pass, discount 14.1%), which I did not audit.
- As a lens it is distinct from the other eleven, but what makes it distinct today is the error.

## 6. What I could not check

- Anything before 2026-09-22: the earlier scans, rebalance log and NAV are gone. The +3.72% carried
  into the tracker and the cause of the 09-22 swap are unverified.
- Whether the vendor's market cap is in the major unit for the other minor-unit currencies
  (`ZAc`, `ILA`): no such names are in the scan. The fix should cover them anyway.
- The universe floor as the cause of the three disappearances is inferred from the last in-scan
  market caps, the price moves and the screener parameter; I did not call the vendor screener.
- Seres' share count and price history (the 52-week high is four times the current price).
- The debate's valuation of any pick, including MGNS.L.
- Live spot checks made: quotes for MGNS.L, WISE.L, 9927.HK, GDWN.L, RMV.L, HBR.L; profile for
  MGNS.L; balance sheets for MGNS.L, WISE.L, 9927.HK; income statement for VEI.OL.
