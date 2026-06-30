# SpeculairWeekly (apex book) — weekly refresh failing

**Detected:** 2026-06-30, while auditing a *separate* question (the methodology-basket entry dates).
**Scope:** This affects ONLY the weekly **apex** book (regime / value / disruptor lenses) driven by the
all-Opus Speculair debate. It does **NOT** affect the 12 methodology baskets (those rebalance on a monthly
cadence via the nightly Cloud Run scan and are healthy). It is also unrelated to the calibration tracker.

## Symptom

The Windows Task Scheduler job **`SpeculairWeekly`** has not completed a successful weekly refresh on its
last two scheduled Sundays. No fresh apex basket has been published since before 2026-06-21.

First-hand evidence (`schtasks /query /tn SpeculairWeekly /v`):

| Field | Value |
|---|---|
| Status | Ready / Enabled |
| Task To Run | `powershell.exe -ExecutionPolicy Bypass -File C:\Users\Bruno\Stock-Screener\backend\run_speculair_weekly.ps1` |
| Schedule | Weekly, SUN 01:00 local |
| **Last Run Time** | **2026-06-28 12:47:04** (note: NOT 01:00 — ran on missed-start catch-up, implying the PC was asleep/off at 01:00) |
| **Last Result** | **1** (non-zero = failure; success is 0) |
| Next Run Time | 2026-07-05 01:00 |

## What the run log shows

`backend/_opus_debate/_run_logs/speculair_weekly_20260628_124706.log` (UTF-16, 162 bytes) contains **only**:

```
=== speculair-opus-weekly launcher START 2026-06-28T12:47:06.0657965+02:00 ===
```

There is **no** `FATAL:` line and **no** `=== launcher END ... exit=N ===` line. So in
`run_speculair_weekly.ps1` the run got past the START banner (line 37) but the script terminated before
reaching the END banner (line 55) — i.e. it was **killed or threw a terminating error mid-run**, and the
headless `claude -p` pipeline (line 52) produced no captured output.

## Two-week timeline

- **2026-06-21** — The *old* Claude scheduled-task `speculair-opus-weekly` died at 01:29, right after PREP
  (141 candidates staged) but before the debate Workflow, because that runtime caps each run at ~20 min.
  This is documented in the header of `run_speculair_weekly.ps1` and is the reason the launcher was created
  (migration noted in memory `project_speculair_weekly_scheduling`). No basket published that week.
- **2026-06-28** — The *new* `SpeculairWeekly` launcher's first scheduled run failed as above (Result=1,
  START-only log). No basket published that week either.

Net: the weekly apex refresh has been relying on manual recovery; both automated attempts since the
migration have failed.

## Likely causes to investigate (unverified hypotheses)

1. **`claude` CLI not usable in the non-interactive Task Scheduler session.** The launcher runs as user
   `Bruno` headless. If the `claude` login/session or PATH differs in that context (or the subscription
   session token isn't available without an interactive login), `claude -p` exits non-zero immediately with
   no output — matching the START-only log. *Check:* run the exact command from a non-interactive context,
   or add `claude --version` + `whoami` echo to the launcher before the `claude -p` call.
2. **Missed-start + an "execution time limit" or "stop if runs longer than" on the task** killing the
   multi-hour run. The 12:47 catch-up start (vs 01:00) confirms the missed-start path fired; if the task's
   time limit is short, the long debate gets terminated → no END line. *Check:* `Stop task if it runs longer
   than` in the task's Settings (the verbose `schtasks` text format does not surface it; use Task Scheduler
   UI or `Get-ScheduledTask SpeculairWeekly | Select -Expand Settings`).
3. **PC asleep at 01:00 Sunday** so the run only fires hours later on wake (and may collide with other load).
   *Check:* enable "Wake the computer to run this task" / "Run task as soon as possible after a missed start".
4. **`$ErrorActionPreference = "Stop"`** turns any non-terminating hiccup in the `claude -p | Tee-Object`
   pipeline into a terminating exit before the END banner is written, swallowing the real error. *Check:*
   wrap the `claude -p` call in try/catch and log `$_` so the next failure is diagnosable.

## Suggested next step

Reproduce by running the launcher manually and watching output:

```powershell
powershell.exe -ExecutionPolicy Bypass -NoProfile -File C:\Users\Bruno\Stock-Screener\backend\run_speculair_weekly.ps1
```

If it works interactively but fails under the scheduler, the cause is environmental (#1/#2/#3); harden the
launcher (log `claude --version`, try/catch around `claude -p`, confirm wake/missed-start settings) before
the next scheduled run on **2026-07-05 01:00**.

## Key files / refs

- `backend/run_speculair_weekly.ps1` — the launcher (logs to `backend/_opus_debate/_run_logs/`).
- `C:\Users\Bruno\.claude\scheduled-tasks\speculair-opus-weekly\SKILL.md` — the runbook it executes.
- `backend/_opus_debate/_run_logs/speculair_weekly_20260628_124706.log` — the failed 06-28 run.
- Task: `SpeculairWeekly` (Task Scheduler, user Bruno, SUN 01:00).
- Memory: `project_speculair_weekly_scheduling`, `project_speculair_opus_pipeline`.
