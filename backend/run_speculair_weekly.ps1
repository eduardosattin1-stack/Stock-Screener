# run_speculair_weekly.ps1 - durable launcher for the weekly all-Opus Speculair refresh.
#
# WHY THIS EXISTS
#   The Claude scheduled-task "speculair-opus-weekly" fires Sun 01:09, but the
#   scheduled-task runtime caps each run at ~20 min of wall-clock - far short of the
#   multi-hour debate+publish pipeline. On 2026-06-21 the run died at 01:29, right
#   after PREP completed (141 candidates staged) but BEFORE the debate Workflow ran,
#   so no fresh basket was published that week. This launcher runs the SAME runbook
#   as a headless `claude -p` (print mode has no turn/time cap), so the full pipeline
#   completes unattended - the same pattern as opus_strategist.ps1 on the gateway PC.
#
# WHAT IT RUNS
#   The exact SKILL.md runbook (STEP 1 PREP -> STEP 2 DEBATE+DIRECTOR Workflow ->
#   STEP 3 PUBLISH --gcs -> STEP 3B VALUE LENS -> STEP 3C DISRUPTOR LENS -> STEP 4
#   REPORT), every GUARD honored. It only refreshes GCS data (no Cloud Run, no
#   frontend deploy). Runs key-free on the Claude subscription (Opus 4.8 subagents).
#
# SCHEDULE (Windows Task Scheduler), Sunday 01:00 local:
#   schtasks /create /tn "SpeculairWeekly" `
#     /tr "powershell.exe -ExecutionPolicy Bypass -File C:\Users\Bruno\Stock-Screener\backend\run_speculair_weekly.ps1" `
#     /sc weekly /d SUN /st 01:00 /rl HIGHEST /f
#   (then DISABLE the Claude scheduled-task `speculair-opus-weekly` so it doesn't
#    double-fire-and-timeout; this launcher replaces it.)
#
# REQUIRES: `claude` CLI on PATH + logged in; gcloud authed (GCS writes); FMP key in
#   env (already configured for the nightly box). Windows PowerShell 5.1 (no pwsh).

$ErrorActionPreference = "Stop"
$repo   = "C:\Users\Bruno\Stock-Screener"
$skill  = "C:\Users\Bruno\.claude\scheduled-tasks\speculair-opus-weekly\SKILL.md"
$logdir = Join-Path $repo "backend\_opus_debate\_run_logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$stamp  = Get-Date -Format "yyyyMMdd_HHmmss"
$log    = Join-Path $logdir "speculair_weekly_$stamp.log"

Set-Location $repo
"=== speculair-opus-weekly launcher START $(Get-Date -Format o) ===" | Tee-Object -FilePath $log

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { "FATAL: claude CLI not on PATH" | Tee-Object -FilePath $log -Append; exit 1 }
if (-not (Test-Path $skill)) { "FATAL: SKILL.md not found at $skill" | Tee-Object -FilePath $log -Append; exit 1 }

# The full runbook is in SKILL.md; the prompt just points the headless agent at it.
$prompt = @"
You are running the weekly all-Opus Speculair refresh, fully unattended, in the Stock-Screener repo at $repo. You have NO memory of prior conversations.
Read the runbook at $skill IN FULL, then execute EVERY step end-to-end:
  STEP 1 PREP  ->  STEP 1B APEX SPECIAL-SIT LANE (catalyst-prep -> Workflow -> catalyst-seed; OPTIONAL, skip silently if catalyst-prep reports no candidates)  ->  STEP 2 DEBATE + DIRECTOR (use the Workflow tool on the printed WORKFLOW_SCRIPT)  ->  STEP 3 PUBLISH --gcs  ->  STEP 3B VALUE LENS  ->  STEP 3C DISRUPTOR LENS  ->  STEP 4 VERIFY + REPORT.
Honor every GUARD exactly: if a GUARD trips, STOP that book and report rather than publishing degraded data. Do not skip steps. Do not edit screener_v6.py / the Cloud Run scan / the frontend. When finished, print the STEP 4 summary (regime apex 10 + value apex 10 + cross-lens names + any caveats).
"@

# Headless, unattended, no turn cap. bypassPermissions = the runbook's commands are
# pre-allowlisted; this box + repo are trusted and Bruno owns this routine.
$prompt | claude -p --model opus --permission-mode bypassPermissions --output-format text 2>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE

"=== launcher END $(Get-Date -Format o) exit=$code ===" | Tee-Object -FilePath $log -Append
exit $code
