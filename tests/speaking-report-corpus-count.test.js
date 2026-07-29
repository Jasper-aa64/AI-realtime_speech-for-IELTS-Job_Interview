const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

assert.match(
  app,
  /function\s+reportQuestionHeaderHtml\(countCorpus\)[\s\S]{0,500}data-report-corpus-count[\s\S]{0,300}>Question</,
  "P1/P3 report headers should expose a scoped corpus-count label.",
);

assert.match(
  app,
  /function\s+updateReportCorpusHeaderCounts\([^)]*\)[\s\S]{0,1400}closest\("table"\)[\s\S]{0,900}Question \(\$\{savedCount\}\/\$\{buttons\.length\}\)/,
  "Corpus counts should be calculated independently inside each report table.",
);

assert.match(
  app,
  /function\s+turnTableSection\([^)]*\)[\s\S]{0,1000}reportQuestionHeaderHtml\(!isP2\)/,
  "Standalone P1/P3 reports should enable the count while P2 keeps its plain header.",
);

assert.match(
  app,
  /function\s+mockTurnSections\([^)]*\)[\s\S]{0,1400}reportQuestionHeaderHtml\(!isP2\)/,
  "Mock P1 and P3 sections should each render their own count header.",
);

assert.match(
  app,
  /api\("\/api\/corpus\/saved-status"[\s\S]{0,1600}dataset\.corpusStatusResolved\s*=\s*"true"[\s\S]{0,500}updateReportCorpusHeaderCounts\(\)/,
  "Counts should become visible only after saved-status resolves successfully.",
);

assert.match(
  app,
  /function\s+applyCorpusButtonState\(button,\s*saved\)[\s\S]{0,400}button\.dataset\.corpusSaved\s*=[\s\S]{0,700}updateReportCorpusHeaderCounts\(\)/,
  "Saving or clearing corpus should update the visible report count immediately.",
);

console.log("Speaking report corpus-count checks passed.");
