# Handoff — Options IVR + Touch-EV Leg Selection (2026-06-02)

## TL;DR
`screener_v6.py` was **not modified**. But two backend modules it calls during the
scan changed, and one needs a **manual one-time bootstrap** before IVR shows up:

1. `massive_options.py` — now computes real **IV Rank** (`options_iv_rank`) from a
   52-week GCS IV history, replacing the hardcoded `None`.
2. `signal_tracker.py` — the **long-call leg** is now chosen as the *cheapest strike
   still profitable when sold at the barrier touch* (was: a near-barrier strike that
   structurally lost). "EV" = net touch P&L.
3. `bootstrap_iv_history.py` — **new** one-off script to seed the IV history from the
   local thetadata parquet cache so IVR is populated immediately.

Frontend (Vercel) changes ship automatically on push. Backend (Cloud Run) ships on
push via Cloud Build, **but IVR stays blank until you run the bootstrap** (below).

---

## What changed and why

### 1. IVR from thetadata  (`massive_options.py`)
- **Before:** `result["iv_rank"] = None; result["iv_samples"] = 0` was hardcoded
  (the IV-rank-from-history logic was never ported from `tradier_options.py`). ATM IV
  (`options_iv_current`) was extracted fine; only the *rank* was missing.
- **After:** ported `update_iv_history()` + `compute_iv_rank()` (same proven logic as
  `tradier_options.py`). On each scan it appends today's ATM IV to
  `gs://screener-signals-carbonbridge/options/iv_history/{SYMBOL}.json` and ranks the
  current IV within the retained window. **Zero extra API calls** — reuses the ATM IV
  already fetched.
- `IV_HISTORY_KEEP_DAYS` changed `90 → 365` (52-week IV-rank window).
- IVR returns `None` until **≥ 20 samples** exist for a symbol. With daily-only
  appends that's ~4 weeks; the bootstrap removes that wait.

### 2. Cheapest-profitable-at-touch call legs  (`signal_tracker.py`)
- **Problem you flagged:** legs were struck *at the barrier* (e.g. spot $50.86, +10%
  barrier $55.95 → strike $55, premium $1.40). At the touch the call is only $0.95 ITM,
  so selling at touch is a guaranteed loss (you paid mostly time value).
- **Fix:** `_pick_best_long_leg()` now selects the **highest strike whose net touch
  P&L `(barrier − strike − ask)` is ≥ 0** — i.e. the cheapest leg (most leverage) that
  still profits when the touch happens. Falls back to the least-bad leg if none clear
  zero. Verified: the AD example now picks strike **$54** (EV +$5) instead of $55 (−$45).
- `_model_fair_value_long_call()` redefined: now the **gross value at the touch**
  `max(0, barrier − strike) × 100` (dropped the `p_barrier` weighting). `edge_dollars`
  is therefore the **net touch P&L**, and `edge_pct` the **touch ROI**.

### Frontend (auto-deploys on push)
- `/signals` ("ML Picks") — data-quality-gated ML leaderboard; **IV + IVR columns**
  (IVR shows `—` until the bootstrap+scan populate it).
- `/performance` → Methods — per-pick table collapses to one row/symbol (expand for the
  4 method lines), sortable columns, **EV cell** on call rows (= net touch P&L), and
  **live Last $** polled every 60s while the tab is open.

---

## DEPLOY (in order)

### Step 1 — push (frontend + backend auto-deploy)
Done as part of this commit. Vercel rebuilds the frontend; Cloud Build rebuilds the
`stock-screener` image and redeploys the scan job.

### Step 2 — seed the IV history (MANUAL, run locally, one time)
The thetadata parquet cache is local-only (`.gcloudignore`'d), and the bootstrap writes
to GCS, so run it on your machine with application-default credentials:
```powershell
gcloud auth application-default login          # once
cd backend
python bootstrap_iv_history.py --limit 20 --dry-run   # sanity check (no writes)
python bootstrap_iv_history.py                        # seed all ~2,874 symbols → GCS
```
It reads `Cache_Data/Theta_Historical/{SYMBOL}_theta.parquet`, takes the ATM-IV (delta
closest to 0.50, `iv_error < 0.1`) per date, keeps the last 365 days, and writes
`options/iv_history/{SYMBOL}.json`. Idempotent — safe to re-run.

### Step 3 — wait for the next nightly scan
The scan then computes IVR against the seeded history and records new picks with the
touch-EV leg logic.

---

## VERIFY (after Step 3)
- `gs://.../scans/latest_global.json` → `options_iv_rank` is non-null for US names.
- `/signals` IVR column populates (0–100).
- New picks in `/performance` → Methods: call legs sit at a **lower strike** with a
  **positive EV** (green), vs the old near-barrier −EV legs.
- `signal_tracker` reprice paths already read `options_iv_rank` → `ivr_at_entry`
  (`signal_tracker.py:1811, 2268`), so the per-pick IVR column fills too.

---

## CAVEATS
- **`screener_v6.py` unchanged** — no scan-orchestration changes.
- **Leg fix is forward-only.** The ~1,176 already-tracked picks keep the strikes they
  were opened with; only new cycles use the touch-EV leg. Old + new methodology coexist
  until old picks resolve.
- **EV column shows old values until a rescan** — existing `edge_dollars_at_entry` was
  computed under the old `p_barrier × intrinsic` model.
- **IVR is `None` until the bootstrap runs** (or ~20 daily scans accrue).
- **Live-poll cost:** `/performance` Methods polls ~595 underlyings/min via FMP
  (cache-busted) while open. Scope it down if quota matters.

## ROLLBACK
All changes are additive and revert cleanly:
- `git revert <backend commit>` restores the `iv_rank = None` stub and the old
  edge-maximizing leg selection. No data migration needed (IV history JSONs are inert
  if unused). `bootstrap_iv_history.py` is standalone (not called by the scan).

## KEY CODE POINTERS
- `backend/massive_options.py` — `update_iv_history` / `compute_iv_rank` (after the GCS
  helpers); wiring in `enrich_stock` where `iv_today` is computed; `IV_HISTORY_KEEP_DAYS`.
- `backend/signal_tracker.py:1418` `_model_fair_value_long_call`; `:1423`
  `_pick_best_long_leg` (the objective).
- `backend/bootstrap_iv_history.py` — the seeding script.
