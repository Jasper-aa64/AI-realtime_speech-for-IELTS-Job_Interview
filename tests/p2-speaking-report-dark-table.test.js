const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const cssSource = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

const marker = "Speaking P2 reports use a two-column layout";
const start = cssSource.indexOf(marker);
assert(start >= 0, "P2 speaking report dark-table override should be documented.");

const source = cssSource.slice(start, start + 3200);

assert.match(
  source,
  /#historyPanel \.turn-report-table\.p2-report-table th[\s\S]*background:\s*#182126\s*!important;/,
  "P2 speaking report headers should use the same dark report table header color.",
);

assert.match(
  source,
  /\.p2-content-row > td[\s\S]*background:\s*linear-gradient\(180deg,\s*#12191b,\s*#0e1416\)\s*!important;/,
  "P2 speaking report answer/model cells should use the same dark report table cell color.",
);

assert.match(
  source,
  /\.p2-coaching-row > td[\s\S]*background:\s*linear-gradient\(180deg,\s*#12191b,\s*#0e1416\)\s*!important;/,
  "P2 speaking report AI guidance rows should use the same dark report table cell color.",
);

assert.match(
  source,
  /body\.theme-dark\.font-popular #historyPanel \.turn-report-table\.p2-report-table/,
  "Third dark theme should also receive the unified P2 speaking report table surface.",
);

console.log("P2 speaking report dark table checks passed.");
