(function () {
  const MODES = new Set(["ielts", "interview"]);
  const PANES = new Set(["home", "bank", "custom", "history", "session"]);
  const MODE_KEY = "ielts-product-mode";
  const COUNTS = [3, 5, 8];
  // detail.design's corner morph: spring stiffness 300, damping 30, mass 1 (ζ≈0.87), sampled over 500 ms.
  const SPRING = "linear(0, 0.0458, 0.1512, 0.2813, 0.4144, 0.5381, 0.6461, 0.7364, 0.8091, 0.8658, 0.9089, 0.9407, 0.9636, 0.9794, 0.99, 0.9968, 1.0009, 1.0031, 1.0041, 1.0043, 1.0041, 1.0036, 1.003, 1.0025, 1.0019, 1.0015, 1)";
  const ARROW = '<span class="iv-arrow" aria-hidden="true">→</span>';

  function createInterview({ state, api, ensureCsrfToken, switchView, exitPractice, promptGuestLogin, escapeHtml, currentAiSourcePreference }) {
    let epoch = 0;
    let initialized = false;
    let requestController = null;
    let morph = null;
    let menuOpen = false;
    let hoverOpened = false;
    let hoverTimer = null;
    let data = freshState();
    const byId = (id) => document.getElementById(id);
    const copy = (zh, en) => state.uiLanguage === "en" ? en : zh;
    const esc = (value) => escapeHtml(String(value ?? ""));
    const pad = (value) => String(value).padStart(2, "0");
    const label = (value) => ({ active: copy("进行中", "In progress"), completed: copy("已完成", "Completed"), aborted: copy("已结束", "Ended"), pending: copy("待回答", "Pending"), skipped: copy("已跳过", "Skipped"), main: copy("主问题", "Main question"), follow_up: copy("追问", "Follow-up"), intermediate: copy("进阶", "Intermediate"), medium: copy("进阶", "Intermediate"), advanced: copy("深入", "Advanced"), beginner: copy("基础", "Beginner"), easy: copy("基础", "Basic"), hard: copy("深入", "Advanced"), general: copy("通用题库", "Question bank"), custom: copy("简历定制", "Tailored") })[value] || data.categories.find((item) => item.id === value)?.label || String(value || "");
    const button = (action, text, { cls = "", attrs = "", disabled = false } = {}) => `<button type="button" class="${cls}" data-interview-action="${action}" ${attrs} ${data.busy || disabled ? "disabled" : ""}>${text}</button>`;
    const solid = (action, text, options = {}) => button(action, `${esc(text)}${ARROW}`, { ...options, cls: `iv-btn iv-btn--solid interview-primary ${options.cls || ""}` });
    const outline = (action, text, options = {}) => button(action, esc(text), { ...options, cls: `iv-btn ${options.cls || ""}` });
    const quiet = (action, text, options = {}) => button(action, esc(text), { ...options, cls: `iv-link ${options.cls || ""}` });
    const kicker = (text) => `<p class="iv-eyebrow">${esc(text)}</p>`;
    const dateText = (value, withTime = true) => {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return "–";
      return date.toLocaleString(state.uiLanguage === "en" ? "en-US" : "zh-CN", withTime ? { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" } : { month: "2-digit", day: "2-digit" });
    };

    function freshState() {
      return { pane: "home", busy: false, error: "", notice: "", questions: [], categories: [], selected: new Set(), category: "", count: 5, sessions: [], sessionsLoaded: false, current: null, lastAnswered: null, answers: {}, resume: "", job: "", file: null, custom: [], manualPrompt: "" };
    }

    function resetForAccount() {
      epoch += 1;
      requestController?.abort();
      requestController = null;
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
      document.addEventListener("keydown", (event) => { if (event.key === "Escape") menu(false, menuOpen); });
      window.addEventListener?.("resize", () => menu(false));
      byId("interviewNav")?.addEventListener("click", (event) => {
        const item = event.target.closest("[data-interview-pane]");
        if (!item) return;
        event.preventDefault?.();
        setPane(item.dataset.interviewPane);
      });
      byId("interviewPanel")?.addEventListener("click", handleAction);
      byId("interviewPanel")?.addEventListener("input", captureInput);
      byId("interviewPanel")?.addEventListener("change", captureInput);
      window.addEventListener("ielts:ui-language-change", () => { setProductMode(state.productMode); render(); });
    }

    async function perform(task, apply) {
      if (data.busy) return;
      if (!state.account.authenticated) {
        promptGuestLogin(copy("登录后保存面试记录与回答。", "Sign in to save interview sessions and answers."), { returnView: "interview" });
        return;
      }
      const generation = epoch;
      const owner = state.account.user?.id;
      requestController = new AbortController();
      data.busy = true;
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

    function request(path, body = null) {
      return api(path, body, { signal: requestController?.signal });
    }

    function show() {
      if (!state.desktopCapabilities?.mock_interview) return;
      render();
      if (state.account.authenticated && !data.questions.length && !data.busy) loadOverview();
    }

    function setPane(pane) {
      if (!PANES.has(pane) || data.busy) return;
      data.pane = pane;
      data.error = "";
      switchView("interview", { force: state.view !== "interview" });
      render();
      if (pane === "history") loadHistory();
      else if (!data.questions.length && state.account.authenticated) loadOverview();
    }

    function acceptOverview([bankPayload, historyPayload]) {
      data.questions = bankPayload?.questions || [];
      data.categories = bankPayload?.categories || [];
      if (historyPayload) { data.sessions = historyPayload.sessions || []; data.sessionsLoaded = true; }
    }

    function loadOverview() {
      return perform(() => Promise.all([request("/api/interview/questions/"), request("/api/interview/sessions/")]), acceptOverview);
    }
    function loadBank() {
      return perform(() => request("/api/interview/questions/"), (payload) => acceptOverview([payload, null]));
    }
    function loadHistory() {
      return perform(() => request("/api/interview/sessions/"), (payload) => { data.sessions = payload.sessions || []; data.sessionsLoaded = true; });
    }

    function acceptSession(payload) {
      data.current = payload;
      data.pane = "session";
      const turns = payload.turns || [];
      const latest = [...turns].reverse().find((turn) => turn.status !== "pending");
      data.lastAnswered = latest?.kind === "main" && latest.status === "completed" && !turns.some((turn) => turn.parent_turn_id === latest.id) ? latest.id : null;
      const summary = data.sessions.find((item) => item.id === payload.session?.id);
      if (summary) Object.assign(summary, payload.session);
      else if (payload.session && data.sessionsLoaded) data.sessions.unshift(payload.session);
    }

    // ---- Shared pieces
    function voiceNote() {
      return `<p class="iv-voice-note interview-voice-note"><span class="iv-dot" aria-hidden="true"></span>${esc(copy("当前支持文字作答；语音作答正在准备中。", "Written answers are available; voice answers are being prepared."))}</p>`;
    }

    function categoryChips(action = "pick-category") {
      const all = [{ id: "", label: copy("综合", "Mixed") }, ...data.categories];
      return all.map((item) => {
        const count = item.id ? data.questions.filter((q) => q.category === item.id).length : data.questions.length;
        return button(action, `${esc(item.label)}${count ? `<sup>${count}</sup>` : ""}`, { cls: `iv-chip${data.category === item.id ? " is-on" : ""}`, attrs: `data-category="${esc(item.id)}" aria-pressed="${data.category === item.id}"` });
      }).join("");
    }

    function countSeg() {
      return `<div class="iv-seg" role="group" aria-label="${esc(copy("题目数量", "Questions"))}">${COUNTS.map((n) => button("pick-count", String(n), { cls: data.count === n ? "is-on" : "", attrs: `data-count="${n}" aria-pressed="${data.count === n}"` })).join("")}</div>`;
    }

    // ---- Panes
    function home() {
      const sessions = data.sessions;
      const answered = sessions.reduce((sum, item) => sum + (Number(item.report?.completed_count) || 0), 0);
      const active = (data.current?.session?.status === "active" && data.current) || null;
      const activeSummary = active ? null : sessions.find((item) => item.status === "active");
      const recent = sessions.slice(0, 3);
      const stat = (dt, dd, attrs = "") => `<div class="iv-stat"><dt>${esc(dt)}</dt><dd ${attrs}>${dd}</dd></div>`;
      const resumeCard = active
        ? `<div class="iv-resume"><span>${esc(copy("进行中", "In progress"))} · ${active.turns.filter((t) => t.status !== "pending").length}/${active.turns.length}</span><strong>${esc(active.session.title)}</strong>${button("resume", `${esc(copy("继续回答", "Resume"))}${ARROW}`, { cls: "iv-link" })}</div>`
        : activeSummary
          ? `<div class="iv-resume"><span>${esc(copy("进行中", "In progress"))}</span><strong>${esc(activeSummary.title)}</strong>${button("open-session", `${esc(copy("继续回答", "Resume"))}${ARROW}`, { cls: "iv-link", attrs: `data-session-id="${esc(activeSummary.id)}"` })}</div>`
          : "";
      const categoryLinks = data.categories.map((item, index) => `<li>${button("bank-category", `<b>${pad(index + 1)}</b><span>${esc(item.label)}</span><i aria-hidden="true">→</i>`, { attrs: `data-category="${esc(item.id)}"` })}</li>`).join("")
        || `<li>${button("bank", `<b>ALL</b><span>${esc(copy("浏览全部题目", "Browse all"))}</span><i aria-hidden="true">→</i>`)}</li>`;
      const recentLinks = recent.map((item) => `<li>${button("open-session", `<b>${esc(dateText(item.created_at, false))}</b><span>${esc(item.title)}</span><i aria-hidden="true">→</i>`, { attrs: `data-session-id="${esc(item.id)}"` })}</li>`).join("");
      return `<section class="iv-hero">
          <div class="iv-intro">
            <p class="iv-kicker">Interview Studio</p>
            <h2 class="iv-title"><span class="iv-title-top">${esc(copy("把做过的系统，讲成面试官想听的答案", "Turn the systems you built into answers that land"))}</span><span class="iv-title-main">Mock Interview</span></h2>
            <p class="iv-topics">C++ <i>/</i> ${esc(copy("低延迟", "Low latency"))} <i>/</i> ${esc(copy("系统并发", "Concurrency"))} <i>/</i> ${esc(copy("项目深挖", "Projects"))} <i>/</i> ${esc(copy("行为面", "Behavioral"))}</p>
            <div class="iv-actions">${solid("start-general", copy("开始一场面试", "Start an interview"))}${outline("custom", copy("按简历定制", "Tailor to my resume"))}</div>
            ${voiceNote()}
          </div>
          <aside class="iv-panel" aria-label="${esc(copy("面试设置", "Interview setup"))}">
            <dl class="iv-stats">${stat(copy("面试场次", "Sessions"), data.sessionsLoaded ? sessions.length : "–")}${stat(copy("已答题", "Answered"), data.sessionsLoaded ? answered : "–")}${stat(copy("最近练习", "Last"), sessions[0] ? esc(dateText(sessions[0].created_at, false)) : "–", 'class="iv-stat-date"')}</dl>
            <p class="iv-panel-label">${esc(copy("方向", "Topic"))}</p>
            <div class="iv-chips">${categoryChips()}</div>
            <p class="iv-panel-label">${esc(copy("题量", "Questions"))}</p>
            ${countSeg()}
            ${resumeCard}
          </aside>
        </section>
        <section class="iv-areas" aria-label="${esc(copy("练习路径", "Practice paths"))}">
          <header class="iv-sec-head">${kicker("Practice paths")}</header>
          <div class="iv-area-grid">
            <article class="iv-area"><span class="iv-area-index">01 · Bank</span><h3 class="iv-area-name">${esc(copy("通用题库", "Question bank"))}</h3><p class="iv-area-blurb">${esc(copy(`${data.questions.length || 30} 道精选技术题，按方向抽题，回答随时保存。`, `${data.questions.length || 30} curated technical questions by topic; every answer is saved.`))}</p><ul class="iv-area-links">${categoryLinks}</ul></article>
            <article class="iv-area"><span class="iv-area-index">02 · Tailored</span><h3 class="iv-area-name">${esc(copy("简历定制", "Tailored"))}</h3><p class="iv-area-blurb">${esc(copy("简历加岗位描述，AI 出题后你可以逐条修改，也能手动补题。", "Resume plus job description; edit every AI question or add your own."))}</p><ul class="iv-area-links"><li>${button("custom", `<b>PDF</b><span>${esc(copy("上传简历 + 岗位描述", "Resume + job description"))}</span><i aria-hidden="true">→</i>`)}</li><li>${button("custom", `<b>DIY</b><span>${esc(copy("手动出题", "Write your own"))}</span><i aria-hidden="true">→</i>`)}</li></ul></article>
            <article class="iv-area"><span class="iv-area-index">03 · Review</span><h3 class="iv-area-name">${esc(copy("面试记录", "Records"))}</h3><p class="iv-area-blurb">${esc(copy("每场的问题、回答和追问都留档，完成后可生成 AI 文字建议。", "Every question, answer and follow-up is kept; ask for AI text coaching when done."))}</p><ul class="iv-area-links">${recentLinks}<li>${button("history", `<b>ALL</b><span>${esc(copy("全部记录", "All records"))}</span><i aria-hidden="true">→</i>`)}</li></ul></article>
          </div>
        </section>`;
    }

    function bank() {
      const questions = data.questions.filter((item) => !data.category || item.category === data.category);
      const rows = questions.map((item, index) => {
        const id = String(item.id);
        const on = data.selected.has(id);
        return `<li><label class="iv-q${on ? " is-on" : ""}"><input type="checkbox" class="iv-q-input" data-interview-question="${esc(id)}" ${on ? "checked" : ""} ${data.busy ? "disabled" : ""}><span class="iv-q-index">${pad(index + 1)}</span><span class="iv-q-body"><strong>${esc(item.prompt)}</strong><small>${esc(label(item.category))} · ${esc(label(item.difficulty))}</small></span><span class="iv-q-check" aria-hidden="true"></span></label></li>`;
      }).join("");
      return `<div class="iv-toolbar"><div class="iv-chips" role="group" aria-label="${esc(copy("方向", "Topic"))}">${categoryChips("filter-category")}</div>${quiet("reload-bank", copy("刷新", "Refresh"))}</div>
        <ol class="iv-qlist">${rows || `<li class="iv-empty">${esc(copy("暂无可显示的问题。", "No questions to display."))}</li>`}</ol>
        <div class="iv-dock"><span class="iv-dock-count"><b>${data.selected.size}</b> / 10 ${esc(copy("已选", "selected"))}</span>${data.selected.size ? quiet("clear-selection", copy("清空", "Clear")) : ""}<span class="iv-dock-spacer"></span>${outline("start-general", copy(`随机 ${data.count} 题`, `Random ${data.count}`))}${solid("start-selected", copy(`开始所选 ${data.selected.size} 题`, `Practice ${data.selected.size} selected`), { disabled: !data.selected.size })}</div>`;
    }

    function custom() {
      const list = data.custom.map((question, index) => `<li class="iv-custom-item interview-custom-question"><span class="iv-q-index">${pad(index + 1)}</span><div><small>${esc(question.source === "manual" ? copy("手动", "Manual") : copy("AI 生成", "AI generated"))}</small><textarea rows="2" maxlength="1500" aria-label="${esc(copy(`问题 ${index + 1}`, `Question ${index + 1}`))}" data-interview-custom-index="${index}">${esc(question.prompt)}</textarea></div>${button("remove-custom", "×", { cls: "iv-icon-btn", attrs: `data-index="${index}" aria-label="${esc(copy("移除", "Remove"))}"` })}</li>`).join("");
      return `<p class="iv-lede">${esc(copy("简历与岗位描述会发送到你在设置里选择的 AI 服务，只填写你愿意用于练习的内容。服务器不保存简历文件。", "Your resume and job description go to the AI service chosen in settings. Include only what you want to practice with; resume files are not stored."))}</p>
        <div class="iv-custom">
          <section class="iv-sheet" aria-label="${esc(copy("输入材料", "Inputs"))}">
            <div class="iv-step"><span>01</span><h3>${esc(copy("简历", "Resume"))}</h3></div>
            <label class="iv-drop"><input type="file" accept="application/pdf,.pdf" data-interview-field="file"><strong>${esc(data.file?.name || copy("选择 PDF 简历", "Choose a PDF resume"))}</strong><small>${esc(copy("最多 2 MB · 扫描件请改用下方粘贴文字", "Up to 2 MB · paste text below for scanned files"))}</small></label>
            <label class="iv-field">${esc(copy("或粘贴简历文字", "Or paste resume text"))}<textarea rows="6" maxlength="24000" data-interview-field="resume">${esc(data.resume)}</textarea></label>
            <div class="iv-step"><span>02</span><h3>${esc(copy("岗位描述", "Job description"))}</h3></div>
            <label class="iv-field"><span class="sr-only">${esc(copy("岗位描述", "Job description"))}</span><textarea rows="6" maxlength="12000" data-interview-field="job">${esc(data.job)}</textarea></label>
            <div class="iv-row"><span class="iv-row-label">${esc(copy("题量", "Questions"))}</span>${countSeg()}<span class="iv-dock-spacer"></span>${solid("generate", copy("生成定制问题", "Generate questions"))}</div>
          </section>
          <section class="iv-sheet" aria-label="${esc(copy("问题清单", "Question list"))}">
            <div class="iv-step"><span>03</span><h3>${esc(copy("问题清单", "Question list"))}</h3><em>${data.custom.length} / 10</em></div>
            ${list ? `<ol class="iv-custom-list">${list}</ol>` : `<p class="iv-empty">${esc(copy("生成后的问题会出现在这里，可以逐条修改。也可以直接手动添加。", "Generated questions appear here for editing. You can also add your own."))}</p>`}
            <label class="iv-field">${esc(copy("手动添加一题", "Add a question"))}<textarea rows="2" maxlength="1500" data-interview-field="manualPrompt">${esc(data.manualPrompt)}</textarea></label>
            <div class="iv-row">${outline("add-custom", copy("添加问题", "Add question"))}<span class="iv-dock-spacer"></span>${solid("start-custom", copy("开始定制面试", "Start tailored interview"), { disabled: !data.custom.length })}</div>
          </section>
        </div>`;
    }

    function history() {
      const rows = data.sessions.map((session) => `<li>${button("open-session", `<time>${esc(dateText(session.created_at))}</time><span class="iv-history-title"><strong>${esc(session.title)}</strong><small>${esc(label(session.mode))}${session.report?.completed_count != null ? ` · ${esc(copy(`答 ${session.report.completed_count} 题`, `${session.report.completed_count} answered`))}` : ""}</small></span><em class="iv-status is-${esc(session.status)}">${esc(label(session.status))}</em><i aria-hidden="true">→</i>`, { cls: "iv-history-row", attrs: `data-session-id="${esc(session.id)}" aria-label="${esc(`${session.title} · ${session.status === "active" ? copy("继续", "Resume") : copy("查看记录", "View report")}`)}"` })}</li>`).join("");
      return `<div class="iv-toolbar"><span class="iv-toolbar-note">${esc(copy(`共 ${data.sessions.length} 场`, `${data.sessions.length} sessions`))}</span>${quiet("reload-history", copy("刷新", "Refresh"))}</div>
        ${rows ? `<ol class="iv-history">${rows}</ol>` : `<div class="iv-empty-card"><p>${esc(copy("还没有面试记录。完成一次练习后，问题和回答会留在这里。", "No sessions yet. Questions and answers will be kept here after your first practice."))}</p>${solid("home", copy("开始练习", "Start practice"))}</div>`}`;
    }

    function rail(turns, currentId) {
      return `<ol class="iv-rail" aria-label="${esc(copy("题目进度", "Progress"))}">${turns.map((item) => `<li class="is-${esc(item.status)}${item.id === currentId ? " is-current" : ""}${item.kind === "follow_up" ? " is-follow" : ""}"><span>${item.kind === "follow_up" ? "↳" : pad(item.order)}</span><p>${esc(item.prompt)}</p></li>`).join("")}</ol>`;
    }

    function report(session, turns, completed, skipped) {
      const feedback = session.report?.ai_feedback;
      const feedbackText = typeof feedback === "string" ? feedback : feedback?.feedback || feedback?.text || feedback?.coaching || "";
      const follows = turns.filter((item) => item.kind === "follow_up").length;
      const coach = session.status === "completed" && !feedbackText && completed > 0 ? solid("coach", copy("生成 AI 文字建议", "Generate AI coaching")) : "";
      return `<header class="iv-report-head">${kicker(`${label(session.mode)} · ${label(session.status)}`)}<h2>${esc(session.title)}</h2><p>${esc(dateText(session.created_at))}</p></header>
        <dl class="iv-report-stats"><div><dt>${esc(copy("已回答", "Answered"))}</dt><dd>${completed}</dd></div><div><dt>${esc(copy("跳过", "Skipped"))}</dt><dd>${skipped}</dd></div><div><dt>${esc(copy("追问", "Follow-ups"))}</dt><dd>${follows}</dd></div></dl>
        <p class="iv-voice-note interview-report-limit"><span class="iv-dot" aria-hidden="true"></span>${esc(copy("文字练习记录：仅根据你输入的回答整理，不评估发音、声音表现或真实面试结果。", "Text practice report: based only on your written answers. No pronunciation, vocal delivery, or hiring outcome assessment."))}</p>
        ${feedback?.status === "failed" ? `<div class="iv-error interview-error" role="alert">${esc(feedback.error || copy("AI 建议生成失败，请重试。", "AI coaching failed; please retry."))}</div>` : ""}
        ${feedbackText ? `<article class="iv-coaching"><p class="iv-eyebrow">AI coaching</p><div class="iv-feedback interview-feedback">${esc(feedbackText)}</div></article>` : ""}
        <div class="iv-actions">${coach}${outline("home", copy("再练一场", "Practice again"))}${quiet("history", copy("返回记录", "Back to records"))}</div>
        <ol class="iv-transcript">${turns.map((item) => `<li class="is-${esc(item.status)}${item.kind === "follow_up" ? " is-follow" : ""}"><span class="iv-q-index">${item.kind === "follow_up" ? "↳" : pad(item.order)}</span><div><small>${esc(label(item.kind))} · ${esc(label(item.status))}</small><h3>${esc(item.prompt)}</h3><p>${esc(item.answer || copy("本题未回答。", "No answer saved."))}</p></div></li>`).join("")}</ol>`;
    }

    function session() {
      if (!data.current) return home();
      const { session, turns = [], current_turn: turn } = data.current;
      const completed = turns.filter((item) => item.status === "completed").length;
      const skipped = turns.filter((item) => item.status === "skipped").length;
      if (session.status !== "active") return report(session, turns, completed, skipped);
      const last = data.lastAnswered && turns.find((item) => item.id === data.lastAnswered);
      const canFollow = last?.kind === "main" && !turns.some((item) => item.parent_turn_id === last.id);
      const done = turns.filter((item) => item.status !== "pending").length;
      const draft = turn ? data.answers[turn.id] || "" : "";
      const progress = `<div class="iv-progress" aria-hidden="true">${turns.map((item) => `<span class="is-${esc(item.status)}${turn && item.id === turn.id ? " is-current" : ""}"></span>`).join("")}</div>`;
      const followUp = canFollow ? `<div class="iv-follow interview-follow-up"><div><strong>${esc(copy("面试官可能会追问", "The interviewer may dig deeper"))}</strong><span>${esc(copy("上一题已保存。先针对你的回答追问一次，再继续下一题。", "Answer saved. Take one follow-up on it before moving on."))}</span></div>${outline("follow-up", copy("追问上一题", "Follow up"))}</div>` : "";
      const question = turn
        ? `<article class="iv-question interview-answer-card"><span class="iv-question-kind${turn.kind === "follow_up" ? " is-follow" : ""}">${turn.kind === "follow_up" ? `↳ ${esc(copy("AI 追问", "AI follow-up"))}` : `Q${pad(turn.order)} · ${esc(copy("主问题", "Main question"))}`}</span><h3>${esc(turn.prompt)}</h3>
            <label class="sr-only" for="interviewAnswer">${esc(copy("你的回答", "Your answer"))}</label><textarea id="interviewAnswer" class="iv-answer" rows="10" maxlength="6000" placeholder="${esc(copy("先说结论，再讲背景、你做了什么、结果和取舍……", "Lead with the conclusion, then context, what you did, results and trade-offs…"))}" data-interview-field="answer" ${data.busy ? "disabled" : ""}>${esc(draft)}</textarea>
            <div class="iv-answer-foot"><span id="interviewAnswerCount" class="iv-count">${draft.length} / 6000</span><span class="iv-dock-spacer"></span>${outline("skip", copy("跳过本题", "Skip"))}${solid("answer", copy("保存，下一题", "Save and continue"))}</div></article>`
        : `<article class="iv-question iv-question--done"><span class="iv-question-kind">${esc(copy("本轮完成", "All answered"))}</span><h3>${esc(copy("问题都答完了。可以对最后一个回答追问，或结束并生成记录。", "Every question is answered. Follow up on the last answer, or finish to save the record."))}</h3><div class="iv-answer-foot"><span class="iv-dock-spacer"></span>${solid("finish", copy("完成并查看记录", "Finish and view record"))}</div></article>`;
      return `<div class="iv-session">
          <div class="iv-session-main">
            <header class="iv-session-head"><div>${kicker(`${label(session.mode)} · ${done}/${turns.length}`)}<h2>${esc(session.title)}</h2></div>${progress}</header>
            ${followUp}${question}
            <footer class="iv-session-foot">${voiceNote()}<span class="iv-dock-spacer"></span>${turn ? quiet("finish", copy("提前完成并保存记录", "Finish early and save")) : ""}${quiet("abort", copy("结束本轮（保留已答内容）", "End session (keep answers)"))}</footer>
          </div>
          <aside class="iv-session-side"><p class="iv-eyebrow">${esc(copy(`已答 ${completed} · 跳过 ${skipped}`, `${completed} answered · ${skipped} skipped`))}</p>${rail(turns, turn?.id)}</aside>
        </div>`;
    }

    const PANE_COPY = {
      bank: ["Interview · Question bank", ["通用题库", "Question bank"], ["勾选想练的题目开始，或按方向随机抽题。", "Pick the questions you want, or draw at random by topic."]],
      custom: ["Interview · Tailored", ["简历定制", "Tailored interview"], ["根据你的简历和目标岗位生成问题，开始前可以逐条修改。", "Questions from your resume and target role, editable before you start."]],
      history: ["Interview · Records", ["面试记录", "Interview records"], ["每一场的问题、回答与追问。", "Questions, answers and follow-ups from every session."]],
    };

    function syncChrome() {
      const pane = data.pane;
      // Home and the live session carry their own headings; the shared page title would repeat them.
      const bare = pane === "home" || pane === "session";
      document.body.classList.toggle("interview-bare", state.view === "interview" && bare);
      if (document.body.dataset) document.body.dataset.interviewPane = pane;
      document.querySelectorAll("#interviewNav [data-interview-pane]").forEach((item) => {
        const active = item.dataset.interviewPane === pane || (pane === "session" && item.dataset.interviewPane === (data.current?.session?.status === "active" ? "home" : "history"));
        item.classList.toggle("active", active && state.view === "interview");
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-current", active ? "page" : "false");
        item.setAttribute("aria-disabled", String(data.busy));
      });
      const entry = PANE_COPY[pane];
      if (!entry || state.view !== "interview") return;
      if (byId("viewTitle")) byId("viewTitle").textContent = copy(...entry[1]);
      if (byId("viewSubtitle")) byId("viewSubtitle").textContent = copy(...entry[2]);
    }

    function render() {
      const panel = byId("interviewPanel");
      if (!panel || !state.desktopCapabilities?.mock_interview) return;
      syncChrome();
      if (!state.account.authenticated) {
        panel.innerHTML = `<div class="iv-guest"><p class="iv-kicker">Interview Studio</p><h2 class="iv-title"><span class="iv-title-main">Mock Interview</span></h2><p>${esc(copy("登录同一个 IELTS Studio 账号，保存面试回答与练习记录。", "Sign in with your Studio account to save answers and interview history."))}</p>${solid("login", copy("登录并开始", "Sign in and start"))}${voiceNote()}</div>`;
        return;
      }
      const content = ({ home, bank, custom, history, session })[data.pane]();
      const status = `<div id="interviewStatus" class="iv-status-line" role="status" aria-live="polite">${data.busy ? `<span class="iv-spinner" aria-hidden="true"></span>${esc(copy("正在处理…", "Working…"))}` : esc(data.notice)}</div>`;
      panel.innerHTML = `${status}${data.error ? `<div class="iv-error interview-error" role="alert">${esc(data.error)}</div>` : ""}<div class="iv-pane iv-pane--${data.pane}">${content}</div>`;
      panel.querySelectorAll("input, select, textarea").forEach((el) => { el.disabled = data.busy; });
    }

    function captureInput(event) {
      if (data.busy) return;
      const el = event.target;
      const field = el.dataset.interviewField;
      if (field === "answer" && data.current?.current_turn) {
        data.answers[data.current.current_turn.id] = el.value;
        const counter = byId("interviewAnswerCount");
        if (counter) counter.textContent = `${el.value.length} / 6000`;
      } else if (field === "file") { data.file = el.files?.[0] || null; render(); }
      else if (field === "count") data.count = Math.max(1, Math.min(10, Number(el.value) || 1));
      else if (field && ["resume", "job", "category", "manualPrompt"].includes(field)) data[field] = el.value;
      if (el.dataset.interviewCustomIndex !== undefined) data.custom[Number(el.dataset.interviewCustomIndex)].prompt = el.value;
      if (el.dataset.interviewQuestion !== undefined && event.type === "change") {
        if (el.checked && data.selected.size >= 10 && !data.selected.has(el.dataset.interviewQuestion)) {
          el.checked = false;
          data.error = copy("每轮最多选择 10 个问题。", "Select up to 10 questions per session.");
        } else { el.checked ? data.selected.add(el.dataset.interviewQuestion) : data.selected.delete(el.dataset.interviewQuestion); data.error = ""; }
        render();
      }
      if (field === "category" && data.pane === "bank") render();
    }

    async function uploadQuestions() {
      const signal = requestController?.signal;
      const form = new FormData();
      form.append("resume_text", data.resume);
      form.append("job_description", data.job);
      form.append("count", String(data.count));
      form.append("ai_source", currentAiSourcePreference());
      if (data.file) form.append("resume_file", data.file);
      const token = await ensureCsrfToken();
      const response = await fetch("/api/interview/custom-questions/", { method: "POST", credentials: "same-origin", headers: token ? { "X-CSRFToken": token } : {}, body: form, signal });
      const raw = await response.text();
      let payload;
      try { payload = JSON.parse(raw); } catch (_error) { throw new Error(copy("服务未返回有效数据，请重试。", "Invalid server response; please retry.")); }
      if (!response.ok) throw new Error(payload.error || payload.message || copy("定制问题生成失败。", "Question generation failed."));
      return payload;
    }

    function handleAction(event) {
      const el = event.target.closest("[data-interview-action]");
      if (!el || data.busy) return;
      const action = el.dataset.interviewAction;
      if (PANES.has(action)) { setPane(action); return; }
      if (action === "login") { promptGuestLogin(copy("登录后保存面试记录与回答。", "Sign in to save interview practice."), { returnView: "interview" }); return; }
      if (action === "resume") { data.pane = "session"; render(); return; }
      if (action === "reload-bank") { loadBank(); return; }
      if (action === "reload-history") { loadHistory(); return; }
      if (action === "pick-category" || action === "filter-category") { data.category = el.dataset.category || ""; render(); return; }
      if (action === "bank-category") { data.category = el.dataset.category || ""; setPane("bank"); return; }
      if (action === "pick-count") { data.count = Number(el.dataset.count) || 5; render(); return; }
      if (action === "clear-selection") { data.selected.clear(); render(); return; }
      if (action === "add-custom") {
        if (!data.manualPrompt.trim()) { data.error = copy("请先输入问题。", "Enter a question first."); render(); return; }
        if (data.custom.length >= 10) { data.error = copy("每轮最多 10 个问题。", "Up to 10 questions per session."); render(); return; }
        data.custom.push({ prompt: data.manualPrompt.trim(), category: "projects", difficulty: "medium", source: "manual" }); data.manualPrompt = ""; data.error = ""; render(); return;
      }
      if (action === "remove-custom") { data.custom.splice(Number(el.dataset.index), 1); render(); return; }
      if (action === "generate") { perform(uploadQuestions, (payload) => { data.custom = payload.questions || []; data.notice = copy("问题已生成，请检查后开始。", "Questions generated. Review before starting."); }); return; }
      if (action === "start-general" || action === "start-selected" || action === "start-custom") {
        const body = action === "start-custom" ? { mode: "custom", questions: data.custom } : { mode: "general", category: data.category, count: action === "start-selected" ? data.selected.size : data.count, ...(action === "start-selected" ? { question_ids: [...data.selected] } : {}) };
        perform(() => request("/api/interview/sessions/", body), (payload) => { acceptSession(payload); if (action === "start-selected") data.selected.clear(); }); return;
      }
      if (action === "open-session") { perform(() => request(`/api/interview/sessions/${encodeURIComponent(el.dataset.sessionId)}/`), acceptSession); return; }
      const sessionId = data.current?.session?.id;
      const turn = data.current?.current_turn;
      if (!sessionId) return;
      const base = `/api/interview/sessions/${encodeURIComponent(sessionId)}/`;
      if (action === "answer" && turn) {
        const answer = (data.answers[turn.id] || "").trim();
        if (!answer) { data.error = copy("请输入回答，或选择跳过。", "Enter an answer or skip this question."); render(); return; }
        perform(() => request(`${base}turns/${encodeURIComponent(turn.id)}/answer/`, { answer }), (payload) => { acceptSession(payload); data.lastAnswered = turn.id; delete data.answers[turn.id]; });
      } else if (action === "skip" && turn) {
        perform(() => request(`${base}turns/${encodeURIComponent(turn.id)}/skip/`, {}), (payload) => { acceptSession(payload); data.lastAnswered = null; delete data.answers[turn.id]; });
      } else if (action === "follow-up" && data.lastAnswered) {
        perform(() => request(`${base}turns/${encodeURIComponent(data.lastAnswered)}/follow-up/`, { ai_source: currentAiSourcePreference() }), (payload) => { acceptSession(payload); data.lastAnswered = null; });
      } else if (["finish", "abort", "coach"].includes(action)) {
        const endpoint = action === "coach" ? "report" : action;
        perform(() => request(`${base}${endpoint}/`, action === "coach" ? { ai_source: currentAiSourcePreference() } : {}), acceptSession);
      }
    }

    return { initialize, setProductMode, show, resetForAccount, setPane };
  }
  window.IELTSInterview = { createInterview };
})();
