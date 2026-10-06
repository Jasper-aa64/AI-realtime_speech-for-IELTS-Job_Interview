const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../web/static/interview-assistant.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../web/static/index.html"), "utf8");
const interview = fs.readFileSync(path.join(__dirname, "../web/static/interview.js"), "utf8");
const urls = fs.readFileSync(path.join(__dirname, "../backend_django/config/urls.py"), "utf8");

// A stand-in for the Deep Chat element: the module only sets properties on it and calls its handler.
function harness(responses = {}, { productMode = "interview" } = {}) {
  const ids = {};
  const element = (id) => ({ id, innerHTML: "", textContent: "", firstChild: null, isConnected: true, children: [], appendChild(child) { this.children.push(child); },
    replaceChildren(child) { this.firstChild = child; }, addEventListener() {} });
  const document = {
    getElementById: (id) => (ids[id] ||= element(id)),
    createElement: (tag) => ({ tag, style: {}, dataset: {}, children: [], appendChild(child) { this.children.push(child); }, addEventListener() {} }),
    documentElement: { classList: { contains: () => false } },
    body: {},
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  const calls = [];
  const uploads = [];
  const upload = async (url, form) => {
    uploads.push({ url, form });
    const reply = responses[url];
    return typeof reply === "function" ? reply(form) : reply || {};
  };
  const request = async (url, body = null, options = {}) => {
    calls.push({ url, body, method: options.method || (body ? "POST" : "GET") });
    const reply = responses[url];
    if (reply instanceof Error) throw reply;
    return typeof reply === "function" ? reply(body) : reply || {};
  };
  const opened = [];
  const corpus = [];
  const ieltsChanges = [];
  const context = vm.createContext({
    window: { setTimeout: (fn) => fn() }, document, customElements: { get: () => true },
    getComputedStyle: () => ({ getPropertyValue: () => "" }), CSS: { escape: (v) => v }, encodeURIComponent, FormData, Blob,
  });
  vm.runInContext(source, context);
  const assistant = context.window.IELTSInterviewAssistant.create({
    state: { uiLanguage: "zh", productMode, account: { authenticated: true, user: { id: 7 } } },
    escapeHtml: (v) => String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"),
    request, upload, popup: () => {}, toast: () => {}, setCorpus: (list) => corpus.push(list), openApplied: (item) => opened.push(item),
    onIeltsChanged: () => ieltsChanges.push(true),
    currentAiSourcePreference: () => "gpt",
  });
  return { assistant, ids, calls, uploads, opened, corpus, ieltsChanges, context, chat: () => ids.ivAssistantChat.firstChild };
}

const reply = {
  thread: { id: "iat_1", title: "SPSC 无锁原理", updated_at: "2026-10-06T00:00:00Z" },
  message: { id: "iam_1", role: "user", content: "存一下", target: "knowledge" },
  reply: { id: "iam_2", role: "assistant", content: "已保存。", model: "gpt-6-luna",
           applied: [{ op: "create", where: "knowledge", label: "知识点语料库 · 低延迟与性能 / <SPSC>", entry_id: "icp_9" },
                     { op: "delete", where: "resume", label: "简历题卡 · 行情网关", entry_id: null }], undoable: true, undone: false,
           steps: [{ kind: "library", label: "读取语料库快照", detail: "知识点题卡 3 个" }, { kind: "model", label: "生成回答", detail: "gpt-6-luna · 4.2 s" }] },
  entries: [{ id: "icp_9" }],
};

test("the page lists threads and mounts a Deep Chat with the chat / agent switch", async () => {
  const env = harness({ "/api/interview/assistant/threads/?domain=interview": { threads: [{ id: "iat_1", title: "RAII", updated_at: "" }], engine: "本机 Codex · gpt-6-luna · medium" } });
  const page = env.assistant.render();
  assert.match(page, /data-mode="chat"/);
  assert.match(page, /data-mode="agent"/);
  assert.match(page, /新对话/);
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(env.ids.ivAssistantThreads.innerHTML, /RAII/);
  assert.match(env.ids.ivAssistantEngine.innerHTML, /gpt-6-luna · medium/);
  assert.equal(env.chat().tag, "deep-chat");
  assert.equal(typeof env.chat().connect.handler, "function");
});

test("a message goes to the assistant API with the mode; the reply carries links, undo and the agent trace", async () => {
  const env = harness({ "/api/interview/assistant/threads/?domain=interview": { threads: [] }, "/api/interview/assistant/": reply });
  env.assistant.render();
  env.assistant.handleClick({ target: { closest: () => ({ dataset: { ivAssistant: "mode", mode: "agent" } }) } });
  let answered;
  await env.chat().connect.handler({ messages: [{ role: "user", text: "存一下" }] }, { onResponse: async (message) => { answered = message; } });
  const sent = env.calls.find((call) => call.url === "/api/interview/assistant/");
  assert.equal(sent.body.message, "存一下");
  assert.equal(sent.body.mode, "agent");
  assert.equal(sent.body.thread_id, undefined);
  assert.equal(answered.text, "已保存。");
  assert.match(answered.html, /class="iv-applied is-create" data-where="knowledge" data-entry="icp_9"/);
  assert.match(answered.html, /&lt;SPSC&gt;/, "labels are escaped");
  assert.match(answered.html, /<span class="iv-applied is-delete"><b>✕<\/b>删除 简历题卡 · 行情网关<\/span>/, "deleted cards are not links");
  assert.match(answered.html, /class="iv-undo" data-message="iam_2"/);
  assert.match(answered.html, /执行过程 · 2 步/);
  assert.match(answered.html, /class="iv-copy" data-message="iam_2"/, "every reply can be copied");
  assert.equal(env.corpus.length, 1, "the corpus is refreshed from the reply");
  assert.match(env.ids.ivAssistantThreads.innerHTML, /SPSC 无锁原理/);
  // The next message continues the same thread.
  await env.chat().connect.handler({ messages: [{ role: "user", text: "再来" }] }, { onResponse: async () => {} });
  assert.equal(env.calls.filter((call) => call.url === "/api/interview/assistant/").pop().body.thread_id, "iat_1");
});

test("failures come back as a Deep Chat error bubble; links open the written card", async () => {
  const env = harness({ "/api/interview/assistant/threads/?domain=interview": { threads: [] }, "/api/interview/assistant/": new Error("AI 生成失败") });
  env.assistant.render();
  let answered;
  await env.chat().connect.handler({ messages: [{ role: "user", text: "你好" }] }, { onResponse: async (message) => { answered = message; } });
  assert.deepEqual(JSON.parse(JSON.stringify(answered)), { error: "AI 生成失败" });
  const applied = { dataset: { where: "knowledge", entry: "icp_9" }, closest: () => applied };
  env.chat().htmlClassUtilities["iv-applied"].events.click({ target: applied });
  assert.deepEqual(JSON.parse(JSON.stringify(env.opened)), [{ where: "knowledge", entryId: "icp_9" }]);
});

test("undo posts to the message's undo endpoint and marks the changes undone", async () => {
  const env = harness({ "/api/interview/assistant/threads/?domain=interview": { threads: [] }, "/api/interview/assistant/": reply,
                        "/api/interview/assistant/messages/iam_2/undo/": { message: { id: "iam_2", undone: true }, entries: [] } });
  env.assistant.render();
  await env.chat().connect.handler({ messages: [{ role: "user", text: "整理" }] }, { onResponse: async () => {} });
  const agent = { classes: [], classList: { add(name) { agent.classes.push(name); } } };
  const button = { dataset: { message: "iam_2" }, disabled: false, outerHTML: "", closest: (selector) => (selector === ".iv-undo" ? button : agent) };
  env.chat().htmlClassUtilities["iv-undo"].events.click({ target: button });
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(env.calls.some((call) => call.url === "/api/interview/assistant/messages/iam_2/undo/" && call.method === "POST"));
  assert.match(button.outerHTML, /已撤销这些修改/);
  assert.deepEqual(agent.classes, ["is-undone"]);
});

test("copy puts the reply's Markdown on the clipboard", async () => {
  const env = harness({ "/api/interview/assistant/threads/?domain=interview": { threads: [] }, "/api/interview/assistant/": reply });
  env.assistant.render();
  await env.chat().connect.handler({ messages: [{ role: "user", text: "整理" }] }, { onResponse: async () => {} });
  const copied = [];
  env.context.navigator = { clipboard: { writeText: async (value) => copied.push(value) } };
  const added = [];
  const button = { dataset: { message: "iam_2" }, classList: { add: (name) => added.push(name), remove() {} }, innerHTML: "", closest: () => button };
  env.chat().htmlClassUtilities["iv-copy"].events.click({ target: button });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(copied, ["已保存。"]);
  assert.deepEqual(added, ["is-done"]);
});

test("the dock is wired: syncDock is called from the interview router; the dock grows from the bottom-right corner", () => {
  assert.match(interview, /assistantChat\?\.syncDock\(\{ visible:/);
  assert.match(interview, /state\.view !== "assistant"/);
  assert.match(source, /anchor: "bottom-right"/);
  assert.match(source, /keepOpen: \(\) => dock\.pinned/);
  const morph = fs.readFileSync(path.join(__dirname, "../web/static/corner-morph.js"), "utf8");
  assert.match(morph, /anchor\.startsWith\("bottom"\)/);
});

test("in IELTS mode the assistant uses the IELTS chats, sends domain=ielts and refreshes the IELTS corpora", async () => {
  const ieltsReply = { ...reply, thread: { ...reply.thread, id: "iat_9" }, entries: undefined, ielts_changed: true,
    reply: { ...reply.reply, applied: [{ op: "create", where: "p1", label: "P1 语料 · Hometown · Where is your hometown?", entry_id: "p1:p1q:1" }] } };
  const env = harness({ "/api/interview/assistant/threads/?domain=ielts": { threads: [] }, "/api/interview/assistant/": ieltsReply }, { productMode: "ielts" });
  const page = env.assistant.render();
  assert.match(page, /data-domain="ielts"/);
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(env.calls.some((call) => call.url === "/api/interview/assistant/threads/?domain=ielts"));
  let answered;
  await env.chat().connect.handler({ messages: [{ role: "user", text: "写 P1" }] }, { onResponse: async (message) => { answered = message; } });
  assert.equal(env.calls.find((call) => call.url === "/api/interview/assistant/").body.domain, "ielts");
  assert.deepEqual(env.ieltsChanges, [true]);
  assert.equal(env.corpus.length, 0, "the interview corpus is untouched");
  assert.match(answered.html, /data-where="p1"/);
});

test("the AI 助手 is a shared view: IELTS nav above 积累, its own panel, mode-aware app hooks", () => {
  const app = fs.readFileSync(path.join(__dirname, "../web/static/app.js"), "utf8");
  assert.match(html, /<a id="ieltsAssistantNav" class="nav-button hidden" data-view="assistant"[^>]*>AI 助手<\/a>\s*<span class="nav-section-label" aria-hidden="true">积累<\/span>/);
  assert.match(html, /<section id="assistantPanel"/);
  assert.match(app, /const SHARED_MODE_VIEWS = new Set\(\["home", "history", "corpus", "assistant"\]\)/);
  assert.match(app, /if \(view === "assistant"\) interview\?\.showAssistant\?\.\(\)/);
  assert.match(app, /onIeltsCorpusChanged: \(\) =>/);
});

test("attachments: Deep Chat's FormData becomes a multipart upload with the message, mode and files", async () => {
  const env = harness({ "/api/interview/assistant/threads/?domain=interview": { threads: [] }, "/api/interview/assistant/": reply });
  env.assistant.render();
  assert.equal(env.chat().mixedFiles.files.acceptedFormats, ".pdf,.png,.jpg,.jpeg,.webp,.gif");
  const body = new FormData();
  body.append("files", new Blob(["%PDF"], { type: "application/pdf" }), "cv.pdf");
  body.append("message1", JSON.stringify({ role: "user", text: "这是我的简历" }));
  let answered;
  await env.chat().connect.handler(body, { onResponse: async (message) => { answered = message; } });
  assert.equal(env.uploads.length, 1);
  const form = env.uploads[0].form;
  assert.equal(form.get("message"), "这是我的简历");
  assert.equal(form.get("domain"), "interview");
  assert.equal(form.getAll("files").length, 1);
  assert.equal(answered.text, "已保存。");
  assert.ok(!env.calls.some((call) => call.url === "/api/interview/assistant/"), "files never go through the JSON request");
});

test("简历 / JD 定制: prepare() opens a new Agent chat with the request in the composer", async () => {
  const env = harness({ "/api/interview/assistant/threads/?domain=interview": { threads: [] } });
  env.assistant.render();
  env.assistant.prepare("jd");
  assert.match(env.chat().defaultInput.text, /JD 定制/);
});

test("the AI 助手 pane is wired into the interview nav, router and asset routes", () => {
  assert.match(html, /data-interview-pane="assistant"[^>]*>AI 助手</);
  assert.match(html, /<script src="\/interview-assistant\.js\?v=/);
  assert.match(interview, /"custom", "assistant"\]/);
  assert.match(urls, /path\("interview-assistant\.js"/);
  assert.ok(fs.existsSync(path.join(__dirname, "../web/static/vendor/deep-chat-2.5.1.bundle.js")));
  assert.ok(fs.existsSync(path.join(__dirname, "../web/static/vendor/highlight-11.12.0.min.js")));
});
