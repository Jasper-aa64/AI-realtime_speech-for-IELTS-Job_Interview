const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const corpus = fs.readFileSync(path.join(root, "web/static/corpus-takeaway.js"), "utf8");
const styles = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");
const index = fs.readFileSync(path.join(root, "web/static/index.html"), "utf8");

assert.match(
  corpus,
  /function syncP2BrainstormFilterBarSelection\(\)[\s\S]*classList\.toggle\("is-active"[\s\S]*aria-pressed/,
  "Changing a Brainstorm filter should update the existing chips instead of rebuilding the filter bar.",
);

assert.match(
  corpus,
  /function commitP2BrainstormFilterVisibility\([\s\S]*classList\.toggle\("is-filtered-out", !show\)/,
  "Brainstorm filter visibility changes should be committed atomically.",
);

assert.match(
  corpus,
  /is-filter-switching-out[\s\S]*commitP2BrainstormFilterVisibility[\s\S]*scrollTop = 0[\s\S]*is-filter-switching-in/,
  "Brainstorm filters should swap while faded out, reset to the first result, then fade in.",
);

assert.match(
  styles,
  /\.p2-brainstorm-list\.is-filter-switching-out\s*>\s*\.p2-brainstorm-row:not\(\.is-filtered-out\)[\s\S]*opacity:\s*0[\s\S]*transform:\s*translateY\(4px\)/,
  "Visible Brainstorm rows should leave together without collapsing one by one.",
);

assert.match(
  styles,
  /\.p2-brainstorm-list\.is-filter-switching-in\s*>\s*\.p2-brainstorm-row:not\(\.is-filtered-out\)[\s\S]*animation:\s*p2BrainstormFilterIn/,
  "The final Brainstorm result set should enter together after the atomic swap.",
);

assert.doesNotMatch(
  corpus,
  /row\.classList\.add\("is-filtering-out"\)/,
  "Rows must not run independent exit callbacks that repeatedly reflow the list.",
);

assert.match(index, /styles\.css\?v=20260818-card-corner-clip-1/);
assert.match(index, /corpus-takeaway\.js\?v=20260816-corpus-voice-dictation-1/);

console.log("P2 Brainstorm filter motion checks passed.");
