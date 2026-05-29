#include <gtest/gtest.h>

#include "ielts/audio_core.h"

#include <cstdint>
#include <vector>

using ielts::audio::AnalyzeFrame;
using ielts::audio::AnalyzeFrameWithVad;
using ielts::audio::IsSpeechFrame;
using ielts::audio::IsSpeechFrameWithVad;
using ielts::audio::NormalizedPeak;
using ielts::audio::NormalizedRms;
using ielts::audio::ResampleLinear;
using ielts::audio::TrimSilence;
using ielts::audio::VadBackend;
using ielts::audio::VadConfig;

TEST(AudioCoreTest, SilentFrameHasZeroEnergy) {
    const std::vector<int16_t> samples(160, 0);

    EXPECT_DOUBLE_EQ(NormalizedRms(samples), 0.0);
    EXPECT_DOUBLE_EQ(NormalizedPeak(samples), 0.0);
    EXPECT_FALSE(IsSpeechFrame(samples, 0.01));
}

TEST(AudioCoreTest, SpeechFrameUsesRmsThreshold) {
    const std::vector<int16_t> samples(160, 4096);

    const auto analysis = AnalyzeFrame(samples, 0.05);

    EXPECT_NEAR(analysis.rms, 0.125, 0.001);
    EXPECT_NEAR(analysis.peak, 0.125, 0.001);
    EXPECT_TRUE(analysis.speech);
}

TEST(AudioCoreTest, TrimSilenceKeepsOnlySpeechRegion) {
    std::vector<int16_t> samples;
    samples.insert(samples.end(), 100, 0);
    samples.insert(samples.end(), 200, 5000);
    samples.insert(samples.end(), 100, 0);

    const auto trimmed = TrimSilence(samples, 1000, 100, 0.05);

    ASSERT_EQ(trimmed.size(), 200u);
    EXPECT_EQ(trimmed.front(), 5000);
    EXPECT_EQ(trimmed.back(), 5000);
}

TEST(AudioCoreTest, TrimSilenceKeepsRequestedPadding) {
    std::vector<int16_t> samples;
    samples.insert(samples.end(), 100, 0);
    samples.insert(samples.end(), 100, 6000);
    samples.insert(samples.end(), 100, 0);

    const auto trimmed = TrimSilence(samples, 1000, 100, 0.05, 50);

    ASSERT_EQ(trimmed.size(), 200u);
    EXPECT_EQ(trimmed.front(), 0);
    EXPECT_EQ(trimmed[50], 6000);
    EXPECT_EQ(trimmed.back(), 0);
}

TEST(AudioCoreTest, TrimSilenceReturnsEmptyWhenNoSpeech) {
    const std::vector<int16_t> samples(300, 100);

    const auto trimmed = TrimSilence(samples, 1000, 100, 0.05);

    EXPECT_TRUE(trimmed.empty());
}

TEST(AudioCoreTest, ResampleLinearUpsamplesDeterministically) {
    const std::vector<int16_t> samples{0, 1000, 2000};

    const auto resampled = ResampleLinear(samples, 3, 6);

    ASSERT_EQ(resampled.size(), 6u);
    EXPECT_EQ(resampled[0], 0);
    EXPECT_EQ(resampled[1], 500);
    EXPECT_EQ(resampled[2], 1000);
    EXPECT_EQ(resampled[3], 1500);
    EXPECT_EQ(resampled[4], 2000);
    EXPECT_EQ(resampled[5], 2000);
}

TEST(AudioCoreTest, ResampleLinearDownsamplesDeterministically) {
    const std::vector<int16_t> samples{0, 1000, 2000, 3000};

    const auto resampled = ResampleLinear(samples, 4, 2);

    ASSERT_EQ(resampled.size(), 2u);
    EXPECT_EQ(resampled[0], 0);
    EXPECT_EQ(resampled[1], 2000);
}

TEST(AudioCoreTest, RejectsInvalidConfiguration) {
    const std::vector<int16_t> samples{0, 1000};

    EXPECT_THROW(TrimSilence(samples, 0, 100, 0.05), std::invalid_argument);
    EXPECT_THROW(TrimSilence(samples, 1000, 0, 0.05), std::invalid_argument);
    EXPECT_THROW(TrimSilence(samples, 1000, 100, 1.5), std::invalid_argument);
    EXPECT_THROW(ResampleLinear(samples, 0, 16000), std::invalid_argument);
    EXPECT_THROW(ResampleLinear(samples, 16000, 0), std::invalid_argument);
}

TEST(AudioCoreTest, VadBackendKeepsRmsFallbackBehavior) {
    const std::vector<int16_t> samples(160, 4096);
    VadConfig config;
    config.backend = VadBackend::RmsThreshold;
    config.speech_threshold = 0.05;

    const auto analysis = AnalyzeFrameWithVad(samples, config);

    EXPECT_TRUE(analysis.speech);
    EXPECT_TRUE(IsSpeechFrameWithVad(samples, config));
    EXPECT_NEAR(analysis.rms, 0.125, 0.001);
}

TEST(AudioCoreTest, WebRtcVadBackendInitializesAndRejectsSilence) {
    const std::vector<int16_t> samples(320, 0);
    VadConfig config;
    config.backend = VadBackend::WebRtc;
    config.sample_rate = 16000;
    config.frame_ms = 20;
    config.aggressiveness = 2;

    const auto analysis = AnalyzeFrameWithVad(samples, config);

    EXPECT_FALSE(analysis.speech);
    EXPECT_DOUBLE_EQ(analysis.rms, 0.0);
    EXPECT_DOUBLE_EQ(analysis.peak, 0.0);
}

TEST(AudioCoreTest, WebRtcVadBackendRejectsInvalidConfiguration) {
    const std::vector<int16_t> samples(320, 0);
    VadConfig config;
    config.backend = VadBackend::WebRtc;

    config.sample_rate = 44100;
    EXPECT_THROW(IsSpeechFrameWithVad(samples, config), std::invalid_argument);

    config.sample_rate = 16000;
    config.frame_ms = 40;
    EXPECT_THROW(IsSpeechFrameWithVad(samples, config), std::invalid_argument);

    config.frame_ms = 20;
    config.aggressiveness = 4;
    EXPECT_THROW(IsSpeechFrameWithVad(samples, config), std::invalid_argument);

    config.aggressiveness = 2;
    const std::vector<int16_t> wrong_size(100, 0);
    EXPECT_THROW(IsSpeechFrameWithVad(wrong_size, config), std::invalid_argument);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
