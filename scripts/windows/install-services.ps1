# Install IELTS Django + AI worker as Windows services via NSSM.
# Run ONCE in an elevated (Administrator) PowerShell.
# Usage: .\scripts\windows\install-services.ps1

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

# --- Config ---
$NssmExe     = "C:\Users\liangjunming\tools\nssm-2.24\win64\nssm.exe"
$VenvPython  = Join-Path $ProjectRoot ".venv-django\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    $Python = if ($PythonCmd) { $PythonCmd.Source } else { $null }
}
if (-not $Python) { throw "Python not found." }
if (-not (Test-Path $NssmExe)) { throw "NSSM not found at $NssmExe" }

$DjangoDir   = Join-Path $ProjectRoot "backend_django"
$RunLogs     = Join-Path $ProjectRoot ".runlogs"
$EnvFile     = Join-Path $ProjectRoot ".env"
$StopFile    = Join-Path ([System.IO.Path]::GetTempPath()) "ielts_worker.stop"

New-Item -ItemType Directory -Force -Path $RunLogs | Out-Null

# --- Build env block from .env ---
$EnvBlock = ""
if (Test-Path $EnvFile) {
    $pairs = Get-Content $EnvFile |
        Where-Object { $_ -match "^\s*[^#]" -and $_ -match "=" } |
        ForEach-Object { $_.Trim() }
    $EnvBlock = $pairs -join "`n"
}

function Install-IeltsService {
    param(
        [string]$Name,
        [string]$DisplayName,
        [string]$Args,
        [string]$OutLog,
        [string]$ErrLog
    )

    Write-Host "Installing service: $Name ..."
    try { & $NssmExe remove $Name confirm 2>&1 | Out-Null } catch {}

    & $NssmExe install        $Name $Python
    & $NssmExe set            $Name AppParameters    $Args
    & $NssmExe set            $Name AppDirectory      $DjangoDir
    & $NssmExe set            $Name DisplayName       $DisplayName
    & $NssmExe set            $Name Description       "IELTS studio — $DisplayName"
    # Run under LocalSystem by default. Do not bind to ".\$env:USERNAME":
    # Microsoft-account or renamed local profiles can fail SID lookup and break
    # NSSM's "Log on as a service" grant.
    & $NssmExe set            $Name ObjectName        LocalSystem
    & $NssmExe set            $Name Start             SERVICE_AUTO_START
    & $NssmExe set            $Name AppStdout         $OutLog
    & $NssmExe set            $Name AppStderr         $ErrLog
    & $NssmExe set            $Name AppStdoutCreationDisposition 4   # append
    & $NssmExe set            $Name AppStderrCreationDisposition 4
    & $NssmExe set            $Name AppRotateFiles     1
    & $NssmExe set            $Name AppRotateBytes     5242880         # 5 MB
    & $NssmExe set            $Name AppExit            Default Restart
    & $NssmExe set            $Name AppRestartDelay    3000            # 3 s

    if ($EnvBlock) {
        & $NssmExe set        $Name AppEnvironmentExtra $EnvBlock
    }

    Write-Host "  => $Name installed."
}

# --- Django (daphne ASGI) ---
Install-IeltsService `
    -Name        "ielts-django" `
    -DisplayName "IELTS Studio Django (daphne)" `
    -Args        "-m daphne -b 127.0.0.1 -p 8767 config.asgi:application" `
    -OutLog      (Join-Path $RunLogs "django.log") `
    -ErrLog      (Join-Path $RunLogs "django.err.log")

# --- AI worker ---
Install-IeltsService `
    -Name        "ielts-worker" `
    -DisplayName "IELTS Studio AI Worker" `
    -Args        "manage.py run_ai_worker --stop-file `"$StopFile`"" `
    -OutLog      (Join-Path $RunLogs "worker.log") `
    -ErrLog      (Join-Path $RunLogs "worker.err.log")

# --- Start both ---
Write-Host "Starting services ..."
Start-Service ielts-django
Start-Sleep -Seconds 3
Start-Service ielts-worker

Write-Host ""
Write-Host "Done. Services installed and started."
Write-Host "  Check status: Get-Service ielts-django, ielts-worker"
Write-Host "  Logs: $RunLogs"
Write-Host "  Uninstall: .\scripts\windows\uninstall-services.ps1"
