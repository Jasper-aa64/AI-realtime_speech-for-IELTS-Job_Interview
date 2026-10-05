#include "navigation_policy.h"

namespace studio {

namespace {
int effectivePort(const QUrl &url) {
    return url.port(url.scheme().compare(QStringLiteral("https"), Qt::CaseInsensitive) == 0 ? 443 : 80);
}
}

bool isSameOrigin(const QUrl &a, const QUrl &b) {
    return a.scheme().compare(b.scheme(), Qt::CaseInsensitive) == 0
        && a.host().compare(b.host(), Qt::CaseInsensitive) == 0
        && effectivePort(a) == effectivePort(b);
}

NavigationTarget classifyNavigation(const QUrl &target, const QUrl &server) {
    const QString scheme = target.scheme().toLower();
    if (scheme == QStringLiteral("about") || scheme == QStringLiteral("blob")) return NavigationTarget::InApp;
    if (isSameOrigin(target, server)) return NavigationTarget::InApp;
    if (scheme == QStringLiteral("http") || scheme == QStringLiteral("https") || scheme == QStringLiteral("mailto"))
        return NavigationTarget::External;
    return NavigationTarget::Blocked;
}

PopupRoute routePopupNavigation(const QUrl &target, const QUrl &server) {
    const QString scheme = target.scheme().toLower();
    if (target.isEmpty() || scheme == QStringLiteral("about")) return PopupRoute::Wait;
    if (scheme == QStringLiteral("blob") || scheme == QStringLiteral("data")) return PopupRoute::Drop;
    switch (classifyNavigation(target, server)) {
    case NavigationTarget::InApp: return PopupRoute::LoadInMain;
    case NavigationTarget::External: return PopupRoute::OpenExternally;
    case NavigationTarget::Blocked: return PopupRoute::Drop;
    }
    return PopupRoute::Drop;
}

bool shouldGrantPermission(QWebEnginePermission::PermissionType type, const QUrl &origin, const QUrl &server) {
    if (!isSameOrigin(origin, server)) return false;
    return type == QWebEnginePermission::PermissionType::MediaAudioCapture
        || type == QWebEnginePermission::PermissionType::ClipboardReadWrite;
}

bool isServerUnreachable(QWebEngineLoadingInfo::ErrorDomain domain, int errorCode) {
    switch (domain) {
    case QWebEngineLoadingInfo::ConnectionErrorDomain:
    case QWebEngineLoadingInfo::DnsErrorDomain:
    case QWebEngineLoadingInfo::CertificateErrorDomain:
        return true;
    case QWebEngineLoadingInfo::HttpStatusCodeDomain:
        return errorCode >= 500;
    default:
        return false;
    }
}

} // namespace studio
