#include "native_bridge.h"

namespace studio {

NativeBridge::NativeBridge(std::function<bool()> trustedOrigin, QObject *parent)
    : QObject(parent), m_trustedOrigin(std::move(trustedOrigin)) {}

QVariantMap NativeBridge::capabilities() const {
    const bool trusted = m_trustedOrigin && m_trustedOrigin();
    return {{QStringLiteral("protocol_version"), 1},
            {QStringLiteral("desktop"), trusted},
            {QStringLiteral("mock_interview"), trusted},
            {QStringLiteral("native_audio"), false}};
}

} // namespace studio
