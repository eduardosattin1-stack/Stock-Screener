# Handoff — PIT Replay Baseline + Fix A + Frontend Wiring

**Date:** 2026-05-29
**Author:** Bruno (brunomoedim) + Claude
**Commit:** `a00c1965` — *feat: PIT replay baseline + Fix A hysteresis scaling + frontend wiring*
**Branch:** `main` (pushed → triggers Vercel + Cloud Run auto-deploy)
**Status:** ✅ Shipped & verified end-to-end in local dev. One known follow-up (live Active-row population) confirmed correct-by-design; will materialize on next live screener run.

---

## 1. What this work set out to do

The frontend's per-methodology track records were **hardcoded placeholder literals** in `METHODOLOGIES_CONFIG` (`frontend/app/page.tsx`) plus a `getBasketReturn()` sine-wave projection. Those numbers were *stitched approximations* — a mix of 1-year LLM-debate CAGRs and market-shaped annual estimates — and diverged from reality by **multiples, not inches** (e.g. dcf_fcff showed 3.5% vs the real 25.7%; 2022 showed −12.4% when a value basket was actually positive).

Goal: replace them with an **honest, screener-parity, point-in-time (PIT) 5-year replay** of all 9 methodologies, after fixing two real defects discovered during validation.

---

## 2. The two fixes (validated before wiring)

### Fix A — Hysteresis boost scaling (LIVE BUG)
- **Problem:** `save_methodology_picks` applied a flat `HYSTERESIS_BOOST = 0.05` incumbency boost. For the three *rank* methods (compressed MOS amplitudes: ev_gp ±0.15, ey_gap ±0.125, acquirers ±0.20), 0.05 was ~3× too strong — it cemented below-median incumbents. `ev_gross_profit` showed a **24.5-month avg hold and −42% drawdown** from lock-in.
- **Fix:** boost now scales to 10% of each method's MOS amplitude via `_hyst_boost(key)`. Absolute methods stay at 0.05 (unchanged, well-calibrated); rank methods scale down proportionally.
- **Applied to BOTH:** `backend/screener_v6.py` (production selection) **and** `backend/replay_baseline.py` (replay mirror).

### Fix 2 — G2b PIT proxy (REPLAY-ONLY)
- **Context:** Live screener has a real forward-looking G2b gate (drops cyclical-peak names with declining forward EPS consensus). The replay can't see forward estimates (FMP analyst-estimates is current-only → would be lookahead), so G2b was inactive in replay → replay was marginally too permissive on peak-cycle names.
- **Fix:** PIT proxy in `replay_baseline.py` only — drops `PEAK_CYCLE` earnings-method names whose **trailing** annual EPS rolled over (≥25% YoY off a positive base). Catches the confirmed-rollover subset.
- **Honest ceiling:** trims ~⅓–½ of the peak-cycle gap, not all of it (names still at peak with rising trailing EPS have no PIT signal — but G1 peak-normalization already demotes those). Earnings-method PEAK_CYCLE share dropped **18% → 15.16%**, in the expected window.
- **Live screener G2b is untouched** — it keeps its real forward-looking gate.

---

## 3. Backend deliverables

### `backend/replay_baseline.py` (NEW, 583 lines)
PIT 5-year monthly replay harness. Key properties:
- **Parity:** imports & calls `screener_v6.get_value()` unchanged; mirrors the 3 rank methods + leverage gate + sector-cap selection from `save_methodology_picks`.
- **PIT discipline:** monkeypatches `cached_fmp` to serve on-disk cache trimmed to `filingDate <= T`; `FMP_OFFLINE=1` (no network, no lookahead); Piotroski/Altman recomputed PIT from as-of statements.
- **Output:** `baseline_history.json` (chained EW + MOSw stats) and `baseline_picks.csv` (per-pick audit rows).
- **Run:** `python replay_baseline.py --start 2021-01 --end 2025-12` (smoke: `--smoke`).

### `backend/screener_v6.py` (MODIFIED)
- Fix A hysteresis scaling (`_hyst_boost`, `HYST_FRAC`, `_MOS_AMPLITUDE`).
- Supporting helpers the replay imports: `_sector_class`, `_methodology_applicable`, `_norm_industry`.
- `get_value(..., forward_eps_growth=0.0)` signature for replay parity.
- `structural_break_reason` field on `Stock`.
- *(Note: this file carried substantial prior in-progress work — the methodology selection plumbing — which is the substrate the whole system runs on. It was committed together because it is the foundation, not unrelated work.)*

### `backend/baseline_history.json` + `backend/baseline_picks.csv` (NEW, generated artifacts)
- Generated 2026-05-29T14:46:33Z. **Post-fix** (Fix A + G2b proxy both applied — verified via the `g2b_forward_decline` config string and `generated_at` timestamp).

---

## 4. Frontend deliverables (`frontend/app/page.tsx` + `frontend/public/baseline_history.json`)

- **`baseline_history.json` copied to `frontend/public/`** — static-JSON delivery, matches the existing `methodology_picks.json` pattern.
- **New fetch+mutate `useEffect`:** on mount, fetches `/baseline_history.json`, walks `METHODOLOGIES_CONFIG`, overrides each method's `metrics.baseline.{cagr,mdd,sharpe,trades}` + `annualReturns` with real PIT numbers. Path→key mapping handles `epv_greenwald → epv`. A `pitLoaded` counter forces re-render after mutation.
- **`trades` derivation:** `20 + round(avg_turnover × 20 × months)` — turnover-consistent estimate (verified to reproduce displayed values exactly).
- **Live-tracking widget re-anchored:** 4× callsites swapped from `metrics.director.cagr` (placeholder) → `metrics.baseline.cagr` (real PIT). Per user direction: the prior baseline was the wrong number to project from.
- **Disclosure footer:** intentionally NOT added (user opted out — internal reminder only, not user-facing).

---

## 5. Verification status

| Check | Result |
|---|---|
| AST parse — `screener_v6.py`, `replay_baseline.py` | ✅ OK |
| TypeScript — `tsc --noEmit -p .` | ✅ exit 0 |
| Dev server (`npm run dev`) | ✅ Ready, rendered |
| Card metrics match `baseline_history.json` | ✅ all 9 (dcf 25.7%, ey_gap 27.1%, ev_gp −1.3%, rd 18.7%, owner 16.7% …) |
| Year-by-year chart | ✅ 2022 now honest (+10.0% dcf, −4.97% ey_gap) — no placeholder negatives |
| `trades` formula reproduces displayed counts | ✅ exact |
| `epv_greenwald → epv` key mapping | ✅ epv card populated |

**Performance numbers now live (EW CAGR / MDD / Sharpe):**
- dcf_fcff: +25.7% / −14.2% / 1.05
- earnings_yield_gap: +27.1% / −16.4% / 1.00
- ev_gross_profit: **−1.3% / −43.9% / −0.12** (honest factor result — see §7)
- rd_capitalized_dcf: +18.7% / −21.3% / 0.73
- owner_earnings: +16.7% / −21.9% / 0.65
- epv: +14.7% / −30.3% / 0.59
- graham_revised: +16.8% / −25.2% / 0.66
- acquirers_multiple: +15.4% / −14.6% / 0.56
- iv15_deep_value: +14.8% / −25.2% / 0.59

---

## 6. NEXT UP — 2026 Active row auto-population (approved, verified correct-by-design)

The detail view's **"2026 Active (Currently Holding)" row shows +0.0%** right now. This is **not a wiring gap** — it auto-populates from the live screener. Trace verified:

**`screener_v6.py` writes (every run, during active tracking year):**
- `meth_track["current_holdings"] = new_holdings` (`:5528`)
- `meth_track["ytd_return"] = _compute_ytd_return(meth_track)` (`:5536`)
- mirror into `methodology_picks.json` (`:5974`)
- append fires when `tracking_year == current_year` (`:5966`); year-boundary rollover finalizes prior year into `baseline_history` + carries holdings forward (`:5963`, `_rollover_tracking_year`)

**`page.tsx` reads exactly those keys:**
- Active return → `trackingData.methodologies[shortKey].ytd_return` (`:2864`)
- Active holdings → `trackingData.methodologies[shortKey].current_holdings` (`:2908`)
- Prior-year rows → `trackingData.baseline_history[year][shortKey]` (`:2784`)

**Why +0.0% now:** the `methodology_tracking.json` currently in GCS/public was written when YTD was ~0. The next live `screener_v6` run recomputes current-vs-entry prices → writes a real `ytd_return` → frontend picks it up on next fetch. **No code change required** — confirm on next cron run.

---

## 7. Honest disclosures (the residuals are real, not artifacts)

1. **Universe survivorship:** offline cache = active universe as of mid-2026; delisted names absent → inflates absolute returns. **Validated negligible** for the methods with most financial exposure during the March-2023 bank crisis (they held insurers/broker-dealers/foreign banks/fintech — zero US regional commercial banks; SVB/Signature/First Republic cohort was never near selection).
2. **`ev_gross_profit` −1.3% is an honest factor result**, not a bug. Fix A reduced avg-hold 24.5→22.6mo (~8%) but USNA/NATR/RHI/KFRC stayed all 60 months — they're genuinely top-ranked on GP/TA every month (asset-light staffing/staples), not boost-stuck. Turnover floor is 2.8%/mo (structural). The GP/TA quality factor on this small-mid-cap cohort lagged growth/AI hard in 2021–2025 (esp. 2022: −36.6%). Honest, disclose, do not chase further.
3. **REIT eligibility** for `graham_revised` / `owner_earnings` is a **design choice** in `METHOD_SECTOR_APPLICABILITY` (NAV-anchored frameworks apply), not a classifier leak — the audit's "25 REIT leaks" flag assumes a strict no-REIT rule the config deliberately overrides.
4. **G2b replay = PIT proxy**, live = forward consensus. Replay marginally more permissive on cyclical-peak names (15.16% PEAK_CYCLE share bounds it).
5. **Small-cap tilt:** dcf_fcff / rd_capitalized_dcf / epv carry ~40% sub-$1B exposure → elevated liquidity risk.
6. **`iv15_deep_value` fill rate** 18.3 avg names (vs 20) — strict G3 no-growth gates, not a bug.

---

## 8. Side-effect to watch on first post-deploy live run

Fix A changes **production** selection. On the next live `screener_v6` run, rank-method baskets — especially `ev_gross_profit` — will churn as the previously locked-in incumbents re-justify under the scaled boost. **Expected behavior, the fix taking effect.** Watch `ev_gross_profit.current_holdings` in `methodology_tracking.json` (or the Active row) — should drop some 60-month incumbents and `ytd_return` should populate non-zero.

Also worth one separate live screener run so the next active basket for the three rank methods reflects de-stickied selection (same fix, live side).

---

## 9. Files in commit `a00c1965`

```
backend/baseline_history.json          (NEW, 325 lines)
backend/baseline_picks.csv             (NEW, 10,698 lines — audit artifact)
backend/replay_baseline.py             (NEW, 583 lines)
backend/screener_v6.py                 (MODIFIED, +449/−51)
frontend/app/page.tsx                  (MODIFIED, +120)
frontend/public/baseline_history.json  (NEW, 325 lines)
```

## 10. To regenerate the baseline (when backend logic changes)

```bash
cd backend
python replay_baseline.py --start 2021-01 --end 2025-12   # → baseline_history.json + baseline_picks.csv
python audit_baskets.py                                    # → bias diagnostics
cp baseline_history.json ../frontend/public/baseline_history.json
```
Then commit both `backend/baseline_history.json` and `frontend/public/baseline_history.json` together (keep them in sync).

---

## 11. POST-RUN ADDENDUM — 2026-05-30 (corrects §6 & §8)

After the first scheduled run, the live tracking did **not** populate. §6's claim that the Active row "just works on the next cron run" was wrong. Honest findings from GCS state + job config + run stderr:

- **The midnight scheduled run did not perform a real screen.** Execution `screener-sp500-zcg2p` ran **22:00:08→22:00:43Z (only ~35 s)**, status "succeeded", but its stderr shows it was in the **DebateEngine**, which logged `OpenAI health check failed` and then `Could not load methodology_picks.json — aborting`. A full SP500 scan takes far longer.
- **Prod GCS is partial/stale:** `scans/methodology_picks.json` fresh (manual run, 2026-05-30 12:22Z); `scans/methodology_tracking.json` still 2-byte `{}` (never populated); `scans/latest_sp500.json` **3 weeks stale (May 5)**; `hit_rate_tracking/` has only old-schema flat files + `test_cache*.json`, **no new four-method cycle dirs**.
- **Consequence:** the `/performance` Methods tab (P20 four-method, the parallel `74a086fe` work) is empty because the new-schema cycle state was never created. The `/` Active row is empty for the same upstream reason.
- **Job config is fine** (no DRY_RUN, no bucket override, `SCREEN_INDEX=sp500`) and the **code path is wired** (`screener_v6:5183` → `signal_tracker.update_from_scan` → per-regime `_record_new_predictions`, all error-logged). So the failure is upstream/runtime, not a missing wire.

**Intermediate diagnoses that were WRONG (retracted):** missing `decile_model_p20.pkl` (`_decile` is threshold-based, no model); `signal_tracker.py` corruption (file is clean, = HEAD); `capture_predictions` unwired (it is wired via `update_from_scan`).

**Open / next step:** the scheduled screener job is aborting in the DebateEngine stage and not completing a real scan (hence stale `latest_sp500.json` + empty tracking). This is upstream of both tracking surfaces and entangled with the parallel debate/P20 work + manual runs in flight. Needs the scan's real stdout to pin down precisely (only stderr was reachable here). **What's confirmed intact: the static PIT baseline (`baseline_history.json` → methodology cards) — that does not depend on the live scan.**
