# Extract C++ Audio Core For Realtime Speaking

## Goal

Extract a small, pure C++ `audio_core` module as the foundation for future browser WASM audio preprocessing and server-side realtime speech gateway work.

This is an incremental performance/refactor layer. It must not change the existing browser-first IELTS product flow.

## Scope

Create a pure, IO-free C++ audio module that can be tested without PortAudio, ASR credentials, WebSocket services, Django, or browser runtime.

Initial functions:

* Frame RMS / peak analysis for 16-bit PCM.
* Simple deterministic VAD decision by normalized RMS threshold.
* Silence trimming with optional padding.
* Deterministic linear resampling for mono PCM.

## Out Of Scope

* No browser WASM build yet.
* No Emscripten integration yet.
* No WebRTC VAD / SpeexDSP / libsamplerate integration yet.
* No Django integration.
* No changes to existing P1/P2/P3 browser behavior.
* No changes to deprecated `web/ielts_server.py`.

## Acceptance Criteria

* [x] Add `include/ielts/audio_core.h`.
* [x] Add `src/ielts/audio_core.cpp`.
* [x] Add `tests/audio_core_test.cpp`.
* [x] Register `audio_core_test` in CMake/CTest.
* [x] The new module has no PortAudio, network, Django, or logging dependency.
* [x] Tests cover silence, speech detection, trim behavior, padding behavior, and resampling.
* [x] Existing C++ targets are not made to depend on new heavy libraries.

## Validation

Preferred checks:

```bash
cmake --build <build-dir> --target audio_core_test
ctest --test-dir <build-dir> -R audio_core_test --output-on-failure
```

Fallback checks if the local CMake/vcpkg environment is not usable:

```bash
c++ -std=c++17 -Iinclude tests/audio_core_test.cpp src/ielts/audio_core.cpp <gtest flags>
```

## Notes

This task is the first implementation step for the longer-term realtime speaking line:

```text
audio_core -> tests -> WASM demo -> realtime gateway -> Django realtime/fallback integration
```
