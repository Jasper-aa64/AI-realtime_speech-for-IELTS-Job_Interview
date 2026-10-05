#pragma once

#include "native_voice/spsc_ring.h"
#include <array>
#include <chrono>
#include <mutex>
#include <thread>

namespace native_voice {

struct Format {
    std::uint32_t sample_rate = 48000;
    std::uint32_t channels = 1;
};
struct Metadata {
    std::uint64_t epoch = 0;
    std::uint64_t sequence = 0;
    // Caller-provided monotonic callback timestamp; zero means unavailable.
    std::uint64_t captured_ns = 0;
};
struct Frame {
    std::array<float, 2> samples{};
    Metadata metadata{};
};
struct Metrics {
    std::uint64_t captured = 0, rendered = 0, processed = 0;
    std::uint64_t capture_overruns = 0, playback_overruns = 0, underruns = 0;
    std::uint64_t stale_capture = 0, stale_playback = 0, invalid_calls = 0;
    std::uint64_t worker_iterations = 0, interrupts = 0;
    std::uint64_t age_discard_frames = 0;
};

// Software echo foundation, NOT an ASR/LLM/TTS or DSP implementation.
// capture/render are one producer/consumer each, with non-reentrant callbacks.
// start/stop use a control mutex, never called from callbacks. Destroy only
// after the device has stopped issuing callbacks. interrupt is atomic-only.
class Engine final {
    static_assert(std::atomic<bool>::is_always_lock_free,
                  "callback gates require lock-free bool atomics");
public:
    explicit Engine(Format format = {}, std::size_t capacity_frames = 4096,
                    std::chrono::microseconds worker_poll = std::chrono::microseconds{100},
                    std::chrono::milliseconds max_backlog = std::chrono::milliseconds{40});
    ~Engine();
    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;
    void start();
    void stop() noexcept;
    std::uint64_t interrupt() noexcept;
    bool running() const noexcept { return running_.load(); }
    std::uint64_t epoch() const noexcept { return epoch_.load(); }
    const Format& format() const noexcept { return format_; }
    std::size_t capacity_frames() const noexcept { return capture_.capacity(); }
    std::uint64_t max_backlog_frames() const noexcept { return max_backlog_frames_; }
    std::size_t preallocated_audio_bytes() const noexcept {
        return capture_.storage_bytes() + playback_.storage_bytes();
    }
    // Return accepted/non-silent frame count. Buffers are interleaved float PCM.
    // Null input is explicit silence. Output must hold frames * channels floats.
    std::size_t capture(const float* input, std::size_t frames,
                        std::uint64_t callback_timestamp_ns = 0) noexcept;
    std::size_t render(float* output, std::size_t frames,
                       Metadata* metadata = nullptr) noexcept;
    Metrics metrics() const noexcept;
private:
    struct CallbackScope {
        explicit CallbackScope(std::atomic<std::uint64_t>& active) noexcept : active_(active) {
            active_.fetch_add(1);
        }
        ~CallbackScope() { active_.fetch_sub(1); }
        std::atomic<std::uint64_t>& active_;
    };
    void worker_loop() noexcept;
    void quiesce_callbacks() noexcept;
    const Format format_;
    const std::chrono::microseconds worker_poll_;
    const std::uint64_t max_backlog_frames_;
    SpscRing<Frame> capture_, playback_;
    std::mutex lifecycle_;
    std::thread worker_;
    std::atomic<bool> running_{false}, cancel_{true};
    std::atomic<std::uint64_t> epoch_{0}, active_callbacks_{0};
    std::atomic<std::uint64_t> latest_capture_sequence_{0};
    std::uint64_t capture_sequence_ = 0; // capture owner only; never reset
    struct AtomicMetrics {
        std::atomic<std::uint64_t> captured{0}, rendered{0}, processed{0};
        std::atomic<std::uint64_t> capture_overruns{0}, playback_overruns{0}, underruns{0};
        std::atomic<std::uint64_t> stale_capture{0}, stale_playback{0}, invalid_calls{0};
        std::atomic<std::uint64_t> worker_iterations{0}, interrupts{0};
        std::atomic<std::uint64_t> age_discard_frames{0};
    } metrics_;
};

} // namespace native_voice
