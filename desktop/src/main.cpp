#include <QApplication>
#include <QCommandLineParser>
#include <QEventLoop>
#include <QIcon>
#include <QLibraryInfo>
#include <QLocale>
#include <QSettings>
#include <QTextStream>
#include <QTimer>
#include <QTranslator>
#include <QWebEngineProfile>

#include "browser_window.h"
#include "server_settings.h"
#include "studio_profile.h"

namespace {
// Let Chromium finish asynchronous teardown (WebContents release, cookie-store flush).
void drainEvents() {
    QEventLoop loop;
    QTimer::singleShot(400, &loop, &QEventLoop::quit);
    loop.exec();
}
} // namespace

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);
    QApplication::setApplicationName(QStringLiteral("IELTS Studio"));
    QApplication::setOrganizationName(QStringLiteral("IELTS Studio"));
    QApplication::setApplicationVersion(QStringLiteral(STUDIO_VERSION));
    QIcon studioIcon(QStringLiteral(":/brand/studio-brain-512.png"));
    studioIcon.addFile(QStringLiteral(":/brand/studio-brain-1024.png"));
    QApplication::setWindowIcon(studioIcon);

    // Chinese titles for Qt's own strings (macOS app menu: 隐藏、退出…).
    QTranslator qtTranslator;
    if (qtTranslator.load(QLocale(QLocale::Chinese, QLocale::China), QStringLiteral("qtbase"), QStringLiteral("_"),
                          QLibraryInfo::path(QLibraryInfo::TranslationsPath)))
        QApplication::installTranslator(&qtTranslator);

    QCommandLineParser parser;
    parser.addHelpOption();
    QCommandLineOption serverOption(QStringLiteral("server"),
                                    QStringLiteral("Use this server for this run only."), QStringLiteral("url"));
    QCommandLineOption smokeOption(QStringLiteral("smoke"),
                                   QStringLiteral("Load the server once, print LOAD_OK/LOAD_FAIL and exit."));
    QCommandLineOption testProfileOption(QStringLiteral("test-profile"),
                                         QStringLiteral("Use an isolated in-memory profile for QA; no saved login data."));
    parser.addOptions({serverOption, smokeOption, testProfileOption});
    parser.process(app);

    QSettings settings;
    QUrl server = studio::ServerSettings::load(settings);
    if (parser.isSet(serverOption)) {
        const auto override = studio::ServerSettings::normalize(parser.value(serverOption));
        if (!override) {
            QTextStream(stderr) << "Invalid --server value: " << parser.value(serverOption) << Qt::endl;
            return 2;
        }
        server = *override;
    }

    // Window and profile are torn down explicitly below, while QApplication is still alive:
    // destroying the profile after the app skips Chromium's final cookie flush (login lost on quick quit).
    QWebEngineProfile *profile = studio::createStudioProfile(nullptr, parser.isSet(testProfileOption));
    auto *window = new studio::BrowserWindow(profile, server);

    if (parser.isSet(smokeOption)) {
        QObject::connect(window, &studio::BrowserWindow::loadResult, &app, [](bool ok, const QUrl &url) {
            QTextStream(stdout) << (ok ? "LOAD_OK " : "LOAD_FAIL ") << url.toString() << Qt::endl;
            QCoreApplication::exit(ok ? 0 : 1);
        });
        QTimer::singleShot(30000, &app, [] {
            QTextStream(stdout) << "LOAD_TIMEOUT" << Qt::endl;
            QCoreApplication::exit(3);
        });
    }

    window->show();
    window->loadServer();
    const int code = app.exec();
    delete window;
    drainEvents();
    delete profile;
    drainEvents();
    return code;
}
