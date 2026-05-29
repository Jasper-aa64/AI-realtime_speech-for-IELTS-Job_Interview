#include "ielts/audio_core.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <stdexcept>

namespace ielts::audio {

namespace {

constexpr double kInt16Scale = 32768.0;

void ValidateThreshold(double threshold) {
    if (threshold < 0.0 || threshold > 1.0) {
        throw std::invalid_argument("speech_threshold must be between 0.0 and 1.0");
    }
}

int SamplesForDuration(int sample_rate, int duration_ms) {
    if (sample_rate <= 0) {
        throw std::invalid_argument("sample_rate must be positive");
    }
    if (duration_ms < 0) {
        throw std::invalid_argument("duration_ms must not be negative");
    }
    return std::max(0, static_cast<int>((static_cast<long long>(sample_rate) * duration_ms) / 1000));
}

int FrameSize(int sample_rate, int frame_ms) {
    if (frame_ms <= 0) {
        throw std::invalid_argument("frame_ms must be positive");
    }
    return std::max(1, SamplesForDuration(sample_rate, frame_ms));
}

int16_t ClampToInt16(double value) {
    const auto rounded = std::lround(value);
    const auto clamped = std::clamp<long>(rounded, -32768, 32767);
    return static_cast<int16_t>(clamped);
}

} // namespace

double NormalizedRms(const std::vector<int16_t>& samples) {
    if (samples.empty()) {
        return 0.0;
    }

    long double sum_squares = 0.0;
    for (const auto sample : samples) {
        const long double normalized = static_cast<long double>(sample) / kInt16Scale;
        sum_squares += normalized * normalized;
    }
    return std::sqrt(static_cast<double>(sum_squares / samples.size()));
}

double NormalizedPeak(const std::vector<int16_t>& samples) {
    int peak = 0;
    for (const auto sample : samples) {
        const int value = sample == INT16_MIN ? 32768 : std::abs(static_cast<int>(sample));
        peak = std::max(peak, value);
    }
    return static_cast<double>(peak) / kInt16Scale;
}

FrameAnalysis AnalyzeFrame(const std::vector<int16_t>& samples, double speech_threshold) {
    ValidateThreshold(speech_threshold);
    FrameAnalysis result;
    result.rms = NormalizedRms(samples);
    result.peak = NormalizedPeak(samples);
    result.speech = result.rms >= speech_threshold;
    return result;
}

bool IsSpeechFrame(const std::vector<int16_t>& samples, double speech_threshold) {
    return AnalyzeFrame(samples, speech_threshold).speech;
}

std::vector<int16_t> TrimSilence(
    const std::vector<int16_t>& samples,
    int sample_rate,
    int frame_ms,
    double speech_threshold,
    int padding_ms) {
    ValidateThreshold(speech_threshold);
    const int frame_size = FrameSize(sample_rate, frame_ms);
    const int padding = SamplesForDuration(sample_rate, padding_ms);

    if (samples.empty()) {
        return {};
    }

    int first_speech = -1;
    int last_speech_end = -1;

    for (int start = 0; start < static_cast<int>(samples.size()); start += frame_size) {
        const int end = std::min(start + frame_size, static_cast<int>(samples.size()));
        const std::vector<int16_t> frame(samples.begin() + start, samples.begin() + end);
        if (IsSpeechFrame(frame, speech_threshold)) {
            if (first_speech < 0) {
                first_speech = start;
            }
            last_speech_end = end;
        }
    }

    if (first_speech < 0) {
        return {};
    }

    const int trimmed_start = std::max(0, first_speech - padding);
    const int trimmed_end = std::min(static_cast<int>(samples.size()), last_speech_end + padding);
    return std::vector<int16_t>(samples.begin() + trimmed_start, samples.begin() + trimmed_end);
}

std::vector<int16_t> ResampleLinear(
    const std::vector<int16_t>& samples,
    int source_rate,
    int target_rate) {
    if (source_rate <= 0 || target_rate <= 0) {
        throw std::invalid_argument("source_rate and target_rate must be positive");
    }
    if (samples.empty()) {
        return {};
    }
    if (source_rate == target_rate) {
        return samples;
    }
    if (samples.size() == 1) {
        return std::vector<int16_t>(std::max(1, target_rate / source_rate), samples.front());
    }

    const double ratio = static_cast<double>(target_rate) / static_cast<double>(source_rate);
    const auto output_size = std::max<std::size_t>(1, static_cast<std::size_t>(std::llround(samples.size() * ratio)));
    std::vector<int16_t> output(output_size);

    for (std::size_t i = 0; i < output.size(); ++i) {
        const double source_pos = static_cast<double>(i) * static_cast<double>(source_rate) / static_cast<double>(target_rate);
        const auto left = static_cast<std::size_t>(std::floor(source_pos));
        const auto right = std::min(left + 1, samples.size() - 1);
        const double fraction = source_pos - static_cast<double>(left);
        const double value = static_cast<double>(samples[left]) * (1.0 - fraction) +
                             static_cast<double>(samples[right]) * fraction;
        output[i] = ClampToInt16(value);
    }

    return output;
}

} // namespace ielts::audio
