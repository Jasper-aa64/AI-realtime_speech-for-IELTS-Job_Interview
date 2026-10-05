#pragma once
#include "native_voice/engine.h"
#include <portaudio.h>

namespace native_voice {
// One device-control thread, one full-duplex native callback. Construction
// alone does not initialize PortAudio or open any hardware.
class PortAudioDevice final {
public:
    explicit PortAudioDevice(Engine& engine) : engine_(engine) {}
    ~PortAudioDevice() { stop(); }
    void start();
    void stop() noexcept;
    std::uint64_t device_status_flags() const noexcept { return status_flags_.load(); }
private:
    static int callback(const void*, void*, unsigned long,
                        const PaStreamCallbackTimeInfo*, PaStreamCallbackFlags, void*) noexcept;
    Engine& engine_;
    PaStream* stream_ = nullptr;
    bool initialized_ = false;
    std::atomic<std::uint64_t> status_flags_{0};
};
} // namespace native_voice
