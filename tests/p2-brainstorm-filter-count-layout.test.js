const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const css = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "styles.css"),
  "utf8"
);
const match = css.match(/\.p2-brainstorm-filter-count\s*{([\s\S]*?)\n}/);

assert.ok(match, "Brainstorm filter-count badge styles must exist.");
const rule = match[1];
assert.match(rule, /flex:\s*0\s+0\s+auto/, "The count badge must shrink to its content instead of reserving a wide flex slot.");
assert.match(rule, /width:\s*fit-content/, "The count badge width must follow its actual label.");
assert.match(rule, /justify-content:\s*center/, "The count label must be centered within its pill.");
assert.match(rule, /text-align:\s*center/, "The count text must not be right-aligned inside the pill.");
assert.doesNotMatch(rule, /flex:\s*0\s+0\s+168px/, "The old 168px reservation must not return.");

console.log("P2 Brainstorm filter-count layout checks passed.");
