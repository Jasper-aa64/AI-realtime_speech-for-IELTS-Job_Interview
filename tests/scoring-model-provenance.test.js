const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

function sliceBetween(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `${startMarker}..${endMarker} slice must exist.`);
  return source.slice(start, end);
}

// ── Display formatting (real model ids, never adapter names) ────────────────

const helperSlice = sliceBetween(
  app,
  "function scoringModelDisplayName",
  "function writingReportScoringModelLabel",
);
const helperContext = vm.createContext({ escapeHtml(value) { return String(value); } });
vm.runInContext(helperSlice, helperContext);

assert.strictEqual(
  helperContext.scoringModelDisplayName("claude", "claude-sonnet-4-6"),
  "Claude Sonnet 4.6",
  "claude-sonnet-4-6 must display as Claude Sonnet 4.6.",
);
assert.strictEqual(
  helperContext.scoringModelDisplayName("openai", "gpt-5.6-terra"),
  "GPT-5.6 Terra",
  "GPT models must keep their accurate version numbers.",
);
assert.strictEqual(
  helperContext.scoringModelDisplayName("claude", "sonnet"),
  "Claude Sonnet",
  "A bare CLI model must still be prefixed with its provider family.",
);
assert.strictEqual(
  helperContext.reportScoringModelLabel({}),
  "历史记录未保存",
  "Missing provenance must show 历史记录未保存.",
);
assert.strictEqual(
  helperContext.reportScoringModelLabel({ provider: "codex" }),
  "历史记录未保存",
  "The internal codex default must never be presented as a model.",
);
assert.strictEqual(
  helperContext.reportScoringModelLabel({ provider: "fallback" }),
  "本地兜底",
  "Local fallback scoring must be labelled honestly.",
);
assert.strictEqual(
  helperContext.reportScoringModelLabel({ provider: "claude", model: "claude-sonnet-4-6" }),
  "Claude Sonnet 4.6",
  "A Claude-scored report must show the real model name.",
);

// ── Writing surface reads only the immutable snapshot ───────────────────────

const writingLabelSlice = sliceBetween(
  app,
  "function writingReportScoringModelLabel(entry) {",
  "function writingReportDetailHtml",
);
assert.doesNotMatch(
  writingLabelSlice,
  /task\.provider|task\.model|ai_task/,
  "The writing label must not read the task's internal adapter defaults.",
);
assert.match(
  writingLabelSlice,
  /score\.scoring_provider[\s\S]{0,200}score\.scoring_model/,
  "The writing label must read the immutable scoring_provider/scoring_model snapshot.",
);

// ── Speaking reports use the same shared provenance helper ──────────────────

const speakingDetailSlice = sliceBetween(
  app,
  "function renderDetail(attempt, updateView = true, options = {}) {",
  "function unscoredSpeakingReportHtml",
);
assert.match(
  speakingDetailSlice,
  /reportScoringModelMetaHtml\(\{ provider: score\.scoring_provider, model: score\.scoring_model \|\| score\.model \}\)/,
  "The speaking report must render the shared scoring-model footer.",
);

// ── Scoring-in-progress card shows the recorded model only ─────────────────

const scoringCardSlice = sliceBetween(
  app,
  "function writingReportScoringStateHtml(entry, task) {",
  "function writingReportScoringModelLabel",
);
assert.match(
  scoringCardSlice,
  /reportScoringModelMetaHtml\(\{ provider: task\?\.provider, model: task\?\.model \}, task\?\.model \? "（评分中）" : ""\)/,
  "The scoring card may show the model only when the task already recorded one.",
);

// The old codex-as-model mapping must be gone.
assert.doesNotMatch(app, /codex: "Codex"/, "No adapter-name→Codex display mapping may remain.");

console.log("Scoring model provenance checks passed.");
