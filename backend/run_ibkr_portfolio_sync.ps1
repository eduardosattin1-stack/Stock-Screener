# run_ibkr_portfolio_sync.ps1 - durable launcher for the IBKR -> portfolio mirror.
#
# WHY THIS EXISTS
#   ibkr_portfolio_sync.py reads the live IBKR account (ib.portfolio() + account
#   values) and reconciles it into gs://screener-signals-carbonbridge/portfolio/
#   state.json, so the /portfolio page mirrors the real broker positions. Like the
#   options batch, it MUST run on this PC (the IB Gateway is at 127.0.0.1:4001; Cloud
#   Run can't reach it). Read-only throughout - never places an order.
#
# WHAT IT RUNS
#   1. A gateway API-liveness probe (ibkr_options.py --probe). If the gateway is
#      logged out / frozen / restarting, it NO-OPS and exits 0 - it never touches
#      state.json on a dead gateway (the reconcile also has its own 0-rows fail-safe).
#   2. python ibkr_portfolio_sync.py --once  (atomic conditional write to GCS).
#
# SCHEDULE (Windows Task Scheduler). EOD daily is enough for a position mirror;
# use a 30-min intraday cadence if you want fresher option marks. Example, 22:45 local
# Mon-Fri (after the US close, ~30 min after monitor-prices so the two don't collide):
#   schtasks /create /tn "IbkrPortfolioSync" `
#     /tr "powershell.exe -ExecutionPolicy Bypass -File C:\Users\Bruno\Stock-Screener\backend\run_ibkr_portfolio_sync.ps1" `
#     /sc weekly /d MON,TUE,WED,THU,FRI /st 22:45 /rl HIGHEST /f
#
# REQUIRES: python on PATH with ib_async installed; gcloud authed (GCS writes); the
#   IB Gateway running + logged in. Uses clientId 18 (distinct from the options
#   batch's 17) via IB_PORTFOLIO_CLIENT_ID. Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
$repo   = "C:\Users\Bruno\Stock-Screener"
$bk     = Join-Path $repo "backend"
$logdir = Join-Path $bk "_run_logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$stamp  = Get-Date -Format "yyyyMMdd_HHmmss"
$log    = Join-Path $logdir "ibkr_portfolio_sync_$stamp.log"

Set-Location $bk
"=== ibkr-portfolio-sync launcher START $(Get-Date -Format o) ===" | Tee-Object -FilePath $log

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { "FATAL: python not on PATH" | Tee-Object -FilePath $log -Append; exit 1 }

# Gateway liveness guard (port open != API answering). Exit 0 quietly if dead so the
# scheduled task isn't flagged failed and state.json is left untouched.
python ibkr_options.py --probe 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { "Gateway not answering - skipping sync (no write)." | Tee-Object -FilePath $log -Append; exit 0 }

$env:IB_PORTFOLIO_CLIENT_ID = "18"
python ibkr_portfolio_sync.py --once 2>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE

"=== launcher END $(Get-Date -Format o) exit=$code ===" | Tee-Object -FilePath $log -Append
exit $code
