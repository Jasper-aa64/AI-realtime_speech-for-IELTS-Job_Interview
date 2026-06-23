import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../web/static/app.js", import.meta.url), "utf8");
const corpus = await readFile(new URL("../web/static/corpus-takeaway.js", import.meta.url), "utf8");

// Regression guard for the "P1 corpus saved entries vanish after a while" bug:
// a GET that snapshotted the server before a save would resolve afterward and
// wholesale-overwrite freshly-saved topics. The fix is a monotonic mutationSeq
// generation token: GETs are stamped at issue-time and stale payloads are
// discarded + refetched instead of applied.

test("p1Corpus state carries a mutationSeq generation counter", () => {
  const block = app.match(/p1Corpus:\s*\{[\s\S]*?\n  \}/)?.[0] || "";
  assert.ok(block, "expected the p1Corpus state initializer");
  assert.match(block, /mutationSeq:\s*0/);
});

test("fetchP1CorpusPayload stamps the issue-time generation onto the payload", () => {
  const fn = app.match(/async function fetchP1CorpusPayload\([\s\S]*?\n}/)?.[0] || "";
  assert.ok(fn, "expected fetchP1CorpusPayload");
  assert.match(fn, /const fetchSeq = state\.p1Corpus\.mutationSeq/);
  assert.match(fn, /payload\.__fetchSeq = fetchSeq/);
});

test("applyP1CorpusPayload discards a stale snapshot instead of clobbering topics", () => {
  const fn = app.match(/function applyP1CorpusPayload\([\s\S]*?\n}/)?.[0] || "";
  assert.ok(fn, "expected applyP1CorpusPayload");
  assert.match(fn, /__fetchSeq < state\.p1Corpus\.mutationSeq/);
  // Stale path must refetch (and return) BEFORE the topics-replacing assignment.
  const guardIndex = fn.indexOf("__fetchSeq < state.p1Corpus.mutationSeq");
  const refetchIndex = fn.indexOf("fetchP1CorpusPayload().then(applyP1CorpusPayload)");
  const clobberIndex = fn.indexOf("state.p1Corpus.topics = payload.topics");
  assert.ok(guardIndex > -1 && refetchIndex > guardIndex, "expected a refetch on stale payload");
  assert.ok(refetchIndex < clobberIndex, "stale guard must short-circuit before overwriting topics");
});

test("saving a P1 corpus entry bumps the generation right after the api save", () => {
  const saveIndex = corpus.indexOf('const saved = await api("/api/p1-corpus", payload);');
  assert.ok(saveIndex > -1, "expected the persisting api call in saveP1CorpusEntry");
  // The very next mutationSeq bump after the save call is the one we added.
  const bumpIndex = corpus.indexOf(
    "state.p1Corpus.mutationSeq = (state.p1Corpus.mutationSeq || 0) + 1",
    saveIndex,
  );
  const nextLoadingNull = corpus.indexOf("state.p1Corpus.loadingPromise = null", saveIndex);
  assert.ok(bumpIndex > saveIndex, "mutationSeq must bump after the save succeeds");
  assert.ok(nextLoadingNull > saveIndex, "the cached GET must be dropped after the save");
  // Both must land before the success-path render so a stale GET can't slip in.
  const renderIndex = corpus.indexOf("renderP1CorpusTopics();", saveIndex);
  assert.ok(bumpIndex < renderIndex && nextLoadingNull < renderIndex);
});

test("clearing a P1 corpus entry also bumps the generation", () => {
  const fn = corpus.match(/function markP1CorpusEntryCleared\([\s\S]*?\n    \}/)?.[0] || "";
  assert.ok(fn, "expected markP1CorpusEntryCleared");
  assert.match(fn, /state\.p1Corpus\.mutationSeq = \(state\.p1Corpus\.mutationSeq \|\| 0\) \+ 1/);
  assert.match(fn, /state\.p1Corpus\.loadingPromise = null/);
});
