#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <type_traits>

namespace native_voice {

// One producer, one consumer. Storage is allocated only during construction.
// reset_quiescent requires both actors to have stopped using the ring.
template <class T> class SpscRing final {
    static_assert(std::is_trivially_copyable_v<T>, "callback frames must be trivial");
    static_assert(std::atomic<std::uint64_t>::is_always_lock_free,
                  "callback indexes require lock-free uint64 atomics");
public:
    explicit SpscRing(std::size_t capacity) : capacity_(capacity), mask_(capacity - 1) {
        if (capacity < 2 || (capacity & (capacity - 1)) != 0 || capacity > (1u << 24))
            throw std::invalid_argument("ring capacity must be a power of two in [2, 2^24]");
        storage_ = std::make_unique<T[]>(capacity);
    }
    bool push(const T& value) noexcept {
        const auto head = head_.load(std::memory_order_relaxed);
        if (head - tail_.load(std::memory_order_acquire) >= capacity_) return false;
        storage_[head & mask_] = value;
        head_.store(head + 1, std::memory_order_release);
        return true;
    }
    bool pop(T& value) noexcept {
        const auto tail = tail_.load(std::memory_order_relaxed);
        if (tail == head_.load(std::memory_order_acquire)) return false;
        value = storage_[tail & mask_];
        tail_.store(tail + 1, std::memory_order_release);
        return true;
    }
    std::size_t capacity() const noexcept { return capacity_; }
    std::size_t storage_bytes() const noexcept { return capacity_ * sizeof(T); }
    void reset_quiescent() noexcept {
        head_.store(0, std::memory_order_relaxed);
        tail_.store(0, std::memory_order_relaxed);
    }
private:
    const std::size_t capacity_, mask_;
    std::unique_ptr<T[]> storage_;
    alignas(64) std::atomic<std::uint64_t> head_{0};
    alignas(64) std::atomic<std::uint64_t> tail_{0};
};

} // namespace native_voice
