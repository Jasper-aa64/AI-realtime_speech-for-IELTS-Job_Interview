# Integrate libfvad As Audio Core VAD Backend

## Goal

Turn the Experiment 5 open-source reuse decision into actual code by integrating `libfvad` as a selectable WebRTC VAD backend for the pure C++ `audio_core` module.

This remains an incremental acceleration/refactor layer. It must not change the existing browser-first IELTS product behavior.

## Scope

- Vendor the minimal `libfvad` source, license, patent grant, authors, and README under `third_party/libfvad/`.
- Add an explicit VAD backend config to `include/ielts/audio_core.h`.
- Keep the existing RMS-threshold VAD as deterministic fallback.
- Add `libfvad_vendor` to CMake.
- Link `audio_core_test` with `libfvad_vendor`.
- Update the WASM build script so future generated WASM includes the WebRTC VAD backend.
- Add unit tests for fallback behavior and WebRTC VAD initialization/error handling.
- Update Experiment 5 documentation.

## Out Of Scope

- No live browser recording integration.
- No P1/P2/P3 product behavior changes.
- No Django API changes.
- No realtime gateway yet.
- No generated `.wasm` commit.

## Acceptance Criteria

- [x] `third_party/libfvad/` includes source plus `LICENSE`, `PATENTS`, `AUTHORS`, and `README.md`.
- [x] `audio_core` exposes a backend config with RMS fallback and WebRTC VAD options.
- [x] Existing `IsSpeechFrame(samples, threshold)` behavior remains available.
- [x] WebRTC VAD accepts only supported sample rates: 8000, 16000, 32000, 48000.
- [x] WebRTC VAD accepts only 10/20/30 ms frames.
- [x] WebRTC VAD aggressiveness must be 0-3.
- [x] Unit tests cover RMS fallback, WebRTC silence frame, and invalid WebRTC config.
- [x] Native `audio_core_test` passes.
- [x] Full CTest passes or any unrelated failures are documented.
- [x] WASM build script lists `libfvad` sources.

## Validation

```bash
cmake -S . -B build
cmake --build build --target audio_core_test
ctest --test-dir build -R audio_core_test --output-on-failure
ctest --test-dir build --output-on-failure
bash -n scripts/build_audio_core_wasm.sh
```

If Emscripten is installed:

```bash
scripts/build_audio_core_wasm.sh
```
