import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../web/static/app.js", import.meta.url), "utf8");
const css = await readFile(new URL("../web/static/styles.css", import.meta.url), "utf8");

test("P3 bank picker renders partial and completed practice state", () => {
  const renderer = app.match(/function p3BankCardPreviewHtml\(entry\)[\s\S]*?\n}/)?.[0] || "";
  assert.ok(renderer, "expected the P3 bank card preview renderer");
  assert.match(renderer, /practice_completed_round_count/);
  assert.match(renderer, /practice_round_count/);
  assert.match(renderer, /practice_is_complete/);
  assert.match(renderer, /p3-bank-picker-card--partial/);
  assert.match(renderer, /p3-bank-picker-card--complete/);
  assert.match(renderer, /\u5df2\u7ec3/);
  assert.match(renderer, /\u5df2\u5b8c\u6210/);
  assert.match(renderer, /tabindex="0"/);
  assert.match(renderer, /role="button"/);
  assert.match(renderer, /data-p3-bank-card/);
});

test("completed P3 bank cards dim without becoming unselectable", () => {
  const completed = css.match(/\.p3-bank-picker-card--complete\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.ok(completed, "expected completed-card styling");
  assert.match(completed, /opacity:/);
  assert.doesNotMatch(completed, /pointer-events\s*:\s*none/);
  assert.doesNotMatch(completed, /display\s*:\s*none/);
  assert.match(css, /\.p3-bank-picker-card--complete:hover[\s\S]*?opacity:\s*1/);
  assert.match(css, /\.p3-bank-picker-card--complete:focus-visible[\s\S]*?opacity:\s*1/);
});

test("P3 bank cards activate from Enter and Space", () => {
  assert.match(app, /p3BankPickerModal"\)\?\.addEventListener\("keydown"/);
  assert.match(app, /event\.key !== "Enter" && event\.key !== " "/);
  assert.match(app, /event\.preventDefault\(\)/);
  assert.match(app, /activateP3BankPickerCard\(cardButton\)/);
});

test("successful P3 scoring invalidates cached corpus progress", () => {
  assert.match(app, /function invalidateP3BankPracticeProgress\(attempt\)/);
  assert.match(app, /invalidateP3BankPracticeProgress\(scored\)/);
  assert.match(app, /invalidateP3BankPracticeProgress\(attempt\)/);
});
