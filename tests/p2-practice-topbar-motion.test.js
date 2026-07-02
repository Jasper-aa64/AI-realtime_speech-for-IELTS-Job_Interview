const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const appSource = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const corpusSource = fs.readFileSync(path.join(root, "web/static/corpus-takeaway.js"), "utf8");
const cssSource = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

const renderStart = appSource.indexOf("async function renderP2CorpusPrepPanel");
const renderEnd = appSource.indexOf("function renderCueTop", renderStart);
assert(renderStart >= 0 && renderEnd > renderStart, "renderP2CorpusPrepPanel should be present.");
const renderSource = appSource.slice(renderStart, renderEnd);

assert.match(
  renderSource,
  /setP2PrepPanelHidden\(panel,\s*true\b/,
  "P2 prep selector should hide through the same animated helper instead of hard-cutting.",
);

assert.match(
  renderSource,
  /setP2PrepPanelHidden\(panel,\s*false\)/,
  "P2 prep selector should enter through an animation when the cue card loads.",
);

assert.match(
  cssSource,
  /\.exam-status \.p2-corpus-prep\.p2-prep-entering[\s\S]{0,120}animation:\s*p2PrepEnter/,
  "P2 prep selector should have a dedicated enter animation.",
);

assert.match(
  cssSource,
  /\.exam-status \.p2-corpus-prep\.p2-prep-leaving[\s\S]{0,160}opacity:\s*0/,
  "P2 prep selector should fade/slide out instead of disappearing abruptly.",
);

assert.match(
  cssSource,
  /\.exam-actions \.p1-corpus-peek-button\.peek-button-entering[\s\S]{0,120}peekButtonEnter/,
  "P2 circular buttons reuse the P1/P3 peek-button enter animation through the shared class.",
);

assert.match(
  corpusSource,
  /setPeekButtonHidden\(bankButton,\s*false,\s*\{\s*replayKey:\s*`p2-bank-\$\{questionId\}`\s*\}\)/,
  "P2 bank body lightbulb button should replay the shared enter animation when a new cue appears.",
);

assert.match(
  corpusSource,
  /setPeekButtonHidden\(bodyButton,\s*!visible,\s*\{\s*replayKey:\s*visible \? `p2-body-\$\{state\.p2Corpus\.selectedEntryId\}` : ""\s*\}\)/,
  "P2 linked-material document button should replay the shared enter animation when it appears.",
);

console.log("P2 practice topbar motion checks passed.");
