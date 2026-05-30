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

    function warmCorpusMarkdownEditor() {
      if (state.prefetch.corpusEditorWarmed) return Promise.resolve();
      if (state.prefetch.corpusEditorWarmPromise) return state.prefetch.corpusEditorWarmPromise;
      state.prefetch.corpusEditorWarmPromise = ensureVditorLoaded().then(() => new Promise((resolve) => {
        const host = document.createElement("div");
        host.className = "editor-prewarm-host";
        document.body.appendChild(host);
        let editor;
        let settled = false;
        const cleanup = () => {
          if (settled) return;
          settled = true;
          window.setTimeout(() => {
            try {
              editor?.destroy?.();
            } catch (_error) {
              // Best effort; this hidden editor only warms Vditor internals.
            }
            host.remove();
            state.prefetch.corpusEditorWarmed = true;
            state.prefetch.corpusEditorWarmPromise = null;
            resolve();
          }, 0);
        };
        try {
          editor = new Vditor(host, {
            value: "",
            mode: "ir",
            height: 120,
            cache: { enable: false },
            toolbar: [],
            after: cleanup,
          });
          window.setTimeout(cleanup, 1800);
        } catch (_error) {
          cleanup();
        }
      })).catch(() => {
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
      if (existing) return Promise.resolve(existing);
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
      const editor = corpusMarkdownEditors[textareaId];
      return !editor || !!editor._corpusReady;
    }

    function setCorpusEditorLoading(textareaId, isLoading) {
      const textarea = $(textareaId);
      if (!textarea) return;
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
              <strong>正在打开编辑器</strong>
              <span>首次加载 Markdown 编辑器需要几秒。</span>
            </div>
          </div>
        `;
        textarea.insertAdjacentElement("afterend", loading);
      }
      loading?.classList.toggle("hidden", !isLoading);
    }

    function setCorpusMarkdownValue(textareaId, value) {
      const textarea = $(textareaId);
      if (textarea) textarea.value = value || "";
      const editor = ensureCorpusMarkdownEditor(textareaId);
      if (editor) {
        if (editor._corpusReady) {
          editor.setValue(value || "", true);
        } else {
          editor._pendingCorpusValue = value || "";
        }
      }
    }

    function ensureCorpusMarkdownEditor(textareaId) {
      if (corpusMarkdownEditors[textareaId]) return corpusMarkdownEditors[textareaId];
      const textarea = $(textareaId);
      if (!textarea || !window.Vditor) return null;
      const mount = document.createElement("div");
      mount.className = "corpus-live-editor";
      textarea.classList.add("hidden");
      textarea.insertAdjacentElement("afterend", mount);
      let editor;
      editor = new Vditor(mount, {
        value: textarea.value || "",
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
          setCorpusEditorLoading(textareaId, false);
          if (editor._pendingCorpusValue !== undefined) {
            editor.setValue(editor._pendingCorpusValue || "", true);
            textarea.value = editor._pendingCorpusValue || "";
            delete editor._pendingCorpusValue;
          }
        },
      });
      editor._corpusReady = false;
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
