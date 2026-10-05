#include <QSettings>
#include <QTemporaryDir>
#include <QtTest>

#include "server_settings.h"

using studio::ServerSettings;

class ServerSettingsTest : public QObject {
    Q_OBJECT
private slots:
    void defaultIsLocalDevServer() {
        QCOMPARE(ServerSettings::defaultUrl(), QUrl(QStringLiteral("http://127.0.0.1:8767/")));
    }

    void normalizeReducesToOrigin_data() {
        QTest::addColumn<QString>("input");
        QTest::addColumn<QString>("expected");
        QTest::newRow("bare host:port") << "127.0.0.1:8767" << "http://127.0.0.1:8767/";
        QTest::newRow("trims spaces") << "  http://localhost:8767  " << "http://localhost:8767/";
        QTest::newRow("drops path query fragment") << "https://Studio.Example.com/app?x=1#y" << "https://studio.example.com/";
        QTest::newRow("keeps https port") << "https://example.com:8443/" << "https://example.com:8443/";
    }
    void normalizeReducesToOrigin() {
        QFETCH(QString, input);
        QFETCH(QString, expected);
        const auto result = ServerSettings::normalize(input);
        QVERIFY(result.has_value());
        QCOMPARE(result->toString(), expected);
    }

    void normalizeRejectsInvalid_data() {
        QTest::addColumn<QString>("input");
        QTest::newRow("empty") << "";
        QTest::newRow("blank") << "   ";
        QTest::newRow("ftp") << "ftp://example.com";
        QTest::newRow("no host") << "http://";
        QTest::newRow("space in host") << "not a url";
    }
    void normalizeRejectsInvalid() {
        QFETCH(QString, input);
        QVERIFY(!ServerSettings::normalize(input).has_value());
    }

    void loadFallsBackToDefault() {
        QTemporaryDir dir;
        QSettings settings(dir.filePath(QStringLiteral("s.ini")), QSettings::IniFormat);
        QCOMPARE(ServerSettings::load(settings), ServerSettings::defaultUrl());
        settings.setValue(QStringLiteral("server/url"), QStringLiteral("ftp://bad"));
        QCOMPARE(ServerSettings::load(settings), ServerSettings::defaultUrl());
    }

    void saveThenLoadRoundTrips() {
        QTemporaryDir dir;
        QSettings settings(dir.filePath(QStringLiteral("s.ini")), QSettings::IniFormat);
        ServerSettings::save(settings, QUrl(QStringLiteral("https://studio.example.com/")));
        QCOMPARE(ServerSettings::load(settings), QUrl(QStringLiteral("https://studio.example.com/")));
    }
};

QTEST_GUILESS_MAIN(ServerSettingsTest)
#include "server_settings_test.moc"
