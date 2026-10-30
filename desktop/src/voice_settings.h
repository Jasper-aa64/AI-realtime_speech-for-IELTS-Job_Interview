#pragma once

#include <QString>

class QSettings;

namespace studio {

// Where the local realtime-voice config (Volcano credentials etc.) lives. Never in the repo, never sent to the
// page. Default ~/.ielts-studio/realtime_voice.json; override with the "voice/configPath" setting.
class VoiceSettings {
public:
    static QString defaultConfigPath();
    static QString configPath(QSettings &settings);
    static void setConfigPath(QSettings &settings, const QString &path);
    // Timing logs when the config names no voice.metrics_dir: ~/Library/Logs/IELTS Studio/voice
    static QString defaultMetricsDir();
};

} // namespace studio
