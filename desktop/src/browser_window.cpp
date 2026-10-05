#include "browser_window.h"

#include <QAction>
#include <QApplication>
#include <QCloseEvent>
#include <QInputDialog>
#include <QMenuBar>
#include <QMessageBox>
#include <QSettings>
#include <QStackedWidget>
#include <QStatusBar>
#include <QTimer>
#include <QWebEngineLoadingInfo>
#include <QWebEngineView>

#include "error_page.h"
#include "navigation_policy.h"
#include "server_settings.h"
#include "studio_page.h"

namespace studio {

namespace {
const QString kGeometryKey = QStringLiteral("window/geometry");
}

BrowserWindow::BrowserWindow(QWebEngineProfile *profile, const QUrl &server, Role role, QWidget *parent)
    : QMainWindow(parent), m_profile(profile), m_server(server), m_role(role),
      m_stack(new QStackedWidget(this)), m_view(new QWebEngineView(this)),
      m_page(new StudioPage(profile, server, m_view)), m_error(new ErrorPage(this)) {
    setWindowTitle(QStringLiteral("IELTS Studio"));
    m_view->setPage(m_page);
    m_stack->addWidget(m_view);
    m_stack->addWidget(m_error);
    setCentralWidget(m_stack);

    // The status bar only appears while it has something to say (download notices).
    connect(statusBar(), &QStatusBar::messageChanged, this, [this](const QString &message) {
        statusBar()->setVisible(!message.isEmpty());
    });
    statusBar()->hide();

    m_page->setWindowFactory([this] { return openPopup(); });
    connect(m_page, &QWebEnginePage::loadingChanged, this, &BrowserWindow::onLoadingChanged);
    connect(m_page, &QWebEnginePage::titleChanged, this, [this](const QString &title) {
        if (m_role == Role::Popup && !title.isEmpty()) setWindowTitle(title);
    });
    connect(m_page, &QWebEnginePage::windowCloseRequested, this, &QWidget::close);
    connect(m_page, &QWebEnginePage::renderProcessTerminated, this,
            [this](QWebEnginePage::RenderProcessTerminationStatus status, int) {
        // Spec §8: a crashed renderer reloads the page instead of leaving a blank window.
        if (status != QWebEnginePage::NormalTerminationStatus)
            QTimer::singleShot(0, m_page, [this] { m_page->triggerAction(QWebEnginePage::Reload); });
    });
    connect(m_page, &StudioPage::openedExternally, this, [this] {
        // A popup created only to reach an external site has nothing left to show.
        if (m_role == Role::Popup && (m_page->url().isEmpty() || m_page->url().scheme() == QStringLiteral("about")))
            close();
    });
    connect(m_error, &ErrorPage::retryRequested, this, [this] {
        m_stack->setCurrentWidget(m_view);
        m_page->load(m_failedUrl.isValid() ? m_failedUrl : m_server);
    });
    connect(m_error, &ErrorPage::changeServerRequested, this, &BrowserWindow::promptForServer);

    if (m_role == Role::Main) {
        buildMenus();
        QSettings settings;
        if (!restoreGeometry(settings.value(kGeometryKey).toByteArray())) resize(1360, 880);
    } else {
        setAttribute(Qt::WA_DeleteOnClose);
        if (parent) resize(parent->size() * 0.9);
    }
}

StudioPage *BrowserWindow::page() const {
    return m_page;
}

void BrowserWindow::loadServer() {
    m_stack->setCurrentWidget(m_view);
    m_page->load(m_server);
}

void BrowserWindow::onLoadingChanged(const QWebEngineLoadingInfo &info) {
    if (info.status() == QWebEngineLoadingInfo::LoadSucceededStatus) {
        m_failedUrl.clear();
        m_stack->setCurrentWidget(m_view);
        if (m_role == Role::Main) emit loadResult(true, info.url());
        return;
    }
    if (info.status() != QWebEngineLoadingInfo::LoadFailedStatus) return;
    if (!isServerUnreachable(info.errorDomain(), info.errorCode())) return;
    m_failedUrl = info.url();
    m_error->showFor(m_server, info.errorString());
    m_stack->setCurrentWidget(m_error);
    if (m_role == Role::Main) emit loadResult(false, info.url());
}

void BrowserWindow::promptForServer() {
    bool accepted = false;
    const QString input = QInputDialog::getText(
        this, QStringLiteral("服务器地址"),
        QStringLiteral("IELTS Studio 服务器地址（例如 https://studio.example.com）："),
        QLineEdit::Normal, m_server.toString(), &accepted);
    if (!accepted) return;
    const auto server = ServerSettings::normalize(input);
    if (!server) {
        QMessageBox::warning(this, QStringLiteral("服务器地址"),
                             QStringLiteral("地址无效：需要 http:// 或 https:// 开头的网址。"));
        return;
    }
    QSettings settings;
    ServerSettings::save(settings, *server);
    m_server = *server;
    m_page->setServer(m_server);
    m_failedUrl.clear();
    loadServer();
}

void BrowserWindow::buildMenus() {
    // On macOS the server and quit items move into the application menu; the rest stays under 视图.
    QMenu *view = menuBar()->addMenu(QStringLiteral("视图"));
    QAction *server = view->addAction(QStringLiteral("服务器地址…"), this, &BrowserWindow::promptForServer);
    server->setShortcut(QKeySequence::Preferences);
    // ApplicationSpecificRole keeps our Chinese title (PreferencesRole would rename it "Preferences...").
    server->setMenuRole(QAction::ApplicationSpecificRole);
    QAction *reload = view->addAction(QStringLiteral("重新加载"), this, [this] {
        if (m_stack->currentWidget() == m_error) emit m_error->retryRequested();
        else m_page->triggerAction(QWebEnginePage::Reload);
    });
    reload->setShortcut(QKeySequence::Refresh);
    QAction *quit = view->addAction(QStringLiteral("退出"), qApp, &QApplication::quit);
    quit->setShortcut(QKeySequence::Quit);
    quit->setMenuRole(QAction::QuitRole);

    // macOS routes Cmd+C/V/X/A/Z through the Edit menu.
    QMenu *edit = menuBar()->addMenu(QStringLiteral("编辑"));
    const QList<QPair<QWebEnginePage::WebAction, QKeySequence::StandardKey>> editActions = {
        {QWebEnginePage::Undo, QKeySequence::Undo}, {QWebEnginePage::Redo, QKeySequence::Redo},
        {QWebEnginePage::Cut, QKeySequence::Cut}, {QWebEnginePage::Copy, QKeySequence::Copy},
        {QWebEnginePage::Paste, QKeySequence::Paste}, {QWebEnginePage::SelectAll, QKeySequence::SelectAll},
    };
    for (const auto &[webAction, key] : editActions) {
        QAction *action = m_page->action(webAction);
        action->setShortcut(key);
        edit->addAction(action);
    }

    QMenu *window = menuBar()->addMenu(QStringLiteral("窗口"));
    QAction *closeWindow = window->addAction(QStringLiteral("关闭窗口"), qApp, [] {
        if (QWidget *active = QApplication::activeWindow()) active->close();
    });
    closeWindow->setShortcut(QKeySequence::Close);
}

QWebEnginePage *BrowserWindow::openPopup() {
    QWidget *host = m_role == Role::Main ? this : parentWidget();
    auto *popup = new BrowserWindow(m_profile, m_server, Role::Popup, host);
    popup->show();
    return popup->page();
}

void BrowserWindow::closeEvent(QCloseEvent *event) {
    if (m_role == Role::Main) {
        QSettings settings;
        settings.setValue(kGeometryKey, saveGeometry());
        // Refuse the close and end the event loop instead: AppKit's own terminate path calls exit()
        // without returning from exec(), which skips main()'s ordered teardown and loses the cookie flush.
        event->ignore();
        QMetaObject::invokeMethod(qApp, [] { QCoreApplication::exit(0); }, Qt::QueuedConnection);
        return;
    }
    QMainWindow::closeEvent(event);
}

} // namespace studio
