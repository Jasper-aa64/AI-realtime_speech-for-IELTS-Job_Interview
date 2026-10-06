// AI 助手: the chat itself is Deep Chat (open-source web component, vendor/deep-chat-*.bundle.js) with highlight.js for
// code; this module adds the thread list and the 聊天 / Agent switch around it, and talks to /api/interview/assistant/.
// In Agent mode the assistant creates, edits and deletes cards in 知识点语料库 / 简历题卡 / JD 与反问 (the server
// validates and applies its actions); each reply carries the agent trace, links to the cards and a one-click undo.
(function () {
  const DEEP_CHAT = "/vendor/deep-chat-2.5.1.bundle.js";
  const HIGHLIGHT = "/vendor/highlight-11.12.0.min.js";
  const MODES = [
    { id: "chat", zh: "聊天", en: "Chat", note: ["只回答，不改语料库", "Answers only; your corpus is untouched"] },
    { id: "agent", zh: "Agent 模式", en: "Agent", note: ["可以新建、修改、删除你的题卡；每次修改都能一键撤销", "Creates, edits and deletes your cards; every change can be undone"] },
  ];
  const MODE_KEY = "iv-assistant-mode";
  const EXAMPLES = [
    { mode: "chat", zh: "讲讲 SPSC 无锁队列怎么实现，为什么要做缓存行对齐", en: "How does an SPSC lock-free queue work?" },
    { mode: "agent", zh: "把我知识点里低延迟相关的题卡整理一下：合并重复的，答得太短的补全", en: "Tidy my low-latency cards: merge duplicates, fill in thin answers" },
    { mode: "agent", zh: "把我简历里的实习经历写成 STAR 题卡，并预判 3 个追问", en: "Turn my internship into a STAR card with 3 follow-ups" },
    { mode: "agent", zh: "下面是一个 JD：……  帮我建一张 JD 卡，出 3 道岗位题和 2 个反问", en: "Here is a JD: … make a JD card with 3 role questions and 2 to ask" },
  ];
  const STEP_MARK = { library: "◎", model: "✦", validate: "✓", create: "＋", update: "✎", delete: "✕", skip: "!" };
  const OP_MARK = { create: "✓", update: "✎", delete: "✕" };

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

  function create({ state, escapeHtml, request, popup, toast, setCorpus, openApplied, currentAiSourcePreference }) {
    let threads = null; // [{id, title, updated_at}]
    let current = null; // thread id, null = new chat
    let history = []; // messages of the current thread, as the server returns them
    let mode = "chat";
    try { mode = localStorage.getItem(MODE_KEY) === "agent" ? "agent" : "chat"; } catch (_error) { /* per-viewer convenience only */ }
    let owner;
    let epoch = 0;
    let chat = null;
    const byId = (id) => document.getElementById(id);
    const copy = (zh, en) => state.uiLanguage === "en" ? en : zh;
    const esc = (value) => escapeHtml(String(value ?? ""));

    // ---- Server
    async function loadThreads() {
      const generation = epoch;
      try {
        const payload = await request("/api/interview/assistant/threads/");
        if (generation !== epoch) return;
        threads = payload.threads || [];
      } catch (_error) {
        if (generation === epoch) threads = threads || [];
      }
      paintThreads();
    }

    async function openThread(id) {
      const generation = epoch;
      current = id;
      history = [];
      paintThreads();
      if (!id) { mountChat(); return; }
      try {
        const payload = await request(`/api/interview/assistant/threads/${encodeURIComponent(id)}/`);
        if (generation !== epoch || current !== id) return;
        history = payload.messages || [];
        mountChat();
      } catch (error) {
        if (generation === epoch) popup(error.message || copy("对话加载失败。", "Could not load the chat."));
      }
    }

    // ---- Deep Chat messages
    function traceHtml(message) {
      const steps = message.steps || [];
      const applied = message.applied || [];
      if (!steps.length && !applied.length) return "";
      const word = { create: copy("新建", "Created"), update: copy("修改", "Edited"), delete: copy("删除", "Deleted") };
      // A deleted card has nothing to open; the others link to the card.
      const links = applied.map((item) => item.op === "delete"
        ? `<span class="iv-applied is-delete"><b>${OP_MARK.delete}</b>${esc(word.delete)} ${esc(item.label)}</span>`
        : `<button type="button" class="iv-applied is-${esc(item.op || "create")}" data-where="${esc(item.where)}" data-entry="${esc(item.entry_id)}"><b>${OP_MARK[item.op] || "✓"}</b>${esc(word[item.op] || word.create)} ${esc(item.label)}<i>→</i></button>`).join("");
      const undo = message.undone ? `<span class="iv-undone">${esc(copy("已撤销这些修改", "Changes undone"))}</span>`
        : message.undoable ? `<button type="button" class="iv-undo" data-message="${esc(message.id)}">↶ ${esc(copy("撤销这些修改", "Undo these changes"))}</button>` : "";
      const rows = steps.map((step) => `<li class="is-${esc(step.kind)}"><span>${STEP_MARK[step.kind] || "·"}</span><strong>${esc(step.label)}</strong>${step.detail ? `<em>${esc(step.detail)}</em>` : ""}</li>`).join("");
      return `<div class="iv-agent${message.undone ? " is-undone" : ""}">${links || undo ? `<div class="iv-applied-list">${links}${undo}</div>` : ""}
          <details class="iv-trace"><summary>${esc(copy(`Agent 执行过程 · ${steps.length} 步`, `Agent trace · ${steps.length} steps`))}</summary><ol>${rows}</ol></details></div>`;
    }

    function toDeepChat(message) {
      if (message.role === "user") return [{ role: "user", text: message.content }];
      const trace = traceHtml(message);
      return [trace ? { role: "ai", text: message.content, html: trace } : { role: "ai", text: message.content }];
    }

    // Colours come from the app's tokens at mount time, so every appearance style (and dark mode) carries over.
    function palette() {
      const css = getComputedStyle(document.body);
      const token = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
      return { ink: token("--ink", "#0d0d0d"), muted: token("--muted", "#6e6e80"), line: token("--line", "#ececf1"),
               panel: token("--panel", "#ffffff"), bg: token("--bg", "#f7f7f8"), accent: token("--accent", "#10a37f") };
    }

    function auxiliaryStyle(c) {
      return `
        .iv-agent { display: grid; gap: 8px; font: 13px/1.5 inherit; }
        .iv-applied-list { display: flex; flex-wrap: wrap; gap: 8px; }
        .iv-applied { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border: 1px solid color-mix(in srgb, ${c.accent} 45%, ${c.line});
          border-radius: 999px; background: color-mix(in srgb, ${c.accent} 9%, ${c.panel}); color: ${c.ink}; font: inherit; cursor: pointer; }
        .iv-applied:hover { border-color: ${c.accent}; background: color-mix(in srgb, ${c.accent} 16%, ${c.panel}); }
        .iv-applied b { color: ${c.accent}; } .iv-applied i { font-style: normal; color: ${c.muted}; }
        .iv-applied.is-delete { cursor: default; border-color: ${c.line}; background: transparent; color: ${c.muted}; }
        .iv-applied.is-delete b { color: #dc2626; }
        .iv-agent.is-undone .iv-applied { opacity: 0.5; text-decoration: line-through; pointer-events: none; }
        .iv-undo { padding: 6px 12px; border: 1px solid ${c.line}; border-radius: 999px; background: ${c.panel}; color: ${c.ink}; font: inherit; cursor: pointer; }
        .iv-undo:hover { border-color: ${c.ink}; }
        .iv-undo:disabled { opacity: 0.5; cursor: default; }
        .iv-undone { padding: 6px 4px; color: ${c.muted}; }
        .iv-trace li.is-skip span, .iv-trace li.is-delete span { color: #dc2626; }
        .iv-trace { color: ${c.muted}; }
        .iv-trace summary { cursor: pointer; width: fit-content; list-style: none; padding: 2px 0; }
        .iv-trace summary::-webkit-details-marker { display: none; }
        .iv-trace summary::before { content: "▸"; display: inline-block; width: 14px; transition: transform 160ms ease; }
        .iv-trace[open] summary::before { transform: rotate(90deg); }
        .iv-trace ol { margin: 6px 0 0; padding: 0 0 0 4px; list-style: none; display: grid; gap: 4px; border-left: 2px solid ${c.line}; }
        .iv-trace li { display: flex; gap: 8px; align-items: baseline; padding-left: 10px; }
        .iv-trace li span { width: 14px; color: ${c.accent}; } .iv-trace li strong { color: ${c.ink}; font-weight: 500; }
        .iv-trace li em { font-style: normal; }
        .outer-message-container .message-bubble pre { border-radius: 10px; }
        .outer-message-container .message-bubble table { border-collapse: collapse; }
        .outer-message-container .message-bubble th, .outer-message-container .message-bubble td { border: 1px solid ${c.line}; padding: 4px 8px; }
        .outer-message-container .message-bubble p { margin: 0.4em 0; }
        .outer-message-container .message-bubble blockquote { margin: 0.4em 0; padding-left: 10px; border-left: 3px solid ${c.line}; color: ${c.muted}; }`;
    }

    function mountChat() {
      const host = byId("ivAssistantChat");
      if (!host) return;
      if (!customElements.get("deep-chat")) {
        host.innerHTML = `<div class="iv-assistant-loading">${esc(copy("正在加载对话组件…", "Loading chat…"))}</div>`;
        loadLibrary().then(() => mountChat()).catch((error) => { host.innerHTML = ""; popup(error.message); });
        return;
      }
      const c = palette();
      const dark = document.documentElement.classList.contains("theme-dark");
      chat = document.createElement("deep-chat");
      chat.className = "iv-deep-chat";
      chat.history = history.flatMap(toDeepChat);
      chat.chatStyle = { width: "100%", height: "100%", border: "none", backgroundColor: "transparent", fontFamily: "inherit", fontSize: "14.5px" };
      chat.messageStyles = {
        default: {
          shared: { bubble: { maxWidth: "88%", lineHeight: "1.7", padding: "10px 14px" } },
          user: { bubble: { backgroundColor: `color-mix(in srgb, ${c.accent} 14%, ${c.panel})`, color: c.ink, borderRadius: "16px 16px 4px 16px" } },
          ai: { bubble: { backgroundColor: "transparent", color: c.ink, padding: "4px 0", maxWidth: "100%" } },
        },
        html: { shared: { bubble: { backgroundColor: "transparent", padding: "0", maxWidth: "100%" } } },
        loading: { message: { styles: { bubble: { backgroundColor: "transparent", color: c.accent } } } },
        error: { bubble: { backgroundColor: dark ? "#3a1d1d" : "#fef2f2", color: dark ? "#fecaca" : "#b91c1c", borderRadius: "12px" } },
      };
      // No avatars (as in ChatGPT): the answer reads as the page, the user's messages sit in bubbles.
      chat.textInput = {
        characterLimit: 8000,
        placeholder: { text: copy("问一个问题，或粘贴一段经历 / JD……（Enter 发送，Shift+Enter 换行）", "Ask, or paste an experience / a JD… (Enter to send)"), style: { color: c.muted } },
        styles: {
          container: { width: "calc(100% - 64px)", maxHeight: "200px", border: `1px solid ${c.line}`, borderRadius: "18px", backgroundColor: c.panel, boxShadow: "0 8px 20px rgba(15, 23, 42, 0.07)", padding: "4px 46px 4px 6px" },
          text: { color: c.ink, padding: "10px 12px", fontSize: "14.5px" },
          focus: { border: `1px solid ${c.accent}` },
        },
      };
      chat.submitButtonStyles = {
        position: "inside-end",
        submit: { container: { default: { backgroundColor: c.ink, borderRadius: "50%", width: "30px", height: "30px", padding: "3px", marginBottom: "4px", marginRight: "6px" } }, svg: { styles: { default: { filter: dark ? "none" : "invert(1)" } } } },
        loading: { container: { default: { backgroundColor: "transparent" } } },
        disabled: { container: { default: { backgroundColor: c.line, borderRadius: "50%", width: "30px", height: "30px", padding: "3px", marginBottom: "4px", marginRight: "6px" } } },
      };
      chat.inputAreaStyle = { backgroundColor: "transparent", padding: "8px 0 14px" };
      chat.scrollButton = true;
      chat.errorMessages = { displayServiceErrorMessages: true };
      chat.auxiliaryStyle = auxiliaryStyle(c);
      chat.htmlClassUtilities = {
        "iv-applied": { events: { click: (event) => { const el = event.target?.closest?.("button.iv-applied"); if (el) openApplied({ where: el.dataset.where, entryId: el.dataset.entry }); } } },
        "iv-undo": { events: { click: (event) => undoChanges(event.target?.closest?.(".iv-undo")) } },
      };
      chat.connect = { handler: (body, signals) => send(body, signals) };
      if (!history.length) chat.appendChild(introPanel());
      host.replaceChildren(chat);
    }

    // Deep Chat shows its child element until the first message.
    function introPanel() {
      const intro = document.createElement("div");
      intro.className = "iv-assistant-intro";
      intro.style.cssText = "display:grid;justify-items:center;gap:10px;text-align:center;padding:24px 12px;max-width:640px;font-family:inherit";
      const c = palette();
      intro.innerHTML = `
        <div style="width:44px;height:44px;border-radius:50%;display:grid;place-items:center;background:${c.accent};color:#fff;font-weight:700">AI</div>
        <div style="font-size:21px;font-weight:650;color:${c.ink}">${esc(copy("有什么想问的？", "What would you like to ask?"))}</div>
        <div style="font-size:13.5px;color:${c.muted};line-height:1.6;max-width:460px">${esc(copy("聊天模式只回答问题；切到 Agent 模式，它会直接整理你的语料库——新建、修改、删除题卡，改错了可以一键撤销。", "Chat answers questions; Agent mode tidies your corpus — creating, editing and deleting cards, with one-click undo."))}</div>
        <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;width:100%;margin-top:10px">
          ${EXAMPLES.map((item, index) => `<button type="button" data-example="${index}" style="padding:12px 14px;border:1px solid ${c.line};border-radius:12px;background:${c.panel};color:${c.ink};text-align:left;font:inherit;font-size:13.5px;line-height:1.5;cursor:pointer">${esc(copy(item.zh, item.en))}</button>`).join("")}
        </div>`;
      intro.addEventListener("click", (event) => {
        const example = EXAMPLES[Number(event.target.closest?.("[data-example]")?.dataset.example)];
        if (!example || !chat) return;
        setMode(example.mode);
        chat.submitUserMessage({ text: copy(example.zh, example.en) });
      });
      return intro;
    }

    async function send(body, signals) {
      const text = String(body?.messages?.slice(-1)[0]?.text || "").trim();
      if (!text) { signals.onResponse({ error: copy("请先输入问题。", "Type a question first.") }); return; }
      const generation = epoch;
      const thread = current;
      try {
        const payload = await request("/api/interview/assistant/", { message: text, mode, thread_id: thread || undefined, ai_source: currentAiSourcePreference?.() || "" });
        if (generation !== epoch) return;
        history.push(payload.message, payload.reply);
        if (!thread) current = payload.thread.id;
        if (payload.entries) setCorpus(payload.entries);
        await signals.onResponse(toDeepChat(payload.reply)[0]);
        if (payload.reply.applied?.length) toast(copy(`已修改语料库 ${payload.reply.applied.length} 处，可在回复下撤销`, `${payload.reply.applied.length} change(s) made — undo below the reply`));
        threads = [payload.thread, ...(threads || []).filter((item) => item.id !== payload.thread.id)];
        paintThreads();
      } catch (error) {
        if (generation === epoch) signals.onResponse({ error: error.message || copy("助手暂时没有回应，请重试。", "No reply; please retry.") });
      }
    }

    // ---- Page around the chat
    function threadList() {
      if (!threads) return `<p class="iv-assistant-note">${esc(copy("加载中…", "Loading…"))}</p>`;
      if (!threads.length) return `<p class="iv-assistant-note">${esc(copy("还没有对话", "No chats yet"))}</p>`;
      return threads.map((item) => `<div class="iv-assistant-thread${item.id === current ? " active" : ""}">
          <button type="button" data-iv-assistant="open" data-thread="${esc(item.id)}" title="${esc(item.title)}">${esc(item.title)}</button>
          <button type="button" class="iv-assistant-thread-menu" data-iv-assistant="rename" data-thread="${esc(item.id)}" aria-label="${esc(copy("重命名", "Rename"))}">✎</button>
          <button type="button" class="iv-assistant-thread-menu" data-iv-assistant="delete" data-thread="${esc(item.id)}" aria-label="${esc(copy("删除", "Delete"))}">×</button>
        </div>`).join("");
    }
    function paintThreads() { const el = byId("ivAssistantThreads"); if (el) el.innerHTML = threadList(); }
    function modeButtons() {
      return MODES.map((item) => `<button type="button" role="radio" aria-checked="${item.id === mode}" class="${item.id === mode ? "active" : ""}${item.id === "agent" ? " is-agent" : ""}" data-iv-assistant="mode" data-mode="${item.id}">${esc(copy(item.zh, item.en))}</button>`).join("");
    }
    const modeNote = () => { const note = MODES.find((item) => item.id === mode).note; return copy(note[0], note[1]); };
    function setMode(next) {
      mode = next === "agent" ? "agent" : "chat";
      try { localStorage.setItem(MODE_KEY, mode); } catch (_error) { /* per-viewer convenience only */ }
      const el = byId("ivAssistantModes");
      if (el) el.innerHTML = modeButtons();
      if (byId("ivAssistantModeNote")) byId("ivAssistantModeNote").textContent = modeNote();
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
        button.closest(".iv-agent")?.classList.add("is-undone");
        button.outerHTML = `<span class="iv-undone">${esc(copy("已撤销这些修改", "Changes undone"))}</span>`;
        toast(copy("已撤销", "Undone"));
      } catch (error) {
        button.disabled = false;
        popup(error.message || copy("撤销失败，请重试。", "Undo failed; please retry."));
      }
    }

    function render() {
      const id = state.account.user?.id || null;
      if (id !== owner) { owner = id; threads = null; current = null; history = []; }
      if (threads === null) loadThreads();
      // Mount after the pane is in the DOM.
      window.setTimeout(() => { if (byId("ivAssistantChat") && !byId("ivAssistantChat").firstChild) mountChat(); }, 0);
      return `<section id="ivAssistant" class="iv-assistant">
          <aside class="iv-assistant-side">
            <button type="button" class="iv-assistant-new" data-iv-assistant="new"><span aria-hidden="true">＋</span>${esc(copy("新对话", "New chat"))}</button>
            <div id="ivAssistantThreads" class="iv-assistant-threads">${threadList()}</div>
          </aside>
          <div class="iv-assistant-main">
            <div class="iv-assistant-bar">
              <div id="ivAssistantModes" class="iv-assistant-targets" role="radiogroup" aria-label="${esc(copy("模式", "Mode"))}">${modeButtons()}</div>
              <span id="ivAssistantModeNote" class="iv-assistant-note">${esc(modeNote())}</span>
            </div>
            <div id="ivAssistantChat" class="iv-assistant-chat"></div>
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
      input.className = "iv-assistant-rename";
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
        paintThreads();
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
            if (current === id) openThread(null); else paintThreads();
          } catch (error) { popup(error.message); }
        });
      }
      return true;
    }

    function reset() {
      epoch += 1;
      owner = undefined;
      threads = null;
      current = null;
      history = [];
      chat = null;
    }

    return { render, handleClick, handleInput: () => false, handleKey: () => false, reset };
  }

  window.IELTSInterviewAssistant = { create };
})();
