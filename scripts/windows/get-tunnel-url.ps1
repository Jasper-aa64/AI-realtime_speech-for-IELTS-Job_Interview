# Print the currently usable Cloudflare Quick Tunnel URL.
# The log can contain stale quick-tunnel URLs after restarts, so this script
# checks recent candidates and returns the newest one that actually responds.

param(
    [int]$RecentCandidates = 12,
    [int]$TimeoutSeconds = 8
)

$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogPath = Join-Path $ProjectRoot ".runlogs\cloudflared.log"

if (-not (Test-Path $LogPath)) {
    Write-Host "cloudflared log not found: $LogPath" -ForegroundColor Red
    exit 1
}

$urls = Select-String -Path $LogPath -Pattern "https://[^\s|]+\.trycloudflare\.com" |
    ForEach-Object { $_.Matches[0].Value.Trim() } |
    Select-Object -Unique |
    Select-Object -Last $RecentCandidates

if (-not $urls) {
    Write-Host "No trycloudflare URL found in $LogPath" -ForegroundColor Yellow
    exit 1
}

$candidates = @($urls)
[array]::Reverse($candidates)

foreach ($url in $candidates) {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $TimeoutSeconds
        if ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 400) {
            Write-Host "Current usable Cloudflare Quick Tunnel URL:" -ForegroundColor Cyan
            Write-Host $url -ForegroundColor Green
            exit 0
        }
    } catch {
        # Stale quick tunnel URLs often return 530/1033. Keep scanning older candidates.
    }
}

Write-Host "No recent trycloudflare URL responded successfully." -ForegroundColor Red
Write-Host "Check local service: Invoke-WebRequest http://127.0.0.1:8767/ -UseBasicParsing"
Write-Host "Check cloudflared service: Get-Service ielts-cloudflared"
exit 2
