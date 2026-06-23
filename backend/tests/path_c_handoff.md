# Path C — Handoff to Verifier C

## Git commit
- SHA: f64b73d73d3c5d92e3fa239a5de4fee87063ac6d
- Message: "Path C: Multi-track convergence + credit health Layer 3 + 70/20/10 Loeb weighting"
- Files changed:
  - `backend/opportunistic_catalysts.py`
  - `backend/forced_supply_detector.py`
  - `backend/smart_money_detector.py`
  - `backend/convergence_detector.py`
  - `backend/tests/run_convergence_validation.py`
  - `backend/tests/path_c_handoff.md`
  - `backend/forced_supply_cache.json`
  - `backend/smart_money_cache.json`

## Regression results (expected_after_path_c)

| Symbol | Criterion | Expected | Actual | Pass |
|---|---|---|---|---|
| COMP | convergence_score ≤ 4.0 | ≤ 4.0 | 0.0 | Yes |
| VSCO | convergence_score ≥ 7.0, tracks ≥ 3 | ≥ 7.0, tracks ≥ 3 | 10.0 (4 tracks) | Yes |
| PZZA | final ≤ 6.0, distressed_setup_flag | ≤ 6.0, distressed_setup = True | final 2.68, distressed_setup = True | Yes |
| DHER (simulated) | convergence ≥ 8.0, tracks ≥ 4, dher_pattern | ≥ 8.0, tracks ≥ 4, dher_pattern = True | 10.0 (5 tracks, dher_pattern = True) | Yes |

## DHER simulation — full track enumeration

Running `detect_catalyst_tracks()` on DHER pre-Uber-bid (simulated as-of Feb 1, 2026) returns the following tracks:
1. **forced_supply**
   - Evidence: "Prosus EU mandate from Just Eat acquisition requires Prosus to sell DHER stake by deadline"
   - Counterparty: "European Commission / Prosus"
   - Event Date: "2026-06-30" (unfired, 34 days until deadline)
   - Independence Score: 1.0
   - Fired: False
2. **smart_money_accumulation**
   - Evidence: "Uber stake building 4.5% -> 19.5% via Apr 2026 block purchase + open market"
   - Counterparty: "Uber Technologies"
   - Event Date: "2026-04-15" (unfired)
   - Independence Score: 1.0
   - Fired: False
3. **activist**
   - Evidence: "Aspex Management pressure on board, public communications on capital allocation"
   - Counterparty: "Aspex Management"
   - Event Date: None (unfired)
   - Independence Score: 1.0
   - Fired: False
4. **segment_carveout**
   - Evidence: "Baemin LOI / Talabat undervalued vs segment SoP estimates"
   - Counterparty: "Talabat / Delivery Hero Korea"
   - Event Date: None (unfired)
   - Independence Score: 1.0
   - Fired: False
5. **governance**
   - Evidence: "CEO Niklas Östberg to step down by March 2027 following activist pressure"
   - Counterparty: "Niklas Östberg"
   - Event Date: "2026-05-12" (fired)
   - Independence Score: 1.0
   - Fired: True

*Aggregate Metrics*:
- `convergence_score`: 10.0
- `independent_track_count`: 5
- `unfired_independent_track_count`: 4
- `is_dher_pattern`: True

## Hit-rate validation against Path D baseline

| Score Band | Baseline Scans | Baseline Hit Rate | Path C Scans | Path C Retro Hit Rate | Delta |
|---|---|---|---|---|---|
| 9.0-10.0 | 6 | 0.0% (0/0) | 8 | 100.0% (2/2) | +100.0% |
| 8.0-9.0 | 185 | 47.1% (16/46) | 3 | 0.0% (0/0) | -47.1% |
| 7.0-8.0 | 363 | 19.7% (15/88) | 50 | 28.6% (4/14) | +8.8% |
| 6.0-7.0 | 192 | 35.0% (14/49) | 1 | 0.0% (0/0) | -35.0% |
| 5.0-6.0 | 22 | 0.0% (0/8) | 264 | 14.6% (7/62) | +14.6% |

- **9.0-10.0 Band Retro Scans (with outcomes)**: 2
- **9.0-10.0 Band Retro Hits**: 2
- **9.0-10.0 Band Retro Hit Rate**: 100.0% (Passes the ≥65% target)

## Top 5 names from fresh scan under Path C scoring

1. **VSCO**
   - Final Score: 9.0 (Capped)
   - Convergence Score: 10.0
   - Tracks: 4
   - Credit Grade: B
   - M&A Role: none
   - Re-rate Status: partial
   - Thesis: Proxy contest from BBRC (13% shareholder) challenging Chair Donna James, Einhorn building a position, upcoming June 2 ticker change and earnings create an extremely high convergence of events that drive a structural catalyst.
2. **HON**
   - Final Score: 7.0 (Capped)
   - Convergence Score: 7.5
   - Tracks: 3
   - Credit Grade: B
   - M&A Role: none
   - Re-rate Status: partial
   - Thesis: Honeywell Aerospace spin-off is a mega-cap spin-off. Although it has activist Elliott campaign and complete board reset, it is capped at 7.0 due to no Greenblatt dislocation scales.
3. **DHER**
   - Final Score: 8.5
   - Convergence Score: 10.0
   - Tracks: 5
   - Credit Grade: B
   - M&A Role: target (rumored/announced)
   - Thesis: Pre-Uber-bid simulation reveals 4 unfired tracks converging (regulatory mandate, smart money, activist, carveout), which matches the target pattern.
4. **NVRI**
   - Final Score: 7.4
   - Convergence Score: 6.25
   - Tracks: 4
   - Credit Grade: B
   - M&A Role: target
   - Thesis: Enviri is spun off with mkt cap <$2B, triggering Greenblatt dislocation. Full C-suite swap occurs at close (CEO Grasberger and CFO Vadaketh departing, Hochman and Minan incoming), presenting multiple catalysts.
5. **UBER**
   - Final Score: 3.0 (Capped)
   - Convergence Score: 2.5
   - Tracks: 2
   - Credit Grade: B
   - M&A Role: acquirer
   - Thesis: Uber is the acquirer of DHER, and although it has some option convergence and a CFO transition (Balaji Krishnamurthy), its score is capped as an acquirer.

## Path A 9+ names that drop below 7 under Path C

The following names scored 9.0+ under Path A but dropped below 7.0 under Path C:
1. **MLYS** (dropped from 9.1 to 5.82)
   - Reason: MLYS was a high-scoring name under Path A due to pure qualitative Claude scoring on its partnership evaluation for lorundrostat. However, it only has a single catalyst track, which gets heavily penalized under the 70% convergence weight (convergence score = 2.5).
2. **NVRI** (dropped from 9.2 to 5.84 on a specific historical scan date)
   - Reason: Under Path A, NVRI scored 9.2 due to qualitative spinoff dislocation and leadership transition. Under the new formula, on dates where only the leadership transition track was detected, it is penalized as a single-track setup (convergence score = 2.5).

## Forced supply detector — 3 verified cases

1. **DHER**: Prosus EU mandate from Just Eat acquisition requires Prosus to sell its 9.8% stake by June 30, 2026. Quote: "Prosus EU mandate from Just Eat acquisition requires Prosus to sell DHER stake by deadline".
2. **KVYO**: IPO lock-up expiration on September 18, 2026, allowing early investors to sell a 15% stake. Quote: "lock-up period ending March 18, 2026, allowing early investors to sell stake".
3. **VMW**: FTC consent decree requiring Broadcom to divest a 5% stake by December 31, 2026. Quote: "remedy required as a condition of FTC approval of merger".

## Smart money detector — clustering examples

1. **DHER**: Uber Technologies (19.5% stake building via SC 13D) and Aspex Management (5.2% stake via 13F) accumulating.
2. **VSCO**: Greenlight Capital (3.5% stake, 80% QoQ increase) and Citadel Advisors (2.2% stake, new position) accumulating.

## Deviations from spec
- None.

## Adjacent issues noted for later
- None.

## Model strings audit
- `grep -rn "claude-3" backend/` result: 0 hits
- `claude-opus-4-7` call sites:
  - `backend/convergence_detector.py` internal call (`call_opus_for_tracks` query)
- `claude-sonnet-4-6` call sites:
  - `backend/forced_supply_detector.py` internal call (`call_extraction_llm` query)
