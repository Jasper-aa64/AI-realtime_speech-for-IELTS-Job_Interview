#include "ielts/part2_session.h"

#include "common/logger.h"
#include "ielts/realtime_speech_capture.h"
#include "services/realtime_client.h"
#include <chrono>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/select.h>
#include <thread>
#include <unistd.h>
#include <vector>

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
    const int filled = total <= 0 ? width : (elapsed * width / total);
    std::string bar = "[";
    for (int i = 0; i < width; ++i) {
        bar += i < filled ? '#' : '-';
    }
    bar += "]";
    return bar;
}

std::string TimestampForFilename() {
    auto now = std::time(nullptr);
    std::tm tm{};
    localtime_r(&now, &tm);
    std::ostringstream oss;
    oss << std::put_time(&tm, "%Y%m%d_%H%M%S");
    return oss.str();
}

void WritePcmWav(const std::filesystem::path& path,
                 const std::vector<int16_t>& samples,
                 int sample_rate,
                 int channels) {
    std::filesystem::create_directories(path.parent_path());
    constexpr int bits_per_sample = 16;
    const int data_bytes = static_cast<int>(samples.size() * sizeof(int16_t));
    const int byte_rate = sample_rate * channels * bits_per_sample / 8;
    const short block_align = channels * bits_per_sample / 8;

    std::ofstream out(path, std::ios::binary);
    if (!out) {
        throw std::runtime_error("Failed to write WAV recording: " + path.string());
    }

    out.write("RIFF", 4);
    int chunk_size = 36 + data_bytes;
    out.write(reinterpret_cast<const char*>(&chunk_size), 4);
    out.write("WAVEfmt ", 8);
    int subchunk1_size = 16;
    short audio_format = 1;
    out.write(reinterpret_cast<const char*>(&subchunk1_size), 4);
    out.write(reinterpret_cast<const char*>(&audio_format), 2);
    out.write(reinterpret_cast<const char*>(&channels), 2);
    out.write(reinterpret_cast<const char*>(&sample_rate), 4);
    out.write(reinterpret_cast<const char*>(&byte_rate), 4);
    out.write(reinterpret_cast<const char*>(&block_align), 2);
    out.write(reinterpret_cast<const char*>(&bits_per_sample), 2);
    out.write("data", 4);
    out.write(reinterpret_cast<const char*>(&data_bytes), 4);
    out.write(reinterpret_cast<const char*>(samples.data()), data_bytes);
}

void SafeSpeak(interview::services::RealtimeClient& client, const std::string& text) {
    try {
        client.SendTextQuery(text);
    } catch (const std::exception& e) {
        LOG_WARNING("IELTS TTS prompt failed, continuing with terminal text: {}", e.what());
    }
}

} // namespace

Part2Session::Part2Session(QuestionBank& bank,
                           interview::services::RealtimeClient& rt_client,
                           Scorer& scorer,
                           const std::string& reports_dir,
                           int prep_seconds,
                           int speak_seconds)
    : bank_(bank)
    , rt_client_(rt_client)
    , scorer_(scorer)
    , reports_dir_(reports_dir)
    , prep_seconds_(prep_seconds)
    , speak_seconds_(speak_seconds) {}

void Part2Session::Start() {
    topic_ = bank_.SampleP2Topic();
    transcript_.clear();
    actual_duration_ = 0;

    ShowCueCard(topic_);
    SafeSpeak(rt_client_, "IELTS Speaking Part 2. " + topic_.title);

    std::cout << "\nCue card displayed. Press [Enter] when you are ready to start your 1-minute preparation time.\n";
    std::cout << "> ";
    std::string discard;
    std::getline(std::cin, discard);

    RunCountdown(prep_seconds_);
    RecordSpeech(speak_seconds_);

    score_ = scorer_.Score(transcript_);
}

IELTSScore Part2Session::GetScore() const {
    return score_;
}

P2Topic Part2Session::GetTopic() const {
    return topic_;
}

std::string Part2Session::GetTranscript() const {
    return transcript_;
}

int Part2Session::GetActualDuration() const {
    return actual_duration_;
}

void Part2Session::ShowCueCard(const P2Topic& topic) const {
    std::cout << "\n\033[1;36mIELTS Speaking - Part 2\033[0m\n";
    std::cout << "========================================\n";
    std::cout << topic.title << "\n\n";
    std::cout << "You should say:\n";
    for (const auto& bullet : topic.bullets) {
        std::cout << "  - " << bullet << "\n";
    }
    if (!topic.rounding.empty()) {
        std::cout << "\n" << topic.rounding << "\n";
    }
    std::cout << "========================================\n";
}

void Part2Session::RunCountdown(int seconds) {
    std::cout << "\nPreparation time. Press Enter to start speaking early.\n";
    for (int elapsed = 0; elapsed < seconds; ++elapsed) {
        const int remaining = seconds - elapsed;
        std::cout << "\r" << ProgressBar(elapsed, seconds) << " " << remaining << "s remaining " << std::flush;
        if (EnterPressed()) {
            break;
        }
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    std::cout << "\r" << ProgressBar(seconds, seconds) << " 0s remaining     \n";
}

void Part2Session::RecordSpeech(int max_seconds) {
    std::cout << "\nRecording window started. Press Enter to stop early.\n";

    RealtimeCaptureOptions options;
    options.max_seconds = max_seconds;
    options.stop_on_first_final = false;
    options.allow_enter_stop = true;
    options.record_audio_without_realtime = true;
    options.status_label = "Recording";

    const auto capture = CaptureSpeechWithRealtime(rt_client_, options);
    actual_duration_ = capture.duration_seconds;
    transcript_ = capture.transcript;

    if (capture.used_realtime_stt) {
        std::cout << "\033[2mRealtime transcript:\033[0m " << transcript_ << "\n";
    } else {
        if (!capture.fallback_reason.empty()) {
            LOG_WARNING("P2 realtime STT unavailable, using terminal transcript: {}", capture.fallback_reason);
        }
        std::cout << "Paste or type the final Part 2 transcript, then press Enter:\n> ";
        std::getline(std::cin, transcript_);
    }

    auto recorded_samples = capture.samples;
    if (recorded_samples.empty()) {
        recorded_samples.assign(static_cast<size_t>(std::max(1, actual_duration_) * capture.sample_rate * capture.channels), 0);
    }

    WritePcmWav(std::filesystem::path(reports_dir_) / ("ielts_part2_" + TimestampForFilename() + ".wav"),
                recorded_samples,
                capture.sample_rate,
                capture.channels);
}

} // namespace ielts
