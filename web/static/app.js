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
  dictationRecognition: null,
  dictationShouldRun: false,
  dictationStopping: false,
  dictationRestartTimer: null,
  dictationRestartCount: 0,
  dictationLastError: "",
  transcript: "",
  transcriptFinal: "",
  transcriptInterim: "",
  transcriptStatus: "missing",
  dictationFinalWait: null,
  browserTtsUtterance: null,
  activeHistoryId: null,
  abortingAttemptId: null,
  practiceViewBeforeSettings: null,
  p3Topics: [],
  p3SelectedTopic: "",
  p3Intensity: "normal",
  practiceLocked: false,
  navToastTimer: null,
  fontStyle: "default",
  pendingRecharge: 0,
  examinerAudioPreloads: new Map(),
  writing: {
    taskType: "task1_academic",
    prompts: {},
    prompt: null,
    entry: null,
    dirty: false,
    month: "",
    recentEntries: [],
    activeReportId: null,
  },
  account: {
    authenticated: false,
    backendAvailable: false,
    user: null,
  },
};

const FONT_STORAGE_KEY = "ielts-font-style";
const VIEW_STORAGE_KEY = "ielts-view";
const FULL_NAME_STORAGE_KEY = "ielts-full-name";
const ENGLISH_NAME_STORAGE_KEY = "ielts-english-name";
const fontStyles = new Set(["default", "academic", "popular"]);
const DEFAULT_FULL_NAME = "LiHua";
const DEFAULT_ENGLISH_NAME = "Jasper";

const viewCopy = {
  mock: ["Mock", "Practice flow: P1, P2, then P3 generated from your P2 answer."],
  p1: ["Part 1", "Practice short questions in an IELTS-style interview flow."],
  p2: ["Part 2", "Cue card, one-minute preparation, then a long turn."],
  p3: ["Part 3", "Discussion generated from your P2 answer with normal or high-intensity practice."],
  history: ["口语报告", ""],
  writing: ["每日写作", ""],
  writingReports: ["写作报告", ""],
  settings: ["Settings", "Server-side AI, TTS, and speech configuration."],
};

const $ = (selector) => {
  if (typeof selector !== "string") return null;
  if (selector.startsWith("#") || selector.startsWith(".") || selector.startsWith("[") || selector.includes(" ") || selector.includes(">") || selector.includes(":")) {
    return document.querySelector(selector);
  }
  return document.getElementById(selector) || document.querySelector(selector);
};
const text = (id, value) => { document.getElementById(id).textContent = value; };
const byId = (id) => document.getElementById(id);
const EXAMINER_AUDIO_PRELOAD_LIMIT = 4;
const AUDIO_READY_TIMEOUT_MS = 2000;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeCssValue(value) {
  if (window.CSS?.escape) return window.CSS.escape(String(value ?? ""));
  return String(value ?? "").replace(/["\\]/g, "\\$&");
}

function renderMarkdown(value) {
  if (!value) return "";
  const codeSpans = [];
  let text = escapeHtml(value).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  text = text.replace(/`([^`\n]+?)`/g, (_match, code) => {
    const token = `@@CODE_SPAN_${codeSpans.length}@@`;
    codeSpans.push(`<code>${code}</code>`);
    return token;
  });
  text = text
    .replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^\*])\*([^*\n]+?)\*/g, "$1<em>$2</em>");
  codeSpans.forEach((code, index) => {
    text = text.replaceAll(`@@CODE_SPAN_${index}@@`, code);
  });

  const lines = text.split("\n");
  const chunks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) {
      i += 1;
      continue;
    }
    if (/^#{2,4}\s+/.test(line)) {
      chunks.push(`<h4>${line.replace(/^#{2,4}\s+/, "")}</h4>`);
      i += 1;
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        const item = lines[i].trim().replace(/^[-*]\s+/, "");
        i += 1;
        const nested = [];
        while (i < lines.length && /^\s{2,}\d+\.\s+/.test(lines[i])) {
          nested.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
          i += 1;
        }
        items.push(nested.length
          ? `${item}<ol>${nested.map((nestedItem) => `<li>${nestedItem}</li>`).join("")}</ol>`
          : item);
      }
      chunks.push(`<ul>${items.map((item) => `<li>${item}</li>`).join("")}</ul>`);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i += 1;
      }
      chunks.push(`<ol>${items.map((item) => `<li>${item}</li>`).join("")}</ol>`);
      continue;
    }

    const paragraph = [];
    while (i < lines.length) {
      const current = lines[i].trim();
      if (!current || /^[-*]\s+/.test(current) || /^\d+\.\s+/.test(current) || /^#{2,4}\s+/.test(current)) break;
      paragraph.push(current);
      i += 1;
    }
    if (paragraph.length) chunks.push(`<p>${paragraph.join("<br>")}</p>`);
  }

  return chunks.join("");
}

async function api(path, body = null, requestOptions = {}) {
  const method = requestOptions.method || (body !== null ? "POST" : "GET");
  const options = {
    method,
    credentials: "same-origin",
    headers: { ...(requestOptions.headers || {}) },
  };
  if (body !== null) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
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
  if (!response.ok) {
    const error = new Error(payload?.error || `Request failed: ${response.status} ${response.statusText}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function setBusy(message) {
  $("#busyBar").classList.toggle("hidden", !message);
  text("busyText", message || "");
}

let fontStyleTransitionTimer = null;
let candidateNameSaveTimer = null;

function applyFontStyle(value) {
  const style = fontStyles.has(value) ? value : "default";
  state.fontStyle = style;

  // Clear any pending transition
  if (fontStyleTransitionTimer) {
    clearTimeout(fontStyleTransitionTimer);
  }

  // Animate font options background immediately
  document.querySelectorAll(".font-options").forEach((el) => {
    el.classList.toggle("academic", style === "academic");
    el.classList.toggle("popular", style === "popular");
  });

  // Update button active states
  document.querySelectorAll("[data-font-style]").forEach((button) => {
    button.classList.toggle("active", button.dataset.fontStyle === style);
  });

  // Delay body class change to wait for slider animation (250ms)
  fontStyleTransitionTimer = setTimeout(() => {
    document.body.classList.toggle("font-academic", style === "academic");
    document.body.classList.toggle("font-popular", style === "popular");
    fontStyleTransitionTimer = null;
  }, 250);

  try {
    localStorage.setItem(FONT_STORAGE_KEY, style);
  } catch (_error) {
    // Ignore storage failures; the visual selection still applies for this session.
  }
}

function loadFontStyle() {
  let stored = "default";
  try {
    stored = localStorage.getItem(FONT_STORAGE_KEY) || "default";
  } catch (_error) {
    stored = "default";
  }
  applyFontStyle(stored);
}

function candidateNames() {
  return {
    fullName: ($("#fullNameInput")?.value || DEFAULT_FULL_NAME).trim() || DEFAULT_FULL_NAME,
    englishName: ($("#englishNameInput")?.value || DEFAULT_ENGLISH_NAME).trim() || DEFAULT_ENGLISH_NAME,
  };
}

function storeCandidateNamesLocally(names) {
  try {
    localStorage.setItem(FULL_NAME_STORAGE_KEY, names.fullName);
    localStorage.setItem(ENGLISH_NAME_STORAGE_KEY, names.englishName);
  } catch (_error) {
    // Local identity settings still apply for the current session.
  }
}

function applyCandidateNames(names, persistLocal = false) {
  const fullName = (names?.fullName || DEFAULT_FULL_NAME).trim() || DEFAULT_FULL_NAME;
  const englishName = (names?.englishName || DEFAULT_ENGLISH_NAME).trim() || DEFAULT_ENGLISH_NAME;
  if ($("#fullNameInput")) $("#fullNameInput").value = fullName;
  if ($("#englishNameInput")) $("#englishNameInput").value = englishName;
  if (persistLocal) storeCandidateNamesLocally({ fullName, englishName });
  updateAvatars(englishName);
}

async function saveCandidateNames(syncBackend = true) {
  const names = candidateNames();
  updateAvatars(names.englishName);
  if (state.account.authenticated && syncBackend) {
    const payload = await api("/api/accounts/me/", {
      full_name: names.fullName,
      english_name: names.englishName,
      display_name: names.englishName,
    }, { method: "PATCH" });
    state.account.user = payload.user || state.account.user;
    renderAccountStatus("姓名已同步到账号。");
    return;
  }
  storeCandidateNamesLocally(names);
  renderAccountStatus(state.account.backendAvailable ? "未登录，姓名暂存在本机。" : "Django 未连接，姓名暂存在本机。");
}

function scheduleCandidateNameSave() {
  updateAvatars(candidateNames().englishName);
  if (candidateNameSaveTimer) clearTimeout(candidateNameSaveTimer);
  candidateNameSaveTimer = setTimeout(() => {
    candidateNameSaveTimer = null;
    saveCandidateNames().catch((error) => renderAccountStatus(error.message, true));
  }, 650);
}

function flushCandidateNameSave() {
  if (candidateNameSaveTimer) {
    clearTimeout(candidateNameSaveTimer);
    candidateNameSaveTimer = null;
  }
  saveCandidateNames().catch((error) => renderAccountStatus(error.message, true));
}

function updateAvatars(name) {
  const initial = (name || "J").charAt(0).toUpperCase();
  ["userAvatarDesktop", "userAvatar"].forEach((id) => {
    const avatar = $(id);
    if (avatar) avatar.textContent = initial;
  });
}

function loadCandidateNames() {
  let fullName = DEFAULT_FULL_NAME;
  let englishName = DEFAULT_ENGLISH_NAME;
  try {
    fullName = localStorage.getItem(FULL_NAME_STORAGE_KEY) || fullName;
    englishName = localStorage.getItem(ENGLISH_NAME_STORAGE_KEY) || englishName;
  } catch (_error) {
    // Use defaults.
  }
  applyCandidateNames({ fullName, englishName });
}

async function withBusy(message, action) {
  setBusy(message);
  try {
    return await action();
  } finally {
    setBusy("");
  }
}

function switchView(view, options = {}) {
  if (!viewCopy[view]) view = "mock";
  if (view === state.view && !options.force) return;
  if (state.practiceLocked && ["mock", "p1", "p2", "p3"].includes(state.view) && view === "settings" && options.preservePractice) {
    showSettingsOverlay();
    return;
  }
  stopAllRuntime("Ready");
  state.view = view;
  state.practiceViewBeforeSettings = null;
  // Save view to localStorage
  try {
    localStorage.setItem(VIEW_STORAGE_KEY, view);
  } catch (e) {
    // Ignore storage errors
  }
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
    button.classList.toggle("tone-mock", button.dataset.view === "mock");
    button.classList.toggle("tone-p1", button.dataset.view === "p1");
    button.classList.toggle("tone-p2", button.dataset.view === "p2");
    button.classList.toggle("tone-p3", button.dataset.view === "p3");
  });
  $("#practicePanel").classList.toggle("hidden", !["mock", "p1", "p2", "p3"].includes(view));
  $("#historyPanel").classList.toggle("hidden", view !== "history");
  $("#writingPanel")?.classList.toggle("hidden", view !== "writing");
  $("#writingReportsPanel")?.classList.toggle("hidden", view !== "writingReports");
  $("#settingsPanel").classList.toggle("hidden", view !== "settings");
  $("#settingsNameFields")?.classList.toggle("hidden", view !== "settings");
  $("#settingsBackButton")?.classList.toggle("hidden", true);
  $(".workspace").classList.toggle("history-workspace", view === "history" || view === "writingReports");
  $(".workspace").classList.toggle("writing-workspace", view === "writing");
  $(".topbar").classList.toggle("hidden", view === "history" || view === "writing" || view === "writingReports");
  $("#viewTitleBlock").classList.toggle("hidden", view === "history" || view === "writing" || view === "writingReports");
  text("viewTitle", viewCopy[view][0]);
  text("viewSubtitle", viewCopy[view][1]);
  if (view === "history") loadHistory();
  if (view === "writing") loadWriting();
  if (view === "writingReports") loadWritingReports();
  if (view === "settings") loadSettings();
  if (["mock", "p1", "p2", "p3"].includes(view)) resetPracticeSurface();
  updateSidebarLock();
}

function showSettingsOverlay() {
  const practiceView = ["mock", "p1", "p2", "p3"].includes(state.view) ? state.view : (state.practiceViewBeforeSettings || "mock");
  state.practiceViewBeforeSettings = practiceView;
  state.view = "settings";
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.remove("active");
    button.classList.toggle("tone-mock", button.dataset.view === "mock");
    button.classList.toggle("tone-p1", button.dataset.view === "p1");
    button.classList.toggle("tone-p2", button.dataset.view === "p2");
    button.classList.toggle("tone-p3", button.dataset.view === "p3");
  });
  $("#practicePanel").classList.add("hidden");
  $("#historyPanel").classList.add("hidden");
  $("#writingPanel")?.classList.add("hidden");
  $("#writingReportsPanel")?.classList.add("hidden");
  $("#settingsPanel").classList.remove("hidden");
  $("#settingsNameFields")?.classList.remove("hidden");
  $(".workspace").classList.remove("history-workspace", "writing-workspace");
  $(".topbar").classList.remove("hidden");
  $("#viewTitleBlock").classList.remove("hidden");
  text("viewTitle", viewCopy.settings[0]);
  text("viewSubtitle", "Settings are open. Your speaking flow is still running in the background.");
  $("#settingsBackButton")?.classList.remove("hidden");
  loadSettings();
  updateSidebarLock();
}

function returnFromSettings() {
  const practiceView = state.practiceViewBeforeSettings || "mock";
  state.view = practiceView;
  state.practiceViewBeforeSettings = null;
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === practiceView);
    button.classList.toggle("tone-mock", button.dataset.view === "mock");
    button.classList.toggle("tone-p1", button.dataset.view === "p1");
    button.classList.toggle("tone-p2", button.dataset.view === "p2");
    button.classList.toggle("tone-p3", button.dataset.view === "p3");
  });
  $("#settingsPanel").classList.add("hidden");
  $("#settingsNameFields")?.classList.add("hidden");
  $("#settingsBackButton")?.classList.add("hidden");
  $("#practicePanel").classList.remove("hidden");
  text("viewTitle", viewCopy[practiceView][0]);
  text("viewSubtitle", viewCopy[practiceView][1]);
  updateSidebarLock();
}

function resetPracticeSurface() {
  state.practiceLocked = false;
  state.status = "idle";
  state.attempt = null;
  state.currentTurn = null;
  state.transcript = "";
  clearExaminerAudioPreloads();
  const summaryPanel = $("#summaryPanel");
  $("#candidateAudio")?.classList.add("hidden");
  $("#examinerAudio")?.classList.add("hidden");
  $("#browserTtsFallback")?.classList.add("hidden");
  $("#cueTop")?.classList.add("hidden");
  $("#promptPane")?.classList.remove("hidden");
  $("#p3TopicPanel")?.classList.toggle("hidden", state.view !== "p3");
  $("#practiceGrid")?.classList.remove("p2-mode", "practice-enter");
  $("#practiceGrid")?.classList.toggle("hidden", state.view === "p3");
  summaryPanel?.classList.add("hidden");
  if (summaryPanel) summaryPanel.innerHTML = "";
  $("#exitPractice")?.classList.add("hidden");
  updateSidebarLock();
  text("progressTrack", state.view === "mock" ? "Mock practice: P1 -> P2 -> P3" : `${viewCopy[state.view][0]} ready`);
  text("phaseLabel", "Ready");
  text("timerValue", "00:00");
  $("#phaseMeter").style.width = "0%";
  text("promptKicker", "Prompt");
  setPromptHtml("Start a voice practice session to load a question.", "short");
  text("followUp", "");
  setRecordButton("ready", "Start", "Record the full section. No typing.");
  text("recordStatus", "Click Start. The examiner will load the questions automatically.");
}

function setRecordButton(status, title, hint) {
  state.status = status;
  $("#recordControl").className = `record-control ${status}`;
  $("#recordControl").disabled = ["loading", "examiner_playing", "processing", "scoring", "turn_saved"].includes(status);
  text("recordTitle", title);
  text("recordHint", hint);
  // Timer color based on status
  const timerEl = $("#timerValue");
  timerEl?.classList.remove("timer-analyzing");
  // Analyzing dots
  const dotsEl = $("#analyzingDots");
  const isAnalyzing = status === "processing" || status === "scoring";
  dotsEl?.classList.toggle("hidden", !isAnalyzing);

  if (status === "preparing") {
    if (timerEl) timerEl.style.color = "#3b82f6"; // blue
  } else if (status === "recording") {
    if (timerEl) timerEl.style.color = "#ef4444"; // red
  } else if (isAnalyzing) {
    if (timerEl) {
      timerEl.style.color = "#d97706"; // amber
      timerEl.classList.add("timer-analyzing");
    }
  } else {
    if (timerEl) timerEl.style.color = "";
  }
  updateSidebarLock();
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
  // Check balance before starting
  try {
    const wallet = await api("/api/billing/wallet");
    const balance = Number(wallet.balance_rmb || 0);
    if (balance <= 0) {
      alert("余额不足，请先充值后再开始练习。");
      switchView("settings");
      return;
    }
  } catch (e) {
    // If wallet check fails, continue anyway
  }

  const mode = state.view === "mock" ? "mock" : state.view;
  state.abortingAttemptId = null;
  state.practiceLocked = true;
  $("#exitPractice").classList.remove("hidden");
  updateSidebarLock();
  if (mode === "p3") revealP3PracticeGrid();
  setRecordButton("loading", "Loading...", "Preparing exam section.");
  try {
    const theme = state.p3SelectedTopic || "";
    const names = candidateNames();
    const attempt = await api("/api/attempts/start", {
      mode,
      candidate: names.englishName,
      full_name: names.fullName,
      english_name: names.englishName,
      ...(mode === "p3" ? { p3_intensity: state.p3Intensity } : {}),
      ...(mode === "p3" && theme ? { theme } : {}),
    });
    state.attempt = attempt;
    state.currentTurn = attempt.turns[0];
    $("#summaryPanel").classList.add("hidden");
    renderTurn(state.currentTurn);
    beginExaminerPhase();
  } catch (error) {
    state.practiceLocked = false;
    updateSidebarLock();
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
  const isP2 = turn.part === "p2";
  const isFollowUp = turn.prompt?.role === "follow_up";
  const isIntro = turn.counts_toward_total === false;
  if (turn.part === "p3") $("p3TopicPanel").classList.add("hidden");
  text("progressTrack", state.view === "mock" ? "Mock practice: P1 -> P2 -> P3" : `${viewCopy[state.view][0]} ready`);
  text("phaseLabel", turnProgressLabel(turn));
  text("promptKicker", isP2 ? "Cue card" : (isFollowUp ? "Follow-up" : (isIntro ? "Intro" : "Question")));
  text("followUp", isFollowUp ? "Follow-up question" : "");
  $("practiceGrid").classList.toggle("p2-mode", isP2);
  $("cueTop").classList.add("hidden");
  $("promptPane").classList.remove("hidden");
  renderExaminerAudio(turn);
  if (isP2 && turn.cue_card) {
    renderCueCardInPrompt(turn.cue_card);
    return;
  }
  setPromptHtml(`<p>${escapeHtml(turn.question)}</p>`, promptSize(turn.question));
}

function turnProgressLabel(turn) {
  if (!turn) return "";
  const part = String(turn.part || "").toUpperCase();
  const questionNumber = Number(turn.display_index ?? (Number(turn.index ?? 0) + 1));
  if (turn.prompt?.role === "follow_up") return `${part} -> Follow-up after Question ${questionNumber}/${turn.total}`;
  if (turn.counts_toward_total === false) return `${part} -> Intro`;
  return `${part} -> Question ${questionNumber}/${turn.total}`;
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
  $("cueTop").classList.remove("hidden");
  $("cueTop").innerHTML = `
    <h2>${escapeHtml(cue.title)}</h2>
    <p class="cue-label">You should say:</p>
    <ul>${bullets}</ul>
    <p>${escapeHtml(cue.rounding || "")}</p>
  `;
}

function renderExaminerAudio(turn) {
  const tts = turn.examiner_tts || {};
  const audio = $("examinerAudio");
  audio.classList.add("hidden");
  $("browserTtsFallback").classList.add("hidden");
  if (tts.audio_url) {
    prepareExaminerAudioElement(audio, tts.audio_url);
    primeExaminerAudio(tts.audio_url);
  }
}

function prepareExaminerAudioElement(audio, url) {
  if (!audio || !url) return;
  audio.preload = "auto";
  if (audio.dataset.src === url && audio.getAttribute("src") === url) return;
  audio.dataset.src = url;
  audio.src = url;
  audio.load();
}

function primeExaminerAudio(url) {
  if (!url || state.examinerAudioPreloads.has(url)) return state.examinerAudioPreloads.get(url);
  const preload = new Audio();
  preload.preload = "auto";
  preload.src = url;
  preload.load();
  state.examinerAudioPreloads.set(url, preload);
  while (state.examinerAudioPreloads.size > EXAMINER_AUDIO_PRELOAD_LIMIT) {
    const oldestUrl = state.examinerAudioPreloads.keys().next().value;
    state.examinerAudioPreloads.delete(oldestUrl);
  }
  return preload;
}

function clearExaminerAudioPreloads() {
  for (const audio of state.examinerAudioPreloads.values()) {
    audio.pause();
    audio.removeAttribute("src");
  }
  state.examinerAudioPreloads.clear();
}

function preloadNextExaminerAudio(turn) {
  const nextIndex = Number(turn?.index ?? -1) + 1;
  const nextTurn = (state.attempt?.turns || [])[nextIndex];
  const nextUrl = nextTurn?.examiner_tts?.audio_url;
  if (!nextUrl) return;
  primeExaminerAudio(nextUrl);
}

function waitForAudioReady(audio) {
  if (!audio || audio.readyState >= 3) return Promise.resolve();
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      audio.removeEventListener("canplay", finish);
      audio.removeEventListener("canplaythrough", finish);
      audio.removeEventListener("loadeddata", finish);
      audio.removeEventListener("error", finish);
      window.clearTimeout(timeout);
      resolve();
    };
    const timeout = window.setTimeout(finish, AUDIO_READY_TIMEOUT_MS);
    audio.addEventListener("canplay", finish, { once: true });
    audio.addEventListener("canplaythrough", finish, { once: true });
    audio.addEventListener("loadeddata", finish, { once: true });
    audio.addEventListener("error", finish, { once: true });
    audio.load();
  });
}

async function beginExaminerPhase() {
  if (!state.currentTurn) return;
  clearTimer();
  const turn = state.currentTurn;
  const turnId = turn.id;
  const isP2 = turn.part === "p2";
  const isIntro = turn.counts_toward_total === false;
  preloadNextExaminerAudio(turn);
  setRecordButton("examiner_playing", "Listening...", "The examiner is asking the question.");
  const progress = turnProgressLabel(turn);
  text("progressTrack", state.view === "mock" ? "Mock practice: P1 -> P2 -> P3" : `${viewCopy[state.view][0]} ready`);
  text("phaseLabel", `${progress} -> Examiner`);
  text("timerValue", "00:00");
  $("phaseMeter").style.width = "0%";
  text("recordStatus", isP2
    ? "Listen to the examiner instruction, then read the cue card during preparation."
    : turn.prompt?.role === "follow_up"
    ? "Listen to the examiner follow-up question. Preparation starts automatically."
    : isIntro
    ? "Listen to the examiner identity question. Preparation starts automatically."
    : "Listen to the examiner question. Preparation starts automatically.");

  const tts = turn.examiner_tts || {};
  if (tts.audio_url) {
    const preloaded = state.examinerAudioPreloads.get(tts.audio_url);
    if (preloaded && preloaded.readyState >= 3) {
      preloaded.onended = () => beginPreparation();
      preloaded.onerror = () => beginBrowserExaminerPlayback(turn.examiner_text || turn.question);
      preloaded.currentTime = 0;
      preloaded.play().catch(() => beginBrowserExaminerPlayback(turn.examiner_text || turn.question));
    } else {
      const audio = $("examinerAudio");
      audio.onended = () => beginPreparation();
      audio.onerror = () => beginBrowserExaminerPlayback(turn.examiner_text || turn.question);
      prepareExaminerAudioElement(audio, tts.audio_url);
      await waitForAudioReady(audio);
      if (state.currentTurn?.id !== turnId || state.status !== "examiner_playing") return;
      audio.currentTime = 0;
      audio.play().catch(() => beginBrowserExaminerPlayback(turn.examiner_text || turn.question));
    }
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
  preloadNextExaminerAudio(state.currentTurn);
  setRecordButton("preparing", isP2 ? "Skip" : "Prepare", isP2 ? "Click to start recording now." : "Recording starts automatically.");
  text("phaseLabel", `Preparing -> ${turnProgressLabel(state.currentTurn)}`);
  text("recordStatus", isP2 ? "Prepare your answer. Click to start recording early." : `Prepare your answer. Recording starts in ${seconds} seconds.`);
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
  text("phaseLabel", `${label} -> ${minutes}:${seconds}`);
  text("timerValue", `${minutes}:${seconds}`);
  const elapsed = Math.max(0, state.timerTotal - remaining);
  $("phaseMeter").style.width = `${Math.min(100, (elapsed / state.timerTotal) * 100)}%`;
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
  state.status = "recording";
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  state.mediaStream = stream;
  state.audioChunks = [];
  state.transcript = "";
  state.transcriptFinal = "";
  state.transcriptInterim = "";
  state.transcriptStatus = "missing";
  state.dictationRestartCount = 0;
  state.dictationLastError = "";
  setDictationStatus("starting", "浏览器转写启动中；如果开头静音，系统会自动重新监听。");
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
  text("recordStatus", "Recording in progress...");
  startRecordingTimer(state.currentTurn.timers.speak_seconds);
}

function stopRecording() {
  if (state.status !== "recording") return;
  state.status = "processing";
  clearTimer();
  setRecordButton("processing", "Saving", "Uploading this answer.");
  text("recordStatus", "Saving this answer...");
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
  } finally {
    state.audioChunks = [];
  }
}

async function scoreAttempt() {
  if (!state.attempt) return;
  const attemptId = state.attempt.id;
  setRecordButton("scoring", "Analyzing", "Analyzing the full section and generating the report.");
  text("recordStatus", "Analyzing the full section and generating the report.");
  try {
    const scored = await api(`/api/attempts/${attemptId}/score`, {});
    if (state.abortingAttemptId === attemptId || state.attempt?.id !== attemptId) return;
    state.attempt = scored;
    renderSummary(scored);
    await loadHistory(false);
    state.practiceLocked = false;
    updateSidebarLock();
    state.status = "summary";
    setRecordButton("summary", "Start Again", "Record another section.");
    text("recordStatus", "Section report is ready.");
    text("phaseLabel", "Scored");
    scrollToSummary();
  } catch (error) {
    showError(error);
  }
}

function updateSidebarLock() {
  const locked = !!state.practiceLocked;
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.disabled = false;
    button.setAttribute("aria-disabled", locked ? "true" : "false");
    button.classList.toggle("locked", locked);
  });
  const hint = $("navLockHint");
  hint?.classList.add("hidden");
  $("viewTitleBlock")?.classList.toggle("locked-flow", locked);
}

function showNavLockHint(button) {
  const hint = $("navLockHint");
  if (!hint || !button) return;
  const nav = button.closest(".nav");
  if (!nav) return;
  const buttonRect = button.getBoundingClientRect();
  const navRect = nav.getBoundingClientRect();
  hint.textContent = "Practice is active. Click the X to end it before switching views.";
  hint.style.top = `${Math.max(12, buttonRect.top - navRect.top + buttonRect.height + 8)}px`;
  hint.classList.remove("hidden", "toast-hide");
  void hint.offsetWidth;
  hint.classList.add("toast-show");
  clearTimeout(state.navToastTimer);
  state.navToastTimer = window.setTimeout(() => {
    hint.classList.add("toast-hide");
    hint.classList.remove("toast-show");
  }, 1400);
  window.setTimeout(() => {
    hint.classList.add("hidden");
  }, 2000);
}

function scrollToSummary() {
  $("summaryPanel")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function startDictation() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    state.transcriptStatus = "missing";
    setDictationStatus("unavailable", "当前浏览器不支持实时转写；录音会保存，但报告可能缺少文字稿。");
    return;
  }
  if (state.dictationRestartTimer) {
    window.clearTimeout(state.dictationRestartTimer);
    state.dictationRestartTimer = null;
  }
  state.dictationShouldRun = true;
  state.dictationStopping = false;
  const recognition = new SpeechRecognition();
  state.dictationRecognition = recognition;
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";
  setDictationStatus("listening", state.dictationRestartCount
    ? `浏览器转写已重新监听 ${state.dictationRestartCount} 次，可以继续说。`
    : "浏览器转写正在监听，请直接开口回答。");
  recognition.onresult = (event) => {
    let interim = "";
    let finalText = state.transcriptFinal || "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      const textValue = result[0]?.transcript || "";
      if (result.isFinal) {
        finalText = `${finalText} ${textValue}`.trim();
      } else {
        interim = textValue;
      }
    }
    state.transcriptFinal = finalText;
    state.transcriptInterim = interim;
    state.transcript = [finalText, interim].filter(Boolean).join(" ").trim();
    state.transcriptStatus = finalText ? "captured" : (interim ? "interim_fallback" : "missing");
    if (state.transcriptStatus === "captured") {
      setDictationStatus("captured", "已捕捉到转写，继续说即可。");
    } else if (state.transcriptStatus === "interim_fallback") {
      setDictationStatus("listening", "正在捕捉这段回答，停止后会保存最后结果。");
    }
  };
  recognition.onerror = (event) => {
    state.dictationLastError = event?.error || "";
    state.transcriptStatus = state.transcript ? state.transcriptStatus : "missing";
    if (["not-allowed", "service-not-allowed", "audio-capture"].includes(state.dictationLastError)) {
      state.dictationShouldRun = false;
      setDictationStatus("unavailable", "浏览器转写没有可用权限；录音仍会保存，但这题可能没有文字稿。");
      return;
    }
    setDictationStatus("reconnecting", "浏览器转写刚刚中断，正在自动重新监听。");
  };
  recognition.onend = () => {
    if (state.dictationShouldRun && !state.dictationStopping && state.status === "recording") {
      state.dictationRestartCount += 1;
      setDictationStatus("reconnecting", "浏览器转写因静音或网络波动结束，正在自动重新监听。");
      state.dictationRestartTimer = window.setTimeout(() => startDictation(), 250);
      return;
    }
    state.dictationRecognition = null;
    state.dictationShouldRun = false;
    state.dictationStopping = false;
    resolveDictationWait();
  };
  try {
    recognition.start();
  } catch {
    state.transcriptStatus = "missing";
    setDictationStatus("reconnecting", "浏览器转写启动失败，正在尝试重新监听。");
    if (state.dictationShouldRun && state.status === "recording") {
      state.dictationRestartCount += 1;
      state.dictationRestartTimer = window.setTimeout(() => startDictation(), 500);
    }
  }
}

function stopDictation() {
  state.dictationShouldRun = false;
  state.dictationStopping = true;
  setDictationStatus("saving", "正在保存最后一段浏览器转写。");
  if (state.dictationRestartTimer) {
    window.clearTimeout(state.dictationRestartTimer);
    state.dictationRestartTimer = null;
  }
  if (state.dictationRecognition) {
    try {
      state.dictationRecognition.stop();
    } catch {
      // ignore
    }
    window.setTimeout(resolveDictationWait, 800);
    return;
  }
  resolveDictationWait();
}

function setDictationStatus(kind, message) {
  const el = $("dictationStatus");
  if (!el) return;
  if (!message) {
    el.className = "dictation-status hidden";
    el.textContent = "";
    return;
  }
  el.className = `dictation-status ${kind || "info"}`;
  el.textContent = message;
}

function waitForFinalDictation() {
  if (!state.dictationRecognition) return Promise.resolve();
  if (state.dictationFinalWait) return state.dictationFinalWaitPromise;
  state.dictationFinalWaitPromise = new Promise((resolve) => {
    state.dictationFinalWait = resolve;
  });
  return state.dictationFinalWaitPromise;
}

function resolveDictationWait() {
  if (state.dictationFinalWait) {
    const resolve = state.dictationFinalWait;
    state.dictationFinalWait = null;
    state.dictationFinalWaitPromise = null;
    resolve();
  }
}

function renderSummary(attempt) {
  const score = attempt.ielts_score || {};
  const summaryPanel = $("summaryPanel");
  const summaryOverlay = $("summaryOverlay");
  if (!summaryPanel) return;

  summaryPanel.innerHTML = `
    <div class="score-row">
      ${scoreCell("Overall", score.overall_band)}
      ${scoreCell("Fluency", score.fluency_coherence)}
      ${scoreCell("Lexical", score.lexical_resource)}
      ${scoreCell("Grammar", score.grammatical_range)}
    </div>
    <p class="feedback">${escapeHtml(attempt.feedback_summary || "No feedback generated.")}</p>
    <div class="summary-actions">
      <button id="viewDetails">View Details</button>
      <button id="closeSummary" class="ghost">Close</button>
    </div>
  `;

  // Show panel and overlay
  summaryPanel.classList.remove("hidden");
  summaryPanel.classList.add("visible");
  if (summaryOverlay) {
    summaryOverlay.classList.remove("hidden");
    summaryOverlay.classList.add("visible");
  }

  const viewDetails = byId("viewDetails");
  if (viewDetails) {
    viewDetails.addEventListener("click", () => {
      hideSummary();
      renderDetail(attempt);
    });
  }

  const closeSummary = byId("closeSummary");
  if (closeSummary) {
    closeSummary.addEventListener("click", hideSummary);
  }
}

function hideSummary() {
  const summaryPanel = $("summaryPanel");
  const summaryOverlay = $("summaryOverlay");
  if (summaryPanel) {
    summaryPanel.classList.remove("visible");
    summaryPanel.classList.add("hidden");
  }
  if (summaryOverlay) {
    summaryOverlay.classList.remove("visible");
    summaryOverlay.classList.add("hidden");
  }
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
    $("historyList").textContent = "No attempts yet.";
    $("detailPanel").innerHTML = '<h2>Attempt Details</h2><p class="muted">No attempts to display.</p>';
    return;
  }
  $("historyList").innerHTML = items.map((item) => {
    const part = (item.mode || item.part || "").toLowerCase();
    const tagClass = ["p1", "p2", "p3", "mock"].includes(part) ? part : "";
    const toneClass = part === "mock" ? "tone-mock" : `tone-${tagClass || "neutral"}`;
    return `
    <div class="history-item-wrap">
      <button class="history-item ${toneClass} ${state.activeHistoryId === item.id ? "active" : ""}" data-attempt-id="${escapeHtml(item.id)}">
        <div class="history-item-top">
          <span class="history-item-tag ${tagClass}">${escapeHtml(part.toUpperCase())}</span>
          <span class="history-item-band">Band ${escapeHtml(item.overall_band ?? "—")}</span>
        </div>
        <strong class="history-item-title">${escapeHtml(item.title || item.question || "Untitled")}</strong>
        <small class="history-item-time">${escapeHtml(item.display_time || "")}</small>
      </button>
      <button class="history-item-menu-btn" data-attempt-id="${escapeHtml(item.id)}" aria-label="More options" title="More options">
        <span aria-hidden="true"></span>
      </button>
    </div>
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
  document.querySelectorAll(".history-item-menu-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      showHistoryItemMenu(btn, btn.dataset.attemptId);
    });
  });
  if (!state.activeHistoryId && items.length) {
    state.activeHistoryId = items[0].id;
    document.querySelector(".history-item")?.classList.add("active");
    api(`/api/history/${items[0].id}`).then((detail) => renderDetail(detail, false)).catch(showError);
  }
}

function showHistoryItemMenu(anchor, attemptId) {
  closeHistoryItemMenu();
  const menu = document.createElement("div");
  menu.className = "history-item-menu";
  menu.innerHTML = `<button class="history-menu-delete" data-attempt-id="${escapeHtml(attemptId)}">删除</button>`;
  anchor.parentElement.appendChild(menu);
  menu.querySelector(".history-menu-delete").addEventListener("click", (e) => {
    e.stopPropagation();
    closeHistoryItemMenu();
    showDeleteConfirm(attemptId);
  });
  setTimeout(() => document.addEventListener("click", closeHistoryItemMenu, { once: true }), 0);
}

function closeHistoryItemMenu() {
  document.querySelectorAll(".history-item-menu").forEach((el) => el.remove());
}

function showDeleteConfirm(attemptId) {
  const overlay = document.createElement("div");
  overlay.className = "confirm-overlay";
  overlay.innerHTML = `
    <div class="confirm-dialog">
      <p>确定要删除这条练习记录吗？</p>
      <div class="confirm-actions">
        <button class="confirm-cancel">取消</button>
        <button class="confirm-delete">删除</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.querySelector(".confirm-cancel").addEventListener("click", () => overlay.remove());
  overlay.querySelector(".confirm-delete").addEventListener("click", async () => {
    overlay.remove();
    try {
      await fetch(`/api/history/${attemptId}`, { method: "DELETE" });
      if (state.activeHistoryId === attemptId) state.activeHistoryId = null;
      await loadHistory(false);
    } catch (err) {
      showError(err);
    }
  });
}

function currentWritingWordCount() {
  const value = $("writingAnswer")?.value || "";
  const matches = value.match(/[A-Za-z]+(?:[-'][A-Za-z]+)?|\d+(?:\.\d+)?/g);
  return matches ? matches.length : 0;
}

function updateWritingWordCount() {
  const count = currentWritingWordCount();
  text("writingWordCount", `${count} word${count === 1 ? "" : "s"}`);
}

function setWritingPending(isPending, title = "", detail = "") {
  const wait = $("writingInlineWait");
  wait?.classList.toggle("hidden", !isPending);
  if (title) text("writingInlineWaitTitle", title);
  if (detail) text("writingInlineWaitText", detail);
  ["writingSaveBtn", "writingScoreBtn", "writingRandomBtn", "writingPromptSelect"].forEach((id) => {
    const element = $(id);
    if (element) element.disabled = isPending;
  });
  document.querySelectorAll("[data-writing-task]").forEach((button) => {
    button.disabled = isPending;
  });
}

function writingTaskLabel(taskType) {
  return taskType === "task1_academic" ? "Task 1 Academic" : "Task 2";
}

async function loadWriting() {
  try {
    await Promise.all([loadWritingPrompts(state.writing.taskType), loadWritingSummary(false)]);
    if (!state.writing.prompt) {
      const prompts = state.writing.prompts[state.writing.taskType] || [];
      if (prompts.length) setWritingPrompt(prompts[0], false);
      else await chooseRandomWritingPrompt(false);
    }
    renderWritingSurface();
  } catch (error) {
    showWritingError(error);
  }
}

async function loadWritingPrompts(taskType) {
  const normalized = taskType || "task1_academic";
  if (state.writing.prompts[normalized]?.length) return state.writing.prompts[normalized];
  const payload = await api(`/api/writing/prompts?task_type=${encodeURIComponent(normalized)}`);
  state.writing.prompts[normalized] = payload.items || [];
  return state.writing.prompts[normalized];
}

async function loadWritingSummary(render = true) {
  const payload = await api("/api/writing/summary");
  state.writing.month = payload.month || "";
  if (render) renderWritingSummary(payload);
  else renderWritingSummary(payload);
  return payload;
}

function renderWritingSummary(payload) {
  const stats = payload.stats || {};
  state.writing.recentEntries = payload.recent_entries || [];
  text("writingMonthLabel", `${payload.month || ""} 签到`);
  text("writingPracticedDays", stats.practiced_days ?? 0);
  text("writingStreakDays", stats.streak_days ?? 0);
  text("writingScoredCount", stats.scored_entries ?? 0);
  const days = payload.days || [];
  const weekLabels = ["一", "二", "三", "四", "五", "六", "日"];
  const firstDate = days.length ? new Date(`${days[0].date}T00:00:00`) : null;
  const leading = firstDate ? (firstDate.getDay() + 6) % 7 : 0;
  const blanks = Array.from({ length: leading }, () => '<span class="writing-day blank"></span>').join("");
  $("writingCalendar").innerHTML = `
    ${weekLabels.map((label) => `<span class="writing-weekday">${label}</span>`).join("")}
    ${blanks}
    ${days.map((day) => {
      const date = new Date(`${day.date}T00:00:00`);
      const label = Number.isNaN(date.getTime()) ? "" : date.getDate();
      return `<button type="button" class="writing-day ${escapeHtml(day.status || "empty")}" data-writing-entry-id="${escapeHtml(day.entry_id || "")}" title="${escapeHtml(day.date)}">${label}</button>`;
    }).join("")}
  `;
}

async function loadWritingReports() {
  try {
    const payload = await withBusy("Loading writing reports...", () => loadWritingSummary(false));
    await renderWritingReports(payload.recent_entries || []);
  } catch (error) {
    showWritingReportError(error);
  }
}

async function renderWritingReports(items) {
  const target = $("writingReportDetail");
  const list = $("writingReportList");
  if (!target) return;
  if (!items.length) {
    if (list) list.textContent = "还没有写作记录。";
    target.innerHTML = '<h2>写作报告</h2><p class="muted">还没有写作记录。保存一篇作文后会出现在这里。</p>';
    return;
  }
  const entries = await Promise.all(items.map((item) => api(`/api/writing/entries/${item.id}`)));
  const activeId = entries.some((entry) => entry.id === state.writing.activeReportId) ? state.writing.activeReportId : entries[0].id;
  state.writing.activeReportId = activeId;
  if (list) {
    list.innerHTML = entries.map((entry) => writingReportTabHtml(entry, entry.id === activeId)).join("");
    list.querySelectorAll("[data-writing-report-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        const entry = entries.find((item) => item.id === button.dataset.writingReportTab);
        if (!entry) return;
        state.writing.activeReportId = entry.id;
        list.querySelectorAll("[data-writing-report-tab]").forEach((item) => item.classList.toggle("active", item.dataset.writingReportTab === entry.id));
        target.innerHTML = writingReportDetailHtml(entry);
        target.scrollTo({ top: 0, behavior: "smooth" });
      });
    });
  }
  target.innerHTML = writingReportDetailHtml(entries.find((entry) => entry.id === activeId) || entries[0]);
}

function writingReportTabHtml(entry, active = false) {
  const score = entry?.score || null;
  const part = entry.task_type === "task1_academic" ? "T1" : "T2";
  const band = score ? `Band ${score.overall_band ?? "—"}` : "未评分";
  const toneClass = entry.task_type === "task1_academic" ? "tone-p1" : "tone-p2";
  const tagClass = entry.task_type === "task1_academic" ? "p1" : "p2";
  return `
    <button class="history-item writing-report-tab ${toneClass} ${active ? "active" : ""}" data-writing-report-tab="${escapeHtml(entry.id || "")}">
      <div class="history-item-top">
        <span class="history-item-tag ${tagClass}">${part}</span>
        <span class="history-item-band">${escapeHtml(band)}</span>
      </div>
      <strong class="history-item-title">${escapeHtml(entry.title || writingTaskLabel(entry.task_type))}</strong>
      <small class="history-item-time">${escapeHtml(entry.practice_date || entry.display_time || "")} · ${escapeHtml(entry.word_count ?? 0)} words</small>
    </button>
  `;
}

function writingReportDetailHtml(entry) {
  const score = entry?.score || null;
  const taskKey = entry.task_type === "task1_academic" ? "task_achievement" : "task_response";
  const taskLabel = entry.task_type === "task1_academic" ? "TA" : "TR";
  const profile = entry?.writing_profile || null;
  const profileIssues = Array.isArray(profile?.top_issues) ? profile.top_issues : [];
  const profileEvidence = Array.isArray(profile?.recent_evidence) ? profile.recent_evidence : [];
  const profileBlock = profile ? `
    <div class="detail-card writing-profile-card">
      <div class="writing-profile-card-head">
        <div>
          <span class="section-label">Personalized profile</span>
          <h3>个性化画像</h3>
        </div>
        <strong>${escapeHtml(profile.total_scored ?? 0)} 次评分</strong>
      </div>
      <p>${escapeHtml(profile.primary_focus_text || "画像会随着更多真实作文评分逐步稳定。")}</p>
      ${profileIssues.length ? `<div class="writing-profile-tags">${profileIssues.map((item) => `<span>${escapeHtml(item.label || item.tag)} · ${escapeHtml(item.count ?? 0)}</span>`).join("")}</div>` : ""}
      ${profileEvidence.length ? `<ul class="writing-profile-evidence">${profileEvidence.slice(0, 3).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
    </div>
  ` : "";
  const scoreBlock = score ? `
    <div class="detail-card" data-writing-report-id="${escapeHtml(entry.id || "")}">
      <div class="detail-header">
        <div>
          <h2>${escapeHtml(entry.task_label || writingTaskLabel(entry.task_type))} report</h2>
          <p class="muted">${escapeHtml(entry.title || "")} - ${escapeHtml(entry.word_count ?? 0)} words</p>
        </div>
        <strong class="overall-badge">Band ${escapeHtml(score.overall_band ?? "—")}</strong>
      </div>
      <div class="score-row compact">
        ${scoreCell(taskLabel, score[taskKey])}
        ${scoreCell("CC", score.coherence_cohesion)}
        ${scoreCell("LR", score.lexical_resource)}
        ${scoreCell("GRA", score.grammatical_range_accuracy)}
      </div>
    </div>
    <div class="detail-card">
      <h3>AI 评分与辅导</h3>
      <div class="coaching-content">${renderMarkdown(score.feedback_markdown || "暂无反馈。")}</div>
    </div>
    ${profileBlock}
  ` : `
    <div class="detail-card" data-writing-report-id="${escapeHtml(entry.id || "")}">
      <div class="detail-header">
        <div>
          <h2>${escapeHtml(entry.task_label || writingTaskLabel(entry.task_type))} saved</h2>
          <p class="muted">${escapeHtml(entry.title || "")} - ${escapeHtml(entry.word_count ?? 0)} words</p>
        </div>
        <strong class="overall-badge muted-badge">未评分</strong>
      </div>
      <p class="muted">这篇作文已保存并计入签到。需要反馈时，回到每日写作打开后点击 AI 评分与辅导。</p>
    </div>
  `;
  return `
    ${scoreBlock}
    <div class="detail-card writing-report-prompt">
      <h3>题目</h3>
      <div class="coaching-content">${renderMarkdown(entry.prompt || "")}</div>
    </div>
    <div class="detail-card writing-report-answer">
      <h3>Your answer</h3>
      <p>${escapeHtml(entry.answer || "").replace(/\n/g, "<br>")}</p>
    </div>
  `;
}

function setWritingPrompt(prompt, clearAnswer = true) {
  state.writing.prompt = prompt;
  state.writing.taskType = prompt.task_type || state.writing.taskType;
  if (clearAnswer) {
    state.writing.entry = null;
    state.writing.dirty = false;
    if ($("writingAnswer")) $("writingAnswer").value = "";
  }
  renderWritingSurface();
}

function renderWritingSurface() {
  const taskType = state.writing.taskType || "task1_academic";
  document.querySelectorAll("[data-writing-task]").forEach((button) => {
    button.classList.toggle("active", button.dataset.writingTask === taskType);
  });
  const prompts = state.writing.prompts[taskType] || [];
  const select = $("writingPromptSelect");
  if (select) {
    select.innerHTML = prompts.map((prompt) => `<option value="${escapeHtml(prompt.id)}">${escapeHtml(prompt.title)}</option>`).join("");
    if (state.writing.prompt?.id) select.value = state.writing.prompt.id;
  }
  const prompt = state.writing.prompt;
  text("writingPromptType", writingTaskLabel(taskType));
  text("writingPromptTitle", prompt?.title || "选择一道题开始");
  $("writingPromptText").innerHTML = renderMarkdown(prompt?.prompt || "请选择一道题，或点击随机题开始。");
  const entry = state.writing.entry;
  renderWritingScore(entry);
  updateWritingWordCount();
  if (!entry?.id) {
    text("writingSaveStatus", "未保存");
  } else if (entry.status === "scored") {
    text("writingSaveStatus", `已评分 · ${entry.practice_date || ""} · 可在写作报告查看`);
  } else {
    text("writingSaveStatus", `已保存 · ${entry.practice_date || ""}`);
  }
}

function renderWritingScore(entry) {
  const score = entry?.score || null;
  if (!score) {
    return;
  }
  text("writingSaveStatus", `已评分 · Band ${score.overall_band ?? "—"} · 可在写作报告查看`);
}

async function chooseRandomWritingPrompt(confirmDirty = true) {
  if (confirmDirty && state.writing.dirty && !window.confirm("当前作文还没有保存，确定要换题吗？")) return;
  const prompt = await withBusy("Loading writing prompt...", () => api("/api/writing/prompts/random", { task_type: state.writing.taskType }));
  setWritingPrompt(prompt, true);
}

async function saveWritingEntry(keepPending = false) {
  const prompt = state.writing.prompt;
  if (!prompt) throw new Error("请先选择一道写作题。");
  const answer = $("writingAnswer")?.value || "";
  const payload = {
    id: state.writing.entry?.id,
    task_type: prompt.task_type || state.writing.taskType,
    prompt_id: prompt.id,
    prompt: prompt.prompt,
    title: prompt.title,
    category: prompt.category,
    answer,
  };
  setWritingPending(true, "正在保存作文", "保存免费，完成后会直接计入今天的签到。");
  try {
    const entry = await withBusy("Saving writing...", () => api("/api/writing/entries", payload));
    state.writing.entry = entry;
    state.writing.dirty = false;
    renderWritingSurface();
    await loadWritingSummary();
    return entry;
  } finally {
    if (!keepPending) setWritingPending(false);
  }
}

async function scoreWritingEntry() {
  setWritingPending(true, "AI 正在评分与生成辅导", "正在分析题目、你的作文和 IELTS 写作评分标准。");
  try {
    let entry = state.writing.entry;
    if (!entry || state.writing.dirty) {
      entry = await saveWritingEntry(true);
      setWritingPending(true, "AI 正在评分与生成辅导", "作文已保存，正在继续生成写作反馈。");
    }
    try {
      const wallet = await api("/api/billing/wallet");
      if (Number(wallet.balance_rmb || 0) <= 0) {
        alert("余额不足，请先充值后再使用 AI 评分与辅导。");
        switchView("settings");
        return;
      }
    } catch (_error) {
      // Backend scoring still handles billing/fallback; keep the writing flow usable.
    }
    const scored = await withBusy("AI 正在评分与生成辅导...", () => api(`/api/writing/entries/${entry.id}/score`, { answer: $("writingAnswer")?.value || "" }));
    state.writing.entry = scored;
    state.writing.activeReportId = scored.id;
    state.writing.dirty = false;
    renderWritingSurface();
    await loadWritingSummary();
    switchView("writingReports");
  } finally {
    setWritingPending(false);
  }
}

async function openWritingEntry(entryId) {
  if (!entryId) return;
  if (state.writing.dirty && !window.confirm("当前作文还没有保存，确定要打开历史记录吗？")) return;
  const entry = await withBusy("Loading writing entry...", () => api(`/api/writing/entries/${entryId}`));
  state.writing.entry = entry;
  state.writing.taskType = entry.task_type || "task2";
  await loadWritingPrompts(state.writing.taskType);
  const prompt = {
    id: entry.prompt_id,
    task_type: entry.task_type,
    task_label: entry.task_label,
    title: entry.title,
    prompt: entry.prompt,
    category: entry.category,
  };
  state.writing.prompt = prompt;
  if ($("writingAnswer")) $("writingAnswer").value = entry.answer || "";
  state.writing.dirty = false;
  renderWritingSurface();
  await loadWritingSummary();
}

function showWritingError(error) {
  const message = error instanceof Error ? error.message : String(error);
  text("writingSaveStatus", message);
}

function showWritingReportError(error) {
  const message = error instanceof Error ? error.message : String(error);
  const list = $("writingReportList");
  if (list) list.textContent = "写作报告加载失败。";
  $("writingReportDetail").innerHTML = `<div class="detail-card"><p class="error">${escapeHtml(message)}</p></div>`;
}

function renderDetail(attempt, updateView = true, options = {}) {
  if (updateView) switchView("history");
  const detailPanel = $("detailPanel");
  const preserveScroll = Boolean(options.preserveScroll);
  const previousScrollTop = detailPanel?.scrollTop || 0;
  state.activeHistoryId = attempt.id;
  const score = attempt.ielts_score || {};
  const criteria = attempt.criteria_feedback || {};
  const turns = attempt.turns || [];
  const isP2 = attempt.mode === "p2" || (turns[0]?.part === "p2");
  const isMock = attempt.mode === "mock" || attempt.part === "mock";
  const p2CueCard = isP2 && !isMock && attempt.cue_card
    ? `<div class="detail-card p2-cue-card">${cueDetail(attempt.cue_card)}</div>`
    : "";
  const overallReview = overallReviewSection(attempt.overall_review || attempt.personalized_coaching);

  detailPanel.innerHTML = `
    <div class="detail-card">
      <div class="detail-header">
        <div>
          <h2>${escapeHtml((attempt.mode || attempt.part || "").toUpperCase())} report</h2>
          <p class="muted">${escapeHtml(attempt.title || "")} - ${turns.length} question${turns.length === 1 ? "" : "s"}</p>
        </div>
        <strong class="overall-badge">Band ${escapeHtml(score.overall_band ?? "—")}</strong>
      </div>
      <p class="feedback">${renderMarkdown(attempt.feedback_summary || "")}</p>
      <div class="score-row compact">
        ${scoreCell("FC", score.fluency_coherence)}
        ${scoreCell("LR", score.lexical_resource)}
        ${scoreCell("GRA", score.grammatical_range)}
      </div>
    </div>
    ${overallReview}
    ${p2CueCard}
    ${isMock ? mockTurnSections(attempt, turns) : turnTableSection(attempt, turns, isP2)}
    <div class="detail-card">
      <h3>Scoring criteria and upgrade guidance</h3>
      <div class="criteria-grid">
        ${criterionBlock("Fluency & Coherence", criteria.fluency_coherence)}
        ${criterionBlock("Lexical Resource", criteria.lexical_resource)}
        ${criterionBlock("Grammatical Range & Accuracy", criteria.grammatical_range_accuracy)}
      </div>
    </div>
  `;
  document.querySelectorAll("[data-speak-band7]").forEach((button) => {
    button.addEventListener("click", () => speakWithBrowser(button.dataset.speakBand7 || ""));
  });
  document.querySelectorAll("[data-regenerate-turn]").forEach((button) => {
    button.addEventListener("click", () => regenerateTurnFeedback(button));
  });
  document.querySelectorAll("[data-regenerate-transcript]").forEach((button) => {
    button.addEventListener("click", () => regenerateTurnTranscript(button));
  });
  if (preserveScroll) {
    detailPanel.scrollTop = previousScrollTop;
  } else {
    detailPanel.scrollTo({ top: 0, behavior: "smooth" });
  }
}

async function regenerateTurnFeedback(button) {
  const attemptId = state.activeHistoryId;
  const turnId = button?.dataset?.regenerateTurn || "";
  if (!attemptId || !turnId) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "重新生成中...";
  try {
    const payload = await api(`/api/attempts/${encodeURIComponent(attemptId)}/turns/${encodeURIComponent(turnId)}/feedback/regenerate`, {});
    renderDetail(payload.attempt, false, { preserveScroll: true });
  } catch (error) {
    button.disabled = false;
    button.textContent = originalText || "一键重新生成";
    alert(error instanceof Error ? error.message : String(error));
  }
}

async function regenerateTurnTranscript(button) {
  const attemptId = state.activeHistoryId;
  const turnId = button?.dataset?.regenerateTranscript || "";
  if (!attemptId || !turnId) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "重新转写中...";
  try {
    const payload = await api(`/api/attempts/${encodeURIComponent(attemptId)}/turns/${encodeURIComponent(turnId)}/transcript/regenerate`, {});
    renderDetail(payload.attempt, false, { preserveScroll: true });
  } catch (error) {
    button.disabled = false;
    button.textContent = originalText || "重新转写录音";
    alert(friendlyTranscriptionError(error instanceof Error ? error.message : String(error)));
  }
}

function overallReviewSection(review = {}) {
  const markdown = review.markdown || "";
  const comment = review.comment || review.focus || "";
  const points = review.review_points || review.next_practice || [];
  if (!markdown && !comment && !points.length) return "";
  const markdownFallback = markdown && !comment && !points.length ? renderMarkdown(markdown) : "";
  const body = markdownFallback || `
    ${comment ? `<h4>总体点评</h4><p>${escapeHtml(comment)}</p>` : ""}
    ${points.length ? `<h4>复盘重点</h4><ul>${points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>` : ""}
  `;
  return `
    <div class="detail-card overall-review-card">
      <h3>Overall Review & Practice Focus</h3>
      <div class="overall-review-content">${body}</div>
    </div>
  `;
}

function partScoreBlock(part, item = {}) {
  return `
    <div class="part-score-block">
      <div class="part-score-band">Band ${escapeHtml(item.band ?? "—")}</div>
      <div class="score-row mini">
        ${scoreCell("FC", item.fluency_coherence)}
        ${scoreCell("LR", item.lexical_resource)}
        ${scoreCell("GRA", item.grammatical_range)}
      </div>
    </div>
  `;
}

function turnTableSection(attempt, turns, isP2 = false) {
  const tableClass = isP2 ? "turn-report-table p2-report-table" : "turn-report-table p1-p3-report-table";
  const headers = isP2
    ? "<th>我的原文</th><th>7 分回答</th>"
    : "<th>Question</th><th>Your recording</th><th>Band 7 spoken version</th>";
  const bodyHtml = turns.map((turn) => turnReportGroup(attempt.id, turn, attempt, isP2)).join("");
  return `
    <div class="detail-card turn-report-card${isP2 ? " p2-report-card" : ""}">
      <div class="turn-report-wrap">
        <table class="${tableClass}">
          <thead><tr>${headers}</tr></thead>
          ${bodyHtml}
        </table>
      </div>
    </div>
  `;
}

function mockTurnSections(attempt, turns) {
  const partScores = attempt.part_scores || {};
  return ["p1", "p2", "p3"].map((part) => {
    const partTurns = turns.filter((turn) => turn.part === part);
    if (!partTurns.length) return "";
    const scoreBlock = partScores[part] ? partScoreBlock(part, partScores[part]) : "";
    const cueCard = part === "p2" && attempt.cue_card ? `<div class="detail-cue-wrap">${cueDetail(attempt.cue_card)}</div>` : "";
    const isP2 = part === "p2";
    const tableClass = isP2 ? "turn-report-table" : "turn-report-table p1-p3-report-table";
    const headers = isP2
      ? "<th>Your recording</th><th>Band 7 spoken version</th>"
      : "<th>Question</th><th>Your recording</th><th>Band 7 spoken version</th>";
    return `
      <div class="detail-section">
        <h3>${escapeHtml(part.toUpperCase())}</h3>
        <div class="part-detail-box">
          ${scoreBlock}
          ${cueCard}
          <table class="${tableClass}">
            <thead><tr>${headers}</tr></thead>
            ${partTurns.map((turn) => turnReportGroup(attempt.id, turn, attempt, isP2)).join("")}
          </table>
        </div>
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
  return missingTranscriptHtml(turn);
}

function missingTranscriptHtml(turn) {
  const hasAudio = !!((turn.audio || {}).url);
  if (!hasAudio) return '<p class="audio-warning">Recording missing. This turn has no playable audio.</p>';
  return `
    <div class="missing-transcript-notice">
      <strong>录音已保存，但没有拿到文字稿。</strong>
      <span>常见原因是开头静音后浏览器实时转写自动结束。新版录音会自动重连；这条旧录音可以尝试重新转写。</span>
      <button type="button" class="ghost regenerate-transcript-button" data-regenerate-transcript="${escapeHtml(turn.id)}">
        重新转写录音
      </button>
    </div>
  `;
}

function aiCoachingHtml(turn, attempt) {
  const coaching = turn.ai_coaching || attempt.ai_coaching || "";
  const fallback = isFallbackCoaching(turn, coaching);
  const fallbackNotice = fallback ? fallbackCoachingNotice(turn) : "";
  if (coaching) return `${fallbackNotice}<div class="coaching-content">${renderMarkdown(coaching)}</div>`;
  const notes = turn.upgrade_notes || attempt.upgrade_notes || [];
  if (!notes.length) return '<p class="muted">No AI coaching generated for this turn.</p>';
  return `${fallbackNotice}<ul>${notes.map((item) => `
    <li><strong>${escapeHtml(item.criterion || "Change")}:</strong> ${renderMarkdown(item.band7_change || item.original_problem || "")}</li>
  `).join("")}</ul>`;
}

function isFallbackCoaching(turn, coaching = "") {
  const backend = String(turn.feedback_generation_backend || "").toLowerCase();
  return backend === "fallback" || String(coaching || "").includes("AI 辅导生成失败");
}

function fallbackCoachingNotice(turn) {
  const error = turn.feedback_generation_error
    ? `<small>失败原因：${escapeHtml(friendlyFeedbackError(turn.feedback_generation_error))}</small>`
    : "<small>当前内容是规则兜底，不是本题 AI 重新分析结果。</small>";
  return `
    <div class="fallback-coaching-notice">
      <div>
        <strong>AI 辅导生成失败</strong>
        ${error}
      </div>
      <button type="button" class="ghost regenerate-feedback-button" data-regenerate-turn="${escapeHtml(turn.id)}">
        一键重新生成
      </button>
    </div>
  `;
}

function friendlyFeedbackError(error) {
  const value = String(error || "").trim();
  const lowered = value.toLowerCase();
  if (!value) return "AI 暂时没有返回可用内容。";
  if (lowered.includes("question-aware band 7 answer")) {
    return "AI 生成的 7 分答案和本题不够贴合，系统已保留默认建议。可以点击重新生成。";
  }
  if (lowered.includes("concise markdown coaching")) {
    return "AI 返回的辅导格式不符合报告要求，系统已保留默认建议。可以点击重新生成。";
  }
  if (lowered.includes("codex disabled")) {
    return "服务器当前关闭了 Codex 生成功能。";
  }
  if (lowered.includes("codex cli not found")) {
    return "服务器没有找到 Codex CLI。";
  }
  if (lowered.includes("timed out") || lowered.includes("timeout")) {
    return "AI 生成超时，系统已保留默认建议。可以稍后重试。";
  }
  return "AI 暂时没有返回可用内容，系统已保留默认建议。可以点击重新生成。";
}

function friendlyTranscriptionError(error) {
  const value = String(error || "").trim();
  const lowered = value.toLowerCase();
  if (!value) return "重新转写失败：服务器没有返回具体原因。";
  if (lowered.includes("azure speech key/region is not configured") || lowered.includes("azure speech is not configured")) {
    return "重新转写失败：服务器还没有配置 Azure Speech。新录音会继续用浏览器实时转写；如果要补旧录音，需要先配置 AZURE_SPEECH_KEY 和 AZURE_SPEECH_REGION。";
  }
  if (lowered.includes("ffmpeg")) {
    return "重新转写失败：服务器需要 ffmpeg 把浏览器录音转换成 Azure 可识别的 WAV。";
  }
  if (lowered.includes("sdk is not installed")) {
    return "重新转写失败：服务器缺少 Azure Speech SDK。";
  }
  if (lowered.includes("did not detect any speech") || lowered.includes("no speech")) {
    return "重新转写失败：服务没有在这段录音里识别到清晰英文。可以重录一次，并在开始后尽快开口。";
  }
  return value.startsWith("重新转写失败") ? value : `重新转写失败：${value}`;
}

function turnReportGroup(attemptId, turn, attempt, isP2 = false) {
  const groupClass = isP2 ? "turn-report-group p2-turn-group" : "turn-report-group p1-p3-turn-group";
  return `<tbody class="${groupClass}">${turnReportRow(attemptId, turn, attempt, isP2)}</tbody>`;
}

function turnReportRow(attemptId, turn, attempt, isP2 = false) {
  const modelAudio = turn.model_audio || {};
  const band7 = turn.band7_version || attempt.band7_version || "";
  const band7Markdown = turn.band7_markdown || attempt.band7_markdown || band7;
  const isFollowUp = turn.prompt?.role === "follow_up";

  // P2 layout: two rows - first row for content, second row for AI coaching
  if (isP2) {
    return `
      <tr class="p2-content-row">
        <td>
          ${isFollowUp ? '<span class="follow-up-pill">Follow-up</span>' : ""}
          ${(turn.audio || {}).url
            ? `<audio controls src="/api/audio/${escapeHtml(attemptId)}/${escapeHtml(turn.id)}/candidate"></audio>`
            : '<p class="audio-warning">Recording missing. This turn has no playable audio.</p>'}
          <p>${transcriptText(turn)}</p>
        </td>
        <td>
          ${modelAudio.audio_url ? `<audio controls src="${escapeHtml(modelAudio.audio_url)}"></audio>` : `<button class="ghost" data-speak-band7="${escapeHtml(band7)}">Play with browser voice</button>`}
          <p>${renderMarkdown(band7Markdown)}</p>
        </td>
      </tr>
      <tr class="p2-coaching-row">
        <td colspan="2" class="ai-coaching-cell">
          <h4 class="coaching-title">AI 辅导</h4>
          ${aiCoachingHtml(turn, attempt)}
        </td>
      </tr>
    `;
  }

  // Non-P2 layout: two rows - content row + AI coaching row
  const questionCell = `<td><div class="question-header"><strong>${escapeHtml(turn.part.toUpperCase())} ${turn.index + 1}</strong>${isFollowUp ? '<span class="follow-up-pill">Follow-up</span>' : ""}</div><p>${escapeHtml(turn.question)}</p></td>`;
  return `
    <tr class="p1-p3-content-row">
      ${questionCell}
      <td>
        ${(turn.audio || {}).url
          ? `<audio controls src="/api/audio/${escapeHtml(attemptId)}/${escapeHtml(turn.id)}/candidate"></audio>`
          : '<p class="audio-warning">Recording missing. This turn has no playable audio.</p>'}
        <p>${transcriptText(turn)}</p>
      </td>
      <td>
        ${modelAudio.audio_url ? `<audio controls src="${escapeHtml(modelAudio.audio_url)}"></audio>` : `<button class="ghost" data-speak-band7="${escapeHtml(band7)}">Play with browser voice</button>`}
        <p>${renderMarkdown(band7Markdown)}</p>
      </td>
    </tr>
    <tr class="p1-p3-coaching-row">
      <td colspan="3" class="ai-coaching-cell">
        <h4 class="coaching-title">AI 辅导</h4>
        ${aiCoachingHtml(turn, attempt)}
      </td>
    </tr>
  `;
}

function criterionBlock(title, item = {}) {
  const standard = item.standard || (item.strengths || [])[0] || "";
  const focus = item.focus || (item.problems || [])[0] || "";
  const advice = item.advice || item.suggestion || "";
  return `
    <article class="criterion">
      <h4>${escapeHtml(title)} - Band ${escapeHtml(item.band ?? "—")}</h4>
      <strong>Standard</strong><p>${renderMarkdown(standard)}</p>
      <strong>Focus</strong><p>${renderMarkdown(focus)}</p>
      <strong>Advice</strong><p>${renderMarkdown(advice)}</p>
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
  setDictationStatus("", "");
  state.browserTtsUtterance = null;
  state.currentTurn = null;
  state.transcript = "";
  state.transcriptFinal = "";
  state.transcriptInterim = "";
  state.transcriptStatus = "missing";
  state.practiceLocked = false;
  const summaryPanel = $("#summaryPanel");
  $("examinerAudio")?.pause();
  $("examinerAudio")?.removeAttribute("src");
  $("examinerAudio")?.removeAttribute("data-src");
  clearExaminerAudioPreloads();
  $("browserTtsFallback")?.classList.add("hidden");
  $("cueTop")?.classList.add("hidden");
  $("promptPane")?.classList.remove("cue");
  $("promptPane")?.classList.add("hidden");
  $("practiceGrid")?.classList.remove("p2-mode", "practice-enter");
  summaryPanel?.classList.add("hidden");
  if (summaryPanel) summaryPanel.innerHTML = "";
  $("exitPractice")?.classList.add("hidden");
  setRecordButton("ready", label, "Record the full section. No typing.");
  text("recordStatus", "Click Start. The examiner will load the questions automatically.");
  updateSidebarLock();
}

async function exitPractice() {
  const attemptId = state.attempt?.id;
  state.abortingAttemptId = attemptId;
  if (state.status === "recording") {
    state.cancelRecording = true;
    stopRecording();
  } else {
    stopAllRuntime("Ready");
  }
  state.practiceLocked = false;
  updateSidebarLock();
  if (attemptId) {
    await api(`/api/attempts/${attemptId}/abort`, {}).catch(() => null);
  }
  resetPracticeSurface();
}

function showError(error) {
  const message = error instanceof Error ? error.message : String(error);
  setBusy("");
  setRecordButton("ready", "Try Again", "The last attempt failed. Start again when ready.");
  text("recordStatus", "Something went wrong. Please try again.");
  $("summaryPanel").classList.remove("hidden");
  $("summaryPanel").innerHTML = `<p class="error">${escapeHtml(message)}</p>`;
}

function accountProfileNames(user) {
  const profile = user?.profile || {};
  return {
    fullName: String(profile.full_name || DEFAULT_FULL_NAME),
    englishName: String(profile.english_name || user?.display_name || DEFAULT_ENGLISH_NAME),
  };
}

function renderAccountStatus(message = "", isError = false) {
  const status = $("accountStatus");
  const details = $("accountDetails");
  const loginForm = $("accountLoginForm");
  const profileActions = $("accountProfileActions");
  const logoutBtn = $("accountLogoutBtn");
  const saveBtn = $("accountSaveProfileBtn");
  if (status) {
    const fallback = state.account.authenticated
      ? `已登录：${state.account.user?.username || ""}`
      : (state.account.backendAvailable ? "未登录，当前使用本机姓名。" : "Django 后端未连接，当前使用本机姓名。");
    status.textContent = message || fallback;
    status.classList.toggle("error", Boolean(isError));
  }
  if (details) {
    if (state.account.authenticated) {
      const user = state.account.user || {};
      const phone = user.phone_number ? ` · ${user.phone_number}` : "";
      details.textContent = `${user.username || "当前用户"}${phone}`;
    } else {
      details.textContent = "登录后，Full name / English name 会写入 Django 用户资料。";
    }
  }
  loginForm?.classList.toggle("hidden", state.account.authenticated);
  profileActions?.classList.toggle("hidden", !state.account.authenticated);
  if (logoutBtn) logoutBtn.disabled = !state.account.backendAvailable;
  if (saveBtn) saveBtn.disabled = !state.account.backendAvailable;
}

async function loadAccount() {
  try {
    const payload = await api("/api/accounts/me/");
    state.account.backendAvailable = true;
    state.account.authenticated = Boolean(payload.authenticated);
    state.account.user = payload.user || null;
    if (state.account.authenticated) {
      applyCandidateNames(accountProfileNames(state.account.user));
    }
    renderAccountStatus();
  } catch (error) {
    state.account.backendAvailable = error.status === 401;
    state.account.authenticated = false;
    state.account.user = null;
    renderAccountStatus(error.status === 401 ? "未登录，当前使用本机姓名。" : "Django 后端未连接，当前使用本机姓名。", false);
  }
}

async function submitAccountAuth(mode) {
  const username = ($("accountUsername")?.value || "").trim();
  const password = $("accountPassword")?.value || "";
  if (!username || !password) {
    renderAccountStatus("请输入用户名和密码。", true);
    return;
  }
  const names = candidateNames();
  const endpoint = mode === "register" ? "/api/accounts/register/" : "/api/accounts/login/";
  const payload = {
    username,
    password,
    full_name: names.fullName,
    english_name: names.englishName,
    display_name: names.englishName,
  };
  try {
    const result = await withBusy(mode === "register" ? "Creating account..." : "Signing in...", () => api(endpoint, payload));
    state.account.backendAvailable = true;
    state.account.authenticated = true;
    state.account.user = result.user || null;
    applyCandidateNames(accountProfileNames(state.account.user), true);
    renderAccountStatus(mode === "register" ? "账号已创建并登录。" : "已登录，Settings 已同步账号资料。");
    await Promise.all([loadWallet(), loadWritingSummary(false).catch(() => null)]);
  } catch (error) {
    state.account.backendAvailable = Boolean(error.status && error.status < 500);
    renderAccountStatus(error.message, true);
  }
}

async function logoutAccount() {
  try {
    await withBusy("Signing out...", () => api("/api/accounts/logout/", {}));
  } catch (_error) {
    // Keep the UI usable even if the backend session has already expired.
  }
  state.account.authenticated = false;
  state.account.user = null;
  loadCandidateNames();
  renderAccountStatus("已退出登录，姓名改为本机保存。");
}

function bindEvents() {
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.addEventListener("click", (event) => {
      if (state.practiceLocked && button.dataset.view === state.practiceViewBeforeSettings) {
        event.preventDefault();
        returnFromSettings();
        return;
      }
      if (button.dataset.view === state.view) {
        event.preventDefault();
        return;
      }
      if (state.practiceLocked && button.dataset.view !== state.view) {
        event.preventDefault();
        showNavLockHint(button);
        return;
      }
      switchView(button.dataset.view);
    });
  });
  document.querySelectorAll(".avatar-settings-button").forEach((button) => {
    button.addEventListener("click", () => {
      switchView("settings", { preservePractice: true });
    });
  });
  $("settingsBackButton")?.addEventListener("click", returnFromSettings);
  $("fullNameInput")?.addEventListener("input", scheduleCandidateNameSave);
  $("englishNameInput")?.addEventListener("input", scheduleCandidateNameSave);
  $("fullNameInput")?.addEventListener("blur", flushCandidateNameSave);
  $("englishNameInput")?.addEventListener("blur", flushCandidateNameSave);
  $("accountLoginBtn")?.addEventListener("click", () => submitAccountAuth("login"));
  $("accountRegisterBtn")?.addEventListener("click", () => submitAccountAuth("register"));
  $("accountLogoutBtn")?.addEventListener("click", logoutAccount);
  $("accountSaveProfileBtn")?.addEventListener("click", () => saveCandidateNames(true).catch((error) => renderAccountStatus(error.message, true)));
  $("recordControl")?.addEventListener("click", () => {
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
  $("exitPractice")?.addEventListener("click", () => exitPractice());
  $("p3StartButton")?.addEventListener("click", () => startPractice());
  document.querySelectorAll("[data-p3-intensity]").forEach((button) => {
    button.addEventListener("click", () => {
      state.p3Intensity = button.dataset.p3Intensity || "normal";
      document.querySelectorAll("[data-p3-intensity]").forEach((option) => {
        option.classList.toggle("active", option === button);
      });
      // Animate switch background
      const switchEl = document.querySelector(".p3-mode-switch");
      if (switchEl) {
        switchEl.classList.toggle("high-intensity", state.p3Intensity === "high");
      }
      // Update mode help text
      const helpEl = $("p3ModeHelp");
      if (helpEl) {
        helpEl.textContent = state.p3Intensity === "high"
          ? "追问加压、话题切换更快，适合高强度训练"
          : "每轮一个主问题，适合稳定练习节奏";
      }
    });
  });
  $("p3TopicChips")?.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-p3-topic]");
    if (!chip) return;
    state.p3SelectedTopic = chip.dataset.p3Topic || "";
    document.querySelectorAll("#p3TopicChips .topic-chip").forEach((c) => {
      c.classList.toggle("active", c === chip);
    });
  });
  document.querySelectorAll("[data-writing-task]").forEach((button) => {
    button.addEventListener("click", async () => {
      const taskType = button.dataset.writingTask || "task1_academic";
      if (taskType === state.writing.taskType) return;
      if (state.writing.dirty && !window.confirm("当前作文还没有保存，确定要切换 Task 吗？")) return;
      state.writing.taskType = taskType;
      state.writing.entry = null;
      state.writing.prompt = null;
      state.writing.dirty = false;
      if ($("writingAnswer")) $("writingAnswer").value = "";
      await loadWritingPrompts(taskType).catch(showWritingError);
      const prompts = state.writing.prompts[taskType] || [];
      if (prompts.length) setWritingPrompt(prompts[0], true);
      renderWritingSurface();
    });
  });
  $("writingPromptSelect")?.addEventListener("change", (event) => {
    if (state.writing.dirty && !window.confirm("当前作文还没有保存，确定要换题吗？")) {
      event.target.value = state.writing.prompt?.id || "";
      return;
    }
    const prompt = (state.writing.prompts[state.writing.taskType] || []).find((item) => item.id === event.target.value);
    if (prompt) setWritingPrompt(prompt, true);
  });
  $("writingRandomBtn")?.addEventListener("click", () => chooseRandomWritingPrompt(true).catch(showWritingError));
  $("writingSaveBtn")?.addEventListener("click", () => saveWritingEntry().catch(showWritingError));
  $("writingScoreBtn")?.addEventListener("click", () => scoreWritingEntry().catch(showWritingError));
  $("writingRefreshBtn")?.addEventListener("click", () => loadWriting().catch(showWritingError));
  $("writingAnswer")?.addEventListener("input", () => {
    state.writing.dirty = true;
    updateWritingWordCount();
    text("writingSaveStatus", "未保存的修改");
  });
  $("writingCalendar")?.addEventListener("click", (event) => {
    const day = event.target.closest("[data-writing-entry-id]");
    if (day?.dataset.writingEntryId) {
      state.writing.activeReportId = day.dataset.writingEntryId;
      switchView("writingReports");
    }
  });
  document.querySelectorAll("[data-font-style]").forEach((button) => {
    button.addEventListener("click", () => applyFontStyle(button.dataset.fontStyle || "default"));
  });
  $("summaryOverlay")?.addEventListener("click", hideSummary);
  // Recharge dialog
  $("openRechargeBtn")?.addEventListener("click", openRechargeDialog);
  $("cancelRechargeBtn")?.addEventListener("click", closeRechargeDialog);
  $("confirmRechargeBtn")?.addEventListener("click", doRecharge);
  $("rechargeDialog")?.addEventListener("click", (e) => {
    if (e.target.id === "rechargeDialog") closeRechargeDialog();
  });
  document.querySelectorAll("#rechargeDialog .recharge-btn[data-amount]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const amount = parseFloat(btn.dataset.amount) || 0;
      setRechargeAmount(amount);
    });
  });
  $("rechargeAmount")?.addEventListener("input", (e) => {
    const amount = parseFloat(e.target.value) || 0;
    state.pendingRecharge = amount;
    updateRechargePreview();
    // Deselect preset buttons when custom input
    document.querySelectorAll("#rechargeDialog .recharge-btn").forEach((btn) => {
      btn.classList.remove("selected");
    });
  });
}

function renderP3TopicChips(topics) {
  state.p3Topics = topics.slice(0, 8);
  $("p3TopicChips").innerHTML = state.p3Topics.map((topic) => (
    `<button type="button" class="topic-chip${state.p3SelectedTopic === topic ? " active" : ""}" data-p3-topic="${escapeHtml(topic)}">${escapeHtml(topic.replaceAll("_", " "))}</button>`
  )).join("");
  if (state.p3Topics.length && !state.p3SelectedTopic) {
    state.p3SelectedTopic = state.p3Topics[0];
    document.querySelector("#p3TopicChips .topic-chip")?.classList.add("active");
  }
}

async function loadSettings() {
  await Promise.all([loadAccount(), loadWallet(), loadWeakTraining(), loadReplayQueue()]);
}

function formatLocalTime(value) {
  if (!value) return "未安排";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未安排";
  return date.toLocaleString("zh-CN", { hour12: false });
}

async function loadWallet() {
  try {
    const wallet = await api("/api/billing/wallet");
    text("walletStatus", `余额 ¥${Number(wallet.balance_rmb || 0).toFixed(6)} · 预留 ¥${Number(wallet.reserved_rmb || 0).toFixed(6)}`);
    const entries = wallet.entries || [];
    $("ledgerList").innerHTML = entries.length
      ? entries.slice(0, 10).map((entry) => `<div class="settings-list-row"><strong>${escapeHtml(entry.entry_type)}</strong><span>¥${Number(entry.amount_rmb || 0).toFixed(6)}</span><small>${escapeHtml(entry.metadata?.reason || entry.created_at || "")}</small></div>`).join("")
      : '<p class="muted">暂无流水。</p>';
  } catch (error) {
    text("walletStatus", error.message);
  }
}

function openRechargeDialog() {
  state.pendingRecharge = 0;
  const dialog = $("rechargeDialog");
  if (dialog) {
    dialog.classList.remove("hidden");
    updateRechargePreview();
  }
}

function closeRechargeDialog() {
  const dialog = $("rechargeDialog");
  if (dialog) {
    dialog.classList.add("hidden");
  }
  state.pendingRecharge = 0;
}

function setRechargeAmount(amount) {
  state.pendingRecharge = amount;
  updateRechargePreview();
  // Update button selection
  document.querySelectorAll("#rechargeDialog .recharge-btn").forEach((btn) => {
    btn.classList.toggle("selected", parseFloat(btn.dataset.amount) === amount);
  });
  // Clear custom input if preset amount selected
  const input = $("rechargeAmount");
  if (input && amount > 0) input.value = "";
}

function updateRechargePreview() {
  const preview = $("rechargePreview");
  const btn = $("confirmRechargeBtn");
  if (preview) {
    preview.textContent = `¥${state.pendingRecharge.toFixed(2)}`;
  }
  if (btn) {
    btn.disabled = state.pendingRecharge <= 0;
  }
}

async function doRecharge() {
  if (state.pendingRecharge <= 0) return;

  const amount = state.pendingRecharge;
  try {
    await api("/api/billing/recharge", { amount_rmb: amount });
    closeRechargeDialog();
    await loadWallet();
  } catch (error) {
    showError(error);
  }
}

async function loadWeakTraining() {
  try {
    const payload = await api("/api/training/weak-items");
    const items = payload.items || [];
    text("weakTrainingStatus", `${items.length} 条弱题记录`);
    $("weakTrainingList").innerHTML = items.length
      ? items.slice(0, 6).map((item) => `<div class="settings-list-row"><strong>${escapeHtml((item.part || "").toUpperCase())}</strong><span>${escapeHtml((item.weak_reason || []).join("、") || "未命中明显弱项")}</span><small>${escapeHtml(item.question || "")}</small><small>下次复习：${escapeHtml(formatLocalTime(item.next_due))}</small></div>`).join("")
      : '<p class="muted">暂无弱题记录。</p>';
  } catch (error) {
    text("weakTrainingStatus", error.message);
  }
}

async function loadReplayQueue() {
  try {
    const payload = await api("/api/training/replay-queue");
    const items = payload.items || [];
    text("replayQueueStatus", `${items.length} 个复习项`);
    $("replayQueueList").innerHTML = items.length
      ? items.slice(0, 8).map((item) => {
          const sourceLabel = item.source === "weak" ? "弱项" : "补位";
          const detail = item.source === "weak" ? (item.weak_reason || []).join("、") || "未命中明显弱项" : "用于补足当前复习覆盖";
          return `<div class="settings-list-row"><strong>${escapeHtml(sourceLabel)}</strong><span>${escapeHtml((item.part || "").toUpperCase())}</span><small>${escapeHtml(item.question || "")}</small><small>${escapeHtml(detail)}</small></div>`;
        }).join("")
      : '<p class="muted">暂无复习队列。</p>';
  } catch (error) {
    text("replayQueueStatus", error.message);
  }
}

async function init() {
  loadFontStyle();
  loadCandidateNames();
  bindEvents();
  await loadAccount();
  // Exclusive audio playback - pause all others when one plays
  document.addEventListener("play", (e) => {
    if (e.target.tagName === "AUDIO") {
      document.querySelectorAll("audio").forEach((audio) => {
        if (audio !== e.target && !audio.paused) {
          audio.pause();
        }
      });
    }
  }, true);
  // Load saved view from localStorage
  let savedView = "mock";
  try {
    savedView = localStorage.getItem(VIEW_STORAGE_KEY) || "mock";
    if (!viewCopy[savedView]) savedView = "mock";
  } catch (e) {
    // Ignore storage errors
  }
  switchView(savedView);
  try {
    const summary = await api("/api/question-bank/summary");
    text("bankStatus", `${summary.part1_count} P1 · ${summary.part2_count} P2`);
    renderP3TopicChips(summary.part2_themes || []);
  } catch (error) {
    text("bankStatus", error.message);
  }
}

init();
