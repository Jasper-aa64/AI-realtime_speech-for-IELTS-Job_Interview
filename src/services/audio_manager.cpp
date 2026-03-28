#include "services/audio_manager.h"
#include "common/logger.h"
#include <portaudio.h>

namespace interview {
namespace services {

class AudioDeviceManager::AudioManagerImpl {
public:
    AudioManagerImpl(const AudioConfig& input_config, const AudioConfig& output_config)
        : input_config_(input_config)
        , output_config_(output_config)
        , input_stream_(nullptr)
        , output_stream_(nullptr)
        , pa_initialized_(false) {
        // 初始化音频后端资源（如 PortAudio）。
        if (pa_initialized_) {
            return;
        }
        if (Pa_Initialize() != paNoError) {
            throw std::runtime_error("Failed to initialize PortAudio");
        }
        pa_initialized_ = true;
        LOG_INFO("PortAudio initialized successfully");
    }

    ~AudioManagerImpl() {
        Cleanup();
    }

    void OpenInputStream() {
        // 使用 input_config_ 打开并启动输入流。
        if (input_stream_) {
            LOG_WARNING("Input stream already opened");
            return;
        }

        PaStreamParameters input_params;
        input_params.device = Pa_GetDefaultInputDevice();
        if (input_params.device == paNoDevice) {
            throw std::runtime_error("No default input device found");
        }

        input_params.channelCount = input_config_.channels;
        input_params.sampleFormat = paInt16;
        input_params.suggestedLatency = Pa_GetDeviceInfo(input_params.device)->defaultLowInputLatency;
        input_params.hostApiSpecificStreamInfo = nullptr;

        // framesPerBuffer 使用 0 (paFramesPerBufferUnspecified) 让 PortAudio 自选内部缓冲区大小。
        // 实测：蓝牙设备(如 OPPO Enco X3) 在 16kHz + framesPerBuffer=3200 时
        // Pa_ReadStream 会阻塞 600ms（应为 200ms），原因是 Core Audio 回调调度异常。
        // 传 0 后 Pa_ReadStream(3200) 恢复正常的 200ms 阻塞时间。
        PaError err = Pa_OpenStream(
            &input_stream_,
            &input_params,
            nullptr,  // 无输出
            input_config_.sample_rate,
            paFramesPerBufferUnspecified,
            paClipOff,
            nullptr,  // 无回调，使用阻塞模式
            nullptr
        );
        if(err!=paNoError){
            throw std::runtime_error("Failed to open input stream: " + std::string(Pa_GetErrorText(err)));
        }

        err = Pa_StartStream(input_stream_);
        if(err!=paNoError){
            throw std::runtime_error("Failed to start input stream: " + std::string(Pa_GetErrorText(err)));
        }
        LOG_INFO("Input stream opened: ", input_config_.sample_rate, "Hz, ",
            input_config_.channels, " channel(s), ",
            input_config_.chunk, " frames/buffer");
    }

    void OpenOutputStream() {
        // 使用 output_config_ 打开并启动输出流。
        if (output_stream_) {
            LOG_WARNING("Output stream already opened");
            return;
        }

        PaStreamParameters output_params;
        output_params.device = Pa_GetDefaultOutputDevice();
        if (output_params.device == paNoDevice) {
            throw std::runtime_error("No default output device found");
        }

        output_params.channelCount = output_config_.channels;
        output_params.sampleFormat = paFloat32;
        output_params.suggestedLatency = Pa_GetDeviceInfo(output_params.device)->defaultLowOutputLatency;
        output_params.hostApiSpecificStreamInfo = nullptr;

        PaError err = Pa_OpenStream(
            &output_stream_,
            nullptr, // 无输入
            &output_params,
            output_config_.sample_rate,
            output_config_.chunk,
            paClipOff,
            nullptr, // 无回调，阻塞模式
            nullptr
        );
        if (err != paNoError) {
            throw std::runtime_error("Failed to open output stream: " + std::string(Pa_GetErrorText(err)));
        }

        err = Pa_StartStream(output_stream_);
        if (err != paNoError) {
            throw std::runtime_error("Failed to start output stream: " + std::string(Pa_GetErrorText(err)));
        }

        LOG_INFO("Output stream opened: ",
            output_config_.sample_rate, "Hz, ",
            output_config_.channels, " channel(s), ",
            output_config_.chunk, " frames/buffer");
    }

    std::vector<int16_t> ReadAudio() {
        // 从输入流读取一块 PCM 输入音频。
        if (!input_stream_) {
            throw std::runtime_error("Input stream not opened");
        }

        std::vector<int16_t> buffer(input_config_.chunk * input_config_.channels);
        PaError err = Pa_ReadStream(input_stream_, buffer.data(), input_config_.chunk);
        if (err == paInputOverflowed) {
            // overflow 时 PortAudio 仍返回数据，只记录警告不抛异常，
            // 否则 catch 里 sleep 100ms 会让缓冲区继续积压，陷入永久 overflow
            LOG_WARNING("Input overflow detected (buffer overrun)");
        } else if (err != paNoError) {
            throw std::runtime_error("Failed to read input stream: " + std::string(Pa_GetErrorText(err)));
        }
        return buffer;
    }

    void WriteAudio(const std::vector<float>& audio) {
        // 将 float PCM 输出音频写入输出流。
        if (!output_stream_) {
            throw std::runtime_error("Output stream not opened");
        }

        if (audio.empty()) {
            return;
        }

        // frame_count = 采样点数 / 声道数（PortAudio 以 frame 为单位，1 frame = N 声道）
        unsigned long frame_count = audio.size() / output_config_.channels;
        PaError err = Pa_WriteStream(output_stream_, audio.data(), frame_count);

        if (err == paOutputUnderflowed) {
            LOG_WARNING("Output underflow detected");
        }
        else if (err != paNoError) {
            throw std::runtime_error("Failed to write output stream: " + std::string(Pa_GetErrorText(err)));
        }

    }

    void Cleanup() {
        // 关闭输入流
        if (input_stream_) {
            PaError err = Pa_StopStream(input_stream_);
            if (err != paNoError && err != paStreamIsStopped) {
                LOG_WARNING("Failed to stop input stream: ", Pa_GetErrorText(err));
            }
            err = Pa_CloseStream(input_stream_);
            if (err != paNoError) {
                LOG_WARNING("Failed to close input stream: ", Pa_GetErrorText(err));
            }
            input_stream_ = nullptr;
            LOG_INFO("Input stream closed");
        }

        // 关闭输出流
        if (output_stream_) {
            PaError err = Pa_StopStream(output_stream_);
            if (err != paNoError && err != paStreamIsStopped) {
                LOG_WARNING("Failed to stop output stream: ", Pa_GetErrorText(err));
            }
            err = Pa_CloseStream(output_stream_);
            if (err != paNoError) {
                LOG_WARNING("Failed to close output stream: ", Pa_GetErrorText(err));
            }
            output_stream_ = nullptr;
            LOG_INFO("Output stream closed");
        }

        // 终止 PortAudio
        if (pa_initialized_) {
            PaError err = Pa_Terminate();
            if (err != paNoError) {
                LOG_WARNING("Failed to terminate PortAudio: ", Pa_GetErrorText(err));
            }
            pa_initialized_ = false;
            LOG_INFO("PortAudio terminated");
        }
    }

private:
    AudioConfig input_config_;
    AudioConfig output_config_;
    PaStream* input_stream_;
    PaStream* output_stream_;
    bool pa_initialized_;
};

AudioDeviceManager::AudioDeviceManager(const AudioConfig& input_config,
                                       const AudioConfig& output_config)
    : pimpl_(std::make_unique<AudioManagerImpl>(input_config, output_config)) {
}

AudioDeviceManager::~AudioDeviceManager() = default;

void AudioDeviceManager::OpenInputStream() {
    pimpl_->OpenInputStream();
}

void AudioDeviceManager::OpenOutputStream() {
    pimpl_->OpenOutputStream();
}

std::vector<int16_t> AudioDeviceManager::ReadAudio() {
    return pimpl_->ReadAudio();
}

void AudioDeviceManager::WriteAudio(const std::vector<float>& audio) {
    pimpl_->WriteAudio(audio);
}

void AudioDeviceManager::Cleanup() {
    pimpl_->Cleanup();
}

} // namespace services
} // namespace interview
