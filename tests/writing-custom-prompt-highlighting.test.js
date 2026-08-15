const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const start = app.indexOf("function task2FixedQuestionRanges");
const end = app.indexOf("function task2FixedQuestionDisplayLabel");
assert.ok(start >= 0 && end > start, "Writing prompt highlight helpers must remain available.");

const context = vm.createContext({
  renderMarkdown(value) { return String(value); },
});
vm.runInContext(app.slice(start, end), context);

const markdown = [
  "Some people believe technology improves education.",
  "",
  "**To what extent do you agree or disagree?**",
].join("\n");
const visible = context.visibleWritingPromptTextWithMap(markdown).text;
const visibleRanges = context.task2FixedQuestionRanges(visible);
assert.strictEqual(visibleRanges.length, 1, "Markdown must not hide the fixed Task 2 directive.");
const sourceRanges = context.sourceRangesForVisiblePromptText(markdown, visibleRanges);
assert.strictEqual(sourceRanges.length, 1);
assert.strictEqual(markdown.slice(sourceRanges[0].start, sourceRanges[0].end), "To what extent do you agree or disagree?");

for (const prompt of [
  "Discuss both these views and give your own opinion.",
  "Do the advantages outweigh the disadvantages?",
  "Do you think this is a positive or negative development?",
]) {
  assert.ok(context.task2FixedQuestionRanges(prompt).length, `Directive should be recognized: ${prompt}`);
}

console.log("Custom writing prompt highlighting checks passed.");
