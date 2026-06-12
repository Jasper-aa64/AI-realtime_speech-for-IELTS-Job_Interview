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
      startPractice,
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
      withPending,
    } = options || {};

    if (!state || typeof $ !== "function" || typeof api !== "function") {
      throw new Error("Corpus/Takeaway controller requires shared app state and helpers.");
    }

    const CORPUS_PEEK_WINDOW_MARGIN = Number(corpusPeekWindowMargin) || 16;
    const EXPRESSION_REPLACEMENT_STORAGE_KEY = "ielts-expression-replacements";
    const TAKEAWAY_SRS_STORAGE_KEY = "ielts-takeaway-srs";
    const TAKEAWAY_DAILY_REVIEW_LIMIT = 20;
    const DEFAULT_EXPRESSION_REPLACEMENTS = [
      ["important", "vital / crucial / essential / significant / critical / indispensable / of great importance"],
      ["important for", "be essential for / be crucial for / be vital for / be indispensable to / contribute to / play a key role in / play a vital role in"],
      ["help", "assist / facilitate / contribute to / promote / support / enable"],
      ["cause", "lead to / result in / give rise to / contribute to / bring about / trigger"],
      ["improve", "enhance / boost / strengthen / upgrade / promote"],
      ["provide", "offer / supply / equip ... with / furnish ... with / make available"],
      ["many", "numerous / a large number of / a considerable number of / a substantial number of"],
      ["more and more", "an increasing number of / a growing number of / an increasing proportion of / a growing trend of"],
      ["think", "believe / argue / maintain / contend / hold the view that"],
      ["need", "require / demand / call for / necessitate / rely on / depend on / be essential for"],
      ["be important", "play a vital role in / play a crucial role in / play a key role in / serve as a cornerstone of / be fundamental to"],
      ["good", "beneficial / advantageous / favourable / positive"],
      ["bad", "detrimental / harmful / adverse / undesirable / negative"],
      ["show", "demonstrate / illustrate / indicate / reveal / highlight"],
      ["get", "obtain / acquire / gain / secure"],
      ["make", "create / generate / establish / develop / produce"],
      ["increase", "rise / grow / climb / expand / surge"],
      ["decrease", "decline / reduce / diminish / drop / fall"],
      ["solve", "address / tackle / overcome / alleviate / mitigate"],
      ["change", "alter / transform / modify / reshape / revolutionise"],
      ["important reason", "key reason / major factor / primary driver / main contributor"],
      ["people", "individuals / residents / citizens / members of society"],
      ["job", "employment / occupation / career opportunity / position"],
      ["money", "income / earnings / financial resources / wealth"],
      ["problem", "issue / challenge / concern / obstacle"],
    ].map(([source, replacements]) => ({
      id: `default:${source}`,
      source,
      replacements,
    }));
    const activeSpeechUtterances = [];
    let speechSequenceToken = 0;
    let suppressNextSpeechCancelError = false;
    const expressionReplacementState = {
      language: { items: null, loading: false, promise: null, synced: false },
      writing: { items: null, loading: false, promise: null, synced: false },
    };
    const p2BankCorpusCache = new Map();
    const p2BankP3Cache = new Map();
    let p1CorpusEditorLoadToken = 0;
    let p2BankCorpusLoadToken = 0;
    let p2BankP3LoadToken = 0;
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

    function reviewDayDate(date = new Date()) {
      const current = new Date(date);
      const start = new Date(current);
      start.setHours(4, 0, 0, 0);
      if (current < start) start.setDate(start.getDate() - 1);
      return start;
    }

    function todayKey(date = new Date()) {
      const reviewDay = reviewDayDate(date);
      const year = reviewDay.getFullYear();
      const month = String(reviewDay.getMonth() + 1).padStart(2, "0");
      const day = String(reviewDay.getDate()).padStart(2, "0");
      return `${year}-${month}-${day}`;
    }

    function nextReviewDayKey(date = new Date()) {
      const next = reviewDayDate(date);
      next.setDate(next.getDate() + 1);
      const year = next.getFullYear();
      const month = String(next.getMonth() + 1).padStart(2, "0");
      const day = String(next.getDate()).padStart(2, "0");
      return `${year}-${month}-${day}`;
    }

    function calendarDayKey(date = new Date()) {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      return `${year}-${month}-${day}`;
    }

    function addDaysKey(days, date = new Date()) {
      const next = reviewDayDate(date);
      next.setDate(next.getDate() + Number(days || 0));
      return calendarDayKey(next);
    }

    function takeawayReviewStorageKey(kind = "language") {
      return `${TAKEAWAY_SRS_STORAGE_KEY}:${kind === "writing" ? "writing" : "language"}`;
    }

    function takeawayReviewState(kind = "language") {
      try {
        const raw = window.localStorage?.getItem(takeawayReviewStorageKey(kind));
        const parsed = raw ? JSON.parse(raw) : {};
        if (parsed && typeof parsed === "object") return parsed;
      } catch (_error) {
        // Ignore malformed localStorage and rebuild review state lazily.
      }
      return {};
    }

    function saveTakeawayReviewState(kind, value) {
      try {
        window.localStorage?.setItem(takeawayReviewStorageKey(kind), JSON.stringify(value || {}));
      } catch (_error) {
        // Review scheduling is local and best-effort.
      }
      syncTakeawayReviewState(kind, value);
    }

    function hasTakeawayReviewData(value) {
      return Boolean(value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length);
    }

    function applyRemoteTakeawayReviewState(kind, value) {
      if (!value || typeof value !== "object" || Array.isArray(value)) return;
      if (!hasTakeawayReviewData(value)) {
        const local = takeawayReviewState(kind);
        if (hasTakeawayReviewData(local)) syncTakeawayReviewState(kind, local);
        return;
      }
      try {
        window.localStorage?.setItem(takeawayReviewStorageKey(kind), JSON.stringify(value));
      } catch (_error) {
        // Server state still wins for the current payload even if local cache fails.
      }
    }

    function syncTakeawayReviewState(kind, value) {
      if (!value || typeof value !== "object" || Array.isArray(value)) return;
      api(`/api/takeaway-review-state/${kind === "writing" ? "writing" : "language"}`, { state: value })
        .catch((error) => {
          setTakeawayReviewToast(kind, "复习状态同步失败，刷新后会重试。", { render: state.view === (kind === "writing" ? "writingTakeawayBook" : "takeawayBook") });
          console.warn("Takeaway review state sync failed", error);
        });
    }

    function takeawayItemsForKind(kind = "language") {
      return kind === "writing" ? (state.writingTakeaway.items || []) : (state.languageTakeaway.items || []);
    }

    function takeawayKindLoaded(kind = "language") {
      const target = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      return Boolean(target?.loaded);
    }

    function takeawayReviewSession(kind = "language") {
      const target = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      if (!target.reviewSession) target.reviewSession = { active: false, ids: [], reviewedIds: new Set() };
      if (!(target.reviewSession.reviewedIds instanceof Set)) {
        target.reviewSession.reviewedIds = new Set(target.reviewSession.reviewedIds || []);
      }
      return target.reviewSession;
    }

    function setTakeawayReviewToast(kind = "language", message = "", options = {}) {
      const target = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      window.clearTimeout(target.reviewToastTimer);
      target.reviewToast = String(message || "");
      if (target.reviewToast) {
        target.reviewToastTimer = window.setTimeout(() => {
          target.reviewToast = "";
          renderTakeawayReviewSurfaces(kind);
        }, 1800);
      }
      if (options.render) renderTakeawayReviewSurfaces(kind);
    }

    function ensureTakeawayReviewRecords(kind = "language") {
      const records = takeawayReviewState(kind);
      const items = takeawayItemsForKind(kind);
      let changed = false;
      const seen = new Set();
      items.forEach((item) => {
        const id = String(item.entry_id || "").trim();
        if (!id) return;
        seen.add(id);
        if (!records[id]) {
          records[id] = {
            due: todayKey(),
            reps: 0,
            interval: 0,
            ease: 2.5,
            last: "",
            lapses: 0,
          };
          changed = true;
        }
      });
      if (takeawayKindLoaded(kind) && items.length > 0) {
        Object.keys(records).forEach((id) => {
          if (id.startsWith("__")) return;
          if (!seen.has(id)) {
            delete records[id];
            changed = true;
          }
        });
      }
      if (changed) {
        const today = todayKey();
        const freshDueIds = items
          .map((item) => String(item.entry_id || "").trim())
          .filter((id) => id && String(records[id]?.due || "") <= today && String(records[id]?.last || "") !== today)
          .slice(0, TAKEAWAY_DAILY_REVIEW_LIMIT);
        const batch = takeawayDailyBatchRecord(records);
        if (freshDueIds.length && batch.day !== today) {
          records.__daily_batch = { day: today, ids: freshDueIds, completedDay: "" };
        }
      }
      if (changed) saveTakeawayReviewState(kind, records);
      return records;
    }

    function markTakeawayEntryDueToday(kind = "language", entryId = "") {
      const id = String(entryId || "").trim();
      if (!id) return;
      const records = ensureTakeawayReviewRecords(kind);
      const today = todayKey();
      const record = records[id] || {};
      records[id] = {
        due: today,
        reps: Number(record.reps || 0),
        interval: Number(record.interval || 0),
        ease: Number(record.ease || 2.5) || 2.5,
        last: "",
        lapses: Number(record.lapses || 0),
      };
      const batch = takeawayDailyBatchRecord(records);
      if (batch.day === today) {
        const ids = Array.from(new Set([...(batch.ids || []).map((value) => String(value || "").trim()).filter(Boolean), id]));
        records.__daily_batch = { day: today, ids, completedDay: "", locked: false };
      }
      saveTakeawayReviewState(kind, records);
    }

    function takeawayDailyBatchRecord(records) {
      const raw = records.__daily_batch;
      if (raw && typeof raw === "object" && Array.isArray(raw.ids)) return raw;
      return { day: "", ids: [], completedDay: "", locked: false };
    }

    function currentDueTakeawayItems(items, records, today) {
      return items
        .filter((item) => {
          const id = String(item?.entry_id || "").trim();
          const record = records[id] || {};
          return id && String(record.due || today) <= today && String(record.last || "") !== today;
        })
        .sort((a, b) => {
          const left = records[a.entry_id] || {};
          const right = records[b.entry_id] || {};
          return String(left.due || today).localeCompare(String(right.due || today));
        })
        .slice(0, TAKEAWAY_DAILY_REVIEW_LIMIT);
    }

    function dueTakeawayEntries(kind = "language") {
      const records = ensureTakeawayReviewRecords(kind);
      const today = todayKey();
      const items = takeawayItemsForKind(kind);
      const itemMap = new Map(items.map((item) => [String(item.entry_id || "").trim(), item]));
      const batch = takeawayDailyBatchRecord(records);
      const allDueItems = currentDueTakeawayItems(items, records, today);
      const reviewedTodayIds = Object.entries(records)
        .filter(([id, record]) => !id.startsWith("__") && record && typeof record === "object" && String(record.last || "") === today)
        .map(([id]) => id);
      if (batch.completedDay === today) {
        if (!batch.locked && !batch.ids.length && allDueItems.length) {
          records.__daily_batch = { day: today, ids: allDueItems.map((item) => item.entry_id), completedDay: "" };
          saveTakeawayReviewState(kind, records);
          return allDueItems;
        }
        return [];
      }
      if (batch.day === today) {
        const due = batch.ids
          .map((id) => itemMap.get(String(id || "").trim()))
          .filter((item) => {
            const id = String(item?.entry_id || "").trim();
            const record = records[id] || {};
            return item && id && String(record.due || today) <= today && String(record.last || "") !== today;
          });
        const batchedIds = new Set(batch.ids.map((id) => String(id || "").trim()).filter(Boolean));
        const hasReviewedInsideBatch = reviewedTodayIds.some((id) => batchedIds.has(id));
        if (reviewedTodayIds.length && batch.ids.length && !hasReviewedInsideBatch) {
          records.__daily_batch = { ...batch, completedDay: today, locked: true };
          saveTakeawayReviewState(kind, records);
          return [];
        }
        const extraDue = allDueItems.filter((item) => !batchedIds.has(String(item.entry_id || "").trim()));
        if (extraDue.length && !due.length && !batch.ids.length) {
          records.__daily_batch = { day: today, ids: extraDue.map((item) => item.entry_id), completedDay: "" };
          saveTakeawayReviewState(kind, records);
          return extraDue;
        }
        if (!due.length && batch.ids.length) {
          records.__daily_batch = { ...batch, completedDay: today, locked: true };
          saveTakeawayReviewState(kind, records);
        }
        return due;
      }
      if (reviewedTodayIds.length) {
        records.__daily_batch = { day: today, ids: reviewedTodayIds.slice(0, TAKEAWAY_DAILY_REVIEW_LIMIT), completedDay: today, locked: true };
        saveTakeawayReviewState(kind, records);
        return [];
      }
      const dueItems = allDueItems;
      records.__daily_batch = { day: today, ids: dueItems.map((item) => item.entry_id), completedDay: dueItems.length ? "" : today };
      saveTakeawayReviewState(kind, records);
      return dueItems;
    }

    function updateTakeawayReviewDots() {
      if (takeawayKindLoaded("language")) {
        const languageDue = dueTakeawayEntries("language").length;
        $("languageTakeawayDueDot")?.classList.toggle("hidden", languageDue <= 0);
        $("languageTakeawayDueDot")?.setAttribute("data-count", String(languageDue));
      }
      if (takeawayKindLoaded("writing")) {
        const writingDue = dueTakeawayEntries("writing").length;
        $("writingTakeawayDueDot")?.classList.toggle("hidden", writingDue <= 0);
        $("writingTakeawayDueDot")?.setAttribute("data-count", String(writingDue));
      }
    }

    function reviewPanelId(kind = "language") {
      return kind === "writing" ? "writingTakeawayReviewPanel" : "languageTakeawayReviewPanel";
    }

    function renderTakeawayReviewPanel(kind = "language") {
      const panel = $(reviewPanelId(kind));
      if (!panel) return;
      const due = dueTakeawayEntries(kind);
      const session = takeawayReviewSession(kind);
      const reviewed = session.reviewedIds?.size || 0;
      const activeTotal = session.ids?.length || due.length;
      const currentId = String(session.currentId || "").trim();
      const currentItem = currentId
        ? takeawayItemsForKind(kind).find((item) => item.entry_id === currentId)
        : null;
      const targetState = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      panel.classList.toggle("hidden", state.view !== (kind === "writing" ? "writingTakeawayBook" : "takeawayBook"));
      panel.classList.toggle("is-active", Boolean(session.active));
      panel.innerHTML = `
        ${session.active ? `
          <button type="button" class="icon-exit-button takeaway-review-exit" data-takeaway-review-exit="${kind}" aria-label="结束复习" title="结束复习">
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M7 7l10 10M17 7L7 17"></path>
            </svg>
          </button>
        ` : ""}
        <div class="takeaway-review-copy">
          <span>${kind === "writing" ? "Writing Bank Recall" : "Takeaway Recall"}</span>
          <strong>${session.active ? `复习中 ${reviewed}/${activeTotal}` : (due.length ? `今天到期 ${due.length} 条` : "今天没有到期提醒")}</strong>
          <small>${session.active ? (currentItem ? `当前：${escapeHtml(currentItem.chinese_text || currentItem.source_text || "已选中")}` : "点一张被遮住的卡片查看英文，再用 A / D 记录。") : `每天最多 ${TAKEAWAY_DAILY_REVIEW_LIMIT} 条，按记忆曲线推送。`}</small>
        </div>
        ${session.active ? `
          <div class="takeaway-review-panel-actions" aria-label="复习反馈">
            <button type="button" class="takeaway-review-grade is-mastered ${currentId ? "" : "needs-card"}" data-takeaway-review-panel-grade="mastered" data-takeaway-review-kind="${kind}" aria-disabled="${currentId ? "false" : "true"}">A<span>已掌握</span></button>
            <button type="button" class="takeaway-review-grade is-again ${currentId ? "" : "needs-card"}" data-takeaway-review-panel-grade="again" data-takeaway-review-kind="${kind}" aria-disabled="${currentId ? "false" : "true"}">D<span>记错了</span></button>
          </div>
        ` : `
          <button type="button" class="takeaway-review-start" data-takeaway-review-start="${kind}" ${due.length ? "" : "disabled"}>
            开始
            ${due.length ? `<span class="takeaway-review-start-badge" aria-hidden="true">${due.length}</span>` : ""}
          </button>
        `}
        <div class="takeaway-review-toast ${targetState.reviewToast ? "is-visible" : ""}" role="status">${escapeHtml(targetState.reviewToast || "")}</div>
      `;
    }

    function renderTakeawayReviewSurfaces(kind = "language") {
      updateTakeawayReviewDots();
      renderTakeawayReviewPanel(kind);
    }

    function startTakeawayReview(kind = "language") {
      const due = dueTakeawayEntries(kind);
      const target = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      target.hideEnglish = true;
      target.revealedEntryIds.clear();
      target.reviewSession = {
        active: true,
        ids: due.map((item) => item.entry_id),
        reviewedIds: new Set(),
        currentId: "",
        previousHideEnglish: Boolean(target.hideEnglish),
      };
      setTakeawayReviewToast(kind, "先点一张被遮住的卡片，露出英文后再按 A / D。");
      if (kind === "writing") {
        renderWritingTakeawayToggle();
        renderWritingTakeaways();
      } else {
        renderLanguageTakeawayToggle();
        renderLanguageTakeaways();
      }
      renderTakeawayReviewSurfaces(kind);
    }

    function endTakeawayReview(kind = "language", message = "已结束复习。") {
      const target = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      const session = takeawayReviewSession(kind);
      const previousHideEnglish = Boolean(session.previousHideEnglish);
      target.hideEnglish = previousHideEnglish;
      target.revealedEntryIds.clear();
      target.reviewSession = {
        active: false,
        ids: [],
        reviewedIds: new Set(),
        currentId: "",
        previousHideEnglish,
      };
      setTakeawayReviewToast(kind, message);
      if (kind === "writing") {
        renderWritingTakeawayToggle();
        renderWritingTakeaways();
      } else {
        renderLanguageTakeawayToggle();
        renderLanguageTakeaways();
      }
      renderTakeawayReviewSurfaces(kind);
      return true;
    }

    function isTakeawayReviewEntry(kind, entryId) {
      const session = takeawayReviewSession(kind);
      return Boolean(session.active && session.ids.includes(entryId) && !session.reviewedIds.has(entryId));
    }

    function selectTakeawayReviewEntry(kind, entryId) {
      const id = String(entryId || "").trim();
      if (!isTakeawayReviewEntry(kind, id)) return false;
      const target = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      const session = takeawayReviewSession(kind);
      if (session.currentId && session.currentId !== id) {
        setTakeawayReviewToast(kind, "先用 A / D 记录当前这张，再看下一条。");
        renderTakeawayReviewSurfaces(kind);
        return true;
      }
      session.currentId = id;
      target.revealedEntryIds.add(id);
      setTakeawayReviewToast(kind, "");
      updateTakeawayCardReveal(kind, id, { current: true });
      renderTakeawayReviewSurfaces(kind);
      return true;
    }

    function takeawayReviewFeedback(kind, entryId = "", result) {
      const session = takeawayReviewSession(kind);
      const id = String(entryId || session.currentId || "").trim();
      if (!id) {
        setTakeawayReviewToast(kind, "先点一张被遮住的卡片，露出英文后再按 A / D。");
        renderTakeawayReviewSurfaces(kind);
        return false;
      }
      const records = ensureTakeawayReviewRecords(kind);
      const record = records[id] || {};
      const currentEase = Number(record.ease || 2.5);
      const currentInterval = Number(record.interval || 0);
      const reps = Number(record.reps || 0);
      if (result === "again") {
        record.reps = 0;
        record.interval = 1;
        record.ease = Math.max(1.3, currentEase - 0.22);
        record.lapses = Number(record.lapses || 0) + 1;
        record.due = addDaysKey(1);
      } else {
        const nextReps = reps + 1;
        const nextInterval = nextReps <= 1
          ? 1
          : (nextReps === 2 ? 3 : Math.max(5, Math.round(Math.max(currentInterval, 3) * currentEase)));
        record.reps = nextReps;
        record.interval = Math.min(nextInterval, 90);
        record.ease = Math.min(3.1, currentEase + 0.08);
        record.due = addDaysKey(record.interval);
      }
      record.last = todayKey();
      records[id] = record;
      saveTakeawayReviewState(kind, records);
      const target = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      session.reviewedIds.add(id);
      session.currentId = "";
      target.revealedEntryIds.delete(id);
      if ((session.reviewedIds.size || 0) >= (session.ids.length || 0)) {
        records.__daily_batch = {
          day: todayKey(),
          ids: (session.ids || []).map((value) => String(value || "").trim()).filter(Boolean),
          completedDay: todayKey(),
          locked: true,
        };
        saveTakeawayReviewState(kind, records);
        endTakeawayReview(kind, "今日复习完成。");
        return true;
      } else {
        setTakeawayReviewToast(kind, result === "again" ? "已记为 D，明天再复习。" : "已记为 A，间隔已延长。");
      }
      if (kind === "writing") renderWritingTakeaways();
      else renderLanguageTakeaways();
      renderTakeawayReviewSurfaces(kind);
      return true;
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
          <article class="p1-topic-card" data-p1-progress="${progress}">
            <header>
              <div>
                <h3>${escapeHtml(topic.label || topic.topic)}</h3>
              </div>
              <span class="p1-topic-count">${saved}/${questions.length}</span>
            </header>
            <div class="p1-topic-progress" aria-label="完成进度 ${progress}%" data-progress="${progress}"><span style="width: ${progress}%"></span></div>
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
      const inP2Turn = state.view === "p2" && turn?.part === "p2";
      const visible = inP2Turn && Boolean(state.p2Corpus.selectedEntryId);
      const entry = visible ? currentP2CorpusEntry() : null;
      button.classList.toggle("hidden", !inP2Turn);
      button.classList.toggle("is-empty-slot", inP2Turn && !visible);
      button.classList.toggle("has-corpus", Boolean(entry));
      button.disabled = !visible;
      button.setAttribute("aria-hidden", visible ? "false" : "true");
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
      const prompt = turn?.prompt || {};
      const source = String(prompt.source || state.p3PracticeSource?.sourceType || "").trim();
      const hasCorpusTarget = Boolean(
        prompt.p3_bank_followup_id
        || prompt.p2_corpus_entry_id
        || state.p3PracticeSource?.p2CorpusEntryId
        || state.p3PracticeSource?.p3FollowUpText
        || source === "season_bank"
        || source === "bank"
        || source === "p2_report"
        || source === "p2_corpus"
      );
      const visible = state.view === "p3" && turn?.part === "p3" && hasCorpusTarget;
      button.classList.toggle("hidden", !visible);
      button.classList.toggle("has-corpus", visible);
      button.title = visible ? "查看这次 P3 关联的已保存语料" : "没有关联的 P3 追问素材";
    }

    async function p3CorpusPeekMaterialForTurn(turn = state.currentTurn) {
      const prompt = turn?.prompt || {};
      const source = String(prompt.source || state.p3PracticeSource?.sourceType || "").trim();
      const p2QuestionId = String(prompt.p2_question_id || prompt.cue_id || "").trim();
      const followupId = String(prompt.p3_bank_followup_id || prompt.followup_id || "").trim();
      if ((source === "season_bank" || source === "bank") && p2QuestionId && followupId) {
        const payload = await api(`/api/p3-bank-corpus/${encodeURIComponent(p2QuestionId)}`);
        const item = (payload.items || []).find((entry) => entry.followup_id === followupId);
        return {
          meta: payload.question || state.p3PracticeSource?.title || "题库 P3 追问",
          title: item?.followup_question || prompt.followup_question || prompt.question || "相关 P3 追问",
          body: String(item?.corpus_text || "").trim(),
          empty: "这道题库 P3 追问还没有保存语料。点击报告里的“编辑语料库”或题卡里的 P3 按钮补充。",
        };
      }
      const entryId = String(prompt.p2_corpus_entry_id || state.p3PracticeSource?.p2CorpusEntryId || "").trim();
      if ((source === "p2_report" || source === "p2_corpus" || entryId) && entryId) {
        await ensureP2CorpusLoaded();
        const entry = findP2CorpusEntry(entryId);
        return {
          meta: entry?.title || state.p3PracticeSource?.title || "P2 素材",
          title: "素材里的 P3 追问",
          body: String(entry?.p3_follow_up_text || "").trim(),
          empty: "这条 P2 素材还没有保存 P3 追问语料。打开素材卡的 P3 按钮补充后，这里会显示。",
        };
      }
      const fallback = String(state.p3PracticeSource?.p3FollowUpText || "").trim();
      return {
        meta: state.p3PracticeSource?.title || "P3 FOLLOW-UP MATERIAL",
        title: "相关 P3 追问",
        body: fallback,
        empty: "这次 P3 没有关联到已保存语料。",
      };
    }

    let p3CorpusPeekRequestSeq = 0;

    function renderP3CorpusPeekSource(source) {
      const body = $("p3CorpusPeekBody");
      if (body) body.innerHTML = `
        <section class="p2-corpus-peek-section">
          <h4>${escapeHtml(source.title || "相关 P3 追问")}</h4>
          <div>${source.body ? renderMarkdown(source.body) : `<p class="muted">${escapeHtml(source.empty || "还没有保存语料。")}</p>`}</div>
        </section>
      `;
    }

    async function openP3CorpusPeek() {
      const seq = ++p3CorpusPeekRequestSeq;
      text("p3CorpusPeekMeta", "P3 FOLLOW-UP MATERIAL");
      text("p3CorpusPeekTitle", "相关 P3 追问");
      const body = $("p3CorpusPeekBody");
      if (body) body.innerHTML = `
        <section class="p2-corpus-peek-section p2-corpus-peek-loading" aria-live="polite">
          <h4>正在加载语料…</h4>
          <div class="corpus-peek-loading-lines" aria-hidden="true">
            <span></span><span></span><span></span>
          </div>
        </section>
      `;
      $("p3CorpusPeekDialog")?.classList.remove("hidden");
      resetCorpusPeekWindowPosition("p3CorpusPeekDialog");
      try {
        const source = await p3CorpusPeekMaterialForTurn();
        if (seq !== p3CorpusPeekRequestSeq) return;
        text("p3CorpusPeekMeta", source.meta || "P3 FOLLOW-UP MATERIAL");
        text("p3CorpusPeekTitle", source.title || "相关 P3 追问");
        renderP3CorpusPeekSource(source);
      } catch (err) {
        if (seq !== p3CorpusPeekRequestSeq) return;
        const errorText = err?.message || "加载失败";
        if (body) body.innerHTML = `
          <section class="p2-corpus-peek-section">
            <h4>语料加载失败</h4>
            <p class="muted">${escapeHtml(errorText)}</p>
            <button type="button" class="corpus-peek-retry" data-p3-corpus-peek-retry>重试</button>
          </section>
        `;
      }
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
        const materialText = getCorpusMarkdownValue("p2CorpusText").trim();
        if (!materialText) return;
        if (p2Entry.is_bank_card) {
          const questionId = p2BankQuestionId(p2Entry);
          if (!questionId) return;
          sendKeepaliveJson(`/api/p2-bank-corpus/${encodeURIComponent(questionId)}`, {
            question: p2Entry.linked_question || p2Entry.question || "",
            corpus_text: materialText,
            metadata: { brainstorm_idea: $("p2CorpusBrainstormIdea")?.value || p2Entry.brainstorm_idea || "" },
            source: "p2_bank_corpus_editor",
          });
          return;
        }
        sendKeepaliveJson("/api/p2-corpus", {
          entry_id: p2Entry.entry_id || "",
          category: $("p2CorpusCategory")?.value || p2Entry.category || "person",
          title: $("p2CorpusTitle")?.value || "",
          material_text: materialText,
          p3_follow_up_text: p2Entry.p3_follow_up_text || "",
          linked_question: p2Entry.linked_question || "",
          source: "p2_corpus_editor",
        });
      }
      const p2P3Entry = state.p2Corpus.activeP3Entry;
      if (p2P3Entry && !$("#p2CorpusP3Dialog")?.classList.contains("hidden")) {
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

    async function openP1CorpusEditor(entry, options = {}) {
      if (!entry) return;
      const showReferenceAnswer = options.showReferenceAnswer === true;
      const token = ++p1CorpusEditorLoadToken;
      const storage = p1CorpusStorageEntry(entry);
      let preparedEntry = { ...entry, ...storage };
      const openedQuestionId = storage.question_id || "";
      const openedQuestion = storage.question || preparedEntry.question || preparedEntry.display_question || "";
      state.p1Corpus.activeEntry = preparedEntry;
      const initialTopic = preparedEntry.topic || preparedEntry.prompt?.topic || "";
      const initialQuestion = preparedEntry.display_question || preparedEntry.question || "";
      const initialAiAnswer = showReferenceAnswer ? (preparedEntry.last_ai_answer || preparedEntry.band7_version || preparedEntry.aiAnswer || "") : "";
      text("p1CorpusDialogTopic", initialTopic ? initialTopic.replaceAll("_", " ").toUpperCase() : "PART 1");
      text("p1CorpusDialogTitle", initialQuestion);
      setCorpusMarkdownValue("p1CorpusText", preparedEntry.corpus_text || "");
      const aiBox = $("p1CorpusAiAnswer");
      const aiWrap = aiBox?.closest(".p1-corpus-ai-box");
      aiWrap?.classList.toggle("hidden", !initialAiAnswer);
      if (aiBox) {
        aiBox.dataset.markdownSource = initialAiAnswer || "";
        aiBox.innerHTML = initialAiAnswer ? renderSpokenAnswerMarkdown(initialAiAnswer) : "";
      }
      text("p1CorpusSaveStatus", preparedEntry.corpus_text ? "" : "正在查找已保存语料...");
      $("p1CorpusDialog")?.classList.remove("hidden");
      if (!preparedEntry.corpus_text) {
        setCorpusEditorLoading("p1CorpusText", true, {
          title: "正在查找已保存语料",
          detail: "没有找到也可以直接开始编辑。",
        });
      }
      ensureCorpusMarkdownEditorReady("p1CorpusText").then((editor) => {
        if (token !== p1CorpusEditorLoadToken) return;
        if (!editor) setCorpusEditorLoading("p1CorpusText", false);
        setTimeout(() => editor?.focus?.() || $("p1CorpusText")?.focus(), 0);
      });
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
            last_ai_answer: showReferenceAnswer ? (preparedEntry.last_ai_answer || existing.last_ai_answer || "") : "",
          };
        }
      }
      if (token !== p1CorpusEditorLoadToken) return;
      if (!$("p1CorpusDialog") || $("p1CorpusDialog").classList.contains("hidden")) return;
      const activeStorage = p1CorpusStorageEntry(state.p1Corpus.activeEntry || {});
      const activeQuestionId = activeStorage.question_id || "";
      const activeQuestion = activeStorage.question || state.p1Corpus.activeEntry?.question || state.p1Corpus.activeEntry?.display_question || "";
      const sameQuestionId = openedQuestionId && activeQuestionId && openedQuestionId === activeQuestionId;
      const sameQuestionText = !openedQuestionId && !activeQuestionId && openedQuestion && activeQuestion && openedQuestion === activeQuestion;
      if (!sameQuestionId && !sameQuestionText && (openedQuestionId || activeQuestionId || openedQuestion || activeQuestion)) return;
      state.p1Corpus.activeEntry = preparedEntry;
      entry = preparedEntry;
      const topic = entry.topic || entry.prompt?.topic || "";
      const question = entry.display_question || entry.question || "";
      const aiAnswer = showReferenceAnswer ? (entry.last_ai_answer || entry.band7_version || entry.aiAnswer || "") : "";
      text("p1CorpusDialogTopic", topic ? topic.replaceAll("_", " ").toUpperCase() : "PART 1");
      text("p1CorpusDialogTitle", question);
      setCorpusEditorLoading("p1CorpusText", false);
      const currentDraft = getCorpusMarkdownValue("p1CorpusText").trim();
      if (String(entry.corpus_text || "").trim() && !currentDraft) {
        setCorpusMarkdownValue("p1CorpusText", entry.corpus_text || "");
      }
      const aiBoxFinal = $("p1CorpusAiAnswer");
      const aiWrapFinal = aiBoxFinal?.closest(".p1-corpus-ai-box");
      aiWrapFinal?.classList.toggle("hidden", !aiAnswer);
      if (aiBoxFinal) {
        aiBoxFinal.dataset.markdownSource = aiAnswer || "";
        aiBoxFinal.innerHTML = aiAnswer ? renderSpokenAnswerMarkdown(aiAnswer) : "";
      }
      text("p1CorpusSaveStatus", "");
    }

    function closeP1CorpusEditor() {
      p1CorpusEditorLoadToken += 1;
      $("p1CorpusDialog")?.classList.add("hidden");
      state.p1Corpus.activeEntry = null;
    }

    async function saveAndCloseP1CorpusEditor() {
      if (!$("p1CorpusDialog") || $("p1CorpusDialog").classList.contains("hidden")) return;
      const entry = state.p1Corpus.activeEntry;
      const corpusText = getCorpusMarkdownValue("p1CorpusText").trim();
      if (entry && !corpusText) {
        const storage = p1CorpusStorageEntry(entry);
        const localEntry = findP1CorpusEntry(storage.question_id || "");
        if (localEntry) {
          localEntry.corpus_text = "";
          localEntry.last_ai_answer = "";
          renderP1CorpusTopics();
          updateP1CorpusPeekButton(state.currentTurn);
        }
      }
      closeP1CorpusEditor();
      if (entry) saveP1CorpusEntry({ entry, corpusText, silent: true }).catch(() => null);
    }

    async function saveP1CorpusEntry(options = {}) {
      const entry = options.entry || state.p1Corpus.activeEntry;
      if (!entry) return;
      if (state.p1Corpus.saving) return;
      state.p1Corpus.saving = true;
      const button = $("saveP1CorpusBtn");
      const original = button?.textContent || "保存语料";
      const nextCorpusText = (options.corpusText ?? getCorpusMarkdownValue("p1CorpusText")).trim();
      if (button && !options.silent) {
        button.disabled = true;
        button.textContent = "保存中...";
      }
      if (!options.silent) text("p1CorpusSaveStatus", "");
      try {
        const storage = p1CorpusStorageEntry(entry);
        const payload = {
          question_id: storage.question_id,
          topic: storage.topic,
          question: storage.question,
          corpus_text: nextCorpusText,
          source: "report_or_library",
        };
        const referenceAnswer = entry.last_ai_answer || entry.band7_version || entry.aiAnswer || "";
        if (referenceAnswer) payload.last_ai_answer = referenceAnswer;
        const saved = await api("/api/p1-corpus", payload);
        if (!String(saved.corpus_text || "").trim()) {
          saved.last_ai_answer = "";
        }
        if (!options.silent) text("p1CorpusSaveStatus", `已保存 ${saved.updated_at || ""}`);
        const updated = upsertP1CorpusEntry(saved);
        const storageQuestionId = storage.question_id || saved.question_id || "";
        const localEntry = storageQuestionId ? findP1CorpusEntry(storageQuestionId) : null;
        if (localEntry) {
          localEntry.corpus_text = saved.corpus_text ?? nextCorpusText;
          localEntry.last_ai_answer = saved.last_ai_answer || "";
          localEntry.updated_at = saved.updated_at || localEntry.updated_at || "";
        }
        if (state.p1Corpus.activeEntry) {
          const activeEntry = state.p1Corpus.activeEntry || {};
          state.p1Corpus.activeEntry = {
            ...activeEntry,
            corpus_text: (updated || saved)?.corpus_text ?? nextCorpusText,
            last_ai_answer: (updated || saved)?.last_ai_answer || activeEntry.last_ai_answer || "",
            updated_at: (updated || saved)?.updated_at || activeEntry.updated_at || "",
            display_question: activeEntry.display_question || activeEntry.question || saved.question || "",
          };
        }
        renderP1CorpusTopics();
        updateP1CorpusPeekButton(state.currentTurn);
        if (options.closeOnSuccess) closeP1CorpusEditor();
      } catch (error) {
        if (String(error?.message || error || "").includes("Corpus text is empty") && !nextCorpusText) {
          const localEntry = findP1CorpusEntry(storage.question_id || "");
          if (localEntry) {
            localEntry.corpus_text = "";
            localEntry.last_ai_answer = "";
          }
          renderP1CorpusTopics();
          updateP1CorpusPeekButton(state.currentTurn);
          return;
        }
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
        if (stats) {
          stats.classList.add("is-refreshing");
          stats.setAttribute("aria-busy", "true");
        }
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
      } finally {
        if (stats) {
          stats.classList.remove("is-refreshing");
          stats.removeAttribute("aria-busy");
        }
      }
    }

    function renderP2CorpusTopics() {
      const container = $("p2CorpusTopics");
      if (!container) return;
      const categories = state.p2Corpus.categories || [];
      const currentCards = state.p2Corpus.currentPart2Cards || [];
      const P2_CAT_META = {
        place:   { label: "地点", color: "#059669", order: 1 },
        special: { label: "特殊", color: "#db2777", order: 2 },
        person:  { label: "人物", color: "#7c3aed", order: 3 },
        event:   { label: "事件", color: "#d97706", order: 4 },
        object:  { label: "物品", color: "#0284c7", order: 5 },
      };
      const normalizeSeasonalCategory = (value) => {
        const raw = String(value || "").trim();
        const aliases = {
          "地点": "place",
          "特殊": "special",
          "人物": "person",
          "事件": "event",
          "物品": "object",
        };
        return aliases[raw] || raw || "special";
      };
      const presentCats = [...new Set(currentCards.map((c) => normalizeSeasonalCategory(c.category)))].sort((a, b) => {
        const aOrder = P2_CAT_META[a]?.order ?? 99;
        const bOrder = P2_CAT_META[b]?.order ?? 99;
        return aOrder === bOrder ? a.localeCompare(b) : aOrder - bOrder;
      });
      const activeSeasonalFilter = presentCats.includes(state.p2Corpus.seasonalFilter)
        ? state.p2Corpus.seasonalFilter
        : "all";
      if (state.p2Corpus.seasonalFilter !== activeSeasonalFilter) {
        state.p2Corpus.seasonalFilter = activeSeasonalFilter;
      }
      const visibleCurrentCards = activeSeasonalFilter === "all"
        ? currentCards
        : currentCards.filter((item) => normalizeSeasonalCategory(item.category) === activeSeasonalFilter);
      if (!categories.length && !currentCards.length) {
        container.innerHTML = '<p class="muted">还没有 P2 素材分类。</p>';
        return;
      }
      const brainstormCount = currentCards.filter((item) => String(item.brainstorm_idea || "").trim()).length;
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
          <article class="p2-topic-card p2-category-entry-card" data-category="${escapeHtml(category.category || "special")}" style="--p2-material-row-count: ${Math.max(items.length, 1)}">
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
      const brainstormCardHtml = `
        <article class="p2-topic-card p2-category-entry-card p2-brainstorm-entry-card" data-category="brainstorm">
          <header>
            <h3>串题灵感 Brainstorm</h3>
            <span class="p2-topic-count">${brainstormCount}/${currentCards.length || 0}</span>
          </header>
          <button type="button" class="p2-brainstorm-open-card" data-p2-brainstorm-open>
            <span class="p2-brainstorm-card-mark" aria-hidden="true">B</span>
            <span class="p2-brainstorm-card-copy">
              <strong>按题干快速记一句灵感</strong>
              <span>适合先放关键词、人物关系、地点、经历碎片，之后再整理成正式素材。</span>
            </span>
          </button>
        </article>
      `;
      const filterBarHtml = presentCats.length > 1
        ? `<div class="p2-cat-filter-bar" role="group" aria-label="按分类筛选">
            <button type="button" class="p2-cat-filter-btn${activeSeasonalFilter === "all" ? " active" : ""}" data-cat-filter="all">全部 <span>${currentCards.length}</span></button>
            ${presentCats.map((cat) => {
              const meta = P2_CAT_META[cat] || { label: cat, color: "#64748b" };
              const cnt = currentCards.filter((c) => normalizeSeasonalCategory(c.category) === cat).length;
              return `<button type="button" class="p2-cat-filter-btn${activeSeasonalFilter === cat ? " active" : ""}" data-cat-filter="${escapeHtml(cat)}" style="--filter-color:${escapeHtml(meta.color)}">${escapeHtml(meta.label)} <span>${cnt}</span></button>`;
            }).join("")}
          </div>`
        : "";
      const cardHtml = visibleCurrentCards.map((item) => {
        const statusLabel = item.status === "new" ? "新题" : item.status === "retained" ? "保留题" : item.status || "";
        const cardId = p2BankQuestionId(item);
        const cat = normalizeSeasonalCategory(item.category);
        const cueTitle = p2CleanCueTitle(item);
        const cueHtml = p2CueQuestionHtml(item);
        return `
          <article
            class="p2-seasonal-card"
            data-p2-bank-card-id="${escapeHtml(cardId)}"
            data-p2-bank-card-title="${escapeHtml(cueTitle)}"
            data-p2-bank-card-category="${escapeHtml(cat)}"
            data-p2-bank-card-label="${escapeHtml(item.label || cat || "P2")}"
          >
            <header>
              <div>
                <span class="p2-seasonal-card-kicker">${escapeHtml(item.label || cat || "P2")}${statusLabel ? ` · ${escapeHtml(statusLabel)}` : ""}</span>
                <h3>${escapeHtml(cueTitle)}</h3>
              </div>
              <span class="p2-seasonal-card-state${item.has_material ? " is-ready" : ""}">${item.has_material ? "正文已填" : "正文待填"}</span>
            </header>
            <div class="p2-seasonal-body">
              ${cueHtml}
              <button type="button" class="p2-seasonal-practice-btn" data-p2-bank-start="${escapeHtml(cardId)}" title="直接用这道题开始 P2 练习">
                <span class="p2-seasonal-practice-icon" aria-hidden="true"></span>
                <span>直接<br>练习</span>
              </button>
            </div>
            <footer>
              <button type="button" class="p2-seasonal-action primary" data-p2-corpus-card-material="${escapeHtml(cardId)}">正文</button>
              <button type="button" class="p2-seasonal-action${item.has_p3_follow_up ? " is-ready" : ""}" data-p2-corpus-card-p3="${escapeHtml(cardId)}">P3 追问</button>
            </footer>
          </article>
        `;
      }).join("");
      container.innerHTML = `
        <section class="p2-category-entry-grid" aria-label="P2 分类入口">
          ${categoryHtml}
          ${brainstormCardHtml}
        </section>
        <section class="p2-seasonal-card-section" aria-label="当季 P2 题卡">
          <header class="p2-seasonal-section-head">
            <div>
              <span class="corpus-page-kicker">CURRENT SEASON</span>
              <h3>当季 P2 题卡</h3>
            </div>
            <span>${currentCards.length} 张题卡</span>
          </header>
          ${filterBarHtml}
          <div class="p2-seasonal-card-grid" id="p2SeasonalCardGrid">
            ${cardHtml || '<p class="muted">当前分类没有 P2 题卡。</p>'}
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
        renderTakeawayReviewSurfaces("language");
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
        renderTakeawayReviewSurfaces("language");
      } catch (error) {
        if (stats) stats.textContent = "加载失败";
        if (list) list.innerHTML = `<p class="error">${escapeHtml(error.message || String(error))}</p>`;
      }
    }

    function takeawaySourceHtml(sourceText = "") {
      const raw = String(sourceText || "").trim();
      const replacement = parseReplacementSource(raw);
      if (!replacement) {
        return `<strong class="takeaway-source takeaway-source-plain"><span>${escapeHtml(raw)}</span></strong>`;
      }
      return `
        <strong class="takeaway-source takeaway-source-replacement">
          <span class="takeaway-source-key">${escapeHtml(replacement.key)}</span>
          <span class="takeaway-source-arrow">→</span>
          <span class="takeaway-source-values">
            ${replacement.values.length
              ? replacement.values.map((value) => `<span class="takeaway-source-value">${escapeHtml(value)}</span>`).join("")
              : `<span class="takeaway-source-value">${escapeHtml(replacement.rest)}</span>`}
          </span>
        </strong>
      `;
    }

    function takeawayChineseDisplayText(item = {}) {
      const chinese = String(item.chinese_text || "").trim();
      if (chinese) return chinese;
      const replacement = parseReplacementSource(item.source_text || "");
      if (replacement?.key) return `表达替换：${replacement.key}`;
      return "未填写中文";
    }

    function parseReplacementSource(sourceText = "") {
      const raw = String(sourceText || "").trim();
      const arrowMatch = raw.match(/^(.*?)\s*(?:→|->|=>|—>)\s*(.+)$/);
      if (!arrowMatch) return null;
      const key = arrowMatch[1].trim();
      const rest = arrowMatch[2].trim();
      if (!key || !rest) return null;
      return {
        key,
        rest,
        values: splitExpressionReplacementValues(rest),
      };
    }

    function splitExpressionReplacementValues(value = "") {
      return String(value || "")
        .split(/\s*(?:\/|,|，)\s*/)
        .map((item) => item.trim())
        .filter(Boolean);
    }

    function uniqueReplacementValues(values = []) {
      const seen = new Set();
      const result = [];
      values.forEach((value) => {
        const textValue = String(value || "").trim();
        const key = textValue.toLowerCase();
        if (!textValue || seen.has(key)) return;
        seen.add(key);
        result.push(textValue);
      });
      return result;
    }

    function replacementTextForSpeech(sourceText = "") {
      const replacement = parseReplacementSource(sourceText);
      if (!replacement) return null;
      return uniqueReplacementValues([replacement.key, ...replacement.values]);
    }

    function renderTakeawayMasonry(list, cards) {
      if (!list) return;
      if (!cards.length) {
        list.innerHTML = "";
        return;
      }
      list.innerHTML = `
        <div class="language-takeaway-column" data-takeaway-column="0"></div>
        <div class="language-takeaway-column" data-takeaway-column="1"></div>
      `;
      const columns = Array.from(list.querySelectorAll(".language-takeaway-column"));
      const measure = document.createElement("div");
      measure.className = "language-takeaway-measure";
      measure.setAttribute("aria-hidden", "true");
      list.appendChild(measure);
      const nodes = cards.map((card) => {
        const template = document.createElement("template");
        template.innerHTML = card.html.trim();
        const node = template.content.firstElementChild;
        if (node) measure.appendChild(node);
        return node;
      }).filter(Boolean);
      const heights = nodes.map((node) => Math.max(1, node.getBoundingClientRect().height));
      const order = nodes.map((node, index) => ({ node, height: heights[index], index }))
        .sort((left, right) => right.height - left.height || left.index - right.index);
      const columnHeights = [0, 0];
      const gap = 10;
      order.forEach(({ node, height }) => {
        const target = columnHeights[0] <= columnHeights[1] ? 0 : 1;
        columns[target].appendChild(node);
        columnHeights[target] += height + gap;
      });
      measure.remove();
    }

    function updateTakeawayCardReveal(kind, entryId, options = {}) {
      const id = String(entryId || "").trim();
      if (!id) return;
      const list = $(kind === "writing" ? "writingTakeawayList" : "languageTakeawayList");
      const selector = kind === "writing" ? "[data-writing-takeaway-entry]" : "[data-takeaway-entry]";
      const button = Array.from(list?.querySelectorAll(selector) || []).find((candidate) => {
        return kind === "writing"
          ? candidate.dataset.writingTakeawayEntry === id
          : candidate.dataset.takeawayEntry === id;
      });
      const wrap = button?.closest(".language-takeaway-card-wrap");
      if (!wrap) return;
      wrap.classList.remove("is-concealed");
      wrap.classList.add("is-revealed");
      wrap.classList.toggle("is-review-current", Boolean(options.current));
    }

    function renderLanguageTakeaways() {
      const list = $("languageTakeawayList");
      if (!list) return;
      const items = state.languageTakeaway.items || [];
      const hiddenMode = state.languageTakeaway.hideEnglish;
      const revealed = state.languageTakeaway.revealedEntryIds;
      const session = takeawayReviewSession("language");
      const dueIds = new Set(dueTakeawayEntries("language").map((item) => item.entry_id));
      if (!items.length) {
        list.innerHTML = '<p class="muted language-book-empty">还没有摘录。平时选中单词或短语，点击“译”就可以加入这里。</p>';
        return;
      }
      const cards = items.map((item) => {
        const isReviewTarget = isTakeawayReviewEntry("language", item.entry_id);
        const isDue = dueIds.has(item.entry_id);
        const shouldConceal = (session.active ? isReviewTarget : hiddenMode) && !revealed.has(item.entry_id);
        const isCurrent = session.active && session.currentId === item.entry_id;
        return {
          html: `
        <div class="language-takeaway-card-wrap ${shouldConceal ? "is-concealed" : "is-revealed"} ${isDue ? "is-review-due" : ""} ${isReviewTarget ? "is-reviewing" : ""} ${isCurrent ? "is-review-current" : ""}">
          <button type="button" class="language-takeaway-card" data-takeaway-entry="${escapeHtml(item.entry_id)}">
            ${takeawaySourceHtml(item.source_text)}
            <span class="takeaway-chinese">${escapeHtml(takeawayChineseDisplayText(item))}</span>
          </button>
          ${corpusCardActionMenuHtml({
            menuAttr: "data-takeaway-menu",
            editAttr: "data-takeaway-edit",
            deleteAttr: "data-takeaway-delete",
            entryId: item.entry_id,
          })}
        </div>
      `,
        };
      });
      renderTakeawayMasonry(list, cards);
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
      renderTakeawayReviewSurfaces("language");
    }

    function preferredEnglishSpeechVoice() {
      const synth = window.speechSynthesis;
      const voices = typeof synth?.getVoices === "function" ? synth.getVoices() : [];
      const englishVoices = voices.filter((voice) => /^en([-_]|$)/i.test(String(voice.lang || "")));
      const localEnglishVoices = englishVoices.filter((voice) => voice.localService);
      const preferredNames = [
        "Google US English",
        "Google UK English Female",
        "Google UK English Male",
        "Google English",
        "Microsoft Jenny",
        "Microsoft Aria",
        "Microsoft Sonia",
        "Alex",
        "Karen",
        "Daniel",
        "Samantha",
      ];
      return preferredNames
        .map((name) => englishVoices.find((voice) => String(voice.name || "").toLowerCase().includes(name.toLowerCase())))
          .find(Boolean)
        || localEnglishVoices.find((voice) => voice.default)
        || englishVoices.find((voice) => voice.default)
        || localEnglishVoices[0]
        || englishVoices[0]
        || null;
    }

    function prepareSpeechQueue(synth) {
      activeSpeechUtterances.length = 0;
      if (synth?.speaking || synth?.pending) {
        suppressNextSpeechCancelError = true;
        synth.cancel();
        window.setTimeout(() => {
          suppressNextSpeechCancelError = false;
        }, 120);
      }
    }

    function applySpeechVoice(utterance, options = {}) {
      utterance.lang = options.lang || "en-US";
      utterance.rate = Number(options.rate || 0.92);
      const voice = preferredEnglishSpeechVoice();
      if (voice) utterance.voice = voice;
      return voice;
    }

    function isIgnoredSpeechError(error) {
      const value = String(error || "").toLowerCase();
      return suppressNextSpeechCancelError && (value === "canceled" || value === "cancelled" || value === "interrupted");
    }

    function speakWithBrowserTts(textValue, options = {}) {
      const value = String(textValue || "").trim();
      if (!value) return { ok: false, reason: "empty" };
      if (!window.speechSynthesis || typeof SpeechSynthesisUtterance === "undefined") {
        return { ok: false, reason: "unsupported" };
      }
      const synth = window.speechSynthesis;
      const token = ++speechSequenceToken;
      prepareSpeechQueue(synth);
      const utterance = new SpeechSynthesisUtterance(value);
      const voice = applySpeechVoice(utterance, options);
      let started = false;
      utterance.onstart = () => {
        started = true;
        options.onStart?.(voice);
      };
      utterance.onend = () => {
        const index = activeSpeechUtterances.indexOf(utterance);
        if (index >= 0) activeSpeechUtterances.splice(index, 1);
        options.onEnd?.();
      };
      utterance.onerror = (event) => {
        const index = activeSpeechUtterances.indexOf(utterance);
        if (index >= 0) activeSpeechUtterances.splice(index, 1);
        const error = event?.error || "unknown";
        if (isIgnoredSpeechError(error)) return;
        options.onError?.(error);
      };
      activeSpeechUtterances.push(utterance);

      window.setTimeout(() => {
        if (token !== speechSequenceToken) return;
        synth.speak(utterance);
      }, Number(options.startDelayMs ?? 80));
      window.setTimeout(() => {
        if (token !== speechSequenceToken || started) return;
        options.onNoStart?.(voice);
      }, Number(options.noStartDelayMs ?? 1200));
      return { ok: true, reason: "queued", voice };
    }

    function speakPhraseSequence(phrases = [], options = {}) {
      const values = uniqueReplacementValues(phrases).filter(Boolean);
      if (!values.length) return { ok: false, reason: "empty" };
      if (!window.speechSynthesis || typeof SpeechSynthesisUtterance === "undefined") {
        return { ok: false, reason: "unsupported" };
      }
      const synth = window.speechSynthesis;
      const token = ++speechSequenceToken;
      const pauseMs = Number(options.pauseMs ?? 450);
      prepareSpeechQueue(synth);
      const utterances = values.map((value) => {
        const utterance = new SpeechSynthesisUtterance(value);
        const voice = applySpeechVoice(utterance, options);
        utterance._takeawayVoice = voice;
        activeSpeechUtterances.push(utterance);
        return utterance;
      });
      const speakAt = (index) => {
        if (token !== speechSequenceToken) return;
        if (index >= utterances.length) return;
        const utterance = utterances[index];
        let started = false;
        utterance.onstart = () => {
          started = true;
          if (index === 0) options.onStart?.(utterance._takeawayVoice || null);
        };
        const continueSequence = () => {
          const utteranceIndex = activeSpeechUtterances.indexOf(utterance);
          if (utteranceIndex >= 0) activeSpeechUtterances.splice(utteranceIndex, 1);
          if (index >= utterances.length - 1) {
            options.onEnd?.();
            return;
          }
          window.setTimeout(() => speakAt(index + 1), pauseMs);
        };
        utterance.onend = continueSequence;
        utterance.onerror = (event) => {
          const error = event?.error || "unknown";
          if (!isIgnoredSpeechError(error)) options.onError?.(error);
          continueSequence();
        };
        window.setTimeout(() => {
          if (token !== speechSequenceToken) return;
          synth.speak(utterance);
        }, index === 0 ? Number(options.startDelayMs ?? 80) : 0);
        window.setTimeout(() => {
          if (token !== speechSequenceToken || started || index !== 0) return;
          options.onNoStart?.(utterance._takeawayVoice || null);
        }, Number(options.noStartDelayMs ?? 1200));
      };
      speakAt(0);
      return { ok: true, reason: "queued", voice: utterances[0]?._takeawayVoice || null };
    }

    function takeawaySpeechStatusId(kind = "language") {
      return kind === "writing" ? "writingTakeawaySpeechStatus" : "languageTakeawaySpeechStatus";
    }

    function setTakeawaySpeechStatus(kind = "language", message = "", options = {}) {
      const el = $(takeawaySpeechStatusId(kind));
      if (!el) return;
      el.textContent = message;
      el.classList.toggle("is-error", Boolean(options.error));
      if (message && options.clear !== false) {
        window.clearTimeout(el._clearTimer);
        el._clearTimer = window.setTimeout(() => {
          el.textContent = "";
          el.classList.remove("is-error");
        }, Number(options.clearDelay || 2400));
      }
    }

    function speakLanguageTakeaway(textValue, options = {}) {
      const kind = options.kind === "writing" ? "writing" : "language";
      const voiceLabel = (voice) => voice?.name ? `：${voice.name}` : "：系统默认声音";
      const callbacks = {
        onStart: (voice) => setTakeawaySpeechStatus(kind, `正在朗读${voiceLabel(voice)}`),
        onEnd: () => setTakeawaySpeechStatus(kind, ""),
        onNoStart: (voice) => setTakeawaySpeechStatus(kind, `浏览器朗读未启动${voiceLabel(voice)}，请换浏览器声音或检查标签页音量`, { error: true, clear: false }),
        onError: (error) => setTakeawaySpeechStatus(kind, `浏览器朗读失败：${error}`, { error: true, clear: false }),
      };
      const sequence = replacementTextForSpeech(textValue);
      const result = sequence
        ? speakPhraseSequence(sequence, callbacks)
        : speakWithBrowserTts(textValue, callbacks);
      if (result?.ok) {
        setTakeawaySpeechStatus(kind, `正在启动浏览器朗读${voiceLabel(result.voice)}`, { clear: false });
      } else if (result?.reason === "unsupported") {
        setTakeawaySpeechStatus(kind, "当前浏览器不支持本地朗读", { error: true, clear: false });
      } else {
        setTakeawaySpeechStatus(kind, "没有可朗读的英文", { error: true });
      }
      return result;
    }

    function revealAndSpeakLanguageTakeaway(entryId) {
      const item = (state.languageTakeaway.items || []).find((entry) => entry.entry_id === entryId);
      if (!item) return;
      state.languageTakeaway.revealedEntryIds.add(entryId);
      speakLanguageTakeaway(item.source_text, { kind: "language" });
      updateTakeawayCardReveal("language", entryId);
    }

    async function deleteLanguageTakeawayEntry(entryId) {
      if (!entryId) return;
      showConfirmDelete("确定要删除这条生词吗？", async () => {
        setTakeawaySpeechStatus("language", "正在删除…", { clear: false });
        try {
          await api(`/api/language-takeaways/${encodeURIComponent(entryId)}`, null, { method: "DELETE" });
          state.languageTakeaway.items = (state.languageTakeaway.items || []).filter((item) => item.entry_id !== entryId);
          state.languageTakeaway.revealedEntryIds.delete(entryId);
          renderLanguageTakeaways();
          text("languageTakeawayStats", `${state.languageTakeaway.items.length} 条`);
          renderTakeawayReviewSurfaces("language");
          setTakeawaySpeechStatus("language", "");
        } catch (error) {
          setTakeawaySpeechStatus("language", error.message || "删除失败", { error: true, clear: false });
        }
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
        markTakeawayEntryDueToday("language", saved.entry_id);
        renderLanguageTakeaways();
        text("languageTakeawayStats", `${state.languageTakeaway.items.length} 条`);
        renderTakeawayReviewSurfaces("language");
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
        markTakeawayEntryDueToday("writing", saved.entry_id);
        renderWritingTakeaways();
        text("writingTakeawayStats", `${state.writingTakeaway.items.length} 条`);
        renderTakeawayReviewSurfaces("writing");
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

    function defaultTakeawayContextLabel(kind) {
      return kind === "writing" ? "写作积累" : "Takeaway";
    }

    function openNewTakeawayEditor(kind = "language") {
      closeCorpusCardActionMenus();
      state.languageTakeaway.activeEdit = {
        kind,
        entryId: "",
        originalSourceText: "",
        originalChineseText: "",
      };
      text("takeawayEditDialogType", defaultTakeawayContextLabel(kind));
      text("takeawayEditDialogTitle", kind === "writing" ? "添加写作积累" : "添加 Takeaway");
      if ($("takeawayEditSource")) $("takeawayEditSource").value = "";
      if ($("takeawayEditChinese")) $("takeawayEditChinese").value = "";
      text("takeawayEditStatus", "");
      $("takeawayEditDialog")?.classList.remove("hidden");
      setTimeout(() => $("takeawayEditSource")?.focus(), 0);
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

    function expressionReplacementStorageKey(kind = "writing") {
      return `${EXPRESSION_REPLACEMENT_STORAGE_KEY}:${kind === "language" ? "language" : "writing"}`;
    }

    function normalizeExpressionReplacementItem(item, index = 0) {
      const source = String(item?.source || "").trim();
      const replacements = String(item?.replacements || "").trim();
      if (!source && !replacements) return null;
      return {
        id: String(item?.id || item?.item_id || `custom:${Date.now()}:${index}`),
        source,
        replacements,
      };
    }

    function defaultExpressionReplacements() {
      return DEFAULT_EXPRESSION_REPLACEMENTS.map((item) => ({ ...item }));
    }

    function loadLocalExpressionReplacements(kind = "writing") {
      try {
        const raw = window.localStorage?.getItem(expressionReplacementStorageKey(kind));
        const parsed = raw ? JSON.parse(raw) : null;
        if (Array.isArray(parsed)) {
          return parsed.map(normalizeExpressionReplacementItem).filter(Boolean);
        }
      } catch (_error) {
        // Ignore malformed localStorage and fall back to defaults.
      }
      return [];
    }

    function expressionReplacementItems(kind = "writing") {
      const value = kind === "language" ? "language" : "writing";
      const cached = expressionReplacementState[value]?.items;
      if (Array.isArray(cached)) return cached;
      const local = loadLocalExpressionReplacements(value);
      return local.length ? local : defaultExpressionReplacements();
    }

    function saveExpressionReplacements(kind, items) {
      const value = kind === "language" ? "language" : "writing";
      expressionReplacementState[value].items = (items || []).map(normalizeExpressionReplacementItem).filter(Boolean);
      try {
        window.localStorage?.setItem(expressionReplacementStorageKey(value), JSON.stringify(expressionReplacementState[value].items || []));
      } catch (_error) {
        // Local custom replacements are best-effort.
      }
    }

    function setExpressionReplacementStatus(message = "", options = {}) {
      const el = $("expressionReplacementStatus");
      if (!el) return;
      el.textContent = message;
      el.classList.toggle("is-error", Boolean(options.error));
    }

    function expressionReplacementEndpoint(kind = "writing", itemId = "") {
      const value = kind === "language" ? "language" : "writing";
      const base = `/api/expression-replacements/${value}`;
      return itemId ? `${base}/${encodeURIComponent(itemId)}` : base;
    }

    function mergeExpressionReplacementItems(serverItems = [], localItems = []) {
      const merged = [];
      const seen = new Set();
      defaultExpressionReplacements().forEach((item) => {
        const normalized = normalizeExpressionReplacementItem(item);
        if (!normalized || seen.has(normalized.id)) return;
        seen.add(normalized.id);
        merged.push(normalized);
      });
      serverItems.forEach((item) => {
        const normalized = normalizeExpressionReplacementItem(item);
        if (!normalized || seen.has(normalized.id)) return;
        seen.add(normalized.id);
        merged.push(normalized);
      });
      localItems.forEach((item) => {
        const normalized = normalizeExpressionReplacementItem(item);
        if (!normalized || seen.has(normalized.id)) return;
        seen.add(normalized.id);
        merged.push(normalized);
      });
      return merged;
    }

    async function migrateLocalExpressionReplacements(kind, serverItems, localItems) {
      const serverIds = new Set((serverItems || []).map((item) => item.id));
      const missing = (localItems || []).filter((item) => !serverIds.has(item.id));
      await Promise.all(missing.map((item) => api(expressionReplacementEndpoint(kind, item.id), {
        source: item.source,
        replacements: item.replacements,
      }, { method: "PUT" }).catch(() => null)));
    }

    async function syncExpressionReplacements(kind = "writing", options = {}) {
      const value = kind === "language" ? "language" : "writing";
      const stateForKind = expressionReplacementState[value];
      if (stateForKind.promise && !options.force) return stateForKind.promise;
      const localItems = loadLocalExpressionReplacements(value);
      stateForKind.loading = true;
      const promise = api(expressionReplacementEndpoint(value), null, { method: "GET" })
        .then(async (payload) => {
          const serverItems = Array.isArray(payload?.items)
            ? payload.items.map(normalizeExpressionReplacementItem).filter(Boolean)
            : [];
          if (localItems.length) await migrateLocalExpressionReplacements(value, serverItems, localItems);
          const items = mergeExpressionReplacementItems(serverItems, localItems);
          saveExpressionReplacements(value, items);
          stateForKind.synced = true;
          return items;
        })
        .catch((error) => {
          const fallback = localItems.length ? localItems : defaultExpressionReplacements();
          saveExpressionReplacements(value, fallback);
          stateForKind.synced = false;
          setExpressionReplacementStatus(`未同步，仅本地：${error.message || error}`, { error: true });
          return fallback;
        })
        .finally(() => {
          stateForKind.loading = false;
          stateForKind.promise = null;
        });
      stateForKind.promise = promise;
      return promise;
    }

    function activeExpressionReplacementKind() {
      return $("expressionReplacementDialog")?.dataset.kind || "writing";
    }

    function renderExpressionReplacements(kind = activeExpressionReplacementKind()) {
      const list = $("expressionReplacementList");
      if (!list) return;
      const value = kind === "language" ? "language" : "writing";
      const stateForKind = expressionReplacementState[value];
      const items = expressionReplacementItems(value);
      if (stateForKind.loading && !items.length) {
        list.innerHTML = '<p class="muted">正在同步表达替换...</p>';
        return;
      }
      list.innerHTML = items.map((item) => `
        <article class="expression-replacement-row" data-expression-replacement-id="${escapeHtml(item.id)}">
          <div class="expression-replacement-copy">
            <strong>${escapeHtml(item.source || "未命名表达")}</strong>
            <p>${escapeHtml(item.replacements || "还没有替换表达")}</p>
          </div>
          <button type="button" class="expression-replacement-add" data-expression-replacement-add="${escapeHtml(item.id)}" aria-label="加入${kind === "language" ? "Takeaway" : "写作积累"}">+</button>
          <button type="button" class="expression-replacement-speak" data-expression-replacement-speak="${escapeHtml(item.id)}" aria-label="朗读替换表达">
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M11 5 6 9H3v6h3l5 4V5z"></path>
              <path d="M15.5 8.5a5 5 0 0 1 0 7"></path>
              <path d="M18.5 5.5a9 9 0 0 1 0 13"></path>
            </svg>
          </button>
          <button type="button" class="expression-replacement-edit" data-expression-replacement-edit="${escapeHtml(item.id)}">编辑</button>
          <button type="button" class="expression-replacement-delete" data-expression-replacement-delete="${escapeHtml(item.id)}">删除</button>
        </article>
      `).join("");
    }

    function expressionReplacementChipHtml(value) {
      return `
        <span class="expression-replacement-chip" data-expression-replacement-chip="${escapeHtml(value)}">
          <span>${escapeHtml(value)}</span>
          <button type="button" data-expression-replacement-chip-remove="${escapeHtml(value)}" aria-label="删除 ${escapeHtml(value)}">×</button>
        </span>
      `;
    }

    function expressionReplacementChipValues(row) {
      return Array.from(row?.querySelectorAll("[data-expression-replacement-chip]") || [])
        .map((chip) => chip.dataset.expressionReplacementChip || "")
        .filter(Boolean);
    }

    function renderExpressionReplacementChips(row, values = []) {
      const box = row?.querySelector("[data-expression-replacement-chip-list]");
      if (!box) return;
      box.innerHTML = uniqueReplacementValues(values).map(expressionReplacementChipHtml).join("");
    }

    function addExpressionReplacementChip(row, rawValue = "") {
      const additions = splitExpressionReplacementValues(rawValue);
      if (!row || !additions.length) return;
      const values = uniqueReplacementValues([...expressionReplacementChipValues(row), ...additions]);
      renderExpressionReplacementChips(row, values);
      const input = row.querySelector("[data-expression-replacement-chip-input]");
      if (input) input.value = "";
    }

    function renderExpressionReplacementEditRow(item) {
      const list = $("expressionReplacementList");
      if (!list || !item) return;
      const row = list.querySelector(`[data-expression-replacement-id="${CSS.escape(item.id)}"]`);
      if (!row) return;
      row.classList.add("is-editing");
      row.innerHTML = `
        <label class="expression-replacement-field">
          <span>原表达</span>
          <input data-expression-replacement-source value="${escapeHtml(item.source || "")}" spellcheck="true">
        </label>
        <label class="expression-replacement-field">
          <span>替换表达</span>
          <div class="expression-replacement-chip-editor">
            <div class="expression-replacement-chip-list" data-expression-replacement-chip-list>
              ${uniqueReplacementValues(splitExpressionReplacementValues(item.replacements || "")).map(expressionReplacementChipHtml).join("")}
            </div>
            <input data-expression-replacement-chip-input placeholder="输入一个替换词，按 Enter 添加" spellcheck="true">
            <button type="button" class="expression-replacement-chip-add" data-expression-replacement-chip-add aria-label="添加替换表达">+</button>
          </div>
        </label>
        <div class="expression-replacement-edit-actions">
          <button type="button" class="expression-replacement-edit" data-expression-replacement-save="${escapeHtml(item.id)}">保存</button>
          <button type="button" class="expression-replacement-delete" data-expression-replacement-cancel>取消</button>
        </div>
      `;
      setTimeout(() => row.querySelector("[data-expression-replacement-source]")?.focus(), 0);
    }

    function openExpressionReplacementDialog(kind = "writing") {
      const dialog = $("expressionReplacementDialog");
      if (!dialog) return;
      dialog.dataset.kind = kind === "language" ? "language" : "writing";
      text("expressionReplacementType", kind === "language" ? "Takeaway" : "写作积累");
      setExpressionReplacementStatus("");
      renderExpressionReplacements(dialog.dataset.kind);
      dialog.classList.remove("hidden");
      syncExpressionReplacements(dialog.dataset.kind).then(() => {
        if ($("expressionReplacementDialog")?.dataset.kind === dialog.dataset.kind) {
          setExpressionReplacementStatus("");
          renderExpressionReplacements(dialog.dataset.kind);
        }
      });
    }

    function closeExpressionReplacementDialog() {
      $("expressionReplacementDialog")?.classList.add("hidden");
    }

    function addExpressionReplacement() {
      const item = {
        id: `custom:${Date.now()}`,
        source: "",
        replacements: "",
      };
      const list = $("expressionReplacementList");
      if (!list) return;
      if (list.querySelector(".expression-replacement-row.is-editing")) {
        renderExpressionReplacements(activeExpressionReplacementKind());
      }
      list.insertAdjacentHTML("afterbegin", `
        <article class="expression-replacement-row" data-expression-replacement-id="${escapeHtml(item.id)}"></article>
      `);
      setTimeout(() => {
        const row = document.querySelector(`[data-expression-replacement-id="${CSS.escape(item.id)}"]`);
        row?.scrollIntoView({ block: "nearest" });
        renderExpressionReplacementEditRow(item);
      }, 0);
    }

    function editExpressionReplacement(itemId) {
      const kind = activeExpressionReplacementKind();
      const items = expressionReplacementItems(kind);
      const item = items.find((entry) => entry.id === itemId);
      if (!item) return;
      renderExpressionReplacementEditRow(item);
    }

    async function saveExpressionReplacementEdit(itemId) {
      const kind = activeExpressionReplacementKind();
      const row = $("expressionReplacementList")?.querySelector(`[data-expression-replacement-id="${CSS.escape(itemId)}"]`);
      if (!row) return;
      const items = expressionReplacementItems(kind);
      let item = items.find((entry) => entry.id === itemId);
      if (!item) {
        item = { id: itemId, source: "", replacements: "" };
        items.unshift(item);
      }
      item.source = String(row.querySelector("[data-expression-replacement-source]")?.value || "").trim();
      const pendingInput = row.querySelector("[data-expression-replacement-chip-input]");
      if (String(pendingInput?.value || "").trim()) addExpressionReplacementChip(row, pendingInput.value);
      item.replacements = uniqueReplacementValues(expressionReplacementChipValues(row)).join(" / ");
      const cleaned = items.map(normalizeExpressionReplacementItem).filter(Boolean);
      saveExpressionReplacements(kind, cleaned);
      renderExpressionReplacements(kind);
      setExpressionReplacementStatus("正在同步...");
      try {
        const saved = await api(expressionReplacementEndpoint(kind, item.id), {
          source: item.source,
          replacements: item.replacements,
        }, { method: "PUT" });
        const current = expressionReplacementItems(kind).filter((entry) => entry.id !== item.id);
        saveExpressionReplacements(kind, [normalizeExpressionReplacementItem(saved), ...current].filter(Boolean));
        setExpressionReplacementStatus("");
        renderExpressionReplacements(kind);
      } catch (error) {
        setExpressionReplacementStatus(`未同步，仅本地：${error.message || error}`, { error: true });
      }
    }

    function speakExpressionReplacement(itemId) {
      const kind = activeExpressionReplacementKind();
      const item = expressionReplacementItems(kind).find((entry) => entry.id === itemId);
      if (!item) return;
      const voiceLabel = (voice) => voice?.name ? `：${voice.name}` : "：系统默认声音";
      const result = speakPhraseSequence([item.source, ...splitExpressionReplacementValues(item.replacements || "")], {
        onStart: (voice) => setTakeawaySpeechStatus(kind, `正在朗读${voiceLabel(voice)}`),
        onNoStart: (voice) => setTakeawaySpeechStatus(kind, `浏览器朗读未启动${voiceLabel(voice)}，请换浏览器声音或检查标签页音量`, { error: true, clear: false }),
        onError: (error) => setTakeawaySpeechStatus(kind, `浏览器朗读失败：${error}`, { error: true, clear: false }),
      });
      if (result?.ok) setTakeawaySpeechStatus(kind, `正在启动浏览器朗读${voiceLabel(result.voice)}`, { clear: false });
      else setTakeawaySpeechStatus(kind, "当前浏览器不支持本地朗读", { error: true, clear: false });
    }

    async function addExpressionReplacementToTakeaway(itemId, button = null) {
      const kind = activeExpressionReplacementKind();
      const item = expressionReplacementItems(kind).find((entry) => entry.id === itemId);
      if (!item || !String(item.source || "").trim()) return;
      const replacements = uniqueReplacementValues(splitExpressionReplacementValues(item.replacements || ""));
      if (!replacements.length) return;
      const sourceText = `${String(item.source || "").trim()} → ${replacements.join(" / ")}`;
      const chineseText = `表达替换：${String(item.source || "").trim()}`;
      const endpoint = kind === "language" ? "/api/language-takeaways" : "/api/writing-takeaways";
      const run = async () => {
        const listState = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
        const tempId = `pending-expression-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const pendingEntry = {
          entry_id: tempId,
          source_text: sourceText,
          chinese_text: chineseText,
          context_url: window.location.href,
          context_label: kind === "language" ? "表达替换" : "写作表达替换",
          source: "expression_replacement",
        };
        listState.items = [pendingEntry, ...(listState.items || [])];
        listState.loaded = true;
        refreshTakeawayList(kind, tempId);
        const saved = await api(endpoint, {
          source_text: sourceText,
          chinese_text: chineseText,
          context_url: window.location.href,
          context_label: kind === "language" ? "表达替换" : "写作表达替换",
          source: "expression_replacement",
        });
        listState.items = (listState.items || []).filter((entry) => entry.entry_id !== tempId);
        if (kind === "writing") state.writingTakeaway.revealedEntryIds.delete(tempId);
        else state.languageTakeaway.revealedEntryIds.delete(tempId);
        replaceTakeawayEntry(kind, saved);
        if (button) {
          button.classList.add("is-added");
          button.textContent = "✓";
          window.setTimeout(() => {
            button.classList.remove("is-added");
            button.innerHTML = "+";
          }, 900);
        }
      };
      const task = withPending ? withPending(button, run) : run();
      return task.catch((error) => {
        const listState = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
        listState.items = (listState.items || []).filter((entry) => !String(entry.entry_id || "").startsWith("pending-expression-"));
        refreshTakeawayList(kind);
        throw error;
      });
    }

    async function deleteExpressionReplacement(itemId) {
      const kind = activeExpressionReplacementKind();
      const items = expressionReplacementItems(kind).filter((item) => item.id !== itemId);
      saveExpressionReplacements(kind, items);
      renderExpressionReplacements(kind);
      setExpressionReplacementStatus("正在同步...");
      try {
        await api(expressionReplacementEndpoint(kind, itemId), null, { method: "DELETE" });
        setExpressionReplacementStatus("");
      } catch (error) {
        setExpressionReplacementStatus(`未同步，仅本地：${error.message || error}`, { error: true });
      }
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
      markTakeawayEntryDueToday(kind, saved.entry_id);
      refreshTakeawayList(kind, saved.entry_id);
    }

    function refreshTakeawayList(kind, revealEntryId = "") {
      if (kind === "writing") {
        if (revealEntryId) state.writingTakeaway.revealedEntryIds.add(revealEntryId);
        renderWritingTakeaways();
        text("writingTakeawayStats", `${state.writingTakeaway.items.length} 条`);
        renderTakeawayReviewSurfaces("writing");
      } else {
        if (revealEntryId) state.languageTakeaway.revealedEntryIds.add(revealEntryId);
        renderLanguageTakeaways();
        text("languageTakeawayStats", `${state.languageTakeaway.items.length} 条`);
        renderTakeawayReviewSurfaces("language");
      }
    }

    async function saveTakeawayEditor() {
      const active = state.languageTakeaway.activeEdit;
      if (!active || state.languageTakeaway.editing) return false;
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
        const endpoint = active.entryId
          ? takeawayEditEndpoint(active.kind, active.entryId)
          : (active.kind === "writing" ? "/api/writing-takeaways" : "/api/language-takeaways");
        const saved = await api(endpoint, {
          source_text: sourceText,
          chinese_text: chineseText,
          context_url: window.location.href,
          context_label: defaultTakeawayContextLabel(active.kind),
          source: active.kind === "writing" ? "writing_takeaway" : "language_takeaway",
        }, { method: active.entryId ? "PATCH" : "POST" });
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
      const targetId = String(entryId || "").trim();
      for (const category of state.p2Corpus.categories || []) {
        const found = (category.items || []).find((item) => String(item.entry_id || "").trim() === targetId);
        if (found) return { ...found, label: category.label || found.label };
      }
      const card = (state.p2Corpus.currentPart2Cards || []).find((item) => p2BankQuestionId(item) === targetId);
      if (card) return { ...card };
      return null;
    }

    function p2BankQuestionId(entry = {}) {
      return String(entry.cue_id || entry.question_id || entry.canonical_entry_id || entry.entry_id || "").trim();
    }

    function p2NormalizedCueText(value) {
      return String(value || "").replace(/\s+/g, " ").trim();
    }

    function p2CleanCueTitle(entry = {}) {
      const raw = p2NormalizedCueText(entry.cue_title || entry.title || entry.question || entry.linked_question || "");
      if (!raw) return "未命名题卡";
      const fragments = [
        ...(Array.isArray(entry.bullets) ? entry.bullets : []),
        entry.rounding,
      ]
        .map(p2NormalizedCueText)
        .filter((fragment) => fragment.length > 3)
        .sort((a, b) => b.length - a.length);
      let boundary = -1;
      fragments.forEach((fragment) => {
        const index = raw.indexOf(fragment);
        if (index > 0 && (boundary === -1 || index < boundary)) boundary = index;
      });
      const explainIndex = raw.search(/\s+And explain\b/);
      if (explainIndex > 0 && (boundary === -1 || explainIndex < boundary)) boundary = explainIndex;
      const title = boundary > 0 ? raw.slice(0, boundary).trim() : raw;
      return title || raw || "未命名题卡";
    }

    function p2BankEntryFromElement(element) {
      const card = element?.closest?.("[data-p2-bank-card-id]");
      const cardId = card?.dataset?.p2BankCardId || element?.dataset?.p2CorpusCardMaterial || element?.dataset?.p2CorpusCardP3 || "";
      return {
        entry_id: cardId,
        cue_id: cardId,
        canonical_entry_id: cardId,
        source_type: "bank",
        category: card?.dataset?.p2BankCardCategory || "special",
        label: card?.dataset?.p2BankCardLabel || "P2",
        title: card?.dataset?.p2BankCardTitle || "P2 题卡",
        cue_title: card?.dataset?.p2BankCardTitle || "P2 题卡",
      };
    }

    function p2BrainstormCueText(entry = {}) {
      return String(entry.linked_question || entry.question || p2CleanCueTitle(entry) || "").trim();
    }

    function fetchP2BankCorpusPayload(questionId) {
      const key = String(questionId || "").trim();
      if (!key) return Promise.resolve(null);
      if (!p2BankCorpusCache.has(key)) {
        p2BankCorpusCache.set(key, api(`/api/p2-bank-corpus/${encodeURIComponent(key)}`));
      }
      return p2BankCorpusCache.get(key);
    }

    function fetchP2BankP3Payload(questionId) {
      const key = String(questionId || "").trim();
      if (!key) return Promise.resolve(null);
      if (!p2BankP3Cache.has(key)) {
        p2BankP3Cache.set(key, api(`/api/p3-bank-corpus/${encodeURIComponent(key)}`));
      }
      return p2BankP3Cache.get(key);
    }

    function warmP2BankEditorPayload(entry = {}) {
      const questionId = p2BankQuestionId(entry);
      if (!questionId) return;
      fetchP2BankCorpusPayload(questionId).catch(() => {
        p2BankCorpusCache.delete(questionId);
      });
      fetchP2BankP3Payload(questionId).catch(() => {
        p2BankP3Cache.delete(questionId);
      });
    }

    function p2BrainstormRows() {
      return (state.p2Corpus.currentPart2Cards || [])
        .map((item, index) => ({ ...item, _rowIndex: index + 1 }))
        .filter((item) => p2BankQuestionId(item));
    }

    function p2BrainstormEntryForQuestion(questionId) {
      const targetId = String(questionId || "").trim();
      return (state.p2Corpus.currentPart2Cards || []).find((item) => p2BankQuestionId(item) === targetId) || {};
    }

    function p2BrainstormInputChanged(input) {
      if (!input) return false;
      const entry = p2BrainstormEntryForQuestion(input.dataset.p2BrainstormInput || "");
      return String(entry.brainstorm_idea || "").trim() !== String(input.value || "").trim();
    }

    function renderP2BrainstormRows() {
      const list = $("p2BrainstormList");
      if (!list) return;
      const rows = p2BrainstormRows();
      if (!rows.length) {
        list.innerHTML = '<p class="muted">还没有加载到 P2 题卡。</p>';
        return;
      }
      list.innerHTML = rows.map((item) => {
        const questionId = p2BankQuestionId(item);
        const idea = String(item.brainstorm_idea || "").trim();
        const stem = escapeHtml(p2CleanCueTitle(item));
        const hasCue = (Array.isArray(item.bullets) && item.bullets.length > 0) || String(item.rounding || "").trim();
        const detailHtml = hasCue ? p2CueQuestionHtml(item) : "";
        return `
          <div class="p2-brainstorm-row" data-p2-brainstorm-row="${escapeHtml(questionId)}">
            <div
              class="p2-brainstorm-left${hasCue ? " is-clickable" : ""}"
              ${hasCue ? `data-p2-brainstorm-toggle="${escapeHtml(questionId)}" role="button" tabindex="0" aria-expanded="false"` : ""}
            >
              <div class="p2-brainstorm-question">
                <span class="p2-brainstorm-index">${item._rowIndex}</span>
                <span class="p2-brainstorm-stem">${stem}</span>
              </div>
              ${hasCue ? `<div class="p2-brainstorm-cue-detail" data-p2-brainstorm-detail="${escapeHtml(questionId)}" hidden>${detailHtml}</div>` : ""}
            </div>
            <input
              class="p2-brainstorm-input"
              data-p2-brainstorm-input="${escapeHtml(questionId)}"
              type="text"
              value="${escapeHtml(idea)}"
              placeholder="一句灵感：人物 / 地点 / 经历 / 可串题角度"
              autocomplete="off"
            >
          </div>
        `;
      }).join("");
    }

    async function openP2BrainstormDialog() {
      if (!state.p2Corpus.loaded) {
        text("p2BrainstormStatus", "正在加载题卡...");
        await loadP2Corpus({ force: true });
      }
      renderP2BrainstormRows();
      const count = (state.p2Corpus.currentPart2Cards || []).filter((item) => String(item.brainstorm_idea || "").trim()).length;
      text("p2BrainstormStatus", count ? `已填写 ${count} 条灵感` : "");
      $("p2BrainstormDialog")?.classList.remove("hidden");
      setTimeout(() => $("p2BrainstormList")?.querySelector(".p2-brainstorm-input")?.focus(), 0);
    }

    function closeP2BrainstormDialog() {
      $("p2BrainstormDialog")?.classList.add("hidden");
      text("p2BrainstormStatus", "");
    }

    function updateP2BrainstormCardLocal(questionId, idea) {
      const targetId = String(questionId || "").trim();
      state.p2Corpus.currentPart2Cards = (state.p2Corpus.currentPart2Cards || []).map((item) => {
        if (p2BankQuestionId(item) !== targetId) return item;
        return {
          ...item,
          brainstorm_idea: idea,
          has_brainstorm_idea: Boolean(String(idea || "").trim()),
        };
      });
    }

    async function saveP2BrainstormIdea(questionId, idea, options = {}) {
      const targetId = String(questionId || "").trim();
      if (!targetId) return null;
      const entry = p2BrainstormEntryForQuestion(targetId);
      const nextIdea = String(idea || "").trim();
      const saved = await api(`/api/p2-bank-corpus/${encodeURIComponent(targetId)}`, {
        question: entry.linked_question || entry.question || p2BrainstormCueText(entry),
        metadata: { brainstorm_idea: nextIdea },
        source: "p2_brainstorm",
      }, { method: "PATCH" });
      updateP2BrainstormCardLocal(targetId, saved.brainstorm_idea ?? nextIdea);
      if (!options.silent) {
        const count = (state.p2Corpus.currentPart2Cards || []).filter((item) => String(item.brainstorm_idea || "").trim()).length;
        text("p2BrainstormStatus", `已保存 · ${count} 条灵感`);
        renderP2CorpusTopics();
      }
      return saved;
    }

    async function saveP2BrainstormAll(options = {}) {
      if (state.p2Corpus.brainstormSaving) return;
      const inputs = Array.from(document.querySelectorAll("[data-p2-brainstorm-input]"))
        .filter(p2BrainstormInputChanged);
      if (!inputs.length) return;
      state.p2Corpus.brainstormSaving = true;
      const button = $("saveP2BrainstormBtn");
      const original = button?.textContent || "保存灵感";
      if (button) {
        button.disabled = true;
        button.textContent = "保存中...";
      }
      text("p2BrainstormStatus", "正在保存...");
      try {
        // SQLite 不支持并发写入，逐条顺序保存避免 "database is locked" 500 错误
        for (const input of inputs) {
          await saveP2BrainstormIdea(input.dataset.p2BrainstormInput || "", input.value || "", { silent: true });
        }
        renderP2BrainstormRows();
        renderP2CorpusTopics();
        const count = (state.p2Corpus.currentPart2Cards || []).filter((item) => String(item.brainstorm_idea || "").trim()).length;
        text("p2BrainstormStatus", `已保存 ${inputs.length} 处修改 · 共 ${count} 条灵感`);
        if (options.closeOnSuccess) closeP2BrainstormDialog();
      } catch (error) {
        text("p2BrainstormStatus", error.message || String(error));
      } finally {
        state.p2Corpus.brainstormSaving = false;
        if (button) {
          button.disabled = false;
          button.textContent = original;
        }
      }
    }

    async function copyPlainTextToClipboard(value) {
      const textValue = String(value || "");
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(textValue);
          return true;
        }
      } catch (_error) {
        // Fall through to the legacy textarea path below.
      }
      try {
        const area = document.createElement("textarea");
        area.value = textValue;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(area);
        return ok;
      } catch (_error) {
        return false;
      }
    }

    // 把当前 Brainstorm 窗口导出成发给 AI 的纯文本（读 DOM 实时值，含未保存的修改和空灵感原题）。
    async function copyP2BrainstormAll() {
      const rows = Array.from(document.querySelectorAll("#p2BrainstormList .p2-brainstorm-row"));
      const blocks = [];
      rows.forEach((row) => {
        const index = (row.querySelector(".p2-brainstorm-index")?.textContent || "").trim();
        const stem = (row.querySelector(".p2-brainstorm-stem")?.textContent || "").trim();
        const idea = (row.querySelector("[data-p2-brainstorm-input]")?.value || "").trim();
        if (!stem && !idea) return;
        const heading = [index ? `${index}.` : "", stem].filter(Boolean).join(" ").trim();
        blocks.push(heading ? `${heading}\n灵感：${idea}` : `灵感：${idea}`);
      });
      if (!blocks.length) {
        text("p2BrainstormStatus", "没有可复制的题卡。");
        return;
      }
      const payload = blocks.join("\n\n");
      const ok = await copyPlainTextToClipboard(payload);
      text("p2BrainstormStatus", ok ? `已复制 ${blocks.length} 道题（含未填写灵感的原题），可直接粘贴给 AI。` : "复制失败，请手动选择文字复制。");
    }

    function isP2BankCard(entry = {}) {
      return Boolean(entry?.cue_id || entry?.canonical_entry_id || entry?.p3_follow_up_count !== undefined || entry?.source_type === "bank");
    }

    function p2CueQuestionHtml(item) {
      const bullets = (item.bullets || []).map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("");
      if (!bullets && !item.rounding) return "";
      return `
        <div class="p2-seasonal-cue">
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
      if (isP2BankCard(entry)) {
        openP2BankCorpusEditor(entry).catch((error) => {
          text("p2CorpusSaveStatus", error.message || String(error));
        });
        return;
      }
      const category = entry.category || "person";
      state.p2Corpus.activeEntry = { ...entry, category };
      $("p2CorpusDialog")?.querySelector("[data-corpus-dialog-card]")?.classList.remove("is-bank-editor");
      $("p2CorpusBrainstormField")?.classList.add("hidden");
      text("p2CorpusDialogCategory", (entry.label || category).toString());
      text("p2CorpusDialogTitle", entry.entry_id ? "编辑 P2 素材" : "新增 P2 素材");
      text("p2CorpusTextLabel", "串题素材");
      const saveButton = $("saveP2CorpusBtn");
      if (saveButton) saveButton.textContent = "保存素材";
      if ($("p2CorpusCategory")) $("p2CorpusCategory").value = category;
      if ($("p2CorpusTitle")) $("p2CorpusTitle").value = entry.title || "";
      if ($("p2CorpusBrainstormIdea")) $("p2CorpusBrainstormIdea").value = "";
      setCorpusMarkdownValue("p2CorpusText", entry.material_text || "");
      text("p2CorpusSaveStatus", "");
      $("p2CorpusDialog")?.classList.remove("hidden");
      if (!isCorpusEditorReady("p2CorpusText")) setCorpusEditorLoading("p2CorpusText", true);
      ensureCorpusMarkdownEditorReady("p2CorpusText").then((editor) => {
        if (!editor) setCorpusEditorLoading("p2CorpusText", false);
      });
      setTimeout(() => $("p2CorpusTitle")?.focus(), 0);
    }

    function showP2BankCorpusEditorLoading(entry = {}) {
      const questionId = p2BankQuestionId(entry);
      const titleText = p2CleanCueTitle(entry) || entry.title || "P2 题卡";
      state.p2Corpus.activeEntry = {
        ...entry,
        is_bank_card: true,
        entry_id: entry.entry_id || questionId,
        cue_id: entry.cue_id || questionId,
        title: titleText,
        cue_title: titleText,
      };
      $("p2CorpusDialog")?.querySelector("[data-corpus-dialog-card]")?.classList.add("is-bank-editor");
      $("p2CorpusBrainstormField")?.classList.remove("hidden");
      text("p2CorpusDialogCategory", "题库正文");
      text("p2CorpusDialogTitle", `编辑题库正文：${titleText}`);
      text("p2CorpusTextLabel", "正文");
      const saveButton = $("saveP2CorpusBtn");
      if (saveButton) {
        saveButton.textContent = "保存正文";
        saveButton.disabled = true;
      }
      if ($("p2CorpusCategory")) $("p2CorpusCategory").value = "special";
      if ($("p2CorpusTitle")) $("p2CorpusTitle").value = titleText;
      if ($("p2CorpusBrainstormIdea")) {
        $("p2CorpusBrainstormIdea").value = "";
        $("p2CorpusBrainstormIdea").disabled = true;
      }
      setCorpusMarkdownValue("p2CorpusText", "");
      setCorpusEditorLoading("p2CorpusText", true, {
        title: "正在加载题库正文",
        detail: "窗口已打开，正文马上出现。",
      });
      text("p2CorpusSaveStatus", "正在加载题库正文...");
      $("p2CorpusDialog")?.classList.remove("hidden");
    }

    async function openP2BankCorpusEditor(entry = {}) {
      const questionId = p2BankQuestionId(entry);
      if (!questionId) return;
      const token = ++p2BankCorpusLoadToken;
      showP2BankCorpusEditorLoading(entry);
      let payload;
      try {
        payload = await fetchP2BankCorpusPayload(questionId);
      } catch (error) {
        if (token === p2BankCorpusLoadToken) {
          text("p2CorpusSaveStatus", error.message || String(error));
          if ($("saveP2CorpusBtn")) $("saveP2CorpusBtn").disabled = false;
          if ($("p2CorpusBrainstormIdea")) $("p2CorpusBrainstormIdea").disabled = false;
          setCorpusEditorLoading("p2CorpusText", false);
        }
        throw error;
      }
      if (token !== p2BankCorpusLoadToken) return;
      const title = p2CleanCueTitle({ ...entry, question: payload.question });
      const activeEntry = {
        ...entry,
        ...payload,
        is_bank_card: true,
        entry_id: entry.entry_id || payload.question_id || questionId,
        cue_id: payload.question_id || entry.cue_id || questionId,
        title,
        cue_title: title,
        material_text: payload.corpus_text || entry.material_text || "",
        linked_question: payload.question || entry.linked_question || "",
        brainstorm_idea: payload.brainstorm_idea ?? entry.brainstorm_idea ?? "",
      };
      state.p2Corpus.activeEntry = activeEntry;
      $("p2CorpusDialog")?.querySelector("[data-corpus-dialog-card]")?.classList.add("is-bank-editor");
      $("p2CorpusBrainstormField")?.classList.remove("hidden");
      const titleText = activeEntry.title || activeEntry.linked_question || "P2 题卡";
      text("p2CorpusDialogCategory", "题库正文");
      text("p2CorpusDialogTitle", `编辑题库正文：${titleText}`);
      text("p2CorpusTextLabel", "正文");
      const saveButton = $("saveP2CorpusBtn");
      if (saveButton) saveButton.textContent = "保存正文";
      if ($("p2CorpusCategory")) $("p2CorpusCategory").value = "special";
      if ($("p2CorpusTitle")) $("p2CorpusTitle").value = activeEntry.title || "";
      if ($("p2CorpusBrainstormIdea")) {
        $("p2CorpusBrainstormIdea").disabled = false;
        $("p2CorpusBrainstormIdea").value = activeEntry.brainstorm_idea || "";
      }
      setCorpusEditorLoading("p2CorpusText", false);
      setCorpusMarkdownValue("p2CorpusText", activeEntry.material_text || "");
      text("p2CorpusSaveStatus", "");
      if (saveButton) saveButton.disabled = false;
      $("p2CorpusDialog")?.classList.remove("hidden");
      if (!isCorpusEditorReady("p2CorpusText")) {
        setCorpusEditorLoading("p2CorpusText", true, {
          title: "正在准备正文",
          detail: "编辑区已打开，内容马上可编辑。",
        });
      }
      ensureCorpusMarkdownEditorReady("p2CorpusText").then((editor) => {
        if (!editor) setCorpusEditorLoading("p2CorpusText", false);
        setTimeout(() => editor?.focus?.() || $("p2CorpusText")?.focus(), 0);
      });
    }

    function closeP2CorpusEditor() {
      $("p2CorpusDialog")?.classList.add("hidden");
      $("p2CorpusDialog")?.querySelector("[data-corpus-dialog-card]")?.classList.remove("is-bank-editor");
      $("p2CorpusBrainstormField")?.classList.add("hidden");
      if ($("p2CorpusBrainstormIdea")) $("p2CorpusBrainstormIdea").disabled = false;
      if ($("saveP2CorpusBtn")) $("saveP2CorpusBtn").disabled = false;
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
      const title = p2CleanCueTitle(entry);
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

    function p2BankP3MarkdownTemplate(entry = {}, items = []) {
      const title = p2CleanCueTitle(entry);
      const validItems = (Array.isArray(items) ? items : [])
        .filter((item) => String(item?.followup_question || "").trim());
      if (!validItems.length) return "";
      const lines = [
        `## ${title} 相关 P3 追问`,
        "",
      ];
      validItems.forEach((item, index) => {
        const question = String(item.followup_question || "").trim();
        const answer = String(item.corpus_text || "").trim();
        lines.push(`### ${index + 1}. ${question}`);
        lines.push("");
        lines.push(answer || "- 我的回答：");
        lines.push("");
      });
      return lines.join("\n").trim();
    }

    function updateP2CorpusP3QuestionSource(entry = {}) {
      const questions = p2OfficialFollowUpQuestions(entry);
      if ($("p2CorpusP3QuestionSourceStatus")) {
        text("p2CorpusP3QuestionSourceStatus", questions.length ? `题库追问 ${questions.length} 道` : "这张题卡暂无题库 P3 追问");
      }
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
      if (isP2BankCard(entry)) {
        openP2BankP3Editor(entry).catch((error) => {
          text("p2CorpusP3SaveStatus", error.message || String(error));
        });
        return;
      }
      if (!entry?.entry_id) return;
      const category = entry.category || "person";
      state.p2Corpus.activeP3Entry = { ...entry, category };
      state.p2Corpus.activeBankP3Entry = null;
      text("p2CorpusP3DialogCategory", (entry.label || category).toString());
      text("p2CorpusP3DialogTitle", entry.title ? `相关 P3 追问：${entry.title}` : "编辑相关 P3 追问");
      updateP2CorpusP3QuestionSource(state.p2Corpus.activeP3Entry);
      $("p2BankP3EntryList")?.classList.add("hidden");
      $("p2CorpusP3FollowUpLabel")?.classList.remove("hidden");
      document.querySelector(".p2-p3-source-tools")?.classList.remove("hidden");
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

    function syncActiveP2BankP3Draft() {
      const entry = state.p2Corpus.activeBankP3Entry;
      if (!entry) return;
      const followupId = entry.selectedFollowupId || "";
      if (!followupId) return;
      const items = Array.isArray(entry.items) ? entry.items : [];
      const target = items.find((item) => item.followup_id === followupId);
      if (!target) return;
      target.corpus_text = isCorpusEditorReady("p2CorpusP3FollowUp")
        ? getCorpusMarkdownValue("p2CorpusP3FollowUp").trim()
        : ($("p2CorpusP3FollowUp")?.value || "").trim();
    }

    function p2BankP3ItemStatus(item = {}) {
      return String(item.corpus_text || "").trim() ? "已填" : "待填";
    }

    function activeP2BankP3Item(entry = state.p2Corpus.activeBankP3Entry || {}) {
      const items = Array.isArray(entry.items) ? entry.items : [];
      if (!items.length) return null;
      const selectedId = entry.selectedFollowupId || items[0]?.followup_id || "";
      return items.find((item) => item.followup_id === selectedId) || items[0] || null;
    }

    function renderP2BankP3Entries(payload = {}) {
      const list = $("p2BankP3EntryList");
      if (!list) return;
      const activeEntry = state.p2Corpus.activeBankP3Entry || {};
      const items = payload.items || activeEntry.items || [];
      if (!items.length) {
        list.innerHTML = '<p class="p2-bank-p3-empty">这张 P2 题卡暂时没有题库 P3 追问。</p>';
        setCorpusMarkdownValue("p2CorpusP3FollowUp", "");
        return;
      }
      const selectedId = activeEntry.selectedFollowupId || items[0]?.followup_id || "";
      const selected = items.find((item) => item.followup_id === selectedId) || items[0];
      if (activeEntry) {
        activeEntry.selectedFollowupId = selected?.followup_id || "";
        activeEntry.items = items;
      }
      const listHtml = items.map((item, index) => {
        const selectedClass = item.followup_id === selected?.followup_id ? " is-active" : "";
        const savedClass = String(item.corpus_text || "").trim() ? " is-ready" : "";
        return `
          <button
            type="button"
            class="p2-bank-p3-question-button${selectedClass}${savedClass}"
            data-p2-bank-p3-select="${escapeHtml(item.followup_id)}"
          >
            <strong>Q${index + 1}</strong>
            <span>${escapeHtml(item.followup_question || "P3 追问")}</span>
            <em>${escapeHtml(p2BankP3ItemStatus(item))}</em>
          </button>
        `;
      }).join("");
      list.innerHTML = `
        <div class="p2-bank-p3-question-list" aria-label="题库 P3 追问列表">
          ${listHtml}
        </div>
        <div class="p2-bank-p3-active-question">
          <span>当前题库追问</span>
          <strong>${escapeHtml(selected?.followup_question || "P3 追问")}</strong>
        </div>
      `;
      if ($("p2CorpusP3FollowUpLabel")) $("p2CorpusP3FollowUpLabel").textContent = "回答正文";
      setCorpusMarkdownValue("p2CorpusP3FollowUp", selected?.corpus_text || "");
    }

    function showP2BankP3EditorLoading(entry = {}) {
      const questionId = p2BankQuestionId(entry);
      const title = p2CleanCueTitle(entry) || entry.title || "P2 题卡";
      state.p2Corpus.activeP3Entry = null;
      state.p2Corpus.activeBankP3Entry = {
        ...entry,
        is_bank_card: true,
        question_id: questionId,
        title,
        cue_title: title,
        items: [],
        selectedFollowupId: "",
      };
      text("p2CorpusP3DialogCategory", entry.label ? `题库素材 · ${entry.label}` : "题库素材");
      text("p2CorpusP3DialogTitle", title ? `编辑题库 P3：${title}` : "编辑题库 P3 追问");
      if ($("p2CorpusP3QuestionSourceStatus")) text("p2CorpusP3QuestionSourceStatus", "正在加载题库追问...");
      document.querySelector(".p2-p3-source-tools")?.classList.add("hidden");
      $("p2BankP3EntryList")?.classList.remove("hidden");
      if ($("p2BankP3EntryList")) {
        $("p2BankP3EntryList").innerHTML = `
          <div class="p2-bank-p3-loading">
            <span></span>
            <span></span>
            <span></span>
          </div>
        `;
      }
      $("p2CorpusP3FollowUpLabel")?.classList.remove("hidden");
      if ($("p2CorpusP3FollowUpLabel")) $("p2CorpusP3FollowUpLabel").textContent = "回答正文";
      setCorpusMarkdownValue("p2CorpusP3FollowUp", "");
      setCorpusEditorLoading("p2CorpusP3FollowUp", true, {
        title: "正在加载 P3 追问",
        detail: "窗口已打开，追问和正文马上出现。",
      });
      text("p2CorpusP3SaveStatus", "正在加载 P3 追问...");
      closeP2CorpusP3QuestionPicker();
      const saveButton = $("saveP2CorpusP3Btn");
      if (saveButton) saveButton.disabled = true;
      $("p2CorpusP3Dialog")?.classList.remove("hidden");
    }

    async function openP2BankP3Editor(entry = {}) {
      const questionId = p2BankQuestionId(entry);
      if (!questionId) return;
      const token = ++p2BankP3LoadToken;
      showP2BankP3EditorLoading(entry);
      let payload;
      try {
        payload = await fetchP2BankP3Payload(questionId);
      } catch (error) {
        if (token === p2BankP3LoadToken) {
          text("p2CorpusP3SaveStatus", error.message || String(error));
          if ($("saveP2CorpusP3Btn")) $("saveP2CorpusP3Btn").disabled = false;
          setCorpusEditorLoading("p2CorpusP3FollowUp", false);
        }
        throw error;
      }
      if (token !== p2BankP3LoadToken) return;
      const title = p2CleanCueTitle({ ...entry, question: payload.question });
      state.p2Corpus.activeP3Entry = null;
      state.p2Corpus.activeBankP3Entry = {
        ...entry,
        is_bank_card: true,
        question_id: payload.p2_question_id || questionId,
        title,
        cue_title: title,
        items: payload.items || [],
        selectedFollowupId: entry.selectedFollowupId || payload.items?.[0]?.followup_id || "",
      };
      text("p2CorpusP3DialogCategory", entry.label ? `题库素材 · ${entry.label}` : "题库素材");
      text("p2CorpusP3DialogTitle", state.p2Corpus.activeBankP3Entry.title ? `编辑题库 P3：${state.p2Corpus.activeBankP3Entry.title}` : "编辑题库 P3 追问");
      if ($("p2CorpusP3QuestionSourceStatus")) {
        text("p2CorpusP3QuestionSourceStatus", payload.count ? `题库追问 ${payload.count} 道` : "暂无题库追问");
      }
      document.querySelector(".p2-p3-source-tools")?.classList.add("hidden");
      $("p2BankP3EntryList")?.classList.remove("hidden");
      $("p2CorpusP3FollowUpLabel")?.classList.remove("hidden");
      setCorpusEditorLoading("p2CorpusP3FollowUp", false);
      renderP2BankP3Entries(payload);
      text("p2CorpusP3SaveStatus", payload.count ? "" : "这张题卡暂无题库 P3 追问。");
      closeP2CorpusP3QuestionPicker();
      if ($("saveP2CorpusP3Btn")) $("saveP2CorpusP3Btn").disabled = false;
      $("p2CorpusP3Dialog")?.classList.remove("hidden");
      if (!isCorpusEditorReady("p2CorpusP3FollowUp")) {
        setCorpusEditorLoading("p2CorpusP3FollowUp", true, {
          title: "正在准备 P3 追问",
          detail: "编辑区已打开，内容马上可编辑。",
        });
      }
      ensureCorpusMarkdownEditorReady("p2CorpusP3FollowUp").then((editor) => {
        if (!editor) setCorpusEditorLoading("p2CorpusP3FollowUp", false);
        const selected = activeP2BankP3Item(state.p2Corpus.activeBankP3Entry);
        setCorpusMarkdownValue("p2CorpusP3FollowUp", selected?.corpus_text || "");
        setTimeout(() => editor?.focus?.() || $("p2CorpusP3FollowUp")?.focus(), 0);
      });
    }

    function selectP2BankP3Question(followupId) {
      if (!followupId || !state.p2Corpus.activeBankP3Entry) return;
      syncActiveP2BankP3Draft();
      state.p2Corpus.activeBankP3Entry.selectedFollowupId = followupId;
      renderP2BankP3Entries({ items: state.p2Corpus.activeBankP3Entry.items || [] });
      setTimeout(() => {
        ensureCorpusMarkdownEditorReady("p2CorpusP3FollowUp")
          .then((editor) => editor?.focus?.() || $("p2CorpusP3FollowUp")?.focus?.())
          .catch(() => $("p2CorpusP3FollowUp")?.focus?.());
      }, 0);
    }

    function closeP2CorpusP3Editor() {
      $("p2CorpusP3Dialog")?.classList.add("hidden");
      closeP2CorpusP3QuestionPicker();
      state.p2Corpus.activeP3Entry = null;
      state.p2Corpus.activeBankP3Entry = null;
      if ($("saveP2CorpusP3Btn")) $("saveP2CorpusP3Btn").disabled = false;
      $("p2BankP3EntryList")?.classList.add("hidden");
      $("p2CorpusP3FollowUpLabel")?.classList.remove("hidden");
      if ($("p2CorpusP3FollowUpLabel")) $("p2CorpusP3FollowUpLabel").textContent = "相关 P3 追问";
      document.querySelector(".p2-p3-source-tools")?.classList.remove("hidden");
    }

    async function saveAndCloseP2CorpusEditor() {
      if (!$("p2CorpusDialog") || $("p2CorpusDialog").classList.contains("hidden")) return;
      const entry = state.p2Corpus.activeEntry || {};
      const materialText = getCorpusMarkdownValue("p2CorpusText").trim();
      if (entry.is_bank_card) {
        const brainstormIdea = $("p2CorpusBrainstormIdea")?.value || "";
        closeP2CorpusEditor();
        if (materialText || brainstormIdea.trim() !== String(entry.brainstorm_idea || "").trim()) {
          saveP2BankCorpusEntry({
            entry,
            materialText,
            brainstormIdea,
            silent: true,
          }).catch(() => null);
        }
        return;
      }
      const title = $("p2CorpusTitle")?.value || "";
      const category = $("p2CorpusCategory")?.value || entry.category || "person";
      closeP2CorpusEditor();
      if (materialText) {
        saveP2CorpusEntry({
          entry: { ...entry, category, title },
          materialText,
          silent: true,
        }).catch(() => null);
      }
    }

    async function saveAndCloseP2CorpusP3Editor() {
      if (!$("p2CorpusP3Dialog") || $("p2CorpusP3Dialog").classList.contains("hidden")) return;
      if (state.p2Corpus.activeBankP3Entry) {
        const entry = state.p2Corpus.activeBankP3Entry;
        syncActiveP2BankP3Draft();
        closeP2CorpusP3Editor();
        saveP2BankP3Entries({ entry, silent: true }).catch(() => null);
        return;
      }
      const entry = state.p2Corpus.activeP3Entry || {};
      const p3FollowUpText = getCorpusMarkdownValue("p2CorpusP3FollowUp").trim();
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

    async function saveP2BankP3Entries(options = {}) {
      const entry = options.entry || state.p2Corpus.activeBankP3Entry || {};
      const questionId = p2BankQuestionId(entry);
      if (!questionId) {
        text("p2CorpusP3SaveStatus", "缺少题卡 ID，无法保存。");
        return;
      }
      syncActiveP2BankP3Draft();
      const items = Array.isArray(entry.items) ? entry.items : [];
      if (!items.length) {
        text("p2CorpusP3SaveStatus", "没有可保存的题库追问。");
        return;
      }
      state.p2Corpus.saving = true;
      const button = $("saveP2CorpusP3Btn");
      const original = button?.textContent || "保存追问";
      if (button && !options.silent) {
        button.disabled = true;
        button.textContent = "保存中...";
      }
      if (!options.silent) text("p2CorpusP3SaveStatus", "");
      try {
        const drafts = items.map((item) => ({
          followup_id: item.followup_id || "",
          followup_question: item.followup_question || "",
          corpus_text: item.corpus_text || "",
        }));
        await Promise.all(drafts.map((draft) => api(`/api/p3-bank-corpus/item/${encodeURIComponent(draft.followup_id || "")}`, {
          p2_question_id: questionId,
          followup_question: draft.followup_question || "",
          corpus_text: draft.corpus_text || "",
          source: "p3_bank_corpus_editor",
        })));
        p2BankP3Cache.delete(questionId);
        if (!options.silent) text("p2CorpusP3SaveStatus", "已保存题库 P3 追问");
        await loadP2Corpus({ force: true });
        if (options.closeOnSuccess) closeP2CorpusP3Editor();
      } catch (error) {
        if (!options.silent) text("p2CorpusP3SaveStatus", error.message || String(error));
        if (options.closeOnError) closeP2CorpusP3Editor();
      } finally {
        state.p2Corpus.saving = false;
        if (button && !options.silent) {
          button.disabled = false;
          button.textContent = original;
        }
      }
    }

    document.addEventListener("click", (event) => {
      const brainstormOpenButton = event.target.closest("[data-p2-brainstorm-open]");
      if (brainstormOpenButton) {
        event.preventDefault();
        event.stopImmediatePropagation();
        openP2BrainstormDialog().catch((error) => {
          text("p2BrainstormStatus", error.message || String(error));
        });
        return;
      }
      // Category filter bar
      const filterBtn = event.target.closest("[data-cat-filter]");
      if (filterBtn) {
        event.preventDefault();
        state.p2Corpus.seasonalFilter = filterBtn.dataset.catFilter || "all";
        renderP2CorpusTopics();
        return;
      }
      // Direct practice button
      const practiceBtn = event.target.closest("[data-p2-bank-start]");
      if (practiceBtn) {
        event.preventDefault();
        event.stopImmediatePropagation();
        const cueId = practiceBtn.dataset.p2BankStart || "";
        if (cueId && typeof startPractice === "function") {
          state.p2Corpus.pinnedCueId = cueId;
          switchView("p2", { force: true });
          // Brief delay to let view switch settle, then auto-start practice
          window.setTimeout(() => {
            if (state.p2Corpus.pinnedCueId === cueId) {
              startPractice();
            }
          }, 120);
        }
        return;
      }
      const cardMaterialButton = event.target.closest("[data-p2-corpus-card-material]");
      if (cardMaterialButton) {
        event.preventDefault();
        event.stopImmediatePropagation();
        withPending(cardMaterialButton, () => openP2BankCorpusEditor(p2BankEntryFromElement(cardMaterialButton)), { busyText: "加载中" }).catch((error) => {
          text("p2CorpusSaveStatus", error.message || String(error));
        });
        return;
      }
      const cardP3Button = event.target.closest("[data-p2-corpus-card-p3]");
      if (cardP3Button) {
        event.preventDefault();
        event.stopImmediatePropagation();
        withPending(cardP3Button, () => openP2BankP3Editor(p2BankEntryFromElement(cardP3Button)), { busyText: "加载中" }).catch((error) => {
          text("p2CorpusP3SaveStatus", error.message || String(error));
        });
        return;
      }
      const bankP3Button = event.target.closest("[data-p2-bank-p3-select]");
      if (!bankP3Button) return;
      if ($("p2CorpusP3Dialog")?.classList.contains("hidden")) return;
      event.preventDefault();
      selectP2BankP3Question(bankP3Button.dataset.p2BankP3Select || "");
    }, true);

    $("p2BrainstormDialog")?.addEventListener("pointerdown", (event) => {
      if (event.target === $("p2BrainstormDialog")) closeP2BrainstormDialog();
    });

    $("p2BrainstormDialog")?.addEventListener("click", (event) => {
      if (event.target.closest("#p2BrainstormList")) return;
      if (event.target.closest("#saveP2BrainstormBtn")) return;
      closeP2BrainstormDetails();
    });

    let p2BrainstormActiveDetailId = "";

    function setP2BrainstormActiveDetail(questionId = "") {
      const list = $("p2BrainstormList");
      if (!list) return;
      const activeId = String(questionId || "").trim();
      p2BrainstormActiveDetailId = activeId;
      list.querySelectorAll("[data-p2-brainstorm-toggle]").forEach((trigger) => {
        const expanded = Boolean(activeId && trigger.dataset.p2BrainstormToggle === activeId);
        trigger.setAttribute("aria-expanded", String(expanded));
        trigger.classList.toggle("is-expanded", expanded);
      });
      list.querySelectorAll("[data-p2-brainstorm-detail]").forEach((detail) => {
        detail.hidden = !(activeId && detail.dataset.p2BrainstormDetail === activeId);
      });
    }

    function closeP2BrainstormDetails() {
      setP2BrainstormActiveDetail("");
    }

    function openP2BrainstormDetail(trigger) {
      if (!trigger) return;
      const qid = trigger.dataset.p2BrainstormToggle;
      const detail = $("p2BrainstormList").querySelector(`[data-p2-brainstorm-detail="${CSS.escape(qid)}"]`);
      if (!detail) return;
      if (p2BrainstormActiveDetailId === qid) {
        closeP2BrainstormDetails();
        return;
      }
      setP2BrainstormActiveDetail(qid);
    }

    $("p2BrainstormList")?.addEventListener("pointerdown", (event) => {
      if (event.target.closest("[data-p2-brainstorm-input]")) {
        closeP2BrainstormDetails();
        return;
      }
      const trigger = event.target.closest("[data-p2-brainstorm-toggle]");
      if (trigger) return;
      closeP2BrainstormDetails();
    });

    $("p2BrainstormList")?.addEventListener("click", (event) => {
      const trigger = event.target.closest("[data-p2-brainstorm-toggle]");
      if (!trigger) return;
      openP2BrainstormDetail(trigger);
    });

    $("p2BrainstormList")?.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeP2BrainstormDetails();
        return;
      }
      if (event.key !== "Enter" && event.key !== " ") return;
      const trigger = event.target.closest("[data-p2-brainstorm-toggle]");
      if (!trigger) return;
      event.preventDefault();
      openP2BrainstormDetail(trigger);
    });

    const warmP2BankCardFromElement = (element) => {
      const trigger = element?.closest?.("[data-p2-corpus-card-material], [data-p2-corpus-card-p3]");
      if (!trigger) return;
      warmP2BankEditorPayload(p2BankEntryFromElement(trigger));
    };

    document.addEventListener("pointerover", (event) => {
      warmP2BankCardFromElement(event.target);
    }, true);

    document.addEventListener("focusin", (event) => {
      warmP2BankCardFromElement(event.target);
    }, true);

    $("p2BrainstormList")?.addEventListener("focusout", (event) => {
      const input = event.target.closest("[data-p2-brainstorm-input]");
      if (!input) return;
      if (state.p2Corpus.brainstormSaving || state.p2Corpus.brainstormSuppressBlurSave) return;
      const questionId = input.dataset.p2BrainstormInput || "";
      if (!p2BrainstormInputChanged(input)) return;
      saveP2BrainstormIdea(questionId, input.value || "").catch((error) => {
        text("p2BrainstormStatus", error.message || String(error));
      });
    });

    $("saveP2BrainstormBtn")?.addEventListener("pointerdown", () => {
      state.p2Corpus.brainstormSuppressBlurSave = true;
      window.setTimeout(() => {
        state.p2Corpus.brainstormSuppressBlurSave = false;
      }, 350);
    });

    $("saveP2BrainstormBtn")?.addEventListener("click", () => {
      state.p2Corpus.brainstormSuppressBlurSave = false;
      saveP2BrainstormAll().catch((error) => {
        text("p2BrainstormStatus", error.message || String(error));
      });
    });

    $("copyP2BrainstormBtn")?.addEventListener("click", () => {
      copyP2BrainstormAll().catch((error) => {
        text("p2BrainstormStatus", error.message || String(error));
      });
    });

    $("p2BankP3EntryList")?.addEventListener("click", (event) => {
      const bankP3Button = event.target.closest("[data-p2-bank-p3-select]");
      if (!bankP3Button) return;
      event.preventDefault();
      selectP2BankP3Question(bankP3Button.dataset.p2BankP3Select || "");
    });

    async function saveP2CorpusEntry(options = {}) {
      const entry = options.entry || state.p2Corpus.activeEntry || {};
      if (state.p2Corpus.saving) return;
      if (entry.is_bank_card) {
        return saveP2BankCorpusEntry({ ...options, entry });
      }
      state.p2Corpus.saving = true;
      const button = $("saveP2CorpusBtn");
      const original = button?.textContent || "保存素材";
      const nextMaterialText = (options.materialText ?? getCorpusMarkdownValue("p2CorpusText")).trim();
      const materialDialogOpen = !$("p2CorpusDialog")?.classList.contains("hidden");
      const p3DialogOpen = !$("p2CorpusP3Dialog")?.classList.contains("hidden");
      const nextCategory = (options.category ?? (materialDialogOpen ? $("p2CorpusCategory")?.value : "")) || entry.category || "person";
      const nextTitle = (options.title ?? (materialDialogOpen ? $("p2CorpusTitle")?.value : "")) || entry.title || "";
      const nextLinkedQuestion = options.linkedQuestion ?? entry.linked_question ?? "";
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

    async function saveP2BankCorpusEntry(options = {}) {
      const entry = options.entry || state.p2Corpus.activeEntry || {};
      const questionId = p2BankQuestionId(entry);
      if (!questionId) {
        text("p2CorpusSaveStatus", "缺少题卡 ID，无法保存。");
        return;
      }
      state.p2Corpus.saving = true;
      const button = $("saveP2CorpusBtn");
      const original = button?.textContent || "保存素材";
      const nextMaterialText = (options.materialText ?? getCorpusMarkdownValue("p2CorpusText")).trim();
      const nextBrainstormIdea = options.brainstormIdea ?? ($("p2CorpusBrainstormIdea")?.value || entry.brainstorm_idea || "");
      if (button && !options.silent) {
        button.disabled = true;
        button.textContent = "保存中...";
      }
      if (!options.silent) text("p2CorpusSaveStatus", "");
      try {
        const saved = await api(`/api/p2-bank-corpus/${encodeURIComponent(questionId)}`, {
          question: entry.linked_question || entry.question || "",
          corpus_text: nextMaterialText,
          last_ai_answer: entry.last_ai_answer || "",
          metadata: { brainstorm_idea: nextBrainstormIdea },
          source: "p2_bank_corpus_editor",
        });
        updateP2BrainstormCardLocal(questionId, saved.brainstorm_idea ?? nextBrainstormIdea);
        p2BankCorpusCache.delete(questionId);
        if (!options.silent) text("p2CorpusSaveStatus", `已保存 ${saved.updated_at || ""}`);
        await loadP2Corpus({ force: true });
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
        text("p2CorpusSaveStatus", "正在删除...");
        try {
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
          text("p2CorpusSaveStatus", "");
          fetchP2CorpusPayload().then(applyP2CorpusPayload).catch(() => null);
        } catch (error) {
          text("p2CorpusSaveStatus", error.message || "删除失败");
        }
      });
    }

    async function loadWritingTakeaways() {
      const stats = $("writingTakeawayStats");
      const list = $("writingTakeawayList");
      if (state.writingTakeaway.loaded) {
        renderWritingTakeawayToggle();
        renderWritingTakeaways();
        if (stats) stats.textContent = `${state.writingTakeaway.items.length} 条`;
        renderTakeawayReviewSurfaces("writing");
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
        renderTakeawayReviewSurfaces("writing");
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
      const session = takeawayReviewSession("writing");
      const dueIds = new Set(dueTakeawayEntries("writing").map((item) => item.entry_id));
      if (!items.length) {
        list.innerHTML = '<p class="muted language-book-empty">还没有写作积累。写作文或看报告时划选表达，点击“加入写作积累”即可保存到这里。</p>';
        return;
      }
      const cards = items.map((item) => {
        const isReviewTarget = isTakeawayReviewEntry("writing", item.entry_id);
        const isDue = dueIds.has(item.entry_id);
        const shouldConceal = (session.active ? isReviewTarget : hiddenMode) && !revealed.has(item.entry_id);
        const isCurrent = session.active && session.currentId === item.entry_id;
        return {
          html: `
        <div class="language-takeaway-card-wrap ${shouldConceal ? "is-concealed" : "is-revealed"} ${isDue ? "is-review-due" : ""} ${isReviewTarget ? "is-reviewing" : ""} ${isCurrent ? "is-review-current" : ""}">
          <button type="button" class="language-takeaway-card writing-takeaway-item" data-writing-takeaway-entry="${escapeHtml(item.entry_id)}">
            ${takeawaySourceHtml(item.source_text)}
            <span class="takeaway-chinese">${escapeHtml(takeawayChineseDisplayText(item))}</span>
          </button>
          ${corpusCardActionMenuHtml({
            menuAttr: "data-writing-takeaway-menu",
            editAttr: "data-writing-takeaway-edit",
            deleteAttr: "data-writing-takeaway-delete",
            entryId: item.entry_id,
          })}
        </div>
      `,
        };
      });
      renderTakeawayMasonry(list, cards);
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
      renderTakeawayReviewSurfaces("writing");
    }

    function revealAndSpeakWritingTakeaway(entryId) {
      const item = (state.writingTakeaway.items || []).find((entry) => entry.entry_id === entryId);
      if (!item) return;
      state.writingTakeaway.revealedEntryIds.add(entryId);
      speakLanguageTakeaway(item.source_text, { kind: "writing" });
      updateTakeawayCardReveal("writing", entryId);
    }

    async function deleteWritingTakeawayEntry(entryId) {
      if (!entryId) return;
      showConfirmDelete("确定要删除这条写作积累吗？", async () => {
        const previousItems = state.writingTakeaway.items || [];
        const removed = previousItems.find((item) => item.entry_id === entryId);
        state.writingTakeaway.items = previousItems.filter((item) => item.entry_id !== entryId);
        state.writingTakeaway.revealedEntryIds.delete(entryId);
        refreshTakeawayList("writing");
        setTakeawaySpeechStatus("writing", "正在删除…", { clear: false });
        try {
          await api(`/api/writing-takeaways/${encodeURIComponent(entryId)}`, null, { method: "DELETE" });
          setTakeawaySpeechStatus("writing", "");
        } catch (error) {
          if (removed) {
            state.writingTakeaway.items = previousItems;
            refreshTakeawayList("writing");
          }
          setTakeawaySpeechStatus("writing", error.message || "删除失败", { error: true, clear: false });
        }
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
      startTakeawayReview,
      endTakeawayReview,
      selectTakeawayReviewEntry,
      takeawayReviewFeedback,
      updateTakeawayReviewDots,
      applyRemoteTakeawayReviewState,
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
      openNewTakeawayEditor,
      openTakeawayEditor,
      closeTakeawayEditor,
      saveTakeawayEditor,
      openExpressionReplacementDialog,
      closeExpressionReplacementDialog,
      addExpressionReplacement,
      editExpressionReplacement,
      saveExpressionReplacementEdit,
      speakExpressionReplacement,
      addExpressionReplacementToTakeaway,
      addExpressionReplacementChip,
      deleteExpressionReplacement,
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
      openP2BrainstormDialog,
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
