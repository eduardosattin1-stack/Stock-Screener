# Machinery audit — selection, rotation and tracking shared by all twelve baskets

Reviewer assignment: `machinery`. Scan dated 2026-11-07, picks and tracking snapshots of 2026-11-12.
All line numbers are `backend/screener_v6.py` unless another file is named.

## 1. Verdict

**UNSOUND as it stands on rotation and on the record (tests 3 and 4 of the brief); sound on the
selection logic and on the arithmetic (tests 1 and 2). The faults are few, contained and fixable.**

What most justifies it:

1. **About half of all exits are not decisions, they are names dropping out of the weekly scan.**
   71 of the 149 exits from the picks file since 2026-09-22 (48%; 70 of 110, or 64%, leaving out the
   convergence basket) happened because the name was simply absent from that week's scan. Only 32
   (21%) were a name being outranked.
2. **A name that drops out of the scan is booked at a 0% return for its last period, and the names
   that drop out are mostly the ones that just fell.** The 35 such exits I could price had a mean
   real return of −6.7% in the period that was booked as 0%. The tracked year-to-date figure is
   overstated in 8 of 12 baskets, by 0.8 to 2.7 percentage points in two months.
3. **The "stay-put" bonus for names already held is far too strong on the four rank baskets and
   absent on convergence.** On the rank baskets it is three to four times the whole score range of
   the 30 seats, so a held name cannot be outranked; on convergence the bonus is overwritten and
   never applies.

What is right, and I reproduced it exactly:

- The picks file is exactly what the code produces from the scan: my re-implementation matches all
  twelve baskets, names **and order**, for 2026-11-07, and — run week by week from 2026-09-22 —
  matches the tracker's holdings on all four rebalance dates and every entry date in the picks file.
- The return arithmetic is exactly what the code says: all 84 weekly value points (12 baskets × 7
  scans from 09-26 to 11-07) reproduce to four decimals from the holdings and the scan prices.
  Nothing is double-counted or dropped at a rebalance, apart from the two rules described below.

## 2. What the shared code computes

**Selection, every weekly scan** (6638–6980). For each basket, take every stock whose metric exists,
drop the ones the method does not apply to (banks, insurers and so on, by basket), drop — for the six
earnings-based methods only — names with a broken or short history or a forecast earnings fall of 25%
or more, then require net debt below three times operating profit before depreciation and a
Piotroski score (a nine-point accounting health score) of at least 3. Convergence and fundamental
momentum skip those last two tests. Survivors are sorted by the metric, names already in last week's
picks get a bonus added to their score, anything at or below zero is dropped, and the list is walked
from the top taking names until 30 are seated, skipping a name when its sector already holds 30% of
the target size (9 of 30).

**Entry memory** (6661–6698, 7041–7053). A name that was in last week's picks file keeps its entry
date, entry price and entry metric; a new name gets today's.

**Tracking, a separate book** (6198–6466). Every 14 days or more the tracker closes the period: the
equal-weight average of each held name's price change since the last rebalance is chained onto the
running return, then the holdings are replaced by that day's picks at that day's prices. Between
rebalances the book is frozen and only marked to market. Prices are the scan's prices in each
stock's own currency; there are no dividends and no currency conversion.

**What the debate reads.** The weekly picks file, not the tracker.

## 3. Findings, most serious first

### F1 — HIGH, CONFIRMED. The scan's list of companies is unstable, and that drives the rotation

**What is wrong.** A name can only stay in a basket if it is in that week's scan. The scan's company
list changes for reasons that have nothing to do with the baskets' metrics.

**Evidence.** I downloaded the eight weekly scans (read-only) and compared them.

| Scan | Names | Left since prior scan | Joined |
|---|---|---|---|
| 09-22 | 3,564 | – | – |
| 09-26 | 3,550 | 34 | 20 |
| 10-03 | 3,539 | 36 | 25 |
| 10-10 | 3,523 | 53 | 37 |
| 10-19 | 3,526 | 58 | 61 |
| 10-24 | 3,506 | 47 | 27 |
| 10-31 | 3,506 | 34 | 34 |
| 11-07 | 3,430 | **157** | 81 |

3,738 different names appeared at least once; only 3,230 were in all eight; 102 left and came back.

Three causes, each visible in the data:

- **Per-exchange row limits that bind** (`REGIONS`, 1245–1318). Hong Kong returns exactly 200 names
  in all eight scans, Tokyo 100, Zurich 100, Seoul 50, São Paulo 50, and Stockholm 300 in seven of
  eight — each equal to its configured limit — and in those venues the number leaving equals the
  number joining every single week (Hong Kong: 2/2, 2/2, 3/3, 6/6, 5/5, 2/2, 4/4). The limit, not the
  market-cap floor, is the real cut: the smallest Hong Kong name in the scan is HKD 57–64 billion.
  The comment at 1285 ("limits are set well above the observed row counts so they never bind") is
  false for Zurich and Stockholm, and the Asian and Brazilian limits were never checked.
- **The market-cap floor has no buffer.** The floor is 1 billion in the *local* currency (the
  smallest Oslo name is NOK 1.03 billion, Warsaw PLN 1.01 billion), and at least 85 names sit within
  15% of it. Of the 41 name-weeks behind the 71 basket exits, 18 were names at 1.00–1.07 billion the
  week before they vanished; 7 of those came back later.
- **The data vendor's list changed on 11-07.** 157 names disappeared in one week, most of them
  second share classes, preference shares and exchange-listed notes (BP-A.L, BP-B.L, PETR4.SA,
  LISP.SW, MGR/MGRB/MGRD/MGRE, PRH, PRS, and 34 Stockholm lines, mostly A/B and preference
  classes). No code changed — the last
  commit to `screener_v6.py` is 2026-08-20.

A fourth possible cause is in the code but I could not observe it: `get_quotes_batch` (1571–1578)
silently loses all ten symbols of a batch when one quote call returns nothing.

**Who it affects.** 41 name-weeks, 71 basket exits. Per basket, exits caused by absence out of all
weekly exits since 09-22: ev_gp 3 of 3, ev_gross_profit 8 of 9, earnings_yield_gap 9 of 12,
dcf_fcff 11 of 16, owner_earnings 8 of 12, graham_revised 4 of 6, rd_capitalized_dcf 10 of 16,
iv15_deep_value 6 of 10, epv 8 of 17, acquirers_multiple 3 of 9, convergence 1 of 39.

**A seat in the real-money book is exposed.** 2618.HK (JD Logistics, a value-book seat) is the
smallest or second-smallest Hong Kong name each week it appears and was **absent from three of the
eight scans** (09-26, 10-03, 10-19), losing its place in four baskets each time. DUE.DE, a seat in
both books, has a market cap of about €1.1 billion — some 10% above the floor.

**Fix.** (a) Add every name currently held by any basket, book or tracker to the scan's symbol list
before the scan runs, whatever the vendor's screener returns. (b) Raise the limits until none binds
and fail loudly when a venue returns exactly its limit. (c) Give the floor a buffer: enter at 1.0
billion, leave below roughly 0.8. (d) Decide deliberately whether second share classes and notes
belong in the universe instead of inheriting the vendor's default.

### F2 — HIGH, CONFIRMED. A vanished name is booked at 0% for its last period; the record is biased upward

**What is wrong.** At a rebalance, a held name missing from the scan is marked at its last recorded
price ("carry it at its last known price (a 0% contribution)", 6303–6311) and its exit is logged at
that same stale price (6338–6343). The comment says this protects against survivorship. It does the
opposite when the reason for vanishing is a price fall through the floor.

**Evidence.** The tracker logged 194 exits since the reconstruction; 61 carry `unpriced_exit`
(8, 7, 12 and 34 on the four rebalance dates — 34 of 56 on 11-07). They are 36 distinct name-dates;
35 have a usable price series. Their real return in the period booked as 0%: **mean −6.7%, median
−4.8%, 24 of 35 negative, 13 worse than −10%**. Examples: TEAM −32.5%, TRIP −25.6%, DFH −23.5%,
PETR4.SA −22.7%, TRST.L −21.4%, ROCK −16.4%, SQZ.L −15.8%.

Effect on the tracked year-to-date figure (recorded, against the same figure with the vanished
names' real period returns put in; 50GP.L left at 0% because its price series is unusable):

| Basket | Recorded | Corrected | Overstated by |
|---|---|---|---|
| ev_gross_profit | +9.84% | +7.14% | 2.70 pts |
| owner_earnings | +12.06% | +10.11% | 1.95 |
| rd_capitalized_dcf | +6.84% | +5.31% | 1.53 |
| epv | +9.12% | +7.73% | 1.39 |
| ev_gp | +1.25% | +0.11% | 1.14 |
| convergence | +5.25% | +4.23% | 1.02 |
| dcf_fcff | +14.25% | +13.31% | 0.94 |
| acquirers_multiple | +10.48% | +9.70% | 0.78 |
| earnings_yield_gap | +1.62% | +1.84% | −0.22 |
| iv15_deep_value | +19.62% | +19.83% | −0.21 |
| graham_revised | +4.70% | +5.34% | −0.64 |
| fundamental_momentum | −30.30% | −30.30% | 0 |

The exit log is stale in the same way: TEAM is logged as a +16.3% exit at 227.61 when it last
closed at 153.68 (−21.5% from entry); PETR4.SA is logged +32.4% at 58.68 against a last close of
45.36.

A related inconsistency: between rebalances a missing name is *dropped* from the average (6459–6464)
rather than carried at 0%. That happened on 18 name-weeks (38 basket instances). It does not bias the
closed return, but it means the weekly value point and the period close follow different rules.

**Fix.** When a held name is missing from the scan, fetch its quote directly and book the real
return; use the stale price only when no quote exists at all, and say so. Restate the record since
09-22 with the table above. F1's fix (a) removes most cases at the source.

### F3 — HIGH for the four rank baskets and convergence, CONFIRMED. The bonus for held names is not the same strength everywhere

**What is wrong.** The bonus is "10% of each method's maximum amplitude" (6869–6873): 0.05 for the
value methods, 0.0125 to 0.02 for the rank methods. That is the same fraction of the *score scale*,
but not of anything that matters. The rank methods score every stock on an even ladder, so 10% of the
amplitude is always 5% of the whole ranked universe — about 165 names — while the basket holds 30.

**Evidence, from the 11-07 scan.**

| Basket | Bonus | Score range of the 30 seats (no bonus) | Qualifying names within one bonus below the cut-off |
|---|---|---|---|
| ev_gross_profit | 0.015 | 0.1461 – 0.1498 | 90 |
| earnings_yield_gap | 0.0125 | 0.1210 – 0.1250 | 90 |
| acquirers_multiple | 0.020 | 0.1932 – 0.2000 | 90 |
| ev_gp | 0.020 | 0.1891 – 0.1999 | 88 |
| dcf_fcff | 0.05 | 0.593 – 0.80 | 11 |
| epv | 0.05 | 0.330 – 0.87 | 10 |
| owner_earnings | 0.05 | 0.584 – 0.93 | 17 |
| rd_capitalized_dcf | 0.05 | 0.598 – 0.89 | 21 |
| graham_revised | 0.05 | 0.780 – 0.95 | 23 |

On a rank basket every held name scores above the highest score any newcomer can reach. A held name
leaves only if it fails a gate, its metric stops being computable, or it vanishes from the scan.
Across the four rank baskets in seven weeks there were 33 exits: 23 vanished, 5 lost a computable
metric, 3 failed the Piotroski test, and **2 were outranked**. So these baskets are frozen on
whatever was top-30 on 09-22, the day the bonus happened not to apply (F4): 27 of 30 ev_gp picks,
27 of 30 acquirers picks and 25 of 30 ev_gross_profit picks date from 09-22 or 09-26.

**Convergence gets no bonus.** The bonus is added at 6937–6938 and then overwritten at 6953–6956
("MoS-unit hysteresis doesn't apply"). Result: 39 exits in seven weeks for 30 seats, identical to my
run with the bonus switched off; 28 of the 39 were names dropping just under the qualifying
thresholds, and 15 names left and re-entered within the eight weeks.

For the record, the bonus does its job on the value methods: 149 weekly exits with it against 214
without (dcf_fcff 16 against 28, epv 17 against 25).

**Fix.** Express the bonus in rank terms and make it the same for all baskets: a held name keeps its
seat while it ranks inside, say, the top 45 qualifiers (1.5 times the basket). Give convergence a
buffer on its own thresholds (enter at 60% agreement and 15% discount, leave below 50% and 10%).

### F4 — MEDIUM, CONFIRMED. When last week's picks cannot be read, everything resets silently

**What is wrong.** If the previous picks file cannot be loaded, the code logs one warning and carries
on (6696–6698): no bonus for held names, every entry date and price reset to today, no exits
recorded. Nothing stops the publish.

**Evidence.** It happened on 2026-09-22, after the storage wipe. No pick in the file has an entry
date before 09-22, in any basket. My selection run with *no* held names reproduces the 09-22 picks of
all twelve baskets exactly. Run instead with the reconstructed 09-07 holdings as the held names, the
same scan gives **21 exits, not the 77 that were booked** (ev_gross_profit 1 not 15, ev_gp 1 not 14,
acquirers_multiple 1 not 11, earnings_yield_gap 0 not 7).

A lasting side effect: the picks file and the tracker now disagree on entry date or entry price for
233 of the 342 current picks (for example 2333.HK: picks file 09-22 at 7.48, tracker 08-21 at 8.445).

**Fix.** Treat "no previous picks" as a failure unless a flag says it is a first run; keep a dated
copy of each week's picks file so a lost one can be restored.

### F5 — MEDIUM. Stale local copies are read before the live ones (CONFIRMED in code and on disk; SUSPECTED as a live risk)

Both loaders read `frontend/public/` first and the live storage only as a fallback (6154–6176,
6669–6685). The repository holds a picks file last updated 2026-07-16 and a tracking file last
updated 2026-09-21 containing only the 09-07 rebalance. The scheduled job's container starts
without that folder (the image copies only `*.py`, see `backend/Dockerfile`), so production is safe
as long as every scan starts in a fresh container. A scan run from this checkout without `--no-gcs` would read both
stale files, rebuild on them, and upload the result over the live state — erasing three rebalances.

**Fix.** Read live storage first; use the local copy only with `--no-gcs`. Remove the two stale files
from the repository.

### F6 — MEDIUM, CONFIRMED. The picks file keeps no trace of a vanished name, and only 15 exits

The picks file skips an exit when the name is missing from the scan ("exit not recorded",
6999–7002), so none of the 71 absence exits appear in the file the debate and the site read. The
list is also cut to the 15 newest (7027): convergence's list covers two weeks only. No exit carries a
reason, so a reader cannot tell "outranked" from "failed a gate" from "data gone".

**Fix.** Record every exit with a reason code (absent from scan, gate failed and which, metric not
computable, outranked) and keep at least a quarter of history.

### F7 — MEDIUM, CONFIRMED. Two cadences: the tracked record is not the record of what the debate saw

- 47 current picks entered the picks file on an off-cycle week and were bought by the tracker one or
  two scans later at a different price. Average gap is small (+0.5%) but single cases are not: UPBD
  entered the picks at 20.70 on 10-31 and the tracker at 24.24 on 11-07 (+17.1%).
- 14 stays in a basket began and ended between two rebalances, so the debate saw them and the
  tracker never held them (9 of the 14 in convergence).
- 36 basket memberships were broken and resumed within eight weeks (2618.HK three separate stays in
  three baskets, PTEC.L out for one week in three baskets). Each return resets the entry date and price in
  the picks file and forfeits the held-name bonus, while the tracker shows one unbroken holding.

**Fix.** Either rebalance the tracker on every scan, or have the picks file carry the tracker's entry
date and price next to its own. F1's fix removes most of the false re-entries.

### F8 — LOW to MEDIUM, CONFIRMED. The sector cap discards qualifying names in thin baskets

The cap is 30% of the size *achieved* (6646–6659, 6973–6976), so a basket that cannot fill 30 seats
gets a smaller cap, which shrinks it further. IV15 has 17 qualifying names and seats 14: 0175.HK (a
regime-book seat, discount 0.47), 000270.KS and JD.L are cut for being the fifth to seventh Consumer
Cyclical name, while four names with smaller discounts (down to 0.16) stay. At a target of 15 the
cap is `round(4.5)`, which Python rounds to 4, not 5 — that alone cost the fifteenth seat.

For full baskets the cap works as intended: no capped basket holds more than 9 names in a sector,
and it bound in only four (dcf_fcff skipped 3 names, ev_gp 2, iv15 2, epv 1). Fundamental momentum
is exempt by design (6965–6970) and holds 19 Technology names out of 28.

**Fix.** Fix the cap at 9 (30% of the nominal 30) whatever the achieved size, or skip it when fewer
than 30 names qualify.

### F9 — LOW, CONFIRMED (by reading; not yet exercised). Year rollover loses a week and leaves loose ends

`_rollover_tracking_year` (6469–6508) stores each basket's last saved figure — the mark at the last
December scan — and clears the rebalance list. The first January run then sees no prior rebalance,
so the test at 6299 is false and no period is closed: the return between the last December scan and
the first January scan belongs to neither year. `tracking_start` is blanked and never set again
(6500, 6258), and the exits list keeps the name `all_exits_2026`.

### F10 — LOW, CONFIRMED. What the return figure is and is not

It is a correct equal-weight, rebalanced, chained return of price changes. It is in each stock's own
currency with no conversion, so it is not a euro or dollar return; it excludes dividends, which
matters for the high-yield names these baskets favour; and there is no check for a stock split or a
pence-for-pounds flip. None occurred in scan prices in this window — the largest single-name moves
inside a tracked period are GMAB.CO +48% and BONEX.ST +40% — but 50GP.L shows the hazard: the vendor's daily series
flips between 84.75 and 0.8475, and the scan carried one unchanged price (74.75) for four weeks.

### F11 — LOW, CONFIRMED. Smaller items

- If the tracking file cannot be loaded, tracking is skipped with an info-level log line
  (7130–7131) and nothing recreates it.
- The leverage test passes any company with no operating profit and no net debt (6642–6643). 329
  names pass that way; the 143 with all-zero fundamentals are caught by the Piotroski test (all score
  0), so no data-gap name is in any basket. The protection is accidental, not designed.
- The scan's own `sector_class` field is built from the industry text alone (2808) and calls 104
  utilities, 100 property companies and 54 financials "operating". The selection loop uses the
  correct version (6894), so the baskets are unaffected, but the weekly intake reads the wrong field
  (`weekly_opus_refresh.py:6233`).
- Timestamps are written as `...+00:00Z` (6181, 7134), which is not a valid format.

### F12 — MEDIUM, CONFIRMED. The intake lanes convert market cap with the wrong factor

Three intake lanes compute a dollar market cap as `market_cap × fx_to_price`
(`weekly_opus_refresh.py:6011`, `6071`, `6117`). `market_cap` is in local currency and `fx_to_price`
is the factor from the *reporting* currency to the *quote* currency (100 for London names quoted in
pence, 1.175 for Hong Kong names reporting in yuan, 1 for US names). The product is dollars only for
US names. So the "$300 million to $15 billion" window of the IPO-orphan lane rejects almost every
non-US candidate: 9980.HK, seven months after listing, was computed at "98.6 billion" against a true
figure of roughly USD 12 billion, and so could not use that lane.

## 4. Rotation since 2026-09-22

Weekly exits from the picks file, all twelve baskets, by cause (my week-by-week reconstruction, which
matches the tracker on every rebalance date):

| Scan | Absent from scan | Metric no longer computable | Failed a gate | Outranked or sector cap | Total |
|---|---|---|---|---|---|
| 09-26 | 8 | 4 | 3 | 3 | 18 |
| 10-03 | 6 | 4 | 0 | 1 | 11 |
| 10-10 | 0 | 5 | 1 | 7 | 13 |
| 10-19 | 11 | 5 | 1 | 4 | 21 |
| 10-24 | 5 | 4 | 3 | 4 | 16 |
| 10-31 | 6 | 6 | 3 | 11 | 26 |
| 11-07 | 35 | 6 | 1 | 2 | 44 |
| **Total** | **71** | **34** | **12** | **32** | **149** |

"Metric no longer computable" is 28 convergence names falling below that basket's own thresholds, 5
acquirers names and 1 epv name. "Failed a gate" is 4 forecast-earnings, 4 IV15 agreement, 3
Piotroski, 1 leverage.

The 09-22 rebalance itself (77 tracker exits) was mostly an artefact of the reset (F4).

What happened to names after they left is covered per basket by the other reviewers; for the
machinery the relevant fact is F2 — the ones that left by vanishing had already fallen 6.7% on
average in their last period.

## 5. What it contributes to the debate

**The picks file is the debate's main feed**: 220 of the roughly 250 names in this week's debate
universe come from the baskets. Its weekly turnover is what section 4 shows, so about half of the
names the debate stops seeing each week are lost to the scan, not to the method.

**How four seated names come from no basket.** There are two routes that bypass the screens, both in
`prep` in `weekly_opus_refresh.py`:

1. **Intake lanes** that read the scan directly and skip the rankings and most of the gates:
   value-drawdown (5917–5954, up to 20 names a week: 25% or more below the 52-week high, in the
   bottom 15% of the range, positive cash-flow margin, decent returns, five years of history),
   neglect-orphan (5956–6042, 3 new a week), fresh-crash (6044–6084, 2) and compounder-discount
   (6086–6130, 3). None applies the leverage test, the structural-break test or the sector rules.
2. **Held-seat unions** (5871–5873 regime seats; 5879–5888 value seats and runners-up; 5895–5903
   tracked positions). Once a name holds a seat it is re-debated every week whether or not any
   screen or lane still selects it.

This week 32 of the 251 names in `_radar_universe.json` have no basket behind them: 20
value-drawdown, 4 held-seat only, 3 compounder-discount, 3 neglect-orphan, 2 fresh-crash.

| Seat | Route | Evidence | Status |
|---|---|---|---|
| 1698.HK | Value-drawdown lane. Barred from the six earnings baskets because the scan flags a structural break (`ipo_2022-09`, its Hong Kong listing date). | Named in the value-drawdown line of `_run_logs/prep_forced_20260717.log`; still meets the lane's rules on the 09-26, 10-31 and 11-07 scans (57–65% below the high). Was in convergence for one week (09-22). First seated 07-07 (regime), 08-31 (value). | CONFIRMED |
| 9980.HK | Value-drawdown lane. Also flagged as a structural break (`ipo_2026-02`). | In no basket in any of the eight scans; meets the value-drawdown rules on the 09-26 scan (59% below the high); first seated 09-29 (value), 10-05 (regime). The prep log for that week is not on disk. | Route inferred, eligibility CONFIRMED |
| DECK | Entered through the convergence basket in July; its record now carries `lane: quality_discount` (the compounder-discount lane). | In convergence in the 2026-07-16 picks file; first seated 07-13 and 07-17; meets the compounder-discount rules on all three scans tested. | CONFIRMED |
| LRN | Unknown. Held today only through the held-seat union. | Meets no intake lane on the 09-26, 10-31 or 11-07 scans and is in no basket except convergence for one week (10-31). First seated 08-10 and 08-18, before the wipe. | Original route NOT recoverable |

All four are tagged only `value_apex` in this week's universe file because the union runs first and
the lanes skip names already present — so the file does not say how a name first arrived. Stamping
the lane of first entry permanently on the record would close that gap.

## 6. What I could not check

- **Anything before 2026-09-07.** The earlier rebalance log, exits and daily values are gone. The
  year-to-date figures rest on a starting value folded in at the reconstruction (for example +9.49%
  for dcf_fcff) that cannot be audited.
- **The reconstruction itself, partly.** From 09-07 to 09-22 my figures match the record to 0.01
  point for four baskets (ev_gross_profit, acquirers_multiple, ev_gp, convergence) using 09-04
  closes and the 09-22 scan prices; seven more match once 50GP.L's fall from 84.75 to 74.75 is
  included, which I infer from the size of the gap rather than observe. fundamental_momentum is 0.44
  point lower in the record than in my reproduction and I did not find why.
- **Why each individual name left the scan.** I classified by pattern (venue at its limit, market
  cap at the floor, second share class). There are no scan logs here; four cases (TEAM, ROCK, PRH,
  PRS) fit none cleanly. I did not use the live market-data tools to check them.
- **Whether a scan is ever run outside the scheduled job** (F5), and whether the lost-batch path in
  `get_quotes_batch` has ever fired.
- **The year rollover** has not happened yet under this code; F9 is from reading it.
- **LRN's original route.**

## How the checks were done

- Selection: re-implemented lines 6638–6980 and ran it on the eight weekly scans, starting with no
  held names on 09-22 and feeding each week's result into the next.
- Accounting: recomputed every weekly value point from the tracker's holdings and the scan prices
  using the code's two rules; separately recomputed period returns from the daily closes in
  `_px_cache` to price the names the scan had lost.
- Nothing in the repository or in storage was modified. Scratch files are outside the repository.
