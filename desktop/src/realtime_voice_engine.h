#pragma once

#include "voice_bridge.h"

namespace studio {

// VoiceBackend backed by interview::voice::VoiceSession (PortAudio + Volcano realtime dialogue).
// available(): the engine can initialise PortAudio with input and output devices, the config at configPath
// loads and has X-Api credentials, and the microphone permission is granted.
VoiceBackend realtimeVoiceBackend(const QString &configPath);

} // namespace studio
