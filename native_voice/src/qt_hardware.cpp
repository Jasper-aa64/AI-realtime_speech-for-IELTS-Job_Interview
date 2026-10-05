#include "native_voice/qt_device.h"
#include "native_voice/hardware_opt_in.h"
#include <QtCore/QCoreApplication>
#include <QtCore/QTimer>
#include <iostream>

int main(int argc, char** argv) {
    if (!native_voice::hardware_authorized(argc, argv)) {
        std::cerr << "Hardware disabled. Explicit opt-in: --hardware --i-understand-microphone\n";
        return 2;
    }
    std::cerr << "Explicit hardware echo for 5 seconds. Use wired headphones to avoid feedback.\n";
    QCoreApplication app(argc, argv);
    native_voice::Engine engine({48000, 1});
    native_voice::QtDevice device(engine);
    try {
        device.start();
        QTimer::singleShot(5000, &app, [&] { device.stop(); app.quit(); });
        const int result = app.exec();
        const auto metrics = engine.metrics();
        std::cout << "Qt callback echo frames captured=" << metrics.captured
                  << " rendered=" << metrics.rendered << " underrun=" << metrics.underruns << '\n';
        return result;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
