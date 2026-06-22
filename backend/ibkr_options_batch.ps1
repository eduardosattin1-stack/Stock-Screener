# ibkr_options_batch.ps1 - nightly IBKR IV/spread enrichment -> GCS scans/options_latest.json.
#
# This is the FIRST half of the options pipeline (the per-symbol IV-rank + spread the stock card
# reads); opus_strategist.ps1 (the Opus strategy half) runs AFTER it. It had NO scheduled task,
# so options_latest.json went stale (last manual run 06-19). Schedule this at ~09:00 (before the
# 09:30 strategist), gateway-up guarded so it never hard-fails on a late gateway.
#
# Windows PowerShell 5.1. Schedule:
#   schtasks via Register-ScheduledTask "IbkrOptionsBatch" -> this file, daily ~09:00.
# Requires: IB Gateway on 127.0.0.1:4001, gcloud authed, FMP/GCS env configured.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# Gateway-up guard (same as opus_strategist.ps1): wait up to 20 min for IB Gateway, else skip gracefully.
function Test-GatewayUp { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 4001); $c.Close(); $true } catch { $false } }
Write-Host "waiting for IB Gateway on 127.0.0.1:4001 (up to 20 min)..."
$deadline = (Get-Date).AddMinutes(20)
while (-not (Test-GatewayUp) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 30 }
if (-not (Test-GatewayUp)) { Write-Host "IB Gateway not up - skipping options batch (card keeps prior data; retries next schedule)."; exit 0 }

Write-Host "IB Gateway up - enriching IV/spread (full universe) -> scans/options_latest.json ..."
python (Join-Path $here "ibkr_options_batch.py")
exit $LASTEXITCODE
