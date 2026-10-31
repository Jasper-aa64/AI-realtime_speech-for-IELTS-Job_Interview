(function () {
  // 面试练习页左栏的像素面试官：念题时说话，回答时看向右边在听，等 AI 时眼睛往上在想；
  // 每题答完按面试官的判断反应一下（strong 点头 + 笑，adequate 淡淡一笑，weak 皱眉流汗）。
  // 只是表情，不影响流程。动作由 app.js 喂进来：setStatus(录音按钮的状态)、react(判断)、sync()（跟随页面显示/隐藏）。
  // 32×32 的像素格：BASE 是不变的部分（"." 透明），OVER 是可切换的眼睛 / 嘴 / 眉毛 / 汗珠。头部 = 第 0-19 行，点头时只有它动。
  const BASE = [
    "................................",
    "................................",
    "................................",
    "..........HHHHHHHHHHHH..........",
    ".........HHHHHHHHHHHHHH.........",
    "........HHHHHHHHHHHHHHHH........",
    "........HHHHHHHHHHHHHHHH........",
    "........HHHSSSSSSSSSSHHH........",
    "........HHSSSSSSSSSSSSHH........",
    "........HSSBBBSSSSBBBSSH........",
    "........sSGGGGGGGGGGGGSs........",
    "........sSGSSSGSSGSSSGSs........",
    "........sSGSSSGSSGSSSGSs........",
    "........sSGGGGGSSGGGGGSs........",
    ".........SSSSSSssSSSSSS.........",
    ".........SSSSSSSSSSSSSS.........",
    ".........SSSSSSSSSSSSSS.........",
    ".........SSSSSSSSSSSSSS.........",
    "..........SSSSSSSSSSSS..........",
    "...........ssssssssss...........",
    ".............SSSSSS.............",
    ".......JJJJJJTSSSSTJJJJJJ.......",
    ".....JJJJJJJjTTRRTTjJJJJJJJ.....",
    "....JJJJJJJJJjTRRTjJJJJJJJJJ....",
    "...JJJJJJJJJJjTRRTjJJJJJJJJJJ...",
    "..JJJJJJJJJJJjTRRTjJJJJJJJJJJJ..",
    "..JJJJJJJJJJJJjRRjJJJJJJJJJJJJ..",
    "..JJJJJJJJJJJJJjjJJJJJJJJJJJJJ..",
    "..JJJJJJJJJJJJJJJJJJJJJJJJJJJJ..",
    "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD",
    "dddddddddddddddddddddddddddddddd",
    "dddddddddddddddddddddddddddddddd",
  ];
  const HEAD_ROWS = 20;
  const run = (from, to, y, code) => Array.from({ length: to - from + 1 }, (_, i) => [from + i, y, code]);
  const OVER = {
    "eyes-open": [[12, 12, "E"], [19, 12, "E"]],
    "eyes-side": [[13, 12, "E"], [20, 12, "E"]],          // 看向右边的回答区
    "eyes-up": [[12, 11, "E"], [19, 11, "E"]],
    "eyes-blink": [...run(11, 13, 12, "E"), ...run(18, 20, 12, "E")],
    "mouth-closed": run(14, 17, 16, "M"),
    "mouth-mid": [...run(14, 17, 16, "M"), [15, 17, "m"], [16, 17, "m"]],
    "mouth-open": [...run(14, 17, 16, "M"), ...run(14, 17, 17, "m")],
    "mouth-smile": [[13, 15, "M"], [18, 15, "M"], ...run(14, 17, 16, "M")],
    "mouth-frown": [...run(14, 17, 16, "M"), [13, 17, "M"], [18, 17, "M"]],
    "brows-worry": [[11, 9, "S"], [20, 9, "S"], [13, 8, "B"], [18, 8, "B"]],
    "sweat": [[24, 7, "w"], [23, 8, "w"], [24, 8, "W"], [25, 8, "w"], [23, 9, "w"], [24, 9, "w"], [25, 9, "w"], [24, 10, "w"]],
    "think": [[25, 4, "t"], [27, 3, "t"], [29, 2, "t"]],
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
    return `<svg viewBox="0 0 32 32" shape-rendering="crispEdges" aria-hidden="true" focusable="false">
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
