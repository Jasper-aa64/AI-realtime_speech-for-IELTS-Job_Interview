import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../web/static/corpus-takeaway.js", import.meta.url), "utf8");
const context = { window: {} };
vm.runInNewContext(source, context, { filename: "corpus-takeaway.js" });

test("Brainstorm copy includes four-space-indented cue requirements and idea", () => {
  const formatBlock = context.window.IELTSCorpusTakeaway.formatP2BrainstormCopyBlock;
  assert.equal(typeof formatBlock, "function");

  assert.equal(
    formatBlock({
      index: "1",
      stem: "Describe a company you admire",
      bullets: ["what company it is", "how you know it", "what it does"],
      rounding: "And explain why you admire it",
      idea: "Use the local coffee shop story",
    }),
    [
      "1. Describe a company you admire",
      "    - what company it is - how you know it - what it does  And explain why you admire it",
      "    灵感：Use the local coffee shop story",
    ].join("\n"),
  );
});
