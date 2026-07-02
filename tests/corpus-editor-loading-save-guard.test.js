const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const corpus = fs.readFileSync(path.join(root, "web/static/corpus-takeaway.js"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

assert(
  /prefetchCorpusEditor\(state\.prefetch\.token\)\.catch\(\(\) => \{\}\);[\s\S]*const corpusTakeawayController/.test(app),
  "Corpus markdown editor should start global warmup before corpus/takeaway controller work, not wait for hover."
);

assert(
  /function p1CorpusEditorIsHydrating\(\)[\s\S]*activeEntry\?\._corpusHydrating/.test(corpus),
  "P1 corpus editor should expose a hydrating guard."
);

assert(
  /async function saveAndCloseP1CorpusEditor[\s\S]*if \(p1CorpusEditorIsHydrating\(\) && !corpusText\)[\s\S]*closeP1CorpusEditor\(options\);[\s\S]*return;/.test(corpus),
  "Closing a still-loading P1 editor with blank content must close without saving an empty corpus."
);

assert(
  /async function saveAndCloseP2CorpusEditor[\s\S]*if \(entry\._corpusHydrating && !materialText\)[\s\S]*closeP2CorpusEditor\(\);[\s\S]*return;/.test(corpus),
  "Closing a still-loading P2 editor with blank content must close without saving empty material."
);

assert(
  /async function saveAndCloseP2CorpusP3Editor[\s\S]*if \(entry\._corpusHydrating && !activeText\)[\s\S]*closeP2CorpusP3Editor\(\);[\s\S]*return;/.test(corpus),
  "Closing a still-loading bank P3 editor with blank content must close without saving empty followups."
);

console.log("Corpus editor loading save guard checks passed.");
