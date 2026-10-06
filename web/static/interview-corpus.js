(function () {
  // The interview corpus screens, opened from the 面试语料库 hub (the IELTS 语料库 hub with interview copy):
  //   knowledge — the P1 corpus page: one card per direction, questions open the editor (>6 open the topic modal)
  //   resume    — the P2 题卡 grid with its filter: a card per project, per tech-stack direction, the self intro and each
  //               award; 正文 opens the editor, 追问 opens the P3 follow-up dialog (unlimited, custom follow-ups)
  //   jd        — the P1 corpus page again: role questions and questions to ask
  // The editor is the P1 corpus dialog (#ivCorpusDialog) with the IELTS Markdown editor; its "AI 参考" box only appears
  // when it is opened from a report, like the IELTS P1 report. The follow-up dialog is the P2 card's P3 dialog.
  const EDITOR_TEXT = "ivCorpusText";
  const CARD_TEXT = "ivCardText";
  const CARD_EXCERPT = "ivCardExcerpt";
  // The STAR body of a project / internship / award card.
  const STAR_TEMPLATE = "**S 情境**：\n\n**T 任务**：\n\n**A 行动**：\n\n**R 结果**：\n";
  const excerptLines = (value) => String(value || "").split(/\n+/).map((line) => line.replace(/^\s*(?:[-*•·]|\d+[.)、])\s*/, "").trim()).filter(Boolean);
  const FOLLOW_TEXT = "ivFollowText";
  const MODAL_AFTER = 6;
  const FILTERS = [
    { id: "all", label: "全部" },
    // Each type wears a P2 category's colours (object / place / event / special).
    { id: "project", label: "项目", color: "#0284c7", tone: "object" },
    { id: "intern", label: "实习", color: "#7c3aed", tone: "person" },
    { id: "stack", label: "技术栈", color: "#059669", tone: "place" },
    { id: "intro", label: "自我介绍", color: "#d97706", tone: "event" },
    { id: "award", label: "获奖", color: "#db2777", tone: "special" },
  ];
  const DOTS = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 6.5h.01"></path><path d="M12 12h.01"></path><path d="M12 17.5h.01"></path></svg>';
  // The P2 category grid on top of the resume screen: one card per kind, each with its rows and a "新增…" row.
  // `create` turns the name typed in the editor into the new entry's fields.
  const SECTIONS = [
    { id: "project", label: "项目", tone: "object", mark: "项",
      create: { placeholder: "一句话简述，如 低延迟撮合网关重构（P99 900µs→55µs）", fields: (name) => ({ kind: "project", title: name, question: `介绍一下你的「${name}」项目。` }) } },
    { id: "intern", label: "实习", tone: "person", mark: "实",
      create: { placeholder: "一句话简述，如 某券商交易系统组 · 行情接入", fields: (name) => ({ kind: "project", group: "实习", title: name, question: `介绍一下你在「${name}」的实习。` }) } },
    { id: "stack", label: "技术栈", tone: "place", mark: "技",
      create: { placeholder: "技术方向，如 C++ / 低延迟 / AI Native", askQuestion: true, fields: (name) => ({ kind: "knowledge", group: name }) } },
    { id: "award", label: "获奖", tone: "special", mark: "奖",
      create: { placeholder: "一句话简述，如 ACM-ICPC 区域赛银奖", fields: (name) => ({ kind: "award", title: name, question: `讲讲你的「${name}」经历。` }) } },
    { id: "intro", label: "自我介绍", tone: "event", mark: "我", single: true,
      create: { fields: () => ({ kind: "self_intro", title: "自我介绍", question: "请先做一个简单的自我介绍。" }) } },
  ];
  const CUES = {
    project: { kicker: "项目", bullets: ["项目背景与目标", "你负责的部分", "技术难点与取舍"], close: "最后讲清结果，最好有量化数据。" },
    intern: { kicker: "实习", bullets: ["公司与团队做什么", "你负责的事情", "遇到的难题与解决"], close: "最后讲清产出和收获。" },
    intro: { kicker: "自我介绍", bullets: ["你是谁、在读什么", "最能代表你的项目", "技术方向与优势"], close: "并说明为什么适合这个岗位。" },
    award: { kicker: "获奖", bullets: ["什么比赛 / 奖项", "你在团队里做了什么", "最难的一关"], close: "以及这段经历让你学到了什么。" },
  };

  function create({ state, escapeHtml, request, markdown, renderMarkdown, currentAiSourcePreference, source, setCorpus, rerender, startPractice, popup = (message) => window.alert(message) }) {
    const byId = (id) => document.getElementById(id);
    const esc = (value) => escapeHtml(String(value ?? ""));
    const entries = () => (source().corpus || []).filter((entry) => !entry.orphaned);
    let filter = "all";
    let tag = "all";
    let editor = null; // { entry, reference, isNew }
    let follow = null; // { card, selected, draft }
    let cardEdit = null; // { entry | null, section, initial }
    let busy = false;
    let bound = false;

    const plusIcon = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"></path></svg>';
    const keyOf = (entry) => entry.id || entry.source_key;
    const ready = (entry) => Boolean(String(entry.corpus_text || "").trim());

    function upsert(saved) {
      const list = [...(source().corpus || [])];
      const index = list.findIndex((item) => (item.id && item.id === saved.id) || (!item.id && item.source_key && item.source_key === saved.source_key));
      if (index >= 0) list.splice(index, 1, saved); else list.push(saved);
      setCorpus(list);
    }

    function remove(id) {
      setCorpus((source().corpus || []).filter((item) => item.id !== id && item.parent_id !== id));
    }

    // ---- Knowledge / JD screens: the P1 corpus page.
    // Knowledge: a tag is the direction (entry.group, e.g. 低延迟与性能); inside it every topic (entry.title, e.g.
    // SPSC 队列与背压) is one P1-style card. Resume directions come first, then the curated bank's.
    function knowledgeTags() {
      const curated = (entry) => entry.source === "curated" || String(entry.source_key || "").startsWith("curated:");
      const tags = new Map();
      entries().filter((entry) => entry.kind === "knowledge").forEach((entry) => {
        const name = entry.group || "自定义";
        if (!tags.has(name)) tags.set(name, { name, curated: true, rows: [] });
        const item = tags.get(name);
        item.rows.push(entry);
        if (!curated(entry)) item.curated = false;
      });
      return [...tags.values()].sort((a, b) => Number(a.curated) - Number(b.curated));
    }

    function knowledgeGroups() {
      const cards = [];
      knowledgeTags().forEach((item) => {
        const topics = new Map();
        item.rows.forEach((entry) => {
          const topic = entry.title || "综合";
          if (!topics.has(topic)) topics.set(topic, []);
          topics.get(topic).push(entry);
        });
        topics.forEach((rows, topic) => cards.push({ key: `k:${item.name}::${topic}`, title: topic, tag: item.name, rows,
          add: { kind: "knowledge", group: item.name, title: topic } }));
      });
      return cards;
    }

    function jdGroups() {
      const of = (kind) => entries().filter((entry) => entry.kind === kind);
      return [
        { key: "jd:role", title: "岗位题", rows: of("jd_question"), add: { kind: "jd_question" } },
        { key: "jd:ask", title: "反问环节", rows: of("reverse_question"), add: { kind: "reverse_question" } },
      ];
    }

    function topicCard(group) {
      const saved = group.rows.filter(ready).length;
      const progress = group.rows.length ? Math.round((saved / group.rows.length) * 100) : 0;
      const modal = group.rows.length > MODAL_AFTER;
      const rows = group.rows.map((entry, index) => `
        <button type="button" class="${ready(entry) ? "has-corpus" : ""}" ${modal ? 'tabindex="-1" aria-hidden="true"' : `data-ivc-edit="${esc(keyOf(entry))}"`}>
          <strong>Q${index + 1}</strong>
          <span>${esc(entry.question)}</span>
        </button>`).join("");
      return `
        <article class="p1-topic-card ${modal ? "is-modal-only" : "is-complete-list"}" data-p1-progress="${progress}" ${modal ? `data-ivc-topic="${esc(group.key)}"` : ""}>
          <header class="p1-topic-export-header">
            <div>${group.tag && tag === "all" ? `<span class="iv-topic-tag">${esc(group.tag)}</span>` : ""}<h3>${esc(group.title)}</h3></div>
            <div class="p1-topic-card-actions">
              <button type="button" class="p1-topic-copy-button" data-ivc-new="${esc(group.key)}" title="自己出一道题" aria-label="在「${esc(group.title)}」里自己出一道题">${plusIcon}</button>
              <span class="p1-topic-count">${saved}/${group.rows.length}</span>
            </div>
          </header>
          <div class="p1-topic-progress" aria-label="完成进度 ${progress}%" data-progress="${progress}"><span style="width: ${progress}%"></span></div>
          <div class="p1-topic-question-list">${rows || '<p class="iv-empty">还没有题目，点右上角 ＋ 自己出一道。</p>'}</div>
        </article>`;
    }

    function p1Page({ kicker, title, groups, empty = "", stat = "", filters = "", extra = "" }) {
      const all = groups.flatMap((group) => group.rows);
      return `<section id="interviewCorpus" class="p1-corpus-panel" aria-label="${esc(title)}">
          <div class="p1-corpus-shell">
            <header class="p1-corpus-head">
              <div class="p1-corpus-head-copy"><span class="corpus-page-kicker">${esc(kicker)}</span><h2>${esc(title)}</h2></div>
              <div class="corpus-head-actions"><span class="corpus-page-stat">${stat || `${groups.length} 个方向 · ${all.length} 道题`} · 已保存 ${all.filter(ready).length}</span></div>
            </header>
            ${filters}
            ${empty}
            <div class="p1-corpus-topics">${groups.map(topicCard).join("")}${extra}</div>
          </div>
        </section>`;
    }

    // ---- Resume screen: the P2 题卡 grid.
    function resumeCards() {
      const all = entries();
      const children = (entry) => all.filter((item) => item.parent_id === entry.id);
      const cards = [];
      all.filter((entry) => entry.kind === "self_intro").forEach((entry) => cards.push({ type: "intro", entry, title: "自我介绍", follows: children(entry) }));
      all.filter((entry) => entry.kind === "project").sort((a, b) => a.order - b.order)
        .forEach((entry) => cards.push({ type: entry.group === "实习" ? "intern" : "project", entry, title: entry.title || entry.question, follows: children(entry) }));
      // A tech-stack card is a direction from the resume or one the candidate added (any group that is not a bank
      // category); questions written on it later join the same group.
      const bankTags = new Set((source().categories || []).map((item) => item.label));
      const resumeGroups = new Set(all.filter((entry) => entry.kind === "knowledge" && entry.source !== "curated"
        && (entry.source === "resume" || !bankTags.has(entry.group || ""))).map((entry) => entry.group || "技术栈"));
      const stacks = new Map([...resumeGroups].map((group) => [group, []]));
      all.filter((entry) => entry.kind === "knowledge" && entry.source !== "curated" && resumeGroups.has(entry.group || "技术栈"))
        .forEach((entry) => stacks.get(entry.group || "技术栈").push(entry));
      stacks.forEach((rows, group) => cards.push({ type: "stack", group, title: group, follows: rows }));
      all.filter((entry) => entry.kind === "award").sort((a, b) => a.order - b.order)
        .forEach((entry) => cards.push({ type: "award", entry, title: entry.title || entry.question, follows: children(entry) }));
      return cards.map((card) => ({ ...card, key: card.entry ? card.entry.id : `stack:${card.group}` }));
    }

    function cueHtml(card) {
      if (card.type !== "stack") {
        // Resume cards show the resume's own lines for this experience; the STAR body is behind 正文.
        const lines = excerptLines(card.entry.resume_excerpt).slice(0, 4);
        return lines.length
          ? `<div class="p2-seasonal-cue iv-card-excerpt"><ul>${lines.map((line) => `<li>${esc(line)}</li>`).join("")}</ul></div>`
          : `<div class="p2-seasonal-cue iv-card-excerpt is-empty"><p>简历原文待填 · 点「正文」补上</p></div>`;
      }
      if (card.type === "stack") {
        const shown = card.follows.slice(0, 3);
        return `<div class="p2-seasonal-cue"><ul>${shown.map((entry) => `<li>${esc(entry.question)}</li>`).join("")}</ul>${card.follows.length > 3 ? `<p>还有 ${card.follows.length - 3} 道题。</p>` : ""}</div>`;
      }
      const cue = CUES[card.type];
      return `<div class="p2-seasonal-cue"><ul>${cue.bullets.map((item) => `<li>${esc(item)}</li>`).join("")}</ul><p>${esc(cue.close)}</p></div>`;
    }

    function resumeCard(card) {
      const filterId = card.type;
      const tone = FILTERS.find((item) => item.id === filterId)?.tone || "special";
      const total = card.follows.length;
      const saved = card.follows.filter(ready).length;
      const progress = total ? Math.round((saved / total) * 100) : 0;
      const hasBody = card.type !== "stack";
      const bodyReady = hasBody ? ready(card.entry) : saved === total && total > 0;
      const kicker = card.type === "stack" ? "技术栈" : CUES[card.type].kicker;
      return `
        <article class="p2-seasonal-card iv-resume-card${hasBody ? "" : " has-single-action"}" data-ivc-card="${esc(card.key)}" data-p2-bank-card-category="${tone}">
          <header>
            <div>
              <span class="p2-seasonal-card-kicker">${esc(kicker)} · ${esc((card.entry ? card.entry.source === "custom" : card.follows.every((entry) => entry.source === "custom")) ? "自定义" : "简历")}</span>
              <h3>${esc(card.title)}</h3>
            </div>
            <span class="p2-seasonal-card-state${bodyReady ? " is-ready" : ""}">${hasBody ? (bodyReady ? "STAR 已填" : "STAR 待填") : `答法 ${saved}/${total}`}</span>
          </header>
          <div class="p2-seasonal-body">
            ${cueHtml(card)}
            <button type="button" class="p2-seasonal-practice-btn" data-ivc-practice="${esc(card.key)}" title="直接用这张题卡开始面试练习">
              <svg class="p2-seasonal-practice-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/></svg>
              <span>直接<br>练习</span>
            </button>
          </div>
          <div class="p2-seasonal-p3-progress" data-progress="${progress}" aria-label="追问完成进度 ${saved}/${total}">
            <span class="p2-seasonal-p3-progress-label">${card.type === "stack" ? "题目" : "追问"}</span>
            <span class="p2-seasonal-p3-progress-track"><span style="width: ${progress}%"></span></span>
            <span class="p2-seasonal-p3-progress-count">${saved}/${total}</span>
          </div>
          <footer>
            ${hasBody ? `<button type="button" class="p2-seasonal-action primary" data-ivc-body="${esc(card.key)}">正文</button>` : ""}
            <button type="button" class="p2-seasonal-action${saved ? " is-ready" : ""}" data-ivc-follow="${esc(card.key)}">${card.type === "stack" ? "题目与答法" : "追问"}</button>
          </footer>
        </article>`;
    }

    function sectionRows(section, cards) {
      return cards.filter((card) => card.type === section.id).map((card, index) => {
        const followed = card.follows.filter(ready).length;
        const status = card.type === "stack" ? `${card.follows.length} 道题 · 已答 ${followed}`
          : [ready(card.entry) ? "STAR 已填" : "STAR 待填", card.follows.length ? `追问 ${followed}/${card.follows.length}` : ""].filter(Boolean).join(" · ");
        const items = card.entry
          ? `<button type="button" role="menuitem" data-ivc-body="${esc(card.key)}">修改</button>
             <button type="button" role="menuitem" class="danger" data-ivc-delete="${esc(card.key)}">删除</button>`
          : `<button type="button" role="menuitem" data-ivc-follow="${esc(card.key)}">题目与答法</button>
             <button type="button" role="menuitem" class="danger" data-ivc-delete="${esc(card.key)}">删除这个方向</button>`;
        const menu = `
          <button type="button" class="corpus-menu-button" data-ivc-menu="${esc(card.key)}" aria-haspopup="menu" aria-expanded="false" aria-label="打开操作菜单" title="更多操作">${DOTS}</button>
          <div class="corpus-card-action-menu hidden" data-ivc-action-menu role="menu" aria-label="题卡操作">${items}</div>`;
        return `
          <div class="p2-material-row">
            <button type="button" class="p2-material-entry-button has-corpus" ${card.entry ? `data-ivc-body="${esc(card.key)}"` : `data-ivc-follow="${esc(card.key)}"`}>
              <span class="p2-material-index">${index + 1}</span>
              <span class="p2-material-copy">
                <span class="p2-material-title">${esc(card.title)}</span>
                <span class="p2-material-status${followed ? " has-follow-up" : " is-empty"}">${esc(status)}</span>
              </span>
            </button>
            <div class="p2-material-actions">
              <button type="button" class="p2-follow-up-edit-button${followed ? " has-follow-up" : ""}" data-ivc-follow="${esc(card.key)}" aria-label="${card.type === "stack" ? "编辑题目与答法" : "编辑追问"}" title="${card.type === "stack" ? "题目与答法" : "追问"}">${card.type === "stack" ? "题" : "追"}</button>
              ${menu}
            </div>
          </div>`;
      }).join("");
    }

    function categoryGrid(cards) {
      const sections = SECTIONS.map((section) => {
        const count = cards.filter((card) => card.type === section.id).length;
        const add = section.single && count ? "" : `
          <button type="button" class="p2-add-material-button" data-ivc-create="${section.id}">
            <strong>+</strong><span>新增${esc(section.label)}</span>
          </button>`;
        return `
          <article class="p2-topic-card p2-category-entry-card iv-resume-section" data-category="${section.tone}" data-ivc-section="${section.id}" style="--p2-material-row-count: ${Math.max(count, 1)}">
            <header><h3>${esc(section.label)}</h3><span class="p2-topic-count">${count}</span></header>
            <div class="p2-topic-material-list">
              ${sectionRows(section, cards) || '<div class="p2-topic-empty">还没有内容，可以直接新增</div>'}
              ${add}
            </div>
          </article>`;
      }).join("");
      const generate = `
        <article class="p2-topic-card p2-category-entry-card iv-resume-generate" data-category="brainstorm">
          <header><h3>从简历生成</h3><span class="p2-topic-count">AI</span></header>
          <button type="button" class="p2-brainstorm-open-card" data-interview-action="go-custom">
            <span class="p2-brainstorm-card-copy">
              <strong>上传简历，一次生成全部题卡</strong>
              <span>自动拆成项目、实习、技术栈、获奖和自我介绍；先给你看草稿，改完再加入。</span>
            </span>
          </button>
        </article>`;
      return `<section class="p2-category-entry-grid" aria-label="简历分类入口">${sections}${generate}</section>`;
    }

    function resumePage() {
      const cards = resumeCards();
      const count = (id) => cards.filter((card) => card.type === id).length;
      const visible = filter === "all" ? cards : cards.filter((card) => card.type === filter);
      const filters = `<div class="p2-cat-filter-bar" role="group" aria-label="按类型筛选">
          ${FILTERS.map((item) => `<button type="button" class="p2-cat-filter-btn${filter === item.id ? " active" : ""}" data-ivc-filter="${item.id}"${item.color ? ` style="--filter-color:${item.color}"` : ""}>${esc(item.label)} <span>${item.id === "all" ? cards.length : count(item.id)}</span></button>`).join("")}
        </div>`;
      return `<section id="interviewResume" class="p2-corpus-panel" aria-label="简历题卡">
          <div class="p2-corpus-shell">
            <header class="p2-corpus-head">
              <div class="p2-corpus-head-copy"><span class="corpus-page-kicker">Resume Cards</span><h2>简历题卡</h2></div>
              <div class="corpus-head-actions"><span class="corpus-page-stat p2-corpus-stat">${cards.length} 张题卡 · 追问 ${cards.reduce((sum, card) => sum + card.follows.length, 0)}</span></div>
            </header>
            <div class="p2-corpus-topics">
              ${categoryGrid(cards)}
              <section class="p2-seasonal-card-section" aria-label="简历题卡">
                <header class="p2-seasonal-section-head">
                  <div><span class="corpus-page-kicker">FROM YOUR RESUME</span><h3>我的简历题卡</h3></div>
                  <span>${cards.length} 张题卡</span>
                </header>
                ${cards.length ? filters : ""}
                <div class="p2-seasonal-card-grid">${cards.length ? (visible.map(resumeCard).join("") || '<p class="muted">这个分类还没有题卡。</p>') : '<p class="muted">在上面新增，或从简历生成，题卡就会出现在这里。</p>'}</div>
              </section>
            </div>
          </div>
        </section>`;
    }

    function render(tab) {
      bind();
      if (!source().corpus) return '<p class="iv-empty">正在载入语料…</p>';
      if (tab === "resume") return resumePage();
      if (tab === "jd") {
        const groups = jdGroups();
        const empty = groups.every((group) => !group.rows.length)
          ? '<div class="iv-empty-card"><p>粘贴目标岗位的 JD，会生成岗位题和反问环节要问的问题；也可以直接点卡片右上角的 ＋ 自己写。</p><button type="button" class="iv-btn iv-btn--solid" data-interview-action="go-custom" data-side="jd">添加 JD →</button></div>' : "";
        return p1Page({ kicker: "JD & Questions", title: "JD 与反问", groups, empty, stat: `岗位题 ${groups[0].rows.length} · 反问 ${groups[1].rows.length}` });
      }
      const tags = knowledgeTags();
      if (tag !== "all" && !tags.some((item) => item.name === tag)) tag = "all";
      const cards = knowledgeGroups();
      const visible = tag === "all" ? cards : cards.filter((card) => card.tag === tag);
      const count = (name) => cards.filter((card) => card.tag === name).length;
      const filters = `<div class="p2-cat-filter-bar iv-tag-filter" role="group" aria-label="按方向筛选">
          <button type="button" class="p2-cat-filter-btn${tag === "all" ? " active" : ""}" data-ivc-tag="all">全部 <span>${cards.length}</span></button>
          ${tags.map((item) => `<button type="button" class="p2-cat-filter-btn${tag === item.name ? " active" : ""}" data-ivc-tag="${esc(item.name)}">${esc(item.name)} <span>${count(item.name)}</span></button>`).join("")}
        </div>`;
      const newCard = `<button type="button" class="p1-topic-card iv-new-topic-card" data-ivc-new-topic="${esc(tag === "all" ? (tags[0]?.name || "自定义") : tag)}">
          <span aria-hidden="true">＋</span><strong>新题卡</strong><small>${esc(tag === "all" ? "在一个方向下新建题卡" : `在「${tag}」下新建题卡`)}</small>
        </button>`;
      return p1Page({ kicker: "Knowledge Library", title: "知识点语料库", groups: visible, filters, extra: newCard,
        stat: `${tags.length} 个方向 · ${cards.length} 张题卡 · ${cards.reduce((sum, card) => sum + card.rows.length, 0)} 道题` });
    }

    function groupByKey(key) {
      return [...knowledgeGroups(), ...jdGroups()].find((group) => group.key === key) || null;
    }

    // ---- P1 topic modal for long cards (same markup as IELTS).
    function openTopicModal(key) {
      const group = groupByKey(key);
      if (!group) return;
      let modal = byId("ivTopicModal");
      if (!modal) {
        modal = document.createElement("div");
        modal.id = "ivTopicModal";
        document.body.appendChild(modal);
        modal.addEventListener("click", (event) => {
          const button = event.target.closest("[data-ivc-modal-edit]");
          if (event.target === modal || button) modal.classList.add("hidden");
          if (button) openEditorByKey(button.dataset.ivcModalEdit);
        });
      }
      modal.className = "p1-topic-modal-backdrop";
      modal.innerHTML = `
        <section class="p1-topic-modal" role="dialog" aria-modal="true" aria-label="${esc(group.title)}">
          <header><div><span>INTERVIEW</span><h3>${esc(group.title)}</h3></div><strong>${group.rows.filter(ready).length}/${group.rows.length}</strong></header>
          <div class="p1-topic-modal-list">${group.rows.map((entry, index) => `
            <button type="button" class="${ready(entry) ? "has-corpus" : ""}" data-ivc-modal-edit="${esc(keyOf(entry))}"><strong>Q${index + 1}</strong><span>${esc(entry.question)}</span></button>`).join("")}
          </div>
        </section>`;
      modal.classList.remove("hidden");
    }

    // ---- Editor: the P1 corpus dialog.
    function openEditorByKey(key) {
      const entry = (source().corpus || []).find((item) => keyOf(item) === key);
      if (entry) openEditor(entry);
    }

    function openEditor(entry, { reference = "", newTopic = false, create = null } = {}) {
      const root = byId("ivCorpusDialog");
      if (!root) return;
      const isNew = !entry.id && !entry.source_key;
      editor = { entry, reference, isNew, newTopic, create, initial: entry.corpus_text || "" };
      const topic = byId("ivCorpusTopic");
      const named = newTopic || Boolean(create?.placeholder);
      if (topic) {
        topic.classList.toggle("hidden", !named);
        topic.value = "";
        topic.placeholder = create?.placeholder || "题卡名，如 SPSC 队列";
      }
      // A new project / internship / award / intro gets its question from the name; a new direction asks for one.
      const editableQuestion = create ? Boolean(create.askQuestion) : isNew || ["custom", "practice"].includes(entry.source);
      const labels = { self_intro: "自我介绍", project: "项目", project_followup: "追问", knowledge: "知识点", award: "奖项", jd_question: "岗位题", reverse_question: "反问" };
      byId("ivCorpusDialogMeta").textContent = [labels[entry.kind] || "语料", entry.group, entry.kind === "knowledge" ? entry.title : ""].filter(Boolean).join(" · ") || "语料";
      byId("ivCorpusDialogTitle").textContent = entry.question || "新题目";
      byId("ivCorpusDialogTitle").classList.toggle("hidden", editableQuestion);
      const question = byId("ivCorpusQuestion");
      question.classList.toggle("hidden", !editableQuestion);
      question.value = entry.question || "";
      byId("ivCorpusDialogStatus").textContent = "";
      byId("ivCorpusDelete").classList.toggle("hidden", !entry.id || entry.source === "curated");
      const box = byId("ivCorpusAi")?.closest(".p1-corpus-ai-box");
      box?.classList.toggle("hidden", !reference);
      if (byId("ivCorpusAi")) {
        byId("ivCorpusAi").dataset.markdownSource = reference || "";
        byId("ivCorpusAi").innerHTML = reference ? renderMarkdown(reference) : "";
      }
      markdown.set(EDITOR_TEXT, entry.corpus_text || "");
      root.classList.remove("hidden");
      markdown.ready(EDITOR_TEXT).then((instance) => setTimeout(() => (editableQuestion && isNew ? question.focus() : instance?.focus?.() || byId(EDITOR_TEXT)?.focus()), 0));
    }

    // A new question with nothing typed closes on a click outside / Escape.
    function dismissEditor() {
      if (editor?.isNew && !markdown.get(EDITOR_TEXT).trim() && !byId("ivCorpusQuestion").value.trim() && !byId("ivCorpusTopic")?.value.trim()) {
        closeEditor();
        return;
      }
      saveEditor();
    }

    function closeEditor() {
      editor = null;
      byId("ivCorpusDialog")?.classList.add("hidden");
      rerender();
    }

    async function saveEditor({ close = true } = {}) {
      if (!editor || busy) return;
      const { entry, isNew } = editor;
      const text = markdown.get(EDITOR_TEXT);
      const status = (value) => { byId("ivCorpusDialogStatus").textContent = value; };
      if (editor.create) {
        const name = editor.create.placeholder ? byId("ivCorpusTopic").value.trim() : "";
        if (editor.create.placeholder && !name) { status("请先写名字。"); return; }
        const fields = editor.create.fields(name);
        const asked = byId("ivCorpusQuestion").value.trim();
        if (editor.create.askQuestion && !asked) { status("请先写第一道题。"); return; }
        busy = true;
        status("正在保存…");
        try {
          const payload = await request("/api/interview/corpus/", { ...fields, question: editor.create.askQuestion ? asked : fields.question, corpus_text: text });
          upsert(payload.entry);
          busy = false;
          if (close) closeEditor();
        } catch (error) {
          busy = false;
          status(""); popup(error.message || "保存失败，请重试。");
        }
        return;
      }
      const question = byId("ivCorpusQuestion").classList.contains("hidden") ? entry.question : byId("ivCorpusQuestion").value.trim();
      if (!question) { status("请先写题目。"); return; }
      const topicName = editor.newTopic ? byId("ivCorpusTopic").value.trim() : entry.title || "";
      if (editor.newTopic && !topicName) { status("请先给题卡起个名字。"); return; }
      const unchanged = text.trim() === String(editor.initial || "").trim() && question === entry.question && !isNew;
      if (unchanged) { if (close) closeEditor(); return; }
      busy = true;
      status("正在保存…");
      try {
        let payload;
        if (entry.id) {
          const body = { corpus_text: text };
          if (question !== entry.question) body.question = question;
          payload = await request(`/api/interview/corpus/${encodeURIComponent(entry.id)}/`, body, { method: "PATCH" });
        } else if (entry.source_key) {
          payload = await request("/api/interview/corpus/", { kind: "knowledge", source_key: entry.source_key, corpus_text: text });
        } else {
          payload = await request("/api/interview/corpus/", { kind: entry.kind, question, corpus_text: text, group: entry.group || "", title: topicName, ...(entry.parent_id ? { parent_id: entry.parent_id } : {}) });
        }
        upsert(payload.entry);
        busy = false;
        if (close) closeEditor();
        else { editor = { ...editor, entry: payload.entry, isNew: false, initial: text }; status("已保存"); }
      } catch (error) {
        busy = false;
        status(""); popup(error.message || "保存失败，请重试。");
      }
    }

    async function deleteEditorEntry() {
      const entry = editor?.entry;
      if (!entry?.id || busy) return;
      busy = true;
      try {
        await request(`/api/interview/corpus/${encodeURIComponent(entry.id)}/`, null, { method: "DELETE" });
        remove(entry.id);
        busy = false;
        closeEditor();
      } catch (error) {
        busy = false;
        popup(error.message || "删除失败，请重试。");
      }
    }

    // ---- Resume card dialog (the P2 素材 dialog): 名称 + 简述, 简历原文, STAR 正文.
    function openCard(entry, section = null) {
      const root = byId("ivCardDialog");
      if (!root) return;
      const type = section?.id || (entry.kind === "self_intro" ? "intro" : entry.kind === "award" ? "award" : entry.group === "实习" ? "intern" : "project");
      const meta = SECTIONS.find((item) => item.id === type);
      cardEdit = { entry, section: meta, initial: { text: entry?.corpus_text || "", excerpt: entry?.resume_excerpt || "", name: entry?.title || "" } };
      const intro = type === "intro";
      byId("ivCardDialogMeta").textContent = `简历题卡 · ${meta?.label || ""}`;
      byId("ivCardDialogTitle").textContent = entry ? (entry.title || entry.question) : `新增${meta?.label || "题卡"}`;
      byId("ivCardNameField").classList.toggle("hidden", intro);
      byId("ivCardName").value = entry?.title || "";
      byId("ivCardName").placeholder = meta?.create?.placeholder || "";
      markdown.set(CARD_EXCERPT, entry?.resume_excerpt || "");
      byId("ivCardTextLabel").textContent = intro ? "正文" : "STAR 正文";
      byId("ivCardStar").classList.toggle("hidden", intro);
      byId("ivCardDelete").classList.toggle("hidden", !entry?.id);
      byId("ivCardDialogStatus").textContent = "";
      markdown.set(CARD_TEXT, entry?.corpus_text || "");
      root.classList.remove("hidden");
      // 简历原文 and the STAR body are both IELTS Markdown editors.
      Promise.all([markdown.ready(CARD_EXCERPT), markdown.ready(CARD_TEXT)])
        .then(() => setTimeout(() => (intro ? null : byId("ivCardName"))?.focus(), 0));
    }

    function cardValues() {
      return { text: markdown.get(CARD_TEXT).trim(), excerpt: markdown.get(CARD_EXCERPT).trim(), name: byId("ivCardName").value.trim() };
    }

    // A new card with nothing typed closes on a click outside / Escape instead of asking for a name.
    function dismissCard() {
      const now = cardValues();
      if (!cardEdit?.entry && !now.text && !now.excerpt && !now.name) { closeCard(); return; }
      saveCard();
    }

    function cardDirty() {
      if (!cardEdit) return false;
      const now = cardValues();
      const was = cardEdit.initial;
      return !cardEdit.entry || now.text !== was.text.trim() || now.excerpt !== was.excerpt.trim() || now.name !== was.name;
    }

    function closeCard() {
      cardEdit = null;
      byId("ivCardDialog")?.classList.add("hidden");
      rerender();
    }

    async function saveCard({ close = true } = {}) {
      if (!cardEdit || busy) return;
      const { entry, section } = cardEdit;
      const status = (value) => { byId("ivCardDialogStatus").textContent = value; };
      if (entry && !cardDirty()) { if (close) closeCard(); return; }
      const name = byId("ivCardName").value.trim();
      const intro = section?.id === "intro";
      if (!intro && !name) { status("请先写一句简述。"); return; }
      const card = { resume_excerpt: markdown.get(CARD_EXCERPT).trim(), corpus_text: markdown.get(CARD_TEXT) };
      busy = true;
      status("正在保存…");
      try {
        let payload;
        if (entry?.id) {
          const body = { ...card };
          if (!intro && name !== entry.title) Object.assign(body, { title: name, question: section.create.fields(name).question });
          payload = await request(`/api/interview/corpus/${encodeURIComponent(entry.id)}/`, body, { method: "PATCH" });
        } else {
          payload = await request("/api/interview/corpus/", { ...section.create.fields(name), ...card });
        }
        upsert(payload.entry);
        busy = false;
        if (close) closeCard();
      } catch (error) {
        busy = false;
        status("");
        popup(error.message || "保存失败，请重试。");
      }
    }

    function insertStar() {
      const current = markdown.get(CARD_TEXT).trim();
      markdown.set(CARD_TEXT, current ? `${current}\n\n${STAR_TEMPLATE}` : STAR_TEMPLATE);
    }

    // ---- Follow-ups: the P2 card's P3 dialog. Tabs for every follow-up, plus one for writing a new one.
    function cardByKey(key) {
      return resumeCards().find((card) => card.key === key) || null;
    }

    function openFollow(key, selected = "") {
      const card = cardByKey(key);
      const root = byId("ivFollowDialog");
      if (!card || !root) return;
      follow = { key, selected: selected || card.follows[0]?.id || "new", initial: "" };
      byId("ivFollowDialogMeta").textContent = `简历题卡 · ${card.type === "stack" ? "技术栈" : CUES[card.type].kicker}`;
      byId("ivFollowDialogTitle").textContent = card.type === "stack" ? `题目与答法：${card.title}` : `编辑追问：${card.title}`;
      renderFollow();
      root.classList.remove("hidden");
      markdown.ready(FOLLOW_TEXT);
    }

    function renderFollow() {
      const card = cardByKey(follow.key);
      if (!card) return;
      const items = card.follows;
      const current = items.find((entry) => entry.id === follow.selected) || null;
      if (!current) follow.selected = "new";
      byId("ivFollowList").innerHTML = `<div class="p2-bank-p3-question-list" aria-label="追问列表">
          ${items.map((entry, index) => `
            <button type="button" class="p2-bank-p3-question-button${entry.id === follow.selected ? " is-active" : ""}${ready(entry) ? " is-ready" : ""}" data-ivc-follow-select="${esc(entry.id)}">
              <strong>Q${index + 1}</strong><span>${esc(entry.question)}</span><em>${ready(entry) ? "已填" : "待填"}</em>
            </button>`).join("")}
          <button type="button" class="p2-bank-p3-question-button iv-follow-new${follow.selected === "new" ? " is-active" : ""}" data-ivc-follow-select="new">
            <strong>＋</strong><span>${card.type === "stack" ? "自己出一道题" : "写一个新追问"}</span><em>自定义</em>
          </button>
        </div>`;
      const editable = !current || ["custom", "practice", "resume"].includes(current.source);
      const question = byId("ivFollowQuestion");
      question.value = current?.question || "";
      question.placeholder = card.type === "stack" ? "写下题目……" : "面试官可能怎么追问？";
      question.readOnly = !editable;
      byId("ivFollowDelete").classList.toggle("hidden", !current || current.source === "curated");
      byId("ivFollowDialogStatus").textContent = "";
      follow.initial = current?.corpus_text || "";
      follow.initialQuestion = current?.question || "";
      markdown.set(FOLLOW_TEXT, current?.corpus_text || "");
    }

    function followDirty() {
      if (!follow) return false;
      // The editor may hand back a trailing newline; compare the text, not the whitespace.
      return markdown.get(FOLLOW_TEXT).trim() !== String(follow.initial || "").trim() || byId("ivFollowQuestion").value.trim() !== follow.initialQuestion;
    }

    async function saveFollow() {
      if (!follow || busy) return false;
      const card = cardByKey(follow.key);
      const current = card?.follows.find((entry) => entry.id === follow.selected) || null;
      const text = markdown.get(FOLLOW_TEXT);
      const question = byId("ivFollowQuestion").value.trim();
      const status = (value) => { byId("ivFollowDialogStatus").textContent = value; };
      if (!followDirty()) return true;
      if (!question) { status("请先写追问。"); return false; }
      busy = true;
      status("正在保存…");
      try {
        let payload;
        if (current) {
          const body = { corpus_text: text };
          if (question !== current.question) body.question = question;
          payload = await request(`/api/interview/corpus/${encodeURIComponent(current.id)}/`, body, { method: "PATCH" });
        } else if (card.type === "stack") {
          payload = await request("/api/interview/corpus/", { kind: "knowledge", group: card.group, question, corpus_text: text });
        } else {
          payload = await request("/api/interview/corpus/", { kind: "project_followup", parent_id: card.entry.id, question, corpus_text: text });
        }
        upsert(payload.entry);
        follow.selected = payload.entry.id;
        busy = false;
        renderFollow();
        status("已保存");
        return true;
      } catch (error) {
        busy = false;
        status(""); popup(error.message || "保存失败，请重试。");
        return false;
      }
    }

    async function deleteFollow() {
      const card = cardByKey(follow?.key);
      const current = card?.follows.find((entry) => entry.id === follow.selected);
      if (!current || busy) return;
      busy = true;
      try {
        await request(`/api/interview/corpus/${encodeURIComponent(current.id)}/`, null, { method: "DELETE" });
        remove(current.id);
        busy = false;
        follow.selected = "";
        renderFollow();
      } catch (error) {
        busy = false;
        popup(error.message || "删除失败，请重试。");
      }
    }

    async function closeFollow() {
      const blankNew = follow?.selected === "new" && !markdown.get(FOLLOW_TEXT).trim() && !byId("ivFollowQuestion").value.trim();
      if (!blankNew && followDirty() && !(await saveFollow())) return;
      follow = null;
      byId("ivFollowDialog")?.classList.add("hidden");
      rerender();
    }

    // Deleting a card (and its follow-ups) asks first, in the IELTS confirm pop-up.
    function confirmDelete(card) {
      const ids = card?.entry?.id ? [card.entry.id] : (card?.follows || []).map((entry) => entry.id).filter(Boolean);
      if (!ids.length) return;
      const overlay = document.createElement("div");
      overlay.className = "confirm-overlay";
      overlay.innerHTML = `<div class="confirm-dialog"><p>${esc(card.entry ? `删除「${card.title}」和它的追问？` : `删除「${card.title}」方向下的 ${ids.length} 道题？`)}</p>
        <div class="confirm-actions"><button class="confirm-cancel" type="button">取消</button><button class="confirm-delete" type="button">删除</button></div></div>`;
      overlay.addEventListener("click", async (event) => {
        if (event.target.closest(".confirm-cancel") || event.target === overlay) { overlay.remove(); return; }
        if (!event.target.closest(".confirm-delete")) return;
        overlay.remove();
        try {
          for (const id of ids) {
            await request(`/api/interview/corpus/${encodeURIComponent(id)}/`, null, { method: "DELETE" });
            remove(id);
          }
          rerender();
        } catch (error) { popup(error.message || "删除失败，请重试。"); }
      });
      document.body.appendChild(overlay);
    }

    // ---- Report: 编辑语料 on an interview turn opens the editor with the reference answer.
    function openFromReport(target) {
      const all = source().corpus || [];
      let entry = (target.entryId && all.find((item) => item.id === target.entryId))
        || (target.questionId && all.find((item) => item.source_key === `curated:${target.questionId}`))
        || all.find((item) => item.question === target.question);
      if (!entry) {
        const parent = target.parentEntryId && all.find((item) => item.id === target.parentEntryId);
        const kind = parent && ["project", "self_intro", "award"].includes(parent.kind) ? "project_followup"
          : target.stage === "reverse" ? "reverse_question" : "knowledge";
        entry = { id: null, kind, source: "custom", question: target.question, corpus_text: "", parent_id: kind === "project_followup" ? parent.id : null,
                  group: kind === "knowledge" ? (parent?.group || "面试追问") : "" };
        editor = null;
        openEditor(entry, { reference: target.aiAnswer || "" });
        // Editing a question taken from a report: it is the report's question, so it is not retyped.
        byId("ivCorpusQuestion").value = target.question;
        return;
      }
      openEditor(entry, { reference: target.aiAnswer || "" });
    }

    function savedForTarget(target) {
      const all = source().corpus || [];
      if (!all.length) return null;
      const entry = (target.entryId && all.find((item) => item.id === target.entryId))
        || (target.questionId && all.find((item) => item.source_key === `curated:${target.questionId}`))
        || all.find((item) => item.question === target.question);
      return entry ? ready(entry) : false;
    }

    // ---- Events.
    function onPanelClick(event) {
      const menuButton = event.target.closest?.("[data-ivc-menu]");
      document.querySelectorAll?.("[data-ivc-action-menu]").forEach((menu) => {
        if (menuButton && menu.previousElementSibling === menuButton) return;
        menu.classList.add("hidden");
        menu.closest(".p2-material-row")?.classList.remove("is-menu-open");
        menu.closest(".p2-category-entry-card")?.classList.remove("is-menu-open");
      });
      if (menuButton) {
        const menu = menuButton.nextElementSibling;
        const open = menu?.classList.contains("hidden");
        menu?.classList.toggle("hidden", !open);
        menuButton.setAttribute("aria-expanded", String(Boolean(open)));
        menuButton.closest(".p2-material-row")?.classList.toggle("is-menu-open", Boolean(open));
        menuButton.closest(".p2-category-entry-card")?.classList.toggle("is-menu-open", Boolean(open));
        return;
      }
      const target = event.target.closest?.("[data-ivc-edit],[data-ivc-topic],[data-ivc-new],[data-ivc-new-topic],[data-ivc-tag],[data-ivc-filter],[data-ivc-body],[data-ivc-follow],[data-ivc-practice],[data-ivc-create],[data-ivc-delete]");
      if (!target) return;
      const data = target.dataset;
      if (data.ivcNew) {
        event.stopPropagation();
        const group = groupByKey(data.ivcNew);
        if (group) openEditor({ id: null, source: "custom", question: "", corpus_text: "", ...group.add });
      } else if (data.ivcEdit) openEditorByKey(data.ivcEdit);
      else if (data.ivcTopic) openTopicModal(data.ivcTopic);
      else if (data.ivcFilter) { filter = data.ivcFilter; rerender(); }
      else if (data.ivcCreate) {
        const section = SECTIONS.find((item) => item.id === data.ivcCreate);
        if (!section) return;
        if (section.id !== "stack") { openCard(null, section); return; }
        const fields = section.create.fields("");
        openEditor({ id: null, source: "custom", kind: fields.kind, group: fields.group || "", title: "", question: section.single ? fields.question : `新${section.label}`, corpus_text: "" },
          { create: section.create });
      } else if (data.ivcDelete) confirmDelete(cardByKey(data.ivcDelete));
      else if (data.ivcTag) { tag = data.ivcTag; rerender(); }
      else if (data.ivcNewTopic !== undefined) openEditor({ id: null, kind: "knowledge", source: "custom", question: "", corpus_text: "", group: data.ivcNewTopic, title: "" }, { newTopic: true });
      else if (data.ivcBody) { const card = cardByKey(data.ivcBody); if (card?.entry) openCard(card.entry); }
      else if (data.ivcFollow) openFollow(data.ivcFollow);
      else if (data.ivcPractice) {
        const card = cardByKey(data.ivcPractice);
        if (!card) return;
        if (card.type === "stack") startPractice("knowledge", { entryIds: card.follows.map((entry) => entry.id) });
        else if (card.type === "project" || card.type === "intern") startPractice("project", { projectIds: [card.entry.id] });
        else startPractice("full", {});
      }
    }

    function bind() {
      if (bound) return;
      bound = true;
      byId("interviewPanel")?.addEventListener("click", onPanelClick);
      byId("ivCorpusSave")?.addEventListener("click", () => saveEditor());
      byId("ivCorpusDelete")?.addEventListener("click", deleteEditorEntry);
      byId("ivCorpusCopyAi")?.addEventListener("click", () => {
        const value = byId("ivCorpusAi")?.dataset.markdownSource || "";
        if (value) navigator.clipboard?.writeText?.(value).catch(() => {});
      });
      byId("ivCorpusAdoptAi")?.addEventListener("click", () => {
        const value = byId("ivCorpusAi")?.dataset.markdownSource || "";
        if (value) markdown.set(EDITOR_TEXT, value);
      });
      byId("ivCardSave")?.addEventListener("click", () => saveCard());
      byId("ivCardStar")?.addEventListener("click", insertStar);
      byId("ivCardDelete")?.addEventListener("click", () => {
        const entry = cardEdit?.entry;
        if (!entry?.id) return;
        const card = cardByKey(entry.id);
        closeCard();
        confirmDelete(card || { entry, title: entry.title || entry.question });
      });
      byId("ivFollowSave")?.addEventListener("click", () => saveFollow());
      byId("ivFollowDelete")?.addEventListener("click", deleteFollow);
      byId("ivFollowList")?.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-ivc-follow-select]");
        if (!button || !follow) return;
        if (followDirty() && !(await saveFollow())) return;
        follow.selected = button.dataset.ivcFollowSelect;
        renderFollow();
        if (follow.selected === "new") byId("ivFollowQuestion")?.focus();
      });
      [["ivCorpusDialog", dismissEditor], ["ivFollowDialog", closeFollow], ["ivCardDialog", dismissCard]].forEach(([id, close]) => {
        byId(id)?.addEventListener("pointerdown", (event) => { if (event.target === byId(id)) { event.preventDefault?.(); close(); } });
      });
      // Capture phase: IELTS keydown handlers stop Escape before it bubbles to the document.
      document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (editor) { event.stopPropagation(); dismissEditor(); }
        else if (cardEdit) { event.stopPropagation(); dismissCard(); }
        else if (follow) { event.stopPropagation(); closeFollow(); }
        else byId("ivTopicModal")?.classList.add("hidden");
      }, true);
    }

    function reset() {
      filter = "all";
      tag = "all";
      editor = null;
      follow = null;
      byId("ivCorpusDialog")?.classList.add("hidden");
      byId("ivFollowDialog")?.classList.add("hidden");
      byId("ivTopicModal")?.classList.add("hidden");
      cardEdit = null;
      byId("ivCardDialog")?.classList.add("hidden");
    }

    return { render, openEditor, openCard, openFromReport, savedForTarget, reset, isEditing: () => Boolean(editor || follow || cardEdit) };
  }

  window.IELTSInterviewCorpus = { create };
})();
