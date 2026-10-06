(function () {
  const MODES = new Set(["ielts", "interview"]);
  const PANES = new Set(["home", "practice", "reports", "report", "corpus", "custom"]);
  const MODE_KEY = "ielts-product-mode";
  const ARROW = '<span class="iv-arrow" aria-hidden="true">→</span>';
  // The interview counterpart of Mock + P1/P2/P3.
  const PARTS = {
    full: { zh: "完整面试", en: "Full interview", hint: ["自我介绍 → 项目 → 知识点 → 奖项 → 反问", "Intro → projects → knowledge → awards → your questions"], corpus: "project" },
    project: { zh: "项目深挖", en: "Projects", hint: ["介绍项目，再接受追问。", "Present a project, then take follow-ups."], corpus: "project" },
    knowledge: { zh: "知识点", en: "Knowledge", hint: ["技术栈与通用题库连续问答。", "Rapid questions from your stack and the bank."], corpus: "knowledge" },
    reverse: { zh: "反问环节", en: "Your questions", hint: ["你来提问，面试官回答并点评。", "You ask; the interviewer answers and reviews."], corpus: "jd" },
  };
  const STAGES = { self_intro: ["自我介绍", "Intro"], project: ["项目", "Projects"], knowledge: ["知识点", "Knowledge"], award: ["奖项", "Awards"], reverse: ["反问", "Questions"] };
  const CORPUS_TABS = [
    { id: "project", zh: "项目", en: "Projects", kinds: ["project", "project_followup"] },
    { id: "knowledge", zh: "知识点", en: "Knowledge", kinds: ["knowledge"] },
    { id: "story", zh: "自我介绍与奖项", en: "Intro & awards", kinds: ["self_intro", "award"] },
    { id: "jd", zh: "JD 与反问", en: "JD & questions", kinds: ["jd_question", "reverse_question"] },
  ];
  const KIND_LABELS = { self_intro: ["自我介绍", "Self intro"], project: ["项目讲述", "Project story"], project_followup: ["项目追问", "Project follow-up"], knowledge: ["知识点", "Knowledge"], award: ["奖项", "Award"], jd_question: ["岗位题", "Role question"], reverse_question: ["反问", "Question to ask"] };
  const SOURCE_LABELS = { curated: ["精选题库", "Curated"], resume: ["简历", "Resume"], jd: ["JD", "JD"], custom: ["自定义", "Custom"], practice: ["练习", "Practice"] };
  const SIGNALS = { strong: ["答得扎实", "Strong"], adequate: ["基本到位", "Adequate"], weak: ["还有缺口", "Gaps"] };

  function createInterview({ state, api, ensureCsrfToken, switchView, exitPractice, promptGuestLogin, escapeHtml, currentAiSourcePreference }) {
    let epoch = 0;
    let initialized = false;
    let requestController = null;
    let switcher = null;
    let recorder = null;
    let data = freshState();
    const byId = (id) => document.getElementById(id);
    const copy = (zh, en) => state.uiLanguage === "en" ? en : zh;
    const pick = (pair) => copy(pair[0], pair[1]);
    const esc = (value) => escapeHtml(String(value ?? ""));
    const pad = (value) => String(value).padStart(2, "0");
    const button = (action, content, { cls = "", attrs = "", disabled = false } = {}) => `<button type="button" class="${cls}" data-interview-action="${action}" ${attrs} ${data.busy || disabled ? "disabled" : ""}>${content}</button>`;
    const solid = (action, text, options = {}) => button(action, `${esc(text)}${ARROW}`, { ...options, cls: `iv-btn iv-btn--solid ${options.cls || ""}` });
    const outline = (action, text, options = {}) => button(action, esc(text), { ...options, cls: `iv-btn ${options.cls || ""}` });
    const quiet = (action, text, options = {}) => button(action, esc(text), { ...options, cls: `iv-link ${options.cls || ""}` });
    const kicker = (text) => `<p class="iv-eyebrow">${esc(text)}</p>`;
    const partName = (part) => (PARTS[part] ? copy(PARTS[part].zh, PARTS[part].en) : "");
    const stageName = (stage) => (STAGES[stage] ? pick(STAGES[stage]) : "");
    const dateText = (value, withTime = true) => {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return "–";
      return date.toLocaleString(state.uiLanguage === "en" ? "en-US" : "zh-CN", withTime ? { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" } : { month: "2-digit", day: "2-digit" });
    };

    function freshState() {
      return {
        pane: "home", part: "full", intensity: "standard", busy: false, error: "", notice: "",
        questions: [], categories: [], sessions: [], sessionsLoaded: false, current: null, report: null,
        corpus: null, corpusTab: "project", profile: null, customSide: "resume", resumeText: "", file: null, jdText: "",
        reportFilter: "all", reportFilterOpen: false, railScroll: 0,
        editor: null, launch: { category: "", count: 5, projectIds: new Set() },
        answer: { state: "idle", text: "", source: "typed", typing: false, error: "", peek: false },
      };
    }

    function resetForAccount() {
      epoch += 1;
      requestController?.abort();
      requestController = null;
      stopRecorder();
      data = freshState();
      if (byId("interviewPanel")) render();
      window.IELTSInterviewHome?.refresh();
      ensureOverview();
    }

    // The shared home panel needs the interview numbers whenever interview mode is on, whatever view loaded first.
    function ensureOverview() {
      if (state.productMode !== "interview" || !state.account.authenticated || data.busy) return;
      if (!data.sessionsLoaded || !data.corpus) loadOverview();
    }

    function setProductMode(mode) {
      if (!MODES.has(mode) || (mode === "interview" && !state.desktopCapabilities?.mock_interview)) mode = "ielts";
      state.productMode = mode;
      const name = mode === "interview" ? copy("模拟面试", "Mock Interview") : "IELTS Studio";
      document.body.classList.toggle("interview-mode", mode === "interview");
      byId("interviewNav")?.classList.toggle("hidden", mode !== "interview");
      if (byId("studioModeLabel")) byId("studioModeLabel").textContent = name;
      if (byId("studioModeCurrent")) byId("studioModeCurrent").textContent = name;
      document.querySelectorAll("[data-studio-mode]").forEach((el) => el.setAttribute("aria-checked", String(el.dataset.studioMode === mode)));
      window.IELTSInterviewHome?.apply(mode);
      if (mode === "interview") ensureOverview();
      try { localStorage.setItem(MODE_KEY, mode); } catch (_error) { /* Session-only preference. */ }
    }

    // ---- Mode switcher: the brand button grows into the card in place (shared corner, spring size, blur cross-fade).
    // ---- Mode switcher: the brand button grows into the card in place (corner-morph.js).
    // Colours come from the sidebar the control actually sits on: some appearance styles redefine --nav
    // without repainting the rail, so the token alone can say "white" on a dark sidebar.
    function syncSwitchPalette() {
      const control = byId("studioModeControl");
      const nav = control?.closest?.(".nav");
      if (!nav || typeof window.getComputedStyle !== "function") return;
      let style = window.getComputedStyle(nav);
      let channels = (style.backgroundColor.match(/[\d.]+/g) || []).map(Number);
      if (channels.length === 4 && channels[3] === 0) channels = (window.getComputedStyle(document.body).backgroundColor.match(/[\d.]+/g) || []).map(Number);
      const surface = channels.length >= 3 ? `rgb(${channels[0]}, ${channels[1]}, ${channels[2]})` : style.backgroundColor;
      const light = channels.length >= 3 && 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2] > 150;
      control.style.setProperty("--switch-surface", surface);
      control.style.setProperty("--switch-ink", style.color);
      control.dataset.switchTone = light ? "light" : "dark";
    }

    function menu(open, restoreFocus = false, focusItem = true) {
      if (!switcher) return;
      if (open) switcher.open(); else switcher.close({ restoreFocus });
      const dropdown = byId("studioModeMenu");
      // The card clips while it grows; a scrolling focus would shift its content out of the shared corner.
      if (open && focusItem && dropdown) { dropdown.querySelector('[aria-checked="true"]')?.focus({ preventScroll: true }); dropdown.scrollTop = 0; }
    }

    async function changeMode(mode, fromKeyboard = true) {
      if (mode !== state.productMode) {
        // Starting an interview must use the existing complete IELTS abort path.
        if (state.practiceLocked) await exitPractice();
        setProductMode(mode);
        // Both modes land on the home panel; interview mode swaps its copy (interview-home.js).
        data.pane = "home";
        switchView("home", { force: true });
        syncNav();
      }
      // Collapse onto the trigger as it now reads (the label width changes with the mode). Only keyboard users
      // get focus handed back; after a pointer pick a focus ring on the brand would read as a flicker.
      if (!fromKeyboard) document.activeElement?.blur?.();
      menu(false, fromKeyboard);
    }

    async function initialize() {
      if (initialized) return;
      initialized = true;
      const capabilities = await (window.IELTSNativeBridge?.ready || Promise.resolve(null));
      state.desktopCapabilities = capabilities;
      if (!capabilities?.mock_interview) return;
      byId("studioModeControl")?.classList.remove("hidden");
      let mode = "ielts";
      try { mode = localStorage.getItem(MODE_KEY) || "ielts"; } catch (_error) { /* Default IELTS. */ }
      setProductMode(mode);
      const trigger = byId("studioModeTrigger");
      switcher = window.IELTSCornerMorph?.create({
        trigger, card: byId("studioModeMenu"), body: byId("studioModeMenu")?.querySelector?.(".studio-switch-body"),
        root: byId("studioModeControl"), lift: byId("studioModeControl")?.closest?.(".nav"), anchor: "top-left", palette: syncSwitchPalette,
      }) || null;
      trigger?.addEventListener("click", () => menu(!switcher?.isOpen()));
      trigger?.addEventListener("keydown", (event) => {
        if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); menu(true); }
      });
      byId("studioModeMenu")?.addEventListener("click", (event) => {
        const closer = event.target.closest?.("[data-studio-close]");
        if (closer?.dataset && "studioClose" in closer.dataset) { if (!switcher?.openedByHover()) menu(false, true); return; }
        const item = event.target.closest("[data-studio-mode]");
        if (item) changeMode(item.dataset.studioMode, !event.detail).catch((error) => { data.error = error.message; render(); });
      });
      byId("studioModeMenu")?.addEventListener("keydown", (event) => {
        const items = [...byId("studioModeMenu").querySelectorAll("[role=menuitemradio]")];
        const index = items.indexOf(document.activeElement);
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
          items[next]?.focus({ preventScroll: true });
        }
        if (event.key === "Escape") { event.preventDefault(); menu(false, true); }
        if (event.key === "Tab") menu(false);
      });
      document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (data.editor) { data.editor = null; render(); return; }
        menu(false, !!switcher?.isOpen());
      });
      byId("interviewNav")?.addEventListener("click", (event) => {
        const item = event.target.closest("[data-interview-pane]");
        if (!item) return;
        event.preventDefault?.();
        setPane(item.dataset.interviewPane, { part: item.dataset.interviewPart });
      });
      byId("interviewPanel")?.addEventListener("click", handleAction);
      // Links on the shared home panel carry data-iv-target ("pane" or "pane:part") in interview mode. Capture
      // phase, so the IELTS router never sees them and the href never navigates.
      document.addEventListener("click", (event) => {
        const target = event.target.closest?.("#homePanel [data-iv-target]");
        if (!target || state.productMode !== "interview") return;
        event.preventDefault();
        event.stopPropagation();
        const [pane, part] = target.dataset.ivTarget.split(":");
        if (pane === "corpus" && part) data.corpusTab = part;
        setPane(pane, part && pane === "practice" ? { part } : {});
      }, true);
      window.IELTSInterviewHome?.setSource(homeNumbers);
      byId("interviewPanel")?.addEventListener("input", captureInput);
      byId("interviewPanel")?.addEventListener("change", captureInput);
      window.addEventListener("ielts:ui-language-change", () => { setProductMode(state.productMode); render(); });
    }

    // ---- Requests: one at a time, discarded when the account changes underneath them.
    async function perform(task, apply, { busy = true } = {}) {
      if (data.busy) return;
      if (!state.account.authenticated) {
        promptGuestLogin(copy("登录后保存面试记录与回答。", "Sign in to save interview sessions and answers."), { returnView: "interview" });
        return;
      }
      const generation = epoch;
      const owner = state.account.user?.id;
      requestController = new AbortController();
      data.busy = busy;
      data.error = "";
      data.notice = "";
      render();
      try {
        const result = await task();
        if (generation !== epoch || owner !== state.account.user?.id || !state.account.authenticated) return;
        apply?.(result);
      } catch (error) {
        if (generation === epoch && owner === state.account.user?.id) data.error = error.message || copy("请求失败，请重试。", "Request failed; please retry.");
      } finally {
        if (generation === epoch && owner === state.account.user?.id) { requestController = null; data.busy = false; render(); }
      }
    }

    function request(path, body = null, options = {}) {
      return api(path, body, { ...options, signal: requestController?.signal });
    }

    async function upload(path, form) {
      const token = await ensureCsrfToken();
      const response = await fetch(path, { method: "POST", credentials: "same-origin", headers: token ? { "X-CSRFToken": token } : {}, body: form, signal: requestController?.signal });
      let payload = {};
      try { payload = JSON.parse(await response.text()); } catch (_error) { throw new Error(copy("服务未返回有效数据，请重试。", "Invalid server response; please retry.")); }
      if (!response.ok) throw new Error(payload.error || copy("请求失败，请重试。", "Request failed; please retry."));
      return payload;
    }

    function acceptOverview([bank, history, profile, corpus]) {
      data.questions = bank?.questions || [];
      data.categories = bank?.categories || [];
      if (history) { data.sessions = history.sessions || []; data.sessionsLoaded = true; }
      if (profile) data.profile = profile.profile;
      if (corpus) data.corpus = corpus.entries || [];
      const active = data.sessions.find((item) => item.status === "active" && item.part);
      if (active && !data.current) data.pendingResumeId = active.id;
      window.IELTSInterviewHome?.refresh();
    }

    // Numbers the shared home panel shows in interview mode (interview-home.js).
    function homeNumbers() {
      if (!state.account.authenticated) return null;
      const finished = data.sessions.filter((item) => item.part && item.status !== "active");
      const scored = finished.filter((item) => item.score?.status === "ready");
      const entries = data.corpus || [];
      const kind = (...kinds) => entries.filter((entry) => kinds.includes(entry.kind) && !entry.orphaned);
      return {
        sessions: data.sessionsLoaded ? finished.length : null,
        average: scored.length ? Math.round(scored.reduce((sum, item) => sum + item.score.total, 0) / scored.length) : null,
        last: finished[0]?.created_at || null,
        projectReady: kind("project").filter((entry) => entry.corpus_text).length,
        knowledgeReady: kind("knowledge").filter((entry) => entry.corpus_text).length,
        jdCount: kind("jd_question", "reverse_question").length,
        projects: kind("project").length,
        knowledge: kind("knowledge").length,
      };
    }

    function loadOverview() {
      return perform(() => Promise.all([
        request("/api/interview/questions/"), request("/api/interview/sessions/"),
        request("/api/interview/profile/"), request("/api/interview/corpus/"),
      ]), acceptOverview);
    }

    function loadHistory() {
      return perform(() => request("/api/interview/sessions/"), (payload) => { data.sessions = payload.sessions || []; data.sessionsLoaded = true; });
    }

    // The reports page opens the newest finished session, like the IELTS report rail.
    function openFirstReport() {
      if (!["reports", "report"].includes(data.pane) || selectedReport() || data.busy) return;
      const first = visibleReports()[0];
      if (first) perform(() => request(`/api/interview/sessions/${encodeURIComponent(first.id)}/`), acceptSession);
    }

    function loadCorpus() {
      return perform(() => request("/api/interview/corpus/"), (payload) => { data.corpus = payload.entries || []; });
    }

    function show() {
      if (!state.desktopCapabilities?.mock_interview) return;
      // ?view=interview with no pane chosen yet means the interview home, which is the shared home panel.
      if (data.pane === "home" && state.account.authenticated) { setPane("home"); return; }
      render();
      if (state.account.authenticated && !data.corpus && !data.busy) loadOverview();
    }

    function setPane(pane, { part } = {}) {
      if (!PANES.has(pane) || data.busy) return;
      if (pane === "home") {
        // The interview home is the IELTS home panel itself, with interview copy swapped in.
        data.pane = "home";
        switchView("home", { force: state.view !== "home" });
        syncNav();
        if (!data.corpus && state.account.authenticated) loadOverview();
        else window.IELTSInterviewHome?.refresh();
        return;
      }
      if (data.answer.state === "recording") stopRecorder();
      if (part && PARTS[part]) data.part = part;
      data.pane = pane;
      data.error = "";
      data.editor = null;
      if (pane === "practice") {
        const session = data.current?.session;
        if (!session || session.status !== "active" || session.part !== data.part) {
          if (session?.status !== "active") data.current = null;
          resetAnswer();
        }
      }
      switchView("interview", { force: state.view !== "interview" });
      render();
      if (pane === "reports") loadHistory().then(openFirstReport);
      else if (!data.corpus && state.account.authenticated) loadOverview();
    }

    function acceptSession(payload) {
      data.current = payload;
      const session = payload.session || {};
      if (session.part) data.part = session.part;
      const summary = data.sessions.find((item) => item.id === session.id);
      if (summary) Object.assign(summary, session);
      else if (session.id && data.sessionsLoaded) data.sessions.unshift(session);
      data.pane = session.status === "active" ? "practice" : "report";
    }

    // ---- Corpus helpers
    function corpusEntries(kinds) {
      return (data.corpus || []).filter((entry) => kinds.includes(entry.kind));
    }

    function corpusStats() {
      const entries = data.corpus || [];
      return { total: entries.length, ready: entries.filter((entry) => entry.corpus_text).length };
    }

    function entryFor(id) {
      return (data.corpus || []).find((entry) => entry.id === id) || null;
    }

    // Links inside interview panes (reports empty state).
    const link = (action, content, { cls = "", attrs = "" } = {}) => `<a class="${cls}" href="?view=interview" data-interview-action="${action}" ${attrs}>${content}</a>`;

    // ---- Practice: the IELTS practice panel, with the interviewer in the prompt pane.
    function activeSession() {
      const current = data.current;
      return current?.session?.status === "active" && current.session.part === data.part ? current : null;
    }

    // Stage progress sits where IELTS shows "READY": 自我介绍 1/1 · 项目 0/2 · …
    function stageTrack(session, turns) {
      const plan = session?.plan?.length ? session.plan : [];
      if (!plan.length) return "";
      const currentStage = data.current?.current_turn?.stage;
      return plan.map((stage) => {
        const ofStage = turns.filter((turn) => turn.stage === stage);
        const answered = ofStage.filter((turn) => turn.status !== "pending").length;
        const cls = stage === currentStage ? "is-current" : ofStage.length && answered === ofStage.length ? "is-done" : "";
        return `<b class="iv-stage ${cls}">${esc(stageName(stage))}${ofStage.length ? ` ${answered}/${ofStage.length}` : ""}</b>`;
      }).join('<i aria-hidden="true">·</i>');
    }

    // Launch options use the IELTS P3 launch panel (p3-launch-section / p3-source-option).
    function launchOptions() {
      const part = data.part;
      const projects = corpusEntries(["project"]).filter((entry) => !entry.orphaned);
      const section = (label, body) => `<section class="p3-launch-section"><div class="p3-launch-label">${esc(label)}</div>${body}</section>`;
      const option = (action, active, title, detail, attrs) => button(action, `<strong>${esc(title)}</strong>${detail ? `<small>${esc(detail)}</small>` : ""}`, { cls: `p3-source-option${active ? " active" : ""}`, attrs });
      if ((part === "full" || part === "project") && !projects.length) {
        return section(copy("先上传简历", "Upload your resume first"), `<div class="p3-plan-empty"><span>${esc(copy("完整面试和项目练习会按你简历里的每个项目提问。", "The full interview and project practice ask about each project on your resume."))}</span></div><div class="p3-start-row">${button("go-custom", esc(copy("去上传简历", "Upload resume")), { cls: "p3-generate-button" })}</div>`);
      }
      if (part === "project") {
        const grid = projects.map((entry) => option("toggle-project", data.launch.projectIds.has(entry.id), entry.title || entry.question, entry.corpus_text ? copy("已备讲述稿", "Story ready") : copy("还没写讲述稿", "No story yet"), `data-entry-id="${esc(entry.id)}" aria-pressed="${data.launch.projectIds.has(entry.id)}"`)).join("");
        return section(copy("选择项目（不选则全部）", "Projects (none = all)"), `<div class="p3-source-grid iv-launch-grid" role="group">${grid}</div>`);
      }
      if (part === "knowledge") {
        const topics = [{ id: "", label: copy("综合（技术栈优先）", "Mixed (stack first)") }, ...data.categories]
          .map((item) => option("launch-category", data.launch.category === item.id, item.label, "", `data-category="${esc(item.id)}"`)).join("");
        const counts = [3, 5, 8].map((n) => button("launch-count", esc(copy(`${n} 题`, `${n} questions`)), { cls: `p3-mode-option${data.launch.count === n ? " active" : ""}`, attrs: `data-count="${n}"` })).join("");
        return `${section(copy("方向", "Topic"), `<div class="p3-source-grid iv-launch-grid" role="group">${topics}</div>`)}${section(copy("题量", "Questions"), `<div class="p3-mode-switch p1-mode-switch iv-count-switch" role="group">${counts}</div>`)}`;
      }
      return "";
    }

    // Same length classes as the IELTS prompt card (short / medium / long).
    function promptCard(textValue, extra = "") {
      const size = textValue.length <= 36 ? "short-prompt" : textValue.length <= 90 ? "medium-prompt" : "long-prompt";
      return `<div id="interviewPromptCard" class="prompt-card ${size} ${extra}">${esc(textValue)}</div>`;
    }

    function promptPane(current) {
      if (!current) {
        // With launch options this pane is the IELTS P3 launch panel; otherwise the idle prompt card.
        const part = PARTS[data.part];
        const options = launchOptions();
        if (options) return `<div class="section-label">${esc(copy("开始前", "Before you start"))}</div><div class="iv-launch">${options}</div>`;
        return `<div class="section-label">${esc(copy("面试官", "Interviewer"))}</div>
          ${promptCard(copy(`点击「开始」，${data.part === "reverse" ? "面试官会请你提问。" : "面试官会先请你做自我介绍。"}`, `Press Start. ${pick(part.hint)}`), "iv-prompt-idle")}`;
      }
      const turns = current.turns || [];
      const turn = current.current_turn;
      const previous = [...turns].reverse().find((item) => item.status !== "pending");
      const parentDecision = turn?.parent_turn_id ? turns.find((item) => item.id === turn.parent_turn_id)?.decision : null;
      const tag = turn?.kind === "follow_up"
        ? `<span class="iv-follow-tag ${parentDecision?.action === "probe" ? "is-probe" : ""}">${esc(parentDecision?.action === "probe" ? copy("换个角度 · 摸清边界", "New angle · finding the limit") : copy("追问 · 往深处挖", "Follow-up · going deeper"))}</span>` : "";
      const reply = previous?.stage === "reverse" && previous.reply ? `<div class="iv-reply"><span>${esc(copy("面试官", "Interviewer"))}</span><p>${esc(previous.reply)}</p></div>` : "";
      const failed = previous?.decision?.status === "failed" ? `<p class="iv-prompt-hint">${esc(copy("面试官这次没能追问，已进入下一题。", "The interviewer could not follow up this time; moved on."))}</p>` : "";
      const corpus = turn?.corpus_entry_id ? entryFor(turn.corpus_entry_id) : null;
      const peek = corpus && (corpus.corpus_text || corpus.ai_draft)
        ? `<div class="iv-peek">${button("toggle-peek", esc(data.answer.peek ? copy("收起我的答法", "Hide my answer") : copy("看看我的答法", "Peek at my answer")), { cls: "iv-link" })}${data.answer.peek ? `<div class="iv-peek-body"><small>${esc(corpus.corpus_text ? copy("我的答法", "My answer") : copy("AI 参考", "AI reference"))}</small><p>${esc(corpus.corpus_text || corpus.ai_draft)}</p></div>` : ""}</div>` : "";
      const saveLast = previous && previous.status === "completed" ? `<div class="iv-save-last">${button("save-corpus", esc(copy("把上一题回答存为我的答法", "Save last answer to my corpus")), { cls: "iv-link", attrs: `data-turn-id="${esc(previous.id)}"` })}</div>` : "";
      if (!turn) {
        return `<div class="section-label">${esc(copy("面试官", "Interviewer"))}</div>${reply}${promptCard(copy("今天就到这里，辛苦了。", "That's all for today — thank you."))}<p class="iv-prompt-hint">${esc(copy("点击「完成」生成百分制报告。", "Press Finish to get your 100-point report."))}</p>${saveLast}`;
      }
      return `<div class="section-label">${esc(copy("面试官", "Interviewer"))} · ${esc(stageName(turn.stage))}</div>${failed}${reply}${tag}
        ${promptCard(turn.prompt)}${peek}${saveLast}`;
    }

    function recordControl(current) {
      const turn = current?.current_turn;
      const stateName = data.answer.state;
      let cls = "";
      let title = copy("开始", "Start");
      let hint = copy("面试官会马上提问", "The interviewer will ask right away");
      let action = "start-session";
      let disabled = false;
      if (data.busy && !current) { cls = "loading"; title = copy("准备中", "Preparing"); hint = copy("正在生成面试计划…", "Building the interview plan…"); disabled = true; }
      else if (current && !turn) { cls = "turn"; title = copy("完成", "Finish"); hint = copy("生成百分制报告", "Get the 100-point report"); action = "finish"; }
      else if (current) {
        action = "record-start";
        title = copy("回答", "Answer"); hint = copy("点击开始录音", "Tap to start recording"); cls = "turn";
        if (stateName === "recording") { cls = "recording"; title = copy("结束", "Stop"); hint = copy("再次点击结束录音", "Tap again to stop"); action = "record-stop"; }
        if (stateName === "processing") { cls = "processing"; title = copy("转写中", "Transcribing"); hint = copy("正在把录音转成文字…", "Turning your recording into text…"); disabled = true; }
        if (stateName === "review") { title = copy("重录", "Re-record"); hint = copy("或修改下方文字后提交", "Or edit the text below and submit"); }
        if (stateName === "thinking") { cls = "examiner"; title = copy("面试官", "Interviewer"); hint = copy("正在判断下一步…", "Deciding what to ask next…"); disabled = true; }
      }
      return `<button type="button" id="interviewRecordControl" class="record-control ${cls}" data-interview-action="${action}" ${disabled || (data.busy && stateName !== "thinking") ? "disabled" : ""}><span class="iv-record-icon" aria-hidden="true"></span><strong>${esc(title)}</strong><small>${esc(hint)}</small>${cls === "examiner" || cls === "processing" || cls === "loading" ? '<div class="analyzing-dots"><span></span><span></span><span></span></div>' : ""}</button>`;
    }

    function recorderPane(current) {
      const turn = current?.current_turn;
      const showText = turn && (data.answer.state === "review" || data.answer.typing);
      const status = data.answer.error ? `<div class="record-status iv-record-error" role="alert">${esc(data.answer.error)}</div>`
        : `<div class="record-status">${esc(!current ? copy("麦克风会在开始录音时请求权限。", "The microphone is requested when you start recording.")
          : data.answer.state === "review" ? copy("转写完成，可以修改后提交。", "Transcribed — edit if needed, then submit.")
          : data.answer.typing ? copy("打字作答：写好后提交。", "Typing: submit when ready.")
          : turn ? copy("录音结束后自动转写；也可以改为打字。", "Recordings are transcribed automatically; you can also type.") : "")}</div>`;
      const editor = showText ? `<div class="iv-answer-box"><textarea id="interviewAnswer" rows="6" maxlength="6000" data-interview-field="answer" placeholder="${esc(copy("先说结论，再讲背景、你做了什么、结果和取舍……", "Conclusion first, then context, what you did, results and trade-offs…"))}">${esc(data.answer.text)}</textarea>
          <div class="iv-answer-foot"><span id="interviewAnswerCount" class="iv-count">${data.answer.text.length} / 6000</span><span class="iv-dock-spacer"></span>${quiet("skip", copy("跳过本题", "Skip"))}${solid("submit-answer", copy("提交回答", "Submit"))}</div></div>`
        : turn && data.answer.state === "idle" ? `<div class="iv-answer-alt">${quiet("type-answer", copy("改为打字作答", "Type instead"))}${quiet("skip", copy("跳过本题", "Skip"))}</div>` : "";
      return `<div class="section-label">${esc(copy("你的回答", "Your answer"))}</div>
        <div class="inline-timer" id="interviewTimer">${timerText()}</div>
        <div class="record-row">${recordControl(current)}${current ? `<button type="button" class="icon-exit-button" data-interview-action="abort" aria-label="${esc(copy("结束本场", "End session"))}" title="${esc(copy("结束本场（保留已答内容）", "End session (keeps answers)"))}"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M7 7l10 10M17 7L7 17"></path></svg></button>` : ""}</div>
        <div class="recorder-status-zone">${status}</div>${editor}`;
    }

    function progressTitle(current, done) {
      if (!current) return copy("准备就绪", "Ready");
      const turn = current.current_turn;
      if (!turn) return copy("· 收尾", "· Wrap-up");
      if (data.part === "full") return `· ${stageName(turn.stage)}`;
      return copy(`· 第 ${done + 1} 题`, `· Question ${done + 1}`);
    }

    // Same shell as #practicePanel (exam-status, phase meter, practice grid); the ids are aliased
    // to the IELTS ones by scripts/alias_ielts_styles.py.
    function practice() {
      const current = activeSession();
      const turns = current?.turns || [];
      const done = turns.filter((turn) => turn.status !== "pending").length;
      const pressure = (current?.session?.intensity || data.intensity) === "pressure";
      const tab = PARTS[data.part].corpus;
      const tabLabel = CORPUS_TABS.find((item) => item.id === tab);
      const progress = turns.length ? Math.round((done / turns.length) * 100) : 0;
      return `<section id="interviewPractice" class="panel practice-panel">
          <div class="exam-status">
            <div id="interviewStatusText"><strong id="interviewProgress">${esc(partName(data.part))} ${esc(progressTitle(current, done))}</strong><span id="interviewPhase">${current ? stageTrack(current.session, turns) || `${done} / ${turns.length}` : "Ready"}</span></div>
            <div class="exam-actions">
              <span class="p1-mode-help">${esc(copy("面试节奏", "Pace"))}</span>
              <div class="p3-mode-switch p1-mode-switch${pressure ? " high-intensity" : ""}" role="group" aria-label="${esc(copy("面试强度", "Intensity"))}">
                ${button("intensity", esc(copy("标准模式", "Standard")), { cls: `p3-mode-option${pressure ? "" : " active"}`, attrs: 'data-intensity="standard"', disabled: !!current })}
                ${button("intensity", esc(copy("追问压力", "Pressure")), { cls: `p3-mode-option${pressure ? " active" : ""}`, attrs: 'data-intensity="pressure"', disabled: !!current })}
              </div>
              <button type="button" class="p1-corpus-entry" data-interview-action="open-corpus" data-tab="${tab}"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg><span>${esc(copy(`我的${tabLabel.zh}语料`, `My ${tabLabel.en.toLowerCase()} corpus`))}</span></button>
            </div>
          </div>
          <div class="phase-meter"><span style="width:${progress}%"></span></div>
          <div id="interviewPracticeGrid" class="practice-grid">
            <article id="interviewPromptPane" class="prompt-pane">${promptPane(current)}</article>
            <article id="interviewRecorderPane" class="recorder-pane">${recorderPane(current)}</article>
          </div>
        </section>`;
    }

    // ---- Reports: the IELTS speaking-report layout (#historyPanel) — a horizontal rail of report
    // cards, then the score summary, overall review and per-question table for the selected session.
    const REPORT_TAGS = { full: ["mock", "MOCK"], project: ["p2", "PROJ"], knowledge: ["p1", "STACK"], reverse: ["p3", "ASK"] };
    const REPORT_FILTERS = ["all", "full", "project", "knowledge", "reverse"];
    const RAIL_ICON = (path) => `<svg aria-hidden="true" viewBox="0 0 24 24"><path d="${path}"></path></svg>`;

    function selectedReport() {
      const current = data.current;
      return current?.session && current.session.status !== "active" ? current : null;
    }

    function visibleReports() {
      // Before the list loads (straight after finishing a session), the rail shows just that session.
      const sessions = data.sessionsLoaded ? data.sessions : [selectedReport()?.session].filter(Boolean);
      return sessions.filter((session) => session.status !== "active" && (data.reportFilter === "all" || session.part === data.reportFilter));
    }

    function reportFilterLabel(filter) {
      return filter === "all" ? copy("全部", "All") : partName(filter);
    }

    function reportRail(items, selectedId) {
      const cards = items.map((session) => {
        const [tag, label] = REPORT_TAGS[session.part] || ["", "TEXT"];
        const score = session.score;
        const scoring = data.busy && selectedId === session.id && session.status === "completed" && score?.status !== "ready";
        const band = scoring ? ["is-scoring", esc(copy("评分中", "Scoring"))]
          : score?.status === "ready" ? ["", `<em class="history-item-band-label">${esc(copy("得分", "Score"))}</em><b class="history-item-band-value">${esc(score.total)}</b>`]
          : score?.status === "failed" ? ["is-failed", esc(copy("评分失败", "Failed"))]
          : ["is-unscored", esc(session.status === "completed" ? copy("未评分", "Unscored") : copy("已结束", "Ended"))];
        return `<div class="history-item-wrap"><button type="button" class="history-item tone-${tag || "neutral"}${selectedId === session.id ? " active" : ""}" data-interview-action="open-session" data-session-id="${esc(session.id)}" ${data.busy ? "disabled" : ""}>
            <div class="history-item-top"><span class="history-item-tag ${tag}">${label}</span>${session.intensity === "pressure" ? `<span class="report-sample-badge">${esc(copy("压力", "Pressure"))}</span>` : ""}<span class="history-item-band ${band[0]}">${band[1]}</span></div>
            <strong class="history-item-title">${esc(session.title || partName(session.part))}</strong>
            <small class="history-item-time">${esc(dateText(session.created_at))}</small>
          </button></div>`;
      }).join("");
      const empty = `<div class="history-empty-state report-empty-rail-card"><span class="report-empty-rail-icon" aria-hidden="true">${RAIL_ICON("M7 8h10M7 12h6M5 4h14a2 2 0 0 1 2 2v11.5a2 2 0 0 1-2 2H8l-5 3V6a2 2 0 0 1 2-2Z")}</span>
          <strong>${esc(data.reportFilter === "all" ? copy("还没有面试报告", "No reports yet") : copy("这个分类暂无报告", "Nothing in this filter"))}</strong>
          <small>${esc(data.reportFilter === "all" ? copy("练完一场面试，报告会出现在这里。", "Finish a session to see its report here.") : copy("换个分类看看，或练一场对应的面试。", "Try another filter or practise this part."))}</small></div>`;
      const loading = `<div class="report-rail-loading-card" role="status" aria-live="polite"><span class="spinner" aria-hidden="true"></span><strong>${esc(copy("正在加载面试报告", "Loading reports"))}</strong><small>${esc(copy("正在读取练习记录。", "Reading your sessions."))}</small></div>`;
      const options = REPORT_FILTERS.map((filter) => `<button type="button" role="option" aria-selected="${data.reportFilter === filter}" data-interview-action="report-filter" data-filter="${filter}">${esc(reportFilterLabel(filter))}</button>`).join("");
      return `<div class="history-rail-shell speaking-report-rail-shell at-start">
          <div class="history-rail-head">
            <div><strong>Reports</strong><span>${esc(copy("横向滑动", "Swipe"))}</span></div>
            <div class="report-filter speaking-report-filter report-filter-compact">
              <button type="button" class="report-filter-button" data-interview-action="report-filter-toggle" aria-haspopup="listbox" aria-expanded="${!!data.reportFilterOpen}"><span>${esc(reportFilterLabel(data.reportFilter))}</span>${RAIL_ICON("m7 10 5 5 5-5")}</button>
              <div class="report-filter-menu${data.reportFilterOpen ? "" : " hidden"}" role="listbox" aria-label="${esc(copy("筛选面试报告", "Filter reports"))}">${options}</div>
            </div>
            <div class="history-rail-actions" aria-label="${esc(copy("报告滚动", "Report rail controls"))}">
              <button type="button" class="history-rail-nav" data-interview-action="rail-step" data-step="-1" aria-label="${esc(copy("上一组", "Previous"))}">${RAIL_ICON("m15 18-6-6 6-6")}</button>
              <button type="button" class="history-rail-nav" data-interview-action="rail-step" data-step="1" aria-label="${esc(copy("下一组", "Next"))}">${RAIL_ICON("m9 18 6-6-6-6")}</button>
            </div>
          </div>
          <div class="history-rail-window"><div id="interviewReportList" class="history-list">${cards || (data.sessionsLoaded ? empty : loading)}</div></div>
        </div>`;
    }

    function emptyDetail() {
      const none = data.sessionsLoaded && !data.busy && !visibleReports().length;
      if (!none) return `<div class="page-center-loading" role="status" aria-live="polite"><div><span class="spinner" aria-hidden="true"></span><div><strong>${esc(copy("正在加载面试报告", "Loading the report"))}</strong><span>${esc(copy("正在读取报告详情。", "Reading the report details."))}</span></div></div></div>`;
      const all = data.reportFilter === "all";
      return `<section class="detail-card report-empty-detail-card">
          <div class="report-empty-orbit" aria-hidden="true"><span></span><svg viewBox="0 0 24 24"><path d="M8 9h8M8 13h5"></path><path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-7l-5 3v-3H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"></path></svg></div>
          <div class="report-empty-copy"><span class="section-label">Interview Reports</span>
            <h2>${esc(all ? copy("还没有面试报告", "No interview reports yet") : copy("这个分类下还没有报告", "No reports in this filter"))}</h2>
            <p>${esc(all ? copy("练完一场完整面试或分段练习后，这里会沉淀百分制评分、能力边界和逐题点评。", "Finish a full interview or a single part to get a 100-point score, your boundary and per-question notes.") : copy("当前筛选没有匹配的报告。可以切换到全部，或者练一场对应的面试。", "Nothing matches this filter. Show all, or practise this part."))}</p></div>
          <div class="report-empty-actions">${all
            ? `${link("go-practice", esc(copy("开始完整面试", "Start a full interview")), { cls: "report-empty-primary", attrs: 'data-part="full"' })}${link("go-practice", esc(copy("练一个项目", "Practise a project")), { cls: "report-empty-secondary", attrs: 'data-part="project"' })}`
            : `<button type="button" class="report-empty-primary" data-interview-action="report-filter" data-filter="all">${esc(copy("查看全部报告", "Show all reports"))}</button>${link("go-practice", esc(copy("去练一场", "Practise now")), { cls: "report-empty-secondary", attrs: `data-part="${esc(data.reportFilter)}"` })}`}</div>
        </section>`;
    }

    function scoreSummary(session, turns) {
      const score = session.score;
      const ready = score?.status === "ready";
      const answered = turns.filter((turn) => turn.status === "completed").length;
      const cells = ready
        ? score.dimensions.map((dim) => `<div class="score-cell"><span>${esc(dim.label)}<small>${esc(copy(`满分 ${dim.max}`, `of ${dim.max}`))}</small></span><strong>${esc(dim.score)}</strong></div>`).join("")
        : "";
      const pending = score?.status === "failed"
        ? `<div class="iv-report-pending"><p role="alert">${esc(score.error || copy("评分生成失败。", "Scoring failed."))}</p>${solid("score", copy("重新生成百分制报告", "Retry scoring"))}</div>`
        : session.status === "completed"
          ? `<div class="iv-report-pending"><p>${esc(data.busy ? copy("正在生成百分制报告…", "Scoring…") : copy("这一场还没有评分。", "This session is not scored yet."))}</p>${data.busy ? "" : solid("score", copy("生成百分制报告", "Get the 100-point report"))}</div>`
          : `<div class="iv-report-pending"><p>${esc(copy("这一场提前结束了，只保留了已答内容，不生成评分。", "This session ended early; answers are kept but not scored."))}</p></div>`;
      return `<div class="detail-card speaking-score-summary-card${ready ? " speaking-report-ready-card" : ""}" data-report-status="${esc(score?.status || "none")}">
          <div class="speaking-score-summary-head">
            <div class="speaking-score-summary-copy">
              <span class="section-label">${esc(copy("模拟面试 · 百分制估分", "Mock interview · 100-point estimate"))}</span>
              <h2>${esc(partName(session.part) || session.title)} ${esc(copy("报告", "report"))}</h2>
              <p class="muted">${esc(session.title)} · ${esc(copy(`${answered} 题已答`, `${answered} answered`))} · ${esc(session.intensity === "pressure" ? copy("追问压力", "Pressure") : copy("标准模式", "Standard"))} · ${esc(dateText(session.created_at))}</p>
            </div>
            <div class="speaking-score-summary-side">
              ${button("go-practice", esc(copy("再练一场", "Practice again")), { cls: "report-export-btn", attrs: `data-part="${esc(session.part || "full")}"` })}
              <div class="speaking-score-summary-band"><span>Overall</span><strong>${ready ? `${esc(score.total)} / 100` : "—"}</strong></div>
            </div>
          </div>
          ${ready ? `<div class="score-row compact speaking-score-summary-grid iv-score-grid">${cells}</div>` : pending}
        </div>`;
    }

    function overallReview(score) {
      if (score?.status !== "ready") return "";
      const body = `${score.summary ? `<h4>${esc(copy("总体点评", "Overall"))}</h4><p>${esc(score.summary)}</p>` : ""}
        ${score.dimensions?.some((dim) => dim.evidence) ? `<h4>${esc(copy("评分依据", "Why these scores"))}</h4><ul>${score.dimensions.filter((dim) => dim.evidence).map((dim) => `<li><strong>${esc(dim.label)} ${esc(dim.score)}/${esc(dim.max)}</strong> ${esc(dim.evidence)}</li>`).join("")}</ul>` : ""}
        ${score.boundary ? `<h4>${esc(copy("能力边界", "Knowledge boundary"))}</h4><p>${esc(score.boundary)}</p>` : ""}
        ${score.next_steps?.length ? `<h4>${esc(copy("下一步练习", "Next steps"))}</h4><ul>${score.next_steps.map((step) => `<li>${esc(step)}</li>`).join("")}</ul>` : ""}`;
      return `<div class="detail-card overall-review-card"><div class="overall-review-head"><h3>Overall Review & Practice Focus</h3></div><div class="overall-review-content">${body}</div></div>`;
    }

    function turnTable(turns, score) {
      const comments = Object.fromEntries((score?.per_turn || []).map((item) => [item.turn_id, item.comment]));
      const counters = {};
      const rows = turns.filter((turn) => turn.status !== "pending").map((turn) => {
        const follow = turn.kind === "follow_up";
        if (!follow) counters[turn.stage] = (counters[turn.stage] || 0) + 1;
        const signal = turn.decision?.signal ? `<em class="iv-signal is-${esc(turn.decision.signal)}">${esc(pick(SIGNALS[turn.decision.signal] || SIGNALS.adequate))}</em>` : "";
        const save = turn.status === "completed"
          ? `<div class="question-cell-actions"><button type="button" class="ghost corpus-edit-button" data-interview-action="save-corpus" data-turn-id="${esc(turn.id)}" ${data.busy ? "disabled" : ""}><svg class="corpus-edit-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h11M4 12h7M4 17h5"></path><path d="m15.5 15.5 4-4a1.4 1.4 0 0 1 2 2l-4 4-2.6.6z"></path></svg><span class="corpus-edit-label">${esc(copy("存为我的答法", "Save to corpus"))}</span></button></div>` : "";
        const notes = [
          turn.reply ? `<p><strong>${esc(copy("面试官回答", "Interviewer"))}</strong>${esc(turn.reply)}</p>` : "",
          turn.decision?.evidence ? `<p>${signal}${esc(turn.decision.evidence)}</p>` : signal ? `<p>${signal}</p>` : "",
          turn.decision?.boundary ? `<p class="muted">${esc(copy("边界：", "Boundary: "))}${esc(turn.decision.boundary)}</p>` : "",
          comments[turn.id] ? `<p>${esc(comments[turn.id])}</p>` : "",
        ].join("");
        return `<tbody class="turn-report-group p1-p3-turn-group"><tr class="p1-p3-content-row">
            <td><div class="question-header"><strong>${esc(stageName(turn.stage) || copy("问题", "Question"))}${follow ? "" : ` ${counters[turn.stage]}`}</strong>${follow ? `<span class="follow-up-pill">${esc(copy("追问", "Follow-up"))}</span>` : ""}</div><p>${esc(turn.prompt)}</p>${save}</td>
            <td>${turn.answer ? `${turn.answer_source === "voice" ? `<span class="iv-source-pill">${esc(copy("语音转写", "Voice"))}</span>` : ""}<p>${esc(turn.answer)}</p>` : `<p class="muted report-empty-answer">${esc(turn.status === "skipped" ? copy("已跳过", "Skipped") : copy("为空", "Empty"))}</p>`}</td>
            <td>${notes || `<p class="muted">${esc(copy("没有点评。", "No notes."))}</p>`}</td>
          </tr></tbody>`;
      }).join("");
      if (!rows) return "";
      return `<div class="detail-card turn-report-card"><div class="turn-report-wrap"><table class="turn-report-table p1-p3-report-table">
          <thead><tr><th>${esc(copy("问题", "Question"))}</th><th>${esc(copy("你的回答", "Your answer"))}</th><th class="band7-head">${esc(copy("面试官判断", "Interviewer notes"))}</th></tr></thead>${rows}</table></div></div>`;
    }

    function reportDetail(current) {
      const { session, turns = [] } = current;
      return `${scoreSummary(session, turns)}${overallReview(session.score)}
        ${turnTable(turns, session.score)}
        <p class="iv-voice-note"><span class="iv-dot" aria-hidden="true"></span>${esc(session.score?.limitations || copy("百分制由 AI 根据本次文字回答（含语音转写稿）估计，不评估发音，也不代表真实招聘结果。", "The score is an AI estimate from this session's text answers; no pronunciation, and not a hiring decision."))}</p>`;
    }

    function reportsPane() {
      const selected = selectedReport();
      const items = visibleReports();
      return `<section id="interviewReports" class="panel speaking-reports-panel">
          ${reportRail(items, selected?.session.id)}
          <article id="interviewReportDetail" class="detail-panel">${selected ? reportDetail(selected) : emptyDetail()}</article>
        </section>`;
    }

    // Like updateReportRailState in app.js: fade the rail edges and disable the arrows at the ends.
    function syncReportRail() {
      const list = byId("interviewReportList");
      const shell = list?.closest?.(".history-rail-shell");
      if (!list || !shell) return;
      const maxScroll = Math.max(0, list.scrollWidth - list.clientWidth);
      const atStart = list.scrollLeft <= 2;
      const atEnd = maxScroll <= 2 || list.scrollLeft >= maxScroll - 2;
      shell.classList.toggle("at-start", atStart);
      shell.classList.toggle("at-end", atEnd);
      const navs = shell.querySelectorAll(".history-rail-nav");
      navs[0]?.toggleAttribute("disabled", atStart);
      navs[1]?.toggleAttribute("disabled", atEnd);
    }

    function mountReportRail() {
      const list = byId("interviewReportList");
      if (!list) return;
      list.scrollLeft = data.railScroll || 0;
      const active = list.querySelector(".history-item.active");
      if (active && (active.offsetLeft < list.scrollLeft || active.offsetLeft + active.offsetWidth > list.scrollLeft + list.clientWidth)) {
        list.scrollLeft = Math.max(0, active.offsetLeft - 12);
      }
      list.addEventListener("scroll", () => { data.railScroll = list.scrollLeft; syncReportRail(); }, { passive: true });
      syncReportRail();
    }

    // ---- Corpus library: grouped cards like "我的 P1 语料库".
    function corpusGroups(tabId) {
      const tab = CORPUS_TABS.find((item) => item.id === tabId) || CORPUS_TABS[0];
      const entries = corpusEntries(tab.kinds);
      if (tabId === "project") {
        return entries.filter((entry) => entry.kind === "project").map((project) => ({
          title: project.title || project.question, orphaned: project.orphaned, project,
          rows: [project, ...entries.filter((entry) => entry.parent_id === project.id)],
        }));
      }
      if (tabId === "story") {
        return [{ title: copy("自我介绍", "Self intro"), rows: entries.filter((e) => e.kind === "self_intro"), kind: "self_intro" },
                { title: copy("奖项与竞赛", "Awards"), rows: entries.filter((e) => e.kind === "award"), kind: "award" }];
      }
      if (tabId === "jd") {
        return [{ title: copy("岗位题", "Role questions"), rows: entries.filter((e) => e.kind === "jd_question"), kind: "jd_question" },
                { title: copy("反问环节", "Questions to ask"), rows: entries.filter((e) => e.kind === "reverse_question"), kind: "reverse_question" }];
      }
      const groups = new Map();
      entries.forEach((entry) => {
        const key = entry.group || copy("自定义", "Custom");
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(entry);
      });
      return [...groups].map(([title, rows]) => ({ title, rows, kind: "knowledge", group: title }));
    }

    function corpusPane() {
      if (!data.corpus) return `<p class="iv-empty">${esc(copy("正在载入语料…", "Loading corpus…"))}</p>`;
      const stats = corpusStats();
      const tab = data.corpusTab;
      const groups = corpusGroups(tab);
      const question = (entry, index) => {
        const ref = entry.id ? `data-entry-id="${esc(entry.id)}"` : `data-source-key="${esc(entry.source_key)}"`;
        const lead = entry.kind === "project" ? copy("讲", "S") : entry.kind === "project_followup" ? copy("追", "F") : `Q${index + 1}`;
        const textValue = entry.kind === "project" ? copy("项目讲述稿", "Project story") : entry.question;
        return `<button type="button" class="${entry.corpus_text ? "has-corpus" : ""}" data-interview-action="edit-entry" ${ref}><strong>${esc(lead)}</strong><span>${esc(textValue)}</span></button>`;
      };
      const cards = groups.map((group) => {
        const ready = group.rows.filter((row) => row.corpus_text).length;
        const progress = group.rows.length ? Math.round((ready / group.rows.length) * 100) : 0;
        const add = group.project ? button("new-entry", `＋ ${esc(copy("追问", "Follow-up"))}`, { cls: "iv-link", attrs: `data-kind="project_followup" data-parent="${esc(group.project.id)}"` })
          : group.kind ? button("new-entry", `＋ ${esc(copy("添加", "Add"))}`, { cls: "iv-link", attrs: `data-kind="${esc(group.kind)}" data-group="${esc(group.group || "")}"` }) : "";
        return `<article class="p1-topic-card is-complete-list" data-p1-progress="${progress}">
            <header class="p1-topic-export-header"><div><h3>${esc(group.title)}</h3>${group.orphaned ? `<small class="iv-orphan">${esc(copy("简历中已移除", "Removed from resume"))}</small>` : ""}</div>
              <div class="p1-topic-card-actions"><span class="p1-topic-count">${ready}/${group.rows.length}</span></div></header>
            <div class="p1-topic-progress" data-progress="${progress}"><span style="width: ${progress}%"></span></div>
            <div class="p1-topic-question-list">${group.rows.map(question).join("") || `<p class="iv-empty">${esc(copy("还没有内容。", "Nothing here yet."))}</p>`}</div>
            <footer class="iv-topic-foot">${add}</footer>
          </article>`;
      }).join("");
      const empty = tab === "project" && !groups.length
        ? `<div class="iv-empty-card"><p>${esc(copy("上传简历后，每个项目会自动生成一份讲述稿和预判追问。", "Upload your resume to get a story and likely follow-ups for every project."))}</p>${solid("go-custom", copy("上传简历", "Upload resume"))}</div>`
        : tab === "jd" && !groups.some((group) => group.rows.length)
          ? `<div class="iv-empty-card"><p>${esc(copy("粘贴目标岗位的 JD，会生成岗位题和反问环节要问的问题。", "Paste a job description to get role questions and questions to ask."))}</p>${solid("go-custom", copy("添加 JD", "Add a JD"), { attrs: 'data-side="jd"' })}</div>` : "";
      const newKind = tab === "jd" ? "reverse_question" : tab === "story" ? "self_intro" : tab === "project" ? "project" : "knowledge";
      return `<section id="interviewCorpus" class="p1-corpus-panel" aria-label="${esc(copy("面试语料库", "Interview corpus"))}">
          <div class="p1-corpus-shell">
            <header class="p1-corpus-head">
              <div class="p1-corpus-head-copy"><span class="corpus-page-kicker">Interview Library</span><h2>${esc(copy("面试语料库", "Interview corpus"))}</h2></div>
              <div class="corpus-head-actions">
                <button type="button" class="agent-assistant-trigger corpus-agent-button" data-interview-action="new-entry" data-kind="${newKind}"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"></path></svg><span>${esc(copy("自定义题", "Custom question"))}</span></button>
                <span class="corpus-page-stat">${esc(copy(`${stats.total} 条 · 已保存 ${stats.ready}`, `${stats.total} items · ${stats.ready} saved`))}</span>
              </div>
            </header>
            <div class="iv-tabs" role="tablist">${CORPUS_TABS.map((item) => button("corpus-tab", `${esc(copy(item.zh, item.en))}<sup>${corpusEntries(item.kinds).length}</sup>`, { cls: `iv-chip${item.id === tab ? " is-on" : ""}`, attrs: `role="tab" aria-selected="${item.id === tab}" data-tab="${item.id}"` })).join("")}</div>
            ${empty || `<div class="p1-corpus-topics">${cards}</div>`}
          </div>
        </section>`;
    }

    // Same shell as the IELTS P1 corpus dialog: header with save, "my answer", then the AI reference box.
    function editorModal() {
      const editor = data.editor;
      if (!editor) return "";
      const entry = editor.entry;
      const editableQuestion = entry.source !== "curated";
      return `<div class="p1-corpus-dialog iv-corpus-dialog" role="dialog" aria-modal="true" aria-label="${esc(copy("编辑语料", "Edit corpus entry"))}">
        <div class="iv-dialog-backdrop" data-interview-action="close-editor"></div>
        <div class="p1-corpus-dialog-card">
          <header class="p1-corpus-dialog-head">
            <div><span>${esc(pick(KIND_LABELS[entry.kind] || KIND_LABELS.knowledge))} · ${esc(pick(SOURCE_LABELS[entry.source] || SOURCE_LABELS.custom))}${entry.title ? ` · ${esc(entry.title)}` : ""}</span>
              <div class="corpus-dialog-title-line">${editableQuestion ? `<textarea class="iv-question-input" rows="1" maxlength="1500" data-interview-field="editor-question" aria-label="${esc(copy("题目", "Question"))}" placeholder="${esc(copy("写下题目……", "Write the question…"))}">${esc(editor.question)}</textarea>` : `<h3>${esc(editor.question)}</h3>`}</div>
              ${entry.summary ? `<p class="iv-note">${esc(entry.summary)}</p>` : ""}</div>
            <div class="iv-dialog-actions">${button("close-editor", "×", { cls: "iv-icon-btn", attrs: `aria-label="${esc(copy("关闭", "Close"))}"` })}${button("save-entry", esc(copy("保存语料", "Save")), { cls: "iv-save-entry" })}</div>
          </header>
          <label class="p1-corpus-label" for="interviewCorpusText">${esc(copy("我的语料", "My answer"))}</label>
          <textarea id="interviewCorpusText" class="p1-corpus-textarea" spellcheck="true" data-interview-field="editor-text" placeholder="${esc(copy("用你自己的话写，面试时照着这个思路讲。", "Write it in your own words — the way you'd say it."))}">${esc(editor.text)}</textarea>
          <div class="p1-corpus-ai-box">
            <div class="p1-corpus-ai-head"><strong>${esc(copy("AI 参考", "AI reference"))}</strong>
              <span class="iv-ai-tools">${entry.ai_draft ? button("adopt-draft", '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 4v12M7 11l5 5 5-5M5 20h14"></path></svg>', { attrs: `title="${esc(copy("采用到我的语料", "Use as my answer"))}" aria-label="${esc(copy("采用到我的语料", "Use as my answer"))}"` }) : ""}${entry.id ? button("draft-entry", '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M20 11a8 8 0 0 0-14.9-4M4 4v4h4M4 13a8 8 0 0 0 14.9 4M20 20v-4h-4"></path></svg>', { attrs: `title="${esc(entry.ai_draft ? copy("重新生成 AI 参考", "Regenerate") : copy("生成 AI 参考", "Generate"))}" aria-label="${esc(entry.ai_draft ? copy("重新生成 AI 参考", "Regenerate") : copy("生成 AI 参考", "Generate"))}"` }) : ""}</span></div>
            <div class="iv-draft-text">${entry.ai_draft ? esc(entry.ai_draft) : `<span class="iv-muted">${esc(copy("还没有 AI 参考。", "No AI reference yet."))}</span>`}</div>
          </div>
          <div class="p1-corpus-dialog-actions">${entry.id && entry.source !== "curated" ? quiet("delete-entry", copy("删除这条语料", "Delete"), { cls: "iv-danger" }) : ""}</div>
        </div>
      </div>`;
    }

    // ---- Tailored: resume | JD switch.
    // ---- Resume / JD: the IELTS daily-writing page (#writingPanel) — prompt card + editor on the
    // left, the result card with counts and the submit row on the right; #writingPanel rules are
    // aliased to #interviewCustom.
    function customPane() {
      const side = data.customSide;
      const resume = side === "resume";
      const profile = data.profile || { resume: {}, jd: {} };
      const modules = profile.resume?.modules || [];
      const count = (kind) => modules.filter((item) => item.kind === kind).length;
      const text = resume ? data.resumeText : data.jdText;
      const updated = resume ? profile.resume?.updated_at : profile.jd?.updated_at;
      const switcher = `<div class="writing-task-switch iv-custom-switch" data-active-task="${resume ? "task1" : "task2"}" role="tablist" aria-label="${esc(copy("简历或 JD", "Resume or JD"))}">
          ${button("custom-side", esc(copy("简历", "Resume")), { cls: `writing-task-option${resume ? " active" : ""}`, attrs: `role="tab" aria-selected="${resume}" data-side="resume"` })}
          ${button("custom-side", "JD", { cls: `writing-task-option${resume ? "" : " active"}`, attrs: `role="tab" aria-selected="${!resume}" data-side="jd"` })}
        </div>`;
      const prompt = resume
        ? `<div class="writing-prompt-card"><div><span class="writing-pill">${esc(copy("简历", "Resume"))}</span><h2>${esc(copy("把简历拆成可练的语料", "Turn your resume into practice material"))}</h2></div>
            <p>${esc(copy("拆成：自我介绍、每个项目的讲述稿与预判追问、技术栈知识点、奖项。重新拆分不会覆盖你已经改写的答法。", "Splits into intro, a story and likely follow-ups per project, stack questions and awards. Re-splitting never overwrites what you wrote."))}</p></div>`
        : `<div class="writing-prompt-card"><div><span class="writing-pill">JD</span><h2>${esc(copy("按目标岗位出题", "Questions for your target role"))}</h2></div>
            <p>${esc(copy("生成岗位相关题和反问环节的问题，都会进入语料库，在「反问环节」里练。", "Creates role questions and questions to ask; both go to your corpus for the questions round."))}</p></div>`;
      const hint = resume
        ? `<div class="writing-frame-hint"><label class="writing-frame-cmd iv-file-pick"><input type="file" accept="application/pdf,.pdf" data-interview-field="file">${esc(data.file?.name || copy("选择 PDF 简历", "Choose a PDF resume"))}</label><span class="writing-frame-hint-dot">·</span><span class="writing-frame-hint-lead">${esc(copy("最多 2 MB，扫描件请粘贴文字", "Up to 2 MB; paste text for scans"))}</span></div>`
        : `<div class="writing-frame-hint"><span class="writing-frame-hint-lead">${esc(copy("内容会发送到你选择的 AI 服务", "Sent to your selected AI service"))}</span></div>`;
      const editor = `<article class="writing-editor-card">${prompt}
          <div class="writing-answer-header"><label class="writing-answer-label" for="interviewCustomText">${esc(resume ? copy("简历文字", "Resume text") : copy("岗位描述", "Job description"))}</label>${hint}</div>
          <textarea id="interviewCustomText" class="writing-answer" maxlength="${resume ? 24000 : 12000}" data-interview-field="${resume ? "resumeText" : "jdText"}" placeholder="${esc(resume ? copy("或者把简历全文粘贴在这里……", "Or paste the full resume text here…") : copy("粘贴目标岗位的职责与要求……", "Paste the role's responsibilities and requirements…"))}">${esc(text)}</textarea>
        </article>`;
      const stats = resume
        ? [[copy("项目", "Projects"), count("project")], [copy("技术栈", "Stack"), count("tech_stack")], [copy("奖项", "Awards"), count("award")]]
        : [[copy("核心要求", "Requirements"), (profile.jd?.summary?.requirements || []).length], [copy("岗位题", "Role Qs"), corpusEntries(["jd_question"]).length], [copy("反问", "To ask"), corpusEntries(["reverse_question"]).length]];
      const detail = resume
        ? (modules.some((item) => item.kind === "project") ? `<ul class="iv-custom-list">${modules.filter((item) => item.kind === "project").map((item) => `<li>${esc(item.title)}</li>`).join("")}</ul>` : "")
        : (profile.jd?.summary?.role ? `<p class="iv-custom-role">${esc(profile.jd.summary.role)}</p><ul class="iv-custom-list">${(profile.jd.summary.requirements || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul>` : "");
      const empty = `<p class="iv-custom-empty">${esc(resume ? copy("拆分完成后，这里会列出识别到的项目和模块。", "Projects and modules appear here after splitting.") : copy("生成后，这里会显示岗位方向和核心要求。", "The role and its core requirements appear here."))}</p>`;
      const result = `<aside class="writing-result-card">
          <div class="writing-card-head"><div><h2>${esc(updated ? (resume ? copy("已拆分", "Split") : copy("已生成", "Generated")) : (resume ? copy("还没有拆分", "Not split yet") : copy("还没有生成", "Not generated yet")))}</h2></div></div>
          <div class="writing-checkin-top">
            <div class="writing-stats-grid">${stats.map(([label, value]) => `<div><span>${esc(label)}</span><strong>${esc(updated ? value : 0)}</strong></div>`).join("")}</div>
            ${updated && detail ? detail : empty}
          </div>
          <div class="writing-checkin-bottom">
            <div class="writing-status-line"><strong id="interviewCustomCount">${esc(copy(`${text.length} 字`, `${text.length} chars`))}</strong><span>${esc(updated ? copy(`上次 ${dateText(updated)}`, `Last ${dateText(updated)}`) : resume ? copy("未拆分", "Not split") : copy("未生成", "Not generated"))}</span></div>
            <div class="writing-submit-row">
              ${button("open-corpus", esc(resume ? copy("去语料库", "Open corpus") : copy("看岗位题", "See questions")), { cls: "ghost", attrs: `id="interviewCustomCorpus" data-tab="${resume ? "project" : "jd"}"`, disabled: !updated })}
              ${button(resume ? "import-resume" : "import-jd", esc(resume ? (updated ? copy("重新拆分简历", "Split again") : copy("拆分简历", "Split resume")) : (updated ? copy("重新生成", "Regenerate") : copy("生成岗位题与反问", "Generate"))), { attrs: 'id="interviewCustomSubmit"' })}
            </div>
          </div>
        </aside>`;
      return `<section id="interviewCustom" class="panel writing-panel">
          <div class="iv-custom-bar">${switcher}<p>${esc(copy("内容会发送到你选择的 AI 服务；服务器不保存简历文件。", "Content goes to your selected AI service; resume files are not stored."))}</p></div>
          <div class="writing-shell">${editor}${result}</div>
        </section>`;
    }

    const PANE_COPY = {
      practice: () => [partName(data.part), pick(PARTS[data.part].hint)],
      reports: () => [copy("面试报告", "Interview reports"), copy("每一场的百分制、能力边界和逐题点评。", "Scores, boundaries and per-question notes for every session.")],
      custom: () => [copy("简历 / JD 定制", "Resume / JD"), copy("把简历和目标岗位拆成可练的语料。", "Turn your resume and target role into practice material.")],
    };

    function syncNav() {
      const pane = data.pane;
      const shown = (state.view === "interview" && pane !== "home") || (state.view === "home" && pane === "home");
      document.querySelectorAll("#interviewNav [data-interview-pane]").forEach((item) => {
        const itemPane = item.dataset.interviewPane;
        const active = itemPane === "practice" ? pane === "practice" && item.dataset.interviewPart === data.part
          : itemPane === pane || (pane === "report" && itemPane === "reports");
        item.classList.toggle("active", active && shown);
        item.setAttribute("aria-current", active && shown ? "page" : "false");
        item.setAttribute("aria-disabled", String(data.busy));
      });
    }

    function syncChrome() {
      const pane = data.pane;
      const bare = pane === "home" || pane === "reports" || pane === "report" || pane === "corpus";
      document.body.classList.toggle("interview-bare", state.view === "interview" && bare);
      document.querySelector?.(".workspace")?.classList.toggle("interview-corpus-workspace", state.view === "interview" && pane === "corpus");
      document.querySelector?.(".workspace")?.classList.toggle("interview-history-workspace", state.view === "interview" && (pane === "reports" || pane === "report"));
      if (document.body.dataset) { document.body.dataset.interviewPane = pane; document.body.dataset.interviewPart = data.part; }
      syncNav();
      const entry = PANE_COPY[pane]?.();
      if (!entry || state.view !== "interview") return;
      if (byId("viewTitle")) byId("viewTitle").textContent = entry[0];
      if (byId("viewSubtitle")) byId("viewSubtitle").textContent = entry[1];
    }

    function render() {
      const panel = byId("interviewPanel");
      if (!panel || !state.desktopCapabilities?.mock_interview) return;
      syncChrome();
      if (!state.account.authenticated) {
        panel.innerHTML = `<div class="iv-guest"><p class="iv-kicker">Interview Studio</p><h2 class="iv-title"><span class="iv-title-main">Mock Interview</span></h2><p>${esc(copy("登录同一个 IELTS Studio 账号，保存面试回答与练习记录。", "Sign in with your Studio account to save answers and interview history."))}</p>${solid("login", copy("登录并开始", "Sign in and start"))}</div>`;
        return;
      }
      if (data.pendingResumeId && data.pane === "practice" && !data.current && !data.busy) {
        const id = data.pendingResumeId;
        data.pendingResumeId = null;
        perform(() => request(`/api/interview/sessions/${encodeURIComponent(id)}/`), (payload) => { if (payload.session.part === data.part) acceptSession(payload); });
        return;
      }
      // Home is the shared IELTS home panel, not part of #interviewPanel.
      if (data.pane === "home") { panel.innerHTML = ""; return; }
      const content = ({ practice, reports: reportsPane, report: reportsPane, corpus: corpusPane, custom: customPane })[data.pane]();
      const status = `<div id="interviewStatus" class="iv-status-line" role="status" aria-live="polite">${data.busy && data.answer.state !== "thinking" ? `<span class="iv-spinner" aria-hidden="true"></span>${esc(copy("正在处理…", "Working…"))}` : esc(data.notice)}</div>`;
      panel.innerHTML = `${status}${data.error ? `<div class="iv-error" role="alert">${esc(data.error)}</div>` : ""}<div class="iv-pane iv-pane--${data.pane}">${content}</div>${editorModal()}`;
      if (data.pane === "reports" || data.pane === "report") mountReportRail();
    }

    // ---- Recording: MediaRecorder -> upload -> server ASR -> editable transcript.
    function timerText() {
      if (!recorder?.startedAt) return "00:00";
      const seconds = Math.floor((Date.now() - recorder.startedAt) / 1000);
      return `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`;
    }

    function resetAnswer() {
      data.answer = { state: "idle", text: "", source: "typed", typing: false, error: "", peek: false };
    }

    function stopRecorder() {
      if (!recorder) return;
      window.clearInterval?.(recorder.tick);
      try { if (recorder.media?.state === "recording") recorder.media.stop(); } catch (_error) { /* already stopped */ }
      recorder.stream?.getTracks?.().forEach((track) => track.stop());
      recorder = null;
    }

    async function startRecording() {
      const devices = typeof navigator !== "undefined" ? navigator.mediaDevices : null;
      if (!devices?.getUserMedia || typeof MediaRecorder !== "function") {
        data.answer.error = copy("当前环境不支持录音，请改为打字作答。", "Recording is unavailable here; please type your answer.");
        data.answer.typing = true;
        render();
        return;
      }
      try {
        const stream = await devices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
        const mimeType = MediaRecorder.isTypeSupported?.("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
        const media = new MediaRecorder(stream, { mimeType });
        recorder = { stream, media, chunks: [], startedAt: Date.now(), mimeType };
        media.ondataavailable = (event) => { if (event.data?.size) recorder?.chunks.push(event.data); };
        media.start(250);
        recorder.tick = window.setInterval(() => { const el = byId("interviewTimer"); if (el) el.textContent = timerText(); }, 250);
        data.answer = { ...data.answer, state: "recording", error: "", typing: false };
        render();
      } catch (_error) {
        stopRecorder();
        data.answer.error = copy("无法使用麦克风，请检查权限，或改为打字作答。", "Microphone unavailable — check permission or type instead.");
        render();
      }
    }

    async function stopRecording() {
      const active = recorder;
      if (!active) return;
      window.clearInterval(active.tick);
      await new Promise((resolve) => { active.media.onstop = resolve; active.media.stop(); });
      active.stream.getTracks().forEach((track) => track.stop());
      recorder = null;
      const blob = new Blob(active.chunks, { type: active.mimeType });
      const turn = data.current?.current_turn;
      if (!turn || !blob.size) { resetAnswer(); render(); return; }
      data.answer.state = "processing";
      const form = new FormData();
      form.append("audio", blob, "answer.webm");
      await perform(() => upload(`/api/interview/sessions/${encodeURIComponent(data.current.session.id)}/turns/${encodeURIComponent(turn.id)}/audio/`, form), (payload) => {
        data.answer = { ...data.answer, state: "review", text: payload.transcript, source: "voice", error: "" };
      }, { busy: false });
      if (data.answer.state === "processing") {
        data.answer = { ...data.answer, state: "idle", typing: true, error: data.error || copy("转写失败，请重录或打字作答。", "Transcription failed; record again or type.") };
        data.error = "";
        render();
      }
    }

    function submitAnswer() {
      const session = data.current?.session;
      const turn = data.current?.current_turn;
      const answer = data.answer.text.trim();
      if (!session || !turn) return;
      if (!answer) { data.answer.error = copy("回答是空的：录一段或打几句再提交。", "Your answer is empty."); render(); return; }
      data.answer.state = "thinking";
      perform(() => request(`/api/interview/sessions/${encodeURIComponent(session.id)}/turns/${encodeURIComponent(turn.id)}/answer/`, { answer, answer_source: data.answer.source, ai_source: currentAiSourcePreference() }),
        (payload) => { acceptSession(payload); resetAnswer(); }).then(() => {
        // A failed submit keeps the text so it can be sent again.
        if (data.answer.state === "thinking") { data.answer.state = "review"; render(); }
      });
    }

    // ---- Inputs and actions
    function captureInput(event) {
      const el = event.target;
      const field = el.dataset.interviewField;
      if (field === "answer") {
        data.answer.text = el.value;
        if (data.answer.state !== "review") data.answer.source = "typed";
        const counter = byId("interviewAnswerCount");
        if (counter) counter.textContent = `${el.value.length} / 6000`;
      } else if (field === "editor-text" && data.editor) data.editor.text = el.value;
      else if (field === "editor-question" && data.editor) data.editor.question = el.value;
      else if (field === "file") { data.file = el.files?.[0] || null; render(); }
      else if (field === "resumeText" || field === "jdText") {
        data[field] = el.value;
        const counter = byId("interviewCustomCount");
        if (counter) counter.textContent = copy(`${el.value.length} 字`, `${el.value.length} chars`);
      }
    }

    function openEditor(entry) {
      data.editor = { entry, text: entry.corpus_text || "", question: entry.question || "" };
      render();
      byId("interviewPanel")?.querySelector?.('[data-interview-field="editor-text"]')?.focus?.();
    }

    function saveEditor() {
      const { entry, text, question } = data.editor;
      const upsert = (payload) => {
        const index = data.corpus.findIndex((item) => (entry.id ? item.id === entry.id : item.source_key === entry.source_key && !item.id));
        if (index >= 0) data.corpus.splice(index, 1, payload.entry);
        else data.corpus.push(payload.entry);
        data.editor = null;
        data.notice = copy("已保存到语料库。", "Saved to your corpus.");
      };
      if (entry.id) {
        const body = { corpus_text: text };
        if (entry.source !== "curated" && question.trim() && question !== entry.question) body.question = question;
        perform(() => request(`/api/interview/corpus/${encodeURIComponent(entry.id)}/`, body, { method: "PATCH" }), upsert);
      } else if (entry.source_key) {
        perform(() => request("/api/interview/corpus/", { kind: "knowledge", source_key: entry.source_key, corpus_text: text }), upsert);
      } else {
        if (!question.trim()) { data.error = copy("请先写题目。", "Write the question first."); render(); return; }
        perform(() => request("/api/interview/corpus/", { kind: entry.kind, question, corpus_text: text, group: entry.group || "", parent_id: entry.parent_id || undefined }), upsert);
      }
    }

    function handleAction(event) {
      const el = event.target.closest("[data-interview-action]");
      if (!el || (data.busy && !["close-editor"].includes(el.dataset.interviewAction))) return;
      if (el.tagName === "A") event.preventDefault?.();
      const action = el.dataset.interviewAction;
      if (action !== "report-filter-toggle") data.reportFilterOpen = false;
      const sessionId = data.current?.session?.id;
      const base = sessionId ? `/api/interview/sessions/${encodeURIComponent(sessionId)}/` : "";
      switch (action) {
        case "login": promptGuestLogin(copy("登录后保存面试记录与回答。", "Sign in to save interview practice."), { returnView: "interview" }); return;
        case "go-practice": setPane("practice", { part: el.dataset.part || "full" }); return;
        case "go-custom": data.customSide = el.dataset.side || data.customSide; setPane("custom"); return;
        case "reports": setPane("reports"); return;
        case "reload-history": loadHistory(); return;
        case "report-filter-toggle": data.reportFilterOpen = !data.reportFilterOpen; render(); return;
        case "report-filter":
          data.reportFilter = REPORT_FILTERS.includes(el.dataset.filter) ? el.dataset.filter : "all";
          data.railScroll = 0;
          if (selectedReport() && !visibleReports().some((item) => item.id === data.current.session.id)) data.current = null;
          render();
          openFirstReport();
          return;
        case "rail-step": {
          const list = byId("interviewReportList");
          if (list) list.scrollBy({ left: Number(el.dataset.step) * Math.max(260, Math.floor(list.clientWidth * 0.45)), behavior: "smooth" });
          return;
        }
        case "open-corpus": data.corpusTab = el.dataset.tab || data.corpusTab; setPane("corpus"); return;
        case "corpus-tab": data.corpusTab = el.dataset.tab; render(); return;
        case "custom-side": data.customSide = el.dataset.side; render(); return;
        case "intensity": data.intensity = el.dataset.intensity; render(); return;
        case "launch-category": data.launch.category = el.dataset.category || ""; render(); return;
        case "launch-count": data.launch.count = Number(el.dataset.count) || 5; render(); return;
        case "toggle-project": {
          const ids = data.launch.projectIds;
          ids.has(el.dataset.entryId) ? ids.delete(el.dataset.entryId) : ids.add(el.dataset.entryId);
          render();
          return;
        }
        case "toggle-peek": data.answer.peek = !data.answer.peek; render(); return;
        case "type-answer": data.answer.typing = true; data.answer.error = ""; render(); byId("interviewAnswer")?.focus?.(); return;
        case "start-session": {
          const body = { part: data.part, intensity: data.intensity };
          if (data.part === "knowledge") Object.assign(body, { category: data.launch.category, count: data.launch.count });
          if (data.part === "project" && data.launch.projectIds.size) body.project_ids = [...data.launch.projectIds];
          resetAnswer();
          perform(() => request("/api/interview/sessions/", body), acceptSession);
          return;
        }
        case "record-start": startRecording(); return;
        case "record-stop": stopRecording(); return;
        case "submit-answer": submitAnswer(); return;
        case "skip": {
          const turn = data.current?.current_turn;
          if (!turn) return;
          stopRecorder();
          perform(() => request(`${base}turns/${encodeURIComponent(turn.id)}/skip/`, {}), (payload) => { acceptSession(payload); resetAnswer(); });
          return;
        }
        case "finish":
          perform(() => request(`${base}finish/`, {}), acceptSession).then(() => {
            // Ask for the 100-point score once, right after the transcript is saved.
            const session = data.current?.session;
            if (session?.status === "completed" && !session.score) {
              return perform(() => request(`/api/interview/sessions/${encodeURIComponent(session.id)}/report/`, { ai_source: currentAiSourcePreference() }), acceptSession);
            }
            return null;
          }).then(() => { if (data.pane === "report" && !data.sessionsLoaded) loadHistory(); });
          return;
        case "abort": stopRecorder(); perform(() => request(`${base}abort/`, {}), (payload) => { acceptSession(payload); data.current = null; data.pane = "practice"; resetAnswer(); }); return;
        case "score": perform(() => request(`${base}report/`, { ai_source: currentAiSourcePreference() }), acceptSession); return;
        case "open-session": perform(() => request(`/api/interview/sessions/${encodeURIComponent(el.dataset.sessionId)}/`), (payload) => { acceptSession(payload); resetAnswer(); }); return;
        case "save-corpus": perform(() => request(`${base}turns/${encodeURIComponent(el.dataset.turnId)}/save-corpus/`, {}), (payload) => {
          const index = (data.corpus || []).findIndex((item) => item.id === payload.entry.id);
          if (data.corpus) index >= 0 ? data.corpus.splice(index, 1, payload.entry) : data.corpus.push(payload.entry);
          data.notice = copy("已存为你的答法。", "Saved to your corpus.");
        }); return;
        case "edit-entry": {
          const entry = el.dataset.entryId ? entryFor(el.dataset.entryId) : (data.corpus || []).find((item) => !item.id && item.source_key === el.dataset.sourceKey);
          if (entry) openEditor(entry);
          return;
        }
        case "new-entry": openEditor({ id: null, kind: el.dataset.kind || "knowledge", source: "custom", group: el.dataset.group || "", parent_id: el.dataset.parent || null, question: "", corpus_text: "", ai_draft: "" }); return;
        case "close-editor": data.editor = null; render(); return;
        case "adopt-draft": if (data.editor) { data.editor.text = data.editor.entry.ai_draft; render(); } return;
        case "save-entry": saveEditor(); return;
        case "draft-entry": {
          const entry = data.editor?.entry;
          if (!entry?.id) return;
          perform(() => request(`/api/interview/corpus/${encodeURIComponent(entry.id)}/draft/`, { ai_source: currentAiSourcePreference() }), (payload) => {
            const index = data.corpus.findIndex((item) => item.id === payload.entry.id);
            if (index >= 0) data.corpus.splice(index, 1, payload.entry);
            if (data.editor) data.editor.entry = payload.entry;
          });
          return;
        }
        case "delete-entry": {
          const entry = data.editor?.entry;
          if (!entry?.id) return;
          perform(() => request(`/api/interview/corpus/${encodeURIComponent(entry.id)}/`, null, { method: "DELETE" }), () => {
            data.corpus = data.corpus.filter((item) => item.id !== entry.id && item.parent_id !== entry.id);
            data.editor = null;
          });
          return;
        }
        case "import-resume": {
          const form = new FormData();
          form.append("resume_text", data.resumeText);
          form.append("ai_source", currentAiSourcePreference());
          if (data.file) form.append("resume_file", data.file);
          perform(() => upload("/api/interview/profile/resume/", form), (payload) => {
            data.profile = payload.profile; data.corpus = payload.entries; data.file = null;
            data.notice = copy("简历已拆分，讲述稿都在语料库里。", "Resume split — your stories are in the corpus.");
          });
          return;
        }
        case "import-jd":
          perform(() => request("/api/interview/profile/jd/", { job_description: data.jdText, ai_source: currentAiSourcePreference() }), (payload) => {
            data.profile = payload.profile; data.corpus = payload.entries;
            data.notice = copy("已生成岗位题与反问问题。", "Role questions and questions to ask are ready.");
          });
          return;
        default:
          if (PANES.has(action)) setPane(action);
      }
    }

    return { initialize, setProductMode, show, resetForAccount, setPane };
  }
  window.IELTSInterview = { createInterview };
})();
