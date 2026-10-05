#include "studio_profile.h"

#include <QCoreApplication>
#include <QDir>
#include <QMainWindow>
#include <QStandardPaths>
#include <QStatusBar>
#include <QWebEngineDownloadRequest>
#include <QWebEngineProfile>
#include <QWebEngineScript>
#include <QWebEngineScriptCollection>
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

// QtWebEngine exposes the Web Speech API but ships no speech service: SpeechRecognition.start()
// makes Chromium kill the renderer ("No binder found for media.mojom.SpeechRecognizer").
// Hiding the constructors lets the pages take their existing "dictation unavailable" path.
QWebEngineScript hideSpeechRecognitionScript() {
    QWebEngineScript script;
    script.setName(QStringLiteral("studio-hide-speech-recognition"));
    script.setInjectionPoint(QWebEngineScript::DocumentCreation);
    script.setWorldId(QWebEngineScript::MainWorld);
    script.setRunsOnSubFrames(true);
    script.setSourceCode(QStringLiteral(
        "for (const name of ['SpeechRecognition', 'webkitSpeechRecognition']) {"
        "  try { Object.defineProperty(window, name, { value: undefined, configurable: true, writable: true }); }"
        "  catch (_error) {}"
        "}"));
    return script;
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

    profile->scripts()->insert(hideSpeechRecognitionScript());

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
