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
# HARDENED 2026-07-01 (after the 06-28 run died at birth with a 162-byte log):
#   1. NO `2>&1` on the native `claude` call and $ErrorActionPreference=Continue for the
#      invocation region: under PS 5.1 + EAP=Stop, redirecting native stderr wraps each
#      line in a NativeCommandError that TERMINATES the script on the first stderr byte
#      (the prime suspect for the instant death). stderr goes to a sidecar .err file.
#   2. COMPLETION SENTINEL, not exit-code trust: the run counts as complete only if the
#      agent printed `RUN_OUTCOME: COMPLETED`, or the apex JSON is fresher than launch
#      AND the publish `LIVE readback` line is in the log. A deliberate guard stop
#      (`RUN_OUTCOME: GUARD_STOP <reason>`) is NOT a death - no resume, loud flag.
#   3. BOUNDED AUTO-RESUME x2: on a death (no sentinel), re-invoke with a resume prompt -
#      cached Workflow agents return instantly, so this is exactly the manual 2-3-cycle
#      babysit, automated. Bounded so a genuinely broken run can't burn the session.
#   4. FAIL LOUD: on final failure (or guard stop) write FAILED_SPECULAIR_<stamp>.flag at
#      the repo root (git-visible; the next interactive session trips over it) and ALWAYS
#      log the END line in a finally.
#
# WHAT IT RUNS
#   The exact SKILL.md runbook (STEP 1 PREP -> STEP 1B SPECIAL-SIT LANE -> STEP 2
#   DEBATE+DIRECTOR Workflow -> STEP 2B REGIME SKEPTIC + POST -> STEP 3 PUBLISH --gcs ->
#   STEP 3B VALUE LENS -> STEP 4 REPORT), every GUARD honored. It only refreshes GCS
#   data (no Cloud Run, no frontend deploy). Runs key-free on the Claude subscription
#   (Opus 4.8 subagents).
#   (STEP 3C DISRUPTOR LENS retired 2026-07-02 — FUTURE_RESOURCES_SPEC.md sec 10; the
#    Future Resources STEP takes this slot at its Phase 3. The local SKILL.md no longer
#    needs a manual edit — this launcher self-patches it below via
#    backend/_retire_disruptor_skill.py before the agent ever reads it.)
#
# SCHEDULE (Windows Task Scheduler), Sunday 01:00 local:
#   schtasks /create /tn "SpeculairWeekly" `
#     /tr "powershell.exe -ExecutionPolicy Bypass -File C:\Users\Bruno\Stock-Screener\backend\run_speculair_weekly.ps1" `
#     /sc weekly /d SUN /st 01:00 /rl HIGHEST /f
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
$errlog = "$log.err"
$apex   = Join-Path $repo "backend\_opus_debate\apex_basket_opus_regime.json"
$flag   = Join-Path $repo "FAILED_SPECULAIR_$stamp.flag"

Set-Location $repo
"=== speculair-opus-weekly launcher START $(Get-Date -Format o) ===" | Tee-Object -FilePath $log

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { "FATAL: claude CLI not on PATH" | Tee-Object -FilePath $log -Append; Set-Content -Path $flag -Value "claude CLI not on PATH"; exit 1 }
if (-not (Test-Path $skill)) { "FATAL: SKILL.md not found at $skill" | Tee-Object -FilePath $log -Append; Set-Content -Path $flag -Value "SKILL.md missing"; exit 1 }

# FRESHNESS GUARD (2026-07-11): a manual mid-week run counts as that week's refresh - if the
# regime apex was published fewer than 4 days ago, skip instead of double-charging the week
# (the 2026-07-11 Friday run would otherwise re-run on Sunday for zero new information).
# Override: set SPECULAIR_FORCE=1 to run regardless. ASCII ONLY in this file: it has no BOM,
# so PowerShell 5.1 reads it as ANSI and UTF-8 punctuation decodes into string-breaking quotes.
if ((Test-Path $apex) -and ($env:SPECULAIR_FORCE -ne "1")) {
    $ageDays = ((Get-Date) - (Get-Item $apex).LastWriteTime).TotalDays
    if ($ageDays -lt 4) {
        "SKIPPED: regime apex is only {0:N1} days old (under 4d) - this week's refresh already ran. Set SPECULAIR_FORCE=1 to override." -f $ageDays | Tee-Object -FilePath $log -Append
        exit 0
    }
}

# One-time retirement hygiene (idempotent, best-effort): strip the retired STEP 3C
# DISRUPTOR block from the local SKILL.md BEFORE the agent reads it (writes a .bak_*
# beside it; no-op once clean). The prompt's disruptor-skip line below is the safety
# net if this fails. FUTURE_RESOURCES_SPEC.md sec 10.1.
try { python (Join-Path $repo "backend\_retire_disruptor_skill.py") $skill 2>&1 | Tee-Object -FilePath $log -Append }
catch { "WARN: skill patcher failed - relying on the prompt's disruptor-skip instruction" | Tee-Object -FilePath $log -Append }

# The full runbook is in SKILL.md; the prompt just points the headless agent at it.
# RUN_OUTCOME is the machine sentinel this launcher keys on - keep it in sync with the loop below.
$basePrompt = @"
You are running the weekly all-Opus Speculair refresh, fully unattended, in the Stock-Screener repo at $repo. You have NO memory of prior conversations.
Read the runbook at $skill IN FULL, then execute EVERY step end-to-end:
  STEP 1 PREP  ->  STEP 1B APEX SPECIAL-SIT LANE (catalyst-prep -> Workflow -> catalyst-seed; OPTIONAL, skip silently if catalyst-prep reports no candidates)  ->  STEP 2 DEBATE + DIRECTOR (use the Workflow tool on the printed WORKFLOW_SCRIPT)  ->  STEP 2B REGIME SKEPTIC + REGIME-POST  ->  STEP 3 PUBLISH --gcs  ->  STEP 3B VALUE LENS  ->  STEP 4 VERIFY + REPORT.
The DISRUPTOR LENS (old STEP 3C) is RETIRED — do NOT run any disruptor-* mode even if the runbook still mentions it; skip it silently and note the skip in the report.
Honor every GUARD exactly: if a GUARD trips, STOP that book and report rather than publishing degraded data. Do not skip steps. Do not edit screener_v6.py / the Cloud Run scan / the frontend. When finished, print the STEP 4 summary (regime apex 10 + value apex 10 + cross-lens names + any caveats).
MANDATORY LAST LINE (machine sentinel): print exactly 'RUN_OUTCOME: COMPLETED' if every step ran (guard-stopped side books are still COMPLETED if the regime apex published), or 'RUN_OUTCOME: GUARD_STOP <one-line reason>' if a GUARD stopped the MAIN regime pipeline before publish.
"@

$resumePrompt = @"
You are RESUMING a partially-complete weekly all-Opus Speculair refresh in $repo (the prior headless attempt died mid-run; its log is at $log). You have NO memory of it.
Read the runbook at $skill IN FULL. Determine which steps already completed THIS run (fresh mtimes on backend/_opus_debate/results_regime/, apex_basket_opus_regime.json, the publish readback in the log) and CONTINUE from the first unfinished step. Re-invoking the SAME Workflow script is safe and cheap - cached agents return instantly, only gaps re-run. Honor every GUARD.
The DISRUPTOR LENS (old STEP 3C) is RETIRED — do NOT run any disruptor-* mode even if the runbook still mentions it; skip it silently and note the skip in the report.
MANDATORY LAST LINE (machine sentinel): print exactly 'RUN_OUTCOME: COMPLETED' or 'RUN_OUTCOME: GUARD_STOP <one-line reason>'.
"@

# Native stderr must never kill the run (the 06-28 162-byte death). Sidecar-file stderr, EAP=Continue.
$ErrorActionPreference = "Continue"
$launchTime = Get-Date
$outcome = "DEAD"
try {
  for ($attempt = 1; $attempt -le 3; $attempt++) {
    $p = if ($attempt -eq 1) { $basePrompt } else { $resumePrompt }
    "--- attempt $attempt START $(Get-Date -Format o) ---" | Tee-Object -FilePath $log -Append
    $p | claude -p --model opus --permission-mode bypassPermissions --output-format text 2>>$errlog | Tee-Object -FilePath $log -Append
    "--- attempt $attempt END exit=$LASTEXITCODE $(Get-Date -Format o) ---" | Tee-Object -FilePath $log -Append

    # SENTINEL (not exit code): COMPLETED line, or fresh apex + publish readback.
    $txt = ""
    try { $txt = Get-Content $log -Raw -ErrorAction Stop } catch {}
    if ($txt -match "RUN_OUTCOME:\s*GUARD_STOP") { $outcome = "GUARD_STOP"; break }   # deliberate stop - do NOT resume
    $apexFresh = (Test-Path $apex) -and ((Get-Item $apex).LastWriteTime -gt $launchTime)
    if (($txt -match "RUN_OUTCOME:\s*COMPLETED") -or ($apexFresh -and $txt -match "LIVE readback")) { $outcome = "COMPLETED"; break }
    "sentinel absent after attempt $attempt (apexFresh=$apexFresh) - $(if($attempt -lt 3){'auto-resuming'}else{'giving up'})" | Tee-Object -FilePath $log -Append
  }
}
finally {
  if ($outcome -eq "GUARD_STOP") {
    $reason = if ($txt -match "RUN_OUTCOME:\s*GUARD_STOP\s*(.*)") { $Matches[1] } else { "(reason not captured)" }
    Set-Content -Path $flag -Value "GUARD_STOP: $reason`nlog: $log"
    "GUARD STOP (deliberate, no resume): $reason - flag written: $flag" | Tee-Object -FilePath $log -Append
  }
  elseif ($outcome -ne "COMPLETED") {
    Set-Content -Path $flag -Value "DEAD after 3 attempts (no completion sentinel)`nlog: $log`nerr: $errlog"
    "FAILED after 3 attempts - flag written: $flag" | Tee-Object -FilePath $log -Append
  }
  "=== launcher END $(Get-Date -Format o) outcome=$outcome ===" | Tee-Object -FilePath $log -Append
}
if ($outcome -eq "COMPLETED") { exit 0 } else { exit 1 }
