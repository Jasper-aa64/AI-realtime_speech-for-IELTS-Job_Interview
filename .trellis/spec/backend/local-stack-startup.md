# Local Stack Startup Spec

> Executable startup contract for the local IELTS Studio stack. Use this before
> debugging UI issues: first prove Django and the AI worker are actually alive.

---

## Scenario: Start and Verify the Local Django + AI Worker Stack

### 1. Scope / Trigger

- Trigger: Local demos, browser QA, public tunnel QA, writing-score checks, and
  speaking follow-up checks need both Django and `run_ai_worker`.
- Scope: `scripts/start-local-stack.sh`, `backend_django/manage.py runserver`,
  `backend_django/manage.py run_ai_worker`, `.runlogs/`, port `8767`, and local
  HTTP checks.
- Reason: `scripts/start-local-stack.sh` can print "IELTS stack requested" even
  when no process remains listening. A stale `.runlogs/stack-status.json` is an
  advertised target, not a liveness proof.

### Windows Production-Like Override

On the user's Windows machine, the steady-state public stack is not the generic
local helper:

- `ielts-django`: NSSM service serving Daphne/Django on `127.0.0.1:8767`.
- `ielts-cloudflared`: NSSM service running a Cloudflare quick tunnel to
  `127.0.0.1:8767`; it depends on `ielts-django`.
- `IELTS Studio Claude AI Worker`: scheduled task that stays stopped unless the
  user explicitly asks for queued AI worker processing.
- `ielts-worker`: legacy LocalSystem service; keep disabled.

Public URL preservation is part of the contract. A trycloudflare URL may change
after sleep, network changes, or a real tunnel restart, but ordinary code edits
must not churn it. Frontend/static work uses cache-buster updates and browser
reload only. Backend work may reload Django only when needed, and must not
restart `ielts-cloudflared` just to apply code. Avoid
`Restart-Service ielts-django -Force`: because `ielts-cloudflared` depends on
`ielts-django`, forceful Django restarts can bounce the tunnel and create a new
public URL.

### 2. Signatures

Preferred local startup:

```bash
scripts/start-local-stack.sh
```

Manual Django fallback when the helper does not leave a listener:

```bash
.venv-django/bin/python backend_django/manage.py runserver 127.0.0.1:8767 --noreload
```

Manual AI worker fallback:

```bash
rm -f /tmp/ielts-ai-worker.stop
.venv-django/bin/python backend_django/manage.py run_ai_worker \
  --interval-seconds 2 \
  --idle-interval-seconds 5 \
  --stop-file /tmp/ielts-ai-worker.stop
```

Persistent macOS LaunchAgent fallback when shell-launched background processes
keep disappearing:

```bash
launchctl print gui/$(id -u)/com.ielts.local.django
launchctl print gui/$(id -u)/com.ielts.local.aiworker
```

Public tunnel startup:

```bash
IELTS_PUBLIC=1 scripts/start-local-stack.sh
```

Windows public URL lookup:

```powershell
.\scripts\windows\get-tunnel-url.ps1
```

### 3. Contracts

- Local app URL: `http://127.0.0.1:8767/`.
- Django must listen on `127.0.0.1:8767` before saying the site is usable.
- On Windows, `ielts-cloudflared` must stay running across routine edits. Do not
  restart it unless local `8767` is healthy and the tunnel itself is proven
  broken/stale, or the user explicitly accepts a tunnel restart.
- AI worker must have exactly one live `run_ai_worker` process for normal local
  operation. Multiple workers can race on AI tasks and make debugging
  nondeterministic.
- On Windows, the AI worker is not part of the always-on stack. Do not start
  `IELTS Studio Claude AI Worker`, `IELTS Stack Watchdog`, `IELTS Stack Auto
  Start`, or LocalSystem `ielts-worker` without an explicit user request.
- Use `.venv-django/bin/python` when it exists. Do not assume plain `python3`
  has the same dependencies.
- The worker and Django must share the same AI environment:
  - `AI_HTTP_BASE_URL`
  - `AI_HTTP_API_KEY`
  - `AI_HTTP_MODEL`
  - `AI_HTTP_TIMEOUT_SECONDS`
  - `SPEAKING_AI_CALL_MODE`
  - `SPEAKING_AI_MODEL`
  - `VOLCENGINE_ASR_ENABLED`
  - `VOLCENGINE_ASR_FFMPEG`
- `speaking_report` AI tasks must keep the worker adapter provider as `codex`.
  Do not create queued speaking-report tasks with `provider=http` or
  `provider=claude`: the async worker dispatches this task type through the
  speaking-report adapter, and that adapter calls `score_attempt_sync`, where
  the actual Aiapis/Claude/Codex preference is resolved. If the UI submits a
  desired provider/model, preserve it as request metadata only.
- Speaking reports require at least one non-empty answer transcript among
  scoring turns. If browser dictation and server ASR both return empty text,
  reject before queueing the AI task with a clear "no transcript" error. Do not
  let an empty transcript create a pending task that later fails and leaves the
  UI stuck on Try Again.
- `.runlogs/stack-status.json` records the requested app URL and log directory.
  It is not a health check.
- In Codex desktop/tool shells, ordinary `nohup ... &` children may be cleaned up
  when the command session ends. If a service repeatedly disappears after a
  successful health check, use macOS `launchd` user agents instead of another
  `nohup` retry.
- When using macOS `launchd`, prefer the Python wrapper
  `scripts/run_local_stack_process.py` over shell scripts inside the Desktop
  project directory. User LaunchAgents can hit `Operation not permitted` or exit
  `126` when trying to execute those shell scripts directly, while the Python
  wrapper safely loads cc-switch env values and then execs Django/worker.
- Local HTTP probes must bypass proxy settings:

```bash
curl -I --noproxy '*' --max-time 5 http://127.0.0.1:8767/
```

Without `--noproxy '*'`, local checks may return unrelated proxy errors such as
`502 Bad Gateway`.

### 4. Validation & Error Matrix

| Condition | Meaning | Correct action |
|---|---|---|
| `127.0.0.1 refused to connect` | Nothing is listening on `8767` | Check `lsof`; start Django foreground if helper failed |
| Windows quick-tunnel URL changed after a routine code edit | The tunnel was restarted unnecessarily or a dependent service restart bounced it | Do not restart `ielts-cloudflared`; avoid `Restart-Service ielts-django -Force`; use `get-tunnel-url.ps1` only to read the current URL |
| Windows public URL returns 1033 but local `8767` is healthy | The browser likely has a stale quick-tunnel URL | Run `scripts\windows\get-tunnel-url.ps1`; do not restart the tunnel unless the helper/logs prove the tunnel is dead |
| `stack-status.json` exists but `lsof` is empty | Helper wrote status but process died or never stayed up | Ignore status file; inspect logs and start manually |
| `curl` returns `502 Bad Gateway` without `--noproxy` | Probe likely went through proxy handling | Retry with `curl --noproxy '*'` |
| Two or more `run_ai_worker` processes | Worker duplication | Stop extra workers; keep one |
| Django works but AI tasks stay queued | Worker missing or wrong env | Start `run_ai_worker` and verify process |
| Worker has no `AI_HTTP_*` | AI may fall back to Codex/fallback | Inject provider env before live AI validation |
| ASR says `ffmpeg is not installed or VOLCENGINE_ASR_FFMPEG is not configured` | Django/worker PATH does not expose ffmpeg to server-side audio transcription | Add `/opt/homebrew/bin:/usr/local/bin` to the process PATH and set `VOLCENGINE_ASR_FFMPEG=/opt/homebrew/bin/ffmpeg` when that binary exists |
| `speaking_report` task fails with `http provider is not enabled for speaking reports` | The queued task was misrouted as `provider=http` | Keep task.provider=`codex`; store HTTP preference in payload metadata |
| Attempt saves audio but no report appears | The turns may have empty transcripts | Check turn transcript fields; configure ASR or re-record rather than scoring empty text |
| `.runlogs/*.log` are empty | No useful proof either way | Use `ps`, `lsof`, and foreground command behavior |
| `nohup` process is alive briefly then disappears | Tool shell cleaned background children | Use `launchd` user agents and verify with `launchctl print` |

### 5. Good/Base/Bad Cases

- Good: `lsof -nP -iTCP:8767 -sTCP:LISTEN` shows one Django process and
  `curl -I --noproxy '*' http://127.0.0.1:8767/` returns `HTTP/1.1 200 OK`.
- Good on Windows: `Get-Service ielts-django, ielts-cloudflared` shows both
  services `Running`, and `scripts\windows\get-tunnel-url.ps1` prints the current
  public URL without restarting anything.
- Good: `ps aux | rg 'manage.py (runserver|run_ai_worker)'` shows one
  `runserver` and one `run_ai_worker`.
- Base: Django is alive but worker is not. The site can load, but async writing
  scoring and queued AI jobs are not fully validated.
- Bad: Trusting "IELTS stack requested" or `.runlogs/stack-status.json` without
  proving the port is listening.
- Bad: Leaving two worker processes running after manual recovery.
- Bad on Windows: restarting `ielts-cloudflared` or force-restarting
  `ielts-django` after frontend/CSS/JS edits and thereby changing the public URL.

### 6. Tests Required

Before browser QA:

```bash
lsof -nP -iTCP:8767 -sTCP:LISTEN
curl -I --noproxy '*' --max-time 5 http://127.0.0.1:8767/
ps aux | rg 'manage.py (runserver|run_ai_worker)|daphne' | rg -v rg
```

On Windows NSSM setup:

```powershell
Get-Service ielts-django, ielts-cloudflared
.\scripts\windows\get-tunnel-url.ps1
```

Assertion points:

- `lsof` contains `TCP 127.0.0.1:8767 (LISTEN)`.
- `curl` returns `HTTP/1.1 200 OK` or a concrete Django response.
- Process list has one Django server and at most one AI worker.
- On Windows, public URL checks must not restart `ielts-cloudflared`.
- If testing AI output, the worker process must exist and its env must be
  configured; otherwise do not claim AI-path validation.

For a live Aiapis smoke test, prove real HTTP usage with non-zero usage tokens:

```bash
source scripts/local-stack-env.sh
load_local_stack_env
.venv-django/bin/python scripts/validate_speaking_ai_routing.py --cases p1 --json
```

Passing evidence must include `backend=http_api`,
`provider=openai_compatible_http`, model `gpt-5.4-mini`, and non-zero token
usage. The model field alone is not proof because it can be locally configured.

### 7. Wrong vs Correct

#### Wrong

```bash
scripts/start-local-stack.sh
cat .runlogs/stack-status.json
# Then assume http://127.0.0.1:8767/ is alive.
```

This only proves the helper wrote a file.

#### Correct

```bash
scripts/start-local-stack.sh
lsof -nP -iTCP:8767 -sTCP:LISTEN
curl -I --noproxy '*' --max-time 5 http://127.0.0.1:8767/
ps aux | rg 'manage.py (runserver|run_ai_worker)|daphne' | rg -v rg
```

If `lsof` is empty, start Django in the foreground with the venv Python and keep
that session alive while the user tests:

```bash
.venv-django/bin/python backend_django/manage.py runserver 127.0.0.1:8767 --noreload
```

If the worker does not stay alive in the background, run it foreground once to
capture behavior, then ensure only one worker remains.

If both Django and worker die after the shell command exits, install or refresh
user LaunchAgents and let `launchd` own the processes. The expected labels are:

```bash
com.ielts.local.django
com.ielts.local.aiworker
```

Validation:

```bash
launchctl print gui/$(id -u)/com.ielts.local.django | rg 'state = running|pid ='
launchctl print gui/$(id -u)/com.ielts.local.aiworker | rg 'state = running|pid ='
lsof -nP -iTCP:8767 -sTCP:LISTEN
curl -I --noproxy '*' --max-time 5 http://127.0.0.1:8767/
```

#### Wrong On Windows

```powershell
# CSS/JS changed, so bounce the stack.
Restart-Service ielts-django -Force
Restart-Service ielts-cloudflared
Start-ScheduledTask -TaskName "IELTS Studio Claude AI Worker"
```

This can change the trycloudflare URL, can open or run the wrong worker path,
and does not prove the public issue was caused by the tunnel.

#### Correct On Windows

```powershell
# CSS/JS changed.
# 1. Bump the static ?v= cache key.
# 2. Reload the browser.
# 3. Read the current URL only if the user asks for it.
.\scripts\windows\get-tunnel-url.ps1
```

For backend changes, restart only what is necessary and preserve
`ielts-cloudflared` unless the tunnel itself is proven unhealthy. If a
service-level Django restart may affect the dependent tunnel, warn the user
before doing it.
