#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace interview { namespace services { class RealtimeClient; } }

namespace ielts {

struct RealtimeCaptureOptions {
    int max_seconds = 60;
    bool stop_on_first_final = true;
    bool allow_enter_stop = true;
    bool record_audio_without_realtime = false;
    std::string status_label = "Listening";
};

struct RealtimeCaptureResult {
    std::string transcript;
    std::vector<int16_t> samples;
    int sample_rate = 16000;
    int channels = 1;
    int duration_seconds = 0;
    bool used_realtime_stt = false;
    std::string fallback_reason;
};

RealtimeCaptureResult CaptureSpeechWithRealtime(
    interview::services::RealtimeClient& rt_client,
    const RealtimeCaptureOptions& options);

} // namespace ielts
