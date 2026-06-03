# IELTS stack launcher for Windows (daphne ASGI + AI worker)
# Requires: .env in project root, Python 3.13 in system PATH or .venv-django
# Usage: .\scripts\windows\start-ielts-stack.ps1

param(
    [string]$EnvFile = ".env",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8767
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

# --- Load .env ---
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | Where-Object { $_ -match "^\s*[^#]" -and $_ -match "=" } | ForEach-Object {
        $parts = $_ -split "=", 2
        $key   = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
    Write-Host "[ielts] Loaded $EnvFile"
} else {
    Write-Warning "[ielts] $EnvFile not found. Copy .env.example to .env and fill in real keys."
}

# --- Resolve Python (venv preferred, system fallback) ---
$VenvPython = Join-Path $ProjectRoot ".venv-django\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    $Python = if ($PythonCmd) { $PythonCmd.Source } else { $null }
}
if (-not $Python) { throw "[ielts] Python not found. Create .venv-django or add python to PATH." }
Write-Host "[ielts] Python: $Python"

# --- Ensure runlogs dir ---
$RunLogs = Join-Path $ProjectRoot ".runlogs"
New-Item -ItemType Directory -Force -Path $RunLogs | Out-Null

# --- Stop-file for worker graceful shutdown ---
$StopFile = Join-Path ([System.IO.Path]::GetTempPath()) "ielts_worker_$(Get-Date -Format 'yyyyMMddHHmmss').stop"
if (Test-Path $StopFile) { Remove-Item $StopFile }

# --- Launch daphne (ASGI, supports WebSocket/Channels) ---
Write-Host "[ielts] Starting daphne on ${BindHost}:${Port} ..."
$DjangoLog = Join-Path $RunLogs "django.log"
$DjangoProc = Start-Process -FilePath $Python -ArgumentList @(
    "-m", "daphne",
    "-b", $BindHost,
    "-p", $Port,
    "config.asgi:application"
) -WorkingDirectory (Join-Path $ProjectRoot "backend_django") `
  -PassThru -NoNewWindow `
  -RedirectStandardOutput $DjangoLog -RedirectStandardError $DjangoLog

# --- Launch AI worker ---
Write-Host "[ielts] Starting AI worker ..."
$WorkerLog = Join-Path $RunLogs "worker.log"
$WorkerProc = Start-Process -FilePath $Python -ArgumentList @(
    "manage.py", "run_ai_worker",
    "--stop-file", $StopFile
) -WorkingDirectory (Join-Path $ProjectRoot "backend_django") `
  -PassThru -NoNewWindow `
  -RedirectStandardOutput $WorkerLog -RedirectStandardError $WorkerLog

Write-Host "[ielts] Stack running."
Write-Host "  Django  PID=$($DjangoProc.Id)  log=$DjangoLog"
Write-Host "  Worker  PID=$($WorkerProc.Id)  log=$WorkerLog"
Write-Host "  Local:  http://${BindHost}:${Port}"
Write-Host "  Tailscale: https://psi-linagjm.tail46b1c.ts.net"
Write-Host "[ielts] Press Ctrl+C to stop."

try {
    Wait-Process -Id $DjangoProc.Id
} finally {
    New-Item -ItemType File -Path $StopFile -Force | Out-Null
    Start-Sleep -Seconds 2
    @($DjangoProc, $WorkerProc) | Where-Object { -not $_.HasExited } | ForEach-Object {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[ielts] Stack stopped."
}
