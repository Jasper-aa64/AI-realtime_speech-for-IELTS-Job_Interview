# Run the IELTS AI worker as the interactive Windows user.
# This is needed for Claude Code CLI subscription auth, which does not work
# from LocalSystem even when token files are readable.

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$DjangoDir = Join-Path $ProjectRoot "backend_django"
$RunLogs = Join-Path $ProjectRoot ".runlogs"
$EnvFile = Join-Path $ProjectRoot ".env"
$StopFile = Join-Path ([System.IO.Path]::GetTempPath()) "ielts_worker_user.stop"
$ClaudeExe = Join-Path $env:APPDATA "npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
$CodexCmd = Join-Path $env:APPDATA "npm\codex.cmd"
$CodexHome = Join-Path $env:USERPROFILE ".codex"
$VenvPython = Join-Path $ProjectRoot ".venv-django\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $RunLogs | Out-Null
if (Test-Path $StopFile) {
    Remove-Item -LiteralPath $StopFile -Force
}

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
if (-not $env:CODEX_CLI_PATH -and (Test-Path $CodexCmd)) {
    $env:CODEX_CLI_PATH = $CodexCmd
}
if (-not $env:CODEX_HOME -and (Test-Path $CodexHome)) {
    $env:CODEX_HOME = $CodexHome
}

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $PythonCmd = Get-Command python -ErrorAction Stop
    $Python = $PythonCmd.Source
}

$LogPath = Join-Path $RunLogs "worker-user.log"
$ErrPath = Join-Path $RunLogs "worker-user.err.log"
Set-Location $DjangoDir

& $Python manage.py run_ai_worker `
    --worker-id "local-ai-worker-user" `
    --recover-stale-seconds 900 `
    --interval-seconds 1 `
    --idle-interval-seconds 2.5 `
    --stop-file "$StopFile" `
    1>> $LogPath 2>> $ErrPath
