# Basket audit — `ev_gross_profit` (gross profit / total assets)

Reviewer scope: the basket only. Scan used: 2026-11-07 (3,430 names), plus the seven earlier weekly
scan files read from GCS (`scans/2026-09-22_global.json` … `2026-10-31_global.json`, read-only).

## 1. Verdict

**UNSOUND as a feeder for the value book** — the arithmetic is right, but (a) about a quarter of the
picks rank high because of how the data vendor classifies costs, not because of the economics,
(b) every one of the nine exits since 2026-09-22 was a data event, none was the metric moving, and
(c) the number carries no valuation at all yet is typed "deep value" downstream and given intake
priority.

The three things that most justify it:

1. **7 of 30 picks are confirmed vendor artefacts.** For contractors, consultancies, a hospital
   operator, a freight broker and an interdealer broker, the vendor's "gross profit" is close to
   revenue because labour and subcontract costs are filed outside "cost of revenue". Veidekke
   (VEI.OL) is ranked #4 of 3,286 on a gross profit that equals its revenue; its real figure puts it
   in the bottom third.
2. **Rotation is 100% noise.** 9 exits since 2026-09-22: 8 because the name was missing from that
   week's scan, 1 because a third-party quality score flipped. The incumbency boost is four times
   wider than the whole basket, so the basket is frozen and only changes when a seat is vacated.
3. **It is a quality rank with no price in it.** Zero seats in either book, median debate discount
   5.7% (second-lowest of the twelve), 9 of 28 priced picks at or above the debate's fair value.

Two of these (the scan-universe flicker and how missing names are booked) are shared machinery, not
special to this basket; they are reported here because they are the *only* thing that moves it.

## 2. What the rule computes

For every stock with total assets above zero, it divides the latest annual gross profit by the
latest annual total assets (`gp_ta`), sorts the whole scan on that ratio, and converts each name's
position into a number between −0.15 (worst) and +0.15 (best) stored as `ev_gross_profit_mos`
(`screener_v6.py:6591-6607`). The basket is the top 30 by that number after two shared gates (net
debt / EBITDA below 3, Piotroski score of at least 3 — `:6928`) and a 30%-per-sector cap.

Checks on the rule itself — all CONFIRMED:

| Check | Result |
|---|---|
| Formula | Correct. I recomputed the rank for all 3,286 names: 0 mismatches against the scan. |
| Units / currency | Clean. Gross profit and total assets are multiplied by the same `fx_to_price` (`:2882-2883`), so the ratio is unit-free. No pence/pound or dollar residue in this basket. |
| Period | Single latest annual income statement over latest annual balance sheet (`:2689-2691`). No averaging, so one unusual year counts in full. |
| Is it the method it claims? | It is gross profit over assets (Novy-Marx), as the code comments and the front-end description say. It is not an enterprise-value multiple; only the key is misleading. |
| Ties | None that matter: 5 exact pairs in the whole scan, none near the top. |
| The "margin of safety" | Not a margin of safety. It is a rank position. Every pick shows 14.6%–15.0%. |

## 3. Findings (most serious first)

### F1 — The vendor's "gross profit" is not comparable across companies (HIGH, CONFIRMED)

**What is wrong.** The factor assumes gross profit = revenue minus the direct cost of delivering it.
The vendor's `grossProfit` field does not hold to that for companies that report costs by type
(materials, staff, other) rather than by function — common in Norway, Switzerland and for service
businesses. Staff and subcontractor costs land in "other expenses", "cost of revenue" is tiny, and
gross profit comes out near revenue. The ratio then measures *sales per unit of assets* for a
low-margin labour business, which is the opposite of what the factor is meant to find.

**Evidence** (live vendor income statements, latest annual):

| Pick | Rank | Revenue | "Cost of revenue" | "Gross profit" | Operating profit | What happened |
|---|---|---|---|---|---|---|
| VEI.OL (Veidekke, contractor) | 4 | 43,143m | 41,168m | **43,143m** | 1,956m | Gross profit equals revenue although the vendor itself carries 41.2bn of cost. Revenue − cost = 1,975m → ratio 0.10, not 2.20 (scan median 0.18). |
| NRC.OL (rail contractor) | 10 | 6,553m | 216m | 6,337m | 141m | "Cost of revenue" is exactly the depreciation line (216m). Net margin 0.4%. |
| CFT.SW (interdealer broker) | 32 | 1,118.6m | 21.181m | 1,097.4m | 161.5m | Same: "cost of revenue" equals depreciation (21.181m). Broker pay sits in other expenses. |
| MULTI.OL (engineering consultancy) | 13 | 6,625m | 968m | 5,657m | 390m | 4,890m of staff cost outside cost of revenue. |
| BRKN.SW (electrical contractor) | 6 | 1,201.5m | 381.7m | 819.9m | 65.6m | Materials only; 717m of other (staff) cost outside. |
| UHS (hospitals) | 29 | 17,365m | 1,659m | 15,706m | 1,994m | Supplies only; 8,233m of salaries filed as SG&A. |
| HUBG (freight) | 18 | 3,946m | 577m | 3,369m | 140m | The vendor's own prior year shows cost of revenue 3,699m and gross profit 504m (12%). On that basis the ratio is about 0.18, not 1.17. Also stale: latest annual on file is FY2024 (every other pick is FY2025 or FY2026). |

In the scan as a whole 3.0% of names have gross margin ≥ 80% with operating margin below 10%; in
this basket's top 100 it is 15%. 82 names in the scan carry a gross margin of exactly 100%.

Sensitivity: ranking the same universe on operating profit over assets (which does not care where a
cost is filed) keeps 14 of the 30 picks in the top 100 and drops 13 out of the top tenth entirely
(NRC.OL to 2,293rd, HUBG 1,941st, MULTI.OL 1,051st, VEI.OL 898th).

**Affects:** 7 of 30 current picks — VEI.OL, NRC.OL, MULTI.OL, BRKN.SW, HUBG, UHS, CFT.SW.

**Fix.** (1) Compute gross profit as revenue − cost of revenue and drop the name when the vendor's
`grossProfit` disagrees with it (catches VEI.OL). (2) Drop or flag names where cost of revenue is
within a few percent of depreciation, or where gross margin ≥ 80% while operating margin < 10% and
SG&A + R&D do not explain the gap. (3) Better: rank on operating profitability (operating income
plus R&D, over assets), which is immune to the classification. (4) Carry the statement date into the
scan row so a stale year is visible.

### F2 — Every exit since 2026-09-22 was a data event; the basket is frozen by the incumbency boost (HIGH, CONFIRMED)

**What is wrong.** Two things combine.

*The boost.* Incumbents get +0.015 (`:6869-6873`, "10% of amplitude"). One rank place is worth
0.0000913, so the boost equals **164 rank places**. The entire basket spans 0.1461 to 0.1498 — a
range of 0.0037, a quarter of the boost. No challenger can score above 0.150, so an incumbent cannot
be displaced until it falls outside roughly the top 165 of 3,286. Entries happen only when a seat
is vacated.

*What vacates seats.* The metric comes from annual statements and barely moves (14–42 names out of
~3,500 change `gp_ta` in any week). Seats open because names disappear from the scan or fail a gate.

**Evidence.** I rebuilt the selection from the eight weekly scan files with the production rules;
it reproduces every entry and exit in the picks file and the tracker. Results:

| Scan | Left the picks | Why (from that week's scan row) | Replaced by |
|---|---|---|---|
| 09-26 | YELP, LZ | Both **absent from the scan** | CORT (rank 39), GRG.L (41) |
| 10-24 | TXT.WA | **Absent from the scan** | TRST.L (10) |
| 10-24 | GUBRA.CO | Piotroski score 7 → 2 in one week; `gp_ta` unchanged at 1.931 | YELP (12) |
| 10-31 | TRST.L | **Absent from the scan** | KFRC |
| 11-07 | SBR, WINA, TEAM, KFRC | All four **absent from the scan** | BRKN.SW, TRST.L, RL, INSP |

Nine exits: eight absent, one gate flip, zero because gross profitability moved.

Lock-out: YELP was back in the scan on 10-03 at rank 11 and stayed locked out for three scans
(10-03, 10-10, 10-19) behind CORT (rank 40–42) and GRG.L (42–44). The tracker therefore sold YELP at
18.59 on 10-10 and re-bought it at 19.99 on 10-24. LZ returned on 10-10 at rank 33 and never got
back in.

Why names vanish (SUSPECTED cause, CONFIRMED pattern): the universe is built with a market-cap
floor (`:1411`, `marketCapMoreThan`). The flickering names all sit at about 1.0bn in listing
currency: TRST.L 1.01, YELP 1.00–1.08, WINA 1.02, SBR 1.03, KFRC 1.03, TXT.WA 1.02, LZ 1.15. Of 72
names that were ever in this basket's top 60 or so, 12 were missing from at least one of the eight
scans. TEAM (48.5bn) does not fit the pattern; I could not establish why it dropped out.

Why the gate flips (CONFIRMED pattern): the Piotroski score is read from the vendor
(`:2246`). Until 10-19 about 45 names a week changed score with unchanged fundamentals; from 10-24
it is about 500 a week, with 10–35 names crossing the ≥3 gate each week.

**Affects:** the whole basket. Current picks that have themselves flickered: YELP, TRST.L.

**Fix.** (1) For rank methods express the boost in rank places (for example 10–15 places), not a
share of amplitude. (2) Treat "absent from this scan" as "hold, unchanged" for a grace period rather
than as an exit; a name missing one week should not lose its seat. (3) Put a buffer on the universe
floor (admit at 1.0bn, drop only below, say, 0.8bn). (4) Do not let a one-week swing in a
third-party score evict a holding; require two consecutive scans.

### F3 — The tracked return is overstated because vanished names are booked flat (HIGH, CONFIRMED)

**What is wrong.** When a held name is absent from the scan on a rebalance day it is carried at its
last known price — a 0% contribution (`:6304-6309`) — and its exit is booked at that stale price
(`:6338-6343`). Names that vanish are disproportionately names that fell.

**Evidence** (equal-weight period returns recomputed from scan prices, vanished names marked from
the daily close cache):

| Period | Booked | Actual | Names booked flat (actual move) |
|---|---|---|---|
| 09-22 → 10-10 | −1.96% | −1.96% | none (matches NAV to 0.01pp) |
| 10-10 → 10-24 | +2.20% | +2.04% | TXT.WA (−4.8%) |
| 10-24 → 11-07 | **+0.73%** | **−0.86%** | TEAM (−32.5%), SBR (−10.0%), WINA (−5.2%) |

Since 09-22 the booked figure is +0.93%; the actual is about −0.8%. Year-to-date reads 9.84% and
should read about 7.9%. The exit log is wrong the same way: TEAM is logged as a +16.3% winner
(exit 227.61); it closed at 153.68 the day before, which is −21.5% from entry.

**Affects:** the basket's headline return and 5 of its 22 logged exits (`exit_metric: 0.0`,
`unpriced_exit`). Otherwise the record is consistent with the picks' price moves.

**Fix.** Mark a vanished name from an independent price source (the close cache already exists)
before booking the period and the exit; never from the stale price.

### F4 — A quality rank is described and routed as a value signal (MEDIUM, CONFIRMED)

**What is wrong.** Nothing in the number refers to price. Downstream it is treated as cheapness:

- `weekly_opus_refresh.py:271-272` puts `ev_gross_profit` in `DEEP_VAL`; line 6236 then types a
  name whose only basket is this one as a `deep_value` signal. 24 of the 30 picks are in no other
  basket.
- `weekly_opus_refresh.py:6527-6531` gives its names +2 intake priority as a "cash-earnings screen
  family", justified by a year-to-date return that F3 shows is overstated. Line 1436 lists it as a
  "recovery family".
- `screener_v6.py:7039` writes `fair_value = price × (1 + mos)` into the picks file — for RMV.L,
  555.4 × 1.1498 = 638.6. That is the price plus a rank, not a valuation.
- `screener_v6.py:6759, 6779-6782` feeds the same price × (1 + rank) into the convergence basket as
  one of its fair-value "votes". It always sits within 15% of the price.
- Front end: the holdings table heads the column "GP/Assets MOS" (`frontend/app/page.tsx:1558`) and
  prints 14.6%–15.0% for every holding; exits with a missing metric print "0.0%"
  (`:3584-3590`). The basket card shows "GROSS MARGIN" rather than the ratio actually ranked
  (`:365-367`). The written description (`methodologiesConfig.ts:83-89`) and the stock page are
  accurate.

**Evidence that it does not find value.** Picks' median price / free cash flow 18.6 against 14.8
for the scan. Median discount to the debate's own fair value 5.7% (dcf 13.2%, rd-dcf 18.2%,
iv15 17.6%). Nine picks at or above debate fair value (VEI.OL −20.9%, BONEX.ST −22.0%, APOTEA.ST
−13.7%, GRG.L −12.4%, FOUR.L, CARG, CHWY, UHS, SEZL). No seat in either book; one value runner-up
(BKNG).

**Fix.** Remove it from `DEEP_VAL` and the +2 tilt; type it as quality. Stop emitting `fair_value`
for rank methods and stop feeding rank-derived values into convergence. Label the column "rank".
If it stays in a funnel that feeds a value book, make it what the original research recommends:
profitable *and* cheap — rank on this, then require a valuation method to agree, or intersect with
the true EV / gross profit basket once that one is repaired (see the note at the end).

### F5 — A single year counts in full: one-off income buys a top seat (MEDIUM, CONFIRMED for a former pick, SUSPECTED for a current one)

**Evidence.** GUBRA.CO held a seat until 10-24 on gross profit of 2,549m against 164.5m the year
before (a one-time licence payment); it left only because of the score flip in F2 and still ranks
5th. BCRX (rank 8, current pick): revenue 450.7m → 874.8m in one year, net margin from −20% to
+30%; I did not confirm what drove it.

**Fix.** Use a two- or three-year average of gross profit, or cap the year-on-year jump that can
count.

### F6 — "Applies to every sector" lets non-comparable businesses in; the gates keep junk out only by luck (LOW–MEDIUM, CONFIRMED)

- Financials are admitted (`:895`); the original factor excludes them. Banks never rank (median
  ratio 0.033), so in practice the door is open only to platforms, lenders and insurers whose
  "gross profit" is revenue before the real cost of the business (credit losses, claims). Current
  picks: AJB.L (gross margin 100%), SEZL, plus DAVE and CFT.SW which are finance businesses filed
  under other sectors. An insurer (LDA.MC, premiums counted as gross profit) is 57th.
- The two highest-ranked names in the scan are not operating companies: PBT (a royalty trust, ratio
  8.6 on 1.9m of assets) and BIPI (a listed Brookfield note trading at 15 with a 1.28 coupon,
  carried by the vendor as a company). Both are excluded only because their Piotroski score is
  below 3. SBR, another royalty trust, scored 4 and held the #1 seat from August until it vanished
  from the scan on 11-07.
- At the extreme the ratio measures a tiny asset base as much as profitability (RMV.L 3.3, VRSN
  with negative equity). Those are genuine businesses; the point is that the top 1% of this ratio
  is dominated by denominators.

**Fix.** Exclude financial, insurance and trust/note structures explicitly; require a minimum asset
base relative to revenue or rank within sector.

### Current picks by cause

| Group | Names |
|---|---|
| Vendor cost-classification artefact (F1) — CONFIRMED | VEI.OL, NRC.OL, MULTI.OL, BRKN.SW, HUBG, UHS, CFT.SW |
| Possible one-off year (F5) — SUSPECTED | BCRX |
| Finance-type business, gross profit not comparable (F6) — SUSPECTED | AJB.L, SEZL, DAVE |
| There for the intended reason (real cost of goods, high gross profit on a small asset base) | RMV.L, FOUR.L, YELP, DNLM.L, CARG, CHWY, VRSN, BONEX.ST, GAW.L, APOTEA.ST, TPR, BKNG, ANF, AOF.DE, CORT, GRG.L, TRST.L, RL, INSP |

## 4. Rotation since 2026-09-22

- 09-22 itself (15 in, 15 out) is the reconstruction and a change of universe, not a signal.
- After that: 9 exits on the weekly picks cadence, all data events (table in F2). The tracker, on
  its 14-day cadence, logged 7 of them.
- The picks file's own exit list shows only one (GUBRA.CO): an exit is not recorded there when the
  name is absent from the scan (`:7000-7002`), which is exactly the case for the other eight.
- After leaving: names that vanished kept falling (TEAM −32%, SBR −10%, WINA −5%, TXT.WA −5% within
  two weeks). The pack's "+3.3% after exit against ACWI" is dominated by the fifteen 09-22
  reconstruction exits and should not be read as evidence the exits were good or bad.
- The incumbency boost is not damping noise; it is converting a one-week data gap into a multi-week
  lock-out (YELP, LZ).

## 5. What it contributes to the debate

- 30 picks, 24 of them in no other basket — about a tenth of the 249-name debate universe. It is a
  distinct lens.
- Grades: 2 A, 22 B, 6 C. Value conviction: 6 at 4, 16 at 3, 8 at 2 or below. Two picks excluded by
  the forensic gate (HUBG, CORT), two rejected by the numeric gate (FOUR.L, NRC.OL).
- Seats supplied: none in either book.
- The six names it shares with other baskets are five London listings (RMV.L, DNLM.L, FOUR.L,
  GAW.L, TRST.L) and UHS — see the note below on why the London overlap is not real agreement.
- Net: it surfaces good businesses the value methods would not, but at prices the debate mostly
  regards as full. On the evidence of the debate's own reliability review (grades filter, they do
  not rank), a basket whose picks mostly land at B with a 5.7% discount adds debate cost without
  adding seats.

## 6. What I could not check

- Why TEAM, INDV and MC dropped out of single scans (not explained by the market-cap floor).
- What drove BCRX's revenue jump, and whether DAVE's and SEZL's credit losses sit above or below
  the vendor's gross profit line.
- Why the vendor's Piotroski score became ten times more volatile from 2026-10-24.
- Anything before 2026-09-22 (history lost).
- The live front end: labels were read from source, not from the rendered page.

## Note for the other reviewers (outside this basket, CONFIRMED)

For London listings priced in pence the scan holds `market_cap` in pounds but `net_debt`, `ebit` and
`gross_profit` in pence. RMV.L: market cap 4.00bn, net debt −3.57bn (it is −35.7m pounds), EV / EBIT
stored as 0.016 and EV / gross profit as 0.010; the real figures are about 14.8 and 9.3. In the
2026-11-07 picks file **29 of 30 `ev_gp` picks and 24 of 30 `acquirers_multiple` picks are `.L`
names.** This basket is unaffected because its ratio divides two numbers in the same unit.
