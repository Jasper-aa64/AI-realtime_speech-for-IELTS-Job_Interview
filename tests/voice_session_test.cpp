// VoiceSession 测试：假 TLS 服务端（tests/fake_realtime_server.h）按脚本回 TTS / ASR 事件，
// 假音频设备代替麦克风和扬声器。不连真实服务、不用真麦克风。
#include <gtest/gtest.h>

#include "voice/voice_session.h"
#include "common/logger.h"
#include "fake_realtime_server.h"

#include <cmath>
#include <condition_variable>
#include <deque>

using namespace fake_realtime;
using interview::voice::AudioDevice;
using interview::voice::HalfDuplexMode;
using interview::voice::SpeakMethod;
using interview::voice::VoiceEvent;
using interview::voice::VoiceOptions;
using interview::voice::VoiceSession;
using interview::voice::VoiceState;

namespace {

using Clock = std::chrono::steady_clock;
using Type = VoiceEvent::Type;

// 20 ms 一包的假麦克风：voiced 为 true 时给 0.25 幅度的正弦，否则给很小的底噪
class FakeAudioDevice : public AudioDevice {
public:
    struct Shared {
        std::atomic<bool> voiced{false};
        std::atomic<int> write_delay_ms{1};
        std::atomic<std::uint64_t> frames_written{0};
        std::atomic<std::uint64_t> packets_read{0};
        std::atomic<bool> input_open{false};
        std::atomic<bool> output_open{false};
        std::atomic<int> read_frames{0};
    };

    explicit FakeAudioDevice(std::shared_ptr<Shared> shared) : s_(std::move(shared)) {}

    void OpenInput(int, int frames) override {
        s_->read_frames = frames;
        s_->input_open = true;
        next_ = std::chrono::steady_clock::now();
    }
    std::size_t Read(int16_t* out, std::size_t frames) override {
        if (!s_->input_open) return 0;
        // 和硬件一样按固定节拍出包，不随调度抖动累积误差
        next_ += std::chrono::milliseconds(20);
        std::this_thread::sleep_until(next_);
        const bool voiced = s_->voiced.load();
        for (std::size_t i = 0; i < frames; ++i) {
            const double v = voiced ? 0.25 * std::sin(2 * M_PI * 440.0 * double(phase_++) / 16000.0)
                                    : (static_cast<int>(phase_++ % 7) - 3) / 32768.0 * 4;
            out[i] = static_cast<int16_t>(v * 32767);
        }
        ++s_->packets_read;
        return frames;
    }
    void CloseInput() override { s_->input_open = false; }
    void OpenOutput(int, int) override { s_->output_open = true; }
    void Write(const int16_t*, std::size_t frames) override {
        std::this_thread::sleep_for(std::chrono::milliseconds(s_->write_delay_ms.load()));
        s_->frames_written += frames;
    }
    void CloseOutput() override { s_->output_open = false; }

private:
    std::shared_ptr<Shared> s_;
    std::uint64_t phase_ = 0;
    std::chrono::steady_clock::time_point next_;
};

// 按火山文档的事件顺序回放：TTS（350 → 352… → 359）、ASR（450 → 451 中间 → 459 → 451 最终），
// 并在 459 之后模拟模型自己接话（tts_type=default 的一轮 TTS）。
struct Script {
    int tts_chunks = 3;                    // 每次念题回几块音频
    std::size_t tts_chunk_bytes = 4800;    // 100 ms @ 24 kHz s16
    bool send_tts = true;
    bool reject_chat_tts_before_asr_end = true;
    int asr_first_after = 5;               // 收听后第几包音频回 450
    int asr_end_after = 25;                // 第几包回 459
    bool model_replies_after_asr = true;

    // 记录
    std::mutex mu;
    std::vector<uint32_t> speak_events;
    std::vector<std::size_t> audio_sizes;
    std::atomic<int> audio_frames{0};
    std::atomic<int> nonzero_audio_frames{0};
    std::atomic<int> errors_sent{0};
    int listen_frames = 0;
    bool asr_ended = false;
    int reply = 0;
};

void SendTts(const std::string& sid, const std::string& type, Script& sc, const SendToClient& send) {
    const std::string reply = "r" + std::to_string(++sc.reply);
    send(ServerFrame(events::TTS_START, sid, nlohmann::json{{"tts_type", type}, {"reply_id", reply}, {"text", "x"}}.dump()));
    for (int i = 0; i < sc.tts_chunks; ++i) {
        send(ServerAudioFrame(sid, std::vector<uint8_t>(sc.tts_chunk_bytes, 1)));
    }
    send(ServerFrame(events::TTS_SENTENCE_END, sid, nlohmann::json{{"reply_id", reply}}.dump()));
    send(ServerFrame(events::TTS_END, sid, nlohmann::json{{"reply_id", reply}}.dump()));
}

ServerBehavior Scripted(Script& sc) {
    ServerBehavior b;
    b.on_frame = [&sc](const ClientFrame& f, const std::string& sid, const SendToClient& send) {
        if (f.event == events::SAY_HELLO || f.event == events::CHAT_TTS_TEXT || f.event == events::CHAT_TEXT_QUERY) {
            const auto payload = nlohmann::json::parse(f.payload.begin(), f.payload.end());
            if (f.event == events::CHAT_TTS_TEXT && !payload.value("end", false)) return;  // 等 end 包
            {
                std::lock_guard<std::mutex> lock(sc.mu);
                sc.speak_events.push_back(f.event);
            }
            if (f.event == events::CHAT_TTS_TEXT && sc.reject_chat_tts_before_asr_end && !sc.asr_ended) {
                ++sc.errors_sent;
                send(ServerFrame(events::DIALOG_COMMON_ERROR, sid, R"({"status_code":"45000001","message":"chat tts before asr ended"})"));
                return;
            }
            sc.asr_ended = false;
            sc.listen_frames = 0;
            if (sc.send_tts) SendTts(sid, f.event == events::CHAT_TTS_TEXT ? "chat_tts_text" : "default", sc, send);
            return;
        }
        if (f.event != events::TASK_REQUEST) return;
        ++sc.audio_frames;
        bool nonzero = false;
        for (auto b : f.payload) nonzero |= (b != 0);
        if (nonzero) ++sc.nonzero_audio_frames;
        {
            std::lock_guard<std::mutex> lock(sc.mu);
            sc.audio_sizes.push_back(f.payload.size());
        }
        if (!nonzero || sc.asr_ended) return;  // 静音不触发识别
        const int n = ++sc.listen_frames;
        if (n == sc.asr_first_after) {
            send(ServerFrame(events::USER_START_SPEAKING, sid, R"({"question_id":"q"})"));
        }
        if (n > sc.asr_first_after && n < sc.asr_end_after && n % 4 == 0) {
            send(ServerFrame(events::ASR_RESULT, sid,
                             nlohmann::json{{"results", {{{"text", "我觉得" + std::to_string(n)}, {"is_interim", true}}}}}.dump()));
        }
        if (n == sc.asr_end_after) {
            sc.asr_ended = true;
            send(ServerFrame(events::USER_STOP_SPEAKING, sid, "{}"));
            send(ServerFrame(events::ASR_RESULT, sid,
                             nlohmann::json{{"results", {{{"text", "我觉得是这样"}, {"is_interim", false}}}}}.dump()));
            if (sc.model_replies_after_asr) SendTts(sid, "default", sc, send);
        }
    };
    return b;
}

class Recorder {
public:
    void operator()(const VoiceEvent& e) {
        {
            std::lock_guard<std::mutex> lock(mu_);
            events_.push_back(e);
        }
        cv_.notify_all();
    }
    // 等第 nth 个（从 1 数）该类型的事件
    bool Wait(Type type, int nth = 1, std::chrono::milliseconds limit = std::chrono::milliseconds(5000)) {
        std::unique_lock<std::mutex> lock(mu_);
        return cv_.wait_for(lock, limit, [&] { return Count(type) >= nth; });
    }
    bool WaitState(VoiceState state, std::chrono::milliseconds limit = std::chrono::milliseconds(5000)) {
        std::unique_lock<std::mutex> lock(mu_);
        return cv_.wait_for(lock, limit, [&] {
            for (const auto& e : events_) if (e.type == Type::kState && e.state == state) return true;
            return false;
        });
    }
    int CountLocked(Type type) {
        std::lock_guard<std::mutex> lock(mu_);
        return Count(type);
    }
    std::vector<VoiceEvent> All() {
        std::lock_guard<std::mutex> lock(mu_);
        return events_;
    }
    VoiceEvent Last(Type type) {
        std::lock_guard<std::mutex> lock(mu_);
        for (auto it = events_.rbegin(); it != events_.rend(); ++it) if (it->type == type) return *it;
        return {};
    }

private:
    int Count(Type type) const {
        int n = 0;
        for (const auto& e : events_) n += e.type == type;
        return n;
    }
    std::mutex mu_;
    std::condition_variable cv_;
    std::vector<VoiceEvent> events_;
};

VoiceOptions TestOptions(unsigned short port) {
    VoiceOptions o;
    o.url = Url(port);
    o.headers = {{"X-Api-App-ID", "test"}, {"X-Api-Access-Key", "test"}};
    o.ca_file = CaFile();
    o.connect_timeout = std::chrono::milliseconds(5000);
    o.stop_timeout = std::chrono::milliseconds(2000);
    o.speak_start_timeout = std::chrono::milliseconds(2000);
    o.noise_floor_packets = 5;
    return o;
}

struct Harness {
    std::shared_ptr<FakeAudioDevice::Shared> dev = std::make_shared<FakeAudioDevice::Shared>();
    Recorder rec;
    std::unique_ptr<VoiceSession> session;

    void Make(VoiceOptions o) {
        session = std::make_unique<VoiceSession>(std::move(o), std::make_unique<FakeAudioDevice>(dev));
        session->SetListener([this](const VoiceEvent& e) { rec(e); });
    }
};

} // namespace

// 念题和收听交替 5 轮：状态流转、第一题 SayHello 之后 ChatTTSText、半双工、模型自己接的话不播
TEST(VoiceSessionTest, FiveRoundsOfSpeakThenListen) {
    Script sc;
    FakeServer server(Scripted(sc));
    Harness h;
    h.Make(TestOptions(server.port()));
    h.session->Start();
    ASSERT_TRUE(h.rec.WaitState(VoiceState::kReady));

    const auto session_frame = server.Frames()[1];
    const auto start_session = nlohmann::json::parse(session_frame.payload.begin(), session_frame.payload.end());
    EXPECT_EQ(start_session["dialog"]["extra"]["input_mod"], "keep_alive");
    EXPECT_EQ(start_session["dialog"]["extra"]["model"], "1.2.1.1");
    EXPECT_EQ(start_session["tts"]["audio_config"]["format"], "pcm_s16le");

    for (int round = 1; round <= 5; ++round) {
        h.session->Speak("第" + std::to_string(round) + "题");
        ASSERT_TRUE(h.rec.Wait(Type::kSpeakStarted, round)) << round;
        const int audio_at_speak = sc.audio_frames.load();
        ASSERT_TRUE(h.rec.Wait(Type::kSpeakFinished, round)) << round;
        // 半双工：AI 说话期间一包都不上传
        EXPECT_EQ(sc.audio_frames.load(), audio_at_speak) << round;
        EXPECT_EQ(h.session->state(), VoiceState::kReady);

        h.dev->voiced = true;
        h.session->StartListening();
        ASSERT_TRUE(h.rec.Wait(Type::kUserStopped, round)) << round;
        h.dev->voiced = false;
        ASSERT_TRUE(h.rec.Wait(Type::kFinal, round)) << round;
        EXPECT_EQ(h.rec.Last(Type::kFinal).text, "我觉得是这样");
    }
    // 留一点时间让最后一轮模型自己接的话到达
    std::this_thread::sleep_for(std::chrono::milliseconds(300));
    EXPECT_GE(h.rec.CountLocked(Type::kPartial), 5);
    EXPECT_EQ(h.rec.CountLocked(Type::kUserStarted), 5);

    {
        std::lock_guard<std::mutex> lock(sc.mu);
        ASSERT_EQ(sc.speak_events.size(), 5u);
        EXPECT_EQ(sc.speak_events[0], events::SAY_HELLO);
        for (size_t i = 1; i < 5; ++i) EXPECT_EQ(sc.speak_events[i], events::CHAT_TTS_TEXT) << i;
        for (auto size : sc.audio_sizes) EXPECT_EQ(size, 640u);  // 20 ms 一包
    }
    EXPECT_EQ(sc.errors_sent.load(), 0);
    // 只播了 5 次念题的音频；模型每轮之后自己接的那段（default）没播
    EXPECT_EQ(h.dev->frames_written.load(), 5u * 3u * 2400u);

    const auto t0 = Clock::now();
    h.session->Stop();
    EXPECT_LT(std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - t0).count(), 2500);
    EXPECT_EQ(h.session->state(), VoiceState::kClosed);
    EXPECT_FALSE(h.dev->input_open.load());
    const auto stats = h.session->GetStats();
    EXPECT_GT(stats.audio_frames_sent, 0u);
    EXPECT_EQ(stats.audio_frames_dropped, 0u);
    EXPECT_EQ(stats.disconnects, 0u);
}

// ChatTTSText 在 ASR_ENDED 之前会被拒：auto 模式不会这样发；强制用 ChatTTSText 时错误照实报出来
TEST(VoiceSessionTest, ChatTtsTextBeforeAsrEndedReportsServerError) {
    Script sc;
    FakeServer server(Scripted(sc));
    Harness h;
    auto o = TestOptions(server.port());
    o.speak_method = SpeakMethod::kChatTTSText;
    h.Make(o);
    h.session->Start();
    ASSERT_TRUE(h.rec.WaitState(VoiceState::kReady));
    h.session->Speak("第一题");
    ASSERT_TRUE(h.rec.Wait(Type::kError));
    EXPECT_EQ(h.rec.Last(Type::kError).code, "45000001");
    EXPECT_NE(h.rec.Last(Type::kError).text.find("chat tts before asr ended"), std::string::npos);
    h.session->Stop();
}

// 服务端一直不给 TTS：在 speak_start_timeout 内报 speak_timeout，回到 ready，页面不会一直等
TEST(VoiceSessionTest, SpeakTimesOutWhenNoTtsArrives) {
    Script sc;
    sc.send_tts = false;
    FakeServer server(Scripted(sc));
    Harness h;
    auto o = TestOptions(server.port());
    o.speak_start_timeout = std::chrono::milliseconds(300);
    h.Make(o);
    h.session->Start();
    ASSERT_TRUE(h.rec.WaitState(VoiceState::kReady));
    const auto t0 = Clock::now();
    h.session->Speak("第一题");
    ASSERT_TRUE(h.rec.Wait(Type::kError, 1, std::chrono::milliseconds(2000)));
    EXPECT_EQ(h.rec.Last(Type::kError).code, "speak_timeout");
    EXPECT_LT(std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - t0).count(), 1000);
    EXPECT_EQ(h.session->state(), VoiceState::kReady);
    h.session->Stop();
}

// 播放队列有上限：设备写得慢、服务端一次给 4 秒音频，队列深度不超过上限，超出的丢最旧的；停止时清空
TEST(VoiceSessionTest, PlaybackQueueIsBoundedAndClearedOnStop) {
    Script sc;
    sc.tts_chunks = 40;  // 4 s
    FakeServer server(Scripted(sc));
    Harness h;
    h.dev->write_delay_ms = 40;
    auto o = TestOptions(server.port());
    o.max_playback_ms = 400;  // 10 块
    h.Make(o);
    h.session->Start();
    ASSERT_TRUE(h.rec.WaitState(VoiceState::kReady));
    h.session->Speak("很长的一道题");
    ASSERT_TRUE(h.rec.Wait(Type::kSpeakStarted));
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    const auto during = h.session->GetStats();
    EXPECT_LE(during.playback_queue_max_chunks, 10u);
    EXPECT_GT(during.playback_chunks_dropped, 0u);
    h.session->Stop();
    EXPECT_EQ(h.session->GetStats().playback_queue_chunks, 0u);
}

// 服务端不回 FinishSession：Stop 仍在 stop_timeout 内返回，所有线程都已 join（析构不卡）
TEST(VoiceSessionTest, StopIsBoundedWhenServerHangs) {
    Script sc;
    auto behavior = Scripted(sc);
    behavior.reply_finish_session = false;
    FakeServer server(behavior);
    Harness h;
    h.Make(TestOptions(server.port()));
    h.session->Start();
    ASSERT_TRUE(h.rec.WaitState(VoiceState::kReady));
    h.dev->voiced = true;
    h.session->StartListening();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    const auto t0 = Clock::now();
    h.session->Stop();
    const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - t0).count();
    EXPECT_LT(ms, 2500);
    EXPECT_EQ(h.session->state(), VoiceState::kClosed);
    const auto t1 = Clock::now();
    h.session.reset();
    EXPECT_LT(std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - t1).count(), 200);
}

// silence 模式：不在收听时补发静音（全零），StartSession 的 input_mod 是 audio
TEST(VoiceSessionTest, SilenceModePadsWithZeros) {
    Script sc;
    FakeServer server(Scripted(sc));
    Harness h;
    auto o = TestOptions(server.port());
    o.half_duplex = HalfDuplexMode::kSilence;
    h.Make(o);
    h.session->Start();
    ASSERT_TRUE(h.rec.WaitState(VoiceState::kReady));
    const auto session_frame = server.Frames()[1];
    const auto start_session = nlohmann::json::parse(session_frame.payload.begin(), session_frame.payload.end());
    EXPECT_EQ(start_session["dialog"]["extra"]["input_mod"], "audio");
    h.dev->voiced = true;  // 有声音也不该上传：没在收听
    std::this_thread::sleep_for(std::chrono::milliseconds(300));
    EXPECT_GT(sc.audio_frames.load(), 5);
    EXPECT_EQ(sc.nonzero_audio_frames.load(), 0);
    h.session->Stop();
}

// 手动停止收听后补发静音，服务端才能给出 459 和最终转写
TEST(VoiceSessionTest, ManualStopFlushesSilence) {
    Script sc;
    sc.asr_end_after = 1000;  // 服务端不会自己判断说完
    FakeServer server(Scripted(sc));
    Harness h;
    auto o = TestOptions(server.port());
    o.end_smooth_window_ms = 500;
    h.Make(o);
    h.session->Start();
    ASSERT_TRUE(h.rec.WaitState(VoiceState::kReady));
    h.dev->voiced = true;
    h.session->StartListening();
    ASSERT_TRUE(h.rec.Wait(Type::kUserStarted));
    const int before = sc.audio_frames.load();
    h.session->StopListening();
    std::this_thread::sleep_for(std::chrono::milliseconds(1000));
    const int flushed = sc.audio_frames.load() - before;
    // 500 + 300 ms 的静音约 40 包；之后不再上传
    EXPECT_GE(flushed, 30);
    EXPECT_LE(flushed, 50);
    EXPECT_EQ(h.session->state(), VoiceState::kReady);
    h.session->Stop();
}

// 连不上：报 connect_failed（带原文），状态 error
TEST(VoiceSessionTest, ConnectFailureIsReported) {
    Harness h;
    auto o = TestOptions(1);  // 没人监听的端口
    o.connect_timeout = std::chrono::milliseconds(1000);
    h.Make(o);
    h.session->Start();
    ASSERT_TRUE(h.rec.Wait(Type::kError, 1, std::chrono::milliseconds(3000)));
    EXPECT_EQ(h.rec.Last(Type::kError).code, "connect_failed");
    EXPECT_FALSE(h.rec.Last(Type::kError).text.empty());
    EXPECT_EQ(h.session->state(), VoiceState::kError);
    h.session->Stop();
}

// 服务端中途结束会话：报错，状态 error，不再上传
TEST(VoiceSessionTest, ServerEndingSessionIsReported) {
    Script sc;
    auto behavior = Scripted(sc);
    behavior.end_session_after_audio = 5;
    FakeServer server(behavior);
    Harness h;
    h.Make(TestOptions(server.port()));
    h.session->Start();
    ASSERT_TRUE(h.rec.WaitState(VoiceState::kReady));
    h.dev->voiced = true;
    h.session->StartListening();
    ASSERT_TRUE(h.rec.Wait(Type::kError));
    EXPECT_TRUE(h.rec.WaitState(VoiceState::kError));
    h.session->Stop();
}

// 计时：停下时刻取最后一个有声音的包；底噪阈值写进日志
TEST(VoiceSessionTest, MetricsLogRecordsUserStopAndFirstAudio) {
    Script sc;
    FakeServer server(Scripted(sc));
    Harness h;
    auto o = TestOptions(server.port());
    o.metrics_path = "voice_session_test_metrics.jsonl";
    std::remove(o.metrics_path.c_str());
    h.Make(o);
    h.session->Start();
    ASSERT_TRUE(h.rec.WaitState(VoiceState::kReady));
    std::this_thread::sleep_for(std::chrono::milliseconds(200));  // 底噪取前 5 包（100 ms）静音
    h.session->Speak("第一题");
    ASSERT_TRUE(h.rec.Wait(Type::kSpeakFinished));
    h.dev->voiced = true;
    h.session->StartListening();
    ASSERT_TRUE(h.rec.Wait(Type::kUserStopped));
    h.dev->voiced = false;
    ASSERT_TRUE(h.rec.Wait(Type::kFinal));
    h.session->MarkTranscriptShown("t1");
    h.session->Stop();

    std::ifstream in(o.metrics_path);
    std::string line;
    bool first_audio = false, ended = false, shown = false, floor = false, stats = false;
    while (std::getline(in, line)) {
        const auto j = nlohmann::json::parse(line);
        const auto ev = j["ev"].get<std::string>();
        if (ev == "speak_first_audio") first_audio = j["handed_to_device_ms"].get<double>() >= 0;
        if (ev == "asr_ended") ended = j["stop_to_asr_ended_ms"].is_number() && j["last_voiced_packet"].get<long>() >= 0;
        if (ev == "transcript_shown") shown = j.contains("since_user_stop_ms");
        if (ev == "noise_floor") floor = j["threshold_dbfs"].get<double>() > j["floor_dbfs"].get<double>();
        if (ev == "session_stats") stats = j.contains("audio_frames_sent") && j.contains("playback_queue_max_chunks");
        EXPECT_EQ(line.find("X-Api"), std::string::npos);  // 凭据不进日志
    }
    EXPECT_TRUE(first_audio);
    EXPECT_TRUE(ended);
    EXPECT_TRUE(shown);
    EXPECT_TRUE(floor);
    EXPECT_TRUE(stats);
}

int main(int argc, char** argv) {
    interview::common::Logger::Init("voice_session_test.log", false);
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
