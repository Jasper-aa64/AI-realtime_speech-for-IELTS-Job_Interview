#include "native_voice/engine.h"
#include <algorithm>
#include <limits>

namespace native_voice {

Engine::Engine(Format format, std::size_t capacity, std::chrono::microseconds poll,
               std::chrono::milliseconds max_backlog)
    : format_(format), worker_poll_(poll),
      max_backlog_frames_(static_cast<std::uint64_t>(format.sample_rate) * max_backlog.count() / 1000),
      capture_(capacity), playback_(capacity) {
    if (format.channels < 1 || format.channels > 2 || format.sample_rate < 8000 ||
        format.sample_rate > 192000 || poll.count() < 0 || poll.count() > 10000 ||
        max_backlog.count() < 1 || max_backlog.count() > 1000)
        throw std::invalid_argument("unsupported format or worker poll interval");
}
Engine::~Engine() { stop(); }

void Engine::quiesce_callbacks() noexcept {
    // Sequentially consistent gate/count establishes either a callback that
    // observes false, or a callback whose active count stop must wait for.
    while (active_callbacks_.load() != 0) std::this_thread::yield();
}
void Engine::start() {
    std::lock_guard<std::mutex> guard(lifecycle_);
    if (running_.load()) return;
    quiesce_callbacks();
    capture_.reset_quiescent();
    playback_.reset_quiescent();
    epoch_.fetch_add(1);
    cancel_.store(false);
    try {
        worker_ = std::thread(&Engine::worker_loop, this);
        running_.store(true);
    } catch (...) {
        cancel_.store(true);
        throw;
    }
}
void Engine::stop() noexcept {
    std::lock_guard<std::mutex> guard(lifecycle_);
    running_.store(false);
    cancel_.store(true);
    epoch_.fetch_add(1);
    quiesce_callbacks();
    if (worker_.joinable()) worker_.join();
    // No callbacks that saw running can still be touching ring storage.
    capture_.reset_quiescent();
    playback_.reset_quiescent();
}
std::uint64_t Engine::interrupt() noexcept {
    metrics_.interrupts.fetch_add(1, std::memory_order_relaxed);
    return epoch_.fetch_add(1) + 1;
}

std::size_t Engine::capture(const float* input, std::size_t frames, std::uint64_t stamp) noexcept {
    CallbackScope scope(active_callbacks_);
    if (!running_.load()) return 0;
    if (frames > std::numeric_limits<std::size_t>::max() / format_.channels) {
        metrics_.invalid_calls.fetch_add(1, std::memory_order_relaxed);
        return 0;
    }
    std::size_t accepted = 0;
    const auto callback_epoch = epoch_.load();
    for (std::size_t i = 0; i < frames; ++i) {
        Frame frame{};
        frame.metadata = {callback_epoch, ++capture_sequence_, stamp};
        for (std::size_t c = 0; c < format_.channels; ++c)
            frame.samples[c] = input ? input[i * format_.channels + c] : 0.0f;
        if (capture_.push(frame)) ++accepted;
    }
    latest_capture_sequence_.store(capture_sequence_, std::memory_order_release);
    metrics_.captured.fetch_add(accepted, std::memory_order_relaxed);
    metrics_.capture_overruns.fetch_add(frames - accepted, std::memory_order_relaxed);
    return accepted;
}

std::size_t Engine::render(float* output, std::size_t frames, Metadata* info) noexcept {
    CallbackScope scope(active_callbacks_);
    if (frames == 0) return 0;
    if (!output || frames > std::numeric_limits<std::size_t>::max() / format_.channels) {
        metrics_.invalid_calls.fetch_add(1, std::memory_order_relaxed);
        return 0;
    }
    const bool is_running = running_.load();
    std::size_t delivered = 0, missing = 0, stale = 0, aged = 0;
    // Bound stale drain work to one ring capacity per callback; no spinning
    // forever if producer races repeated interrupts.
    std::size_t discard_budget = playback_.capacity();
    for (std::size_t i = 0; i < frames; ++i) {
        Frame frame{};
        bool have = false;
        if (is_running) {
            while (playback_.pop(frame)) {
                const auto latest = latest_capture_sequence_.load(std::memory_order_acquire);
                const bool too_old = latest > frame.metadata.sequence &&
                    latest - frame.metadata.sequence > max_backlog_frames_;
                if (frame.metadata.epoch == epoch_.load() && !too_old) { have = true; break; }
                if (too_old) ++aged; else ++stale;
                if (--discard_budget == 0) break;
            }
        }
        // Recheck after pop so interruption races cannot play queued old data.
        have = have && frame.metadata.epoch == epoch_.load() && running_.load();
        if (have) ++delivered; else if (is_running) ++missing;
        for (std::size_t c = 0; c < format_.channels; ++c)
            output[i * format_.channels + c] = have ? frame.samples[c] : 0.0f;
        if (info) info[i] = have ? frame.metadata : Metadata{};
        if (discard_budget == 0) {
            // Once stale drain bound is hit, remaining callback is silence.
            for (++i; i < frames; ++i) {
                for (std::size_t c = 0; c < format_.channels; ++c)
                    output[i * format_.channels + c] = 0.0f;
                if (info) info[i] = {};
                if (is_running) ++missing;
            }
            break;
        }
    }
    metrics_.rendered.fetch_add(delivered, std::memory_order_relaxed);
    metrics_.underruns.fetch_add(missing, std::memory_order_relaxed);
    metrics_.stale_playback.fetch_add(stale, std::memory_order_relaxed);
    metrics_.age_discard_frames.fetch_add(aged, std::memory_order_relaxed);
    return delivered;
}

void Engine::worker_loop() noexcept {
    Frame frame{};
    while (!cancel_.load()) {
        metrics_.worker_iterations.fetch_add(1, std::memory_order_relaxed);
        std::size_t processed = 0;
        // A finite batch keeps stop responsive even while capture keeps filling.
        while (processed < capture_.capacity() && !cancel_.load() && capture_.pop(frame)) {
            ++processed;
            if (frame.metadata.epoch != epoch_.load()) {
                metrics_.stale_capture.fetch_add(1, std::memory_order_relaxed);
                continue;
            }
            const auto latest = latest_capture_sequence_.load(std::memory_order_acquire);
            if (latest > frame.metadata.sequence &&
                latest - frame.metadata.sequence > max_backlog_frames_) {
                metrics_.age_discard_frames.fetch_add(1, std::memory_order_relaxed);
                continue;
            }
            if (!playback_.push(frame))
                metrics_.playback_overruns.fetch_add(1, std::memory_order_relaxed);
            metrics_.processed.fetch_add(1, std::memory_order_relaxed);
        }
        if (processed == 0) {
            if (worker_poll_.count() == 0) std::this_thread::yield();
            else std::this_thread::sleep_for(worker_poll_);
        }
    }
}

Metrics Engine::metrics() const noexcept {
    Metrics result{};
#define NV_LOAD(field) result.field = metrics_.field.load(std::memory_order_relaxed)
    NV_LOAD(captured); NV_LOAD(rendered); NV_LOAD(processed);
    NV_LOAD(capture_overruns); NV_LOAD(playback_overruns); NV_LOAD(underruns);
    NV_LOAD(stale_capture); NV_LOAD(stale_playback); NV_LOAD(invalid_calls);
    NV_LOAD(worker_iterations); NV_LOAD(interrupts);
    NV_LOAD(age_discard_frames);
#undef NV_LOAD
    return result;
}

} // namespace native_voice
