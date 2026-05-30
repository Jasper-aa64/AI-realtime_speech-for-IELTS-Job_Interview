# Abstract AudioWorklet Analyzer for WASM Swap

## Goal

Keep the standalone AudioWorklet microphone demo usable today while separating frame capture from frame analysis, so the current JavaScript RMS analyzer can later be replaced by `audio_core_wasm.js` without changing the frame-stream plumbing.

## Scope

- Only modify the standalone files under `web/static/wasm/`.
- Do not integrate this into the production P1/P2/P3 recording flow.
- The `Mock RMS` analyzer remains usable without generated artifacts.
- The `WASM audio_core` analyzer requires `scripts/build_audio_core_wasm.sh` to generate the ignored `audio_core_wasm.js/.wasm` artifacts.

## Acceptance Criteria

- [x] `audio_frame_processor.js` owns frame capture and delegates analysis through an analyzer boundary.
- [x] The demo exposes the active analyzer in the UI.
- [x] The default analyzer remains the current JavaScript RMS behavior.
- [x] `wasm-audio-core` is selectable after `scripts/build_audio_core_wasm.sh` generates `audio_core_wasm.js/.wasm`.
- [x] The production app files remain untouched.
