#include <QtTest>
#include "native_bridge.h"

class NativeBridgeTest : public QObject {
    Q_OBJECT
private slots:
    void exposesOnlyAvailableCapabilities() {
        bool trusted = true;
        studio::NativeBridge bridge([&trusted] { return trusted; });
        const auto ready = bridge.capabilities();
        QCOMPARE(ready.value("protocol_version").toInt(), 1);
        QVERIFY(ready.value("desktop").toBool());
        QVERIFY(ready.value("mock_interview").toBool());
        QVERIFY(!ready.value("native_audio").toBool());
        trusted = false;
        const auto foreign = bridge.capabilities();
        QVERIFY(!foreign.value("desktop").toBool());
        QVERIFY(!foreign.value("mock_interview").toBool());
    }
};
QTEST_APPLESS_MAIN(NativeBridgeTest)
#include "native_bridge_test.moc"
