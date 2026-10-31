const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../web/static/interviewer-avatar.js"), "utf8");
const app = fs.readFileSync(path.join(__dirname, "../web/static/app.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../web/static/index.html"), "utf8");
const urls = fs.readFileSync(path.join(__dirname, "../backend_django/config/urls.py"), "utf8");

function harness({ active = true, reducedMotion = false } = {}) {
  const classSet = (el) => ({ add: (n) => el.classes.add(n), remove: (n) => el.classes.delete(n), contains: (n) => el.classes.has(n),
    toggle: (n, on) => ((on ?? !el.classes.has(n)) ? el.classes.add(n) : el.classes.delete(n)) });
  class Element {
    constructor() { this.classes = new Set(); this.classList = classSet(this); this.dataset = {}; this.attrs = {}; this.layers = []; this.offsetWidth = 0; }
    set className(value) { this.classes = new Set(value.split(/\s+/).filter(Boolean)); this.classList = classSet(this); }
    set innerHTML(markup) { // the switchable layers are what the avatar toggles
      this.layers = [...markup.matchAll(/<g class="iv-iv-layer" data-layer="([\w-]+)">/g)].map(([, name]) => {
        const layer = new Element();
        layer.dataset.layer = name;
        return layer;
      });
      this.markup = markup;
    }
    setAttribute(name, value) { this.attrs[name] = value; }
    querySelectorAll(selector) { return selector === ".iv-iv-layer" ? this.layers : []; }
    querySelector() { return null; }
    after(el) { this.next = el; }
    prepend(el) { this.first = el; }
  }
  const kicker = new Element();
  const pane = new Element();
  pane.querySelector = (selector) => (selector === "#promptKicker" ? kicker : null);
  let now = 0;
  const timers = new Map();
  let seq = 0;
  const schedule = (fn, ms, repeat) => { seq += 1; timers.set(seq, { fn, at: now + ms, ms, repeat }); return seq; };
  const window = {
    setTimeout: (fn, ms) => schedule(fn, ms, false),
    setInterval: (fn, ms) => schedule(fn, ms, true),
    clearTimeout: (id) => timers.delete(id),
    clearInterval: (id) => timers.delete(id),
    matchMedia: () => ({ matches: reducedMotion }),
  };
  const context = { window, document: { createElement: () => new Element() }, Math };
  vm.runInNewContext(source, context);
  const flags = { active };
  window.IELTSInterviewer.create({ host: () => pane, active: () => flags.active });
  const api = window.IELTSInterviewer;
  // advance the fake clock, running timers in order
  const fire = (ms) => {
    const end = now + ms;
    for (;;) {
      const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!due) break;
      const [id, t] = due;
      now = t.at;
      if (t.repeat) t.at += t.ms; else timers.delete(id);
      t.fn();
    }
    now = end;
  };
  const avatar = () => kicker.next;
  const on = () => new Set(avatar().layers.filter((l) => l.classes.has("is-on")).map((l) => l.dataset.layer));
  return { api, flags, fire, avatar, on, timers };
}

test("it sits under the PROMPT label and shows only on practice pages (interview and IELTS)", () => {
  const env = harness({ active: false });
  env.api.sync();
  assert.equal(env.avatar(), undefined);                  // not built until a page needs it
  env.flags.active = true;
  env.api.sync();
  assert.equal(env.avatar().id, "ivInterviewer");
  assert.equal(env.avatar().classes.has("hidden"), false);
  assert.match(env.avatar().markup, /shape-rendering="crispEdges"/);
  assert.deepEqual([...env.on()].sort(), ["eyes-open", "mouth-closed"]);
  env.flags.active = false;
  env.api.sync();
  assert.equal(env.avatar().classes.has("hidden"), true);
});

test("he talks while the question plays, looks at the answer side while you answer, and thinks while the AI works", () => {
  const env = harness();
  env.api.sync();
  env.api.setStatus("examiner_playing");
  assert.equal(env.avatar().dataset.phase, "speaking");
  const mouths = new Set();
  for (let i = 0; i < 4; i += 1) { env.fire(120); mouths.add([...env.on()].find((n) => n.startsWith("mouth-"))); }
  assert.deepEqual([...mouths].sort(), ["mouth-closed", "mouth-mid", "mouth-open"]);
  env.api.setStatus("recording");
  assert.equal(env.avatar().dataset.phase, "listening");
  assert.ok(env.on().has("eyes-side"));
  assert.ok(env.on().has("mouth-closed"));
  env.api.setStatus("processing");
  assert.ok(env.on().has("eyes-up"));
  assert.ok(env.on().has("think"));
  env.api.setStatus("ready");
  assert.equal(env.avatar().dataset.phase, "idle");
  assert.equal(env.on().has("think"), false);
});

test("each answer gets a reaction: strong nods and smiles, adequate smiles, weak sweats — then back to calm", () => {
  const env = harness();
  env.api.sync();
  env.api.react("strong");
  assert.equal(env.avatar().dataset.reaction, "nod");
  assert.ok(env.on().has("mouth-smile"));
  env.fire(2200);
  assert.equal(env.avatar().dataset.reaction, "");
  assert.ok(env.on().has("mouth-closed"));
  env.api.react("adequate");
  assert.equal(env.avatar().dataset.reaction, "smile");
  env.api.react("weak");
  assert.equal(env.avatar().dataset.reaction, "sweat");
  for (const layer of ["sweat", "brows-worry", "mouth-frown"]) assert.ok(env.on().has(layer), layer);
  env.fire(2600);
  assert.equal(env.on().has("sweat"), false);
  env.api.react("");                                      // no judgement (empty answer, AI failure): no reaction
  env.api.react("loud");
  assert.equal(env.avatar().dataset.reaction, "");
});

test("a reaction does not stop him talking: the next question's mouth keeps moving under a nod", () => {
  const env = harness();
  env.api.sync();
  env.api.setStatus("examiner_playing");
  env.api.react("strong");
  env.fire(240);
  assert.equal(env.avatar().dataset.reaction, "nod");
  assert.equal(env.on().has("mouth-smile"), false);
});

test("reduced motion: no mouth flapping or blinking, just the still faces", () => {
  const env = harness({ reducedMotion: true });
  env.api.sync();
  assert.equal(env.timers.size, 0);                       // no blink scheduled
  env.api.setStatus("examiner_playing");
  assert.ok(env.on().has("mouth-mid"));
  assert.equal(env.timers.size, 0);
});

test("leaving the page stops its timers", () => {
  const env = harness();
  env.api.sync();
  env.api.setStatus("examiner_playing");
  assert.ok(env.timers.size > 0);
  env.flags.active = false;
  env.api.sync();
  assert.equal(env.timers.size, 0);
});

test("app.js feeds it the record status, each answer's judgement and the page; the asset is routed", () => {
  assert.match(html, /<script src="\/interviewer-avatar\.js\?v=[^"]+"><\/script>[\s\S]*<script src="\/app\.js\?v=/);
  assert.match(app, /window\.IELTSInterviewer\?\.create\?\.\(\{\n  host: \(\) => \$\("promptPane"\),\n  active: \(\) => isPracticeView\(state\.view\),\n  anchors: \(\) => \(\{ circle: \$\("recordControl"\)/);
  assert.match(app, /const look = RECORD_STATUS_LOOK\[status\] \|\| status;\n  window\.IELTSInterviewer\?\.setStatus\?\.\(look\);/);
  assert.match(app, /window\.IELTSInterviewer\?\.react\?\.\(payload\?\.interview_signal\);/);
  assert.match(app, /window\.IELTSInterviewer\?\.sync\?\.\(\);/);
  assert.match(urls, /path\("interviewer-avatar\.js", frontend_asset, \{"asset_path": "interviewer-avatar\.js"\}/);
});
