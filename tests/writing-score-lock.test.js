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

// No "edit while scoring" escape hatch anywhere.
assert.doesNotMatch(app, /allowEditing/, "No allowEditing option may remain.");

// The polling loop must lock unconditionally (no options arg, no editing).
assert.match(
  app,
  /setWritingPending\(true, writingTaskStatusTitle\(task\), writingTaskStatusText\(task\)\);/,
  "Polling must lock the composer without any allow-editing escape hatch.",
);

// The lock's single source of truth is the entry's active ai_task.
assert.match(
  app,
  /function writingEntryHasActiveScoreTask\(entry = state\.writing\.entry\) \{[\s\S]{0,200}isWritingTaskActive\(entry\.ai_task\)/,
  "The lock predicate must derive from the entry's active ai_task.",
);
assert.match(
  app,
  /function applyWritingScoreLock\(\) \{[\s\S]{0,600}const locked = writingEntryHasActiveScoreTask\(\)/,
  "applyWritingScoreLock must derive from writingEntryHasActiveScoreTask.",
);

// Every surface render re-applies the lock (refresh/recovery/poll data can't
// transiently unlock the composer).
const surfaceBody = sliceBetween(app, "function renderWritingSurface() {", "function currentWritingPromptImageUrl");
assert.match(
  surfaceBody,
  /applyWritingScoreLock\(\);/,
  "renderWritingSurface must re-apply the score lock on every render.",
);

// setWritingPending(true) locks immediately even before the entry carries a task.
const pendingBody = sliceBetween(app, "function setWritingPending(isPending", "function writingTaskLabel");
assert.match(
  pendingBody,
  /if \(isPending\) \{[\s\S]{0,400}lockWritingComposerControls\(\)/,
  "setWritingPending(true) must lock all controls immediately.",
);
assert.match(
  pendingBody,
  /applyWritingScoreLock\(\);/,
  "setWritingPending(false) must defer to the ai_task-derived lock.",
);

// Queued or scheduled autosave must never fire while the entry has an active task.
const autosaveGuardCount = (app.match(/if \(writingEntryHasActiveScoreTask\(\)\) return;/g) || []).length;
assert.ok(autosaveGuardCount >= 2, "Both schedule and run autosave paths must guard on the active task.");

// The scoring report card shows status only — no editable entry point.
const scoringCardBody = sliceBetween(app, "function writingReportScoringStateHtml(entry, task) {", "function writingReportScoringModelLabel");
assert.doesNotMatch(scoringCardBody, /继续编辑/, "The scoring card must not offer 继续编辑.");
assert.doesNotMatch(scoringCardBody, /data-writing-report-edit=/, "The scoring card must not render an edit action.");
assert.match(scoringCardBody, /class="spinner"/, "The scoring card must still show the scoring spinner.");

// The retired "edit while scoring → auto rescore" flow must be fully removed.
assert.doesNotMatch(app, /rescoreAfterActiveTask/, "No rescore-after-active-task legacy state may remain.");
assert.doesNotMatch(app, /正在使用最新作文重新评分/, "No auto-rescore messaging may remain.");

// ── Report paragraph undo is scoped to the CURRENT node ────────────────────
// A rewrite+rescore creates a new report node: the previous report's undo
// history must never be reachable from the new one.
assert.doesNotMatch(
  app,
  /moveWritingReportUndoStacks/,
  "Old undo stacks must not be carried into a new report node.",
);
assert.match(
  app,
  /function clearWritingReportUndoStacks\(entryId\) \{[\s\S]{0,400}saveWritingReportUndoStackByKey\(key, \[\]\)/,
  "Clearing a report's undo stacks must also wipe its persisted snapshots.",
);
assert.match(
  app,
  /if \(originalId && savedId && originalId !== savedId\) \{[\s\S]{0,600}clearWritingReportUndoStacks\(originalId\);/,
  "When a save produces a new entry id, the old node's undo history must be cleared.",
);
assert.match(
  app,
  /async function scoreWritingEntry\(\) \{[\s\S]{0,300}clearWritingReportUndoStacks\(state\.writing\.entry\?\.id\);/,
  "Starting a new scoring round must clear the previous node's undo history.",
);

console.log("Writing score-lock checks passed.");
