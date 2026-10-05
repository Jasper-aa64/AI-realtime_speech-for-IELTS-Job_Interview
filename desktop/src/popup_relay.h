#pragma once

#include <QUrl>
#include <QWebEnginePage>

#include "navigation_policy.h"

namespace studio {

// Stand-in page handed to window.open()/target=_blank. It never shows: its first real navigation
// is reported through routed() (see routePopupNavigation) and refused, and the owner deletes it.
class PopupRelay : public QWebEnginePage {
    Q_OBJECT
public:
    PopupRelay(QWebEngineProfile *profile, const QUrl &server, QObject *parent = nullptr);

signals:
    void routed(studio::PopupRoute route, const QUrl &url);

protected:
    bool acceptNavigationRequest(const QUrl &url, NavigationType type, bool isMainFrame) override;

private:
    QUrl m_server;
    bool m_done = false;
};

} // namespace studio
