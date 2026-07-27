# Handover — debt-cycle build session (2026-07-27)

**To:** the chat running the Speculair weekly routine
**From:** the session that built the Dalio debt-cycle layer
**All of it is on `main`, tests green.** This is what was done, what was decided and why, and
what is deliberately left open.

---

## 1 — TL;DR

The macro stack went from **two axes to three**. A new module, `backend/debt_cycle.py`,
classifies where the sovereign sits in the long-term debt cycle —
`EXPANSION | DISCIPLINE | FORCING | MONETIZATION` — and feeds it to the Apex Director,
the briefing, and a new ledger.

The layer **gives direction, not sizing**. That was Bruno's explicit call and it is the single
most important thing to carry forward (§3, FORK 2).

Also merged in the same session: the `ux-revamp` branch (equal-weight books, no fixed seat
count, entry-discount floor, ROTATION memo). Those are Bruno's prior decisions — not this
session's — but they interact with the cycle layer and that interaction is why the duration cap
ended up advisory.

---

## 2 — Commits on `main` (oldest → newest)

| Commit | What |
|---|---|
| `03f3a71` | `MACRO_REGIME_DIRECTOR_LOGIC.md` — documents the existing classifier → Director wiring, including the dead wiring nobody had written down |
| `aa43275` | The debt-cycle layer: module, state machine, splices, Director/RegimeRead prompts, post layer, publish, frontend, ledger, tests |
| `f37ea40` | **Fail-open fix** — the duration cap was pinning whole books to the floor on missing FCF data |
| `22440b0` | **Auction fetcher fixes** — reopenings were being dropped; tenors were being pooled |
| `1be7999` | Merge of `ux-revamp` (one conflict, in the Director prompt) |
| `746e79e` | Duration cap relabelled **advisory** end-to-end + this handover |

---

## 3 — Decisions Bruno made (do not silently reverse these)

**FORK 1 → A. Separate module.** `debt_cycle.py` stands alone with its own GCS cache and
fetchers, spliced into *both* the v7 and v8 regime fetchers via `_attach_debt_cycle`.
Rationale: the growth×inflation quadrant lives only in v7 and would have been silently stripped
by a v8 switch. A separate module cannot be lost that way. **Do not fold it into
`macro_regime.py`.**

**FORK 2 → C, ADVISORY.** Originally specced as a duration cap with real sizing authority.
Bruno, verbatim: *"the macro should give us trends/direction, not weigh on the picks (that's
too complicated)."*

So the cap computes and trims `size_units_effective`, stamps
`duration_cap_effect: "advisory"`, and writes the realized duration mix to
`_cycle_ledger.jsonl` — **but moves no published weight.** The secular-theme and correlation
caps are inert in exactly the same way under `EQUAL_WEIGHT_BOOKS=True`; this is not special to
the cycle layer.

Macro reaches the book through exactly four channels, none of which is a weight:

| Channel | Where |
|---|---|
| `risk_stance` (DISCIPLINE caps at balanced · FORCING floors at defensive · MONETIZATION unlocks aggressive) | Director STEP 1 |
| Entry-discount floor — a bar to clear, not a weight | Director STEP 3a |
| Horizon stretch, 12 → 18-24mo | `expected_horizon_months` |
| `phase_fit` — judgement input, one sentence per seat | per-pick field |

The cap is kept live-but-inert on purpose: the ledger accumulates evidence so *"would trimming
story duration in DISCIPLINE have helped?"* becomes answerable from data instead of priors.
**Flipping `EQUAL_WEIGHT_BOOKS` off is a SIZING change**, not a display change — it makes every
cap live across both the apex and value books.

**FORK 3 → A. Auction fetcher built.** TreasuryDirect 10y/30y results feed `auction_quality`.

**FORK 4 → yes.** A phase transition forces a live-Director re-run outside the 30-day
cost-guard. "The bond market is cracking" must not sit unread for a month.

---

## 4 — What was built

**`backend/debt_cycle.py`** — 6 gauges, weights summing to 1.0:
real 30y rate `0.25` · term premium `0.20` · auction quality `0.15` · debt service `0.15` ·
credit stress `0.15` · CB balance sheet `0.10`.

Convention is **inverted** vs `macro_regime.py`: here *higher = later in the cycle / more
stress*. Mixing the two is an easy bug.

- **State machine**, not a stateless classifier: one legal step per publish, two-publish
  hysteresis, illegal jumps logged as `transition_blocked`. Prevents a hot CPI print from
  jumping to MONETIZATION and telling the Director to buy gold six months early.
- **FORCING is gated on live funding stress**, not just a high composite. The 2026 tape maxes
  the discipline gauges and brushes 0.70 while credit sits at 310bp and auctions cover 2.3× —
  that is severe DISCIPLINE, not a crisis.
- **Gold is a falsification check only, never scored.** Scoring gold into a phase that drives
  buying real assets is a momentum loop wearing a macro costume; it would have bought the
  Jan-2026 top. Inconsistency raises a falsifier for RegimeRead, it does not move the score.
- **Fail-open throughout:** `UNKNOWN` phase = loosest caps + no stance modifier, published with
  a FAIL-LOUD warning. A data outage must never tighten the book.

**Wiring** (every call site shipped in the same commit as its code — this repo's recurring
failure mode is imported-but-never-called tables):

- `_write_macro_regime` publishes the cycle block and is the **only** call site that advances
  the state machine (`advance=True`). Everything else reads.
- RegimeRead argues against the phase dials too, emitting `phase_falsifiers` with `check_by`
  dates. The one-notch rule is unchanged: an agent CONTRADICT tempers stance, never flips a dial.
- `_regime_post` stamps the deterministic `duration_bucket` and computes the advisory cap.
- `live_debate_engine`: the live Director's macro brief is now **grounded in the snapshot**
  instead of model recall (it previously got only the date and a sector histogram), plus the
  phase-transition re-run trigger.
- Frontend: `CYCLE · PHASE (Nw)` chip beside the quadrant chip with dated falsifiers, and C/P/S
  payback badges on tracker rows.
- `_cycle_ledger.jsonl`: one row per publish including the **realized duration mix**.

---

## 5 — Bugs found during the build (worth knowing about)

**1. The duration cap failed CLOSED on missing data.** `screener_v6` defaults `p_fcf` and
`fcf_margin` to `0.0`, so a scan record with *no* cash-flow data was byte-identical to one with
genuinely no FCF. Both were labelled `story`, and DISCIPLINE's 20% cap then slammed **every
seat** to the 0.1u floor. A data gap tightening the book is precisely what the fail-open rule
forbids. Fixed by adding a fourth bucket, `unknown`, which sits outside the cap and prints a
WARN. Caught by `test_regime_post`, whose fixture has no FCF data.

**2. The auction fetcher dropped reopenings — ~2/3 of what matters.** Treasury sells 10y/30y
originals quarterly and reopens them monthly; a reopening's `securityTerm` reads
`"9-Year 10-Month"`, so a `startswith("10-")` filter kept ~4/yr/tenor instead of ~12. The gauge
needs 5 auctions before reporting, so it would have sat neutral for months *while looking
healthy*. Now matches `originalSecurityTerm`.

**3. Pooling the tenors made the score depend on auction order.** Comparing "latest vs trailing
4" across a mixed 10y/30y series is apples-to-oranges — notes structurally cover better than
bonds. A 30y print following three 10y prints read as deteriorating demand with nothing moving;
on the test fixture that pushed the gauge to 0.71, over the 0.70 FORCING gate — a false crisis
signal from pure sequencing. Now scored per tenor against its own history: same fixture reads
0.62.

**4. `test_regime_post` was already red before this work.** Its weight-sum assert demanded 1e-6
but `build_weights` rounds each weight to 4dp, so the sum lands ~1e-4 off. Verified red at
`03f3a71` via a temp worktree. Relaxed to 1e-3 with the arithmetic documented, rather than
making `build_weights` renormalize exactly — that would move published weights in **both** the
apex and value books.

---

## 6 — The `ux-revamp` merge

Five commits, one conflict, in the Apex Director prompt (STEP 4/5/6 — both branches edited the
same lines). Resolved by taking **ux-revamp as the base** (it carries the newer direction) and
layering the debt-cycle additions on top. Verified field-by-field that both survived:

- From ux-revamp: no fixed seat count, dilution-as-discipline, `EQUAL-WEIGHT` note,
  `thesis_break_px`, the ROTATION memo subsection, the regime-scaled entry floor.
- From this session: the phase modifier in STEP 1, `phase_fit` and `duration_bucket_override`
  per pick, and the STEP 6 `debt_cycle_phase` / `phase_read` / `expected_horizon_months` echoes.

The merge is also *why* FORK 2 became advisory: equal-weight publishing landed in parallel and
neutralises every cap's effect on published weight.

---

## 7 — For the run itself

New behaviour is already wired; nothing to do beforehand. Log lines to expect:

```
macro_regime: NEUTRAL (score …) | quadrant REFLATION | cycle DISCIPLINE (2w) -> macro_regime.json
duration-cap [ADVISORY — no published weight moves]: DISCIPLINE story<= 20% BOUND — units trimmed on [...]
cycle ledger += 2026-07-28 DISCIPLINE (2w) / mix {...} / binding ['duration_story']
```

| Symptom | Meaning | Action |
|---|---|---|
| `cycle UNKNOWN` / `FAIL-LOUD WARN` | classifier couldn't reach its data | Not fatal — loosest caps, no stance modifier, by design. Note it; don't patch mid-run |
| `WARN duration-cap: N/N seats have NO FCF data` | thin/stale scan | The fail-open guard working. Names are `unknown`, not `story` |
| `TreasuryDirect … HTTP 4xx` / empty auction cache | Saturday job never ran | One of six gauges neutral; phase reads on the other five |
| Phase flipped in one week | should be impossible | Hysteresis needs two consecutive publishes. Investigate before trusting the read |

**Current seeded state:** `DISCIPLINE · week 1 · cycle_score 0.665 · confidence low` (only 2 of
6 gauges reachable from the build sandbox). Expect `confidence: high` and `weeks_in_phase: 2`
after tomorrow's publish.

---

## 8 — Known-unverified (be sceptical here)

The build sandbox could not reach FRED or TreasuryDirect (gateway 403), so:

- **Never executed against live data:** the FRED CSV fetches (`DFII30`, `BAMLH0A0HYM2`,
  `WALCL`, interest/receipts) and the TreasuryDirect auction fetch. Parsing is unit-tested
  against realistic payloads; the HTTP round-trip is not. **Tomorrow is their first real
  exercise.** If a gauge reports `missing` in `cycle_sub_sources`, that is where to look.
- **Verified live via FMP MCP:** the treasury curve (matches the spec fixture exactly — 30y
  5.16%, 10y 4.69% on 2026-07-24) and `inflationRate`. That series is daily and reads ~2.26
  while CPI is ~4%, i.e. market-implied *expected* inflation — so the real-rate fallback is
  `nominal 30y − inflationRate`. Where FRED works, TIPS take priority and the fallback never
  fires.

---

## 9 — Still open

- **Saturday auction job not scheduled.** `python backend/debt_cycle.py fetch-auctions`,
  05:00 Europe/Amsterdam Saturdays, one hour before the routine. Non-blocking: the classifier
  self-heals inline when the cache is >8 days stale.
- **`apply_macro_tilt` / `regime_composite_floor`** in `macro_regime.py` are still imported and
  never called — pre-existing dead wiring, documented in `MACRO_REGIME_DIRECTOR_LOGIC.md` §9,
  flagged not fixed. Decide wire-or-delete before adding anything near them.
- **Score `_cycle_ledger.jsonl` quarterly.** That is the evidence that would justify making the
  duration cap live, or deleting it. The cap thresholds in `PHASE_DURATION_CAPS` are hand-tuned
  priors, like every threshold in `macro_regime.py`.

---

## 10 — Verify

```bash
python backend/tests/test_debt_cycle.py         # 54 checks, must print ALL PASS
python backend/_opus_debate/test_regime_post.py # baseline, must not crash
python backend/debt_cycle.py                    # live read, no state advance
```

Read `CLAUDE.md` (repo root) for the invariants and `MACRO_REGIME_DIRECTOR_LOGIC.md` for the
full wiring before touching any of this.
