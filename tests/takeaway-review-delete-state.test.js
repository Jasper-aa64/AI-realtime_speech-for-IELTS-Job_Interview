const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "corpus-takeaway.js"),
  "utf8"
);

function functionDefinition(name) {
  const declaration = source.indexOf(`function ${name}(`);
  assert.notStrictEqual(declaration, -1, `${name} must exist.`);
  const bodyStart = source.indexOf("{", declaration);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(declaration, index + 1);
  }
  assert.fail(`${name} must have a closed body.`);
}

function makeRuntime(session) {
  const state = {
    languageTakeaway: { reviewSession: session, revealedEntryIds: new Set(["current"]) },
    writingTakeaway: { reviewSession: null, revealedEntryIds: new Set() },
  };
  const ended = [];
  const remove = new Function(
    "state",
    "endTakeawayReview",
    `${functionDefinition("takeawayReviewSession")}
     ${functionDefinition("removeDeletedTakeawayReviewEntry")}
     return removeDeletedTakeawayReviewEntry;`
  )(state, (kind, message) => ended.push({ kind, message }));
  return { state, ended, remove };
}

{
  const { state, ended, remove } = makeRuntime({
    active: true,
    ids: ["current"],
    reviewedIds: new Set(),
    currentId: "current",
    locatedId: "current",
    animatingId: "",
    pendingLocate: true,
  });

  remove("language", "current");

  assert.deepEqual(state.languageTakeaway.reviewSession.ids, [], "Deleted card must leave the active review batch.");
  assert.equal(state.languageTakeaway.reviewSession.currentId, "", "Deleted current card must not remain awaiting A/D.");
  assert.equal(state.languageTakeaway.revealedEntryIds.has("current"), false, "Deleted card must not remain revealed.");
  assert.equal(ended.length, 1, "Deleting the final review card must leave review mode immediately.");
}

{
  const { state, ended, remove } = makeRuntime({
    active: true,
    ids: ["current", "next"],
    reviewedIds: new Set(),
    currentId: "current",
    locatedId: "current",
    animatingId: "",
    pendingLocate: false,
  });

  remove("language", "current");

  assert.deepEqual(state.languageTakeaway.reviewSession.ids, ["next"], "Only the deleted review target should be removed.");
  assert.equal(state.languageTakeaway.reviewSession.currentId, "", "Remaining cards must be selectable immediately after deleting the current card.");
  assert.equal(ended.length, 0, "A remaining review target should keep the session active.");
}

for (const [fn, kind] of [["deleteLanguageTakeawayEntry", "language"], ["deleteWritingTakeawayEntry", "writing"]]) {
  const start = source.indexOf(`async function ${fn}`);
  assert.notStrictEqual(start, -1, `${fn} must exist.`);
  const body = source.slice(start, start + 2800);
  assert.match(body, new RegExp(`removeDeletedTakeawayReviewEntry\\("${kind}", entryId\\)`), `${fn} must clear its matching review session when a card is deleted.`);
}

console.log("Takeaway review delete-state checks passed.");
