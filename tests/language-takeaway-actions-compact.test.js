const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const cssSource = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

assert.match(
  cssSource,
  /\.language-takeaway-action-buttons\s*{[\s\S]{0,180}grid-template-columns:\s*repeat\(2,\s*minmax\(104px,\s*1fr\)\)\s*!important;[\s\S]{0,140}width:\s*min\(100%,\s*232px\)\s*!important;/,
  "Language Takeaway action row should use narrower text-button columns.",
);

assert.match(
  cssSource,
  /\.language-takeaway-action-buttons button:not\(\.language-takeaway-dict-toggle\)\s*{[\s\S]{0,180}min-height:\s*40px\s*!important;[\s\S]{0,140}font-size:\s*14px\s*!important;/,
  "Language Takeaway save buttons should be compact but not too small, without shrinking the dictionary switch.",
);

console.log("Language Takeaway compact action checks passed.");
