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
      source: () => data,
      onProfile: (payload) => { data.profile = payload.profile; data.corpus = payload.entries || data.corpus; window.IELTSInterviewHome?.refresh(); },
    }) || null;
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
        pane: "home", part: "full", busy: false, error: "", notice: "",
        questions: [], categories: [], sessions: [], sessionsLoaded: false,
        corpus: null, corpusTab: "project", profile: null, customSide: "resume", resumeText: "", file: null, jdText: "",
        editor: null,
      };
    }

    function resetForAccount() {
      epoch += 1;
      requestController?.abort();
      requestController = null;
      data = freshState();
      launch?.reset();
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
      if (part && PARTS[part]) data.part = part;
      data.pane = pane;
      data.error = "";
      data.editor = null;
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
      custom: () => [copy("简历 / JD 定制", "Resume / JD"), copy("把简历和目标岗位拆成可练的语料。", "Turn your resume and target role into practice material.")],
    };

    function syncNav() {
      const practiceView = /^iv_/.test(state.view || "");
      if (practiceView) { data.pane = "practice"; data.part = state.view.slice(3); }
      if (state.view === "history") data.pane = "reports";
      const pane = data.pane;
      if (document.body.dataset) { document.body.dataset.interviewPane = pane; document.body.dataset.interviewPart = data.part; }
      const shown = practiceView || state.view === "history" || (state.view === "interview" && pane !== "home") || (state.view === "home" && pane === "home");
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
      document.body.classList.toggle("interview-bare", state.view === "interview" && pane === "corpus");
      document.querySelector?.(".workspace")?.classList.toggle("interview-corpus-workspace", state.view === "interview" && pane === "corpus");
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
      // Home, practice and reports are shared IELTS panels (home, iv_* and history views), not #interviewPanel.
      const paneView = ({ corpus: corpusPane, custom: customPane })[data.pane];
      if (!paneView) { panel.innerHTML = ""; return; }
      const content = paneView();
      const status = `<div id="interviewStatus" class="iv-status-line" role="status" aria-live="polite">${data.busy ? `<span class="iv-spinner" aria-hidden="true"></span>${esc(copy("正在处理…", "Working…"))}` : esc(data.notice)}</div>`;
      panel.innerHTML = `${status}${data.error ? `<div class="iv-error" role="alert">${esc(data.error)}</div>` : ""}<div class="iv-pane iv-pane--${data.pane}">${content}</div>${editorModal()}`;
    }

    // ---- Inputs and actions
    function captureInput(event) {
      const el = event.target;
      const field = el.dataset.interviewField;
      if (field === "editor-text" && data.editor) data.editor.text = el.value;
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
      switch (action) {
        case "login": promptGuestLogin(copy("登录后保存面试记录与回答。", "Sign in to save interview practice."), { returnView: "interview" }); return;
        case "go-practice": setPane("practice", { part: el.dataset.part || "full" }); return;
        case "go-custom": data.customSide = el.dataset.side || data.customSide; setPane("custom"); return;
        case "reports": setPane("reports"); return;
        case "open-corpus": data.corpusTab = el.dataset.tab || data.corpusTab; setPane("corpus"); return;
        case "corpus-tab": data.corpusTab = el.dataset.tab; render(); return;
        case "custom-side": data.customSide = el.dataset.side; render(); return;
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
      data.corpusTab = PARTS[part]?.corpus || data.corpusTab;
      setPane("corpus");
    }

    return { initialize, setProductMode, show, resetForAccount, setPane, launchOptions, renderLaunch, hideLaunch: () => launch?.hide(), openCorpusFor, syncNav };
  }
  window.IELTSInterview = { createInterview };
})();
