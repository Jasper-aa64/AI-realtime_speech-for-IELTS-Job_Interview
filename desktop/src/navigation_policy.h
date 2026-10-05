#pragma once

#include <QUrl>
#include <QWebEngineLoadingInfo>
#include <QWebEnginePermission>

namespace studio {

enum class NavigationTarget { InApp, External, Blocked };

// The shell has a single window, so window.open()/target=_blank never get one of their own:
// the first real navigation of a would-be popup is redirected into the main window or the system browser.
enum class PopupRoute { Wait, LoadInMain, OpenExternally, Drop };

bool isSameOrigin(const QUrl &a, const QUrl &b);

// Where a main-frame navigation should go: stay in the shell, open in the system browser, or be dropped.
NavigationTarget classifyNavigation(const QUrl &target, const QUrl &server);

// Where a would-be popup's navigation goes. about:blank is the opener still preparing it (Wait);
// blob:/data: documents have no in-app home, so they are dropped rather than replacing the app.
PopupRoute routePopupNavigation(const QUrl &target, const QUrl &server);

// Only the server's own pages may use the microphone and the clipboard.
bool shouldGrantPermission(QWebEnginePermission::PermissionType type, const QUrl &origin, const QUrl &server);

// Failures that mean "the server can't be reached", as opposed to aborted loads or app-level 4xx.
bool isServerUnreachable(QWebEngineLoadingInfo::ErrorDomain domain, int errorCode);

} // namespace studio
