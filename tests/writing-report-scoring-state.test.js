const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

function sliceBetween(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `${startMarker}..${endMarker} slice must exist.`);
  return source.slice(start, end);
}

assert.match(
  app,
  /function\s+writingReportScoringStateHtml\(/,
  "Writing reports should have a dedicated scoring-state surface.",
);

const scoringCardBody = sliceBetween(
  app,
  "function writingReportScoringStateHtml(entry, task) {",
  "function writingReportScoringModelLabel",
);
assert.match(
  scoringCardBody,
  /class="spinner"/,
  "The writing scoring surface should reuse the animated spinner.",
);
assert.doesNotMatch(
  scoringCardBody,
  /data-writing-report-edit=/,
  "The scoring surface must NOT expose an edit action while the score task is active.",
);
assert.doesNotMatch(
  scoringCardBody,
  /继续编辑/,
  "The scoring surface must not offer 继续编辑 while scoring.",
);

assert.match(
  app,
  /if \(isScoringReport\) \{[\s\S]{0,1800}return `[^`]*writingReportScoringStateHtml\(entry, task\)/,
  "Active writing scoring must return one dedicated surface instead of stacking a pending card with the old report or saved draft.",
);

assert.doesNotMatch(
  app,
  /const\s+isScoringReport\s*=\s*isWritingTaskActive\(task\)[\s\S]{0,500}isScoringReport\s*\?\s*"继续编辑"/,
  "An active writing score task must NOT label any report action as 继续编辑.",
);

// setWritingPending no longer takes an options/allowEditing parameter, and it
// must lock the answer field while pending.
const pendingBody = sliceBetween(app, "function setWritingPending(isPending", "function writingTaskLabel");
assert.doesNotMatch(
  pendingBody,
  /allowEditing/,
  "setWritingPending must not distinguish task submission from background scoring.",
);
assert.match(
  pendingBody,
  /if \(isPending\) \{[\s\S]{0,400}lockWritingComposerControls\(\)/,
  "Pending must lock the composer immediately, even before the entry carries an active task.",
);

const lockBody = sliceBetween(app, "function lockWritingComposerControls() {", "function applyWritingScoreLock");
assert.match(
  lockBody,
  /"writingSaveBtn", "writingScoreBtn", "writingRandomBtn", "writingPromptPickerBtn", "writingAnswer"[\s\S]{0,300}disabled = true/,
  "Locking must disable the answer, save, score, random, and picker controls.",
);

assert.match(
  app,
  /setWritingPending\(true,\s*writingTaskStatusTitle\(task\),\s*writingTaskStatusText\(task\)\);/,
  "Background score polling must keep the composer locked (no allowEditing escape hatch).",
);

console.log("Writing report scoring-state checks passed.");
