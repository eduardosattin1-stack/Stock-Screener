# Catalyst Watch — Full Production & Feature Implementation Report

## Table of Contents
1. [Backend Architecture](#1-backend-architecture)
2. [What to Expect After the Scan](#2-what-to-expect-after-the-scan)
3. [The Parallel Scanner & Progress Tracking](#3-the-parallel-scanner--progress-tracking)
4. [Interactive Spread Calculator & Options Hedging Suggestions](#4-interactive-spread-calculator--options-hedging-suggestions)
5. [Timing Distinction & Merger Arb Filters](#5-timing-distinction--merger-arb-filters)
6. [Production Pipeline: Git → Cloud Run → Schedules](#6-production-pipeline)

---

## 1. Backend Architecture

### Core Files (What's Deployed to Cloud Run)

| File | Purpose |
|---|---|
| [run_server.py](file:///c:/Users/Bruno/Stock-Screener/backend/run_server.py) | HTTP server entry point. Exposes all API routes on port 8080, now including the new `/api/catalysts/progress` endpoint. |
| [screener_v6.py](file:///c:/Users/Bruno/Stock-Screener/backend/screener_v6.py) | **The brain** — 10-factor stock scoring engine with `compute_catalyst_score()`, `compute_composite_v8()`, and `save_scan_to_gcs()`. |
| [opportunistic_catalysts.py](file:///c:/Users/Bruno/Stock-Screener/backend/opportunistic_catalysts.py) | **Catalyst Watch engine** — Implements candidate fetching, merges deep scan cache, dispatches Claude LLM scans with refined Loeb/Bloom timing logic, and computes hedging suggestions. |
| [massive_options.py](file:///c:/Users/Bruno/Stock-Screener/backend/massive_options.py) | **Options layer** — Integrates directly with the local ThetaData terminal SDK to extract ATM IV, skew, term structure, and open interest. |
| [run_universe_scan.py](file:///c:/Users/Bruno/Stock-Screener/backend/run_universe_scan.py) | **Batch parallel scanner** — runs `run_catalyst_scan()` for candidates concurrently with ThreadPoolExecutor and updates real-time scan progress. |

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
│   → Adds is_merger_arb flag for immediate sidebar filter toggle  │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│            run_catalyst_scan(symbol, force_refresh)               │
│   1. Collect: FMP profile, SEC filings, news, transcripts       │
│   2. Collect: ThetaData options (ATM IV, skew, term structure)  │
│   3. Claude → timing nature, re-rate status, loeb score, R/R     │
│   4. Generate dynamic hedging option spreads suggestions        │
│   5. Cache to deep_scans_cache.json (local + GCS)               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. What to Expect After the Scan

### After `run_universe_scan.py` completes:

1. **`deep_scans_cache.json`** will contain updated Claude LLM analysis for up to 400 symbols. Each entry has:
   - `catalyst_density_score` (1.0–10.0 Loeb Score)
   - `upside_downside_ratio` (e.g., 2.8 for 2.8:1)
   - `re_rate_status` ("pending" | "partial" | "complete")
   - `catalyst_nature` ("pricing_dislocation" | "mechanical_execution")
   - `catalyst_nature_rationale` (detailed trade timing insight)
   - `bloom_catalysts` (3 stages)
   - `options_signals` (IV, skew, term structure, P/C ratios)
   - `merger_arb_data` (cash component, stock component ratio, acquirer price, expected close, and hedging suggestions)
   - `recent_events` (timeline of filings/news)

2. **GCS Sync**: The consolidated cache is uploaded to `gs://screener-signals-carbonbridge/scans/deep_scans_cache.json` after all scans complete (single consolidated write).

3. **Frontend**: The `/catalysts` page will show all candidates sorted by Loeb Score. Tickers will render with badges indicating if they are M&A merger arbs, and display alpha-bearing pricing dislocation or mechanical execution statuses.

---

## 3. The Parallel Scanner & Progress Tracking

[run_universe_scan.py](file:///c:/Users/Bruno/Stock-Screener/backend/run_universe_scan.py) has been upgraded to track and report its progress:

1. **Local and Remote State**: The scanner updates progress variables inside a thread-safe `progress_lock` block and outputs them to `backend/scan_progress.json`.
2. **Rate-Limited GCS Sync**: Updates are synced to the GCS bucket at `scans/scan_progress.json` with a rate limiter (at most once every 5 seconds, or always on start/completion) to avoid hitting GCS write rate limits.
3. **Exposed Endpoint**: The server (`run_server.py`) exposes `/api/catalysts/progress` which reads the GCS progress state.
4. **Dashboard Progress Indicator**: The frontend `/catalysts` dashboard polls `/api/catalysts/progress` every 3 seconds during active scans, rendering a glassmorphic progress bar displaying:
   - Current symbol being scanned.
   - Scan percentage and ratio (e.g. `214/400`).
   - Live scanning speed stats (e.g. `1.43 symbols/sec`).
   - Remaining time estimation (ETA).

---

## 4. Interactive Spread Calculator & Options Hedging Suggestions

To handle announced buyout transactions and calculate correct risk/reward arbitrage parameters:

1. **Interactive Acquirer Price Input**: Users can input a custom acquirer price on the Merger Arb card (when target receives stock components) on both the `/catalysts` dashboard and `/stock/[symbol]` details page.
2. **Real-Time Spread Math**: The card recalculates the following parameters client-side:
   - `Implied Deal Value = Cash Component + (Stock Component Ratio * Custom Acquirer Price)`
   - `Gross Spread = Implied Deal Value - Target Price`
   - `Spread % = (Gross Spread / Target Price) * 100`
   - `Downside if Deal Breaks = Target Price - Pre-Announce Reference Price`
   - `Unhedged R/R Asymmetry = -(Downside / Gross Spread) : 1`
3. **Hedged Option Builder Suggestions**: Suggests option structures to hedge deal-break risk:
   - **Target Stock**: Bear Put Spread (ATM long put / pre-announce short put) and Covered Call (buy target stock and sell call at deal value strike).
   - **Acquirer Stock** (if stock merger): Bear Call Spread (short protection via OTM calls) and Bear Put Spread (synthetic short component without stock borrow cost).
   - Strikes and legs are dynamically computed and rounded (steps of $2.50 or $5.00) based on target price and acquirer prices.

---

## 5. Timing Distinction & Merger Arb Filters

1. **Catalyst Nature Distinction**:
   - Claude classifies catalysts as `"pricing_dislocation"` (the alpha-bearing dislocation window when the market misprices the setup) or `"mechanical_execution"` (the mechanical completion or execution date of an event, which are often days or weeks apart).
   - Displays as visual green/blue glow badges on the dashboard card, followed by the rationale.
2. **Re-rate Status Check**:
   - Tracks if the price re-rate has already happened (`"pending"` | `"partial"` | `"complete"`), highlighting if the alpha has already been priced in.
3. **Merger Arb Watchlist Toggle**:
   - Added a `Show Merger Arbs` binary switch to the left sidebar filters.
   - Allows users to instantly isolate announced transactions or exclude them from the main watchlist candidates.

---

## 6. Production Pipeline

### Deploy Workflow

When changes are pushed to GitHub `main` branch:
1. **Cloud Run Redeploy**: The backend Docker container is auto-built and deployed to Cloud Run (`stock-screener` on `europe-west1`), updating the server and scheduling jobs.
2. **Vercel Frontend Redeploy**: Next.js 16 app compiles, runs TypeScript verification checks, and is deployed to production.
