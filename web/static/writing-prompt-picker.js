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
      writingCategoryLabel,
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

    function close() {
      $("writingPromptModal")?.classList.add("hidden");
      document.body.classList.remove("modal-open");
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
        ? `<span class="writing-prompt-choice-image${prompt.image_url ? "" : " placeholder"}">${prompt.image_url ? `<img src="${escapeHtml(prompt.image_url)}" alt="" loading="${imageLoading}" decoding="async" fetchpriority="${imagePriority}" onerror="this.closest('.writing-prompt-choice-image').classList.add('placeholder'); this.remove();">` : "Task 1 chart"}</span>`
        : "";
      return `
        <button type="button" class="writing-prompt-choice ${isTask1 ? "task1-choice" : "task2-choice"} ${active ? "active" : ""}" data-writing-prompt-choice="${escapeHtml(prompt.id)}">
          ${imageHtml}
          <span class="writing-prompt-choice-body">
            <strong>${escapeHtml(choiceTitle)}</strong>
            ${choiceMeta ? `<small class="writing-prompt-choice-subtitle">${escapeHtml(choiceMeta)}</small>` : ""}
            <span>${escapeHtml(String(prompt.prompt || "").split(/\n+/)[0] || "")}</span>
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
      renderTypeFilters(taskType);
      const selectedCategory = state.writing.pickerCategoryFilters[taskType] || "";
      const prompts = writingUsablePromptsForSource(taskType, selectedSource).filter((prompt) => !selectedCategory || prompt.category === selectedCategory);
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
        cambridge: writingUsablePromptsForSource(taskType, "cambridge").length,
        reported: writingUsablePromptsForSource(taskType, "reported").length,
        other: writingUsablePromptsForSource(taskType, "other").length,
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
        : "Task 2 可按题型筛选；剑雅真题按 20 到 1 排列，仅显示已导入的可用原题。");
    }

    function renderTypeFilters(taskType) {
      const target = $("writingPromptTypeFilters");
      if (!target) return;
      const selectedSource = state.writing.pickerSourceFilters[taskType] || "cambridge";
      const categories = inferWritingCategories(writingUsablePromptsForSource(taskType, selectedSource));
      const selected = state.writing.pickerCategoryFilters[taskType] || "";
      target.innerHTML = [
        `<button type="button" class="writing-type-filter ${selected ? "" : "active"}" data-writing-prompt-category="">全部</button>`,
        ...categories.map((item) => `
          <button type="button" class="writing-type-filter ${selected === item.category ? "active" : ""}" data-writing-prompt-category="${escapeHtml(item.category)}">
            ${escapeHtml(writingCategoryLabel(item.category) || item.label)}
            <span>${escapeHtml(item.count ?? "")}</span>
          </button>
        `),
      ].join("");
      target.querySelectorAll("[data-writing-prompt-category]").forEach((button) => {
        button.addEventListener("click", () => {
          state.writing.pickerCategoryFilters[taskType] = button.dataset.writingPromptCategory || "";
          render();
        });
      });
    }

    async function chooseRandom(confirmDirty = true) {
      if (confirmDirty && state.writing.dirty && !window.confirm("当前作文还没有保存，确定要换题吗？")) return;
      const taskType = state.writing.taskType || "task1_academic";
      const prompt = await api("/api/writing/prompts/random", {
        task_type: taskType,
        category: state.writing.pickerCategoryFilters[taskType] || "",
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

  window.IELTSWritingPromptPicker = { createWritingPromptPickerController };
})();
