# Implement OpenAI-compatible HTTP provider for fast speaking follow-ups

## Goal

Move the user-visible speaking follow-up generation path away from Codex CLI subprocess cold starts and toward a configurable OpenAI-compatible HTTP API client. P1/P3 follow-up generation should prefer HTTP, fall back to the existing Codex CLI path when HTTP is unavailable, and finally fall back to clearly marked local fallback text when all AI providers fail.

## What I already know

- The product value is "real examiner-style follow-up"; latency currently comes from spawning `codex exec` for each follow-up.
- `backend_django/apps/speaking/services.py` contains `quick_follow_up_runner`, `_generate_p3_dynamic_follow_up`, and `_generate_p1_identity_follow_up`.
- `backend_django/apps/ai/provider_config.py` already has provider routing concepts but no implemented OpenAI-compatible HTTP client for follow-ups.
- The user has OpenAI-compatible endpoints, so `base_url`, `api_key`, and `model` must all be environment-driven.
- Existing business WIP files are dirty and must not be touched or staged.

## Requirements

- Add a provider-agnostic OpenAI-compatible HTTP client using environment variables:
  - `AI_HTTP_BASE_URL`
  - `AI_HTTP_API_KEY`
  - `AI_HTTP_MODEL`
  - optional timeout/config values may be environment-driven.
- Prefer streaming Chat Completions when possible and parse SSE `delta.content` chunks.
- Use HTTP first for P1/P3 follow-ups, then Codex CLI, then explicit fallback.
- Never log, return, persist, or commit API keys.
- Preserve existing public function names and backward-compatible behavior where possible.
- Keep fallback metadata explicit; fallback must not masquerade as AI success.
- Do not change frontend behavior in this task.

## Acceptance Criteria

- [ ] HTTP provider/client exists and reads configuration from environment only.
- [ ] P3 follow-up generation prefers HTTP and records backend metadata as HTTP on success.
- [ ] P1 identity follow-up generation prefers HTTP and records backend metadata as HTTP on success.
- [ ] HTTP failure falls back to Codex; Codex failure falls back to clearly marked fallback text.
- [ ] Tests cover streaming parse, missing config, HTTP success path, and HTTP-to-Codex/fallback path.
- [ ] A latency/diagnostic script exists without leaking secrets.
- [ ] `python manage.py check` and targeted tests pass.
- [ ] CHANGES.md records implementation and validation.

## Out of Scope

- Realtime gateway / interruptible examiner flow.
- Frontend streaming rendering.
- Changing prompts or question-bank logic beyond routing the provider call.
- Retired `web/ielts_server.py`.
- Any existing dirty business WIP files.

## Technical Notes

- Source spec: `docs/SPEC-http-api-provider-followup-latency.md`.
- Backend conventions: `.trellis/spec/backend/index.md`, `.trellis/spec/backend/quality-guidelines.md`.
- Research notes will live under this task's `research/` directory.
