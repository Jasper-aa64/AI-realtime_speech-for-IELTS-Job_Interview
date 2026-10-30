#include "realtime_voice_engine.h"

#include "voice_settings.h"
#include "voice/voice_session.h"
#include "voice/injecting_device.h"

#include <QCoreApplication>
#include <QDir>
#include <QPermissions>
#include <QProcessEnvironment>

#include <atomic>
#include <mutex>

namespace studio {

namespace {

using interview::voice::VoiceEvent;
using interview::voice::VoiceSession;
using interview::voice::VoiceState;

interview::voice::VoiceOptions loadOptions(const QString &configPath) {
    auto options = interview::voice::LoadVoiceOptions(configPath.toStdString());
    if (options.metrics_dir.empty()) options.metrics_dir = VoiceSettings::defaultMetricsDir().toStdString();
    QDir().mkpath(QString::fromStdString(options.metrics_dir));
    return options;
}

VoiceEngineEvent convert(const VoiceEvent &e) {
    VoiceEngineEvent out;
    out.state = QString::fromLatin1(interview::voice::ToString(e.state));
    out.text = QString::fromStdString(e.text);
    out.code = QString::fromStdString(e.code);
    switch (e.type) {
    case VoiceEvent::Type::kState: out.type = QStringLiteral("state"); break;
    case VoiceEvent::Type::kPartial: out.type = QStringLiteral("partial"); break;
    case VoiceEvent::Type::kFinal: out.type = QStringLiteral("final"); break;
    case VoiceEvent::Type::kError: out.type = QStringLiteral("error"); break;
    // The page drives its flow from these, so they travel as state changes with a reason.
    case VoiceEvent::Type::kSpeakStarted: out.type = QStringLiteral("state"); out.reason = QStringLiteral("audio_started"); break;
    case VoiceEvent::Type::kSpeakFinished: out.type = QStringLiteral("state"); out.reason = QStringLiteral("speak_finished"); break;
    case VoiceEvent::Type::kUserStarted: out.type = QStringLiteral("state"); out.reason = QStringLiteral("user_started"); break;
    case VoiceEvent::Type::kUserStopped: out.type = QStringLiteral("state"); out.reason = QStringLiteral("user_stopped"); break;
    }
    return out;
}

class RealtimeVoiceEngine : public VoiceEngine {
public:
    explicit RealtimeVoiceEngine(QString configPath) : m_configPath(std::move(configPath)) {}
    ~RealtimeVoiceEngine() override { stop(); }

    void setSink(Sink sink) override { m_sink = std::move(sink); }

    void start() override {
        if (m_session) {
            const auto s = m_session->state();
            if (s != VoiceState::kError && s != VoiceState::kClosed) return;  // already running
            m_session->Stop();
            m_session.reset();
        }
        interview::voice::VoiceOptions options;
        try {
            options = loadOptions(m_configPath);
        } catch (const std::exception &e) {
            if (m_sink) m_sink({QStringLiteral("error"), QStringLiteral("error"), QString::fromUtf8(e.what()),
                                QStringLiteral("config"), {}});
            return;
        }
        std::unique_ptr<interview::voice::AudioDevice> device;
        try {
            device = interview::voice::CreatePortAudioDevice(options.input_device, options.output_device);
        } catch (const std::exception &e) {
            if (m_sink) m_sink({QStringLiteral("error"), QStringLiteral("error"), QString::fromUtf8(e.what()),
                                QStringLiteral("audio_device"), {}});
            return;
        }
        // Acceptance switch: STUDIO_VOICE_TEST_ANSWER_WAV mixes that answer into the real microphone signal each
        // time listening starts, so the whole page flow can be measured without anyone speaking or loud playback.
        m_injector = nullptr;
        m_testAnswer.clear();
        const auto env = QProcessEnvironment::systemEnvironment();
        const QString wav = env.value(QStringLiteral("STUDIO_VOICE_TEST_ANSWER_WAV"));
        if (!wav.isEmpty()) {
            const double gain = env.value(QStringLiteral("STUDIO_VOICE_TEST_ANSWER_GAIN"), QStringLiteral("0.5")).toDouble();
            m_testAnswer = interview::voice::LoadWav16k(wav.toStdString(), gain);
            auto injector = std::make_unique<interview::voice::InjectingAudioDevice>(std::move(device));
            m_injector = injector.get();
            device = std::move(injector);
        }
        m_session = std::make_unique<VoiceSession>(std::move(options), std::move(device));
        auto sink = m_sink;
        m_session->SetListener([sink](const VoiceEvent &e) {
            if (sink) sink(convert(e));
        });
        m_session->Start();
    }

    void speak(const QString &text) override {
        if (m_session) m_session->Speak(text.toStdString());
    }
    void startListening() override {
        if (!m_session) return;
        m_session->StartListening();
        if (m_injector && !m_testAnswer.empty()) m_injector->Inject(m_testAnswer);
    }
    void stopListening() override {
        if (m_session) m_session->StopListening();
    }
    void stop() override {
        if (!m_session) return;
        m_session->Stop();
        m_session.reset();
    }
    void markTranscriptShown(const QString &note) override {
        if (m_session) m_session->MarkTranscriptShown(note.toStdString());
    }

private:
    QString m_configPath;
    Sink m_sink;
    std::unique_ptr<VoiceSession> m_session;
    interview::voice::InjectingAudioDevice *m_injector = nullptr;  // owned by m_session
    std::vector<int16_t> m_testAnswer;
};

QString permissionText(Qt::PermissionStatus status) {
    switch (status) {
    case Qt::PermissionStatus::Granted: return QStringLiteral("granted");
    case Qt::PermissionStatus::Denied: return QStringLiteral("denied");
    case Qt::PermissionStatus::Undetermined: return QStringLiteral("not asked yet");
    }
    return QStringLiteral("unknown");
}

} // namespace

VoiceBackend realtimeVoiceBackend(const QString &configPath) {
    VoiceBackend backend;
    backend.available = [configPath](QString *reason) {
        try {
            const auto options = interview::voice::LoadVoiceOptions(configPath.toStdString());
            if (!interview::voice::HasCredentials(options)) {
                if (reason) *reason = QStringLiteral("no credentials in %1").arg(configPath);
                return false;
            }
        } catch (const std::exception &e) {
            if (reason) *reason = QString::fromUtf8(e.what());
            return false;
        }
        // PortAudio probing costs a few ms; once it worked, keep the answer for this run.
        static std::atomic<bool> engineOk{false};
        if (!engineOk.load()) {
            std::string why;
            if (!interview::voice::ProbePortAudio(&why)) {
                if (reason) *reason = QString::fromStdString(why);
                return false;
            }
            engineOk.store(true);
        }
        if (qApp) {
            const auto status = qApp->checkPermission(QMicrophonePermission{});
            if (status != Qt::PermissionStatus::Granted) {
                if (reason) *reason = QStringLiteral("microphone permission %1").arg(permissionText(status));
                return false;
            }
        }
        return true;
    };
    backend.create = [configPath]() -> std::unique_ptr<VoiceEngine> {
        return std::make_unique<RealtimeVoiceEngine>(configPath);
    };
    return backend;
}

} // namespace studio
