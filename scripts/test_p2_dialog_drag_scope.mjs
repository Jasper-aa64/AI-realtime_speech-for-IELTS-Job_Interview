import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../web/static/app.js", import.meta.url), "utf8");

test("dialog dragging is not bound to the P3 corpus window", () => {
  const bindings = source.match(/\[\s*"p2CorpusDialog"[\s\S]*?\]\.forEach\(bindP2DialogDrag\);/)?.[0] || "";
  assert.ok(bindings, "expected the P2 drag binding list");
  assert.doesNotMatch(bindings, /p3CorpusPeekDialog/);
});

test("clickable P2 editor titles cannot start a drag", () => {
  const dragStart = source.match(/dialog\.addEventListener\("pointerdown"[\s\S]*?event\.preventDefault\(\);\s*}\);/)?.[0] || "";
  assert.ok(dragStart, "expected the dialog pointerdown handler");
  assert.match(dragStart, /p2-corpus-title-cue-trigger|\[role=["']?button/);
});
