# ROUTINE — "Speculair Mining + FDT weekly" (canonical copy)

> **This file is the source of truth for a NEW Claude Routines-UI entry** — separate from the
> existing "Speculair opus weekly" entry (`ROUTINE_speculair_weekly.md`), so the two books can run
> independently and neither risks the other's schedule. Suggested cadence: a day/time that doesn't
> collide with the Monday ~12:00 Apex/Value run — e.g. **Wednesdays ~09:00** — but the exact
> day/time is Bruno's call in the Routines UI; nothing below depends on it. When this routine
> changes, change it HERE first and paste the body between the markers into the Routines UI — the
> routine store is invisible to repo sessions (this is what caused the 2026-07-03 disruptor-
> retirement detour on the OTHER routine; don't repeat it on this one).
>
> Created 2026-07-27 (FUTURE_RESOURCES_SPLIT_SPEC.md): the Future Resources book split into two
> independent books — **MINING** (uranium fuel cycle, copper mining, precious metals, rare earths &
> strategic metals, diversified miners) with the `/commodities` page and its Dalio/Tavi Costa macro
> layer, and **FUTURE DISRUPTIVE TECH — "FDT"** (electrification & grid, nuclear/SMR, power-for-AI,
> robotics, quantum) on the Speculair page's amber card. The old Future Resources book is FROZEN,
> not deleted — it keeps publishing from the existing routine's STEP 3C (universe-build only) until
> Bruno runs the freeze (`_retire_fr.py --execute`, a separate later step, not part of this routine).
> Both books start FRESH live-forward NAVs; nothing here reads or inherits FR's history.

<!-- ROUTINE BODY BEGIN -->

Weekly **Mining + Future Disruptive Tech refresh**, designed to be fully hands-off. You are running
automatically in the Stock-Screener repo at `C:\Users\Bruno\Stock-Screener` with NO memory of prior
conversations — everything you need is below and in the repo. Goal: rebuild each book's universe
when its monthly cadence is due, refresh the commodity-macro dials, re-debate Lane A with Claude
Opus SUBAGENTS, kill-tier the finalists, pick each book's apex 8, and publish both to production GCS
so `/commodities` and the Speculair FDT card show fresh analysis. No Anthropic/OpenAI API key is
consumed by the debates (Claude Code subscription); only FMP + GCS + web calls use keys/network,
already configured.

**Operating rules (Bruno's standing instructions — same as the other Speculair routine):**
- This pipeline runs ENTIRELY on Claude Code (local). NEVER deploy any of it to Cloud Run / Cloud
  Run Jobs.
- The frontend is already deployed and reads GCS live — no frontend commit/deploy is needed;
  refreshing GCS data IS the whole job.
- This routine ONLY consumes production data and overlays the Opus debate layer. Do NOT edit
  `screener_v6.py`, the production scan, or any Cloud Run job.
- All commands below ride the existing `python backend/weekly_opus_refresh.py …` wildcard allowlist,
  same as every other Speculair mode — a headless run completes without permission prompts. If a
  step's GUARD trips, STOP and report rather than publishing degraded data.
- **NEVER run any `fr-*` mode from this routine** — the Future Resources chain is the OTHER
  routine's job (and only its universe-build step, until the freeze). Mining and FDT are separate
  books with separate taxonomies (`mining_chains.json` / `fdt_chains.json`), separate subtrees
  (`_opus_debate/mining/` / `_opus_debate/fdt/`), separate payloads
  (`speculair_mining.json` / `speculair_fdt.json`) — never mix inputs or outputs across books.
- **This lane is additive.** If MINING fails at any step, still attempt FDT (and vice versa) — the
  two books are independently breakable by design; one's failure never blocks the other, and neither
  blocks the existing Apex/Value/B13 routine.

STEP 0 — REPO SYNC (~30 s; same pattern as the other routine). Run `git rev-parse --abbrev-ref HEAD`
and `git status --porcelain`. ONLY if the branch is `main` AND the tree is clean, run
`git pull --ff-only origin main` and report the old→new commit in the final summary. In ANY other
state — wrong branch, dirty tree, diverged history, a permission prompt — print
`REPO SYNC SKIPPED: <reason> — running with the local copy` and CONTINUE; NEVER stash, reset,
force-pull, or switch branches unattended. A skipped sync is never a failure.

## MINING

STEP M1 — UNIVERSE + CHAIN MAP (monthly cadence, checked weekly; ~5-15 min when it runs, most weeks
skips). Read `backend/_opus_debate/mining/_candidates.json` — if it exists and its `built_at` is
less than 21 days old, print `MINING UNIVERSE FRESH, skipped` and go to STEP M2. Otherwise:
1. `python backend/weekly_opus_refresh.py mining-universe` — screens the five mining chains via FMP
   company-screener across NYSE/NASDAQ/AMEX (AMEX carries the uranium cohort — the canary: a
   `GUARD: uranium_fuel_cycle mapped 0 candidates — the AMEX canary (NYSE-American cohort
   missing?) — STOP` means AMEX access broke). Any `GUARD: ... STOP` line here — no FMP_API_KEY,
   `FMP screen returned <100 raw rows (key/quota failure?)`, a chain screened to 0 candidates on a
   PROVEN (non-`fmp_industries_verify`) industry string, or the AMEX canary above — means report and
   skip the rest of MINING this week; the Apex/Value/B13/FDT books are unaffected. Otherwise ends
   with `MINING UNIVERSE STAGE A+B OK: screened=<n> liquid=<n> lane_a=<n> lane_b=<n>`. A
   `WARN industry '<s>' -> 0 rows (unverified string ...)` on a string listed in that chain's
   `fmp_industries_verify` is expected and non-fatal — continue.
2. `mining-map`, then invoke the Workflow tool on the printed path (chain-map assignment Workflow;
   confirms with `MINING CHAIN-MAP EMIT OK: <n> candidates -> <n> map chunks`).
3. `mining-map-merge` — applies the physical-anchor drop rule, the royalty/streamer lane_b→lane_a
   promotion, the split-rule check (a `producer`/`royalty_streamer` name that mapped into a MINING
   chain from the FDT side, or vice versa, is dropped WITH a printed reason — this is working as
   designed, not an error), and the CROSS-BOOK DEDUP against FDT's universe if it exists (a
   straddler — e.g. a copper producer with a grid-equipment arm — is resolved by producer revenue
   share, ties to Mining; each decision prints and appends to `_basket_dedup_log.jsonl`). Ends with
   `MINING UNIVERSE OK: <n> mapped members (lane_a=<n> lane_b=<n>, ceded to fdt=<n>)`. A
   `NOTE: only <n> lane-A members mapped — mining-prep will STOP if <25 mappable; a thin lane-A is
   expected on the current cohorts, not a bug` is a heads-up, not a failure — continue to STEP M2;
   the actual hard stop (if the count is STILL thin after STEP M3's pre-rank) fires in STEP M3.

STEP M2 — COMMODITY MACRO (weekly, MANDATORY every run — this is what feeds both the `/commodities`
page's macro layer AND the Director's cited-only macro block, so it must run BEFORE the debates).
`python backend/weekly_opus_refresh.py mining-macro --gcs` — the `--gcs` flag is NOT optional: without
it the page's `scans/commodity_macro.json` object goes stale even though the local file is fresh.
Ends with `mining-macro: <n> dials, <n> chains scored (phase <PHASE> x quadrant <QUADRANT>) -> <path>`
followed by one ranked line per chain. A `DEGRADED: Macro dials degraded: ...` line is fail-open —
report it and continue; it never blocks Mining from proceeding. Quote the full scoreboard ranking in
the final report.

STEP M3 — PREP (deterministic, fetches FMP transcripts; ~3-8 min). `python backend/weekly_opus_refresh.py mining-prep`.
Staleness self-gates on the universe from STEP M1 (`MINING UNIVERSE STALE — run mining-universe, the
_mining_map.js workflow, then mining-map-merge first. STOP` if it's missing/too old — go back to
STEP M1). GUARD: `only <n> mappable Lane A members (<25) — DEGRADED universe, STOP (do not debate a
thin book, do not reuse a prior month)` — this is the hard stop the STEP M1 NOTE warned about;
report and skip the rest of MINING this week (the universe file is still fine for next week, no need
to rebuild it). Otherwise ends with `MINING PREP OK: <n> FMP + <n> online = <n> total ...` and
`MINING_WORKFLOW_SCRIPT=<path>`. Invoke the Workflow tool on that path (Interrogator → Architect →
CRO debate, batched 8; the debate BRIEF is cost-curve/reserve-life/contract-cover/capital-discipline
with symmetric commodity torque — a bear case that doesn't price the downside torque is
non-conforming).

STEP M4 — NUMERIC GATE (deterministic; ~30 s). `python backend/weekly_opus_refresh.py mining-numeric-gate --enforce`.
Stamps REJECT/EXCLUDE on records whose numeric claims don't verify. Report the outcome counts line
verbatim.

STEP M5 — GRADE INPUT + DIRECTOR PROMPT. `python backend/weekly_opus_refresh.py mining-input`. Joins
the debate results with the deterministic torque metrics and the STEP M2 macro block into
`mining_grade_input.json` + `mining_director_prompt.txt`. Ends with
`mining_grade_input.json: <n> names | forensic_gate=<n> growth_capex_fcf_negative=<n>
balance_sheet_stale=<n>` and `mining_director_prompt.txt written (<n> chars)`. Confirm the prompt
file contains exactly one `COMMODITY MACRO (CITED-ONLY)` section (grep it if unsure) — if STEP M2's
`mining-macro --gcs` didn't run this week, the block still gets written but says the macro layer is
degraded (fail-open, never a STOP).

STEP M6 — DIRECTOR. ONE Director subagent (Agent tool, `general-purpose`, `model: opus`), told
exactly: "Read backend/_opus_debate/mining/mining_director_prompt.txt IN FULL and execute it over
backend/_opus_debate/mining/mining_grade_input.json; write
backend/_opus_debate/mining/apex_basket_mining.json EXACTLY per its schema; reply DONE." Confirm the
written file has exactly 8 `apex_basket` entries.

STEP M7 — SKEPTIC KILL-TIER (independent adversarial pass — default-REFUTED unless primary sources
confirm; the resource sector's promoter-density attacks: cost-curve/AISC truth vs primary guidance,
reserve/contract truth vs the latest technical report, the cyclical-peak-cheapness trap, hidden
disqualifiers). `python backend/weekly_opus_refresh.py mining-skeptic`, then invoke the Workflow tool
on the printed `MINING_SKEPTIC_WORKFLOW=<path>`. Confirm the summary line shows
`lanes={'mining': <n>}` with `<n>` matching the apex+runner-up count (NOT `lanes={}` or a count of
0 — that would mean the apex file wasn't found; re-check STEP M6 landed first).

STEP M8 — POST + CSV + PUBLISH.
`python backend/weekly_opus_refresh.py mining-post` — deterministic safety layer: consumes the
STEP M7 skeptic verdicts (a REFUTED apex member is DEMOTED to runner-ups, MISSING/stale-REFUTED
half-sizes a seat), the HEADWIND/growth-capex/torque-leverage-quadrant gate caps, the joint
chain-concentration cap (≤3 names AND ≤30% weight per chain — NOTE: this book publishes
EQUAL-WEIGHTED, so a chain's published share is its seat count; a 3-seat chain landing at 37.5% with
a printed `NOTE chain residual (ADVISORY)` line is expected arithmetic, not an error — only a
`WARN chain residual` naming a >3-seat chain is a real problem), the Dalio duration-cap ADVISORY
layer (logs to `_cycle_ledger_mining.jsonl`, moves no published weight), and the cross-book seat
backstop (a name seated in BOTH this week's mining and fdt payloads is a hard STOP — report and do
not publish either book until resolved).
`python backend/weekly_opus_refresh.py mining-csv` — ends with
`wrote <n> mining-apex rows x <n> cols -> <path>`.
`python backend/weekly_opus_refresh.py mining-publish --gcs` — ends with
`mining_publish: <n> apex + <n> runners | tracking nav=<n> since=<n>% open=<n> closed=<n>
inception=<date>`, then per-file `GCS push <key> (attempt <n>): OK`, then
`GCS LIVE readback: <n> apex symbols [...]` (reads the payload BACK from GCS — this is what actually
confirms the publish is live, not just staged). GUARD:
`apex_basket_mining.json has NO mining_post_applied stamp` means mining-post didn't actually run
first — go back and run it; `only <n> Lane A picks (<6)` or a GCS push FAILED after retry → report
and stop; the other book is unaffected either way.

## FUTURE DISRUPTIVE TECH (FDT)

Same shape as Mining, mirrored — with two structural differences: **no `fdt-macro` mode exists**
(FDT gets no commodity-tilt block by design — it's not a commodity book), and the debate BRIEF reads
backlog/book-to-bill durability and gross-margin trajectory instead of commodity torque (these
chains are `torque_metrics: false` — there is no spot price for them to be levered to).

STEP F1 — UNIVERSE + CHAIN MAP (monthly, checked weekly). Read
`backend/_opus_debate/fdt/_candidates.json` — fresh (<21d) → `FDT UNIVERSE FRESH, skipped`, go to
STEP F2. Otherwise: `fdt-universe` (canary: `robotics_automation` — a
`GUARD: robotics_automation mapped 0 candidates — the deepest FDT cohort (industrial-machinery
screen missing?) — STOP` means that screen broke). Any `GUARD: ... STOP` line — no FMP_API_KEY,
`FMP screen returned <100 raw rows`, a chain screened to 0 on a PROVEN industry string, or the
canary above — means report and skip the rest of FDT this week; the other books are unaffected.
Otherwise: `fdt-map` + Workflow the printed path
(`FDT CHAIN-MAP EMIT OK: ...`); `fdt-map-merge` (split-rule check the other direction — an
`equipment_services`/`utility` name that mapped into a MINING chain is dropped there, not here; the
CROSS-BOOK DEDUP already ran when MINING's map-merge executed first — if FDT runs its map-merge
first in some week, its own dedup pass resolves straddlers the same way, ties still going to Mining).
Ends with `FDT UNIVERSE OK: <n> mapped members (lane_a=<n> lane_b=<n>, ceded to mining=<n>)`. A
`NOTE: only <n> lane-A members mapped — fdt-prep will STOP if <20 mappable; a thin lane-A is expected
on the current cohorts, not a bug` is a heads-up (FDT's floor is lower than Mining's — quantum/SMR
Lane A cohorts are structurally thin by design) — continue to STEP F2; the hard stop fires there if
it's still thin.

STEP F2 — PREP. `fdt-prep` (staleness self-gates on STEP F1's universe: `FDT UNIVERSE STALE — run
fdt-universe, the _fdt_map.js workflow, then fdt-map-merge first. STOP` → go back to STEP F1).
GUARD: `only <n> mappable Lane A members (<20) — DEGRADED universe, STOP (do not debate a thin book,
do not reuse a prior month)` → report and skip the rest of FDT this week. Otherwise ends with
`FDT PREP OK: <n> FMP + <n> online = <n> total ...` and `FDT_WORKFLOW_SCRIPT=<path>` — invoke the
Workflow tool on it.

STEP F3 — NUMERIC GATE. `fdt-numeric-gate --enforce`. Report the outcome counts line.

STEP F4 — GRADE INPUT + DIRECTOR PROMPT. `fdt-input`. Ends with
`fdt_grade_input.json: <n> names | ...` and `fdt_director_prompt.txt written (<n> chars)`. Confirm
the prompt file contains NO `COMMODITY MACRO` section (FDT is deliberately excluded — its presence
would mean the wrong template rendered).

STEP F5 — DIRECTOR. ONE Director subagent (Agent tool, `general-purpose`, `model: opus`): "Read
backend/_opus_debate/fdt/fdt_director_prompt.txt IN FULL and execute it over
backend/_opus_debate/fdt/fdt_grade_input.json; write backend/_opus_debate/fdt/apex_basket_fdt.json
EXACTLY per its schema; reply DONE." Confirm exactly 8 `apex_basket` entries.

STEP F6 — SKEPTIC KILL-TIER (the equipment/tech attack lane: backlog/order-book truth vs primary
filings, gross-margin-trajectory truth, thesis specificity — is the demand flowing to THIS name or
is a broad theme doing the work, hidden disqualifiers). `fdt-skeptic`, then invoke the Workflow tool
on the printed `FDT_SKEPTIC_WORKFLOW=<path>`. Confirm `lanes={'fdt': <n>}` matches the apex+runner
count.

STEP F7 — POST + CSV + PUBLISH. `fdt-post` (same mechanics as STEP M8 minus the Dalio duration layer
— FDT has none by design; same equal-weight chain-residual note vs warn distinction; same cross-book
seat backstop). `fdt-csv` — `wrote <n> fdt-apex rows x <n> cols -> <path>`. `fdt-publish --gcs` —
same guards as STEP M8 (`apex_basket_fdt.json has NO fdt_post_applied stamp`, `only <n> Lane A picks
(<6)`, GCS push FAILED after retry) — ends with
`fdt_publish: <n> apex + <n> runners | tracking nav=<n> since=<n>% ...`, then GCS push confirmations,
then `GCS LIVE readback: <n> apex symbols [...]`.

## STEP FINAL — VERIFY + REPORT

Report a concise summary: for EACH book, the apex 8 with `fr_score`s (yes, that field name is
deliberately unchanged in both books' schemas — it's what the frontend cards already render), the
chain exposure breakdown, whether it changed vs last week (call out any ONLINE-fetched names that
made the basket), and the GCS LIVE readback symbol list (the only thing that actually confirms
what's live, not just staged). ALSO report: MINING's macro scoreboard ranking (from STEP M2) and
which chain is currently favored by the Dalio tilt; any `NOTE chain residual (ADVISORY)` lines
(expected, not a problem) vs any `WARN chain residual`/count-breach lines (a real Director slate
issue — flag for next week); any cross-book dedup decisions from either map-merge; and any GUARD/WARN
line from any step, verbatim. If STEP 0 pulled, state the old→new commit. Keep every figure
grounded — never fabricate a number that wasn't actually printed.

<!-- ROUTINE BODY END -->

## Notes for the operator (not part of the paste)

- **Regime sidecars** (`backend/_opus_debate/mining/regime_state.json`,
  `backend/_opus_debate/fdt/regime_state.json`) are NOT built by this routine — they're the same
  manually-authored 6-agent research protocol FR used (see `FUTURE_RESOURCES_REGIME.md`'s §2 for the
  pattern to clone per book). Absent, they fail open: the setup leg of the macro scoreboard falls
  back to a price-percentile proxy, and the Director's `chain_regime` reads NEUTRAL. Refresh
  whenever convenient — there's no hard cadence requirement, just staler judgement without it.
- **The skeptic tier is real for both books** (unlike the original FR chain, which had none by
  design) — do not skip STEP M7/F7 thinking they're optional the way B13's catalyst-prep sometimes
  is. Skipping them means every pick ships un-vetted and half-sized on the next post-run (MISSING →
  the `_per_name_cap` teeth), which defeats the point of having built the tier.
- This routine and the existing "Speculair opus weekly" routine's STEP 3C (`fr-universe` only) can
  both run in the same week without conflict — different taxonomies, different subtrees, different
  GCS payloads. Nothing here touches `future_resources_chains.json` or any `fr-*` artifact.
