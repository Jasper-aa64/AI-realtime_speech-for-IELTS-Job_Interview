const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const source = fs.readFileSync(path.join(__dirname, "../web/static/native-bridge.js"), "utf8");

async function discover({ payload, noTransport = false, iframe = false, failure = false } = {}) {
  let constructed = 0;
  const window = { setTimeout, clearTimeout };
  window.top = iframe ? {} : window;
  if (!noTransport) {
    window.qt = { webChannelTransport: {} };
    window.QWebChannel = function (_transport, callback) {
      constructed += 1;
      if (failure) throw new Error("Transport failed");
      callback({ objects: { studioNative: { capabilities(done) { done(payload); } } } });
    };
  }
  vm.runInNewContext(source, { window });
  return { capabilities: await window.IELTSNativeBridge.ready, constructed };
}

test("ordinary browsers and subframes cannot enable desktop interview", async () => {
  for (const options of [{ noTransport: true }, { iframe: true }]) {
    const result = await discover(options);
    assert.equal(result.capabilities.mock_interview, false);
    assert.equal(result.constructed, 0);
  }
});
test("real channel metadata enables desktop but does not invent native audio", async () => {
  const result = await discover({ payload: { protocol_version: 1, desktop: true, mock_interview: true, native_audio: false } });
  assert.equal(result.capabilities.desktop, true);
  assert.equal(result.capabilities.mock_interview, true);
  assert.equal(result.capabilities.native_audio, false);
  assert.equal(result.constructed, 1);
  assert.equal(Object.isFrozen(result.capabilities), true);
});
test("malformed, foreign-origin, or incompatible capabilities fail closed", async () => {
  for (const payload of [null, { protocol_version: 2, desktop: true, mock_interview: true }, { protocol_version: 1, desktop: false, mock_interview: true }]) {
    assert.equal((await discover({ payload })).capabilities.mock_interview, false);
  }
  assert.equal((await discover({ failure: true })).capabilities.mock_interview, false);
});
