# Handover → the chat running the Speculair weekly routine (2026-07-28)

**From:** the debt-cycle build session (2026-07-27)
**Status of the work:** merged to `main`, tests green. Nothing here needs your action *before*
the routine — this is what changed and what to watch while it runs.

---

## 0 — Read these first

- `CLAUDE.md` (repo root) — the macro stack is now THREE axes; the FORK decisions and the
  invariants that must not be broken are there.
- `MACRO_REGIME_DIRECTOR_LOGIC.md` — full wiring, §9b is the debt-cycle addendum.

---

## 1 — What is new since last week's run

Two independent workstreams landed on `main` and were merged together (`1be7999`):

**A. `ux-revamp` (Bruno's parallel work)** — already his decisions, not mine to re-litigate:
- `_post_common.EQUAL_WEIGHT_BOOKS = True` — every book publishes 1/n. Evidence: across 2151
  dated debate records Director conviction had no monotone relation to forward return, and its
  top grade was its worst bucket.
- The book has **no fixed seat count**. Dilution is the discipline: a name only earns a seat if
  it is at least as good as the current median seat.
- STEP 3a **entry-discount floor**, scaled by regime: ≥+20% GOLDILOCKS/REFLATION, ≥+25%
  STAGFLATION, ≥+30% RISK_OFF.
- Director memo must OPEN with a `ROTATION` subsection (ADDED / DROPPED / KEPT / RE-ADDED).
- `thesis_break_px` is now a required per-pick field.
- The weekly run gates on a real run marker, not the apex file's mtime.

**B. The Dalio debt-cycle layer (this session)** — a third macro axis, `backend/debt_cycle.py`:
`EXPANSION | DISCIPLINE | FORCING | MONETIZATION`, a path-dependent state machine with
two-publish hysteresis and one legal step per publish.

---

## 2 — The one thing to understand about the cycle layer

**It gives direction, not sizing.** Bruno, 2026-07-27: *"the macro should give us
trends/direction, not weigh on the picks."*

Macro reaches the book through exactly four channels, none of which is a weight:

| Channel | Where |
|---|---|
| `risk_stance` posture (DISCIPLINE caps at balanced, FORCING floors at defensive, MONETIZATION unlocks aggressive) | Director STEP 1 |
| Entry-discount floor — a bar to clear | Director STEP 3a |
| Horizon stretch (12 → 18-24mo in DISCIPLINE/FORCING) | `expected_horizon_months` |
| `phase_fit` — one sentence per seat, judgement input | per-pick field |

The duration cap **is advisory**. It still trims `size_units_effective` and stamps
`duration_cap_effect: "advisory"`, so `_cycle_ledger.jsonl` accumulates evidence — but the
published weight stays 1/n. The secular-theme and correlation caps are inert in exactly the
same way; this is not special to the cycle layer.

**Do not "fix" this by making the cap live.** Flipping `EQUAL_WEIGHT_BOOKS` is a sizing change
that touches both the apex and value books.

---

## 3 — What the routine will do differently

New step, already wired into the pipeline — no action needed:

1. `_write_macro_regime()` (setup phase) computes the phase and **ticks the state machine**.
   This is the ONLY call site that advances it (`advance=True`). Everything else reads.
2. **RegimeRead** now argues against the phase dials as well as the quadrant, and emits
   `phase_falsifiers` with `check_by` dates.
3. **Director STEP 1** applies the phase modifier on top of the quadrant playbook, and STEP 6
   must echo `debt_cycle_phase`, `phase_read`, `expected_horizon_months`.
4. `_regime_post` stamps each pick's deterministic `duration_bucket` and computes the
   (advisory) cap.
5. `publish_to_frontend` writes the `debt_cycle` block, per-pick badge fields, and appends one
   row to `_cycle_ledger.jsonl` with the **realized duration mix**.

---

## 4 — Log lines to check while it runs

```
macro_regime: NEUTRAL (score 0.5475) | quadrant REFLATION | cycle DISCIPLINE (2w) -> macro_regime.json
duration-cap [ADVISORY — no published weight moves]: DISCIPLINE story<= 20% BOUND — units trimmed on [...]
cycle ledger += 2026-07-28 DISCIPLINE (2w) / mix {...} / binding ['duration_story']
```

**Red flags:**

| Symptom | Meaning | Action |
|---|---|---|
| `cycle UNKNOWN` or `FAIL-LOUD WARN: debt_cycle_phase is UNKNOWN` | classifier couldn't reach its data | Not fatal — loosest caps, no stance modifier (fail-open by design). Note it; don't patch mid-run. |
| `WARN duration-cap: N/N seats have NO FCF data` | the scan lacks `p_fcf`/`fcf_margin` | Means the scan is thin/stale. Names are labelled `unknown`, NOT `story`, and sit outside the cap. This is the fail-open guard working. |
| `TreasuryDirect ... HTTP 4xx` or auction cache empty | Saturday auction job never ran | One of six gauges goes neutral; the phase still reads on the other five. Run `python backend/debt_cycle.py fetch-auctions` when convenient. |
| Phase flipped in one week | should be impossible | Hysteresis requires the target to repeat on two consecutive publishes. If it flipped in one, something bypassed `advance_state` — investigate before trusting the read. |

---

## 5 — Known-unverified (be sceptical here)

The build sandbox could not reach FRED or TreasuryDirect (gateway 403), so:

- **Never executed against live data:** the FRED CSV fetches (`DFII30`, `BAMLH0A0HYM2`,
  `WALCL`, interest/receipts) and the TreasuryDirect auction fetch. Parsing is unit-tested
  against realistic payloads; the HTTP round-trip is not.
- **Verified live:** the FMP treasury curve and `inflationRate` series. `inflationRate` is
  daily and reads ~2.26 while CPI is ~4% — it is market-implied *expected* inflation, so the
  real-rate fallback is `nominal 30y − inflationRate`. If FRED works in production, TIPS take
  priority and this fallback never fires.
- Tomorrow's run is the **first live exercise** of those fetchers. If a gauge reports
  `missing` in `cycle_sub_sources`, that is where to look.

---

## 6 — Current state (seeded, will advance tomorrow)

```
phase DISCIPLINE · week 1 · cycle_score 0.665 · confidence low (2 of 6 gauges live in sandbox)
basis: real 30y 2.90% (rising) × 30y-3m +120bp
```

Expect `confidence` to rise to `high` on your machine once FRED/TreasuryDirect resolve.
`weeks_in_phase` should read 2 after tomorrow's publish.

---

## 7 — Still open

- **Saturday auction job not scheduled.** `python backend/debt_cycle.py fetch-auctions`,
  05:00 Europe/Amsterdam Saturdays, one hour before the routine. Self-heals inline if the
  cache is >8 days stale, so it is not blocking.
- **`apply_macro_tilt` / `regime_composite_floor`** in `macro_regime.py` remain imported and
  never called — pre-existing dead wiring, flagged not fixed.
- **`test_regime_post` weight-sum tolerance** was relaxed 1e-6 → 1e-3. `build_weights` rounds
  each weight to 4dp so the sum lands ~1e-4 off; the strict assert was failing before this
  work existed (verified red at `03f3a71`).

---

## 8 — Verify commands

```bash
python backend/tests/test_debt_cycle.py        # 54 checks, must print ALL PASS
python backend/_opus_debate/test_regime_post.py # baseline, must not crash
python backend/debt_cycle.py                    # live read, no state advance
```
