# CHANGES

## Summary

Integrated `libfvad` as a real open-source WebRTC VAD dependency behind the C++ `audio_core` module.

## Files Changed

- `third_party/libfvad/**`
- `include/ielts/audio_core.h`
- `src/ielts/audio_core.cpp`
- `tests/audio_core_test.cpp`
- `CMakeLists.txt`
- `scripts/build_audio_core_wasm.sh`
- `软件构造/实验5_开源复用与WASM方案.md`

## API Added

```cpp
enum class VadBackend {
    RmsThreshold,
    WebRtc,
};

struct VadConfig {
    VadBackend backend = VadBackend::RmsThreshold;
    int sample_rate = 16000;
    int frame_ms = 20;
    double speech_threshold = 0.02;
    int aggressiveness = 2;
};

FrameAnalysis AnalyzeFrameWithVad(const std::vector<int16_t>& samples, const VadConfig& config);
bool IsSpeechFrameWithVad(const std::vector<int16_t>& samples, const VadConfig& config);
```

## Design Notes

- Existing `AnalyzeFrame(samples, threshold)` and `IsSpeechFrame(samples, threshold)` remain RMS-threshold based and unchanged.
- `VadBackend::RmsThreshold` is the deterministic fallback.
- `VadBackend::WebRtc` uses `libfvad` and validates sample rate, frame duration, aggressiveness, and frame length before processing.
- No product recording flow is wired to this yet.

