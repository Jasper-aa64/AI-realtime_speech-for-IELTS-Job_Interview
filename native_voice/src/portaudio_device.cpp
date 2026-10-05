#include "native_voice/portaudio_device.h"

namespace native_voice {
void PortAudioDevice::start() {
    if (stream_) return;
    if (Pa_Initialize() != paNoError) throw std::runtime_error("PortAudio initialization failed");
    initialized_ = true;
    try {
        const auto input_id = Pa_GetDefaultInputDevice(), output_id = Pa_GetDefaultOutputDevice();
        if (input_id == paNoDevice || output_id == paNoDevice)
            throw std::runtime_error("default audio device unavailable");
        PaStreamParameters input{}, output{};
        input.device = input_id;
        input.channelCount = static_cast<int>(engine_.format().channels);
        input.sampleFormat = paFloat32;
        input.suggestedLatency = Pa_GetDeviceInfo(input_id)->defaultLowInputLatency;
        output.device = output_id;
        output.channelCount = input.channelCount;
        output.sampleFormat = paFloat32;
        output.suggestedLatency = Pa_GetDeviceInfo(output_id)->defaultLowOutputLatency;
        if (Pa_IsFormatSupported(&input, &output, engine_.format().sample_rate) != paFormatIsSupported)
            throw std::runtime_error("devices do not support requested identical float PCM format");
        const auto open_result = Pa_OpenStream(&stream_, &input, &output, engine_.format().sample_rate,
            paFramesPerBufferUnspecified, paClipOff, &PortAudioDevice::callback, this);
        if (open_result != paNoError) throw std::runtime_error(Pa_GetErrorText(open_result));
        engine_.start();
        const auto start_result = Pa_StartStream(stream_);
        if (start_result != paNoError) throw std::runtime_error(Pa_GetErrorText(start_result));
    } catch (...) { stop(); throw; }
}
int PortAudioDevice::callback(const void* input, void* output, unsigned long frames,
    const PaStreamCallbackTimeInfo*, PaStreamCallbackFlags flags, void* context) noexcept {
    auto& device = *static_cast<PortAudioDevice*>(context);
    device.status_flags_.fetch_or(flags, std::memory_order_relaxed);
    device.engine_.capture(static_cast<const float*>(input), frames);
    device.engine_.render(static_cast<float*>(output), frames);
    return paContinue;
}
void PortAudioDevice::stop() noexcept {
    if (stream_) {
        // Abort intentionally discards pending output instead of draining it.
        Pa_AbortStream(stream_);
        Pa_CloseStream(stream_);
        stream_ = nullptr;
    }
    engine_.stop();
    if (initialized_) { Pa_Terminate(); initialized_ = false; }
}
} // namespace native_voice
