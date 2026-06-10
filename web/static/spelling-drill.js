/*
 * Spelling Drill — Nocturne Reader edition.
 * State machine: loading | empty | drill | done | library
 * Single container (#spellingPracticeCard). No split layout.
 *
 * KEY DESIGN:
 *  - S() patches the existing state.spellingDrill object (app.js pre-creates it)
 *  - renderDrill() does PARTIAL in-place DOM updates for same-word state changes
 *    (submit answer, retry, hint) → no card animation replay, no progress jump
 *  - Full card rebuild only on new word (gotoNext) → animation plays once, intentionally
 */
(function () {
  "use strict";

  function createSpellingDrillController(options) {
    const { state, $, escapeHtml, api, showConfirmDelete } = options || {};
    if (!state || typeof $ !== "function" || typeof api !== "function") {
      throw new Error("Spelling drill controller requires shared app state and helpers.");
    }

    // ─── State ───────────────────────────────────────────────────────
    // app.js pre-creates state.spellingDrill with a minimal shape.
    // S() patches in all fields our controller needs, once, via _drillReady flag.
    function S() {
      const sd = state.spellingDrill;
      if (!sd._drillReady) {
        sd.view           = "drill";   // "drill" | "library"
        sd.phase          = "idle";    // "idle" | "loading" | "ready"
        sd.scope          = "due";     // always open on today's due queue
        sd.items          = Array.isArray(sd.items) ? sd.items : [];
        sd.stats          = sd.stats  || {};
        sd.queue          = [];
        sd.queuePos       = 0;
        sd.requeueMap     = {};
        sd.doneCount      = 0;
        sd.queueInitialLen= 0;
        sd.result         = null;
        sd.retryTyped     = null;      // last rewrite attempt after a wrong
        sd.retryCorrect   = false;     // whether the rewrite matched
        sd.loadingPromise = sd.loadingPromise || null;
        sd._drillReady    = true;
      }
      return sd;
    }

    const root     = () => $("spellingPracticeCard");
    const sideList = () => $("spellingDrillList");

    function currentWord() {
      const s = S();
      return s.queue[s.queuePos] || null;
    }

    // ─── Helpers ─────────────────────────────────────────────────────
    function wrongFormsText(word) {
      const forms = Array.isArray(word?.wrong_forms) ? word.wrong_forms.filter(Boolean) : [];
      return forms.length ? forms.join(" · ") : "—";
    }

    function letterDiff(typed, correct) {
      const t  = typed   || "";
      const c  = correct || "";
      const lc = c.toLowerCase();
      const lt = t.toLowerCase();
      const mx = Math.max(t.length, c.length);
      let html = "";
      for (let i = 0; i < mx; i++) {
        if (i < t.length) {
          const ok = i < c.length && lt[i] === lc[i];
          html += `<span class="nr-letter ${ok ? "is-ok" : "is-bad"}">${escapeHtml(t[i])}</span>`;
        } else {
          html += `<span class="nr-letter is-miss">${escapeHtml(c[i])}</span>`;
        }
      }
      return html;
    }

    function setStatus(msg, isError = false) {
      const el = $("spellingDrillStatus");
      if (!el) return;
      el.textContent = msg || "";
      el.classList.toggle("error", Boolean(isError));
    }

    function setHeaderStats() {
      const el = $("spellingDrillStats");
      if (!el) return;
      const s   = S().stats || {};
      const due = Number(s.due     || 0);
      const act = Number(s.active  || 0);
      const mst = Number(s.mastered|| 0);
      const acc = Math.round(Number(s.accuracy || 0) * 100);
      el.innerHTML = `
        <span class="nr-stat"><b>${due}</b>待复习</span>
        <span class="nr-stat-dot">·</span>
        <span class="nr-stat"><b>${act}</b>学中</span>
        <span class="nr-stat-dot">·</span>
        <span class="nr-stat"><b>${mst}</b>已掌握</span>
        <span class="nr-stat-dot">·</span>
        <span class="nr-stat"><b>${acc}%</b>正确率</span>
      `;
    }

    function updateDueDot() {
      const s = S();
      const due = s.scope === "due" && s.queueInitialLen
        ? Math.max(0, Number(s.queueInitialLen || 0) - Number(s.doneCount || 0))
        : Number(s.stats?.due || 0);
      const dot = $("spellingDrillDueDot");
      if (!dot) return;
      dot.classList.toggle("hidden", due <= 0);
      dot.setAttribute("data-count", String(due));
    }

    function syncScopeTabs() {
      document.querySelectorAll("[data-spelling-scope]").forEach((btn) => {
        const on = btn.dataset.spellingScope === S().scope;
        btn.classList.toggle("is-active", on);
        btn.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }

    // ─── Data ────────────────────────────────────────────────────────
    async function fetchWords(scope, { force = false } = {}) {
      const s = S();
      s.scope = scope;
      if (force) s.loadingPromise = null;
      if (!s.loadingPromise) {
        s.loadingPromise = api(`/api/writing/spelling-words?scope=${encodeURIComponent(scope)}`)
          .finally(() => { s.loadingPromise = null; });
      }
      return s.loadingPromise;
    }

    function ingest(payload, { resetQueue = true } = {}) {
      const s = S();
      s.items = payload.items || [];
      s.stats = payload.stats || {};
      s.phase = "ready";
      if (resetQueue) {
        s.queue          = [...s.items];
        s.queuePos       = 0;
        s.requeueMap     = {};
        s.doneCount      = 0;
        s.queueInitialLen= s.items.length;
        s.result         = null;
        s.retryTyped     = null;
        s.retryCorrect   = false;
      }
    }

    async function load({ force = false, resetQueue = true, _pivoted = false } = {}) {
      const s  = S();
      s.phase  = "loading";
      render();
      try {
        const payload = await fetchWords(s.scope, { force });
        ingest(payload, { resetQueue });
      } catch (err) {
        s.phase = "ready";
        setStatus(err.message || String(err), true);
      }
      render();
    }

    // ─── Render helpers ───────────────────────────────────────────────
    // buildPromptHtml / buildInputHtml are called both in full rebuild
    // and in partial (in-place) updates so the card doesn't re-animate.

    // Split chinese_gloss on "；" (or ";") — first part is the Chinese meaning,
    // everything after is a spelling note (e.g. "high 的比较级需要保留 h 后的结构").
    function splitGloss(gloss) {
      const raw  = gloss || "";
      const idx  = raw.search(/[；;]/);
      if (idx < 0) return { chinese: raw, note: "" };
      return { chinese: raw.slice(0, idx).trim(), note: raw.slice(idx + 1).trim() };
    }

    function buildPromptHtml(word, s) {
      const { chinese, note: _note } = splitGloss(word.chinese_gloss);
      const letterCount = String(word.correct_spelling || "").replace(/[^A-Za-z]/g, "").length;
      const fallback    = letterCount > 0 ? `回忆这个 ${letterCount} 字母的词` : "回忆这个词";
      // Only show the Chinese meaning; the spelling note is revealed after Enter.
      return `
        <p class="nr-gloss${chinese ? "" : " is-fallback"}">${escapeHtml(chinese || fallback)}</p>
        <div class="nr-wrong-pill">
          <span class="nr-wrong-tag">曾误作</span>
          <span class="nr-wrong-text">${escapeHtml(wrongFormsText(word))}</span>
        </div>
      `;
    }

    function buildInputHtml(word, result, s) {
      const correctSpell = result
        ? (result.correct_spelling || word.correct_spelling || "")
        : "";

      // ── State A: waiting for first input ──
      // No spelling note here; it only appears after the user presses Enter.
      if (!result) {
        return `
          <form id="spellingAttemptForm" class="nr-slot nr-form" autocomplete="off">
            <span class="nr-note-slot nr-note-slot--placeholder" aria-hidden="true"></span>
            <input id="spellingTypedInput" class="nr-input" type="text"
              autocomplete="off" autocapitalize="none" spellcheck="false"
              placeholder="敲下正确拼写，回车判定">
            <span class="nr-form-spacer" aria-hidden="true"></span>
            <span class="nr-button-spacer" aria-hidden="true"></span>
          </form>
        `;
      }

      // Extract spelling note (the part after "；" in the gloss) for post-Enter reveal.
      const { note } = splitGloss(word.chinese_gloss);
      const noteHtml = note
        ? `<p class="nr-note-slot nr-spell-note" aria-label="拼写提示">${escapeHtml(note)}</p>`
        : `<p class="nr-note-slot nr-note-slot--placeholder" aria-hidden="true"></p>`;

      // ── State B: correct — show green diff, wait for Enter ──
      return result.correct ? `
        <div class="nr-slot nr-result-slot is-correct">
          ${noteHtml}
          <div class="nr-inline-answer" aria-live="polite">
            <p class="nr-answer-line">${letterDiff(result._typed || "", correctSpell)}</p>
          </div>
          <p class="nr-inline-correct nr-inline-correct--placeholder" aria-hidden="true">
            <span class="nr-answer-word" data-label="正解">${escapeHtml(correctSpell)}</span>
          </p>
          <button type="button" class="nr-next-btn" data-spelling-continue>下一题 <kbd>↵</kbd></button>
        </div>
      ` : `
        <div class="nr-slot nr-result-slot is-wrong">
          ${noteHtml}
          <div class="nr-inline-answer" aria-live="polite">
            <p class="nr-answer-line">${letterDiff(result._typed || "", correctSpell)}</p>
          </div>
          <p class="nr-inline-correct">
            <span class="nr-answer-word" data-label="正解">${escapeHtml(correctSpell)}</span>
          </p>
          <button type="button" class="nr-next-btn" data-spelling-continue>下一题 <kbd>↵</kbd></button>
        </div>
      `;
    }

    function focusInputArea(result, s) {
      if (!result) {
        $("spellingTypedInput")?.focus();
      } else {
        // Both correct and wrong states show the continue button
        root().querySelector("[data-spelling-continue]")?.focus();
      }
    }

    // ─── Render ──────────────────────────────────────────────────────
    function render() {
      setHeaderStats();
      updateDueDot();
      syncScopeTabs();
      const s    = S();
      const list = sideList();
      if (list) list.hidden = s.view !== "library";
      const card = root();
      if (!card) return;
      card.hidden = s.view !== "drill";

      if (s.view === "library") { renderLibrary(); return; }
      if (s.phase === "loading") return renderLoading();
      if (!s.items.length)       return renderEmpty();
      if (s.queuePos >= s.queue.length) return renderDone();
      renderDrill();
    }

    function renderLoading() {
      root().innerHTML = `
        <div class="nr-stage nr-stage-loading">
          <div class="nr-spinner" aria-hidden="true"><span></span><span></span><span></span></div>
          <p class="nr-meta">正在翻开错词本…</p>
        </div>
      `;
    }

    function renderEmpty() {
      const s     = S();
      const isDue = s.scope === "due";
      root().innerHTML = `
        <div class="nr-stage nr-stage-empty">
          <svg class="nr-empty-mark" viewBox="0 0 80 80" aria-hidden="true">
            <circle cx="40" cy="40" r="34" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.35"/>
            <path d="M24 40 L36 52 L58 28" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <h3 class="nr-empty-title">${
            isDue ? "今夜已无待复习"
            : s.scope === "mastered" ? "尚无已掌握的词"
            : "错词本空着"
          }</h3>
          <p class="nr-empty-sub">${
            isDue ? "所有词都已按计划排好，明天再来。"
            : s.scope === "mastered" ? "把一个词从生疏背到第六阶，它就会出现在这里。"
            : "去作文里写写错字，我会替你收集起来。"
          }</p>
          <div class="nr-empty-actions">
            ${isDue ? `<button class="nr-btn nr-btn-primary" data-spelling-scope="active">提前练（全部词）</button>` : ""}
            <button class="nr-btn nr-btn-ghost" data-open-library>翻看词库</button>
          </div>
        </div>
      `;
    }

    function renderDone() {
      const s = S();
      root().innerHTML = `
        <div class="nr-stage nr-stage-done">
          <div class="nr-done-seal">
            <svg viewBox="0 0 120 120" aria-hidden="true">
              <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.6"/>
              <circle cx="60" cy="60" r="46" fill="none" stroke="currentColor" stroke-width="0.6" opacity="0.45"/>
              <path d="M40 62 L54 76 L82 46" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <h3 class="nr-done-title">本轮收笔</h3>
          <p class="nr-done-meta">
            复习 <b>${s.doneCount}</b> 词 · 重练 <b>${Object.values(s.requeueMap).reduce((a, b) => a + b, 0)}</b> 次
          </p>
          <div class="nr-empty-actions">
            <button class="nr-btn nr-btn-primary" data-spelling-reload>再来一轮</button>
            <button class="nr-btn nr-btn-ghost" data-open-library>翻看词库</button>
          </div>
        </div>
      `;
    }

    function renderDrill() {
      const s      = S();
      const word   = currentWord();
      if (!word) return renderEmpty();

      const result = s.result;
      const pct    = Math.round((s.doneCount / Math.max(s.queueInitialLen, 1)) * 100);
      const reqs   = s.requeueMap[word.word_id] || 0;
      const progressTextHtml = `<b>${s.doneCount}</b><span>/${s.queueInitialLen}</span>${reqs > 0 ? ` <em class="nr-requeue">·重 ${reqs}</em>` : ""}`;

      // ── Partial in-place update (same word, state changed) ──────────
      // Avoids card animation replay and lets progress-fill CSS transition work.
      const existingCard = root().querySelector(`[data-drill-word]`);
      const sameWord = existingCard &&
        existingCard.dataset.drillWord === String(word.word_id);

      if (sameWord) {
        // Update progress bar (CSS transition animates width smoothly)
        const fill = existingCard.querySelector(".nr-progress-fill");
        const txt  = existingCard.querySelector(".nr-progress-text");
        if (fill) fill.style.width = pct + "%";
        if (txt)  txt.innerHTML = progressTextHtml;

        // Update only the input/answer area
        const bodyEl = existingCard.querySelector(".nr-drill-body");
        if (bodyEl) {
          bodyEl.innerHTML = buildInputHtml(word, result, s);
          focusInputArea(result, s);
          return;
        }
      }

      // ── Full rebuild (new word, or first paint) ──────────────────────
      const stage     = Number(word.review_stage || 0);
      const maxStage = 4;
      const stageDots = Array.from({ length: maxStage }, (_, i) =>
        `<span class="nr-stage-dot ${i < stage ? "is-on" : ""}"></span>`
      ).join("");

      root().innerHTML = `
        <div class="nr-card" data-drill-card data-drill-word="${escapeHtml(String(word.word_id))}">
          <header class="nr-card-head">
            <div class="nr-progress">
              <div class="nr-progress-track">
                <div class="nr-progress-fill" style="width:${pct}%"></div>
              </div>
              <span class="nr-progress-text">${progressTextHtml}</span>
            </div>
            <button type="button" class="nr-lib-btn" data-open-library>
              <svg viewBox="0 0 24 24" aria-hidden="true" width="14" height="14">
                <path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"
                  d="M4 5h12a3 3 0 013 3v11H7a3 3 0 01-3-3V5zM4 5v11M16 8h0M16 12h0M16 16h0"/>
              </svg>
              词库
            </button>
          </header>

          <div class="nr-prompt">${buildPromptHtml(word, s)}</div>

          <div class="nr-drill-body">${buildInputHtml(word, result, s)}</div>

          <div class="nr-meta-row">
            <div class="nr-stage-track">
              ${stageDots}
              <span class="nr-stage-text">阶段 ${stage}/${maxStage}</span>
            </div>
          </div>
        </div>
      `;
      focusInputArea(result, s);
    }

    function renderLibrary() {
      const s     = S();
      const items = s.items || [];
      const groups = [];
      if (items.length) {
        const due      = items.filter((w) => w.is_due);
        const active   = items.filter((w) => !w.is_due && w.status !== "mastered");
        const mastered = items.filter((w) => !w.is_due && w.status === "mastered");
        if (due.length)      groups.push({ title: "待复习", items: due });
        if (active.length)   groups.push({ title: "学中",   items: active });
        if (mastered.length) groups.push({ title: "已掌握", items: mastered });
      }

      const groupHtml = groups.length ? groups.map((g) => `
        <section class="nr-lib-group">
          <h4 class="nr-lib-group-title"><span>${escapeHtml(g.title)}</span><em>${g.items.length}</em></h4>
          <ul class="nr-lib-list">
            ${g.items.map((w) => {
              const stage = Number(w.review_stage || 0);
              return `
                <li class="nr-lib-item" data-spelling-word="${escapeHtml(w.word_id)}">
                  <div class="nr-lib-main">
                    <strong class="nr-lib-word">${escapeHtml(w.correct_spelling)}</strong>
                    <span class="nr-lib-gloss">${escapeHtml(w.chinese_gloss || "—")}</span>
                    <span class="nr-lib-wrong">误：${escapeHtml(wrongFormsText(w))}</span>
                  </div>
                  <div class="nr-lib-side">
                    <span class="nr-lib-stage">阶 ${stage}</span>
                    <button class="nr-lib-act" data-spelling-master="${escapeHtml(w.word_id)}" title="标为已掌握">✓</button>
                    <button class="nr-lib-act is-danger" data-spelling-delete="${escapeHtml(w.word_id)}" title="移出错词本">×</button>
                  </div>
                </li>
              `;
            }).join("")}
          </ul>
        </section>
      `).join("") : `<p class="nr-lib-empty">这个范围里还没有词。</p>`;

      sideList().innerHTML = `
        <header class="nr-lib-head">
          <button class="nr-lib-back" data-close-library>
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M15 18l-6-6 6-6"/>
            </svg>
            回练习
          </button>
          <span class="nr-lib-title">错词本 · ${escapeHtml(
            ({ due: "今日待复习", active: "全部学中", mastered: "已掌握" })[s.scope] || s.scope
          )}</span>
        </header>
        <div class="nr-lib-body">
          ${groupHtml}
        </div>
      `;
    }

    // ─── Actions ─────────────────────────────────────────────────────
    function gotoNext() {
      const s = S();
      s.queuePos    += 1;
      s.result       = null;
      s.retryTyped   = null;
      s.retryCorrect = false;
      render();
    }

    async function submitAttempt(e) {
      e?.preventDefault();
      const word  = currentWord();
      const input = $("spellingTypedInput");
      const typed = input?.value || "";
      if (!word || !typed.trim()) { setStatus("先输入拼写。", true); return; }
      setStatus("");
      try {
        const result = await api(
          `/api/writing/spelling-words/${encodeURIComponent(word.word_id)}/attempt`,
          { typed }
        );
        const stored = { ...result, _typed: typed };
        const s = S();
        s.result = stored;
        Object.assign(word, {
          current_streak: result.current_streak,
          review_stage:   result.review_stage ?? word.review_stage,
          status:         result.status,
          attempt_count:  Number(word.attempt_count || 0) + 1,
          correct_count:  Number(word.correct_count || 0) + (result.correct ? 1 : 0),
        });
        const iw = s.items.find((w) => w.word_id === word.word_id);
        if (iw) Object.assign(iw, word);
        if (result.correct) {
          s.doneCount += 1;
        } else {
          // Insert immediately after current position so the same word
          // appears on the very next card, not buried at the end.
          s.requeueMap[word.word_id] = (s.requeueMap[word.word_id] || 0) + 1;
          s.queue.splice(s.queuePos + 1, 0, { ...word });
        }
        render();
        // No auto-advance: user must press Enter on the continue button.
      } catch (err) {
        setStatus(err.message || String(err), true);
      }
    }

    function submitRetry() {
      const word  = currentWord();
      const input = $("spellingRetryInput");
      const typed = (input?.value || "").trim();
      if (!word || !typed) return;
      const s       = S();
      const correct = String(word.correct_spelling || "").toLowerCase();
      s.retryTyped  = typed;
      s.retryCorrect= typed.toLowerCase() === correct;
      render();
    }

    async function updateWord(wordId, payload) {
      const result = await api(
        `/api/writing/spelling-words/${encodeURIComponent(wordId)}`,
        payload,
        { method: "PATCH" }
      );
      const s   = S();
      const idx = s.items.findIndex((w) => w.word_id === wordId);
      if (idx >= 0) s.items[idx] = result;
      const qi = s.queue.findIndex((w) => w.word_id === wordId);
      if (qi >= 0) s.queue[qi] = result;
      s.result   = null;
      render();
    }

    async function deleteWord(wordId) {
      await api(`/api/writing/spelling-words/${encodeURIComponent(wordId)}`, null, { method: "DELETE" });
      const s   = S();
      s.items = s.items.filter((w) => w.word_id !== wordId);
      s.queue = s.queue.filter((w) => w.word_id !== wordId);
      s.queuePos = Math.min(s.queuePos, Math.max(0, s.queue.length));
      s.result = null;
      render();
    }

    // ─── Events ──────────────────────────────────────────────────────
    function bindSpellingDrillEvents() {
      // Scope tabs (header bar)
      document.querySelectorAll("[data-spelling-scope]").forEach((btn) => {
        btn.addEventListener("click", () => {
          S().scope = btn.dataset.spellingScope || "due";
          S().view  = "drill";
          load({ force: true, resetQueue: true });
        });
      });

      // Card: form submit — only handles the main attempt form
      root()?.addEventListener("submit", (e) => {
        submitAttempt(e);
      });


      // Card: button clicks
      root()?.addEventListener("click", (e) => {
        const t = e.target;
        if (t.closest("[data-spelling-continue]")) { gotoNext(); return; }
        if (t.closest("[data-open-library]"))      { S().view = "library"; render(); return; }
        if (t.closest("[data-spelling-reload]"))   { load({ force: true, resetQueue: true }); return; }
        const scopeBtn = t.closest("[data-spelling-scope]");
        if (scopeBtn) {
          S().scope = scopeBtn.dataset.spellingScope;
          load({ force: true, resetQueue: true });
          return;
        }
      });

      // Library: back + actions
      sideList()?.addEventListener("click", (e) => {
        const t = e.target;
        if (t.closest("[data-close-library]")) { S().view = "drill"; render(); return; }
        const m = t.closest("[data-spelling-master]");
        if (m) {
          updateWord(m.dataset.spellingMaster, { action: "master" })
            .catch((err) => setStatus(err.message, true));
          return;
        }
        const d = t.closest("[data-spelling-delete]");
        if (d) {
          const id  = d.dataset.spellingDelete;
          const run = () => deleteWord(id).catch((err) => setStatus(err.message, true));
          if (typeof showConfirmDelete === "function")
            showConfirmDelete("把这个词从错词本里移走吗？", run);
          else if (window.confirm("把这个词从错词本里移走吗？")) run();
          return;
        }
      });
    }

    return {
      loadSpellingDrill: load,
      renderSpellingDrill: render,
      bindSpellingDrillEvents,
    };
  }

  window.IELTSSpellingDrill = { createSpellingDrillController };
})();
