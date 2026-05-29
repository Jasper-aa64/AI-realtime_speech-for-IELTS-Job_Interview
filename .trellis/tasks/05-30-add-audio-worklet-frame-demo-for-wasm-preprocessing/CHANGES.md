# CHANGES

## Summary

Added a standalone AudioWorklet microphone-frame demo for the future WASM preprocessing path.

## Files Changed

- `web/static/wasm/audio_worklet_demo.html`
- `web/static/wasm/audio_worklet_demo.js`
- `web/static/wasm/audio_frame_processor.js`
- `.trellis/tasks/05-30-add-audio-worklet-frame-demo-for-wasm-preprocessing/*`

## Behavior

- User clicks start before microphone permission is requested.
- `AudioWorkletProcessor` receives live input frames.
- Worklet posts frame count, sample rate, frame size, RMS, peak, and mock speech decision.
- Stop button closes nodes, tracks, ports, and the audio context.

No production P1/P2/P3 recording flow is changed.

