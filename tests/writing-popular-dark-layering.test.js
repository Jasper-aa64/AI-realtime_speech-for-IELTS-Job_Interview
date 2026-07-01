const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const cssSource = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

const marker = "Third dark theme daily-writing layering";
const start = cssSource.indexOf(marker);
assert(start >= 0, "Third dark theme daily-writing layering override should be documented.");

const source = cssSource.slice(start, start + 3600);

assert.match(
  source,
  /body\.theme-dark\.font-popular #writingPanel \.writing-shell[\s\S]*background:\s*transparent\s*!important;/,
  "Writing shell should stay transparent so card boundaries read against the black workspace.",
);

assert.match(
  source,
  /body\.theme-dark\.font-popular #writingPanel \.writing-editor-card,[\s\S]*body\.theme-dark\.font-popular #writingPanel \.writing-result-card[\s\S]*background:[\s\S]*linear-gradient\(180deg,\s*rgba\(255,\s*255,\s*255,\s*0\.040\),\s*rgba\(255,\s*255,\s*255,\s*0\.008\)\),[\s\S]*#0b0e11\s*!important;/,
  "Main daily-writing cards should use a raised graphite layer instead of the same pure black as the page.",
);

assert.match(
  source,
  /body\.theme-dark\.font-popular #writingPanel \.writing-prompt-card[\s\S]*background:\s*linear-gradient\(180deg,\s*#15191d,\s*#0d1013\)\s*!important;/,
  "The prompt card should use a separate inner graphite layer.",
);

assert.match(
  source,
  /body\.theme-dark\.font-popular #writingPanel \.writing-answer[\s\S]*background:\s*#050608\s*!important;/,
  "The writing textarea should remain near-black while retaining a visible boundary.",
);

assert.match(
  source,
  /body\.theme-dark\.font-popular #writingPanel \.writing-stats-grid div[\s\S]*background:[\s\S]*linear-gradient\(180deg,\s*rgba\(255,\s*255,\s*255,\s*0\.055\),\s*rgba\(255,\s*255,\s*255,\s*0\.012\)\),[\s\S]*#11161b\s*!important;/,
  "Writing stats tiles should stand apart from the result card.",
);

console.log("Third dark daily-writing layering checks passed.");
