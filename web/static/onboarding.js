/*
 * onboarding.js — 新手导览 (guided onboarding tour)
 *
 * Self-contained, decoupled walkthrough for first-time users. Spotlights real
 * navigation elements (driver.js / Shepherd style) and shows illustrated cards
 * for the transient gestures that can't be reliably spotlighted live
 * (划词→译→加入 Takeaway, A/D 复习, Enter 继续).
 *
 * Drives entirely off the DOM — no app.js internals — so it can't drift from
 * the app. Auto-starts once for logged-in first-time users; replayable anytime
 * via the floating "教程" launcher or window.IELTSOnboarding.start().
 */
(function () {
  "use strict";

  var DONE_KEY = "ielts-onboarding-v1-done";
  var Z = 2147483000; // above app modals

  // ---------------------------------------------------------------- illustrations
  // Small, theme-aware inline SVGs used by the "gesture" steps.

  function illoSelectToTakeaway() {
    return (
      '<svg class="ob-illo" viewBox="0 0 320 168" role="img" aria-label="选中文字后点译，加入 Takeaway">' +
      '  <rect x="10" y="14" width="300" height="60" rx="12" fill="var(--ob-surface-2)" stroke="var(--ob-line)"/>' +
      '  <text x="26" y="40" class="ob-illo-text">it is going well, but I have to</text>' +
      '  <g class="ob-illo-sel">' +
      '    <rect x="24" y="48" width="176" height="20" rx="5" fill="var(--ob-clay-soft)"/>' +
      '    <text x="30" y="63" class="ob-illo-text ob-illo-strong">manage it quite carefully</text>' +
      '  </g>' +
      '  <g class="ob-illo-pop">' +
      '    <circle cx="220" cy="58" r="15" fill="var(--ob-clay)"/>' +
      '    <text x="220" y="63" text-anchor="middle" class="ob-illo-badge">译</text>' +
      '  </g>' +
      '  <path class="ob-illo-arrow" d="M170 86 C 170 104, 150 104, 150 118" fill="none" stroke="var(--ob-clay)" stroke-width="2" stroke-dasharray="3 4"/>' +
      '  <rect x="40" y="118" width="240" height="38" rx="10" fill="var(--ob-surface)" stroke="var(--ob-clay)"/>' +
      '  <text x="56" y="135" class="ob-illo-text ob-illo-strong">manage it quite carefully</text>' +
      '  <text x="56" y="150" class="ob-illo-sub">非常小心地管理 · 已翻译</text>' +
      '  <g transform="translate(214,128)"><rect width="54" height="20" rx="10" fill="var(--ob-clay)"/>' +
      '    <text x="27" y="14" text-anchor="middle" class="ob-illo-cta">加入</text></g>' +
      '</svg>'
    );
  }

  function illoReviewKeys() {
    return (
      '<svg class="ob-illo" viewBox="0 0 320 150" role="img" aria-label="复习卡片用 A 掌握 D 再练">' +
      '  <rect x="86" y="12" width="148" height="64" rx="12" fill="var(--ob-surface)" stroke="var(--ob-line)"/>' +
      '  <text x="160" y="42" text-anchor="middle" class="ob-illo-text ob-illo-strong">come up at the same time</text>' +
      '  <text x="160" y="61" text-anchor="middle" class="ob-illo-sub">同时出现</text>' +
      '  <g transform="translate(70,96)">' +
      '    <rect width="80" height="40" rx="9" fill="var(--ob-mint-soft)" stroke="var(--ob-mint)"/>' +
      '    <text x="20" y="26" text-anchor="middle" class="ob-illo-key" fill="var(--ob-mint)">A</text>' +
      '    <text x="54" y="25" text-anchor="middle" class="ob-illo-sub">掌握</text>' +
      '  </g>' +
      '  <g transform="translate(170,96)">' +
      '    <rect width="80" height="40" rx="9" fill="var(--ob-clay-soft)" stroke="var(--ob-clay)"/>' +
      '    <text x="20" y="26" text-anchor="middle" class="ob-illo-key" fill="var(--ob-clay)">D</text>' +
      '    <text x="55" y="25" text-anchor="middle" class="ob-illo-sub">再练</text>' +
      '  </g>' +
      '</svg>'
    );
  }

  function illoEnter() {
    return (
      '<svg class="ob-illo" viewBox="0 0 320 138" role="img" aria-label="拼写后按 Enter 继续">' +
      '  <rect x="48" y="16" width="224" height="44" rx="10" fill="var(--ob-surface-2)" stroke="var(--ob-line)"/>' +
      '  <text x="64" y="44" class="ob-illo-text ob-illo-strong">accommodation</text>' +
      '  <text x="250" y="44" text-anchor="end" class="ob-illo-check">✓</text>' +
      '  <g transform="translate(108,80)">' +
      '    <rect width="104" height="40" rx="9" fill="var(--ob-surface)" stroke="var(--ob-ink-soft)"/>' +
      '    <text x="52" y="25" text-anchor="middle" class="ob-illo-key" style="font-size:15px" fill="var(--ob-ink)">Enter ⏎</text>' +
      '  </g>' +
      '  <text x="160" y="132" text-anchor="middle" class="ob-illo-sub">拼对后按 Enter 继续下一个</text>' +
      '</svg>'
    );
  }

  function illoWelcome() {
    return (
      '<svg class="ob-illo ob-illo-welcome" viewBox="0 0 360 150" role="img" aria-label="欢迎">' +
      '  <circle cx="180" cy="74" r="58" fill="var(--ob-clay-soft)"/>' +
      '  <rect x="120" y="52" width="120" height="78" rx="10" fill="var(--ob-surface)" stroke="var(--ob-line)"/>' +
      '  <line x1="134" y1="72" x2="226" y2="72" stroke="var(--ob-line)" stroke-width="3" stroke-linecap="round"/>' +
      '  <line x1="134" y1="88" x2="208" y2="88" stroke="var(--ob-line)" stroke-width="3" stroke-linecap="round"/>' +
      '  <line x1="134" y1="104" x2="220" y2="104" stroke="var(--ob-line)" stroke-width="3" stroke-linecap="round"/>' +
      '  <circle cx="248" cy="48" r="18" fill="var(--ob-clay)"/>' +
      '  <text x="248" y="54" text-anchor="middle" class="ob-illo-badge" style="font-size:16px">译</text>' +
      '  <g transform="translate(86,40)"><circle r="10" fill="var(--ob-mint)"/><text y="5" text-anchor="middle" class="ob-illo-badge" style="font-size:12px">A</text></g>' +
      '  <g transform="translate(96,116)"><circle r="10" fill="var(--ob-clay)"/><text y="5" text-anchor="middle" class="ob-illo-badge" style="font-size:12px">D</text></g>' +
      '</svg>'
    );
  }

  // ---------------------------------------------------------------- steps
  var STEPS = [
    {
      kind: "welcome",
      title: "欢迎来到 IELTS Studio",
      body: "一个把「练 → 批改 → 复盘 → 复习」串成闭环的雅思口语 / 写作训练台。<br>约 1 分钟，带你认识每个核心功能与几个隐藏神器。",
      illustration: illoWelcome(),
    },
    {
      target: ".nav-primary",
      placement: "right",
      title: "左边是你的练习中心",
      body: "导航把功能分好了区：上半区练 <b>口语</b> 和 <b>写作</b>，下半区是 <b>语料库与复习</b>。先认识口语这块。",
    },
    {
      target: ".nav-exam-group",
      placement: "right",
      title: "口语练习：模考 + 单项",
      body: "<b>Mock</b> 是完整模考；<b>P1 / P2 / P3</b> 是单项专练。系统自动按「话题成组、练得少的优先」出题，你只管开口录音，考官会语音播题。",
    },
    {
      target: '[data-view="history"]',
      placement: "right",
      title: "口语报告：四维评分 + 7 分参考",
      body: "每次练完生成 <b>流利度 / 词汇 / 语法 / 发音</b> 四维评分 + 中文讲解，还附 <b>7 分参考答案</b>（可一键复制、支持 Markdown 自己改写）。",
    },
    {
      kind: "illustration",
      illustration: illoSelectToTakeaway(),
      title: "划词即收藏 ✦ 隐藏神器",
      body: "在报告或参考答案里，用鼠标 <b>选中任意好句</b> → 点出现的 <b>「译」</b> → 系统自动翻译好 → 一键 <b>加入 Takeaway</b> 或 <b>加入写作积累</b>。好表达不再用手抄。",
    },
    {
      target: '[data-view="takeawayBook"]',
      placement: "right",
      title: "Takeaway：记忆曲线复习",
      body: "收藏的表达都汇到这里。点右上角 <b>「开始」</b> → 听英文发音 → 用键盘 <b>A = 已掌握</b> / <b>D = 明天再练</b>。导航上的小红点 = 有到期复习。",
      illustration: illoReviewKeys(),
    },
    {
      target: '[data-view="spellingDrill"]',
      placement: "right",
      title: "拼写错词训练",
      body: "写作里拼错的词会 <b>自动收进来</b>，按记忆曲线安排。拼对一个后，直接按 <b>Enter</b> 继续下一个，不用找按钮。",
      illustration: illoEnter(),
    },
    {
      target: '[data-view="writing"]',
      placement: "right",
      title: "写作 & 语料库",
      body: "<b>每日写作</b>：Task 1 / Task 2 分大类题库 + AI 分段批改 + 写作模板。<b>语料库</b>：沉淀你自己的素材，结合 AI 内容自己整理，比直接让 AI 代写更扎实。",
    },
    {
      kind: "illustration",
      illustration: illoWelcome(),
      title: "就这些，去练吧 ✦",
      body: "右上角 <b>头像</b> 里有外观、账户和余额设置。随时点左下角的 <b>「教程」</b> 重看这份导览。祝你早日上岸 🎯",
      finish: true,
    },
  ];

  // ---------------------------------------------------------------- styles
  var CSS =
    '.ob-root{position:fixed;inset:0;z-index:' + Z + ';font-family:var(--nr-serif-body,"Newsreader",Georgia,serif);' +
    '--ob-surface:var(--panel,#fff);--ob-surface-2:#faf7f2;--ob-ink:var(--ink,#1c160f);--ob-ink-soft:#6f6557;' +
    '--ob-muted:var(--muted,#857a6a);--ob-line:var(--border-soft,rgba(28,20,15,.12));' +
    '--ob-clay:#c0664a;--ob-clay-dark:#a8543c;--ob-clay-soft:#f6e7df;' +
    '--ob-mint:#0f9f7a;--ob-mint-soft:#e1f6ee;--ob-dim:rgba(28,18,10,.60);}' +
    '.ob-root *{box-sizing:border-box;}' +
    // spotlight
    '.ob-spot{position:absolute;border-radius:14px;box-shadow:0 0 0 9999px var(--ob-dim),0 0 0 2px var(--ob-clay),0 12px 40px rgba(0,0,0,.28);' +
    'transition:all 360ms cubic-bezier(.4,.02,.2,1);pointer-events:none;}' +
    '.ob-spot::after{content:"";position:absolute;inset:-6px;border-radius:18px;border:2px solid var(--ob-clay);opacity:.5;animation:ob-pulse 1.8s ease-out infinite;}' +
    '@keyframes ob-pulse{0%{transform:scale(.98);opacity:.55;}70%{transform:scale(1.06);opacity:0;}100%{opacity:0;}}' +
    // full-screen dim for centered cards (no spotlight)
    '.ob-backdrop{position:absolute;inset:0;background:var(--ob-dim);backdrop-filter:blur(2px);}' +
    // card
    '.ob-card{position:absolute;width:360px;max-width:calc(100vw - 28px);background:var(--ob-surface);color:var(--ob-ink);' +
    'border:1px solid var(--ob-line);border-radius:18px;padding:20px 22px 18px;box-shadow:0 24px 60px rgba(28,18,10,.32);' +
    'animation:ob-rise 320ms cubic-bezier(.2,.7,.2,1) both;}' +
    '.ob-card.ob-center{position:relative;width:440px;}' +
    '.ob-center-wrap{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:20px;}' +
    '@keyframes ob-rise{from{opacity:0;transform:translateY(10px) scale(.985);}to{opacity:1;transform:none;}}' +
    '.ob-eyebrow{display:flex;align-items:center;gap:10px;font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;' +
    'color:var(--ob-clay-dark);font-weight:700;margin-bottom:10px;font-family:var(--nr-serif-body,Georgia,serif);}' +
    '.ob-dots{display:flex;gap:5px;margin-left:auto;}' +
    '.ob-dot{width:6px;height:6px;border-radius:50%;background:var(--ob-line);transition:all .25s;}' +
    '.ob-dot.on{background:var(--ob-clay);width:18px;border-radius:3px;}' +
    '.ob-title{font-family:var(--nr-serif-display,"Fraunces",Georgia,serif);font-size:21px;line-height:1.25;font-weight:600;margin:0 0 8px;letter-spacing:.01em;}' +
    '.ob-body{font-size:14.5px;line-height:1.62;color:var(--ob-ink-soft);margin:0;}' +
    '.ob-body b{color:var(--ob-ink);font-weight:700;}' +
    '.ob-illo{display:block;width:100%;height:auto;margin:14px 0 4px;border-radius:12px;}' +
    '.ob-illo-welcome{max-width:280px;margin:6px auto 8px;}' +
    '.ob-illo-text{font-family:var(--nr-serif-body,Georgia,serif);font-size:13px;fill:var(--ob-ink-soft);}' +
    '.ob-illo-strong{fill:var(--ob-ink);font-weight:600;}' +
    '.ob-illo-sub{font-size:11px;fill:var(--ob-muted);}' +
    '.ob-illo-badge{fill:#fff;font-size:14px;font-weight:700;font-family:var(--nr-serif-body,Georgia,serif);}' +
    '.ob-illo-cta{fill:#fff;font-size:11px;font-weight:700;}' +
    '.ob-illo-key{font-size:18px;font-weight:800;font-family:var(--nr-serif-body,Georgia,serif);}' +
    '.ob-illo-check{fill:var(--ob-mint);font-size:18px;font-weight:800;}' +
    '.ob-illo-sel rect{animation:ob-hl 2.4s ease-in-out infinite;}' +
    '.ob-illo-pop{animation:ob-popin 2.4s ease-in-out infinite;transform-origin:220px 58px;}' +
    '.ob-illo-arrow{stroke-dashoffset:40;animation:ob-dash 2.4s linear infinite;}' +
    '@keyframes ob-hl{0%,20%{opacity:0;}35%,100%{opacity:1;}}' +
    '@keyframes ob-popin{0%,35%{opacity:0;transform:scale(.4);}50%,100%{opacity:1;transform:scale(1);}}' +
    '@keyframes ob-dash{to{stroke-dashoffset:0;}}' +
    // footer
    '.ob-foot{display:flex;align-items:center;margin-top:18px;gap:10px;}' +
    '.ob-skip{background:none;border:none;color:var(--ob-muted);font-size:13px;cursor:pointer;padding:6px 2px;font-family:inherit;}' +
    '.ob-skip:hover{color:var(--ob-ink);}' +
    '.ob-spacer{flex:1;}' +
    '.ob-btn{font-family:inherit;font-size:14px;font-weight:600;border-radius:999px;cursor:pointer;border:1px solid transparent;padding:9px 18px;transition:all .15s;}' +
    '.ob-btn-ghost{background:none;border-color:var(--ob-line);color:var(--ob-ink-soft);}' +
    '.ob-btn-ghost:hover{border-color:var(--ob-ink-soft);color:var(--ob-ink);}' +
    '.ob-btn-primary{background:var(--ob-clay);color:#fff;box-shadow:0 6px 16px rgba(192,102,74,.35);}' +
    '.ob-btn-primary:hover{background:var(--ob-clay-dark);transform:translateY(-1px);}' +
    '.ob-close{position:absolute;top:12px;right:14px;width:26px;height:26px;border-radius:50%;border:none;background:var(--ob-surface-2);' +
    'color:var(--ob-muted);font-size:15px;cursor:pointer;line-height:1;}' +
    '.ob-close:hover{color:var(--ob-ink);}' +
    // launcher
    '.ob-launch{position:fixed;left:14px;bottom:14px;z-index:' + (Z - 5) + ';display:inline-flex;align-items:center;gap:7px;' +
    'background:var(--panel,#fff);color:#a8543c;border:1px solid rgba(192,102,74,.4);border-radius:999px;padding:8px 14px;' +
    'font-family:var(--nr-serif-body,Georgia,serif);font-size:13px;font-weight:600;cursor:pointer;box-shadow:0 6px 18px rgba(28,18,10,.12);' +
    'transition:all .16s;}' +
    '.ob-launch:hover{transform:translateY(-1px);box-shadow:0 10px 24px rgba(28,18,10,.18);border-color:#c0664a;}' +
    '.ob-launch .ob-q{display:inline-flex;align-items:center;justify-content:center;width:17px;height:17px;border-radius:50%;background:#c0664a;color:#fff;font-size:11px;}' +
    '@media (prefers-reduced-motion: reduce){.ob-root *{animation:none!important;transition:none!important;}}';

  // ---------------------------------------------------------------- engine
  var root = null;
  var idx = 0;

  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }

  function injectStyle() {
    if (document.getElementById("ob-style")) return;
    var s = document.createElement("style");
    s.id = "ob-style";
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function dotsHtml(active) {
    var h = "";
    for (var i = 0; i < STEPS.length; i++) h += '<span class="ob-dot' + (i === active ? " on" : "") + '"></span>';
    return h;
  }

  function clear() {
    if (root) root.innerHTML = "";
  }

  function render() {
    var step = STEPS[idx];
    clear();
    var isCentered = step.kind === "welcome" || step.kind === "illustration";
    var target = !isCentered && step.target ? document.querySelector(step.target) : null;
    if (!isCentered && !target) {
      // target missing → degrade to centered card so the tour never dead-ends
      isCentered = true;
    }

    var card = buildCard(step);

    if (isCentered) {
      var back = el("div", "ob-backdrop");
      var wrap = el("div", "ob-center-wrap");
      card.classList.add("ob-center");
      wrap.appendChild(card);
      root.appendChild(back);
      root.appendChild(wrap);
    } else {
      var spot = el("div", "ob-spot");
      root.appendChild(spot);
      root.appendChild(card);
      positionSpotlight(spot, target);
      positionCard(card, target, step.placement || "right");
      target.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }

  function buildCard(step) {
    var card = el("div", "ob-card");
    var stepNo = idx + 1;
    var eyebrow = el(
      "div",
      "ob-eyebrow",
      "<span>第 " + stepNo + " 步 / 共 " + STEPS.length + " 步</span>" + '<span class="ob-dots">' + dotsHtml(idx) + "</span>"
    );
    card.appendChild(eyebrow);
    card.appendChild(el("h3", "ob-title", step.title));
    card.appendChild(el("p", "ob-body", step.body));
    if (step.illustration) {
      var box = el("div", null, step.illustration);
      card.appendChild(box.firstChild);
    }

    var foot = el("div", "ob-foot");
    var skip = el("button", "ob-skip", step.finish ? "" : "跳过导览");
    skip.addEventListener("click", finish);
    foot.appendChild(skip);
    foot.appendChild(el("div", "ob-spacer"));
    if (idx > 0) {
      var prev = el("button", "ob-btn ob-btn-ghost", "上一步");
      prev.addEventListener("click", function () { go(idx - 1); });
      foot.appendChild(prev);
    }
    var next = el("button", "ob-btn ob-btn-primary", step.finish ? "开始使用 ✦" : (idx === 0 ? "开始导览" : "下一步"));
    next.addEventListener("click", function () { step.finish ? finish() : go(idx + 1); });
    foot.appendChild(next);
    card.appendChild(foot);

    var close = el("button", "ob-close", "✕");
    close.setAttribute("aria-label", "关闭导览");
    close.addEventListener("click", finish);
    card.appendChild(close);
    return card;
  }

  function positionSpotlight(spot, target) {
    var r = target.getBoundingClientRect();
    var pad = 8;
    spot.style.left = r.left - pad + "px";
    spot.style.top = r.top - pad + "px";
    spot.style.width = r.width + pad * 2 + "px";
    spot.style.height = r.height + pad * 2 + "px";
  }

  function positionCard(card, target, placement) {
    var r = target.getBoundingClientRect();
    var cw = card.offsetWidth || 360;
    var ch = card.offsetHeight || 220;
    var gap = 18;
    var vw = window.innerWidth, vh = window.innerHeight;
    var left, top;
    if (placement === "right") { left = r.right + gap; top = r.top + r.height / 2 - ch / 2; }
    else if (placement === "left") { left = r.left - gap - cw; top = r.top + r.height / 2 - ch / 2; }
    else if (placement === "top") { left = r.left + r.width / 2 - cw / 2; top = r.top - gap - ch; }
    else { left = r.left + r.width / 2 - cw / 2; top = r.bottom + gap; }
    // if right placement overflows, flip below the target
    if (placement === "right" && left + cw > vw - 12) { left = r.left; top = r.bottom + gap; }
    left = Math.max(12, Math.min(left, vw - cw - 12));
    top = Math.max(12, Math.min(top, vh - ch - 12));
    card.style.left = left + "px";
    card.style.top = top + "px";
  }

  function go(i) {
    if (i < 0 || i >= STEPS.length) return;
    idx = i;
    render();
  }

  function onKey(e) {
    if (!root) return;
    if (e.key === "Escape") finish();
    else if (e.key === "ArrowRight" || e.key === "Enter") { if (idx < STEPS.length - 1) go(idx + 1); else finish(); }
    else if (e.key === "ArrowLeft") { if (idx > 0) go(idx - 1); }
  }

  var reflow = function () { if (root) render(); };

  function start(fromLauncher) {
    if (root) return;
    injectStyle();
    idx = 0;
    root = el("div", "ob-root");
    document.body.appendChild(root);
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("resize", reflow);
    window.addEventListener("scroll", reflow, true);
    render();
  }

  function finish() {
    if (!root) return;
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("resize", reflow);
    window.removeEventListener("scroll", reflow, true);
    root.remove();
    root = null;
    document.body.style.overflow = "";
    try { localStorage.setItem(DONE_KEY, "1"); } catch (e) {}
  }

  // ---------------------------------------------------------------- launcher + auto
  function addLauncher() {
    if (document.querySelector(".ob-launch")) return;
    injectStyle();
    var b = el("button", "ob-launch", '<span class="ob-q">?</span><span>教程</span>');
    b.setAttribute("aria-label", "重新观看新手教程");
    b.addEventListener("click", function () { start(true); });
    document.body.appendChild(b);
  }

  function appReady() {
    if (document.body.classList.contains("app-booting")) return false;
    var shell = document.querySelector(".shell");
    if (!shell || shell.classList.contains("auth-shell")) return false; // not logged in / on auth screen
    var nav = document.querySelector(".nav-primary");
    return !!(nav && nav.offsetParent !== null);
  }

  function waitForReady(cb) {
    if (appReady()) { cb(); return; }
    var done = false;
    var obs = new MutationObserver(function () {
      if (done) return;
      if (appReady()) { done = true; obs.disconnect(); cb(); }
    });
    obs.observe(document.body, { attributes: true, childList: true, subtree: true });
    setTimeout(function () { if (!done) { done = true; obs.disconnect(); } }, 20000);
  }

  function boot() {
    waitForReady(function () {
      addLauncher();
      var done = false;
      try { done = localStorage.getItem(DONE_KEY) === "1"; } catch (e) {}
      if (!done) setTimeout(function () { if (appReady()) start(false); }, 650);
    });
  }

  window.IELTSOnboarding = {
    start: function () { start(true); },
    finish: finish,
    reset: function () { try { localStorage.removeItem(DONE_KEY); } catch (e) {} },
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
