const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

const annotationStart = app.indexOf("function normalizeWritingAnnotation");
const annotationEnd = app.indexOf("function writingAnnotationsForParagraph", annotationStart);
assert(annotationStart >= 0 && annotationEnd > annotationStart, "Writing annotation helpers should exist.");
const sandbox = {};
vm.runInNewContext(app.slice(annotationStart, annotationEnd), sandbox);

const annotations = sandbox.writingInlineAnnotations({
  inline_annotations: [
    { paragraph_index: 1, original: "finantial", type: "spelling", suggestion: "financial" },
  ],
  grammar_corrections: [
    { paragraph_index: 1, original: "which ensure", type: "grammar", suggestion: "which ensures" },
    { paragraph_index: 1, original: "finantial", type: "spelling", suggestion: "financial" },
  ],
});
assert.deepStrictEqual(
  Array.from(annotations, (item) => item.original),
  ["finantial", "which ensure"],
  "Inline annotations and grammar corrections must be merged, then deduplicated; one inline annotation must not hide the rest.",
);

const scoringStart = app.indexOf("function writingReportDetailHtml(entry)");
const scoringEnd = app.indexOf("function writingStructureAdviceHtml", scoringStart);
const scoringSource = app.slice(scoringStart, scoringEnd);
assert.match(
  scoringSource,
  /if \(isScoringReport\) \{[\s\S]{0,1800}return `[^`]*writingReportScoringStateHtml\(entry, task\)/,
  "A scoring report must return one dedicated status surface instead of stacking it with a saved-draft card.",
);

const applyStart = app.indexOf("async function applyWritingFixFromPopover()");
const applyEnd = app.indexOf("function writingParagraphsForEditing", applyStart);
const applySource = app.slice(applyStart, applyEnd);
const optimisticRender = applySource.indexOf("renderVisibleWritingReport(optimisticEntry)");
const persistFix = applySource.indexOf("await saveWritingReportAnswer");
assert(optimisticRender >= 0 && persistFix >= 0 && optimisticRender < persistFix, "Fix should update the report immediately before waiting for persistence.");

assert.match(
  app,
  /event\.target\?\.closest\?\.\("#writingFixPopover"\)[\s\S]{0,180}hideWritingInlineTooltip\(\)[\s\S]{0,80}return;/,
  "Moving onto the Fix control must suppress the text annotation tooltip instead of letting it cover the button.",
);

assert.match(
  app,
  /api\(`\/api\/writing\/entries\/\$\{entry\.id\}\/score-task`,\s*\{\s*force:\s*writingReportScored\(entry\)\s*\}\)/,
  "Starting scoring from an already scored essay must explicitly create a replacement report task rather than reuse the old successful task.",
);

console.log("Writing report regression checks passed.");
