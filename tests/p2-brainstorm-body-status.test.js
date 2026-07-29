const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "corpus-takeaway.js"),
  "utf8",
);

const bodyPredicate = source.match(
  /function p2BrainstormHasEditedBody\(item = \{\}\) \{([\s\S]*?)\n    \}/,
);
assert.ok(bodyPredicate, "Brainstorm needs one reusable predicate for an edited P2 body.");

const hasEditedBody = new Function("item", bodyPredicate[1]);
assert.equal(hasEditedBody({ corpus_text: "prepared body" }), true);
assert.equal(hasEditedBody({ material_text: "cached body" }), true);
assert.equal(hasEditedBody({ has_bank_corpus: true }), true);
assert.equal(hasEditedBody({ corpus_text: "  ", material_text: "", has_bank_corpus: false }), false);

assert.match(
  source,
  /function p2BrainstormFilteredBodyStats\(\)[\s\S]*p2BrainstormRowMatchesActiveFilter[\s\S]*has-p2-bank-body/,
  "The badge must count edited P2 bodies inside the active filter, not the complete bank.",
);

assert.match(
  source,
  /p2-brainstorm-index\$\{p2BrainstormHasEditedBody\(item\) \? " has-p2-bank-body" : ""\}/,
  "Only rows with an edited P2 body should tint the left index.",
);

assert.match(
  source,
  /P2 正文已填 \$\{stats\.filled\}\/\$\{stats\.total\}/,
  "The filter badge must show the scoped edited-body numerator and denominator.",
);

console.log("P2 Brainstorm edited-body status checks passed.");
