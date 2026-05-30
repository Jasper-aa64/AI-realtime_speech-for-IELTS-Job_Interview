# Changes

- Added `audio_analyzer.js` as the main-thread analyzer registry for the standalone WASM bridge demo.
- Refactored `audio_frame_processor.js` so AudioWorklet frame capture delegates to analyzer classes instead of hard-coding all analysis in `process()`.
- Added an analyzer selector and analyzer metric to `audio_worklet_demo.html`.
- Initially kept `mock-rms` as the only ready analyzer and represented `wasm-audio-core` as a disabled future slot until `audio_core_wasm.js` existed.
- Fixed `scripts/build_audio_core_wasm.sh` so libfvad C sources compile as C objects without `-std=c++17`, C++ sources compile separately with `-std=c++17`, and the objects link into the generated `audio_core_wasm.js/.wasm` artifacts with Emscripten.
- Verified the standalone WASM demo artifacts can be built and served from a local static server with `audio_core_wasm.wasm` served as `application/wasm`.
- Exported `HEAP16` and enabled C++ exception catching in the WASM build so the browser demo can write Int16 samples and receive wrapper error codes instead of aborting on invalid WebRTC VAD frames.
- Browser-smoked `audio_core_demo.html`; the demo reports `WASM smoke test passed` with RMS VAD, WebRTC VAD silence, invalid-frame rejection, trim, and resample checks.
- Connected `audio_worklet_demo.html` to the generated `audio_core_wasm.js` analyzer path while keeping `Mock RMS` as the fallback analyzer.
