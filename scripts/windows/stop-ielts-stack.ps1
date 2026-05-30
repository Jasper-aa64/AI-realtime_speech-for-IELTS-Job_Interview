[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$RepoRoot
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $RepoRoot = (Resolve-Path (Join-Path $scriptRoot "..\..")).Path
}

$repoPattern = [regex]::Escape($RepoRoot)
$targets = Get-CimInstance Win32_Process | Where-Object {
    # Stop the current Django runtime and any stale retired legacy server process
    # that may have been started before the retirement guard was introduced.
    ($_.Name -eq "python.exe" -and $_.CommandLine -match $repoPattern -and ($_.CommandLine -match "web\\ielts_server\.py" -or $_.CommandLine -match "backend_django\\manage\.py")) -or
    ($_.Name -eq "cloudflared.exe" -and $_.CommandLine -match "127\.0\.0\.1:")
}

foreach ($target in $targets) {
    if ($PSCmdlet.ShouldProcess("$($target.Name) pid=$($target.ProcessId)", "Stop IELTS stack process")) {
        Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped $($target.Name) pid=$($target.ProcessId)"
    }
}

if (-not $targets) {
    Write-Host "No IELTS stack processes were running."
}
