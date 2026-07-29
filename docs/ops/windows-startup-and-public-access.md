# Windows Startup and Public Access

This note records the reliable ways to start the IELTS Studio stack on this Windows machine.

## What Must Be Running

The public URL is only a tunnel. The real app is local:

- Django ASGI backend on `http://127.0.0.1:8767/`
- AI worker for queued speaking/writing reports
- Optional public tunnel, such as `cloudflared` quick tunnel, Tailscale Funnel, or a named Cloudflare Tunnel

If `127.0.0.1:8767` is down, every public tunnel will eventually show `502 Bad Gateway`.

## Current Setup: NSSM Services + Cloudflare Quick Tunnel

Current deployed setup on this Windows machine:

- `ielts-django`: Daphne/Django on `127.0.0.1:8767`
- `ielts-cloudflared`: Cloudflare Quick Tunnel to `127.0.0.1:8767`, managed as
  an NSSM service and dependent on `ielts-django`
- `IELTS Studio Claude AI Worker`: AI worker scheduled task exists but stays
  stopped by default. Start it only when the user explicitly asks for queued AI
  worker processing. Its action must include `-WindowStyle Hidden`, so it must
  not open a visible terminal. The legacy `ielts-worker` LocalSystem service
  stays disabled.
- `IELTS Stack Watchdog`: currently disabled and not used. Do not start or
  enable it unless the user explicitly asks to restore watchdog operation.

The web and tunnel should be Windows services with `Running / Automatic`:

```powershell
Get-Service ielts-django, ielts-cloudflared
Get-ScheduledTask -TaskName "IELTS Studio Claude AI Worker"
Get-ScheduledTask -TaskName "IELTS Stack Watchdog"
```

Expected state: `ielts-django` and `ielts-cloudflared` are `Running`; the worker
task is `Ready`/stopped; the watchdog remains disabled. Only start the dedicated
AI worker task when queued AI work is intentionally in use and the user asked
for it. Do not enable the LocalSystem `ielts-worker` service: local Claude/Codex
CLI authentication belongs to the interactive Windows user.

The current public URL is a trycloudflare quick-tunnel URL. It can change when
`cloudflared` restarts. Use the helper below instead of copying the last URL
from the log, because the log can contain stale URLs that now return 530/1033:

```powershell
.\scripts\windows\get-tunnel-url.ps1
```

This quick-tunnel setup is intended to be stable during one boot/session while
the machine stays on. It is not a permanent fixed-domain deployment.

### Public URL Preservation Rule

The quick-tunnel URL should not change as a side effect of normal code changes.
A URL change is normal after the computer sleeps, the network changes, or
`ielts-cloudflared` actually restarts; it is not acceptable as a routine outcome
of editing CSS, JavaScript, Python, prompts, or tests.

Do this:

- Frontend/static edits: bump the `?v=` cache key and reload the browser. Do not
  restart `ielts-django` or `ielts-cloudflared`.
- Backend edits: first decide whether a Django reload is truly needed. If it is,
  preserve the tunnel process and tell the user before any service-level restart
  that can affect the public URL.
- Public URL lookup: run `.\scripts\windows\get-tunnel-url.ps1`; do not copy a
  random old URL from `.runlogs\cloudflared.log`.
- Tunnel recovery: restart `ielts-cloudflared` only when local `8767` is healthy
  and the tunnel itself is proven dead/stale, or when the user explicitly asks.

Do not do this:

- Do not restart `ielts-cloudflared` merely to apply code changes.
- Do not use `Restart-Service ielts-django -Force` for routine work. Because
  `ielts-cloudflared` depends on `ielts-django`, forceful Django service restarts
  can bounce the tunnel and create a new trycloudflare URL.
- Do not start `IELTS Stack Watchdog`, `IELTS Stack Auto Start`, or
  `IELTS Studio Claude AI Worker` as a default recovery step.

## Legacy Watchdog (currently disabled)

This is the way to keep the stack from "randomly dropping". A per-user Scheduled
Task starts daphne + the AI worker at logon and re-checks every 3 minutes, starting
either one **detached** if it is missing. It runs as the logged-in user (so P3's
Claude CLI auth keeps working) and needs **no administrator**.

The watchdog is not part of the current deployment. Keep it disabled. The
instructions below are retained only for a future explicit decision to restore
automatic recovery.

Install once (normal, non-elevated PowerShell):

```powershell
cd C:\Users\liangjunming\Desktop\AI_Project
.\scripts\windows\install-ielts-watchdog.ps1
```

Scripts:

- Watchdog logic: `scripts\windows\watchdog-ielts-stack.ps1` (idempotent; starts each
  piece only when missing, never duplicates, never blocks)
- Installer: `scripts\windows\install-ielts-watchdog.ps1`
- Task name: `IELTS Stack Watchdog`
- Log: `.runlogs\watchdog.log` (only writes when it actually has to recover something)

Why this and not `start-ielts-stack.ps1` for long-running use: that launcher ties
daphne+worker to one foreground PowerShell and **kills them in its `finally` when it
exits**, with no restart — so any hiccup in the launcher drops the whole stack. The
fragile `AtLogOn`-only "IELTS Stack Auto Start" task (which wrapped that launcher)
should stay **Disabled** when the watchdog is installed:

```powershell
Disable-ScheduledTask -TaskName "IELTS Stack Auto Start"
```

Verify recovery (optional): kill daphne, trigger the watchdog, confirm it comes back.

```powershell
Stop-Process -Name python -Force            # or just the daphne PID
Start-ScheduledTask -TaskName "IELTS Stack Watchdog"
Invoke-WebRequest http://127.0.0.1:8767/ -UseBasicParsing   # back to 200
```

## Quick Manual Start

This is a legacy/debug path, not the current public steady state. For daily
public access, prefer the NSSM services `ielts-django` + `ielts-cloudflared`
above. Do not use this launcher to keep the public site alive long-term.

From the project root:

```powershell
cd C:\Users\liangjunming\Desktop\AI_Project
.\scripts\windows\start-ielts-stack.ps1
```

This starts:

- Daphne/Django: `python -m daphne -b 127.0.0.1 -p 8767 config.asgi:application`
- AI worker: `python manage.py run_ai_worker`

Check locally:

```powershell
Invoke-WebRequest http://127.0.0.1:8767/ -UseBasicParsing
```

Expected result: HTTP `200`.

## Public Quick Tunnel

Only start this after local `8767` returns `200`:

```powershell
cloudflared tunnel --url http://127.0.0.1:8767
```

Important: `trycloudflare.com` quick tunnel URLs are temporary. They can change or die when the process exits, the computer sleeps, or the network changes.

## NSSM Windows Services

The "NXXX" thing was **NSSM**: Non-Sucking Service Manager. It wraps commands as Windows services and can auto-restart them.

Existing scripts:

- Install services: `scripts\windows\install-services.ps1`
- Uninstall services: `scripts\windows\uninstall-services.ps1`
- Django service wrapper: `scripts\windows\run-django.bat`
- Worker service wrapper: `scripts\windows\run-worker.bat`

Install once from an Administrator PowerShell:

```powershell
cd C:\Users\liangjunming\Desktop\AI_Project
.\scripts\windows\install-services.ps1
```

Service names:

- `ielts-django`
- `ielts-cloudflared`
- `ielts-worker` (legacy LocalSystem worker; keep disabled)

Useful commands:

```powershell
Get-Service ielts-django, ielts-cloudflared, ielts-worker
Start-Service ielts-django
Start-Service ielts-cloudflared
.\scripts\windows\get-tunnel-url.ps1
```

Avoid routine `Restart-Service`/`Stop-Service` commands here. In the current
setup `ielts-cloudflared` depends on `ielts-django`; forceful restarts can churn
the quick-tunnel URL. The legacy `ielts-worker` service should remain disabled.

Logs:

- `.runlogs\django.log`
- `.runlogs\django.err.log`
- `.runlogs\worker.log`
- `.runlogs\worker.err.log`

NSSM path currently hardcoded in the installer:

```text
C:\Users\liangjunming\tools\nssm-2.24\win64\nssm.exe
```

## Interactive User Scheduled Tasks

Use this route when AI calls need the currently logged-in user account, especially Claude/Codex-style CLI auth. LocalSystem services may not see the same auth files.

Existing scripts:

- Install Django user task: `scripts\windows\install-django-user-task.ps1`
- Install AI worker user task: `scripts\windows\install-claude-worker-task.ps1`
- Runtime Django script: `scripts\windows\run-django-user.ps1`
- Runtime worker script: `scripts\windows\run-ai-worker-user.ps1`
- Simple stack-at-logon task: `scripts\windows\install-ielts-stack-autostart.ps1`
- Remove simple stack-at-logon task: `scripts\windows\uninstall-ielts-stack-autostart.ps1`

Install from an Administrator PowerShell:

```powershell
cd C:\Users\liangjunming\Desktop\AI_Project
.\scripts\windows\install-django-user-task.ps1
.\scripts\windows\install-claude-worker-task.ps1
```

Task names:

- `IELTS Studio Django (User)`
- `IELTS Studio Claude AI Worker`

Logs:

- `.runlogs\django-user.log`
- `.runlogs\django-user.err.log`
- `.runlogs\worker-user.log`
- `.runlogs\worker-user.err.log`

## Tunnel URL Helper

Existing helper:

```powershell
.\scripts\windows\get-tunnel-url.ps1
```

Note: this helper expects a cloudflared log file. If the tunnel is started manually without redirecting logs, it may not find the URL.

## Recommended Stable Setup

For daily development:

1. Keep `ielts-django` and `ielts-cloudflared` running as NSSM services.
2. Use `.\scripts\windows\get-tunnel-url.ps1` to report the active public URL.
3. For frontend/static changes, bump cache keys and reload; do not restart either
   service.

For "do not drop" local availability:

1. Keep the NSSM Django + cloudflared services healthy.
2. Start the interactive-user AI worker task only when the user explicitly asks
   for queued AI worker processing.
3. Use Tailscale Funnel or Cloudflare Named Tunnel only if a truly fixed public
   address is required.

Avoid relying on a random `trycloudflare.com` quick tunnel for long-term stable access.

## 502 Checklist

When the public URL shows `Bad gateway Error code 502`:

1. Check local Django:

   ```powershell
   Invoke-WebRequest http://127.0.0.1:8767/ -UseBasicParsing
   ```

2. If local fails, inspect Django first:

   ```powershell
   Get-Service ielts-django, ielts-cloudflared
   Get-Content .runlogs\django.err.log -Tail 80
   ```

   If a Django service restart is truly needed, warn that it may affect the
   dependent quick tunnel. Do not use `Restart-Service ielts-django -Force` as a
   routine fix.

3. If local succeeds but public still fails, first print the active tunnel URL:

   ```powershell
   .\scripts\windows\get-tunnel-url.ps1
   ```

   Restart `ielts-cloudflared` only if the tunnel process is unhealthy or the
   user explicitly accepts a URL change.

4. Check logs:

   ```powershell
   Get-Content .runlogs\django.err.log -Tail 80
   Get-Content .runlogs\cloudflared.log -Tail 80
   ```

## Report Stuck On `Analyzing`

`Analyzing the full section and generating the report` means the browser has
already queued an `AITask` and is polling it. If it remains there for several
minutes, distinguish a dead worker from a slow provider before restarting
anything:

```powershell
Get-ScheduledTask -TaskName "IELTS Studio Claude AI Worker"
Get-ScheduledTaskInfo -TaskName "IELTS Studio Claude AI Worker"
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "python.exe" -and $_.CommandLine -match "run_ai_worker"
}
```

- Task `Ready` plus no `run_ai_worker` process: the worker is down. Do not start
  it automatically; tell the user the worker is stopped and start the hidden
  worker task only if the user explicitly asks.
- Task `Running` plus a worker process: the AI provider is still executing. Do
  not repeatedly submit the same report.
- `LastTaskResult = 0xC000013A`: the interactive worker was externally
  interrupted (Ctrl+C or terminal close), not cleanly completed.

If the user explicitly asks to run the worker, use the hidden scheduled task:

```powershell
Start-ScheduledTask -TaskName "IELTS Studio Claude AI Worker"
```

The browser polls the original task ID, so once the worker claims a pending
task the existing `Analyzing` page proceeds to the report without a new attempt.

### 2026-06-19 Incident Summary

A P1 report stayed at `Analyzing` because its task was still `pending` with
`attempt_count=0` and no `worker_id`. Django and Cloudflare were healthy, but
the interactive-user worker had stopped with `0xC000013A`; the watchdog was
disabled, so nothing restarted it. The task was safely re-queued, the worker
completed it (`succeeded`, 100%), the worker action was changed to hidden mode,
and later deployment policy changed again: the watchdog and worker now stay
stopped unless the user explicitly asks for them.
