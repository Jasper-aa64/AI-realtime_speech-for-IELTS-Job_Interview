(function () {
  // 面试练习页左栏的像素面试官：念题时说话，回答时看向右边在听，等 AI 时眼睛往上在想；
  // 每题答完按面试官的判断反应一下（strong 点头 + 笑，adequate 淡淡一笑，weak 皱眉流汗）。
  // 只是表情，不影响流程。动作由 app.js 喂进来：setStatus(录音按钮的状态)、react(判断)、sync()（跟随页面显示/隐藏）。
  // 64×64 的像素格（由形状栅格化生成）：BASE 是不变的部分（"." 透明），OVER 是可切换的眼睛 / 嘴 / 眉毛 / 汗珠 / 思考点。
  // 头部 = 第 0-34 行，点头时只有它动。
  const BASE = [
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "............................hhhHHHHH............................",
    ".........................HhhHHHHHHHhhHH.........................",
    "........................HhHHHHHHHHHHHhHH........................",
    ".......................HhHHHHHHHHHHHHHHhH.......................",
    "......................HHHHHHHHHHHHHHHHHHhH......................",
    "....................HHHHHHHHHHHHHHHHHHHHHHHH....................",
    "....................HHHHHHHHHHHHHHHHHHHHHHHH....................",
    "....................HHHHHHHHHHHHHHHHHHHHHHHH....................",
    "...................HHHHHHHHHHHssssHHHHHHHHHHH...................",
    "...................HHssssHHHHHSSSSsssssHHHHHH...................",
    "...................HHSSSSsssssSSSSSSSSSssssHH...................",
    "..................HHHSSSBBBBBSSSSSSBBBBBSSSHHH..................",
    "..................HHHSSBSSSSSBSSSSBSSSSSBSSHHH..................",
    "..................HHHSSSSSSSSSSSSSSSSSSSSSSHHH..................",
    "..................HHHSGGGGGGGSSSSSSGGGGGGGSHHH..................",
    "..................SGGGLllLLLLGSSSSGLllLLLLGGGS..................",
    "..................SSSGLlLLLLLGGGGGGLlLLLLLGSSS..................",
    ".................SSSSGLLLLLLLGSSSSGLLLLLLLGSSSS.................",
    ".................SSsSGLLLLLLLGSSSSGLLLLLLLGSsSS.................",
    "..................SsSGLLLLLLLGSSSSGLLLLLLLGSsS..................",
    "..................SSSSGGGGGGGSSSsSSGGGGGGGSSSS..................",
    "...................S.SSSSSSSSSSSsSSSSSSSSSS.S...................",
    ".....................SSSSSSSSSSSssSSSSSSSSS.....................",
    "......................SSSSSSSSSsssSSSSSSSS......................",
    "......................SSSSSSSSSSSSSSSSSSSS......................",
    ".......................sSSSSSSSSSSSSSSSSs.......................",
    "........................sSSSSSSSSSSSSSSs........................",
    ".........................sSSSSSSSSSSSSs.........................",
    "..........................sssSSSSSSsss..........................",
    "...........................ssssssssss...........................",
    "...........................SSSSSSSSSS...........................",
    "...........................SSSSSSSSSS...........................",
    "...........................SSSSSSSSSS...........................",
    ".........................TTTTTTTTTTTTTT.........................",
    "...................JJJJJJTTTTTRRRRTTTTTJJJJJJ...................",
    "...............JJJJJJJJJJjTTTTRrRRTTTjJJJJJJJJJJJ...............",
    "............JJJJJJJJJJJJJJjTTTRRRRTTjJJJJJJJJJJJJJJJ............",
    "............JJJJJJJJJJJJJJjJTTRRRRTTjJJJJJJJJJJJJJJJ............",
    "..........JJJJJJJJJJJJJJJJJjJTRrRRTjJJJJJJJJJJJJJJJJJJ..........",
    "........JJJJJJJJJJJJJJJJJJJJjTRRRRjJJJJJJJJJJJJJJJJJJJJJ........",
    "......JJJJJJJJJJJJJJJJJJJJJJjJRRRRjJJJJJJJJJJJJJJJJJJJJJJJ......",
    ".....JJJJJJJJJJJJJJJJJJJJJJJJjRrRRJJJJJJJJJJJJJJJJJJJJJJJJJ.....",
    ".....JJJJJJJJJJJJJJJJJJJJJJJJJRRRRJJJJJJJJJJJJJJJJJJJJJJJJJ.....",
    ".....JJJJJJJJJJJJJJJJJJJJJJJJJRRRRJJJJJJJJJJJJJJJJJJJJJJJJJ.....",
    ".....JJJJJJJJJJJJJJJJJJJJJJJJJJRRJJJJJJJJJJJJJJJJJJJJJJJJJJ.....",
    ".....JJJJJJJJJJJJJJJJJJJJJJJJJJRRJJJJJJJJJJJJJJJJJJJJJJJJJJ.....",
    ".....JJJJJJJJJJJJJJJJJJJJJJJJJJRRJJJJJJJJJJJJJJJJJJJJJJJJJJ.....",
    ".....JJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJ.....",
    ".....JJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJ.....",
    "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD",
    "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  ];
  const HEAD_ROWS = 35;
  const OVER = {
    "eyes-open": [[24, 25, "e"], [25, 25, "e"], [26, 25, "e"], [24, 26, "e"], [25, 26, "e"], [26, 26, "e"], [25, 25, "E"], [25, 26, "E"], [26, 26, "E"], [37, 25, "e"], [38, 25, "e"], [39, 25, "e"], [37, 26, "e"], [38, 26, "e"], [39, 26, "e"], [38, 25, "E"], [38, 26, "E"], [39, 26, "E"]],
    "eyes-side": [[24, 25, "e"], [25, 25, "e"], [26, 25, "e"], [24, 26, "e"], [25, 26, "e"], [26, 26, "e"], [26, 25, "E"], [26, 26, "E"], [27, 26, "E"], [37, 25, "e"], [38, 25, "e"], [39, 25, "e"], [37, 26, "e"], [38, 26, "e"], [39, 26, "e"], [39, 25, "E"], [39, 26, "E"], [40, 26, "E"]],
    "eyes-up": [[24, 25, "e"], [25, 25, "e"], [26, 25, "e"], [24, 26, "e"], [25, 26, "e"], [26, 26, "e"], [25, 24, "E"], [25, 25, "E"], [26, 25, "E"], [37, 25, "e"], [38, 25, "e"], [39, 25, "e"], [37, 26, "e"], [38, 26, "e"], [39, 26, "e"], [38, 24, "E"], [38, 25, "E"], [39, 25, "E"]],
    "eyes-blink": [[23, 26, "E"], [24, 26, "E"], [25, 26, "E"], [26, 26, "E"], [27, 26, "E"], [36, 26, "E"], [37, 26, "E"], [38, 26, "E"], [39, 26, "E"], [40, 26, "E"]],
    "mouth-closed": [[29, 34, "M"], [30, 34, "M"], [31, 34, "M"], [32, 34, "M"], [33, 34, "M"], [34, 34, "M"], [35, 34, "M"]],
    "mouth-mid": [[29, 34, "M"], [30, 34, "M"], [31, 34, "M"], [32, 34, "M"], [33, 34, "M"], [34, 34, "M"], [35, 34, "M"], [30, 35, "m"], [31, 35, "m"], [32, 35, "m"], [33, 35, "m"], [34, 35, "m"]],
    "mouth-open": [[29, 33, "M"], [30, 33, "M"], [31, 33, "M"], [32, 33, "M"], [33, 33, "M"], [34, 33, "M"], [35, 33, "M"], [29, 34, "m"], [30, 34, "m"], [31, 34, "m"], [32, 34, "m"], [33, 34, "m"], [34, 34, "m"], [35, 34, "m"], [29, 35, "m"], [30, 35, "m"], [31, 35, "m"], [32, 35, "m"], [33, 35, "m"], [34, 35, "m"], [35, 35, "m"], [30, 36, "M"], [31, 36, "M"], [32, 36, "M"], [33, 36, "M"], [34, 36, "M"], [30, 34, "W"], [31, 34, "W"], [32, 34, "W"], [33, 34, "W"], [34, 34, "W"]],
    "mouth-smile": [[28, 33, "M"], [36, 33, "M"], [29, 34, "M"], [30, 34, "M"], [31, 34, "M"], [32, 34, "M"], [33, 34, "M"], [34, 34, "M"], [35, 34, "M"], [30, 35, "m"], [31, 35, "m"], [32, 35, "m"], [33, 35, "m"], [34, 35, "m"], [24, 31, "b"], [25, 31, "b"], [39, 31, "b"], [40, 31, "b"]],
    "mouth-frown": [[29, 34, "M"], [30, 34, "M"], [31, 34, "M"], [32, 34, "M"], [33, 34, "M"], [34, 34, "M"], [35, 34, "M"], [28, 35, "M"], [36, 35, "M"]],
    "brows-worry": [[23, 19, "S"], [24, 19, "S"], [25, 19, "S"], [26, 19, "S"], [27, 19, "S"], [28, 19, "S"], [29, 19, "S"], [23, 20, "S"], [24, 20, "S"], [25, 20, "S"], [26, 20, "S"], [27, 20, "S"], [28, 20, "S"], [29, 20, "S"], [34, 19, "S"], [35, 19, "S"], [36, 19, "S"], [37, 19, "S"], [38, 19, "S"], [39, 19, "S"], [40, 19, "S"], [34, 20, "S"], [35, 20, "S"], [36, 20, "S"], [37, 20, "S"], [38, 20, "S"], [39, 20, "S"], [40, 20, "S"], [23, 21, "B"], [24, 21, "B"], [25, 20, "B"], [26, 20, "B"], [27, 19, "B"], [28, 18, "B"], [29, 18, "B"], [40, 21, "B"], [39, 21, "B"], [38, 20, "B"], [37, 20, "B"], [36, 19, "B"], [35, 18, "B"], [34, 18, "B"]],
    "sweat": [[48, 15, "w"], [47, 16, "w"], [48, 16, "w"], [49, 16, "w"], [46, 17, "w"], [47, 17, "W"], [48, 17, "w"], [49, 17, "w"], [46, 18, "w"], [47, 18, "w"], [48, 18, "w"], [49, 18, "w"], [47, 19, "w"], [48, 19, "w"]],
    "think": [[50, 9, "t"], [51, 9, "t"], [50, 10, "t"], [51, 10, "t"], [54, 6, "t"], [55, 6, "t"], [54, 7, "t"], [55, 7, "t"], [58, 3, "t"], [59, 3, "t"], [58, 4, "t"], [59, 4, "t"]],
  };
  const PHASE_BY_LOOK = {
    examiner_playing: "speaking",
    recording: "listening",
    examiner_loading: "thinking", loading: "thinking", processing: "thinking", scoring: "thinking", turn_saved: "thinking",
  };
  const REACTION_BY_SIGNAL = { strong: "nod", adequate: "smile", weak: "sweat" };
  const REACTION_MS = { nod: 2200, smile: 1600, sweat: 2600 };
  const MOUTH_CYCLE = ["mid", "open", "mid", "closed"];

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
    return `<svg viewBox="0 0 64 64" shape-rendering="crispEdges" aria-hidden="true" focusable="false">
      <g class="iv-iv-body">${rects(baseCells(HEAD_ROWS, BASE.length))}</g>
      <g class="iv-iv-head">${rects(baseCells(0, HEAD_ROWS))}${Object.keys(OVER).map(layer).join("")}</g>
    </svg>`;
  }

  function create({ host, active }) {
    let el = null;
    let phase = "idle";
    let mouth = "closed";
    let blink = false;
    let reaction = "";
    let reactionTimer = 0;
    let mouthTimer = 0;
    let blinkTimer = 0;
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
      return el;
    }

    function paint() {
      if (!el) return;
      const eyes = blink && phase !== "thinking" ? "blink" : ({ listening: "side", thinking: "up" }[phase] || "open");
      let face = mouth;
      if (phase !== "speaking") face = reaction === "sweat" ? "frown" : (reaction === "nod" || reaction === "smile" ? "smile" : "closed");
      const on = new Set([`eyes-${eyes}`, `mouth-${face}`]);
      if (reaction === "sweat") { on.add("brows-worry"); on.add("sweat"); }
      if (phase === "thinking") on.add("think");
      el.querySelectorAll(".iv-iv-layer").forEach((layer) => layer.classList.toggle("is-on", on.has(layer.dataset.layer)));
      el.dataset.phase = phase;
      el.dataset.reaction = reaction;
    }

    function setMouthCycle(running) {
      window.clearInterval(mouthTimer);
      mouthTimer = 0;
      mouth = "closed";
      if (!running) return;
      if (reducedMotion()) { mouth = "mid"; return; }
      let step = 0;
      mouthTimer = window.setInterval(() => {
        mouth = MOUTH_CYCLE[step % MOUTH_CYCLE.length];
        step += 1;
        paint();
      }, 120);
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
        return;
      }
      if (wasHidden) scheduleBlink();
      paint();
    }

    // look = 录音按钮的外观状态（native_* 已映射成 examiner_playing / recording / processing）
    function setStatus(look) {
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
