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
// The 追问压力 headers (P1 / P3 / interview) look the same in light and dark and never flash on switch-on:
// no ignite animation, and the backdrop arrives fast while the pixels fade in.
assert.match(cssSource, /\.p2-pixel-flow-canvas\.is-themed\s*{\s*animation:\s*none !important;/);
assert.match(cssSource, /\.exam-status\.p1-pixel-flow\.p1-pixel-flow-visible,[\s\S]{0,160}transition:\s*background-color 260ms ease !important;/);
assert.doesNotMatch(cssSource, /body:not\(\.theme-dark\)[^{]*\.exam-status\.p1-pixel-flow \.p2-pixel-flow-canvas[^{]*{[^}]*saturate\(5\.2\)/);
assert.match(flowSource, /is-themed/);

console.log("Light pixel-flow brightness regression checks passed.");
