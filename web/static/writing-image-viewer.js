(function () {
  "use strict";

  function createWritingImageViewerController(options) {
    const {
      state,
      $,
      currentWritingPromptImageUrl,
    } = options || {};

    if (!state || typeof $ !== "function" || typeof currentWritingPromptImageUrl !== "function") {
      throw new Error("Writing image viewer requires shared state, DOM lookup, and image URL resolver.");
    }

    function open(src = currentWritingPromptImageUrl()) {
      const url = String(src || "").trim();
      if (!url) return;
      const viewer = $("writingImageViewer");
      const image = $("writingImageViewerImg");
      if (!viewer || !image) return;
      image.src = url;
      viewer.classList.remove("hidden");
      document.body.classList.add("modal-open");
    }

    function close() {
      const viewer = $("writingImageViewer");
      const image = $("writingImageViewerImg");
      viewer?.classList.add("hidden");
      if (image) image.src = "";
      document.body.classList.remove("modal-open");
    }

    function isOpen() {
      return Boolean($("writingImageViewer") && !$("writingImageViewer").classList.contains("hidden"));
    }

    function canToggle() {
      if (isOpen()) return true;
      const writingPanel = $("writingPanel");
      const writingPanelVisible = Boolean(writingPanel && !writingPanel.classList.contains("hidden"));
      return Boolean(currentWritingPromptImageUrl() && (state.view === "writing" || writingPanelVisible));
    }

    function toggle() {
      if (isOpen()) {
        close();
        return;
      }
      open();
    }

    function isShiftSpaceShortcut(event) {
      const isSpace = event.code === "Space" || event.key === " " || event.key === "Spacebar" || event.key === "Space";
      return Boolean(isSpace && event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey);
    }

    return {
      open,
      close,
      isOpen,
      canToggle,
      toggle,
      isShiftSpaceShortcut,
    };
  }

  window.IELTSWritingImageViewer = { createWritingImageViewerController };
})();
