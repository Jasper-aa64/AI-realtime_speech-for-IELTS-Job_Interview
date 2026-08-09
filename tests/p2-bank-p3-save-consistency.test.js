const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const corpusSource = fs.readFileSync(path.join(root, "web", "static", "corpus-takeaway.js"), "utf8");
const markdownEditorSource = fs.readFileSync(path.join(root, "web", "static", "corpus-markdown-editor.js"), "utf8");
const appSource = fs.readFileSync(path.join(root, "web", "static", "app.js"), "utf8");

const saveStart = corpusSource.indexOf("async function saveP2BankP3Entries");
const saveEnd = corpusSource.indexOf("document.addEventListener(\"click\"", saveStart);
assert(saveStart >= 0 && saveEnd > saveStart, "P3 bank save function should exist");
const saveBlock = corpusSource.slice(saveStart, saveEnd);
assert.match(saveBlock, /api\(`\/api\/p3-bank-corpus\/\$\{encodeURIComponent\(questionId\)\}`/);
assert.match(saveBlock, /method:\s*"PUT"/);
assert.doesNotMatch(saveBlock, /Promise\.all\(drafts\.map/);

const closeStart = corpusSource.indexOf("async function saveAndCloseP2CorpusP3Editor");
const closeEnd = corpusSource.indexOf("async function saveP2BankP3Entries", closeStart);
const closeBlock = corpusSource.slice(closeStart, closeEnd);
assert.match(closeBlock, /await saveP2BankP3Entries\(\{ entry, closeOnSuccess: true \}\)/);
assert.doesNotMatch(closeBlock, /closeP2CorpusP3Editor\(\);\s*saveP2BankP3Entries/);
assert.match(
  closeBlock,
  /p2BankP3ItemsSignature\(entry\.items\)\s*===\s*entry\._loadedSignature/,
  "Closing an untouched P3 bank editor should skip the PUT entirely.",
);

const syncStart = corpusSource.indexOf("function syncActiveP2BankP3Draft");
const syncEnd = corpusSource.indexOf("function p2BankP3ItemStatus", syncStart);
assert(syncStart >= 0 && syncEnd > syncStart, "P3 bank draft sync should exist");
const syncBlock = corpusSource.slice(syncStart, syncEnd);
assert.match(
  syncBlock,
  /return\s+previousText\s*!==\s*nextText/,
  "Draft sync should report whether the current follow-up changed.",
);

assert.match(
  markdownEditorSource,
  /new Event\("corpusmarkdowninput",\s*\{\s*bubbles:\s*true\s*\}\)/,
  "The live markdown editor should expose a change event for P3 status updates.",
);
assert.match(
  markdownEditorSource,
  /pre\[contenteditable="true"\][\s\S]*?addEventListener\("input"/,
  "The Vditor editable surface should bridge native typing to the corpus change event.",
);
assert.match(
  markdownEditorSource,
  /presenceOnly:\s*true/,
  "Native editor input should publish immediate content-presence updates without overwriting markdown.",
);
assert.match(
  markdownEditorSource,
  /frame\?\.addEventListener\("input",\s*syncNativeCorpusMarkdownInput,\s*true\)/,
  "The Vditor frame should capture native input before Vditor stops it during reconciliation.",
);
assert.match(
  markdownEditorSource,
  /new MutationObserver/,
  "The P3 editor should observe Vditor DOM edits when the editor swallows native input events.",
);
assert.match(
  corpusSource,
  /addEventListener\("corpusmarkdowninput"/,
  "The P3 editor should listen for live markdown changes.",
);
assert.match(
  corpusSource,
  /function syncP2BankP3SelectedItemStatus/,
  "The P3 editor should update only the selected question status while typing.",
);
assert.match(
  corpusSource,
  /event\.detail\?\.presenceOnly/,
  "The P3 editor should apply native content-presence updates immediately.",
);
assert.match(
  corpusSource,
  /\$\("p2CorpusP3Dialog"\)\?\.addEventListener\("input"/,
  "Native Vditor input should update the current P3 question status immediately.",
);

const revalidateStart = corpusSource.indexOf("function maybeApplyFreshP2BankP3");
const revalidateEnd = corpusSource.indexOf("// Warm the whole visible list", revalidateStart);
assert(revalidateStart >= 0 && revalidateEnd > revalidateStart, "P3 revalidation guard should exist");
const revalidateBlock = corpusSource.slice(revalidateStart, revalidateEnd);
assert.match(revalidateBlock, /selectedDirty/);
assert.match(revalidateBlock, /switchedDraftDirty/);
assert.match(revalidateBlock, /if \(selectedDirty \|\| switchedDraftDirty\)/);
assert.match(revalidateBlock, /active\._loadedSignature\s*=\s*freshSignature/);

const applyStart = appSource.indexOf("function applyP2CorpusPayload");
const applyEnd = appSource.indexOf("async function ensureP2CorpusLoaded", applyStart);
assert(applyStart >= 0 && applyEnd > applyStart, "P2 corpus payload application should exist");
const applyBlock = appSource.slice(applyStart, applyEnd);
assert.match(applyBlock, /state\.p2Corpus\.saving/);
assert.match(applyBlock, /savingPromise/);

console.log("p2 bank P3 save consistency checks passed");
