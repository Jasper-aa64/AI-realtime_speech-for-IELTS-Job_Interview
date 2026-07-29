const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

assert.match(
  app,
  /function\s+examinerAudioCacheKey\([\s\S]{0,700}role[\s\S]{0,700}voice[\s\S]{0,700}normalize/,
  "Examiner audio cache keys must be stable across refreshes of the same voice, role, and normalized text.",
);

assert.match(
  app,
  /examinerAudioPreloads:\s*new Map\(\)/,
  "Examiner audio preload state must persist a shared in-flight/cache map for the active practice session.",
);

assert.match(
  app,
  /const examinerPrefetchGate = \{ active: 0, max: 1, queue: \[\], retryTimer: null \}/,
  "Known questions must warm one at a time so future clips cannot compete with the foreground question.",
);

function functionBody(source, name) {
  const declaration = source.indexOf(`function ${name}`);
  assert.notStrictEqual(declaration, -1, `${name} must exist.`);
  const open = source.indexOf("{", declaration);
  let depth = 0;
  for (let index = open; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(open + 1, index);
  }
  assert.fail(`${name} must have a closed function body.`);
}

const attemptWarmup = functionBody(app, "prefetchAllMainExaminerTts");
const upcomingWarmup = functionBody(app, "prefetchUpcomingExaminerTts");
const loadingGate = functionBody(app, "examinerAudioIsLoading");
const fixedWarmup = functionBody(app, "prefetchFixedExaminerTts");
const gateDrain = functionBody(app, "drainExaminerPrefetchGate");
const clearPreloads = functionBody(app, "clearExaminerAudioPreloads");
const ttsRefresh = functionBody(app, "refreshPendingExaminerTts");
const startPracticeBody = functionBody(app, "startPractice");
const playExaminerBody = functionBody(app, "playExaminerTurn");
const stopPlaybackBody = functionBody(app, "stopExaminerPlayback");

assert.match(
  loadingGate,
  /state\.status\s*===\s*["']examiner_loading["']/,
  "Background prefetch must pause for the full foreground examiner-loading phase, before the active player is registered.",
);
assert.match(
  loadingGate,
  /state\.status\s*===\s*["']loading["']/,
  "Background prefetch must also pause during the renderTurn-to-beginExaminerPhase startup gap.",
);

assert.match(
  app,
  /const\s+EXAMINER_AUDIO_PLAY_START_TIMEOUT_MS\s*=\s*\d+/,
  "Examiner playback must have a bounded start timeout so Preparing cannot hang forever.",
);
assert.match(
  app,
  /const\s+EXAMINER_TTS_REQUEST_TIMEOUT_MS\s*=\s*\d+/,
  "On-demand examiner TTS refresh requests must have a bounded network timeout.",
);

assert.match(
  app,
  /class\s+ExaminerAudioPlayer[\s\S]{0,5200}playToEnd\([\s\S]{0,1500}EXAMINER_AUDIO_PLAY_START_TIMEOUT_MS[\s\S]{0,1200}_fail\(["']play["']/,
  "Howler playback must reject when neither onplay nor onplayerror arrives.",
);

assert.match(
  fixedWarmup,
  /preloadFixedExaminerAudioItems\(payload\)/,
  "Authenticated fixed-question warmup must also preload ready clips into the browser cache.",
);
assert.match(
  ttsRefresh,
  /EXAMINER_TTS_REQUEST_TIMEOUT_MS[\s\S]{0,400}apiWithAbortTimeout\(/,
  "A stalled examiner-TTS refresh request must abort instead of leaving the identity question in Preparing forever.",
);
assert.match(
  startPracticeBody,
  /warmFixedExaminerTtsNow\(\)/,
  "Starting practice must retry the fixed identity-audio warmup instead of relying only on one app-start attempt.",
);

assert.match(
  gateDrain,
  /if \(!examinerPrefetchGate\.retryTimer\)[\s\S]{0,300}examinerPrefetchGate\.retryTimer\s*=\s*window\.setTimeout/,
  "A blocked prefetch queue must use one shared retry timer instead of one polling timer per queued turn.",
);

assert.match(
  app,
  /function\s+preloadExaminerAudio[\s\S]{0,1800}persistent:\s*isFixedExaminerAudioTurn\(turn\)/,
  "Fixed identity prompts must mark their browser audio cache entries as persistent across practice-view resets.",
);
assert.match(
  clearPreloads,
  /if \(entry\.persistent\) continue;/,
  "Practice teardown must preserve already-loaded fixed identity audio while clearing dynamic turn audio.",
);

const gateTimers = new Map();
let gateTimerId = 0;
let gateTimerCreates = 0;
const gateWindow = {
  setTimeout(callback) {
    gateTimerCreates += 1;
    gateTimerId += 1;
    gateTimers.set(gateTimerId, callback);
    return gateTimerId;
  },
  clearTimeout(id) {
    gateTimers.delete(id);
  },
};
const gateState = { status: "loading", activeExaminerAudioPlayer: null };
const gate = { active: 0, max: 1, queue: Array.from({ length: 10 }, () => () => null), retryTimer: null };
const executeGate = new Function(
  "state",
  "window",
  "examinerPrefetchGate",
  `
    function examinerAudioIsLoading() {${loadingGate}}
    function drainExaminerPrefetchGate() {${gateDrain}}
    return drainExaminerPrefetchGate;
  `,
)(gateState, gateWindow, gate);
executeGate();
executeGate();
executeGate();
assert.strictEqual(gateTimerCreates, 1, "Repeated drain calls while the current question loads must share one retry timer.");
assert.strictEqual(gateTimers.size, 1, "Only one pending retry timer may exist for the blocked prefetch queue.");

let fixedUnloadCount = 0;
let dynamicUnloadCount = 0;
const clearState = {
  examinerAudioBlobUrls: new Map(),
  speaking: {
    examinerAudioPreloads: new Map([
      ["fixed", { persistent: true, player: { unload: () => { fixedUnloadCount += 1; } } }],
      ["dynamic", { persistent: false, player: { unload: () => { dynamicUnloadCount += 1; } } }],
    ]),
  },
};
new Function("state", "traceExaminerAudio", "URL", clearPreloads)(
  clearState,
  () => null,
  { revokeObjectURL: () => null },
);
assert.strictEqual(fixedUnloadCount, 0, "Fixed identity audio must remain loaded when changing practice views.");
assert.strictEqual(dynamicUnloadCount, 1, "Dynamic audio from the previous practice must be unloaded.");
assert.deepStrictEqual(Array.from(clearState.speaking.examinerAudioPreloads.keys()), ["fixed"]);

assert.match(
  upcomingWarmup,
  /if \(next\.examiner_tts\?\.audio_url\) \{[\s\S]{0,240}warmed \+= 1;[\s\S]{0,320}runExaminerPrefetch\(\(\) => preloadExaminerAudio\(next\)/,
  "The immediately upcoming ready clip must use the bounded prefetch gate.",
);
assert.doesNotMatch(
  upcomingWarmup,
  /if \(next\.examiner_tts\?\.audio_url\) \{\s*preloadExaminerAudio\(next\)/,
  "Future clips must never bypass the bounded prefetch gate with direct eager loads.",
);

const currentTurn = { id: "t1", examiner_tts: { audio_url: "/audio/t1.mp3" } };
const queuedPrefetches = [];
const loadedTurnIds = [];
const preloadState = {
  attempt: {
    id: "attempt-1",
    turns: [currentTurn, ...[2, 3, 4, 5, 6].map((number) => ({
      id: `t${number}`,
      examiner_tts: { audio_url: `/audio/t${number}.mp3` },
    }))],
  },
  practiceSessionId: 1,
  speaking: { examinerTtsPrefetched: new Set() },
};
const executeUpcomingWarmup = new Function(
  "currentTurn",
  "state",
  "runExaminerPrefetch",
  "preloadExaminerAudio",
  "shouldStreamFollowUpTurn",
  "hasUsableTurnQuestion",
  "api",
  "traceExaminerAudio",
  upcomingWarmup,
);
executeUpcomingWarmup(
  currentTurn,
  preloadState,
  (task) => queuedPrefetches.push(task),
  (turn) => {
    loadedTurnIds.push(turn.id);
    return Promise.resolve(turn);
  },
  () => false,
  () => true,
  () => Promise.reject(new Error("Ready clips must not call the TTS status API.")),
  () => null,
);
assert.strictEqual(queuedPrefetches.length, 1, "Only the immediately upcoming ready clip should enter the prefetch queue.");
assert.deepStrictEqual(loadedTurnIds, [], "Ready clips must not start loading before the bounded gate runs them.");
queuedPrefetches.forEach((task) => task());
assert.deepStrictEqual(loadedTurnIds, ["t2"], "The gate should load only the next question ahead of time.");

assert.match(
  attemptWarmup,
  /prefetchUpcomingExaminerTts\(state\.currentTurn\)/,
  "Startup preloading must exclude the current turn; its direct playback path owns that audio state.",
);
assert.doesNotMatch(
  attemptWarmup,
  /examiner-tts/,
  "Startup preloading must not start a second server-side TTS pipeline; the attempt service already owns synthesis.",
);

assert.match(
  app,
  /function\s+preloadExaminerAudio\([\s\S]{0,1800}existing\.promise[\s\S]{0,1400}new ExaminerAudioPlayer\(\)[\s\S]{0,900}\.load\(/,
  "Preloading must reuse the same in-flight promise and load a real Howler-backed player exactly once.",
);

assert.match(
  upcomingWarmup,
  /next\.examiner_tts\?\.audio_url[\s\S]{0,500}runExaminerPrefetch\([\s\S]{0,500}preloadExaminerAudio\(next\)/,
  "Future audio must preload only through the bounded browser queue.",
);

assert.match(
  app,
  /prefetchUpcomingExaminerTts[\s\S]{0,3400}preloadExaminerAudio\(next\)/,
  "The next questions must reuse browser preload rather than only warming server-side TTS.",
);

assert.match(
  app,
  /async\s+function\s+playExaminerAudioWithRetry[\s\S]{0,2000}preloadExaminerAudio\(turn, tts\)[\s\S]{0,900}resetForPlayback/,
  "Question playback must claim the preloaded player and restart it at time zero.",
);

assert.match(
  app,
  /function\s+clearExaminerAudioPreloads\([\s\S]{0,1300}examinerAudioPreloads[\s\S]{0,600}\.unload\(/,
  "Practice teardown must unload cached Howler players and listeners.",
);

assert.match(
  app,
  /tts-refresh:payload/,
  "Audio diagnostics must record the server TTS refresh payload without learner content.",
);
assert.match(
  app,
  /howler:ready/,
  "Audio diagnostics must record when the browser player becomes ready.",
);
assert.doesNotMatch(
  app,
  /format:\s*inferHowlerFormat\(playbackUrl\)/,
  "Stable examiner audio may be served as m4a behind an mp3 URL, so Howler must use the response MIME type instead of forcing mp3 decoding.",
);

console.log("Speaking examiner-audio preload checks passed.");
