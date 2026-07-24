# Apex selection-authority decision rule — pre-registered 2026-07-24

Written BEFORE the first full-pool run under the neutralized rubric, so the result forces a
decision instead of another study. Supersedes the ad-hoc success metric in the 2026-07-21
synthesis (which was circular — see Finding 2 below).

---

## Evidence already banked (2026-07-24 cohort joins)

Panel: 2,151 point-in-time debate records, 422 symbols, 18 run-dates (2026-06-05 → 07-21),
joined to FMP daily closes. Bootstrap CIs cluster on SYMBOL (weekly carry-forwards make
entry-level observations autocorrelated). One regime, ~7 weeks — a real limit, not hidden.

**Join 1 — the catalyst penalty was negative-EV, not a positive-EV cost.**

| cohort | n (entries) | fwd-to-now | fwd 21d |
|---|---|---|---|
| PENALIZED (FIRED / SOFT_EXTENDED) | 1,867 | **+1.64%** | **+2.52%** |
| NON-PENALIZED (PENDING_HARD / ARB) | 121 | **−2.14%** | **−4.23%** |
| difference (clustered bootstrap) | | +3.76pp, 95% CI [+1.27, +6.34] | +6.70pp, CI [+2.09, +11.08] |

Both significant. Date-matched (within each run-date, fixed 21-day horizon, killing calendar
composition): **penalized won 6 of 7 dates, mean +5.38pp**. Not an arb-caps-upside artifact —
PENDING_HARD alone is the single worst bucket (−4.77% at 21d, 35% win rate), worse than ARB.

Corollaries from the same panel:
- **conviction has no monotone signal**: buckets 1→5 return +1.36 / +1.48 / +1.94 / +1.22 / +1.69%.
- **verdict-A was the worst bucket**: −1.92%, 38% win rate (n=26) vs verdict-B +2.08%, C +1.44%.
- catalyst-blind `value_conviction` orders weakly *better* than catalyst-tilted `conviction`
  (2 → −2.04%, 3 → −1.60%, 4 → −0.49%; date-composition differs, so read the ordering, not the level).

**Join 2 — the valuation stack is not inverted; it is uninformative above the bottom quintile.**

| implied upside quintile (sop_fair_value vs price at debate) | fwd-to-now |
|---|---|
| Q1 (−83% … −15%) | **−2.29%** |
| Q2 (−15% … −0.4%) | +3.04% |
| Q3 (−0.4% … +11%) | +2.13% |
| Q4 (+11% … +25%) | +1.32% |
| Q5 (+25% … +135%) | +2.91% |

NO_UPSIDE vs positive-upside: −1.68pp, CI [−3.55, +0.14] — **not significant**.
Spearman(upside, forward return) = +0.099 entry-level, +0.252 symbol-clustered.
Reading: the stack correctly identifies the worst tail (Q1) and then **cannot rank anything**
between Q2 and Q5. It is a floor detector, not a return ranker.

**Gate map** (answering the review's open question): `NO_UPSIDE` is a **B13 edge_flag**
(`_numeric_core.rr_ratio_lane` → `_B13_BLOCKING`), *not* an apex gate. In the regime apex the hard
block is `numeric_gate ∈ {REJECT, EXCLUDE_ELIGIBILITY}`, enforced **twice**: the Director's STEP-3
eligibility line, and deterministically in `_regime_post.numeric_demote()` (seat → runner_ups).
THIN_FLOOR (downside-to-floor < 15% of live) is the reason that actually fires in practice.
So after the catalyst neutralization, DAVE/SEZL-profile names are **not** hard-blocked in the apex —
they face the Director's discretionary preference for wide computed R:R, which is a soft filter.

---

## The three findings that change how this is justified

1. **Lead with the structural argument, not the 20/20 stat.** Post-B13 the reward pole of the
   catalyst axis is unreachable by construction, so a lever that can only demote is a tax, not a
   tilt. The 20/20 winner stat is winner-conditioned and proves nothing on its own. It is now
   *corroborated* by Join 1's denominator — but the structural argument is what carries the change.
2. **The 20-winner control re-run was circular** (remove the clause that blocked 20 names, then
   check those 20 names pass). It is retained ONLY as a regression smoke test — specifically for the
   forensic-exclusion invariant. It is not evidence of selection value.
3. **One-tape humility.** Everything here is a ~7-week window where buying strength in cheap quality
   worked and washouts were not offered. Frame the change as "removing a lever that cannot earn its
   keep post-B13", NOT as "the Director's caution was refuted". Keep it reversible.

---

## The fork — pre-committed

Three layers hold selection authority: mechanical baskets, the debate, B13. The evidence assigns
them different competencies — baskets earned the alpha; the debate seated 0 of the top 20 winners
while its *vetoes* were its one clear win (CORT/INSP/HUBG/MOH quarantined with live fraud/DOJ
actions); B13 owns events cleanly.

- **Side A — repair the debate's selection role.** What shipped on 2026-07-21 (`16a1cd69`) is a
  step down this path.
- **Side B — demote the debate to VETO-AND-SIZE.** Screens select; the debate may only subtract
  (forensic / skeptic / moat) and size (macro stance); B13 handles events. One-directional
  authority per layer, which eliminates the incoherence of names that are simultaneously
  basket-owned and debate-rejected.

### Decision rule (evaluated at the first full-pool run under the neutralized rubric)

Measured on the FULL debated cohort, not on the 20 winners:

- **ADOPT SIDE B** if EITHER:
  - (a) the cash-earnings winning profile (FIRED/SOFT + iv15/ev_gp/ev_gross_profit/acquirers +
    clean forensic) still fails to reach ≥3 apex seats, **and** the blocking reason is the
    valuation stack (`numeric_gate` demotes or Director R:R preference) rather than catalyst
    residue; or
  - (b) the newly-eligible pool grows but the seated book is ≥80% unchanged — i.e. the Director
    ignores the widened pool, proving the constraint was never the rubric text.
- **STAY ON SIDE A** if the neutralized rubric seats ≥3 of that profile AND the seated book differs
  from the old-rubric book by ≥2 names. Then re-evaluate after one quarter of paper divergence.
- **In EITHER case**, the valuation stack goes on the work list: Join 2 shows it cannot rank above
  the bottom quintile, so any book that leans on `sop_fair_value` ordering is leaning on noise.

Explicitly NOT a Side-B trigger: "0 verdict-A". The panel shows verdict-A was the worst-performing
bucket; the absence of A's is not evidence of over-restriction.

---

## Test design (replaces the circular metric)

1. **Snapshot** (done 2026-07-24, `_prefork_snapshot/`): the old-rubric apex + the full eligible
   pool + every record's grade, so the post-run diff is computable.
2. **Full-pool diff** at the next weekly run: eligible-pool delta, seat delta, and the *reason* each
   winning-profile name did or did not seat (conviction floor / numeric gate / Director preference).
3. **Paper divergence**: track the neutralized-rubric apex against the pre-change apex for one
   quarter. Both are paper; neither trades.
4. **Regression invariant**: CORT / INSP / HUBG / MOH must remain excluded by the forensic ledger +
   skeptic + value forensic gate. The 2026-07-21 control re-run showed the *debate layer alone* no
   longer floors INSP/MOH (fresh committees scored them interrogator-3) — so this invariant is now
   carried entirely by the ledger/skeptic layers. **If it ever fails, that is a stop-ship.**

---

## Open items carried forward

- **`risk_stance` survives on an identity argument, not evidence** — nothing in any study attributes
  P&L to quadrant sizing. It is the apex's last differentiator from the value lens under Side A.
  INSTRUMENT it (log per-seat sizing decisions vs a flat-sized counterfactual) so next quarter can
  test it rather than grandfather it.
- **#2 is one correlated factor bet.** iv15 / ev_gp / ev_gross_profit / acquirers are all
  cheap-on-cash-earnings. Size it as a single factor decision, not four independent ones.
- **Momentum was mislabeled, not defeated** (autopsy 2026-07-24): its 20 holdings had median
  52-wk-range position 0.617, RSI 49, MoS 0 — while the actual ripper cohort (275 in-scan names
  ≥+50% off the low and in the top 15% of their range) had median position 0.92, RSI 60, MoS
  **−0.199**. Overlap: **2 of 20** (AMD, ASML); only 2 of 20 holdings were near their own 52-wk high.
  The upstream MoS≥0 anchor structurally excluded the momentum cohort, so the screen could never
  hold momentum. Retire it for mislabeling — the −14.12% is a symptom, not the reason.
- **Universe coverage is the larger, separate lane.** Corrected capture rate of the in-scan ripper
  cohort: **13 of 275 (5%)** — independently reproducing the review's 4–8% figure. Of the 262 missed,
  **249 have MoS ≤ 0**: mechanically invisible to every value screen, so this is NOT fixable at the
  apex. Two near-free wins belong here: (i) a **spin-off auto-add rule** (parent in universe ⇒
  children inherit eligibility at distribution — GEV was never re-added after the GE split, on a
  platform whose own regime doc ranks spins the #1 lane); (ii) a **year_high/year_low sanity check**
  plus 15–40% market-cap reconciliation vs FMP.
- **The `proximity_52wk` bug that seeded the "only CAR escaped" myth**: the field is
  position-from-low (0 = at the 52-wk low), so the original miss filter demanded "+50% off the low
  AND in the bottom 12% of the range" — near-impossible, which is why it returned exactly one name,
  and that one only because a corrupt `year_high` (847.7) inflated its range. Any future miss audit
  must assert the orientation empirically before filtering.
