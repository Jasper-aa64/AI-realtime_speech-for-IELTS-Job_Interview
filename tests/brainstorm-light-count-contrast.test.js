const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const css = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

assert.match(
  css,
  /body:not\(\.theme-dark\) \.p2-brainstorm-entry-card\[data-category="brainstorm"\] > header > \.p2-topic-count\s*{[\s\S]{0,260}color:\s*#0f172a\s*!important[\s\S]{0,260}text-shadow:\s*none\s*!important/,
  "Light-mode Brainstorm count badge should use dark readable digits, not inherited white text.",
);

console.log("Brainstorm light count contrast checks passed.");
