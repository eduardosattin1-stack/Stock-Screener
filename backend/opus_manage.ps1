# opus_manage.ps1 - mark the paper book + Opus close/hold pass (the "manage" half).
#
#   a. paper   : opus_paper_tracker.py   -> re-mark open positions from live IBKR quotes,
#                settle expiries, write execution_input.json  (open-new is a no-op intraday
#                since strategies publish once nightly)
#   b. execute : claude -p --model opus   -> execution_output.json (CLOSE/HOLD w/ real data)
#   c. apply   : opus_executor_apply.py   -> realize the closes into the paper book
#
# Run STANDALONE intraday (every ~30 min during US market hours) so Opus can manage exits
# on LIVE prices, AND called by opus_strategist.ps1 at the nightly run. Windows PS 5.1:
#   powershell.exe -ExecutionPolicy Bypass -File C:\Users\Bruno\Stock-Screener\backend\opus_manage.ps1
# Requires: 'claude' on PATH, gcloud authed, IB Gateway on 127.0.0.1:4001.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# Gateway-up guard (same as opus_strategist.ps1): the intraday task can fire before IB Gateway is up.
# Wait up to 10 min, then skip this pass gracefully (the next interval retries) rather than hard-fail.
function Test-GatewayUp { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 4001); $c.Close(); $true } catch { $false } }
$deadline = (Get-Date).AddMinutes(10)
while (-not (Test-GatewayUp) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 30 }
if (-not (Test-GatewayUp)) { Write-Host "IB Gateway not up - skipping this manage pass (retries next interval)."; exit 0 }

Write-Host "[paper] marking the paper book from live IBKR quotes..."
python (Join-Path $here "opus_paper_tracker.py")
if ($LASTEXITCODE -ne 0) { throw "paper tracker failed (exit $LASTEXITCODE)" }

$execIn  = Join-Path $here "execution_input.json"
$execOut = Join-Path $here "execution_output.json"
$nOpen = 0
if (Test-Path $execIn) { $nOpen = @((Get-Content $execIn -Raw -Encoding UTF8 | ConvertFrom-Json).positions).Count }
if ($nOpen -ge 1) {
  Write-Host "[execute] asking Opus to manage $nOpen open position(s)..."
  $esys  = Get-Content (Join-Path $here "opus_executor_prompt.md") -Raw -Encoding UTF8
  $edata = Get-Content $execIn -Raw -Encoding UTF8
  $ecomb = $esys + "`n`n--- execution_input.json ---`n" + $edata + "`n`nReturn ONLY the JSON object {""decisions"":[...]} - no prose, no markdown fences."
  $eout  = $ecomb | claude -p --model opus --output-format text | Out-String
  if ($LASTEXITCODE -ne 0) { throw "claude execute step failed (exit $LASTEXITCODE)" }
  [System.IO.File]::WriteAllText($execOut, $eout, (New-Object System.Text.UTF8Encoding($false)))

  Write-Host "[apply] realizing Opus closes into the paper book..."
  python (Join-Path $here "opus_executor_apply.py") $execOut
  if ($LASTEXITCODE -ne 0) { throw "executor apply failed (exit $LASTEXITCODE)" }
} else {
  Write-Host "[execute] no open positions to manage; skipping."
}

Write-Host "manage done."
