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

test("guest login prompt is a simple two-option (登录 / 取消) dialog", () => {
  const fn = app.match(/function promptGuestLogin\(reason, options = \{\}\)[\s\S]*?\n}/)?.[0] || "";
  assert.ok(fn, "expected promptGuestLogin definition");
  assert.match(fn, /取消/);   // cancel / keep browsing
  assert.match(fn, />登录</); // go to login
  assert.match(fn, /switchView\("login"/);
  // Only the two options — no register / 继续参观 buttons.
  assert.doesNotMatch(fn, /继续参观/);
  assert.doesNotMatch(fn, /switchView\("register"/);
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

test("guests may browse the corpus library; editing is gated at the edit actions", () => {
  assert.match(corpus, /function guestGate\(reason, returnView\)/);
  // Library ENTRY is no longer gated — guests browse the seeded cards.
  assert.doesNotMatch(corpus, /guestGate\("登录后才能保存和复用你的 P1 语料库。", "p1Corpus"\)/);
  assert.doesNotMatch(corpus, /guestGate\("登录后才能保存和复用你的 P2 串题素材库。", "p2Corpus"\)/);
  // EDIT actions (P1/P2 corpus + P3 follow-up + bank editors) gate guests.
  assert.match(corpus, /guestGate\("登录后才能编辑和保存你的 P1 语料库。", "p1Corpus"\)/);
  assert.match(corpus, /guestGate\("登录后才能编辑和保存你的 P2 串题素材库。", "p2Corpus"\)/);
  assert.match(corpus, /guestGate\("登录后才能编辑和保存这道题卡的正文素材。", "p2Corpus"\)/);
  assert.match(corpus, /guestGate\("登录后才能编辑这道题卡的 P3 追问素材。", "p2Corpus"\)/);
  // Direct-practice (题卡播放) from a library card is gated too.
  assert.match(corpus, /guestGate\("登录后才能用这道题卡开始 P2 练习。", "p2Corpus"\)/);
});

test("P3 browse + generation are gated for guests", () => {
  const picker = app.match(/async function openP3BankPicker\(\)[\s\S]*?\n  const list/)?.[0] || "";
  assert.match(picker, /!state\.account\.authenticated/);
  assert.match(picker, /promptGuestLogin\("登录后才能浏览 P3 题卡并生成追问。"\)/);
  const gen = app.match(/async function generateP3Plan\(options = \{\}\)[\s\S]*?if \(state\.p3PlanLoading\)/)?.[0] || "";
  assert.match(gen, /promptGuestLogin\("登录后才能生成 P3 追问。"\)/);
});

test("writing frame fill + customize are gated for guests", () => {
  const apply = app.match(/async function applyWritingFrame\(\)[\s\S]*?currentWritingFrameKey/)?.[0] || "";
  assert.match(apply, /promptGuestLogin\("登录后才能填充和保存你的作文框架。"\)/);
  const editor = app.match(/async function openWritingFrameEditor\(\)[\s\S]*?currentWritingFrameKey/)?.[0] || "";
  assert.match(editor, /promptGuestLogin\("登录后才能定制和保存你的作文框架。"\)/);
  // The slash path gates before clearing the textarea.
  assert.match(app, /if \(v !== "\/frame" && v !== "\/myframe"\) return false;\s*\n\s*if \(!state\.account\.authenticated\)/);
});

test("entering the corpus library is allowed (not gated) from the practice screen", () => {
  // The practice-screen entry buttons just navigate; no guest guard wraps them.
  assert.match(app, /\$\("openP1CorpusBtn"\)\?\.addEventListener\("click", openP1CorpusLibrary\)/);
  assert.match(app, /\$\("openP2CorpusBtn"\)\?\.addEventListener\("click", openP2CorpusLibrary\)/);
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
