const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

function functionBody(source, name) {
  const declaration = source.indexOf(`function ${name}(`);
  assert.notStrictEqual(declaration, -1, `${name} must exist.`);
  const signatureEnd = source.indexOf(") {", declaration);
  assert.notStrictEqual(signatureEnd, -1, `${name} must have a function body.`);
  const open = signatureEnd + 2;
  let depth = 0;
  for (let index = open; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(open + 1, index);
  }
  assert.fail(`${name} must have a closed function body.`);
}

assert.match(
  app,
  /const examinerPrefetchGate = \{ active: 0, max: 1, queue: \[\], retryTimer: null \}/,
  "Examiner preloading must stay single-flight so future clips cannot compete with the question being heard.",
);

assert.match(
  app,
  /const EXAMINER_AUDIO_LOAD_TIMEOUT_MS = 15000;/,
  "A normal examiner clip gets a full 15 seconds before the client treats the network as failed.",
);

assert.doesNotMatch(
  app,
  /EXAMINER_PHASE_MAX_WAIT_MS|armExaminerPlaybackGuard/,
  "A wall-clock guard must never silently move the learner to preparation while a question is still trying to play.",
);

assert.match(
  functionBody(app, "playExaminerTurn"),
  /playExaminerAudioWithRetry\(/,
  "A transient audio-load/play failure must retry the cached examiner clip before changing phase.",
);

assert.match(
  app,
  /function playBrowserExaminerFallback\([\s\S]{0,1800}SpeechSynthesisUtterance[\s\S]{0,1400}beginPreparation\(/,
  "If cached examiner playback remains unavailable, a spoken browser fallback must finish before preparation starts.",
);

const playbackBody = functionBody(app, "playExaminerTurn");
assert.doesNotMatch(
  playbackBody,
  /beginPreparationWithoutExaminerAudio/,
  "The normal examiner playback path must never silently skip a question's audio.",
);

assert.match(
  functionBody(app, "stopExaminerPlayback"),
  /evictExaminerAudioPlayer\(player, reason\)/,
  "A cached player that is playing or waiting to play must be evicted, not merely stopped, before preparation or recording.",
);

console.log("Speaking examiner-audio reliability checks passed.");
