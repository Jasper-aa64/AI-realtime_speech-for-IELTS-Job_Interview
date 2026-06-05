(function () {
  "use strict";

  function createSpellingDrillController(options) {
    const {
      state,
      $,
      escapeHtml,
      api,
      showConfirmDelete,
    } = options || {};

    if (!state || typeof $ !== "function" || typeof api !== "function") {
      throw new Error("Spelling drill controller requires shared app state and helpers.");
    }

    function drillState() {
      if (!state.spellingDrill) {
        state.spellingDrill = {
          items: [],
          stats: {},
          scope: "due",
          loaded: false,
          loadingPromise: null,
          currentIndex: 0,
          result: null,
          hintLevel: 0,
          // SRS session queue
          queue: [],
          queuePos: 0,
          requeueMap: {},
          doneCount: 0,
          queueInitialLen: 0,
        };
      }
      return state.spellingDrill;
    }

    function currentItems() {
      return drillState().items || [];
    }

    function currentQueueWord() {
      const local = drillState();
      return local.queue[local.queuePos] || null;
    }

    function isQueueDone() {
      const local = drillState();
      return local.queue.length > 0 && local.queuePos >= local.queue.length;
    }

    function isQueueEmpty() {
      return drillState().queue.length === 0 && drillState().loaded;
    }

    function statText(payload) {
      const stats = payload?.stats || drillState().stats || {};
      const due = Number(stats.due || 0);
      const active = Number(stats.active || 0);
      const mastered = Number(stats.mastered || 0);
      const accuracy = Math.round(Number(stats.accuracy || 0) * 100);
      return `${due} 个待复习 · ${active} 个学中 · ${mastered} 个已掌握 · 正确率 ${accuracy}%`;
    }

    function wrongFormsText(word) {
      const forms = Array.isArray(word?.wrong_forms) ? word.wrong_forms.filter(Boolean) : [];
      return forms.length ? forms.join(" / ") : "暂无错拼记录";
    }

    function getHintDisplay(word) {
      const level = drillState().hintLevel || 0;
      const correct = String(word?.correct_spelling || "");
      if (!correct) return "";
      return correct.split("").map((ch, i) =>
        (level > 0 && i === 0) ? escapeHtml(ch) : "_"
      ).join(" ");
    }

    function letterDiff(typed, correct) {
      const t = (typed || "").toLowerCase();
      const c = (correct || "").toLowerCase();
      const maxLen = Math.max(t.length, c.length);
      let html = "";
      for (let i = 0; i < maxLen; i++) {
        if (i < typed.length) {
          const isOk = i < c.length && t[i] === c[i];
          html += `<span class="${isOk ? "dl-ok" : "dl-err"}">${escapeHtml(typed[i])}</span>`;
        } else {
          html += `<span class="dl-miss">_</span>`;
        }
      }
      return html;
    }

    function stageLabel(word) {
      if (!word) return "";
      if (word.status === "mastered") return "已掌握";
      const stage = Number(word.review_stage || 0);
      return `阶段 ${stage}/6`;
    }

    function exampleHtml(word) {
      const examples = Array.isArray(word?.examples) ? word.examples : [];
      const snippet = examples.find((e) => e && e.snippet)?.snippet || "";
      if (!snippet) return "";
      return `
        <div class="spell-example">
          <span>你的作文例句</span>
          <q>${escapeHtml(snippet)}</q>
        </div>
      `;
    }

    function setStatus(message, isError = false) {
      const status = $("spellingDrillStatus");
      if (!status) return;
      status.textContent = message || "";
      status.classList.toggle("error", Boolean(isError));
    }

    async function fetchSpellingWords(scope = drillState().scope || "due", options = {}) {
      if (options.force) drillState().loadingPromise = null;
      drillState().scope = scope;
      if (!drillState().loadingPromise) {
        drillState().loadingPromise = api(`/api/writing/spelling-words?scope=${encodeURIComponent(scope)}`)
          .finally(() => {
            drillState().loadingPromise = null;
          });
      }
      return drillState().loadingPromise;
    }

    function applySpellingPayload(payload, options = {}) {
      const local = drillState();
      local.items = payload.items || [];
      local.stats = payload.stats || {};
      local.loaded = true;
      local.currentIndex = Math.min(local.currentIndex || 0, Math.max(0, local.items.length - 1));
      local.result = null;
      local.hintLevel = 0;
      if (options.force || !local.queue.length) {
        local.queue = [...local.items];
        local.queuePos = 0;
        local.requeueMap = {};
        local.doneCount = 0;
        local.queueInitialLen = local.items.length;
      }
    }

    async function loadSpellingDrill(options = {}) {
      const local = drillState();
      const stats = $("spellingDrillStats");
      const list = $("spellingDrillList");
      if (!local.loaded || options.force) {
        if (stats) stats.textContent = "Loading...";
        if (list) list.innerHTML = '<p class="language-book-empty muted">正在从已评分作文里整理拼写错词...</p>';
      }
      try {
        const payload = await fetchSpellingWords(local.scope || "due", options);
        applySpellingPayload(payload, options);
        renderSpellingDrill();
      } catch (error) {
        if (stats) stats.textContent = "加载失败";
        if (list) list.innerHTML = `<p class="language-book-empty error">${escapeHtml(error.message || String(error))}</p>`;
      }
    }

    function renderScopeButtons() {
      document.querySelectorAll("[data-spelling-scope]").forEach((button) => {
        const active = button.dataset.spellingScope === (drillState().scope || "due");
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }

    function renderSpellingList() {
      const list = $("spellingDrillList");
      if (!list) return;
      const items = currentItems();
      if (!items.length) {
        const emptyMsg = drillState().scope === "due"
          ? "今日复习已全部完成，或暂无到期词汇。"
          : drillState().scope === "mastered" ? "还没有已掌握的词。" : "这个范围里还没有词汇。";
        list.innerHTML = `<p class="language-book-empty muted">${emptyMsg}</p>`;
        return;
      }
      list.innerHTML = items.map((word, index) => {
        const isDue = word.is_due;
        const stage = Number(word.review_stage || 0);
        const dueLabel = word.status === "mastered" ? "已掌握"
          : isDue ? `待复习·阶段${stage}`
          : `阶段${stage}`;
        return `
          <article class="spelling-word-card ${index === drillState().currentIndex ? "is-current" : ""}" data-spelling-word="${escapeHtml(word.word_id)}">
            <button type="button" class="spelling-word-main" data-spelling-select="${escapeHtml(word.word_id)}">
              <span class="spelling-word-title">
                <strong>${escapeHtml(word.correct_spelling)}</strong>
                <em class="${isDue ? "due-badge" : ""}">${escapeHtml(dueLabel)}</em>
              </span>
              <span class="spelling-word-wrong">曾写成：${escapeHtml(wrongFormsText(word))}</span>
              <span class="spelling-word-meta">${escapeHtml(word.chinese_gloss || "暂无中文释义")} · 出现 ${Number(word.occurrence_count || 0)} 次</span>
            </button>
            <div class="spelling-word-actions">
              <button type="button" data-spelling-master="${escapeHtml(word.word_id)}">掌握</button>
              <button type="button" class="danger" data-spelling-delete="${escapeHtml(word.word_id)}">移出</button>
            </div>
          </article>
        `;
      }).join("");
    }

    function renderPracticeCard() {
      const card = $("spellingPracticeCard");
      if (!card) return;

      // Queue-done screen
      if (isQueueDone()) {
        const local = drillState();
        card.innerHTML = `
          <div class="spelling-session-done">
            <div class="session-done-icon">✓</div>
            <strong>本轮复习完成！</strong>
            <span>共完成 ${local.doneCount} 个词，下次见～</span>
            <button type="button" class="spelling-done-next-btn" data-spelling-load-due>刷新队列</button>
          </div>
        `;
        return;
      }

      // No-due-words screen
      if (isQueueEmpty() && drillState().scope === "due") {
        card.innerHTML = `
          <div class="spelling-session-done">
            <div class="session-done-icon">🎉</div>
            <strong>今日复习已清空</strong>
            <span>所有词汇都按计划安排好了，暂时没有到期词。</span>
            <button type="button" class="spelling-done-next-btn" data-spelling-scope="active">提前练（全部词）</button>
          </div>
        `;
        return;
      }

      const word = currentQueueWord();
      if (!word) {
        card.innerHTML = `
          <div class="spelling-practice-empty">
            <strong>没有可训练的错词</strong>
            <span>完成作文评分后，页面会自动从拼写批注里整理错词。</span>
          </div>
        `;
        return;
      }

      const local = drillState();
      const result = local.result;
      const progressTotal = Math.max(local.queueInitialLen, 1);
      const progressDone = local.doneCount;
      const progressPct = Math.round((progressDone / progressTotal) * 100);
      const requeueCount = local.requeueMap[word.word_id] || 0;

      const wrongResultHtml = result && !result.correct ? `
        <div class="spell-diff-row">
          <span>你写的：</span>
          <span class="spell-diff">${letterDiff(result._typed || "", result.correct_spelling || word.correct_spelling)}</span>
        </div>
        <div class="spell-diff-row">
          <span>正确：</span>
          <strong class="spell-correct-word">${escapeHtml(result.correct_spelling || word.correct_spelling)}</strong>
        </div>
        ${(result.explanation || word.explanation) ? `<p class="spell-explanation">${escapeHtml(result.explanation || word.explanation)}</p>` : ""}
      ` : "";

      const resultHtmlFull = result ? `
        <div class="spelling-attempt-result ${result.correct ? "is-correct" : "is-wrong"}">
          <strong>${result.correct ? "拼对了" : "这次拼错了"}</strong>
          ${result.correct
            ? `<span>阶段 ${result.review_stage || 0}/6 · ${escapeHtml(result.next_due_human || "")}</span>`
            : wrongResultHtml}
          ${result.next_due_human && !result.correct ? `<p class="spell-next-due">10 分钟后会再考你</p>` : ""}
        </div>
      ` : "";

      const gloss = word.chinese_gloss || "";
      const hasGloss = Boolean(gloss);

      card.innerHTML = `
        <div class="spelling-session-progress">
          <div class="session-progress-bar">
            <div class="session-progress-fill" style="width:${progressPct}%"></div>
          </div>
          <span>${progressDone} / ${progressTotal}${requeueCount > 0 ? ` <em class="requeue-badge">重练 ×${requeueCount}</em>` : ""}</span>
        </div>
        <div class="spelling-practice-head">
          <div>
            <span class="corpus-page-kicker">Spelling Drill</span>
            <h3>${hasGloss ? escapeHtml(gloss) : escapeHtml(word.correct_spelling)}</h3>
            ${!hasGloss ? '<span class="spell-no-gloss">（根据错拼回忆正确单词）</span>' : ""}
          </div>
          <span class="spelling-progress-pill">${escapeHtml(stageLabel(word))}</span>
        </div>
        <div class="spelling-prompt-box">
          <span>你之前写成</span>
          <strong>${escapeHtml(wrongFormsText(word))}</strong>
          <div class="spelling-hint-display">${getHintDisplay(word)}</div>
        </div>
        ${drillState().hintLevel === 0 ? '<div class="spelling-hint-bar"><button type="button" class="spelling-hint-link" data-spelling-hint>显示首字母</button></div>' : '<div class="spelling-hint-bar"></div>'}
        ${exampleHtml(word)}
        <form id="spellingAttemptForm" class="spelling-attempt-form">
          <label for="spellingTypedInput">重新拼写</label>
          <div>
            <input id="spellingTypedInput" type="text" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="输入正确拼写，Enter 提交">
            <button type="submit">判分</button>
          </div>
        </form>
        <div class="spelling-practice-actions">
          <button type="button" data-spelling-next>下一词</button>
          <button type="button" data-spelling-reset-word="${escapeHtml(word.word_id)}">重练</button>
        </div>
        ${resultHtmlFull}
      `;
      $("spellingTypedInput")?.focus();
    }

    function renderSpellingDrill() {
      const payload = { stats: drillState().stats };
      const stats = $("spellingDrillStats");
      if (stats) stats.textContent = statText(payload);
      renderScopeButtons();
      renderSpellingList();
      renderPracticeCard();
    }

    function selectWord(wordId) {
      const index = currentItems().findIndex((word) => word.word_id === wordId);
      if (index < 0) return;
      drillState().currentIndex = index;
      // Also seek queue to this word if present
      const local = drillState();
      const queueIdx = local.queue.findIndex((w) => w.word_id === wordId);
      if (queueIdx >= 0 && queueIdx >= local.queuePos) {
        local.queuePos = queueIdx;
      }
      local.result = null;
      local.hintLevel = 0;
      renderSpellingDrill();
    }

    function nextWord() {
      const local = drillState();
      local.queuePos += 1;
      local.result = null;
      local.hintLevel = 0;
      // Sync currentIndex to list view
      const word = currentQueueWord();
      if (word) {
        const idx = currentItems().findIndex((w) => w.word_id === word.word_id);
        if (idx >= 0) local.currentIndex = idx;
      }
      renderSpellingDrill();
    }

    async function submitAttempt(event) {
      event?.preventDefault();
      const word = currentQueueWord();
      const input = $("spellingTypedInput");
      const typed = input?.value || "";
      if (!word || !typed.trim()) {
        setStatus("先输入你认为正确的拼写。", true);
        return;
      }
      try {
        const result = await api(`/api/writing/spelling-words/${encodeURIComponent(word.word_id)}/attempt`, { typed });
        const storedResult = { ...result, _typed: typed };
        drillState().result = storedResult;

        // Update word in queue + items
        Object.assign(word, {
          current_streak: result.current_streak,
          review_stage: result.review_stage ?? word.review_stage,
          status: result.status,
          attempt_count: Number(word.attempt_count || 0) + 1,
          correct_count: Number(word.correct_count || 0) + (result.correct ? 1 : 0),
        });
        const itemsWord = currentItems().find((w) => w.word_id === word.word_id);
        if (itemsWord) Object.assign(itemsWord, word);

        const local = drillState();
        if (result.correct) {
          local.doneCount += 1;
          setStatus(result.status === "mastered" ? "恭喜！这个词已毕业，进入已掌握名单。" : "");
        } else {
          // Re-queue: push to end of session queue
          const requeueCount = (local.requeueMap[word.word_id] || 0) + 1;
          local.requeueMap[word.word_id] = requeueCount;
          local.queue.push({ ...word });
          setStatus("");
        }

        renderSpellingDrill();
        if (result.correct) {
          window.setTimeout(() => {
            if (drillState().result === storedResult) nextWord();
          }, 800);
        }
      } catch (error) {
        setStatus(error.message || String(error), true);
      }
    }

    async function updateWord(wordId, payload) {
      const result = await api(`/api/writing/spelling-words/${encodeURIComponent(wordId)}`, payload, { method: "PATCH" });
      const index = currentItems().findIndex((word) => word.word_id === wordId);
      if (index >= 0) currentItems()[index] = result;
      const local = drillState();
      const qi = local.queue.findIndex((w) => w.word_id === wordId);
      if (qi >= 0) local.queue[qi] = result;
      local.result = null;
      local.hintLevel = 0;
      renderSpellingDrill();
      return result;
    }

    async function deleteWord(wordId) {
      await api(`/api/writing/spelling-words/${encodeURIComponent(wordId)}`, null, { method: "DELETE" });
      drillState().items = currentItems().filter((word) => word.word_id !== wordId);
      const local = drillState();
      local.queue = local.queue.filter((w) => w.word_id !== wordId);
      local.queuePos = Math.min(local.queuePos, Math.max(0, local.queue.length - 1));
      local.result = null;
      local.hintLevel = 0;
      renderSpellingDrill();
    }

    function bindSpellingDrillEvents() {
      document.querySelectorAll("[data-spelling-scope]").forEach((button) => {
        button.addEventListener("click", () => {
          const scope = button.dataset.spellingScope || "due";
          drillState().scope = scope;
          drillState().currentIndex = 0;
          loadSpellingDrill({ force: true });
        });
      });
      $("spellingDrillList")?.addEventListener("click", (event) => {
        const select = event.target.closest("[data-spelling-select]");
        if (select) {
          selectWord(select.dataset.spellingSelect || "");
          return;
        }
        const master = event.target.closest("[data-spelling-master]");
        if (master) {
          updateWord(master.dataset.spellingMaster || "", { action: "master" }).catch((error) => setStatus(error.message || String(error), true));
          return;
        }
        const remove = event.target.closest("[data-spelling-delete]");
        if (remove) {
          const wordId = remove.dataset.spellingDelete || "";
          const runDelete = () => deleteWord(wordId).catch((error) => setStatus(error.message || String(error), true));
          if (typeof showConfirmDelete === "function") {
            showConfirmDelete("确定把这个拼写错词移出错词库吗？", runDelete);
          } else if (window.confirm("确定把这个拼写错词移出错词库吗？")) {
            runDelete();
          }
        }
      });
      $("spellingPracticeCard")?.addEventListener("submit", submitAttempt);
      $("spellingPracticeCard")?.addEventListener("click", (event) => {
        if (event.target.closest("[data-spelling-hint]")) {
          drillState().hintLevel = Math.min(1, (drillState().hintLevel || 0) + 1);
          renderPracticeCard();
          return;
        }
        if (event.target.closest("[data-spelling-next]")) {
          nextWord();
          return;
        }
        if (event.target.closest("[data-spelling-load-due]")) {
          drillState().scope = "due";
          loadSpellingDrill({ force: true });
          return;
        }
        const reset = event.target.closest("[data-spelling-reset-word]");
        if (reset) {
          updateWord(reset.dataset.spellingResetWord || "", { action: "reset" }).catch((error) => setStatus(error.message || String(error), true));
        }
      });
    }

    return {
      loadSpellingDrill,
      renderSpellingDrill,
      bindSpellingDrillEvents,
    };
  }

  window.IELTSSpellingDrill = {
    createSpellingDrillController,
  };
})();
