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
