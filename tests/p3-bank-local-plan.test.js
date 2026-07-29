const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const appSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "app.js"), "utf8");

function sourceForFunction(name, nextName) {
  const start = appSource.indexOf(`function ${name}`);
  const end = appSource.indexOf(`function ${nextName}`, start);
  assert(start >= 0 && end > start, `${name} should be present before ${nextName}.`);
  return appSource.slice(start, end);
}

assert.match(
  appSource,
  /function buildLocalP3BankPlanFromCard/,
  "Fixed P3 bank cards should build their plan locally from cached progress instead of round-tripping to /api/p3/questions.",
);

const activateStart = appSource.indexOf("function activateP3BankPickerCard");
const activateEnd = appSource.indexOf("function closeP3BankPicker", activateStart);
assert(activateStart >= 0 && activateEnd > activateStart, "activateP3BankPickerCard should be present.");
const activateSource = appSource.slice(activateStart, activateEnd);

assert.match(
  activateSource,
  /loadP3BankPlanFromCard\(card\);/,
  "Selecting a fixed P3 bank card should set the ready plan synchronously.",
);

assert.match(
  activateSource,
  /p3BankCardProgressState\(card\)\s*===\s*["']complete["']/,
  "A completed card should open the replay chooser instead of silently changing its counted plan.",
);
assert.match(
  appSource,
  /\{\s*roundIndex,\s*replay:\s*true\s*\}/,
  "A manually selected completed group must pass an explicit replay marker into its plan.",
);
assert.match(
  appSource,
  /p3_bank_replay:\s*isReplay/,
  "The local P3 bank plan must persist the replay marker for the backend.",
);

const roundLabelSource = sourceForFunction("p3BankRoundLabel", "p3BankRoundChipsHtml");
const p3BankRoundLabel = vm.runInNewContext(`(${roundLabelSource.trim()})`);
assert.strictEqual(
  p3BankRoundLabel([0, 1, 2]),
  "Q1 Q2 Q3",
  "A three-question round should list each Q tag without a range dash.",
);
assert.strictEqual(
  p3BankRoundLabel([3, 4]),
  "Q4 Q5",
  "A two-question round should list each Q tag without a range dash.",
);

const replayPickerSource = sourceForFunction("openP3BankReplayPicker", "activateP3BankPickerCard");
const replayCalls = [];
let replayPickerClosed = 0;
vm.runInNewContext(
  `${replayPickerSource}
   openP3BankReplayPicker({
     practice_rounds: [{ round_index: 0, question_indexes: [0, 1, 2] }]
   });`,
  {
    loadP3BankPlanFromCard(card, message, options) {
      replayCalls.push({ card, message, options });
    },
    closeP3BankPicker() {
      replayPickerClosed += 1;
    },
  },
);
assert.deepStrictEqual(
  replayCalls.map(({ options }) => ({ ...options })),
  [{ roundIndex: 0, replay: true }],
  "A completed card with one round should replay that round immediately without opening a chooser.",
);
assert.strictEqual(replayPickerClosed, 1, "Direct one-round replay should close the P3 bank picker.");

assert.doesNotMatch(
  activateSource,
  /generateP3Plan\(\)\.catch/,
  "Selecting a fixed P3 bank card must not show 'reloading follow-ups' by calling the backend plan generator.",
);

const generateButtonStart = appSource.indexOf('$("p3GeneratePlanButton")?.addEventListener');
const generateButtonEnd = appSource.indexOf('$("p3StartButton")?.addEventListener', generateButtonStart);
assert(generateButtonStart >= 0 && generateButtonEnd > generateButtonStart, "P3 generate button handler should be present.");
const generateButtonSource = appSource.slice(generateButtonStart, generateButtonEnd);

assert.match(
  generateButtonSource,
  /loadP3BankPlanFromCard\(selected,/,
  "Reloading fixed P3 bank follow-ups should use the cached card plan instead of waiting on /api/p3/questions.",
);

const cycleNoticeStart = appSource.indexOf("function p3BankPlanCycleNotice");
const cycleNoticeEnd = appSource.indexOf("function confirmP3BankPracticeCycle", cycleNoticeStart);
assert(cycleNoticeStart >= 0 && cycleNoticeEnd > cycleNoticeStart, "P3 cycle notice helper should be present.");
const cycleNoticeSource = appSource.slice(cycleNoticeStart, cycleNoticeEnd);
assert.match(
  cycleNoticeSource,
  /plan\.p3_bank_replay/,
  "A replay should bypass the cycle-completion notice because it contributes no new coverage.",
);

console.log("P3 bank local plan regression checks passed.");
