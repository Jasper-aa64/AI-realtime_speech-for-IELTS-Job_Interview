#include "native_voice/engine.h"
#include <algorithm>
#include <cmath>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

using Clock = std::chrono::steady_clock;
static std::uint64_t now_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
}
static double percentile(std::vector<double>& values, double fraction) {
    if (values.empty()) return 0;
    std::sort(values.begin(), values.end());
    return values[static_cast<std::size_t>(std::ceil(fraction * values.size())) - 1];
}
int main(int argc, char** argv) {
    double seconds = 3;
    try {
        for (int i = 1; i < argc; ++i) {
            if (std::string(argv[i]) != "--seconds" || i + 1 >= argc)
                throw std::invalid_argument("usage: native_voice_benchmark [--seconds 0.05..30]");
            seconds = std::stod(argv[++i]);
        }
        if (!std::isfinite(seconds) || seconds < 0.05 || seconds > 30)
            throw std::invalid_argument("seconds must be in [0.05,30]");
        native_voice::Engine engine({48000, 1}, 4096);
        const std::size_t total_frames = static_cast<std::size_t>(seconds * 48000);
        // All telemetry/input/output storage allocated before callbacks start.
        std::vector<double> latencies(total_frames + 4096, 0), capture_times(total_frames + 1, 0),
                            render_times(total_frames + 1, 0), schedule_jitter(total_frames + 1, 0);
        std::array<float, 480> input{}, output{};
        std::array<native_voice::Metadata, 480> metadata{};
        input.fill(0.25f);
        constexpr std::array<std::size_t, 4> pattern{127, 256, 97, 480};
        std::size_t captured = 0, callbacks = 0, observed = 0;
        const auto cpu_start = std::clock();
        const auto start = Clock::now();
        engine.start();
        while (captured < total_frames) {
            const auto frames = std::min(pattern[callbacks % pattern.size()], total_frames - captured);
            const auto scheduled = start + std::chrono::nanoseconds(captured * 1000000000ull / 48000);
            std::this_thread::sleep_until(scheduled);
            const auto stamp = now_ns();
            schedule_jitter[callbacks] = std::chrono::duration<double, std::micro>(Clock::now() - scheduled).count();
            const auto before_capture = now_ns();
            engine.capture(input.data(), frames, stamp);
            capture_times[callbacks] = (now_ns() - before_capture) / 1000.0;
            const auto before_render = now_ns();
            engine.render(output.data(), frames, metadata.data());
            const auto rendered_at = now_ns();
            render_times[callbacks] = (rendered_at - before_render) / 1000.0;
            for (std::size_t i = 0; i < frames; ++i)
                if (metadata[i].captured_ns && observed < latencies.size())
                    latencies[observed++] = (rendered_at - metadata[i].captured_ns) / 1000000.0;
            captured += frames; ++callbacks;
        }
        // Capture ends first. Drain at real-time cadence so missing final data
        // is reflected explicitly, rather than included as fake zero latency.
        for (int attempt = 0; attempt < 20; ++attempt) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            engine.render(output.data(), 480, metadata.data());
            const auto rendered_at = now_ns();
            for (std::size_t i = 0; i < 480; ++i)
                if (metadata[i].captured_ns && observed < latencies.size())
                    latencies[observed++] = (rendered_at - metadata[i].captured_ns) / 1000000.0;
            if (observed == total_frames) break;
        }
        const auto before_stop = Clock::now();
        engine.stop();
        const double stop_us = std::chrono::duration<double, std::micro>(Clock::now() - before_stop).count();
        const auto metrics = engine.metrics();
        const auto wall = std::chrono::duration<double>(Clock::now() - start).count();
        const double cpu_seconds = static_cast<double>(std::clock() - cpu_start) / CLOCKS_PER_SEC;
        latencies.resize(observed); capture_times.resize(callbacks); render_times.resize(callbacks);
        schedule_jitter.resize(callbacks);
        const std::size_t telemetry_bytes = (latencies.capacity() + capture_times.capacity() +
            render_times.capacity() + schedule_jitter.capacity()) * sizeof(double) + sizeof(metadata);
        std::cout << std::fixed << std::setprecision(3)
            << "{\n  \"mode\": \"paced_software_echo_no_device\",\n"
            << "  \"latency_scope\": \"caller_capture_timestamp_to_software_render_return_not_DAC\",\n"
            << "  \"hardware_or_cloud_measured\": false,\n  \"sample_rate\": 48000,\n  \"channels\": 1,\n"
            << "  \"sample_format\": \"float32\",\n  \"callback_frame_pattern\": [127,256,97,480],\n"
            << "  \"requested_seconds\": " << seconds << ",\n  \"observed_wall_seconds\": " << wall << ",\n"
            << "  \"cpu_seconds\": " << cpu_seconds << ",\n  \"cpu_percent_one_core\": " << cpu_seconds / wall * 100 << ",\n"
            << "  \"callback_count\": " << callbacks << ",\n  \"latency_sample_count\": " << observed << ",\n"
            << "  \"captured_frames\": " << metrics.captured << ",\n  \"rendered_frames\": " << metrics.rendered << ",\n"
            << "  \"capture_overrun_frames\": " << metrics.capture_overruns << ",\n"
            << "  \"playback_overrun_frames\": " << metrics.playback_overruns << ",\n"
            << "  \"underrun_silence_frames\": " << metrics.underruns << ",\n"
            << "  \"stale_discard_frames\": " << metrics.stale_capture + metrics.stale_playback << ",\n"
            << "  \"backlog_age_discard_frames\": " << metrics.age_discard_frames << ",\n"
            << "  \"preallocated_audio_bytes\": " << engine.preallocated_audio_bytes() << ",\n"
            << "  \"preallocated_harness_telemetry_bytes\": " << telemetry_bytes << ",\n"
            << "  \"ring_capacity_frames_each\": " << engine.capacity_frames() << ",\n"
            << "  \"ring_capacity_ms_each\": " << engine.capacity_frames() * 1000.0 / 48000 << ",\n"
            << "  \"max_backlog_sample_age_ms\": " << engine.max_backlog_frames() * 1000.0 / 48000 << ",\n"
            << "  \"capture_to_render_ms\": {\"p50\":" << percentile(latencies, .5)
            << ",\"p95\":" << percentile(latencies, .95) << ",\"p99\":" << percentile(latencies, .99) << "},\n"
            << "  \"capture_to_render_ms_max\": " << (latencies.empty() ? 0 : latencies.back()) << ",\n"
            << "  \"capture_callback_us_p99\": " << percentile(capture_times, .99) << ",\n"
            << "  \"render_callback_us_p99\": " << percentile(render_times, .99) << ",\n"
            << "  \"scheduler_jitter_us_p99\": " << percentile(schedule_jitter, .99) << ",\n"
            << "  \"observed_stop_us\": " << stop_us << "\n}\n";
        return observed && metrics.capture_overruns == 0 && metrics.playback_overruns == 0 ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 2;
    }
}
