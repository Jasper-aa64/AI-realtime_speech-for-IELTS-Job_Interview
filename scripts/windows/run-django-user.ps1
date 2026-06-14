# Run IELTS Django as the interactive Windows user.
# Claude Code CLI auth is bound to the logged-in user, so sync API calls
# such as /api/p3/questions must not run from LocalSystem.

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$DjangoDir = Join-Path $ProjectRoot "backend_django"
$RunLogs = Join-Path $ProjectRoot ".runlogs"
$EnvFile = Join-Path $ProjectRoot ".env"
$ClaudeExe = Join-Path $env:APPDATA "npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
$VenvPython = Join-Path $ProjectRoot ".venv-django\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $RunLogs | Out-Null

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

$env:PYTHONUNBUFFERED = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:AI_PROVIDER_ENABLE_CLAUDE = "1"
$env:AI_DEFAULT_PROVIDER = "claude"
$env:CLAUDE_CLI_MODEL = if ($env:CLAUDE_CLI_MODEL) { $env:CLAUDE_CLI_MODEL } else { "sonnet" }
if (-not $env:CLAUDE_CLI_PATH -and (Test-Path $ClaudeExe)) {
    $env:CLAUDE_CLI_PATH = $ClaudeExe
}

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $PythonCmd = Get-Command python -ErrorAction Stop
    $Python = $PythonCmd.Source
}

$LogPath = Join-Path $RunLogs "django-user.log"
$ErrPath = Join-Path $RunLogs "django-user.err.log"
Set-Location $DjangoDir

try {
    $listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        exit 0
    }
} catch {
    # Older PowerShell/network stacks may not expose Get-NetTCPConnection.
}

$Arguments = "-m daphne -b 127.0.0.1 -p 8767 config.asgi:application"
Start-Process `
    -FilePath $Python `
    -ArgumentList $Arguments `
    -WorkingDirectory $DjangoDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $LogPath `
    -RedirectStandardError $ErrPath

