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
const progressStart = appSource.indexOf("function p3BankCardProgressState");
const progressEnd = appSource.indexOf("function p3BankCardProgressLabel", progressStart);
assert(progressStart >= 0 && progressEnd > progressStart, "P3 bank progress state helper should be present.");
const progressSource = appSource.slice(progressStart, progressEnd);

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
assert.match(
  previewSource,
  /p3BankRoundChipsHtml\(entry\)/,
  "P3 bank cards should show the stable Q-group chips beside their fill progress.",
);
const roundChipsStart = appSource.indexOf("function p3BankRoundChipsHtml");
const roundChipsEnd = appSource.indexOf("function buildLocalP3BankPlanFromCard", roundChipsStart);
assert(roundChipsStart >= 0 && roundChipsEnd > roundChipsStart, "P3 bank round-chip helper should be present.");
const roundChipsSource = appSource.slice(roundChipsStart, roundChipsEnd);
assert.match(
  roundChipsSource,
  /p3-bank-round-chip.*is-next/,
  "The pending Q group should be the only highlighted chip.",
);
assert.match(
  roundChipsSource,
  /is-dim/,
  "Completed and non-current Q groups should stay visibly dimmed.",
);
assert.match(
  cssSource,
  /\.p3-bank-round-chip\.is-next[\s\S]{0,260}color:/,
  "The active Q group needs a distinct readable treatment.",
);
assert.match(
  cssSource,
  /\.p3-bank-round-chip\.is-dim[\s\S]{0,220}(?:opacity|color):/,
  "Inactive Q groups need a muted treatment without dimming the whole card.",
);
assert.match(
  cssSource,
  /\.p3-bank-replay-dialog\s*{[\s\S]{0,120}width:\s*min\(480px,\s*calc\(100vw\s*-\s*40px\)\)/,
  "The multi-round replay chooser should be wider on desktop while remaining viewport-safe.",
);
assert.match(
  progressSource,
  /practice_is_complete/,
  "The three-state mapper should recognize completed cards from legacy cached payloads.",
);
assert.match(
  progressSource,
  /practice_completed_round_count/,
  "The three-state mapper should recognize partial progress from legacy cached payloads.",
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
assert.doesNotMatch(
  cssSource,
  /\.p3-bank-picker-card::before/,
  "Progress fill must be painted by the card background, not an overlay that can hide card content.",
);
assert.match(
  cssSource,
  /\.p3-bank-picker-card\s*{[\s\S]{0,900}background:\s*linear-gradient\(/,
  "P3 bank cards should paint progress directly in their own background.",
);
assert.doesNotMatch(
  cssSource,
  /\.p3-bank-picker-card:hover,[\s\S]{0,420}background\s*:/,
  "Hovering a P3 bank card must not repaint its progress-filled surface.",
);
assert.match(
  cssSource,
  /body\.theme-dark\.font-popular\s+\.p3-bank-picker-card\s*{[\s\S]{0,220}--p3-bank-progress-color:\s*#[0-9a-f]{6}/i,
  "The third dark theme needs a dedicated, visible P3 bank progress fill.",
);
assert.match(
  cssSource,
  /body\.theme-dark\.font-popular\s+\.p3-bank-picker-card\s+\.p3-bank-card-top\s*{[\s\S]{0,180}color:\s*#[0-9a-f]{6}/i,
  "The third dark theme needs a readable P3 bank category label.",
);
assert.match(
  cssSource,
  /body\.theme-dark\.font-popular\s+\.p3-bank-round-chip\.is-next\s*{[\s\S]{0,220}color:\s*#[0-9a-f]{6}/i,
  "The third dark theme needs a readable active Q-group chip.",
);

console.log("P3 bank three-state fill progress checks passed.");
