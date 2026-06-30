(function () {
  "use strict";

  function formatP2BrainstormCopyBlock({
    index = "",
    stem = "",
    bullets = [],
    rounding = "",
    fallbackRequirement = "",
    idea = "",
  } = {}) {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const normalizedIndex = normalize(index);
    const normalizedStem = normalize(stem);
    const normalizedBullets = (Array.isArray(bullets) ? bullets : []).map(normalize).filter(Boolean);
    const normalizedRounding = normalize(rounding);
    const heading = [normalizedIndex ? `${normalizedIndex}.` : "", normalizedStem].filter(Boolean).join(" ");
    const structuredRequirement = [
      normalizedBullets.map((bullet) => `- ${bullet}`).join(" "),
      normalizedRounding,
    ].filter(Boolean).join(normalizedBullets.length && normalizedRounding ? "  " : "");
    const requirement = structuredRequirement || normalize(fallbackRequirement);
    return [
      heading,
      requirement ? `    ${requirement}` : "",
      `    灵感：${normalize(idea)}`,
    ].filter(Boolean).join("\n");
  }

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
      promptGuestLogin,
      renderGuestViewNotice,
      switchView,
      startPractice,
      openCorpusWindow,
      renderP2CorpusPrepPanel,
      ensureCorpusMarkdownEditorReady,
      getCorpusMarkdownValue,
      isCorpusEditorReady,
      setCorpusEditorLoading,
      setCorpusMarkdownValue,
      ensureCsrfToken,
      getCsrfToken,
      viewCopy,
      corpusPeekWindowMargin,
      withPending,
      setAnimatedHidden,
      onCorpusSaved,
    } = options || {};

    if (!state || typeof $ !== "function" || typeof api !== "function") {
      throw new Error("Corpus/Takeaway controller requires shared app state and helpers.");
    }

    function setPeekButtonHidden(button, hidden) {
      if (typeof setAnimatedHidden === "function") {
        setAnimatedHidden(button, hidden, {
          enteringClass: "peek-button-entering",
          leavingClass: "peek-button-leaving",
          duration: 420,
        });
        return;
      }
      button?.classList.toggle("hidden", hidden);
    }

    // Guest gate for corpus features: prefer the dismissible login prompt; fall
    // back to the old hard redirect only if the host didn't inject the prompt.
    function guestGate(reason, returnView) {
      if (typeof promptGuestLogin === "function") {
        promptGuestLogin(reason, returnView ? { returnView } : {});
        return;
      }
      if (returnView) state.account.returnView = returnView;
      switchView("login", { force: true, skipAuthGate: true, authMessage: reason });
    }

    // Default seed data, in the SAME payload shapes the live render pipeline
    // consumes. Published by assets/guest-samples.js. We feed these straight
    // through applyXPayload + the real render functions so every native feature
    // (browser TTS, click-to-open, SRS review) works — no hand-drawn cards.
    function guestSamples() {
      return (typeof window !== "undefined" && window.IELTSGuestSamples) || {};
    }

    // Takeaway seed in {items, count} library shape.
    function takeawaySeedPayload(kind) {
      const seed = guestSamples();
      const items = (kind === "writing" ? seed.writingTakeaways : seed.languageTakeaways) || [];
      return { items: items.slice(), count: items.length };
    }

    // Fall back to the default takeaway seed when a real payload is empty, so
    // guests AND brand-new/emptied accounts always start with a few cards.
    function withTakeawayDefaults(kind, payload) {
      if (payload && Array.isArray(payload.items) && payload.items.length) return payload;
      return takeawaySeedPayload(kind);
    }

    function p1SeedPayload() {
      return guestSamples().p1Corpus || { topics: [] };
    }

    // Seed the single "What is your full name?" default answer into a real P1
    // payload when that question is still empty — so brand-new accounts start
    // with the same one default as guests. The bank question_id is shared across
    // users, so this is just a starter template they can keep or overwrite.
    function mergeP1FullNameDefault(payload) {
      const seedQuestion = (p1SeedPayload().topics || [])
        .flatMap((topic) => topic.questions || [])
        .find((q) => q.corpus_text);
      if (!seedQuestion) return payload;
      for (const topic of payload?.topics || []) {
        for (const question of topic.questions || []) {
          if (
            String(question.question || "").toLowerCase().includes("full name") &&
            !String(question.corpus_text || "").trim()
          ) {
            question.corpus_text = seedQuestion.corpus_text;
          }
        }
      }
      return payload;
    }

    function p2SeedPayload() {
      return guestSamples().p2Corpus || { categories: [], current_part2_cards: [] };
    }

    // On the P1/P2 素材库 screens a guest can browse the cards, but clicking any
    // content must NOT enter an editor — it pops the login dialog instead. A
    // single capturing listener on the (stable) container intercepts every child
    // click before the card's own handler runs; it stays inert after login.
    // Guest gate for takeaway edit surfaces. Reviewing the default cards (and
    // starting a review from the red dot) is allowed, but adding / editing /
    // expression-replacement windows all bounce to the login dialog.
    function guestBlockTakeawayEdit(reason) {
      if (state.account.authenticated) return false;
      if (typeof promptGuestLogin === "function") promptGuestLogin(reason, { returnView: state.view });
      return true;
    }

    function installGuestCorpusGuard(containerId, reason) {
      const el = $(containerId);
      if (!el || el.dataset.guestGuard === "1") return;
      el.dataset.guestGuard = "1";
      el.addEventListener("click", (event) => {
        if (state.account.authenticated) return;
        if (event.target === el) return; // ignore clicks on empty padding
        event.preventDefault();
        event.stopPropagation();
        if (typeof promptGuestLogin === "function") promptGuestLogin(reason, { returnView: state.view });
      }, true);
    }

    const CORPUS_PEEK_WINDOW_MARGIN = Number(corpusPeekWindowMargin) || 16;
    const EXPRESSION_REPLACEMENT_STORAGE_KEY = "ielts-expression-replacements";
    const TAKEAWAY_SRS_STORAGE_KEY = "ielts-takeaway-srs";
    const TAKEAWAY_DAILY_REVIEW_LIMIT = 20;
    // Max length of a 划词 selection that still offers the Takeaway trigger.
    // Widened 3× (was 160) so longer sentences can be captured.
    const TAKEAWAY_SELECTION_MAX_LEN = 480;
    const P1_CORPUS_CLEARED_STORAGE_KEY = "ielts-p1-corpus-cleared";
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
      ["like", "enjoy / be fond of / be into / be keen on / have a strong interest in / be drawn to / find ... appealing"],
      ["relax", "unwind / loosen up / de-stress / take a break / recharge / clear my mind / let off steam"],
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
    const takeawayPronunciationState = {
      recognition: null,
      recording: false,
      startedAt: 0,
      targetText: "",
      finalTranscript: "",
    };
    const expressionReplacementState = {
      language: { items: null, loading: false, promise: null, synced: false },
      writing: { items: null, loading: false, promise: null, synced: false },
    };
    const p2BankCorpusCache = new Map();
    const p2BankP3Cache = new Map();
    let p1CorpusEditorLoadToken = 0;
    let p1TopicModalResumeKey = "";
    let p2BankCorpusLoadToken = 0;
    let p2BankP3LoadToken = 0;

    // ── P2/P3 bank corpus: persistent SWR cache + batch prefetch ──────────────
    // Memory cache holds resolved Promises; localStorage gives stale-while-
    // revalidate across reloads; a batch endpoint warms the whole visible list.
    const P2BANK_LS_PREFIX = "p2bank_corpus_v2";
    const P3BANK_LS_PREFIX = "p2bank_p3_v2";
    const P2BANK_LS_MAX = 200;
    const P2BANK_BATCH_CHUNK = 20;
    const p2BankBatchRequested = new Set();

    function scheduleIdle(fn, delay = 0) {
      const idle = window.requestIdleCallback;
      if (idle) { idle(() => fn(), { timeout: Math.max(delay, 200) }); return; }
      window.setTimeout(fn, delay);
    }

    function canBackgroundPrefetch() {
      const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
      if (connection?.saveData) return false;
      const effectiveType = String(connection?.effectiveType || "").toLowerCase();
      return effectiveType !== "slow-2g" && effectiveType !== "2g";
    }

    // localStorage is scoped per logged-in user so one account never sees
    // another's cached corpus. Guests (no scope) skip persistence entirely.
    function p2BankUserScope() {
      const user = state.account?.user;
      return String(user?.id ?? user?.username ?? "").trim();
    }
    function p2BankLsKey(prefix, qid) {
      const scope = p2BankUserScope();
      return scope ? `${prefix}:${scope}:${qid}` : "";
    }
    function p2BankLsIndexKey(prefix) {
      const scope = p2BankUserScope();
      return scope ? `${prefix}:index:${scope}` : "";
    }
    function p2BankLsRead(prefix, qid) {
      const key = p2BankLsKey(prefix, qid);
      if (!key) return null;
      try {
        const raw = localStorage.getItem(key);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return parsed && parsed.payload ? parsed : null;
      } catch (_error) { return null; }
    }
    function p2BankLsReadAny(prefix, qid) {
      for (const id of p2EquivalentQuestionIds(qid)) {
        const cached = p2BankLsRead(prefix, id);
        if (cached) return cached;
      }
      return null;
    }
    function p2BankLsWrite(prefix, qid, payload) {
      const key = p2BankLsKey(prefix, qid);
      if (!key || !payload) return;
      try {
        localStorage.setItem(key, JSON.stringify({ payload, cached_at: Date.now() }));
        const indexKey = p2BankLsIndexKey(prefix);
        if (!indexKey) return;
        let index = [];
        try { index = JSON.parse(localStorage.getItem(indexKey) || "[]"); } catch (_error) { index = []; }
        if (!Array.isArray(index)) index = [];
        index = index.filter((entry) => entry !== qid);
        index.push(qid);
        while (index.length > P2BANK_LS_MAX) {
          const evicted = index.shift();
          try { localStorage.removeItem(p2BankLsKey(prefix, evicted)); } catch (_error) { /* ignore */ }
        }
        localStorage.setItem(indexKey, JSON.stringify(index));
      } catch (_error) { /* quota / disabled storage — ignore */ }
    }
    function p2BankLsDelete(prefix, qid) {
      const key = p2BankLsKey(prefix, qid);
      if (!key) return;
      try { localStorage.removeItem(key); } catch (_error) { /* ignore */ }
    }

    function hasP2BankP3PayloadCached(questionId) {
      ensureP2BankCacheScope();
      return p2EquivalentQuestionIds(questionId).some((id) => p2BankP3Cache.has(id) || Boolean(p2BankLsRead(P3BANK_LS_PREFIX, id)));
    }

    function notifyCorpusSaved(detail = {}) {
      if (typeof onCorpusSaved !== "function") return;
      try { onCorpusSaved(detail); } catch (_error) { /* host notification is best effort */ }
    }

    // The in-memory caches are not key-scoped, so drop them whenever the logged
    // in user changes (logout / account switch) to prevent cross-account leaks.
    // localStorage is already isolated via the user id baked into each key.
    let p2BankCacheScope = null;
    function ensureP2BankCacheScope() {
      const scope = p2BankUserScope();
      if (p2BankCacheScope === scope) return;
      p2BankCacheScope = scope;
      p2BankCorpusCache.clear();
      p2BankP3Cache.clear();
      p2BankBatchRequested.clear();
    }

    function revalidateP2BankCorpus(questionId) {
      api(`/api/p2-bank-corpus/${encodeURIComponent(questionId)}`).then((fresh) => {
        p2BankCorpusCache.set(questionId, Promise.resolve(fresh));
        p2BankLsWrite(P2BANK_LS_PREFIX, questionId, fresh);
        maybeApplyFreshP2BankCorpus(questionId, fresh);
      }).catch(() => { /* keep cached copy on failure */ });
    }
    function revalidateP2BankP3(questionId) {
      api(`/api/p3-bank-corpus/${encodeURIComponent(questionId)}`).then((fresh) => {
        p2BankP3Cache.set(questionId, Promise.resolve(fresh));
        p2BankLsWrite(P3BANK_LS_PREFIX, questionId, fresh);
        maybeApplyFreshP2BankP3(questionId, fresh);
      }).catch(() => { /* keep cached copy on failure */ });
    }

    // Background revalidation may update caches, but an already-open editor must
    // remain visually stable. Do not rewrite its fields after the dialog opens.
    function maybeApplyFreshP2BankCorpus(questionId, fresh) {
      if ($("p2CorpusDialog")?.classList.contains("hidden")) return;
      const active = state.p2Corpus.activeEntry;
      if (!active || p2BankQuestionId(active) !== questionId) return;
      const rendered = String(active.material_text || "");
      const freshText = String(fresh.corpus_text || "");
      const renderedIdea = String(active.brainstorm_idea || "");
      const freshIdea = String(fresh.brainstorm_idea || "");
      if (freshText === rendered && freshIdea === renderedIdea) return;
      text("p2CorpusSaveStatus", "\u670d\u52a1\u5668\u4e0a\u6709\u66f4\u65b0\uff0c\u5f53\u524d\u7f16\u8f91\u7a97\u53e3\u5df2\u4fdd\u6301\u4e0d\u53d8");
    }
    function maybeApplyFreshP2BankP3(questionId, fresh) {
      if ($("p2CorpusP3Dialog")?.classList.contains("hidden")) return;
      const active = state.p2Corpus.activeBankP3Entry;
      if (!active || String(active.question_id) !== String(questionId)) return;
      const signature = (items) => JSON.stringify((items || []).map((item) => [item.followup_id, item.corpus_text]));
      if (signature(active.items) === signature(fresh.items)) return;
      const selected = (active.items || []).find((item) => item.followup_id === active.selectedFollowupId);
      const current = String(getCorpusMarkdownValue("p2CorpusP3FollowUp") || "");
      if (selected && current.trim() !== String(selected.corpus_text || "").trim()) {
        text("p2CorpusP3SaveStatus", "服务器上有更新版本（未覆盖你的修改）");
        return;
      }
      active.items = fresh.items || [];
      renderP2BankP3Entries(fresh);
    }

    // Warm the whole visible list in a couple of batched round-trips.
    function prefetchP2BankList() {
      if (!canBackgroundPrefetch()) return;
      ensureP2BankCacheScope();
      const ids = [...new Set((state.p2Corpus.currentPart2Cards || []).map(p2BankQuestionId).filter(Boolean))];
      const pending = ids.filter((id) => !p2BankCorpusCache.has(id) && !p2BankBatchRequested.has(id));
      if (!pending.length) return;
      pending.forEach((id) => p2BankBatchRequested.add(id));
      for (let offset = 0; offset < pending.length; offset += P2BANK_BATCH_CHUNK) {
        const chunk = pending.slice(offset, offset + P2BANK_BATCH_CHUNK);
        api("/api/p2-bank-corpus/batch", { question_ids: chunk }).then((response) => {
          const items = (response && response.items) || {};
          Object.keys(items).forEach((qid) => {
            if (!p2BankCorpusCache.has(qid)) p2BankCorpusCache.set(qid, Promise.resolve(items[qid]));
            p2BankLsWrite(P2BANK_LS_PREFIX, qid, items[qid]);
          });
        }).catch(() => { chunk.forEach((qid) => p2BankBatchRequested.delete(qid)); });
        api("/api/p3-bank-corpus/batch", { question_ids: chunk }).then((response) => {
          const items = (response && response.items) || {};
          Object.keys(items).forEach((qid) => {
            if (!p2BankP3Cache.has(qid)) p2BankP3Cache.set(qid, Promise.resolve(items[qid]));
            p2BankLsWrite(P3BANK_LS_PREFIX, qid, items[qid]);
          });
        }).catch(() => { /* P3 falls back to per-card fetch on open */ });
      }
    }
    function prefetchVisibleP2BankP3Cards(limit = 3) {
      if (!canBackgroundPrefetch()) return;
      ensureP2BankCacheScope();
      const cards = state.p2Corpus.currentPart2Cards || [];
      const ids = [];
      for (const card of cards) {
        const id = p2BankQuestionId(card);
        if (!id || ids.includes(id) || hasP2BankP3PayloadCached(id)) continue;
        ids.push(id);
        if (ids.length >= limit) break;
      }
      ids.forEach((id, index) => {
        scheduleIdle(() => {
          fetchP2BankP3Payload(id).catch(() => {
            p2BankP3Cache.delete(id);
          });
        }, 900 + index * 180);
      });
    }
    function scheduleP2BankListPrefetch() {
      if (state.p2Corpus._bankBatchScheduled) return;
      state.p2Corpus._bankBatchScheduled = true;
      scheduleIdle(() => {
        state.p2Corpus._bankBatchScheduled = false;
        prefetchP2BankList();
        prefetchVisibleP2BankP3Cards();
      }, 700);
    }
    function scheduleP2BankP3EditorWarmup() {
      if (!state.account.authenticated) return;
      if (state.p2Corpus._p3EditorWarmScheduled) return;
      state.p2Corpus._p3EditorWarmScheduled = true;
      scheduleIdle(() => {
        state.p2Corpus._p3EditorWarmScheduled = false;
        ensureCorpusMarkdownEditorReady("p2CorpusP3FollowUp").catch(() => null);
      }, 260);
    }
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
        menu.closest(".p2-material-row, .language-takeaway-card-wrap")?.classList.remove("is-menu-open");
        menu.closest(".p2-category-entry-card, .p2-topic-card, .language-takeaway-card")?.classList.remove("is-menu-open");
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
      menu.closest(".p2-material-row, .language-takeaway-card-wrap")?.classList.toggle("is-menu-open", willOpen);
      menu.closest(".p2-category-entry-card, .p2-topic-card, .language-takeaway-card")?.classList.toggle("is-menu-open", willOpen);
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

    // Client-side mirror of the server's merge_takeaway_review_state so that a
    // stale server copy can never clobber locally-newer grades. Used when the
    // library payload brings remote review state back in (e.g. after re-login).
    function reviewRecordLast(value) {
      return value && typeof value === "object" ? String(value.last || "") : "";
    }
    function reviewRecordReps(value) {
      if (!value || typeof value !== "object") return 0;
      const n = Number(value.reps || 0);
      return Number.isFinite(n) ? n : 0;
    }
    function preferReviewRecord(current, incoming) {
      if (!current || typeof current !== "object") return incoming;
      if (!incoming || typeof incoming !== "object") return current;
      const a = reviewRecordLast(current);
      const b = reviewRecordLast(incoming);
      if (b > a) return incoming;
      if (b < a) return current;
      return reviewRecordReps(incoming) > reviewRecordReps(current) ? incoming : current;
    }
    function preferDailyBatch(current, incoming) {
      if (!current || typeof current !== "object") return incoming;
      if (!incoming || typeof incoming !== "object") return current;
      const currentDay = String(current.day || "");
      const incomingDay = String(incoming.day || "");
      if (incomingDay > currentDay) return incoming;
      if (incomingDay < currentDay) return current;
      // Same review-day: completion is monotonic — a not-yet-completed batch must
      // not un-complete a day the user already cleared.
      const currentDone = Boolean(current.completedDay) || Boolean(current.locked);
      const incomingDone = Boolean(incoming.completedDay) || Boolean(incoming.locked);
      if (currentDone && !incomingDone) return current;
      return incoming;
    }
    function mergeTakeawayReviewRecords(localState, remoteState) {
      const merged = { ...(localState || {}) };
      for (const [key, value] of Object.entries(remoteState || {})) {
        if (key === "__daily_batch") merged[key] = preferDailyBatch(merged[key], value);
        else if (key.startsWith("__")) merged[key] = value;
        else merged[key] = preferReviewRecord(merged[key], value);
      }
      return merged;
    }

    function applyRemoteTakeawayReviewState(kind, value) {
      if (!value || typeof value !== "object" || Array.isArray(value)) return;
      const local = takeawayReviewState(kind);
      if (!hasTakeawayReviewData(value)) {
        if (hasTakeawayReviewData(local)) syncTakeawayReviewState(kind, local);
        return;
      }
      // Reconcile instead of overwriting: a grade whose sync POST failed leaves a
      // newer record in localStorage than on the server, and a blind overwrite on
      // the next login would resurrect already-cleared due cards (the red dot bug).
      const merged = mergeTakeawayReviewRecords(local, value);
      try {
        window.localStorage?.setItem(takeawayReviewStorageKey(kind), JSON.stringify(merged));
      } catch (_error) {
        // Reconciled state still drives this session even if the cache write fails.
      }
      // Heal the server when local turned out to be ahead, so the next login is clean.
      if (hasTakeawayReviewData(local) && JSON.stringify(merged) !== JSON.stringify(value)) {
        syncTakeawayReviewState(kind, merged);
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
            <button type="button" class="takeaway-review-grade is-locate" data-takeaway-review-locate="${kind}" aria-label="定位最上面要练的卡片（快捷键 W）" title="定位最上面要练的卡片（W）">
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.4"></circle><path d="M12 2.5v3.6M12 17.9v3.6M2.5 12h3.6M17.9 12h3.6"></path></svg>
            </button>
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
      interruptTakeawaySpeechPlayback();
      setTakeawaySpeechStatus("language", "");
      setTakeawaySpeechStatus("writing", "");
      const due = dueTakeawayEntries(kind);
      const target = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      // Capture the reveal state BEFORE the session forces masking, so that
      // ending the review restores what the user actually had (typically
      // "show English") instead of always falling back to all-masked.
      const previousHideEnglish = Boolean(target.hideEnglish);
      target.hideEnglish = true;
      target.revealedEntryIds.clear();
      target.reviewSession = {
        active: true,
        ids: due.map((item) => item.entry_id),
        reviewedIds: new Set(),
        currentId: "",
        animatingId: "",
        pendingLocate: false,
        previousHideEnglish,
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
      // Jump straight to the first card to practise so the user isn't left
      // scrolling to find where this session starts.
      window.requestAnimationFrame(() => scrollToTakeawayReviewTarget(kind));
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
        animatingId: "",
        pendingLocate: false,
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

    function runPendingTakeawayLocate(kind = "language") {
      const session = takeawayReviewSession(kind);
      if (!session.active || !session.pendingLocate || session.animatingId) return;
      session.pendingLocate = false;
      window.requestAnimationFrame(() => triggerTakeawayLocate(kind));
    }

    function selectTakeawayReviewEntry(kind, entryId) {
      const id = String(entryId || "").trim();
      const session = takeawayReviewSession(kind);
      // Ignore taps while the current card's mascot is flying off.
      if (session.active && session.animatingId) return "blocked";
      // Only a "current" card (revealed, awaiting A / D) locks the deck: clicking
      // any *other* card is refused and we scroll back to it. With no current
      // card, clicking is free — review targets become current, everything else
      // just reveals normally (handled by the caller via the "inactive" result).
      if (session.active && session.currentId && session.currentId !== id) {
        setTakeawayReviewToast(kind, "先用 A / D 记录当前这张，再看下一条。");
        renderTakeawayReviewSurfaces(kind);
        scrollTakeawayCardIntoView(kind, session.currentId);
        return "blocked";
      }
      if (!isTakeawayReviewEntry(kind, id)) return "inactive";
      const target = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      session.currentId = id;
      target.revealedEntryIds.add(id);
      setTakeawayReviewToast(kind, "");
      updateTakeawayCardReveal(kind, id, { current: true });
      renderTakeawayReviewSurfaces(kind);
      return "selected";
    }

    function takeawayReviewFeedback(kind, entryId = "", result) {
      const session = takeawayReviewSession(kind);
      if (session.animatingId) return false; // ignore input while the mascot flies off
      const id = String(entryId || session.currentId || "").trim();
      if (!id) {
        setTakeawayReviewToast(kind, "先点一张被遮住的卡片，露出英文后再按 A / D。");
        renderTakeawayReviewSurfaces(kind);
        return false;
      }
      // Persist the SRS record immediately so the grade is never lost, then let
      // the mascot lift the card away before we re-conceal / advance the deck.
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

      const wasCurrent = session.currentId === id;
      const commit = () => commitTakeawayReviewFeedback(kind, id, result, records);
      if (wasCurrent && playTakeawayMascotFlyAway(kind, id, result, commit)) return true;
      commit();
      return true;
    }

    // Re-rendering the book rebuilds the masonry from scratch (list.innerHTML=""),
    // which resets the scroll container to the top and reshuffles cards between
    // columns — so after every A/D the view jumped. Anchor on the topmost card
    // visible in the list, run the mutation, then restore that card to the same
    // offset so the position stays put across the rebuild.
    function preserveTakeawayListScroll(kind, mutate) {
      const list = $(kind === "writing" ? "writingTakeawayList" : "languageTakeawayList");
      if (!list) { mutate(); return; }
      const listTop = list.getBoundingClientRect().top;
      let anchorId = "";
      let anchorOffset = 0;
      for (const wrap of list.querySelectorAll(".language-takeaway-card-wrap")) {
        const rect = wrap.getBoundingClientRect();
        if (rect.bottom > listTop + 1) {
          const btn = wrap.querySelector("[data-takeaway-entry], [data-writing-takeaway-entry]");
          anchorId = btn?.dataset.takeawayEntry || btn?.dataset.writingTakeawayEntry || "";
          anchorOffset = rect.top - listTop;
          break;
        }
      }
      mutate();
      if (!anchorId) return;
      const newWrap = takeawayReviewCardWrap(kind, anchorId);
      if (!newWrap) return;
      const newOffset = newWrap.getBoundingClientRect().top - list.getBoundingClientRect().top;
      list.scrollTop += (newOffset - anchorOffset);
    }

    function commitTakeawayReviewFeedback(kind, entryId, result, records) {
      const id = String(entryId || "").trim();
      const session = takeawayReviewSession(kind);
      const target = kind === "writing" ? state.writingTakeaway : state.languageTakeaway;
      session.animatingId = "";
      session.reviewedIds.add(id);
      session.currentId = "";
      if (session.locatedId === id) session.locatedId = "";
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
      }
      setTakeawayReviewToast(kind, result === "again" ? "已记为 D，明天再复习。" : "已记为 A，间隔已延长。");
      preserveTakeawayListScroll(kind, () => {
        if (kind === "writing") renderWritingTakeaways();
        else renderLanguageTakeaways();
      });
      renderTakeawayReviewSurfaces(kind);
      runPendingTakeawayLocate(kind);
      return true;
    }

    // A → green balloon, D → red. The brain grabs it and floats up out of the
    // card top, then it's gone (no return — the card is done). Returns false if
    // there's no mascot to animate so the caller can commit immediately.
    function playTakeawayMascotFlyAway(kind, entryId, result, onDone) {
      const wrap = takeawayReviewCardWrap(kind, entryId);
      const mascot = wrap?.querySelector(".takeaway-review-mascot");
      if (!mascot) return false;
      const session = takeawayReviewSession(kind);
      session.animatingId = String(entryId || "").trim();
      mascot.classList.add("is-flying", result === "again" ? "is-flying-d" : "is-flying-a");
      const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;
      if (reduceMotion) {
        onDone?.();
        return true;
      }
      let done = false;
      const finish = () => { if (done) return; done = true; onDone?.(); };
      const icon = mascot.querySelector(".tk-brain-icon");
      const onEnd = (event) => {
        if (event.animationName !== "tkBrainFlyAway") return;
        icon.removeEventListener("animationend", onEnd);
        finish();
      };
      icon?.addEventListener("animationend", onEnd);
      window.setTimeout(finish, 1200); // safety net if animationend never fires
      return true;
    }

    async function loadP1Corpus() {
      if (!state.account.authenticated) {
        // Seed the default P1 corpus through the real render path so guests see
        // the genuine topic cards; any click is intercepted to the login dialog.
        applyP1CorpusPayload(p1SeedPayload());
        installGuestCorpusGuard("p1CorpusTopics", "登录后才能保存和复用你的 P1 语料库。");
        return;
      }
      const stats = $("p1CorpusStats");
      const container = $("p1CorpusTopics");
      if (state.p1Corpus.loaded) {
        renderP1CorpusTopics();
        if (stats) stats.textContent = `${state.p1Corpus.topics.length} 个话题 · 刷新中`;
      } else {
        if (stats) stats.textContent = "加载中";
        if (container) container.innerHTML = corpusLoadingSkeletonHtml("正在加载 P1 题库...");
      }
      try {
        const payload = mergeP1FullNameDefault(await fetchP1CorpusPayload());
        applyP1CorpusPayload(payload);
      } catch (error) {
        if (container) container.innerHTML = `<p class="error">${escapeHtml(error.message || String(error))}</p>`;
        if (stats) stats.textContent = "加载失败";
      }
    }

    function corpusLoadingSkeletonHtml(label = "正在加载题库...") {
      return `
        <div class="corpus-loading-state" role="status" aria-live="polite">
          <div class="corpus-loading-copy">
            <span class="spinner" aria-hidden="true"></span>
            <span>${escapeHtml(label)}</span>
          </div>
          <div class="corpus-loading-grid" aria-hidden="true">
            ${Array.from({ length: 6 }).map(() => `
              <article class="corpus-loading-card">
                <div class="corpus-loading-card-head">
                  <span></span>
                  <em></em>
                </div>
                <strong></strong>
                <p></p>
                <p></p>
                <p></p>
              </article>
            `).join("")}
          </div>
        </div>
      `;
    }

    function renderP1CorpusTopics() {
      const container = $("p1CorpusTopics");
      if (!container) return;
      const topics = state.p1Corpus.topics || [];
      if (!topics.length) {
        container.innerHTML = '<p class="muted">还没有 P1 题目。</p>';
        return;
      }
      // Near-permanent opener topics recur every cycle: those with 9+ questions
      // (hometown, work/study, etc.) plus the "city/area you live in" topics,
      // which are long-term retained regardless of question count. Keep them, but
      // float them to the very end so the rotating seasonal topics surface first.
      // sort() is stable, so the order within each group is preserved.
      const isPermanentTopic = (topic) => {
        if ((topic.questions || []).length >= 9) return true;
        const name = String(topic.label || topic.topic || "").toLowerCase();
        return /\b(city|area)\b.*\byou live in\b/.test(name);
      };
      const orderedTopics = topics
        .map((topic, index) => ({ topic, index }))
        .sort((a, b) => {
          const aPerm = isPermanentTopic(a.topic) ? 1 : 0;
          const bPerm = isPermanentTopic(b.topic) ? 1 : 0;
          return aPerm - bPerm || a.index - b.index;
        })
        .map((entry) => entry.topic);
      // Index of the first permanent topic — a full-width divider goes right
      // before it to visually fence off the long-term retained topics.
      const firstPermanentIndex = orderedTopics.findIndex(isPermanentTopic);
      container.innerHTML = orderedTopics.map((topic, topicIndex) => {
        const divider = (topicIndex === firstPermanentIndex && firstPermanentIndex > 0)
          ? '<hr class="p1-topic-divider" aria-hidden="true">'
          : "";
        const questions = topic.questions || [];
        const saved = questions.filter((item) => item.corpus_text).length;
        const progress = questions.length ? Math.round((saved / questions.length) * 100) : 0;
        const topicKey = String(topic.topic || topic.label || "").trim();
        const opensInModal = questions.length > 6;
        return `
          ${divider}
          <article class="p1-topic-card ${opensInModal ? "is-modal-only" : "is-complete-list"}" data-p1-progress="${progress}" data-p1-topic-card="${escapeHtml(topicKey)}">
            <header>
              <div>
                <h3>${escapeHtml(topic.label || topic.topic)}</h3>
              </div>
              <span class="p1-topic-count">${saved}/${questions.length}</span>
            </header>
            <div class="p1-topic-progress" aria-label="完成进度 ${progress}%" data-progress="${progress}"><span style="width: ${progress}%"></span></div>
            <div class="p1-topic-question-list">
              ${questions.map((item, index) => `
                <button type="button" class="${item.corpus_text ? "has-corpus" : ""}" ${opensInModal ? 'tabindex="-1" aria-hidden="true"' : `data-p1-corpus-question="${escapeHtml(item.question_id)}"`}>
                  <strong>Q${index + 1}</strong>
                  <span>${escapeHtml(item.question)}</span>
                </button>
              `).join("")}
            </div>
          </article>
        `;
      }).join("");
    }

    function openP1TopicCardModal(topicKey) {
      const key = String(topicKey || "").trim();
      if (!key) return;
      const topic = (state.p1Corpus.topics || []).find((item) => String(item.topic || item.label || "").trim() === key);
      if (!topic) return;
      const questions = topic.questions || [];
      const saved = questions.filter((item) => item.corpus_text).length;
      let modal = $("p1TopicCardModal");
      if (!modal) {
        modal = document.createElement("div");
        modal.id = "p1TopicCardModal";
        document.body.appendChild(modal);
      }
      modal.className = "p1-topic-modal-backdrop";
      modal.dataset.p1TopicKey = key;
      modal.innerHTML = `
        <section class="p1-topic-modal" role="dialog" aria-modal="true" aria-label="${escapeHtml(topic.label || topic.topic || "P1 话题")}">
          <header>
            <div>
              <span>PART 1</span>
              <h3>${escapeHtml(topic.label || topic.topic)}</h3>
            </div>
            <strong>${saved}/${questions.length}</strong>
          </header>
          <div class="p1-topic-modal-list">
            ${questions.map((item, index) => `
              <button type="button" class="${item.corpus_text ? "has-corpus" : ""}" data-p1-topic-modal-question="${escapeHtml(item.question_id)}">
                <strong>Q${index + 1}</strong>
                <span>${escapeHtml(item.question)}</span>
              </button>
            `).join("")}
          </div>
        </section>
      `;
      modal.classList.remove("hidden");
      modal.addEventListener("click", handleP1TopicModalClick);
      document.addEventListener("keydown", handleP1TopicModalKeydown);
    }

    function closeP1TopicCardModal() {
      const modal = $("p1TopicCardModal");
      if (!modal) return;
      modal.classList.add("hidden");
      modal.removeEventListener("click", handleP1TopicModalClick);
      document.removeEventListener("keydown", handleP1TopicModalKeydown);
    }

    function handleP1TopicModalClick(event) {
      if (event.target === event.currentTarget || event.target.closest("[data-p1-topic-modal-close]")) {
        closeP1TopicCardModal();
        return;
      }
      const button = event.target.closest("[data-p1-topic-modal-question]");
      if (!button) return;
      const topicKey = String(event.currentTarget?.dataset?.p1TopicKey || "").trim();
      closeP1TopicCardModal();
      p1TopicModalResumeKey = topicKey;
      openP1CorpusEditor(findP1CorpusEntry(button.dataset.p1TopicModalQuestion || ""));
    }

    function handleP1TopicModalKeydown(event) {
      if (event.key === "Escape") closeP1TopicCardModal();
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

    function p1CorpusClearedStorageKey() {
      const userKey = state.account?.user?.id || state.account?.user?.username || "anonymous";
      return `${P1_CORPUS_CLEARED_STORAGE_KEY}:${userKey}`;
    }

    function loadP1CorpusClearedIds() {
      try {
        const raw = window.localStorage?.getItem(p1CorpusClearedStorageKey());
        const ids = JSON.parse(raw || "[]");
        return new Set(Array.isArray(ids) ? ids.map((id) => String(id || "").trim()).filter(Boolean) : []);
      } catch (_error) {
        return new Set();
      }
    }

    function persistP1CorpusClearedIds() {
      try {
        window.localStorage?.setItem(
          p1CorpusClearedStorageKey(),
          JSON.stringify(Array.from(state.p1Corpus.clearedQuestionIds || [])),
        );
      } catch (_error) {
        // Local tombstones are a best-effort guard against stale server reads.
      }
    }

    function hydrateP1CorpusClearedIds() {
      if (state.p1Corpus.clearedQuestionIds?.size) return;
      state.p1Corpus.clearedQuestionIds = loadP1CorpusClearedIds();
    }

    function markP1CorpusEntryCleared(entry) {
      hydrateP1CorpusClearedIds();
      const storage = p1CorpusStorageEntry(entry || {});
      const ids = p1CorpusEntryIds({
        question_id: storage.question_id,
        storage_question_id: entry?.storage_question_id,
        legacy_question_id: entry?.legacy_question_id,
      });
      ids.forEach((id) => state.p1Corpus.clearedQuestionIds?.add?.(id));
      persistP1CorpusClearedIds();
      const localEntry = ids.map((id) => findP1CorpusEntry(id)).find(Boolean);
      if (localEntry) {
        localEntry.corpus_text = "";
        localEntry.last_ai_answer = "";
        localEntry.updated_at = "";
      }
      if (state.p1Corpus.activeEntry) {
        state.p1Corpus.activeEntry = {
          ...state.p1Corpus.activeEntry,
          corpus_text: "",
          last_ai_answer: "",
          band7_version: "",
          aiAnswer: "",
        };
      }
      renderP1CorpusTopics();
      updateP1CorpusPeekButton(state.currentTurn);
      // Same generation bump as the save path: a clear is also a local mutation
      // that must win against any GET snapshotted before it.
      state.p1Corpus.mutationSeq = (state.p1Corpus.mutationSeq || 0) + 1;
      state.p1Corpus.loadingPromise = null;
    }

    function applyP1CorpusDraftLocal(entry, corpusText) {
      const textValue = String(corpusText || "").trim();
      if (!entry || !textValue) return null;
      hydrateP1CorpusClearedIds();
      const storage = p1CorpusStorageEntry(entry);
      const ids = p1CorpusEntryIds({
        question_id: storage.question_id,
        storage_question_id: entry.storage_question_id,
        legacy_question_id: entry.legacy_question_id,
      });
      ids.forEach((id) => state.p1Corpus.clearedQuestionIds?.delete?.(id));
      persistP1CorpusClearedIds();
      const localEntry =
        ids.map((id) => findP1CorpusEntry(id)).find(Boolean)
        || findExactP1CorpusEntryForTarget(entry);
      if (!localEntry) return null;
      localEntry.corpus_text = textValue;
      localEntry.last_ai_answer = entry.last_ai_answer || entry.band7_version || entry.aiAnswer || localEntry.last_ai_answer || "";
      localEntry.updated_at = localEntry.updated_at || "";
      if (state.p1Corpus.activeEntry) {
        state.p1Corpus.activeEntry = {
          ...state.p1Corpus.activeEntry,
          corpus_text: textValue,
          last_ai_answer: localEntry.last_ai_answer,
        };
      }
      state.p1Corpus.mutationSeq = (state.p1Corpus.mutationSeq || 0) + 1;
      state.p1Corpus.loadingPromise = null;
      renderP1CorpusTopics();
      const topicModal = $("p1TopicCardModal");
      if (topicModal && !topicModal.classList.contains("hidden") && topicModal.dataset.p1TopicKey) {
        openP1TopicCardModal(topicModal.dataset.p1TopicKey);
      }
      updateP1CorpusPeekButton(state.currentTurn);
      return localEntry;
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
      setPeekButtonHidden(button, !target);
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

    // The bank question id for the current P2 turn (mirrors p2CorpusTargetForTurn
    // in app.js). Used to load 随题目绑定的「题库正文」 — independent of any linked
    // 串题素材.
    function p2TurnBankQuestionId(turn = state.currentTurn) {
      if (turn?.part !== "p2") return "";
      const prompt = turn.prompt || {};
      const cue = turn.cue_card || state.attempt?.cue_card || {};
      return String(
        cue.cue_id
        || cue.question_id
        || cue.canonical_entry_id
        || prompt.p2_question_id
        || prompt.cue_id
        || prompt.question_id
        || ""
      ).trim();
    }

    function updateP2CorpusPeekButton(turn = state.currentTurn) {
      const inP2Turn = state.view === "p2" && turn?.part === "p2";

      // Lightbulb → 随题目绑定的「题库正文」(串题灵感 + 正文). Shown only once we
      // confirm the learner actually prepared a body for this question.
      const questionId = inP2Turn ? p2TurnBankQuestionId(turn) : "";
      state.p2Corpus.activeTurnQuestionId = questionId;
      const bankButton = $("peekP2CorpusBtn");
      if (bankButton) {
        bankButton.title = "我准备的本题正文";
        bankButton.setAttribute("aria-label", "查看我为这道题准备的题库正文");
        if (!inP2Turn || !questionId) {
          setPeekButtonHidden(bankButton, true);
          bankButton.classList.remove("has-corpus", "is-empty-slot", "is-loading-slot");
          bankButton.disabled = true;
          bankButton.setAttribute("aria-hidden", "true");
        } else {
          bankButton.disabled = false;
          setPeekButtonHidden(bankButton, false);
          bankButton.classList.remove("has-corpus", "is-empty-slot", "is-loading-slot");
          bankButton.setAttribute("aria-hidden", "false");
          fetchP2BankCorpusPayload(questionId)
            .then((payload) => {
              if (state.p2Corpus.activeTurnQuestionId !== questionId) return;
              const hasBody = Boolean(String(payload?.corpus_text || payload?.brainstorm_idea || "").trim());
              bankButton.classList.remove("is-loading-slot");
              bankButton.classList.toggle("is-empty-slot", !hasBody);
              bankButton.classList.toggle("has-corpus", hasBody);
              bankButton.disabled = false;
              bankButton.setAttribute("aria-hidden", "false");
            })
            .catch(() => {
              if (state.p2Corpus.activeTurnQuestionId !== questionId) return;
              bankButton.classList.remove("is-loading-slot", "has-corpus");
              bankButton.classList.add("is-empty-slot");
              bankButton.disabled = false;
              bankButton.setAttribute("aria-hidden", "false");
            });
        }
      }

      // Document → 随素材绑定的内容 (the linked 串题素材). Shown only when a material
      // is linked for this turn.
      const visible = inP2Turn && Boolean(state.p2Corpus.selectedEntryId);
      const entry = visible ? currentP2CorpusEntry() : null;
      const bodyButton = $("peekP2CorpusBodyBtn");
      if (bodyButton) {
        setPeekButtonHidden(bodyButton, !visible);
        bodyButton.classList.toggle("is-empty-slot", inP2Turn && Boolean(state.p2Corpus.selectedEntryId) && !entry);
        bodyButton.classList.toggle("has-corpus", Boolean(entry));
        bodyButton.disabled = !visible;
        bodyButton.setAttribute("aria-hidden", visible ? "false" : "true");
        bodyButton.title = entry ? "查看链接的串题素材" : "已选择素材，正在加载内容";
      }
      if (inP2Turn && state.p2Corpus.selectedEntryId && !entry && !state.p2Corpus.loaded) {
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

    // 随题目绑定的「题库正文」: 串题灵感 (brainstorm) on top, 正文 (corpus_text) below,
    // mirroring the 编辑题库正文 editor layout.
    function p2BankBodyPeekHtml(payload) {
      const parsed = p2ParseBrainstormValue(payload?.brainstorm_idea);
      const corpusText = String(payload?.corpus_text || "").trim();
      if (!parsed.tags.length && !parsed.text && !corpusText) {
        return '<p class="muted">还没有为这道题准备正文。可以在「题库正文」里编辑。</p>';
      }
      const tagChips = parsed.tags.map((t) => `<span class="p2-brainstorm-tag is-readonly">${escapeHtml(t)}</span>`).join("");
      const ideaHtml = (parsed.tags.length || parsed.text)
        ? `<div class="p2-brainstorm-peek-idea">${tagChips}${parsed.text ? `<span class="p2-brainstorm-peek-idea-text">${escapeHtml(parsed.text)}</span>` : ""}</div>`
        : '<p class="muted">还没有写串题灵感。</p>';
      return `
        <section class="p2-corpus-peek-section p2-corpus-body-peek-section p2-corpus-peek-drag-handle" data-p2-dialog-drag-handle>
          <h4>串题灵感 Brainstorm</h4>
          <div>${ideaHtml}</div>
        </section>
        <section class="p2-corpus-peek-section p2-corpus-body-peek-section">
          <h4>正文</h4>
          <div>${corpusText ? renderMarkdown(corpusText) : '<p class="muted">还没有保存正文。</p>'}</div>
        </section>
      `;
    }

    function corpusPeekLoadingHtml(label = "正在加载…") {
      return `
        <section class="p2-corpus-peek-section p2-corpus-peek-loading" aria-live="polite">
          <div class="corpus-peek-loading-box">
            <strong>${escapeHtml(label)}</strong>
            <div class="corpus-peek-loading-lines" aria-hidden="true">
              <span></span><span></span><span></span><span></span>
            </div>
          </div>
        </section>
      `;
    }

    // Lightbulb → 随题目绑定的「题库正文」(我准备的本题正文): 串题灵感 + 正文,
    // loaded by the turn's bank question id (independent of any linked material).
    async function openP2CorpusPeek() {
      const questionId = state.p2Corpus.activeTurnQuestionId || p2TurnBankQuestionId(state.currentTurn);
      if (!questionId) return;
      // 这个弹窗不要标题栏（超长题干 + 多余的关闭按钮都没意义，点空白即关）。
      $("p2CorpusPeekHead")?.classList.add("hidden");
      // 立刻出窗口 + 加载反馈，不再等 fetch 才弹。
      const body = $("p2CorpusPeekBody");
      if (body) body.innerHTML = corpusPeekLoadingHtml("正在加载本题正文…");
      $("p2CorpusPeekDialog")?.classList.remove("hidden");
      resetCorpusPeekWindowPosition("p2CorpusPeekDialog");
      let payload = null;
      try {
        // 不 force：按钮渲染时已预热过缓存，命中即秒开；过期由后台 revalidate 处理。
        payload = await fetchP2BankCorpusPayload(questionId);
      } catch (_error) {
        payload = null;
      }
      // 窗口可能已被关掉或切到了别的题。
      if ($("p2CorpusPeekDialog")?.classList.contains("hidden")) return;
      if (state.p2Corpus.activeTurnQuestionId && state.p2Corpus.activeTurnQuestionId !== questionId) return;
      if (body) body.innerHTML = p2BankBodyPeekHtml(payload);
    }

    // Document → 随素材绑定的内容: the linked 串题素材 the learner attached to this turn.
    async function openP2CorpusBodyPeek() {
      if (!state.p2Corpus.selectedEntryId) return;
      if (!state.p2Corpus.loaded) await ensureP2CorpusLoaded();
      const entry = currentP2CorpusEntry();
      $("p2CorpusPeekHead")?.classList.remove("hidden"); // 链接素材弹窗仍保留标题栏
      text("p2CorpusPeekMeta", entry?.label || "P2 LINKED MATERIAL");
      text("p2CorpusPeekTitle", entry?.title ? `链接素材：${entry.title}` : "链接的串题素材");
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
      setPeekButtonHidden(button, !visible);
      button.classList.toggle("has-corpus", visible);
      button.title = visible ? "查看这次 P3 关联的已保存语料" : "没有关联的 P3 追问素材";
      // Warm the material in the background so the popup opens instantly.
      if (visible) prefetchP3CorpusPeekMaterial(turn).catch(() => {});
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
    // Prefetch cache: warm the P3 material the moment the peek button becomes
    // visible so clicking it opens instantly instead of waiting on a network
    // round-trip. Keyed by the turn's corpus identity so a new turn re-fetches.
    let p3CorpusPeekPrefetch = null; // { key, promise }

    function p3CorpusPeekTurnKey(turn = state.currentTurn) {
      const prompt = turn?.prompt || {};
      return [
        turn?.id || turn?.turn_id || "",
        prompt.source || state.p3PracticeSource?.sourceType || "",
        prompt.p3_bank_followup_id || prompt.followup_id || "",
        prompt.p2_question_id || prompt.cue_id || "",
        prompt.p2_corpus_entry_id || state.p3PracticeSource?.p2CorpusEntryId || "",
      ].join("|");
    }

    function prefetchP3CorpusPeekMaterial(turn = state.currentTurn) {
      const key = p3CorpusPeekTurnKey(turn);
      if (p3CorpusPeekPrefetch && p3CorpusPeekPrefetch.key === key) {
        return p3CorpusPeekPrefetch.promise;
      }
      const promise = p3CorpusPeekMaterialForTurn(turn).catch((err) => {
        // Drop a failed prefetch so a real open (or retry) fetches again.
        if (p3CorpusPeekPrefetch && p3CorpusPeekPrefetch.key === key) p3CorpusPeekPrefetch = null;
        throw err;
      });
      p3CorpusPeekPrefetch = { key, promise };
      return promise;
    }

    function renderP3CorpusPeekSource(source) {
      const body = $("p3CorpusPeekBody");
      if (!body) return;
      // The P3 question is the only thing the user wants here. It already shows
      // in the header, so the body carries just the saved corpus text when it
      // exists — no duplicated question, no empty-state nag, no P2 cue clutter.
      const corpus = source.body ? renderMarkdown(source.body) : "";
      body.innerHTML = corpus
        ? `<section class="p2-corpus-peek-section"><div>${corpus}</div></section>`
        : "";
    }

    async function openP3CorpusPeek() {
      const seq = ++p3CorpusPeekRequestSeq;
      // Header carries only the P3 question — hide the kicker so the P2 cue card
      // and other meta never leak in.
      $("p3CorpusPeekMeta")?.classList.add("hidden");
      text("p3CorpusPeekTitle", "相关 P3 追问");
      const body = $("p3CorpusPeekBody");
      if (body) body.innerHTML = corpusPeekLoadingHtml("正在加载关联语料…");
      $("p3CorpusPeekDialog")?.classList.remove("hidden");
      resetCorpusPeekWindowPosition("p3CorpusPeekDialog");
      try {
        // Reuse the warmed prefetch when available — usually already resolved,
        // so the loading state is skipped entirely.
        const source = await prefetchP3CorpusPeekMaterial();
        if (seq !== p3CorpusPeekRequestSeq) return;
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
      return api(path, payload, { keepalive: true });
    }

    function p1CorpusSavePayload(entry, corpusText) {
      const storage = p1CorpusStorageEntry(entry);
      const payload = {
        question_id: storage.question_id,
        topic: storage.topic,
        question: storage.question,
        corpus_text: String(corpusText || "").trim(),
        source: "report_or_library",
      };
      const referenceAnswer = entry?.last_ai_answer || entry?.band7_version || entry?.aiAnswer || "";
      if (referenceAnswer && payload.corpus_text) payload.last_ai_answer = referenceAnswer;
      return payload;
    }

    async function sendP1CorpusClearKeepalive(entry) {
      const payload = p1CorpusSavePayload(entry, "");
      if (!payload.question || !payload.question_id) return;
      const saved = await sendKeepaliveJson("/api/p1-corpus", payload);
      markP1CorpusEntryCleared({ ...entry, ...saved });
      return saved;
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
        }).catch(() => null);
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
            metadata: { brainstorm_idea: p2CorpusBrainstormIdeaValue() || p2Entry.brainstorm_idea || "" },
            source: "p2_bank_corpus_editor",
          }).catch(() => null);
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
        }).catch(() => null);
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
        }).catch(() => null);
      }
    }

    async function openP1CorpusLibrary() {
      // Guests may browse the library (the seeded cards render via the real
      // path); editing/saving is gated at the edit actions below, not at entry.
      openCorpusWindow("p1Corpus");
    }

    async function openP1CorpusEditor(entry, options = {}) {
      if (!entry) return;
      if (!state.account.authenticated) {
        guestGate("登录后才能编辑和保存你的 P1 语料库。", "p1Corpus");
        return;
      }
      ensureCsrfToken?.().catch(() => null);
      const showReferenceAnswer = options.showReferenceAnswer === true;
      const token = ++p1CorpusEditorLoadToken;
      const storage = p1CorpusStorageEntry(entry);
      let preparedEntry = { ...entry, ...storage };
      const openedQuestionId = storage.question_id || "";
      const openedQuestion = storage.question || preparedEntry.question || preparedEntry.display_question || "";
      const openedIds = p1CorpusEntryIds({
        question_id: storage.question_id,
        storage_question_id: preparedEntry.storage_question_id,
        legacy_question_id: preparedEntry.legacy_question_id,
      });
      // When opened from a report, the band7 reference travels in on the entry
      // (last_ai_answer/aiAnswer). Clearing the saved corpus must NOT wipe that
      // read-only reference — otherwise a previously-cleared question shows an
      // empty 7分回答参考 even though the report still has a Band 7 version.
      const reportReferenceAnswer = showReferenceAnswer
        ? String(entry.last_ai_answer || entry.aiAnswer || entry.band7_version || "")
        : "";
      const wasCleared = openedIds.some((id) => state.p1Corpus.clearedQuestionIds?.has?.(id));
      if (wasCleared) {
        preparedEntry = {
          ...preparedEntry,
          corpus_text: "",
          last_ai_answer: reportReferenceAnswer,
          band7_version: "",
          aiAnswer: reportReferenceAnswer,
        };
      }
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
      text("p1CorpusSaveStatus", preparedEntry.corpus_text || wasCleared ? "" : "正在查找已保存语料...");
      $("p1CorpusDialog")?.classList.remove("hidden");
      if (!preparedEntry.corpus_text && !wasCleared) {
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
      if ((storage.question_id || storage.question || preparedEntry.display_question) && !preparedEntry.corpus_text && !wasCleared) {
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

    function closeP1CorpusEditor(options = {}) {
      const restoreTopic = options.restoreTopic !== false;
      const resumeTopicKey = restoreTopic ? p1TopicModalResumeKey : "";
      p1TopicModalResumeKey = "";
      p1CorpusEditorLoadToken += 1;
      $("p1CorpusDialog")?.classList.add("hidden");
      state.p1Corpus.activeEntry = null;
      if (resumeTopicKey && state.view === "p1Corpus") {
        requestAnimationFrame(() => openP1TopicCardModal(resumeTopicKey));
      }
    }

    async function saveAndCloseP1CorpusEditor(options = {}) {
      if (!$("p1CorpusDialog") || $("p1CorpusDialog").classList.contains("hidden")) return;
      const entry = state.p1Corpus.activeEntry;
      const corpusText = getCorpusMarkdownValue("p1CorpusText").trim();
      if (entry && !corpusText) {
        markP1CorpusEntryCleared(entry);
        const storage = p1CorpusStorageEntry(entry);
        notifyCorpusSaved({ kind: "p1", questionId: storage.question_id, saved: false });
        closeP1CorpusEditor(options);
        state.p1Corpus.savingPromise?.catch(() => null)
          .then(() => sendP1CorpusClearKeepalive(entry))
          .catch((error) => {
            console.error(error);
            text("p1CorpusSaveStatus", error?.message || "清空保存失败，请重试。");
          });
        return;
      }
      if (entry) {
        const storage = p1CorpusStorageEntry(entry);
        notifyCorpusSaved({ kind: "p1", questionId: storage.question_id, saved: true });
        applyP1CorpusDraftLocal(entry, corpusText);
      }
      closeP1CorpusEditor(options);
      if (entry) {
        saveP1CorpusEntry({ entry, corpusText, silent: true })
          .catch((error) => {
            console.error(error);
            text("p1CorpusSaveStatus", error?.message || "清空保存失败，请重试。");
          });
      }
    }

    async function saveP1CorpusEntry(options = {}) {
      const entry = options.entry || state.p1Corpus.activeEntry;
      if (!entry) return;
      const nextCorpusText = (options.corpusText ?? getCorpusMarkdownValue("p1CorpusText")).trim();
      if (state.p1Corpus.saving) {
        await state.p1Corpus.savingPromise?.catch(() => null);
        return saveP1CorpusEntry(options);
      }
      state.p1Corpus.saving = true;
      const button = $("saveP1CorpusBtn");
      const original = button?.textContent || "保存语料";
      if (button && !options.silent) {
        button.disabled = true;
        button.textContent = "保存中...";
      }
      if (!options.silent) text("p1CorpusSaveStatus", "");
      const savePromise = (async () => {
      try {
        const storage = p1CorpusStorageEntry(entry);
        const payload = p1CorpusSavePayload(entry, nextCorpusText);
        if (nextCorpusText) {
          p1CorpusEntryIds({
            question_id: storage.question_id,
            storage_question_id: entry.storage_question_id,
            legacy_question_id: entry.legacy_question_id,
          }).forEach((id) => state.p1Corpus.clearedQuestionIds?.delete?.(id));
          persistP1CorpusClearedIds();
        }
        const saved = await api("/api/p1-corpus", payload);
        // Local state now leads any GET issued before this save. Bump the
        // generation and drop the cached in-flight request so a pre-save
        // snapshot can't overwrite what we just persisted (see
        // applyP1CorpusPayload's stale-payload guard).
        state.p1Corpus.mutationSeq = (state.p1Corpus.mutationSeq || 0) + 1;
        state.p1Corpus.loadingPromise = null;
        if (!String(saved.corpus_text || "").trim()) {
          saved.last_ai_answer = "";
          markP1CorpusEntryCleared({
            ...entry,
            ...saved,
            storage_question_id: storage.question_id,
            legacy_question_id: entry.legacy_question_id,
          });
        }
        if (!options.silent) text("p1CorpusSaveStatus", `已保存 ${saved.updated_at || ""}`);
        const updated = upsertP1CorpusEntry(saved);
        notifyCorpusSaved({
          kind: "p1",
          questionId: storage.question_id || saved.question_id || "",
          saved: Boolean(String(saved.corpus_text ?? nextCorpusText).trim()),
        });
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
            last_ai_answer: (updated || saved)?.last_ai_answer || "",
            updated_at: (updated || saved)?.updated_at || activeEntry.updated_at || "",
            display_question: activeEntry.display_question || activeEntry.question || saved.question || "",
          };
        }
        renderP1CorpusTopics();
        const topicModal = $("p1TopicCardModal");
        if (topicModal && !topicModal.classList.contains("hidden") && topicModal.dataset.p1TopicKey) {
          openP1TopicCardModal(topicModal.dataset.p1TopicKey);
        }
        updateP1CorpusPeekButton(state.currentTurn);
        if (options.closeOnSuccess) closeP1CorpusEditor();
      } catch (error) {
        if (String(error?.message || error || "").includes("Corpus text is empty") && !nextCorpusText) {
          markP1CorpusEntryCleared(entry);
          return;
        }
        if (!options.silent) text("p1CorpusSaveStatus", error.message || String(error));
        if (nextCorpusText) {
          const storage = p1CorpusStorageEntry(entry);
          notifyCorpusSaved({ kind: "p1", questionId: storage.question_id, invalidate: true });
          state.p1Corpus.loadingPromise = null;
          fetchP1CorpusPayload().then(applyP1CorpusPayload).catch(() => null);
        }
        if (options.closeOnError) closeP1CorpusEditor();
      } finally {
        state.p1Corpus.saving = false;
        state.p1Corpus.savingPromise = null;
        if (button && !options.silent) {
          button.disabled = false;
          button.textContent = original;
        }
      }
      })();
      state.p1Corpus.savingPromise = savePromise;
      return savePromise;
    }

    async function loadP2Corpus(options = {}) {
      if (!state.account.authenticated) {
        // Seed the default P2 素材库 through the real render path so guests see
        // genuine cards (P3 progress); any click is intercepted to the login dialog.
        applyP2CorpusPayload(p2SeedPayload());
        installGuestCorpusGuard("p2CorpusTopics", "登录后才能保存和复用你的 P2 串题素材库。");
        return;
      }
      const stats = $("p2CorpusStats");
      const container = $("p2CorpusTopics");
      if (state.p2Corpus.loaded) {
        renderP2CorpusTopics();
        if (stats) {
          stats.classList.add("is-refreshing");
          stats.setAttribute("aria-busy", "true");
        }
      } else {
        if (stats) stats.textContent = "加载中";
        if (container) container.innerHTML = corpusLoadingSkeletonHtml("正在加载 P2 素材库...");
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

    let p2CorpusFeedbackTimer = 0;

    function setP2CorpusFeedback(message, kind = "info") {
      const stats = $("p2CorpusStats");
      if (!stats) return;
      window.clearTimeout(p2CorpusFeedbackTimer);
      stats.textContent = message;
      stats.classList.toggle("is-refreshing", kind === "saving");
      stats.classList.toggle("is-success", kind === "success");
      stats.classList.toggle("is-error", kind === "error");
      if (kind !== "saving") {
        p2CorpusFeedbackTimer = window.setTimeout(() => {
          stats.classList.remove("is-success", "is-error");
          if (state.view === "p2Corpus" && state.p2Corpus.loaded) loadP2Corpus({ force: false }).catch(() => null);
        }, 1600);
      }
    }

    function flashP2CorpusEntry(entryId) {
      if (!entryId) return;
      window.requestAnimationFrame(() => {
        const selector = `[data-p2-corpus-entry="${CSS.escape(String(entryId))}"]`;
        const row = document.querySelector(selector)?.closest(".p2-material-row");
        if (!row) return;
        row.classList.remove("just-saved");
        void row.offsetWidth;
        row.classList.add("just-saved");
        window.setTimeout(() => row.classList.remove("just-saved"), 1800);
      });
    }

    function renderP2CorpusTopics() {
      const container = $("p2CorpusTopics");
      if (!container) return;
      scheduleP2BankListPrefetch();
      scheduleP2BankP3EditorWarmup();
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
            <div id="p2BrainstormHeadField" class="p2-brainstorm-head-field" aria-hidden="true"></div>
            <h3>串题灵感 Brainstorm</h3>
            <span class="p2-topic-count">${brainstormCount}/${currentCards.length || 0}</span>
          </header>
          <button type="button" class="p2-brainstorm-open-card" data-p2-brainstorm-open>
            <span id="p2BrainstormParticles" class="p2-brainstorm-particles" aria-hidden="true"></span>
            <span class="p2-brainstorm-card-copy">
              <strong>按题干快速记一句灵感</strong>
              <span>适合先放关键词、人物关系、地点、经历碎片，之后再整理成正式素材。</span>
            </span>
            <span class="p2-brainstorm-card-mark p2-brainstorm-card-mark--brain" aria-hidden="true">
              <svg class="p2-brain-icon" viewBox="0 0 32 32" focusable="false">
                <g class="p2-brain-cloud">
                  <path class="p2-brain-cloud-puff" d="M27.3,-5 H35.7 Q37,-5 37,-3.7 V0.2 Q37,1.5 35.7,1.5 H30.6 L26.6,3.3 L27.3,1.5 Q26,1.5 26,0.2 V-3.7 Q26,-5 27.3,-5 Z"/>
                  <g class="p2-brain-cloud-dots">
                    <rect x="27.8" y="-2.75" width="2" height="2"/>
                    <rect x="30.5" y="-2.75" width="2" height="2"/>
                    <rect x="33.2" y="-2.75" width="2" height="2"/>
                  </g>
                </g>
                <g class="p2-brain-bulb">
                  <line class="p2-brain-bulb-ray" x1="32" y1="-4.6" x2="32" y2="-6.2"/>
                  <line class="p2-brain-bulb-ray" x1="27.9" y1="-2.6" x2="26.6" y2="-3.7"/>
                  <line class="p2-brain-bulb-ray" x1="36.1" y1="-2.6" x2="37.4" y2="-3.7"/>
                  <circle class="p2-brain-bulb-glass" cx="32" cy="-1" r="3.5"/>
                  <rect class="p2-brain-bulb-base" x="30.2" y="1.8" width="3.6" height="2"/>
                </g>
                <rect class="p2-brain-limb" x="12.55" y="20" width="1.7" height="3.4"/>
                <rect class="p2-brain-limb" x="11.85" y="22.8" width="3.1" height="1.6"/>
                <rect class="p2-brain-limb" x="17.75" y="20" width="1.7" height="3.4"/>
                <rect class="p2-brain-limb" x="17.05" y="22.8" width="3.1" height="1.6"/>
                <path class="p2-brain-limb-stroke" d="M7.5,12.5 Q4.6,15.2 4,19.4"/>
                <rect class="p2-brain-hand" x="2.6" y="18.6" width="2.7" height="2.7"/>
                <path class="p2-brain-body" d="M10,6 H22 V8 H24 V10 H26 V16 H24 V18 H22 V20 H10 V18 H8 V16 H6 V10 H8 V8 H10 Z"/>
                <path class="p2-brain-fold" d="M16,8 V18 M10.5,10 H13.5 M18.5,10 H21.5 M10,16 H13 M19,16 H22"/>
                <rect class="p2-brain-eye" x="12" y="12.4" width="2" height="2"/>
                <rect class="p2-brain-eye" x="18" y="12.4" width="2" height="2"/>
                <g class="p2-brain-balloon">
                  <path class="p2-brain-balloon-string" d="M28,-1.9 C30.2,1 24.6,3.6 26.4,6.4"/>
                  <g class="p2-brain-balloon-bob">
                    <ellipse class="p2-brain-balloon-body" cx="28" cy="-6.6" rx="3.4" ry="3.9"/>
                    <path class="p2-brain-balloon-knot" d="M27.2,-3 L28.8,-3 L28,-1.5 Z"/>
                  </g>
                </g>
                <g class="p2-brain-arm-think">
                  <path class="p2-brain-limb-stroke" d="M24,13 C28.6,12 28.8,4.8 22,5"/>
                  <g class="p2-brain-hand-right">
                    <rect class="p2-brain-hand" x="20" y="2.9" width="3" height="3"/>
                  </g>
                </g>
                <g class="p2-brain-arm-idea">
                  <path class="p2-brain-limb-stroke" d="M24,13 C27.2,11.2 27.6,6.5 26,5.2"/>
                  <rect class="p2-brain-hand" x="24.8" y="3.6" width="2.8" height="2.8"/>
                </g>
                <g class="p2-brain-arm-hold">
                  <path class="p2-brain-limb-stroke" d="M24,13 C28.4,11.6 28.8,7 26.4,6"/>
                  <rect class="p2-brain-hand" x="24.9" y="4.9" width="3" height="3"/>
                </g>
              </svg>
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
        const p3Total = Number(item.p3_follow_up_count) || 0;
        const p3Saved = Math.min(Number(item.p3_follow_up_saved_count) || 0, p3Total);
        const p3Progress = p3Total ? Math.round((p3Saved / p3Total) * 100) : 0;
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
                <svg class="p2-seasonal-practice-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/></svg>
                <span>直接<br>练习</span>
              </button>
            </div>
            ${p3Total > 0 ? `
            <div class="p2-seasonal-p3-progress" data-progress="${p3Progress}" aria-label="P3 追问完成进度 ${p3Saved}/${p3Total}">
              <span class="p2-seasonal-p3-progress-label">P3 追问</span>
              <span class="p2-seasonal-p3-progress-track"><span style="width: ${p3Progress}%"></span></span>
              <span class="p2-seasonal-p3-progress-count">${p3Saved}/${p3Total}</span>
            </div>` : ""}
            <footer>
              <button type="button" class="p2-seasonal-action primary" data-p2-corpus-card-material="${escapeHtml(cardId)}">正文</button>
              <button type="button" class="p2-seasonal-action${item.has_p3_follow_up ? " is-ready" : ""}" data-p2-corpus-card-p3="${escapeHtml(cardId)}">P3 追问</button>
            </footer>
          </article>
        `;
      }).join("");
      destroyP2BrainstormParticles();
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
      initializeP2BrainstormParticles();
    }

    let p2BrainstormFields = [];
    // Shared origin for the mascot's 7s animation loop so re-renders can resume
    // the rebuilt SVG from the same phase instead of snapping back to t=0.
    let p2BrainMascotStartTime = 0;

    function destroyP2BrainstormParticles() {
      p2BrainstormFields.forEach((field) => field.destroy());
      p2BrainstormFields = [];
    }

    function initializeP2BrainstormParticles() {
      destroyP2BrainstormParticles();
      // Header strip ("串题灵感 Brainstorm 62/64") → dense pixel grid lit by a soft
      // diagonal wave. Card body (正文) → loose square fragments drifting across.
      const head = $("p2BrainstormHeadField");
      const body = $("p2BrainstormParticles");
      if (head) p2BrainstormFields.push(createPixelFlowField(head, "grid"));
      if (body) p2BrainstormFields.push(createPixelFlowField(body, "scatter"));
      initializeP2BrainstormMascot();
    }

    // The mascot's act-3 balloon picks a fresh random color every loop. The icon
    // element is rebuilt on each card render, so the listener can't accumulate.
    function initializeP2BrainstormMascot() {
      const icon = document.querySelector(".p2-brainstorm-card-mark--brain .p2-brain-icon");
      if (!icon) return;
      const colors = ["#fb7185", "#f59e0b", "#34d399", "#38bdf8", "#a78bfa", "#f472b6", "#facc15", "#4ade80", "#fb923c"];
      const pick = () => colors[Math.floor(Math.random() * colors.length)];
      icon.style.setProperty("--p2-balloon-color", pick());
      icon.addEventListener("animationiteration", (event) => {
        if (event.animationName === "p2BrainFloat") icon.style.setProperty("--p2-balloon-color", pick());
      });

      // The card re-renders when the async corpus payload resolves (a few seconds
      // after the first paint), which rebuilds this SVG and would otherwise
      // restart every 7s loop from t=0. On a hard refresh that reset lands right
      // in the middle of act-3 lift-off, so the balloon ascent visibly breaks the
      // first time (and only the first time). Anchor all 7s-synced animations to
      // one shared origin and resume the rebuilt element from the same phase via a
      // negative animation-delay, so any re-render is seamless. The cloud dots run
      // their own staggered 1.05s bounce and are intentionally left untouched.
      const LOOP_MS = 7000;
      if (!p2BrainMascotStartTime) p2BrainMascotStartTime = Date.now();
      const phase = ((Date.now() - p2BrainMascotStartTime) % LOOP_MS) / 1000;
      const delay = `-${phase.toFixed(3)}s`;
      icon.style.animationDelay = delay;
      icon
        .querySelectorAll(
          ".p2-brain-arm-think, .p2-brain-arm-idea, .p2-brain-arm-hold, .p2-brain-hand-right, .p2-brain-cloud, .p2-brain-bulb, .p2-brain-bulb-ray, .p2-brain-balloon, .p2-brain-balloon-bob"
        )
        .forEach((el) => {
          el.style.animationDelay = delay;
        });
    }

    // Self-contained canvas effect with two modes. Unlike particles.js, which
    // measures its host exactly once at init and silently renders nothing when
    // the box is 0×0 (hidden view) or its density math collapses the count, this
    // owns its canvas, re-sizes through a ResizeObserver, and repaints every
    // frame — so it can never go blank and always fills the host edge-to-edge.
    //   mode "grid"    — dense block grid, soft diagonal brightness wave.
    //   mode "scatter" — loose square fragments drifting rightward (the原来的特效).
    function createPixelFlowField(host, mode = "grid", options = {}) {
      // reverse=false → original flow LEFT→RIGHT (bright on the left); reverse=true →
      // flow RIGHT→LEFT (bright on the right). Per-instance so the P1 header can keep
      // left→right while the P3 box runs right→left.
      const reverse = options && options.reverse === true;
      const canvas = document.createElement("canvas");
      canvas.className = "p2-pixel-flow-canvas";
      host.appendChild(canvas);
      const ctx = canvas.getContext("2d");
      const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;
      const palette = ["#5eead4", "#34d399", "#22d3ee", "#7dd3fc", "#93c5fd", "#a5b4fc", "#c4b5fd"]
        .map((hex) => {
          const n = parseInt(hex.slice(1), 16);
          return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
        });
      const cell = 9;  // logical px per grid cell (block + gap) → small, dense pixels
      const block = 7; // painted grid square size
      // Stable per-cell colour + phase so the grid shimmers without flickering.
      const colorAt = (c, r) => palette[(c * 7 + r * 13 + ((c * r) % 5)) % palette.length];
      // Well-distributed per-cell random (no row/column structure → no diagonal).
      const hash = (c, r) => { const s = Math.sin(c * 127.1 + r * 311.7) * 43758.5453; return s - Math.floor(s); };
      // Deterministic fragment pool for scatter mode. Positions use the R2
      // low-discrepancy sequence so the fragments spread evenly across the whole
      // box instead of folding into a couple of rows (which a plain `i*k % n`
      // recurrence does).
      const frac = (x) => x - Math.floor(x);
      const fragments = Array.from({ length: 64 }, (_, i) => {
        const h1 = frac(Math.sin((i + 1) * 12.9898) * 43758.5453);
        const h2 = frac(Math.sin((i + 1) * 4.1414) * 27182.8459);
        return {
          x0: frac(0.5 + 0.7548776662 * i),   // 1/plastic-number
          y: frac(0.13 + 0.5698402910 * i),   // 1/plastic-number²
          size: 4 + Math.round(h1 * h1 * 6),  // 4–10px, skewed small: a few large, most smaller
          speed: 9 + h2 * 22,
          color: palette[i % palette.length],
          phase: h1 * Math.PI * 2,
        };
      });
      let cols = 0;
      let rows = 0;
      let width = 0;
      let height = 0;
      let rafId = 0;
      let start = 0;

      // Pointer-link state for scatter mode: a FIXED maximum number of the nearest
      // fragments get tethered to the cursor with a line, so moving the mouse looks
      // like it gathers the drifting fragments together — never a big clump.
      const pointer = { x: 0, y: 0, active: false };
      const scatterPos = new Array(fragments.length);
      const LINK_MAX = 6;      // never tether more than this many fragments at once
      const LINK_RADIUS = 170; // px; lines fade out past this so distant ones drop off
      function onPointerMove(e) {
        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        pointer.x = x;
        pointer.y = y;
        pointer.active = x >= 0 && y >= 0 && x <= rect.width && y <= rect.height;
      }
      function onPointerLeave() { pointer.active = false; }

      function resize() {
        const w = host.clientWidth;
        const h = host.clientHeight;
        if (w < 1 || h < 1) return;
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        width = w;
        height = h;
        cols = Math.ceil(w / cell) + 1;
        rows = Math.ceil(h / cell) + 1;
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
        canvas.style.width = `${w}px`;
        canvas.style.height = `${h}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        if (reduceMotion) draw(0);
      }

      function drawGrid(t) {
        // Soft VERTICAL band. Brightness over time comes ONLY from the moving column
        // waves (depends on c and t, never on r → never diagonal), so it reads as a
        // coherent flow, not random blinking. A static per-cell texture grains the
        // band to keep its edges soft. Pixel density is EVEN across the whole bar;
        // intensity just eases off toward the trailing edge.
        //   reverse=false (default): flow LEFT→RIGHT, bright on the LEFT  (P1 header).
        //   reverse=true:            flow RIGHT→LEFT, bright on the RIGHT (P3 box).
        const baseA = 0.16;
        const peakA = 0.9;
        // dir = -1 keeps the original rightward wave march (sin(c*k - t*w)); +1 flips
        // it to march leftward.
        const dir = reverse ? 1 : -1;
        for (let r = 0; r < rows; r += 1) {
          for (let c = 0; c < cols; c += 1) {
            const x = c * cell;
            const rnd = hash(c, r);                                // static texture, no time → no random blink
            // Three waves at incommensurate scales sum into an irregular, non-periodic
            // flow — keeps the directional trend but breaks the too-regular even
            // spacing. Raised baseline avoids hard dark gaps.
            const flow = 0.5
              + 0.22 * Math.sin(c * 0.17 + dir * t * 8.32)
              + 0.16 * Math.sin(c * 0.41 + dir * t * 6.76 + 2.1)
              + 0.12 * Math.sin(c * 0.93 + dir * t * 9.1 + 0.7);
            const lit = (0.4 + 0.6 * flow) * (0.32 + 0.68 * rnd); // wider per-cell grain → more randomness
            // u = distance from the BRIGHT edge (left edge normally, right edge when
            // reversed). The first 1/3 from that edge stays fullest, then intensity
            // eases off, the far quarter dims harder, and the last eighth goes dark.
            const uRaw = x / width;
            const u = reverse ? 1 - uRaw : uRaw;
            let soft;
            if (u >= 0.875) soft = 0;                              // trailing 1/8 fully dark
            else if (u >= 0.75) soft = 0.55 * (1 - (u - 0.75) / 0.125); // trailing 1/4: 0.55 → 0
            else if (u >= 1 / 3) soft = 1 - ((u - 1 / 3) / (0.75 - 1 / 3)) * 0.45; // ease 1 → 0.55
            else soft = 1;                                         // bright 1/3 stays brightest
            let alpha = (baseA + (peakA - baseA) * lit) * soft;
            if (alpha < 0.03) continue;
            const rgb = colorAt(c, r);
            // A little pure white at the brightest crest cells (on the bright edge).
            // The white probability eases off smoothly toward the dark edge: ~0.7 at
            // the bright edge, fading to 0 by 2/5 in.
            const leftWhite = u < 0.4 ? 0.7 * Math.pow(1 - u / 0.4, 0.35) : 0;
            const wAmt = Math.min(1, Math.max(0, (flow * rnd - (0.82 - 0.5 * leftWhite)) / 0.18)) * soft;
            const rr = Math.round(rgb[0] + (255 - rgb[0]) * wAmt);
            const gg = Math.round(rgb[1] + (255 - rgb[1]) * wAmt);
            const bb = Math.round(rgb[2] + (255 - rgb[2]) * wAmt);
            ctx.fillStyle = `rgba(${rr}, ${gg}, ${bb}, ${alpha.toFixed(3)})`;
            ctx.fillRect(x, r * cell, block, block);
          }
        }
      }

      function drawScatter(t, dark) {
        const ceiling = dark ? 0.82 : 0.66;
        const span = width + 16;
        for (let i = 0; i < fragments.length; i += 1) {
          const f = fragments[i];
          const x = ((f.x0 * span + f.speed * t) % span) - 8;
          const y = f.y * height + Math.sin(t * 0.6 + f.phase) * 3;
          const alpha = ceiling * (0.5 + 0.5 * (0.5 + 0.5 * Math.sin(t * 1.4 + f.phase)));
          ctx.fillStyle = `rgba(${f.color[0]}, ${f.color[1]}, ${f.color[2]}, ${alpha.toFixed(3)})`;
          ctx.fillRect(x, y, f.size, f.size);
          scatterPos[i] = { x: x + f.size / 2, y: y + f.size / 2, c: f.color };
        }
        if (pointer.active) drawPointerLinks(dark);
      }

      // Tether the cursor to its nearest few fragments. Ranking every fragment and
      // keeping only the closest LINK_MAX (and dropping any past LINK_RADIUS) keeps
      // the web small and steady instead of binding a whole cluster.
      function drawPointerLinks(dark) {
        const px = pointer.x;
        const py = pointer.y;
        const near = scatterPos
          .map((p, i) => ({ i, d: Math.hypot(p.x - px, p.y - py) }))
          .sort((a, b) => a.d - b.d)
          .slice(0, LINK_MAX);
        ctx.lineWidth = 1.4;
        for (const { i, d } of near) {
          if (d > LINK_RADIUS) continue;
          const p = scatterPos[i];
          const fade = 1 - d / LINK_RADIUS;
          const lineA = (dark ? 0.65 : 0.52) * fade;
          ctx.strokeStyle = `rgba(${p.c[0]}, ${p.c[1]}, ${p.c[2]}, ${lineA.toFixed(3)})`;
          ctx.beginPath();
          ctx.moveTo(px, py);
          ctx.lineTo(p.x, p.y);
          ctx.stroke();
        }
        // A faint hub dot where the cursor sits, so the link origin reads clearly.
        const hub = dark ? "rgba(125, 211, 252, 0.6)" : "rgba(45, 212, 191, 0.5)";
        ctx.fillStyle = hub;
        ctx.fillRect(px - 1.5, py - 1.5, 3, 3);
      }

      function draw(elapsed) {
        if (width < 1 || height < 1) return;
        ctx.clearRect(0, 0, width, height);
        const dark = document.body.classList.contains("theme-dark");
        const t = elapsed / 1000;
        if (mode === "scatter") drawScatter(t, dark);
        else drawGrid(t);
      }

      function frame(now) {
        if (!start) start = now;
        draw(now - start);
        rafId = window.requestAnimationFrame(frame);
      }

      const observer = new ResizeObserver(() => resize());
      observer.observe(host);
      resize();
      if (!reduceMotion) rafId = window.requestAnimationFrame(frame);

      // The canvas host is pointer-events:none (so card clicks pass through), so the
      // cursor is tracked on the document and mapped into canvas-local coordinates.
      const pointerTracked = mode === "scatter" && !reduceMotion;
      if (pointerTracked) {
        window.addEventListener("pointermove", onPointerMove, { passive: true });
        window.addEventListener("pointerleave", onPointerLeave, { passive: true });
      }

      return {
        destroy() {
          if (rafId) window.cancelAnimationFrame(rafId);
          observer.disconnect();
          if (pointerTracked) {
            window.removeEventListener("pointermove", onPointerMove);
            window.removeEventListener("pointerleave", onPointerLeave);
          }
          canvas.remove();
        },
      };
    }

    async function loadCorpusHome() {}

    async function loadLanguageTakeaways() {
      const stats = $("languageTakeawayStats");
      const list = $("languageTakeawayList");
      if (!state.account.authenticated) {
        // Default seed through the real render path: cards keep TTS, click and
        // review. Guests share the same defaults as a brand-new account.
        const payload = takeawaySeedPayload("language");
        applyLanguageTakeawaysPayload(payload);
        if (stats) stats.textContent = `${payload.count || 0} 条`;
        renderLanguageTakeawayToggle();
        renderLanguageTakeaways();
        renderTakeawayReviewSurfaces("language");
        return;
      }
      if (state.languageTakeaway.loaded) {
        renderLanguageTakeawayToggle();
        renderLanguageTakeaways();
        if (stats) stats.textContent = `${state.languageTakeaway.items.length} 条`;
        renderTakeawayReviewSurfaces("language");
        return;
      } else {
        if (stats) stats.textContent = "Loading...";
        if (list) list.innerHTML = '<div class="page-center-loading takeaway-page-loading" role="status" aria-live="polite"><div><span class="spinner"></span><div><strong>正在加载 Takeaway</strong><span>按记忆曲线整理你的语料卡片…</span></div></div></div>';
      }
      try {
        const payload = withTakeawayDefaults("language", await fetchLanguageTakeawaysPayload());
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

    // Strip inline markdown so a pasted "**a**" shows as plain "a" — the 原文,
    // nothing else. The Language Takeaway popup already captures clean text via
    // the browser selection; this gives the same result for typed/pasted/stored
    // source text everywhere it's displayed or saved.
    function stripInlineMarkdown(value) {
      return String(value || "")
        .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1") // [text](url) / ![alt](url) -> text
        .replace(/\*\*\*([^*]+)\*\*\*/g, "$1")      // ***bold italic***
        .replace(/\*\*([^*]+)\*\*/g, "$1")           // **bold**
        .replace(/\*([^*]+)\*/g, "$1")               // *italic*
        .replace(/__([^_]+)__/g, "$1")               // __bold__
        .replace(/~~([^~]+)~~/g, "$1")               // ~~strike~~
        .replace(/`([^`]+)`/g, "$1")                 // `code`
        .replace(/[*`~]/g, "");                      // any stray leftover markers
    }

    function takeawaySourceHtml(sourceText = "") {
      const raw = stripInlineMarkdown(String(sourceText || "").trim());
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
      // Keep the given order (creation order). Greedy: drop each next card into
      // the currently-shorter column. This balances heights without scrambling
      // reading order — older entries stay above newer ones within each column.
      const columnHeights = [0, 0];
      const gap = 10;
      nodes.forEach((node, index) => {
        const target = columnHeights[0] <= columnHeights[1] ? 0 : 1;
        columns[target].appendChild(node);
        columnHeights[target] += heights[index] + gap;
      });
      measure.remove();
    }

    // Expression-replacement entries (表达替换) are pinned to the top group.
    // They carry source="expression_replacement" (local optimistic inserts) and
    // a persisted context_label of "表达替换"/"写作表达替换" (survives reload).
    function isExpressionReplacementTakeaway(item) {
      return String(item?.source || "") === "expression_replacement"
        || String(item?.context_label || "").includes("表达替换");
    }

    // Sort by add-time ascending (oldest on top). Missing created_at (a just-
    // added optimistic entry not yet saved) sorts last → newest at the bottom.
    function sortTakeawaysByCreatedAsc(arr) {
      const key = (item) => String(item?.created_at || "").trim() || "￿";
      return arr
        .map((item, index) => ({ item, index }))
        .sort((a, b) => {
          const ka = key(a.item);
          const kb = key(b.item);
          if (ka < kb) return -1;
          if (ka > kb) return 1;
          return a.index - b.index;
        })
        .map((x) => x.item);
    }

    // Render a takeaway book as two notebook-style numbered sections, each its own
    // height-balanced masonry sorted by add-time: the ordinary "积累的…表达" group
    // on top (section 1), the 表达替换 group below (section 2). cardFor(item)
    // returns the card HTML for one entry; kind picks the 口语/写作 wording.
    function renderTakeawayBook(list, items, cardFor, kind = "language") {
      const expr = [];
      const normal = [];
      for (const item of items) {
        (isExpressionReplacementTakeaway(item) ? expr : normal).push(item);
      }
      const exprSorted = sortTakeawaysByCreatedAsc(expr);
      const normalSorted = sortTakeawaysByCreatedAsc(normal);
      list.innerHTML = "";
      const ordinaryLabel = kind === "writing" ? "积累的写作表达" : "积累的口语表达";
      let sectionNum = 0;
      const renderSection = (label, groupItems) => {
        if (!groupItems.length) return;
        sectionNum += 1;
        const heading = document.createElement("h2");
        heading.className = "takeaway-section-heading";
        heading.innerHTML = `<span class="tk-sec-num">${sectionNum}.</span> ${escapeHtml(label)}`;
        list.appendChild(heading);
        const group = document.createElement("div");
        group.className = "takeaway-group";
        list.appendChild(group);
        renderTakeawayMasonry(group, groupItems.map((item) => ({ html: cardFor(item) })));
      };
      renderSection(ordinaryLabel, normalSorted);
      renderSection("表达替换", exprSorted);
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
      setTakeawayReviewMascot(wrap, Boolean(options.current));
    }

    // The thinking pixel-brain that sits in the bottom-right of the "current"
    // review card. Unlike the P2 brainstorm mascot it only loops two acts
    // (scratch-think → lightbulb idea); the balloon + fly-off only run on A / D.
    function takeawayReviewMascotHtml() {
      return `
        <span class="takeaway-review-mascot" aria-hidden="true">
          <svg class="tk-brain-icon" viewBox="0 0 32 32" focusable="false">
            <g class="tk-brain-cloud">
              <path class="tk-brain-cloud-puff" d="M27.3,-5 H35.7 Q37,-5 37,-3.7 V0.2 Q37,1.5 35.7,1.5 H30.6 L26.6,3.3 L27.3,1.5 Q26,1.5 26,0.2 V-3.7 Q26,-5 27.3,-5 Z"/>
              <g class="tk-brain-cloud-dots">
                <rect x="27.8" y="-2.75" width="2" height="2"/>
                <rect x="30.5" y="-2.75" width="2" height="2"/>
                <rect x="33.2" y="-2.75" width="2" height="2"/>
              </g>
            </g>
            <g class="tk-brain-bulb">
              <line class="tk-brain-bulb-ray" x1="32" y1="-4.6" x2="32" y2="-6.2"/>
              <line class="tk-brain-bulb-ray" x1="27.9" y1="-2.6" x2="26.6" y2="-3.7"/>
              <line class="tk-brain-bulb-ray" x1="36.1" y1="-2.6" x2="37.4" y2="-3.7"/>
              <circle class="tk-brain-bulb-glass" cx="32" cy="-1" r="3.5"/>
              <rect class="tk-brain-bulb-base" x="30.2" y="1.8" width="3.6" height="2"/>
            </g>
            <rect class="tk-brain-limb" x="12.55" y="20" width="1.7" height="3.4"/>
            <rect class="tk-brain-limb" x="11.85" y="22.8" width="3.1" height="1.6"/>
            <rect class="tk-brain-limb" x="17.75" y="20" width="1.7" height="3.4"/>
            <rect class="tk-brain-limb" x="17.05" y="22.8" width="3.1" height="1.6"/>
            <path class="tk-brain-limb-stroke" d="M7.5,12.5 Q4.6,15.2 4,19.4"/>
            <rect class="tk-brain-hand" x="2.6" y="18.6" width="2.7" height="2.7"/>
            <path class="tk-brain-body" d="M10,6 H22 V8 H24 V10 H26 V16 H24 V18 H22 V20 H10 V18 H8 V16 H6 V10 H8 V8 H10 Z"/>
            <path class="tk-brain-fold" d="M16,8 V18 M10.5,10 H13.5 M18.5,10 H21.5 M10,16 H13 M19,16 H22"/>
            <rect class="tk-brain-eye" x="12" y="12.4" width="2" height="2"/>
            <rect class="tk-brain-eye" x="18" y="12.4" width="2" height="2"/>
            <g class="tk-brain-balloon">
              <path class="tk-brain-balloon-string" d="M28,-1.9 C30.2,1 24.6,3.6 26.4,6.4"/>
              <g class="tk-brain-balloon-bob">
                <ellipse class="tk-brain-balloon-body" cx="28" cy="-6.6" rx="3.4" ry="3.9"/>
                <path class="tk-brain-balloon-knot" d="M27.2,-3 L28.8,-3 L28,-1.5 Z"/>
              </g>
            </g>
            <g class="tk-brain-arm-think">
              <path class="tk-brain-limb-stroke" d="M24,13 C28.6,12 28.8,4.8 22,5"/>
              <g class="tk-brain-hand-right">
                <rect class="tk-brain-hand" x="20" y="2.9" width="3" height="3"/>
              </g>
            </g>
            <g class="tk-brain-arm-idea">
              <path class="tk-brain-limb-stroke" d="M24,13 C27.2,11.2 27.6,6.5 26,5.2"/>
              <rect class="tk-brain-hand" x="24.8" y="3.6" width="2.8" height="2.8"/>
            </g>
            <g class="tk-brain-arm-hold">
              <path class="tk-brain-limb-stroke" d="M24,13 C28.4,11.6 28.8,7 26.4,6"/>
              <rect class="tk-brain-hand" x="24.9" y="4.9" width="3" height="3"/>
            </g>
          </svg>
        </span>
      `;
    }

    function setTakeawayReviewMascot(wrap, on) {
      if (!wrap) return;
      const existing = wrap.querySelector(".takeaway-review-mascot");
      if (on) {
        if (!existing) wrap.insertAdjacentHTML("beforeend", takeawayReviewMascotHtml());
      } else if (existing) {
        existing.remove();
      }
    }

    function takeawayReviewCardWrap(kind, entryId) {
      const id = String(entryId || "").trim();
      if (!id) return null;
      const list = $(kind === "writing" ? "writingTakeawayList" : "languageTakeawayList");
      const selector = kind === "writing" ? "[data-writing-takeaway-entry]" : "[data-takeaway-entry]";
      const button = Array.from(list?.querySelectorAll(selector) || []).find((candidate) => {
        return kind === "writing"
          ? candidate.dataset.writingTakeawayEntry === id
          : candidate.dataset.takeawayEntry === id;
      });
      return button?.closest(".language-takeaway-card-wrap") || null;
    }

    function markTakeawayLocatedCard(kind, entryId = "") {
      const list = $(kind === "writing" ? "writingTakeawayList" : "languageTakeawayList");
      if (!list) return;
      list.querySelectorAll(".language-takeaway-card-wrap.is-located").forEach((wrap) => {
        wrap.classList.remove("is-located");
      });
      const wrap = takeawayReviewCardWrap(kind, entryId);
      if (wrap) wrap.classList.add("is-located");
    }

    function scrollTakeawayCardIntoView(kind, entryId) {
      const wrap = takeawayReviewCardWrap(kind, entryId);
      if (!wrap) return;
      const list = $(kind === "writing" ? "writingTakeawayList" : "languageTakeawayList");
      if (!list) return;
      const maxScroll = Math.max(0, list.scrollHeight - list.clientHeight);
      if (maxScroll <= 1) return;
      const listRect = list.getBoundingClientRect();
      const wrapRect = wrap.getBoundingClientRect();
      const margin = 18;
      if (wrapRect.top >= listRect.top + margin && wrapRect.bottom <= listRect.bottom - margin) return;
      const centeredTop = list.scrollTop
        + (wrapRect.top - listRect.top)
        - Math.max(0, (list.clientHeight - wrapRect.height) / 2);
      const nextTop = Math.max(0, Math.min(maxScroll, centeredTop));
      if (Math.abs(nextTop - list.scrollTop) < 2) return;
      const totalCards = list.querySelectorAll(".language-takeaway-card-wrap").length;
      const behavior = kind === "writing" && totalCards <= 6 ? "auto" : "smooth";
      list.scrollTo({ top: nextTop, behavior });
    }

    // The card to jump to this session. If a card is currently revealed and
    // awaiting A / D the deck is locked to it, so that wins. Otherwise we pick
    // the *visually topmost* un-graded due card — the masonry reorders cards
    // across columns, so "first in session.ids" is not the one highest on the
    // page. We measure live DOM rects and take the smallest top, so the result
    // is dynamic: as cards get graded and disappear, the topmost shifts.
    function firstTakeawayReviewTargetId(kind = "language") {
      const session = takeawayReviewSession(kind);
      if (!session.active) return "";
      const reviewed = session.reviewedIds || new Set();
      const current = String(session.currentId || "").trim();
      if (current && !reviewed.has(current)) return current;
      let bestId = "";
      let bestTop = Infinity;
      for (const value of (session.ids || [])) {
        const id = String(value || "").trim();
        if (!id || reviewed.has(id)) continue;
        const wrap = takeawayReviewCardWrap(kind, id);
        if (!wrap) continue;
        // All rects measured at the same scroll offset, so the relative order by
        // viewport-top equals document order — smallest top = physically highest.
        const top = wrap.getBoundingClientRect().top;
        if (top < bestTop) {
          bestTop = top;
          bestId = id;
        }
      }
      return bestId;
    }

    // Jump the list to that card — used by the auto-jump right after 开始, so the
    // user never has to scroll around hunting for where the session begins.
    function scrollToTakeawayReviewTarget(kind = "language") {
      const id = firstTakeawayReviewTargetId(kind);
      if (id) scrollTakeawayCardIntoView(kind, id);
    }

    // The 定位 button / W key is two-stage: the first press frames the visually
    // topmost card still to practise (dashed outline) and centres it; pressing
    // again — while that same card is still the target — opens it (reveals the
    // English, entering the selected state), exactly like clicking the card.
    function triggerTakeawayLocate(kind = "language") {
      const session = takeawayReviewSession(kind);
      if (!session.active) return;
      if (session.animatingId) {
        session.pendingLocate = true;
        return;
      }
      const target = firstTakeawayReviewTargetId(kind);
      if (!target) return;
      if (session.locatedId === target) {
        session.locatedId = "";
        markTakeawayLocatedCard(kind, "");
        const reviewState = selectTakeawayReviewEntry(kind, target);
        // Opening via W must read the English aloud, same as clicking the card.
        if (reviewState === "selected") {
          const items = kind === "writing" ? state.writingTakeaway.items : state.languageTakeaway.items;
          const item = (items || []).find((entry) => entry.entry_id === target);
          speakLanguageTakeaway(item?.source_text || "", { kind });
        }
        scrollTakeawayCardIntoView(kind, target);
        return;
      }
      session.locatedId = target;
      markTakeawayLocatedCard(kind, target);
      scrollTakeawayCardIntoView(kind, target);
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
      const cardFor = (item) => {
        const isReviewTarget = isTakeawayReviewEntry("language", item.entry_id);
        const isDue = dueIds.has(item.entry_id);
        const shouldConceal = (session.active ? isReviewTarget : hiddenMode) && !revealed.has(item.entry_id);
        const isCurrent = session.active && session.currentId === item.entry_id;
        const isLocated = session.active && session.locatedId === item.entry_id && isReviewTarget && !isCurrent;
        return `
        <div class="language-takeaway-card-wrap ${shouldConceal ? "is-concealed" : "is-revealed"} ${isDue ? "is-review-due" : ""} ${isReviewTarget ? "is-reviewing" : ""} ${isCurrent ? "is-review-current" : ""} ${isLocated ? "is-located" : ""}">
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
          ${isCurrent ? takeawayReviewMascotHtml() : ""}
        </div>
      `;
      };
      renderTakeawayBook(list, items, cardFor, "language");
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

    function interruptTakeawaySpeechPlayback() {
      speechSequenceToken += 1;
      if (window.speechSynthesis) prepareSpeechQueue(window.speechSynthesis);
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
      if (guestBlockTakeawayEdit("登录后才能删除 Takeaway 内容。")) return;
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
      if (textValue.length < 1 || textValue.length > TAKEAWAY_SELECTION_MAX_LEN) return null;
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

    // 串题灵感 fields are <input>/<textarea> elements, so window.getSelection()
    // returns nothing for them (like the writing answer box). Capture the
    // selected substring directly and place the trigger at the caret end.
    function brainstormSelectionText() {
      const el = document.activeElement;
      if (!el || !el.matches?.("[data-p2-brainstorm-input], #p2CorpusBrainstormIdea")) return null;
      const start = Number(el.selectionStart);
      const end = Number(el.selectionEnd);
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
      const textValue = String(el.value || "").slice(start, end).trim();
      if (textValue.length < 1 || textValue.length > TAKEAWAY_SELECTION_MAX_LEN) return null;
      const selectionRect = textareaSelectionEndpointRect(el, end);
      if (!selectionRect) return null;
      return {
        text: textValue,
        rect: selectionRect,
        center: {
          x: selectionRect.left + selectionRect.width / 2,
          y: selectionRect.top + selectionRect.height / 2,
        },
        source: "brainstorm",
      };
    }

    function nearestElementFromNode(node) {
      if (!node) return null;
      return node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    }

    function usableClientRect(rect) {
      return rect && (rect.width || rect.height) ? rect : null;
    }

    function vditorSelectionScope(selection, range) {
      const anchor = nearestElementFromNode(selection?.anchorNode);
      const focus = nearestElementFromNode(selection?.focusNode);
      const common = nearestElementFromNode(range?.commonAncestorContainer);
      return anchor?.closest?.(".vditor")
        || focus?.closest?.(".vditor")
        || common?.closest?.(".vditor")
        || null;
    }

    function cleanMarkdownSelectionText(value) {
      return String(value || "")
        .replace(/\u200b/g, "")
        .replace(/\*\*/g, "")
        .replace(/__([^_]+)__/g, "$1")
        .replace(/`([^`]+)`/g, "$1")
        .trim();
    }

    function vditorSelectionRect(selection, range) {
      const common = nearestElementFromNode(range?.commonAncestorContainer);
      const anchor = nearestElementFromNode(selection?.anchorNode);
      const focus = nearestElementFromNode(selection?.focusNode);
      const scope = vditorSelectionScope(selection, range);
      if (!scope) return null;
      for (const node of [focus, anchor, common]) {
        const rect = usableClientRect(node?.getBoundingClientRect?.());
        if (rect) return rect;
      }
      const selectedNode = common?.closest?.("strong, b, em, span, p, li, .vditor-ir__node, .vditor-wysiwyg__block");
      const selectedRect = usableClientRect(selectedNode?.getBoundingClientRect?.());
      if (selectedRect) return selectedRect;
      return usableClientRect(scope.getBoundingClientRect());
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
      const brainstormSelection = brainstormSelectionText();
      if (brainstormSelection) return brainstormSelection;
      const selection = window.getSelection?.();
      if (!selection || selection.rangeCount === 0) return null;
      const range = selection.getRangeAt(0);
      const vditorScope = vditorSelectionScope(selection, range);
      const rawText = String(selection?.toString() || range.cloneContents?.().textContent || "");
      const textValue = vditorScope ? cleanMarkdownSelectionText(rawText) : rawText.trim();
      if (textValue.length < 1 || textValue.length > TAKEAWAY_SELECTION_MAX_LEN) return null;
      let rect = range.getBoundingClientRect();
      // A selection that begins/ends inside a Vditor bold node (whose ** markers
      // are non-selectable spans) can report a degenerate 0×0 bounding rect.
      // Fall back to the first non-empty client rect so the trigger still shows.
      if (!rect || (rect.width === 0 && rect.height === 0)) {
        for (const candidate of range.getClientRects()) {
          if (candidate && (candidate.width || candidate.height)) { rect = candidate; break; }
        }
      }
      if (!rect || (rect.width === 0 && rect.height === 0)) {
        rect = vditorSelectionRect(selection, range);
      }
      if (!rect || (rect.width === 0 && rect.height === 0)) return null;
      const promptEl = $("writingPromptText");
      const answerEl = $("writingAnswer");
      const activeEl = document.activeElement;
      const source = vditorScope
        ? "markdown_editor"
        : promptEl && promptEl.contains(range.commonAncestorContainer)
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
      resetLanguageTakeawayDictionary();
    }

    // Grow the English source textarea to fit its content so the whole selection
    // is shown without an inner scrollbar (capped by the CSS max-height).
    function autosizeLanguageTakeawaySource() {
      const el = $("languageTakeawaySource");
      if (!el) return;
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    }

    function languageTakeawayDictionaryState() {
      const target = state.languageTakeaway;
      if (!target.dictionary) {
        target.dictionary = {
          active: false,
          mode: "zh",
          chineseText: "",
          englishText: "",
          hasEnglish: false,
        };
      }
      return target.dictionary;
    }

    // Domain-label tags for the offline-dictionary card. ECDICT marks the field
    // of a Chinese sense with a bracketed code like "[经]"; render those as
    // compact English pills (icon + English label) so they read clearly.
    const DICT_DOMAIN_TAGS = {
      "经": { en: "Economics", icon: "📈" },
      "计": { en: "Computing", icon: "💻" },
      "医": { en: "Medicine", icon: "⚕️" },
      "法": { en: "Law", icon: "⚖️" },
      "化": { en: "Chemistry", icon: "🧪" },
      "数": { en: "Math", icon: "📐" },
      "军": { en: "Military", icon: "🎖️" },
      "语": { en: "Linguistics", icon: "🗣️" },
      "物": { en: "Physics", icon: "⚛️" },
      "植": { en: "Botany", icon: "🌿" },
      "动": { en: "Zoology", icon: "🐾" },
      "天": { en: "Astronomy", icon: "🔭" },
      "地": { en: "Geography", icon: "🌍" },
      "生": { en: "Biology", icon: "🧬" },
      "电": { en: "Electrical", icon: "⚡" },
      "机": { en: "Mechanics", icon: "⚙️" },
      "建": { en: "Architecture", icon: "🏛️" },
      "商": { en: "Business", icon: "💼" },
      "农": { en: "Agriculture", icon: "🌾" },
      "音": { en: "Music", icon: "🎵" },
      "体": { en: "Sports", icon: "⚽" },
      "宗": { en: "Religion", icon: "⛪" },
      "心": { en: "Psychology", icon: "🧠" },
      "解": { en: "Anatomy", icon: "🦴" },
      "药": { en: "Pharmacy", icon: "💊" },
      "史": { en: "History", icon: "📜" },
      "哲": { en: "Philosophy", icon: "💭" },
      "政": { en: "Politics", icon: "🏛️" },
      "航": { en: "Aviation", icon: "✈️" },
      "海": { en: "Nautical", icon: "⚓" },
      "矿": { en: "Mining", icon: "⛏️" },
      "林": { en: "Forestry", icon: "🌲" },
      "摄": { en: "Photography", icon: "📷" },
    };
    const DICT_DOMAIN_BY_LABEL = Object.fromEntries(
      Object.entries(DICT_DOMAIN_TAGS).map(([code, tag]) => [String(tag.en).toLowerCase(), code])
    );

    function dictionaryDomainTagHtml(code) {
      const tag = DICT_DOMAIN_TAGS[code];
      const label = String(tag ? tag.en : code).toLowerCase();
      const icon = tag ? tag.icon : "🏷️";
      return `<span class="dict-domain-tag" data-dict-domain-code="${escapeHtml(code)}" data-dict-domain-label="${escapeHtml(label)}" contenteditable="false"><span class="dict-domain-tag-icon" aria-hidden="true">${escapeHtml(icon)}</span><span class="dict-domain-tag-text">${escapeHtml(label)}</span></span><span class="dict-domain-tag-colon" contenteditable="false">&#65306; </span>`;
    }

    function dictionaryDomainLabelTagHtml(label) {
      const key = String(label || "").trim().toLowerCase();
      const code = DICT_DOMAIN_BY_LABEL[key];
      return code ? dictionaryDomainTagHtml(code) : null;
    }

    function escapeHtmlWithDictionaryDomainTags(text) {
      let html = escapeHtml(String(text || ""));
      html = html.replace(/\[([^\]]{1,4})\]\s*/g, (_m, code) => dictionaryDomainTagHtml(code));
      html = html.replace(/\b([A-Za-z][A-Za-z ]{1,28})\s*[:：]\s*/g, (match, label) => {
        return dictionaryDomainLabelTagHtml(label) || match;
      });
      return html;
    }

    // Chinese senses with bracketed domain codes -> one line per sense, codes
    // swapped for pill tags. Non-domain text is escaped as-is.
    function dictionaryChineseTagsHtml(text) {
      const lines = String(text || "").split(/\n+/).map((s) => s.trim()).filter(Boolean);
      if (!lines.length) return "";
      return lines
        .map((line) => {
          const html = escapeHtmlWithDictionaryDomainTags(line);
          return `<span class="dict-sense-line">${html}</span>`;
        })
        .join("");
    }

    if (typeof window !== "undefined") {
      window.IELTSDictTags = {
        escapeHtmlWithDomainTags: escapeHtmlWithDictionaryDomainTags,
        chineseTagsHtml: dictionaryChineseTagsHtml,
      };
    }

    function dictionaryEnglishHtml(text) {
      const value = String(text || "").trim();
      if (!value) return "";
      // ECDICT separates definition senses with a literal "\n" (backslash + n),
      // and occasionally real newlines — split on both so each English sense
      // renders on its own line instead of showing a raw "\n".
      const lines = value.split(/\\n|\n+/).map((s) => s.trim()).filter(Boolean);
      if (!lines.length) return "";
      return lines
        .map((line) => `<span class="dict-sense-line dict-sense-en">${escapeHtml(line)}</span>`)
        .join("");
    }

    function languageTakeawayDictNodeText(node) {
      if (!node) return "";
      if (node.nodeType === Node.TEXT_NODE) return node.textContent || "";
      if (node.nodeType !== Node.ELEMENT_NODE) return "";
      if (node.classList?.contains("dict-domain-tag")) {
        return node.dataset.dictDomainLabel || node.textContent || "";
      }
      if (node.classList?.contains("dict-domain-tag-colon")) return "：";
      return Array.from(node.childNodes || []).map(languageTakeawayDictNodeText).join("");
    }

    function languageTakeawayDictDisplayPlainText() {
      const display = $("languageTakeawayDictDisplay");
      if (!display || display.classList.contains("hidden")) return "";
      const lines = Array.from(display.querySelectorAll(".dict-sense-line"));
      const sourceLines = lines.length ? lines : [display];
      return sourceLines
        .map((line) => languageTakeawayDictNodeText(line).replace(/[ \t]+/g, " ").trim())
        .filter(Boolean)
        .join("\n");
    }

    // The dictionary card is a read-only, tag-rendered view that replaces the
    // plain <textarea> while a single-word lookup is active. The textarea stays
    // in the DOM as the hidden value carrier, so saving logic is untouched.
    function renderLanguageTakeawayDictDisplay() {
      const display = $("languageTakeawayDictDisplay");
      const field = $("languageTakeawayChineseField") || $("languageTakeawayChinese")?.closest("label");
      if (!display) return;
      const dict = languageTakeawayDictionaryState();
      if (!dict.active) {
        display.classList.add("hidden");
        display.innerHTML = "";
        field?.classList.remove("hidden");
        return;
      }
      const chineseEl = $("languageTakeawayChinese");
      if (dict.mode === "en") {
        display.innerHTML = dictionaryEnglishHtml(dict.englishText);
        display.classList.add("is-dictionary-english");
        display.classList.remove("is-dictionary-editable");
        display.contentEditable = "false";
        display.removeAttribute("role");
        display.removeAttribute("aria-label");
      } else {
        display.innerHTML = dictionaryChineseTagsHtml(dict.chineseText);
        display.classList.remove("is-dictionary-english");
        display.classList.add("is-dictionary-editable");
        display.contentEditable = "true";
        display.setAttribute("role", "textbox");
        display.setAttribute("aria-label", "中文释义，可编辑");
      }
      display.classList.remove("hidden");
      field?.classList.add("hidden");
    }

    function dictionaryAtomElementFromNode(node, direction = "self") {
      const element = nearestElementFromNode(node);
      if (!element) return null;
      if (element.classList?.contains("dict-domain-tag")) return element;
      if (element.classList?.contains("dict-domain-tag-colon")) {
        const sibling = direction === "next" ? element.nextElementSibling : element.previousElementSibling;
        return sibling?.classList?.contains("dict-domain-tag") ? sibling : null;
      }
      return element.closest?.(".dict-domain-tag") || null;
    }

    function dictionaryAdjacentNode(node, root, direction) {
      if (!node || !root) return null;
      const childNode = direction === "previous" ? "lastChild" : "firstChild";
      const siblingNode = direction === "previous" ? "previousSibling" : "nextSibling";
      const descend = (candidate) => {
        let current = candidate;
        while (current?.[childNode]) current = current[childNode];
        return current;
      };
      if (node[siblingNode]) return descend(node[siblingNode]);
      let parent = node.parentNode;
      while (parent && parent !== root) {
        if (parent[siblingNode]) return descend(parent[siblingNode]);
        parent = parent.parentNode;
      }
      return null;
    }

    function dictionaryCandidateAtCaret(container, offset, display, direction) {
      let candidate = null;
      if (container?.nodeType === Node.TEXT_NODE) {
        const textLength = String(container.textContent || "").length;
        if (direction === "previous" && offset > 0) return null;
        if (direction === "next" && offset < textLength) return null;
        candidate = dictionaryAdjacentNode(container, display, direction);
      } else if (container?.nodeType === Node.ELEMENT_NODE) {
        const child = direction === "previous"
          ? container.childNodes[Math.max(0, offset - 1)]
          : container.childNodes[offset];
        candidate = child || dictionaryAdjacentNode(container, display, direction);
        const edge = direction === "previous" ? "lastChild" : "firstChild";
        while (candidate?.[edge]) candidate = candidate[edge];
      }
      while (candidate?.nodeType === Node.TEXT_NODE && !String(candidate.textContent || "").trim()) {
        candidate = dictionaryAdjacentNode(candidate, display, direction);
      }
      return candidate;
    }

    function deleteDictionaryDomainAtom(tag) {
      if (!tag?.classList?.contains("dict-domain-tag")) return false;
      const colon = tag.nextElementSibling?.classList?.contains("dict-domain-tag-colon")
        ? tag.nextElementSibling
        : null;
      const range = document.createRange();
      range.setStartBefore(tag);
      if (colon) range.setEndAfter(colon);
      else range.setEndAfter(tag);
      const selection = window.getSelection?.();
      selection?.removeAllRanges?.();
      selection?.addRange?.(range);
      const deleted = document.execCommand?.("delete") !== false;
      syncLanguageTakeawayDictionaryChineseDraft();
      return deleted;
    }

    function handleDictionaryDomainAtomDelete(event) {
      if (!["Backspace", "Delete"].includes(event.key)) return;
      const display = $("languageTakeawayDictDisplay");
      if (!display?.classList.contains("is-dictionary-editable")) return;
      const selection = window.getSelection?.();
      if (!selection || selection.rangeCount === 0) return;
      const range = selection.getRangeAt(0);
      if (!display.contains(range.commonAncestorContainer) || !selection.isCollapsed) return;
      const direction = event.key === "Backspace" ? "previous" : "next";
      const directAtom = dictionaryAtomElementFromNode(selection.anchorNode, direction);
      const candidate = directAtom || dictionaryAtomElementFromNode(
        dictionaryCandidateAtCaret(selection.anchorNode, selection.anchorOffset, display, direction),
        direction,
      );
      if (!candidate) return;
      event.preventDefault();
      deleteDictionaryDomainAtom(candidate);
    }

    function resetLanguageTakeawayDictionary() {
      state.languageTakeaway.dictionary = {
        active: false,
        mode: "zh",
        chineseText: "",
        englishText: "",
        hasEnglish: false,
      };
      const chineseEl = $("languageTakeawayChinese");
      if (chineseEl) {
        chineseEl.readOnly = false;
        chineseEl.classList.remove("is-dictionary-english", "is-dictionary-transitioning");
        chineseEl.setAttribute("aria-label", "中文");
      }
      renderLanguageTakeawayDictionaryToggle();
      renderLanguageTakeawayDictDisplay();
    }

    function renderLanguageTakeawayDictionaryToggle() {
      const btn = $("languageTakeawayDictToggle");
      if (!btn) return;
      const dict = languageTakeawayDictionaryState();
      const show = dict.active && dict.hasEnglish;
      btn.classList.toggle("hidden", !show);
      btn.disabled = !show;
      btn.dataset.dictionaryMode = dict.mode;
      const isEnglish = dict.mode === "en";
      btn.setAttribute("aria-pressed", isEnglish ? "true" : "false");
      btn.setAttribute(
        "aria-label",
        isEnglish ? "当前英英词典，点击切换到翻译词典" : "当前翻译词典，点击切换到英英词典",
      );
      btn.title = isEnglish ? "当前英英词典 · 切换到翻译词典" : "当前翻译词典 · 切换到英英词典";
    }

    function setLanguageTakeawayDictionaryDisplay(mode, { animate = true } = {}) {
      const dict = languageTakeawayDictionaryState();
      const chineseEl = $("languageTakeawayChinese");
      if (!dict.active || !chineseEl) {
        renderLanguageTakeawayDictionaryToggle();
        return;
      }
      const nextMode = mode === "en" && dict.hasEnglish ? "en" : "zh";
      if (dict.mode === "zh") {
        syncLanguageTakeawayDictionaryChineseDraft();
      }
      dict.mode = nextMode;
      const display = $("languageTakeawayDictDisplay");
      const apply = () => {
        chineseEl.value = nextMode === "en" ? dict.englishText : dict.chineseText;
        chineseEl.readOnly = nextMode === "en";
        chineseEl.classList.toggle("is-dictionary-english", nextMode === "en");
        chineseEl.setAttribute("aria-label", nextMode === "en" ? "英英释义（只读）" : "中文");
        renderLanguageTakeawayDictDisplay();
        renderLanguageTakeawayDictionaryToggle();
      };
      if (!animate) {
        apply();
        return;
      }
      display?.classList.add("is-dictionary-transitioning");
      chineseEl.classList.add("is-dictionary-transitioning");
      window.setTimeout(() => {
        apply();
        window.setTimeout(() => {
          chineseEl.classList.remove("is-dictionary-transitioning");
          display?.classList.remove("is-dictionary-transitioning");
        }, 120);
      }, 120);
    }

    function setLanguageTakeawayDictionaryEntry({ chineseText = "", englishText = "" } = {}) {
      const dict = languageTakeawayDictionaryState();
      dict.active = true;
      dict.chineseText = String(chineseText || "").trim();
      dict.englishText = String(englishText || "").trim();
      dict.hasEnglish = Boolean(dict.englishText);
      // Default to the 翻译词典 (Chinese); the toggle still lets the user switch to
      // the 英英 definition when one exists.
      setLanguageTakeawayDictionaryDisplay("zh", { animate: false });
    }

    function toggleLanguageTakeawayDictionaryMode() {
      const dict = languageTakeawayDictionaryState();
      if (!dict.active || !dict.hasEnglish) return;
      setLanguageTakeawayDictionaryDisplay(dict.mode === "en" ? "zh" : "en");
    }

    function syncLanguageTakeawayDictionaryChineseDraft() {
      const dict = languageTakeawayDictionaryState();
      if (!dict.active || dict.mode !== "zh") return;
      dict.chineseText = languageTakeawayDictDisplayPlainText() || String($("languageTakeawayChinese")?.value || "").trim();
      const chineseEl = $("languageTakeawayChinese");
      if (chineseEl) chineseEl.value = dict.chineseText;
    }

    function languageTakeawayChineseForSave() {
      const dict = languageTakeawayDictionaryState();
      if (dict.active) {
        if (dict.mode === "zh") syncLanguageTakeawayDictionaryChineseDraft();
        return String(dict.chineseText || "").trim();
      }
      return String($("languageTakeawayChinese")?.value || "").trim();
    }

    function isSingleEnglishWord(value) {
      return /^[A-Za-z][A-Za-z'’-]*$/.test(String(value || "").trim());
    }

    function setLanguageTakeawaySpellingGlyph(btn, stateName = "plus") {
      if (!btn) return;
      btn.dataset.spellingState = stateName === "busy" || stateName === "check" ? stateName : "plus";
    }

    // The + button (bottom-left of the popup) only applies to a single English
    // word; it adds that word to spelling training.
    function updateLanguageTakeawaySpellingButton() {
      const btn = $("languageTakeawaySpellingBtn");
      if (!btn) return;
      const single = isSingleEnglishWord($("languageTakeawaySource")?.value || "");
      btn.classList.toggle("hidden", !single);
      if (!single) return;
      btn.classList.remove("is-added", "is-busy");
      btn.removeAttribute("aria-busy");
      delete btn.dataset.spellingWordId;
      setLanguageTakeawaySpellingGlyph(btn, "plus");
      btn.disabled = false;
      btn.title = "加入拼写训练";
      btn.setAttribute("aria-label", "加入拼写训练");
    }

    // Toggle the current word in/out of spelling training. First click adds it
    // (button turns green + checkmark); clicking the added button cancels the
    // add, same as deleting the word from the drill.
    async function addLanguageTakeawaySpellingWord() {
      const btn = $("languageTakeawaySpellingBtn");
      if (btn && btn.classList.contains("is-added")) {
        return removeLanguageTakeawaySpellingWord();
      }
      const word = String($("languageTakeawaySource")?.value || "").trim();
      if (!isSingleEnglishWord(word)) return;
      if (guestBlockTakeawayEdit("登录后才能加入拼写训练。")) return;
      if (btn) {
        btn.disabled = true;
        btn.classList.add("is-busy");
        btn.setAttribute("aria-busy", "true");
        setLanguageTakeawaySpellingGlyph(btn, "busy");
      }
      try {
        const result = await api("/api/writing/spelling-words/add", {
          word,
          chinese_gloss: languageTakeawayChineseForSave(),
        });
        if (btn) {
          btn.dataset.spellingWordId = String(result?.word?.word_id || "");
          btn.classList.add("is-added");
          // Morph "+" → check; the green .is-added state alone is the confirm
          // (reuses the expression-replacement add button's glyph swap — no
          // bespoke scale keyframe, which read as "distorted" on click).
          setLanguageTakeawaySpellingGlyph(btn, "check");
          btn.disabled = false;
          btn.classList.remove("is-busy");
          btn.removeAttribute("aria-busy");
          btn.title = "已加入拼写训练 · 点击取消";
          btn.setAttribute("aria-label", "已加入拼写训练，点击取消");
        }
        setLanguageTakeawayStatus("已加入拼写训练");
      } catch (error) {
        if (btn) {
          btn.disabled = false;
          btn.classList.remove("is-busy");
          btn.removeAttribute("aria-busy");
          setLanguageTakeawaySpellingGlyph(btn, "plus");
        }
        setLanguageTakeawayStatus(error.message || "加入拼写训练失败");
      }
    }

    async function removeLanguageTakeawaySpellingWord() {
      const btn = $("languageTakeawaySpellingBtn");
      const wordId = String(btn?.dataset.spellingWordId || "");
      if (!wordId) {
        updateLanguageTakeawaySpellingButton();
        return;
      }
      if (btn) {
        btn.disabled = true;
        btn.classList.add("is-busy");
        btn.setAttribute("aria-busy", "true");
        setLanguageTakeawaySpellingGlyph(btn, "busy");
      }
      try {
        await api(`/api/writing/spelling-words/${encodeURIComponent(wordId)}`, null, { method: "DELETE" });
        updateLanguageTakeawaySpellingButton();
        setLanguageTakeawayStatus("已取消加入拼写训练");
      } catch (error) {
        if (btn) {
          btn.disabled = false;
          btn.classList.remove("is-busy");
          btn.removeAttribute("aria-busy");
          setLanguageTakeawaySpellingGlyph(btn, "check");
        }
        setLanguageTakeawayStatus(error.message || "取消加入拼写训练失败");
      }
    }


    // Browser-TTS the English source of the 划词 popup (the popup's top-right
    // control is now a speaker button instead of a close button).
    function speakLanguageTakeawaySource() {
      const value = String($("languageTakeawaySource")?.value || "").trim();
      if (!value) return;
      if (takeawayPronunciationState.recording) stopTakeawayPronunciationRecording({ abort: true });
      const btn = $("languageTakeawayTtsBtn");
      const done = () => {
        btn?.classList.remove("is-loading", "is-speaking");
        if (btn) {
          btn.disabled = false;
          btn.removeAttribute("aria-busy");
        }
      };
      btn?.classList.remove("is-speaking");
      btn?.classList.add("is-loading");
      if (btn) {
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
      }
      const startSpeaking = () => {
        btn?.classList.remove("is-loading");
        btn?.classList.add("is-speaking");
        if (btn) btn.disabled = false;
      };
      let started = false;
      const result = speakWithBrowserTts(value, {
        onStart: () => {
          started = true;
          startSpeaking();
        },
        onEnd: done,
        onError: done,
        onNoStart: done,
      });
      if (result?.ok && !started) {
        window.setTimeout(() => {
          if (btn?.classList.contains("is-loading")) startSpeaking();
        }, 120);
      }
      if (!result?.ok) done();
    }

    function takeawaySpeechRecognitionCtor() {
      return window.SpeechRecognition || window.webkitSpeechRecognition || null;
    }

    function pronunciationEscapeHtml(value) {
      return String(value || "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;",
      }[char]));
    }

    function pronunciationTokens(value) {
      return String(value || "")
        .toLowerCase()
        .replace(/[’]/g, "'")
        .match(/[a-z]+(?:'[a-z]+)?/g) || [];
    }

    function pronunciationWordDistance(a, b) {
      const left = String(a || "");
      const right = String(b || "");
      const rows = left.length + 1;
      const cols = right.length + 1;
      const dp = Array.from({ length: rows }, () => Array(cols).fill(0));
      for (let i = 0; i < rows; i += 1) dp[i][0] = i;
      for (let j = 0; j < cols; j += 1) dp[0][j] = j;
      for (let i = 1; i < rows; i += 1) {
        for (let j = 1; j < cols; j += 1) {
          const cost = left[i - 1] === right[j - 1] ? 0 : 1;
          dp[i][j] = Math.min(
            dp[i - 1][j] + 1,
            dp[i][j - 1] + 1,
            dp[i - 1][j - 1] + cost
          );
        }
      }
      return dp[left.length][right.length];
    }

    function pronunciationSimilarity(a, b) {
      const maxLen = Math.max(String(a || "").length, String(b || "").length, 1);
      return 1 - (pronunciationWordDistance(a, b) / maxLen);
    }

    function analyzeTakeawayPronunciation(targetText, transcript, durationMs = 0) {
      const targetWords = pronunciationTokens(targetText);
      const spokenWords = pronunciationTokens(transcript);
      const matchedIndexes = new Set();
      const wordResults = targetWords.map((word) => {
        let bestIndex = -1;
        let bestScore = 0;
        for (let index = 0; index < spokenWords.length; index += 1) {
          if (matchedIndexes.has(index)) continue;
          const score = pronunciationSimilarity(word, spokenWords[index]);
          if (score > bestScore) {
            bestScore = score;
            bestIndex = index;
          }
        }
        if (bestIndex >= 0 && bestScore >= 0.72) {
          matchedIndexes.add(bestIndex);
          return {
            word,
            heard: spokenWords[bestIndex],
            status: bestScore >= 0.92 ? "good" : "close",
            score: bestScore,
          };
        }
        return { word, heard: "", status: "missed", score: 0 };
      });
      const correct = wordResults.filter((item) => item.status === "good").length;
      const close = wordResults.filter((item) => item.status === "close").length;
      const matched = correct + close;
      const total = Math.max(targetWords.length, 1);
      const accuracy = Math.round(((correct + close * 0.55) / total) * 100);
      const completeness = Math.round((matched / total) * 100);
      const durationMin = Math.max(Number(durationMs || 0) / 60000, 0.05);
      const wpm = spokenWords.length / durationMin;
      const paceScore = Math.max(0, Math.min(100, 100 - Math.abs(wpm - 125) * 1.15));
      const fluency = Math.round(Math.min(100, paceScore * 0.76 + completeness * 0.24));
      const overall = Math.round(accuracy * 0.55 + completeness * 0.25 + fluency * 0.2);
      return {
        targetWords,
        spokenWords,
        transcript: String(transcript || "").trim(),
        wordResults,
        accuracy,
        completeness,
        fluency,
        overall,
        wpm: Math.round(wpm),
      };
    }

    function setTakeawayPronunciationStatus(message = "", options = {}) {
      const el = $("takeawayPronunciationStatus");
      if (!el) return;
      el.textContent = message;
      el.classList.toggle("is-error", Boolean(options.error));
      el.classList.toggle("is-listening", Boolean(options.listening));
    }

    function setTakeawayPronunciationRecordingState(recording) {
      takeawayPronunciationState.recording = Boolean(recording);
      const btn = $("takeawayPronunciationRecordBtn");
      if (!btn) return;
      btn.classList.toggle("is-recording", Boolean(recording));
      const label = btn.querySelector("span");
      if (label) label.textContent = recording ? "停止并评分" : "重新朗读";
    }

    function renderTakeawayPronunciationAnalysis(analysis) {
      $("takeawayPronunciationScore") && ($("takeawayPronunciationScore").textContent = String(analysis.overall));
      $("takeawayPronunciationAccuracy") && ($("takeawayPronunciationAccuracy").textContent = `${analysis.accuracy}`);
      $("takeawayPronunciationCompleteness") && ($("takeawayPronunciationCompleteness").textContent = `${analysis.completeness}`);
      $("takeawayPronunciationFluency") && ($("takeawayPronunciationFluency").textContent = `${analysis.fluency}`);
      const words = $("takeawayPronunciationWords");
      if (words) {
        words.innerHTML = analysis.wordResults.map((item) => `
          <span class="takeaway-pronunciation-word is-${item.status}" title="${pronunciationEscapeHtml(item.heard ? `识别为 ${item.heard}` : "未识别到")}">
            ${pronunciationEscapeHtml(item.word)}
          </span>
        `).join("");
      }
      const transcript = $("takeawayPronunciationTranscript");
      if (transcript) transcript.textContent = analysis.transcript || "没有识别到清晰内容";
      $("takeawayPronunciationResult")?.classList.remove("hidden");
      setTakeawayPronunciationStatus(`完成。语速约 ${analysis.wpm} wpm，可以继续重复练。`);
    }

    function resetTakeawayPronunciationDialog(textValue) {
      const target = $("takeawayPronunciationTarget");
      if (target) target.textContent = textValue;
      $("takeawayPronunciationResult")?.classList.add("hidden");
      const words = $("takeawayPronunciationWords");
      if (words) words.innerHTML = "";
      const transcript = $("takeawayPronunciationTranscript");
      if (transcript) transcript.textContent = "";
      ["takeawayPronunciationScore", "takeawayPronunciationAccuracy", "takeawayPronunciationCompleteness", "takeawayPronunciationFluency"].forEach((id) => {
        const el = $(id);
        if (el) el.textContent = "--";
      });
      const btn = $("takeawayPronunciationRecordBtn");
      const label = btn?.querySelector("span");
      if (label) label.textContent = "开始朗读";
      btn?.classList.remove("is-recording");
      setTakeawayPronunciationStatus("点击开始，按原句完整朗读一遍。");
    }

    function openTakeawayPronunciationDialog() {
      const textValue = String($("languageTakeawaySource")?.value || "").trim();
      if (!textValue) {
        setLanguageTakeawayStatus("先选中或输入一句英文。", { error: true, clear: true });
        return;
      }
      interruptTakeawaySpeechPlayback();
      takeawayPronunciationState.targetText = textValue;
      takeawayPronunciationState.finalTranscript = "";
      resetTakeawayPronunciationDialog(textValue);
      const dialog = $("takeawayPronunciationDialog");
      dialog?.classList.remove("hidden");
      if (!takeawaySpeechRecognitionCtor()) {
        setTakeawayPronunciationStatus("当前浏览器不支持语音识别；请用 Chrome 或 Edge 打开后再练。", { error: true });
      }
    }

    function stopTakeawayPronunciationRecording(options = {}) {
      const recognition = takeawayPronunciationState.recognition;
      if (recognition && takeawayPronunciationState.recording) {
        try {
          if (options.abort) recognition.abort();
          else recognition.stop();
        } catch (error) {
          console.warn("Takeaway pronunciation recognition stop failed", error);
        }
      }
      setTakeawayPronunciationRecordingState(false);
    }

    function closeTakeawayPronunciationDialog() {
      stopTakeawayPronunciationRecording({ abort: true });
      $("takeawayPronunciationDialog")?.classList.add("hidden");
      setTakeawayPronunciationStatus("");
    }

    function startTakeawayPronunciationRecording() {
      if (takeawayPronunciationState.recording) {
        stopTakeawayPronunciationRecording();
        return;
      }
      const Recognition = takeawaySpeechRecognitionCtor();
      if (!Recognition) {
        setTakeawayPronunciationStatus("当前浏览器不支持语音识别；请用 Chrome 或 Edge 打开后再练。", { error: true });
        return;
      }
      const targetText = String(takeawayPronunciationState.targetText || $("languageTakeawaySource")?.value || "").trim();
      if (!targetText) {
        setTakeawayPronunciationStatus("没有可练习的英文句子。", { error: true });
        return;
      }
      interruptTakeawaySpeechPlayback();
      let recognition;
      try {
        recognition = new Recognition();
      } catch (error) {
        setTakeawayPronunciationStatus("语音识别启动失败，请检查浏览器麦克风权限。", { error: true });
        return;
      }
      takeawayPronunciationState.recognition = recognition;
      takeawayPronunciationState.targetText = targetText;
      takeawayPronunciationState.finalTranscript = "";
      takeawayPronunciationState.startedAt = performance.now();
      recognition.lang = "en-US";
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 3;
      recognition.onstart = () => {
        setTakeawayPronunciationRecordingState(true);
        setTakeawayPronunciationStatus("正在听，读完后会自动评分。", { listening: true });
      };
      recognition.onresult = (event) => {
        let finalText = "";
        let interimText = "";
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index];
          const text = result?.[0]?.transcript || "";
          if (result?.isFinal) finalText += ` ${text}`;
          else interimText += ` ${text}`;
        }
        if (finalText.trim()) takeawayPronunciationState.finalTranscript += ` ${finalText.trim()}`;
        if (interimText.trim()) {
          const transcript = $("takeawayPronunciationTranscript");
          if (transcript) transcript.textContent = interimText.trim();
          $("takeawayPronunciationResult")?.classList.remove("hidden");
        }
      };
      recognition.onerror = (event) => {
        const message = event?.error === "not-allowed"
          ? "麦克风权限被拒绝，允许权限后再试。"
          : `识别失败：${event?.error || "unknown"}`;
        setTakeawayPronunciationStatus(message, { error: true });
      };
      recognition.onend = () => {
        const durationMs = Math.max(1, performance.now() - takeawayPronunciationState.startedAt);
        setTakeawayPronunciationRecordingState(false);
        const transcript = String(takeawayPronunciationState.finalTranscript || $("takeawayPronunciationTranscript")?.textContent || "").trim();
        if (!transcript) {
          setTakeawayPronunciationStatus("没有识别到清晰朗读，靠近麦克风再试一次。", { error: true });
          return;
        }
        renderTakeawayPronunciationAnalysis(analyzeTakeawayPronunciation(targetText, transcript, durationMs));
      };
      try {
        recognition.start();
      } catch (error) {
        setTakeawayPronunciationRecordingState(false);
        setTakeawayPronunciationStatus("语音识别已经在启动中，稍等一秒再点。", { error: true });
      }
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

    // Re-clamp the popup at its current position. The popup grows/shrinks when the
    // dictionary toggles EN/中文 or a translation arrives, so its size changes
    // after placement — without this it can grow off the bottom/right edge.
    function clampLanguageTakeawayPopupIntoView() {
      const popup = $("languageTakeawayPopup");
      if (!popup || popup.classList.contains("hidden")) return;
      const rect = popup.getBoundingClientRect();
      placeLanguageTakeawayPopup(rect.left, rect.top);
    }

    // Bind once: a ResizeObserver keeps the popup on-screen through any size
    // change (EN/中文 swap, source auto-grow), and window resize re-clamps too.
    function ensureLanguageTakeawayPopupClamp() {
      const popup = $("languageTakeawayPopup");
      if (!popup || state.languageTakeaway._popupClampBound) return;
      if (typeof ResizeObserver !== "undefined") {
        const observer = new ResizeObserver(() => clampLanguageTakeawayPopupIntoView());
        observer.observe(popup);
      }
      window.addEventListener("resize", clampLanguageTakeawayPopupIntoView);
      state.languageTakeaway._popupClampBound = true;
    }

    async function openLanguageTakeawayPopup() {
      if (guestBlockTakeawayEdit("登录后才能把划选的表达保存到你的 Takeaway。")) return;
      const textValue = state.languageTakeaway.selectedText;
      if (!textValue) return;
      const popup = $("languageTakeawayPopup");
      const trigger = $("languageTakeawayTrigger");
      if (!popup || !trigger) return;
      $("languageTakeawaySource").value = textValue;
      $("languageTakeawayChinese").value = "";
      resetLanguageTakeawayDictionary();
      setLanguageTakeawayStatus("翻译中...", { loading: true });
      const triggerRect = trigger.getBoundingClientRect();
      popup.classList.remove("hidden");
      ensureLanguageTakeawayPopupClamp();
      placeLanguageTakeawayPopup(triggerRect.left, triggerRect.bottom + 8);
      autosizeLanguageTakeawaySource();
      updateLanguageTakeawaySpellingButton();
      hideLanguageTakeawayTrigger();
      // Single English word -> offline dictionary; otherwise full-sentence translation.
      if (isSingleEnglishWord(textValue)) {
        const found = await lookupLanguageTakeawayDictionary(textValue);
        if (found) return;
      }
      await translateLanguageTakeawaySource(textValue);
    }

    // Offline dictionary lookup for a single English word. Fills the Chinese
    // box with the dictionary senses (so saving + the spelling gloss work) and
    // shows the phonetic in the status line. Returns false on miss so the caller
    // can fall back to online sentence translation.
    async function lookupLanguageTakeawayDictionary(word) {
      const w = String(word || "").trim();
      if (!w) return false;
      setLanguageTakeawayStatus("查询中...", { loading: true });
      try {
        const result = await api(`/api/dictionary/lookup?word=${encodeURIComponent(w)}`);
        const entry = result && result.found ? result.entry : null;
        if (!entry) return false;
        const senses = Array.isArray(entry.senses) && entry.senses.length
          ? entry.senses
          : (entry.translation ? [entry.translation] : []);
        if (!senses.length) return false;
        const chineseEl = $("languageTakeawayChinese");
        const chineseText = senses.slice(0, 6).join("\n");
        const englishText = String(entry.definition || "").trim();
        if (chineseEl) chineseEl.value = chineseText;
        setLanguageTakeawayDictionaryEntry({ chineseText, englishText });
        autosizeLanguageTakeawaySource();
        // Keep the phonetic, drop the "离线词典" label the user found noisy.
        setLanguageTakeawayStatus(entry.phonetic ? `[${entry.phonetic}]` : "");
        return true;
      } catch (_error) {
        return false;
      }
    }

    // Enter in the 划词 source field: a single English word goes through the
    // dictionary (same as opening the popup on one word); anything else uses
    // full-sentence translation.
    async function resolveLanguageTakeawaySource() {
      const value = String($("languageTakeawaySource")?.value || "").trim();
      if (!value) {
        setLanguageTakeawayStatus("原文为空。");
        return;
      }
      if (isSingleEnglishWord(value)) {
        const found = await lookupLanguageTakeawayDictionary(value);
        if (found) return;
      }
      await translateLanguageTakeawaySource(value);
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
        resetLanguageTakeawayDictionary();
        $("languageTakeawaySource").value = result.source_text || sourceText;
        $("languageTakeawayChinese").value = result.chinese_text || "";
        autosizeLanguageTakeawaySource();
        setLanguageTakeawayStatus(languageTakeawayTranslationStatus(result));
      } catch (error) {
        setLanguageTakeawayStatus(error.message || "翻译失败，可手动填写中文");
      }
    }

    async function saveLanguageTakeaway() {
      if (guestBlockTakeawayEdit("登录后才能保存到 Takeaway。")) return;
      const sourceText = ($("languageTakeawaySource")?.value || "").trim();
      const chineseText = languageTakeawayChineseForSave();
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
      if (guestBlockTakeawayEdit("登录后才能保存到写作积累。")) return;
      const sourceText = ($("languageTakeawaySource")?.value || "").trim();
      const chineseText = languageTakeawayChineseForSave();
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
      if (guestBlockTakeawayEdit(kind === "writing" ? "登录后才能添加写作积累。" : "登录后才能添加 Takeaway。")) return;
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
      if (guestBlockTakeawayEdit(kind === "writing" ? "登录后才能编辑写作积累。" : "登录后才能编辑 Takeaway。")) return;
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
          <button type="button" class="expression-replacement-add" data-expression-replacement-add="${escapeHtml(item.id)}" aria-label="加入${kind === "language" ? "Takeaway" : "写作积累"}">
            <span aria-hidden="true">+</span>
          </button>
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
      if (guestBlockTakeawayEdit("登录后才能管理你的表达替换。")) return;
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
          button.innerHTML = '<span aria-hidden="true">&#10003;</span>';
          window.setTimeout(() => {
            button.classList.remove("is-added");
            button.innerHTML = '<span aria-hidden="true">+</span>';
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

    function deleteExpressionReplacement(itemId) {
      const kind = activeExpressionReplacementKind();
      const item = expressionReplacementItems(kind).find((entry) => entry.id === itemId);
      if (!item) return;
      const runDelete = async () => {
        const items = expressionReplacementItems(kind).filter((entry) => entry.id !== itemId);
        saveExpressionReplacements(kind, items);
        renderExpressionReplacements(kind);
        setExpressionReplacementStatus("\u6b63\u5728\u540c\u6b65...");
        try {
          await api(expressionReplacementEndpoint(kind, itemId), null, { method: "DELETE" });
          setExpressionReplacementStatus("");
        } catch (error) {
          setExpressionReplacementStatus(`\u672a\u540c\u6b65\uff0c\u4ec5\u672c\u5730\uff1a${error.message || error}`, { error: true });
        }
      };
      if (typeof showConfirmDelete === "function") {
        showConfirmDelete("\u786e\u5b9a\u8981\u5220\u9664\u8fd9\u6761\u8868\u8fbe\u66ff\u6362\u5417\uff1f", runDelete);
        return;
      }
      runDelete();
    }

    function takeawayEditorValues() {
      return {
        // Keep only the 原文 — drop any pasted markdown emphasis (**a** → a).
        sourceText: stripInlineMarkdown(($("takeawayEditSource")?.value || "").trim()).trim(),
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

    // Enter in the add/edit dialog's English field auto-translates and fills the
    // 中文 field — same behaviour as the 划词 popup.
    async function translateTakeawayEditSource() {
      const sourceText = String($("takeawayEditSource")?.value || "").trim();
      if (!sourceText) {
        text("takeawayEditStatus", "原文为空。");
        return;
      }
      text("takeawayEditStatus", "翻译中...");
      try {
        const result = await api("/api/language-takeaways/translate", { text: sourceText });
        if ($("takeawayEditSource")) $("takeawayEditSource").value = result.source_text || sourceText;
        if ($("takeawayEditChinese")) $("takeawayEditChinese").value = result.chinese_text || "";
        text("takeawayEditStatus", languageTakeawayTranslationStatus(result));
      } catch (error) {
        text("takeawayEditStatus", error.message || "翻译失败，可手动填写中文");
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
      const targetIds = p2EquivalentQuestionIds(targetId);
      const card = (state.p2Corpus.currentPart2Cards || []).find((item) => {
        const ids = p2EquivalentQuestionIds(p2BankQuestionId(item));
        return ids.some((id) => targetIds.includes(id));
      });
      if (card) return { ...card };
      return null;
    }

    function p2EquivalentQuestionIds(questionId) {
      const value = String(questionId || "").trim();
      if (!value) return [];
      const ids = [value];
      if (value.startsWith("p2:")) ids.push(`p2cue:${value.slice(3)}`);
      if (value.startsWith("p2cue:")) ids.push(`p2:${value.slice(6)}`);
      return [...new Set(ids)];
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
      const fullEntry = findP2CorpusEntry(cardId);
      if (fullEntry) {
        return {
          ...fullEntry,
          source_type: "bank",
          entry_id: fullEntry.entry_id || cardId,
          cue_id: fullEntry.cue_id || cardId,
          canonical_entry_id: fullEntry.canonical_entry_id || cardId,
        };
      }
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

    function fetchP2BankCorpusPayload(questionId, options = {}) {
      const key = String(questionId || "").trim();
      if (!key) return Promise.resolve(null);
      ensureP2BankCacheScope();
      const force = Boolean(options.force);
      if (!force && p2BankCorpusCache.has(key)) return p2BankCorpusCache.get(key);
      const cached = p2BankLsRead(P2BANK_LS_PREFIX, key);
      if (!force && cached) {
        const promise = Promise.resolve(cached.payload);
        p2BankCorpusCache.set(key, promise);
        scheduleIdle(() => revalidateP2BankCorpus(key), 50);
        return promise;
      }
      const netPromise = api(`/api/p2-bank-corpus/${encodeURIComponent(key)}`).then((payload) => {
        p2BankLsWrite(P2BANK_LS_PREFIX, key, payload);
        const canonicalKey = String(payload?.question_id || "").trim();
        if (canonicalKey && canonicalKey !== key) {
          p2BankCorpusCache.set(canonicalKey, Promise.resolve(payload));
          p2BankLsWrite(P2BANK_LS_PREFIX, canonicalKey, payload);
        }
        return payload;
      });
      p2BankCorpusCache.set(key, netPromise);
      return netPromise;
    }

    function fetchP2BankP3Payload(questionId) {
      const key = String(questionId || "").trim();
      if (!key) return Promise.resolve(null);
      ensureP2BankCacheScope();
      for (const id of p2EquivalentQuestionIds(key)) {
        if (p2BankP3Cache.has(id)) {
          const promise = p2BankP3Cache.get(id);
          if (id !== key) p2BankP3Cache.set(key, promise);
          return promise;
        }
      }
      const cached = p2BankLsReadAny(P3BANK_LS_PREFIX, key);
      if (cached) {
        const promise = Promise.resolve(cached.payload);
        p2BankP3Cache.set(key, promise);
        scheduleIdle(() => revalidateP2BankP3(key), 50);
        return promise;
      }
      const netPromise = api(`/api/p3-bank-corpus/${encodeURIComponent(key)}`).then((payload) => {
        p2BankLsWrite(P3BANK_LS_PREFIX, key, payload);
        const canonicalKey = String(payload?.p2_question_id || payload?.question_id || "").trim();
        if (canonicalKey && canonicalKey !== key) {
          p2BankP3Cache.set(canonicalKey, Promise.resolve(payload));
          p2BankLsWrite(P3BANK_LS_PREFIX, canonicalKey, payload);
        }
        return payload;
      });
      p2BankP3Cache.set(key, netPromise);
      return netPromise;
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

    // --- Brainstorm 素材标签（A/B/C 或 A1/B2 这类），内联存进 brainstorm_idea 字符串开头 ---
    let p2BrainstormActiveFilter = "";
    const P2_BRAINSTORM_EMPTY_FILTER = "__empty__"; // 筛选「空」：当前没写灵感的题

    function p2NormalizeBrainstormTag(token) {
      const t = String(token || "").trim().toUpperCase();
      return /^[A-Z]\d?$/.test(t) ? t : "";
    }

    // 把存储字符串解析成 { tags:[], text:"" }：开头连续的“字母+可选一位数字 + 空格”视为标签。
    function p2ParseBrainstormValue(raw) {
      let rest = String(raw || "");
      const tags = [];
      const seen = new Set();
      let m;
      // 仅大写字母（A/B/C 或 A1/B2）才当标签，避免把英文冠词 "a "/"the " 误判成标签。
      // 末尾用 (\s+|$)：单走的 "B"（保存后没有尾随空格）再次打开也能识别成标签。
      while ((m = rest.match(/^\s*([A-Z]\d?)(\s+|$)/))) {
        const tag = p2NormalizeBrainstormTag(m[1]);
        if (!tag) break;
        if (!seen.has(tag)) { seen.add(tag); tags.push(tag); }
        rest = rest.slice(m[0].length);
      }
      return { tags, text: rest };
    }

    function p2SerializeBrainstormValue(tags, text) {
      const seen = new Set();
      const cleanTags = [];
      (tags || []).forEach((raw) => {
        const tag = p2NormalizeBrainstormTag(raw);
        if (tag && !seen.has(tag)) { seen.add(tag); cleanTags.push(tag); }
      });
      const body = String(text || "");
      if (!cleanTags.length) return body;
      return body ? `${cleanTags.join(" ")} ${body}` : cleanTags.join(" ");
    }

    function p2BrainstormTagChipHtml(tag) {
      const t = escapeHtml(tag);
      return `<span class="p2-brainstorm-tag" data-tag="${t}">${t}<button type="button" class="p2-brainstorm-tag-x" data-p2-brainstorm-tag-remove aria-label="删除标签 ${t}">×</button></span>`;
    }

    function p2BrainstormRowTags(row) {
      return Array.from(row?.querySelectorAll(".p2-brainstorm-tag") || []).map((el) => el.dataset.tag);
    }

    // 行的完整存储值 = 标签（开头）+ 正文。
    function p2BrainstormRowValue(row) {
      if (!row) return "";
      const text = row.querySelector("[data-p2-brainstorm-input]")?.value || "";
      return p2SerializeBrainstormValue(p2BrainstormRowTags(row), text);
    }

    function p2BrainstormFieldValue(input) {
      const field = input?.closest?.(".p2-brainstorm-tagfield");
      if (!field) return String(input?.value || "");
      const tags = Array.from(field.querySelectorAll(".p2-brainstorm-tag")).map((el) => el.dataset.tag);
      return p2SerializeBrainstormValue(tags, input?.value || "");
    }

    // 把存储值渲染进「正文编辑」里的串题灵感字段（标签 chip + 正文）。
    function setP2CorpusBrainstormField(rawValue) {
      const input = $("p2CorpusBrainstormIdea");
      if (!input) return;
      const parsed = p2ParseBrainstormValue(rawValue);
      const tagsEl = input.closest(".p2-brainstorm-tagfield")?.querySelector(".p2-brainstorm-tags");
      if (tagsEl) tagsEl.innerHTML = parsed.tags.map(p2BrainstormTagChipHtml).join("");
      input.value = parsed.text;
    }

    function p2CorpusBrainstormIdeaValue() {
      const input = $("p2CorpusBrainstormIdea");
      return input ? p2BrainstormFieldValue(input) : "";
    }

    // 只在输入框开头出现“标签令牌 + 空格”时，把它转成 chip 并从文本里抠掉；中间输入不触发。
    function maybeConvertLeadingBrainstormTag(input) {
      // 只在开头出现大写标签令牌（A/B/C/A1/B2）+ 空格时解析；小写或中间输入都不触发。
      const match = String(input.value || "").match(/^([A-Z]\d?)\s+(.*)$/);
      if (!match) return false;
      const tag = p2NormalizeBrainstormTag(match[1]);
      if (!tag) return false;
      const tagsEl = input.closest(".p2-brainstorm-tagfield")?.querySelector(".p2-brainstorm-tags");
      if (!tagsEl) return false;
      const existing = Array.from(tagsEl.querySelectorAll(".p2-brainstorm-tag")).map((el) => el.dataset.tag);
      if (!existing.includes(tag)) {
        tagsEl.insertAdjacentHTML("beforeend", p2BrainstormTagChipHtml(tag));
      }
      input.value = match[2];
      try { input.setSelectionRange(0, 0); } catch (_e) {}
      // 筛选栏只属于 Brainstorm 列表窗口；编辑器字段里不刷新。
      if (input.closest("#p2BrainstormList")) {
        renderP2BrainstormFilterBar();
        applyP2BrainstormFilter();
      }
      return true;
    }

    function p2BrainstormAllTags() {
      const set = new Set();
      (state.p2Corpus.currentPart2Cards || []).forEach((item) => {
        p2ParseBrainstormValue(item.brainstorm_idea).tags.forEach((t) => set.add(t));
      });
      document.querySelectorAll("#p2BrainstormList .p2-brainstorm-tag").forEach((el) => set.add(el.dataset.tag));
      return Array.from(set).sort();
    }

    // 「没灵感」= 既没有正文也没有标签。只打了标签（如单走的 B）算已处理，不算没灵感。
    function p2BrainstormRowIsEmpty(row) {
      const hasText = !!String(row?.querySelector("[data-p2-brainstorm-input]")?.value || "").trim();
      const hasTags = p2BrainstormRowTags(row).length > 0;
      return !hasText && !hasTags;
    }

    function p2BrainstormHasEmptyRow() {
      return Array.from(document.querySelectorAll("#p2BrainstormList .p2-brainstorm-row")).some(p2BrainstormRowIsEmpty);
    }

    // 当前筛选命中的题数。
    function p2BrainstormFilteredCount() {
      const rows = Array.from(document.querySelectorAll("#p2BrainstormList .p2-brainstorm-row"));
      if (!p2BrainstormActiveFilter) return rows.length;
      if (p2BrainstormActiveFilter === P2_BRAINSTORM_EMPTY_FILTER) return rows.filter(p2BrainstormRowIsEmpty).length;
      return rows.filter((row) => p2BrainstormRowTags(row).includes(p2BrainstormActiveFilter)).length;
    }

    // 当前筛选对应的复制标签：无筛选→全部、空筛选→没灵感、否则就是标签名。
    function p2BrainstormFilterLabel() {
      if (!p2BrainstormActiveFilter) return "全部";
      if (p2BrainstormActiveFilter === P2_BRAINSTORM_EMPTY_FILTER) return "没灵感";
      return p2BrainstormActiveFilter;
    }

    function updateP2BrainstormCopyLabel() {
      const btn = $("copyP2BrainstormBtn");
      if (btn) btn.textContent = `复制「${p2BrainstormFilterLabel()}」`;
    }

    function renderP2BrainstormFilterBar() {
      const bar = $("p2BrainstormFilterBar");
      if (!bar) { updateP2BrainstormCopyLabel(); return; }
      const tags = p2BrainstormAllTags();
      const hasEmpty = p2BrainstormHasEmptyRow();
      // 选中的筛选若已不存在了，回落到「全部」。
      if (p2BrainstormActiveFilter === P2_BRAINSTORM_EMPTY_FILTER) {
        if (!hasEmpty) p2BrainstormActiveFilter = "";
      } else if (p2BrainstormActiveFilter && !tags.includes(p2BrainstormActiveFilter)) {
        p2BrainstormActiveFilter = "";
      }
      if (!tags.length && !hasEmpty) {
        bar.hidden = true;
        bar.innerHTML = "";
        updateP2BrainstormCopyLabel();
        return;
      }
      bar.hidden = false;
      const chip = (label, value) =>
        `<button type="button" class="p2-brainstorm-filter-chip${p2BrainstormActiveFilter === value ? " is-active" : ""}" data-p2-brainstorm-filter="${escapeHtml(value)}">${escapeHtml(label)}</button>`;
      bar.innerHTML =
        `<span class="p2-brainstorm-filter-label">筛选</span>` +
        chip("全部", "") +
        tags.map((t) => chip(t, t)).join("") +
        (hasEmpty ? chip("没灵感", P2_BRAINSTORM_EMPTY_FILTER) : "") +
        `<span class="p2-brainstorm-filter-count">共 ${p2BrainstormFilteredCount()} 道「${escapeHtml(p2BrainstormFilterLabel())}」</span>`;
      updateP2BrainstormCopyLabel();
    }

    // Bumped on every filter pass so a stale exit-animation handler can't hide a
    // row that a newer pass has since decided to keep visible.
    let p2BrainstormFilterGen = 0;

    function applyP2BrainstormFilter(options = {}) {
      const animate = options.animate !== false;
      const gen = ++p2BrainstormFilterGen;
      Array.from(document.querySelectorAll("#p2BrainstormList .p2-brainstorm-row")).forEach((row) => {
        let show;
        if (!p2BrainstormActiveFilter) show = true;
        else if (p2BrainstormActiveFilter === P2_BRAINSTORM_EMPTY_FILTER) show = p2BrainstormRowIsEmpty(row);
        else show = p2BrainstormRowTags(row).includes(p2BrainstormActiveFilter);
        const hidden = row.classList.contains("is-filtered-out");
        if (!animate) {
          row.classList.remove("is-filtering-in", "is-filtering-out");
          row.classList.toggle("is-filtered-out", !show);
          return;
        }
        if (show && hidden) {
          // Reveal: drop the hide flag and play the fade-in.
          row.classList.remove("is-filtered-out", "is-filtering-out");
          row.classList.add("is-filtering-in");
          row.addEventListener("animationend", (e) => {
            if (e.animationName === "p2BrainstormFilterIn") row.classList.remove("is-filtering-in");
          }, { once: true });
        } else if (!show && !hidden) {
          // Hide: play the fade-out, then collapse it once the animation ends.
          row.classList.remove("is-filtering-in");
          row.classList.add("is-filtering-out");
          row.addEventListener("animationend", (e) => {
            if (e.animationName !== "p2BrainstormFilterOut") return;
            row.classList.remove("is-filtering-out");
            if (gen === p2BrainstormFilterGen) row.classList.add("is-filtered-out");
          }, { once: true });
        }
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
      return String(entry.brainstorm_idea || "").trim() !== p2BrainstormFieldValue(input).trim();
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
        const parsedIdea = p2ParseBrainstormValue(item.brainstorm_idea);
        const chipsHtml = parsedIdea.tags.map(p2BrainstormTagChipHtml).join("");
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
              ${hasCue ? `
                <div class="p2-brainstorm-cue-detail" data-p2-brainstorm-detail="${escapeHtml(questionId)}" hidden>
                  <div class="p2-brainstorm-detail-head">
                    <strong>题目要求</strong>
                    <div class="p2-brainstorm-detail-actions">
                      <button type="button" class="p2-brainstorm-practice-btn" data-p2-brainstorm-practice="${escapeHtml(questionId)}" aria-label="在新标签页练习此题" title="练习此题">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/></svg>
                      </button>
                      <button type="button" class="ghost p2-brainstorm-edit-body" data-p2-brainstorm-edit-body="${escapeHtml(questionId)}">编辑正文</button>
                    </div>
                  </div>
                  ${detailHtml}
                </div>
              ` : ""}
            </div>
            <div class="p2-brainstorm-tagfield" data-p2-brainstorm-field="${escapeHtml(questionId)}">
              <span class="p2-brainstorm-tags">${chipsHtml}</span>
              <input
                class="p2-brainstorm-input"
                data-p2-brainstorm-input="${escapeHtml(questionId)}"
                type="text"
                value="${escapeHtml(parsedIdea.text)}"
                placeholder="一句灵感：人物 / 地点 / 经历 / 可串题角度"
                autocomplete="off"
              >
            </div>
          </div>
        `;
      }).join("");
      // Rebuilding innerHTML wipes the per-row is-filtered-out flags, so the active
      // filter must be re-applied here — otherwise any caller that re-renders (e.g.
      // returning from the body editor) silently drops the filter and every tag
      // reappears. Keeping it inside the renderer makes every call self-consistent.
      renderP2BrainstormFilterBar();
      applyP2BrainstormFilter({ animate: false });
    }

    async function openP2BrainstormDialog() {
      if (!state.account.authenticated) {
        guestGate("登录后才能记录和复用串题灵感 Brainstorm。", "p2Corpus");
        return;
      }
      if (!state.p2Corpus.loaded) {
        text("p2BrainstormStatus", "正在加载题卡...");
        await loadP2Corpus({ force: true });
      }
      p2BrainstormActiveFilter = "";  // open in 「全部」; reset before the render applies it
      renderP2BrainstormRows();
      if ($("p2BrainstormSearchInput")) $("p2BrainstormSearchInput").value = "";
      updateP2BrainstormSearch();
      const count = (state.p2Corpus.currentPart2Cards || []).filter((item) => String(item.brainstorm_idea || "").trim()).length;
      text("p2BrainstormStatus", count ? `已填写 ${count} 条灵感` : "");
      // Clear the body-editor-return flag so a fresh open plays the entrance again.
      $("p2BrainstormDialog")?.classList.remove("no-entrance", "hidden");
      // One-shot staggered row entrance: tag the list while the dialog opens, then
      // drop the flag so later filtering/searching re-flows the rows instantly.
      const listEl = $("p2BrainstormList");
      if (listEl) {
        listEl.classList.add("is-entering");
        window.setTimeout(() => listEl.classList.remove("is-entering"), 700);
      }
      setTimeout(() => $("p2BrainstormList")?.querySelector(".p2-brainstorm-input")?.focus(), 0);
    }

    function closeP2BrainstormDialog() {
      flushP2BrainstormAutosaves();
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

    function upsertP2CorpusEntryLocal(saved = {}) {
      const entryId = String(saved.entry_id || "").trim();
      if (!entryId) return null;
      let updated = null;
      const categories = state.p2Corpus.categories || [];
      let found = false;
      state.p2Corpus.categories = categories.map((category) => {
        const items = category.items || [];
        const nextItems = items.map((item) => {
          if (String(item.entry_id || "").trim() !== entryId) return item;
          found = true;
          updated = {
            ...item,
            ...saved,
            label: category.label || item.label || saved.label,
            p3_follow_up_text: saved.p3_follow_up_text ?? saved.metadata?.p3_follow_up_text ?? item.p3_follow_up_text ?? "",
          };
          return updated;
        });
        return { ...category, items: nextItems };
      });
      if (!found) {
        const categoryId = saved.category || "special";
        let inserted = false;
        state.p2Corpus.categories = (state.p2Corpus.categories || []).map((category) => {
          if (inserted || category.category !== categoryId) return category;
          updated = {
            ...saved,
            label: category.label || saved.label,
            p3_follow_up_text: saved.p3_follow_up_text ?? saved.metadata?.p3_follow_up_text ?? "",
          };
          inserted = true;
          return { ...category, items: [updated, ...(category.items || [])] };
        });
        if (!inserted) {
          updated = {
            ...saved,
            label: saved.label || "P2",
            p3_follow_up_text: saved.p3_follow_up_text ?? saved.metadata?.p3_follow_up_text ?? "",
          };
          state.p2Corpus.categories = [
            { category: categoryId, label: saved.label || categoryId, items: [updated] },
            ...(state.p2Corpus.categories || []),
          ];
        }
      }
      state.p2Corpus.mutationSeq = (state.p2Corpus.mutationSeq || 0) + 1;
      state.p2Corpus.loadingPromise = null;
      return updated;
    }

    function applyP2BankCorpusSavedLocal(questionId, saved = {}) {
      const targetId = String(questionId || "").trim();
      if (!targetId) return;
      const corpusText = saved.corpus_text ?? "";
      const targetIds = p2EquivalentQuestionIds(targetId);
      targetIds.forEach((id) => {
        p2BankCorpusCache.set(id, Promise.resolve(saved));
        p2BankLsWrite(P2BANK_LS_PREFIX, id, saved);
        p2BankBatchRequested.add(id);
      });
      state.p2Corpus.currentPart2Cards = (state.p2Corpus.currentPart2Cards || []).map((item) => {
        const ids = p2EquivalentQuestionIds(p2BankQuestionId(item));
        if (!ids.some((id) => targetIds.includes(id))) return item;
        return {
          ...item,
          corpus_text: corpusText,
          material_text: corpusText,
          brainstorm_idea: saved.brainstorm_idea ?? item.brainstorm_idea ?? "",
          has_material: Boolean(String(corpusText || "").trim()),
          has_bank_corpus: Boolean(String(corpusText || "").trim()),
        };
      });
      if (state.p2Corpus.activeEntry && p2EquivalentQuestionIds(p2BankQuestionId(state.p2Corpus.activeEntry)).some((id) => targetIds.includes(id))) {
        state.p2Corpus.activeEntry = {
          ...state.p2Corpus.activeEntry,
          ...saved,
          material_text: corpusText,
          corpus_text: corpusText,
        };
      }
      state.p2Corpus.mutationSeq = (state.p2Corpus.mutationSeq || 0) + 1;
      state.p2Corpus.loadingPromise = null;
    }

    function applyP2BankP3SavedLocal(questionId, items = []) {
      const targetId = String(questionId || "").trim();
      if (!targetId) return;
      const nextItems = Array.isArray(items) ? items : [];
      const savedCount = nextItems.filter((item) => String(item.corpus_text || "").trim()).length;
      const payload = {
        p2_question_id: targetId,
        items: nextItems,
        count: nextItems.length,
      };
      p2BankP3Cache.set(targetId, Promise.resolve(payload));
      p2BankLsWrite(P3BANK_LS_PREFIX, targetId, payload);
      p2BankBatchRequested.add(targetId);
      updateP2CardP3CountLocal(targetId, savedCount, nextItems.length);
    }

    // Mirror the P1 pattern: after a P3 save, update the seasonal card's
    // filled/total counts in place so the progress bar moves instantly, instead
    // of waiting on (or depending on) a full loadP2Corpus refetch. Pass
    // totalCount when known (e.g. the editor loaded every follow-up) so clearing
    // the last answer drops the bar without a refresh.
    function updateP2CardP3CountLocal(questionId, savedCount, totalCount) {
      const targetId = String(questionId || "").trim();
      if (!targetId) return;
      const nextSaved = Math.max(0, Number(savedCount) || 0);
      state.p2Corpus.currentPart2Cards = (state.p2Corpus.currentPart2Cards || []).map((item) => {
        if (p2BankQuestionId(item) !== targetId) return item;
        const total = Number.isFinite(totalCount)
          ? Math.max(Number(totalCount) || 0, nextSaved)
          : Math.max(Number(item.p3_follow_up_count) || 0, nextSaved);
        return {
          ...item,
          p3_follow_up_count: total,
          p3_follow_up_saved_count: Math.min(nextSaved, total),
          has_p3_follow_up: nextSaved > 0,
        };
      });
      // This is a local mutation that must win against any GET snapshotted before
      // it — bump the generation and drop the in-flight load so the background
      // reconcile refetches fresh instead of replaying a pre-save snapshot.
      state.p2Corpus.mutationSeq = (state.p2Corpus.mutationSeq || 0) + 1;
      state.p2Corpus.loadingPromise = null;
    }

    const p2BrainstormDirtyValues = new Map();
    const p2BrainstormAutosaveTimers = new Map();
    let p2BrainstormAutosaveChain = Promise.resolve();
    let p2BrainstormSearchMatches = [];
    let p2BrainstormSearchIndex = -1;
    let p2BrainstormReturnAfterBodyEditor = false;
    let p2BrainstormReturnQuestionId = "";

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

    function p2BrainstormFilledCount() {
      return (state.p2Corpus.currentPart2Cards || []).filter((item) => String(item.brainstorm_idea || "").trim()).length;
    }

    function persistP2BrainstormDirty(questionId) {
      const targetId = String(questionId || "").trim();
      if (!targetId || !p2BrainstormDirtyValues.has(targetId)) return;
      const nextIdea = p2BrainstormDirtyValues.get(targetId);
      p2BrainstormDirtyValues.delete(targetId);
      const timer = p2BrainstormAutosaveTimers.get(targetId);
      if (timer) window.clearTimeout(timer);
      p2BrainstormAutosaveTimers.delete(targetId);
      text("p2BrainstormStatus", "自动保存中...");
      p2BrainstormAutosaveChain = p2BrainstormAutosaveChain
        .catch(() => null)
        .then(async () => {
          await saveP2BrainstormIdea(targetId, nextIdea, { silent: true });
          if (p2BrainstormDirtyValues.has(targetId)) {
            updateP2BrainstormCardLocal(targetId, p2BrainstormDirtyValues.get(targetId));
            return;
          }
          renderP2CorpusTopics();
          text("p2BrainstormStatus", `已自动保存 · ${p2BrainstormFilledCount()} 条灵感`);
        })
        .catch((error) => {
          p2BrainstormDirtyValues.set(targetId, nextIdea);
          text("p2BrainstormStatus", error.message || String(error));
        });
    }

    function scheduleP2BrainstormAutosave(input, delay = 700) {
      const targetId = String(input?.dataset?.p2BrainstormInput || "").trim();
      if (!targetId) return;
      const nextIdea = p2BrainstormFieldValue(input);
      updateP2BrainstormCardLocal(targetId, nextIdea);
      p2BrainstormDirtyValues.set(targetId, nextIdea);
      const existing = p2BrainstormAutosaveTimers.get(targetId);
      if (existing) window.clearTimeout(existing);
      p2BrainstormAutosaveTimers.set(targetId, window.setTimeout(() => {
        persistP2BrainstormDirty(targetId);
      }, delay));
      text("p2BrainstormStatus", "已修改，正在自动保存...");
    }

    function flushP2BrainstormAutosaves() {
      Array.from(p2BrainstormDirtyValues.keys()).forEach((questionId) => persistP2BrainstormDirty(questionId));
    }

    async function openP2BrainstormBodyEditor(questionId = "") {
      const targetId = String(questionId || "").trim();
      if (!targetId) return;
      const entry = p2BrainstormEntryForQuestion(targetId);
      if (!p2BankQuestionId(entry)) return;
      const input = document.querySelector(`[data-p2-brainstorm-input="${CSS.escape(targetId)}"]`);
      if (input && p2BrainstormInputChanged(input)) {
        p2BrainstormDirtyValues.set(targetId, input.value || "");
        persistP2BrainstormDirty(targetId);
        await p2BrainstormAutosaveChain.catch(() => null);
      }
      p2BrainstormReturnAfterBodyEditor = true;
      p2BrainstormReturnQuestionId = targetId;
      closeP2BrainstormDetails();
      $("p2BrainstormDialog")?.classList.add("hidden");
      try {
        await openP2BankCorpusEditor({
          ...entry,
          source_type: "bank",
          entry_id: entry.entry_id || targetId,
          cue_id: entry.cue_id || targetId,
          canonical_entry_id: entry.canonical_entry_id || targetId,
        });
      } catch (error) {
        p2BrainstormReturnAfterBodyEditor = false;
        p2BrainstormReturnQuestionId = "";
        $("p2CorpusDialog")?.classList.add("hidden");
        state.p2Corpus.activeEntry = null;
        $("p2BrainstormDialog")?.classList.remove("hidden");
        throw error;
      }
    }

    function openP2BankPracticeInNewTab(cueId = "") {
      const normalizedCueId = String(cueId || "").trim();
      if (!normalizedCueId) return;
      const url = new URL(window.location.href);
      url.search = "";
      url.hash = "";
      url.searchParams.set("view", "p2");
      url.searchParams.set("p2_cue_id", normalizedCueId);
      url.searchParams.set("autostart", "1");
      const opened = window.open(url.toString(), "_blank", "noopener");
      if (!opened) text("p2BrainstormStatus", "浏览器阻止了新标签页，请允许弹窗后重试。");
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
          await saveP2BrainstormIdea(input.dataset.p2BrainstormInput || "", p2BrainstormFieldValue(input), { silent: true });
        }
        renderP2BrainstormRows();  // re-applies the active filter internally
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

    function clearP2BrainstormSearchMarks() {
      $("p2BrainstormList")?.querySelectorAll(".p2-brainstorm-row").forEach((row) => {
        row.classList.remove("is-search-match", "is-search-current");
      });
    }

    function p2BrainstormRowSearchText(row) {
      const stem = row.querySelector(".p2-brainstorm-stem")?.textContent || "";
      return `${stem} ${p2BrainstormRowValue(row)}`.toLowerCase();
    }

    function activateP2BrainstormSearchMatch(step = 1, options = {}) {
      if (!p2BrainstormSearchMatches.length) {
        updateP2BrainstormSearch();
        return;
      }
      p2BrainstormSearchMatches.forEach((row) => row.classList.remove("is-search-current"));
      p2BrainstormSearchIndex = (p2BrainstormSearchIndex + step + p2BrainstormSearchMatches.length) % p2BrainstormSearchMatches.length;
      const row = p2BrainstormSearchMatches[p2BrainstormSearchIndex];
      row.classList.add("is-search-current");
      const counter = $("p2BrainstormSearchCount");
      if (counter) counter.textContent = `${p2BrainstormSearchIndex + 1}/${p2BrainstormSearchMatches.length}`;
      row.scrollIntoView({ block: "center", behavior: "smooth" });
      if (!options.preserveFocus) row.querySelector("[data-p2-brainstorm-input]")?.focus({ preventScroll: true });
    }

    function updateP2BrainstormSearch(options = {}) {
      const input = $("p2BrainstormSearchInput");
      const counter = $("p2BrainstormSearchCount");
      const prev = $("p2BrainstormSearchPrev");
      const next = $("p2BrainstormSearchNext");
      const query = String(input?.value || "").trim().toLowerCase();
      clearP2BrainstormSearchMarks();
      p2BrainstormSearchMatches = [];
      if (!query) {
        p2BrainstormSearchIndex = -1;
        if (counter) counter.textContent = "0/0";
        if (prev) prev.disabled = true;
        if (next) next.disabled = true;
        return;
      }
      p2BrainstormSearchMatches = Array.from($("p2BrainstormList")?.querySelectorAll(".p2-brainstorm-row") || [])
        .filter((row) => p2BrainstormRowSearchText(row).includes(query));
      p2BrainstormSearchMatches.forEach((row) => row.classList.add("is-search-match"));
      if (prev) prev.disabled = p2BrainstormSearchMatches.length < 2;
      if (next) next.disabled = p2BrainstormSearchMatches.length < 2;
      if (!p2BrainstormSearchMatches.length) {
        p2BrainstormSearchIndex = -1;
        if (counter) counter.textContent = "0/0";
        return;
      }
      if (!options.keepIndex) {
        p2BrainstormSearchIndex = -1;
      } else if (p2BrainstormSearchIndex >= p2BrainstormSearchMatches.length) {
        p2BrainstormSearchIndex = p2BrainstormSearchMatches.length - 1;
      }
      if (counter) counter.textContent = p2BrainstormSearchIndex >= 0 ? `${p2BrainstormSearchIndex + 1}/${p2BrainstormSearchMatches.length}` : `0/${p2BrainstormSearchMatches.length}`;
      if (options.jump) activateP2BrainstormSearchMatch(0, { preserveFocus: true });
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
    // 跟随筛选：只复制当前筛选出来的题（无筛选=全部，A1=只复制 A1，空=只复制没灵感的）。
    async function copyP2BrainstormAll() {
      const rows = Array.from(document.querySelectorAll("#p2BrainstormList .p2-brainstorm-row"))
        .filter((row) => !row.classList.contains("is-filtered-out"));
      const blocks = [];
      rows.forEach((row) => {
        const index = (row.querySelector(".p2-brainstorm-index")?.textContent || "").trim();
        const stem = (row.querySelector(".p2-brainstorm-stem")?.textContent || "").trim();
        const idea = p2BrainstormRowValue(row).trim();
        if (!stem && !idea) return;
        const questionId = String(row.dataset.p2BrainstormRow || "").trim();
        const entry = p2BrainstormEntryForQuestion(questionId);
        const sourceQuestion = p2NormalizedCueText(entry.question || entry.linked_question || "");
        const cleanTitle = p2CleanCueTitle(entry);
        const fallbackRequirement = sourceQuestion && cleanTitle
          ? sourceQuestion.replace(cleanTitle, "").trim()
          : sourceQuestion;
        blocks.push(formatP2BrainstormCopyBlock({
          index,
          stem,
          bullets: entry.bullets,
          rounding: entry.rounding,
          fallbackRequirement,
          idea,
        }));
      });
      if (!blocks.length) {
        text("p2BrainstormStatus", "当前筛选下没有可复制的题卡。");
        return;
      }
      const payload = blocks.join("\n\n");
      const ok = await copyPlainTextToClipboard(payload);
      const scope = p2BrainstormActiveFilter ? `（筛选：${p2BrainstormFilterLabel()}）` : "（含未填写灵感的原题）";
      text("p2BrainstormStatus", ok ? `已复制 ${blocks.length} 道题${scope}，可直接粘贴给 AI。` : "复制失败，请手动选择文字复制。");
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

    function p2CueRequirementsHtml(entry = {}) {
      const structured = p2CueQuestionHtml(entry);
      if (structured) return structured;
      const title = p2CleanCueTitle(entry);
      const question = p2NormalizedCueText(entry.question || entry.linked_question || "");
      const remainder = question && title ? question.replace(title, "").trim() : question;
      if (!remainder) return "";
      return `
        <div class="p2-seasonal-cue">
          <p>${escapeHtml(remainder)}</p>
        </div>
      `;
    }

    function p2CorpusTitleCueDetail() {
      const host = $("p2CorpusDialogTitle")?.parentElement;
      if (!host) return null;
      let detail = $("p2CorpusTitleCueDetail");
      if (!detail) {
        detail = document.createElement("div");
        detail.id = "p2CorpusTitleCueDetail";
        detail.className = "p2-brainstorm-cue-detail p2-corpus-title-cue-detail";
        detail.hidden = true;
        host.appendChild(detail);
      }
      return detail;
    }

    function closeP2CorpusTitleCue() {
      const title = $("p2CorpusDialogTitle");
      const detail = $("p2CorpusTitleCueDetail");
      title?.setAttribute("aria-expanded", "false");
      if (detail) detail.hidden = true;
    }

    function setP2CorpusTitleCue(entry = {}, enabled = false) {
      const title = $("p2CorpusDialogTitle");
      const body = enabled ? p2CueRequirementsHtml(entry) : "";
      if (!title || !body) {
        title?.classList.remove("p2-corpus-title-cue-trigger");
        title?.removeAttribute("role");
        title?.removeAttribute("tabindex");
        title?.removeAttribute("aria-expanded");
        const detail = $("p2CorpusTitleCueDetail");
        if (detail) {
          detail.hidden = true;
          detail.innerHTML = "";
        }
        return;
      }
      title.classList.add("p2-corpus-title-cue-trigger");
      title.setAttribute("role", "button");
      title.setAttribute("tabindex", "0");
      title.setAttribute("aria-expanded", "false");
      const detail = p2CorpusTitleCueDetail();
      if (detail) {
        detail.hidden = true;
        detail.innerHTML = body;
      }
    }

    function toggleP2CorpusTitleCue() {
      const title = $("p2CorpusDialogTitle");
      const detail = $("p2CorpusTitleCueDetail");
      if (!title?.classList.contains("p2-corpus-title-cue-trigger") || !detail?.innerHTML) return;
      const willOpen = detail.hidden;
      detail.hidden = !willOpen;
      title.setAttribute("aria-expanded", String(willOpen));
    }

    async function openP2CorpusLibrary() {
      // Guests may browse the library; editing/saving is gated at the edit
      // actions below, not at entry.
      openCorpusWindow("p2Corpus");
    }

    function openP2CorpusEditor(entry = {}) {
      if (!state.account.authenticated) {
        guestGate("登录后才能编辑和保存你的 P2 串题素材库。", "p2Corpus");
        return;
      }
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
      setP2CorpusTitleCue({}, false);
      text("p2CorpusDialogCategory", (entry.label || category).toString());
      text("p2CorpusDialogTitle", entry.entry_id ? "编辑 P2 素材" : "新增 P2 素材");
      text("p2CorpusTextLabel", "串题素材");
      const saveButton = $("saveP2CorpusBtn");
      if (saveButton) saveButton.textContent = "保存素材";
      if ($("p2CorpusCategory")) $("p2CorpusCategory").value = category;
      if ($("p2CorpusTitle")) $("p2CorpusTitle").value = entry.title || "";
      setP2CorpusBrainstormField("");
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
      setP2CorpusTitleCue(state.p2Corpus.activeEntry, true);
      text("p2CorpusDialogCategory", "题库正文");
      text("p2CorpusDialogTitle", `编辑正文：${titleText}`);
      text("p2CorpusTextLabel", "正文");
      const saveButton = $("saveP2CorpusBtn");
      if (saveButton) {
        saveButton.textContent = "保存正文";
        saveButton.disabled = true;
      }
      if ($("p2CorpusCategory")) $("p2CorpusCategory").value = "special";
      if ($("p2CorpusTitle")) $("p2CorpusTitle").value = titleText;
      setP2CorpusBrainstormField("");
      if ($("p2CorpusBrainstormIdea")) $("p2CorpusBrainstormIdea").disabled = true;
      setCorpusMarkdownValue("p2CorpusText", "");
      setCorpusEditorLoading("p2CorpusText", true, {
        title: "正在加载题库正文",
        detail: "窗口已打开，正文马上出现。",
      });
      text("p2CorpusSaveStatus", "正在加载题库正文...");
      $("p2CorpusDialog")?.classList.remove("hidden");
    }

    async function openP2BankCorpusEditor(entry = {}) {
      if (!state.account.authenticated) {
        guestGate("登录后才能编辑和保存这道题卡的正文素材。", "p2Corpus");
        return;
      }
      const questionId = p2BankQuestionId(entry);
      if (!questionId) return;
      const token = ++p2BankCorpusLoadToken;
      // Cache-first open. A local copy exists after the first open or any save,
      // so render it instantly with no loading flash and let the SWR layer
      // revalidate in the background — revalidate never rewrites an open editor
      // (see maybeApplyFreshP2BankCorpus), so content can't jump under the user.
      // Only a genuinely cold cache shows the loader. This removes both the
      // every-open network wait and the "blank → text jumps in" flicker on
      // reopen that the forced refetch used to cause.
      const forceFresh = entry.forceFresh === true || entry.reportForceFresh === true;
      const cachedRecord = p2BankLsReadAny(P2BANK_LS_PREFIX, questionId);
      const cachedPayload = cachedRecord?.payload || null;
      const cachedHasMaterial = Boolean(String(cachedPayload?.corpus_text || "").trim());
      const canRenderCachedFirst = forceFresh && cachedHasMaterial;
      const hasLocalCopy = canRenderCachedFirst || (!forceFresh && Boolean(cachedRecord));
      if (!hasLocalCopy) showP2BankCorpusEditorLoading(entry);
      let payload;
      try {
        if (canRenderCachedFirst) {
          payload = cachedPayload;
          fetchP2BankCorpusPayload(questionId, { force: true })
            .then((fresh) => {
              if (token !== p2BankCorpusLoadToken) return;
              if ($("p2CorpusDialog")?.classList.contains("hidden")) return;
              const active = state.p2Corpus.activeEntry || {};
              const activeIds = p2EquivalentQuestionIds(p2BankQuestionId(active));
              const freshIds = p2EquivalentQuestionIds(fresh?.question_id || questionId);
              if (!activeIds.some((id) => freshIds.includes(id))) return;
              applyP2BankCorpusSavedLocal(fresh.question_id || questionId, fresh);
              const cachedText = String(cachedPayload?.corpus_text || "").trim();
              const currentDraft = getCorpusMarkdownValue("p2CorpusText").trim();
              if (currentDraft !== cachedText) return;
              state.p2Corpus.activeEntry = {
                ...active,
                ...fresh,
                material_text: fresh.corpus_text || "",
                linked_question: fresh.question || active.linked_question || "",
                brainstorm_idea: fresh.brainstorm_idea ?? active.brainstorm_idea ?? "",
              };
              setP2CorpusBrainstormField(state.p2Corpus.activeEntry.brainstorm_idea || "");
              setCorpusMarkdownValue("p2CorpusText", state.p2Corpus.activeEntry.material_text || "");
            })
            .catch(() => null);
        } else {
          payload = await fetchP2BankCorpusPayload(questionId, { force: forceFresh });
        }
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
      setP2CorpusTitleCue(activeEntry, true);
      const titleText = activeEntry.title || activeEntry.linked_question || "P2 题卡";
      text("p2CorpusDialogCategory", "题库正文");
      text("p2CorpusDialogTitle", `编辑正文：${titleText}`);
      text("p2CorpusTextLabel", "正文");
      const saveButton = $("saveP2CorpusBtn");
      if (saveButton) saveButton.textContent = "保存正文";
      if ($("p2CorpusCategory")) $("p2CorpusCategory").value = "special";
      if ($("p2CorpusTitle")) $("p2CorpusTitle").value = activeEntry.title || "";
      if ($("p2CorpusBrainstormIdea")) $("p2CorpusBrainstormIdea").disabled = false;
      setP2CorpusBrainstormField(activeEntry.brainstorm_idea || "");
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
      setP2CorpusTitleCue({}, false);
      if ($("p2CorpusBrainstormIdea")) $("p2CorpusBrainstormIdea").disabled = false;
      if ($("saveP2CorpusBtn")) $("saveP2CorpusBtn").disabled = false;
      state.p2Corpus.activeEntry = null;
      if (p2BrainstormReturnAfterBodyEditor) {
        const returnId = p2BrainstormReturnQuestionId;
        p2BrainstormReturnAfterBodyEditor = false;
        p2BrainstormReturnQuestionId = "";
        renderP2BrainstormRows();
        // Returning from the body editor should reveal the dialog that was sitting
        // underneath, not replay the open-from-scratch entrance — otherwise it reads
        // as a fresh dialog rather than the layer beneath. The flag stays on while
        // shown (removing it would re-trigger the animation); a fresh open clears it.
        const dialog = $("p2BrainstormDialog");
        if (dialog) {
          dialog.classList.add("no-entrance");
          dialog.classList.remove("hidden");
        }
        if (returnId) {
          setP2BrainstormActiveDetail(returnId);
          setTimeout(() => {
            document.querySelector(`[data-p2-brainstorm-row="${CSS.escape(returnId)}"]`)?.scrollIntoView({ block: "center" });
          }, 0);
        }
      }
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
      if (!state.account.authenticated) {
        guestGate("登录后才能编辑 P3 追问素材。", "p2Corpus");
        return;
      }
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
      $("p2BankP3EntryList")?.classList.add("hidden");
      $("p2CorpusP3FollowUpLabel")?.classList.remove("hidden");
      const initialText = entry.p3_follow_up_text || p2P3FollowUpMarkdownTemplate(entry);
      setCorpusMarkdownValue("p2CorpusP3FollowUp", initialText);
      text("p2CorpusP3SaveStatus", entry.p3_follow_up_text ? "" : "可直接编辑并保存。");
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
      if (!state.account.authenticated) {
        guestGate("登录后才能编辑这道题卡的 P3 追问素材。", "p2Corpus");
        return;
      }
      const questionId = p2BankQuestionId(entry);
      if (!questionId) return;
      const token = ++p2BankP3LoadToken;
      const hasWarmPayload = hasP2BankP3PayloadCached(questionId);
      if (!hasWarmPayload) showP2BankP3EditorLoading(entry);
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
        const brainstormIdea = p2CorpusBrainstormIdeaValue();
        const questionId = p2BankQuestionId(entry);
        notifyCorpusSaved({ kind: "p2_bank", questionId, saved: Boolean(materialText) });
        closeP2CorpusEditor();
        saveP2BankCorpusEntry({
          entry,
          materialText,
          brainstormIdea,
          silent: true,
        }).catch(() => null);
        return;
      }
      const title = $("p2CorpusTitle")?.value || "";
      const category = $("p2CorpusCategory")?.value || entry.category || "person";
      if (entry.entry_id) {
        notifyCorpusSaved({ kind: "p2_corpus", entryId: entry.entry_id, saved: Boolean(materialText) });
      }
      closeP2CorpusEditor();
      if (materialText || entry.entry_id) {
        setP2CorpusFeedback(entry.entry_id ? "正在保存素材..." : "正在新增素材...", "saving");
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
        const questionId = p2BankQuestionId(entry);
        (entry.items || []).forEach((item) => {
          notifyCorpusSaved({
            kind: "p3_bank",
            questionId,
            p2QuestionId: questionId,
            followupId: item.followup_id || "",
            saved: Boolean(String(item.corpus_text || "").trim()),
          });
        });
        closeP2CorpusP3Editor();
        saveP2BankP3Entries({ entry, silent: true }).catch(() => null);
        return;
      }
      const entry = state.p2Corpus.activeP3Entry || {};
      const p3FollowUpText = getCorpusMarkdownValue("p2CorpusP3FollowUp").trim();
      if (entry.entry_id) {
        notifyCorpusSaved({ kind: "p2_corpus_p3", entryId: entry.entry_id, saved: Boolean(p3FollowUpText) });
      }
      closeP2CorpusP3Editor();
      if (entry.entry_id) {
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
      if (state.p2Corpus.saving) {
        await state.p2Corpus.savingPromise?.catch(() => null);
        return saveP2BankP3Entries(options);
      }
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
      // Move the progress bar NOW from local drafts, before any network — this is
      // what makes P1 feel instant and roll back the moment you empty an answer.
      // The editor loaded every follow-up, so items.length is the true total and
      // the non-empty count is the true saved count. updateP2CardP3CountLocal
      // bumps mutationSeq, so the background reconcile below can't clobber this.
      const savedCount = items.filter((item) => String(item.corpus_text || "").trim()).length;
      updateP2CardP3CountLocal(questionId, savedCount, items.length);
      renderP2CorpusTopics();
      const savePromise = (async () => {
      try {
        const drafts = items.map((item) => ({
          followup_id: item.followup_id || "",
          followup_question: item.followup_question || "",
          corpus_text: item.corpus_text || "",
        }));
        const savedItems = await Promise.all(drafts.map((draft) => api(`/api/p3-bank-corpus/item/${encodeURIComponent(draft.followup_id || "")}`, {
          p2_question_id: questionId,
          followup_question: draft.followup_question || "",
          corpus_text: draft.corpus_text || "",
          source: "p3_bank_corpus_editor",
        })));
        // P3 save is per-item with no combined payload; drop both caches so the
        // next open re-fetches fresh and no stale copy covers the new content.
        const mergedItems = items.map((item) => {
          const saved = savedItems.find((row) => row.followup_id === item.followup_id);
          return saved ? { ...item, ...saved } : item;
        });
        entry.items = mergedItems;
        applyP2BankP3SavedLocal(questionId, mergedItems);
        mergedItems.forEach((item) => {
          notifyCorpusSaved({
            kind: "p3_bank",
            questionId,
            p2QuestionId: questionId,
            followupId: item.followup_id || "",
            saved: Boolean(String(item.corpus_text || "").trim()),
          });
        });
        if (!options.silent) text("p2CorpusP3SaveStatus", "已保存题库 P3 追问");
        // Reconcile in the background; the optimistic counts already match the
        // saved state, so the UI must not block on a full library refetch.
        loadP2Corpus({ force: true }).catch(() => null);
        if (options.closeOnSuccess) closeP2CorpusP3Editor();
      } catch (error) {
        if (!options.silent) text("p2CorpusP3SaveStatus", error.message || String(error));
        // Save failed after the optimistic bar moved — pull server truth back so
        // the count reverts instead of lying. mutationSeq was bumped above, so
        // this refetch is current (not discarded by the stale guard).
        loadP2Corpus({ force: true }).catch(() => null);
        if (options.closeOnError) closeP2CorpusP3Editor();
      } finally {
        state.p2Corpus.saving = false;
        state.p2Corpus.savingPromise = null;
        if (button && !options.silent) {
          button.disabled = false;
          button.textContent = original;
        }
      }
      })();
      state.p2Corpus.savingPromise = savePromise;
      return savePromise;
    }

    document.addEventListener("click", (event) => {
      const titleCueTrigger = event.target.closest("#p2CorpusDialogTitle");
      if (titleCueTrigger?.classList.contains("p2-corpus-title-cue-trigger")) {
        event.preventDefault();
        event.stopImmediatePropagation();
        toggleP2CorpusTitleCue();
        return;
      }
      if (!event.target.closest("#p2CorpusTitleCueDetail")) {
        closeP2CorpusTitleCue();
      }
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
        if (!state.account.authenticated) {
          guestGate("登录后才能用这道题卡开始 P2 练习。", "p2Corpus");
          return;
        }
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
        openP2BankCorpusEditor(p2BankEntryFromElement(cardMaterialButton)).catch((error) => {
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

    $("p2CorpusDialogTitle")?.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeP2CorpusTitleCue();
        return;
      }
      if (event.key !== "Enter" && event.key !== " ") return;
      if (!event.currentTarget.classList.contains("p2-corpus-title-cue-trigger")) return;
      event.preventDefault();
      toggleP2CorpusTitleCue();
    });

    $("languageTakeawayDictDisplay")?.addEventListener("input", () => {
      const display = $("languageTakeawayDictDisplay");
      if (!display?.classList.contains("is-dictionary-editable")) return;
      syncLanguageTakeawayDictionaryChineseDraft();
    });

    $("languageTakeawayDictDisplay")?.addEventListener("keydown", handleDictionaryDomainAtomDelete);

    $("languageTakeawayDictDisplay")?.addEventListener("paste", (event) => {
      const display = $("languageTakeawayDictDisplay");
      if (!display?.classList.contains("is-dictionary-editable")) return;
      event.preventDefault();
      const textValue = event.clipboardData?.getData("text/plain") || "";
      document.execCommand("insertText", false, textValue);
    });

    $("p2BrainstormDialog")?.addEventListener("pointerdown", (event) => {
      if (event.target === $("p2BrainstormDialog")) closeP2BrainstormDialog();
    });

    $("p2BrainstormDialog")?.addEventListener("click", (event) => {
      if (event.target.closest("#p2BrainstormList")) return;
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
        const isActive = Boolean(activeId && detail.dataset.p2BrainstormDetail === activeId);
        detail.hidden = !isActive;
        if (isActive) positionP2BrainstormDetail(detail);
        else detail.classList.remove("is-detail-up", "is-detail-in");
      });
    }

    // The cue popover is absolutely positioned inside the scrolling list, so for a
    // row near the bottom an open-downward popover spills past the content and
    // inflates the scroll height (you'd have to scroll to see it). Flip it to open
    // upward whenever there isn't enough room below, then replay its entrance.
    function positionP2BrainstormDetail(detail) {
      const list = $("p2BrainstormList");
      const row = detail.closest(".p2-brainstorm-row");
      if (!list || !row) return;
      const listRect = list.getBoundingClientRect();
      const rowRect = row.getBoundingClientRect();
      const needed = Math.min((detail.scrollHeight || 200) + 24, 244);
      const spaceBelow = listRect.bottom - rowRect.bottom;
      const spaceAbove = rowRect.top - listRect.top;
      const flipUp = spaceBelow < needed && spaceAbove > spaceBelow;
      detail.classList.toggle("is-detail-up", flipUp);
      detail.classList.remove("is-detail-in");
      void detail.offsetWidth;            // reflow so the entrance animation replays
      detail.classList.add("is-detail-in");
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
      const tagRemove = event.target.closest("[data-p2-brainstorm-tag-remove]");
      if (tagRemove) {
        event.preventDefault();
        event.stopPropagation();
        const row = tagRemove.closest(".p2-brainstorm-row");
        tagRemove.closest(".p2-brainstorm-tag")?.remove();
        const input = row?.querySelector("[data-p2-brainstorm-input]");
        if (input) scheduleP2BrainstormAutosave(input);
        renderP2BrainstormFilterBar();
        applyP2BrainstormFilter();
        return;
      }
      const practiceButton = event.target.closest("[data-p2-brainstorm-practice]");
      if (practiceButton) {
        event.preventDefault();
        event.stopPropagation();
        openP2BankPracticeInNewTab(practiceButton.dataset.p2BrainstormPractice || "");
        return;
      }
      const editBodyButton = event.target.closest("[data-p2-brainstorm-edit-body]");
      if (editBodyButton) {
        event.preventDefault();
        event.stopPropagation();
        openP2BrainstormBodyEditor(editBodyButton.dataset.p2BrainstormEditBody || "").catch((error) => {
          $("p2BrainstormDialog")?.classList.remove("hidden");
          text("p2BrainstormStatus", error.message || String(error));
        });
        return;
      }
      const trigger = event.target.closest("[data-p2-brainstorm-toggle]");
      if (!trigger) return;
      openP2BrainstormDetail(trigger);
    });

    $("p2BrainstormList")?.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeP2BrainstormDetails();
        return;
      }
      if (event.target.closest("button")) return;
      if (event.key !== "Enter" && event.key !== " ") return;
      const trigger = event.target.closest("[data-p2-brainstorm-toggle]");
      if (!trigger) return;
      event.preventDefault();
      openP2BrainstormDetail(trigger);
    });

    $("p2BrainstormList")?.addEventListener("input", (event) => {
      const input = event.target.closest("[data-p2-brainstorm-input]");
      if (!input) return;
      maybeConvertLeadingBrainstormTag(input);
      scheduleP2BrainstormAutosave(input);
      updateP2BrainstormSearch({ keepIndex: true });
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
      if (p2BrainstormDirtyValues.has(questionId)) persistP2BrainstormDirty(questionId);
    });

    $("p2BrainstormSearchInput")?.addEventListener("input", () => {
      updateP2BrainstormSearch();
    });

    $("p2BrainstormSearchInput")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        updateP2BrainstormSearch({ keepIndex: true });
        activateP2BrainstormSearchMatch(event.shiftKey ? -1 : 1);
      } else if (event.key === "Escape") {
        event.currentTarget.value = "";
        updateP2BrainstormSearch();
      }
    });

    $("p2BrainstormSearchPrev")?.addEventListener("click", () => {
      activateP2BrainstormSearchMatch(-1);
    });

    $("p2BrainstormSearchNext")?.addEventListener("click", () => {
      activateP2BrainstormSearchMatch(1);
    });

    $("copyP2BrainstormBtn")?.addEventListener("click", () => {
      copyP2BrainstormAll().catch((error) => {
        text("p2BrainstormStatus", error.message || String(error));
      });
    });

    $("p2BrainstormFilterBar")?.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-p2-brainstorm-filter]");
      if (!btn) return;
      p2BrainstormActiveFilter = btn.dataset.p2BrainstormFilter || "";
      renderP2BrainstormFilterBar();
      applyP2BrainstormFilter();
    });

    // 「正文编辑」里的串题灵感字段：开头打 A/B2 + 空格转 chip；× 删除 chip。
    $("p2CorpusBrainstormIdea")?.addEventListener("input", (event) => {
      maybeConvertLeadingBrainstormTag(event.target);
    });

    $("p2CorpusBrainstormField")?.addEventListener("click", (event) => {
      const x = event.target.closest("[data-p2-brainstorm-tag-remove]");
      if (!x) return;
      event.preventDefault();
      event.stopPropagation();
      x.closest(".p2-brainstorm-tag")?.remove();
      $("p2CorpusBrainstormIdea")?.focus();
    });

    $("p2BankP3EntryList")?.addEventListener("click", (event) => {
      const bankP3Button = event.target.closest("[data-p2-bank-p3-select]");
      if (!bankP3Button) return;
      event.preventDefault();
      selectP2BankP3Question(bankP3Button.dataset.p2BankP3Select || "");
    });

    async function saveP2CorpusEntry(options = {}) {
      const entry = options.entry || state.p2Corpus.activeEntry || {};
      if (state.p2Corpus.saving) {
        await state.p2Corpus.savingPromise?.catch(() => null);
        return saveP2CorpusEntry(options);
      }
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
      const existingEntryId = String(entry.entry_id || options.entryId || "").trim();
      if (!existingEntryId && !nextMaterialText && !String(nextP3FollowUpText || "").trim() && options.source !== "p2_corpus_p3_editor") {
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
      const savePromise = (async () => {
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
        // Force a fresh pull so the just-saved material/P3 status replaces any
        // cached snapshot — without this a save can show stale state until a
        // manual refresh (same fix the bank path already has).
        const updated = upsertP2CorpusEntryLocal(saved);
        state.p2Corpus.selectedEntryId ||= saved.entry_id;
        notifyCorpusSaved({
          kind: options.source === "p2_corpus_p3_editor" ? "p2_corpus_p3" : "p2_corpus",
          entryId: saved.entry_id || entry.entry_id || "",
          saved: options.source === "p2_corpus_p3_editor"
            ? Boolean(String(saved.p3_follow_up_text || saved.metadata?.p3_follow_up_text || nextP3FollowUpText || "").trim())
            : Boolean(String(saved.material_text || nextMaterialText || "").trim()),
        });
        renderP2CorpusTopics();
        renderP2CorpusPrepPanel();
        loadP2Corpus({ force: true }).catch(() => null);
        if (options.silent) {
          setP2CorpusFeedback("\u5df2\u4fdd\u5b58\u7d20\u6750", "success");
          flashP2CorpusEntry(updated?.entry_id || saved.entry_id);
        }
        if (options.closeOnSuccess) closeP2CorpusEditor();
      } catch (error) {
        if (!options.silent) text("p2CorpusSaveStatus", error.message || String(error));
        if (options.silent) setP2CorpusFeedback(error.message || "\u4fdd\u5b58\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5", "error");
        if (options.closeOnError) closeP2CorpusEditor();
      } finally {
        state.p2Corpus.saving = false;
        state.p2Corpus.savingPromise = null;
        if (button && !options.silent) {
          button.disabled = false;
          button.textContent = original;
        }
      }
      })();
      state.p2Corpus.savingPromise = savePromise;
      return savePromise;
    }

    async function saveP2BankCorpusEntry(options = {}) {
      const entry = options.entry || state.p2Corpus.activeEntry || {};
      if (state.p2Corpus.saving) {
        await state.p2Corpus.savingPromise?.catch(() => null);
        return saveP2BankCorpusEntry(options);
      }
      const questionId = p2BankQuestionId(entry);
      if (!questionId) {
        text("p2CorpusSaveStatus", "缺少题卡 ID，无法保存。");
        return;
      }
      state.p2Corpus.saving = true;
      const button = $("saveP2CorpusBtn");
      const original = button?.textContent || "保存素材";
      const nextMaterialText = (options.materialText ?? getCorpusMarkdownValue("p2CorpusText")).trim();
      const nextBrainstormIdea = options.brainstormIdea ?? (p2CorpusBrainstormIdeaValue() || entry.brainstorm_idea || "");
      if (button && !options.silent) {
        button.disabled = true;
        button.textContent = "保存中...";
      }
      if (!options.silent) text("p2CorpusSaveStatus", "");
      const savePromise = (async () => {
      try {
        const saved = await api(`/api/p2-bank-corpus/${encodeURIComponent(questionId)}`, {
          question: entry.linked_question || entry.question || "",
          corpus_text: nextMaterialText,
          last_ai_answer: entry.last_ai_answer || "",
          metadata: { brainstorm_idea: nextBrainstormIdea },
          source: "p2_bank_corpus_editor",
        });
        updateP2BrainstormCardLocal(questionId, saved.brainstorm_idea ?? nextBrainstormIdea);
        // Push the just-saved payload into both caches so a stale copy can
        // never cover fresh content, and a reopen is instant.
        applyP2BankCorpusSavedLocal(questionId, saved);
        notifyCorpusSaved({ kind: "p2_bank", questionId, saved: Boolean(String(saved.corpus_text || nextMaterialText || "").trim()) });
        if (state.p2Corpus.activeEntry && p2BankQuestionId(state.p2Corpus.activeEntry) === questionId) {
          state.p2Corpus.activeEntry.material_text = saved.corpus_text || "";
        }
        if (!options.silent) text("p2CorpusSaveStatus", `已保存 ${saved.updated_at || ""}`);
        renderP2CorpusTopics();
        renderP2CorpusPrepPanel();
        loadP2Corpus({ force: true }).catch(() => null);
        if (options.closeOnSuccess) closeP2CorpusEditor();
      } catch (error) {
        if (!options.silent) text("p2CorpusSaveStatus", error.message || String(error));
        if (options.closeOnError) closeP2CorpusEditor();
      } finally {
        state.p2Corpus.saving = false;
        state.p2Corpus.savingPromise = null;
        if (button && !options.silent) {
          button.disabled = false;
          button.textContent = original;
        }
      }
      })();
      state.p2Corpus.savingPromise = savePromise;
      return savePromise;
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
      if (!state.account.authenticated) {
        const payload = takeawaySeedPayload("writing");
        applyWritingTakeawaysPayload(payload);
        if (stats) stats.textContent = `${payload.count || 0} 条`;
        renderWritingTakeawayToggle();
        renderWritingTakeaways();
        renderTakeawayReviewSurfaces("writing");
        return;
      }
      if (state.writingTakeaway.loaded) {
        renderWritingTakeawayToggle();
        renderWritingTakeaways();
        if (stats) stats.textContent = `${state.writingTakeaway.items.length} 条`;
        renderTakeawayReviewSurfaces("writing");
        return;
      } else {
        if (stats) stats.textContent = "Loading...";
        if (list) list.innerHTML = '<div class="page-center-loading takeaway-page-loading" role="status" aria-live="polite"><div><span class="spinner"></span><div><strong>正在加载写作积累</strong><span>整理你保存的写作素材…</span></div></div></div>';
      }
      try {
        const payload = withTakeawayDefaults("writing", await fetchWritingTakeawaysPayload());
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
      const cardFor = (item) => {
        const isReviewTarget = isTakeawayReviewEntry("writing", item.entry_id);
        const isDue = dueIds.has(item.entry_id);
        const shouldConceal = (session.active ? isReviewTarget : hiddenMode) && !revealed.has(item.entry_id);
        const isCurrent = session.active && session.currentId === item.entry_id;
        const isLocated = session.active && session.locatedId === item.entry_id && isReviewTarget && !isCurrent;
        return `
        <div class="language-takeaway-card-wrap ${shouldConceal ? "is-concealed" : "is-revealed"} ${isDue ? "is-review-due" : ""} ${isReviewTarget ? "is-reviewing" : ""} ${isCurrent ? "is-review-current" : ""} ${isLocated ? "is-located" : ""}">
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
          ${isCurrent ? takeawayReviewMascotHtml() : ""}
        </div>
      `;
      };
      renderTakeawayBook(list, items, cardFor, "writing");
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
      if (guestBlockTakeawayEdit("登录后才能删除写作积累内容。")) return;
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
      openP1TopicCardModal,
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
      openP2CorpusBodyPeek,
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
      hydrateP1CorpusClearedIds,
      loadP2Corpus,
      renderP2CorpusTopics,
      loadCorpusHome,
      loadLanguageTakeaways,
      renderLanguageTakeaways,
      renderLanguageTakeawayToggle,
      toggleLanguageTakeawayHiddenMode,
      startTakeawayReview,
      endTakeawayReview,
      setTakeawayReviewToast,
      interruptTakeawaySpeechPlayback,
      selectTakeawayReviewEntry,
      scrollToTakeawayReviewTarget,
      triggerTakeawayLocate,
      takeawayReviewFeedback,
      updateTakeawayReviewDots,
      applyRemoteTakeawayReviewState,
      speakLanguageTakeaway,
      setTakeawaySpeechStatus,
      revealAndSpeakLanguageTakeaway,
      deleteLanguageTakeawayEntry,
      languageTakeawayTranslationStatus,
      setLanguageTakeawayStatus,
      writingAnswerSelectionText,
      textareaSelectionEndpointRect,
      selectionText,
      hideLanguageTakeawayTrigger,
      hideLanguageTakeawayPopup,
      speakLanguageTakeawaySource,
      openTakeawayPronunciationDialog,
      closeTakeawayPronunciationDialog,
      startTakeawayPronunciationRecording,
      autosizeLanguageTakeawaySource,
      resetLanguageTakeawayDictionary,
      toggleLanguageTakeawayDictionaryMode,
      syncLanguageTakeawayDictionaryChineseDraft,
      createPixelFlowField,
      updateLanguageTakeawaySpellingButton,
      addLanguageTakeawaySpellingWord,
      translateTakeawayEditSource,
      placeLanguageTakeawayTrigger,
      showLanguageTakeawayTrigger,
      trackLanguageTakeawayTriggerDuringScroll,
      scheduleLanguageTakeawayTriggerFromSelection,
      placeLanguageTakeawayPopup,
      openLanguageTakeawayPopup,
      resolveLanguageTakeawaySource,
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
    formatP2BrainstormCopyBlock,
  };
})();
