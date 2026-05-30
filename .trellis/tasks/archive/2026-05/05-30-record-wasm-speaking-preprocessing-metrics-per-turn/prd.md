# Record WASM Speaking Preprocessing Metrics Per Turn

## Goal

Promote the feature-flagged WASM speaking preprocessor from a live observer into a per-turn diagnostics source. When the developer flag is enabled, each recorded speaking turn should capture stable metrics from `audio_core` analysis so we can evaluate VAD usefulness before any future audio trimming, endpoint detection, or realtime ASR work.

## Baseline Principle

The existing speaking practice flow is mature and remains the baseline. This task is diagnostic-only:

- Do not replace `MediaRecorder`.
- Do not trim, resample, or mutate uploaded audio.
- Do not change browser dictation behavior.
- Do not change scoring, report generation, TTS, billing, or server APIs unless strictly needed to persist an optional diagnostic payload.
- Do not add visible product UI.

## What I Already Know

- Previous task `05-30-feature-flagged-wasm-speaking-preprocessing` added a disabled-by-default flag:
  - `?wasm_audio=1` enables `wasm-audio-core`.
  - `?wasm_audio=mock` enables `mock-rms`.
  - `?wasm_audio=0` disables it.
- `web/static/wasm/speaking_audio_preprocessor.js` exposes `snapshot()` with metrics:
  - analyzer
  - fallback reason
  - frame count
  - speech frame count
  - latest RMS / peak
  - sample rate / frame size
  - status / error
- Production `web/static/app.js` already starts/stops the preprocessor next to `MediaRecorder` when the flag is enabled.
- The current upload blob and transcript payload are unchanged.
- Generated WASM artifacts remain ignored by git.

## Requirements

- Feature remains off by default.
- When enabled, capture a final preprocessor snapshot for each recorded turn.
- Compute derived diagnostic fields:
  - `total_frames`
  - `speech_frames`
  - `silence_frames`
  - `speech_ratio`
  - `silence_ratio`
  - `sample_rate`
  - `frame_size`
  - `analyzer`
  - `fallback_analyzer`
  - `fallback_reason`
  - `last_error`
- Attach diagnostics to the turn completion payload only when diagnostics exist.
- Keep payload optional and backwards-compatible.
- If diagnostics are missing, incomplete, or fail to compute, continue baseline recording and completion.
- Keep diagnostic data small; do not include raw samples.
- Expose latest per-turn diagnostics through the existing dev metrics surface for local inspection.

## Acceptance Criteria

- [x] Flag disabled: no WASM import, no diagnostics payload.
- [x] Flag enabled with WASM artifacts: final turn completion payload includes `audio_preprocessing_metrics`.
- [x] Flag enabled with missing WASM artifacts: payload records mock fallback metrics or safe fallback reason without blocking turn completion.
- [x] Metrics contain ratios rounded to a stable precision and never include raw audio samples.
- [x] Upload blob remains unchanged.
- [x] Browser dictation payload remains unchanged.
- [x] `node --check web/static/app.js` passes.
- [x] `node --check web/static/wasm/speaking_audio_preprocessor.js` passes.
- [x] WASM build and ignored-artifact checks still pass.

## Definition of Done

- Scoped frontend implementation.
- Optional backend passthrough only if the current `/complete` endpoint safely accepts metadata.
- Validation commands recorded in `CHANGES.md`.
- No unrelated dirty files staged.

## Out of Scope

- Audio trimming.
- Endpoint detection.
- Realtime ASR.
- User-facing metrics UI.
- Report rendering changes.
- Database migration unless existing metadata cannot store diagnostics.
- Commit generated WASM artifacts.

## Technical Notes

- Likely frontend files:
  - `web/static/app.js`
  - `web/static/wasm/speaking_audio_preprocessor.js`
- Likely backend inspection only:
  - `backend_django/apps/speaking/views.py`
  - `backend_django/apps/speaking/services.py`
- Prefer adding diagnostics to an existing metadata field if available.
- If backend currently rejects unknown completion payload fields, keep diagnostics client-side for this task and record that server persistence is a follow-up.
