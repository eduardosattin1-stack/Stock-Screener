# run_tradebot.ps1 <watch|stage|morning|eod|show> — Task Scheduler wrapper.
#
# NORMAL MODE is "watch": a single self-healing task that fires every ~15 min and
# runs whichever phase is due-and-not-done, reaching IBKR only when it's actually
# logged in. So if you weren't logged into Trader Workstation / IB Gateway when a
# phase was supposed to run, the next watch cycle after you log in runs it (each
# phase is idempotent per session, so nothing double-fires). Register it with
# register_tasks.ps1 (which also removes the old fixed Stage/Morning/EOD tasks).
#
# LIVE SWITCH: the bot trades real orders ONLY if the file LIVE.flag exists in
# this directory. No flag file = dry-run (orders logged, never placed). Halt
# instantly: create TRADEBOT_HALT here, or the GCS blob tradebot/HALT.

param([Parameter(Mandatory = $true)][ValidateSet("watch", "stage", "morning", "eod", "show")][string]$Phase)

# "Continue", NOT "Stop": in Windows PowerShell 5.1, `2>&1` on a native command
# wraps every stderr line in an ErrorRecord — under EAP=Stop the FIRST such line
# becomes a terminating error and kills the run (this happened on 2026-07-02:
# python's first INFO log line, on stderr, aborted all three phases with exit=1).
$ErrorActionPreference = "Continue"
$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo   = Split-Path -Parent (Split-Path -Parent $here)   # ...\Stock-Screener
$logdir = Join-Path $here "_logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$log = Join-Path $logdir ("tradebot_{0}_{1}.log" -f $Phase, (Get-Date -Format "yyyyMMdd_HHmmss"))

Set-Location (Join-Path $repo "backend")
if (Test-Path (Join-Path $here "LIVE.flag")) { $env:TRADEBOT_LIVE = "1" }

"=== tradebot --$Phase START $(Get-Date -Format o) live=$($env:TRADEBOT_LIVE -eq '1') ===" |
    Out-File -FilePath $log -Encoding utf8
# ForEach stringifies any ErrorRecords to plain text; utf8 keeps the log greppable
python -u -m tradebot.run_bot --$Phase 2>&1 | ForEach-Object { "$_" } |
    Out-File -FilePath $log -Encoding utf8 -Append
$code = $LASTEXITCODE
"=== tradebot --$Phase END $(Get-Date -Format o) exit=$code ===" |
    Out-File -FilePath $log -Encoding utf8 -Append
exit $code
