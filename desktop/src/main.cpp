#include <QApplication>
#include <QCommandLineParser>
#include <QSettings>
#include <QTextStream>
#include <QTimer>

#include "browser_window.h"
#include "server_settings.h"
#include "studio_profile.h"

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);
    QApplication::setApplicationName(QStringLiteral("IELTS Studio"));
    QApplication::setOrganizationName(QStringLiteral("IELTS Studio"));
    QApplication::setApplicationVersion(QStringLiteral(STUDIO_VERSION));

    QCommandLineParser parser;
    parser.addHelpOption();
    QCommandLineOption serverOption(QStringLiteral("server"),
                                    QStringLiteral("Use this server for this run only."), QStringLiteral("url"));
    QCommandLineOption smokeOption(QStringLiteral("smoke"),
                                   QStringLiteral("Load the server once, print LOAD_OK/LOAD_FAIL and exit."));
    parser.addOptions({serverOption, smokeOption});
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

    QWebEngineProfile *profile = studio::createStudioProfile(&app);
    studio::BrowserWindow window(profile, server, studio::BrowserWindow::Role::Main);

    if (parser.isSet(smokeOption)) {
        QObject::connect(&window, &studio::BrowserWindow::loadResult, &app, [](bool ok, const QUrl &url) {
            QTextStream(stdout) << (ok ? "LOAD_OK " : "LOAD_FAIL ") << url.toString() << Qt::endl;
            QCoreApplication::exit(ok ? 0 : 1);
        });
        QTimer::singleShot(30000, &app, [] {
            QTextStream(stdout) << "LOAD_TIMEOUT" << Qt::endl;
            QCoreApplication::exit(3);
        });
    }

    window.show();
    window.loadServer();
    return app.exec();
}
