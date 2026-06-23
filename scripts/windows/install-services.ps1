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

# cloudflared, for the public-access quick-tunnel service. Optional: if it is not
# found we still install the Django + worker services and just skip the tunnel.
$CloudflaredExe = $null
foreach ($cf in @(
    "C:\Program Files (x86)\cloudflared\cloudflared.exe",
    "C:\Program Files\cloudflared\cloudflared.exe"
)) { if (Test-Path $cf) { $CloudflaredExe = $cf; break } }
if (-not $CloudflaredExe) {
    $cfCmd = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
    if ($cfCmd) { $CloudflaredExe = $cfCmd.Source }
}

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
        [string]$AppArgs,
        [string]$OutLog,
        [string]$ErrLog,
        [string]$Exe = $Python
    )

    Write-Host "Installing service: $Name ..."
    try { & $NssmExe remove $Name confirm 2>&1 | Out-Null } catch {}

    & $NssmExe install        $Name $Exe
    # NOTE: the parameter is named $AppArgs, NOT $Args — $Args collides with the
    # PowerShell automatic $args variable and silently passes an EMPTY value, which
    # leaves AppParameters blank and makes NSSM launch a bare interpreter (python
    # then drops into the 3.13 REPL and dies with WinError 123 under a service).
    & $NssmExe set            $Name AppParameters    $AppArgs
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
    -AppArgs     "-m daphne -b 127.0.0.1 -p 8767 config.asgi:application" `
    -OutLog      (Join-Path $RunLogs "django.log") `
    -ErrLog      (Join-Path $RunLogs "django.err.log")

# --- AI worker ---
Install-IeltsService `
    -Name        "ielts-worker" `
    -DisplayName "IELTS Studio AI Worker" `
    -AppArgs     "manage.py run_ai_worker --stop-file `"$StopFile`"" `
    -OutLog      (Join-Path $RunLogs "worker.log") `
    -ErrLog      (Join-Path $RunLogs "worker.err.log")

# --- Cloudflare quick tunnel (public access) ---
# A Windows service is the durable, no-terminal-flashing way to keep the quick
# tunnel alive: NSSM auto-restarts it on crash and starts it at boot. The public
# URL is a random trycloudflare address that CHANGES whenever cloudflared restarts
# (see .runlogs/cloudflared.log for the current one); ALLOWED_HOSTS already has the
# .trycloudflare.com wildcard, so a changed URL still serves and logs in.
if ($CloudflaredExe) {
    Install-IeltsService `
        -Name        "ielts-cloudflared" `
        -DisplayName "IELTS Studio Cloudflare Quick Tunnel" `
        -AppArgs     "tunnel --url http://127.0.0.1:8767 --no-autoupdate --logfile `"$(Join-Path $RunLogs 'cloudflared.log')`"" `
        -OutLog      (Join-Path $RunLogs "cloudflared.svc.log") `
        -ErrLog      (Join-Path $RunLogs "cloudflared.svc.err.log") `
        -Exe         $CloudflaredExe
    & $NssmExe set ielts-cloudflared DependOnService ielts-django | Out-Null
} else {
    Write-Warning "cloudflared.exe not found - skipping ielts-cloudflared service."
}

# --- Start all ---
Write-Host "Starting services ..."
Start-Service ielts-django
Start-Sleep -Seconds 3
Start-Service ielts-worker
if ($CloudflaredExe) { Start-Sleep -Seconds 2; Start-Service ielts-cloudflared }

Write-Host ""
Write-Host "Done. Services installed and started."
Write-Host "  Check status: Get-Service ielts-django, ielts-worker"
Write-Host "  Logs: $RunLogs"
Write-Host "  Uninstall: .\scripts\windows\uninstall-services.ps1"
