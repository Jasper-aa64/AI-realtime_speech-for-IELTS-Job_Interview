const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const source = fs.readFileSync(path.join(__dirname, "../web/static/interview.js"), "utf8");
const clone = (value) => JSON.parse(JSON.stringify(value));
const settle = async () => { for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setImmediate(resolve)); };

function fixture({ desktop = true, storedMode = "ielts", decisionFails = true, scoreFails = false } = {}) {
  let focused;
  class Element {
    constructor(dataset = {}) { this.dataset = dataset; this.handlers = {}; this.attrs = {}; this.hidden = true; this.innerHTML = ""; this.classes = new Set(); this.classList = { toggle: (name, active) => active ? this.classes.add(name) : this.classes.delete(name), remove: (name) => this.classes.delete(name), add: (name) => this.classes.add(name) }; }
    addEventListener(type, callback) { (this.handlers[type] ||= []).push(callback); }
    emit(type, event = {}) { for (const callback of this.handlers[type] || []) callback(event); }
    setAttribute(name, value) { this.attrs[name] = value; }
    focus() { focused = this; }
    contains(node) { return node === this; }
    closest() { return this; }
    querySelectorAll() { return []; }
    querySelector() { return null; }
  }
  const ids = Object.fromEntries(["interviewPanel", "interviewNav", "studioModeControl", "studioModeTrigger", "studioModeMenu", "studioModeLabel", "viewTitle", "viewSubtitle"].map((id) => [id, new Element()]));
  const modes = [new Element({ studioMode: "ielts" }), new Element({ studioMode: "interview" })];
  modes[0].attrs["aria-checked"] = "true";
  ids.studioModeMenu.querySelectorAll = () => modes;
  ids.studioModeMenu.querySelector = () => modes.find((el) => el.attrs["aria-checked"] === "true");
  const document = new Element();
  document.body = new Element();
  document.getElementById = (id) => ids[id];
  document.querySelectorAll = (selector) => selector.includes("data-studio-mode") ? modes : [];
  Object.defineProperty(document, "activeElement", { get: () => focused });
  const state = { uiLanguage: "zh", account: { authenticated: true, user: { id: 1 } }, view: "interview", practiceLocked: false };
  const window = new Element();
  window.IELTSNativeBridge = { ready: Promise.resolve({ desktop, mock_interview: desktop, native_audio: false }) };
  const requests = [];
  const store = new Map([["ielts-product-mode", storedMode]]);
  let deferred;
  const corpus = [
    { id: "icp_gw", kind: "project", title: "撮合网关", question: "介绍一下你的「撮合网关」项目。", corpus_text: "", ai_draft: "AI 讲述稿", source: "resume", source_key: "resume:project:gw", parent_id: null, orphaned: false },
    { id: null, kind: "knowledge", group: "C++ 基础与进阶", question: "解释 RAII。", corpus_text: "", ai_draft: "", source: "curated", source_key: "curated:cpp-1", parent_id: null, orphaned: false },
  ];
  const saved = { session: { id: "int_1", part: "full", intensity: "standard", plan: ["self_intro", "project"], title: "完整面试", status: "active", created_at: "2026-10-05T00:00:00Z", score: null },
    turns: [{ id: "t1", order: 1, kind: "main", stage: "self_intro", prompt: "请先做一个简单的自我介绍。", status: "pending", answer: "" },
            { id: "t2", order: 2, kind: "main", stage: "project", prompt: "介绍一下你的「撮合网关」项目。", status: "pending", answer: "", corpus_entry_id: "icp_gw" }] };
  const details = () => clone({ ...saved, current_turn: saved.session.status === "active" ? saved.turns.find((turn) => turn.status === "pending") || null : null });
  const api = async (url, body, options = {}) => {
    requests.push({ url, body: clone(body ?? null), method: options.method || (body === null || body === undefined ? "GET" : "POST"), signal: options.signal });
    if (deferred && url === "/api/interview/sessions/" && !body) return deferred;
    if (url === "/api/interview/questions/") return { questions: [], categories: [{ id: "cpp", label: "C++ 基础与进阶" }] };
    if (url === "/api/interview/sessions/" && !body) return { sessions: [] };
    if (url === "/api/interview/profile/") return { profile: { resume: { modules: [], updated_at: "2026-10-05T00:00:00Z" }, jd: { summary: {} } } };
    if (url === "/api/interview/corpus/" && !body) return { entries: clone(corpus) };
    if (url === "/api/interview/corpus/") return { entry: { ...clone(corpus[1]), id: "icp_new", corpus_text: body.corpus_text } };
    if (url.startsWith("/api/interview/corpus/") && options.method === "PATCH") return { entry: { ...clone(corpus[0]), corpus_text: body.corpus_text } };
    if (url === "/api/interview/profile/jd/") return { profile: { resume: {}, jd: { summary: { role: "C++ 开发", requirements: [] }, updated_at: "2026-10-05T00:00:00Z" } }, entries: clone(corpus) };
    if (url === "/api/interview/sessions/") { saved.session.intensity = body.intensity; return details(); }
    if (url.endsWith("/answer/")) {
      const turn = saved.turns.find((item) => url.includes(`/${item.id}/`));
      turn.status = "completed"; turn.answer = body.answer; turn.answer_source = body.answer_source;
      turn.decision = decisionFails ? { status: "failed", action: "next" } : { status: "ready", action: "follow_up", signal: "strong" };
      if (!decisionFails) saved.turns.splice(1, 0, { id: "f1", order: 2, kind: "follow_up", parent_turn_id: turn.id, stage: turn.stage, prompt: "你在之前的团队里负责什么？", status: "pending", answer: "" });
      return details();
    }
    if (url.endsWith("/skip/")) { saved.turns.find((item) => url.includes(`/${item.id}/`)).status = "skipped"; return details(); }
    if (url.endsWith("/finish/")) { saved.session.status = "completed"; saved.turns.forEach((turn) => { if (turn.status === "pending") turn.status = "skipped"; }); return details(); }
    if (url.endsWith("/report/")) {
      if (scoreFails) throw new Error("AI 服务还没有配置");
      saved.session.score = { status: "ready", total: 72, summary: "表达清楚", dimensions: [{ key: "technical_depth", label: "技术深度", score: 20, max: 30, evidence: "e" }], per_turn: [], next_steps: ["多讲量化结果"], boundary: "并发细节" };
      return details();
    }
    return details();
  };
  vm.runInNewContext(source, { window, document, localStorage: { getItem: (key) => store.get(key), setItem: (key, value) => store.set(key, value) }, AbortController, FormData, Blob, fetch: async () => ({ ok: false, text: async () => "{}" }) });
  let loginRequested = false;
  let exited = false;
  const app = window.IELTSInterview.createInterview({ state, api, ensureCsrfToken: async () => "csrf", switchView: (view) => { state.view = view; }, exitPractice: async () => { exited = true; state.practiceLocked = false; }, promptGuestLogin: () => { loginRequested = true; }, currentAiSourcePreference: () => "gpt", escapeHtml: (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;") });
  const action = async (name, extra = {}) => { ids.interviewPanel.emit("click", { target: new Element({ interviewAction: name, ...extra }) }); await settle(); };
  const input = (field, value) => { const target = new Element({ interviewField: field }); target.value = value; ids.interviewPanel.emit("input", { target }); };
  return { app, state, ids, modes, document, requests, saved, store, action, input, html: () => ids.interviewPanel.innerHTML, setDeferred: (promise) => { deferred = promise; }, loginRequested: () => loginRequested, exited: () => exited, focused: () => focused };
}

async function started(options) {
  const env = fixture(options);
  await env.app.initialize(); env.app.show(); await settle();
  env.app.setPane("practice", { part: "full" }); await settle();
  return env;
}

test("full interview: start, type an answer, interviewer moves on, finish and auto-score", async () => {
  const env = await started();
  assert.match(env.html(), /点击「开始」/);
  await env.action("start-session");
  const created = env.requests.find((request) => request.url === "/api/interview/sessions/" && request.body);
  assert.deepEqual(created.body, { part: "full", intensity: "standard" });
  assert.match(env.html(), /请先做一个简单的自我介绍/);
  await env.action("type-answer");
  env.input("answer", "我是张三 <script>x</script>");
  await env.action("submit-answer");
  const answered = env.requests.find((request) => request.url.endsWith("/answer/"));
  assert.deepEqual([answered.body.answer, answered.body.answer_source, answered.body.ai_source], ["我是张三 <script>x</script>", "typed", "gpt"]);
  assert.match(env.html(), /面试官这次没能追问/);
  assert.match(env.html(), /撮合网关/);
  await env.action("toggle-peek");
  assert.match(env.html(), /AI 讲述稿/);
  await env.action("skip");
  assert.match(env.html(), /data-interview-action="finish"/);
  await env.action("finish");
  assert.ok(env.requests.some((request) => request.url.endsWith("/report/")));
  assert.match(env.html(), /<strong>72<\/strong>/);
  assert.match(env.html(), /并发细节/);
  assert.match(env.html(), /&lt;script>/);
  assert.doesNotMatch(env.html(), /<script>x/);
  assert.ok(env.requests.every((request) => request.url.endsWith("/")));
});

test("follow-up from the interviewer is labelled; pressure intensity is sent", async () => {
  const env = await started({ decisionFails: false });
  await env.action("intensity", { intensity: "pressure" });
  await env.action("start-session");
  assert.equal(env.requests.find((request) => request.url === "/api/interview/sessions/" && request.body).body.intensity, "pressure");
  await env.action("type-answer"); env.input("answer", "回答"); await env.action("submit-answer");
  assert.match(env.html(), /追问 · 往深处挖/);
  assert.match(env.html(), /你在之前的团队里负责什么/);
});

test("recording falls back to typing when the microphone API is unavailable; empty answers are refused", async () => {
  const env = await started();
  await env.action("start-session");
  await env.action("record-start");
  assert.match(env.html(), /当前环境不支持录音/);
  assert.match(env.html(), /id="interviewAnswer"/);
  await env.action("submit-answer");
  assert.match(env.html(), /回答是空的/);
  assert.ok(!env.requests.some((request) => request.url.endsWith("/answer/")));
});

test("score failure keeps the transcript and offers a retry", async () => {
  const env = await started({ scoreFails: true });
  await env.action("start-session");
  await env.action("skip"); await env.action("skip");
  await env.action("finish");
  assert.match(env.html(), /AI 服务还没有配置/);
  assert.match(env.html(), /data-interview-action="score"/);
  assert.match(env.html(), /请先做一个简单的自我介绍/);
});

test("corpus: curated questions save by key, existing entries patch, JD side generates", async () => {
  const env = fixture(); await env.app.initialize(); env.app.show(); await settle();
  env.app.setPane("corpus"); await settle();
  assert.match(env.html(), /撮合网关/);
  await env.action("corpus-tab", { tab: "knowledge" });
  assert.match(env.html(), /解释 RAII/);
  await env.action("edit-entry", { sourceKey: "curated:cpp-1" });
  env.input("editor-text", "我的 RAII 答法");
  await env.action("save-entry");
  const created = env.requests.find((request) => request.url === "/api/interview/corpus/" && request.body);
  assert.deepEqual(created.body, { kind: "knowledge", source_key: "curated:cpp-1", corpus_text: "我的 RAII 答法" });
  await env.action("corpus-tab", { tab: "project" });
  await env.action("edit-entry", { entryId: "icp_gw" });
  await env.action("adopt-draft");
  await env.action("save-entry");
  const patched = env.requests.find((request) => request.method === "PATCH");
  assert.equal(patched.body.corpus_text, "AI 讲述稿");
  env.app.setPane("custom"); await settle();
  await env.action("custom-side", { side: "jd" });
  env.input("jdText", "招聘 C++ 开发");
  await env.action("import-jd");
  assert.equal(env.requests.find((request) => request.url === "/api/interview/profile/jd/").body.job_description, "招聘 C++ 开发");
  assert.match(env.html(), /C\+\+ 开发/);
});

test("account reset cancels in-flight requests and discards private data", async () => {
  const env = fixture(); await env.app.initialize();
  let resolve; env.setDeferred(new Promise((done) => { resolve = done; }));
  env.app.show(); await settle();
  const pending = env.requests.find((request) => request.url === "/api/interview/sessions/");
  env.state.account.user = { id: 2 }; env.app.resetForAccount();
  assert.equal(pending.signal.aborted, true);
  resolve({ sessions: [{ id: "secret", title: "Previous user's private interview", status: "active", part: "full" }] }); await settle();
  assert.doesNotMatch(env.html(), /Previous user's private interview/);
});

test("mode menu keyboard, Escape, outside close, and IELTS abort are functional", async () => {
  const env = fixture({ storedMode: "interview" }); await env.app.initialize();
  assert.equal(env.state.productMode, "interview");
  env.ids.studioModeTrigger.emit("keydown", { key: "ArrowDown", preventDefault() {} });
  assert.equal(env.ids.studioModeMenu.hidden, false);
  env.ids.studioModeMenu.emit("keydown", { key: "Home", preventDefault() {} }); assert.equal(env.focused(), env.modes[0]);
  env.ids.studioModeMenu.emit("keydown", { key: "Escape", preventDefault() {} }); assert.equal(env.ids.studioModeMenu.hidden, true);
  env.ids.studioModeTrigger.emit("click"); env.document.emit("pointerdown", { target: {} }); assert.equal(env.ids.studioModeMenu.hidden, true);
  env.app.setProductMode("ielts"); env.state.practiceLocked = true;
  env.ids.studioModeMenu.emit("click", { target: env.modes[1] }); await settle();
  assert.equal(env.exited(), true); assert.equal(env.state.view, "interview");
});

test("browser capability absence keeps mode hidden; guests never call authenticated interview APIs", async () => {
  const browser = fixture({ desktop: false, storedMode: "interview" }); await browser.app.initialize(); browser.app.setProductMode("interview"); browser.app.show();
  assert.equal(browser.state.productMode, "ielts");
  assert.equal(browser.requests.length, 0);
  const guest = fixture(); guest.state.account.authenticated = false; guest.state.account.user = null;
  await guest.app.initialize(); guest.app.show(); assert.match(guest.html(), /登录并开始/);
  await guest.action("login"); assert.equal(guest.loginRequested(), true); assert.equal(guest.requests.length, 0);
});
