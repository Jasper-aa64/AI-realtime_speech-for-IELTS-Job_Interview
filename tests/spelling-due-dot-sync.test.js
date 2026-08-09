const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "app.js"),
  "utf8"
);

assert.match(
  source,
  /const liveDue = spellingDrillController\?\.getLiveDueDotCount\?\.\(\);/,
  "Sidebar red-dot updates must ask the active spelling controller for its local queue progress."
);
assert.match(
  source,
  /Number\.isFinite\(liveDue\) \? liveDue : Number\(stats\?\.due \|\| 0\)/,
  "Stale prefetch stats may only drive the red dot when no live queue count exists."
);

console.log("Spelling due-dot synchronization checks passed.");
