# Add AudioWorklet Frame Demo For WASM Preprocessing

## Goal

Add a standalone browser demo that proves microphone audio can be captured as realtime frames through `AudioWorklet`.

This is the bridge between the current C++/WASM audio core work and a future product integration. It must not change P1/P2/P3 production recording behavior.

## Scope

- Add `web/static/wasm/audio_worklet_demo.html`.
- Add `web/static/wasm/audio_worklet_demo.js`.
- Add `web/static/wasm/audio_frame_processor.js`.
- Use a JS mock analyzer for RMS/peak/speech decision while Emscripten is unavailable.
- Display live sample rate, frame size, frame count, RMS, peak, and speech/silence decision.

## Out Of Scope

- No production P1/P2/P3 recording integration.
- No Django API changes.
- No generated WASM artifacts.
- No real WebRTC VAD in the worklet yet.

## Acceptance Criteria

- [x] Demo requests microphone permission only after the user clicks start.
- [x] Demo uses `AudioContext.audioWorklet.addModule`.
- [x] Processor posts frame metrics to the main thread.
- [x] Main thread renders sample rate, frame size, RMS, peak, and speech/silence state.
- [x] Stop button closes tracks, nodes, and the audio context.
- [x] JS syntax checks pass for all new demo scripts.
- [x] Existing `audio_core_test` still passes.

## Validation

```bash
node --check web/static/wasm/audio_frame_processor.js
node --check web/static/wasm/audio_worklet_demo.js
cmake --build build --target audio_core_test
ctest --test-dir build -R audio_core_test --output-on-failure
```
