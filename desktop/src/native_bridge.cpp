#include "native_bridge.h"

namespace studio {

NativeBridge::NativeBridge(std::function<bool()> trustedOrigin, QObject *parent)
    : QObject(parent), m_trustedOrigin(std::move(trustedOrigin)) {}

NativeBridge::NativeBridge(std::function<bool()> trustedOrigin, std::function<bool()> nativeAudio, QObject *parent)
    : QObject(parent), m_trustedOrigin(std::move(trustedOrigin)), m_nativeAudio(std::move(nativeAudio)) {}

QVariantMap NativeBridge::capabilities() const {
    const bool trusted = m_trustedOrigin && m_trustedOrigin();
    return {{QStringLiteral("protocol_version"), 1},
            {QStringLiteral("desktop"), trusted},
            {QStringLiteral("mock_interview"), trusted},
            {QStringLiteral("native_audio"), trusted && m_nativeAudio && m_nativeAudio()}};
}

} // namespace studio
