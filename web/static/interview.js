(function () {
  const MODES = new Set(["ielts", "interview"]);
  const PANES = new Set(["home", "practice", "reports", "report", "corpus", "custom", "assistant"]);
  const MODE_KEY = "ielts-product-mode";
  const ARROW = '<span class="iv-arrow" aria-hidden="true">→</span>';
  // The interview counterpart of Mock + P1/P2/P3.
  const PARTS = {
    full: { zh: "完整面试", en: "Full interview", hint: ["自我介绍 → 项目 → 知识点 → 奖项 → 反问", "Intro → projects → knowledge → awards → your questions"], corpus: "resume" },
    project: { zh: "项目深挖", en: "Projects", hint: ["介绍项目，再接受追问。", "Present a project, then take follow-ups."], corpus: "resume" },
    knowledge: { zh: "知识点", en: "Knowledge", hint: ["技术栈与通用题库连续问答。", "Rapid questions from your stack and the bank."], corpus: "knowledge" },
    reverse: { zh: "反问环节", en: "Your questions", hint: ["你来提问，面试官回答并点评。", "You ask; the interviewer answers and reviews."], corpus: "jd" },
  };
  const STAGES = { self_intro: ["自我介绍", "Intro"], project: ["项目", "Projects"], knowledge: ["知识点", "Knowledge"], award: ["奖项", "Awards"], reverse: ["反问", "Questions"] };

  function createInterview({ state, api, ensureCsrfToken, switchView, exitPractice, promptGuestLogin, escapeHtml, currentAiSourcePreference, markdown, renderMarkdown }) {
    let epoch = 0;
    let initialized = false;
    let requestController = null;
    let switcher = null;
    let data = freshState();
    const byId = (id) => document.getElementById(id);
    // The launch block in the practice panel's PROMPT pane (interview-launch.js).
    const launch = window.IELTSInterviewLaunch?.create({
      state, escapeHtml, markdown, currentAiSourcePreference, renderMarkdown: renderMarkdown || ((value) => escapeHtml(String(value || ""))),
      upload: (path, form) => upload(path, form),
      popup: (message) => popup(message),
      source: () => data,
      onProfile: (payload) => { data.profile = payload.profile; data.corpus = payload.entries || data.corpus; window.IELTSInterviewHome?.refresh(); },
    }) || null;
    // The three corpus screens and their editors (interview-corpus.js).
    const corpusScreens = window.IELTSInterviewCorpus?.create({
      state, escapeHtml, markdown, currentAiSourcePreference, renderMarkdown: renderMarkdown || ((value) => escapeHtml(String(value || ""))),
      request: (path, body, options) => api(path, body, options),
      popup: (message) => popup(message),
      source: () => data,
      setCorpus: (list) => { data.corpus = list; window.IELTSInterviewHome?.refresh(); },
      rerender: () => { if (data.pane === "corpus" && state.view === "interview") render(); },
      startPractice: (part, preset) => { launch?.preset(`iv_${part}`, preset); setPane("practice", { part }); },
    }) || null;
    // AI 助手 (interview-assistant.js): chat; saves into the three corpus screens in agent mode.
    const assistantChat = window.IELTSInterviewAssistant?.create({
      state, escapeHtml, currentAiSourcePreference,
      request: (path, body, options) => api(path, body, options),
      popup: (message) => popup(message),
      toast: (message) => toast(message),
      setCorpus: (list) => { data.corpus = list; window.IELTSInterviewHome?.refresh(); },
      openApplied: (item) => openApplied(item),
      openPage: () => setPane("assistant"),
    }) || null;
    // The corner dock (the assistant in miniature) is on every interview page but the AI 助手 pane itself.
    function syncDock() {
      assistantChat?.syncDock({ visible: state.productMode === "interview" && Boolean(state.account.authenticated)
        && Boolean(state.desktopCapabilities?.mock_interview) && !(state.view === "interview" && data.pane === "assistant") });
    }
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
        pane: "home", part: "full", busy: false, notice: "",
        questions: [], categories: [], sessions: [], sessionsLoaded: false,
        corpus: null, corpusTab: "knowledge", profile: null, customSide: "resume", resumeText: "", file: null, jdText: "",
        drafts: { resume: null, jd: null },
      };
    }

    function resetForAccount() {
      epoch += 1;
      requestController?.abort();
      requestController = null;
      data = freshState();
      launch?.reset();
      corpusScreens?.reset();
      assistantChat?.reset();
      if (byId("interviewPanel")) render({ force: true });
      window.IELTSInterviewHome?.refresh();
      ensureOverview();
      syncDock();
    }

    // The shared home panel needs the interview numbers whenever interview mode is on, whatever view loaded first.
    function ensureOverview() {
      if (state.productMode !== "interview" || !state.account.authenticated || data.busy) return;
      if (!data.sessionsLoaded || !data.corpus) loadOverview();
    }

    function setProductMode(mode) {
      if (!MODES.has(mode) || (mode === "interview" && !state.desktopCapabilities?.mock_interview)) mode = "ielts";
      state.productMode = mode;
      const name = mode === "interview" ? "Interview" : "IELTS Studio"; // the brand reads like "IELTS Studio", in both languages
      document.body.classList.toggle("interview-mode", mode === "interview");
      byId("interviewNav")?.classList.toggle("hidden", mode !== "interview");
      if (byId("studioModeLabel")) byId("studioModeLabel").textContent = name;
      if (byId("studioModeCurrent")) byId("studioModeCurrent").textContent = name;
      document.querySelectorAll("[data-studio-mode]").forEach((el) => el.setAttribute("aria-checked", String(el.dataset.studioMode === mode)));
      window.IELTSInterviewHome?.apply(mode);
      if (mode === "interview") ensureOverview();
      syncDock();
      try { localStorage.setItem(MODE_KEY, mode); } catch (_error) { /* Session-only preference. */ }
    }

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
        if (item) changeMode(item.dataset.studioMode, !event.detail).catch((error) => popup(error.message));
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
        menu(false, !!switcher?.isOpen());
      });
      byId("interviewNav")?.addEventListener("click", (event) => {
        const item = event.target.closest("[data-interview-pane]");
        if (!item) return;
        event.preventDefault?.();
        setPane(item.dataset.interviewPane, { part: item.dataset.interviewPart });
      });
      byId("interviewPanel")?.addEventListener("click", (event) => { if (!assistantChat?.handleClick(event)) handleAction(event); });
      byId("interviewPanel")?.addEventListener("keydown", (event) => assistantChat?.handleKey(event));
      // Links on the shared home panel carry data-iv-target ("pane" or "pane:part") in interview mode. Capture
      // phase, so the IELTS router never sees them and the href never navigates.
      document.addEventListener("click", (event) => {
        const target = event.target.closest?.("#homePanel [data-iv-target], #corpusPanel [data-iv-target]");
        if (!target || state.productMode !== "interview") return;
        event.preventDefault();
        event.stopPropagation();
        const [pane, part] = target.dataset.ivTarget.split(":");
        setPane(pane, part ? (pane === "practice" ? { part } : { tab: part }) : {});
      }, true);
      // The IELTS back button above a corpus screen returns to the interview hub here.
      document.addEventListener("click", (event) => {
        if (!event.target.closest?.("#topbarBackCorpusBtn") || state.productMode !== "interview" || state.view !== "interview" || data.pane !== "corpus") return;
        event.preventDefault();
        event.stopPropagation();
        setPane("corpus");
      }, true);
      window.IELTSInterviewHome?.setSource(homeNumbers);
      byId("interviewPanel")?.addEventListener("input", (event) => { if (!assistantChat?.handleInput(event)) captureInput(event); });
      byId("interviewPanel")?.addEventListener("change", captureInput);
      window.addEventListener("ielts:ui-language-change", () => { setProductMode(state.productMode); render({ force: true }); });
    }

    // ---- Feedback without taking page space: errors in the IELTS pop-up (confirm-overlay), progress and success
    // in a floating toast.
    function popup(message) {
      document.querySelector(".iv-alert-overlay")?.remove();
      const overlay = document.createElement("div");
      overlay.className = "confirm-overlay iv-alert-overlay";
      overlay.innerHTML = `<div class="confirm-dialog" role="alertdialog" aria-modal="true"><p>${esc(message)}</p>
        <div class="confirm-actions"><button class="confirm-cancel" type="button">${esc(copy("知道了", "OK"))}</button></div></div>`;
      const close = () => overlay.remove();
      overlay.addEventListener("click", (event) => { if (event.target === overlay || event.target.closest(".confirm-cancel")) close(); });
      document.body.appendChild(overlay);
      overlay.querySelector(".confirm-cancel")?.focus?.();
    }

    let toastTimer = 0;
    function toast(message, { busy = false } = {}) {
      let el = byId("ivToast");
      if (!el) {
        el = document.createElement("div");
        el.id = "ivToast";
        el.className = "iv-toast";
        el.setAttribute("role", "status");
        el.setAttribute("aria-live", "polite");
        document.body.appendChild(el);
      }
      window.clearTimeout?.(toastTimer);
      if (!message) { el.classList.remove("is-visible"); return; }
      el.innerHTML = `${busy ? '<span class="iv-spinner" aria-hidden="true"></span>' : ""}<span>${esc(message)}</span>`;
      el.classList.add("is-visible");
      if (!busy) toastTimer = window.setTimeout?.(() => el.classList.remove("is-visible"), 3200);
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
      data.notice = "";
      if (busy) toast(copy("正在处理…", "Working…"), { busy: true });
      render();
      try {
        const result = await task();
        if (generation !== epoch || owner !== state.account.user?.id || !state.account.authenticated) return;
        apply?.(result);
      } catch (error) {
        // Only what the candidate asked for gets a pop-up; a background refresh fails quietly.
        if (busy && generation === epoch && owner === state.account.user?.id) popup(error.message || copy("请求失败，请重试。", "Request failed; please retry."));
      } finally {
        if (generation === epoch && owner === state.account.user?.id) {
          requestController = null;
          data.busy = false;
          if (busy) toast(data.notice);
          data.notice = "";
          render();
        }
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
      // Finished interviews are speaking attempts; the IELTS history endpoint lists them under domain=interview.
      if (history) { data.sessions = history.items || []; data.sessionsLoaded = true; }
      if (profile) data.profile = profile.profile;
      if (corpus) data.corpus = corpus.entries || [];
      window.IELTSInterviewHome?.refresh();
      // The launch block lists corpus projects and categories; redraw it once they arrive.
      if (/^iv_/.test(state.view || "") && !state.practiceLocked && !byId("ivLaunch")?.classList.contains("hidden")) launch?.render(state.view);
    }

    // Numbers the shared home panel shows in interview mode (interview-home.js).
    function homeNumbers() {
      if (!state.account.authenticated) return null;
      const finished = data.sessions;
      const scored = finished.filter((item) => Number.isFinite(item.interview_total));
      const entries = data.corpus || [];
      const kind = (...kinds) => entries.filter((entry) => kinds.includes(entry.kind) && !entry.orphaned);
      return {
        sessions: data.sessionsLoaded ? finished.length : null,
        average: scored.length ? Math.round(scored.reduce((sum, item) => sum + item.interview_total, 0) / scored.length) : null,
        last: finished[0]?.timestamp || null,
        projectReady: kind("project").filter((entry) => entry.corpus_text).length,
        knowledgeReady: kind("knowledge").filter((entry) => entry.corpus_text).length,
        jdCount: kind("jd_question", "reverse_question").length,
        projects: kind("project").length,
        knowledge: kind("knowledge").length,
      };
    }

    function loadOverview() {
      return perform(() => Promise.all([
        request("/api/interview/questions/"), request("/api/history?domain=interview"),
        request("/api/interview/profile/"), request("/api/interview/corpus/"),
      ]), acceptOverview, { busy: false }); // background refresh: never blocks navigation
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

    function setPane(pane, { part, tab } = {}) {
      if (!PANES.has(pane) || data.busy) return;
      if (pane === "corpus" && !tab) {
        // 面试语料库 is the IELTS 语料库 hub with interview copy (interview-home.js); its cards open the screens.
        data.pane = "library";
        switchView("corpus", { force: state.view !== "corpus" });
        syncNav();
        ensureOverview();
        return;
      }
      if (tab) data.corpusTab = ["knowledge", "resume", "jd"].includes(tab) ? tab : "knowledge";
      if (pane === "home") {
        // The interview home is the IELTS home panel itself, with interview copy swapped in.
        data.pane = "home";
        switchView("home", { force: state.view !== "home" });
        syncNav();
        if (!data.corpus && state.account.authenticated) loadOverview();
        else window.IELTSInterviewHome?.refresh();
        return;
      }
      if (part && PARTS[part]) data.part = part;
      data.pane = pane;
      if (pane === "reports" || pane === "report") {
        // Interview reports live on the IELTS report page (history view, interview attempts only).
        data.pane = "reports";
        switchView("history", { force: true });
        syncNav();
        return;
      }
      if (pane === "practice") {
        // Interview practice is the IELTS practice panel itself (views iv_full / iv_project / …).
        switchView(`iv_${data.part}`, { force: state.view !== `iv_${data.part}` });
        syncNav();
        return;
      }
      switchView("interview", { force: state.view !== "interview" });
      render();
      if (!data.corpus && state.account.authenticated) loadOverview();
    }

    // ---- Drafts: 定制 generates first; the candidate reviews / edits each item, then adds the lot to the corpus.
    const draftValue = (root, path) => path.split(".").reduce((node, key) => node?.[key], root);
    function setDraftValue(root, path, value) {
      const keys = path.split(".");
      const last = keys.pop();
      const parent = keys.reduce((node, key) => node?.[key], root);
      if (parent) parent[last] = value;
    }
    function removeDraftItem(root, path) {
      const keys = path.split(".");
      const index = Number(keys.pop());
      const list = keys.reduce((node, key) => node?.[key], root);
      if (Array.isArray(list)) list.splice(index, 1);
    }

    function draftRows(side) {
      const draft = data.drafts[side]?.draft;
      if (!draft) return [];
      if (side === "jd") {
        return [
          ...(draft.questions || []).map((item, i) => ({ path: `questions.${i}.draft`, remove: `questions.${i}`, kind: "岗位题", title: item.question, body: item.draft })),
          ...(draft.reverse_questions || []).map((item, i) => ({ path: `reverse_questions.${i}.draft`, remove: `reverse_questions.${i}`, kind: "反问", title: item.question, body: item.draft })),
        ];
      }
      const rows = [{ path: "self_intro.draft", kind: "自我介绍", title: "自我介绍", body: draft.self_intro?.draft || "" }];
      (draft.projects || []).forEach((project, i) => {
        rows.push({ path: `projects.${i}.draft`, remove: `projects.${i}`, kind: project.type === "internship" ? "实习" : "项目", title: project.title, body: project.draft });
        (project.followups || []).forEach((item, j) => rows.push({ path: `projects.${i}.followups.${j}.draft`, remove: `projects.${i}.followups.${j}`, kind: "追问", title: item.question, body: item.draft, nested: true }));
      });
      (draft.tech_stack || []).forEach((group, g) => (group.questions || []).forEach((item, q) =>
        rows.push({ path: `tech_stack.${g}.questions.${q}.draft`, remove: `tech_stack.${g}.questions.${q}`, kind: group.group, title: item.question, body: item.draft })));
      (draft.awards || []).forEach((award, i) => rows.push({ path: `awards.${i}.draft`, remove: `awards.${i}`, kind: "奖项", title: award.title, body: award.draft, summary: award.summary }));
      return rows;
    }

    function draftReview(side) {
      const rows = draftRows(side);
      const plain = (value) => String(value || "").replace(/[#*_`>~\-]+/g, " ").replace(/\s+/g, " ").trim();
      return `<div class="iv-draft-list">${rows.map((row) => `
          <div class="iv-draft-row${row.nested ? " is-nested" : ""}">
            <button type="button" class="${row.body ? "has-corpus" : ""}" data-interview-action="draft-edit" data-path="${esc(row.path)}">
              <strong>${esc(row.kind)}</strong><span>${esc(row.title)}<small>${esc(plain(row.body).slice(0, 60) || copy("（空）点开填写", "(empty)"))}</small></span>
            </button>
            ${row.remove ? `<button type="button" class="iv-draft-remove" data-interview-action="draft-remove" data-path="${esc(row.remove)}" aria-label="${esc(copy("不加入这一条", "Leave this out"))}">×</button>` : ""}
          </div>`).join("")}</div>`;
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
            <p>${esc(copy("生成：自我介绍、每个项目的讲述稿与预判追问、技术栈题、奖项。先在右边检查、修改，再加入语料库；已经改写过的答法不会被覆盖。", "Generates an intro, a story and likely follow-ups per project, stack questions and awards. Review and edit them on the right, then add them; your own answers are never overwritten."))}</p></div>`
        : `<div class="writing-prompt-card"><div><span class="writing-pill">JD</span><h2>${esc(copy("按目标岗位出题", "Questions for your target role"))}</h2></div>
            <p>${esc(copy("生成岗位题和反问环节要问的问题。先在右边检查、修改，再加入语料库，在「JD 与反问」和「反问环节」里练。", "Generates role questions and questions to ask. Review and edit them, then add them to your corpus."))}</p></div>`;
      const hint = resume
        ? `<div class="writing-frame-hint"><label class="writing-frame-cmd iv-file-pick"><input type="file" accept="application/pdf,.pdf" data-interview-field="file">${esc(data.file?.name || copy("选择 PDF 简历", "Choose a PDF resume"))}</label><span class="writing-frame-hint-dot">·</span><span class="writing-frame-hint-lead">${esc(copy("最多 2 MB，扫描件请粘贴文字", "Up to 2 MB; paste text for scans"))}</span></div>`
        : `<div class="writing-frame-hint"><span class="writing-frame-hint-lead">${esc(copy("内容会发送到你选择的 AI 服务", "Sent to your selected AI service"))}</span></div>`;
      const editor = `<article class="writing-editor-card">${prompt}
          <div class="writing-answer-header"><label class="writing-answer-label" for="interviewCustomText">${esc(resume ? copy("简历文字", "Resume text") : copy("岗位描述", "Job description"))}</label>${hint}</div>
          <textarea id="interviewCustomText" class="writing-answer" maxlength="${resume ? 24000 : 12000}" data-interview-field="${resume ? "resumeText" : "jdText"}" placeholder="${esc(resume ? copy("或者把简历全文粘贴在这里……", "Or paste the full resume text here…") : copy("粘贴目标岗位的职责与要求……", "Paste the role's responsibilities and requirements…"))}">${esc(text)}</textarea>
        </article>`;
      const stats = resume
        ? [[copy("项目", "Projects"), count("project")], [copy("技术栈", "Stack"), count("tech_stack")], [copy("奖项", "Awards"), count("award")]]
        : [[copy("核心要求", "Requirements"), (profile.jd?.summary?.requirements || []).length], [copy("岗位题", "Role Qs"), (data.corpus || []).filter((e) => e.kind === "jd_question").length], [copy("反问", "To ask"), (data.corpus || []).filter((e) => e.kind === "reverse_question").length]];
      const detail = resume
        ? (modules.some((item) => item.kind === "project") ? `<ul class="iv-custom-list">${modules.filter((item) => item.kind === "project").map((item) => `<li>${esc(item.title)}</li>`).join("")}</ul>` : "")
        : (profile.jd?.summary?.role ? `<p class="iv-custom-role">${esc(profile.jd.summary.role)}</p><ul class="iv-custom-list">${(profile.jd.summary.requirements || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul>` : "");
      const empty = `<p class="iv-custom-empty">${esc(resume ? copy("生成后，这里会先列出草稿，检查完再加入语料库。", "The draft appears here for review before it goes into your corpus.") : copy("生成后，这里会先列出岗位题和反问草稿，检查完再加入语料库。", "The draft appears here for review before it goes into your corpus."))}</p>`;
      const pending = data.drafts[side];
      if (pending) {
        const rows = draftRows(side);
        const review = `<aside class="writing-result-card iv-draft-card">
          <div class="writing-card-head"><div><h2>${esc(copy("先检查一下草稿", "Review the draft"))}</h2></div></div>
          <div class="writing-checkin-top">
            <p class="iv-custom-empty">${esc(copy("点开任意一条可以直接改，× 表示这条不加入。确认后一起加入语料库；已经改写过的答法不会被覆盖。", "Open any item to edit it; × leaves it out. Your own answers are never overwritten."))}</p>
            ${draftReview(side)}
          </div>
          <div class="writing-checkin-bottom">
            <div class="writing-status-line"><strong id="interviewCustomCount">${esc(copy(`${rows.length} 条待确认`, `${rows.length} to review`))}</strong><span>${esc(side === "jd" ? (pending.draft.summary?.role || "") : "")}</span></div>
            <div class="writing-submit-row">
              ${button("draft-discard", esc(copy("放弃草稿", "Discard")), { cls: "ghost", attrs: 'id="interviewCustomCorpus"' })}
              ${button("draft-commit", esc(copy("加入语料库", "Add to corpus")), { attrs: 'id="interviewCustomSubmit"' })}
            </div>
          </div>
        </aside>`;
        return `<section id="interviewCustom" class="panel writing-panel">
          <div class="iv-custom-bar">${switcher}<p>${esc(copy("内容会发送到你选择的 AI 服务；服务器不保存简历文件。", "Content goes to your selected AI service; resume files are not stored."))}</p></div>
          <div class="writing-shell">${editor}${review}</div>
        </section>`;
      }
      const result = `<aside class="writing-result-card">
          <div class="writing-card-head"><div><h2>${esc(updated ? (resume ? copy("已加入语料库", "Added") : copy("已生成", "Generated")) : (resume ? copy("还没有生成", "Not generated yet") : copy("还没有生成", "Not generated yet")))}</h2></div></div>
          <div class="writing-checkin-top">
            <div class="writing-stats-grid">${stats.map(([label, value]) => `<div><span>${esc(label)}</span><strong>${esc(updated ? value : 0)}</strong></div>`).join("")}</div>
            ${updated && detail ? detail : empty}
          </div>
          <div class="writing-checkin-bottom">
            <div class="writing-status-line"><strong id="interviewCustomCount">${esc(copy(`${text.length} 字`, `${text.length} chars`))}</strong><span>${esc(updated ? copy(`上次 ${dateText(updated)}`, `Last ${dateText(updated)}`) : resume ? copy("未生成", "Not generated") : copy("未生成", "Not generated"))}</span></div>
            <div class="writing-submit-row">
              ${button("open-corpus", esc(resume ? copy("去语料库", "Open corpus") : copy("看岗位题", "See questions")), { cls: "ghost", attrs: `id="interviewCustomCorpus" data-tab="${resume ? "resume" : "jd"}"`, disabled: !updated })}
              ${button(resume ? "import-resume" : "import-jd", esc(resume ? (updated ? copy("重新生成题卡", "Generate again") : copy("生成简历题卡", "Generate cards")) : (updated ? copy("重新生成", "Regenerate") : copy("生成岗位题与反问", "Generate"))), { attrs: 'id="interviewCustomSubmit"' })}
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
      custom: () => [copy("简历 / JD 定制", "Resume / JD"), copy("把简历和目标岗位拆成可练的语料。", "Turn your resume and target role into practice material.")],
      assistant: () => [copy("AI 助手", "AI assistant"), copy("随时提问；让它整理进知识点、简历题卡或 JD 与反问。", "Ask anything; have it filed into your knowledge, resume cards or JD questions.")],
    };

    function syncNav() {
      const practiceView = /^iv_/.test(state.view || "");
      if (practiceView) { data.pane = "practice"; data.part = state.view.slice(3); }
      if (state.view === "history") data.pane = "reports";
      if (state.view === "corpus") data.pane = "library";
      const pane = data.pane;
      if (document.body.dataset) { document.body.dataset.interviewPane = pane; document.body.dataset.interviewPart = data.part; }
      const shown = practiceView || state.view === "history" || state.view === "corpus" || (state.view === "interview" && pane !== "home") || (state.view === "home" && pane === "home");
      document.querySelectorAll("#interviewNav [data-interview-pane]").forEach((item) => {
        const itemPane = item.dataset.interviewPane;
        const active = itemPane === "practice" ? pane === "practice" && item.dataset.interviewPart === data.part
          : itemPane === pane || (pane === "report" && itemPane === "reports") || (pane === "library" && itemPane === "corpus");
        item.classList.toggle("active", active && shown);
        item.setAttribute("aria-current", active && shown ? "page" : "false");
        item.setAttribute("aria-disabled", String(data.busy));
      });
      syncDock();
    }

    function syncChrome() {
      const pane = data.pane;
      // Corpus screens and the AI 助手 use the whole page (no title block).
      document.body.classList.toggle("interview-bare", state.view === "interview" && (pane === "corpus" || pane === "assistant"));
      // Corpus screens sit in the IELTS corpus workspace (its chrome and the many .corpus-workspace rules) too.
      document.querySelector?.(".workspace")?.classList.toggle("interview-corpus-workspace", state.view === "interview" && pane === "corpus");
      if (state.view === "interview") document.querySelector?.(".workspace")?.classList.toggle("corpus-workspace", pane === "corpus");
      // A corpus screen has the IELTS back button above it, like the P1 / P2 corpus pages (handled in initialize).
      if (state.view === "interview") byId("topbarBackCorpusBtn")?.classList.toggle("hidden", pane !== "corpus");
      if (document.body.dataset) { document.body.dataset.interviewPane = pane; document.body.dataset.interviewPart = data.part; }
      syncNav();
      const entry = PANE_COPY[pane]?.();
      if (!entry || state.view !== "interview") return;
      if (byId("viewTitle")) byId("viewTitle").textContent = entry[0];
      if (byId("viewSubtitle")) byId("viewSubtitle").textContent = entry[1];
    }

    function render({ force = false } = {}) {
      const panel = byId("interviewPanel");
      if (!panel || !state.desktopCapabilities?.mock_interview) return;
      syncChrome();
      if (!state.account.authenticated) {
        panel.innerHTML = `<div class="iv-guest"><p class="iv-kicker">Interview Studio</p><h2 class="iv-title"><span class="iv-title-main">Mock Interview</span></h2><p>${esc(copy("登录同一个 IELTS Studio 账号，保存面试回答与练习记录。", "Sign in with your Studio account to save answers and interview history."))}</p>${solid("login", copy("登录并开始", "Sign in and start"))}</div>`;
        return;
      }
      // The AI 助手 chat is a live component (a reply may be on its way): background refreshes leave it alone.
      if (data.pane === "assistant" && panel.querySelector("#ivAssistant") && !force) return;
      // Home, practice and reports are shared IELTS panels (home, iv_* and history views), not #interviewPanel.
      const paneView = ({ corpus: () => corpusScreens?.render(data.corpusTab) || "", custom: customPane, assistant: () => assistantChat?.render() || "" })[data.pane];
      if (!paneView) { panel.innerHTML = ""; return; }
      const content = paneView();
      panel.innerHTML = `<div class="iv-pane iv-pane--${data.pane}">${content}</div>`;
    }

    // ---- Inputs and actions
    function captureInput(event) {
      const el = event.target;
      const field = el.dataset.interviewField;
      if (field === "file") { data.file = el.files?.[0] || null; render(); }
      else if (field === "resumeText" || field === "jdText") {
        data[field] = el.value;
        const counter = byId("interviewCustomCount");
        if (counter) counter.textContent = copy(`${el.value.length} 字`, `${el.value.length} chars`);
      }
    }

    function handleAction(event) {
      const el = event.target.closest("[data-interview-action]");
      if (!el || data.busy) return;
      if (el.tagName === "A") event.preventDefault?.();
      const action = el.dataset.interviewAction;
      switch (action) {
        case "login": promptGuestLogin(copy("登录后保存面试记录与回答。", "Sign in to save interview practice."), { returnView: "interview" }); return;
        case "go-practice": setPane("practice", { part: el.dataset.part || "full" }); return;
        case "go-custom": data.customSide = el.dataset.side || data.customSide; setPane("custom"); return;
        case "reports": setPane("reports"); return;
        case "open-corpus": setPane("corpus", { tab: el.dataset.tab || data.corpusTab }); return;
        case "custom-side": data.customSide = el.dataset.side; render(); return;
        case "import-resume": {
          const form = new FormData();
          form.append("resume_text", data.resumeText);
          form.append("ai_source", currentAiSourcePreference());
          form.append("preview", "1");
          if (data.file) form.append("resume_file", data.file);
          perform(() => upload("/api/interview/profile/resume/", form), (payload) => {
            data.drafts.resume = payload; data.file = null;
            data.notice = copy("题卡草稿已生成，先检查一下再加入语料库。", "Draft ready — review it before adding it to your corpus.");
          });
          return;
        }
        case "import-jd":
          perform(() => request("/api/interview/profile/jd/", { job_description: data.jdText, ai_source: currentAiSourcePreference(), preview: true }), (payload) => {
            data.drafts.jd = payload;
            data.notice = copy("岗位题与反问草稿已生成，先检查一下再加入语料库。", "Draft ready — review it before adding it to your corpus.");
          });
          return;
        case "draft-edit": {
          const side = data.customSide;
          const draft = data.drafts[side]?.draft;
          const row = draftRows(side).find((item) => item.path === el.dataset.path);
          if (!draft || !row) return;
          launch?.editMarkdown({
            meta: copy(`草稿 · ${row.kind}`, `Draft · ${row.kind}`), title: row.title, label: copy("AI 草稿（可直接改）", "AI draft (edit freely)"),
            value: draftValue(draft, row.path) || "", note: copy("改完点「保存修改」，最后在右下角一起加入语料库。", "Save, then add everything to the corpus."),
            onSave: (value) => { setDraftValue(draft, row.path, value); render(); },
          });
          return;
        }
        case "draft-remove": {
          const draft = data.drafts[data.customSide]?.draft;
          if (draft) { removeDraftItem(draft, el.dataset.path); render(); }
          return;
        }
        case "draft-discard": data.drafts[data.customSide] = null; render(); return;
        case "draft-commit": {
          const side = data.customSide;
          const pending = data.drafts[side];
          if (!pending) return;
          const path = side === "resume" ? "/api/interview/profile/resume/commit/" : "/api/interview/profile/jd/commit/";
          const body = side === "resume" ? { resume_text: pending.resume_text, draft: pending.draft } : { job_description: pending.job_description, draft: pending.draft };
          perform(() => request(path, body), (payload) => {
            data.profile = payload.profile; data.corpus = payload.entries; data.drafts[side] = null;
            data.notice = side === "resume" ? copy("已加入语料库，去「简历题卡」看看。", "Added — see Resume cards.") : copy("已加入语料库，去「JD 与反问」看看。", "Added — see JD & questions.");
          });
          return;
        }
        default:
          if (PANES.has(action)) setPane(action);
      }
    }

    // Hooks for app.js's practice panel: the launch block, its attempt-start fields, and the corpus button.
    function launchOptions(view) {
      return launch?.options(view) || {};
    }

    function renderLaunch(view) {
      launch?.render(view);
      ensureOverview();
    }

    function openCorpusFor(view) {
      const part = String(view || "").replace(/^iv_/, "");
      setPane("corpus", { tab: PARTS[part]?.corpus || data.corpusTab });
    }

    // A "已写入 …" link under an assistant reply: that corpus screen, with the written card or answer open.
    function openApplied({ where, entryId }) {
      setPane("corpus", { tab: where });
      const entry = (data.corpus || []).find((item) => item.id === entryId);
      if (!entry) return;
      if (["project", "award", "jd"].includes(entry.kind)) corpusScreens?.openCard(entry);
      else corpusScreens?.openEditor(entry);
    }

    // The report's 编辑语料 on an interview turn: the corpus editor with the reference answer.
    async function openCorpusFromReport(target) {
      if (!data.corpus) await perform(() => request("/api/interview/corpus/"), (payload) => { data.corpus = payload.entries || []; }, { busy: false });
      corpusScreens?.openFromReport(target);
    }

    return {
      initialize, setProductMode, show, resetForAccount, setPane, launchOptions, renderLaunch, hideLaunch: () => launch?.hide(),
      openCorpusFor, openCorpusFromReport, corpusSavedForTarget: (target) => corpusScreens?.savedForTarget(target) ?? null, syncNav,
    };
  }
  window.IELTSInterview = { createInterview };
})();
