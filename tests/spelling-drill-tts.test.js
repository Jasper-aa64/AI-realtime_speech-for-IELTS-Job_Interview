const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const spellingDrillSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "spelling-drill.js"), "utf8");
const indexHtml = fs.readFileSync(path.join(__dirname, "..", "web", "static", "index.html"), "utf8");
const stylesSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "styles.css"), "utf8");

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

assert.match(
  indexHtml,
  /id="spellingAddDialog"\s+class="spelling-add-dialog hidden"/,
  "Spelling add dialog should not reuse the full-screen P1 corpus modal/backdrop."
);

assert.match(
  indexHtml,
  /class="language-takeaway-popup spelling-add-card"/,
  "Spelling add dialog should reuse the Language Takeaway popup shell."
);

assert.match(
  indexHtml,
  /id="spellingAddGlossPreview"\s+class="language-takeaway-dict-display spelling-add-gloss-preview hidden"/,
  "Spelling add dialog should render dictionary glosses through the shared tag card."
);

assert.match(
  indexHtml,
  /id="spellingAddGlossField"[\s\S]{0,180}for="spellingAddGloss"[\s\S]{0,180}<textarea id="spellingAddGloss"/,
  "Spelling add dialog should have one hideable Chinese field so the tag editor can replace it instead of rendering two boxes."
);

assert.doesNotMatch(
  stylesSource,
  /\.spelling-add-dialog\s*\{[^}]*background:\s*rgba/s,
  "Spelling add dialog should not darken the whole page with a black overlay."
);

assert.match(
  spellingDrillSource,
  /renderSpellingAddGlossPreview/,
  "Spelling add dialog should render Chinese dictionary senses with domain-tag markup."
);

assert.match(
  spellingDrillSource,
  /spellingAddSpeakBtn[\s\S]{0,220}addEventListener\("click"/,
  "Spelling add dialog should expose the Language Takeaway-style pronunciation button."
);

assert.match(
  indexHtml,
  /id="spellingAddSpeakBtn"\s+class="language-takeaway-tts-btn spelling-add-tts-btn"[\s\S]{0,260}<svg viewBox="0 0 24 24"/,
  "Spelling add dialog should reuse the single-word Language Takeaway speaker button, not a text glyph."
);

assert.match(
  indexHtml,
  /<div class="spelling-add-head-actions">[\s\S]*id="spellingAddStatus"[\s\S]*id="spellingAddSpeakBtn"[\s\S]*id="spellingAddSaveBtn"/,
  "Spelling add header actions should be ordered as status, speaker, then the rectangular Add button."
);

assert.match(
  spellingDrillSource,
  /function\s+renderSpellingAddGlossPreview\([\s\S]*preview\.contentEditable\s*=\s*"true"/,
  "Spelling add dictionary card should be directly editable like the Language Takeaway word card."
);
