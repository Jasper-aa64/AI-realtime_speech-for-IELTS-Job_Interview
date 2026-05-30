# Phase 2 Realtime ASR Logic Layer

## Goal

Implement Phase 2.3 logic-layer realtime ASR wiring for the existing ASGI WebSocket path. Browser PCM frames may be sent to `/ws/realtime/pcm/`; when explicitly enabled, the backend streams those PCM chunks through the existing `stream_pcm_chunks()` provider and sends ASR `interim`, `final`, `done`, and `error` events back to the browser so the UI can display live transcript text.

## Context

Phase 2.1 established ASGI/Channels without breaking the synchronous Django stack. Phase 2.2 established optional browser PCM uplink with `?realtime_pcm=1`; default recording remains batch processing. Phase 2.3 must connect the logical ASR stream using fake websocket tests only. Real openspeech endpoint validation is out of scope and must be explicitly marked pending user-provided credentials.

## Requirements

- Keep `/ws/realtime/pcm/` optional behind the existing `?realtime_pcm=1` frontend switch.
- Backend consumer receives binary PCM frames and still emits `pcm_ack` with cumulative frame/byte counts.
- Add explicit JSON control for ASR streaming, e.g. `{"event":"start_asr"}` from the frontend after the socket opens.
- When ASR is enabled, the consumer feeds PCM chunks to `stream_pcm_chunks()` and forwards provider events to the same browser WebSocket:
  - `asr_started`
  - `asr_interim`
  - `asr_final`
  - `asr_done`
  - `asr_error`
- Use existing `backend_django/apps/speaking/volcengine_asr.py`; do not implement openspeech protocol in the consumer.
- Frontend consumes ASR events and updates live transcript state (`state.transcriptFinal`, `state.transcriptInterim`, `state.transcript`, `state.transcriptStatus`) plus a visible status message while recording.
- If ASR is disabled, missing, fails, or is not started, baseline browser dictation and batch completion must keep working.
- Do not claim real openspeech is completed. CHANGES/final report must say: logic layer tested with fake websocket; true endpoint validation awaits user-provided ASR credentials.

## Out of Scope

- Real openspeech endpoint validation.
- ASR credentials or secrets in code.
- Replacing browser dictation or existing batch scoring/reporting.
- Phase 2.4 follow-up chaining.
- Phase 2.5 latency and fallback field test.
- App.js broad modularization or unrelated audio playback diagnostics.

## Acceptance Criteria

- [ ] Backend test covers `/ws/realtime/pcm/` sending binary PCM and receiving forwarded `asr_interim`, `asr_final`, `asr_done` events using fake websocket/provider behavior.
- [ ] Backend test covers disabled/error ASR produces `asr_error` without breaking PCM ack.
- [ ] Existing 2.2 PCM ack test remains valid.
- [ ] Frontend updates live transcript from `asr_interim`/`asr_final` without disabling browser dictation fallback.
- [ ] Full Django suite remains green.
- [ ] `node --check web/static/app.js` passes.
- [ ] `manage.py check` passes.
- [ ] No unrelated WIP files are staged or committed.
- [ ] Completion report explicitly separates logic-layer tested vs real endpoint pending user validation.

## Technical Notes

- Existing provider: `backend_django/apps/speaking/volcengine_asr.py::stream_pcm_chunks`.
- Existing ASGI consumer: `backend_django/apps/speaking/consumers.py::RealtimePcmUplinkConsumer`.
- Existing ASGI tests: `backend_django/apps/speaking/test_asgi_channels.py`.
- Existing frontend PCM optional hook: `web/static/app.js::startRealtimePcmUplink`.
