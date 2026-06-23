param(
    [string]$TaskName = "IELTS Claude Scheduled Refactor 0452",
    [string]$StartBoundary = "2026-06-22T04:52:00"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\liangjunming\Desktop\AI_Project"
$Runner = Join-Path $ProjectRoot "scripts\windows\run-claude-scheduled-refactor.cmd"

if (-not (Test-Path $Runner)) {
    throw "Runner not found: $Runner"
}

$TaskTriggerTime = [datetime]::Parse($StartBoundary)
if ($TaskTriggerTime -le (Get-Date)) {
    throw "Scheduled time has already passed: $StartBoundary"
}

$Service = New-Object -ComObject "Schedule.Service"
$Service.Connect()
$Root = $Service.GetFolder("\")

try {
    $Root.DeleteTask($TaskName, 0)
} catch {
    # Task did not exist.
}

$Task = $Service.NewTask(0)
$Task.RegistrationInfo.Description = "Run Claude Code Opus on IELTS Studio refactor task at 04:52."
$Task.Settings.Enabled = $true
$Task.Settings.StartWhenAvailable = $true
$Task.Settings.DisallowStartIfOnBatteries = $false
$Task.Settings.StopIfGoingOnBatteries = $false
$Task.Settings.ExecutionTimeLimit = "PT0S"

$Trigger = $Task.Triggers.Create(1)
$Trigger.StartBoundary = $TaskTriggerTime.ToString("yyyy-MM-ddTHH:mm:ss")
$Trigger.Enabled = $true

$Action = $Task.Actions.Create(0)
$Action.Path = $Runner
$Action.WorkingDirectory = $ProjectRoot

# 6 = TASK_CREATE_OR_UPDATE, 3 = TASK_LOGON_INTERACTIVE_TOKEN.
$Root.RegisterTaskDefinition($TaskName, $Task, 6, $null, $null, 3) | Out-Null

Write-Host "Registered task: $TaskName"
Write-Host "StartBoundary: $($Trigger.StartBoundary)"
Write-Host "Runner: $Runner"
