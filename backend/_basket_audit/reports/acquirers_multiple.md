# Basket audit — `acquirers_multiple` (enterprise value / operating earnings)

Reviewer: independent basket reviewer, 2026-11-13. Data: scan of 2026-11-07, picks and tracking
snapshots of 2026-11-12, live vendor (FMP) spot checks on 2026-11-13.

## 1. Verdict

**UNSOUND.** The ranking number is wrong for every London stock quoted in pence, and 29 of the 30
current picks are there because of a data artefact, not because they are cheap.

The three things that justify it:

1. **Pounds are added to pence.** Market value is in pounds; debt and operating earnings are in
   pence. For a UK stock the multiple comes out roughly 100 times too low. 24 of 30 picks are UK
   pence-quoted names (5% of the scan, 80% of the basket). Rightmove is ranked the cheapest company
   in the world at 0.016 times earnings; its real multiple is 14.8.
2. **Five of the six non-UK picks are also artefacts** (statement years in two different currencies
   averaged together, a vendor field that changes meaning between years, an 11-month-old cash
   balance that has since been paid out, a one-off licence payment).
3. **Rotation is driven by a cliff, not by cheapness.** A name whose enterprise value is just above
   zero is rank 1; just below zero it is thrown out. Every exit since 2026-09-22 was an eligibility
   flip, a gate, or a name missing from the scan. None was a name being out-ranked.

With the unit error corrected, INCH.L (the seat this basket supplied to both books) is still
genuinely cheap on this measure (4.7 times, 71st of 2,731), but it would sit at position 37 on a
fresh ranking, just outside the 30 seats.

## 2. What the rule computes

Code: `backend/screener_v6.py:6615-6637`.

- Enterprise value = vendor market value + net debt (`:6618`). Net debt = total debt minus cash and
  short-term investments from the **latest annual** balance sheet (`:2866-2873`).
- Operating earnings = the **average of the last three annual** "operating income" figures
  (`:2717`), not the latest year and not the last twelve months.
- Multiple = enterprise value / operating earnings. A name qualifies only if both are above zero
  and the multiple is at most 100 (`:6620-6622`). Cheapest first.
- The "margin of safety" is **not a discount to anything**. It is the rank spread onto a line from
  +0.20 (cheapest of 2,693) to −0.20 (dearest): `(0.5 − rank%) × 0.4` (`:6636`). All 30 picks read
  between 0.1927 and 0.2000. The file's `fair_value` is simply price × (1 + that number), i.e.
  price × 1.2 for every pick (`:7039`; Rightmove 555.4 → "666.48").
- Selection then drops banks and insurers (`:891`, `:6894-6899`), names with net debt above three
  times EBITDA (`:6639-6644`), names with a Piotroski score under 3 (`:6928`), names below the
  median (`:6579`), and caps any sector at 9 of 30 (`:6649`). Incumbents get +0.02 (`:6869-6873`).

It is recognisably the Acquirer's Multiple in intent. In execution the units are wrong, the
earnings figure is not protected against peaks, one-offs or mixed data, and the balance sheet can
be a year old against a live price.

I reproduced the basket from the scan: my rebuild matches 29 of 30 picks, the one difference
(ABF.L held instead of CHG.L) being the incumbent boost.

## 3. Findings, most serious first

### F1 — Market value in pounds, debt and earnings in pence. HIGH, CONFIRMED

- `market_cap` is the vendor's figure, untouched (`:1551`, `:5251`). For London stocks it is in
  **pounds**. Live check: RMV.L price 563 (pence), market cap 4,048,540,420 — that is £4.05bn.
- `net_debt` and `ebit` are multiplied by `fx_to_price` (`:2879-2880`), the rate into the *price*
  currency. Since the 2026-08-20 currency fix (commit `1acf48aa`) the price currency of UK stocks
  is pence, so the rate is 100 (or 74.9 for a dollar reporter such as Rio Tinto).
- Line `:6618` then adds pounds to pence and divides by pence.

Rightmove, from the scan row: market value £3,997.5m; net cash £35.7m stored as −3,572.2m;
three-year operating earnings £267.4m stored as 26,741m. Code: (3,997.5 − 3,572.2) / 26,741 =
**0.0159**. Correct: (3,997.5 − 35.7) / 267.4 = **14.8**.

Effect on the whole scan:

| | Pence-quoted UK | Everything else |
|---|---|---|
| Share of the scan | 178 of 3,430 (5%) | 95% |
| Median multiple as computed | 3.2 | 13 to 23 by currency |
| Share of the cheapest 80 | 52 (65%) | 35% |
| Share of the basket | 24 of 30 (80%) | 6 of 30 |

The 24 UK picks with the multiple the code used and the corrected one (rank out of 2,731):

| Pick | As coded | Corrected | Corrected rank | Pick | As coded | Corrected | Corrected rank |
|---|---|---|---|---|---|---|---|
| RMV.L | 0.02 | 14.8 | 996 | SVS.L | 1.36 | 25.4 | 1,960 |
| MONY.L | 0.22 | 9.8 | 426 | CWK.L | 1.37 | 16.0 | 1,155 |
| KLR.L | 0.25 | 10.4 | 479 | RS1.L | 1.46 | 15.7 | 1,116 |
| HOC.L | 0.27 | 15.7 | 1,101 | IAG.L | 1.47 | 6.8 | 167 |
| EDV.L | 0.40 | 14.9 | 1,010 | IMI.L | 1.62 | 19.3 | 1,515 |
| PFD.L | 0.59 | 9.4 | 391 | NXT.L | 1.69 | 17.4 | 1,327 |
| HILS.L | 0.60 | 18.3 | 1,429 | DNLM.L | 1.73 | 9.9 | 432 |
| AUTO.L | 0.63 | 11.9 | 617 | QQ.L | 1.73 | 27.0 | 2,043 |
| RIO.L | 1.01 | 9.8 | 427 | GNS.L | 1.75 | 35.4 | 2,337 |
| DRX.L | 1.05 | 4.8 | 75 | ABF.L | 1.81 | 10.2 | 459 |
| **INCH.L** | 1.07 | **4.7** | **71** | HWDN.L | 1.17 | 14.2 | 920 |
| ANTO.L | 1.31 | 17.8 | 1,367 | BAB.L | 1.34 | 17.4 | 1,313 |

Six of them (HILS.L, ANTO.L, SVS.L, IMI.L, QQ.L, GNS.L) are **dearer than the median stock** in the
scan (median 17.8). Only DRX.L, INCH.L and IAG.L are cheap on the corrected figure.

A second effect of the same error: a UK name with net cash above 1% of its market value gets a
negative enterprise value and is disqualified. 44 UK names are thrown out this way; 42 of them have
a positive real enterprise value (HSBA.L, BKG.L, EZJ.L, CNA.L, JET2.L and others).

**The same error is in the `ev_gp` basket** (`:6549`, same pounds + pence sum): 29 of its 30 picks
are pence-quoted. It also leaks into `convergence`, which takes price × (1 + this rank number) as
one of its fair-value votes (`:6759`, `:6779-6782`).

Fix: put both sides in one unit before adding (scale the vendor market value by 100 for pence,
cents and agorot quotes, or build enterprise value in the reporting currency). Add a test that
Rightmove's multiple is about 15, and a publish-time alarm when one price currency holds a share of
a basket many times its share of the scan.

### F2 — The three-year average mixes currencies and vendor definitions. HIGH, CONFIRMED

One exchange rate, taken from the newest statement (`:2179-2185`), is applied to all three years
that go into the average (`:2717`, `:2880`). Where the vendor's years differ, the average is
nonsense. Verified against live vendor statements:

| Pick | What the vendor holds | Average the code used | Honest figure | Multiple coded → real |
|---|---|---|---|---|
| OKEA.OL | FY2025 in US dollars (218m); FY2024 and FY2023 in kroner (4,963m; 1,316m) | 2,166m treated as dollars = NOK 20.5bn | about NOK 2.1bn (latest) to 2.8bn | 0.24 → about 1.8 to 2.4 |
| SOFF.OL | FY2025, FY2024 in dollars (92.5m; 42.7m); FY2023 in kroner (1,944m) | 693m treated as dollars | about 106m dollars | 1.29 → about 8.4 |
| 0762.HK | "operating income" 190,972m in 2023, then 22,206m and 18,110m (same company, flat pre-tax profit) | 77,096m yuan | about 18,000 to 22,000m | 1.40 → about 5.5 to 6 |
| GSF.OL | 2023 "operating income" 3,379m includes 2,281m of non-operating items; 2024 −96m; 2025 383m | 1,222m | 383m | see F4 |

OKEA is still cheap on the honest figure; Solstad and China Unicom are not top-30 names.

Scale across the scan (proxy only): 45 qualifiers have a three-year average more than three times
their latest year; 61 qualify on a positive average while their latest year is a loss.

Fix: convert each year with its own reported currency (or drop years in a different currency), and
fall back to the latest year when the average is far above it.

### F3 — No protection against peak or one-off earnings. HIGH, CONFIRMED

The code excludes this basket from the peak-earnings adjustment on the grounds that multiples are
"less sensitive" (`:6881-6887`). An earnings multiple is directly proportional to earnings, so it
is fully sensitive.

- ZEAL.CO (entered 2026-11-07): revenue 63m kroner in 2024, 9,215m in 2025 (a licence payment).
  Operating result −572m, −1,272m, +7,156m; average 1,770m. Net cash 14.7bn against a 15.4bn market
  value. Multiple 0.42. This is a research company near cash value with a one-time receipt, not a
  cheap operating business.
- 15 of the 30 picks carry the scan's own PEAK_CYCLE flag, against 24% of all qualifiers.
- With the unit error corrected the problem gets worse, not better: 16 of the 30 corrected picks
  are flagged PEAK_CYCLE and Energy sits at the 9-name sector cap (oil and gas, coal, shipping,
  shipbuilding, autos, eggs). Peabody would qualify on a three-year average 845 times its latest
  year; Corteva on pre-split earnings against a post-split market value.

Fix: scale flagged-peak earnings down by the scan's `norm_scale`, as the six earnings-based methods
already do (`:6932-6936`), and use the lower of latest-year and average earnings.

### F4 — A year-old balance sheet against today's price. MEDIUM, CONFIRMED (one pick)

Net debt comes from the latest **annual** balance sheet. GSF.OL: at 2025-12-31 cash 5,012m kroner,
net cash 2,176m. The vendor's 2026 first-half balance sheet shows cash 232m and net **debt**
1,543m — the sale proceeds were paid out and the share price fell from 78 to 22. The code computes
enterprise value 336m; on the newer balance sheet it is about 4,055m, roughly 10.6 times latest
earnings instead of 0.27. The debate's forensic gate already excluded this name.

The leverage gate reads the same stale figure, so it passed GSF.OL as a net-cash company.

Fix: take net debt from the most recent interim balance sheet.

### F5 — Enterprise value near zero is a cliff. MEDIUM, CONFIRMED

`ev > 0` is required (`:6620`). A name with enterprise value just above zero is the cheapest in the
world; just below zero it is unrankable. Small price moves flip names between rank 1 and out.

- RMV.L (with the pence error): out below about 496p, rank 1 above it. Left on 2026-09-26 at
  440.9p with metric −1.0; back on 2026-10-19 at 536p as rank 1.
- PLX.PA (no pence error; its cash is largely customer float): in at 14.9, out at 11.9 with −1.0,
  two round trips since August.
- SMIN.L, BWY.L, GDWN.L left the same way (metric −1.0).

Fix: do not rank on a near-zero denominator. Either floor enterprise value at a fraction of market
value or treat net-cash-heavy names consistently on both sides of zero.

### F6 — The "margin of safety" and "fair value" are labels on a rank. MEDIUM, CONFIRMED

The basket header shows `average_mos 0.1964`; each pick shows a fair value 20% above its price.
Neither is a valuation. The top is distinguishable (no ties, 60 distinct values in the top 60) but
the number says nothing about how cheap a name is: 0.016 times and 1.8 times both read "0.20".
The debate's own median discount for these picks is 6.3%.

Fix: publish the multiple itself and the rank; stop emitting a fair value for rank baskets; remove
the rank number from the convergence votes.

### F7 — What enterprise value leaves out. LOW to MEDIUM, CONFIRMED in code

- Minority interests, preferred shares and pension deficits are never added (`:6618`). INCH.L has
  £83m of minorities (3% of enterprise value); PNOR.OL $20.5m (18%).
- Leases are included only when the vendor's total debt includes them. For INCH.L it does
  (412 + 509 + 343 leases = 1,264).
- Customer cash counts as free cash (PLX.PA vouchers, JET2.L deposits), which is how such names
  reach the top.
- Missing net debt is treated as zero debt (`s.net_debt or 0.0`), which the sister function
  forbids in its own comment (`:6537-6538`). Only one qualifier is affected today.

### F8 — The tracked return is overstated by exits booked at no change. MEDIUM, CONFIRMED

The tracker is an accurate equal-weight chain: I reproduced each period's change from daily closes.

| Period | Tracker | From closes | Gap |
|---|---|---|---|
| 09-07 → 09-22 | −1.96% | −1.67% | reconstruction period |
| 09-22 → 10-10 | −2.17% | −2.43% | MONY.L, GAMA.L booked at 0% |
| 10-10 → 10-24 | −1.37% | −1.37% | none |
| 10-24 → 11-07 | +1.75% | +1.22% | SQZ.L booked at −0.7%, really −15.8% |

The second row reconciles to the basis point once the two "unpriced" exits are set to 0% and the
09-21 closes are used as the start. Names that vanish from the scan are sold at their last known
price. Since 09-22 that flatters the basket by about 0.8 points (reported −1.8%, real about −2.6%).
This is shared machinery, not specific to this basket.

### F9 — Banks and insurers: excluded at selection, still in the ranking pool. LOW, CONFIRMED

The exclusion works: no financial is in the basket although 26 of the 100 lowest multiples are
banks or insurers. Two loose ends. They are still ranked (`:6617` has no sector filter), which only
shifts the rank number slightly. And the `sector_class` written to the scan uses the industry
string alone (`:2808`) while selection uses the sector as a fallback (`:6894`), so 40 financial
names (Investec, CITIC Securities, Paragon Banking) read "operating" in the scan file although
selection treats them as financial. Anything downstream that trusts the scan field will disagree
with the screen.

### F10 — The leverage gate. Works; one caveat. LOW, CONFIRMED

It compares reported-currency figures with each other (`:6640-6644`), so the pence error does not
touch it. It removes 655 of 2,400 applicable qualifiers. Caveat: it uses the latest year's earnings
while the multiple uses the three-year average, and it inherits the stale balance sheet (F4).

### F11 — The incumbent boost covers four times the basket. LOW, CONFIRMED arithmetic, untested in practice

+0.02 on a ±0.20 scale is 5% of the pool, about 135 rank places. On the corrected ranking an
incumbent would keep its seat down to roughly candidate position 126 of 890 for a 30-seat basket.
It has not mattered yet because no exit since 09-22 was a ranking exit.

## 4. Rotation since 2026-09-22

Picks-file entry dates: 23 on 09-22, 4 on 09-26, one each on 10-19, 10-31, 11-07.

| Date | Out | Why | In |
|---|---|---|---|
| 09-22 (tracker) | 11 names incl. BP.L, IMB.L, CALM, TFI.PA, KARE.AT, JD.L, WPP.L | First rebalance after the rebuild. Their own rank numbers were still 0.18 to 0.19 (top 5%); they were displaced by names ranking higher under the pence error. The starting state is reconstructed, so I cannot attribute further | 11 names, 10 of them UK |
| 09-26 | RMV.L, PLX.PA, SMIN.L | Enterprise value flipped below zero (F5) | PNOR.OL, DNLM.L, QQ.L, GNS.L |
| 10-10 (tracker) | MONY.L, GAMA.L | Missing from the scan ("unpriced") | — |
| 10-03 / 10-24 | VOLCAR-B.ST in, then out | Its three-year average is 31 times its latest year in the current scan. Out after a 24% one-day fall while its rank number was still 0.197, so a gate removed it; its Piotroski score is now 2, below the floor of 3 (inferred, not replayed) | — |
| 10-19 | BWY.L | Enterprise value below zero (pence error) | RMV.L back as rank 1 |
| 10-24 / 10-31 | PLX.PA in, then out | Cliff again; new annual accounts and a 17% fall | MONY.L back in the scan |
| 11-07 | SQZ.L | Missing from the scan | ZEAL.CO (one-off, F3) |

Nine exit events since 09-22 (after the mass change): five are the zero cliff, three are names
missing from the scan, one is a gate. **None is a name becoming less cheap.** Turnover since 09-22
is therefore all noise or data events.

After leaving, the 20 logged exits beat the world index by 5.5 points on average (IMB.L +20%,
JD.L +22%, RMV.L +15%, MONY.L +12%). Leaving this basket has carried no information.

Before the wipe the tracker also held three lines of one company (BP.L plus the preference shares
BP-A.L and BP-B.L, each ranked on BP's group earnings). They are gone from the scan now.

## 5. What it contributes to the debate

- Grades of the 30 picks: 4 A (RIO.L, INCH.L, IMI.L, ZEAL.CO), 20 B, 6 C. The forensic gate
  excluded GSF.OL; the numeric gate rejected HWDN.L.
- 23 of the 30 picks are in no other basket, so it does add names nobody else supplies — but
  mostly as a list of mid-priced UK companies. The debate found little: median discount 6.3%.
- Seat supplied: **INCH.L**, in both books, and from this basket only. Its route in was the pence
  error (1.07 as coded). On honest numbers it is still cheap: 4.7 times on the three-year average,
  about 5.1 on the latest year (£540m), about 5.2 with minorities. Two cautions: the average still
  contains 2023 earnings (£652m) from before the UK retail arm was sold, and the scan flags it
  PEAK_CYCLE. The debate's own 48.7% discount does not depend on the screen's number.
- IMI.L (grade A, corrected multiple 19.3) and RIO.L (grade A, 9.8) are supplied by this basket
  and no other, and would not be on a correct ranking.
- Picks are down 0.07% on average since entry against a world index down about 3%; 60% beat it.
  With 80% of the basket in one market over seven weeks that is a UK-versus-world result, not
  evidence about the method.

## 6. What I could not check

- Anything before 2026-09-22 (rebalance log, exits and daily NAV were lost).
- Whether the vendor's market value is in major units for every non-UK listing. I checked London,
  Oslo and Hong Kong quotes only.
- How many names beyond OKEA.OL and SOFF.OL have statement years in two currencies; the scan keeps
  only the average, so I have a proxy count (45), not a list.
- Why MONY.L, GAMA.L and SQZ.L dropped out of individual scans, and what made ZEAL.CO eligible on
  11-07 rather than earlier.
- I did not run the screener; the corrected ranking is rebuilt from scan fields, without the
  incumbent boost.

## Fixes, in order

1. Make market value, net debt and earnings the same unit (F1); same change in `ev_gp`. Add the
   Rightmove test and a currency-concentration alarm at publish.
2. Convert each statement year in its own currency and distrust an average far above the latest
   year (F2).
3. Apply the peak adjustment and a one-off guard to the earnings figure (F3).
4. Use the latest interim balance sheet for net debt (F4).
5. Remove the zero cliff (F5).
6. Publish the multiple and the rank, not a "margin of safety" or a fair value; drop the rank
   number from the convergence votes (F6).
7. Add minorities and preferred shares to enterprise value (F7).
8. Price exits of vanished names from the daily closes, not at no change (F8, shared machinery).

Artefact picks (29 of 30): the 24 pence-quoted names in the F1 table, plus OKEA.OL, SOFF.OL,
0762.HK, GSF.OL and ZEAL.CO. PNOR.OL is the only pick that is in for the reason the method intends.
