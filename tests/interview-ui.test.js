const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const source = fs.readFileSync(path.join(__dirname, "../web/static/interview.js"), "utf8");
const clone = (value) => JSON.parse(JSON.stringify(value));
const settle = () => new Promise((resolve) => setImmediate(resolve));

function fixture({ desktop = true, storedMode = "ielts" } = {}) {
  let focused;
  class Element {
    constructor(dataset = {}) { this.dataset = dataset; this.handlers = {}; this.attrs = {}; this.hidden = true; this.innerHTML = ""; this.classes = new Set(); this.classList = { toggle: (name, active) => active ? this.classes.add(name) : this.classes.delete(name), remove: (name) => this.classes.delete(name) }; }
    addEventListener(type, callback) { (this.handlers[type] ||= []).push(callback); }
    emit(type, event = {}) { for (const callback of this.handlers[type] || []) callback(event); }
    setAttribute(name, value) { this.attrs[name] = value; }
    focus() { focused = this; }
    contains(node) { return node === this; }
    closest() { return this; }
    querySelectorAll() { return []; }
  }
  const ids = Object.fromEntries(["interviewPanel", "interviewNav", "studioModeControl", "studioModeTrigger", "studioModeMenu", "studioModeLabel"].map((id) => [id, new Element()]));
  const modes = [new Element({ studioMode: "ielts" }), new Element({ studioMode: "interview" })];
  modes[0].attrs["aria-checked"] = "true";
  const panes = ["home", "bank", "custom", "history"].map((pane) => new Element({ interviewPane: pane }));
  ids.studioModeMenu.querySelectorAll = () => modes;
  ids.studioModeMenu.querySelector = () => modes.find((el) => el.attrs["aria-checked"] === "true");
  const document = new Element();
  document.body = new Element();
  document.getElementById = (id) => ids[id];
  document.querySelectorAll = (selector) => selector.includes("data-studio-mode") ? modes : panes;
  Object.defineProperty(document, "activeElement", { get: () => focused });
  const state = { uiLanguage: "zh", account: { authenticated: true, user: { id: 1 } }, view: "interview", practiceLocked: false };
  const window = new Element();
  window.IELTSNativeBridge = { ready: Promise.resolve({ desktop, mock_interview: desktop, native_audio: false }) };
  const requests = [];
  const store = new Map([["ielts-product-mode", storedMode]]);
  let deferred;
  let followFails = true;
  let coachFails = true;
  const saved = { session: { id: "session-1", title: "C++ 练习", mode: "general", status: "active", created_at: "2026-10-05T00:00:00Z", report: null }, turns: [{ id: "turn-1", order: 1, kind: "main", prompt: "Explain ownership", status: "pending", answer: "", source: "curated" }, { id: "turn-2", order: 2, kind: "main", prompt: "Explain bounded queues", status: "pending", answer: "", source: "curated" }] };
  const details = () => clone({ ...saved, current_turn: saved.session.status === "active" ? saved.turns.find((turn) => turn.status === "pending") || null : null });
  const api = async (url, body, options) => {
    requests.push({ url, body: clone(body || {}), signal: options?.signal });
    if (url.endsWith("questions/")) return { questions: [{ id: "q1", category: "cpp", difficulty: "intermediate", prompt: "Explain ownership" }], categories: [{ id: "cpp", label: "C++" }] };
    if (url === "/api/interview/sessions/" && body === null) {
      if (deferred) return deferred;
      return { sessions: [clone(saved.session)] };
    }
    if (url === "/api/interview/sessions/") return details();
    if (url.endsWith("/answer/")) { const turn = saved.turns.find((item) => url.includes(item.id)); turn.status = "completed"; turn.answer = body.answer; return details(); }
    if (url.endsWith("/skip/")) { saved.turns.find((item) => url.includes(item.id)).status = "skipped"; return details(); }
    if (url.endsWith("/follow-up/")) {
      if (followFails) throw new Error("AI provider unavailable");
      saved.turns.splice(1, 0, { id: "follow-1", order: 2, kind: "follow_up", parent_turn_id: "turn-1", prompt: "What happens on destruction?", status: "pending", answer: "", source: "ai_generated" }); saved.turns[2].order = 3; return details();
    }
    if (url.endsWith("/finish/")) { saved.session.status = "completed"; saved.turns.forEach((turn) => { if (turn.status === "pending") turn.status = "skipped"; }); saved.session.report = { limitations: "text only" }; return details(); }
    if (url.endsWith("/report/")) {
      if (coachFails) { saved.session.report.ai_feedback = { status: "failed", error: "Coaching unavailable" }; throw new Error("Coaching unavailable"); }
      saved.session.report.ai_feedback = { status: "ready", text: "Cite a concrete ownership example." }; return details();
    }
    return details();
  };
  vm.runInNewContext(source, { window, document, localStorage: { getItem: (key) => store.get(key), setItem: (key, value) => store.set(key, value) }, AbortController, FormData, fetch: async () => ({ ok: false, text: async () => '{"error":"No custom question provider"}' }) });
  let loginRequested = false;
  let exited = false;
  const app = window.IELTSInterview.createInterview({ state, api, ensureCsrfToken: async () => "csrf", switchView: (view) => { state.view = view; }, exitPractice: async () => { exited = true; state.practiceLocked = false; }, promptGuestLogin: () => { loginRequested = true; }, currentAiSourcePreference: () => "gpt", escapeHtml: (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;") });
  const action = async (name, extra = {}) => { ids.interviewPanel.emit("click", { target: new Element({ interviewAction: name, ...extra }) }); await settle(); };
  const input = (field, value) => { const target = new Element({ interviewField: field }); target.value = value; ids.interviewPanel.emit("input", { target }); };
  return { app, state, ids, modes, panes, document, window, requests, saved, store, action, input, html: () => ids.interviewPanel.innerHTML, setFollowSuccess: () => { followFails = false; }, setCoachSuccess: () => { coachFails = false; }, setDeferred: (promise) => { deferred = promise; }, loginRequested: () => loginRequested, exited: () => exited, focused: () => focused };
}

test("typed interview saves answers, surfaces follow-up failure, skips, finishes, reloads, and coaches", async () => {
  const env = fixture();
  await env.app.initialize(); env.app.show(); await settle();
  await env.action("start-general");
  assert.match(env.html(), /Explain ownership/);
  env.input("answer", "A unique_ptr owns <script>alert(1)</script>");
  await env.action("answer");
  assert.equal(env.saved.turns[0].status, "completed");
  assert.match(env.html(), /data-interview-action="follow-up"/);
  await env.action("follow-up");
  assert.match(env.html(), /AI provider unavailable/);
  assert.equal(env.saved.turns.length, 2);
  env.setFollowSuccess(); await env.action("follow-up");
  assert.match(env.html(), /What happens on destruction/);
  await env.action("skip");
  await env.action("finish");
  assert.match(env.html(), /&lt;script>/);
  assert.doesNotMatch(env.html(), /<script>alert/);
  await env.action("coach");
  assert.match(env.html(), /Coaching unavailable/);
  assert.match(env.html(), /unique_ptr/);
  await env.action("history");
  await env.action("open-session", { sessionId: "session-1" });
  assert.match(env.html(), /data-interview-action="coach"/);
  env.setCoachSuccess(); await env.action("coach");
  assert.match(env.html(), /Cite a concrete ownership example/);
  assert.doesNotMatch(env.html(), /data-interview-action="coach"/);
  assert.ok(env.requests.every((request) => request.url.endsWith("/")));
  assert.ok(env.requests.every((request) => request.signal));
});

test("resuming a saved active session recovers eligible follow-up, manual custom questions start without AI", async () => {
  const env = fixture(); await env.app.initialize(); env.app.show(); await settle();
  await env.action("start-general"); env.input("answer", "Ownership is explicit"); await env.action("answer");
  env.app.resetForAccount(); await env.action("history"); await env.action("open-session", { sessionId: "session-1" });
  assert.match(env.html(), /data-interview-action="follow-up"/);
  await env.action("custom"); env.input("resume", "Private resume"); env.input("job", "C++ engineer"); await env.action("generate");
  assert.match(env.html(), /No custom question provider/);
  env.input("manualPrompt", "Explain your latency budget"); await env.action("add-custom"); await env.action("start-custom");
  const creation = env.requests.find((request) => request.body.mode === "custom");
  assert.equal(creation.body.questions[0].prompt, "Explain your latency budget");
});

test("account reset cancels in-flight requests and discards private data and late results", async () => {
  const env = fixture(); await env.app.initialize(); env.app.show(); await settle();
  await env.action("custom"); env.input("resume", "Private previous-user resume");
  let resolve; env.setDeferred(new Promise((done) => { resolve = done; }));
  await env.action("history"); const pending = env.requests.at(-1);
  env.state.account.user = { id: 2 }; env.app.resetForAccount();
  assert.equal(pending.signal.aborted, true);
  resolve({ sessions: [{ id: "secret", title: "Previous user's private interview", status: "active" }] }); await settle();
  assert.doesNotMatch(env.html(), /Previous user's private interview|Private previous-user resume/);
  await env.action("custom"); assert.doesNotMatch(env.html(), /Private previous-user resume/);
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
  assert.equal(browser.state.productMode, "ielts"); assert.equal(browser.ids.studioModeControl.classes.has("hidden"), false);
  assert.equal(browser.requests.length, 0);
  const guest = fixture(); guest.state.account.authenticated = false; guest.state.account.user = null;
  await guest.app.initialize(); guest.app.show(); assert.match(guest.html(), /登录并开始/);
  await guest.action("login"); assert.equal(guest.loginRequested(), true); assert.equal(guest.requests.length, 0);
});
