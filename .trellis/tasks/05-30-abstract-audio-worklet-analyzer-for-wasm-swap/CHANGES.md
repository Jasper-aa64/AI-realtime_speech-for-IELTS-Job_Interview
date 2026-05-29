# Changes

- Added `audio_analyzer.js` as the main-thread analyzer registry for the standalone WASM bridge demo.
- Refactored `audio_frame_processor.js` so AudioWorklet frame capture delegates to analyzer classes instead of hard-coding all analysis in `process()`.
- Added an analyzer selector and analyzer metric to `audio_worklet_demo.html`.
- Kept `mock-rms` as the only ready analyzer and represented `wasm-audio-core` as a disabled future slot until `audio_core_wasm.js` exists.

