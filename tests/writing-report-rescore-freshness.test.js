const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web", "static", "app.js"), "utf8");

const detailFetchStart = app.indexOf("function writingReportDetailEpoch(entryId)");
const detailFetchEnd = app.indexOf("function isWritingEntryScored", detailFetchStart);
assert(detailFetchStart >= 0 && detailFetchEnd > detailFetchStart,
  "Writing report detail fetch should support an explicit fresh-read mode.");
const detailFetchSource = app.slice(detailFetchStart, detailFetchEnd);

let resolveStale;
let resolveFresh;
const staleResponse = new Promise((resolve) => { resolveStale = resolve; });
const freshResponse = new Promise((resolve) => { resolveFresh = resolve; });
const sandbox = {
  state: {
    writing: {
      reportDetailCache: new Map(),
      reportDetailPromises: new Map(),
      reportDetailEpochs: new Map(),
    },
  },
  encodeURIComponent,
  Date,
  api: (requestPath) => requestPath.includes("cache_bust=") ? freshResponse : staleResponse,
};
vm.runInNewContext(detailFetchSource, sandbox);

(async () => {
  const staleRequest = sandbox.fetchWritingReportDetail("entry-1");
  const freshRequest = sandbox.fetchWritingReportDetail("entry-1", { force: true });
  const freshEntry = { id: "entry-1", score: { overall_band: 7.5 } };
  resolveFresh(freshEntry);
  assert.strictEqual(await freshRequest, freshEntry, "The fresh score result should be accepted.");

  resolveStale({ id: "entry-1", score: { overall_band: 8 } });
  const staleResult = await staleRequest;
  assert.strictEqual(staleResult.score.overall_band, 7.5,
    "A detail request started before re-score completion must resolve to the newer score, not overwrite it.");
  assert.strictEqual(sandbox.state.writing.reportDetailCache.get("entry-1").score.overall_band, 7.5,
    "The report-detail cache must retain the freshly scored Band after a late stale response.");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

const completionOpenStart = app.indexOf("async function openWritingScoreCompleteReport()");
const completionOpenEnd = app.indexOf("function clearWritingScorePolling", completionOpenStart);
assert(completionOpenStart >= 0 && completionOpenEnd > completionOpenStart,
  "Opening a completed writing score should asynchronously revalidate the report.");
const completionOpenSource = app.slice(completionOpenStart, completionOpenEnd);

assert.match(
  completionOpenSource,
  /await fetchWritingReportDetail\(entry\.id, \{ force: true \}\)/,
  "The completion action must revalidate its exact entry, rather than trusting an old rail/detail cache.",
);
assert.match(
  completionOpenSource,
  /renderVisibleWritingReport\(freshEntry\)/,
  "The freshly revalidated score must be rendered immediately when the same report remains active.",
);

console.log("Writing report rescore freshness checks passed.");
