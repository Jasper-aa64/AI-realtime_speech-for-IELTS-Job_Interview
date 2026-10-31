const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const app = fs.readFileSync(path.join(__dirname, "../web/static/app.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../web/static/index.html"), "utf8");

function extract(name) {
  const start = app.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `${name} exists`);
  let depth = 0;
  // Body starts at ") {", so a default argument like `provenance = {}` is not mistaken for it.
  for (let i = app.indexOf(") {", start) + 2; i < app.length; i += 1) {
    if (app[i] === "{") depth += 1;
    if (app[i] === "}" && --depth === 0) return app.slice(start, i + 1);
  }
  throw new Error(`unterminated ${name}`);
}

test("the interview report is the IELTS summary card with a 100-point score and five dimensions", () => {
  const context = vm.createContext({
    escapeHtml: (value) => String(value),
    reportTurnAnswerIsEmpty: (turn) => !turn.transcript,
    scoreCell: (label, score, note) => `<div class="score-cell"><span>${label}</span><strong>${score}</strong><small>${note}</small></div>`,
    viewTitleFor: () => "完整面试",
    overallReviewSection: () => '<div class="overall-review"></div>',
    turnTableSection: (attempt) => `<table><th>${attempt.interview_score ? "参考回答" : "7分回答参考"}</th></table>`,
  });
  for (const name of ["scoringModelDisplayName", "reportScoringModelLabel", "reportScoringModelMetaHtml", "renderInterviewDetail"]) {
    vm.runInContext(extract(name), context);
  }
  const panel = { innerHTML: "" };
  const dims = [["技术深度", 22, 30], ["项目表达", 18, 25], ["问题拆解", 15, 20], ["沟通", 11, 15], ["岗位匹配", 7, 10]];
  context.renderInterviewDetail(panel, {
    mode: "iv_full", title: "完整面试",
    interview_score: { total: 73, dimensions: dims.map(([label, score, max]) => ({ label, score, max })),
      scoring_provider: "http_api", scoring_model: "claude-sonnet-4-6" },
    turns: [{ transcript: "我做过撮合网关" }, { transcript: "" }],
  });
  assert.match(panel.innerHTML, /73 \/ 100/);
  assert.equal((panel.innerHTML.match(/class="score-cell"/g) || []).length, 5);
  assert.match(panel.innerHTML, /参考回答/);
  assert.match(panel.innerHTML, /1 题已答/);
  assert.doesNotMatch(panel.innerHTML, /Band/);
  // The foot of the report names the model that generated the score, not the old disclaimer.
  assert.match(panel.innerHTML, /<span>评分模型<\/span><strong>Claude Sonnet 4\.6<\/strong>/);
  assert.doesNotMatch(panel.innerHTML, /不评估发音/);
});

test("interview mode lists only interview attempts and filters by interview part", () => {
  assert.match(app, /state\.productMode === "interview" \? "\/api\/history\?domain=interview" : "\/api\/history"/);
  for (const [mode, label] of [["iv_full", "完整面试"], ["iv_project", "项目深挖"], ["iv_knowledge", "知识点"], ["iv_reverse", "反问环节"]]) {
    assert.match(html, new RegExp(`data-speaking-report-filter="${mode}"`));
    assert.match(app, new RegExp(`${mode}: "${label}"`));
  }
});
