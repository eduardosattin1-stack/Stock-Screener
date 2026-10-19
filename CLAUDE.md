# CB Screener — repo memory

## Macro stack: THREE axes, not two (since 2026-07-27)

1. **Risk regime** — `backend/macro_regime.py` → `RISK_ON|NEUTRAL|CAUTIOUS|RISK_OFF`
2. **Growth × inflation quadrant** — same file → `GOLDILOCKS|REFLATION|STAGFLATION|RISK_OFF`
3. **Dalio debt-cycle phase** — `backend/debt_cycle.py` (SEPARATE module, deliberately) →
   `EXPANSION|DISCIPLINE|FORCING|MONETIZATION`, path-dependent state machine with 2-publish
   hysteresis, one legal step per weekly publish.

All three ride the v7 snapshot `backend/_opus_debate/macro_regime.json`
(written by `weekly_opus_refresh._write_macro_regime`, the ONLY call site that
advances the phase state machine). Read `MACRO_REGIME_DIRECTOR_LOGIC.md` for the
full wiring before touching any of it.

### Debt-cycle layer — decisions locked by Bruno (2026-07-27)

- **FORK 1/A — separate file.** `debt_cycle.py` must stay standalone (own GCS cache,
  own fetchers, spliced into BOTH v7 and v8 fetchers via `_attach_debt_cycle`).
  Rationale: the quadrant lives only in v7 and would have been silently stripped by a
  v8 switch; a separate module can't be lost that way. Do not fold it into
  `macro_regime.py`.
- **FORK 2/B → ADVISORY (amended 2026-07-27 after the ux-revamp merge).** Bruno:
  *"the macro should give us trends/direction, not weigh on the picks."* The phase NEVER
  gates eligibility, never touches conviction, and — while `_post_common.EQUAL_WEIGHT_BOOKS`
  is True — **moves no published weight either.** `_regime_post.duration_cap_entries` still
  trims `size_units_effective` (lowest-conviction story seats toward a 0.1u floor, never
  demotes) and stamps `duration_cap_effect: "advisory"`, so the audit trail and
  `_cycle_ledger.jsonl` accumulate the evidence; the published book stays 1/n. Note the
  secular-theme and correlation caps are inert in exactly the same way — this is not
  special to the cycle layer.
  **How macro actually reaches the book:** `risk_stance` (posture), the STEP-3a
  entry-discount floor (≥20% GOLDILOCKS/REFLATION · ≥25% STAGFLATION · ≥30% RISK_OFF —
  a bar to clear, not a weight), the horizon stretch (12 → 18-24mo in DISCIPLINE/FORCING),
  and `phase_fit` as judgement input to the Director. That's it.
  Flipping `EQUAL_WEIGHT_BOOKS` off makes every cap live again — that is a SIZING change,
  not a display change. Score `_cycle_ledger.jsonl` first.
- **FORK 3/A — auction fetcher built.** TreasuryDirect 10y/30y results feed
  `auction_quality`. Saturday job BEFORE the weekly routine:
  `python backend/debt_cycle.py fetch-auctions`
  (gcloud: schedule `0 5 * * 6`, Europe/Amsterdam — one hour before `paper-all-friday`'s
  Saturday 06:30 slot). Self-heals inline when the cache is >8 days stale.
- **Fork 4 — yes.** A phase transition forces a live-Director re-run outside the 30-day
  cost-guard (`live_debate_engine._phase_transition_check`; last-seen phase stamped as
  `director_last_phase` in the speculair output).
- **Payback-speed label** (`duration_bucket`: cash_now / payback_2_3y / story / **unknown**)
  is DETERMINISTIC (`debt_cycle.duration_bucket`, from scan `p_fcf`/`fcf_margin`).
  Director may override only with a written dated justification; unjustified overrides
  are dropped. This is the first macro-adjacent field with numeric sizing authority —
  treat changes to it as cap changes, not cosmetics.
- **`story` vs `unknown` is load-bearing — do not collapse them.** screener_v6 defaults
  `p_fcf`/`fcf_margin` to 0.0, so a name with no cash-flow data is byte-identical to one
  with genuinely no FCF. The first build collapsed both to `story`, and a thin scan pinned
  the ENTIRE book to the 0.1u floor under the DISCIPLINE cap — a data gap tightening the
  book, which the fail-open rule forbids. `unknown` sits OUTSIDE the story cap and prints
  a WARN. Regression test: "a no-FCF-data book is NOT trimmed by the story cap".

### Invariants (do not break)

- Sub-score convention is INVERTED vs macro_regime.py: higher = later in cycle / more stress.
- Gold / reserve assets are a falsification check ONLY, never a scored input
  (momentum-loop guard — it would have bought the Jan-2026 gold top).
- Fail-open: `UNKNOWN` phase = loosest caps + no stance modifier. A data outage must
  never tighten the book. `_write_macro_regime` warns FAIL-LOUD when publishing UNKNOWN.
- Phase citations are NOT valid `delta_justification` for conviction moves
  (`_regime_post._dated_fact_outside_phase`). Macro reaches weights via the caps, never conviction.
- Cap thresholds in `PHASE_DURATION_CAPS` are hand-tuned priors; the track record that
  will justify changing them is `backend/_opus_debate/_cycle_ledger.jsonl` (one row per
  publish, includes the realized duration mix). Score it quarterly.
- FRED series (DFII30, HY OAS, WALCL, interest/receipts) come via keyless fredgraph CSV;
  this sandbox's proxy blocks FRED/TreasuryDirect (403), production does not. The real-rate
  master dial has an FMP fallback (nominal 30y − `inflationRate`, which is market-implied
  expected inflation ~2.3%, NOT realized CPI).

### Quadrant inputs — repaired 2026-10-12 (do not regress)

- From the day it shipped (2026-07-16) to 2026-10-12 the quadrant ran on a **0.5 CPI no-data
  default + a hardcoded Q4-2025 GDP seed** and printed GOLDILOCKS every week (true tape: CPI
  +3.35% y/y, accelerating). Root cause: FMP `economic-indicators` ignores from/to WINDOWS
  (0-1 rows) but answers POINT queries (from == to). `_fetch_monthly_series` now backfills by
  point query (v7 + v8 + historical). Never re-add hardcoded macro seeds.
- Quadrant inflation axis = CPI y/y level + 6m-annualized trend (`cpi_measures`, matched by
  DATE — Oct-2025 CPI was never published). Growth axis = REAL GDP, annualized, live paths only
  (historical/backtest keep nominal QoQ). `quadrant_inputs` carries provenance; when it is not
  ok the quadrant publishes UNKNOWN (fail-open) and `_write_macro_regime` FAIL-LOUDs; the
  briefing shows "QUADRANT · INPUTS STALE" instead of a label-derived guess.
  Mid-week repair without ticking the cycle: `weekly_opus_refresh.py macro-refresh`.
- `debt_cycle.advance_state` is a no-op within 4 days of the last tick (same weekly publish):
  a re-prep after a paused run can no longer add a week or a second hysteresis tick.
- `inflation_resilience` (`backend/inflation_resilience.py`, Bruno-approved 2026-10-12):
  deterministic per-name label from the 2021-22 gross-margin path (resilient/mixed/exposed/
  unknown) -> `_opus_debate/inflation_resilience.json`, read by macro_fit + the Director as a
  JUDGEMENT input only (FORK 2/B: no weight, no gate, no conviction; unknown never a penalty).
  Thresholds are priors — score them before giving the label teeth.

### Held-seat re-debate triggers (2026-10-19, `backend/_seat_triggers.py`)

A held seat gets a light weekly update (delta) unless a trigger forces a FULL re-debate. Beyond the
existing ones (wash-out, dated catalyst, escalation, 91-day refresh, new transcript), three fixes:
1. **Price** is measured from the last FULL debate (`full_debate_px`, stamped by lane-stamp;
   older seats fall back to the close on `last_full_debate`). Delta agents restate
   `valuation.live_price` weekly, so the old check only saw week-over-week moves (INTU +19% read +5.6%).
2. **Results release** from FMP reported-earnings dates, so names without an FMP transcript
   (HK/KS listings) re-underwrite on their own results.
3. **Macro change**: the quadrant or debt-cycle phase differs from the read at the seat's last full
   debate (`macro_at_full_debate`) AND the seat is exposed (its debate called macro a tailwind or
   headwind; inflation-exposed margins into REFLATION/STAGFLATION; a story-duration name into
   DISCIPLINE/FORCING). Runs in prep AFTER `_write_macro_regime`. Capped at `MACRO_U_CAP` per run,
   oldest first. It re-checks the thesis only and never gates, weights or touches conviction
   (FORK 2/B); an UNKNOWN read never triggers.

## Other standing notes

- `apply_macro_tilt` / `regime_composite_floor` in `macro_regime.py` are imported but
  never called (known dead wiring — see MACRO_REGIME_DIRECTOR_LOGIC.md §9). Decide
  wire-or-delete before adding anything near them.
- Tests: `python backend/tests/test_debt_cycle.py` (fixture = the 2026-07 tape;
  must read DISCIPLINE), `python backend/tests/test_macro_inputs.py` (fixture = the
  2026-10-12 tape; must read REFLATION), `python backend/tests/test_seat_triggers.py` and
  `python backend/_opus_debate/test_regime_post.py`.
  On Windows set `PYTHONIOENCODING=utf-8` or the arrow glyphs crash the cp1252 console.
