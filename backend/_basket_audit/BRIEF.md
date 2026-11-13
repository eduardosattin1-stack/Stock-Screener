# Basket audit, November 2026 — reviewer brief

You are one of thirteen independent reviewers. Twelve of you each audit ONE methodology basket; one
audits the selection, rotation and tracking machinery all twelve share. Your assignment (which
basket, or "machinery") is in the message that sent you here.

## Why this matters

The twelve baskets in `scans/methodology_picks.json` are the screen that decides which companies the
weekly multi-agent debate ever looks at. Two books are then picked from that debate: the regime
("apex") book and the value book. The owner follows the value book with his own money. A basket
that ranks on a broken number, admits junk, or rotates for data reasons instead of real ones
silently degrades everything downstream. The goal is to establish whether each basket is SOUND.

"Sound" means all of:
1. **The rule does what it says.** The code computes the stated method correctly (formula, units,
   currency, per-share vs total, the period used) and the gates that are supposed to protect it do.
2. **The names it picks are what the method intends.** They rank high because of the economics the
   method measures, not because of a data artefact (a currency or unit mismatch, a default value
   treated as real, a one-off, a peak year, a capped or saturated number, a stale statement).
3. **It rotates for real reasons.** Names enter and leave because the metric genuinely moved, not
   because a field went missing, a price series broke, or the ranking is a coin-flip between ties.
4. **Its record is measured correctly.** The tracked return reflects what the picks actually did.

## Rules of engagement

- **Read-only.** Do not edit any existing file. Do not run the production scan, prep, any publish,
  or anything that writes to GCS. You may run small read-only Python snippets to inspect data.
- **Write exactly one file:** your report (path below). Nothing else.
- **Evidence or it did not happen.** Every finding needs either a code citation (`file:line`) or a
  number you computed from the data, ideally both. Separate what you CONFIRMED (you reproduced it)
  from what you SUSPECT (plausible, not reproduced) — never present a suspicion as a fact.
- **Check before you claim a root cause.** If a number looks wrong, look at the raw scan row and the
  code path before deciding why. A lead in this brief is a lead, not a conclusion.
- **Use the live market data tools when a pick looks wrong.** Load the FMP tools with ToolSearch
  (keywords such as "FMP quote", "FMP statements", "FMP company") to check a price, a currency, a
  statement line or what kind of security a ticker is. Web search is available for the same purpose.
  Budget: roughly 10 to 15 spot checks; pick the names that would change your verdict.
- Do not give investment advice. You are auditing a screen.

## Where things are

Everything is under `C:\Users\Bruno\Stock-Screener`.

**Your evidence pack:** `backend/_basket_audit/packs/<basket>.json` (about 120 KB — load it with
Python and slice it; do not print it whole). It contains:
- `summary` — qualifiers in the whole scan, the basket's cut-off, ties at the cut-off, entry-date
  counts, the debate grades of the picks, how many picks the debate's gates threw out, mean return
  since entry against ACWI, exits logged, mean return AFTER exit, and tracking fields.
- `picks[]` — every current pick with its entry date and price, the metric in the picks file and in
  the scan, its rank in the scan on that metric, return since entry, a `scan` block (price,
  currency, `fx_to_price`, sector class, years of history, structural-break flag, cycle flag, every
  method's fair value and margin of safety) and a `debate` block (grade A/B/C, value conviction,
  thesis state, numeric gate, forensic gate, the debate's own discount to fair value, whether the
  name holds a seat in either book).
- `rebalances_since_reconstruction[]`, `all_exits_2026[]` (each with the return after exit),
  `recent_exits_in_picks_file[]`, `tracking_current_holdings[]`.

**All baskets at a glance:** `backend/_basket_audit/packs/_overview.json` (overlap matrix, which
basket each seat came from, names by number of baskets).

**Raw snapshots:** `backend/_basket_audit/methodology_picks.json` and `methodology_tracking.json`
(the live GCS files as of 2026-11-12).

**The scan:** `backend/_opus_debate/latest_global.json` — 26 MB, 3,430 stocks, 194 fields each,
scan dated 2026-11-07. Load with `json.load`, index by `symbol`, read only the rows you need.

**Daily closes:** `backend/_opus_debate/_px_cache/<SYMBOL>.json` (`{date: close}` since June 2026,
vendor data, local currency).

**The code:** `backend/screener_v6.py` (7,336 lines — read by line range, never whole):

| What | Lines |
|---|---|
| Local 10-year yields table | 98–110 |
| `PICKS_PER_METHODOLOGY`, history floor | 111–125 |
| `_methodology_applicable` (which sectors each method applies to) | 898–960 |
| Valuation defaults (every method starts at −1.0) | 2060–2095 |
| Structural-break detection | 2780–2840 |
| Normalised EPS, de-peaked growth, `calc_mos` | 2840–2933 |
| 1 DCF-FCFF | 2934–2950 |
| 2 R&D-capitalised DCF | 2951–2967 |
| 3 Owner earnings | 2968–2987 |
| 4 EPV (Greenwald) | 2988–3007 |
| 5 Graham revised | 3008–3018 |
| 6 IV15 deep value | 3019–3040 |
| Tracking state, rebalance append, NAV / YTD | 6154–6510 |
| `_rank_ey_gap` (earnings-yield gap) | 6511–6532 |
| `_rank_ev_gp` (true EV / gross profit) | 6533–6581 |
| `save_methodology_picks` starts; GP/Assets rank; acquirer's multiple | 6582–6637 |
| Leverage gate, sector-diversified portfolio builder | 6638–6660 |
| Loading the previous picks (entry preservation) | 6661–6700 |
| Method table | 6700–6740 |
| Convergence basket | 6740–6803 |
| Fundamental-momentum basket | 6804–6858 |
| Rotation hysteresis and the selection loop | 6859–6990 |
| Exits list, picks serialisation | 6990–7105 |
| Paper tracker hook, year rollover | 7106–7140 |

`backend/replay_baseline.py` mirrors the selection for back-testing; `backend/audit_baskets.py` is
an older audit script. Both are optional reading.

## Facts you should know before you start

- **The history is short.** GCS was wiped around 2026-09-12 and rebuilt on 2026-09-22 from a
  2026-09-07 snapshot. Entry dates before that are reconstructed; the earlier rebalance log, exits
  and daily NAV are gone. Judge rotation on the seven weekly scans since 2026-09-22.
- **Two cadences.** The picks file can change every weekly scan; the paper tracker rebalances every
  14 days. The debate reads the picks file.
- **The scan is weekly** (Saturdays). Prices in the picks file are scan prices.
- **`fundamental_momentum` is retired from the debate universe** (since 2026-07-21) but still
  computed and tracked.
- **Leads already seen while building the packs — verify, do not assume:**
  - `50GP.L` sat in seven baskets with a margin of safety near the cap; the vendor price series
    reads 77 → 0.77 → 74.75 between mid-October and early November (pounds against pence?). It is
    not in the 2026-11-07 scan. What is this security, and why did seven methods love it?
  - Many logged exits carry `exit_metric: 0.0` and `unpriced_exit: true`.
  - `convergence` has 40 qualifiers in the whole scan for 30 seats and 38 logged exits.
  - `fundamental_momentum` has 28 qualifiers for 28 picks and no exits.
  - The four rank-based baskets (`earnings_yield_gap`, `ev_gross_profit`, `acquirers_multiple`,
    `ev_gp`) carry a "margin of safety" that is really a percentile-style rank; check what the
    number means, how ties are broken and whether the top of the list is distinguishable.
  - Four of the nine names currently seated in the two books come from NO basket.
  - Several non-US names appear across the value-method baskets; a past bug priced every non-US
    stock as dollars (fixed 2026-08-20, reading currency per symbol). Check whether any residue
    remains for your basket's picks (compare `currency`, `fx_to_price`, price and fair value).

## What to cover (basket reviewers)

1. **The rule.** Read the method's code. State in two or three plain sentences what it actually
   computes. Is it the method it claims to be? Any error in formula, units, currency conversion,
   per-share handling, period, sign, caps or defaults? Do the gates that apply to it work?
2. **The picks.** Go through all current picks. Which are there for the right reason and which look
   like artefacts? Group the suspicious ones by cause. Spot-check the worst against live data.
3. **Selectivity.** How many names qualify against how many seats? Is the cut-off meaningful, or is
   the basket taking nearly everything that qualifies, or choosing among ties or capped values?
4. **Rotation.** For every entry and exit since 2026-09-22: did the metric really move, or was it a
   data event? How much of the turnover is noise? Is the incumbency boost doing its job? What
   happened to names after they left?
5. **Does it feed the debate anything useful?** Grades of its picks, how many the gates rejected,
   the gap between the screen's discount and the debate's, seats it supplied, overlap with the
   other baskets (is it a distinct lens or a near-copy of another?).
6. **The record.** Is the tracked return consistent with the picks' actual price moves?
7. **Verdict:** SOUND, SOUND WITH ISSUES, or UNSOUND, in one line, then the fixes you would make,
   most important first, each with the evidence that justifies it.

## What to cover (machinery reviewer)

The shared code only, not any one method: loading the previous picks and entry preservation; the
hysteresis boost (is "10% of each method's max amplitude" applied consistently, and does it behave
for rank-based methods?); the leverage gate; the sector cap and `get_best_portfolio_of_size`; how
exits are detected, priced and logged (`exit_metric: 0.0`, `unpriced_exit`); the two cadences and
whether the tracker's holdings can drift from the picks file; `_compute_ytd_return` and
`realized_ytd` (is the return a correct equal-weight time-weighted figure, and is anything
double-counted or dropped at a rebalance?); the 2026-09-22 reconstruction; what happens when a held
name disappears from the scan; what happens when the previous picks cannot be loaded. Use the
packs of several baskets as test data. Same report format, same verdict line.

## Your report

Write `backend/_basket_audit/reports/<basket>.md` (or `machinery.md`). Plain language, no jargon
without a definition, short paragraphs, tables for lists of names. Structure:

1. Verdict (one line) and the two or three things that most justify it.
2. What the rule computes.
3. Findings, most serious first. For each: what is wrong, the evidence (`file:line` and/or the
   numbers), how many current picks it affects and which, CONFIRMED or SUSPECTED, and the fix.
4. Rotation since 2026-09-22.
5. What it contributes to the debate.
6. What you could not check.

Then reply to the session that sent you with: the verdict line, the findings as a short list (one
line each, with severity HIGH / MEDIUM / LOW and CONFIRMED / SUSPECTED), and the names of any picks
you consider artefacts. Keep that reply under 400 words — the detail lives in the report file.
