#pragma once

#include <QUrl>
#include <QWebEnginePage>

#include <functional>

namespace studio {

// Keeps the shell on the server's origin, sends other links to the system browser,
// hands window.open() to a factory (a redirecting PopupRelay), and grants mic/clipboard to the server only.
class StudioPage : public QWebEnginePage {
    Q_OBJECT
public:
    StudioPage(QWebEngineProfile *profile, const QUrl &server, QObject *parent = nullptr);

    void setServer(const QUrl &server);
    void setWindowFactory(std::function<QWebEnginePage *()> factory);

signals:
    // A main-frame navigation was handed to the system browser instead of loading here.
    void openedExternally();

protected:
    bool acceptNavigationRequest(const QUrl &url, NavigationType type, bool isMainFrame) override;
    QWebEnginePage *createWindow(WebWindowType type) override;

private:
    QUrl m_server;
    std::function<QWebEnginePage *()> m_windowFactory;
};

} // namespace studio
