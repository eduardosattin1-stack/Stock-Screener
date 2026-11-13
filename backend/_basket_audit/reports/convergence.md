# Basket audit — `convergence` (cross-method agreement)

Reviewer scope: `backend/screener_v6.py` 6740-6803 (the rule), 6875-7103 (selection, exits), 6290-6363
(tracker close), pack `packs/convergence.json`, scan `latest_global.json` (2026-11-07, 3,430 names).
Every number below was recomputed from the scan or the pack unless marked SUSPECTED. My reproduction of
the rule matches the scan exactly: 40 qualifiers, 0 mismatches, identical `consensus_mos` values.

---

## 1. Verdict

**UNSOUND.** The code does what its comment says, but what it says is not "several independent
valuation methods agree".

1. **Three of the (up to) eleven "votes" are the share price in disguise.** They are `price x (1 + rank
   score)` and can only ever land between 0.80x and 1.20x the price. Among the 40 qualifiers they fall
   inside the agreement band 117 times out of 120. Remove them and only 11 of the 30 current picks still
   qualify. Sixteen of the 30 picks have three or fewer real valuation methods inside the band.
2. **Qualification is a narrow price window with hard edges and no incumbency protection.** A pick must
   be at least 15% below the median estimate, but not so far below that the three price-anchored votes
   drop out of the band. 23 of 30 picks lose their seat on a price move of 10% or less (8 of 30 on 5% or
   less). Names are expelled both when they rise a little and when they get cheaper. This, not news, is
   what drives the turnover.
3. **The protective gates that guard the six feeder methods are not applied here.** 8 picks carry the
   structural-break flag that bars a name from every earnings-based basket, 5 sit on peak-cycle earnings
   without the normalisation the feeder baskets apply, 5 are banks/insurers valued by methods the code's
   own table marks as not applicable, one company (ANTA) holds two seats, and methods that return a
   negative value silently abstain instead of voting "no".

---

## 2. What the rule computes

For each stock it collects up to eleven "fair value" numbers (`screener_v6.py:6757-6782`):

- six model values: DCF, R&D-capitalised DCF, owner earnings, EPV, Graham, IV15 — only if positive;
- the Buffett fair value — only if positive;
- the analyst price target — only if present (no non-US pick has one);
- three "derived" numbers: `price x (1 + mos)` for the acquirer's-multiple, earnings-yield-gap and
  GP/assets baskets, where `mos` is a centred percentile rank (+/-0.20, +/-0.125, +/-0.15).

It takes the **median**, counts the share of numbers within +/-25% of the median ("agreement"), and
sets `consensus_mos = (median - price) / price`. A name qualifies when there are at least 6 numbers,
agreement is at least 0.60, `consensus_mos` is at least 0.15 and there are at least 5 years of history
(`:6783-6795`). Qualifiers are ordered by `min(mos, 0.50) x agreement^2` (`:6800`, used at `:6953-6956`)
and the top 30 are taken subject to the 30%-per-sector cap.

Two things to know when reading its numbers:

- `consensus_mos` is **upside to fair value**, `(FV - price) / price`. Every other value basket uses
  **discount to fair value**, `(FV - price) / FV` (`calc_mos`, `:2923-2926`). The 15% floor is a 13%
  discount; the basket's median pick (0.22) is an 18% discount.
- The incumbency boost is deliberately switched off for this basket: line 6956 overwrites
  `_temp_mos` (which held `eff_mos + boost`) with the raw score.

---

## 3. Findings, most serious first

### F1 — Three "methods" are price-anchored pseudo-votes; the agreement is largely manufactured. HIGH, CONFIRMED

**What is wrong.** The three derived numbers are not valuations. Each is a cross-sectional rank
re-expressed as a price (`:6779-6782`). By construction they sit at 0.80-1.20x (acquirer's),
0.875-1.125x (earnings-yield gap) and 0.85-1.15x (GP/assets) of the current price — confirmed as the
min/max across the scan. One of them (GP/assets, `:6591-6607`) is a quality rank, not a price measure
at all; its rank correlation with every valuation method is between -0.17 and +0.15. The earnings-yield
vote is issued to all 3,430 names with no eligibility test (`:6519-6529`), loss-makers included.

**Evidence.**

| Check | Result |
|---|---|
| The three derived numbers within 25% of each other, whole scan | 96%, 99% and 100% of names (pairwise) |
| Derived votes inside the band, 40 qualifiers | 117 of 120 (acquirer's 40/40, EY gap 40/40, GP/assets 37/40) |
| Graham inside the band, 40 qualifiers | 7 of 40 (it is typically 2-5x the price) |
| IV15 inside the band | 8 of 38 |
| Real valuation methods inside the band per qualifier | 3 or fewer for 25 of 40 (16 of the 30 picks) |
| Qualifiers if the three derived votes are removed (same floors) | 32, of which only 11 are among today's 40 |
| Current picks that survive that removal | 11 of 30: 2020.HK, 82020.HK, WFRD, EVO.ST, 8725.T, ELEC.PA, SFD, MOH, GNTX, ORI, BBWI |

A typical pick has 10 numbers and needs 6 in the band. Three arrive for free from the price, so the
real test is "three of the earnings models land within 25% of a median that is itself pulled toward the
price". The basket is in practice "names in the cheaper half on the rank baskets (median derived vote
1.15x / 1.10x / 1.05x of price among picks) where the median model value is 15-45% above the price".

**Side effect: a ceiling as well as a floor.** A derived vote stays in the band only while the median
is no more than `(1 + rank score) / 0.75` times the price, i.e. consensus upside of at most about
33-60%. Every one of the 40 qualifiers lies between 15% and 45%. A name that is genuinely far below
its model values cannot qualify. 221 names in the scan have consensus upside of 15% or more; 181 fail
on agreement.

**Affects:** all 30 picks (the rule itself). **Fix:** take the three derived numbers out of the vote.
If cheapness on the rank baskets is wanted, use it as a separate eligibility test or a tie-break, not
as three ballots. This changes membership heavily (see table) and needs a replay before it ships.

### F2 — Hard thresholds, a two-sided price window and no incumbency: the churn is mechanical. HIGH, CONFIRMED

**What is wrong.** Agreement is a ratio of small whole numbers (6/10 = 0.60 passes, 6/11 = 0.545 and
5/10 fail), the upside floor is a hard 15%, and an incumbent gets neither a boost (`:6953-6956`) nor a
retention band. With 40 qualifiers for 30 seats the cut-off itself is a coin-flip: rank 30 scores
0.0660 and rank 31 scores 0.0652; ranks 27 to 36 span 0.068 to 0.062 (a 1.7-point difference in
upside).

**Evidence — how far each pick is from losing its seat** (everything else held at scan values):

| Move that disqualifies | Picks |
|---|---|
| Price **falls** 5% or less | SFM (1.0%), ADBE (3.5%), WFRD (3.8%) |
| Price **rises** 5% or less | GNTX (1.0%), ORI (2.5%), SFD (3.2%), HEM.ST (3.2%), 2883.HK (4.8%) |
| Either direction, 10% or less | 23 of 30 picks |
| Median across picks | +10.2% up, -14.0% down |

The picks' own weekly price move over the seven scans: median 2.3%, 75th percentile 4.6%, 90th
percentile 8.0%. Nine picks sit at agreement of exactly 0.60 — one vote from failing. A static shock to
the whole scan gives the same picture: prices +5% loses 12 of the 40 qualifiers and adds 9; prices -5%
loses 7 and adds 18.

**The seven exits recorded in the picks file on 2026-11-07** (exact, from that scan):

| Name | Held since | Price move while held | Status in the 11-07 scan | Why it left |
|---|---|---|---|---|
| AX | 10-31 (one week) | +2.5% | upside 14.8%, agreement 8/11 | 0.2 points under the 15% floor |
| BKT.MC | 10-24 | +2.9% | upside 11.9%, agreement 6/8 | under the floor (entered at 15.1%) |
| 0168.HK | 10-24 | +5.7% | upside 13.6%, agreement 9/10 | under the floor |
| LRN | 10-31 (one week) | -4.3% | upside 15.4%, agreement 6/11 | one vote short; owner-earnings value at 1.25x the median, a hair outside the band |
| 6198.HK | 10-31 (one week) | -2.8% | upside 26.5%, agreement 5/10 | one vote short |
| JD.L | 10-10 | +12.8% | upside 35.8%, agreement 5/10 | one vote short |
| 6936.HK | 09-22 | +9.5% | **still qualifies** (17.7%, 6/10) | out-ranked, rank 34 of 40, no incumbency credit |

An eighth holding, ROCK, left because it dropped out of the scan (see F7). With a modest retention
band for incumbents (stay while agreement is 0.50 or more and upside 10% or more) all seven would have
stayed: one seat change that week instead of eight.

**It sells names for getting cheaper.** FAG.ST fell 28% while held; its consensus upside is now 87%
but the three price-anchored votes sit at 0.55-0.62x the median, agreement fell to 3/10 and it was
expelled. PLX.PA: -20%, upside now 113%, agreement 4/9, expelled. Of the 25 de-qualification exits in
the tracker, 15 happened with the implied upside still at or above 15% (so the agreement test did it,
mostly after a price fall) and 10 after a price rise pushed upside under the floor (those rises: +1.3%
to +18.8%, seven of them under 6%).

**Affects:** all picks. **Fix:** (a) give incumbents a retention band rather than the entry thresholds;
(b) restore an incumbency boost on the score; (c) once F1 is fixed the "too cheap" ceiling largely
disappears — confirm it does.

### F3 — The gates that protect the feeder methods are bypassed. HIGH, CONFIRMED

**What is wrong.** The selection loop exempts convergence from the leverage and Piotroski floors
(`:6928`) on the argument that agreement is a stronger signal. But the structural-break exclusion and
the forward-decline gate apply only to the six `EARNINGS_BASED` keys (`:6884-6913`), the peak-cycle
normalisation likewise (`:6932-6936`), and `METHOD_SECTOR_APPLICABILITY` has no `convergence` row
(`:879-896`), so `_methodology_applicable` returns True for every sector (`:898-899`). The consensus is
built from the same six model values those gates exist to protect.

**Affected picks (16 of 30 carry at least one):**

| Cause | Picks | Note |
|---|---|---|
| Structural-break flag (barred from all six earnings baskets) | 82020.HK, WFRD, GUBRA.CO, NORION.ST, 2097.HK, SFD, NOG, WBD.MI | IPO under 5 years ago or a share-count jump |
| Peak-cycle earnings, no normalisation | GUBRA.CO (scale 0.05), 8725.T (0.50), FNTN.DE (0.63), NOG (0.69), SFM (0.92) | scale = through-cycle / current earnings |
| Bank or insurer; all six model methods and the acquirer's multiple are marked not applicable | NORION.ST, ANIM.MI (financial); 8725.T, PSSA3.SA, ORI (insurance) | their "agreement" rests entirely on methods the table rejects |
| REIT / utility with part of the vote not applicable | RITM (mortgage REIT), ELEC.PA | |

**Worst case, checked against live statements — GUBRA.CO.** Revenue DKK 2,637m in 2025 against 266m
in 2024; net income 1,691m against a loss of 36m in each of the two prior years (FMP income statement).
A one-off licence year. DCF, owner earnings and EPV all capitalise it and "agree"; Graham, which uses
normalised earnings, says DKK 9 against a price of 302. The debate graded it C, thesis BROKEN, with
its own value 21% **below** the price.

**Downstream.** The debate's gates threw out 9 of the 30 picks (forensic: DUNI.ST, MOH, HEM.ST;
numeric: 2020.HK, ADBE, NORION.ST, 2097.HK, ELEC.PA, 2883.HK).

**Fix:** apply structural-break, forward-decline and peak normalisation to the inputs; let a method
vote only where `METHOD_SECTOR_APPLICABILITY` allows it for that sector class.

### F4 — A method that returns a negative value abstains instead of dissenting. MEDIUM, CONFIRMED

`if v > 0: ests.append(...)` (`:6772-6775`). A negative equity value (debt larger than the capitalised
cash flow, or negative free cash flow) simply vanishes from the count.

| Pick | Methods that came out negative | What is left inside the band |
|---|---|---|
| NOG | DCF -62.65, owner earnings -72.41, EPV -28.60, IV15 -3.08 | Graham, analyst target, three price votes (5 of 7) |
| RITM | DCF -77.85, EPV -24.85, IV15 -53.32 | owner earnings, analyst target, three price votes (5 of 8) |
| WEN | EPV | DCF, Graham, target, three price votes (6 of 10) |
| WBD.MI | owner earnings | still passes if counted |

NOG's free cash flow was -679m (2023), -266m (2024), +253m (2025) and net income 39m (FMP cash-flow
statement). Four of six models say the equity is worth less than nothing and the name "converges" on
one model plus the price. Counting a negative value as a vote outside the band removes NOG, RITM and
WEN (40 qualifiers become 37). **Fix:** count them in the denominator.

### F5 — One company holds two seats. MEDIUM, CONFIRMED

2020.HK and 82020.HK are the Hong Kong dollar and renminbi counters of ANTA Sports (same ISIN
KYG040111059, FMP profile). They rank 2nd and 4th. The renminbi counter trades about 1,000 shares a
day. The debate then graded the same company A / thesis INTACT / 24.3% discount on one line and B /
IMPAIRED / 10.8% on the other. **Fix:** de-duplicate by issuer before taking the top 30 (this belongs
in the shared selection code).

### F6 — The real methods are not independent either. MEDIUM, CONFIRMED

Rank correlation of (value / price) across the scan: DCF-EPV 0.75, R&D DCF-owner earnings 0.75,
owner earnings-EPV 0.71, DCF-owner earnings 0.67, acquirer's rank-EPV 0.75. They share inputs: the
same 10% discount rate and 2.5% terminal growth (`:2935-2981`), growth derived from the same
return on equity, net income feeding R&D DCF, owner earnings, Graham and Buffett, free cash flow
feeding DCF and IV15. R&D DCF and owner earnings land within 25% of each other for 56% of all names.
The analyst target, the one genuinely outside view, correlates negatively with every model (-0.08 to
-0.22) and exists for 1,574 of 3,430 names (none of the 18 non-US picks). So the eleven numbers reduce
to roughly three families: an earnings/cash-flow DCF cluster, the price, and a handful of outliers
(Graham, IV15, Buffett) that almost never join.

### F7 — The tracked return is overstated by about 0.6 points in the last period. MEDIUM, CONFIRMED (shared machinery)

ROCK was held on 2026-10-24, then disappeared from the 11-07 scan. The tracker carries an absent name
at its period-start price, a 0% contribution (`:6304-6309`), and books an "unpriced" exit at that
stale price (`:6338-6343`). ROCK's vendor close went from 38.83 (10-23) to 32.47 (11-06); the exit is
booked at 39.66 (-6.9% from entry) when the true figure is about -24%.

| Period | Equal-weight return from vendor closes | Tracker NAV change |
|---|---|---|
| 09-07 to 09-22 (reconstructed) | -4.31% | -3.79% |
| 09-22 to 10-10 | -2.64% | -2.71% |
| 10-10 to 10-24 | +3.35% | +3.38% |
| 10-24 to 11-07 | **+0.87%** | **+1.46%** |

The 0.59-point gap in the last period equals ROCK's missed -18% divided by 30 seats. Reported YTD
+5.25% should read about +4.6%. ROCK is still listed (USD 30.90, market value USD 0.92bn, FMP quote);
the smallest market value in the scan is USD 1.005bn, so it most likely fell under the universe's size
floor (SUSPECTED — I did not trace the universe build). The picks file did not record this exit at all
(`:7000-7002` skips a name absent from the scan), which is why it shows 7 exits against 8 entries on
11-07. The first-period gap (0.5 points) coincides with the other unpriced exit, SMPL; not verified.

### F8 — Smaller items. LOW, CONFIRMED

- **Units.** `consensus_mos` is upside, the other value baskets report discount (section 2). The
  picks file prints both under `mos`.
- **The picks-file exit list is capped at 15** (`:7026-7027`). The "15 exits in the last two scans" is
  the cap, not a count; the true figure for those two scans is at least 16.
- **Classification mismatch.** HEM.ST (Hemnet, a property-listings website) is `operating` in the scan
  row and `reit` in the picks file (sector-level fallback, `:871-872`). No effect here because the
  basket ignores sector class.

---

## 4. Rotation since 2026-09-22

**Scale.** The tracker (fortnightly) logged 38 exits over four rebalances: 11, 9, 7, 11 out of 30
seats. The picks file (weekly) changed 8 seats on 11-07 and at least 8 on 10-31. 55 different names
held a seat across five rebalance dates; 10 were held throughout. Median holding period of the exits
was 28 days; 29 of 38 lasted 35 days or less (entry dates before 09-22 are reconstructed). The weekly
file churns faster than the tracker shows: AX, 6198.HK and LRN each lasted exactly one week.

**Round trips.** 13 of the 55 names left and came back: ANIM.MI, BBWI, DJUR.CO, EEFT, HEM.ST, KARE.AT,
KRU.WA, MOH, NOG, ORI, PLX.PA, WEN, WFRD. MOH is the clearest case: in 08-26, out 09-22, in 10-19, out
10-31, in 11-07, with its metric at 0.179, 0.180, 0.177, 0.178, 0.177 throughout. Nothing moved; it
was simply out-ranked and re-ranked.

**Why names left (38 tracker exits).**

| Reason | Count | Evidence |
|---|---|---|
| Still qualified, out-ranked (no incumbency credit) | 11 | exit metric positive: ANIM.MI, 2328.HK, DJUR.CO, KARE.AT, MOH, KRU.WA, ORI, 1698.HK, BBWI, HEM.ST, 6936.HK |
| Upside fell under 15% after a price rise | 10 | implied upside at exit below 0.15; seven of the rises under 6% |
| Agreement failed with upside still 15% or more | 15 | mostly after a price fall (WEN -19%, OTF -18%, WFRD -16%, LHA.DE -11%, FAG.ST -28%, PLX.PA -20%) |
| Dropped out of the scan | 2 | ROCK, SMPL (`exit_metric 0.0`, unpriced) |

I found no exit I can attribute to a change in a company's reported numbers, though I cannot rule it
out for exits before 11-07 (no earlier scan is kept — section 6). 19 of 38 exited names had moved less
than 5% in either direction while held; 15 of 38 had entered within three points of the 15% floor.

**Price alone is enough to reproduce the turnover.** Holding every fundamental at its 11-07 value and
replaying only the closing prices of the 654 names that have a price history, the simulated top 30
changes by 2 to 7 names every week and the qualifier set by 2 to 12. This is a lower bound on a
subset, not a replay of the production scan.

**After they left.** Return from exit to 2026-11-12 against ACWI over the same days:

| Group | n | Mean excess | Median | Share ahead of ACWI |
|---|---|---|---|---|
| All exits | 38 | +3.8 pts | +2.1 pts | 53% |
| Left 09-22 | 11 | +7.7 | +7.3 | 82% |
| Left 10-10 | 9 | +8.4 | +8.7 | 78% |
| Left 10-24 | 7 | +2.0 | +2.6 | 57% |
| Left 11-07 (three trading days) | 11 | -2.7 | -2.8 | 0% |
| Still qualified, out-ranked | 11 | +3.8 | +5.3 | 73% |
| Agreement failed, upside still 15% or more | 15 | +5.0 | +1.7 | 53% |
| Upside under the floor | 10 | +0.2 | -0.4 | 30% |

The current picks are +2.1 points ahead of ACWI since entry (60% ahead). The names the basket threw
out in September and early October have done better than the ones it kept. The window is three days to
seven weeks and the sample is small; read it as "the exits were not informed", not as a measured edge.

**Is the incumbency boost doing its job?** It does not exist for this basket (`:6953-6956`).

---

## 5. What it contributes to the debate

- **A distinct set of names.** 25 of the 30 picks are in no other basket (overlaps: IV15 3, Graham 2,
  DCF 1, R&D DCF 1, none with the four rank baskets). It is not a near-copy of another basket by
  membership, even though its vote leans on the rank baskets' scores.
- **Grades.** A 7, B 19, C 4 — the most A grades of any basket. 9 of 30 were removed by the debate's
  gates, including two of the seven A's (2020.HK, ADBE).
- **Discount gap.** Median screen discount (converted to discount form) 18%; median debate discount
  16.6%. On several picks the debate sees almost no discount: NORION.ST -4.0% (bank), 8725.T +0.4%
  and ORI +2.2% (insurers), EVO.ST +2.6%, EEFT +5.8%.
- **Seats: none.** Likely reason (SUSPECTED — I did not read the Director's reasoning): the rule can
  only admit names with a moderate discount (F1 ceiling), while the value book ranks on the debate's
  discount with the bar at the median of held seats, currently 30.0% (held seats: 14.1, 15.3, 29.2,
  30.0, 39.4, 48.4, 48.7). The seven A-graded picks carry debate discounts of 16.6, 23.2, 23.2, 24.3,
  28.7, 29.5 and 35.9; only KARE.AT clears the bar, and it re-entered the basket on 11-07.
- **Two seated names passed through and were dropped.** LRN (both books) was a convergence pick for
  one week (10-31 to 11-07) and 1698.HK (value book) for under three weeks (09-22 to 10-10). Both were
  already seated before (LRN in the value book since 2026-08-10; 1698.HK in the regime book from
  2026-07-07 and the value book since 2026-08-31), so the basket cannot be credited with them, but it is why both now show as "from no basket".
- **Unstable input.** A basket that swaps a quarter of its names each week sends the debate a stream
  of names that are gone before a full debate is three weeks old.

---

## 6. What I could not check

- **Earlier scans.** Only the 11-07 scan is on disk. For exits before that date the reason is inferred
  from the entry metric, the price move and the name's current status, not observed. I cannot say which
  vote crossed the band on a given earlier date, or exclude a fundamentals update as the cause.
- **History before 2026-09-22** (wiped). Whether convergence originally surfaced LRN or 1698.HK is
  unknown.
- **Why ROCK and SMPL were absent from a scan.** The size floor is my inference for ROCK.
- **The Director's reasons for not seating the A-graded picks.**
- **A replay of any proposed fix.** The counts in F1, F2 and F4 are one-scan, static tests. The fixes
  change membership materially and should be replayed (`replay_baseline.py`) before adoption.
- **Five picks show an identical debate discount of 16.6%** (2097.HK, SFD, ANIM.MI, WEN, WKL.AS). It
  may be a carried or default value in the pack or the debate output; I did not trace it.
- **Currency.** No residue found in the picks: every in-band value sits at 0.9-1.7x the price, FX
  factors are coherent (HKD/CNY 1.175, SEK/EUR 11.03 for EVO.ST). I did not re-derive any model value
  from raw statements.

---

## Fixes, most important first

1. **Remove the three price-derived votes from the consensus** (F1). Evidence: 117 of 120 in band; 19
   of 30 picks qualify only because of them.
2. **Add a retention band and an incumbency boost** (F2). Evidence: 7 of 7 recorded exits on 11-07
   would have stayed; 11 of 38 tracker exits were still-qualifying names out-ranked by a hair; exited
   names beat ACWI by 3.8 points afterwards.
3. **Apply the feeder methods' gates to the inputs** — structural break, forward decline, peak
   normalisation, sector applicability per vote (F3). Evidence: 16 of 30 picks flagged; GUBRA.CO.
4. **Count a negative model value as a dissenting vote** (F4). Evidence: NOG, RITM, WEN.
5. **De-duplicate issuers** (F5). Evidence: ANTA twice.
6. **Tracker: mark a name absent from the scan at a real last price**, not at 0% (F7). Evidence: ROCK,
   0.6 points of NAV.
7. **Report the metric in the same form as the other baskets, and lift the 15-row cap on the exit
   list** (F8).

Items 1 to 4 change which names qualify. They are a methodology change, not a repair, and need the
owner's decision and a replay.
