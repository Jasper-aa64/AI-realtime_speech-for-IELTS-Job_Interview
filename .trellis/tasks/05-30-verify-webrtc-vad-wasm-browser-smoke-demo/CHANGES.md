# CHANGES

## Summary

Expanded the standalone WASM demo so it verifies both the RMS fallback VAD path and the `libfvad` / WebRTC VAD path.

## Files Changed

- `web/static/wasm/audio_core_demo.html`
- `web/static/wasm/audio_core_demo.js`
- `.trellis/tasks/05-30-verify-webrtc-vad-wasm-browser-smoke-demo/*`

## Behavior

The demo now checks:

- RMS VAD returns speech for mixed silence/speech input.
- WebRTC VAD returns silence for a valid 20 ms silence frame.
- WebRTC VAD returns error for an invalid 100-sample frame.
- Trim and downsample functions return plausible output sizes.

No P1/P2/P3 product flow is changed.

## Environment Note

`emcc` is not available on this machine yet. A Homebrew install attempt stalled
on the `openjdk` dependency and was stopped. The demo remains ready to run once
Emscripten is installed via `scripts/build_audio_core_wasm.sh`.
