(function () {
  // 桌面壳的实时语音回答（面试模式）：念题 → 收听 → 实时显示转写 → 说完自动提交最终转写（走原来的文字回答路径）。
  // 追问压力就是实时语音模式：只在选了追问压力、且 studioNative.capabilities().native_audio 为 true 时启用
  // （IELTSNativeBridge.voice 不为 null）；标准模式照旧录音。
  // 普通浏览器拿到的 voice 是 null，这里什么都不做。出错、断线或超时都回落到原来的录音流程。
  // review = 说完了、正在提交；retry = 没听到回答，等用户点“再说一次”
  const STATUSES = Object.freeze({ speaking: "native_speaking", listening: "native_listening", review: "native_review", retry: "native_retry" });
  const START_TIMEOUT_MS = 15000;   // 连接 + StartSession
  const SPEAK_TIMEOUT_MS = 45000;   // 念一道题（含首包）
  const SILENCE_TIMEOUT_MS = 20000; // 开始收听后一直没识别到说话
  const SUBMIT_DELAY_MS = 600;      // 最终转写在页面上停留一下再提交
  const FINAL_WAIT_MS = 4000;       // 手动“说完了”之后等最终转写的上限

  function create({ state, text, setRecordButton, submit, fallback, isActive }) {
    let voice = null;
    let session = "closed";      // closed / starting / ready / error
    let turn = null;             // { sessionId, id, final, live, timer, submitTimer }
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
      return !!voice && state.productMode === "interview" && state.p1Intensity === "high" && state.desktopCapabilities?.native_audio === true;
    }

    function handles(currentTurn) {
      return enabled() && currentTurn?.part === "interview" && !!String(currentTurn.question || "").trim() && !failedTurns.has(currentTurn.id);
    }

    // ---- 面板：只显示转写（已定稿的文字 + 正在识别的一句），放在状态文字下面（状态区里），不影响大圆的位置 ----
    function panel() {
      let el = document.getElementById("ivVoicePanel");
      if (el) return el;
      el = document.createElement("div");
      el.id = "ivVoicePanel";
      el.className = "iv-voice-panel hidden";
      el.setAttribute("aria-live", "polite");
      el.innerHTML = `<p class="iv-voice-transcript"><span id="ivVoiceAnswer" class="iv-voice-final"></span><span id="ivVoiceLive" class="iv-voice-live"></span></p>`;
      (document.querySelector("#recorderPane .recorder-status-zone") || document.getElementById("recorderPane") || document.body).appendChild(el);
      return el;
    }

    function showPanel(show) {
      const el = panel();
      el.classList.toggle("hidden", !show);
      if (show) paintTranscript();
    }

    function paintTranscript() {
      const el = panel();
      // Follow the newest words while the box is scrolled to the bottom; a reader who scrolled up keeps their place.
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
      el.querySelector("#ivVoiceAnswer").textContent = turn?.final || "";
      el.querySelector("#ivVoiceLive").textContent = turn?.live || "";
      el.classList.toggle("is-empty", !turn?.final && !turn?.live);
      if (atBottom || !turn?.final) el.scrollTop = el.scrollHeight;
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
      turn.live = value;
      paintTranscript();
    }

    function onFinal(value) {
      if (!turn) return;
      turn.final = value;
      turn.live = "";
      paintTranscript();
      // 计时 ②：最终转写真正画到页面上之后再回报
      const id = turn.id;
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
        try { voice?.markTranscriptShown(String(id)); } catch (_error) { /* timing only */ }
      }));
      if (state.status === STATUSES.review || state.status === STATUSES.retry) scheduleSubmit();
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
      turn = { sessionId, id: currentTurn.id, final: "", live: "", timer: 0, submitTimer: 0 };
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
      turn.final = "";
      turn.live = "";
      paintTranscript();
      setRecordButton(STATUSES.listening, "说完了", "正在听你回答；停顿过长会自动结束，也可以点这里结束。");
      text("recordStatus", "实时语音：正在听…");
      window.clearTimeout(turn.timer);
      turn.timer = window.setTimeout(() => {
        if (turn && state.status === STATUSES.listening) {
          voice.stopListening();
          toReview();
        }
      }, SILENCE_TIMEOUT_MS);
      voice.startListening();
    }

    // 说完（自动判定或点“说完了”）：有最终转写就自动提交；还没到就等一会儿，等不到就用已识别的文字；什么都没有就让用户再说一次。
    function toReview() {
      if (!turn) return;
      window.clearTimeout(turn.timer);
      setRecordButton(STATUSES.review, "提交中", "识别完成后自动提交。");
      if (turn.final) { scheduleSubmit(); return; }
      text("recordStatus", "正在等最后几个字的识别结果…");
      turn.timer = window.setTimeout(() => {
        if (!turn || state.status !== STATUSES.review) return;
        if (turn.live) { turn.final = turn.live; turn.live = ""; paintTranscript(); scheduleSubmit(); return; }
        setRecordButton(STATUSES.retry, "再说一次", "没有听到回答，点这里重新开始收听。");
        text("recordStatus", "没有听到声音，点大圆再说一次。");
      }, FINAL_WAIT_MS);
    }

    function scheduleSubmit() {
      if (!turn || turn.submitTimer) return;
      window.clearTimeout(turn.timer);
      text("recordStatus", "识别完成，正在提交…");
      turn.submitTimer = window.setTimeout(() => {
        if (turn) turn.submitTimer = 0;
        submitAnswer();
      }, SUBMIT_DELAY_MS);
    }

    function stillCurrent(sessionId, turnId) {
      return !!turn && turn.id === turnId && isActive(sessionId) && state.currentTurn?.id === turnId;
    }

    function submitAnswer() {
      if (!turn) return;
      const answer = String(turn.final || "").trim();
      if (!answer) return;
      if (state.status === STATUSES.listening) voice.stopListening();
      window.clearTimeout(turn.timer);
      window.clearTimeout(turn.submitTimer);
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
        window.clearTimeout(current.submitTimer);
        failedTurns.add(current.id);
      }
      try { if (state.status === STATUSES.listening) voice?.stopListening(); } catch (_error) { /* already gone */ }
      turn = null;
      showPanel(false);
      setRecordButton("idle", "Start", "No typing. Record your answer aloud.");
      text("recordStatus", `${reason}。已改用录音回答。`);
      if (current) fallback(current.sessionId, reason);
    }

    // 录音大按钮在实时语音期间的含义：收听中 = 说完了；没听到回答时 = 再说一次；提交中不响应。返回 true 表示已处理。
    function onRecordControl() {
      if (!turn) return false;
      if (state.status === STATUSES.listening) {
        voice.stopListening();
        toReview();
        return true;
      }
      if (state.status === STATUSES.retry) {
        listen();
        return true;
      }
      if (state.status === STATUSES.review) return true;
      return state.status === STATUSES.speaking;
    }

    // 退出练习、开始评分时释放麦克风
    function endSession() {
      clearWaiter();
      if (turn) { window.clearTimeout(turn.timer); window.clearTimeout(turn.submitTimer); }
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
