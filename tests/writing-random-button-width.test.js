const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const cssSource = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

const randomButtonRules = Array.from(cssSource.matchAll(/\.writing-topbar-actions \.topbar-random-button\s*{[^}]*}/g)).map((match) => match[0]);

assert(randomButtonRules.length >= 1, "Writing random button should have scoped topbar sizing rules.");

assert(
  randomButtonRules.some((rule) => /min-width:\s*118px\s*!important;/.test(rule)),
  "Writing random button should be narrower than the old 150px width.",
);

assert(
  randomButtonRules.every((rule) => !/min-width:\s*150px\s*!important;/.test(rule)),
  "Writing random button must not keep the old 150px fixed width.",
);

console.log("Writing random button width checks passed.");
