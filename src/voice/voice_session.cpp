#include "voice/voice_session.h"

#include "common/protocol.h"
#include "common/utils.h"
#include "services/realtime_client.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <condition_variable>
#include <cstring>
#include <ctime>
#include <deque>
#include <fstream>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <vector>

namespace interview {
namespace voice {

namespace events = common::events;
using Clock = std::chrono::steady_clock;

const char* ToString(SpeakMethod method) {
    switch (method) {
    case SpeakMethod::kAuto: return "auto";
    case SpeakMethod::kSayHello: return "say_hello";
    case SpeakMethod::kChatTTSText: return "chat_tts_text";
    case SpeakMethod::kPrompt: return "prompt";
    }
    return "auto";
}

const char* ToString(HalfDuplexMode mode) {
    return mode == HalfDuplexMode::kKeepAlive ? "keep_alive" : "silence";
}

bool ParseSpeakMethod(const std::string& text, SpeakMethod* out) {
    for (auto m : {SpeakMethod::kAuto, SpeakMethod::kSayHello, SpeakMethod::kChatTTSText, SpeakMethod::kPrompt}) {
        if (text == ToString(m)) {
            *out = m;
            return true;
        }
    }
    return false;
}

const char* ToString(VoiceState state) {
    switch (state) {
    case VoiceState::kIdle: return "idle";
    case VoiceState::kConnecting: return "connecting";
    case VoiceState::kReady: return "ready";
    case VoiceState::kSpeaking: return "speaking";
    case VoiceState::kListening: return "listening";
    case VoiceState::kClosing: return "closing";
    case VoiceState::kClosed: return "closed";
    case VoiceState::kError: return "error";
    }
    return "idle";
}

nlohmann::json VoiceOptions::StartSessionPayload() const {
    nlohmann::json p;
    p["asr"]["extra"]["end_smooth_window_ms"] = end_smooth_window_ms;
    p["tts"]["speaker"] = speaker;
    // pcm 是 32 位 float；引擎和设备都按 16 位处理，所以要 pcm_s16le
    p["tts"]["audio_config"] = {{"channel", 1}, {"format", "pcm_s16le"}, {"sample_rate", output_sample_rate}};
    p["dialog"]["bot_name"] = bot_name;
    if (!system_role.empty()) p["dialog"]["system_role"] = system_role;
    if (!speaking_style.empty()) p["dialog"]["speaking_style"] = speaking_style;
    p["dialog"]["extra"]["model"] = model;
    p["dialog"]["extra"]["input_mod"] = half_duplex == HalfDuplexMode::kKeepAlive ? "keep_alive" : "audio";
    if (extra_start_session.is_object()) {
        p.merge_patch(extra_start_session);
    }
    return p;
}

namespace {

constexpr char kDefaultSystemRole[] =
    "你是模拟面试的语音通道。客户端会给你要朗读的文字，你只逐字朗读，不补充、不评论、不回答问题。";

std::string StringOr(const nlohmann::json& obj, const char* key, const std::string& fallback) {
    if (obj.is_object() && obj.contains(key) && obj.at(key).is_string()) return obj.at(key).get<std::string>();
    return fallback;
}

template <typename T>
T NumberOr(const nlohmann::json& obj, const char* key, T fallback) {
    if (obj.is_object() && obj.contains(key) && obj.at(key).is_number()) return obj.at(key).get<T>();
    return fallback;
}

std::string Timestamp() {
    const std::time_t now = std::time(nullptr);
    std::tm tm{};
    localtime_r(&now, &tm);
    std::ostringstream out;
    out << std::put_time(&tm, "%Y%m%d-%H%M%S");
    return out.str();
}

double RmsDbfs(const int16_t* samples, std::size_t n) {
    if (n == 0) return -120.0;
    double sum = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        const double v = samples[i] / 32768.0;
        sum += v * v;
    }
    const double rms = std::sqrt(sum / static_cast<double>(n));
    return rms > 0.0 ? 20.0 * std::log10(rms) : -120.0;
}

std::string PayloadText(const common::ParsedResponse& r) {
    if (r.is_binary) return std::to_string(r.payload_bytes.size()) + " bytes";
    return r.payload.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace);
}

// 计时日志：一行一个 JSON，t_ms 是会话内单调时钟
class MetricsLog {
public:
    void Open(const std::string& path, Clock::time_point epoch) {
        std::lock_guard<std::mutex> lock(mu_);
        epoch_ = epoch;
        if (!path.empty()) out_.open(path, std::ios::app);
    }
    bool enabled() {
        std::lock_guard<std::mutex> lock(mu_);
        return out_.is_open();
    }
    void Write(nlohmann::json line, Clock::time_point at = Clock::now()) {
        std::lock_guard<std::mutex> lock(mu_);
        if (!out_.is_open()) return;
        line["t_ms"] = std::chrono::duration<double, std::milli>(at - epoch_).count();
        out_ << line.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace) << '\n';
        out_.flush();
    }

private:
    std::mutex mu_;
    std::ofstream out_;
    Clock::time_point epoch_;
};

} // namespace

VoiceOptions VoiceOptionsFromJson(const nlohmann::json& root) {
    VoiceOptions o;
    const auto ws = root.value("ws", nlohmann::json::object());
    o.url = StringOr(ws, "base_url", "");
    if (ws.contains("headers") && ws["headers"].is_object()) {
        for (const auto& item : ws["headers"].items()) {
            if (item.value().is_string() && !item.value().get<std::string>().empty()) {
                o.headers[item.key()] = item.value().get<std::string>();
            }
        }
    }
    if (o.headers.find("X-Api-Connect-Id") == o.headers.end()) {
        o.headers["X-Api-Connect-Id"] = common::GenerateUUID();
    }
    if (ws.contains("tls_verify") && ws["tls_verify"].is_boolean()) o.tls_verify = ws["tls_verify"].get<bool>();
    o.ca_file = StringOr(ws, "ca_file", "");

    const auto dialog = root.value("dialog", nlohmann::json::object());
    o.model = StringOr(dialog, "model", o.model);
    o.bot_name = StringOr(dialog, "bot_name", o.bot_name);

    const auto tts = root.value("tts", nlohmann::json::object());
    o.speaker = StringOr(tts, "speaker", o.speaker);
    const auto asr = root.value("asr", nlohmann::json::object());
    o.end_smooth_window_ms = NumberOr<int>(asr, "end_smooth_window_ms", o.end_smooth_window_ms);

    // voice 段只给语音引擎用；dialog.system_role 是旧原型的"面试官"人设，这里不沿用
    const auto voice = root.value("voice", nlohmann::json::object());
    o.system_role = StringOr(voice, "system_role", kDefaultSystemRole);
    o.speaking_style = StringOr(voice, "speaking_style", "");
    if (voice.contains("end_smooth_window_ms")) {
        o.end_smooth_window_ms = NumberOr<int>(voice, "end_smooth_window_ms", o.end_smooth_window_ms);
    }
    SpeakMethod method;
    if (ParseSpeakMethod(StringOr(voice, "speak_method", "auto"), &method)) o.speak_method = method;
    o.half_duplex = StringOr(voice, "half_duplex", "keep_alive") == "silence" ? HalfDuplexMode::kSilence
                                                                              : HalfDuplexMode::kKeepAlive;
    o.playback_chunk_ms = NumberOr<int>(voice, "playback_chunk_ms", o.playback_chunk_ms);
    o.max_playback_ms = NumberOr<int>(voice, "max_playback_ms", o.max_playback_ms);
    o.voiced_margin_db = NumberOr<double>(voice, "voiced_margin_db", o.voiced_margin_db);
    o.voiced_min_dbfs = NumberOr<double>(voice, "voiced_min_dbfs", o.voiced_min_dbfs);
    if (voice.contains("extra_start_session")) o.extra_start_session = voice["extra_start_session"];
    o.metrics_dir = StringOr(voice, "metrics_dir", "");
    if (voice.contains("dump_pcm") && voice["dump_pcm"].is_boolean()) o.dump_pcm = voice["dump_pcm"].get<bool>();
    o.end_smooth_window_ms = std::clamp(o.end_smooth_window_ms, 500, 50000);
    return o;
}

VoiceOptions LoadVoiceOptions(const std::string& path) {
    std::ifstream in(path);
    if (!in.is_open()) throw std::runtime_error("cannot open voice config: " + path);
    nlohmann::json root;
    try {
        in >> root;
    } catch (const nlohmann::json::exception& e) {
        throw std::runtime_error("cannot parse voice config " + path + ": " + e.what());
    }
    auto options = VoiceOptionsFromJson(root);
    if (options.url.empty()) throw std::runtime_error("voice config has no ws.base_url: " + path);
    if (!HasCredentials(options)) throw std::runtime_error("voice config has no X-Api credentials: " + path);
    return options;
}

bool HasCredentials(const VoiceOptions& options) {
    const auto app = options.headers.find("X-Api-App-ID");
    const auto key = options.headers.find("X-Api-Access-Key");
    return app != options.headers.end() && !app->second.empty() && key != options.headers.end() && !key->second.empty();
}

class VoiceSession::Impl {
    struct Item {
        enum class Kind { kStart, kSpeak, kListen, kStopListen, kStop, kServer, kFirstAudio, kPlaybackIdle, kShown };
        Kind kind;
        std::string text;
        common::ParsedResponse response;
        std::uint64_t speak_id = 0;
        Clock::time_point at = Clock::now();
    };

public:
    using ItemKind = Item::Kind;

private:
    struct Chunk {
        std::vector<int16_t> pcm;
        std::uint64_t speak_id = 0;
    };

public:
    Impl(VoiceOptions options, std::unique_ptr<AudioDevice> device)
        : opt_(std::move(options)), device_(std::move(device)), epoch_(Clock::now()) {
        packet_frames_ = opt_.input_sample_rate * opt_.packet_ms / 1000;
        chunk_frames_ = std::max(1, opt_.output_sample_rate * opt_.playback_chunk_ms / 1000);
        max_chunks_ = static_cast<std::size_t>(std::max(1, opt_.max_playback_ms / std::max(1, opt_.playback_chunk_ms)));
        control_ = std::thread([this] { ControlLoop(); });
    }

    ~Impl() { Stop(); }

    void SetListener(Listener listener) {
        std::lock_guard<std::mutex> lock(listener_mu_);
        listener_ = std::move(listener);
    }

    void Push(Item item) {
        {
            std::lock_guard<std::mutex> lock(q_mu_);
            if (stop_requested_ && item.kind != Item::Kind::kStop) return;
            q_.push_back(std::move(item));
        }
        q_cv_.notify_one();
    }

    void Command(Item::Kind kind, std::string text = {}) {
        Item item{kind};
        item.text = std::move(text);
        Push(std::move(item));
    }

    void Stop() {
        {
            std::lock_guard<std::mutex> lock(q_mu_);
            if (!stop_requested_) {
                stop_requested_ = true;
                q_.push_back(Item{Item::Kind::kStop});
            }
        }
        q_cv_.notify_one();
        if (std::this_thread::get_id() == control_id_.load()) {
            return;  // 在事件回调里：只发起，析构时 join
        }
        if (control_.joinable()) control_.join();
    }

    VoiceState state() const { return state_.load(); }

    VoiceStats GetStats() const {
        VoiceStats s;
        if (auto client = Client()) {
            const auto cs = client->GetStats();
            s.audio_frames_sent = cs.audio_frames_sent;
            s.audio_frames_dropped = cs.audio_frames_dropped;
            s.control_frames_sent = cs.control_frames_sent;
        } else {
            s.audio_frames_sent = last_client_stats_.audio_frames_sent;
            s.audio_frames_dropped = last_client_stats_.audio_frames_dropped;
            s.control_frames_sent = last_client_stats_.control_frames_sent;
        }
        s.mic_packets = mic_packets_.load();
        s.playback_chunks_dropped = playback_dropped_.load();
        s.playback_queue_max_chunks = playback_max_depth_.load();
        {
            std::lock_guard<std::mutex> lock(play_mu_);
            s.playback_queue_chunks = play_q_.size();
        }
        s.disconnects = disconnects_.load();
        return s;
    }

private:
    std::shared_ptr<services::RealtimeClient> Client() const {
        std::lock_guard<std::mutex> lock(client_mu_);
        return client_;
    }

    std::int64_t Ms(Clock::time_point t) const {
        return std::chrono::duration_cast<std::chrono::milliseconds>(t - epoch_).count();
    }

    // ---- 控制线程 ----

    void ControlLoop() {
        control_id_.store(std::this_thread::get_id());
        for (;;) {
            Item item{Item::Kind::kShown};
            bool have = false;
            {
                std::unique_lock<std::mutex> lock(q_mu_);
                q_cv_.wait_for(lock, std::chrono::milliseconds(100), [this] { return !q_.empty(); });
                if (!q_.empty()) {
                    item = std::move(q_.front());
                    q_.pop_front();
                    have = true;
                }
            }
            if (have) {
                if (item.kind == Item::Kind::kStop) {
                    DoStop();
                    return;
                }
                Handle(item);
            }
            Tick();
        }
    }

    void Handle(Item& item) {
        switch (item.kind) {
        case Item::Kind::kStart: DoStart(); break;
        case Item::Kind::kSpeak: DoSpeak(item.text); break;
        case Item::Kind::kListen: DoStartListening(); break;
        case Item::Kind::kStopListen: DoStopListening(); break;
        case Item::Kind::kServer: OnServer(item.response, item.at); break;
        case Item::Kind::kFirstAudio: OnFirstAudio(item.speak_id, item.at); break;
        case Item::Kind::kPlaybackIdle: MaybeFinishSpeaking(); break;
        case Item::Kind::kShown: OnShown(item.text, item.at); break;
        case Item::Kind::kStop: break;
        }
    }

    void Emit(VoiceEvent event) {
        event.state = state_.load();
        if (event.at_ms == 0) event.at_ms = Ms(Clock::now());
        Listener copy;
        {
            std::lock_guard<std::mutex> lock(listener_mu_);
            copy = listener_;
        }
        if (copy) copy(event);  // 不持锁
    }

    void SetState(VoiceState next) {
        if (state_.load() == next) return;
        state_.store(next);
        metrics_.Write({{"ev", "state"}, {"state", ToString(next)}});
        VoiceEvent e;
        e.type = VoiceEvent::Type::kState;
        Emit(e);
    }

    void Fail(const std::string& code, const std::string& message, bool fatal) {
        metrics_.Write({{"ev", "error"}, {"code", code}, {"message", message}, {"fatal", fatal}});
        uploading_.store(false);
        if (fatal) {
            ClearPlayback();
            SetState(VoiceState::kError);
        } else if (state_.load() == VoiceState::kSpeaking || state_.load() == VoiceState::kListening) {
            SetState(VoiceState::kReady);
        }
        VoiceEvent e;
        e.type = VoiceEvent::Type::kError;
        e.code = code;
        e.text = message;
        Emit(e);
    }

    void DoStart() {
        const auto s = state_.load();
        if (s != VoiceState::kIdle && s != VoiceState::kError) return;
        SetState(VoiceState::kConnecting);
        if (opt_.metrics_path.empty() && !opt_.metrics_dir.empty()) {
            const std::string stamp = Timestamp();
            opt_.metrics_path = opt_.metrics_dir + "/voice-" + stamp + ".jsonl";
            if (opt_.dump_pcm) opt_.pcm_dump_path = opt_.metrics_dir + "/mic-" + stamp + ".pcm";
        }
        metrics_.Open(opt_.metrics_path, epoch_);
        metrics_.Write({{"ev", "session_start"},
                        {"wall", Timestamp()},
                        {"model", opt_.model},
                        {"speaker", opt_.speaker},
                        {"end_smooth_window_ms", opt_.end_smooth_window_ms},
                        {"speak_method", ToString(opt_.speak_method)},
                        {"half_duplex", ToString(opt_.half_duplex)},
                        {"packet_ms", opt_.packet_ms},
                        {"playback_chunk_ms", opt_.playback_chunk_ms},
                        {"voiced_margin_db", opt_.voiced_margin_db},
                        {"voiced_min_dbfs", opt_.voiced_min_dbfs},
                        {"noise_floor_packets", opt_.noise_floor_packets},
                        {"pcm_dump", opt_.pcm_dump_path}});

        try {
            if (!devices_open_) {
                device_->OpenInput(opt_.input_sample_rate, packet_frames_);
                device_->OpenOutput(opt_.output_sample_rate, chunk_frames_);
                devices_open_ = true;
                output_latency_ms_ = device_->OutputLatencySeconds() * 1000.0;
                if (!opt_.pcm_dump_path.empty()) {
                    pcm_dump_.open(opt_.pcm_dump_path, std::ios::binary);
                    pcm_times_.open(opt_.pcm_dump_path + ".times");
                }
                capture_running_.store(true);
                capture_ = std::thread([this] { CaptureLoop(); });
                playback_running_.store(true);
                playback_ = std::thread([this] { PlaybackLoop(); });
            }
        } catch (const std::exception& e) {
            return Fail("audio_device", e.what(), true);
        }

        services::RealtimeClientOptions copt;
        copt.tls_verify = opt_.tls_verify;
        copt.ca_file = opt_.ca_file;
        copt.connect_timeout = opt_.connect_timeout;
        copt.close_timeout = std::chrono::milliseconds(std::max<long long>(500, opt_.stop_timeout.count() - 1000));
        copt.finish_session_wait = std::chrono::milliseconds(std::min<long long>(1500, copt.close_timeout.count() / 2));
        copt.max_audio_backlog_bytes = static_cast<std::size_t>(opt_.input_sample_rate) * 2 / 2;  // 0.5 s
        copt.start_session = opt_.StartSessionPayload();
        const auto connect_started = Clock::now();
        try {
            auto client = std::make_shared<services::RealtimeClient>(opt_.url, opt_.headers, copt);
            client->SetResponseCallback([this](const common::ParsedResponse& r) {
                // I/O 线程：只入队，不阻塞
                Item item{Item::Kind::kServer};
                item.response = r;
                Push(std::move(item));
            });
            client->Connect();
            std::lock_guard<std::mutex> lock(client_mu_);
            client_ = std::move(client);
        } catch (const std::exception& e) {
            metrics_.Write({{"ev", "connect_failed"}, {"ms", Ms(Clock::now()) - Ms(connect_started)}, {"error", e.what()}});
            return Fail("connect_failed", e.what(), true);
        }
        metrics_.Write({{"ev", "session_started"},
                        {"connect_ms", Ms(Clock::now()) - Ms(connect_started)},
                        {"model_sent", opt_.model},
                        {"input_mod", copt.start_session["dialog"]["extra"]["input_mod"]}});
        asr_ended_since_speak_ = false;
        SetState(VoiceState::kReady);
    }

    SpeakMethod ChooseMethod() const {
        if (opt_.speak_method != SpeakMethod::kAuto) return opt_.speak_method;
        return asr_ended_since_speak_ ? SpeakMethod::kChatTTSText : SpeakMethod::kSayHello;
    }

    void DoSpeak(const std::string& text) {
        const auto s = state_.load();
        if (s != VoiceState::kReady && s != VoiceState::kListening && s != VoiceState::kSpeaking) {
            return Fail("not_ready", std::string("speak while ") + ToString(s), false);
        }
        auto client = Client();
        if (!client) return Fail("not_ready", "no connection", false);
        uploading_.store(false);
        flush_until_ns_.store(0);
        accept_asr_ = false;
        ClearPlayback();
        const auto method = ChooseMethod();
        const std::uint64_t id = ++speak_id_;
        speak_id_atomic_.store(id);
        try {
            switch (method) {
            case SpeakMethod::kSayHello:
                client->SendEvent(events::SAY_HELLO, {{"content", text}});
                break;
            case SpeakMethod::kChatTTSText:
                client->SendEvent(events::CHAT_TTS_TEXT, {{"start", true}, {"content", text}, {"end", false}});
                client->SendEvent(events::CHAT_TTS_TEXT, {{"start", false}, {"content", ""}, {"end", true}});
                break;
            case SpeakMethod::kPrompt:
            case SpeakMethod::kAuto:
                client->SendEvent(events::CHAT_TEXT_QUERY,
                                  {{"content", "直接朗读下面文字，不要添加任何其他内容：" + text}});
                break;
            }
        } catch (const std::exception& e) {
            return Fail("send_failed", e.what(), false);
        }
        speak_method_ = method;
        speak_at_ = Clock::now();
        speak_text_chars_ = text.size();
        sentence_playing_ = false;
        accepted_reply_.clear();
        tts_done_ = false;
        speak_audio_started_ = false;
        metrics_.Write({{"ev", "speak"}, {"id", id}, {"method", ToString(method)}, {"bytes", text.size()},
                        {"asr_ended_before", asr_ended_since_speak_}});
        asr_ended_since_speak_ = false;
        SetState(VoiceState::kSpeaking);
    }

    void DoStartListening() {
        const auto s = state_.load();
        if (s != VoiceState::kReady && s != VoiceState::kSpeaking && s != VoiceState::kListening) {
            return Fail("not_ready", std::string("listen while ") + ToString(s), false);
        }
        if (s == VoiceState::kListening) return;
        ClearPlayback();
        ++listen_id_;
        listen_at_ = Clock::now();
        listen_start_packet_ = mic_packets_.load();
        last_partial_at_ = Clock::time_point{};
        partial_count_ = 0;
        accept_asr_ = true;
        user_stop_valid_ = false;
        flush_until_ns_.store(0);
        uploading_.store(true);
        metrics_.Write({{"ev", "listen_start"}, {"listen", listen_id_}, {"packet", listen_start_packet_}});
        SetState(VoiceState::kListening);
    }

    void DoStopListening() {
        if (state_.load() != VoiceState::kListening) return;
        uploading_.store(false);
        // 补发一个平滑窗口的静音，服务端才会给出 ASR_ENDED 和最终转写
        const auto until = Clock::now() + std::chrono::milliseconds(opt_.end_smooth_window_ms + 300);
        flush_until_ns_.store(until.time_since_epoch().count());
        metrics_.Write({{"ev", "listen_stop_manual"}, {"listen", listen_id_}, {"packet", mic_packets_.load()}});
        SetState(VoiceState::kReady);
    }

    void DoStop() {
        SetState(VoiceState::kClosing);
        uploading_.store(false);
        flush_until_ns_.store(0);
        std::shared_ptr<services::RealtimeClient> client;
        {
            std::lock_guard<std::mutex> lock(client_mu_);
            client = std::move(client_);
        }
        if (client) {
            last_client_stats_ = client->GetStats();
            client->SetResponseCallback(nullptr);
            client->Close();  // FinishSession → 等 SessionFinished → FinishConnection，总时限 close_timeout
        }
        capture_running_.store(false);
        playback_running_.store(false);
        play_cv_.notify_all();
        if (capture_.joinable()) capture_.join();   // 最多一包（20 ms）
        if (playback_.joinable()) playback_.join(); // 最多一块（40 ms）
        if (devices_open_) {
            device_->CloseInput();
            device_->CloseOutput();
            devices_open_ = false;
        }
        ClearPlayback();
        const auto stats = GetStats();
        metrics_.Write({{"ev", "session_stats"},
                        {"audio_frames_sent", stats.audio_frames_sent},
                        {"audio_frames_dropped", stats.audio_frames_dropped},
                        {"control_frames_sent", stats.control_frames_sent},
                        {"mic_packets", stats.mic_packets},
                        {"playback_queue_max_chunks", stats.playback_queue_max_chunks},
                        {"playback_chunk_ms", opt_.playback_chunk_ms},
                        {"playback_chunks_dropped", stats.playback_chunks_dropped},
                        {"disconnects", stats.disconnects}});
        if (pcm_dump_.is_open()) pcm_dump_.close();
        if (pcm_times_.is_open()) pcm_times_.close();
        SetState(VoiceState::kClosed);
    }

    void Tick() {
        const auto s = state_.load();
        if (s == VoiceState::kReady || s == VoiceState::kSpeaking || s == VoiceState::kListening) {
            auto client = Client();
            if (client && !client->IsConnected()) {
                ++disconnects_;
                last_client_stats_ = client->GetStats();
                {
                    std::lock_guard<std::mutex> lock(client_mu_);
                    client_.reset();
                }
                return Fail("disconnected", "realtime connection closed", true);
            }
        }
        if (s == VoiceState::kSpeaking && accepted_reply_.empty() && !sentence_playing_ &&
            Clock::now() - speak_at_ > opt_.speak_start_timeout) {
            metrics_.Write({{"ev", "speak_timeout"}, {"method", ToString(speak_method_)}});
            Fail("speak_timeout", std::string("no TTS for ") + ToString(speak_method_) + " within " +
                                      std::to_string(opt_.speak_start_timeout.count()) + " ms", false);
        }
    }

    // ---- 服务端消息（控制线程） ----

    void OnServer(const common::ParsedResponse& r, Clock::time_point at) {
        if (r.message_type == "SERVER_ERROR_RESPONSE" || r.message_type == "SERVER_ERROR") {
            return Fail(std::to_string(r.code), PayloadText(r), false);
        }
        switch (r.event) {
        case events::TTS_START: return OnSentenceStart(r);
        case events::TTS_RESPONSE: return OnTtsAudio(r);
        case events::TTS_SENTENCE_END: return;
        case events::TTS_END: return OnTtsEnded(r);
        case events::USER_START_SPEAKING: return OnAsrInfo(at);
        case events::ASR_RESULT: return OnAsrResult(r, at);
        case events::USER_STOP_SPEAKING: return OnAsrEnded(at);
        case events::CHAT_RESPONSE:
        case events::CHAT_ENDED:
            metrics_.Write({{"ev", r.event == events::CHAT_RESPONSE ? "chat_response" : "chat_ended"},
                            {"state", ToString(state_.load())}, {"payload", r.payload}}, at);
            return;
        case events::USAGE_RESPONSE:
            metrics_.Write({{"ev", "usage"}, {"payload", r.payload}}, at);
            return;
        case events::DIALOG_COMMON_ERROR:
            return Fail(StringOr(r.payload, "status_code", "599"), StringOr(r.payload, "message", PayloadText(r)), false);
        case events::SESSION_ENDED:  // 153 SessionFailed
            return Fail("session_failed", StringOr(r.payload, "error", PayloadText(r)), true);
        case events::SESSION_FINISHED:
            if (state_.load() != VoiceState::kClosing) Fail("session_finished", "server finished the session", true);
            return;
        default:
            metrics_.Write({{"ev", "server_event"}, {"event", r.event}, {"payload", PayloadText(r)}}, at);
            return;
        }
    }

    bool AcceptsSentence(const std::string& tts_type) const {
        if (state_.load() != VoiceState::kSpeaking) return false;
        // ChatTTSText 期间模型自己的闲聊（default）也可能在合成，只放指定文本
        if (speak_method_ == SpeakMethod::kChatTTSText) return tts_type == "chat_tts_text";
        return true;
    }

    void OnSentenceStart(const common::ParsedResponse& r) {
        const std::string tts_type = StringOr(r.payload, "tts_type", "");
        const std::string reply = StringOr(r.payload, "reply_id", "");
        sentence_playing_ = AcceptsSentence(tts_type);
        if (sentence_playing_) {
            if (accepted_reply_.empty()) accepted_reply_ = reply.empty() ? "?" : reply;
            metrics_.Write({{"ev", "tts_sentence"}, {"tts_type", tts_type}, {"played", true},
                            {"since_speak_ms", Ms(Clock::now()) - Ms(speak_at_)}, {"text", StringOr(r.payload, "text", "")}});
        } else {
            // 模型自己接的话：不播，只记下来（申报要回答"念完后会不会自己接话"）
            metrics_.Write({{"ev", "tts_sentence"}, {"tts_type", tts_type}, {"played", false},
                            {"state", ToString(state_.load())}, {"text", StringOr(r.payload, "text", "")}});
        }
    }

    void OnTtsAudio(const common::ParsedResponse& r) {
        if (!sentence_playing_ || state_.load() != VoiceState::kSpeaking) {
            unplayed_tts_bytes_ += r.payload_bytes.size();
            return;
        }
        const auto& bytes = r.payload_bytes;
        std::vector<int16_t> samples;
        samples.reserve((bytes.size() + 1) / 2);
        std::size_t i = 0;
        if (carry_valid_ && !bytes.empty()) {
            samples.push_back(static_cast<int16_t>(carry_byte_ | (bytes[0] << 8)));
            carry_valid_ = false;
            i = 1;
        }
        for (; i + 1 < bytes.size(); i += 2) {
            samples.push_back(static_cast<int16_t>(bytes[i] | (bytes[i + 1] << 8)));
        }
        if (i < bytes.size()) {
            carry_byte_ = bytes[i];
            carry_valid_ = true;
        }
        const std::uint64_t id = speak_id_;
        for (std::size_t at = 0; at < samples.size(); at += chunk_frames_) {
            const std::size_t n = std::min<std::size_t>(chunk_frames_, samples.size() - at);
            EnqueuePlayback(Chunk{std::vector<int16_t>(samples.begin() + at, samples.begin() + at + n), id});
        }
    }

    void OnTtsEnded(const common::ParsedResponse& r) {
        const std::string reply = StringOr(r.payload, "reply_id", "");
        const bool ours = state_.load() == VoiceState::kSpeaking && !accepted_reply_.empty() &&
                          (reply.empty() || accepted_reply_ == "?" || reply == accepted_reply_);
        metrics_.Write({{"ev", "tts_ended"}, {"ours", ours}, {"status_code", StringOr(r.payload, "status_code", "")}});
        sentence_playing_ = false;
        if (!ours) return;
        tts_done_ = true;
        carry_valid_ = false;
        MaybeFinishSpeaking();
    }

    void MaybeFinishSpeaking() {
        if (state_.load() != VoiceState::kSpeaking || !tts_done_) return;
        {
            std::lock_guard<std::mutex> lock(play_mu_);
            if (!play_q_.empty() || writing_) return;
        }
        metrics_.Write({{"ev", "speak_finished"}, {"id", speak_id_}, {"since_speak_ms", Ms(Clock::now()) - Ms(speak_at_)}});
        SetState(VoiceState::kReady);
        VoiceEvent e;
        e.type = VoiceEvent::Type::kSpeakFinished;
        Emit(e);
    }

    void OnFirstAudio(std::uint64_t id, Clock::time_point at) {
        if (id != speak_id_ || speak_audio_started_) return;
        speak_audio_started_ = true;
        const double handed = std::chrono::duration<double, std::milli>(at - speak_at_).count();
        metrics_.Write({{"ev", "speak_first_audio"},
                        {"id", id},
                        {"method", ToString(speak_method_)},
                        {"handed_to_device_ms", handed},
                        {"output_latency_ms", output_latency_ms_},
                        {"first_audio_ms", handed + output_latency_ms_}}, at);
        VoiceEvent e;
        e.type = VoiceEvent::Type::kSpeakStarted;
        e.at_ms = Ms(at);
        Emit(e);
    }

    void OnAsrInfo(Clock::time_point at) {
        metrics_.Write({{"ev", "asr_info"}, {"listen", listen_id_}, {"accepted", accept_asr_}}, at);
        if (!accept_asr_) return;
        VoiceEvent e;
        e.type = VoiceEvent::Type::kUserStarted;
        e.at_ms = Ms(at);
        Emit(e);
    }

    void OnAsrResult(const common::ParsedResponse& r, Clock::time_point at) {
        if (!r.payload.contains("results") || !r.payload["results"].is_array() || r.payload["results"].empty()) return;
        const auto& first = r.payload["results"][0];
        const std::string text = StringOr(first, "text", "");
        const bool interim = first.value("is_interim", false);
        if (!accept_asr_) {
            metrics_.Write({{"ev", "asr_ignored"}, {"interim", interim}}, at);
            return;
        }
        VoiceEvent e;
        e.text = text;
        e.at_ms = Ms(at);
        if (interim) {
            nlohmann::json line{{"ev", "asr_partial"}, {"listen", listen_id_}, {"chars", text.size()},
                                {"listening", state_.load() == VoiceState::kListening}};
            if (last_partial_at_ != Clock::time_point{} && state_.load() == VoiceState::kListening) {
                line["interval_ms"] = std::chrono::duration<double, std::milli>(at - last_partial_at_).count();
            }
            last_partial_at_ = at;
            ++partial_count_;
            metrics_.Write(line, at);
            e.type = VoiceEvent::Type::kPartial;
        } else {
            nlohmann::json line{{"ev", "asr_final"}, {"listen", listen_id_}, {"chars", text.size()}};
            if (user_stop_valid_) {
                line["since_user_stop_ms"] = std::chrono::duration<double, std::milli>(at - user_stop_at_).count();
            }
            metrics_.Write(line, at);
            final_at_ = at;
            e.type = VoiceEvent::Type::kFinal;
        }
        Emit(e);
    }

    void OnAsrEnded(Clock::time_point at) {
        const auto voiced_packet = last_voiced_packet_.load();
        const auto voiced_end_ns = last_voiced_end_ns_.load();
        const auto packet_now = mic_packets_.load();
        nlohmann::json line{{"ev", "asr_ended"},
                            {"listen", listen_id_},
                            {"accepted", accept_asr_},
                            {"listening", state_.load() == VoiceState::kListening},
                            {"packet_at_event", packet_now},
                            {"listen_start_packet", listen_start_packet_},
                            {"last_voiced_packet", voiced_packet},
                            {"floor_dbfs", floor_db_.load()},
                            {"threshold_dbfs", threshold_db_.load()},
                            {"end_smooth_window_ms", opt_.end_smooth_window_ms}};
        if (accept_asr_ && voiced_packet >= static_cast<std::int64_t>(listen_start_packet_) && voiced_end_ns != 0) {
            user_stop_at_ = Clock::time_point(Clock::duration(voiced_end_ns));
            user_stop_valid_ = true;
            line["user_stop_t_ms"] = Ms(user_stop_at_);
            line["stop_to_asr_ended_ms"] = std::chrono::duration<double, std::milli>(at - user_stop_at_).count();
        } else {
            line["stop_to_asr_ended_ms"] = nullptr;  // 这一段没检测到有声音的包
        }
        metrics_.Write(line, at);
        if (!accept_asr_) return;
        asr_ended_since_speak_ = true;
        if (state_.load() == VoiceState::kListening) {
            uploading_.store(false);  // 半双工：服务端认为说完了，停止上传
            SetState(VoiceState::kReady);
        }
        VoiceEvent e;
        e.type = VoiceEvent::Type::kUserStopped;
        e.at_ms = Ms(at);
        Emit(e);
    }

    void OnShown(const std::string& note, Clock::time_point at) {
        nlohmann::json line{{"ev", "transcript_shown"}, {"listen", listen_id_}, {"note", note}};
        if (user_stop_valid_) {
            line["since_user_stop_ms"] = std::chrono::duration<double, std::milli>(at - user_stop_at_).count();
        }
        if (final_at_ != Clock::time_point{}) {
            line["since_final_ms"] = std::chrono::duration<double, std::milli>(at - final_at_).count();
        }
        metrics_.Write(line, at);
    }

    // ---- 采集线程 ----

    void CaptureLoop() {
        std::vector<int16_t> buf(static_cast<std::size_t>(packet_frames_));
        std::vector<uint8_t> bytes(buf.size() * 2);
        const std::vector<uint8_t> silence(bytes.size(), 0);
        std::vector<double> floor_samples;
        bool floor_ready = false;
        double threshold = 0.0;
        while (capture_running_.load()) {
            const std::size_t n = device_->Read(buf.data(), buf.size());
            if (n == 0) {
                if (!capture_running_.load()) break;
                std::this_thread::sleep_for(std::chrono::milliseconds(opt_.packet_ms));
                continue;
            }
            const auto now = Clock::now();
            const std::int64_t index = static_cast<std::int64_t>(mic_packets_.load());
            const double db = RmsDbfs(buf.data(), n);
            if (pcm_dump_.is_open()) {
                pcm_dump_.write(reinterpret_cast<const char*>(buf.data()), static_cast<std::streamsize>(n * 2));
                pcm_times_ << index << ' ' << std::fixed << std::setprecision(3)
                           << std::chrono::duration<double, std::milli>(now - epoch_).count() << '\n';
            }
            if (!floor_ready) {
                floor_samples.push_back(db);
                if (static_cast<int>(floor_samples.size()) >= opt_.noise_floor_packets) {
                    std::vector<double> sorted = floor_samples;
                    std::nth_element(sorted.begin(), sorted.begin() + sorted.size() / 2, sorted.end());
                    const double floor = sorted[sorted.size() / 2];
                    threshold = std::max(floor + opt_.voiced_margin_db, opt_.voiced_min_dbfs);
                    floor_db_.store(floor);
                    threshold_db_.store(threshold);
                    floor_ready = true;
                    metrics_.Write({{"ev", "noise_floor"}, {"floor_dbfs", floor}, {"threshold_dbfs", threshold},
                                    {"packets", floor_samples.size()}});
                }
            } else if (db >= threshold) {
                last_voiced_packet_.store(index);
                last_voiced_end_ns_.store(now.time_since_epoch().count());
            }
            mic_packets_.fetch_add(1);  // 先记下声音判断，再让控制线程看到新的包号

            const bool upload = uploading_.load();
            const bool flush = !upload && now.time_since_epoch().count() < flush_until_ns_.load();
            const bool pad = !upload && !flush && opt_.half_duplex == HalfDuplexMode::kSilence;
            if (!upload && !flush && !pad) continue;
            auto client = Client();
            if (!client) continue;
            try {
                if (upload) {
                    std::memcpy(bytes.data(), buf.data(), n * 2);
                    client->SendAudioData(bytes);
                } else {
                    client->SendAudioData(silence);
                }
            } catch (const std::exception&) {
                // 连接断了：控制线程的 Tick 会发现并报错
            }
        }
    }

    // ---- 播放线程 ----

    void EnqueuePlayback(Chunk chunk) {
        {
            std::lock_guard<std::mutex> lock(play_mu_);
            play_q_.push_back(std::move(chunk));
            while (play_q_.size() > max_chunks_) {
                play_q_.pop_front();
                playback_dropped_.fetch_add(1);
            }
            if (play_q_.size() > playback_max_depth_.load()) playback_max_depth_.store(play_q_.size());
        }
        play_cv_.notify_one();
    }

    void ClearPlayback() {
        std::lock_guard<std::mutex> lock(play_mu_);
        play_q_.clear();
    }

    void PlaybackLoop() {
        std::uint64_t started_for = 0;
        for (;;) {
            Chunk chunk;
            {
                std::unique_lock<std::mutex> lock(play_mu_);
                play_cv_.wait(lock, [this] { return !play_q_.empty() || !playback_running_.load(); });
                if (!playback_running_.load()) return;
                chunk = std::move(play_q_.front());
                play_q_.pop_front();
                writing_ = true;
            }
            if (chunk.speak_id != started_for) {
                started_for = chunk.speak_id;
                Item item{Item::Kind::kFirstAudio};
                item.speak_id = chunk.speak_id;
                Push(std::move(item));  // at = 交给设备的时刻
            }
            device_->Write(chunk.pcm.data(), chunk.pcm.size());
            bool idle;
            {
                std::lock_guard<std::mutex> lock(play_mu_);
                writing_ = false;
                idle = play_q_.empty();
            }
            if (idle) Push(Item{Item::Kind::kPlaybackIdle});
        }
    }

    VoiceOptions opt_;
    std::unique_ptr<AudioDevice> device_;
    const Clock::time_point epoch_;
    int packet_frames_ = 320;
    int chunk_frames_ = 960;
    std::size_t max_chunks_ = 1500;

    // 命令队列
    std::mutex q_mu_;
    std::condition_variable q_cv_;
    std::deque<Item> q_;
    bool stop_requested_ = false;
    std::thread control_;
    std::atomic<std::thread::id> control_id_{};

    std::mutex listener_mu_;
    Listener listener_;

    mutable std::mutex client_mu_;
    std::shared_ptr<services::RealtimeClient> client_;
    services::RealtimeClientStats last_client_stats_;

    std::atomic<VoiceState> state_{VoiceState::kIdle};
    MetricsLog metrics_;

    // 以下只在控制线程上读写
    bool devices_open_ = false;
    double output_latency_ms_ = 0.0;
    std::uint64_t speak_id_ = 0;
    SpeakMethod speak_method_ = SpeakMethod::kAuto;
    Clock::time_point speak_at_;
    std::size_t speak_text_chars_ = 0;
    bool sentence_playing_ = false;
    std::string accepted_reply_;
    bool tts_done_ = false;
    bool speak_audio_started_ = false;
    bool asr_ended_since_speak_ = false;
    bool carry_valid_ = false;
    uint8_t carry_byte_ = 0;
    std::uint64_t unplayed_tts_bytes_ = 0;
    std::uint64_t listen_id_ = 0;
    Clock::time_point listen_at_;
    std::uint64_t listen_start_packet_ = 0;
    Clock::time_point last_partial_at_;
    int partial_count_ = 0;
    bool accept_asr_ = false;
    Clock::time_point user_stop_at_;
    bool user_stop_valid_ = false;
    Clock::time_point final_at_;

    // 和采集线程共享
    std::thread capture_;
    std::atomic<bool> capture_running_{false};
    std::atomic<bool> uploading_{false};
    std::atomic<Clock::rep> flush_until_ns_{0};
    std::atomic<std::uint64_t> mic_packets_{0};
    std::atomic<std::int64_t> last_voiced_packet_{-1};
    std::atomic<Clock::rep> last_voiced_end_ns_{0};
    std::atomic<double> floor_db_{0.0};
    std::atomic<double> threshold_db_{0.0};
    std::ofstream pcm_dump_;
    std::ofstream pcm_times_;

    // 和播放线程共享
    std::thread playback_;
    std::atomic<bool> playback_running_{false};
    mutable std::mutex play_mu_;
    std::condition_variable play_cv_;
    std::deque<Chunk> play_q_;
    bool writing_ = false;
    std::atomic<std::uint64_t> speak_id_atomic_{0};
    std::atomic<std::uint64_t> playback_dropped_{0};
    std::atomic<std::size_t> playback_max_depth_{0};
    std::atomic<std::uint64_t> disconnects_{0};
};

VoiceSession::VoiceSession(VoiceOptions options, std::unique_ptr<AudioDevice> device)
    : impl_(std::make_unique<Impl>(std::move(options), std::move(device))) {}

VoiceSession::~VoiceSession() = default;

void VoiceSession::SetListener(Listener listener) { impl_->SetListener(std::move(listener)); }
void VoiceSession::Start() { impl_->Command(Impl::ItemKind::kStart); }
void VoiceSession::Speak(const std::string& text) { impl_->Command(Impl::ItemKind::kSpeak, text); }
void VoiceSession::StartListening() { impl_->Command(Impl::ItemKind::kListen); }
void VoiceSession::StopListening() { impl_->Command(Impl::ItemKind::kStopListen); }
void VoiceSession::Stop() { impl_->Stop(); }
VoiceState VoiceSession::state() const { return impl_->state(); }
VoiceStats VoiceSession::GetStats() const { return impl_->GetStats(); }
void VoiceSession::MarkTranscriptShown(const std::string& note) { impl_->Command(Impl::ItemKind::kShown, note); }

} // namespace voice
} // namespace interview
