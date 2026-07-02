# run_supervisor.ps1 — nightly headless Claude audit of the trading bot.
# Same pattern as opus_strategist.ps1: `claude -p` on the gateway PC, key-free.
# The supervisor can only write reports + the HALT blob (see SUPERVISOR.md).
#
# Registration (elevated, after the EOD phase):
#   schtasks /create /tn "TradeBot-Supervisor" /tr "powershell -ExecutionPolicy Bypass -NoProfile -File C:\Users\Bruno\Stock-Screener\backend\tradebot\run_supervisor.ps1" /sc weekly /d MON,TUE,WED,THU,FRI /st 23:00 /rl HIGHEST /f

# EAP=Continue, not Stop: PS 5.1 wraps native stderr from `2>&1` in
# ErrorRecords; Stop kills the run on the first stderr line (seen 2026-07-02).
$ErrorActionPreference = "Continue"
$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo   = Split-Path -Parent (Split-Path -Parent $here)
$logdir = Join-Path $here "_logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$log = Join-Path $logdir ("supervisor_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

Set-Location $repo
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    "FATAL: claude CLI not on PATH" | Out-File -FilePath $log -Encoding utf8; exit 1
}

$prompt = @"
You are the TradeBot supervisor, running unattended on the gateway PC in the
Stock-Screener repo at $repo. Read backend/tradebot/SUPERVISOR.md IN FULL and
execute the audit checklist exactly. Honor the hard limits: you may only write
the nightly report to GCS tradebot/reports/ and, if a HALT criterion is met,
the GCS blob tradebot/HALT. Never place orders, never edit state or code.
Finish by printing the report verbatim.
"@

"=== tradebot supervisor START $(Get-Date -Format o) ===" | Out-File -FilePath $log -Encoding utf8
$prompt | claude -p --model opus --permission-mode bypassPermissions --output-format text 2>&1 |
    ForEach-Object { "$_" } | Out-File -FilePath $log -Encoding utf8 -Append
$code = $LASTEXITCODE
"=== tradebot supervisor END $(Get-Date -Format o) exit=$code ===" |
    Out-File -FilePath $log -Encoding utf8 -Append
exit $code
