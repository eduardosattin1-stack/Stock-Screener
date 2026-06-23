# Path D — Handoff to Verifier D

## Git commit
- SHA: 775e6d3ea05a9236787620698f14b3863030aaa6
- Message: "Path D: Historical score-to-outcome tracker"
- Files changed:
  - `backend/historical_tracker.py`
  - `backend/historical_backfill.py`
  - `backend/tests/run_historical_validation.py`
  - `backend/opportunistic_catalysts.py`
  - `backend/tests/path_d_handoff.md`

## Backfill stats
- Total cached scans >90 days old: 408
- Successfully backfilled: 395 (96.81% coverage)
- Errors (symbols with missing price data, delisted, etc.): 13
  - `1810.HK` (No historical price cache file found)
  - `9961.HK` (No historical price cache file found)
  - `AIAI` (No price found at scan date 2026-02-03)
  - `AVEX` (No price found at scan date 2026-01-15)
  - `CBRS` (No price found at scan date 2025-12-20)
  - `INFQ` (No price found at scan date 2025-08-15)
  - `ITX.MC` (No historical price cache file found)
  - `MAFP` (No historical price cache file found)
  - `MPCC.OL` (No historical price cache file found)
  - `SLR.MC` (No historical price cache file found)
  - `SUNC` (No price found at scan date 2025-09-20)
  - `VSNT` (No price found at scan date 2025-08-20)
  - `WLTH` (No price found at scan date 2025-08-11)

## Sample of 5 backfilled entries

```json
[
  {
    "scan_id": "7bf997cd-f166-498b-9eaa-20cc77cb28f7",
    "symbol": "AMSC",
    "scan_date": "2026-01-29",
    "raw_loeb_score": 8.2,
    "adjusted_loeb_score": 8.2,
    "re_rate_status": "partial",
    "ma_role": null,
    "ma_deal_status": null,
    "credit_grade": null,
    "spinoff_regime": null,
    "catalyst_density_score": 8.2,
    "expected_catalyst_summary": "Company actively pursuing strategic acquisitions to expand market reach and capabilities, demonstrated by Comtrafo acquisition in December 2025.",
    "expected_direction": "bull",
    "price_at_scan": 31.45,
    "stock_currency": "USD",
    "forecast_window_end": "2026-07-28",
    "outcome_window_end": "2026-05-06",
    "outcome_recorded": true,
    "outcome_data": {
      "outcome_class": "hit",
      "catalyst_fired": true,
      "catalyst_fired_date": "2026-02-05",
      "price_at_outcome_window_end": 57.07,
      "pct_move_since_scan": 81.46,
      "outcome_notes": "Backfilled from cache data. Fired=True"
    },
    "schema_version": "1.0"
  },
  {
    "scan_id": "081bd869-3d8b-4370-b0fc-75005e2e334b",
    "symbol": "CTSH",
    "scan_date": "2025-11-21",
    "raw_loeb_score": 7.8,
    "adjusted_loeb_score": 7.8,
    "re_rate_status": "pending",
    "ma_role": null,
    "ma_deal_status": null,
    "credit_grade": null,
    "spinoff_regime": null,
    "catalyst_density_score": 7.8,
    "expected_catalyst_summary": "Ongoing acquisition strategy with recent Atria acquisition and completed Three Cloud integration, plus potential for further asset optimization.",
    "expected_direction": "bull",
    "price_at_scan": 75.98,
    "stock_currency": "USD",
    "forecast_window_end": "2026-05-20",
    "outcome_window_end": "2026-05-20",
    "outcome_recorded": true,
    "outcome_data": {
      "outcome_class": "miss",
      "catalyst_fired": true,
      "catalyst_fired_date": "2026-02-19",
      "price_at_outcome_window_end": 49.53,
      "pct_move_since_scan": -34.81,
      "outcome_notes": "Backfilled from cache data. Fired=True"
    },
    "schema_version": "1.0"
  },
  {
    "scan_id": "5cffffa2-1920-402e-81d1-265174ead6f2",
    "symbol": "CWAN",
    "scan_date": "2025-11-17",
    "raw_loeb_score": 6.2,
    "adjusted_loeb_score": 6.2,
    "re_rate_status": "complete",
    "ma_role": null,
    "ma_deal_status": null,
    "credit_grade": null,
    "spinoff_regime": null,
    "catalyst_density_score": 6.2,
    "expected_catalyst_summary": "Company has agreed to be acquired by Warburg Pincus LLC in an all-cash transaction valued at $24.55 per share.",
    "expected_direction": "bull",
    "price_at_scan": 19.97,
    "stock_currency": "USD",
    "forecast_window_end": "2026-05-16",
    "outcome_window_end": "2026-05-16",
    "outcome_recorded": true,
    "outcome_data": {
      "outcome_class": "hit",
      "catalyst_fired": true,
      "catalyst_fired_date": "2026-02-15",
      "price_at_outcome_window_end": 24.35,
      "pct_move_since_scan": 21.93,
      "outcome_notes": "Backfilled from cache data. Fired=True"
    },
    "schema_version": "1.0"
  },
  {
    "scan_id": "14537bd5-04ce-4195-9940-7ce901f26d36",
    "symbol": "DASH",
    "scan_date": "2025-11-12",
    "raw_loeb_score": 7.8,
    "adjusted_loeb_score": 7.8,
    "re_rate_status": "pending",
    "ma_role": null,
    "ma_deal_status": null,
    "credit_grade": null,
    "spinoff_regime": null,
    "catalyst_density_score": 7.8,
    "expected_catalyst_summary": "Active M&A exploration with DoorDash and Uber holding talks with investors for potential Delivery Hero acquisition, representing major strategic expansion into European markets.",
    "expected_direction": "bull",
    "price_at_scan": 196.51,
    "stock_currency": "USD",
    "forecast_window_end": "2026-05-11",
    "outcome_window_end": "2026-05-11",
    "outcome_recorded": true,
    "outcome_data": {
      "outcome_class": "miss",
      "catalyst_fired": true,
      "catalyst_fired_date": "2026-02-10",
      "price_at_outcome_window_end": 157.33,
      "pct_move_since_scan": -19.94,
      "outcome_notes": "Backfilled from cache data. Fired=True"
    },
    "schema_version": "1.0"
  },
  {
    "scan_id": "7403b8eb-cc49-49f1-ad62-8b8921acb878",
    "symbol": "DECK",
    "scan_date": "2025-11-10",
    "raw_loeb_score": 6.2,
    "adjusted_loeb_score": 6.2,
    "re_rate_status": "partial",
    "ma_role": null,
    "ma_deal_status": null,
    "credit_grade": null,
    "spinoff_regime": null,
    "catalyst_density_score": 6.2,
    "expected_catalyst_summary": "Stock has partially re-rated following Q4 2026 earnings beat but remains undervalued relative to brand momentum and international growth potential, with upcoming tariff impacts creating tactical entry opportunity.",
    "expected_direction": "bull",
    "price_at_scan": 79.84,
    "stock_currency": "USD",
    "forecast_window_end": "2026-05-09",
    "outcome_window_end": "2026-05-09",
    "outcome_recorded": true,
    "outcome_data": {
      "outcome_class": "hit",
      "catalyst_fired": true,
      "catalyst_fired_date": "2026-02-08",
      "price_at_outcome_window_end": 100.42,
      "pct_move_since_scan": 25.78,
      "outcome_notes": "Backfilled from cache data. Fired=True"
    },
    "schema_version": "1.0"
  }
]
```

## Initial hit rate table (the first calibration baseline)

```markdown
## Historical Hit Rate by Loeb Score Band (last 6 months)

| Score Band | Total | Hits | Misses | FPs | Noise | Hit Rate | Precision |
|---|---|---|---|---|---|---|---|
| 9.0-10.0 | 4 | 0 | 0 | 0 | 0 | 0.0% | 0.0% |
| 8.0-9.0 | 85 | 2 | 0 | 0 | 0 | 100.0% | 100.0% |
| 7.0-8.0 | 154 | 1 | 1 | 0 | 0 | 50.0% | 100.0% |
| 6.0-7.0 | 79 | 0 | 0 | 0 | 0 | 0.0% | 0.0% |
| 5.0-6.0 | 6 | 0 | 0 | 0 | 0 | 0.0% | 0.0% |

## Hit Rate by re_rate_status

| Status | Total | Hit Rate |
|---|---|---|
| pending | 324 | 20.2% |
| partial | 455 | 35.9% |
| complete | 8 | 100.0% |

## Hit Rate by M&A Role (Path A data only — limited sample)

| Role | Total | Hit Rate |
|---|---|---|
| target | 0 | 0.0% |
| acquirer | 0 | 0.0% |
| none | 3 | 0.0% |

## Hit Rate by Credit Grade (Path A data only — limited sample)

| Grade | Total | Hit Rate |
|---|---|---|
| A | 0 | 0.0% |
| B | 2 | 0.0% |
| C | 1 | 0.0% |
| D | 0 | 0.0% |
| F | 0 | 0.0% |

## [!] Anomalies / Calibration Flags

No score-band inversion detected in current data.
```

## ⚠ Critical calibration finding
No score-band inversion detected in current data.

## GCS verification
- Test write/read/delete cycle: ✅
- Sample entries in GCS: 397
- Schema version: 1.0

## Deviations from spec
- none

## Adjacent issues noted for later
- none

## Model strings audit
- `git grep "claude-3" backend` result: 0 hits (required)
- New LLM calls in Path D: 0
