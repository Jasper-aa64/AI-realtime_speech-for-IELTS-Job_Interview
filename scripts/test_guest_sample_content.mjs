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
  // P1: the FULL topic bank, but only "What is your full name?" is pre-filled.
  assert.ok(Array.isArray(S.p1Corpus?.topics) && S.p1Corpus.topics.length >= 5, "P1 full topic bank");
  const filledP1 = S.p1Corpus.topics.flatMap((t) => (t.questions || []).filter((q) => q.corpus_text));
  assert.equal(filledP1.length, 1, "only one P1 question carries default content");
  assert.match(filledP1[0].question, /full name/i);
  assert.equal(S.p1Corpus.saved_count, 1);
  // P2: ALL category groups shown, only 人物 carries one material item; all cards.
  assert.ok(Array.isArray(S.p2Corpus?.categories) && S.p2Corpus.categories.length >= 3, "all P2 category groups");
  const p2WithItems = S.p2Corpus.categories.filter((c) => (c.items || []).length);
  assert.equal(p2WithItems.length, 1, "only one P2 category seeded with material");
  assert.match(p2WithItems[0].label, /人物/);
  assert.equal(p2WithItems[0].items.length, 1, "人物 has exactly one material");
  assert.ok(Array.isArray(S.p2Corpus?.current_part2_cards) && S.p2Corpus.current_part2_cards.length >= 1);
});

test("language takeaway seed is 3 expression-replacements + 3 plain phrases", () => {
  const S = loadSeed();
  const isRep = (t) => /→|->|=>|—>/.test(t || "");
  assert.equal(S.languageTakeaways.filter((i) => isRep(i.source_text)).length, 3, "3 replacements");
  assert.equal(S.languageTakeaways.filter((i) => !isRep(i.source_text)).length, 3, "3 phrases");
});

test("seeded data is NOT flagged 示例 — only the speaking report is", () => {
  const S = loadSeed();
  for (const it of [...S.languageTakeaways, ...S.writingTakeaways]) {
    assert.ok(!("is_sample" in it), "takeaways must be plain defaults, not samples");
  }
  for (const t of S.p1Corpus.topics) assert.ok(!t.is_sample, "p1 topics are defaults");
  // The speaking + writing reports carry real detail payloads and is_sample.
  assert.ok(Array.isArray(S.history) && S.history.length >= 1);
  for (const h of S.history) {
    assert.equal(h.is_sample, true, "history report must be flagged is_sample");
    assert.ok(h.detail && Array.isArray(h.detail.turns) && h.detail.turns.length, "report needs real turns");
    assert.ok(h.detail.ielts_score, "report needs ielts_score for renderDetail");
  }
  assert.ok(Array.isArray(S.writingReports) && S.writingReports.length >= 1, "a writing report sample exists");
  for (const w of S.writingReports) {
    assert.equal(w.is_sample, true, "writing report flagged is_sample");
    assert.ok(w.detail && w.detail.score, "writing report needs score detail for the real renderer");
  }
});

test("guest gates: P1/P2 corpus, takeaway edits, writing bank, report edits, profile", () => {
  // P1/P2 corpus screens: any content click is intercepted to the login dialog.
  assert.match(corpus, /function installGuestCorpusGuard\(containerId, reason\)/);
  assert.match(corpus, /installGuestCorpusGuard\("p1CorpusTopics"/);
  assert.match(corpus, /installGuestCorpusGuard\("p2CorpusTopics"/);
  // Takeaway: review is allowed, but add/edit/expression-replacement are gated.
  assert.match(corpus, /function guestBlockTakeawayEdit\(reason\)/);
  assert.match(corpus, /openNewTakeawayEditor\(kind = "language"\) \{\s*\n\s*if \(guestBlockTakeawayEdit/);
  assert.match(corpus, /openTakeawayEditor\(kind, entryId\) \{\s*\n\s*if \(guestBlockTakeawayEdit/);
  assert.match(corpus, /openExpressionReplacementDialog\(kind = "writing"\) \{\s*\n\s*if \(guestBlockTakeawayEdit/);
  // Writing question bank: guests get the prompt instead of the picker.
  assert.match(app, /function openWritingPromptPicker[\s\S]{0,160}?promptGuestLogin\("登录后才能打开写作题库并选题。"\)/);
  // Writing report edit + speaking report 编辑语料库 are gated.
  assert.match(app, /promptGuestLogin\("登录后才能编辑作文并重新生成报告。"\)/);
  assert.match(app, /promptGuestLogin\("登录后才能编辑语料库并保存到你的账号。"\)/);
  // Profile: logout button doubles as 登录 and entry pops the login prompt.
  assert.match(app, /logoutBtn\.textContent = "登录"/);
  assert.match(app, /logoutBtn\.textContent = t\("account\.logout"\)/);
  assert.match(app, /if \(!state\.account\.authenticated\) \{\s*\n\s*switchView\("login"[\s\S]{0,80}?return;/);
  assert.match(app, /loadAccountProfile[\s\S]{0,400}?promptGuestLogin\("登录后即可管理账号资料/);
});

test("the writing report sample renders through the REAL writing pipeline, badged 示例", () => {
  assert.match(app, /function seedGuestWritingReports\(\)/);
  assert.match(app, /state\.writing\.reportDetailCache\.set\(entry\.id, entry\.detail\)/);
  assert.match(app, /renderWritingReports\(state\.writing\.reportEntries\)/);
  assert.match(app, /if \(!seedGuestWritingReports\(\)\) \{/);
  assert.match(app, /entry\.is_sample \? ` <span class="report-sample-badge">示例<\/span>`/);
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
