# FUTURE RESOURCES — Build Spec (v1.1, 2026-07-02)

> **Status**: SPEC + Phase-1 slice. The chain taxonomy (`backend/_opus_debate/future_resources_chains.json`)
> and the Stage-A/B universe builder (`fr-universe` mode) ship with this spec; everything from Phase 2
> onward is design-locked but unbuilt. Structure and rigor model: `THEMATIC_DISRUPTOR_SPEC.md`.
>
> **What this builds**: a hybrid two-lane basket — **"Future Resources"** — the tracked container for
> the physical build-out of the future: the inputs (uranium/nuclear fuel cycle, copper/electrification,
> rare earths & strategic metals), the power (power-for-AI), and the machines the inputs feed
> (robotics & physical AI, quantum). Six value chains at v1.1. This basket **replaces the Disruptor
> Lens**, which is retired (§10) — its robotics theme migrates here; its energy_transition ground is
> inherited by the power_for_ai chain. Lithium/battery is deliberately excluded until the oversupply
> clears (a regime tripwire, §4, decides when to revisit).
>
> **The one rule that keeps this basket honest — the PHYSICAL-ANCHOR RULE**: every member must make,
> move, power, or directly instrument a physical thing (quantum hardware counts; a payments network
> never does). The Disruptor Lens died picking Visa — an industry-filtered "theme" book with
> profitability gates but no physical anchor re-derives the generic S&P quality-compounder factor.
> The chain map (§2) enforces this rule per name, and any pick whose revenue is not physically
> anchored is a mapping error, printed and dropped.

---

## 0. Executive summary

### 0.1 Why this basket exists

The system has a hole exactly where the next decade's physical scarcity lives. The disruptor taxonomy's
`energy_transition` theme touches grid/solar/uranium equipment, but there is **no mining or
critical-minerals coverage anywhere** — and the disruptor profitability gates (TTM FCF > 0, ≥15% revenue
growth) exclude most miners **by design**. Meanwhile the machinery this repo already runs is unusually
well-suited to the sector:

- **Catalyst Watch's Bloom gates** map 1:1 onto mining events (§6.2) — and mining is the most
  catalyst-dense sector in the market.
- **The Interrogator credibility ban and Skeptic demotion** are worth more here than in any existing
  book: mining is where promoters live.
- **The regime-doc pattern** (`CATALYST_WATCH_REGIME.md`) is exactly the right shape for commodity
  cycles, which are slower and more legible than deal windows.

### 0.2 The four alpha engines (why this is edge, not beta)

1. **Dated resource catalysts (Lane B).** Permit rulings (Records of Decision), Final Investment
   Decisions, feasibility studies (PFS/DFS), first production, signed offtakes, government awards
   (DPA Title III, DOE LPO). These pass the existing Bloom gates cleanly: G1 named counterparty = the
   regulator/DoD/offtaker; G2 concrete commitment = the signed contract or filed study; G3 unpriced
   figure = feasibility NPV vs current EV. The structural mispricing is the **Lassonde curve**:
   developers systematically de-rate in the "orphan period" between discovery and construction, then
   re-rate into dated milestones. Buying late-orphan names ahead of a dated milestone is a repeatable,
   analyzable edge — the special-sits playbook applied to rocks.
   *Carve-out note*: `_post_board.py::canon_lane` today tags commodity names `Commodity_price` — i.e.
   macro bets that fail the board's "idiosyncratic, not a macro bet" filter. The new lane's entire job
   is separating the **idiosyncratic** mining events (a permit resolves on its own docket, whatever
   copper does that day) from commodity-price beta. Score ≠ edge applies verbatim: a real FID with the
   NPV already in the price is spent fuel.
2. **Strategic-policy repricings.** Export controls, Section 232 rulings, critical-minerals lists,
   DoD price floors (the MP Materials playbook). A government acting as a **forced buyer** is the
   mirror image of the board's #1 forced-seller lane, with the same structural asymmetry: the buyer is
   price-insensitive, on a public timeline, and pre-announced. These are datelined events, not vibes.
3. **Margin torque / cost-curve position (Lane A).** Deterministic from FMP fundamentals: a producer
   whose cost sits just below spot has 3–5x FCF leverage to a modest commodity move; one far down the
   cost curve is a bond. §3 defines the proxy metrics (no AISC endpoint exists — we build honest
   approximations and say so). This is a rankable, non-narrative edge input the debate can't hallucinate.
4. **Contracting-cycle / regime timing.** Term-contracting state (uranium's term-vs-spot is the
   canonical cycle tell), inventories, futures-curve shape, COT positioning, policy datelines — one
   living regime doc per the four chains (§4), refreshed bi-weekly, read by every debate.

### 0.3 Locked design decisions

1. **Hybrid two-lane.** Lane A: profitable producers + royalty/streamers — book-style weekly debate,
   torque-scored, own NAV chain (later phase). Lane B: pre-FCF developers with dated catalysts —
   Catalyst-Watch-style mini-sweep + Basket-13 discipline (append-only tracker, event-resolution
   semantics, hard caps in code). **The two lanes are never blended into one NAV.**
2. **Developers allowed, defined-risk only**: dated milestone ≤ 9 months out, funded through the
   milestone (`runway_months ≥ months_to_milestone × 1.5`, enforced deterministically), half-sized,
   skeptic-verified upstream. Sub-$300M names usually lack sane options — the half-size equity default
   is code-enforced, never left to the LLM.
3. **Scope**: the six chains in `future_resources_chains.json` v1.1 — four commodity/power chains plus
   two machine chains (robotics & physical AI, quantum) added when the Disruptor Lens was retired
   (§10). US listings only (NYSE/NASDAQ/**AMEX** — the uranium/RE cohort lists on NYSE American). Both
   constraints are honest limits stated on the card: much copper/RE developer alpha lists on TSX/ASX
   and is out of scope v1.
4. **Valuation discipline inherits per lane**: Lane A uses the debate chain's CRO fair value as a
   guard (disruptor-style — torque is the driver, valuation can veto/cap); Lane B uses the board's
   edge grading (score ≠ edge — catalyst density never substitutes for mispricing).
5. **Reuse over invention.** The debate chain, the 3-tier sweep mechanics, the Basket-13 tracker, the
   regime-doc protocol, `_funded_leverage`/`_funded_solvency`, and the post-layer patterns are all
   cloned or parameterized — never edited in place (the two-books-independently-breakable rule).

### 0.4 New surface at a glance

| Artifact | Path | Phase |
|---|---|---|
| Chain taxonomy (versioned config, never code) | `backend/_opus_debate/future_resources_chains.json` | **shipped** |
| Universe builder Stage A/B | `weekly_opus_refresh.py` → `fr-universe` mode | **shipped** |
| Run subtree | `backend/_opus_debate/future_resources/` | **shipped** (created by fr-universe) |
| Chain-map workflow + merge | `future_resources/_fr_map.js` (emitted) + `fr-map-merge` mode | 2 |
| Torque metrics | `backend/_opus_debate/_resource_metrics.py` | 2 |
| Regime layer | `FUTURE_RESOURCES_REGIME.md` + `future_resources/regime_state.json` | 2 |
| Lane A debate/Director/post | `fr-prep`, `fr-input`, `FR_DIRECTOR_PROMPT`, `_fr_post.py`, `fr-post/csv/publish` | 3 |
| Lane B mini-sweep | `backend/_fr_sweep.py` + `_fr_universe.json` + `_fr_board.json` | 4 |
| Lane B candidates + tracker | `_fr_laneB_candidates.py` / `_fr_laneB_gen.py` / `_fr_laneB_inject.py` / `_fr_laneB_tracker.json` | 4 |
| Shared-surface edit (the ONLY one) | `_post_board.py`: `resource_milestone` in `LANE_PRIORITY` + one `canon_lane()` regex | 4 |
| Publish payload + card | `frontend/public/speculair_future_resources.json` + bespoke card | 5 |

All driver modes are `python backend/weekly_opus_refresh.py fr-*` — they ride the existing
`Bash(python backend/weekly_opus_refresh.py *)` allowlist wildcard. Zero permission changes.

---

## 1. Universe builder — `fr-universe` (Stage A/B, monthly)

Clone of `disruptor_universe()` (the proven pattern) with two-lane gates. Anti-shrink guards copied
verbatim: re-screen FMP from scratch every build; never read a prior `universe.json`; STOP loudly if
the raw screen returns < 100 rows; funnel counts printed per chain × lane; the only carry-over
(Phase 3+) is the held-name union.

### 1.1 Stage A — FMP company-screener per chain × industry × exchange

Same param vocabulary as `disruptor_universe()`. One delta: the screen runs at the **Lane B floors**
(the lower ones — mcap ≥ $150M, price ≥ $1) and lane assignment happens after gating, so one screen
serves both lanes. `AMEX` is in the taxonomy's `exchanges` — dropping it silently loses the uranium
cohort (UEC/UUUU/DNN-class list on NYSE American).

Industry strings: `Uranium`, `Other Industrial Metals & Mining`, `Electrical Equipment & Parts`,
`Utilities - Independent Power Producers`, `Specialty Industrial Machinery`, `Engineering &
Construction` are proven in-repo against this key (themes_map.py / disruptor_themes.json), and the
robotics/quantum strings (`Scientific & Technical Instruments`, `Software - Application`,
`Medical - Instruments & Supplies`, `Computer Hardware`, `Semiconductors`, `Software - Infrastructure`)
are proven by the Disruptor Lens's live runs. `Copper`, `Aluminum`, `Other Precious Metals & Mining`,
`Specialty Chemicals` are **(verify)** — confirm against `/stable/available-industries` on the first
live run; the builder prints per-industry row counts so a misspelled string shows up as a loud zero,
never a silent gap.

The two machine chains screen deliberately broad industries (quantum broadest of all) and rely on the
chain map's physical-anchor rule + keyword hints to cut them down — a high Stage-C drop rate on those
chains is designed-in, and every drop prints.

### 1.2 Stage B — two-lane financial gates (no LLM, cached by symbol+month)

One fetch pass (cash-flow quarterly ×5, income annual ×4 + quarterly ×8, balance-sheet quarterly ×1 —
the extra balance-sheet call is the only addition vs the disruptor gates), then both lanes' gates are
computed from the same cache entry:

**Lane A (producers/royalties) — replaces the disruptor rules, keeps the structure:**

| Gate | Rule | Rationale |
|---|---|---|
| Cash generation | TTM FCF > 0 **OR** TTM OCF > 0 (OCF-only ⇒ tag `growth_capex_fcf_negative`; Director caps `size_units ≤ 0.75` and must verify the sustaining-vs-growth capex split in the debate) | producers mid-build are OCF-positive/FCF-negative; that is not distress |
| Profitability | TTM EBITDA > 0 | replaces the disruptor growth gate — producers are not growth stories |
| Funded solvency | `_funded_leverage()` + `_funded_solvency()` reused **verbatim**; bucket ≠ `weak` | capital-intensity makes this the gate that matters |
| Floors | mcap ≥ $500M, ADV ≥ $5M/day, price ≥ $2 | taxonomy `floors.lane_a` |
| Royalty bypass | `business_model = royalty_streamer` (from the Phase-2 chain map; Stage B tags a provisional pass) auto-passes cash gates | royalty cos are structurally FCF-light-but-clean and the industry filter can't find them anyway |

**Lane B (developers) — no profitability gate; survivability instead:**

| Gate | Rule |
|---|---|
| Floors | mcap ≥ $150M, ADV ≥ $2M/day, price ≥ $1 (taxonomy `floors.lane_b`) |
| Runway | `runway_months = cash_and_st_investments / monthly_burn`, `monthly_burn = max(-(TTM OCF + TTM capex), ε)/12`. Stamped here; the **deterministic entry gate** `runway_months ≥ months_to_milestone × 1.5` is asserted at Lane B candidate extraction (§6.4), Basket-13-validator style |
| Staleness flag | `balance_sheet_stale = true` if the latest balance sheet > 2 quarters old — miners raise equity between filings; the debate must web-verify recent raises before trusting the runway number |

A name that passes Lane A gates is `lane: "a"`; a name that fails Lane A but passes Lane B floors is
`lane: "b"` (subject to the milestone requirement resolving downstream). A name passing neither is out.
The pre-Stage-C output is `future_resources/_candidates.json` with per-chain × per-lane funnel counts.

### 1.3 Output + guards

`future_resources/universe.json` (Phase 2, after the chain map): `built_at`, `taxonomy_version`,
`funnel` (screened → liquid → gated_a / gated_b → mapped → debated), `by_chain` × lane counts,
`members` with `gates` blocks. Guards: STOP if raw < 100 rows, if `Uranium` maps to 0 (the AMEX
canary), or — Phase 2 — if any chain with historically ≥3 members maps to 0.

---

## 2. Chain map — Stage C Sonnet pass (`fr-map-merge`, monthly, Phase 2)

Clone of the disruptor theme-map workflow (`_dt_map.js` emission + `disruptor_map_merge()`), chunked
≤20/agent, with two **new required fields** per symbol:

- `business_model`: `producer | royalty_streamer | developer | equipment_services` — drives the royalty
  gate bypass and the lane assignment sanity check (a `developer` in lane A is a mapping error, printed).
- `commodity_revenue_share`: 0–1, the fraction of revenue exposed to the chain's commodity (1.0 for
  pure producers; TECK-class diversifieds get the Sonnet estimate). An LLM-estimated **input to a
  deterministic formula** — the `load_bearing_score` precedent.

Everything else mirrors the disruptor pass: `chains` (max 2 — UUUU legitimately carries uranium + rare
earth), `value_chain_position`, `true_competitors`, `chain_fit_confidence` with low-confidence drops
**printed, never silent** (the Specialty Chemicals filter will catch actual chemical companies; the
Gold industry will catch non-chain royalty cos; the quantum/robotics filters will catch generic
hardware and software names — all must drop loudly).

**The physical-anchor rule is enforced HERE, per name**: the chain-map prompt requires each agent to
state, in one line, the physical thing the company makes/moves/powers/instruments for its chain. A
name with no answer maps `chain_fit_confidence=low` regardless of industry or keywords — this is the
anti-Visa gate (§10), and it binds hardest on the quantum and robotics chains where the industry
filters are broadest.

---

## 3. Margin-torque metrics — `backend/_opus_debate/_resource_metrics.py` (Phase 2)

No AISC endpoint exists on FMP; these are honest proxies, computed deterministically from Stage-B
fetches, stamped into the grade input. Precedent for the shared-module extraction: `_moat.py`.

| Metric | Definition | Reading |
|---|---|---|
| `ebitda_margin_ttm` + `ebitda_margin_band` | TTM EBITDA / revenue; percentile **within the chain cohort** — cohorts < 8 names (uranium) fall back to fixed bands (>45% / 25–45% / <25%) because percentiles are unstable on n=6 | highest margin at the same commodity price ≈ lowest cost quartile — the cost-curve-position proxy |
| `fcf_torque_10pct` | `(0.10 × TTM revenue × commodity_revenue_share) / max(TTM EBITDA, ε)` | % EBITDA uplift from a +10% commodity move — incremental price flows through at ~full incremental margin. **Symmetric**: the Director must read it as downside torque too |
| `commodity_beta_2y` | regression of 2y weekly log-returns vs the chain's `commodity.fmp_symbol` (or `proxy_etf` where the commodity is off-FMP) — reuses `get_chart(days=760)` + the ISO-week resample from `_value_post.py` | empirical cross-check on the torque proxy; a "producer" with beta ≈ 0 is hedged or mislabeled |
| `ndebt_ebitda` | already fetched by `_funded_leverage` | torque × leverage is the blow-up quadrant — high-torque + high-leverage names get a mandatory size cap |

**Non-commodity chains (robotics_automation, quantum) never get torque metrics** — there is no spot
price to be leveraged to, and pretending an ETF is one would be a fabricated number. Their Lane A
deterministic set is instead: `gm_trajectory` (direction + 3-yr numbers — the pricing-power lie
detector, reused from the disruptor rubric where it did real work), `rev_yoy`, `fcf_margin`, and
`ndebt_ebitda`. The taxonomy encodes this: `commodity.fmp_symbol = null` on those chains switches
`_resource_metrics.py` to the non-commodity set; `commodity_beta_2y` is still computed vs the
`proxy_etf` (BOTZ/QTUM) purely as a factor-exposure read for the Director's concentration stress,
clearly labeled a proxy.

**These are Director scoring inputs, never a ranking that picks members** (deterministic-guards-never-
pick, Do-NOT #2 discipline).

---

## 4. Commodity regime layer (Phase 2)

`FUTURE_RESOURCES_REGIME.md` at repo root — structural clone of `CATALYST_WATCH_REGIME.md`
(§0 why / §1 decision mapping / §2 reproducible protocol / §3 action mapping / §4 append-only dated
instances / §5 tripwires / change log). **Protocol**: 6 parallel research agents, one per chain. The
four commodity/power agents produce, with citations: spot vs incentive price (incentive = cited
feasibility/analyst consensus, never invented), inventories, term-contracting state, futures-curve
shape, COT positioning, policy datelines. The two machine-chain agents read a different dial set:
**robotics** — industrial capex cycle (PMI/machine-tool orders), humanoid program datelines, robot
order/backlog trends; **quantum** — the government funding cycle (NQI reauthorization, DARPA/DOE/
sovereign programs), the error-correction milestone track, enterprise contract flow. Verdict per
chain: **TAILWIND / NEUTRAL / HEADWIND** + a tripwire table (including the lithium re-entry tripwire:
sustained spot > marginal-producer incentive price = revisit the exclusion).

**Data reality (audited 2026-07-02):** copper (`HGUSD`) and natural gas (`NGUSD`) price history are
FMP commodities; COT exists on FMP but is plan-tier-gated (verify on first live run; on failure COT
stays agent-narrative-only). **Uranium spot and NdPr are NOT FMP commodities** — agents web-source
them with citations (UxC/Numerco/SMM as reported in press) or proxy via SRUUF/U.UN trust NAV. This is
exactly how the catalyst regime doc already works: agent-verified, cited, dated.

Machine-readable sidecar `future_resources/regime_state.json`:
`{chain_id: {state, spot, vs_incentive_pct, one_liner, tripwires_breached, as_of}}`. Consumption in
both directions, mirroring the existing pattern: the Lane A BRIEF tells every debate to read the doc's
chain section; the grade-input builder stamps `chain_regime` so the Director prompt can enforce
**"HEADWIND chain ⇒ size_units ≤ 0.5 or a written justification"** deterministically-checkable.
Cadence: bi-weekly, a scheduled task cloned from the catalyst regime refresh, ≥13-day self-gating floor.

---

## 5. Lane A — debate, Director, post (Phase 3)

Reuses the debate chain verbatim (Interrogator → Architect/SoP → web verification → CRO), disruptor
recipe: isolated subtree, §3.1-style re-debate triggers, BATCH=8, "Reply exactly: DONE".

**BRIEF replacement** (the one substantive prompt change): judge **COST-CURVE POSITION** (the §3
metrics are in the bundle; web-verify against company-reported AISC/cost guidance where published —
the metrics are proxies and the debate should say when they disagree), **CONTRACTING & RESERVE LIFE**
(contract book vs spot exposure, reserve/resource life, offtake counterparties), **CAPITAL DISCIPLINE**
(the sector's besetting sin — capex history through the last cycle, buyback/dividend behavior at the
top), and **THE REGIME** (read `FUTURE_RESOURCES_REGIME.md` §<chain>). A live catalyst is neither a
plus nor a requirement (Lane B owns catalysts). Torque is symmetric — the bear case must price the
downside torque, not just assert "commodity risk".

**`FR_DIRECTOR_PROMPT` rubric** (~25 pts each): (1) cost-curve position & torque quality,
(2) contracting cycle & reserve life, (3) capital discipline & balance sheet, (4) growth-adjusted
valuation GUARD (CRO `sop_mos_pct` as veto/cap, never the driver). Hard constraints: 8 picks;
**chain caps ≤3 names AND ≤30% weight per chain** (a 2-chain name counts toward both);
`growth_capex_fcf_negative` ⇒ size ≤ 0.75; HEADWIND chain ⇒ size ≤ 0.5 or written justification;
torque × leverage quadrant ⇒ mandatory combined cap. **Commodity-factor stress replaces the AI-capex
stress**: the four commodity/power chains share one "global growth + China demand" axis — decompose
the final 8 on it EVERY run — plus chain-specific axes (uranium: one utility contracting cycle;
power-for-AI: one hyperscaler's PPA appetite; robotics: the industrial capex cycle; quantum +
robotics together: the long-duration-growth-multiple axis — rate-sensitive multiples compressing in
sync, the axis the machine chains import into an otherwise commodity book).

**Post-layer**: `_fr_post.py`, parameterized clone of `_disruptor_post.py` — beta benchmark
`["XME", "URA"]` instead of `["SMH", "QQQ"]`; `enforce_theme_caps` → `enforce_chain_caps`; everything
else (weights, stress block, correlation, exits, entry plans) copied.

---

## 6. Lane B — the developer/catalyst lane (Phase 4)

### 6.1 Own mini-sweep, not a widened main sweep

The main board's universe is frozen at ~2,961 names with a $300M floor; much developer alpha sits at
$150–300M. Widening the main sweep to harvest one sector's juniors multiplies cost across all sectors.
Instead **`backend/_fr_sweep.py`**: a parameterized clone of `_sweep_pipe.py`'s gen/inject mechanics
over `_fr_universe.json` (= Lane B Stage-A output, ~250–450 names ≈ 2–3 chunks vs the main board's
~20). `_fr_board.json` is **never merged into `_sweep_board.json`** (never-blend, applied to boards).

### 6.2 Mining event taxonomy (injected into the Scan tier prompt)

| Event | G1 named counterparty | G2 concrete commitment | G3 unpriced figure |
|---|---|---|---|
| Permit / Record of Decision | the agency, docketed | filed application, statutory clock | project NPV vs EV |
| Final Investment Decision | the board / JV partner | board-approved, financing named | post-FID re-rate vs peers |
| Feasibility study (PFS/DFS) | the company, dated release | committed publication window | NPV/IRR vs EV |
| First production / commissioning | the company + offtaker | construction % complete, guided date | production-multiple re-rate |
| Signed offtake (≠ MoU) | the named offtaker | signed, volumes + duration | contracted revenue vs mcap |
| Government award / price floor | DoD/DOE/EXIM, program named | signed award, appropriated | award size + floor economics vs EV |
| Quantum/robotics contract or award | the named agency/enterprise customer | signed contract or appropriated award, dated deliverables | contract value + follow-on economics vs EV |
| Dated technical milestone (quantum EC demo, humanoid production start) | the company + a named partner/customer on the dateline | publicly committed, verifiable date | the re-rate the last comparable milestone produced vs what is priced |

The skeptic tier gets the sector-specific kill list: MoUs dressed as offtakes, "permitting progress"
without a docket date, PEA-stage economics presented as DFS, serial-diluter financing patterns — and
for the machine chains: LOIs dressed as contracts, "roadmap" milestones with no committed date, and
qubit-count press releases with no error-rate substance (the quantum promoter pattern is the mining
promoter pattern with better slides).

### 6.3 The idiosyncrasy rule

An event qualifies only if it **resolves on its own driver** (a docket, a board vote, a commissioning
date) — commodity-price levels are the regime layer's business, never a Lane B catalyst.
`resolution_driver = Commodity_price` names stay off this lane's candidates exactly as they gate out
of the main board today.

### 6.4 Candidates → debate → tracker

`_fr_laneB_candidates.py` (clone of `_basket13_candidates.py`): ACTIVE tier, edge H/M, milestone
≤ 9 months (`MILESTONE_WINDOW_MONTHS = 9` — mining clocks are slower than deal clocks), **runway gate
asserted here deterministically** (`runway_months ≥ months_to_milestone × 1.5`, using fresh Stage-B
runway data; `balance_sheet_stale` names require the debate's web-verified raise check). Two-phase
Fable debate (`_basket13_gen.py` pattern — the CRO judges ONLY the trade). Append-only tracker with
event-resolution semantics, non-selections stamped, caps hard in `validate()`: 6–10 names, ≤2 per
resolution driver, ≤40% per chain, half-size default, sub-$300M names equity-only at half
`RISK_TO_FLOOR_PCT` (thin options are a fact, not a preference). Quarterly dial re-fit from realized
resolutions — the B13 calibration loop, separate ledger.

### 6.5 The only shared-surface edit

`_post_board.py`: append `resource_milestone` to `LANE_PRIORITY` (priority 8, beside
`supply_timing`) + one `canon_lane()` regex
(`permit|record of decision|\bFID\b|feasibility stud|first production|offtake|43-101|DOE loan|title iii`)
inserted **before** the supply_timing pattern. Acceptance: re-running the enrichment on the existing
board is **byte-identical** (no current row matches the new regex ahead of its old lane).

---

## 7. Publish / tracking / frontend (Phase 5) + cadence (Phase 6)

- **No publishing before Phase 5.** The `per_methodology_baskets` thin-card path is REJECTED: the
  nightly screener job rewrites `speculair_baskets.json` and would wipe a locally-injected foreign key
  (fixing that means a production-scan edit — worse than a bespoke card).
- Lane A NAV: `E._update_apex_tracking(track_in, gcs_path="scans/speculair_future_resources_tracking.json",
  local_name="speculair_future_resources_tracking.json")` — the signature already supports nth books.
  Weekly-stepped NAV until the nightly `_mark_speculair_nav()` fourth tuple + redeploy (deliberately
  deferred; it is the only production-scan change in the whole build).
- Lane B publishes the tracker (a track record of resolved events, B13-style), never a NAV.
- One card, two clearly-labeled sections, one honest banner: *"Commodity-cyclical sleeve. Lane A NAV
  steps weekly until the nightly mark ships. Lane B is an event tracker, not a NAV. US-listed names
  only — much developer alpha lists on TSX/ASX and is out of scope. Never blended with any other book."*
- Cadence: universe monthly (staleness self-gate, 21d), Lane A grading weekly (**STEP 3D** in the
  Sunday skill, after 3C, failure-isolated by order), Lane B sweep bi-weekly (rides the Catalyst Watch
  rhythm), regime refresh bi-weekly (13-day floor), Lane B dials quarterly.

---

## 8. Do-NOTs

1. **Never blend the lanes** — Lane A NAV and Lane B tracker are separate surfaces, separate state
   files; no combined number exists anywhere.
2. **Deterministic code never picks members** — gates decide eligibility, pre-ranks decide who gets
   debated, caps bound sizing; only the Director selects Lane A picks, only the two-phase debate
   selects Lane B entries.
3. **Never source a build from a prior universe/board file** — every monthly build re-screens FMP from
   scratch; the only carry-over is the held-name union. Thin screens STOP loudly.
4. **Commodity price is regime, not catalyst** — a name whose "event" is really a commodity-price view
   never enters Lane B (the §6.3 rule). Score ≠ edge applies to every mining event.
5. **Never mutate the existing books' surfaces** — `_sweep_pipe.py`, `_basket13_*.py`,
   `_disruptor_post.py`, the value/regime prompts are cloned, not generalized in place. The one
   sanctioned shared edit is §6.5, gated on byte-identical acceptance.
6. **The runway gate is code, not prompt** — an under-funded developer must be rejected by
   `validate()`, whatever the debate says.
7. **Torque is symmetric** — any memo citing upside torque without the downside number is
   non-conforming; reject and re-run.
8. **Never fabricate a spot price** — uranium/NdPr numbers carry a citation or don't appear; the
   proxy (trust NAV / ETF) is labeled as a proxy.
9. **Chain taxonomy lives in `future_resources_chains.json` only** — no chain lists, industry strings,
   or anchors hardcoded in Python/JS; the version stamps through to every payload.
10. **Never publish degraded** — <6 Lane A picks, a cap breach after post, or a failed GCS push after
    one retry → report and stop; the other books are unaffected by design.
11. **No member without a physical anchor** — every pick's chain-map entry must name the physical
    thing it makes/moves/powers/instruments. A basket diff showing a payments network, a lender, or a
    pure-software compounder is non-conforming regardless of score — reject and re-run the map (the
    anti-Visa rule, §10).

---

## 9. Phased rollout — acceptance criteria

**Phase 0+1 — Spec + taxonomy + Stage A/B builder (THIS DELIVERY).**
*Accept:* spec reviewed by Bruno; taxonomy validates with 4 chains and per-lane floors; `fr-universe`
runs end-to-end with a live key: per-industry and per-chain × lane funnel counts print; Lane A 25–60
names incl. CCJ/FCX/MP/GEV-class; Lane B 20–80 names with runway fields; `Uranium→0` guard trips when
AMEX is removed (synthetic test); re-run inside the month hits the gates cache; zero writes outside
`future_resources/`; `py_compile` clean. *(Verified this session: taxonomy JSON validity, py_compile,
dispatch wiring, and offline guard behavior — the live-key run is Bruno's first-run checklist, §11.)*

**Phase 2 — chain map + torque + regime v1.** *Accept:* every kept member has a `chain_map/<SYM>.json`
with `business_model` + `commodity_revenue_share`; misfiled names (chemical cos, non-chain royalties)
dropped WITH printed symbols; torque fields present for all Lane A; regime doc has 4 cited chain
verdicts + the lithium tripwire; `regime_state.json` parses.

**Phase 3 — Lane A debates + Director + post.** *Accept:* disruptor Phase-2/3 criteria transposed
(results ≥90% of debated, exactly 8 picks, numeric size_units/thesis_break_px/bear_fv_px, no pick
failing a hard gate, chain caps hold after post, `--offline` re-run byte-identical, cross-book
isolation diff clean).

**Phase 4 — Lane B sweep + tracker.** *Accept:* existing enriched board byte-identical after the
`_post_board.py` edit; skeptic kill rate spot-checked 30–50%; synthetic under-runway entry rejected by
`validate()`; non-selections stamped; sub-$300M entries carry the half-size equity expression.

**Phase 5/6 — publish + cadence.** *Accept:* payload carries every key + honest banner + taxonomy
version; tracking inception prints; STEP 3D failure isolation proven (forced failure stops only this
book); regime scheduled task self-gates at <13 days.

## 10. Disruptor Lens retirement (runbook)

**Why retired**: the Disruptor Lens picked Visa through its `fintech_rails` theme — a legitimate
output of its own rules, and exactly the failure that matters: an industry-filtered theme book with
profitability gates but **no physical anchor** converges on the generic S&P quality-compounder
factor, which the value books already cover. Rather than patch themes one by one, the book is
retired and its durable ground moves here: `robotics_automation` migrates as a chain (industry
strings and the GM-trajectory lie detector come with it), `energy_transition`'s ground is inherited
by `power_for_ai`, and `quantum` — which the disruptor gates could never hold, being pre-FCF — gets
the Lane B treatment it actually needed. The physical-anchor rule (header, §2, Do-NOT #11) is the
structural fix, not a theme tweak.

**What retirement means (honest-rails compliant — nothing is deleted, nothing back-filled):**

1. **Stop the rotation**: remove STEP 3C from the Sunday skill
   (`~/.claude/scheduled-tasks/speculair-opus-weekly/SKILL.md`, Bruno's machine). The disruptor
   subtree, prompts, and modes stay in the repo — retired code that ran a live track record is
   history, not dead weight.
2. **Freeze the NAV where it stands**: remove the disruptor tuple from
   `screener_v6.py::_mark_speculair_nav()` at the next planned `screener-sp500` redeploy (verify
   image digest before firing — the standing deploy lesson). Until that redeploy, nightly marks
   continue harmlessly; the freeze date on the card is the STEP 3C removal date.
3. **The card tells the truth**: the purple card becomes a retired card — frozen NAV chart, final
   holdings, and a banner: *"Retired <date>. Live-forward record <start> → <freeze>, wins and losses
   included. Robotics and quantum coverage continues in the Future Resources basket; this chart will
   never move again."* Tracking JSONs stay in GCS untouched. (Alternative — removing the card —
   violates the spirit of the honest rails: a retired book's record stays visible.)
4. **No holdings migration**: Future Resources builds its universe from scratch (anti-shrink rule).
   A disruptor holding that belongs here will re-earn its seat through the screen, the chain map, and
   the debate — the held-name union applies only to Future Resources' own holders, never to another
   book's.
5. **Non-migrating themes**: `ai_infrastructure`, `genomics_bio_tools`, `defense_tech`,
   `fintech_rails`, `space` retire with the book. AI infrastructure's power leg lives on in
   `power_for_ai`; defense/genomics names remain reachable by the value books' 12-method screens;
   fintech_rails is deliberately dead (the Visa lesson). If a retired theme deserves resurrection, it
   re-enters as a Future Resources chain **only if it can pass the physical-anchor rule**.
6. **Ordering**: retire only after Future Resources Phase 3 publishes its first Lane A basket — the
   site never has a gap where neither book exists. Until then the disruptor keeps rotating normally.

## 11. First-live-run checklist (Bruno, one-time — needs the FMP key)

1. `/stable/available-industries` → confirm `Copper`, `Aluminum`, `Other Precious Metals & Mining`,
   `Specialty Chemicals` exact strings; fix taxonomy if they differ (config edit only).
2. `python backend/weekly_opus_refresh.py fr-universe` → funnel prints; spot-check CCJ/UEC/UUUU (AMEX
   canary), FCX/SCCO, MP, GEV/CEG present; ISRG/TER-class in the robotics screen; IONQ/RGTI-class in
   the quantum screen (expect them lane_b); TSLA/JPM/V-class absent.
3. COT endpoint on this key's tier (regime layer degrade decision).
4. Re-run fr-universe same day → `cached: N` counter shows the cache hit.

---

## Appendix — decisions log

- 2026-07-02: basket conceived (user brief: "future energy and mining needs — future of the world");
  hybrid two-lane structure, developer inclusion (defined-risk), 4-chain scope, and spec-first
  delivery chosen as defaults — the interactive question dialog could not reach the user this session;
  all four are explicitly overridable at review.
- 2026-07-02: lithium/battery excluded at launch (oversupply); re-entry is a named regime tripwire.
- 2026-07-02: `per_methodology_baskets` publish path rejected (nightly-overwrite hazard).
- 2026-07-02: FMP data audit run against in-repo evidence (no key in the remote sandbox): 7 of 11
  industry strings proven, 4 marked (verify); uranium/NdPr confirmed off-FMP → regime doc web-sources.
- 2026-07-02 (v1.1, user decision): Disruptor Lens RETIRED (the Visa pick — no-physical-anchor
  drift); robotics migrates in as a chain, quantum added as a chain (Lane B treatment for pure-plays);
  Future Resources is the tracked container going forward. Physical-anchor rule made a hard Do-NOT.
  Retirement runbook in §10; retirement executes only after Phase 3 first publish (no coverage gap).
