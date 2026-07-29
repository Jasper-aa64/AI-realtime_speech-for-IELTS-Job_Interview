const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const appSource = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const corpusSource = fs.readFileSync(path.join(root, "web/static/corpus-takeaway.js"), "utf8");

const materialStart = corpusSource.indexOf("async function p3CorpusPeekMaterialForTurn");
const materialEnd = corpusSource.indexOf("let p3CorpusPeekRequestSeq", materialStart);
assert(materialStart >= 0 && materialEnd > materialStart, "p3CorpusPeekMaterialForTurn should be present.");
const materialSource = corpusSource.slice(materialStart, materialEnd);

assert.match(
  materialSource,
  /const payload = await fetchP2BankP3Payload\(p2QuestionId\);/,
  "Fixed-bank P3 peek should reuse the P2/P3 bank corpus cache instead of issuing a cold single-card GET.",
);

assert.doesNotMatch(
  materialSource,
  /api\(`\/api\/p3-bank-corpus\/\$\{encodeURIComponent\(p2QuestionId\)\}`\)/,
  "Fixed-bank P3 peek must not bypass the cache with a direct /api/p3-bank-corpus GET.",
);

assert.match(
  corpusSource,
  /let p3CorpusPeekPrefetch = new Map\(\);/,
  "P3 peek prefetch cache should be keyed by turn, not a single overwritten promise.",
);

assert.match(
  corpusSource,
  /function prefetchP3CorpusPeekMaterialsForAttempt\(attempt = state\.attempt\)/,
  "P3 should expose an attempt-level peek prefetch helper.",
);

assert.match(
  corpusSource,
  /prefetchP3CorpusPeekMaterialsForAttempt,/,
  "Attempt-level P3 peek prefetch helper should be exported by corpusTakeawayController.",
);

assert.match(
  appSource,
  /prefetchAllMainExaminerTts\(attempt\);\s*\n\s*prefetchP3CorpusPeekMaterialsForAttempt\(attempt\);/,
  "P3 attempt start should prefetch all fixed-bank peek material together with examiner audio.",
);

console.log("P3 corpus peek prefetch regression checks passed.");
