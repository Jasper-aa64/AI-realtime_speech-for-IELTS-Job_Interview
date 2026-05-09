# IELTS Web P1/P2 Flow, Reports, Abort, and History

## Goal

Implement the requested IELTS web practice behavior updates across the server, frontend, tests, and narrowly relevant docs/spec notes if needed.

## Requirements

- Attempt status supports `started`, `aborted`, `ready_to_score`, and `scored`.
- `POST /api/attempts/{id}/abort` marks an attempt aborted with `aborted_at`.
- Aborted attempts cannot be scored and are excluded from `/api/history`.
- Practice flow has a visible Exit button that stops audio, speech synthesis, timers, pending auto-next timeouts, dictation, MediaRecorder, and media tracks.
- Exit aborts the current attempt and returns UI to idle/ready without showing a report.
- P1/P3 auto-play examiner question after Start; P2 auto-plays instruction only.
- Prefer server audio; use browser TTS only as fallback.
- Preload next turn examiner audio where available.
- Frontend dictation uses final/interim buffers and waits briefly for final dictation before submitting.
- Submit `transcript_status` as `captured`, `interim_fallback`, or `missing`.
- Backend persists `turn.transcript_status`.
- Missing transcript UI text says recording exists but transcript was not captured.
- P2 cue card stays fixed at top and record control stays in the same place across Listening/Preparing/Recording/Saving.
- No duplicate prompt/cue section below P2.
- Detail page uses a per-turn table with headers `题目`, `Your recording`, `Band 7 spoken version`, `升级了什么`.
- Each report row includes question, audio plus transcript/status, turn-specific Band 7 text plus model audio if available, and turn-specific upgrade notes.
- P2 uses the same table with one row.
- Clean Band 7 model output by removing Trellis/session/workflow/system logs, Markdown fences, and non-answer text.
- If cleaned output is not plausible spoken answer, use deterministic fallback.
- Generate per-turn `turn.band7_version`, `turn.model_audio`, and `turn.upgrade_notes` when scoring.
- Keep aggregate `band7_version` only as summary fallback, not the main P1/P3 detail.
- Redesign history rail title/refresh/scroll affordance/active state while keeping details full width below.

## Acceptance Criteria

- [ ] Abort endpoint works and records `aborted_at`.
- [ ] Aborted attempts cannot score and do not appear in history.
- [ ] P1/P3/P2 playback and Exit behavior matches requirements.
- [ ] Transcript status is recorded and displayed with stable fallback messaging.
- [ ] P2 layout remains structurally stable after start.
- [ ] Reports render per-turn Band 7 and upgrade notes in the required table.
- [ ] Band 7 cleaning removes Trellis SessionStart-like logs and falls back deterministically.
- [ ] Tests cover abort, P2 examiner text, per-turn scoring, cleaning, and missing transcript behavior.

## Write Scope

- `web/ielts_server.py`
- `web/static/app.js`
- `web/static/index.html`
- `web/static/styles.css`
- `tests/test_ielts_web_server.py`
- Optional focused docs/spec note under `.trellis/spec` or `docs`.

## Verification

- `node --check web/static/app.js`
- `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py`
- `python3 -m unittest discover -s tests -p 'test_*.py'`
- `ctest --test-dir build-ui-verify --output-on-failure`

## Out of Scope

- Broad unrelated refactors.
- Commits or pushes.
