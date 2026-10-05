#pragma once

#include <QObject>
#include <QVariantMap>
#include <functional>

namespace studio {

// Control metadata only: no PCM, microphone access, or provider credentials.
class NativeBridge : public QObject {
    Q_OBJECT
public:
    explicit NativeBridge(std::function<bool()> trustedOrigin, QObject *parent = nullptr);
    Q_INVOKABLE QVariantMap capabilities() const;
private:
    std::function<bool()> m_trustedOrigin;
};

} // namespace studio
