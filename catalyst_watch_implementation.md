# Catalyst Watch — Full Production Report

## Table of Contents
1. [Backend Architecture](#1-backend-architecture)
2. [What to Expect After the Scan](#2-what-to-expect-after-the-scan)
3. [The Parallel Scanner Explained](#3-the-parallel-scanner-explained)
4. [Production Pipeline: Git → Cloud Run → Schedules](#4-production-pipeline)
5. [Current 404 Issue & Resolution](#5-current-404-issue)
6. [Action Plan: Future Improvements](#6-action-plan-future-improvements)

---

## 1. Backend Architecture

### Core Files (What's Deployed to Cloud Run)

| File | Purpose |
|---|---|
| [run_server.py](file:///c:/Users/Bruno/Stock-Screener/backend/run_server.py) | HTTP server entry point. Exposes all API routes on port 8080: `/transcript`, `/catalysts/candidates`, `/catalysts/scan`, `/health`, `/macro`, `/briefing`, `/performance/*`, `/portfolio/*`, `/stock/*`, `POST /scan` |
| [screener_v6.py](file:///c:/Users/Bruno/Stock-Screener/backend/screener_v6.py) | **The brain** — 5,249 lines, 235KB. 10-factor stock scoring engine with `compute_catalyst_score()` (line 2504), `compute_composite_v8()` (line 3880), `compute_smart_money_score()`, `get_symbols()`, `screen()`, and `save_scan_to_gcs()` |
| [opportunistic_catalysts.py](file:///c:/Users/Bruno/Stock-Screener/backend/opportunistic_catalysts.py) | **Catalyst Watch engine** — 694 lines. Implements `get_catalyst_candidates()` (reads GCS/local scan data, applies market cap filter, merges deep scan cache), `run_catalyst_scan()` (dispatches Claude LLM for Loeb/Bloom analysis), and `_save_deep_scan_to_cache()` (GCS + local persistence) |
| [massive_options.py](file:///c:/Users/Bruno/Stock-Screener/backend/massive_options.py) | **Options layer** — migrated from Polygon.io REST to local ThetaData SDK. Thread-safe `get_theta_client()`, EOD date resolution via AAPL probe, schema adapter converting ThetaData → Polygon-style dicts. Feeds ATM IV, skew, term structure, P/C ratios into the catalyst scan |
| [signal_tracker.py](file:///c:/Users/Bruno/Stock-Screener/backend/signal_tracker.py) | Signal performance tracking (BUY/SELL cycle tracking, P(+10%) hit rates), 60-day evaluation windows |
| [macro_regime.py](file:///c:/Users/Bruno/Stock-Screener/backend/macro_regime.py) | 9-signal macro composite (yield curve, VIX, CPI, GDP, unemployment, consumer sentiment, recession probability) |
| [monitor_prices.py](file:///c:/Users/Bruno/Stock-Screener/backend/monitor_prices.py) | Daily price refresh job (Mon-Fri), updates display prices in GCS |
| [run_universe_scan.py](file:///c:/Users/Bruno/Stock-Screener/backend/run_universe_scan.py) | **Batch parallel scanner** — runs `run_catalyst_scan()` for up to 400 candidates concurrently with ThreadPoolExecutor |
| [paper_strategy_runner_*.py](file:///c:/Users/Bruno/Stock-Screener/backend) | 4 paper trading strategy runners: Compounder US, Compounder Global, Momentum, Fallen Angel |
| [run_all_strategies.py](file:///c:/Users/Bruno/Stock-Screener/backend/run_all_strategies.py) | Orchestrator that runs all 4 paper strategies in sequence |
| [paper_weekly_email.py](file:///c:/Users/Bruno/Stock-Screener/backend/paper_weekly_email.py) | Weekly email report combining all strategy performance |
| [fmp_cache.py](file:///c:/Users/Bruno/Stock-Screener/backend/fmp_cache.py) | FMP API cache layer with offline mode support |

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                   screener_v6.py (screen())                      │
│   10-Factor Composite: macro + momentum + quality + value +      │
│   institutional + catalyst + smart_money + options + ...         │
│                         │                                        │
│                         ▼                                        │
│            save_scan_to_gcs() → GCS bucket                       │
│            scans/latest.json, scans/latest_global.json           │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│            opportunistic_catalysts.py                             │
│   get_catalyst_candidates() reads latest scan from GCS           │
│   → Filters: $300M+ market cap, 400 candidates max              │
│   → Merges deep_scans_cache.json for refined Loeb scores         │
│   → Unscanned: score × 0.6 (capped at 6.0)                     │
│   → Scanned:  real Claude score (1.0–10.0)                      │
│   → Sorts by Loeb Score descending                              │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│            run_catalyst_scan(symbol, force_refresh)               │
│   1. Collect: FMP profile, SEC filings, news, transcripts       │
│   2. Collect: ThetaData options (ATM IV, skew, term structure)  │
│   3. Build Claude prompt: Loeb/Bloom methodology                │
│   4. Claude → structured JSON analysis                          │
│   5. Cache to deep_scans_cache.json (local + GCS)               │
│   6. Return: catalyst_density_score, upside_downside_ratio,     │
│      bloom_catalysts, loeb_criteria, options_signals, events     │
└─────────────────────────────────────────────────────────────────┘
```

### Key Fixes Implemented in This Session

1. **ThetaData Migration** (`massive_options.py`): Retired Polygon.io REST API. Options data now fetched from local ThetaData terminal SDK with thread-safe initialization, 18 RPS rate limiter, and AAPL-probed EOD date resolution.

2. **Post-Event Timing Penalty** (`screener_v6.py` line 2715–2727): Detects completed M&A/buyout events in news titles (15 completed phrases like "closes merger", "acquisition completed"). Applies `-0.35` penalty on the 0.0–1.0 scale (= -3.5 on the 10-point display scale), preventing post-event stocks from ranking at the top.

3. **LLM Prompt Calibration** (`opportunistic_catalysts.py` line 414–417): Added methodological directives to the Claude prompt requiring distinction between fired vs. pending catalysts, capping Loeb scores for post-event setups at 5.0–6.8 range, and requiring real financial risk/reward ratios.

4. **Thread-Safe Cache** (`opportunistic_catalysts.py` line 11, 36, 59): Added `threading.RLock()` to prevent cache corruption during concurrent batch scanning.

5. **Heuristic Score Discount** (`opportunistic_catalysts.py` line 167): Unscanned candidates are capped at 60% of their raw score (max 6.0) to prevent unscanned "leads" from outranking genuinely scanned candidates.

---

## 2. What to Expect After the Scan

### After `run_universe_scan.py` completes:

1. **`deep_scans_cache.json`** (~880KB) will contain Claude LLM analysis for up to 400 symbols. Each entry has:
   - `catalyst_density_score` (1.0–10.0 Loeb Score)
   - `upside_downside_ratio` (e.g., 2.5 for 2.5:1)
   - `bloom_catalysts` (3 stages: Governance Reset, Strategic Process, Premium Scenario)
   - `loeb_criteria` (catalyst density, sum-of-parts, activism potential, risk/reward)
   - `options_signals` (IV, skew, term structure, P/C ratios)
   - `recent_events` (timeline of filings/news)

2. **GCS Sync**: The consolidated cache is uploaded to `gs://screener-signals-carbonbridge/scans/deep_scans_cache.json` after all scans complete (single write, not per-symbol).

3. **Frontend**: The `/catalysts` page will show all candidates sorted by Loeb Score. Scanned candidates show clean scores; unscanned show heuristic estimates with asterisks.

4. **Per-ticker view**: Clicking any ticker on the `/stock/[symbol]` page → "Catalyst Watch" tab loads the cached deep scan instantly (~50ms).

### Scan Cost Estimate

Each `run_catalyst_scan()` call sends ~6,000 tokens of context (profile + filings + news + transcripts + options) and receives ~4,000 tokens. Using Claude Sonnet 4:
- **Input**: ~6K tokens × $3/M = ~$0.018/symbol
- **Output**: ~4K tokens × $15/M = ~$0.06/symbol
- **Total per symbol**: ~$0.078
- **400 symbols**: ~$31.20

---

## 3. The Parallel Scanner Explained

### What is it?

[run_universe_scan.py](file:///c:/Users/Bruno/Stock-Screener/backend/run_universe_scan.py) is a **standalone batch script** (not a Cloud Run service or job). It:

1. Calls `get_catalyst_candidates()` to load up to 400 symbols from the latest GCS scan
2. Sets `BATCH_SCAN_MODE=1` to suppress per-symbol GCS writes (avoids 400 individual uploads)
3. Uses `ThreadPoolExecutor(max_workers=10)` to run 10 concurrent Claude API calls
4. Each worker calls `run_catalyst_scan(symbol, force_refresh=True)` which fetches FMP + ThetaData data and dispatches a Claude LLM analysis
5. After all workers finish, performs a **single consolidated GCS upload** of the full cache

### Why you don't see it in Cloud Run / GitHub Actions

**It is NOT deployed as a Cloud Run job or GitHub Action**. It exists only as a local Python script meant to be run from your machine:

```powershell
.venv\Scripts\python.exe backend/run_universe_scan.py --workers 10
```

The deploy.yml workflow does NOT include a `run_universe_scan` job definition. The reasons:

1. **ThetaData dependency**: The ThetaData terminal SDK requires a local running ThetaData Terminal application (desktop app). Cloud Run doesn't have this.
2. **Cost control**: Running 400 Claude API calls ($31) is a conscious decision, not something to auto-trigger on every deploy.
3. **Duration**: With 10 workers and 400 symbols, the scan takes ~40-60 minutes. Cloud Run job timeout is 3600s (1hr) which barely covers it.

### How to productionize it (future)

To make the scanner run automatically:
- Option A: **Cloud Scheduler → Cloud Run Job** (requires removing ThetaData dependency or running a ThetaData proxy service)
- Option B: **GitHub Actions scheduled workflow** (if running on a self-hosted runner with ThetaData Terminal)
- Option C: **Local cron job** on your Windows PC (simplest, current approach)

---

## 4. Production Pipeline

### Current Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        GitHub (main)                          │
│                            │                                  │
│   Push backend/**  ──────→ GitHub Actions deploy.yml          │
│                            │                                  │
│                     ┌──────┴──────────────────────────┐       │
│                     │  1. Build Docker image           │       │
│                     │  2. Deploy Cloud Run Service     │       │
│                     │     (stock-screener)             │       │
│                     │  3. Update/Deploy 10 Cloud       │       │
│                     │     Run Jobs                     │       │
│                     └─────────────────────────────────┘       │
│                                                              │
│   Push frontend/** ──────→ Vercel auto-deploy                │
│                            (Next.js 16 app)                  │
└──────────────────────────────────────────────────────────────┘
```

### Cloud Run Service

| Property | Value |
|---|---|
| Name | `stock-screener` |
| Region | `europe-west1` |
| Memory | 1Gi |
| Timeout | 3600s |
| Env Vars | `SCREEN_INDEX=nasdaq100`, `MASSIVE_API_KEY` |
| Image | Auto-built from `backend/Dockerfile` |

### Cloud Run Jobs (10 total)

| Job | Script | Schedule | Status |
|---|---|---|---|
| `screener-sp500` | screener_v6 scan | Fri 4:00 CET | **ENABLED** |
| `screener-global` | screener_v6 global scan | — | Manual |
| `compounder-us-runner` | paper_strategy_runner_compounder_us.py | — | Manual |
| `compounder-global-runner` | paper_strategy_runner_compounder_global.py | — | Manual |
| `momentum-runner` | paper_strategy_runner_momentum.py | — | Manual |
| `fa-runner` | paper_strategy_runner_fa.py | — | Manual |
| `paper-all-runner` | run_all_strategies.py (orchestrator) | Sat 6:30 CET | **ENABLED** |
| `monitor-prices` | monitor_prices.py | Mon-Fri 18:00 CET | **ENABLED** |
| `paper-email` | paper_weekly_email.py | — | Manual |
| `backtest-sp500` / `backtest-v8` | backtest_full.py / backtest_v8.py | — | Manual |

### Cloud Scheduler (5 jobs)

| Job | Schedule | Status |
|---|---|---|
| `paper-all-friday` | Sat 6:30 CET | **ENABLED** |
| `monitor-prices-daily` | Mon-Fri 18:00 CET | **ENABLED** |
| `screener-us-daily` | Fri 4:00 CET | **ENABLED** |
| `weekly-report` | Mon 6:00 CET | **PAUSED** |
| `screener-monitor` | Mon-Fri 13:00 CET | **PAUSED** |

### Secrets (GitHub Actions)

- `GCP_SA_KEY` — GCP service account JSON
- `MASSIVE_API_KEY` — ThetaData/options API key
- `FMP_API_KEY` — Financial Modeling Prep API key
- `SMTP_USER` / `SMTP_PASS` / `EMAIL_TO` — Email delivery

---

## 5. Current 404 Issue

### Diagnosis

The app is returning 404 because the **frontend (Vercel)** proxies API calls to the **backend (Cloud Run)** via Next.js API routes in `frontend/app/api/`. These API routes hardcode `http://127.0.0.1:8080` as the backend URL:

```typescript
// frontend/app/api/catalysts/candidates/route.ts
const res = await fetch("http://127.0.0.1:8080/catalysts/candidates", {
  cache: "no-store",
});
```

This works **locally** (when you run `python run_server.py` on port 8080), but on **Vercel** in production, the API routes proxy to `127.0.0.1:8080` which doesn't exist — the Cloud Run service runs at `https://stock-screener-XXXXX-ew.a.run.app`.

### Root Cause

The 2 unpushed commits (`b06512f` and `86ef620`) haven't been pushed to `main` yet. The production deployment is running an older version of the backend code. Additionally, if the Vercel deployment is also stale, the frontend API routes may be pointing to `127.0.0.1` instead of the Cloud Run service URL.

### Resolution

1. **Push the 2 unpushed commits** to trigger a Cloud Run redeploy
2. **Verify frontend API routes** use the correct backend URL for production (should use env var like `NEXT_PUBLIC_API_URL` or server-side `API_URL`)

---

## 6. Action Plan: Future Improvements

### Immediate (This Week)

- [ ] **Push & deploy**: Commit catalyst watch + parallel scanner + post-event penalty changes to `main`, triggering Cloud Run redeploy
- [ ] **Add `ANTHROPIC_API_KEY` to Cloud Run env vars** (currently only local)
- [ ] **Add `catalyst-universe-scan` Cloud Run Job**: Create a dedicated job in deploy.yml for the batch scanner (requires removing ThetaData SDK dependency from the scan path, or making it optional)
- [ ] **Fix frontend API proxy URLs**: Ensure API routes use `process.env.BACKEND_URL` instead of hardcoded `127.0.0.1:8080`

### Short-Term (2 Weeks)

- [ ] **Monthly Auto-Rescan Scheduler**: Add a Cloud Scheduler job that triggers `run_universe_scan` monthly (1st Saturday of each month) to refresh the entire Loeb score universe
- [ ] **Scan Freshness Indicator**: Show last-scanned timestamp on each candidate card with color coding (green: <7d, yellow: 7-30d, red: >30d)
- [ ] **Batch Scan Progress API**: Add `/catalysts/scan-status` endpoint to show live progress (X/400 scanned, estimated time remaining)
- [ ] **Catalyst Watch Filters**: Add filter controls on `/catalysts` page: by category (M&A, Governance, Spinoff, Options), by scan status, by score range

### Medium-Term (1 Month)

- [ ] **Bloom Timeline Visualization**: Interactive D3 timeline showing when each of the 3 Bloom catalysts were detected, with future event markers
- [ ] **Options Term Structure Chart**: Render IV term structure (near vs. far expiry) as a mini chart on the catalyst detail view
- [ ] **Alert System**: Push notifications (email or webhook) when a candidate's Loeb score crosses thresholds (e.g., jumps from WATCH to BUY after a new catalyst fires)
- [ ] **Comparative R/R Table**: Side-by-side comparison view of top 10 candidates showing Loeb Score, R/R ratio, Bloom stage, and options signals
- [ ] **Portfolio Integration**: "Add to Portfolio" button from catalyst detail that pre-fills the position with the R/R ratio as the target

### Long-Term (3 Months)

- [ ] **Historical Loeb Score Tracking**: Store score snapshots over time to show score trajectory (rising = accumulating catalysts, falling = catalysts firing)
- [ ] **Backtest the Methodology**: Paper trade a "Top 10 Loeb Score" portfolio monthly and measure alpha vs S&P 500
- [ ] **Multi-Model Consensus**: Run parallel LLM scans (Claude + Gemini + GPT-4) and average the scores for more robust ratings
- [ ] **Sector Heat Map**: Visual heat map of catalyst density by GICS sector, highlighting where event-driven opportunities cluster
