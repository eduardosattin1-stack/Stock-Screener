# Basket audit — `owner_earnings` (Buffett-style owner earnings)

Reviewer: independent basket reviewer, 2026-11-13. Scan audited: 2026-11-07 (3,430 names). Picks file: 2026-11-07.
Everything marked CONFIRMED was reproduced from the scan, the pack, the code or a live FMP statement. SUSPECTED means plausible but not reproduced.

## 1. Verdict

**UNSOUND.** The code computes its own formula without arithmetic or currency errors, but the formula is not owner earnings, and most of the basket is there because of that.

1. **It adds back all depreciation and amortisation but only charges "capital expenditure" on plant.** Lease costs (for non-US reporters), rental-fleet replacement, capitalised contract costs and concession investment are never charged. 13 of 30 picks get more than 40% of their "owner earnings" from this gap, including the one value-book seat the basket supplied (2618.HK), whose margin of safety falls from 60% to about zero once its leases are charged.
2. **One-off gains sit in the earnings base** (4 picks: SPB, PTEC.L, BYD, SOLB.BR), and one pick (SBSP3.SA) is valued on a share count that is five times too small.
3. **Rotation is mostly data events, not metric moves.** 6 of the 10 exits since 2026-09-22 were names missing from that week's scan, booked out at a stale price. That overstates the tracked return since 09-22 by about 1.6 percentage points (tracked +3.9%, from daily closes +2.1%).

A conservative re-ranking (section 3, finding 1) keeps only 8 to 12 of the 30 current picks.

## 2. What the rule computes

Code: `backend/screener_v6.py:2968-2986`; inputs at `2716-2721`, `2856`, `2887-2893`, `2929-2935`.

- **Owner earnings** = 3-year average net income + 3-year average depreciation and amortisation − "maintenance capex". Maintenance capex = 3-year average capital expenditure ÷ (1 + last year's revenue growth, clipped to 0–100%).
- **Fair value** = that figure grown for 10 years at a rate of 40% of return on equity (floor 2%, cap 15%, fading 10% a year), then 2.5% for ever, all discounted at a flat 10%. No debt is subtracted (correct, because net income is after interest). The result is divided by the latest diluted share count and converted to the trading currency.
- In practice fair value is **12.5× to 22.3× owner earnings** (I reproduced both ends), so a name needs an "owner earnings yield" of 10.5% to 18.7% of its price to reach the current cut-off of 57%.

Gates in the selection loop (`6889-6957`): sector applicability (banks and insurers excluded, `883`), structural break or under 5 years of history (`6902`), forward EPS decline of 25% or worse (`6912`), net debt / EBITDA under 3 and Piotroski of 3 or more (`6928`), peak-cycle demotion (`6932-6936`), +0.05 incumbency boost (`6937`), 30% sector cap.

I reproduced the 30 picks exactly from the scan using these rules (0 differences). 1,869 names have a value, 955 pass the gates, 355 are above zero after the peak adjustment. The sector cap does not bind (largest sector holds 8 of a permitted 9). There are no ties at the cut-off.

**Currency handling is clean (CONFIRMED).** All 30 picks have a consistent currency, conversion rate, price and fair value: pence names use ×100 (or ×83.49 for PTEC.L, which reports in euros), 0788.HK and 2618.HK use 1.1751 yuan-to-HKD against a live rate of 1.1758, ODF.OL converts dollars to kroner. No residue of the old "everything is dollars" bug.

## 3. Findings, most serious first

### Finding 1 — Depreciation is added back in full, but the cash that replaces those assets is often never charged. HIGH, CONFIRMED.

`oe = net_income + depreciation - maint_capex` (`2973`). `depreciation` is the cash-flow line "depreciation and amortisation"; `capex` is the line "capital expenditure". These two lines do not describe the same assets in four common situations:

| Situation | Why the charge is missing | Picks | Evidence (live FMP, latest year) |
|---|---|---|---|
| Leases under IFRS 16 (all non-US reporters) | Depreciation of leased stores, warehouses and sites is in D&A; the lease repayment is a financing cash flow, not capex | 2618.HK, CEC.DE, CURY.L, JD.L, SAX.DE, 0788.HK, NOS.LS, FGR.PA, TEP.PA, DNLM.L | 2618.HK: D&A 13.0bn yuan, capex 7.6bn, lease liabilities 18.0bn of which 7.35bn due within a year. CURY.L: D&A £294m, capex £79m, other financing outflow £194m |
| Rental fleets | Fleet depreciation is in D&A; buying replacement stock runs through working capital | UPBD, RENT3.SA, JUN3.DE | UPBD: D&A $1,515m, capex $67m, working-capital outflow $1,457m. RENT3.SA: D&A 5.94bn reais, capex 0.31bn, working-capital outflow 4.67bn |
| Capitalised contract costs | Amortisation is in D&A; the spend is an operating cash flow | KD | D&A $2,775m, capex $608m, net income $198m, working-capital outflow $1,959m |
| Concession assets | Network investment is booked as an intangible, not as capex | SBSP3.SA | "capital expenditure" 0.29bn reais; investment in plant and equipment 13.74bn |

Size of the effect (CONFIRMED, computed from the scan for every gate-passing name):

- Median share of owner earnings that comes from "D&A minus maintenance capex": **33% for the picks, 12% for all candidates** (8% for US candidates, 16% for non-US). The basket is 80% non-US against 68% of the candidate pool.
- 13 picks get more than 40% of owner earnings this way: UPBD (96%), KD (98%), CEC.DE (100%), RENT3.SA (75%), SAX.DE (65%), 0788.HK (64%), 2618.HK (62%), CURY.L (61%), JUN3.DE (59%), FGR.PA (49%), TEP.PA (47%), JD.L (44%), NOS.LS (41%).
- UPBD is the extreme: 3-year average D&A is $1.41bn against a market value of $1.41bn, so the screen reports owner earnings equal to the whole share price each year and a fair value of $334 against a price of $24.
- Sensitivity test: if the add-back is capped at maintenance capex (so D&A can never add more than the capex it is supposed to fund), only **12 of the 30 picks stay in the top 30**; with a median instead of a mean for net income, **8 stay**.

**The supplied seat, 2618.HK (JD Logistics).** Screen fair value HK$27.2, price HK$10.76, margin of safety 60%. Subtracting one year of lease repayment (7.35bn yuan, the current lease liability) from owner earnings of about 12.1bn leaves about 4.75bn, a fair value of about HK$10.5 and a margin of safety of about −2%. This is an estimate: the lease liabilities are confirmed, the annual charge is approximated. The debate reached its own 39% discount by other means, so this does not say the seat is wrong; it says the screen's reason for nominating it was largely an accounting artefact. The other three baskets that carry it (dcf_fcff, epv, iv15_deep_value) share the same leak, because free cash flow also excludes lease repayments.

The leverage gate (`6639-6644`) uses the same inflated figure: UPBD passes at 1.0× net debt / EBITDA only because EBITDA includes $1.5bn of rental-stock depreciation (SUSPECTED: about 6× without it).

**Fix.** Charge what replaces the depreciated assets: subtract the current lease liability (FMP `capitalLeaseObligationsCurrent`) as the annual lease cost; use the larger of `capitalExpenditure` and `investmentsInPropertyPlantAndEquipment`; and cap the net add-back (D&A − maintenance capex) at a fraction of net income, or exclude names where it exceeds net income. Exclude rental and leasing industries, where this method cannot work.

### Finding 2 — One-off gains are in the earnings base. HIGH, CONFIRMED (4 picks).

`net_income` is the 3-year mean of reported net income (`2716`), which includes discontinued operations and disposal gains.

| Pick | Net income, last 3 years (m) | The one-off | Source |
|---|---|---|---|
| SPB | 1,802 / 125 / 100 | FY2023 includes $2,035m from discontinued operations (sale of a division); continuing operations lost $234m | FMP income statement |
| PTEC.L | 105 / −24 / 1,457 | 2025 includes €1,624m from discontinued operations; continuing operations lost €166m | FMP income statement |
| BYD | 620 / 578 / 1,843 | 2025 operating income $877m; $1,453m of other income (a stake sale) | FMP income statement |
| SOLB.BR | 2,093 / 223 / 30 | 2023 figure is ten times the later years (the year of its demerger; cause not pulled live) | scan history |

SPB filed FY2026 on 2026-11-12 (net income $49.5m). The 2023 gain drops out of the window at the next scan, the 3-year mean falls from about $675m to about $91m, and SPB will leave the basket for a reporting-calendar reason.

**Fix.** Use income from continuing operations and a median (or drop the highest year) rather than a mean.

### Finding 3 — SBSP3.SA is valued on a share count five times too small, and its real capex is missing. HIGH, CONFIRMED (1 pick; 85 names scan-wide).

The price is 26.78 reais and the live market value is 94.7bn reais, which implies 3.5bn shares. The statement used for the per-share figure shows 684m (`shares`, `2856`). Market value ÷ (price × statement shares) = **5.14**. The US-listed line trades at $4.84, which confirms the lower post-split price. Every per-share fair value for this name is therefore about five times too high (owner earnings 86%, Graham 94%, IV15 93%, DCF 73%). On top of that its capex is recorded as 0.29bn against 13.7bn actually invested (finding 1), and a 10% discount rate is applied in a country whose 10-year yield the code itself lists as 13.9% (`101`).

Scan-wide, 85 names have a market value more than 1.5× what price × statement shares implies (examples: DRX.L 93×, NRP.AS 19×, 8035.T 4.9×, TAEE3.SA 3.0×, ALUP3.SA 4.6×). Most are stopped by other gates today; SBSP3.SA is not. The debate's numeric gate did reject it.

**Fix.** Derive the share count from market value ÷ price, or skip per-share methods when the two disagree by more than 1.5×.

### Finding 4 — The growth rate comes from return on equity, so a thin equity base buys the top multiple. MEDIUM, CONFIRMED (4 picks).

`growth_oe = min(max(roe * 0.4, 0.02), 0.15)` (`2974`). Companies that have shrunk their equity through buy-backs or write-downs show a very high return on equity and receive 15% growth and a 22× multiple regardless of how the business is actually growing.

| Pick | Return on equity | Multiple applied | Margin of safety as screened | At the 12.5× floor multiple |
|---|---|---|---|---|
| IMB.L (tobacco) | 0.41 | 22.3× | 60% | 29% |
| DNLM.L | 1.10 | 22.3× | 60% | 28% |
| BYD | 0.43 | 21.9× | 67% | 42% |
| VRLA.PA | 0.30 | 20.4× | 63% | 39% |

None would clear the 57% cut-off on the floor multiple. **Fix.** Tie growth to the de-peaked revenue-per-share trend already computed for IV15 (`2909-2918`) and cap it there.

### Finding 5 — The method cannot see decline, and uses one discount rate for every country. MEDIUM, CONFIRMED.

Growth never goes below 2% for ten years plus 2.5% for ever, discounted at 10% (`2935`, `2974-2981`). A shrinking business is valued at 12.5× its trailing three-year average at the very least. This is the main answer to the question of why 14 of 30 picks are graded "pass" (section 5). Two Brazilian picks (SBSP3.SA, RENT3.SA) are discounted at 10% against a local 10-year yield of 13.9%; at 16% with 4.5% terminal growth the floor multiple is 7.5× instead of 12.5×.

**Fix.** Discount at the local 10-year yield plus a fixed premium (the table exists at `98-103`), and let the growth floor be zero when the revenue trend is negative.

### Finding 6 — Exits of names missing from the scan are booked at a stale price. MEDIUM, CONFIRMED.

See section 4 for the rotation detail. Booked exit price against the vendor close on the exit date:

| Exit | Booked | Actual close | Effect on the basket |
|---|---|---|---|
| UPBD, 09-22 | 18.98 | 16.78 | +0.39 pt overstated |
| DFH, 10-10 | 11.40 | 9.38 | +0.59 pt |
| AEGN.AT, 10-10 | 11.39 | 10.90 | +0.14 pt |
| TXT.WA, 10-24 | 40.00 | 38.10 | +0.16 pt |
| CMIG4.SA, 11-07 | 11.67 | 10.39 | +0.37 pt |
| LISP.SW, 11-07 | 8,400 | 8,635 | −0.09 pt understated |

Net about **+1.6 points** of overstatement since 09-22. Tracked NAV 107.88 → 112.06 (+3.87%); an equal-weight chain of the actual holdings from daily closes gives +2.05% (excluding the 50GP.L price glitch). The priced periods agree to within a few tenths of a point, so the NAV arithmetic itself looks right; the gap is the stale exit prices. **Fix** (shared machinery): price every exit from the vendor close when the name is absent from the scan.

### Finding 7 — Smaller defects. LOW, CONFIRMED by reading the code.

- The fallback `if maint_capex <= 0: maint_capex = capex * 0.7` (`2971-2972`) can never help: maintenance capex is only zero when capex is zero, and 70% of zero is zero. A name with no capex on file is charged nothing.
- Maintenance capex uses 3-year average capex but last year's revenue growth only (`2969-2970`), so growth bought through an acquisition shrinks the maintenance charge.
- Working capital is not charged. DFH (a homebuilder, free cash flow negative) reads 75% because land and inventory are its real reinvestment.
- The peak-cycle demotion is a no-op when average operating profit is not positive: KD is flagged PEAK_CYCLE with a scale of 1.0 (`2761`), so it is not demoted.
- 50GP.L sat in this basket from 2026-08-21 to 2026-10-24 at a 92% margin of safety. FMP describes it as "Croda International Plc", ISIN GB0002343159, market value about £49m, not actively trading, average volume 1,495: it is Croda's preference share valued on the whole group's accounts. It is not in the 11-07 scan.

### Which picks are artefacts

| Group | Picks |
|---|---|
| Clear artefacts (9) | UPBD, KD, RENT3.SA, CEC.DE, SBSP3.SA, SPB, PTEC.L, BYD, SOLB.BR |
| Largely inflated by leases or other uncharged D&A (9) | 2618.HK, CURY.L, SAX.DE, 0788.HK, JD.L, JUN3.DE, NOS.LS, FGR.PA, TEP.PA |
| In only because of the return-on-equity growth cap (3, besides BYD) | IMB.L, DNLM.L, VRLA.PA |
| Working capital not charged (1) | DFH |
| Rank for the reason the method intends (8) | CMCSA, ODF.OL (cyclical peak, demoted but still in), FAG.ST, LIGHT.AS, BETS-B.ST, ITV.L, MMT.PA, TFI.PA |

CEC.DE is also trading at 4.53–4.64 euros, its 52-week high, with a debate discount of −0.7%; it looks pinned to an agreed offer (SUSPECTED), so a 73% margin of safety is not available to anyone.

## 4. Rotation since 2026-09-22

Tracker rebalances: 10-10, 10-24, 11-07. Ten exits and ten entries in seven weeks for 30 seats.

| Exit | Date | Metric at entry → exit | What happened | Real or data? |
|---|---|---|---|---|
| EMBRAC-B.ST | 10-10 | 0.74 → 0.52 | Price +21% | Real |
| BBWI | 10-24 | 0.64 → 0.55 | Price +24% | Real |
| HOG | 11-07 | 0.62 → 0.51 | Price +21% in four weeks | Real |
| 2618.HK | 10-10 | 0.615 → 0.621 | Left with a higher metric than it entered and than all four names that replaced it; back on 10-24 | Not the metric. SUSPECTED gate flip: its Piotroski score is exactly 3, the minimum |
| DFH | 10-10 | 0.70 → not priced | Missing from that scan; in the picks file it had already been dropped on 09-26 with a metric of 0.77; back on 11-07 at 0.75 | Data |
| AEGN.AT | 10-10 | not priced | Not in the scan | Data |
| 50GP.L | 10-24 | not priced | Preference share, vendor price flips between pounds and pence | Data |
| TXT.WA | 10-24 | not priced | Not in the scan | Data |
| LISP.SW | 11-07 | not priced | Not in the scan | Data |
| CMIG4.SA | 11-07 | not priced | Not in the scan (the other share class, CMIG3.SA, is) | Data |

- **3 of 10 exits were real metric moves; 6 were names absent from that week's scan; 1 is unexplained.**
- Of the 10 entries, 5 are re-entries of names that had left within the previous seven weeks (UPBD, DFH, RENT3.SA, NOS.LS, 2618.HK). Only RENT3.SA came back for a real reason (price −19%, metric 0.58 → 0.68).
- UPBD was out from 09-22 to 11-07 with a metric of about 0.93 throughout and rose about 50% from its real exit-date close. DFH rose 28%. The pack's "+7.2% versus ACWI after exit" is mostly these two data exits.
- The incumbency boost works as designed at the bottom: NOS.LS (0.573) and MMT.PA (0.584) hold their seats against FDJU.PA (0.587) and WWI.OL (0.574). Nineteen challengers sit within 0.05 below the lowest incumbent, so a price move of about 12% changes a seat. That is reasonable. The boost cannot help when a name vanishes from the scan.
- The five exits logged on 09-22 belong to the reconstruction and were not judged. Two of them (WWIB.OL, PETR4.SA) carry an identical exit metric of 0.5948, which looks like a reconstruction artefact (SUSPECTED).

## 5. What it contributes to the debate

| Measure | Value |
|---|---|
| Grades of the 30 picks | A 4, B 12, C 14 (47% "pass"; the next highest basket is epv at 40%, the rank-based baskets are 17–27%) |
| Thrown out by the debate's gates | 10: forensic gate 6 (KD, TEP.PA, FAG.ST, DFH, BETS-B.ST, LIGHT.AS), numeric gate 4 (SBSP3.SA, FGR.PA, BYD, NOS.LS) |
| Median discount: screen vs debate | 66% vs 12% |
| Seats supplied | 2618.HK (value book), also nominated by dcf_fcff, epv and iv15_deep_value |
| Overlap | 16 of 30 shared with epv, 11 with dcf_fcff, 9 with rd_capitalized_dcf; 8 names appear in no other basket |

**The screen's number does not separate good from bad.** Median screen margin of safety by grade: C 70%, A 66%, B 65%. Median debate discount: C 2.4%, B 12.0%, A 28.5%. The names the screen likes most are the ones the debate likes least.

**Why 14 are graded "pass":**

| Cause | Count | Names |
|---|---|---|
| Deteriorating business flagged by the forensic gate (management-credibility score 2, trend deteriorating); a 3-year trailing average with a 2% growth floor cannot see it | 5 | TEP.PA, FAG.ST, LIGHT.AS, BETS-B.ST, DFH |
| Uncharged D&A (finding 1); the debate finds no discount | 3 | KD, CEC.DE (−0.7%), JD.L (−0.4%) |
| One-off gain in earnings (finding 2) | 2 | SPB, BYD |
| Structural decline the formula cannot model (thesis broken or moat eroding) | 2 | TFI.PA, MMT.PA (−17.7%) |
| Return-on-equity growth cap (finding 4) | 1 | DNLM.L (0.3%) |
| Cyclical peak | 1 | ODF.OL |

So roughly 6 of the 14 are measurement artefacts of this method and 8 are cheap-looking businesses in decline that the method has no way to recognise. The high pass share is a property of the formula, not bad luck.

**Is it a distinct lens?** Not much. EPV uses the same add-back and the same maintenance-capex estimate (`2997-3000`), which is why they share 16 names. Its 8 unique names are mostly lease-heavy or thin-equity cases (CURY.L, SAX.DE, 0788.HK, NOS.LS, IMB.L, VRLA.PA) plus ODF.OL and ITV.L.

**The record.** Tracked +12.06% for the year, of which +9.44% was carried in from before the reconstruction and cannot be checked. Since 09-22: tracked +3.87%, about +2.1% from actual closes (finding 6). Picks are +3.8% on average since entry and 77% beat ACWI, over windows of seven weeks or less; C-graded picks did as well as A-graded ones. That is too short and too undifferentiated to count as evidence that the screen ranks anything.

## 6. Fixes, in order

1. Charge lease repayments and use the larger capex field; cap or exclude names whose owner earnings are mostly uncharged D&A; exclude rental and leasing businesses (finding 1).
2. Use continuing-operations income and a median across years (finding 2).
3. Reconcile the share count with market value ÷ price before any per-share value (finding 3).
4. Take growth from the revenue trend, not return on equity; allow zero growth (findings 4 and 5).
5. Discount at the local yield plus a premium (finding 5).
6. Price exits of names missing from the scan from the vendor close; investigate why liquid names (UPBD, DFH) drop out of a weekly scan (finding 6, shared machinery).
7. Remove the dead fallback; charge working-capital growth for builders (finding 7).

After fixes 1 to 4 this basket and EPV should be re-compared; if they still share half their names, one of them is redundant.

## 7. What I could not check

- **Earlier scans.** Only the 2026-11-07 scan is on disk, so the reasons for the DFH, UPBD and 2618.HK exits are inferred from the exit records and today's gate values, not observed.
- **Exact lease depreciation.** FMP's standard statements do not split it out. I used the current lease liability and the financing outflow as proxies; the adjusted fair values for 2618.HK and CURY.L are estimates.
- **My decomposition of owner earnings** rebuilds net income from the scan's per-year history block, which differs slightly from the field the code averages (2618.HK: 616 / 6,198 / 6,647 in the scan against 1,167 / 6,198 / 6,890 live). Shares of owner earnings quoted above are accurate to a few points, not exactly.
- **Solvay's 2023 figure** was read from the scan history, not pulled live.
- **The pre-reconstruction record** (+9.44% to 09-07) and the tracker's NAV code path (`6154-6510`), which I did not read; the stale-exit finding rests on the logged prices against daily closes.
- **Whether CEC.DE is under an agreed offer** — inferred from price behaviour only.
- Live data calls used: 15 (one batch quote for 8 names, one FX pair, 13 statement or profile pulls).
