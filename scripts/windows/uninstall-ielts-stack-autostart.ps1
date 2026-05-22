param(
    [string]$TaskName = "IELTS Stack Auto Start"
)

$ErrorActionPreference = "Stop"

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Removed scheduled task: $TaskName"
