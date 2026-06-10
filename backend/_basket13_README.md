# Basket 13 — the Catalyst sleeve in Speculair

Connects **Catalyst Watch** (the event-driven board, `catalyst_candidates_231.json`) to **Speculair**
as a tracked **paper** basket with **event-resolution** semantics — and a **calibration loop**: every
entry and resolution is stamped so the edge thresholds, lane tilt, and lane priors can be re-fit
against realized outcomes.

> **Paper only.** No live orders, ever. Any broker (IBKR) access is read-only (quotes/chains).
> Sizing and expression are *recorded*, not executed.

---

## Pipeline (run order)

```
catalyst_candidates_231.json
   │  python _basket13_candidates.py            # filter -> entry + staging pool
   ▼
_basket13_candidates.json   (~15-30 names)
   │  python _basket13_gen.py [--only A,B,C]     # -> _basket13_workflow.js (two phases, Fable 5)
   ▼
_basket13_workflow.js
   │  Workflow({scriptPath: ".../_basket13_workflow.js"})   # Phase 1 Catalyst-CRO -> Phase 2 Director
   ▼   (returns {cro, director:{picks,passed,memo}, ...}; write it to _basket13_out.json)
_basket13_out.json
   │  python _basket13_inject.py _basket13_out.json         # validate caps -> append entry + non-selection stamps
   ▼
_basket13_tracker.json   (append-only)
   │  python _basket13_inject.py resolve SYM --type FIRED_WIN --price 12.3   # stamp a resolution
   │  python _basket13_inject.py report                                      # calibration analytics
```

## Files

| File | Role |
|---|---|
| `_basket13_candidates.py` | Universe handoff. Filters the enriched board into the ENTRY (ACTIVE, edge H/M, unblocked, milestone ≤6mo) + STAGING (WATCH, edge H or lane≤2 & ≥M) pool. Attaches `super_cluster`, `dated_milestone`(=`valuation.expected_close_date`), `live_price`, `score`. |
| `_basket13_gen.py` | Two-phase debate generator (clone of `_valuation_gen.py`). Phase 1 **Catalyst-CRO** (per name, batched 5) attacks the TRADE on four surfaces only; Phase 2 **Director** selects + sizes under hard caps. Both phases `model:'fable'` (set `MODEL='opus'` to fall back). |
| `_basket13_inject.py` | Append-only sidecar tracker + deterministic **cap validator** + `resolve` + `report`. The LLM proposes, this asserts every cap before stamping. |
| `_basket13_selftest.py` | Synthetic entry→resolve→report round-trip + cap-rejection proof (temp tracker; never touches the real one). |
| `_basket13_mark.py` | Daily NAV mark → `marks[]` in the tracker (idempotent per date; underlying prices; resolved seats freeze at exit). Feeds the /catalysts TRACK RECORD chart. Scheduled task `basket13-daily-mark` runs it weekday evenings (mark + export, local-only — publishes to prod on the next §10 push). |
| `_basket13_export.py` | Tracker → `frontend/app/data/basket13.ts` (joins CRO conditions, computes `expected_return_pct`, carries `marks[]`). Re-run after every inject / resolve / mark. |
| `_basket13_tracker.json` | The append-only ledger (created on first inject). |

## Design invariants

1. **Catalyst reality is settled upstream.** The scan→deep→skeptic tier already adjudicated *"is the
   event real"* (kills 40–50%). The basket-13 debate adjudicates ONLY *"is the trade good."* The CRO is
   explicitly forbidden from attacking margin-of-safety, valuation cheapness, business quality, or
   "would I own this for 5 years" — a catalyst name is *supposed* to look bad on value/quality.
2. **Paper basket, read-only broker.** No order placement.
3. **`score` / `board_priority` are never mutated** — Catalyst Watch owns them.
4. **Tracker is append-only; every entry must eventually resolve; non-selections are recorded** (the
   counterfactuals selection-calibration needs).
5. **Caps are hard** — enforced deterministically in `_basket13_inject.validate()`, not left to the LLM.

## The • dials (re-fit from realized outcomes — NOT constants)

Re-fit **quarterly** from `report` (hit rate + realized-vs-expected R:R + slippage, by lane / driver /
edge band):

| Dial | Where | Start |
|---|---|---|
| Milestone window (entry) | `_basket13_candidates.py` `MILESTONE_WINDOW_MONTHS` | 6 |
| Edge gate / staging lane | `_basket13_candidates.py` `EDGE_OK`, `STAGING_LANE_PRIORITY` | {H,M}, ≤2 |
| Max names / driver | `_basket13_inject.py` `MAX_PER_DRIVER` | 2 |
| Max % / super-cluster | `MAX_SUPER_PCT` | 40 |
| Basket size | `MIN_NAMES`,`MAX_NAMES` | 8–12 |
| Risk-to-floor / name | `RISK_TO_FLOOR_PCT` | 1.5% NAV |
| Binary premium-at-risk | `BINARY_PREMIUM_PCT` | 2% NAV |

(Upstream edge thresholds 2.5/1.5 and lane tilt 0.12 live in `_post_board.py`; this loop informs them.)

---

## PENDING / follow-ups

### Apex addendum (Task 5) — ✅ WIRED (regime apex)
Applied as **STEP 3b** in the regime apex director prompt (`backend/weekly_opus_refresh.py`,
`_WORKFLOW_TEMPLATE`, between STEP 3 and STEP 4): the Director reads
`backend/_basket13_candidates.json` if present (skips silently if absent — the weekly run never
breaks when the sleeve has not run), gets the 4-line reading guide (score ≠ edge; ev_pct ≠ MoS;
check `dated_milestone` vs holding window; edge_grade is live-price-perishable), and the HARD
constraint: never select a sleeve name with `valuation_method == binary_prob`, `edge_grade == L`,
or a blocking edge_flag. One-line insertion; nothing else in the apex prompt restructured. The
**value** apex (`VALUE_DIRECTOR_PROMPT`) was deliberately NOT touched — it is the pure-value book
with the catalyst overlay removed; sleeve names are a conceptual mismatch there.

Constraint test: `python _basket13_apex_check.py [apex_basket.json]` — asserts no apex pick is a
sleeve name violating the constraint (exit 1 + named violations). Run it after every regime-apex
run. Negative-tested (a synthetic apex holding MGNI/binary_prob is correctly rejected).

### Frontend (Task 6) — deferred (spec's escape hatch)
The catalyst-sleeve fields (structured R:R, option expression/strikes, driver-cap utilization, resolution
history) do **not** exist in `speculair_baskets.json` yet, and the basket cards in `frontend/app/page.tsx`
(parallel session's file) are bespoke per book. Cheapest first step: publish Basket 13 as a
`per_methodology_baskets` key (auto-renders a thin card). Full catalyst-sleeve section (~120 lines,
modeled on the Apex block) is a follow-up once the structured fields flow.

---

## Verification status (Task 7)

- ✅ Extractor yields 29 (9 entry + 20 staging); MGNI present as forced-seller staging. *(PUBM is
  excluded — it is edge_grade **L** on the live board, so the edge gate correctly drops it.)*
- ✅ Director caps asserted programmatically (`_basket13_selftest.py`): ≤2/driver, ≤40%/super-cluster,
  risk-to-floor ≤1.5%, binaries defined-risk ≤2%, staging equity-only half-weight, 8–12 names.
- ✅ entry→resolve→report round-trips on a synthetic position.
- ⏳ Live CRO dry-run on Fable (one batch) — pending go (spends tokens + hits FMP/IBKR read-only).
- ✅ Apex constraint test — `_basket13_apex_check.py` wired + negative-tested (synthetic MGNI apex
  rejected exit 1); current live apex: 10 picks, 0 sleeve names, clean.
