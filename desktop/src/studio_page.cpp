#include "studio_page.h"

#include <QDesktopServices>
#include <QFile>
#include <QWebChannel>
#include <QWebEngineScript>
#include <QWebEngineScriptCollection>
#include <QWebEnginePermission>

#include "navigation_policy.h"
#include "native_bridge.h"

namespace studio {

StudioPage::StudioPage(QWebEngineProfile *profile, const QUrl &server, QObject *parent)
    : QWebEnginePage(profile, parent), m_server(server) {
    auto *channel = new QWebChannel(this);
    auto *bridge = new NativeBridge([this] { return isSameOrigin(url(), m_server); }, channel);
    channel->registerObject(QStringLiteral("studioNative"), bridge);
    setWebChannel(channel, QWebEngineScript::MainWorld);
    QFile runtime(QStringLiteral(":/qtwebchannel/qwebchannel.js"));
    if (runtime.open(QIODevice::ReadOnly)) {
        QWebEngineScript script;
        script.setName(QStringLiteral("studio-webchannel-runtime"));
        script.setInjectionPoint(QWebEngineScript::DocumentCreation);
        script.setWorldId(QWebEngineScript::MainWorld);
        script.setRunsOnSubFrames(false);
        script.setSourceCode(QString::fromUtf8(runtime.readAll()));
        scripts().insert(script);
    }
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
