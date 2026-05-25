# Comprehensive Walkthrough: Multi-Agent Optimization, Cache Integration & Scenario C Backtest

This walkthrough documents the full progression of the Stock Screener project, including:
1. **Multi-Agent Alpha Platform Optimization** (S&P 500 5-Iteration Loop)
2. **FMP Offline Cache Integration** (Offline mode migration and performance optimization)
3. **Scenario C: 1-Year PIT LLM Debate & Portfolio Director Backtest Results** (Ranks 1-3 and 7-9 deep-dives, outlier diagnostics, and bullet-proofing)
4. **Scenario C Upgraded: 4-Agent Barbell Debate & Apex PM Basket Allocator** (Barbell architecture, Expectations Arbitrage CRO, and single-run PM Allocator)
5. **UI Fixes, Column Sorting, Ticker Search, and Weekend EOD Greeks Repricing**

---

## 1. Multi-Agent Alpha Platform Optimization

We successfully implemented,
- **Duplicate Navigation Fix**: Removed the duplicate `Nav` component import and render block in `frontend/app/catalysts/page.tsx` since Next.js `RootLayout` already renders the navigation bar globally across all routes.

### 4. Unified Scoring Scale & Sidebar Duplication Fixes
- **Unified Score Range (0.0 to 10.0)**: Scaled candidate catalyst scores returned by the `/catalysts/candidates` backend by `10.0` to match the `1.0` to `10.0` cognitive scan range. This ensures consistency across candidate lists, watchlists, recent scans, and deep scans (e.g., ZS shows up as `10.00` candidate / `7.80` deep scan instead of `1.00` candidate / `7.80` deep scan).
- **Double Fetch Loop & Duplicates Fixed**: Solved the Next.js `useEffect` dependency loop by storing the scan cache in a React `useRef` rather than state. Because updating state cache triggered re-renders and re-runs of the deep scan `useEffect` before state updates were completed, it caused duplicate entries (e.g., two ZS cards) in the recent scans sidebar due to race conditions.
- **Exquisite Card UI Updates**: Each candidate sidebar card now clearly displays both key metrics at a glance: the **Loeb Score** (e.g. `Loeb: 10.0`) and the **Asymmetry** (e.g. `R/R: 2.3:1` or `Upside: +67%`).
- **Concurrent Score Propagation**: Implemented `propagateScoreUpdate` which ensures that once a force-refresh completes, the updated score is concurrently synchronized across the Candidates list, Watchlist (state & `localStorage`), and Recent Scans.

### 6. Heuristic Score Calibration & Rank Correction (Latest Update)
- **Heuristic Score Discount (Capped at 6.0)**: Capped raw, unscanned heuristic catalyst scores at a maximum of `6.0` (applying a `0.6` discount factor) in `get_catalyst_candidates`. This prevents unscanned "leads" from polluting the top ranks and crowding out genuine scanned candidates (like AVGO `9.1`, GILD `9.2`, or CVS `7.8`).
- **`is_scanned` State Synchronization**: Added an `is_scanned` boolean flag to both backend responses and the frontend `Candidate` type.
- **Visual Indicators & Tooltips**:
  - Unscanned heuristic scores are decorated with an asterisk (`Loeb: 6.0*`) and carry a `"Heuristic Estimate (Unscanned)"` tooltip.
  - Deep-scanned scores display as clean values (`Loeb: 7.8`) and carry a `"Loeb Score (Deep Scanned)"` tooltip.
- **Instant Promotion on Scan**: Propagating the scan result updates the Candidate's score to its true Claude-synthesized value and flips `is_scanned` to `true`, instantly moving the stock to its correct sorted rank in the list.

### 4. Pipeline Sidebar Logic
- The Candidates list filters out any items that are already in the Watchlist or Recent Scans.
- Recent Scans list filters out any items that are currently in the Watchlist.
- This ensures a ticker moves cleanly down the pipeline (`Scanning Candidates` -> `Recent Scans` -> `Watchlist`) without duplicating.

### 4. Persistent Scan Caching & Stock Page Integration
- **Persistent Local Scan Cache**: Implemented a local JSON cache (`backend/deep_scans_cache.json`) on the backend. Deep scans (e.g., Claude analysis) are cached for 24 hours. When candidates are loaded, if any has a cached deep scan, its candidate score is dynamically overridden with its refined deep-scanned score (e.g. Agilent Technologies `A` showing `6.8` instead of `10.0`), resolving the score mismatch between candidate lists and scan results.
- **Stock Detail Page Integration**: Added a new **"Catalyst Watch"** tab to the dynamic stock detail page (`/stock/[symbol]`). This tab fetches the deep scan report (which loads instantly in ~50ms if cached, or runs on-demand if not) and renders the exact same beautiful event-driven dashboard (Bloom timeline, Loeb criteria, options Term structure, and evidence feed) inline.

iple universes, dynamically tuning parameters to find top-performing methodologies while mitigating risks.

### Key Accomplishments
* **Dynamic Universe Configurations**: The data steward ([pita_data_steward.py](file:///C:/Users/Bruno/Stock-Screener/backend/backtest_v9/pita_data_steward.py)) reconstructs multiple universes per rebalance date: `sp500`, `midcap`, `blend`, and `all`.
* **Options Decoupling**: If options data is present, the steward checks for valid options scans within a 10-day lookback window. Backtests can now run in **stock-only mode** (utilizing the full stock universe) or **options-inclusive mode** (utilizing the intersection) to prevent data gaps from limiting the stock universe size.
* **Multi-Agent Orchestrator Loop**: We updated [run_multi_agent_pipeline.py](file:///C:/Users/Bruno/Stock-Screener/backend/backtest_v9/run_multi_agent_pipeline.py) to run exactly 5 iterations. In each iteration, the pipeline runs valuation/ranking ML models, performs red-team validation, calculates 3-factor exposure loadings, analyzes performance across macro regimes (BULL, BEAR, SIDEWAYS), and synthesizes recommendations.
* **Asymmetric Veto Softening**: Strategies failing stress tests in [val_validator.py](file:///C:/Users/Bruno/Stock-Screener/backend/backtest_v9/val_validator.py) are no longer vetoed (`NOT_DEPLOYED`). Instead, they are flagged as `POTENTIAL_USE_CASE` (e.g., regime protection) with specific parameter tuning recommendations.

---

## 2. FMP Offline Cache Integration & Performance Optimization

We completed the migration of the Alpha Compounder pipeline to a fully offline configuration using the local FMP cache and universe manifest. Additionally, we optimized the primary CPU bottleneck in Agent A's discovery process to run the offline search in minutes rather than hours.

### Key Accomplishments
* **Central Cache Layer (`fmp_cache.py`):** Added a global flag check for `FMP_OFFLINE=1` which bypasses GCS read/write operations and skips live fetching when a requested endpoint isn't found in cache, enforcing strict offline execution.
* **Live API Safeguard (`screener_v6.py`):** Modified the low-level `fmp()` fetcher to immediately return `None` when `FMP_OFFLINE` is enabled, preventing any outbound network calls.
* **Universe Loading & Date Filtering (`discovery.py`):** Rewrote `build_universe()` to seed from `expanded_universe_manifest.json` and automatically filter by the presence of EOD prices in the local cache. Added robust historical price filtering within targeted window ranges to avoid look-ahead bias.
* **Greedy Scan Refactoring (`utils.py`):** Refactored `greedy_trough_peak_pairs()` to resolve the $O(N^2)$ CPU bottleneck by introducing a sliding window (`j_max`), moving validation checks inside peak update conditionals, and delaying costly string parsing.
  * **Results:** Reduced the time of 10 mock iterations on a 1700-day series from **43.3s to 4.5s (9.5x speedup)** with 100% identical outputs.

---

## 3. Scenario C: 1-Year PIT LLM Debate & Portfolio Director Backtest Results (4-Methodology Re-run)

We executed the 1-year Point-in-Time (PIT) LLM Debate and Portfolio Director backtest (**2025-03-31 to 2026-03-30**, 13 monthly rebalances) for the 4 target methodologies:
1. **Earnings Yield Gap** (`emerging/earnings_yield_gap`)
2. **Owner Earnings** (`intrinsic/owner_earnings`)
3. **Graham Revised** (`v8fusion/graham_revised`)
4. **DCF-FCFF** (`intrinsic/dcf_fcff`)

This run incorporates the new **No-Transcript LLM Bypass** logic:
* Stocks without PIT earnings transcripts are automatically penalized with a strict conviction score of `2.0` (Sell/Penalty) directly in Python code.
* They bypass the LLM debate and Director evaluations completely, saving significant API token usage.
* If a rebalance date has no candidates with transcripts, the LLM call is skipped entirely.

---

### 3.1. Performance Summary (Baseline vs. Debate vs. Director)

The performance of each methodology under the three comparison modes—Baseline (pure quant rankings), Debate-Filtered (debate conviction $\ge 3.0$), and Director-Filtered (Director conviction $\ge 3.0$)—is detailed below:

| Methodology | Mode | CAGR | Max Drawdown | Sharpe Ratio | Total Trades |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **1. emerging/earnings_yield_gap** | Baseline | 21.95% | -4.00% | 1.96 | 28 |
| | Debate | **24.28%** | **-2.88%** | **2.26** | **43** |
| | **Director** | **24.50%** | **-2.88%** | **2.25** | **49** |
| **2. intrinsic/owner_earnings** | Baseline | 21.78% | -2.78% | 1.99 | 34 |
| | Debate | 18.20% | -3.64% | 1.59 | 43 |
| | **Director** | **18.74%** | **-3.64%** | **1.71** | **48** |
| **3. v8fusion/graham_revised** | Baseline | 13.74% | -4.93% | 1.15 | 28 |
| | Debate | 14.10% | -4.35% | 1.24 | 42 |
| | **Director** | **13.53%** | **-3.84%** | **1.28** | **50** |
| **4. intrinsic/dcf_fcff** | Baseline | 3.52% | -7.27% | 0.35 | 19 |
| | Debate | **5.65%** | **-7.36%** | **0.55** | **34** |
| | **Director** | **5.06%** | **-7.33%** | **0.50** | **35** |

> [!NOTE]
> Under the strict conviction filtering (conviction $\ge 3.0$), the portfolio size is kept at `top_n = 15`. When top-ranked stocks without transcripts are penalized with a conviction of `2.0`, they are filtered out, prompting the engine to select lower-ranked candidates that have transcripts. This shifts the portfolio composition and generally leads to more trades, reflecting a higher turnover but ensuring that every held asset has passed qualitative earnings review.

---

### 3.2. Detailed Analysis of the 4 Methodologies

#### **1. Earnings Yield Gap (`emerging/earnings_yield_gap`)**
* **The Winner**: The debate and director filters significantly boosted CAGR from **21.95%** to **24.50%** and reduced Max Drawdown from **-4.00%** to **-2.88%**, resulting in a superior Sharpe ratio of **2.25**.
* **Rationale**: The Earnings Yield Gap methodology identifies companies where the yield on earnings exceeds the risk-free rate by a wide margin. Filtering by qualitative transcripts ensured that high-yield candidates were not "value traps" with deteriorating business structures, yielding clean compounding wins.

#### **2. Owner Earnings (`intrinsic/owner_earnings`)**
* **The Challenge**: The debate and director filters resulted in lower CAGR (**18.74%**) and higher drawdown (**-3.64%**) compared to the baseline (**21.78%** CAGR, **-2.78%** DD).
* **Rationale**: Owner Earnings targets companies with strong cash flow relative to maintenance Capex. The strict transcript penalty removed some high-quality firms that lacked transcripts in the cache, forcing the portfolio to pick lower-ranked, less optimal alternatives. This highlights a potential area where expanding transcript database coverage would immediately recover performance.

#### **3. Graham Revised (`v8fusion/graham_revised`)**
* **The Optimizer**: While CAGR remained flat (~13.5%), the Director-Filtered mode successfully reduced Max Drawdown from **-4.93%** to **-3.84%**, boosting the Sharpe ratio from **1.15** to **1.28**.
* **Rationale**: The director pruned tail-risk candidates that had structural headwinds (e.g. leverage issues), stabilizing the equity curve.

#### **4. DCF-FCFF (`intrinsic/dcf_fcff`)**
* **The Compounder**: The baseline DCF performed poorly (**3.52%** CAGR), but the Debate-Filtered mode improved CAGR to **5.65%** and the Director-Filtered mode achieved **5.06%** CAGR with improved Sharpe ratio (**0.50** vs **0.35**).
* **Rationale**: Qualitative assessment filtered out value traps that standard DCF metrics (heavy on interest-rate assumptions) mispriced, raising the floor of this lagging strategy.

---

### 3.3. Transcript Coverage Analysis

Our analytical run on transcript database availability across all candidate stocks showed:
* **Total candidate (symbol, date) pairs evaluated**: 1,358
* **Pairs WITH transcript**: 1,200 (**88.4%**)
* **Pairs WITHOUT transcript**: 158 (**11.6%**)
* **Unique transcript files found**: 467
* **Symbols with ZERO transcripts**: 4 (`L`, `MPWR`, `NVR`, `VST`)

The **11.6% missing rate** highlights that while coverage is high (almost 90%), certain stocks like `NVR` consistently lack transcripts in the cache (13 dates missing). These are immediately penalized with a `2.0` conviction score.

---

### 3.4. Multi-Agent Debate & Director API Cost Analysis

We simulated the API costs for running the full screener (evaluating all 165 unique candidates) across different rebalance frequencies.

#### **Cost Assumptions (Per-Stock)**
1. **Debate Bear Agent (Gemini Flash)**:
   * Input: 12,000 tokens × $0.15/1M = $0.0018
   * Output: 158 tokens × $0.60/1M = $0.0001
   * **Total: $0.0019**
2. **Debate Bull Agent (GPT-4o)**:
   * Input: 12,000 tokens × $2.50/1M = $0.0300
   * Output: 158 tokens × $10.00/1M = $0.0016
   * **Total: $0.0316**
3. **Portfolio Director (Claude Opus 4.7)**:
   * Input: 2,000 tokens × $15.00/1M = $0.0300
   * Output: 100 tokens × $75.00/1M = $0.0075
   * **Total: $0.0375**

* **Total Cost Per Stock**: **$0.0710**

#### **Screener Cost Projections**
* **First Run** (All 165 candidate stocks require fresh debate + director): **$11.71**
* **Cached Run** (Only new quarterly transcripts require evaluation, ~25% of candidates or 41 stocks): **$2.91**

| Frequency | Runs / Year | Monthly Cost | Annual Cost (Claude Opus 4.7) | Annual Cost (Claude Sonnet 4)* |
| :--- | :---: | :---: | :---: | :---: |
| **Daily** | 365 | $89.24 | $1,070.94 | $618.27 |
| **Weekly** | 52 | $13.34 | $160.12 | $92.44 |
| **Bi-weekly** | 26 | $7.04 | $84.46 | $48.76 |
| **Monthly** | 12 | $3.64 | $43.72 | $25.24 |
| **Quarterly** | 4 | $1.70 | $20.44 | $11.80 |

*\* Claude Sonnet 4 pricing: $3.00/1M input, $15.00/1M output, reducing Director costs by ~60%.*

> [!TIP]
> By caching historical debate results and only running evaluations when a **new transcript is published**, running the screener every day is extremely cost-effective. Daily scans cost just **$89.24/month** even when using Claude Opus 4.7, and drop to **$51.52/month** when using Claude Sonnet 4, as the vast majority of runs reuse cached convictions.

---

## 4. Scenario C Upgraded: 4-Agent Barbell Debate & Apex PM Basket Allocator (2026-05-23 Upgrades)

We upgraded the Multi-Agent Debate and Director pipeline to the new **4-Agent Barbell Architecture** and **Apex PM & Basket Allocator**:
1. **The Barbell Focus**: Blends structural compounding (R&D and Technological Moats) with event-driven activism (Loeb/Bloom Catalyst Playbooks).
2. **Model Migrations**:
   - **The Radar**: `models/gemini-3.5-flash` for high-throughput, low-cost transcript scanning. Bypasses downstream layers if no moats or restructuring catalysts are found.
   - **The Interrogator**: `models/gemini-3.1-pro-preview` for alternative data & acoustic/tone validation.
   - **The Architect**: `gpt-4o` for System-2 bull/bear probabilistic scenario mapping.
   - **The Moderator**: `models/gemini-3.1-pro-preview` acting as Chief Risk Officer (CRO) for Expectations Arbitrage & Temporal Vetoes.
3. **The Portfolio Director (Apex PM & Basket Allocator)**: Refactored from a two-run individual assessment into a **single-run cross-sectional triage and basket allocation process** to eliminate Agreeability Bias and enforce relative opportunity cost. Enforces strict quotas (Alpha Basket of 5-7 tickers, Capitulation Watchlist of 3-5 tickers, and Graveyard for rejections).

---

### 4.1. Upgraded Backtest Performance (1-Year Period: 2025-03-31 to 2026-03-30)

We ran the upgraded barbell debate and allocator configurations against the **`emerging/rd_capitalized_dcf`** growth methodology (using `top_n = 50` rebalance target):

| Methodology | Configuration | CAGR | Max Drawdown | Sharpe Ratio | Total Trades | Final Portfolio Value |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **emerging/rd_capitalized_dcf** | Baseline (Pure Quant) | 27.09% | -3.90% | 2.295 | 301 | $129,654.18 |
| | Debate-Filtered | 26.95% | -3.90% | 2.277 | 306 | $129,495.25 |
| | **Portfolio Director (Apex PM - Sized to Active)** | **30.84%** | **-3.90%** | **2.796** | **300** | **$133,803.27** |

> [!NOTE]
> * **Sizing to Active Stocks (`equal_active`)**: By using the upgraded concentrated weighting configuration, we prevent the engine from filling vetoed slots with unvetted candidates or leaving cash idle. When the Director culls the portfolio, capital is fully reallocated across the approved stocks. This boosts CAGR to **30.84%** (+3.75% absolute outperformance over the quant baseline) and increases the Sharpe Ratio to **2.80**.
> * **8-Picks Sub-Portfolio Results (on 2025-10-27)**:
>   * Sized to 50 (Cash Drag): CAGR = **17.82%** | MaxDD = **-2.61%** | Sharpe = **2.84** (the remaining 84% stays in cash).
>   * Fully Invested (Concentrated): CAGR = **35.01%** | MaxDD = **-5.85%** | Sharpe = **2.68** (100% of capital distributed across the 8 picks).
> * **Uncorrelated Risk & Diversification**: By culling semiconductor supply-chain overlaps and macro-clustered bets, the Portfolio Director successfully constructed an idiosyncratic moat portfolio with diversified risk.

---

### 4.2. Upgraded API Cost & Savings Analysis

The refactored architecture achieved **dramatic cost reductions** by introducing transcript truncation (from ~35k characters to 8k characters), Radar programmatic bypass, and consolidating the Director into a single-run batch call:

#### **Single Date Cost Breakdown (50 candidates, 41 pass Radar)**
| Layer | Original Cost (Claude Opus) | Upgraded Cost (Gemini 3.x Barbell) | Savings (%) |
|---|---|---|---|
| Radar / Analysis | $1.1724 | $0.5119 | 56.3% |
| Moderator (CRO) | $8.2462 | $0.2255 | 97.3% |
| Director (PM) | $23.1060 | $0.0288 | 99.9% |
| **Total per Date** | **$32.52** | **$0.77** | **97.6%** |

#### **Projected Full Backtest Cost (13 dates, 650 total candidates)**
| Configuration | Total Cost (13 dates) | Savings (%) |
|---|---|---|
| Original Claude Opus | **$422.82** | - |
| **Upgraded Gemini 3.x Barbell** | **$9.96** | **97.6%** |
| **Total Savings** | **$412.86** | **97.6%** |

> [!TIP]
> * **Single-Run Director Consolidation**: Consolidating the Portfolio Director from 50 separate stock-by-stock LLM calls to a single cross-sectional batch call reduced the Director cost from **$23.11** to **$0.0288** per date (a **99.9% cost reduction**).
> * **Transcript Truncation**: Truncating raw transcript inputs to 8,000 characters (focusing on prepared executive remarks containing primary R&D moats and catalysts) reduced token footprints by **75%**, speeding up Radar queries to **4.5 seconds** and saving significant input token costs.

---

## 5. UI Fixes, Column Sorting, Ticker Search, and Weekend EOD Greeks Repricing (2026-05-24)

We successfully resolved compilation/syntax errors in the frontend app, finalized the search and sorting features in the prediction tables, fixed the weekend EOD date resolution in the price monitor backend, and pushed the updated Friday EOD prices/Greeks to GCS.

### Key Accomplishments
* **Next.js Compile & Build Fixes:**
  * Fixed an unbalanced JSX tag check around the main content container in [page.tsx](file:///c:/Users/Bruno/Stock-Screener/frontend/app/page.tsx#L1384), properly wrapping the sectors dashboard with `{viewMode === "sectors" ? (...) : ...}`.
  * Corrected the broken `{collectingPreds.length === 0 ? (...) : (...) }` ternary wrapper in [performance/page.tsx](file:///c:/Users/Bruno/Stock-Screener/frontend/app/performance/page.tsx#L2013) that caused Turbopack build crashes.
  * Reordered the `stocks` declaration in [page.tsx](file:///c:/Users/Bruno/Stock-Screener/frontend/app/page.tsx#L986) to prevent block-scoped reference errors during type checking.
  * Resolved Next.js compile errors due to property mismatches (e.g. `basket.title` to `basket.name`).
  * Verified that local `npm run build` runs and compiles 100% successfully.
* **GCS Write Auth Fallback:**
  * Refactored `gcs_write` in [monitor_prices.py](file:///c:/Users/Bruno/Stock-Screener/backend/monitor_prices.py#L84) to include the local `gcloud auth print-access-token` fallback (similar to the fallback in the signal tracker). This allows developers executing the monitor script locally to successfully update GCS files on weekends without authentication blocks.
* **Repriced All Open Cycles:**
  * Successfully executed [monitor_prices.py](file:///c:/Users/Bruno/Stock-Screener/backend/monitor_prices.py) locally on Windows.
  * Correctly fetched EOD option greeks and prices for Friday, May 22, 2026.
  * Repriced all 1,112 open options contracts (532 in `60d` P(20) regime, 580 in `30d` P(10) regime) and wrote the updated states to GCS.
* **Search & Sorting Deployment:**
  * Deployed the frontend fixes to `main` branch to trigger remote build and Vercel hosting.
  * The prediction list tables now display a dynamic search input that filters by symbol and company name, along with header-click sorting for probability (`P20` / `P10`), `MAX%`, `MIN%`, `DTE`, and `IV`.
