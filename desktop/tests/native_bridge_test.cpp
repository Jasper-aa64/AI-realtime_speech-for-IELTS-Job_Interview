#include <QtTest>

#include <memory>
#include <thread>

#include "native_bridge.h"
#include "voice_bridge.h"

namespace {

// Records calls; the test pushes engine events from a plain std::thread, like the real engine's control thread.
struct FakeEngineLog {
    QStringList calls;
    studio::VoiceEngine::Sink sink;
    int stops = 0;
};

class FakeEngine : public studio::VoiceEngine {
public:
    explicit FakeEngine(std::shared_ptr<FakeEngineLog> log) : m_log(std::move(log)) {}
    ~FakeEngine() override { m_log->calls << QStringLiteral("destroyed"); }
    void setSink(Sink sink) override { m_log->sink = std::move(sink); }
    void start() override { m_log->calls << QStringLiteral("start"); }
    void speak(const QString &text) override { m_log->calls << QStringLiteral("speak:") + text; }
    void startListening() override { m_log->calls << QStringLiteral("listen"); }
    void stopListening() override { m_log->calls << QStringLiteral("stopListen"); }
    void stop() override {
        ++m_log->stops;
        m_log->calls << QStringLiteral("stop");
    }
    void markTranscriptShown(const QString &note) override { m_log->calls << QStringLiteral("shown:") + note; }

private:
    std::shared_ptr<FakeEngineLog> m_log;
};

studio::VoiceBackend fakeBackend(std::shared_ptr<FakeEngineLog> log, bool *available) {
    studio::VoiceBackend backend;
    backend.available = [available](QString *reason) {
        if (!*available && reason) *reason = QStringLiteral("microphone permission denied");
        return *available;
    };
    backend.create = [log]() -> std::unique_ptr<studio::VoiceEngine> { return std::make_unique<FakeEngine>(log); };
    return backend;
}

void emitFromOtherThread(const studio::VoiceEngine::Sink &sink, const studio::VoiceEngineEvent &event) {
    std::thread([sink, event] { sink(event); }).join();
}

} // namespace

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

    // native_audio follows the voice backend, and is never true for a foreign origin.
    void nativeAudioFollowsVoiceBackend() {
        bool trusted = true;
        bool voice = true;
        studio::NativeBridge bridge([&trusted] { return trusted; }, [&voice] { return voice; });
        QVERIFY(bridge.capabilities().value("native_audio").toBool());
        voice = false;
        QVERIFY(!bridge.capabilities().value("native_audio").toBool());
        voice = true;
        trusted = false;
        QVERIFY(!bridge.capabilities().value("native_audio").toBool());
    }

    void voiceBridgeForwardsCallsAndSignals() {
        auto log = std::make_shared<FakeEngineLog>();
        bool available = true;
        studio::VoiceBridge bridge([] { return true; }, fakeBackend(log, &available));
        QSignalSpy states(&bridge, &studio::VoiceBridge::stateChanged);
        QSignalSpy partials(&bridge, &studio::VoiceBridge::partialTranscript);
        QSignalSpy finals(&bridge, &studio::VoiceBridge::finalTranscript);
        QSignalSpy errors(&bridge, &studio::VoiceBridge::error);

        QVERIFY(bridge.status().value("available").toBool());
        QVERIFY(bridge.startSession());
        bridge.speak(QStringLiteral("第一题"));
        bridge.startListening();
        bridge.stopListening();
        bridge.markTranscriptShown(QStringLiteral("t1"));
        QCOMPARE(log->calls, (QStringList{"start", "speak:第一题", "listen", "stopListen", "shown:t1"}));
        QVERIFY(log->sink);

        // Engine events arrive on a non-GUI thread and must reach the page on the GUI thread.
        QThread *signalThread = nullptr;
        connect(&bridge, &studio::VoiceBridge::finalTranscript, this, [&signalThread] { signalThread = QThread::currentThread(); });
        emitFromOtherThread(log->sink, {QStringLiteral("state"), QStringLiteral("ready"), {}, {}, QStringLiteral("speak_finished")});
        emitFromOtherThread(log->sink, {QStringLiteral("partial"), QStringLiteral("listening"), QStringLiteral("我觉得"), {}, {}});
        emitFromOtherThread(log->sink, {QStringLiteral("final"), QStringLiteral("ready"), QStringLiteral("我觉得是这样"), {}, {}});
        emitFromOtherThread(log->sink, {QStringLiteral("error"), QStringLiteral("error"), QStringLiteral("realtime connection closed"),
                                        QStringLiteral("disconnected"), {}});
        // Queued: nothing is emitted until the GUI event loop runs.
        QCOMPARE(states.count(), 0);
        QTRY_COMPARE(errors.count(), 1);
        QCOMPARE(states.count(), 1);
        QCOMPARE(states.at(0).at(0).toString(), QStringLiteral("ready"));
        QCOMPARE(states.at(0).at(1).toString(), QStringLiteral("speak_finished"));
        QCOMPARE(partials.at(0).at(0).toString(), QStringLiteral("我觉得"));
        QCOMPARE(finals.at(0).at(0).toString(), QStringLiteral("我觉得是这样"));
        QCOMPARE(errors.at(0).at(0).toString(), QStringLiteral("disconnected"));
        QCOMPARE(signalThread, QThread::currentThread());
        QCOMPARE(bridge.status().value("state").toString(), QStringLiteral("ready"));

        bridge.endSession();
        QCOMPARE(log->stops, 1);
        QVERIFY(log->calls.contains("destroyed"));
        QCOMPARE(states.last().at(0).toString(), QStringLiteral("closed"));
    }

    void voiceBridgeRefusesForeignOrigin() {
        auto log = std::make_shared<FakeEngineLog>();
        bool available = true;
        bool trusted = false;
        studio::VoiceBridge bridge([&trusted] { return trusted; }, fakeBackend(log, &available));
        QSignalSpy errors(&bridge, &studio::VoiceBridge::error);
        QVERIFY(!bridge.status().value("available").toBool());
        QVERIFY(!bridge.startSession());
        bridge.speak(QStringLiteral("x"));
        QVERIFY(log->calls.isEmpty());
        QCOMPARE(errors.count(), 2);
        QCOMPARE(errors.at(0).at(0).toString(), QStringLiteral("untrusted_origin"));
    }

    void voiceBridgeReportsWhyUnavailable() {
        auto log = std::make_shared<FakeEngineLog>();
        bool available = false;
        studio::VoiceBridge bridge([] { return true; }, fakeBackend(log, &available));
        QSignalSpy errors(&bridge, &studio::VoiceBridge::error);
        const auto status = bridge.status();
        QVERIFY(!status.value("available").toBool());
        QCOMPARE(status.value("reason").toString(), QStringLiteral("microphone permission denied"));
        QVERIFY(!bridge.startSession());
        QCOMPARE(errors.at(0).at(0).toString(), QStringLiteral("unavailable"));
        QVERIFY(log->calls.isEmpty());
    }

    // Destroying the bridge (page closed) stops a running engine.
    void voiceBridgeStopsEngineOnDestruction() {
        auto log = std::make_shared<FakeEngineLog>();
        bool available = true;
        {
            studio::VoiceBridge bridge([] { return true; }, fakeBackend(log, &available));
            QVERIFY(bridge.startSession());
        }
        QCOMPARE(log->stops, 1);
        QVERIFY(log->calls.contains("destroyed"));
    }
};
QTEST_GUILESS_MAIN(NativeBridgeTest)
#include "native_bridge_test.moc"
