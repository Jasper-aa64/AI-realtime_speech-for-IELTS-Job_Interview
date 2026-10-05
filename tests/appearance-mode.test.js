const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "../web/static/appearance.js"), "utf8");

function classList() {
  const values = new Set();
  return {
    add(...names) { names.forEach((name) => values.add(name)); },
    remove(name) { values.delete(name); },
    toggle(name, active) { active ? values.add(name) : values.delete(name); },
    contains(name) { return values.has(name); },
  };
}

function browser({ stored = {}, systemDark = false, denied = false, media = true, legacyListener = false } = {}) {
  const storage = new Map(Object.entries(stored));
  const writes = [];
  let change;
  const query = { matches: systemDark };
  if (legacyListener) query.addListener = (listener) => { change = listener; };
  else query.addEventListener = (_event, listener) => { change = listener; };
  const select = { value: "system" };
  const document = {
    documentElement: { classList: classList(), style: {} },
    body: { classList: classList() },
    getElementById: (id) => id === "appearanceModeSelect" ? select : null,
  };
  const context = {
    window: media ? { matchMedia: () => query } : {}, document,
    localStorage: {
      getItem(key) { if (denied) throw new Error("Storage denied"); return storage.get(key) ?? null; },
      setItem(key, value) { if (denied) throw new Error("Storage denied"); storage.set(key, value); writes.push([key, value]); },
    },
  };
  vm.runInNewContext(source, context);
  const appearance = context.window.IELTSAppearance;
  appearance.bootstrapAppearance();
  const bootDark = document.documentElement.classList.contains("theme-dark");
  const state = {};
  const controls = appearance.createAppearanceControls({ state });
  controls.loadDarkMode();
  return {
    state, controls, storage, writes, document, select, bootDark,
    changeSystem(dark) { query.matches = dark; change?.({ matches: dark }); },
  };
}

function expectAppearance(env, mode, dark) {
  assert.equal(env.state.appearanceMode, mode);
  assert.equal(env.state.darkMode, dark);
  assert.equal(env.document.documentElement.classList.contains("theme-dark"), dark);
  assert.equal(env.document.body.classList.contains("theme-dark"), dark);
  assert.equal(env.select.value, mode);
  assert.equal(env.document.documentElement.style.colorScheme, dark ? "dark" : "light");
  assert.equal(env.document.documentElement.classList.contains("boot-theme-dark"), false);
}

// Both startup phases honor manual legacy choices, explicit choices, and fresh defaults.
for (const systemDark of [false, true]) {
  for (const [stored, mode, dark] of [
    [{}, "system", systemDark],
    [{ "ielts-dark-mode": "1" }, "dark", true],
    [{ "ielts-dark-mode": "0" }, "light", false],
    [{ "ielts-appearance-mode": "system", "ielts-dark-mode": "1" }, "system", systemDark],
    [{ "ielts-appearance-mode": "light", "ielts-dark-mode": "1" }, "light", false],
    [{ "ielts-appearance-mode": "dark", "ielts-dark-mode": "0" }, "dark", true],
    [{ "ielts-appearance-mode": "invalid", "ielts-dark-mode": "0" }, "light", false],
    [{ "ielts-appearance-mode": "invalid", "ielts-dark-mode": "invalid" }, "system", systemDark],
  ]) {
    const env = browser({ stored, systemDark });
    assert.equal(env.bootDark, dark, "First paint and runtime must agree");
    expectAppearance(env, mode, dark);
    env.changeSystem(!systemDark);
    expectAppearance(env, mode, mode === "system" ? !systemDark : dark);
    assert.equal(env.writes.length, 0, "Startup and OS changes cannot overwrite saved preferences");
  }
}

const env = browser();
env.controls.applyAppearanceMode("dark");
expectAppearance(env, "dark", true);
assert.equal(env.storage.get("ielts-dark-mode"), "1");
env.changeSystem(true);
env.controls.applyAppearanceMode("light");
expectAppearance(env, "light", false);
assert.equal(env.storage.get("ielts-dark-mode"), "0");
env.controls.applyAppearanceMode("system");
expectAppearance(env, "system", true);
const beforeChange = env.writes.length;
env.changeSystem(false);
expectAppearance(env, "system", false);
assert.equal(env.writes.length, beforeChange);
const reloaded = browser({ stored: Object.fromEntries(env.storage), systemDark: true });
expectAppearance(reloaded, "system", true);
assert.equal(reloaded.bootDark, true);

for (const systemDark of [false, true]) {
  const denied = browser({ denied: true, systemDark });
  expectAppearance(denied, "system", systemDark);
  assert.equal(denied.bootDark, systemDark);
  denied.controls.applyAppearanceMode("light");
  expectAppearance(denied, "light", false);
  denied.changeSystem(!systemDark);
  expectAppearance(denied, "light", false);
}
expectAppearance(browser({ media: false }), "system", false);
const oldBrowser = browser({ legacyListener: true });
oldBrowser.changeSystem(true);
expectAppearance(oldBrowser, "system", true);
console.log("Appearance startup, legacy preferences, live system changes, persistence, and storage denial checks passed.");
