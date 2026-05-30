(function () {
  "use strict";

  function createSpeakingAudioPreprocessorRuntime(options) {
    const {
      state,
      isActivePracticeSession,
      startRealtimePcmUplink,
      stopRealtimePcmUplink,
      storageKey = "ielts-wasm-audio-preprocess",
    } = options || {};

    if (!state || typeof isActivePracticeSession !== "function") {
      throw new Error("Speaking audio preprocessor runtime requires shared app state and session guard.");
    }

    function resolveConfig() {
      const params = new URLSearchParams(window.location.search);
      const queryValue = params.get("wasm_audio");
      if (queryValue !== null) {
        const normalized = queryValue.trim().toLowerCase();
        if (["0", "false", "off", "disabled"].includes(normalized)) {
          localStorage.setItem(storageKey, "off");
        } else if (["mock", "mock-rms"].includes(normalized)) {
          localStorage.setItem(storageKey, "mock-rms");
        } else {
          localStorage.setItem(storageKey, "wasm-audio-core");
        }
      }
      const stored = localStorage.getItem(storageKey) || "wasm-audio-core";
      if (stored === "wasm-audio-core" || stored === "mock-rms") {
        return {
          enabled: true,
          analyzerId: stored,
          threshold: 0.02,
        };
      }
      return {
        enabled: false,
        analyzerId: "wasm-audio-core",
        threshold: 0.02,
      };
    }

    function recordMetrics(metrics, extra = {}) {
      state.speaking.audioPreprocessorMetrics = {
        ...(metrics || {}),
        ...extra,
        updatedAt: Date.now(),
      };
    }

    function loadModule() {
      if (!state.speaking.audioPreprocessorModulePromise) {
        state.speaking.audioPreprocessorModulePromise = import("/wasm/speaking_audio_preprocessor.js")
          .catch((error) => {
            state.speaking.audioPreprocessorModulePromise = null;
            throw error;
          });
      }
      return state.speaking.audioPreprocessorModulePromise;
    }

    async function summarizeMetrics(metrics) {
      if (!metrics || metrics.enabled !== true) return null;
      try {
        const module = await loadModule();
        return module.summarizeSpeakingAudioPreprocessingMetrics(metrics);
      } catch (error) {
        return {
          enabled: true,
          analyzer: String(metrics.analyzer || ""),
          fallback_analyzer: String(metrics.fallbackAnalyzer || ""),
          fallback_reason: String(metrics.fallbackReason || ""),
          total_frames: Math.max(0, Number(metrics.frameCount || 0)),
          speech_frames: Math.max(0, Number(metrics.speechFrameCount || 0)),
          silence_frames: Math.max(0, Number(metrics.frameCount || 0) - Number(metrics.speechFrameCount || 0)),
          speech_ratio: 0,
          silence_ratio: 0,
          sample_rate: Math.max(0, Number(metrics.sampleRate || 0)),
          frame_size: Math.max(0, Number(metrics.frameSize || 0)),
          last_error: error instanceof Error ? error.message : String(error),
        };
      }
    }

    async function waitForTurnMetrics() {
      if (state.speaking.audioPreprocessorStopPromise) {
        await state.speaking.audioPreprocessorStopPromise.catch(() => null);
      }
      return state.speaking.audioPreprocessorTurnMetrics || null;
    }

    async function maybeStart(stream, sessionId = state.practiceSessionId) {
      const config = resolveConfig();
      if (!config.enabled || !stream) return;
      const token = state.speaking.audioPreprocessorToken + 1;
      state.speaking.audioPreprocessorToken = token;
      state.speaking.audioPreprocessorTurnMetrics = null;
      state.speaking.audioPreprocessorStopPromise = null;
      recordMetrics(null, {
        enabled: true,
        running: false,
        status: "starting",
        analyzer: config.analyzerId,
      });

      try {
        const module = await loadModule();
        if (token !== state.speaking.audioPreprocessorToken || !isActivePracticeSession(sessionId)) return;
        const onPcmFrame = startRealtimePcmUplink?.(sessionId);
        const preprocessor = module.createSpeakingAudioPreprocessor({
          analyzerId: config.analyzerId,
          threshold: config.threshold,
          onPcmFrame,
        });
        state.speaking.audioPreprocessor = preprocessor;
        const metrics = await preprocessor.start(stream);
        if (token !== state.speaking.audioPreprocessorToken || !isActivePracticeSession(sessionId)) {
          await preprocessor.stop();
          return;
        }
        recordMetrics(metrics, { status: "running" });
        console.info("[wasm-audio] preprocessing started", state.speaking.audioPreprocessorMetrics);
      } catch (error) {
        stopRealtimePcmUplink?.("preprocessor-failed");
        recordMetrics(null, {
          enabled: true,
          running: false,
          status: "failed",
          analyzer: config.analyzerId,
          lastError: error instanceof Error ? error.message : String(error),
        });
        console.info("[wasm-audio] preprocessing unavailable; continuing baseline recorder", state.speaking.audioPreprocessorMetrics);
      }
    }

    function stop(reason = "stopped") {
      state.speaking.audioPreprocessorToken += 1;
      const realtimeStopPromise = Promise.resolve(stopRealtimePcmUplink?.(reason)).catch(() => null);
      const preprocessor = state.speaking.audioPreprocessor;
      state.speaking.audioPreprocessor = null;
      if (!preprocessor) {
        if (state.speaking.audioPreprocessorMetrics) {
          recordMetrics(state.speaking.audioPreprocessorMetrics, {
            running: false,
            status: reason,
          });
        }
        state.speaking.audioPreprocessorTurnMetrics = null;
        state.speaking.audioPreprocessorStopPromise = null;
        return realtimeStopPromise.then(() => null);
      }
      const stopPromise = preprocessor.stop()
        .then((metrics) => {
          recordMetrics(metrics, {
            running: false,
            status: reason,
          });
          return summarizeMetrics(state.speaking.audioPreprocessorMetrics);
        })
        .then(async (summary) => {
          await realtimeStopPromise;
          return summary;
        })
        .then((summary) => {
          state.speaking.audioPreprocessorTurnMetrics = summary;
          console.info("[wasm-audio] preprocessing stopped", state.speaking.audioPreprocessorMetrics);
          return summary;
        })
        .catch((error) => {
          recordMetrics(state.speaking.audioPreprocessorMetrics, {
            running: false,
            status: "stop_failed",
            lastError: error instanceof Error ? error.message : String(error),
          });
          return realtimeStopPromise.then(() => summarizeMetrics(state.speaking.audioPreprocessorMetrics));
        });
      state.speaking.audioPreprocessorStopPromise = stopPromise;
      return stopPromise;
    }

    function expose(realtimePcmMetrics) {
      window.__ieltsWasmAudioPreprocess = {
        enabled: () => resolveConfig().enabled,
        metrics: () => ({ ...(state.speaking.audioPreprocessorMetrics || {}) }),
        realtimePcm: () => (typeof realtimePcmMetrics === "function" ? realtimePcmMetrics() : {}),
        disable: () => {
          localStorage.setItem(storageKey, "off");
          stop("disabled");
        },
      };
    }

    return {
      expose,
      maybeStart,
      stop,
      waitForTurnMetrics,
    };
  }

  window.IELTSSpeakingAudioPreprocessorRuntime = {
    createSpeakingAudioPreprocessorRuntime,
  };
}());
