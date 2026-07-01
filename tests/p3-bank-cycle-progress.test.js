const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const appSource = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

const startPracticeStart = appSource.indexOf("async function startPractice()");
const startPracticeEnd = appSource.indexOf("function revealP3PracticeGrid", startPracticeStart);
assert(startPracticeStart >= 0 && startPracticeEnd > startPracticeStart, "startPractice should be present.");
const startPracticeSource = appSource.slice(startPracticeStart, startPracticeEnd);

assert.doesNotMatch(
  startPracticeSource,
  /confirmP3BankPracticeCycle\(/,
  "P3 bank cycle completion notice must not block the start button; cycle completion is reported after a scored report refreshes progress.",
);

assert.match(
  startPracticeSource,
  /if \(mode === "p3"\) setP3StartPending\(true/,
  "P3 start should show immediate pending feedback before wallet/start-attempt round trips.",
);

const invalidationStart = appSource.indexOf("function invalidateP3BankPracticeProgress");
const invalidationEnd = appSource.indexOf("function startSpeakingScorePolling", invalidationStart);
assert(invalidationStart >= 0 && invalidationEnd > invalidationStart, "invalidateP3BankPracticeProgress should be present.");
const invalidationSource = appSource.slice(invalidationStart, invalidationEnd);

assert.match(
  invalidationSource,
  /fetchP2CorpusPayload\(\{ force: true \}\)/,
  "P3 bank progress invalidation should refresh the corpus payload directly so it can compare cycle progress before applying it.",
);

assert.match(
  invalidationSource,
  /maybeShowP3BankCycleCompleteNotice/,
  "P3 bank progress invalidation should check whether the whole fixed P3 bank cycle just completed.",
);

const switchViewStart = appSource.indexOf("function switchView(view, options = {})");
const switchViewEnd = appSource.indexOf("function updateAgentAssistantVisibility", switchViewStart);
assert(switchViewStart >= 0 && switchViewEnd > switchViewStart, "switchView should be present.");
const switchViewSource = appSource.slice(switchViewStart, switchViewEnd);

assert.match(
  switchViewSource,
  /prefetchP3BankPracticeAssets\(\)\.catch\(\(\) => \{\}\);/,
  "Entering P3 should warm the P2 bank corpus in the background before the first Browse Card/start interaction.",
);

console.log("P3 bank cycle progress regression checks passed.");
