# Changes

## Implemented

- Added `web/static/wasm/speaking_audio_preprocessor.js`.
- Added a disabled-by-default production speaking flag:
  - `?wasm_audio=1` enables `wasm-audio-core` and persists it in localStorage.
  - `?wasm_audio=mock` enables the JS `mock-rms` analyzer.
  - `?wasm_audio=0` disables the integration and persists `off`.
- Wired production `startRecording()` to start the preprocessor after `MediaRecorder.start()`.
- Wired `stopRecording()` and `stopAllRuntime()` to stop the preprocessor without owning or stopping the recorder stream.
- Exposed dev metrics at `window.__ieltsWasmAudioPreprocess.metrics()`.

## Preserved

- Existing `MediaRecorder` upload blob is unchanged.
- Browser dictation and transcript payload are unchanged.
- Turn completion, scoring, TTS, billing, and reports are unchanged.
- Default production flow does not load WASM artifacts.

## Validation

- `node --check web/static/app.js`
- `node --check web/static/wasm/speaking_audio_preprocessor.js`
- `node --check web/static/wasm/audio_analyzer.js`
- `node --check web/static/wasm/audio_frame_processor.js`
- `node --check web/static/wasm/audio_worklet_demo.js`
- `scripts/build_audio_core_wasm.sh`
- `git check-ignore -v web/static/wasm/audio_core_wasm.js web/static/wasm/audio_core_wasm.wasm`
- Browser smoke: `?wasm_audio=1` persists `wasm-audio-core`; `?wasm_audio=0` persists `off`.
- Browser smoke with fake microphone: `wasm-audio-core` starts, receives frames, produces RMS/peak/speech metrics, then stops cleanly.
- Browser smoke with blocked WASM artifact: helper falls back to `mock-rms` and continues receiving frames.
