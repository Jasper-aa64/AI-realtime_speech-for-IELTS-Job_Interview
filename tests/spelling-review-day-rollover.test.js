const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function classList() {
  const values = new Set();
  return {
    add: (...names) => names.forEach((name) => values.add(name)),
    remove: (...names) => names.forEach((name) => values.delete(name)),
    toggle(name, force) {
      const next = force === undefined ? !values.has(name) : Boolean(force);
      if (next) values.add(name);
      else values.delete(name);
      return next;
    },
    contains: (name) => values.has(name),
  };
}

const listeners = new Map();
const dueDot = {
  classList: classList(),
  dataset: {},
  setAttribute(name, value) {
    if (name === "data-count") this.dataset.count = String(value);
  },
};
const typedInput = { value: "" };
const elements = {
  spellingDrillDueDot: dueDot,
  spellingTypedInput: typedInput,
};
const requests = [];
let nextPayload = {
  items: [{ word_id: "fresh", correct_spelling: "fresh" }],
  stats: {
    due: 1,
    active: 4,
    mastered: 2,
    accuracy: 0.75,
    review_day_start: "2026-07-30T04:00:00+08:00",
  },
};

const windowObject = {
  addEventListener(type, callback) {
    if (!listeners.has(type)) listeners.set(type, []);
    listeners.get(type).push(callback);
  },
  dispatchEvent(event) {
    return Promise.all((listeners.get(event.type) || []).map((callback) => callback(event)));
  },
  clearTimeout() {},
  setTimeout() {
    return 1;
  },
};

const context = {
  window: windowObject,
  document: {
    activeElement: null,
    querySelectorAll: () => [],
  },
  Node: { TEXT_NODE: 3, ELEMENT_NODE: 1 },
  Event: class Event {
    constructor(type) {
      this.type = type;
    }
  },
  Audio: class Audio {},
  console,
  Map,
  Set,
  Promise,
  setTimeout,
  clearTimeout,
};

const source = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "spelling-drill.js"),
  "utf8"
);
vm.runInNewContext(source, context, { filename: "spelling-drill.js" });

const state = {
  view: "home",
  account: { authenticated: true },
  spellingDrill: { _drillReady: false, items: [], stats: {}, scope: "due" },
};
const controller = windowObject.IELTSSpellingDrill.createSpellingDrillController({
  state,
  $: (id) => elements[id] || null,
  escapeHtml: (value) => String(value ?? ""),
  api: async (url) => {
    requests.push(url);
    return nextPayload;
  },
});

assert.equal(
  typeof controller.bindSpellingReviewDayRefresh,
  "function",
  "The spelling controller must expose its review-day event binding."
);
assert.equal(
  typeof controller.refreshSpellingReviewDay,
  "function",
  "The spelling controller must expose a refresh operation for the shared day watcher."
);

controller.bindSpellingReviewDayRefresh();
assert.equal(
  listeners.get("ielts:review-day-change")?.length,
  1,
  "Spelling must subscribe once to the shared 4 AM review-day event."
);

(async () => {
  await windowObject.dispatchEvent({ type: "ielts:review-day-change", detail: { day: "2026-07-30" } });
  assert.deepEqual(
    requests,
    ["/api/writing/spelling-words?scope=due"],
    "A review-day change must fetch the new due batch without waiting for navigation."
  );
  assert.equal(dueDot.dataset.count, "1");
  assert.equal(dueDot.classList.contains("hidden"), false);

  const oldQueue = [{ word_id: "old", correct_spelling: "old" }];
  Object.assign(state.spellingDrill, {
    view: "drill",
    phase: "ready",
    scope: "due",
    itemsScope: "due",
    queue: oldQueue,
    queuePos: 0,
    queueInitialLen: 1,
    sessionReviewDayStart: "2026-07-30T04:00:00+08:00",
    doneCount: 0,
    result: null,
  });
  state.view = "spellingDrill";
  typedInput.value = "o";
  nextPayload = {
    items: [{ word_id: "tomorrow", correct_spelling: "tomorrow" }],
    stats: {
      due: 1,
      active: 5,
      mastered: 2,
      accuracy: 0.8,
      review_day_start: "2026-07-31T04:00:00+08:00",
    },
  };

  await controller.refreshSpellingReviewDay();
  assert.strictEqual(
    state.spellingDrill.queue,
    oldQueue,
    "Cross-day refresh must not replace a queue while the learner is typing."
  );
  assert.equal(
    state.spellingDrill.pendingReviewDayPayload?.items?.[0]?.word_id,
    "tomorrow",
    "The fresh day batch should wait until the active answer is finished."
  );

  await controller.loadSpellingDrill({ force: false, resetQueue: true });
  assert.equal(
    state.spellingDrill.pendingReviewDayPayload?.items?.[0]?.word_id,
    "tomorrow",
    "Sidebar navigation must not discard a deferred cross-day payload."
  );

  state.spellingDrill.pendingReviewDayPayload = null;
  nextPayload = {
    items: [{ word_id: "same-day", correct_spelling: "same-day" }],
    stats: {
      due: 1,
      active: 5,
      mastered: 2,
      accuracy: 0.8,
      review_day_start: "2026-07-30T04:00:00+08:00",
    },
  };
  state.spellingDrill.scopeCache = {
    due: { payload: nextPayload, epoch: state.spellingDrill.cacheEpoch },
  };
  await controller.loadSpellingDrill({ force: false, resetQueue: true });
  assert.strictEqual(
    state.spellingDrill.queue,
    oldQueue,
    "Leaving and returning through the sidebar on the same review day must preserve the active queue."
  );
  assert.equal(
    typedInput.value,
    "o",
    "Same-day navigation must not clear the learner's in-progress spelling."
  );

  typedInput.value = "";
  nextPayload = {
    items: [{ word_id: "next-day", correct_spelling: "next-day" }],
    stats: {
      due: 1,
      active: 5,
      mastered: 2,
      accuracy: 0.8,
      review_day_start: "2026-07-31T04:00:00+08:00",
    },
  };
  state.spellingDrill.scopeCache = {};
  await controller.loadSpellingDrill({ force: true, resetQueue: true });
  assert.equal(
    state.spellingDrill.queue[0]?.word_id,
    "next-day",
    "A genuinely new review day must replace the previous day's queue."
  );

  Object.assign(state.spellingDrill, {
    phase: "ready",
    scope: "due",
    itemsScope: "due",
    queueInitialLen: 6,
    doneCount: 6,
    dueDotOverride: null,
  });
  assert.equal(
    typeof controller.getLiveDueDotCount,
    "function",
    "The app shell needs the controller's live queue count so a late prefetch cannot restore a completed red dot."
  );
  assert.equal(
    controller.getLiveDueDotCount(),
    0,
    "Finishing the local due queue must report zero immediately, before server attempt writes settle."
  );

  const completedQueue = [
    { word_id: "completed-a", correct_spelling: "completed-a" },
    { word_id: "completed-b", correct_spelling: "completed-b" },
  ];
  Object.assign(state.spellingDrill, {
    view: "drill",
    phase: "ready",
    scope: "due",
    itemsScope: "due",
    queue: completedQueue,
    queuePos: completedQueue.length,
    queueInitialLen: completedQueue.length,
    doneCount: completedQueue.length,
    sessionReviewDayStart: "2026-07-31T04:00:00+08:00",
    pendingReviewDayPayload: null,
  });
  nextPayload = {
    items: [{ word_id: "late-same-day", correct_spelling: "flustered" }],
    stats: {
      due: 1,
      active: 5,
      mastered: 2,
      accuracy: 0.8,
      review_day_start: "2026-07-31T04:00:00+08:00",
    },
  };
  await controller.refreshSpellingReviewDay();
  assert.strictEqual(
    state.spellingDrill.queue,
    completedQueue,
    "A same-day background refresh must not reopen a completed daily queue with a late server word."
  );
  assert.equal(
    state.spellingDrill.queuePos,
    completedQueue.length,
    "A same-day refresh must preserve the completed state instead of starting a second wave."
  );

  console.log("Spelling review day rollover checks passed.");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
