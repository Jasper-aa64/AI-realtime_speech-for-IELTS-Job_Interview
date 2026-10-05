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
