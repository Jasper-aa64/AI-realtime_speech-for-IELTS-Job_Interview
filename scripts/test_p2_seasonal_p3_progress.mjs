import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const corpus = await readFile(new URL("../web/static/corpus-takeaway.js", import.meta.url), "utf8");
const css = await readFile(new URL("../web/static/styles.css", import.meta.url), "utf8");

test("P2 seasonal card derives P3 follow-up progress from the bank payload counts", () => {
  // The counts come straight from the backend p2_topic_card_payload, so the card
  // must read p3_follow_up_count / p3_follow_up_saved_count rather than re-deriving.
  assert.match(corpus, /Number\(item\.p3_follow_up_count\)/);
  assert.match(corpus, /Number\(item\.p3_follow_up_saved_count\)/);
  // saved is clamped to the total so a stale/over-count can never exceed 100%.
  assert.match(corpus, /Math\.min\(Number\(item\.p3_follow_up_saved_count\) \|\| 0, p3Total\)/);
  assert.match(corpus, /p3Total \? Math\.round\(\(p3Saved \/ p3Total\) \* 100\) : 0/);
});

test("P2 seasonal card renders a P3 progress bar like the P1 topic progress", () => {
  const cardRenderer = corpus.match(/const cardHtml = visibleCurrentCards\.map[\s\S]*?\}\)\.join\(""\);/)?.[0] || "";
  assert.ok(cardRenderer, "expected the seasonal card renderer block");
  // Only render the bar when the cue card actually has P3 follow-ups.
  assert.match(cardRenderer, /\$\{p3Total > 0 \?/);
  assert.match(cardRenderer, /class="p2-seasonal-p3-progress" data-progress="\$\{p3Progress\}"/);
  assert.match(cardRenderer, /class="p2-seasonal-p3-progress-track"><span style="width: \$\{p3Progress\}%">/);
  assert.match(cardRenderer, /class="p2-seasonal-p3-progress-count">\$\{p3Saved\}\/\$\{p3Total\}/);
  // accessible label mirrors the saved/total figure.
  assert.match(cardRenderer, /aria-label="P3 追问完成进度 \$\{p3Saved\}\/\$\{p3Total\}"/);
});

test("P2 P3 progress bar is styled and keyed to the per-category accent", () => {
  const track = css.match(/\.p2-seasonal-p3-progress-track\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.ok(track, "expected the progress track styling");
  const fill = css.match(/\.p2-seasonal-p3-progress-track > span\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.match(fill, /var\(--cat-color/);
  assert.match(fill, /transition: width/);
  // 100% gets a check affordance, like the P1 "全部" state.
  assert.match(css, /\.p2-seasonal-p3-progress\[data-progress="100"\] \.p2-seasonal-p3-progress-count::after/);
  // dark theme adjusts the track background, matching the P1 dark progress treatment.
  assert.match(css, /body\.theme-dark \.p2-seasonal-p3-progress-track/);
});
