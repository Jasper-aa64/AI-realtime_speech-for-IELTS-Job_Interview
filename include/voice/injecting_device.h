#pragma once

#include "voice/audio_device.h"

#include <chrono>
#include <mutex>
#include <string>
#include <vector>

namespace interview {
namespace voice {

/**
 * @brief 测试工具：真实麦克风 + 数字叠加的一段"回答"音频
 *
 * 读麦克风照常（真实设备的节拍和房间底噪都在），Inject() 之后把给定的 16 kHz 采样逐包加进去，
 * 房间里不出声。输出照常走被包装的设备。只给 voice_probe 和桌面壳的验收开关
 * （STUDIO_VOICE_TEST_ANSWER_WAV）用，正常运行不经过它。
 */
class InjectingAudioDevice : public AudioDevice {
public:
    using Clock = std::chrono::steady_clock;

    explicit InjectingAudioDevice(std::unique_ptr<AudioDevice> inner);

    void Inject(std::vector<int16_t> samples);
    bool Injecting();
    /// 最后一个注入采样进入 Read 的时刻；还没注入完时为默认值
    Clock::time_point InjectEnd();

    void OpenInput(int sample_rate, int frames_per_packet) override;
    std::size_t Read(int16_t* out, std::size_t frames) override;
    void CloseInput() override;
    void OpenOutput(int sample_rate, int frames_per_chunk) override;
    void Write(const int16_t* samples, std::size_t frames) override;
    double OutputLatencySeconds() const override;
    std::string Describe() const override;
    void CloseOutput() override;

private:
    std::unique_ptr<AudioDevice> inner_;
    std::mutex mu_;
    std::vector<int16_t> pending_;
    std::size_t at_ = 0;
    Clock::time_point end_at_;
};

/// 读 16 kHz 单声道 s16le WAV 的 data 块，去掉末尾静音（|x| < 64），乘以 gain。读不了返回空。
std::vector<int16_t> LoadWav16k(const std::string& path, double gain = 1.0);

} // namespace voice
} // namespace interview
