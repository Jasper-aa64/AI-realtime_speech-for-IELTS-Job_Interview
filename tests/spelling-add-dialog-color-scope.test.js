const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const css = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");
const index = fs.readFileSync(path.join(root, "web/static/index.html"), "utf8");

assert.doesNotMatch(
  css,
  /Spelling drill dark contrast guard: keep dark mode layered, not flat black/,
  "This task is scoped to the add-word dialog; it must not add a broad spelling page dark-mode guard.",
);

assert.doesNotMatch(
  css,
  /body\.theme-dark \.spelling-drill-panel\s*{[\s\S]{0,900}--sd-card:\s*#111a24\s*!important/,
  "Do not override the whole spelling drill page when only the add-word dialog color is being fixed.",
);

assert.match(
  css,
  /\/\* Spelling add dialog color scope: only the small add-word popup, not the full spelling page\. \*\//,
  "Expected a scoped color guard for the add-word popup.",
);

assert.match(
  css,
  /body:not\(\.theme-dark\) \.spelling-add-dialog \.language-takeaway-popup\.spelling-add-card\s*{[\s\S]{0,360}background:\s*#ffffff\s*!important/,
  "Light mode add-word popup should have an opaque white card.",
);

assert.match(
  css,
  /body\.theme-dark \.spelling-add-dialog \.language-takeaway-popup\.spelling-add-card\s*{[\s\S]{0,480}background:\s*linear-gradient\(180deg,\s*#111a24 0%,\s*#0b121b 100%\)\s*!important/,
  "Dark mode add-word popup should have an opaque dark card.",
);

assert.doesNotMatch(
  css,
  /spelling-add-save-btn\s*{[\s\S]{0,420}#14b8a6|spelling-add-save-btn\s*{[\s\S]{0,420}#38bdf8/,
  "Add-word save button should not use the one-off teal/blue color from the previous fix.",
);

assert.match(
  css,
  /body\.theme-dark:not\(\.font-academic\):not\(\.font-popular\) \.language-takeaway-action-buttons button:last-child\s*{[\s\S]{0,360}background:\s*linear-gradient\(180deg,\s*#1f4f47 0%,\s*#173c37 62%,\s*#102c2a 100%\)\s*!important;[\s\S]{0,180}color:\s*#f4fff9\s*!important/,
  "Default dark Takeaway save button should be a dark white-text button.",
);

assert.match(
  css,
  /body\.theme-dark:not\(\.font-academic\):not\(\.font-popular\) \.spelling-add-dialog \.spelling-add-save-btn\s*{[\s\S]{0,360}background:\s*linear-gradient\(180deg,\s*#1f4f47 0%,\s*#173c37 62%,\s*#102c2a 100%\)\s*!important;[\s\S]{0,180}color:\s*#f4fff9\s*!important/,
  "Default dark add-word save button should match the Takeaway save button.",
);

assert.match(
  css,
  /body\.theme-dark\.font-academic \.spelling-add-dialog \.spelling-add-save-btn\s*{[\s\S]{0,360}background:[\s\S]{0,220}#2f2721\s*!important;[\s\S]{0,180}color:\s*#fff2e6\s*!important/,
  "Academic dark add-word save button should match the Takeaway save button.",
);

assert.match(
  css,
  /body\.theme-dark\.font-popular \.spelling-add-dialog \.spelling-add-save-btn\s*{[\s\S]{0,300}background:\s*linear-gradient\(180deg,\s*#235b86 0%,\s*#184870 62%,\s*#0f3e62 100%\)\s*!important;[\s\S]{0,180}color:\s*#f4faff\s*!important/,
  "Popular dark add-word save button should match the Takeaway save button.",
);

assert.match(
  index,
  /styles\.css\?v=20260709-spelling-add-dialog-takeaway-style-1/,
  "The stylesheet cache-buster should change when the add-word button color changes.",
);

console.log("Spelling add dialog color scope checks passed.");
