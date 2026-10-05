#include "native_voice/engine.h"
#include <algorithm>
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <new>
#include <vector>

namespace {
thread_local bool callback_allocation_check = false;
thread_local std::uint64_t callback_allocations = 0;
}
void* operator new(std::size_t size) {
    if (callback_allocation_check) ++callback_allocations;
    if (void* result = std::malloc(size ? size : 1)) return result;
    throw std::bad_alloc();
}
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* ptr) noexcept { std::free(ptr); }
void operator delete[](void* ptr) noexcept { std::free(ptr); }
void operator delete(void* ptr, std::size_t) noexcept { std::free(ptr); }
void operator delete[](void* ptr, std::size_t) noexcept { std::free(ptr); }

namespace {
using namespace native_voice;
#define REQUIRE(value) do { if (!(value)) throw std::runtime_error(#value); } while (false)
template <class Predicate> void await(Predicate predicate) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (!predicate()) {
        if (std::chrono::steady_clock::now() >= deadline) throw std::runtime_error("worker timeout");
        std::this_thread::sleep_for(std::chrono::microseconds(50));
    }
}
void ring_bounds_and_wrap() {
    bool rejected = false;
    try { SpscRing<std::uint64_t> invalid(3); } catch (const std::invalid_argument&) { rejected = true; }
    REQUIRE(rejected);
    SpscRing<std::uint64_t> ring(8);
    for (std::uint64_t iteration = 0; iteration < 1000; ++iteration) {
        std::uint64_t value = 0;
        REQUIRE(!ring.pop(value));
        for (std::uint64_t i = 0; i < 8; ++i) REQUIRE(ring.push(iteration * 8 + i));
        REQUIRE(!ring.push(999));
        for (std::uint64_t i = 0; i < 8; ++i) {
            REQUIRE(ring.pop(value)); REQUIRE(value == iteration * 8 + i);
        }
    }
}
void ring_two_thread_order() {
    SpscRing<std::uint64_t> ring(256);
    constexpr std::uint64_t count = 250000;
    std::thread producer([&] {
        for (std::uint64_t i = 1; i <= count; ++i)
            while (!ring.push(i)) std::this_thread::yield();
    });
    bool ordered = true;
    for (std::uint64_t i = 1; i <= count; ++i) {
        std::uint64_t value = 0;
        while (!ring.pop(value)) std::this_thread::yield();
        ordered = ordered && value == i;
    }
    producer.join();
    REQUIRE(ordered);
}
void partial_stereo_and_no_allocation() {
    Engine engine({48000, 2}, 1024);
    engine.start();
    std::array<float, 146> input{};
    for (std::size_t i = 0; i < input.size(); ++i) input[i] = static_cast<float>(i) / 200;
    callback_allocation_check = true;
    const auto accepted = engine.capture(input.data(), 73, 42);
    callback_allocation_check = false;
    REQUIRE(accepted == 73);
    await([&] { return engine.metrics().processed == 73; });
    std::array<float, 146> output{};
    std::array<Metadata, 73> metadata{};
    callback_allocation_check = true;
    const auto first = engine.render(output.data(), 17, metadata.data());
    const auto second = engine.render(output.data() + 34, 56, metadata.data() + 17);
    callback_allocation_check = false;
    REQUIRE(first == 17 && second == 56);
    REQUIRE(output == input);
    for (std::size_t i = 0; i < metadata.size(); ++i) {
        REQUIRE(metadata[i].sequence == i + 1);
        REQUIRE(metadata[i].captured_ns == 42);
        REQUIRE(metadata[i].epoch == engine.epoch());
    }
    callback_allocation_check = true;
    engine.render(output.data(), 73);
    engine.capture(nullptr, 0);
    callback_allocation_check = false;
    REQUIRE(callback_allocations == 0);
    REQUIRE(std::all_of(output.begin(), output.end(), [](float x) { return x == 0; }));
    REQUIRE(engine.metrics().underruns == 73);
    engine.stop();
}
void interruption_flush_and_restart() {
    Engine engine({48000, 1}, 256);
    std::array<float, 100> old_input{}, fresh_input{}, output{};
    old_input.fill(0.25f); fresh_input.fill(0.75f);
    engine.start();
    engine.capture(old_input.data(), 100);
    await([&] { return engine.metrics().processed == 100; });
    REQUIRE(engine.render(output.data(), 17) == 17);
    const auto previous_epoch = engine.epoch();
    REQUIRE(engine.interrupt() > previous_epoch);
    REQUIRE(engine.render(output.data(), 83) == 0);
    REQUIRE(std::all_of(output.begin(), output.begin() + 83, [](float x) { return x == 0; }));
    REQUIRE(engine.metrics().stale_playback == 83);
    engine.capture(fresh_input.data(), 100);
    await([&] { return engine.metrics().processed == 200; });
    REQUIRE(engine.render(output.data(), 100) == 100);
    REQUIRE(output == fresh_input);
    engine.stop(); engine.stop();
    REQUIRE(engine.capture(old_input.data(), 100) == 0);
    output.fill(0.9f);
    REQUIRE(engine.render(output.data(), 100) == 0);
    REQUIRE(std::all_of(output.begin(), output.end(), [](float x) { return x == 0; }));
    engine.start(); engine.start();
    REQUIRE(engine.render(output.data(), 100) == 0);
    engine.stop();
}
void bounded_pressure() {
    Engine engine({48000, 1}, 32, std::chrono::microseconds{10000});
    std::array<float, 1024> input{};
    input.fill(1.0f);
    engine.start();
    engine.capture(input.data(), input.size());
    await([&] { return engine.metrics().processed > 0; });
    engine.capture(input.data(), input.size());
    await([&] { return engine.metrics().playback_overruns > 0; });
    REQUIRE(engine.metrics().capture_overruns > 0);
    REQUIRE(engine.preallocated_audio_bytes() == 2 * 32 * sizeof(Frame));
    engine.stop();
}
void delayed_backlog_is_not_replayed() {
    Engine engine({8000, 1}, 1024, std::chrono::microseconds{100}, std::chrono::milliseconds{1});
    std::array<float, 512> input{}, output{};
    input.fill(0.25f);
    engine.start();
    engine.capture(input.data(), input.size());
    await([&] { return engine.metrics().processed + engine.metrics().age_discard_frames >= 512; });
    const auto delivered = engine.render(output.data(), output.size());
    REQUIRE(delivered <= 9); // 1ms budget =8-frame lag plus the newest sample
    REQUIRE(engine.metrics().age_discard_frames >= 503);
    engine.stop();
}
void interrupt_render_and_restart_stress() {
    Engine engine({48000, 2}, 256);
    std::atomic<bool> done{false};
    std::atomic<std::uint64_t> cycles{0};
    engine.start();
    std::thread capture([&] {
        std::array<float, 254> input{}; input.fill(0.5f);
        while (!done.load()) { engine.capture(input.data(), 127); std::this_thread::yield(); }
    });
    std::thread render([&] {
        std::array<float, 194> output{};
        while (!done.load()) {
            engine.render(output.data(), 97);
            cycles.fetch_add(1);
            std::this_thread::yield();
        }
    });
    for (int i = 0; i < 100; ++i) {
        engine.interrupt();
        if (i % 5 == 0) { engine.stop(); engine.start(); }
        std::this_thread::sleep_for(std::chrono::microseconds(100));
    }
    done.store(true);
    capture.join(); render.join(); engine.stop();
    REQUIRE(cycles.load() > 0);
    REQUIRE(engine.metrics().interrupts == 100);
}
} // namespace
int main() {
    try {
        ring_bounds_and_wrap(); ring_two_thread_order(); partial_stereo_and_no_allocation();
        interruption_flush_and_restart(); bounded_pressure(); delayed_backlog_is_not_replayed();
        interrupt_render_and_restart_stress();
        std::cout << "PASS: ring bounds/order, arbitrary stereo frames, callback allocations, "
                     "interrupt/restart, pressure, simultaneous callbacks/lifecycle\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n'; return 1;
    }
}
