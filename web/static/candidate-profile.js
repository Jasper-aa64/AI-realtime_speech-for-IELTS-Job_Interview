(function () {
  function createCandidateProfileController({
    state,
    $,
    api,
    defaultFullName,
    defaultEnglishName,
    fullNameStorageKey,
    englishNameStorageKey,
    renderAccountStatus,
  }) {
    let candidateNameSaveTimer = null;

    function candidateNames() {
      return {
        fullName: ($("#fullNameInput")?.value || defaultFullName).trim() || defaultFullName,
        englishName: ($("#englishNameInput")?.value || defaultEnglishName).trim() || defaultEnglishName,
      };
    }

    function storeCandidateNamesLocally(names) {
      try {
        localStorage.setItem(fullNameStorageKey, names.fullName);
        localStorage.setItem(englishNameStorageKey, names.englishName);
      } catch (_error) {
        // Local identity settings still apply for the current session.
      }
    }

    function applyCandidateNames(names, persistLocal = false) {
      const fullName = (names?.fullName || defaultFullName).trim() || defaultFullName;
      const englishName = (names?.englishName || defaultEnglishName).trim() || defaultEnglishName;
      if ($("#fullNameInput")) $("#fullNameInput").value = fullName;
      if ($("#englishNameInput")) $("#englishNameInput").value = englishName;
      if (persistLocal) storeCandidateNamesLocally({ fullName, englishName });
      updateAvatars(englishName);
    }

    async function saveCandidateNames(syncBackend = true) {
      const names = candidateNames();
      updateAvatars(names.englishName);
      if (state.account.authenticated && syncBackend) {
        const payload = await api("/api/accounts/me/", {
          full_name: names.fullName,
          english_name: names.englishName,
          display_name: names.englishName,
        }, { method: "PATCH" });
        state.account.user = payload.user || state.account.user;
        renderAccountStatus("姓名已同步到账号。");
        return;
      }
      storeCandidateNamesLocally(names);
      renderAccountStatus(state.account.backendAvailable ? "未登录，姓名暂存在本机。" : "Django 未连接，姓名暂存在本机。");
    }

    function scheduleCandidateNameSave() {
      updateAvatars(candidateNames().englishName);
      if (candidateNameSaveTimer) clearTimeout(candidateNameSaveTimer);
      candidateNameSaveTimer = setTimeout(() => {
        candidateNameSaveTimer = null;
        saveCandidateNames().catch((error) => renderAccountStatus(error.message, true));
      }, 650);
    }

    function flushCandidateNameSave() {
      if (candidateNameSaveTimer) {
        clearTimeout(candidateNameSaveTimer);
        candidateNameSaveTimer = null;
      }
      saveCandidateNames().catch((error) => renderAccountStatus(error.message, true));
    }

    function updateAvatars(name) {
      const initial = (name || "J").charAt(0).toUpperCase();
      ["userAvatarDesktop", "userAvatar"].forEach((id) => {
        const avatar = $(id);
        if (avatar) avatar.textContent = initial;
      });
    }

    function loadCandidateNames() {
      let fullName = defaultFullName;
      let englishName = defaultEnglishName;
      try {
        fullName = localStorage.getItem(fullNameStorageKey) || fullName;
        englishName = localStorage.getItem(englishNameStorageKey) || englishName;
      } catch (_error) {
        // Use defaults.
      }
      applyCandidateNames({ fullName, englishName });
    }

    return {
      applyCandidateNames,
      candidateNames,
      flushCandidateNameSave,
      loadCandidateNames,
      saveCandidateNames,
      scheduleCandidateNameSave,
      updateAvatars,
    };
  }

  window.IELTSCandidateProfile = { createCandidateProfileController };
})();
