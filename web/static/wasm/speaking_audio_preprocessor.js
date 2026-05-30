import { createAnalyzer } from "./audio_analyzer.js";

const DEFAULT_ANALYZER_ID = "wasm-audio-core";
const FALLBACK_ANALYZER_ID = "mock-rms";
const DEFAULT_THRESHOLD = 0.02;

function now() {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

function emptyMetrics(options = {}) {
  return {
    enabled: true,
    running: false,
    analyzer: options.analyzerId || DEFAULT_ANALYZER_ID,
    fallbackAnalyzer: "",
    fallbackReason: "",
    frameCount: 0,
    speechFrameCount: 0,
    latestRms: 0,
    latestPeak: 0,
    latestSpeech: false,
    sampleRate: 0,
    frameSize: 0,
    startedAt: 0,
    stoppedAt: 0,
    lastError: "",
  };
}

function roundMetric(value, precision = 6) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  const multiplier = 10 ** precision;
  return Math.round(numeric * multiplier) / multiplier;
}

export function summarizeSpeakingAudioPreprocessingMetrics(metrics = {}) {
  if (!metrics || metrics.enabled !== true) return null;
  const totalFrames = Math.max(0, Number(metrics.frameCount || 0));
  const speechFrames = Math.max(0, Math.min(totalFrames, Number(metrics.speechFrameCount || 0)));
  const silenceFrames = Math.max(0, totalFrames - speechFrames);
  return {
    enabled: true,
    analyzer: String(metrics.analyzer || ""),
    fallback_analyzer: String(metrics.fallbackAnalyzer || ""),
    fallback_reason: String(metrics.fallbackReason || ""),
    total_frames: totalFrames,
    speech_frames: speechFrames,
    silence_frames: silenceFrames,
    speech_ratio: totalFrames ? roundMetric(speechFrames / totalFrames) : 0,
    silence_ratio: totalFrames ? roundMetric(silenceFrames / totalFrames) : 0,
    latest_rms: roundMetric(metrics.latestRms),
    latest_peak: roundMetric(metrics.latestPeak),
    latest_speech: Boolean(metrics.latestSpeech),
    sample_rate: Math.max(0, Number(metrics.sampleRate || 0)),
    frame_size: Math.max(0, Number(metrics.frameSize || 0)),
    started_at_ms: roundMetric(metrics.startedAt, 3),
    stopped_at_ms: roundMetric(metrics.stoppedAt, 3),
    last_error: String(metrics.lastError || ""),
  };
}

export function createSpeakingAudioPreprocessor(options = {}) {
  const analyzerId = options.analyzerId || DEFAULT_ANALYZER_ID;
  const threshold = typeof options.threshold === "number" ? options.threshold : DEFAULT_THRESHOLD;
  const reportEveryFrames = Math.max(1, options.reportEveryFrames || 8);
  const metrics = emptyMetrics({ analyzerId });
  const state = {
    audioContext: null,
    sourceNode: null,
    workletNode: null,
    analyzer: null,
    stopped: false,
  };

  function snapshot() {
    return { ...metrics };
  }

  async function loadAnalyzer() {
    try {
      state.analyzer = await createAnalyzer(analyzerId, { threshold });
      metrics.analyzer = analyzerId;
    } catch (error) {
      metrics.fallbackAnalyzer = FALLBACK_ANALYZER_ID;
      metrics.fallbackReason = error instanceof Error ? error.message : String(error);
      state.analyzer = await createAnalyzer(FALLBACK_ANALYZER_ID, { threshold });
      metrics.analyzer = FALLBACK_ANALYZER_ID;
    }
  }

  function handleFrameMessage(event) {
    const data = event.data || {};
    if (state.stopped || data.type !== "audio-frame" || !state.analyzer) return;
    try {
      const result = state.analyzer.analyze(data.samples);
      metrics.frameCount += 1;
      metrics.sampleRate = Number(data.sampleRate || 0);
      metrics.frameSize = Number(data.frameSize || 0);
      metrics.latestRms = Number(result.rms || 0);
      metrics.latestPeak = Number(result.peak || 0);
      metrics.latestSpeech = Boolean(result.speech);
      if (result.speech) metrics.speechFrameCount += 1;
    } catch (error) {
      metrics.lastError = error instanceof Error ? error.message : String(error);
    }
  }

  async function start(stream) {
    if (metrics.running) return snapshot();
    if (!stream) throw new Error("Audio stream is required.");
    if (!window.AudioWorkletNode) throw new Error("AudioWorkletNode is unavailable.");
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCtor) throw new Error("AudioContext is unavailable.");

    metrics.startedAt = now();
    await loadAnalyzer();
    if (state.stopped) return snapshot();

    const audioContext = new AudioContextCtor();
    state.audioContext = audioContext;
    if (audioContext.state === "suspended") {
      await audioContext.resume().catch(() => null);
    }
    await audioContext.audioWorklet.addModule("/wasm/audio_frame_processor.js");
    if (state.stopped) return snapshot();

    const sourceNode = audioContext.createMediaStreamSource(stream);
    const workletNode = new AudioWorkletNode(audioContext, "audio-frame-processor", {
      numberOfInputs: 1,
      numberOfOutputs: 0,
      channelCount: 1,
      processorOptions: { reportEveryFrames },
    });

    workletNode.port.onmessage = handleFrameMessage;
    workletNode.onprocessorerror = () => {
      metrics.lastError = "AudioWorklet processor failed.";
    };
    sourceNode.connect(workletNode);

    state.sourceNode = sourceNode;
    state.workletNode = workletNode;
    metrics.running = true;
    return snapshot();
  }

  async function stop() {
    state.stopped = true;
    metrics.running = false;
    metrics.stoppedAt = now();
    if (state.sourceNode) {
      try {
        state.sourceNode.disconnect();
      } catch {
        // The recorder owns the stream; ignore disconnect races during exit.
      }
    }
    if (state.workletNode) {
      try {
        state.workletNode.port.close();
        state.workletNode.disconnect();
      } catch {
        // AudioWorklet shutdown can race with MediaRecorder stop.
      }
    }
    if (state.audioContext) {
      await state.audioContext.close().catch(() => null);
    }
    state.sourceNode = null;
    state.workletNode = null;
    state.audioContext = null;
    return snapshot();
  }

  return {
    start,
    stop,
    snapshot,
  };
}
