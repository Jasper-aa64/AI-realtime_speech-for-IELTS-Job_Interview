# Feature-flagged WASM preprocessing for production speaking recording

## Goal

Add a disabled-by-default path that lets the production speaking recording flow observe browser microphone frames through the C++ `audio_core` WebAssembly analyzer. The goal is to validate production integration and collect frame-level metrics without changing the existing P1/P2/P3 user flow, audio upload payload, transcript behavior, or report generation.

## What I Already Know

- The standalone WASM demo is complete and documented in `.trellis/spec/frontend/wasm-audio-guidelines.md`.
- `web/static/wasm/audio_analyzer.js` exposes `createAnalyzer("mock-rms")` and `createAnalyzer("wasm-audio-core")`.
- `web/static/wasm/audio_frame_processor.js` emits `audio-frame` messages from an `AudioWorkletProcessor`.
- The production speaking recorder in `web/static/app.js` currently uses:
  - `navigator.mediaDevices.getUserMedia({ audio: true })`
  - `MediaRecorder` for upload bytes
  - browser `SpeechRecognition` for transcript capture
  - `/api/attempts/{attempt_id}/turns/{turn_id}/audio`
  - `/api/attempts/{attempt_id}/turns/{turn_id}/complete`
- The production recorder must remain the baseline. The WASM integration is an acceleration/measurement layer, not a replacement.
- Generated artifacts `web/static/wasm/audio_core_wasm.js` and `.wasm` are intentionally ignored and must not be committed.

## Assumptions

- MVP should not trim, resample, or modify the audio uploaded by `MediaRecorder`.
- MVP should not change visible product UI when the flag is disabled.
- Production integration should be isolated in a small module under `web/static/wasm/` so `web/static/app.js` only gets minimal lifecycle hooks.
- If the generated WASM artifacts are absent or fail to load, the app should continue with the existing recorder.

## Requirements

- Feature flag is off by default.
- When the flag is off, production P1/P2/P3/Mock recording behavior remains unchanged.
- When the flag is on, the recording lifecycle may:
  - create an `AudioContext`
  - load `audio_frame_processor.js`
  - create an analyzer via `audio_analyzer.js`
  - collect frame metrics such as frame count, RMS, peak, speech-frame count, and fallback/error state
- WASM preprocessing must never block `MediaRecorder.start()`, `MediaRecorder.stop()`, audio upload, or turn completion.
- A failed `AudioWorklet` or WASM load must degrade to the existing recorder without ending the practice session.
- Do not modify server APIs, database models, scoring, transcript, TTS, report generation, or billing in this task.
- Do not commit generated `.js` / `.wasm` artifacts.

## Acceptance Criteria

- [x] Default production flow does not import or initialize WASM preprocessing.
- [x] A dev flag can enable production microphone-frame analysis for speaking practice.
- [x] With flag enabled and artifacts present, the analyzer starts during recording and stops cleanly afterward.
- [x] With flag enabled and artifacts missing, the user can still record/upload/complete a turn normally.
- [x] WASM metrics are available for development inspection without changing the uploaded audio blob.
- [x] P1/P2/P3/Mock baseline behavior remains compatible with current tests.
- [x] `node --check web/static/app.js` passes.
- [x] WASM standalone checks from `.trellis/spec/frontend/wasm-audio-guidelines.md` still pass where applicable.

## Definition of Done

- Scoped implementation with minimal `web/static/app.js` changes.
- New helper module documented or self-contained.
- Validation commands recorded.
- No unrelated dirty files staged.
- Rollback is straightforward: disable the flag or remove the lifecycle hooks.

## Out of Scope

- Real-time ASR.
- Replacing `MediaRecorder`.
- Mutating upload bytes through VAD trimming/resampling.
- User-facing production settings UI.
- Server-side C++ realtime gateway.
- Codex/AI scoring changes.
- Committing generated WASM artifacts.

## Technical Notes

- Existing spec: `.trellis/spec/frontend/wasm-audio-guidelines.md`.
- Likely files:
  - `web/static/app.js`
  - `web/static/wasm/audio_analyzer.js`
  - `web/static/wasm/audio_frame_processor.js`
  - possible new `web/static/wasm/speaking_audio_preprocessor.js`
- Production recorder anchor points:
  - `startRecording(sessionId)`
  - `stopRecording()`
  - `finalizeTurn(mimeType)`
- Recommended integration shape:
  - `createSpeakingAudioPreprocessor({ enabled, analyzerId, threshold })`
  - `await preprocessor.start(stream)`
  - `await preprocessor.stop()`
  - `preprocessor.snapshot()`
- Current `web/static/app.js` is already dirty from unrelated work. Implementation must patch carefully and stage only files belonging to this task.

## Open Questions

- Which flag surface should the MVP use?
