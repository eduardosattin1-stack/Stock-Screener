# FUTURE RESOURCES — Phase 3 handoff (for the executing session)

> **Audience**: the Claude session (Sonnet 5) building Phase 3 — Lane A debates + Director + post +
> publish. Read this file, then `FUTURE_RESOURCES_SPEC.md` §5 + §7 + §8 + §9(Phase 3) IN FULL before
> writing any code. The spec is the design authority; this handoff only adds session-state context,
> execution order, and coordination rules the spec couldn't know about.

## 0. State of the world (as of 2026-07-08, branch `claude/fr-phase2-chain-map`)

DONE (Phases 0–2, tested):
- `fr-universe` (Stage A/B two-lane screen) — validated LIVE on the operator box: 627 liquid
  candidates, 297 lane-A / 330 lane-B, all chains populated, taxonomy v1.2 (`(verify)` strings
  fixed empirically against FMP's real vocabulary).
- `fr-universe` now also emits the chunked Sonnet chain-map workflow
  (`future_resources/_fr_map.js` + `_fr_map_chunk_*.json`).
- `fr-map-merge` — merges shards, enforces the **physical-anchor rule** (drops printed, never
  silent), promotes royalty/streamers from lane_b (Stage B gated cash before `business_model` was
  known), computes Lane A metrics, writes `future_resources/universe.json` + `chain_map/<SYM>.json`.
- `backend/_opus_debate/_resource_metrics.py` — ebitda_margin_band / fcf_torque_10pct /
  commodity_beta_2y / gm_trajectory. All unit-tested; commodity chains get torque, robotics/quantum
  get gm_trajectory (never torque — no spot price to be levered to).
- `FUTURE_RESOURCES_REGIME.md` + `backend/_opus_debate/future_resources/regime_state.json` —
  first live 6-agent regime read (check these exist on the branch; if missing, regenerate per spec
  §4 protocol: 6 parallel research agents → synthesize, citations mandatory, never fabricate spot).
- Disruptor retired end-to-end: every `disruptor-*` mode is a code-level no-op
  (`ALLOW_DISRUPTOR=1` operator escape hatch); frozen card live; routine rewritten
  (`ROUTINE_speculair_weekly.md` is the canonical copy).

NOT YET RUN (needs the operator box / FMP key): the chain-map Workflow itself over the real 627
candidates + `fr-map-merge` over its shards. Phase 3's `fr-prep` self-gates on
`future_resources/universe.json` existing and fresh — so the first real Phase 3 run happens after
the operator (or the Monday routine) executes: `fr-universe` → `Workflow(_fr_map.js)` →
`fr-map-merge`.

## 1. COORDINATION — a parallel session is modifying the multi-agent debate engine

Another chat is actively working on the multi-agent debate machinery. HARD RULES to avoid collision:
1. **Do NOT edit shared debate surfaces**: `live_debate_engine.py`, the value/regime director
   prompts, `_WORKFLOW_TEMPLATE`, `_value_post.py`, `_regime_post.py`, `_post_common.py`,
   `publish_to_frontend.py`, any `_basket13_*` file. Phase 3 CLONES patterns from them
   (spec §0.3.5: two-books-independently-breakable); it never generalizes them in place.
2. Keep ALL Phase 3 additions in **new contiguous functions** in `weekly_opus_refresh.py`
   (beside `fr_map_merge`, mirroring how the disruptor block sits) + **new files**
   (`_opus_debate/_fr_post.py`, prompts under `future_resources/`) + new dispatch `elif`s only.
   This makes the inevitable `weekly_opus_refresh.py` merge trivial (pure additions).
3. `git fetch origin main` and rebase/merge this branch onto current `main` BEFORE starting and
   again BEFORE opening the PR — `main` moves fast (the other session + the operator box both push).
4. If the debate-engine session changed a pattern you were told to clone (e.g. a new skeptic
   consumption contract in `_post_common.py`), clone the NEW version and say so in the commit.

## 2. Build items (spec §5 is the design; these are the concrete deltas)

Clone anchors are the disruptor pipeline (all still in-repo, retired-but-readable):
`disruptor_prep` / `disruptor_input` / `DISRUPTOR_DIRECTOR_PROMPT` / `_disruptor_post.py` /
`disruptor_csv` / `disruptor_publish` in `weekly_opus_refresh.py` + `_opus_debate/_disruptor_post.py`.

a. **`fr-prep`** (weekly): staleness self-gate (`universe.json` missing or >21d → print
   `UNIVERSE STALE — run fr-universe first`, exit nonzero); isolated subtree
   (`future_resources/inputs|transcripts|results|dossiers|_archive_prev` — self-clean touches ONLY
   this subtree); Lane A members only (lane_b is Phase 4); re-debate triggers cloned from
   `_disruptor_redebate_triggers` (28d age / earnings / ±15% move / thesis-break / new entrant);
   bundles embed the member's `chain_map/<SYM>.json` + `metrics` + `regime_state.json` chain state;
   transcripts via `E.resolve_transcripts` with the online-fetch fallback (no-pick-skipped rule);
   emits `_fr_debate.js` with names baked in, `BATCH = 8`.
b. **FR debate BRIEF** (the one substantive prompt change, spec §5): judge COST-CURVE POSITION
   (the deterministic metrics are in the bundle; web-verify against company-reported AISC/cost
   guidance where published — the metrics are proxies, the debate must say when they disagree),
   CONTRACTING & RESERVE LIFE, CAPITAL DISCIPLINE (the sector's besetting sin), and THE REGIME
   (read `FUTURE_RESOURCES_REGIME.md` §<chain>). A live catalyst is neither a plus nor a
   requirement. **Torque is symmetric** — a bear case that doesn't price the downside torque is
   non-conforming.
c. **`FR_DIRECTOR_PROMPT`** (module constant beside `DISRUPTOR_DIRECTOR_PROMPT`): rubric ~25 pts
   each — (1) cost-curve position & torque quality, (2) contracting cycle & reserve life,
   (3) capital discipline & balance sheet, (4) growth-adjusted valuation GUARD (CRO `sop_mos_pct`
   veto/cap, never the driver). Hard constraints: exactly 8 picks; chain caps ≤3 names AND ≤30%
   weight (2-chain names count toward both); `growth_capex_fcf_negative` ⇒ size ≤0.75;
   regime HEADWIND chain ⇒ size ≤0.5 or written justification; torque×leverage quadrant ⇒ mandatory
   combined cap. Concentration stress: the shared "global growth + China demand" axis EVERY run +
   chain-specific axes (uranium: one utility contracting cycle; power-for-AI: one hyperscaler's PPA
   appetite — flag the cross-book overlap with the apex/value books; robotics+quantum: the
   long-duration-multiple axis). Output schema mirrors the disruptor's (numeric `size_units`,
   `thesis_break_px`, `bear_fv_px`, `combined_caps`, `chain_exposure`, memo).
   **Director seat: `model: fable`** (revived 2026-07-01; fall back to `opus` if retired again).
c2. **FR skeptic kill-tier**: every book now has one (the disruptor got its skeptic on 2026-07-01
   precisely because the highest-vol book lacked it — do not repeat that gap). Clone the unified
   skeptic pattern (`disruptor_skeptic` + its workflow emission): default-REFUTED unless primary
   sources confirm, verdict-based demotion to runner-ups in the post layer.
d. **`_opus_debate/_fr_post.py`**: parameterized clone of `_disruptor_post.py` — beta benchmarks
   `["XME", "URA"]`; `enforce_chain_caps` (≤3 names/≤30% weight per chain, deterministic backstop);
   weights / measured 2y correlation / stress block / thesis-break exits copied; idempotent
   `--offline`. Never changes membership (P1).
e. **`fr-input` / `fr-csv` / `fr-publish [--gcs]`**: clone `disruptor_input`/`disruptor_csv`/
   `disruptor_publish`. Publish contract (already pre-staged in the nightly scan): payload
   `frontend/public/speculair_future_resources.json`, picks array **MUST be named `apex_basket`**,
   embedded tracking key **`fr_tracking`**, NAV chain via `E._update_apex_tracking(...,
   gcs_path="scans/speculair_future_resources_tracking.json",
   local_name="speculair_future_resources_tracking.json")` — the
   `("future_resources", ...)` tuple in `screener_v6.py::_mark_speculair_nav()` self-activates on
   the first publish (off-scan members price via the `_current_prices` FMP fallback, already live).
   Honest banner per spec §7. **Do NOT touch `screener_v6.py`** — its part is done.
f. **Dispatch**: `fr-prep`, `fr-input`, `fr-post`, `fr-csv`, `fr-publish`, `fr-skeptic`,
   `fr-finish` beside the existing `fr-*` entries. All ride the existing
   `python backend/weekly_opus_refresh.py *` allowlist wildcard.

## 3. Acceptance (spec §9 Phase 3, verbatim) + verification here

- Offline synthetic tests in the scratchpad, mirroring this session's pattern
  (`test_fr_universe.py` / `test_fr_map_merge.py` there): stub `screener_v6` via
  `sys.modules` injection, fabricate `universe.json` + results, assert: exactly 8 picks schema,
  chain caps enforced by `_fr_post.py` on a synthetic 4-names-one-chain basket, `--offline`
  re-run byte-identical, HEADWIND size cap applied, skeptic REFUTED → demoted.
- `py_compile` on every touched file; the three existing FR test suites still green.
- Cross-book isolation: value/regime/B13 surfaces byte-identical before/after any fr-* run.
- PR into `main` (protected — direct push 403s; use the GitHub PR flow).

## 4. After Phase 3 lands (not this session's scope)

Phase 4 (Lane B mining/quantum catalyst mini-sweep + funded-through-milestone tracker) and
Phase 5/6 (frontend card + cadence: the routine's STEP 3C expands to the full chain; new bi-weekly
regime-refresh routine). The routine text change goes through `ROUTINE_speculair_weekly.md` FIRST
(source of truth), then pasted into the Routines UI by the operator.
