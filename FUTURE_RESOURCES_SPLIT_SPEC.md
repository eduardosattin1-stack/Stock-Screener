# FUTURE RESOURCES SPLIT — Mining + Future Disruptive Tech (build spec v1.0)

> **Status**: approved-for-build pending Bruno's sign-off. Drafted 2026-07-27 from a 6-lens design
> pass + 2 adversarial verifications (14 invariant violations and 53 cross-section contradictions
> found and resolved — the resolution log is §C below).
> **Read order for an executing session**: this preamble (§A–§D) FIRST — it is AUTHORITATIVE and
> wins over any appendix text it contradicts — then the six design appendices (§1–§6) for the full
> mechanics. House rules in repo-root CLAUDE.md apply throughout and win over everything here.

## §A. What was decided (locked by Bruno, 2026-07-27)

1. The Future Resources book **splits into two independent books**:
   - **MINING** — chains: `uranium_fuel_cycle`, `copper_mining`, `precious_metals` (NEW: gold/
     silver producers + royalties), `rare_earth_strategic`, `diversified_miners` (NEW: BHP/RIO
     class). Gets the **full dedicated `/commodities` page** with the Dalio + Tavi Costa macro
     layer, replacing the Social Arb page **outright** (nav swap; the Cloud Run social engine is
     never touched).
   - **FUTURE DISRUPTIVE TECH (`fdt`)** — chains: `electrification_grid` (equipment side of the
     old copper_electrification), `nuclear_smr` (NEW), `power_for_ai`, `robotics_automation`,
     `quantum`. Inherits the amber card slot on the Speculair page.
2. The FR book **freezes** (disruptor precedent — frozen record, never back-filled, never deleted);
   **both new books start fresh live-forward NAVs**. No inherited or blended history.
3. Old `copper_electrification` names split **by business_model**: `producer`/`royalty_streamer`
   → Mining `copper_mining`; `equipment_services`/utility → FDT `electrification_grid`.

## §B. CANON — names, paths, keys (authoritative; any appendix text that differs is WRONG)

| Thing | Canonical value |
|---|---|
| Book literals | `mining`, `fdt` |
| Modes | `mining-universe/-map/-map-merge/-macro/-prep/-numeric-gate/-input/-post/-csv/-publish` + `fdt-*` mirrors (no `fdt-macro`) |
| Taxonomy files | `backend/_opus_debate/mining_chains.json`, `backend/_opus_debate/fdt_chains.json` (both v2.0; `future_resources_chains.json` stays frozen at v1.3, never loaded by new modes) |
| Run subtrees | `backend/_opus_debate/mining/`, `backend/_opus_debate/fdt/` |
| Payloads (GCS) | `scans/speculair_mining.json`, `scans/speculair_fdt.json` |
| Tracking (GCS + local) | `scans/speculair_mining_tracking(.weighted).json`, `scans/speculair_fdt_tracking(.weighted).json`; local same basenames in `frontend/public/` |
| Embed keys | `mining_tracking`, `fdt_tracking` |
| Nightly NAV tuples (screener_v6, the ONLY two sanctioned edits) | `("mining", "scans/speculair_mining.json", "scans/speculair_mining_tracking.json", "speculair_mining_tracking.json", "mining_tracking")` and the `fdt` mirror. The existing `("future_resources", ...)` tuple is **KEPT** — after the freeze renames `apex_basket` → `final_holdings` it self-no-ops ("no published constituents") forever. Removing it is an unsanctioned third edit. |
| Macro artifact | `backend/_opus_debate/mining/commodity_macro.json` → staged `frontend/public/commodity_macro.json` → `scans/commodity_macro.json`, produced ONLY by `mining-macro --gcs` |
| Macro payload date field | `generated_at` (staleness checks read this everywhere) |
| Tilt module | `backend/_opus_debate/_commodity_tilt.py` — the SINGLE source of truth for the Dalio tilt tables; the page renders tilt ONLY from data it generated (no frontend tilt const, ever) |
| Macro header source | page fetches `scans/macro_regime.json` — pushed by `mining-publish --gcs` as a staged copy of `backend/_opus_debate/macro_regime.json` (no payload embeds, no live macro fetch, no v8 `/api/macro`) |
| Post layers | TWO clones (house two-books-independently-breakable rule): `_opus_debate/_mining_post.py`, `_opus_debate/_fdt_post.py` — each trimmed to its book |
| Benchmarks | Mining `50/50 XME+GDX`; FDT `50/50 GRID+QQQ` — publisher stamps and card labels identical |
| Regime sidecars | `mining/regime_state.json` (5 chains, schema gains `vs_incentive_pct` per commodity chain), `fdt/regime_state.json` (5 chains) — bi-weekly refresh protocol unchanged |
| Nav | `Social Arb` entry → `Commodities` (`/commodities`), lucide `Pickaxe` |
| Scoreboard join key | pick `chain` (primary chain id) — page joins picks → scoreboard → tilt on it; no `commodity_family` field |
| Miners-confirmation window | 63 trading days, labeled "3m" |
| Freeze tool + date | `backend/_retire_fr.py --execute`; freeze date = the execute-run date (stamped then, never pre-agreed) |
| FR retirement guard | `_norm == "fr" or _norm.startswith("fr-")` → RETIRED notice + exit 0; `ALLOW_FR=1` operator escape; fr-* bodies stay in place for forensics (deletion is a later housekeeping PR) |
| New test suites (committed, not scratchpad) | `backend/_opus_debate/test_mining_pipeline.py`, `test_fdt_pipeline.py`, `test_commodity_tilt.py` |

## §C. Resolution log (every verifier finding → the ruling)

**Invariant violations (all fixed):**
1. *FR tuple removal* — REJECTED; tuple kept (see §B). `_retire_fr.py --execute` renames
   `apex_basket` → `final_holdings` in the frozen payload, which makes the nightly mark a true
   no-op. Pipeline §9's removal step and its acceptance test 7 are void.
2. *Frontend PHASE_TILTS const* — deleted. `mining-macro` embeds `tilt: {phase_table,
   quadrant_table, resolved}` (rendered by `_commodity_tilt.py`) into `commodity_macro.json`; the
   page renders only that. Page appendix Block 1 is amended accordingly.
3. *Tilt key-sync test target* — points at `mining_chains.json` v2.0 ids (not the frozen v1.3 file).
4. **Gold as a scored input (the big one)** — the taxonomy adds `monetary_metal: true` to the
   `precious_metals` commodity block. For any `monetary_metal` chain the scoreboard NEUTRALIZES
   the momentum leg AND the percentile/setup-proxy leg (fixed midpoints, stamped
   `momentum_source: "monetary_metal_excluded"`). Precious ranks ONLY on miners-confirmation
   (GDX/GLD, equities confirming the metal), the Dalio tilt, and regime-read state. Gold/silver
   spot dials remain on the page as DISPLAY-ONLY, labeled so. This extends the debt-cycle
   momentum-loop guard ("it would have bought the Jan-2026 gold top") into the scoreboard.
5. *FRED re-entering via the page's dial contract* — dial set is tavi's D1–D8, FMP-only. The
   macro header's real-rate readout comes from the `debt_cycle` block of `macro_regime.json`
   (already computed upstream), labeled as such. No `real_30y`/`cpi_trend`/`gold_spx_ratio` dials.

**Substantive contradictions (ruling per topic; mechanical name drift already normalized into the appendices):**
6. *Post-layer structure* — two clones win (§B) over a parameterized `--book` flag: matches the
   `_value_post`/`_disruptor_post`/`_fr_post` precedent; a shared module is a shared breakage
   surface between books.
7. *Duration caps (Dalio §4.4)* — `_mining_post.py` IMPORTS `stamp_duration_buckets` +
   `duration_cap_entries` from `_regime_post` (read-only reuse; `_regime_post.py` itself is never
   edited) and logs to its OWN ledger `_cycle_ledger_mining.jsonl` (never the regime book's).
   Advisory semantics identical (EQUAL_WEIGHT_BOOKS honored). `_fdt_post.py` has no duration layer.
8. *Director macro injection* — ONE block, built at `mining-input` time: the
   `_commodity_tilt.director_brief(snapshot)` text + the `commodity_macro.json` scoreboard,
   under a single `COMMODITY MACRO (CITED-ONLY)` header. Macro reaches the book via risk_stance,
   entry-discount floors, horizon stretch, and phase_fit judgement — NEVER conviction, NEVER
   membership (existing FORK-2/B wiring). FDT's Director gets NO commodity tilt (it keeps the
   plain macro_regime read the disruptor rubric used).
9. *Scoreboard setup leg input* — `mining/regime_state.json` schema gains `vs_incentive_pct`
   (+ `as_of`); when absent/stale >45d the leg falls back to the percentile proxy and stamps
   `setup_source: "percentile_proxy"` (fail-open, banner'd — a data gap never tightens anything).
10. *Sparklines* — every dial in `commodity_macro.json` carries `series`: ~52 weekly points
    (downsampled closes). Percentile field is `pctile` labeled with its true window (6y joint /
    5y where shorter); no 10y label anywhere.
11. *Spot-vs-incentive display* — the page renders spot BELOW incentive as the GREEN
    "supply-destruction setup" state (matching what the scoreboard scores), with the label spelled
    out so the color can't be misread as bearishness.
12. *Cross-book dedup* — no standalone mode. `mining-map-merge` and `fdt-map-merge` each call a
    shared `_cross_basket_dedup()` helper that reads the OTHER book's universe (if present) and
    enforces: a straddler seats in ONE book only — primary by revenue share; ties →
    `commodity_revenue_share >= 0.5` goes Mining, else FDT. Both merges print what they ceded.
13. *Social removal* — per Bruno's decision: `frontend/app/social/` AND `frontend/app/api/social/`
    are deleted in PR-2, with a grep sweep proving nothing references them. The Cloud Run engine
    and its GCS data are untouched. (The page appendix's "keep reachable" text is void.)
14. *Amber-slot transition* — dual-mode during migration: the card fetches
    `scans/speculair_fdt.json` first and falls back to the live FR payload until the maiden FDT
    publish; after `_retire_fr.py --execute` the FR record renders as a separate frozen card
    (retired-disruptor idiom). Only after one stable week does the FR fallback path get removed.
15. *PR ordering* — three PRs (migration appendix §0 wins): **PR-1** taxonomies + pipeline +
    `mining-macro` + `_commodity_tilt` + post layers + tests; **PR-2** frontend (/commodities page,
    FDT card, nav swap, social removal); **PR-3** retirement (fr-* guard, `_retire_fr.py`,
    ROUTINE v3 text) — the guard lands only AFTER both maiden publishes succeed on the operator
    box. Pipeline §10's one-PR plan is void.
16. *Routine cadence* — ROUTINE v3 STEP 3C runs `mining-macro --gcs` (the `--gcs` is mandatory —
    without it the page's GCS object goes permanently stale) BEFORE the Mining debates so the
    Director cites fresh dials; then the Mining chain; STEP 3D runs the FDT chain; universes
    monthly (21d gate per book); regime sidecars bi-weekly; additive-lane guard preserved for both.
17. *Freeze/flip trigger* — the operator (or the routine's post-publish check) runs
    `_retire_fr.py --execute` only after BOTH maiden publishes round-trip from GCS. It stamps the
    freeze date, renames the picks key, adds the honest retired banner. FR fr-* modes guard-retire
    in the same PR-3.
18. *Tests* — committed suites (§B) replace all references to the scratchpad-only
    `test_fr_phase3.py`. Acceptance additionally requires: cross-book isolation (value/regime/B13
    surfaces byte-identical across any mining-*/fdt-* run), key-sync (`_commodity_tilt` families ==
    `mining_chains.json` ids), monetary-metal neutralization, dedup tie rule, and both `--offline`
    idempotency checks.

## §D. Open items for Bruno (non-blocking, defaults chosen)

1. **FDT Lane-A floor**: 20 (vs Mining 25) — quantum/SMR profitable cohorts are structurally thin.
   Flip back to 25 if you'd rather keep the bar and accept a thinner book.
2. **Mining benchmark**: 50/50 XME+GDX (default). Alternative if you want uranium represented at
   book level: 40/40/20 XME/GDX/URA — say so before PR-1 and the publisher stamps it.
3. **Proxy ETFs with `(verify)`**: GRID (electrification_grid), NLR (nuclear_smr) — first live
   universe run prints 0-row WARNs if wrong; config-only fix in the taxonomy files.
4. **PWR placement**: primary `power_for_ai` (2-chain with `electrification_grid` allowed).

---

# Appendices — the six design sections (§1–§6)

> Written by parallel design lenses against the live repo; mechanical naming already normalized to
> §B. Where any sentence still contradicts §B/§C, the preamble wins.

## §1. The Dalio layer

# The Dalio layer — consuming the existing macro stack

## 0. Governing principle: consume, never rebuild

The /commodities macro layer is a **read-only consumer** of the existing three-axis stack. It adds exactly one new deterministic artifact (a static phase/quadrant → commodity-family tilt table) and zero new classifiers, fetchers, state machines, or snapshot writers.

**Explicitly NOT rebuilt (spec bugs if an implementer adds them):**

- **No new phase machine.** `backend/debt_cycle.py` stays the only phase authority. `weekly_opus_refresh._write_macro_regime` remains the ONLY call site that runs `fetch_debt_cycle(advance=True)`. The commodities publish path and the Mining Director read the snapshot file — they never call `fetch_debt_cycle` at all (not even `advance=False`; a read-time call would touch the GCS cycle cache and, in cloud sandboxes where FRED/TreasuryDirect 403, would degrade the read for no benefit).
- **No new macro fetchers.** FRED series, TreasuryDirect auctions (Saturday `fetch-auctions` job), FMP treasury-rates/economics — all existing. The verified commodity quote feeds (GCUSD, HGUSD, SIUSD, …) feed the page's **market-dial display layer** (owned by the page-data section of this spec), not this layer.
- **No second regime read.** `backend/_opus_debate/regime_read.json` (the RegimeRead adversarial agent) is reused as-is; the Mining Director does not get its own regime skeptic.
- **No v8 switch, no snapshot schema change.** The v7 snapshot `backend/_opus_debate/macro_regime.json` is consumed byte-for-byte as `_write_macro_regime` publishes it today.

## 1. Inputs — the exact fields consumed

Everything comes from two files, both already published by the weekly pipeline:

### 1.1 `backend/_opus_debate/macro_regime.json` (v7 snapshot)

| Field | Type / values | Consumed by |
|---|---|---|
| `regime` | `RISK_ON\|NEUTRAL\|CAUTIOUS\|RISK_OFF` | page header chip; Director STEP-1 |
| `score` | 0–1 | page header chip |
| `quadrant` | `GOLDILOCKS\|REFLATION\|STAGFLATION\|RISK_OFF` (may be missing/`UNKNOWN` — see §6) | tilt resolution (row axis 2); entry-discount floor; Director |
| `quadrant_basis` | prose, e.g. `"growth up (gdp 0.65) × inflation hot/sticky (cpi 0.42)"` | page tooltip — a mid-band read stays auditable |
| `regime_detail` | `{growth, inflation, rates, credit}` English labels | page dials row; Director prose |
| `debt_cycle.debt_cycle_phase` | `EXPANSION\|DISCIPLINE\|FORCING\|MONETIZATION\|UNKNOWN` | tilt resolution (row axis 1); stance modifier; horizon; Director |
| `debt_cycle.cycle_score`, `cycle_target`, `weeks_in_phase`, `prior_phase`, `pending_target`, `pending_count`, `transition_blocked`, `transition_implied` | state-machine internals | page "cycle odometer" panel (phase, weeks in phase, where the composite is pulling, whether hysteresis is pending a step) |
| `debt_cycle.cycle_sub_scores` | 6 gauges, **inverted convention: higher = later/more stress** | page gauge strip (real_long_rate is the master dial; auction_quality is the Dalio tell) |
| `debt_cycle.cycle_sub_sources` | `live\|missing` per gauge | honest data chips (§6) |
| `debt_cycle.confidence` | `high\|med\|low` (count of live gauges) | banner (§6) |
| `debt_cycle.seeded` | bool | banner: "phase is a seeded prior, not yet earned" |
| `debt_cycle.phase_basis`, `phase_detail` | prose | page phase card body |
| `debt_cycle.reserve_asset_check` | `{consistent_with_phase: true\|false\|null, note}` | falsification chip (§5) |
| `debt_cycle.duration_caps`, `expected_horizon_months` | per-phase caps + 12/18/24 | Mining post layer (§4.3, §4.4) |
| `debt_cycle.asof` | date | staleness banner (§6) |

### 1.2 `backend/_opus_debate/regime_read.json` (if present)

`agent_view`, `phase_view` (`AGREE|CONTRADICT`), `evidence[]`, `falsifiers[]`, `phase_falsifiers[{condition, check_by, implies}]`, `stance_note`, `confidence`. The page renders the phase falsifiers as a **"What would change this call"** panel — dated, checkable conditions, same honesty culture as the briefing CYCLE chip. The Mining Director gets the same one-notch rule the Apex Director has: a CONTRADICT with dated evidence may temper stance one notch, never flip a dial.

### 1.3 Payload embedding (books never blended)

The Mining book's published payload embeds its **own copy** of the snapshot under `commodities.macro_regime` (mirroring how the briefing reads `spec.macro_regime` rather than the lean v8 `/macro` endpoint — that endpoint carries no quadrant and no debt_cycle block, so the page must NOT use it). The /commodities page renders exclusively from its payload; it performs no live macro fetch. The FDT book independently embeds the same snapshot in its own payload. Same file, two copies, zero blending.

## 2. The one new artifact: `backend/_opus_debate/_commodity_tilt.py`

A standalone, pure, no-network module (constants + pure functions — same isolation ethos as FORK 1/A). It is the **single source of truth** for the Dalio commodity playbook; the page and the Director prompt both render from it so they can never drift apart.

```python
# Family keys MUST equal the Mining chain ids in future_resources_chains.json
# after the split (test-enforced, §7): uranium_fuel_cycle, copper_mining,
# precious_metals, rare_earth_strategic, diversified_miners.

PHASE_COMMODITY_TILT: dict   # phase -> {favored, disfavored, gold_role, dalio_note}
QUADRANT_COMMODITY_TILT: dict  # quadrant -> {favored, disfavored, note}

def resolve_tilt(phase: str, quadrant: str) -> dict:
    """{family: 'tailwind'|'mixed'|'headwind'|'neutral'} — favored on BOTH axes
    = tailwind; favored on one & not disfavored on the other = mixed; disfavored
    on either = headwind. phase/quadrant UNKNOWN or unrecognized -> ALL neutral
    (fail-open: a data gap must never paint a headwind)."""

def director_brief(snapshot: dict) -> str:
    """Prompt-ready text block: current phase + quadrant, the two tilt rows,
    the resolved per-family tilt, gold_role, and the reserve_asset_check note.
    Injected verbatim into the Mining Director STEP 1 (§4.1)."""
```

CLI: `python backend/_opus_debate/_commodity_tilt.py` prints the resolved tilt for the current snapshot; `... brief` prints the Director text block (lets the weekly Workflow shell it in, and lets a human eyeball what the Director saw).

### 2.1 Phase → commodity implications (Dalio; DISPLAY + TILT table)

Rendered on the page as a 4-row table with the live phase row highlighted; cited by the Mining Director. Convention reminder printed on the page: cycle sub-scores are inverted (higher = later in cycle).

| Phase | Favored families | Disfavored | Gold's role (`gold_role`) | Dalio note (`dalio_note`) |
|---|---|---|---|---|
| **EXPANSION** | `copper_mining`, `diversified_miners`, `uranium_fuel_cycle` — credit expansion funds capex, demand-driven industrials lead | `precious_metals` | Underweight — positive-but-*chosen* real rates are gold's opportunity cost; no monetary premium while credit is freely extended | Borrowing accommodated; own what a growing economy consumes, not what a breaking one hedges |
| **DISCIPLINE** | Cash-generative producers in every family: `diversified_miners`, established `copper_mining` FCF payers, royalty/streaming models inside `precious_metals` | Development-stage story names in ALL families (juniors, pre-production rare-earth, uranium developers) | Headwind at the metal level — imposed positive real rates compete with a zero-yield asset; **royalties survive on FCF, the gold price does not have to rise** | Real rates being imposed by the bond market: payback speed beats resource optionality. Real assets **not yet** — that trade belongs to MONETIZATION, and buying it early is the classic misread |
| **FORCING** | Fortress balance sheets only: royalty/streamers (no debt, contractual cash), lowest-cost `diversified_miners` majors | Anything that needs capital markets — juniors, developers, high-cost producers; industrial metals hit by de-grossing | Two-sided — sold in the margin-call liquidation, then first re-bid as the market front-runs the monetization response | Funding stress liquidates the complex indiscriminately; survivorship is the only edge. Reaches suspended, not resized |
| **MONETIZATION** | `precious_metals` first (producers + royalties), then hard assets broadly: `copper_mining`, `diversified_miners`, `uranium_fuel_cycle` re-rate as real assets | None structurally — paper-claim duration is the loser, not commodities | **The phase gold exists for** — real rates forced negative while the CB absorbs supply; the monetary premium expands | The printing phase: currency debasement re-prices everything hard. This is where the real-asset trade is *earned*, not anticipated |
| **UNKNOWN** | — (all `neutral`) | — | "no phase read — no gold prior" | Fail-open: loosest caps, no tilt, banner (§6) |

### 2.2 Quadrant → commodity implications (JPM 2×2, Dalio-consistent)

| Quadrant | Favored | Disfavored | Note |
|---|---|---|---|
| **GOLDILOCKS** | `copper_mining`, `uranium_fuel_cycle` (structural demand: electrification, AI power) | `precious_metals` | Growth up, inflation cooling — demand-linked metals carry on volume, monetary metals lack a driver |
| **REFLATION** | `copper_mining`, `diversified_miners`, `rare_earth_strategic` | — | The classic commodity quadrant: growth up + inflation hot, industrial metals lead the complex; gold participates but does not lead |
| **STAGFLATION** | `precious_metals` | `copper_mining`, `diversified_miners` (demand-cycle beta) | Pricing power + real assets only; decelerating growth hits volume-linked miners while sticky inflation feeds the monetary metals |
| **RISK_OFF** (disinflationary slowdown) | `precious_metals` (royalties especially — FCF carry) | Everything demand-linked | Falling real rates make gold a duration proxy; the rest of the complex trades with recession odds |

Where the two axes disagree (e.g. DISCIPLINE phase × REFLATION quadrant — today's plausible tape), `resolve_tilt` degrades the conflicted family to `mixed` and the page shows both rows highlighted so the tension is visible, not averaged away.

## 3. What the Mining Director consumes (weekly Workflow, `weekly_opus_refresh.py`)

The Mining Director prompt gets a STEP 1 modeled on the existing Apex Director STEP 1 (same file, `phase('Director')` block — copy its structure, not its content):

1. Read `backend/_opus_debate/macro_regime.json` (regime + score + quadrant + quadrant_basis + `debt_cycle` block) and `regime_read.json` if present (one-notch rule).
2. Receive the `_commodity_tilt.director_brief(...)` text block injected by the Workflow (shelled via the CLI) — this is the commodity phase playbook it must cite.
3. Apply the quadrant playbook → provisional stance, then the **phase modifier via the same semantics as `debt_cycle.apply_phase_to_stance`** (DISCIPLINE caps at `balanced`, FORCING floors at `defensive`, MONETIZATION unlocks `aggressive` even from a RISK_OFF quadrant — for a mining book MONETIZATION-unlocks-aggressive is precisely the state the book exists for, and the prompt says so).
4. Emit in the mining director output JSON: `risk_stance` (post-modifier), `regime_quadrant` (echo), `debt_cycle_phase` (echo), `phase_read` (one sentence), `expected_horizon_months` (12 EXPANSION/MONETIZATION, up to 18–24 DISCIPLINE/FORCING), `macro_read`, plus per pick: `regime_fit`, `phase_fit` (a story-duration developer seated in DISCIPLINE must say so and own it), and `commodity_family` (one of the five chain ids — lets the page join picks to the tilt matrix).
5. Stamp `director_last_phase` in the mining output for parity with the speculair Fork-4 stamp. No new re-run trigger is needed: the mining book is weekly-cadence, so a phase transition is picked up at the next publish by construction.

**The Director cites the tilt; it is never bound by it.** Membership stays entirely with the debate pipeline (underwrite → skeptic → Director), exactly as for every other book.

## 4. How the tilt is allowed to reach the book — the FORK-2/B channels, verbatim

The phase/quadrant/tilt **never gates eligibility and never moves conviction**. The only sanctioned channels, mirroring the existing wiring:

1. **Advisory stance** — `risk_stance` after the `apply_phase_to_stance` modifier (§3.3). Posture prose, not weights.
2. **Entry-discount floor (STEP-3a analog, same thresholds)** — a NEW mining seat's computed expected return to base fair value must clear **≥ +20% in GOLDILOCKS/REFLATION, ≥ +25% in STAGFLATION, ≥ +30% in RISK_OFF**. A bar to clear, not a weight. Held seats are never force-sold for slipping under it.
3. **Horizon stretch** — `expected_horizon_months` 12 → 18–24 in DISCIPLINE/FORCING (from `PHASE_HORIZON_MONTHS`), so the Director stretches the goal rather than chasing it into a bad tape.
4. **Duration caps, ADVISORY** — the mining post layer reuses `_regime_post.stamp_duration_buckets` (deterministic `debt_cycle.duration_bucket` from scan `p_fcf`/`fcf_margin` — royalties will read `cash_now`, developers `story`, no-data names `unknown` and OUTSIDE the cap, the load-bearing story/unknown split) and `_regime_post.duration_cap_entries` unchanged. While `_post_common.EQUAL_WEIGHT_BOOKS` is True this trims `size_units_effective` and stamps `duration_cap_effect: "advisory"` only — **no published weight moves**; the evidence accrues in `_cycle_ledger.jsonl`. Flipping `EQUAL_WEIGHT_BOOKS` is a sizing change governed by the FORK-2 note in CLAUDE.md, not by this spec.
5. **`phase_fit` / `regime_fit`** — judgement inputs to the Director's tiebreaks, rendered on the page per pick.

**Guard rails carried over unchanged:** `_regime_post._dated_fact_outside_phase` applies to the mining book — a phase citation is not a valid `delta_justification` for a conviction move; and no deterministic consumer anywhere may map a tilt label (`tailwind`/`headwind`) to units, weights, floors, or eligibility. The tilt is display + Director judgement, full stop.

## 5. Gold — the two hats, kept separate

- **Inside `debt_cycle.py` scoring:** gold remains a **falsification check only** (`reserve_asset_check`), never a scored input. This layer changes nothing there.
- **On the page:** market gold dials (GCUSD/SIUSD spot + history, GLD/GDX/SIL quotes — all verified FMP feeds) MAY be displayed as data, and the `reserve_asset_check` is rendered as a labeled falsification chip: *consistent* (✓), *inconsistent — phase call may be early/late, falsifier raised* (⚠), or *skipped — no gold data* (—), always with its `note` verbatim.
- **The seam that must never close:** nothing computed from displayed gold/ratio dials (including any Tavi-Costa-style ratio dials the page section adds — copper/gold, silver/gold, commodities/equities) may feed `resolve_tilt`, the phase machine, or any cap. `_commodity_tilt.py` is pure constants over `(phase, quadrant)` precisely so this is structurally impossible — it has no data inputs to smuggle gold into.

## 6. Fail-open + honest banners (display contract)

- `debt_cycle_phase == "UNKNOWN"` or snapshot `fallback: true` → matrix renders with **no highlighted row, all families `neutral`**, banner: "No phase read — macro layer degraded, showing the playbook without a call." A data outage must never paint a headwind on a family (the display analog of "never tighten the book").
- `quadrant` missing or `UNKNOWN` (the checked-in snapshot predates the quadrant; the briefing already has a `quadrantFallback` for this) → quadrant row unhighlighted; `resolve_tilt` returns phase-axis-only `mixed`/`neutral` labels; banner names the missing axis.
- `debt_cycle.confidence == "low"` or `seeded: true` → banner: "Phase read on N/6 live gauges" / "Phase is a seeded prior (2026 tape), not yet earned by the state machine."
- Each of the 6 gauges shows its `cycle_sub_sources` chip (`live`/`missing`); `transition_blocked: true` renders the `transition_implied` jump that hysteresis refused.
- `debt_cycle.asof` older than 8 days at page-build time (the module's own self-heal threshold) → "stale macro read" banner with the date.

## 7. Tests (add `backend/tests/test_commodity_tilt.py`; extend existing suites, do not fork them)

1. **Fail-open:** `resolve_tilt("UNKNOWN", q)` and `resolve_tilt(p, "UNKNOWN")` return all-`neutral` for every counterpart value; no KeyError on any of the 5×5 phase×quadrant grid (incl. UNKNOWN×UNKNOWN).
2. **Key-sync:** the family keys in both tilt tables exactly equal the Mining chain ids in `backend/_opus_debate/future_resources_chains.json` post-split (set equality, both directions) — guards taxonomy drift.
3. **Purity:** `_commodity_tilt` imports no fetcher/requests/network module (static import-graph assertion) — the gold seam of §5.
4. **Weights untouched:** regression in the mining post-layer suite mirroring the existing `test_regime_post` pattern — an identical book published under `resolve_tilt` outputs of all-`tailwind` vs all-`headwind` yields byte-identical published weights (tilt is not a sizing input).
5. **Existing invariants re-run:** `python backend/tests/test_debt_cycle.py` (2026-07 fixture must still read DISCIPLINE) and `python backend/_opus_debate/test_regime_post.py` must pass unmodified — this section adds zero code paths inside either.
---

## §2. The Tavi Costa layer

# The Tavi Costa layer — mining-macro dials (new, deterministic)

## 0. Summary and placement

A new **deterministic weekly mode `mining-macro`** (accept `mining_macro`) in `backend/weekly_opus_refresh.py`, whose computation lives in a **new standalone module `backend/mining_macro.py`** (placed beside `backend/debt_cycle.py`, same design pattern: pure, fixture-testable scoring functions + a thin live-gather layer + CLI). It computes Crescat/Tavi-Costa-style mining-macro dials from the verified FMP feeds only, writes:

- `backend/_opus_debate/mining/commodity_macro.json` (pipeline-side snapshot, read by the Mining Director prompt builder and the /commodities page build),
- `frontend/public/commodity_macro.json` (staged copy, byte-identical),
- pushes to `gs://screener-signals-carbonbridge/scans/commodity_macro.json` when `--gcs` is passed (exact `gcloud storage cp` + one-retry + live-readback pattern from `fr_publish`, `weekly_opus_refresh.py:2714-2751`).

No LLM anywhere in this mode. It is display + Director-citation input. **It never gates membership, never touches conviction, never feeds `debt_cycle.py` scoring.** Runs on local Claude Code only (house rule — no Cloud Run task, no scheduler; it is a verb in the Saturday runbook).

### What this mode must NOT duplicate

`backend/debt_cycle.py` already owns: FRED fetchers (`_fetch_fred_csv`), TreasuryDirect auctions, the 30y−3m term-premium score, HY OAS, WALCL, debt-service, the real-30y master dial, and the gold **falsification** check. `mining_macro.py` imports **nothing** from `debt_cycle.py` and `debt_cycle.py` must never import `mining_macro.py`. The only cross-touch is read-only: `mining_macro` reads the already-published `backend/_opus_debate/macro_regime.json` for the `debt_cycle.debt_cycle_phase` field (Dalio tilt, §4.4). It must **never** call `debt_cycle.fetch_debt_cycle(advance=True)` — `_write_macro_regime` (`weekly_opus_refresh.py:154`) is the only site allowed to tick the state machine. mining-macro also deliberately uses **no FRED/TreasuryDirect series at all** — every input is FMP, which works in cloud sandboxes too, so this mode has no environment-specific fetch path.

## 1. Inputs (all via `screener_v6.fmp(endpoint, params)` — `screener_v6.py:693`, returns list or None; do not edit screener_v6)

`mining_macro.py` defines its own EOD helper (does NOT reuse `get_chart`, whose 200-day default and ≥30-row check are wrong for 6-year percentile windows):

```python
def _eod(fmp_func, sym: str, years: int = 6) -> list[tuple[str, float]]:
    """FMP historical-price-eod/full -> [(date, close)] oldest-first, [] on failure."""
```
(`fmp("historical-price-eod/full", {"symbol": sym, "from": today-years, "to": today})`, sort ascending by `date`, keep `(date, float(close))`.)

Series fetched per run (~21 FMP calls, throttled by screener_v6's own `RATE_LIMIT` sleep):

| group | symbols | endpoint |
|---|---|---|
| commodity EOD (6y) | GCUSD SIUSD HGUSD CLUSD PLUSD PAUSD ALIUSD ESUSD DXUSD | `historical-price-eod/full` |
| ETF EOD (6y) | GDX GLD XME URA (+ per-taxonomy `proxy_etf`s not already listed, e.g. COPX REMX SIL) | `historical-price-eod/full` |
| curve (400d) | — | `treasury-rates` `{from,to}` → rows with `year2/year10/year30/month3` (field names proven in `debt_cycle.py:287,301` and `macro_regime.py:174`) |
| CPI (6y) | — | `economic-indicators` `{name:"CPI"}` (endpoint string proven at `weekly_opus_refresh`-adjacent `debt_cycle.py:773`); fallback `{name:"inflationRate"}` |

**CPI note (load-bearing):** FMP `inflationRate` is market-implied expected inflation (~2.3%), NOT realized CPI (~4%) — verified 2026-07-27, see `debt_cycle.py:47-49`. Dial 4 needs **realized CPI YoY**: primary = CPI index series, `cpi_yoy = (cpi_t / cpi_{t-12mo} - 1) * 100` (match month-12 by nearest date ≤ t−350d). Only if the CPI series is empty fall back to `inflationRate` and stamp `"real_rate_basis": "expected_inflation_proxy"` on the dial.

### Shared math (one implementation each, unit-tested)

```python
def _pctile(x: float, hist: list[float]) -> float | None:
    """100 * (#{h<x} + 0.5*#{h==x}) / len(hist); None if len(hist) < 252."""
def _rebase(series, anchor_date) -> list  # closes / close@anchor * 100
def _joint(series_a, series_b) -> list    # inner-join on date, both present
def _chg(series, days) -> float | None    # close[-1]/close[-1-days] - 1 (trading days)
def _dma(series, n) -> float | None
```
Percentile is always **latest value vs its own available joint history** (empirical, no interpolation). When history < 252 joint observations the percentile field is `null` and the dial stamps `"insufficient_history": true` — never a fabricated number.

## 2. The dials (all deterministic; each dial object carries `value`, `asof`, `source: "live"|"cache"|"missing"`, and the fields below)

**D1 — Commodities-to-equities ratio** (the Tavi flagship). Basket = equal-weight of GCUSD, SIUSD, HGUSD, CLUSD each rebased to 100 at the first date all five series (incl. ESUSD) jointly exist within the 6y window; `basket_t = mean(4 rebased closes)`; `ratio_t = basket_t / esusd_rebased_t`. Emit: `level` (latest ratio), `chg_3m_pct` (63 trading days), `chg_12m_pct` (252), `pctile` (latest vs full joint ratio history), `direction` (`"rising"` if chg_3m ≥ +2%, `"falling"` ≤ −2%, else `"flat"`). Display semantics (string shipped in payload as `read`): low percentile = commodities historically cheap vs equities; rising from a low percentile is the Costa setup.

**D2 — Copper/gold ratio** (growth signal). `ratio_t = HGUSD_close / GCUSD_close` (raw, units cancel into a stable scalar). Emit `level`, `chg_3m_pct`, `pctile` (vs 6y), `trend`: `"up"` if 50DMA > 200DMA of the ratio AND chg_3m > 0; `"down"` if 50DMA < 200DMA AND chg_3m < 0; else `"mixed"`. `read`: rising = growth/reflation bid; falling = gold-led defensive/debasement bid.

**D3 — Silver/gold ratio** (debasement risk appetite). `SIUSD/GCUSD`, identical mechanics to D2. `read`: silver outperforming gold = speculative breadth confirming a monetary-metal move; gold-only rallies are the narrow/fear phase.

**D4 — Gold-vs-real-rate divergence** (the debasement tell — **display-only, hard invariant**). Inputs: `gold_yoy_pct = _chg(GCUSD, 252)*100`; `real10y_now = year10_latest − cpi_yoy_latest`; `real10y_1y = year10 (~252 trading days back in treasury-rates history) − cpi_yoy (same month, prior year)`; `real10y_change_pp = real10y_now − real10y_1y`. Classification (exact bands):
- `"debasement_divergence"` — gold_yoy ≥ +10 **and** real10y_change_pp ≥ 0 (gold rallying into flat/rising real rates: the classical anchor is broken; Dalio/Costa monetary-debasement bid);
- `"classical"` — sign(gold_yoy) opposite sign(real10y_change_pp) (textbook inverse relation holding);
- `"neutral"` — everything else.
Payload object must carry `"display_only": true` and `"never_input_to": "debt_cycle scoring"`. This dial exists to be LOOKED AT; the momentum-loop guard in `debt_cycle.py` (gold = falsification check only, `debt_cycle.py:617`) stands, and D4 is likewise excluded from the §4 scoreboard. The `mining_macro.py` docstring restates this.

**D5 — Miners-vs-metal (are equities confirming?)** Two legs:
- `gdx_gld`: raw close ratio GDX/GLD → `level`, `chg_3m_pct`, `pctile` (6y).
- `xme_copper`: XME and HGUSD each rebased to 100 at the joint date 2y back → `level = xme_rb/hg_rb`, `chg_3m_pct`.
Each leg gets `confirmation`: `"confirming"` if chg_3m_pct ≥ +2, `"diverging"` if ≤ −2, else `"flat"`. `read`: metal up while its miners lag = unconfirmed move (paper/late); miners leading = the equity market believes the margin story.

**D6 — Curve.** From the latest `treasury-rates` row: `spread_2s10s_bp = (year10 − year2)*100`; `spread_3m10y_bp = (year10 − month3)*100`; deltas vs the row nearest 63 trading days back (`chg_3m_bp` each). Labels: `"inverted"` (<0), `"flat"` (0–50bp), `"steep"` (>50bp) + `"steepening"/"flattening"` from the delta sign. This deliberately does NOT reproduce `debt_cycle._score_term_premium` (30y−3m, scored) — different tenors, never scored here, display + scoreboard-free.

**D7 — DXY.** DXUSD: `level`, `chg_3m_pct`, `chg_12m_pct`, `trend` (50/200 DMA rule as D2), `pctile` (6y). `read`: falling dollar = broad commodity tailwind.

**D8 — Per-commodity momentum table.** One row per symbol in `[GCUSD, SIUSD, HGUSD, PLUSD, PAUSD, ALIUSD]` + `URA` (uranium proxy — `future_resources_chains.json` uranium block: `fmp_symbol: null, proxy_etf: "URA"`; uranium spot is not on FMP). Row schema:
```json
{"symbol":"GCUSD","label":"Gold","is_proxy":false,
 "mom_12m_pct":..., "mom_3m_pct":..., "pctile_5y":...,
 "off_52wk_high_pct":..., "source":"live"}
```
`pctile_5y` = `_pctile(latest_close, trailing ≤1260 closes)`. URA row carries `is_proxy: true` and `proxy_note: "ETF proxy — carries equity beta, not uranium spot"`. Short-history symbols (PLUSD/PAUSD/ALIUSD if FMP depth is thin) get `pctile_5y: null` via the ≥252-obs rule, momentum still shown if ≥253 closes exist.

## 3. Caching, staleness, fail-open

Local last-known-good cache: `backend/_opus_debate/mining/_commodity_macro_cache.json` — `{ "SERIES": {sym: [[date, close], ...]}, "TREASURY": [...], "CPI": [...], "ASOF": "YYYY-MM-DD" }`, rewritten on every successful gather (local file, no GCS round-trip — this mode runs on the operator machine; GCS carries only the published payload).

Per-series rule on any FMP failure (403 / timeout / empty list — `fmp()` returns None on all of them):
1. cache entry exists and `ASOF` ≤ 14 days old → use it, dial `source: "cache"`, `stale_days: N`;
2. else dial fields `null`, `source: "missing"`.

Payload-level honesty: if ANY dial is non-live, top-level `"degraded": true` and `"stale_banner": "Some dials ride cached data from <ASOF> (FMP outage) — readings may be stale."`; if a dial is `missing`, banner says so per dial name. The /commodities page renders the banner verbatim (honest-banner house rule). **Fail-open:** a missing feed can never worsen any chain's scoreboard standing — see neutral-midpoint rule in §4.5 — and the mode always writes a payload (even fully degraded), exiting 0; it exits non-zero only on filesystem/GCS-push failure (report-and-stop, `fr_publish` precedent).

## 4. The winner scoreboard — 0–100 per Mining chain, deterministic

**Rows come from the Mining taxonomy file, never a hardcoded chain list** (Do-NOT #9, restated in `future_resources_chains.json` `torque_note`). Iterate `chains[*]` of the Mining taxonomy (the basket-split section owns that file; path assumed `backend/_opus_debate/mining_chains.json` — see open questions) and use each chain's `commodity` block: `fmp_symbol` (e.g. HGUSD for copper, GCUSD for precious) or, when null, `proxy_etf` (URA uranium, REMX rare-earth, XME diversified) as the chain's price series.

Four legs, weights fixed and summing to 100:

**4.1 Setup leg — spot-vs-incentive, 30 pts.** Where the Mining regime file (`backend/_opus_debate/mining/regime_state.json`, successor of `backend/_opus_debate/future_resources/regime_state.json`, same schema: per-chain `{state, spot, vs_incentive_pct, as_of}`) carries a numeric `vs_incentive_pct` with `as_of` ≤ 45 days old: linear map `pts = 30 * clamp((0 − vs_incentive_pct + 0) ... )` — concretely `pts = clamp(15 − vs_incentive_pct * 0.5, 0, 30)` so −30% below incentive → 30 pts (max supply-destruction setup), 0% → 15, +30% above → 0. Where `vs_incentive_pct` is null/stale: substitute `pts = (100 − pctile_5y_of_chain_series) * 0.30` and stamp `setup_source: "percentile_proxy"` (cheap-vs-own-history as the incentive stand-in); if the percentile is also null → neutral 15, `setup_source: "missing_neutral"`.

**4.2 Momentum leg — 30 pts.** `mom_pctile` = `_pctile(current 12m return, series of trailing 12m returns computed daily over the last 5y for that symbol)` — i.e. "how strong is today's momentum by this commodity's own standards". `pts = 0.30 * mom_pctile`. Null percentile → 15, `momentum_source: "missing_neutral"`.

**4.3 Miners-confirmation leg — 20 pts.** For chains with BOTH an `fmp_symbol` commodity and a `proxy_etf` (copper: COPX/HGUSD; precious: GDX/GCUSD): 63-day change of the rebased ETF/commodity ratio → ≥ +2% = 20, −2..+2% = 10, ≤ −2% = 0. For proxy-only chains (uranium/URA, rare-earth/REMX, diversified/XME — no independent metal series): fixed 10, `confirmation_source: "n/a_proxy_only"`. Missing data: 10, `"missing_neutral"`.

**4.4 Dalio tilt — 20 pts.** Read `debt_cycle.debt_cycle_phase` from `backend/_opus_debate/macro_regime.json` (published by `_write_macro_regime`; read-only, no state tick), stamp its `asof` as `debt_phase_asof`. Chains classify as **monetary** iff `commodity.monetary_metal: true` in the taxonomy (new boolean the taxonomy section adds to the precious chain; fallback heuristic if absent: `fmp_symbol in {GCUSD, SIUSD}` or `proxy_etf in {GDX, SIL}`), else **industrial**. Module-level table:

```python
PHASE_TILT_POINTS = {          # hand-tuned priors, debt_cycle PHASE_DURATION_CAPS precedent
  "EXPANSION":    {"monetary": 8,  "industrial": 15},
  "DISCIPLINE":   {"monetary": 15, "industrial": 8},
  "FORCING":      {"monetary": 20, "industrial": 4},
  "MONETIZATION": {"monetary": 20, "industrial": 20},
  "UNKNOWN":      {"monetary": 10, "industrial": 10},   # fail-open neutral
}
```

**4.5 Composite + authority.** `score = round(setup + momentum + confirmation + tilt, 1)`, rows sorted descending, each row exposing every leg, every `*_source` stamp, and `confidence: "high"|"med"|"low"` (≥3 legs live / 2 / fewer — `debt_cycle.compute_debt_cycle` precedent). Fail-open is structural: every missing leg pays its exact neutral midpoint (15/15/10/10), so an outage compresses scores toward 50 symmetrically and can never single out a chain. Top-level field, verbatim:

```json
"scoreboard_authority": "Ranks commodity setups for display and Director citation ONLY. Never gates membership, never sizes, never touches conviction. The Mining debate pipeline selects picks."
```

The Mining Director prompt builder may quote scoreboard rows as dated facts; a scoreboard rank is **not** by itself a valid `delta_justification` for a conviction move (same rule as phase citations, `_regime_post._dated_fact_outside_phase` precedent).

## 5. Payload schema (`commodity_macro.json`, all three locations identical)

```json
{
 "version": "mining-macro-v1",
 "generated_at": "YYYY-MM-DD",
 "degraded": false, "stale_banner": null,
 "dials": {
   "commodities_vs_equities": {...D1}, "copper_gold": {...D2},
   "silver_gold": {...D3}, "gold_real_rate_divergence": {...D4, "display_only": true},
   "miners_vs_metal": {"gdx_gld": {...}, "xme_copper": {...}},
   "curve": {...D6}, "dxy": {...D7}
 },
 "momentum_table": [ ...D8 rows... ],
 "scoreboard": [ {"chain_id": "...", "score": 71.5, "legs": {...}, "confidence": "high"} ],
 "scoreboard_authority": "...", "debt_phase": "DISCIPLINE", "debt_phase_asof": "YYYY-MM-DD",
 "sources_note": "FMP only. Uranium via URA ETF proxy (no FMP uranium spot). Gold real-rate dial is display-only and never feeds debt-cycle scoring."
}
```

## 6. Wiring, cadence, CLI, tests

**Dispatch** (in the `__main__` chain at `weekly_opus_refresh.py:4357ff`):
```python
elif mode in ("mining-macro", "mining_macro"):
    mining_macro_publish(push_gcs=("--gcs" in sys.argv), offline=("--offline" in sys.argv))
```
`mining_macro_publish()` (new, in weekly_opus_refresh.py): `import mining_macro; from screener_v6 import fmp` → `doc = mining_macro.build_payload(fmp if not offline else None)` → write `ROOT / "mining" / "commodity_macro.json"` and `E.FRONTEND_DIR / "public" / "commodity_macro.json"` → if `push_gcs`, push to `scans/commodity_macro.json` with the one-retry + live-readback loop copied from `fr_publish`. `--offline` forces an all-cache/degraded build (used by tests and sandbox runs where FMP keys are absent).

**Cadence:** Saturday runbook, one line after `python backend/debt_cycle.py fetch-auctions` and before the Mining debate verbs:
```
python backend/weekly_opus_refresh.py mining-macro --gcs
```
It reads whatever `macro_regime.json` is current (at worst last week's phase — the state machine moves ≤1 step/week, and `debt_phase_asof` makes the vintage explicit). Local Claude Code only; no gcloud scheduler entry, no Cloud Run.

**Module layout of `backend/mining_macro.py`:** pure functions `compute_dials(series_map, treasury_rows, cpi_rows, asof)` and `compute_scoreboard(dials, chains, regime_state, debt_phase)` take plain dicts/lists (zero network — fixture-testable exactly like `debt_cycle.compute_debt_cycle`); `_gather(fmp_func, cache)` does all fetching + cache fallback; `build_payload(fmp_func)` composes; CLI `python backend/mining_macro.py [--offline]` prints the payload.

**Tests:** `backend/tests/test_mining_macro.py` — (1) dial formulas against a canned 6y fixture (known ratios/percentiles); (2) `_pctile` edge cases (<252 obs → None, ties); (3) full-outage run: payload written, `degraded: true`, every scoreboard leg at its neutral midpoint, all chains within tilt-spread of each other — asserts the fail-open invariant "a data gap never singles out a chain"; (4) D4 classification bands incl. the `debasement_divergence` case; (5) proxy-only chains get `confirmation_source: "n/a_proxy_only"` = 10 pts; (6) stale `vs_incentive_pct` (as_of 60d) falls back to `percentile_proxy`. PR-gated (main is branch-protected).

**Invariants restated for the reviewer:** no import edge between `mining_macro.py` and `debt_cycle.py`; D4 is display-only forever; scoreboard = display + citation, never membership/sizing; chains and proxies come from the taxonomy file, never Python constants; payload always writes (fail-open), banners are honest; screener_v6.py is untouched by this section (its single sanctioned change — the nightly-NAV tuples — belongs to the book-split section).
---

## §3. Taxonomy v2.0

# Taxonomy v2.0 — the split

## T.0 Decision: TWO files, not one file with a `basket` field

Ship **`backend/_opus_debate/mining_chains.json`** and **`backend/_opus_debate/fdt_chains.json`** as two standalone taxonomies, both `"version": "2.0"`. Rejected alternative: one file with a per-chain `basket` field.

Rationale (this is the two-books-independently-breakable rule applied to config):

1. **Blast radius.** Every consumer of the v1.3 taxonomy does a bare `json.load` at module/run start (`weekly_opus_refresh.py:1668`, `:1936`; `_resource_metrics.py:62` → `TAX_F`). A malformed edit to a shared file stalls BOTH weekly runs; with two files, a broken `fdt_chains.json` cannot stop the Mining publish. This is exactly the FORK-1/A logic in CLAUDE.md (separate module so one book's plumbing can't silently strip the other's).
2. **Independent version stamps.** `fr_publish` stamps `taxonomy_version` into the payload (`weekly_opus_refresh.py:2652`). Two books, two payloads, two independently-advancing versions — a Mining chain edit must not bump FDT's stamp.
3. **Divergence is expected, not hypothetical.** The floors already want to diverge (SMR/quantum lane-B economics vs producer lane-A economics), and the commodity-block schema diverges immediately (Mining gets `fmp_symbol_secondary`, FDT is mostly `torque_metrics=false`).
4. **Do-NOT #9 carries over per book**: no chain lists/industry strings/anchors hardcoded in Python/JS. Mining code reads ONLY `mining_chains.json`; FDT code reads ONLY `fdt_chains.json`. The single sanctioned cross-reader is the dedup step (§T.4), and it reads the two `universe.json` member lists, never the other taxonomy.

`future_resources_chains.json` stays **byte-identical in the repo at v1.3** — frozen record, same as the retired disruptor taxonomy. Supersession is documented in the new files' `lineage` blocks (§T.1) and in this spec; the old `fr-*` modes become RETIRED no-ops and never load it again.

## T.1 Shared schema (both files) — v1.3 schema + four additions

Both files reuse the v1.3 top-level shape (`version`, `updated`, `exchanges`, `floors`, `chains[]`, `vocab_note`, `torque_note`) verbatim, plus:

```json
{
  "basket": "mining",                        // or "fdt" — self-identification, stamped into every payload
  "lineage": {
    "supersedes": "future_resources_chains.json v1.3 (frozen, never edited)",
    "chain_moves": { "copper_electrification": "split: producer/royalty side -> mining:copper_mining; equipment/utility side -> fdt:electrification_grid" }
  },
  "chains": [ {
     "fmp_industries_verify": ["Gold", "Silver"],   // NEW, optional: subset of fmp_industries not yet proven live.
     "commodity": { "fmp_symbol": "GCUSD", "fmp_symbol_secondary": "SIUSD", "proxy_etf": "GDX", "spot_source": "..." }
  } ]
}
```

- **`fmp_industries_verify`** replaces the v1.0/v1.3 prose-only "(verify)" convention with a machine-readable list. Universe-builder behavior (clone of `fr_universe()`'s per-industry row-count prints): an industry in this list that returns **0 rows prints `WARN industry '<s>' -> 0 rows (unverified string — check /stable/available-industries)`** and the build continues; an industry NOT in this list (proven) that returns 0 rows on a chain with historically ≥3 members **STOPs** (the existing anti-shrink guard). After the first live run confirms a string, remove it from `fmp_industries_verify` (config edit only) — it is then guard-protected like every proven string.
- **`fmp_symbol_secondary`**: second FMP commodity symbol for dual-metal chains (precious metals: GCUSD + SIUSD). `_resource_metrics.py` v2 computes `commodity_beta_2y` against `fmp_symbol` by default and against `fmp_symbol_secondary` when the chain map stamps the name's dominant metal as the secondary (`dominant_metal` field, §T.3); `fcf_torque_10pct` is metal-agnostic (it uses `commodity_revenue_share`).
- **`floors`**: copied VERBATIM from v1.3 into both files — lane_a `{mcap ≥ $500M, ADV ≥ $5M, price ≥ $2}`, lane_b `{mcap ≥ $150M, ADV ≥ $2M, price ≥ $1}`. The two-lane gate structure (FUTURE_RESOURCES_SPEC.md §1.2 — Lane A cash/EBITDA/funded-solvency gates with the royalty bypass, Lane B runway + staleness) applies unchanged in both books.
- **`exchanges`**: `["NYSE","NASDAQ","AMEX"]` in both (AMEX remains the uranium-cohort canary; the `Uranium -> 0` STOP guard moves into the Mining builder unchanged).
- **Physical-anchor rule: BOTH books, unchanged.** The chain-map prompt in both books keeps the v1.3 one-line requirement — name the physical thing the company makes/moves/powers/instruments; no answer ⇒ `chain_fit_confidence=low`, printed drop. Quantum hardware counts; a payments network never does. It binds hardest on FDT's quantum/robotics/grid filters (broadest industries) exactly as before.
- **Max 2 chains per name, per book** (v1.3 rule; UUUU legitimately carries `uranium_fuel_cycle` + `rare_earth_strategic` inside Mining and counts toward both chain caps). Cross-book dual membership is forbidden absolutely (§T.4).

## T.2 `mining_chains.json` — five chains

| # | id | Status | fmp_industries (bold = proven v1.3/live; *(v)* = in `fmp_industries_verify`) | commodity block | Anchor expectations (first-run checklist) |
|---|---|---|---|---|---|
| 1 | `uranium_fuel_cycle` | copied VERBATIM from v1.3 | **Uranium** | `fmp_symbol: null`, `proxy_etf: "URA"`, spot_source: web-cited UxC/Numerco or SRUUF/U.UN trust NAV (uranium spot is NOT on FMP — unchanged) | present: CCJ, UEC, UUUU, LEU, NXE, DNN, UROY |
| 2 | `copper_mining` | copper_electrification's **producer/royalty side** — thesis/keywords/layers copied, minus the equipment layer | **Industrial Materials**, Copper *(v)*, Aluminum *(v)* (both carried over still-unverified from v1.3 — the first live run never happened) | `fmp_symbol: "HGUSD"`, `proxy_etf: "COPX"` (both feed-verified) | present: FCX, SCCO, ERO, HBM, TECK |
| 3 | `precious_metals` | **NEW** — gold/silver producers + royalty/streamers | Gold *(v)*, Silver *(v)*, Other Precious Metals *(v)* — proposed per the stable-vocab pattern in v1.3's `vocab_note`; confirm via `/stable/profile` on NEM (expect Gold), PAAS (expect Silver), WPM/FNV | `fmp_symbol: "GCUSD"`, `fmp_symbol_secondary: "SIUSD"`, `proxy_etf: "GDX"`, note: SIL is the silver-cohort read, displayed on /commodities but not a taxonomy field | present: AEM, NEM, WPM, FNV (WPM/FNV `business_model=royalty_streamer` → auto-pass cash gates, existing bypass) |
| 4 | `rare_earth_strategic` | copied VERBATIM from v1.3 | **Industrial Materials**, **Chemicals - Specialty** | `fmp_symbol: null`, `proxy_etf: "REMX"`, NdPr web-cited (unchanged) | present: MP, USAR, UUUU |
| 5 | `diversified_miners` | **NEW** — BHP/RIO-class multi-commodity majors | **Industrial Materials**, Other Industrial Metals & Mining *(v)* (legacy-string fallback in case BHP/RIO ADR profiles still carry it) — confirm via `/stable/profile` on BHP, RIO, VALE | `fmp_symbol: null`, `proxy_etf: "XME"` (feed-verified), `torque_metrics: true` — beta runs vs the proxy_etf (the existing off-FMP-commodity path), fcf_torque uses per-name `commodity_revenue_share` which for diversifieds is REQUIRED from the chain map, never defaulted to 1.0 (v1.3 TECK note, now load-bearing) | present: BHP, RIO, VALE; TECK may carry `copper_mining` + `diversified_miners` (legal 2-chain within book) |

**Absent-list assertion (Mining first-run checklist): V, JPM, and any ETN/HUBB-class equipment name must NOT appear.** An equipment name in a Mining universe is a split-rule failure (§T.4), printed and dropped.

Mining thesis framing (for the two NEW chain `thesis` strings): precious_metals — "monetary-debasement + central-bank-bid regime meets a decade of reserve depletion; producers gear FCF to the gold/silver price, royalties gear without the capex" (Dalio/Costa framing lives on the /commodities macro layer, NOT in scoring — gold stays falsification-only inside `debt_cycle.py`, displayed-as-data on the page); diversified_miners — "the BHP/RIO class is the cash-returning, low-cost-quartile backbone of the basket; the cycle read is capital discipline vs the capex cycle, not any single metal".

## T.3 `fdt_chains.json` — five chains

| # | id | Status | fmp_industries | commodity block | Anchor expectations |
|---|---|---|---|---|---|
| 1 | `electrification_grid` | **NEW cohort assembly** — copper_electrification's **equipment side** + power_for_ai's grid-equipment layer | **Electrical Equipment & Parts**, **Industrial - Machinery**, **Engineering & Construction** (all proven v1.3) | `fmp_symbol: null`, `proxy_etf: "GRID"` *(v — batch-quote it on first run; standard ETF, expected quotable)*, `torque_metrics: false` — equipment makers are backlog/margin stories, not spot-levered; copper is an input COST here. Non-commodity metric set (gm_trajectory/rev_yoy/fcf_margin/ndebt_ebitda) per the v1.3 `torque_note` mechanism | present: ETN, HUBB, nVent/AZZ-class; PWR may straddle with power_for_ai (2-chain within book, recommendation: PWR primary here is wrong — keep PWR primary `power_for_ai`, its EPC/interconnection revenue is a power-delivery play) |
| 2 | `nuclear_smr` | **NEW chain** — SMR/advanced-reactor developers + nuclear component/fuel-services equipment | **Industrial - Machinery**, **Independent Power Producers**, Aerospace & Defense *(v — BWXT's expected filing)*, Regulated Electric *(v — OKLO-class check)* — confirm via `/stable/profile` on BWXT, SMR, OKLO | `fmp_symbol: null`, `proxy_etf: "NLR"` *(v)*, `torque_metrics: false`; spot_source: "no spot — the regime read is the NRC/COL dateline track + datacenter-PPA flow; uranium is Mining's business" | present: BWXT (lane A), SMR, OKLO, NNE-class (lane B). **Lane-B-heavy BY DESIGN**: SMR developers are pre-FCF; they enter via dated NRC/COL/first-concrete milestones under the unchanged lane-B runway gate. A thin lane A (BWXT-class only) is the expected outcome, not a failure — the v1.3 quantum precedent verbatim |
| 3 | `power_for_ai` | carried from v1.3, **minus** the grid-equipment layer (→ chain 1) and the SMR-developers layer (→ chain 2); id UNCHANGED so regime/ledger keys survive | **Independent Power Producers**, **Renewable Utilities**, **Industrial - Machinery**, **Engineering & Construction** (proven; drops Electrical Equipment & Parts — that's chain 1's screen now) | unchanged: `fmp_symbol: "NGUSD"`, `proxy_etf: null`, Henry-Hub-as-fuel-cost note; torque = margin-vs-power-prices | present: GEV, CEG, VST, TLN, PWR |
| 4 | `robotics_automation` | copied VERBATIM from v1.3 (incl. `torque_metrics: false`) | as v1.3 (all proven) | `proxy_etf: "BOTZ"`, unchanged | present: ISRG, TER, ROK, CGNX, SYM |
| 5 | `quantum` | copied VERBATIM from v1.3 (incl. `torque_metrics: false`; **stays lane-B heavy** — IONQ/RGTI/QBTS-class pre-FCF via dated awards/EC milestones; tiny FORM/COHR-class lane A is the designed outcome) | as v1.3 | `proxy_etf: "QTUM"`, unchanged | present: IONQ-class lane B, FORM/COHR-class lane A |

**Absent-list assertion (FDT first-run checklist): V, JPM absent; FCX/SCCO/any producer absent** (a producer in an FDT universe is a split-rule failure, printed and dropped).

## T.4 The split rule, straddlers, and cross-book dedup

**business_model enum extends** (chain-map required field, both books): `producer | royalty_streamer | developer | equipment_services | utility` (v2.0 adds `utility` — CEG/VST-class IPPs were awkwardly `equipment_services` in v1.3).

**Deterministic split rule for the old `copper_electrification` cohort** (and any future overlap):

- `producer` or `royalty_streamer` → Mining (`copper_mining`).
- `equipment_services` or `utility` → FDT (`electrification_grid` / `power_for_ai`).
- `developer` → the book whose chain the developed PHYSICAL ASSET belongs to (a copper-mine developer → Mining; an SMR developer → FDT). Each book's map runs against its own taxonomy, so developers land where they screen; the rule only arbitrates overlaps.

**How the re-run implements it.** There is no migration script — anti-shrink forbids sourcing from prior universe files. Each book's monthly builder (`mining-universe` → `mining-map-merge`, `fdt-universe` → `fdt-map-merge`, clones of `fr_universe()`/`fr_map_merge()`) rebuilds from a fresh FMP screen against its OWN taxonomy. The split is then enforced twice, deterministically:

1. **In-book sanity check at map-merge** (extends the existing "a `developer` in lane A is a mapping error" check): a `producer`/`royalty_streamer` mapped into any FDT chain, or an `equipment_services`/`utility` mapped into any Mining chain, is a **mapping error — printed with symbol + business_model + chain, and dropped**. Royalty bypass note: `royalty_streamer` is a legal business_model ONLY in Mining chains.
2. **Cross-book dedup — new mode `basket-dedup`** (`python backend/weekly_opus_refresh.py basket-dedup`, rides the existing allowlist wildcard), run after BOTH map-merges in the monthly sequence. It reads both books' `universe.json` member lists (the only sanctioned cross-book read; taxonomies are never cross-read), computes the symbol intersection, and for each straddler (e.g. a copper producer with a grid-equipment arm, screened into both via `Copper` + `Electrical Equipment & Parts`):
   - **Primary basket by revenue share**: the chain map in each book already stamps `commodity_revenue_share`; producer-side share ≥ 0.5 → Mining wins; < 0.5 → FDT wins.
   - **Pre-revenue straddler**: resolve by the physical-anchor line — extraction of a commodity → Mining; a machine/plant → FDT.
   - **Ties and genuinely-undeterminable → Mining wins.** Justification: producer revenue is the hardest-to-fake physical anchor, and the Mining book's torque metrics + commodity regime layer explicitly price the commodity exposure the name carries either way; seating it in FDT would smuggle unlabeled commodity beta into a book whose stress axes don't decompose it.
   - The loser is REMOVED from its `universe.json` (funnel stamped `deduped_out: N`, symbols printed), and one row is appended to **`backend/_opus_debate/_basket_dedup_log.jsonl`** (append-only tracker: `{date, symbol, winner, loser, revenue_share, reason}`). Re-derived from scratch every monthly rebuild — the log is audit trail, never an input.
   - **Fail-open**: if either `universe.json` is missing/unparseable, `basket-dedup` WARNs and no-ops — a data gap must never drop names from either book.
3. **Publish-time backstop** (both books' post layers): assert the about-to-publish pick set has empty intersection with the other book's latest published payload symbol set. Non-empty → **STOP, do not publish** (Do-NOT #10 discipline — a name is NEVER seated in both books simultaneously, whatever upstream missed). Other payload unreadable → WARN and publish (fail-open).

## T.5 Acceptance for this section

1. Both JSONs parse; each has `basket`, `lineage`, `floors` byte-equal to v1.3's, 5 chains, and every `fmp_industries_verify` entry is a subset of its chain's `fmp_industries`.
2. `future_resources_chains.json` is byte-identical to v1.3 after the build (git diff clean on that path).
3. Synthetic tests: (a) a fake `producer` injected into an FDT chain at map-merge prints + drops; (b) a symbol planted in both `universe.json`s with `commodity_revenue_share: 0.5` dedups to Mining with a printed row and a `_basket_dedup_log.jsonl` append; (c) deleting one `universe.json` makes `basket-dedup` WARN + no-op; (d) the `Uranium -> 0` STOP still trips in the Mining builder when AMEX is removed.
4. First live run: every `fmp_industries_verify` string either returns rows or prints the 0-row WARN with the string named; anchor spot-checks per the tables above (incl. the absent-lists) pass; strings confirmed live get removed from `fmp_industries_verify` as a config-only edit.
---

## §4. Pipeline v2

# Pipeline v2 — two books from the fr-* machinery

## 0. Scope

This section converts the single-book Future Resources (FR) pipeline in `backend/weekly_opus_refresh.py` (the `fr_universe / fr_map / fr_map_merge / fr_prep / fr_input / fr_numeric_gate / fr_post / fr_csv / fr_publish` chain plus `backend/_opus_debate/_fr_post.py`) into ONE shared, book-parameterized implementation driving TWO independent books — **MINING** and **FUTURE DISRUPTIVE TECH (FDT)** — and retires the `fr-*` modes as no-ops with the FR record frozen in place. Membership stays 100% Director-decided; everything parameterized here is deterministic plumbing (paths, caps, stamps, benchmarks, prompts). No Cloud Run involvement anywhere: every mode below runs only in local Claude Code sessions, published via `--gcs` from the operator's machine (existing `fr_publish` gcloud-subprocess pattern, unchanged).

Working-directory note (matters for every path below): `weekly_opus_refresh.py` runs from `backend/` with `ROOT = Path("_opus_debate")`; `_fr_post.py` does `os.chdir(BK)` itself. All new subtrees live under `backend/_opus_debate/`.

## 1. The BOOKS registry

Add near the current `FR_DIR` block (`weekly_opus_refresh.py` ~line 1647), replacing the module-level `FR_DIR/FR_INP/FR_TXT/FR_RES/FR_DOSS/FR_ARCH` constants with per-book derivation:

```python
def _book_paths(d):
    return {"dir": d, "inp": d / "inputs", "txt": d / "transcripts",
            "res": d / "results", "doss": d / "dossiers", "arch": d / "_archive_prev"}

BOOKS = {
  "mining": {
    "key": "mining",
    **_book_paths(ROOT / "mining"),                       # backend/_opus_debate/mining/
    "taxonomy": ROOT / "mining_chains.json",
    "signal_type": "mining",
    "workflow_name": "speculair-mining-weekly",
    "workflow_brief": MINING_BRIEF,
    "apex_file": "apex_basket_mining.json",
    "grade_input": "mining_grade_input.json",
    "prompt_file": "mining_director_prompt.txt",
    "director_prompt": MINING_DIRECTOR_PROMPT,
    "ledger_book": "mining",                              # -> _director_ledger_mining.txt + _ledger.py history key
    "payload_local": "speculair_mining.json",             # frontend/public/ + GCS scans/
    "payload_gcs": "scans/speculair_mining.json",
    "tracking_local": "speculair_mining_tracking.json",
    "tracking_gcs": "scans/speculair_mining_tracking.json",
    "tracking_weighted_local": "speculair_mining_tracking_weighted.json",
    "tracking_weighted_gcs": "scans/speculair_mining_tracking_weighted.json",
    "embed_key": "mining_tracking",
    "memo_key": "mining_memo",
    "engine": "opus-5-mining-v1",
    "post_stamp": "mining_post_applied",
    "benchmark_legs": {"XME": 0.5, "GDX": 0.5},
    "benchmark_label": "50/50 XME+GDX",
    "beta_bench": ["XME", "GDX"],                         # _fr_post book-level regression benches
    "chain_caps": {"max_names": 3, "max_weight": 0.30},
    "min_lane_a": 25,
    "canary_chain": "uranium_fuel_cycle",                 # the AMEX-cohort canary (unchanged semantics)
    "csv_name": "speculair_mining_apex.csv",
    "macro_file": "commodity_macro.json",                 # CITED-ONLY macro layer (mining only)
    "banner": ("Commodity-cyclical MINING sleeve (split from Future Resources 2026-07-27; fresh NAV, "
               "no back-fill). Never blended with any other book. US-listed names only."),
  },
  "fdt": {
    "key": "fdt",
    **_book_paths(ROOT / "fdt"),
    "taxonomy": ROOT / "fdt_chains.json",
    "signal_type": "future_disruptive_tech",
    "workflow_name": "speculair-fdt-weekly",
    "workflow_brief": FDT_BRIEF,
    "apex_file": "apex_basket_fdt.json",
    "grade_input": "fdt_grade_input.json",
    "prompt_file": "fdt_director_prompt.txt",
    "director_prompt": FDT_DIRECTOR_PROMPT,
    "ledger_book": "fdt",
    "payload_local": "speculair_fdt.json",
    "payload_gcs": "scans/speculair_fdt.json",
    "tracking_local": "speculair_fdt_tracking.json",
    "tracking_gcs": "scans/speculair_fdt_tracking.json",
    "tracking_weighted_local": "speculair_fdt_tracking_weighted.json",
    "tracking_weighted_gcs": "scans/speculair_fdt_tracking_weighted.json",
    "embed_key": "fdt_tracking",
    "memo_key": "fdt_memo",
    "engine": "opus-5-future-disruptive-tech-v1",
    "post_stamp": "fdt_post_applied",
    "benchmark_legs": {"GRID": 0.5, "QQQ": 0.5},
    "benchmark_label": "50/50 GRID+QQQ",
    "beta_bench": ["GRID", "QQQ"],
    "chain_caps": {"max_names": 3, "max_weight": 0.30},
    "min_lane_a": 20,                                     # see §8 rationale
    "canary_chain": "robotics_automation",                # deepest FDT chain; 0 mapped names = screen failure
    "csv_name": "speculair_fdt_apex.csv",
    "macro_file": None,                                   # FDT gets NO commodity macro layer
    "banner": ("FUTURE DISRUPTIVE TECH sleeve (split from Future Resources 2026-07-27; fresh NAV, "
               "no back-fill). Never blended with any other book. US-listed names only."),
  },
  "fr": {   # LEGACY / FROZEN — reachable ONLY under ALLOW_FR=1 (forensic re-runs). Preserves every
            # current path/constant byte-for-byte so a forensic run reproduces the frozen record.
    "key": "fr", **_book_paths(ROOT / "future_resources"),
    "taxonomy": ROOT / "future_resources_chains.json", "signal_type": "future_resources",
    "workflow_name": "speculair-future-resources-weekly", "workflow_brief": FR_BRIEF,
    "apex_file": "apex_basket_fr.json", "grade_input": "fr_grade_input.json",
    "prompt_file": "fr_director_prompt.txt", "director_prompt": FR_DIRECTOR_PROMPT,
    "ledger_book": "fr", "payload_local": "speculair_future_resources.json",
    "payload_gcs": "scans/speculair_future_resources.json",
    "tracking_local": "speculair_future_resources_tracking.json",
    "tracking_gcs": "scans/speculair_future_resources_tracking.json",
    "tracking_weighted_local": "speculair_future_resources_tracking_weighted.json",
    "tracking_weighted_gcs": "scans/speculair_future_resources_tracking_weighted.json",
    "embed_key": "fr_tracking", "memo_key": "fr_memo", "engine": "opus-5-future-resources-lane-a-v1",
    "post_stamp": "fr_post_applied", "benchmark_legs": {"XME": 0.5, "URA": 0.5},
    "benchmark_label": "50/50 XME+URA", "beta_bench": ["XME", "URA"],
    "chain_caps": {"max_names": 3, "max_weight": 0.30}, "min_lane_a": 25,
    "canary_chain": "uranium_fuel_cycle", "csv_name": "speculair_fr_apex.csv", "macro_file": None,
    "banner": "FROZEN RECORD — retired 2026-07-27.",
  },
}
```

**Registry invariant (unit-tested, §11):** across all three entries, every `payload_*`, `tracking_*`, `dir`, `apex_file`-resolved path and `embed_key` is pairwise distinct. Books are never blended; a path collision is a spec bug caught at test time, not publish time.

## 2. Shared implementation — the mechanical refactor

Each `fr_*` function becomes a book-generic function taking `bk` (a `BOOKS` entry) as its first argument. The bodies are the EXISTING bodies with hardcoded constants swapped for registry fields — no logic changes beyond the deltas called out below:

| Current | New | Substitutions (beyond `FR_DIR/FR_INP/FR_TXT/FR_RES/FR_DOSS/FR_ARCH` → `bk["dir"]/["inp"]/…`) |
|---|---|---|
| `fr_universe()` | `book_universe(bk)` | taxonomy path → `bk["taxonomy"]`; `_gates_cache.json` per subtree (`bk["dir"]/"_gates_cache.json"`); the uranium canary guard (line ~1718) → `bk["canary_chain"]` (message parameterized) |
| `fr_map()` / `fr_map_merge()` | `book_map(bk)` / `book_map_merge(bk)` | `_candidates.json`, `_map_chunk_*.json`, `_fr_map.js` → `bk["dir"]/f"_{bk['key']}_map.js"`; universe output `bk["dir"]/"universe.json"` |
| `_fr_redebate_triggers(members)` | `_book_redebate_triggers(bk, members)` | held/thesis-break read `E.FRONTEND_DIR/"public"/bk["payload_local"]` |
| `fr_prep()` | `book_prep(bk)` | thin-book floor `bk["min_lane_a"]` (currently hardcoded 25 at line ~2169); held-name read → `bk["payload_local"]`; regime sidecar → `bk["dir"]/"regime_state.json"` (already per-subtree — no change needed beyond the dir swap); `signal_type` in bundles → `bk["signal_type"]`; workflow render → `bk["dir"]/f"_{bk['key']}_debate.js"` with `__BOOK_NAME__`/`__SIGNAL_TYPE__`/`__BRIEF__` placeholders added to `_FR_WORKFLOW_TEMPLATE` (renamed `_BOOK_WORKFLOW_TEMPLATE`; the current FR brief text moves to the `FR_BRIEF` constant); torque metrics call → `RM.compute(..., taxonomy=bk["taxonomy"])` |
| `fr_input()` | `book_input(bk)` | grade-input file → `bk["grade_input"]`; prompt file → `bk["prompt_file"]`; prompt constant → `bk["director_prompt"]`; ledger → `write_director_ledger(bk["ledger_book"], bk["dir"]/bk["apex_file"], E.FRONTEND_DIR/"public"/bk["tracking_local"])`; **mining-only macro injection, §6** |
| `fr_numeric_gate()` | `book_numeric_gate(bk)` | `NG.run(..., res_dir=bk["res"])` — `_numeric_gate.py` itself is NOT edited (the `res_dir` injection point already exists) |
| `fr_csv()` | `book_csv(bk)` | apex file, grade input, csv/memo outputs (`bk["csv_name"]`, `f"{bk['key']}_apex_memo.txt"`); memo key → `bk["memo_key"]` |
| `fr_publish(push_gcs)` | `book_publish(bk, push_gcs)` | post-stamp gate → `bk["post_stamp"]`; chain caps → `bk["chain_caps"]` (currently hardcoded `30.0`/`3` at lines ~2601-2602); `append_decision_history(bk["ledger_book"], apx)`; tracking paths/GCS keys/weighted variants → registry; payload dict keys: picks stay under **`apex_basket`** (the `_mark_speculair_nav` contract), tracking under `bk["embed_key"]` + `f"{bk['embed_key']}_weighted"`, memo under `bk["memo_key"]`; `engine` → `bk["engine"]`; banner → `bk["banner"]`; **benchmark block → §7** |

`_ledger.py`, `live_debate_engine._update_apex_tracking`, `write_director_ledger`, `append_decision_history` are already book-string-keyed — **zero edits** there. The dumped engine system prompts (`interrogator_system.txt` etc.) are written per subtree exactly as today.

`backend/_opus_debate/_resource_metrics.py`: change `TAX_F` from a module constant to a `compute(members, offline=False, taxonomy=None)` parameter defaulting to the existing `future_resources_chains.json` path (backwards-compatible; the Do-NOT #9 "never hardcode the chain list in Python" rule is preserved — the split is pure taxonomy data).

## 3. `_fr_post.py` — book parameterization

`backend/_opus_debate/_fr_post.py` gains a required `--book mining|fdt|fr` argv (no default — an unflagged run prints usage and exits 1, so a stale muscle-memory invocation can never stamp the wrong book). A small `_POST_BOOKS` dict at the top of the file replaces the `FRD/APEX_F/GIN_F/RES_DIR/CACHE_F/BETA_BENCH` constants:

```python
_POST_BOOKS = {
  "mining": {"dir": ROOT/"mining",           "apex": "apex_basket_mining.json",
             "gin": "mining_grade_input.json", "cache": "_mining_post_cache.json",
             "beta_bench": ["XME", "GDX"], "stamp": "mining_post_applied"},
  "fdt":    {"dir": ROOT/"fdt",              "apex": "apex_basket_fdt.json",
             "gin": "fdt_grade_input.json",  "cache": "_fdt_post_cache.json",
             "beta_bench": ["GRID", "QQQ"], "stamp": "fdt_post_applied"},
  "fr":     {"dir": ROOT/"future_resources", "apex": "apex_basket_fr.json",
             "gin": "fr_grade_input.json",   "cache": "_fr_post_cache.json",
             "beta_bench": ["XME", "URA"],  "stamp": "fr_post_applied"},
}
```

All existing mechanics are shared unchanged: `enforce_chain_caps` (≤3 names AND ≤30% units per chain, 2-chain names count toward both), `stamp_gate_caps` (growth_capex clamp 0.75, torque×leverage quadrant clamp 0.75, unjustified-HEADWIND clamp 0.5), no skeptic tier, `_post_common` weights/stress/correlation/exits/wheel delegation, `--offline` idempotency. The final stamp writes `_POST_BOOKS[book]["stamp"]`. `stamp_gate_caps`' torque-quadrant check is a no-op for FDT rows where `torque_metrics=false` (fields are None — the existing `isinstance` guards already handle this; no code change).

**Mining-only addition — `warn_macro_as_conviction(picks)`:** a WARN-only textual check (mirroring the spirit of `_regime_post._dated_fact_outside_phase`, which is NOT touched): if any pick's `decision_rationale` or `headwind_justification` matches `r"(?i)dalio|macro setup|commodity winner|tilt table|scoreboard"` without also containing a digit-bearing dated fact, print a loud WARN naming the seat. Advisory only — it never mutates `size_units`, never demotes (macro reaches weights via caps/stance, never conviction; a violation is an operator-review flag, not a deterministic rewrite of Director text). Wired only when `--book mining`.

`_post_common.py`, `_disruptor_post.py`, `_value_post.py`, `_regime_post.py` are **NOT edited** (standing Do-NOT).

## 4. Modes, dispatch, and the FR retirement guard — exact ordering

New modes (each a thin dispatch to the shared functions): `mining-universe`, `mining-map`, `mining-map-merge`, `mining-prep`, `mining-input`, `mining-numeric-gate`, `mining-post`, `mining-csv`, `mining-publish` — and the nine `fdt-*` mirrors. Underscore variants accepted like today (`mode in ("mining-prep", "mining_prep")`). `mining-post`/`fdt-post` run `subprocess([sys.executable, ROOT/"_fr_post.py", "--book", "mining"] + (["--offline"] if ...))` exactly like the current `fr-post` branch.

The `__main__` block ordering is load-bearing. Exact structure:

```python
mode = sys.argv[1] if len(sys.argv) > 1 else "prep"
_norm = mode.replace("_", "-")
# GUARD 1 — disruptor retirement (EXISTING, byte-for-byte unchanged): startswith("disruptor") -> exit 0
if _norm.startswith("disruptor"):
    ...existing message...; sys.exit(0)
# GUARD 2 — FR retirement (NEW, 2026-07-27 split). MUST sit AFTER the disruptor guard and BEFORE
# the first `if mode == "prep"` of the dispatch chain. The test is exactly `== "fr"` or
# startswith("fr-") — NEVER bare startswith("fr") — so no current or future mode
# ("mining-*", "fdt-*", a hypothetical "fresh-*") can ever be shadowed by it, and conversely a
# typed fr-* command can never fall through into a new-book branch.
if (_norm == "fr" or _norm.startswith("fr-")) and os.environ.get("ALLOW_FR") != "1":
    print("FUTURE RESOURCES BOOK RETIRED 2026-07-27 (split into MINING + FUTURE DISRUPTIVE TECH; "
          "FUTURE_RESOURCES_SPLIT_SPEC.md) — mode '%s' is a no-op. The FR payload/NAV/tracking are a "
          "FROZEN RECORD (disruptor precedent): never marked, never back-filled. Use mining-* / fdt-*. "
          "Forensic re-runs against the frozen subtree: ALLOW_FR=1." % mode)
    sys.exit(0)                                    # exit 0: a retired mode is not an error (disruptor precedent)
if mode == "prep":
    ...
elif mode in ("mining-universe", "mining_universe"): book_universe(BOOKS["mining"])
...                                                # all mining-*/fdt-* branches
elif mode in ("fr-universe", "fr_universe"): book_universe(BOOKS["fr"])   # KEPT — reachable ONLY via ALLOW_FR=1
...                                                # all fr-* branches kept for forensic use
```

Difference from the disruptor guard: the disruptor code was deleted (its escape hatch is dead); the fr-* branches STAY, rewired to `BOOKS["fr"]`, so `ALLOW_FR=1 python backend/weekly_opus_refresh.py fr-csv` reproduces the frozen book's CSV. `ALLOW_FR=1` must never be set in any scheduled task or doc example — forensic-only, interactive-only.

## 5. Taxonomy split — two new data files (no Python chain knowledge)

Split `backend/_opus_debate/future_resources_chains.json` (v1.3, chains: uranium_fuel_cycle, copper_electrification, rare_earth_strategic, power_for_ai, robotics_automation, quantum) into two same-schema files (both `"version": "2.0"`, same `floors`/`exchanges` blocks, per-chain `fmp_industries`/`torque_metrics`/`proxy_etf`/`fmp_symbol` fields):

- **`mining_chains.json`** — `uranium_fuel_cycle` (carried verbatim, incl. proxy_etf URA), `copper_mining` (the mining-side split of `copper_electrification`: keep the miner industries, drop electrical-equipment industries; commodity HGUSD), `precious_metals` (NEW: gold/silver producers + royalty/streamers; commodities GCUSD/SIUSD, proxy_etf GDX; the existing royalty-gate-bypass machinery applies as-is via the `royalty_hint`/`business_model` path), `rare_earth_strategic` (carried), `diversified_miners` (NEW: BHP/RIO-class; proxy_etf XME; `torque_metrics: true` with commodity basket beta vs XME labeled proxy). All five `torque_metrics: true`.
- **`fdt_chains.json`** — `electrification_grid` (the equipment side of old copper_electrification: electrical equipment/grid industries; `torque_metrics: false` → gm_trajectory/rev_yoy/fcf_margin set, proxy_etf GRID), `nuclear_smr` (NEW chain; `torque_metrics: false`; note in the chain's `verify` block that pure-play SMR developers (OKLO-class) fail the Lane A EBITDA gate and land in Lane B — Lane A SMR seats come from profitable nuclear-supply-chain names, BWXT-class), `power_for_ai` (carried, keeps NGUSD torque), `robotics_automation` (carried), `quantum` (carried).

`future_resources_chains.json` is left in place untouched (the frozen `BOOKS["fr"]` entry and `_resource_metrics`' default still point at it).

## 6. Director prompts

Two new module-level constants beside `FR_DIRECTOR_PROMPT` (line ~629, which stays for forensic runs):

**`MINING_DIRECTOR_PROMPT`** = the FR rubric re-scoped to the five mining chains, output path `backend/_opus_debate/mining/apex_basket_mining.json`, ledger `_director_ledger_mining.txt`, memo key `mining_memo` — all four pillars, symmetric-torque rule, chain caps, HEADWIND rule, commodity-factor stress (global-growth + China-demand axis now joined by a **gold/real-rate axis** across precious_metals seats), rotation discipline: unchanged mechanics. **Plus the MACRO LAYER paragraph:**

> COMMODITY MACRO LAYER (CITED-ONLY). `backend/_opus_debate/mining/commodity_macro.json` carries the /commodities macro scoreboard — per-commodity macro-setup scores ("commodity winners") and the Dalio tilt table — built by the deterministic macro job (separate spec section owns its schema). You MAY cite it in `entry_posture` (e.g. tightening a wait_for_weakness on a macro-rich commodity), in horizon language, and in the memo's color. You MUST NOT move `fr_score`, `size_units`, or membership on it; a macro citation is NOT a valid `decision_rationale` for ADD/DROP/KEEP and NOT a valid `headwind_justification` (name-specific dated facts only — the `_regime_post._dated_fact_outside_phase` principle, enforced here as a WARN by the post layer). Macro reaches this book ONLY through stance, the entry-discount floor, and horizon — the FORK-2/B wiring. If the block below says UNAVAILABLE, proceed on `chain_regime` alone.

`book_input(BOOKS["mining"])` appends after the correlation block: if `mining/commodity_macro.json` exists and its `as_of` is <15 days old, the verbatim scoreboard + tilt table under the header `COMMODITY MACRO (CITED-ONLY, as of <date>)`; else the single line `COMMODITY MACRO LAYER UNAVAILABLE this run — proceed on chain_regime alone.` **Fail-open: a missing/stale macro file never STOPs, never tightens anything.**

**`FDT_DIRECTOR_PROMPT`** = the FR rubric minus the mining chains, **gm_trajectory-weighted**: pillar 1 scores every chain on the non-commodity set (`gm_trajectory` as the pricing-power lie detector, `rev_yoy`, `fcf_margin`) — except power_for_ai seats may still carry the NG-linked torque read where `_resource_metrics` computed one; pillar 2 (contracting/reserve) becomes **backlog & milestone quality**: order-book/backlog vs revenue, utility-capex exposure (grid), NRC/regulatory milestones with dates (nuclear_smr), named customer deployments (robotics/quantum); pillars 3-4 (capital discipline, valuation guard) unchanged. Shared-axis stress replaces the commodity-factor stress: global-growth + industrial-capex (grid + robotics), hyperscaler-PPA appetite (power_for_ai + nuclear_smr — the new cross-chain pair, flag it explicitly), long-duration-multiple/rate axis (quantum + robotics). No commodity macro layer — `macro_file: None`. Output `backend/_opus_debate/fdt/apex_basket_fdt.json`, ledger `_director_ledger_fdt.txt`, memo `fdt_memo`.

## 7. Benchmarks and the sidecar anchors

Benchmark mechanics are the existing `fr_publish` sidecar pattern, parameterized: anchors persist in `bk["dir"]/"_benchmark_anchors.json"`, stamped at FIRST publish from live `E._current_prices(set(bk["benchmark_legs"]))`, measured-forward only, never back-filled, never stored in the tracking file (the `_update_apex_tracking` wipe documented at lines 2671-2676 — keep that comment). The blend return generalizes to `sum(w*100*(px/anchor-1) for leg, w in legs.items())`. Best-effort try/except stays: a missing leg quote prints WARN and omits the benchmark block — **it never blocks publish (fail-open)**.

- **Mining = 50/50 XME+GDX, not XME+URA.** URA was half the FR benchmark because uranium was the flagship of a 4-commodity-chain book. In the Mining book uranium is one chain of five, while the NEW precious-metals chain (producers + royalties, GDX's exact constituency incl. FNV/WPM/RGLD) and diversified miners have no URA representation at all — keeping URA would grade a 5-chain book against a single chain and structurally flatter/punish it on uranium beta alone. XME covers the diversified/copper/industrial-metals complex; GDX covers precious metals. Uranium beta is NOT lost: URA remains the uranium chain's `proxy_etf` inside `_resource_metrics` (chain-level beta read, unchanged).
- **FDT = 50/50 GRID+QQQ.** GRID (First Trust Smart Grid Infrastructure — ETN/ABB/HUBB/PWR class) is the electrification-equipment complex, the book's largest industrial axis, with power/nuclear adjacency; QQQ carries the long-duration-tech-multiple axis (the discount-rate beta of robotics/quantum/AI seats) — the same role it played in the disruptor's SMH/QQQ blend. **SMH rejected:** FDT deliberately holds no semiconductor chain (power-for-AI is power infrastructure, not chips); an SMH leg would benchmark the book against a factor it does not own. Both legs are standard US-listed ETFs (FMP batch-quote verified class).
- **FR's `future_resources/_benchmark_anchors.json` freezes in place** — never read or rewritten by the new books.

## 8. Regime sidecars — per-book split, protocol unchanged

- `backend/_opus_debate/mining/regime_state.json` — chains: uranium_fuel_cycle, copper_mining, precious_metals, rare_earth_strategic, diversified_miners.
- `backend/_opus_debate/fdt/regime_state.json` — chains: electrification_grid, nuclear_smr, power_for_ai, robotics_automation, quantum.
- Companion docs `MINING_REGIME.md` + `FDT_REGIME.md` at repo root (structural clones of `FUTURE_RESOURCES_REGIME.md`, which gets a one-line RETIRED/frozen banner prepended and is otherwise untouched).
- **Cadence unchanged:** the ONE existing bi-weekly local scheduled task (the catalyst-watch-regime-refresh clone, ≥13-day self-gating floor) is repointed to write BOTH sidecars + both docs in the same session. No new scheduled task.
- **Seeding at cutover (fail-open):** carried chains inherit the current FR sidecar verdict (copper_electrification's read seeds BOTH copper_mining and electrification_grid); NEW chains (precious_metals, diversified_miners, nuclear_smr) seed `{"state": "NEUTRAL", "one_liner": "unseeded — first bi-weekly refresh pending", "as_of": <cutover date>}`. Never seed HEADWIND from absence — a missing read must not tighten a book, and the existing `book_prep`/`book_input` default of `"NEUTRAL"` for absent chains already backstops this.
- `min_lane_a`: mining keeps 25 (five deep chains). FDT is recommended **20** — quantum + nuclear_smr Lane A (profitable, EBITDA-positive) cohorts are structurally thin; a 25 floor would likely dead-lock the maiden book. The floor is a registry field precisely so Bruno can retune it after the first `fdt-universe` funnel prints.

## 9. FR freeze mechanics + nightly NAV (`screener_v6.py`)

**Cutover checklist, in order:**
1. **One final honest-banner write (the last FR write, ever):** under `ALLOW_FR=1`, download `scans/speculair_future_resources.json`, set `pool_stats.banner` and a top-level `"retired": {"date": "2026-07-27", "note": "FROZEN RECORD — split into Mining + Future Disruptive Tech. NAV frozen at last mark; never back-filled; successor books started fresh."}`, re-upload once. Mirror into `frontend/public/` if the local copy exists.
2. **`backend/screener_v6.py` `_mark_speculair_nav()` (line 6908 tuple list) — the ONLY screener_v6 edit, exactly the sanctioned one-tuple-per-new-book:** REMOVE the `("future_resources", ...)` tuple (freezing means the nightly mark stops; the tracking files in GCS/`frontend/public` become the frozen record — the disruptor precedent, whose tracking files still sit in `frontend/public` untouched and unlisted in this loop) and ADD:
```python
("mining", "scans/speculair_mining.json", "scans/speculair_mining_tracking.json",
 "speculair_mining_tracking.json", "mining_tracking"),
("fdt", "scans/speculair_fdt.json", "scans/speculair_fdt_tracking.json",
 "speculair_fdt_tracking.json", "fdt_tracking"),
```
Both self-no-op via the existing missing-book skip until each book's first `--gcs` publish. The weighted-embed refresh stays apex/value-only (FR precedent: weighted tracking for these books is embedded at publish time by `book_publish`, not nightly).
3. `fr-*` guard live (§4); FR GCS payload/tracking/decision-history (`_ledger.py` `"fr"` key) and `future_resources/` subtree frozen in place, read-only by convention.

## 10. Files touched / NOT touched

**Touched (all in one PR; main is branch-protected):**
- `backend/weekly_opus_refresh.py` — BOOKS registry; `fr_*` → `book_*(bk)` refactor; `MINING_DIRECTOR_PROMPT`/`FDT_DIRECTOR_PROMPT`/`MINING_BRIEF`/`FDT_BRIEF`; workflow-template placeholders; FR retirement guard; mining-*/fdt-* dispatch; fr-* branches rewired to `BOOKS["fr"]`.
- `backend/_opus_debate/_fr_post.py` — `--book` parameterization + `_POST_BOOKS` + `warn_macro_as_conviction` (mining, WARN-only).
- `backend/_opus_debate/_resource_metrics.py` — `taxonomy=` parameter (default preserves current behavior).
- `backend/screener_v6.py` — `_mark_speculair_nav` tuple list ONLY (−1 fr, +2 books). Nothing else in the file.
- NEW: `backend/_opus_debate/mining_chains.json`, `backend/_opus_debate/fdt_chains.json`; subtree dirs `backend/_opus_debate/mining/`, `backend/_opus_debate/fdt/` with seeded `regime_state.json` each; `MINING_REGIME.md`, `FDT_REGIME.md` (repo root); tests (§11).
- Docs: `FUTURE_RESOURCES_REGIME.md` (RETIRED banner line), `FUTURE_RESOURCES_SPEC.md` (pointer to the split spec), `CLAUDE.md` (split note).

**NOT touched (spec bug if a diff appears):** `backend/_opus_debate/_post_common.py`, `_disruptor_post.py`, `_value_post.py`, `_regime_post.py`, `_numeric_gate.py`; `backend/_ledger.py`; `backend/live_debate_engine.py`; `backend/macro_regime.py`, `backend/debt_cycle.py` (gold stays falsification-only there; the /commodities page may DISPLAY gold dials as data, but nothing here feeds gold into debt-cycle scoring); the shared debate surfaces `backend/_opus_debate/{results_regime,inputs,transcripts,dossiers}/`, `apex_basket_value.json`, `apex_basket_opus_regime.json`, `secular_themes.json`, `disruptor_themes.json`, all `speculair_baskets/value/apex` payloads and trackers; the frozen `backend/_opus_debate/future_resources/` subtree and `future_resources_chains.json`; every Cloud Run social-arb file (the /commodities page swap is a frontend-nav change owned by the page section — the social ENGINE is never touched); `screener_v6.py` outside the tuple list.

## 11. Acceptance tests (new `backend/_opus_debate/test_book_split.py` + extensions to `test_fr_phase3.py`)

1. `python backend/weekly_opus_refresh.py fr-prep` → prints RETIRED, exit 0, zero filesystem writes; same for `fr`, `fr_publish`, `fr-universe`.
2. `ALLOW_FR=1 ... fr-csv` reaches `book_csv(BOOKS["fr"])` over the frozen subtree (forensic path alive).
3. `... mining-prep` and `... fdt-prep` reach `book_prep` and STOP at the universe-stale guard (proves the guard cannot shadow new modes); `... disruptor-anything` still prints the disruptor message.
4. Registry-disjointness unit test (§1 invariant): no shared path/GCS key/embed key across mining/fdt/fr.
5. `_fr_post.py` with no `--book` → usage + exit 1; `--book fdt --offline` on a fixture apex is byte-idempotent; the fdt fixture includes a `torque_metrics=false` row proving the quadrant clamp no-ops instead of clamping on None.
6. Fail-open regressions: (a) missing `mining/commodity_macro.json` → `mining_director_prompt.txt` contains the UNAVAILABLE line, run completes; (b) missing chain in a regime sidecar → NEUTRAL, never HEADWIND; (c) benchmark leg quote failure → publish completes with WARN, no benchmark block.
7. `_mark_speculair_nav` dry-run against empty GCS: mining/fdt log "skipped — no published constituents"; NO `future_resources` log line exists.
8. Standing suites still green: `python backend/tests/test_debt_cycle.py` (fixture must still read DISCIPLINE) and `python backend/_opus_debate/test_regime_post.py`.
---

## §5. /commodities page + FDT card + nav

# /commodities page + FDT card + nav swap (frontend)

Scope of this section: everything that renders. Producers (mining/FDT publishers, `commodity_macro.json` writer, `_mark_speculair_nav` tuples) are owned by the backend sections; their **payload contracts and GCS keys are fixed here** so both sides build against the same shapes.

## 0. Files touched

| File | Change |
|---|---|
| `frontend/app/commodities/page.tsx` | NEW — the full Mining page ("use client", self-contained, mirrors `frontend/app/social/page.tsx` structure) |
| `frontend/app/nav.tsx` | Swap Social Arb entry for Commodities |
| `frontend/app/page.tsx` | FDT card repoint/retitle (lines ~2104–2132 fetch, ~4945–5161 card+memo), frozen-FR record card, "How the baskets work" copy (~2846–2878) |
| `frontend/app/data/catalystGlossary.ts` | Add `CM_*` glossary keys for the new page's `<Tip>` hovers |
| `backend/_opus_debate/publish_to_frontend.py` | ONE new push tuple (§1c) — the only backend edit in this section |
| `frontend/app/social/page.tsx` | **Untouched.** Route stays on disk and reachable by URL; only the nav link disappears. The Cloud Run social engine is never touched. |

## 1. Nav swap (`frontend/app/nav.tsx`)

- Import: replace `MessageCircle` with `Pickaxe` in the lucide import (verified present in `lucide-react@^1.8.0`: `node_modules/lucide-react/dist/esm/icons/pickaxe.js`).
- In `links` (line 12–17), replace
  `{ href: "/social", label: "Social Arb", icon: <MessageCircle size={13} /> }` with
  `{ href: "/commodities", label: "Commodities", icon: <Pickaxe size={13} /> }`.
- Active-state logic (`pathname.startsWith(l.href)`) needs no change.

### 1b. macro_regime.json push — VERIFIED GAP, spec the small push

Checked: `publish_to_frontend.py` loads `BK / "macro_regime.json"` (line 558) but only **embeds** `macro_regime` + `debt_cycle` + `regime_read` blocks into `speculair_baskets.json` (lines 589–612). The raw file is **never** pushed to GCS; nothing else pushes it either (grep `scans/macro_regime` → no hits).

### 1c. The push (one tuple)

In `publish_to_frontend.py`, extend the `args.gcs` push list (lines 812–814):
```python
for local, remote in [(BASKETS_LOCAL, "scans/speculair_baskets.json"),
                      (TRACK_LOCAL, "scans/speculair_apex_tracking.json"),
                      (PUB / "speculair_apex_tracking_weighted.json", "scans/speculair_apex_tracking_weighted.json"),
                      (BK / "macro_regime.json", "scans/macro_regime.json")]:   # NEW — staged copy for /commodities
```
This is a verbatim copy of the v7 snapshot written by `weekly_opus_refresh._write_macro_regime` — no transformation, no new writer, no state-machine touch. Cadence: weekly (the Saturday routine). The mining publisher (backend section) adds the same tuple to its own `--gcs` push so a mining-only publish also refreshes it.

## 2. `/commodities` page — component blocks top to bottom

Shell conventions (copy from `social/page.tsx`): `"use client"`, one `T` palette const, `maxWidth: 1080` wrapper, module-scope presentational components only (`StatCard`, `Chip`, `Toggle`, `MetricBlock`, `Spark` — copy them verbatim from social/page.tsx lines 165–218), hand-rolled `<svg>` sparklines, `Fragment`-keyed expandable table rows, inline styles, `var(--font-mono)` for all numerics, lucide icons, tables ≥ min-width inside `overflowX: "auto"` containers. Tooltips: `<Tip k="CM_...">` with new glossary entries (`CM_WINNER_SCORE`, `CM_SPOT_INCENTIVE`, `CM_MINERS_CONFIRM`, `CM_PHASE_TILT`, `CM_DIAL_PERCENTILE`, `CM_ADVISORY`).

Data fetching (all in `useEffect`, GCS-first with `/public` fallback, exact idiom of page.tsx lines 2080–2114):
```ts
fetch("/api/gcs/scans/<file>").then(r => { if (r.ok) return r.json(); throw new Error(); })
  .then(setX).catch(() => fetch("/<file>").then(r => r.ok ? r.json() : null).then(d => { if (d) setX(d); }).catch(() => {}));
```

### Block 1 — MACRO HEADER

**Data:** `scans/macro_regime.json` (§1c). Fallback chain: if it 404s, read `scans/speculair_baskets.json` and use its embedded `.macro_regime` + `.debt_cycle` blocks (published weekly since 2026-07-27, see publish_to_frontend.py lines 589–605). If both fail → render gray `MACRO UNAVAILABLE` chips and **continue rendering everything below** — fail-open, a macro outage never hides picks.

**Render (one banner row + one table):**
- **Risk regime banner** — full-width strip, the social-page "strategy glass banner" idiom (social/page.tsx lines 398–409): `regime` (`RISK_ON` green / `NEUTRAL` muted / `CAUTIOUS` amber / `RISK_OFF` red) + `score` + one-line `quadrant_basis`.
- **Quadrant chip** — `quadrant` (`GOLDILOCKS` green · `REFLATION` amber · `STAGFLATION` red · `RISK_OFF` red), from the same payload.
- **Debt-cycle phase chip** — `debt_cycle.debt_cycle_phase` (`EXPANSION`/`DISCIPLINE`/`FORCING`/`MONETIZATION`/`UNKNOWN`) + `weeks_in_phase` + `confidence`; sub-line from `phase_basis`. `UNKNOWN` renders gray with text "fail-open — loosest caps" (never as an error state).
- **Falsifier strip** — `debt_cycle.reserve_asset_check` verbatim, labeled "falsification check — never a scored input".
- **Dalio phase → commodity tilt table** — a hardcoded frontend const, display-only:

```ts
const PHASE_TILTS: Record<string, { tail: string[]; head: string[]; note: string }> = {
  EXPANSION:    { tail: ["copper_mining", "diversified_miners"], head: ["precious_metals"],
                  note: "growth-linked industrials lead; gold carries opportunity cost" },
  DISCIPLINE:   { tail: ["uranium_fuel_cycle", "diversified_miners"], head: ["rare_earth_strategic"],
                  note: "cash-now producers and royalties; long-duration stories fight rising real rates" },
  FORCING:      { tail: ["precious_metals"], head: ["copper_mining", "diversified_miners"],
                  note: "hard assets start to bid as debt service crowds out growth" },
  MONETIZATION: { tail: ["precious_metals", "copper_mining"], head: [],
                  note: "currency debasement: monetary metals max tailwind, real assets over paper" },
  UNKNOWN:      { tail: [], head: [], note: "no phase read — no tilt (fail-open)" },
};
```
Rows: the 5 mining chains; cell chip green (tailwind) / red (headwind) / gray, current phase column highlighted. **Mandatory caption** (the honest-banner rule + CLAUDE.md invariant): *"Advisory tilt table — direction, not sizing. Tilts never gate membership, never move weights; macro reaches the book only via entry-discount floors and risk stance."*

### Block 2 — TAVI DIALS ROW

**Data:** `scans/commodity_macro.json`. Contract (producer: the new weekly `mining-macro` mode, backend section; built from verified FMP feeds — commodity EOD history for GCUSD/SIUSD/HGUSD/PLUSD/DXUSD etc., `treasury-rates`, `economics-indicators` CPI; FRED real-rate dial uses the existing debt_cycle FMP fallback in sandboxes):
```jsonc
{
  "generated_at": "2026-08-02",
  "dials": [
    { "id": "gold_silver_ratio", "label": "Gold/Silver", "value": 78.2, "unit": "x",
      "direction": "falling", "pctile": 62, "series": [ { "d": "2025-08-01", "v": 84.1 }, ... ],  // ~52 weekly points
      "note": "silver outperforming — late-cycle metals confirmation", "source": "FMP GCUSD/SIUSD" },
    { "id": "copper_gold_ratio", ... }, { "id": "real_30y", ... }, { "id": "dxy", ... },
    { "id": "cpi_trend", ... }, { "id": "curve_2s10s", ... }, { "id": "gold_spx_ratio", ... },
    { "id": "miners_vs_metal", ... }, { "id": "commodities_vs_equities", ... }
  ],
  "winners": [ /* Block 3 */ ]
}
```
**Render:** flex-wrap row of compact stat tiles (StatCard footprint, `minWidth: 150`): label, value+unit, a 100×24 `Spark` of `series`, and a percentile context line ("62nd pctile · 10y"). `direction` arrow colored by whether the move is commodity-supportive (green) or not (red) — per-dial mapping hardcoded in the page. **Gold dials are permitted here**: market gold data may be *displayed*; the falsification-only rule constrains `debt_cycle.py` *scoring*, not this page. Say so in the tile tooltip for the gold dials.

**Stale banner:** if `Date.now() - Date.parse(generated_at) > 10 * 864e5`, render an amber banner above the row (social-page thin-data banner idiom, lines 414–421): *"Dials are N days old (weekly job may have missed). Shown as-is — stale macro never tightens the book (fail-open); the Mining basket below is unaffected."* If the file is missing entirely, hide Blocks 2–3 and show one gray line "commodity macro layer awaiting first publish"; Block 4 still renders.

### Block 3 — WINNER SCOREBOARD

**Data:** `winners[]` from the same `commodity_macro.json`:
```jsonc
{ "chain": "uranium_fuel_cycle", "label": "Uranium fuel cycle", "score": 74,           // 0-100, deterministic composite
  "regime": "TAILWIND",                                    // TAILWIND | NEUTRAL | HEADWIND
  "spot_vs_incentive_pct": 18,                             // null for uranium if only proxy data
  "momentum_12m_pct": 31.5, "momentum_z": 1.2,
  "miners_confirmation": "CONFIRMING",                     // CONFIRMING | DIVERGING | FLAT (proxy ETF vs commodity, 90d)
  "proxy_symbols": ["URA"],                                // uranium has NO FMP spot — URA/term proxy, as the taxonomy already does
  "sub_readings": { "phase_fit": "...", "quadrant_fit": "...", "supply_note": "...", "cot_note": "...", "dial_evidence": ["gold_silver_ratio", ...] },
  "why": "one-paragraph deterministic rationale" }
```
**Render:** ranked dense table (the social-page board idiom exactly: `hdr` th style, hover row, chevron, `Fragment` expand). Columns: `#` · `Commodity` (label + proxy chips) · `Regime` chip (green/gray/red) · `Score` (bar vs max, like signal_score bar at social lines 554–561) · `Spot vs incentive` (± %, green when spot > incentive) · `12m mom` · `Miners` chip (`CONFIRMING` green / `DIVERGING` red / `FLAT` gray). Uranium's spot column renders `— · URA proxy`.

Expanded row (**the WHY**): `MetricBlock` strip of the numeric subs + `sub_readings` text lines + `why` paragraph, left-bordered like the social `narrative` block (line 627). Footer caption: *"Deterministic setup ranking of commodities — it never picks the equities. The debate pipeline picks the players below."*

### Block 4 — THE MINING BASKET (the page's point)

**Data:** `scans/speculair_mining.json` — produced by the new Mining publisher (`mining-publish --gcs`, local Claude Code only, weekly). **Contract: the FR payload schema verbatim** — `apex_basket[]` entries carry the same field names the FR card already renders (`fr_score`, `chain`, `chain_regime`, `physical_anchor`, `funded_solvency`, `net_funded_debt_ebitda`, `interest_coverage`, `sop_mos_pct`, `thesis`, `torque_note`, `wheel`, `weight_pct`, `entry_posture`, `duration_bucket`, cap flags `growth_capex_fcf_negative` / `torque_leverage_quadrant` / `headwind_unjustified` / `stale_anchor` / `corr_flag`), plus book-level `mining_tracking`, `mining_tracking_weighted`, `benchmark`, `stress_test`, `correlation`, `chain_exposure`, `pool_stats`, `runner_ups`, `mining_memo`, `generated_at`. Keeping `fr_score` as the field name is deliberate — it lets the pick card be a near-verbatim port of page.tsx lines 5016–5120.

`chain` values MUST equal the scoreboard `chain` ids: `uranium_fuel_cycle` · `copper_mining` · `precious_metals` · `rare_earth_strategic` · `diversified_miners`.

**Render, in order:**
1. **NAV strip** — port of the FR track-record strip (page.tsx 4963–4989): since-inception %, inception date, annualized, mini NAV polyline, `NAV x · n held · n closed · win%`, and the promote-to-weighted rule (`history.length >= 4`). Sub-caption keeps the equal-weight honesty: while `EQUAL_WEIGHT_BOOKS` is on, weighted === 1/n — label it "equal-weight NAV · live-forward, not back-filled".
2. **Benchmark line** — port of 4990–4994; `benchmark.blend` default **"50/50 XME+GDX"** ("the null hypothesis: a closet miners ETF blend"). ETF quotes come with the payload from the publisher; the page itself does not re-derive benchmark math.
3. **Stress/correlation + chain-exposure chips + pool banner** — ports of 4995–5013.
4. **Rotation log** — port of the existing `rotationLog(...)` helper reading `mining_tracking`.
5. **Picks, grouped under their scoreboard chain** — the structural change vs the FR card: group `apex_basket` by `chain`, order groups by the Block-3 winner ranking (chains with no picks show a one-line "no seats — best players didn't clear the gates"; picks whose chain has no scoreboard row group under "other"). Each group header repeats the chain's regime chip + score. Pick card = the FR card idiom verbatim (fr-score badge with 80/65 color breaks, gate-cap chips with their `title=` explanations, physical-anchor ⚓ line, solvency line, contract/reserve line, thesis + TORQUE expander, `wheelLine`, MoS right-aligned, click → `/stock/<sym>?tab=debate`). Prices via the FR batch-quote effect (port of page.tsx 2117–2132, `/api/fmp?e=batch-quote`, 50-symbol chunks) — mining names are AMEX/commodity tickers usually absent from the main scan.
6. **Director memo** — `<details>` expander, port of 5130–5161, reading `mining_memo`.
7. **Runner-ups** line — port of 5122–5127.
8. **Awaiting state** — until the first `mining-publish --gcs` lands, the dashed-border awaiting box (port of 4958–4962): "Awaiting the first Mining publish. The chain runs locally on the operator box… this card lights up the moment the payload lands on GCS." The macro layer (Blocks 1–3) renders independently of it.

### Block 5 — HONEST BANNERS (bottom strip, always rendered)

Three one-line captions in `--text-light` mono, matching the FR card's honesty idioms:
- *"Paper book — no real money. NAV is live-forward from `<inception_date>`; young record, never back-filled."*
- *"US-listed scope (FMP coverage) — the global cost curve is wider than this universe."*
- *"Macro layer is advisory: it ranks setups and sets entry-discount floors/stance. It never gates membership, never moves conviction, and while books publish equal-weight it moves no weight."*

## 3. FDT card changes (Speculair page, `frontend/app/page.tsx`)

The amber FR slot is inherited, not duplicated:
- **Fetch** (2104–2114): repoint to `"/api/gcs/scans/speculair_fdt.json"` (public fallback `"/speculair_fdt.json"`). Rename state `frApex`→`fdtApex` (`frPrices`→`fdtPrices`, `expandedFr`→`expandedFdt`) — mechanical rename across the card block.
- **Batch-quote effect** (2117–2132): unchanged except the state rename.
- **Card** (4946–5128): same amber border/slot. Title → **"Speculair Future Disruptive Tech"**. Header pill → `"N names · builders of the disruptive build-out · physical-anchor rule"`. Intro paragraph rewritten to the five chains: *electrification & grid equipment (the equipment side of the old copper_electrification chain) · nuclear SMRs (new) · power-for-AI · robotics · quantum* — keep the anti-Visa sentence and the "own NAV chain — never blended" sentence verbatim.
- **Tracking keys**: read `fdt_tracking` / `fdt_tracking_weighted` (the embed keys the backend section wires into `_mark_speculair_nav` — new sanctioned tuple, source `scans/speculair_fdt.json`, tracking `scans/speculair_fdt_tracking.json`). Fresh NAV: no history until first publish; the same `>= 4` weighted-promotion rule applies.
- **Benchmark**: `benchmark.blend` default label "QQQ" (or whatever the publisher stamps — render the field, don't hardcode).
- **Awaiting-state idiom kept** (4958–4962), text updated to `fdt-publish --gcs`.
- **Memo** `<details>` (5130–5161): reads `fdt_memo`, retitled "Future Disruptive Tech Director Memo".

## 4. Frozen FR card (disruptor precedent)

Precedent check: the retired Disruptor renders today ONLY as a paragraph in "How the baskets work" (page.tsx 2862–2863) — the live card was replaced outright. Bruno's lock says FR's record is *frozen, never back-filled*, so FR gets slightly more than the disruptor: a compact frozen-record card, because its NAV history must stay visible.

- Directly below the FDT card: a collapsed `<details>` card, border `1px solid var(--border)` (NOT amber — amber now belongs to FDT). Summary: **"Future Resources — FROZEN <freeze_date>"** + final since-inception %.
- Body: the NAV strip (port of 4963–4989) reading the **final** `speculair_future_resources.json` (keep the existing fetch at 2104–2114 as a second, read-only fetch into `frFrozen` state; the GCS object is never rewritten again — the backend section retires the `future_resources` tuple from `_mark_speculair_nav`, so the payload stops marking), the final benchmark line, and a plain symbol list of the final basket (no live pick cards, no quotes fetch — prices are frozen with the payload).
- Banner inside: *"Frozen record — preserved as published, never back-filled, never re-marked. Coverage split 2026-XX-XX: miners → Mining (/commodities), equipment/SMR/power-for-AI/robotics/quantum → Future Disruptive Tech above. Old fr-* modes are retired no-ops."*
- **"How the baskets work"** (2846–2878): rewrite the FR mention in the disruptor paragraph's style — add a `FUTURE RESOURCES — frozen <date>` entry mirroring line 2862's voice, plus two new entries: `MINING — /commodities` (amber→use `var(--amber)`) and `FUTURE DISRUPTIVE TECH` (amber). Update the summary count line (2850).

## 5. Data plumbing table (every fetch the new/changed surfaces make)

| # | Fetch (frontend) | GCS key | Producer (mode, local Claude Code only) | Cadence |
|---|---|---|---|---|
| 1 | `/commodities` macro header | `scans/macro_regime.json` (fallback: embedded blocks in `scans/speculair_baskets.json`) | `weekly_opus_refresh._write_macro_regime` writes it; **NEW push tuple** in `publish_to_frontend.py --gcs` (§1c) + mining publisher's push list | weekly (Sat routine) |
| 2 | `/commodities` dials + winner scoreboard | `scans/commodity_macro.json` | NEW `mining-macro` mode (deterministic; FMP commodities EOD + treasury-rates + economics-indicators; FRED via prod-only fredgraph with FMP fallback) | weekly Sat; page banners at >10d |
| 3 | `/commodities` mining basket | `scans/speculair_mining.json` | NEW `mining-publish --gcs` (Mining Director pipeline; FR-schema payload) | weekly |
| 4 | (indirect — embedded `mining_tracking`) | `scans/speculair_mining_tracking.json` (+ `_weighted`) | `screener_v6._mark_speculair_nav` — ONE new sanctioned tuple (`"mining"`, src `scans/speculair_mining.json`, embed key `mining_tracking`) | nightly mark |
| 5 | `/commodities` + FDT card pick prices | `/api/fmp?e=batch-quote&symbols=…` | FMP proxy route (exists) | on payload load |
| 6 | Speculair FDT card | `scans/speculair_fdt.json` | NEW `fdt-publish --gcs` | weekly |
| 7 | (indirect — embedded `fdt_tracking`) | `scans/speculair_fdt_tracking.json` (+ `_weighted`) | `_mark_speculair_nav` — ONE new sanctioned tuple (`"disruptive_tech"`, embed key `fdt_tracking`) | nightly mark |
| 8 | Frozen FR card | `scans/speculair_future_resources.json` (final, immutable) | none — tuple retired, payload frozen | never again |

House-rule conformance notes for the implementer: two new books ⇒ two new `_mark_speculair_nav` tuples (one per book — within the "ONE per new book" sanction); NAVs never blend (separate payloads, separate tracking files); everything above the pick grid is deterministic display — nothing on this page selects membership; all banners state paper/young-NAV/US-scope honestly; every fetch fail-opens (missing macro/dials never hides or trims the basket); no chart libs — `Spark`/polyline SVG only.
---

## §6. Migration, retirement & routine v3

# SECTION — Migration, retirement & routine v3

**Scope**: the ordered path from today's single Future Resources (FR) book to the two successor books — **MINING** (the `/commodities` page book) and **FDT** (Future Disruptive Tech, inheriting FR's amber card slot on the Speculair page) — plus the FR freeze, the Social Arb page removal, the two sanctioned `screener_v6.py` nightly-NAV tuples, the ROUTINE v3 text, and the test plan. Naming contract with the sibling sections (Taxonomy & pipeline / Page): mode prefixes are `mining-*` and `fdt-*`, isolated subtrees are `backend/_opus_debate/mining/` and `backend/_opus_debate/fdt/`, payloads are `scans/speculair_mining.json` and `scans/speculair_fdt.json` with the picks array named **`apex_basket`** in both (that key is the nightly-mark contract — see §5). If a sibling section chose different literals, map 1:1; do not invent a third scheme.

---

## 0. Build order — three PRs, then the maiden runs, then the retirement PR

`main` is branch-protected; everything lands via PR. Order is load-bearing:

| Stage | What | Why this order |
|---|---|---|
| **PR-1 — taxonomy + pipeline** | Chain-taxonomy split (per the Taxonomy section), the `mining-*`/`fdt-*` mode clones of the nine `fr-*` modes (`fr-universe/fr-map/fr-map-merge/fr-prep/fr-input/fr-numeric-gate/fr-post/fr-csv/fr-publish`, dispatch at `backend/weekly_opus_refresh.py:4400-4419`), `_mining_post.py`/`_fdt_post.py` clones of `backend/_opus_debate/_fr_post.py`, the `mining-macro` dial fetcher, **the two `_mark_speculair_nav()` tuples (§5)**, and the committed offline test suites (§6). Backend-only; every new mode is inert until invoked, so merging is user-invisible. | Nothing can be rehearsed, tested, or maiden-run without the pipeline. The NAV tuples ride PR-1 because the backend auto-deploy (Cloud Build → `screener-sp500` image) needs lead time — the tuples self-no-op until the maiden publishes land, exactly like the FR tuple did (spec §7 precedent, "verify image digest before firing"). |
| **PR-2 — pages** | `/commodities` page (Mining book + macro layer, awaiting-state until `speculair_mining.json` exists), the nav swap (§2), deletion of `frontend/app/social/` and `frontend/app/api/social/` (§2), and the Speculair-page amber-slot change: the card at `frontend/app/page.tsx:4945` renders the **FDT** payload when `speculair_fdt.json` exists, else continues rendering the live FR payload (literal slot inheritance; the data source switches when the maiden lands). Also ships the frozen-FR render path (reads `final_holdings` + `frozen` — §1), dormant until the freeze. | Pages must be live **before** the maiden publishes, or the payloads land invisible (the FR card precedent: card first, `fr-publish --gcs` second). Merging PR-2 right before the maiden-run day keeps the /social→awaiting-/commodities window to hours. |
| **MAIDEN RUNS** (not a PR) | Both books' full chains on the operator box, §3. FR's live card/NAV continue untouched throughout — three books briefly coexist, separate NAVs, never blended. | The freeze trigger (§1) requires both maiden publishes confirmed live. This preserves the original §10 no-coverage-gap ordering (the disruptor's early-retirement supersession was a one-off operator decision; nothing forces it here). |
| **PR-3 — retirement** | The `fr-*` dispatch guard (§1 step 1), `backend/_retire_fr.py` (§1 step 2), the FR-card flip finalization (frozen record becomes the only FR surface; FDT owns the amber slot unconditionally), the `run_speculair_weekly.ps1` belt-and-suspenders line, and the ROUTINE v3 rewrite of `ROUTINE_speculair_weekly.md` (§4). | Retirement last, gated on the trigger. Prepared in advance as an open PR so the flip is a merge, not a build. |

Do **not** fold PR-1 and PR-2 together: the frontend auto-deploys to Vercel and the backend to Cloud Build on the same merge, and a mixed PR makes a revert of one surface drag the other.

---

## 1. FR freeze runbook (mirror of FUTURE_RESOURCES_SPEC.md §10)

**Honest-rails compliant: nothing deleted, nothing back-filled.** FR is a live-forward record that ran; it freezes as a visible final record, exactly like the disruptor card.

**THE TRIGGER (exact)**: both of these confirmed on the operator box, same day —
1. `mining-publish --gcs` printed `GCS push scans/speculair_mining.json: OK` **and** its fresh readback line, and the `/commodities` page renders the live slate;
2. `fdt-publish --gcs` printed `GCS push scans/speculair_fdt.json: OK` **and** its readback, and the Speculair amber slot renders FDT.

**WHO FLIPS**: **Bruno, and only Bruno** — by merging the pre-staged PR-3, then on the operator box: `git pull --ff-only origin main`, run `python backend/_retire_fr.py --execute`, and paste ROUTINE v3 (§4) into the Routines UI. One owner, one day, in that order. (The 2026-07-03 retirement detour came from routine-text drift — the paste is part of the flip, not a follow-up.)

**The four retirement edits (all in PR-3 except the script *execution*):**

1. **Stop the rotation — dispatch guard.** In `weekly_opus_refresh.py` `__main__`, immediately after the existing disruptor guard (line 4364), add the mirror:
   ```python
   if mode.replace("_", "-").startswith("fr-"):
       print(f"FUTURE RESOURCES (single-book) RETIRED <date> (split into MINING + FDT, "
             f"FUTURE_RESOURCES_SPLIT_SPEC.md) — mode '{mode}' is a no-op. Use mining-* / fdt-*.")
       sys.exit(0)
   ```
   Exit 0, prints RETIRED — the disruptor pattern verbatim. The `fr_*` function bodies **stay in the repo** in PR-3 (retired code that ran a live track record is history; the disruptor precedent deleted code only later, as a separate housekeeping decision after the clones proved stable). Also add to `backend/run_speculair_weekly.ps1`'s headless prompt (beside the existing disruptor lines at 102/111): *"FUTURE RESOURCES (fr-*) is RETIRED — do NOT run any fr-* mode even if the runbook still mentions it; skip silently and note the skip in the report."*

2. **The NAV freeze is NOT automatic — this is the critical difference from the disruptor.** The disruptor's nightly tuple never shipped, so stopping its weekly step WAS the freeze (§10.2). **FR's tuple DID ship** (`screener_v6.py:6915-6917`) and the deployed nightly job will keep marking the FR NAV forever as long as `scans/speculair_future_resources.json` carries a non-empty `apex_basket` (`screener_v6.py:6925` — `picks = book.get("apex_basket") or []`). So the freeze is a **payload rewrite**, executed once by `backend/_retire_fr.py --execute` (new one-shot script, `_retire_disruptor_skill.py` naming precedent):
   - `gcs_download("scans/speculair_future_resources.json")`; rename key `apex_basket` → `final_holdings` (record preserved byte-for-byte, incl. entry prices/dates); stamp `"frozen": true`, `"frozen_at": <ISO date>`, and the banner `"Final track record · frozen at retirement · never back-filled · coverage moved to the Mining and Future Disruptive Tech books"`; `gcs_upload` back. Mirror the same rewrite into `frontend/public/speculair_future_resources.json`.
   - `--dry-run` (default) prints the rename plan and touches nothing.
   - Verification is §5's no-op proof: next nightly log must read `Speculair future_resources NAV mark skipped — no published constituents`.
   - `scans/speculair_future_resources_tracking.json` (+`_weighted`) stay in GCS **untouched** — the frozen NAV history, never rewritten (disruptor rule: "Tracking JSONs stay in GCS untouched"). The embedded `fr_tracking`/`benchmark` blocks in the payload stay as last refreshed — they ARE the final record.
   - **Freeze date = the `_retire_fr.py --execute` run date** (the NAV marked nightly up to that night), stamped as `frozen_at`. Not the last weekly publish date — the disruptor's "freeze = last STEP 3C run" rule does not transfer, because FR's NAV stepped nightly.

3. **The card tells the truth** (PR-3 frontend, activated by the `frozen` stamp): the FR record renders from `final_holdings` + the frozen `fr_tracking`, amber RETIRED banner, "Final track record · frozen <date>" replacing "Live track record", footnote "live-forward while it ran, frozen at retirement, never back-filled", and the "How the baskets work" explainer states the split and where each chain moved (the disruptor explainer at `page.tsx:2863` is the template). The batch-quote effect at `page.tsx:2116-2120` must key off `apex_basket` only (frozen holdings are not re-quoted).

4. **No holdings migration.** Both new books build from scratch (anti-shrink rule, Do-NOT #3). An FR holding that belongs in Mining or FDT re-earns its seat through its book's screen → chain map → debate. The held-name union in `mining-prep`/`fdt-prep` applies only to each book's OWN holders — on the maiden runs, `held` is empty by construction (their payloads don't exist yet). FR's ledgers (`_director_ledger_fr.txt`, the `"fr"` decision history) freeze append-only, never written again.

---

## 2. Social Arb removal (frontend only; the social engine is NEVER touched)

1. **Nav swap** — `frontend/app/nav.tsx:16`: replace
   `{ href: "/social", label: "Social Arb", icon: <MessageCircle size={13} /> }` with
   `{ href: "/commodities", label: "Commodities", icon: <Pickaxe size={13} /> }` (lucide-react only, house rule; drop the now-unused `MessageCircle` import).
2. **Delete `frontend/app/social/`** (the page) — Bruno's locked decision: replaced outright.
3. **Delete `frontend/app/api/social/`** (the `[...path]` proxy route) — **DECISION: delete, with the page.** Rationale: (a) verified sole consumer — the only references to `/api/social` in the app tree are inside `frontend/app/social/page.tsx` itself; (b) it is an unauthenticated route that reads GCS server-side — dead surface with no consumer is pure liability; (c) nothing is lost: the route reads the `scans/social_arb.json` snapshot, and that snapshot **keeps being published** — the social engine (local publisher, `backend/publish_gcs.py`; note the route's own comment records that the old Cloud Run FastAPI backend is already gone) is not touched in any way, so the append-only data record continues on GCS; (d) restoring page + route from git history rehydrates the whole surface with zero backend work if Bruno ever wants it back.
4. **Sweep**: `grep -rn '"/social"\|/api/social' frontend/app` must return nothing; `npx tsc --noEmit` clean.
5. **Do NOT touch**: `backend/publish_gcs.py`'s social publisher, the `scans/social_arb.json` snapshot, or any social backend schedule. The engine keeps running and publishing whether or not anything reads it — that is the locked rule.

---

## 3. Maiden-run sequence (operator box, after PR-1 + PR-2 are merged and pulled)

Run **Mining first** (the flagship page book), FDT second, same day if possible. Each chain is failure-isolated: a GUARD/STOP in one book never blocks the other, and the Apex/Value/B13/FR books are untouched throughout. One-paste runbook text:

```
# ── MAIDEN RUN — MINING (run top to bottom; STOP and report on any GUARD line; never publish degraded) ──
git pull --ff-only origin main
python backend/weekly_opus_refresh.py mining-universe
#   → Workflow(backend/_opus_debate/mining/_mining_map.js)          # Sonnet chain-map shards
python backend/weekly_opus_refresh.py mining-map-merge
python backend/weekly_opus_refresh.py mining-macro                  # fresh dials BEFORE the debates
python backend/weekly_opus_refresh.py mining-prep
#   → Workflow(<the printed _mining_debate.js path>)                # BATCH=8, "Reply exactly: DONE"
python backend/weekly_opus_refresh.py mining-numeric-gate --enforce
python backend/weekly_opus_refresh.py mining-input
#   → ONE Director subagent (Agent tool, general-purpose, model: opus), told exactly:
#     "Read backend/_opus_debate/mining/mining_director_prompt.txt IN FULL and execute it over
#      backend/_opus_debate/mining/mining_grade_input.json; write
#      backend/_opus_debate/mining/apex_basket_mining.json EXACTLY per its schema; reply DONE."
python backend/weekly_opus_refresh.py mining-post
python backend/weekly_opus_refresh.py mining-csv
python backend/weekly_opus_refresh.py mining-publish --gcs
# CONFIRM: "GCS push scans/speculair_mining.json: OK" + the fresh readback line + tracking inception
#          ("tracking nav=1.0 since=0.0%") + the /commodities page renders the slate.

# ── MAIDEN RUN — FDT (identical shape; no macro step — FDT reads the chain-regime sidecar only) ──
python backend/weekly_opus_refresh.py fdt-universe
#   → Workflow(backend/_opus_debate/fdt/_fdt_map.js)
python backend/weekly_opus_refresh.py fdt-map-merge
python backend/weekly_opus_refresh.py fdt-prep
#   → Workflow(<the printed _fdt_debate.js path>)
python backend/weekly_opus_refresh.py fdt-numeric-gate --enforce
python backend/weekly_opus_refresh.py fdt-input
#   → ONE Director subagent, same instruction shape over backend/_opus_debate/fdt/
#     (fdt_director_prompt.txt → apex_basket_fdt.json)
python backend/weekly_opus_refresh.py fdt-post
python backend/weekly_opus_refresh.py fdt-csv
python backend/weekly_opus_refresh.py fdt-publish --gcs
# CONFIRM: "GCS push scans/speculair_fdt.json: OK" + readback + inception + the amber slot renders FDT.
```

Notes baked into the clones (verify, don't re-derive): the publish gates are inherited from `fr_publish` (`weekly_opus_refresh.py:2580-2607`) — no-post-stamp abort, <6-picks degraded-stop, post-hoc chain-cap breach stop; the benchmark sidecar (`_benchmark_anchors.json` pattern, `weekly_opus_refresh.py:2677-2690`) stamps each book's anchors on the maiden publish, **measured from that date forward, never back-filled**; off-scan members price via the `_current_prices()` FMP batch-quote fallback (already live). Both maiden NAVs **start fresh at inception** — no FR history is imported into either tracking file, ever. Until the next `screener-sp500` redeploy carries the §5 tuples, both NAVs step weekly at publish (the FR precedent); after it, nightly.

Once both CONFIRM blocks pass → **the §1 trigger is met** → Bruno executes the flip (merge PR-3 → pull → `_retire_fr.py --execute` → paste ROUTINE v3).

---

## 4. ROUTINE v3 — STEP 3C replacement (verbatim)

Edit `ROUTINE_speculair_weekly.md` first (it is the canonical copy), then paste the body into the Routines UI — both in the PR-3 flip. Add a header note: *"Updated <date>: STEP 3C FUTURE RESOURCES retired (split into MINING + FDT, FUTURE_RESOURCES_SPLIT_SPEC.md; every `fr-*` mode is a code-level RETIRED no-op); STEP 3C is now the MINING book (full chain weekly, macro dials first), STEP 3D is the FDT book."* Also update the operating-rules bullet that lists the disruptor retirement to add: *"and the single-book FUTURE RESOURCES lens (`fr-*`) is likewise RETIRED — its modes print a RETIRED notice and exit 0; never run one."* Note the live Routines-UI text currently runs the full FR Lane A chain at STEP 3C (the repo copy lags — it still says universe-only), so the paste **replaces a live full-chain step**, which is exactly the §1 rotation-stop.

The replacement text, in the routine's voice — this replaces STEP 3C wholesale and inserts STEP 3D before STEP 4:

> STEP 3C — MINING BOOK (the /commodities page book — uranium fuel cycle, copper mining, precious metals producers/royalties, rare earths & strategic metals, diversified miners; full Lane A chain weekly; ~25-45 min). This step replaced the retired single-book FUTURE RESOURCES lens — never run any `fr-*` mode; they are code-level no-ops that print RETIRED and exit 0. Sequence, in order:
> 1. `python backend/weekly_opus_refresh.py mining-macro` — the deterministic Dalio/Tavi commodity dials (FMP commodity quotes/EOD + the treasury curve + CPI + ETF quotes) → `_opus_debate/mining/commodity_macro.json`. ALWAYS runs BEFORE the debates so this week's Director cites this week's dials, never last week's. Gold dials are DISPLAY DATA here (the falsification-only rule binds `debt_cycle.py` scoring, not this page). GUARD: a failed fetch degrades that dial to null with a WARN and the chain CONTINUES — fail-open, a data gap must never tighten the book; quote any dial WARN in STEP 4.
> 2. UNIVERSE FRESHNESS (this is how "monthly" fires — it cannot be forgotten): `mining-prep` self-gates on `mining/universe.json` (>21 days → prints STALE and STOPs). If it STOPs, run the monthly rebuild first — `python backend/weekly_opus_refresh.py mining-universe` → `Workflow(backend/_opus_debate/mining/_mining_map.js)` → `python backend/weekly_opus_refresh.py mining-map-merge` — then continue.
> 3. REGIME FRESHNESS (read-only): if `mining/regime_state.json`'s `as_of` is >16 days old, print a WARN and CONTINUE — the bi-weekly regime scheduled task owns the refresh; a stale regime read NEVER stops this chain (the Director sees the sidecar with its date; staleness is reported, not enforced).
> 4. The chain: `python backend/weekly_opus_refresh.py mining-prep` → `Workflow(<the printed _mining_debate.js path>)` (BATCH=8; no skeptic tier by design — the adversarial teeth are the Interrogator credibility gate + the numeric gate + the deterministic post caps) → `python backend/weekly_opus_refresh.py mining-numeric-gate --enforce` → `python backend/weekly_opus_refresh.py mining-input` → ONE Director subagent (Agent tool, `general-purpose`, `model: opus`), told exactly: "Read backend/_opus_debate/mining/mining_director_prompt.txt IN FULL and execute it over backend/_opus_debate/mining/mining_grade_input.json; write backend/_opus_debate/mining/apex_basket_mining.json EXACTLY per its schema; reply DONE." → `python backend/weekly_opus_refresh.py mining-post` → `mining-csv` → `mining-publish --gcs`.
> 5. Confirm `GCS push scans/speculair_mining.json: OK` + the fresh readback line. If the push FAILED, re-run `mining-publish --gcs` once (idempotent — one publish = one rotation, never publish twice in a run).
> GUARD: this lane is ADDITIVE — any GUARD/STOP line here (`stale universe`, `<25 mappable members`, `<6 picks`, chain-cap breach, failed push after one retry) → report it, SKIP the rest of this step, and proceed to STEP 3D; the Apex + Value + B13 books are already live and completely unaffected. Never publish degraded.
>
> STEP 3D — FUTURE DISRUPTIVE TECH BOOK (the amber Speculair card — electrification/grid equipment, nuclear SMRs, power-for-AI, robotics, quantum; full Lane A chain weekly; ~20-40 min). Identical shape to STEP 3C minus the macro step (FDT reads its chain-regime sidecar, not the commodity dials): universe freshness self-gate (>21d → `fdt-universe` → `Workflow(_fdt_map.js)` → `fdt-map-merge` first) → regime-freshness WARN (read-only, never stops) → `fdt-prep` → `Workflow(<the printed _fdt_debate.js path>)` → `fdt-numeric-gate --enforce` → `fdt-input` → ONE Director subagent ("Read backend/_opus_debate/fdt/fdt_director_prompt.txt IN FULL … write backend/_opus_debate/fdt/apex_basket_fdt.json … reply DONE.") → `fdt-post` → `fdt-csv` → `fdt-publish --gcs`. Confirm `GCS push scans/speculair_fdt.json: OK` + readback; re-run the publish once on FAILED. GUARD: additive lane — any GUARD/STOP → report, skip, proceed to STEP 4; every other book unaffected. The Mining and FDT books are SEPARATE — separate NAVs, separate payloads, never blended, and a failure in one never blocks the other.

STEP 4 gains one sentence (append to the existing reporting paragraph):

> If STEP 3C/3D ran, ALSO report each book separately: the picks with Director scores, per-chain exposure, what changed vs last week, the macro-dial summary the Mining Director cited (and any dial WARN), both `GCS push … OK` readbacks with tracking NAV/since-inception, and any GUARD that skipped a step. Never blend the two books into one number.

The NOTES section's disruptor paragraph gains the FR mirror: *"The single-book Future Resources lens is likewise retired (frozen card, `final_holdings`, nightly mark self-no-ops); its successors are STEP 3C/3D. The bi-weekly commodity-regime scheduled task (13-day self-gating floor) now covers both books' chains."*

---

## 5. Nightly NAV — the two sanctioned `screener_v6.py` tuples + the FR no-op proof

**The ONLY `screener_v6.py` edit in this whole migration** (house rule: one sanctioned nightly-NAV tuple per new book) is appending exactly these two 5-tuples to the list in `_mark_speculair_nav()` (`screener_v6.py:6908-6918`), directly under the existing `future_resources` tuple, with a comment mirroring its style:

```python
        # MINING (FUTURE_RESOURCES_SPLIT_SPEC.md): self-no-ops until the first mining-publish --gcs.
        ("mining", "scans/speculair_mining.json",
         "scans/speculair_mining_tracking.json",
         "speculair_mining_tracking.json", "mining_tracking"),
        # FDT (FUTURE_RESOURCES_SPLIT_SPEC.md): self-no-ops until the first fdt-publish --gcs.
        ("fdt", "scans/speculair_fdt.json",
         "scans/speculair_fdt_tracking.json",
         "speculair_fdt_tracking.json", "fdt_tracking"),
```

Contract recap (it is positional): `(label, payload GCS path, tracking GCS path, local tracking name, embedded-summary key)`; the picks array in each payload MUST be `apex_basket` (line 6925 reads exactly that key). Do NOT extend the apex/value-only *weighted* nightly branches (lines 6939-6956) to the new labels — that would be a second unsanctioned edit; the weighted sidecars step weekly at publish, as FR's always did.

**The FR tuple stays in place — and the claim "it self-no-ops on the frozen payload" is only true AFTER the §1 payload rewrite. Verified against the code:** the loop body does `picks = (book or {}).get("apex_basket") or []; if not picks: log "skipped — no published constituents"; continue` (`screener_v6.py:6925-6928`) — the `continue` fires **before** `_update_apex_tracking`, before the embedded-summary refresh, and before the `gcs_upload(src, book)` write-back, so with `apex_basket` absent the tuple performs zero writes and zero NAV steps: a true no-op. But **as of today the live FR payload has a populated `apex_basket`, so without the rewrite the deployed nightly job would keep marking the "frozen" book every night** — the record would silently keep moving, which is precisely what a freeze forbids. That is why `_retire_fr.py` renames `apex_basket` → `final_holdings` (§1.2): the record stays byte-identical and visible, the key the nightly mark reads goes empty, and the pre-existing skip path does the freezing forever, with **no screener_v6.py edit needed for the retirement itself**. Acceptance for the flip: the first post-freeze nightly log line `Speculair future_resources NAV mark skipped — no published constituents`.

---

## 6. Test plan

**A note found during this design pass, now a requirement**: the FR offline suites (`test_fr_phase3.py`, `test_fr_universe.py`, `test_fr_caps.py`, `test_fr_map_merge.py`, `test_resource_metrics.py`) live only in a build session's scratchpad — they are NOT in the repo. PR-1 must **commit** the cloned per-book suites so they survive sessions, beside the existing `backend/_opus_debate/test_regime_post.py` / `test_caps.py`.

1. **Per-book offline suites** — `backend/_opus_debate/test_mining_pipeline.py` + `test_fdt_pipeline.py`, cloning the `test_fr_phase3.py` pattern (synthetic universe → P1 prep: staleness gate, pre-rank cut, bundles carry regime + metrics, workflow rendered; P2 input: torque/regime join, forensic EXCLUDE / fail-closed CAP, hard-gate counters, director prompt written; P3 post `--offline`: HEADWIND clamp unjustified-vs-justified, growth-capex 0.75, torque-quadrant cap, chain caps on a stacked basket, weights sum 1, REFUTED demotion where applicable, **second `--offline` run byte-identical**). Plus the publish gates: <6 picks aborts, missing post stamp aborts, post-hoc chain-cap breach aborts.
2. **NAV tuple + freeze unit test** — drive `_mark_speculair_nav()` with `gcs_download` monkeypatched: (a) frozen-shape payload (`final_holdings` populated, no `apex_basket`) → asserts the skip log and that `_update_apex_tracking`/`gcs_upload` were never called; (b) `apex_basket`-shaped mining/fdt payloads → marked, embedded `mining_tracking`/`fdt_tracking` refreshed. This test is the executable form of §5's no-op proof.
3. **Retired-mode guard test** (PR-3) — `subprocess` each of `fr-prep`, `fr-publish --gcs`, `fr-universe`: expect the RETIRED line, exit 0, and no mtime change anywhere under `backend/_opus_debate/future_resources/`. `_retire_fr.py --dry-run` prints the rename plan and writes nothing.
4. **Cross-book isolation — byte-identical, the hard gate for PR-1**: on the PR-1 branch, re-run `python backend/_opus_debate/_regime_post.py --offline` and `python backend/_opus_debate/_value_post.py --offline` over the pre-branch fixtures and `diff` their outputs against pre-branch bytes — **byte-identical or the PR does not merge** (value and regime books untouched by construction). B13: `python backend/_basket13_selftest.py` green and `_basket13_tracker.json` untouched. Standing suites stay green: `python backend/tests/test_debt_cycle.py` (must print ALL PASS and still read DISCIPLINE on the 2026-07 tape) and `python backend/_opus_debate/test_regime_post.py`.
5. **Frontend** — `cd frontend && npx tsc --noEmit` clean on PR-2 and PR-3; the §2.4 grep sweep returns nothing; manual render check of the four states: /commodities awaiting → live, amber slot FR-live → FDT-live, frozen FR record visible post-flip.
6. **Routine-drift check** (flip day) — after the Routines-UI paste, diff the pasted body against the repo copy's BEGIN/END block: identical, or stop (the 2026-07-03 lesson).