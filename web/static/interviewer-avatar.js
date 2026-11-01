(function () {
  // 面试练习页左栏的像素面试官：念题时说话，回答时看向右下（转写区）在听，等 AI 时眼睛往上在想；
  // 每题答完按面试官的判断反应一下（strong 点头 + 笑，adequate 淡淡一笑，weak 皱眉流汗）。
  // 只是表情，不影响流程。动作由 app.js 喂进来：setStatus(录音按钮的状态)、react(判断)、sync()（跟随页面显示/隐藏）。
  // 80×80 的像素格（由形状栅格化生成）：BASE 是不变的部分（"." 透明），OVER 是可切换的眼睛 / 嘴 / 眉毛 / 汗珠 / 思考点。
  // 头部 = 第 0-45 行，点头时只有它动。
  const BASE = [
    "................................................................................",
    "................................................................................",
    "................................................................................",
    "................................................................................",
    "................................................................................",
    "................................................................................",
    "................................................................................",
    "................................................................................",
    ".................................kkkhhhhhkkkkkk.................................",
    "..............................kkkHhhHhhhHhhHHHHkkk..............................",
    ".............................kHHkHHhhHHHHHHHHhhHHHk.............................",
    "...........................khhHHkHHHHHHHHHHHHHHhhHHkk...........................",
    "..........................khHHHHHkHHHHHHHHHHHHHHHhHHHk..........................",
    "..........................hHHHHHHkHHHHHHHHHHHHHHHHhHHk..........................",
    ".........................kHHHHHHHkHHHHHHHHHHHHHHHHHHHHk.........................",
    ".........................hHHHHHHHHHHHHHHHHHHHHHHHHHHHHk.........................",
    "........................kHHHHHHHHHHHHHHHHHHHHHHHkkHHHHHk........................",
    "........................kHHHHHHHHHHHHHHHHkkkkHkksskHHHHk........................",
    "........................kHHHHHHHkkkHkkkkksssskssSSskHHHk........................",
    "........................kHHHHkHksssksssssSSSSsSSSSSkHHHk........................",
    "........................kHHkksksSSSsSSSSSSSSSSSSSSSkkHHk........................",
    ".......................kHHkssSsSSSSSSSSSSSSSSSSSSSSsskHHk.......................",
    ".......................kHHkSSBBBBBBBSSSSSSSSBBBBBBBSSkHHk.......................",
    ".......................kHHkSBBBBBBBBBSSSSSSBBBBBBBBBSkHHk.......................",
    ".......................kHHkSSSSSSSSSSSSSSSSSSSSSSSSSSkHHk.......................",
    ".......................kHHkSGGGGGGGGGSSSSSSSGGGGGGGGGkHHk.......................",
    ".......................kkkkGLllLLLLLLGSSSSSGLllLLLLLLGkkk.......................",
    ".......................SSGGGLlLLLLLLLGGGGGGGLlLLLLLLLGGSS.......................",
    ".......................SSSHGLLLLLLLLLGSSSSSGLLLLLLLLLGSSS.......................",
    ".......................SSsSGLLLLLLLLLGSSSSSGLLLLLLLLLGsSS.......................",
    ".......................SSsSGLLLLLLLLLGSSSSSGLLLLLLLLLGsSS.......................",
    ".......................SSsSGLLLLLLLLLGSSSSSGLLLLLLLLLGsSS.......................",
    ".......................SSSSGLLLLLLLLLGSSSSSGLLLLLLLLLGSSS.......................",
    "........................SSSSGGGGGGGGGSSSSnSSGGGGGGGGGSSS........................",
    "..........................SSSSSSSSSSSSSSSnSSSSSSSSSSSS..........................",
    "...........................sSSSSSSSSSSSSSnSSSSSSSSSSs...........................",
    "...........................sSSSSSSSSSSnSSSnSSSSSSSSSs...........................",
    "............................sSSSSSSSSSSnnnSSSSSSSSSs............................",
    "............................sSSSSSSSSSSSSSSSSSSSSSSs............................",
    ".............................sSSSSSSSSSSSSSSSSSSSSs.............................",
    "..............................sSSSSSSSSSSSSSSSSSSs..............................",
    "...............................sSSSSSSSSSSSSSSSSs...............................",
    "................................sSSSSSSSSSSSSSSs................................",
    "................................sSSSSSSSSSSSSSSs................................",
    ".................................ssssssssssssss.................................",
    "...................................ssssssssss...................................",
    "...................................sSSSSSSSSs...................................",
    "...................................sSSSSSSSSs...................................",
    "................................TTTTSSSSSSSSTTTT................................",
    "..............................qqqTTTTSSSSSSTTTTqqq..............................",
    ".........................qqqqqJJJTTTTSSSSSSTTTTJJJqqqqq.........................",
    ".....................qqqqqJJJJJJTTTTTTSSSSTTTTTTJJJJJJqqqqq.....................",
    "..................qqqqqqqJJJJJTTjqTTTTSSSSTTTTqjTTJJJJJqqqqqqq..................",
    "...............qqqqqqJJJJJJJJJjqqqqTTTTssTTTTqqqqjJJJJJJJJJqqqqqq...............",
    ".............qqqqqJJJJJJJJJJjqqqqqqUUUUssUUUUqqqqqqjJJJJJJJJJJqqqqq.............",
    "...........qqqqJJJJJJJJJJJJJjqqqqqqTTTTTTTTTTqqqqqqjJJJJJJJJJJJJJqqqq...........",
    "..........qqqJJJJJJJJJJJJJJJJjqqqqqqTTTTTTTTqqqqqqjJJJJJJJJJJJJJJJJqqq..........",
    "..........qJJJJJJJJJJJJJJJJJJjqqqqqqTTTTTTTTqqqqqqjJJJJJJJJJJJJJJJJJJq..........",
    "..........jJJJJJJJJJJJJJJJJJJJjqqqqqqTTTTTTqqqqqqjJJJJJJJJJJJJJJJJJJJj..........",
    ".........jjJJJJJJJJJJJJJJJJJJJJjqqqqqTTUTTTqqqqqjJJJJJJJJJJJJJJJJJJJJjj.........",
    ".........jjJJJJJJJJJJJJJJJJJJJJjqqqqqqTTTTqqqqqqjJJJJJJJJJJJJJJJJJJJJjj.........",
    ".........jjjJJJJJJJJJJJJJJJJJJJJjqqqqqTTTTqqqqqjJJJJJJJJJJJJJJJJJJJJjjj.........",
    "........jjjjJJJJJJJJJJJJJJJJJJJJJjqqqqTTTTqqqqjJJJJJJJJJJJJJJJJJJJJJjjjj........",
    "........jjjjJJJJJJJJJJJJJJJJJJJJJjqqqqqUTqqqqqjJJJJJJJJJJJJJJJJJJJJJjjjj........",
    "........jjjjjJJJJJJJJJJJJJJJJJJJJJjqqqqTTqqqqjJJJJJJJJJJJJJJJJJJJJJjjjjj........",
    "........jjjjjJJJJJJJJJJJJJJJJJJJJJjqqqqqqqqqqjJJJJJJJJJJJJJJJJJJJJJjjjjj........",
    "........jjjjjJJJJJJJJJJJJJJJJJJJJJJjqqqqqqqqjJJJJJJJJJJJJJJJJJJJJJJjjjjj........",
    "........jjjjjjJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJjjjjjj........",
    "........jjjjjjJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJjjjjjj........",
    "........jjjjjjJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJjjjjjj........",
    "........jjjjjjjJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJjjjjjjj........",
    "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD",
    "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  ];
  const HEAD_ROWS = 46;
  const OVER = {
    "eyes-open": [[30, 29, "e"], [31, 29, "e"], [32, 29, "e"], [33, 29, "e"], [34, 29, "e"], [30, 30, "e"], [31, 30, "e"], [32, 30, "e"], [33, 30, "e"], [34, 30, "e"], [30, 28, "E"], [31, 28, "E"], [32, 28, "E"], [33, 28, "E"], [34, 28, "E"], [32, 29, "i"], [33, 29, "i"], [32, 30, "E"], [33, 30, "i"], [46, 29, "e"], [47, 29, "e"], [48, 29, "e"], [49, 29, "e"], [50, 29, "e"], [46, 30, "e"], [47, 30, "e"], [48, 30, "e"], [49, 30, "e"], [50, 30, "e"], [46, 28, "E"], [47, 28, "E"], [48, 28, "E"], [49, 28, "E"], [50, 28, "E"], [48, 29, "i"], [49, 29, "i"], [48, 30, "E"], [49, 30, "i"]],
    "eyes-up": [[30, 29, "e"], [31, 29, "e"], [32, 29, "e"], [33, 29, "e"], [34, 29, "e"], [30, 30, "e"], [31, 30, "e"], [32, 30, "e"], [33, 30, "e"], [34, 30, "e"], [30, 28, "E"], [31, 28, "E"], [32, 28, "E"], [33, 28, "E"], [34, 28, "E"], [32, 28, "i"], [33, 28, "i"], [32, 29, "E"], [33, 29, "i"], [46, 29, "e"], [47, 29, "e"], [48, 29, "e"], [49, 29, "e"], [50, 29, "e"], [46, 30, "e"], [47, 30, "e"], [48, 30, "e"], [49, 30, "e"], [50, 30, "e"], [46, 28, "E"], [47, 28, "E"], [48, 28, "E"], [49, 28, "E"], [50, 28, "E"], [48, 28, "i"], [49, 28, "i"], [48, 29, "E"], [49, 29, "i"]],
    "eyes-downright": [[30, 28, "E"], [31, 28, "E"], [32, 28, "E"], [33, 28, "E"], [34, 28, "E"], [30, 30, "e"], [31, 30, "e"], [32, 30, "e"], [33, 30, "e"], [34, 30, "e"], [30, 29, "E"], [31, 29, "e"], [32, 29, "e"], [33, 29, "i"], [34, 29, "i"], [33, 30, "E"], [34, 30, "i"], [46, 28, "E"], [47, 28, "E"], [48, 28, "E"], [49, 28, "E"], [50, 28, "E"], [46, 30, "e"], [47, 30, "e"], [48, 30, "e"], [49, 30, "e"], [50, 30, "e"], [46, 29, "E"], [47, 29, "e"], [48, 29, "e"], [49, 29, "i"], [50, 29, "i"], [49, 30, "E"], [50, 30, "i"]],
    "eyes-blink": [[30, 29, "s"], [31, 29, "s"], [32, 29, "s"], [33, 29, "s"], [34, 29, "s"], [30, 30, "E"], [31, 30, "E"], [32, 30, "E"], [33, 30, "E"], [34, 30, "E"], [46, 29, "s"], [47, 29, "s"], [48, 29, "s"], [49, 29, "s"], [50, 29, "s"], [46, 30, "E"], [47, 30, "E"], [48, 30, "E"], [49, 30, "E"], [50, 30, "E"]],
    "mouth-closed": [[37, 40, "M"], [38, 40, "M"], [39, 40, "M"], [40, 40, "M"], [41, 40, "M"], [42, 40, "M"], [43, 40, "M"], [36, 39, "n"], [44, 39, "n"]],
    "mouth-mid": [[37, 40, "M"], [38, 40, "M"], [39, 40, "M"], [40, 40, "M"], [41, 40, "M"], [42, 40, "M"], [43, 40, "M"], [38, 41, "m"], [39, 41, "m"], [40, 41, "m"], [41, 41, "m"], [42, 41, "m"]],
    "mouth-open": [[37, 39, "M"], [38, 39, "M"], [39, 39, "M"], [40, 39, "M"], [41, 39, "M"], [42, 39, "M"], [43, 39, "M"], [37, 40, "m"], [38, 40, "m"], [39, 40, "m"], [40, 40, "m"], [41, 40, "m"], [42, 40, "m"], [43, 40, "m"], [37, 41, "m"], [38, 41, "m"], [39, 41, "m"], [40, 41, "m"], [41, 41, "m"], [42, 41, "m"], [43, 41, "m"], [38, 42, "M"], [39, 42, "M"], [40, 42, "M"], [41, 42, "M"], [42, 42, "M"], [38, 40, "W"], [39, 40, "W"], [40, 40, "W"], [41, 40, "W"], [42, 40, "W"]],
    "mouth-smile": [[35, 39, "M"], [45, 39, "M"], [36, 40, "M"], [37, 40, "M"], [38, 40, "M"], [39, 40, "M"], [40, 40, "M"], [41, 40, "M"], [42, 40, "M"], [43, 40, "M"], [44, 40, "M"], [38, 41, "M"], [39, 41, "M"], [40, 41, "M"], [41, 41, "M"], [42, 41, "M"], [29, 36, "b"], [30, 36, "b"], [31, 36, "b"], [49, 36, "b"], [50, 36, "b"], [51, 36, "b"]],
    "mouth-frown": [[37, 40, "M"], [38, 40, "M"], [39, 40, "M"], [40, 40, "M"], [41, 40, "M"], [42, 40, "M"], [43, 40, "M"], [36, 41, "M"], [44, 41, "M"]],
    "mouth-wide": [[37, 39, "M"], [38, 39, "M"], [39, 39, "M"], [40, 39, "M"], [41, 39, "M"], [42, 39, "M"], [43, 39, "M"], [36, 40, "M"], [44, 40, "M"], [37, 40, "W"], [38, 40, "W"], [39, 40, "W"], [40, 40, "W"], [41, 40, "W"], [42, 40, "W"], [43, 40, "W"], [37, 41, "m"], [38, 41, "m"], [39, 41, "m"], [40, 41, "m"], [41, 41, "m"], [42, 41, "m"], [43, 41, "m"], [38, 42, "M"], [39, 42, "M"], [40, 42, "M"], [41, 42, "M"], [42, 42, "M"]],
    "mouth-round": [[39, 39, "M"], [40, 39, "M"], [41, 39, "M"], [38, 40, "M"], [42, 40, "M"], [38, 41, "M"], [42, 41, "M"], [39, 40, "m"], [40, 40, "m"], [41, 40, "m"], [39, 41, "m"], [40, 41, "m"], [41, 41, "m"], [39, 42, "M"], [40, 42, "M"], [41, 42, "M"]],
    "brows-raise": [[28, 23, "S"], [29, 23, "S"], [30, 23, "S"], [31, 23, "S"], [32, 23, "S"], [33, 23, "S"], [34, 23, "S"], [35, 23, "S"], [36, 23, "S"], [43, 23, "S"], [44, 23, "S"], [45, 23, "S"], [46, 23, "S"], [47, 23, "S"], [48, 23, "S"], [49, 23, "S"], [50, 23, "S"], [51, 23, "S"], [28, 22, "B"], [29, 22, "B"], [30, 22, "B"], [31, 22, "B"], [32, 22, "B"], [33, 22, "B"], [34, 22, "B"], [35, 22, "B"], [36, 22, "B"], [43, 22, "B"], [44, 22, "B"], [45, 22, "B"], [46, 22, "B"], [47, 22, "B"], [48, 22, "B"], [49, 22, "B"], [50, 22, "B"], [51, 22, "B"], [29, 21, "B"], [30, 21, "B"], [31, 21, "B"], [32, 21, "B"], [33, 21, "B"], [34, 21, "B"], [35, 21, "B"], [44, 21, "B"], [45, 21, "B"], [46, 21, "B"], [47, 21, "B"], [48, 21, "B"], [49, 21, "B"], [50, 21, "B"]],
    "brows-worry": [[28, 22, "S"], [29, 22, "S"], [30, 22, "S"], [31, 22, "S"], [32, 22, "S"], [33, 22, "S"], [34, 22, "S"], [35, 22, "S"], [36, 22, "S"], [28, 23, "S"], [29, 23, "S"], [30, 23, "S"], [31, 23, "S"], [32, 23, "S"], [33, 23, "S"], [34, 23, "S"], [35, 23, "S"], [36, 23, "S"], [43, 22, "S"], [44, 22, "S"], [45, 22, "S"], [46, 22, "S"], [47, 22, "S"], [48, 22, "S"], [49, 22, "S"], [50, 22, "S"], [51, 22, "S"], [43, 23, "S"], [44, 23, "S"], [45, 23, "S"], [46, 23, "S"], [47, 23, "S"], [48, 23, "S"], [49, 23, "S"], [50, 23, "S"], [51, 23, "S"], [28, 24, "B"], [29, 24, "B"], [30, 23, "B"], [31, 23, "B"], [32, 22, "B"], [33, 22, "B"], [34, 21, "B"], [35, 21, "B"], [36, 21, "B"], [51, 24, "B"], [50, 24, "B"], [49, 23, "B"], [48, 23, "B"], [47, 22, "B"], [46, 22, "B"], [45, 21, "B"], [44, 21, "B"], [43, 21, "B"]],
    "sweat": [[59, 17, "w"], [58, 18, "w"], [59, 18, "w"], [60, 18, "w"], [57, 19, "w"], [58, 19, "W"], [59, 19, "w"], [60, 19, "w"], [57, 20, "w"], [58, 20, "w"], [59, 20, "w"], [60, 20, "w"], [57, 21, "w"], [58, 21, "w"], [59, 21, "w"], [60, 21, "w"], [58, 22, "w"], [59, 22, "w"]],
    "think": [[62, 12, "t"], [63, 12, "t"], [62, 13, "t"], [63, 13, "t"], [67, 8, "t"], [68, 8, "t"], [67, 9, "t"], [68, 9, "t"], [72, 4, "t"], [73, 4, "t"], [72, 5, "t"], [73, 5, "t"]],
  };
  const PHASE_BY_LOOK = {
    examiner_playing: "speaking",
    recording: "listening",
    examiner_loading: "thinking", loading: "thinking", processing: "thinking", scoring: "thinking", turn_saved: "thinking",
  };
  const REACTION_BY_SIGNAL = { strong: "nod", adequate: "smile", weak: "sweat" };
  const REACTION_MS = { nod: 2200, smile: 1600, sweat: 2600 };
  // 说话时一个“音节”一个嘴型，不连着重复；几个音节一句，句间合嘴停一下，句首偶尔挑眉、头轻轻一点
  const TALK_SHAPES = ["mid", "open", "wide", "round", "mid", "open"];

  // 同色相邻的格子合成一条 rect，SVG 里元素少一些
  function rects(cells) {
    const rows = new Map();
    cells.forEach(([x, y, code]) => {
      if (!rows.has(y)) rows.set(y, []);
      rows.get(y).push([x, code]);
    });
    let out = "";
    rows.forEach((items, y) => {
      items.sort((a, b) => a[0] - b[0]);
      for (let i = 0; i < items.length;) {
        let j = i;
        while (j + 1 < items.length && items[j + 1][1] === items[i][1] && items[j + 1][0] === items[j][0] + 1) j += 1;
        out += `<rect class="px-${items[i][1]}" x="${items[i][0]}" y="${y}" width="${j - i + 1}" height="1"/>`;
        i = j + 1;
      }
    });
    return out;
  }

  function baseCells(fromRow, toRow) {
    const cells = [];
    for (let y = fromRow; y < toRow; y += 1) {
      [...BASE[y]].forEach((code, x) => { if (code !== ".") cells.push([x, y, code]); });
    }
    return cells;
  }

  function markup() {
    const layer = (name) => `<g class="iv-iv-layer" data-layer="${name}">${rects(OVER[name])}</g>`;
    return `<svg viewBox="0 0 ${BASE.length} ${BASE.length}" shape-rendering="crispEdges" aria-hidden="true" focusable="false">
      <g class="iv-iv-body">${rects(baseCells(HEAD_ROWS, BASE.length))}</g>
      <g class="iv-iv-head">${rects(baseCells(0, HEAD_ROWS))}${Object.keys(OVER).map(layer).join("")}</g>
    </svg>`;
  }

  function create({ host, active, anchors }) {
    let el = null;
    let phase = "idle";
    let mouth = "closed";
    let blink = false;
    let reaction = "";
    let reactionTimer = 0;
    let mouthTimer = 0;
    let blinkTimer = 0;
    let brows = false;
    let beat = false;
    let seed = 7; // fixed-seed pseudo-random: an uneven rhythm that tests can replay
    const rand = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
    const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

    function node() {
      if (el) return el;
      const pane = host();
      if (!pane) return null;
      el = document.createElement("div");
      el.id = "ivInterviewer";
      el.className = "iv-interviewer hidden";
      el.setAttribute("aria-hidden", "true");
      el.innerHTML = markup();
      const kicker = pane.querySelector("#promptKicker");
      if (kicker) kicker.after(el);
      else pane.prepend(el);
      watchLayout(pane);
      return el;
    }

    // ---- 和右栏对齐（桌面宽度）：底边落在“人像竖直居中对准录音大圆”时的位置，从底边往上长到 PROMPT 标签下面；
    // 题目从转写区的顶边开始。题目太长（P2 题卡）时题目往上让、人整个跟着上移，大小不变，可以上到 PROMPT 标签旁边
    // （标签在最左，和人不重叠）；到顶了还放不下才缩小差的那一点，题目永远完整显示。
    // 同一次练习、同一窗口大小里只往上让、不往回弹，换题时人不会跳来跳去。
    // 参照物不在（P3 选题、窄屏）时交回 CSS 的默认位置。
    let alignFrame = 0;
    let held = null; // { key, bottom, size }: the highest / smallest placement used so far in this practice
    function scheduleAlign() {
      if (alignFrame) return;
      alignFrame = window.requestAnimationFrame?.(() => { alignFrame = 0; align(); }) || 0;
    }
    function watchLayout(pane) {
      const { circle, text } = anchors?.() || {};
      // size / content changes are handled before that frame paints (both callbacks run ahead of paint), so he never lags a frame
      if (window.ResizeObserver) {
        const observer = new window.ResizeObserver(() => align());
        [pane, circle, text].forEach((target) => target && observer.observe(target));
      }
      const card = pane.querySelector?.("#promptCard");
      if (card && window.MutationObserver) {
        new window.MutationObserver(() => align()).observe(card, { childList: true, subtree: true, characterData: true });
      }
      window.addEventListener?.("resize", scheduleAlign);
    }
    function align() {
      const pane = host();
      if (!pane || !el) return;
      const { circle, text, session } = anchors?.() || {};
      const card = pane.querySelector("#promptCard");
      const c = circle?.getBoundingClientRect?.();
      const t = text?.getBoundingClientRect?.();
      const wide = window.matchMedia?.("(min-width: 981px)").matches === true;
      if (el.classList.contains("hidden") || !card || !c?.height || !t?.height || !wide) {
        pane.classList.remove("iv-aligned");
        return;
      }
      pane.classList.add("iv-aligned"); // the avatar leaves the flow first, so the card's own top is measured without it
      const p = pane.getBoundingClientRect();
      const box = card.getBoundingClientRect();
      const kids = [...card.children].filter((child) => window.getComputedStyle(child).position !== "absolute");
      const contentHeight = kids.length ? kids[kids.length - 1].getBoundingClientRect().bottom - kids[0].getBoundingClientRect().top : 0;
      const padBottom = parseFloat(window.getComputedStyle(card).paddingBottom) || 0;
      const cardTop = box.top - p.top;
      const textTop = Math.max(cardTop, Math.min(t.top - p.top, box.bottom - p.top - padBottom - contentHeight));
      const kicker = pane.querySelector("#promptKicker")?.getBoundingClientRect();
      const ceiling = (kicker ? kicker.bottom : p.top) - p.top + 6;
      // centre the drawn figure (hair to desk), not the canvas: the rows above the hair are room for the 思考 dots
      const top = BASE.findIndex((row) => /[^.]/.test(row));
      const mid = (top + BASE.length) / 2 / BASE.length;
      const center = c.top + c.height / 2 - p.top;
      const home = center + c.height * 1.15 * (1 - mid);
      const reach = Math.min(top, ...OVER.think.map(([, y]) => y)) / BASE.length; // the 思考 dots must clear the label too
      const normal = Math.max(96, Math.min(c.height * 1.35, (home - ceiling) / (1 - reach)));
      const bottom = Math.min(home, textTop - 10);
      const label = labelBox(pane.querySelector("#promptKicker")); // the label's text, not its full-width box
      const roof = label && label.right < p.left + p.width / 2 - normal / 2 ? 8 : ceiling;
      let size = Math.max(96, Math.min(normal, (bottom - roof) / (1 - reach)));
      let place = bottom;
      const key = `${session}|${window.innerWidth}x${window.innerHeight}`;
      if (held?.key === key) { place = Math.min(place, held.bottom); size = Math.min(size, held.size); }
      held = { key, bottom: place, size };
      pane.style.setProperty("--iv-avatar-top", `${Math.round(place - size)}px`);
      pane.style.setProperty("--iv-avatar-size", `${Math.round(size)}px`);
      pane.style.setProperty("--iv-text-pad", `${Math.round(textTop - cardTop)}px`);
    }

    function labelBox(node) {
      if (!node || !document.createRange) return null;
      const range = document.createRange();
      range.selectNodeContents(node);
      return range.getBoundingClientRect();
    }

    function paint() {
      if (!el) return;
      const eyes = blink && phase !== "thinking" ? "blink" : ({ listening: "downright", thinking: "up" }[phase] || "open");
      let face = mouth;
      if (phase !== "speaking") face = reaction === "sweat" ? "frown" : (reaction === "nod" || reaction === "smile" ? "smile" : "closed");
      const on = new Set([`eyes-${eyes}`, `mouth-${face}`]);
      if (reaction === "sweat") { on.add("brows-worry"); on.add("sweat"); }
      else if (brows && phase === "speaking") on.add("brows-raise");
      if (phase === "thinking") on.add("think");
      el.querySelectorAll(".iv-iv-layer").forEach((layer) => layer.classList.toggle("is-on", on.has(layer.dataset.layer)));
      el.dataset.phase = phase;
      el.dataset.reaction = reaction;
      el.dataset.beat = beat && phase === "speaking" ? "1" : "";
    }

    function setMouthCycle(running) {
      window.clearTimeout(mouthTimer);
      mouthTimer = 0;
      mouth = "closed";
      brows = false;
      beat = false;
      if (!running) return;
      if (reducedMotion()) { mouth = "mid"; return; }
      let left = 0; // syllables left in this phrase
      const step = () => {
        if (left <= 0) { // between phrases: mouth shut for a breath; the next phrase may open with raised brows and a dip
          left = 3 + Math.floor(rand() * 6);
          mouth = "closed";
          brows = rand() < 0.35;
          beat = rand() < 0.5;
          paint();
          mouthTimer = window.setTimeout(step, 180 + rand() * 200);
          return;
        }
        left -= 1;
        let next = mouth;
        while (next === mouth) next = TALK_SHAPES[Math.floor(rand() * TALK_SHAPES.length)];
        mouth = next;
        paint();
        beat = false;
        if (left < 2) brows = false;
        mouthTimer = window.setTimeout(step, 80 + rand() * 100);
      };
      left = 2 + Math.floor(rand() * 4);
      step();
    }

    function scheduleBlink() {
      window.clearTimeout(blinkTimer);
      if (!el || el.classList.contains("hidden") || reducedMotion()) return;
      blinkTimer = window.setTimeout(() => {
        blink = true;
        paint();
        window.setTimeout(() => { blink = false; paint(); scheduleBlink(); }, 140);
      }, 2600 + Math.random() * 3000);
    }

    // 页面在面试练习页时显示，离开时停掉所有计时
    function sync() {
      const show = !!active();
      if (!show && !el) return;
      const target = node();
      if (!target) return;
      const wasHidden = target.classList.contains("hidden");
      target.classList.toggle("hidden", !show);
      if (!show) {
        setMouthCycle(false);
        window.clearTimeout(blinkTimer);
        host()?.classList.remove("iv-aligned");
        return;
      }
      if (wasHidden) scheduleBlink();
      paint();
      if (wasHidden) align(); // placed in the same frame it appears, never first drawn at the default spot
      else scheduleAlign();
    }

    // look = 录音按钮的外观状态（native_* 已映射成 examiner_playing / recording / processing）
    function setStatus(look) {
      sync(); // Start and exit flip the practice lock together with the record button, so show / hide follows it here too
      const next = PHASE_BY_LOOK[look] || "idle";
      if (next === phase) return;
      phase = next;
      setMouthCycle(phase === "speaking");
      paint();
    }

    function react(signal) {
      const next = REACTION_BY_SIGNAL[signal] || "";
      if (!next || !el || el.classList.contains("hidden")) return;
      window.clearTimeout(reactionTimer);
      reaction = "";
      paint();
      void el.offsetWidth; // restart the nod animation when two reactions come back to back
      reaction = next;
      paint();
      reactionTimer = window.setTimeout(() => { reaction = ""; paint(); }, REACTION_MS[next]);
    }

    return { sync, setStatus, react, state: () => ({ phase, mouth, reaction }) };
  }

  // app.js talks to the page's one avatar through these, so calls made before it exists are simply no-ops
  let current = null;
  window.IELTSInterviewer = {
    create: (options) => (current = create(options)),
    sync: () => current?.sync(),
    setStatus: (look) => current?.setStatus(look),
    react: (signal) => current?.react(signal),
    PHASE_BY_LOOK,
    REACTION_BY_SIGNAL,
  };
})();
