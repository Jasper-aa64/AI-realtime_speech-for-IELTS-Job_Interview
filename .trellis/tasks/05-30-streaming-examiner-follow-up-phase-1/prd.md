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

- [ ] `HttpApiProvider.stream_tokens()` yields text chunks as the provider streams them.
- [ ] Stream-token unit tests cover chunk parsing and provider errors.
- [ ] `/api/attempts/{attempt_id}/turns/{turn_id}/follow-up-stream` returns `text/event-stream`.
- [ ] SSE emits `chunk`, `question_complete`, `tts_ready` or explicit fallback/timeout events.
- [ ] The endpoint is authenticated and owner-scoped.
- [ ] Frontend consumes the stream with `fetch`/`ReadableStream` and progressively displays the next follow-up.
- [ ] Existing `/complete` behavior still works when streaming is unavailable.
- [ ] Targeted tests and syntax checks pass.
