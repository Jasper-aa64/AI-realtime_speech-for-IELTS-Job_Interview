const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const styles = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");
const corpus = fs.readFileSync(path.join(root, "web/static/corpus-takeaway.js"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

assert(
  /function\s+updateLanguageTakeawaySpellingButton\(\)[\s\S]*isSingleEnglishWord\(\$\("languageTakeawaySource"\)\?\.value \|\| ""\)[\s\S]*classList\.toggle\("hidden",\s*!single\)/.test(corpus),
  "Language Takeaway spelling button should only be shown for a single English word."
);

assert(
  /\.language-takeaway-actions-left\s+\.language-takeaway-spelling-btn\.hidden\s*\{[\s\S]*display:\s*none\s*!important/.test(styles),
  "Final compact spelling button CSS must not override the hidden state in sentence mode."
);

console.log("Language Takeaway spelling button visibility checks passed.");
