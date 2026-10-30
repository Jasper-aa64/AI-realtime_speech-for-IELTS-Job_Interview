#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>

namespace interview {
namespace voice {

/**
 * @brief 语音引擎用的音频设备：阻塞式读麦克风、写扬声器
 *
 * 只用 16 位单声道 PCM。Read/Write 在引擎自己的采集线程、播放线程上调用，
 * 每次最多阻塞一包的时长，所以停止时线程能在一包之内退出。
 * 测试用假设备实现这个接口，不碰真麦克风。
 */
class AudioDevice {
public:
    virtual ~AudioDevice() = default;

    /// 打开麦克风；失败抛 std::runtime_error（错误原文带在 what() 里）
    virtual void OpenInput(int sample_rate, int frames_per_packet) = 0;
    /// 读一包，阻塞到读满；返回实际帧数，0 表示设备已关或出错
    virtual std::size_t Read(int16_t* out, std::size_t frames) = 0;
    virtual void CloseInput() = 0;

    /// 打开扬声器；失败抛 std::runtime_error
    virtual void OpenOutput(int sample_rate, int frames_per_chunk) = 0;
    /// 写一块，阻塞到设备收下
    virtual void Write(const int16_t* samples, std::size_t frames) = 0;
    /// 输出设备的延迟（秒），算"扬声器出声"时刻用；不知道时返回 0
    virtual double OutputLatencySeconds() const { return 0.0; }
    /// 实际打开的设备名，写进计时日志
    virtual std::string Describe() const { return {}; }
    virtual void CloseOutput() = 0;
};

/**
 * @brief PortAudio 实现。构造时初始化 PortAudio，析构时释放。
 * @param input_name、output_name 设备名里包含这段文字就选它（例如 "MacBook Air"）；空串用系统默认设备。
 *        找不到时 OpenInput / OpenOutput 抛异常，信息里列出可用设备名。
 */
std::unique_ptr<AudioDevice> CreatePortAudioDevice(const std::string& input_name = {},
                                                   const std::string& output_name = {});

/**
 * @brief 不打开流，只检查 PortAudio 能初始化、有默认输入和输出设备
 * @param reason 不可用时写入原因
 */
bool ProbePortAudio(std::string* reason);

} // namespace voice
} // namespace interview
