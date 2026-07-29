const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "web/static/corpus-takeaway.js"), "utf8");

function functionBody(name) {
  const declaration = source.indexOf(`function ${name}(`);
  assert.notStrictEqual(declaration, -1, `${name} must exist.`);
  const signatureEnd = source.indexOf(") {", declaration);
  assert.notStrictEqual(signatureEnd, -1, `${name} must have a body.`);
  const open = signatureEnd + 2;
  let depth = 0;
  for (let index = open; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(open + 1, index);
  }
  assert.fail(`${name} must have a closed body.`);
}

function functionDefinition(name) {
  const declaration = source.indexOf(`function ${name}(`);
  const body = functionBody(name);
  const bodyStart = source.indexOf("{", declaration);
  return `${source.slice(declaration, bodyStart + 1)}${body}}`;
}

assert.match(
  functionBody("takeawayReviewState"),
  /if\s*\(isGuestTakeawayReviewDemo\(\)\)\s*return\s+guestTakeawayReviewState\(kind\)/,
  "Guest review state must come from page memory before localStorage is read.",
);

const saveBody = functionBody("saveTakeawayReviewState");
assert.ok(
  saveBody.indexOf("if (isGuestTakeawayReviewDemo()) return") >= 0
    && saveBody.indexOf("if (isGuestTakeawayReviewDemo()) return") < saveBody.indexOf("localStorage"),
  "Guest A/D feedback must return before any localStorage write.",
);

const syncBody = functionBody("syncTakeawayReviewState");
assert.ok(
  syncBody.indexOf("if (isGuestTakeawayReviewDemo()) return") >= 0
    && syncBody.indexOf("if (isGuestTakeawayReviewDemo()) return") < syncBody.indexOf("api("),
  "Guest A/D feedback must return before the review-state API is called.",
);

assert.match(
  functionBody("applyRemoteTakeawayReviewState"),
  /if\s*\(isGuestTakeawayReviewDemo\(\)\)\s*return/,
  "Guest demo review must ignore persisted server state.",
);

assert.doesNotMatch(
  functionBody("guestTakeawayReviewState"),
  /localStorage|sessionStorage|api\(/,
  "Guest review memory must not use browser storage or the backend.",
);

let storageReads = 0;
let storageWrites = 0;
let apiCalls = 0;
const state = {
  account: { authenticated: false, user: null },
  languageTakeaway: {},
  writingTakeaway: {},
};
const runtime = new Function(
  "state",
  "window",
  "api",
  "setTakeawayReviewToast",
  "hasTakeawayReviewData",
  "mergeTakeawayReviewRecords",
  "takeawayReviewStorageKey",
  `${functionDefinition("isGuestTakeawayReviewDemo")}
   ${functionDefinition("guestTakeawayReviewState")}
   ${functionDefinition("takeawayReviewState")}
   ${functionDefinition("saveTakeawayReviewState")}
   ${functionDefinition("syncTakeawayReviewState")}
   ${functionDefinition("applyRemoteTakeawayReviewState")}
   return {
     reviewState: takeawayReviewState,
     save: saveTakeawayReviewState,
     sync: syncTakeawayReviewState,
     applyRemote: applyRemoteTakeawayReviewState,
   };`,
)(
  state,
  {
    localStorage: {
      getItem() { storageReads += 1; return null; },
      setItem() { storageWrites += 1; },
    },
  },
  () => { apiCalls += 1; return Promise.resolve({}); },
  () => null,
  () => false,
  (_local, remote) => remote,
  () => "forbidden-guest-key",
);

const guestRecords = runtime.reviewState("language");
guestRecords.demo = { result: "mastered" };
assert.strictEqual(runtime.reviewState("language"), guestRecords, "Guest grades should survive only in page memory.");
runtime.save("language", guestRecords);
runtime.sync("language", guestRecords);
runtime.applyRemote("language", { remote: true });
assert.deepStrictEqual(
  { storageReads, storageWrites, apiCalls },
  { storageReads: 0, storageWrites: 0, apiCalls: 0 },
  "Guest review must perform zero browser-storage and backend operations.",
);

console.log("Guest Takeaway review demo checks passed.");
