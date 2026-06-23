import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../web/static/app.js", import.meta.url), "utf8");
const corpus = await readFile(new URL("../web/static/corpus-takeaway.js", import.meta.url), "utf8");
const onboarding = await readFile(new URL("../web/static/onboarding.js", import.meta.url), "utf8");
const css = await readFile(new URL("../web/static/styles.css", import.meta.url), "utf8");

test("only the account-security page still hard-gates guests; content is browsable", () => {
  assert.match(app, /const protectedViews = new Set\(\["accountSecurity"\]\);/);
  // The old wall (history/writing/corpus/... redirecting to login) is gone.
  assert.doesNotMatch(app, /const protectedViews = new Set\(\["history"/);
});

test("guest actions show a dismissible login prompt instead of a hard redirect", () => {
  const fn = app.match(/function promptGuestLogin\(reason, options = \{\}\)[\s\S]*?\n}/)?.[0] || "";
  assert.ok(fn, "expected promptGuestLogin definition");
  assert.match(fn, /继续参观/); // dismiss / keep browsing
  assert.match(fn, /注册/);     // register
  assert.match(fn, /前往登录/); // go to login
  assert.match(fn, /switchView\("register"/);
  assert.match(fn, /switchView\("login"/);
});

test("start-practice gate uses the prompt, not a forced jump to the login view", () => {
  const start = app.match(/state\.userExitedPractice = false;[\s\S]{0,400}?\n  const mode =/)?.[0] || "";
  assert.ok(start, "expected the startPractice guest gate region");
  assert.match(start, /promptGuestLogin\("登录后才能开始练习并保存完整报告。"\)/);
  assert.doesNotMatch(start, /switchView\(\s*["']login["']/);
});

test("the avatar opens the (guest-capable) account profile, never bounces to login", () => {
  const handler = app.match(/const handleAccountNavigation = \(event\) => \{[\s\S]*?\n  \};/)?.[0] || "";
  assert.ok(handler, "expected handleAccountNavigation");
  assert.doesNotMatch(handler, /switchView\("login"/);
  assert.match(handler, /switchView\("accountProfile"/);
});

test("guest-reachable data loaders bail cleanly instead of spinning/erroring on 401", () => {
  assert.match(app, /function renderGuestViewNotice\(container, line\)/);
  // app-side loaders seed the real history pipeline or fall back to the notice.
  for (const fnName of ["loadHistory", "loadWritingReports"]) {
    const body = app.match(new RegExp(`async function ${fnName}\\([^)]*\\) \\{[\\s\\S]{0,320}?(renderGuestViewNotice|seedGuestHistory)`))?.[0] || "";
    assert.ok(body, `expected ${fnName} to guard guests`);
  }
  assert.match(app, /async function loadWriting\(\) \{\s*\n\s*if \(!state\.account\.authenticated\)/);
  // module-side loaders seed real default data through the live render pipeline.
  for (const fnName of ["loadP1Corpus", "loadP2Corpus", "loadLanguageTakeaways", "loadWritingTakeaways"]) {
    const body = corpus.match(new RegExp(`async function ${fnName}\\([^)]*\\) \\{[\\s\\S]{0,400}?(SeedPayload)`))?.[0] || "";
    assert.ok(body, `expected ${fnName} to seed defaults for guests`);
  }
});

test("corpus library entry points prompt (dismissible) rather than hard-redirect", () => {
  assert.match(corpus, /function guestGate\(reason, returnView\)/);
  assert.match(corpus, /guestGate\("登录后才能保存和复用你的 P1 语料库。", "p1Corpus"\)/);
  assert.match(corpus, /guestGate\("登录后才能保存和复用你的 P2 串题素材库。", "p2Corpus"\)/);
});

test("onboarding no longer auto-pops; the manual launcher stays", () => {
  const boot = onboarding.match(/function boot\(\) \{[\s\S]*?\n  \}/)?.[0] || "";
  assert.ok(boot, "expected boot()");
  assert.match(boot, /addLauncher\(\)/);
  assert.doesNotMatch(boot, /setTimeout\([^)]*start\(false\)/);
  assert.doesNotMatch(boot, /start\(false\)/);
  // Manual entry points remain.
  assert.match(onboarding, /window\.IELTSOnboarding = \{/);
});

test("guest prompt and placeholder are styled", () => {
  assert.match(css, /\.guest-login-go\s*\{/);
  assert.match(css, /\.guest-login-register\s*\{/);
  assert.match(css, /\.guest-view-notice\s*\{/);
  assert.match(css, /\.guest-view-notice-login\s*\{/);
});
