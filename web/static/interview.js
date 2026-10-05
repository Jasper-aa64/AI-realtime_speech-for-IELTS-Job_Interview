(function () {
  const MODES = new Set(["ielts", "interview"]);
  const PANES = new Set(["home", "practice", "reports", "report", "corpus", "custom"]);
  const MODE_KEY = "ielts-product-mode";
  // detail.design's corner morph: spring stiffness 300, damping 30, mass 1 (ζ≈0.87), sampled over 500 ms.
  const SPRING = "linear(0, 0.0458, 0.1512, 0.2813, 0.4144, 0.5381, 0.6461, 0.7364, 0.8091, 0.8658, 0.9089, 0.9407, 0.9636, 0.9794, 0.99, 0.9968, 1.0009, 1.0031, 1.0041, 1.0043, 1.0041, 1.0036, 1.003, 1.0025, 1.0019, 1.0015, 1)";
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
  const SLIDES = [
    { kicker: "Mock interview", title: ["完整面试", "Full interview"], body: ["自我介绍、项目、知识点、奖项、反问，一场走完。", "Intro, projects, knowledge, awards and your questions in one run."], pane: "practice", part: "full" },
    { kicker: "Projects", title: ["项目讲述", "Project stories"], body: ["每个项目一份讲述稿，面试官现场追问。", "One story per project, then live follow-ups."], pane: "practice", part: "project" },
    { kicker: "Knowledge", title: ["知识点", "Knowledge"], body: ["技术栈题与精选题库，答完可存成你的标准答法。", "Stack and curated questions; keep your best answers."], pane: "practice", part: "knowledge" },
    { kicker: "Report", title: ["百分制报告", "100-point report"], body: ["五个维度打分，标出能力边界和下一步。", "Five dimensions, your knowledge boundary and next steps."], pane: "reports" },
  ];

  function createInterview({ state, api, ensureCsrfToken, switchView, exitPractice, promptGuestLogin, escapeHtml, currentAiSourcePreference }) {
    let epoch = 0;
    let initialized = false;
    let requestController = null;
    let morph = null;
    let menuOpen = false;
    let hoverOpened = false;
    let hoverTimer = null;
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
        editor: null, launch: { category: "", count: 5, projectIds: new Set() },
        answer: { state: "idle", text: "", source: "typed", typing: false, error: "", peek: false }, slide: 0,
      };
    }

    function resetForAccount() {
      epoch += 1;
      requestController?.abort();
      requestController = null;
      stopRecorder();
      data = freshState();
      if (byId("interviewPanel")) render();
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
      try { localStorage.setItem(MODE_KEY, mode); } catch (_error) { /* Session-only preference. */ }
    }

    // ---- Mode switcher: the brand button grows into the card in place (shared corner, spring size, blur cross-fade).
    function reducedMotion() {
      try { return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true; } catch (_error) { return false; }
    }

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

    function animateMenu(dropdown, trigger, opening) {
      if (typeof dropdown.animate !== "function" || typeof trigger.getBoundingClientRect !== "function") return null;
      morph?.cancel();
      const from = trigger.getBoundingClientRect();
      dropdown.style.left = `${Math.round(from.left)}px`;
      dropdown.style.top = `${Math.round(from.top)}px`;
      const to = dropdown.getBoundingClientRect();
      const body = dropdown.querySelector?.(".studio-switch-body");
      // Closing holds its last frame ("forwards") until the card is hidden, so it never pops back to full size.
      const timing = (duration, extra = {}) => ({ duration, easing: SPRING, fill: opening ? "none" : "forwards", ...extra });
      if (reducedMotion()) {
        morph = dropdown.animate([{ opacity: opening ? 0 : 1 }, { opacity: opening ? 1 : 0 }], timing(120, { easing: "ease-out" }));
        return morph;
      }
      // Opening starts from the hovered trigger's tint; closing ends on the plain rail so the hand-off is seamless.
      const closed = { width: `${from.width}px`, height: `${from.height}px`, borderRadius: "10px", backgroundColor: opening ? "var(--switch-hover)" : "var(--switch-closed)", borderColor: "transparent", boxShadow: "0 0 0 rgba(0,0,0,0)" };
      const open = { width: `${to.width}px`, height: `${to.height}px`, borderRadius: "18px", backgroundColor: "var(--switch-bg)", borderColor: "var(--switch-line)", boxShadow: "var(--switch-shadow)" };
      morph = dropdown.animate(opening ? [closed, open] : [open, closed], timing(opening ? 500 : 380));
      body?.getAnimations?.().forEach((animation) => animation.cancel());
      body?.animate?.(
        opening ? [{ opacity: 0, filter: "blur(4px)" }, { opacity: 1, filter: "blur(0px)" }] : [{ opacity: 1, filter: "blur(0px)" }, { opacity: 0, filter: "blur(4px)" }],
        { duration: opening ? 200 : 100, delay: opening ? 60 : 0, easing: "ease-out", fill: opening ? "backwards" : "forwards" },
      );
      return morph;
    }

    function menu(open, restoreFocus = false, focusItem = true) {
      const trigger = byId("studioModeTrigger");
      const dropdown = byId("studioModeMenu");
      if (!trigger || !dropdown) return;
      window.clearTimeout?.(hoverTimer);
      if (menuOpen === open) {
        if (!open && restoreFocus) trigger.focus();
        return;
      }
      menuOpen = open;
      if (!open) hoverOpened = false;
      trigger.setAttribute("aria-expanded", String(open));
      byId("studioModeControl")?.classList.toggle("is-open", open);
      if (open) { syncSwitchPalette(); dropdown.hidden = false; dropdown.inert = false; }
      const animation = animateMenu(dropdown, trigger, open);
      if (!open) {
        const finish = () => { if (menuOpen) return; dropdown.hidden = true; dropdown.inert = false; animation?.cancel(); dropdown.querySelector?.(".studio-switch-body")?.getAnimations?.().forEach((item) => item.cancel()); };
        if (animation) { dropdown.inert = true; animation.finished.then(finish, () => {}); } else finish();
      }
      // The card clips while it grows; a scrolling focus would shift its content out of the shared corner.
      if (open && focusItem) { dropdown.querySelector('[aria-checked="true"]')?.focus({ preventScroll: true }); dropdown.scrollTop = 0; }
      else if (!open && restoreFocus) trigger.focus();
    }

    async function changeMode(mode, fromKeyboard = true) {
      if (mode !== state.productMode) {
        // Starting an interview must use the existing complete IELTS abort path.
        if (state.practiceLocked) await exitPractice();
        setProductMode(mode);
        switchView(mode === "interview" ? "interview" : "home", { force: true });
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
      trigger?.addEventListener("click", () => menu(!menuOpen));
      // Pointer intent opens it like detail.design; a short grace period lets the cursor travel into the card.
      const control = byId("studioModeControl");
      control?.addEventListener("pointerenter", (event) => {
        if (event.pointerType !== "mouse") return;
        window.clearTimeout?.(hoverTimer);
        syncSwitchPalette();
        if (!menuOpen) hoverTimer = window.setTimeout?.(() => { menu(true, false, false); hoverOpened = true; }, 90);
      });
      control?.addEventListener("pointerleave", (event) => {
        if (event.pointerType !== "mouse") return;
        window.clearTimeout?.(hoverTimer);
        if (menuOpen) hoverTimer = window.setTimeout?.(() => menu(false), 240);
      });
      trigger?.addEventListener("keydown", (event) => {
        if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); menu(true); }
      });
      byId("studioModeMenu")?.addEventListener("click", (event) => {
        const closer = event.target.closest?.("[data-studio-close]");
        if (closer?.dataset && "studioClose" in closer.dataset) { if (!hoverOpened) menu(false, true); return; }
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
      document.addEventListener("pointerdown", (event) => { if (!byId("studioModeControl")?.contains(event.target)) menu(false); });
      document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (data.editor) { data.editor = null; render(); return; }
        menu(false, menuOpen);
      });
      window.addEventListener?.("resize", () => menu(false));
      byId("interviewNav")?.addEventListener("click", (event) => {
        const item = event.target.closest("[data-interview-pane]");
        if (!item) return;
        event.preventDefault?.();
        setPane(item.dataset.interviewPane, { part: item.dataset.interviewPart });
      });
      byId("interviewPanel")?.addEventListener("click", handleAction);
      byId("interviewPanel")?.addEventListener("animationend", (event) => {
        if (data.pane === "home" && event.target.closest?.(".hx-seg.is-on")) showSlide(data.slide + 1);
      });
      const hold = (event, on) => event.target.closest?.(".hx-show")?.classList.toggle("is-paused", on);
      byId("interviewPanel")?.addEventListener("pointerover", (event) => hold(event, true));
      byId("interviewPanel")?.addEventListener("pointerout", (event) => { if (!event.relatedTarget?.closest?.(".hx-show")) hold(event, false); });
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

    function loadCorpus() {
      return perform(() => request("/api/interview/corpus/"), (payload) => { data.corpus = payload.entries || []; });
    }

    function show() {
      if (!state.desktopCapabilities?.mock_interview) return;
      render();
      if (state.account.authenticated && !data.corpus && !data.busy) loadOverview();
    }

    function setPane(pane, { part } = {}) {
      if (!PANES.has(pane) || data.busy) return;
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
      if (pane === "reports") loadHistory();
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

    // ---- Home: the IELTS home markup (hx-*), styled by the shared #homePanel/#interviewHome rules.
    const link = (action, content, { cls = "", attrs = "" } = {}) => `<a class="${cls}" href="?view=interview" data-interview-action="${action}" ${attrs}>${content}</a>`;

    function home() {
      const studio = data.sessions.filter((item) => item.part);
      const scored = studio.filter((item) => item.score?.status === "ready");
      const average = scored.length ? Math.round(scored.reduce((sum, item) => sum + item.score.total, 0) / scored.length) : null;
      const stats = corpusStats();
      const resume = data.profile?.resume?.updated_at;
      const stat = (dt, dd, attrs = "") => `<div class="hx-stat"><dt>${esc(dt)}</dt><dd ${attrs}>${dd}</dd></div>`;
      const slides = SLIDES.map((slide, index) => link("slide-open", `
          <span class="hx-slide-media"><span class="iv-slide-art iv-slide-art--${index}" aria-hidden="true"><span></span><span></span><span></span></span><span class="hx-slide-chip">${esc(slide.kicker)}</span></span>
          <span class="hx-slide-body"><strong>${esc(pick(slide.title))}</strong><span>${esc(pick(slide.body))}</span></span>`,
        { cls: `hx-slide${index === data.slide ? " is-active" : ""}`, attrs: `data-index="${index}" aria-roledescription="slide" ${index === data.slide ? "" : 'aria-hidden="true" tabindex="-1"'}` })).join("");
      const segs = SLIDES.map((_slide, index) => `<button type="button" class="hx-seg${index === data.slide ? " is-on" : ""}${index < data.slide ? " is-done" : ""}" data-interview-action="slide-go" data-index="${index}" aria-label="${index + 1} / ${SLIDES.length}"><i></i></button>`).join("");
      const areaLink = (action, label, text, attrs = "") => `<li>${link(action, `<b>${esc(label)}</b><span>${esc(text)}</span><i aria-hidden="true">→</i>`, { attrs })}</li>`;
      return `<section id="interviewHome" class="hx-home" aria-label="${esc(copy("面试首页", "Interview home"))}">
          <div class="hx-hero">
            <div class="hx-intro">
              <p class="hx-kicker">Interview Studio</p>
              <h2 class="hx-title"><span class="hx-title-top">${esc(copy("把做过的系统，讲成面试官想听的答案", "Turn what you built into answers that land"))}</span><em class="hx-title-main">Mock Interview</em></h2>
              <p class="hx-topics"><span>${esc(copy("项目", "Projects"))}</span><i aria-hidden="true">|</i><span>${esc(copy("知识点", "Knowledge"))}</span><i aria-hidden="true">|</i><span>${esc(copy("语料", "Corpus"))}</span><i aria-hidden="true">|</i><span>${esc(copy("报告", "Reports"))}</span></p>
              <div class="hx-actions">${link("go-practice", `${esc(copy("开始完整面试", "Start a full interview"))} <span aria-hidden="true">→</span>`, { cls: "hx-btn hx-btn--solid", attrs: 'data-part="full"' })}${link("go-custom", `${esc(resume ? copy("更新简历 / JD", "Update resume / JD") : copy("上传简历", "Upload resume"))} <span aria-hidden="true">→</span>`, { cls: "hx-btn" })}</div>
            </div>
            <section class="hx-show" aria-roledescription="carousel" aria-label="${esc(copy("功能一览", "Highlights"))}">
              <div class="hx-stage">${slides}<span class="hx-count" aria-hidden="true"><b data-hx-count>${pad(data.slide + 1)}</b><i>/</i>${pad(SLIDES.length)}</span></div>
              <div class="hx-bar"><div class="hx-progress">${segs}</div>
                <button type="button" class="hx-nav" data-interview-action="slide-prev" aria-label="${esc(copy("上一张", "Previous"))}"><svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="M10 3 5 8l5 5"></path></svg></button>
                <button type="button" class="hx-nav" data-interview-action="slide-next" aria-label="${esc(copy("下一张", "Next"))}"><svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="m6 3 5 5-5 5"></path></svg></button></div>
            </section>
            <aside class="hx-panel" aria-label="${esc(copy("面试数据", "Interview data"))}">
              <dl class="hx-stats">${stat(copy("面试场次", "Sessions"), data.sessionsLoaded ? link("reports", String(studio.length)) : "–")}${stat(copy("平均分", "Average"), average ?? "–")}${stat(copy("最近练习", "Last"), studio[0] ? esc(dateText(studio[0].created_at, false)) : "–", 'class="hx-stat-date"')}</dl>
              <p class="hx-panel-label">${esc(copy("语料待完善", "Corpus to finish"))}</p>
              <div class="hx-chips">${CORPUS_TABS.map((tab) => { const entries = corpusEntries(tab.kinds); const left = entries.filter((e) => !e.corpus_text).length; return link("open-corpus", `${esc(copy(tab.zh, tab.en))}<sup>${left || ""}</sup>`, { cls: `hx-chip${left ? " is-due" : ""}`, attrs: `data-tab="${tab.id}"` }); }).join("")}</div>
              <p class="hx-panel-label">${esc(copy("练习", "Practice"))} · <span>${esc(resume ? copy(`简历已拆分 · 已备 ${stats.ready}/${stats.total}`, `Resume split · ${stats.ready}/${stats.total} ready`) : copy("还没上传简历", "No resume yet"))}</span></p>
              <div class="hx-chips">${Object.keys(PARTS).map((part) => link("go-practice", esc(partName(part)), { cls: "hx-chip", attrs: `data-part="${part}"` })).join("")}${link("go-custom", `${esc(copy("简历 / JD", "Resume / JD"))} →`, { cls: "hx-chip hx-chip--more" })}</div>
            </aside>
          </div>
          <section class="hx-areas" aria-label="${esc(copy("练习路径", "Practice paths"))}">
            <header class="hx-sec-head"><p class="hx-eyebrow">Practice paths</p>${link("open-corpus", `${esc(copy("进入面试语料库", "Open the corpus"))} <span aria-hidden="true">→</span>`, { cls: "hx-sec-more", attrs: 'data-tab="project"' })}</header>
            <div class="hx-area-grid">
              <article class="hx-area"><span class="hx-area-index">01 · Interview</span><h3 class="hx-area-name">${esc(copy("面试练习", "Practice"))}</h3><p class="hx-area-blurb">${esc(copy("面试官按你的回答追问或换题，追问压力会一直问到你的边界。", "The interviewer follows up or moves on; pressure mode digs to your limit."))}</p>
                <ul class="hx-area-links">${areaLink("go-practice", "Mock", copy("完整面试", "Full interview"), 'data-part="full"')}${areaLink("go-practice", "Project", copy("项目深挖", "Projects"), 'data-part="project"')}${areaLink("go-practice", "Stack", copy("知识点", "Knowledge"), 'data-part="knowledge"')}${areaLink("go-practice", "Ask", copy("反问环节", "Your questions"), 'data-part="reverse"')}</ul></article>
              <article class="hx-area"><span class="hx-area-index">02 · Corpus</span><h3 class="hx-area-name">${esc(copy("面试语料", "Corpus"))}</h3><p class="hx-area-blurb">${esc(copy("项目讲述稿、知识点答法、自我介绍和反问，像雅思语料一样随时调出。", "Stories, answers, intro and questions to ask — ready like the IELTS corpus."))}</p>
                <ul class="hx-area-links">${CORPUS_TABS.map((tab) => areaLink("open-corpus", tab.id === "story" ? "Intro" : tab.id === "jd" ? "JD" : tab.id === "project" ? "Project" : "Stack", copy(tab.zh, tab.en), `data-tab="${tab.id}"`)).join("")}</ul></article>
              <article class="hx-area"><span class="hx-area-index">03 · Review</span><h3 class="hx-area-name">${esc(copy("面试报告", "Reports"))}</h3><p class="hx-area-blurb">${esc(copy("百分制五维打分，标出能力边界，逐题点评可直接存成你的答法。", "100-point score in five dimensions, your boundary, notes you can keep."))}</p>
                <ul class="hx-area-links">${studio.slice(0, 2).map((item) => areaLink("open-session", item.score?.status === "ready" ? String(item.score.total) : "—", item.title, `data-session-id="${esc(item.id)}"`)).join("")}${areaLink("reports", "All", copy("全部报告", "All reports"))}${areaLink("go-custom", "CV", copy("简历 / JD 定制", "Resume / JD"))}</ul></article>
            </div>
          </section>
        </section>`;
    }

    // ---- Practice: the IELTS practice panel, with the interviewer in the prompt pane.
    function activeSession() {
      const current = data.current;
      return current?.session?.status === "active" && current.session.part === data.part ? current : null;
    }

    function stageTrack(session, turns) {
      const plan = session?.plan?.length ? session.plan : data.part === "full" ? ["self_intro", "project", "knowledge", "award", "reverse"] : [];
      if (!plan.length) return "";
      const currentStage = data.current?.current_turn?.stage;
      return `<ol class="iv-stage-track">${plan.map((stage) => {
        const ofStage = turns.filter((turn) => turn.stage === stage);
        const done = ofStage.length && ofStage.every((turn) => turn.status !== "pending");
        const cls = stage === currentStage ? "is-current" : done ? "is-done" : "";
        return `<li class="${cls}"><span>${esc(stageName(stage))}</span>${ofStage.length ? `<small>${ofStage.filter((turn) => turn.status !== "pending").length}/${ofStage.length}</small>` : ""}</li>`;
      }).join("")}</ol>`;
    }

    function launchOptions() {
      const part = data.part;
      const projects = corpusEntries(["project"]).filter((entry) => !entry.orphaned);
      if ((part === "full" || part === "project") && !projects.length) {
        return `<div class="iv-launch-note"><strong>${esc(copy("先上传简历", "Upload your resume first"))}</strong><p>${esc(copy("完整面试和项目练习会按你简历里的每个项目提问。", "The full interview and project practice ask about each project on your resume."))}</p>${solid("go-custom", copy("去上传简历", "Upload resume"))}</div>`;
      }
      if (part === "project") {
        return `<div class="iv-launch-options"><p class="iv-panel-label">${esc(copy("选择项目（不选则全部）", "Projects (none = all)"))}</p>${projects.map((entry) => `<label class="iv-check"><input type="checkbox" data-interview-field="project" value="${esc(entry.id)}" ${data.launch.projectIds.has(entry.id) ? "checked" : ""}><span>${esc(entry.title || entry.question)}</span></label>`).join("")}</div>`;
      }
      if (part === "knowledge") {
        const chips = [{ id: "", label: copy("综合（技术栈优先）", "Mixed (stack first)") }, ...data.categories].map((item) => button("launch-category", esc(item.label), { cls: `iv-chip${data.launch.category === item.id ? " is-on" : ""}`, attrs: `data-category="${esc(item.id)}"` })).join("");
        return `<div class="iv-launch-options"><p class="iv-panel-label">${esc(copy("方向", "Topic"))}</p><div class="iv-chips">${chips}</div><p class="iv-panel-label">${esc(copy("题量", "Questions"))}</p><div class="iv-seg">${[3, 5, 8].map((n) => button("launch-count", String(n), { cls: data.launch.count === n ? "is-on" : "", attrs: `data-count="${n}"` })).join("")}</div></div>`;
      }
      return "";
    }

    // Same length classes as the IELTS prompt card (short / medium / long).
    function promptCard(textValue, extra = "") {
      const size = textValue.length <= 36 ? "short-prompt" : textValue.length <= 90 ? "medium-prompt" : "long-prompt";
      return `<div class="prompt-card ${size} ${extra}">${esc(textValue)}</div>`;
    }

    function promptPane(current) {
      if (!current) {
        const part = PARTS[data.part];
        return `<div class="section-label">${esc(copy("面试官", "Interviewer"))}</div>
          ${promptCard(copy(`点击「开始」，${data.part === "reverse" ? "面试官会请你提问。" : data.part === "knowledge" ? "面试官会连续问知识点。" : "面试官会先请你做自我介绍。"}`, `Press Start. ${pick(part.hint)}`), "iv-prompt-idle")}
          <p class="iv-prompt-hint">${esc(pick(part.hint))}</p>${launchOptions()}`;
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
      return `<button type="button" class="record-control ${cls}" data-interview-action="${action}" ${disabled || (data.busy && stateName !== "thinking") ? "disabled" : ""}><span class="iv-record-icon" aria-hidden="true"></span><strong>${esc(title)}</strong><small>${esc(hint)}</small>${cls === "examiner" || cls === "processing" || cls === "loading" ? '<div class="analyzing-dots"><span></span><span></span><span></span></div>' : ""}</button>`;
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

    function practice() {
      const current = activeSession();
      const turns = current?.turns || [];
      const done = turns.filter((turn) => turn.status !== "pending").length;
      const pressure = (current?.session?.intensity || data.intensity) === "pressure";
      const tab = PARTS[data.part].corpus;
      const tabLabel = CORPUS_TABS.find((item) => item.id === tab);
      return `<section class="iv-practice">
          <div class="iv-practice-head">
            <div class="iv-practice-title"><strong>${esc(partName(data.part))} ${esc(current ? `· ${stageName(current.current_turn?.stage) || copy("收尾", "Wrap-up")}` : copy("准备就绪", "Ready"))}</strong><small>${current ? `${done} / ${turns.length}` : "READY"}</small></div>
            <div class="iv-practice-tools"><span class="iv-mode-label">${esc(copy("面试节奏", "Pace"))}</span>
              <div class="p3-mode-switch${pressure ? " high-intensity" : ""}" role="group" aria-label="${esc(copy("面试强度", "Intensity"))}">
                ${button("intensity", esc(copy("标准模式", "Standard")), { cls: `p3-mode-option${pressure ? "" : " active"}`, attrs: 'data-intensity="standard"', disabled: !!current })}
                ${button("intensity", esc(copy("追问压力", "Pressure")), { cls: `p3-mode-option${pressure ? " active" : ""}`, attrs: 'data-intensity="pressure"', disabled: !!current })}
              </div>
              <button type="button" class="p1-corpus-entry" data-interview-action="open-corpus" data-tab="${tab}"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg><span>${esc(copy(`我的${tabLabel.zh}语料`, `My ${tabLabel.en.toLowerCase()} corpus`))}</span></button>
            </div>
          </div>
          ${stageTrack(current?.session, turns)}
          <div class="practice-grid iv-practice-grid">
            <article class="prompt-pane">${promptPane(current)}</article>
            <article class="recorder-pane">${recorderPane(current)}</article>
          </div>
        </section>`;
    }

    // ---- Report: 100-point score with dimensions, boundary and per-turn notes.
    function reportPane() {
      const current = data.current;
      if (!current) return reports();
      const { session, turns = [] } = current;
      const score = session.score;
      const comments = Object.fromEntries((score?.per_turn || []).map((item) => [item.turn_id, item.comment]));
      const hero = score?.status === "ready"
        ? `<div class="iv-score"><div class="iv-score-total"><strong>${score.total}</strong><span>/ 100</span></div><p>${esc(score.summary)}</p></div>
          <div class="iv-dimensions">${score.dimensions.map((dim) => `<div class="iv-dimension"><div><span>${esc(dim.label)}</span><b>${dim.score}<small> / ${dim.max}</small></b></div><div class="iv-meter"><span style="width:${Math.round((dim.score / dim.max) * 100)}%"></span></div><p>${esc(dim.evidence)}</p></div>`).join("")}</div>
          ${score.boundary ? `<article class="iv-boundary"><p class="iv-eyebrow">${esc(copy("能力边界", "Boundary"))}</p><p>${esc(score.boundary)}</p></article>` : ""}
          ${score.next_steps?.length ? `<article class="iv-boundary"><p class="iv-eyebrow">${esc(copy("下一步", "Next steps"))}</p><ul>${score.next_steps.map((step) => `<li>${esc(step)}</li>`).join("")}</ul></article>` : ""}`
        : score?.status === "failed"
          ? `<div class="iv-error" role="alert">${esc(score.error || copy("评分生成失败。", "Scoring failed."))}</div>${solid("score", copy("重新生成百分制报告", "Retry scoring"))}`
          : session.status === "completed"
            ? `<div class="iv-score iv-score--pending"><p>${esc(data.busy ? copy("正在生成百分制报告…", "Scoring…") : copy("还没有评分。", "Not scored yet."))}</p>${data.busy ? "" : solid("score", copy("生成百分制报告", "Get the 100-point report"))}</div>` : "";
      const rows = turns.map((turn) => {
        const decision = turn.decision?.signal ? `<em class="iv-signal is-${esc(turn.decision.signal)}">${esc(pick(SIGNALS[turn.decision.signal] || SIGNALS.adequate))}</em>` : "";
        return `<li class="is-${esc(turn.status)}${turn.kind === "follow_up" ? " is-follow" : ""}"><span class="iv-q-index">${turn.kind === "follow_up" ? "↳" : pad(turn.order)}</span><div>
          <small>${esc(stageName(turn.stage) || "")}${turn.kind === "follow_up" ? ` · ${esc(copy("追问", "Follow-up"))}` : ""}${turn.answer_source === "voice" ? ` · ${esc(copy("语音", "Voice"))}` : ""} ${decision}</small>
          <h3>${esc(turn.prompt)}</h3><p>${esc(turn.answer || copy("本题未回答。", "No answer."))}</p>
          ${turn.reply ? `<div class="iv-reply"><span>${esc(copy("面试官", "Interviewer"))}</span><p>${esc(turn.reply)}</p></div>` : ""}
          ${turn.decision?.evidence ? `<p class="iv-note">${esc(turn.decision.evidence)}</p>` : ""}
          ${comments[turn.id] ? `<p class="iv-note iv-note--comment">${esc(comments[turn.id])}</p>` : ""}
          ${turn.status === "completed" ? button("save-corpus", esc(copy("存为我的答法", "Save to my corpus")), { cls: "iv-link", attrs: `data-turn-id="${esc(turn.id)}"` }) : ""}
        </div></li>`;
      }).join("");
      return `<header class="iv-report-head">${kicker(`${partName(session.part) || session.title} · ${session.intensity === "pressure" ? copy("追问压力", "Pressure") : copy("标准模式", "Standard")}`)}<h2>${esc(session.title)}</h2><p>${esc(dateText(session.created_at))}</p></header>
        ${hero}
        <p class="iv-voice-note"><span class="iv-dot" aria-hidden="true"></span>${esc(score?.limitations || copy("百分制由 AI 根据本次文字回答（含语音转写稿）估计，不评估发音，也不代表真实招聘结果。", "The score is an AI estimate from this session's text answers; no pronunciation, and not a hiring decision."))}</p>
        <div class="iv-actions">${solid("go-practice", copy("再练一场", "Practice again"), { attrs: `data-part="${esc(session.part || "knowledge")}"` })}${quiet("reports", copy("全部报告", "All reports"))}</div>
        <ol class="iv-transcript">${rows}</ol>`;
    }

    function reports() {
      const rows = data.sessions.map((session) => `<li>${button("open-session", `<time>${esc(dateText(session.created_at))}</time><span class="iv-history-title"><strong>${esc(session.title)}</strong><small>${esc(partName(session.part) || copy("文字练习", "Text practice"))}${session.intensity === "pressure" ? ` · ${esc(copy("追问压力", "Pressure"))}` : ""}</small></span><em class="iv-status is-${esc(session.status)}">${esc(session.status === "active" ? copy("进行中", "In progress") : session.status === "completed" ? copy("已完成", "Completed") : copy("已结束", "Ended"))}</em><b class="iv-history-score">${session.score?.status === "ready" ? esc(session.score.total) : "—"}</b><i aria-hidden="true">→</i>`, { cls: "iv-history-row", attrs: `data-session-id="${esc(session.id)}"` })}</li>`).join("");
      return `<div class="iv-toolbar"><span class="iv-toolbar-note">${esc(copy(`共 ${data.sessions.length} 场`, `${data.sessions.length} sessions`))}</span>${quiet("reload-history", copy("刷新", "Refresh"))}</div>
        ${rows ? `<ol class="iv-history">${rows}</ol>` : `<div class="iv-empty-card"><p>${esc(copy("还没有面试报告。练完一场就会出现在这里。", "No reports yet. Finish a session to see it here."))}</p>${solid("go-practice", copy("开始练习", "Start practice"), { attrs: 'data-part="full"' })}</div>`}`;
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
    function customPane() {
      const side = data.customSide;
      const profile = data.profile || { resume: {}, jd: {} };
      const modules = profile.resume?.modules || [];
      const count = (kind) => modules.filter((item) => item.kind === kind).length;
      const resumeSummary = profile.resume?.updated_at
        ? `<div class="iv-summary-card"><p class="iv-eyebrow">${esc(copy("已拆分", "Split"))} · ${esc(dateText(profile.resume.updated_at))}</p><p>${esc(copy(`自我介绍 · ${count("project")} 个项目 · 技术栈 ${count("tech_stack")} 组 · 奖项 ${count("award")} 项`, `Intro · ${count("project")} projects · ${count("tech_stack")} stack areas · ${count("award")} awards`))}</p><div class="iv-chips">${modules.filter((item) => item.kind === "project").map((item) => `<span class="iv-chip">${esc(item.title)}</span>`).join("")}</div>${button("open-corpus", `${esc(copy("去语料库修改讲述稿", "Edit stories in the corpus"))}${ARROW}`, { cls: "iv-link", attrs: 'data-tab="project"' })}</div>` : "";
      const jdSummary = profile.jd?.updated_at
        ? `<div class="iv-summary-card"><p class="iv-eyebrow">${esc(copy("岗位", "Role"))} · ${esc(dateText(profile.jd.updated_at))}</p><p><strong>${esc(profile.jd.summary?.role || "")}</strong></p><ul>${(profile.jd.summary?.requirements || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul>${button("open-corpus", `${esc(copy("查看岗位题与反问", "See role questions"))}${ARROW}`, { cls: "iv-link", attrs: 'data-tab="jd"' })}</div>` : "";
      const form = side === "resume"
        ? `<section class="iv-sheet"><div class="iv-step"><span>01</span><h3>${esc(copy("简历", "Resume"))}</h3></div>
            <label class="iv-drop"><input type="file" accept="application/pdf,.pdf" data-interview-field="file"><strong>${esc(data.file?.name || copy("选择 PDF 简历", "Choose a PDF resume"))}</strong><small>${esc(copy("最多 2 MB · 扫描件请改用下方粘贴文字", "Up to 2 MB · paste text for scanned files"))}</small></label>
            <label class="iv-field">${esc(copy("或粘贴简历文字", "Or paste resume text"))}<textarea rows="10" maxlength="24000" data-interview-field="resumeText">${esc(data.resumeText)}</textarea></label>
            <p class="iv-note">${esc(copy("拆成：自我介绍、每个项目的讲述稿与预判追问、技术栈知识点、奖项。重新拆分不会覆盖你已经改写的答法。", "Splits into intro, a story and likely follow-ups per project, stack questions and awards. Re-splitting never overwrites what you wrote."))}</p>
            <div class="iv-row"><span class="iv-dock-spacer"></span>${solid("import-resume", profile.resume?.updated_at ? copy("重新拆分简历", "Split again") : copy("拆分简历", "Split resume"))}</div></section>`
        : `<section class="iv-sheet"><div class="iv-step"><span>01</span><h3>${esc(copy("岗位描述（JD）", "Job description"))}</h3></div>
            <label class="iv-field"><span class="sr-only">JD</span><textarea rows="14" maxlength="12000" data-interview-field="jdText" placeholder="${esc(copy("粘贴目标岗位的职责与要求……", "Paste the role's responsibilities and requirements…"))}">${esc(data.jdText)}</textarea></label>
            <p class="iv-note">${esc(copy("生成岗位相关题和反问环节的问题，都会进入语料库。", "Creates role questions and questions to ask; both go to your corpus."))}</p>
            <div class="iv-row"><span class="iv-dock-spacer"></span>${solid("import-jd", profile.jd?.updated_at ? copy("重新生成", "Regenerate") : copy("生成岗位题与反问", "Generate"))}</div></section>`;
      return `<div class="iv-switch-row"><div class="iv-seg iv-seg--wide" role="tablist">${button("custom-side", esc(copy("简历", "Resume")), { cls: side === "resume" ? "is-on" : "", attrs: `role="tab" aria-selected="${side === "resume"}" data-side="resume"` })}${button("custom-side", "JD", { cls: side === "jd" ? "is-on" : "", attrs: `role="tab" aria-selected="${side === "jd"}" data-side="jd"` })}</div>
          <p class="iv-lede">${esc(copy("内容会发送到你选择的 AI 服务；服务器不保存简历文件。", "Content goes to your selected AI service; resume files are not stored."))}</p></div>
        <div class="iv-custom">${form}<div class="iv-custom-side">${(side === "resume" ? resumeSummary : jdSummary) || `<div class="iv-empty-card"><p>${esc(side === "resume" ? copy("拆分完成后，这里会列出识别到的项目和模块。", "Projects and modules appear here after splitting.") : copy("生成后，这里会显示岗位方向和核心要求。", "The role and its core requirements appear here."))}</p></div>`}</div></div>`;
    }

    const PANE_COPY = {
      practice: () => [partName(data.part), pick(PARTS[data.part].hint)],
      reports: () => [copy("面试报告", "Interview reports"), copy("每一场的百分制、能力边界和逐题点评。", "Scores, boundaries and per-question notes for every session.")],
      custom: () => [copy("简历 / JD 定制", "Resume / JD"), copy("把简历和目标岗位拆成可练的语料。", "Turn your resume and target role into practice material.")],
    };

    function syncChrome() {
      const pane = data.pane;
      const bare = pane === "home" || pane === "report" || pane === "corpus";
      document.body.classList.toggle("interview-bare", state.view === "interview" && bare);
      document.querySelector?.(".workspace")?.classList.toggle("interview-corpus-workspace", state.view === "interview" && pane === "corpus");
      if (document.body.dataset) { document.body.dataset.interviewPane = pane; document.body.dataset.interviewPart = data.part; }
      document.querySelectorAll("#interviewNav [data-interview-pane]").forEach((item) => {
        const itemPane = item.dataset.interviewPane;
        const active = itemPane === "practice" ? pane === "practice" && item.dataset.interviewPart === data.part
          : itemPane === pane || (pane === "report" && itemPane === "reports");
        item.classList.toggle("active", active && state.view === "interview");
        item.setAttribute("aria-current", active ? "page" : "false");
        item.setAttribute("aria-disabled", String(data.busy));
      });
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
      const content = ({ home, practice, reports, report: reportPane, corpus: corpusPane, custom: customPane })[data.pane]();
      const status = `<div id="interviewStatus" class="iv-status-line" role="status" aria-live="polite">${data.busy && data.answer.state !== "thinking" ? `<span class="iv-spinner" aria-hidden="true"></span>${esc(copy("正在处理…", "Working…"))}` : esc(data.notice)}</div>`;
      panel.innerHTML = `${status}${data.error ? `<div class="iv-error" role="alert">${esc(data.error)}</div>` : ""}<div class="iv-pane iv-pane--${data.pane}">${content}</div>${editorModal()}`;
    }

    // ---- Carousel: same behaviour as home-dashboard.js — the active segment fills (CSS animation)
    // and its animationend advances; hover/focus pauses. Classes only, no re-render.
    function showSlide(index) {
      data.slide = (index + SLIDES.length) % SLIDES.length;
      const show = byId("interviewPanel")?.querySelector?.("#interviewHome .hx-show");
      if (!show) return;
      show.querySelectorAll(".hx-slide").forEach((slide, i) => {
        const on = i === data.slide;
        slide.classList.toggle("is-active", on);
        slide.toggleAttribute("aria-hidden", !on);
        slide.tabIndex = on ? 0 : -1;
      });
      show.querySelectorAll(".hx-seg").forEach((seg, i) => {
        seg.classList.toggle("is-on", i === data.slide);
        seg.classList.toggle("is-done", i < data.slide);
        const bar = seg.querySelector("i");
        if (bar && i === data.slide) { bar.style.animation = "none"; void bar.offsetWidth; bar.style.animation = ""; }
      });
      const count = show.querySelector("[data-hx-count]");
      if (count) count.textContent = pad(data.slide + 1);
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
      else if (field === "resumeText" || field === "jdText") data[field] = el.value;
      else if (field === "project" && event.type === "change") {
        el.checked ? data.launch.projectIds.add(el.value) : data.launch.projectIds.delete(el.value);
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
      const sessionId = data.current?.session?.id;
      const base = sessionId ? `/api/interview/sessions/${encodeURIComponent(sessionId)}/` : "";
      switch (action) {
        case "login": promptGuestLogin(copy("登录后保存面试记录与回答。", "Sign in to save interview practice."), { returnView: "interview" }); return;
        case "go-practice": setPane("practice", { part: el.dataset.part || "full" }); return;
        case "go-custom": data.customSide = el.dataset.side || data.customSide; setPane("custom"); return;
        case "reports": setPane("reports"); return;
        case "reload-history": loadHistory(); return;
        case "slide-prev": showSlide(data.slide - 1); return;
        case "slide-next": showSlide(data.slide + 1); return;
        case "slide-go": showSlide(Number(el.dataset.index) || 0); return;
        case "slide-open": { const slide = SLIDES[Number(el.dataset.index)] || SLIDES[0]; setPane(slide.pane, { part: slide.part }); return; }
        case "open-corpus": data.corpusTab = el.dataset.tab || data.corpusTab; setPane("corpus"); return;
        case "corpus-tab": data.corpusTab = el.dataset.tab; render(); return;
        case "custom-side": data.customSide = el.dataset.side; render(); return;
        case "intensity": data.intensity = el.dataset.intensity; render(); return;
        case "launch-category": data.launch.category = el.dataset.category || ""; render(); return;
        case "launch-count": data.launch.count = Number(el.dataset.count) || 5; render(); return;
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
              perform(() => request(`/api/interview/sessions/${encodeURIComponent(session.id)}/report/`, { ai_source: currentAiSourcePreference() }), acceptSession);
            }
          });
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
