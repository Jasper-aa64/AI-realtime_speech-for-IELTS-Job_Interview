# Phase 2 Browser PCM Frame Hook

## Goal

Prepare the existing WASM/AudioWorklet microphone preprocessor for realtime ASR
transport by exposing a 16kHz mono PCM frame callback. This must be additive and
must not change the current recording flow unless a caller explicitly provides
the callback.

## Scope

- Add reusable Float32 -> 16kHz PCM16 conversion helpers.
- Add optional `onPcmFrame` callback support to `createSpeakingAudioPreprocessor`.
- Preserve existing metrics and analyzer behavior.
- Keep baseline MediaRecorder upload and browser dictation unchanged.

## Acceptance Criteria

- `node --check web/static/wasm/speaking_audio_preprocessor.js` passes.
- `node --check web/static/app.js` passes.
- No default app behavior changes unless a callback is supplied.
