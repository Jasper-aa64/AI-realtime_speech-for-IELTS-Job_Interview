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
          scope: "active",
          loaded: false,
          loadingPromise: null,
          currentIndex: 0,
          result: null,
          hintLevel: 0,
        };
      }
      return state.spellingDrill;
    }

    function currentItems() {
      return drillState().items || [];
    }

    function currentWord() {
      const items = currentItems();
      if (!items.length) return null;
      const index = Math.max(0, Math.min(drillState().currentIndex || 0, items.length - 1));
      drillState().currentIndex = index;
      return items[index] || null;
    }

    function statText(payload) {
      const stats = payload?.stats || drillState().stats || {};
      const accuracy = Math.round(Number(stats.accuracy || 0) * 100);
      return `${Number(stats.active || 0)} 个待练 · ${Number(stats.mastered || 0)} 个已掌握 · 正确率 ${accuracy}%`;
    }

    function wrongFormsText(word) {
      const forms = Array.isArray(word?.wrong_forms) ? word.wrong_forms.filter(Boolean) : [];
      return forms.length ? forms.join(" / ") : "暂无错拼记录";
    }

    function hintText(word) {
      const level = drillState().hintLevel || 0;
      if (!word || !level) return "";
      const correct = String(word.correct_spelling || "");
      if (level === 1) return `首字母：${correct.slice(0, 1) || "-"}`;
      return `首字母：${correct.slice(0, 1) || "-"} · ${correct.length} 个字母`;
    }

    function setStatus(message, isError = false) {
      const status = $("spellingDrillStatus");
      if (!status) return;
      status.textContent = message || "";
      status.classList.toggle("error", Boolean(isError));
    }

    async function fetchSpellingWords(scope = drillState().scope || "active", options = {}) {
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

    function applySpellingPayload(payload) {
      const local = drillState();
      local.items = payload.items || [];
      local.stats = payload.stats || {};
      local.loaded = true;
      local.currentIndex = Math.min(local.currentIndex || 0, Math.max(0, local.items.length - 1));
      local.result = null;
      local.hintLevel = 0;
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
        const payload = await fetchSpellingWords(local.scope || "active", options);
        applySpellingPayload(payload);
        renderSpellingDrill();
      } catch (error) {
        if (stats) stats.textContent = "加载失败";
        if (list) list.innerHTML = `<p class="language-book-empty error">${escapeHtml(error.message || String(error))}</p>`;
      }
    }

    function renderScopeButtons() {
      document.querySelectorAll("[data-spelling-scope]").forEach((button) => {
        const active = button.dataset.spellingScope === (drillState().scope || "active");
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }

    function renderSpellingList() {
      const list = $("spellingDrillList");
      if (!list) return;
      const items = currentItems();
      if (!items.length) {
        list.innerHTML = `
          <p class="language-book-empty muted">
            ${drillState().scope === "active" ? "当前没有待练拼写错词。" : "这个范围里还没有错词。"}
          </p>
        `;
        return;
      }
      list.innerHTML = items.map((word, index) => `
        <article class="spelling-word-card ${index === drillState().currentIndex ? "is-current" : ""}" data-spelling-word="${escapeHtml(word.word_id)}">
          <button type="button" class="spelling-word-main" data-spelling-select="${escapeHtml(word.word_id)}">
            <span class="spelling-word-title">
              <strong>${escapeHtml(word.correct_spelling)}</strong>
              <em>${escapeHtml(word.status === "mastered" ? "已掌握" : `连对 ${word.current_streak || 0}/4`)}</em>
            </span>
            <span class="spelling-word-wrong">曾写成：${escapeHtml(wrongFormsText(word))}</span>
            <span class="spelling-word-meta">${escapeHtml(word.chinese_gloss || "暂无中文释义")} · 出现 ${Number(word.occurrence_count || 0)} 次</span>
          </button>
          <div class="spelling-word-actions">
            <button type="button" data-spelling-master="${escapeHtml(word.word_id)}">掌握</button>
            <button type="button" class="danger" data-spelling-delete="${escapeHtml(word.word_id)}">移出</button>
          </div>
        </article>
      `).join("");
    }

    function renderPracticeCard() {
      const card = $("spellingPracticeCard");
      if (!card) return;
      const word = currentWord();
      if (!word) {
        card.innerHTML = `
          <div class="spelling-practice-empty">
            <strong>没有可训练的错词</strong>
            <span>完成作文评分后，页面会自动从拼写批注里整理错词。</span>
          </div>
        `;
        return;
      }
      const result = drillState().result;
      const resultHtml = result ? `
        <div class="spelling-attempt-result ${result.correct ? "is-correct" : "is-wrong"}">
          <strong>${result.correct ? "拼对了" : "这次拼错了"}</strong>
          <span>${result.correct ? `连对 ${result.current_streak || 0}/4` : `正确拼写：${escapeHtml(result.correct_spelling || word.correct_spelling)}`}</span>
          ${!result.correct && (result.explanation || word.explanation) ? `<p>${escapeHtml(result.explanation || word.explanation)}</p>` : ""}
        </div>
      ` : "";
      card.innerHTML = `
        <div class="spelling-practice-head">
          <div>
            <span class="corpus-page-kicker">Spelling Drill</span>
            <h3>${escapeHtml(word.chinese_gloss || "根据错拼回忆正确单词")}</h3>
          </div>
          <span class="spelling-progress-pill">${escapeHtml(word.status === "mastered" ? "已掌握" : `连对 ${word.current_streak || 0}/4`)}</span>
        </div>
        <div class="spelling-prompt-box">
          <span>你之前写成</span>
          <strong>${escapeHtml(wrongFormsText(word))}</strong>
          <small>${escapeHtml(hintText(word))}</small>
        </div>
        <form id="spellingAttemptForm" class="spelling-attempt-form">
          <label for="spellingTypedInput">重新拼写</label>
          <div>
            <input id="spellingTypedInput" type="text" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="输入正确拼写">
            <button type="submit">判分</button>
          </div>
        </form>
        <div class="spelling-practice-actions">
          <button type="button" data-spelling-hint>提示</button>
          <button type="button" data-spelling-next>下一词</button>
          <button type="button" data-spelling-reset-word="${escapeHtml(word.word_id)}">重练</button>
        </div>
        ${resultHtml}
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
      drillState().result = null;
      drillState().hintLevel = 0;
      renderSpellingDrill();
    }

    function nextWord() {
      const items = currentItems();
      if (!items.length) return;
      drillState().currentIndex = (drillState().currentIndex + 1) % items.length;
      drillState().result = null;
      drillState().hintLevel = 0;
      renderSpellingDrill();
    }

    async function submitAttempt(event) {
      event?.preventDefault();
      const word = currentWord();
      const input = $("spellingTypedInput");
      const typed = input?.value || "";
      if (!word || !typed.trim()) {
        setStatus("先输入你认为正确的拼写。", true);
        return;
      }
      try {
        const result = await api(`/api/writing/spelling-words/${encodeURIComponent(word.word_id)}/attempt`, { typed });
        drillState().result = result;
        Object.assign(word, {
          current_streak: result.current_streak,
          status: result.status,
          attempt_count: Number(word.attempt_count || 0) + 1,
          correct_count: Number(word.correct_count || 0) + (result.correct ? 1 : 0),
        });
        setStatus(result.correct && result.status === "mastered" ? "这个词已达到连对 4 次，自动标为已掌握。" : "");
        renderSpellingDrill();
        if (result.correct) {
          window.setTimeout(() => {
            if (drillState().result === result) nextWord();
          }, 700);
        }
      } catch (error) {
        setStatus(error.message || String(error), true);
      }
    }

    async function updateWord(wordId, payload) {
      const result = await api(`/api/writing/spelling-words/${encodeURIComponent(wordId)}`, payload, { method: "PATCH" });
      const index = currentItems().findIndex((word) => word.word_id === wordId);
      if (index >= 0) currentItems()[index] = result;
      drillState().result = null;
      drillState().hintLevel = 0;
      renderSpellingDrill();
      return result;
    }

    async function deleteWord(wordId) {
      await api(`/api/writing/spelling-words/${encodeURIComponent(wordId)}`, null, { method: "DELETE" });
      drillState().items = currentItems().filter((word) => word.word_id !== wordId);
      drillState().currentIndex = Math.min(drillState().currentIndex, Math.max(0, currentItems().length - 1));
      drillState().result = null;
      drillState().hintLevel = 0;
      renderSpellingDrill();
    }

    function bindSpellingDrillEvents() {
      document.querySelectorAll("[data-spelling-scope]").forEach((button) => {
        button.addEventListener("click", () => {
          drillState().scope = button.dataset.spellingScope || "active";
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
          drillState().hintLevel = Math.min(2, (drillState().hintLevel || 0) + 1);
          renderPracticeCard();
          return;
        }
        if (event.target.closest("[data-spelling-next]")) {
          nextWord();
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
