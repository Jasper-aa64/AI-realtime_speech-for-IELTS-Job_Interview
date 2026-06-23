import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const corpus = await readFile(new URL("../web/static/corpus-takeaway.js", import.meta.url), "utf8");
const app = await readFile(new URL("../web/static/app.js", import.meta.url), "utf8");
const router = await readFile(new URL("../web/static/view-router.js", import.meta.url), "utf8");
const css = await readFile(new URL("../web/static/styles.css", import.meta.url), "utf8");
const html = await readFile(new URL("../web/static/index.html", import.meta.url), "utf8");

test("Brainstorm cue launches the selected P2 question in a new tab", () => {
  assert.match(corpus, /data-p2-brainstorm-practice=/);
  assert.match(corpus, /function openP2BankPracticeInNewTab\(cueId/);
  assert.match(corpus, /searchParams\.set\("view", "p2"\)/);
  assert.match(corpus, /searchParams\.set\("p2_cue_id", normalizedCueId\)/);
  assert.match(corpus, /searchParams\.set\("autostart", "1"\)/);
  assert.match(corpus, /window\.open\(url\.toString\(\), "_blank", "noopener"\)/);
  assert.match(router, /p2CueId:\s*params\.get\("p2_cue_id"\)/);
  assert.match(router, /autoStartP2:\s*params\.get\("autostart"\) === "1"/);
  assert.match(app, /state\.p2Corpus\.pinnedCueId = route\.p2CueId/);
  assert.match(app, /if \(route\.autoStartP2 && route\.p2CueId\)/);
  assert.match(app, /startPractice\(\)/);
});

test("Brainstorm practice control is a fixed centered circle using a theme-aware inline icon", () => {
  assert.match(corpus, /class="p2-brainstorm-practice-btn"/);
  // Inline SVG (not <img>) so stroke="currentColor" can follow the page theme.
  const btnMarkup = corpus.match(/class="p2-brainstorm-practice-btn"[\s\S]*?<\/button>/)?.[0] || "";
  assert.match(btnMarkup, /<svg[\s\S]*stroke="currentColor"/);
  assert.doesNotMatch(btnMarkup, /<img/);
  const rule = css.match(/\.p2-brainstorm-practice-btn\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.match(rule, /inline-size:\s*30px/);
  assert.match(rule, /block-size:\s*30px/);
  assert.match(rule, /border-radius:\s*50%/);
  assert.match(rule, /display:\s*grid/);
  assert.match(rule, /place-items:\s*center/);
  // currentColor needs an explicit color so the icon adapts in light and dark themes.
  assert.match(rule, /color:\s*var\(--accent\)/);
});

test("Seasonal P2 practice control matches the restrained Brainstorm Lucide button", () => {
  const btnMarkup = corpus.match(/class="p2-seasonal-practice-btn"[\s\S]*?<\/button>/)?.[0] || "";
  assert.match(btnMarkup, /<svg class="p2-seasonal-practice-icon"[\s\S]*?stroke="currentColor"/);
  assert.doesNotMatch(btnMarkup, /<img/);
  const buttonRule = css.match(/\.p2-seasonal-practice-btn\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.match(buttonRule, /background:\s*color-mix\(in srgb, var\(--cat-color, var\(--p2-corpus-accent\)\) 10%, var\(--panel\)\)/);
  assert.match(buttonRule, /border:\s*1px solid color-mix/);
  assert.match(buttonRule, /color:\s*var\(--cat-color, var\(--p2-corpus-accent\)\)/);
  const iconRule = css.match(/\.p2-seasonal-practice-icon\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.match(iconRule, /width:\s*18px/);
  assert.match(iconRule, /height:\s*18px/);
  assert.doesNotMatch(iconRule, /filter:/);
});

test("Brainstorm splits canvas effects: grid on the header, scatter in the body", () => {
  const cardMarkup = corpus.match(/class="p2-topic-card p2-category-entry-card p2-brainstorm-entry-card"[\s\S]*?<\/article>/)?.[0] || "";
  // Grid host lives inside the header strip ("串题灵感 Brainstorm 62/64").
  assert.match(cardMarkup, /<header>[\s\S]*?id="p2BrainstormHeadField"[\s\S]*?<\/header>/);
  // Scatter host lives in the card body, below the header.
  const headerEnd = cardMarkup.indexOf("</header>");
  const particleIndex = cardMarkup.indexOf('class="p2-brainstorm-particles"');
  assert.ok(particleIndex > headerEnd, "scatter host must sit below the header");
  assert.match(cardMarkup, /class="p2-brainstorm-open-card"[\s\S]*?class="p2-brainstorm-particles"/);
  // One reusable renderer, two modes; header gets grid, body gets scatter.
  assert.match(corpus, /function initializeP2BrainstormParticles\(/);
  assert.match(corpus, /function destroyP2BrainstormParticles\(\)/);
  assert.match(corpus, /function createPixelFlowField\(host, mode/);
  assert.match(corpus, /createPixelFlowField\(head, "grid"\)/);
  assert.match(corpus, /createPixelFlowField\(body, "scatter"\)/);
  assert.match(corpus, /function drawGrid\(/);
  assert.match(corpus, /function drawScatter\(/);
  // ResizeObserver-driven canvas that cannot go blank (vs particles.js one-shot).
  assert.match(corpus, /new ResizeObserver/);
  assert.match(corpus, /cancelAnimationFrame/);
  assert.match(corpus, /createElement\("canvas"\)/);
  // particles.js is fully retired — neither the lib nor its globals remain.
  assert.doesNotMatch(corpus, /particlesJS|pJSDom/);
  assert.doesNotMatch(html, /particles\.min\.js/);
  assert.match(css, /\.p2-brainstorm-particles[\s\S]*?z-index:\s*2/);
  const headFieldRule = css.match(/\.p2-brainstorm-head-field\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.match(headFieldRule, /inset:\s*0/);
  const canvasRule = css.match(/\.p2-pixel-flow-canvas\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.match(canvasRule, /inset:\s*0/);
  assert.match(canvasRule, /inline-size:\s*100%/);
  // Header title + count are lifted above the grid canvas.
  assert.match(css, /\.p2-brainstorm-entry-card > header > h3[\s\S]*?z-index:\s*1/);
});

test("Brainstorm header grid stays visible when the canvas script never runs", () => {
  const fallbackRule = css.match(/\.p2-brainstorm-head-field::before\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.match(fallbackRule, /content:\s*""/);
  assert.match(fallbackRule, /position:\s*absolute/);
  assert.match(fallbackRule, /inset:\s*0/);
  assert.match(fallbackRule, /background-image:/);
  assert.match(fallbackRule, /background-size:\s*9px 9px/);
  // Header is a dark "ultracode" bar with a white-flaring shimmer that fades right.
  assert.match(css, /\.p2-brainstorm-entry-card\[data-category="brainstorm"\] > header\s*\{[\s\S]*?background:\s*linear-gradient/);
  assert.match(css, /header > h3\s*\{[\s\S]*?color:\s*#f8fafc\s*!important/);
  // The wave must be column-only (vertical, rightward) — never a (c + r) diagonal.
  assert.match(corpus, /flows RIGHTWARD/);
  assert.match(corpus, /left reads brighter and the right stays softer/);
  assert.match(corpus, /function drawGrid\(t\)\s*\{[\s\S]*?Math\.sin\(c \* 0\.17 - t \* \d/);
  assert.doesNotMatch(corpus, /Math\.sin\(\(c \+ r\)/);
  assert.match(corpus, /pure white at the brightest crest/);
});
