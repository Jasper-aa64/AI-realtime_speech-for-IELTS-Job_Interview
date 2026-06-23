param(
    [string]$TaskName = "IELTS Claude Scheduled Refactor 0452",
    [datetime]$RunAt = [datetime]"2026-06-22T04:52:00"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\liangjunming\Desktop\AI_Project"
$Runner = Join-Path $ProjectRoot "scripts\windows\run-claude-scheduled-refactor.ps1"

if (-not (Test-Path $Runner)) {
    throw "Runner not found: $Runner"
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Once -At $RunAt
$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null

Write-Host "Registered task: $TaskName"
Write-Host "RunAt: $($RunAt.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "Runner: $Runner"

