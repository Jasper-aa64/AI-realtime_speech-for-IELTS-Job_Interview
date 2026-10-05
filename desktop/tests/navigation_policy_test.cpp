#include <QtTest>

#include "navigation_policy.h"

using namespace studio;
using Perm = QWebEnginePermission::PermissionType;

namespace {
const QUrl kServer(QStringLiteral("http://127.0.0.1:8767/"));
}

class NavigationPolicyTest : public QObject {
    Q_OBJECT
private slots:
    void sameOriginUsesDefaultPorts() {
        QVERIFY(isSameOrigin(QUrl("https://a.com/x"), QUrl("https://a.com:443/")));
        QVERIFY(isSameOrigin(QUrl("http://a.com/"), QUrl("http://a.com:80/y?z")));
        QVERIFY(!isSameOrigin(QUrl("http://a.com/"), QUrl("https://a.com/")));
        QVERIFY(!isSameOrigin(QUrl("http://a.com:8767/"), QUrl("http://a.com:8768/")));
        QVERIFY(!isSameOrigin(QUrl("http://a.com/"), QUrl("http://b.com/")));
    }

    void classify_data() {
        QTest::addColumn<QString>("target");
        QTest::addColumn<int>("expected");
        QTest::newRow("app view") << "http://127.0.0.1:8767/?view=p1" << int(NavigationTarget::InApp);
        QTest::newRow("about blank popup") << "about:blank" << int(NavigationTarget::InApp);
        QTest::newRow("blob download") << "blob:http://127.0.0.1:8767/1234" << int(NavigationTarget::InApp);
        QTest::newRow("other site") << "https://detail.design/" << int(NavigationTarget::External);
        QTest::newRow("mailto") << "mailto:a@b.c" << int(NavigationTarget::External);
        QTest::newRow("other port") << "http://127.0.0.1:8768/" << int(NavigationTarget::External);
        QTest::newRow("file") << "file:///etc/hosts" << int(NavigationTarget::Blocked);
        QTest::newRow("javascript") << "javascript:alert(1)" << int(NavigationTarget::Blocked);
    }
    void classify() {
        QFETCH(QString, target);
        QFETCH(int, expected);
        QCOMPARE(int(classifyNavigation(QUrl(target), kServer)), expected);
    }

    void popupRoute_data() {
        QTest::addColumn<QString>("target");
        QTest::addColumn<int>("expected");
        QTest::newRow("opener still preparing") << "about:blank" << int(PopupRoute::Wait);
        QTest::newRow("no url yet") << "" << int(PopupRoute::Wait);
        QTest::newRow("app view opens in main") << "http://127.0.0.1:8767/?view=p1Corpus" << int(PopupRoute::LoadInMain);
        QTest::newRow("other site to browser") << "https://detail.design/" << int(PopupRoute::OpenExternally);
        QTest::newRow("blob document dropped") << "blob:http://127.0.0.1:8767/1234" << int(PopupRoute::Drop);
        QTest::newRow("data document dropped") << "data:text/html,hi" << int(PopupRoute::Drop);
        QTest::newRow("file dropped") << "file:///etc/hosts" << int(PopupRoute::Drop);
    }
    void popupRoute() {
        QFETCH(QString, target);
        QFETCH(int, expected);
        QCOMPARE(int(routePopupNavigation(QUrl(target), kServer)), expected);
    }

    void permissions() {
        const QUrl own(QStringLiteral("http://127.0.0.1:8767"));
        const QUrl other(QStringLiteral("https://evil.example"));
        QVERIFY(shouldGrantPermission(Perm::MediaAudioCapture, own, kServer));
        QVERIFY(shouldGrantPermission(Perm::ClipboardReadWrite, own, kServer));
        QVERIFY(!shouldGrantPermission(Perm::MediaAudioCapture, other, kServer));
        QVERIFY(!shouldGrantPermission(Perm::MediaVideoCapture, own, kServer));
        QVERIFY(!shouldGrantPermission(Perm::Geolocation, own, kServer));
        QVERIFY(!shouldGrantPermission(Perm::Notifications, own, kServer));
    }

    void unreachable() {
        QVERIFY(isServerUnreachable(QWebEngineLoadingInfo::ConnectionErrorDomain, -102));
        QVERIFY(isServerUnreachable(QWebEngineLoadingInfo::DnsErrorDomain, -105));
        QVERIFY(isServerUnreachable(QWebEngineLoadingInfo::CertificateErrorDomain, -202));
        QVERIFY(isServerUnreachable(QWebEngineLoadingInfo::HttpStatusCodeDomain, 502));
        QVERIFY(!isServerUnreachable(QWebEngineLoadingInfo::HttpStatusCodeDomain, 404));
        QVERIFY(!isServerUnreachable(QWebEngineLoadingInfo::InternalErrorDomain, -3));
        QVERIFY(!isServerUnreachable(QWebEngineLoadingInfo::NoErrorDomain, 0));
    }
};

QTEST_GUILESS_MAIN(NavigationPolicyTest)
#include "navigation_policy_test.moc"
