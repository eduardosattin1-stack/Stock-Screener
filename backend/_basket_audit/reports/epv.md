# Basket audit — `epv` (Greenwald earnings power value)

Reviewer scope: `backend/screener_v6.py` 2684-2723 (inputs), 2988-3006 (method), 6859-7103 (selection),
the pack `packs/epv.json`, the 2026-11-07 scan, and 16 live vendor (FMP) spot checks. Read-only.

## 1. Verdict

**UNSOUND as a ranking (fixable).** The formula is coded exactly as documented and the currency
handling is clean, but the inputs it trusts are wrong often enough that the list is not what the
method intends.

1. **10 of the 30 picks are confirmed artefacts and 3 more are suspected**; 6 further picks rest on
   contaminated or overstated inputs. Only 11 show no distortion. The five highest published
   discounts in the basket (UPBD, CNA.L, 0762.HK, SBSP3.SA, KD) all have a confirmed input problem.
2. **The June 2026 change opened a hole.** "EBIT + depreciation − maintenance capital spending"
   treats any depreciation that is not matched by reported capital spending as free cash. Lease
   depreciation, rental-fleet depreciation and capitalised contract costs are not free cash. This is
   what put the value seat **2618.HK** in the basket: its published fair value of HK$17.41 falls to
   HK$6.69 on plain operating profit, against a price of HK$10.76.
3. **11 of the 19 logged exits were data events**, not moves in the metric.

## 2. What the rule computes

In plain words (`screener_v6.py:2997-3006`):

- Take the **three-year average** of operating profit (EBIT), of depreciation and amortisation
  (D&A) and of capital spending (`2716-2720`; zero years are skipped).
- Maintenance spending = capital spending ÷ (1 + last year's revenue growth, clamped 0-100%). If
  capital spending is zero or missing, maintenance spending = D&A.
- Sustainable earnings = EBIT + D&A − maintenance spending, taxed at a flat **21%**, divided by a
  flat **10%** cost of capital. Subtract net debt (total debt − cash and short-term investments,
  latest balance sheet). Divide by the latest fiscal year's diluted weighted share count. Convert
  to the price currency. Margin of safety = (fair value − price) ÷ fair value, capped at −1 / +0.95.

I reproduced the code's figure for 2618.HK to the cent from vendor statements: 3.873bn + 12.659bn −
(6.249bn ÷ 1.1876) = 11.27bn CNY; × 0.79 ÷ 0.10 = 89.0bn; + 5.86bn net cash; ÷ 6.404bn shares =
14.82 CNY × 1.1751 = **HK$17.41** (scan: 17.4136).

Is it the June change as described? **Yes** — line 3000 adds D&A back and subtracts maintenance
spending instead of leaving D&A in. Is it Greenwald? Only partly:

| Point asked | What the code does | Assessment |
|---|---|---|
| Maintenance capital spending | Reported `capitalExpenditure` ÷ (1+growth) | Wrong whenever the real reinvestment is not booked as capital spending — see F1 |
| Margin normalisation | Three-year average EBIT. The 10-year median margin (`2752-2762`) is **not** used in the fair value; it only scales the ranking of names flagged PEAK_CYCLE (`6932-6936`) | Weak — see F8 |
| Cost of capital per country | None. `wacc = 0.10` for every stock (`2935`). The local-yield table at `98-103` is used only by the earnings-yield basket | See F5 |
| Tax | Flat 21% (`3001`) | See F3 |
| Net debt and cash | Total debt (leases included, as the vendor reports it) minus cash and short-term investments. Minority interests, pensions and long-term investments ignored; all cash treated as surplus | See F3, F7 |
| Currency | Statement currency → price currency via rates refreshed at scan start; pence handled | Correct — see below |

**Currency: clean.** For the 11 picks where reporting and price currency differ, the scan's rates
match live quotes within 1% (CNY→HKD 1.1751 vs 1.1757; USD→NOK 9.45 vs 9.56; EUR→SEK 11.03 vs
11.08; pence ×100). No residue of the pre-08-20 dollar bug in this basket.

## 3. Findings

### The 30 picks at a glance

"EBIT-only" = the same formula with maintenance spending set equal to D&A (Greenwald's own default,
and what the code does when capital spending is missing). "Add-back" = share of sustainable
earnings that comes from D&A exceeding maintenance spending.

| Pick | Published discount | Fair value / price | EBIT-only fair value (discount) | Add-back | Status |
|---|---|---|---|---|---|
| UPBD | 0.87 | 183.57 / 24.24 | 0.83 (−1.00) | 86% | **Artefact** F1 |
| CNA.L | 0.80 (ranked at 0.63) | 769 / 151.5 | 763 (0.80) | 1% | Contaminated F4 |
| 0762.HK | 0.80 (ranked at 0.33) | 27.36 / 5.46 | 24.70 (0.78) | 10% | Contaminated F4 |
| SBSP3.SA | 0.77 | 118.55 / 26.78 | 90.98 (0.71) | 17% | **Artefact** F2 |
| KD | 0.73 | 59.27 / 16.29 | 4.40 (−1.00) | 79% | **Artefact** F1 |
| JUN3.DE | 0.61 | 58.29 / 22.58 | 32.88 (0.31) | 45% | No distortion found |
| 000270.KS | 0.60 (ranked at 0.37) | 253,283 / 100,300 | 275,519 (0.64) | −11% | No distortion found |
| 0135.HK | 0.57 | 17.75 / 7.60 | 18.30 (0.59) | −4% | Overstated F3 |
| 1605.T | 0.55 | 7,593 / 3,413 | 6,544 (0.48) | 12% | **Artefact** F3 |
| TFI.PA | 0.54 | 14.03 / 6.46 | 11.07 (0.42) | 25% | No distortion found |
| CEC.DE | 0.53 | 9.60 / 4.53 | 0.79 (−1.00) | 71% | Suspected artefact F1 |
| TEP.PA | 0.53 | 144.28 / 68.44 | 79.65 (0.14) | 31% | Weakened F1 |
| DFH | 0.52 | 26.09 / 12.40 | 25.87 (0.52) | 1% | No distortion found |
| EQNR.OL | 0.52 | 815 / 394.9 | 832 (0.53) | −2% | **Artefact** F3 |
| FAG.ST | 0.50 | 25.62 / 12.80 | 15.34 (0.17) | 25% | Weakened F1 |
| SWON.SW | 0.49 | 17.33 / 8.76 | 14.66 (0.40) | 18% | No distortion found (share count caveat, F2) |
| LIGHT.AS | 0.47 (ranked at 0.38) | 29.18 / 15.44 | 20.02 (0.23) | 25% | Weakened F1 |
| WPP.L | 0.46 | 763 / 408.7 | 378 (−0.08) | 34% | Suspected artefact F1 |
| RENT3.SA | 0.46 | 56.48 / 30.29 | 16.50 (−0.84) | 45% | **Artefact** F1, F5 |
| CDI.PA | 0.45 | 802 / 441.4 | 735 (0.40) | 7% | **Artefact** F3 |
| FGR.PA | 0.44 | 187.69 / 106.0 | 103.13 (−0.03) | 29% | **Artefact** F1, F3 |
| 2333.HK | 0.43 | 11.15 / 6.40 | 13.70 (0.53) | −27% | No distortion found |
| BETS-B.ST | 0.42 | 167.56 / 97.75 | 161.72 (0.40) | 4% | No distortion found |
| 2607.HK | 0.42 | 19.46 / 11.36 | 19.46 (0.42) | 0% | No distortion found (minorities not checked) |
| MMT.PA | 0.41 | 19.11 / 11.30 | 15.38 (0.27) | 20% | No distortion found |
| **2618.HK (value seat)** | 0.38 | 17.41 / 10.76 | 6.69 (−0.61) | 66% | **Artefact** F1 |
| OPM.PA | 0.38 | 15.19 / 9.43 | 12.76 (0.26) | 9% | No distortion found |
| EOLU-B.ST | 0.36 | 78.93 / 50.6 | 76.02 (0.33) | 4% | No distortion found (latest year is a loss) |
| JET2.L | 0.36 | 2,342 / 1,510 | 2,776 (0.46) | −33% | **Artefact** F7 |
| JD.L | 0.35 | 145.77 / 95.34 | 87.11 (−0.09) | 29% | Suspected artefact F1 |

Tally: 10 confirmed artefacts, 3 suspected, 6 contaminated / overstated / weakened, 11 with nothing
found. On an EBIT-only basis 8 picks have no discount at all and 15 fall below the basket's own
cut-off of 0.346.

### F1 — HIGH — Depreciation with no matching capital spending is counted as free cash

**What is wrong.** Line 3000 adds back all D&A and subtracts only reported capital spending. Four
kinds of D&A have a real cash cost that never appears in the capital-spending line:

- **Lease depreciation** under international accounting rules (the lease payment is booked as
  financing). US accounting keeps most lease cost in operating expenses, so the bias falls on
  non-US names.
- **Rental fleets and rental merchandise**, bought through operating cash flow.
- **Capitalised contract and software costs**, also paid through operating cash flow.
- **Concession assets**, booked as intangibles rather than capital spending.

There is also a cliff: capital spending of exactly zero makes maintenance = D&A (earnings = EBIT),
but capital spending of 1 makes earnings ≈ EBIT + all D&A (`2997-2999`). The `capex * 0.7` branch
on line 2999 can never produce a non-zero value.

**Evidence (vendor statements, latest year).**

| Pick | D&A | Capital spending | Where the real spend sits | Fair value: published → EBIT-only |
|---|---|---|---|---|
| UPBD | $1,515m | $67m | $1,457m rental merchandise in "other working capital" | $183.57 → $0.83 |
| KD | $2,775m | $608m | $1,959m in "other working capital" | $59.27 → $4.40 |
| RENT3.SA | R$5.94bn | R$0.31bn | R$4.67bn cars bought through working capital | R$56.48 → R$16.50 |
| 2618.HK | 12.99bn CNY | 7.65bn CNY | 18.0bn lease liabilities, 7.35bn due within a year; 11.9bn "other financing" outflow | HK$17.41 → HK$6.69 |
| SBSP3.SA | R$2.21bn | R$0.29bn | R$13.7bn "investments in property, plant and equipment" not in the capital-spending field | see F2 |

For 2618.HK even generous variants give no discount: latest-year EBIT instead of the average gives
HK$8.50; adding long-term investments and deducting minorities gives HK$10.72 against a price of
HK$10.76.

The bias shows across the scan: median D&A ÷ EBIT is 0.48 for non-US names against 0.31 for US
names; 9.0% of eligible non-US names clear the basket's cut-off against 3.5% of US names; 24 of the
30 picks are non-US (the scan is 53% non-US).

**Picks affected.** Confirmed (statements checked): UPBD, KD, RENT3.SA, 2618.HK, FGR.PA. Suspected
(discount disappears on EBIT-only, statements not checked line by line): CEC.DE, WPP.L, JD.L.
Weakened: TEP.PA, FAG.ST, LIGHT.AS. The same add-back sits in `owner_earnings` (16 shared names).

**Fix.** Do not let the add-back run free. Simplest: sustainable earnings = EBIT (maintenance =
D&A) as the default, and allow an add-back only for amortisation of acquired intangibles when the
vendor separates it. Alternatively cap the add-back (for example at 20% of EBIT) and add a
cross-check: drop the name when three-year free cash flow after lease payments is under half of
the earnings being capitalised. UPBD, KD, RENT3.SA, DFH and EOLU-B.ST all carry a DCF discount of
−1.0 beside an EPV discount of 0.36-0.87; that contradiction is already in the scan row.

### F2 — HIGH — Share count from the last annual statement, never checked against the price

**What is wrong.** Fair value per share divides by the latest fiscal year's weighted diluted shares
(`2856`, `3004`). After a split or large issue the price is on the new count and the fair value on
the old one.

**Evidence.** SBSP3.SA: statements show 684m shares and earnings per share of R$12.37; the live
profile shows a price of R$26.93 and a market value of R$94.7bn, i.e. 3,517m shares (5.14×). The
US-listed line (SBS) trades at $4.84, consistent with the new count. Fair value on the current
count is 118.55 ÷ 5.14 = **R$23.07 against R$26.78** — a discount of −16%, not +77%. The same
stale count feeds its Graham (0.94), owner-earnings (0.86) and DCF (0.73) discounts; it sits in
five baskets. Across the scan, 18 of the 340 names with a positive EPV discount have a market
value more than 1.5× (or under 0.67×) price × statement shares.

**Picks affected.** SBSP3.SA (confirmed). SWON.SW (suspected: 152m statement shares against about
215m implied by market value, after its 2025 acquisition).

**Fix.** Use market value ÷ price as the share count when it differs from the statement count by
more than about 20%, or exclude the name from per-share methods until the next annual statement.

### F3 — HIGH — Flat 21% tax and no deduction for minority shareholders

**What is wrong.** Line 3001 taxes every company at 21%. Lines 3002-3004 give 100% of consolidated
operating profit to the listed company's shareholders.

**Evidence (vendor income statements).**

| Pick | Problem | Published fair value | Corrected | Price | Corrected discount |
|---|---|---|---|---|---|
| EQNR.OL | Tax paid 69-80% of pre-tax profit, three-year mean 73% | 815 NOK | 247 NOK | 394.9 | −60% |
| 1605.T | Tax 63-74%, mean 68% | 7,593 JPY | 2,559 JPY | 3,413 | −33% |
| CDI.PA | Shareholders' profit 4.53bn of 11.17bn total (40.5%): the rest belongs to LVMH's other owners | 802 EUR | 325 EUR | 441.4 | −36% |
| FGR.PA | Shareholders get 70% of profit (and F1 applies) | 187.69 EUR | about 99 EUR | 106.0 | −7% |
| 0135.HK | Shareholders get 63%; tax 27% | 17.75 HKD | 11.21 HKD | 7.60 | +32% (below the cut-off) |

**Picks affected.** Confirmed: EQNR.OL, 1605.T, CDI.PA, FGR.PA, 0135.HK. Not checked: 2607.HK,
OPM.PA, JD.L (all have minorities).

**Fix.** Use each company's own three-year effective tax rate, clamped (for example 15%-80%), and
scale the result by the shareholders' share of profit (`netIncome ÷
netIncomeFromContinuingOperations`).

### F4 — MEDIUM — The vendor's "operating income" field is trusted without a cross-check

**Evidence.** 0762.HK: operating income is 190.97bn CNY for 2023 against EBIT of 24.9bn and pre-tax
profit of 22.9bn in the same row (2022 has the same fault). The three-year average the code uses
is 77.1bn; the true figure is about 19.7bn. CNA.L: 2025 operating income is £5,101m against pre-tax
profit of £112m (a £4,989m charge sits below the line), and the window also holds 2023's £6,512m.
For both, the peak-cycle flag fired and cut the ranking value (0.80 → 0.33 and 0.80 → 0.63), which
masked the error by accident rather than by design. Re-computed on the true EBIT, 0762.HK still
shows about 0.45, so its seat probably survives; CNA.L's true level is unclear.

**Fix.** Before using operating income, compare it with pre-tax profit plus net interest. When
they differ by more than, say, a third, use the smaller or drop the year.

### F5 — MEDIUM — One 10% cost of capital for every country

**Evidence.** `2935`. The code's own table puts the Brazilian 10-year yield at 13.9% (`101`), so
Brazilian earnings are capitalised below the local risk-free rate. At 13.9% + 5% the two Brazilian
picks' fair values fall from R$56.48 to R$14.74 (RENT3.SA) and from R$118.55 to R$43.71 (SBSP3.SA,
before the share-count fix). Japanese and Swiss names are penalised the other way.

**Fix.** Cost of capital = local 10-year yield + a fixed premium, using the existing table (add
KR and CN, which fall back to the US rate today).

### F6 — MEDIUM — Secondary share lines are valued as if they were the ordinary share

**What is wrong.** A preference share or participation certificate inherits the issuer's
statements; fair value per ordinary share is then compared with the price of a different security.

**Evidence.** Five of the basket's holdings until October/November were such lines: 50GP.L
(Croda International 5.9% preference shares, about 75p, discount 0.91), BP-A.L and BP-B.L (BP 8%
and 9% preference shares, 0.80 and 0.76), LISP.SW (Lindt participation certificate, 0.68; the
registered share LISN.SW reads −1.0), 066575.KS (LG Electronics preferred, 0.38; the ordinary
reads −0.23). No rule removed them: they left only because the vendor's screener stopped returning
them (all five are absent from the 11-07 scan). CECV.DE, MCHPP and SMCIP are still in the scan.

On the 50GP.L lead: the vendor price series flips between pounds and pence (0.8475 until 10-05,
84.75, 77, then 0.77 from 10-19 to 11-06, then 74.75) and the profile now shows it as not actively
trading. Seven methods liked it because every per-share method compared Croda's ordinary-share
value with a 75p preference share.

**Fix.** Drop non-ordinary lines at universe build (one line per issuer; reject when market value
÷ price disagrees with statement shares by 3× or more).

### F7 — MEDIUM — Customer prepayments counted as surplus cash

**Evidence.** JET2.L: cash £3,293m, debt £1,280m, so "net cash" of £2,013m — 44% of the published
fair value. The same balance sheet carries £2,142m of deferred revenue (holidays paid for and not
yet taken). Excluding it, fair value is about 1,245p against a price of 1,510p (−21%).

**Fix.** Net customer deposits / deferred revenue against cash, or cap the cash credit.

### F8 — LOW — Margin normalisation is a cliff, and the published number ignores it

- Fair value uses a three-year average, not a through-cycle margin. The 10-year median only acts
  when a name is flagged PEAK_CYCLE (scale under 0.75 or 1.5 standard deviations), so a scale of
  0.76 gets no haircut and 0.74 gets a 26% one (`2771-2774`, `6932-6936`).
- The haircut scales the whole fair value including net cash or debt, not just the earnings part.
- The picks file publishes the raw discount (`7034`, `7061`): CNA.L and 0762.HK show 0.80 while
  ranked at 0.63 and 0.33. The basket's headline average (0.524) is overstated for the same reason.

### F9 — LOW — Gates

- The stored `sector_class` field is computed from the industry string only (`2808`), so brokers
  such as 6886.HK, 8601.T and IBKR read "operating" in the scan. Selection recomputes it with the
  sector (`6894`) and correctly excludes them; the stored field is misleading for any other reader.
- The quality floor (Piotroski score of 3 or more) removed 3 of 998 names. The leverage gate
  removed 47 but uses the same lease-inflated D&A; it passes FAG.ST, UPBD, OPM.PA, RENT3.SA and
  FGR.PA, each with net debt at or above its market value, where a small error in EBIT becomes a
  large error in the discount.

### Selectivity (no finding)

998 names have an EPV figure; 517 pass the gates; 134 have a positive raw discount, 105 a positive
ranking value; 30 seats. The cut-off is 0.346 raw, with no ties and 57 distinct values in the top
60. Only 3 names sit at the 0.95 cap and all are gated out. The cut is meaningful; the problem is
what is being ranked, not how many. My replication of the selection loop from the scan returns the
live 30 exactly.

### Seen in passing (not this basket — please route)

`acquirers_multiple` and `ev_gp` add market value in **pounds** to net debt in **pence** for London
stocks (`6618-6621`: `market_cap` is not converted, `net_debt` and `ebit` are multiplied by 100 at
`2879-2880`). JD.L reads 3.12 against a true 7.94; CNA.L and JET2.L read 999. London supplies 24 of
30 `acquirers_multiple` picks and 29 of 30 `ev_gp` picks, including the seats INCH.L and MGNS.L.

## 4. Rotation since 2026-09-22

Twelve of the current 30 entered after 09-22 (seven weekly scans); 19 exits logged by the tracker over four
rebalances (63% of the basket in under seven weeks). Nine names made a round trip or stayed under
five weeks.

| Exit | Date | What happened | Real? |
|---|---|---|---|
| UPBD | 09-22 | Absent from that scan; back 10-31 with the same metric (0.89). +50.6% while out | Data |
| GYL.OL | 09-22 | Dropped out of the scan universe | Data |
| 2607.HK | 09-22 | Absent from that scan; back four days later | Data |
| EMBRAC-B.ST | 09-22 | Price +14%, metric 0.39 → 0.30 | Real |
| RENT3.SA | 09-22 | Price +17%, metric 0.43 → 0.34; back 10-31 after −26% | Real (on an artefact metric) |
| DFH | 09-26 | Left with metric 0.57, well above the cut-off: a gate, not the metric. Back 11-07. +27.8% while out | Data (gate not identified) |
| FRVIA.PA | 10-10 | Metric 0.58 → 0.06 on a price move of −8% | Data (suspected statement change) |
| KNOW.ST | 10-10 | Metric 0.35 → 0.31, displaced | Real, marginal |
| BBWI | 10-19 | Price +19% | Real |
| CTVA | 10-24 | Entered 10-03 at 0.67, left at −1.0 with the price flat (11.9-12.5) | Data |
| LEN | 10-24 | In two weeks; price +11% | Real |
| 50GP.L | 10-24 | Preference share; vanished | Data |
| GIII, MOH, DRW8.DE | 10-31 | Metrics 0.32-0.34; displaced by UPBD (returning), FAG.ST and RENT3.SA | Real, marginal |
| BP-A.L, BP-B.L, LISP.SW, 066575.KS | 11-07 | Secondary share lines; vanished from the scan | Data |

**11 of 19 exits were data events; 8 were real.** The ten exits logged with `exit_metric: 0.0` and
`unpriced_exit: true` are names missing from the scan on the rebalance day. In the picks file these
exits are not recorded at all (`7000-7002` skips them with a log warning).

Entries: KD entered on 10-24 because its five-year listing clock ran out (`2813`), not because
anything moved. 0762.HK entered on 11-07 on a vendor error (F4), taking the last seat by 0.003 over
MOH. 2618.HK, FAG.ST, RENT3.SA, 2333.HK and OPM.PA entered after real price falls.

Incumbency boost (+0.05): it worked as designed at the margin and was not decisive in any exit I
could trace; the turnover comes from names appearing and disappearing, which the boost cannot damp.

After exit the names beat the world index by 5.5 points on average (pack figure, 50GP.L excluded).
The two largest are data-event exits (UPBD, DFH).

## 5. What it contributes to the debate

- Grades: 5 A, 13 B, 12 C. The debate's gates threw out 10 of 30 (6 forensic, 4 numeric), among
  them four of my confirmed artefacts (KD, SBSP3.SA, EQNR.OL, FGR.PA).
- The screen's discount carries no information for the debate: median 50% on the screen against
  14% in the debate, and a correlation of **0.01** between the two across the 24 picks with a
  debate figure. Five picks have a debate discount at or below zero.
- Four of the five A grades are names I class as artefacts (2618.HK, RENT3.SA, 1605.T, FGR.PA).
  The debate values companies itself, so an A may stand on other grounds; I did not audit that.
- Seat: 2618.HK, also supplied by `dcf_fcff`, `owner_earnings` and `iv15_deep_value`. The screen
  reason for it is the lease add-back (F1).
- Distinctness: 16 of 30 shared with `owner_earnings` (same add-back), 12 with `dcf_fcff`. Eight
  names reach the debate only through this basket: 0135.HK, 1605.T, EQNR.OL, SWON.SW, WPP.L,
  2607.HK, 000270.KS, EOLU-B.ST — three of them flagged above.

## 6. The record

The tracked figure is consistent with prices. Rebuilding the holdings backwards from the rebalance
log and using vendor closes: 10-24 → 11-07 gives +0.88% against a tracked +0.88%; 10-10 → 10-24
gives +2.11% against +2.53% (the gap is mostly 50GP.L's broken price); 09-22 → 10-10 gives −0.9%
against −0.35% (the tracker starts from 09-21 closes). From 09-22 to 11-07 the basket is +3.1%
against −6.1% for the world index. Seven weeks of a non-US value tilt in a falling US market says
nothing about whether the EPV ranking works.

Entry prices in the picks file for the 18 names dated 09-22 are 09-21 closes; the tracker keeps
older entries (SBSP3.SA: 08-21 at 23.31). The two files disagree on entry date and price for those
names — a matter for the machinery review.

## 7. Fixes, most important first

1. **Stop the free add-back (F1).** Default to EBIT; allow an add-back only for acquired-intangible
   amortisation, or cap it and require free cash flow to confirm. Removes UPBD, KD, RENT3.SA,
   2618.HK, CEC.DE, WPP.L, JD.L, FGR.PA from the top 30 on today's scan. Apply the same to
   `owner_earnings`.
2. **Company tax rate and shareholders' share of profit (F3).** Removes EQNR.OL, 1605.T, CDI.PA.
3. **Reconcile the share count with market value ÷ price (F2).** Removes SBSP3.SA.
4. **One line per issuer; drop preference shares and certificates (F6).** Would have kept 5 of 30
   holdings out through October.
5. **Cross-check operating income against pre-tax profit (F4).**
6. **Country cost of capital from the existing yield table (F5).**
7. **Net customer deposits against cash (F7).**
8. **Rotation:** do not exit a holding because it is missing from one scan; carry it one week and
   record which gate removed a name. Would have avoided at least the UPBD, 2607.HK and DFH round
   trips.
9. **Normalise every name on its long-run margin** (earnings part only) and publish the number
   that was ranked (F8).

## 8. What I could not check

- Anything before 2026-09-22, and the six weekly scans between 09-22 and 11-07 (only the 11-07 scan
  is on disk). So I could not identify which gate removed DFH, why UPBD and 2607.HK were missing on
  09-22, or what changed in FRVIA.PA's statements.
- The lease share of D&A for CEC.DE, WPP.L, JD.L, TEP.PA, FAG.ST and LIGHT.AS (vendor statements do
  not split it); those are marked suspected or weakened, not confirmed.
- Whether SWON.SW's share count is stale, and minorities at 2607.HK, OPM.PA and JD.L.
- Whether the debate's own 39.4% discount for 2618.HK leans on the screen's fair value.
- CTVA's corporate action (inferred from the tracker's own log: +0.67 → −1.0 at a flat price).
