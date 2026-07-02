# run_tradebot.ps1 <stage|morning|eod> — Task Scheduler wrapper for the bot phases.
#
# LIVE SWITCH: the bot trades real orders ONLY if the file LIVE.flag exists in
# this directory. No flag file = dry-run (orders logged, never placed). To halt
# everything instantly regardless: create TRADEBOT_HALT here, or the GCS blob
# tradebot/HALT (the supervisor uses the latter).
#
# SCHEDULE (verified against GCS archive timestamps: the nightly scan completes
# 04:05-04:30 UTC = ~06:30 CET with the PRIOR US session's closes; staging at
# noon CET gives >5h margin, and the morning entry the same day IS the scan's
# "next trading day open"). Times are LOCAL/CET — note US-EU DST misalignment
# shifts the ET-anchored morning run by 1h for ~3 weeks/yr.
# Task Scheduler registration (run once, elevated):
#   schtasks /create /tn "TradeBot-Stage"   /tr "powershell -ExecutionPolicy Bypass -NoProfile -File C:\Users\Bruno\Stock-Screener\backend\tradebot\run_tradebot.ps1 stage"   /sc weekly /d MON,TUE,WED,THU,FRI /st 12:00 /rl HIGHEST /f
#   schtasks /create /tn "TradeBot-Morning" /tr "powershell -ExecutionPolicy Bypass -NoProfile -File C:\Users\Bruno\Stock-Screener\backend\tradebot\run_tradebot.ps1 morning" /sc weekly /d MON,TUE,WED,THU,FRI /st 15:25 /rl HIGHEST /f
#   schtasks /create /tn "TradeBot-EOD"     /tr "powershell -ExecutionPolicy Bypass -NoProfile -File C:\Users\Bruno\Stock-Screener\backend\tradebot\run_tradebot.ps1 eod"     /sc weekly /d MON,TUE,WED,THU,FRI /st 22:15 /rl HIGHEST /f

param([Parameter(Mandatory = $true)][ValidateSet("stage", "morning", "eod")][string]$Phase)

$ErrorActionPreference = "Stop"
$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo   = Split-Path -Parent (Split-Path -Parent $here)   # ...\Stock-Screener
$logdir = Join-Path $here "_logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$log = Join-Path $logdir ("tradebot_{0}_{1}.log" -f $Phase, (Get-Date -Format "yyyyMMdd_HHmmss"))

Set-Location (Join-Path $repo "backend")
if (Test-Path (Join-Path $here "LIVE.flag")) { $env:TRADEBOT_LIVE = "1" }

"=== tradebot --$Phase START $(Get-Date -Format o) live=$($env:TRADEBOT_LIVE -eq '1') ===" |
    Tee-Object -FilePath $log
try {
    python -u -m tradebot.run_bot --$Phase 2>&1 | Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
} catch {
    "FATAL: $_" | Tee-Object -FilePath $log -Append
    $code = 1
}
"=== tradebot --$Phase END $(Get-Date -Format o) exit=$code ===" | Tee-Object -FilePath $log -Append
exit $code
