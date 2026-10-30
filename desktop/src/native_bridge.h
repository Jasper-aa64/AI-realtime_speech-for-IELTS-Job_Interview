#pragma once

#include <QObject>
#include <QVariantMap>
#include <functional>

namespace studio {

// Control metadata only: no PCM, microphone access, or provider credentials.
// native_audio is true only when nativeAudio() says the realtime voice engine can run (engine initialises,
// local config has credentials, microphone granted); the voice controls themselves live on "studioVoice".
class NativeBridge : public QObject {
    Q_OBJECT
public:
    explicit NativeBridge(std::function<bool()> trustedOrigin, QObject *parent = nullptr);
    NativeBridge(std::function<bool()> trustedOrigin, std::function<bool()> nativeAudio, QObject *parent = nullptr);
    Q_INVOKABLE QVariantMap capabilities() const;
private:
    std::function<bool()> m_trustedOrigin;
    std::function<bool()> m_nativeAudio;
};

} // namespace studio
