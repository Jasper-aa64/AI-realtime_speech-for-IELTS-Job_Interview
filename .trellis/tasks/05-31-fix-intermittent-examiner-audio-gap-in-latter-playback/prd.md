# Fix Intermittent Examiner Audio Gap In Playback

## Goal

Remove the intermittent examiner-audio gap/stutter that still appears during speaking practice by preventing dynamically generated examiner TTS from starting playback before the browser has buffered enough media data.

## What I already know

- The current repro is not limited to the literal latter half of a session; it can also appear in Part 1 practice runs with `realtime_pcm=1`.
- `web/static/app.js` uses one shared `#examinerAudio` element for both fixed examiner prompts and dynamic TTS prompts.
- Fixed prompts are direct `/api/tts-audio/examiner/...mp3` assets listed in `FIXED_EXAMINER_AUDIO_URLS`, while dynamic prompts also resolve to `/api/tts-audio/examiner/...` URLs after TTS generation/refresh.
- Both paths already share the same element preparation flow and direct-url playback path.
- The remaining behavioral difference is the readiness gate before `audio.play()`: fixed audio waits for `readyState >= 4`, while non-fixed audio currently proceeds at `readyState >= 3` with a shorter timeout.
- Existing research found no active blob-preload population path and no active use of `stableExaminerAudioUrl()` in the playback path, so the current issue is better explained by readiness timing than by URL indirection.

## Assumptions (temporary)

- The audible gap is caused by dynamic TTS entering playback when the browser only reports `HAVE_FUTURE_DATA` instead of the more stable `HAVE_ENOUGH_DATA` threshold already used for fixed prompts.
- A narrow readiness/timeout fix is preferable to another playback-lifecycle refactor because transaction ownership and duplicate-playback guards are already in place.

## Open Questions

- Whether the dynamic path needs the exact same timeout as fixed prompts, or only the same ready-state threshold with a slightly shorter cap.

## Requirements (evolving)

- Examiner playback must not call `audio.play()` for dynamic TTS until the media element reaches a stable ready state that avoids audible startup gaps.
- Fixed prompts, standard prompts, and streamed follow-up prompts must continue using the same playback pipeline.
- Existing fallback behavior for missing/unready TTS must remain intact.
- Existing client diagnostics for examiner audio must keep working.

## Acceptance Criteria (evolving)

- [ ] Part 1 practice with `realtime_pcm=1` no longer shows intermittent examiner-audio gaps caused by dynamic TTS starting too early.
- [ ] Follow-up streaming still starts examiner playback exactly once when text/TTS becomes ready.
- [ ] Fixed prompts, standard prompts, and no-audio fallback still reach preparation/recording correctly.
- [ ] Verification passes for the touched frontend path (`node --check web/static/app.js` at minimum; broader checks if environment permits).

## Definition of Done (team quality bar)

- Tests added/updated where practical for the touched behavior
- Lint / typecheck / CI-relevant checks green for the changed surface
- Docs/notes updated if behavior changes
- Rollout/rollback considered if risky

## Out of Scope (explicit)

- Replacing the TTS provider
- Rewriting the recording / realtime PCM uplink pipeline
- Refactoring examiner playback into a new controller abstraction
- Changing prompt content or speaking product behavior beyond playback stability

## Technical Approach

Apply a minimal frontend hardening change in `web/static/app.js`:

- Raise the readiness requirement for dynamic examiner TTS to match the fixed-audio path before `audio.play()`.
- Extend the dynamic ready timeout so the browser has enough time to reach the stronger readiness threshold on freshly generated audio.
- Keep the existing TTS refresh polling, direct URL resolution, telemetry, and fallback flow unchanged.

## Decision (ADR-lite)

**Context**: Dynamic examiner TTS and fixed examiner audio already share the same playback element and URL path pattern, but only dynamic audio is allowed to start at a lower `readyState` with a shorter timeout.

**Decision**: Use the same stable ready-state gate for dynamic examiner TTS as fixed examiner prompts, and lengthen the dynamic wait budget accordingly.

**Consequences**: This keeps the diff narrow and directly addresses the last material difference in startup behavior. The tradeoff is a slightly longer bounded wait before fallback when a generated clip is genuinely slow to buffer.

## Technical Notes

- Root-cause note: `.trellis/tasks/05-31-fix-intermittent-examiner-audio-gap-in-latter-playback/research/ready-state-diagnosis.md`
- Inspected readiness and playback flow around `web/static/app.js:1931`, `web/static/app.js:1945`, `web/static/app.js:1951`, `web/static/app.js:2081`, and `web/static/app.js:2334`.
- Existing playback-controller/transaction work remains relevant context but is not the primary fix target for this task.
