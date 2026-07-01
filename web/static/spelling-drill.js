/*
 * Spelling Drill — Nocturne Reader edition.
 * State machine: loading | empty | drill | done | library
 * Single container (#spellingPracticeCard). No split layout.
 *
 * KEY DESIGN:
 *  - S() patches the existing state.spellingDrill object (app.js pre-creates it)
 *  - renderDrill() does PARTIAL in-place DOM updates for same-word state changes
 *    (submit answer, hint) → no card animation replay, no progress jump
 *  - Full card rebuild only on new word (gotoNext) → animation plays once, intentionally
 */
(function () {
  "use strict";

  function createSpellingDrillController(options) {
    const { state, $, escapeHtml, api, showConfirmDelete, withPending } = options || {};
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
        sd.itemsScope     = sd.itemsScope || null; // which scope sd.items holds
        sd.itemsEpoch     = Number(sd.itemsEpoch || 0);
        sd.scopeCache     = sd.scopeCache || {};   // scope → last payload (SWR)
        sd.cacheEpoch     = Number(sd.cacheEpoch || 0);
        sd.stats          = sd.stats  || {};
        sd.queue          = [];
        sd.queuePos       = 0;
        sd.requeueMap     = {};
        sd.completedWordIds = new Set();
        sd.doneCount      = 0;
        sd.queueInitialLen= 0;
        sd.result         = null;
        sd.loadingPromise = sd.loadingPromise || null;
        sd.submitSeq      = Number(sd.submitSeq || 0);
        sd.nextHintTimer  = sd.nextHintTimer || null;
        sd._drillReady    = true;
      }
      return sd;
    }

    const root     = () => $("spellingPracticeCard");
    const sideList = () => $("spellingDrillList");
    const NEXT_HINT_DELAY_MS = 4000;

    function currentWord() {
      const s = S();
      return s.queue[s.queuePos] || null;
    }

    function clearNextHintTimer() {
      const s = S();
      if (s.nextHintTimer) {
        window.clearTimeout(s.nextHintTimer);
        s.nextHintTimer = null;
      }
    }

    function scheduleNextHintReveal(renderKey, seq) {
      clearNextHintTimer();
      const s = S();
      s.nextHintTimer = window.setTimeout(() => {
        const currentResult = S().result;
        if (seq !== S().submitSeq || !currentResult || wordRenderKey(currentWord()) !== renderKey) return;
        currentResult._nextHintVisible = true;
        render();
      }, NEXT_HINT_DELAY_MS);
    }

    // ─── TTS ─────────────────────────────────────────────────────────
    // Main path: server-side VolcEngine mp3 via /api/tts, prefetched per word.
    // Browser speechSynthesis stays only as a fallback for provider errors.
    const SERVER_TTS_VOICE = "en_female_sarah";
    const SERVER_TTS_ROLE = "model";
    const serverTts = {
      cache: new Map(),
      activeKey: "",
      activeAudio: null,
    };

    const speech = {
      token: 0,
      voice: null,
      warmed: false,
      primed: false,
      primedText: "",
      preparedText: "",
      suppressCancelErr: false,
    };

    function speechSupported() {
      return typeof window !== "undefined"
        && !!window.speechSynthesis
        && typeof window.SpeechSynthesisUtterance !== "undefined";
    }

    function pickEnglishVoice() {
      const synth = window.speechSynthesis;
      const voices = typeof synth?.getVoices === "function" ? synth.getVoices() : [];
      if (!voices.length) return null;
      const english = voices.filter((v) => /^en([-_]|$)/i.test(String(v.lang || "")));
      const local = english.filter((v) => v.localService);
      const findNamed = (list, names) => names
        .map((name) => list.find((v) => String(v.name || "").toLowerCase().includes(name.toLowerCase())))
        .find(Boolean);
      const preferredRemote = [
        "Google US English", "Google UK English Female", "Google UK English Male", "Google English",
      ];
      const localFallback = [
        "Microsoft Jenny", "Microsoft Aria", "Microsoft Sonia",
        "Samantha", "Alex", "Karen", "Daniel",
      ];
      return findNamed(english, preferredRemote)
        || english.find((v) => v.default)
        || findNamed(local, localFallback)
        || local.find((v) => v.default)
        || local[0]
        || english[0]
        || null;
    }

    function warmSpeech() {
      if (!speechSupported() || speech.warmed) return;
      speech.warmed = true;
      speech.voice = pickEnglishVoice();
      // First getVoices() can be empty until the engine loads; refresh on the event.
      if (!speech.voice && typeof window.speechSynthesis.addEventListener === "function") {
        const onVoices = () => {
          speech.voice = pickEnglishVoice();
          if (speech.voice) window.speechSynthesis.removeEventListener("voiceschanged", onVoices);
        };
        window.speechSynthesis.addEventListener("voiceschanged", onVoices);
      }
    }

    function speechTextForWord(word) {
      return String(word?.correct_spelling || word?.normalized || "").trim();
    }

    function serverTtsCacheKey(text) {
      const word = String(text || "").trim().toLowerCase();
      const safe = word.replace(/[^a-z0-9_.-]+/g, "_").replace(/^_+|_+$/g, "");
      return `spelling_${safe || "word"}`;
    }

    function makeAudio(url) {
      const AudioCtor = window.Audio || (typeof Audio !== "undefined" ? Audio : null);
      if (!AudioCtor || !url) return null;
      const audio = new AudioCtor(url);
      audio.preload = "auto";
      try { audio.load?.(); } catch (_e) { /* ignore */ }
      return audio;
    }

    function prefetchServerTts(text) {
      const value = String(text || "").trim();
      if (!value) return null;
      const cacheKey = serverTtsCacheKey(value);
      serverTts.activeKey = cacheKey;
      const existing = serverTts.cache.get(cacheKey);
      if (existing && (existing.status === "ready" || existing.status === "pending")) return existing;
      const entry = {
        status: "pending",
        text: value,
        cacheKey,
        audioUrl: "",
        audio: null,
        promise: null,
      };
      serverTts.cache.set(cacheKey, entry);
      entry.promise = api("/api/tts", {
        text: value,
        role: SERVER_TTS_ROLE,
        voice: SERVER_TTS_VOICE,
        cache_key: cacheKey,
        server_fallback: true,
      }).then((payload) => {
        const audioUrl = String(payload?.audio_url || "");
        if (!audioUrl) {
          entry.status = "fallback";
          entry.error = payload?.message || payload?.error || "server tts unavailable";
          return entry;
        }
        entry.audioUrl = audioUrl;
        entry.audio = makeAudio(audioUrl);
        entry.status = entry.audio ? "ready" : "fallback";
        return entry;
      }).catch((err) => {
        entry.status = "failed";
        entry.error = err;
        return entry;
      });
      return entry;
    }

    function playServerTts(text) {
      const value = String(text || "").trim();
      if (!value) return false;
      const cacheKey = serverTtsCacheKey(value);
      const entry = serverTts.cache.get(cacheKey);
      if (!entry || entry.status !== "ready" || !entry.audio) {
        prefetchServerTts(value);
        return false;
      }
      try {
        if (serverTts.activeAudio && serverTts.activeAudio !== entry.audio) {
          serverTts.activeAudio.pause?.();
        }
        serverTts.activeAudio = entry.audio;
        entry.audio.currentTime = 0;
        const playPromise = entry.audio.play?.();
        if (playPromise && typeof playPromise.catch === "function") {
          playPromise.catch(() => browserSpeakWord(value));
        }
        return true;
      } catch (_e) {
        return false;
      }
    }

    function prepareSpeechForWord(word) {
      const text = speechTextForWord(word);
      prefetchServerTts(text);
      if (!speechSupported()) return;
      warmSpeech();
      speech.preparedText = text;
      if (!speech.voice) speech.voice = pickEnglishVoice();
    }

    // Warm the audio engine itself (not just the voice list) with a silent
    // utterance for the current word. Gated on a real user gesture because
    // browsers may block speechSynthesis before one.
    function primeSpeech(text) {
      if (!speechSupported()) return;
      const value = String(text || speech.preparedText || "").trim();
      const primeText = value || " ";
      if (speech.primed && speech.primedText === primeText) return;
      speech.primed = true;
      speech.primedText = primeText;
      try {
        const synth = window.speechSynthesis;
        synth.resume?.();
        if (!speech.voice) speech.voice = pickEnglishVoice();
        const warm = new SpeechSynthesisUtterance(primeText);
        warm.volume = 0;
        warm.rate = 2;
        if (speech.voice) warm.voice = speech.voice;
        synth.speak(warm);
      } catch (_e) { /* ignore */ }
    }

    function shouldPrimeSpeechFromKey(e) {
      if (!e || e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return false;
      return String(e.key || "").length === 1;
    }

    function browserSpeakWord(text) {
      const value = String(text || "").trim();
      if (!value || !speechSupported()) return;
      const synth = window.speechSynthesis;
      const token = ++speech.token;
      const needCancel = synth.speaking || synth.pending;
      if (needCancel) { speech.suppressCancelErr = true; synth.cancel(); }
      if (!speech.voice) speech.voice = pickEnglishVoice();
      const utt = new SpeechSynthesisUtterance(value);
      utt.lang = "en-US";
      utt.rate = 0.92;
      if (speech.voice) utt.voice = speech.voice;
      utt.onend = utt.onerror = () => { speech.suppressCancelErr = false; };
      const fire = () => {
        if (token !== speech.token) return;
        try { synth.resume?.(); } catch (_e) { /* ignore */ }
        synth.speak(utt);
      };
      // Speak immediately when idle (0 latency on Enter). Only defer when we had
      // to cancel a previous utterance — that needs a beat to settle in Chrome.
      if (needCancel) window.setTimeout(fire, 50);
      else fire();
    }

    function speakWord(text) {
      if (playServerTts(text)) return;
      browserSpeakWord(text);
    }

    function normalizeTyped(value) {
      return String(value || "").trim().toLowerCase();
    }

    function isReviewCopy(word) {
      return Boolean(word && word._sessionReview === true);
    }

    function shouldCountCorrectAnswer(word) {
      return !isReviewCopy(word) || word?._sessionReviewKind === "final";
    }

    function cloneForSessionReview(word) {
      return {
        ...word,
        _sessionReview: true,
        _sessionReviewKind: "final",
        _reviewCopyId: `${word.word_id}:review:${Date.now()}:${Math.random().toString(16).slice(2)}`,
      };
    }

    function cloneForImmediateRetry(word) {
      return {
        ...word,
        _sessionReview: true,
        _sessionReviewKind: "immediate",
        _reviewCopyId: `${word.word_id}:retry:${Date.now()}:${Math.random().toString(16).slice(2)}`,
      };
    }

    function wordRenderKey(word) {
      return String(word?._reviewCopyId || word?.word_id || "");
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
      // Only trust the live queue-progress count once the queue is actually
      // loaded FOR THE CURRENT SCOPE. During a scope switch the scope flips to
      // "due" immediately while queueInitialLen still holds the previous scope's
      // length (e.g. 32 from "已掌握"), which would flash a wrong red-dot count.
      const useQueue =
        s.phase === "ready" &&
        s.scope === "due" &&
        s.itemsScope === "due" &&
        Number(s.queueInitialLen || 0) > 0;
      const due = useQueue
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
    // In-flight requests keyed by scope so switching scopes can't hand back a
    // promise (and payload) for the wrong scope.
    function cachedPayload(scope) {
      const s = S();
      const entry = s.scopeCache?.[scope];
      if (!entry || Number(entry.epoch) !== Number(s.cacheEpoch)) return null;
      return entry.payload || null;
    }

    function rememberScopePayload(scope, payload, epoch = S().cacheEpoch) {
      const s = S();
      if (Number(epoch) !== Number(s.cacheEpoch)) return;
      s.scopeCache = s.scopeCache || {};
      s.scopeCache[scope] = { payload, epoch };
    }

    function invalidateWordDataCache() {
      const s = S();
      s.cacheEpoch = Number(s.cacheEpoch || 0) + 1;
      s.scopeCache = {};
      s._loading = {};
      s.itemsEpoch = s.cacheEpoch;
    }

    async function fetchWords(scope, { force = false } = {}) {
      const s = S();
      s._loading = s._loading || {};
      if (force) delete s._loading[scope];
      if (!s._loading[scope]) {
        s._loading[scope] = api(`/api/writing/spelling-words?scope=${encodeURIComponent(scope)}`)
          .finally(() => { delete s._loading[scope]; });
      }
      return s._loading[scope];
    }

    // Warm the other scopes in the background so the first switch to them is
    // instant. Doesn't touch s.scope (uses a raw request, not fetchWords).
    function prefetchOtherScopes() {
      const s = S();
      s.scopeCache = s.scopeCache || {};
      const epoch = Number(s.cacheEpoch || 0);
      const others = ["due", "active", "mastered"].filter(
        (sc) => sc !== s.scope && !cachedPayload(sc)
      );
      if (!others.length) return;
      const run = () => others.forEach((sc) => {
        api(`/api/writing/spelling-words?scope=${encodeURIComponent(sc)}`)
          .then((p) => { rememberScopePayload(sc, p, epoch); })
          .catch(() => {});
      });
      if (window.requestIdleCallback) window.requestIdleCallback(run, { timeout: 2000 });
      else setTimeout(run, 500);
    }

    function ingest(payload, { resetQueue = true } = {}) {
      const s = S();
      s.items = payload.items || [];
      s.itemsScope = s.scope;
      s.itemsEpoch = s.cacheEpoch;
      s.stats = payload.stats || {};
      s.phase = "ready";
      if (resetQueue) {
        clearNextHintTimer();
        s.queue          = [...s.items];
        s.queuePos       = 0;
        s.requeueMap     = {};
        s.completedWordIds = new Set();
        s.doneCount      = 0;
        s.queueInitialLen= s.items.length;
        s.result         = null;
      }
    }

    function draftInputValue() {
      const input = $("spellingTypedInput");
      return input ? String(input.value || "") : "";
    }

    async function load({ force = false, resetQueue = true, _pivoted = false } = {}) {
      const s  = S();
      // Pin the scope + a monotonic sequence for THIS load. Rapid tab switches
      // fire overlapping loads; a stale one must not paint over the newest view
      // ("快速切换会乱界面"). stale() is true once a newer load() has started.
      const scope = s.scope;
      const seq   = (s._loadSeq = (s._loadSeq || 0) + 1);
      const epoch = Number(s.cacheEpoch || 0);
      const stale = () => seq !== s._loadSeq;

      s.scopeCache = s.scopeCache || {};
      const cached = cachedPayload(scope);
      // Paint instantly when we have data for THIS scope (a per-scope cache, or
      // s.items already holding this scope), then revalidate behind it.
      const sameScopeItems =
        s.itemsScope === scope &&
        Number(s.itemsEpoch) === Number(s.cacheEpoch) &&
        Array.isArray(s.items) &&
        s.items.length > 0;
      const canRenderCached = !force && resetQueue && Boolean(cached || sameScopeItems);

      if (canRenderCached) {
        ingest(cached || { items: s.items, stats: s.stats || {} }, { resetQueue: true });
        render();
        setStatus("正在同步最新错词本…");
      } else {
        s.phase  = "loading";
        render();
      }
      try {
        const payload = await fetchWords(scope, { force });
        if (stale() || Number(epoch) !== Number(s.cacheEpoch)) return;
        rememberScopePayload(scope, payload, epoch);
        // If the user already started answering in the cached view, don't yank
        // the queue out from under them — refresh stats/items only.
        const progressed = canRenderCached &&
          (Number(s.doneCount || 0) > 0 || Number(s.queuePos || 0) > 0 || s.result || draftInputValue());
        ingest(payload, { resetQueue: resetQueue && !progressed });
        setStatus("");
        prefetchOtherScopes();
      } catch (err) {
        if (stale()) return;
        s.phase = "ready";
        setStatus(err.message || String(err), true);
      }
      if (stale()) return;
      render();
    }

    // ─── Render helpers ───────────────────────────────────────────────
    // buildPromptHtml / buildInputHtml are called both in full rebuild
    // and in partial (in-place) updates so the card doesn't re-animate.

    // ECDICT marks a sense's field with a bracketed code like "[经]". Render
    // those as compact English pill tags (matching the 划词 dictionary card) so
    // the spelling gloss reads clearly instead of showing a bare "[经]".
    const GLOSS_DOMAIN_TAGS = {
      "经": { en: "Economics", icon: "📈" },
      "计": { en: "Computing", icon: "💻" },
      "医": { en: "Medicine", icon: "⚕️" },
      "法": { en: "Law", icon: "⚖️" },
      "化": { en: "Chemistry", icon: "🧪" },
      "数": { en: "Math", icon: "📐" },
      "军": { en: "Military", icon: "🎖️" },
      "语": { en: "Linguistics", icon: "🗣️" },
      "物": { en: "Physics", icon: "⚛️" },
      "植": { en: "Botany", icon: "🌿" },
      "动": { en: "Zoology", icon: "🐾" },
      "天": { en: "Astronomy", icon: "🔭" },
      "地": { en: "Geography", icon: "🌍" },
      "生": { en: "Biology", icon: "🧬" },
      "电": { en: "Electrical", icon: "⚡" },
      "机": { en: "Mechanics", icon: "⚙️" },
      "建": { en: "Architecture", icon: "🏛️" },
      "商": { en: "Business", icon: "💼" },
      "农": { en: "Agriculture", icon: "🌾" },
      "音": { en: "Music", icon: "🎵" },
      "体": { en: "Sports", icon: "⚽" },
      "宗": { en: "Religion", icon: "⛪" },
      "心": { en: "Psychology", icon: "🧠" },
      "解": { en: "Anatomy", icon: "🦴" },
      "药": { en: "Pharmacy", icon: "💊" },
      "史": { en: "History", icon: "📜" },
      "哲": { en: "Philosophy", icon: "💭" },
      "政": { en: "Politics", icon: "🏛️" },
      "航": { en: "Aviation", icon: "✈️" },
      "海": { en: "Nautical", icon: "⚓" },
      "矿": { en: "Mining", icon: "⛏️" },
      "林": { en: "Forestry", icon: "🌲" },
      "摄": { en: "Photography", icon: "📷" },
    };
    const GLOSS_DOMAIN_BY_LABEL = Object.fromEntries(
      Object.entries(GLOSS_DOMAIN_TAGS).map(([code, tag]) => [String(tag.en).toLowerCase(), code])
    );

    // Prefer the shared renderer (window.IELTSDictTags, exposed by corpus-takeaway)
    // so both surfaces stay identical; fall back to the local map if unavailable.
    function escapeGlossWithTags(text) {
      const shared = (typeof window !== "undefined" && window.IELTSDictTags)
        ? window.IELTSDictTags.escapeHtmlWithDomainTags
        : null;
      if (typeof shared === "function") return shared(text);
      let html = escapeHtml(String(text || "")).replace(/\[([^\]]{1,4})\]\s*/g, (_m, code) => {
        const tag = GLOSS_DOMAIN_TAGS[code];
        const label = String(tag ? tag.en : code).toLowerCase();
        const icon = tag ? tag.icon : "🏷️";
        return `<span class="dict-domain-tag" data-dict-domain-code="${escapeHtml(code)}" data-dict-domain-label="${escapeHtml(label)}" contenteditable="false"><span class="dict-domain-tag-icon" aria-hidden="true">${escapeHtml(icon)}</span><span class="dict-domain-tag-text">${escapeHtml(label)}</span></span><span class="dict-domain-tag-colon" contenteditable="false">&#65306; </span>`;
      });
      html = html.replace(/\b([A-Za-z][A-Za-z ]{1,28})\s*[:：]\s*/g, (match, label) => {
        const code = GLOSS_DOMAIN_BY_LABEL[String(label || "").trim().toLowerCase()];
        if (!code) return match;
        const tag = GLOSS_DOMAIN_TAGS[code];
        const lower = String(tag.en).toLowerCase();
        return `<span class="dict-domain-tag" data-dict-domain-code="${escapeHtml(code)}" data-dict-domain-label="${escapeHtml(lower)}" contenteditable="false"><span class="dict-domain-tag-icon" aria-hidden="true">${escapeHtml(tag.icon)}</span><span class="dict-domain-tag-text">${escapeHtml(lower)}</span></span><span class="dict-domain-tag-colon" contenteditable="false">&#65306; </span>`;
      });
      return html;
    }

    // Split chinese_gloss on "；" (or ";") — first part is the Chinese meaning,
    // everything after is a spelling note (e.g. "high 的比较级需要保留 h 后的结构").
    function splitGloss(gloss) {
      const raw  = gloss || "";
      const looksLikeSense = (value) => {
        const text = String(value || "").trim();
        if (!text) return false;
        if (/^\[[^\]]{1,4}\]/.test(text)) return true;
        if (/^(n|v|vt|vi|adj|adv|prep|pron|conj|abbr|num|interj)\./i.test(text)) return true;
        return /^(economics|computing|medicine|law|chemistry|math|military|linguistics|physics|botany|zoology|astronomy|geography|biology|electrical|mechanics|architecture|business|agriculture|music|sports|religion|psychology|anatomy|pharmacy|history|philosophy|politics|aviation|nautical|mining|forestry|photography)\s*[:：]/i.test(text);
      };
      const parts = raw.split(/[；;]/).map((part) => part.trim()).filter(Boolean);
      if (parts.length > 1 && parts.some(looksLikeSense) && parts.slice(1).some(looksLikeSense)) {
        return { chinese: parts.join("\n"), note: "" };
      }
      const idx  = raw.search(/[；;]/);
      if (idx < 0) return { chinese: raw, note: "" };
      return { chinese: raw.slice(0, idx).trim(), note: raw.slice(idx + 1).trim() };
    }

    function glossDisplayParts(text) {
      return String(text || "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
    }

    function glossFontSize(lines) {
      if (!Array.isArray(lines) || lines.length <= 1) return "";
      const maxLineChars = Math.max(...lines.map((line) => Array.from(line).length));
      let raw = 48 - Math.max(0, lines.length - 1) * 7 - Math.max(0, maxLineChars - 18) * 0.45;
      // Two-line glosses still read too large — shrink only that case, leave the
      // single-line and 3+ line sizes untouched.
      if (lines.length === 2) raw -= 6;
      return Math.max(22, Math.min(48, Math.round(raw)));
    }

    function glossHtml(text, fallback) {
      const value = String(text || fallback || "");
      const lines = glossDisplayParts(value);
      const displayLines = lines.length ? lines : [value];
      const multiline = displayLines.length > 1;
      const size = glossFontSize(displayLines);
      const classes = ["nr-gloss", text ? "" : "is-fallback", multiline ? "is-multiline" : ""]
        .filter(Boolean)
        .join(" ");
      const style = size ? ` style="--nr-gloss-size:${size}px"` : "";
      const body = multiline
        ? displayLines.map((line) => `<span class="nr-gloss-line">${escapeGlossWithTags(line)}</span>`).join("")
        : escapeGlossWithTags(displayLines[0] || "");
      return `<p class="${classes}"${style}>${body}</p>`;
    }

    function buildPromptHtml(word, s) {
      const { chinese, note: _note } = splitGloss(word.chinese_gloss);
      const letterCount = String(word.correct_spelling || "").replace(/[^A-Za-z]/g, "").length;
      const fallback    = letterCount > 0 ? `回忆这个 ${letterCount} 字母的词` : "回忆这个词";
      // Only show the Chinese meaning; the spelling note is revealed after Enter.
      // Manually-added words (from the 划词 popup) were never misspelled, so they
      // carry no wrong_forms — hide the "曾误作" pill rather than show a bare "—".
      const forms = Array.isArray(word?.wrong_forms) ? word.wrong_forms.filter(Boolean) : [];
      const wrongPill = forms.length
        ? `<div class="nr-wrong-pill">
          <span class="nr-wrong-tag">曾误作</span>
          <span class="nr-wrong-text">${escapeHtml(forms.join(" · "))}</span>
        </div>`
        : "";
      return `
        ${glossHtml(chinese, fallback)}
        ${wrongPill}
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
      const nextHintVisible = Boolean(result._nextHintVisible);
      const nextHintHtml = `<p class="nr-next-hint ${nextHintVisible ? "is-visible" : ""}" aria-live="polite" aria-hidden="${nextHintVisible ? "false" : "true"}">按 Enter 进入下一题</p>`;

      // ── State B: correct — show green diff, wait for Enter ──
      if (result.correct) return `
        <div class="nr-slot nr-result-slot is-correct">
          ${noteHtml}
          <div class="nr-inline-answer" aria-live="polite">
            <p class="nr-answer-line">${letterDiff(result._typed || "", correctSpell)}</p>
          </div>
          <p class="nr-inline-correct nr-inline-correct--placeholder" aria-hidden="true">
            <span class="nr-answer-word" data-label="正解">${escapeHtml(correctSpell)}</span>
          </p>
          ${nextHintHtml}
        </div>
      `;

      return `
        <div class="nr-slot nr-result-slot is-wrong">
          ${noteHtml}
          <div class="nr-inline-answer" aria-live="polite">
            <p class="nr-answer-line">${letterDiff(result._typed || "", correctSpell)}</p>
          </div>
          <p class="nr-inline-correct">
            <span class="nr-answer-word" data-label="正解">${escapeHtml(correctSpell)}</span>
          </p>
          ${nextHintHtml}
        </div>
      `;
    }

    function focusInputArea(result, s) {
      if (!result) {
        $("spellingTypedInput")?.focus();
      } else {
        const card = root();
        card?.setAttribute?.("tabindex", "-1");
        card?.focus?.({ preventScroll: true });
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
      // Anything that isn't a settled "ready" state shows the spinner — never the
      // empty card. Otherwise the initial "idle" phase flashes "错词本空着" for a
      // frame before the words arrive ("进入为空，然后突然跳出来单词").
      if (s.phase !== "ready")   return renderLoading();
      if (!s.queue.length)       return renderEmpty();
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
          <button type="button" class="nr-card-tool nr-empty-add" data-spelling-card-add
            aria-label="添加单词" title="添加单词">
            <svg viewBox="0 0 24 24" aria-hidden="true" width="15" height="15">
              <path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M12 5v14M5 12h14"/>
            </svg>
          </button>
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
      prepareSpeechForWord(word);

      const result = s.result;
      const pct    = Math.round((s.doneCount / Math.max(s.queueInitialLen, 1)) * 100);
      const reqs   = s.requeueMap[word.word_id] || 0;
      const progressTextHtml = `<b>${s.doneCount}</b><span>/${s.queueInitialLen}</span>${reqs > 0 ? ` <em class="nr-requeue">·重 ${reqs}</em>` : ""}`;

      // ── Partial in-place update (same word, state changed) ──────────
      // Avoids card animation replay and lets progress-fill CSS transition work.
      const existingCard = root().querySelector(`[data-drill-word]`);
      const sameWord = existingCard &&
        existingCard.dataset.drillWord === wordRenderKey(word);

      if (sameWord) {
        // Update progress bar (CSS transition animates width smoothly)
        const fill = existingCard.querySelector(".nr-progress-fill");
        const txt  = existingCard.querySelector(".nr-progress-text");
        if (fill) fill.style.width = pct + "%";
        if (txt)  txt.innerHTML = progressTextHtml;

        // Update only the input/answer area
        const bodyEl = existingCard.querySelector(".nr-drill-body");
        if (bodyEl) {
          if (!result && draftInputValue()) return;
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
        <div class="nr-card" data-drill-card data-drill-word="${escapeHtml(wordRenderKey(word))}">
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

          <div class="nr-card-tools">
            <button type="button" class="nr-card-tool" data-spelling-card-add
              aria-label="添加单词" title="添加单词（查词典后加入拼写训练）">
              <svg viewBox="0 0 24 24" aria-hidden="true" width="15" height="15">
                <path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M12 5v14M5 12h14"/>
              </svg>
            </button>
            <button type="button" class="nr-card-tool is-danger" data-spelling-card-del
              aria-label="移除此单词" title="移除此单词（拼写训练不再出现）">
              <svg viewBox="0 0 24 24" aria-hidden="true" width="15" height="15">
                <path fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"
                  d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>
              </svg>
            </button>
          </div>

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
        if (due.length)      groups.push({ title: "\u5f85\u590d\u4e60", items: due });
        if (active.length)   groups.push({ title: "\u5b66\u4e2d",   items: active });
        if (mastered.length) groups.push({ title: "\u5df2\u638c\u63e1", items: mastered });
      }

      const groupHtml = groups.length ? groups.map((g) => `
        <section class="nr-lib-group">
          <h4 class="nr-lib-group-title"><span>${escapeHtml(g.title)}</span><em>${g.items.length}</em></h4>
          <ul class="nr-lib-list">
            ${g.items.map((w) => {
              const stage = Number(w.review_stage || 0);
              const isMastered = w.status === "mastered";
              return `
                <li class="nr-lib-item" data-spelling-word="${escapeHtml(w.word_id)}">
                  <div class="nr-lib-main">
                    <strong class="nr-lib-word">${escapeHtml(w.correct_spelling)}</strong>
                    <span class="nr-lib-gloss">${escapeGlossWithTags(w.chinese_gloss || "-")}</span>
                    ${(Array.isArray(w.wrong_forms) ? w.wrong_forms.filter(Boolean) : []).length
                      ? `<span class="nr-lib-wrong">\u8bef\uff1a${escapeHtml(wrongFormsText(w))}</span>`
                      : ""}
                  </div>
                  <div class="nr-lib-side">
                    <span class="nr-lib-stage">\u9636 ${stage}</span>
                    ${isMastered
                      ? `<span class="nr-lib-mastered">\u5df2\u638c\u63e1</span>`
                      : `<button class="nr-lib-act nr-lib-master-btn" data-spelling-master="${escapeHtml(w.word_id)}" title="\u6807\u4e3a\u5df2\u638c\u63e1">\u6807\u4e3a\u5df2\u638c\u63e1</button>`}
                    <button class="nr-lib-act is-danger" data-spelling-delete="${escapeHtml(w.word_id)}" title="\u79fb\u51fa\u9519\u8bcd\u672c">\u5220\u9664</button>
                  </div>
                </li>
              `;
            }).join("")}
          </ul>
        </section>
      `).join("") : `<p class="nr-lib-empty">\u8fd9\u4e2a\u8303\u56f4\u91cc\u8fd8\u6ca1\u6709\u8bcd\u3002</p>`;

      sideList().innerHTML = `
        <header class="nr-lib-head">
          <button class="nr-lib-back" data-close-library>
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M15 18l-6-6 6-6"/>
            </svg>
            \u56de\u5230\u7ec3\u4e60
          </button>
          <span class="nr-lib-title">\u9519\u8bcd\u672c \u00b7 ${escapeHtml(
            ({ due: "\u4eca\u65e5\u5f85\u590d\u4e60", active: "\u5168\u90e8\u5b66\u4e2d", mastered: "\u5df2\u638c\u63e1" })[s.scope] || s.scope
          )}</span>
        </header>
        <div class="nr-lib-body">
          ${groupHtml}
        </div>
      `;
    }

    // ─── Actions ─────────────────────────────────────────────────────
    function markWordCompleted(word) {
      const s = S();
      const id = String(word?.word_id || "");
      if (!id || s.completedWordIds?.has(id)) return;
      s.completedWordIds.add(id);
      s.doneCount += 1;
    }

    function gotoNext() {
      const s = S();
      clearNextHintTimer();
      s.queuePos    += 1;
      s.result       = null;
      render();
    }

    function scheduleWrongWordReview(word) {
      const s = S();
      if (!word || s.result?._queuedForReview) return;
      s.queue.splice(s.queuePos + 1, 0, cloneForImmediateRetry(word));
      const hasFinalReview = s.queue.some((item, index) =>
        index > s.queuePos &&
        String(item?.word_id || "") === String(word.word_id || "") &&
        item?._sessionReviewKind === "final"
      );
      if (!hasFinalReview) {
        s.queue.push(cloneForSessionReview(word));
      }
      if (s.result) s.result._queuedForReview = true;
    }

    function localAttemptResult(word, typed, correct) {
      const currentStreak = Number(word?.current_streak || 0);
      return {
        correct,
        correct_spelling: correct ? "" : (word?.correct_spelling || ""),
        current_streak: correct ? currentStreak + 1 : 0,
        review_stage: word?.review_stage,
        status: word?.status,
        explanation: correct ? "" : word?.explanation,
        next_due_human: word?.next_due_human || "",
        _typed: typed,
      };
    }

    function isBlankAttempt(typed) {
      return !String(typed || "").trim();
    }

    function isTypingContinuationKey(e) {
      if (!e || e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return false;
      return /^[A-Za-z]$/.test(String(e.key || ""));
    }

    function continueWrongResultWithTypedKey(e) {
      const s = S();
      if (!s.result || s.result.correct || !isTypingContinuationKey(e)) return false;
      e.preventDefault();
      gotoNext();
      const input = $("spellingTypedInput");
      if (!input) return true;
      input.value = String(e.key || "");
      input.focus();
      input.dispatchEvent(new Event("input", { bubbles: true }));
      return true;
    }

    function mergeAttemptResultIntoWord(word, result, { countAttempt = false } = {}) {
      if (!word || !result) return;
      Object.assign(word, {
        current_streak: result.current_streak ?? word.current_streak,
        review_stage:   result.review_stage ?? word.review_stage,
        status:         result.status ?? word.status,
      });
      if (countAttempt) {
        word.attempt_count = Number(word.attempt_count || 0) + 1;
        word.correct_count = Number(word.correct_count || 0) + (result.correct ? 1 : 0);
      }
      const s = S();
      const iw = s.items.find((w) => w.word_id === word.word_id);
      if (iw) Object.assign(iw, word);
    }

    function applyAttemptResult(word, result, typed, { syncWord = false } = {}) {
      const s = S();
      const stored = { ...result, _typed: typed, _nextHintVisible: false };
      s.result = stored;
      clearNextHintTimer();
      // Read the answer aloud the moment it's revealed (right or wrong).
      speakWord(word?.correct_spelling || word?.normalized || "");
      if (syncWord) {
        invalidateWordDataCache();
        mergeAttemptResultIntoWord(word, result, { countAttempt: true });
      }
      if (result.correct) {
        if (shouldCountCorrectAnswer(word)) {
          markWordCompleted(word);
        }
      } else {
        s.requeueMap[word.word_id] = (s.requeueMap[word.word_id] || 0) + 1;
        scheduleWrongWordReview(word);
      }
      render();
      scheduleNextHintReveal(wordRenderKey(word), s.submitSeq);
    }

    function syncServerAttemptResult(word, localResult, typed, seq, renderKey) {
      api(
        `/api/writing/spelling-words/${encodeURIComponent(word.word_id)}/attempt`,
        { typed }
      ).then((serverResult) => {
        const s = S();
        const queuedFlag = s.result?._queuedForReview;
        const nextHintVisible = Boolean(s.result?._nextHintVisible);
        invalidateWordDataCache();
        mergeAttemptResultIntoWord(word, serverResult, { countAttempt: false });
        if (seq !== s.submitSeq) return;
        const stillSameCard = wordRenderKey(currentWord()) === renderKey;
        if (!stillSameCard || !s.result || s.result._typed !== typed) return;
        s.result = {
          ...s.result,
          ...serverResult,
          _typed: typed,
          _nextHintVisible: nextHintVisible || Boolean(s.result._nextHintVisible),
          _queuedForReview: queuedFlag || s.result._queuedForReview,
        };
        render();
      }).catch((_err) => {
        if (seq === S().submitSeq && !isBlankAttempt(typed)) {
          setStatus("同步失败，本次结果可能未记录。", true);
        }
      });
    }

    async function submitAttempt(e) {
      e?.preventDefault();
      const word  = currentWord();
      const input = $("spellingTypedInput");
      const typed = input?.value || "";
      if (!word) { setStatus("当前没有可练习的单词。", true); return; }
      setStatus("");
      const s = S();
      const reviewCopy = isReviewCopy(word);
      const localCorrect = normalizeTyped(typed) === normalizeTyped(word.correct_spelling || word.normalized || "");
      const result = localAttemptResult(word, typed, localCorrect);
      const seq = ++s.submitSeq;
      const renderKey = wordRenderKey(word);
      applyAttemptResult(word, result, typed, { syncWord: !reviewCopy });
      if (!reviewCopy) {
        syncServerAttemptResult(word, result, typed, seq, renderKey);
      }
      // No auto-advance: user presses Enter again anywhere on the card to continue.
    }

    async function updateWord(wordId, payload) {
      invalidateWordDataCache();
      const result = await api(
        `/api/writing/spelling-words/${encodeURIComponent(wordId)}`,
        payload,
        { method: "PATCH" }
      );
      const s   = S();
      const idx = s.items.findIndex((w) => w.word_id === wordId);
      if (idx >= 0) s.items[idx] = result;
      s.queue = s.queue.map((w) => w.word_id === wordId ? { ...result, _sessionReview: w._sessionReview === true } : w);
      s.result   = null;
      render();
    }

    function deleteWord(wordId) {
      const s = S();
      invalidateWordDataCache();
      // Optimistic: drop it from the UI immediately so the card never lags, then
      // confirm with the server in the background. Roll back on failure.
      const snapshot = { items: s.items, queue: s.queue, queuePos: s.queuePos, doneCount: s.doneCount };
      const wasCompleted = s.completedWordIds?.has(wordId);
      s.items = s.items.filter((w) => w.word_id !== wordId);
      s.queue = s.queue.filter((w) => w.word_id !== wordId);
      s.completedWordIds?.delete(wordId);
      s.doneCount = Math.min(s.doneCount, s.completedWordIds?.size || s.doneCount);
      s.queuePos = Math.min(s.queuePos, Math.max(0, s.queue.length));
      s.result = null;
      render();
      return api(`/api/writing/spelling-words/${encodeURIComponent(wordId)}`, null, { method: "DELETE" })
        .catch((err) => {
          // Restore exactly what we removed and re-render.
          Object.assign(s, snapshot);
          if (wasCompleted) s.completedWordIds?.add(wordId);
          render();
          throw err;
        });
    }

    // Remove the current drill word for good (Delete key or the card's trash
    // button), behind a confirm. Shared so both entry points behave the same.
    function confirmRemoveCurrentWord() {
      const word = currentWord();
      if (!word) return;
      const run = () => deleteWord(word.word_id).catch((err) => setStatus(err.message, true));
      if (typeof showConfirmDelete === "function")
        showConfirmDelete("移除此单词？以后拼写训练不再出现。", run);
      else if (window.confirm("移除此单词？以后拼写训练不再出现。")) run();
    }

    // Add-word dialog (card's + button). A centered modal like the takeaway 添加
    // window: type one English word, Enter looks it up in the dictionary and
    // fills 中文, 保存 adds it. Backdrop / Escape closes (no cancel button).
    function normalizeAddWord(value) {
      // Keep only the 原文 — strip pasted markdown markers (**phone** → phone).
      return String(value || "").replace(/[*_`~]/g, "").trim();
    }

    function setAddWordStatus(msg, isError = false) {
      const el = $("spellingAddStatus");
      if (!el) return;
      el.textContent = msg || "";
      el.classList.toggle("is-error", !!isError);
    }

    function renderSpellingAddGlossPreview(text) {
      const preview = $("spellingAddGlossPreview");
      const field = $("spellingAddGlossField");
      const glossEl = $("spellingAddGloss");
      if (!preview) return;
      const raw = String(text ?? glossEl?.value ?? "").trim();
      if (!raw) {
        preview.classList.add("hidden");
        preview.innerHTML = "";
        field?.classList.remove("hidden");
        return;
      }
      const lines = glossDisplayParts(raw);
      preview.innerHTML = lines.length
        ? lines.map((line) => `<span class="dict-sense-line">${escapeGlossWithTags(line)}</span>`).join("")
        : "";
      preview.classList.toggle("hidden", !lines.length);
      field?.classList.toggle("hidden", !!lines.length);
    }

    function resetSpellingAddGlossPreview() {
      if ($("spellingAddGloss")) $("spellingAddGloss").value = "";
      renderSpellingAddGlossPreview("");
    }

    function setAddWordBusy(isBusy) {
      const saveBtn = $("spellingAddSaveBtn");
      if (!saveBtn) return;
      saveBtn.disabled = !!isBusy;
      saveBtn.classList.toggle("is-busy", !!isBusy);
      saveBtn.setAttribute("aria-busy", isBusy ? "true" : "false");
      saveBtn.textContent = isBusy ? "\u6dfb\u52a0\u4e2d" : "\u6dfb\u52a0";
    }

    function openAddWordDialog() {
      const dialog = $("spellingAddDialog");
      if (!dialog) return;
      if ($("spellingAddWord")) { $("spellingAddWord").value = ""; $("spellingAddWord").disabled = false; }
      resetSpellingAddGlossPreview();
      setAddWordBusy(false);
      setAddWordStatus("");
      dialog.classList.remove("hidden");
      setTimeout(() => $("spellingAddWord")?.focus(), 0);
    }

    function closeAddWordDialog() {
      $("spellingAddDialog")?.classList.add("hidden");
    }

    // Enter in the word field → dictionary lookup → fill 中文 (translate-on-enter,
    // same as the takeaway 原文 field).
    async function lookupAddWordGloss() {
      const word = normalizeAddWord($("spellingAddWord")?.value);
      if ($("spellingAddWord")) $("spellingAddWord").value = word;
      if (!word) return;
      if (!/^[A-Za-z][A-Za-z'’-]*$/.test(word)) {
        setAddWordStatus("只能添加单个英文单词。", true);
        return;
      }
      setAddWordStatus("查词中…");
      try {
        const dict = await api(`/api/dictionary/lookup?word=${encodeURIComponent(word)}`);
        const entry = dict && dict.found ? dict.entry : null;
        const senses = entry
          ? (Array.isArray(entry.senses) && entry.senses.length ? entry.senses : (entry.translation ? [entry.translation] : []))
          : [];
        if (senses.length && $("spellingAddGloss")) {
          const text = senses.slice(0, 4).join("\n");
          $("spellingAddGloss").value = text;
          renderSpellingAddGlossPreview(text);
        }
        setAddWordStatus(entry?.phonetic ? `[${entry.phonetic}]` : "");
      } catch (_e) {
        setAddWordStatus("");
      }
    }

    async function submitAddWord() {
      const word = normalizeAddWord($("spellingAddWord")?.value);
      if ($("spellingAddWord")) $("spellingAddWord").value = word;
      if (!word) { setAddWordStatus("\u5148\u8f93\u5165\u4e00\u4e2a\u82f1\u6587\u5355\u8bcd\u3002", true); return; }
      // Single English word only.
      if (!/^[A-Za-z][A-Za-z'\u2019]*$/.test(word)) {
        setAddWordStatus("\u53ea\u80fd\u6dfb\u52a0\u5355\u4e2a\u82f1\u6587\u5355\u8bcd\u3002", true);
        return;
      }
      let gloss = String($("spellingAddGloss")?.value || "").trim();
      if ($("spellingAddSaveBtn")?.disabled) return;
      setAddWordBusy(true);
      setAddWordStatus("\u6b63\u5728\u6dfb\u52a0...");
      setStatus(`\u6b63\u5728\u6dfb\u52a0\uff1a${word}`);
      closeAddWordDialog();
      try {
        // If the learner saved straight away without pressing Enter, look up in
        // the background. Closing the dialog first keeps the click response
        // immediate; the page status carries the loading feedback.
        if (!gloss) {
          try {
            const dict = await api(`/api/dictionary/lookup?word=${encodeURIComponent(word)}`);
            const entry = dict && dict.found ? dict.entry : null;
            const senses = entry
              ? (Array.isArray(entry.senses) && entry.senses.length ? entry.senses : (entry.translation ? [entry.translation] : []))
              : [];
            gloss = senses.slice(0, 4).join("\uff1b");
          } catch (_e) { /* dictionary optional; backend fills a local gloss */ }
        }
        const res = await api("/api/writing/spelling-words/add", { word, chinese_gloss: gloss });
        const saved = res?.word;
        const s = S();
        if (saved && saved.word_id) {
          invalidateWordDataCache();
          const idx = s.items.findIndex((w) => w.word_id === saved.word_id);
          if (idx >= 0) s.items[idx] = saved;
          else s.items.unshift(saved);
        }
        setStatus(`\u5df2\u52a0\u5165\uff1a${word}`);
        if (s.view === "library") render();
      } catch (err) {
        setStatus(err.message || "\u52a0\u5165\u5931\u8d25");
      } finally {
        setAddWordBusy(false);
      }
    }

    function bindSpellingDrillEvents() {
      warmSpeech();
      // Scope tabs (header bar)
      document.querySelectorAll("[data-spelling-scope]").forEach((btn) => {
        btn.addEventListener("click", () => {
          S().scope = btn.dataset.spellingScope || "due";
          S().view  = "drill";
          load({ resetQueue: true });
        });
      });

      // Card: form submit — the main attempt form.
      root()?.addEventListener("submit", (e) => {
        if (e.target?.id === "spellingAttemptForm") submitAttempt(e);
      });

      // Add-word dialog: 保存, Enter-to-lookup, backdrop / Escape close.
      $("spellingAddSaveBtn")?.addEventListener("click", () => submitAddWord());
      $("spellingAddSpeakBtn")?.addEventListener("click", () => {
        const word = normalizeAddWord($("spellingAddWord")?.value);
        if (word) speakWord(word);
      });
      $("spellingAddWord")?.addEventListener("keydown", (e) => {
        if (e.key !== "Enter" || e.isComposing) return;
        e.preventDefault();
        lookupAddWordGloss();
      });
      $("spellingAddWord")?.addEventListener("input", () => {
        resetSpellingAddGlossPreview();
        setAddWordStatus("");
      });
      $("spellingAddDialog")?.addEventListener("pointerdown", (e) => {
        if (e.target === $("spellingAddDialog")) closeAddWordDialog();
      });
      $("spellingAddDialog")?.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeAddWordDialog();
      });


      // Card: button clicks
      root()?.addEventListener("click", (e) => {
        const t = e.target;
        const ansWord = t.closest(".nr-answer-word");
        if (ansWord) { speakWord(ansWord.textContent); return; }
        if (t.closest("[data-spelling-card-add]")) { openAddWordDialog(); return; }
        if (t.closest("[data-spelling-card-del]")) { confirmRemoveCurrentWord(); return; }
        if (t.closest("[data-open-library]"))      { S().view = "library"; render(); return; }
        if (t.closest("[data-spelling-reload]"))   { load({ force: true, resetQueue: true }); return; }
        const scopeBtn = t.closest("[data-spelling-scope]");
        if (scopeBtn) {
          S().scope = scopeBtn.dataset.spellingScope;
          load({ resetQueue: true });
          return;
        }
      });

      // Press Delete on the current word to drop it for good (never drilled again).
      // Don't hijack Delete while the learner is mid-edit with text in the box —
      // only when the input is empty or the answer is already revealed.
      root()?.addEventListener("keydown", (e) => {
        if (continueWrongResultWithTypedKey(e)) return;
        if (e.key === "Enter" && !e.isComposing && S().result) {
          e.preventDefault();
          gotoNext();
          return;
        }
        // Any keystroke is a user gesture — warm the speech engine once so the
        // answer speaks with ~0 latency by the time Enter reveals it.
        if (shouldPrimeSpeechFromKey(e)) primeSpeech(speechTextForWord(currentWord()));
        if (e.key !== "Delete") return;
        const s = S();
        if (s.view !== "drill") return;
        const word = currentWord();
        if (!word) return;
        const input = $("spellingTypedInput");
        const editingText = input && document.activeElement === input && input.value.length > 0;
        if (editingText) return;
        e.preventDefault();
        confirmRemoveCurrentWord();
      });

      root()?.addEventListener("input", (e) => {
        if (e.target?.id !== "spellingTypedInput") return;
        const text = speechTextForWord(currentWord());
        prefetchServerTts(text);
        primeSpeech(text);
      });

      // Library: back + actions
      sideList()?.addEventListener("click", (e) => {
        const t = e.target;
        if (t.closest("[data-close-library]")) { S().view = "drill"; render(); return; }
        const m = t.closest("[data-spelling-master]");
        if (m) {
          const run = () => updateWord(m.dataset.spellingMaster, { action: "master" });
          (withPending ? withPending(m, run, { busyText: "..." }) : run())
            .catch((err) => setStatus(err.message, true));
          return;
        }
        const d = t.closest("[data-spelling-delete]");
        if (d) {
          const id  = d.dataset.spellingDelete;
          const run = () => {
            const task = () => deleteWord(id);
            return (withPending ? withPending(d, task, { busyText: "..." }) : task())
              .catch((err) => setStatus(err.message, true));
          };
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
