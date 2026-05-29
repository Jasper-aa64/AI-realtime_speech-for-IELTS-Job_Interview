# Verify WebRTC VAD WASM Browser Smoke Demo

## Goal

Make the standalone WASM demo verify both audio_core paths:

- RMS-threshold fallback VAD.
- `libfvad` / WebRTC VAD backend.

This remains a demo-only task. It must not wire WASM into P1/P2/P3 product recording.

## Scope

- Improve `web/static/wasm/audio_core_demo.js` with browser-side assertions.
- Display WebRTC VAD valid-frame and invalid-frame results.
- Keep `scripts/build_audio_core_wasm.sh` as the single build entrypoint.
- Document the demo behavior in the task.

## Out Of Scope

- No live microphone capture.
- No AudioWorklet.
- No P1/P2/P3 integration.
- No generated `.wasm` commit.

## Acceptance Criteria

- [x] Demo reports RMS fallback VAD result.
- [x] Demo reports WebRTC VAD silence-frame result.
- [x] Demo reports invalid WebRTC frame as error.
- [x] Demo throws a clear browser-side assertion if a smoke expectation fails.
- [x] JS syntax passes.
- [x] Native wrapper compile still passes.
- [x] `audio_core_test` still passes.

## Environment Note

The local machine does not currently have a working `emcc`. Homebrew has a stale
`emscripten` prefix but no keg, and `brew install emscripten` stalled while
downloading the `openjdk` dependency. Generated `.wasm` artifacts are still not
committed. Once Emscripten is installed, `scripts/build_audio_core_wasm.sh` is
the only required build entrypoint.

## Validation

```bash
node --check web/static/wasm/audio_core_demo.js
c++ -std=c++17 -Iinclude -Ithird_party/libfvad/include -c src/ielts/audio_core_wasm.cpp -o /tmp/audio_core_wasm.o
cmake --build build --target audio_core_test
ctest --test-dir build -R audio_core_test --output-on-failure
```

If Emscripten is available:

```bash
scripts/build_audio_core_wasm.sh
```
