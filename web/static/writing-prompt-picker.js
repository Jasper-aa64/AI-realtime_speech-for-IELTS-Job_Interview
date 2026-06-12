(function () {
  "use strict";

  function createWritingPromptPickerController(options) {
    const {
      state,
      $,
      text,
      escapeHtml,
      centeredLoadingHtml,
      loadWritingPrompts,
      writingPromptPickerTitle,
      writingPromptDisplayTitle,
      writingPromptMeta,
      writingPromptSourceKey,
      writingPromptSourceLabel,
      writingUsablePromptsForSource,
      resolveWritingPickerSource,
      inferWritingCategories,
      inferWritingPromptPatterns,
      writingCategoryLabel,
      writingPromptPatternLabel,
      withWritingPromptPattern,
      setWritingSwitchState,
      showWritingError,
      api,
      ensureWritingPromptImageReady,
      setWritingPrompt,
      eagerImageCount,
    } = options || {};

    if (!state?.writing || typeof $ !== "function" || typeof escapeHtml !== "function") {
      throw new Error("Writing prompt picker requires writing state and shared UI helpers.");
    }

    function closePatternMenu() {
      $("writingPromptPatternFilters")?.classList.remove("is-open");
      $("writingPromptPatternButton")?.setAttribute("aria-expanded", "false");
    }

    function open(taskType = state.writing.taskType || "task1_academic") {
      state.writing.pickerTaskType = taskType;
      $("writingPromptModal")?.classList.remove("hidden");
      document.body.classList.add("modal-open");
      const grid = $("writingPromptGrid");
      if (grid) {
        grid.classList.add("is-loading");
        grid.innerHTML = centeredLoadingHtml("正在加载写作题库", "题目和 Task 1 图表正在准备。");
      }
      renderShell(taskType);
      loadWritingPrompts(taskType)
        .then(() => render())
        .catch(renderError);
    }

    function promptWithPattern(prompt) {
      return typeof withWritingPromptPattern === "function" ? withWritingPromptPattern(prompt) : prompt;
    }

    function task2UsablePromptsForSource(taskType, source) {
      return writingUsablePromptsForSource(taskType, source).map(promptWithPattern);
    }

    function fixedQuestionDisplayText(textValue = "") {
      const text = String(textValue || "").replace(/\s+/g, " ").trim();
      const patterns = [
        {
          test: /to what exten[td] do(?: you)? agree (?:or|of) disagree(?: with (?:this|the) (?:statement|opinion|view))?\?/i,
        },
        {
          test: /to what exten[td] do you think[^?]*\?/i,
        },
        {
          test: /do you agree or disagree\?/i,
        },
        {
          test: /(?:do you think|whether|is|are|ls) (?:this|it|that|these|they|the (?:trend|development|change|situation|effect|impact))?(?: is| are)?(?: a)? positive (?:or )?(?:a )?negative (?:development|trend|change|situation|effects?|impacts?|characteristic)?\?/i,
        },
        {
          test: /(?:do you think|whether) (?:the|this|that) (?:trend|development|change|situation|effect|impact) (?:is|are) (?:a )?positive (?:or )?(?:a )?negative (?:development|trend|change|situation|effects?|impacts?|characteristic)?\?/i,
        },
        {
          test: /has (?:this|it|that|the (?:trend|development|change|situation|effect|impact)) become (?:a )?positive (?:or )?(?:a )?negative (?:development|trend|change|situation|effects?|impacts?|characteristic)\?/i,
        },
        {
          test: /discuss\s*&\s*give (?:your|our)(?: own)? opinions?\.?/i,
        },
        {
          test: /discuss both(?: (?:these|the|those))?(?: (?:views?|sides?))?(?: and)?(?: give)? (?:your|our)(?: own)? (?:opinions?|view)\.?/i,
        },
        {
          test: /what is the value[^?]*\?[^?]*what are the arguments in favour[^?]*\?/i,
        },
        {
          test: /to what exten[td]\s+do (?:the )?(?:advantages?|benefits?)[^?]*\boutweigh\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/i,
        },
        {
          test: /do you think [^?]*\bbenefits?\b[^?]*\boutweigh\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/i,
        },
        {
          test: /do (?:the )?benefits?[^?]*\boutweigh\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/i,
        },
        {
          test: /do you think [^?]*\badvantages?\b[^?]*\boutweigh\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/i,
        },
        {
          test: /do (?:the )?advantages?[^?]*\boutweigh\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/i,
        },
        {
          test: /\bnegative effects?\b[^?]*\boutweigh\b[^?]*\bpositive effects?\b[^?]*\?/i,
        },
        {
          test: /\b(?:advantages?|benefits?)\b[^?]*\bor\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/i,
        },
        {
          test: /what are the advantages and disadvantages(?: of this)?\?/i,
        },
        {
          test: /what are the benefits and drawbacks(?: of this)?\?/i,
        },
        {
          test: /what is the value[^?]*\?[^?]*what are the arguments in favour[^?]*\?/i,
        },
        {
          test: /what factors? contribute[^?]*\?[^?]*how realistic[^?]*\?/i,
        },
        {
          test: /(?:why|what (?:do you think )?(?:are )?(?:the )?(?:reasons?|causes?|problems?))[^?]*(?:how (?:can|could)|what can|what could|what should|what (?:are )?(?:the )?(?:solutions?|measures?)|solutions?|measures?|solve|research|encourage|positive|negative|effects?|impact|affect|advantages?|disadvantages?)[^?]*\?/i,
        },
        {
          test: /what (?:problems?|causes?)[^?]*\?[^?]*(?:solutions?|measures|solve)[^?]*\?/i,
        },
        {
          test: /why is this (?:the case|happening)\?[^?]*(?:solutions?|measures|solve|positive|negative)[^?]*\?/i,
        },
        {
          test: /what (?:are )?(?:the )?(?:causes?|reasons?)[^?]*\?[^?]*(?:effects?|impact|affect)[^?]*\?/i,
        },
        {
          test: /(?:what|why|how)[^?]*\?[^?]*(?:what|why|how|do you think)[^?]*\?/i,
        },
      ];
      return patterns.map((item) => text.match(item.test)?.[0]).find(Boolean) || "";
    }

    function promptPreviewHtml(prompt) {
      const text = String(prompt.prompt || "").replace(/\s+/g, " ").trim();
      const fixedText = fixedQuestionDisplayText(text);
      if (!fixedText) return escapeHtml(text);
      const escaped = escapeHtml(text);
      const fixedEscaped = escapeHtml(fixedText);
      const normalizedNeedles = [
        fixedText,
        fixedText.replace(" or a negative", " or negative"),
      ].map(escapeHtml);
      const needle = normalizedNeedles.find((item) => escaped.toLowerCase().includes(item.toLowerCase()));
      if (!needle) {
        return `${escaped}<span class="writing-prompt-card-fixed-line">${fixedEscaped}</span>`;
      }
      const index = escaped.toLowerCase().indexOf(needle.toLowerCase());
      return `${escaped.slice(0, index)}<strong class="writing-prompt-card-fixed-line">${fixedEscaped}</strong>${escaped.slice(index + needle.length)}`;
    }

    function close() {
      $("writingPromptModal")?.classList.add("hidden");
      document.body.classList.remove("modal-open");
    }

    function thumbUrlFor(imageUrl = "") {
      const raw = String(imageUrl || "").trim();
      if (!raw.startsWith("/assets/")) return raw;
      return `/assets/thumbs/${raw.slice("/assets/".length)}.webp`;
    }

    function promptChoiceImageHtml(prompt, imageLoading, imagePriority) {
      const originalUrl = String(prompt?.image_url || "").trim();
      if (!originalUrl) return "Task 1 chart";
      const thumbUrl = thumbUrlFor(originalUrl);
      return `<img src="${escapeHtml(thumbUrl)}" data-original-src="${escapeHtml(originalUrl)}" alt="" loading="${imageLoading}" decoding="async" fetchpriority="${imagePriority}">`;
    }

    function handlePromptThumbError(image) {
      const wrap = image?.closest?.(".writing-prompt-choice-image");
      const originalUrl = image?.dataset?.originalSrc || "";
      if (originalUrl && image?.dataset?.thumbFallback !== "true" && image.src !== originalUrl) {
        image.dataset.thumbFallback = "true";
        image.src = originalUrl;
        return;
      }
      wrap?.classList.add("placeholder");
      image?.remove();
    }

    function choiceHtml(prompt, active = false, index = 0) {
      const isTask1 = prompt.task_type === "task1_academic";
      const isCambridgePrompt = writingPromptSourceKey(prompt) === "cambridge";
      const choiceTitle = isCambridgePrompt
        ? writingPromptPickerTitle(prompt)
        : writingPromptDisplayTitle(prompt);
      const choiceMeta = isCambridgePrompt ? "" : writingPromptMeta(prompt);
      const loadImmediately = isTask1 && index < eagerImageCount;
      const imageLoading = loadImmediately ? "eager" : "lazy";
      const imagePriority = loadImmediately ? "auto" : "low";
      const imageHtml = isTask1
        ? `<span class="writing-prompt-choice-image${prompt.image_url ? "" : " placeholder"}">${promptChoiceImageHtml(prompt, imageLoading, imagePriority)}</span>`
        : "";
      return `
        <button type="button" class="writing-prompt-choice ${isTask1 ? "task1-choice" : "task2-choice"} ${active ? "active" : ""}" data-writing-prompt-choice="${escapeHtml(prompt.id)}">
          ${imageHtml}
          <span class="writing-prompt-choice-body">
            <strong>${escapeHtml(choiceTitle)}</strong>
            ${choiceMeta ? `<small class="writing-prompt-choice-subtitle">${escapeHtml(choiceMeta)}</small>` : ""}
            <span class="writing-prompt-preview">${isTask1 ? escapeHtml(String(prompt.prompt || "").split(/\n+/)[0] || "") : promptPreviewHtml(prompt)}</span>
          </span>
        </button>
      `;
    }

    function catalogSlotHtml(slot) {
      const isTask1 = slot.task_type === "task1_academic";
      const statusText = isTask1 ? "待导入授权题干/配图" : "待导入授权题干";
      return `
        <button type="button" class="writing-prompt-choice ${isTask1 ? "task1-choice" : "task2-choice"} missing" disabled aria-disabled="true">
          ${isTask1 ? `<span class="writing-prompt-choice-image placeholder">Task 1 chart</span>` : ""}
          <span class="writing-prompt-choice-body">
            <strong>${escapeHtml(slot.source_label || slot.id || "Cambridge IELTS")}</strong>
            <small>${escapeHtml(statusText)}</small>
            <span>${escapeHtml(isTask1 && slot.expected_image_url ? slot.expected_image_url : "Add an authorized prompt JSON file with this id to enable the slot.")}</span>
          </span>
        </button>
      `;
    }

    function render() {
      const taskType = state.writing.pickerTaskType || state.writing.taskType || "task1_academic";
      renderShell(taskType);
      const selectedSource = resolveWritingPickerSource(taskType);
      renderSourceFilters(taskType);
      renderPatternFilters(taskType);
      renderTypeFilters(taskType);
      const selectedCategory = state.writing.pickerCategoryFilters[taskType] || "";
      const selectedPattern = state.writing.pickerPromptPatternFilters?.[taskType] || "";
      const prompts = task2UsablePromptsForSource(taskType, selectedSource)
        .filter((prompt) => taskType !== "task1_academic" || !selectedCategory || prompt.category === selectedCategory)
        .filter((prompt) => taskType !== "task2" || !selectedPattern || prompt.prompt_pattern === selectedPattern);
      const missingSlots = [];
      const grid = $("writingPromptGrid");
      if (!grid) return;
      grid.classList.remove("is-loading");
      if (!prompts.length && !missingSlots.length) {
        grid.innerHTML = '<p class="muted writing-prompt-empty">当前筛选下没有可用题目。</p>';
        return;
      }
      grid.innerHTML = [
        ...prompts.map((prompt, index) => choiceHtml(prompt, prompt.id === state.writing.prompt?.id, index)),
        ...missingSlots.map((slot) => catalogSlotHtml(slot)),
      ].join("");
      grid.querySelectorAll("[data-writing-prompt-choice]").forEach((button) => {
        button.querySelectorAll(".writing-prompt-choice-image img").forEach((image) => {
          image.addEventListener("error", () => handlePromptThumbError(image));
        });
        button.addEventListener("click", () => {
          if (state.writing.dirty && !window.confirm("当前作文还没有保存，确定要换题吗？")) return;
          const prompt = prompts.find((item) => item.id === button.dataset.writingPromptChoice);
          if (!prompt) return;
          state.writing.taskType = prompt.task_type || taskType;
          if (prompt.task_type === "task1_academic" && prompt.image_url) {
            ensureWritingPromptImageReady(prompt.image_url).catch(() => null);
          }
          setWritingPrompt(prompt, true);
          close();
        });
      });
    }

    function renderSourceFilters(taskType) {
      const target = $("writingPromptSourceFilters");
      if (!target) return;
      const counts = {
        cambridge: task2UsablePromptsForSource(taskType, "cambridge").length,
        reported: task2UsablePromptsForSource(taskType, "reported").length,
        other: task2UsablePromptsForSource(taskType, "other").length,
      };
      const selected = state.writing.pickerSourceFilters[taskType] || "cambridge";
      target.innerHTML = ["cambridge", "reported", "other"].map((source) => `
        <button type="button" class="writing-source-filter ${selected === source ? "active" : ""}" data-writing-prompt-source="${escapeHtml(source)}">
          ${escapeHtml(writingPromptSourceLabel(source))}
          <span>${escapeHtml(counts[source] || 0)}</span>
        </button>
      `).join("");
      target.querySelectorAll("[data-writing-prompt-source]").forEach((button) => {
        button.addEventListener("click", () => {
          state.writing.pickerSourceFilters[taskType] = button.dataset.writingPromptSource || "cambridge";
          state.writing.pickerCategoryFilters[taskType] = "";
          if (state.writing.pickerPromptPatternFilters) state.writing.pickerPromptPatternFilters[taskType] = "";
          render();
        });
      });
    }

    function renderError(error) {
      const grid = $("writingPromptGrid");
      if (grid) {
        grid.classList.remove("is-loading");
        grid.innerHTML = `
          <div class="writing-prompt-load-error">
            <strong>写作题库加载失败</strong>
            <span>${escapeHtml(error?.message || String(error || "请稍后重试。"))}</span>
          </div>
        `;
      }
      showWritingError(error);
    }

    function renderShell(taskType) {
      setWritingSwitchState(".writing-prompt-modal-toolbar .writing-task-switch", taskType);
      document.querySelectorAll("[data-writing-picker-task]").forEach((button) => {
        button.classList.toggle("active", button.dataset.writingPickerTask === taskType);
      });
      text("writingPromptModalHint", taskType === "task1_academic"
        ? "Task 1 有图表；剑雅真题按 20 到 1 排列，仅显示已导入的可用原题。"
        : "Task 2 按问法筛选；同一句型会归在一起，便于看分布和套用对应框架。");
    }

    function renderTypeFilters(taskType) {
      const target = $("writingPromptPatternFilters");
      const legacyTarget = $("writingPromptTypeFilters");
      const panel = $("writingPromptPatternPanel");
      const toggle = $("writingPromptPatternToggle");
      if (!target) return;
      if (taskType !== "task1_academic") {
        legacyTarget?.classList.add("hidden");
        return;
      }
      if (legacyTarget) legacyTarget.innerHTML = "";
      legacyTarget?.classList.add("hidden");
      panel?.classList.remove("hidden");
      const selectedSource = state.writing.pickerSourceFilters[taskType] || "cambridge";
      const basePrompts = task2UsablePromptsForSource(taskType, selectedSource);
      const categories = inferWritingCategories(basePrompts);
      const selected = state.writing.pickerCategoryFilters[taskType] || "";
      text("writingPromptFilterLabel", "");
      text("writingPromptCurrentPattern", "");
      target.innerHTML = [
        `<button type="button" class="writing-type-filter ${selected ? "" : "active"}" data-writing-prompt-category=""><strong>全部</strong><span>${escapeHtml(basePrompts.length)}</span></button>`,
        ...categories.map((item) => `
          <button type="button" class="writing-type-filter ${selected === item.category ? "active" : ""}" data-writing-prompt-category="${escapeHtml(item.category)}">
            <strong>${escapeHtml(item.label || writingCategoryLabel?.(item.category) || item.category)}</strong>
            <span>${escapeHtml(item.count ?? "")}</span>
          </button>
        `),
      ].join("");
      target.classList.remove("hidden");
      target.classList.add("is-task1");
      target.classList.remove("is-task2", "is-open");
      toggle?.setAttribute("aria-expanded", "true");
      if (toggle) toggle.onclick = null;
      panel?.classList.remove("is-open");
      target.querySelectorAll("[data-writing-prompt-category]").forEach((button) => {
        button.addEventListener("click", () => {
          state.writing.pickerCategoryFilters[taskType] = button.dataset.writingPromptCategory || "";
          render();
        });
      });
    }

    function clearTypeFilters() {
      const target = $("writingPromptTypeFilters");
      if (!target) return;
      target.innerHTML = "";
      target.classList.add("hidden");
    }

    function renderPatternFilters(taskType) {
      const target = $("writingPromptPatternFilters");
      if (!target) return;
      const panel = $("writingPromptPatternPanel");
      const toggle = $("writingPromptPatternToggle");
      if (taskType !== "task2") {
        target.innerHTML = "";
        target.classList.add("hidden");
        return;
      }
      panel?.classList.remove("hidden");
      clearTypeFilters();
      const selectedSource = state.writing.pickerSourceFilters[taskType] || "cambridge";
      const basePrompts = task2UsablePromptsForSource(taskType, selectedSource);
      const patterns = inferWritingPromptPatterns(basePrompts);
      const selected = state.writing.pickerPromptPatternFilters?.[taskType] || "";
      const selectedItem = patterns.find((item) => item.pattern === selected);
      text("writingPromptFilterLabel", "");
      text("writingPromptCurrentPattern", selectedItem
        ? (selectedItem.label || writingPromptPatternLabel?.(selectedItem.pattern) || selectedItem.pattern)
        : "全部问法");
      const currentLabel = selectedItem
        ? (selectedItem.label || writingPromptPatternLabel?.(selectedItem.pattern) || selectedItem.pattern)
        : "全部问法";
      const currentCount = selectedItem ? selectedItem.count : basePrompts.length;
      target.innerHTML = `
        <div class="writing-pattern-menu">
          <button id="writingPromptPatternButton" type="button" class="writing-pattern-menu-button" aria-expanded="false" aria-haspopup="listbox">
            <strong>${escapeHtml(currentLabel)}</strong>
            <span>${escapeHtml(currentCount)}</span>
            <svg aria-hidden="true" viewBox="0 0 16 16"><path d="M4 6l4 4 4-4"></path></svg>
          </button>
          <div class="writing-pattern-menu-list" role="listbox" aria-label="问法筛选">
            <button type="button" class="writing-pattern-menu-option ${selected ? "" : "active"}" data-writing-prompt-pattern="">
              <strong>全部问法</strong><span>${escapeHtml(basePrompts.length)}</span>
            </button>
            ${patterns.map((item) => `
              <button type="button" class="writing-pattern-menu-option ${selected === item.pattern ? "active" : ""}" data-writing-prompt-pattern="${escapeHtml(item.pattern)}">
                <strong>${escapeHtml(item.label || writingPromptPatternLabel?.(item.pattern) || item.pattern)}</strong>
                <span>${escapeHtml(item.count ?? "")}</span>
              </button>
            `).join("")}
          </div>
        </div>
      `;
      target.classList.remove("hidden");
      target.classList.add("is-task2");
      target.classList.remove("is-task1", "is-open");
      toggle?.setAttribute("aria-expanded", "true");
      if (toggle) toggle.onclick = null;
      panel?.classList.remove("is-open");
      target.querySelector("#writingPromptPatternButton")?.addEventListener("click", (event) => {
        event.stopPropagation();
        const nextOpen = !target.classList.contains("is-open");
        target.classList.toggle("is-open", nextOpen);
        event.currentTarget?.setAttribute("aria-expanded", String(nextOpen));
      });
      target.querySelectorAll("[data-writing-prompt-pattern]").forEach((button) => {
        button.addEventListener("click", (event) => {
          event.stopPropagation();
          if (!state.writing.pickerPromptPatternFilters) state.writing.pickerPromptPatternFilters = {};
          state.writing.pickerPromptPatternFilters[taskType] = button.dataset.writingPromptPattern || "";
          closePatternMenu();
          render();
        });
      });
    }

    async function chooseRandom(confirmDirty = true) {
      if (confirmDirty && state.writing.dirty && !window.confirm("当前作文还没有保存，确定要换题吗？")) return;
      const taskType = state.writing.taskType || "task1_academic";
      const prompt = await api("/api/writing/prompts/random", {
        task_type: taskType,
        category: "",
        prompt_pattern: state.writing.pickerPromptPatternFilters?.[taskType] || "",
      });
      setWritingPrompt(prompt, true);
    }

    async function switchTask(taskType) {
      state.writing.pickerTaskType = taskType;
      renderShell(taskType);
      const grid = $("writingPromptGrid");
      if (grid) {
        grid.classList.add("is-loading");
        grid.innerHTML = centeredLoadingHtml("正在加载写作题库", "题目和 Task 1 图表正在准备。");
      }
      await loadWritingPrompts(taskType).catch(renderError);
      render();
    }

    return {
      chooseRandom,
      close,
      open,
      render,
      renderError,
      renderShell,
      switchTask,
    };
  }

  document.addEventListener("click", (event) => {
    if (event.target?.closest?.(".writing-pattern-menu")) return;
    const controller = window.IELTSWritingPromptPicker;
    if (!controller) return;
    document.getElementById("writingPromptPatternFilters")?.classList.remove("is-open");
    document.getElementById("writingPromptPatternButton")?.setAttribute("aria-expanded", "false");
  });

  window.IELTSWritingPromptPicker = { createWritingPromptPickerController };
})();
