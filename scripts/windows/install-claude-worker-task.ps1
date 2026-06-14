# Install a no-password Scheduled Task that starts the AI worker as the
# currently logged-in Windows user. Run from an elevated PowerShell.

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$TaskName = "IELTS Studio Claude AI Worker"
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$ScriptPath = Join-Path $ProjectRoot "scripts\windows\run-ai-worker-user.ps1"
$TaskArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $TaskArgs -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$Principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed and started task: $TaskName"
Write-Host "User: $UserId"
Write-Host "Logs: $(Join-Path $ProjectRoot '.runlogs')"

