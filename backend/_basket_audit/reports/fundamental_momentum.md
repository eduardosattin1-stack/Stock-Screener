# Basket audit — `fundamental_momentum`

Reviewer scope: `backend/screener_v6.py:6804-6858` (the score), `:6859-7103` (selection, exits),
`:6198-6466` (paper tracker). Data: the 2026-11-07 scan, the 2026-11-12 picks and tracking
snapshots, the daily close cache, and eight live vendor (FMP) spot checks.

## 1. Verdict

**UNSOUND as a screen** — it is not selecting or rotating anything; it is a static list of every
name that passes four yearly thresholds. The inputs are clean and the tracked loss is arithmetically
right, but the basket fails "rotates for real reasons" and its record is published in two
contradictory versions.

The three things that most justify this:

1. **There is no selection and no exit rule.** 28 names qualify, the basket has 30 seats and no
   sector cap, so every qualifier is seated and the score never decides membership. A name can only
   leave when its next *annual* report fails a threshold. Price, the 200-day trend, and analyst
   downgrades cannot remove anything.
2. **The score is saturated and partly backwards.** 24 of 28 picks sit at the maximum 1.3×
   "analyst support" multiplier, which *rises* when the price falls. Within the basket, higher
   score went with worse return (rank correlation −0.35; top nine −28.8%, bottom nine −10.1%).
3. **The record is published twice with different numbers.** The home page, picks file and tracker
   show −30.3% and still accruing; the public pipeline page, `speculair_baskets.json` and the
   briefing show −14.1% "frozen for honesty". Both describe the same basket.

## 2. What the rule computes

Scope: a stock is eligible if its theme is one of four (AI & Semiconductors, Electrification &
Clean Energy, Space & Defense, Infrastructure & Industrials) or its industry name contains one of
eleven keywords (semiconductor, aerospace, computer hardware, communication equipment…)
(`screener_v6.py:6816-6827`).

Gates (`:6841-6843`): latest annual revenue growth ≥ 15%, three-year revenue growth rate ≥ 10% a
year, gross margin ≥ 30%, five-year average return on invested capital ≥ 0, and an analyst price
target greater than zero.

Score (`:6844-6851`): `0.28·growth + 0.16·three-year growth + 0.24·return on capital +
0.18·analyst-target revision + 0.14·gross margin`, each scaled 0–1 with a cap, then multiplied by
`target ÷ price` clamped to 0.7–1.3. The range is therefore 0 to 1.3. The "fair value" it
publishes is simply the analyst target (`:6852`).

I recomputed the score for all 28 picks from the scan row; every one matches the published value
to four decimals. So the code does what the code says. It is a growth-and-quality checklist on
annual accounts, not "momentum" in any price or quarterly sense: revenue growth is the last two
annual rows (`:2526-2529`), return on capital is a five-year annual average (`:2225-2237`), and the
"revision" input compares last quarter's average target with last year's average
(`:1999-2001` — the code comment itself calls the 60-day name a misnomer).

## 3. Findings, most serious first

### F1 — No selection, no exit rule (HIGH, CONFIRMED)

- 363 scan names are in scope; 28 pass the gates; the basket has 30 seats
  (`PICKS_PER_METHODOLOGY = 30`, `:116`) and is exempt from the sector cap
  (`:6965-6970`, `portfolio = candidates[:30]`). Every qualifier is seated. Cut-off score 0.3199 is
  simply the weakest qualifier.
- Seats were 20 until commit `c23010ad` (2026-07-24). With 20 seats the basket did rank: the only
  two exits ever recorded (SHLS 07-17, WLDN 07-21, in the frozen copy inside
  `frontend/public/speculair_baskets.json`) were names pushed out by a higher-scoring entrant, both
  still qualifying (exit scores 0.29 and 0.34). Raising the seat count to 30 turned a ranked top-20
  into take-everything, and both came straight back.
- The only ways out today: the next annual report fails a gate; the vendor drops the analyst
  target; the theme or industry label changes; the name disappears from the scan. Most picks have
  December year-ends, so nothing is re-tested before roughly February 2027.
- **The incumbency boost does not freeze it.** It is 0.05 (`:6872-6873`, default amplitude 0.50)
  on a score that moved by a median 0.06 and up to 0.25 per name between entry and now. If seats
  were binding the boost would be too small to cement anything. With 28 names for 30 seats it is
  simply never used.
- Meanwhile the facts the basket ignores: 23 of 28 picks trade below their 200-day average; 11 of
  28 are flagged `PEAK_CYCLE` by the scan's own cycle detector; the tracker shows 26 of 28 below
  their entry price.

Affects: all 28. Fix: see section 7.

### F2 — The analyst-support multiplier is saturated and rewards falling prices (HIGH, CONFIRMED)

- `asup = clamp(target / price, 0.7, 1.3)` (`:6850`). 24 of 28 picks have target/price ≥ 1.3
  (basket median 1.8×), so for them it is a constant 1.3. Only HEI, GE, SHLS (1.19–1.24) and UI
  (0.82) carry any information.
- Because the target barely moves and the price does, a falling price *raises* the score.
  SNDK: price −53% since entry, score 0.98 → 1.05. AMD: 0.54 → 0.72. ANET: 0.75 → 0.89.
- The target can be stale. Live check, WLDN: consensus target 117.5 but zero targets published in
  the last quarter (three in the last year). The scan shows the same for SHLS (0 in the quarter),
  ASML and UI (1 each). The `target > 0` gate does not look at how old the target is.
- The revision input is also slow: SNDK scores the maximum 1.0 because last quarter's average
  target (1,866) is 29% above last year's average (1,441), while the stock halved.
- Score against outcome, 28 picks, entry to the 2026-11-06 close: rank correlation −0.352. Top nine
  by entry score −28.8%, middle ten −23.0%, bottom nine −10.1%. One window and one sector sell-off,
  so this is suggestive, not proof — but there is no evidence the score orders anything usefully.

Affects: 24 picks at the cap (all except HEI, GE, SHLS, UI). Fix: drop the multiplier, or replace
it with something that cannot improve when the price falls.

### F3 — Two contradictory published records (MEDIUM, CONFIRMED)

| Where | Number shown | Source |
|---|---|---|
| Home page basket card, picks file header, tracker | −30.3%, still moving | `scans/methodology_tracking.json` (`frontend/app/page.tsx:2297`, `:3124-3141`) |
| Public `/welcome/pipeline` page | "−14.1% RETIRED … record frozen for honesty" | hard-coded, `frontend/app/welcome/pipeline/page.tsx:67`, `:154` |
| `speculair_baskets.json` and the briefing | −14.12%, `retired: true`, 20 names | `publish_to_frontend.py:78-93`, `api/briefing/route.ts:471-475` |

The retirement on 2026-07-21 was done on the consumption side only
(`weekly_opus_refresh.py:5848-5853`); the scan still computes, publishes and tracks the basket.
So "frozen" is true of one copy and false of the other.

Related labelling errors in the live copy:

- The tracker point dated **2026-09-07** (NAV 85.88) is really the **2026-07-21** state. The
  September rebuild took this basket from the frozen copy, whose prices are the 07-20 closes
  (NVDA 203.28, AVGO 378.16, UI 532.41, SKHY 151.16, FTAI 199.71 — all equal the 07-20 close in the
  price cache). The tracker's reconstruction note ("held from their 09-07 prices") is wrong for
  this basket.
- The picks file gives 27 names an entry date of 2026-09-22; the tracker gives the true June/July
  entries for 20 of them (NVDA 214.75 on 06-04 against 227.38 on 09-22). Mean per-name result:
  −26.4% on tracker entries, −20.6% on picks-file entries.
- "YTD" starts on 2026-06-04.

### F4 — The loss is measured correctly, but against the wrong yardstick (MEDIUM, CONFIRMED)

I rebuilt every period from the daily close cache:

| Period (price dates) | Names | Recomputed | Tracker |
|---|---|---|---|
| 07-20 → 09-21 (labelled 09-07 → 09-22) | 20 | +3.02% | +3.02% |
| 09-21 → 10-09 | 27 | −0.22% | −0.23% |
| 10-09 → 10-23 | 28 | −15.59% | −15.59% |
| 10-23 → 11-06 | 28 | −6.45% | −6.46% |

The four interim weekly marks also match to 0.01 points. The chain reproduces NAV 69.70. No
split, currency or bad-price artefact: scan prices equal the prior close for all 28, every pick is
quoted in dollars with `fx_to_price` 1.0, and the declines are spread over weeks. The −14.1%
before 07-21 cannot be rebuilt (history wiped) but is plausible: the same file read −10.1% on
07-16 and the holdings fell about 4.5% over the next three sessions.

What the number means:

| Window | Basket | Semiconductor ETF (SMH) | Nasdaq-100 (QQQ) | Global index (ACWI) |
|---|---|---|---|---|
| 06-03 → 11-06 | −30.3% | −27.3% | −11.8% | −4.0% |
| 07-20 → 11-06 | −18.8% | −17.0% | −5.7% | −1.4% |
| 09-21 → 11-06 | −21.2% | −22.2% | −11.5% | −5.9% |

19 of 28 picks are semiconductors (13) or computer/communication hardware (6). The loss is almost entirely
the sector; against a semiconductor fund the basket is within about 3 points either way. The
"quarter of picks beat the global index" figure (6 of 28 at the 11-06 close) is a statement about
the sector, not about stock selection. There is no evidence of skill and none of a measurement
error.

One residual gap: from 07-21 to 09-22 the tracker held the frozen 20, not whatever the live basket
held, so the record for those two months is "the frozen list", not "the picks".

### F5 — Non-US companies are shut out by a missing data field (MEDIUM, CONFIRMED)

The `target > 0` gate needs a vendor analyst target. In scope: 185 of 187 US names have one; 6 of
176 non-US names do. Eleven names pass every economic gate and fail only this one:

| Symbol | Company / note |
|---|---|
| 000660.KS | SK hynix ordinary share — its US receipt SKHY is in the basket |
| ASML.AS | ASML ordinary share — its US line ASML is in the basket |
| 6857.T | Advantest |
| 285A.T | Kioxia |
| 267260.KS | HD Hyundai Electric |
| 6809.HK, HMS.ST, MILDEF.ST, EXA.PA, LBW.WA, BITTI.HE | smaller names |

All 28 picks are US-listed. The same company qualifies or not depending on which listing the vendor
covers. That is a data rule, not an investment rule.

### F6 — No protection against cyclical peaks; entries arrive late (MEDIUM, CONFIRMED)

- 11 of 28 picks carry the scan's `PEAK_CYCLE` flag. The peak adjustment at `:6932-6936` applies
  only to the earnings-based value methods.
- Growth uses annual accounts, so names enter only once a full year of growth is reported. The six
  storage/memory/optical names that joined on their fiscal-year results (SNDK, STX, WDC, LRCX,
  LITE in August–September, MU in October) plus WLDN and SHLS lost 30.2% from 09-21 to 11-06,
  against 16.8% for the twenty older holdings.
- Vendor check: MU revenue 133.2bn against 37.4bn (+256%), gross margin 80.7%; SNDK 20.2bn against
  7.4bn (+175%). The scan values are right. The three-year growth rate is measured from a trough
  year (MU made a gross loss in fiscal 2023), and four picks hit the growth cap. These are real
  numbers describing a cycle peak.

### F7 — "Positive return on capital" is not enforced (LOW, CONFIRMED in code; no current pick depends on a missing value)

`FM_ROIC = 0.0` with `roic >= FM_ROIC`, and a missing value defaults to 0.0 (`:6821`, `:6836`,
`:6842`), so a name with no data passes. 30 in-scope names have exactly 0; none currently passes the
other gates. The UI text says "ROIC > 0" (`stock/[symbol]/page.tsx:2819`).

Two picks clear the gate by a hair and are not "durable compounders":

- **LITE** — five-year average 0.7% (yearly: +6.6%, −2.0%, −9.8%, +0.8%, +7.9%, confirmed with the
  vendor); latest-year net margin −230%.
- **AXON** — five-year average 0.8%.

### F8 — The score is stored and displayed as a margin of safety (LOW, CONFIRMED)

- Maximum is 1.3 (base ≤ 1.0 × multiplier ≤ 1.3). NVDA 1.24, MU 1.10, SNDK 1.05 exceed 1.0.
- It is written into `mos`, `entry_metric`, `average_mos` (0.6728) and `mos_source`
  (`:7061-7102`). The basket table multiplies by 100 and adds a percent sign for every basket
  (`frontend/app/page.tsx:1585-1589`, called at `:3420`), so NVDA's entry reads "130.0%".
- No mechanical harm found: the above-zero floor exempts it (`:6577`), nothing else in the backend
  reads `momentum_mos`, and it is not in the home page's cross-method margin-of-safety median.
- The incumbency boost of 0.05 is 3.8% of this score's range, not the "10% of amplitude" the
  comment at `:6864` promises. Moot while F1 stands.

### F9 — Scope is looser than "physical hard technology" (LOW, CONFIRMED)

The "Infrastructure & Industrials" theme is exactly the Engineering & Construction industry
(89 names). **WLDN** (Willdan, an energy-consulting and engineering-services firm) qualifies through
it, with a stale target (F2).

### F10 — Missing revision data is scored as the worst outcome (LOW, CONFIRMED)

`pt_velocity_score` is `None` when fewer than two targets were published in the quarter
(`:2024`), and the basket turns `None` into 0 (`:6847`) — worth up to 0.23 score points. Affects
ASML, UI, WLDN, SHLS. It only changes display order today.

## 4. Rotation since 2026-09-22

| Date | Event | Real or data? |
|---|---|---|
| 09-22 | Tracker goes from 20 to 27 names: SNDK, STX, WDC, LRCX, LITE, SHLS, WLDN | Mixed. SHLS and WLDN are the two names displaced in July returning because seats went 20 → 30. The other five have June fiscal year-ends and qualified on new annual results (real). The 09-22 date itself is a reconstruction artefact — when they truly entered the live file between 07-21 and 09-22 is lost. |
| 10-03 (picks) / 10-10 (tracker) | MU enters | Real: fiscal-2026 results. |
| 10-24, 11-07 | No change | — |
| Any date | Exits: none | No mechanism (F1). |

Turnover from noise: none, because there is no turnover. Names closest to a gate, which would be
the first to leave on a new annual report: ACMR (growth 15.2%), SMTC (15.5%), ASML (15.6%), HEI
(16.3%), LRCX (three-year rate 10.1%), FTAI (gross margin 31.1%), LITE and AXON (return on capital
under 1%).

## 5. What it contributes to the debate

Nothing, by design. It has been excluded from the debate universe since 2026-07-21. 27 of 28 picks
are not in the universe; WDC is (grade C, numeric gate WARN) but did not come from a basket. It
supplies no seat in either book and shares no name with any of the other eleven baskets, so it is a
distinct lens — the only one that would ever surface these names.

Its one remaining use: the frozen July list is the yardstick for the paper "recovery" sleeve
(`weekly_opus_refresh.py:1605-1612`, `:1686-1695`). That uses the frozen copy, not the live one.

## 6. Artefact check on the picks

No pick is a price, currency or unit artefact. All 28 are dollar-quoted, scan prices match the
close cache, and the vendor statements I pulled (MU, SNDK, LITE) match the scan. SKHY is a genuine
security — the SK hynix US depositary receipt listed 2026-07-10.

Picks that are there for a weak reason:

| Pick | Why it is questionable |
|---|---|
| WLDN | Services firm inside a "hard-tech" scope; analyst target has had no update in the last quarter |
| LITE | Return on capital 0.7% average with two negative years; latest-year net margin −230% |
| AXON | Return on capital 0.8% average |
| SHLS | No analyst target published in the last quarter; weakest score |

## 7. Should it keep being published in its current form? No.

Fixes, most important first:

1. **Choose one status and make every surface agree** (F3). Either stop the scan computing and
   tracking it and show the frozen July record everywhere, or keep it as a live reference list and
   remove the "frozen" wording and the −14.1% from the public page. Publishing −14.1% as final
   while −30.3% accrues elsewhere is the one issue with reputational cost.
2. **If it stays live, give it a real cut-off and a real exit** (F1). Fewer seats than qualifiers,
   and a rule that can remove a name between annual reports (for example a trend or drawdown test,
   or quarterly rather than annual growth). Without this it is a list, not a screen.
3. **Remove or redesign the analyst-support multiplier** (F2). It is constant for 24 of 28 names,
   improves as the price falls, and accepts targets with no recent update.
4. **Benchmark it against a semiconductor fund as well as the global index** (F4), and relabel
   "YTD" as "since 2026-06-04". Correct the 2026-09-07 point to 2026-07-21 for this basket.
5. **Decide the non-US question on purpose** (F5): either require a target and say the basket is
   US-listed only, or let names without a target qualify with a neutral multiplier.
6. **Apply the existing peak-cycle flag** (F6), at least as a visible marker.
7. Make the return-on-capital gate strictly positive and treat missing as fail (F7); rename the
   stored field or stop formatting it as a percentage (F8); tighten the scope list (F9); treat a
   missing revision score as neutral, not zero (F10).

## 8. What I could not check

- The record before 2026-07-21 (−14.1%) period by period — the rebalance log was lost in the wipe.
- When SNDK, STX, WDC, LRCX and LITE really entered the live picks file, and what the live basket
  held between 07-21 and 09-22. Only the 2026-11-07 scan is available, so I could not replay the
  gates on the six earlier weekly scans.
- How the pages actually render; I read the front-end code but did not open the site.
- SMH and QQQ figures come from the local close cache, not a second source.
- Whether the −0.35 score-to-return relationship holds outside this one sell-off.
