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
      this.classes = new Set(); this.parentNode = null;
      this.classList = { add: (n) => this.classes.add(n), remove: (n) => this.classes.delete(n), toggle: (n, on) => (on ? this.classes.add(n) : this.classes.delete(n)), contains: (n) => this.classes.has(n) }; }
    set innerHTML(markup) { // build the panel's children from their ids
      for (const [, tag, id] of markup.matchAll(/<(\w+)[^>]*?\sid="(\w+)"/g)) { const child = ids[id] ||= new Element(id); child.tag = tag; this.children.push(child); }
    }
    set className(value) { value.split(/\s+/).filter(Boolean).forEach((n) => this.classes.add(n)); }
    querySelector(selector) { return selector.startsWith("#") ? ids[selector.slice(1)] || null : null; }
    insertBefore(child) { child.parentNode = this; ids[child.id] = child; }
    addEventListener(type, callback) { (this.handlers[type] ||= []).push(callback); }
    emit(type, event = {}) { (this.handlers[type] || []).forEach((callback) => callback(event)); }
  }
  const ids = {};
  const recorderPane = new Element("recorderPane");
  const recordRow = new Element("recordRow");
  recordRow.parentNode = recorderPane;
  ids.recorderPane = recorderPane;
  const document = {
    getElementById: (id) => ids[id] || null,
    createElement: () => new Element(""),
    querySelector: (selector) => (selector === "#recorderPane .record-row" ? recordRow : null),
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
  const state = { productMode: "interview", desktopCapabilities: { native_audio: nativeAudio }, status: "idle", currentTurn: null };
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
  return { controller, voice, state, ids, log, flush, timers };
}

const turn = { id: "t1", part: "interview", question: "介绍一个你做过的项目。" };

test("speak, listen, live partials, final into the answer box, edit and submit through the existing path", async () => {
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

  env.voice.partialTranscript.fire("我负责");
  assert.equal(env.ids.ivVoiceLive.textContent, "我负责");
  env.voice.finalTranscript.fire("我负责交易网关的延迟优化。");
  env.voice.stateChanged.fire("ready", "user_stopped");
  assert.equal(env.state.status, "native_review");
  assert.equal(env.ids.ivVoiceAnswer.value, "我负责交易网关的延迟优化。");
  assert.equal(env.voice.calls.at(-1), "shown:t1");  // timing (2) reported after the text is on the page
  assert.equal(env.ids.ivVoiceSubmit.disabled, false);

  // "继续说" appends a second utterance to what is already in the box
  assert.equal(env.controller.onRecordControl(), true);
  assert.equal(env.state.status, "native_listening");
  env.voice.finalTranscript.fire("延迟降了三成。");
  assert.equal(env.ids.ivVoiceAnswer.value, "我负责交易网关的延迟优化。\n延迟降了三成。");
  env.voice.stateChanged.fire("ready", "user_stopped");

  env.ids.ivVoiceAnswer.value += "（已核对）";
  env.ids.ivVoiceSubmit.emit("click");
  assert.deepEqual(env.log.submitted, ["我负责交易网关的延迟优化。\n延迟降了三成。（已核对）"]);
  assert.equal(env.log.fallbacks.length, 0);
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
});

test("app.js routes interview turns through the voice controller and submits without audio", () => {
  assert.match(html, /<script src="\/interview-voice\.js\?v=[^"]+"><\/script>/);
  assert.match(app, /if \(interviewVoice\?\.handles\(turn\)\)/);
  assert.match(app, /if \(interviewVoice\?\.onRecordControl\(\)\) return;/);
  assert.match(app, /state\.transcriptSource = "desktop_realtime_asr";/);
  assert.match(app, /if \(blob\.size === 0\) return \{\};/);
  assert.match(app, /if \(blob\.size > 0\) await putPendingTurnAudio/);
});
