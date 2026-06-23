import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../web/static/app.js", import.meta.url), "utf8");
const corpus = await readFile(new URL("../web/static/corpus-takeaway.js", import.meta.url), "utf8");
const samplesSrc = await readFile(new URL("../web/static/assets/guest-samples.js", import.meta.url), "utf8");
const html = await readFile(new URL("../web/static/index.html", import.meta.url), "utf8");
const css = await readFile(new URL("../web/static/styles.css", import.meta.url), "utf8");

test("guest-samples.js publishes a populated fixture under window.IELTSGuestSamples", () => {
  const win = {};
  new Function("window", samplesSrc)(win);
  const S = win.IELTSGuestSamples;
  assert.ok(S, "expected window.IELTSGuestSamples");
  assert.ok(Array.isArray(S.languageTakeaways) && S.languageTakeaways.length >= 3);
  assert.ok(Array.isArray(S.writingTakeaways) && S.writingTakeaways.length >= 3);
  assert.ok(Array.isArray(S.p1Corpus?.topics) && S.p1Corpus.topics.length >= 1);
  assert.ok(Array.isArray(S.history) && S.history.length >= 1);
  // takeaway items carry the bilingual fields the cards render.
  for (const it of S.languageTakeaways) {
    assert.ok(it.source_text && it.chinese_text, "takeaway sample needs source+chinese text");
  }
  // p1 sample topics include filled corpus so the preview is non-empty.
  assert.ok(S.p1Corpus.topics.every((t) => (t.questions || []).some((q) => q.corpus_text)));
});

test("the fixture script loads before the consumers in index.html", () => {
  const iGuest = html.indexOf("guest-samples.js");
  const iCorpus = html.indexOf("corpus-takeaway.js");
  const iApp = html.indexOf("/app.js?");
  assert.ok(iGuest > -1 && iCorpus > -1 && iApp > -1, "all three scripts present");
  assert.ok(iGuest < iCorpus && iGuest < iApp, "guest-samples.js must load first");
});

test("takeaway + P1 guest loaders render the samples and fall back to the notice", () => {
  assert.match(corpus, /function renderGuestTakeawaySamples\(kind\)/);
  assert.match(corpus, /function renderGuestP1CorpusSamples\(\)/);
  assert.match(corpus, /if \(!renderGuestTakeawaySamples\("language"\)\) \{/);
  assert.match(corpus, /if \(!renderGuestTakeawaySamples\("writing"\)\) \{/);
  assert.match(corpus, /if \(!renderGuestP1CorpusSamples\(\)\) \{/);
  // content is explicitly badged as a sample.
  assert.match(corpus, /guest-sample-banner-pill">示例/);
});

test("the takeaway nav dot lights up for guests (both on entry and on boot)", () => {
  assert.match(corpus, /function showGuestTakeawayDot\(kind, count\)/);
  assert.match(corpus, /(languageTakeawayDueDot|writingTakeawayDueDot)/);
  assert.match(app, /function maybeShowGuestTakeawayDots\(\)/);
  assert.match(app, /await loadAccount\(\);\s*\n\s*maybeShowGuestTakeawayDots\(\);/);
  assert.match(app, /setDot\("languageTakeawayDueDot", \(samples\.languageTakeaways \|\| \[\]\)\.length\)/);
});

test("history shows clickable sample report cards with a sample detail", () => {
  assert.match(app, /function renderGuestHistorySamples\(\)/);
  assert.match(app, /function renderGuestHistoryDetail\(item\)/);
  assert.match(app, /if \(!renderGuestHistorySamples\(\)\) \{/);
  assert.match(app, /data-guest-sample-report=/);
  assert.match(app, /这是示例报告/);
});

test("guest sample UI is styled", () => {
  for (const cls of [
    "\\.guest-sample-banner\\s*\\{",
    "\\.guest-sample-grid\\s*\\{",
    "\\.guest-sample-takeaway-card\\b", // used as a descendant selector
    "\\.guest-sample-history-card\\s*\\{",
    "\\.guest-sample-bands\\s*\\{",
  ]) {
    assert.match(css, new RegExp(cls), `expected CSS for ${cls}`);
  }
});
