# Streaming Examiner Follow-Up Phase 1

## Goal

Implement the first phase of the "real examiner" follow-up pipeline: stream generated examiner follow-up text to the browser as it arrives, then surface server TTS readiness without replacing the existing `/complete` fallback path.

## Source Spec

Primary implementation contract: `docs/SPEC-streaming-examiner-followup.md`.

## Scope

- Add a streaming token generator to the OpenAI-compatible HTTP provider.
- Add an owner-scoped Django SSE endpoint:
  `GET /api/attempts/{attempt_id}/turns/{turn_id}/follow-up-stream`.
- Wire the frontend to consume the SSE stream for dynamic P1/P3 follow-up turns.
- Keep `turn_complete_view` and `complete_turn()` compatible with the existing batch path.
- Keep fallback explicit and safe when the HTTP provider is unavailable.

## Out of Scope

- Realtime ASR / C++ realtime gateway.
- Replacing the existing `/complete` contract.
- Changing writing/report/corpus/Takeaway flows.
- Persisting or exposing provider secrets.

## Acceptance Criteria

- [x] `HttpApiProvider.stream_tokens()` yields text chunks as the provider streams them.
- [x] Stream-token unit tests cover chunk parsing and provider errors.
- [x] `/api/attempts/{attempt_id}/turns/{turn_id}/follow-up-stream` returns `text/event-stream`.
- [x] SSE emits `chunk`, `question_complete`, `tts_ready` or explicit fallback/timeout events.
- [x] The endpoint is authenticated and owner-scoped.
- [x] Frontend consumes the stream with `fetch`/`ReadableStream` and progressively displays the next follow-up.
- [x] Existing `/complete` behavior still works when streaming is unavailable.
- [x] Targeted tests and syntax checks pass.
