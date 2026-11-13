# Basket audit — `iv15_deep_value`

Reviewer: independent basket reviewer. Scan dated 2026-11-07, picks and tracking files as of 2026-11-12.
Everything marked CONFIRMED was reproduced from the code, the scan, the local statement cache
(`backend/fmp_cache/`), the price cache or a live vendor call. SUSPECTED means plausible, not reproduced.

## 1. Verdict

**UNSOUND as a ranking method — the basket's membership is decided by its gates (mainly "the zero-growth
method must also say cheap"), not by the IV15 number, and that number is a 15-year extrapolation of the
last three years' growth that cannot be trusted.**

The three things that most justify it:

1. **The fair value is a trailing-growth multiplier, not a deep-value measure.** Fair value = (3-year average
   free cash flow per share) × K, where K runs from 1.3 to 37.9 depending only on the last three years'
   revenue-per-share growth. Across the scan the typical company grew 6% a year on that measure; among the
   names IV15 calls cheap the typical figure is 18.8%, and 44% of them sit at the 20% cap. The top pick
   (2333.HK) gets a fair value 11.7 times its price.
2. **There is no selection.** After the gates only 17 names in a 3,430-name scan have a positive score; the
   sector cap cuts that to 14. Every qualifier gets a seat. The ranking, the saturation cap and the incumbency
   boost decide exactly one seat today.
3. **The +19.6% is real prices but not evidence.** The chain since 2026-09-07 reconciles to actual closes
   (−3.1% over that stretch). The whole gain was made before then by a book of two to ten stocks; my
   reconstruction puts about 60% of it in June, when the basket held roughly two names.

## 2. What the rule computes

Code: `backend/screener_v6.py:3019-3040`, growth input at `:2898-2918`, selection at `:6915-6957`.

In plain words: take the company's free cash flow (operating cash flow minus capital spending), averaged over
the last three years (`:2721`). Grow it for 15 years at the rate its **revenue per share** grew over the last
three years, floored at 2% and capped at 20% (`:2909-2917`, `:3022`). Value the year-15 cash flow at a multiple
equal to twice the growth rate in percent, between 8 and 20 times (`:3023`). Discount that back at 15% a year
(`:3029`), divide by today's share count, convert to the price currency. Margin of safety (MoS) = 1 − price /
fair value, clamped to −1.0 … +0.95 (`:3034`).

Because everything is proportional to the starting cash flow, the whole method collapses to
**fair value = K(g) × average FCF per share**:

| Growth input g | Terminal multiple | K (fair value as a multiple of FCF per share) |
|---|---|---|
| ≤ 4% | 8 | 1.3 – 1.8 |
| 5% | 10 | 2.6 |
| 8% | 16 | 6.2 |
| 10% | 20 | 10.3 |
| 14% | 20 | 17.5 |
| 17.8% | 20 | 28.7 |
| 19.6% | 20 | 35.9 |
| ≥ 20% (cap) | 20 | 37.9 |

Then the gates (`:6893-6928`): operating companies only (no banks, insurers, REITs, utilities); at least five
years of statements and no structural break; consensus forward earnings not falling 25% or more;
`iv15_nogrowth_agreement` — the EPV method (a zero-growth valuation) must also show MoS > 0; net debt under 3×
EBITDA; Piotroski score of at least 3. Names flagged `iv15_saturated` (growth input ≥ 20%, or MoS at the 0.95
clamp) have their MoS cut to 0.50 and are ordered among themselves by EPV MoS (`:6919-6921`, `:6949-6952`).
Peak-cycle names are ranked on a margin-normalised MoS (`:6932-6936`). Top 30 by that score, at most 30% per
sector.

**Is the arithmetic right?** Yes. CONFIRMED: I recomputed the fair value from the cached statements for 11 of
the 14 picks and six other names (recent exits and 0175.HK) and matched the scan to the cent in 15 of 17 cases
(INVA and CMCSA differ by 2–6% because the cache predates a newer statement). Example, 2333.HK: revenue per share 15.12 → 25.84 CNY
(2022 → 2025) = 19.56% a year; average FCF 15.14bn CNY; K = 35.9; 63.8 CNY × 1.175 = HK$74.95, exactly the scan
value. Currency handling is clean for all 14 picks (GBp ×100 for JET2.L, CNY→HKD 1.175 for the three mainland
names, USD→HKD 7.84 for 1208.HK, EUR→SEK 11.03 for BETS-B.ST). No residue of the pre-08-20 currency bug.

**Is it the method it claims to be?** No. It is described as projecting per-share *earnings*; it projects
*free cash flow* at the growth rate of *revenue per share*. The code comment (`:2898-2908`) is honest about
that. The label "deep value" is not: see finding 1.

## 3. Findings, most serious first

### F1 — HIGH, CONFIRMED. The growth input is not trustworthy, and it dominates the result

What is wrong: one number — three-year revenue-per-share growth — sets both the 15-year compounding rate and
the terminal multiple, so the fair value moves 29-fold between the floor and the cap. A margin of safety above
zero is, in practice, a statement that the company grew fast recently.

Evidence:

- Distribution of the growth input, recomputed from the local statement cache (cache dates May–August 2026,
  so approximate; 2,350 scan names covered):

  | Group | Names | Median growth | Share at ≥ 20% | Share under 10% |
  |---|---|---|---|---|
  | Whole scan | 2,350 | 6.0% | 12.7% | 66.5% |
  | Fair value above half the price | 550 | 15.7% | 30.9% | 18.9% |
  | IV15 MoS > 0 | 293 | 18.8% | 44.0% | 9.9% |

  The scan itself agrees: 424 names carry `iv15_saturated`, including 210 of the 445 with IV15 MoS > 0 (47%).
- Buybacks are extrapolated as growth. Per-share growth against plain revenue growth: EEFT 13.9% vs 8.1%,
  MOH 17.8% vs 12.4%, INVA 13.0% vs 8.7%, 2333.HK 19.6% vs 17.0%; recent exits TNET 11.0% vs 0.9%, WEX 12.1% vs
  4.2%, CMCSA 7.5% vs 0.6%. TriNet's revenue was flat, and the method assumed 11% a year for 15 years at a 20×
  exit because the share count fell.
- The base year is 2022 for most names, a trough for China, travel and post-pandemic recoveries, and the
  window ends after an inflationary period. A three-year endpoint rate is not a 15-year rate.
- Outputs that follow: 2333.HK fair value 11.7× price, JET2.L 7.8×, HRMY 5.1× (a one-product drug company
  assumed to grow 20% a year until 2040), MOH "26% margin of safety" at 21 times its average free cash flow
  with the latest year's cash flow negative (−$636m).
- The debate does not believe these numbers: median screen MoS of the picks 53%, median debate discount 17.6%.

Affects: all 14 picks (10 of the 12 I could recompute have g > 10% and therefore the maximum 20× multiple).

Fix: cap the growth input far lower (8–10%) and fade it; use the lower of revenue growth and per-share
growth; use a longer window (median of rolling rates over 5–7 years); fix the terminal multiple (10–12×)
instead of tying it to trailing growth. Expect the number of qualifiers to fall further — that is the honest
answer for a 15% hurdle.

### F2 — HIGH, CONFIRMED. No selectivity: 17 qualifiers for 30 seats

Funnel reproduced from the scan (the function that decides financial/operating in the selection loop is the
object form, `:837-877`):

| Step | Names left |
|---|---|
| Scan | 3,430 |
| IV15 computed (fair value above half the price) | 796 |
| IV15 MoS > 0 | 445 |
| …and EPV MoS > 0 (`iv15_nogrowth_agreement`) | 107 |
| …and operating company, no structural break, forward earnings gate, leverage, Piotroski | 20 |
| …and rank score > 0 after the peak-cycle adjustment | 17 |
| After the 30%-per-sector cap | 14 |

Seven of the 17 are Consumer Cyclical; the cap allows four at a basket size of 14 (`:6649`), so 0175.HK,
000270.KS and JD.L are cut. The lowest pick (1208.HK) has MoS 0.107 and entered at 0.0026. The "cut-off" is
simply zero. Ranking only matters inside the sector cap.

The basket is therefore a list: *EPV-cheap operating companies whose recent growth is high enough for IV15 to
agree*. The EPV gate does the value work; IV15 contributes the growth filter of F1.

Fix: publish it as what it is (a gated list with however many names qualify) or repair F1 so the score can
rank. Do not read the seat count or the average MoS (0.539) as signal.

### F3 — HIGH, CONFIRMED on the numbers, SUSPECTED on the cause. The cash-flow base is not owner cash flow for several picks

The method needs cash that belongs to shareholders. The vendor's `freeCashFlow` is operating cash flow minus
capital spending. Under IFRS 16 the repayment of lease liabilities sits in financing, so lease-heavy non-US
companies show free cash flow far above earnings; consolidated cash flow also includes minority partners'
share. US lease payments stay in operating cash flow, so the bias favours non-US names (10 of 14 picks).

| Pick | Avg FCF ÷ avg net income (3y) | What inflates it |
|---|---|---|
| 1208.HK | 4.6 | Consolidated FCF $1.05bn vs attributable profit $227m (minority partners in the main mine) |
| MMB.PA | ~4.6 | FCF €980m vs profit €203m; D&A €832m vs capex €255m; "other financing" outflow €710m (lease repayments, not itemised by the vendor) |
| FGR.PA | 2.9 | Concession amortisation, minorities, leases; other financing −€842m |
| 2618.HK | 2.8 | FCF 11.1bn vs profit 6.9bn CNY; other financing −11.9bn with no dividends or buybacks |
| TEP.PA | 2.4 | D&A 3.1× capex; leases and acquired intangibles |
| 2333.HK | 1.5 | 2025 FCF 28.3bn CNY of which 20.0bn is a working-capital release; 2023 was 1.0bn, 2022 −4.0bn |
| MOH | 0.5 | Health insurer; premium timing; FCF 1,578 → 544 → −636 ($m) |

JET2.L (customer deposits, aircraft leases) is probably in the same group; no cached statements to confirm.

Affects: 7 of 14 picks, including the value seat 2618.HK.

Fix: subtract lease principal repayments where the vendor provides them, or cap the cash-flow base at a
multiple of net income (say 1.5×); use the parent's share where minorities are material.

### F4 — MEDIUM, CONFIRMED. The saturation cap is a cliff, it rewrites the scan field, and today it changes one seat

- **Cliff.** Growth of 19.56% leaves 2333.HK uncapped at MoS 0.915 and ranked first. Growth of 20.00% would
  have capped it at 0.50. JET2.L (raw MoS 0.872), HRMY (0.805) and 0175.HK (0.861) are capped; nothing between
  10% and 20% is touched even though K triples over that range.
- **It mutates the stock record.** `:6921` writes `s.iv15_deep_value_mos = min(0.50, …)` and the scan is saved
  afterwards (`:7320` then `:7323`). In the 2026-11-07 scan five names sit at exactly 0.50 (JET2.L, HRMY,
  0175.HK, RBW.WA, 009540.KS) with fair values implying 0.80–0.87, while ten names sit at 0.95 because they
  were skipped before that line. The same field therefore means two different things depending on which gate a
  name hit. In the picks file JET2.L shows MoS 0.50 next to a fair value of 11,778p against a price of 1,510p.
- **Names at the 0.95 clamp (10 by my count; the pack says 11): none is eligible.** Four are banks or
  lenders (1288.HK, NBS.L, PTSB.IR, PAG.L), two utilities (ALUP3.SA, DRX.L), three structural breaks
  (WISE.L, NRP.AS, MFEA.MI), one fails leverage and EPV (1055.HK). The gates work here; DRX.L (fair value 569×
  price) is a share-count error caught by the structural-break flag.
- **Effect on selection today.** With every qualifier seated, the cap only reorders Consumer Cyclical:
  capped, 0175.HK scores 0.469 and is the fifth name in a sector allowed four; uncapped it would be third and
  MMB.PA would be cut instead. That is the whole effect.
- **Double penalty.** The cap is applied before the peak-cycle normalisation (`:6920` then `:6936`), so a
  saturated peak-cycle name is cut twice: 009540.KS goes 0.863 → 0.50 → −1.0.
- **Flag meaning.** The dataclass comment says "MOS pegged at the 0.95 clamp" (`:1124`); the flag also fires
  on growth ≥ 20% (`:3038`), which is 424 names.

Fix: never overwrite the raw field; keep the ranking score in its own variable. Replace the cliff with the
growth cap of F1 (then there is nothing to saturate).

### F5 — MEDIUM, CONFIRMED. Rotation is driven by gates and missing scan rows, not by the metric; the incumbency boost cannot act

See section 4 for the events. Mechanism:

- `iv15_nogrowth_agreement` is computed inside the valuation (`:3037`) and tested before the boost is added
  (`:6917` vs `:6937`). A held name whose IV15 MoS slips to −0.01, or whose EPV MoS slips to −0.01, is dropped
  with no buffer. The 0.05 incumbency boost never gets a chance. WEX left at −0.013 despite being held.
- The leverage gate is a hard line at 3.0×. MMB.PA is at 3.0 today (rounded); FIS, which left on 10-10 with
  its IV15 MoS still positive, reads 3.5× in the current scan.
- Current picks within about 0.15 of the EPV line: INVA 0.066, EEFT 0.105, 2883.HK 0.118, MBB.DE 0.136,
  HRMY 0.151. On the IV15 line: 1208.HK 0.107.

Fix: give the gates an entry/exit band (enter above +0.05, leave below −0.05; leverage enter under 2.75, leave
above 3.25). Carry a held name for one scan when its row is missing instead of dropping it.

### F6 — MEDIUM, CONFIRMED. Two share-class artefacts sat in the basket until October/November

| Name | What it is | Why IV15 liked it | Held |
|---|---|---|---|
| 50GP.L | Croda International **preference share** (vendor profile: "Croda International Plc", price 74.75p, market cap £49m, not actively trading, average volume 1,495) | Priced at 75p against the ordinary share's cash flow per share | 2026-08-21 → 2026-10-24, also in six other baskets |
| LISP.SW | Lindt & Sprüngli **participation certificate**, one tenth of a registered share (8,495 vs 87,800 CHF; the vendor reports the same market cap for both) | Fair value 10,890 CHF is per registered share. The registered share scores −1.0; the certificate at a tenth of the price scored +0.25 | 2026-08-20 → 2026-11-07, also in six other baskets |

They were 2 of the 10 holdings on 2026-09-07. Both left because they vanished from the scan (logged as
`unpriced_exit`, `exit_metric 0.0`), not because any rule caught them. The 50GP.L vendor series flips between
84.75 and 0.8475 (pence and pounds); the tracker used scan quotes (84.75 → 77.5 → 74.75), so the flip did not
reach the NAV.

Fix: reject a security when the vendor's market cap divided by (price × statement share count) is far from 1,
and when the profile says it is not actively trading.

### F7 — MEDIUM, CONFIRMED chain / SUSPECTED attribution. The +19.6% is real but comes from a tiny book, and it was used as evidence

- **Since 2026-09-07 the chain reconciles.** Period returns recomputed from daily closes against the tracker:

  | Period | Holdings | From closes | Tracker |
  |---|---|---|---|
  | 09-07 → 09-22 | 10 | −3.0% (50GP.L 84.75 → 77.5) | −3.3% |
  | 09-22 → 10-10 | 13 | −2.8% | −2.8% |
  | 10-10 → 10-24 | 14 | +2.6% (50GP.L booked at 0%) | +2.6% |
  | 10-24 → 11-07 | 16 | +0.6% (+0.45% with LISP.SW booked at 0%) | +0.45% |

  NAV 123.50 → 119.62 = −3.1%; ACWI over the same closes −5.9% (161.89 → 152.37). Returns are price-only,
  local currency, equal weight.
- **All of the gain predates 2026-09-07** and the rebalance log for that period is lost. What survives: a
  2026-05-28 picks backup with two names (CALM, PRG), a 2026-07-16 picks file with nine names, a code comment
  dated 2026-07-21 citing "iv15 +17.6%" (`weekly_opus_refresh.py:6527`), and the 09-07 snapshot.
- **Reconstruction from closes (SUSPECTED — holdings inferred from those snapshots):** June with CALM and PRG
  ≈ +14.7% (PRG +22.3%, CALM +7.1%); 07-01 → 07-21 with the nine names +4.0%; 07-21 → 08-19 +6.7% (TEP.PA
  +33%, WEX +21%, TNET +16%); 08-20 → 09-07 with the ten new names −1.1%. Chained: about +19% at 07-21
  (the code comment says +17.6%) and about +26% at 09-07 (recorded: +23.5%). So the number is consistent with
  real prices to within a few points, and about 60% of it was earned by roughly two stocks in one month, under
  the pre-June growth rule.
- Of the names behind the gain only TEP.PA is still a pick. All ten 09-07 holdings carry entry dates of
  08-20/08-21: the basket was rebuilt from scratch after the 2026-08-18 universe collapse (which left it with
  one pick, `screener_v6.py:7307-7311`) and the 08-20 currency fix.
- **It was acted on.** `weekly_opus_refresh.py:6526-6531` gives names from this basket +2 intake priority for
  the debate because of that return.

Fix: show the return with the number of holdings behind it; drop or re-justify the intake tilt; treat
2026-09-22 as the start of the usable record (+0.2% since then on 13–16 names).

### F8 — LOW, CONFIRMED. Smaller defects

- `round(target_T * 0.3)` (`:6649`) uses banker's rounding: at 15 names the cap is 4, not 5, which is why
  the basket stops at 14 rather than 15.
- The scan's `sector_class` is set from the industry string alone (`:2808`) and has no sector fallback, so it
  reads "operating" for IBKR, PAG.L, 8601.T, 6030.HK and FTK.DE. The selection uses the object form and
  excludes them correctly; anything else reading the scan field is misled.
- `revenue_cagr_3y` tests the oldest year's revenue (`revs[0] > 0`, `:2195`), so HRMY shows 0 in the scan
  while its revenue grew 25.6% a year. IV15 has its own calculation and is not affected.
- Published MoS and fair value for the two peak-cycle picks (MMB.PA, MBB.DE) are the raw, un-normalised
  figures; only the ranking is adjusted.

## The picks, one by one

| Pick | Published MoS | Fair value ÷ price | Growth input | Avg FCF ÷ net income | EPV MoS | Debate | Reading |
|---|---|---|---|---|---|---|---|
| 2333.HK | 0.915 | 11.7 | 19.6% | 1.5 | 0.43 | B, thesis impaired, numeric gate REJECT | Top rank from one working-capital year and growth 0.4 points under the cap |
| 2618.HK | 0.730 | 3.7 | 14.0% | 2.8 | 0.38 | A, PASS, value seat | Cheap on four methods; the IV15 number is lease-inflated |
| BETS-B.ST | 0.683 | 3.2 | 15.2% | 1.05 | 0.42 | C, forensic EXCLUDE | Clean inputs; debate rejects the business |
| EEFT | 0.641 | 2.8 | 13.9% (8.1% revenue) | 1.8 | 0.11 | B, debate discount 5.8% | Buyback growth, settlement-float cash flow |
| FGR.PA | 0.578 | 2.4 | 8.9% | 2.9 | 0.44 | A, numeric gate REJECT | Concession and lease cash flow |
| 2883.HK | 0.549 | 2.2 | 12.1% | 1.4 | 0.12 | B, numeric gate EXCLUDE_ELIGIBILITY | Method-consistent |
| TEP.PA | 0.516 | 2.1 | 8.1% | 2.4 | 0.53 | C, forensic EXCLUDE | Lease and intangible-inflated cash flow |
| MMB.PA | 0.730 | 3.7 | ~10.4% | ~4.6 | 0.54 | C | Lease-inflated; peak cycle; on the leverage line |
| JET2.L | 0.50 (raw 0.87) | 7.8 | ≥ 20% (capped) | n/a | 0.36 | B, debate discount 13.9% | Saturated |
| HRMY | 0.50 (raw 0.81) | 5.1 | 27.4% (capped) | 1.8 | 0.15 | A, PASS | Saturated; single-product company |
| INVA | 0.385 | 1.6 | 13.0% (8.7% revenue) | 1.1 | 0.07 | C, forensic EXCLUDE | On the EPV line |
| MOH | 0.257 | 1.35 | 17.8% (12.4% revenue) | 0.5 | 0.33 | C, forensic EXCLUDE | Insurer; latest FCF negative |
| MBB.DE | 0.456 | 1.8 | n/a | n/a | 0.14 | B, PASS | Peak cycle |
| 1208.HK | 0.107 | 1.1 | 10.8% (24.2% revenue) | 4.6 | 0.28 | A, PASS | Consolidated FCF vs attributable profit |

None of the 14 is a unit, currency or share-class artefact. Seven carry a cash-flow base that overstates
owner cash (F3); all carry the growth problem (F1).

## 4. Rotation since 2026-09-22

Picks file (weekly) events, pieced together from entry dates, the exits list and the tracker:

| Date | Event | Metric at the time | Real reason |
|---|---|---|---|
| 09-26 | WEX in | IV15 MoS 0.008 | Crossed zero |
| 10-10 | FIS out | 0.178 (above its entry 0.151) | A gate (current scan: leverage 3.5×, EPV MoS −0.03) |
| 10-10 | 2883.HK in | 0.513 | EPV gate crossed |
| 10-19 | WEX out | −0.013 | Metric (the only one) |
| 10-19 | HRMY in (0.50 capped), 1208.HK in (0.003) | — | EPV gate / crossed zero |
| 10-19 | 2618.HK and 2883.HK vanish, no exit record | — | Row missing from that scan |
| 10-24 | 2618.HK and 2883.HK back, entry date and price reset | — | Data event |
| 10-24 | FDJU.PA in (0.62), MBB.DE in (0.42) | — | EPV gate crossed |
| 10-24 | 50GP.L gone, no exit record | — | Dropped from the scan |
| 10-31 | FDJU.PA out after one week | 0.61 | A gate (current scan: EPV MoS −0.04, all other gates pass) |
| 10-31 | CMCSA out | 0.016 | A gate (current scan: EPV MoS −0.05) |
| 10-31 | MBB.DE vanishes, no exit record | — | Row missing from that scan |
| 11-07 | MBB.DE back (entry reset), INVA in (0.385) | — | Data event / EPV gate |
| 11-07 | LISP.SW gone, no exit record | — | Dropped from the scan |

Of nine departures, one was the IV15 metric moving (WEX), three were a gate flipping while the metric was
still positive (FIS, FDJU.PA, CMCSA — CONFIRMED that the metric was positive at exit; which gate flipped is
read from the current scan, so SUSPECTED), and five were rows missing from a scan (three temporary, two
permanent).
The "no exit record" cases are CONFIRMED by elimination: the only code path that removes a previous pick
without logging an exit is the name being absent from the scan (`:6999-7002`), and the exits list holds only
four entries, so nothing was truncated. 2618.HK shows the same 10-24 entry date in all four baskets that hold it.

Consequence for the value seat: the picks file dates 2618.HK from 10-24 at 9.895 (+8.7% to the scan price);
the tracker, which did not rebalance that week, dates it from 08-21 at 11.69 (−8.0%).

After leaving: FIS −11.3%, WEX −7.7%, FDJU.PA +1.2%, CMCSA +2.6% (pack figures to the latest close).

Incumbency boost: does nothing for this basket (F5).

## 5. What it contributes to the debate

- Grades of the 14 picks: 4 A, 5 B, 5 C. Seven of 14 are thrown out by the debate's own gates: forensic
  EXCLUDE on BETS-B.ST, TEP.PA, INVA, MOH; numeric gate REJECT on 2333.HK and FGR.PA; EXCLUDE_ELIGIBILITY on
  2883.HK.
- Median screen MoS 53% against a median debate discount of 17.6%. The debate treats the IV15 number as noise.
- Seats: value seat 2618.HK, which is also in `dcf_fcff`, `epv` and `owner_earnings`. No regime seat. 0175.HK
  (a regime seat) qualifies here and is cut by the sector cap.
- Overlap: 11 of 14 picks are in another basket (7 in `dcf_fcff`, 6 in `epv`, 5 in `graham_revised`). Unique
  to this basket: 1208.HK (A, PASS), MBB.DE (B, PASS), MMB.PA (C). Every pick is EPV-positive by construction.
- It is a partial lens, not a copy: "EPV-cheap and recently fast-growing". Its marginal contribution to the
  debate universe today is three names.

## 6. What I could not check

- The holdings, rebalances and exits between 2026-05-27 and 2026-09-07. My reconstruction in F7 rests on two
  surviving snapshots and one code comment; the June attribution in particular is an inference.
- Why 2618.HK, 2883.HK and MBB.DE were missing from single weekly scans, and why 50GP.L and LISP.SW left the
  universe. No past scan files are available locally.
- The growth input and cash-flow split for JET2.L, MBB.DE and (partly) MMB.PA: no cached statements. JET2.L's
  growth ≥ 20% is inferred from the flag (its raw MoS is below 0.95).
- Whether the "other financing" outflows in F3 are lease repayments line by line. The vendor does not itemise
  them; the pattern (large D&A against small capex, no dividends or buybacks to explain the outflow) fits.
- The CNY→HKD rate of 1.175 used by the scan. It is applied consistently to all three mainland names.
- The growth-distribution table uses statement caches dated May to August 2026 and covers 550 of the 796
  names with a computed IV15.

## Fixes, in order

1. Rebuild the growth input (F1): cap at 8–10%, fade it, use the lower of revenue and per-share growth, a
   longer window, and a fixed terminal multiple.
2. Use an owner-cash-flow base (F3): lease repayments out, minorities out, or cap FCF at about 1.5× net income.
3. Stop overwriting `iv15_deep_value_mos` at `screener_v6.py:6921`; keep ranking adjustments in a separate
   variable (F4).
4. Put entry/exit bands on the EPV, IV15 and leverage gates, and hold a name through one missing scan (F5).
5. Add a share-class guard: market cap against price × statement shares, and the vendor's not-actively-trading
   flag (F6).
6. Remove or re-justify the intake tilt at `weekly_opus_refresh.py:6526-6531`; report the tracked return with
   the holding count and from 2026-09-22 (F7).
7. Tidy the small items in F8.
