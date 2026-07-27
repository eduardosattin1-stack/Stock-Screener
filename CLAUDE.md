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
- **FORK 2/B — portion control, with a badge.** The phase NEVER gates eligibility or
  touches conviction. It caps the aggregate `story` duration-bucket share of the book
  (`_regime_post.enforce_duration_caps`, trims lowest-conviction first toward a 0.1u
  floor, never demotes) and modifies stance (`apply_phase_to_stance`). Every director
  pick publishes `duration_bucket` + `cycle_capped` badge fields; the tracker renders
  C/P/S chips with a ✂ when trimmed.
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

## Other standing notes

- `apply_macro_tilt` / `regime_composite_floor` in `macro_regime.py` are imported but
  never called (known dead wiring — see MACRO_REGIME_DIRECTOR_LOGIC.md §9). Decide
  wire-or-delete before adding anything near them.
- Tests: `python backend/tests/test_debt_cycle.py` (fixture = the 2026-07 tape;
  must read DISCIPLINE) and `python backend/_opus_debate/test_regime_post.py`.
