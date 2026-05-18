const state = {
  view: "home",
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
  historyItems: [],
  historyDetailCache: new Map(),
  abortingAttemptId: null,
  practiceViewBeforeSettings: null,
  p3Topics: [],
  p3SelectedTopic: "",
  p3Intensity: "normal",
  p1Corpus: {
    topics: [],
    activeEntry: null,
    previousPracticeView: "p1",
    saving: false,
  },
  p2Corpus: {
    categories: [],
    activeEntry: null,
    previousPracticeView: "p2",
    selectedEntryId: "",
    saving: false,
  },
  languageTakeaway: {
    items: [],
    loaded: false,
    selectedText: "",
    rangeRect: null,
    dragging: false,
    dragOffsetX: 0,
    dragOffsetY: 0,
    hideEnglish: false,
    revealedEntryIds: new Set(),
    selectionTimer: null,
  },
  practiceLocked: false,
  startRequestId: 0,
  practiceSessionId: 0,
  startAbortController: null,
  navToastTimer: null,
  fontStyle: "default",
  pendingRecharge: 0,
  examinerAudioPreloads: new Map(),
  activeExaminerAudio: null,
  writing: {
    taskType: "task1_academic",
    prompts: {},
    prompt: null,
    entry: null,
    dirty: false,
    month: "",
    recentEntries: [],
    reportEntries: [],
    activeReportId: null,
    activeReportDetail: null,
    reportDetailCache: new Map(),
    scorePollTimer: null,
    scorePollingEntryId: null,
    pickerTaskType: "task1_academic",
    promptCategories: {},
    promptCatalog: {},
    pickerCategoryFilters: {
      task1_academic: "",
      task2: "",
    },
  },
  account: {
    authenticated: false,
    backendAvailable: false,
    user: null,
    returnView: null,
  },
  prefetch: {
    started: false,
    token: 0,
  },
};

const FONT_STORAGE_KEY = "ielts-font-style";
const VIEW_STORAGE_KEY = "ielts-view";
const FULL_NAME_STORAGE_KEY = "ielts-full-name";
const ENGLISH_NAME_STORAGE_KEY = "ielts-english-name";
const fontStyles = new Set(["default", "academic", "popular"]);
const DEFAULT_FULL_NAME = "LiHua";
const DEFAULT_ENGLISH_NAME = "Jasper";
const corpusMarkdownEditors = {};
const FIXED_EXAMINER_AUDIO_URLS = new Set([
  "/api/tts-audio/examiner/fixed_examiner_what_is_your_full_name.mp3",
  "/api/tts-audio/examiner/fixed_examiner_do_you_work_or_do_you_study.mp3",
  "/api/tts-audio/examiner/fixed_examiner_p2_cue_card_instruction.mp3",
]);

const viewCopy = {
  home: ["首页", "选择今天要练的口语模式。"],
  mock: ["Mock", "完整模拟 P1、P2 和 P3 的口语考试流程。"],
  p1: ["Part 1", "Practice short questions in an IELTS-style interview flow."],
  p2: ["Part 2", "Cue card, one-minute preparation, then a long turn."],
  p3: ["Part 3", "Discussion generated from your P2 answer with normal or high-intensity practice."],
  corpus: ["语料库", "Manage prepared speaking material and language takeaways."],
  p1Corpus: ["我的 P1语料库", "Prepare grouped Part 1 answers and reuse them in AI feedback."],
  p2Corpus: ["我准备的P2串题素材库", "Prepare reusable Part 2 story materials and link them during preparation."],
  takeawayBook: ["Takeaway", "Review saved language takeaways with hidden English recall."],
  history: ["口语报告", ""],
  writing: ["每日写作", ""],
  writingReports: ["写作报告", ""],
  login: ["Sign in", "Sign in to access your reports, wallet, and personalized training."],
  register: ["Create account", "Create an account to save your practice history and access personalized features."],
  forgotPassword: ["Reset password", "Reset your password via email if configured."],
  accountProfile: ["Account", "Manage your profile and account settings."],
  accountSecurity: ["Security", "Change your password and manage security settings."],
};

const authViews = new Set(["login", "register", "forgotPassword"]);
const protectedViews = new Set(["history", "writing", "writingReports", "corpus", "p1Corpus", "p2Corpus", "takeawayBook", "accountProfile", "accountSecurity"]);
const corpusViews = new Set(["corpus", "p1Corpus", "p2Corpus", "takeawayBook"]);

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

let csrfToken = null;

async function ensureCsrfToken() {
  if (csrfToken) return csrfToken;
  try {
    const response = await fetch("/api/accounts/csrf/", { credentials: "same-origin" });
    const data = await response.json();
    csrfToken = data.csrfToken || null;
  } catch (_error) {
    csrfToken = null;
  }
  return csrfToken;
}

async function api(path, body = null, requestOptions = {}) {
  const method = requestOptions.method || (body !== null ? "POST" : "GET");
  const options = {
    method,
    credentials: "same-origin",
    headers: { ...(requestOptions.headers || {}) },
  };
  if (requestOptions.signal) options.signal = requestOptions.signal;
  if (body !== null) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  if (method !== "GET") {
    const token = await ensureCsrfToken();
    if (token) options.headers["X-CSRFToken"] = token;
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
    const message = payload?.message || payload?.error || `Request failed: ${response.status} ${response.statusText}`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = payload;
    error.errors = payload?.errors || null;
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

function applyFontStyle(value, options = {}) {
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

  const updateBodyClass = () => {
    document.body.classList.toggle("font-academic", style === "academic");
    document.body.classList.toggle("font-popular", style === "popular");
    fontStyleTransitionTimer = null;
  };
  if (options.immediate) {
    updateBodyClass();
  } else {
    // Delay body class change to wait for slider animation (250ms) on user-initiated changes.
    fontStyleTransitionTimer = setTimeout(updateBodyClass, 250);
  }

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
  applyFontStyle(stored, { immediate: true });
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

function scheduleIdleTask(action, timeout = 1200) {
  const run = () => {
    Promise.resolve()
      .then(action)
      .catch(() => {
        // Background prefetch should never interrupt the active learner flow.
      });
  };
  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(run, { timeout });
  } else {
    window.setTimeout(run, Math.min(timeout, 400));
  }
}

function prefetchCanApply(token) {
  return state.account.authenticated && state.prefetch.token === token;
}

function clearUserScopedCaches() {
  state.historyItems = [];
  state.historyDetailCache.clear();
  state.activeHistoryId = null;
  state.languageTakeaway.items = [];
  state.languageTakeaway.loaded = false;
  state.languageTakeaway.revealedEntryIds.clear();
  state.writing.reportEntries = [];
  state.writing.activeReportId = null;
  state.writing.activeReportDetail = null;
  state.writing.reportDetailCache.clear();
  state.prefetch.started = false;
  state.prefetch.token += 1;
}

function scheduleAuthenticatedPrefetch() {
  if (!state.account.authenticated || state.prefetch.started) return;
  state.prefetch.started = true;
  state.prefetch.token += 1;
  const token = state.prefetch.token;
  scheduleIdleTask(() => prefetchLanguageTakeaways(token), 600);
  scheduleIdleTask(() => prefetchSpeakingHistory(token), 1000);
  scheduleIdleTask(() => prefetchWritingReports(token), 1400);
}

async function prefetchLanguageTakeaways(token) {
  const payload = await api("/api/language-takeaways");
  if (!prefetchCanApply(token)) return;
  state.languageTakeaway.items = payload.items || [];
  state.languageTakeaway.loaded = true;
  if (state.view === "takeawayBook") {
    const stats = $("languageTakeawayStats");
    if (stats) stats.textContent = `${payload.count || 0} 条`;
    renderLanguageTakeawayToggle();
    renderLanguageTakeaways();
  }
}

async function prefetchSpeakingHistory(token) {
  const payload = await api("/api/history");
  if (!prefetchCanApply(token)) return;
  const items = payload.items || [];
  state.historyItems = items;
  const activeId = state.activeHistoryId && items.some((item) => item.id === state.activeHistoryId)
    ? state.activeHistoryId
    : items[0]?.id;
  if (activeId && !state.historyDetailCache.has(activeId)) {
    const detail = await api(`/api/history/${activeId}`);
    if (prefetchCanApply(token)) state.historyDetailCache.set(activeId, detail);
  }
  if (prefetchCanApply(token) && state.view === "history") {
    renderHistoryList(state.historyItems, { refreshActive: false });
  }
}

async function prefetchWritingReports(token) {
  const payload = await api("/api/writing/reports");
  if (!prefetchCanApply(token)) return;
  const items = payload.items || [];
  state.writing.reportEntries = items;
  const activeId = state.writing.activeReportId && items.some((item) => item.id === state.writing.activeReportId)
    ? state.writing.activeReportId
    : items[0]?.id;
  if (activeId && !state.writing.reportDetailCache.has(activeId)) {
    const detail = await api(`/api/writing/entries/${activeId}`);
    if (prefetchCanApply(token)) state.writing.reportDetailCache.set(activeId, detail);
  }
  if (prefetchCanApply(token) && state.view === "writingReports") {
    await renderWritingReports(state.writing.reportEntries, { refreshActive: false });
  }
}

function switchView(view, options = {}) {
  if (!viewCopy[view]) view = "home";
  if (protectedViews.has(view) && !state.account.authenticated && !options.skipAuthGate) {
    state.account.returnView = view;
    switchView("login", {
      force: true,
      skipAuthGate: true,
      authMessage: options.authMessage || loginReasonForView(view),
    });
    return;
  }
  if (view === "p1Corpus") {
    state.p1Corpus.previousPracticeView = ["mock", "p1", "p2", "p3"].includes(state.view) ? state.view : "p1";
  }
  if (view === "p2Corpus") {
    state.p2Corpus.previousPracticeView = ["mock", "p1", "p2", "p3"].includes(state.view) ? state.view : "p2";
  }
  if (view === state.view && !options.force) return;
  if (state.practiceLocked && ["mock", "p1", "p2", "p3"].includes(state.view) && ["accountProfile", "accountSecurity"].includes(view) && options.preservePractice) {
    showPracticeOverlay(view);
    return;
  }
  stopAllRuntime("Ready");
  if (!["writing", "writingReports"].includes(view)) {
    clearWritingScorePolling();
    setWritingPending(false);
  }
  state.view = view;
  state.practiceViewBeforeSettings = null;
  if (!options.skipUrl) updateViewUrl(view);
  if (!options.skipPersist) {
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, view);
    } catch (e) {
      // Ignore storage errors
    }
  }
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
    button.classList.toggle("tone-mock", button.dataset.view === "mock");
    button.classList.toggle("tone-p1", button.dataset.view === "p1");
    button.classList.toggle("tone-p2", button.dataset.view === "p2");
    button.classList.toggle("tone-p3", button.dataset.view === "p3");
  });
  $(".shell")?.classList.toggle("auth-shell", authViews.has(view));
  $(".shell")?.classList.toggle("account-shell", view === "accountProfile");
  $(".workspace")?.classList.toggle("corpus-workspace", ["corpus", "p1Corpus", "p2Corpus", "takeawayBook"].includes(view));
  $("#topbarBackCorpusBtn")?.classList.toggle("hidden", !["p1Corpus", "p2Corpus", "takeawayBook"].includes(view));
  $("#homePanel")?.classList.toggle("hidden", view !== "home");
  $("#practicePanel").classList.toggle("hidden", !["mock", "p1", "p2", "p3"].includes(view));
  $("#corpusPanel")?.classList.toggle("hidden", view !== "corpus");
  $("#p1CorpusPanel")?.classList.toggle("hidden", view !== "p1Corpus");
  $("#p2CorpusPanel")?.classList.toggle("hidden", view !== "p2Corpus");
  $("#takeawayBookPanel")?.classList.toggle("hidden", view !== "takeawayBook");
  $("#historyPanel").classList.toggle("hidden", view !== "history");
  $("#writingPanel")?.classList.toggle("hidden", view !== "writing");
  $("#writingReportsPanel")?.classList.toggle("hidden", view !== "writingReports");
  $("#loginPanel")?.classList.toggle("hidden", view !== "login");
  $("#authRequiredPanel")?.classList.toggle("hidden", true);
  $("#registerPanel")?.classList.toggle("hidden", view !== "register");
  $("#forgotPasswordPanel")?.classList.toggle("hidden", view !== "forgotPassword");
  $("#accountProfilePanel")?.classList.toggle("hidden", view !== "accountProfile");
  $("#accountSecurityPanel")?.classList.toggle("hidden", view !== "accountSecurity");
  $(".workspace").classList.toggle("history-workspace", view === "history" || view === "writingReports");
  $(".workspace").classList.toggle("writing-workspace", view === "writing");
  $(".topbar").classList.toggle("hidden", view === "history" || view === "writing" || view === "writingReports" || view === "corpus" || view === "p1Corpus" || view === "p2Corpus" || view === "takeawayBook" || authViews.has(view));
  $("#viewTitleBlock").classList.toggle("hidden", view === "history" || view === "writing" || view === "writingReports" || view === "corpus" || view === "p1Corpus" || view === "p2Corpus" || view === "takeawayBook" || authViews.has(view));
  text("viewTitle", viewCopy[view][0]);
  text("viewSubtitle", viewCopy[view][1]);
  if (view === "history") loadHistory();
  if (view === "corpus") loadCorpusHome();
  if (view === "takeawayBook") loadLanguageTakeaways();
  if (view === "writing") loadWriting();
  if (view === "writingReports") loadWritingReports();
  if (view === "p1Corpus") loadP1Corpus();
  if (view === "p2Corpus") loadP2Corpus();
  if (view === "accountProfile") loadAccountProfile();
  if (view === "accountSecurity") loadAccount();
  if (view === "login") prepareLoginView(options.authMessage || "");
  if (view === "forgotPassword") loadPasswordResetAvailability();
  $("#openP1CorpusBtn")?.classList.toggle("hidden", view !== "p1");
  $("#openP2CorpusBtn")?.classList.toggle("hidden", view !== "p2");
  $("#examStatusText")?.classList.remove("hidden");
  $("#exitPractice")?.classList.toggle("hidden", !state.practiceLocked || !["mock", "p1", "p2", "p3"].includes(view));
  if (["mock", "p1", "p2", "p3"].includes(view)) resetPracticeSurface();
  updateSidebarLock();
}

function requestedUrlView() {
  try {
    const view = new URLSearchParams(window.location.search).get("view");
    return viewCopy[view] ? view : "";
  } catch (_error) {
    return "";
  }
}

function requestedStandaloneView() {
  const view = requestedUrlView();
  return ["p1Corpus", "p2Corpus"].includes(view) ? view : "";
}

function updateViewUrl(view) {
  if (!window.history?.replaceState || !viewCopy[view]) return;
  const url = new URL(window.location.href);
  if (view === "home") {
    url.searchParams.delete("view");
  } else {
    url.searchParams.set("view", view);
  }
  window.history.replaceState({}, "", url.toString());
}

function openCorpusWindow(view) {
  if (!["p1Corpus", "p2Corpus"].includes(view)) return;
  const url = new URL(window.location.href);
  url.searchParams.set("view", view);
  const opened = window.open(url.toString(), "_blank");
  if (opened) opened.opener = null;
}

function closeCorpusWindowOrReturn() {
  if (requestedStandaloneView() && window.opener) {
    window.close();
    return;
  }
  switchView("corpus");
}

async function exitPracticeAndSwitch(view) {
  await exitPractice();
  switchView(view, { force: true });
}

function loginReasonForView(view) {
  const reasons = {
    history: "登录后才能查看你的口语报告和历史记录。",
    corpus: "登录后才能保存和管理你的语料库。",
    p1Corpus: "登录后才能保存和复用你的 P1 语料库。",
    p2Corpus: "登录后才能保存和复用你的 P2 串题素材库。",
    takeawayBook: "登录后才能查看和复习你的 Takeaway。",
    writing: "登录后才能保存每日写作、签到和 AI 评分记录。",
    writingReports: "登录后才能查看你的写作报告。",
    accountProfile: "请先登录后管理账号资料。",
    accountSecurity: "请先登录后修改账号安全设置。",
  };
  return reasons[view] || "请先登录后继续。";
}

function prepareLoginView(message = "") {
  const notice = $("loginNotice");
  if (notice) {
    notice.textContent = message || "登录后继续使用报告、钱包和个性化训练。";
    notice.classList.toggle("auth-notice-emphasis", Boolean(message));
  }
  const status = $("loginStatus");
  if (status) {
    status.textContent = "";
    status.classList.remove("error");
  }
}

function showPracticeOverlay(view = "accountProfile") {
  const practiceView = ["mock", "p1", "p2", "p3"].includes(state.view) ? state.view : (state.practiceViewBeforeSettings || "mock");
  state.practiceViewBeforeSettings = practiceView;
  state.view = view;
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
  $("#loginPanel")?.classList.add("hidden");
  $("#authRequiredPanel")?.classList.add("hidden");
  $("#registerPanel")?.classList.add("hidden");
  $("#forgotPasswordPanel")?.classList.add("hidden");
  $("#accountProfilePanel")?.classList.toggle("hidden", view !== "accountProfile");
  $("#accountSecurityPanel")?.classList.toggle("hidden", view !== "accountSecurity");
  $(".workspace").classList.remove("history-workspace", "writing-workspace");
  $(".topbar").classList.remove("hidden");
  $("#viewTitleBlock").classList.remove("hidden");
  text("viewTitle", viewCopy[view][0]);
  text("viewSubtitle", `${viewCopy[view][0]} 已打开，当前练习仍在后台保留。`);
  if (view === "accountProfile") loadAccountProfile();
  if (view === "accountSecurity") loadAccount();
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
  $("#loginPanel")?.classList.add("hidden");
  $("#authRequiredPanel")?.classList.add("hidden");
  $("#registerPanel")?.classList.add("hidden");
  $("#forgotPasswordPanel")?.classList.add("hidden");
  $("#accountProfilePanel")?.classList.add("hidden");
  $("#accountSecurityPanel")?.classList.add("hidden");
  $("#practicePanel").classList.remove("hidden");
  $(".shell")?.classList.remove("auth-shell", "account-shell");
  text("viewTitle", viewCopy[practiceView][0]);
  text("viewSubtitle", viewCopy[practiceView][1]);
  updateSidebarLock();
}

function resetPracticeSurface() {
  stopExaminerPlayback();
  state.practiceLocked = false;
  state.status = "idle";
  state.attempt = null;
  state.currentTurn = null;
  state.transcript = "";
  clearExaminerAudioPreloads();
  const summaryPanel = $("#summaryPanel");
  const isPracticeMode = ["mock", "p1", "p2", "p3"].includes(state.view);
  $(".exam-status")?.classList.toggle("hidden", !isPracticeMode);
  $("#examStatusText")?.classList.toggle("hidden", state.view === "p2");
  $("#candidateAudio")?.classList.add("hidden");
  $("#examinerAudio")?.classList.add("hidden");
  $("#browserTtsFallback")?.classList.add("hidden");
  const p2PrepPanel = $("#p2CorpusPrepPanel");
  p2PrepPanel?.classList.add("hidden");
  if (p2PrepPanel) p2PrepPanel.innerHTML = "";
  if (state.view !== "p2") state.p2Corpus.selectedEntryId = "";
  $("#cueTop")?.classList.add("hidden");
  $("#promptPane")?.classList.remove("hidden");
  $("#p3TopicPanel")?.classList.toggle("hidden", !isPracticeMode || state.view !== "p3");
  $("#practiceGrid")?.classList.remove("p2-mode", "practice-enter");
  $("#practiceGrid")?.classList.toggle("hidden", !isPracticeMode || state.view === "p3");
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
  $("#examStatusText")?.classList.toggle("hidden", state.view === "p2");
}

function startPracticeMode(mode) {
  if (!["mock", "p1", "p2", "p3"].includes(mode)) return;
  switchView(mode, { force: true });
  window.requestAnimationFrame(() => {
    if (mode === "p3") return;
    startPractice();
  });
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
  if (state.status === "loading" || state.practiceLocked) return;
  stopExaminerPlayback();
  const requestId = state.startRequestId + 1;
  state.startRequestId = requestId;
  const sessionId = state.practiceSessionId + 1;
  state.practiceSessionId = sessionId;
  state.startAbortController?.abort();
  state.startAbortController = new AbortController();
  if (!state.account.authenticated) {
    state.account.returnView = state.view;
    switchView("login", {
      force: true,
      skipAuthGate: true,
      authMessage: "登录后才能开始练习并保存完整报告。",
    });
    return;
  }
  const mode = state.view === "mock" ? "mock" : state.view;
  state.abortingAttemptId = null;
  state.practiceLocked = true;
  $(".exam-status")?.classList.remove("hidden");
  $("#examStatusText")?.classList.toggle("hidden", mode === "p2");
  $("#practiceGrid")?.classList.remove("hidden");
  $("#exitPractice").classList.remove("hidden");
  updateSidebarLock();
  setRecordButton("loading", "Loading...", "Checking account balance.");
  // Check balance before starting
  try {
    const wallet = await api("/api/billing/wallet", null, { signal: state.startAbortController.signal });
    if (state.startRequestId !== requestId || state.practiceSessionId !== sessionId) return;
    const balance = Number(wallet.balance_rmb || 0);
    if (balance <= 0) {
      state.practiceLocked = false;
      $("#exitPractice")?.classList.add("hidden");
      updateSidebarLock();
      alert("余额不足，请先充值后再开始练习。");
      switchView("accountProfile");
      return;
    }
  } catch (e) {
    if (e?.name === "AbortError" || state.startRequestId !== requestId || state.practiceSessionId !== sessionId || state.abortingAttemptId === "__loading__") return;
    // If wallet check fails, continue anyway
  }

  if (state.startRequestId !== requestId || state.practiceSessionId !== sessionId || state.abortingAttemptId === "__loading__") return;
  $(".exam-status")?.classList.remove("hidden");
  $("#examStatusText")?.classList.toggle("hidden", mode === "p2");
  $("#practiceGrid")?.classList.remove("hidden");
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
    }, { signal: state.startAbortController.signal });
    if (state.startRequestId !== requestId || state.practiceSessionId !== sessionId || state.abortingAttemptId === "__loading__") {
      if (attempt?.id) api(`/api/attempts/${attempt.id}/abort`, {}).catch(() => null);
      return;
    }
    state.attempt = attempt;
    state.currentTurn = attempt.turns[0];
    $("#summaryPanel").classList.add("hidden");
    renderTurn(state.currentTurn);
    beginExaminerPhase(sessionId);
  } catch (error) {
    if (error?.name === "AbortError" || state.startRequestId !== requestId || state.practiceSessionId !== sessionId) return;
    state.practiceLocked = false;
    $("#exitPractice")?.classList.add("hidden");
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
    renderP2CorpusPrepPanel();
    return;
  }
  $("p2CorpusPrepPanel")?.classList.add("hidden");
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

async function renderP2CorpusPrepPanel(renderOptions = {}) {
  const panel = $("p2CorpusPrepPanel");
  const shouldShow = state.currentTurn?.part === "p2";
  if (!panel || !shouldShow) {
    panel?.classList.add("hidden");
    if (panel) panel.innerHTML = "";
    return;
  }
  if (!(state.p2Corpus.categories || []).length) {
    try {
      const payload = await api("/api/p2-corpus");
      state.p2Corpus.categories = payload.categories || [];
    } catch (_error) {
      state.p2Corpus.categories = [];
    }
  }
  const options = [];
  for (const category of state.p2Corpus.categories || []) {
    for (const item of category.items || []) {
      options.push({ ...item, label: category.label || item.label || item.category });
    }
  }
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div>
      <strong>本次 P2 回答链接到哪里</strong>
      <span>选择一个素材，AI 生成 7 分回答和辅导时会参考。</span>
    </div>
    <select id="p2CorpusPrepSelect">
      <option value="">不链接素材</option>
      ${options.map((item) => `<option value="${escapeHtml(item.entry_id)}"${item.entry_id === state.p2Corpus.selectedEntryId ? " selected" : ""}>${escapeHtml(item.label)} •「${escapeHtml(item.title)}」</option>`).join("")}
    </select>
  `;
  $("p2CorpusPrepSelect")?.addEventListener("change", (event) => {
    state.p2Corpus.selectedEntryId = event.target.value || "";
  });
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
  for (const [url, audio] of state.examinerAudioPreloads.entries()) {
    audio.pause();
    audio.onended = null;
    audio.onerror = null;
    try {
      audio.currentTime = 0;
    } catch {
      // Some browsers reject seeking before metadata is loaded.
    }
    if (FIXED_EXAMINER_AUDIO_URLS.has(url)) continue;
    audio.removeAttribute("src");
    state.examinerAudioPreloads.delete(url);
  }
}

function stopExaminerPlayback() {
  const activeAudio = state.activeExaminerAudio;
  if (activeAudio) {
    activeAudio.pause();
    activeAudio.onended = null;
    activeAudio.onerror = null;
    try {
      activeAudio.currentTime = 0;
    } catch {
      // Ignore seek errors for partially loaded audio.
    }
  }
  state.activeExaminerAudio = null;
  const examinerAudio = $("examinerAudio");
  if (examinerAudio) {
    examinerAudio.pause();
    examinerAudio.onended = null;
    examinerAudio.onerror = null;
    examinerAudio.removeAttribute("src");
    examinerAudio.removeAttribute("data-src");
    try {
      examinerAudio.currentTime = 0;
    } catch {
      // Ignore seek errors for unloaded audio.
    }
  }
  for (const audio of state.examinerAudioPreloads.values()) {
    audio.pause();
    audio.onended = null;
    audio.onerror = null;
    try {
      audio.currentTime = 0;
    } catch {
      // Ignore seek errors for unloaded audio.
    }
  }
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  state.browserTtsUtterance = null;
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

function isActivePracticeSession(sessionId) {
  return !!sessionId && state.practiceSessionId === sessionId && state.practiceLocked;
}

async function beginExaminerPhase(sessionId = state.practiceSessionId) {
  if (!isActivePracticeSession(sessionId)) return;
  if (!state.currentTurn) return;
  clearTimer();
  stopExaminerPlayback();
  if (!isActivePracticeSession(sessionId)) return;
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
      state.activeExaminerAudio = preloaded;
      preloaded.onended = () => {
        if (state.activeExaminerAudio === preloaded) state.activeExaminerAudio = null;
        if (isActivePracticeSession(sessionId)) beginPreparation(sessionId);
      };
      preloaded.onerror = () => {
        if (state.activeExaminerAudio === preloaded) state.activeExaminerAudio = null;
        if (isActivePracticeSession(sessionId)) beginBrowserExaminerPlayback(turn.examiner_text || turn.question, sessionId);
      };
      preloaded.currentTime = 0;
      preloaded.play().catch(() => isActivePracticeSession(sessionId) && beginBrowserExaminerPlayback(turn.examiner_text || turn.question, sessionId));
    } else {
      const audio = $("examinerAudio");
      state.activeExaminerAudio = audio;
      audio.onended = () => {
        if (state.activeExaminerAudio === audio) state.activeExaminerAudio = null;
        if (isActivePracticeSession(sessionId)) beginPreparation(sessionId);
      };
      audio.onerror = () => {
        if (state.activeExaminerAudio === audio) state.activeExaminerAudio = null;
        if (isActivePracticeSession(sessionId)) beginBrowserExaminerPlayback(turn.examiner_text || turn.question, sessionId);
      };
      prepareExaminerAudioElement(audio, tts.audio_url);
      await waitForAudioReady(audio);
      if (!isActivePracticeSession(sessionId) || state.currentTurn?.id !== turnId || state.status !== "examiner_playing") return;
      audio.currentTime = 0;
      audio.play().catch(() => isActivePracticeSession(sessionId) && beginBrowserExaminerPlayback(turn.examiner_text || turn.question, sessionId));
    }
    return;
  }
  beginBrowserExaminerPlayback(turn.examiner_text || turn.question, sessionId);
}

function beginBrowserExaminerPlayback(value, sessionId = state.practiceSessionId) {
  if (!isActivePracticeSession(sessionId)) return;
  if (!value || !window.speechSynthesis) {
    beginPreparation(sessionId);
    return;
  }
  stopExaminerPlayback();
  if (!isActivePracticeSession(sessionId)) return;
  const utterance = new SpeechSynthesisUtterance(value);
  state.browserTtsUtterance = utterance;
  utterance.lang = "en-US";
  utterance.rate = 0.92;
  utterance.onend = () => {
    if (state.browserTtsUtterance === utterance && isActivePracticeSession(sessionId)) beginPreparation(sessionId);
  };
  utterance.onerror = () => {
    if (state.browserTtsUtterance === utterance && isActivePracticeSession(sessionId)) beginPreparation(sessionId);
  };
  window.speechSynthesis.speak(utterance);
}

function beginPreparation(sessionId = state.practiceSessionId) {
  if (!isActivePracticeSession(sessionId)) return;
  const seconds = state.currentTurn?.timers?.prep_seconds || 3;
  const isP2 = state.currentTurn?.part === "p2";
  preloadNextExaminerAudio(state.currentTurn);
  setRecordButton("preparing", isP2 ? "Skip" : "Prepare", isP2 ? "Click to start recording now." : "Recording starts automatically.");
  text("phaseLabel", `Preparing -> ${turnProgressLabel(state.currentTurn)}`);
  text("recordStatus", isP2 ? "Prepare your answer. Click to start recording early." : `Prepare your answer. Recording starts in ${seconds} seconds.`);
  startCountdown(seconds, "Preparing", () => startRecording(sessionId).catch(showError), sessionId);
}

function startCountdown(seconds, label, onDone, sessionId = state.practiceSessionId) {
  clearTimer();
  state.timerRemaining = Number(seconds || 0);
  state.timerTotal = Math.max(1, state.timerRemaining);
  updateTimer(label);
  state.timer = setInterval(() => {
    if (!isActivePracticeSession(sessionId)) {
      clearTimer();
      return;
    }
    state.timerRemaining -= 1;
    updateTimer(label);
    if (state.timerRemaining <= 0) {
      clearTimer();
      onDone();
    }
  }, 1000);
}

function startRecordingTimer(seconds, sessionId = state.practiceSessionId) {
  clearTimer();
  state.timerRemaining = Number(seconds || 0);
  state.timerTotal = Math.max(1, state.timerRemaining);
  updateTimer("Recording");
  state.timer = setInterval(() => {
    if (!isActivePracticeSession(sessionId)) {
      clearTimer();
      return;
    }
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

async function startRecording(sessionId = state.practiceSessionId) {
  if (!isActivePracticeSession(sessionId)) return;
  if (!state.currentTurn) return;
  state.status = "recording";
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  if (!isActivePracticeSession(sessionId)) {
    stream.getTracks().forEach((track) => track.stop());
    return;
  }
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
  startRecordingTimer(state.currentTurn.timers.speak_seconds, sessionId);
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
    const token = await ensureCsrfToken();
    const uploadHeaders = { "Content-Type": mimeType.split(";")[0] };
    if (token) uploadHeaders["X-CSRFToken"] = token;
    const upload = await fetch(`/api/attempts/${attempt.id}/turns/${turn.id}/audio`, {
      method: "POST",
      credentials: "same-origin",
      headers: uploadHeaders,
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
      ...(turn.part === "p2" && state.p2Corpus.selectedEntryId ? { p2_corpus_link: { entry_id: state.p2Corpus.selectedEntryId } } : {}),
    });
    if (state.abortingAttemptId === attempt.id || state.attempt?.id !== attempt.id) return;
    state.attempt = completePayload.attempt;
    if (completePayload.next_turn) {
      const sessionId = state.practiceSessionId;
      state.currentTurn = completePayload.next_turn;
      renderTurn(completePayload.next_turn);
      setRecordButton("turn_saved", "Next", "Moving to the next question.");
      text("recordStatus", "Question saved. The next examiner prompt will start automatically.");
      clearAutoNextTimeout();
      state.autoNextTimeout = window.setTimeout(() => beginExaminerPhase(sessionId), 650);
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
  const selector = $("p2CorpusPrepSelect");
  if (selector) selector.disabled = true;
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
    if (state.historyItems.length) renderHistoryList(state.historyItems, { refreshActive: false });
    const payload = await api("/api/history");
    state.historyItems = payload.items || [];
    renderHistoryList(state.historyItems);
  };
  if (showBusy && !state.historyItems.length) return withBusy("Loading history...", action).catch(showError);
  return action().catch(showError);
}

function renderHistoryList(items, options = {}) {
  const refreshActive = options.refreshActive !== false;
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
        <small class="history-item-time">${escapeHtml(formatReportTime(item.display_time || item.timestamp || ""))}</small>
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
      const cached = state.historyDetailCache.get(button.dataset.attemptId);
      if (cached) renderDetail(cached, false);
      api(`/api/history/${button.dataset.attemptId}`)
        .then((detail) => {
          state.historyDetailCache.set(button.dataset.attemptId, detail);
          if (state.activeHistoryId === button.dataset.attemptId) renderDetail(detail, false, { preserveScroll: Boolean(cached) });
        })
        .catch(showError);
    });
  });
  document.querySelectorAll(".history-item-menu-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      showHistoryItemMenu(btn, btn.dataset.attemptId);
    });
  });
  if (state.activeHistoryId && !items.some((item) => item.id === state.activeHistoryId)) {
    state.activeHistoryId = null;
  }
  if (!state.activeHistoryId && items.length) {
    state.activeHistoryId = items[0].id;
    document.querySelector(".history-item")?.classList.add("active");
  }
  if (refreshActive && state.activeHistoryId) {
    const cached = state.historyDetailCache.get(state.activeHistoryId);
    if (cached) renderDetail(cached, false, { preserveScroll: true });
    api(`/api/history/${state.activeHistoryId}`)
      .then((detail) => {
        state.historyDetailCache.set(state.activeHistoryId, detail);
        if (state.activeHistoryId === detail.id) renderDetail(detail, false, { preserveScroll: Boolean(cached) });
      })
      .catch(showError);
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
      await api(`/api/history/${attemptId}`, null, { method: "DELETE" });
      if (state.activeHistoryId === attemptId) state.activeHistoryId = null;
      state.historyDetailCache.delete(attemptId);
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

function autoResizeWritingAnswer() {
  const answer = $("writingAnswer");
  if (!answer) return;
  answer.style.height = "auto";
  const targetHeight = Math.min(Math.max(answer.scrollHeight, 500), 800);
  answer.style.height = `${targetHeight}px`;
}

function updateWritingWordCount() {
  const count = currentWritingWordCount();
  text("writingWordCount", `${count} word${count === 1 ? "" : "s"}`);
  autoResizeWritingAnswer();
}

function setWritingPending(isPending, title = "", detail = "") {
  const wait = $("writingInlineWait");
  wait?.classList.toggle("hidden", !isPending);
  if (title) text("writingInlineWaitTitle", title);
  if (detail) text("writingInlineWaitText", detail);
  ["writingSaveBtn", "writingScoreBtn", "writingRandomBtn", "writingPromptPickerBtn", "writingAnswer"].forEach((id) => {
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

function writingCategoryLabel(category = "") {
  const labels = {
    line_graph: "\u6298\u7ebf\u56fe",
    bar_chart: "\u67f1\u72b6\u56fe",
    pie_chart: "\u997c\u56fe",
    table: "\u8868\u683c",
    map: "\u5730\u56fe",
    process: "\u6d41\u7a0b\u56fe",
    mixed: "\u6df7\u5408\u56fe",
    opinion: "\u89c2\u70b9\u7c7b",
    discussion: "\u8ba8\u8bba\u7c7b",
    problem_solution: "\u95ee\u9898\u89e3\u51b3\u7c7b",
    advantages_disadvantages: "\u5229\u5f0a\u7c7b",
    two_part: "\u53cc\u95ee\u9898\u7c7b",
  };
  const key = String(category || "").trim();
  return labels[key] || key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) || "Writing";
}

function writingPromptDisplayTitle(prompt) {
  const sourceLabel = String(prompt?.source_label || prompt?.display_source_label || "").trim();
  const title = String(prompt?.title || writingTaskLabel(prompt?.task_type)).trim();
  return sourceLabel || title;
}

function writingPromptMeta(prompt) {
  if (!prompt) return writingTaskLabel(state.writing.taskType || "task1_academic");
  const sourceLabel = String(prompt.source_label || prompt.display_source_label || "").trim();
  const parts = sourceLabel
    ? [prompt.title || "", writingTaskLabel(prompt.task_type), writingCategoryLabel(prompt.category)]
    : [writingTaskLabel(prompt.task_type), writingCategoryLabel(prompt.category)];
  return parts.filter(Boolean).join(" \u00b7 ");
}

function attachWritingDisplayLabels(taskType, prompts = [], catalog = []) {
  return prompts.map((prompt, index) => {
    if (prompt.source_label || prompt.display_source_label) return prompt;
    const slot = catalog[index];
    if (!slot?.source_label) return prompt;
    return { ...prompt, display_source_label: slot.source_label, display_catalog_id: slot.id || "" };
  });
}

function writingCatalogMissingSlots(taskType, selectedCategory = "") {
  if (selectedCategory) return [];
  const promptCount = (state.writing.prompts[taskType] || []).length;
  const assignedCatalogIds = new Set((state.writing.prompts[taskType] || []).map((prompt) => prompt.display_catalog_id).filter(Boolean));
  const availableIds = new Set((state.writing.prompts[taskType] || []).map((prompt) => prompt.id));
  return (state.writing.promptCatalog[taskType] || [])
    .filter((slot) => slot?.id && !availableIds.has(slot.id))
    .filter((slot, index) => index >= promptCount && !assignedCatalogIds.has(slot.id));
}

async function loadWriting() {
  try {
    const [, summary] = await Promise.all([loadWritingPrompts(state.writing.taskType), loadWritingSummary(false)]);
    if (!state.writing.entry && summary?.today_entry?.ai_task && isWritingTaskActive(summary.today_entry.ai_task)) {
      await recoverWritingEntry(summary.today_entry);
      startWritingScorePolling(summary.today_entry.id, { switchOnComplete: false });
    }
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
  if (state.writing.prompts[normalized]?.length) {
    if (!state.writing.promptCategories[normalized]?.length) {
      state.writing.promptCategories[normalized] = inferWritingCategories(state.writing.prompts[normalized]);
    }
    return state.writing.prompts[normalized];
  }
  const payload = await api(`/api/writing/prompts?task_type=${encodeURIComponent(normalized)}`);
  state.writing.promptCatalog[normalized] = payload.catalog || [];
  state.writing.prompts[normalized] = attachWritingDisplayLabels(normalized, payload.items || [], state.writing.promptCatalog[normalized]);
  state.writing.promptCategories[normalized] = payload.categories || inferWritingCategories(state.writing.prompts[normalized]);
  return state.writing.prompts[normalized];
}

function inferWritingCategories(prompts = []) {
  const counts = new Map();
  for (const prompt of prompts) {
    const category = String(prompt.category || "").trim();
    if (!category) continue;
    counts.set(category, (counts.get(category) || 0) + 1);
  }
  return Array.from(counts.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([category, count]) => ({ category, label: writingCategoryLabel(category), count }));
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
    if (state.writing.reportEntries.length) renderWritingReports(state.writing.reportEntries, { refreshActive: false });
    const loader = () => api("/api/writing/reports");
    const payload = state.writing.reportEntries.length
      ? await loader()
      : await withBusy("Loading writing reports...", loader);
    await renderWritingReports(payload.items || []);
  } catch (error) {
    showWritingReportError(error);
  }
}

async function renderWritingReports(items, options = {}) {
  const refreshActive = options.refreshActive !== false;
  const target = $("writingReportDetail");
  if (!target) return;
  if (!items.length) {
    state.writing.reportEntries = [];
    const list = $("writingReportList");
    if (list) list.textContent = "还没有写作记录。";
    target.innerHTML = '<h2>写作报告</h2><p class="muted">还没有写作记录。保存一篇作文后会出现在这里。</p>';
    return;
  }
  // Store compact items from /api/writing/reports
  state.writing.reportEntries = items;
  // Determine active report id
  const activeId = items.some((item) => item.id === state.writing.activeReportId) ? state.writing.activeReportId : items[0].id;
  state.writing.activeReportId = activeId;
  // Render list from compact items
  renderWritingReportList(items);
  // Fetch detail only for the selected item
  const activeItem = items.find((item) => item.id === activeId) || items[0];
  const cached = state.writing.reportDetailCache.get(activeItem.id);
  if (cached) {
    state.writing.activeReportDetail = cached;
    target.innerHTML = writingReportDetailHtml(cached);
  } else {
    state.writing.activeReportDetail = null;
    target.innerHTML = '<div class="detail-card"><p class="muted">正在加载报告详情...</p></div>';
  }
  if (!refreshActive) return;
  try {
    const entry = await api(`/api/writing/entries/${activeItem.id}`);
    state.writing.reportDetailCache.set(activeItem.id, entry);
    state.writing.activeReportDetail = entry;
    target.innerHTML = writingReportDetailHtml(entry);
    if (isWritingTaskActive(entry?.ai_task)) startWritingScorePolling(entry.id, { switchOnComplete: false });
  } catch (error) {
    target.innerHTML = `<div class="detail-card"><p class="error">${escapeHtml(error.message || "Failed to load report detail.")}</p></div>`;
  }
}

function renderWritingReportList(items) {
  const list = $("writingReportList");
  if (!list) return;
  list.innerHTML = items.map((item) => writingReportTabHtml(item, item.id === state.writing.activeReportId)).join("");
  list.querySelectorAll("[data-writing-report-tab]").forEach((button) => {
    button.addEventListener("click", async () => {
      const itemId = button.dataset.writingReportTab;
      if (!itemId) return;
      state.writing.activeReportId = itemId;
      renderWritingReportList(state.writing.reportEntries);
      const target = $("writingReportDetail");
      if (!target) return;
      const cached = state.writing.reportDetailCache.get(itemId);
      if (cached) {
        state.writing.activeReportDetail = cached;
        target.innerHTML = writingReportDetailHtml(cached);
        target.scrollTo({ top: 0, behavior: "auto" });
      } else {
        state.writing.activeReportDetail = null;
        target.innerHTML = '<div class="detail-card"><p class="muted">正在加载报告详情...</p></div>';
      }
      // Fetch detail for the selected report
      try {
        const entry = await api(`/api/writing/entries/${itemId}`);
        state.writing.reportDetailCache.set(itemId, entry);
        state.writing.activeReportDetail = entry;
        target.innerHTML = writingReportDetailHtml(entry);
        target.scrollTo({ top: 0, behavior: cached ? "auto" : "smooth" });
        if (isWritingTaskActive(entry.ai_task)) startWritingScorePolling(entry.id, { switchOnComplete: false });
        else clearWritingScorePolling();
      } catch (error) {
        target.innerHTML = `<div class="detail-card"><p class="error">${escapeHtml(error.message || "Failed to load report detail.")}</p></div>`;
      }
    });
  });
}

function writingReportTabHtml(item, active = false) {
  const task = item?.ai_task || null;
  const part = item.task_type === "task1_academic" ? "T1" : "T2";
  const band = item.overall_band != null ? `Band ${item.overall_band}` : (isWritingTaskActive(task) ? "评分中" : "未评分");
  const toneClass = item.task_type === "task1_academic" ? "tone-p1" : "tone-p2";
  const tagClass = item.task_type === "task1_academic" ? "p1" : "p2";
  return `
    <button class="history-item writing-report-tab ${toneClass} ${active ? "active" : ""}" data-writing-report-tab="${escapeHtml(item.id || "")}">
      <div class="history-item-top">
        <span class="history-item-tag ${tagClass}">${part}</span>
        <span class="history-item-band">${escapeHtml(band)}</span>
      </div>
      <strong class="history-item-title">${escapeHtml(item.title || writingTaskLabel(item.task_type))}</strong>
      <small class="history-item-time">${escapeHtml(item.display_time || item.practice_date || "")} · ${escapeHtml(item.word_count ?? 0)} words</small>
    </button>
  `;
}

function writingReportDetailHtml(entry) {
  const score = entry?.score || null;
  const task = entry?.ai_task || null;
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
  const taskBlock = !score && task ? `
    <div class="detail-card writing-task-state-card">
      <div class="detail-header">
        <div>
          <h2>${escapeHtml(writingTaskStatusTitle(task))}</h2>
          <p class="muted">${escapeHtml(writingTaskStatusText(task))}</p>
        </div>
        <strong class="overall-badge muted-badge">${escapeHtml(task.status || "pending")}</strong>
      </div>
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
    ${taskBlock}
    ${scoreBlock}
    <div class="detail-card writing-report-prompt">
      <h3>题目</h3>
      ${entry.image_url ? `<div class="writing-report-image"><img src="${escapeHtml(entry.image_url)}" alt="Task 1 chart"></div>` : ""}
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
  const prompt = state.writing.prompt;
  text("writingPromptType", writingTaskLabel(taskType));
  text("writingPromptTitle", prompt ? writingPromptDisplayTitle(prompt) : "\u9009\u62e9\u4e00\u9053\u9898\u5f00\u59cb");
  text("writingPromptPickerTitle", prompt ? writingPromptDisplayTitle(prompt) : "\u9009\u62e9\u5199\u4f5c\u9898\u76ee");
  text("writingPromptPickerMeta", prompt ? writingPromptMeta(prompt) : writingTaskLabel(taskType));
  $("writingPromptText").innerHTML = renderMarkdown(prompt?.prompt || "\u8bf7\u9009\u62e9\u4e00\u9053\u9898\uff0c\u6216\u70b9\u51fb\u968f\u673a\u9898\u5f00\u59cb\u3002");

  // Render Task 1 image if available
  const imageContainer = $("writingPromptImage");
  if (imageContainer) {
    if (taskType === "task1_academic" && prompt?.image_url) {
      imageContainer.innerHTML = `<img src="${escapeHtml(prompt.image_url)}" alt="Task 1 chart" onerror="this.parentElement.classList.add('hidden')">`;
      imageContainer.classList.remove("hidden");
    } else {
      imageContainer.innerHTML = "";
      imageContainer.classList.add("hidden");
    }
  }

  const entry = state.writing.entry;
  renderWritingScore(entry);
  updateWritingWordCount();
  if (entry?.ai_task && isWritingTaskActive(entry.ai_task)) {
    text("writingSaveStatus", writingTaskStatusTitle(entry.ai_task));
  } else if (!entry?.id) {
    text("writingSaveStatus", "\u672a\u4fdd\u5b58");
  } else if (entry.status === "scored") {
    text("writingSaveStatus", `\u5df2\u8bc4\u5206 \u00b7 ${entry.practice_date || ""} \u00b7 \u53ef\u5728\u5199\u4f5c\u62a5\u544a\u67e5\u770b`);
  } else {
    text("writingSaveStatus", `\u5df2\u4fdd\u5b58 \u00b7 ${entry.practice_date || ""}`);
  }
}

function renderWritingScore(entry) {
  const score = entry?.score || null;
  if (!score) {
    return;
  }
  text("writingSaveStatus", `\u5df2\u8bc4\u5206 \u00b7 Band ${score.overall_band ?? "\u2014"} \u00b7 \u53ef\u5728\u5199\u4f5c\u62a5\u544a\u67e5\u770b`);
}

function openWritingPromptPicker(taskType = state.writing.taskType || "task1_academic") {
  state.writing.pickerTaskType = taskType;
  $("writingPromptModal")?.classList.remove("hidden");
  document.body.classList.add("modal-open");
  loadWritingPrompts(taskType)
    .then(() => renderWritingPromptPicker())
    .catch(showWritingError);
}

function closeWritingPromptPicker() {
  $("writingPromptModal")?.classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function writingPromptChoiceHtml(prompt, active = false) {
  const isTask1 = prompt.task_type === "task1_academic";
  return `
    <button type="button" class="writing-prompt-choice ${active ? "active" : ""}" data-writing-prompt-choice="${escapeHtml(prompt.id)}">
      ${isTask1 && prompt.image_url ? `<span class="writing-prompt-choice-image"><img src="${escapeHtml(prompt.image_url)}" alt=""></span>` : ""}
      <span class="writing-prompt-choice-body">
        <strong>${escapeHtml(writingPromptDisplayTitle(prompt))}</strong>
        <small>${escapeHtml(writingPromptMeta(prompt))}</small>
        <span>${escapeHtml(String(prompt.prompt || "").split(/\n+/)[0] || "")}</span>
      </span>
    </button>
  `;
}

function writingCatalogSlotHtml(slot) {
  const isTask1 = slot.task_type === "task1_academic";
  const statusText = isTask1 ? "\u5f85\u5bfc\u5165\u6388\u6743\u9898\u5e72/\u914d\u56fe" : "\u5f85\u5bfc\u5165\u6388\u6743\u9898\u5e72";
  return `
    <button type="button" class="writing-prompt-choice missing" disabled aria-disabled="true">
      ${isTask1 ? `<span class="writing-prompt-choice-image placeholder">Task 1 chart</span>` : ""}
      <span class="writing-prompt-choice-body">
        <strong>${escapeHtml(slot.source_label || slot.id || "Cambridge IELTS")}</strong>
        <small>${escapeHtml(statusText)}</small>
        <span>${escapeHtml(isTask1 && slot.expected_image_url ? slot.expected_image_url : "Add an authorized prompt JSON file with this id to enable the slot.")}</span>
      </span>
    </button>
  `;
}

function renderWritingPromptPicker() {
  const taskType = state.writing.pickerTaskType || state.writing.taskType || "task1_academic";
  document.querySelectorAll("[data-writing-picker-task]").forEach((button) => {
    button.classList.toggle("active", button.dataset.writingPickerTask === taskType);
  });
  text("writingPromptModalHint", taskType === "task1_academic"
    ? "Task 1 \u6709\u56fe\u8868\uff1b\u5251\u96c5\u76ee\u5f55\u6309 20 \u5230 1 \u6392\u5217\uff0c\u5f85\u5bfc\u5165\u7684\u539f\u9898\u4f1a\u7070\u663e\u3002"
    : "Task 2 \u53ef\u6309\u9898\u578b\u7b5b\u9009\uff1b\u5251\u96c5\u76ee\u5f55\u6309 20 \u5230 1 \u6392\u5217\uff0c\u5f85\u5bfc\u5165\u7684\u539f\u9898\u4f1a\u7070\u663e\u3002");
  renderWritingPromptTypeFilters(taskType);
  const selectedCategory = state.writing.pickerCategoryFilters[taskType] || "";
  const prompts = (state.writing.prompts[taskType] || []).filter((prompt) => !selectedCategory || prompt.category === selectedCategory);
  const missingSlots = writingCatalogMissingSlots(taskType, selectedCategory);
  const grid = $("writingPromptGrid");
  if (!grid) return;
  if (!prompts.length && !missingSlots.length) {
    grid.innerHTML = '<p class="muted">\u5f53\u524d\u7b5b\u9009\u4e0b\u6ca1\u6709\u53ef\u7528\u9898\u76ee\u3002</p>';
    return;
  }
  grid.innerHTML = [
    ...prompts.map((prompt) => writingPromptChoiceHtml(prompt, prompt.id === state.writing.prompt?.id)),
    ...missingSlots.map((slot) => writingCatalogSlotHtml(slot)),
  ].join("");
  grid.querySelectorAll("[data-writing-prompt-choice]").forEach((button) => {
    button.addEventListener("click", () => {
      if (state.writing.dirty && !window.confirm("\u5f53\u524d\u4f5c\u6587\u8fd8\u6ca1\u6709\u4fdd\u5b58\uff0c\u786e\u5b9a\u8981\u6362\u9898\u5417\uff1f")) return;
      const prompt = prompts.find((item) => item.id === button.dataset.writingPromptChoice);
      if (!prompt) return;
      state.writing.taskType = prompt.task_type || taskType;
      setWritingPrompt(prompt, true);
      closeWritingPromptPicker();
    });
  });
}

function renderWritingPromptTypeFilters(taskType) {
  const target = $("writingPromptTypeFilters");
  if (!target) return;
  const categories = state.writing.promptCategories[taskType]?.length
    ? state.writing.promptCategories[taskType]
    : inferWritingCategories(state.writing.prompts[taskType] || []);
  const selected = state.writing.pickerCategoryFilters[taskType] || "";
  target.innerHTML = [
    `<button type="button" class="writing-type-filter ${selected ? "" : "active"}" data-writing-prompt-category="">\u5168\u90e8</button>`,
    ...categories.map((item) => `
      <button type="button" class="writing-type-filter ${selected === item.category ? "active" : ""}" data-writing-prompt-category="${escapeHtml(item.category)}">
        ${escapeHtml(writingCategoryLabel(item.category) || item.label)}
        <span>${escapeHtml(item.count ?? "")}</span>
      </button>
    `),
  ].join("");
  target.querySelectorAll("[data-writing-prompt-category]").forEach((button) => {
    button.addEventListener("click", () => {
      state.writing.pickerCategoryFilters[taskType] = button.dataset.writingPromptCategory || "";
      renderWritingPromptPicker();
    });
  });
}

async function chooseRandomWritingPrompt(confirmDirty = true) {
  if (confirmDirty && state.writing.dirty && !window.confirm("当前作文还没有保存，确定要换题吗？")) return;
  const taskType = state.writing.taskType || "task1_academic";
  const prompt = await api("/api/writing/prompts/random", {
    task_type: taskType,
    category: state.writing.pickerCategoryFilters[taskType] || "",
  });
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
    image_url: prompt.image_url || "",
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

function isWritingTaskActive(task) {
  return Boolean(task && ["pending", "running"].includes(String(task.status || "")));
}

function isWritingTaskTerminal(task) {
  return Boolean(task && ["succeeded", "fallback", "failed", "cancelled"].includes(String(task.status || "")));
}

function writingTaskStatusTitle(task) {
  const status = String(task?.status || "pending");
  if (status === "running") return "AI 正在评分与生成辅导";
  if (status === "pending") return "AI 评分已排队";
  if (status === "fallback") return "AI 评分使用了系统默认建议";
  if (status === "succeeded") return "AI 评分已完成";
  if (status === "cancelled") return "AI 评分已取消";
  if (status === "failed") return "AI 评分失败";
  return "AI 评分状态更新中";
}

function writingTaskStatusText(task) {
  const status = String(task?.status || "pending");
  if (status === "running") return "任务已经开始，刷新或切换页面不会丢失结果；完成后会写入写作报告。";
  if (status === "pending") return "任务正在等待后台 worker 处理。刷新页面后仍可从写作记录中恢复。";
  if (status === "cancelled") return "这次评分尚未开始时被取消，作文仍然已保存并计入签到。";
  if (status === "failed") return task?.error_message || "这次评分没有生成可用结果，可以稍后重新评分。";
  return "结果已写入这篇作文的记录。";
}

function clearWritingScorePolling() {
  if (state.writing.scorePollTimer) {
    clearTimeout(state.writing.scorePollTimer);
    state.writing.scorePollTimer = null;
  }
  state.writing.scorePollingEntryId = null;
}

function isScoreTaskUnsupported(error) {
  const message = String(error?.message || "");
  return error?.status === 404 && /Unknown API endpoint/i.test(message);
}

function renderVisibleWritingReport(entry) {
  if (state.view !== "writingReports" || state.writing.activeReportId !== entry?.id) return;
  // Update active report detail
  state.writing.activeReportDetail = entry;
  // Merge status/overall_band/ai_task into the corresponding compact item
  const reportEntries = Array.isArray(state.writing.reportEntries) ? [...state.writing.reportEntries] : [];
  const reportIndex = reportEntries.findIndex((item) => item.id === entry.id);
  if (reportIndex >= 0) {
    const existing = reportEntries[reportIndex] || {};
    reportEntries[reportIndex] = {
      ...existing,
      status: entry.status ?? existing.status,
      overall_band: entry.score?.overall_band ?? entry.overall_band ?? existing.overall_band,
      ai_task: entry.ai_task ?? existing.ai_task,
    };
    state.writing.reportEntries = reportEntries;
    renderWritingReportList(reportEntries);
  }
  const target = $("writingReportDetail");
  if (target) target.innerHTML = writingReportDetailHtml(entry);
}

async function recoverWritingEntry(entry) {
  state.writing.entry = entry;
  state.writing.taskType = entry.task_type || state.writing.taskType || "task2";
  await loadWritingPrompts(state.writing.taskType);
  state.writing.prompt = {
    id: entry.prompt_id,
    task_type: entry.task_type,
    task_label: entry.task_label,
    title: entry.title,
    prompt: entry.prompt,
    category: entry.category,
    image_url: entry.image_url || "",
  };
  if ($("writingAnswer")) $("writingAnswer").value = entry.answer || "";
  state.writing.dirty = false;
  renderWritingSurface();
}

function startWritingScorePolling(entryId, options = {}) {
  if (!entryId) return;
  clearWritingScorePolling();
  const switchOnComplete = options.switchOnComplete !== false;
  state.writing.scorePollingEntryId = entryId;
  const poll = async () => {
    try {
      const entry = await api(`/api/writing/entries/${entryId}`);
      if (state.writing.scorePollingEntryId !== entryId) return;
      await recoverWritingEntry(entry);
      renderVisibleWritingReport(entry);
      await loadWritingSummary();
      const task = entry.ai_task || null;
      if (entry.score || (task && ["fallback", "succeeded"].includes(String(task.status || "")))) {
        clearWritingScorePolling();
        setWritingPending(false);
        state.writing.activeReportId = entry.id;
        if (switchOnComplete) switchView("writingReports");
        return;
      }
      if (task && isWritingTaskTerminal(task)) {
        clearWritingScorePolling();
        setWritingPending(false);
        text("writingSaveStatus", writingTaskStatusTitle(task));
        return;
      }
      setWritingPending(true, writingTaskStatusTitle(task), writingTaskStatusText(task));
      state.writing.scorePollTimer = setTimeout(poll, 2500);
    } catch (error) {
      clearWritingScorePolling();
      setWritingPending(false);
      showWritingError(error);
    }
  };
  poll();
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
        switchView("accountProfile");
        return;
      }
    } catch (_error) {
      // Backend scoring still handles billing/fallback; keep the writing flow usable.
    }
    try {
      const result = await withBusy("AI 评分任务已提交...", () => api(`/api/writing/entries/${entry.id}/score-task`, {}));
      const savedEntry = result.entry || entry;
      state.writing.entry = savedEntry;
      state.writing.activeReportId = savedEntry.id;
      state.writing.dirty = false;
      renderWritingSurface();
      await loadWritingSummary();
      startWritingScorePolling(savedEntry.id, { switchOnComplete: true });
      return;
    } catch (error) {
      if (!isScoreTaskUnsupported(error)) throw error;
    }
    const scored = await withBusy("AI 正在评分与生成辅导...", () => api(`/api/writing/entries/${entry.id}/score`, { answer: $("writingAnswer")?.value || "" }));
    state.writing.entry = scored;
    state.writing.activeReportId = scored.id;
    state.writing.dirty = false;
    renderWritingSurface();
    await loadWritingSummary();
    switchView("writingReports");
  } finally {
    if (!state.writing.scorePollingEntryId) setWritingPending(false);
  }
}

async function openWritingEntry(entryId) {
  if (!entryId) return;
  if (state.writing.dirty && !window.confirm("当前作文还没有保存，确定要打开历史记录吗？")) return;
  const entry = await withBusy("Loading writing entry...", () => api(`/api/writing/entries/${entryId}`));
  await recoverWritingEntry(entry);
  if (isWritingTaskActive(entry.ai_task)) startWritingScorePolling(entry.id, { switchOnComplete: false });
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
  const turns = attempt.turns || [];
  const visibleTurns = turns.filter(shouldRenderReportTurn);
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
          <p class="muted">${escapeHtml(attempt.title || "")} - ${visibleTurns.length} question${visibleTurns.length === 1 ? "" : "s"}</p>
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
  `;
  document.querySelectorAll("[data-regenerate-turn]").forEach((button) => {
    button.addEventListener("click", () => regenerateTurnFeedback(button));
  });
  document.querySelectorAll("[data-regenerate-transcript]").forEach((button) => {
    button.addEventListener("click", () => regenerateTurnTranscript(button));
  });
  document.querySelectorAll("[data-edit-p1-corpus]").forEach((button) => {
    button.addEventListener("click", () => openP1CorpusEditor({
      question_id: button.dataset.questionId || "",
      topic: button.dataset.topic || "general",
      question: button.dataset.question || "",
      display_question: button.dataset.displayQuestion || button.dataset.question || "",
      corpus_text: "",
      last_ai_answer: button.dataset.aiAnswer || "",
    }));
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
  const body = markdown ? renderMarkdown(markdown) : `
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
  const reportTurns = turns.filter(shouldRenderReportTurn);
  const tableClass = isP2 ? "turn-report-table p2-report-table" : "turn-report-table p1-p3-report-table";
  const headers = isP2
    ? "<th>我的原文</th><th>7 分回答</th>"
    : "<th>Question</th><th>Your recording</th><th>Band 7 spoken version</th>";
  const bodyHtml = reportTurns.map((turn) => turnReportGroup(attempt.id, turn, attempt, isP2)).join("");
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

function reportPromptRole(turn) {
  return turn?.prompt?.role || "";
}

function shouldRenderReportTurn(turn) {
  return !(turn?.part === "p1" && turn?.prompt?.flow === "intro" && reportPromptRole(turn) === "name");
}

function shouldRenderTurnCoaching(turn) {
  return !(turn?.part === "p1" && turn?.prompt?.flow === "intro" && reportPromptRole(turn) === "work_study");
}

function mockTurnSections(attempt, turns) {
  const partScores = attempt.part_scores || {};
  return ["p1", "p2", "p3"].map((part) => {
    const partTurns = turns.filter((turn) => turn.part === part).filter(shouldRenderReportTurn);
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
  if (turn.display_transcript_markdown) return renderMarkdown(turn.display_transcript_markdown);
  if (turn.display_transcript) return renderMarkdown(turn.display_transcript);
  if (turn.transcript_markdown) return renderMarkdown(turn.transcript_markdown);
  if (turn.transcript_cleaned) return renderMarkdown(turn.transcript_cleaned);
  return missingTranscriptHtml(turn);
}

function formatReportTime(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(raw)) return raw;
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  const pad = (number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
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

async function loadP1Corpus() {
  const stats = $("p1CorpusStats");
  const container = $("p1CorpusTopics");
  if (stats) stats.textContent = "Loading...";
  if (container) container.innerHTML = '<p class="muted">正在加载 P1 题库...</p>';
  try {
    const payload = await api("/api/p1-corpus");
    state.p1Corpus.topics = payload.topics || [];
    if (stats) {
      stats.textContent = `${payload.topic_count || state.p1Corpus.topics.length} 个话题 · ${payload.question_count || 0} 道题 · 已保存 ${payload.saved_count || 0}`;
    }
    renderP1CorpusTopics();
  } catch (error) {
    if (container) container.innerHTML = `<p class="error">${escapeHtml(error.message || String(error))}</p>`;
    if (stats) stats.textContent = "加载失败";
  }
}

function renderP1CorpusTopics() {
  const container = $("p1CorpusTopics");
  if (!container) return;
  const topics = state.p1Corpus.topics || [];
  if (!topics.length) {
    container.innerHTML = '<p class="muted">还没有 P1 题目。</p>';
    return;
  }
  container.innerHTML = topics.map((topic) => {
    const questions = topic.questions || [];
    const saved = questions.filter((item) => item.corpus_text).length;
    return `
      <article class="p1-topic-card">
        <header>
          <h3>${escapeHtml(topic.label || topic.topic)}</h3>
          <span>${saved}/${questions.length}</span>
        </header>
        <div class="p1-topic-question-list">
          ${questions.map((item, index) => `
            <button type="button" class="${item.corpus_text ? "has-corpus" : ""}" data-p1-corpus-question="${escapeHtml(item.question_id)}">
              <strong>Q${index + 1}.</strong>
              <span>${escapeHtml(item.question)}</span>
            </button>
          `).join("")}
        </div>
      </article>
    `;
  }).join("");
}

function findP1CorpusEntry(questionId) {
  for (const topic of state.p1Corpus.topics || []) {
    const found = (topic.questions || []).find((item) => item.question_id === questionId);
    if (found) return found;
  }
  return null;
}

function p1CorpusStorageEntry(entry) {
  const prompt = entry?.prompt || {};
  return {
    question_id: entry?.storage_question_id || entry?.question_id || "",
    topic: entry?.storage_topic || entry?.topic || prompt.topic || "general",
    question: entry?.storage_question || entry?.question || prompt.question || "",
  };
}

function upsertP1CorpusEntry(saved) {
  if (!saved?.question_id) return null;
  const existing = findP1CorpusEntry(saved.question_id);
  if (existing) {
    existing.corpus_text = saved.corpus_text || "";
    existing.last_ai_answer = saved.last_ai_answer || "";
    existing.updated_at = saved.updated_at || "";
    existing.question = saved.question || existing.question || "";
    existing.topic = saved.topic || existing.topic || "general";
    return existing;
  }
  return saved;
}

function getCorpusMarkdownValue(textareaId) {
  const editor = corpusMarkdownEditors[textareaId];
  if (editor?._corpusReady) return editor.getValue();
  return $(textareaId)?.value || "";
}

function isCorpusEditorReady(textareaId) {
  const editor = corpusMarkdownEditors[textareaId];
  return !editor || !!editor._corpusReady;
}

function setCorpusMarkdownValue(textareaId, value) {
  const textarea = $(textareaId);
  if (textarea) textarea.value = value || "";
  const editor = ensureCorpusMarkdownEditor(textareaId);
  if (editor) {
    if (editor._corpusReady) {
      editor.setValue(value || "", true);
    } else {
      editor._pendingCorpusValue = value || "";
    }
  }
}

function sendKeepaliveJson(path, payload) {
  try {
    const headers = { "Content-Type": "application/json" };
    if (csrfToken) headers["X-CSRFToken"] = csrfToken;
    navigator.sendBeacon?.(
      path,
      new Blob([JSON.stringify(payload)], { type: "application/json" }),
    ) || fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers,
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => null);
  } catch (_error) {
    // Best-effort autosave during unload.
  }
}

function autosaveOpenCorpusEditors() {
  const p1Entry = state.p1Corpus.activeEntry;
  if (p1Entry && !$("#p1CorpusDialog")?.classList.contains("hidden")) {
    if (!isCorpusEditorReady("p1CorpusText")) return;
    const corpusText = getCorpusMarkdownValue("p1CorpusText").trim();
    if (!corpusText) return;
    const storage = p1CorpusStorageEntry(p1Entry);
    sendKeepaliveJson("/api/p1-corpus", {
      question_id: storage.question_id,
      topic: storage.topic,
      question: storage.question,
      corpus_text: corpusText,
      last_ai_answer: p1Entry.last_ai_answer || p1Entry.band7_version || p1Entry.aiAnswer || "",
      source: "report_or_library",
    });
  }
  const p2Entry = state.p2Corpus.activeEntry;
  if (p2Entry && !$("#p2CorpusDialog")?.classList.contains("hidden")) {
    if (!isCorpusEditorReady("p2CorpusText")) return;
    const materialText = getCorpusMarkdownValue("p2CorpusText").trim();
    if (!materialText) return;
    sendKeepaliveJson("/api/p2-corpus", {
      entry_id: p2Entry.entry_id || "",
      category: $("p2CorpusCategory")?.value || p2Entry.category || "person",
      title: $("p2CorpusTitle")?.value || "",
      material_text: materialText,
      linked_question: $("p2CorpusLinkedQuestion")?.value || "",
      source: "p2_corpus_editor",
    });
  }
}

function ensureCorpusMarkdownEditor(textareaId) {
  if (corpusMarkdownEditors[textareaId]) return corpusMarkdownEditors[textareaId];
  const textarea = $(textareaId);
  if (!textarea || !window.Vditor) return null;
  const mount = document.createElement("div");
  mount.className = "corpus-live-editor";
  textarea.classList.add("hidden");
  textarea.insertAdjacentElement("afterend", mount);
  let editor;
  editor = new Vditor(mount, {
    value: textarea.value || "",
    mode: "ir",
    height: "100%",
    cache: { enable: false },
    counter: { enable: false },
    typewriterMode: false,
    toolbarConfig: { pin: true },
    toolbar: [
      "headings",
      "bold",
      "italic",
      "strike",
      "|",
      "quote",
      "list",
      "ordered-list",
      "|",
      "link",
    ],
    input(value) {
      textarea.value = value || "";
    },
    after() {
      editor._corpusReady = true;
      if (editor._pendingCorpusValue !== undefined) {
        editor.setValue(editor._pendingCorpusValue || "", true);
        textarea.value = editor._pendingCorpusValue || "";
        delete editor._pendingCorpusValue;
      }
    },
  });
  editor._corpusReady = false;
  corpusMarkdownEditors[textareaId] = editor;
  return editor;
}

async function openP1CorpusLibrary() {
  if (!state.account.authenticated) {
    state.account.returnView = "p1Corpus";
    switchView("login", { force: true, skipAuthGate: true, authMessage: "登录后才能保存和复用你的 P1 语料库。" });
    return;
  }
  openCorpusWindow("p1Corpus");
}

async function openP1CorpusEditor(entry) {
  if (!entry) return;
  const storage = p1CorpusStorageEntry(entry);
  let preparedEntry = { ...entry, ...storage };
  if (storage.question_id && !preparedEntry.corpus_text) {
    if (!(state.p1Corpus.topics || []).length) {
      try {
        const payload = await api("/api/p1-corpus");
        state.p1Corpus.topics = payload.topics || [];
      } catch (_error) {
        // The editor can still open with the current report answer.
      }
    }
    const existing = findP1CorpusEntry(storage.question_id);
    if (existing) {
      preparedEntry = {
        ...preparedEntry,
        corpus_text: existing.corpus_text || "",
        last_ai_answer: preparedEntry.last_ai_answer || existing.last_ai_answer || "",
      };
    }
  }
  state.p1Corpus.activeEntry = preparedEntry;
  entry = preparedEntry;
  const topic = entry.topic || entry.prompt?.topic || "";
  const question = entry.display_question || entry.question || "";
  const aiAnswer = entry.last_ai_answer || entry.band7_version || entry.aiAnswer || "";
  text("p1CorpusDialogTopic", topic ? topic.replaceAll("_", " ").toUpperCase() : "PART 1");
  text("p1CorpusDialogTitle", question);
  setCorpusMarkdownValue("p1CorpusText", entry.corpus_text || "");
  const aiBox = $("p1CorpusAiAnswer");
  const aiWrap = aiBox?.closest(".p1-corpus-ai-box");
  aiWrap?.classList.toggle("hidden", !aiAnswer);
  if (aiBox) aiBox.innerHTML = aiAnswer ? renderMarkdown(aiAnswer) : "";
  text("p1CorpusSaveStatus", "");
  $("p1CorpusDialog")?.classList.remove("hidden");
  setTimeout(() => corpusMarkdownEditors.p1CorpusText?.focus?.() || $("p1CorpusText")?.focus(), 0);
}

function closeP1CorpusEditor() {
  $("p1CorpusDialog")?.classList.add("hidden");
  state.p1Corpus.activeEntry = null;
}

async function saveAndCloseP1CorpusEditor() {
  if (!$("p1CorpusDialog") || $("p1CorpusDialog").classList.contains("hidden")) return;
  const entry = state.p1Corpus.activeEntry;
  const editorReady = isCorpusEditorReady("p1CorpusText");
  const corpusText = editorReady ? getCorpusMarkdownValue("p1CorpusText").trim() : "";
  closeP1CorpusEditor();
  if (entry && corpusText) saveP1CorpusEntry({ entry, corpusText, silent: true }).catch(() => null);
}

async function saveP1CorpusEntry(options = {}) {
  const entry = options.entry || state.p1Corpus.activeEntry;
  if (!entry) return;
  if (state.p1Corpus.saving) return;
  if (!options.corpusText && !isCorpusEditorReady("p1CorpusText")) {
    text("p1CorpusSaveStatus", "编辑器还没加载完成，请等一秒再保存。");
    if (options.closeOnError) closeP1CorpusEditor();
    return;
  }
  state.p1Corpus.saving = true;
  const button = $("saveP1CorpusBtn");
  const original = button?.textContent || "保存语料";
  const nextCorpusText = (options.corpusText ?? getCorpusMarkdownValue("p1CorpusText")).trim();
  if (!nextCorpusText) {
    if (!options.silent) text("p1CorpusSaveStatus", "内容为空，未保存。");
    state.p1Corpus.saving = false;
    if (options.closeOnEmpty) closeP1CorpusEditor();
    return;
  }
  if (button && !options.silent) {
    button.disabled = true;
    button.textContent = "保存中...";
  }
  if (!options.silent) text("p1CorpusSaveStatus", "");
  try {
    const storage = p1CorpusStorageEntry(entry);
    const saved = await api("/api/p1-corpus", {
      question_id: storage.question_id,
      topic: storage.topic,
      question: storage.question,
      corpus_text: nextCorpusText,
      last_ai_answer: entry.last_ai_answer || entry.band7_version || entry.aiAnswer || "",
      source: "report_or_library",
    });
    if (!options.silent) text("p1CorpusSaveStatus", `已保存 ${saved.updated_at || ""}`);
    const updated = upsertP1CorpusEntry(saved);
    if (state.p1Corpus.activeEntry) {
      state.p1Corpus.activeEntry = {
        ...(state.p1Corpus.activeEntry || {}),
        ...(updated || saved),
        display_question: state.p1Corpus.activeEntry?.display_question || saved.question || "",
      };
    }
    renderP1CorpusTopics();
    if (options.closeOnSuccess) closeP1CorpusEditor();
  } catch (error) {
    if (!options.silent) text("p1CorpusSaveStatus", error.message || String(error));
    if (options.closeOnError) closeP1CorpusEditor();
  } finally {
    state.p1Corpus.saving = false;
    if (button && !options.silent) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

async function loadP2Corpus() {
  const stats = $("p2CorpusStats");
  const container = $("p2CorpusTopics");
  if (stats) stats.textContent = "Loading...";
  if (container) container.innerHTML = '<p class="muted">正在加载 P2 素材库...</p>';
  try {
    const payload = await api("/api/p2-corpus");
    state.p2Corpus.categories = payload.categories || [];
    if (stats) stats.textContent = `${payload.category_count || 5} 个分类 · 已保存 ${payload.material_count || 0}`;
    renderP2CorpusTopics();
    renderP2CorpusPrepPanel();
  } catch (error) {
    if (container) container.innerHTML = `<p class="error">${escapeHtml(error.message || String(error))}</p>`;
    if (stats) stats.textContent = "加载失败";
  }
}

function renderP2CorpusTopics() {
  const container = $("p2CorpusTopics");
  if (!container) return;
  const categories = state.p2Corpus.categories || [];
  if (!categories.length) {
    container.innerHTML = '<p class="muted">还没有 P2 素材分类。</p>';
    return;
  }
  container.innerHTML = categories.map((category) => {
    const items = category.items || [];
    return `
      <article class="p2-topic-card">
        <header>
          <h3>${escapeHtml(category.label || category.category)}</h3>
          <span>${items.length}</span>
        </header>
        <div class="p2-topic-material-list">
          ${items.map((item, index) => `
            <button type="button" class="has-corpus" data-p2-corpus-entry="${escapeHtml(item.entry_id)}">
              <strong>${index + 1}.</strong>
              <span>${escapeHtml(item.title)}</span>
            </button>
          `).join("")}
          <button type="button" class="p2-add-material-button" data-p2-corpus-new="${escapeHtml(category.category)}">
            <strong>+</strong>
            <span>新增${escapeHtml(category.label || "素材")}</span>
          </button>
        </div>
      </article>
    `;
  }).join("");
}

async function loadCorpusHome() {}

async function loadLanguageTakeaways() {
  const stats = $("languageTakeawayStats");
  const list = $("languageTakeawayList");
  if (state.languageTakeaway.loaded) {
    renderLanguageTakeawayToggle();
    renderLanguageTakeaways();
    if (stats) stats.textContent = `${state.languageTakeaway.items.length} 条 · 刷新中`;
  } else {
    if (stats) stats.textContent = "Loading...";
    if (list) list.innerHTML = '<p class="muted">正在加载 Takeaway...</p>';
  }
  try {
    const payload = await api("/api/language-takeaways");
    state.languageTakeaway.items = payload.items || [];
    state.languageTakeaway.loaded = true;
    if (stats) stats.textContent = `${payload.count || 0} 条`;
    renderLanguageTakeawayToggle();
    renderLanguageTakeaways();
  } catch (error) {
    if (stats) stats.textContent = "加载失败";
    if (list) list.innerHTML = `<p class="error">${escapeHtml(error.message || String(error))}</p>`;
  }
}

function renderLanguageTakeaways() {
  const list = $("languageTakeawayList");
  if (!list) return;
  const items = state.languageTakeaway.items || [];
  const hiddenMode = state.languageTakeaway.hideEnglish;
  const revealed = state.languageTakeaway.revealedEntryIds;
  if (!items.length) {
    list.innerHTML = '<p class="muted language-book-empty">还没有摘录。平时选中单词或短语，点击“译”就可以加入这里。</p>';
    return;
  }
  list.innerHTML = items.map((item) => `
    <button type="button"
      class="language-takeaway-card ${hiddenMode && !revealed.has(item.entry_id) ? "is-concealed" : "is-revealed"}"
      data-takeaway-entry="${escapeHtml(item.entry_id)}">
      <strong class="takeaway-source">${escapeHtml(item.source_text)}</strong>
      <span class="takeaway-chinese">${escapeHtml(item.chinese_text || "未填写中文")}</span>
    </button>
  `).join("");
}

function renderLanguageTakeawayToggle() {
  const button = $("languageTakeawayHideToggle");
  if (!button) return;
  const hidden = state.languageTakeaway.hideEnglish;
  button.setAttribute("aria-pressed", hidden ? "true" : "false");
  button.innerHTML = hidden
    ? `<svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M3 3l18 18"></path>
        <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"></path>
        <path d="M9.9 4.2A10.3 10.3 0 0 1 12 4c6.5 0 10 8 10 8a17.9 17.9 0 0 1-4.2 5.1"></path>
        <path d="M6.6 6.6C3.6 8.6 2 12 2 12s3.5 8 10 8a9.5 9.5 0 0 0 4.8-1.3"></path>
      </svg><span>显示英文</span>`
    : `<svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"></path>
        <circle cx="12" cy="12" r="3"></circle>
      </svg><span>遮住英文</span>`;
}

function toggleLanguageTakeawayHiddenMode() {
  state.languageTakeaway.hideEnglish = !state.languageTakeaway.hideEnglish;
  if (state.languageTakeaway.hideEnglish) state.languageTakeaway.revealedEntryIds.clear();
  renderLanguageTakeawayToggle();
  renderLanguageTakeaways();
}

function speakLanguageTakeaway(textValue) {
  const value = String(textValue || "").trim();
  if (!value || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(value);
  utterance.lang = "en-US";
  utterance.rate = 0.86;
  window.speechSynthesis.speak(utterance);
}

function revealAndSpeakLanguageTakeaway(entryId) {
  const item = (state.languageTakeaway.items || []).find((entry) => entry.entry_id === entryId);
  if (!item) return;
  state.languageTakeaway.revealedEntryIds.add(entryId);
  speakLanguageTakeaway(item.source_text);
  renderLanguageTakeaways();
}

function languageTakeawayTranslationStatus(result) {
  if (result?.status === "ready" && result?.provider === "local") return "本地词典已填充，可继续编辑";
  if (result?.status === "ready") return "已翻译";
  if (result?.status === "needs_edit") return "本地词典未命中，可手动填写中文";
  if (result?.status === "missing_token") return "未配置翻译服务，可手动填写中文";
  if (result?.status === "unavailable") return "翻译服务暂不可用，可手动填写中文";
  return "可手动填写中文";
}

function selectionText() {
  const selection = window.getSelection?.();
  const textValue = String(selection?.toString() || "").trim();
  if (!selection || selection.rangeCount === 0 || textValue.length < 1 || textValue.length > 160) return null;
  const range = selection.getRangeAt(0);
  const rect = range.getBoundingClientRect();
  if (!rect || (rect.width === 0 && rect.height === 0)) return null;
  return { text: textValue, rect };
}

function hideLanguageTakeawayTrigger() {
  $("languageTakeawayTrigger")?.classList.add("hidden");
}

function hideLanguageTakeawayPopup() {
  $("languageTakeawayPopup")?.classList.add("hidden");
  text("languageTakeawayStatus", "");
}

function placeLanguageTakeawayTrigger(left, top) {
  const trigger = $("languageTakeawayTrigger");
  if (!trigger) return;
  const margin = 12;
  const rect = trigger.getBoundingClientRect();
  const width = rect.width || 34;
  const height = rect.height || 34;
  const maxLeft = Math.max(margin, window.innerWidth - width - margin);
  const maxTop = Math.max(margin, window.innerHeight - height - margin);
  trigger.style.left = `${Math.min(maxLeft, Math.max(margin, left))}px`;
  trigger.style.top = `${Math.min(maxTop, Math.max(margin, top))}px`;
}

function showLanguageTakeawayTrigger(selectionInfo) {
  const trigger = $("languageTakeawayTrigger");
  if (!trigger || !selectionInfo) return;
  state.languageTakeaway.selectedText = selectionInfo.text;
  placeLanguageTakeawayTrigger(selectionInfo.rect.right + 8, selectionInfo.rect.top - 4);
  trigger.classList.remove("hidden");
}

function scheduleLanguageTakeawayTriggerFromSelection() {
  window.clearTimeout(state.languageTakeaway.selectionTimer);
  state.languageTakeaway.selectionTimer = window.setTimeout(() => {
    if (!$("languageTakeawayPopup")?.classList.contains("hidden")) return;
    const info = selectionText();
    if (info) showLanguageTakeawayTrigger(info);
    else hideLanguageTakeawayTrigger();
  }, 80);
}

function placeLanguageTakeawayPopup(left, top) {
  const popup = $("languageTakeawayPopup");
  if (!popup) return;
  const margin = 12;
  const rect = popup.getBoundingClientRect();
  const width = rect.width || 360;
  const height = rect.height || 360;
  const maxLeft = Math.max(margin, window.innerWidth - width - margin);
  const maxTop = Math.max(margin, window.innerHeight - height - margin);
  popup.style.left = `${Math.min(maxLeft, Math.max(margin, left))}px`;
  popup.style.top = `${Math.min(maxTop, Math.max(margin, top))}px`;
}

async function openLanguageTakeawayPopup() {
  const textValue = state.languageTakeaway.selectedText;
  if (!textValue) return;
  const popup = $("languageTakeawayPopup");
  const trigger = $("languageTakeawayTrigger");
  if (!popup || !trigger) return;
  $("languageTakeawaySource").value = textValue;
  $("languageTakeawayChinese").value = "";
  text("languageTakeawayStatus", "翻译中...");
  const triggerRect = trigger.getBoundingClientRect();
  popup.classList.remove("hidden");
  placeLanguageTakeawayPopup(triggerRect.left, triggerRect.bottom + 8);
  hideLanguageTakeawayTrigger();
  await translateLanguageTakeawaySource(textValue);
}

async function translateLanguageTakeawaySource(sourceValue = null) {
  const sourceText = String(sourceValue ?? $("languageTakeawaySource")?.value ?? "").trim();
  if (!sourceText) {
    text("languageTakeawayStatus", "原文为空。");
    return;
  }
  text("languageTakeawayStatus", "翻译中...");
  try {
    const result = await api("/api/language-takeaways/translate", { text: sourceText });
    $("languageTakeawaySource").value = result.source_text || sourceText;
    $("languageTakeawayChinese").value = result.chinese_text || "";
    text("languageTakeawayStatus", languageTakeawayTranslationStatus(result));
  } catch (error) {
    text("languageTakeawayStatus", error.message || "翻译失败，可手动填写中文");
  }
}

async function saveLanguageTakeaway() {
  const sourceText = ($("languageTakeawaySource")?.value || "").trim();
  const chineseText = ($("languageTakeawayChinese")?.value || "").trim();
  if (!sourceText) {
    text("languageTakeawayStatus", "原文为空。");
    return;
  }
  text("languageTakeawayStatus", "保存中...");
  try {
    const saved = await api("/api/language-takeaways", {
      source_text: sourceText,
      chinese_text: chineseText,
      context_url: window.location.href,
      context_label: viewCopy[state.view]?.[0] || "",
      source: "selection_popup",
    });
    const existingIndex = state.languageTakeaway.items.findIndex((item) => item.entry_id === saved.entry_id);
    if (existingIndex >= 0) state.languageTakeaway.items.splice(existingIndex, 1);
    state.languageTakeaway.items.unshift(saved);
    state.languageTakeaway.revealedEntryIds.add(saved.entry_id);
    renderLanguageTakeaways();
    text("languageTakeawayStats", `${state.languageTakeaway.items.length} 条`);
    hideLanguageTakeawayPopup();
  } catch (error) {
    text("languageTakeawayStatus", error.message || "保存失败");
  }
}

function findP2CorpusEntry(entryId) {
  for (const category of state.p2Corpus.categories || []) {
    const found = (category.items || []).find((item) => item.entry_id === entryId);
    if (found) return { ...found, label: category.label || found.label };
  }
  return null;
}

async function openP2CorpusLibrary() {
  if (!state.account.authenticated) {
    state.account.returnView = "p2Corpus";
    switchView("login", { force: true, skipAuthGate: true, authMessage: "登录后才能保存和复用你的 P2 串题素材库。" });
    return;
  }
  openCorpusWindow("p2Corpus");
}

function openP2CorpusEditor(entry = {}) {
  const category = entry.category || "person";
  state.p2Corpus.activeEntry = { ...entry, category };
  text("p2CorpusDialogCategory", (entry.label || category).toString());
  text("p2CorpusDialogTitle", entry.entry_id ? "编辑 P2 素材" : "新增 P2 素材");
  if ($("p2CorpusCategory")) $("p2CorpusCategory").value = category;
  if ($("p2CorpusTitle")) $("p2CorpusTitle").value = entry.title || "";
  setCorpusMarkdownValue("p2CorpusText", entry.material_text || "");
  if ($("p2CorpusLinkedQuestion")) $("p2CorpusLinkedQuestion").value = entry.linked_question || "";
  text("p2CorpusSaveStatus", "");
  $("p2CorpusDialog")?.classList.remove("hidden");
  setTimeout(() => $("p2CorpusTitle")?.focus(), 0);
}

function closeP2CorpusEditor() {
  $("p2CorpusDialog")?.classList.add("hidden");
  state.p2Corpus.activeEntry = null;
}

async function saveAndCloseP2CorpusEditor() {
  if (!$("p2CorpusDialog") || $("p2CorpusDialog").classList.contains("hidden")) return;
  const entry = state.p2Corpus.activeEntry || {};
  const editorReady = isCorpusEditorReady("p2CorpusText");
  const materialText = editorReady ? getCorpusMarkdownValue("p2CorpusText").trim() : "";
  const title = $("p2CorpusTitle")?.value || "";
  const category = $("p2CorpusCategory")?.value || entry.category || "person";
  const linkedQuestion = $("p2CorpusLinkedQuestion")?.value || "";
  closeP2CorpusEditor();
  if (materialText) {
    saveP2CorpusEntry({ entry: { ...entry, category, title, linked_question: linkedQuestion }, materialText, silent: true }).catch(() => null);
  }
}

async function saveP2CorpusEntry(options = {}) {
  const entry = options.entry || state.p2Corpus.activeEntry || {};
  if (state.p2Corpus.saving) return;
  if (!options.materialText && !isCorpusEditorReady("p2CorpusText")) {
    text("p2CorpusSaveStatus", "编辑器还没加载完成，请等一秒再保存。");
    if (options.closeOnError) closeP2CorpusEditor();
    return;
  }
  state.p2Corpus.saving = true;
  const button = $("saveP2CorpusBtn");
  const original = button?.textContent || "保存素材";
  const nextMaterialText = (options.materialText ?? getCorpusMarkdownValue("p2CorpusText")).trim();
  if (!nextMaterialText) {
    if (!options.silent) text("p2CorpusSaveStatus", "内容为空，未保存。");
    state.p2Corpus.saving = false;
    if (options.closeOnEmpty) closeP2CorpusEditor();
    return;
  }
  if (button && !options.silent) {
    button.disabled = true;
    button.textContent = "保存中...";
  }
  if (!options.silent) text("p2CorpusSaveStatus", "");
  try {
    const saved = await api("/api/p2-corpus", {
      entry_id: entry.entry_id || "",
      category: $("p2CorpusCategory")?.value || entry.category || "person",
      title: $("p2CorpusTitle")?.value || entry.title || "",
      material_text: nextMaterialText,
      linked_question: $("p2CorpusLinkedQuestion")?.value || entry.linked_question || "",
      source: "p2_corpus_editor",
    });
    if (!options.silent) text("p2CorpusSaveStatus", `已保存 ${saved.updated_at || ""}`);
    await loadP2Corpus();
    state.p2Corpus.selectedEntryId ||= saved.entry_id;
    if (options.closeOnSuccess) closeP2CorpusEditor();
  } catch (error) {
    if (!options.silent) text("p2CorpusSaveStatus", error.message || String(error));
    if (options.closeOnError) closeP2CorpusEditor();
  } finally {
    state.p2Corpus.saving = false;
    if (button && !options.silent) {
      button.disabled = false;
      button.textContent = original;
    }
  }
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

function p1CorpusTargetForTurn(turn, attempt) {
  if (turn?.part !== "p1") return null;
  const prompt = turn.prompt || {};
  let topicTarget = turn;
  if (prompt.role === "follow_up" && prompt.after_turn) {
    topicTarget = (attempt.turns || []).find((item) => item.id === prompt.after_turn) || turn;
  }
  const topicPrompt = topicTarget.prompt || {};
  return {
    questionId: turn.parent_question_id || topicTarget.question_id || topicPrompt.question_id || turn.question_id || prompt.question_id || "",
    topic: turn.parent_topic || topicTarget.topic || topicPrompt.topic || turn.topic || prompt.topic || "general",
    question: turn.parent_question || topicTarget.question || topicPrompt.question || turn.question || "",
    displayQuestion: turn.question || topicTarget.question || "",
  };
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
  const modelAudioControl = modelAudio.audio_url
    ? `<audio controls src="${escapeHtml(modelAudio.audio_url)}"></audio>`
    : '<p class="audio-warning">Server model-answer audio unavailable.</p>';
  const corpusTarget = p1CorpusTargetForTurn(turn, attempt);
  const corpusButton = corpusTarget
    ? `<button type="button" class="ghost corpus-edit-button"
        data-edit-p1-corpus="1"
        data-question-id="${escapeHtml(corpusTarget.questionId)}"
        data-topic="${escapeHtml(corpusTarget.topic)}"
        data-question="${escapeHtml(corpusTarget.question)}"
        data-display-question="${escapeHtml(corpusTarget.displayQuestion || corpusTarget.question)}"
        data-ai-answer="${escapeHtml(band7Markdown || band7 || "")}">编辑语料库</button>`
    : "";
  const coachingRow = shouldRenderTurnCoaching(turn)
    ? `<tr class="p1-p3-coaching-row">
      <td colspan="3" class="ai-coaching-cell">
        <h4 class="coaching-title">AI 辅导</h4>
        ${aiCoachingHtml(turn, attempt)}
      </td>
    </tr>`
    : "";

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
          ${modelAudioControl}
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
  const questionCell = `<td><div class="question-header"><strong>${escapeHtml(turn.part.toUpperCase())} ${turn.index + 1}</strong>${isFollowUp ? '<span class="follow-up-pill">Follow-up</span>' : ""}</div><p>${escapeHtml(turn.question)}</p>${corpusButton ? `<div class="question-cell-actions">${corpusButton}</div>` : ""}</td>`;
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
        ${modelAudioControl}
        <p>${renderMarkdown(band7Markdown)}</p>
      </td>
    </tr>
    ${coachingRow}
  `;
}

function stopAllRuntime(label = "Ready") {
  state.startRequestId += 1;
  state.practiceSessionId += 1;
  state.startAbortController?.abort();
  state.startAbortController = null;
  stopExaminerPlayback();
  clearTimer();
  clearAutoNextTimeout();
  stopDictation();
  setDictationStatus("", "");
  state.currentTurn = null;
  state.transcript = "";
  state.transcriptFinal = "";
  state.transcriptInterim = "";
  state.transcriptStatus = "missing";
  state.practiceLocked = false;
  const summaryPanel = $("#summaryPanel");
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
  state.startRequestId += 1;
  state.practiceSessionId += 1;
  state.startAbortController?.abort();
  state.startAbortController = null;
  stopExaminerPlayback();
  let exitSessionId = state.practiceSessionId;
  if (state.status === "recording") {
    state.abortingAttemptId = attemptId || "__loading__";
    state.cancelRecording = true;
    stopRecording();
  } else {
    stopAllRuntime("Ready");
    state.abortingAttemptId = attemptId || "__loading__";
    exitSessionId = state.practiceSessionId;
  }
  state.practiceLocked = false;
  updateSidebarLock();
  if (attemptId) {
    await api(`/api/attempts/${attemptId}/abort`, {}).catch(() => null);
  }
  if (state.practiceSessionId !== exitSessionId) return;
  resetPracticeSurface();
}

function showError(error) {
  if (error?.status === 401) {
    state.account.authenticated = false;
    state.account.user = null;
    state.account.returnView = state.view;
    switchView("login", {
      force: true,
      skipAuthGate: true,
      authMessage: "登录状态已失效，请重新登录后继续。",
    });
    return;
  }
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
  const status = $("accountProfileStatus");
  const details = $("accountProfileDetails");
  const securityStatus = $("securityStatus");
  const fallback = state.account.authenticated
    ? `Signed in as ${state.account.user?.username || ""}`
    : (state.account.backendAvailable ? "Not signed in. Local names are still available." : "Backend unavailable. Local names are still available.");

  if (status) {
    status.textContent = message || fallback;
    status.classList.toggle("error", Boolean(isError));
  }
  if (details) {
    if (state.account.authenticated) {
      const user = state.account.user || {};
      const phone = user.phone_number ? ` · ${user.phone_number}` : "";
      details.textContent = `${user.username || "Current user"}${phone}`;
    } else {
      details.textContent = "Sign in to sync profile and security settings.";
    }
  }
  if (!message && securityStatus && !securityStatus.textContent.trim()) {
    securityStatus.textContent = state.account.authenticated ? "Use a strong password and rotate it regularly." : "Sign in to update password.";
    securityStatus.classList.remove("error");
  }
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
  } catch (error) {
    state.account.backendAvailable = error.status === 401;
    state.account.authenticated = false;
    state.account.user = null;
  }
}

async function submitLogin() {
  const username = ($("loginUsername")?.value || "").trim();
  const password = $("loginPassword")?.value || "";
  const statusEl = $("loginStatus");
  if (!username || !password) {
    if (statusEl) {
      statusEl.textContent = "Please enter username and password.";
      statusEl.classList.add("error");
    }
    return;
  }
  try {
    const result = await withBusy("Signing in...", () => api("/api/accounts/login/", { username, password }));
    state.account.backendAvailable = true;
    state.account.authenticated = true;
    state.account.user = result.user || null;
    csrfToken = null;
    await ensureCsrfToken();
    applyCandidateNames(accountProfileNames(state.account.user), true);
    await Promise.all([loadWallet(), loadWritingSummary(false).catch(() => null)]);
    const returnView = state.account.returnView || "accountProfile";
    state.account.returnView = null;
    switchView(returnView, { force: true, skipAuthGate: true });
    scheduleAuthenticatedPrefetch();
  } catch (error) {
    state.account.backendAvailable = Boolean(error.status && error.status < 500);
    if (statusEl) {
      statusEl.textContent = error.message || "Login failed";
      statusEl.classList.add("error");
    }
  }
}

async function submitRegister() {
  const username = ($("registerUsername")?.value || "").trim();
  const password = $("registerPassword")?.value || "";
  const passwordConfirm = $("registerPasswordConfirm")?.value || "";
  const statusEl = $("registerStatus");
  if (!username || !password) {
    if (statusEl) {
      statusEl.textContent = "Please enter username and password.";
      statusEl.classList.add("error");
    }
    return;
  }
  if (password !== passwordConfirm) {
    if (statusEl) {
      statusEl.textContent = "Passwords do not match.";
      statusEl.classList.add("error");
    }
    return;
  }
  const names = {
    fullName: ($("registerFullName")?.value || DEFAULT_FULL_NAME).trim() || DEFAULT_FULL_NAME,
    englishName: ($("registerEnglishName")?.value || DEFAULT_ENGLISH_NAME).trim() || DEFAULT_ENGLISH_NAME,
  };
  try {
    const result = await withBusy("Creating account...", () => api("/api/accounts/register/", {
      username,
      password,
      password_confirm: passwordConfirm,
      full_name: names.fullName,
      english_name: names.englishName,
      display_name: names.englishName,
    }));
    state.account.backendAvailable = true;
    state.account.authenticated = true;
    state.account.user = result.user || null;
    csrfToken = null;
    await ensureCsrfToken();
    applyCandidateNames(accountProfileNames(state.account.user), true);
    await Promise.all([loadWallet(), loadWritingSummary(false).catch(() => null)]);
    const returnView = state.account.returnView || "accountProfile";
    state.account.returnView = null;
    switchView(returnView, { force: true, skipAuthGate: true });
    scheduleAuthenticatedPrefetch();
  } catch (error) {
    state.account.backendAvailable = Boolean(error.status && error.status < 500);
    if (statusEl) {
      const errors = error.errors || {};
      const fieldErrors = Object.entries(errors).map(([field, messages]) => `${field}: ${messages.join(", ")}`).join("; ");
      statusEl.textContent = fieldErrors || error.message || "Registration failed";
      statusEl.classList.add("error");
    }
  }
}

async function submitPasswordChange() {
  const currentPassword = $("securityCurrentPassword")?.value || "";
  const newPassword = $("securityNewPassword")?.value || "";
  const newPasswordConfirm = $("securityNewPasswordConfirm")?.value || "";
  const statusEl = $("securityStatus");
  if (!currentPassword || !newPassword) {
    if (statusEl) {
      statusEl.textContent = "Please enter current and new password.";
      statusEl.classList.add("error");
    }
    return;
  }
  if (newPassword !== newPasswordConfirm) {
    if (statusEl) {
      statusEl.textContent = "New passwords do not match.";
      statusEl.classList.add("error");
    }
    return;
  }
  try {
    await withBusy("Changing password...", () => api("/api/accounts/password/change/", {
      current_password: currentPassword,
      new_password: newPassword,
      new_password_confirm: newPasswordConfirm,
    }));
    if (statusEl) {
      statusEl.textContent = "Password changed successfully.";
      statusEl.classList.remove("error");
    }
    $("securityCurrentPassword").value = "";
    $("securityNewPassword").value = "";
    $("securityNewPasswordConfirm").value = "";
  } catch (error) {
    if (statusEl) {
      const errors = error.errors || {};
      const fieldErrors = Object.entries(errors).map(([field, messages]) => `${field}: ${messages.join(", ")}`).join("; ");
      statusEl.textContent = fieldErrors || error.message || "Password change failed";
      statusEl.classList.add("error");
    }
  }
}

async function logoutAccount() {
  try {
    await withBusy("Signing out...", () => api("/api/accounts/logout/", {}));
  } catch (_error) {
    // Keep UI usable even if backend session expired
  }
  state.account.authenticated = false;
  state.account.user = null;
  state.account.returnView = null;
  clearUserScopedCaches();
  csrfToken = null;
  loadCandidateNames();
  switchView("login", { force: true, skipAuthGate: true, authMessage: "你已退出登录。" });
}

async function loadPasswordResetAvailability() {
  const status = $("forgotPasswordStatus");
  if (!status) return;
  status.textContent = "Checking password reset availability...";
  status.classList.remove("error");
  try {
    const payload = await api("/api/accounts/password/reset/availability/");
    status.textContent = payload.available
      ? "Password reset email is configured for this deployment."
      : (payload.message || "Password reset email is not configured on this deployment.");
    status.classList.toggle("error", !payload.available);
  } catch (error) {
    status.textContent = error.message || "Could not check password reset availability.";
    status.classList.add("error");
  }
}

function bindEvents() {
  const bindCorpusOverlayClose = (dialogId, closeEditor) => {
    const dialog = $(dialogId);
    if (!dialog) return;
    dialog.addEventListener("pointerdown", (event) => {
      if (event.target === dialog) {
        event.preventDefault();
        closeEditor();
      }
    });
  };
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
        if (corpusViews.has(button.dataset.view)) {
          exitPracticeAndSwitch(button.dataset.view).catch(showError);
          return;
        }
        showNavLockHint(button);
        return;
      }
      switchView(button.dataset.view);
    });
  });
  document.querySelectorAll(".avatar-settings-button").forEach((button) => {
    button.addEventListener("click", () => {
      if (state.account.authenticated) {
        switchView("accountProfile", { preservePractice: true });
      } else {
        switchView("login");
      }
    });
  });
  $("fullNameInput")?.addEventListener("input", scheduleCandidateNameSave);
  $("englishNameInput")?.addEventListener("input", scheduleCandidateNameSave);
  $("fullNameInput")?.addEventListener("blur", flushCandidateNameSave);
  $("englishNameInput")?.addEventListener("blur", flushCandidateNameSave);
  $("loginSubmitBtn")?.addEventListener("click", submitLogin);
  $("registerSubmitBtn")?.addEventListener("click", submitRegister);
  $("loginToRegisterLink")?.addEventListener("click", () => switchView("register"));
  $("loginForgotLink")?.addEventListener("click", () => switchView("forgotPassword"));
  $("registerToLoginLink")?.addEventListener("click", () => switchView("login"));
  $("forgotBackToLoginBtn")?.addEventListener("click", () => switchView("login"));
  $("authRequiredLoginBtn")?.addEventListener("click", () => switchView("login", { force: true, skipAuthGate: true }));
  $("authRequiredBackBtn")?.addEventListener("click", () => switchView("mock"));
  $("profileLogoutBtn")?.addEventListener("click", logoutAccount);
  $("profileSaveBtn")?.addEventListener("click", () => saveCandidateNames(true).catch((error) => renderAccountStatus(error.message, true)));
  $("securityChangePasswordBtn")?.addEventListener("click", submitPasswordChange);
  $("securityLogoutBtn")?.addEventListener("click", logoutAccount);
  $("openP1CorpusBtn")?.addEventListener("click", openP1CorpusLibrary);
  $("openP2CorpusBtn")?.addEventListener("click", openP2CorpusLibrary);
  $("topbarBackCorpusBtn")?.addEventListener("click", closeCorpusWindowOrReturn);
  bindCorpusOverlayClose("p1CorpusDialog", saveAndCloseP1CorpusEditor);
  bindCorpusOverlayClose("p2CorpusDialog", saveAndCloseP2CorpusEditor);
  $("p1CorpusTopics")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-p1-corpus-question]");
    if (!button) return;
    openP1CorpusEditor(findP1CorpusEntry(button.dataset.p1CorpusQuestion || ""));
  });
  $("p2CorpusTopics")?.addEventListener("click", (event) => {
    const existing = event.target.closest("[data-p2-corpus-entry]");
    if (existing) {
      openP2CorpusEditor(findP2CorpusEntry(existing.dataset.p2CorpusEntry || ""));
      return;
    }
    const created = event.target.closest("[data-p2-corpus-new]");
    if (created) openP2CorpusEditor({ category: created.dataset.p2CorpusNew || "person" });
  });
  document.querySelectorAll("[data-corpus-home-target]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.corpusHomeTarget || "corpus"));
  });
  $("languageTakeawayHideToggle")?.addEventListener("click", toggleLanguageTakeawayHiddenMode);
  $("languageTakeawayList")?.addEventListener("click", (event) => {
    const card = event.target.closest("[data-takeaway-entry]");
    if (!card) return;
    revealAndSpeakLanguageTakeaway(card.dataset.takeawayEntry || "");
  });
  document.addEventListener("selectionchange", () => {
    window.clearTimeout(state.languageTakeaway.selectionTimer);
    if (!selectionText()) hideLanguageTakeawayTrigger();
  });
  document.addEventListener("pointerdown", (event) => {
    const popup = $("languageTakeawayPopup");
    const trigger = $("languageTakeawayTrigger");
    if (popup?.contains(event.target) || trigger?.contains(event.target)) return;
    hideLanguageTakeawayTrigger();
  });
  document.addEventListener("pointerup", scheduleLanguageTakeawayTriggerFromSelection);
  document.addEventListener("keyup", (event) => {
    if (["Shift", "Meta", "Control", "Alt"].includes(event.key)) scheduleLanguageTakeawayTriggerFromSelection();
  });
  $("languageTakeawayTrigger")?.addEventListener("click", (event) => {
    event.preventDefault();
    openLanguageTakeawayPopup();
  });
  $("languageTakeawaySaveBtn")?.addEventListener("click", saveLanguageTakeaway);
  $("languageTakeawayCloseBtn")?.addEventListener("click", hideLanguageTakeawayPopup);
  $("languageTakeawaySource")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    translateLanguageTakeawaySource();
  });
  document.addEventListener("pointerdown", (event) => {
    const popup = $("languageTakeawayPopup");
    const trigger = $("languageTakeawayTrigger");
    if (popup?.classList.contains("hidden")) return;
    if (popup.contains(event.target) || trigger?.contains(event.target)) return;
    hideLanguageTakeawayPopup();
  });
  $("languageTakeawayPopupHandle")?.addEventListener("pointerdown", (event) => {
    const popup = $("languageTakeawayPopup");
    if (!popup || event.target.closest("button")) return;
    const rect = popup.getBoundingClientRect();
    state.languageTakeaway.dragging = true;
    state.languageTakeaway.dragOffsetX = event.clientX - rect.left;
    state.languageTakeaway.dragOffsetY = event.clientY - rect.top;
    popup.setPointerCapture?.(event.pointerId);
  });
  $("languageTakeawayPopup")?.addEventListener("pointermove", (event) => {
    if (!state.languageTakeaway.dragging) return;
    const popup = $("languageTakeawayPopup");
    if (!popup) return;
    placeLanguageTakeawayPopup(
      event.clientX - state.languageTakeaway.dragOffsetX,
      event.clientY - state.languageTakeaway.dragOffsetY
    );
  });
  $("languageTakeawayPopup")?.addEventListener("pointerup", () => {
    state.languageTakeaway.dragging = false;
  });
  $("saveP1CorpusBtn")?.addEventListener("click", () => saveP1CorpusEntry({ closeOnSuccess: true }));
  $("saveP2CorpusBtn")?.addEventListener("click", () => saveP2CorpusEntry({ closeOnSuccess: true }));
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!$("p1CorpusDialog")?.classList.contains("hidden")) {
      event.preventDefault();
      saveAndCloseP1CorpusEditor();
    } else if (!$("p2CorpusDialog")?.classList.contains("hidden")) {
      event.preventDefault();
      saveAndCloseP2CorpusEditor();
    }
  });
  window.addEventListener("beforeunload", autosaveOpenCorpusEditors);
  $("recordControl")?.addEventListener("click", () => {
    if (state.status === "recording") {
      stopRecording();
    } else if (state.status === "preparing") {
      const sessionId = state.practiceSessionId;
      if (!isActivePracticeSession(sessionId)) return;
      clearTimer();
      startRecording(sessionId).catch(showError);
    } else if (state.status === "idle" || state.status === "ready" || state.status === "summary") {
      if (state.currentTurn && state.status === "ready") {
        beginExaminerPhase(state.practiceSessionId);
      } else {
        startPractice();
      }
    }
  });
  document.querySelectorAll("[data-home-mode]").forEach((button) => {
    button.addEventListener("click", () => startPracticeMode(button.dataset.homeMode || "mock"));
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
  $("writingPromptPickerBtn")?.addEventListener("click", () => openWritingPromptPicker());
  $("writingPromptCloseBtn")?.addEventListener("click", closeWritingPromptPicker);
  document.querySelectorAll("[data-writing-prompt-close]").forEach((button) => {
    button.addEventListener("click", closeWritingPromptPicker);
  });
  document.querySelectorAll("[data-writing-picker-task]").forEach((button) => {
    button.addEventListener("click", async () => {
      const taskType = button.dataset.writingPickerTask || "task1_academic";
      state.writing.pickerTaskType = taskType;
      await loadWritingPrompts(taskType).catch(showWritingError);
      renderWritingPromptPicker();
    });
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

async function loadAccountProfile() {
  await loadAccount();
  await Promise.all([loadWallet(), loadWeakTraining()]);
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
  const urlView = requestedUrlView();
  let savedView = urlView || "home";
  if (!viewCopy[savedView]) savedView = "home";
  switchView(savedView, { skipPersist: Boolean(urlView), skipUrl: true });
  document.body.classList.remove("app-booting");
  scheduleAuthenticatedPrefetch();
  try {
    const summary = await api("/api/question-bank/summary");
    text("bankStatus", `${summary.part1_count} P1 · ${summary.part2_count} P2`);
    renderP3TopicChips(summary.part2_themes || []);
  } catch (error) {
    text("bankStatus", error.message);
  }
}

init();
