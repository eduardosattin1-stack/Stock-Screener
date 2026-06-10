# ML Track-Record Audit — 2026-06-10

Multi-agent audit (5 dimensions × adversarial verification; 36 agents, 31 findings verified:
26 confirmed, 5 partially-confirmed/sharpened, 0 refuted). Scope: the four-method live
track record on `/performance`, the tracking methodology in `backend/signal_tracker.py`,
and the time_model_v3 ML pipeline. Raw GCS cycle data snapshot in `_audit_data/`.

**Verdict: QUARANTINE the displayed track record, FIX serving + measurement, keep the
append-only raw ledger and recompute outcomes offline. The model as deployed is not the
model that was validated.**

---

## 1. What the page actually shows today (all numbers reproduced exactly from raw data)

Cycle opened 2026-05-31; today is day ~10 of a 30/60-day window. **Zero windows have
elapsed — every resolved row is an early barrier-touch or stop.** Window-end (TERMINAL)
resolutions are mechanically impossible before 2026-06-30 / 2026-07-30.

| Stat | Displayed (resolved-only) | Blended mark-to-market |
|---|---|---|
| Stock × 10%/30d — mean ROI / win | +5.72% / 78.3% | **−0.48% / 46%** |
| Stock × 20%/60d — mean ROI / win | +25.47% / 100% | **−2.01% / 41%** |
| Long Call × 10%/30d — port ret | +2.70% | **−26.22%** (−$103k unrealized on $356k basis) |
| Long Call × 20%/60d — port ret | +1.77% | **−22.11%** |

The 60d-stock "100% win rate" is structural: that arm has no stop, so the only possible
mid-cycle resolution is a touch. `CALIBRATION 0%` is an empty-bucket sentinel (D10 n=0),
not an observed hit rate. `PICKS 1520` double-counts 760 picks across the two streams.

## 2. Tracker methodology defects (signal_tracker.py)

1. **Resolution censoring (critical).** Win%/ROI/median/tails computed over
   `realized_return_pct != None` rows only (`_method_stats`, :748–762) — i.e. early
   winners. 608–743 of 760 rows per arm are still open at a median −1.2% mark.
2. **Touch fills booked at the intraday peak, not the barrier** (:2179). Mean phantom
   gain +2.85pp (30d) / +5.47pp (60d) per hit; max booked +47.86% on a +10% barrier.
   Permanent contamination of the append-only ledger.
3. **Stop semantics asymmetric-optimistic.** Trigger on scan close, fill recorded at
   exactly −20.0% (actual closes averaged −22.2%, worst −29.6%); barrier checked before
   stop; intraday stop-throughs that recover don't stop, intraday spikes do count as hits.
   6 open rows have already breached −20% intraday and remain open.
4. **Entry look-ahead.** Entry at scan-time FMP quote; entry day's full OHLC counts
   toward the barrier; 2 same-day resolutions observed (e.g. BFLY +14.12% on day 0).
   ~80% of rows are Sunday-dated entries at stale Friday quotes — Monday gap booked as gain.
5. **Kill switch is blind mid-cycle.** `_compute_rolling_d10_health` counts CLOSED rows
   immediately, skips immature OPEN rows → observed_rate is touch-conditioned (100% on the
   60d stream) and DEGRADED can never fire while censoring dominates.
6. **FLAG "OK" gates on total n (760), not resolved n** (16–17 on the 60d arms).
7. ThetaData credentials hardcoded in plaintext, 5 locations (separate security fix).

## 3. The model: validated ≠ deployed

Training/validation discipline is genuinely good (purged walk-forward CV, uniqueness
weighting, real gates; holdout AUC 0.709, Brier 0.219, slope 1.118). But:

1. **Train/serve skew (critical).** 40 of 59 features are constants at inference —
   32 median-filled (`ML_MEDIANS`, screener_v6.py:330–334) + 8 hard-pinned 0.0 —
   including **8 of the top-10 by importance**. The #1 feature `f_sector_momentum` is fed
   in wrong units (0–1 score vs raw 3m return); `f_upside_rank` (training: rank of sector
   momentum, not analyst upside) is a constant 0.4998 live; `f_op_margin`/`f_fcf_yield`
   fed wrong quantities. Emulating live serving collapses prediction spread:
   p_max 0.787→0.536 (30d), 0.685→0.436 (60d) — exactly matching the observed live caps
   (0.4989 / 0.4975). **The empty D8–D10 deciles are a serving artifact, not legitimate
   sparsity.** (Corrects the prior belief recorded 2026-06-05.)
2. **Horizon mismatch (critical).** Trained on 30/60 *trading bars*, entry bar excluded;
   live tracker resolves over 30/60 *calendar days* (~21/~41 trading days), entry day
   included. Live hit rates will mechanically undershoot model p even if perfectly calibrated.
3. **Decile thresholds & baselines are in-sample.** Derived by scoring full-data deploy
   models (trained 2019→2026-02) on the ≥2025-06-01 slice *inside* their training window.
   Claimed baselines (D10 83.2% 60d / 70.45% 30d) not reproducible: honest holdout
   reproduction ≈ 0.709 / 0.760.
4. **Survivorship + no embargo.** Universe = present-day optionable list (no delisted);
   every sample requires 60 future bars; no purge at the 2025-06-01 OOS cutoff.
5. **Thin real edge.** AUC lift over a single-feature `f_vol_60d` baseline: **+0.0079**.
   The model is, in substance, a volatility-touch ranker. Its own basket validation shows
   **negative edge vs option-implied touch probabilities (−0.07..−0.10)** — i.e. options
   are priced richer than the model's probabilities, so the long-call arms are
   structurally −EV by the model's own numbers.
6. 47.6% prevalence for +10%/30d touch is real (high-vol optionable universe), not a bug.

## 4. Frontend

Compliant on the two project rules (no client-side deciles; per-record table present).
Defects: resolved-only Win%/ROI shown beside n=760 with no caveat (the only censoring
disclosure is on the calibration card, which has the opposite-direction bias); red "0%"
calibration KPI for an empty bucket; PICKS double-count; FLAG semantics.

## 5. Recommendation (priority order)

1. **Quarantine the display, not the data.** Annotate/hide Win%/ROI/port-ret until fixed;
   keep nightly collection running — entry rows (price/date/decile/p) are clean
   (0 null prices, 0 missing deciles, 0 barrier mismatches, 0 dup symbols).
2. **Fix serving skew before anything else** — it invalidates every downstream number.
   Either wire the 32 missing features live, or (better) retrain a slim model on the 27
   genuinely live-available features with corrected units/mappings.
3. **Align measurement with the trained target:** trading-day windows, exclude entry day,
   fill at barrier price, consistent stop convention (intraday or close, pick one and
   mirror it in training), no stale-weekend entries.
4. **Recompute baselines + deciles honestly:** holdout-trained models, embargoed cutoff,
   thresholds stored in the model artifact, baselines from holdout only.
5. **Fix reporting:** blended MTM columns alongside resolved-only; maturity-aware
   kill-switch (compare hits-by-day-k vs expected hazard, or evaluate only elapsed
   windows); FLAG on resolved n; dedup PICKS; honest empty-state for D10.
6. **Recompute the current cycle's outcomes offline** from predictions.jsonl with the
   corrected resolver once fixed; mark the cycle `methodology_v1-flawed` either way.
7. Drop or demote the long-call arms unless the model beats option-implied probabilities
   after the serving fix — as validated, they measure option pricing, not model skill.

Raw audit output: `C:\Users\Bruno\AppData\Local\Temp\claude\C--Users-Bruno-Stock-Screener\ccb32805-ea94-45ce-b54f-657675b6e235\tasks\wdbibt7hg.output`
(parse with `_audit_data/parse_audit.py {overview|metrics|dim <key>}`).
