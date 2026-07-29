const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const appSource = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "app.js"),
  "utf8"
);
const cssSource = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "styles.css"),
  "utf8"
);

const sectionStart = appSource.indexOf("function p3DiscussionSkillsSection(skills)");
const sectionEnd = appSource.indexOf("\nfunction p3TurnDiscussionMoves", sectionStart);
assert.ok(sectionStart >= 0 && sectionEnd > sectionStart, "P3 skills renderer must exist.");
const section = appSource.slice(sectionStart, sectionEnd);

assert.match(
  section,
  /abstract_extension[\s\S]*reasoning[\s\S]*comparison_concession[\s\S]*specific_support/,
  "The report renderer must allow only the four current P3 skill dimensions."
);
assert.match(
  section,
  /filter\(/,
  "Legacy report payloads must be filtered before the skill cards are rendered."
);
assert.match(
  section,
  /follow_up_handling/,
  "The legacy key must be named explicitly so it cannot leak back into old reports."
);
assert.match(
  cssSource,
  /\.p3-skills-grid\s*\{[\s\S]{0,220}grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
  "P3 skill cards must use a stable two-column grid."
);
assert.match(
  cssSource,
  /@media \(max-width: 640px\)\s*\{[\s\S]*?\.p3-skills-grid\s*\{\s*grid-template-columns:\s*1fr;/,
  "P3 skill cards should collapse to one column only on narrow mobile screens."
);

console.log("P3 discussion skills four-card grid checks passed.");
