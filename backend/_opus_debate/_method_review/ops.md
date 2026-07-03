# Ops Audit — Speculair Weekly Pipeline: Speed, Cost, Safety, Data Hygiene

Reviewer: Fable 5 (senior quant-methodology review, cross-cutting ops subsystem)
Date: 2026-07-01
Scope: `backend/weekly_opus_refresh.py` (3,091 lines), `backend/run_speculair_weekly.ps1`,
`backend/_opus_debate/publish_to_frontend.py`, `_value_post.py`, `_regime_post.py`, `_post_common.py`,
`backend/alpha_compounder/gcs_io.py`, the SKILL runbook at
`C:\Users\Bruno\.claude\scheduled-tasks\speculair-opus-weekly\SKILL.md`, live run artifacts
(`_run_logs/`, `results_regime/` mtimes).

---

## 1. WHAT WORKS (keep — and why it earns its complexity)

1. **Verdict-based skeptic demotion is correctly implemented — the skeptic-as-cap bug is NOT in the weekly path.**
   I checked this specifically (it was flagged as a suspected residual). `_post_common.consume_skeptic`
   (via `_value_post.py:100-157` and `_regime_post.py:77`) demotes ONLY on `verdict == "REFUTED"`;
   `value_conviction_cap` is stamped as display metadata (`_value_post.py:138-139`,
   `publish_to_frontend.py:247`) and is never fed into `build_weights`, `value_score`, or seat selection.
   Grep across `_post_common.py`, `_regime_post.py`, `_value_post.py`, `publish_to_frontend.py`, and the
   frontend confirms no numeric `min(conviction, cap)` consumption anywhere. Keep exactly as is.

2. **Prep self-clean + raw-screen sourcing** (`weekly_opus_refresh.py:2658-2706`). Archiving the prior
   run and re-reading `methodology_picks.json` fixed two real, observed failures (mixed-vintage Director
   inputs; the 2026-06-06 shrink loop). The `<40 names → fold in curated` fallback and the apex union
   (held names never dropped) are cheap and correct.

3. **Deterministic merge + per-symbol explode for the Radar** (`merge_radar()`, :402-431). Chunked Sonnet
   shards with a plain dict-update merge sidesteps the observed 161-name LLM-output truncation, and
   per-symbol `peer_groups/<sym>.json` files keep every debate agent under the 25k Read cap. The
   `PEER_OVERRIDES` backstop (:304-399) is idempotent (preserves `_radar_*_raw`) and injects a LIVE
   anchor multiple — this is exactly the freshness discipline the ad-hoc path lacks (see W6).

4. **Freshness injection on the weekly path.** `_ttm_cash_block` (`live_debate_engine.py:876-931`,
   duplicated at `weekly_opus_refresh.py:194-245`) date-stamps TTM FCF/EPS "as of <date> — USE THESE
   OVER THE FISCAL-YEAR-ANNUAL"; `_live_corrections` (:934+) overrides the two most-often-wrong scan
   fields. This is why the weekly books don't show the ad-hoc 87% corrections rate.

5. **GCS readback via `gcloud storage cat`** (`publish_to_frontend.py:534-545`). The publish
   self-verifies what is actually LIVE through the fresh client path, explicitly avoiding the
   public-URL stale-cache read. Correct, and the SKILL's STEP 4 consumes it.

6. **Best-effort isolation of the ledger/decision-history/backfill layers.** Every continuity feature
   (`write_director_ledger`, `append_decision_history`, entry-price backfill, wheel stamping) is wrapped
   so it can never break the debate/publish path. The right trade for a hands-off pipeline.

7. **The forensic ledger short-recheck** (`prep()` :2790-2816, `recheckPrompt` :2888-2892). Unexpired
   EXCLUDE names get a web-delta re-affirm instead of a full I→A→CRO debate. This is the pipeline's ONE
   existing change-detection gate — and it is the template for the biggest speed win below.

8. **Guard coverage in the SKILL is real, not decorative**: TOTAL<30 / methodologies<8 (STEP 1), apex<10
   with a one-retry-then-stop (STEP 2), publish abort on empty picks (`publish_to_frontend.py:102-104`),
   value<8 (STEP 3B), disruptor<6 + subtree-only self-clean (STEP 3C). The catalyst lane is correctly
   additive-only (never blocks the compounder book).

---

## 2. WEAKNESSES / RISKS

### W1 — PROVEN: the WTS launcher dies silently; the 06-28 run produced a 162-byte log and no basket.
`_run_logs/speculair_weekly_20260628_124706.log` contains ONLY the launcher START line (162 bytes,
UTF-16) — no claude output, **no "launcher END" line, no exit code**. The launcher
(`run_speculair_weekly.ps1:52`) pipes `claude -p ... 2>&1 | Tee-Object` under
`$ErrorActionPreference = "Stop"` (line 28) in Windows PowerShell 5.1. In PS 5.1, redirecting a native
executable's stderr with `2>&1` wraps each stderr line in a `NativeCommandError` ErrorRecord; under
`Stop`, the first stderr byte from `claude` **terminates the whole script** before the END line — which
is exactly the observed log shape. The real run then happened only because someone drove it manually:
`_weekly_debate.js` regenerated 06-29 12:58, debate shards finishing 06-30 12:47, apex written 06-30
13:16 (file mtimes) — a two-day, hand-resumed cycle for a job scheduled Sunday 01:00. Failure it causes:
**a scheduled week simply doesn't publish, and nothing tells anyone.** The frontend serves last week's
GCS data with a stale `generated_at` no one is checking.

### W2 — PROVEN (mechanism) / SUSPECTED (occurrence): GCS read-modify-write on the publish merge base, with two writers.
`publish_to_frontend.py:57` reads `scans/speculair_baskets.json` as the merge BASE and `:95` refreshes
local tracking from `scans/speculair_apex_tracking.json` — both via `gcs_io.gcs_read_json`
(`alpha_compounder/gcs_io.py:62-93`), a **plain URL read with no generation pin and no cache-buster**.
This is the exact read class that returned a prior generation and silently clobbered
`calibration_tracker`'s append (repo memory, confirmed root cause). And tracking has **two writers**:
the nightly Cloud Run `_mark_speculair_nav()` and the weekly local publish (`_update_apex_tracking` →
`gcloud cp` back). If the Sunday publish reads a pre-last-night generation of tracking, the NAV chain
re-marks from a stale point — a small, silent, cumulative NAV corruption, indistinguishable from market
noise afterward. The same helper feeds `prep()`'s universe read (:2686) and `value_input()`'s scan read.
Note the asymmetry: the pipeline already distrusts this path on READBACK (it uses `gcloud storage cat`,
:534-545) but still trusts it for the read-half of a read-modify-write, which is strictly more dangerous.

### W3 — PROVEN: no change-detection gate on the main universe — ~149 full Opus debates weekly, most re-deriving unchanged conclusions.
`results_regime/` holds 149 records this run. Every name gets a full Interrogator→Architect→CRO Opus
web-heavy debate every week (`_WORKFLOW_TEMPLATE` :2894-2905), even when nothing changed: no new
earnings (transcripts are quarterly — for ~12 of 13 weeks the transcript file is byte-identical),
catalyst status unchanged, price within noise. At BATCH=8 that is ~19 serial batches — the dominant
share of the multi-hour wall clock and the direct cause of the 2-3 resume cycles (session limits bind
on total agent count, not on any single batch). The pipeline already proves the cheaper pattern works
twice: the forensic-ledger recheck (:2885-2892) and the disruptor lens's §3.1 steady-state triggers
(~10-15 of ~40 re-debate). Cost framing: ~190-230 Opus agent invocations/week (149 debates + ~26-32
skeptics + 3 directors + lane/recheck), each reading ~20-25k tokens of transcript plus multi-round web
tools — order 30-60M tokens/week. On subscription this is wall-clock and session-limit budget, not
dollars, but it is precisely the budget that forces the resume cycles.

### W4 — PROVEN: a failed run followed by a re-prep destroys the last GOOD run's local outputs.
`prep()` (:2665-2678) unconditionally `rmtree`s `_archive_prev/` and moves the CURRENT
`results_regime/` + apex into it. Sequence: week N completes → week N+1 prep archives N (fine) → week
N+1 dies mid-debate (see W1, observed twice: 06-21, 06-28) → someone re-runs `prep` to restart →
prep **deletes week N's archive** and archives week N+1's partial shards over it. Week N's local debate
outputs are gone (GCS history keeps the published subset — `results_regime` context like dossiers and
non-published fields is lost). The comment at :2664 ("the workflow-resume retry path does NOT call
prep, so a mid-run re-invoke is safe") is true only if the operator resumes via Workflow rather than
restarting from STEP 1 — nothing enforces that, and a fresh headless session following the SKILL from
the top will call prep again.

### W5 — PROVEN: BATCH=8 sits above the proven-safe burst width, and the recovery path is manual prose.
The empirical ceiling is "batch ≤6 works" for >16-wide web-heavy bursts (proven ops evidence); the
debate loops pin `BATCH = 8` (:2899, :1276, :1325, :2561 — the disruptor comment even cites 429s).
The SKILL's own STEP 3C text documents the consequence: "if a back-half batch hits the server-side
rate limit, re-invoke the SAME Workflow with resumeFromRunId … converges in 1-3 passes." That is a
known-flaky width with a human-driven retry loop written into the runbook instead of an automatic one.
Each tripped batch costs a resume cycle in a pipeline already short on session budget.

### W6 — PROVEN: ad-hoc/online debate paths get no pre-injected dated metrics — the 87%-corrections defect is still open.
`_adhoc_debate.js:13` tells the agent to "fetch the LATEST fundamentals online" — no `_ttm_cash_block`,
no `_live_corrections`, no dated anchor injected into `inputs/<sym>.json`. The weekly path injects all
of these (What-Works #4). Empirical result on record: 87% CONFIRMED_WITH_CORRECTIONS and one staleness
kill (MYRG) on ad-hoc runs. The fix already exists in the repo and is unwired: `fmp_facts.py` ("dump
LIVE FMP facts for one ticker as a clean sheet") is a standalone CLI nobody's prep calls.

### W7 — PROVEN: NTFS reserved-name tickers are landmines on the local tree and one is committed.
Ticker `CON` produced `backend/_opus_debate/results_regime/CON.json` and
`frontend/public/speculair_debate_history/CON.json` (both present now), and
`frontend/public/speculair_debate_voiced/CON.json` is **tracked in git** (commit c5f1d6b9, shipped via
the plumbing recipe). Known blast radius: `git add <dir>` fails, `git checkout main` is impossible
without `core.protectNTFS=false` plumbing (the "761 files dropped" near-disaster is documented in
memory). Any new reserved ticker (PRN, AUX, NUL, COM1-9, LPT1-9) entering the raw screen re-detonates
this with zero warning — the debate agent's Write of `results_regime/PRN.json` may itself fail
silently mid-run, and the SKILL has no guard for it.

### W8 — SUSPECTED: shared-working-dir parallel-session races on `frontend/public/*.json`.
A second Claude session commits in the SAME repo directory (documented memory; HEAD moves under the
weekly run). The publish writes `frontend/public/speculair_baskets.json`, tracking, history, and
peer_groups locally before pushing. A parallel session doing `git add -A`/checkout mid-publish can
commit half-written JSON or move the tree under the headless run. No corruption observed yet (GCS is
the serving path, which limits blast radius), but the weekly run assumes single-writer on the working
tree and nothing asserts it (e.g., a lockfile or a branch check at launcher start).

### W9 — MINOR / PROVEN: Opus spent where Sonnet suffices.
Ledger re-checks run as `model: 'opus'` inside the debate batches (:2903-2904) though the task is "web
search for material changes, re-affirm in one paragraph." The radar-merge step burns an agent turn to
run one allowlisted python command (:2864-2866). Both are Sonnet-grade (the merge is arguably
zero-LLM). Savings are real but small (~5-12 agents/week) next to W3.

---

## 3. PROPOSALS (ranked)

### P1 [SAFETY] Harden the launcher: kill the 2>&1 trap, add an auto-resume loop and a completion sentinel.
**Change** (`backend/run_speculair_weekly.ps1`): (a) drop `2>&1` on the `claude -p` invocation (PS 5.1
NativeCommandError under `$ErrorActionPreference=Stop` is the prime suspect for the 06-28 162-byte
log; stderr is capturable via the log redirect instead) or wrap the invocation with
`$ErrorActionPreference="Continue"`; (b) after each attempt, test a COMPLETION SENTINEL — freshest
evidence is `apex_basket_opus_regime.json` mtime > launcher start AND the publish's `LIVE readback`
line in the log; (c) if absent, re-invoke `claude -p` up to 2 more times with a RESUME prompt ("the run
is partially complete; re-invoke the SAME workflows — cached agents return instantly — and continue
from the first unfinished STEP"), which is exactly what the human does today across 2-3 cycles; (d) on
final failure, emit a notification (ntfy/email/a `FAILED_<date>.flag` file the next interactive session
surfaces) and log the END line unconditionally in a `finally`.
**Impact**: converts the two observed silent-death modes (06-21 budget kill, 06-28 instant death) into
self-healing or at worst loudly-failed runs; removes the 2-day manual babysit. **Effort: S.**
**Risk**: an auto-resume loop re-invoking a genuinely broken run wastes session budget — bound it at 2
and gate on the sentinel, not on exit code alone.

### P2 [SPEED] Change-detection gate for the main weekly universe (the disruptor §3.1 pattern, generalized).
**Change** (`weekly_opus_refresh.py prep()`): before emitting `__SYMS__`, diff each candidate against
its prior `results_regime` record (in `_archive_prev/`) and its history: full re-debate ONLY if
(a) new transcript since last debate (the fetched `transcripts/<sym>.txt` hash changed / a new quarter
date appears), (b) |price move| > ~10% since the last debate's `live_price`, (c) `catalyst_status` was
PENDING_HARD with a dated milestone now elapsed, (d) the name is NEW to the universe or seat-relevant
(current apex/runner-up in any book), or (e) the record is older than 28 days (hard staleness ceiling).
Everything else gets a CARRY-FORWARD: copy the prior record into `results_regime/` re-stamped
(`carried_from=<date>`), optionally with a Sonnet one-shot delta check (the `recheckPrompt` skeleton
already exists). Directors and posts consume `results_regime/` unchanged — zero downstream edits.
**Impact**: honest estimate 50-70% fewer Opus debates in a steady-state week (149 → ~45-70; earnings
weeks spike back up by design). That is the difference between "needs 2-3 resume cycles" and "fits one
session" — it also shrinks W5's exposure mechanically. **Effort: M.**
**Risk**: a thesis can break without tripping (a)-(e) (peer de-rate, sector news). Mitigants: the 28-day
ceiling, seat-relevant names always re-debate, and both skeptic kill-tiers still run fresh every week
on the finalists — the money-bearing layer stays weekly.

### P3 [SAFETY] Generation-pinned (or gcloud-cat) reads for every GCS read-modify-write in the weekly path.
**Change**: add `gcs_read_json_fresh()` to `alpha_compounder/gcs_io.py` — GET the object metadata for
`generation`, then read `?alt=media&generation=N` (the proven fix from the calibration_tracker
incident); or, simpler and already-allowlisted, shell `gcloud storage cat` like the readback does.
Swap the three RMW-feeding call sites: `publish_to_frontend.py:57` (merge base), `:95` (tracking
refresh — the two-writer file), and the equivalent reads in `value-publish`/`disruptor-publish`.
`prep()`'s universe read can stay lazy (worst case it debates yesterday's screen).
**Impact**: closes the one remaining instance of the bug class that already corrupted the calibration
tracker, on the files that carry the public NAV track record — a silent-corruption class you cannot
detect after the fact. **Effort: S.** **Risk**: essentially none; +1-2s per publish.

### P4 [SAFETY] Make prep's self-clean refuse to destroy the last completed run.
**Change** (`weekly_opus_refresh.py:2665-2678`): archive-and-wipe ONLY when the current
`results_regime/` represents a COMPLETED run (its `apex_basket_opus_regime.json` exists alongside it);
if the tree looks partial (results present, apex missing), move the partial shards to a
`_archive_partial_<ts>/` instead and LEAVE `_archive_prev/` (the last good run) untouched. Print which
branch was taken so the headless agent reports it.
**Impact**: a crash-then-restart (both observed incidents) can no longer erase the last good week's
local debate context. **Effort: S.** **Risk**: slow disk-bloat from partial archives — cap at 2.

### P5 [SAFETY] Wire `fmp_facts.py` into every ad-hoc/online debate prep.
**Change**: give the ad-hoc path a tiny prep verb (or extend the existing bundle writers): for each
symbol, run the existing `fmp_facts.py` collector and inject its dated output into
`inputs/<sym>.json.metrics_str` exactly as prep injects `_ttm_cash_block` — then have
`_adhoc_debate.js` (and future scale-out/one-off workflow generators) state "these dated figures are
the anchor; web-verify deltas only." The code exists; it is one plumbing seam.
**Impact**: attacks the measured 87% corrections rate and the MYRG-class staleness kill at the source;
also makes ad-hoc verdicts comparable to weekly ones (same evidence basis). **Effort: S.**
**Risk**: none material; FMP quota is already retried with backoff in `fmp_facts.py`.

### P6 [SPEED] Match the batch width to the proven ceiling — with the retry inside the workflow, not the runbook.
**Change**: either lower `BATCH` 8→6 in the four loops (:1276, :1325, :2561, :2899) to the empirically
safe width, or keep 8 and wrap each `parallel()` batch in a one-retry catch (re-run only the failed
agents of that batch) so a 429 costs seconds instead of a full manual `resumeFromRunId` cycle.
Prefer the latter: same throughput, removes the human from the loop the SKILL currently scripts in prose.
**Impact**: eliminates the most common cause of mid-run stalls; modest wall-clock cost (0-33% on the
debate phase depending on variant) — mostly recovered by P2 shrinking the batch count. **Effort: S.**
**Risk**: retry-in-workflow depends on the harness surfacing per-agent failures to the JS layer; verify
on one batch before rollout.

### P7 [SAFETY] Reserved-ticker quarantine at the write seam.
**Change**: one shared `safe_name(sym)` in the debate output path — reserved DOS names (CON, PRN, AUX,
NUL, COM1-9, LPT1-9) get a trailing underscore on the FILE name only (`CON_.json`), with the same
mapping applied at every read site (`publish_to_frontend.dossier_for`/`_opus_overlay`/history loop,
`compact_table.py`, `_value_post`/`_regime_post` result reads) and stripped for GCS object names
(GCS/Linux/Vercel don't care; only local NTFS + git do). Migrate the three existing CON.json files
(incl. untracking `speculair_debate_voiced/CON.json` in favor of the sanitized name).
**Impact**: permanently defuses the `git add`/checkout landmine class before the next reserved ticker
screens in; retires the need for the protectNTFS plumbing recipe for these files. **Effort: M**
(one function, ~6 read sites, small migration). **Risk**: a missed read site shows an empty debate for
that one ticker — grep-audit `results_regime /` and `HIST_DIR /` joins before shipping.

### Deliberately NOT proposed
- Moving Radar/Director seats to cheaper models: Radar is already Sonnet; Director/Skeptic are
  capability-bound kill/selection tiers on 1M context — the conviction-ceiling evidence says the
  bottleneck is funnel composition, not seat quality, so don't cheapen the layers that carry the money.
- Parallelizing the three books: total agent concurrency is rate-limit-bound (W5), so overlapping the
  disruptor debate with the value lens adds coordination risk for near-zero throughput.
- Anything touching funnel composition / the special-sit lane — just shipped, let it run.

---

## 4. IF YOU ONLY DO ONE THING

**P1 — harden the launcher (drop `2>&1`, sentinel-gated auto-resume, fail loudly).** It is S-effort,
and the evidence is three days old: the 06-28 scheduled run died at birth with a 162-byte log, nobody
was told, and the week's books shipped only because a human hand-drove resume cycles for two days.
Every other property of this pipeline — the guards, the skeptic teeth, the honest NAV — only exists in
weeks where the run actually happens.
