param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [int]$DjangoPort = $(if ($env:IELTS_DJANGO_PORT) { [int]$env:IELTS_DJANGO_PORT } else { 8000 })
)

$ErrorActionPreference = "Stop"

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port
    )

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(250)) {
            $client.Close()
            return $false
        }
        $client.EndConnect($async)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

function Resolve-Python {
    foreach ($candidate in @("python.exe", "py.exe")) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw "Unable to find python.exe or py.exe on PATH."
}

function Resolve-Cloudflared {
    $command = Get-Command "cloudflared.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $known = Join-Path $env:LOCALAPPDATA "npm-cache\_npx"
    if (Test-Path $known) {
        $found = Get-ChildItem $known -Recurse -Filter "cloudflared.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            return $found.FullName
        }
    }

    throw "Unable to locate cloudflared.exe."
}

function Start-DetachedProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$LogStem
    )

    $runlogs = Join-Path $RepoRoot ".runlogs"
    New-Item -ItemType Directory -Force -Path $runlogs | Out-Null
    $stdout = Join-Path $runlogs "$LogStem.out.log"
    $stderr = Join-Path $runlogs "$LogStem.err.log"

    Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr | Out-Null
}

function Write-StackStatus {
    param(
        [string]$Mode,
        [string]$PublicUrl
    )

    $runlogs = Join-Path $RepoRoot ".runlogs"
    New-Item -ItemType Directory -Force -Path $runlogs | Out-Null

    $statusPath = Join-Path $runlogs "stack-status.json"
    $urlPath = Join-Path $runlogs "public-url.txt"
    $status = [ordered]@{
        updated_at = (Get-Date).ToString("s")
        app = "http://127.0.0.1:$DjangoPort"
        django = "http://127.0.0.1:$DjangoPort"
        tunnel_mode = $Mode
        public_url = $PublicUrl
    }

    $status | ConvertTo-Json | Set-Content -Path $statusPath -Encoding UTF8
    if ($PublicUrl) {
        Set-Content -Path $urlPath -Value $PublicUrl -Encoding UTF8
    }
}

function Get-QuickTunnelUrl {
    $logPath = Join-Path $RepoRoot ".runlogs\cloudflared.err.log"
    if (-not (Test-Path $logPath)) {
        return $null
    }

    $match = Select-String -Path $logPath -Pattern 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' | Select-Object -Last 1
    if ($match) {
        return $match.Matches[0].Value
    }

    return $null
}

function Get-NamedTunnelName {
    $envName = $env:IELTS_CLOUDFLARED_TUNNEL_NAME
    if ($envName) {
        return $envName.Trim()
    }

    $configPath = if ($env:IELTS_CLOUDFLARED_CONFIG) {
        $env:IELTS_CLOUDFLARED_CONFIG
    } else {
        Join-Path $env:USERPROFILE ".cloudflared\config.yml"
    }

    if (Test-Path $configPath) {
        $match = Select-String -Path $configPath -Pattern '^\s*tunnel:\s*([^\s#]+)\s*$' | Select-Object -First 1
        if ($match) {
            return $match.Matches[0].Groups[1].Value.Trim()
        }
    }

    return $null
}

$python = Resolve-Python
$cloudflared = Resolve-Cloudflared
$managePy = Join-Path $RepoRoot "backend_django\manage.py"

if (-not (Test-TcpPort -HostName "127.0.0.1" -Port $DjangoPort)) {
    Start-DetachedProcess `
        -FilePath $python `
        -ArgumentList @($managePy, "runserver", "127.0.0.1:$DjangoPort") `
        -WorkingDirectory $RepoRoot `
        -LogStem "django"
}

Start-Sleep -Seconds 2

$tunnelName = Get-NamedTunnelName
if (-not (Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue)) {
    if ($tunnelName) {
        Start-DetachedProcess `
            -FilePath $cloudflared `
            -ArgumentList @("tunnel", "run", $tunnelName) `
            -WorkingDirectory $RepoRoot `
            -LogStem "cloudflared"
    } else {
        Start-DetachedProcess `
            -FilePath $cloudflared `
            -ArgumentList @("tunnel", "--url", "http://127.0.0.1:$DjangoPort", "--no-autoupdate") `
            -WorkingDirectory $RepoRoot `
            -LogStem "cloudflared"
    }
}

$publicUrl = $env:IELTS_PUBLIC_URL
if (-not $publicUrl -and -not $tunnelName) {
    for ($i = 0; $i -lt 20; $i += 1) {
        $publicUrl = Get-QuickTunnelUrl
        if ($publicUrl) {
            break
        }
        Start-Sleep -Seconds 1
    }
}

Write-Host "IELTS stack launch requested."
Write-Host "App: http://127.0.0.1:$DjangoPort"
Write-Host "Django: http://127.0.0.1:$DjangoPort"
if ($tunnelName) {
    Write-Host "Tunnel mode: named tunnel '$tunnelName' (stable URL if DNS is already routed)."
    if ($publicUrl) {
        Write-Host "Public URL: $publicUrl"
    } else {
        Write-Host "Public URL: set IELTS_PUBLIC_URL to record the routed hostname in .runlogs."
    }
    Write-StackStatus -Mode "named" -PublicUrl $publicUrl
} else {
    Write-Host "Tunnel mode: quick tunnel (URL changes on restart unless you switch to a named tunnel)."
    if ($publicUrl) {
        Write-Host "Public URL: $publicUrl"
    }
    Write-StackStatus -Mode "quick" -PublicUrl $publicUrl
}
