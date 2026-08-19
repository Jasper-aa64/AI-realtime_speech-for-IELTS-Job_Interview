const assert = require("assert");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const promptData = JSON.parse(fs.readFileSync(
  path.join(root, "data/ielts/writing/cambridge/task1_academic/cambridge_20.json"),
  "utf8",
));

const test3 = promptData.prompts.find((item) => item.id === "cambridge-20-test-3-task-1");
assert(test3, "Cambridge 20 Test 3 Task 1 must remain in the Task 1 prompt source.");
assert.match(
  test3.image_url,
  /\/assets\/writing\/task1\/cambridge\/20\/test_3_task_1\.png\?v=20260818-c20t3-clear-1$/,
  "Cambridge 20 Test 3 must point to the cache-busted clear chart asset.",
);

const imagePath = path.join(root, "web/static/assets/writing/task1/cambridge/20/test_3_task_1.png");
const imageHash = crypto.createHash("sha256").update(fs.readFileSync(imagePath)).digest("hex").toUpperCase();
assert.strictEqual(
  imageHash,
  "F477FEA00A14015606E187AC5A88253BE8ED4FA3FDF974120AF78BB355BCE87D",
  "Cambridge 20 Test 3 must use the supplied high-resolution Little Chalfont Library image.",
);

assert.match(
  app,
  /function\s+writingReportScoringModelLabel\(/,
  "Writing reports need a single helper that prefers a stored model and falls back to the real provider.",
);
assert.match(
  app,
  /class="writing-report-model-meta"[\s\S]{0,240}评分模型/,
  "A scored writing report must show its scoring model at the report's lower-right footer.",
);

console.log("Writing report model label and Cambridge 20 Test 3 image checks passed.");
