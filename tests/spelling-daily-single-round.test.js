const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "spelling-drill.js"),
  "utf8"
);

assert.doesNotMatch(
  source,
  /data-spelling-reload/,
  "A completed spelling session must not expose a client-side replay action."
);
assert.match(
  source,
  /今日复习完成[\s\S]{0,240}明天再来/,
  "The completed daily queue should clearly end for the day instead of inviting another round."
);

assert.match(
  source,
  /\/api\/writing\/spelling-words\/complete-daily-batch/,
  "Finishing the visible daily queue must persist that boundary before a reload can reopen it."
);

console.log("Spelling daily single-round checks passed.");
