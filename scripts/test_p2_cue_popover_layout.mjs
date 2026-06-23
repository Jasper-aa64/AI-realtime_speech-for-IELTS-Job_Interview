import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const css = await readFile(new URL("../web/static/styles.css", import.meta.url), "utf8");

test("P2 bank-body cue popover is 335px wide and sits just below the title", () => {
  const block = css.match(/\.p2-corpus-dialog-card\.is-bank-editor \.p2-corpus-title-cue-detail\.p2-brainstorm-cue-detail\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.ok(block, "expected the final P2 cue popover override");
  assert.match(block, /top:\s*calc\(100% \+ 8px\)\s*!important/);
  assert.match(block, /width:\s*min\(335px,/);
  assert.match(block, /max-width:\s*335px\s*!important/);
  assert.match(block, /min-width:\s*min\(300px,/);
});

test("P2 bank-body Markdown uses the standard corpus editor type size", () => {
  const block = css.match(/\.p2-corpus-dialog-card\.is-bank-editor #p2CorpusText,[\s\S]*?\.p2-corpus-dialog-card\.is-bank-editor \.vditor-reset p\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.ok(block, "expected the final P2 Markdown editor override");
  assert.match(block, /font-size:\s*18px\s*!important/);
  assert.match(block, /line-height:\s*1\.62\s*!important/);
});
