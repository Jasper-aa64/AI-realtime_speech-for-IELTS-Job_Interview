#pragma once
#include "native_voice/engine.h"
#include <QtMultimedia/QAudioSource>
#include <QtMultimedia/QAudioSink>
#include <memory>

namespace native_voice {
// Create/start/stop/destroy on one Qt application thread. Hardware opt-in is
// enforced by the executable; merely constructing this adapter opens nothing.
class QtDevice final {
public:
    explicit QtDevice(Engine& engine) : engine_(engine) {}
    ~QtDevice() { stop(); }
    void start();
    void stop() noexcept;
    bool healthy() const noexcept;
private:
    Engine& engine_;
    std::unique_ptr<QAudioSource> source_;
    std::unique_ptr<QAudioSink> sink_;
};
} // namespace native_voice
