import assert from "node:assert/strict";

import { summarizeSpeakingAudioPreprocessingMetrics } from "../web/static/wasm/speaking_audio_preprocessor.js";

assert.equal(summarizeSpeakingAudioPreprocessingMetrics(null), null);
assert.equal(summarizeSpeakingAudioPreprocessingMetrics({ enabled: false }), null);

const summary = summarizeSpeakingAudioPreprocessingMetrics({
  enabled: true,
  analyzer: "wasm-audio-core",
  fallbackAnalyzer: "mock-rms",
  fallbackReason: "generated wasm missing",
  frameCount: 8,
  speechFrameCount: 3,
  latestRms: 0.123456789,
  latestPeak: 0.987654321,
  latestSpeech: true,
  sampleRate: 48000,
  frameSize: 128,
  startedAt: 10.123456,
  stoppedAt: 20.987654,
  lastError: "",
  samples: [1, 2, 3],
});

assert.deepEqual(summary, {
  enabled: true,
  analyzer: "wasm-audio-core",
  fallback_analyzer: "mock-rms",
  fallback_reason: "generated wasm missing",
  total_frames: 8,
  speech_frames: 3,
  silence_frames: 5,
  speech_ratio: 0.375,
  silence_ratio: 0.625,
  latest_rms: 0.123457,
  latest_peak: 0.987654,
  latest_speech: true,
  sample_rate: 48000,
  frame_size: 128,
  started_at_ms: 10.123,
  stopped_at_ms: 20.988,
  last_error: "",
});
assert.equal(Object.hasOwn(summary, "samples"), false);

const clampedSummary = summarizeSpeakingAudioPreprocessingMetrics({
  enabled: true,
  frameCount: 4,
  speechFrameCount: 99,
});

assert.equal(clampedSummary.total_frames, 4);
assert.equal(clampedSummary.speech_frames, 4);
assert.equal(clampedSummary.silence_frames, 0);
assert.equal(clampedSummary.speech_ratio, 1);
assert.equal(clampedSummary.silence_ratio, 0);

console.log("speaking audio preprocessor metrics tests passed");
