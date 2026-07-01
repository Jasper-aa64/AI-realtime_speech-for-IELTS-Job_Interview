const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const appSource = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const cssSource = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

const showMatch = /function showWritingFixPopover\(anchor,\s*event = null\)/.exec(appSource);
const showStart = showMatch ? showMatch.index : -1;
const showEnd = appSource.indexOf("async function applyWritingFixFromPopover", showStart);
assert(showStart >= 0 && showEnd > showStart, "showWritingFixPopover should exist.");

const showSource = appSource.slice(showStart, showEnd);
const hideMatch = /function hideWritingFixPopover\(\)/.exec(appSource);
const hideStart = hideMatch ? hideMatch.index : -1;
const hideEnd = appSource.indexOf("function showWritingFixPopover", hideStart);
assert(hideStart >= 0 && hideEnd > hideStart, "hideWritingFixPopover should exist.");
const hideSource = appSource.slice(hideStart, hideEnd);
assert.match(
  showSource,
  /anchor\.appendChild\(popover\);/,
  "Fix popover should be anchored to the clicked annotation so it scrolls with report content.",
);
assert.doesNotMatch(
  showSource,
  /document\.body\.appendChild\(popover\);/,
  "Fix popover must not be placed at document body level; fixed viewport positioning flies to the page top.",
);
assert.doesNotMatch(
  showSource,
  /event\?\.client[XY]|getBoundingClientRect\(\)|aboveTop/,
  "Fix popover should not depend on viewport click coordinates.",
);
assert.match(
  hideSource,
  /popover\.remove\(\);/,
  "Hiding the Fix popover should remove the anchored node from the previous annotation.",
);
assert.match(
  cssSource,
  /\.writing-fix-popover\s*{[\s\S]{0,160}position:\s*absolute\s*!important;[\s\S]{0,160}bottom:\s*calc\(100% \+ 6px\)\s*!important;/,
  "Fix popover should use absolute positioning above the clicked annotation.",
);
assert.doesNotMatch(
  cssSource,
  /\.writing-fix-popover\s*{[\s\S]{0,120}position:\s*fixed\s*!important;/,
  "Fix popover must not use fixed positioning.",
);

console.log("Writing Fix popover position regression checks passed.");
