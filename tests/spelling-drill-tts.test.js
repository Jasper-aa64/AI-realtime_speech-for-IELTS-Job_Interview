const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const spellingDrillSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "spelling-drill.js"), "utf8");

function createElement() {
  const handlers = {};
  return {
    handlers,
    addEventListener(type, fn) {
      handlers[type] = handlers[type] || [];
      handlers[type].push(fn);
    },
    querySelector() {
      return null;
    },
    dispatch(type, event) {
      for (const fn of handlers[type] || []) fn(event);
    },
  };
}

function createControllerHarness() {
  const spoken = [];
  const voices = [
    { name: "Google US English", lang: "en-US", localService: false, default: true },
    { name: "Microsoft Jenny Online (Natural) - English (United States)", lang: "en-US", localService: true },
  ];
  const root = createElement();
  const sideList = createElement();

  function SpeechSynthesisUtterance(text) {
    this.text = text;
    this.volume = 1;
    this.rate = 1;
    this.lang = "";
    this.voice = null;
  }

  const window = {
    speechSynthesis: {
      speaking: false,
      pending: false,
      getVoices: () => voices,
      speak: (utterance) => spoken.push(utterance),
      cancel: () => {},
      resume: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
    },
    SpeechSynthesisUtterance,
    setTimeout: (fn) => fn(),
  };

  const context = {
    window,
    document: { querySelectorAll: () => [] },
    SpeechSynthesisUtterance,
    setTimeout: window.setTimeout,
  };
  vm.createContext(context);
  vm.runInContext(spellingDrillSource, context);

  const state = {
    spellingDrill: {
      _drillReady: true,
      view: "drill",
      phase: "ready",
      scope: "due",
      items: [],
      stats: {},
      queue: [{
        word_id: "w1",
        correct_spelling: "example",
        normalized: "example",
        chinese_gloss: "例子",
      }],
      queuePos: 0,
      requeueMap: {},
      completedWordIds: new Set(),
      doneCount: 0,
      queueInitialLen: 1,
      result: null,
      submitSeq: 0,
    },
  };

  const controller = context.window.IELTSSpellingDrill.createSpellingDrillController({
    state,
    $: (id) => (id === "spellingPracticeCard" ? root : id === "spellingDrillList" ? sideList : null),
    escapeHtml: (value) => String(value || ""),
    api: async () => ({ items: [], stats: {} }),
  });
  controller.bindSpellingDrillEvents();

  return { root, spoken };
}

function firstTypingGesture(harness) {
  harness.root.dispatch("keydown", {
    key: "e",
    isComposing: false,
    preventDefault() {},
  });
}

{
  const harness = createControllerHarness();
  firstTypingGesture(harness);
  assert.equal(harness.spoken[0]?.voice?.name, "Google US English");
}

{
  const harness = createControllerHarness();
  firstTypingGesture(harness);
  assert.equal(harness.spoken[0]?.text, "example");
  assert.equal(harness.spoken[0]?.volume, 0);
}

assert.doesNotMatch(
  spellingDrillSource,
  /!word\s*\|\|\s*!typed\.trim\(\)/,
  "Spelling drill should allow a blank answer to be submitted as a wrong attempt."
);

assert.doesNotMatch(
  spellingDrillSource,
  /data-spelling-continue/,
  "Spelling drill should not render or depend on a separate Next button after reveal."
);

assert.match(
  spellingDrillSource,
  /e\.key\s*===\s*"Enter"[\s\S]{0,500}gotoNext\(\)/,
  "After answer reveal, Enter should advance to the next word."
);

assert.match(
  spellingDrillSource,
  /NEXT_HINT_DELAY_MS\s*=\s*4000/,
  "The post-answer Enter hint should wait four seconds before becoming visible."
);

assert.match(
  spellingDrillSource,
  /_nextHintVisible/,
  "The post-answer Enter hint should be hidden first, then revealed without changing the answer flow."
);

assert.match(
  spellingDrillSource,
  /isBlankAttempt/,
  "Blank spelling submissions should not show a scary sync-failure warning."
);

assert.match(
  spellingDrillSource,
  /continueWrongResultWithTypedKey/,
  "After a wrong spelling result, typing a letter should advance into the retry and keep that first letter."
);
