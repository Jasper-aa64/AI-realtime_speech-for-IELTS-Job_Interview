#include "voice/audio_device.h"

#include <portaudio.h>

#include <mutex>
#include <stdexcept>

namespace interview {
namespace voice {

namespace {

std::string PaText(PaError err) {
    return Pa_GetErrorText(err);
}

// 阻塞模式的 PortAudio 流；读只在采集线程、写只在播放线程上调用，打开/关闭由引擎在这两个线程之外串行做。
class PortAudioDevice : public AudioDevice {
public:
    PortAudioDevice() {
        const PaError err = Pa_Initialize();
        if (err != paNoError) {
            throw std::runtime_error("PortAudio init failed: " + PaText(err));
        }
    }

    ~PortAudioDevice() override {
        CloseInput();
        CloseOutput();
        Pa_Terminate();
    }

    void OpenInput(int sample_rate, int frames_per_packet) override {
        if (input_) return;
        PaStreamParameters params{};
        params.device = Pa_GetDefaultInputDevice();
        if (params.device == paNoDevice) {
            throw std::runtime_error("no default input device");
        }
        params.channelCount = 1;
        params.sampleFormat = paInt16;
        params.suggestedLatency = Pa_GetDeviceInfo(params.device)->defaultLowInputLatency;
        PaError err = Pa_OpenStream(&input_, &params, nullptr, sample_rate,
                                    static_cast<unsigned long>(frames_per_packet), paClipOff, nullptr, nullptr);
        if (err != paNoError) {
            input_ = nullptr;
            throw std::runtime_error("open input stream: " + PaText(err));
        }
        err = Pa_StartStream(input_);
        if (err != paNoError) {
            Pa_CloseStream(input_);
            input_ = nullptr;
            throw std::runtime_error("start input stream: " + PaText(err));
        }
    }

    std::size_t Read(int16_t* out, std::size_t frames) override {
        if (!input_) return 0;
        const PaError err = Pa_ReadStream(input_, out, static_cast<unsigned long>(frames));
        // 溢出说明读得不够快、丢了一些采样；这一包仍然有效
        if (err != paNoError && err != paInputOverflowed) return 0;
        return frames;
    }

    void CloseInput() override {
        if (!input_) return;
        Pa_StopStream(input_);
        Pa_CloseStream(input_);
        input_ = nullptr;
    }

    void OpenOutput(int sample_rate, int frames_per_chunk) override {
        if (output_) return;
        PaStreamParameters params{};
        params.device = Pa_GetDefaultOutputDevice();
        if (params.device == paNoDevice) {
            throw std::runtime_error("no default output device");
        }
        params.channelCount = 1;
        params.sampleFormat = paInt16;
        params.suggestedLatency = Pa_GetDeviceInfo(params.device)->defaultLowOutputLatency;
        PaError err = Pa_OpenStream(&output_, nullptr, &params, sample_rate,
                                    static_cast<unsigned long>(frames_per_chunk), paClipOff, nullptr, nullptr);
        if (err != paNoError) {
            output_ = nullptr;
            throw std::runtime_error("open output stream: " + PaText(err));
        }
        err = Pa_StartStream(output_);
        if (err != paNoError) {
            Pa_CloseStream(output_);
            output_ = nullptr;
            throw std::runtime_error("start output stream: " + PaText(err));
        }
        if (const PaStreamInfo* info = Pa_GetStreamInfo(output_)) {
            output_latency_ = info->outputLatency;
        }
    }

    void Write(const int16_t* samples, std::size_t frames) override {
        if (!output_ || frames == 0) return;
        // 欠载（paOutputUnderflowed）只说明中间断过一下，不算错
        Pa_WriteStream(output_, samples, static_cast<unsigned long>(frames));
    }

    double OutputLatencySeconds() const override { return output_latency_; }

    void CloseOutput() override {
        if (!output_) return;
        Pa_StopStream(output_);
        Pa_CloseStream(output_);
        output_ = nullptr;
    }

private:
    PaStream* input_ = nullptr;
    PaStream* output_ = nullptr;
    double output_latency_ = 0.0;
};

} // namespace

std::unique_ptr<AudioDevice> CreatePortAudioDevice() {
    return std::make_unique<PortAudioDevice>();
}

bool ProbePortAudio(std::string* reason) {
    const PaError err = Pa_Initialize();
    if (err != paNoError) {
        if (reason) *reason = "PortAudio init failed: " + PaText(err);
        return false;
    }
    std::string why;
    if (Pa_GetDefaultInputDevice() == paNoDevice) {
        why = "no default input device";
    } else if (Pa_GetDefaultOutputDevice() == paNoDevice) {
        why = "no default output device";
    }
    Pa_Terminate();
    if (!why.empty()) {
        if (reason) *reason = why;
        return false;
    }
    return true;
}

} // namespace voice
} // namespace interview
