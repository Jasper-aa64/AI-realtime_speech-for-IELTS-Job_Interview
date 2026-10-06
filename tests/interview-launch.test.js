const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../web/static/interview-launch.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../web/static/index.html"), "utf8");
const app = fs.readFileSync(path.join(__dirname, "../web/static/app.js"), "utf8");

function harness({ corpus = [], profile = { resume: {}, jd: {} }, categories = [{ id: "cpp", label: "C++ 基础与进阶" }] } = {}) {
  class Element {
    constructor(id) { this.id = id; this.handlers = {}; this.innerHTML = ""; this.textContent = ""; this.value = ""; this.classes = new Set(["hidden"]);
      this.classList = { add: (n) => this.classes.add(n), remove: (n) => this.classes.delete(n), toggle: (n, on) => (on ? this.classes.add(n) : this.classes.delete(n)), contains: (n) => this.classes.has(n) }; }
    addEventListener(type, callback) { (this.handlers[type] ||= []).push(callback); }
    emit(type, event) { (this.handlers[type] || []).forEach((callback) => callback(event)); }
    closest() { return null; }
    focus() {}
  }
  const ids = {};
  const document = { getElementById: (id) => (ids[id] ||= new Element(id)), addEventListener() {} };
  const store = new Map();
  const editor = { value: "" };
  const context = vm.createContext({ window: {}, document, setTimeout: (fn) => fn(), FormData: class { append() {} },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) } });
  vm.runInContext(source, context);
  const state = { view: "iv_knowledge", account: { authenticated: true, user: { id: 7 } }, practiceLocked: false };
  const data = { corpus, profile, categories };
  const launch = context.window.IELTSInterviewLaunch.create({
    state, escapeHtml: (v) => String(v), currentAiSourcePreference: () => "gpt", renderMarkdown: (v) => v,
    markdown: { ready: async () => null, get: () => editor.value, set: (_id, v) => { editor.value = v; } },
    upload: async () => ({}), source: () => data, onProfile: () => {},
  });
  // Clicks on launch tiles / picker rows: the delegated handlers read data-* from the closest match.
  const click = (hostId, attrs) => {
    const target = { dataset: attrs, closest: () => target };
    ids[hostId].emit("click", { target });
  };
  return { launch, state, ids, store, editor, click, plainQuestion: context.window.IELTSInterviewLaunch.plainQuestion };
}

const curated = (n) => ({ id: null, kind: "knowledge", group: "C++ 基础与进阶", question: `题${n}`, source: "curated", source_key: `curated:cpp-${n}` });

test("questions written in the Markdown editor are read aloud without Markdown marks", () => {
  const { plainQuestion } = harness();
  assert.equal(plainQuestion("## **epoll** 和 `select` 的区别？"), "epoll 和 select 的区别？");
  assert.equal(plainQuestion("- 第一行\n- 第二行"), "第一行 第二行");
  assert.equal(plainQuestion("[链接](http://x) 是什么"), "链接 是什么");
});

test("knowledge: picked bank questions, a session question and the count become the start payload", () => {
  const env = harness({ corpus: [curated(1), curated(2), { id: "icp_1", kind: "knowledge", group: "C++", question: "内存序", source: "resume" }] });
  env.launch.render("iv_knowledge");
  assert.match(env.ids.ivLaunch.innerHTML, /C\+\+ 基础与进阶/);
  assert.deepEqual(JSON.parse(JSON.stringify(env.launch.options("iv_knowledge"))), { count: 5 });
  env.click("ivLaunch", { ivLaunch: "pick-group", group: "C++ 基础与进阶" });
  env.click("ivPickDialog", { ivPick: "entry", key: "q:cpp-2" });
  env.click("ivPickDialog", { ivPick: "add" });
  env.editor.value = "**epoll** 和 select？";
  env.ids.ivLaunchDialogSave.emit("click", {});
  env.click("ivPickDialog", { ivPick: "done" });
  env.click("ivLaunch", { ivLaunch: "pick-group", group: "C++" });
  env.click("ivPickDialog", { ivPick: "entry", key: "e:icp_1" });
  env.click("ivPickDialog", { ivPick: "done" });
  env.click("ivLaunch", { ivLaunch: "count", count: "3" });
  assert.deepEqual(JSON.parse(JSON.stringify(env.launch.options("iv_knowledge"))), {
    count: 3, entry_ids: ["icp_1"], question_ids: ["cpp-2"], custom_questions: ["epoll 和 select？"], categories: ["cpp"],
  });
  assert.match(env.ids.ivLaunch.innerHTML, /已选 3 题/);
});

test("project: a written description, or picked corpus projects", () => {
  const project = { id: "icp_gw", kind: "project", title: "撮合网关", question: "介绍撮合网关" };
  const env = harness({ corpus: [project] });
  env.launch.render("iv_project");
  assert.deepEqual(JSON.parse(JSON.stringify(env.launch.options("iv_project"))), {}, "nothing picked: every corpus project");
  env.click("ivLaunch", { ivLaunch: "project-pick", id: "icp_gw" });
  assert.deepEqual(JSON.parse(JSON.stringify(env.launch.options("iv_project"))), { project_ids: ["icp_gw"] });
  env.click("ivLaunch", { ivLaunch: "project-source", source: "text" });
  env.click("ivLaunch", { ivLaunch: "project-text" });
  env.editor.value = "## 行情回放\n- 回放 10 倍速";
  env.ids.ivLaunchDialogSave.emit("click", {});
  assert.deepEqual(JSON.parse(JSON.stringify(env.launch.options("iv_project"))), { project_text: "## 行情回放\n- 回放 10 倍速" });
});

test("project without corpus projects defaults to writing a description", () => {
  const env = harness();
  env.launch.render("iv_project");
  assert.match(env.ids.ivLaunch.innerHTML, /写项目描述/);
  assert.match(env.ids.ivLaunch.innerHTML, /上传简历|写一段项目描述/);
});

test("reverse: this session's JD and at most three planned questions; full interview sends the JD too", () => {
  const env = harness({ profile: { resume: {}, jd: { text: "旧 JD" } } });
  env.launch.render("iv_reverse");
  assert.deepEqual(JSON.parse(JSON.stringify(env.launch.options("iv_full"))), { jd_text: "旧 JD" }, "the saved JD is the default");
  env.click("ivLaunch", { ivLaunch: "jd" });
  env.editor.value = "低延迟 C++";
  env.ids.ivLaunchDialogSave.emit("click", {});
  for (const question of ["问一", "问二", "问三", "问四"]) {
    env.click("ivLaunch", { ivLaunch: "reverse-add" });
    env.editor.value = question;
    env.ids.ivLaunchDialogSave.emit("click", {});
  }
  assert.deepEqual(JSON.parse(JSON.stringify(env.launch.options("iv_reverse"))), { jd_text: "低延迟 C++", reverse_questions: ["问一", "问二", "问三"] });
  env.click("ivLaunch", { ivLaunch: "reverse-remove", index: "1" });
  assert.deepEqual(JSON.parse(JSON.stringify(env.launch.options("iv_reverse"))).reverse_questions, ["问一", "问三"]);
});

test("the setup is kept per account and dropped on account change", () => {
  const env = harness();
  env.launch.render("iv_reverse");
  env.click("ivLaunch", { ivLaunch: "reverse-add" });
  env.editor.value = "问一";
  env.ids.ivLaunchDialogSave.emit("click", {});
  assert.match(env.store.get("ielts-iv-launch:7"), /问一/);
  env.state.account.user = { id: 8 };
  env.launch.reset();
  assert.equal(env.launch.options("iv_reverse").reverse_questions, undefined);
  env.state.account.user = { id: 7 };
  env.launch.reset();
  assert.deepEqual(JSON.parse(JSON.stringify(env.launch.options("iv_reverse"))).reverse_questions, ["问一"]);
});

test("the launch block lives in the PROMPT pane under the idle line and uses the IELTS editor dialog", () => {
  assert.match(html, /Start a voice practice session to load a question\.<\/div>\s*<div id="ivLaunch"/);
  assert.match(html, /<textarea id="ivLaunchText" class="p1-corpus-textarea"/);
  assert.match(app, /markdown: \{ ready: ensureCorpusMarkdownEditorReady, get: getCorpusMarkdownValue, set: setCorpusMarkdownValue \}/);
  assert.equal((app.match(/interview\?\.renderLaunch\?\.\(state\.view\);/g) || []).length, 2);
});
