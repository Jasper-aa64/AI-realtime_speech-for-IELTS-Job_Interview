(function () {
  const FONT_STORAGE_KEY = "ielts-font-style";
  const DARK_MODE_STORAGE_KEY = "ielts-dark-mode";
  const fontStyles = new Set(["default", "academic", "popular"]);

  function createAppearanceControls({ state }) {
    if (!state) {
      throw new Error("IELTSAppearance requires the shared app state.");
    }

    let fontStyleTransitionTimer = null;

    function applyFontStyle(value, options = {}) {
      const style = fontStyles.has(value) ? value : "default";
      state.fontStyle = style;

      if (fontStyleTransitionTimer) {
        clearTimeout(fontStyleTransitionTimer);
      }

      document.querySelectorAll(".font-options").forEach((el) => {
        el.classList.toggle("academic", style === "academic");
        el.classList.toggle("popular", style === "popular");
      });

      document.querySelectorAll("[data-font-style]").forEach((button) => {
        button.classList.toggle("active", button.dataset.fontStyle === style);
      });

      const updateBodyClass = () => {
        document.body.classList.toggle("font-academic", style === "academic");
        document.body.classList.toggle("font-popular", style === "popular");
        fontStyleTransitionTimer = null;
      };
      if (options.immediate) {
        updateBodyClass();
      } else {
        fontStyleTransitionTimer = setTimeout(updateBodyClass, 250);
      }

      try {
        localStorage.setItem(FONT_STORAGE_KEY, style);
      } catch (_error) {
        // Ignore storage failures; the visual selection still applies for this session.
      }
    }

    function applyDarkMode(enabled, options = {}) {
      const active = Boolean(enabled);
      state.darkMode = active;
      document.body.classList.toggle("theme-dark", active);
      const toggle = document.getElementById("darkModeToggle");
      if (toggle) toggle.checked = active;
      if (!options.skipPersist) {
        try {
          localStorage.setItem(DARK_MODE_STORAGE_KEY, active ? "1" : "0");
        } catch (_error) {
          // Ignore storage failures; the visual selection still applies for this session.
        }
      }
    }

    function loadDarkMode() {
      let enabled = false;
      try {
        enabled = localStorage.getItem(DARK_MODE_STORAGE_KEY) === "1";
      } catch (_error) {
        enabled = false;
      }
      applyDarkMode(enabled, { skipPersist: true });
    }

    function loadFontStyle() {
      let stored = "default";
      try {
        stored = localStorage.getItem(FONT_STORAGE_KEY) || "default";
      } catch (_error) {
        stored = "default";
      }
      applyFontStyle(stored, { immediate: true });
    }

    return {
      applyFontStyle,
      applyDarkMode,
      loadDarkMode,
      loadFontStyle,
    };
  }

  window.IELTSAppearance = {
    createAppearanceControls,
  };
})();
