const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const app = fs.readFileSync(path.join(__dirname, "../web/static/app.js"), "utf8");

function extract(name) {
  const start = app.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `${name} exists`);
  let depth = 0;
  for (let i = app.indexOf(") {", start) + 2; i < app.length; i += 1) {
    if (app[i] === "{") depth += 1;
    if (app[i] === "}" && --depth === 0) return app.slice(start, i + 1);
  }
  throw new Error(`unterminated ${name}`);
}

const context = {};
vm.runInNewContext([
  "turnRequiresSynchronousComplete", "isP1WorkStudyIdentityTurn", "isP1DynamicFollowUpBoundary", "isP3DynamicFollowUpBoundary",
].map(extract).join("\n") + "\nthis.sync = turnRequiresSynchronousComplete;", context);

const interview = (id, role = "main") => ({ id, part: "interview", prompt: { role, question: `Q${id}` } });

test("every interview answer waits for the interviewer, so a follow-up it inserts is the next question", () => {
  // The interviewer decides follow-up / next after each answer; moving on locally would skip its follow-up.
  // 追问压力 submits the realtime transcript with no audio, which used to take the background path.
  assert.equal(context.sync(interview("a"), interview("b")), true);
  assert.equal(context.sync(interview("a", "follow_up"), interview("b")), true);
  assert.equal(context.sync(interview("a"), null), true);
});

test("IELTS middle questions still move on at once", () => {
  assert.equal(context.sync({ id: "p1a", part: "p1", prompt: { role: "main", question: "Do you like music?" } },
    { id: "p1b", part: "p1", prompt: { role: "main", question: "Do you play an instrument?" } }), false);
});
