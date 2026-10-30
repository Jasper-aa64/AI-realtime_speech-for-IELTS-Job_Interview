#include "voice_settings.h"

#include <QDir>
#include <QSettings>

namespace studio {

namespace {
const QString kConfigPathKey = QStringLiteral("voice/configPath");
}

QString VoiceSettings::defaultConfigPath() {
    return QDir::homePath() + QStringLiteral("/.ielts-studio/realtime_voice.json");
}

QString VoiceSettings::configPath(QSettings &settings) {
    const QString stored = settings.value(kConfigPathKey).toString().trimmed();
    return stored.isEmpty() ? defaultConfigPath() : stored;
}

void VoiceSettings::setConfigPath(QSettings &settings, const QString &path) {
    settings.setValue(kConfigPathKey, path);
}

QString VoiceSettings::defaultMetricsDir() {
    return QDir::homePath() + QStringLiteral("/Library/Logs/IELTS Studio/voice");
}

} // namespace studio
