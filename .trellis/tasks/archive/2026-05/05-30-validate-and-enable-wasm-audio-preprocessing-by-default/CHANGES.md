# Changes

## What Changed

- Added a Django `/wasm/<path>` static route for generated audio core WASM assets and demo files.
- Added common app tests for `/wasm/audio_core_wasm.wasm` MIME type and path traversal rejection.
- Changed the browser audio preprocessing default from `off` to `wasm-audio-core`.

## Browser Verification

- Demo page: `http://127.0.0.1:8768/wasm/audio_core_demo.html`
  - PASS `WASM smoke test passed.`
  - PASS RMS VAD classified mixed input as speech.
  - PASS WebRTC VAD classified 20ms silence as silence.
  - PASS WebRTC VAD rejected invalid frame length.
- Speaking page: `http://127.0.0.1:8768/?view=p1&wasm_audio=wasm-audio-core`
  - PASS `window.__ieltsWasmAudioPreprocess.enabled()` returned true.
  - PASS WASM analyzer processed browser audio frames.
  - PASS metrics showed `analyzer = wasm-audio-core`, `frameCount = 310`, no fallback.
- Fallback path:
  - Simulated `.wasm` load failure by aborting `/wasm/audio_core_wasm.wasm`.
  - PASS analyzer fell back to `mock-rms`.
  - PASS audio frame processing continued with `frameCount = 168`.
- Default path:
  - Opened `/?view=p1` without `wasm_audio`.
  - PASS default enabled WASM preprocessing and processed frames with `analyzer = wasm-audio-core`.

## Command Verification

- `node --check web/static/app.js`
- `node --check web/static/wasm/audio_analyzer.js`
- `node --check web/static/wasm/audio_core_demo.js`
- `node --check web/static/wasm/speaking_audio_preprocessor.js`
- `node --no-warnings scripts/test_wasm_audio_preprocessor_metrics.mjs`
- `cd backend_django && python3 manage.py test apps.common.tests apps.speaking.tests.SpeakingRuntimeApiTests.test_turn_complete_persists_audio_preprocessing_metrics -v 1`
- `cd backend_django && python3 manage.py check`

## Boundaries

- No unrelated business WIP was staged.
- Existing dirty frontend/theme/test/database files remain outside this task commit except for the single selected `web/static/app.js` default-value hunk.
