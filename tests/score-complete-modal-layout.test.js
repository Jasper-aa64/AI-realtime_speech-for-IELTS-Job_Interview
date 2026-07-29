const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "web/static/index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

assert.match(
  html,
  /id="writingScoreCompleteModal"[\s\S]{0,2200}class="score-complete-main"[\s\S]{0,900}id="writingScoreCompleteCriteria"/,
  "Writing completion should use the shared compact scorecard layout.",
);

assert.match(
  html,
  /id="speakingScoreCompleteModal"[\s\S]{0,2200}class="score-complete-main speaking-score-complete-main"[\s\S]{0,900}id="speakingScoreCompleteCriteria"/,
  "Speaking completion should use the same scorecard layout.",
);

assert.match(
  css,
  /\.modal-card\.writing-score-complete-card\s*\{[\s\S]{0,260}width:\s*min\(620px,\s*calc\(100vw\s*-\s*32px\)\)/,
  "Score completion cards must override the later generic modal width with a compact desktop width.",
);

assert.match(
  css,
  /\.writing-score-complete-criteria\s*\{[\s\S]{0,220}grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/,
  "Writing should distribute its four criteria evenly.",
);

assert.match(
  css,
  /\.speaking-score-complete-criteria\s*\{[\s\S]{0,220}grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/,
  "Speaking should distribute its three criteria across the full available row.",
);

assert.doesNotMatch(
  css,
  /\.writing-score-complete-body\s*>\s*strong\s*\{[\s\S]{0,180}linear-gradient/,
  "The old full-width Band strip should not remain in the redesigned completion modal.",
);

console.log("Score completion modal layout checks passed.");
