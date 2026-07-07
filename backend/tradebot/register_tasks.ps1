# register_tasks.ps1 — (re)register the TradeBot scheduled tasks with the
# resilience settings that make the bot survive you not being logged into IBKR.
# Run ONCE, elevated (right-click > Run with PowerShell as admin), on the gateway PC.
#
# It replaces the old fixed Stage/Morning/EOD tasks with ONE self-healing watcher:
#   TradeBot-Watch  — every 15 min, MON–FRI, 11:45–23:45 CET. Each cycle runs any
#                     phase that's due (stage ~12:00, entries at the open, eod after
#                     the close) and not yet done today, connecting to IBKR only
#                     when it's up. Missed a phase because you weren't logged in?
#                     The next cycle after you log in runs it.
#   TradeBot-Supervisor — unchanged nightly Claude audit (kept as-is if present).
#
# Resilience settings applied to the watcher:
#   -StartWhenAvailable  : if the PC was asleep/off at a scheduled start, run ASAP
#                          on wake (covers "the PC wasn't even on").
#   -WakeToRun           : wake the PC to run (best-effort; laptop lids/hibernate
#                          can still veto — pair with IBKR IBC auto-login for a
#                          truly unattended box).
#   RestartOnFailure     : if a cycle errors, retry after 2 min, up to 3×.
#   Repetition 15 min    : the watcher itself; one registration, self-healing.

$ErrorActionPreference = "Stop"
$here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$wrapper = Join-Path $here "run_tradebot.ps1"
$psExe   = "powershell.exe"

# --- remove the superseded fixed-time tasks (safe if they don't exist) ---
foreach ($t in @("TradeBot-Stage", "TradeBot-Morning", "TradeBot-EOD")) {
    schtasks /delete /tn $t /f 2>$null | Out-Null
    if ($?) { "removed old task $t" }
}

# --- the self-healing watcher ---
$action = New-ScheduledTaskAction -Execute $psExe `
    -Argument "-ExecutionPolicy Bypass -NoProfile -File `"$wrapper`" watch"

# fire at 11:45 then repeat every 15 min for 12h (=> last cycle 23:45), MON–FRI
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 11:45
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At 11:45 `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Hours 12)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2)
$settings.DisallowStartIfOnBatteries = $false   # trade on a laptop too
$settings.StopIfGoingOnBatteries     = $false

Register-ScheduledTask -TaskName "TradeBot-Watch" -Action $action -Trigger $trigger `
    -Settings $settings -RunLevel Highest -Force

"registered TradeBot-Watch (every 15 min, MON-FRI 11:45-23:45, run-if-missed + wake)"
"NOTE: the watcher connects to IBKR on port $((Select-String -Path (Join-Path $here 'config.py') -Pattern 'ib_port: int = (\d+)').Matches.Groups[1].Value) — make sure whatever you log into (IB Gateway or TWS) is listening there."
