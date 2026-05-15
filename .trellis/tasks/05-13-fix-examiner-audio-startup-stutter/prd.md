# Fix examiner audio startup stutter

## Goal

Reduce or remove the short, repeatable pause at the start of examiner question audio playback in the web IELTS speaking flow.

## What I already know

* The issue is scoped to playback startup, not the Saving or Analyzing backend stages.
* Frontend playback is handled in `web/static/app.js` by `renderExaminerAudio`, `preloadNextExaminerAudio`, and `beginExaminerPhase`.
* Examiner TTS files are served from `web/ielts_server.py` via `/api/tts-audio/{role}/{filename}` and `send_file_audio`.
* The current audio response uses `Cache-Control: no-store` and does not implement HTTP Range responses.
* The frontend sets `src`, calls `load()`, then later seeks to `0` and calls `play()`.

## Assumptions

* Browser decode/buffer startup is the likely source of the initial pause.
* Improving HTTP caching, preserving preloaded audio references, and waiting for readiness before playback should improve perceived startup smoothness.
* The change should not alter exam flow timing except to begin preparation only after examiner audio actually ends.

## Requirements

* Preserve existing examiner audio fallback behavior when generated audio is unavailable or fails.
* Make examiner TTS audio cacheable and range-friendly.
* Keep a stable preload reference for the next examiner prompt.
* Avoid repeated unnecessary `load()` calls when the same audio URL is already assigned.
* Start playback from a ready-enough media state rather than always firing immediately after `src` assignment.

## Acceptance Criteria

* [x] Examiner audio endpoint supports full-file responses and byte range requests.
* [x] Examiner/model TTS audio is cacheable for generated file URLs.
* [x] Frontend preloads next examiner audio using a retained cache.
* [x] Existing browser speech fallback still works on audio error/play rejection.
* [x] Existing Python tests pass, or failures are documented if unrelated.

## Definition of Done

* Tests added/updated where useful.
* Relevant test suite run.
* No unrelated files changed.

## Out of Scope

* Optimizing Saving latency.
* Optimizing Analyzing latency.
* Replacing VolcEngine TTS.
* Changing candidate recording behavior.

## Technical Notes

* `web/static/app.js`: examiner audio element lifecycle and preload logic.
* `web/ielts_server.py`: static audio serving behavior.
