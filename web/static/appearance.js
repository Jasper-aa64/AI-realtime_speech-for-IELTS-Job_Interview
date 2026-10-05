(function () {
  const FONT_STORAGE_KEY = "ielts-font-style";
  const DARK_MODE_STORAGE_KEY = "ielts-dark-mode";
  const APPEARANCE_STORAGE_KEY = "ielts-appearance-mode";
  const appearanceModes = new Set(["light", "dark", "system"]);
  const fontStyles = new Set(["default", "academic", "popular"]);

  function readAppearanceMode() {
    try {
      const stored = localStorage.getItem(APPEARANCE_STORAGE_KEY);
      if (appearanceModes.has(stored)) return stored;
      const legacy = localStorage.getItem(DARK_MODE_STORAGE_KEY);
      if (legacy === "1") return "dark";
      if (legacy === "0") return "light";
    } catch (_error) {
      // With unavailable storage, follow the system for this session.
    }
    return "system";
  }

  function systemAppearanceQuery() {
    return typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: dark)")
      : null;
  }

  function isDarkMode(mode, query) {
    return mode === "dark" || (mode === "system" && query?.matches === true);
  }

  function bootstrapAppearance() {
    if (!isDarkMode(readAppearanceMode(), systemAppearanceQuery())) return;
    document.documentElement.classList.add("theme-dark", "boot-theme-dark");
    document.documentElement.style.background = "#071119";
    document.documentElement.style.colorScheme = "dark";
  }

  function createAppearanceControls({ state }) {
    if (!state) {
      throw new Error("IELTSAppearance requires the shared app state.");
    }

    let fontStyleTransitionTimer = null;
    const systemQuery = systemAppearanceQuery();
    const onSystemAppearanceChange = () => {
      if (state.appearanceMode === "system") {
        applyAppearanceMode("system", { skipPersist: true });
      }
    };
    if (systemQuery?.addEventListener) {
      systemQuery.addEventListener("change", onSystemAppearanceChange);
    } else if (systemQuery?.addListener) {
      systemQuery.addListener(onSystemAppearanceChange);
    }

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

    function applyAppearanceMode(value, options = {}) {
      const mode = appearanceModes.has(value) ? value : "system";
      const active = isDarkMode(mode, systemQuery);
      state.appearanceMode = mode;
      state.darkMode = active;
      document.documentElement.classList.toggle("theme-dark", active);
      document.documentElement.classList.remove("boot-theme-dark");
      document.documentElement.style.background = "";
      document.documentElement.style.colorScheme = active ? "dark" : "light";
      document.body.classList.toggle("theme-dark", active);
      const select = document.getElementById("appearanceModeSelect");
      if (select) select.value = mode;
      if (!options.skipPersist) {
        try {
          localStorage.setItem(APPEARANCE_STORAGE_KEY, mode);
          // Preserve compatibility with existing manual preferences. System mode
          // is independent of this key; OS changes must never become a manual choice.
          if (mode !== "system") localStorage.setItem(DARK_MODE_STORAGE_KEY, active ? "1" : "0");
        } catch (_error) {
          // Ignore storage failures; the visual selection still applies for this session.
        }
      }
    }

    function applyDarkMode(enabled, options = {}) {
      applyAppearanceMode(enabled ? "dark" : "light", options);
    }

    function loadDarkMode() {
      applyAppearanceMode(readAppearanceMode(), { skipPersist: true });
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
      applyAppearanceMode,
      loadDarkMode,
      loadFontStyle,
    };
  }

  window.IELTSAppearance = {
    bootstrapAppearance,
    createAppearanceControls,
  };
})();
