import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../web/static/app.js", import.meta.url), "utf8");

test("completed report navigation makes the report's part visible", () => {
  const handler = source.match(/function openSpeakingScoreCompleteReport\(\)[\s\S]*?\n}/)?.[0] || "";
  assert.ok(handler, "expected the completed speaking report navigation handler");
  assert.match(handler, /state\.speakingReportFilter\s*=\s*reportPart/);
});

test("history rendering reveals the active report card", () => {
  const renderer = source.match(/function renderHistoryList\(items, options = \{\}\)[\s\S]*?\n}/)?.[0] || "";
  assert.ok(renderer, "expected the speaking history renderer");
  assert.match(renderer, /scrollIntoView\(\{\s*block:\s*"nearest",\s*inline:\s*"nearest"/);
});
