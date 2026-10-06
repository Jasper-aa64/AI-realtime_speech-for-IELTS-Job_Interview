const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../web/static/interview-corpus.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../web/static/index.html"), "utf8");
const settle = async () => { for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setImmediate(resolve)); };

function harness(corpus, { fail = false } = {}) {
  class Element {
    constructor(id) { this.id = id; this.handlers = {}; this.innerHTML = ""; this.textContent = ""; this.value = ""; this.dataset = {}; this.classes = new Set(["hidden"]);
      this.classList = { add: (n) => this.classes.add(n), remove: (n) => this.classes.delete(n), toggle: (n, on) => (on ? this.classes.add(n) : this.classes.delete(n)), contains: (n) => this.classes.has(n) }; }
    addEventListener(type, callback) { (this.handlers[type] ||= []).push(callback); }
    emit(type, event) { (this.handlers[type] || []).forEach((callback) => callback(event)); }
    closest() { return this; }
    focus() {}
  }
  const ids = {};
  const appended = [];
  const document = { getElementById: (id) => (ids[id] ||= new Element(id)), addEventListener() {}, querySelectorAll: () => [], createElement: () => new Element(""), body: { appendChild: (el) => appended.push(el) } };
  const context = vm.createContext({ window: {}, document, setTimeout: (fn) => fn(), navigator: {} });
  vm.runInContext(source, context);
  const data = { corpus };
  const requests = [];
  const editor = { value: "" };
  const started = [];
  const popups = [];
  const screens = context.window.IELTSInterviewCorpus.create({
    state: {}, escapeHtml: (v) => String(v), renderMarkdown: (v) => v, currentAiSourcePreference: () => "gpt",
    markdown: { ready: async () => null, get: () => editor.value, set: (_id, v) => { editor.value = v; } },
    popup: (message) => popups.push(message),
    request: async (url, body, options = {}) => {
      requests.push({ url, body, method: options.method || (body ? "POST" : "GET") });
      if (fail) throw new Error("AI 服务还没有配置");
      if (options.method === "DELETE") return { deleted: true };
      return { entry: { id: body?.question ? `new_${requests.length}` : url.split("/").at(-2), source: "custom", kind: body?.kind || "knowledge", question: body?.question || "", corpus_text: body?.corpus_text || "", group: body?.group || "", title: body?.title || "", parent_id: body?.parent_id || null } };
    },
    source: () => data, setCorpus: (list) => { data.corpus = list; }, rerender: () => {}, startPractice: (part, preset) => started.push([part, preset]),
  });
  // closest() matches a selector only when it names one of the clicked element's data attributes.
  const camel = (name) => name.replace(/-(\w)/g, (_m, c) => c.toUpperCase());
  const click = (attrs) => {
    const target = { dataset: attrs, closest: (selector) => (selector.split(",").some((part) => { const m = part.match(/\[data-([\w-]+)\]/); return m && camel(m[1]) in attrs; }) ? target : null) };
    ids.interviewPanel.emit("click", { target, stopPropagation() {} });
  };
  return { screens, ids, data, requests, editor, click, started, popups };
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
  assert.equal((page.match(/<article class="p1-topic-card /g) || []).length, 5, "自我介绍 / SPSC / 硬件基础 / 智能指针 / C++ 综合");
  assert.equal([...page.matchAll(/<h3>([^<]+)<\/h3>/g)][0][1], "自我介绍", "the intro is pinned first");
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

test("resume: P2 cards for projects and awards (no stack, no intro), filterable; follow-ups are unlimited", async () => {
  const env = harness(corpus);
  let page = env.screens.render("resume");
  assert.equal((page.match(/class="p2-seasonal-card /g) || []).length, 2);
  assert.doesNotMatch(page, /data-ivc-section="stack"|data-ivc-filter="(stack|intro)"|<h3>技术栈/);
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

test("resume: the P2 category grid lists every kind with a 新增 row, so an empty resume can be filled by hand", async () => {
  const env = harness([]);
  env.data.categories = [{ id: "cpp", label: "C++ 基础与进阶" }];
  const page = env.screens.render("resume");
  for (const label of ["项目", "实习", "获奖", "JD 与反问"]) assert.match(page, new RegExp(`新增${label}`));
  assert.doesNotMatch(page, /新增自我介绍|新增技术栈/);
  assert.match(page, /从简历生成/);
  env.click({ ivcCreate: "intern" });
  assert.equal(env.ids.ivCardDialog.classes.has("hidden"), false, "the card dialog opens");
  env.ids.ivCardName.value = "某券商交易组";
  env.editor.value = "我在交易组做行情接入";
  env.ids.ivCardSave.emit("click");
  await settle();
  const created = JSON.parse(JSON.stringify(env.requests.at(-1).body));
  assert.deepEqual([created.kind, created.group, created.title, created.question], ["project", "实习", "某券商交易组", "介绍一下你在「某券商交易组」的实习。"]);
  const after = env.screens.render("resume");
  assert.match(after, /data-p2-bank-card-category="person"/, "the internship card wears the P2 person colours");
});

test("knowledge: 自我介绍 is a pinned card whose ＋ writes another version of the intro", async () => {
  const env = harness([{ id: "icp_i", kind: "self_intro", title: "自我介绍", question: "1 分钟中文自我介绍", source: "resume", corpus_text: "我是……" }]);
  let page = env.screens.render("knowledge");
  assert.match(page, /data-ivc-tag="自我介绍"/);
  assert.match(page, /1 分钟中文自我介绍/);
  env.click({ ivcTag: "自我介绍" });
  page = env.screens.render("knowledge");
  assert.doesNotMatch(page, /新题卡/, "the intro has its own ＋ instead of new topic cards");
  env.click({ ivcNew: "k:intro" });
  env.ids.ivCorpusQuestion.value = "3 分钟英文自我介绍";
  env.editor.value = "I am …";
  env.ids.ivCorpusSave.emit("click");
  await settle();
  const created = JSON.parse(JSON.stringify(env.requests.at(-1).body));
  assert.deepEqual([created.kind, created.title, created.question], ["self_intro", "自我介绍", "3 分钟英文自我介绍"]);
  const empty = harness([]).screens.render("knowledge");
  assert.match(empty, /还没有自我介绍/);
});

test("request failures in the corpus dialogs go to a pop-up, not an inline bar", async () => {
  const env = harness(corpus, { fail: true });
  env.screens.render("knowledge");
  env.screens.openEditor(corpus[3]);
  env.editor.value = "新答法";
  env.ids.ivCorpusSave.emit("click");
  await settle();
  assert.deepEqual([...env.popups], ["AI 服务还没有配置"]);
  assert.equal(env.ids.ivCorpusDialogStatus.textContent, "");
});

test("resume cards are 简述 (the card title) + 简历原文 + STAR 正文, edited in the P2-style card dialog", async () => {
  const env = harness([{ id: "icp_gw", kind: "project", title: "撮合网关重构", question: "介绍一下你的「撮合网关重构」项目。", source: "resume",
    resume_excerpt: "- 主导网关重构\n- P99 900µs→55µs", corpus_text: "", order: 0 }]);
  const page = env.screens.render("resume");
  const escaped = harness([{ id: "icp_x", kind: "project", title: "x", question: "q", source: "custom", resume_excerpt: "用 LD\\_PRELOAD", corpus_text: "", order: 0 }]);
  assert.match(escaped.screens.render("resume"), /用 LD_PRELOAD/, "editor escapes are undone");
  assert.match(page, /<h3>撮合网关重构<\/h3>/);
  assert.doesNotMatch(page, /iv-card-summary/);
  assert.match(page, /iv-card-excerpt">- 主导网关重构/, "the excerpt goes through the Markdown renderer");
  assert.match(page, /STAR 待填/);
  env.click({ ivcBody: "icp_gw" });
  assert.equal(env.ids.ivCardName.value, "撮合网关重构");
  assert.equal(env.ids.ivCardTextLabel.textContent, "STAR 正文");
  env.ids.ivCardStar.emit("click");
  assert.match(env.editor.value, /\*\*S 情境\*\*/);
  env.ids.ivCardName.value = "撮合网关重构（P99 55µs）";
  env.ids.ivCardSave.emit("click");
  await settle();
  const body = JSON.parse(JSON.stringify(env.requests.at(-1).body));
  assert.equal(body.title, "撮合网关重构（P99 55µs）");
  assert.equal(body.question, "介绍一下你的「撮合网关重构（P99 55µs）」项目。");
  assert.equal(body.summary, undefined);
  assert.match(body.corpus_text, /R 结果/);
  env.click({ ivcCreate: "award" });
  env.ids.ivCardName.value = "ACM-ICPC 区域赛银奖";
  env.editor.value = "";
  env.ids.ivCardSave.emit("click");
  await settle();
  assert.deepEqual(JSON.parse(JSON.stringify(env.requests.at(-1).body)), {
    kind: "award", title: "ACM-ICPC 区域赛银奖", question: "讲讲你的「ACM-ICPC 区域赛银奖」经历。", resume_excerpt: "", corpus_text: "",
  });
});

test("a new card with nothing typed closes on a click outside, without asking for a name", () => {
  const env = harness([]);
  env.screens.render("resume");
  env.click({ ivcCreate: "project" });
  env.editor.value = "";
  env.ids.ivCardDialog.emit("pointerdown", { target: env.ids.ivCardDialog, preventDefault() {} });
  assert.equal(env.ids.ivCardDialog.classes.has("hidden"), true);
  assert.equal(env.requests.length, 0);
});
