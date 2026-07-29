const assert = require("assert");
const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(path.join(__dirname, "..", "web", "static", "corpus-takeaway.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "web", "static", "styles.css"), "utf8");

assert.match(
  source,
  /pendingLocate/,
  "W locate requests during the A/D mascot animation should be queued instead of ignored."
);

assert.match(
  source,
  /runPendingTakeawayLocate/,
  "Queued W locate requests should run after the current review animation commits."
);

assert.doesNotMatch(
  source,
  /markTakeawayLocatedCard\(kind,\s*""\)/,
  "Pressing W on the already-located card should keep the dashed frame while opening/reading it."
);

assert.match(
  source,
  /scrollTakeawayCardIntoView\(kind,\s*target,\s*\{\s*forceCenter:\s*true\s*\}\)/,
  "Pressing W should always request a centered scroll for the located card, clamped naturally near the bottom."
);

assert.doesNotMatch(
  source,
  /if\s*\(takeawayCardNeedsScroll\(kind,\s*target\)\)\s*\{[\s\S]{0,140}return;\s*\}/,
  "Pressing W on the already-located card must not stop at scrolling; the second press should reveal/read it."
);

assert.match(
  source,
  /function scrollTakeawayCardIntoView\(kind,\s*entryId,\s*options\s*=\s*\{\}\)/,
  "Card centering should accept options so W can force-center while other call sites keep existing behavior."
);

assert.match(
  css,
  /body\.theme-dark\.font-popular[^{}]*\.language-takeaway-card-wrap\.is-located \.language-takeaway-card[\s\S]*outline:\s*2px dashed rgba\(191,\s*230,\s*255,\s*0\.92\)/,
  "The third dark theme should use a light readable dashed locate frame, not the deep-blue accent."
);
