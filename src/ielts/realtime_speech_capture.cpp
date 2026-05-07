#include "ielts/realtime_speech_capture.h"

#include "common/config.h"
#include "common/logger.h"
#include "common/protocol.h"
#include "services/audio_manager.h"
#include "services/realtime_client.h"

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <iostream>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/select.h>
#include <thread>
#include <unistd.h>

namespace ielts {

namespace {

bool EnterPressed() {
    fd_set read_fds;
    FD_ZERO(&read_fds);
    FD_SET(STDIN_FILENO, &read_fds);
    timeval timeout{};
    timeout.tv_sec = 0;
    timeout.tv_usec = 0;
    if (select(STDIN_FILENO + 1, &read_fds, nullptr, nullptr, &timeout) > 0) {
        std::string discard;
        std::getline(std::cin, discard);
        return true;
    }
    return false;
}

std::string ProgressBar(int elapsed, int total, int width = 24) {
    const int filled = total <= 0 ? width : (std::min(elapsed, total) * width / total);
    std::string bar = "[";
    for (int i = 0; i < width; ++i) {
        bar += i < filled ? '#' : '-';
    }
    bar += "]";
    return bar;
}

std::string JoinSegments(const std::vector<std::string>& segments) {
    std::ostringstream joined;
    for (const auto& segment : segments) {
        if (segment.empty()) {
            continue;
        }
        if (joined.tellp() > 0) {
            joined << ' ';
        }
        joined << segment;
    }
    return joined.str();
}

struct CaptureState {
    std::mutex mutex;
    std::condition_variable cv;
    std::vector<std::string> final_segments;
    std::string latest_interim;
    bool saw_final = false;
};

void AddFinalSegment(CaptureState& state, const std::string& text) {
    if (text.empty()) {
        return;
    }
    if (!state.final_segments.empty() && state.final_segments.back() == text) {
        return;
    }
    state.final_segments.push_back(text);
    state.saw_final = true;
}

void HandleAsrPayload(CaptureState& state, const nlohmann::json& payload) {
    std::lock_guard<std::mutex> lock(state.mutex);

    const auto handle_result = [&](const nlohmann::json& result) {
        if (!result.is_object()) {
            return;
        }
        const std::string text = result.value("text", std::string());
        if (text.empty()) {
            return;
        }
        const bool is_final = !result.value("is_interim", true);
        if (is_final) {
            AddFinalSegment(state, text);
        } else {
            state.latest_interim = text;
        }
    };

    if (payload.contains("results") && payload["results"].is_array()) {
        for (const auto& result : payload["results"]) {
            handle_result(result);
        }
    } else if (payload.contains("text")) {
        const bool is_final = !payload.value("is_interim", true);
        const std::string text = payload.value("text", std::string());
        if (is_final) {
            AddFinalSegment(state, text);
        } else {
            state.latest_interim = text;
        }
    }

    state.cv.notify_all();
}

std::string CurrentTranscript(CaptureState& state) {
    std::lock_guard<std::mutex> lock(state.mutex);
    const std::string final_text = JoinSegments(state.final_segments);
    return final_text.empty() ? state.latest_interim : final_text;
}

bool HasFinal(CaptureState& state) {
    std::lock_guard<std::mutex> lock(state.mutex);
    return state.saw_final;
}

void WaitBrieflyForFinal(CaptureState& state) {
    std::unique_lock<std::mutex> lock(state.mutex);
    state.cv.wait_for(lock, std::chrono::milliseconds(1500), [&state]() {
        return state.saw_final;
    });
}

std::vector<uint8_t> ToBytes(const std::vector<int16_t>& samples) {
    std::vector<uint8_t> bytes(samples.size() * sizeof(int16_t));
    if (!bytes.empty()) {
        std::memcpy(bytes.data(), samples.data(), bytes.size());
    }
    return bytes;
}

} // namespace

RealtimeCaptureResult CaptureSpeechWithRealtime(
    interview::services::RealtimeClient& rt_client,
    const RealtimeCaptureOptions& options) {
    RealtimeCaptureResult result;

    auto& cfg = interview::common::Config::Instance();
    result.sample_rate = cfg.input_audio_config.sample_rate;
    result.channels = cfg.input_audio_config.channels;

    const bool realtime_connected = rt_client.IsConnected();
    if (!realtime_connected && !options.record_audio_without_realtime) {
        result.fallback_reason = "Realtime service is not connected";
        return result;
    }

    auto state = std::make_shared<CaptureState>();
    if (realtime_connected) {
        rt_client.SetResponseCallback([state](const interview::common::ParsedResponse& response) {
            if ((response.message_type == "SERVER_FULL_RESPONSE" ||
                 response.message_type == "SERVER_ACK") &&
                response.event == interview::common::events::ASR_RESULT &&
                !response.payload.empty()) {
                HandleAsrPayload(*state, response.payload);
            }
        });
    }

    const auto start = std::chrono::steady_clock::now();
    bool realtime_send_failed = !realtime_connected;

    try {
        interview::services::AudioDeviceManager audio(cfg.input_audio_config, cfg.output_audio_config);
        audio.OpenInputStream();

        while (true) {
            const int elapsed = static_cast<int>(
                std::chrono::duration_cast<std::chrono::seconds>(
                    std::chrono::steady_clock::now() - start).count());
            std::cout << "\r" << options.status_label << "... "
                      << ProgressBar(elapsed, options.max_seconds)
                      << " " << elapsed << " / " << options.max_seconds << "s "
                      << std::flush;

            if (elapsed >= options.max_seconds ||
                (options.allow_enter_stop && elapsed > 0 && EnterPressed())) {
                break;
            }

            auto chunk = audio.ReadAudio();
            result.samples.insert(result.samples.end(), chunk.begin(), chunk.end());

            if (!realtime_send_failed) {
                try {
                    rt_client.SendAudioData(ToBytes(chunk));
                } catch (const std::exception& e) {
                    realtime_send_failed = true;
                    result.fallback_reason = e.what();
                    LOG_WARNING("Realtime STT audio send failed, continuing local recording: {}", e.what());
                }
            }

            if (options.stop_on_first_final && HasFinal(*state)) {
                break;
            }

            std::this_thread::sleep_for(interview::common::timing::AUDIO_SEND_INTERVAL);
        }

        audio.Cleanup();
    } catch (const std::exception& e) {
        result.fallback_reason = e.what();
        LOG_WARNING("Realtime speech capture failed: {}", e.what());
    }

    result.duration_seconds = static_cast<int>(
        std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - start).count());

    if (realtime_connected && !realtime_send_failed) {
        WaitBrieflyForFinal(*state);
        result.transcript = CurrentTranscript(*state);
        result.used_realtime_stt = !result.transcript.empty();
        if (!result.used_realtime_stt && result.fallback_reason.empty()) {
            result.fallback_reason = "Realtime STT returned no transcript";
        }
    } else if (result.fallback_reason.empty()) {
        result.fallback_reason = "Realtime service is not connected";
    }

    std::cout << "\n";
    return result;
}

std::string CaptureAnswerOrFallback(interview::services::RealtimeClient& client,
                                    const std::string& fallback_prompt,
                                    int max_seconds) {
    RealtimeCaptureOptions options;
    options.max_seconds = max_seconds;
    options.stop_on_first_final = true;
    options.allow_enter_stop = true;
    options.record_audio_without_realtime = false;
    options.status_label = "Listening for answer";

    const auto capture = CaptureSpeechWithRealtime(client, options);
    if (capture.used_realtime_stt) {
        std::cout << "\033[2mTranscript:\033[0m " << capture.transcript << "\n";
        return capture.transcript;
    }

    if (!capture.fallback_reason.empty()) {
        LOG_WARNING("Realtime STT unavailable, using terminal transcript: {}", capture.fallback_reason);
    }

    std::cout << fallback_prompt << "\n> ";
    std::string answer;
    std::getline(std::cin, answer);
    return answer;
}

} // namespace ielts
