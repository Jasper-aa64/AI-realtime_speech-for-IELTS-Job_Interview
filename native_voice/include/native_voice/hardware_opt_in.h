#pragma once
#include <cstring>

namespace native_voice {
// Parse before any device API/QCoreApplication/PortAudio initialization.
inline bool hardware_authorized(int argc, char** argv) noexcept {
    if (argc != 3) return false;
    return std::strcmp(argv[1], "--hardware") == 0 &&
           std::strcmp(argv[2], "--i-understand-microphone") == 0;
}
} // namespace native_voice
