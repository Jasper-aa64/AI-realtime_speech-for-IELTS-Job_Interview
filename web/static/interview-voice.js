(function () {
  // 桌面壳的实时语音回答（面试模式）：念题 → 收听 → 实时显示中间转写 → 最终转写进回答框，可改后提交。
  // 只在 studioNative.capabilities().native_audio 为 true 时启用（IELTSNativeBridge.voice 不为 null）；
  // 普通浏览器拿到的 voice 是 null，这里什么都不做。出错、断线或超时都回落到原来的录音流程。
  const STATUSES = Object.freeze({ speaking: "native_speaking", listening: "native_listening", review: "native_review" });
  const START_TIMEOUT_MS = 15000;   // 连接 + StartSession
  const SPEAK_TIMEOUT_MS = 45000;   // 念一道题（含首包）
  const SILENCE_TIMEOUT_MS = 20000; // 开始收听后一直没识别到说话

  function create({ state, text, setRecordButton, submit, fallback, isActive }) {
    let voice = null;
    let session = "closed";      // closed / starting / ready / error
    let turn = null;             // { sessionId, id, base, final, timer }
    let waiter = null;           // { reasons:Set, resolve, reject, timer }
    const failedTurns = new Set();

    window.IELTSNativeBridge?.voice?.then((object) => {
      voice = object || null;
      if (!voice) return;
      voice.stateChanged.connect(onState);
      voice.partialTranscript.connect(onPartial);
      voice.finalTranscript.connect(onFinal);
      voice.error.connect(onError);
    });

    function enabled() {
      return !!voice && state.productMode === "interview" && state.desktopCapabilities?.native_audio === true;
    }

    function handles(currentTurn) {
      return enabled() && currentTurn?.part === "interview" && !!String(currentTurn.question || "").trim() && !failedTurns.has(currentTurn.id);
    }

    // ---- 面板：回答框、实时转写、提交 / 改用录音 ----
    function panel() {
      let el = document.getElementById("ivVoicePanel");
      if (el) return el;
      el = document.createElement("div");
      el.id = "ivVoicePanel";
      el.className = "iv-voice-panel hidden";
      el.innerHTML = `
        <div class="iv-voice-live" id="ivVoiceLive" aria-live="polite"></div>
        <textarea id="ivVoiceAnswer" class="iv-voice-answer" spellcheck="true" placeholder="实时转写会出现在这里，说完可以修改后提交"></textarea>
        <div class="iv-voice-actions">
          <button id="ivVoiceSubmit" class="primary" type="button" disabled>提交回答</button>
          <button id="ivVoiceFallback" class="ghost" type="button">改用录音</button>
        </div>`;
      const anchor = document.querySelector("#recorderPane .record-row");
      (anchor?.parentNode || document.getElementById("recorderPane") || document.body).insertBefore(el, anchor?.nextSibling || null);
      el.querySelector("#ivVoiceSubmit").addEventListener("click", () => submitAnswer());
      el.querySelector("#ivVoiceFallback").addEventListener("click", () => toRecording("用户改用录音"));
      el.querySelector("#ivVoiceAnswer").addEventListener("input", syncSubmit);
      return el;
    }

    function showPanel(show) {
      const el = panel();
      el.classList.toggle("hidden", !show);
      if (show) {
        el.querySelector("#ivVoiceLive").textContent = "";
        el.querySelector("#ivVoiceAnswer").value = "";
        syncSubmit();
      }
    }

    function answerBox() { return panel().querySelector("#ivVoiceAnswer"); }
    function syncSubmit() {
      const button = panel().querySelector("#ivVoiceSubmit");
      button.disabled = !answerBox().value.trim() || state.status === STATUSES.speaking;
    }

    // ---- 和桥的往返：等某个状态原因（speak_finished / user_stopped / ready），带超时 ----
    function waitFor(reasons, ms) {
      clearWaiter();
      return new Promise((resolve, reject) => {
        waiter = { reasons: new Set(reasons), resolve, reject, timer: window.setTimeout(() => {
          waiter = null;
          reject(Object.assign(new Error(`等待${reasons.join("/")}超时`), { code: "timeout" }));
        }, ms) };
      });
    }
    function clearWaiter() {
      if (waiter) window.clearTimeout(waiter.timer);
      waiter = null;
    }

    function onState(stateName, reason) {
      if (stateName === "ready" && session === "starting") session = "ready";
      if (stateName === "error" || stateName === "closed") session = stateName === "error" ? "error" : "closed";
      const key = reason || stateName;
      if (waiter && (waiter.reasons.has(key) || waiter.reasons.has(stateName))) {
        const { resolve, timer } = waiter;
        window.clearTimeout(timer);
        waiter = null;
        resolve(key);
      }
      if (!turn) return;
      if (reason === "user_started") window.clearTimeout(turn.timer);
      if (reason === "user_stopped" && state.status === STATUSES.listening) toReview();
    }

    function onPartial(value) {
      if (!turn || state.status !== STATUSES.listening) return;
      panel().querySelector("#ivVoiceLive").textContent = value;
    }

    function onFinal(value) {
      if (!turn) return;
      turn.final = value;
      const box = answerBox();
      box.value = [turn.base, value].filter(Boolean).join(turn.base ? "\n" : "");
      panel().querySelector("#ivVoiceLive").textContent = "";
      syncSubmit();
      // 计时 ②：最终转写真正画到页面上之后再回报
      const id = turn.id;
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
        try { voice?.markTranscriptShown(String(id)); } catch (_error) { /* timing only */ }
      }));
    }

    function onError(code, message) {
      const fatal = ["disconnected", "session_failed", "session_finished", "connect_failed", "audio_device", "config", "unavailable", "untrusted_origin"].includes(code);
      if (fatal) session = "error";
      if (waiter) {
        const { reject, timer } = waiter;
        window.clearTimeout(timer);
        waiter = null;
        reject(Object.assign(new Error(message || code), { code }));
        return;
      }
      if (turn && (fatal || state.status === STATUSES.listening)) toRecording(`实时语音出错（${code}）：${message || ""}`);
    }

    async function ensureSession() {
      if (session === "ready") return;
      session = "starting";
      const started = waitFor(["ready"], START_TIMEOUT_MS);
      if (voice.startSession() === false) {
        // startSession 同步失败时已经发了 error 信号，waiter 会被拒绝；这里兜底
        clearWaiter();
        throw Object.assign(new Error("实时语音不可用"), { code: "unavailable" });
      }
      await started;
      session = "ready";
    }

    // ---- 一道题 ----
    async function runTurn(sessionId, currentTurn) {
      turn = { sessionId, id: currentTurn.id, base: "", final: "", timer: 0 };
      showPanel(true);
      setRecordButton(STATUSES.speaking, "念题中", "面试官正在读题，读完自动开始收听。");
      text("recordStatus", "实时语音：正在连接并读题…");
      try {
        await ensureSession();
        if (!stillCurrent(sessionId, currentTurn.id)) return;
        const finished = waitFor(["speak_finished"], SPEAK_TIMEOUT_MS);
        voice.speak(String(currentTurn.question));
        await finished;
        if (!stillCurrent(sessionId, currentTurn.id)) return;
        listen();
      } catch (error) {
        if (stillCurrent(sessionId, currentTurn.id)) toRecording(`实时语音不可用（${error.code || "error"}）：${error.message}`);
      }
    }

    function listen() {
      if (!turn) return;
      turn.base = answerBox().value.trim();
      panel().querySelector("#ivVoiceLive").textContent = "";
      setRecordButton(STATUSES.listening, "说完了", "正在听你回答；停顿过长会自动结束，也可以点这里结束。");
      text("recordStatus", "实时语音：正在听…");
      syncSubmit();
      window.clearTimeout(turn.timer);
      turn.timer = window.setTimeout(() => {
        if (turn && state.status === STATUSES.listening) {
          voice.stopListening();
          toReview("没有听到声音。可以点“继续说”再试，或改用录音。");
        }
      }, SILENCE_TIMEOUT_MS);
      voice.startListening();
    }

    function toReview(message = "") {
      if (!turn) return;
      window.clearTimeout(turn.timer);
      setRecordButton(STATUSES.review, "继续说", "接着补充回答；确认无误后点“提交回答”。");
      text("recordStatus", message || "识别完成，可以修改后提交，或点“继续说”补充。");
      syncSubmit();
    }

    function stillCurrent(sessionId, turnId) {
      return !!turn && turn.id === turnId && isActive(sessionId) && state.currentTurn?.id === turnId;
    }

    function submitAnswer() {
      if (!turn) return;
      const answer = answerBox().value.trim();
      if (!answer) return;
      if (state.status === STATUSES.listening) voice.stopListening();
      window.clearTimeout(turn.timer);
      turn = null;
      clearWaiter();
      showPanel(false);
      submit(answer);
    }

    function toRecording(reason) {
      const current = turn;
      clearWaiter();
      if (current) {
        window.clearTimeout(current.timer);
        failedTurns.add(current.id);
      }
      try { if (state.status === STATUSES.listening) voice?.stopListening(); } catch (_error) { /* already gone */ }
      turn = null;
      showPanel(false);
      setRecordButton("idle", "Start", "No typing. Record your answer aloud.");
      text("recordStatus", `${reason}。已改用录音回答。`);
      if (current) fallback(current.sessionId, reason);
    }

    // 录音大按钮在实时语音期间的含义：收听中 = 说完了；识别完 = 继续说。返回 true 表示已处理。
    function onRecordControl() {
      if (!turn) return false;
      if (state.status === STATUSES.listening) {
        voice.stopListening();
        toReview("正在等最后几个字的识别结果…");
        return true;
      }
      if (state.status === STATUSES.review) {
        listen();
        return true;
      }
      return state.status === STATUSES.speaking;
    }

    // 退出练习、开始评分时释放麦克风
    function endSession() {
      clearWaiter();
      if (turn) window.clearTimeout(turn.timer);
      turn = null;
      if (document.getElementById("ivVoicePanel")) showPanel(false);
      if (voice && session !== "closed") {
        try { voice.endSession(); } catch (_error) { /* shell already gone */ }
      }
      session = "closed";
    }

    return { enabled, handles, runTurn, onRecordControl, endSession, statuses: STATUSES };
  }

  window.IELTSInterviewVoice = Object.freeze({ create, STATUSES });
})();
