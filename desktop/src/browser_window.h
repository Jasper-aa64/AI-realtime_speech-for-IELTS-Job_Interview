#pragma once

#include <QMainWindow>
#include <QUrl>

class QStackedWidget;
class QWebEngineLoadingInfo;
class QWebEnginePage;
class QWebEngineProfile;
class QWebEngineView;

namespace studio {

class ErrorPage;
class StudioPage;

// The one app window (menus, server address, error page). window.open() never gets a window of its own:
// a PopupRelay redirects it here or to the system browser.
class BrowserWindow : public QMainWindow {
    Q_OBJECT
public:
    BrowserWindow(QWebEngineProfile *profile, const QUrl &server, QWidget *parent = nullptr);

    StudioPage *page() const;
    void loadServer();

signals:
    // The server finished loading (true) or turned out unreachable (false).
    void loadResult(bool ok, const QUrl &url);

protected:
    void closeEvent(QCloseEvent *event) override;

private:
    void onLoadingChanged(const QWebEngineLoadingInfo &info);
    void promptForServer();
    void buildMenus();
    QWebEnginePage *openRelay();

    QWebEngineProfile *m_profile;
    QUrl m_server;
    QUrl m_failedUrl;
    QStackedWidget *m_stack;
    QWebEngineView *m_view;
    StudioPage *m_page;
    ErrorPage *m_error;
};

} // namespace studio
