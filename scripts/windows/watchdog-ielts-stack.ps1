# IELTS stack watchdog.
#
# Keeps the LOCAL backend alive so the public tunnel never 502s:
#   - daphne ASGI on 127.0.0.1:8767
#   - the AI worker (queued speaking/writing reports)
#
# Idempotent and safe to run on a schedule (every few minutes): it starts each
# piece DETACHED only when that piece is actually missing, so it never spawns
# duplicates and never blocks. Runs as the interactive user, so P3's Claude CLI
# auth keeps working. No administrator required.
#
# This is the auto-recovery net the old "IELTS Stack Auto Start" task lacked:
# start-ielts-stack.ps1 ties daphne+worker to one foreground launcher and kills
# them when it exits, with no restart. The watchdog brings them back within one
# interval regardless of how they died.

$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Scripts = Join-Path $ProjectRoot "scripts\windows"
$RunLogs = Join-Path $ProjectRoot ".runlogs"
New-Item -ItemType Directory -Force -Path $RunLogs | Out-Null
$Log = Join-Path $RunLogs "watchdog.log"

function Write-WatchdogLog($msg) {
    Add-Content -LiteralPath $Log -Value ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}

# Launch a runtime script in its OWN detached, hidden PowerShell so the started
# process (daphne / the blocking worker) outlives this watchdog run and an `exit`
# inside the runtime script cannot terminate the watchdog.
function Start-Detached($scriptName) {
    Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
        "-File", (Join-Path $Scripts $scriptName)
    )
}

# 1) Daphne on 127.0.0.1:8767
$listener = $null
try {
    $listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue
} catch {
    # Older network stacks may not expose Get-NetTCPConnection; fall through and let
    # run-django-user.ps1 do its own listener check before starting.
}
if (-not $listener) {
    Write-WatchdogLog "daphne 8767 down -> launching run-django-user.ps1"
    Start-Detached "run-django-user.ps1"
}

# 2) AI worker (any variant: the user task's --worker-id or the bare manage.py run)
$worker = $null
try {
    $worker = Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'run_ai_worker' }
} catch {}
if (-not $worker) {
    Write-WatchdogLog "ai worker down -> launching run-ai-worker-user.ps1"
    Start-Detached "run-ai-worker-user.ps1"
}
