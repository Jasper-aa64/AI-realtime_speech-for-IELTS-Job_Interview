#include "studio_page.h"

#include <QDesktopServices>
#include <QWebEnginePermission>

#include "navigation_policy.h"

namespace studio {

StudioPage::StudioPage(QWebEngineProfile *profile, const QUrl &server, QObject *parent)
    : QWebEnginePage(profile, parent), m_server(server) {
    connect(this, &QWebEnginePage::permissionRequested, this, [this](QWebEnginePermission permission) {
        if (shouldGrantPermission(permission.permissionType(), permission.origin(), m_server))
            permission.grant();
        else
            permission.deny();
    });
}

void StudioPage::setServer(const QUrl &server) {
    m_server = server;
}

void StudioPage::setWindowFactory(std::function<QWebEnginePage *()> factory) {
    m_windowFactory = std::move(factory);
}

bool StudioPage::acceptNavigationRequest(const QUrl &url, NavigationType, bool isMainFrame) {
    if (!isMainFrame) return true;
    switch (classifyNavigation(url, m_server)) {
    case NavigationTarget::InApp:
        return true;
    case NavigationTarget::External:
        QDesktopServices::openUrl(url);
        emit openedExternally();
        return false;
    case NavigationTarget::Blocked:
        return false;
    }
    return false;
}

QWebEnginePage *StudioPage::createWindow(WebWindowType) {
    return m_windowFactory ? m_windowFactory() : nullptr;
}

} // namespace studio
