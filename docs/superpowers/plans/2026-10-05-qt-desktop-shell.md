# Qt Desktop Shell (Phases 0–1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A double-clickable macOS app `IELTS Studio.app` that hosts the existing web SPA from a configurable server inside QtWebEngine, with a native "server unreachable" page, persistent login, popups, downloads, clipboard and microphone working (audio still goes through the browser chain in this phase).

**Architecture:** A standalone CMake project under `desktop/` that depends only on Qt 6 (no vcpkg). Pure-logic units (`ServerSettings`, `navigation_policy`) and the `ErrorPage` widget are unit-tested with QtTest; the WebEngine glue (`StudioPage`, `BrowserWindow`, `createStudioProfile`) is verified by a `--smoke` command-line mode plus a manual acceptance checklist.

**Tech Stack:** Qt 6.11 from Homebrew (`Widgets`, `WebEngineWidgets`, `Test`), CMake ≥ 3.21, C++17.

**Spec:** `docs/superpowers/specs/2026-10-05-qt-desktop-studio-design.md` (§3 decisions, §5 architecture, §8 error handling, §10 phases 0–1)

## Global Constraints

- The desktop app is a client only: it does not bundle or start Python/Django (spec D2).
- Server URL is configurable; development default is `http://127.0.0.1:8767/` (spec D2).
- No API keys or secrets in the app bundle or on disk (spec D2′).
- `desktop/` must build without vcpkg: only `find_package(Qt6 ...)`. Do not touch the root `CMakeLists.txt`.
- `Info.plist` must contain `NSMicrophoneUsageDescription` (spec §8).
- Do not change anything under `web/static` or `backend_django` in this plan; `node --test tests/*.test.js` must keep passing.
- Never commit `backend_django/db.sqlite3`. Commit only on branch `ui-polish`; do not push.
- User-facing copy is Simplified Chinese.

## File Structure

```
desktop/
  CMakeLists.txt           project, studio_core library, IELTSStudio bundle, tests
  Info.plist.in            bundle metadata + microphone usage string
  README.md                build / run / smoke commands
  src/
    server_settings.h/.cpp   normalise, load and save the server origin (QSettings)
    navigation_policy.h/.cpp same-origin rules: navigation, permissions, unreachable errors
    error_page.h/.cpp        native "can't reach server" widget (retry / change server)
    studio_profile.h/.cpp    persistent QWebEngineProfile + settings + download handling
    studio_page.h/.cpp       QWebEnginePage: navigation filter, popups, permission grants
    browser_window.h/.cpp    QMainWindow: view/error stack, menus, server dialog, popups
    main.cpp                 app setup, --server / --smoke options
  tests/
    server_settings_test.cpp
    navigation_policy_test.cpp
    error_page_test.cpp
```

Build and test commands used throughout (run from the repo root
`~/Documents/trading-study/AI-realtime_speech-for-IELTS-Job_Interview`):

```bash
cmake -S desktop -B build-desktop -DCMAKE_PREFIX_PATH="$(brew --prefix qt)" -DCMAKE_BUILD_TYPE=Debug
cmake --build build-desktop -j
ctest --test-dir build-desktop --output-on-failure
```

`build-desktop/` is already ignored by `.gitignore` (`build-*/`).

---

### Task 1: Toolchain check, project scaffold and `ServerSettings`

**Files:**
- Create: `desktop/CMakeLists.txt`
- Create: `desktop/src/server_settings.h`, `desktop/src/server_settings.cpp`
- Test: `desktop/tests/server_settings_test.cpp`
- Modify: `docs/superpowers/specs/2026-10-05-qt-desktop-studio-design.md` (phase 0 step 2 wording)

**Interfaces:**
- Produces: `namespace studio { class ServerSettings { static QUrl defaultUrl(); static std::optional<QUrl> normalize(const QString &input); static QUrl load(QSettings &settings); static void save(QSettings &settings, const QUrl &url); }; }` — every URL it returns is an origin with path `/` (e.g. `https://studio.example.com/`).
- Produces: CMake target `studio_core` (static library, `PUBLIC` include dir `desktop/src`, links `Qt6::Widgets Qt6::WebEngineWidgets`) and CMake function `studio_test(name)` that builds `tests/<name>.cpp` against `studio_core` + `Qt6::Test` and registers it with CTest.

- [ ] **Step 1: Verify the Qt toolchain**

Run:
```bash
ls "$(brew --prefix qt)/lib/cmake" | grep -E '^Qt6(Widgets|WebEngineWidgets|Test)$'
```
Expected: three lines `Qt6Test`, `Qt6WebEngineWidgets`, `Qt6Widgets`. If any is missing, stop and report — `brew install qt` did not finish.

- [ ] **Step 2: Write the failing test**

`desktop/tests/server_settings_test.cpp`:
```cpp
#include <QSettings>
#include <QTemporaryDir>
#include <QtTest>

#include "server_settings.h"

using studio::ServerSettings;

class ServerSettingsTest : public QObject {
    Q_OBJECT
private slots:
    void defaultIsLocalDevServer() {
        QCOMPARE(ServerSettings::defaultUrl(), QUrl(QStringLiteral("http://127.0.0.1:8767/")));
    }

    void normalizeReducesToOrigin_data() {
        QTest::addColumn<QString>("input");
        QTest::addColumn<QString>("expected");
        QTest::newRow("bare host:port") << "127.0.0.1:8767" << "http://127.0.0.1:8767/";
        QTest::newRow("trims spaces") << "  http://localhost:8767  " << "http://localhost:8767/";
        QTest::newRow("drops path query fragment") << "https://Studio.Example.com/app?x=1#y" << "https://studio.example.com/";
        QTest::newRow("keeps https port") << "https://example.com:8443/" << "https://example.com:8443/";
    }
    void normalizeReducesToOrigin() {
        QFETCH(QString, input);
        QFETCH(QString, expected);
        const auto result = ServerSettings::normalize(input);
        QVERIFY(result.has_value());
        QCOMPARE(result->toString(), expected);
    }

    void normalizeRejectsInvalid_data() {
        QTest::addColumn<QString>("input");
        QTest::newRow("empty") << "";
        QTest::newRow("blank") << "   ";
        QTest::newRow("ftp") << "ftp://example.com";
        QTest::newRow("no host") << "http://";
        QTest::newRow("space in host") << "not a url";
    }
    void normalizeRejectsInvalid() {
        QFETCH(QString, input);
        QVERIFY(!ServerSettings::normalize(input).has_value());
    }

    void loadFallsBackToDefault() {
        QTemporaryDir dir;
        QSettings settings(dir.filePath(QStringLiteral("s.ini")), QSettings::IniFormat);
        QCOMPARE(ServerSettings::load(settings), ServerSettings::defaultUrl());
        settings.setValue(QStringLiteral("server/url"), QStringLiteral("ftp://bad"));
        QCOMPARE(ServerSettings::load(settings), ServerSettings::defaultUrl());
    }

    void saveThenLoadRoundTrips() {
        QTemporaryDir dir;
        QSettings settings(dir.filePath(QStringLiteral("s.ini")), QSettings::IniFormat);
        ServerSettings::save(settings, QUrl(QStringLiteral("https://studio.example.com/")));
        QCOMPARE(ServerSettings::load(settings), QUrl(QStringLiteral("https://studio.example.com/")));
    }
};

QTEST_GUILESS_MAIN(ServerSettingsTest)
#include "server_settings_test.moc"
```

- [ ] **Step 3: Write the CMake project and a header-only stub so the test compiles and fails**

`desktop/CMakeLists.txt`:
```cmake
cmake_minimum_required(VERSION 3.21)
project(IELTSStudioDesktop VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 6.8 REQUIRED COMPONENTS Widgets WebEngineWidgets Test)
qt_standard_project_setup()

add_library(studio_core STATIC
    src/server_settings.cpp src/server_settings.h
)
target_include_directories(studio_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(studio_core PUBLIC Qt6::Widgets Qt6::WebEngineWidgets)

enable_testing()

function(studio_test name)
    qt_add_executable(${name} tests/${name}.cpp)
    target_link_libraries(${name} PRIVATE studio_core Qt6::Test)
    add_test(NAME ${name} COMMAND ${name})
    set_tests_properties(${name} PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endfunction()

studio_test(server_settings_test)
```

`desktop/src/server_settings.h`:
```cpp
#pragma once

#include <QString>
#include <QUrl>

#include <optional>

class QSettings;

namespace studio {

// Origin of the IELTS Studio server the shell loads, always "scheme://host[:port]/".
class ServerSettings {
public:
    static QUrl defaultUrl();
    // Trims, adds "http://" when no scheme is given, accepts only http/https with a host,
    // and drops path/query/fragment. Returns nullopt for anything else.
    static std::optional<QUrl> normalize(const QString &input);
    static QUrl load(QSettings &settings);
    static void save(QSettings &settings, const QUrl &url);
};

} // namespace studio
```

`desktop/src/server_settings.cpp` (stub — returns wrong values on purpose):
```cpp
#include "server_settings.h"

#include <QSettings>

namespace studio {

QUrl ServerSettings::defaultUrl() { return {}; }
std::optional<QUrl> ServerSettings::normalize(const QString &) { return std::nullopt; }
QUrl ServerSettings::load(QSettings &) { return {}; }
void ServerSettings::save(QSettings &, const QUrl &) {}

} // namespace studio
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cmake -S desktop -B build-desktop -DCMAKE_PREFIX_PATH="$(brew --prefix qt)" -DCMAKE_BUILD_TYPE=Debug && cmake --build build-desktop -j && ctest --test-dir build-desktop --output-on-failure`
Expected: configure and build succeed; `server_settings_test` FAILS (e.g. `defaultIsLocalDevServer` compares an empty URL).

- [ ] **Step 5: Implement**

Replace `desktop/src/server_settings.cpp`:
```cpp
#include "server_settings.h"

#include <QSettings>

namespace studio {

namespace {
const QString kServerKey = QStringLiteral("server/url");
}

QUrl ServerSettings::defaultUrl() {
    return QUrl(QStringLiteral("http://127.0.0.1:8767/"));
}

std::optional<QUrl> ServerSettings::normalize(const QString &input) {
    QString text = input.trimmed();
    if (text.isEmpty()) return std::nullopt;
    if (!text.contains(QStringLiteral("://"))) text.prepend(QStringLiteral("http://"));

    const QUrl url(text, QUrl::StrictMode);
    if (!url.isValid() || url.host().isEmpty()) return std::nullopt;
    const QString scheme = url.scheme().toLower();
    if (scheme != QStringLiteral("http") && scheme != QStringLiteral("https")) return std::nullopt;

    QUrl origin;
    origin.setScheme(scheme);
    origin.setHost(url.host());
    origin.setPort(url.port());
    origin.setPath(QStringLiteral("/"));
    return origin;
}

QUrl ServerSettings::load(QSettings &settings) {
    return normalize(settings.value(kServerKey).toString()).value_or(defaultUrl());
}

void ServerSettings::save(QSettings &settings, const QUrl &url) {
    settings.setValue(kServerKey, url.toString());
}

} // namespace studio
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cmake --build build-desktop -j && ctest --test-dir build-desktop --output-on-failure`
Expected: `100% tests passed, 0 tests failed out of 1`.

- [ ] **Step 7: Fix the spec's phase 0 wording**

In `docs/superpowers/specs/2026-10-05-qt-desktop-studio-design.md`, replace the line
`2. 验证 CMake 能找到 \`Qt6::WebEngineWidgets\` / \`Qt6::WebChannel\`，旧目标 \`CppInterviewSystemQt\` 仍能编过。`
with
`2. 桌面端是独立 CMake 工程 \`desktop/\`（只依赖 Qt，不依赖 vcpkg），验证它能找到 \`Qt6::WebEngineWidgets\` 并跑通单测；根目录旧目标不动。`

- [ ] **Step 8: Commit**

```bash
git add desktop/CMakeLists.txt desktop/src/server_settings.h desktop/src/server_settings.cpp desktop/tests/server_settings_test.cpp docs/superpowers/specs/2026-10-05-qt-desktop-studio-design.md
git commit -m "feat(desktop): scaffold Qt desktop project with server settings"
```

---

### Task 2: `navigation_policy` (same-origin rules)

**Files:**
- Create: `desktop/src/navigation_policy.h`, `desktop/src/navigation_policy.cpp`
- Modify: `desktop/CMakeLists.txt` (add sources + test)
- Test: `desktop/tests/navigation_policy_test.cpp`

**Interfaces:**
- Consumes: nothing from Task 1 at the code level (URLs are plain `QUrl`).
- Produces (namespace `studio`):
  - `enum class NavigationTarget { InApp, External, Blocked };`
  - `bool isSameOrigin(const QUrl &a, const QUrl &b);` — scheme, host and effective port (80/443 defaults) equal.
  - `NavigationTarget classifyNavigation(const QUrl &target, const QUrl &server);` — same origin as server, `about:` or `blob:` → `InApp`; other `http`/`https`/`mailto` → `External`; everything else → `Blocked`.
  - `bool shouldGrantPermission(QWebEnginePermission::PermissionType type, const QUrl &origin, const QUrl &server);` — `true` only for `MediaAudioCapture` and `ClipboardReadWrite` from the server origin.
  - `bool isServerUnreachable(QWebEngineLoadingInfo::ErrorDomain domain, int errorCode);` — `true` for connection, DNS and certificate errors, and HTTP status ≥ 500.

- [ ] **Step 1: Write the failing test**

`desktop/tests/navigation_policy_test.cpp`:
```cpp
#include <QtTest>

#include "navigation_policy.h"

using namespace studio;
using Perm = QWebEnginePermission::PermissionType;

namespace {
const QUrl kServer(QStringLiteral("http://127.0.0.1:8767/"));
}

class NavigationPolicyTest : public QObject {
    Q_OBJECT
private slots:
    void sameOriginUsesDefaultPorts() {
        QVERIFY(isSameOrigin(QUrl("https://a.com/x"), QUrl("https://a.com:443/")));
        QVERIFY(isSameOrigin(QUrl("http://a.com/"), QUrl("http://a.com:80/y?z")));
        QVERIFY(!isSameOrigin(QUrl("http://a.com/"), QUrl("https://a.com/")));
        QVERIFY(!isSameOrigin(QUrl("http://a.com:8767/"), QUrl("http://a.com:8768/")));
        QVERIFY(!isSameOrigin(QUrl("http://a.com/"), QUrl("http://b.com/")));
    }

    void classify_data() {
        QTest::addColumn<QString>("target");
        QTest::addColumn<int>("expected");
        QTest::newRow("app view") << "http://127.0.0.1:8767/?view=p1" << int(NavigationTarget::InApp);
        QTest::newRow("about blank popup") << "about:blank" << int(NavigationTarget::InApp);
        QTest::newRow("blob download") << "blob:http://127.0.0.1:8767/1234" << int(NavigationTarget::InApp);
        QTest::newRow("other site") << "https://detail.design/" << int(NavigationTarget::External);
        QTest::newRow("mailto") << "mailto:a@b.c" << int(NavigationTarget::External);
        QTest::newRow("other port") << "http://127.0.0.1:8768/" << int(NavigationTarget::External);
        QTest::newRow("file") << "file:///etc/hosts" << int(NavigationTarget::Blocked);
        QTest::newRow("javascript") << "javascript:alert(1)" << int(NavigationTarget::Blocked);
    }
    void classify() {
        QFETCH(QString, target);
        QFETCH(int, expected);
        QCOMPARE(int(classifyNavigation(QUrl(target), kServer)), expected);
    }

    void permissions() {
        const QUrl own(QStringLiteral("http://127.0.0.1:8767"));
        const QUrl other(QStringLiteral("https://evil.example"));
        QVERIFY(shouldGrantPermission(Perm::MediaAudioCapture, own, kServer));
        QVERIFY(shouldGrantPermission(Perm::ClipboardReadWrite, own, kServer));
        QVERIFY(!shouldGrantPermission(Perm::MediaAudioCapture, other, kServer));
        QVERIFY(!shouldGrantPermission(Perm::MediaVideoCapture, own, kServer));
        QVERIFY(!shouldGrantPermission(Perm::Geolocation, own, kServer));
        QVERIFY(!shouldGrantPermission(Perm::Notifications, own, kServer));
    }

    void unreachable() {
        QVERIFY(isServerUnreachable(QWebEngineLoadingInfo::ConnectionErrorDomain, -102));
        QVERIFY(isServerUnreachable(QWebEngineLoadingInfo::DnsErrorDomain, -105));
        QVERIFY(isServerUnreachable(QWebEngineLoadingInfo::CertificateErrorDomain, -202));
        QVERIFY(isServerUnreachable(QWebEngineLoadingInfo::HttpStatusCodeDomain, 502));
        QVERIFY(!isServerUnreachable(QWebEngineLoadingInfo::HttpStatusCodeDomain, 404));
        QVERIFY(!isServerUnreachable(QWebEngineLoadingInfo::InternalErrorDomain, -3));
        QVERIFY(!isServerUnreachable(QWebEngineLoadingInfo::NoErrorDomain, 0));
    }
};

QTEST_GUILESS_MAIN(NavigationPolicyTest)
#include "navigation_policy_test.moc"
```

Add to `desktop/CMakeLists.txt` after `studio_test(server_settings_test)`:
```cmake
studio_test(navigation_policy_test)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cmake --build build-desktop -j`
Expected: FAIL to compile with `'navigation_policy.h' file not found`.

- [ ] **Step 3: Implement**

`desktop/src/navigation_policy.h`:
```cpp
#pragma once

#include <QUrl>
#include <QWebEngineLoadingInfo>
#include <QWebEnginePermission>

namespace studio {

enum class NavigationTarget { InApp, External, Blocked };

bool isSameOrigin(const QUrl &a, const QUrl &b);

// Where a main-frame navigation should go: stay in the shell, open in the system browser, or be dropped.
NavigationTarget classifyNavigation(const QUrl &target, const QUrl &server);

// Only the server's own pages may use the microphone and the clipboard.
bool shouldGrantPermission(QWebEnginePermission::PermissionType type, const QUrl &origin, const QUrl &server);

// Failures that mean "the server can't be reached", as opposed to aborted loads or app-level 4xx.
bool isServerUnreachable(QWebEngineLoadingInfo::ErrorDomain domain, int errorCode);

} // namespace studio
```

`desktop/src/navigation_policy.cpp`:
```cpp
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
```

Add the sources to `studio_core` in `desktop/CMakeLists.txt`:
```cmake
add_library(studio_core STATIC
    src/server_settings.cpp src/server_settings.h
    src/navigation_policy.cpp src/navigation_policy.h
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cmake --build build-desktop -j && ctest --test-dir build-desktop --output-on-failure`
Expected: `100% tests passed, 0 tests failed out of 2`.

- [ ] **Step 5: Commit**

```bash
git add desktop/CMakeLists.txt desktop/src/navigation_policy.h desktop/src/navigation_policy.cpp desktop/tests/navigation_policy_test.cpp
git commit -m "feat(desktop): same-origin navigation and permission policy"
```

---

### Task 3: `ErrorPage` widget

**Files:**
- Create: `desktop/src/error_page.h`, `desktop/src/error_page.cpp`
- Modify: `desktop/CMakeLists.txt`
- Test: `desktop/tests/error_page_test.cpp`

**Interfaces:**
- Produces: `class studio::ErrorPage : public QWidget` with
  - `explicit ErrorPage(QWidget *parent = nullptr);`
  - `void showFor(const QUrl &server, const QString &detail);` — sets the detail line to `"<server> · <detail>"`.
  - `QString detailText() const;`
  - signals `void retryRequested();` and `void changeServerRequested();`
  - child buttons with object names `retryButton` ("重试") and `changeServerButton` ("更改服务器地址…").

- [ ] **Step 1: Write the failing test**

`desktop/tests/error_page_test.cpp`:
```cpp
#include <QPushButton>
#include <QSignalSpy>
#include <QtTest>

#include "error_page.h"

class ErrorPageTest : public QObject {
    Q_OBJECT
private slots:
    void showsServerAndDetail() {
        studio::ErrorPage page;
        page.showFor(QUrl(QStringLiteral("https://studio.example.com/")), QStringLiteral("连接被拒绝"));
        QVERIFY(page.detailText().contains(QStringLiteral("https://studio.example.com/")));
        QVERIFY(page.detailText().contains(QStringLiteral("连接被拒绝")));
    }

    void buttonsEmitSignals() {
        studio::ErrorPage page;
        QSignalSpy retry(&page, &studio::ErrorPage::retryRequested);
        QSignalSpy change(&page, &studio::ErrorPage::changeServerRequested);

        auto *retryButton = page.findChild<QPushButton *>(QStringLiteral("retryButton"));
        auto *changeButton = page.findChild<QPushButton *>(QStringLiteral("changeServerButton"));
        QVERIFY(retryButton);
        QVERIFY(changeButton);
        QCOMPARE(retryButton->text(), QStringLiteral("重试"));

        QTest::mouseClick(retryButton, Qt::LeftButton);
        QTest::mouseClick(changeButton, Qt::LeftButton);
        QCOMPARE(retry.count(), 1);
        QCOMPARE(change.count(), 1);
    }
};

QTEST_MAIN(ErrorPageTest)
#include "error_page_test.moc"
```

Add to `desktop/CMakeLists.txt`:
```cmake
studio_test(error_page_test)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cmake --build build-desktop -j`
Expected: FAIL to compile with `'error_page.h' file not found`.

- [ ] **Step 3: Implement**

`desktop/src/error_page.h`:
```cpp
#pragma once

#include <QUrl>
#include <QWidget>

class QLabel;

namespace studio {

// Shown instead of the web view when the server can't be reached.
class ErrorPage : public QWidget {
    Q_OBJECT
public:
    explicit ErrorPage(QWidget *parent = nullptr);

    void showFor(const QUrl &server, const QString &detail);
    QString detailText() const;

signals:
    void retryRequested();
    void changeServerRequested();

private:
    QLabel *m_detail = nullptr;
};

} // namespace studio
```

`desktop/src/error_page.cpp`:
```cpp
#include "error_page.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>

namespace studio {

ErrorPage::ErrorPage(QWidget *parent) : QWidget(parent) {
    auto *title = new QLabel(QStringLiteral("连不上 IELTS Studio 服务器"), this);
    QFont titleFont = title->font();
    titleFont.setPointSizeF(titleFont.pointSizeF() * 1.6);
    titleFont.setWeight(QFont::Medium);
    title->setFont(titleFont);
    title->setAlignment(Qt::AlignCenter);

    m_detail = new QLabel(this);
    m_detail->setAlignment(Qt::AlignCenter);
    m_detail->setWordWrap(true);
    m_detail->setTextInteractionFlags(Qt::TextSelectableByMouse);
    m_detail->setForegroundRole(QPalette::PlaceholderText);

    auto *retry = new QPushButton(QStringLiteral("重试"), this);
    retry->setObjectName(QStringLiteral("retryButton"));
    retry->setDefault(true);
    auto *change = new QPushButton(QStringLiteral("更改服务器地址…"), this);
    change->setObjectName(QStringLiteral("changeServerButton"));
    connect(retry, &QPushButton::clicked, this, &ErrorPage::retryRequested);
    connect(change, &QPushButton::clicked, this, &ErrorPage::changeServerRequested);

    auto *buttons = new QHBoxLayout;
    buttons->addStretch();
    buttons->addWidget(change);
    buttons->addWidget(retry);
    buttons->addStretch();

    auto *layout = new QVBoxLayout(this);
    layout->addStretch();
    layout->addWidget(title);
    layout->addSpacing(8);
    layout->addWidget(m_detail);
    layout->addSpacing(20);
    layout->addLayout(buttons);
    layout->addStretch();
}

void ErrorPage::showFor(const QUrl &server, const QString &detail) {
    m_detail->setText(server.toString() + QStringLiteral(" · ") + detail);
}

QString ErrorPage::detailText() const {
    return m_detail->text();
}

} // namespace studio
```

Add the sources to `studio_core`:
```cmake
add_library(studio_core STATIC
    src/server_settings.cpp src/server_settings.h
    src/navigation_policy.cpp src/navigation_policy.h
    src/error_page.cpp src/error_page.h
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cmake --build build-desktop -j && ctest --test-dir build-desktop --output-on-failure`
Expected: `100% tests passed, 0 tests failed out of 3`.

- [ ] **Step 5: Commit**

```bash
git add desktop/CMakeLists.txt desktop/src/error_page.h desktop/src/error_page.cpp desktop/tests/error_page_test.cpp
git commit -m "feat(desktop): native server-unreachable page"
```

---

### Task 4: The app — profile, page, window, `main` and `--smoke`

**Files:**
- Create: `desktop/src/studio_profile.h`, `desktop/src/studio_profile.cpp`
- Create: `desktop/src/studio_page.h`, `desktop/src/studio_page.cpp`
- Create: `desktop/src/browser_window.h`, `desktop/src/browser_window.cpp`
- Create: `desktop/src/main.cpp`, `desktop/Info.plist.in`
- Modify: `desktop/CMakeLists.txt`

**Interfaces:**
- Consumes: `ServerSettings` (Task 1), `classifyNavigation`, `shouldGrantPermission`, `isServerUnreachable`, `NavigationTarget` (Task 2), `ErrorPage` (Task 3).
- Produces:
  - `QWebEngineProfile *studio::createStudioProfile(QObject *parent);` — persistent profile named `IELTSStudio`, downloads go to the user's Downloads folder.
  - `class studio::StudioPage : public QWebEnginePage` — `StudioPage(QWebEngineProfile *profile, const QUrl &server, QObject *parent = nullptr)`, `void setServer(const QUrl &server)`, `void setWindowFactory(std::function<QWebEnginePage *()> factory)`, signal `void openedExternally()`.
  - `class studio::BrowserWindow : public QMainWindow` — `enum class Role { Main, Popup }`, `BrowserWindow(QWebEngineProfile *profile, const QUrl &server, Role role, QWidget *parent = nullptr)`, `StudioPage *page() const`, `void loadServer()`, signal `void loadResult(bool ok, const QUrl &url)` (main window only).
  - Executable bundle `IELTS Studio.app` (target `IELTSStudio`) with options `--server <url>` (this run only) and `--smoke` (print `LOAD_OK <url>` / `LOAD_FAIL <url>` / `LOAD_TIMEOUT`, exit 0 / 1 / 3).

- [ ] **Step 1: Profile**

`desktop/src/studio_profile.h`:
```cpp
#pragma once

class QObject;
class QWebEngineProfile;

namespace studio {

// One persistent profile for every window: cookies (login), localStorage and cache survive restarts.
QWebEngineProfile *createStudioProfile(QObject *parent);

} // namespace studio
```

`desktop/src/studio_profile.cpp`:
```cpp
#include "studio_profile.h"

#include <QCoreApplication>
#include <QDir>
#include <QMainWindow>
#include <QStandardPaths>
#include <QStatusBar>
#include <QWebEngineDownloadRequest>
#include <QWebEngineProfile>
#include <QWebEngineSettings>
#include <QWebEngineView>

namespace studio {

namespace {
void announceDownload(QWebEngineDownloadRequest *download) {
    auto *view = QWebEngineView::forPage(download->page());
    auto *window = view ? qobject_cast<QMainWindow *>(view->window()) : nullptr;
    if (!window) return;
    const QString path = QDir(download->downloadDirectory()).filePath(download->downloadFileName());
    window->statusBar()->showMessage(QStringLiteral("已下载：") + QDir::toNativeSeparators(path), 6000);
}
}

QWebEngineProfile *createStudioProfile(QObject *parent) {
    auto *profile = new QWebEngineProfile(QStringLiteral("IELTSStudio"), parent);
    profile->setPersistentCookiesPolicy(QWebEngineProfile::ForcePersistentCookies);
    profile->setHttpUserAgent(profile->httpUserAgent() + QStringLiteral(" IELTSStudioDesktop/")
                              + QCoreApplication::applicationVersion());

    QWebEngineSettings *settings = profile->settings();
    settings->setAttribute(QWebEngineSettings::JavascriptCanOpenWindows, true);
    settings->setAttribute(QWebEngineSettings::JavascriptCanAccessClipboard, true);
    settings->setAttribute(QWebEngineSettings::JavascriptCanPaste, true);
    settings->setAttribute(QWebEngineSettings::LocalStorageEnabled, true);
    // Examiner TTS starts playing without a fresh click.
    settings->setAttribute(QWebEngineSettings::PlaybackRequiresUserGesture, false);

    QObject::connect(profile, &QWebEngineProfile::downloadRequested, profile,
                     [](QWebEngineDownloadRequest *download) {
        download->setDownloadDirectory(QStandardPaths::writableLocation(QStandardPaths::DownloadLocation));
        QObject::connect(download, &QWebEngineDownloadRequest::isFinishedChanged, download, [download] {
            if (download->state() == QWebEngineDownloadRequest::DownloadCompleted) announceDownload(download);
        });
        download->accept();
    });
    return profile;
}

} // namespace studio
```

- [ ] **Step 2: Page**

`desktop/src/studio_page.h`:
```cpp
#pragma once

#include <QUrl>
#include <QWebEnginePage>

#include <functional>

namespace studio {

// Keeps the shell on the server's origin, sends other links to the system browser,
// opens popups through a window factory, and grants mic/clipboard to the server only.
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
```

`desktop/src/studio_page.cpp`:
```cpp
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
```

- [ ] **Step 3: Window**

`desktop/src/browser_window.h`:
```cpp
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
```

`desktop/src/browser_window.cpp`:
```cpp
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
    QMenu *app = menuBar()->addMenu(QStringLiteral("IELTS Studio"));
    QAction *server = app->addAction(QStringLiteral("服务器地址…"), this, &BrowserWindow::promptForServer);
    server->setShortcut(QKeySequence::Preferences);
    server->setMenuRole(QAction::PreferencesRole);
    QAction *reload = app->addAction(QStringLiteral("重新加载"), this, [this] {
        if (m_stack->currentWidget() == m_error) emit m_error->retryRequested();
        else m_page->triggerAction(QWebEnginePage::Reload);
    });
    reload->setShortcut(QKeySequence::Refresh);
    QAction *quit = app->addAction(QStringLiteral("退出"), qApp, &QApplication::quit);
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
        event->accept();
        QApplication::quit();
        return;
    }
    QMainWindow::closeEvent(event);
}

} // namespace studio
```

- [ ] **Step 4: `main.cpp` and bundle metadata**

`desktop/src/main.cpp`:
```cpp
#include <QApplication>
#include <QCommandLineParser>
#include <QSettings>
#include <QTextStream>
#include <QTimer>

#include "browser_window.h"
#include "server_settings.h"
#include "studio_profile.h"

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);
    QApplication::setApplicationName(QStringLiteral("IELTS Studio"));
    QApplication::setOrganizationName(QStringLiteral("IELTS Studio"));
    QApplication::setApplicationVersion(QStringLiteral(STUDIO_VERSION));

    QCommandLineParser parser;
    parser.addHelpOption();
    QCommandLineOption serverOption(QStringLiteral("server"),
                                    QStringLiteral("Use this server for this run only."), QStringLiteral("url"));
    QCommandLineOption smokeOption(QStringLiteral("smoke"),
                                   QStringLiteral("Load the server once, print LOAD_OK/LOAD_FAIL and exit."));
    parser.addOptions({serverOption, smokeOption});
    parser.process(app);

    QSettings settings;
    QUrl server = studio::ServerSettings::load(settings);
    if (parser.isSet(serverOption)) {
        const auto override = studio::ServerSettings::normalize(parser.value(serverOption));
        if (!override) {
            QTextStream(stderr) << "Invalid --server value: " << parser.value(serverOption) << Qt::endl;
            return 2;
        }
        server = *override;
    }

    QWebEngineProfile *profile = studio::createStudioProfile(&app);
    studio::BrowserWindow window(profile, server, studio::BrowserWindow::Role::Main);

    if (parser.isSet(smokeOption)) {
        QObject::connect(&window, &studio::BrowserWindow::loadResult, &app, [](bool ok, const QUrl &url) {
            QTextStream(stdout) << (ok ? "LOAD_OK " : "LOAD_FAIL ") << url.toString() << Qt::endl;
            QCoreApplication::exit(ok ? 0 : 1);
        });
        QTimer::singleShot(30000, &app, [] {
            QTextStream(stdout) << "LOAD_TIMEOUT" << Qt::endl;
            QCoreApplication::exit(3);
        });
    }

    window.show();
    window.loadServer();
    return app.exec();
}
```

`desktop/Info.plist.in`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>zh_CN</string>
    <key>CFBundleExecutable</key>
    <string>${MACOSX_BUNDLE_EXECUTABLE_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>${MACOSX_BUNDLE_GUI_IDENTIFIER}</string>
    <key>CFBundleName</key>
    <string>${MACOSX_BUNDLE_BUNDLE_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>${MACOSX_BUNDLE_BUNDLE_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>${MACOSX_BUNDLE_SHORT_VERSION_STRING}</string>
    <key>CFBundleVersion</key>
    <string>${MACOSX_BUNDLE_BUNDLE_VERSION}</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>IELTS Studio 需要使用麦克风来录制你的口语回答。</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
</dict>
</plist>
```

Replace the `add_library(studio_core ...)` block in `desktop/CMakeLists.txt` and add the bundle target right after it:
```cmake
add_library(studio_core STATIC
    src/server_settings.cpp src/server_settings.h
    src/navigation_policy.cpp src/navigation_policy.h
    src/error_page.cpp src/error_page.h
    src/studio_profile.cpp src/studio_profile.h
    src/studio_page.cpp src/studio_page.h
    src/browser_window.cpp src/browser_window.h
)
target_include_directories(studio_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(studio_core PUBLIC Qt6::Widgets Qt6::WebEngineWidgets)

qt_add_executable(IELTSStudio MACOSX_BUNDLE src/main.cpp)
set_target_properties(IELTSStudio PROPERTIES
    OUTPUT_NAME "IELTS Studio"
    MACOSX_BUNDLE_INFO_PLIST ${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in
    MACOSX_BUNDLE_GUI_IDENTIFIER com.ieltsstudio.desktop
    MACOSX_BUNDLE_BUNDLE_NAME "IELTS Studio"
    MACOSX_BUNDLE_BUNDLE_VERSION ${PROJECT_VERSION}
    MACOSX_BUNDLE_SHORT_VERSION_STRING ${PROJECT_VERSION}
)
target_compile_definitions(IELTSStudio PRIVATE STUDIO_VERSION="${PROJECT_VERSION}")
target_link_libraries(IELTSStudio PRIVATE studio_core)
```

- [ ] **Step 5: Build and run the unit tests**

Run: `cmake -S desktop -B build-desktop -DCMAKE_PREFIX_PATH="$(brew --prefix qt)" -DCMAKE_BUILD_TYPE=Debug && cmake --build build-desktop -j && ctest --test-dir build-desktop --output-on-failure`
Expected: build succeeds, `build-desktop/IELTS Studio.app` exists, `100% tests passed, 0 tests failed out of 3`.

- [ ] **Step 6: Smoke — reachable server**

Precondition: `curl -s http://127.0.0.1:8767/api/health/` returns `{"ok": true, ...}`. If not, start the dev server (from the repo root):
```bash
set -a && . ./.env && set +a && .venv-django/bin/python backend_django/manage.py runserver 127.0.0.1:8767 --noreload
```
(run it in the background; do not touch any Windows service).

Run: `"build-desktop/IELTS Studio.app/Contents/MacOS/IELTS Studio" --server http://127.0.0.1:8767 --smoke`
Expected: prints `LOAD_OK http://127.0.0.1:8767/` (possibly with a query string) and exits 0.

- [ ] **Step 7: Smoke — unreachable server**

Run: `"build-desktop/IELTS Studio.app/Contents/MacOS/IELTS Studio" --server http://127.0.0.1:59999 --smoke; echo "exit=$?"`
Expected: prints `LOAD_FAIL http://127.0.0.1:59999/` then `exit=1`. (Use a closed ordinary port: Chromium blocks ports like 9 with `ERR_UNSAFE_PORT`, which is not a connection error.)

- [ ] **Step 8: Commit**

```bash
git add desktop/CMakeLists.txt desktop/Info.plist.in desktop/src/studio_profile.h desktop/src/studio_profile.cpp desktop/src/studio_page.h desktop/src/studio_page.cpp desktop/src/browser_window.h desktop/src/browser_window.cpp desktop/src/main.cpp
git commit -m "feat(desktop): QtWebEngine shell with error page, popups, downloads and smoke mode"
```

---

### Task 5: Manual acceptance and docs

**Files:**
- Create: `desktop/README.md`
- Modify: `docs/index.md` (one row pointing to `desktop/README.md`)

**Interfaces:**
- Consumes: the built `IELTS Studio.app` from Task 4.
- Produces: a checked acceptance list (recorded in the commit message) and build docs.

- [ ] **Step 1: Launch the app like a user**

Run: `open "build-desktop/IELTS Studio.app"` (the dev server from Task 4 Step 6 must be running; the saved server defaults to `http://127.0.0.1:8767/`).

- [ ] **Step 2: Walk the checklist; take a screenshot for each visual item**

Use the computer-use tools (or `screencapture -l`) on the `IELTS Studio` window. Every item must pass; if one fails, fix it in the relevant Task 4 file, rebuild, and re-check before moving on.

1. Home page renders with the unified design (serif headings, sidebar groups 口语/写作).
2. Log in with the local test account (credentials in the scratchpad `test-login.txt`; never echo them), quit with Cmd+Q, relaunch → still logged in.
3. Switch views from the sidebar: 首页, P1, P2, P3, 历史, 写作, 语料库 all render.
4. P1 practice: click start → macOS asks for microphone access for "IELTS Studio" (first run) → after allowing, the level meter moves when speaking.
5. Open a P1/P2 corpus window (the button that calls `openCorpusWindow`) → a second window opens on the same origin; Cmd+W closes it.
6. In a speaking report, use the export/download action → the status bar shows `已下载：…` and the file exists in `~/Downloads`.
7. Copy something via an in-app copy button, paste into another app → clipboard works; Cmd+C / Cmd+V work in text fields.
8. System dark mode on → the page switches to the dark theme (`prefers-color-scheme`). If it does not, record it as a follow-up for phase 3 instead of blocking.
9. Cmd+, → change the server to `http://127.0.0.1:59999` → native error page "连不上 IELTS Studio 服务器" with 重试 / 更改服务器地址…; change back to `http://127.0.0.1:8767` → app loads again.
10. Clicking a link to another site opens it in the default browser, not inside the app.
11. Renderer crash recovery: run `pkill -f QtWebEngineProcess` while the app is open → the page reloads by itself.

- [ ] **Step 3: Write `desktop/README.md`**

```markdown
# IELTS Studio 桌面端（Qt）

Qt 6 + QtWebEngine 外壳，加载服务器上的 IELTS Studio 网页界面。设计与计划见
`docs/superpowers/specs/2026-10-05-qt-desktop-studio-design.md`。

## 构建

需要 `brew install qt`（Qt 6，含 WebEngine）。在仓库根目录：

    cmake -S desktop -B build-desktop -DCMAKE_PREFIX_PATH="$(brew --prefix qt)" -DCMAKE_BUILD_TYPE=Debug
    cmake --build build-desktop -j
    ctest --test-dir build-desktop --output-on-failure

## 运行

    open "build-desktop/IELTS Studio.app"

- 服务器地址：菜单「IELTS Studio → 服务器地址…」（Cmd+,），默认 `http://127.0.0.1:8767/`。
- 只对这一次运行换服务器：`"build-desktop/IELTS Studio.app/Contents/MacOS/IELTS Studio" --server <url>`。
- 冒烟检查：加 `--smoke`，加载成功打印 `LOAD_OK` 退出码 0，服务器不可达打印 `LOAD_FAIL` 退出码 1，30 秒超时退出码 3。

登录状态、localStorage 存在 Qt 的持久化 profile `IELTSStudio` 里（`~/Library/Application Support/IELTS Studio/`）。
```

- [ ] **Step 4: Link it from `docs/index.md`**

Add this section after the `## ops/` table in `docs/index.md`:
```markdown
## desktop/ — Qt 桌面端

| 文档 | 用途 |
| --- | --- |
| [../desktop/README.md](../desktop/README.md) | 桌面端构建、运行、冒烟检查 |
```

- [ ] **Step 5: Re-run all automated checks**

Run:
```bash
ctest --test-dir build-desktop --output-on-failure
node --test tests/*.test.js
```
Expected: `100% tests passed` for ctest; node tests all pass (no web files changed).

- [ ] **Step 6: Commit**

```bash
git add desktop/README.md docs/index.md
git commit -m "docs(desktop): build/run guide; phase 1 acceptance passed" -m "Checked: home render, persistent login, view switching, mic permission, popup window, download, clipboard, dark mode, error page + server change, external links."
```

(Edit the `-m` body to list any item recorded as a follow-up instead of passing.)

---

## Later plans (not part of this one)

Each phase gets its own plan when we reach it, because each depends on findings from the previous one:

- Phase 2 — native audio bridge (`NativeAudioBridge`, `native-bridge.js`, `POST /api/realtime/credentials`); starts by checking whether Volcengine realtime dialogue supports temporary credentials.
- Phase 3 — mode switcher (desktop only), after frame-by-frame observation of detail.design.
- Phase 4 — mock interview (question bank, resume/JD custom interview, reports).
- Phase 5 — VPS deployment (parallel track, needs a purchased server).
- Phase 6 — packaging (`macdeployqt`, signing).

---

## Execution notes (2026-10-05)

Deviations found while executing; the code in `desktop/` is the source of truth.

- `browser_window.h` needed `class QWebEnginePage;` forward-declared (compile error otherwise).
- Smoke "unreachable" must use an ordinary closed port (59999). Port 9 fails with `ERR_UNSAFE_PORT` (`HttpErrorDomain`), which is deliberately not treated as "server unreachable".
- **Login lost on quick quit.** Chromium flushes cookies to disk every ~30 s; the final flush only happens if the page and profile are destroyed in order while `QApplication` is alive. Fixes:
  - `main.cpp` creates the profile without a parent, deletes the main window, drains events, deletes the profile, drains again, then returns.
  - On macOS, AppKit's Quit path closes windows and calls `exit()` without returning from `exec()`. The main window's `closeEvent` therefore ignores the close and queues `QCoreApplication::exit(0)`, so every quit path returns through `main()`.
- Menus: our menu titled "IELTS Studio" duplicated the macOS application menu → renamed **视图**. "服务器地址…" uses `ApplicationSpecificRole` (PreferencesRole renamed it to "Preferences..."). `qtbase_zh_CN` translations are loaded so 隐藏/退出/取消/确定 are Chinese.

Acceptance (Task 5), driven through `QTWEBENGINE_REMOTE_DEBUGGING` + accessibility:
1 ✅ unified design renders · 2 ✅ login survives Cmd+Q (after the fix above) · 3 ✅ all 10 sidebar views · 4 ⏳ mic: page permission granted, macOS TCC prompt needs the user to click Allow · 5 ✅ popup window opens/closes, page freed · 6 ✅ download + status bar · 7 ⏳ clipboard: blocked only because the window was not focused during background testing; needs a focused manual check · 8 ⏳ dark mode: shell follows Qt's colour scheme; real system-dark check needs the user (fallback if it fails: `--blink-settings=preferredColorScheme=0` chosen at launch from `QStyleHints::colorScheme()`) · 9 ✅ error page + server dialog + saved setting · 10 ✅ external link → system browser · 11 ✅ renderer crash → auto reload, still logged in.
