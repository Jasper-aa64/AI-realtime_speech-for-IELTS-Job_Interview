const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

assert(
  /function writingParagraphReviewItems\(answerParagraphs, reviews\)/.test(app),
  "Writing reports should reconcile saved review rows against the current essay paragraphs."
);

assert(
  /return answerParagraphs\.map\(\(paragraph, index\) => \{[\s\S]*learner: paragraph/.test(app),
  "The current saved essay must be the source of truth for every rendered paragraph."
);

assert(
  /const items = writingParagraphReviewItems\(answerParagraphs, reviews\);/.test(app),
  "The report renderer should use the current-paragraph reconciliation helper."
);

assert(
  !/const items = reviews\.length \? reviews : answerParagraphs\.map/.test(app),
  "A stale, shorter paragraph_reviews array must not truncate the current essay."
);

console.log("Writing report current paragraph checks passed.");
