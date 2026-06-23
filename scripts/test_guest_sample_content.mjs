import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../web/static/app.js", import.meta.url), "utf8");
const corpus = await readFile(new URL("../web/static/corpus-takeaway.js", import.meta.url), "utf8");
const samplesSrc = await readFile(new URL("../web/static/assets/guest-samples.js", import.meta.url), "utf8");
const html = await readFile(new URL("../web/static/index.html", import.meta.url), "utf8");

function loadSeed() {
  const win = {};
  new Function("window", samplesSrc)(win);
  return win.IELTSGuestSamples;
}

test("guest-samples.js publishes default seed in the live payload shapes", () => {
  const S = loadSeed();
  assert.ok(S, "expected window.IELTSGuestSamples");
  // Takeaways are flat arrays of library items {source_text, chinese_text}.
  assert.ok(Array.isArray(S.languageTakeaways) && S.languageTakeaways.length >= 3);
  assert.ok(Array.isArray(S.writingTakeaways) && S.writingTakeaways.length >= 3);
  for (const it of [...S.languageTakeaways, ...S.writingTakeaways]) {
    assert.ok(it.entry_id && it.source_text && it.chinese_text, "takeaway needs id+source+chinese");
  }
  // P1 corpus is a full library payload with filled topics.
  assert.ok(Array.isArray(S.p1Corpus?.topics) && S.p1Corpus.topics.length >= 1);
  assert.ok(S.p1Corpus.topics.every((t) => (t.questions || []).some((q) => q.corpus_text)));
  // P2 corpus is a full library payload with current_part2_cards.
  assert.ok(Array.isArray(S.p2Corpus?.categories), "p2 categories array");
  assert.ok(Array.isArray(S.p2Corpus?.current_part2_cards) && S.p2Corpus.current_part2_cards.length >= 1);
});

test("seeded data is NOT flagged 示例 — only the speaking report is", () => {
  const S = loadSeed();
  for (const it of [...S.languageTakeaways, ...S.writingTakeaways]) {
    assert.ok(!("is_sample" in it), "takeaways must be plain defaults, not samples");
  }
  for (const t of S.p1Corpus.topics) assert.ok(!t.is_sample, "p1 topics are defaults");
  // The history report carries the real report_payload detail and is_sample.
  assert.ok(Array.isArray(S.history) && S.history.length >= 1);
  for (const h of S.history) {
    assert.equal(h.is_sample, true, "history report must be flagged is_sample");
    assert.ok(h.detail && Array.isArray(h.detail.turns) && h.detail.turns.length, "report needs real turns");
    assert.ok(h.detail.ielts_score, "report needs ielts_score for renderDetail");
  }
});

test("the fixture script loads before the consumers in index.html", () => {
  const iGuest = html.indexOf("guest-samples.js");
  const iCorpus = html.indexOf("corpus-takeaway.js");
  const iApp = html.indexOf("/app.js?");
  assert.ok(iGuest > -1 && iCorpus > -1 && iApp > -1, "all three scripts present");
  assert.ok(iGuest < iCorpus && iGuest < iApp, "guest-samples.js must load first");
});

test("takeaway/P1/P2 loaders inject defaults through the REAL render pipeline", () => {
  // Library-shaped seed helpers, fed to the same applyXPayload the auth path uses.
  assert.match(corpus, /function takeawaySeedPayload\(kind\)/);
  assert.match(corpus, /function withTakeawayDefaults\(kind, payload\)/);
  assert.match(corpus, /function p1SeedPayload\(\)/);
  assert.match(corpus, /function p2SeedPayload\(\)/);
  assert.match(corpus, /applyP1CorpusPayload\(p1SeedPayload\(\)\)/);
  assert.match(corpus, /applyP2CorpusPayload\(p2SeedPayload\(\)\)/);
  assert.match(corpus, /applyLanguageTakeawaysPayload\(payload\)/);
  assert.match(corpus, /applyWritingTakeawaysPayload\(payload\)/);
  // Empty real accounts also fall back to the defaults.
  assert.match(corpus, /withTakeawayDefaults\("language", await fetchLanguageTakeawaysPayload\(\)\)/);
  assert.match(corpus, /withTakeawayDefaults\("writing", await fetchWritingTakeawaysPayload\(\)\)/);
  // No hand-drawn sample cards / banners survive.
  assert.doesNotMatch(corpus, /guest-sample-banner/);
  assert.doesNotMatch(corpus, /renderGuestTakeawaySamples/);
  assert.doesNotMatch(corpus, /renderGuestP1CorpusSamples/);
});

test("the takeaway nav dot lights up for guests (both on entry and on boot)", () => {
  assert.match(corpus, /function showGuestTakeawayDot\(kind, count\)/);
  assert.match(corpus, /showGuestTakeawayDot\("language", payload\.count\)/);
  assert.match(corpus, /showGuestTakeawayDot\("writing", payload\.count\)/);
  assert.match(app, /function maybeShowGuestTakeawayDots\(\)/);
  assert.match(app, /await loadAccount\(\);\s*\n\s*maybeShowGuestTakeawayDots\(\);/);
});

test("the demo report renders through the REAL history pipeline, badged 示例", () => {
  // Seed pushes into state.historyItems + historyDetailCache, then renderHistoryList.
  assert.match(app, /function seedGuestHistory\(\)/);
  assert.match(app, /state\.historyDetailCache\.set\(entry\.id, entry\.detail\)/);
  assert.match(app, /renderHistoryList\(state\.historyItems\)/);
  assert.match(app, /if \(!seedGuestHistory\(\)\) \{/);
  // 示例 badge in both the list card and the detail header.
  assert.match(app, /item\.is_sample \? `<span class="report-sample-badge">示例<\/span>`/);
  assert.match(app, /attempt\.is_sample \? ` <span class="report-sample-badge">示例<\/span>`/);
  // No hand-drawn guest report UI.
  assert.doesNotMatch(app, /renderGuestHistorySamples/);
  assert.doesNotMatch(app, /renderGuestHistoryDetail/);
});
