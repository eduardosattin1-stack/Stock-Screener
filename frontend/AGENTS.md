<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

---

# CB Screener — frontend guide for future Claude sessions

## Page-level purpose (important — these are easy to confuse)

### `/` — Screener (`app/page.tsx`)
The main stock screener. Reads `gs://screener-signals-carbonbridge/scans/latest_{region}.json`. Displays ranked stocks with 13-factor radar, composite score, live ML hit-probability, Bull score, MoS, upside, and catalyst badges. Each row has an **Add to Portfolio** inline form (editable price, shares, notes). Does NOT maintain any user state.

### `/stock/[symbol]` — Stock Detail
Deep-dive view for a single stock. TradingView chart, 13-factor radar, earnings-transcript AI analysis, growth/profitability/valuation panels, news feed. Has an **Add to Portfolio** button in the header.

### `/portfolio` — User's Portfolio (`app/portfolio/page.tsx`)
**This is the user's actual holdings.** Every position was explicitly added by the user. Signal/Action badges are informational — they are NEVER triggers for any state change. The user decides when to close a position using the **Close** button (prompts for exit price and reason).

- State: GCS is authoritative (`portfolio/state.json`). Legacy localStorage positions are migrated up on first load, then localStorage is cleared.
- Monitor writes: the `monitor_v7.py` daily job updates `last_price`, `last_composite`, `peak_price`, `days_held` on existing positions only. It **does not add or close** positions.
- History: closed positions move to `state.history[]` with entry/exit/pnl/reason.

### `/performance` — Signal Performance Tracker (`app/performance/page.tsx`)
**This tracks how the screener's SIGNALS would have performed — not the user's actual trades.** Every BUY/STRONG BUY auto-opens a paper trade (in `performance/tracker.json`). When the signal later turns SELL, the paper trade closes. This is the model's shadow portfolio, used to validate live-time that the backtest's +35%/yr alpha holds up.

**Do not confuse this with `/portfolio`**. They share no state. The user's portfolio is what they actually own; the performance tracker is what the algorithm's recommendations would have produced if followed perfectly.

---

## v7.2 factor schema (13 factors)

Source of truth: `backend/screener_v6.py` → `WEIGHTS` dict.

Weights (must sum to 1.00):
- Technical 25% | Upside 14% | Quality 12% | Proximity 12%
- Institutional Flow 9% | Transcript 6% | Earnings 5% | Catalyst 5%
- Institutional 3% | Sector Momentum 3% | Analyst 3% | Insider 2% | Congressional 1%

Factor data is delivered in `factor_scores` on each stock object. New v7.2 factors:
- `institutional_flow` — 13F QoQ velocity (US-only, pass 2 enrichment)
- `sector_momentum` — stock return vs sector 60d avg
- `congressional` — Senate + House trade disclosures (US-only)

Missing factors are `null`, NOT zero. The radar renders nulls as dashed gray lines; `inferFactors()` should never substitute a default value for these.

### Display conventions
- Main screener radar: `MiniRadar` (44px) in table, `LargeRadar` (180px) in expanded row
- Stock detail: `FactorRadar` (260px), uses label + score-number pair per vertex
- Short labels (`FACTOR_LABELS`) keep each ≤10 chars to avoid overlap at 13 vertices

---

## Portfolio API contract

Frontend → `/api/portfolio/*` (Vercel route handlers) → Cloud Run HTTP endpoints.

### POST `/api/portfolio/add`
Request:
```json
{"symbol": "AAPL", "entry_price": 189.42, "shares": 10, "notes": "earnings beat"}
```
Response 200:
```json
{"ok": true, "symbol": "AAPL", "positions": 7}
```

### POST `/api/portfolio/close`
Request:
```json
{"symbol": "AAPL", "exit_price": 205.50, "reason": "took profit"}
```
Response 200:
```json
{"ok": true, "symbol": "AAPL", "positions": 6, "history": 3}
```

### GET `/api/portfolio/state`
Returns current `portfolio/state.json` directly. Used for cross-device refresh.

**Note on auth**: these endpoints are unauthenticated (user decision). Low-value target — worst case is restoring `portfolio/state.json` from GCS versioning. Keep UI calls minimal and do not expose these paths in error messages or docs that hit the public internet.

---

## ML hit_prob

`hit_prob` on each stock is the live GBM prediction for P(+10% in 60 days). Always prefer this over `getProb()` (the hardcoded composite→probability fallback table, kept only for stocks without `hit_prob` set). The model is systematically conservative by ~10-15pp in mid-high probability bands — when it says 70%, historical reality was ~80%. See backend `train_time_model.py` for retrain details.

---

## Styling conventions

- Font: `var(--font-mono)` (JetBrains Mono) for all numeric data
- Green `#2d7a4f` = good/buy, Red `#ef4444` = bad/sell, Amber `#d97706` = watch
- Sizing: tables use 11-12px, labels 9-10px, captions 8-9px
- Never introduce shadcn/ui or similar — this project uses inline styles only for portability
- Icons: `lucide-react` only

---

## Deploy flow

- Frontend: push to GitHub → Vercel auto-deploys from `frontend/` subdir
- Backend: push to GitHub → Cloud Build runs `deploy.yml` → rebuilds `stock-screener` image in `europe-west1`
- Both auto-deploy on commits to `main`. No manual steps required.
