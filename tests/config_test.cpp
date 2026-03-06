#include <gtest/gtest.h>
#include "common/config.h"

using interview::common::Config;

TEST(ConfigTest, LoadDefaultConfig)
{
    Config& config = Config::Instance();

    EXPECT_NO_THROW(
        config.LoadFromFile(
            std::string(PROJECT_ROOT) + "/config/default_config.json"
        );
    );

    // audio input
    EXPECT_EQ(config.input_audio_config.chunk, 3200);
    EXPECT_EQ(config.input_audio_config.channels, 1);
    EXPECT_EQ(config.input_audio_config.sample_rate, 16000);
    EXPECT_EQ(config.input_audio_config.bit_size, 16);
    EXPECT_EQ(config.input_audio_config.format, "pcm");

    // audio output
    EXPECT_EQ(config.output_audio_config.chunk, 4800);
    EXPECT_EQ(config.output_audio_config.channels, 1);
    EXPECT_EQ(config.output_audio_config.sample_rate, 24000);
    EXPECT_EQ(config.output_audio_config.bit_size, 16);
    EXPECT_EQ(config.output_audio_config.format, "pcm");

    // websocket
    EXPECT_EQ(
        config.ws_config.base_url,
        "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
    );

    // dialog
    EXPECT_EQ(config.dialog_config.city, "北京");
    EXPECT_EQ(config.dialog_config.recv_timeout, 10);
    EXPECT_EQ(config.dialog_config.input_mod, "audio");

    // tts
    EXPECT_EQ(config.tts_config.sample_rate, 24000);
    EXPECT_EQ(config.tts_config.channel, 1);
    EXPECT_EQ(config.tts_config.format, "pcm");

    // asr
    EXPECT_EQ(config.asr_config.end_smooth_window_ms, 2000);
    EXPECT_EQ(config.asr_config.vad_silence_duration, 6000);
    EXPECT_EQ(config.asr_config.vad_speech_trigger_duration, 240);

    // llm
    EXPECT_EQ(config.llm_config.model, "qwen3-8b");
    EXPECT_NEAR(config.llm_config.temperature, 0.3f, 1e-6);
    EXPECT_NEAR(config.llm_config.max_tokens, 32000, 1);
    EXPECT_EQ(config.llm_config.timeout_seconds, 60);
}