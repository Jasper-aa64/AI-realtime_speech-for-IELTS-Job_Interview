<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

## Subagents

- ALWAYS wait for all subagents to complete before yielding.
- Spawn subagents automatically when:
  - Parallelizable work (e.g., install + verify, npm test + typecheck, multiple tasks from plan)
  - Long-running or blocking tasks where a worker can run independently.
  - Isolation for risky changes or checks

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

## Docs map

`docs/index.md` is the navigation hub for everything else (ops, specs, plans,
reports, research). Start there; do not pile prose into this file — it is a map,
not a manual.

Hard rule (frontend): icon-only buttons must be square — equal width/height plus
matching `min-width`/`min-height` and `box-sizing: border-box`, or a stray global
`min-height` stretches them into tall rectangles. See
`docs/frontend-ui-conventions.md`.

## Local Startup / Public Access

When asked to start, restart, expose, debug public access, diagnose `502 Bad Gateway`, the backend "randomly dropping", or work with NSSM / Windows services for this project, read this guide first:

- `docs/ops/windows-startup-and-public-access.md`

It documents the Django + AI worker startup paths, the legacy watchdog option, NSSM service scripts, interactive-user scheduled tasks, Cloudflare quick tunnel usage, and the 502 checklist.

Do NOT keep the stack alive long-term with `start-ielts-stack.ps1` or the `IELTS Stack Auto Start` task: that launcher kills daphne+worker in its `finally` on exit and never restarts them.

Current deployed setup override, updated 2026-06-21: this Windows machine keeps
only the NSSM services `ielts-django` and `ielts-cloudflared` running as the
steady state. The **AI worker is NOT auto-started** and is not part of the
always-on stack. The `IELTS Studio Claude AI Worker` scheduled task exists but
must stay stopped; do **not** start it (nor the `IELTS Stack Watchdog`, `IELTS
Stack Auto Start`, or LocalSystem `ielts-worker`) unless the user **explicitly**
asks. The user has moved away from that terminal-popping worker mechanism, so
starting it on your own initiative is wrong even when a report looks stuck —
report-generation failures are surfaced to the user, who then retries via their
chosen model. If the user does ask to run the worker, its action must include
`-WindowStyle Hidden` (Claude/Codex CLI auth belongs to the logged-in user, so
the LocalSystem `ielts-worker` service stays disabled). Use
`scripts\windows\get-tunnel-url.ps1` to print the currently usable trycloudflare
URL, because `.runlogs\cloudflared.log` may contain stale 530/1033 URLs after
quick-tunnel restarts (a stale URL is the usual cause of a 1033, not a real
outage).
