/**
 * @file realtime_client.h
 * @brief 实时对话WebSocket客户端模块
 *
 * 与字节跳动实时对话服务通信的WebSocket客户端类。
 * 负责建立安全连接、发送音频数据、接收服务器响应等。
 */

#pragma once

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <string>
#include <map>
#include <memory>
#include <functional>
#include "common/protocol.h"

namespace interview {
namespace services {

/**
 * @brief RealtimeClient 的可调参数
 *
 * 只给测试和特殊部署用；常规调用用两参数构造函数，参数从 Config 的 ws 段取。
 */
struct RealtimeClientOptions {
    bool tls_verify = true;          ///< 校验服务端证书和主机名
    std::string ca_file;             ///< 自定义 CA 文件；为空时用系统默认 CA 路径
    std::chrono::milliseconds connect_timeout{15000};      ///< 从建 TCP 到收到 SESSION_STARTED 的总时限
    std::chrono::milliseconds finish_session_wait{2000};   ///< Close 发完 FINISH_SESSION 后等 SESSION_FINISHED 的时限
    std::chrono::milliseconds close_timeout{5000};         ///< Close 的总时限，超时直接关 socket
    std::size_t max_audio_backlog_bytes = 16000;           ///< 待发音频上限（默认约 0.5 s 的 16 kHz int16），超过丢最旧的
};

/// @brief 发送统计，所有字段单调递增
struct RealtimeClientStats {
    std::uint64_t audio_frames_sent = 0;
    std::uint64_t audio_frames_dropped = 0;   ///< 积压超过上限被丢掉的音频帧
    std::uint64_t control_frames_sent = 0;
};

/**
 * @brief 实时对话WebSocket客户端类
 *
 * 封装与字节跳动实时对话服务的所有WebSocket通信逻辑。
 * 提供高层次的接口用于音频传输和文本查询。
 *
 * 线程模型：连接由一个内部 I/O 线程独占，所有读、写、关闭都在这个线程上执行。
 * SendAudioData / SendTextQuery 只把消息投递给 I/O 线程，立刻返回，可以从任意线程调用；
 * 网络卡住时不会阻塞调用方，音频积压超过上限时丢最旧的帧并计数。
 * 响应回调也在 I/O 线程上执行，必须很快返回（只入队），回调里可以调用 Close()。
 *
 * 使用示例：
 * @code
 * // 创建客户端
 * std::string url = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue";
 * std::map<std::string, std::string> headers;
 * headers["X-Api-App-ID"] = "your-app-id";
 * headers["X-Api-Access-Key"] = "your-key";
 *
 * services::RealtimeClient client(url, headers);
 *
 * // 设置响应回调
 * client.SetResponseCallback([](const common::ParsedResponse& resp) {
 *     if (resp.event == common::events::TTS_START) {
 *         std::cout << "AI started speaking" << std::endl;
 *     }
 * });
 *
 * // 连接服务器（自动完成START_CONNECTION和START_SESSION）
 * client.Connect();
 *
 * // 发送音频数据
 * std::vector<uint8_t> audio_data = ReadMicrophone();
 * client.SendAudioData(audio_data);
 *
 * // 发送文本查询
 * client.SendTextQuery("请问第一个问题");
 *
 * // 关闭连接
 * client.Close();
 * @endcode
 */
class RealtimeClient {
public:
    /// @brief 响应回调函数类型，用于接收服务器事件
    using ResponseCallback = std::function<void(const common::ParsedResponse&)>;
    /**
     * @brief 构造函数
     *
     * 创建WebSocket客户端实例，解析URL和配置。
     *
     * @param url WebSocket服务器URL（wss://开头）
     * @param headers HTTP请求头，包含认证信息（X-Api-*）
     */
    RealtimeClient(const std::string& url,
                   const std::map<std::string, std::string>& headers);

    /// @brief 带可调参数的构造函数（测试、自定义 CA 等）
    RealtimeClient(const std::string& url,
                   const std::map<std::string, std::string>& headers,
                   const RealtimeClientOptions& options);

    /**
     * @brief 析构函数
     *
     * 自动关闭连接，清理资源。
     */
    ~RealtimeClient();

    /**
     * @brief 连接到服务器
     *
     * 建立WebSocket连接并完成会话初始化：收到 CONNECTION_STARTED、SESSION_STARTED 之后才返回，
     * 此时 IsConnected() 才为 true。总时限见 RealtimeClientOptions::connect_timeout。
     *
     * @throws std::runtime_error 连接失败、握手失败、初始化失败、超时
     */
    void Connect();

    /**
     * @brief 发送音频数据
     *
     * 发送麦克风录音的PCM音频数据给服务器进行ASR识别。
     * 只投递给 I/O 线程，立刻返回；发送失败表现为连接断开（之后的调用抛异常）。
     *
     * @param audio 原始PCM音频数据（每个采样点2字节，小端序）
     * @throws std::runtime_error 未连接
     */
    void SendAudioData(const std::vector<uint8_t>& audio);

    /**
     * @brief 发送文本查询
     *
     * 发送文本提示让AI主动说话（而不是等待用户说话触发）。
     * 只投递给 I/O 线程，立刻返回；控制帧优先于音频发送，不会被丢弃。
     *
     * @param text 文本提示内容（中文）
     * @throws std::runtime_error 未连接
     */
    void SendTextQuery(const std::string& text);

    /**
     * @brief 接收服务器响应（阻塞）
     *
     * 没有设置回调时，收到的消息放进一个有上限的收件箱，由这个方法取出。
     * 设置了回调时消息都交给回调，这里拿不到。
     *
     * @return 解析后的响应结构
     * @throws std::runtime_error 连接已断开且收件箱为空
     */
    common::ParsedResponse ReceiveResponse();

    /// @brief 发送统计（含被丢弃的音频帧数）
    RealtimeClientStats GetStats() const;

    /**
     * @brief 设置响应回调函数
     *
     * 注册回调函数用于接收服务器事件。
     * 回调在接收线程中执行，需要保证线程安全。
     *
     * 回调时机：
     * - TTS_START: AI开始说话
     * - TTS_END: AI说完了
     * - USER_START_SPEAKING: 检测到用户开始说话
     * - USER_STOP_SPEAKING: 用户说完了
     * - ASR_RESULT: 语音识别结果
     * - SESSION_FINISHED: 会话正常结束
     * - SERVER_ACK with audio: TTS音频数据
     *
     * @param callback 响应回调函数
     */
    void SetResponseCallback(ResponseCallback callback);

    /**
     * @brief 返回当前 WebSocket 是否已连接。
     *
     * 用于上层 CLI 在实时服务不可用时选择文本输入降级路径。
     */
    bool IsConnected() const;

    /**
     * @brief 关闭连接
     *
     * 关闭流程（全部在 I/O 线程上按顺序执行）：
     * 1. 发送FINISH_SESSION请求（会话还在时）
     * 2. 等 SESSION_FINISHED，最多 finish_session_wait
     * 3. 发送FINISH_CONNECTION请求
     * 4. 关闭WebSocket（发送Close帧）
     * 5. 总时限 close_timeout，到了直接关 socket
     *
     * 注意：
     * - 可重复调用（内部有状态检查）
     * - 不会抛出异常（错误只记录日志）
     * - 在别的线程调用时，等关闭完成（不超过总时限）再返回；
     *   在响应回调里调用时，只发起关闭、立刻返回
     */
    void Close();

private:
    class RealtimeClientImpl;
    std::unique_ptr<RealtimeClientImpl> pimpl_;
};

} // namespace services
} // namespace interview
