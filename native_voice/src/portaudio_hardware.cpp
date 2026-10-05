#include "native_voice/portaudio_device.h"
#include "native_voice/hardware_opt_in.h"
#include <iostream>

int main(int argc, char** argv) {
    if (!native_voice::hardware_authorized(argc, argv)) {
        std::cerr << "Hardware disabled. Explicit opt-in: --hardware --i-understand-microphone\n";
        return 2;
    }
    std::cerr << "Explicit hardware echo for 5 seconds. Use wired headphones to avoid feedback.\n";
    native_voice::Engine engine({48000, 1});
    native_voice::PortAudioDevice device(engine);
    try {
        device.start();
        std::this_thread::sleep_for(std::chrono::seconds(5));
        device.stop();
        const auto metrics = engine.metrics();
        std::cout << "PortAudio callback echo frames captured=" << metrics.captured
                  << " rendered=" << metrics.rendered << " underrun=" << metrics.underruns
                  << " device_status_flags=" << device.device_status_flags() << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
