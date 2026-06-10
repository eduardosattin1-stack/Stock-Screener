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

## PENDING / follow-ups (deliberately not yet wired — they touch the parallel session's files)

### Apex addendum (Task 5) — ready to apply, target = the REGIME apex
The apex director lives in `backend/weekly_opus_refresh.py` (the parallel session's actively-developed
file). The conceptually correct target is the **regime** apex (`_WORKFLOW_TEMPLATE`, the `phase('Director')`
STEP-3 block, ~L1705 — it's the catalyst/regime-aware book, already on Fable, carrying lane/catalyst_status).
The **value** apex (`VALUE_DIRECTOR_PROMPT` ~L265) is the pure-value book with the catalyst overlay
removed → a conceptual mismatch; do not target it.

**Two parts:** (a) the prompt block below, and (b) wiring basket-13 names into the regime universe feed
(it arrives as stdout from `compact_table.py results_regime` — the basket-13 picks/candidates must be
surfaced there with their native fields, or via an added rows file the Director is pointed at).

Drop-in prompt block (append to the STEP-3 eligibility instruction):

```
BASKET-13 CATALYST SLEEVE — some universe names carry native catalyst fields (score, board_priority,
edge_grade, ev_pct, valuation_method, dated_milestone, lane_canon, resolution_driver). Reading guide:
(1) score / board_priority measure catalyst DENSITY, not cheapness — score is NOT edge;
(2) ev_pct is an expected-value barbell, NOT a margin of safety;
(3) check dated_milestone against YOUR holding window before selecting;
(4) edge_grade (H/M/L) is computed vs the LIVE price and is perishable.
HARD CONSTRAINT: you may NOT select any catalyst-sleeve name whose valuation_method == 'binary_prob',
whose edge_grade == 'L', or that carries a blocking edge_flag (QUARANTINED / NO_UPSIDE /
TRADING_THROUGH_TERMS / FLOOR_GE_LIVE / NO_BREAK_DOWNSIDE).
```

Constraint test (Task 7): after wiring, assert no apex pick has `valuation_method=='binary_prob'` or
`edge_grade=='L'` or a blocking flag.

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
- ⏳ Apex constraint test — pending the apex wiring above.
