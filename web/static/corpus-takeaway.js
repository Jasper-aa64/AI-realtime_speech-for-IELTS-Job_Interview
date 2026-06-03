(function () {
  "use strict";

  function createCorpusTakeawayController(options) {
    const {
      state,
      $,
      text,
      escapeHtml,
      renderMarkdown,
      renderSpokenAnswerMarkdown,
      fetchP1CorpusPayload,
      applyP1CorpusPayload,
      fetchP2CorpusPayload,
      applyP2CorpusPayload,
      fetchLanguageTakeawaysPayload,
      applyLanguageTakeawaysPayload,
      fetchWritingTakeawaysPayload,
      applyWritingTakeawaysPayload,
      p1CorpusTargetForTurn,
      api,
      showConfirmDelete,
      switchView,
      openCorpusWindow,
      renderP2CorpusPrepPanel,
      ensureCorpusMarkdownEditorReady,
      getCorpusMarkdownValue,
      isCorpusEditorReady,
      setCorpusEditorLoading,
      setCorpusMarkdownValue,
      getCsrfToken,
      viewCopy,
      corpusPeekWindowMargin,
    } = options || {};

    if (!state || typeof $ !== "function" || typeof api !== "function") {
      throw new Error("Corpus/Takeaway controller requires shared app state and helpers.");
    }

    const CORPUS_PEEK_WINDOW_MARGIN = Number(corpusPeekWindowMargin) || 16;
    const DOTS_ICON = `
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M12 6.5h.01"></path>
        <path d="M12 12h.01"></path>
        <path d="M12 17.5h.01"></path>
      </svg>
    `;

    function corpusCardActionMenuHtml({ menuAttr, editAttr, deleteAttr, entryId }) {
      const id = escapeHtml(entryId);
      return `
        <button type="button" class="corpus-menu-button" ${menuAttr}="${id}" data-corpus-card-menu aria-haspopup="menu" aria-expanded="false" aria-label="打开操作菜单" title="更多操作">
          ${DOTS_ICON}
        </button>
        <div class="corpus-card-action-menu hidden" data-corpus-card-action-menu role="menu" aria-label="项目操作">
          <button type="button" role="menuitem" ${editAttr}="${id}">修改</button>
          <button type="button" role="menuitem" class="danger" ${deleteAttr}="${id}">删除</button>
        </div>
      `;
    }

    function closeCorpusCardActionMenus(exceptMenu = null) {
      document.querySelectorAll("[data-corpus-card-action-menu]").forEach((menu) => {
        if (menu === exceptMenu) return;
        menu.classList.add("hidden");
        const button = menu.parentElement?.querySelector("[data-corpus-card-menu]");
        button?.setAttribute("aria-expanded", "false");
      });
    }

    function toggleCorpusCardActionMenu(button) {
      if (!button) return;
      const menu = button.parentElement?.querySelector("[data-corpus-card-action-menu]");
      if (!menu) return;
      const willOpen = menu.classList.contains("hidden");
      closeCorpusCardActionMenus(menu);
      menu.classList.toggle("hidden", !willOpen);
      button.setAttribute("aria-expanded", willOpen ? "true" : "false");
    }

    async function loadP1Corpus() {
      const stats = $("p1CorpusStats");
      const container = $("p1CorpusTopics");
      if (state.p1Corpus.loaded) {
        renderP1CorpusTopics();
        if (stats) stats.textContent = `${state.p1Corpus.topics.length} 个话题 · 刷新中`;
      } else {
        if (stats) stats.textContent = "Loading...";
        if (container) container.innerHTML = '<p class="muted">正在加载 P1 题库...</p>';
      }
      try {
        const payload = await fetchP1CorpusPayload();
        applyP1CorpusPayload(payload);
      } catch (error) {
        if (container) container.innerHTML = `<p class="error">${escapeHtml(error.message || String(error))}</p>`;
        if (stats) stats.textContent = "加载失败";
      }
    }

    function renderP1CorpusTopics() {
      const container = $("p1CorpusTopics");
      if (!container) return;
      const topics = state.p1Corpus.topics || [];
      if (!topics.length) {
        container.innerHTML = '<p class="muted">还没有 P1 题目。</p>';
        return;
      }
      container.innerHTML = topics.map((topic) => {
        const questions = topic.questions || [];
        const saved = questions.filter((item) => item.corpus_text).length;
        const progress = questions.length ? Math.round((saved / questions.length) * 100) : 0;
        return `
          <article class="p1-topic-card">
            <header>
              <div>
                <h3>${escapeHtml(topic.label || topic.topic)}</h3>
                <small>${saved ? `已保存 ${saved}` : "未开始"}</small>
              </div>
              <span class="p1-topic-count">${saved}/${questions.length}</span>
            </header>
            <div class="p1-topic-progress" aria-hidden="true"><span style="width: ${progress}%"></span></div>
            <div class="p1-topic-question-list">
              ${questions.map((item, index) => `
                <button type="button" class="${item.corpus_text ? "has-corpus" : ""}" data-p1-corpus-question="${escapeHtml(item.question_id)}">
                  <strong>Q${index + 1}</strong>
                  <span>${escapeHtml(item.question)}</span>
                </button>
              `).join("")}
            </div>
          </article>
        `;
      }).join("");
    }

    function findP1CorpusEntry(questionId) {
      const id = String(questionId || "").trim();
      if (!id) return null;
      for (const topic of state.p1Corpus.topics || []) {
        const found = (topic.questions || []).find((item) => (
          item.question_id === id
          || item.storage_question_id === id
          || item.legacy_question_id === id
        ));
        if (found) return found;
      }
      return null;
    }

    function p1CorpusEntryIds(entry) {
      return [
        entry?.question_id,
        entry?.storage_question_id,
        entry?.legacy_question_id,
      ].map((value) => String(value || "").trim()).filter(Boolean);
    }

    function normalizeP1CorpusQuestionText(value) {
      return String(value || "")
        .toLowerCase()
        .replace(/[\u2018\u2019\u201c\u201d"'`]/g, "")
        .replace(/[^a-z0-9]+/g, " ")
        .replace(/\s+/g, " ")
        .trim();
    }

    function findP1CorpusEntryByExactQuestion(question) {
      const normalizedQuestion = normalizeP1CorpusQuestionText(question);
      if (!normalizedQuestion) return null;
      for (const topicGroup of state.p1Corpus.topics || []) {
        for (const item of topicGroup.questions || []) {
          if (normalizeP1CorpusQuestionText(item.question) === normalizedQuestion) return item;
        }
      }
      return null;
    }

    function findExactP1CorpusEntryForTargetInTopics(target, topics) {
      const storage = p1CorpusStorageEntry(target);
      const targetIds = p1CorpusEntryIds({
        question_id: storage.question_id,
        storage_question_id: target?.storage_question_id,
        legacy_question_id: target?.legacy_question_id,
      });
      const targetQuestion = normalizeP1CorpusQuestionText(storage.question || target?.display_question);
      for (const topicGroup of topics || []) {
        for (const item of topicGroup.questions || []) {
          const itemQuestion = normalizeP1CorpusQuestionText(item.question);
          if (targetIds.some((id) => p1CorpusEntryIds(item).includes(id))) {
            if (!targetQuestion || !itemQuestion || itemQuestion === targetQuestion) return item;
          }
        }
      }
      if (targetIds.length || !targetQuestion) return null;
      for (const topicGroup of topics || []) {
        for (const item of topicGroup.questions || []) {
          if (normalizeP1CorpusQuestionText(item.question) === targetQuestion) return item;
        }
      }
      return null;
    }

    function findExactP1CorpusEntryForTarget(target) {
      return findExactP1CorpusEntryForTargetInTopics(target, state.p1Corpus.topics || []);
    }

    function currentP1CorpusTarget(turn = state.currentTurn) {
      if (!turn || turn.part !== "p1") return null;
      return p1CorpusTargetForTurn(turn, state.attempt || {});
    }

    async function ensureP1CorpusLoaded() {
      if (state.p1Corpus.loaded) return true;
      try {
        const payload = await fetchP1CorpusPayload();
        applyP1CorpusPayload(payload);
        return true;
      } catch (_error) {
        return false;
      }
    }

    function updateP1CorpusPeekButton(turn = state.currentTurn) {
      const button = $("peekP1CorpusBtn");
      if (!button) return;
      const target = currentP1CorpusTarget(turn);
      const entry = target?.questionId ? findP1CorpusEntry(target.questionId) : null;
      const hasCorpus = !!(entry?.corpus_text || "").trim();
      button.classList.toggle("hidden", !target);
      button.classList.toggle("has-corpus", hasCorpus);
      button.title = hasCorpus ? "查看这道题的语料提示" : "这道题还没有保存语料";
      if (target) {
        button.dataset.questionId = target.questionId || "";
        button.dataset.topic = target.topic || "";
        button.dataset.question = target.displayQuestion || target.question || "";
        if (!state.p1Corpus.loaded) {
          ensureP1CorpusLoaded().then(() => {
            if (state.currentTurn?.id === turn?.id) updateP1CorpusPeekButton(state.currentTurn);
          });
        }
      } else {
        button.removeAttribute("data-question-id");
        button.removeAttribute("data-topic");
        button.removeAttribute("data-question");
      }
    }

    async function openP1CorpusPeek() {
      const target = currentP1CorpusTarget();
      if (!target?.questionId) return;
      if (!state.p1Corpus.loaded) await ensureP1CorpusLoaded();
      const entry = findP1CorpusEntry(target.questionId);
      const corpusText = (entry?.corpus_text || "").trim();
      text("p1CorpusPeekTopic", (entry?.topic || target.topic || "PART 1").replaceAll("_", " ").toUpperCase());
      text("p1CorpusPeekTitle", target.displayQuestion || entry?.question || target.question || "语料提示");
      const body = $("p1CorpusPeekBody");
      if (body) {
        body.innerHTML = corpusText
          ? renderMarkdown(corpusText)
          : '<p class="muted">这道题还没有保存语料。</p>';
      }
      $("p1CorpusPeekDialog")?.classList.remove("hidden");
      updateP1CorpusPeekButton(state.currentTurn);
    }

    function closeP1CorpusPeek() {
      $("p1CorpusPeekDialog")?.classList.add("hidden");
    }

    function corpusPeekCard(dialogId) {
      return $(dialogId)?.querySelector(".p2-corpus-peek-card") || null;
    }

    function placeCorpusPeekWindow(dialogId, left, top) {
      const card = corpusPeekCard(dialogId);
      if (!card) return;
      const margin = CORPUS_PEEK_WINDOW_MARGIN;
      const rect = card.getBoundingClientRect();
      const width = Math.min(rect.width || 760, Math.max(1, window.innerWidth - margin * 2));
      const height = Math.min(rect.height || 620, Math.max(1, window.innerHeight - margin * 2));
      const maxLeft = Math.max(margin, window.innerWidth - width - margin);
      const maxTop = Math.max(margin, window.innerHeight - height - margin);
      card.style.left = `${Math.min(maxLeft, Math.max(margin, left))}px`;
      card.style.top = `${Math.min(maxTop, Math.max(margin, top))}px`;
      card.style.right = "auto";
      card.style.transform = "none";
    }

    function resetCorpusPeekWindowPosition(dialogId) {
      const card = corpusPeekCard(dialogId);
      if (!card) return;
      card.style.left = "";
      card.style.top = "";
      card.style.right = "";
      card.style.transform = "";
      window.requestAnimationFrame(() => {
        if ($(dialogId)?.classList.contains("hidden")) return;
        const rect = card.getBoundingClientRect();
        placeCorpusPeekWindow(dialogId, rect.left, rect.top);
      });
    }

    function keepOpenCorpusPeekWindowsInBounds() {
      ["p2CorpusPeekDialog", "p3CorpusPeekDialog"].forEach((dialogId) => {
        const dialog = $(dialogId);
        const card = corpusPeekCard(dialogId);
        if (!dialog || !card || dialog.classList.contains("hidden")) return;
        const rect = card.getBoundingClientRect();
        placeCorpusPeekWindow(dialogId, rect.left, rect.top);
      });
    }

    function currentP2CorpusEntry() {
      const selectedId = state.p2Corpus.selectedEntryId || "";
      return selectedId ? findP2CorpusEntry(selectedId) : null;
    }

    async function ensureP2CorpusLoaded() {
      if (state.p2Corpus.loaded) return true;
      try {
        const payload = await fetchP2CorpusPayload();
        applyP2CorpusPayload(payload);
        return true;
      } catch (_error) {
        return false;
      }
    }

    function updateP2CorpusPeekButton(turn = state.currentTurn) {
      const button = $("peekP2CorpusBtn");
      if (!button) return;
      const visible = state.view === "p2" && turn?.part === "p2" && Boolean(state.p2Corpus.selectedEntryId);
      const entry = visible ? currentP2CorpusEntry() : null;
      button.classList.toggle("hidden", !visible);
      button.classList.toggle("has-corpus", Boolean(entry));
      button.title = entry ? "查看已链接素材" : "已选择素材，正在加载内容";
      if (visible && !entry && !state.p2Corpus.loaded) {
        ensureP2CorpusLoaded().then(() => updateP2CorpusPeekButton(state.currentTurn));
      }
    }

    function p2CorpusPeekHtml(entry) {
      if (!entry) return '<p class="muted">没有找到已链接的素材。</p>';
      const materialText = String(entry.material_text || "").trim();
      if (!materialText) return '<p class="muted">这条素材还没有内容。</p>';
      return `
        <section class="p2-corpus-peek-section">
          <h4>串题素材</h4>
          <div>${renderMarkdown(materialText)}</div>
        </section>
      `;
    }

    async function openP2CorpusPeek() {
      if (!state.p2Corpus.selectedEntryId) return;
      if (!state.p2Corpus.loaded) await ensureP2CorpusLoaded();
      const entry = currentP2CorpusEntry();
      text("p2CorpusPeekMeta", entry?.label || "P2 LINKED MATERIAL");
      text("p2CorpusPeekTitle", entry?.title || "已链接素材");
      const body = $("p2CorpusPeekBody");
      if (body) body.innerHTML = p2CorpusPeekHtml(entry);
      $("p2CorpusPeekDialog")?.classList.remove("hidden");
      resetCorpusPeekWindowPosition("p2CorpusPeekDialog");
    }

    function closeP2CorpusPeek() {
      $("p2CorpusPeekDialog")?.classList.add("hidden");
    }

    function updateP3CorpusPeekButton(turn = state.currentTurn) {
      const button = $("peekP3CorpusBtn");
      if (!button) return;
      const hasFollowUps = Boolean(String(state.p3PracticeSource?.p3FollowUpText || "").trim());
      const visible = state.view === "p3" && turn?.part === "p3" && hasFollowUps;
      button.classList.toggle("hidden", !visible);
      button.classList.toggle("has-corpus", visible);
      button.title = visible ? "查看这次 P3 参考的追问素材" : "没有关联的 P3 追问素材";
    }

    function openP3CorpusPeek() {
      const source = state.p3PracticeSource || {};
      const followUps = String(source.p3FollowUpText || "").trim();
      if (!followUps) return;
      text("p3CorpusPeekMeta", source.title || "P3 FOLLOW-UP MATERIAL");
      text("p3CorpusPeekTitle", "相关 P3 追问");
      const body = $("p3CorpusPeekBody");
      if (body) body.innerHTML = `
        <section class="p2-corpus-peek-section">
          <h4>相关 P3 追问</h4>
          <div>${renderMarkdown(followUps)}</div>
        </section>
      `;
      $("p3CorpusPeekDialog")?.classList.remove("hidden");
      resetCorpusPeekWindowPosition("p3CorpusPeekDialog");
    }

    function closeP3CorpusPeek() {
      $("p3CorpusPeekDialog")?.classList.add("hidden");
    }

    function p1CorpusStorageEntry(entry) {
      const prompt = entry?.prompt || {};
      return {
        question_id: entry?.storage_question_id || entry?.question_id || "",
        topic: entry?.storage_topic || entry?.topic || prompt.topic || "general",
        question: entry?.storage_question || entry?.question || entry?.display_question || prompt.question || "",
      };
    }

    function upsertP1CorpusEntry(saved) {
      if (!saved?.question_id) return null;
      const existing = findP1CorpusEntry(saved.question_id);
      if (existing) {
        existing.corpus_text = saved.corpus_text || "";
        existing.last_ai_answer = saved.last_ai_answer || "";
        existing.updated_at = saved.updated_at || "";
        existing.question = saved.question || existing.question || "";
        existing.topic = saved.topic || existing.topic || "general";
        return existing;
      }
      return saved;
    }

    function sendKeepaliveJson(path, payload) {
      try {
        const headers = { "Content-Type": "application/json" };
        const csrfToken = getCsrfToken();
        if (csrfToken) headers["X-CSRFToken"] = csrfToken;
        navigator.sendBeacon?.(
          path,
          new Blob([JSON.stringify(payload)], { type: "application/json" }),
        ) || fetch(path, {
          method: "POST",
          credentials: "same-origin",
          headers,
          body: JSON.stringify(payload),
          keepalive: true,
        }).catch(() => null);
      } catch (_error) {
        // Best-effort autosave during unload.
      }
    }

    function autosaveOpenCorpusEditors() {
      const p1Entry = state.p1Corpus.activeEntry;
      if (p1Entry && !$("#p1CorpusDialog")?.classList.contains("hidden")) {
        if (!isCorpusEditorReady("p1CorpusText")) return;
        const corpusText = getCorpusMarkdownValue("p1CorpusText").trim();
        if (!corpusText) return;
        const storage = p1CorpusStorageEntry(p1Entry);
        sendKeepaliveJson("/api/p1-corpus", {
          question_id: storage.question_id,
          topic: storage.topic,
          question: storage.question,
          corpus_text: corpusText,
          last_ai_answer: p1Entry.last_ai_answer || p1Entry.band7_version || p1Entry.aiAnswer || "",
          source: "report_or_library",
        });
      }
      const p2Entry = state.p2Corpus.activeEntry;
      if (p2Entry && !$("#p2CorpusDialog")?.classList.contains("hidden")) {
        if (!isCorpusEditorReady("p2CorpusText")) return;
        const materialText = getCorpusMarkdownValue("p2CorpusText").trim();
        if (!materialText) return;
        sendKeepaliveJson("/api/p2-corpus", {
          entry_id: p2Entry.entry_id || "",
          category: $("p2CorpusCategory")?.value || p2Entry.category || "person",
          title: $("p2CorpusTitle")?.value || "",
          material_text: materialText,
          p3_follow_up_text: p2Entry.p3_follow_up_text || "",
          linked_question: $("p2CorpusLinkedQuestion")?.value || "",
          source: "p2_corpus_editor",
        });
      }
      const p2P3Entry = state.p2Corpus.activeP3Entry;
      if (p2P3Entry && !$("#p2CorpusP3Dialog")?.classList.contains("hidden")) {
        if (!isCorpusEditorReady("p2CorpusP3FollowUp")) return;
        const materialText = String(p2P3Entry.material_text || "").trim();
        if (!materialText) return;
        sendKeepaliveJson("/api/p2-corpus", {
          entry_id: p2P3Entry.entry_id || "",
          category: p2P3Entry.category || "person",
          title: p2P3Entry.title || "",
          material_text: materialText,
          p3_follow_up_text: getCorpusMarkdownValue("p2CorpusP3FollowUp").trim(),
          linked_question: p2P3Entry.linked_question || "",
          source: "p2_corpus_p3_editor",
        });
      }
    }

    async function openP1CorpusLibrary() {
      if (!state.account.authenticated) {
        state.account.returnView = "p1Corpus";
        switchView("login", { force: true, skipAuthGate: true, authMessage: "登录后才能保存和复用你的 P1 语料库。" });
        return;
      }
      openCorpusWindow("p1Corpus");
    }

    async function openP1CorpusEditor(entry) {
      if (!entry) return;
      const storage = p1CorpusStorageEntry(entry);
      let preparedEntry = { ...entry, ...storage };
      if ((storage.question_id || storage.question || preparedEntry.display_question) && !preparedEntry.corpus_text) {
        let refreshedCorpus = false;
        if (!(state.p1Corpus.topics || []).length) {
          try {
            const payload = await fetchP1CorpusPayload();
            applyP1CorpusPayload(payload);
            refreshedCorpus = true;
          } catch (_error) {
            // The editor can still open with the current report answer.
          }
        }
        let existing = findExactP1CorpusEntryForTarget(preparedEntry);
        if (!existing?.corpus_text && !refreshedCorpus) {
          try {
            const payload = await fetchP1CorpusPayload();
            applyP1CorpusPayload(payload);
            existing = findExactP1CorpusEntryForTarget(preparedEntry);
          } catch (_error) {
            // The editor can still open with the current report answer.
          }
        }
        if (!existing?.corpus_text) {
          try {
            const payload = await fetchP1CorpusPayload({ scope: "all" });
            existing = findExactP1CorpusEntryForTargetInTopics(preparedEntry, payload.topics || []);
          } catch (_error) {
            // Archive corpus lookup is best-effort and must not block editing.
          }
        }
        if (existing) {
          preparedEntry = {
            ...preparedEntry,
            corpus_text: existing.corpus_text || "",
            last_ai_answer: preparedEntry.last_ai_answer || existing.last_ai_answer || "",
          };
        }
      }
      state.p1Corpus.activeEntry = preparedEntry;
      entry = preparedEntry;
      const topic = entry.topic || entry.prompt?.topic || "";
      const question = entry.display_question || entry.question || "";
      const aiAnswer = entry.last_ai_answer || entry.band7_version || entry.aiAnswer || "";
      text("p1CorpusDialogTopic", topic ? topic.replaceAll("_", " ").toUpperCase() : "PART 1");
      text("p1CorpusDialogTitle", question);
      setCorpusMarkdownValue("p1CorpusText", entry.corpus_text || "");
      const aiBox = $("p1CorpusAiAnswer");
      const aiWrap = aiBox?.closest(".p1-corpus-ai-box");
      aiWrap?.classList.toggle("hidden", !aiAnswer);
      if (aiBox) {
        aiBox.dataset.markdownSource = aiAnswer || "";
        aiBox.innerHTML = aiAnswer ? renderSpokenAnswerMarkdown(aiAnswer) : "";
      }
      text("p1CorpusSaveStatus", "");
      $("p1CorpusDialog")?.classList.remove("hidden");
      if (!isCorpusEditorReady("p1CorpusText")) setCorpusEditorLoading("p1CorpusText", true);
      ensureCorpusMarkdownEditorReady("p1CorpusText").then((editor) => {
        if (!editor) setCorpusEditorLoading("p1CorpusText", false);
        setTimeout(() => editor?.focus?.() || $("p1CorpusText")?.focus(), 0);
      });
    }

    function closeP1CorpusEditor() {
      $("p1CorpusDialog")?.classList.add("hidden");
      state.p1Corpus.activeEntry = null;
    }

    async function saveAndCloseP1CorpusEditor() {
      if (!$("p1CorpusDialog") || $("p1CorpusDialog").classList.contains("hidden")) return;
      const entry = state.p1Corpus.activeEntry;
      const editorReady = isCorpusEditorReady("p1CorpusText");
      const corpusText = editorReady ? getCorpusMarkdownValue("p1CorpusText").trim() : "";
      closeP1CorpusEditor();
      if (entry && corpusText) saveP1CorpusEntry({ entry, corpusText, silent: true }).catch(() => null);
    }

    async function saveP1CorpusEntry(options = {}) {
      const entry = options.entry || state.p1Corpus.activeEntry;
      if (!entry) return;
      if (state.p1Corpus.saving) return;
      if (!options.corpusText && !isCorpusEditorReady("p1CorpusText")) {
        text("p1CorpusSaveStatus", "编辑器还没加载完成，请等一秒再保存。");
        if (options.closeOnError) closeP1CorpusEditor();
        return;
      }
      state.p1Corpus.saving = true;
      const button = $("saveP1CorpusBtn");
      const original = button?.textContent || "保存语料";
      const nextCorpusText = (options.corpusText ?? getCorpusMarkdownValue("p1CorpusText")).trim();
      if (!nextCorpusText) {
        if (!options.silent) text("p1CorpusSaveStatus", "内容为空，未保存。");
        state.p1Corpus.saving = false;
        if (options.closeOnEmpty) closeP1CorpusEditor();
        return;
      }
      if (button && !options.silent) {
        button.disabled = true;
        button.textContent = "保存中...";
      }
      if (!options.silent) text("p1CorpusSaveStatus", "");
      try {
        const storage = p1CorpusStorageEntry(entry);
        const saved = await api("/api/p1-corpus", {
          question_id: storage.question_id,
          topic: storage.topic,
          question: storage.question,
          corpus_text: nextCorpusText,
          last_ai_answer: entry.last_ai_answer || entry.band7_version || entry.aiAnswer || "",
          source: "report_or_library",
        });
        if (!options.silent) text("p1CorpusSaveStatus", `已保存 ${saved.updated_at || ""}`);
        const updated = upsertP1CorpusEntry(saved);
        if (state.p1Corpus.activeEntry) {
          const activeEntry = state.p1Corpus.activeEntry || {};
          state.p1Corpus.activeEntry = {
            ...activeEntry,
            corpus_text: (updated || saved)?.corpus_text || nextCorpusText,
            last_ai_answer: (updated || saved)?.last_ai_answer || activeEntry.last_ai_answer || "",
            updated_at: (updated || saved)?.updated_at || activeEntry.updated_at || "",
            display_question: activeEntry.display_question || activeEntry.question || saved.question || "",
          };
        }
        renderP1CorpusTopics();
        updateP1CorpusPeekButton(state.currentTurn);
        if (options.closeOnSuccess) closeP1CorpusEditor();
      } catch (error) {
        if (!options.silent) text("p1CorpusSaveStatus", error.message || String(error));
        if (options.closeOnError) closeP1CorpusEditor();
      } finally {
        state.p1Corpus.saving = false;
        if (button && !options.silent) {
          button.disabled = false;
          button.textContent = original;
        }
      }
    }

    async function loadP2Corpus(options = {}) {
      const stats = $("p2CorpusStats");
      const container = $("p2CorpusTopics");
      if (state.p2Corpus.loaded) {
        renderP2CorpusTopics();
        if (stats) stats.textContent = `${state.p2Corpus.categories.length} 个分类 · 刷新中`;
      } else {
        if (stats) stats.textContent = "Loading...";
        if (container) container.innerHTML = '<p class="muted">正在加载 P2 素材库...</p>';
      }
      try {
        const payload = await fetchP2CorpusPayload({ force: Boolean(options.force) });
        applyP2CorpusPayload(payload);
      } catch (error) {
        if (container) container.innerHTML = `<p class="error">${escapeHtml(error.message || String(error))}</p>`;
        if (stats) stats.textContent = "加载失败";
      }
    }

    function renderP2CorpusTopics() {
      const container = $("p2CorpusTopics");
      if (!container) return;
      const categories = state.p2Corpus.categories || [];
      const currentCards = state.p2Corpus.currentPart2Cards || [];
      if (!categories.length && !currentCards.length) {
        container.innerHTML = '<p class="muted">还没有 P2 素材分类。</p>';
        return;
      }
      const categoryHtml = categories.map((category) => {
        const items = category.items || [];
        const materialRows = items.map((item, index) => {
          const hasP3 = !!String(item.p3_follow_up_text || "").trim();
          const menu = corpusCardActionMenuHtml({
            menuAttr: "data-p2-corpus-menu",
            editAttr: "data-p2-corpus-edit",
            deleteAttr: "data-p2-corpus-delete",
            entryId: item.entry_id,
          });
          return `
            <div class="p2-material-row">
              <button type="button" class="p2-material-entry-button has-corpus" data-p2-corpus-entry="${escapeHtml(item.entry_id)}">
                <span class="p2-material-index">${index + 1}</span>
                <span class="p2-material-copy">
                  <span class="p2-material-title">${escapeHtml(item.title || "未命名素材")}</span>
                  <span class="p2-material-status${hasP3 ? " has-follow-up" : " is-empty"}">${hasP3 ? "P3 已填" : "P3 待填"}</span>
                </span>
              </button>
              <div class="p2-material-actions">
                <button type="button" class="p2-follow-up-edit-button${hasP3 ? " has-follow-up" : ""}" data-p2-corpus-p3="${escapeHtml(item.entry_id)}" aria-label="编辑 P3 追问" title="编辑 P3 追问">P3</button>
                ${menu}
              </div>
            </div>
          `;
        }).join("");
        return `
          <article class="p2-topic-card p2-category-entry-card">
            <header>
              <h3>${escapeHtml(category.label || category.category)}</h3>
              <span class="p2-topic-count">${category.material_count ?? (category.items || []).length}</span>
            </header>
            <div class="p2-topic-material-list">
              ${materialRows || '<div class="p2-topic-empty">还没有保存素材</div>'}
              <button type="button" class="p2-add-material-button" data-p2-corpus-new="${escapeHtml(category.category)}">
                <strong>+</strong>
                <span>新增${escapeHtml(category.label || "素材")}</span>
              </button>
            </div>
          </article>
        `;
      }).join("");
      const cardHtml = currentCards.map((item) => {
        const statusLabel = item.status === "new" ? "新题" : item.status === "retained" ? "保留题" : item.status || "";
        return `
          <article class="p2-seasonal-card">
            <header>
              <div>
                <span class="p2-seasonal-card-kicker">${escapeHtml(item.label || item.category || "P2")}${statusLabel ? ` · ${escapeHtml(statusLabel)}` : ""}</span>
                <h3>${escapeHtml(item.cue_title || item.title || "未命名题卡")}</h3>
              </div>
              <span class="p2-seasonal-card-state${item.has_material ? " is-ready" : ""}">${item.has_material ? "正文已填" : "正文待填"}</span>
            </header>
            ${p2CueQuestionHtml(item)}
            <footer>
              <button type="button" class="p2-seasonal-action primary" data-p2-corpus-card-material="${escapeHtml(item.entry_id)}">正文</button>
              <button type="button" class="p2-seasonal-action${item.has_p3_follow_up ? " is-ready" : ""}" data-p2-corpus-card-p3="${escapeHtml(item.entry_id)}">P3 追问</button>
            </footer>
          </article>
        `;
      }).join("");
      container.innerHTML = `
        <section class="p2-category-entry-grid" aria-label="P2 分类入口">
          ${categoryHtml}
        </section>
        <section class="p2-seasonal-card-section" aria-label="当季 P2 题卡">
          <header class="p2-seasonal-section-head">
            <div>
              <span class="corpus-page-kicker">CURRENT SEASON</span>
              <h3>当季 P2 题卡</h3>
            </div>
            <span>${currentCards.length} 张题卡</span>
          </header>
          <div class="p2-seasonal-card-grid">
            ${cardHtml || '<p class="muted">当前范围没有 P2 题卡。</p>'}
          </div>
        </section>
      `;
    }

    async function loadCorpusHome() {}

    async function loadLanguageTakeaways() {
      const stats = $("languageTakeawayStats");
      const list = $("languageTakeawayList");
      if (state.languageTakeaway.loaded) {
        renderLanguageTakeawayToggle();
        renderLanguageTakeaways();
        if (stats) stats.textContent = `${state.languageTakeaway.items.length} 条`;
        return;
      } else {
        if (stats) stats.textContent = "Loading...";
        if (list) list.innerHTML = '<p class="muted">正在加载 Takeaway...</p>';
      }
      try {
        const payload = await fetchLanguageTakeawaysPayload();
        applyLanguageTakeawaysPayload(payload);
        if (stats) stats.textContent = `${payload.count || 0} 条`;
        renderLanguageTakeawayToggle();
        renderLanguageTakeaways();
      } catch (error) {
        if (stats) stats.textContent = "加载失败";
        if (list) list.innerHTML = `<p class="error">${escapeHtml(error.message || String(error))}</p>`;
      }
    }

    function renderLanguageTakeaways() {
      const list = $("languageTakeawayList");
      if (!list) return;
      const items = state.languageTakeaway.items || [];
      const hiddenMode = state.languageTakeaway.hideEnglish;
      const revealed = state.languageTakeaway.revealedEntryIds;
      if (!items.length) {
        list.innerHTML = '<p class="muted language-book-empty">还没有摘录。平时选中单词或短语，点击“译”就可以加入这里。</p>';
        return;
      }
      list.innerHTML = items.map((item) => `
        <div class="language-takeaway-card-wrap ${hiddenMode && !revealed.has(item.entry_id) ? "is-concealed" : "is-revealed"}">
          <button type="button" class="language-takeaway-card" data-takeaway-entry="${escapeHtml(item.entry_id)}">
            <strong class="takeaway-source">${escapeHtml(item.source_text)}</strong>
            <span class="takeaway-chinese">${escapeHtml(item.chinese_text || "未填写中文")}</span>
          </button>
          ${corpusCardActionMenuHtml({
            menuAttr: "data-takeaway-menu",
            editAttr: "data-takeaway-edit",
            deleteAttr: "data-takeaway-delete",
            entryId: item.entry_id,
          })}
        </div>
      `).join("");
    }

    function renderLanguageTakeawayToggle() {
      const button = $("languageTakeawayHideToggle");
      if (!button) return;
      const hidden = state.languageTakeaway.hideEnglish;
      button.setAttribute("aria-pressed", hidden ? "true" : "false");
      button.innerHTML = hidden
        ? `<svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M3 3l18 18"></path>
            <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"></path>
            <path d="M9.9 4.2A10.3 10.3 0 0 1 12 4c6.5 0 10 8 10 8a17.9 17.9 0 0 1-4.2 5.1"></path>
            <path d="M6.6 6.6C3.6 8.6 2 12 2 12s3.5 8 10 8a9.5 9.5 0 0 0 4.8-1.3"></path>
          </svg><span>显示英文</span>`
        : `<svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"></path>
            <circle cx="12" cy="12" r="3"></circle>
          </svg><span>遮住英文</span>`;
    }

    function toggleLanguageTakeawayHiddenMode() {
      state.languageTakeaway.hideEnglish = !state.languageTakeaway.hideEnglish;
      if (state.languageTakeaway.hideEnglish) state.languageTakeaway.revealedEntryIds.clear();
      renderLanguageTakeawayToggle();
      renderLanguageTakeaways();
    }

    function speakLanguageTakeaway(textValue) {
      const value = String(textValue || "").trim();
      if (!value || !window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(value);
      utterance.lang = "en-US";
      utterance.rate = 0.86;
      window.speechSynthesis.speak(utterance);
    }

    function revealAndSpeakLanguageTakeaway(entryId) {
      const item = (state.languageTakeaway.items || []).find((entry) => entry.entry_id === entryId);
      if (!item) return;
      state.languageTakeaway.revealedEntryIds.add(entryId);
      speakLanguageTakeaway(item.source_text);
      renderLanguageTakeaways();
    }

    async function deleteLanguageTakeawayEntry(entryId) {
      if (!entryId) return;
      showConfirmDelete("确定要删除这条生词吗？", async () => {
        await api(`/api/language-takeaways/${encodeURIComponent(entryId)}`, null, { method: "DELETE" });
        state.languageTakeaway.items = (state.languageTakeaway.items || []).filter((item) => item.entry_id !== entryId);
        state.languageTakeaway.revealedEntryIds.delete(entryId);
        renderLanguageTakeaways();
        text("languageTakeawayStats", `${state.languageTakeaway.items.length} 条`);
      });
    }

    function languageTakeawayTranslationStatus(result) {
      if (result?.status === "ready" && result?.provider === "local") return "本地词典已填充，可继续编辑";
      if (result?.status === "ready") return "已翻译";
      if (result?.status === "needs_edit") return "本地词典未命中，可手动填写中文";
      if (result?.status === "missing_token") return "未配置翻译服务，可手动填写中文";
      if (result?.status === "unavailable") return "翻译服务暂不可用，可手动填写中文";
      return "可手动填写中文";
    }

    function setLanguageTakeawayStatus(message = "", options = {}) {
      const status = $("languageTakeawayStatus");
      if (!status) return;
      status.classList.toggle("is-loading", Boolean(options.loading));
      status.innerHTML = options.loading
        ? `<span class="language-status-spinner" aria-hidden="true"></span><span>${escapeHtml(message)}</span>`
        : escapeHtml(message);
    }

    function writingAnswerSelectionText() {
      const answerEl = $("writingAnswer");
      if (!answerEl || document.activeElement !== answerEl) return null;
      const start = Number(answerEl.selectionStart);
      const end = Number(answerEl.selectionEnd);
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
      const textValue = String(answerEl.value || "").slice(start, end).trim();
      if (textValue.length < 1 || textValue.length > 160) return null;
      const selectionRect = textareaSelectionEndpointRect(answerEl, end);
      if (!selectionRect) return null;
      return {
        text: textValue,
        rect: selectionRect,
        center: {
          x: selectionRect.left + selectionRect.width / 2,
          y: selectionRect.top + selectionRect.height / 2,
        },
        source: "writing_answer",
      };
    }

    function textareaSelectionEndpointRect(textarea, endOffset) {
      const hostRect = textarea.getBoundingClientRect();
      if (!hostRect.width || !hostRect.height) return null;
      const style = window.getComputedStyle(textarea);
      const mirror = document.createElement("div");
      const marker = document.createElement("span");
      const copyProperties = [
        "boxSizing", "width", "height", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
        "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
        "fontFamily", "fontSize", "fontWeight", "fontStyle", "fontVariant", "lineHeight",
        "letterSpacing", "textTransform", "textIndent", "textAlign", "wordSpacing", "tabSize",
      ];
      copyProperties.forEach((property) => {
        mirror.style[property] = style[property];
      });
      mirror.style.position = "fixed";
      mirror.style.left = `${hostRect.left}px`;
      mirror.style.top = `${hostRect.top}px`;
      mirror.style.width = `${hostRect.width}px`;
      mirror.style.height = `${hostRect.height}px`;
      mirror.style.overflow = "auto";
      mirror.style.whiteSpace = "pre-wrap";
      mirror.style.overflowWrap = "break-word";
      mirror.style.wordBreak = style.wordBreak || "break-word";
      mirror.style.visibility = "hidden";
      mirror.style.pointerEvents = "none";
      mirror.style.zIndex = "-1";
      marker.textContent = "\u200b";
      mirror.append(document.createTextNode(String(textarea.value || "").slice(0, endOffset)));
      mirror.append(marker);
      document.body.append(mirror);
      mirror.scrollTop = textarea.scrollTop;
      mirror.scrollLeft = textarea.scrollLeft;
      const markerRect = marker.getBoundingClientRect();
      mirror.remove();
      const lineHeight = Number.parseFloat(style.lineHeight) || Number.parseFloat(style.fontSize) * 1.4 || 24;
      const left = Math.min(hostRect.right - 18, Math.max(hostRect.left + 8, markerRect.left));
      const top = Math.min(hostRect.bottom - lineHeight, Math.max(hostRect.top + 8, markerRect.top));
      return {
        left,
        right: left + 1,
        top,
        bottom: top + lineHeight,
        width: 1,
        height: lineHeight,
      };
    }

    function selectionText() {
      const answerSelection = writingAnswerSelectionText();
      if (answerSelection) return answerSelection;
      const selection = window.getSelection?.();
      const textValue = String(selection?.toString() || "").trim();
      if (!selection || selection.rangeCount === 0 || textValue.length < 1 || textValue.length > 160) return null;
      const range = selection.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      if (!rect || (rect.width === 0 && rect.height === 0)) return null;
      const promptEl = $("writingPromptText");
      const answerEl = $("writingAnswer");
      const activeEl = document.activeElement;
      const source = promptEl && promptEl.contains(range.commonAncestorContainer)
        ? "writing_prompt"
        : (activeEl === answerEl ? "writing_answer" : "general");
      return {
        text: textValue,
        rect,
        center: {
          x: rect.left + rect.width / 2,
          y: rect.top + rect.height / 2,
        },
        source,
      };
    }

    function hideLanguageTakeawayTrigger() {
      $("languageTakeawayTrigger")?.classList.add("hidden");
      state.languageTakeaway.selectionAnchor = null;
      if (state.languageTakeaway.selectionScrollRaf) {
        window.cancelAnimationFrame(state.languageTakeaway.selectionScrollRaf);
        state.languageTakeaway.selectionScrollRaf = null;
      }
    }

    function hideLanguageTakeawayPopup() {
      $("languageTakeawayPopup")?.classList.add("hidden");
      setLanguageTakeawayStatus("");
    }

    function placeLanguageTakeawayTrigger(left, top) {
      const trigger = $("languageTakeawayTrigger");
      if (!trigger) return;
      const margin = 12;
      const rect = trigger.getBoundingClientRect();
      const width = rect.width || 34;
      const height = rect.height || 34;
      const maxLeft = Math.max(margin, window.innerWidth - width - margin);
      const maxTop = Math.max(margin, window.innerHeight - height - margin);
      trigger.style.left = `${Math.min(maxLeft, Math.max(margin, left))}px`;
      trigger.style.top = `${Math.min(maxTop, Math.max(margin, top))}px`;
    }

    function showLanguageTakeawayTrigger(selectionInfo) {
      const trigger = $("languageTakeawayTrigger");
      if (!trigger || !selectionInfo) return;
      if (selectionInfo.source === "writing_prompt") return;
      state.languageTakeaway.selectedText = selectionInfo.text;
      if (!state.languageTakeaway.selectionAnchor) {
        state.languageTakeaway.selectionAnchor = selectionInfo.center;
      }
      placeLanguageTakeawayTrigger(selectionInfo.rect.right + 8, selectionInfo.rect.top - 4);
      trigger.classList.remove("hidden");
    }

    function trackLanguageTakeawayTriggerDuringScroll() {
      const trigger = $("languageTakeawayTrigger");
      if (!trigger || trigger.classList.contains("hidden")) return;
      if (!$("languageTakeawayPopup")?.classList.contains("hidden")) return;
      if (state.languageTakeaway.selectionScrollRaf) return;
      state.languageTakeaway.selectionScrollRaf = window.requestAnimationFrame(() => {
        state.languageTakeaway.selectionScrollRaf = null;
        const info = selectionText();
        const anchor = state.languageTakeaway.selectionAnchor;
        if (!info || !anchor) {
          hideLanguageTakeawayTrigger();
          return;
        }
        const distance = Math.hypot(info.center.x - anchor.x, info.center.y - anchor.y);
        if (distance > 260) {
          hideLanguageTakeawayTrigger();
          return;
        }
        placeLanguageTakeawayTrigger(info.rect.right + 8, info.rect.top - 4);
      });
    }

    function scheduleLanguageTakeawayTriggerFromSelection() {
      window.clearTimeout(state.languageTakeaway.selectionTimer);
      state.languageTakeaway.selectionTimer = window.setTimeout(() => {
        if (!$("languageTakeawayPopup")?.classList.contains("hidden")) return;
        const info = selectionText();
        if (info?.source === "writing_prompt") {
          hideLanguageTakeawayTrigger();
          return;
        }
        if (info?.source === "writing_answer") {
          state.languageTakeaway.selectionAnchor = info?.center || null;
          if (info) showLanguageTakeawayTrigger(info);
          else hideLanguageTakeawayTrigger();
          return;
        }
        state.languageTakeaway.selectionAnchor = info?.center || null;
        if (info) showLanguageTakeawayTrigger(info);
        else hideLanguageTakeawayTrigger();
      }, 80);
    }

    function placeLanguageTakeawayPopup(left, top) {
      const popup = $("languageTakeawayPopup");
      if (!popup) return;
      const margin = 12;
      const rect = popup.getBoundingClientRect();
      const width = rect.width || 360;
      const height = rect.height || 360;
      const maxLeft = Math.max(margin, window.innerWidth - width - margin);
      const maxTop = Math.max(margin, window.innerHeight - height - margin);
      popup.style.left = `${Math.min(maxLeft, Math.max(margin, left))}px`;
      popup.style.top = `${Math.min(maxTop, Math.max(margin, top))}px`;
    }

    async function openLanguageTakeawayPopup() {
      const textValue = state.languageTakeaway.selectedText;
      if (!textValue) return;
      const popup = $("languageTakeawayPopup");
      const trigger = $("languageTakeawayTrigger");
      if (!popup || !trigger) return;
      $("languageTakeawaySource").value = textValue;
      $("languageTakeawayChinese").value = "";
      setLanguageTakeawayStatus("翻译中...", { loading: true });
      const triggerRect = trigger.getBoundingClientRect();
      popup.classList.remove("hidden");
      placeLanguageTakeawayPopup(triggerRect.left, triggerRect.bottom + 8);
      hideLanguageTakeawayTrigger();
      await translateLanguageTakeawaySource(textValue);
    }

    async function translateLanguageTakeawaySource(sourceValue = null) {
      const sourceText = String(sourceValue ?? $("languageTakeawaySource")?.value ?? "").trim();
      if (!sourceText) {
        setLanguageTakeawayStatus("原文为空。");
        return;
      }
      setLanguageTakeawayStatus("翻译中...", { loading: true });
      try {
        const result = await api("/api/language-takeaways/translate", { text: sourceText });
        $("languageTakeawaySource").value = result.source_text || sourceText;
        $("languageTakeawayChinese").value = result.chinese_text || "";
        setLanguageTakeawayStatus(languageTakeawayTranslationStatus(result));
      } catch (error) {
        setLanguageTakeawayStatus(error.message || "翻译失败，可手动填写中文");
      }
    }

    async function saveLanguageTakeaway() {
      const sourceText = ($("languageTakeawaySource")?.value || "").trim();
      const chineseText = ($("languageTakeawayChinese")?.value || "").trim();
      if (!sourceText) {
        setLanguageTakeawayStatus("原文为空。");
        return;
      }
      setLanguageTakeawayStatus("保存中...");
      try {
        const saved = await api("/api/language-takeaways", {
          source_text: sourceText,
          chinese_text: chineseText,
          context_url: window.location.href,
          context_label: viewCopy[state.view]?.[0] || "",
          source: "selection_popup",
        });
        const existingIndex = state.languageTakeaway.items.findIndex((item) => item.entry_id === saved.entry_id);
        if (existingIndex >= 0) state.languageTakeaway.items.splice(existingIndex, 1);
        state.languageTakeaway.items.unshift(saved);
        state.languageTakeaway.revealedEntryIds.add(saved.entry_id);
        renderLanguageTakeaways();
        text("languageTakeawayStats", `${state.languageTakeaway.items.length} 条`);
        hideLanguageTakeawayPopup();
      } catch (error) {
        setLanguageTakeawayStatus(error.message || "保存失败");
      }
    }

    async function saveWritingTakeaway() {
      const sourceText = ($("languageTakeawaySource")?.value || "").trim();
      const chineseText = ($("languageTakeawayChinese")?.value || "").trim();
      if (!sourceText) {
        setLanguageTakeawayStatus("原文为空。");
        return;
      }
      setLanguageTakeawayStatus("保存到写作积累中...");
      try {
        const saved = await api("/api/writing-takeaways", {
          source_text: sourceText,
          chinese_text: chineseText,
          context_url: window.location.href,
          context_label: viewCopy[state.view]?.[0] || "",
          source: "writing_takeaway",
        });
        const existingIndex = state.writingTakeaway.items.findIndex((item) => item.entry_id === saved.entry_id);
        if (existingIndex >= 0) state.writingTakeaway.items.splice(existingIndex, 1);
        state.writingTakeaway.items.unshift(saved);
        state.writingTakeaway.loaded = true;
        state.writingTakeaway.revealedEntryIds.add(saved.entry_id);
        renderWritingTakeaways();
        text("writingTakeawayStats", `${state.writingTakeaway.items.length} 条`);
        hideLanguageTakeawayPopup();
      } catch (error) {
        setLanguageTakeawayStatus(error.message || "保存失败");
      }
    }

    function takeawayItems(kind) {
      return kind === "writing" ? (state.writingTakeaway.items || []) : (state.languageTakeaway.items || []);
    }

    function findTakeawayEntry(kind, entryId) {
      return takeawayItems(kind).find((entry) => entry.entry_id === entryId) || null;
    }

    function takeawayEditEndpoint(kind, entryId) {
      const base = kind === "writing" ? "/api/writing-takeaways" : "/api/language-takeaways";
      return `${base}/${encodeURIComponent(entryId)}`;
    }

    function openTakeawayEditor(kind, entryId) {
      const entry = findTakeawayEntry(kind, entryId);
      if (!entry) return;
      closeCorpusCardActionMenus();
      state.languageTakeaway.activeEdit = {
        kind,
        entryId,
        originalSourceText: entry.source_text || "",
        originalChineseText: entry.chinese_text || "",
      };
      text("takeawayEditDialogType", kind === "writing" ? "写作积累" : "Takeaway");
      text("takeawayEditDialogTitle", kind === "writing" ? "编辑写作积累" : "编辑 Takeaway");
      if ($("takeawayEditSource")) $("takeawayEditSource").value = entry.source_text || "";
      if ($("takeawayEditChinese")) $("takeawayEditChinese").value = entry.chinese_text || "";
      text("takeawayEditStatus", "");
      $("takeawayEditDialog")?.classList.remove("hidden");
      setTimeout(() => $("takeawayEditSource")?.focus(), 0);
    }

    function takeawayEditorValues() {
      return {
        sourceText: ($("takeawayEditSource")?.value || "").trim(),
        chineseText: ($("takeawayEditChinese")?.value || "").trim(),
      };
    }

    function isTakeawayEditorDirty() {
      const active = state.languageTakeaway.activeEdit;
      if (!active?.entryId) return false;
      const values = takeawayEditorValues();
      return (
        values.sourceText !== String(active.originalSourceText || "").trim() ||
        values.chineseText !== String(active.originalChineseText || "").trim()
      );
    }

    async function closeTakeawayEditor(options = {}) {
      if (options.saveDirty && isTakeawayEditorDirty()) {
        const saved = await saveTakeawayEditor();
        if (!saved) return false;
        return true;
      }
      $("takeawayEditDialog")?.classList.add("hidden");
      state.languageTakeaway.activeEdit = null;
      state.languageTakeaway.editing = false;
      text("takeawayEditStatus", "");
      return true;
    }

    function replaceTakeawayEntry(kind, saved) {
      const listState = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      const items = listState.items || [];
      const index = items.findIndex((item) => item.entry_id === saved.entry_id);
      if (index >= 0) items.splice(index, 1, saved);
      else items.unshift(saved);
      listState.items = items;
      if (kind === "writing") {
        state.writingTakeaway.revealedEntryIds.add(saved.entry_id);
        renderWritingTakeaways();
        text("writingTakeawayStats", `${state.writingTakeaway.items.length} 条`);
      } else {
        state.languageTakeaway.revealedEntryIds.add(saved.entry_id);
        renderLanguageTakeaways();
        text("languageTakeawayStats", `${state.languageTakeaway.items.length} 条`);
      }
    }

    async function saveTakeawayEditor() {
      const active = state.languageTakeaway.activeEdit;
      if (!active?.entryId || state.languageTakeaway.editing) return false;
      const { sourceText, chineseText } = takeawayEditorValues();
      if (!sourceText) {
        text("takeawayEditStatus", "原文为空，未保存。");
        return false;
      }
      state.languageTakeaway.editing = true;
      const button = $("saveTakeawayEditBtn");
      const original = button?.textContent || "保存";
      if (button) {
        button.disabled = true;
        button.textContent = "保存中...";
      }
      text("takeawayEditStatus", "");
      try {
        const saved = await api(takeawayEditEndpoint(active.kind, active.entryId), {
          source_text: sourceText,
          chinese_text: chineseText,
        }, { method: "POST" });
        replaceTakeawayEntry(active.kind, saved);
        closeTakeawayEditor();
        return true;
      } catch (error) {
        text("takeawayEditStatus", error.message || String(error));
        return false;
      } finally {
        state.languageTakeaway.editing = false;
        if (button) {
          button.disabled = false;
          button.textContent = original;
        }
      }
    }

    function findP2CorpusEntry(entryId) {
      for (const category of state.p2Corpus.categories || []) {
        const found = (category.items || []).find((item) => item.entry_id === entryId);
        if (found) return { ...found, label: category.label || found.label };
      }
      const card = (state.p2Corpus.currentPart2Cards || []).find((item) => item.entry_id === entryId);
      if (card) return { ...card };
      return null;
    }

    function p2CueQuestionHtml(item) {
      const bullets = (item.bullets || []).map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("");
      return `
        <div class="p2-seasonal-cue">
          <strong>${escapeHtml(item.cue_title || item.title || "未命名题卡")}</strong>
          ${bullets ? `<ul>${bullets}</ul>` : ""}
          ${item.rounding ? `<p>${escapeHtml(item.rounding)}</p>` : ""}
        </div>
      `;
    }

    async function openP2CorpusLibrary() {
      if (!state.account.authenticated) {
        state.account.returnView = "p2Corpus";
        switchView("login", { force: true, skipAuthGate: true, authMessage: "登录后才能保存和复用你的 P2 串题素材库。" });
        return;
      }
      openCorpusWindow("p2Corpus");
    }

    function openP2CorpusEditor(entry = {}) {
      const category = entry.category || "person";
      state.p2Corpus.activeEntry = { ...entry, category };
      text("p2CorpusDialogCategory", (entry.label || category).toString());
      text("p2CorpusDialogTitle", entry.entry_id ? "编辑 P2 素材" : "新增 P2 素材");
      if ($("p2CorpusCategory")) $("p2CorpusCategory").value = category;
      if ($("p2CorpusTitle")) $("p2CorpusTitle").value = entry.title || "";
      setCorpusMarkdownValue("p2CorpusText", entry.material_text || "");
      if ($("p2CorpusLinkedQuestion")) $("p2CorpusLinkedQuestion").value = entry.linked_question || "";
      text("p2CorpusSaveStatus", "");
      $("p2CorpusDialog")?.classList.remove("hidden");
      if (!isCorpusEditorReady("p2CorpusText")) setCorpusEditorLoading("p2CorpusText", true);
      ensureCorpusMarkdownEditorReady("p2CorpusText").then((editor) => {
        if (!editor) setCorpusEditorLoading("p2CorpusText", false);
      });
      setTimeout(() => $("p2CorpusTitle")?.focus(), 0);
    }

    function closeP2CorpusEditor() {
      $("p2CorpusDialog")?.classList.add("hidden");
      state.p2Corpus.activeEntry = null;
    }

    function p2OfficialFollowUpQuestions(entry = {}) {
      const seen = new Set();
      return (entry.p3_follow_ups || [])
        .map((item) => String(item || "").replace(/\s+/g, " ").trim())
        .filter((item) => {
          if (!item || seen.has(item)) return false;
          seen.add(item);
          return true;
        });
    }

    function p2P3FollowUpMarkdownTemplate(entry = {}, selectedQuestions = null) {
      const questions = Array.isArray(selectedQuestions) ? selectedQuestions : p2OfficialFollowUpQuestions(entry);
      if (!questions.length) return "";
      const title = String(entry.cue_title || entry.title || "P2 题卡").trim();
      const lines = [
        `## ${title} 相关 P3 追问`,
        "",
        "根据题库追问整理答案。每道题下面留空给你写自己的回答。",
        "",
      ];
      questions.forEach((question, index) => {
        lines.push(`### ${index + 1}. ${question}`);
        lines.push("");
        lines.push("- 我的回答：");
        lines.push("");
      });
      return lines.join("\n").trim();
    }

    function updateP2CorpusP3QuestionSource(entry = {}) {
      const questions = p2OfficialFollowUpQuestions(entry);
      text("p2CorpusP3QuestionSourceStatus", questions.length ? `题库追问 ${questions.length} 道` : "这张题卡暂无题库 P3 追问");
      const pickerButton = $("openP2CorpusP3QuestionPickerBtn");
      if (pickerButton) {
        pickerButton.disabled = !questions.length;
        pickerButton.textContent = questions.length ? "选择题库追问" : "暂无题库追问";
      }
      renderP2CorpusP3QuestionPicker(entry);
    }

    function renderP2CorpusP3QuestionPicker(entry = state.p2Corpus.activeP3Entry || {}) {
      const list = $("p2CorpusP3QuestionList");
      if (!list) return;
      const questions = p2OfficialFollowUpQuestions(entry);
      if (!questions.length) {
        list.innerHTML = '<p class="muted">这张 P2 题卡暂时没有题库 P3 追问。你可以直接在编辑器里手动添加。</p>';
        text("p2CorpusP3QuestionPickerStatus", "");
        return;
      }
      list.innerHTML = questions.map((question, index) => `
        <label class="p2-p3-question-option">
          <input type="checkbox" value="${index}" checked>
          <span>
            <strong>Q${index + 1}</strong>
            <em>${escapeHtml(question)}</em>
          </span>
        </label>
      `).join("");
      text("p2CorpusP3QuestionPickerStatus", `已默认选择 ${questions.length} 道`);
    }

    function openP2CorpusP3QuestionPicker() {
      const entry = state.p2Corpus.activeP3Entry || {};
      renderP2CorpusP3QuestionPicker(entry);
      $("p2CorpusP3QuestionPicker")?.classList.remove("hidden");
    }

    function closeP2CorpusP3QuestionPicker() {
      $("p2CorpusP3QuestionPicker")?.classList.add("hidden");
    }

    function insertSelectedP2CorpusP3Questions() {
      const entry = state.p2Corpus.activeP3Entry || {};
      const officialQuestions = p2OfficialFollowUpQuestions(entry);
      if (!officialQuestions.length) {
        text("p2CorpusP3QuestionPickerStatus", "这张题卡暂无题库追问。");
        return;
      }
      const selected = Array.from(document.querySelectorAll("#p2CorpusP3QuestionList input[type='checkbox']:checked"))
        .map((input) => officialQuestions[Number(input.value)])
        .filter(Boolean);
      if (!selected.length) {
        text("p2CorpusP3QuestionPickerStatus", "请选择至少一道追问。");
        return;
      }
      setCorpusMarkdownValue("p2CorpusP3FollowUp", p2P3FollowUpMarkdownTemplate(entry, selected));
      text("p2CorpusP3QuestionPickerStatus", `已插入 ${selected.length} 道追问`);
      text("p2CorpusP3SaveStatus", "已插入题库追问，编辑回答后保存。");
      closeP2CorpusP3QuestionPicker();
      setTimeout(() => {
        const editor = isCorpusEditorReady("p2CorpusP3FollowUp") ? null : $("p2CorpusP3FollowUp");
        editor?.focus?.();
      }, 0);
    }

    function openP2CorpusP3Editor(entry = {}) {
      if (!entry?.entry_id) return;
      const category = entry.category || "person";
      state.p2Corpus.activeP3Entry = { ...entry, category };
      text("p2CorpusP3DialogCategory", (entry.label || category).toString());
      text("p2CorpusP3DialogTitle", entry.title ? `相关 P3 追问：${entry.title}` : "编辑相关 P3 追问");
      updateP2CorpusP3QuestionSource(state.p2Corpus.activeP3Entry);
      const initialText = entry.p3_follow_up_text || p2P3FollowUpMarkdownTemplate(entry);
      setCorpusMarkdownValue("p2CorpusP3FollowUp", initialText);
      text("p2CorpusP3SaveStatus", entry.p3_follow_up_text ? "" : (initialText ? "已放入题库追问，可直接补充回答。" : "这张题卡暂无题库 P3 追问，可手动添加。"));
      closeP2CorpusP3QuestionPicker();
      $("p2CorpusP3Dialog")?.classList.remove("hidden");
      if (!isCorpusEditorReady("p2CorpusP3FollowUp")) setCorpusEditorLoading("p2CorpusP3FollowUp", true);
      ensureCorpusMarkdownEditorReady("p2CorpusP3FollowUp").then((editor) => {
        if (!editor) setCorpusEditorLoading("p2CorpusP3FollowUp", false);
        setTimeout(() => editor?.focus?.() || $("p2CorpusP3FollowUp")?.focus(), 0);
      });
    }

    function closeP2CorpusP3Editor() {
      $("p2CorpusP3Dialog")?.classList.add("hidden");
      closeP2CorpusP3QuestionPicker();
      state.p2Corpus.activeP3Entry = null;
    }

    async function saveAndCloseP2CorpusEditor() {
      if (!$("p2CorpusDialog") || $("p2CorpusDialog").classList.contains("hidden")) return;
      const entry = state.p2Corpus.activeEntry || {};
      const editorReady = isCorpusEditorReady("p2CorpusText");
      const materialText = editorReady ? getCorpusMarkdownValue("p2CorpusText").trim() : "";
      const title = $("p2CorpusTitle")?.value || "";
      const category = $("p2CorpusCategory")?.value || entry.category || "person";
      const linkedQuestion = $("p2CorpusLinkedQuestion")?.value || "";
      closeP2CorpusEditor();
      if (materialText) {
        saveP2CorpusEntry({
          entry: { ...entry, category, title, linked_question: linkedQuestion },
          materialText,
          silent: true,
        }).catch(() => null);
      }
    }

    async function saveAndCloseP2CorpusP3Editor() {
      if (!$("p2CorpusP3Dialog") || $("p2CorpusP3Dialog").classList.contains("hidden")) return;
      const entry = state.p2Corpus.activeP3Entry || {};
      const editorReady = isCorpusEditorReady("p2CorpusP3FollowUp");
      const p3FollowUpText = editorReady ? getCorpusMarkdownValue("p2CorpusP3FollowUp").trim() : "";
      closeP2CorpusP3Editor();
      if (entry.entry_id && p3FollowUpText) {
        saveP2CorpusEntry({
          entry,
          materialText: entry.material_text,
          p3FollowUpText,
          source: "p2_corpus_p3_editor",
          silent: true,
        }).catch(() => null);
      }
    }

    async function saveP2CorpusEntry(options = {}) {
      const entry = options.entry || state.p2Corpus.activeEntry || {};
      if (state.p2Corpus.saving) return;
      const hasExplicitP3Text = typeof options.p3FollowUpText === "string";
      if (!options.materialText && !hasExplicitP3Text && !isCorpusEditorReady("p2CorpusText")) {
        text("p2CorpusSaveStatus", "编辑器还没加载完成，请等一秒再保存。");
        if (options.closeOnError) closeP2CorpusEditor();
        return;
      }
      state.p2Corpus.saving = true;
      const button = $("saveP2CorpusBtn");
      const original = button?.textContent || "保存素材";
      const nextMaterialText = (options.materialText ?? getCorpusMarkdownValue("p2CorpusText")).trim();
      const materialDialogOpen = !$("p2CorpusDialog")?.classList.contains("hidden");
      const p3DialogOpen = !$("p2CorpusP3Dialog")?.classList.contains("hidden");
      const nextCategory = (options.category ?? (materialDialogOpen ? $("p2CorpusCategory")?.value : "")) || entry.category || "person";
      const nextTitle = (options.title ?? (materialDialogOpen ? $("p2CorpusTitle")?.value : "")) || entry.title || "";
      const nextLinkedQuestion = (options.linkedQuestion ?? (materialDialogOpen ? $("p2CorpusLinkedQuestion")?.value : "")) || entry.linked_question || "";
      const nextP3FollowUpText = options.p3FollowUpText ?? (p3DialogOpen ? getCorpusMarkdownValue("p2CorpusP3FollowUp") : entry.p3_follow_up_text || "");
      if (!nextMaterialText && !String(nextP3FollowUpText || "").trim()) {
        if (!options.silent) text("p2CorpusSaveStatus", "内容为空，未保存。");
        state.p2Corpus.saving = false;
        if (options.closeOnEmpty) closeP2CorpusEditor();
        return;
      }
      if (button && !options.silent) {
        button.disabled = true;
        button.textContent = "保存中...";
      }
      if (!options.silent) text("p2CorpusSaveStatus", "");
      try {
        const saved = await api("/api/p2-corpus", {
          entry_id: entry.entry_id || "",
          category: nextCategory,
          title: nextTitle,
          material_text: nextMaterialText,
          p3_follow_up_text: nextP3FollowUpText,
          linked_question: nextLinkedQuestion,
          source: options.source || "p2_corpus_editor",
        });
        if (!options.silent) text("p2CorpusSaveStatus", `已保存 ${saved.updated_at || ""}`);
        await loadP2Corpus();
        state.p2Corpus.selectedEntryId ||= saved.entry_id;
        if (options.closeOnSuccess) closeP2CorpusEditor();
      } catch (error) {
        if (!options.silent) text("p2CorpusSaveStatus", error.message || String(error));
        if (options.closeOnError) closeP2CorpusEditor();
      } finally {
        state.p2Corpus.saving = false;
        if (button && !options.silent) {
          button.disabled = false;
          button.textContent = original;
        }
      }
    }

    async function deleteP2CorpusEntry(entryId) {
      if (!entryId) return;
      showConfirmDelete("确定要删除这条 P2 素材吗？", async () => {
        await api(`/api/p2-corpus/${encodeURIComponent(entryId)}`, null, { method: "DELETE" });
        state.p2Corpus.categories = (state.p2Corpus.categories || []).map((category) => ({
          ...category,
          items: (category.items || []).filter((item) => item.entry_id !== entryId),
        }));
        if (state.p2Corpus.selectedEntryId === entryId) state.p2Corpus.selectedEntryId = "";
        if (state.p2Corpus.activeEntry?.entry_id === entryId) closeP2CorpusEditor();
        if (state.p2Corpus.activeP3Entry?.entry_id === entryId) closeP2CorpusP3Editor();
        renderP2CorpusTopics();
        renderP2CorpusPrepPanel();
        const stats = $("p2CorpusStats");
        if (stats) {
          const count = (state.p2Corpus.categories || []).reduce((total, category) => total + (category.items || []).length, 0);
          stats.textContent = `${state.p2Corpus.categories.length || 5} 个分类 · 已保存 ${count}`;
        }
        fetchP2CorpusPayload().then(applyP2CorpusPayload).catch(() => null);
      });
    }

    async function loadWritingTakeaways() {
      const stats = $("writingTakeawayStats");
      const list = $("writingTakeawayList");
      if (state.writingTakeaway.loaded) {
        renderWritingTakeawayToggle();
        renderWritingTakeaways();
        if (stats) stats.textContent = `${state.writingTakeaway.items.length} 条`;
        return;
      } else {
        if (stats) stats.textContent = "Loading...";
        if (list) list.innerHTML = '<p class="muted">正在加载写作积累...</p>';
      }
      try {
        const payload = await fetchWritingTakeawaysPayload();
        applyWritingTakeawaysPayload(payload);
        if (stats) stats.textContent = `${payload.count || 0} 条`;
        renderWritingTakeawayToggle();
        renderWritingTakeaways();
      } catch (error) {
        if (stats) stats.textContent = "加载失败";
        if (list) list.innerHTML = `<p class="error">${escapeHtml(error.message || String(error))}</p>`;
      }
    }

    function renderWritingTakeaways() {
      const list = $("writingTakeawayList");
      if (!list) return;
      const items = state.writingTakeaway.items || [];
      const hiddenMode = state.writingTakeaway.hideEnglish;
      const revealed = state.writingTakeaway.revealedEntryIds;
      if (!items.length) {
        list.innerHTML = '<p class="muted language-book-empty">还没有写作积累。写作文或看报告时划选表达，点击“加入写作积累”即可保存到这里。</p>';
        return;
      }
      list.innerHTML = items.map((item) => `
        <div class="language-takeaway-card-wrap ${hiddenMode && !revealed.has(item.entry_id) ? "is-concealed" : "is-revealed"}">
          <button type="button" class="language-takeaway-card writing-takeaway-item" data-writing-takeaway-entry="${escapeHtml(item.entry_id)}">
            <strong class="takeaway-source">${escapeHtml(item.source_text)}</strong>
            <span class="takeaway-chinese">${escapeHtml(item.chinese_text || "未填写中文")}</span>
          </button>
          ${corpusCardActionMenuHtml({
            menuAttr: "data-writing-takeaway-menu",
            editAttr: "data-writing-takeaway-edit",
            deleteAttr: "data-writing-takeaway-delete",
            entryId: item.entry_id,
          })}
        </div>
      `).join("");
    }

    function renderWritingTakeawayToggle() {
      const button = $("writingTakeawayHideToggle");
      if (!button) return;
      const hidden = state.writingTakeaway.hideEnglish;
      button.setAttribute("aria-pressed", hidden ? "true" : "false");
      button.innerHTML = hidden
        ? `<svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M3 3l18 18"></path>
            <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"></path>
            <path d="M9.9 4.2A10.3 10.3 0 0 1 12 4c6.5 0 10 8 10 8a17.9 17.9 0 0 1-4.2 5.1"></path>
            <path d="M6.6 6.6C3.6 8.6 2 12 2 12s3.5 8 10 8a9.5 9.5 0 0 0 4.8-1.3"></path>
          </svg><span>显示英文</span>`
        : `<svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"></path>
            <circle cx="12" cy="12" r="3"></circle>
          </svg><span>遮住英文</span>`;
    }

    function toggleWritingTakeawayHiddenMode() {
      state.writingTakeaway.hideEnglish = !state.writingTakeaway.hideEnglish;
      if (state.writingTakeaway.hideEnglish) state.writingTakeaway.revealedEntryIds.clear();
      renderWritingTakeawayToggle();
      renderWritingTakeaways();
    }

    function revealAndSpeakWritingTakeaway(entryId) {
      const item = (state.writingTakeaway.items || []).find((entry) => entry.entry_id === entryId);
      if (!item) return;
      state.writingTakeaway.revealedEntryIds.add(entryId);
      speakLanguageTakeaway(item.source_text);
      renderWritingTakeaways();
    }

    async function deleteWritingTakeawayEntry(entryId) {
      if (!entryId) return;
      showConfirmDelete("确定要删除这条写作积累吗？", async () => {
        await api(`/api/writing-takeaways/${encodeURIComponent(entryId)}`, null, { method: "DELETE" });
        state.writingTakeaway.items = (state.writingTakeaway.items || []).filter((item) => item.entry_id !== entryId);
        state.writingTakeaway.revealedEntryIds.delete(entryId);
        renderWritingTakeaways();
        text("writingTakeawayStats", `${state.writingTakeaway.items.length} 条`);
      });
    }

    return {
      loadP1Corpus,
      renderP1CorpusTopics,
      findP1CorpusEntry,
      p1CorpusEntryIds,
      normalizeP1CorpusQuestionText,
      findP1CorpusEntryByExactQuestion,
      findExactP1CorpusEntryForTarget,
      currentP1CorpusTarget,
      ensureP1CorpusLoaded,
      updateP1CorpusPeekButton,
      openP1CorpusPeek,
      closeP1CorpusPeek,
      corpusPeekCard,
      placeCorpusPeekWindow,
      resetCorpusPeekWindowPosition,
      keepOpenCorpusPeekWindowsInBounds,
      currentP2CorpusEntry,
      ensureP2CorpusLoaded,
      updateP2CorpusPeekButton,
      p2CorpusPeekHtml,
      openP2CorpusPeek,
      closeP2CorpusPeek,
      updateP3CorpusPeekButton,
      openP3CorpusPeek,
      closeP3CorpusPeek,
      p1CorpusStorageEntry,
      upsertP1CorpusEntry,
      sendKeepaliveJson,
      autosaveOpenCorpusEditors,
      closeCorpusCardActionMenus,
      toggleCorpusCardActionMenu,
      openP1CorpusLibrary,
      openP1CorpusEditor,
      closeP1CorpusEditor,
      saveAndCloseP1CorpusEditor,
      saveP1CorpusEntry,
      loadP2Corpus,
      renderP2CorpusTopics,
      loadCorpusHome,
      loadLanguageTakeaways,
      renderLanguageTakeaways,
      renderLanguageTakeawayToggle,
      toggleLanguageTakeawayHiddenMode,
      speakLanguageTakeaway,
      revealAndSpeakLanguageTakeaway,
      deleteLanguageTakeawayEntry,
      languageTakeawayTranslationStatus,
      setLanguageTakeawayStatus,
      writingAnswerSelectionText,
      textareaSelectionEndpointRect,
      selectionText,
      hideLanguageTakeawayTrigger,
      hideLanguageTakeawayPopup,
      placeLanguageTakeawayTrigger,
      showLanguageTakeawayTrigger,
      trackLanguageTakeawayTriggerDuringScroll,
      scheduleLanguageTakeawayTriggerFromSelection,
      placeLanguageTakeawayPopup,
      openLanguageTakeawayPopup,
      translateLanguageTakeawaySource,
      saveLanguageTakeaway,
      saveWritingTakeaway,
      openTakeawayEditor,
      closeTakeawayEditor,
      saveTakeawayEditor,
      findP2CorpusEntry,
      openP2CorpusLibrary,
      openP2CorpusEditor,
      closeP2CorpusEditor,
      openP2CorpusP3Editor,
      closeP2CorpusP3Editor,
      openP2CorpusP3QuestionPicker,
      closeP2CorpusP3QuestionPicker,
      insertSelectedP2CorpusP3Questions,
      saveAndCloseP2CorpusEditor,
      saveAndCloseP2CorpusP3Editor,
      saveP2CorpusEntry,
      deleteP2CorpusEntry,
      loadWritingTakeaways,
      renderWritingTakeaways,
      renderWritingTakeawayToggle,
      toggleWritingTakeawayHiddenMode,
      revealAndSpeakWritingTakeaway,
      deleteWritingTakeawayEntry,
    };
  }

  window.IELTSCorpusTakeaway = {
    createCorpusTakeawayController,
  };
})();
