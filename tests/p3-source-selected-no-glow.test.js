const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const css = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "styles.css"),
  "utf8"
);

const finalRule = css.match(
  /\/\* P3 source selection: flat active state \*\/[\s\S]*?\.p3-source-option\.active\s*\{([^}]*)\}/
);

assert.ok(finalRule, "P3 source options need a final active-state override.");
assert.match(finalRule[1], /box-shadow\s*:\s*none\s*!important\s*;/);
assert.match(finalRule[1], /filter\s*:\s*none\s*!important\s*;/);
assert.ok(
  css.indexOf("/* P3 source selection: flat active state */")
    > css.lastIndexOf("body.theme-dark.font-popular .p3-source-option.active"),
  "The flat active state must come after all theme-specific glow rules."
);

console.log("P3 source selected no-glow checks passed.");
