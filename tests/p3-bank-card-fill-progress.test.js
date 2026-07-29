const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const appSource = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const cssSource = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

const previewStart = appSource.indexOf("function p3BankCardPreviewHtml");
const previewEnd = appSource.indexOf("function p3SelectedBankCardHtml", previewStart);
assert(previewStart >= 0 && previewEnd > previewStart, "P3 bank card preview renderer should be present.");
const previewSource = appSource.slice(previewStart, previewEnd);

assert.match(
  previewSource,
  /p3BankCardProgressState\(entry\)/,
  "P3 bank cards should derive one explicit three-state progress value.",
);
assert.match(
  previewSource,
  /p3-bank-picker-card--\$\{progressState\}/,
  "P3 bank cards should expose their progress state as a fill class.",
);
assert.doesNotMatch(
  previewSource,
  /p3BankRoundChipsHtml|p3BankPracticeLabel|practice_completed_round_count/,
  "P3 bank cards must not render per-card rounds or the old dimmed-round progress.",
);

assert.match(
  cssSource,
  /\.p3-bank-picker-card--none\s*{[\s\S]{0,120}--p3-bank-progress-fill:\s*0%/,
  "Uncompleted cards should have no progress fill.",
);
assert.match(
  cssSource,
  /\.p3-bank-picker-card--partial\s*{[\s\S]{0,120}--p3-bank-progress-fill:\s*50%/,
  "Partially completed cards should fill the left half.",
);
assert.match(
  cssSource,
  /\.p3-bank-picker-card--complete\s*{[\s\S]{0,120}--p3-bank-progress-fill:\s*100%/,
  "Completed cards should fill the whole card.",
);
assert.doesNotMatch(
  cssSource,
  /\.p3-bank-picker-card--complete\s*{[\s\S]{0,120}opacity:\s*0\./,
  "Completed cards should use fill rather than dimming the card.",
);

console.log("P3 bank three-state fill progress checks passed.");
