# CHANGES

## Summary

Added a pure C++ `audio_core` module as the first foundation for future realtime speaking performance work.

This is intentionally incremental: it does not change the existing browser/Django product flow and does not integrate with PortAudio, ASR, WASM, or Django yet.

## Files Changed

* `include/ielts/audio_core.h`
* `src/ielts/audio_core.cpp`
* `tests/audio_core_test.cpp`
* `CMakeLists.txt`

## Added API

Namespace: `ielts::audio`

* `NormalizedRms(samples)`
* `NormalizedPeak(samples)`
* `AnalyzeFrame(samples, speech_threshold)`
* `IsSpeechFrame(samples, speech_threshold)`
* `TrimSilence(samples, sample_rate, frame_ms, speech_threshold, padding_ms)`
* `ResampleLinear(samples, source_rate, target_rate)`

## Design Notes

* The module is pure C++ and IO-free.
* It has no PortAudio, WebSocket, ASR, Django, logging, or filesystem dependency.
* It is suitable as a future shared core for WASM and realtime gateway work.
* The first VAD implementation is deterministic RMS-threshold based; WebRTC VAD / SpeexDSP / libsamplerate remain future Experiment 5 open-source integration candidates.

## Validation

```text
cmake -S . -B build
cmake --build build --target audio_core_test
ctest --test-dir build -R audio_core_test --output-on-failure

100% tests passed, 0 tests failed out of 1
```
