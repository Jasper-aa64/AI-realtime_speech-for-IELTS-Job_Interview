const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const appSource = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

const exitStart = appSource.indexOf("async function exitPractice()");
const exitEnd = appSource.indexOf("function recoverActivePracticeAfterError", exitStart);
assert(exitStart >= 0 && exitEnd > exitStart, "exitPractice should be present before error recovery.");

const exitSource = appSource.slice(exitStart, exitEnd);
assert.match(
  exitSource,
  /const shouldReturnToP3Launch = state\.view === "p3";/,
  "P3 exits should be detected before async abort cleanup starts.",
);

const p3ExitBlock = /if \(shouldReturnToP3Launch\) \{([\s\S]*?)\n  \}\n  if \(attemptId\)/.exec(exitSource)?.[1] || "";
assert.match(
  p3ExitBlock,
  /resetPracticeSurface\(\);/,
  "P3 red-X exits should immediately restore the launch/prep surface.",
);
assert.doesNotMatch(
  p3ExitBlock,
  /await\s+api/,
  "P3 red-X exits must not wait for the abort request before returning to prep.",
);
assert.match(
  p3ExitBlock,
  /api\(`\/api\/attempts\/\$\{attemptId\}\/abort`, \{\}\)\.catch\(\(\) => null\);/,
  "P3 red-X exits should still abort the attempt in the background.",
);

console.log("P3 red-X exit UI regression checks passed.");
