#pragma once

#include <QObject>
#include <QString>
#include <QVariantMap>

#include <functional>
#include <memory>

namespace studio {

// One engine event, already converted to Qt types. type: state / partial / final / error.
// reason (for state) says what caused it: speak_finished, user_stopped, connected, …
struct VoiceEngineEvent {
    QString type;
    QString state;
    QString text;
    QString code;
    QString reason;
};

// What the bridge needs from a realtime voice engine. The real one wraps interview::voice::VoiceSession
// (realtime_voice_engine.cpp); tests use a fake. Methods return at once; the sink may be called from any thread.
class VoiceEngine {
public:
    using Sink = std::function<void(const VoiceEngineEvent &)>;
    virtual ~VoiceEngine() = default;
    virtual void setSink(Sink sink) = 0;
    virtual void start() = 0;
    virtual void speak(const QString &text) = 0;
    virtual void startListening() = 0;
    virtual void stopListening() = 0;
    // Blocks until the session is closed (bounded by the engine's stop timeout).
    virtual void stop() = 0;
    virtual void markTranscriptShown(const QString &note) = 0;
};

// Process-wide hooks set by main(): whether native voice can work on this machine, and how to make an engine.
struct VoiceBackend {
    // True only when the engine can initialise, the local config has credentials and the microphone is granted.
    // Writes the first failing condition to *reason.
    std::function<bool(QString *reason)> available;
    std::function<std::unique_ptr<VoiceEngine>()> create;
};

void setVoiceBackend(VoiceBackend backend);
const VoiceBackend &voiceBackend();

// Registered on the page's QWebChannel as "studioVoice". Control only: no PCM and no credentials cross the
// bridge (same rule as NativeBridge). Every method checks the page is still on the server's origin.
class VoiceBridge : public QObject {
    Q_OBJECT
public:
    VoiceBridge(std::function<bool()> trustedOrigin, const VoiceBackend &backend, QObject *parent = nullptr);
    ~VoiceBridge() override;

    // {available, reason, state}
    Q_INVOKABLE QVariantMap status() const;
    // Opens a session; false (with an error signal) when unavailable or the origin is not trusted.
    Q_INVOKABLE bool startSession();
    Q_INVOKABLE void speak(const QString &text);
    Q_INVOKABLE void startListening();
    Q_INVOKABLE void stopListening();
    Q_INVOKABLE void endSession();
    // The page displayed the final transcript; only logged for timing.
    Q_INVOKABLE void markTranscriptShown(const QString &note);

signals:
    void stateChanged(const QString &state, const QString &reason);
    void partialTranscript(const QString &text);
    void finalTranscript(const QString &text);
    void error(const QString &code, const QString &message);

private:
    bool allowed(const char *method);
    void dispatch(const VoiceEngineEvent &event);

    std::function<bool()> m_trustedOrigin;
    VoiceBackend m_backend;
    std::unique_ptr<VoiceEngine> m_engine;
    QString m_state = QStringLiteral("idle");
};

} // namespace studio
