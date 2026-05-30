# Optimize Follow-up Voice Response Latency

## Goal

Make generated P1/P3 follow-up questions feel like spoken examiner prompts, not silent text prompts.

The HTTP follow-up provider has already moved question generation from slow Codex CLI to a faster OpenAI-compatible API. The remaining gap is voice: generated follow-up turns often return with `examiner_tts.status=pending`, and the frontend immediately starts preparation because it has no way to refresh the server-generated TTS URL.

## Scope

- Add a small owner-scoped Django endpoint to refresh the current turn's examiner TTS.
- Reuse the existing VolcEngine TTS path and cache key behavior.
- In the frontend examiner phase, if a turn has pending/warming examiner TTS, wait briefly for the server TTS URL before starting preparation.
- Keep fallback explicit. If server TTS is still unavailable, continue the flow without browser TTS and without blocking the learner for long.

## Out of Scope

- Do not replace the TTS provider.
- Do not introduce streaming TTS.
- Do not change AI follow-up generation prompts.
- Do not refactor the practice frontend broadly.
- Do not touch retired `web/ielts_server.py`.

## Acceptance Criteria

- Dynamic P1/P3 follow-up turns can obtain a server `audio_url` after `/complete` returns pending TTS.
- P3 dynamic follow-up saves must enqueue or allow server TTS generation; it must not stay pending forever.
- Frontend waits only a short bounded time for pending TTS and then continues safely.
- Owner scoping is enforced for the new endpoint.
- Existing fallback metadata remains explicit; no browser TTS is reintroduced as the normal path.
- Targeted speaking tests pass.

## Validation

- `python3 backend_django/manage.py test apps.speaking.test_http_followups`
- A targeted Django test for the new examiner TTS refresh endpoint/service.
- `node --check web/static/app.js`
