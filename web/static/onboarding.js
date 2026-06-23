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
      '<svg class="ob-illo" viewBox="0 0 380 244" role="img" aria-label="选中文字后点译，加入 Takeaway">' +
      '  <rect x="14" y="16" width="352" height="78" rx="14" fill="var(--ob-surface)" stroke="var(--ob-line)"/>' +
      '  <text x="34" y="46" class="ob-illo-text">it is going well, but I have to</text>' +
      '  <g class="ob-illo-sel">' +
      '    <rect x="30" y="56" width="214" height="26" rx="6" fill="var(--ob-clay-soft)"/>' +
      '    <text x="40" y="75" class="ob-illo-text ob-illo-strong">manage it quite carefully</text>' +
      '  </g>' +
      '  <g class="ob-illo-pop">' +
      '    <circle cx="276" cy="70" r="19" fill="var(--ob-clay)"/>' +
      '    <text x="276" y="77" text-anchor="middle" class="ob-illo-badge" style="font-size:17px">译</text>' +
      '  </g>' +
      '  <path class="ob-illo-arrow" d="M150 100 C 150 128, 120 128, 120 150" fill="none" stroke="var(--ob-clay)" stroke-width="2.4" stroke-dasharray="3 5"/>' +
      '  <rect x="40" y="150" width="300" height="76" rx="14" fill="var(--ob-surface)" stroke="var(--ob-clay)" stroke-width="1.5"/>' +
      '  <text x="60" y="182" class="ob-illo-text ob-illo-strong" style="font-size:15px">manage it quite carefully</text>' +
      '  <text x="60" y="205" class="ob-illo-sub" style="font-size:12.5px">非常小心地管理 · 已自动翻译</text>' +
      '  <g transform="translate(256,184)"><rect width="66" height="28" rx="14" fill="var(--ob-clay)"/>' +
      '    <text x="33" y="19" text-anchor="middle" class="ob-illo-cta" style="font-size:13px">加入</text></g>' +
      '</svg>'
    );
  }

  function illoReviewKeys() {
    return (
      '<svg class="ob-illo" viewBox="0 0 380 220" role="img" aria-label="复习卡片用 A 掌握 D 再练">' +
      '  <rect x="34" y="14" width="312" height="92" rx="14" fill="var(--ob-surface)" stroke="var(--ob-line)"/>' +
      '  <text x="190" y="54" text-anchor="middle" class="ob-illo-text ob-illo-strong" style="font-size:15px">come up at the same time</text>' +
      '  <text x="190" y="82" text-anchor="middle" class="ob-illo-sub" style="font-size:13px">同时出现</text>' +
      '  <g transform="translate(54,134)">' +
      '    <rect width="124" height="58" rx="13" fill="var(--ob-mint-soft)" stroke="var(--ob-mint)" stroke-width="1.5"/>' +
      '    <text x="34" y="38" text-anchor="middle" class="ob-illo-key" style="font-size:24px" fill="var(--ob-mint)">A</text>' +
      '    <text x="84" y="35" text-anchor="middle" class="ob-illo-sub" style="font-size:13px">已掌握</text>' +
      '  </g>' +
      '  <g transform="translate(202,134)">' +
      '    <rect width="124" height="58" rx="13" fill="var(--ob-clay-soft)" stroke="var(--ob-clay)" stroke-width="1.5"/>' +
      '    <text x="34" y="38" text-anchor="middle" class="ob-illo-key" style="font-size:24px" fill="var(--ob-clay)">D</text>' +
      '    <text x="86" y="35" text-anchor="middle" class="ob-illo-sub" style="font-size:13px">明天再练</text>' +
      '  </g>' +
      '</svg>'
    );
  }

  // A sample of the spelling-drill screen — new users have no words yet, so we
  // mock the interface and point at it rather than spotlighting an empty panel.
  function illoSpellingSample() {
    return (
      '<svg class="ob-illo" viewBox="0 0 380 246" role="img" aria-label="拼写训练界面示例">' +
      '  <rect x="14" y="14" width="352" height="218" rx="16" fill="var(--ob-surface)" stroke="var(--ob-line)"/>' +
      '  <text x="36" y="48" class="ob-illo-sub" style="font-size:12px">中文提示</text>' +
      '  <text x="36" y="74" class="ob-illo-text ob-illo-strong" style="font-size:18px">住宿</text>' +
      '  <text x="232" y="48" text-anchor="end" class="ob-illo-sub" style="font-size:12px">你的误拼</text>' +
      '  <text x="232" y="73" text-anchor="end" class="ob-illo-text" style="font-size:14px;text-decoration:line-through;fill:var(--ob-muted)">acommodation</text>' +
      '  <rect x="36" y="104" width="308" height="50" rx="12" fill="var(--ob-surface-2)" stroke="var(--ob-clay)" stroke-width="1.5"/>' +
      '  <text x="166" y="135" text-anchor="middle" class="ob-illo-text ob-illo-strong" style="font-size:17px">accommodation</text>' +
      '  <rect x="246" y="119" width="2" height="22" fill="var(--ob-clay)"><animate attributeName="opacity" values="1;0;1" dur="1.1s" repeatCount="indefinite"/></rect>' +
      '  <text x="330" y="136" text-anchor="end" class="ob-illo-check" style="font-size:20px">✓</text>' +
      '  <g transform="translate(130,166)"><rect width="120" height="40" rx="10" fill="var(--ob-surface)" stroke="var(--ob-ink-soft)"/>' +
      '    <text x="60" y="27" text-anchor="middle" class="ob-illo-key" style="font-size:15px" fill="var(--ob-ink)">Enter ⏎</text></g>' +
      '  <text x="190" y="227" text-anchor="middle" class="ob-illo-sub" style="font-size:13px">拼对后按 Enter 继续下一个</text>' +
      '</svg>'
    );
  }

  // Sample of the P1-corpus editor: 题卡标题 + 我的语料 + 7分回答参考.
  // New users have no AI answers yet, so the "7 分参考" can't be shown live.
  function illoP1Editor() {
    return (
      '<svg class="ob-illo" viewBox="0 0 460 304" role="img" aria-label="P1 语料库编辑界面示例">' +
      '  <rect x="8" y="8" width="444" height="288" rx="18" fill="var(--ob-surface)" stroke="var(--ob-line)"/>' +
      '  <text x="28" y="48" class="ob-illo-text ob-illo-strong" style="font-size:16px">Could you live without the Internet?</text>' +
      '  <g transform="translate(354,24)"><rect width="86" height="32" rx="16" fill="var(--ob-blue)"/>' +
      '    <text x="43" y="21" text-anchor="middle" class="ob-illo-cta" style="font-size:13px">保存语料</text></g>' +
      '  <text x="28" y="84" class="ob-illo-sub" style="font-size:13px">我的语料</text>' +
      '  <rect x="28" y="94" width="412" height="70" rx="12" fill="var(--ob-surface-2)" stroke="var(--ob-line)"/>' +
      '  <text x="44" y="122" class="ob-illo-text" style="font-size:14px">Probably not for a whole week, because I rely</text>' +
      '  <text x="44" y="146" class="ob-illo-text" style="font-size:14px">on it for study and work…</text>' +
      '  <rect x="28" y="182" width="412" height="100" rx="12" fill="var(--ob-blue-soft)" stroke="var(--ob-blue-line)"/>' +
      '  <rect x="28" y="182" width="5" height="100" rx="2.5" fill="var(--ob-blue)"/>' +
      '  <text x="46" y="208" style="font-size:13px;font-weight:700;fill:var(--ob-blue);font-family:var(--nr-serif-body,Georgia,serif)">7 分回答参考</text>' +
      '  <text x="46" y="234" class="ob-illo-text" style="font-size:14px">I&#8217;d like to do a <tspan font-weight="700">digital detox</tspan> sometimes,</text>' +
      '  <text x="46" y="257" class="ob-illo-text" style="font-size:14px">especially when I feel <tspan font-weight="700">overwhelmed by</tspan></text>' +
      '  <text x="46" y="277" class="ob-illo-text" style="font-size:14px">coding work.</text>' +
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
  // Each non-centered step names a `navView`: the tour first switches the app
  // INTO that view (clicking the real nav button), then spotlights an element
  // that lives INSIDE that view — so the user is led from the sidebar to the
  // actual screen, not lectured at the sidebar.
  var STEPS = [
    {
      kind: "welcome",
      title: "欢迎来到 IELTS Studio",
      body: "一个把「练 → 批改 → 复盘 → 复习」串成闭环的雅思口语 / 写作训练台。<br>大约 1 分钟，我会带你<b>逐个点开真实界面</b>，并指出几个藏起来的提效神器。",
      illustration: illoWelcome(),
    },
    {
      navView: "home",
      target: ".nav-primary",
      placement: "right",
      title: "先认识左边的导航",
      body: "功能都在这条导航里：上半区是 <b>口语</b> 与 <b>写作</b> 练习，下半区是 <b>语料库与复习</b>。下面每一步我都会<b>先点亮左边的入口</b>，再带你走进右边对应的界面。",
    },
    {
      navView: "p1",
      navTarget: '.nav .nav-button[data-view="p1"]',
      target: "#recordControl",
      placement: "left",
      title: "口语练习 · 开口录音",
      body: "左边点 <b>P1 / P2 / P3</b>（或 <b>Mock</b> 完整模考）进入练习。系统自动「<b>话题成组、练得少的优先</b>」出题、考官<b>语音播题</b>；你点右边这个按钮<b>录音作答</b>，全程不用打字。",
    },
    {
      navView: "history",
      navTarget: '.nav .nav-button[data-view="history"]',
      target: ".history-rail-head",
      placement: "bottom",
      title: "口语报告 · 四维评分 + 7 分参考",
      body: "左边点 <b>口语报告</b> 进来。每次练完都生成 <b>流利度 / 词汇 / 语法 / 发音</b> 四维评分 + 中文讲解，并附 <b>7 分参考答案</b>；报告收在这条卡片轨里，可按 P1/P2/P3 筛选回看。",
    },
    {
      kind: "illustration",
      illustration: illoSelectToTakeaway(),
      title: "划词即收藏 ✦ 隐藏神器",
      body: "在报告或参考答案里，用鼠标 <b>选中任意好句</b> → 点弹出的 <b>「译」</b> → 系统<b>自动翻译</b> → 一键 <b>加入 Takeaway / 写作积累</b>。好表达不用再手抄。",
    },
    {
      navView: "takeawayBook",
      navTarget: '.nav .nav-button[data-view="takeawayBook"]',
      target: "#languageTakeawayReviewPanel .takeaway-review-start",
      placement: "bottom",
      title: "Takeaway · 按记忆曲线复习",
      body: "左边点 <b>Takeaway</b> 进来，划词收藏的表达都汇在这里。点右上角的 <b>「开始」</b> 听英文发音，用键盘 <b>A = 已掌握</b> / <b>D = 明天再练</b>。导航上的小红点 = <b>有到期复习</b>。",
      illustration: illoReviewKeys(),
    },
    {
      navView: "spellingDrill",
      navTarget: '.nav .nav-button[data-view="spellingDrill"]',
      // New users have no words yet, so we show a sample of the screen instead
      // of spotlighting an empty panel.
      title: "拼写错词训练",
      body: "左边点 <b>拼写错词训练</b> 进来。写作里拼错的词会<b>自动收进来</b>，按记忆曲线安排。界面长这样 ↓：看<b>中文 + 你的误拼</b>回忆正确写法，拼对一个直接按 <b>Enter</b> 继续下一个，不用找按钮。",
      illustration: illoSpellingSample(),
    },
    {
      navView: "writing",
      navTarget: '.nav .nav-button[data-view="writing"]',
      targets: ["#writingTopbarActions", ".writing-prompt-card", ".writing-answer-header"],
      placement: "right",
      title: "每日写作 · AI 分段批改",
      body: "左边点 <b>每日写作</b> 进来。顶部是<b>题目控制区</b>（<b>Task 1 / Task 2</b> 分大类题库、点题目换题、或点 <b>「随机换题」</b>）；下面是<b>题目正文</b>，再下面写答案、写完 <b>AI 分段批改</b>。不会下笔时用 <code>/frame</code>、<code>/myframe</code> 一键生成<b>作文框架</b>。",
    },
    {
      navView: "corpus",
      navTarget: '.nav .nav-button[data-view="corpus"]',
      target: ".corpus-top-cards",
      placement: "bottom",
      title: "语料库 · 沉淀你自己的素材",
      body: "左边点 <b>语料库</b> 进来。分两块：<b>P1 语料库</b> 按话题整理短答；<b>P2 串题 + P3 追问</b> 维护题卡正文。结合 AI 自己整理，比直接让 AI 代写更扎实、更像你的话。下面分别带你看。",
    },
    {
      navClicks: ['.nav .nav-button[data-view="corpus"]', '[data-corpus-home-target="p1Corpus"]'],
      target: ".p1-topic-card",
      placement: "right",
      title: "P1 语料库 · 按话题攒短答",
      body: "题库按话题分成一张张卡片，每张卡里是这个话题的所有问题。<b>点任意问题</b>就能打开编辑器写「我的语料」。下一步带你看编辑界面长什么样。",
    },
    {
      kind: "illustration",
      illustration: illoP1Editor(),
      title: "P1 编辑器 · 我的语料 + 7 分参考",
      body: "点开一道题就是这个编辑界面：上半区写 <b>「我的语料」</b>，AI 自动配一份 <b>「7 分回答参考」</b>（蓝色那块）可对照改写、一键复制。练习或报告里点 <b>「编辑语料库」</b> 也能把好句一键存进对应题目——新用户暂时没有报告，先认识这个入口。",
    },
    {
      navClicks: ['.nav .nav-button[data-view="corpus"]', '[data-corpus-home-target="p2Corpus"]'],
      target: ".p2-category-entry-grid",
      placement: "bottom",
      title: "P2 语料库 · ① 上方分类",
      body: "P2 靠「<b>大素材串多题</b>」省力。最上面这排是<b>分类入口</b>（<b>人物 / 地点 / 事件 / 物品…</b>），先把<b>能共用同一个大素材</b>的题目归到一起，后面写素材就能一稿多用。",
    },
    {
      navClicks: ['.nav .nav-button[data-view="corpus"]', '[data-corpus-home-target="p2Corpus"]'],
      target: ".p2-brainstorm-entry-card",
      placement: "right",
      title: "P2 语料库 · ② 串题灵感 Brainstorm",
      body: "这张 <b>「串题灵感 Brainstorm」</b> 卡用来按题干<b>快记一句灵感</b>：关键词、人物关系、地点、经历碎片先随手放进来，之后再慢慢整理成正式素材，避免一上来就憋大段正文。",
    },
    {
      navClicks: ['.nav .nav-button[data-view="corpus"]', '[data-corpus-home-target="p2Corpus"]'],
      target: ".p2-seasonal-card",
      placement: "right",
      title: "P2 语料库 · ③ 当季 P2 题卡",
      body: "下面是<b>当季每一张 P2 题卡</b>。点卡片上的 <b>「正文」</b> 写这道题的大素材，点 <b>「P3 追问」</b> 补好可复用的 Part 3 追问答案。练习时直接调出来按 cue 微调即可。",
    },
    {
      kind: "illustration",
      title: "P2 正确打开方式 · 5 步攒素材",
      body: "别一题一题硬背。推荐这样用本站把这季 P2 串成几个大素材：" +
        '<ol class="ob-flow">' +
        "<li><b>过一遍本季题库</b>：在 P2 语料库里看清这季有哪些卡片题。</li>" +
        "<li><b>Brainstorm 快记灵感</b>：给每题写一句关键词 / 人物 / 地点 / 经历碎片。</li>" +
        "<li><b>归类</b>：把能套同一个大素材的题目放进同一<b>分类</b>（人物 / 地点 / 事件 / 物品…）。</li>" +
        "<li><b>写大素材</b>：在每张题卡的<b>正文</b>里把这类的核心内容写扎实，并补好 <b>P3 追问</b>。</li>" +
        "<li><b>按题微调</b>：练习时调出对应正文，照着具体 cue 加减改一改就能用。</li>" +
        "</ol>",
    },
    {
      kind: "illustration",
      illustration: illoWelcome(),
      title: "就这些，去练吧 ✦",
      body: "右上角 <b>头像</b> 里有外观、账户与余额设置。随时点左下角的 <b>「教程」</b> 重看这份导览。祝你早日上岸 🎯",
      finish: true,
    },
  ];

  // ---------------------------------------------------------------- styles
  var CSS =
    '.ob-root{position:fixed;inset:0;z-index:' + Z + ';font-family:var(--nr-serif-body,"Newsreader",Georgia,serif);' +
    '--ob-surface:var(--panel,#fff);--ob-surface-2:#faf7f2;--ob-ink:var(--ink,#1c160f);--ob-ink-soft:#6f6557;' +
    '--ob-muted:var(--muted,#857a6a);--ob-line:var(--border-soft,rgba(28,20,15,.12));' +
    '--ob-clay:#c0664a;--ob-clay-dark:#a8543c;--ob-clay-soft:#f6e7df;' +
    '--ob-mint:#0f9f7a;--ob-mint-soft:#e1f6ee;--ob-dim:rgba(28,18,10,.60);' +
    '--ob-blue:#2f6bd8;--ob-blue-soft:#eef4ff;--ob-blue-line:#bcd2f7;--ob-green:#2f6f57;}' +
    // Dark-mode: flip the hardcoded LIGHT helper colors so illustration boxes
    // (light fills) don't collide with the now-light ink text.
    'body.theme-dark .ob-root{--ob-surface-2:#2b3140;--ob-ink:#f2ece1;--ob-ink-soft:#cabfae;' +
    '--ob-muted:#9b9384;--ob-line:rgba(255,255,255,.16);--ob-clay-soft:rgba(192,102,74,.34);' +
    '--ob-mint-soft:rgba(15,159,122,.30);--ob-blue:#9cc0ff;--ob-blue-soft:rgba(90,135,235,.22);' +
    '--ob-blue-line:rgba(120,160,235,.45);--ob-green:#5fb591;--ob-dim:rgba(0,0,0,.66);}' +
    '.ob-root *{box-sizing:border-box;}' +
    // spotlight
    '.ob-spot{position:absolute;border-radius:14px;box-shadow:0 0 0 9999px var(--ob-dim),0 0 0 2px var(--ob-clay),0 12px 40px rgba(0,0,0,.28);' +
    'transition:all 360ms cubic-bezier(.4,.02,.2,1);pointer-events:none;}' +
    '.ob-spot::after{content:"";position:absolute;inset:-6px;border-radius:18px;border:2px solid var(--ob-clay);opacity:.5;animation:ob-pulse 1.8s ease-out infinite;}' +
    '@keyframes ob-pulse{0%{transform:scale(.98);opacity:.55;}70%{transform:scale(1.06);opacity:0;}100%{opacity:0;}}' +
    // full-screen dim for centered cards (no spotlight)
    '.ob-backdrop{position:absolute;inset:0;background:var(--ob-dim);backdrop-filter:blur(2px);}' +
    // card
    '.ob-card{position:absolute;width:432px;max-width:calc(100vw - 28px);max-height:calc(100vh - 28px);overflow-y:auto;' +
    'background:var(--ob-surface);color:var(--ob-ink);' +
    'border:1px solid var(--ob-line);border-radius:20px;padding:26px 30px 22px;box-shadow:0 26px 64px rgba(28,18,10,.34);' +
    'animation:ob-rise 320ms cubic-bezier(.2,.7,.2,1) both;}' +
    '.ob-card.ob-center{position:relative;width:588px;padding:32px 38px 26px;}' +
    '.ob-center-wrap{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:20px;}' +
    '@keyframes ob-rise{from{opacity:0;transform:translateY(10px) scale(.985);}to{opacity:1;transform:none;}}' +
    '.ob-eyebrow{display:flex;align-items:center;gap:10px;font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;' +
    'color:var(--ob-clay-dark);font-weight:700;margin-bottom:13px;font-family:var(--nr-serif-body,Georgia,serif);}' +
    '.ob-dots{display:flex;gap:5px;margin-left:auto;}' +
    '.ob-dot{width:6px;height:6px;border-radius:50%;background:var(--ob-line);transition:all .25s;}' +
    '.ob-dot.on{background:var(--ob-clay);width:18px;border-radius:3px;}' +
    '.ob-title{font-family:var(--nr-serif-display,"Fraunces",Georgia,serif);font-size:23px;line-height:1.26;font-weight:600;margin:0 0 10px;letter-spacing:.01em;}' +
    '.ob-body{font-size:15.5px;line-height:1.72;color:var(--ob-ink-soft);margin:0;}' +
    '.ob-body b{color:var(--ob-ink);font-weight:700;}' +
    '.ob-body code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.9em;background:var(--ob-surface-2);' +
    'border:1px solid var(--ob-line);border-radius:6px;padding:1px 6px;color:var(--ob-clay-dark);}' +
    '.ob-flow{list-style:none;counter-reset:ob-flow;margin:14px 0 0;padding:0;}' +
    '.ob-flow li{counter-increment:ob-flow;position:relative;padding:0 0 0 38px;margin:0 0 12px;font-size:14.5px;line-height:1.55;color:var(--ob-ink-soft);}' +
    '.ob-flow li:last-child{margin-bottom:0;}' +
    '.ob-flow li::before{content:counter(ob-flow);position:absolute;left:0;top:1px;width:25px;height:25px;border-radius:50%;' +
    'background:var(--ob-clay);color:#fff;font-size:13px;font-weight:700;display:flex;align-items:center;justify-content:center;' +
    'font-family:var(--nr-serif-body,Georgia,serif);}' +
    '.ob-flow b{color:var(--ob-ink);font-weight:700;}' +
    '.ob-illo-frame{margin:18px 0 6px;padding:18px 20px;background:var(--ob-surface-2);border:1px solid var(--ob-line);border-radius:16px;}' +
    '.ob-illo{display:block;width:100%;height:auto;}' +
    '.ob-illo-welcome{max-width:300px;margin:0 auto;}' +
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
    '.ob-foot{display:flex;align-items:center;margin-top:22px;gap:10px;}' +
    '.ob-skip{background:none;border:none;color:var(--ob-muted);font-size:13px;cursor:pointer;padding:6px 2px;font-family:inherit;}' +
    '.ob-skip:hover{color:var(--ob-ink);}' +
    '.ob-spacer{flex:1;}' +
    '.ob-btn{font-family:inherit;font-size:14.5px;font-weight:600;border-radius:999px;cursor:pointer;border:1px solid transparent;padding:10px 22px;transition:all .15s;}' +
    '.ob-btn-ghost{background:none;border-color:var(--ob-line);color:var(--ob-ink-soft);}' +
    '.ob-btn-ghost:hover{border-color:var(--ob-ink-soft);color:var(--ob-ink);}' +
    '.ob-btn-primary{background:var(--ob-clay);color:#fff;box-shadow:0 6px 16px rgba(192,102,74,.35);}' +
    '.ob-btn-primary:hover{background:var(--ob-clay-dark);transform:translateY(-1px);}' +
    // launcher — sits inline in the top bar, just left of the avatar
    '.ob-launch{display:inline-flex;align-items:center;gap:6px;margin-right:6px;' +
    'background:var(--panel,#fff);color:#a8543c;border:1px solid rgba(192,102,74,.4);border-radius:999px;padding:6px 12px;' +
    'font-family:var(--nr-serif-body,Georgia,serif);font-size:13px;font-weight:600;cursor:pointer;' +
    'transition:all .16s;white-space:nowrap;}' +
    '.ob-launch:hover{border-color:#c0664a;background:color-mix(in srgb,#c0664a 8%,var(--panel,#fff));}' +
    'body.theme-dark .ob-launch{background:transparent;color:#e3a48f;border-color:rgba(192,102,74,.5);}' +
    '.ob-launch .ob-q{display:inline-flex;align-items:center;justify-content:center;width:17px;height:17px;border-radius:50%;background:#c0664a;color:#fff;font-size:11px;}' +
    // nav-button lifted above the dim + clay ring (the "from the sidebar" cue)
    '.ob-navlift{border-radius:12px!important;animation:ob-navpulse 1.8s ease-out infinite;}' +
    '@keyframes ob-navpulse{0%,100%{box-shadow:0 0 0 2px var(--ob-clay),0 0 0 5px var(--ob-clay-soft),0 14px 34px rgba(28,18,10,.42);}' +
    '50%{box-shadow:0 0 0 2px var(--ob-clay),0 0 0 9px color-mix(in srgb,var(--ob-clay) 20%,transparent),0 14px 34px rgba(28,18,10,.42);}}' +
    '@media (prefers-reduced-motion: reduce){.ob-root *{animation:none!important;transition:none!important;}' +
    '.ob-navlift{animation:none!important;box-shadow:0 0 0 2px var(--ob-clay),0 0 0 6px var(--ob-clay-soft),0 14px 34px rgba(28,18,10,.42)!important;}}';

  // ---------------------------------------------------------------- engine
  var root = null;
  var idx = 0;
  var curSelectors = []; // selector(s) currently spotlit; re-queried each reposition
  var curStep = null;
  var renderSeq = 0; // guards async target resolution against fast step changes

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
    clearNavLift();
    if (root) root.innerHTML = "";
  }

  // "Lift" the matching left-sidebar nav button above the dim and ring it, so
  // each step visibly starts from the navigation entry, then leads to the view.
  var navLift = null;
  function liftNav(sel) {
    clearNavLift();
    if (!sel) return;
    var btn = document.querySelector(sel);
    if (!isVisible(btn)) return;
    navLift = { el: btn, position: btn.style.position, zIndex: btn.style.zIndex };
    if (window.getComputedStyle(btn).position === "static") btn.style.position = "relative";
    btn.style.zIndex = String(Z + 2);
    btn.classList.add("ob-navlift");
  }
  function clearNavLift() {
    if (!navLift) return;
    navLift.el.classList.remove("ob-navlift");
    navLift.el.style.position = navLift.position;
    navLift.el.style.zIndex = navLift.zIndex;
    navLift = null;
  }

  function currentView() {
    var a = document.querySelector(".nav .nav-button.active") ||
            document.querySelector(".nav-primary .nav-button.active");
    return a ? a.dataset.view : null;
  }

  // Switch the app into `view` by clicking its real nav button. Returns true if
  // a navigation was actually triggered (so we know to wait a beat for render).
  function ensureView(view) {
    if (!view || currentView() === view) return false;
    var btn = document.querySelector('.nav .nav-button[data-view="' + view + '"]');
    if (!btn) return false;
    btn.click();
    return true;
  }

  // NB: don't use offsetParent — it is null for elements inside position:fixed
  // / sticky bars (e.g. the global top bar that holds the writing controls),
  // which would wrongly mark them invisible. Client rects are the reliable test.
  function isVisible(elx) {
    if (!elx || !elx.getClientRects().length) return false;
    var b = elx.getBoundingClientRect();
    return b.width > 0 && b.height > 0;
  }

  // Click a sequence of selectors (each polled until present) — used to reach
  // corpus sub-views (语料库 → P1/P2 语料库) which aren't direct nav buttons.
  function runClicks(list, done) {
    if (!list.length) { done(); return; }
    var sel = list.shift();
    var start = Date.now();
    (function poll() {
      var elx = document.querySelector(sel);
      if (isVisible(elx)) { elx.click(); setTimeout(function () { runClicks(list, done); }, 40); return; }
      if (Date.now() - start > 1500) { runClicks(list, done); return; }
      setTimeout(poll, 30);
    })();
  }

  // A step may spotlight one element (`target`) or a union of several
  // (`targets`, e.g. the writing header + the prompt/answer card together).
  function stepSelectors(step) {
    if (step.targets && step.targets.length) return step.targets;
    if (step.target) return [step.target];
    return [];
  }

  // Get the step's view on screen, then continue. Skips work if the (first)
  // target is already visible (e.g. stepping back to a view we're still on).
  function navigateForStep(step, done) {
    var first = stepSelectors(step)[0];
    if (first && isVisible(document.querySelector(first))) { done(); return; }
    if (step.navClicks && step.navClicks.length) { runClicks(step.navClicks.slice(), done); return; }
    ensureView(step.navView);
    done();
  }

  // Poll for the step's in-view target(s) after navigation (panels un-hide
  // synchronously, but give async view loads a short window just in case).
  // Resolves to the array of visible elements (empty → centered fallback).
  function resolveTarget(step, cb) {
    var sels = stepSelectors(step);
    if (!sels.length) { cb([]); return; }
    var start = Date.now();
    (function poll() {
      var found = sels.map(function (s) { return document.querySelector(s); });
      var visible = found.filter(isVisible);
      if (visible.length === sels.length || (visible.length && Date.now() - start > 1500)) { cb(visible); return; }
      if (Date.now() - start > 1500) { cb(visible); return; }
      setTimeout(poll, 30);
    })();
  }

  function centeredCard(step) {
    var back = el("div", "ob-backdrop");
    var wrap = el("div", "ob-center-wrap");
    var card = buildCard(step);
    card.classList.add("ob-center");
    wrap.appendChild(card);
    root.appendChild(back);
    root.appendChild(wrap);
    curSelectors = [];
    curStep = step;
  }

  function render() {
    var step = STEPS[idx];
    var seq = ++renderSeq;
    curSelectors = [];
    clear();

    if (step.kind === "welcome" || step.kind === "illustration") {
      if (step.navTarget) liftNav(step.navTarget);
      centeredCard(step);
      return;
    }

    // Lead the user from the sidebar INTO the matching view: switch the app,
    // light up the left nav entry, then spotlight an element inside the screen.
    root.appendChild(el("div", "ob-backdrop")); // hold a dim while we wait
    navigateForStep(step, function () {
      if (seq !== renderSeq) return;
      resolveTarget(step, function (target) {
        if (seq !== renderSeq) return; // a newer step superseded this one
        clear();
        if (step.navTarget) liftNav(step.navTarget);
        if (!target.length) { centeredCard(step); return; } // empty view → sample card
        curSelectors = stepSelectors(step);
        curStep = step;
        try {
          target[0].scrollIntoView({ block: "center", inline: "nearest" });
        } catch (e) { /* older browsers */ }
        root.appendChild(el("div", "ob-spot"));
        root.appendChild(buildCard(step));
        reposition();
        // The view may finish laying out / re-render (e.g. writing surface loads
        // its prompt async) AFTER we positioned. Re-measure a few times so the
        // frame tracks the final layout instead of a stale one.
        [120, 380, 800, 1500].forEach(function (ms) {
          setTimeout(function () { if (seq === renderSeq) reposition(); }, ms);
        });
      });
    });
  }

  function reposition() {
    if (!curSelectors.length) return;
    var spot = root && root.querySelector(".ob-spot");
    var card = root && root.querySelector(".ob-card");
    if (!spot || !card) return;
    // Re-query live each time so re-rendered views don't leave us on stale nodes.
    var els = curSelectors.map(function (s) { return document.querySelector(s); }).filter(isVisible);
    if (!els.length) return;
    var r = unionRect(els);
    positionSpotlight(spot, r);
    positionCard(card, r, (curStep && curStep.placement) || "right");
  }

  // Bounding box that encloses every spotlit element (in viewport coords).
  function unionRect(els) {
    var L = Infinity, T = Infinity, R = -Infinity, B = -Infinity;
    els.forEach(function (e) {
      var b = e.getBoundingClientRect();
      L = Math.min(L, b.left); T = Math.min(T, b.top);
      R = Math.max(R, b.right); B = Math.max(B, b.bottom);
    });
    return { left: L, top: T, right: R, bottom: B, width: R - L, height: B - T };
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
      var frame = el("div", "ob-illo-frame");
      var box = el("div", null, step.illustration);
      frame.appendChild(box.firstChild);
      card.appendChild(frame);
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
    return card;
  }

  function positionSpotlight(spot, r) {
    var pad = 8;
    spot.style.left = r.left - pad + "px";
    spot.style.top = r.top - pad + "px";
    spot.style.width = r.width + pad * 2 + "px";
    spot.style.height = r.height + pad * 2 + "px";
  }

  function positionCard(card, r, placement) {
    var cw = card.offsetWidth || 432;
    var ch = card.offsetHeight || 240;
    var gap = 18, m = 12, pad = 8;
    var vw = window.innerWidth, vh = window.innerHeight;

    function at(p) {
      if (p === "right") return { left: r.right + gap, top: r.top + r.height / 2 - ch / 2 };
      if (p === "left") return { left: r.left - gap - cw, top: r.top + r.height / 2 - ch / 2 };
      if (p === "top") return { left: r.left + r.width / 2 - cw / 2, top: r.top - gap - ch };
      return { left: r.left + r.width / 2 - cw / 2, top: r.bottom + gap }; // bottom
    }
    function overlaps(pos) {
      return !(pos.left >= r.right + pad - 0.5 || pos.left + cw <= r.left - pad + 0.5 ||
               pos.top >= r.bottom + pad - 0.5 || pos.top + ch <= r.top - pad + 0.5);
    }
    function fits(pos) {
      return pos.left >= m && pos.top >= m && pos.left + cw <= vw - m && pos.top + ch <= vh - m;
    }

    // Try the preferred placement, then the others; pick the first that both
    // fits on screen AND doesn't cover the spotlit target.
    var order = [placement || "right", "right", "bottom", "left", "top"];
    var chosen = null, fallback = null;
    for (var i = 0; i < order.length; i++) {
      var pos = at(order[i]);
      if (!fallback) fallback = pos;
      if (fits(pos) && !overlaps(pos)) { chosen = pos; break; }
    }
    var best = chosen || fallback;
    card.style.left = Math.max(m, Math.min(best.left, vw - cw - m)) + "px";
    card.style.top = Math.max(m, Math.min(best.top, vh - ch - m)) + "px";
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

  var reflow = function () { if (root) reposition(); };

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
    curSelectors = [];
    curStep = null;
    document.body.style.overflow = "";
    // Leave the user on a clean home screen rather than wherever the tour ended.
    try { ensureView("home"); } catch (e) {}
    try { localStorage.setItem(DONE_KEY, "1"); } catch (e) {}
  }

  // ---------------------------------------------------------------- launcher + auto
  function addLauncher() {
    if (document.querySelector(".ob-launch")) return;
    injectStyle();
    var b = el("button", "ob-launch", '<span class="ob-q">?</span><span>教程</span>');
    b.setAttribute("type", "button");
    b.setAttribute("aria-label", "重新观看新手教程");
    b.addEventListener("click", function () { start(true); });
    // Place it inline in the top bar, immediately left of the avatar button.
    var avatar = document.querySelector(".global-topbar-actions .avatar-settings-button");
    if (avatar && avatar.parentNode) {
      avatar.parentNode.insertBefore(b, avatar);
    } else {
      document.body.appendChild(b); // fallback if the topbar isn't found
    }
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
      // Only mount the floating "教程" launcher. The tour no longer auto-opens
      // on first visit — guests (and anyone demoing the app) can browse freely,
      // and start the walkthrough on demand via the launcher or
      // window.IELTSOnboarding.start().
      addLauncher();
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
