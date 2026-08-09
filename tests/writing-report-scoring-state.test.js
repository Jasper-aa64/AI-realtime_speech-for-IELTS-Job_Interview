const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

assert.match(
  app,
  /function\s+writingReportScoringStateHtml\(/,
  "Writing reports should have a dedicated scoring-state surface.",
);

assert.match(
  app,
  /function\s+writingReportScoringStateHtml\([^)]*\)\s*\{[\s\S]{0,2400}class="spinner"[\s\S]{0,1200}data-writing-report-edit=/,
  "The writing scoring surface should reuse the animated spinner and keep an edit action available.",
);

assert.match(
  app,
  /const\s+isScoringReport\s*=\s*isWritingTaskActive\(task\)[\s\S]{0,500}isScoringReport\s*\?\s*"继续编辑"/,
  "An active writing score task should label the report action as 继续编辑, even when an older score exists.",
);

assert.match(
  app,
  /if \(isScoringReport\) \{[\s\S]{0,1800}return `[^`]*writingReportScoringStateHtml\(entry, task\)/,
  "Active writing scoring must return one dedicated surface instead of stacking a pending card with the old report or saved draft.",
);

assert.doesNotMatch(
  app,
  /function\s+writingReportScoringStateHtml\([^)]*\)\s*\{[\s\S]{0,3600}data-writing-report-edit=[^>]*\bdisabled\b/,
  "Continue editing must not be disabled while writing scoring is active.",
);

assert.match(
  app,
  /function\s+setWritingPending\([^)]*options\s*=\s*\{\}[\s\S]{0,700}allowEditing[\s\S]{0,700}writingAnswer/,
  "Writing pending state should distinguish task submission from background scoring so the editor can remain usable.",
);

assert.match(
  app,
  /setWritingPending\(true,\s*writingTaskStatusTitle\(task\),\s*writingTaskStatusText\(task\),\s*\{\s*allowEditing:\s*true\s*\}\)/,
  "Background score polling should explicitly keep writing editing enabled.",
);

console.log("Writing report scoring-state checks passed.");
