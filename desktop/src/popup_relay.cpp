#include "popup_relay.h"

namespace studio {

PopupRelay::PopupRelay(QWebEngineProfile *profile, const QUrl &server, QObject *parent)
    : QWebEnginePage(profile, parent), m_server(server) {}

bool PopupRelay::acceptNavigationRequest(const QUrl &url, NavigationType, bool isMainFrame) {
    if (!isMainFrame || m_done) return false;
    const PopupRoute route = routePopupNavigation(url, m_server);
    if (route == PopupRoute::Wait) return true;
    m_done = true;
    emit routed(route, url);
    return false;
}

} // namespace studio
