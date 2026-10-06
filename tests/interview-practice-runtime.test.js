const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const app = fs.readFileSync(path.join(__dirname, "../web/static/app.js"), "utf8");

test("interview practice views are IELTS practice views named after the attempt modes", () => {
  assert.match(app, /INTERVIEW_PRACTICE_VIEWS = new Set\(\["iv_full", "iv_project", "iv_knowledge", "iv_reverse"\]\)/);
  assert.match(app, /PRACTICE_VIEWS = new Set\(\["mock", "p1", "p2", "p3", \.\.\.INTERVIEW_PRACTICE_VIEWS\]\)/);
  // startPractice sends mode = state.view, so the view name is the attempt mode.
  assert.match(app, /const mode = state\.view === "mock" \? "mock" : state\.view;/);
});

test("the P1 standard / pressure switch drives the interviewer and is shown in interview views", () => {
  assert.match(app, /iv_intensity: state\.p1Intensity === "high" \? "pressure" : "standard"/);
  assert.match(app, /const isP1 = state\.view === "p1" \|\| isInterviewView\(state\.view\);/);
});

test("interview turns are labelled by stage and read in Chinese by the browser fallback", () => {
  assert.match(app, /if \(turn\.part === "interview"\) \{/);
  assert.match(app, /turn\.prompt\?\.role === "follow_up" \? `\$\{stage\} -> 追问`/);
  assert.match(app, /if \(turn\.prompt\?\.language === "zh"\) utterance\.lang = "zh-CN";/);
});

test("interview views keep interview mode; IELTS-only views switch back", () => {
  assert.match(app, /if \(view === "interview" \|\| isInterviewView\(view\)\) interview\?\.setProductMode\("interview"\);/);
});
