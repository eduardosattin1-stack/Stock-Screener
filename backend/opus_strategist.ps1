# opus_strategist.ps1 - nightly Opus 4.8 option-strategy routine (runs on the IB Gateway PC).
#
#   1. gather  : opus_strategist_gather.py  -> strategy_input.json   (needs IB Gateway up)
#   2. design  : claude -p --model opus      -> strategy_output.json  (free on the subscription)
#   3. publish : opus_strategist_publish.py  -> GCS scans/options_strategies.json
#   4. paper   : opus_paper_tracker.py       -> GCS scans/options_paper.json + execution_input.json
#   5. execute : claude -p --model opus      -> execution_output.json (Opus closes/holds w/ real data)
#   6. apply   : opus_executor_apply.py      -> realizes the closes into the paper book
#
# This box runs Windows PowerShell 5.1 (no 'pwsh'). Run / schedule with:
#   powershell.exe -ExecutionPolicy Bypass -File C:\Users\Bruno\Stock-Screener\backend\opus_strategist.ps1
# Schedule via Task Scheduler AFTER the nightly ibkr_options_batch (gateway already logged in).
#
# Requires: 'claude' CLI on PATH, gcloud authed (for the GCS write), IB Gateway on 127.0.0.1:4001.

$ErrorActionPreference = "Stop"
$here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$prompt  = Join-Path $here "opus_strategist_prompt.md"
$inFile  = Join-Path $here "strategy_input.json"
$outFile = Join-Path $here "strategy_output.json"

Write-Host "[1/6] gather - selecting D9/D10 picks + pulling IBKR chains..."
python (Join-Path $here "opus_strategist_gather.py")
if ($LASTEXITCODE -ne 0) { throw "gather failed (exit $LASTEXITCODE)" }
if (-not (Test-Path $inFile)) { throw "no $inFile produced" }

$picks = (Get-Content $inFile -Raw -Encoding UTF8 | ConvertFrom-Json).count
if ($picks -lt 1) { Write-Host "no D9/D10 picks tonight - nothing to design. done."; exit 0 }
Write-Host "      $picks pick(s) gathered."

Write-Host "[2/6] design - asking Opus 4.8 for the best strategy per name..."
$system   = Get-Content $prompt -Raw -Encoding UTF8
$data     = Get-Content $inFile -Raw -Encoding UTF8
$combined = $system + "`n`n--- strategy_input.json ---`n" + $data + "`n`nReturn ONLY the JSON object keyed by symbol - no prose, no markdown fences."
$design   = $combined | claude -p --model opus --output-format text | Out-String
if ($LASTEXITCODE -ne 0) { throw "claude design step failed (exit $LASTEXITCODE)" }
if ([string]::IsNullOrWhiteSpace($design)) { throw "empty strategy_output.json" }
# Write UTF-8 WITHOUT BOM so publish.py's json.loads is happy.
[System.IO.File]::WriteAllText($outFile, $design, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "[3/6] publish - uploading to GCS scans/options_strategies.json..."
python (Join-Path $here "opus_strategist_publish.py") $outFile
if ($LASTEXITCODE -ne 0) { throw "publish failed (exit $LASTEXITCODE)" }

Write-Host "[4/6] paper - opening + marking the paper book (forward-test)..."
python (Join-Path $here "opus_paper_tracker.py")
if ($LASTEXITCODE -ne 0) { throw "paper tracker failed (exit $LASTEXITCODE)" }

# 5/6 + 6/6 — Opus execution layer: decide CLOSE/HOLD on open positions with real data.
$execIn  = Join-Path $here "execution_input.json"
$execOut = Join-Path $here "execution_output.json"
$nOpen = 0
if (Test-Path $execIn) { $nOpen = @((Get-Content $execIn -Raw -Encoding UTF8 | ConvertFrom-Json).positions).Count }
if ($nOpen -ge 1) {
  Write-Host "[5/6] execute - asking Opus to manage $nOpen open position(s)..."
  $esys  = Get-Content (Join-Path $here "opus_executor_prompt.md") -Raw -Encoding UTF8
  $edata = Get-Content $execIn -Raw -Encoding UTF8
  $ecomb = $esys + "`n`n--- execution_input.json ---`n" + $edata + "`n`nReturn ONLY the JSON object {""decisions"":[...]} - no prose, no markdown fences."
  $eout  = $ecomb | claude -p --model opus --output-format text | Out-String
  if ($LASTEXITCODE -ne 0) { throw "claude execute step failed (exit $LASTEXITCODE)" }
  [System.IO.File]::WriteAllText($execOut, $eout, (New-Object System.Text.UTF8Encoding($false)))

  Write-Host "[6/6] apply - realizing Opus closes into the paper book..."
  python (Join-Path $here "opus_executor_apply.py") $execOut
  if ($LASTEXITCODE -ne 0) { throw "executor apply failed (exit $LASTEXITCODE)" }
} else {
  Write-Host "[5/6] execute - no open positions to manage; skipping."
}

Write-Host "done."
