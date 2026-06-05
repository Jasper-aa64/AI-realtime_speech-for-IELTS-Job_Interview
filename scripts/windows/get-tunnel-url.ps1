# 读取当前 cloudflared 隧道 URL
$log = "$PSScriptRoot\..\..\runlogs\cloudflared.log"
$log = (Resolve-Path $log -ErrorAction SilentlyContinue)?.Path
if (-not $log -or -not (Test-Path $log)) {
  Write-Host "日志文件不存在，ielts-tunnel 服务是否在运行？" -ForegroundColor Red
  exit 1
}
$url = (Select-String -Path $log -Pattern "https://.*\.trycloudflare\.com" | Select-Object -Last 1)?.Matches[0].Value
if ($url) {
  Write-Host "当前隧道 URL：" -ForegroundColor Cyan
  Write-Host $url -ForegroundColor Green
} else {
  Write-Host "未找到 URL，请稍等几秒后重试（服务可能刚启动）" -ForegroundColor Yellow
}
