const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "corpus-takeaway.js"),
  "utf8"
);
const appSource = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "app.js"),
  "utf8"
);

function functionDefinition(name) {
  const declaration = source.indexOf(`function ${name}(`);
  assert.notStrictEqual(declaration, -1, `${name} must exist.`);
  const bodyStart = source.indexOf("{", declaration);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(declaration, index + 1);
  }
  assert.fail(`${name} must have a closed body.`);
}

const boundaryDelay = new Function(
  `${functionDefinition("msUntilNextTakeawayReviewDay")};
   return msUntilNextTakeawayReviewDay;`
)();

assert.equal(
  boundaryDelay(new Date(2026, 6, 17, 3, 59, 0, 0)),
  60 * 1000,
  "At 03:59 the watcher should refresh at the 04:00 review-day boundary."
);
assert.equal(
  boundaryDelay(new Date(2026, 6, 17, 4, 1, 0, 0)),
  (23 * 60 + 59) * 60 * 1000,
  "After 04:00 the next refresh should be scheduled for the following review day."
);

assert.match(
  source,
  /function startTakeawayReviewDayWatcher\(\)[\s\S]*visibilitychange[\s\S]*focus[\s\S]*pageshow/,
  "The watcher must recover after hidden tabs, sleep, and browser page restoration."
);
assert.match(
  source,
  /function refreshTakeawayReviewDay[\s\S]*todayKey\(\)[\s\S]*updateTakeawayReviewDots\(\)/,
  "A changed review-day key must recompute the navigation dots."
);
assert.match(
  source,
  /function refreshTakeawayReviewDay[\s\S]*renderTakeawayReviewPanel/,
  "An open Takeaway review panel must update together with its navigation dot."
);
assert.match(
  appSource,
  /startTakeawayReviewDayWatcher\(\);/,
  "App initialization must start exactly one review-day watcher."
);

console.log("Takeaway review day rollover checks passed.");
