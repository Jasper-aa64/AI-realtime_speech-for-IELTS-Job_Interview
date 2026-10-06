(function () {
  // Interview mode shows the IELTS home panel itself (#homePanel, same markup, CSS and carousel script), so the
  // layout is identical by construction; only words, numbers and link targets change. Every node touched keeps its
  // IELTS original, and switching back restores it exactly.
  const go = (pane, part = "") => ({ href: "?view=interview", "data-view": null, "data-home-mode": null, "data-corpus-home-target": null, "data-iv-target": part ? `${pane}:${part}` : pane });

  // [selector inside #homePanel, change, link target?]. `text` replaces the whole text; `label` replaces only the
  // first text node, so an element's children (arrows, counters, nested spans) stay the same nodes.
  const COPY = [
    [".hx-kicker", { text: "Interview Studio" }],
    [".hx-title-top", { text: "把做过的系统，讲成面试官想听的答案" }],
    [".hx-title-main", { text: "Mock Interview" }],
    [".hx-topics span:nth-of-type(1)", { text: "项目" }],
    [".hx-topics span:nth-of-type(2)", { text: "知识点" }],
    [".hx-topics span:nth-of-type(3)", { text: "语料" }],
    [".hx-topics span:nth-of-type(4)", { text: "报告" }],
    [".hx-actions a:nth-of-type(1)", { label: "开始完整面试 " }, go("practice", "full")],
    [".hx-actions a:nth-of-type(2)", { label: "简历 / JD 定制 " }, go("custom")],
    // Carousel: same five slides; the screenshots stay as placeholders until interview images exist.
    [".hx-slide:nth-of-type(1)", {}, go("practice", "full")],
    [".hx-slide:nth-of-type(1) .hx-slide-chip", { text: "Interview" }],
    [".hx-slide:nth-of-type(1) .hx-slide-body strong", { text: "完整面试" }],
    [".hx-slide:nth-of-type(1) .hx-slide-body > span", { text: "自我介绍、项目、知识点、奖项、反问，一场走完。" }],
    [".hx-slide:nth-of-type(2)", {}, go("practice", "project")],
    [".hx-slide:nth-of-type(2) .hx-slide-chip", { text: "Projects" }],
    [".hx-slide:nth-of-type(2) .hx-slide-body strong", { text: "项目深挖" }],
    [".hx-slide:nth-of-type(2) .hx-slide-body > span", { text: "每个项目一张题卡，面试官按你的回答现场追问。" }],
    [".hx-slide:nth-of-type(3)", {}, go("practice", "knowledge")],
    [".hx-slide:nth-of-type(3) .hx-slide-chip", { text: "Knowledge" }],
    [".hx-slide:nth-of-type(3) .hx-slide-body strong", { text: "知识点" }],
    [".hx-slide:nth-of-type(3) .hx-slide-body > span", { text: "技术栈题与精选题库，答完沉淀成自己的标准答法。" }],
    [".hx-slide:nth-of-type(4)", {}, go("reports")],
    [".hx-slide:nth-of-type(4) .hx-slide-chip", { text: "Report" }],
    [".hx-slide:nth-of-type(4) .hx-slide-body strong", { text: "百分制报告" }],
    [".hx-slide:nth-of-type(4) .hx-slide-body > span", { text: "五个维度打分，标出能力边界和下一步练什么。" }],
    [".hx-slide:nth-of-type(5)", {}, go("custom")],
    [".hx-slide:nth-of-type(5) .hx-slide-chip", { text: "Resume" }],
    [".hx-slide:nth-of-type(5) .hx-slide-body strong", { text: "简历 / JD 定制" }],
    [".hx-slide:nth-of-type(5) .hx-slide-body > span", { text: "简历拆成项目和技术栈题卡，JD 生成岗位题和反问。" }],
    // Data panel.
    [".hx-stat:nth-of-type(1) dt", { text: "面试场次" }],
    [".hx-stat:nth-of-type(1) dd a", {}, go("reports")],
    [".hx-stat:nth-of-type(2) dt", { text: "平均分" }],
    [".hx-stat:nth-of-type(2) dd a", {}, go("reports")],
    [".hx-panel > p.hx-panel-label:nth-of-type(1)", { text: "语料准备" }],
    [".hx-panel > div.hx-chips:nth-of-type(1) a:nth-of-type(1)", { label: "项目讲述稿" }, go("corpus", "resume")],
    [".hx-panel > div.hx-chips:nth-of-type(1) a:nth-of-type(2)", { label: "知识点" }, go("corpus", "knowledge")],
    [".hx-panel > div.hx-chips:nth-of-type(1) a:nth-of-type(3)", { label: "JD 与反问" }, go("corpus", "jd")],
    [".hx-panel > p.hx-panel-label:nth-of-type(2)", { label: "面试题库 · " }],
    [".hx-panel [data-hx-bank=\"label\"]", { text: "精选 + 简历" }],
    [".hx-panel > div.hx-chips:nth-of-type(2) a:nth-of-type(1)", { label: "完整面试" }, go("practice", "full")],
    [".hx-panel > div.hx-chips:nth-of-type(2) a:nth-of-type(2)", { label: "项目深挖" }, go("practice", "project")],
    [".hx-panel > div.hx-chips:nth-of-type(2) a:nth-of-type(3)", { label: "知识点" }, go("practice", "knowledge")],
    [".hx-panel > div.hx-chips:nth-of-type(2) a:nth-of-type(4)", { text: "面试语料库 →" }, go("corpus")],
    // Practice paths: same three cards with the same number of rows.
    [".hx-sec-more", { label: "进入面试语料库 " }, go("corpus")],
    [".hx-area:nth-of-type(1) .hx-area-index", { text: "01 · Interview" }],
    [".hx-area:nth-of-type(1) .hx-area-name", { text: "面试练习" }],
    [".hx-area:nth-of-type(1) .hx-area-blurb", { text: "面试官读题，准备 3 秒自动录音，按你的回答决定下一题还是追问。" }],
    [".hx-area:nth-of-type(1) li:nth-of-type(1) a", {}, go("practice", "full")],
    [".hx-area:nth-of-type(1) li:nth-of-type(1) b", { text: "Mock" }],
    [".hx-area:nth-of-type(1) li:nth-of-type(1) span", { text: "完整面试" }],
    [".hx-area:nth-of-type(1) li:nth-of-type(2) a", {}, go("practice", "project")],
    [".hx-area:nth-of-type(1) li:nth-of-type(2) b", { text: "Project" }],
    [".hx-area:nth-of-type(1) li:nth-of-type(2) span", { text: "项目深挖" }],
    [".hx-area:nth-of-type(1) li:nth-of-type(3) a", {}, go("practice", "knowledge")],
    [".hx-area:nth-of-type(1) li:nth-of-type(3) b", { text: "Stack" }],
    [".hx-area:nth-of-type(1) li:nth-of-type(3) span", { text: "知识点" }],
    [".hx-area:nth-of-type(1) li:nth-of-type(4) a", {}, go("practice", "reverse")],
    [".hx-area:nth-of-type(1) li:nth-of-type(4) b", { text: "Ask" }],
    [".hx-area:nth-of-type(1) li:nth-of-type(4) span", { text: "反问环节" }],
    [".hx-area:nth-of-type(2) .hx-area-index", { text: "02 · Report" }],
    [".hx-area:nth-of-type(2) .hx-area-name", { text: "面试报告" }],
    [".hx-area:nth-of-type(2) .hx-area-blurb", { text: "百分制评分加逐题点评，标出答得扎实和还有缺口的地方。" }],
    [".hx-area:nth-of-type(2) li:nth-of-type(1) a", {}, go("reports")],
    [".hx-area:nth-of-type(2) li:nth-of-type(1) b", { text: "Report" }],
    [".hx-area:nth-of-type(2) li:nth-of-type(1) span", { text: "全部报告" }],
    [".hx-area:nth-of-type(2) li:nth-of-type(2) a", {}, go("custom")],
    [".hx-area:nth-of-type(2) li:nth-of-type(2) b", { text: "CV" }],
    [".hx-area:nth-of-type(2) li:nth-of-type(2) span", { text: "简历 / JD 定制" }],
    [".hx-area:nth-of-type(3) .hx-area-index", { text: "03 · Corpus" }],
    [".hx-area:nth-of-type(3) .hx-area-name", { text: "面试语料" }],
    [".hx-area:nth-of-type(3) .hx-area-blurb", { text: "项目讲述稿、知识点答法和反问问题沉淀下来，面试前随时复习。" }],
    [".hx-area:nth-of-type(3) li:nth-of-type(1) a", {}, go("corpus", "resume")],
    [".hx-area:nth-of-type(3) li:nth-of-type(1) b", { text: "Project" }],
    [".hx-area:nth-of-type(3) li:nth-of-type(1) span", { text: "项目题卡" }],
    [".hx-area:nth-of-type(3) li:nth-of-type(2) a", {}, go("corpus", "knowledge")],
    [".hx-area:nth-of-type(3) li:nth-of-type(2) b", { text: "Stack" }],
    [".hx-area:nth-of-type(3) li:nth-of-type(2) span", { text: "知识点语料" }],
    [".hx-area:nth-of-type(3) li:nth-of-type(3) a", {}, go("corpus", "jd")],
    [".hx-area:nth-of-type(3) li:nth-of-type(3) b", { text: "JD" }],
    [".hx-area:nth-of-type(3) li:nth-of-type(3) span", { text: "JD 与反问" }],
  ];
  // The 语料库 hub (#corpusPanel) the same way: its two cards open the knowledge and resume screens, the review lane
  // holds JD & questions, Resume / JD and the reports.
  const HUB_COPY = [
    [".corpus-page-kicker", { text: "Interview Library" }],
    [".corpus-home-title", { text: "面试语料库" }],
    [".corpus-home-sub", { text: "把知识点答法、简历题卡和反问问题放在同一个工作台里。" }],
    [".corpus-card-p1", {}, go("corpus", "knowledge")],
    [".corpus-card-p1 .corpus-card-mark", { text: "知识点" }],
    [".corpus-card-p1 .corpus-card-type", { text: "Knowledge corpus" }],
    [".corpus-card-p1 strong", { text: "我的知识点语料库" }],
    [".corpus-card-p1 small", { text: "按技术方向整理答法，练习时可直接调出对应语料。" }],
    [".corpus-card-p1 .cca-topics text:nth-of-type(1)", { text: "C++" }],
    [".corpus-card-p1 .cca-topics text:nth-of-type(2)", { text: "低延迟" }],
    [".corpus-card-p1 .cca-topics text:nth-of-type(3)", { text: "并发" }],
    [".corpus-card-p1 .cca-tag", { text: "答法" }],
    [".corpus-card-p2", {}, go("corpus", "resume")],
    [".corpus-card-p2 .corpus-card-mark", { text: "简历" }],
    [".corpus-card-p2 .corpus-card-type", { text: "Resume cards" }],
    [".corpus-card-p2 strong", { text: "简历题卡 + 追问" }],
    [".corpus-card-p2 small", { text: "每个项目、每个技术栈一张题卡，并补好可复用的追问。" }],
    [".corpus-card-p2 .cca-tag", { text: "项目题卡" }],
    [".corpus-card-p2 .q1 text", { text: "为什么" }],
    [".corpus-card-p2 .q2 text", { text: "取舍" }],
    [".corpus-card-p2 .q3 text", { text: "量化" }],
    [".corpus-review-lane-head span", { text: "More" }],
    [".corpus-review-lane-head strong", { text: "岗位与复盘" }],
    [".corpus-review-link:nth-of-type(1)", {}, go("corpus", "jd")],
    [".corpus-review-link:nth-of-type(1) b", { text: "JD" }],
    [".corpus-review-link:nth-of-type(1) span", { text: "JD 与反问" }],
    [".corpus-review-link:nth-of-type(1) small", { text: "岗位题与反问环节" }],
    [".corpus-review-link:nth-of-type(2)", {}, go("custom")],
    [".corpus-review-link:nth-of-type(2) b", { text: "CV" }],
    [".corpus-review-link:nth-of-type(2) span", { text: "简历 / JD 定制" }],
    [".corpus-review-link:nth-of-type(2) small", { text: "生成题卡，改完再入库" }],
    [".corpus-review-link:nth-of-type(3)", {}, go("reports")],
    [".corpus-review-link:nth-of-type(3) b", { text: "RP" }],
    [".corpus-review-link:nth-of-type(3) span", { text: "面试报告" }],
    [".corpus-review-link:nth-of-type(3) small", { text: "百分制与参考回答" }],
  ];
  const ROOTS = [["homePanel", COPY], ["corpusPanel", HUB_COPY]];
  // Numbers the IELTS dashboard fills in; saved and restored like the copy.
  const NUMBERS = ['[data-hx-stat="speaking"]', '[data-hx-stat="writing"]', '[data-hx-stat="last"]',
    "[data-hx-due]", '[data-hx-bank="p1"]', '[data-hx-bank="p2"]', '[data-hx-bank="p3"]'];

  const saved = [];
  let active = false;
  let source = () => null;
  const panel = () => document.getElementById("homePanel");
  const firstText = (el) => [...el.childNodes].find((node) => node.nodeType === 3 && node.nodeValue.trim());

  function remember(el) {
    if (saved.some((item) => item.el === el)) return;
    const attrs = {};
    ["href", "data-view", "data-home-mode", "data-corpus-home-target", "data-iv-target"].forEach((name) => { attrs[name] = el.getAttribute(name); });
    const text = firstText(el);
    saved.push({ el, html: el.innerHTML, attrs, text, value: text?.nodeValue });
  }

  function setAttrs(el, attrs) {
    Object.entries(attrs).forEach(([name, value]) => (value === null ? el.removeAttribute(name) : el.setAttribute(name, value)));
  }

  function apply(mode) {
    const root = panel();
    if (!root) return;
    if (mode === "interview") {
      active = true;
      ROOTS.forEach(([id, table]) => {
        const scope = document.getElementById(id);
        if (!scope) return;
        table.forEach(([selector, change, attrs]) => {
          const el = scope.querySelector(selector);
          if (!el) return;
          remember(el);
          if (change.text !== undefined) el.textContent = change.text;
          else if (change.label !== undefined) { const node = firstText(el); if (node) node.nodeValue = change.label; }
          if (attrs) setAttrs(el, attrs);
        });
      });
      NUMBERS.forEach((selector) => root.querySelectorAll(selector).forEach((el) => { remember(el); el.textContent = ""; }));
      refresh();
      return;
    }
    if (!active) return;
    active = false;
    // Restore in reverse so a parent saved after its child gets its own markup back last.
    for (let i = saved.length - 1; i >= 0; i -= 1) {
      const item = saved[i];
      // A label swap kept the original text node (restore its value); a full text swap replaced the children
      // (put the original markup back).
      if (item.text && item.el.contains(item.text)) item.text.nodeValue = item.value;
      else if (item.el.innerHTML !== item.html) item.el.innerHTML = item.html;
      setAttrs(item.el, item.attrs);
    }
    saved.length = 0;
  }

  // Interview numbers: sessions, average 100-point score, last practice, corpus readiness.
  function refresh() {
    const root = panel();
    const numbers = active ? source() : null;
    if (!root || !numbers) return;
    const put = (selector, value) => { const el = root.querySelector(selector); if (el) el.textContent = value; };
    put('[data-hx-stat="speaking"]', numbers.sessions == null ? "–" : String(numbers.sessions));
    put('[data-hx-stat="writing"]', numbers.average == null ? "–" : String(numbers.average));
    const last = root.querySelector('[data-hx-stat="last"]');
    const date = numbers.last ? new Date(numbers.last) : null;
    if (last) {
      const pad = (n) => String(n).padStart(2, "0");
      last.innerHTML = date && !Number.isNaN(date.getTime())
        ? `<time datetime="${date.toISOString().slice(0, 10)}"><span class="hx-stat-year">${date.getFullYear()}</span>${pad(date.getMonth() + 1)}<span class="hx-stat-sep">·</span>${pad(date.getDate())}</time>`
        : "–";
    }
    const dues = root.querySelectorAll("[data-hx-due]");
    [numbers.projectReady, numbers.knowledgeReady, numbers.jdCount].forEach((value, index) => { if (dues[index]) dues[index].textContent = value ? String(value) : ""; });
    put('[data-hx-bank="p1"]', numbers.projects ? String(numbers.projects) : "");
    put('[data-hx-bank="p2"]', numbers.projects ? String(numbers.projects) : "");
    put('[data-hx-bank="p3"]', numbers.knowledge ? String(numbers.knowledge) : "");
  }

  window.IELTSInterviewHome = {
    apply,
    refresh,
    isActive: () => active,
    numbers: () => source(),
    setSource: (fn) => { source = typeof fn === "function" ? fn : () => null; },
  };
})();
