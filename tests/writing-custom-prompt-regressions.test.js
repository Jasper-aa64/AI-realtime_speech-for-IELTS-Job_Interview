const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const picker = fs.readFileSync(path.join(root, "web/static/writing-prompt-picker.js"), "utf8");

function sliceBetween(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `${startMarker}..${endMarker} slice must exist.`);
  return source.slice(start, end);
}

// ── Goal A: Task 1 = tag filters, Task 2 = 问法 filters, source row only 3 ──

const renderTypeFiltersBody = sliceBetween(
  picker,
  "function renderTypeFilters(taskType) {",
  "function clearTypeFilters()",
);
const renderPatternFiltersBody = sliceBetween(
  picker,
  "function renderPatternFilters(taskType) {",
  "async function chooseRandom",
);

// The source row renders exactly the three sources and nothing else.
assert.match(
  picker,
  /\["cambridge", "reported", "custom"\]\.map/,
  "The source row must be exactly 剑雅真题 / 中国考区机经 / 自定义练习.",
);

// Task 1 keeps its own tag (chart-type) filters, computed per current source.
assert.match(
  renderTypeFiltersBody,
  /if \(taskType !== "task1_academic"\) \{[\s\S]{0,300}return;[\s\S]{0,300}\}[\s\S]{0,300}Task 1 keeps its own chart-type filters/,
  "renderTypeFilters must keep the Task 1 tag-filter branch.",
);
assert.match(
  renderTypeFiltersBody,
  /const basePrompts = pickerPromptsForSource\(taskType, selectedSource\);[\s\S]{0,200}const categories = inferWritingCategories\(basePrompts\);/,
  "Task 1 tags must be computed from the current source's Task 1 prompts.",
);
assert.match(
  renderTypeFiltersBody,
  /if \(selected && !categories\.some\([\s\S]{0,400}pickerCategoryFilters\[taskType\] = "";/,
  "A stale Task 1 tag from another source must reset to 全部.",
);

// Task 2 has NO 题型 row (全部类型/利弊类/…) — it filters by 问法 only.
const task2TypeBranch = renderTypeFiltersBody.slice(
  renderTypeFiltersBody.indexOf("if (!legacyTarget) return;"),
);
assert.ok(task2TypeBranch.length > 0, "renderTypeFilters must have a Task 2 branch.");
assert.doesNotMatch(
  task2TypeBranch,
  /data-writing-prompt-category=/,
  "The Task 2 branch must not render any category (题型) chips.",
);
assert.doesNotMatch(
  task2TypeBranch,
  /全部类型/,
  "The Task 2 branch must never render the 全部类型 chip.",
);
assert.match(
  task2TypeBranch,
  /legacyTarget\.classList\.add\("hidden"\)/,
  "The Task 2 branch must clear and hide the 题型 row.",
);

// Task 2 问法 menu is computed strictly from the CURRENT source (custom included).
assert.match(
  renderPatternFiltersBody,
  /const basePrompts = pickerPromptsForSource\(taskType, selectedSource\);[\s\S]{0,200}const patterns = inferWritingPromptPatterns\(basePrompts\);/,
  "Task 2 问法 tags must be computed per current source, custom included.",
);
assert.match(
  renderPatternFiltersBody,
  /if \(selected && !patterns\.some\([\s\S]{0,400}pickerPromptPatternFilters\[taskType\] = "";/,
  "A stale 问法 from another source must reset to 全部问法.",
);
assert.match(
  renderPatternFiltersBody,
  /data-writing-prompt-pattern=/,
  "The Task 2 问法 menu must render pattern options.",
);

// Switching sources resets both filters.
assert.match(
  picker,
  /pickerSourceFilters\[taskType\] = button\.dataset\.writingPromptSource \|\| "cambridge";[\s\S]{0,200}pickerCategoryFilters\[taskType\] = "";[\s\S]{0,200}pickerPromptPatternFilters\[taskType\] = "";/,
  "Switching sources must reset the tag and 问法 selections.",
);

// ── Goal B: custom prompts are plain text ───────────────────────────────────

const customPreviewBody = sliceBetween(
  picker,
  "function customPromptPreviewHtml(prompt) {",
  "function customCreateCardHtml",
);
assert.doesNotMatch(
  customPreviewBody,
  /renderMarkdown\(/,
  "Custom prompt preview must never render Markdown — **text** stays literal.",
);
assert.match(
  customPreviewBody,
  /escapeHtml\(text\)\.replace\(\/\\n\/g, "<br>"\)/,
  "Custom prompt preview must escape the raw text and keep newlines.",
);

// Task 2 card previews strip the repeating "Give reasons…" boilerplate.
assert.ok(
  picker.includes("WRITING_PROMPT_GIVE_REASONS_BOILERPLATE"),
  "The picker must strip the repeating Give reasons… boilerplate from card previews.",
);
assert.match(
  picker,
  /function promptPreviewHtml\(prompt\) \{[\s\S]{0,200}stripWritingPromptBoilerplate\(String\(prompt\.prompt \|\| ""\)\)/,
  "Bank Task 2 card previews must strip the boilerplate too.",
);

assert.match(
  app,
  /prompt: promptMarkdown/,
  "The custom prompt save payload must use the plain-text `prompt` field.",
);
assert.match(
  app,
  /String\(prompt\?\.prompt \|\| prompt\?\.prompt_markdown \|\| ""\)/,
  "Custom prompts must read `prompt` first with `prompt_markdown` only as legacy fallback.",
);
assert.doesNotMatch(
  app,
  /prompt_markdown: customPromptId \? entry\.prompt : ""/,
  "recoverWritingEntry must not feed prompt_markdown back into the prompt object.",
);
assert.match(
  picker,
  /String\(prompt\.prompt \|\| prompt\.prompt_markdown \|\| ""\)\.trim\(\)/,
  "The picker must prefer the standard `prompt` field.",
);

// Custom prompt blank-line runs collapse to a single break so pasted questions
// don't render with oversized gaps; the structured grid adds no extra gap.
assert.ok(
  app.includes('.replace(/\\n{2,}/g, "\\n")'),
  "Custom prompt normalization must collapse runs of blank lines.",
);
const css = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");
assert.match(
  css,
  /\.writing-prompt-text-structured \{[\s\S]{0,200}gap: 0;/,
  "The structured prompt grid must not insert extra gaps between segments.",
);

// ── Goal B: fixed-question emphasis and manual highlights must overlay ──────

const highlightSlice = sliceBetween(
  app,
  "function normalizeWritingPromptHighlightRanges",
  "function deletePendingWritingPromptHighlight",
);
const highlightContext = vm.createContext({
  renderMarkdown(value) { return String(value); },
  escapeHtml(value) { return String(value); },
});
vm.runInContext(highlightSlice, highlightContext);

{
  const text = "Some people believe technology improves education.\n\nTo what extent do you agree or disagree?";
  const fixed = highlightContext.task2FixedQuestionRanges(text);
  assert.strictEqual(fixed.length, 1, "The fixed directive must be detected.");
  const userStart = fixed[0].start + 3;
  const userEnd = fixed[0].end - 4;
  const html = highlightContext.renderTask2PromptTextWithHighlights(text, [{ start: userStart, end: userEnd }]);
  const strongIndex = html.indexOf("writing-prompt-fixed-question");
  const markIndex = html.indexOf('class="writing-highlight-mark"');
  const strongEndIndex = html.indexOf("</strong>", strongIndex);
  assert.ok(strongIndex >= 0, "The fixed question must be auto-emphasized.");
  assert.ok(markIndex > strongIndex && markIndex < strongEndIndex,
    "A manual highlight inside the fixed question must render inside the <strong>, not be dropped.");
  const contextMarkIndex = html.indexOf('<span class="writing-prompt-segment writing-prompt-context">');
  assert.ok(contextMarkIndex >= 0 && contextMarkIndex < strongIndex,
    "Text before the fixed question must still render as the context segment.");
}

{
  // A manual highlight entirely outside the fixed directive keeps working too.
  const text = "Do the advantages outweigh the disadvantages? Give reasons.";
  const html = highlightContext.renderTask2PromptTextWithHighlights(text, [{ start: 0, end: 10 }]);
  assert.match(html, /class="writing-highlight-mark"/, "Highlights outside the fixed range must still render.");
}

console.log("Custom prompt filter + plain-text + highlight overlay checks passed.");
