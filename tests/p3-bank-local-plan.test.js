const assert = require("assert");
const fs = require("fs");
const path = require("path");

const appSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "app.js"), "utf8");

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

console.log("P3 bank local plan regression checks passed.");
