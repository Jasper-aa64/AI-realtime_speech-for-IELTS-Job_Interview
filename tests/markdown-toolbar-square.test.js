const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const styles = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

const toolbarButtonRule = /\.p1-corpus-dialog-card\s+\.vditor-toolbar__item\s+button\s*\{([\s\S]*?)\n\}/.exec(styles);

assert(toolbarButtonRule, "Markdown editor toolbar button rule should exist.");

const ruleBody = toolbarButtonRule[1];

for (const declaration of [
  /width:\s*30px\s*!important/,
  /height:\s*30px\s*!important/,
  /min-width:\s*30px\s*!important/,
  /min-height:\s*30px\s*!important/,
  /aspect-ratio:\s*1\s*\/\s*1/,
  /box-sizing:\s*border-box\s*!important/,
  /padding:\s*0\s*!important/,
  /display:\s*inline-flex\s*!important/,
  /align-items:\s*center\s*!important/,
  /justify-content:\s*center\s*!important/,
  /line-height:\s*0\s*!important/,
]) {
  assert(declaration.test(ruleBody), `Markdown toolbar square button rule missing ${declaration}.`);
}

console.log("Markdown toolbar square button checks passed.");
