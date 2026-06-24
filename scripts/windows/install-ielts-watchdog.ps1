# Install the IELTS stack watchdog as a per-user Scheduled Task.
#
# Runs as the currently logged-in user at the DEFAULT (limited) run level, so it
# needs NO administrator. Triggers at logon AND repeats every few minutes, so the
# backend comes up at sign-in and is auto-recovered if anything kills it.
#
# Usage (normal, non-elevated PowerShell):
#   .\scripts\windows\install-ielts-watchdog.ps1

param(
    [string]$TaskName = "IELTS Stack Watchdog",
    [int]$IntervalMinutes = 10
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Watchdog = Join-Path $ProjectRoot "scripts\windows\watchdog-ielts-stack.ps1"
if (-not (Test-Path $Watchdog)) { throw "Watchdog script not found: $Watchdog" }
$HiddenLauncher = Join-Path $ProjectRoot "scripts\windows\run-watchdog-hidden.vbs"
if (-not (Test-Path $HiddenLauncher)) { throw "Hidden launcher not found: $HiddenLauncher" }

# Launch through wscript.exe + a VBS launcher so the periodic run never flashes a
# console window. powershell.exe as the action spawns a conhost window that blinks
# on screen every interval even with -WindowStyle Hidden; wscript has no console.
$argument = "`"$HiddenLauncher`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $argument

# Two triggers: once at logon, and a repeating one so a mid-session crash recovers.
$atLogon = New-ScheduledTaskTrigger -AtLogOn
$repeat = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

# DEFAULT run level (no -RunLevel Highest) keeps this installable without admin.
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($atLogon, $repeat) `
    -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed and started watchdog task: $TaskName (every $IntervalMinutes min, no admin)."
Write-Host "Log: $(Join-Path $ProjectRoot '.runlogs\watchdog.log')"
