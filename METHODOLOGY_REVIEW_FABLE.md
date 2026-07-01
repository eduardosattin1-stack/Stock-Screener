# Speculair Methodology Review (Fable 5)

Date: 2026-07-01. Sources: `backend/_opus_debate/_method_review/{debate_engine,apex_book,value_book,basket13,basket14,ops}.md` + `redteam.md` (42 proposals → 3 killed, 3 killed-in-part, 18 keep-with-conditions). Audited against the proven evidence base; nothing below is re-derived.

## Executive summary

The machinery is honest; the returns are not there — and the platform's own evidence says why. The same
stack that produced 0 verdict-A / 0 conviction-5 across 407 priced-quality names produced 10 A / 6 c5 /
2 Director-80+ on the 17-name catalyst funnel: the bottleneck is FUNNEL COMPOSITION, not calibration.
Meanwhile the controls with proven teeth run on runbook memory, not enforcement: the live apex basket
shipped 06-30 with NO skeptic pass and NO post-processing; the value book's largest seat (EEFT, 20.4%)
is un-vetted and a stale-REFUTED name (HRMY) is seated; the 06-28 scheduled run died at birth with a
162-byte log and told nobody. B13 — the one book on the proven funnel — holds ~27 NAV-pts of seats its
own weekly diagnosis already rejected (GDOT 14%, AQST 4.5%, UNF 8%) while the highest-conviction name
the platform ever produced (BBIO 84) sits blocked behind those dead seats. The three moves that matter:
(1) make the weekly run happen and fail loud — launcher hardening + publish/coverage gates;
(2) make B13 consume the diagnosis it already pays for — REFUTED/FIRED blocks entries, flags dead seats;
(3) change what the debate SEES, not how it grades — S-curve slots, value drawdown intake, gate widening.

## Scorecard

| Subsystem | What it does well | Sharpest weakness | Grade |
|---|---|---|---|
| Debate engine | Deterministic post-processing owns the teeth; dated TTM/correction injection on the weekly path; fail-closed interrogator; chunked radar peer-comps with live anchors | Conviction is a recoded verdict letter (5 unreachable by construction on a priced tape); ad-hoc paths un-anchored → 87% corrections rate | B- |
| Skeptic kill-tier | Verdict-based demotion, mtime staleness guard, proven scalps (GDOT REFUTED after CRO said A/5; MYRG staleness kill) | Fails OPEN: partial runs silently produce an unvetted book; numeric `value_conviction_cap` still stamped/shipped, a reintroduction magnet for the proven cap bug | B |
| Apex / regime book | Special-sit lane floor-sizing binds exactly (15.00%); entry-price integrity chain; rotation ledger | Shipped LIVE 06-30 with no skeptic and no post; Director emits no `size_units` so every cap is arithmetically unbindable; 41.4% "expected return" is a display artifact | C |
| Value book | Best deterministic post-layer (measured 2y corr + feed-forward, market stress, P1 membership rule); funded-leverage solvency | Kill-tier fails open on the top seat; 70% secular load vs a prose-only 60% line; funnel-starved — re-weighting a priced pool can't mint value alpha | C+ |
| Basket 13 catalyst sleeve | The proven verdict-A funnel; cap validator in code; append-only stamp-honest tracker; counterfactual cohort | Ignores its own weekly full-stack diagnosis; manual resolve rot (VRDN fired 06-26, still OPEN); dead seats consume driver caps and lock out BBIO-class queue | B- |
| Basket 14 disruptor | Fail-loud funnel guards; hard profitability gates; the vector-sign gate is genuinely novel; clean NAV isolation | Rebuilt the conviction ceiling out of theme-flavored parts (0 A / 0 c5 / modal 3 on first 40 names); only book with NO skeptic; `ev_gp` valuation guard silently broken (dead `if False` branch, 9/40 null) | C |
| Weekly ops pipeline | Prep self-clean; freshness injection; forensic-ledger rechecks; real guard coverage in the SKILL | Launcher dies silently (06-28: 162-byte log, no basket, no alert); ~149 full Opus debates/week regardless of change → 2-3 resume cycles; un-pinned GCS read-modify-write under the NAV chain | C- |
| Track record / NAV | Live YTD TWR verified correct (all 12 baskets); B13 stamps honest (live entries, PENDING_LIMIT, no fiction fills) | Un-haircut base-case upside published as "expected return"; frozen 06-06 watchlist presented as live; FIP P&L prints twice across unstamped overlapping books | B- |

## Top 10 revisions

All items are red-team KEEP or KEEP-WITH-CONDITIONS, ranked by impact-per-effort.

**1. Launcher hardening (OPS-P1) — [SAFETY] — S**
Change: `backend/run_speculair_weekly.ps1:52` — drop `2>&1` on the `claude -p` pipe (PS 5.1 NativeCommandError under `$ErrorActionPreference=Stop` is the prime suspect for the 06-28 instant death); add a completion sentinel (apex mtime > launch start AND the publish LIVE-readback log line); bounded auto-resume ×2 on sentinel failure; unconditional END line + `FAILED_<date>.flag` in a `finally`.
Impact: converts both observed silent-death modes into self-healing or loudly-failed runs; every other property of the system only exists in weeks the run happens.
Conditions: resume loop bounded at 2, gated on the sentinel not the exit code; sentinel must distinguish an intentional publish-gate abort from a death (the gate prints its reason where the sentinel reads).

**2. Wire the weekly catalyst diagnosis into B13 (B13-P2 + P1 + P3) — [RETURN] — S/M**
Change: `_basket13_gen.py` joins each candidate with its latest `_catalyst_results/{SYM}.json` + `_catalyst_skeptic/{SYM}.json`; `_basket13_inject.validate()` hard-rejects a NEW seat with skeptic REFUTED or `catalyst_status ∈ {FIRED, ARB-through-terms}` (artifact ≤10d, else warn-only); `_basket13_mark.py` flags OPEN seats past `dated_milestone`+5td or carrying a fresh REFUTED/FIRED shard as `resolution_due` (alert-only); operator resolves promptly → driver caps free → watchlist graduates.
Impact: would have blocked ~27 NAV-pts of proven-broken seats (GDOT/AQST/UNF); unblocks the BBIO-class queue; the calibration loop finally accrues resolutions. Best return-per-line in all six audits — consumes artifacts already paid for weekly.
Conditions: catalyst Workflow ordering written into the SKILL; align the freshness window with the B13-P6 cache window (both 10d or both 14d); resolution stamping stays a human act on primary sources.

**3. Skeptic coverage + publish gate (VB-P1 + AX-P1, red-team-reconciled) — [SAFETY] — S**
Change: in `_post_common.consume_skeptic` (both books inherit): stamp `skeptic_verdict:"MISSING"` on apex members with no FRESH shard, half-size them via the existing `moat_per_name_cap` flags, and flag stale-REFUTED holds (`skeptic_stale_refuted:true`, half-size — the HRMY case). In `publish_to_frontend.py:100-104`: hard-abort (with `--force`) ONLY on missing `moat_post_applied`; skeptic coverage stays soft-gated (visible and priced, never blocking a headless run).
Impact: the kill-tier's coverage becomes either true or loudly false; closes the live failure (EEFT 20.4% un-vetted; HRMY seated over a stale REFUTED; the 06-30 apex shipping with no post at all).
Conditions: hard on the deterministic post, soft on the skeptic (X2 resolution); gate reason printed into the log item 1 reads; both posts consume identical stamps via `_post_common`.

**4. Same-day fuse pack (DE-P2, B14-P4, OPS-P4, AX-P5, VB-P6) — [SAFETY] — S**
Change: (a) `live_debate_engine.py:1415` → `-(x.get("conviction") or 0), -(x.get("interrogator_score") or 0)` (a `None` score currently crashes the whole tier-1 sort); (b) `weekly_opus_refresh.py:2150-2157` — delete the dead `if False` branch, take off-scan net debt from the funded-leverage cache + GM from the Stage-B fetch, emit `ev_gp_basis`; (c) prep archives a PARTIAL tree to `_archive_partial_<ts>` instead of clobbering the last good run (`:2665-2678`); (d) publish `director.runner_ups`, retire the frozen 06-06 capitulation watchlist (`page.tsx:3631`); (e) delete `MEMO_UNITS_20260609` (`_value_post.py:42-45`), fix `"universe": 161` (`weekly_opus_refresh.py:1149`), stamp as-of dates on `value_grade_input`.
Impact: one guaranteed crash, one silently-gutted valuation guard, one data-destruction path, one standing UI lie, three fuses — all removed for trivial effort.
Conditions: none material (cap partial archives at 2).

**5. Generation-pinned GCS reads on every read-modify-write (OPS-P3) — [SAFETY] — S**
Change: add `gcs_read_json_fresh()` (metadata → `?alt=media&generation=N`, or shell `gcloud storage cat` like the readback already does) to `alpha_compounder/gcs_io.py`; swap the RMW call sites: `publish_to_frontend.py:57` (merge base), `:95` (the two-writer tracking file), and the value/disruptor publish equivalents.
Impact: closes the exact bug class that already corrupted calibration_tracker — now sitting under the public NAV chain with two writers (nightly Cloud Run mark + weekly local publish). Silent cumulative NAV corruption is undetectable after the fact.
Conditions: unconditional keep; the generation-pin rule is a stated invariant for every NEW tracking writer (X6 — the B14 benchmark line adopts it day one).

**6. Honor the special-sit lane contract in `_regime_post` (AX-P4) — [SAFETY] — S**
Change: in `_regime_post.process` (`_regime_post.py:79-87`): skip `moat_per_name_cap` and exclude `lane=="equity_special_sit"` from `secular_theme_caps` membership (2-line predicate — the lane already has harsher floor-sizing at publish). The catalyst attack-rubric for `source=opus_catalyst` seats lands inside item 7.
Impact: urgent the moment item 3 forces the post to actually run — otherwise LBTYK (deliberately-melting, held for the event) gets wrongly half-sized by the moat cap the Director explicitly exempted it from, and the lane's three highest-conviction seats get skepticked on the wrong axis.
Conditions: rubric arm implemented inside the unified skeptic, not as a regime-only branch.

**7. Unified skeptic redesign (X1: VB-P2 + B14-P2 + DE-P4×VB-P5 + AX-P4 rubric + B13-P7) — [SAFETY] — M**
Change: ONE generator over the union of both books' finalists (merge `weekly_opus_refresh.py:1250` and `:1301` — they differ by ~2 clauses), per-lane attack rubric (value / regime / catalyst / disruptor — adding the disruptor tier the highest-vol book has never had), `kill_scope: value|catalyst|both`, and a categorical `correction_severity: minor|load_bearing` REPLACING the numeric `value_conviction_cap` everywhere (prompts `:1285/:1334`, `_post_common.py:56-57`, `publish_to_frontend.py:247`, UI). CWC + load_bearing → half-size flag. Also drop the numeric HARD-CAP from the catalyst Director (`_catalyst_weekly.mjs` step 3 — BBIO 84→78 was the cap binding, not information).
Impact: −30-40% skeptic agents from the 4/8 cross-book overlap funds the +13 disruptor tier (net ≤ today's count); permanently closes the proven skeptic-as-cap bug's reintroduction seam; the one book that grades its own homework gets an adversary.
Conditions: one work item, one session — seven audits touch this generator/consumer pair and shipped separately they collide; batch ≤6 for the web-heavy tier; disruptor skeptic must accept dated earnings-call guidance as primary source or it razes the book.

**8. Change-detection carry-forward for the main universe (OPS-P2) — [SPEED] — M**
Change: `prep()` diffs each candidate against `_archive_prev/`: full re-debate only on new transcript (hash change), |move| > 10%, elapsed PENDING_HARD milestone, new-to-universe or seat-relevant, or record age > 21d. Everything else carries forward re-stamped `carried_from=<date>`.
Impact: ~149 → ~45-70 Opus debates in a steady-state week — the difference between "2-3 resume cycles" and "fits one session"; earnings weeks spike back up by design.
Conditions (binding): deterministic freshness restamp (`_ttm_block` + live price) at carry time; `carried_from` age exposed in `value_grade_input` rows and the Director prompt; exits/stress recompute from LIVE price never the carried one (else the 87%-staleness class returns through the back door — X5); finalists/seat-relevant always re-debate; start at 21d ceiling, widen to 28 after 2 clean cycles.

**9. S-curve reserved slots in the disruptor pre-rank (B14-P1) — [RETURN] — S**
Change: `disruptor_map_merge()` Stage D (`weekly_opus_refresh.py:1757-1771`): split the ≤8/theme cut into 5 consensus slots + 3 reserved for `s_curve_stage ∈ {early_adoption, steep_ramp}` AND mcap < ~$25B, same rank key. Zero new agents, zero new data.
Impact: honest — it does not manufacture alpha; it creates the *possibility* of a 4/5-conviction seat in a book that got the exact 0-A / 0-c5 / modal-3 ceiling signature on its first 40 names. Expect 1-2 genuinely differentiated seats per quarter. Ship B14-P3 (same-inception SMH/QQQ benchmark NAV lines) alongside — it is the scoreboard that decides whether this book deserves to exist.
Conditions: hold the 5/3 split fixed ≥2 graded runs so the effect is attributable.

**10. Drawdown / forced-seller intake for the value book (VB-P3) — [RETURN] — M**
Change: `prep()` (`:2686-2706`) unions a dedicated slice (≤20 names/week, tagged `value_drawdown`, cap enforced in code): quality names (positive FCF, funded-solvency ≠ weak, non-EXCLUDE) in the bottom decile of their own 2y range after a −25%+ drawdown, plus existing spin-off/index-deletion/forced-seller flags. They debate through the normal pipeline as ordinary rows.
Impact: the only evidence-backed path to value alpha — the value book currently re-weights a priced pool where its entire risk machinery filters names that don't need filtering. Most weeks add 0-3 credible candidates; a sector de-rate transforms the book. It will not manufacture a drawdown the tape doesn't offer.
Conditions: sequence AFTER item 8 (agent budget); one composition change per book per cycle or attribution dies; rows tagged for attribution; stamp `rubric_version` on artifacts (X4).

## Quick wins (this week)

- [ ] Fix the launcher: drop `2>&1`, add sentinel + bounded auto-resume + fail-loud flag (`run_speculair_weekly.ps1:52`) — item 1
- [ ] `-None` sort crash: `live_debate_engine.py:1415` — item 4a
- [ ] `ev_gp` dead-branch fix + `ev_gp_basis` stamp (`weekly_opus_refresh.py:2150-2157`) — item 4b
- [ ] Prep partial-archive protection (`weekly_opus_refresh.py:2665-2678`) — item 4c
- [ ] Publish `runner_ups`; retire the frozen 06-06 watchlist (`page.tsx:3631`) — item 4d
- [ ] Delete `MEMO_UNITS_20260609`; fix `universe:161`; as-of stamps — item 4e
- [ ] Skeptic coverage stamps + half-size MISSING/stale-REFUTED (`_post_common.py`); post-only hard publish gate (`publish_to_frontend.py:100-104`) — item 3
- [ ] Generation-pinned reads at `publish_to_frontend.py:57/:95` + value/disruptor publish — item 5
- [ ] Lane predicate in `_regime_post.py:79-87` (BEFORE the next weekly run — the LBTYK mis-cap fires the first time the post actually runs) — item 6
- [ ] B13 resolution radar in the daily mark + resolve GDOT/AQST/UNF/VRDN promptly (prints honest losses — that is the system working) — item 2, S part
- [ ] S-curve reserved slots (`weekly_opus_refresh.py:1757-1771`) — item 9

## Structural bets (this quarter)

Sequencing — each unlocks the next:
1. **Items 1+3 first** (a run that happens and fails loud). Every downstream bet assumes the pipeline actually executes; two of the last three scheduled runs did not.
2. **Item 7 (unified skeptic) as ONE session.** Consolidate before any other skeptic-touching change lands — seven proposals collide in `weekly_opus_refresh.py:1250-1349` + `consume_skeptic` if shipped piecemeal. Its −30-40% agent saving is the budget that pays for the disruptor tier.
3. **Item 8 (carry-forward) next.** It frees 80-100 debates/week of session budget — the resource every composition change below spends. Land reductions before additions (X3); print agents-invoked-per-run in the log so budget is a measured number.
4. **Item 2's M part (entry-gate wiring) + item 10 (drawdown intake) last, one composition change per book per cycle**, each stamped with a `rubric_version` (X4) so the calibration loop can segment across the boundary. The gate-widening arm of DE-P1 (`conviction >= 3 OR value_conviction >= 4` at the Director eligibility line) rides here too — only after ≥1 full special-sit-lane cycle.

## Do NOT do

- **Rewrite the conviction rubric (DE-P1 rewrite arm)** — the decoupled catalyst-blind score already exists and ships (`value_conviction`, `weekly_opus_refresh.py:552`); rewriting destroys the only 407-debate longitudinal series exactly while the special-sit lane experiment reads out against it.
- **Near-miss skeptic band (DE-P8)** — premise false: both skeptic tiers already cover apex + runner_ups (`weekly_opus_refresh.py:1262-1266, :1311-1315`); it would spend ~10 web-heavy agents/week of the binding budget on the lowest-value review in the stack.
- **Grow the special-sit lane 3→5 / 15%→20% (AX-P3b)** — the lane has run ZERO complete cycles; the supporting cohort is 3 weeks, n≈12, no resolutions; FIP cross-book overlap is live and unstamped. Re-open after one quarter of lane data + overlap stamping + real resolutions.
- **Retrofit PENDING_LIMIT fills onto the disruptor NAV (B14-P5 retrofit arm)** — it mutates `_update_apex_tracking`, the shared VERIFIED-correct TWR machinery, mid-track-record; a fill-regime change breaks NAV comparability. Delete the ignored `entry_posture` field instead; revisit real fills as a stamped new epoch if the book survives its benchmark.
- **Reuse scale-out overlay shards as debate cache (B14-P6a)** — the overlay was a one-off (45 names, 06-22, no refresh cadence); every shard is permanently past the proposal's own 28-day bound. Dead code on arrival.
- **Optimize the nightly debate path's tokens (DE-P6 nightly arm)** — the path is env-gated OFF and its Director is being retired; decide its status ONCE (retired-in-place, loud header, port the ≤3/sector cap into `_regime_post`, keep the 2-token crash fix as insurance).
- **Any numeric skeptic cap consumption, ever** — the proven bug: numeric caps as ceilings crushed all scores to ~35; verdict/severity categories only.
- **Auto-stamping B13 resolutions** — exit price/type on a primary source is the honesty that makes the tracker credible; radar flags, human stamps.
- **Cheapening the Director/Skeptic model seats** — capability-bound kill/selection tiers on 1M context; the ceiling is funnel composition, not seat quality.

## What to leave alone

- **`consume_skeptic` verdict-based demotion + mtime staleness guard** (`_post_common.py:19-74`) — the exact fix for the proven cap bug, with a proven scalp (GDOT). Extend its coverage (item 3); never change its demotion logic.
- **Re-grading cached debates in the value book** — sound as designed: prep self-cleans weekly, `value_conviction` is elicited catalyst-blind inside the debate, and a second full 161-name debate would double a multi-hour run to re-score the same pool. (Carry-forward makes it carry-AWARE — item 8's conditions — not re-debated.)
- **The deterministic post-layer's P1 membership rule** — posts size and stamp but never change membership (sole exceptions: skeptic demotion, gate-sync EXCLUDE). This is what keeps the agentic layer auditable.
- **B13's cap validator + append-only tracker + human resolve** (`_basket13_inject.py:323-373`) — "the LLM proposes, the code asserts" is the single reason the sleeve's record is trustable; it earns its ~700 lines.
- **Funded-leverage solvency** (`weekly_opus_refresh.py:524-535`) — 12 lines that fixed a real Altman-Z artifact; correct basis, financials exempt.
- **The disruptor vector-sign gate + separate debate framing** (`DISRUPTOR_DIRECTOR_PROMPT :583-592`) — "abnormal cheapness is a warning, not a margin of safety" is a genuine inversion of the value rubric; folding it into another book would re-import "cheap = safe".
- **Single-agent-per-name weekly debate economics** — 1 agent instead of 3-4, inside the rate-limit ceiling; independence is recovered at the separately-spawned bear-only Skeptic, which is where it matters.
- **Forensic ledger short-rechecks** (`prep() :2790-2816`) — the template every cost-saving above copies.
- **Chunked Radar peer-comps + `PEER_OVERRIDES` live anchors** (`weekly_opus_refresh.py:304-447`) — the best prompt-engineering in the repo; it names the Edenred/Pluxee failure mode and hands the agent the corrected input.
- **The special-sit lane as wired** — floor-sized, ≤3 seats, ≤15% NAV, 1.5% rtf; it is the platform's one composition fix aimed at the proven bottleneck. Let it run a full quarter untouched.
- **NAV isolation / chained TWR tracking** — verified correct across all 12 baskets; every proposal that touches it (benchmark lines, marks) adds writers, never rewrites mechanics.
