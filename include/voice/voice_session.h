#pragma once

#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <string>

#include <nlohmann/json.hpp>

#include "voice/audio_device.h"

namespace interview {
namespace voice {

/// 让模型念指定文字的方式
enum class SpeakMethod {
    kAuto,         ///< 还没收到过 ASR_ENDED 时用 SayHello，之后用 ChatTTSText
    kSayHello,     ///< 事件 300
    kChatTTSText,  ///< 事件 500（start/content/end 分包）
    kPrompt,       ///< 事件 501 + "直接朗读下面文字" 提示词（旧原型的兜底做法）
};

/// AI 说话、没在收听时麦克风怎么处理（半双工）
enum class HalfDuplexMode {
    kKeepAlive,    ///< 不上传；StartSession 带 dialog.extra.input_mod = "keep_alive"
    kSilence,      ///< 上传等长的静音包
};

const char* ToString(SpeakMethod method);
const char* ToString(HalfDuplexMode mode);
bool ParseSpeakMethod(const std::string& text, SpeakMethod* out);

struct VoiceOptions {
    std::string url;
    std::map<std::string, std::string> headers;   ///< X-Api-* 凭据，不进日志
    bool tls_verify = true;
    std::string ca_file;                           ///< 为空时 macOS 用系统 CA 文件

    // StartSession 里的会话参数
    std::string model = "1.2.1.1";
    std::string speaker = "zh_male_yunzhou_jupiter_bigtts";
    std::string bot_name = "面试官";
    std::string system_role;
    std::string speaking_style;
    int end_smooth_window_ms = 1500;               ///< 服务端判断说完的平滑窗口，[500, 50000]
    /// asr.extra.enable_custom_vad：文档里 end_smooth_window_ms 属于"自定义判停参数"，默认关；
    /// 关着时实测 2000 ms 窗口不生效（900 ms 的停顿就被判说完），所以默认开
    bool enable_custom_vad = true;
    nlohmann::json extra_start_session;            ///< 合并进 StartSession payload 的额外字段

    std::string input_device;                      ///< 设备名包含这段文字就用它；空串用系统默认（壳和 voice_probe 用）
    std::string output_device;

    int input_sample_rate = 16000;
    int packet_ms = 20;                            ///< 上行每包时长（20 ms = 320 帧 = 640 字节）
    int output_sample_rate = 24000;
    int playback_chunk_ms = 40;                    ///< 下行写设备的块大小
    int max_playback_ms = 60000;                   ///< 播放队列上限，超过丢最旧的块
    double output_gain = 1.0;                      ///< 播放音量系数（0~1），不改系统音量

    SpeakMethod speak_method = SpeakMethod::kAuto;
    HalfDuplexMode half_duplex = HalfDuplexMode::kKeepAlive;

    std::chrono::milliseconds connect_timeout{15000};
    std::chrono::milliseconds speak_start_timeout{10000};  ///< Speak 后这么久没收到要播的 TTS 就报错
    std::chrono::milliseconds stop_timeout{4000};           ///< Stop 的总时限

    // 计时："用户停下"= 收听期间最后一段语音的结束时刻。
    // 一包（20 ms）的 RMS 比底噪高出 voiced_margin_db 算有声；连续 min_voiced_run 包有声才算一段语音
    // （键盘声、扬声器开关的爆音只有一两包，不算）。底噪 = 打开麦克风后前 noise_floor_packets 包 RMS 的中位数。
    int noise_floor_packets = 50;                  ///< 1 s
    double voiced_margin_db = 20.0;
    double voiced_min_dbfs = -55.0;                ///< 阈值至少这么高，防止底噪极低时被呼吸声触发
    int min_voiced_run = 3;                        ///< 60 ms

    std::string metrics_path;                      ///< 计时日志（JSON 行）；空则不写
    std::string pcm_dump_path;                     ///< 麦克风原始 PCM（16 kHz s16le），旁边 .times 记每包时刻；空则不存
    /// metrics_path 为空时，Start 在这个目录下按时间戳建 voice-*.jsonl（dump_pcm 时再建 mic-*.pcm）
    std::string metrics_dir;
    bool dump_pcm = false;

    /// 生成 StartSession payload（半双工模式决定 input_mod）
    nlohmann::json StartSessionPayload() const;
};

/**
 * @brief 从本机 JSON 配置读 VoiceOptions
 *
 * 认 config/default_config.json 的 ws / dialog / tts / asr 段（多余字段忽略），
 * 另有可选的 "voice" 段：speak_method、half_duplex、playback_chunk_ms、metrics_dir 等。
 * @throws std::runtime_error 文件读不了、缺 ws.base_url 或 X-Api 凭据
 */
VoiceOptions LoadVoiceOptions(const std::string& path);
VoiceOptions VoiceOptionsFromJson(const nlohmann::json& root);
/// 配置里 X-Api-App-ID / X-Api-Access-Key 都非空才算有凭据
bool HasCredentials(const VoiceOptions& options);

enum class VoiceState {
    kIdle,        ///< 未连接
    kConnecting,
    kReady,       ///< 已连接，没在说也没在听
    kSpeaking,    ///< 在念指定文字（不上传麦克风）
    kListening,   ///< 在上传麦克风、等识别结果
    kClosing,
    kClosed,
    kError,       ///< 连接断了或会话失败，需要重新 Start
};
const char* ToString(VoiceState state);

struct VoiceEvent {
    enum class Type {
        kState,          ///< state 变了
        kPartial,        ///< 中间转写（text 是本段到目前为止的全文）
        kFinal,          ///< 最终转写（text 是本段全文）
        kUserStarted,    ///< 服务端识别到首字（450）
        kUserStopped,    ///< 服务端认为用户说完（459）
        kSpeakStarted,   ///< 第一块要播的声音写进了设备
        kSpeakFinished,  ///< 指定文字播完
        kError,
    };
    Type type = Type::kState;
    VoiceState state = VoiceState::kIdle;
    std::string text;
    std::string code;      ///< 错误码（服务端的 status_code、或 connect_failed / disconnected 等）
    std::int64_t at_ms = 0;  ///< 会话内单调时钟（毫秒），和计时日志同一时钟
};

struct VoiceStats {
    std::uint64_t audio_frames_sent = 0;      ///< RealtimeClient::GetStats()
    std::uint64_t audio_frames_dropped = 0;
    std::uint64_t control_frames_sent = 0;
    std::uint64_t mic_packets = 0;
    std::uint64_t playback_chunks_dropped = 0;
    std::size_t playback_queue_max_chunks = 0;
    std::size_t playback_queue_chunks = 0;
    std::uint64_t disconnects = 0;
};

/**
 * @brief 一次实时语音会话：说一段、听一段
 *
 * 不调大模型，不含题目逻辑。不是单例，可以有多个实例（但一台机器通常只有一个麦克风）。
 *
 * 线程：
 * - 网络由 RealtimeClient 的 I/O 线程负责；它的回调只把消息放进本对象的队列。
 * - 控制线程按顺序处理命令和服务端消息，状态机只在这个线程上改；对外的事件回调也在
 *   这个线程上调用，调用时不持有任何锁。回调里不要调用 Stop()（会只发起、不等待）。
 * - 采集线程每 packet_ms 从设备读一包；只在收听时上传。
 * - 播放线程从有上限的队列取块写设备。
 * 所有线程都由 Stop()/析构 join，不 detach。
 *
 * 公开方法都只投递命令、立刻返回（Stop 除外），可以从任意线程调用。
 */
class VoiceSession {
public:
    using Listener = std::function<void(const VoiceEvent&)>;

    VoiceSession(VoiceOptions options, std::unique_ptr<AudioDevice> device);
    ~VoiceSession();

    VoiceSession(const VoiceSession&) = delete;
    VoiceSession& operator=(const VoiceSession&) = delete;

    /// 在 Start 之前设置
    void SetListener(Listener listener);

    /// 打开设备并连接；结果通过 kState（kReady 或 kError）回报
    void Start();
    /// 念一段文字；正在收听时先停止收听
    void Speak(const std::string& text);
    void StartListening();
    /// 停止上传；补发 end_smooth_window 长的静音，让服务端给出最终转写
    void StopListening();
    /// 结束会话：FinishSession、关连接、停线程。阻塞，总时长不超过 stop_timeout。
    void Stop();

    VoiceState state() const;
    VoiceStats GetStats() const;

    /// 网页显示出最终转写时由壳调用，只记计时日志
    void MarkTranscriptShown(const std::string& note);

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace voice
} // namespace interview
