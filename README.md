# 运行

# 1) 编译
```
cmake --build build -j
```

# 2) 运行命令行程序
```
./build/CppInterviewSystemQt
```

# IELTS Speaking Simulator

新增独立终端入口 `IELTSSpeakingSimulator`，用于 IELTS Speaking P1/P2/P3 模拟、题库动态加载、Codex CLI 评分和 JSON 报告生成。

## 编译 IELTS 目标

如果现有 `build/` 缓存路径不可用，先重新配置一个构建目录：

```
cmake -S . -B build
cmake --build build --target IELTSSpeakingSimulator -j
```

## 运行

```
./build/IELTSSpeakingSimulator --config-file config/default_config.json --data-dir data/ielts --reports-dir reports
```

菜单支持：

```
[1] Full Mock Exam (P1 + P2 + P3)
[2] Practice Part 1 only
[3] Practice Part 2 only
[4] Practice Part 3 only
[5] View last report
[q] Quit
```

题库会在启动时扫描 `data/ielts/part1/*.json` 和 `data/ielts/part2/*.json`。新增 P1 题库 JSON 后重启程序即可加载，无需重新编译。报告写入 `reports/ielts_YYYYMMDD_HHMMSS.json`。

## IELTS Web App

The production web app is now served by Django from `backend_django/`, with the
browser UI in `web/static/`. Django is the only production runtime for static
frontend files and `/api/*` routes.

The old `web/ielts_server.py` runtime is retired and frozen as a reference
artifact. It is blocked from accidental startup unless
`IELTS_ALLOW_LEGACY_SERVER=1` is set for explicit legacy debugging.

Run locally from the repository root:

```bash
python backend_django/manage.py migrate
python backend_django/manage.py runserver 127.0.0.1:8767 --noreload
```

Run the worker in a second terminal when testing queued AI tasks:

```bash
python backend_django/manage.py run_ai_worker --interval-seconds 2 --idle-interval-seconds 5
```

Open:

```text
http://127.0.0.1:8767
```

The UI supports Home, Mock, Part 1, Part 2, Part 3, speaking reports, daily
writing, writing reports, corpus, and Takeaway. Practice answers are recorded
with the browser microphone using `MediaRecorder`. Browser dictation, when
available, is used only as an automatic transcript source.

Windows auto-start:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/install-ielts-stack-autostart.ps1
```

This registers a hidden scheduled task that starts Django, the web UI, and
Cloudflare Tunnel when you sign in. Public URL stability depends on tunnel
mode:

- quick tunnel: URL changes on restart
- named tunnel: URL stays stable if you already have a Cloudflare tunnel and
  DNS hostname configured; set `IELTS_CLOUDFLARED_TUNNEL_NAME` or place the
  tunnel name in `~/.cloudflared/config.yml`. Set `IELTS_PUBLIC_URL` when you
  want the launcher to record the stable hostname in `.runlogs/public-url.txt`.

Manual start / stop:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/start-ielts-stack.ps1
powershell -ExecutionPolicy Bypass -File scripts/windows/stop-ielts-stack.ps1
```

After startup, the launcher writes the current public URL to
`.runlogs/public-url.txt` and a fuller status snapshot to
`.runlogs/stack-status.json`.

Default flow:

- Part 1: 10 questions, 3 seconds preparation and 35 seconds speaking per turn,
  then one section report.
- Part 2: cue card at the top, 60 seconds preparation and 120 seconds speaking,
  then one report.
- Part 3: 5 questions, 7 seconds preparation and 75 seconds speaking per turn,
  then one section report.
- Mock: P1 -> P2 -> P3 in one session.

History replaces the old Reports page. Each recorded attempt is saved under the
configured reports directory and can be opened as a detailed report with:

- compact IELTS score summary
- criterion-level feedback
- candidate recording playback per turn
- cleaned transcript
- Band 7 model answer
- model-answer playback through generated audio when server TTS succeeds, with
  browser speech synthesis as fallback
- upgrade notes

Backend JSON contracts:

```
GET  /api/accounts/me/
GET  /api/writing/summary
GET  /api/writing/reports
GET  /api/writing/prompts
POST /api/writing/prompts/random
POST /api/writing/entries
GET  /api/writing/entries/{entry_id}
POST /api/writing/entries/{entry_id}/score-task
GET  /api/question-bank/summary
POST /api/question-bank/sample
GET  /api/training/weak-items
GET  /api/training/replay-queue
POST /api/attempts/start
POST /api/attempts/{id}/turns/{turn_id}/audio
POST /api/attempts/{id}/turns/{turn_id}/complete
POST /api/attempts/{id}/score
POST /api/attempts/{id}/abort
GET  /api/history
GET  /api/history/{id}
DELETE /api/history/{id}
GET  /api/audio/{id}/{turn_id}/candidate
POST /api/tts
GET  /api/billing/wallet/
```

By default, dynamic AI generation uses local `codex exec` with
`model_reasoning_effort="low"`, plus server-side VolcEngine TTS integrations
when they are available. Claude API/CLI is not used as a default dynamic
generation path. If a CLI/TTS path is missing or fails,
deterministic/browser fallbacks keep the demo usable.
Pronunciation is not faked from text. Configure Azure Speech on the server when
you want real pronunciation assessment:

```
export AZURE_SPEECH_KEY=...
export AZURE_SPEECH_REGION=...
```

To force fallback mode:

```
AI_PROVIDER_ENABLE_CODEX=0 python backend_django/manage.py run_ai_worker
```

Blog/deploy notes:

- Link blog readers to the hosted Web URL directly; the first screen is the
  practice experience, not a landing page.
- Serve the Django app. It serves `web/static/` entrypoints and owns `/api/*`.
- Keep any future CLI/API credentials only in the backend environment. Do not
  put secrets in `web/static/`.
- Public static hosting alone can show the UI shell, but live sampling,
  scoring, reports, and P3 generation require the Django backend boundary.
