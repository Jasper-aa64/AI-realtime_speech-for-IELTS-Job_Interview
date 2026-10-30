#include "voice/injecting_device.h"

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>

namespace interview {
namespace voice {

InjectingAudioDevice::InjectingAudioDevice(std::unique_ptr<AudioDevice> inner) : inner_(std::move(inner)) {}

void InjectingAudioDevice::Inject(std::vector<int16_t> samples) {
    std::lock_guard<std::mutex> lock(mu_);
    pending_ = std::move(samples);
    at_ = 0;
    end_at_ = Clock::time_point{};
}

bool InjectingAudioDevice::Injecting() {
    std::lock_guard<std::mutex> lock(mu_);
    return at_ < pending_.size();
}

InjectingAudioDevice::Clock::time_point InjectingAudioDevice::InjectEnd() {
    std::lock_guard<std::mutex> lock(mu_);
    return end_at_;
}

void InjectingAudioDevice::OpenInput(int sample_rate, int frames_per_packet) { inner_->OpenInput(sample_rate, frames_per_packet); }

std::size_t InjectingAudioDevice::Read(int16_t* out, std::size_t frames) {
    const std::size_t n = inner_->Read(out, frames);
    std::lock_guard<std::mutex> lock(mu_);
    if (at_ < pending_.size()) {
        for (std::size_t i = 0; i < n && at_ < pending_.size(); ++i, ++at_) {
            const int v = out[i] + pending_[at_];
            out[i] = static_cast<int16_t>(std::max(-32768, std::min(32767, v)));
        }
        if (at_ >= pending_.size()) end_at_ = Clock::now();
    }
    return n;
}

void InjectingAudioDevice::CloseInput() { inner_->CloseInput(); }
void InjectingAudioDevice::OpenOutput(int sample_rate, int frames_per_chunk) { inner_->OpenOutput(sample_rate, frames_per_chunk); }
void InjectingAudioDevice::Write(const int16_t* samples, std::size_t frames) { inner_->Write(samples, frames); }
double InjectingAudioDevice::OutputLatencySeconds() const { return inner_->OutputLatencySeconds(); }
std::string InjectingAudioDevice::Describe() const { return inner_->Describe() + " (+injected answer audio)"; }
void InjectingAudioDevice::CloseOutput() { inner_->CloseOutput(); }

std::vector<int16_t> LoadWav16k(const std::string& path, double gain) {
    std::ifstream in(path, std::ios::binary);
    std::vector<char> bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    std::vector<int16_t> samples;
    std::size_t pos = 12;  // RIFF....WAVE
    while (pos + 8 <= bytes.size()) {
        const std::string id(bytes.data() + pos, 4);
        uint32_t size = 0;
        std::memcpy(&size, bytes.data() + pos + 4, 4);
        if (id == "data") {
            const std::size_t n = std::min<std::size_t>(size, bytes.size() - pos - 8) / 2;
            samples.resize(n);
            std::memcpy(samples.data(), bytes.data() + pos + 8, n * 2);
            break;
        }
        pos += 8 + size + (size & 1);
    }
    while (!samples.empty() && std::abs(samples.back()) < 64) samples.pop_back();
    if (gain != 1.0) {
        for (auto& v : samples) v = static_cast<int16_t>(v * gain);
    }
    return samples;
}

} // namespace voice
} // namespace interview
