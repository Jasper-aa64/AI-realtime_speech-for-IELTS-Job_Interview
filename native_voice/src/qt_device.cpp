#include "native_voice/qt_device.h"
#include <QtMultimedia/QMediaDevices>
#include <QtCore/QCoreApplication>
#include <QtCore/QThread>
#include <algorithm>

namespace native_voice {
void QtDevice::start() {
    if (!QCoreApplication::instance() ||
        QThread::currentThread() != QCoreApplication::instance()->thread())
        throw std::logic_error("QtDevice requires the Qt application control thread");
    if (source_ || sink_) return;
    QAudioFormat format;
    format.setSampleRate(static_cast<int>(engine_.format().sample_rate));
    format.setChannelCount(static_cast<int>(engine_.format().channels));
    format.setSampleFormat(QAudioFormat::Float);
    const auto input = QMediaDevices::defaultAudioInput();
    const auto output = QMediaDevices::defaultAudioOutput();
    if (input.isNull() || output.isNull() || !input.isFormatSupported(format) ||
        !output.isFormatSupported(format))
        throw std::runtime_error("default devices do not support requested identical float PCM format");
    try {
        source_ = std::make_unique<QAudioSource>(input, format);
        sink_ = std::make_unique<QAudioSink>(output, format);
        engine_.start();
        sink_->start([this](QSpan<float> samples) noexcept {
            engine_.render(samples.data(), static_cast<std::size_t>(samples.size()) / engine_.format().channels);
        });
        source_->start([this](QSpan<const float> samples) noexcept {
            engine_.capture(samples.data(), static_cast<std::size_t>(samples.size()) / engine_.format().channels);
        });
        if (!healthy()) throw std::runtime_error("Qt native callback stream failed to start");
    } catch (...) {
        stop();
        throw;
    }
}
bool QtDevice::healthy() const noexcept {
    return source_ && sink_ && source_->error() == QtAudio::NoError && sink_->error() == QtAudio::NoError;
}
void QtDevice::stop() noexcept {
    // Stop device actors first. reset discards output instead of Linux/Darwin
    // stop's synchronous drain. Object destruction quiesces backend callbacks.
    if (source_) source_->stop();
    if (sink_) sink_->reset();
    source_.reset(); sink_.reset();
    engine_.stop();
}
} // namespace native_voice
