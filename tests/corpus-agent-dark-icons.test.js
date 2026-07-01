const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const cssSource = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

const marker = "P1/P2 corpus assistant icons";
const start = cssSource.indexOf(marker);
assert(start >= 0, "Dark corpus assistant icon override should be documented.");

const source = cssSource.slice(start, start + 1800);

assert.match(
  source,
  /body\.theme-dark:not\(\.font-academic\):not\(\.font-popular\)[\s\S]*\.p1-corpus-head \.corpus-agent-button svg/,
  "Default dark theme should restore readable P1 corpus assistant icon color.",
);

assert.match(
  source,
  /body\.theme-dark:not\(\.font-academic\):not\(\.font-popular\)[\s\S]*\.p2-corpus-head \.corpus-agent-button svg/,
  "Default dark theme should restore readable P2 corpus assistant icon color.",
);

assert.match(
  source,
  /body\.theme-dark\.font-academic[\s\S]*\.p1-corpus-head \.corpus-agent-button svg/,
  "Second dark theme should restore readable P1 corpus assistant icon color.",
);

assert.match(
  source,
  /body\.theme-dark\.font-academic[\s\S]*\.p2-corpus-head \.corpus-agent-button svg/,
  "Second dark theme should restore readable P2 corpus assistant icon color.",
);

assert.match(
  source,
  /stroke:\s*currentColor\s*!important;/,
  "Corpus assistant icons should inherit the button text color instead of using a hard-coded dark stroke.",
);

assert.doesNotMatch(
  source,
  /body\.theme-dark\.font-popular/,
  "This fix should not directly override the third dark theme's separate corpus assistant styling.",
);

console.log("Corpus assistant dark icon checks passed.");
