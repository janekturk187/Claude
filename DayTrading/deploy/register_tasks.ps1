# register_tasks.ps1 — register Windows Task Scheduler tasks for the trading system.
#
# Run once from an elevated PowerShell prompt:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\deploy\register_tasks.ps1
#
# Times are set for Mountain Time (MT = ET - 2h).

$tradingDir = "C:\Users\ironm\claude\DayTrading"
$deployDir  = "$tradingDir\deploy"

$days = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

$taskSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 10) `
    -RestartCount 0 `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable $false

# ---------------------------------------------------------------------------
# Task 1: Start paper session at 9:35 AM ET (Mon–Fri)
# ---------------------------------------------------------------------------
$startAction  = New-ScheduledTaskAction `
    -Execute    "cmd.exe" `
    -Argument   "/c `"$deployDir\start_paper.bat`"" `
    -WorkingDirectory $tradingDir

$startTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek $days `
    -At "7:35AM"

Register-ScheduledTask `
    -TaskName   "DayTrading - Start Paper Session" `
    -Action     $startAction `
    -Trigger    $startTrigger `
    -Settings   $taskSettings `
    -Description "Starts the day trading system in paper mode at market open." `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Host "Registered: DayTrading - Start Paper Session  (weekdays 7:35 AM MT)"

# ---------------------------------------------------------------------------
# Task 2: Stop session and generate report at 4:05 PM ET (Mon–Fri)
# ---------------------------------------------------------------------------
$stopAction  = New-ScheduledTaskAction `
    -Execute    "cmd.exe" `
    -Argument   "/c `"$deployDir\stop_trading.bat`"" `
    -WorkingDirectory $tradingDir

$stopTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek $days `
    -At "2:05PM"

Register-ScheduledTask `
    -TaskName   "DayTrading - Stop Session" `
    -Action     $stopAction `
    -Trigger    $stopTrigger `
    -Settings   $taskSettings `
    -Description "Stops the trading system and generates the session report." `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Host "Registered: DayTrading - Stop Session          (weekdays 2:05 PM MT)"

Write-Host ""
Write-Host "All tasks registered. Next steps:"
Write-Host "  1. Fill in your API keys in deploy\env.bat"
Write-Host "  2. Verify the tasks in Task Scheduler (taskschd.msc)"
Write-Host "  3. Right-click each task -> Run to test manually"
Write-Host ""
Write-Host "Logs will appear in: $tradingDir\logs\"
Write-Host "Session reports in:  $tradingDir\reports_output\"
