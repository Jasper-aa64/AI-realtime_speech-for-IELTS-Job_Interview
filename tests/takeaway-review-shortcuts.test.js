const assert = require("assert");
const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(path.join(__dirname, "..", "web", "static", "corpus-takeaway.js"), "utf8");

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
