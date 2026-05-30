(function () {
  "use strict";

  function createRealtimePcmUplinkController(options) {
    const {
      state,
      isActivePracticeSession,
      setDictationStatus,
      setRealtimePcmStatus,
      queryKey = "realtime_pcm",
    } = options || {};

    if (!state || typeof isActivePracticeSession !== "function") {
      throw new Error("Realtime PCM uplink requires shared app state and session guard.");
    }

    let stopWaitPromise = null;
    let stopWaitResolve = null;
    let stopWaitTimer = null;

    function resolveStopWait(payload = {}) {
      if (stopWaitTimer) {
        window.clearTimeout(stopWaitTimer);
        stopWaitTimer = null;
      }
      if (stopWaitResolve) {
        stopWaitResolve(payload);
      }
      stopWaitResolve = null;
      stopWaitPromise = null;
    }

    function waitForAsrStop(timeoutMs = 1400) {
      if (stopWaitPromise) return stopWaitPromise;
      stopWaitPromise = new Promise((resolve) => {
        stopWaitResolve = resolve;
        stopWaitTimer = window.setTimeout(() => {
          recordMetrics({ asrStatus: "stop_timeout", lastError: "Realtime ASR stop timed out" });
          resolveStopWait({ event: "asr_stop_timeout" });
        }, timeoutMs);
      });
      return stopWaitPromise;
    }

    function resolveConfig() {
      const params = new URLSearchParams(window.location.search);
      const raw = params.get(queryKey);
      const normalized = String(raw || "").trim().toLowerCase();
      const fakeAsr = ["fake", "mock", "simulate"].includes(normalized);
      const enabled = raw !== null && (fakeAsr || ["1", "true", "on", "ws", "websocket"].includes(normalized));
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      return {
        enabled,
        fakeAsr,
        mode: fakeAsr ? "fake" : "real",
        url: `${protocol}//${window.location.host}/ws/realtime/pcm/`,
      };
    }

    async function fetchRealtimeAsrStatus() {
      const response = await fetch("/api/speaking/realtime-asr/status", {
        method: "GET",
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
      });
      if (!response.ok) throw new Error(`Realtime ASR status failed: ${response.status}`);
      return response.json();
    }

    function elapsedSince(startedAt) {
      const start = Number(startedAt || 0);
      return start > 0 ? Math.max(0, Date.now() - start) : 0;
    }

    function recordMetrics(patch = {}) {
      state.speaking.realtimePcmMetrics = {
        ...(state.speaking.realtimePcmMetrics || {}),
        ...patch,
        updatedAt: Date.now(),
      };
      setRealtimePcmStatus?.(state.speaking.realtimePcmMetrics);
    }

    function markFirstAsrEvent() {
      const metrics = state.speaking.realtimePcmMetrics || {};
      if (metrics.firstAsrEventAt) return;
      recordMetrics({
        firstAsrEventAt: Date.now(),
        firstAsrEventMs: elapsedSince(metrics.startedAt),
      });
    }

    function markFirstTranscript() {
      const metrics = state.speaking.realtimePcmMetrics || {};
      if (metrics.firstTranscriptAt) return;
      recordMetrics({
        firstTranscriptAt: Date.now(),
        firstTranscriptMs: elapsedSince(metrics.startedAt),
      });
    }

    function transcriptSourceFromPayload(payload = {}) {
      return payload.provider || "volcengine_realtime_asr";
    }

    function applyAsrTranscript(payload = {}) {
      const event = String(payload.event || "");
      const context = payload.turn_context && typeof payload.turn_context === "object" ? payload.turn_context : {};
      if (event === "asr_started") {
        markFirstAsrEvent();
        recordMetrics({ asrStatus: "started", asrProvider: payload.provider || "", turnContext: context });
        setDictationStatus?.("listening", "服务端实时转写已连接，继续直接回答。");
        return;
      }
      if (event === "asr_interim") {
        const interim = String(payload.interim || "");
        const finalText = state.transcriptFinal || String(payload.text || "");
        state.transcriptFinal = finalText;
        state.transcriptInterim = interim;
        state.transcript = [finalText, interim].filter(Boolean).join(" ").trim();
        state.transcriptStatus = state.transcript ? "interim_fallback" : "missing";
        if (state.transcript) state.transcriptSource = transcriptSourceFromPayload(payload);
        if (state.transcript) markFirstTranscript();
        recordMetrics({ asrStatus: "interim", asrInterim: interim, transcriptSource: state.transcriptSource, turnContext: context });
        if (state.transcript) setDictationStatus?.("listening", "服务端实时转写正在更新。");
        return;
      }
      if (event === "asr_final") {
        const finalText = String(payload.text || payload.segment || "").trim();
        if (finalText) {
          markFirstTranscript();
          state.transcriptFinal = finalText;
          state.transcriptInterim = "";
          state.transcript = finalText;
          state.transcriptStatus = "captured";
          state.transcriptSource = transcriptSourceFromPayload(payload);
          recordMetrics({
            asrStatus: "final",
            asrTranscript: finalText,
            finalTranscriptAt: Date.now(),
            finalTranscriptMs: elapsedSince(state.speaking.realtimePcmMetrics?.startedAt),
            transcriptSource: state.transcriptSource,
            turnContext: context,
          });
          setDictationStatus?.("captured", "服务端实时转写已捕捉到文字。");
        }
        return;
      }
      if (event === "asr_done") {
        const transcript = String(payload.transcript || "").trim();
        if (transcript) {
          markFirstTranscript();
          state.transcriptFinal = transcript;
          state.transcriptInterim = "";
          state.transcript = transcript;
          state.transcriptStatus = "captured";
          state.transcriptSource = transcriptSourceFromPayload(payload);
          setDictationStatus?.("captured", "服务端实时转写已完成。");
        }
        recordMetrics({
          asrStatus: payload.ok ? "done" : "done_empty",
          asrTranscript: transcript,
          doneAt: Date.now(),
          doneMs: elapsedSince(state.speaking.realtimePcmMetrics?.startedAt),
          transcriptSource: state.transcriptSource,
          turnContext: context,
        });
        resolveStopWait(payload);
        return;
      }
      if (event === "asr_error") {
        recordMetrics({ asrStatus: "error", lastError: String(payload.error || "ASR failed"), turnContext: context });
        setDictationStatus?.("reconnecting", "服务端实时转写暂不可用，继续使用浏览器转写和批处理兜底。");
        resolveStopWait(payload);
      }
    }

    function stop(reason = "stopped") {
      const socket = state.speaking.realtimePcmSocket;
      state.speaking.realtimePcmSocket = null;
      if (!socket) return Promise.resolve(null);
      const waitForStop = waitForAsrStop();
      recordMetrics({ running: false, status: "stopping_asr", stopReason: reason });
      try {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ event: "stop_asr", reason }));
        }
      } catch {
        // Ignore close races; realtime PCM is diagnostic and must not block recording.
        resolveStopWait({ event: "asr_stop_send_failed" });
      }
      if (socket.readyState !== WebSocket.OPEN) resolveStopWait({ event: "socket_not_open" });
      return waitForStop.finally(() => {
        try {
          if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
            socket.close(1000, reason);
          }
        } catch {
          // Ignore already-closed sockets.
        }
      });
    }

    function start(sessionId = state.practiceSessionId) {
      const config = resolveConfig();
      if (!config.enabled || !window.WebSocket) return null;
      stop("restart");
      let socket = null;
      let disabled = false;
      recordMetrics({
        enabled: true,
        running: false,
        status: "checking_asr",
        url: config.url,
        startedAt: Date.now(),
        asrStatusCheckStartedAt: Date.now(),
        framesSent: 0,
        bytesSent: 0,
        framesAcked: 0,
        bytesAcked: 0,
        droppedFrames: 0,
        lastError: "",
      });
      const openSocket = () => {
        if (!isActivePracticeSession(sessionId)) return;
        socket = new WebSocket(config.url);
        socket.binaryType = "arraybuffer";
        state.speaking.realtimePcmSocket = socket;
        recordMetrics({ running: true, status: "connecting" });
        socket.onopen = () => {
          if (!isActivePracticeSession(sessionId)) {
            stop("inactive-session");
            return;
          }
          recordMetrics({
            status: "open",
            socketOpenedAt: Date.now(),
            socketOpenMs: elapsedSince(state.speaking.realtimePcmMetrics?.startedAt),
          });
          socket.send(JSON.stringify({ event: "start", sample_rate: 16000, channels: 1 }));
          socket.send(JSON.stringify({
            event: "start_asr",
            attempt_id: state.attempt?.id || "",
            turn_id: state.currentTurn?.id || "",
            stream_follow_up: shouldStreamFollowUp(state.currentTurn),
            fake_asr: Boolean(config.fakeAsr),
          }));
        };
        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data || "{}");
            if (payload.event === "pcm_ack" || payload.event === "stopped" || payload.event === "status") {
              recordMetrics({
                status: payload.event,
                framesAcked: Number(payload.frames || 0),
                bytesAcked: Number(payload.bytes || 0),
              });
            } else if (String(payload.event || "").startsWith("asr_")) {
              applyAsrTranscript(payload);
            }
          } catch {
            // Malformed server messages should not affect baseline recording.
          }
        };
        socket.onerror = () => {
          recordMetrics({ status: "error", lastError: "WebSocket error" });
        };
        socket.onclose = () => {
          recordMetrics({ running: false, status: "closed" });
          if (state.speaking.realtimePcmSocket === socket) state.speaking.realtimePcmSocket = null;
          resolveStopWait({ event: "closed" });
        };
      };
      const sendPcmFrame = ({ pcm }) => {
        if (!isActivePracticeSession(sessionId) || !pcm || disabled) return;
        if (!socket || socket.readyState !== WebSocket.OPEN) {
          recordMetrics({
            droppedFrames: Number(state.speaking.realtimePcmMetrics?.droppedFrames || 0) + 1,
          });
          return;
        }
        const bytes = pcm.byteLength || 0;
        socket.send(pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength));
        recordMetrics({
          framesSent: Number(state.speaking.realtimePcmMetrics?.framesSent || 0) + 1,
          bytesSent: Number(state.speaking.realtimePcmMetrics?.bytesSent || 0) + bytes,
        });
      };
      if (config.fakeAsr) {
        recordMetrics({
          asrConfigured: true,
          asrEnabled: true,
          asrProvider: "fake_realtime_asr",
          asrStatusCheckedAt: Date.now(),
          asrStatusCheckMs: elapsedSince(state.speaking.realtimePcmMetrics?.asrStatusCheckStartedAt),
          status: "fake_asr_ready",
        });
        setDictationStatus?.("listening", "服务端实时转写模拟模式已开启。");
        openSocket();
        return sendPcmFrame;
      }
      fetchRealtimeAsrStatus()
        .then((status) => {
          if (!isActivePracticeSession(sessionId)) return;
          recordMetrics({
            asrConfigured: Boolean(status?.configured),
            asrEnabled: Boolean(status?.enabled),
            asrProvider: status?.provider || "",
            asrStatusCheckedAt: Date.now(),
            asrStatusCheckMs: elapsedSince(state.speaking.realtimePcmMetrics?.asrStatusCheckStartedAt),
          });
          if (!status?.configured) {
            disabled = true;
            recordMetrics({ running: false, status: "asr_not_configured", lastError: "Realtime ASR is not configured" });
            setDictationStatus?.("unavailable", "服务端实时转写未配置，继续使用浏览器转写和批处理兜底。");
            return;
          }
          openSocket();
        })
        .catch((error) => {
          disabled = true;
          recordMetrics({ running: false, status: "asr_status_error", lastError: String(error?.message || error || "status failed") });
          setDictationStatus?.("reconnecting", "服务端实时转写状态检查失败，继续使用浏览器转写和批处理兜底。");
        });
      return sendPcmFrame;
    }

    function metrics() {
      return { ...(state.speaking.realtimePcmMetrics || {}) };
    }

    function shouldStreamFollowUp(turn) {
      const prompt = turn?.prompt || {};
      return prompt.backend === "stream_pending" || prompt.generation_status === "pending";
    }

    return {
      metrics,
      start,
      stop,
    };
  }

  window.IELTSRealtimePcmUplink = {
    createRealtimePcmUplinkController,
  };
}());
