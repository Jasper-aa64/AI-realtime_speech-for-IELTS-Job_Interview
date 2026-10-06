const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../web/static/interview-corpus.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../web/static/index.html"), "utf8");
const settle = async () => { for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setImmediate(resolve)); };

function harness(corpus) {
  class Element {
    constructor(id) { this.id = id; this.handlers = {}; this.innerHTML = ""; this.textContent = ""; this.value = ""; this.dataset = {}; this.classes = new Set(["hidden"]);
      this.classList = { add: (n) => this.classes.add(n), remove: (n) => this.classes.delete(n), toggle: (n, on) => (on ? this.classes.add(n) : this.classes.delete(n)), contains: (n) => this.classes.has(n) }; }
    addEventListener(type, callback) { (this.handlers[type] ||= []).push(callback); }
    emit(type, event) { (this.handlers[type] || []).forEach((callback) => callback(event)); }
    closest() { return this; }
    focus() {}
  }
  const ids = {};
  const document = { getElementById: (id) => (ids[id] ||= new Element(id)), addEventListener() {}, createElement: () => new Element(""), body: { appendChild() {} } };
  const context = vm.createContext({ window: {}, document, setTimeout: (fn) => fn(), navigator: {} });
  vm.runInContext(source, context);
  const data = { corpus };
  const requests = [];
  const editor = { value: "" };
  const started = [];
  const screens = context.window.IELTSInterviewCorpus.create({
    state: {}, escapeHtml: (v) => String(v), renderMarkdown: (v) => v, currentAiSourcePreference: () => "gpt",
    markdown: { ready: async () => null, get: () => editor.value, set: (_id, v) => { editor.value = v; } },
    request: async (url, body, options = {}) => {
      requests.push({ url, body, method: options.method || (body ? "POST" : "GET") });
      if (options.method === "DELETE") return { deleted: true };
      return { entry: { id: body?.question ? `new_${requests.length}` : url.split("/").at(-2), source: "custom", kind: body?.kind || "knowledge", question: body?.question || "", corpus_text: body?.corpus_text || "", group: body?.group || "", title: body?.title || "", parent_id: body?.parent_id || null } };
    },
    source: () => data, setCorpus: (list) => { data.corpus = list; }, rerender: () => {}, startPractice: (part, preset) => started.push([part, preset]),
  });
  const click = (attrs) => { const target = { dataset: attrs, closest: () => target }; ids.interviewPanel.emit("click", { target, stopPropagation() {} }); };
  return { screens, ids, data, requests, editor, click, started };
}

const corpus = [
  { id: null, kind: "knowledge", group: "低延迟与性能", title: "SPSC 队列与背压", question: "手写 SPSC 队列", source: "curated", source_key: "curated:low_latency-7", corpus_text: "" },
  { id: null, kind: "knowledge", group: "低延迟与性能", title: "硬件基础", question: "缓存延迟多少", source: "curated", source_key: "curated:low_latency-9", corpus_text: "" },
  { id: null, kind: "knowledge", group: "C++ 基础与进阶", title: "智能指针", question: "shared_ptr 成本", source: "curated", source_key: "curated:cpp-2", corpus_text: "" },
  { id: "icp_k", kind: "knowledge", group: "C++", title: "", question: "讲讲内存序", source: "resume", source_key: "resume:tech:a", corpus_text: "我的答法" },
  { id: "icp_gw", kind: "project", title: "撮合网关", question: "介绍撮合网关", source: "resume", source_key: "resume:project:gw", corpus_text: "", order: 0 },
  { id: "icp_f", kind: "project_followup", title: "撮合网关", question: "为什么无锁", source: "resume", parent_id: "icp_gw", corpus_text: "" },
  { id: "icp_i", kind: "self_intro", question: "自我介绍", source: "resume", corpus_text: "" },
  { id: "icp_a", kind: "award", title: "ACM 银牌", question: "讲讲 ACM", source: "resume", corpus_text: "", order: 0 },
  { id: "icp_r", kind: "reverse_question", question: "团队怎么衡量延迟", source: "jd", corpus_text: "" },
];

test("knowledge: a tag filter over directions, and one P1 card per topic inside the tag", () => {
  const env = harness(corpus);
  let page = env.screens.render("knowledge");
  assert.match(page, /p2-cat-filter-bar/);
  assert.match(page, /data-ivc-tag="低延迟与性能"/);
  assert.equal((page.match(/<article class="p1-topic-card /g) || []).length, 4, "SPSC / 硬件基础 / 智能指针 / C++ 综合");
  env.click({ ivcTag: "低延迟与性能" });
  page = env.screens.render("knowledge");
  const titles = [...page.matchAll(/<h3>([^<]+)<\/h3>/g)].map((m) => m[1]);
  assert.deepEqual(titles, ["SPSC 队列与背压", "硬件基础"]);
  assert.match(page, /新题卡/);
});

test("the editor shows AI 参考 only when opened from a report", async () => {
  const env = harness(corpus);
  env.screens.render("knowledge");
  env.screens.openEditor(corpus[0]);
  assert.ok(env.ids.ivCorpusAi.closest().classes.has("hidden") || env.ids.ivCorpusAi.innerHTML === "");
  env.screens.openFromReport({ questionId: "low_latency-7", question: "手写 SPSC 队列", aiAnswer: "**参考**" });
  assert.equal(env.ids.ivCorpusAi.innerHTML, "**参考**");
  env.editor.value = "我的 SPSC 答法";
  env.ids.ivCorpusSave.emit("click");
  await settle();
  assert.deepEqual(JSON.parse(JSON.stringify(env.requests.at(-1).body)), { kind: "knowledge", source_key: "curated:low_latency-7", corpus_text: "我的 SPSC 答法" });
});

test("a report follow-up with no corpus entry becomes a follow-up under its card", async () => {
  const env = harness(corpus);
  env.screens.render("knowledge");
  env.screens.openFromReport({ question: "P99 怎么测", parentEntryId: "icp_gw", aiAnswer: "ref" });
  env.editor.value = "HdrHistogram";
  env.ids.ivCorpusSave.emit("click");
  await settle();
  assert.equal(env.requests.at(-1).body.kind, "project_followup");
  assert.equal(env.requests.at(-1).body.parent_id, "icp_gw");
});

test("resume: P2 cards for intro, projects, stack directions and awards, filterable; follow-ups are unlimited", async () => {
  const env = harness(corpus);
  let page = env.screens.render("resume");
  assert.equal((page.match(/class="p2-seasonal-card /g) || []).length, 4);
  assert.match(page, /data-p2-bank-card-category="object"/);
  env.click({ ivcFilter: "project" });
  page = env.screens.render("resume");
  assert.equal((page.match(/class="p2-seasonal-card /g) || []).length, 1);
  env.click({ ivcFollow: "icp_gw" });
  assert.match(env.ids.ivFollowList.innerHTML, /为什么无锁/);
  assert.match(env.ids.ivFollowList.innerHTML, /写一个新追问/);
  env.ids.ivFollowList.emit("click", { target: { closest: () => ({ dataset: { ivcFollowSelect: "new" } }) } });
  await settle();
  env.ids.ivFollowQuestion.value = "P99 怎么测？";
  env.editor.value = "用直方图";
  env.ids.ivFollowSave.emit("click");
  await settle();
  assert.deepEqual(JSON.parse(JSON.stringify(env.requests.at(-1).body)), { kind: "project_followup", parent_id: "icp_gw", question: "P99 怎么测？", corpus_text: "用直方图" });
  env.click({ ivcPractice: "icp_gw" });
  assert.deepEqual(JSON.parse(JSON.stringify(env.started.at(-1))), ["project", { projectIds: ["icp_gw"] }]);
});

test("the dialogs are static copies of the IELTS P1 and P2-P3 dialogs, with the Markdown editor textareas", () => {
  assert.match(html, /<textarea id="ivCorpusText" class="p1-corpus-textarea"/);
  assert.match(html, /<textarea id="ivFollowText" class="p1-corpus-textarea p2-p3-follow-up"/);
  assert.match(html, /id="ivCorpusDialog" class="p1-corpus-dialog/);
  assert.match(html, /p1-corpus-ai-box hidden/);
});
