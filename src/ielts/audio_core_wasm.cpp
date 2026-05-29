#include "ielts/audio_core.h"

#include <algorithm>
#include <cstdint>
#include <exception>
#include <vector>

#ifndef EMSCRIPTEN_KEEPALIVE
#define EMSCRIPTEN_KEEPALIVE
#endif

namespace {

std::vector<int16_t> CopyInput(const int16_t* samples, int length) {
    if (length < 0) {
        throw std::invalid_argument("length must not be negative");
    }
    if (length == 0) {
        return {};
    }
    if (samples == nullptr) {
        throw std::invalid_argument("samples must not be null");
    }
    return std::vector<int16_t>(samples, samples + length);
}

int CopyOutput(const std::vector<int16_t>& result, int16_t* output, int output_capacity) {
    if (output_capacity < 0) {
        return -1;
    }
    if (result.empty()) {
        return 0;
    }
    if (output == nullptr || output_capacity < static_cast<int>(result.size())) {
        return -2;
    }
    std::copy(result.begin(), result.end(), output);
    return static_cast<int>(result.size());
}

} // namespace

extern "C" {

EMSCRIPTEN_KEEPALIVE
double audio_core_normalized_rms(const int16_t* samples, int length) {
    try {
        return ielts::audio::NormalizedRms(CopyInput(samples, length));
    } catch (const std::exception&) {
        return -1.0;
    }
}

EMSCRIPTEN_KEEPALIVE
double audio_core_normalized_peak(const int16_t* samples, int length) {
    try {
        return ielts::audio::NormalizedPeak(CopyInput(samples, length));
    } catch (const std::exception&) {
        return -1.0;
    }
}

EMSCRIPTEN_KEEPALIVE
int audio_core_is_speech(const int16_t* samples, int length, double speech_threshold) {
    try {
        return ielts::audio::IsSpeechFrame(CopyInput(samples, length), speech_threshold) ? 1 : 0;
    } catch (const std::exception&) {
        return -1;
    }
}

EMSCRIPTEN_KEEPALIVE
int audio_core_trim_silence(
    const int16_t* samples,
    int length,
    int sample_rate,
    int frame_ms,
    double speech_threshold,
    int padding_ms,
    int16_t* output,
    int output_capacity) {
    try {
        const auto input = CopyInput(samples, length);
        const auto result = ielts::audio::TrimSilence(
            input,
            sample_rate,
            frame_ms,
            speech_threshold,
            padding_ms);
        return CopyOutput(result, output, output_capacity);
    } catch (const std::exception&) {
        return -1;
    }
}

EMSCRIPTEN_KEEPALIVE
int audio_core_resample_linear(
    const int16_t* samples,
    int length,
    int source_rate,
    int target_rate,
    int16_t* output,
    int output_capacity) {
    try {
        const auto input = CopyInput(samples, length);
        const auto result = ielts::audio::ResampleLinear(input, source_rate, target_rate);
        return CopyOutput(result, output, output_capacity);
    } catch (const std::exception&) {
        return -1;
    }
}

} // extern "C"

