const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../web/static/corner-morph.js"), "utf8");
const settle = async () => { for (let i = 0; i < 4; i += 1) await new Promise((resolve) => setImmediate(resolve)); };

function harness() {
  class Element {
    constructor(rect = { left: 0, top: 0, right: 0, width: 0, height: 0 }) {
      this.rect = rect; this.style = {}; this.attrs = {}; this.handlers = {}; this.hidden = true; this.children = [];
      this.classes = new Set();
      this.classList = { add: (n) => this.classes.add(n), remove: (n) => this.classes.delete(n), toggle: (n, on) => (on ? this.classes.add(n) : this.classes.delete(n)) };
      this.animations = [];
    }
    getBoundingClientRect() { return this.rect; }
    setAttribute(name, value) { this.attrs[name] = value; }
    addEventListener(type, callback) { (this.handlers[type] ||= []).push(callback); }
    emit(type, event = {}) { (this.handlers[type] || []).forEach((callback) => callback(event)); }
    contains(node) { return node === this || this.children.includes(node); }
    focus() {}
    getAnimations() { return this.animations; }
    animate() {
      let resolve;
      const animation = { finished: new Promise((r) => { resolve = r; }), cancel: () => {}, finish: () => resolve() };
      this.animations.push(animation);
      this.last = animation;
      return animation;
    }
  }
  const document = new Element();
  const window = new Element();
  window.innerWidth = 1440;
  window.setTimeout = (callback) => { callback(); return 1; };
  window.clearTimeout = () => {};
  const context = vm.createContext({ window, document });
  vm.runInContext(source, context);
  return { Element, document, window, morph: window.IELTSCornerMorph };
}

test("top-left anchor pins the card to the trigger's left edge", () => {
  const { Element, morph } = harness();
  const trigger = new Element({ left: 12, top: 8, right: 180, width: 168, height: 46 });
  const card = new Element({ left: 12, top: 8, right: 282, width: 270, height: 180 });
  const control = morph.create({ trigger, card, anchor: "top-left" });
  control.open();
  assert.equal(card.hidden, false);
  assert.equal(card.style.left, "12px");
  assert.equal(card.style.right, "auto");
  assert.equal(card.style.top, "8px");
});

test("top-right anchor grows leftwards from the avatar", () => {
  const { Element, morph } = harness();
  const avatar = new Element({ left: 1384, top: 6, right: 1424, width: 40, height: 40 });
  const card = new Element({ left: 1144, top: 6, right: 1424, width: 280, height: 320 });
  const lift = new Element();
  const control = morph.create({ trigger: avatar, card, anchor: "top-right", lift, closedRadius: "999px" });
  control.open();
  assert.equal(card.style.right, "16px");
  assert.equal(card.style.left, "auto");
  assert.ok(lift.classes.has("has-corner-morph-open"), "the bar holding the card is lifted above the page");
});

test("closing hides the card after the morph and drops the lift; reopening mid-close wins", async () => {
  const { Element, morph } = harness();
  const trigger = new Element({ left: 0, top: 0, right: 40, width: 40, height: 40 });
  const card = new Element({ left: 0, top: 0, right: 280, width: 280, height: 300 });
  const lift = new Element();
  const control = morph.create({ trigger, card, lift });
  control.open();
  control.close();
  const closing = card.last;
  control.open();
  closing.finish();
  await settle();
  assert.equal(card.hidden, false, "a close that was overtaken by a reopen must not hide the card");
  control.close();
  card.last.finish();
  await settle();
  assert.equal(card.hidden, true);
  assert.equal(lift.classes.has("has-corner-morph-open"), false);
});

test("hover opens and leaving closes for mouse pointers only", () => {
  const { Element, morph } = harness();
  const root = new Element();
  const trigger = new Element({ left: 0, top: 0, right: 40, width: 40, height: 40 });
  const card = new Element({ left: 0, top: 0, right: 280, width: 280, height: 300 });
  root.children.push(trigger, card);
  const control = morph.create({ trigger, card, root });
  root.emit("pointerenter", { pointerType: "touch" });
  assert.equal(control.isOpen(), false);
  root.emit("pointerenter", { pointerType: "mouse" });
  assert.equal(control.isOpen(), true);
  root.emit("pointerleave", { pointerType: "mouse", relatedTarget: null });
  assert.equal(control.isOpen(), false);
});

test("contents stay inert to the pointer until the morph settles", async () => {
  const { Element, morph } = harness();
  const trigger = new Element({ left: 0, top: 0, right: 44, width: 44, height: 44 });
  const card = new Element({ left: 0, top: 0, right: 272, width: 272, height: 346 });
  const control = morph.create({ trigger, card, anchor: "top-right", closedRadius: "22px", openRadius: "22px" });
  control.open();
  assert.ok(card.classes.has("is-morphing"));
  card.last.finish();
  await settle();
  assert.equal(card.classes.has("is-morphing"), false);
});
