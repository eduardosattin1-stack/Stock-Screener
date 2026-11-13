# Basket audit — `rd_capitalized_dcf` (R&D-capitalised DCF)

Reviewer: independent basket reviewer, 2026-11-13. Scan audited: 2026-11-07 (3,430 names). Picks file and tracker: GCS snapshot of 2026-11-12.

## 1. Verdict

**UNSOUND.** The formula does not capitalise research spending; it adds 80% of it straight back to profit, and at least 10 of the 30 picks sit in the basket because of a data artefact or a one-off gain.

The three things that most justify it:

1. **The amortisation charge is wrong by construction** (`screener_v6.py:2952`). It subtracts one fifth of *this year's* R&D instead of the amortisation of the research built up over the previous five years. For a company that spends a steady amount, the correct adjustment is roughly zero; the code's adjustment is +80% of R&D, every year, for ever. The basket is therefore a screen for "R&D spend that is large next to the market value", not for undervalued research. Strip the add-back out and about 17 of the 30 picks lose their seat.
2. **Four picks are confirmed data errors** (8035.T, GMAB.CO, NOD.OL, IT) and **six more rest on a one-off profit** inside the three-year average (PTEC.L, SOLB.BR, SPB, LYFT, BYD, DUE.DE).
3. **The size of the discount carries no information.** Median discount on the screen is 70%; the debate's own median discount for the same names is 18%, and the rank correlation between the two across the picks is −0.03. The debate's gates threw out 11 of the 30.

## 2. What the rule computes

In plain words (`screener_v6.py:2951-2966`, inputs at `2716`, `2722`, `2851-2856`):

- Take the three-year average of net income and the three-year average of reported R&D expense (years with a zero are skipped, `2698-2702`).
- "Adjusted profit" = net income + R&D − R&D/5, i.e. **net income + 0.8 × R&D**.
- "Adjusted equity" = book equity + 2.5 × R&D. Growth = 40% of adjusted profit ÷ adjusted equity, floored at 3% and capped at 20%.
- Grow adjusted profit for seven years (growth fading 10% a year), add a terminal value at 2.5% growth, discount everything at a flat 10%, divide by the diluted share count of the latest annual report, convert to the price currency with one exchange rate.
- Margin of safety = (fair value − price) ÷ fair value, capped to −1.0 … +0.95.

Net effect: fair value is between 13.3 and 25.2 times "net income + 0.8 × R&D" (13.3× at the growth floor, 17.4× at 10% growth, 25.2× at the cap — computed from the code's own loop).

It is **not** the method it claims to be. Capitalising R&D (the Damodaran adjustment) means: add back this year's R&D, then subtract the amortisation of the research asset, which is the sum of the last N years' R&D divided by N. The code subtracts only the first-year slice of the current vintage. That is correct for a company in its first year of doing research and for no one else.

Other points on the rule:

- No tax effect on the add-back: pre-tax R&D is added to after-tax net income (`2952`).
- `adj_assets` (`2953`) is computed and never used.
- No debt is deducted. That is consistent (it values net income, which is after interest), but it means this is an equity-earnings discount model, not a free-cash-flow DCF.
- The same flat 10% discount rate and 2.5% terminal growth are used for every country; the local-yield table at `98-110` is not used here.
- Gates that apply (`6885-6936`): operating companies only, no structural break, at least 5 years of history, forward earnings not falling 25% or more, net debt under 3× EBITDA, Piotroski score of 3 or more, peak-cycle names ranked on a scaled-down discount, a 30% sector cap, and a +0.05 bonus for names already held. I re-ran these gates on the scan and reproduced the 30 published picks exactly, so the gates do what the code says.

I reproduced the fair value itself from the local statement cache (`backend/fmp_cache`) for 2,044 scan names; 1,796 match the scan to within 2% (the cache is older than the scan, which explains the rest). The formula reading above is therefore CONFIRMED, not inferred.

## 3. Findings, most serious first

### F1 — The "amortisation" is one fifth of the current year, so 80% of R&D is counted as profit. HIGH, CONFIRMED

Evidence: `screener_v6.py:2952` `adj_net_income = net_income + rd_expense - (rd_expense / 5.0)`.

What it does to the picks. "No-R&D discount" below is the discount the same formula gives with the add-back removed (which is close to what a correct schedule gives for a steady spender). The cut-off for a seat is about 0.60.

| Pick | Share of adjusted profit that is the add-back | Discount in scan | Discount without add-back | Rank without add-back (cached universe) |
|---|---|---|---|---|
| NOD.OL | 104% (net income is negative) | 0.72 | fair value below zero | 704 |
| FR.PA | 90% | 0.89 | −0.04 | 200 |
| 0763.HK | 70% | 0.80 | 0.23 | 109 |
| DRW3.DE | 68% | 0.67 | about −0.15 to −0.03 | n/a (live data) |
| KWS.DE | 61% | 0.68 | about 0.05 to 0.16 | n/a (live data) |
| KTN.VI | 55% | 0.67 | about 0.12 to 0.22 | n/a (live data) |
| GMAB.CO | 54% | 0.85 | see F3 | 116 |
| HUSQ-B.ST | 53% | 0.65 | 0.19 | 123 |
| 9888.HK | 52% | 0.62 | 0.17 | 130 |
| OPM.PA | 51% | 0.74 | 0.42 | 46 |
| IT | 47% | 0.70 | 0.43 | 42 |
| DUE.DE | 46% | 0.70 | 0.42 | 48 |
| LIGHT.AS | 45% | 0.73 | 0.47 | 61 |
| FAG.ST | 44% | 0.77 | about 0.58 to 0.63 | n/a (live data) |
| 0175.HK | 43% | 0.64 | 0.33 | 73 |
| 2333.HK | 41% | 0.83 | 0.67 | 7 |
| VC | 34% | 0.75 | 0.60 | 45 |
| HPQ | 31% | 0.74 | 0.29 | 85 |
| 6690.HK | 31% | 0.60 | 0.39 | 58 |

FR.PA (Valeo) is the clearest case: R&D of €2.0–2.3bn a year against net income of about €0.2bn. The basket's fair value is €102 a share; every other method in the scan puts it between €2.6 and €10.0 with the share at €10.96.

Scale across the scan: for operating companies where all five earnings methods give a positive value, this method's fair value is a median 1.25× the median of the other four, more than 1.5× for 34% of names and more than 2× for 16%.

Affects: about 17 picks would lose their seat without the add-back — FR.PA, 0763.HK, DRW3.DE, KWS.DE, KTN.VI, HUSQ-B.ST, 9888.HK, OPM.PA, IT, DUE.DE, LIGHT.AS, 0175.HK, HPQ, 6690.HK, plus NOD.OL, GMAB.CO and VC (VC falls to rank 45 once its peak-cycle scaling is applied). Of the 23 picks with cached statements, 9 stay in a no-add-back top 30 (SPB, 2333.HK, BYD, CMCSA, DFH, LYFT, 8035.T, BETS-B.ST, SLVM); of the 7 without cached statements, SOLB.BR, PTEC.L, PROX.BR and FAG.ST would probably stay because their add-back is small or their plain discount is high.

Fix: build the research asset properly. With N = 5: amortisation in year t = (R&D of years t−1 … t−5) ÷ 5; research asset = unamortised remainder of those five years; adjusted profit = net income + (R&D of year t − amortisation) × (1 − tax rate). The scan already holds up to 15 years of statements, so the inputs exist. Use per-year values, not an average that skips zeros.

Fairness note: for a company whose R&D is growing fast the correct add-back is genuinely large. 0175.HK (Geely) is the example — R&D went 7.8 → 10.4 → 17.6bn CNY in three years, so a proper schedule still adds back most of the latest year's increase.

### F2 — Share count not checked against the price: 8035.T is valued on a share count 4.9× too small. HIGH, CONFIRMED

Evidence: `screener_v6.py:2856` takes `weightedAverageShsOutDil` from the latest annual statement (459.2m for the year to March 2026, checked live). The scan price is ¥8,263 and the scan market value ¥18.70trn, which implies 2,264m shares. Live quote on 2026-11-13: ¥9,595, market value ¥21.72trn, same ratio. Earnings per share in the statement (¥1,250.9) against that price would be a price-earnings ratio of under 8 for Tokyo Electron, while market value ÷ net income is 33 (scan) to 38 (live).

Consequence: every per-share fair value for 8035.T is 4.93× too high. Reported: fair value ¥26,419, discount 0.69. On the market-implied share count: fair value ¥5,360 against a price of ¥8,263, i.e. the price is 54% above it. The name entered the basket on 2026-11-07.

The cause is most likely a 5-for-1 share split that the price series reflects and the vendor's statement share count does not (SUSPECTED — I confirmed the mismatch, not the corporate action).

Scan-wide: 54 of 2,432 names with cached statements have statement shares × price outside 0.5×–2× of the scan market value. 8035.T is the only current pick among them.

Affects: 1 pick (8035.T). Also every other per-share method for the same name.

Fix: before dividing, compare the statement share count with market value ÷ price. If they differ by more than 1.5×, use the market-implied count, or drop the name from the per-share methods and log it.

### F3 — Years reported in different currencies are averaged as if they were one currency: GMAB.CO. HIGH, CONFIRMED

Evidence: `screener_v6.py:2181-2185` reads one `reportedCurrency` (the latest year's) and one exchange rate; `2716` and `2722` then average three years. Genmab's cached statements are DKK for 2023 and 2024 and USD for 2025: net income 4,352m DKK, 7,844m DKK, 999m USD; R&D 7,630m DKK, 9,748m DKK, 1,618m USD. The code averages these to 4,398m and 6,332m, treats both as dollars and multiplies by 6.7078.

Consequence: reported fair value 23,276 DKK, discount 0.85 (rank 20 in the scan). With the two DKK years converted to dollars first: fair value about 3,600 DKK against a price of 3,527, discount about 0.02. The peak-cycle flag on the name (scale 0.379) is produced by the same mixed average, so the "protection" that cut its ranking discount to 0.60 is an accident.

Scan-wide: 10 names have mixed currencies inside the three-year window (2259.HK, DOFG.OL, GALD.SW, GMAB.CO, HUT, NIQ, NSIS-B.CO, OKEA.OL, PETR3.SA, SOFF.OL). DOFG.OL and SOFF.OL rank 5th and 13th in the raw scan and are kept out only by the structural-break gate. PETR3.SA sits at 0.58, just under the cut-off.

Affects: 1 pick (GMAB.CO). It was also held from 2026-08-21 and rose from 2,141 to 3,527, so one artefact name supplied roughly 2 percentage points of the basket's tracked return.

Fix: convert each year at its own reported currency, or drop years whose currency differs from the latest year.

### F4 — A one-off profit inside the three-year average of net income. HIGH, CONFIRMED

Evidence: `screener_v6.py:2716` averages `netIncome`, which includes discontinued operations and one-time gains. Statement lines (cache and live):

| Pick | Net income, three years (m) | What the outlier is | Effect |
|---|---|---|---|
| PTEC.L | 105, −24, 1,457 (EUR) | 2025 includes 1,624 from discontinued operations; continuing operations lost money in all three years (−12, −137, −166) | Fair value 3,503p vs price 364p. No value on continuing earnings |
| SOLB.BR | 2,093, 223, 30 (EUR) | 2023 includes 2,130 from discontinued operations (the split of the group) | Fair value €193 vs price €24. On continuing earnings about €10 |
| SPB | 1,802, 125, 100 (USD) | FY2023 includes 2,035 from discontinued operations | Fair value $545 vs price $87 |
| LYFT | −340, 23, 2,844 (USD) | 2025: pre-tax result −53, tax line −2,897 (a tax credit) | Fair value $53 vs price $17. Pre-tax results for the three years were −332, +25, −53, so there is no profit to value without the credit |
| BYD | 620, 578, 1,843 (USD) | 2025 pre-tax 2,330 against operating income 877: a non-operating gain | Fair value $271 vs price $77; at about 600 a year roughly $155, a discount near 0.5 and under the cut-off |
| DUE.DE | 112, 102, 204 (EUR) | 2025 includes 256 from discontinued operations, 2024 includes 40; continuing operations 110, 62, −50 | See section 5 |

KWS.DE has a smaller case (96m from discontinued operations in the year to June 2025).

Affects: 6 picks materially (PTEC.L, SOLB.BR, SPB, LYFT, BYD, DUE.DE). PTEC.L, SOLB.BR and SPB are ranks 3, 2 and 4 of the selection. All of them will leave when the outlier year rolls out of the three-year window, which is a data event, not a change in the business.

Fix: use `netIncomeFromContinuingOperations` (already in the vendor payload) and take the median of the three years instead of the mean. Both changes together remove all six cases.

### F5 — The R&D field itself is unreliable and the average skips zero years. HIGH, CONFIRMED

Evidence: `_avg_field` (`2698-2702`) drops zero values before averaging, so a single year with a number becomes "the three-year level".

| Pick | R&D by year (m) | Problem | Effect |
|---|---|---|---|
| NOD.OL | 2023: 147, 2024: 1,673, 2025: 0 (USD, live) | The 2024 figure is 3.3× that year's revenue of 511 — a unit or currency error at the vendor. Average of the non-zero years = 910 | Fair value 601 NOK (reproduced exactly from the live data). With R&D at 150 a year: 78 NOK vs price 169.6. Other methods give −9 to +10 NOK |
| IT | 2023: 0, 2024: 0, 2025: 1,047 (USD) | R&D appears in one year only; 2011–2024 show zero except 35 in 2021 | Fair value $627 vs $334 without it. Discount 0.70 → 0.43, below the cut-off |
| KTN.VI | 196, 11, 267 (EUR, live) | 2024 figure is 20× smaller than its neighbours | Level is a guess |
| KWS.DE | 326, 349, 0 (EUR, live) | Newest year missing | Averages two years |
| DUE.DE | 166, 128, 0 (and 36 in 2022) | Newest year missing, 2022 implausibly low | Averages two years |
| 2333.HK, HUSQ-B.ST, FAG.ST | one zero year each | Missing year | Averages two years |

Scan-wide: of 1,283 names with any R&D in the three-year window, 321 (25%) have at least one zero year and 55 have a more than 3× spread between non-zero years. Because the add-back is multiplied by 13–25, a vendor filling in or blanking one year moves fair value by a large step. This is the rotation risk for this basket: names will enter and leave when the vendor edits a field.

Affects: 2 picks are outright artefacts (NOD.OL, IT); 6 more carry a patched average.

Fix: require R&D in at least four of the last five years to treat a company as an R&D company; reject any year where R&D exceeds revenue or is more than 3× the median of the other years; never let one year stand in for the average.

### F6 — For companies with no R&D the method is a plain net-income model and a near-copy of `owner_earnings`, not of `dcf_fcff`. MEDIUM, CONFIRMED

Evidence: with `rd_expense = 0` lines `2952-2956` reduce to net income, book equity and return on equity. Of the gate-passing names with cached statements, 288 of 779 (37%) report no R&D at all.

Among those no-R&D names the rank correlation of this method's discount is 0.81 with `owner_earnings`, 0.59 with `dcf_fcff`, 0.53 with `epv`, 0.16 with `graham_revised`. So the specific worry in my assignment (collapse into the plain DCF) is not what happens: it uses net income, not free cash flow, and deducts no debt. It collapses into owner earnings.

In the current basket: CMCSA, DFH, SLVM and PROX.BR have zero R&D; SPB, BYD, SOLB.BR and BETS-B.ST have an add-back of 11% or less. Six of those eight are also in the `owner_earnings` basket. Whole-basket overlap: 9 names with `owner_earnings`, 7 with `graham_revised`, 6 each with `dcf_fcff`, `epv` and `earnings_yield_gap`; 14 names are in no other basket.

Fix: give a no-R&D company −1.0 on this method so the basket only ever holds companies the adjustment is about. The no-R&D names are already covered by `owner_earnings`.

### F7 — Thin or negative book equity pushes growth to the 20% cap. MEDIUM, CONFIRMED

Evidence: `2955-2956`. HPQ has negative book equity after buy-backs. Without R&D, adjusted equity is negative, return is set to 0 and growth is the 3% floor. Adding 2.5 × R&D turns equity slightly positive, return on it becomes very large and growth jumps to the 20% cap. So the add-back raises HPQ's growth assumption from 3% to 20% as well as its profit. IT is at the cap for the same reason. 42 of 779 gate-passing names are at the cap and 59 at the floor.

Affects: HPQ, IT.

Fix: when adjusted equity is under, say, two years of adjusted profit, use the floor growth rate; consider lowering the cap to 10% for a seven-year fade.

### F8 — The inflated fair value also votes in the `convergence` basket. MEDIUM, CONFIRMED (code), effect not measured

Evidence: `screener_v6.py:6757` lists `rd_capitalized_dcf` among the fair values whose median is the consensus. A value that runs a median 25% above the other earnings methods, and more than double for one name in six, shifts that median and the "agreement" share.

Fix: leave it out of the consensus until F1 is fixed.

### F9 — Record: exits with no price are booked flat, which flatters the tracked return. MEDIUM, CONFIRMED (shared machinery)

Evidence: I rebuilt the holdings for each tracker period from the rebalance log and priced them from `_px_cache`.

| Period | Equal-weight return on vendor closes (excl. 50GP.L) | Tracker NAV change | Gap |
|---|---|---|---|
| 09-07 → 09-22 | −2.42% | −2.89% | −0.47 pt |
| 09-22 → 10-10 | −2.71% | −1.88% | +0.83 pt |
| 10-10 → 10-24 | +0.13% | +0.29% | +0.15 pt |
| 10-24 → 11-07 | +0.79% | +1.29% | +0.50 pt |

The gaps come from the eight "unpriced" exits. On 11-07 five names (LISP.SW, UHRN.SW, DRW8.DE, 066575.KS, TRIP) were booked out at their 10-24 price; their real moves were +2.8%, +7.7%, +6.0%, −5.7% and −25.6%. DFH was booked out on 10-10 at 11.40 when the close was 9.38.

Since the 09-22 rebuild the tracker shows −0.3%; the same holdings on vendor closes made about −1.8%. The gap is 1.5 points in seven weeks. The headline +6.84% year to date mostly pre-dates the rebuild and cannot be checked.

Fix: belongs to the machinery review — price an exit from the daily close when the scan has no row.

### F10 — Share-class lines were held as if they were the company. LOW now, CONFIRMED (already gone)

Evidence: the basket held 50GP.L from 08-21 to 10-24 at the capped discount of 0.95. The vendor profile shows it is Croda International's 5.9% preference share, quoted around 75p and not actively trading; the method divided Croda's whole-company profit by the ordinary share count and compared it with a 75p preference share. LISP.SW (Lindt participation certificate, one tenth of a registered share) was held at a discount of 0.82 while the registered line LISN.SW shows −0.98 in the scan; UHRN.SW (Swatch registered, one fifth of the bearer share) at 0.79 while UHR.SW shows −0.19. DRW8.DE and DRW3.DE (the two Drägerwerk lines) were held together from 10-24 to 11-07, so the company took two seats.

All of these are absent from the 2026-11-07 scan, so a clean-up of secondary lines has evidently landed. Nothing of this kind remains in the 30 picks.

### F11 — Currency handling for the picks is otherwise clean. No finding

Every pick's price currency, reporting currency and rate are consistent: PTEC.L EUR→pence 83.49, NOD.OL USD→NOK 9.45, BETS-B.ST EUR→SEK 11.03, GMAB.CO USD→DKK 6.71, the six Hong Kong lines CNY→HKD 1.1751 (live rate checked: 1.1755), FAG.ST and HUSQ-B.ST report in SEK (rate 1.0, checked live for FAG.ST). There is no residue of the old "everything is dollars" bug. The only currency error is the mixed-year case in F3.

### F12 — The stored `sector_class` field labels all utilities "operating". LOW, CONFIRMED

All 104 Utilities names in the scan carry `sector_class: operating` and `methodology_applicable: true`, yet the selection excludes them (my replication matches the published picks only when utilities are removed; five would otherwise hold seats). Selection is right, the stored label is wrong (`2808` classifies from the industry text alone, `6894` from the stock object). Anyone reading the scan field will be misled.

## 4. Selectivity

- 2,105 names have a value above −1.0 in the scan; 990 are above zero.
- After the gates and excluding utilities, about 1,075 remain, about 460 above zero. 30 seats, so the basket takes roughly the top 7% of real candidates. It is not taking everything that qualifies.
- No ties: 58 distinct values in the top 60, and only 2 names in the whole scan at the 0.95 cap (both gated out). The cap is not doing the ranking.
- The cut-off is thin, though. Seat 30 (GMAB.CO) has a ranking value of 0.600; the first name out (NOVO-B.CO) has 0.598. Ranks 10 to 40 span 0.74 to 0.59. At a discount of 0.6, a 5% price move shifts the value by 0.02, so the bottom third of the basket turns on ordinary weekly price noise. The +0.05 bonus for held names (worth about a 12% price move) is what holds it together.
- Ten of the top 12 names by raw value are removed by the gates (leverage, structural break, sector class). The gates are doing most of the cleaning at the top of the list.
- Consumer Cyclical holds 9 seats, the sector maximum; nobody was actually displaced by the cap this week.

## 5. Rotation since 2026-09-22

Picks file (weekly): 14 new entry dates in seven scans — 2 on 09-26, 1 on 10-10, 3 on 10-19, 1 on 10-24, 1 on 10-31, 6 on 11-07. That is 47% of the seats in seven weeks.

| Entry | Date | Why |
|---|---|---|
| KWS.DE, PROX.BR | 09-26 | Round trip. Dropped at the 09-22 rebuild with values of 0.61–0.63, back four days later |
| DRW3.DE, KTN.VI | 10-19 | Round trip. Same story, back within four weeks |
| DFH | 11-07 | Round trip. Left on 09-26 with a value of 0.74, well above the cut-off, so a gate or a missing row removed it, not the metric. Back on 11-07 at 0.72 |
| GMAB.CO | 11-07 | Round trip. Left 10-31 after the share rose 73%, back a week later when it slipped 10%. The fair value is the F3 artefact throughout |
| PTEC.L | 11-07 | The tracker shows it held since 08-21; the picks file gives it a new entry date. It dropped out of one scan and returned. Cause not recoverable |
| 8035.T, 9888.HK, 6690.HK | 11-07 | Filled seats vacated by five names that vanished from the scan. 8035.T is the F2 artefact; the other two are the last two seats |
| SLVM, BETS-B.ST, 0175.HK, VC | 10-10 to 10-31 | Ordinary entries on the metric |

So 7 of the 14 entries are round trips and 3 more exist only because other names disappeared.

Tracker exits (16 logged):

| Group | Names | Count |
|---|---|---|
| Name missing from the scan, exit booked with no price and `exit_metric: 0.0` | 50GP.L, TXT.WA, LISP.SW, UHRN.SW, DRW8.DE, 066575.KS, TRIP | 7 |
| Gate or missing row, metric still high | DFH | 1 |
| Dropped at the 09-22 rebuild at 0.61–0.63, all back since | DRW3.DE, PROX.BR, KTN.VI, KWS.DE | 4 |
| Price rose, discount shrank — a real reason | AFX.DE (+10% in its last period), WKL.AS (+11% since entry), BBWI (+24%), IMB.L (+15%) | 4 |

Only 4 of 16 exits happened because the metric genuinely moved. Those four behaved as intended: winners that had become less cheap, and they kept rising afterwards (+3% to +19%). The four round trips at the rebuild are consistent with the held-name bonus not applying on 09-22 because there were no previous picks to load (SUSPECTED). The pack's "mean excess after exit +3.0%" is not meaningful: it includes 50GP.L's broken price series.

## 6. What it contributes to the debate

- Grades of the 30 picks: 3 A, 18 B, 9 C. Forensic gate excluded 8 (0763.HK, FAG.ST, IT, LIGHT.AS, KTN.VI, DFH, BETS-B.ST, 9888.HK); numeric gate rejected or excluded 3 (2333.HK, BYD, KWS.DE). 11 of 30 thrown out.
- Screen discount against the debate's: median 70% against 18%; rank correlation −0.03 across the 23 picks with a debate figure. The four largest screen discounts (PTEC.L, FR.PA, SOLB.BR, SPB) get 35%, 10%, 7% and 6% from the debate. The debate is ignoring this number, correctly.
- 14 picks reach the debate through no other basket: 0763.HK, 8035.T, 9888.HK, DRW3.DE, FR.PA, GMAB.CO, HPQ, HUSQ-B.ST, IT, KTN.VI, KWS.DE, NOD.OL, SLVM, VC. Their grades: 1 A (GMAB.CO), 10 B, 3 C. Four of them are confirmed data artefacts (8035.T, GMAB.CO, NOD.OL, IT) and most of the rest are add-back cases. None holds a seat. The distinct contribution of this basket is therefore debate time, not seats.
- Seats: 0175.HK (regime book) and DUE.DE (regime and value books). Both are also in `dcf_fcff` and `graham_revised`, so neither depended on this basket to be seen.
  - **0175.HK**: discount 0.64 here, 0.33 without the add-back. R&D is growing fast, so a correct schedule would still add a good part of it back. `dcf_fcff` independently shows 0.66. Reasonable name to surface; the size of the discount is overstated.
  - **DUE.DE**: discount 0.70 here. Two things hold it up: the add-back (46% of adjusted profit; 0.42 without it) and 296m EUR of discontinued-operations profit in 2024–2025 (continuing operations were +110, +62, −50). On continuing profit with the code's add-back the discount is 0.48, under the cut-off; on continuing profit with no add-back the fair value is about €8 against a price of €16.10. The debate's own discount is 48% and it flags the name as peak-earnings, so the seat rests on the debate's work and not on this figure — but the screen's number for the one name in the real-money book that this basket supplied is not trustworthy. The R&D field for 2025 is also blank at the vendor.

## 7. Fixes, most important first

1. **Compute the research asset and its amortisation properly** (F1): per-year R&D for five prior years, straight-line; adjusted profit = net income + (R&D − amortisation) × (1 − tax). Evidence: about 17 picks lose their seat when the 80% add-back is removed.
2. **Check the share count against market value ÷ price** before any per-share division (F2). Evidence: 8035.T valued 4.9× too high; 54 names scan-wide out of range.
3. **Use continuing-operations net income and the median of three years** (F4). Evidence: PTEC.L, SOLB.BR, SPB, LYFT, BYD, DUE.DE.
4. **Convert each statement year at its own currency** (F3). Evidence: GMAB.CO 23,276 DKK reported against about 3,600; 10 names scan-wide.
5. **Validate the R&D field** (F5): four of five years present, no year above revenue or above 3× the others. Evidence: NOD.OL, IT; 25% of R&D names have a blank year.
6. **Give no-R&D companies no value on this method** (F6), so the basket is a distinct lens and not a second owner-earnings list.
7. **Stop thin equity from forcing the growth cap** (F7). Evidence: HPQ 3% → 20%.
8. **Leave this fair value out of the convergence vote until 1–5 are done** (F8).
9. Until then, treat this basket's ranking as unreliable as a feed. Its picks that no other basket supplies have produced no seat.

## 8. What I could not check

- Anything before the 2026-09-22 rebuild, including the +6.84% year-to-date figure and the ten earlier rebalances.
- The weekly scans between 09-22 and 10-31 are not on disk, so I could not see which gate removed DFH on 09-26 or why PTEC.L received a new entry date on 11-07.
- The local statement cache dates from May to August 2026 and has no file for SOLB.BR, PTEC.L, FAG.ST, KWS.DE, KTN.VI, DRW3.DE or PROX.BR. I pulled their income statements live, but not their balance sheets, so the "without add-back" figures for those names are ranges, not exact.
- Whether the 8035.T mismatch is a share split. The 4.93× ratio and the price range fit one; I did not find the corporate action itself.
- Whether Gartner (IT) really spent 1,047m on R&D in 2025. Whatever the answer, one reported year should not stand for three.
- A full re-ranking of the scan under a correct five-year schedule. The cache holds only five annual rows for many names, so the "about 17 of 30 lose their seat" figure uses the simpler no-add-back version on the 71% of the scan that has cached statements (fewer competitors than the real scan, so if anything it understates the losses).
- The effect of this method's fair value on which names qualify for `convergence` (F8) — code path confirmed, impact not measured.
- Companies that already capitalise development costs under IFRS (Valeo, Geely, Kontron, Dürr): adding back the expensed part on top may double-count. SUSPECTED, not tested.

Live data checks used: 12 calls (one batch quote for five names, one currency rate, one profile, income statements for nine names).
