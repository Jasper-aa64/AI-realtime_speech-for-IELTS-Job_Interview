(function () {
  // What the candidate sets up before Start, in the practice panel's PROMPT pane (#ivLaunch):
  //   完整面试 — resume (split into the corpus) + this session's JD
  //   项目     — a project written for this session, or projects picked from the corpus
  //   知识点   — per category, corpus / bank questions or questions written for this session, plus a count
  //   反问     — this session's JD + the 2–3 questions the candidate plans to ask
  // Built from the IELTS P3 launch panel (p3-launch-section / p3-source-option) and the P1 corpus dialog with the
  // IELTS Markdown editor. launchOptions(view) turns the choices into the attempt-start payload.
  const COUNTS = [3, 5, 8, 10];
  const REVERSE_MAX = 3;
  const DIALOG_TEXT = "ivLaunchText";

  // Questions are read aloud by the examiner, so Markdown marks are dropped from a question written in the editor.
  function plainQuestion(markdown) {
    return String(markdown || "")
      .replace(/```[\s\S]*?```/g, " ")
      .split("\n")
      .map((line) => line.replace(/^\s*(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)/, "").trim())
      .filter(Boolean)
      .join(" ")
      .replace(/(\*\*|__|\*|_|~~|`)(.+?)\1/g, "$2")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .trim();
  }

  function create({ state, escapeHtml, markdown, upload, currentAiSourcePreference, source, onProfile, renderMarkdown, popup = (message) => window.alert(message) }) {
    const byId = (id) => document.getElementById(id);
    const esc = (value) => escapeHtml(String(value ?? ""));
    let launch = fresh();
    let dialog = null; // { kind, group? } while the Markdown dialog is open
    let pickGroup = null; // the knowledge category whose picker is open
    let bound = false;
    let loadedFor = null;

    // The setup survives a reload (per account, this browser only); it is a convenience, so storage may fail.
    const storeKey = () => `ielts-iv-launch:${state.account?.user?.id ?? "guest"}`;
    function save() {
      const { jd, projectSource, projectText, count, reverse, customs } = launch;
      try {
        localStorage.setItem(storeKey(), JSON.stringify({ jd, projectSource, projectText, count, reverse, customs,
          projectIds: [...launch.projectIds], picked: [...launch.picked] }));
      } catch (_error) { /* Session-only setup. */ }
    }
    function load() {
      if (loadedFor === storeKey()) return;
      loadedFor = storeKey();
      launch = fresh();
      try {
        const saved = JSON.parse(localStorage.getItem(storeKey()) || "null");
        if (!saved || typeof saved !== "object") return;
        if (typeof saved.jd === "string") launch.jd = saved.jd;
        if (["text", "corpus"].includes(saved.projectSource)) launch.projectSource = saved.projectSource;
        if (typeof saved.projectText === "string") launch.projectText = saved.projectText;
        if (COUNTS.includes(saved.count)) launch.count = saved.count;
        if (Array.isArray(saved.reverse)) launch.reverse = saved.reverse.filter((item) => typeof item === "string").slice(0, REVERSE_MAX);
        if (saved.customs && typeof saved.customs === "object") {
          Object.entries(saved.customs).forEach(([key, list]) => { if (Array.isArray(list)) launch.customs[key] = list.filter((item) => typeof item === "string"); });
        }
        if (Array.isArray(saved.projectIds)) launch.projectIds = new Set(saved.projectIds.filter((item) => typeof item === "string"));
        if (Array.isArray(saved.picked)) launch.picked = new Set(saved.picked.filter((item) => typeof item === "string"));
      } catch (_error) { /* Start from a clean setup. */ }
    }

    function fresh() {
      return { jd: null, projectSource: null, projectText: "", projectIds: new Set(), picked: new Set(), customs: {}, count: 5, reverse: [], busy: false, status: "" };
    }

    function reset() {
      loadedFor = null;
      launch = fresh();
      dialog = null;
      pickGroup = null;
      byId("ivLaunchDialog")?.classList.add("hidden");
      byId("ivPickDialog")?.classList.add("hidden");
    }

    const data = () => source() || {};
    const profile = () => data().profile || { resume: {}, jd: {} };
    const corpus = () => data().corpus || [];
    const jdText = () => (launch.jd ?? profile().jd?.text ?? "").trim();

    // ---- Knowledge categories: corpus groups (resume stack first), each holding its saved and curated questions.
    function groups() {
      const map = new Map();
      corpus().filter((entry) => entry.kind === "knowledge" && !entry.orphaned).forEach((entry) => {
        const key = entry.group || "自定义";
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(entry);
      });
      Object.keys(launch.customs).forEach((key) => { if (!map.has(key)) map.set(key, []); });
      const curated = (rows) => rows.every((entry) => entry.source === "curated" || String(entry.source_key || "").startsWith("curated:"));
      return [...map].map(([label, rows]) => ({ label, rows })).sort((a, b) => Number(curated(a.rows)) - Number(curated(b.rows)));
    }

    function pickKey(entry) {
      if (entry.id) return `e:${entry.id}`;
      return `q:${String(entry.source_key || "").replace(/^curated:/, "")}`;
    }

    function groupPicked(group) {
      return group.rows.filter((entry) => launch.picked.has(pickKey(entry))).length + (launch.customs[group.label] || []).length;
    }

    function categoryId(label) {
      return (data().categories || []).find((item) => item.label === label)?.id || "";
    }

    // ---- Rendering the launch block.
    // Tiles that open a dialog instead of being selected carry no check circle (iv-launch-action).
    const action = (attrs, title, note) => card(attrs, title, note, { cls: "iv-launch-action" });
    const card = (attrs, title, note, { active = false, cls = "" } = {}) =>
      `<button type="button" class="p3-source-option iv-launch-option ${cls}${active ? " active" : ""}" ${attrs}><strong>${esc(title)}</strong><small>${esc(note)}</small></button>`;
    const section = (label, body, extra = "") => `<section class="p3-launch-section iv-launch-section"${extra}><div class="p3-launch-label">${esc(label)}</div>${body}</section>`;
    const dateText = (value) => {
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
    };

    function resumeCard() {
      const resume = profile().resume || {};
      const projects = (resume.modules || []).filter((item) => item.kind === "project").length;
      return resume.updated_at
        ? card('data-iv-launch="resume"', "简历已上传", `${projects} 个项目 · ${dateText(resume.updated_at)} 更新，点击重新上传`, { active: true })
        : card('data-iv-launch="resume"', "上传简历", "PDF 或粘贴文字，拆成自我介绍、项目和技术栈");
    }

    function jdCard(optional) {
      const value = jdText();
      return value
        ? card('data-iv-launch="jd"', "本次 JD", `${value.length} 字 · ${plainQuestion(value.split("\n").find((line) => line.trim()) || "").slice(0, 26)}`, { active: true })
        : card('data-iv-launch="jd"', "粘贴 JD", optional ? "可选：用于岗位题、反问回答和岗位匹配评分" : "面试官按这个岗位回答你的问题");
    }

    function fullBlock() {
      return section("简历与岗位", `<div class="p3-source-grid iv-launch-grid">${resumeCard()}${jdCard(true)}</div>`);
    }

    function projectBlock() {
      const projects = corpus().filter((entry) => entry.kind === "project" && !entry.orphaned);
      // Without corpus projects a written description is the only way in, so it is the default.
      const fromText = (launch.projectSource || (projects.length ? "corpus" : "text")) === "text";
      const sources = `<div class="p3-source-grid iv-launch-grid">
          ${card('data-iv-launch="project-source" data-source="text"', "写一段项目描述", "本次只练这段描述里的项目", { active: fromText })}
          ${card('data-iv-launch="project-source" data-source="corpus"', "选择语料库项目", projects.length ? `${projects.length} 个项目可选，不选则全部` : "还没有项目，先上传简历", { active: !fromText })}
        </div>`;
      const detail = fromText
        ? (launch.projectText
          ? `<button type="button" class="iv-launch-preview" data-iv-launch="project-text"><span class="iv-launch-preview-body">${renderMarkdown(launch.projectText)}</span><em>编辑描述</em></button>`
          : `<div class="iv-launch-grid iv-launch-grid--one">${action('data-iv-launch="project-text"', "＋ 写项目描述", "背景、你的职责、技术难点和结果；支持 Markdown")}</div>`)
        : !projects.length
          ? `<div class="iv-launch-grid iv-launch-grid--one">${action('data-iv-launch="resume"', "＋ 上传简历", "拆出每个项目后，就能在这里挑本次要问的项目")}</div>`
          : `<div class="p3-source-grid iv-launch-grid">${projects.map((entry) => card(`data-iv-launch="project-pick" data-id="${esc(entry.id)}"`, entry.title || entry.question, launch.projectIds.has(entry.id) ? "本次会问" : "点击加入本次", { active: launch.projectIds.has(entry.id) })).join("")}</div>`;
      return section("项目来源", sources) + section(fromText ? "项目描述" : "本次项目", detail);
    }

    function knowledgeBlock() {
      const list = groups();
      const picked = list.reduce((sum, group) => sum + groupPicked(group), 0);
      const cards = list.map((group) => {
        const count = groupPicked(group);
        return card(`data-iv-launch="pick-group" data-group="${esc(group.label)}"`, group.label, count ? `已选 ${count} 题` : `${group.rows.length} 题可选 · 点击挑题或自己出题`, { active: count > 0 });
      }).join("");
      const counts = `<div class="p3-mode-switch iv-launch-count" role="group" aria-label="题数">${COUNTS.map((value) => `<button type="button" class="p3-mode-option${launch.count === value ? " active" : ""}" data-iv-launch="count" data-count="${value}">${value} 题</button>`).join("")}</div>
        <p class="p3-mode-help iv-launch-help">${esc(picked ? (picked > launch.count ? `已选 ${picked} 题，本次随机问其中 ${launch.count} 题。` : `已选 ${picked} 题${picked < launch.count ? "，不足的从所选分类的题库补齐" : ""}。`) : "不选题时，从简历技术栈、JD 和精选题库混合出题。")}</p>`;
      return section("知识点分类", `<div class="p3-source-grid iv-launch-grid iv-launch-grid--categories">${cards}</div>`) + section("题数", counts);
    }

    function reverseBlock() {
      const planned = launch.reverse.map((question, index) => `<div class="iv-launch-question"><span>${index + 1}</span><p>${esc(question)}</p><button type="button" data-iv-launch="reverse-remove" data-index="${index}" aria-label="删除这个问题">×</button></div>`).join("");
      const suggestions = corpus().filter((entry) => entry.kind === "reverse_question" && !launch.reverse.includes(entry.question)).slice(0, 4);
      const add = launch.reverse.length < REVERSE_MAX ? action('data-iv-launch="reverse-add"', "＋ 写一个反问", `准备 2～${REVERSE_MAX} 个，面试官逐个回答并点评`) : "";
      const chips = suggestions.length && launch.reverse.length < REVERSE_MAX
        ? `<div class="iv-launch-chips">${suggestions.map((entry) => `<button type="button" class="iv-launch-chip" data-iv-launch="reverse-suggest" data-question="${esc(entry.question)}">＋ ${esc(entry.question)}</button>`).join("")}</div>` : "";
      return section("岗位 JD", `<div class="iv-launch-grid iv-launch-grid--one">${jdCard(false)}</div>`)
        + section(`准备的反问 · ${launch.reverse.length}/${REVERSE_MAX}`, `<div class="iv-launch-questions">${planned}</div><div class="iv-launch-grid iv-launch-grid--one">${add}</div>${chips}`);
    }

    const BLOCKS = { iv_full: fullBlock, iv_project: projectBlock, iv_knowledge: knowledgeBlock, iv_reverse: reverseBlock };

    function render(view = state.view) {
      bind();
      load();
      const host = byId("ivLaunch");
      const pane = byId("promptPane");
      const block = BLOCKS[view];
      const show = Boolean(block) && state.account?.authenticated;
      host?.classList.toggle("hidden", !show);
      pane?.classList.toggle("has-iv-launch", show);
      if (!host || !show) return;
      save();
      host.innerHTML = `${block()}${launch.status ? `<p class="iv-launch-status" role="status">${esc(launch.status)}</p>` : ""}`;
    }

    function hide() {
      byId("ivLaunch")?.classList.add("hidden");
      byId("promptPane")?.classList.remove("has-iv-launch");
    }

    // ---- The Markdown dialog (the P1 corpus dialog shell with the IELTS editor).
    const DIALOGS = {
      resume: { meta: "简历", title: "上传简历", label: "简历文字", save: "保存并拆分", value: () => profile().resume?.text || "", file: true,
        note: "拆成自我介绍、每个项目、技术栈与奖项，存进语料库；重新拆分不会覆盖你改写过的答法。" },
      jd: { meta: "岗位 JD", title: "本次面试的 JD", label: "岗位描述", save: "用于本次", value: () => jdText(),
        note: "只用于这次面试：面试官据此回答反问、追问岗位相关内容，并评岗位匹配。" },
      "project-text": { meta: "项目描述", title: "写一段项目描述", label: "项目描述", save: "用于本次", value: () => launch.projectText,
        note: "第一行写项目名。面试官先请你介绍，再按描述里的细节追问。" },
      custom: { meta: "自定义题目", title: "新增题目", label: "题目", save: "加入本次", value: () => "", note: "只作为本次提问；面试官会把它读出来。" },
      reverse: { meta: "反问", title: "写一个反问", label: "你想问面试官的问题", save: "加入本次", value: () => "", note: "面试官会像真实面试一样回答，并点评这个问题问得好不好。" },
    };

    function openDialog(kind, extra = {}) {
      const spec = kind === "generic" ? extra.spec : DIALOGS[kind];
      const root = byId("ivLaunchDialog");
      if (!spec || !root) return;
      dialog = { kind, ...extra };
      byId("ivLaunchDialogMeta").textContent = extra.group ? `${spec.meta} · ${extra.group}` : spec.meta;
      byId("ivLaunchDialogTitle").textContent = spec.title;
      byId("ivLaunchDialogLabel").textContent = spec.label;
      byId("ivLaunchDialogSave").textContent = spec.save;
      byId("ivLaunchDialogNote").textContent = spec.note;
      byId("ivLaunchDialogStatus").textContent = "";
      byId("ivLaunchFile")?.closest(".iv-launch-file")?.classList.toggle("hidden", !spec.file);
      if (byId("ivLaunchFile")) byId("ivLaunchFile").value = "";
      if (byId("ivLaunchFileName")) byId("ivLaunchFileName").textContent = "选择 PDF 简历";
      byId("ivPickDialog")?.classList.add("hidden");
      markdown.set(DIALOG_TEXT, spec.value());
      root.classList.remove("hidden");
      markdown.ready(DIALOG_TEXT).then((editor) => setTimeout(() => editor?.focus?.() || byId(DIALOG_TEXT)?.focus(), 0));
    }

    function closeDialog() {
      if (launch.busy) return;
      const back = dialog?.kind === "custom" ? dialog.group : null;
      dialog = null;
      byId("ivLaunchDialog")?.classList.add("hidden");
      if (back) openPicker(back);
    }

    async function saveDialog() {
      if (!dialog || launch.busy) return;
      const value = markdown.get(DIALOG_TEXT).trim();
      const status = (text) => { byId("ivLaunchDialogStatus").textContent = text; };
      const { kind, group } = dialog;
      if (kind === "resume") {
        const file = byId("ivLaunchFile")?.files?.[0] || null;
        if (!value && !file) { status("请粘贴简历文字或选择 PDF。"); return; }
        const form = new FormData();
        form.append("resume_text", value);
        form.append("ai_source", currentAiSourcePreference());
        if (file) form.append("resume_file", file);
        launch.busy = true;
        status("正在拆分简历，通常需要几十秒…");
        try {
          onProfile(await upload("/api/interview/profile/resume/", form));
          launch.busy = false;
          launch.status = "简历已拆分，项目和技术栈都进了语料库。";
          closeDialog();
          render();
        } catch (error) {
          launch.busy = false;
          status(""); popup(error.message || "拆分失败，请重试。");
        }
        return;
      }
      if (kind === "generic") {
        if (dialog.onSave?.(value) === false) return;
        closeDialog();
        return;
      }
      if (kind === "jd") launch.jd = value;
      else if (kind === "project-text") launch.projectText = value;
      else {
        const question = plainQuestion(value);
        if (!question) { status("请先写题目。"); return; }
        if (kind === "custom") {
          const list = launch.customs[group] || (launch.customs[group] = []);
          if (!list.includes(question)) list.push(question);
        } else if (launch.reverse.length < REVERSE_MAX && !launch.reverse.includes(question)) {
          launch.reverse.push(question);
        }
      }
      closeDialog();
      render();
    }

    // ---- The knowledge picker: one category's questions plus the ones written for this session.
    function openPicker(label) {
      const root = byId("ivPickDialog");
      if (!root) return;
      pickGroup = label;
      renderPicker();
      root.classList.remove("hidden");
    }

    // Questions sit on topic cards (题卡), like the knowledge library: a grid to scan instead of one long column.
    function renderPicker() {
      const group = groups().find((item) => item.label === pickGroup) || { label: pickGroup, rows: [] };
      const customs = launch.customs[group.label] || [];
      const total = group.rows.length + customs.length;
      byId("ivPickDialogTitle").textContent = group.label;
      byId("ivPickDialogMeta").textContent = `知识点 · 已选 ${groupPicked(group)} / ${total}`;
      const row = (attrs, lead, textValue, selected, extra = "") =>
        `<button type="button" class="iv-pick-row${selected ? " is-selected" : ""}" ${attrs} aria-pressed="${selected}"><strong>${esc(lead)}</strong><span>${esc(textValue)}</span>${extra}<i aria-hidden="true"></i></button>`;
      const topics = new Map();
      group.rows.forEach((entry) => {
        const topic = entry.title || "综合";
        if (!topics.has(topic)) topics.set(topic, []);
        topics.get(topic).push(entry);
      });
      const card = (title, picked, count, body, toggle = "") => `
        <article class="iv-pick-topic${picked ? " has-picked" : ""}">
          <header><h4>${esc(title)}</h4><span class="iv-pick-count">${picked}/${count}</span>${toggle}</header>
          <div class="iv-pick-rows">${body}</div>
        </article>`;
      const cards = [...topics.entries()].sort((a, b) => a[0].localeCompare(b[0], "zh")).map(([topic, rows]) => {
        const picked = rows.filter((entry) => launch.picked.has(pickKey(entry))).length;
        const all = picked === rows.length;
        return card(topic, picked, rows.length,
          rows.map((entry, index) => row(`data-iv-pick="entry" data-key="${esc(pickKey(entry))}"`, `Q${index + 1}`, entry.question, launch.picked.has(pickKey(entry)),
            entry.corpus_text ? '<em class="iv-pick-tag">有语料</em>' : "")).join(""),
          `<button type="button" class="iv-pick-topic-all" data-iv-pick="topic" data-topic="${esc(topic)}">${all ? "清空" : "全选"}</button>`);
      });
      if (customs.length) {
        cards.unshift(card("本次自定", customs.length, customs.length,
          customs.map((question, index) => row(`data-iv-pick="custom" data-index="${index}"`, "自定", question, true, '<em class="iv-pick-tag">点击移除</em>')).join("")));
      }
      byId("ivPickList").innerHTML = cards.length ? `<div class="iv-pick-grid">${cards.join("")}</div>` : '<p class="iv-pick-empty">这个分类还没有题目，自己出一道吧。</p>';
      const allPicked = group.rows.length > 0 && group.rows.every((entry) => launch.picked.has(pickKey(entry)));
      byId("ivPickAll").textContent = allPicked ? "清空本类" : "全选本类";
      byId("ivPickAll").classList.toggle("hidden", !group.rows.length);
    }

    function closePicker() {
      pickGroup = null;
      byId("ivPickDialog")?.classList.add("hidden");
      render();
    }

    function onPick(event) {
      const target = event.target.closest("[data-iv-pick]");
      if (!target) return;
      const group = groups().find((item) => item.label === pickGroup);
      const action = target.dataset.ivPick;
      if (action === "entry") {
        const key = target.dataset.key;
        if (launch.picked.has(key)) launch.picked.delete(key); else launch.picked.add(key);
      } else if (action === "custom") {
        launch.customs[pickGroup]?.splice(Number(target.dataset.index), 1);
      } else if (action === "topic" && group) {
        const keys = group.rows.filter((entry) => (entry.title || "综合") === target.dataset.topic).map(pickKey);
        const all = keys.every((key) => launch.picked.has(key));
        keys.forEach((key) => (all ? launch.picked.delete(key) : launch.picked.add(key)));
      } else if (action === "all" && group) {
        const keys = group.rows.map(pickKey);
        const all = keys.every((key) => launch.picked.has(key));
        keys.forEach((key) => (all ? launch.picked.delete(key) : launch.picked.add(key)));
      } else if (action === "add") {
        openDialog("custom", { group: pickGroup });
        return;
      } else if (action === "done") {
        closePicker();
        return;
      }
      renderPicker();
    }

    // ---- Launch-block actions.
    function onLaunch(event) {
      const target = event.target.closest("[data-iv-launch]");
      if (!target || state.practiceLocked) return;
      const action = target.dataset.ivLaunch;
      launch.status = "";
      if (action === "resume" || action === "jd" || action === "project-text") { openDialog(action); return; }
      if (action === "reverse-add") { openDialog("reverse"); return; }
      if (action === "pick-group") { openPicker(target.dataset.group); return; }
      if (action === "project-source") launch.projectSource = target.dataset.source === "text" ? "text" : "corpus";
      else if (action === "project-pick") {
        const id = target.dataset.id;
        if (launch.projectIds.has(id)) launch.projectIds.delete(id); else launch.projectIds.add(id);
      } else if (action === "count") launch.count = Number(target.dataset.count) || 5;
      else if (action === "reverse-remove") launch.reverse.splice(Number(target.dataset.index), 1);
      else if (action === "reverse-suggest" && launch.reverse.length < REVERSE_MAX) launch.reverse.push(target.dataset.question);
      render();
    }

    function bind() {
      if (bound) return;
      bound = true;
      byId("ivLaunch")?.addEventListener("click", onLaunch);
      byId("ivPickDialog")?.addEventListener("click", onPick);
      byId("ivLaunchDialogSave")?.addEventListener("click", () => { saveDialog(); });
      byId("ivLaunchDialogClose")?.addEventListener("click", closeDialog);
      byId("ivLaunchFile")?.addEventListener("change", (event) => {
        byId("ivLaunchFileName").textContent = event.target.files?.[0]?.name || "选择 PDF 简历";
      });
      [["ivLaunchDialog", closeDialog], ["ivPickDialog", closePicker]].forEach(([id, close]) => {
        byId(id)?.addEventListener("pointerdown", (event) => { if (event.target === byId(id)) { event.preventDefault?.(); close(); } });
      });
      // Capture phase: IELTS keydown handlers stop Escape before it bubbles to the document.
      document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (dialog) { event.stopPropagation(); closeDialog(); }
        else if (pickGroup) { event.stopPropagation(); closePicker(); }
      }, true);
    }

    // ---- The attempt-start payload for each view.
    function options(view) {
      load();
      if (view === "iv_full") return jdText() ? { jd_text: jdText() } : {};
      if (view === "iv_project") {
        const hasProjects = corpus().some((entry) => entry.kind === "project" && !entry.orphaned);
        if ((launch.projectSource || (hasProjects ? "corpus" : "text")) === "text") return launch.projectText ? { project_text: launch.projectText } : {};
        return launch.projectIds.size ? { project_ids: [...launch.projectIds] } : {};
      }
      if (view === "iv_knowledge") {
        const entryIds = [];
        const questionIds = [];
        const categories = new Set();
        groups().forEach((group) => {
          group.rows.forEach((entry) => {
            const key = pickKey(entry);
            if (!launch.picked.has(key)) return;
            if (key.startsWith("e:")) entryIds.push(entry.id); else questionIds.push(key.slice(2));
            if (categoryId(group.label)) categories.add(categoryId(group.label));
          });
          if ((launch.customs[group.label] || []).length && categoryId(group.label)) categories.add(categoryId(group.label));
        });
        const customs = Object.values(launch.customs).flat();
        if (!entryIds.length && !questionIds.length && !customs.length) return { count: launch.count };
        return { count: launch.count, entry_ids: entryIds, question_ids: questionIds, custom_questions: customs, categories: [...categories] };
      }
      if (view === "iv_reverse") {
        return { ...(jdText() ? { jd_text: jdText() } : {}), ...(launch.reverse.length ? { reverse_questions: [...launch.reverse] } : {}) };
      }
      return {};
    }

    // A corpus card's 直接练习: start that card's practice with the card already chosen.
    function preset(view, { projectIds = [], entryIds = [], jdText = "", reverse = [] } = {}) {
      load();
      if (view === "iv_reverse") {
        if (jdText) launch.jd = jdText;
        if (reverse.length) launch.reverse = reverse.slice(0, REVERSE_MAX);
      }
      if (view === "iv_project" && projectIds.length) {
        launch.projectSource = "corpus";
        launch.projectIds = new Set(projectIds);
      }
      if (view === "iv_knowledge" && entryIds.length) {
        launch.picked = new Set(entryIds.map((id) => `e:${id}`));
        launch.customs = {};
        launch.count = COUNTS.find((value) => value >= entryIds.length) || COUNTS[COUNTS.length - 1];
      }
      save();
    }

    // The same Markdown dialog for other screens (the Resume / JD draft review): edits one text, hands it back.
    function editMarkdown({ meta = "", title = "", label = "", value = "", save = "保存修改", note = "", onSave }) {
      openDialog("generic", { spec: { meta, title, label, save, note, value: () => value }, onSave });
    }

    return { render, hide, options, reset, preset, editMarkdown };
  }

  window.IELTSInterviewLaunch = { create, plainQuestion };
})();
