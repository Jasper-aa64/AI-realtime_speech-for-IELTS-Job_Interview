const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

function classDefinition(source, name) {
  const declaration = source.indexOf(`class ${name}`);
  assert.notStrictEqual(declaration, -1, `${name} must exist.`);
  const open = source.indexOf("{", declaration);
  let depth = 0;
  for (let index = open; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(declaration, index + 1);
  }
  assert.fail(`${name} must have a closed class body.`);
}

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
  functionBody(app, "playExaminerTurn"),
  /playExaminerAudioWithRetry\([\s\S]{0,1800}catch\s*\(error\)[\s\S]{0,900}currentExaminerTurnStillMatches[\s\S]{0,500}playBrowserExaminerFallback/,
  "An interrupted player must speak a fallback question instead of silently entering preparation.",
);

const playExaminerTurnBody = functionBody(app, "playExaminerTurn");
const retryErrorIndex = playExaminerTurnBody.indexOf('traceExaminerAudio("playback:audio-retries-exhausted"');
const retryFallbackIndex = playExaminerTurnBody.indexOf("playBrowserExaminerFallback", retryErrorIndex);
const retryPhaseCheckIndex = playExaminerTurnBody.indexOf("currentExaminerTurnStillMatches", retryErrorIndex);
assert.ok(
  retryErrorIndex >= 0
    && retryFallbackIndex > retryErrorIndex
    && retryPhaseCheckIndex > retryErrorIndex
    && retryPhaseCheckIndex < retryFallbackIndex,
  "An exhausted retry must re-check the active playback phase before it can start the fallback voice.",
);

async function main() {
  const scheduled = new Map();
  let timerId = 0;
  const fakeWindow = {
    setTimeout(callback) {
      timerId += 1;
      scheduled.set(timerId, callback);
      return timerId;
    },
    clearTimeout(id) {
      scheduled.delete(id);
    },
  };
  const Player = new Function(
    "window",
    "traceExaminerAudio",
    "normalizeHowlerError",
    "EXAMINER_AUDIO_LOAD_TIMEOUT_MS",
    "EXAMINER_AUDIO_PLAY_START_TIMEOUT_MS",
    `${classDefinition(app, "ExaminerAudioPlayer")}; return ExaminerAudioPlayer;`,
  )(
    fakeWindow,
    () => null,
    (error) => error instanceof Error ? error.message : String(error),
    5000,
    5000,
  );

  const player = new Player();
  player.status = "ready";
  player.source = { sourceUrl: "/audio/identity.mp3", playbackUrl: "/audio/identity.mp3" };
  player.howl = {
    play: () => 7,
    playing: () => false,
    seek: () => 0,
    duration: () => 1.5,
    state: () => "loaded",
  };

  const result = player.playToEnd().then(
    () => ({ resolved: true }),
    (error) => ({ resolved: false, message: error.message }),
  );
  assert.strictEqual(scheduled.size, 1, "A playback-start watchdog must be armed before Howler play begins.");
  const watchdog = Array.from(scheduled.values())[0];
  watchdog();
  const outcome = await result;
  assert.strictEqual(outcome.resolved, false, "A silent Howler start must reject instead of hanging forever.");
  assert.match(outcome.message, /Timed out starting examiner audio/);
  assert.strictEqual(player.status, "failed");
  assert.strictEqual(scheduled.size, 0, "The watchdog timer must be cleared after failure.");

  let cachedHowlOptions = null;
  let cachedStopCalls = 0;
  fakeWindow.Howl = class CachedIdleHowl {
    constructor(options) {
      cachedHowlOptions = options;
    }

    stop() {
      cachedStopCalls += 1;
    }

    seek() {}

    play() {
      return 41;
    }

    playing() {
      return false;
    }

    duration() {
      return 1.5;
    }

    state() {
      return "loaded";
    }

    unload() {}
  };
  const cachedPlayer = new Player();
  const cachedLoad = cachedPlayer.load({
    sourceUrl: "/audio/cached-question.mp3",
    playbackUrl: "/audio/cached-question.mp3",
  });
  cachedHowlOptions.onload();
  await cachedLoad;
  cachedPlayer.resetForPlayback();
  assert.strictEqual(
    cachedStopCalls,
    0,
    "Resetting an idle preloaded clip must not emit a stale stop event into the next question playback.",
  );
  const startedPlayIds = [];
  let cachedOutcomeSettled = false;
  const cachedOutcome = cachedPlayer.playToEnd({
    onPlay: ({ id }) => startedPlayIds.push(id),
  });
  cachedOutcome.finally(() => {
    cachedOutcomeSettled = true;
  });
  cachedHowlOptions.onplay(99);
  cachedHowlOptions.onstop(99);
  await Promise.resolve();
  assert.deepStrictEqual(
    startedPlayIds,
    [],
    "A delayed onplay event from an older Howler sound id must not move the new turn into Listening.",
  );
  assert.strictEqual(
    cachedOutcomeSettled,
    false,
    "A delayed stop/end event from an older Howler sound id must not finish the active question playback.",
  );
  cachedHowlOptions.onplay(41);
  cachedHowlOptions.onend(41);
  assert.strictEqual(
    await cachedOutcome,
    "ended",
    "An idle preloaded clip must still reach its normal playback completion path.",
  );

  let staleCachedUnloadCalls = 0;
  const staleCachedPlayer = {
    playing: () => false,
    hasPendingPlayback: () => true,
    unload: () => { staleCachedUnloadCalls += 1; },
  };
  const stopPlaybackState = {
    examinerPlayback: null,
    activeExaminerAudio: null,
    activeExaminerAudioPlayer: null,
    browserTtsUtterance: null,
    speaking: {
      examinerAudioPreloads: new Map([
        ["stale-question", { player: staleCachedPlayer }],
      ]),
    },
  };
  const stopPlayback = new Function(
    "state",
    "window",
    "evictExaminerAudioPlayer",
    `return function stopExaminerPlayback(reason = "stop-playback") {${functionBody(app, "stopExaminerPlayback")}};`,
  )(
    stopPlaybackState,
    {},
    (player) => player.unload(),
  );
  stopPlayback("enter-recording");
  assert.strictEqual(
    staleCachedUnloadCalls,
    1,
    "Stopping examiner playback must unload a cached player whose start is pending after it escaped the active-player pointer.",
  );

  let ownedPlayerUnloadCalls = 0;
  const ownedPlayer = {
    playing: () => true,
    hasPendingPlayback: () => true,
    unload: () => { ownedPlayerUnloadCalls += 1; },
  };
  const ownedPlaybackState = {
    examinerPlayback: {
      player: ownedPlayer,
      guardTimer: null,
      cancelled: false,
      promise: Promise.resolve(),
    },
    activeExaminerAudio: null,
    activeExaminerAudioPlayer: null,
    browserTtsUtterance: null,
    speaking: { examinerAudioPreloads: new Map() },
  };
  const stopOwnedPlayback = new Function(
    "state",
    "window",
    "evictExaminerAudioPlayer",
    `return function stopExaminerPlayback(reason = "stop-playback") {${functionBody(app, "stopExaminerPlayback")}};`,
  )(
    ownedPlaybackState,
    {},
    (player) => player.unload(),
  );
  stopOwnedPlayback("enter-preparation");
  assert.strictEqual(
    ownedPlayerUnloadCalls,
    1,
    "Stopping a phase must unload the player owned by the playback transaction even when active/cache pointers no longer reference it.",
  );

  let fallbackUtterance = null;
  const fallbackPreparation = [];
  const fallbackState = {
    currentTurn: { id: "question-1" },
    browserTtsUtterance: null,
  };
  const fallbackWindow = {
    SpeechSynthesisUtterance: class {
      constructor(text) { this.text = text; }
    },
    speechSynthesis: {
      cancel() {},
      speak(utterance) { fallbackUtterance = utterance; },
    },
  };
  const browserFallback = new Function(
    "state",
    "window",
    "isActivePracticeSession",
    "resolvedExaminerText",
    "clearAutoNextTimeout",
    "stopExaminerPlayback",
    "setExaminerListeningUi",
    "text",
    "beginPreparation",
    `
      function canUseBrowserExaminerFallback() {${functionBody(app, "canUseBrowserExaminerFallback")}}
      function playBrowserExaminerFallback(sessionId, turn, reason = "browser-fallback") {${functionBody(app, "playBrowserExaminerFallback")}}
      return playBrowserExaminerFallback;
    `,
  )(
    fallbackState,
    fallbackWindow,
    () => true,
    (turn) => turn.question,
    () => null,
    () => null,
    () => null,
    () => null,
    (...args) => fallbackPreparation.push(args),
  );
  const fallbackTurn = { id: "question-1", question: "What is your full name?" };
  assert.strictEqual(browserFallback(1, fallbackTurn, "network-failed"), true);
  assert.strictEqual(fallbackUtterance.text, fallbackTurn.question, "The fallback must speak the same question that is visible.");
  assert.strictEqual(fallbackPreparation.length, 0, "Preparation must wait until the fallback voice ends.");
  fallbackUtterance.onend();
  assert.strictEqual(fallbackPreparation.length, 1, "The normal preparation countdown starts only after browser fallback playback ends.");

  const phaseState = {
    status: "examiner_loading",
    currentTurn: { id: "question-1" },
  };
  const phasePlayback = { turnId: "question-1" };
  const currentPlaybackStillMatches = new Function(
    "state",
    "isActivePracticeSession",
    "isCurrentExaminerPlayback",
    "EXAMINER_PLAYBACK_STATUSES",
    `return function currentExaminerTurnStillMatches(sessionId, turnId, playback) {${functionBody(app, "currentExaminerTurnStillMatches")}};`,
  )(
    phaseState,
    () => true,
    () => true,
    new Set(["examiner_loading", "examiner_playing"]),
  );
  assert.strictEqual(
    currentPlaybackStillMatches(4, "question-1", phasePlayback),
    true,
    "The active playback transaction must remain valid while loading/listening.",
  );
  phaseState.status = "preparing";
  assert.strictEqual(
    currentPlaybackStillMatches(4, "question-1", phasePlayback),
    false,
    "A late audio callback must be rejected after the UI enters preparation.",
  );
  phaseState.status = "recording";
  assert.strictEqual(
    currentPlaybackStillMatches(4, "question-1", phasePlayback),
    false,
    "A late audio callback must be rejected after recording starts.",
  );

  assert.match(
    functionBody(app, "beginPreparation"),
    /stopExaminerPlayback\(["']begin-preparation["']\)/,
    "Entering preparation must silence every examiner player before starting the countdown.",
  );
  const startRecordingBody = functionBody(app, "startRecording");
  const recordingStopIndex = startRecordingBody.indexOf('stopExaminerPlayback("start-recording")');
  const recordingStateIndex = startRecordingBody.indexOf('state.status = "recording"');
  const microphoneIndex = startRecordingBody.indexOf("getSpeakingAudioStream()");
  assert.ok(
    recordingStopIndex >= 0
      && recordingStopIndex < recordingStateIndex
      && recordingStopIndex < microphoneIndex,
    "Recording must silence examiner audio before switching state or opening the microphone.",
  );

  fakeWindow.Howl = class SilentLoadingHowl {
    constructor() {}
    stop() {}
    unload() {}
  };
  const loadingPlayer = new Player();
  const pendingLoad = loadingPlayer.load({
    sourceUrl: "/audio/warming-identity.mp3",
    playbackUrl: "/audio/warming-identity.mp3",
  });
  const loadOutcome = pendingLoad.then(
    () => ({ status: "resolved" }),
    (error) => ({ status: "rejected", message: error.message }),
  );
  loadingPlayer.unload("practice-view-reset");
  const cancelled = await Promise.race([
    loadOutcome,
    new Promise((resolve) => setTimeout(() => resolve({ status: "still-pending" }), 30)),
  ]);
  assert.strictEqual(cancelled.status, "rejected", "Unloading a warming player must settle its load promise.");
  assert.match(cancelled.message, /practice-view-reset|cancel/i);

  console.log("Speaking examiner-audio playback watchdog checks passed.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
