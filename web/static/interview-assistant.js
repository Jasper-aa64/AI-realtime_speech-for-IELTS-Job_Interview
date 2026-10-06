// AI 助手: the chat itself is Deep Chat (open-source web component, vendor/deep-chat-*.bundle.js) with highlight.js for
// code. One conversation state feeds two hosts:
//   page — the AI 助手 pane: thread list (search, grouped by date, rename / delete), a header with the 聊天 / Agent
//          switch, and the chat;
//   dock — a small button in the bottom-right corner of every interview page that grows into a compact chat on hover
//          (corner-morph.js, like the mode switcher); its ⋮ menu picks a recent thread — no rename / delete there.
// It follows the product mode: in interview mode Agent edits 知识点语料库 / 简历题卡 / JD 与反问, in IELTS mode the
// P1 / P2 / P3 corpora and Takeaway (the server validates and applies its actions); each reply carries links to what
// it changed, a one-click undo and the agent trace. Each mode keeps its own chats.
(function () {
  const DEEP_CHAT = "/vendor/deep-chat-2.5.1.bundle.js";
  const HIGHLIGHT = "/vendor/highlight-11.12.0.min.js";
  const MODE_KEY = "iv-assistant-mode";
  const DOCK_RECENT = 8;
  const MODES = [
    { id: "chat", zh: "聊天", en: "Chat", note: ["只回答，不改语料库", "Answers only; your corpus is untouched"] },
    { id: "agent", zh: "Agent", en: "Agent", note: ["可以新建、修改、删除你的语料；每次修改都能一键撤销", "Creates, edits and deletes your corpus items; every change can be undone"] },
  ];
  const EXAMPLES = {
    interview: [
      { mode: "chat", zh: "讲讲 SPSC 无锁队列怎么实现，为什么要做缓存行对齐", en: "How does an SPSC lock-free queue work?" },
      { mode: "agent", zh: "把我知识点里低延迟相关的题卡整理一下：合并重复的，答得太短的补全", en: "Tidy my low-latency cards: merge duplicates, fill in thin answers" },
      { mode: "agent", zh: "用 STAR 法则把我简历里的实习经历写成项目描述，并预判 3 个追问", en: "Write my internship up with the STAR method and predict 3 follow-ups" },
      { mode: "agent", zh: "下面是一个 JD：……  帮我建一张 JD 卡，出 3 道岗位题和 2 个反问", en: "Here is a JD: … make a JD card with 3 role questions and 2 to ask" },
    ],
    ielts: [
      { mode: "chat", zh: "P2 讲一个人物题，怎么在 2 分钟里讲得有细节又不跑题？", en: "How do I keep a Part 2 person story detailed but on topic?" },
      { mode: "agent", zh: "帮我写一个「人物」类 P2 通用素材：我的外公，教我下象棋，能套用到多个题", en: "Write a reusable Part 2 person story about my grandfather" },
      { mode: "agent", zh: "把这期 P1 里关于 hometown 的题都写上 7 分答法", en: "Write band-7 answers for this season's hometown Part 1 questions" },
      { mode: "agent", zh: "把这几个表达存进 Takeaway：a far cry from / on a whim / it dawned on me", en: "Save these to Takeaway: a far cry from / on a whim / it dawned on me" },
    ],
  };
  const STEP_MARK = { library: "◎", model: "✦", validate: "✓", create: "＋", update: "✎", delete: "✕", skip: "!" };
  const OP_MARK = { create: "✓", update: "✎", delete: "✕" };
  const svg = (paths, size = 16) => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
  const ICON = {
    spark: svg('<path d="M12 3l1.9 4.8L19 10l-5.1 2.2L12 17l-1.9-4.8L5 10l5.1-2.2z"/><path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z"/>'),
    compose: svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>'),
    search: svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>', 15),
    rename: svg('<path d="M4 20h4L19 9l-4-4L4 16z"/>', 14),
    trash: svg('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>', 14),
    dots: svg('<circle cx="12" cy="5.5" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="12" cy="18.5" r="1.2"/>'),
    expand: svg('<path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/>', 15),
    copy: svg('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>', 14),
    check: svg('<path d="m5 12.5 4.5 4.5L19 7.5"/>', 14),
  };

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
      const el = document.createElement("script");
      el.src = src;
      el.onload = () => resolve();
      el.onerror = () => reject(new Error(`无法加载 ${src}`));
      document.head.appendChild(el);
    });
  }
  let libraryPromise = null;
  // highlight.js first: Deep Chat picks up window.hljs when a chat is created.
  function loadLibrary() {
    libraryPromise ||= loadScript(HIGHLIGHT).catch(() => null).then(() => import(DEEP_CHAT)).catch((error) => { libraryPromise = null; throw error; });
    return libraryPromise;
  }

  function create({ state, escapeHtml, request, popup, toast, setCorpus, openApplied, openPage = () => {}, onIeltsChanged = () => {}, currentAiSourcePreference }) {
    let threads = null; // [{id, title, updated_at}]
    let engine = "";
    let current = null; // thread id, null = new chat
    let history = []; // messages of the current thread, as the server returns them
    let mode = "chat";
    let search = "";
    let owner;
    let epoch = 0;
    let chat = null; // the Deep Chat element, in whichever host is showing
    let dock = null; // { root, morph, pinned }
    const byId = (id) => document.getElementById(id);
    const copy = (zh, en) => state.uiLanguage === "en" ? en : zh;
    const esc = (value) => escapeHtml(String(value ?? ""));
    try { mode = localStorage.getItem(MODE_KEY) === "agent" ? "agent" : "chat"; } catch (_error) { /* per-viewer convenience only */ }
    const domain = () => (state.productMode === "ielts" ? "ielts" : "interview");
    const examples = () => EXAMPLES[domain()];

    // Chats belong to an account and a mode; switching either starts from that pair's own list.
    function ensureOwner() {
      const id = `${state.account.user?.id || ""}:${domain()}`;
      if (id === owner) return;
      owner = id;
      threads = null;
      current = null;
      history = [];
    }

    // ---- Server
    async function loadThreads() {
      const generation = epoch;
      try {
        const payload = await request(`/api/interview/assistant/threads/?domain=${domain()}`);
        if (generation !== epoch) return;
        threads = payload.threads || [];
        engine = payload.engine || "";
      } catch (_error) {
        if (generation === epoch) threads = threads || [];
      }
      paint();
    }

    async function openThread(id) {
      const generation = epoch;
      current = id;
      history = [];
      paint();
      if (id) {
        try {
          const payload = await request(`/api/interview/assistant/threads/${encodeURIComponent(id)}/`);
          if (generation !== epoch || current !== id) return;
          history = payload.messages || [];
        } catch (error) {
          if (generation === epoch) popup(error.message || copy("对话加载失败。", "Could not load the chat."));
          return;
        }
      }
      const host = activeHost();
      if (host) mount(host, { force: true });
    }

    const threadTitle = () => (threads || []).find((item) => item.id === current)?.title || copy("新对话", "New chat");

    // ---- Deep Chat messages
    function footerHtml(message) {
      const steps = message.steps || [];
      const applied = message.applied || [];
      const word = { create: copy("新建", "Created"), update: copy("修改", "Edited"), delete: copy("删除", "Deleted") };
      // A deleted card has nothing to open; the others link to the card.
      const links = applied.map((item) => item.op === "delete"
        ? `<span class="iv-applied is-delete"><b>${OP_MARK.delete}</b>${esc(word.delete)} ${esc(item.label)}</span>`
        : `<button type="button" class="iv-applied is-${esc(item.op || "create")}" data-where="${esc(item.where)}" data-entry="${esc(item.entry_id)}"><b>${OP_MARK[item.op] || "✓"}</b>${esc(word[item.op] || word.create)} ${esc(item.label)}<i>→</i></button>`).join("");
      const undo = message.undone ? `<span class="iv-undone">${esc(copy("已撤销这些修改", "Changes undone"))}</span>`
        : message.undoable ? `<button type="button" class="iv-undo" data-message="${esc(message.id)}">↶ ${esc(copy("撤销这些修改", "Undo these changes"))}</button>` : "";
      const rows = steps.map((step) => `<li class="is-${esc(step.kind)}"><span>${STEP_MARK[step.kind] || "·"}</span><strong>${esc(step.label)}</strong>${step.detail ? `<em>${esc(step.detail)}</em>` : ""}</li>`).join("");
      const trace = steps.length ? `<details class="iv-trace"><summary>${esc(copy(`执行过程 · ${steps.length} 步`, `Trace · ${steps.length} steps`))}</summary><ol>${rows}</ol></details>` : "";
      return `<div class="iv-agent${message.undone ? " is-undone" : ""}">${links || undo ? `<div class="iv-applied-list">${links}${undo}</div>` : ""}
          <div class="iv-meta"><button type="button" class="iv-copy" data-message="${esc(message.id)}" title="${esc(copy("复制回答", "Copy reply"))}">${ICON.copy}<span>${esc(copy("复制", "Copy"))}</span></button>${trace}</div></div>`;
    }

    function toDeepChat(message) {
      if (message.role === "user") return [{ role: "user", text: message.content }];
      return [{ role: "ai", text: message.content, html: footerHtml(message) }];
    }

    // Colours come from the app's tokens at mount time, so every appearance style (and dark mode) carries over.
    // In the dock the "panel" is the dock's lifted surface, so the chat sits on the card, not on the page colour.
    function palette(compact = false) {
      const css = getComputedStyle(document.body);
      const token = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
      const lifted = compact && dock ? getComputedStyle(dock.root).getPropertyValue("--dock-bg").trim() : "";
      return { ink: token("--ink", "#0d0d0d"), muted: token("--muted", "#6e6e80"), line: token("--line", "#ececf1"),
               panel: lifted || token("--panel", "#ffffff"), bg: token("--bg", "#f7f7f8"), accent: token("--accent", "#10a37f") };
    }

    // Like the mode switcher (interview.js syncSwitchPalette): read the colour the dock floats over and lift the card
    // off it — lighter on a dark page, white on a light one — so it never blends into the background.
    function liftDock() {
      if (!dock) return;
      const read = (el) => (getComputedStyle(el).backgroundColor.match(/[\d.]+/g) || []).map(Number);
      let channels = read(document.querySelector(".workspace") || document.body);
      if (channels.length < 3 || channels[3] === 0) channels = read(document.body);
      if (channels.length < 3) return;
      const light = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2] > 150;
      dock.root.style.setProperty("--dock-surface", `rgb(${channels[0]}, ${channels[1]}, ${channels[2]})`);
      dock.root.dataset.tone = light ? "light" : "dark";
    }

    function auxiliaryStyle(c, compact) {
      return `
        .iv-agent { display: grid; gap: 6px; margin-top: 2px; font-size: ${compact ? 12.5 : 13}px; line-height: 1.5; }
        .iv-applied-list { display: flex; flex-wrap: wrap; gap: 6px; }
        .iv-applied { display: inline-flex; align-items: center; gap: 6px; padding: 5px 11px; border: 1px solid color-mix(in srgb, ${c.accent} 40%, ${c.line});
          border-radius: 8px; background: color-mix(in srgb, ${c.accent} 8%, ${c.panel}); color: ${c.ink}; font: inherit; cursor: pointer; text-align: left; }
        .iv-applied:hover { border-color: ${c.accent}; background: color-mix(in srgb, ${c.accent} 14%, ${c.panel}); }
        .iv-applied b { color: ${c.accent}; font-weight: 600; } .iv-applied i { font-style: normal; color: ${c.muted}; }
        .iv-applied.is-delete { cursor: default; border-color: ${c.line}; background: transparent; color: ${c.muted}; }
        .iv-applied.is-delete b { color: #dc2626; }
        .iv-agent.is-undone .iv-applied { opacity: 0.5; text-decoration: line-through; pointer-events: none; }
        .iv-undo { padding: 5px 11px; border: 1px solid ${c.line}; border-radius: 8px; background: ${c.panel}; color: ${c.ink}; font: inherit; cursor: pointer; }
        .iv-undo:hover { border-color: ${c.muted}; }
        .iv-undo:disabled { opacity: 0.5; cursor: default; }
        .iv-undone { padding: 5px 2px; color: ${c.muted}; }
        .iv-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 10px; color: ${c.muted}; }
        .iv-copy { display: inline-flex; align-items: center; gap: 4px; padding: 3px 6px; margin-left: -6px; border: 0; border-radius: 6px; background: transparent;
          color: ${c.muted}; font: inherit; cursor: pointer; }
        .iv-copy:hover { background: color-mix(in srgb, ${c.ink} 7%, transparent); color: ${c.ink}; }
        .iv-copy.is-done { color: ${c.accent}; }
        .iv-trace summary { cursor: pointer; width: fit-content; list-style: none; padding: 3px 0; }
        .iv-trace summary:hover { color: ${c.ink}; }
        .iv-trace summary::-webkit-details-marker { display: none; }
        .iv-trace summary::before { content: "▸"; display: inline-block; width: 12px; transition: transform 160ms ease; }
        .iv-trace[open] { flex-basis: 100%; }
        .iv-trace[open] summary::before { transform: rotate(90deg); }
        .iv-trace ol { margin: 4px 0 2px; padding: 0 0 0 4px; list-style: none; display: grid; gap: 3px; border-left: 2px solid ${c.line}; }
        .iv-trace li { display: flex; gap: 8px; align-items: baseline; padding-left: 10px; }
        .iv-trace li span { width: 14px; color: ${c.accent}; } .iv-trace li strong { color: ${c.ink}; font-weight: 500; }
        .iv-trace li em { font-style: normal; }
        .iv-trace li.is-skip span, .iv-trace li.is-delete span { color: #dc2626; }
        .iv-thinking { display: inline-flex; align-items: center; gap: 10px; color: ${c.muted}; font-size: ${compact ? 12.5 : 13}px; }
        .iv-thinking-dots { display: inline-flex; gap: 4px; }
        .iv-thinking-dots i { width: 6px; height: 6px; border-radius: 50%; background: ${c.accent}; animation: iv-dot 1.2s ease-in-out infinite; }
        .iv-thinking-dots i:nth-child(2) { animation-delay: 0.15s; } .iv-thinking-dots i:nth-child(3) { animation-delay: 0.3s; }
        .iv-thinking-text { background: linear-gradient(90deg, ${c.muted} 0%, ${c.ink} 50%, ${c.muted} 100%); background-size: 200% 100%;
          -webkit-background-clip: text; background-clip: text; color: transparent; animation: iv-shimmer 1.8s linear infinite; }
        @keyframes iv-dot { 0%, 80%, 100% { opacity: 0.25; transform: translateY(0); } 40% { opacity: 1; transform: translateY(-2px); } }
        @keyframes iv-shimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }
        @media (prefers-reduced-motion: reduce) { .iv-thinking-dots i, .iv-thinking-text { animation: none; } .iv-thinking-text { color: ${c.muted}; } }
        .outer-message-container .message-bubble pre { border-radius: 10px; font-size: ${compact ? 12 : 13}px; }
        .outer-message-container .message-bubble code { font-size: 0.92em; }
        .outer-message-container .message-bubble table { border-collapse: collapse; }
        .outer-message-container .message-bubble th, .outer-message-container .message-bubble td { border: 1px solid ${c.line}; padding: 4px 8px; }
        .outer-message-container .message-bubble p { margin: 0.45em 0; }
        .outer-message-container .message-bubble h1, .outer-message-container .message-bubble h2, .outer-message-container .message-bubble h3 { font-size: 1.05em; margin: 0.9em 0 0.4em; }
        .outer-message-container .message-bubble blockquote { margin: 0.4em 0; padding-left: 10px; border-left: 3px solid ${c.line}; color: ${c.muted}; }`;
    }

    function introPanel(compact) {
      const c = palette(compact);
      const intro = document.createElement("div");
      intro.className = "iv-assistant-intro";
      intro.style.cssText = `display:grid;justify-items:center;gap:${compact ? 8 : 10}px;text-align:center;padding:${compact ? "12px 14px" : "24px 12px"};max-width:640px;width:100%;box-sizing:border-box;font-family:inherit`;
      const shown = compact ? examples().slice(0, 2) : examples();
      const note = MODES.find((item) => item.id === mode).note;
      intro.innerHTML = `
        <div style="width:${compact ? 34 : 44}px;height:${compact ? 34 : 44}px;border-radius:12px;display:grid;place-items:center;background:color-mix(in srgb, ${c.accent} 14%, ${c.panel});color:${c.accent}">${ICON.spark}</div>
        <div style="font-size:${compact ? 16 : 21}px;font-weight:650;color:${c.ink}">${esc(copy("有什么想问的？", "What would you like to ask?"))}</div>
        <div style="font-size:${compact ? 12.5 : 13.5}px;color:${c.muted};line-height:1.6;max-width:460px">${esc(copy(`当前是${mode === "agent" ? " Agent 模式" : "聊天模式"}：${note[0]}。`, `${mode === "agent" ? "Agent" : "Chat"} mode: ${note[1]}.`))}</div>
        <div style="display:grid;grid-template-columns:${compact ? "1fr" : "repeat(2,minmax(0,1fr))"};gap:8px;width:100%;margin-top:${compact ? 4 : 10}px">
          ${shown.map((item, index) => `<button type="button" data-example="${index}" style="padding:${compact ? "9px 12px" : "12px 14px"};border:1px solid ${c.line};border-radius:10px;background:${c.panel};color:${c.ink};text-align:left;font:inherit;font-size:${compact ? 12.5 : 13.5}px;line-height:1.5;cursor:pointer"><span style="display:block;font-size:11px;color:${c.muted};margin-bottom:2px">${item.mode === "agent" ? "Agent" : copy("聊天", "Chat")}</span>${esc(copy(item.zh, item.en))}</button>`).join("")}
        </div>`;
      intro.addEventListener("click", (event) => {
        const example = examples()[Number(event.target.closest?.("[data-example]")?.dataset.example)];
        if (!example || !chat) return;
        setMode(example.mode);
        chat.submitUserMessage({ text: copy(example.zh, example.en) });
      });
      return intro;
    }

    function buildChat(compact) {
      const c = palette(compact);
      const dark = document.documentElement.classList.contains("theme-dark");
      const size = compact ? "13.5px" : "14.5px";
      const el = document.createElement("deep-chat");
      el.className = "iv-deep-chat";
      el.history = history.flatMap(toDeepChat);
      el.chatStyle = { width: "100%", height: "100%", border: "none", backgroundColor: "transparent", fontFamily: "inherit", fontSize: size };
      el.messageStyles = {
        default: {
          shared: { bubble: { maxWidth: compact ? "92%" : "86%", lineHeight: "1.7", padding: compact ? "8px 12px" : "10px 14px" }, outerContainer: { marginTop: compact ? "6px" : "10px" } },
          user: { bubble: { backgroundColor: `color-mix(in srgb, ${c.ink} 7%, ${c.panel})`, color: c.ink, borderRadius: "14px 14px 4px 14px" } },
          ai: { bubble: { backgroundColor: "transparent", color: c.ink, padding: "2px 0", maxWidth: "100%" } },
        },
        html: { shared: { bubble: { backgroundColor: "transparent", padding: "0", maxWidth: "100%" } } },
        loading: { message: { html: `<div class="iv-thinking"><span class="iv-thinking-dots"><i></i><i></i><i></i></span><span class="iv-thinking-text">${esc(copy("正在思考…", "Thinking…"))}</span></div>`,
                              styles: { bubble: { backgroundColor: "transparent", padding: "6px 0" } } } },
        error: { bubble: { backgroundColor: dark ? "#3a1d1d" : "#fef2f2", color: dark ? "#fecaca" : "#b91c1c", borderRadius: "10px", fontSize: "13px" } },
      };
      el.textInput = {
        characterLimit: 8000,
        placeholder: { text: compact ? copy("问点什么…", "Ask something…")
          : domain() === "ielts" ? copy("问一个口语 / 写作问题，或贴一段你的回答…", "Ask about speaking / writing, or paste an answer…")
          : copy("问一个问题，或粘贴一段经历 / JD…", "Ask, or paste an experience / a JD…"), style: { color: c.muted } },
        styles: {
          container: { width: compact ? "calc(100% - 24px)" : "calc(100% - 48px)", maxHeight: compact ? "140px" : "220px", border: `1px solid ${c.line}`, borderRadius: compact ? "12px" : "14px",
                       backgroundColor: compact ? `color-mix(in srgb, ${c.ink} 4%, ${c.panel})` : c.panel,
                       boxShadow: compact ? "none" : "0 1px 2px rgba(15, 23, 42, 0.06), 0 8px 24px rgba(15, 23, 42, 0.06)", padding: "2px 42px 2px 4px" },
          text: { color: c.ink, padding: compact ? "8px 10px" : "11px 12px", fontSize: size },
          focus: { border: `1px solid color-mix(in srgb, ${c.accent} 70%, ${c.line})` },
        },
      };
      const round = { borderRadius: "8px", width: "28px", height: "28px", padding: "3px", marginBottom: compact ? "3px" : "5px", marginRight: "5px" };
      el.submitButtonStyles = {
        position: "inside-end",
        submit: { container: { default: { ...round, backgroundColor: c.ink } }, svg: { styles: { default: { filter: dark ? "none" : "invert(1)" } } } },
        loading: { container: { default: { ...round, backgroundColor: "transparent" } } },
        disabled: { container: { default: { ...round, backgroundColor: c.line } } },
      };
      el.inputAreaStyle = { backgroundColor: "transparent", padding: compact ? "6px 0 10px" : "8px 0 6px" };
      el.scrollButton = true;
      el.errorMessages = { displayServiceErrorMessages: true };
      el.auxiliaryStyle = auxiliaryStyle(c, compact);
      el.htmlClassUtilities = {
        "iv-applied": { events: { click: (event) => { const item = event.target?.closest?.("button.iv-applied"); if (item) { closeDock(); openApplied({ where: item.dataset.where, entryId: item.dataset.entry }); } } } },
        "iv-undo": { events: { click: (event) => undoChanges(event.target?.closest?.(".iv-undo")) } },
        "iv-copy": { events: { click: (event) => copyReply(event.target?.closest?.(".iv-copy")) } },
      };
      el.connect = { handler: (body, signals) => send(body, signals) };
      if (!history.length) el.appendChild(introPanel(compact));
      return el;
    }

    // Puts the chat in a host (page or dock); a host that already shows it keeps it, unless forced (thread changed).
    function mount(host, { force = false } = {}) {
      if (!host) return;
      if (!customElements.get("deep-chat")) {
        host.innerHTML = `<div class="iv-assistant-loading">${esc(copy("正在加载对话组件…", "Loading chat…"))}</div>`;
        loadLibrary().then(() => mount(host, { force: true })).catch((error) => { host.innerHTML = ""; popup(error.message); });
        return;
      }
      if (!force && chat && chat.parentElement === host && chat.dataset.owner === owner) return;
      chat = buildChat(host.id === "ivDockChat");
      chat.dataset.owner = owner;
      host.replaceChildren(chat);
    }

    function pageHost() { const el = byId("ivAssistantChat"); return el?.isConnected ? el : null; }
    function activeHost() { return pageHost() || (dock?.morph.isOpen() ? byId("ivDockChat") : null); }

    async function send(body, signals) {
      const text = String(body?.messages?.slice(-1)[0]?.text || "").trim();
      if (!text) { signals.onResponse({ error: copy("请先输入问题。", "Type a question first.") }); return; }
      const generation = epoch;
      const thread = current;
      const log = history;
      const origin = chat;
      try {
        const payload = await request("/api/interview/assistant/", { message: text, mode, domain: domain(), thread_id: thread || undefined, ai_source: currentAiSourcePreference?.() || "" });
        if (generation !== epoch) return;
        log.push(payload.message, payload.reply);
        if (payload.entries) setCorpus(payload.entries);
        if (payload.ielts_changed) onIeltsChanged();
        threads = [payload.thread, ...(threads || []).filter((item) => item.id !== payload.thread.id)];
        // The candidate may have switched threads while waiting; the reply still lands in its own thread.
        if (history === log) {
          if (!thread) current = payload.thread.id;
          await signals.onResponse(toDeepChat(payload.reply)[0]);
          if (chat !== origin) mount(activeHost(), { force: true });
        }
        if (payload.reply.applied?.length) toast(copy(`已修改语料库 ${payload.reply.applied.length} 处，可在回复下撤销`, `${payload.reply.applied.length} change(s) made — undo below the reply`));
        paint();
      } catch (error) {
        if (generation === epoch && history === log) signals.onResponse({ error: error.message || copy("助手暂时没有回应，请重试。", "No reply; please retry.") });
      }
    }

    async function undoChanges(button) {
      const id = button?.dataset?.message;
      if (!id || button.disabled) return;
      button.disabled = true;
      try {
        const payload = await request(`/api/interview/assistant/messages/${encodeURIComponent(id)}/undo/`, {});
        const message = history.find((item) => item.id === id);
        if (message) Object.assign(message, { undone: true, undoable: false });
        if (payload.entries) setCorpus(payload.entries);
        if (payload.ielts_changed) onIeltsChanged();
        button.closest(".iv-agent")?.classList.add("is-undone");
        button.outerHTML = `<span class="iv-undone">${esc(copy("已撤销这些修改", "Changes undone"))}</span>`;
        toast(copy("已撤销", "Undone"));
      } catch (error) {
        button.disabled = false;
        popup(error.message || copy("撤销失败，请重试。", "Undo failed; please retry."));
      }
    }

    async function copyReply(button) {
      const message = history.find((item) => item.id === button?.dataset?.message);
      if (!message) return;
      try {
        await navigator.clipboard.writeText(message.content);
      } catch (_error) {
        // Embedded browsers may refuse the async clipboard; a selected textarea still copies.
        const area = document.createElement("textarea");
        area.value = message.content;
        area.style.cssText = "position:fixed;opacity:0";
        document.body.appendChild(area);
        area.select();
        document.execCommand?.("copy");
        area.remove();
      }
      button.classList.add("is-done");
      button.innerHTML = `${ICON.check}<span>${esc(copy("已复制", "Copied"))}</span>`;
      window.setTimeout?.(() => { button.classList.remove("is-done"); button.innerHTML = `${ICON.copy}<span>${esc(copy("复制", "Copy"))}</span>`; }, 1600);
    }

    // ---- Mode
    function modeButtons() {
      return MODES.map((item) => `<button type="button" role="radio" aria-checked="${item.id === mode}" class="${item.id === mode ? "active" : ""}${item.id === "agent" ? " is-agent" : ""}" data-iv-assistant="mode" data-mode="${item.id}" title="${esc(copy(item.note[0], item.note[1]))}">${esc(copy(item.zh, item.en))}</button>`).join("");
    }
    function setMode(next) {
      mode = next === "agent" ? "agent" : "chat";
      try { localStorage.setItem(MODE_KEY, mode); } catch (_error) { /* per-viewer convenience only */ }
      document.querySelectorAll("[data-iv-modes]").forEach((el) => { el.innerHTML = modeButtons(); });
    }

    // ---- Page
    function groupLabel(value) {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return copy("更早", "Earlier");
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const days = Math.floor((today - new Date(date.getFullYear(), date.getMonth(), date.getDate())) / 86400000);
      if (days <= 0) return copy("今天", "Today");
      if (days === 1) return copy("昨天", "Yesterday");
      if (days < 7) return copy("近 7 天", "Previous 7 days");
      if (days < 30) return copy("近 30 天", "Previous 30 days");
      return copy("更早", "Earlier");
    }

    function threadList() {
      if (!threads) return `<p class="iv-as-note">${esc(copy("加载中…", "Loading…"))}</p>`;
      const query = search.trim().toLowerCase();
      const shown = query ? threads.filter((item) => item.title.toLowerCase().includes(query)) : threads;
      if (!shown.length) return `<p class="iv-as-note">${esc(query ? copy("没有匹配的对话", "No matching chats") : copy("还没有对话", "No chats yet"))}</p>`;
      let last = "";
      return shown.map((item) => {
        const label = groupLabel(item.updated_at);
        const head = label !== last ? `<p class="iv-as-group">${esc(label)}</p>` : "";
        last = label;
        return `${head}<div class="iv-as-thread${item.id === current ? " active" : ""}">
            <button type="button" class="iv-as-thread-open" data-iv-assistant="open" data-thread="${esc(item.id)}" title="${esc(item.title)}">${esc(item.title)}</button>
            <span class="iv-as-thread-actions">
              <button type="button" data-iv-assistant="rename" data-thread="${esc(item.id)}" title="${esc(copy("重命名", "Rename"))}" aria-label="${esc(copy("重命名", "Rename"))}">${ICON.rename}</button>
              <button type="button" data-iv-assistant="delete" data-thread="${esc(item.id)}" title="${esc(copy("删除", "Delete"))}" aria-label="${esc(copy("删除", "Delete"))}">${ICON.trash}</button>
            </span>
          </div>`;
      }).join("");
    }

    const engineChip = () => engine ? `<span class="iv-as-engine-dot" aria-hidden="true"></span>${esc(engine)}` : "";

    function paint() {
      if (byId("ivAssistantThreads")) byId("ivAssistantThreads").innerHTML = threadList();
      if (byId("ivAssistantTitle")) byId("ivAssistantTitle").textContent = threadTitle();
      if (byId("ivAssistantEngine")) byId("ivAssistantEngine").innerHTML = engineChip();
      if (byId("ivDockTitle")) byId("ivDockTitle").textContent = current ? threadTitle() : copy("AI 助手", "AI assistant");
      if (byId("ivDockMenu") && !byId("ivDockMenu").hidden) byId("ivDockMenu").innerHTML = dockMenu();
    }

    function render() {
      ensureOwner();
      if (threads === null) loadThreads();
      // Mount after the pane is in the DOM.
      window.setTimeout(() => { const host = pageHost(); if (host && !host.firstChild) mount(host, { force: true }); }, 0);
      return `<section id="ivAssistant" class="iv-assistant" data-domain="${domain()}">
          <aside class="iv-as-side" aria-label="${esc(copy("对话列表", "Chats"))}">
            <div class="iv-as-side-head">
              <span class="iv-as-brand">${ICON.spark}<span>${esc(copy("AI 助手", "AI assistant"))}</span></span>
              <button type="button" class="iv-as-icon" data-iv-assistant="new" title="${esc(copy("新对话", "New chat"))}" aria-label="${esc(copy("新对话", "New chat"))}">${ICON.compose}</button>
            </div>
            <label class="iv-as-search">${ICON.search}<input id="ivAssistantSearch" type="search" autocomplete="off" placeholder="${esc(copy("搜索对话", "Search chats"))}" value="${esc(search)}"></label>
            <div id="ivAssistantThreads" class="iv-as-threads">${threadList()}</div>
            <div id="ivAssistantEngine" class="iv-as-engine" title="${esc(copy("回答由本机 Codex 生成", "Answered by local Codex"))}">${engineChip()}</div>
          </aside>
          <div class="iv-as-main">
            <header class="iv-as-bar">
              <h2 id="ivAssistantTitle" class="iv-as-title">${esc(threadTitle())}</h2>
              <div class="iv-as-modes" data-iv-modes role="radiogroup" aria-label="${esc(copy("模式", "Mode"))}">${modeButtons()}</div>
            </header>
            <div id="ivAssistantChat" class="iv-as-chat"></div>
            <p class="iv-as-foot">${esc(copy("Enter 发送 · Shift+Enter 换行 · 回答由 AI 生成，重要信息请核对", "Enter to send · Shift+Enter for a new line · AI answers can be wrong"))}</p>
          </div>
        </section>`;
    }

    function confirm(message, onYes) {
      const overlay = document.createElement("div");
      overlay.className = "confirm-overlay iv-alert-overlay";
      overlay.innerHTML = `<div class="confirm-dialog" role="alertdialog" aria-modal="true"><p>${esc(message)}</p>
        <div class="confirm-actions"><button class="confirm-cancel" type="button">${esc(copy("取消", "Cancel"))}</button><button class="confirm-ok" type="button">${esc(copy("删除", "Delete"))}</button></div></div>`;
      overlay.addEventListener("click", (event) => {
        if (event.target.closest(".confirm-ok")) { overlay.remove(); onYes(); }
        else if (event.target === overlay || event.target.closest(".confirm-cancel")) overlay.remove();
      });
      document.body.appendChild(overlay);
    }

    async function renameThread(id) {
      const item = (threads || []).find((entry) => entry.id === id);
      const button = document.querySelector(`#ivAssistantThreads [data-iv-assistant=open][data-thread="${CSS.escape(id)}"]`);
      if (!item || !button) return;
      // Rename in place: the title becomes an input; Enter / blur saves, Escape cancels.
      const input = document.createElement("input");
      input.className = "iv-as-rename";
      input.value = item.title;
      input.maxLength = 80;
      button.replaceWith(input);
      input.focus();
      input.select();
      let done = false;
      const finish = async (save) => {
        if (done) return;
        done = true;
        const title = input.value.trim();
        if (save && title && title !== item.title) {
          try {
            const payload = await request(`/api/interview/assistant/threads/${encodeURIComponent(id)}/`, { title }, { method: "PATCH" });
            item.title = payload.thread.title;
          } catch (error) { popup(error.message); }
        }
        paint();
      };
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") { event.preventDefault(); finish(true); }
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); finish(false); }
      });
      input.addEventListener("blur", () => finish(true));
    }

    function handleClick(event) {
      const el = event.target.closest?.("#ivAssistant [data-iv-assistant]");
      if (!el) return false;
      const action = el.dataset.ivAssistant;
      const id = el.dataset.thread;
      if (action === "new") openThread(null);
      else if (action === "open" && id !== current) openThread(id);
      else if (action === "mode") { setMode(el.dataset.mode); chat?.focusInput?.(); }
      else if (action === "rename") renameThread(id);
      else if (action === "delete") {
        confirm(copy("删除这段对话？已经写入语料库的内容不受影响。", "Delete this chat? Anything saved to your corpus stays."), async () => {
          try {
            await request(`/api/interview/assistant/threads/${encodeURIComponent(id)}/`, null, { method: "DELETE" });
            threads = (threads || []).filter((item) => item.id !== id);
            if (current === id) openThread(null); else paint();
          } catch (error) { popup(error.message); }
        });
      }
      return true;
    }

    function handleInput(event) {
      if (event.target?.id !== "ivAssistantSearch") return false;
      search = event.target.value;
      if (byId("ivAssistantThreads")) byId("ivAssistantThreads").innerHTML = threadList();
      return true;
    }

    // ---- Dock: a small corner button that grows into a compact chat (same corner morph as the mode switcher).
    function dockMenu() {
      const recent = (threads || []).slice(0, DOCK_RECENT);
      return `<p class="iv-dock-menu-label">${esc(copy("最近的会话", "Recent chats"))}</p>
          ${recent.length ? recent.map((item) => `<button type="button" role="menuitemradio" aria-checked="${item.id === current}" data-iv-dock="open" data-thread="${esc(item.id)}"><span>${esc(item.title)}</span>${item.id === current ? ICON.check : ""}</button>`).join("")
            : `<p class="iv-dock-menu-empty">${esc(copy("还没有对话", "No chats yet"))}</p>`}
          <hr>
          <button type="button" role="menuitem" data-iv-dock="new">${ICON.compose}<span>${esc(copy("新对话", "New chat"))}</span></button>
          <button type="button" role="menuitem" data-iv-dock="page">${ICON.expand}<span>${esc(copy("打开完整页面", "Open full page"))}</span></button>`;
    }

    function toggleDockMenu(open) {
      const menu = byId("ivDockMenu");
      if (!menu) return;
      const show = open ?? menu.hidden;
      if (show) menu.innerHTML = dockMenu();
      menu.hidden = !show;
      byId("ivDockMenuButton")?.setAttribute("aria-expanded", String(show));
    }

    function closeDock() { dock?.morph.close(); }

    function ensureDock() {
      if (dock || !window.IELTSCornerMorph) return dock;
      const root = document.createElement("div");
      root.id = "ivDock";
      root.className = "iv-dock";
      root.hidden = true;
      root.innerHTML = `
        <button type="button" id="ivDockTrigger" class="iv-dock-trigger" aria-label="${esc(copy("AI 助手", "AI assistant"))}" aria-expanded="false" aria-controls="ivDockCard" title="${esc(copy("AI 助手", "AI assistant"))}">${ICON.spark}</button>
        <section id="ivDockCard" class="iv-dock-card" role="dialog" aria-label="${esc(copy("AI 助手", "AI assistant"))}" hidden>
          <div class="iv-dock-body">
            <header class="iv-dock-head">
              <span class="iv-dock-mark" aria-hidden="true">${ICON.spark}</span>
              <strong id="ivDockTitle" class="iv-dock-title">${esc(copy("AI 助手", "AI assistant"))}</strong>
              <div class="iv-as-modes is-compact" data-iv-modes role="radiogroup" aria-label="${esc(copy("模式", "Mode"))}">${modeButtons()}</div>
              <button type="button" class="iv-as-icon" data-iv-dock="new" title="${esc(copy("新对话", "New chat"))}" aria-label="${esc(copy("新对话", "New chat"))}">${ICON.compose}</button>
              <button type="button" id="ivDockMenuButton" class="iv-as-icon" data-iv-dock="menu" title="${esc(copy("最近的会话", "Recent chats"))}" aria-label="${esc(copy("最近的会话", "Recent chats"))}" aria-haspopup="menu" aria-expanded="false">${ICON.dots}</button>
              <div id="ivDockMenu" class="iv-dock-menu" role="menu" hidden></div>
            </header>
            <div id="ivDockChat" class="iv-dock-chat"></div>
          </div>
        </section>`;
      document.body.appendChild(root);
      const card = root.querySelector("#ivDockCard");
      dock = { root, pinned: false };
      dock.morph = window.IELTSCornerMorph.create({
        trigger: root.querySelector("#ivDockTrigger"), card, body: root.querySelector(".iv-dock-body"), root, anchor: "bottom-right",
        closedRadius: "10px", openRadius: "16px", closedBackground: "var(--dock-closed)", hoverBackground: "var(--dock-hover)",
        keepOpen: () => dock.pinned, palette: liftDock,
        onOpenChange: (open) => {
          if (open) {
            ensureOwner();
            if (threads === null) loadThreads();
            paint();
            mount(byId("ivDockChat"));
          } else {
            dock.pinned = false;
            toggleDockMenu(false);
          }
        },
      });
      root.querySelector("#ivDockTrigger").addEventListener("click", () => { dock.pinned = true; dock.morph.open(); });
      // Working in the card (a click, typing) keeps it open when the cursor leaves; outside click / Esc still close it.
      card.addEventListener("pointerdown", () => { dock.pinned = true; });
      card.addEventListener("focusin", () => { dock.pinned = true; });
      card.addEventListener("click", (event) => {
        const el = event.target.closest?.("[data-iv-dock], [data-iv-assistant=mode]");
        if (!el) { if (!event.target.closest?.("#ivDockMenu")) toggleDockMenu(false); return; }
        if (el.dataset.ivAssistant === "mode") { setMode(el.dataset.mode); return; }
        const action = el.dataset.ivDock;
        if (action === "menu") { toggleDockMenu(); return; }
        toggleDockMenu(false);
        if (action === "new") openThread(null);
        else if (action === "open" && el.dataset.thread !== current) openThread(el.dataset.thread);
        else if (action === "page") { closeDock(); openPage(); }
      });
      return dock;
    }

    // Shown on every interview page except the AI 助手 pane itself; hidden for guests and in IELTS mode.
    function syncDock({ visible }) {
      if (!visible && !dock) return;
      ensureDock();
      if (!dock) return;
      if (!visible && dock.morph.isOpen()) dock.morph.close();
      dock.root.hidden = !visible;
      if (visible) liftDock();
      // A mode switch while the dock is open swaps in that mode's chats.
      if (visible && dock.morph.isOpen() && !pageHost()) {
        ensureOwner();
        if (threads === null) loadThreads();
        mount(byId("ivDockChat"));
      }
    }

    function reset() {
      epoch += 1;
      owner = undefined;
      threads = null;
      current = null;
      history = [];
      chat = null;
      search = "";
      closeDock();
      if (byId("ivDockChat")) byId("ivDockChat").replaceChildren();
    }

    // The page wires its own events (it lives in #assistantPanel, outside the interview panel).
    document.addEventListener?.("click", (event) => { handleClick(event); });
    document.addEventListener?.("input", (event) => { handleInput(event); });
    document.addEventListener?.("dblclick", (event) => {
      const el = event.target.closest?.("#ivAssistant .iv-as-thread-open");
      if (el) renameThread(el.dataset.thread);
    });

    return { render, handleClick, handleInput, handleKey: () => false, reset, syncDock };
  }

  window.IELTSInterviewAssistant = { create };
})();
