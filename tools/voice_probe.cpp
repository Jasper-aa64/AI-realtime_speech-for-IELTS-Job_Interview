// voice_probe：开发用命令行，直接驱动 VoiceSession 连真实服务，用于验收计时。
//
//   voice_probe --config ~/.ielts-studio/realtime_voice.json \
//       [--method auto|say_hello|chat_tts_text|prompt] [--half-duplex keep_alive|silence] \
//       [--smooth 2000] [--rounds 5] [--listen-seconds 20] [--answer "say 的文本"] [--voice Tingting] \
//       [--duration-seconds 600] [--no-listen]
//
// 每轮：念第 N 题 → 播完后开始收听 →（可选）放一段 macOS say 生成的回答 →
// 等 ASR_ENDED 和最终转写（或超时）。回答两种放法（--answer-mode）：
//   inject（默认）：读真实麦克风，把 say 生成的 16 kHz 音频数字叠加进麦克风采样，房间里不出声；
//                  回答最后一个采样进入引擎的时刻记为 inject_end，可以拿来核对能量阈值判出的"停下"。
//   speaker：用 say 从扬声器外放（声音要够大服务端才识别，实测约 -20 dBFS 才行）。--duration-seconds 时一直循环到时间到，最后打印统计。
// 计时日志写到配置里 voice.metrics_dir（或 --metrics-dir）。
#include "voice/voice_session.h"
#include "common/logger.h"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <spawn.h>
#include <string>
#include <sys/wait.h>
#include <thread>
#include <vector>

extern char** environ;

using namespace interview::voice;
using Clock = std::chrono::steady_clock;

namespace {

struct Waiter {
    std::mutex mu;
    std::condition_variable cv;
    std::vector<VoiceEvent> events;

    void Push(const VoiceEvent& e) {
        {
            std::lock_guard<std::mutex> lock(mu);
            events.push_back(e);
        }
        cv.notify_all();
    }
    // 等 since 之后出现 type 之一；返回找到的事件类型，超时返回 kState
    VoiceEvent::Type WaitAny(std::size_t since, std::vector<VoiceEvent::Type> types, std::chrono::milliseconds limit) {
        std::unique_lock<std::mutex> lock(mu);
        VoiceEvent::Type found = VoiceEvent::Type::kState;
        cv.wait_for(lock, limit, [&] {
            for (std::size_t i = since; i < events.size(); ++i) {
                for (auto t : types) {
                    if (events[i].type == t) {
                        found = t;
                        return true;
                    }
                }
            }
            return false;
        });
        return found;
    }
    std::size_t Size() {
        std::lock_guard<std::mutex> lock(mu);
        return events.size();
    }
};

// 真实麦克风 + 数字叠加的回答音频。输出照常走真实设备。
class MixInDevice : public AudioDevice {
public:
    explicit MixInDevice(std::unique_ptr<AudioDevice> inner) : inner_(std::move(inner)) {}

    void Inject(std::vector<int16_t> samples) {
        std::lock_guard<std::mutex> lock(mu_);
        pending_ = std::move(samples);
        at_ = 0;
        end_at_ = Clock::time_point{};
    }
    bool Injecting() {
        std::lock_guard<std::mutex> lock(mu_);
        return at_ < pending_.size();
    }
    Clock::time_point InjectEnd() {
        std::lock_guard<std::mutex> lock(mu_);
        return end_at_;
    }

    void OpenInput(int rate, int frames) override { inner_->OpenInput(rate, frames); }
    std::size_t Read(int16_t* out, std::size_t frames) override {
        const std::size_t n = inner_->Read(out, frames);
        std::lock_guard<std::mutex> lock(mu_);
        if (at_ < pending_.size()) {
            for (std::size_t i = 0; i < n && at_ < pending_.size(); ++i, ++at_) {
                const int v = out[i] + pending_[at_];
                out[i] = static_cast<int16_t>(std::max(-32768, std::min(32767, v)));
            }
            if (at_ >= pending_.size()) end_at_ = Clock::now();
        }
        return n;
    }
    void CloseInput() override { inner_->CloseInput(); }
    void OpenOutput(int rate, int frames) override { inner_->OpenOutput(rate, frames); }
    void Write(const int16_t* samples, std::size_t frames) override { inner_->Write(samples, frames); }
    double OutputLatencySeconds() const override { return inner_->OutputLatencySeconds(); }
    std::string Describe() const override { return inner_->Describe() + " (+injected answer audio)"; }
    void CloseOutput() override { inner_->CloseOutput(); }

private:
    std::unique_ptr<AudioDevice> inner_;
    std::mutex mu_;
    std::vector<int16_t> pending_;
    std::size_t at_ = 0;
    Clock::time_point end_at_;
};

// say -o 生成 WAV（16 kHz 单声道 s16le），读出 data 块；去掉末尾的静音，回答的"停下"就是最后一个采样
std::vector<int16_t> SynthesizeAnswer(const std::string& voice, const std::string& text, double gain) {
    const std::string path = "/tmp/voice_probe_answer.wav";
    std::vector<std::string> args{"/usr/bin/say", "-o", path, "--file-format=WAVE", "--data-format=LEI16@16000"};
    if (!voice.empty()) {
        args.push_back("-v");
        args.push_back(voice);
    }
    args.push_back(text);
    std::vector<char*> argv;
    for (auto& a : args) argv.push_back(a.data());
    argv.push_back(nullptr);
    pid_t pid = 0;
    if (posix_spawn(&pid, argv[0], nullptr, nullptr, argv.data(), environ) != 0) return {};
    int status = 0;
    waitpid(pid, &status, 0);
    std::ifstream in(path, std::ios::binary);
    std::vector<char> bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    std::size_t pos = 12;
    std::vector<int16_t> samples;
    while (pos + 8 <= bytes.size()) {
        const std::string id(bytes.data() + pos, 4);
        uint32_t size = 0;
        std::memcpy(&size, bytes.data() + pos + 4, 4);
        if (id == "data") {
            const std::size_t n = std::min<std::size_t>(size, bytes.size() - pos - 8) / 2;
            samples.resize(n);
            std::memcpy(samples.data(), bytes.data() + pos + 8, n * 2);
            break;
        }
        pos += 8 + size + (size & 1);
    }
    while (!samples.empty() && std::abs(samples.back()) < 64) samples.pop_back();
    for (auto& v : samples) v = static_cast<int16_t>(v * gain);
    return samples;
}

const char* TypeName(VoiceEvent::Type t) {
    switch (t) {
    case VoiceEvent::Type::kState: return "state";
    case VoiceEvent::Type::kPartial: return "partial";
    case VoiceEvent::Type::kFinal: return "final";
    case VoiceEvent::Type::kUserStarted: return "user_started";
    case VoiceEvent::Type::kUserStopped: return "user_stopped";
    case VoiceEvent::Type::kSpeakStarted: return "speak_started";
    case VoiceEvent::Type::kSpeakFinished: return "speak_finished";
    case VoiceEvent::Type::kError: return "error";
    }
    return "?";
}

pid_t SpawnSay(const std::string& voice, const std::string& text, const std::string& device) {
    std::vector<std::string> args{"/usr/bin/say"};
    if (!device.empty()) {
        args.push_back("-a");
        args.push_back(device);
    }
    if (!voice.empty()) {
        args.push_back("-v");
        args.push_back(voice);
    }
    args.push_back(text);
    std::vector<char*> argv;
    for (auto& a : args) argv.push_back(a.data());
    argv.push_back(nullptr);
    pid_t pid = 0;
    if (posix_spawn(&pid, argv[0], nullptr, nullptr, argv.data(), environ) != 0) return 0;
    return pid;
}

} // namespace

int main(int argc, char** argv) {
    std::string config = std::string(std::getenv("HOME")) + "/.ielts-studio/realtime_voice.json";
    std::string method, half_duplex, answer, say_voice = "Tingting", metrics_dir, input_device, output_device, say_device;
    std::string custom_vad;
    double output_gain = -1;
    std::string answer_mode = "inject";
    double answer_gain = 0.5;
    int smooth = 0, rounds = 1, listen_seconds = 20, duration_seconds = 0;
    bool listen = true;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&]() -> std::string { return i + 1 < argc ? argv[++i] : ""; };
        if (a == "--config") config = next();
        else if (a == "--method") method = next();
        else if (a == "--half-duplex") half_duplex = next();
        else if (a == "--smooth") smooth = std::atoi(next().c_str());
        else if (a == "--rounds") rounds = std::atoi(next().c_str());
        else if (a == "--listen-seconds") listen_seconds = std::atoi(next().c_str());
        else if (a == "--answer") answer = next();
        else if (a == "--voice") say_voice = next();
        else if (a == "--say-device") say_device = next();
        else if (a == "--metrics-dir") metrics_dir = next();
        else if (a == "--duration-seconds") duration_seconds = std::atoi(next().c_str());
        else if (a == "--no-listen") listen = false;
        else if (a == "--custom-vad") custom_vad = next();
        else if (a == "--output-gain") output_gain = std::atof(next().c_str());
        else if (a == "--answer-mode") answer_mode = next();
        else if (a == "--answer-gain") answer_gain = std::atof(next().c_str());
        else if (a == "--input-device") input_device = next();
        else if (a == "--output-device") output_device = next();
        else {
            std::cerr << "unknown argument " << a << "\n";
            return 2;
        }
    }
    interview::common::Logger::Init("/tmp/voice_probe.log", false);

    VoiceOptions o;
    try {
        o = LoadVoiceOptions(config);
    } catch (const std::exception& e) {
        std::cerr << "config: " << e.what() << "\n";
        return 2;
    }
    if (!method.empty() && !ParseSpeakMethod(method, &o.speak_method)) {
        std::cerr << "bad --method\n";
        return 2;
    }
    if (half_duplex == "silence") o.half_duplex = HalfDuplexMode::kSilence;
    if (half_duplex == "keep_alive") o.half_duplex = HalfDuplexMode::kKeepAlive;
    if (smooth > 0) o.end_smooth_window_ms = smooth;
    if (output_gain >= 0) o.output_gain = output_gain;
    if (custom_vad == "on") o.enable_custom_vad = true;
    if (custom_vad == "off") o.enable_custom_vad = false;
    if (!metrics_dir.empty()) o.metrics_dir = metrics_dir;
    if (!input_device.empty()) o.input_device = input_device;
    if (!output_device.empty()) o.output_device = output_device;

    Waiter w;
    const auto t0 = Clock::now();
    MixInDevice* mixer = nullptr;
    std::unique_ptr<AudioDevice> device = CreatePortAudioDevice(o.input_device, o.output_device);
    std::vector<int16_t> answer_pcm;
    if (!answer.empty() && answer_mode == "inject") {
        answer_pcm = SynthesizeAnswer(say_voice, answer, answer_gain);
        std::printf("injected answer: %.2f s of audio, gain %.2f\n", answer_pcm.size() / 16000.0, answer_gain);
        auto mix = std::make_unique<MixInDevice>(std::move(device));
        mixer = mix.get();
        device = std::move(mix);
    }
    VoiceSession session(o, std::move(device));
    session.SetListener([&](const VoiceEvent& e) {
        std::printf("[%7lld] %-14s state=%-10s %s%s%s\n", static_cast<long long>(e.at_ms), TypeName(e.type),
                    ToString(e.state), e.code.empty() ? "" : ("code=" + e.code + " ").c_str(), e.text.c_str(), "");
        std::fflush(stdout);
        w.Push(e);
    });
    std::printf("config=%s method=%s half_duplex=%s smooth=%d custom_vad=%d model=%s\n", config.c_str(),
                ToString(o.speak_method), ToString(o.half_duplex), o.end_smooth_window_ms, o.enable_custom_vad ? 1 : 0,
                o.model.c_str());
    session.Start();
    if (w.WaitAny(0, {VoiceEvent::Type::kError}, std::chrono::milliseconds(0)) == VoiceEvent::Type::kError) return 1;
    {
        std::unique_lock<std::mutex> lock(w.mu);
        w.cv.wait_for(lock, std::chrono::seconds(20), [&] {
            return session.state() == VoiceState::kReady || session.state() == VoiceState::kError;
        });
    }
    if (session.state() != VoiceState::kReady) {
        std::printf("START FAILED state=%s\n", ToString(session.state()));
        session.Stop();
        return 1;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(300));  // 底噪 1 s 已经在连接期间取完

    const std::vector<std::string> questions = {
        "请先做一个简短的自我介绍。",
        "介绍一个你最有代表性的项目，你在里面负责什么？",
        "这个项目里遇到的最大技术难点是什么，你是怎么解决的？",
        "说说 C++ 里智能指针的种类和各自的使用场景。",
        "如果线上服务延迟突然升高，你会怎么排查？",
        "你为什么想加入我们团队？",
    };
    int round = 0;
    for (;;) {
        ++round;
        if (duration_seconds > 0) {
            if (Clock::now() - t0 > std::chrono::seconds(duration_seconds)) break;
        } else if (round > rounds) {
            break;
        }
        const std::string q = "第" + std::to_string(round) + "题。" + questions[(round - 1) % questions.size()];
        std::printf("---- round %d: speak\n", round);
        auto since = w.Size();
        session.Speak(q);
        auto got = w.WaitAny(since, {VoiceEvent::Type::kSpeakFinished, VoiceEvent::Type::kError}, std::chrono::seconds(40));
        if (got != VoiceEvent::Type::kSpeakFinished) {
            std::printf("round %d: speak did not finish (%s)\n", round, TypeName(got));
            if (session.state() == VoiceState::kError) break;
            continue;
        }
        if (!listen) continue;
        since = w.Size();
        session.StartListening();
        pid_t say = 0;
        const auto listen_at = Clock::now();
        if (!answer.empty()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(300));
            if (mixer) mixer->Inject(answer_pcm);
            else say = SpawnSay(say_voice, answer, say_device);
        }
        got = w.WaitAny(since, {VoiceEvent::Type::kUserStopped, VoiceEvent::Type::kError},
                        std::chrono::seconds(listen_seconds));
        bool premature = false;
        if (mixer) {
            premature = got == VoiceEvent::Type::kUserStopped && mixer->Injecting();
            if (premature) std::printf("round %d: PREMATURE asr_ended while the answer is still being injected\n", round);
            while (mixer->Injecting()) std::this_thread::sleep_for(std::chrono::milliseconds(20));
            const auto end = mixer->InjectEnd();
            std::printf("round %d: inject_end_ms_after_listen=%.0f\n", round,
                        std::chrono::duration<double, std::milli>(end - listen_at).count());
        }
        if (say > 0) {
            int status = 0;
            // 服务端判定说完时 say 还在念：正常停顿被当成了说完
            premature = got == VoiceEvent::Type::kUserStopped && waitpid(say, &status, WNOHANG) == 0;
            if (premature) std::printf("round %d: PREMATURE asr_ended while the answer is still being spoken\n", round);
            if (!premature || waitpid(say, &status, WNOHANG) == 0) waitpid(say, &status, 0);
        }
        if (got != VoiceEvent::Type::kUserStopped) {
            std::printf("round %d: no ASR_ENDED within %d s (%s), stopping listen\n", round, listen_seconds, TypeName(got));
            session.StopListening();
            if (session.state() == VoiceState::kError) break;
        }
        // 等最终转写（459 和最终 451 谁先到都行），再模拟"网页显示"
        w.WaitAny(since, {VoiceEvent::Type::kFinal}, std::chrono::seconds(5));
        std::string note = "probe-round-" + std::to_string(round) + (premature ? "-premature" : "");
        if (mixer) {
            // 引擎按收到这条标记的时刻记 t_ms；inject_end_ago_ms 让分析脚本换算出回答结束的时刻
            note += " inject_end_ago_ms=" + std::to_string(static_cast<long long>(
                std::chrono::duration<double, std::milli>(Clock::now() - mixer->InjectEnd()).count()));
        }
        session.MarkTranscriptShown(note);
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
    }
    const auto stats = session.GetStats();
    session.Stop();
    std::printf("STATS audio_frames_sent=%llu dropped=%llu control=%llu mic_packets=%llu playback_max_chunks=%zu "
                "playback_dropped=%llu disconnects=%llu elapsed_s=%.1f\n",
                static_cast<unsigned long long>(stats.audio_frames_sent),
                static_cast<unsigned long long>(stats.audio_frames_dropped),
                static_cast<unsigned long long>(stats.control_frames_sent),
                static_cast<unsigned long long>(stats.mic_packets), stats.playback_queue_max_chunks,
                static_cast<unsigned long long>(stats.playback_chunks_dropped),
                static_cast<unsigned long long>(stats.disconnects),
                std::chrono::duration<double>(Clock::now() - t0).count());
    return 0;
}
