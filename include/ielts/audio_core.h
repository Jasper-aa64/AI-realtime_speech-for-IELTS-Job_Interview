#pragma once

#include <cstdint>
#include <vector>

namespace ielts::audio {

struct FrameAnalysis {
    double rms = 0.0;
    double peak = 0.0;
    bool speech = false;
};

double NormalizedRms(const std::vector<int16_t>& samples);
double NormalizedPeak(const std::vector<int16_t>& samples);

FrameAnalysis AnalyzeFrame(const std::vector<int16_t>& samples, double speech_threshold);
bool IsSpeechFrame(const std::vector<int16_t>& samples, double speech_threshold);

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
