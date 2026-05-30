# Phase 2.2 PCM Uplink WebSocket

## Goal

Wire the existing browser PCM frame callback to a new WebSocket transport and
prove that 16kHz PCM16 frames can reach the Django/Channels backend.

## Scope

- Add a WebSocket consumer endpoint for PCM frame uplink.
- Count received frames and bytes on the backend and return ack/stat messages.
- Add a frontend uplink helper that can be enabled explicitly and receives PCM
  frames from `createSpeakingAudioPreprocessor({ onPcmFrame })`.
- Keep default recording behavior unchanged unless realtime PCM uplink is
  explicitly enabled.
- Add tests for backend binary frame counting and JSON status/stop messages.

## Out of Scope

- VolcEngine ASR streaming.
- Realtime transcript rendering.
- Follow-up generation or TTS changes.
- Replacing MediaRecorder upload or browser dictation.

## Acceptance Criteria

- Backend WebSocket test proves binary PCM frames arrive and byte counts update.
- Frontend syntax checks pass.
- Full Django test suite still passes.
- No unrelated WIP files are staged or committed.
