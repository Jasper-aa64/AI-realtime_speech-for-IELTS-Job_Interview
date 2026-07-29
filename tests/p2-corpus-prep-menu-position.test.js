const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const appSource = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

const renderStart = appSource.indexOf("async function renderP2CorpusPrepPanel");
const renderEnd = appSource.indexOf("function renderCueTop", renderStart);
assert(renderStart >= 0 && renderEnd > renderStart, "renderP2CorpusPrepPanel should be present.");
const renderSource = appSource.slice(renderStart, renderEnd);

assert.match(
  renderSource,
  /document\.body\.querySelectorAll\("#p2CorpusPrepMenu"\)[\s\S]{0,220}node\.remove\(\)/,
  "Stale P2 prep menus should be removed from body before re-rendering.",
);

assert.match(
  renderSource,
  /const menuHome = menu\?\.parentElement/,
  "P2 prep menu should remember its original home before being portaled.",
);

assert.match(
  renderSource,
  /document\.body\.appendChild\(menu\)[\s\S]{0,180}positionMenu\(\)/,
  "Open P2 prep menu should be portaled to document.body before fixed-positioning.",
);

assert.match(
  renderSource,
  /menuHome\.appendChild\(menu\)/,
  "Closed P2 prep menu should be restored to its picker home.",
);

assert.match(
  renderSource,
  /!panel\.contains\(event\.target\)[\s\S]{0,80}!menu\.contains\(event\.target\)/,
  "Outside-click handler should not close when clicking inside the portaled menu.",
);

console.log("P2 corpus prep menu positioning checks passed.");
