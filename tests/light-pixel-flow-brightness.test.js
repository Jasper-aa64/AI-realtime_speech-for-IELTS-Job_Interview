const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const cssSource = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");
const flowSource = fs.readFileSync(path.join(root, "web/static/corpus-takeaway.js"), "utf8");

// The P2 brainstorm field keeps its strong light-mode filter.
assert.match(
  cssSource,
  /body:not\(\.theme-dark\) \.p2-brainstorm-head-field \.p2-pixel-flow-canvas\s*{[\s\S]{0,120}filter:\s*saturate\(5\.2\)\s*brightness\(5\.15\)\s*contrast\(1\.52\)/,
  "Light-mode brainstorm pixel canvas should keep the stronger bright filter.",
);
// The 追问压力 headers (P1 / P3 / interview) draw their own light palette, unfiltered, and never flash on switch-on.
assert.match(cssSource, /\.p2-pixel-flow-canvas\.is-themed\s*{\s*animation:\s*none !important;/);
assert.match(cssSource, /body:not\(\.theme-dark\):not\(#_\):not\(#__\) \.p2-pixel-flow-canvas\.is-themed\s*{\s*filter:\s*none !important;/);
assert.match(flowSource, /const lightPalette = \[/);

console.log("Light pixel-flow brightness regression checks passed.");
