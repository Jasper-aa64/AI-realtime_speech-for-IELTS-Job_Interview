(function () {
  function createExaminerAudioDiagnostics({ state, $, audioSnapshot, traceExaminerAudio, diagnosticsEnabled }) {
    const signalNodes = new WeakMap();

    function expose() {
      window.__ieltsExaminerAudio = {
        events: () => [...state.examinerAudioDiagnostics],
        clear: () => {
          state.examinerAudioDiagnostics = [];
        },
        enable: () => {
          localStorage.setItem("ielts-examiner-audio-debug", "1");
        },
        disable: () => {
          localStorage.removeItem("ielts-examiner-audio-debug");
        },
        preloads: () => [...state.examinerAudioBlobUrls.entries()].map(([url, item]) => ({
          url,
          playbackUrl: item.playbackUrl,
          size: item.size,
          type: item.type,
        })),
        timeline: () => [...state.examinerPlaybackTimelineReports],
        samples: () => [...state.examinerPlaybackSamples],
        signal: () => [...state.examinerSignalReports],
        signalSamples: () => [...state.examinerSignalSamples],
        active: () => ({
          element: audioSnapshot(state.activeExaminerAudio || $("examinerAudio")),
        }),
      };
    }

    function startPlaybackSampler(audio, url) {
      stopPlaybackSampler("restart");
      state.examinerPlaybackSamples = [];
      const startedAt = performance.now();
      const pushSample = () => {
        if (!audio) return;
        state.examinerPlaybackSamples.push({
          wallMs: Number((performance.now() - startedAt).toFixed(1)),
          currentMs: Number(((Number.isFinite(audio.currentTime) ? audio.currentTime : 0) * 1000).toFixed(1)),
          paused: !!audio.paused,
          ended: !!audio.ended,
          readyState: audio.readyState,
          networkState: audio.networkState,
        });
        if (state.examinerPlaybackSamples.length > 600) state.examinerPlaybackSamples.shift();
      };
      pushSample();
      state.examinerPlaybackSampleTimer = window.setInterval(pushSample, 50);
      traceExaminerAudio("timeline:start", { url });
    }

    function stopPlaybackSampler(reason = "stopped") {
      if (state.examinerPlaybackSampleTimer) {
        window.clearInterval(state.examinerPlaybackSampleTimer);
        state.examinerPlaybackSampleTimer = null;
      }
      const samples = state.examinerPlaybackSamples || [];
      if (samples.length < 2) return null;
      const report = summarizePlaybackTimeline(samples, reason);
      state.examinerPlaybackTimelineReports.push(report);
      if (state.examinerPlaybackTimelineReports.length > 20) state.examinerPlaybackTimelineReports.shift();
      traceExaminerAudio("timeline:summary", report);
      return report;
    }

    function ensureSignalProbe(audio) {
      if (!audio || !diagnosticsEnabled()) return null;
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return null;
      try {
        if (!state.examinerSignalContext) {
          state.examinerSignalContext = new AudioContextClass();
        }
        let nodes = signalNodes.get(audio);
        if (!nodes) {
          const source = state.examinerSignalContext.createMediaElementSource(audio);
          const analyser = state.examinerSignalContext.createAnalyser();
          analyser.fftSize = 1024;
          source.connect(analyser);
          analyser.connect(state.examinerSignalContext.destination);
          nodes = {
            analyser,
            buffer: new Float32Array(analyser.fftSize),
          };
          signalNodes.set(audio, nodes);
        }
        if (state.examinerSignalContext.state === "suspended") {
          state.examinerSignalContext.resume().catch(() => null);
        }
        return nodes;
      } catch (error) {
        traceExaminerAudio("signal:probe-failed", {
          error: error instanceof Error ? error.message : String(error),
        });
        return null;
      }
    }

    function startSignalSampler(audio, url) {
      stopSignalSampler("restart");
      state.examinerSignalSamples = [];
      const nodes = ensureSignalProbe(audio);
      if (!nodes) return;
      const startedAt = performance.now();
      const pushSample = () => {
        if (!audio || !nodes.analyser) return;
        nodes.analyser.getFloatTimeDomainData(nodes.buffer);
        let sumSquares = 0;
        let peak = 0;
        for (let index = 0; index < nodes.buffer.length; index += 1) {
          const value = nodes.buffer[index] || 0;
          const absolute = Math.abs(value);
          sumSquares += value * value;
          if (absolute > peak) peak = absolute;
        }
        const rms = Math.sqrt(sumSquares / Math.max(1, nodes.buffer.length));
        const rmsDbfs = rms > 0 ? 20 * Math.log10(rms) : -120;
        state.examinerSignalSamples.push({
          wallMs: Number((performance.now() - startedAt).toFixed(1)),
          currentMs: Number(((Number.isFinite(audio.currentTime) ? audio.currentTime : 0) * 1000).toFixed(1)),
          rmsDbfs: Number(Math.max(-120, rmsDbfs).toFixed(1)),
          peak: Number(peak.toFixed(4)),
          paused: !!audio.paused,
          ended: !!audio.ended,
          readyState: audio.readyState,
        });
        if (state.examinerSignalSamples.length > 1200) state.examinerSignalSamples.shift();
      };
      pushSample();
      state.examinerSignalSampleTimer = window.setInterval(pushSample, 20);
      traceExaminerAudio("signal:start", { url });
    }

    function stopSignalSampler(reason = "stopped") {
      if (state.examinerSignalSampleTimer) {
        window.clearInterval(state.examinerSignalSampleTimer);
        state.examinerSignalSampleTimer = null;
      }
      const samples = state.examinerSignalSamples || [];
      if (samples.length < 3) return null;
      const report = summarizeSignal(samples, reason);
      state.examinerSignalReports.push(report);
      if (state.examinerSignalReports.length > 20) state.examinerSignalReports.shift();
      traceExaminerAudio("signal:summary", report);
      return report;
    }

    function summarizeSignal(samples, reason) {
      const lowEnergyRuns = [];
      let run = null;
      const lowDb = -58;
      for (const sample of samples) {
        const active = !sample.paused && !sample.ended;
        const low = active && sample.rmsDbfs <= lowDb && sample.currentMs > 30;
        if (low && !run) {
          run = {
            startWallMs: sample.wallMs,
            startCurrentMs: sample.currentMs,
            endWallMs: sample.wallMs,
            endCurrentMs: sample.currentMs,
            minRmsDbfs: sample.rmsDbfs,
          };
        } else if (low && run) {
          run.endWallMs = sample.wallMs;
          run.endCurrentMs = sample.currentMs;
          run.minRmsDbfs = Math.min(run.minRmsDbfs, sample.rmsDbfs);
        } else if (!low && run) {
          if (run.endWallMs - run.startWallMs >= 80) lowEnergyRuns.push(run);
          run = null;
        }
      }
      if (run && run.endWallMs - run.startWallMs >= 80) lowEnergyRuns.push(run);
      const activeSamples = samples.filter((sample) => !sample.paused && !sample.ended);
      const rmsValues = activeSamples.map((sample) => sample.rmsDbfs);
      return {
        reason,
        sampleCount: samples.length,
        wallDurationMs: samples.at(-1)?.wallMs || 0,
        audioDurationMs: samples.at(-1)?.currentMs || 0,
        minRmsDbfs: rmsValues.length ? Math.min(...rmsValues) : null,
        maxRmsDbfs: rmsValues.length ? Math.max(...rmsValues) : null,
        lowEnergyRuns: lowEnergyRuns.slice(0, 20),
        verdict: lowEnergyRuns.length ? "decoded audio signal has low-energy gaps" : "decoded audio signal is continuous",
      };
    }

    function summarizePlaybackTimeline(samples, reason) {
      const stalls = [];
      const jumps = [];
      for (let index = 1; index < samples.length; index += 1) {
        const prev = samples[index - 1];
        const next = samples[index];
        const wallDelta = next.wallMs - prev.wallMs;
        const audioDelta = next.currentMs - prev.currentMs;
        if (!prev.paused && !next.paused && !next.ended && wallDelta >= 35 && audioDelta < Math.max(8, wallDelta * 0.25)) {
          stalls.push({
            atWallMs: next.wallMs,
            currentMs: next.currentMs,
            wallDelta: Number(wallDelta.toFixed(1)),
            audioDelta: Number(audioDelta.toFixed(1)),
            readyState: next.readyState,
          });
        }
        if (audioDelta < -20 || audioDelta > wallDelta * 2.5 + 80) {
          jumps.push({
            atWallMs: next.wallMs,
            fromMs: prev.currentMs,
            toMs: next.currentMs,
            wallDelta: Number(wallDelta.toFixed(1)),
            audioDelta: Number(audioDelta.toFixed(1)),
          });
        }
      }
      return {
        reason,
        sampleCount: samples.length,
        wallDurationMs: samples.at(-1)?.wallMs || 0,
        audioDurationMs: samples.at(-1)?.currentMs || 0,
        stalls: stalls.slice(0, 20),
        jumps: jumps.slice(0, 20),
        verdict: stalls.length || jumps.length ? "playback timeline has stalls/jumps" : "playback timeline is continuous",
      };
    }

    return {
      expose,
      startPlaybackSampler,
      stopPlaybackSampler,
      startSignalSampler,
      stopSignalSampler,
    };
  }

  window.IELTSExaminerAudioDiagnostics = { createExaminerAudioDiagnostics };
})();
