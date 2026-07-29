const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const css = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

assert.match(
  css,
  /\.writing-saved-report-head\s*>\s*strong\s+span\.speaking-report-status-chip\s*\{[^}]*font-size:\s*18px;/s,
  "Unscored and failed speaking report status chips must retain the same readable size as scoring.",
);

console.log("Speaking report status-chip size checks passed.");
