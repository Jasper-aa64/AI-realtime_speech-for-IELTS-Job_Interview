const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const styles = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

assert.match(
  styles,
  /#accountProfilePanel \.account-card-footer\s*\{[\s\S]*?grid-template-columns:\s*112px\s+148px\s+minmax\(0,\s*1fr\)\s*!important[\s\S]*?width:\s*100%\s*!important[\s\S]*?min-width:\s*0\s*!important/,
  "Account settings must keep compact fixed utility columns and give all remaining width to the AI source without overflowing.",
);

assert.match(
  styles,
  /#accountProfilePanel \.account-theme-toggle span,[\s\S]*?#accountProfilePanel \.account-ai-source-label\s*\{[\s\S]*?align-self:\s*flex-start\s*!important[\s\S]*?text-align:\s*left\s*!important/,
  "All three account setting labels must stay at the upper-left.",
);

assert.match(
  styles,
  /#accountProfilePanel \.account-ai-source-select\s*\{[\s\S]*?width:\s*100%\s*!important[\s\S]*?min-width:\s*0\s*!important[\s\S]*?max-width:\s*100%\s*!important[\s\S]*?box-sizing:\s*border-box\s*!important/,
  "The AI source select must use its wider column without clipping long labels.",
);

assert.match(
  styles,
  /#accountProfilePanel \.account-language-options\s*\{[\s\S]*?width:\s*100%\s*!important[\s\S]*?min-width:\s*0\s*!important[\s\S]*?box-sizing:\s*border-box\s*!important/,
  "The language switch must fit inside the compact language column.",
);

assert.match(
  styles,
  /@media\s*\(max-width:\s*860px\)[\s\S]*?#accountProfilePanel \.account-card-footer\s*\{[\s\S]*?grid-template-columns:\s*1fr\s*!important/,
  "Account settings must stack on narrow screens.",
);

console.log("Account settings width checks passed.");
