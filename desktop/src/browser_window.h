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

// Main window (menus, server address, error page) or a popup opened by window.open().
// Popups are children of the main window so they close with it and never outlive the profile.
class BrowserWindow : public QMainWindow {
    Q_OBJECT
public:
    enum class Role { Main, Popup };

    BrowserWindow(QWebEngineProfile *profile, const QUrl &server, Role role, QWidget *parent = nullptr);

    StudioPage *page() const;
    void loadServer();

signals:
    // Main window only: the server finished loading (true) or turned out unreachable (false).
    void loadResult(bool ok, const QUrl &url);

protected:
    void closeEvent(QCloseEvent *event) override;

private:
    void onLoadingChanged(const QWebEngineLoadingInfo &info);
    void promptForServer();
    void buildMenus();
    QWebEnginePage *openPopup();

    QWebEngineProfile *m_profile;
    QUrl m_server;
    QUrl m_failedUrl;
    Role m_role;
    QStackedWidget *m_stack;
    QWebEngineView *m_view;
    StudioPage *m_page;
    ErrorPage *m_error;
};

} // namespace studio
