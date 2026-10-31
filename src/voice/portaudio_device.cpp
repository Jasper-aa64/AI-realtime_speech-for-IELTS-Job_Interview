#include "voice/audio_device.h"

#include <portaudio.h>

#ifdef __APPLE__
#include <CoreAudio/CoreAudio.h>
#include <CoreFoundation/CoreFoundation.h>
#endif

#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

namespace interview {
namespace voice {

namespace {

std::string PaText(PaError err) {
    return Pa_GetErrorText(err);
}

#ifdef __APPLE__
UInt32 TransportType(AudioDeviceID device) {
    AudioObjectPropertyAddress address{kAudioDevicePropertyTransportType, kAudioObjectPropertyScopeGlobal,
                                       kAudioObjectPropertyElementMain};
    UInt32 transport = 0;
    UInt32 size = sizeof(transport);
    if (AudioObjectGetPropertyData(device, &address, 0, nullptr, &size, &transport) != noErr) return 0;
    return transport;
}

std::string DeviceName(AudioDeviceID device) {
    AudioObjectPropertyAddress address{kAudioObjectPropertyName, kAudioObjectPropertyScopeGlobal,
                                       kAudioObjectPropertyElementMain};
    CFStringRef cf = nullptr;
    UInt32 size = sizeof(cf);
    if (AudioObjectGetPropertyData(device, &address, 0, nullptr, &size, &cf) != noErr || !cf) return {};
    char buffer[256] = {};
    const bool ok = CFStringGetCString(cf, buffer, sizeof(buffer), kCFStringEncodingUTF8);
    CFRelease(cf);
    return ok ? buffer : std::string();
}

// 系统默认输入是蓝牙耳机时返回内置麦克风的名字，否则返回空。打开蓝牙耳机的麦克风会把耳机切到通话模式
// （输出从 44.1 kHz 掉到 16 kHz），页面上的声音会被打断、音质变差；网页录音也是这样避开蓝牙麦克风的。
std::string BuiltInInputInsteadOfBluetooth() {
    AudioObjectPropertyAddress address{kAudioHardwarePropertyDefaultInputDevice, kAudioObjectPropertyScopeGlobal,
                                       kAudioObjectPropertyElementMain};
    AudioDeviceID current = kAudioObjectUnknown;
    UInt32 size = sizeof(current);
    if (AudioObjectGetPropertyData(kAudioObjectSystemObject, &address, 0, nullptr, &size, &current) != noErr) return {};
    const UInt32 transport = TransportType(current);
    if (transport != kAudioDeviceTransportTypeBluetooth && transport != kAudioDeviceTransportTypeBluetoothLE) return {};

    address.mSelector = kAudioHardwarePropertyDevices;
    if (AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, &address, 0, nullptr, &size) != noErr) return {};
    std::vector<AudioDeviceID> devices(size / sizeof(AudioDeviceID));
    if (AudioObjectGetPropertyData(kAudioObjectSystemObject, &address, 0, nullptr, &size, devices.data()) != noErr) return {};
    for (AudioDeviceID device : devices) {
        if (TransportType(device) != kAudioDeviceTransportTypeBuiltIn) continue;
        AudioObjectPropertyAddress streams{kAudioDevicePropertyStreams, kAudioObjectPropertyScopeInput,
                                           kAudioObjectPropertyElementMain};
        UInt32 bytes = 0;
        if (AudioObjectGetPropertyDataSize(device, &streams, 0, nullptr, &bytes) != noErr || bytes == 0) continue;
        return DeviceName(device);
    }
    return {};
}
#endif

PaDeviceIndex FindDevice(const std::string& name, bool input);

// 没指定输入设备时的默认输入：一般是系统默认，默认是蓝牙耳机时换成内置麦克风（找不到就还用系统默认）
PaDeviceIndex DefaultInput() {
#ifdef __APPLE__
    const std::string built_in = BuiltInInputInsteadOfBluetooth();
    if (!built_in.empty()) {
        try {
            return FindDevice(built_in, true);
        } catch (const std::exception&) {
        }
    }
#endif
    return Pa_GetDefaultInputDevice();
}

// 阻塞模式的 PortAudio 流；读只在采集线程、写只在播放线程上调用，打开/关闭由引擎在这两个线程之外串行做。
// 名字里包含 name 且有对应方向声道的设备；name 为空返回默认（输入见 DefaultInput）
PaDeviceIndex FindDevice(const std::string& name, bool input) {
    if (name.empty()) return input ? DefaultInput() : Pa_GetDefaultOutputDevice();
    const int count = Pa_GetDeviceCount();
    std::string available;
    for (int i = 0; i < count; ++i) {
        const PaDeviceInfo* info = Pa_GetDeviceInfo(i);
        if (!info) continue;
        const int channels = input ? info->maxInputChannels : info->maxOutputChannels;
        if (channels <= 0) continue;
        const std::string device = info->name ? info->name : "";
        if (device.find(name) != std::string::npos) return i;
        available += (available.empty() ? "" : ", ") + device;
    }
    throw std::runtime_error(std::string("no ") + (input ? "input" : "output") + " device matching \"" + name +
                             "\" (available: " + available + ")");
}

class PortAudioDevice : public AudioDevice {
public:
    PortAudioDevice(std::string input_name, std::string output_name)
        : input_name_(std::move(input_name)), output_name_(std::move(output_name)) {
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
        params.device = FindDevice(input_name_, true);
        if (params.device == paNoDevice) {
            throw std::runtime_error("no default input device");
        }
        input_device_name_ = Pa_GetDeviceInfo(params.device)->name;
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
        params.device = FindDevice(output_name_, false);
        if (params.device == paNoDevice) {
            throw std::runtime_error("no default output device");
        }
        output_device_name_ = Pa_GetDeviceInfo(params.device)->name;
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
    std::string Describe() const override { return "input=" + input_device_name_ + " output=" + output_device_name_; }

    void CloseOutput() override {
        if (!output_) return;
        Pa_StopStream(output_);
        Pa_CloseStream(output_);
        output_ = nullptr;
    }

private:
    std::string input_name_;
    std::string output_name_;
    std::string input_device_name_;
    std::string output_device_name_;
    PaStream* input_ = nullptr;
    PaStream* output_ = nullptr;
    double output_latency_ = 0.0;
};

} // namespace

std::unique_ptr<AudioDevice> CreatePortAudioDevice(const std::string& input_name, const std::string& output_name) {
    return std::make_unique<PortAudioDevice>(input_name, output_name);
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
