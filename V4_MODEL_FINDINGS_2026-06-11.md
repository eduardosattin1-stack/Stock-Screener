# time_model v4 — Findings & Edge Verdict (2026-06-11)

Companion to [ML_TRACK_RECORD_AUDIT_2026-06-10.md](ML_TRACK_RECORD_AUDIT_2026-06-10.md).
All numbers below are from the **embargoed holdout** (n=102,803 rows, 2,819 symbols,
scan_date 2025-06-02 → 2026-02-24, models trained strictly before 2025-03-03 with a
60-trading-bar purge). Every economics number was independently re-derived by an
adversarial verifier from raw price files (exact match, zero corrections).
Reproduce: `backend/scratch/holdout_economics.py` → `holdout_economics_results.json`.

## 1. Model quality (validation: time_model_v4_validation.json — all 7 gates passed)

| Target | AUC | Brier | Calib. slope | f_vol_60d alone | Lift |
|---|---|---|---|---|---|
| +10% touch / 30 bars | 0.708 | 0.219 | 1.12 | 0.701 | +0.007 |
| +10% / 60 bars | 0.687 | 0.212 | 1.13 | 0.677 | +0.010 |
| +20% / 30 bars | 0.783 | 0.141 | 1.16 | 0.767 | +0.015 |
| +20% / 60 bars | 0.749 | 0.196 | 1.19 | 0.732 | +0.017 |

Slopes >1 = model slightly under-confident. Lift gate (≥ +0.005 over the single
volatility feature) enforced and passed — but note how thin it is.

## 2. Decile calibration + stock-arm economics (sold-AT-barrier policy)

Strategy: touched → sold exactly at the barrier; never touched → exit at bar-K close.
Per-window percentages, NOT annualized (overlapping samples). BH = buy-and-hold same window.

**+10% / 30 bars** (decile edges from p=0.230 → 0.659; pooled touch rate 47.6%)

| D | n | Touch | Strat mean | BH mean | Non-toucher mean | Mean maxDD | DD≤−20% | Bars-to-touch |
|---|---|---|---|---|---|---|---|---|
| 1 | 9,626 | 17.6% | +0.62% | +0.63% | −1.4% | −5.1% | 1% | 18.9 |
| 5 | 10,819 | 45.6% | +1.35% | +1.85% | −5.9% | −8.6% | 9% | 14.2 |
| 9 | 10,173 | 69.1% | +2.64% | +7.49% | −13.8% | −13.4% | 23% | 9.7 |
| 10 | 10,632 | **75.7%** | +3.00% | **+11.77%** | **−18.8%** | −17.2% | **35%** | 7.7 |

**+20% / 60 bars** (edges 0.103 → 0.578; pooled touch 37.4%)

| D | n | Touch | Strat mean | BH mean | Non-toucher mean | Mean maxDD | DD≤−20% |
|---|---|---|---|---|---|---|---|
| 1 | 9,104 | 5.6% | +1.37% | +1.33% | +0.3% | −7.0% | 3% |
| 5 | 8,085 | 32.5% | +2.95% | +3.58% | −5.3% | −12.0% | 19% |
| 9 | 10,405 | 60.4% | +5.98% | +13.71% | −15.4% | −18.3% | 38% |
| 10 | 11,262 | **70.8%** | +8.16% | **+25.35%** | **−20.5%** | −21.4% | **47%** |

Key spreads: strat D10−D1 = +2.38pp / +6.79pp (survives 20bps friction); BH D10−D1 =
+11.14pp / +24.03pp. **The barrier-sell mechanic destroyed value in this tape:** pooled
strat − BH = −1.92pp (30d) / −3.59pp (60d) — it caps the right tail the deciles select
for while leaving the left tail open.

## 3. The volatility-control test (the decisive one)

Model decile and 60d volatility are heavily confounded (off-diagonal cells nearly empty:
low-vol quintile has ~zero D8+ rows and vice versa). Within the comparable quintiles
(Q2–Q4), comparing D≥8 vs D≤3:

- **Touch-rate spread stays strongly positive** (30d: +31/+23/+15pp; 60d: +19/+33/+38pp)
  → the model genuinely predicts barrier touches *beyond* what volatility explains.
- **Strategy-return spread collapses or inverts** (30d Q3 −0.6pp, Q4 −2.4pp; 60d Q2
  −0.3pp, Q4 −1.5pp) → under the sold-at-barrier policy, the *economic* edge within a
  vol band is approximately zero.

## 4. Verdict — do we have an edge?

1. **Probability-calibration edge: YES (modest, real).** Monotonic 4.3×/12.6× D1→D10
   touch-odds separation, survived embargo + gates + independent reverification, and the
   touch-rate spread survives vol-matching. The model is a genuine, calibrated
   touch-probability ranker.
2. **Economic edge from the sold-at-barrier stock strategy: NO (in this regime).**
   What looked like strategy edge is high-beta exposure; buy-and-hold on the same picks
   dominated, and within vol bands the strategy spread vanishes. Win-small-lose-big:
   median D10 return saturates at +barrier while non-touchers average −19/−20%.
3. **Edge vs the options market: NO.** Model touch probabilities run 7–10pp *below*
   option-implied — the market prices these events richer than we do. Corollary: if the
   model is right, the structural opportunity is *selling* that premium, not buying it
   (untested; would need margin/assignment modeling).
4. **What the model is actually worth:** honest probability inputs — position sizing,
   "don't buy premium here" vetoes, candidate ranking for the catalyst/Speculair books —
   rather than a standalone trading strategy. If the stock arm should make money, the
   exit policy (not the picker) is the thing to redesign: trend-capture with stops vs
   barrier caps, regime-conditional.

## 5. Caveats (all load-bearing)

- Survivorship: universe = present-day optionable list → absolute return LEVELS
  optimistic; decile SPREADS are the trustworthy part.
- One ~9-month bullish regime; the barrier-cap penalty vs BH is regime-dependent and
  could flip in a flat/down tape.
- Overlapping windows (every-5th-day grid) → n's overstate effective sample size; no
  naive t-stats or annualization.
- Live confirmation pending: the calibration tracker v2 (first v4 cohort 2026-06-11)
  is the only forward, leak-proof test. D10-predicted 75.7% should observe ≈75.7%.

## 6. Document map

| Artifact | Content |
|---|---|
| `ML_TRACK_RECORD_AUDIT_2026-06-10.md` | The audit: censoring bias, serving skew, 31 verified findings |
| `backend/time_model_v4_meta.json` | Decile edges, per-decile hit rates, time-to-touch CDFs |
| `backend/time_model_v4_validation.json` | AUC/Brier/slopes/gates |
| `backend/scratch/holdout_economics.py` + results JSON | This document's §2–§3, reproducible |
| `/performance` (live) | Forward calibration: expected-vs-observed touches, accruing nightly |
