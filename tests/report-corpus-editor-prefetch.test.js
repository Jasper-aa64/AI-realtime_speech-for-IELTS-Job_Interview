const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const index = fs.readFileSync(path.join(root, "web/static/index.html"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

assert(
  /function warmReportCorpusEditing\(\)[\s\S]*prefetchCorpusEditor\(token\)/.test(app),
  "Report detail should have a dedicated corpus-editor warmup helper."
);

assert(
  /const buttons = Array\.from\(document\.querySelectorAll\("#detailPanel \[data-edit-turn-corpus\]"\)\)/.test(app),
  "Report corpus warmup should only scan edit buttons inside the active detail panel."
);

assert(
  /buttons\.some\(\(button\) => \(button\.dataset\.corpusKind \|\| ""\) === "p1"\)[\s\S]*prefetchP1Corpus\(token\)/.test(app)
    && /buttons\.some\(\(button\) => \/\^p2|p3_bank|p2_corpus_p3\/\.test\(button\.dataset\.corpusKind \|\| ""\)\)[\s\S]*prefetchP2Corpus\(token\)/.test(app),
  "Report corpus warmup should prefetch the matching P1/P2 corpus data."
);

assert(
  /button\.addEventListener\("pointerenter", warmReportCorpusEditing, \{ once: true \}\)/.test(app)
    && /button\.addEventListener\("focus", warmReportCorpusEditing, \{ once: true \}\)/.test(app),
  "Report corpus edit buttons should warm the editor on pointer and keyboard approach."
);

assert(
  /warmReportCorpusEditing\(\);\s*\n\s*refreshReportCorpusButtonStates\(\);/.test(app),
  "Report detail render should start corpus editor warmup before saved-state network refresh."
);

assert(
  /<link rel="preload" href="https:\/\/cdn\.jsdelivr\.net\/npm\/vditor\/dist\/index\.min\.js" as="script">/.test(index),
  "Vditor script should be preloaded so first corpus editor open does not wait on script discovery."
);

console.log("Report corpus editor prefetch checks passed.");
