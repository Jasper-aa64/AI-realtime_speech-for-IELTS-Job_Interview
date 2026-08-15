const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const picker = fs.readFileSync(path.join(root, "web/static/writing-prompt-picker.js"), "utf8");
const html = fs.readFileSync(path.join(root, "web/static/index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

assert.match(app, /loadCustomWritingPrompts/, "The app must load authenticated custom prompts.");
assert.match(app, /createCustomWritingPrompt/, "The app must create custom prompts through the API.");
assert.match(app, /updateCustomWritingPrompt/, "The card menu must support editing.");
assert.match(app, /deleteCustomWritingPrompt/, "The card menu must support deletion.");
assert.match(app, /showConfirmDelete[\s\S]*custom/i, "Deletion must use the in-app confirmation dialog.");
assert.match(app, /visibleWritingPromptTextWithMap/, "Markdown markers must not break directive detection.");
assert.match(app, /Discuss both|To what extent do you agree|positive or negative|advantages.*outweigh/i,
  "Task 2 directive variants must be highlighted programmatically.");
assert.match(picker, /data-writing-custom-create/, "Custom practice must start with an add card.");
assert.match(picker, /data-writing-custom-edit/, "Each saved card must expose edit.");
assert.match(picker, /data-writing-custom-delete/, "Each saved card must expose delete.");
assert.match(picker, /writing-custom-prompt-choice/, "Custom prompts must use bounded cards matching the bank.");
assert.match(html, /customWritingPromptDialog/, "The page must include a custom prompt editor dialog.");
assert.match(html, /customWritingPromptMarkdown/, "The dialog must include the shared editor source.");
assert.match(css, /writing-custom-add-card/, "The add card needs theme-aware styling.");
assert.match(css, /writing-custom-prompt-menu/, "The card management menu needs a top-layer style.");

console.log("Custom writing prompt checks passed.");
