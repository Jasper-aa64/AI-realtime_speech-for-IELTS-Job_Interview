param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\liangjunming\Desktop\AI_Project"
$PromptPath = Join-Path $ProjectRoot "scripts\windows\claude-scheduled-refactor-prompt.md"
$RunLogs = Join-Path $ProjectRoot ".runlogs"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogPath = Join-Path $RunLogs "claude-scheduled-refactor-$Timestamp.log"
$ClaudeCmd = "C:\Users\liangjunming\AppData\Roaming\npm\claude.cmd"

New-Item -ItemType Directory -Force -Path $RunLogs | Out-Null

if (-not (Test-Path $PromptPath)) {
    throw "Prompt file not found: $PromptPath"
}

if (-not (Test-Path $ClaudeCmd)) {
    $found = Get-Command claude.cmd -ErrorAction SilentlyContinue
    if ($found) {
        $ClaudeCmd = $found.Source
    } else {
        throw "claude.cmd not found."
    }
}

$Prompt = Get-Content -Raw -Encoding UTF8 $PromptPath
$Args = @(
    "--model", "opus",
    "--permission-mode", "bypassPermissions",
    "-p", $Prompt
)

Set-Location $ProjectRoot

if ($DryRun) {
    "DRY RUN ONLY" | Tee-Object -FilePath $LogPath
    "ProjectRoot=$ProjectRoot" | Tee-Object -FilePath $LogPath -Append
    "ClaudeCmd=$ClaudeCmd" | Tee-Object -FilePath $LogPath -Append
    "PromptPath=$PromptPath" | Tee-Object -FilePath $LogPath -Append
    "Scheduled command: claude --model opus --permission-mode bypassPermissions -p <prompt>" | Tee-Object -FilePath $LogPath -Append
    exit 0
}

"Starting Claude scheduled refactor at $(Get-Date -Format o)" | Tee-Object -FilePath $LogPath
"ProjectRoot=$ProjectRoot" | Tee-Object -FilePath $LogPath -Append
"PromptPath=$PromptPath" | Tee-Object -FilePath $LogPath -Append

& $ClaudeCmd @Args *>> $LogPath
$ExitCode = $LASTEXITCODE
"Claude exited with code $ExitCode at $(Get-Date -Format o)" | Tee-Object -FilePath $LogPath -Append
exit $ExitCode

