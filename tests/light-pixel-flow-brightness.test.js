const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const cssSource = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

assert.match(
  cssSource,
  /body:not\(\.theme-dark\) \.p2-brainstorm-head-field \.p2-pixel-flow-canvas,\s*body:not\(\.theme-dark\) \.exam-status\.p1-pixel-flow \.p2-pixel-flow-canvas,\s*body:not\(\.theme-dark\) \.p3-mode-row\.p3-pixel-flow \.p2-pixel-flow-canvas\s*{[\s\S]{0,180}filter:\s*saturate\(5\.2\)\s*brightness\(5\.15\)\s*contrast\(1\.52\)/,
  "Light-mode P1/P3/Brainstorm pixel canvases should use the stronger bright filter.",
);

console.log("Light pixel-flow brightness regression checks passed.");
