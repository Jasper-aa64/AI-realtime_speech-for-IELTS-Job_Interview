#include "voice_bridge.h"

#include <QMetaObject>

namespace studio {

namespace {
VoiceBackend &backendSlot() {
    static VoiceBackend backend;
    return backend;
}
} // namespace

void setVoiceBackend(VoiceBackend backend) {
    backendSlot() = std::move(backend);
}

const VoiceBackend &voiceBackend() {
    return backendSlot();
}

VoiceBridge::VoiceBridge(std::function<bool()> trustedOrigin, const VoiceBackend &backend, QObject *parent)
    : QObject(parent), m_trustedOrigin(std::move(trustedOrigin)), m_backend(backend) {}

VoiceBridge::~VoiceBridge() {
    // stop() joins every engine thread, so no sink call can reach this object afterwards;
    // events already posted to it are dropped by Qt when it is deleted.
    if (m_engine) m_engine->stop();
}

QVariantMap VoiceBridge::status() const {
    QString reason;
    const bool trusted = m_trustedOrigin && m_trustedOrigin();
    const bool available = trusted && m_backend.available && m_backend.available(&reason);
    if (!trusted) reason = QStringLiteral("untrusted origin");
    return {{QStringLiteral("available"), available},
            {QStringLiteral("reason"), available ? QString() : reason},
            {QStringLiteral("state"), m_state}};
}

bool VoiceBridge::allowed(const char *method) {
    if (m_trustedOrigin && m_trustedOrigin()) return true;
    emit error(QStringLiteral("untrusted_origin"), QStringLiteral("%1 refused: page is not on the server origin")
                                                       .arg(QString::fromLatin1(method)));
    return false;
}

bool VoiceBridge::startSession() {
    if (!allowed("startSession")) return false;
    QString reason;
    if (!m_backend.available || !m_backend.available(&reason) || !m_backend.create) {
        emit error(QStringLiteral("unavailable"), reason.isEmpty() ? QStringLiteral("native voice unavailable") : reason);
        return false;
    }
    if (!m_engine) {
        m_engine = m_backend.create();
        if (!m_engine) {
            emit error(QStringLiteral("unavailable"), QStringLiteral("could not create the voice engine"));
            return false;
        }
        // Engine threads call the sink; hop to the GUI thread before touching Qt signals.
        m_engine->setSink([this](const VoiceEngineEvent &event) {
            QMetaObject::invokeMethod(this, [this, event] { dispatch(event); }, Qt::QueuedConnection);
        });
    }
    m_engine->start();
    return true;
}

void VoiceBridge::speak(const QString &text) {
    if (!allowed("speak")) return;
    if (!m_engine) {
        emit error(QStringLiteral("no_session"), QStringLiteral("speak before startSession"));
        return;
    }
    m_engine->speak(text);
}

void VoiceBridge::startListening() {
    if (!allowed("startListening")) return;
    if (!m_engine) {
        emit error(QStringLiteral("no_session"), QStringLiteral("startListening before startSession"));
        return;
    }
    m_engine->startListening();
}

void VoiceBridge::stopListening() {
    if (!allowed("stopListening") || !m_engine) return;
    m_engine->stopListening();
}

void VoiceBridge::endSession() {
    if (!m_engine) return;  // allowed from any origin: ending only releases the microphone
    auto engine = std::move(m_engine);
    engine->stop();
    m_state = QStringLiteral("closed");
    emit stateChanged(m_state, QStringLiteral("ended"));
}

void VoiceBridge::markTranscriptShown(const QString &note) {
    if (!allowed("markTranscriptShown") || !m_engine) return;
    m_engine->markTranscriptShown(note);
}

void VoiceBridge::dispatch(const VoiceEngineEvent &event) {
    if (event.type == QStringLiteral("state")) {
        m_state = event.state;
        emit stateChanged(event.state, event.reason);
    } else if (event.type == QStringLiteral("partial")) {
        emit partialTranscript(event.text);
    } else if (event.type == QStringLiteral("final")) {
        emit finalTranscript(event.text);
    } else if (event.type == QStringLiteral("error")) {
        emit error(event.code, event.text);
    }
}

} // namespace studio
