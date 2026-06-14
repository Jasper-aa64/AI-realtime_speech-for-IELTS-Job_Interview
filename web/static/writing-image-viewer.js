(function () {
  "use strict";

  function createWritingImageViewerController(options) {
    const {
      state,
      $,
      currentWritingPromptImageUrl,
      thumbUrlFor,
    } = options || {};

    if (!state || typeof $ !== "function" || typeof currentWritingPromptImageUrl !== "function") {
      throw new Error("Writing image viewer requires shared state, DOM lookup, and image URL resolver.");
    }

    const thumbFor = typeof thumbUrlFor === "function" ? thumbUrlFor : (value) => value;
    let openToken = 0;

    function open(src = currentWritingPromptImageUrl()) {
      const url = String(src || "").trim();
      if (!url) return;
      const viewer = $("writingImageViewer");
      const image = $("writingImageViewerImg");
      if (!viewer || !image) return;

      const token = (openToken += 1);
      image.dataset.targetSrc = url;

      // If the original is already cached, show it directly (no thumb flash).
      const probe = new Image();
      probe.src = url;
      if (probe.complete && probe.naturalWidth > 0) {
        image.src = url;
      } else {
        // Show the thumbnail immediately, then swap to the original the moment
        // it finishes loading — instant open, sharpens up a beat later.
        const thumb = String(thumbFor(url) || "").trim();
        if (thumb && thumb !== url) image.src = thumb;
        const full = new Image();
        full.onload = () => {
          if (openToken === token && image.dataset.targetSrc === url) image.src = url;
        };
        full.src = url;
      }

      viewer.classList.remove("hidden");
      document.body.classList.add("modal-open");
    }

    function close() {
      const viewer = $("writingImageViewer");
      const image = $("writingImageViewerImg");
      // Invalidate any in-flight original-image swap from a prior open().
      openToken += 1;
      viewer?.classList.add("hidden");
      if (image) {
        image.src = "";
        delete image.dataset.targetSrc;
      }
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
