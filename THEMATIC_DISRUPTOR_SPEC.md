# THEMATIC DISRUPTOR LENS — Build Spec (v1, 2026-06-10)

> **Status**: SPEC ONLY — no code written. Every integration point below was verified against the
> repo as of 2026-06-10 (branch `ux-revamp`). Design decisions in §0.2 are Bruno's and are NOT up
> for relitigation by the implementer.
>
> **What this builds**: a THIRD tracked Speculair book — the **"Disruptor Lens"** — profitable
> companies riding secular disruption themes (AI infrastructure/semis, energy transition,
> robotics/automation, genomics/bio tools, defense tech, fintech rails, space). Picks-and-shovels
> toll-takers with real TTM FCF, NOT pre-profit moonshots. Its own universe, its own Director
> rubric, its own NAV chain, its own purple card — never blended into the Apex or Value books.

---

## 0. Executive summary

### 0.1 The three books — three lenses over different universes

| | **Apex (catalyst/regime)** — green card | **Value Lens** — blue card | **Disruptor Lens (NEW)** — purple card |
|---|---|---|---|
| Universe | RAW 11-method value screen (`scans/methodology_picks.json`, ~161 names) | SAME debate pool as Apex, re-graded | NEW thematic FMP screen + Sonnet theme map, **≤40 debated names** |
| Question | "Which cheap names have a live, dated catalyst under the current regime?" | "Which names are cheap on pure value, regime stripped?" | "Which PROFITABLE toll-takers are load-bearing in a durable secular theme?" |
| Score driver | director_conviction (regime-tilted) | sop_mos_pct (CRO-normalized MoS) | Theme position + moat + reinvestment runway; **valuation is a GUARD, not the driver** |
| Concentration axis | hidden macro factors (demand cycle, regulatory…) | hidden factors (reimbursement, ad-cycle…) | **THEME concentration** (AI-capex is the obvious cluster): ≤3 names AND ≤30% weight per theme |
| Picks | 10 | 10 | **8** (deliberately the smallest sleeve) |
| Tracking | `speculair_apex_tracking.json` | `speculair_value_tracking.json` (+ weighted) | `speculair_disruptor_tracking.json` (+ weighted) — **never blended** |
| Re-grade cadence | weekly (Sun skill) | weekly (STEP 3B) | weekly grading (NEW STEP 3C); theme membership/universe **monthly** |

The debate CHAIN (Interrogator → Architect/SoP → web catalyst-verification → CRO reconcile) is
reused verbatim; only the universe sourcing, the debate brief, the Director rubric, and the
post-layer parameterization differ.

### 0.2 Locked design decisions (Bruno)

1. **Profitable disruptors only.** Hard gates: FCF-positive TTM (or clearly FCF-positive within 4
   quarters with cited evidence), revenue growth >~15% 3-yr CAGR or accelerating, funded-leverage
   solvency reused verbatim from the value book. Mcap floor ≥ ~$2B, ADV floor.
2. **Different rubric**: (1) Theme durability & position, (2) Moat & pricing power, (3)
   Reinvestment runway & unit economics, (4) Growth-adjusted valuation GUARD (+ Interrogator
   forensic gate + funded-leverage solvency reused verbatim).
3. **Universe is the key design problem**: the 161-name universe comes from an 11-method VALUE
   screen — disruptors will not be in it. New thematic universe builder (§1), capped at ~40
   debated names. Theme membership refreshed monthly; grading weekly (justified §7.2).
4. **Reuse the debate chain as-is**; only a NEW `DISRUPTOR_DIRECTOR_PROMPT` (§4) with theme
   concentration as the primary stress axis.
5. **Post-layer / tracking / frontend reuse** `_value_post.py` patterns, a third NAV chain, a third
   card with an honest highest-vol banner. Separate, clearly-labeled, smaller sleeve.

### 0.3 New surface at a glance

| Artifact | Path |
|---|---|
| Theme taxonomy (versioned config, NOT code) | `backend/_opus_debate/disruptor_themes.json` |
| Run subtree (isolated from value's self-clean) | `backend/_opus_debate/disruptor/` |
| Driver modes (ride existing allowlist wildcard) | `backend/weekly_opus_refresh.py` → `disruptor-universe`, `disruptor-prep`, `disruptor-input`, `disruptor-post`, `disruptor-csv`, `disruptor-publish [--gcs]`, `disruptor-finish` |
| Deterministic post-layer | `backend/_opus_debate/_disruptor_post.py` |
| Director output | `backend/_opus_debate/disruptor/apex_basket_disruptor.json` |
| Public payload | `frontend/public/speculair_disruptor_apex.json` → `gs://screener-signals-carbonbridge/scans/speculair_disruptor_apex.json` |
| NAV chains | `speculair_disruptor_tracking.json` + `speculair_disruptor_tracking_weighted.json` (public + `scans/`) |
| Nightly mark | third tuple in `backend/screener_v6.py::_mark_speculair_nav()` (line ~6212) — **requires screener-sp500 redeploy** |
| Frontend | purple-border card in the Speculair tab of `frontend/app/page.tsx`, inserted between the Value Lens card and the Capitulation Watchlist |
| Skill | NEW **STEP 3C** in `C:\Users\Bruno\.claude\scheduled-tasks\speculair-opus-weekly\SKILL.md` |

---

## 1. Universe builder — `disruptor-universe` mode (monthly)

**The key design problem.** The existing universe sourcing (`prep()` in
`backend/weekly_opus_refresh.py:846` reads `scans/methodology_picks.json` from GCS) is a VALUE
screen — secular growers at fair-to-rich multiples never pass it. The disruptor book needs its own
sourcing, built to the same anti-shrink-loop standard `prep()` learned the hard way (the 2026-06-06
incident: sourcing from curated survivors degenerated the universe to 8 methodologies / 15 names).

### 1.1 Theme taxonomy — versioned JSON, never code

**New file**: `backend/_opus_debate/disruptor_themes.json`. Themes must be editable without
touching Python. Schema:

```json
{
  "version": "1.0",
  "updated": "2026-06-15",
  "themes": [
    {
      "id": "ai_infrastructure",
      "name": "AI infrastructure & semis",
      "thesis": "Hyperscaler + sovereign AI capex flows to compute, networking, memory, power and cooling toll-takers.",
      "value_chain_layers": ["chip design", "fab equipment", "advanced packaging", "networking", "power/cooling", "design software"],
      "fmp_sectors": ["Technology"],
      "fmp_industries": ["Semiconductors", "Semiconductor Equipment & Materials", "Computer Hardware", "Communication Equipment", "Software - Infrastructure"],
      "keyword_hints": ["data center", "HBM", "accelerator", "inference", "EDA", "liquid cooling"],
      "anchor_examples": ["ASML", "ANET", "VRT", "CDNS"],
      "notes": "The obvious concentration cluster — every layer rides ONE capex line. Flag in every Director run."
    },
    { "id": "energy_transition", "...": "grid equipment, electrification, storage, nuclear fuel/services" },
    { "id": "robotics_automation", "...": "factory automation, warehouse robotics, machine vision, motion control" },
    { "id": "genomics_bio_tools", "...": "sequencing tools, bioprocessing consumables, lab automation — tools, not therapies" },
    { "id": "defense_tech", "...": "C4ISR, drones/counter-drone, space-based ISR, munitions modernization" },
    { "id": "fintech_rails", "...": "payment rails, market infrastructure, banking software — toll-takers, not lenders" },
    { "id": "space", "...": "launch-adjacent, satellite comms/ground segment, space hardware suppliers" }
  ]
}
```

`anchor_examples` are illustrative only — they seed the Sonnet mapping pass, they are NEVER
auto-included. The `version` field is stamped into every downstream payload (`taxonomy_version`)
so a published basket is traceable to the taxonomy that produced it.

### 1.2 Stage A — deterministic FMP screen (no LLM)

Per theme, call FMP `company-screener` exactly the way `screener_v6.get_symbols()`
(backend/screener_v6.py:927) does — same param vocabulary, proven against this key:

```python
fmp("company-screener", {
    "sector": <theme.fmp_sectors[i]>,            # and/or "industry": <theme.fmp_industries[j]>
    "marketCapMoreThan": 2_000_000_000,          # $2B floor (design brief)
    "volumeMoreThan": 200_000, "priceMoreThan": 5,
    "isActivelyTrading": "true", "isEtf": "false", "isFund": "false",
    "exchange": <"NYSE" | "NASDAQ" | EU majors>, "limit": 1000,
})
```

Use the module-level `fmp()` wrapper from `screener_v6` (line 396 — rate-limited, FMP_OFFLINE-aware,
error-logged) by importing it the way `_value_post.py` already does
(`from screener_v6 import fmp, get_chart`). Union the per-theme results, dedupe, and record
`screened_by_theme` counts. Expect a few hundred raw candidates.

### 1.3 Stage B — deterministic financial gates (no LLM)

Per candidate, reusing the exact endpoint patterns already in `weekly_opus_refresh.py`:

| Gate | Source (existing pattern) | Pass rule |
|---|---|---|
| FCF-positive TTM | `/stable/cash-flow-statement` quarterly, sum last 4 `freeCashFlow` (the `_ttm_cash_block` pattern, line 44) | TTM FCF > 0, **OR** last 2 consecutive quarters FCF > 0 (tag `fcf_inflecting=true` — the Director must cite guidance evidence to keep these) |
| Revenue growth | `/stable/income-statement` annual `limit=4` → 3-yr CAGR; quarterly `limit=8` → YoY | 3-yr CAGR ≥ 15% **OR** (latest YoY > 3-yr CAGR AND YoY ≥ 10%) — "or accelerating" |
| Funded-leverage solvency | `_funded_leverage()` (line 194: `/stable/key-metrics-ttm` `netDebtToEBITDATTM` + `/stable/ratios-ttm` `interestCoverageRatioTTM`, ThreadPool 8, cached) + `_funded_solvency()` (line 236) | bucket ≠ `weak` |
| Liquidity | `batch-quote` chunked 50 (the `_value_post.live_quotes` pattern) | price × avgVolume ≥ $10M/day |
| Listing hygiene | company-screener fields | primary listing, not an alt share class |

Cache Stage-B fetches to `backend/_opus_debate/disruptor/_gates_cache.json` keyed by symbol+month
so a re-run inside the same month is free.

### 1.4 Stage C — Sonnet theme-mapping pass (Radar-style, chunked + deterministic merge)

Mirror the Radar phase exactly (`_WORKFLOW_TEMPLATE` Phase 0, weekly_opus_refresh.py:999-1012, and
`merge_radar()` line 141 — chunked because a single agent over 161 names truncated):

- Chunk survivors ≤20 per agent; one **Sonnet** agent per chunk writes
  `backend/_opus_debate/disruptor/_dt_<i>.json`.
- Each agent assigns, per symbol: `themes` (ids from `disruptor_themes.json` — a name may carry 2),
  `value_chain_position` (which layer, one line), `load_bearing_score` 1-5 (how hard is this company
  to route around in the theme's value chain), `s_curve_stage`
  (`early_adoption|steep_ramp|broadening|maturing`), `true_competitors` (4-8 real tickers,
  in-universe or not — same instruction as the Radar), `relative_comps` (2-4 sentences),
  and `theme_fit_confidence` (`high|medium|low` — `low` = the FMP industry filter caught a
  non-disruptor; these are DROPPED with a printed count, never silently).
- Deterministic merge (a `disruptor-map-merge` step mirroring `merge_radar()`): shards →
  `disruptor/theme_map.json` + per-symbol explode to `disruptor/theme_map/<SYM>.json` (same
  reasoning: the combined file would blow the 25k-token Read cap; each debate agent reads only its
  own entry).
- **This pass double-serves as the Radar**: the debate's peer-comps step reads
  `disruptor/theme_map/<SYM>.json` instead of `peer_groups/<sym>.json`. No separate Radar phase —
  one Sonnet pass, two jobs (cost win, §8).

### 1.5 Stage D — deterministic cut to ≤40 debated names

- Rank within theme by a transparent pre-rank: `load_bearing_score` desc, then 3-yr revenue CAGR,
  then FCF margin, then ROIC. Take ≤8 per theme, ≤40 global.
- **UNION in current disruptor apex holders** (mirror `prep()`'s apex union, line 892-894): a held
  name is never dropped from the debate just because it aged out of the screen.
- The pre-rank ONLY decides who gets DEBATED. It never decides who gets PICKED — the Director picks
  (Do-NOT §10.2).

### 1.6 Output + anti-shrink guards

Write `backend/_opus_debate/disruptor/universe.json`:

```json
{ "built_at": "...", "taxonomy_version": "1.0",
  "funnel": { "screened": 412, "gated": 96, "mapped_high_med": 71, "debated": 38 },
  "by_theme": { "ai_infrastructure": 8, "energy_transition": 7, "...": 0 },
  "members": [ { "symbol": "...", "themes": [...], "value_chain_position": "...", "load_bearing_score": 4,
                 "gates": { "ttm_fcf": 1.2e9, "fcf_inflecting": false, "rev_cagr_3y": 0.24, "rev_yoy": 0.31,
                            "funded_solvency": "strong", "adv_usd": 5.4e7 } } ] }
```

Print the funnel counts every run. **GUARDS (mirror the SKILL's STEP 1 guard and the raw-screen
lesson)**: STOP and report degraded — do not proceed, do not reuse last month's members — if
`debated < 25`, OR any theme with historically ≥3 members maps to 0, OR the FMP screen returned
< 100 raw candidates (key/quota failure). Every monthly build re-screens FMP from scratch; the ONLY
carry-over from the prior month is the held-name union (§1.5). Sourcing from last month's
`universe.json` is the shrink loop and is forbidden.

---

## 2. Prep / bundle — `disruptor-prep` mode (weekly)

Mirror `prep()` (weekly_opus_refresh.py:846) with these deltas:

1. **Isolated subtree.** All run artifacts under `backend/_opus_debate/disruptor/`
   (`inputs/`, `transcripts/`, `results/`, `dossiers/`, `_archive_prev/`). The value pipeline's
   `prep()` self-clean archives `_opus_debate/results_regime/` + `dossiers/` + the regime apex —
   it must never touch the disruptor subtree, and vice versa.
2. **Universe staleness self-gate** (this is how "monthly" actually fires, §7.2): if
   `disruptor/universe.json` is missing or `built_at` > 21 days old, print
   `UNIVERSE STALE — run disruptor-universe first` and exit non-zero. The SKILL's STEP 3C runs the
   monthly rebuild only when this trips.
3. **Self-clean policy — selective, not total.** Unlike the value book (full weekly re-debate),
   archive to `disruptor/_archive_prev/` ONLY the results being re-debated this week (§3.1
   triggers). Cached, still-fresh debates stay in place — the Director re-grades over the union.
4. **Bundles**: per member, write `disruptor/inputs/<SYM>.json` with the same fields prep() writes
   (`symbol, sector, signal_type, company, metrics_str, methodologies→themes`), where
   `metrics_str = E._build_debate_metrics(financials=cand, scan_fin=scan_fin) + _fmp_segments(sym)`.
   For members present in `scans/latest_global.json`, populate `scan_fin` from
   `E._SCAN_FIN_FIELDS` exactly as prep() does (line 903) — this is the retired-signals firewall:
   `_SCAN_FIN_FIELDS` (live_debate_engine.py:811) deliberately excludes `hit_prob` and
   `factor_scores`. For members NOT in the scan (expected — different universe), build `scan_fin`
   from the Stage-B FMP fetches (revenue/margins/ROIC/net_debt) and leave scan-only fields absent
   (absent, never zero-filled). Set `signal_type: "disruptor"`.
5. **Transcripts**: identical to prep() lines 931-945 — `E.resolve_transcripts(sym)` (FMP
   `/stable/earning-call-transcript` + local cache, live_debate_engine.py:104), keep last 5
   quarters through `E._slice_transcript` (55% head / 45% tail), write
   `disruptor/transcripts/<SYM>.txt`. Names with no usable FMP transcript go to `ONLINE_SYMS` —
   the agent WebSearch/WebFetches the latest call/results, never skips, never fabricates (the
   no-pick-skipped rule).
6. **System prompts**: dump `E.INTERROGATOR_SYSTEM_PROMPT / ARCHITECT_SYSTEM_PROMPT /
   MODERATOR_SYSTEM_PROMPT` into `disruptor/` (idempotent copies, so a standalone disruptor run
   does not depend on the value prep having run first).
7. **Emit the workflow**: render `_DISRUPTOR_WORKFLOW_TEMPLATE` (§3) with `__SYMS__` /
   `__ONLINE_SYMS__` baked in (the args-delivery-bug workaround prep() already uses) →
   `backend/_opus_debate/disruptor/_disruptor_debate.js`. Print
   `DISRUPTOR PREP OK: <f> FMP + <o> online = <T> total (re-debating <R>, cached <C>)` and
   `DISRUPTOR_WORKFLOW_SCRIPT=<abs path>` for the skill to hand to the Workflow tool.

---

## 3. Debate workflow — `_disruptor_debate.js`

Clone `_WORKFLOW_TEMPLATE` (weekly_opus_refresh.py:988-1054) with these deltas; everything else —
batching, agentType, the seven-step debate prompt skeleton, "Reply exactly: DONE" — is copied
as-is because it is the pattern that proved reliable.

### 3.1 Weekly re-debate triggers (cost control without staleness)

A member is RE-DEBATED this week iff any of: (a) no cached `disruptor/results/<SYM>.json`;
(b) cached result older than 28 days; (c) an earnings report since the cached debate
(`days_to_earnings` flip or transcript date newer than result date); (d) |price move| ≥ 15% since
the cached debate's stamped price; (e) close < its published `thesis_break_px`; (f) it is a NEW
universe entrant. Everything else keeps its cached debate and is re-GRADED by the Director off
refreshed deterministic inputs (§5.1 rebuilds `disruptor_grade_input.json` fresh every week
regardless). Typical steady-state: 10-15 fresh debates/week; worst case (first run, monthly
rebuild week): all ~40.

### 3.2 Phases

- **No Radar phase** — the monthly theme map (§1.4) already produced peers/relative-comps;
  `meta.phases = [{title:'Debate'}, {title:'Director'}]`.
- **BRIEF replacement** (the one substantive prompt change): the value/regime BRIEF reads
  `CATALYST_WATCH_REGIME.md` and tilts toward dated catalysts; the disruptor BRIEF must NOT. New
  `BRIEF`:
  > "Read backend/_opus_debate/disruptor/theme_map/<SYM>.json — this name's assigned theme(s),
  > value-chain position, and true competitors. This is a PROFITABLE-DISRUPTOR debate, not a
  > catalyst debate: judge THEME DURABILITY (is the secular demand real and multi-year, or a
  > capex air-pocket away from rollover), the company's LOAD-BEARING position in the chain
  > (who can route around it, what breaks if it disappears), MOAT evidence (switching costs, IP,
  > network effects — use the GROSS-MARGIN TRAJECTORY as the lie detector: expanding GM on
  > growing revenue = pricing power; compressing GM = commoditization), and REINVESTMENT
  > economics (incremental ROIC, TAM headroom). A live catalyst is neither a plus nor a
  > requirement. In step 5, web-verify the THEME-LOAD-BEARING facts (backlog, hyperscaler/customer
  > capex guidance, design wins, order trends) as of today — catalyst_status is still emitted for
  > the record but must NOT drive the verdict."
- **Debate step 3** (peer comps) reads `disruptor/theme_map/<SYM>.json` instead of
  `peer_groups/<sym>.json`.
- **Result schema**: same fields as the regime results (so `compact_table.py` and the CSV
  exporters keep working) PLUS `themes` (list), `value_chain_position`, `load_bearing_score`,
  `gm_trajectory` (one line: direction + 3-yr numbers). `source` = `"opus_disruptor_mod"` /
  `"opus_disruptor_online"`; `signal_type` = `"disruptor"`. Written to
  `backend/_opus_debate/disruptor/results/<SYM>.json`.
- `BATCH = 8` kept verbatim (the 429 rate-limit lesson).
- **Director phase**: ONE Opus agent told exactly (mirroring SKILL STEP 3B's proven one-liner):
  "Read backend/_opus_debate/disruptor/disruptor_director_prompt.txt IN FULL and execute it over
  backend/_opus_debate/disruptor/disruptor_grade_input.json; write
  backend/_opus_debate/disruptor/apex_basket_disruptor.json EXACTLY per its schema; reply DONE."
- **`disruptor-finish` mode**: clone of `finish_debate()` (line 715) over the disruptor subtree —
  re-emit only the gap names after a partial outage.

---

## 4. DISRUPTOR_DIRECTOR_PROMPT — full text (module constant beside VALUE_DIRECTOR_PROMPT)

The grade-input builder (§5.1) writes this to `disruptor/disruptor_director_prompt.txt`, appending
the PRIOR-RUN MEASURED CORRELATIONS block exactly the way `value_input()` does (line 410-421).

```
You are the SPECULAIR DISRUPTOR DIRECTOR (Claude Opus 4.8), allocating REAL capital to PROFITABLE SECULAR DISRUPTORS — picks-and-shovels toll-takers in durable disruption themes — with the catalyst regime overlay FULLY REMOVED (a live catalyst is neither a plus nor a requirement) and with VALUATION AS A GUARD, NOT THE SCORE DRIVER. Read backend/_opus_debate/disruptor/disruptor_grade_input.json — one row per debated name, every field pre-computed.

SYSTEM OF RECORD (decisive — read FIRST). The multi-agent DEBATE already ran on each name. When the debate conflicts with the raw screen factors, THE DEBATE WINS:
  - `forensic_gate`: "EXCLUDE" => INELIGIBLE (interrogator credibility<=2 — a forensic red flag the factors miss). "CAP" => disruptor_score capped at ~50 (DETERIORATING trajectory: credible but worsening). A great theme story NEVER overrides the forensic gate.
  - `sop_mos_pct` (the CRO's reconciled fair value vs price) is the system-of-record valuation reference where present. For disruptors it is a GUARD input (pillar 4), not a ranking input: a deeply negative sop_mos_pct (price far above even the CRO's bull-leaning fair value) is a SIZE-CAP or VETO signal; a positive one is NOT extra score.
  - HARD GATES (pre-stamped, re-verify, never waive): `ttm_fcf_positive` must be true, OR `fcf_inflecting`=true AND the debate record cites explicit guidance/backlog evidence of FCF turning positive within 4 quarters — name every fcf_inflecting name you keep in the memo with that evidence, and set its size_units <= 0.5. `rev_growth_gate` must be true (>=15% 3yr CAGR or accelerating). `funded_solvency` must not be "weak" (same funded-debt basis as the value book: interest-bearing only, float/reserves excluded; IGNORE raw altman_z). A name failing a hard gate is INELIGIBLE no matter how good the theme story is — this book holds PROFITABLE disruptors, not moonshots.

RUBRIC — four pillars ~25 pts each, applied ONLY to names that clear the gates:
1. THEME DURABILITY & POSITION — from `themes`, `value_chain_position`, `load_bearing_score`, `s_curve_stage` + the debate's verified theme facts. Reward: multi-year secular demand verified against CURRENT orders/backlog (not narrative); a LOAD-BEARING chain position (hard to route around, structural content gains); `steep_ramp`/`broadening` S-curve stages. Penalize: theme exposure that is really ONE customer's capex line (check `customer_concentration` in the dossier); `early_adoption` stories priced as certainties; "AI-adjacent" relabeling of a cyclical business — the Interrogator dossier is your lie detector here.
2. MOAT & PRICING POWER — switching costs, IP, network effects, ecosystem lock-in, with the GROSS-MARGIN TRAJECTORY (`gross_margin`, `gm_trajectory`) as EVIDENCE, not vibes: expanding/holding GM while revenue compounds = priced power proven; compressing GM on rising revenue = commoditization in progress — cap pillar 2 at half marks no matter what the story says. Cross-check the debate's `true_competitors`: if credible competitors are taking share on price, say so and score accordingly.
3. REINVESTMENT RUNWAY & UNIT ECONOMICS — `roic_avg` (and its direction) as the return on INCREMENTAL capital, TAM headroom vs current share (from the debate, stated as numbers not adjectives), capex efficiency (revenue growth per unit of capex), `fcf_margin` trajectory. A toll-taker that can redeploy at >15% incremental ROIC for years deserves the score; a grower that needs $1 of capex for $1 of revenue does not.
4. GROWTH-ADJUSTED VALUATION GUARD — a GUARD, not a ranking pillar: full marks by default, DEDUCTIONS for danger. Inputs: `ev_gp` (EV / TTM gross profit), `rule_of_40` (revenue YoY % + FCF margin %), `sop_mos_pct`, `peak_flag`/`freshness_stale`. Apply: rule_of_40 < 40 => deduct; ev_gp rich vs the name's growth+GM profile (use the debate's peer comps; as a rough rail, ev_gp > ~1x its revenue growth rate in % is rich for hardware, software tolerates more) => deduct and consider a size cap; sop_mos_pct <= -40% => the CRO himself cannot get near the price — VETO or size_units <= 0.5 with explicit justification; peak_flag + decelerating revenue => the "growth" may be a cycle peak (the AI-capex air-pocket case) — treat multiple compression as the base case. The guard can VETO or CAP a name; it must NEVER be the reason a name ranks above another that passed the guard clean.

HARD CONSTRAINTS:
  - EXACTLY 8 apex picks (the Disruptor Lens is deliberately the SMALLEST, highest-volatility sleeve), ~5 runner_ups.
  - THEME CAPS: <=3 names per theme AND <=30% of basket weight per theme (by size_units share). A name carrying 2 themes counts toward BOTH. State the per-theme weights in theme_exposure.
  - <=3 names per GICS sector (the theme cap usually binds first; both apply).
  - Every pick must clear forensic_gate, every hard gate, and the valuation guard (possibly with a stated size cap).

THEME-CONCENTRATION STRESS (run over the final 8 BEFORE sizing — this is the PRIMARY axis; GICS sectors will NOT catch it because half this universe is "Technology"). Decompose the 8 on SHARED THEME/FACTOR exposure: (a) AI-CAPEX (the obvious cluster — semis, networking, power, cooling, EDA ALL ride the same hyperscaler capex line; a 2-quarter digestion pause hits every leg at once) — call this one out EXPLICITLY in every run; (b) CHINA / EXPORT-CONTROL exposure (revenue share + license risk); (c) RATE-DURATION (long-duration growth multiples compressing together when real rates rise); (d) SINGLE-CUSTOMER concentration (>=2 names with the same top customer); (e) SUPPLY-CHAIN chokepoint (e.g. one foundry's advanced nodes). FLAG every axis carrying >=2 names. For each: EITHER (i) DIVERSIFY — swap the lower-scoring leg for the best orthogonal eligible runner-up that does NOT re-cluster, OR (ii) keep both ONLY with an explicit combined-size cap + written justification. Every keep-with-cap MUST appear in `combined_caps` as NUMBERS (not prose): combined_caps:[{names:[...], max_units(float), axis(str)}] — prose-only caps are a spec violation. A single hyperscaler capex cut or one export-control ruling must not be able to hit more than 30% of this book.

OUTPUT — Write VALID JSON to backend/_opus_debate/disruptor/apex_basket_disruptor.json =
{apex_basket:[{symbol, sector, theme (primary id), themes (all ids), value_chain_position, disruptor_score(0-100), thesis(one sentence), theme_durability(one line), moat_evidence(one line incl. the GM-trajectory fact), reinvestment_runway(one line with numbers), valuation_guard(one line, e.g. "EV/GP 14x vs +38% rev — guard passes" or "rule-of-40=31 — capped"), rule_of_40(number), ev_gp(number), sop_mos_pct, ttm_fcf_positive(bool), fcf_inflecting(bool), net_funded_debt_ebitda, interest_coverage, funded_solvency, growth_durability, exposure_axes(list of shared axes this name carries, e.g. ["ai-capex","china-export-controls"]), size_units(float 0.1-1.5: 1.0=full unit; every fcf_inflecting name, guard-capped name, and combined-cap member MUST carry its number here), thesis_break_px(number: the price at which the THESIS is broken — derive it from a thesis-level break like a GM inflection, a lost flagship design, or theme-demand rollover, then express it as a price; below it the name exits at the next review), bear_fv_px(number: your adverse-case per-share value assuming the theme pauses 12-18 months — used for the market stress test), forensic_gate, hype_flag(bool: true if the price embeds a materially more aggressive S-curve than the evidence supports)}],
runner_ups:[...~5], combined_caps:[{names:[...], max_units(float), axis(str)}], theme_exposure:{<theme_id>: weight_pct}, disruptor_memo}.
The disruptor_memo MUST: (a) state the rubric weighting and that valuation acted only as a guard; (b) LIST the names EXCLUDED by the forensic gate, the hard gates (FCF/growth/solvency), and the valuation guard — with the one-line reason each; (c) name every fcf_inflecting keep and its cited evidence; (d) give the name-by-name RISE/FALL vs the prior disruptor apex (the caller specifies the prior basket in the run instruction; if none is given, read the existing backend/_opus_debate/disruptor/apex_basket_disruptor.json for the prior slate BEFORE you overwrite it); (e) a theme_concentration_stress section naming EACH >=2-name axis (ALWAYS including the AI-capex check, even if it carries <=1 name — say so) and EXACTLY how it was resolved (diversified -> which swap and why; or kept-with-cap -> the numbers). Reply exactly: DONE
```

---

## 5. Deterministic layer: grade-input → post → CSVs → publish → nightly mark

### 5.1 `disruptor-input` (mirrors `value_input()`, line 277)

Builds `disruptor/disruptor_grade_input.json` — one row per name in `disruptor/results/`, joining:
universe row (themes, value_chain_position, load_bearing_score, gates) + debate record (verdict,
conviction, interrogator_score, trajectory, sop_fair_value → `sop_mos_pct` via `_val_money()`
line 169, gm_trajectory) + theme map entry + deterministic metrics. Reuse VERBATIM from
`value_input()`: the forensic-gate derivation (iscore ≤ 2 → EXCLUDE; "DETERIORAT" in trajectory →
CAP — lines 363-371), `_funded_leverage`/`_funded_solvency`, peak/freshness flags
(`eps_peak_ratio`, `freshness_stale` — they still catch cyclical-peak "growth"). NEW computed
fields: `ttm_fcf_positive`, `fcf_inflecting`, `rev_growth_gate`, `rule_of_40` (revenue YoY % + TTM
FCF margin %), `ev_gp` (EV = mcap + net funded debt, over TTM gross profit; reuse Stage-B fetches),
`customer_concentration` (from the dossier when stated). Then writes
`disruptor_director_prompt.txt` = the §4 constant + the prior-run measured-correlation block read
from the existing `apex_basket_disruptor.json` `correlation` key (feed-forward, mirroring lines
410-421). Prints gate counts (n_gate_fails by gate) — visible funnel, never silent.

### 5.2 `_disruptor_post.py` (parameterized clone of `_value_post.py` — what to reuse vs change)

`backend/_opus_debate/_disruptor_post.py`. Same shape: validate/stamp AFTER the Director, BEFORE
CSV/publish; NEVER changes membership (P1); idempotent via `--offline` + a run cache.

| `_value_post.py` piece | Disruptor treatment |
|---|---|
| File constants (`APEX_F`, `GIN_F`, `RES_DIR`, `CACHE_F`) | **Parameterize** → `disruptor/apex_basket_disruptor.json`, `disruptor/disruptor_grade_input.json`, `disruptor/results/`, `disruptor/_disruptor_post_cache.json` |
| `live_quotes` / `weekly_logrets` / `get_market` (FMP batch-quote + `get_chart(days=760)` + ISO-week resample + cache) | **Copy verbatim** |
| `stamp_cro_only` (fix 2) | **Replace** with `stamp_gate_caps`: clamp `size_units ≤ 0.5` for `fcf_inflecting` and `hype_flag` names (the disruptor analogues of a CRO-only leg) |
| `stamp_stale_anchor` (fix 3) | **Copy** (stale + peak + FIRED still means a pre-event anchor) |
| `build_weights` (size_units clamp 0.1-1.5 → combined_caps scaling → normalize → `weight_pct`) | **Copy verbatim**; drop the `MEMO_UNITS_20260609` one-off map (Director emits structured size_units from day 1 here) |
| NEW: `enforce_theme_caps` | **New function**: from each pick's `themes`, deterministically verify ≤3 names AND ≤30% weight per theme; on breach, append `{names: <theme members>, max_units: 30% of total units, axis: "theme:<id>"}` to extra_caps and rebuild weights — the deterministic backstop to the Director's promise |
| `stress_block` (fix 1: weighted return to 52w-lows, lows−15% recession, CRO bear; published = worst valid) | **Copy verbatim** (`bear_fv_px` feeds it, same as value) |
| `corr_block` (fix 4: 2y weekly log-returns Pearson, ≥60 common weeks, flag ≥0.6, breach = ≥0.7 AND >16% combined weight, cap at 1.5 units) | **Copy**, with the beta benchmark **parameterized**: `["SMH", "QQQ"]` instead of `XLY` (AI-capex/long-duration beta is this book's systematic risk, not consumer). Emit `theme_beta = {sym: {smh, qqq}}` |
| `stamp_entry_plans` / `exits_block` (thesis_break_px sanity 0 < tb < px) | **Copy verbatim** |
| `gate_sync` (fix 7, cross-surface demotion) | **Drop** — the disruptor universe barely overlaps the regime/value books; cross-book demotion across different universes is out of scope v1. Instead: if a disruptor EXCLUDE symbol also appears in the regime or value apex, PRINT a loud warning for the operator. |
| `main()` ordering | **Copy** (stamps → provisional weights → corr → breach caps → **theme caps** → final weights → recompute corr → entry plans → stamp `weights/stress_test/correlation/exits/theme_exposure` → write) |

Dispatch: `weekly_opus_refresh.py disruptor-post [--offline]` runs it via subprocess, mirroring the
`value-post` branch (line 1073-1075).

### 5.3 `disruptor-csv`

Clone `value_csv()` (line 435) over the disruptor subtree → `disruptor/speculair_disruptor_apex.csv`
+ `speculair_disruptor_apex_memo.txt`. Column deltas: add `theme, themes, value_chain_position,
load_bearing_score, rule_of_40, ev_gp, gm_trajectory, hype_flag, fcf_inflecting,
theme_exposure_pct`; drop the value-only `mos_agreement*`, `cro_only`, `in_regime_apex` columns.
Do NOT extend `baskets_csv()` — it joins the value/regime universe; the disruptor book is a
different universe and merging the files would imply a shared pool (§10.9).

### 5.4 `disruptor-publish [--gcs]` (mirrors `value_publish()`, line 638)

1. Read `disruptor/apex_basket_disruptor.json`; `track_in = [{**p, "conviction": p["disruptor_score"]}]`.
2. Equal-weight NAV chain: `E._update_apex_tracking(track_in, push_gcs=False,
   gcs_path="scans/speculair_disruptor_tracking.json", local_name="speculair_disruptor_tracking.json")` —
   the signature already supports third books (live_debate_engine.py:2050: `gcs_path`, `local_name`,
   `weights` params). Weighted variant with `weights=apx["weights"]` →
   `scans/speculair_disruptor_tracking_weighted.json` / `speculair_disruptor_tracking_weighted.json`.
3. Attach `entry_price`/`entry_date` per pick from the tracking positions (value_publish lines
   663-674 pattern) so the card shows per-pick performance.
4. `pool_stats` honest banner (mirror lines 675-687), disruptor wording — this text feeds the §6
   card banner: `"Highest-volatility sleeve: <n> profitable secular-theme names from a <N>-name
   thematic screen (taxonomy v<X>). Long-duration growth multiples — expect drawdowns ~2x the
   value book's; sized as the SMALLEST sleeve by design and never blended into the Apex or Value
   NAVs."` Include `n_pool`, `verdict_counts`, `n_hard_gate_fails`, `taxonomy_version`.
5. Write `frontend/public/speculair_disruptor_apex.json` =
   `{apex_basket, runner_ups, disruptor_memo, disruptor_tracking, disruptor_tracking_weighted,
   weights, stress_test, correlation, exits, combined_caps, theme_exposure, pool_stats,
   generated_at, engine: "opus-4.8-disruptor-theme-v1", universe: <debated count>,
   taxonomy_version}`.
6. `--gcs`: push the three files via `gcloud storage cp` shell=True (value_publish lines 700-711
   pattern — Windows gcloud.cmd resolution), then a LIVE readback via `gcloud storage cat`
   (publish_to_frontend.py:336-344 pattern — the public URL can serve a stale cache right after a
   write).

**PRICE-COVERAGE CHECK (new, mandatory)**: before writing, look up every member in
`scans/latest_global.json` (the file `_current_prices` marks from) and print
`off-scan members (FMP-quote fallback will price them): [...]`. See §5.5.

### 5.5 Nightly NAV mark — `backend/screener_v6.py::_mark_speculair_nav()` (+ redeploy)

The ONLY production-scan change in this whole build. Two edits in `screener_v6.py`:

1. **Third tuple** in the loop list at line ~6212:
   ```python
   ("disruptor", "scans/speculair_disruptor_apex.json",
    "scans/speculair_disruptor_tracking.json", "speculair_disruptor_tracking.json"),
   ```
   (the loop body is already generic; equal-weight chain only, matching the value book — the
   weighted chain refreshes weekly at publish, same as value today).
2. **Price fallback for off-scan members** — `live_debate_engine.py::_current_prices()` (line
   2017) prices EXCLUSIVELY from `scans/latest_global.json`. Disruptor members outside the
   production scan universe would otherwise silently contribute nothing to the daily mark (their
   legs go stale, the NAV quietly under-counts). Additive fix in `_current_prices`: after the scan
   lookup, for any still-missing requested symbols, batch-quote them from FMP
   (`/stable/batch-quote`, chunked 50 — the `_value_post.live_quotes` pattern, key via
   `get_key("FMP_API_KEY")`); merge into the result. Strictly additive: when every symbol is in
   the scan (apex + value books today), behavior is byte-identical.

**Deploy note (memory lessons apply)**: these ship in the deployed `screener-sp500` Cloud Run job.
The `stock-screener-2026` trigger fails every push (no root Dockerfile) — after pushing, redeploy
the job from `--source backend` and **verify the job's image digest equals the newest built digest
before firing it** (build-success ≠ job-updated). Until the redeploy lands, the disruptor card
shows weekly-stepped NAV (publish-time marks only) — acceptable interim, not an error.

---

## 6. Frontend — the purple card (`frontend/app/page.tsx`)

Mirror the Value Lens card exactly; all anchors verified:

1. **State** (beside lines 2193-2195): `const [disruptorApex, setDisruptorApex] = useState<any>({});`
   `const [expandedDisruptor, setExpandedDisruptor] = useState<Set<string>>(new Set());`
   plus `const [disruptorPrices, setDisruptorPrices] = useState<Record<string, number>>({});`
2. **Fetch effect** (clone of lines 2214-2224): `/api/gcs/scans/speculair_disruptor_apex.json` →
   catch → `/speculair_disruptor_apex.json` public fallback.
3. **Quote top-up effect (REQUIRED, unlike the other two cards)**: the value card reads current
   price via `findStock(pick.symbol)` from the loaded scan — disruptor members are often NOT in
   that scan. Clone the methodology-holdings quote effect (lines 2249-2268):
   batch `/api/fmp?e=quote&symbol=<csv>` (chunk 50) for all constituents → `disruptorPrices`;
   per-pick price = `findStock(...)?.price ?? disruptorPrices[sym]`.
4. **Card placement**: in the Speculair tab, immediately AFTER the Value Lens card's closing
   `</div>` (line ~3051) and BEFORE the `{/* Capitulation Watchlist */}` comment (line 3053).
   Container: `border: "1px solid var(--purple)"` (green=Apex line 2813, blue=Value line 2917,
   orange=Capitulation line 3054 — purple completes the set).
5. **Card contents** (clone the Value card's blocks, lines 2917-3051):
   - Header: "Speculair Disruptor Lens" + right-aligned
     `{n} names · profitable disruptors · theme-capped ≤30%` in `var(--purple)`.
   - Subtitle line: "A separate ~40-name thematic screen (NOT the 161-name value universe):
     FCF-positive secular-theme toll-takers, graded on theme position, moat and reinvestment
     runway — valuation as a guard. Own NAV chain; never blended with the Apex or Value books."
   - **Honest banner — REQUIRED, mirror the `pool_stats.banner` block (lines 2956-2960)** rendering
     `disruptorApex.pool_stats.banner` (the highest-vol-sleeve text staged by §5.4.4), styled with
     the amber/warning treatment rather than the muted-italic of the value banner.
   - Live track record block + sparkline: clone lines 2929-2949 against
     `disruptorApex.disruptor_tracking` (footnote: "equal-weight NAV · live-forward, not
     back-filled · highest-vol sleeve").
   - Stress line: clone 2951-2955 (`stress_test.published_downside_pct`, `basket_to_52w_lows_pct`,
     `correlation.avg_pairwise` + breach) and append theme line:
     `top theme {maxTheme} {pct}% (cap 30%)` from `theme_exposure`.
   - Pick tiles: clone 2962-3040 — badge `dis {disruptor_score}/100`, `wt {weight_pct}%`, chips:
     primary `theme` (purple), `value_chain_position` (gray), `rule-of-40 {n}` (green ≥40 / amber
     <40), `½ size` when `fcf_inflecting || hype_flag` (reuse the title-tooltip pattern), `corr`
     flag, GM-trajectory chip. Right-aligned headline number: per-pick performance vs
     `entry_price` (the Apex card's perf pattern, lines 2846-2867) — NOT MoS (this book is not a
     MoS book). Thesis expander keyed `expandedDisruptor`, prefix `DISRUPTOR` in purple.
   - Runner-ups line: clone 3045-3050.
6. **Stock-page links**: tiles use the same `setChartCard(... href: /stock/<sym>?tab=debate)`
   pattern; disruptor debates publish per-symbol history the same way (§7.1 STEP 3C runs the same
   history appender), so the debate tab works for any member with a published debate.
7. **Verification**: `tsc` + `preview_eval` DOM reads — preview screenshots are flaky on `/`
   (memory note), don't gate on them.

---

## 7. Skill / cadence integration

### 7.1 Decision: STEP 3C inside the existing weekly skill (not a separate scheduled task)

**Decision**: the Disruptor Lens runs as **STEP 3C** of
`C:\Users\Bruno\.claude\scheduled-tasks\speculair-opus-weekly\SKILL.md`, after STEP 3B, in the same
Sunday 01:00 session. The monthly universe rebuild self-gates INSIDE STEP 3C via the 21-day
staleness check (§2.2) — no second scheduled task.

**Why** (vs a separate cadence): (a) one session already carries the operating rules, allowlist,
and guard discipline — a second task would duplicate and inevitably drift; (b) all three books
then rotate on the same day, so cross-book comparisons (and the three cards' "since" dates) read
cleanly; (c) failure isolation is preserved by ORDER: STEP 3C runs last, so a disruptor failure
can never degrade the two already-published books (the SKILL's existing STEP 3B guard wording —
"the regime/catalyst book from STEP 3 is independent and already live" — extends verbatim);
(d) the debate-reuse triggers (§3.1) make the weekly marginal cost small enough to share the
session (§8); (e) the monthly stage is self-gating, so "monthly" cannot be forgotten — it fires
exactly when the universe is stale.

**SKILL.md edit** — insert after STEP 3B, before STEP 4:

> STEP 3C — DISRUPTOR LENS (separate thematic universe; ~10-20 min steady-state, ~45-60 min on a
> monthly-rebuild week). Run: `python backend/weekly_opus_refresh.py disruptor-prep`.
> If it prints `UNIVERSE STALE`, first run `python backend/weekly_opus_refresh.py disruptor-universe`,
> then Workflow the printed theme-map script, then `python backend/weekly_opus_refresh.py disruptor-map-merge`,
> then re-run disruptor-prep. GUARD: if disruptor-universe prints debated < 25 or a 0-member core
> theme → STOP the disruptor step and report (the Apex and Value books are already live).
> Then: Workflow({scriptPath: <DISRUPTOR_WORKFLOW_SCRIPT>}) → `disruptor-input` → ONE Opus subagent
> ("Read backend/_opus_debate/disruptor/disruptor_director_prompt.txt IN FULL and execute it over
> backend/_opus_debate/disruptor/disruptor_grade_input.json; write
> backend/_opus_debate/disruptor/apex_basket_disruptor.json EXACTLY per its schema; reply DONE")
> → `disruptor-post` → `disruptor-csv` → `disruptor-publish --gcs`.
> GUARD: <6 apex names or GCS push FAILED → re-run publish once; if still failing, report and stop
> (never publish a degraded disruptor basket; the other two books are unaffected).
> STEP 4 addition: also report the DISRUPTOR apex 8 (disruptor_score + theme + how the
> theme-concentration stress resolved, esp. the AI-capex axis) and the three-book overlap (any
> symbol in 2+ books is a cross-lens conviction).

**Allowlist**: all new commands are `python backend/weekly_opus_refresh.py <mode>` — they ride the
EXISTING wildcard `Bash(python backend/weekly_opus_refresh.py *)` in `.claude/settings.json`
(line 46). Zero permission changes for the hands-off run. (This is the deciding reason the modes
live in `weekly_opus_refresh.py` rather than a new sibling driver file, mirroring how the value
book was added.)

### 7.2 Cadence: theme membership monthly, grading weekly — justification

- **Membership monthly**: theme membership moves on a quarters-to-years timescale (S-curves,
  listings, FCF inflections) — a weekly FMP re-screen + Sonnet re-map would re-derive a ~99%
  identical set at 4x the screening/mapping cost and add weekly churn noise to the universe
  funnel. Monthly catches a new entrant within ≤4 weeks, which is faster than any secular thesis
  develops. The held-name union (§1.5) guarantees a holding can never be orphaned between rebuilds.
- **Grading weekly**: (a) thesis-break exits are enforced at review time — the exits block's
  contract is "weekly refresh OR close < thesis_break_px" (`_value_post.exits_block`); monthly-only
  grading would let a broken thesis sit un-acted for up to 4 weeks in the book's most volatile
  sleeve; (b) NAV rotation stays aligned with the other two books; (c) earnings season lands
  mid-month — the §3.1 triggers re-debate exactly the names with new information, so weekly grading
  buys freshness without weekly full-universe debate cost.

---

## 8. Cost / runtime budget

Grounded in the value book's actuals: **~60-95k tokens per debate agent; ~150-180k for a Director
pass**; value's weekly run ≈ 45-50 debates.

| Step | Agents × tokens | Total | Model | Cadence |
|---|---|---|---|---|
| Universe Stage A+B (FMP screen + gates) | 0 LLM (~400-600 FMP calls, cached per month) | 0 | — | monthly |
| Stage C theme map | ~5-8 Sonnet agents × 30-50k | ~0.2-0.4M | Sonnet | monthly |
| Debates — steady state (triggers §3.1) | 10-15 × 60-95k | ~0.6-1.4M | Opus | weekly |
| Debates — monthly-rebuild week / first run | ~40 × 60-95k | ~2.4-3.8M | Opus | monthly peak |
| Disruptor Director | 1 × 150-180k | ~0.15-0.18M | Opus | weekly |
| disruptor-input / post / csv / publish | 0 LLM | 0 | — | weekly |

**Relative load**: the existing Sunday session runs ~45-50 debates (~3-4.7M Opus) + regime Director
+ value Director (~0.3-0.36M). STEP 3C adds **~+20-30% on a typical Sunday** (0.75-1.6M) and
**~+80-100% on a monthly-rebuild Sunday** (2.5-4M). Wall-clock at `BATCH=8`: steady-state ~2
debate batches (~12-20 min) + Director (~5-8 min) + deterministic steps (~4-6 min) ≈ **+20-35
min**; monthly ~5 batches ≈ **+45-70 min**. All on Claude Code subscription subagents — zero
Anthropic API spend (the cross-model engine path stays out of scope). FMP: weekly ~150-300 calls
(transcripts ≤8/name on misses + segments + quotes), monthly +~500 — well inside the existing key's
budget. If the session ever pressures the subscription's weekly token envelope, the pressure valve
is the §3.1 trigger thresholds (28d→42d, ±15%→±20%) — NOT shrinking the universe builder.

---

## 9. Phased rollout — acceptance criteria per phase

**Phase 0 — Taxonomy + scaffolding (no LLM)**
Create `disruptor_themes.json` v1.0 (7 themes; each with ≥1 fmp_sector/industry mapping +
anchor_examples) and the `disruptor/` subtree.
*Accept*: JSON validates against §1.1 schema; Bruno has reviewed/edited the taxonomy; subtree
exists; `py_compile backend/weekly_opus_refresh.py` clean.

**Phase 1 — Universe builder (`disruptor-universe` + theme-map workflow + `disruptor-map-merge`)**
*Accept*: full funnel prints (screened → gated → mapped → debated); 25 ≤ debated ≤ 40; every
member's `gates` block shows passing values; every member has a `theme_map/<SYM>.json` with
`load_bearing_score` + `true_competitors`; `theme_fit_confidence=low` drops are PRINTED with
symbols; guards verified by simulation (point Stage A at one theme only → expect STOP, not a
silent small universe); zero reads of any prior `universe.json` in the build path (code review).

**Phase 2 — Prep + debate (`disruptor-prep`, `_disruptor_debate.js`, `disruptor-finish`)**
*Accept*: `DISRUPTOR PREP OK` line with FMP/online split; staleness gate trips at >21d; bundles for
off-scan names carry FMP-derived `scan_fin` with NO `hit_prob`/`factor_scores` keys anywhere in
`inputs/*.json` (grep check); after the Workflow: `results/*.json` count ≥ 90% of debated, every
record parses with the §3.2 schema incl. `themes`/`gm_trajectory`; online names tagged
`transcript_source="web"`; re-run of the same workflow only fills gaps (cache behavior);
value-book regression: `prep()` self-clean leaves `disruptor/` untouched (run both, diff subtree).

**Phase 3 — Director + post (`disruptor-input`, §4 prompt, `_disruptor_post.py`)**
*Accept*: `disruptor_grade_input.json` row count == results count, gate-fail counts printed;
Director writes valid JSON: exactly 8 picks, every pick carries numeric `size_units`,
`thesis_break_px`, `bear_fv_px`, `rule_of_40`, `ev_gp`; no pick with `forensic_gate=EXCLUDE` or
`funded_solvency=weak` or failed FCF/growth gates; `combined_caps` numeric; `theme_exposure` sums
≈100%. Post: weights sum to 1.0000±0.001; ≤3 names and ≤30% weight per theme AFTER post (assert in
test by feeding a synthetic 4-names-one-theme basket → expect deterministic cap);
`disruptor-post --offline` re-run is byte-identical; `exits` sanity warnings fire on a synthetic
`thesis_break_px > price`.

**Phase 4 — Publish + tracking + CSVs (`disruptor-publish`, `disruptor-csv`)**
*Accept*: `frontend/public/speculair_disruptor_apex.json` carries every §5.4.5 key incl.
`pool_stats.banner` + `taxonomy_version`; first run prints tracking inception
(`nav=100.x`, `n_open=8`); weighted state file exists; `--gcs` push prints 3× OK + a LIVE readback
showing the 8 symbols; off-scan members are listed by the price-coverage check; re-running publish
the same day does not double-rotate (one entry per date in tracking history); CSV rows == picks
and memo txt non-empty; `scans/speculair_value_*` and `scans/speculair_baskets.json` byte-identical
before/after the whole STEP 3C (cross-book isolation proof).

**Phase 5 — Nightly mark + redeploy (the only production-scan change)**
*Accept*: third tuple present in `_mark_speculair_nav()`; `_current_prices` FMP fallback covers a
synthetic off-scan symbol locally; `screener-sp500` redeployed from `--source backend` and the
job's image digest == newest build digest VERIFIED before firing (memory lesson); next nightly log
shows `Speculair disruptor NAV marked: nav=...`; apex+value marks unchanged vs prior night's
pattern; disruptor tracking history grows one point per day thereafter.

**Phase 6 — Frontend card**
*Accept*: purple card renders between Value Lens and Capitulation Watchlist from the GCS route and
ALSO with the route blocked (public fallback); every pick tile shows a live price (off-scan names
priced via the quote top-up); the honest banner renders; `tsc --noEmit` clean; DOM verified via
`preview_eval` (not screenshots); Vercel deploy verified after push (shared-dir memory note:
fetch+diff before committing `page.tsx`, commit promptly).

**Phase 7 — SKILL integration + first hands-off run**
*Accept*: STEP 3C text merged into SKILL.md + STEP 4 reporting extended; confirmed every STEP 3C
command matches the existing `weekly_opus_refresh.py *` wildcard (settings.json:46); one full
unattended Sunday run completes: both old books publish first, disruptor publishes after, report
includes the three-book overlap; a forced STEP 3C failure (rename universe.json) stops ONLY the
disruptor step and says so in the report.

---

## 10. Do-NOTs

1. **Never feed retired signals.** `hit_prob` (ML) and `factor_scores` (13-factor radar) are
   deprecated and still linger in `latest_global.json` — the bundle builder must source scan
   fields ONLY through `E._SCAN_FIN_FIELDS` (which excludes them by design,
   live_debate_engine.py:811-825). Phase-2 acceptance greps for them in `disruptor/inputs/`.
2. **Deterministic guards never pick members.** Gates (FCF/growth/solvency/ADV) decide
   ELIGIBILITY; the Stage-D pre-rank decides who gets DEBATED; theme/correlation caps bound
   SIZING. Only the Opus Director selects the 8. No code path may auto-promote a runner-up.
3. **The universe builder must never silently shrink** (the raw-screen-source lesson,
   2026-06-06): every monthly build re-screens FMP from scratch; never source candidates from a
   prior `universe.json` or from published baskets; funnel counts always printed; thin screens
   STOP loudly (guards §1.6). The only survivor carry-over is the held-name union.
4. **Never blend the third NAV.** Separate state files (`speculair_disruptor_tracking*.json`),
   separate GCS paths, separate card. Never write to `scans/speculair_apex_tracking.json` /
   `scans/speculair_value_tracking*.json`, never aggregate the three NAVs into any combined
   number, anywhere.
5. **Never deploy the weekly pipeline to Cloud Run.** Debate/grade/publish run LOCALLY on Claude
   Code (standing instruction). The ONLY production-scan edits permitted are §5.5's two surgical
   changes (third tuple + `_current_prices` fallback) — nothing else in `screener_v6.py`, and the
   fallback must be a no-op when all symbols are in the scan.
6. **Do not mutate the value book's surfaces.** `VALUE_DIRECTOR_PROMPT`, `value_input()`,
   `_value_post.py` are NOT to be edited or "generalized" in place — `_disruptor_post.py` is a
   parameterized COPY (§5.2). The two books must remain independently runnable and independently
   breakable. (Refactoring both posts onto a shared lib is a later, separate task.)
7. **prep()'s self-clean and the disruptor self-clean must never cross subtrees** —
   `results_regime/`+`dossiers/` belong to the value/regime run; `disruptor/` belongs to STEP 3C.
8. **Valuation never ranks.** Pillar 4 may veto or cap; if a diff shows picks ordered by
   `ev_gp`/`rule_of_40`/`sop_mos_pct`, the Director run is non-conforming — reject and re-run.
9. **Do not merge disruptor rows into `baskets_csv()`/`speculair_baskets.json`'s
   per-methodology overlay** — different universe, different pool; implying a shared pool corrupts
   both books' funnels. The disruptor CSV stands alone.
10. **Never publish degraded.** <6 picks, failed gates in the apex, theme cap breach after post,
    or GCS push failure after one retry → report and stop. The catalyst+value books are live by
    then; a missing disruptor week is fine, a corrupt one is not.
11. **Never fabricate.** Online-fetch debates with thin evidence cap conviction and say so (the
    existing rule); `fcf_inflecting` keeps REQUIRE cited guidance/backlog evidence in the memo.
12. **Theme taxonomy lives in `disruptor_themes.json` only** — never hardcode theme lists,
    industry filters, or anchor tickers in Python/JS; the file is versioned and the version is
    stamped through to the published payload.

---

## Appendix A — full file map (create vs modify)

| Action | Path | What |
|---|---|---|
| CREATE | `backend/_opus_debate/disruptor_themes.json` | §1.1 versioned taxonomy |
| CREATE | `backend/_opus_debate/disruptor/` subtree | `universe.json`, `theme_map.json` + `theme_map/<SYM>.json`, `_dt_*.json`, `_gates_cache.json`, `inputs/`, `transcripts/`, `results/`, `dossiers/`, `_archive_prev/`, `_disruptor_debate.js`, `disruptor_grade_input.json`, `disruptor_director_prompt.txt`, `apex_basket_disruptor.json`, `_disruptor_post_cache.json`, `speculair_disruptor_apex.csv`, `speculair_disruptor_apex_memo.txt` |
| CREATE | `backend/_opus_debate/_disruptor_post.py` | §5.2 parameterized post-layer |
| MODIFY | `backend/weekly_opus_refresh.py` | new modes in `__main__` dispatch (line ~1057): `disruptor-universe`, `disruptor-map-merge`, `disruptor-prep`, `disruptor-input`, `disruptor-post`, `disruptor-csv`, `disruptor-publish [--gcs]`, `disruptor-finish`; constants `DISRUPTOR_DIRECTOR_PROMPT` + `_DISRUPTOR_WORKFLOW_TEMPLATE`; reuses in-module `_funded_leverage`/`_funded_solvency`/`_val_money`/`_fmp_segments` |
| MODIFY | `backend/screener_v6.py` | third tuple in `_mark_speculair_nav()` (~line 6212) |
| MODIFY | `backend/live_debate_engine.py` | `_current_prices()` additive FMP batch-quote fallback (~line 2042) |
| MODIFY | `frontend/app/page.tsx` | §6 state + fetch + quote top-up + purple card between lines ~3051/3053 |
| MODIFY | `C:\Users\Bruno\.claude\scheduled-tasks\speculair-opus-weekly\SKILL.md` | STEP 3C + STEP 4 reporting |
| DEPLOY | Cloud Run job `screener-sp500` | redeploy from `--source backend`; verify image digest before firing |
| GCS (new objects) | `scans/speculair_disruptor_apex.json`, `scans/speculair_disruptor_tracking.json`, `scans/speculair_disruptor_tracking_weighted.json` | bucket `screener-signals-carbonbridge` (`gcs_io.GCS_BUCKET`) |
