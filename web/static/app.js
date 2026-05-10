const state = {
  view: "mock",
  status: "idle",
  attempt: null,
  currentTurn: null,
  timer: null,
  timerRemaining: 0,
  timerTotal: 1,
  mediaRecorder: null,
  mediaStream: null,
  audioChunks: [],
  cancelRecording: false,
  autoNextTimeout: null,
  recognition: null,
  transcript: "",
  transcriptFinal: "",
  transcriptInterim: "",
  transcriptStatus: "missing",
  dictationFinalWait: null,
  browserTtsUtterance: null,
  activeHistoryId: null,
  abortingAttemptId: null,
  p3Topics: [],
  p3SelectedTopic: "",
  p3Intensity: "normal",
};

const viewCopy = {
  mock: ["Mock", "P1, P2, and P3 in one voice-first exam flow."],
  p1: ["Part 1", "10 short questions. Report appears after the full section."],
  p2: ["Part 2", "Cue card, one-minute preparation, two-minute long turn."],
  p3: ["Part 3", "Choose a topic, then run a normal or high-intensity discussion."],
  history: ["History", ""],
  settings: ["Settings", "Server-side AI, TTS, and speech configuration."],
};

const $ = (selector) => document.querySelector(selector);
const text = (id, value) => { document.getElementById(id).textContent = value; };

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderMarkdown(value) {
  if (!value) return "";
  const codeSpans = [];
  let html = escapeHtml(value).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  html = html.replace(/`([^`\n]+?)`/g, (_match, code) => {
    const token = `@@CODE_SPAN_${codeSpans.length}@@`;
    codeSpans.push(`<code>${code}</code>`);
    return token;
  });
  html = html
    .replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^\*])\*([^*\n]+?)\*/g, "$1<em>$2</em>");
  codeSpans.forEach((code, index) => {
    html = html.replaceAll(`@@CODE_SPAN_${index}@@`, code);
  });
  return html
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim().replace(/\n/g, "<br>"))
    .filter(Boolean)
    .join("<br><br>");
}

async function api(path, body = null) {
  const options = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const response = await fetch(path, options);
  const raw = await response.text();
  let payload = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch (error) {
      if (!response.ok) throw new Error(`Request failed: ${response.status} ${response.statusText}`);
      throw new Error(`Invalid JSON response from ${path}`);
    }
  }
  if (!response.ok) throw new Error(payload?.error || `Request failed: ${response.status} ${response.statusText}`);
  return payload;
}

function setBusy(message) {
  $("#busyBar").classList.toggle("hidden", !message);
  text("busyText", message || "");
}

async function withBusy(message, action) {
  setBusy(message);
  try {
    return await action();
  } finally {
    setBusy("");
  }
}

function switchView(view) {
  stopAllRuntime("Ready");
  state.view = view;
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  $("#practicePanel").classList.toggle("hidden", !["mock", "p1", "p2", "p3"].includes(view));
  $("#historyPanel").classList.toggle("hidden", view !== "history");
  $("#settingsPanel").classList.toggle("hidden", view !== "settings");
  $("#historyTopRail").classList.toggle("hidden", view !== "history");
  $("#viewTitleBlock").classList.toggle("hidden", view === "history");
  text("viewTitle", viewCopy[view][0]);
  text("viewSubtitle", viewCopy[view][1]);
  if (view === "history") loadHistory();
  if (["mock", "p1", "p2", "p3"].includes(view)) resetPracticeSurface();
}

function resetPracticeSurface() {
  state.status = "idle";
  state.attempt = null;
  state.currentTurn = null;
  state.transcript = "";
  $("#candidateAudio").classList.add("hidden");
  $("#examinerAudio").classList.add("hidden");
  $("#browserTtsFallback").classList.add("hidden");
  $("#cueTop").classList.add("hidden");
  $("#promptPane").classList.remove("hidden");
  $("#p3TopicPanel").classList.toggle("hidden", state.view !== "p3");
  $("#practiceGrid").classList.remove("p2-mode", "practice-enter");
  $("#practiceGrid").classList.toggle("hidden", state.view === "p3");
  $("#summaryPanel").classList.add("hidden");
  $("#summaryPanel").innerHTML = "";
  $("#exitPractice").classList.add("hidden");
  text("progressTrack", state.view === "mock" ? "Mock: P1 → P2 → P3" : `${viewCopy[state.view][0]} ready`);
  text("phaseLabel", "Ready");
  text("timerValue", "00:00");
  $("#phaseMeter").style.width = "0%";
  text("promptKicker", "Prompt");
  setPromptHtml("Start a voice practice session to load a question.", "short");
  text("followUp", "");
  setRecordButton("ready", "Start", "Record the full section. No typing.");
  text("recordStatus", "Microphone will be requested when recording starts.");
}

function setRecordButton(status, title, hint) {
  state.status = status;
  $("#recordControl").className = `record-control ${status}`;
  $("#recordControl").disabled = ["loading", "examiner_playing", "processing", "scoring", "turn_saved"].includes(status);
  text("recordTitle", title);
  text("recordHint", hint);
}

function setPromptHtml(html, size = "medium") {
  $("#promptCard").className = `prompt-card ${size}-prompt`;
  $("#promptCard").innerHTML = html;
}

function promptSize(question) {
  const length = String(question || "").length;
  if (length < 90) return "short";
  if (length < 190) return "medium";
  return "long";
}

async function startPractice() {
  const mode = state.view === "mock" ? "mock" : state.view;
  state.abortingAttemptId = null;
  $("#exitPractice").classList.remove("hidden");
  if (mode === "p3") revealP3PracticeGrid();
  setRecordButton("loading", "Loading...", "Preparing exam section.");
  try {
    const theme = state.p3SelectedTopic || "";
    const attempt = await api("/api/attempts/start", {
      mode,
      candidate: $("#candidateName").value || "jasper",
      ...(mode === "p3" ? { p3_intensity: state.p3Intensity } : {}),
      ...(mode === "p3" && theme ? { theme } : {}),
    });
    state.attempt = attempt;
    state.currentTurn = attempt.turns[0];
    $("#summaryPanel").classList.add("hidden");
    renderTurn(state.currentTurn);
    beginExaminerPhase();
  } catch (error) {
    showError(error);
  }
}

function revealP3PracticeGrid() {
  $("#p3TopicPanel").classList.add("hidden");
  const grid = $("#practiceGrid");
  grid.classList.remove("hidden", "practice-enter");
  void grid.offsetWidth;
  grid.classList.add("practice-enter");
}

function renderTurn(turn) {
  if (!turn) return;
  const partLabel = turn.part.toUpperCase();
  const isP2 = turn.part === "p2";
  const isFollowUp = turn.prompt?.role === "follow_up";
  if (turn.part === "p3") $("#p3TopicPanel").classList.add("hidden");
  const questionNumber = Number(turn.index ?? 0) + 1;
  text("progressTrack", isFollowUp
    ? `${partLabel} · Follow-up after Question ${questionNumber}/${turn.total}`
    : `${partLabel} · Question ${questionNumber}/${turn.total}`);
  text("promptKicker", isP2 ? "Cue card" : (isFollowUp ? "Follow-up" : "Question"));
  text("followUp", isFollowUp ? "Follow-up question" : "");
  $("#practiceGrid").classList.toggle("p2-mode", isP2);
  $("#cueTop").classList.add("hidden");
  $("#promptPane").classList.remove("hidden");
  renderExaminerAudio(turn);
  if (isP2 && turn.cue_card) {
    renderCueCardInPrompt(turn.cue_card);
    return;
  }
  setPromptHtml(`<p>${escapeHtml(turn.question)}</p>`, promptSize(turn.question));
}

function cueCardHtml(cue) {
  const bullets = (cue.bullets || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `
    <h2>${escapeHtml(cue.title)}</h2>
    <p class="cue-label">You should say:</p>
    <ul>${bullets}</ul>
    <p>${escapeHtml(cue.rounding || "")}</p>
  `;
}

function renderCueCardInPrompt(cue) {
  setPromptHtml(cueCardHtml(cue), "cue");
}

function renderCueTop(cue) {
  const bullets = (cue.bullets || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  $("#cueTop").classList.remove("hidden");
  $("#cueTop").innerHTML = `
    <h2>${escapeHtml(cue.title)}</h2>
    <p class="cue-label">You should say:</p>
    <ul>${bullets}</ul>
    <p>${escapeHtml(cue.rounding || "")}</p>
  `;
}

function renderExaminerAudio(turn) {
  const tts = turn.examiner_tts || {};
  $("#examinerAudio").classList.add("hidden");
  $("#browserTtsFallback").classList.add("hidden");
  if (tts.audio_url) {
    $("#examinerAudio").src = tts.audio_url;
    $("#examinerAudio").load();
  }
}

function preloadNextExaminerAudio(turn) {
  const nextIndex = Number(turn?.index ?? -1) + 1;
  const nextTurn = (state.attempt?.turns || [])[nextIndex];
  const nextUrl = nextTurn?.examiner_tts?.audio_url;
  if (!nextUrl) return;
  const preload = new Audio();
  preload.preload = "auto";
  preload.src = nextUrl;
}

function beginExaminerPhase() {
  if (!state.currentTurn) return;
  clearTimer();
  const turn = state.currentTurn;
  const isFollowUp = turn.prompt?.role === "follow_up";
  const questionNumber = Number(turn.index ?? 0) + 1;
  preloadNextExaminerAudio(turn);
  setRecordButton("examiner_playing", "Listening...", "The examiner is asking the question.");
  const progress = isFollowUp
    ? `${turn.part.toUpperCase()} · Follow-up after Question ${questionNumber}/${turn.total}`
    : `${turn.part.toUpperCase()} · Question ${questionNumber}/${turn.total}`;
  text("progressTrack", progress);
  text("phaseLabel", `${progress} · Examiner`);
  text("timerValue", "00:00");
  $("#phaseMeter").style.width = "0%";
  text("recordStatus", turn.examiner_behavior === "auto_play_instruction_only"
    ? "Listen to the examiner instruction, then read the cue card during preparation."
    : isFollowUp
    ? "Listen to the examiner follow-up question. Preparation starts automatically."
    : "Listen to the examiner question. Preparation starts automatically.");

  const audio = $("#examinerAudio");
  const tts = turn.examiner_tts || {};
  if (tts.audio_url) {
    audio.onended = () => beginPreparation();
    audio.onerror = () => beginBrowserExaminerPlayback(turn.examiner_text || turn.question);
    audio.currentTime = 0;
    audio.play().catch(() => beginBrowserExaminerPlayback(turn.examiner_text || turn.question));
    return;
  }
  beginBrowserExaminerPlayback(turn.examiner_text || turn.question);
}

function beginBrowserExaminerPlayback(value) {
  if (!value || !window.speechSynthesis) {
    beginPreparation();
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(value);
  state.browserTtsUtterance = utterance;
  utterance.lang = "en-US";
  utterance.rate = 0.92;
  utterance.onend = () => {
    if (state.browserTtsUtterance === utterance) beginPreparation();
  };
  utterance.onerror = () => {
    if (state.browserTtsUtterance === utterance) beginPreparation();
  };
  window.speechSynthesis.speak(utterance);
}

function beginPreparation() {
  const seconds = state.currentTurn?.timers?.prep_seconds || 3;
  const isP2 = state.currentTurn?.part === "p2";
  setRecordButton("preparing", isP2 ? "Skip" : "Prepare", isP2 ? "Click to start recording now." : "Recording starts automatically.");
  text("phaseLabel", `Preparing · ${state.currentTurn.part.toUpperCase()} ${state.currentTurn.index + 1}/${state.currentTurn.total}`);
  text("recordStatus", isP2 ? `Prepare your answer (${seconds}s). Click to start recording early.` : `Prepare your answer. Recording starts in ${seconds} seconds.`);
  startCountdown(seconds, "Preparing", () => startRecording().catch(showError));
}

function startCountdown(seconds, label, onDone) {
  clearTimer();
  state.timerRemaining = Number(seconds || 0);
  state.timerTotal = Math.max(1, state.timerRemaining);
  updateTimer(label);
  state.timer = setInterval(() => {
    state.timerRemaining -= 1;
    updateTimer(label);
    if (state.timerRemaining <= 0) {
      clearTimer();
      onDone();
    }
  }, 1000);
}

function startRecordingTimer(seconds) {
  clearTimer();
  state.timerRemaining = Number(seconds || 0);
  state.timerTotal = Math.max(1, state.timerRemaining);
  updateTimer("Recording");
  state.timer = setInterval(() => {
    state.timerRemaining -= 1;
    updateTimer("Recording");
    if (state.timerRemaining <= 0) stopRecording();
  }, 1000);
}

function updateTimer(label) {
  const remaining = Math.max(0, state.timerRemaining);
  const minutes = String(Math.floor(remaining / 60)).padStart(2, "0");
  const seconds = String(remaining % 60).padStart(2, "0");
  text("phaseLabel", `${label} · ${minutes}:${seconds}`);
  text("timerValue", `${minutes}:${seconds}`);
  const elapsed = Math.max(0, state.timerTotal - remaining);
  $("#phaseMeter").style.width = `${Math.min(100, (elapsed / state.timerTotal) * 100)}%`;
}

function clearTimer() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
}

function clearAutoNextTimeout() {
  if (state.autoNextTimeout) window.clearTimeout(state.autoNextTimeout);
  state.autoNextTimeout = null;
}

async function startRecording() {
  if (!state.currentTurn) return;
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  state.mediaStream = stream;
  state.audioChunks = [];
  state.transcript = "";
  state.transcriptFinal = "";
  state.transcriptInterim = "";
  state.transcriptStatus = "missing";
  const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : "audio/webm";
  state.mediaRecorder = new MediaRecorder(stream, { mimeType });
  state.mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) state.audioChunks.push(event.data);
  };
  state.mediaRecorder.onstop = () => {
    if (state.cancelRecording) {
      state.cancelRecording = false;
      return;
    }
    finalizeTurn(mimeType).catch(showError);
  };
  state.mediaRecorder.start();
  state.cancelRecording = false;
  startDictation();
  setRecordButton("recording", "Stop", "Recording. Press to finish early.");
  text("recordStatus", "Recording your answer...");
  startRecordingTimer(state.currentTurn.timers.speak_seconds);
}

function stopRecording() {
  if (state.status !== "recording") return;
  clearTimer();
  setRecordButton("processing", "Saving", "Uploading this answer.");
  text("recordStatus", "正在保存本题录音与转写");
  stopDictation();
  if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
    state.mediaRecorder.stop();
  }
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach((track) => track.stop());
    state.mediaStream = null;
  }
}

async function finalizeTurn(mimeType) {
  const attempt = state.attempt;
  const turn = state.currentTurn;
  if (!attempt || !turn) return;
  await waitForFinalDictation();
  if (state.abortingAttemptId === attempt.id || state.attempt?.id !== attempt.id) return;
  const blob = new Blob(state.audioChunks, { type: mimeType });
  setRecordButton("processing", "Saving", "Uploading answer audio...");
  try {
    const upload = await fetch(`/api/attempts/${attempt.id}/turns/${turn.id}/audio`, {
      method: "POST",
      headers: { "Content-Type": mimeType.split(";")[0] },
      body: blob,
    });
    const body = await upload.text();
    const payload = body ? JSON.parse(body) : {};
    if (!upload.ok) throw new Error(payload.error || "Audio upload failed");
    setRecordButton("processing", "Saving", "Saving turn...");
    const completePayload = await api(`/api/attempts/${attempt.id}/turns/${turn.id}/complete`, {
      transcript_raw: state.transcript,
      transcript_status: state.transcriptStatus,
      transcript_source: "browser_dictation",
    });
    if (state.abortingAttemptId === attempt.id || state.attempt?.id !== attempt.id) return;
    state.attempt = completePayload.attempt;
    if (completePayload.next_turn) {
      state.currentTurn = completePayload.next_turn;
      renderTurn(completePayload.next_turn);
      setRecordButton("turn_saved", "Next", "Moving to the next question.");
      text("recordStatus", "Question saved. The next examiner prompt will start automatically.");
      clearAutoNextTimeout();
      state.autoNextTimeout = window.setTimeout(() => beginExaminerPhase(), 650);
    } else {
      state.currentTurn = null;
      await scoreAttempt();
    }
  } catch (error) {
    showError(error);
  }
}

async function scoreAttempt() {
  if (!state.attempt) return;
  const attemptId = state.attempt.id;
  setRecordButton("scoring", "Analyzing", "正在分析整轮回答 / 正在评分 / 正在生成报告");
  text("recordStatus", "正在分析整轮回答 / 正在评分 / 正在生成报告");
  try {
    const scored = await api(`/api/attempts/${attemptId}/score`, {});
    if (state.abortingAttemptId === attemptId || state.attempt?.id !== attemptId) return;
    state.attempt = scored;
    renderSummary(scored);
    await loadHistory(false);
    setRecordButton("summary", "Start Again", "Record another section.");
    text("recordStatus", "Section report is ready.");
    text("phaseLabel", "Scored");
    text("timerValue", "00:00");
    scrollToSummary();
  } catch (error) {
    showError(error);
  }
}

function scrollToSummary() {
  const panel = $("#summaryPanel");
  panel.classList.remove("summary-highlight");
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => panel.classList.add("summary-highlight"), 120);
  window.setTimeout(() => panel.classList.remove("summary-highlight"), 1700);
}

function startDictation() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    state.transcript = "";
    state.transcriptStatus = "missing";
    text("recordStatus", "Recording audio. Browser dictation unavailable; transcript may be incomplete.");
    return;
  }
  state.recognition = new SpeechRecognition();
  state.recognition.continuous = true;
  state.recognition.interimResults = true;
  state.recognition.lang = "en-US";
  state.recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      if (result.isFinal) {
        state.transcriptFinal = `${state.transcriptFinal} ${result[0].transcript}`.trim();
      } else {
        interim += result[0].transcript;
      }
    }
    state.transcriptInterim = interim.trim();
    state.transcript = (state.transcriptFinal || state.transcriptInterim).trim();
    state.transcriptStatus = state.transcriptFinal
      ? "captured"
      : (state.transcriptInterim ? "interim_fallback" : "missing");
    resolveDictationWait();
  };
  state.recognition.onerror = () => text("recordStatus", "Recording audio. Browser dictation had an error.");
  try {
    state.recognition.start();
  } catch (error) {
    state.transcript = "";
  }
}

function stopDictation() {
  if (!state.recognition) return;
  try {
    state.recognition.stop();
  } catch (error) {
    // Browser recognition may already be stopped.
  }
  state.recognition = null;
}

function waitForFinalDictation() {
  if (state.transcriptFinal) {
    state.transcript = state.transcriptFinal.trim();
    state.transcriptStatus = "captured";
    return Promise.resolve();
  }
  if (state.transcriptInterim) {
    state.transcript = state.transcriptInterim.trim();
    state.transcriptStatus = "interim_fallback";
  } else {
    state.transcript = "";
    state.transcriptStatus = "missing";
  }
  return new Promise((resolve) => {
    state.dictationFinalWait = resolve;
    window.setTimeout(() => {
      if (state.transcriptFinal) {
        state.transcript = state.transcriptFinal.trim();
        state.transcriptStatus = "captured";
      }
      resolveDictationWait();
    }, 450);
  });
}

function resolveDictationWait() {
  if (!state.dictationFinalWait) return;
  const resolve = state.dictationFinalWait;
  state.dictationFinalWait = null;
  resolve();
}

function renderSummary(attempt) {
  const score = attempt.ielts_score || {};
  const pron = attempt.pronunciation || {};
  $("#summaryPanel").classList.remove("hidden");
  $("#summaryPanel").innerHTML = `
    <div class="score-row">
      ${scoreCell("Overall", score.overall_band)}
      ${scoreCell("Fluency", score.fluency_coherence)}
      ${scoreCell("Lexical", score.lexical_resource)}
      ${scoreCell("Grammar", score.grammatical_range)}
      ${scoreCell("Pronunciation", score.pronunciation_estimate ?? "Not assessed")}
    </div>
    <p class="feedback">${escapeHtml(attempt.feedback_summary || "No feedback generated.")}</p>
    <div class="summary-actions">
      <button id="viewDetails">View Details</button>
    </div>
    <p class="muted">Pronunciation: ${escapeHtml(pron.message || pron.status || "unknown")}</p>
  `;
  $("#viewDetails").addEventListener("click", () => renderDetail(attempt));
}

function scoreCell(label, value) {
  return `<div class="score-cell"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? "—")}</strong></div>`;
}

async function loadHistory(showBusy = true) {
  const action = async () => {
    const payload = await api("/api/history");
    renderHistoryList(payload.items || []);
  };
  if (showBusy) return withBusy("Loading history...", action).catch(showError);
  return action().catch(showError);
}

function renderHistoryList(items) {
  if (!items.length) {
    $("#historyList").textContent = "No attempts yet.";
    $("#detailPanel").innerHTML = "<h2>Attempt Details</h2><p class=\"muted\">No attempts to display.</p>";
    return;
  }
  $("#historyList").innerHTML = items.map((item) => {
    const part = (item.mode || item.part || "").toLowerCase();
    const tagClass = ["p1", "p2", "p3"].includes(part) ? part : "";
    return `
    <button class="history-item ${state.activeHistoryId === item.id ? "active" : ""}" data-attempt-id="${escapeHtml(item.id)}">
      <div class="history-item-top">
        <span class="history-item-tag ${tagClass}">${escapeHtml(part.toUpperCase())}</span>
        <span class="history-item-band">Band ${escapeHtml(item.overall_band ?? "—")}</span>
      </div>
      <strong class="history-item-title">${escapeHtml(item.title || item.question || "Untitled")}</strong>
      <small class="history-item-time">${escapeHtml(item.display_time || "")}</small>
    </button>
  `;}).join("");
  document.querySelectorAll(".history-item").forEach((button) => {
    button.addEventListener("click", async () => {
      if (state.activeHistoryId === button.dataset.attemptId) return;
      state.activeHistoryId = button.dataset.attemptId;
      document.querySelectorAll(".history-item").forEach((item) => {
        item.classList.toggle("active", item.dataset.attemptId === state.activeHistoryId);
      });
      const detail = await api(`/api/history/${button.dataset.attemptId}`);
      renderDetail(detail, false);
    });
  });
  if (!state.activeHistoryId && items.length) {
    state.activeHistoryId = items[0].id;
    document.querySelector(".history-item")?.classList.add("active");
    api(`/api/history/${items[0].id}`).then((detail) => renderDetail(detail, false)).catch(showError);
  }
}

function renderDetail(attempt, updateView = true) {
  if (updateView) switchView("history");
  state.activeHistoryId = attempt.id;
  const score = attempt.ielts_score || {};
  const criteria = attempt.criteria_feedback || {};
  const turns = attempt.turns || [];
  const isP2 = attempt.mode === "p2" || (turns[0]?.part === "p2");
  const isMock = attempt.mode === "mock" || attempt.part === "mock";
  const partScores = isMock ? partScoresHtml(attempt) : "";

  $("#detailPanel").innerHTML = `
    <div class="detail-section">
      <div class="detail-header">
        <div>
          <h2>${escapeHtml((attempt.mode || attempt.part || "").toUpperCase())} report</h2>
          <p class="muted">${escapeHtml(attempt.title || "")} · ${turns.length} question${turns.length === 1 ? "" : "s"}</p>
        </div>
        <strong class="overall-badge">Band ${escapeHtml(score.overall_band ?? "—")}</strong>
      </div>
      <div class="score-row compact">
        ${scoreCell("FC", score.fluency_coherence)}
        ${scoreCell("LR", score.lexical_resource)}
        ${scoreCell("GRA", score.grammatical_range)}
        ${scoreCell("Pron", score.pronunciation_estimate ?? "Not assessed")}
      </div>
      <p class="feedback">${renderMarkdown(attempt.feedback_summary || "")}</p>
    </div>
    ${partScores}
    ${attempt.cue_card ? `<div class="detail-section">${cueDetail(attempt.cue_card)}</div>` : ""}
    ${isMock ? mockTurnSections(attempt, turns) : turnTableSection(attempt, turns, isP2)}
    <div class="detail-section">
      <h3>📊 参考：雅思各维度评分标准，以及提升建议</h3>
      <div class="criteria-grid">
        ${criterionBlock("Fluency & Coherence", criteria.fluency_coherence)}
        ${criterionBlock("Lexical Resource", criteria.lexical_resource)}
        ${criterionBlock("Grammatical Range & Accuracy", criteria.grammatical_range_accuracy)}
        ${criterionBlock("Pronunciation", criteria.pronunciation)}
      </div>
    </div>
  `;
  document.querySelectorAll("[data-speak-band7]").forEach((button) => {
    button.addEventListener("click", () => speakWithBrowser(button.dataset.speakBand7 || ""));
  });
}

function partScoresHtml(attempt) {
  const partScores = attempt.part_scores || {};
  const parts = ["p1", "p2", "p3"].filter((part) => partScores[part]);
  if (!parts.length) return "";
  return `
    <div class="detail-section">
      <h3>Part scores</h3>
      <div class="part-score-grid">
        ${parts.map((part) => {
          const item = partScores[part] || {};
          return `
            <article class="part-score-card">
              <div class="part-score-head">
                <strong>${escapeHtml(part.toUpperCase())}</strong>
                <span>Band ${escapeHtml(item.band ?? "—")}</span>
              </div>
              <div class="score-row mini">
                ${scoreCell("FC", item.fluency_coherence)}
                ${scoreCell("LR", item.lexical_resource)}
                ${scoreCell("GRA", item.grammatical_range)}
                ${scoreCell("Pron", item.pronunciation_estimate ?? "Not assessed")}
              </div>
            </article>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function turnTableSection(attempt, turns, isP2 = false) {
  return `
    <div class="detail-section">
      <table class="turn-report-table">
        <thead><tr>${isP2 ? "<th>Your recording</th><th>Band 7 spoken version</th><th>AI 辅导</th>" : "<th>题目</th><th>Your recording</th><th>Band 7 spoken version</th><th>AI 辅导</th>"}</tr></thead>
        <tbody>${turns.map((turn) => turnReportRow(attempt.id, turn, attempt, isP2)).join("")}</tbody>
      </table>
    </div>
  `;
}

function mockTurnSections(attempt, turns) {
  return ["p1", "p2", "p3"].map((part) => {
    const partTurns = turns.filter((turn) => turn.part === part);
    if (!partTurns.length) return "";
    return `
      <div class="detail-section">
        <h3>${escapeHtml(part.toUpperCase())} answers</h3>
        <table class="turn-report-table">
          <thead><tr>${part === "p2" ? "<th>Your recording</th><th>Band 7 spoken version</th><th>AI 辅导</th>" : "<th>题目</th><th>Your recording</th><th>Band 7 spoken version</th><th>AI 辅导</th>"}</tr></thead>
          <tbody>${partTurns.map((turn) => turnReportRow(attempt.id, turn, attempt, part === "p2")).join("")}</tbody>
        </table>
      </div>
    `;
  }).join("");
}

function cueDetail(cue) {
  const bullets = (cue.bullets || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `<article class="cue-detail"><h2>${escapeHtml(cue.title)}</h2><p>You should say:</p><ul>${bullets}</ul><p>${escapeHtml(cue.rounding || "")}</p></article>`;
}

function transcriptText(turn) {
  if (turn.transcript_markdown) return renderMarkdown(turn.transcript_markdown);
  if (turn.transcript_cleaned) return renderMarkdown(turn.transcript_cleaned);
  if (turn.transcript_status === "missing" && (turn.audio || {}).url) {
    return "Recording exists, but transcript was not captured.";
  }
  return "Recording exists, but transcript was not captured.";
}

function aiCoachingHtml(turn, attempt) {
  const coaching = turn.ai_coaching || attempt.ai_coaching || "";
  if (coaching) return `<p>${renderMarkdown(coaching)}</p>`;
  const notes = turn.upgrade_notes || attempt.upgrade_notes || [];
  if (!notes.length) return "<p class=\"muted\">No AI coaching generated for this turn.</p>";
  return `<ul>${notes.map((item) => `
    <li><strong>${escapeHtml(item.criterion || "Change")}:</strong> ${renderMarkdown(item.band7_change || item.original_problem || "")}</li>
  `).join("")}</ul>`;
}

function turnReportRow(attemptId, turn, attempt, isP2 = false) {
  const modelAudio = turn.model_audio || {};
  const band7 = turn.band7_version || attempt.band7_version || "";
  const band7Markdown = turn.band7_markdown || attempt.band7_markdown || band7;
  const statusLabel = turn.transcript_status === "interim_fallback"
    ? "Interim transcript used"
    : (turn.transcript_status === "captured" ? "Transcript captured" : "Transcript missing");
  const isFollowUp = turn.prompt?.role === "follow_up";
  const questionCell = isP2 ? "" : `<td><strong>${escapeHtml(turn.part.toUpperCase())} ${turn.index + 1}</strong><p>${escapeHtml(turn.question)}</p></td>`;
  return `
    <tr>
      ${questionCell}
      <td>
        ${isFollowUp ? `<span class="follow-up-pill">Follow-up</span>` : ""}
        ${(turn.audio || {}).url
          ? `<audio controls src="/api/audio/${escapeHtml(attemptId)}/${escapeHtml(turn.id)}/candidate"></audio>`
          : "<p class=\"audio-warning\">Recording missing. This turn has no playable audio.</p>"}
        <p class="transcript-status">${escapeHtml(statusLabel)}</p>
        <p>${transcriptText(turn)}</p>
      </td>
      <td>
        ${modelAudio.audio_url ? `<audio controls src="${escapeHtml(modelAudio.audio_url)}"></audio>` : `<button class="ghost" data-speak-band7="${escapeHtml(band7)}">Play with browser voice</button>`}
        <p>${renderMarkdown(band7Markdown)}</p>
      </td>
      <td>${aiCoachingHtml(turn, attempt)}</td>
    </tr>
  `;
}

function criterionBlock(title, item = {}) {
  const standard = item.standard || (item.strengths || [])[0] || "";
  const focus = item.focus || (item.problems || [])[0] || "";
  const advice = item.advice || item.suggestion || "";
  return `
    <article class="criterion">
      <h4>${escapeHtml(title)} · Band ${escapeHtml(item.band ?? "—")}</h4>
      <strong>评分标准</strong><p>${renderMarkdown(standard)}</p>
      <strong>当前关注</strong><p>${renderMarkdown(focus)}</p>
      <strong>提升建议</strong><p>${renderMarkdown(advice)}</p>
    </article>
  `;
}

function speakWithBrowser(value) {
  if (!value || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(value);
  utterance.lang = "en-US";
  utterance.rate = 0.92;
  window.speechSynthesis.speak(utterance);
}

function stopAllRuntime(label = "Ready") {
  clearTimer();
  clearAutoNextTimeout();
  stopDictation();
  $("#examinerAudio").pause();
  $("#examinerAudio").removeAttribute("src");
  $("#examinerAudio").load();
  $("#examinerAudio").onended = null;
  $("#examinerAudio").onerror = null;
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  state.browserTtsUtterance = null;
  if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
    state.cancelRecording = true;
    state.mediaRecorder.stop();
  }
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach((track) => track.stop());
    state.mediaStream = null;
  }
  text("phaseLabel", label);
  text("timerValue", "00:00");
}

async function exitPractice() {
  const attemptId = state.attempt?.id;
  state.abortingAttemptId = attemptId || null;
  stopAllRuntime("Ready");
  setBusy("");
  if (attemptId) {
    await api(`/api/attempts/${attemptId}/abort`, {}).catch(() => null);
  }
  resetPracticeSurface();
}

function showError(error) {
  const message = error instanceof Error ? error.message : String(error);
  setBusy("");
  setRecordButton("ready", "Try Again", "The last attempt failed. Start again when ready.");
  text("recordStatus", message);
  $("#summaryPanel").classList.remove("hidden");
  $("#summaryPanel").innerHTML = `<p class="error">${escapeHtml(message)}</p>`;
}

function bindEvents() {
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  $("#recordControl").addEventListener("click", () => {
    if (state.status === "recording") {
      stopRecording();
    } else if (state.status === "preparing") {
      clearTimer();
      startRecording().catch(showError);
    } else if (state.status === "idle" || state.status === "ready" || state.status === "summary") {
      if (state.currentTurn && state.status === "ready") {
        beginExaminerPhase();
      } else {
        startPractice();
      }
    }
  });
  $("#exitPractice").addEventListener("click", () => exitPractice());
  $("#p3StartButton").addEventListener("click", () => startPractice());
  document.querySelectorAll("[data-p3-intensity]").forEach((button) => {
    button.addEventListener("click", () => {
      state.p3Intensity = button.dataset.p3Intensity || "normal";
      document.querySelectorAll("[data-p3-intensity]").forEach((option) => {
        option.classList.toggle("active", option === button);
      });
    });
  });
  $("#p3TopicChips").addEventListener("click", (event) => {
    const chip = event.target.closest("[data-p3-topic]");
    if (!chip) return;
    state.p3SelectedTopic = chip.dataset.p3Topic || "";
    document.querySelectorAll("#p3TopicChips .topic-chip").forEach((c) => {
      c.classList.toggle("active", c === chip);
    });
  });
}

function renderP3TopicChips(topics) {
  state.p3Topics = topics.slice(0, 8);
  $("#p3TopicChips").innerHTML = state.p3Topics.map((topic) => (
    `<button type="button" class="topic-chip${state.p3SelectedTopic === topic ? " active" : ""}" data-p3-topic="${escapeHtml(topic)}">${escapeHtml(topic.replaceAll("_", " "))}</button>`
  )).join("");
  if (state.p3Topics.length && !state.p3SelectedTopic) {
    state.p3SelectedTopic = state.p3Topics[0];
    document.querySelector("#p3TopicChips .topic-chip")?.classList.add("active");
  }
}

async function init() {
  bindEvents();
  switchView("mock");
  try {
    const summary = await api("/api/question-bank/summary");
    text("bankStatus", `${summary.part1_count} P1 · ${summary.part2_count} P2`);
    renderP3TopicChips(summary.part2_themes || []);
  } catch (error) {
    text("bankStatus", error.message);
  }
}

init();
