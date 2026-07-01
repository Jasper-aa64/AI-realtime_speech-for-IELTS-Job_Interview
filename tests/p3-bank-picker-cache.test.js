const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const appSource = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

const start = appSource.indexOf("async function openP3BankPicker()");
const end = appSource.indexOf("function activateP3BankPickerCard", start);
assert(start >= 0 && end > start, "openP3BankPicker should be present.");

const source = appSource.slice(start, end);
assert.match(
  source,
  /if \(list && !state\.p2Corpus\.loaded\) list\.innerHTML = p3BankPickerLoadingHtml\(\);/,
  "P3 bank picker should only show the loading state when the P2 corpus cache is cold.",
);

assert.match(
  source,
  /await renderP3BankPicker\(\{ force: false \}\);/,
  "P3 bank picker should reuse the warm P2 corpus cache instead of forcing a network refresh.",
);

assert.doesNotMatch(
  source,
  /renderP3BankPicker\(\{ force: true \}\)/,
  "P3 bank picker must not force-refresh on every open.",
);

console.log("P3 bank picker cache regression checks passed.");
