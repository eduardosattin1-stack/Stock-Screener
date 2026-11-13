# Basket audit — `dcf_fcff` (discounted cash flow)

Reviewer run: 2026-11-13. Scan audited: 2026-11-07 (3,430 names). Picks file: 2026-11-07.
"MoS" below means margin of safety: (fair value − price) / fair value. Cut-off of the basket: 0.569.

## 1. Verdict

**UNSOUND as a measure of cheapness (usable only as a wide net).** Three things justify it:

1. **At least 9 of the 30 picks are there because of a data or formula artefact, not because of the
   economics** (wrong share count, minority interests ignored, a one-off in the cash-flow base, a
   25%-a-year growth rate nobody could defend). Another 7 are real but clearly overstated.
2. **The number does not order the basket.** The screen says the median pick trades 66% below fair
   value; the debate's own work says 13%. Across the 26 picks that have both numbers the rank
   correlation between the two is −0.04 (none).
3. **Most turnover is not the metric moving.** 9 of the 14 exits logged since the reconstruction are
   names that vanished from the scan, and a current value-book seat (2618.HK) dropped out for one
   week and came back with a reset entry.

What is fine: currency conversion (no residue of the August dollar bug), the bank / insurer / REIT
exclusion, the leverage gate, no ties and no capped values among the picks, and the tracked return
is within about 0.6 points of what the picks really did. The debate caught every artefact I name
below — none reached a seat — so the cost today is wasted debate slots, not a bad holding.

## 2. What the rule computes

Code: `backend/screener_v6.py:2934-2950`, inputs from `2684-2721` and `2849-2885`.

- Takes the **average of the last three annual "free cash flow" figures** from the data vendor
  (operating cash flow minus capital expenditure), skipping zero years (`2698-2702`, `2721`).
- Grows it for five years at **half the return on equity**, floored at 3% and capped at 25%, fading
  by 15% a year (`2936`, `2940-2942`), then a perpetuity at 2.5% growth (`2943-2944`).
- Discounts everything at **10% for every company in every currency** (`2935`).
- Subtracts the latest net debt, divides by the diluted share count of the **latest annual income
  statement** (`2856`, `2946-2947`), converts to the price currency (`2948`) and caps the result at
  −1.0 … +0.95 (`2923-2926`).

Effect: fair value is between 13.3 times (3% growth) and 23.7 times (25% growth) the three-year
average cash flow, plus net cash. A debt-free stock at the growth floor clears the cut-off if it
trades under about 5.7 times that average.

It is **not** free cash flow to the firm. The vendor figure is after interest, so for an indebted
company interest is taken out once in the cash flow and the debt is taken out again. That error is
on the cautious side; the ones below are not.

Gates that apply (`6889-6957`): sector class must be operating or utility; no structural break; five
years of history; forward earnings not falling 25% or more; net debt under 3 times EBITDA;
Piotroski score of 3 or more; peak-cycle names are ranked on a reduced MoS; incumbents get +0.05;
at most 9 names per sector. I rebuilt the basket from the scan with these rules and reproduced it.

## 3. Findings, most serious first

### F1 — Share count is never checked against the live one (HIGH, CONFIRMED)

`shares` is the diluted weighted count of the last annual report (`2856`). Nothing compares it with
market value divided by price, so a split, a vendor error or heavy issuance flows straight into
fair value per share.

| Pick | Shares used | Shares really in issue | Published MoS | MoS at the right count |
|---|---|---|---|---|
| SBSP3.SA | 684m (FY2025 report) | about 3,517m (market value R$94.2bn / price R$26.78; the New York listing agrees: $16.5bn / $4.84) | 0.735 | about **−0.37** |
| PAH3.DE | 153.1m (the vendor's 2025 row at scan time) | 306.25m (every earlier year, and the vendor today) | 0.704 | about **0.41** |
| IEP | 575m | about 711m (units issued since) | 0.803 | lower, see F3 |

SBSP3.SA shows net income of R$8.46bn against a R$94bn market value (about 11 times earnings), yet
the scan row implies 2.2 times. Its row is wrong for every per-share method: its MoS reads 0.77 to
0.94 in five other methods. PAH3.DE escaped the structural-break test because the test is
`ratio < 0.5` (`2831`) and the share count exactly halved (ratio 0.500).

Fix: compare `price × shares` with the quoted market value; if they differ by more than about 25%,
do not publish a per-share value (flag it). Make the break test `<= 0.5`.

### F2 — Minority interests are not deducted (HIGH, CONFIRMED)

`eq_val = pv_stage1 + pv_terminal - net_debt_local` (`2946`). A parent that consolidates a
subsidiary it only partly owns gets credit for all of the subsidiary's cash flow.

- **CDI.PA** (Christian Dior, which owns about 41% of LVMH and consolidates all of it): FY2025
  balance sheet shows shareholders' equity €24.5bn and minority interest €42.0bn. Scaling the
  model's own equity value by Dior's 37% share of book equity gives about €437 a share against a
  price of €441 — MoS about **0**, not 0.627. The debate's own discount for it is −0.1%.
- **FGR.PA** (Eiffage): minority interest €1.39bn at book, and the motorway concessions that
  generate much of the cash are about half owned by others and end on fixed dates. SUSPECTED
  material; the size was not reproduced.
- **IEP** consolidates partly owned subsidiaries too.

Fix: subtract minority interest (at least at book value; better, scale cash flow by the parent's
share of net income) and flag names where minorities exceed about 20% of total equity.

### F3 — The cash-flow base lets through one-offs, non-operating cash and lease-blind figures (HIGH, CONFIRMED)

The three-year average was added to damp noise. It does nothing when the series is falling or one
year is not operating cash at all, and the vendor figure leaves lease payments out for companies
reporting under international rules (they sit in financing).

| Pick | Free cash flow, oldest → newest (reporting currency, millions) | What is wrong |
|---|---|---|
| IEP | 3,433 / 552 / **−654** → average 1,110 | 2023 is the investment fund selling securities (net income that year −1,012). Latest year negative. Fair value $24 vs price $4.75 is fiction. |
| PAH3.DE | 1,873 / 1,431 / 700 → 1,335 | Dividend income has fallen 63%. On the latest year alone MoS is 0.14 (before the F1 correction). |
| BOUV.OL | prior year 811, latest 321 (−60%) → 536 | One strong year carries the average. |
| STP.WA | latest **−200**, average +170 | Positive only because of earlier years. |
| TFI.PA | latest 98, average 193 | Same pattern. |
| CEC.DE | 645 / 689 (last two years) | "Other financing" outflows of €689m and €475m are not in the figure; depreciation exceeds capex by about €475m a year, the signature of store leases. Net of those outflows: −44 and +214. |

Valued on the latest year alone, **12 of the 30 picks fall below the basket cut-off** (PAH3.DE, IEP,
FAG.ST, PETR3.SA, CA.PA, EEFT, SOLB.BR, STP.WA, JUN3.DE, EFOR, TFI.PA, BOUV.OL) and two have a
negative value. (Ten would rise, so this is not a one-way bias; the point is that the base is not
checked.)

**The three seats this basket supplied** — all real companies, correctly converted, but all
overstated for the same reason:

| Seat | Screen MoS | What the cash-flow base contains | Rough MoS on a cleaner base | Debate's own discount |
|---|---|---|---|---|
| 0175.HK | 0.658 | 2025 cash flow of CNY 42.7bn is 2.6 times net income: CNY 18.3bn is a working-capital inflow, and the vendor's capex field (CNY 4.0bn) is a quarter of the plant-investment line in the same row (CNY 17.5bn). 7.0 → 23.5 → 42.7bn in three years. | 0.41 – 0.54 | 40.8% |
| 2618.HK | 0.657 | Average CNY 12.4bn against average net income CNY 4.8bn; depreciation CNY 13.0bn vs capex CNY 7.6bn — the warehouse-lease pattern (lease payments not in the figure; SUSPECTED, the vendor has no lease line). | about 0.40 on the latest year's net income; lower on the three-year average | 39.4% |
| DUE.DE | 0.652 | Three straight years of working-capital release (€56m, €110m, €110m = 39% of the three-year cash flow); 2025 net income was −€52m. | about 0.43 (without the release) | 48.4% |

So for the seats the screen's direction is right and the size is about one and a half times too
big. The debate's numbers already reflect that.

Fix: use the lower of the latest year and the three-year average when the latest is more than about
30% below the average; reject a base whose latest year is negative; flag cash flow above about 1.5
times net income; subtract lease repayments where the vendor reports lease liabilities.

### F4 — Growth is "half of return on equity" whatever the company pays out (HIGH, CONFIRMED)

`growth_est = min(max(roe * 0.5, 0.03), 0.25)` (`2936`). Return on equity explodes when equity is
thin, and a company that pays out all its profit cannot grow at half its return on equity.

| Pick | Median return on equity | Median payout | Growth used | MoS published | MoS with growth tied to what is retained |
|---|---|---|---|---|---|
| CGAS3.SA | 158% | 78% | 25% | 0.705 | about 0.42 at 3% (a regulated gas utility) |
| DNLM.L | 110% | 105% | 25% | 0.617 | 0.28 |
| BOUV.OL | 72% | 97% | 25% | 0.610 | 0.32 |
| DMLP | 50% | 119% | 25% | 0.593 | 0.29 |

All four leave the basket. Seven of the top 60 eligible names in the scan sit at the cap.

Fix: growth = return on equity × (1 − payout), capped near 10–12%; ignore return on equity when
equity is below about 10% of assets.

### F5 — One discount rate for every currency (MEDIUM-HIGH; arithmetic CONFIRMED, size of the bias SUSPECTED)

10% and a 2.5% perpetuity are applied to Brazilian reais, Polish zloty, Hong Kong dollars and yen
alike (`2935`, `2943-2944`). The same file lists the Brazilian ten-year yield at 13.9% (`101`), so
Brazilian cash flows are discounted below the local risk-free rate.

- Share of eligible names with MoS above 0.5: Brazil 31% (4 of 13), Norway 17%, Hong Kong 16%, France 14%,
  US 3%, Japan 0%, Switzerland 0%. US names are 41% of the eligible pool and 20% of the top 30.
- Three picks are Brazilian (SBSP3.SA, PETR3.SA, CGAS3.SA; PETR4.SA was a fourth until 11-07). At a
  rate built on the local yield (my assumption: 18.4%, 4% perpetuity) their MoS would be 0.11, 0.18
  and 0.28.

Fix: discount at the local ten-year yield (`_local_risk_free` already exists at `105`) plus a fixed
premium, with terminal growth tied to that currency.

### F6 — Turnover is mostly names disappearing from the scan (MEDIUM, CONFIRMED)

See section 4. 9 of 14 logged exits were scan drop-outs. Three of those nine were fixed-dividend
preference shares valued as if they were ordinary shares (50GP.L confirmed; BP-A.L and BP-B.L are
recognisable as BP's 8% and 9% preference shares, not re-verified), and three more were
participation, savings or second share classes.

### F7 — Nothing checks that a pick can be bought or still has upside (MEDIUM)

- CGAS3.SA traded **100 shares** on the scan day (about R$12,000). CONFIRMED.
- KGN.WA and STP.WA traded about PLN 0.6m and PLN 0.3m. CONFIRMED.
- CEC.DE has crept from €3.95 to €4.64 and now sits at its 52-week high with almost no movement —
  the pattern of an agreed cash offer near €4.60. SUSPECTED (not verified in a filing). If so the
  0.77 MoS cannot be earned.
- JET2.L: the model adds £2.0bn of net cash, but the balance sheet holds £2.16bn of customer money
  paid in advance against £3.29bn of cash. Small next to the cash-flow term; noted. CONFIRMED.

Fix: a minimum traded value per day; skip names under a cash offer; net customer prepayments
against cash.

### F8 — Exits of vanished names are booked at a stale price (LOW-MEDIUM, CONFIRMED)

When a holding is missing from the scan the tracker closes it at the last price it had. PETR4.SA
was booked out at R$58.68 (+32.4%); its close that week was R$45.36 (+2.4%). Recomputing every
fortnight from vendor closes, the basket made **+5.84%** from 09-22 to 11-07 against the tracked
**+6.45%**. Close, but the error is one-sided when a falling name disappears.

### F9 — Smaller points (LOW, CONFIRMED)

- The scan's own `sector_class` field (`2808`, industry text only) disagrees with the live gate
  (`6894`, which also uses the sector). 21 "Financial Services" names carry `operating` and a
  positive DCF MoS in the scan (IBKR, 8601.T, FTK.DE, 6886.HK …). The basket excludes them
  correctly; anything reading the field from the scan will not.
- The forward-earnings gate passes a name with no estimate (default 0.0): FRVIA.PA, IEP, CGAS3.SA,
  CDI.PA, DMLP.
- Peak-cycle demotion works (IEP 0.80 → 0.69, LIGHT.AS 0.66 → 0.60) but is too mild to matter when
  the base is as wrong as IEP's.

### Picks I consider artefacts (9)

SBSP3.SA, PAH3.DE, CDI.PA, IEP, CEC.DE, CGAS3.SA, DNLM.L, BOUV.OL, DMLP.

Real but overstated (7): 0175.HK, 2618.HK, DUE.DE, PETR3.SA, FGR.PA, TFI.PA, STP.WA.

### What is clean

- **Currency.** All 30 picks: price currency, reporting currency and conversion agree. Hong Kong
  names convert yuan at 1.1751 (live 1.1758); London names in pence at 100; everything else 1.0.
  No residue of the dollar bug.
- **Selectivity.** 1,555 names have a usable value, 776 a positive MoS; after the gates about 870
  remain, 315 positive, 37 at or above the cut-off. No ties, 53 distinct values in the top 60, no
  pick at the 0.95 cap (six scan names are, all excluded by gates). The sector cap binds in
  Consumer Cyclical (9 of 9; 1928.HK at 0.653 is shut out).

## 4. Rotation since 2026-09-22

Tracker (fortnightly): 14 entries, 14 exits. Picks file (weekly): 13 of 30 seats changed.

| Exit | Date | Why | Real reason? |
|---|---|---|---|
| GYL.OL, AEGN.AT, TXT.WA | 09-22, 10-10, 10-24 | Missing from the scan | No — data |
| 50GP.L | 10-24 | Missing from the scan. It is a Croda preference share (5.9% dividend, £49m, no longer trading); the price series flips between pounds and pence | No — should never have been valued |
| BP-A.L, BP-B.L | 11-07 | Missing from the scan; preference shares | No — should never have been valued |
| LISP.SW, PETR4.SA, DANR.MI | 11-07 | Missing from the scan; a participation certificate (a 0.72 MoS on Lindt is not credible — SUSPECTED per-share mismatch) and two second share classes that duplicate the ordinary line | No — data |
| EFOR | 10-24 | Price +36%, MoS 0.66 → 0.54 | Yes (re-entered 11-07 after −21%) |
| IMB.L | 10-31 | Price +19%, MoS 0.64 → 0.57 | Yes |
| HOG | 10-31 | Price +19%, MoS still 0.625; pushed out of the capped sector when 0175.HK arrived | Partly — sector cap, by about 0.001 |
| BOUV.OL | 10-31 | Price +14%, MoS 0.569; back in one week later at 0.611 | Whipsaw at the cut-off |
| WPP.L, BETS-B.ST | 10-10, 09-22 | MoS moved 0.005 and 0.016; displaced at the cut-off | Noise |

- **2618.HK (value seat)** carries a picks-file entry date of 10-24 although the tracker has held it
  since 08-21 and no exit was logged. The only code path that drops a name without logging an exit
  is "absent from the scan" (`6999-7002`), so it was missing on 10-19 and returned on 10-24 with a
  reset entry price (9.895 instead of 10.26). Inferred from the code; the 10-19 scan is not kept.
- The five 11-07 entrants (CGAS3.SA, EFOR, BOUV.OL, HRMY, DMLP) filled seats vacated by vanished
  names, at MoS 0.59–0.70; three of the five are artefacts under F4/F7.
- The +0.05 incumbency boost works as designed but cannot help when the name is absent.
- After leaving, exits lagged the world index by 1.1 points on average — leaving was not a mistake.

## 5. What it contributes to the debate

- Grades of the picks: A 5, B 15, C 10. Gates threw out 7 of 30 (forensic: TEP.PA, IEP, FAG.ST,
  LIGHT.AS; numeric: 2333.HK, SBSP3.SA, FGR.PA).
- Screen discount median 65.9%; debate discount median 13.2%. For 7 of 26 the debate sees 5% or
  less (CEC.DE, GIII, KGN.WA, CGAS3.SA, CDI.PA, DNLM.L, TFI.PA).
- Seats supplied: 0175.HK and DUE.DE (regime), DUE.DE and 2618.HK (value). They are three of the
  four picks with the largest debate discount, so the debate is selecting on its own valuation.
- Overlap with other baskets: EPV 12, owner earnings 11, IV15 7, R&D-capitalised DCF 6, Graham 6.
  It is a distinct lens, and 24 of the 30 are non-US names.
- Net: useful as a net for cheap non-US industrials and consumer names; about a third of its
  slots are spent on names the debate then has to dismiss.

## 6. What I could not check

- Only the 11-07 scan exists locally, so week-to-week metric changes rest on the logged entry and
  exit metrics, and the 2618.HK drop-out is inferred.
- Why nine names left the scan universe (share-class clean-up or a data gap) — for the machinery
  reviewer.
- Vendor rows at scan time versus today (PAH3.DE's 2025 share count differs between the two).
- Actual lease payments for 2618.HK, CA.PA, TEP.PA, DNLM.L (the vendor has no such line). For
  CEC.DE the outflow is confirmed; that it is leases is inferred from depreciation against capex.
- The CEC.DE offer; minority interests for the 27 picks whose balance sheet I did not pull; the
  A-share / H-share structure behind 2333.HK; KGN.WA and EFOR in any depth.
- The local-rate figures in F5 use my own premium; the direction is certain, the size is not.

Live data checks used: 15 calls (quotes, profiles, income, balance-sheet and cash-flow statements
for SBSP3.SA, PAH3.DE, 0175.HK, 2618.HK, DUE.DE, IEP, CDI.PA, CEC.DE, JET2.L, FGR.PA, 50GP.L, FX).
