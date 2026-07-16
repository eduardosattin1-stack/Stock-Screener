# _watchdog_speculair.ps1 (v2, 2026-07-16 night) - session-independent safety net for the weekly
# Speculair launcher. Registered via Windows Task Scheduler (schtasks), so it runs under the OS
# Task Scheduler service - NOT as a child process of any Claude Code session - and survives even
# if the session that registered it times out or is torn down.
#
# v2: loop-capable. Tonight's pattern was 4 consecutive dead runs, all from the SAME shared
# session-limit wall (resets stated in-log, e.g. "resets 11:30pm") - a single relaunch-then-exit
# (v1) isn't enough when the limit re-hits. This version relaunches repeatedly (bounded), with a
# backoff pause after a session-limit death so it doesn't immediately re-burn 3 attempts into the
# same wall, until either a COMPLETED sentinel appears or the relaunch budget is exhausted.
#
# Detection logic (conservative - only acts on strong signals):
#   SUCCESS = the newest speculair_weekly_*.log shows "RUN_OUTCOME: COMPLETED" or "outcome=COMPLETED"
#   FAILURE = a FAILED_SPECULAIR_*.flag appears with a timestamp AFTER this watchdog started
#             (ignores stale flags from earlier dead attempts already on disk)
#   SESSION-LIMIT DEATH = the dead run's log contains "session limit" -> back off before retrying
#     (a raw exhausted-budget retry just re-dies in seconds, as seen twice tonight)

param(
  [int]$MaxMinutes = 240,
  [int]$MaxRelaunches = 6,
  [int]$BackoffMinutesOnSessionLimit = 20
)

$repo = "C:\Users\Bruno\Stock-Screener"
$logdir = Join-Path $repo "backend\_opus_debate\_run_logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$wlog = Join-Path $logdir "watchdog_$(Get-Date -Format yyyyMMdd_HHmmss).log"
$watchdogStart = Get-Date
"watchdog v2 START $($watchdogStart.ToString('o')) - budget ${MaxMinutes}m, max $MaxRelaunches relaunches" | Out-File -FilePath $wlog -Encoding utf8

function Get-NewestWeeklyLog {
    Get-ChildItem -Path $logdir -Filter "speculair_weekly_*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

$deadline = $watchdogStart.AddMinutes($MaxMinutes)
$relaunchCount = 0
$sinceMarker = $watchdogStart

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 300   # poll every 5 min

    $newestLog = Get-NewestWeeklyLog
    $txt = ""
    if ($newestLog) { try { $txt = Get-Content -LiteralPath $newestLog.FullName -Raw -ErrorAction Stop } catch {} }
    if ($txt -match "RUN_OUTCOME:\s*COMPLETED" -or $txt -match "outcome=COMPLETED") {
        "$(Get-Date -Format o): COMPLETED sentinel found in $($newestLog.Name) - watchdog exiting, no further action needed" | Out-File -FilePath $wlog -Append
        exit 0
    }

    $newFlag = Get-ChildItem -Path $repo -Filter "FAILED_SPECULAIR_*.flag" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $sinceMarker } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $newFlag) { continue }   # still running quietly in the foreground - normal for print-mode

    if ($relaunchCount -ge $MaxRelaunches) {
        "$(Get-Date -Format o): new failure flag $($newFlag.Name) but relaunch budget ($MaxRelaunches) exhausted - giving up, leaving flag for manual review" | Out-File -FilePath $wlog -Append
        exit 1
    }

    $sessionLimited = $txt -match "session limit"
    if ($sessionLimited) {
        "$(Get-Date -Format o): $($newFlag.Name) died on a session-limit wall - backing off ${BackoffMinutesOnSessionLimit}m before retrying (raw retry just re-dies in seconds)" | Out-File -FilePath $wlog -Append
        Start-Sleep -Seconds ($BackoffMinutesOnSessionLimit * 60)
    } else {
        "$(Get-Date -Format o): $($newFlag.Name) died for a NON-session-limit reason - see $($newestLog.Name) for details; relaunching anyway (bounded) but flagging for review" | Out-File -FilePath $wlog -Append
    }

    $relaunchCount++
    "$(Get-Date -Format o): relaunch #$relaunchCount of $MaxRelaunches - starting run_speculair_weekly.ps1 (SPECULAIR_FORCE=1)" | Out-File -FilePath $wlog -Append
    $env:SPECULAIR_FORCE = "1"
    Start-Process powershell -ArgumentList "-ExecutionPolicy","Bypass","-File","$repo\backend\run_speculair_weekly.ps1" -WindowStyle Hidden
    $sinceMarker = Get-Date   # only react to flags from THIS relaunch onward
    Start-Sleep -Seconds 30   # let the new launcher create its log before the next poll
}
"$(Get-Date -Format o): watchdog budget (${MaxMinutes}m) exhausted with no COMPLETED sentinel - exiting without further action ($relaunchCount relaunch(es) attempted; check manually)" | Out-File -FilePath $wlog -Append
