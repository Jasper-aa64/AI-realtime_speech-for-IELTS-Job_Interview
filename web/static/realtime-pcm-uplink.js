(function () {
  "use strict";

  function createRealtimePcmUplinkController(options) {
    const {
      state,
      isActivePracticeSession,
      setDictationStatus,
      queryKey = "realtime_pcm",
    } = options || {};

    if (!state || typeof isActivePracticeSession !== "function") {
      throw new Error("Realtime PCM uplink requires shared app state and session guard.");
    }

    function resolveConfig() {
      const params = new URLSearchParams(window.location.search);
      const raw = params.get(queryKey);
      const enabled = raw !== null && ["1", "true", "on", "ws", "websocket"].includes(raw.trim().toLowerCase());
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      return {
        enabled,
        url: `${protocol}//${window.location.host}/ws/realtime/pcm/`,
      };
    }

    function recordMetrics(patch = {}) {
      state.speaking.realtimePcmMetrics = {
        ...(state.speaking.realtimePcmMetrics || {}),
        ...patch,
        updatedAt: Date.now(),
      };
    }

    function applyAsrTranscript(payload = {}) {
      const event = String(payload.event || "");
      const context = payload.turn_context && typeof payload.turn_context === "object" ? payload.turn_context : {};
      if (event === "asr_started") {
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
        recordMetrics({ asrStatus: "interim", asrInterim: interim, turnContext: context });
        if (state.transcript) setDictationStatus?.("listening", "服务端实时转写正在更新。");
        return;
      }
      if (event === "asr_final") {
        const finalText = String(payload.text || payload.segment || "").trim();
        if (finalText) {
          state.transcriptFinal = finalText;
          state.transcriptInterim = "";
          state.transcript = finalText;
          state.transcriptStatus = "captured";
          recordMetrics({ asrStatus: "final", asrTranscript: finalText, turnContext: context });
          setDictationStatus?.("captured", "服务端实时转写已捕捉到文字。");
        }
        return;
      }
      if (event === "asr_done") {
        const transcript = String(payload.transcript || "").trim();
        if (transcript) {
          state.transcriptFinal = transcript;
          state.transcriptInterim = "";
          state.transcript = transcript;
          state.transcriptStatus = "captured";
          setDictationStatus?.("captured", "服务端实时转写已完成。");
        }
        recordMetrics({ asrStatus: payload.ok ? "done" : "done_empty", asrTranscript: transcript, turnContext: context });
        return;
      }
      if (event === "asr_error") {
        recordMetrics({ asrStatus: "error", lastError: String(payload.error || "ASR failed"), turnContext: context });
        setDictationStatus?.("reconnecting", "服务端实时转写暂不可用，继续使用浏览器转写和批处理兜底。");
      }
    }

    function stop(reason = "stopped") {
      const socket = state.speaking.realtimePcmSocket;
      state.speaking.realtimePcmSocket = null;
      if (!socket) return;
      recordMetrics({ running: false, status: reason });
      try {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ event: "stop", reason }));
        }
      } catch {
        // Ignore close races; realtime PCM is diagnostic and must not block recording.
      }
      try {
        socket.close(1000, reason);
      } catch {
        // Ignore already-closed sockets.
      }
    }

    function start(sessionId = state.practiceSessionId) {
      const config = resolveConfig();
      if (!config.enabled || !window.WebSocket) return null;
      stop("restart");
      const socket = new WebSocket(config.url);
      socket.binaryType = "arraybuffer";
      state.speaking.realtimePcmSocket = socket;
      recordMetrics({
        enabled: true,
        running: true,
        status: "connecting",
        url: config.url,
        framesSent: 0,
        bytesSent: 0,
        framesAcked: 0,
        bytesAcked: 0,
        droppedFrames: 0,
        lastError: "",
      });
      socket.onopen = () => {
        if (!isActivePracticeSession(sessionId)) {
          stop("inactive-session");
          return;
        }
        recordMetrics({ status: "open" });
        socket.send(JSON.stringify({ event: "start", sample_rate: 16000, channels: 1 }));
        socket.send(JSON.stringify({
          event: "start_asr",
          attempt_id: state.attempt?.id || "",
          turn_id: state.currentTurn?.id || "",
          stream_follow_up: shouldStreamFollowUp(state.currentTurn),
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
      };
      return ({ pcm }) => {
        if (!isActivePracticeSession(sessionId) || !pcm) return;
        if (socket.readyState !== WebSocket.OPEN) {
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
