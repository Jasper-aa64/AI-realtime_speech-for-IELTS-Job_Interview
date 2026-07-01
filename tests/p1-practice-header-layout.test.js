const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const cssSource = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

assert.match(
  cssSource,
  /#practicePanel\s+\.exam-status\s*{[\s\S]{0,260}margin:\s*-18px -18px 0\s*!important;[\s\S]{0,260}width:\s*calc\(100% \+ 36px\)\s*!important;[\s\S]{0,160}height:\s*82px\s*!important;/,
  "P2/mock headers should inherit the P1 full-bleed pressure header geometry.",
);

assert.match(
  cssSource,
  /#practicePanel\s+\.exam-status\.p1-pixel-flow\s*{[\s\S]{0,120}overflow:\s*hidden\s*!important;/,
  "P1 pixel-flow should keep clipping inside the full-bleed header shell.",
);

console.log("P1 practice header layout regression checks passed.");
