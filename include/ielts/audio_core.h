#pragma once

#include <cstdint>
#include <vector>

namespace ielts::audio {

struct FrameAnalysis {
    double rms = 0.0;
    double peak = 0.0;
    bool speech = false;
};

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

double NormalizedRms(const std::vector<int16_t>& samples);
double NormalizedPeak(const std::vector<int16_t>& samples);

FrameAnalysis AnalyzeFrame(const std::vector<int16_t>& samples, double speech_threshold);
bool IsSpeechFrame(const std::vector<int16_t>& samples, double speech_threshold);

FrameAnalysis AnalyzeFrameWithVad(const std::vector<int16_t>& samples, const VadConfig& config);
bool IsSpeechFrameWithVad(const std::vector<int16_t>& samples, const VadConfig& config);

std::vector<int16_t> TrimSilence(
    const std::vector<int16_t>& samples,
    int sample_rate,
    int frame_ms,
    double speech_threshold,
    int padding_ms = 0);

std::vector<int16_t> ResampleLinear(
    const std::vector<int16_t>& samples,
    int source_rate,
    int target_rate);

} // namespace ielts::audio
