(function () {
  "use strict";

  function createCorpusMarkdownEditorController(options) {
    const {
      state,
      $,
      prefetchCanApply,
      vditorCssUrl,
      vditorScriptUrl,
    } = options || {};

    if (!state || typeof $ !== "function") {
      throw new Error("Corpus markdown editor requires shared app state and DOM helpers.");
    }

    const corpusMarkdownEditors = {};
    const dynamicScriptPromises = {};
    function ensureStylesheetLoaded(href) {
      if ([...document.styleSheets].some((sheet) => sheet.href === href)) return Promise.resolve();
      if ([...document.querySelectorAll('link[rel="stylesheet"]')].some((link) => link.href === href)) return Promise.resolve();
      return new Promise((resolve) => {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = href;
        link.onload = resolve;
        link.onerror = resolve;
        document.head.appendChild(link);
      });
    }

    function ensureScriptLoaded(src, globalName) {
      if (globalName && window[globalName]) return Promise.resolve(window[globalName]);
      if (dynamicScriptPromises[src]) return dynamicScriptPromises[src];
      dynamicScriptPromises[src] = new Promise((resolve, reject) => {
        const done = () => {
          window.clearTimeout(timer);
          if (!globalName || window[globalName]) resolve(window[globalName]);
          else reject(new Error(`Script loaded without ${globalName}`));
        };
        const fail = () => {
          window.clearTimeout(timer);
          delete dynamicScriptPromises[src];
          reject(new Error(`Failed to load ${src}`));
        };
        const timer = window.setTimeout(() => {
          delete dynamicScriptPromises[src];
          reject(new Error(`Timed out loading ${src}`));
        }, 8000);
        const existing = [...document.scripts].find((script) => script.src === src);
        if (existing) {
          existing.addEventListener("load", done, { once: true });
          existing.addEventListener("error", fail, { once: true });
          if (!globalName || window[globalName]) done();
          return;
        }
        const script = document.createElement("script");
        script.src = src;
        script.async = true;
        script.onload = done;
        script.onerror = fail;
        document.body.appendChild(script);
      });
      return dynamicScriptPromises[src];
    }

    async function ensureVditorLoaded() {
      ensureStylesheetLoaded(vditorCssUrl);
      await ensureScriptLoaded(vditorScriptUrl, "Vditor");
    }

    // Static fields whose Vditor instance is built once, up front, so the
    // first open of each never pays the ~0.5-1s `new Vditor` construction tax.
    const PREWARM_TEXTAREA_IDS = ["p2CorpusText", "p2CorpusP3FollowUp", "p1CorpusText"];

    function prewarmCorpusMarkdownInstances() {
      if (!window.Vditor) return;
      const idle = window.requestIdleCallback || ((fn) => window.setTimeout(fn, 1));
      PREWARM_TEXTAREA_IDS.forEach((textareaId, index) => {
        idle(() => {
          // Skip if already built, or the static textarea isn't in the DOM yet.
          if (corpusMarkdownEditors[textareaId] || !$(textareaId) || !window.Vditor) return;
          // Builds inside the (hidden) dialog; the editor's after() callback
          // keeps it inactive until the field is actually opened, then
          // activateCorpusMarkdownEditor fixes layout with a resize.
          ensureCorpusMarkdownEditor(textareaId);
        }, { timeout: 600 + index * 350 });
      });
    }

    function warmCorpusMarkdownEditor() {
      if (state.prefetch.corpusEditorWarmed) {
        prewarmCorpusMarkdownInstances();
        return Promise.resolve();
      }
      if (state.prefetch.corpusEditorWarmPromise) return state.prefetch.corpusEditorWarmPromise;
      state.prefetch.corpusEditorWarmPromise = ensureVditorLoaded()
        .then(() => {
          state.prefetch.corpusEditorWarmed = true;
          prewarmCorpusMarkdownInstances();
        })
        .catch(() => {
          state.prefetch.corpusEditorWarmed = false;
        })
        .finally(() => {
          state.prefetch.corpusEditorWarmPromise = null;
        });
      return state.prefetch.corpusEditorWarmPromise;
    }

    async function prefetchCorpusEditor(token) {
      await warmCorpusMarkdownEditor();
      if (typeof prefetchCanApply === "function" && !prefetchCanApply(token)) return;
      state.prefetch.corpusEditorWarmed = true;
    }

    function ensureCorpusMarkdownEditorReady(textareaId) {
      const existing = corpusMarkdownEditors[textareaId];
      if (existing) {
        if (existing._corpusReady) activateCorpusMarkdownEditor(textareaId, existing);
        return Promise.resolve(existing);
      }
      const textarea = $(textareaId);
      if (textarea) {
        textarea.classList.remove("hidden");
        textarea.style.removeProperty("display");
        delete textarea.dataset.markdownEditorSource;
      }
      return ensureVditorLoaded()
        .then(() => ensureCorpusMarkdownEditor(textareaId))
        .catch(() => null);
    }

    function getCorpusMarkdownValue(textareaId) {
      const editor = corpusMarkdownEditors[textareaId];
      if (editor?._corpusReady) return editor.getValue();
      return $(textareaId)?.value || "";
    }

    function isCorpusEditorReady(textareaId) {
      return Boolean($(textareaId));
    }

    function ensureCorpusEditorFrame(textarea) {
      if (!textarea) return null;
      const existing = textarea.closest(".corpus-editor-frame");
      if (existing) return existing;
      const frame = document.createElement("div");
      frame.className = "corpus-editor-frame";
      textarea.parentNode?.insertBefore(frame, textarea);
      frame.appendChild(textarea);
      return frame;
    }

    function setCorpusEditorLoading(textareaId, isLoading, options = {}) {
      const textarea = $(textareaId);
      if (!textarea) return;
      const frame = ensureCorpusEditorFrame(textarea);
      const loadingId = `${textareaId}Loading`;
      let loading = document.getElementById(loadingId);
      if (isLoading && !loading) {
        loading = document.createElement("div");
        loading.id = loadingId;
        loading.className = "corpus-editor-loading";
        loading.innerHTML = `
          <div>
            <span class="spinner"></span>
            <div>
              <strong data-corpus-editor-loading-title>正在加载内容</strong>
              <span data-corpus-editor-loading-detail>正在加载内容，请稍候。</span>
            </div>
          </div>
        `;
        (frame || textarea.parentElement)?.appendChild(loading);
      }
      if (loading && isLoading) {
        const title = loading.querySelector("[data-corpus-editor-loading-title]");
        const detail = loading.querySelector("[data-corpus-editor-loading-detail]");
        if (title) title.textContent = options.title || "正在加载内容";
        if (detail) detail.textContent = options.detail || "窗口已打开，内容马上出现。";
      }
      loading?.classList.toggle("hidden", !isLoading);
    }

    function setCorpusMarkdownValue(textareaId, value) {
      const textarea = $(textareaId);
      if (textarea) textarea.value = value || "";
      const editor = corpusMarkdownEditors[textareaId];
      if (editor) {
        if (editor._corpusReady) {
          editor.setValue(value || "", true);
          activateCorpusMarkdownEditor(textareaId, editor);
        } else {
          editor._pendingCorpusValue = value || "";
        }
      }
      setCorpusEditorLoading(textareaId, false);
    }

    function activateCorpusMarkdownEditor(textareaId, editor = corpusMarkdownEditors[textareaId]) {
      const textarea = $(textareaId);
      if (!textarea || !editor?._corpusReady) return;
      const mount = editor._corpusMount || textarea.closest(".corpus-editor-frame")?.querySelector(".corpus-live-editor");
      mount?.classList.remove("hidden");
      textarea.dataset.markdownEditorSource = "true";
      textarea.classList.add("hidden");
      textarea.style.display = "none";
      setCorpusEditorLoading(textareaId, false);
      window.requestAnimationFrame?.(() => window.dispatchEvent(new Event("resize")));
    }

    function ensureCorpusMarkdownEditor(textareaId) {
      if (corpusMarkdownEditors[textareaId]) return corpusMarkdownEditors[textareaId];
      const textarea = $(textareaId);
      if (!textarea || !window.Vditor) return null;
      const frame = ensureCorpusEditorFrame(textarea);
      const mount = document.createElement("div");
      mount.className = "corpus-live-editor hidden";
      (frame || textarea.parentElement)?.appendChild(mount);
      const valueAtCreate = textarea.value || "";
      let editor;
      editor = new Vditor(mount, {
        value: valueAtCreate,
        mode: "ir",
        height: "100%",
        cache: { enable: false },
        counter: { enable: false },
        typewriterMode: false,
        toolbarConfig: { pin: true },
        toolbar: [
          "headings",
          "bold",
          "italic",
          "strike",
          "|",
          "quote",
          "list",
          "ordered-list",
          "|",
          "link",
        ],
        input(value) {
          textarea.value = value || "";
        },
        after() {
          editor._corpusReady = true;
          if (editor._pendingCorpusValue !== undefined) {
            const pendingValue = editor._pendingCorpusValue || "";
            const userEditedTextarea = textarea.value !== (editor._corpusValueAtCreate || "");
            const nextValue = userEditedTextarea ? textarea.value : pendingValue;
            editor.setValue(nextValue || "", true);
            textarea.value = nextValue || "";
            delete editor._pendingCorpusValue;
          }
          if (!textarea.offsetParent && textarea.closest(".hidden")) return;
          activateCorpusMarkdownEditor(textareaId, editor);
        },
      });
      editor._corpusReady = false;
      editor._corpusMount = mount;
      editor._corpusValueAtCreate = valueAtCreate;
      corpusMarkdownEditors[textareaId] = editor;
      return editor;
    }

    return {
      ensureCorpusMarkdownEditorReady,
      getCorpusMarkdownValue,
      isCorpusEditorReady,
      prefetchCorpusEditor,
      setCorpusEditorLoading,
      setCorpusMarkdownValue,
    };
  }

  window.IELTSCorpusMarkdownEditor = {
    createCorpusMarkdownEditorController,
  };
}());
