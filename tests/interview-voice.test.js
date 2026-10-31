const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../web/static/interview-voice.js"), "utf8");
const app = fs.readFileSync(path.join(__dirname, "../web/static/app.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../web/static/index.html"), "utf8");

// A QWebChannel-like studioVoice: signals have connect(); methods record calls.
function fakeVoice() {
  const signal = () => { const handlers = []; return { connect: (fn) => handlers.push(fn), fire: (...args) => handlers.forEach((fn) => fn(...args)) }; };
  const calls = [];
  return {
    calls,
    stateChanged: signal(), partialTranscript: signal(), finalTranscript: signal(), error: signal(),
    startSession() { calls.push("startSession"); return true; },
    speak(text) { calls.push(`speak:${text}`); },
    startListening() { calls.push("startListening"); },
    stopListening() { calls.push("stopListening"); },
    endSession() { calls.push("endSession"); },
    markTranscriptShown(note) { calls.push(`shown:${note}`); },
  };
}

function harness({ voice = fakeVoice(), nativeAudio = true } = {}) {
  class Element {
    constructor(id) { this.id = id; this.handlers = {}; this.textContent = ""; this.value = ""; this.disabled = false; this.children = [];
      this.classes = new Set(); this.parentNode = null; this.attrs = {}; this.scrollTop = 0; this.scrollHeight = 0;
      this.classList = { add: (n) => this.classes.add(n), remove: (n) => this.classes.delete(n), toggle: (n, on) => (on ? this.classes.add(n) : this.classes.delete(n)), contains: (n) => this.classes.has(n) }; }
    set innerHTML(markup) { // build the panel's children from their ids
      for (const [, tag, id] of markup.matchAll(/<(\w+)[^>]*?\sid="(\w+)"/g)) { const child = ids[id] ||= new Element(id); child.tag = tag; this.children.push(child); }
    }
    set className(value) { value.split(/\s+/).filter(Boolean).forEach((n) => this.classes.add(n)); }
    querySelector(selector) { return selector.startsWith("#") ? ids[selector.slice(1)] || null : null; }
    setAttribute(name, value) { this.attrs[name] = value; }
    insertBefore(child) { child.parentNode = this; ids[child.id] = child; }
    appendChild(child) { child.parentNode = this; ids[child.id] = child; }
    addEventListener(type, callback) { (this.handlers[type] ||= []).push(callback); }
    emit(type, event = {}) { (this.handlers[type] || []).forEach((callback) => callback(event)); }
  }
  const ids = {};
  const recorderPane = new Element("recorderPane");
  const statusZone = new Element("statusZone");
  statusZone.parentNode = recorderPane;
  ids.recorderPane = recorderPane;
  ids.statusZone = statusZone;
  const document = {
    getElementById: (id) => ids[id] || null,
    createElement: () => new Element(""),
    querySelector: (selector) => (selector === "#recorderPane .recorder-status-zone" ? statusZone : null),
  };
  const timers = [];
  const window = {
    IELTSNativeBridge: { voice: Promise.resolve(voice) },
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: () => {},
    requestAnimationFrame: (fn) => fn(),
  };
  const context = vm.createContext({ window, document });
  vm.runInContext(source, context);
  const state = { productMode: "interview", p1Intensity: "high", desktopCapabilities: { native_audio: nativeAudio }, status: "idle", currentTurn: null };
  const log = { submitted: [], fallbacks: [], status: [] };
  const controller = context.window.IELTSInterviewVoice.create({
    state,
    text: (id, value) => log.status.push([id, value]),
    setRecordButton: (status) => { state.status = status; },
    isActive: () => true,
    submit: (answer) => log.submitted.push(answer),
    fallback: (sessionId, reason) => log.fallbacks.push(reason),
  });
  const flush = () => new Promise((resolve) => setImmediate(resolve));
  // run the newest pending timer armed for `ms`
  const fire = (ms) => { const t = timers.filter((x) => x.ms === ms).at(-1); assert.ok(t, `a ${ms} ms timer is armed`); t.fn(); };
  return { controller, voice, state, ids, log, flush, timers, fire };
}

const turn = { id: "t1", part: "interview", question: "介绍一个你做过的项目。" };

async function listening(env) {
  await env.flush();
  env.state.currentTurn = turn;
  const running = env.controller.runTurn(1, turn);
  env.voice.stateChanged.fire("ready", "");
  await env.flush();
  env.voice.stateChanged.fire("ready", "speak_finished");
  await running;
}

test("speak, listen, live transcript, then the final transcript is submitted through the existing path", async () => {
  const env = harness();
  await env.flush();
  env.state.currentTurn = turn;
  assert.equal(env.controller.handles(turn), true);
  const running = env.controller.runTurn(1, turn);
  assert.equal(env.state.status, "native_speaking");
  assert.deepEqual(env.voice.calls, ["startSession"]);
  env.voice.stateChanged.fire("ready", "");
  await env.flush();
  assert.deepEqual(env.voice.calls, ["startSession", "speak:介绍一个你做过的项目。"]);
  env.voice.stateChanged.fire("ready", "speak_finished");
  await running;
  assert.equal(env.state.status, "native_listening");
  assert.equal(env.voice.calls.at(-1), "startListening");
  // the transcript sits in the status zone under the status line, not between the record button and the status
  assert.equal(env.ids.ivVoicePanel.parentNode, env.ids.statusZone);

  env.voice.partialTranscript.fire("我负责");
  assert.equal(env.ids.ivVoiceLive.textContent, "我负责");
  env.voice.finalTranscript.fire("我负责交易网关的延迟优化。");
  assert.equal(env.ids.ivVoiceAnswer.textContent, "我负责交易网关的延迟优化。");
  assert.equal(env.ids.ivVoiceLive.textContent, "");
  assert.equal(env.voice.calls.at(-1), "shown:t1");  // timing (2) reported after the text is on the page
  env.voice.stateChanged.fire("ready", "user_stopped");
  assert.equal(env.state.status, "native_review");
  assert.equal(env.log.submitted.length, 0);         // it stays on the page for a moment first
  env.fire(600);
  assert.deepEqual(env.log.submitted, ["我负责交易网关的延迟优化。"]);
  assert.equal(env.log.fallbacks.length, 0);
});

test("pressing 说完了 before the final transcript arrives submits it once it lands", async () => {
  const env = harness();
  await listening(env);
  env.voice.partialTranscript.fire("延迟降了");
  assert.equal(env.controller.onRecordControl(), true);
  assert.equal(env.voice.calls.at(-1), "stopListening");
  assert.equal(env.state.status, "native_review");
  env.voice.finalTranscript.fire("延迟降了三成。");
  env.fire(600);
  assert.deepEqual(env.log.submitted, ["延迟降了三成。"]);
});

test("no speech at all: nothing is submitted and the record button listens again", async () => {
  const env = harness();
  await listening(env);
  env.fire(20000);                      // silence timeout
  assert.equal(env.voice.calls.at(-1), "stopListening");
  env.fire(4000);                       // no final transcript either
  assert.equal(env.log.submitted.length, 0);
  assert.equal(env.controller.onRecordControl(), true);
  assert.equal(env.state.status, "native_listening");
  assert.equal(env.voice.calls.at(-1), "startListening");
});

test("a disconnect while listening falls back to recording and that turn stays on recording", async () => {
  const env = harness();
  await env.flush();
  env.state.currentTurn = turn;
  const running = env.controller.runTurn(1, turn);
  env.voice.stateChanged.fire("ready", "");
  await env.flush();
  env.voice.stateChanged.fire("ready", "speak_finished");
  await running;
  env.voice.error.fire("disconnected", "realtime connection closed");
  assert.equal(env.log.fallbacks.length, 1);
  assert.match(env.log.fallbacks[0], /disconnected/);
  assert.equal(env.state.status, "idle");
  assert.equal(env.controller.handles(turn), false);
  // The next question tries realtime voice again.
  assert.equal(env.controller.handles({ ...turn, id: "t2" }), true);
});

test("a session that never becomes ready times out into the recording fallback instead of spinning", async () => {
  const env = harness();
  await env.flush();
  env.state.currentTurn = turn;
  const running = env.controller.runTurn(1, turn);
  const start = env.timers.find((t) => t.ms === 15000);
  assert.ok(start, "a start timeout is armed");
  start.fn();
  await running;
  assert.equal(env.log.fallbacks.length, 1);
  assert.match(env.log.fallbacks[0], /timeout/);
});

test("ordinary browsers (no voice object) and IELTS turns never use realtime voice", async () => {
  const browser = harness({ voice: null });
  await browser.flush();
  assert.equal(browser.controller.handles(turn), false);
  const off = harness({ nativeAudio: false });
  await off.flush();
  assert.equal(off.controller.handles(turn), false);
  const ielts = harness();
  await ielts.flush();
  assert.equal(ielts.controller.handles({ id: "p1", part: "p1", question: "Do you like music?" }), false);
  // 追问压力 is the realtime-voice mode; 标准 keeps recording
  const standard = harness();
  await standard.flush();
  standard.state.p1Intensity = "normal";
  assert.equal(standard.controller.handles(turn), false);
});

test("app.js routes interview turns through the voice controller and submits without audio", () => {
  assert.match(html, /<script src="\/interview-voice\.js\?v=[^"]+"><\/script>/);
  assert.match(app, /if \(interviewVoice\?\.handles\(turn\)\)/);
  assert.match(app, /if \(interviewVoice\?\.onRecordControl\(\)\) return;/);
  assert.match(app, /state\.transcriptSource = "desktop_realtime_asr";/);
  assert.match(app, /if \(blob\.size === 0\) return \{\};/);
  assert.match(app, /if \(blob\.size > 0\) await putPendingTurnAudio/);
});
