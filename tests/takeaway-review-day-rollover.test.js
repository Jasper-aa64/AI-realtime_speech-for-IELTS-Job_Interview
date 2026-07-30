const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "corpus-takeaway.js"),
  "utf8"
);
const appSource = fs.readFileSync(
  path.join(__dirname, "..", "web", "static", "app.js"),
  "utf8"
);

function functionDefinition(name) {
  const declaration = source.indexOf(`function ${name}(`);
  assert.notStrictEqual(declaration, -1, `${name} must exist.`);
  const bodyStart = source.indexOf("{", declaration);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(declaration, index + 1);
  }
  assert.fail(`${name} must have a closed body.`);
}

const boundaryDelay = new Function(
  `${functionDefinition("msUntilNextTakeawayReviewDay")};
   return msUntilNextTakeawayReviewDay;`
)();

assert.equal(
  boundaryDelay(new Date(2026, 6, 17, 3, 59, 0, 0)),
  60 * 1000,
  "At 03:59 the watcher should refresh at the 04:00 review-day boundary."
);
assert.equal(
  boundaryDelay(new Date(2026, 6, 17, 4, 1, 0, 0)),
  (23 * 60 + 59) * 60 * 1000,
  "After 04:00 the next refresh should be scheduled for the following review day."
);

assert.match(
  source,
  /function startTakeawayReviewDayWatcher\(\)[\s\S]*visibilitychange[\s\S]*focus[\s\S]*pageshow/,
  "The watcher must recover after hidden tabs, sleep, and browser page restoration."
);
assert.match(
  source,
  /function refreshTakeawayReviewDay[\s\S]*todayKey\(\)[\s\S]*updateTakeawayReviewDots\(\)/,
  "A changed review-day key must recompute the navigation dots."
);
assert.match(
  source,
  /function refreshTakeawayReviewDay[\s\S]*renderTakeawayReviewPanel/,
  "An open Takeaway review panel must update together with its navigation dot."
);
assert.match(
  appSource,
  /startTakeawayReviewDayWatcher\(\);/,
  "App initialization must start exactly one review-day watcher."
);

let now = new Date(2026, 6, 17, 3, 59, 0, 0).getTime();
const scheduled = [];
const emitted = [];
class FakeDate extends Date {
  constructor(...args) {
    super(...(args.length ? args : [now]));
  }
  static now() {
    return now;
  }
}
class FakeEvent {
  constructor(type) {
    this.type = type;
  }
}
class FakeCustomEvent extends FakeEvent {
  constructor(type, options = {}) {
    super(type);
    this.detail = options.detail;
  }
}
const browserWindow = {
  addEventListener() {},
  clearTimeout() {},
  dispatchEvent(event) {
    emitted.push(event);
  },
  setTimeout(callback, delay) {
    scheduled.push({ callback, delay });
    return scheduled.length;
  },
};
const context = {
  window: browserWindow,
  document: {
    hidden: false,
    addEventListener() {},
  },
  Date: FakeDate,
  Event: FakeEvent,
  CustomEvent: FakeCustomEvent,
  console,
  Map,
  Set,
  Promise,
};
vm.runInNewContext(source, context, { filename: "corpus-takeaway.js" });
const controller = browserWindow.IELTSCorpusTakeaway.createCorpusTakeawayController({
  state: {
    view: "home",
    account: { authenticated: true },
    languageTakeaway: { items: [], loaded: false },
    writingTakeaway: { items: [], loaded: false },
  },
  $: () => null,
  api: async () => ({}),
});
controller.startTakeawayReviewDayWatcher();
assert.equal(scheduled.length, 1);
now = new Date(2026, 6, 17, 4, 0, 1, 0).getTime();
scheduled.shift().callback();
assert.equal(
  emitted.some((event) => event.type === "ielts:review-day-change" && event.detail?.day === "2026-07-17"),
  true,
  "The working Takeaway watcher must publish the shared review-day event for spelling."
);

console.log("Takeaway review day rollover checks passed.");
