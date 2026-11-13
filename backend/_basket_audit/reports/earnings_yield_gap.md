# Basket audit — `earnings_yield_gap` (earnings yield against the local 10-year yield)

Scan audited: 2026-11-07 (3,430 names). Picks file and tracker: GCS snapshot of 2026-11-12.
Reviewer's checks were read-only. "CONFIRMED" means I reproduced it from the scan row, the code or
the vendor's live data. "SUSPECTED" means the evidence points that way but I did not reproduce it.

---

## 1. Verdict

**UNSOUND.** The formula is computed as written, but the basket does not select what the method intends.

1. **More than half of the 30 picks are at the top for the wrong reason.** 4 sit on a wrong number
   (a 100-fold share-count error, a preferred share, an unadjusted stock split, a doubled EPS),
   5 on a confirmed one-off gain, and 7 more on a suspected one-off or investment-company
   revaluation. Ranking on a normalised EPS keeps only 14 of the 30.
2. **Until 2026-11-07 the basket held 7 to 9 non-equity or unit-broken lines out of 30 seats**
   (exchange-traded notes, a preference share, a participation certificate, a depositary receipt).
   They left because they vanished from the scan, not because anything was fixed, and one new
   preferred share (`ATH-PA`) entered the same day.
3. **The "local yield" part of the rule does nothing at the top.** A plain earnings/price rank
   selects the identical 30 names. The yield table is also out of date by 0.7 to 1.7 percentage
   points and has no entry for 403 names (12% of the scan, including every China-domiciled name).

Not one of the 11 exits since the reconstruction was caused by a real change in cheapness.

---

## 2. What the rule computes

`_rank_ey_gap` (`screener_v6.py:6511-6530`):

- Earnings yield = latest **annual** diluted EPS (`eps_latest`, one fiscal year, as reported,
  `screener_v6.py:2859-2860`) × `fx_to_price` ÷ current price. `fx_to_price` converts the reporting
  currency into the price currency (including pounds → pence), so the currency handling is correct.
- Gap = earnings yield − the 10-year government yield looked up by the stock's `country`
  (`screener_v6.py:98-107`). Unknown countries silently get the US figure.
- All 3,430 names are sorted on the gap. There is no eligibility test: loss-makers, names with no
  statements (EPS 0) and names with a zero price are all ranked.

**What the "margin of safety" number is.** `earnings_yield_gap_mos = (rank_pct − 0.5) × 0.25`
(`screener_v6.py:6528-6529`). It is the name's position in the sorted list, rescaled to run from
−0.125 (worst) through 0 (median) to +0.125 (best). It is not a discount to any value.

- The rank-1 name (gap 232%) scores 0.1250. The last pick, rank 65 (gap 15.2%), scores 0.1203.
  The whole basket sits inside a band 0.0047 wide. The picks file's `average_mos` of 12.27% and
  each pick's `mos` of "12.0% to 12.5%" say nothing about how cheap anything is.
- The picks file's `fair_value` for this basket is `price × (1 + mos)` (`screener_v6.py:7036-7039`).
  CONFIRMED: every pick's fair value is 1.120 to 1.125 times its price. It is not a fair value.
- The same rank score is fed into the convergence basket as one of its fair-value votes
  (`_CONV_DERIVE_MOS`, `screener_v6.py:6759`).

**Ties.** None that matter. The gap is a continuous number; the only tied groups are at the very
bottom (118 US names with EPS 0 all at −4.2%, and a few smaller groups). The pack's "44 distinct
values in the top 60" is a rounding effect of printing to four decimals (one rank step is 0.00007).
The sort is stable, so real ties fall to scan order, which is arbitrary but irrelevant here.

**Gates that apply.** Net debt / EBITDA below 3 and Piotroski score of 3 or more
(`screener_v6.py:6639-6644`, `6928`); a 30%-per-sector cap; the above-median floor
(`_apply_mos_floor`). The basket is declared applicable to every sector class including banks and
insurers (`screener_v6.py:887`). It is **exempt** from the peak-cycle normalisation, the
structural-break exclusion and the falling-forward-EPS gate (`screener_v6.py:6881-6913`).

Selectivity: 2,251 names pass both gates, 1,241 of them above the median, for 30 seats. The cut-off
is far out in the tail (top 2% of the scan), so the basket is not short of candidates. The problem
is what lives in that tail.

---

## 3. Findings, most serious first

### F1 — HIGH — CONFIRMED — Four picks rank on a wrong number

There is no sanity check between the per-share EPS and the price it is divided into.

| Pick | Rank | Scan earnings yield | What is wrong | Evidence | True figure |
|---|---|---|---|---|---|
| `DRX.L` | 1 | 236% | Vendor's FY2025 diluted share count is 3.61 m; every earlier year is ~390-414 m. EPS 20.2 is therefore 100 times too high once multiplied by 100 for pence. | FMP income statement: net income £73.0 m, `weightedAverageShsOutDil` 3,614,000, `epsDiluted` 20.2 (FY2024: 390.7 m shares, EPS 1.35). Market cap ÷ price gives 337 m shares. | £73 m ÷ £2.88 bn ≈ 2.5% — below the UK 10-year yield |
| `ATH-PA` | 7 | 57.5% | It is a preferred share of Athene (price $22.46). The EPS 12.92 belongs to the company. | FMP profile: Athene Holding, ISIN US04686J8615, IPO date 2019-06-10, price range 22.2-25.2. | Not an equity earnings yield at all |
| `SBSP3.SA` | 16 | 46.2% | EPS 12.37 is on 684 m shares; the price is on about 3.52 bn shares (five-for-one). | FMP: FY2025 `weightedAverageShsOutDil` 684.2 m; live market cap 94.7 bn ÷ 26.93 = 3.52 bn. | EPS ≈ 2.41, yield ≈ 9.0%, gap ≈ −4.9% against the 13.9% in the table. Below the median. |
| `PAH3.DE` | 19 | 33.1% | Scan EPS 8.65 is net income over 153.1 m shares (one of two share classes). | Scan history row: 153.1 m shares; market cap ÷ price = 306.2 m. FMP today returns `epsDiluted` 4.33 on 306.25 m shares. | Yield 16.6%, gap 14.1% — would rank about 75th, outside the basket |

The scan itself flagged `DRX.L` (`structural_break_reason: share_count_jump_2025`), but that flag
only excludes the six "earnings-based" methods, not this one.

The same test (shares implied by market cap ÷ price, against the statement's diluted shares) also
exposes names just outside the basket: `8035.T` 4.9×, `TAEE3.SA` 3.0×, `ALUP3.SA` 4.6×, `SM` 2.1×,
`PRS.OL` 2.1×, `ACR.OL` 2.7×. And it explains a past pick: `6288.HK` (a depositary receipt, 100
receipts per share) had FY2025 EPS 1,409 on 307 m shares against a receipt price of HK$37.

**Fix.** Compute the yield as net income ÷ market cap in one currency, and cross-check it against
EPS ÷ price. Where the two disagree by more than about 25%, exclude the name and log it. (Chinese
A/H dual listings show a ratio of 1.2 to 1.8 because the vendor's market cap blends two share
prices; they need the per-share route.)

### F2 — HIGH — CONFIRMED — Non-equity securities are admitted and ranked on the issuer's EPS

The universe pull filters only `isEtf=false`, `isFund=false` (`screener_v6.py:1413`).
`includeAllShareClasses=false` is sent for the retired S&P 500 region only (`:1423-1425`).

Seats held by lines that are not ordinary shares, or whose per-share unit is broken:

| Rebalance date | Such seats | Names |
|---|---|---|
| 2026-09-07 / 09-22 | 9 of 30 | `MGRD`, `MGRB`, `MGR`, `MGRE` (Affiliated Managers notes), `PRS`, `PRH` (Prudential Financial notes), `LISP.SW` (Lindt participation certificate, one-tenth of a share), `50GP.L`, `6288.HK` |
| 2026-10-10 | 8 of 30 | as above less `6288.HK` |
| 2026-10-24 | 7 of 30 | as above less `50GP.L` |
| 2026-11-07 | 1 of 30 | `ATH-PA` |

`50GP.L` is Croda International's 5.9% preference share (FMP profile: Croda, ISIN GB0002343159,
last dividend 5.9, price 74.75p, market cap £49 m, `isActivelyTrading: false`). Croda's
per-ordinary-share earnings and fair values were set against a 75p preference share, which is why
seven methods scored it near the cap. Its vendor price series alternates between pounds and pence
(0.8475 on 10-05, 84.75 on 10-06, 77 on 10-16, 0.77 on 10-19, 74.75 on 11-09).

`MGRD` trades at $13.43 with an IPO date of 2021-07-23, while FMP reports the parent's $9.8 bn
market cap. It is not the common share.

These seven left on 2026-11-07 because they were **absent from that scan**. `screener_v6.py` has
not changed since 2026-08-20 (`git log`), so nothing prevents their return. Two more such lines sit
at ranks 3 and 6 today (`HEIM-PREF.ST`, a preference share; `NBS.L`, Nationwide Building Society
capital securities) and are kept out only because they happen to fail the leverage gate.

**Fix.** Ordinary shares only: reject lines whose issuer already has another line in the universe,
ticker patterns such as `-P?` and `PREF`, and anything failing the F1 share-count check.

### F3 — HIGH — CONFIRMED (5) / SUSPECTED (7) — One year's reported EPS puts one-off gains at the top

`eps_latest` is the last fiscal year's bottom-line diluted EPS. It includes disposal gains, tax
credits and discontinued operations. The code comment calls this basket "less sensitive" to the
earnings base (`screener_v6.py:6881-6883`) and exempts it from every earnings-quality gate. That is
backwards: earnings ÷ price is the most earnings-sensitive measure in the file.

| Pick | Rank | Scan yield | Latest EPS vs 5-year median | What the statement shows | Status |
|---|---|---|---|---|---|
| `PTEC.L` | 4 | 108% | 4.70 vs 0.34 | Net income €1,457 m, of which discontinued operations €1,624 m. Continuing operations lost €166 m. | CONFIRMED |
| `ZEAL.CO` | 12 | 38.7% | 90.2 vs −16.2 (four loss years) | Revenue DKK 9.2 bn in a single year for a development-stage company | CONFIRMED |
| `LYFT` | 13 | 39.8% | 6.81 vs −0.88 | Pre-tax income −$53 m; income tax expense −$2,897 m (a tax credit) | CONFIRMED |
| `BYD` | 27 | 29.5% | 22.56 vs 6.12 | Operating income $877 m; other income +$1,453 m | CONFIRMED |
| `SMIN.L` | 37 | 24.3% | 6.26 vs 0.72 | Net income £1,970 m, of which discontinued operations £1,815 m. Continuing EPS ≈ £0.50, yield ≈ 1.9%. | CONFIRMED |
| `NWL.MI` | 15 | 36.1% | 8.71 vs 0.34 | "Other" income of €326 m inside net income of €375 m | SUSPECTED one-off |
| `OTEC.OL` | 14 | 36.2% | 0.67 vs 0.08 | Not checked | SUSPECTED |
| `MNC.WA` | 32 | 25.8% | 9.77 vs 1.70 | Not checked | SUSPECTED |
| `TPE.WA` | 53 | 21.0% | 1.89 vs 0.33 | Not checked | SUSPECTED |
| `MAU.PA` | 28 | 26.8% | 2.13 vs 1.05 | Not checked | SUSPECTED |
| `2628.HK` | 33 | 25.4% | 5.45 vs 1.81 | Insurer; scan flags PEAK_CYCLE | SUSPECTED peak |
| `BION.SW` | 40 | 20.4% | 10.54 vs −3.77 | Investment company; "earnings" are portfolio revaluations | SUSPECTED |

Two more picks are investment companies whose EPS is mostly unrealised gains (`VEFAB.ST`, `III.L`).

Tests on the scan:

- Re-ranking on the lower of latest EPS and the 5-year median keeps **14 of the 30** picks.
  `ZEAL.CO`, `LYFT`, `BION.SW`, `SMIN.L` and `NWL.MI` fall below rank 1,900.
- 15 of the 30 picks show an earnings yield of 25% or more (a price/earnings ratio of 4 or less).
- 14 of the 30 carry the scan's own `PEAK_CYCLE` or `structural_break` flag; `DRX.L` and `ZEAL.CO`
  also have forward EPS growth below the −25% gate (−33%, −67%). None of this is used here.

**Fix.** Rank on earning power: continuing-operations income, capped at a multi-year median (the
`eps_normalized` / `norm_scale` machinery already exists), and apply the structural-break and
forward-decline gates to this basket. Treat any yield above roughly 25% as "verify before seating".

### F4 — MEDIUM — CONFIRMED — The local-yield comparison is cosmetic, stale and incomplete

- **Cosmetic.** Rebuilding the basket from the scan on plain earnings ÷ price, with the same gates,
  gives the **same 30 names** as the gap ranking. The yields in the table span 0.9% to 13.9%; the
  cut-off gap is 15.2%. Across the whole scan the two rankings correlate 0.946.
- **Stale.** The table is labelled "asof 2026-Q2 — refresh roughly once a quarter"
  (`screener_v6.py:92-103`). Current levels:

  | Country | Table | Now | Source |
  |---|---|---|---|
  | US | 4.2% | 4.86% (11-06), 5.10% (11-12) | FMP treasury rates |
  | Germany | 2.5% | about 3.25% (11-09) | Trading Economics |
  | UK | 4.4% | 5.29% (end October) | Tradeweb |
  | Japan | 1.1% | 2.77% (end October) | Tradeweb |
  | Brazil | 13.9% | 15.29% (November) | Trading Economics |

  Updating only these five: names with a positive gap fall from 1,773 to 1,603, the median name
  moves 37 rank places (maximum 405), the median Japanese name moves from rank 672 to 923. The
  top 30 do not change. The other twelve countries were not checked.
- **Incomplete.** 403 names (11.7%) have a country that is not in the table and get the US 4.2%:
  China 143, Poland 78, Korea 51, Belgium 39, Austria 29, Greece 19, Iceland 18, Ireland 12,
  Portugal 10, others 4. Nine of the 30 picks are priced this way (`2628.HK`, `2601.HK`,
  `1339.HK`, `1988.HK`, `2333.HK`, `MNC.WA`, `KGN.WA`, `TPE.WA`, `PROX.BR`).
- **Not "listing country".** The docstring says the table is keyed by listing country. `country`
  is the issuer's domicile. `6288.HK` (priced in Hong Kong dollars) gets the Japanese yield;
  `0RG4.L` (priced in Danish kroner) gets the UK yield; Hong Kong-listed Chinese issuers get the US.

**Fix.** Either drop the pretence and call it an earnings-yield rank, or make the yield matter:
pull the yields live, key them by price currency, cover every country in the universe, and fail
loudly on a missing one instead of defaulting to the US.

### F5 — MEDIUM — CONFIRMED — The leverage gate decides which banks and insurers get in, and it is meaningless for them

Financials are "applicable" (`screener_v6.py:887`) and pass through net debt ÷ EBITDA < 3. The code
itself says this gate "misreads insurers" (`screener_v6.py:6923-6927`) and waives it for
convergence only.

Among the 54 Financial Services names in the top 200 by gap, 27 pass and 27 fail. `1988.HK` (China
Minsheng Bank, ratio 1.6) passes; `6818.HK` (China Everbright Bank, 8.1) and `3698.HK` (Huishang
Bank, 24.0) fail. `2628.HK` and `2601.HK` pass; `1336.HK` (4.1) and `0966.HK` (3.8) fail. 8 of the
30 seats are financial or insurance names chosen this way.

**Fix.** Give financials their own solvency test (capital ratio, or simply exclude them from this
basket) rather than a debt-to-EBITDA figure.

### F6 — MEDIUM — CONFIRMED — The incumbency boost is 171 rank places wide for a 30-seat basket

Boost = 10% × 0.125 = 0.0125 (`screener_v6.py:6869-6873`). One rank step is 0.25 ÷ 3,429 = 0.000073,
so the boost equals **171 places**. Only about half of the top-ranked names pass the gates, so the
30th seat is at rank 65. An incumbent keeps its seat down to roughly rank 236, where the gap is
7.7% against 15.2% at the cut-off.

Evidence that it bites: the seven names dropped on 2026-09-22, when the previous picks could not
be loaded and incumbency reset, had exit scores of 0.1142 to 0.1201 (ranks about 68 to 149). All
had been holding seats.

At the 2026-11-07 scan the boost held two names (`NAS.OL`, `PROX.BR`) over `0RG4.L` and `SLM`.
Near the cut-off the gaps differ by 0.1 to 0.4 points, which is one day's price move, so some
damping is needed. The size is the issue.

**Fix.** Define incumbency in seats, not in units of the whole-universe score: for example, an
incumbent stays while it is inside the top 45 names that pass the gates.

### F7 — LOW — CONFIRMED — Smaller points

- **Stale statements are not screened out.** `0RG4.L` (rank 54, next in line for a seat) is ranked
  on FY2023 EPS. Six names in the scan have a latest statement of 2024 or older.
- **Picks-file churn the tracker cannot see.** `PTEC.L` has been in the tracker since 2026-08-21
  but its picks-file entry date is 2026-11-07 (entry price reset from 391.6 to 363.6). A rank-4
  name fell out of the picks file for a scan and came back. Its EBITDA is slightly negative, so the
  leverage gate turns on whether net debt is at or below zero. Cause SUSPECTED, not reproduced.
- **The back-test mirror is a different rule.** `replay_baseline.py:344` still subtracts one global
  risk-free rate.

---

## 4. All 30 current picks

| Group | Count | Names |
|---|---|---|
| Wrong number (F1, F2) | 4 | `DRX.L`, `ATH-PA`, `SBSP3.SA`, `PAH3.DE` |
| One-off gain, confirmed (F3) | 5 | `PTEC.L`, `ZEAL.CO`, `LYFT`, `BYD`, `SMIN.L` |
| One-off or peak, suspected (F3) | 7 | `NWL.MI`, `OTEC.OL`, `MNC.WA`, `TPE.WA`, `MAU.PA`, `2628.HK`, `BION.SW` |
| Investment-company revaluations | 2 | `VEFAB.ST`, `III.L` |
| Plausibly there for the stated reason | 12 | `SEA1.OL`, `SOFF.OL`, `MPCC.OL`, `NAS.OL`, `1988.HK`, `2601.HK`, `1339.HK`, `2333.HK`, `CMCSA`, `KGN.WA`, `IMC.MC`, `PROX.BR` |

Currency residue from the pre-August bug: none found. For every pick, `currency`, `fx_to_price`
and price are consistent (pence lines use 100 or the euro-to-pence rate; the Norwegian shipping
names report in dollars and convert at 9.45; Chinese H-shares convert yuan at 1.175). `SOFF.OL`
switched reporting currency from kroner to dollars in FY2024, confirmed against FMP, so its
multi-year EPS history mixes currencies. That does not affect this basket, which uses one year.
`2333.HK` at HK$6.40 looked low; the daily series shows a gradual fall from 10.65 in June with no
break, so the price is real.

---

## 5. Rotation since 2026-09-22

**2026-09-22 (reconstruction).** Seven out, seven in. All 18 surviving picks carry an entry date
of 09-22, so the previous picks were not loaded and incumbency did not apply. This is a data event.
Out: `PROX.BR`, `TUI1.DE`, `DUE.DE`, `GEF`, `PEUG.PA`, `LHA.DE`, `AEGN.AT`.
In: `KGN.WA`, `MNC.WA`, `SEA1.OL`, `SOFF.OL`, `2601.HK`, `NAS.OL`, `TPE.WA`.

**After the reconstruction — 11 exits:**

| Exit | Date | Exit score | Why it left | Real change in cheapness? |
|---|---|---|---|---|
| `6288.HK` | 10-10 | 0.0216 (from 0.1249) | New fiscal-year statement arrived with EPS in receipt units (17.61) instead of share units (1,409) | No — a unit correction |
| `50GP.L` | 10-24 | 0.0, unpriced | Absent from the scan | No |
| `GUBRA.CO` | 10-24 | 0.1233 (still rank 17) | Piotroski score fell to 2, below the gate | No — a gate, and the EPS is a one-off (102.7 against losses) |
| `MGRD`, `MGRB`, `MGR`, `MGRE`, `PRS`, `PRH`, `LISP.SW` | 11-07 | 0.0, unpriced | Absent from the scan | No |
| `DNR.MI` | 11-07 | 0.0736 (from 0.1216) | Score collapsed while the price fell 26% — a lower price should raise the yield, so the EPS input changed | No — SUSPECTED data revision |

**Entries:** `SMIN.L` (10-10, new statement with the disposal gain), `IMC.MC` (10-19), `PROX.BR`
(10-24, back after the 09-22 reset), `2333.HK` (10-31, real price fall), and eight on 11-07 that
filled the seats vacated by the vanished securities: `PTEC.L` (re-entry), `ATH-PA` (preferred
share), `NWL.MI`, `2628.HK`, `1988.HK`, `1339.HK`, `MPCC.OL`, `III.L`.

Turnover that was noise or data: all 11 exits. The incumbency boost is not the cause of any of
them; it cannot protect a name that leaves the scan or fails a gate.

After exit, the 18 logged leavers averaged +1.6% against the world index, the same as the current
picks since entry. Neither figure is informative given what the seats contained.

---

## 6. What it contributes to the debate

- **Seats supplied: none**, in either book. `DUE.DE`, which holds a seat in both books, was in this
  basket until the 09-22 reset and now ranks 63rd, just outside.
- **Grades of the 30 picks:** 3 A, 19 B, 8 C. Value conviction 4 for four names, 2 for nine.
- **Thrown out by the debate's gates: 8** — forensic `NWL.MI`, `1988.HK`, `TPE.WA`; numeric
  `SBSP3.SA`, `SEA1.OL`, `2333.HK` (reject), `BYD`, `IMC.MC` (eligibility). Thesis state is
  IMPAIRED or BROKEN for 7.
- **The debate does not see the cheapness the screen claims.** Median debate discount to fair value
  is 12.7%. For `DRX.L`, the rank-1 name, it is −1.2%. The debate set its peak flag on 20 of 30.
- **It also did not catch the artefacts.** `ATH-PA` (a preferred share) was graded B with a
  numeric-gate pass. `PTEC.L` and `ZEAL.CO` were graded A.
- **Distinct lens: yes.** 16 of the 30 picks appear in no other basket. Largest overlaps are 7
  with `graham_revised` and 6 with `rd_capitalized_dcf`. But the distinct names are mostly the
  one-offs, the investment companies and the Chinese financials let through by F5.

Net: it spends 30 debate slots (16 of them unique to it) and has produced no seat.

---

## 7. The record

Tracked value: 103.84 on 09-22, 101.62 on 11-07 (−2.1%). Year-to-date +1.62%.

I recomputed each weekly step as the equal-weight move of the held names from the daily closes.
Six of the seven steps match within 0.5 points. The 09-22 to 09-26 step differs by 0.85 points
(tracker −1.50%, closes −0.65%); `DNR.MI` fell 18% on 09-22 itself, after the scan price of 7.395
was taken, which accounts for about 0.6 points. `50GP.L`'s pounds/pence flips did not leak into
the tracked value (the steps match with that name excluded). CONFIRMED: the arithmetic follows the
prices.

What it measures is another matter. From 09-22 to 11-07, between 23% and 30% of the portfolio
(7 to 9 of 30 seats) was notes, preference shares and unit artefacts. The figure is not a record of a
high-earnings-yield equity strategy.

---

## 8. Fixes, in order

1. **Check per-share figures against company totals** (F1). Net income ÷ market cap, cross-checked
   with EPS ÷ price; exclude and log disagreements. Removes `DRX.L`, `SBSP3.SA`, `PAH3.DE` today.
2. **Ordinary shares only** (F2). Removes `ATH-PA` and stops the notes returning.
3. **Rank on earning power, not one reported year** (F3). Continuing operations, capped at a
   multi-year median; apply the structural-break and forward-decline gates. Changes 16 of 30 seats.
4. **Decide what the yield is for** (F4). Live, complete, keyed by currency — or rename the basket.
5. **A solvency test that fits financials, or exclude them** (F5).
6. **Size incumbency in seats** (F6).
7. **Stop publishing the rank score as `mos` and `price × 1.12` as `fair_value`**, and stop passing
   it to convergence as a fair-value vote (section 2).
8. **Reject statements older than about 18 months**; align `replay_baseline.py` (F7).

---

## 9. What I could not check

- **The weekly picks files between 09-22 and 11-07.** Only the 11-12 snapshot and the two-weekly
  tracker log exist, so picks-file churn inside a fortnight (`PTEC.L`) is inferred from entry dates.
- **Why the seven notes and certificates left the 11-07 scan.** No code change explains it.
- **`DNR.MI`'s earlier EPS input**, and the nature of the suspected one-offs at `OTEC.OL`,
  `MNC.WA`, `TPE.WA`, `MAU.PA` (EPS history only, statements not opened).
- **Twelve of the seventeen yields in the table.** Only US, Germany, UK, Japan and Brazil were
  compared with current levels, and four of those five come from web search results, not a data feed.
- **Whether the stock split at `SBSP3.SA` is the cause** of its share-count mismatch. The mismatch
  (684 m against 3.52 bn) is confirmed; the split is the evident explanation, and the daily series
  shows no break since June, so it predates the cache.
- **The hard-coded historical returns** for this basket in `backfill_2026_tracking.py:119`.

## Lead for other reviewers (not this basket)

For pence-quoted London names the scan's `market_cap` is in pounds while `net_debt`, `ebit` and
`gross_profit` are in pence. `DRX.L`: market cap 2.88 bn, net debt 77.55 bn, EBIT 76.27 bn, giving
an acquirer's multiple of 1.05. Median acquirer's multiple is 3.2 for the 178 pence-quoted names
against 17.4 for the whole scan. 24 of 30 `acquirers_multiple` picks and 29 of 30 `ev_gp` picks are
pence-quoted. Not reproduced through the code path — verify there.

## Sources for current yields

- FMP treasury-rates endpoint (US 10-year, 2026-11-05 to 2026-11-12)
- [Trading Economics — government bond 10y news](https://tradingeconomics.com/news/government-bond-10y)
- [Trading Economics — Germany government bond yield](https://tradingeconomics.com/germany/government-bond-yield/news/599652)
- [Tradeweb Government Bond Update — October 2026](https://www.tradeweb.com/newsroom/media-center/insights/blog/tradeweb-government-bond-update--october-2026/)
