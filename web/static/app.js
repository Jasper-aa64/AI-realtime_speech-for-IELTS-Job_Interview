const state = {
  view: "home",
  viewHistory: [],
  routeApplying: false,
  status: "idle",
  attempt: null,
  currentTurn: null,
  timer: null,
  timerRemaining: 0,
  timerTotal: 1,
  mediaRecorder: null,
  mediaStream: null,
  audioChunks: [],
  cancelRecording: false,
  autoNextTimeout: null,
  dictationRecognition: null,
  dictationShouldRun: false,
  dictationStopping: false,
  dictationRestartTimer: null,
  dictationRestartCount: 0,
  dictationLastError: "",
  transcript: "",
  transcriptFinal: "",
  transcriptInterim: "",
  transcriptStatus: "missing",
  transcriptSource: "browser_dictation",
  dictationFinalWait: null,
  browserTtsUtterance: null,
  activeHistoryId: null,
  historyItems: [],
  historyDetailCache: new Map(),
  historyDetailPromises: new Map(),
  abortingAttemptId: null,
  userExitedPractice: false,
  practiceViewBeforeSettings: null,
  darkMode: false,
  uiLanguage: "zh",
  p3Topics: [],
  p3SelectedTopic: "",
  p3Intensity: "normal",
  p3Focus: "comparison_concession",
  p3SourceType: "bank",
  p3SelectedBankCardId: "",
  p3CustomTheme: "",
  p3Plan: null,
  p3PlanError: "",
  p3PlanLoading: false,
  p3PracticeSource: null,
  p3CorpusSourceEntryId: "",
  p1Corpus: {
    topics: [],
    loaded: false,
    loadingPromise: null,
    activeEntry: null,
    previousPracticeView: "p1",
    saving: false,
  },
  p2Corpus: {
    categories: [],
    currentPart2Cards: [],
    loaded: false,
    loadingPromise: null,
    activeEntry: null,
    activeP3Entry: null,
    activeBankP3Entry: null,
    brainstormSaving: false,
    brainstormSuppressBlurSave: false,
    previousPracticeView: "p2",
    selectedEntryId: "",
    pinnedCueId: "",
    saving: false,
  },
  languageTakeaway: {
    items: [],
    loaded: false,
    loadingPromise: null,
    selectedText: "",
    rangeRect: null,
    selectionAnchor: null,
    selectionScrollRaf: null,
    dragging: false,
    dragOffsetX: 0,
    dragOffsetY: 0,
    hideEnglish: false,
    revealedEntryIds: new Set(),
    selectionTimer: null,
    activeEdit: null,
    editing: false,
  },
  writingTakeaway: {
    items: [],
    loaded: false,
    loadingPromise: null,
    hideEnglish: false,
    revealedEntryIds: new Set(),
  },
  spellingDrill: {
    _drillReady: false,
    items: [],
    stats: {},
    scope: "due",
    loaded: false,
    loadingPromise: null,
    currentIndex: 0,
    result: null,
    hintLevel: 0,
  },
  practiceLocked: false,
  startRequestId: 0,
  practiceSessionId: 0,
  startAbortController: null,
  navToastTimer: null,
  fontStyle: "default",
  pendingRecharge: 0,
  examinerAudioBlobUrls: new Map(),
  activeExaminerAudio: null,
  activeExaminerAudioPlayer: null,
  examinerPlayback: null,
  writing: {
    taskType: "task1_academic",
    prompts: {},
    prompt: null,
    requestedPromptId: "",
    promptHighlights: {},
    promptSelectionTimer: null,
    promptSelectionActive: false,
    pendingHighlightPointer: null,
    highlightMenuMode: "select",
    pendingHighlightDeleteIndex: -1,
    highlightPersistTimer: null,
    autosaveTimer: null,
    autosaveEnabled: false,
    autosaveSaving: false,
    autosaveQueued: false,
    autosaveFrameBaselineText: "",
    autosaveFrameBaselineWordCount: 0,
    entry: null,
    requestedEntryId: "",
    dirty: false,
    month: "",
    recentEntries: [],
    reportEntries: [],
    activeReportId: null,
    activeReportDetail: null,
    reportDetailCache: new Map(),
    reportDetailPromises: new Map(),
    reportEditLoading: false,
    reportEditRequestId: 0,
    scorePollTimer: null,
    scorePollingEntryId: null,
    scoreCompletionModalEntry: null,
    scoreCompletionNotifiedIds: new Set(),
    pickerTaskType: "task1_academic",
    promptCategories: {},
    promptPatterns: {},
    promptCatalog: {},
    promptLoadingPromises: {},
    promptImagePreloads: new Set(),
    promptImagePreloadPromises: new Map(),
    promptImagePreloadQueue: [],
    promptImagePreloadQueued: new Set(),
    promptImagePreloadActive: 0,
    promptImagePreloadScheduled: false,
    nearbyPromptImagePreloadSource: "",
    pickerCategoryFilters: {
      task1_academic: "",
      task2: "",
    },
    pickerPromptPatternFilters: {
      task2: "",
    },
    pickerSourceFilters: {
      task1_academic: "cambridge",
      task2: "cambridge",
    },
  },
  agentAssistant: {
    query: "",
    results: [],
    loading: false,
    context: "writing",
  },
  speaking: {
    pendingAnalysis: null,
    pendingTurnCompletions: new Map(),
    turnCompletionErrors: new Map(),
    retryCompletion: null,
    scorePollTimer: null,
    scorePollingTaskId: null,
    scoreCompletionModalAttempt: null,
    scoreCompletionNotifiedIds: new Set(),
    audioPreprocessor: null,
    audioPreprocessorToken: 0,
    audioPreprocessorMetrics: null,
    audioPreprocessorTurnMetrics: null,
    audioPreprocessorStopPromise: null,
    audioPreprocessorModulePromise: null,
    realtimePcmSocket: null,
    realtimePcmMetrics: null,
    examinerTtsRefreshPromises: new Map(),
    captureDevice: null,
  },
  account: {
    authenticated: false,
    backendAvailable: false,
    user: null,
    returnView: null,
    fromView: null,
    questionBankScope: "current",
    questionBankSummary: null,
    questionBankLoadingPromise: null,
    questionBankLoadingScope: "",
  },
  wallet: {
    payload: null,
    loaded: false,
    loadingPromise: null,
    fetchedAt: 0,
  },
  prefetch: {
    started: false,
    token: 0,
    fixedExaminerTtsWarmed: false,
    fixedExaminerTtsPromise: null,
    corpusEditorWarmed: false,
    corpusEditorWarmPromise: null,
  },
};

const VIEW_STORAGE_KEY = "ielts-view";
const UI_LANGUAGE_STORAGE_KEY = "ielts-ui-language";
const FULL_NAME_STORAGE_KEY = "ielts-full-name";
const ENGLISH_NAME_STORAGE_KEY = "ielts-english-name";
const QUESTION_BANK_SCOPE_STORAGE_KEY = "ielts-speaking-question-bank-scope";
const QUESTION_BANK_SCOPES = new Set(["current", "new", "retained", "archive", "all"]);
const PRACTICE_VIEWS = new Set(["mock", "p1", "p2", "p3"]);
const SPEAKING_PART_VIEWS = new Set(["p1", "p2", "p3", "mock"]);
const STANDALONE_CORPUS_VIEWS = new Set(["p1Corpus", "p2Corpus"]);
const WRITING_TASK_TYPES = new Set(["task1_academic", "task2"]);
const WRITING_PROMPT_BACKGROUND_IMAGE_PRELOAD_LIMIT = 2;
const WRITING_PROMPT_PICKER_EAGER_IMAGE_COUNT = 9;
const DEFAULT_FULL_NAME = "LiHua";
const DEFAULT_ENGLISH_NAME = "Jasper";
const WRITING_HIGHLIGHT_STORAGE_KEY = "writing-prompt-highlights";
const UI_LANGUAGES = new Set(["zh", "en"]);
const RECORD_CONTROL_DISABLED_STATUSES = new Set(["loading", "examiner_loading", "examiner_playing", "processing", "scoring", "turn_saved"]);
const PRACTICE_BUSY_STATUSES = new Set(["preparing", "recording", "processing", "scoring"]);
const TURN_RENDER_BUSY_STATUSES = new Set(["examiner_loading", "examiner_playing", "preparing", "recording", "processing"]);
const RECOVERABLE_PRACTICE_ERROR_STATUSES = new Set(["recording", "preparing", "processing", "turn_saved", "completion_failed"]);
const EXAMINER_TTS_PENDING_STATUSES = new Set(["pending", "warming", "generating"]);
const AI_TASK_ACTIVE_STATUSES = new Set(["pending", "running"]);
const AI_TASK_TERMINAL_STATUSES = new Set(["succeeded", "fallback", "failed", "cancelled"]);
const AI_TASK_COMPLETED_WITH_RESULT_STATUSES = new Set(["fallback", "succeeded"]);
const STREAM_PENDING_FOLLOW_UP_PLACEHOLDER = "Generating follow-up question...";
const STREAM_PENDING_FOLLOW_UP_PLACEHOLDERS = new Set([
  "",
  STREAM_PENDING_FOLLOW_UP_PLACEHOLDER,
  "正在生成追问...",
]);
const uiTranslations = {
  zh: {
    "app.title": "IELTS Studio",
    "action.back": "返回",
    "action.account": "账户",
    "action.questionAssistant": "题库助手",
    "writing.taskType": "Writing task type",
    "writing.selectPrompt": "选择写作题目",
    "writing.openBank": "打开题库",
    "writing.random": "随机换题",
    "nav.home": "首页",
    "nav.mock": "Mock",
    "nav.p1": "P1",
    "nav.p2": "P2",
    "nav.p3": "P3",
    "nav.speakingReports": "口语报告",
    "nav.dailyWriting": "每日写作",
    "nav.writingReports": "写作报告",
    "nav.corpus": "语料库",
    "nav.takeaway": "Takeaway",
    "nav.writingTakeaway": "写作积累",
    "nav.spellingDrill": "拼写错词训练",
    "nav.appearance": "Appearance",
    "nav.lockHint": "流程进行中，先点右侧叉号结束，再切换左侧模式。",
    "home.kicker": "IELTS Study Workspace",
    "home.title": "口语、写作和语料，一张工作台搞定。",
    "home.subtitle": "从真题练习到 AI 反馈，再到语料复用和拼写复习，把 IELTS 训练压进一个清晰的闭环。",
    "home.cta.speaking": "开始口语练习",
    "home.cta.writing": "写一篇作文",
    "home.spotlight.kicker": "Today",
    "home.spotlight.title": "先练输入，再沉淀表达",
    "home.spotlight.desc": "口语题库、写作报告、Takeaway 和拼写错词会互相回流，形成你自己的表达资产。",
    "home.speaking.title": "口语训练",
    "home.p1.title": "P1 短问短答",
    "home.p1.desc": "练直答、原因和具体细节。",
    "home.p2.title": "P2 Cue Card",
    "home.p2.desc": "准备 1 分钟后完成长回答。",
    "home.p3.title": "P3 深入讨论",
    "home.p3.desc": "围绕话题练观点、原因和对比。",
    "home.mock.title": "完整 Mock",
    "home.mock.desc": "P1、P2、P3 串联模拟。",
    "home.writing.title": "写作闭环",
    "home.writing.practice": "每日写作",
    "home.writing.practiceDesc": "选题、写作、保存，再交给 AI 评分。",
    "home.writing.reports": "写作报告",
    "home.writing.reportsDesc": "查看批改、Band 7 改写和错词反馈。",
    "home.corpus.title": "语料与复习",
    "home.corpus.library": "语料库",
    "home.corpus.libraryDesc": "管理 P1、P2、Takeaway 和写作积累。",
    "home.corpus.takeaway": "写作积累",
    "home.corpus.takeawayDesc": "沉淀可复用句型和观点表达。",
    "home.corpus.spelling": "拼写错词训练",
    "home.corpus.spellingDesc": "把作文错词加入间隔复习。",
    "account.kicker": "账户",
    "account.title": "个人资料与训练",
    "account.profileEyebrow": "Profile",
    "account.profileTitle": "口语身份资料",
    "account.profileLoading": "正在读取账号资料...",
    "account.nameChinese": "中文名",
    "account.nameEnglish": "英文名",
    "account.changePassword": "修改密码",
    "account.logout": "退出登录",
    "account.detailsGuest": "登录后可同步个人资料和账号安全设置。",
    "account.currentUser": "当前登录账号：",
    "account.guestLocal": "当前未登录，姓名仍会保存在本机。",
    "account.backendOffline": "后端暂不可用，姓名仍会保存在本机。",
    "account.securityStrong": "请使用强密码，并定期更换。",
    "account.securityLogin": "登录后可修改密码。",
    "bank.eyebrow": "题库",
    "bank.title": "题库选择",
    "bank.loading": "正在读取当前题库...",
    "bank.scopeAria": "选择口语题库范围",
    "bank.current": "当前考季",
    "bank.new": "新题",
    "bank.retained": "保留题",
    "bank.archive": "历史考季",
    "bank.all": "全部题库",
    "bank.currentGroup": "当季范围",
    "bank.archiveSelect": "选择历史考季",
    "bank.defaultLabel": "当季全部",
    "bank.followups": "P3 参考追问",
    "settings.darkMode": "深色外观",
    "settings.darkModeAria": "切换深色外观",
    "settings.language": "界面语言",
    "settings.languageAria": "选择界面语言",
    "settings.aiSource": "AI 评分来源",
    "settings.aiSource.gpt": "GPT（默认）",
    "settings.aiSource.claude": "Claude",
    "p1.corpusButton": "我的 P1 语料库",
    "p2.corpusButton": "我的 P2 串题素材库",
    "p2Corpus.aria": "我的 P2 串题素材库",
    "p2Corpus.kicker": "Part 2 语料库",
    "p2Corpus.title": "P2 串题素材库",
    "p2Corpus.subtitle": "按分类管理可复用素材，并单独维护相关 P3 追问。",
    "common.loading": "加载中...",
    "bank.generic": "题库",
    "bank.currentSeason": "当前考季",
    "bank.statusLine": "{season} · {scope} · {p1} P1 · {p2} P2 · {p3} P3 参考追问",
    "bank.statusLineNoP3": "{season} · {scope} · {p1} P1 · {p2} P2",
    "bank.loadFailed": "题库读取失败，练习会继续使用默认当季题库。",
    "wallet.eyebrow": "钱包",
    "wallet.title": "钱包",
    "wallet.recharge": "充值",
    "wallet.topUpKicker": "钱包充值",
    "wallet.topUpTitle": "充值",
    "wallet.topUpSubtitle": "选择预设金额，或输入自定义金额。",
    "wallet.amountLabel": "充值金额：",
    "wallet.amountPlaceholder": "输入金额",
    "wallet.cancel": "取消",
    "wallet.confirmRecharge": "确认充值",
    "wallet.available": "可用余额",
    "wallet.loading": "加载中",
    "wallet.reading": "读取中",
    "wallet.hint": "AI 功能按实际用量结算，余额需大于 ¥0.30。",
    "wallet.aiReady": "AI 可用",
    "wallet.lowBalance": "余额不足",
    "wallet.readyHint": "按实际用量结算；余额需保持大于 ¥{threshold}。",
    "wallet.blockedHint": "余额需大于 ¥{threshold} 才能使用 AI 功能，请先充值。",
    "wallet.rechargeRequiredShort": "余额不足，请先充值。",
    "wallet.emptyLedger": "暂无流水。",
    "wallet.loadFailed": "钱包加载失败",
    "wallet.ledgerUnavailable": "钱包流水暂时不可用。",
    "wallet.ledger.grant": "初始赠额",
    "wallet.ledger.recharge": "充值",
    "wallet.ledger.reserve": "历史预留",
    "wallet.ledger.release": "余额释放",
    "wallet.ledger.settle": "用量结算",
    "wallet.ledger.default": "钱包流水",
    "wallet.insufficientTitle": "余额不足",
    "wallet.insufficientBody": "余额需大于 ¥{threshold} 才能使用 AI 功能。充值后即可继续。",
    "wallet.later": "稍后",
    "wallet.goRecharge": "去充值",
    "security.title": "修改密码",
    "security.subtitle": "修改登录密码，保持账号安全。",
  },
  en: {
    "app.title": "IELTS Studio",
    "action.back": "Back",
    "action.account": "Account",
    "action.questionAssistant": "Question Assistant",
    "writing.taskType": "Writing task type",
    "writing.selectPrompt": "Choose writing prompt",
    "writing.openBank": "Open bank",
    "writing.random": "Random prompt",
    "nav.home": "Home",
    "nav.mock": "Mock",
    "nav.p1": "P1",
    "nav.p2": "P2",
    "nav.p3": "P3",
    "nav.speakingReports": "Speaking Reports",
    "nav.dailyWriting": "Daily Writing",
    "nav.writingReports": "Writing Reports",
    "nav.corpus": "Corpus",
    "nav.takeaway": "Takeaway",
    "nav.writingTakeaway": "Writing Bank",
    "nav.spellingDrill": "Spelling Drill",
    "nav.appearance": "Appearance",
    "nav.lockHint": "A practice flow is active. Use the close button on the right before switching modes.",
    "home.kicker": "IELTS Study Workspace",
    "home.title": "Speaking, writing, and corpus work in one desk.",
    "home.subtitle": "Move from real prompts to AI feedback, reusable language, and spelling review in one focused IELTS workflow.",
    "home.cta.speaking": "Start speaking",
    "home.cta.writing": "Write an essay",
    "home.spotlight.kicker": "Today",
    "home.spotlight.title": "Practice first, then bank the language",
    "home.spotlight.desc": "Speaking prompts, writing reports, takeaway notes, and spelling drills feed back into your own expression library.",
    "home.speaking.title": "Speaking practice",
    "home.p1.title": "P1 Short Answers",
    "home.p1.desc": "Practice direct answers, reasons, and details.",
    "home.p2.title": "P2 Cue Card",
    "home.p2.desc": "Prepare for one minute, then give a long turn.",
    "home.p3.title": "P3 Discussion",
    "home.p3.desc": "Practice opinions, reasons, comparisons, and follow-ups.",
    "home.mock.title": "Full Mock",
    "home.mock.desc": "Run P1, P2, and P3 as a full speaking test.",
    "home.writing.title": "Writing loop",
    "home.writing.practice": "Daily Writing",
    "home.writing.practiceDesc": "Choose a prompt, write, save, then score with AI.",
    "home.writing.reports": "Writing Reports",
    "home.writing.reportsDesc": "Review corrections, Band 7 rewrites, and spelling feedback.",
    "home.corpus.title": "Corpus & review",
    "home.corpus.library": "Corpus",
    "home.corpus.libraryDesc": "Manage P1, P2, Takeaway, and writing banks.",
    "home.corpus.takeaway": "Writing Bank",
    "home.corpus.takeawayDesc": "Save reusable sentence patterns and ideas.",
    "home.corpus.spelling": "Spelling Drill",
    "home.corpus.spellingDesc": "Review spelling mistakes from writing reports.",
    "account.kicker": "Account",
    "account.title": "Profile & Training",
    "account.profileEyebrow": "Profile",
    "account.profileTitle": "Speaking profile",
    "account.profileLoading": "Loading account profile...",
    "account.nameChinese": "Chinese name",
    "account.nameEnglish": "English name",
    "account.changePassword": "Change password",
    "account.logout": "Sign out",
    "account.detailsGuest": "Sign in to sync profile and account settings.",
    "account.currentUser": "Signed in as: ",
    "account.guestLocal": "Not signed in. Names are still saved locally.",
    "account.backendOffline": "Backend unavailable. Names are still saved locally.",
    "account.securityStrong": "Use a strong password and update it regularly.",
    "account.securityLogin": "Sign in to change your password.",
    "bank.eyebrow": "Question Bank",
    "bank.title": "Question bank",
    "bank.loading": "Loading current question bank...",
    "bank.scopeAria": "Choose speaking question bank scope",
    "bank.current": "Current season",
    "bank.new": "New topics",
    "bank.retained": "Retained",
    "bank.archive": "Past seasons",
    "bank.all": "All banks",
    "bank.currentGroup": "Current-season scopes",
    "bank.archiveSelect": "Choose past season",
    "bank.defaultLabel": "Current bank",
    "bank.followups": "P3 follow-ups",
    "settings.darkMode": "Dark mode",
    "settings.darkModeAria": "Toggle dark mode",
    "settings.language": "Interface language",
    "settings.languageAria": "Choose interface language",
    "settings.aiSource": "AI scoring source",
    "settings.aiSource.gpt": "GPT (default)",
    "settings.aiSource.claude": "Claude",
    "p1.corpusButton": "My P1 Corpus",
    "p2.corpusButton": "My P2 Story Bank",
    "p2Corpus.aria": "My P2 Story Bank",
    "p2Corpus.kicker": "Part 2 Library",
    "p2Corpus.title": "My P2 Story Bank",
    "p2Corpus.subtitle": "Organize reusable story material and maintain related P3 follow-ups separately.",
    "common.loading": "Loading...",
    "bank.generic": "Bank",
    "bank.currentSeason": "Current season",
    "bank.statusLine": "{season} · {scope} · {p1} P1 · {p2} P2 · {p3} P3 follow-ups",
    "bank.statusLineNoP3": "{season} · {scope} · {p1} P1 · {p2} P2",
    "bank.loadFailed": "Could not load the question bank. Practice will continue with the default current bank.",
    "wallet.eyebrow": "Wallet",
    "wallet.title": "Wallet",
    "wallet.recharge": "Recharge",
    "wallet.topUpKicker": "Wallet top-up",
    "wallet.topUpTitle": "Recharge",
    "wallet.topUpSubtitle": "Choose a preset amount or enter a custom amount.",
    "wallet.amountLabel": "Top-up amount:",
    "wallet.amountPlaceholder": "Enter amount",
    "wallet.cancel": "Cancel",
    "wallet.confirmRecharge": "Confirm recharge",
    "wallet.available": "Available balance",
    "wallet.loading": "Loading",
    "wallet.reading": "Loading",
    "wallet.hint": "AI features are usage-based. Balance must stay above ¥0.30.",
    "wallet.aiReady": "AI ready",
    "wallet.lowBalance": "Low balance",
    "wallet.readyHint": "Charged by actual usage; keep balance above ¥{threshold}.",
    "wallet.blockedHint": "Balance must be above ¥{threshold} to use AI features. Please recharge first.",
    "wallet.rechargeRequiredShort": "Low balance. Please recharge first.",
    "wallet.emptyLedger": "No wallet activity yet.",
    "wallet.loadFailed": "Wallet failed to load",
    "wallet.ledgerUnavailable": "Wallet activity is temporarily unavailable.",
    "wallet.ledger.grant": "Initial credit",
    "wallet.ledger.recharge": "Recharge",
    "wallet.ledger.reserve": "Historical reserve",
    "wallet.ledger.release": "Balance release",
    "wallet.ledger.settle": "Usage settlement",
    "wallet.ledger.default": "Wallet activity",
    "wallet.insufficientTitle": "Low balance",
    "wallet.insufficientBody": "Balance must be above ¥{threshold} to use AI features. Recharge to continue.",
    "wallet.later": "Later",
    "wallet.goRecharge": "Recharge",
    "security.title": "Change password",
    "security.subtitle": "Update your login password to keep the account secure.",
  },
};
const viewCopy = {
  home: ["首页", "口语、写作和语料复习的综合训练工作台。"],
  mock: ["Mock 模考", "完整模拟 P1、P2 和 P3 的口语考试流程。"],
  p1: ["Part 1 短问短答", "练习 IELTS 风格的短问短答流程。"],
  p2: ["Part 2 题卡", "题卡准备 1 分钟，然后完成一段长回答。"],
  p3: ["Part 3 深入讨论", "练观点解释、对比让步、未来趋势和社会层面的深入讨论。"],
  corpus: ["语料库", "管理口语素材、写作积累和可复用表达。"],
  p1Corpus: ["我的 P1 语料库", "按话题整理 Part 1 答案，并在 AI 反馈中复用。"],
  p2Corpus: ["我的 P2 串题素材库", "准备可复用的 Part 2 故事素材，并在练习中链接使用。"],
  takeawayBook: ["Takeaway", "复习已保存表达，遮住英文进行回忆。"],
  writingTakeawayBook: ["写作积累", "复习已保存的写作短语和论证素材。"],
  spellingDrill: ["拼写错词训练", "重写作文批改中的拼写错词，直到掌握。"],
  history: ["口语报告", ""],
  writing: ["", ""],
  writingReports: ["写作报告", ""],
  login: ["Sign in", "Sign in to access your reports, wallet, and personalized training."],
  register: ["Create account", "Create an account to save your practice history and access personalized features."],
  forgotPassword: ["Reset password", "Reset your password via email if configured."],
  accountProfile: ["账户", "管理个人资料和账号设置。"],
  accountSecurity: ["账号安全", "修改密码并管理账号安全设置。"],
};
const viewCopyEn = {
  home: ["Home", "A focused workspace for speaking, writing, and corpus review."],
  mock: ["Mock", "Run a full P1, P2, and P3 speaking exam flow."],
  p1: ["Part 1", "Practice short questions in an IELTS-style interview flow."],
  p2: ["Part 2", "Cue card, one-minute preparation, then a long turn."],
  p3: ["Part 3", "Practice explanation, comparison, future trends, and social-level discussion."],
  corpus: ["Corpus", "Manage prepared speaking material and language takeaways."],
  p1Corpus: ["My P1 Corpus", "Prepare grouped Part 1 answers and reuse them in AI feedback."],
  p2Corpus: ["My P2 Story Bank", "Prepare reusable Part 2 story materials and link them during preparation."],
  takeawayBook: ["Takeaway", "Review saved language takeaways with hidden English recall."],
  writingTakeawayBook: ["Writing Bank", "Review saved writing phrases and reusable argument material."],
  spellingDrill: ["Spelling Drill", "Rewrite spelling mistakes from scored writing reports until they are mastered."],
  history: ["Speaking Reports", ""],
  writing: ["", ""],
  writingReports: ["Writing Reports", ""],
  login: ["Sign in", "Sign in to access your reports, wallet, and personalized training."],
  register: ["Create account", "Create an account to save your practice history and access personalized features."],
  forgotPassword: ["Reset password", "Reset your password via email if configured."],
  accountProfile: ["Account", "Manage profile and account settings."],
  accountSecurity: ["Account security", "Change password and manage account security."],
};

function normalizeUiLanguage(value) {
  return UI_LANGUAGES.has(value) ? value : "zh";
}

function currentUiLanguage() {
  return normalizeUiLanguage(state.uiLanguage);
}

function t(key, fallback = "") {
  const lang = currentUiLanguage();
  return uiTranslations[lang]?.[key] ?? uiTranslations.zh?.[key] ?? fallback ?? key;
}

function tf(key, values = {}, fallback = "") {
  return String(t(key, fallback)).replace(/\{(\w+)\}/g, (_match, name) => {
    return Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : "";
  });
}

function viewCopyFor(view) {
  const langCopy = currentUiLanguage() === "en" ? viewCopyEn : viewCopy;
  return langCopy[view] || viewCopy[view] || viewCopy.home;
}

function isKnownView(view) {
  return Boolean(viewCopy[view]);
}

function viewTitleFor(view) {
  return viewCopyFor(view)[0];
}

function viewSubtitleFor(view) {
  return viewCopyFor(view)[1];
}

function practiceReadyText(view) {
  if (view === "mock") return currentUiLanguage() === "en" ? "Mock practice: P1 -> P2 -> P3" : "Mock 模考：P1 → P2 → P3";
  return currentUiLanguage() === "en" ? `${viewTitleFor(view)} ready` : `${viewTitleFor(view)} 准备就绪`;
}

function isPracticeView(view) {
  return PRACTICE_VIEWS.has(view);
}

function isStandaloneCorpusView(view) {
  return STANDALONE_CORPUS_VIEWS.has(view);
}

function isKnownWritingTaskType(value) {
  return WRITING_TASK_TYPES.has(value);
}

function isSpeakingPartView(part) {
  return SPEAKING_PART_VIEWS.has(part);
}

function isRecordControlDisabledStatus(status) {
  return RECORD_CONTROL_DISABLED_STATUSES.has(String(status || ""));
}

function isPracticeBusyStatus(status) {
  return PRACTICE_BUSY_STATUSES.has(String(status || ""));
}

function isTurnRenderBusyStatus(status) {
  return TURN_RENDER_BUSY_STATUSES.has(String(status || ""));
}

function isRecoverablePracticeErrorStatus(status) {
  return RECOVERABLE_PRACTICE_ERROR_STATUSES.has(String(status || ""));
}

function isPendingExaminerTtsStatus(status) {
  return EXAMINER_TTS_PENDING_STATUSES.has(String(status || ""));
}

function isAiTaskActiveStatus(status) {
  return AI_TASK_ACTIVE_STATUSES.has(String(status || ""));
}

function isAiTaskTerminalStatus(status) {
  return AI_TASK_TERMINAL_STATUSES.has(String(status || ""));
}

function isAiTaskCompletedWithResultStatus(status) {
  return AI_TASK_COMPLETED_WITH_RESULT_STATUSES.has(String(status || ""));
}

function isEditableShortcutTarget(target) {
  const element = target?.nodeType === Node.TEXT_NODE ? target.parentElement : target;
  if (!element) return false;
  const tagName = String(element.tagName || "").toLowerCase();
  return Boolean(
    element.isContentEditable
      || ["input", "textarea", "select"].includes(tagName)
      || element.closest?.("[contenteditable='true'], .toastui-editor-contents, .toastui-editor-ww-container, .vditor, .ProseMirror")
  );
}

function isTakeawayReviewActiveForKind(kind) {
  const panel = kind === "writing" ? $("writingTakeawayReviewPanel") : $("languageTakeawayReviewPanel");
  return Boolean(panel && !panel.classList.contains("hidden") && panel.classList.contains("is-active"));
}

function applyStaticTranslations(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n, el.textContent || "");
  });
  root.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const value = t(el.dataset.i18nTitle, el.getAttribute("title") || "");
    el.setAttribute("title", value);
  });
  root.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    const value = t(el.dataset.i18nAria, el.getAttribute("aria-label") || "");
    el.setAttribute("aria-label", value);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.setAttribute("placeholder", t(el.dataset.i18nPlaceholder, el.getAttribute("placeholder") || ""));
  });
}

function updateLanguageControls() {
  const lang = currentUiLanguage();
  document.querySelectorAll("[data-ui-language-option]").forEach((button) => {
    const active = normalizeUiLanguage(button.dataset.uiLanguageOption) === lang;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function refreshLocalizedChrome() {
  applyStaticTranslations();
  updateLanguageControls();
  const copy = viewCopyFor(state.view);
  text("viewTitle", copy[0]);
  text("viewSubtitle", copy[1]);
  renderQuestionBankSelector(state.account.questionBankSummary);
  renderNavigationBankStatus(state.account.questionBankSummary);
  renderAccountStatus();
  if (state.wallet.loaded && state.wallet.payload) {
    renderWalletPayload(state.wallet.payload);
  }
}

function applyUiLanguage(value, options = {}) {
  const lang = normalizeUiLanguage(value);
  state.uiLanguage = lang;
  document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
  document.title = t("app.title", "IELTS Studio");
  document.body.dataset.uiLang = lang;
  if (!options.skipPersist) {
    try {
      localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, lang);
    } catch (_error) {
      // Local preference only; failing to persist should not block the app.
    }
  }
  refreshLocalizedChrome();
  window.IELTS_I18N = {
    language: lang,
    t,
    setLanguage: (nextLanguage) => applyUiLanguage(nextLanguage),
  };
  window.dispatchEvent(new CustomEvent("ielts:ui-language-change", { detail: { language: lang } }));
}

function loadUiLanguage() {
  let stored = "zh";
  try {
    stored = localStorage.getItem(UI_LANGUAGE_STORAGE_KEY) || "zh";
  } catch (_error) {
    stored = "zh";
  }
  applyUiLanguage(stored, { skipPersist: true });
}

const authViews = new Set(["login", "register", "forgotPassword"]);
const protectedViews = new Set(["history", "writing", "writingReports", "corpus", "p1Corpus", "p2Corpus", "takeawayBook", "writingTakeawayBook", "spellingDrill", "accountProfile", "accountSecurity"]);
const corpusViews = new Set(["corpus", "p1Corpus", "p2Corpus", "takeawayBook", "writingTakeawayBook", "spellingDrill"]);
const accountViews = new Set(["accountProfile", "accountSecurity"]);
const corpusBackButtonViews = new Set(["p1Corpus", "p2Corpus", "takeawayBook", "writingTakeawayBook", "spellingDrill"]);
const topPinnedViews = new Set(["home", "corpus", "p1Corpus", "p2Corpus"]);
const workspaceHeaderHiddenViews = new Set(["home", "history", "writing", "writingReports", ...corpusViews, ...authViews, ...accountViews]);
const agentAssistantViews = new Set(["writing"]);

const EXAMINER_AUDIO_LOAD_TIMEOUT_MS = 15000;
const EXAMINER_AUDIO_INPUT_RELEASE_TIMEOUT_MS = 1800;
const EXAMINER_AUDIO_BLUETOOTH_DRAIN_MS = 320;
const EXAMINER_TTS_REFRESH_WAIT_MS = 4200;
const EXAMINER_TTS_REFRESH_INTERVAL_MS = 550;
const CORPUS_PEEK_WINDOW_MARGIN = 16;
const P3_SOURCE_LABELS = {
  bank: "题库固定追问",
  season_bank: "题库固定追问",
  p2_report: "根据 P2 报告",
  custom: "自定义主题",
  p2_answer: "根据 P2 回答",
};
const P3_FOCUS_LABELS = {
  abstract_discussion: "抽象讨论",
  cause_effect: "原因影响",
  comparison_concession: "对比让步",
  future_trends: "未来趋势",
  policy_society: "社会政策",
};
const P3_TYPE_LABELS = {
  opinion_justify: "观点论证",
  change_trend: "变化趋势",
  future_prediction: "未来预测",
  problem_solution: "问题方案",
  policy_responsibility: "责任政策",
  comparison_concession: "对比让步",
  abstract_discussion: "抽象讨论",
  cause_effect: "原因影响",
  future_trends: "未来趋势",
  policy_society: "社会政策",
};
const P3_MOVE_LABELS = {
  "clear position": "先给明确立场",
  reason: "解释原因",
  "brief contrast": "补一个反方角度",
  "past-present comparison": "过去/现在对比",
  cause: "指出原因",
  consequence: "说明影响",
  prediction: "给出预测",
  condition: "补充条件",
  "long-term impact": "长期影响",
  problem: "指出问题",
  example: "给具体例子",
  "practical response": "给现实方案",
  stakeholder: "点出相关群体",
  responsibility: "讨论责任",
  "balanced view": "平衡观点",
  "compare groups": "比较不同群体",
  concession: "承认反方合理性",
  "specific example": "具体例子支撑",
  generalize: "上升到一般现象",
  "define the issue": "界定问题",
  "social impact": "社会层面影响",
  "main cause": "主因",
  effect: "结果影响",
  priority: "判断优先级",
  "future change": "未来变化",
  driver: "变化驱动因素",
  "risk or benefit": "风险/好处",
  "public role": "公共角色",
  "individual role": "个人角色",
  "trade-off": "权衡利弊",
  "respond directly": "直接回应追问",
  "add evidence": "补证据",
  "extend the idea": "继续延展观点",
};
const P3_TYPE_SEQUENCE = [
  "opinion_justify",
  "change_trend",
  "future_prediction",
  "problem_solution",
  "policy_responsibility",
];
const P3_FOCUS_TO_TYPE = {
  abstract_discussion: "abstract_discussion",
  cause_effect: "cause_effect",
  comparison_concession: "comparison_concession",
  future_trends: "future_trends",
  policy_society: "policy_society",
};
const P3_TARGET_MOVES = {
  opinion_justify: ["clear position", "reason", "brief contrast"],
  change_trend: ["past-present comparison", "cause", "consequence"],
  future_prediction: ["prediction", "condition", "long-term impact"],
  problem_solution: ["problem", "example", "practical response"],
  policy_responsibility: ["stakeholder", "responsibility", "balanced view"],
  comparison_concession: ["compare groups", "concession", "specific example"],
  abstract_discussion: ["generalize", "define the issue", "social impact"],
  cause_effect: ["main cause", "effect", "priority"],
  future_trends: ["future change", "driver", "risk or benefit"],
  policy_society: ["public role", "individual role", "trade-off"],
};
const P3_INTENSITY_HELP = {
  normal: "每轮 3 个主问题，重点把每题说成“观点 + 原因 + 例子/对比 + 影响”。",
  high: "每个主问题后追加追问，训练临场承接和更深一层解释。",
};
const corpusPeekDrag = {
  dialogId: "",
  dragging: false,
  dragOffsetX: 0,
  dragOffsetY: 0,
};

const {
  $,
  byId,
  escapeCssValue,
  escapeHtml,
  normalizeSpokenAnswerMarkdown,
  renderMarkdown,
  renderSpokenAnswerMarkdown,
  text,
} = window.IELTSSharedUI || {};

const apiClient = window.IELTSApiClient;
if (!apiClient) {
  throw new Error("IELTSApiClient module failed to initialize.");
}
const {
  api,
  ensureCsrfToken,
  getCsrfToken,
  resetCsrfToken,
} = apiClient;

const appearance = window.IELTSAppearance?.createAppearanceControls?.({ state });
if (!appearance) {
  throw new Error("IELTSAppearance module failed to initialize.");
}
const {
  applyFontStyle,
  applyDarkMode,
  loadDarkMode,
  loadFontStyle,
} = appearance;

const viewRouter = window.IELTSViewRouter?.createViewRouter?.({ state, viewCopy });
if (!viewRouter) {
  throw new Error("IELTSViewRouter module failed to initialize.");
}
const {
  requestedUrlView,
  requestedRouteState,
  requestedStandaloneView,
  viewUrl,
  isNewTabNavigationEvent,
  openViewInNewTabForModifier,
  updateViewUrl,
  syncUrlForCurrentState,
  writingPromptDeepLink,
  writingEntryEditUrl,
} = viewRouter;

function loadWritingPromptHighlights() {
  try {
    const raw = localStorage.getItem(WRITING_HIGHLIGHT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function saveWritingPromptHighlights() {
  try {
    localStorage.setItem(WRITING_HIGHLIGHT_STORAGE_KEY, JSON.stringify(state.writing.promptHighlights || {}));
  } catch (_error) {
    // Ignore storage failures.
  }
}

function normalizeWritingPromptHighlightRanges(ranges = [], sourceText = "") {
  const text = String(sourceText || "");
  return (Array.isArray(ranges) ? ranges : [])
    .map((range) => ({
      start: Math.max(0, Math.min(text.length, Number(range?.start) || 0)),
      end: Math.max(0, Math.min(text.length, Number(range?.end) || 0)),
    }))
    .filter((range) => range.end > range.start)
    .sort((a, b) => a.start - b.start);
}

function writingPromptHighlightKey(prompt = state.writing.prompt) {
  return String(prompt?.id || prompt?.prompt_id || prompt?.display_catalog_id || "").trim();
}

function currentWritingPromptHighlightState() {
  const promptId = writingPromptHighlightKey();
  if (!promptId) return [];
  return Array.isArray(state.writing.promptHighlights?.[promptId]) ? state.writing.promptHighlights[promptId] : [];
}

function textOffsetFromNode(root, node, offset) {
  const range = document.createRange();
  range.selectNodeContents(root);
  try {
    range.setEnd(node, offset);
    return range.toString().length;
  } catch (_error) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let cursor = 0;
    while (walker.nextNode()) {
      const current = walker.currentNode;
      if (current === node) return cursor + offset;
      cursor += current.textContent.length;
    }
    return cursor;
  }
}

function setWritingPromptHighlightState(promptId, ranges) {
  const id = String(promptId || "").trim();
  if (!id) return;
  const sourceText = String(state.writing.prompt?.prompt || "");
  state.writing.promptHighlights[id] = normalizeWritingPromptHighlightRanges(ranges, sourceText);
  saveWritingPromptHighlights();
  if (state.writing.entry && id === writingPromptHighlightKey(state.writing.prompt)) {
    state.writing.entry.prompt_highlights = state.writing.promptHighlights[id];
    scheduleWritingHighlightPersist();
  }
  renderWritingSurface();
}

function setWritingHighlightMenuMode(mode) {
  state.writing.highlightMenuMode = mode === "clear" ? "clear" : "select";
  const button = $("writingHighlightBtn");
  $("writingHighlightMenu")?.classList.toggle("is-delete", state.writing.highlightMenuMode === "clear");
  if (!button) return;
  if (state.writing.highlightMenuMode === "clear") {
    button.innerHTML = `<svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M3 6h18"></path>
        <path d="M8 6V4h8v2"></path>
        <path d="M19 6l-1 14H6L5 6"></path>
      </svg>
      <span>Delete</span>`;
  } else {
    button.innerHTML = `<svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="m9 11 4 4L22 6"></path>
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
      </svg>
      <span>Highlight</span>`;
  }
}

function getWritingPromptSelectionRange() {
  const selection = window.getSelection?.();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;
  const promptEl = $("writingPromptText");
  if (!promptEl) return null;
  const range = selection.getRangeAt(0);
  if (!promptEl.contains(range.commonAncestorContainer)) return null;
  const sourceText = String(promptEl.textContent || "");
  const start = textOffsetFromNode(promptEl, range.startContainer, range.startOffset);
  const end = textOffsetFromNode(promptEl, range.endContainer, range.endOffset);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
  if (start < 0 || end > sourceText.length) return null;
  return {
    start,
    end,
    text: sourceText.slice(start, end),
    rect: range.getBoundingClientRect(),
  };
}

function getWritingPromptRangeAtPoint(clientX, clientY) {
  const promptEl = $("writingPromptText");
  if (!promptEl) return null;
  const point = document.caretRangeFromPoint?.(clientX, clientY) || document.caretPositionFromPoint?.(clientX, clientY);
  if (!point) return null;
  const node = point.startContainer || point.offsetNode || null;
  const offset = point.startOffset ?? point.offset ?? 0;
  if (!node || !promptEl.contains(node)) return null;
  const textOffset = textOffsetFromNode(promptEl, node, offset);
  return currentWritingPromptHighlightState().find((range) => textOffset >= range.start && textOffset <= range.end) || null;
}

function renderWritingPromptSliceWithHighlights(text, ranges = [], start = 0, end = text.length) {
  const safeStart = Math.max(0, Math.min(start, text.length));
  const safeEnd = Math.max(safeStart, Math.min(end, text.length));
  const visibleRanges = normalizeWritingPromptHighlightRanges(ranges, text)
    .map((range, index) => ({ ...range, index }))
    .filter((range) => range.end > safeStart && range.start < safeEnd);
  if (!visibleRanges.length) return escapeHtml(text.slice(safeStart, safeEnd)).replace(/\n/g, "<br>");
  let output = "";
  let cursor = safeStart;
  visibleRanges.forEach((range) => {
    const rangeStart = Math.max(range.start, safeStart);
    const rangeEnd = Math.min(range.end, safeEnd);
    output += escapeHtml(text.slice(cursor, rangeStart)).replace(/\n/g, "<br>");
    output += `<mark class="writing-highlight-mark" data-writing-highlight-index="${range.index}" tabindex="0" role="button" aria-label="删除这条题目高亮">${escapeHtml(text.slice(rangeStart, rangeEnd)).replace(/\n/g, "<br>")}</mark>`;
    cursor = rangeEnd;
  });
  output += escapeHtml(text.slice(cursor, safeEnd)).replace(/\n/g, "<br>");
  return output;
}

function task2FixedQuestionRanges(textValue = "") {
  const text = String(textValue || "");
  const patterns = [
    /to what exten[td] do(?: you)? agree (?:or|of) disagree(?: with (?:this|the) (?:statement|opinion|view))?\?/gi,
    /to what exten[td] do you think[^?]*\?/gi,
    /do you agree or disagree\?/gi,
    /(?:do you think|whether|is|are|ls) (?:this|it|that|these|they|the (?:trend|development|change|situation|effect|impact))?(?: is| are)?(?: a)? positive (?:or )?(?:a )?negative (?:development|trend|change|situation|effects?|impacts?|characteristic)?\?/gi,
    /(?:do you think|whether) (?:the|this|that) (?:trend|development|change|situation|effect|impact) (?:is|are) (?:a )?positive (?:or )?(?:a )?negative (?:development|trend|change|situation|effects?|impacts?|characteristic)?\?/gi,
    /has (?:this|it|that|the (?:trend|development|change|situation|effect|impact)) become (?:a )?positive (?:or )?(?:a )?negative (?:development|trend|change|situation|effects?|impacts?|characteristic)\?/gi,
    /discuss\s*&\s*give (?:your|our)(?: own)? opinions?\.?/gi,
    /discuss both(?: (?:these|the|those))?(?: (?:views?|sides?))?(?: and)?(?: give)? (?:your|our)(?: own)? (?:opinions?|view)\.?/gi,
    /what is the value[^?]*\?[^?]*what are the arguments in favour[^?]*\?/gi,
    /to what exten[td]\s+do (?:the )?(?:advantages?|benefits?)[^?]*\boutweigh\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/gi,
    /do you think [^?]*\bbenefits?\b[^?]*\boutweigh\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/gi,
    /do (?:the )?benefits?[^?]*\boutweigh\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/gi,
    /do you think [^?]*\badvantages?\b[^?]*\boutweigh\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/gi,
    /do (?:the )?advantages?[^?]*\boutweigh\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/gi,
    /\bnegative effects?\b[^?]*\boutweigh\b[^?]*\bpositive effects?\b[^?]*\?/gi,
    /\b(?:advantages?|benefits?)\b[^?]*\bor\b[^?]*\b(?:disadvantages?|drawbacks?)\b[^?]*\?/gi,
    /what are the advantages and disadvantages(?: of this)?\?/gi,
    /what are the benefits and drawbacks(?: of this)?\?/gi,
    /what is the value[^?]*\?[^?]*what are the arguments in favour[^?]*\?/gi,
    /what factors? contribute[^?]*\?[^?]*how realistic[^?]*\?/gi,
    /(?:why|what (?:do you think )?(?:are )?(?:the )?(?:reasons?|causes?|problems?))[^?]*(?:how (?:can|could)|what can|what could|what should|what (?:are )?(?:the )?(?:solutions?|measures?)|solutions?|measures?|solve|research|encourage|positive|negative|effects?|impact|affect|advantages?|disadvantages?)[^?]*\?/gi,
    /what (?:problems?|causes?)[^?]*\?[^?]*(?:solutions?|measures|solve)[^?]*\?/gi,
    /why is this (?:the case|happening)\?[^?]*(?:solutions?|measures|solve|positive|negative)[^?]*\?/gi,
    /what (?:are )?(?:the )?(?:causes?|reasons?)[^?]*\?[^?]*(?:effects?|impact|affect)[^?]*\?/gi,
    /(?:what|why|how)[^?]*\?[^?]*(?:what|why|how|do you think)[^?]*\?/gi,
  ];
  const ranges = [];
  for (const pattern of patterns) {
    pattern.lastIndex = 0;
    let match = pattern.exec(text);
    while (match) {
      ranges.push({ start: match.index, end: match.index + match[0].length });
      match = pattern.exec(text);
    }
  }
  return ranges
    .sort((a, b) => a.start - b.start || b.end - a.end)
    .filter((range, index, sorted) => !sorted.slice(0, index).some((prev) => range.start >= prev.start && range.end <= prev.end));
}

function task2FixedQuestionDisplayLabel(questionText = "") {
  const text = String(questionText || "").replace(/\s+/g, " ").trim();
  return text;
}

function renderTask2PromptTextWithHighlights(textValue, ranges = []) {
  const text = String(textValue || "");
  const fixedRanges = task2FixedQuestionRanges(text);
  if (!fixedRanges.length) return renderWritingPromptTextWithHighlights(text, ranges);
  let output = "";
  let cursor = 0;
  fixedRanges.forEach((range) => {
    if (range.start > cursor) {
      output += `<span class="writing-prompt-segment writing-prompt-context">${renderWritingPromptSliceWithHighlights(text, ranges, cursor, range.start)}</span>`;
    }
    output += `<strong class="writing-prompt-segment writing-prompt-fixed-question">${escapeHtml(task2FixedQuestionDisplayLabel(text.slice(range.start, range.end)))}</strong>`;
    cursor = range.end;
  });
  if (cursor < text.length) {
    output += `<span class="writing-prompt-segment writing-prompt-context">${renderWritingPromptSliceWithHighlights(text, ranges, cursor, text.length)}</span>`;
  }
  return `<span class="writing-prompt-text-structured">${output}</span>`;
}

function renderWritingPromptTextWithHighlights(textValue, ranges = []) {
  const text = String(textValue || "");
  const normalized = normalizeWritingPromptHighlightRanges(ranges, text);
  if (!text) return "";
  if (!normalized.length) return escapeHtml(text).replace(/\n/g, "<br>");
  return renderWritingPromptSliceWithHighlights(text, normalized, 0, text.length);
}

function deletePendingWritingPromptHighlight() {
  const promptId = writingPromptHighlightKey(state.writing.prompt);
  if (!promptId) return false;
  const current = currentWritingPromptHighlightState();
  const index = Number(state.writing.pendingHighlightDeleteIndex);
  if (!Number.isInteger(index) || index < 0 || index >= current.length) return false;
  current.splice(index, 1);
  state.writing.pendingHighlightDeleteIndex = -1;
  setWritingPromptHighlightState(promptId, current);
  return true;
}

function currentWritingPromptHighlightsPayload() {
  const promptId = writingPromptHighlightKey(state.writing.prompt);
  if (!promptId) return [];
  return currentWritingPromptHighlightState().map((range) => ({
    start: range.start,
    end: range.end,
  }));
}

function scheduleWritingHighlightPersist() {
  window.clearTimeout(state.writing.highlightPersistTimer);
  if (!state.writing.entry?.id || !state.writing.prompt) return;
  if (state.writing.dirty) return;
  state.writing.highlightPersistTimer = window.setTimeout(() => {
    persistWritingPromptHighlights().catch(() => null);
  }, 450);
}

async function persistWritingPromptHighlights() {
  if (!state.writing.entry?.id || !state.writing.prompt) return null;
  if (state.writing.dirty) return null;
  const prompt = state.writing.prompt;
  const payload = {
    id: state.writing.entry.id,
    task_type: prompt.task_type || state.writing.taskType,
    prompt_id: prompt.id || prompt.prompt_id || state.writing.entry.prompt_id,
    prompt: prompt.prompt,
    title: writingPromptDisplayTitle(prompt),
    category: prompt.category,
    image_url: prompt.image_url || "",
    answer: $("writingAnswer")?.value || state.writing.entry.answer || "",
    prompt_highlights: currentWritingPromptHighlightsPayload(),
  };
  const entry = await api("/api/writing/entries", payload);
  state.writing.entry = entry;
  state.writing.reportDetailCache.set(entry.id, entry);
  return entry;
}

let busyDepth = 0;

function setBusy(message, options = {}) {
  if (options.forceClear) busyDepth = 0;
  const bar = $("#busyBar");
  if (!bar) return;
  bar.classList.toggle("hidden", !message);
  text("busyText", message || "");
}

const candidateProfile = window.IELTSCandidateProfile?.createCandidateProfileController?.({
  state,
  $,
  api,
  defaultFullName: DEFAULT_FULL_NAME,
  defaultEnglishName: DEFAULT_ENGLISH_NAME,
  fullNameStorageKey: FULL_NAME_STORAGE_KEY,
  englishNameStorageKey: ENGLISH_NAME_STORAGE_KEY,
  renderAccountStatus,
});
if (!candidateProfile) {
  throw new Error("IELTSCandidateProfile module failed to initialize.");
}

function candidateNames(...args) {
  return candidateProfile.candidateNames(...args);
}

function applyCandidateNames(...args) {
  return candidateProfile.applyCandidateNames(...args);
}

function saveCandidateNames(...args) {
  return candidateProfile.saveCandidateNames(...args);
}

function scheduleCandidateNameSave(...args) {
  return candidateProfile.scheduleCandidateNameSave(...args);
}

function flushCandidateNameSave(...args) {
  return candidateProfile.flushCandidateNameSave(...args);
}

function updateAvatars(...args) {
  return candidateProfile.updateAvatars(...args);
}

function loadCandidateNames(...args) {
  return candidateProfile.loadCandidateNames(...args);
}

async function withBusy(message, action) {
  busyDepth += 1;
  setBusy(message);
  try {
    return await action();
  } finally {
    busyDepth = Math.max(0, busyDepth - 1);
    if (busyDepth === 0) setBusy("");
  }
}

function scheduleIdleTask(action, timeout = 1200) {
  const run = () => {
    Promise.resolve()
      .then(action)
      .catch(() => {
        // Background prefetch should never interrupt the active learner flow.
      });
  };
  const delay = Math.max(0, Number(timeout) || 0);
  window.setTimeout(() => {
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(run, { timeout: Math.max(800, delay) });
    } else {
      run();
    }
  }, delay);
}

const writingPromptImagePreloader = window.IELTSWritingImagePreload?.createWritingPromptImagePreloader?.({
  state,
  scheduleIdleTask,
  imagePreloadLimit: WRITING_PROMPT_BACKGROUND_IMAGE_PRELOAD_LIMIT,
});
if (!writingPromptImagePreloader) {
  throw new Error("IELTSWritingImagePreload module failed to initialize.");
}
const {
  canWarmWritingPromptImages,
  drainWritingPromptImagePreloadQueue,
  ensureWritingPromptImageReady,
  primeWritingPromptImage,
  scheduleNearbyWritingPromptImagePreload,
} = writingPromptImagePreloader;

const writingPromptPickerController = window.IELTSWritingPromptPicker?.createWritingPromptPickerController?.({
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
  eagerImageCount: WRITING_PROMPT_PICKER_EAGER_IMAGE_COUNT,
});
if (!writingPromptPickerController) {
  throw new Error("IELTSWritingPromptPicker module failed to initialize.");
}

const corpusMarkdownEditorController = window.IELTSCorpusMarkdownEditor?.createCorpusMarkdownEditorController?.({
  state,
  $,
  prefetchCanApply,
  vditorCssUrl: "https://cdn.jsdelivr.net/npm/vditor/dist/index.css",
  vditorScriptUrl: "https://cdn.jsdelivr.net/npm/vditor/dist/index.min.js",
});
if (!corpusMarkdownEditorController) {
  throw new Error("IELTSCorpusMarkdownEditor module failed to initialize.");
}

const realtimePcmUplinkController = window.IELTSRealtimePcmUplink?.createRealtimePcmUplinkController?.({
  state,
  isActivePracticeSession,
  setDictationStatus,
  setRealtimePcmStatus,
});
if (!realtimePcmUplinkController) {
  throw new Error("IELTSRealtimePcmUplink module failed to initialize.");
}

const speakingAudioPreprocessorRuntime = window.IELTSSpeakingAudioPreprocessorRuntime?.createSpeakingAudioPreprocessorRuntime?.({
  state,
  isActivePracticeSession,
  startRealtimePcmUplink,
  stopRealtimePcmUplink,
});
if (!speakingAudioPreprocessorRuntime) {
  throw new Error("IELTSSpeakingAudioPreprocessorRuntime module failed to initialize.");
}

const corpusTakeawayController = window.IELTSCorpusTakeaway?.createCorpusTakeawayController?.({
  state,
  $,
  text,
  escapeHtml,
  renderMarkdown,
  renderSpokenAnswerMarkdown,
  fetchP1CorpusPayload,
  applyP1CorpusPayload,
  fetchP2CorpusPayload,
  applyP2CorpusPayload,
  fetchLanguageTakeawaysPayload,
  applyLanguageTakeawaysPayload,
  fetchWritingTakeawaysPayload,
  applyWritingTakeawaysPayload,
  p1CorpusTargetForTurn,
  api,
  showConfirmDelete,
  switchView,
  startPractice,
  openCorpusWindow,
  renderP2CorpusPrepPanel,
  ensureCorpusMarkdownEditorReady,
  getCorpusMarkdownValue,
  isCorpusEditorReady,
  setCorpusEditorLoading,
  setCorpusMarkdownValue,
  getCsrfToken,
  viewCopy,
  corpusPeekWindowMargin: CORPUS_PEEK_WINDOW_MARGIN,
});
if (!corpusTakeawayController) {
  throw new Error("IELTSCorpusTakeaway module failed to initialize.");
}

const spellingDrillController = window.IELTSSpellingDrill?.createSpellingDrillController?.({
  state,
  $,
  escapeHtml,
  api,
  showConfirmDelete,
});
if (!spellingDrillController) {
  throw new Error("IELTSSpellingDrill module failed to initialize.");
}

function prefetchCanApply(token) {
  return state.account.authenticated && state.prefetch.token === token;
}

function clearUserScopedCaches() {
  state.historyItems = [];
  state.historyDetailCache.clear();
  state.historyDetailPromises.clear();
  state.activeHistoryId = null;
  state.languageTakeaway.items = [];
  state.languageTakeaway.loaded = false;
  state.languageTakeaway.loadingPromise = null;
  state.languageTakeaway.revealedEntryIds.clear();
  state.writingTakeaway.items = [];
  state.writingTakeaway.loaded = false;
  state.writingTakeaway.loadingPromise = null;
  state.writingTakeaway.revealedEntryIds.clear();
  state.spellingDrill._drillReady = false;  // force S() re-init on next visit
  state.spellingDrill.items = [];
  state.spellingDrill.stats = {};
  state.spellingDrill.loaded = false;
  state.spellingDrill.loadingPromise = null;
  state.spellingDrill.currentIndex = 0;
  state.spellingDrill.result = null;
  state.spellingDrill.hintLevel = 0;
  state.p1Corpus.topics = [];
  state.p1Corpus.loaded = false;
  state.p1Corpus.loadingPromise = null;
  state.p2Corpus.categories = [];
  state.p2Corpus.currentPart2Cards = [];
  state.p2Corpus.loaded = false;
  state.p2Corpus.loadingPromise = null;
  state.writing.reportEntries = [];
  state.writing.activeReportId = null;
  state.writing.activeReportDetail = null;
  state.writing.reportDetailCache.clear();
  state.writing.reportDetailPromises.clear();
  state.writing.scoreCompletionModalEntry = null;
  state.writing.scoreCompletionNotifiedIds.clear();
  state.writing.promptLoadingPromises = {};
  state.writing.promptImagePreloads.clear();
  state.writing.promptImagePreloadPromises.clear();
  state.writing.promptImagePreloadQueue = [];
  state.writing.promptImagePreloadQueued.clear();
  state.writing.promptImagePreloadActive = 0;
  state.writing.promptImagePreloadScheduled = false;
  state.speaking.pendingAnalysis = null;
  state.speaking.pendingTurnCompletions.clear();
  state.speaking.turnCompletionErrors.clear();
  state.speaking.scoreCompletionModalAttempt = null;
  state.speaking.scoreCompletionNotifiedIds.clear();
  state.prefetch.started = false;
  state.prefetch.token += 1;
  state.prefetch.fixedExaminerTtsWarmed = false;
  state.prefetch.fixedExaminerTtsPromise = null;
  state.prefetch.corpusEditorWarmPromise = null;
  state.p3PracticeSource = null;
}

function scheduleAuthenticatedPrefetch() {
  if (!state.account.authenticated || state.prefetch.started) return;
  state.prefetch.started = true;
  state.prefetch.token += 1;
  const token = state.prefetch.token;
  prefetchFixedExaminerTts(token);
  scheduleIdleTask(() => prefetchSpeakingHistory(token), 550);
  scheduleIdleTask(() => prefetchWritingReports(token), 1300);
  scheduleIdleTask(() => prefetchLanguageTakeaways(token), 1800);
  scheduleIdleTask(() => prefetchWritingTakeaways(token), 1800);
  scheduleIdleTask(() => prefetchSpellingDrill(token), 2200);
  scheduleIdleTask(() => prefetchP1Corpus(token), 4200);
  scheduleIdleTask(() => prefetchP2Corpus(token), 5400);
  scheduleIdleTask(() => prefetchCorpusEditor(token), 6500);
  scheduleIdleTask(() => prefetchWritingPrompts(token), 8200);
}

function normalizeQuestionBankScope(scope) {
  const value = String(scope || "").trim().toLowerCase();
  return QUESTION_BANK_SCOPES.has(value) ? value : "current";
}

function loadStoredQuestionBankScope() {
  try {
    state.account.questionBankScope = normalizeQuestionBankScope(localStorage.getItem(QUESTION_BANK_SCOPE_STORAGE_KEY));
  } catch (_error) {
    state.account.questionBankScope = "current";
  }
}

function questionBankScopeQuery() {
  return `scope=${encodeURIComponent(normalizeQuestionBankScope(state.account.questionBankScope))}`;
}

function clearQuestionBankScopedCaches() {
  state.p1Corpus.topics = [];
  state.p1Corpus.loaded = false;
  state.p1Corpus.loadingPromise = null;
  state.p2Corpus.categories = [];
  state.p2Corpus.currentPart2Cards = [];
  state.p2Corpus.loaded = false;
  state.p2Corpus.loadingPromise = null;
}

async function loadQuestionBankSummary(options = {}) {
  const scope = normalizeQuestionBankScope(options.scope || state.account.questionBankScope);
  if (!options.force && state.account.questionBankSummary?.active_scope === scope) {
    return state.account.questionBankSummary;
  }
  if (!state.account.questionBankLoadingPromise || state.account.questionBankLoadingScope !== scope) {
    state.account.questionBankLoadingScope = scope;
    state.account.questionBankLoadingPromise = api(`/api/question-bank/summary?scope=${encodeURIComponent(scope)}`)
      .then((summary) => {
        state.account.questionBankSummary = summary;
        return summary;
      })
      .finally(() => {
        state.account.questionBankLoadingPromise = null;
        state.account.questionBankLoadingScope = "";
      });
  }
  return state.account.questionBankLoadingPromise;
}

async function fetchFixedExaminerTtsWarmup() {
  if (!state.prefetch.fixedExaminerTtsPromise) {
    state.prefetch.fixedExaminerTtsPromise = api("/api/tts/warmup", {}).finally(() => {
      state.prefetch.fixedExaminerTtsPromise = null;
    });
  }
  return state.prefetch.fixedExaminerTtsPromise;
}

async function prefetchFixedExaminerTts(token) {
  if (state.prefetch.fixedExaminerTtsWarmed) return;
  const payload = await fetchFixedExaminerTtsWarmup();
  if (!prefetchCanApply(token)) return;
  traceExaminerAudio("warmup:fixed-tts-ready", {
    count: (payload.audio_urls || []).length,
  });
  state.prefetch.fixedExaminerTtsWarmed = true;
}

function warmFixedExaminerTtsNow() {
  if (!state.account.authenticated) return;
  const token = state.prefetch.token;
  prefetchFixedExaminerTts(token).catch(() => null);
}

async function fetchP1CorpusPayload(options = {}) {
  const scope = options.scope ? normalizeQuestionBankScope(options.scope) : "";
  if (scope && scope !== normalizeQuestionBankScope(state.account.questionBankScope)) {
    return api(`/api/p1-corpus?scope=${encodeURIComponent(scope)}`);
  }
  if (!state.p1Corpus.loadingPromise) {
    state.p1Corpus.loadingPromise = api(`/api/p1-corpus?${questionBankScopeQuery()}`).finally(() => {
      state.p1Corpus.loadingPromise = null;
    });
  }
  return state.p1Corpus.loadingPromise;
}

async function fetchP2CorpusPayload(options = {}) {
  if (options.force) state.p2Corpus.loadingPromise = null;
  if (!state.p2Corpus.loadingPromise) {
    state.p2Corpus.loadingPromise = api(`/api/p2-corpus?${questionBankScopeQuery()}`).finally(() => {
      state.p2Corpus.loadingPromise = null;
    });
  }
  return state.p2Corpus.loadingPromise;
}

function applyP1CorpusPayload(payload) {
  state.p1Corpus.topics = payload.topics || [];
  state.p1Corpus.loaded = true;
  const stats = $("p1CorpusStats");
  if (stats) {
    const season = payload.active_season ? `${payload.active_season.replace(/-/g, " ")} · ` : "";
    const scope = payload.active_scope_label ? `${payload.active_scope_label} · ` : "";
    stats.textContent = `${season}${scope}${payload.topic_count || state.p1Corpus.topics.length} 个话题 · ${payload.question_count || 0} 道题 · 已保存 ${payload.saved_count || 0}`;
  }
  if (state.view === "p1Corpus") renderP1CorpusTopics();
  updateP1CorpusPeekButton(state.currentTurn);
}

function applyP2CorpusPayload(payload) {
  state.p2Corpus.categories = payload.categories || [];
  state.p2Corpus.currentPart2Cards = payload.current_part2_cards || [];
  state.p2Corpus.loaded = true;
  const stats = $("p2CorpusStats");
  if (stats) {
    const season = payload.active_season ? `${payload.active_season.replace(/-/g, " ")} · ` : "";
    const scope = payload.active_scope_label ? `${payload.active_scope_label} · ` : "";
    stats.textContent = `${season}${scope}${payload.current_part2_count || 0} 道 P2 题 · ${payload.category_count || 5} 个素材分类 · 已保存 ${payload.material_count || 0}`;
  }
  if (state.view === "p2Corpus") renderP2CorpusTopics();
  renderP2CorpusPrepPanel();
  updateP2CorpusPeekButton(state.currentTurn);
  updateP3CorpusPeekButton(state.currentTurn);
}

async function prefetchP1Corpus(token) {
  const payload = await fetchP1CorpusPayload();
  if (!prefetchCanApply(token)) return;
  applyP1CorpusPayload(payload);
}

async function prefetchP2Corpus(token) {
  const payload = await fetchP2CorpusPayload();
  if (!prefetchCanApply(token)) return;
  applyP2CorpusPayload(payload);
}

async function prefetchLanguageTakeaways(token) {
  const payload = await fetchLanguageTakeawaysPayload();
  if (!prefetchCanApply(token)) return;
  applyLanguageTakeawaysPayload(payload);
  updateTakeawayReviewDots();
  if (state.view === "takeawayBook") {
    const stats = $("languageTakeawayStats");
    if (stats) stats.textContent = `${payload.count || 0} 条`;
    renderLanguageTakeawayToggle();
    renderLanguageTakeaways();
  }
}

async function fetchLanguageTakeawaysPayload() {
  if (!state.languageTakeaway.loadingPromise) {
    state.languageTakeaway.loadingPromise = api("/api/language-takeaways")
      .finally(() => {
        state.languageTakeaway.loadingPromise = null;
      });
  }
  return state.languageTakeaway.loadingPromise;
}

function applyLanguageTakeawaysPayload(payload) {
  state.languageTakeaway.items = payload.items || [];
  state.languageTakeaway.loaded = true;
  updateTakeawayReviewDots();
}

async function prefetchSpeakingHistory(token) {
  const payload = await api("/api/history");
  if (!prefetchCanApply(token)) return;
  const items = payload.items || [];
  state.historyItems = items;
  const activeId = state.activeHistoryId && items.some((item) => item.id === state.activeHistoryId)
    ? state.activeHistoryId
    : items[0]?.id;
  if (activeId && !state.historyDetailCache.has(activeId)) {
    const detail = await fetchHistoryDetail(activeId);
    if (prefetchCanApply(token)) state.historyDetailCache.set(activeId, detail);
  }
}

async function prefetchWritingReports(token) {
  const payload = await api("/api/writing/reports");
  if (!prefetchCanApply(token)) return;
  const items = payload.items || [];
  state.writing.reportEntries = items;
  const activeId = state.writing.activeReportId && items.some((item) => item.id === state.writing.activeReportId)
    ? state.writing.activeReportId
    : items[0]?.id;
  if (activeId && !state.writing.reportDetailCache.has(activeId)) {
    const detail = await fetchWritingReportDetail(activeId);
    if (prefetchCanApply(token)) state.writing.reportDetailCache.set(activeId, detail);
  }
}

async function prefetchCorpusEditor(token) {
  return corpusMarkdownEditorController.prefetchCorpusEditor(token);
}

function ensureCorpusMarkdownEditorReady(textareaId) {
  return corpusMarkdownEditorController.ensureCorpusMarkdownEditorReady(textareaId);
}

function guestVisibleView(view) {
  return isKnownView(view) && !authViews.has(view) && !protectedViews.has(view) ? view : null;
}

function lastGuestVisibleHistoryView() {
  for (let index = state.viewHistory.length - 1; index >= 0; index -= 1) {
    const view = guestVisibleView(state.viewHistory[index]);
    if (view) return view;
  }
  return null;
}

function authSourceView(candidate) {
  return guestVisibleView(candidate)
    || guestVisibleView(state.view)
    || guestVisibleView(state.account.fromView)
    || lastGuestVisibleHistoryView()
    || "home";
}

function rememberAuthSource(candidate) {
  state.account.fromView = authSourceView(candidate);
}

function setWritingActionPanelCollapsed(collapsed) {
  const panel = $("writingActionPanel");
  const toggle = $("writingActionPanelToggle");
  if (!panel || !toggle) return;
  panel.classList.toggle("is-collapsed", collapsed);
  toggle.setAttribute("aria-expanded", String(!collapsed));
  toggle.setAttribute("aria-label", collapsed ? "展开评分操作" : "折叠评分操作");
}

function switchView(view, options = {}) {
  if (!isKnownView(view)) view = "home";
  if (protectedViews.has(view) && !state.account.authenticated && !options.skipAuthGate) {
    state.account.returnView = view;
    rememberAuthSource(options.fromView);
    switchView("login", {
      force: true,
      skipAuthGate: true,
      fromView: state.account.fromView,
      authMessage: options.authMessage || loginReasonForView(view),
    });
    return;
  }
  if (view === "p1Corpus") {
    state.p1Corpus.previousPracticeView = isPracticeView(state.view) ? state.view : "p1";
  }
  if (view === "p2Corpus") {
    state.p2Corpus.previousPracticeView = isPracticeView(state.view) ? state.view : "p2";
  }
  if (authViews.has(view) && !options.skipHistory) {
    rememberAuthSource(options.fromView);
  } else if (accountViews.has(view) && !options.skipHistory) {
    const sourceView = options.fromView || state.view;
    if (sourceView && !accountViews.has(sourceView) && !authViews.has(sourceView)) {
      state.account.fromView = sourceView;
    }
  }
  if (view === state.view && !options.force) return;
  if (state.practiceLocked && isPracticeView(state.view) && accountViews.has(view) && options.preservePractice) {
    showPracticeOverlay(view);
    return;
  }
  const shouldTrackHistory = !options.skipHistory && !authViews.has(view);
  if (shouldTrackHistory) {
    const currentView = state.view;
    if (currentView && currentView !== view && !authViews.has(currentView)) {
      const lastHistoryView = state.viewHistory[state.viewHistory.length - 1];
      if (lastHistoryView !== currentView) state.viewHistory.push(currentView);
      if (state.viewHistory.length > 8) state.viewHistory.shift();
    }
  }
  stopAllRuntime("Ready");
  hideWritingHighlightMenu();
  if (view === "p3" && !options.keepP3Source) {
    state.p3PracticeSource = null;
    state.p3CorpusSourceEntryId = "";
    state.p3SourceType = "bank";
    state.p3Plan = null;
  }
  state.view = view;
  state.practiceViewBeforeSettings = null;
  if (!options.skipUrl) updateViewUrl(view, { replace: Boolean(options.replaceUrl) });
  if (!options.skipPersist) {
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, view);
    } catch (e) {
      // Ignore storage errors
    }
  }
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
    button.classList.toggle("tone-mock", button.dataset.view === "mock");
    button.classList.toggle("tone-p1", button.dataset.view === "p1");
    button.classList.toggle("tone-p2", button.dataset.view === "p2");
    button.classList.toggle("tone-p3", button.dataset.view === "p3");
  });
  $(".shell")?.classList.toggle("auth-shell", authViews.has(view));
  document.body.classList.toggle("view-home", view === "home");
  document.body.classList.toggle("view-writing", view === "writing");
  document.body.classList.toggle("view-takeawayBook", view === "takeawayBook");
  document.body.classList.toggle("view-writingTakeawayBook", view === "writingTakeawayBook");
  $(".shell")?.classList.toggle("account-shell", accountViews.has(view));
  $(".workspace")?.classList.toggle("corpus-workspace", corpusViews.has(view));
  $("#topbarBackCorpusBtn")?.classList.toggle("hidden", !corpusBackButtonViews.has(view));
  $("#accountBackBtn")?.classList.toggle("hidden", !accountViews.has(view));
  $("#homePanel")?.classList.toggle("hidden", view !== "home");
  $("#practicePanel").classList.toggle("hidden", !isPracticeView(view));
  $("#practicePanel")?.classList.toggle("p3-launch-mode", view === "p3" && !state.practiceLocked);
  $("#corpusPanel")?.classList.toggle("hidden", view !== "corpus");
  $("#p1CorpusPanel")?.classList.toggle("hidden", view !== "p1Corpus");
  $("#p2CorpusPanel")?.classList.toggle("hidden", view !== "p2Corpus");
  $("#takeawayBookPanel")?.classList.toggle("hidden", view !== "takeawayBook");
  $("#writingTakeawayBookPanel")?.classList.toggle("hidden", view !== "writingTakeawayBook");
  $("#languageTakeawayReviewPanel")?.classList.toggle("hidden", view !== "takeawayBook");
  $("#writingTakeawayReviewPanel")?.classList.toggle("hidden", view !== "writingTakeawayBook");
  $("#spellingDrillPanel")?.classList.toggle("hidden", view !== "spellingDrill");
  $("#historyPanel").classList.toggle("hidden", view !== "history");
  $("#writingPanel")?.classList.toggle("hidden", view !== "writing");
  $("#writingReportsPanel")?.classList.toggle("hidden", view !== "writingReports");
  $("#loginPanel")?.classList.toggle("hidden", view !== "login");
  $("#authRequiredPanel")?.classList.toggle("hidden", true);
  $("#registerPanel")?.classList.toggle("hidden", view !== "register");
  $("#forgotPasswordPanel")?.classList.toggle("hidden", view !== "forgotPassword");
  $("#accountProfilePanel")?.classList.toggle("hidden", view !== "accountProfile");
  $("#accountSecurityPanel")?.classList.toggle("hidden", view !== "accountSecurity");
  $(".workspace").classList.toggle("history-workspace", view === "history" || view === "writingReports");
  $(".workspace").classList.toggle("writing-workspace", view === "writing");
  const hideWorkspaceHeader = workspaceHeaderHiddenViews.has(view);
  $(".topbar").classList.toggle("hidden", hideWorkspaceHeader);
  $("#viewTitleBlock").classList.toggle("hidden", hideWorkspaceHeader);
  $("#writingTopbarActions")?.classList.toggle("hidden", view !== "writing");
  const currentViewCopy = viewCopyFor(view);
  text("viewTitle", currentViewCopy[0]);
  text("viewSubtitle", currentViewCopy[1]);
  if (view === "history") loadHistory();
  if (view === "corpus") loadCorpusHome();
  if (view === "takeawayBook") loadLanguageTakeaways();
  if (view === "writingTakeawayBook") loadWritingTakeaways();
  if (view === "spellingDrill") loadSpellingDrill();
  if (view === "writing") {
    setWritingActionPanelCollapsed(false);
    loadWriting();
  }
  if (view === "writingReports") loadWritingReports();
  if (view === "p1Corpus") loadP1Corpus();
  if (view === "p2Corpus") loadP2Corpus({ force: true });
  if (view === "accountProfile") loadAccountProfile();
  if (view === "accountSecurity") loadAccount();
  if (view !== "accountSecurity") $("#accountSecurityPanel")?.classList.add("hidden");
  if (view === "login") prepareLoginView(options.authMessage || "");
  if (view === "forgotPassword") loadPasswordResetAvailability();
  $("#openP1CorpusBtn")?.classList.toggle("hidden", view !== "p1");
  $("#openP2CorpusBtn")?.classList.toggle("hidden", view !== "p2");
  if (view !== "p2") {
    closeP2CorpusPeek();
    updateP2CorpusPeekButton(null);
  }
  if (view !== "p3") {
    closeP3CorpusPeek();
    updateP3CorpusPeekButton(null);
  }
  if (view === "p3") syncP3LaunchPanel();
  $("#examStatusText")?.classList.remove("hidden");
  $("#exitPractice")?.classList.toggle("hidden", !state.practiceLocked || !isPracticeView(view));
  updateAgentAssistantVisibility(view);
  if (isPracticeView(view)) {
    if (hasPendingSpeakingAnalysisForView(view)) {
      restorePendingSpeakingAnalysisView(view);
    } else {
      resetPracticeSurface();
    }
  }
  updateSidebarLock();
}


function updateAgentAssistantVisibility(view = state.view) {
  const button = $("agentAssistantBtn");
  if (!button) return;
  const visible = agentAssistantViews.has(view) && !authViews.has(view) && !accountViews.has(view);
  button.classList.toggle("hidden", !visible);
  button.setAttribute("aria-hidden", visible ? "false" : "true");
  button.tabIndex = visible ? 0 : -1;
  if (!visible) closeAgentAssistant();
}


async function prefetchWritingTakeaways(token) {
  const payload = await fetchWritingTakeawaysPayload();
  if (!prefetchCanApply(token)) return;
  applyWritingTakeawaysPayload(payload);
  if (state.view === "writingTakeawayBook") {
    renderWritingTakeawayToggle();
    renderWritingTakeaways();
    text("writingTakeawayStats", `${payload.count || 0} 条`);
  }
}

async function fetchWritingTakeawaysPayload() {
  if (!state.writingTakeaway.loadingPromise) {
    state.writingTakeaway.loadingPromise = api("/api/writing-takeaways")
      .finally(() => {
        state.writingTakeaway.loadingPromise = null;
      });
  }
  return state.writingTakeaway.loadingPromise;
}

function applyWritingTakeawaysPayload(payload) {
  state.writingTakeaway.items = payload.items || [];
  state.writingTakeaway.loaded = true;
  updateTakeawayReviewDots();
}

function updateSpellingDrillDueDot(stats = state.spellingDrill?.stats || {}) {
  const due = Number(stats?.due || 0);
  const dot = $("spellingDrillDueDot");
  if (!dot) return;
  dot.classList.toggle("hidden", due <= 0);
  dot.setAttribute("data-count", String(due));
}

async function prefetchSpellingDrill(token) {
  const payload = await api("/api/writing/spelling-words?scope=due");
  if (!prefetchCanApply(token)) return;
  state.spellingDrill.items = payload.items || [];
  state.spellingDrill.stats = payload.stats || {};
  state.spellingDrill.loaded = true;
  updateSpellingDrillDueDot(payload.stats || {});
}

async function fetchHistoryDetail(attemptId) {
  const id = String(attemptId || "").trim();
  if (!id) return null;
  if (state.historyDetailCache.has(id)) return state.historyDetailCache.get(id);
  if (!state.historyDetailPromises.has(id)) {
    state.historyDetailPromises.set(id, api(`/api/history/${encodeURIComponent(id)}`)
      .then((detail) => {
        state.historyDetailCache.set(id, detail);
        return detail;
      })
      .finally(() => {
        state.historyDetailPromises.delete(id);
      }));
  }
  return state.historyDetailPromises.get(id);
}

async function fetchWritingReportDetail(entryId) {
  const id = String(entryId || "").trim();
  if (!id) return null;
  if (state.writing.reportDetailCache.has(id)) return state.writing.reportDetailCache.get(id);
  if (!state.writing.reportDetailPromises.has(id)) {
    state.writing.reportDetailPromises.set(id, api(`/api/writing/entries/${encodeURIComponent(id)}`)
      .then((entry) => {
        state.writing.reportDetailCache.set(id, entry);
        return entry;
      })
      .finally(() => {
        state.writing.reportDetailPromises.delete(id);
      }));
  }
  return state.writing.reportDetailPromises.get(id);
}

function isWritingEntryScored(entry = {}) {
  return entry?.status === "scored" && Boolean(entry?.score);
}

function applyRouteState(route) {
  if (route.speakingReportId) state.activeHistoryId = route.speakingReportId;
  if (route.writingReportId) state.writing.activeReportId = route.writingReportId;
  if (isKnownWritingTaskType(route.writingTask)) state.writing.taskType = route.writingTask;
  state.writing.requestedPromptId = route.writingPromptId || "";
  state.writing.requestedEntryId = route.writingEntryId || "";
}

function restoreRouteFromLocation() {
  const route = requestedRouteState();
  applyRouteState(route);
  state.routeApplying = true;
  try {
    switchView(route.view || "home", { force: true, skipPersist: true, skipUrl: true });
  } finally {
    state.routeApplying = false;
  }
}

function openCorpusWindow(view) {
  if (!isStandaloneCorpusView(view)) return;
  const url = new URL(window.location.href);
  url.searchParams.set("view", view);
  const opened = window.open(url.toString(), "_blank");
  if (opened) opened.opener = null;
}

function closeCorpusWindowOrReturn() {
  if (!$("p1CorpusDialog")?.classList.contains("hidden")) {
    saveAndCloseP1CorpusEditor().catch(() => null);
  }
  if (!$("p2CorpusDialog")?.classList.contains("hidden")) {
    saveAndCloseP2CorpusEditor().catch(() => null);
  }
  if (!$("p2CorpusP3Dialog")?.classList.contains("hidden")) {
    saveAndCloseP2CorpusP3Editor().catch(() => null);
  }
  hideLanguageTakeawayPopup();
  hideLanguageTakeawayTrigger();
  if (requestedStandaloneView() && window.opener) {
    window.close();
    return;
  }
  switchView("corpus", { force: true, skipHistory: true });
}

async function exitPracticeAndSwitch(view) {
  await exitPractice();
  switchView(view, { force: true });
}

function loginReasonForView(view) {
  const reasons = {
    history: "登录后才能查看你的口语报告和历史记录。",
    corpus: "登录后才能保存和管理你的语料库。",
    p1Corpus: "登录后才能保存和复用你的 P1 语料库。",
    p2Corpus: "登录后才能保存和复用你的 P2 串题素材库。",
    takeawayBook: "登录后才能查看和复习你的 Takeaway。",
    writing: "登录后才能保存每日写作、签到和 AI 评分记录。",
    writingReports: "登录后才能查看你的写作报告。",
    accountProfile: "请先登录后管理账号资料。",
    accountSecurity: "请先登录后修改账号安全设置。",
  };
  return reasons[view] || "请先登录后继续。";
}

function prepareLoginView(message = "") {
  const notice = $("loginNotice");
  if (notice) {
    notice.textContent = message || "登录后继续使用报告、钱包和个性化训练。";
    notice.classList.toggle("auth-notice-emphasis", Boolean(message));
  }
  const status = $("loginStatus");
  if (status) {
    status.textContent = "";
    status.classList.remove("error");
  }
}

function accountErrorMessage(error, fallback = "操作失败") {
  const errors = error?.errors || error?.payload?.errors || {};
  const messages = Object.values(errors)
    .flatMap((value) => Array.isArray(value) ? value : [value])
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  const raw = messages[0] || error?.message || fallback;
  const translations = {
    "Login failed": "登录失败",
    "Invalid username or password": "用户名或密码不正确。",
    "Username and password are required": "请输入账号和密码。",
    "Registration failed": "注册失败",
    "Password change failed": "修改密码失败",
    "Please enter username and password.": "请输入账号和密码。",
  };
  return translations[raw] || raw;
}

function showPracticeOverlay(view = "accountProfile") {
  const practiceView = isPracticeView(state.view) ? state.view : (state.practiceViewBeforeSettings || "mock");
  state.practiceViewBeforeSettings = practiceView;
  state.view = view;
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.remove("active");
    button.classList.toggle("tone-mock", button.dataset.view === "mock");
    button.classList.toggle("tone-p1", button.dataset.view === "p1");
    button.classList.toggle("tone-p2", button.dataset.view === "p2");
    button.classList.toggle("tone-p3", button.dataset.view === "p3");
  });
  $("#practicePanel").classList.add("hidden");
  $("#historyPanel").classList.add("hidden");
  $("#writingPanel")?.classList.add("hidden");
  $("#writingReportsPanel")?.classList.add("hidden");
  $("#loginPanel")?.classList.add("hidden");
  $("#authRequiredPanel")?.classList.add("hidden");
  $("#registerPanel")?.classList.add("hidden");
  $("#forgotPasswordPanel")?.classList.add("hidden");
  $("#accountProfilePanel")?.classList.toggle("hidden", view !== "accountProfile");
  $("#accountSecurityPanel")?.classList.toggle("hidden", view !== "accountSecurity");
  $(".workspace").classList.remove("history-workspace", "writing-workspace");
  $(".topbar").classList.remove("hidden");
  $("#viewTitleBlock").classList.remove("hidden");
  text("viewTitle", viewTitleFor(view));
  text("viewSubtitle", viewSubtitleFor(view));
  if (view === "accountProfile") loadAccountProfile();
  if (view === "accountSecurity") loadAccount();
  updateAgentAssistantVisibility(view);
  updateSidebarLock();
}

function returnFromSettings() {
  const practiceView = state.practiceViewBeforeSettings || state.viewHistory.pop() || "mock";
  state.view = practiceView;
  state.practiceViewBeforeSettings = null;
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === practiceView);
    button.classList.toggle("tone-mock", button.dataset.view === "mock");
    button.classList.toggle("tone-p1", button.dataset.view === "p1");
    button.classList.toggle("tone-p2", button.dataset.view === "p2");
    button.classList.toggle("tone-p3", button.dataset.view === "p3");
  });
  $("#loginPanel")?.classList.add("hidden");
  $("#authRequiredPanel")?.classList.add("hidden");
  $("#registerPanel")?.classList.add("hidden");
  $("#forgotPasswordPanel")?.classList.add("hidden");
  $("#accountProfilePanel")?.classList.add("hidden");
  $("#accountSecurityPanel")?.classList.add("hidden");
  $("#practicePanel").classList.remove("hidden");
  $(".shell")?.classList.remove("auth-shell", "account-shell");
  text("viewTitle", viewTitleFor(practiceView));
  text("viewSubtitle", viewSubtitleFor(practiceView));
  updateAgentAssistantVisibility(practiceView);
  updateSidebarLock();
}

function returnToPreviousView() {
  if (authViews.has(state.view)) {
    const sourceView = authSourceView(state.account.fromView);
    state.account.returnView = null;
    state.account.fromView = null;
    switchView(sourceView, { force: true, skipHistory: true });
    return;
  }
  const lastView = state.account.fromView || state.viewHistory.pop() || state.practiceViewBeforeSettings || state.account.returnView || "home";
  if (accountViews.has(lastView)) {
    const fallback = state.viewHistory.pop() || "home";
    switchView(fallback, { force: true, skipHistory: true });
    return;
  }
  switchView(lastView, { force: true, skipHistory: true });
}

function resetPracticeSurface() {
  stopExaminerPlayback("reset-practice-surface");
  closeP1CorpusPeek();
  closeP2CorpusPeek();
  closeP3CorpusPeek();
  updateP1CorpusPeekButton(null);
  updateP2CorpusPeekButton(null);
  updateP3CorpusPeekButton(null);
  state.practiceLocked = false;
  state.status = "idle";
  state.attempt = null;
  state.currentTurn = null;
  state.examinerPlayback = null;
  state.activeExaminerAudioPlayer = null;
  state.transcript = "";
  state.speaking.realtimePcmMetrics = null;
  setRealtimePcmStatus({});
  state.speaking.pendingTurnCompletions.clear();
  state.speaking.turnCompletionErrors.clear();
  state.speaking.examinerTtsRefreshPromises.clear();
  clearExaminerAudioPreloads();
  const summaryPanel = $("#summaryPanel");
  const isPracticeMode = isPracticeView(state.view);
  $(".exam-status")?.classList.toggle("hidden", !isPracticeMode || state.view === "p3");
  $("#examStatusText")?.classList.toggle("hidden", state.view === "p2");
  $("#candidateAudio")?.classList.add("hidden");
  $("#browserTtsFallback")?.classList.add("hidden");
  const p2PrepPanel = $("#p2CorpusPrepPanel");
  p2PrepPanel?.classList.add("hidden");
  if (p2PrepPanel) p2PrepPanel.innerHTML = "";
  if (state.view !== "p2") state.p2Corpus.selectedEntryId = "";
  if (state.view !== "p3") {
    state.p3PracticeSource = null;
    state.p3Plan = null;
    state.p3PlanLoading = false;
  }
  $("#cueTop")?.classList.add("hidden");
  $("#promptPane")?.classList.remove("hidden");
  $("#p3TopicPanel")?.classList.toggle("hidden", !isPracticeMode || state.view !== "p3");
  $("#practicePanel")?.classList.toggle("p3-launch-mode", state.view === "p3");
  $("#practiceGrid")?.classList.remove("p2-mode", "practice-enter");
  $("#practiceGrid")?.classList.toggle("hidden", !isPracticeMode || state.view === "p3");
  if (state.view === "p3") {
    renderP3PlanPreview();
    syncP3LaunchPanel();
  }
  summaryPanel?.classList.add("hidden");
  if (summaryPanel) summaryPanel.innerHTML = "";
  $("#exitPractice")?.classList.add("hidden");
  updateSidebarLock();
  text("progressTrack", practiceReadyText(state.view));
  text("phaseLabel", "Ready");
  text("timerValue", "00:00");
  $("#phaseMeter").style.width = "0%";
  text("promptKicker", "Prompt");
  setPromptHtml("Start a voice practice session to load a question.", "short");
  text("followUp", "");
  setRecordButton("ready", "Start", "Record the full section. No typing.");
  text("recordStatus", "Click Start. The examiner will load the questions automatically.");
  $("#examStatusText")?.classList.toggle("hidden", state.view === "p2");
}

function hasPendingSpeakingAnalysisForView(view) {
  const pending = state.speaking.pendingAnalysis;
  return Boolean(pending?.attemptId && pending.view === view);
}

function restorePendingSpeakingAnalysisView(view = state.view) {
  const pending = state.speaking.pendingAnalysis;
  if (!pending?.attemptId) return;
  state.attempt = pending.attempt || state.attempt;
  state.currentTurn = null;
  state.practiceLocked = false;
  $(".exam-status")?.classList.remove("hidden");
  $("#examStatusText")?.classList.toggle("hidden", view === "p2");
  $("#candidateAudio")?.classList.add("hidden");
  $("#browserTtsFallback")?.classList.add("hidden");
  $("#cueTop")?.classList.add("hidden");
  $("#promptPane")?.classList.remove("hidden");
  $("#p3TopicPanel")?.classList.add("hidden");
  $("#practiceGrid")?.classList.remove("hidden", "practice-enter");
  $("#summaryPanel")?.classList.add("hidden");
  $("#exitPractice")?.classList.add("hidden");
  text("progressTrack", practiceReadyText(view));
  text("phaseLabel", "Analyzing");
  text("timerValue", "00:00");
  $("#phaseMeter").style.width = "100%";
  text("promptKicker", "Analysis");
  setPromptHtml("The full speaking section is being analyzed. You can keep navigating; the completion modal will appear when the report is ready.", "medium");
  text("followUp", "");
  setRecordButton("scoring", "Analyzing", "Analyzing the full section and generating the report.");
  text("recordStatus", "Analyzing the full section and generating the report.");
  updateSidebarLock();
}

function navigatePracticeMode(mode) {
  if (!isPracticeView(mode)) return;
  switchView(mode, { force: true });
}

function captureNavScrollState() {
  const nav = document.querySelector(".nav");
  if (!nav) return null;
  const maxScrollTop = Math.max(0, nav.scrollHeight - nav.clientHeight);
  return {
    top: nav.scrollTop,
    atBottom: maxScrollTop > 0 && nav.scrollTop >= maxScrollTop - 2,
  };
}

function restoreNavScrollState(snapshot) {
  if (!snapshot) return;
  const nav = document.querySelector(".nav");
  if (!nav) return;
  const apply = () => {
    const maxScrollTop = Math.max(0, nav.scrollHeight - nav.clientHeight);
    nav.scrollTop = snapshot.atBottom ? maxScrollTop : Math.min(snapshot.top, maxScrollTop);
  };
  apply();
  requestAnimationFrame(apply);
}

function setRecordButton(status, title, hint) {
  const navScroll = captureNavScrollState();
  state.status = status;
  $("#recordControl").className = `record-control ${status}`;
  $("#recordControl").disabled = isRecordControlDisabledStatus(status);
  text("recordTitle", title);
  text("recordHint", hint);
  // Timer color based on status
  const timerEl = $("#timerValue");
  timerEl?.classList.remove("timer-analyzing");
  // Analyzing dots
  const dotsEl = $("#analyzingDots");
  const isAnalyzing = status === "processing" || status === "scoring";
  dotsEl?.classList.toggle("hidden", !isAnalyzing);

  if (status === "preparing") {
    if (timerEl) timerEl.style.color = "#3b82f6"; // blue
  } else if (status === "recording") {
    if (timerEl) timerEl.style.color = "#ef4444"; // red
  } else if (isAnalyzing) {
    if (timerEl) {
      timerEl.style.color = "#d97706"; // amber
      timerEl.classList.add("timer-analyzing");
    }
  } else {
    if (timerEl) timerEl.style.color = "";
  }
  updateSidebarLock();
  restoreNavScrollState(navScroll);
}

function setPromptHtml(html, size = "medium") {
  $("#promptCard").className = `prompt-card ${size}-prompt`;
  $("#promptCard").innerHTML = html;
}

function promptSize(question) {
  const length = String(question || "").length;
  if (length < 90) return "short";
  if (length < 190) return "medium";
  return "long";
}

async function startPractice() {
  if (state.speaking.pendingAnalysis?.attemptId) return;
  if (state.status === "loading" || state.practiceLocked) return;
  stopExaminerPlayback("start-practice");
  state.speaking.pendingTurnCompletions.clear();
  state.speaking.turnCompletionErrors.clear();
  const requestId = state.startRequestId + 1;
  state.startRequestId = requestId;
  const sessionId = state.practiceSessionId + 1;
  state.practiceSessionId = sessionId;
  state.startAbortController?.abort();
  state.startAbortController = new AbortController();
  state.userExitedPractice = false;
  if (!state.account.authenticated) {
    state.account.returnView = state.view;
    switchView("login", {
      force: true,
      skipAuthGate: true,
      authMessage: "登录后才能开始练习并保存完整报告。",
    });
    return;
  }
  const mode = state.view === "mock" ? "mock" : state.view;
  if (mode === "p3" && !state.p3Plan) {
    await generateP3Plan();
    if (!state.p3Plan) return;
  }
  state.abortingAttemptId = null;
  state.practiceLocked = true;
  $(".exam-status")?.classList.remove("hidden");
  $("#examStatusText")?.classList.toggle("hidden", mode === "p2");
  $("#practiceGrid")?.classList.remove("hidden");
  $("#exitPractice").classList.remove("hidden");
  updateSidebarLock();
  setRecordButton("loading", "Loading...", "Checking account balance.");
  try {
    const wallet = await fetchWalletPayload({
      maxAgeMs: 60000,
      requestOptions: { signal: state.startAbortController.signal },
    });
    if (state.startRequestId !== requestId || state.practiceSessionId !== sessionId || state.abortingAttemptId === "__loading__") return;
    if (!walletAiStartAllowed(wallet)) {
      state.practiceLocked = false;
      $("#exitPractice")?.classList.add("hidden");
      updateSidebarLock();
      setRecordButton("idle", "Start", t("wallet.rechargeRequiredShort"));
      showInsufficientBalanceDialog(walletAiStartThreshold(wallet));
      switchView("accountProfile", { force: true });
      return;
    }
  } catch (error) {
    if (error?.name === "AbortError" || state.startRequestId !== requestId || state.practiceSessionId !== sessionId) return;
  }

  if (state.startRequestId !== requestId || state.practiceSessionId !== sessionId || state.abortingAttemptId === "__loading__") return;
  $(".exam-status")?.classList.remove("hidden");
  $("#examStatusText")?.classList.toggle("hidden", mode === "p2");
  $("#practiceGrid")?.classList.remove("hidden");
  $("#exitPractice").classList.remove("hidden");
  updateSidebarLock();
  if (mode === "p3") revealP3PracticeGrid();
  setRecordButton("loading", "Loading...", "Preparing exam section.");
  try {
    const p3Source = mode === "p3" ? state.p3PracticeSource : null;
    const p2PinnedCueId = mode === "p2" ? String(state.p2Corpus.pinnedCueId || "").trim() : "";
    const theme = mode === "p3" ? currentP3Theme() : "";
    const names = candidateNames();
    const attempt = await api("/api/attempts/start", {
      mode,
      question_bank_scope: normalizeQuestionBankScope(state.account.questionBankScope),
      candidate: names.englishName,
      full_name: names.fullName,
      english_name: names.englishName,
      ...(mode === "p2" && p2PinnedCueId ? { p2_cue_id: p2PinnedCueId } : {}),
      ...(mode === "p3" ? { p3_intensity: state.p3Intensity } : {}),
      ...(mode === "p3" ? { p3_focus: state.p3Focus } : {}),
      ...(mode === "p3" && state.p3Plan ? { p3_plan: state.p3Plan } : {}),
      ...(mode === "p3" && theme ? { theme } : {}),
      ...(mode === "p3" && p3Source?.answer ? { prior_answer: p3Source.answer } : {}),
      ...(mode === "p3" ? { source: p3Source?.sourceType || state.p3SourceType } : {}),
      ...(mode === "p3" && p3Source?.attemptId ? { p2_attempt_id: p3Source.attemptId } : {}),
      ...(mode === "p3" && p3Source?.p2CorpusEntryId ? { p2_corpus_entry_id: p3Source.p2CorpusEntryId } : {}),
      ...(mode === "p3" && p3Source?.p3FollowUpText ? { p3_follow_up_text: p3Source.p3FollowUpText } : {}),
      ...(mode === "p3" && p3Source?.p2QuestionId ? { p2_question_id: p3Source.p2QuestionId } : {}),
      ...(mode === "p3" && Array.isArray(p3Source?.p3FollowUps) && p3Source.p3FollowUps.length ? { p3_follow_ups: p3Source.p3FollowUps } : {}),
    }, { signal: state.startAbortController.signal });
    if (state.startRequestId !== requestId || state.practiceSessionId !== sessionId || state.abortingAttemptId === "__loading__") {
      if (attempt?.id) api(`/api/attempts/${attempt.id}/abort`, {}).catch(() => null);
      return;
    }
    if (mode === "p2") state.p2Corpus.pinnedCueId = "";
    state.attempt = attempt;
    state.currentTurn = attempt.turns[0];
    $("#summaryPanel").classList.add("hidden");
    renderTurn(state.currentTurn);
    beginExaminerPhase(sessionId);
  } catch (error) {
    if (error?.name === "AbortError" || state.startRequestId !== requestId || state.practiceSessionId !== sessionId) return;
    state.practiceLocked = false;
    $("#exitPractice")?.classList.add("hidden");
    updateSidebarLock();
    showError(error);
  }
}

function revealP3PracticeGrid() {
  $("#p3TopicPanel").classList.add("hidden");
  $("#practicePanel")?.classList.remove("p3-launch-mode");
  const grid = $("#practiceGrid");
  grid.classList.remove("hidden", "practice-enter");
  void grid.offsetWidth;
  grid.classList.add("practice-enter");
}

function renderTurn(turn) {
  if (!turn) return;
  if (state.status === "examiner_playing") {
    traceExaminerAudio("render-turn-during-playback", {
      renderTurnId: turn.id || "",
      currentTurnId: state.currentTurn?.id || "",
      playbackTurnId: state.examinerPlayback?.turnId || "",
      activePlayer: examinerPlayerSnapshot(state.activeExaminerAudioPlayer),
    });
  }
  const isP2 = turn.part === "p2";
  const isFollowUp = turn.prompt?.role === "follow_up";
  const isIntro = turn.counts_toward_total === false;
  if (turn.part === "p3") $("p3TopicPanel").classList.add("hidden");
  text("progressTrack", practiceReadyText(state.view));
  text("phaseLabel", turnProgressLabel(turn));
  text("promptKicker", isP2 ? "Cue card" : (isIntro ? "Intro" : "Question"));
  text("followUp", "");
  $("practiceGrid").classList.toggle("p2-mode", isP2);
  $("cueTop").classList.add("hidden");
  $("promptPane").classList.remove("hidden");
  updateP1CorpusPeekButton(turn);
  updateP2CorpusPeekButton(turn);
  updateP3CorpusPeekButton(turn);
  renderExaminerAudio(turn);
  if (isP2 && turn.cue_card) {
    renderCueCardInPrompt(turn.cue_card);
    renderP2CorpusPrepPanel({
      sessionId: state.practiceSessionId,
      turnId: turn.id,
    });
    return;
  }
  $("p2CorpusPrepPanel")?.classList.add("hidden");
  if (isStreamFollowUpFailed(turn)) {
    setPromptHtml('<span class="prompt-followup-tag">Follow-up question</span><p>追问生成失败。点击下方按钮重新生成，不会重开整场练习。</p>', "short");
    text("recordStatus", "追问生成失败，可以重新生成。");
    return;
  }
  if (isWaitingForStreamedFollowUpText(turn)) {
    setPromptHtml('<span class="prompt-followup-tag">Follow-up question</span><p>正在生成追问...</p>', "short");
    text("recordStatus", "正在生成追问...");
    return;
  }
  setPromptHtml(`${isFollowUp ? '<span class="prompt-followup-tag">Follow-up question</span>' : ""}<p>${escapeHtml(turn.question)}</p>`, promptSize(turn.question));
}

function turnProgressLabel(turn) {
  if (!turn) return "";
  const part = String(turn.part || "").toUpperCase();
  const questionNumber = Number(turn.display_index ?? (Number(turn.index ?? 0) + 1));
  if (turn.prompt?.role === "follow_up") return `${part} -> Follow-up after Question ${questionNumber}/${turn.total}`;
  if (turn.counts_toward_total === false) return `${part} -> Intro`;
  return `${part} -> Question ${questionNumber}/${turn.total}`;
}

function cueCardHtml(cue) {
  const bullets = (cue.bullets || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `
    <h2>${escapeHtml(cue.title)}</h2>
    <p class="cue-label">You should say:</p>
    <ul>${bullets}</ul>
    <p>${escapeHtml(cue.rounding || "")}</p>
  `;
}

function renderCueCardInPrompt(cue) {
  setPromptHtml(cueCardHtml(cue), "cue");
}

async function renderP2CorpusPrepPanel(renderOptions = {}) {
  const panel = $("p2CorpusPrepPanel");
  const expectedSessionId = renderOptions.sessionId ?? state.practiceSessionId;
  const expectedTurnId = renderOptions.turnId ?? state.currentTurn?.id ?? "";
  const isCurrentP2Prep = () => {
    if (!panel || !state.practiceLocked || state.currentTurn?.part !== "p2") return false;
    if (expectedSessionId && state.practiceSessionId !== expectedSessionId) return false;
    if (expectedTurnId && state.currentTurn?.id !== expectedTurnId) return false;
    return true;
  };
  if (!isCurrentP2Prep()) {
    panel?.classList.add("hidden");
    if (panel) panel.innerHTML = "";
    return;
  }
  if (!(state.p2Corpus.categories || []).length) {
    try {
      const payload = await api(`/api/p2-corpus?${questionBankScopeQuery()}`);
      state.p2Corpus.categories = payload.categories || [];
      state.p2Corpus.currentPart2Cards = payload.current_part2_cards || [];
    } catch (_error) {
      state.p2Corpus.categories = [];
      state.p2Corpus.currentPart2Cards = [];
    }
  }
  if (!isCurrentP2Prep()) return;
  const options = [];
  const optionIds = new Set();
  for (const category of state.p2Corpus.categories || []) {
    for (const item of category.items || []) {
      if (optionIds.has(item.entry_id)) continue;
      optionIds.add(item.entry_id);
      options.push({ ...item, label: category.label || item.label || item.category });
    }
  }
  for (const item of state.p2Corpus.currentPart2Cards || []) {
    if (item.has_material || item.has_p3_follow_up) {
      if (optionIds.has(item.entry_id)) continue;
      optionIds.add(item.entry_id);
      options.push({ ...item, label: item.label || item.category });
    }
  }
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div>
      <strong>本次 P2 回答链接素材</strong>
      <span>AI 生成 7 分回答和辅导时会参考。</span>
    </div>
    <select id="p2CorpusPrepSelect" aria-label="本次 P2 回答链接素材">
      <option value="">不链接素材</option>
      ${options.map((item) => `<option value="${escapeHtml(item.entry_id)}"${item.entry_id === state.p2Corpus.selectedEntryId ? " selected" : ""}>${escapeHtml(item.label)} •「${escapeHtml(item.title)}」</option>`).join("")}
    </select>
  `;
  updateP2CorpusPeekButton(state.currentTurn);
  $("p2CorpusPrepSelect")?.addEventListener("change", (event) => {
    state.p2Corpus.selectedEntryId = event.target.value || "";
    updateP2CorpusPeekButton(state.currentTurn);
  });
}

function renderCueTop(cue) {
  const bullets = (cue.bullets || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  $("cueTop").classList.remove("hidden");
  $("cueTop").innerHTML = `
    <h2>${escapeHtml(cue.title)}</h2>
    <p class="cue-label">You should say:</p>
    <ul>${bullets}</ul>
    <p>${escapeHtml(cue.rounding || "")}</p>
  `;
}

function examinerAudioDebugEnabled() {
  const params = new URLSearchParams(window.location.search);
  if (params.has("audio_debug")) {
    const value = String(params.get("audio_debug") || "").toLowerCase();
    return !["0", "false", "off", "disabled"].includes(value);
  }
  return localStorage.getItem("ielts-examiner-audio-debug") === "1";
}

function traceExaminerAudio(event, details = {}) {
  if (examinerAudioDebugEnabled()) {
    const record = {
      event,
      at: Number(performance.now().toFixed(1)),
      sessionId: state.practiceSessionId,
      status: state.status,
      view: state.view,
      turnId: state.currentTurn?.id || "",
      ...details,
    };
    console.info("[examiner-audio]", event, record);
    return record;
  }
  return { event, ...details };
}

function exposeExaminerAudioDiagnostics() {
  window.__ieltsExaminerAudio = {
    current: () => state.activeExaminerAudioPlayer?.snapshot?.() || null,
    stop: () => stopExaminerPlayback("debug-stop"),
  };
  return window.__ieltsExaminerAudio;
}

function renderExaminerAudio(turn) {
  const tts = turn.examiner_tts || {};
  $("browserTtsFallback")?.classList.add("hidden");
  if (tts.audio_url) {
    traceExaminerAudio("render:prime-ready-url", {
      url: tts.audio_url,
      ttsStatus: tts.status || "",
    });
  } else if (
    isPendingExaminerTts(tts)
    && !shouldStreamFollowUpTurn(turn)
    && state.attempt?.id
    && state.practiceSessionId
  ) {
    traceExaminerAudio("render:refresh-pending-tts", {
      turnId: turn.id,
      ttsStatus: tts.status || "",
    });
    refreshPendingExaminerTts(turn, state.practiceSessionId).catch(() => null);
  }
}

function stableExaminerAudioUrl(url) {
  if (!url || !url.includes("/api/tts-audio/examiner/")) return url;
  try {
    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set("stable", "1");
    return parsed.pathname + parsed.search;
  } catch {
    return url.includes("?") ? `${url}&stable=1` : `${url}?stable=1`;
  }
}

function resolveExaminerAudioPlaybackSource(url) {
  if (!url) return null;
  const stableUrl = stableExaminerAudioUrl(url);
  traceExaminerAudio("playback-url:stable", { url, stableUrl });
  return { sourceUrl: url, playbackUrl: stableUrl, stableUrl, objectUrl: false };
}

function clearExaminerAudioPreloads() {
  for (const [url, item] of state.examinerAudioBlobUrls.entries()) {
    traceExaminerAudio("blob-audio:clear", { url, size: item.size, type: item.type });
    if (item.playbackUrl) URL.revokeObjectURL(item.playbackUrl);
  }
  state.examinerAudioBlobUrls.clear();
}

function examinerPlayerSnapshot(player = state.activeExaminerAudioPlayer) {
  if (!player) return {};
  return player.snapshot();
}

function inferHowlerFormat(url) {
  const path = String(url || "").split("?")[0].toLowerCase();
  if (path.endsWith(".mp3") || path.endsWith(".mpeg")) return ["mp3"];
  if (path.endsWith(".wav")) return ["wav"];
  if (path.endsWith(".m4a") || path.endsWith(".mp4") || path.endsWith(".aac")) return ["mp4"];
  if (path.endsWith(".ogg") || path.endsWith(".oga")) return ["ogg"];
  if (path.endsWith(".webm")) return ["webm"];
  return ["mp3"];
}

function normalizeHowlerError(error) {
  if (error instanceof Error) return error.message;
  if (error && typeof error === "object") return JSON.stringify(error);
  return String(error ?? "unknown error");
}

class ExaminerAudioPlayer {
  constructor() {
    this.howl = null;
    this.playId = null;
    this.source = null;
    this.status = "idle";
    this.loadTimer = null;
    this._loadReject = null;
    this._playResolve = null;
    this._playReject = null;
    this._onPlay = null;
  }

  load(source) {
    this.unload("load-new-source");
    this.source = source;
    this.status = "loading";
    const playbackUrl = source?.playbackUrl || "";
    const sourceUrl = source?.sourceUrl || playbackUrl;
    if (!playbackUrl) return Promise.reject(new Error("Missing examiner audio URL"));
    if (typeof window.Howl !== "function") return Promise.reject(new Error("Howler.js is not loaded"));

    traceExaminerAudio("howler:load-start", { url: sourceUrl, playbackUrl });
    return new Promise((resolve, reject) => {
      let settled = false;
      this._loadReject = reject;
      this.loadTimer = window.setTimeout(() => {
        this._fail("load", `Timed out loading examiner audio after ${EXAMINER_AUDIO_LOAD_TIMEOUT_MS}ms`);
      }, EXAMINER_AUDIO_LOAD_TIMEOUT_MS);
      const clearLoadTimeout = () => {
        if (this.loadTimer) window.clearTimeout(this.loadTimer);
        this.loadTimer = null;
      };
      const ready = () => {
        if (settled) return;
        settled = true;
        this._loadReject = null;
        clearLoadTimeout();
        this.status = "ready";
        traceExaminerAudio("howler:ready", { url: sourceUrl, playbackUrl, player: this.snapshot() });
        resolve(this);
      };
      const failLoad = (_id, error) => {
        if (settled) return;
        settled = true;
        clearLoadTimeout();
        const message = normalizeHowlerError(error);
        this._fail("load", message);
      };
      try {
        this.howl = new window.Howl({
          src: [playbackUrl],
          html5: true,
          preload: true,
          autoplay: false,
          format: inferHowlerFormat(playbackUrl),
          onload: ready,
          onloaderror: failLoad,
          onplay: (id) => {
            this.playId = id;
            this.status = "started";
            this._onPlay?.({ id, player: this, source });
          },
          onplayerror: (_id, error) => this._fail("play", error),
          onend: () => this._finish("ended"),
          onstop: () => this._finish("stopped"),
        });
      } catch (error) {
        clearLoadTimeout();
        settled = true;
        this.status = "failed";
        reject(error);
      }
    });
  }

  playToEnd({ onPlay } = {}) {
    if (!this.howl) return Promise.reject(new Error("Examiner audio is not loaded"));
    this._onPlay = onPlay || null;
    return new Promise((resolve, reject) => {
      this._playResolve = resolve;
      this._playReject = reject;
      try {
        this.playId = this.howl.play();
      } catch (error) {
        this._fail("play", error);
      }
    });
  }

  _finish(result) {
    if (!this._playResolve) return;
    this.status = result;
    const resolve = this._playResolve;
    this._playResolve = null;
    this._playReject = null;
    this._onPlay = null;
    resolve(result);
  }

  _fail(stage, error) {
    const message = normalizeHowlerError(error);
    this.status = "failed";
    traceExaminerAudio("howler:error", { stage, error: message, player: this.snapshot() });
    if (stage === "load" && this._loadReject) {
      const reject = this._loadReject;
      this._loadReject = null;
      reject(new Error(message));
      return;
    }
    if (this._playReject) {
      const reject = this._playReject;
      this._playResolve = null;
      this._playReject = null;
      this._onPlay = null;
      reject(new Error(message));
    }
  }

  stop(reason = "stop") {
    traceExaminerAudio("howler:stop", { reason, player: this.snapshot() });
    try {
      this.howl?.stop();
    } catch {
      // Ignore stop errors while Howler is unloading.
    }
    this._finish("stopped");
  }

  unload(reason = "unload") {
    this.stop(reason);
    if (this.howl) {
      traceExaminerAudio("howler:unload", { reason, player: this.snapshot() });
      try {
        this.howl.unload();
      } catch {
        // Ignore unload errors during teardown.
      }
    }
    if (this.loadTimer) window.clearTimeout(this.loadTimer);
    this.howl = null;
    this.playId = null;
    this.loadTimer = null;
    this._loadReject = null;
    this._playResolve = null;
    this._playReject = null;
    this._onPlay = null;
    this.status = "unloaded";
  }

  playing() {
    if (!this.howl) return false;
    try {
      return this.playId !== null ? this.howl.playing(this.playId) : this.howl.playing();
    } catch {
      return false;
    }
  }

  snapshot() {
    const howl = this.howl;
    let seek = 0;
    let duration = null;
    let howlerState = "unloaded";
    if (howl) {
      try {
        const currentSeek = howl.seek(this.playId ?? undefined);
        seek = Number.isFinite(currentSeek) ? Number(currentSeek.toFixed(3)) : 0;
      } catch {
        seek = 0;
      }
      try {
        const currentDuration = howl.duration(this.playId ?? undefined);
        duration = Number.isFinite(currentDuration) ? Number(currentDuration.toFixed(3)) : null;
      } catch {
        duration = null;
      }
      try {
        howlerState = howl.state();
      } catch {
        howlerState = "unknown";
      }
    }
    return {
      engine: "howler",
      url: this.source?.sourceUrl || "",
      playbackUrl: this.source?.playbackUrl || "",
      stableUrl: this.source?.stableUrl || "",
      state: this.status,
      howlerState,
      playId: this.playId ?? null,
      playing: this.playing(),
      currentTime: seek,
      duration,
    };
  }
}

function isCurrentExaminerPlayback(playback) {
  return Boolean(
    playback
    && state.examinerPlayback === playback
    && !playback.cancelled
    && isActivePracticeSession(playback.sessionId)
    && state.currentTurn?.id === playback.turnId
  );
}

function stopExaminerPlayback(reason = "stop-playback") {
  const playback = state.examinerPlayback;
  if (playback) {
    playback.cancelled = true;
    playback.promise = null;
  }
  const activePlayer = state.activeExaminerAudioPlayer;
  if (activePlayer) activePlayer.unload(reason);
  state.activeExaminerAudio = null;
  state.activeExaminerAudioPlayer = null;
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  state.browserTtsUtterance = null;
  state.examinerPlayback = null;
}

function localNextTurnAfter(turn, attempt = state.attempt) {
  if (!turn || !attempt) return null;
  const turns = attempt.turns || [];
  const currentIndex = turns.findIndex((item) => item.id === turn.id);
  if (currentIndex < 0) return null;
  return turns[currentIndex + 1] || null;
}

function isP3DynamicFollowUpBoundary(turn, nextTurn) {
  return turn?.part === "p3"
    && turn?.prompt?.role === "main"
    && nextTurn?.part === "p3"
    && nextTurn?.prompt?.role === "follow_up";
}

function turnRequiresSynchronousComplete(turn, nextTurn) {
  if (!nextTurn) return true;
  return isP1WorkStudyIdentityTurn(turn) || isP3DynamicFollowUpBoundary(turn, nextTurn);
}

function isPendingExaminerTts(tts) {
  return isPendingExaminerTtsStatus(tts?.status);
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function refreshPendingExaminerTts(turn, sessionId) {
  if (!turn || !state.attempt?.id || !isPendingExaminerTts(turn.examiner_tts)) return turn;
  const attemptId = state.attempt.id;
  const key = `${attemptId}:${turn.id}`;
  const existing = state.speaking.examinerTtsRefreshPromises.get(key);
  if (existing) {
    traceExaminerAudio("tts-refresh:reuse", { key, ttsStatus: turn.examiner_tts?.status || "" });
    return existing;
  }
  const refreshPromise = (async () => {
    traceExaminerAudio("tts-refresh:start", { key, ttsStatus: turn.examiner_tts?.status || "" });
    const deadline = Date.now() + EXAMINER_TTS_REFRESH_WAIT_MS;
    let delay = 0;
    while (Date.now() <= deadline && isActivePracticeSession(sessionId) && state.currentTurn?.id === turn.id) {
      if (delay > 0) await wait(delay);
      try {
        const payload = await api(`/api/attempts/${encodeURIComponent(attemptId)}/turns/${encodeURIComponent(turn.id)}/examiner-tts`);
        const refreshedTts = payload?.examiner_tts || null;
        if (refreshedTts) {
          traceExaminerAudio("tts-refresh:payload", {
            key,
            ttsStatus: refreshedTts.status || "",
            audioUrl: refreshedTts.audio_url || "",
            latencyMs: refreshedTts.refresh_latency_ms ?? null,
          });
          turn.examiner_tts = refreshedTts;
          if (state.currentTurn?.id === turn.id) {
            state.currentTurn = { ...state.currentTurn, examiner_tts: refreshedTts };
            state.attempt = mergeCompletedTurnPayload(state.attempt, { id: turn.id, examiner_tts: refreshedTts });
            renderExaminerAudio(state.currentTurn);
          }
          if (refreshedTts.audio_url) return state.currentTurn?.id === turn.id ? state.currentTurn : turn;
          if (!isPendingExaminerTts(refreshedTts)) return state.currentTurn?.id === turn.id ? state.currentTurn : turn;
        }
      } catch (_error) {
        traceExaminerAudio("tts-refresh:error", { key });
        return turn;
      }
      delay = EXAMINER_TTS_REFRESH_INTERVAL_MS;
    }
    traceExaminerAudio("tts-refresh:deadline", { key });
    return state.currentTurn?.id === turn.id ? state.currentTurn : turn;
  })().finally(() => {
    if (state.speaking.examinerTtsRefreshPromises.get(key) === refreshPromise) {
      state.speaking.examinerTtsRefreshPromises.delete(key);
    }
  });
  state.speaking.examinerTtsRefreshPromises.set(key, refreshPromise);
  return refreshPromise;
}

function isActivePracticeSession(sessionId) {
  return !!sessionId && state.practiceSessionId === sessionId && state.practiceLocked;
}

function examinerLoadingHint(turn) {
  if (turn?.prompt?.role === "follow_up") return "正在准备追问...";
  if (turn?.counts_toward_total === false) return "正在准备身份题...";
  return "正在准备考官音频...";
}

function examinerListeningStatus(turn) {
  if (turn?.part === "p2") {
    return "Listen to the examiner instruction, then read the cue card during preparation.";
  }
  if (turn?.prompt?.role === "follow_up") {
    return "Listen to the examiner follow-up question. Preparation starts automatically.";
  }
  if (turn?.counts_toward_total === false) {
    return "Listen to the examiner identity question. Preparation starts automatically.";
  }
  return "Listen to the examiner question. Preparation starts automatically.";
}

function beginPreparationWithoutExaminerAudio(sessionId, turn, reason = "no-examiner-audio") {
  if (!isActivePracticeSession(sessionId) || !turn || state.currentTurn?.id !== turn.id) return false;
  clearAutoNextTimeout();
  stopExaminerPlayback(reason);
  traceExaminerAudio("playback:prepare-without-audio", {
    reason,
    turnId: turn.id,
    ttsStatus: turn.examiner_tts?.status || "",
    hasQuestion: hasUsableTurnQuestion(turn),
  });
  text("recordStatus", turn.prompt?.role === "follow_up"
    ? "Follow-up audio is not ready. Prepare your answer directly."
    : "Examiner audio is not ready. Prepare your answer directly.");
  beginPreparation(sessionId, { reason, turnId: turn.id });
  return true;
}

function setExaminerLoadingUi(turn) {
  setRecordButton("examiner_loading", "Preparing", examinerLoadingHint(turn));
  const progress = turnProgressLabel(turn);
  text("progressTrack", practiceReadyText(state.view));
  text("phaseLabel", `${progress} -> Preparing examiner`);
  text("timerValue", "00:00");
  $("phaseMeter").style.width = "0%";
  text("recordStatus", examinerLoadingHint(turn));
}

function setExaminerListeningUi(turn) {
  const progress = turnProgressLabel(turn);
  setRecordButton("examiner_playing", "Listening...", "The examiner is asking the question.");
  text("phaseLabel", `${progress} -> Examiner`);
  text("recordStatus", examinerListeningStatus(turn));
}

function currentExaminerTurnStillMatches(sessionId, turnId, playback) {
  return Boolean(
    isActivePracticeSession(sessionId)
    && state.currentTurn?.id === turnId
    && isCurrentExaminerPlayback(playback)
  );
}

async function playExaminerTurn(turn, sessionId = state.practiceSessionId) {
  if (!isActivePracticeSession(sessionId) || !turn) return false;
  if (isWaitingForStreamedFollowUpText(turn)) {
    text("recordStatus", "正在生成追问...");
    traceExaminerAudio("playback:stream-pending-follow-up-blocked", {
      turnId: turn.id,
      hasQuestion: hasUsableTurnQuestion(turn),
      question: turn.question || turn.prompt?.question || "",
      promptBackend: turn.prompt?.backend || "",
      generationStatus: turn.prompt?.generation_status || "",
    });
    return false;
  }

  const turnId = turn.id;
  const existingPlayback = state.examinerPlayback;
  if (
    existingPlayback
    && !existingPlayback.cancelled
    && existingPlayback.sessionId === sessionId
    && existingPlayback.turnId === turnId
    && existingPlayback.promise
  ) {
    return existingPlayback.promise;
  }

  stopExaminerPlayback("begin-new-examiner-turn");
  if (!isActivePracticeSession(sessionId) || state.currentTurn?.id !== turnId) return false;

  const playback = {
    sessionId,
    turnId,
    player: null,
    promise: null,
    cancelled: false,
  };
  state.examinerPlayback = playback;
  setExaminerLoadingUi(turn);

  const playbackPromise = (async () => {
    await releaseRecordingAudioSessionForExaminerPlayback(playback, "before-examiner-playback");
    if (!currentExaminerTurnStillMatches(sessionId, turnId, playback)) return false;

    let currentTurn = state.currentTurn?.id === turnId ? state.currentTurn : turn;
    let tts = currentTurn.examiner_tts || {};
    if (!tts.audio_url && isPendingExaminerTts(tts)) {
      currentTurn = await refreshPendingExaminerTts(currentTurn, sessionId);
      if (!currentExaminerTurnStillMatches(sessionId, turnId, playback)) return false;
      tts = currentTurn?.examiner_tts || {};
    }

    if (!tts.audio_url) {
      return beginPreparationWithoutExaminerAudio(sessionId, currentTurn, "no-audio");
    }

    const source = resolveExaminerAudioPlaybackSource(tts.audio_url);
    if (!source || !currentExaminerTurnStillMatches(sessionId, turnId, playback)) return false;

    const player = new ExaminerAudioPlayer();
    playback.player = player;
    state.activeExaminerAudio = null;
    state.activeExaminerAudioPlayer = player;

    try {
      await player.load(source);
      if (!currentExaminerTurnStillMatches(sessionId, turnId, playback)) return false;
      const outcome = await player.playToEnd({
        onPlay: () => {
          if (currentExaminerTurnStillMatches(sessionId, turnId, playback)) {
            setExaminerListeningUi(currentTurn);
          }
        },
      });
      if (!currentExaminerTurnStillMatches(sessionId, turnId, playback)) return false;
      if (outcome === "ended") {
        player.unload("ended");
        if (state.activeExaminerAudioPlayer === player) state.activeExaminerAudioPlayer = null;
        beginPreparation(sessionId, { reason: "ended", turnId });
        return true;
      }
      return false;
    } catch (error) {
      traceExaminerAudio("playback:error", {
        turnId,
        error: error instanceof Error ? error.message : String(error),
        player: player.snapshot(),
      });
      if (!currentExaminerTurnStillMatches(sessionId, turnId, playback)) return false;
      return beginPreparationWithoutExaminerAudio(sessionId, currentTurn, "playback-error");
    } finally {
      if (state.examinerPlayback === playback) {
        playback.promise = null;
      }
    }
  })();

  playback.promise = playbackPromise;
  return playbackPromise;
}

async function beginExaminerPhase(sessionId = state.practiceSessionId) {
  if (!isActivePracticeSession(sessionId)) return;
  if (!state.currentTurn) return;
  clearAutoNextTimeout();
  if (isPracticeBusyStatus(state.status)) {
    traceExaminerAudio("playback:begin-blocked-by-status", {
      status: state.status,
      turnId: state.currentTurn.id,
    });
    return;
  }
  clearTimer();
  const turn = state.currentTurn;
  await playExaminerTurn(turn, sessionId);
}

function beginPreparation(sessionId = state.practiceSessionId, options = {}) {
  if (!isActivePracticeSession(sessionId)) return;
  const expectedTurnId = options.turnId || "";
  if (expectedTurnId && state.currentTurn?.id !== expectedTurnId) {
    traceExaminerAudio("preparation:stale-turn-skipped", {
      reason: options.reason || "",
      expectedTurnId,
      currentTurnId: state.currentTurn?.id || "",
      playbackTurnId: state.examinerPlayback?.turnId || "",
    });
    return;
  }
  traceExaminerAudio("preparation:begin", {
    reason: options.reason || "",
    expectedTurnId,
    currentTurnId: state.currentTurn?.id || "",
    playbackTurnId: state.examinerPlayback?.turnId || "",
    player: examinerPlayerSnapshot(options.player || state.activeExaminerAudioPlayer),
  });
  state.examinerPlayback = null;
  const seconds = state.currentTurn?.timers?.prep_seconds || 3;
  const isP2 = state.currentTurn?.part === "p2";
  setRecordButton("preparing", isP2 ? "Skip" : "Prepare", isP2 ? "Click to start recording now." : "Recording starts automatically.");
  text("phaseLabel", `Preparing -> ${turnProgressLabel(state.currentTurn)}`);
  text("recordStatus", isP2 ? "Prepare your answer. Click to start recording early." : `Prepare your answer. Recording starts in ${seconds} seconds.`);
  startCountdown(seconds, "Preparing", () => startRecording(sessionId).catch(showError), sessionId);
}

function startCountdown(seconds, label, onDone, sessionId = state.practiceSessionId) {
  clearTimer();
  state.timerRemaining = Number(seconds || 0);
  state.timerTotal = Math.max(1, state.timerRemaining);
  updateTimer(label);
  state.timer = setInterval(() => {
    if (!isActivePracticeSession(sessionId)) {
      clearTimer();
      return;
    }
    state.timerRemaining -= 1;
    updateTimer(label);
    if (state.timerRemaining <= 0) {
      clearTimer();
      onDone();
    }
  }, 1000);
}

function startRecordingTimer(seconds, sessionId = state.practiceSessionId) {
  clearTimer();
  state.timerRemaining = Number(seconds || 0);
  state.timerTotal = Math.max(1, state.timerRemaining);
  updateTimer("Recording");
  state.timer = setInterval(() => {
    if (!isActivePracticeSession(sessionId)) {
      clearTimer();
      return;
    }
    state.timerRemaining -= 1;
    updateTimer("Recording");
    if (state.timerRemaining <= 0) stopRecording();
  }, 1000);
}

function updateTimer(label) {
  const remaining = Math.max(0, state.timerRemaining);
  const minutes = String(Math.floor(remaining / 60)).padStart(2, "0");
  const seconds = String(remaining % 60).padStart(2, "0");
  text("phaseLabel", `${label} -> ${minutes}:${seconds}`);
  text("timerValue", `${minutes}:${seconds}`);
  const elapsed = Math.max(0, state.timerTotal - remaining);
  $("phaseMeter").style.width = `${Math.min(100, (elapsed / state.timerTotal) * 100)}%`;
}

function clearTimer() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
}

function clearAutoNextTimeout() {
  if (state.autoNextTimeout) window.clearTimeout(state.autoNextTimeout);
  state.autoNextTimeout = null;
}

function scheduleExaminerPhase(sessionId, turnId = state.currentTurn?.id, delayMs = 0) {
  clearAutoNextTimeout();
  const expectedTurnId = turnId || "";
  traceExaminerAudio("playback:scheduled-begin-set", {
    expectedTurnId,
    currentTurnId: state.currentTurn?.id || "",
    delayMs: Math.max(0, Number(delayMs) || 0),
    status: state.status,
    playbackTurnId: state.examinerPlayback?.turnId || "",
  });
  state.autoNextTimeout = window.setTimeout(() => {
    state.autoNextTimeout = null;
    if (!isActivePracticeSession(sessionId)) return;
    if (expectedTurnId && state.currentTurn?.id !== expectedTurnId) {
      traceExaminerAudio("playback:scheduled-begin-skipped", {
        expectedTurnId,
        currentTurnId: state.currentTurn?.id || "",
        status: state.status,
        playbackTurnId: state.examinerPlayback?.turnId || "",
      });
      return;
    }
    const activePlayback = state.examinerPlayback;
    if (
      activePlayback
      && !activePlayback.cancelled
      && activePlayback.sessionId === sessionId
      && activePlayback.turnId === (expectedTurnId || state.currentTurn?.id || "")
      && activePlayback.promise
    ) return;
    if (isPracticeBusyStatus(state.status)) {
      traceExaminerAudio("playback:scheduled-begin-status-skipped", {
        expectedTurnId,
        currentTurnId: state.currentTurn?.id || "",
        status: state.status,
      });
      return;
    }
    traceExaminerAudio("playback:scheduled-begin-fire", {
      expectedTurnId,
      currentTurnId: state.currentTurn?.id || "",
      status: state.status,
      playbackTurnId: state.examinerPlayback?.turnId || "",
    });
    beginExaminerPhase(sessionId);
  }, Math.max(0, Number(delayMs) || 0));
}

function stopRealtimePcmUplink(reason = "stopped") {
  return realtimePcmUplinkController.stop(reason);
}

function startRealtimePcmUplink(sessionId = state.practiceSessionId) {
  return realtimePcmUplinkController.start(sessionId);
}

function exposeWasmAudioPreprocessMetrics() {
  return speakingAudioPreprocessorRuntime.expose(() => realtimePcmUplinkController.metrics());
}

async function waitForSpeakingAudioPreprocessorTurnMetrics() {
  return speakingAudioPreprocessorRuntime.waitForTurnMetrics();
}

async function maybeStartSpeakingAudioPreprocessor(stream, sessionId = state.practiceSessionId) {
  return speakingAudioPreprocessorRuntime.maybeStart(stream, sessionId);
}

function stopSpeakingAudioPreprocessor(reason = "stopped") {
  return speakingAudioPreprocessorRuntime.stop(reason);
}

function normalizedDeviceLabel(label = "") {
  return String(label || "").trim().toLowerCase();
}

function isBluetoothAudioInputLabel(label = "") {
  const value = normalizedDeviceLabel(label);
  return Boolean(value && [
    "bluetooth",
    "headset",
    "hands-free",
    "handsfree",
    "airpods",
    "oppo",
    "enco",
    "soundcore",
    "rose openfun",
    "q45",
    "beats",
    "buds",
    "earbuds",
  ].some((token) => value.includes(token)));
}

function isVirtualAudioInputLabel(label = "") {
  const value = normalizedDeviceLabel(label);
  return Boolean(value && [
    "virtual",
    "oray",
    "blackhole",
    "soundflower",
    "loopback",
    "aggregate",
    "multi-output",
  ].some((token) => value.includes(token)));
}

function speakingInputDeviceScore(device) {
  const label = normalizedDeviceLabel(device?.label || "");
  if (!device || device.kind !== "audioinput" || !label) return -100;
  if (isBluetoothAudioInputLabel(label)) return -100;
  if (isVirtualAudioInputLabel(label)) return -80;
  let score = 1;
  if (label.includes("macbook") || label.includes("built-in") || label.includes("internal")) score += 100;
  if (label.includes("microphone") || label.includes("mic")) score += 30;
  if (label.includes("usb") || label.includes("studio display")) score += 20;
  if (label.includes("default")) score -= 10;
  return score;
}

function maskDeviceId(deviceId = "") {
  const value = String(deviceId || "");
  if (!value) return "";
  if (value.length <= 8) return `${value.slice(0, 2)}…`;
  return `${value.slice(0, 4)}…${value.slice(-4)}`;
}

function captureDeviceDiagnostics(device, extra = {}) {
  const label = device?.label || "";
  return {
    label,
    deviceId: maskDeviceId(device?.deviceId || ""),
    bluetoothLike: isBluetoothAudioInputLabel(label),
    virtualLike: isVirtualAudioInputLabel(label),
    ...extra,
  };
}

async function enumerateAudioInputDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.filter((device) => device.kind === "audioinput");
  } catch {
    return [];
  }
}

async function selectPreferredSpeakingInputDevice() {
  const inputs = await enumerateAudioInputDevices();
  const bluetoothInputs = inputs.filter((device) => isBluetoothAudioInputLabel(device.label));
  const ranked = inputs
    .map((device) => ({ device, score: speakingInputDeviceScore(device) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score);
  return {
    device: ranked[0]?.device || null,
    bluetoothInputs,
    inputs,
  };
}

function speakingAudioConstraintsForDevice(device) {
  const audio = {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
  if (device?.deviceId) {
    audio.deviceId = { exact: device.deviceId };
  }
  return { audio };
}

function activeTrackDeviceInfo(stream) {
  const track = stream?.getAudioTracks?.()[0] || null;
  return {
    label: track?.label || "",
    deviceId: "",
    bluetoothLike: isBluetoothAudioInputLabel(track?.label || ""),
    virtualLike: isVirtualAudioInputLabel(track?.label || ""),
  };
}

function exposeSpeakingInputDevice(info = {}) {
  state.speaking.captureDevice = {
    ...(state.speaking.captureDevice || {}),
    ...info,
    updatedAt: Date.now(),
  };
  window.__ieltsSpeakingInputDevice = { ...state.speaking.captureDevice };
  traceExaminerAudio("capture-device:selected", state.speaking.captureDevice);
}

async function getSpeakingAudioStream() {
  const initialSelection = await selectPreferredSpeakingInputDevice();
  const bluetoothInputsPresent = initialSelection.bluetoothInputs.length > 0;

  if (initialSelection.device) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia(speakingAudioConstraintsForDevice(initialSelection.device));
      const activeTrack = activeTrackDeviceInfo(stream);
      exposeSpeakingInputDevice({
        ...captureDeviceDiagnostics(initialSelection.device, {
          source: "preferred-enumerated-device",
          bluetoothInputsPresent,
          avoidBrowserDictation: activeTrack.bluetoothLike,
        }),
        activeTrack,
      });
      return stream;
    } catch (error) {
      traceExaminerAudio("capture-device:preferred-failed", {
        preferred: captureDeviceDiagnostics(initialSelection.device),
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  const baselineStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
  const baselineTrack = activeTrackDeviceInfo(baselineStream);

  if (baselineTrack.bluetoothLike) {
    const postPermissionSelection = await selectPreferredSpeakingInputDevice();
    const preferred = postPermissionSelection.device;
    if (preferred) {
      baselineStream.getTracks().forEach((track) => track.stop());
      const stream = await navigator.mediaDevices.getUserMedia(speakingAudioConstraintsForDevice(preferred));
      const activeTrack = activeTrackDeviceInfo(stream);
      exposeSpeakingInputDevice({
        ...captureDeviceDiagnostics(preferred, {
          source: "preferred-after-permission",
          bluetoothInputsPresent: true,
          avoidedBluetoothInput: baselineTrack.label || true,
          avoidBrowserDictation: activeTrack.bluetoothLike,
        }),
        activeTrack,
      });
      return stream;
    }
  }

  exposeSpeakingInputDevice({
    label: baselineTrack.label || "Default microphone",
    deviceId: "",
    bluetoothLike: baselineTrack.bluetoothLike,
    virtualLike: baselineTrack.virtualLike,
    source: "browser-default",
    bluetoothInputsPresent,
    avoidBrowserDictation: baselineTrack.bluetoothLike,
    activeTrack: baselineTrack,
  });
  return baselineStream;
}

function stopDictationForExaminerPlayback(reason = "examiner-playback") {
  const waitPromise = state.dictationRecognition ? waitForFinalDictation() : Promise.resolve();
  state.dictationShouldRun = false;
  state.dictationStopping = true;
  if (state.dictationRestartTimer) {
    window.clearTimeout(state.dictationRestartTimer);
    state.dictationRestartTimer = null;
  }
  if (state.dictationRecognition) {
    try {
      state.dictationRecognition.stop();
    } catch {
      // Ignore browser dictation stop races; examiner audio stability is the priority.
    }
    window.setTimeout(resolveDictationWait, 800);
  } else {
    resolveDictationWait();
  }
  traceExaminerAudio("audio-session:dictation-stop-requested", {
    reason,
    hadRecognition: Boolean(state.dictationRecognition),
  });
  return waitPromise;
}

function stopMediaTracksForExaminerPlayback(reason = "examiner-playback") {
  const stream = state.mediaStream;
  if (!stream) return false;
  let stopped = false;
  try {
    stream.getTracks().forEach((track) => {
      try {
        if (track.readyState !== "ended") {
          track.stop();
          stopped = true;
        }
      } catch {
        // Ignore individual stale track failures.
      }
    });
  } finally {
    state.mediaStream = null;
  }
  traceExaminerAudio("audio-session:media-tracks-stopped", { reason, stopped });
  return stopped;
}

async function withTimeout(promise, timeoutMs, fallbackValue = null) {
  let timer = null;
  try {
    return await Promise.race([
      Promise.resolve(promise),
      new Promise((resolve) => {
        timer = window.setTimeout(() => resolve(fallbackValue), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) window.clearTimeout(timer);
  }
}

async function releaseRecordingAudioSessionForExaminerPlayback(playback, reason = "examiner-playback") {
  const startedAt = Date.now();
  const hadDictation = Boolean(state.dictationRecognition || state.dictationShouldRun || state.dictationRestartTimer);
  const hadPreprocessor = Boolean(state.speaking.audioPreprocessor || state.speaking.audioPreprocessorStopPromise);
  const hadRealtimeSocket = Boolean(state.speaking.realtimePcmSocket);
  const hadMediaStream = Boolean(state.mediaStream);
  if (!hadDictation && !hadPreprocessor && !hadRealtimeSocket && !hadMediaStream) {
    traceExaminerAudio("audio-session:release-skip", { reason });
    return;
  }

  traceExaminerAudio("audio-session:release-start", {
    reason,
    turnId: playback?.turnId || state.currentTurn?.id || "",
    hadDictation,
    hadPreprocessor,
    hadRealtimeSocket,
    hadMediaStream,
  });

  const dictationPromise = hadDictation
    ? stopDictationForExaminerPlayback(reason).catch(() => null)
    : Promise.resolve(null);

  let preprocessorPromise = null;
  if (state.speaking.audioPreprocessorStopPromise) {
    preprocessorPromise = state.speaking.audioPreprocessorStopPromise.catch(() => null);
  } else if (state.speaking.audioPreprocessor) {
    preprocessorPromise = Promise.resolve(stopSpeakingAudioPreprocessor(reason)).catch(() => null);
  } else if (state.speaking.realtimePcmSocket) {
    preprocessorPromise = Promise.resolve(stopRealtimePcmUplink(reason)).catch(() => null);
  } else {
    preprocessorPromise = Promise.resolve(null);
  }

  const tracksStopped = stopMediaTracksForExaminerPlayback(reason);

  await withTimeout(
    Promise.allSettled([dictationPromise, preprocessorPromise]),
    EXAMINER_AUDIO_INPUT_RELEASE_TIMEOUT_MS,
    null,
  );

  if (!isCurrentExaminerPlayback(playback)) {
    traceExaminerAudio("audio-session:release-stale", {
      reason,
      elapsedMs: Date.now() - startedAt,
    });
    return;
  }

  if (hadDictation || hadPreprocessor || hadRealtimeSocket || hadMediaStream || tracksStopped) {
    await wait(EXAMINER_AUDIO_BLUETOOTH_DRAIN_MS);
  }

  traceExaminerAudio("audio-session:release-end", {
    reason,
    elapsedMs: Date.now() - startedAt,
  });
}

async function startRecording(sessionId = state.practiceSessionId) {
  if (!isActivePracticeSession(sessionId)) return;
  if (!state.currentTurn) return;
  stopExaminerPlayback("start-recording");
  state.status = "recording";
  const stream = await getSpeakingAudioStream();
  if (!isActivePracticeSession(sessionId)) {
    stream.getTracks().forEach((track) => track.stop());
    return;
  }
  state.mediaStream = stream;
  state.audioChunks = [];
  state.transcript = "";
  state.transcriptFinal = "";
  state.transcriptInterim = "";
  state.transcriptStatus = "missing";
  state.transcriptSource = "browser_dictation";
  state.dictationRestartCount = 0;
  state.dictationLastError = "";
  setDictationStatus("starting", state.speaking.captureDevice?.avoidBrowserDictation
    ? "检测到蓝牙耳机输入风险，已优先使用非蓝牙麦克风录音，并关闭浏览器转写以避免耳机通话模式。"
    : "浏览器转写启动中；如果开头静音，系统会自动重新监听。");
  const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : "audio/webm";
  state.mediaRecorder = new MediaRecorder(stream, { mimeType });
  state.mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) state.audioChunks.push(event.data);
  };
  state.mediaRecorder.onstop = () => {
    if (state.cancelRecording) {
      state.cancelRecording = false;
      return;
    }
    finalizeTurn(mimeType).catch(showError);
  };
  state.mediaRecorder.start();
  state.cancelRecording = false;
  maybeStartSpeakingAudioPreprocessor(stream, sessionId);
  startDictation();
  setRecordButton("recording", "Stop", "Recording. Press to finish early.");
  text("recordStatus", "Recording in progress...");
  startRecordingTimer(state.currentTurn.timers.speak_seconds, sessionId);
}

function stopRecording() {
  if (state.status !== "recording") return;
  state.status = "processing";
  clearTimer();
  setRecordButton("processing", "Saving", "Uploading this answer.");
  text("recordStatus", "Saving this answer...");
  recordRealtimePhaseMetric({ recordingStoppedAt: Date.now() });
  stopDictation();
  stopSpeakingAudioPreprocessor("recording-stopped");
  if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
    state.mediaRecorder.stop();
  }
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach((track) => track.stop());
    state.mediaStream = null;
  }
}

function isP1WorkStudyIdentityTurn(turn) {
  return turn?.part === "p1" && turn?.prompt?.flow === "intro" && turn?.prompt?.role === "work_study";
}

function mergeCompletedTurnPayload(attemptPayload, completedTurn) {
  if (!attemptPayload || !completedTurn) return attemptPayload;
  const turns = (attemptPayload.turns || []).map((item) => (
    item.id === completedTurn.id ? { ...item, ...completedTurn } : item
  ));
  return { ...attemptPayload, turns };
}

function completeTurnPayload(
  turn,
  transcript,
  transcriptStatus,
  transcriptSource = "browser_dictation",
  p2CorpusEntryId = state.p2Corpus.selectedEntryId,
  audioPreprocessingMetrics = null,
  realtimeAsrMetrics = null,
  streamFollowUp = false,
) {
  return {
    transcript_raw: transcript,
    transcript_status: transcriptStatus,
    transcript_source: transcriptSource || "browser_dictation",
    ...(turn.part === "p2" && p2CorpusEntryId ? { p2_corpus_link: { entry_id: p2CorpusEntryId } } : {}),
    ...(audioPreprocessingMetrics ? { audio_preprocessing_metrics: audioPreprocessingMetrics } : {}),
    ...(realtimeAsrMetrics ? { realtime_asr_metrics: realtimeAsrMetrics } : {}),
    ...(streamFollowUp ? { stream_follow_up: true } : {}),
  };
}

function pendingTurnCompletionKey(attemptId, turnId) {
  return `${attemptId}:${turnId}`;
}

function registerPendingTurnCompletion(attempt, turn, promise) {
  const key = pendingTurnCompletionKey(attempt.id, turn.id);
  state.speaking.turnCompletionErrors.delete(key);
  state.speaking.pendingTurnCompletions.set(key, promise);
  promise.finally(() => {
    if (state.speaking.pendingTurnCompletions.get(key) === promise) {
      state.speaking.pendingTurnCompletions.delete(key);
    }
  });
}

function handleTurnCompletionFailure(error, context = {}) {
  const attemptId = context.attempt?.id || state.attempt?.id || "";
  if (state.abortingAttemptId === attemptId) return;
  const message = error instanceof Error ? error.message : String(error || "");
  state.speaking.turnCompletionErrors.set(
    pendingTurnCompletionKey(attemptId, context.turn?.id || state.speaking.retryCompletion?.turn?.id || ""),
    error,
  );
  setBusy("");
  setDictationStatus("", "");
  $("summaryPanel")?.classList.add("hidden");
  if (context.localNextTurn && state.currentTurn?.id === context.localNextTurn.id) {
    text("recordStatus", `后台保存本题失败：${message || "请重试保存。"}`);
    return;
  }
  setRecordButton("completion_failed", "重新保存", "本题保存失败，点击重新保存。");
  text("recordStatus", message ? `本题保存失败：${message}` : "本题保存失败，请重新保存。");
}

async function waitForPendingTurnCompletions(attemptId) {
  const pending = [...state.speaking.pendingTurnCompletions.entries()]
    .filter(([key]) => key.startsWith(`${attemptId}:`))
    .map(([, promise]) => promise);
  if (pending.length) await Promise.all(pending);
  const errors = [...state.speaking.turnCompletionErrors.entries()]
    .filter(([key]) => key.startsWith(`${attemptId}:`));
  if (errors.length) {
    const [, error] = errors[0];
    throw error;
  }
}

function handleTurnCompletionResult(attempt, turn, completePayload) {
  if (state.abortingAttemptId === attempt.id || state.attempt?.id !== attempt.id) return;
  if (completePayload?.turn) {
    state.attempt = mergeCompletedTurnPayload(state.attempt, completePayload.turn);
  }
  if (completePayload?.next_turn && state.currentTurn?.id === completePayload.next_turn.id) {
    state.currentTurn = completePayload.next_turn;
    state.attempt = mergeCompletedTurnPayload(state.attempt, completePayload.next_turn);
    if (isTurnRenderBusyStatus(state.status)) {
      traceExaminerAudio("render-turn-background-complete-skipped", {
        completedTurnId: turn?.id || "",
        nextTurnId: completePayload.next_turn.id || "",
        status: state.status,
        playbackTurnId: state.examinerPlayback?.turnId || "",
      });
      return;
    }
    renderTurn(completePayload.next_turn);
  }
}

function shouldStreamFollowUpTurn(turn) {
  const prompt = turn?.prompt || {};
  return ["stream_pending", "stream_failed"].includes(prompt.backend)
    || ["pending", "failed"].includes(prompt.generation_status);
}

function isStreamFollowUpFailed(turn) {
  const prompt = turn?.prompt || {};
  return prompt.backend === "stream_failed" || prompt.generation_status === "failed";
}

function hasUsableTurnQuestion(turn) {
  if (shouldStreamFollowUpTurn(turn)) {
    const promptQuestion = String(turn?.prompt?.question || "").trim();
    const question = String(turn?.question || turn?.examiner_text || turn?.text || "").trim();
    return Boolean(
      (promptQuestion && !STREAM_PENDING_FOLLOW_UP_PLACEHOLDERS.has(promptQuestion))
      || (question && !STREAM_PENDING_FOLLOW_UP_PLACEHOLDERS.has(question)),
    );
  }
  return Boolean(String(
    turn?.question ||
    turn?.prompt?.question ||
    turn?.examiner_text ||
    turn?.text ||
    "",
  ).trim());
}

function isWaitingForStreamedFollowUpText(turn) {
  return shouldStreamFollowUpTurn(turn) && !isStreamFollowUpFailed(turn) && !hasUsableTurnQuestion(turn);
}

function mergeStreamingFollowUpTurn(nextTurn, patch) {
  const question = patch.question ?? patch.text ?? nextTurn?.question ?? "";
  const turnPatch = patch.turn || {};
  const prompt = {
    ...(nextTurn?.prompt || {}),
    ...(turnPatch.prompt || {}),
    ...(patch.prompt || {}),
    ...(question ? { question } : {}),
  };
  return {
    ...nextTurn,
    ...turnPatch,
    question,
    prompt,
    examiner_text: patch.examiner_text ?? turnPatch.examiner_text ?? question,
    ...(patch.examiner_tts ? { examiner_tts: patch.examiner_tts } : {}),
  };
}

function sourceTurnForStreamedFollowUp(attempt, followUpTurn) {
  const afterTurnId = followUpTurn?.prompt?.after_turn;
  if (!afterTurnId) return null;
  return (attempt?.turns || []).find((item) => item.id === afterTurnId) || null;
}

function parseSseEventBlock(block) {
  const dataLines = String(block || "")
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (!dataLines.length) return null;
  try {
    return JSON.parse(dataLines.join("\n"));
  } catch (_error) {
    return null;
  }
}

async function consumeSseResponse(response, onPayload) {
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    let message = body || `Request failed: ${response.status}`;
    try {
      const parsed = JSON.parse(body);
      message = parsed.error || message;
    } catch (_error) {
      // Keep the raw response text.
    }
    throw new Error(message);
  }
  if (!response.body?.getReader) {
    throw new Error("Streaming follow-up is not supported in this browser.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\n\n/);
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const payload = parseSseEventBlock(block);
      if (payload) await onPayload(payload);
    }
  }
  buffer += decoder.decode();
  const payload = parseSseEventBlock(buffer);
  if (payload) await onPayload(payload);
}

async function streamFollowUpForCompletedTurn(attempt, completedTurn, nextTurn, sessionId) {
  if (!attempt?.id || !completedTurn?.id || !nextTurn?.id || !shouldStreamFollowUpTurn(nextTurn)) return false;
  let currentNextTurn = nextTurn;
  let streamedText = "";
  let examinerStarted = false;
  let ttsWaitPromise = null;
  let streamResolvedQuestion = false;
  const streamStartedAt = Date.now();
  recordRealtimePhaseMetric({
    followUpStreamStartedAt: streamStartedAt,
    followUpStreamStartAfterStopMs: realtimeMetricElapsed("recordingStoppedAt", "followUpStreamStartedAt"),
  });
  const startExaminerOnce = () => {
    if (examinerStarted || !isActivePracticeSession(sessionId) || state.currentTurn?.id !== currentNextTurn.id) return;
    examinerStarted = true;
    const examinerStartedAt = Date.now();
    recordRealtimePhaseMetric({
      followUpExaminerStartedAt: examinerStartedAt,
      followUpExaminerStartAfterStopMs: realtimeMetricElapsed("recordingStoppedAt", "followUpExaminerStartedAt"),
      followUpExaminerStartAfterStreamMs: realtimeMetricElapsed("followUpStreamStartedAt", "followUpExaminerStartedAt"),
    });
    scheduleExaminerPhase(sessionId, currentNextTurn.id, 120);
  };
  const startPreparationWithoutAudioOnce = (reason) => {
    if (examinerStarted || !isActivePracticeSession(sessionId) || state.currentTurn?.id !== currentNextTurn.id) return;
    examinerStarted = true;
    const startedAt = Date.now();
    recordRealtimePhaseMetric({
      followUpExaminerStartedAt: startedAt,
      followUpExaminerStartAfterStopMs: realtimeMetricElapsed("recordingStoppedAt", "followUpExaminerStartedAt"),
      followUpExaminerStartAfterStreamMs: realtimeMetricElapsed("followUpStreamStartedAt", "followUpExaminerStartedAt"),
      followUpTtsStatus: reason,
    });
    beginPreparationWithoutExaminerAudio(sessionId, currentNextTurn, reason);
  };
  const waitForFollowUpAudioThenStart = async (reason = "tts-refresh") => {
    if (examinerStarted || !isActivePracticeSession(sessionId) || state.currentTurn?.id !== currentNextTurn.id) return;
    if (isStreamFollowUpFailed(currentNextTurn)) {
      setRecordButton("follow_up_failed", "重新生成追问", "追问生成失败，点击重试。");
      text("recordStatus", "追问生成失败，可以重新生成。");
      return;
    }
    if (ttsWaitPromise) return ttsWaitPromise;
    ttsWaitPromise = (async () => {
      const currentTts = currentNextTurn.examiner_tts || {};
      if (currentTts.audio_url) {
        startExaminerOnce();
        return;
      }
      text("recordStatus", "追问已生成，正在准备考官音频...");
      traceExaminerAudio("follow-up-tts:wait-start", {
        reason,
        turnId: currentNextTurn.id,
        ttsStatus: currentTts.status || "",
      });
      let refreshedTurn = currentNextTurn;
      if (isPendingExaminerTts(currentTts)) {
        refreshedTurn = await refreshPendingExaminerTts(currentNextTurn, sessionId);
      }
      if (!isActivePracticeSession(sessionId) || state.currentTurn?.id !== currentNextTurn.id || examinerStarted) return;
      currentNextTurn = refreshedTurn || currentNextTurn;
      state.currentTurn = currentNextTurn;
      state.attempt = mergeCompletedTurnPayload(state.attempt, currentNextTurn);
      const refreshedTts = currentNextTurn.examiner_tts || {};
      traceExaminerAudio("follow-up-tts:wait-end", {
        reason,
        turnId: currentNextTurn.id,
        ttsStatus: refreshedTts.status || "",
        audioUrl: refreshedTts.audio_url || "",
      });
      if (refreshedTts.audio_url) {
        text("recordStatus", "考官音频已准备好。");
        startExaminerOnce();
        return;
      }
      text("recordStatus", "追问音频暂不可用，可以直接准备回答。");
      startPreparationWithoutAudioOnce(`${reason}-no-audio`);
    })().finally(() => {
      ttsWaitPromise = null;
    });
    return ttsWaitPromise;
  };
  const applyTurnPatch = (patch) => {
    if (!isActivePracticeSession(sessionId) || state.currentTurn?.id !== currentNextTurn.id) return;
    currentNextTurn = mergeStreamingFollowUpTurn(currentNextTurn, patch);
    state.currentTurn = currentNextTurn;
    state.attempt = mergeCompletedTurnPayload(state.attempt, currentNextTurn);
    renderTurn(currentNextTurn);
  };

  text("recordStatus", "正在生成追问...");
  const response = await fetch(`/api/attempts/${encodeURIComponent(attempt.id)}/turns/${encodeURIComponent(completedTurn.id)}/follow-up-stream`, {
    method: "GET",
    credentials: "same-origin",
    headers: { "Accept": "text/event-stream" },
  });
  await consumeSseResponse(response, async (payload) => {
    if (!isActivePracticeSession(sessionId) || state.currentTurn?.id !== currentNextTurn.id) return;
    if (payload.event === "chunk") {
      streamedText += payload.text || "";
      if (streamedText.trim()) {
        if (!state.speaking.realtimePcmMetrics?.followUpFirstChunkAt) {
          const firstChunkAt = Date.now();
          recordRealtimePhaseMetric({
            followUpFirstChunkAt: firstChunkAt,
            followUpFirstChunkAfterStopMs: realtimeMetricElapsed("recordingStoppedAt", "followUpFirstChunkAt"),
            followUpFirstChunkAfterStreamMs: realtimeMetricElapsed("followUpStreamStartedAt", "followUpFirstChunkAt"),
          });
        }
        applyTurnPatch({ text: streamedText });
        text("recordStatus", "追问正在生成...");
      }
      return;
    }
    if (payload.event === "question_complete") {
      streamResolvedQuestion = true;
      streamedText = payload.text || streamedText;
      const questionCompleteAt = Date.now();
      recordRealtimePhaseMetric({
        followUpQuestionCompleteAt: questionCompleteAt,
        followUpQuestionCompleteAfterStopMs: realtimeMetricElapsed("recordingStoppedAt", "followUpQuestionCompleteAt"),
        followUpQuestionCompleteAfterStreamMs: realtimeMetricElapsed("followUpStreamStartedAt", "followUpQuestionCompleteAt"),
        followUpBackend: payload.backend || "",
      });
      applyTurnPatch({ text: streamedText, turn: payload.turn });
      text("recordStatus", "追问已生成，正在准备考官音频...");
      waitForFollowUpAudioThenStart("question-complete");
      return;
    }
    if (payload.event === "tts_ready") {
      const ttsReadyAt = Date.now();
      recordRealtimePhaseMetric({
        followUpTtsReadyAt: ttsReadyAt,
        followUpTtsReadyAfterStopMs: realtimeMetricElapsed("recordingStoppedAt", "followUpTtsReadyAt"),
        followUpTtsReadyAfterStreamMs: realtimeMetricElapsed("followUpStreamStartedAt", "followUpTtsReadyAt"),
      });
      applyTurnPatch({ examiner_tts: payload.examiner_tts || { audio_url: payload.audio_url, status: "ready", provider: "volcengine" } });
      text("recordStatus", "考官音频已准备好。");
      startExaminerOnce();
      return;
    }
    if (payload.event === "tts_timeout") {
      recordRealtimePhaseMetric({
        followUpTtsTimeoutAt: Date.now(),
        followUpTtsStatus: "timeout",
      });
      applyTurnPatch({ examiner_tts: payload.examiner_tts || { provider: "volcengine", status: "pending", audio_url: null } });
      text("recordStatus", "考官音频仍在生成，稍等一下...");
      waitForFollowUpAudioThenStart("tts-timeout");
      return;
    }
    if (payload.event === "fallback") {
      streamResolvedQuestion = true;
      streamedText = payload.text || streamedText || currentNextTurn.question || "";
      const fallbackAt = Date.now();
      recordRealtimePhaseMetric({
        followUpFallbackAt: fallbackAt,
        followUpFallbackAfterStopMs: realtimeMetricElapsed("recordingStoppedAt", "followUpFallbackAt"),
        followUpBackend: "fallback",
      });
      applyTurnPatch({ text: streamedText, turn: payload.turn });
      text("recordStatus", "追问已生成，正在准备考官音频...");
      waitForFollowUpAudioThenStart("fallback");
      return;
    }
    if (payload.event === "failed") {
      recordRealtimePhaseMetric({
        followUpFailedAt: Date.now(),
        followUpBackend: payload.backend || "stream_failed",
      });
      applyTurnPatch({ turn: payload.turn || {}, prompt: payload.turn?.prompt || {} });
      setRecordButton("follow_up_failed", "重新生成追问", "追问生成失败，点击重试。");
      text("recordStatus", payload.error ? `追问生成失败：${payload.error}` : "追问生成失败，可以重新生成。");
      return;
    }
    if (payload.event === "done") {
      if (payload.turn) applyTurnPatch({ turn: payload.turn });
      if (isStreamFollowUpFailed(currentNextTurn)) {
        setRecordButton("follow_up_failed", "重新生成追问", "追问生成失败，点击重试。");
        text("recordStatus", "追问生成失败，可以重新生成。");
        return;
      }
      if (hasUsableTurnQuestion(currentNextTurn)) streamResolvedQuestion = true;
      if ((currentNextTurn.examiner_tts || {}).audio_url) {
        startExaminerOnce();
      } else {
        waitForFollowUpAudioThenStart("stream-done");
      }
    }
  });
  if ((currentNextTurn.examiner_tts || {}).audio_url) {
    startExaminerOnce();
  } else if (isStreamFollowUpFailed(currentNextTurn)) {
    setRecordButton("follow_up_failed", "重新生成追问", "追问生成失败，点击重试。");
    text("recordStatus", "追问生成失败，可以重新生成。");
  } else if (!streamResolvedQuestion && isWaitingForStreamedFollowUpText(currentNextTurn)) {
    setRecordButton("turn_saved", "Next", "正在等待追问生成。");
    text("recordStatus", "正在生成追问...");
  } else {
    await waitForFollowUpAudioThenStart("stream-ended");
  }
  return true;
}

async function finalizeTurn(mimeType, retrySnapshot = null) {
  const attempt = retrySnapshot?.attempt || state.attempt;
  const turn = retrySnapshot?.turn || state.currentTurn;
  if (!attempt || !turn) return;
  if (!retrySnapshot) {
    await waitForFinalDictation();
    setDictationStatus("", "");
  }
  const audioPreprocessingMetrics = retrySnapshot?.audioPreprocessingMetrics || await waitForSpeakingAudioPreprocessorTurnMetrics();
  const realtimeAsrMetrics = retrySnapshot?.realtimeAsrMetrics || realtimePcmUplinkController.metrics();
  if (state.abortingAttemptId === attempt.id || state.attempt?.id !== attempt.id) return;
  const audioChunks = retrySnapshot?.audioChunks?.slice() || state.audioChunks.slice();
  const blob = new Blob(audioChunks, { type: mimeType });
  const transcriptSnapshot = retrySnapshot?.transcript ?? state.transcript;
  const transcriptStatusSnapshot = retrySnapshot?.transcriptStatus || state.transcriptStatus;
  const transcriptSourceSnapshot = retrySnapshot?.transcriptSource || state.transcriptSource || "browser_dictation";
  const p2CorpusEntrySnapshot = retrySnapshot?.p2CorpusEntryId || state.p2Corpus.selectedEntryId;
  state.speaking.retryCompletion = {
    attempt,
    turn,
    mimeType,
    audioChunks,
    audioPreprocessingMetrics,
    realtimeAsrMetrics,
    transcript: transcriptSnapshot,
    transcriptStatus: transcriptStatusSnapshot,
    transcriptSource: transcriptSourceSnapshot,
    p2CorpusEntryId: p2CorpusEntrySnapshot,
  };
  setRecordButton("processing", "Saving", "正在上传回答音频...");
  try {
    const token = await ensureCsrfToken();
    const uploadHeaders = { "Content-Type": mimeType.split(";")[0] };
    if (token) uploadHeaders["X-CSRFToken"] = token;
    const upload = await fetch(`/api/attempts/${attempt.id}/turns/${turn.id}/audio`, {
      method: "POST",
      credentials: "same-origin",
      headers: uploadHeaders,
      body: blob,
    });
    const body = await upload.text();
    const payload = body ? JSON.parse(body) : {};
    if (!upload.ok) throw new Error(payload.error || "Audio upload failed");
    const completionStatus = isP1WorkStudyIdentityTurn(turn)
      ? "正在生成追问..."
      : "正在保存本题...";
    const localNextTurn = localNextTurnAfter(turn, attempt);
    const requiresSyncComplete = turnRequiresSynchronousComplete(turn, localNextTurn);
    recordRealtimePhaseMetric({ turnCompleteStartedAt: Date.now() });
    const completeRequest = (streamFollowUp = false) => api(`/api/attempts/${attempt.id}/turns/${turn.id}/complete`, completeTurnPayload(
      turn,
      transcriptSnapshot,
      transcriptStatusSnapshot,
      transcriptSourceSnapshot,
      p2CorpusEntrySnapshot,
      audioPreprocessingMetrics,
      realtimeAsrMetrics,
      streamFollowUp,
    ));
    if (!requiresSyncComplete) {
      const sessionId = state.practiceSessionId;
      state.attempt = mergeCompletedTurnPayload(state.attempt, {
        id: turn.id,
        status: "completed",
        audio: payload.audio || turn.audio,
        transcript_raw: transcriptSnapshot,
        transcript_cleaned: transcriptSnapshot,
        transcript_status: transcriptStatusSnapshot,
        transcript_source: transcriptSourceSnapshot,
      });
      state.currentTurn = localNextTurn;
      renderTurn(localNextTurn);
      setRecordButton("turn_saved", "Next", "正在进入下一题。");
      text("recordStatus", "音频已上传，正在后台保存转写。");
      scheduleExaminerPhase(sessionId, localNextTurn.id, 200);
      const completion = completeRequest()
        .then((completePayload) => {
          if (state.speaking.retryCompletion?.turn?.id === turn.id) {
            state.speaking.retryCompletion = null;
            state.audioChunks = [];
          }
          state.speaking.turnCompletionErrors.delete(pendingTurnCompletionKey(attempt.id, turn.id));
          handleTurnCompletionResult(attempt, turn, completePayload);
        })
        .catch((error) => {
          if (state.abortingAttemptId === attempt.id || state.attempt?.id !== attempt.id) return;
          handleTurnCompletionFailure(error, { attempt, turn, localNextTurn });
        });
      registerPendingTurnCompletion(attempt, turn, completion);
      return;
    }
    setRecordButton("processing", "Saving", completionStatus);
    text("recordStatus", completionStatus);
    const completePayload = await completeRequest(requiresSyncComplete);
    recordRealtimePhaseMetric({
      turnCompleteReturnedAt: Date.now(),
      turnCompleteAfterStopMs: realtimeMetricElapsed("recordingStoppedAt", "turnCompleteReturnedAt"),
    });
    if (state.abortingAttemptId === attempt.id || state.attempt?.id !== attempt.id) return;
    state.speaking.turnCompletionErrors.delete(pendingTurnCompletionKey(attempt.id, turn.id));
    state.attempt = completePayload.attempt;
    if (completePayload.next_turn) {
      const sessionId = state.practiceSessionId;
      state.currentTurn = completePayload.next_turn;
      renderTurn(completePayload.next_turn);
      setRecordButton("turn_saved", "Next", "正在进入下一题。");
      clearAutoNextTimeout();
      if (shouldStreamFollowUpTurn(completePayload.next_turn)) {
        text("recordStatus", "本题已保存，正在生成追问...");
        streamFollowUpForCompletedTurn(attempt, turn, completePayload.next_turn, sessionId)
          .catch((error) => {
            if (state.abortingAttemptId === attempt.id || state.attempt?.id !== attempt.id) return;
            const message = error instanceof Error ? error.message : String(error || "");
            traceExaminerAudio("follow-up-stream:error-recovered", {
              turnId: completePayload.next_turn.id,
              message,
            });
            if (isStreamFollowUpFailed(state.currentTurn)) {
              setRecordButton("follow_up_failed", "重新生成追问", "追问生成失败，点击重试。");
              text("recordStatus", "追问生成失败，可以重新生成。");
              return;
            }
            if (isWaitingForStreamedFollowUpText(state.currentTurn)) {
              setRecordButton("turn_saved", "Next", "正在等待追问生成。");
              text("recordStatus", "追问仍在生成，请稍等。");
              return;
            }
            if (hasUsableTurnQuestion(state.currentTurn)) {
              text("recordStatus", "追问已保留，正在准备下一步。");
              scheduleExaminerPhase(sessionId, state.currentTurn.id, 650);
              return;
            }
            showError(error);
          });
      } else {
        text("recordStatus", "本题已保存，下一题会自动开始。");
        scheduleExaminerPhase(sessionId, completePayload.next_turn.id, 650);
      }
    } else {
      state.currentTurn = null;
      state.speaking.retryCompletion = null;
      await scoreAttempt();
    }
    state.speaking.retryCompletion = null;
  } finally {
    if (!state.speaking.retryCompletion) state.audioChunks = [];
  }
}

async function retryTurnCompletion() {
  const retry = state.speaking.retryCompletion;
  if (!retry?.attempt || !retry?.turn || !retry?.audioChunks?.length) {
    setRecordButton("ready", "Try Again", "上次保存失败，请重新开始。");
    text("recordStatus", "没有可重新保存的录音，请重新开始。");
    return;
  }
  state.attempt = retry.attempt;
  state.currentTurn = retry.turn;
  state.audioChunks = retry.audioChunks.slice();
  state.transcript = retry.transcript || "";
  state.transcriptFinal = retry.transcript || "";
  state.transcriptInterim = "";
  state.transcriptStatus = retry.transcriptStatus || (retry.transcript ? "captured" : "missing");
  state.transcriptSource = retry.transcriptSource || "browser_dictation";
  state.p2Corpus.selectedEntryId = retry.p2CorpusEntryId || state.p2Corpus.selectedEntryId || "";
  renderTurn(retry.turn);
  await finalizeTurn(retry.mimeType || "audio/webm", retry);
}

async function scoreAttempt() {
  if (!state.attempt) return;
  const attemptId = state.attempt.id;
  const selector = $("p2CorpusPrepSelect");
  if (selector) selector.disabled = true;
  state.speaking.pendingAnalysis = {
    attemptId,
    view: isPracticeView(state.view) ? state.view : null,
    attempt: state.attempt,
  };
  state.practiceLocked = false;
  updateSidebarLock();
  $("exitPractice")?.classList.add("hidden");
  setRecordButton("scoring", "Analyzing", "Analyzing the full section and generating the report.");
  text("recordStatus", "Analyzing the full section and generating the report.");
  try {
    await waitForPendingTurnCompletions(attemptId);
    if (state.abortingAttemptId === attemptId || state.attempt?.id !== attemptId) return;
    const scored = await api(`/api/attempts/${attemptId}/score`, {});
    if (state.abortingAttemptId === attemptId) return;
    const task = scored.ai_task || null;
    if (isSpeakingTaskActive(task)) {
      setRecordButton("scoring", "Analyzing", "AI analysis is running in the background.");
      text("recordStatus", speakingTaskStatusTitle(task));
      text("phaseLabel", "Analyzing");
      startSpeakingScorePolling(task.id, attemptId);
      return;
    }
    if (task && isSpeakingTaskTerminal(task)) {
      handleSpeakingAnalysisFailure(new Error(speakingTaskStatusText(task)), attemptId, { task });
      return;
    }
    if (scored.status === "analysis_pending" && !scored.ielts_score) {
      handleSpeakingAnalysisFailure(new Error("口语分析任务没有进入后台队列，请重试分析。"), attemptId, { task });
      return;
    }
    const isCurrentAttempt = state.attempt?.id === attemptId;
    if (isCurrentAttempt) state.attempt = scored;
    state.historyDetailCache.set(scored.id, scored);
    await loadHistory(false);
    if (isCurrentAttempt) state.status = "summary";
    if (isCurrentAttempt && isPracticeView(state.view)) {
      setRecordButton("summary", "Start Again", "Record another section.");
      text("recordStatus", "Section report is ready.");
      text("phaseLabel", "Scored");
    }
    if (state.speaking.pendingAnalysis?.attemptId === attemptId) state.speaking.pendingAnalysis = null;
    showSpeakingScoreCompleteModal(scored);
  } catch (error) {
    if (state.speaking.pendingAnalysis?.attemptId === attemptId) state.speaking.pendingAnalysis = null;
    if (error?.status === 401) {
      showError(error);
      return;
    }
    if (state.speaking.retryCompletion?.attempt?.id === attemptId) {
      state.currentTurn = state.speaking.retryCompletion.turn;
      renderTurn(state.currentTurn);
      handleTurnCompletionFailure(error, {
        attempt: state.speaking.retryCompletion.attempt,
        turn: state.speaking.retryCompletion.turn,
      });
      return;
    }
    handleSpeakingAnalysisFailure(error, attemptId);
  }
}

function speakingAnalysisFailureMessage(error, task = null) {
  const rawMessage = task ? speakingTaskStatusText(task) : (error instanceof Error ? error.message : String(error || ""));
  const message = String(rawMessage || "").trim();
  if (
    message.includes("没有拿到文字稿")
    || message.includes("没有文字稿")
    || message.includes("Missing transcript")
    || message.includes("服务端 ASR")
    || message.includes("ASR")
  ) {
    return "录音已保存，但没有拿到可评分的文字稿。请先开启或修复 ASR/浏览器转写，再重试分析。";
  }
  return message || "AI 分析没有生成报告，可以重试分析。";
}

function handleSpeakingAnalysisFailure(error, attemptId = state.attempt?.id || "", options = {}) {
  if (state.userExitedPractice || state.abortingAttemptId === attemptId) {
    setBusy("");
    return;
  }
  clearSpeakingScorePolling();
  if (state.speaking.pendingAnalysis?.attemptId === attemptId) state.speaking.pendingAnalysis = null;
  const isCurrentAttempt = !attemptId || state.attempt?.id === attemptId;
  const message = speakingAnalysisFailureMessage(error, options.task || null);
  setBusy("");
  setDictationStatus("", "");
  if (isCurrentAttempt && isPracticeView(state.view)) {
    state.status = "analysis_failed";
    state.currentTurn = null;
    state.practiceLocked = false;
    updateSidebarLock();
    $("exitPractice")?.classList.add("hidden");
    setRecordButton("analysis_failed", "重新分析", "本次录音已保存，点击重新生成报告。");
    text("recordStatus", message);
    text("phaseLabel", "分析失败");
    $("summaryPanel")?.classList.remove("hidden");
    const panel = $("summaryPanel");
    if (panel) {
      panel.innerHTML = `<p class="error">${escapeHtml(message)}</p>`;
    }
    return;
  }
  showError(error);
}

function clearSpeakingScorePolling() {
  if (state.speaking.scorePollTimer) {
    clearTimeout(state.speaking.scorePollTimer);
    state.speaking.scorePollTimer = null;
  }
  state.speaking.scorePollingTaskId = null;
}

function startSpeakingScorePolling(taskId, attemptId) {
  if (!taskId) return;
  clearSpeakingScorePolling();
  state.speaking.scorePollingTaskId = taskId;
  const poll = async () => {
    try {
      const task = await api(`/api/ai/tasks/${taskId}`);
      if (state.speaking.scorePollingTaskId !== taskId) return;
      if (isSpeakingTaskActive(task)) {
        text("recordStatus", speakingTaskStatusTitle(task));
        text("phaseLabel", "Analyzing");
        state.speaking.scorePollTimer = setTimeout(poll, 2500);
        return;
      }
      clearSpeakingScorePolling();
      const attempt = task?.result_payload?.attempt || null;
      if (task?.status === "succeeded" && attempt?.id) {
        if (state.speaking.pendingAnalysis?.attemptId === attemptId) state.speaking.pendingAnalysis = null;
        const isCurrentAttempt = state.attempt?.id === attemptId;
        if (isCurrentAttempt) {
          state.attempt = attempt;
          state.status = "summary";
          setRecordButton("summary", "Start Again", "Record another section.");
          text("recordStatus", "Section report is ready.");
          text("phaseLabel", "Scored");
        }
        state.historyDetailCache.set(attempt.id, attempt);
        await loadHistory(false);
        showSpeakingScoreCompleteModal(attempt);
        return;
      }
      if (state.speaking.pendingAnalysis?.attemptId === attemptId) state.speaking.pendingAnalysis = null;
      handleSpeakingAnalysisFailure(new Error(speakingTaskStatusText(task)), attemptId, { task });
    } catch (error) {
      clearSpeakingScorePolling();
      if (state.speaking.pendingAnalysis?.attemptId === attemptId) state.speaking.pendingAnalysis = null;
      if (error?.status === 401) {
        showError(error);
        return;
      }
      handleSpeakingAnalysisFailure(error, attemptId);
    }
  };
  poll();
}

function updateSidebarLock() {
  const locked = !!state.practiceLocked;
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.disabled = false;
    button.setAttribute("aria-disabled", locked ? "true" : "false");
    button.classList.toggle("locked", locked);
  });
  const hint = $("navLockHint");
  hint?.classList.add("hidden");
  $("viewTitleBlock")?.classList.toggle("locked-flow", locked);
}

function showNavLockHint(button) {
  const hint = $("navLockHint");
  if (!hint || !button) return;
  const nav = button.closest(".nav");
  if (!nav) return;
  const buttonRect = button.getBoundingClientRect();
  const navRect = nav.getBoundingClientRect();
  hint.textContent = "Practice is active. Click the X to end it before switching views.";
  hint.style.top = `${Math.max(12, buttonRect.top - navRect.top + buttonRect.height + 8)}px`;
  hint.classList.remove("hidden", "toast-hide");
  void hint.offsetWidth;
  hint.classList.add("toast-show");
  clearTimeout(state.navToastTimer);
  state.navToastTimer = window.setTimeout(() => {
    hint.classList.add("toast-hide");
    hint.classList.remove("toast-show");
  }, 1400);
  window.setTimeout(() => {
    hint.classList.add("hidden");
  }, 2000);
}

function scrollToSummary() {
  $("summaryPanel")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function realtimeMetricElapsed(fromKey, toKey = "") {
  const metrics = state.speaking.realtimePcmMetrics || {};
  const from = Number(metrics[fromKey] || 0);
  const to = toKey ? Number(metrics[toKey] || 0) : Date.now();
  return from > 0 && to > 0 ? Math.max(0, to - from) : 0;
}

function recordRealtimePhaseMetric(patch = {}) {
  if (!state.speaking.realtimePcmMetrics?.enabled) return;
  state.speaking.realtimePcmMetrics = {
    ...(state.speaking.realtimePcmMetrics || {}),
    ...patch,
    updatedAt: Date.now(),
  };
  window.__ieltsRealtimePhase2Metrics = { ...state.speaking.realtimePcmMetrics };
  setRealtimePcmStatus(state.speaking.realtimePcmMetrics);
}

function isRealtimeTranscriptSource(source = state.transcriptSource) {
  return Boolean(source && source !== "browser_dictation");
}

function shouldApplyBrowserDictationResult() {
  if (!isRealtimeTranscriptSource()) return true;
  return !state.transcript;
}

function startDictation() {
  if (state.speaking.captureDevice?.avoidBrowserDictation) {
    state.dictationShouldRun = false;
    state.dictationStopping = false;
    state.dictationRecognition = null;
    state.transcriptStatus = "missing";
    setDictationStatus("unavailable", "蓝牙耳机兼容模式：浏览器转写已关闭，避免系统重新启用蓝牙耳机麦克风。录音仍会保存；开启 Realtime ASR 时会使用所选麦克风。");
    traceExaminerAudio("dictation:skipped-for-bluetooth-input-compat", {
      captureDevice: state.speaking.captureDevice || null,
    });
    return;
  }
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    state.transcriptStatus = "missing";
    setDictationStatus("unavailable", "当前浏览器不支持实时转写；录音会保存，但报告可能缺少文字稿。");
    return;
  }
  if (state.dictationRestartTimer) {
    window.clearTimeout(state.dictationRestartTimer);
    state.dictationRestartTimer = null;
  }
  state.dictationShouldRun = true;
  state.dictationStopping = false;
  const recognition = new SpeechRecognition();
  state.dictationRecognition = recognition;
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";
  setDictationStatus("listening", state.dictationRestartCount
    ? `浏览器转写已重新监听 ${state.dictationRestartCount} 次，可以继续说。`
    : "浏览器转写正在监听，请直接开口回答。");
  recognition.onresult = (event) => {
    let interim = "";
    let finalText = state.transcriptFinal || "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      const textValue = result[0]?.transcript || "";
      if (result.isFinal) {
        finalText = `${finalText} ${textValue}`.trim();
      } else {
        interim = textValue;
      }
    }
    const transcript = [finalText, interim].filter(Boolean).join(" ").trim();
    const transcriptStatus = finalText ? "captured" : (interim ? "interim_fallback" : "missing");
    if (!shouldApplyBrowserDictationResult()) {
      if (transcript) {
        setDictationStatus("listening", "服务端实时转写优先，浏览器转写继续作为兜底监听。");
      }
      return;
    }
    state.transcriptFinal = finalText;
    state.transcriptInterim = interim;
    state.transcript = transcript;
    state.transcriptStatus = transcriptStatus;
    if (state.transcript) state.transcriptSource = "browser_dictation";
    if (state.transcriptStatus === "captured") {
      setDictationStatus("captured", "已捕捉到转写，继续说即可。");
    } else if (state.transcriptStatus === "interim_fallback") {
      setDictationStatus("listening", "正在捕捉这段回答，停止后会保存最后结果。");
    }
  };
  recognition.onerror = (event) => {
    state.dictationLastError = event?.error || "";
    state.transcriptStatus = state.transcript ? state.transcriptStatus : "missing";
    if (["not-allowed", "service-not-allowed", "audio-capture"].includes(state.dictationLastError)) {
      state.dictationShouldRun = false;
      setDictationStatus("unavailable", "浏览器转写没有可用权限；录音仍会保存，但这题可能没有文字稿。");
      return;
    }
    setDictationStatus("reconnecting", "浏览器转写刚刚中断，正在自动重新监听。");
  };
  recognition.onend = () => {
    if (state.dictationShouldRun && !state.dictationStopping && state.status === "recording") {
      state.dictationRestartCount += 1;
      setDictationStatus("reconnecting", "浏览器转写因静音或网络波动结束，正在自动重新监听。");
      state.dictationRestartTimer = window.setTimeout(() => startDictation(), 250);
      return;
    }
    state.dictationRecognition = null;
    state.dictationShouldRun = false;
    state.dictationStopping = false;
    resolveDictationWait();
  };
  try {
    recognition.start();
  } catch {
    state.transcriptStatus = "missing";
    setDictationStatus("reconnecting", "浏览器转写启动失败，正在尝试重新监听。");
    if (state.dictationShouldRun && state.status === "recording") {
      state.dictationRestartCount += 1;
      state.dictationRestartTimer = window.setTimeout(() => startDictation(), 500);
    }
  }
}

function stopDictation() {
  state.dictationShouldRun = false;
  state.dictationStopping = true;
  setDictationStatus("saving", "正在保存最后一段浏览器转写。");
  if (state.dictationRestartTimer) {
    window.clearTimeout(state.dictationRestartTimer);
    state.dictationRestartTimer = null;
  }
  if (state.dictationRecognition) {
    try {
      state.dictationRecognition.stop();
    } catch {
      // ignore
    }
    window.setTimeout(resolveDictationWait, 800);
    return;
  }
  resolveDictationWait();
}

function setDictationStatus(kind, message) {
  const el = $("dictationStatus");
  if (!el) return;
  if (!message) {
    el.className = "dictation-status hidden";
    el.textContent = "";
    return;
  }
  el.className = `dictation-status ${kind || "info"}`;
  el.textContent = message;
}

function setRealtimePcmStatus(metrics = {}) {
  const el = $("realtimePcmStatus");
  if (!el) return;
  if (!metrics.enabled) {
    el.className = "realtime-pcm-status hidden";
    el.textContent = "";
    return;
  }

  const status = String(metrics.status || "");
  const asrStatus = String(metrics.asrStatus || "");
  const framesSent = Number(metrics.framesSent || 0);
  const framesAcked = Number(metrics.framesAcked || 0);
  const droppedFrames = Number(metrics.droppedFrames || 0);
  const source = String(metrics.transcriptSource || state.transcriptSource || "browser_dictation");
  const latencyParts = [];
  if (Number(metrics.socketOpenMs || 0) > 0) latencyParts.push(`WS ${Math.round(metrics.socketOpenMs)}ms`);
  if (Number(metrics.firstTranscriptMs || 0) > 0) latencyParts.push(`首字 ${Math.round(metrics.firstTranscriptMs)}ms`);
  if (Number(metrics.finalTranscriptMs || 0) > 0) latencyParts.push(`final ${Math.round(metrics.finalTranscriptMs)}ms`);
  if (Number(metrics.followUpFirstChunkAfterStopMs || 0) > 0) {
    latencyParts.push(`追问首字 ${Math.round(metrics.followUpFirstChunkAfterStopMs)}ms`);
  }
  if (Number(metrics.followUpTtsReadyAfterStopMs || 0) > 0) {
    latencyParts.push(`TTS ${Math.round(metrics.followUpTtsReadyAfterStopMs)}ms`);
  }
  if (Number(metrics.followUpExaminerStartAfterStopMs || 0) > 0) {
    latencyParts.push(`考官 ${Math.round(metrics.followUpExaminerStartAfterStopMs)}ms`);
  }

  let tone = "info";
  let headline = "Realtime ASR";
  if (status === "asr_not_configured" || status === "asr_status_error") {
    tone = "fallback";
    headline = "Realtime ASR 未启用";
  } else if (status === "open" || asrStatus === "started" || asrStatus === "interim" || asrStatus === "final" || asrStatus === "done") {
    tone = "live";
    headline = "Realtime ASR 已连接";
  } else if (status === "error" || asrStatus === "error") {
    tone = "fallback";
    headline = "Realtime ASR 降级";
  }

  const detail = [
    headline,
    `source ${source}`,
    `frames ${framesSent}/${framesAcked}`,
    droppedFrames ? `dropped ${droppedFrames}` : "",
    latencyParts.join(" · "),
  ].filter(Boolean).join(" · ");
  el.className = `realtime-pcm-status ${tone}`;
  el.textContent = detail;
}

function waitForFinalDictation() {
  if (!state.dictationRecognition) return Promise.resolve();
  if (state.dictationFinalWait) return state.dictationFinalWaitPromise;
  state.dictationFinalWaitPromise = new Promise((resolve) => {
    state.dictationFinalWait = resolve;
  });
  return state.dictationFinalWaitPromise;
}

function resolveDictationWait() {
  if (state.dictationFinalWait) {
    const resolve = state.dictationFinalWait;
    state.dictationFinalWait = null;
    state.dictationFinalWaitPromise = null;
    resolve();
  }
}

function renderSummary(attempt) {
  const score = attempt.ielts_score || {};
  const summaryPanel = $("summaryPanel");
  const summaryOverlay = $("summaryOverlay");
  if (!summaryPanel) return;

  summaryPanel.innerHTML = `
    <div class="score-row">
      ${scoreCell("Overall", score.overall_band)}
      ${scoreCell("Fluency", score.fluency_coherence)}
      ${scoreCell("Lexical", score.lexical_resource)}
      ${scoreCell("Grammar", score.grammatical_range)}
    </div>
    <p class="feedback">${escapeHtml(attempt.feedback_summary || "No feedback generated.")}</p>
    <div class="summary-actions">
      <button id="viewDetails">View Details</button>
      <button id="closeSummary" class="ghost">Close</button>
    </div>
  `;

  // Show panel and overlay
  summaryPanel.classList.remove("hidden");
  summaryPanel.classList.add("visible");
  if (summaryOverlay) {
    summaryOverlay.classList.remove("hidden");
    summaryOverlay.classList.add("visible");
  }

  const viewDetails = byId("viewDetails");
  if (viewDetails) {
    viewDetails.addEventListener("click", () => {
      hideSummary();
      renderDetail(attempt);
    });
  }

  const closeSummary = byId("closeSummary");
  if (closeSummary) {
    closeSummary.addEventListener("click", hideSummary);
  }
}

function hideSummary() {
  const summaryPanel = $("summaryPanel");
  const summaryOverlay = $("summaryOverlay");
  if (summaryPanel) {
    summaryPanel.classList.remove("visible");
    summaryPanel.classList.add("hidden");
  }
  if (summaryOverlay) {
    summaryOverlay.classList.remove("visible");
    summaryOverlay.classList.add("hidden");
  }
}

function scoreCell(label, value, caption = "") {
  const captionHtml = caption ? `<small>${escapeHtml(caption)}</small>` : "";
  return `<div class="score-cell"><span>${escapeHtml(label)}${captionHtml}</span><strong>${escapeHtml(value ?? "—")}</strong></div>`;
}

function centeredLoadingHtml(title = "正在加载", detail = "请稍等。") {
  return `
    <div class="page-center-loading" role="status" aria-live="polite">
      <div>
        <span class="spinner"></span>
        <div>
          <strong>${escapeHtml(title)}</strong>
          <span>${escapeHtml(detail)}</span>
        </div>
      </div>
    </div>
  `;
}

function setWritingSwitchState(selector, taskType) {
  const activeTask = taskType === "task2" ? "task2" : "task1";
  document.querySelectorAll(selector).forEach((switchEl) => {
    switchEl.dataset.activeTask = activeTask;
  });
}

function setWritingPageLoading(isLoading, title = "正在加载每日写作", detail = "正在读取题库、签到和草稿。") {
  const panel = $("writingPanel");
  if (!panel) return;
  panel.classList.toggle("is-loading", Boolean(isLoading));
  let loading = panel.querySelector(":scope > .page-center-loading");
  if (isLoading) {
    if (!loading) {
      loading = document.createElement("div");
      panel.appendChild(loading);
    }
    loading.outerHTML = centeredLoadingHtml(title, detail);
  } else {
    loading?.remove();
  }
}

async function loadHistory(showBusy = true) {
  const navScroll = captureNavScrollState();
  const action = async () => {
    if (state.historyItems.length) renderHistoryList(state.historyItems, { refreshActive: true });
    const payload = await api("/api/history");
    state.historyItems = payload.items || [];
    renderHistoryList(state.historyItems);
  };
  const currentActiveId = state.activeHistoryId && state.historyItems.some((item) => item.id === state.activeHistoryId)
    ? state.activeHistoryId
    : state.historyItems[0]?.id;
  const panel = $("historyPanel");
  if (showBusy && (!currentActiveId || !state.historyDetailCache.has(currentActiveId))) {
    panel?.classList.add("is-loading");
    $("detailPanel").innerHTML = centeredLoadingHtml("正在加载口语报告", "正在读取历史记录和报告详情。");
  }
  try {
    return await action();
  } finally {
    panel?.classList.remove("is-loading");
    restoreNavScrollState(navScroll);
  }
}

function updateReportRailState(listId) {
  const list = byId(listId);
  const shell = list?.closest(".history-rail-shell");
  if (!list || !shell) return;
  const maxScroll = Math.max(0, list.scrollWidth - list.clientWidth);
  const atStart = list.scrollLeft <= 2;
  const atEnd = maxScroll <= 2 || list.scrollLeft >= maxScroll - 2;
  shell.classList.toggle("at-start", atStart);
  shell.classList.toggle("at-end", atEnd);
  shell.querySelector(".history-rail-nav:first-of-type")?.toggleAttribute("disabled", atStart);
  shell.querySelector(".history-rail-nav:last-of-type")?.toggleAttribute("disabled", atEnd);
}

function scrollReportRail(listId, direction) {
  const list = byId(listId);
  if (!list) return;
  const step = Math.max(260, Math.floor(list.clientWidth * 0.45));
  list.scrollBy({ left: direction * step, behavior: "smooth" });
  window.setTimeout(() => updateReportRailState(listId), 220);
}

function setupReportRails() {
  [
    ["historyList", "historyRailPrev", "historyRailNext"],
    ["writingReportList", "writingReportRailPrev", "writingReportRailNext"],
  ].forEach(([listId, prevId, nextId]) => {
    const list = byId(listId);
    if (!list || list.dataset.railBound === "true") return;
    list.dataset.railBound = "true";
    list.addEventListener("scroll", () => updateReportRailState(listId), { passive: true });
    byId(prevId)?.addEventListener("click", () => scrollReportRail(listId, -1));
    byId(nextId)?.addEventListener("click", () => scrollReportRail(listId, 1));
    updateReportRailState(listId);
  });
}

function renderHistoryList(items, options = {}) {
  const refreshActive = options.refreshActive !== false;
  if (!items.length) {
    $("historyList").textContent = "No attempts yet.";
    $("detailPanel").innerHTML = '<h2>Attempt Details</h2><p class="muted">No attempts to display.</p>';
    updateReportRailState("historyList");
    return;
  }
  $("historyList").innerHTML = items.map((item) => {
    const part = (item.mode || item.part || "").toLowerCase();
    const tagClass = isSpeakingPartView(part) ? part : "";
    const toneClass = part === "mock" ? "tone-mock" : `tone-${tagClass || "neutral"}`;
    return `
    <div class="history-item-wrap">
      <button class="history-item ${toneClass} ${state.activeHistoryId === item.id ? "active" : ""}" data-attempt-id="${escapeHtml(item.id)}">
        <div class="history-item-top">
          <span class="history-item-tag ${tagClass}">${escapeHtml(part.toUpperCase())}</span>
          <span class="history-item-band">Band ${escapeHtml(item.overall_band ?? "—")}</span>
        </div>
        <strong class="history-item-title">${escapeHtml(item.title || item.question || "Untitled")}</strong>
        <small class="history-item-time">${escapeHtml(formatReportTime(item.display_time || item.timestamp || ""))}</small>
      </button>
      <button class="history-item-menu-btn" data-attempt-id="${escapeHtml(item.id)}" aria-label="More options" title="More options">
        <span aria-hidden="true"></span>
      </button>
    </div>
  `;}).join("");
  document.querySelectorAll(".history-item").forEach((button) => {
    button.addEventListener("click", async () => {
      if (state.activeHistoryId === button.dataset.attemptId) return;
      state.activeHistoryId = button.dataset.attemptId;
      syncUrlForCurrentState();
      document.querySelectorAll(".history-item").forEach((item) => {
        item.classList.toggle("active", item.dataset.attemptId === state.activeHistoryId);
      });
      const cached = state.historyDetailCache.get(button.dataset.attemptId);
      if (cached) {
        renderDetail(cached, false);
        return;
      }
      $("detailPanel").innerHTML = centeredLoadingHtml("正在加载口语报告", "报告内容首次打开需要从服务端读取。");
      fetchHistoryDetail(button.dataset.attemptId)
        .then((detail) => {
          if (detail && state.activeHistoryId === button.dataset.attemptId) renderDetail(detail, false);
        })
        .catch(showError);
    });
  });
  document.querySelectorAll(".history-item-menu-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      showHistoryItemMenu(btn, btn.dataset.attemptId);
    });
  });
  if (state.activeHistoryId && !items.some((item) => item.id === state.activeHistoryId)) {
    state.activeHistoryId = null;
  }
  if (!state.activeHistoryId && items.length) {
    state.activeHistoryId = items[0].id;
    document.querySelector(".history-item")?.classList.add("active");
    syncUrlForCurrentState({ replace: true });
  }
  requestAnimationFrame(() => updateReportRailState("historyList"));
  if (refreshActive && state.activeHistoryId) {
    const cached = state.historyDetailCache.get(state.activeHistoryId);
    if (cached) {
      renderDetail(cached, false, { preserveScroll: true });
      return;
    }
    $("detailPanel").innerHTML = centeredLoadingHtml("正在加载口语报告", "报告内容首次打开需要从服务端读取。");
    fetchHistoryDetail(state.activeHistoryId)
      .then((detail) => {
        if (detail && state.activeHistoryId === detail.id) renderDetail(detail, false);
      })
      .catch(showError);
  }
}

function showHistoryItemMenu(anchor, attemptId) {
  closeHistoryItemMenu();
  const menu = document.createElement("div");
  menu.className = "history-item-menu";
  menu.innerHTML = `<button class="history-menu-delete" data-attempt-id="${escapeHtml(attemptId)}">删除</button>`;
  anchor.parentElement.appendChild(menu);
  menu.querySelector(".history-menu-delete").addEventListener("click", (e) => {
    e.stopPropagation();
    closeHistoryItemMenu();
    showDeleteConfirm(attemptId);
  });
  setTimeout(() => document.addEventListener("click", closeHistoryItemMenu, { once: true }), 0);
}

function closeHistoryItemMenu() {
  document.querySelectorAll(".history-item-menu").forEach((el) => el.remove());
}

function showDeleteConfirm(attemptId) {
  showConfirmDelete("确定要删除这条练习记录吗？", async () => {
    try {
      if (state.activeHistoryId === attemptId) {
        $("detailPanel").innerHTML = centeredLoadingHtml("正在删除报告", "删除完成后会自动刷新列表。");
      }
      await api(`/api/history/${attemptId}`, null, { method: "DELETE" });
      if (state.activeHistoryId === attemptId) state.activeHistoryId = null;
      state.historyDetailCache.delete(attemptId);
      await loadHistory(false);
    } catch (err) {
      showError(err);
    }
  });
}

function showConfirmDelete(message, onConfirm) {
  const overlay = document.createElement("div");
  overlay.className = "confirm-overlay";
  overlay.innerHTML = `
    <div class="confirm-dialog">
      <p>${escapeHtml(message)}</p>
      <div class="confirm-actions">
        <button class="confirm-cancel" type="button">取消</button>
        <button class="confirm-delete" type="button">删除</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.querySelector(".confirm-cancel").addEventListener("click", () => overlay.remove());
  overlay.querySelector(".confirm-delete").addEventListener("click", async () => {
    overlay.remove();
    try {
      await onConfirm();
    } catch (error) {
      showError(error);
    }
  });
}

function currentWritingWordCount() {
  return writingWordCountForValue($("writingAnswer")?.value || "");
}

function writingParagraphs(value) {
  return String(value || "").split(/\n\s*\n+/).map((item) => item.trim()).filter(Boolean);
}

function writingAnnotationTypeLabel(type) {
  return {
    spelling: "\u62fc\u5199",
    punctuation: "\u6807\u70b9",
    format: "\u683c\u5f0f",
    grammar: "\u8bed\u6cd5",
    word_choice: "\u7528\u8bcd",
    missing_word: "\u7f3a\u8bcd",
    extra_word: "\u591a\u4f59",
  }[type] || "\u95ee\u9898";
}

function normalizeWritingAnnotation(item = {}) {
  const original = String(item.original || "").trim();
  if (!original) return null;
  const rawType = String(item.type || item.category || "grammar").trim().toLowerCase();
  const type = ["spelling", "punctuation", "format", "grammar", "word_choice", "missing_word", "extra_word"].includes(rawType) ? rawType : "grammar";
  const paragraphIndex = Number.parseInt(item.paragraph_index ?? item.paragraphIndex ?? "", 10);
  return {
    paragraphIndex: Number.isFinite(paragraphIndex) ? paragraphIndex : null,
    original,
    type,
    suggestion: String(item.suggestion || "").trim(),
    explanation: String(item.explanation || item.reason || "").trim(),
    severity: String(item.severity || "medium").trim().toLowerCase(),
  };
}

function writingInlineAnnotations(score = {}) {
  const annotations = [];
  if (Array.isArray(score.inline_annotations)) {
    score.inline_annotations.forEach((item) => {
      const normalized = normalizeWritingAnnotation(item);
      if (normalized) annotations.push(normalized);
    });
  }
  if (!annotations.length && Array.isArray(score.grammar_corrections)) {
    score.grammar_corrections.forEach((item) => {
      const normalized = normalizeWritingAnnotation({
        ...item,
        type: item.type || "grammar",
        explanation: item.explanation || item.reason || "",
      });
      if (normalized) annotations.push(normalized);
    });
  }
  const seen = new Set();
  return annotations.filter((item) => {
    const key = `${item.paragraphIndex || ""}:${item.type}:${item.original}:${item.suggestion}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function writingAnnotationsForParagraph(annotations, paragraph, paragraphIndex) {
  const text = String(paragraph || "");
  return annotations.filter((item) => {
    if (item.paragraphIndex && item.paragraphIndex !== paragraphIndex) return false;
    return text.includes(item.original);
  });
}

function renderWritingAnnotatedText(textValue, annotations = []) {
  const text = String(textValue || "");
  const ranges = [];
  annotations.forEach((annotation) => {
    let start = text.indexOf(annotation.original);
    while (start >= 0) {
      const end = start + annotation.original.length;
      const overlaps = ranges.some((range) => start < range.end && end > range.start);
      if (!overlaps) {
        ranges.push({ start, end, annotation });
        break;
      }
      start = text.indexOf(annotation.original, start + 1);
    }
  });
  if (!ranges.length) return escapeHtml(text).replace(/\n/g, "<br>");
  ranges.sort((a, b) => a.start - b.start || b.end - a.end);
  let cursor = 0;
  let html = "";
  ranges.forEach(({ start, end, annotation }) => {
    if (start < cursor) return;
    const label = writingAnnotationTypeLabel(annotation.type);
    const detail = [label, annotation.suggestion ? `\u5efa\u8bae\uff1a${annotation.suggestion}` : "", annotation.explanation].filter(Boolean).join(" \u00b7 ");
    html += escapeHtml(text.slice(cursor, start)).replace(/\n/g, "<br>");
    const original = escapeHtml(text.slice(start, end)).replace(/\n/g, "<br>");
    if (annotation.type === "missing_word") {
      html += `${original}<mark class="writing-inline-insert" title="${escapeHtml(detail)}" tabindex="0">^ ${escapeHtml(annotation.suggestion || "\u8865\u8bcd")}</mark>`;
    } else if (annotation.type === "spelling" && annotation.suggestion) {
      html += `<span class="writing-inline-replacement" title="${escapeHtml(detail)}" tabindex="0"><mark class="writing-inline-issue writing-inline-issue-spelling">${original}</mark><span class="writing-inline-arrow">→</span><span class="writing-inline-suggestion">${escapeHtml(annotation.suggestion)}</span></span>`;
    } else {
      html += `<mark class="writing-inline-issue writing-inline-issue-${escapeHtml(annotation.type)}" title="${escapeHtml(detail)}" tabindex="0">${original}</mark>`;
    }
    cursor = end;
  });
  html += escapeHtml(text.slice(cursor)).replace(/\n/g, "<br>");
  return html;
}

function parseWritingSpellingSummary(value = "") {
  const groups = [];
  let current = null;
  const genericTitles = new Set(["拼写纠错", "拼写纠正", "spelling corrections", "spelling correction"]);
  const isGenericTitle = (title = "") => genericTitles.has(String(title || "").trim().toLowerCase());
  const inferredGroupTitle = (wrong = "", correct = "") => {
    const left = String(wrong || "").trim();
    const right = String(correct || "").trim();
    const lowerLeft = left.toLowerCase();
    const lowerRight = right.toLowerCase();
    const sortedLeft = lowerLeft.split("").sort().join("");
    const sortedRight = lowerRight.split("").sort().join("");
    const editDistance = (a, b) => {
      const previous = Array.from({ length: b.length + 1 }, (_, index) => index);
      for (let i = 1; i <= a.length; i += 1) {
        const currentRow = [i];
        for (let j = 1; j <= b.length; j += 1) {
          currentRow[j] = a[i - 1] === b[j - 1]
            ? previous[j - 1]
            : Math.min(previous[j - 1], previous[j], currentRow[j - 1]) + 1;
        }
        previous.splice(0, previous.length, ...currentRow);
      }
      return previous[b.length];
    };
    if (left && right && lowerLeft === lowerRight && left !== right) return "大小写类错误";
    if (sortedLeft === sortedRight || editDistance(lowerLeft, lowerRight) <= 2) return "字母顺序 / 字母遗漏类错误";
    return "词形记忆混淆类错误";
  };
  const ensureGroup = (title = "拼写纠错") => {
    const existing = groups.find((group) => group.title === title);
    if (existing) {
      current = existing;
      return current;
    }
    if (!current || current.title !== title) {
      current = { title, items: [] };
      groups.push(current);
    }
    return current;
  };
  String(value || "").split(/\r?\n/).forEach((rawLine) => {
    const line = String(rawLine || "").trim();
    if (!line) return;
    const plain = line
      .replace(/^#{1,6}\s*/, "")
      .replace(/^\*\*(.*)\*\*$/, "$1")
      .trim();
    const entry = plain
      .replace(/^[-*]\s+/, "")
      .replace(/^\d+[.)、]\s*/, "")
      .trim();
    const match = entry.match(/`?([A-Za-z][A-Za-z'-]*)`?\s*(?:->|→)\s*(?:正确\s*[:：]\s*)?`?([A-Za-z][A-Za-z'-]*)`?\s*(?:[（(]([^）)]*)[）)])?/);
    if (match) {
      const targetGroup = current && !isGenericTitle(current.title)
        ? current
        : ensureGroup(inferredGroupTitle(match[1], match[2]));
      targetGroup.items.push({
        wrong: match[1],
        correct: match[2],
        note: String(match[3] || "").trim(),
      });
      return;
    }
    if (!entry.includes("->") && !entry.includes("→")) {
      current = isGenericTitle(entry) ? null : ensureGroup(entry);
    }
  });
  return groups
    .map((group) => ({ ...group, items: group.items.filter((item) => item.wrong && item.correct) }))
    .filter((group) => group.items.length);
}

function writingSpellingCardsHtml(spelling = "") {
  const groups = parseWritingSpellingSummary(spelling);
  if (!groups.length) return "";
  return `
    <div class="writing-spelling-corrections">
      ${groups.map((group) => `
        <section class="writing-spelling-correction-group">
          <h4>${escapeHtml(group.title)}</h4>
          <div class="writing-spelling-correction-list">
            ${group.items.map((item) => `
              <article class="writing-spelling-correction-row">
                <span class="writing-spelling-token writing-spelling-token-wrong">${escapeHtml(item.wrong)}</span>
                <span class="writing-spelling-correction-arrow" aria-hidden="true">→</span>
                <span class="writing-spelling-token writing-spelling-token-correct">${escapeHtml(item.correct)}</span>
                ${item.note ? `<div class="writing-spelling-note">${escapeHtml(item.note)}</div>` : ""}
              </article>
            `).join("")}
          </div>
        </section>
      `).join("")}
    </div>
  `;
}

function writingSpellingSummaryHtml(score = {}) {
  const spelling = String(score.spelling_correction_summary || "").trim();
  if (!spelling) return "";
  const cardsHtml = writingSpellingCardsHtml(spelling);
  return `
    <div class="detail-card writing-language-summary-card writing-spelling-summary-card">
      <section>
        <span class="section-label">Spelling corrections</span>
        <h3>拼写纠错</h3>
        ${cardsHtml || `<div class="coaching-content">${renderMarkdown(spelling)}</div>`}
      </section>
    </div>
  `;
}

function writingSpellingTermsFromSummary(value = "") {
  const terms = new Set();
  String(value || "").replace(/`?([A-Za-z]{2,})`?\s*(?:->|→)/g, (_, term) => {
    terms.add(String(term || "").toLowerCase());
    return "";
  });
  return terms;
}

function looksLikeSingleWordSpellingFix(value = "") {
  const compact = String(value || "").replace(/`/g, "").trim().replace(/[。.]+$/g, "").trim();
  const arrow = compact.includes("->") ? "->" : (compact.includes("→") ? "→" : "");
  if (!arrow) return false;
  const [left, ...rest] = compact.split(arrow);
  let right = rest.join(arrow).trim();
  ["正确：", "正确:", "correct:", "Correct:"].forEach((prefix) => {
    if (right.startsWith(prefix)) right = right.slice(prefix.length).trim();
  });
  right = right.split("（")[0].split("(")[0].trim();
  return /^[A-Za-z]{2,}$/.test(left.trim()) && /^[A-Za-z]{2,}$/.test(right);
}

function stripSpellingFromLanguageUpgrade(value = "", spellingSummary = "") {
  const spellingTerms = ["拼写", "错拼", "错别字", "spelling", "misspell", "typo"];
  const summaryTerms = writingSpellingTermsFromSummary(spellingSummary);
  return String(value || "").split(/\r?\n/).filter((line) => {
    const lowered = line.toLowerCase();
    if (spellingTerms.some((term) => lowered.includes(term))) return false;
    if ([...summaryTerms].some((term) => new RegExp(`\\b${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`).test(lowered))) return false;
    const compact = line.trim().replace(/^[-*•\s]+/, "");
    return !looksLikeSingleWordSpellingFix(compact);
  }).join("\n").trim();
}

function stripSpellingFromParagraphCoaching(value = "", spellingSummary = "") {
  const summaryTerms = writingSpellingTermsFromSummary(spellingSummary);
  let text = String(value || "").trim();
  text = text
    .replace(/[，,；;]?\s*但?有(?:明显)?拼写错误[，,]?\s*而且?/g, "，")
    .replace(/[，,；;]?\s*存在(?:明显)?拼写错误[，,。；;]?/g, "。")
    .replace(/[，,；;]?\s*拼写(?:方面)?(?:也)?(?:需要|可以|应当)?(?:再)?(?:检查|注意|修改|纠正)[，,。；;]?/g, "。");
  return text.split(/\r?\n/).filter((line) => {
    const lowered = line.toLowerCase();
    return ![...summaryTerms].some((term) => new RegExp(`\\b${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`).test(lowered));
  }).join("\n").replace(/，。/g, "。").replace(/^[ ，,]+|[ ，,]+$/g, "").trim();
}

function writingParagraphCoachingMarkdown(item = {}, score = {}) {
  const coaching = stripSpellingFromParagraphCoaching(
    item.coaching || "暂无段落辅导。",
    score.spelling_correction_summary || ""
  ) || "暂无段落辅导。";
  const content = stripSpellingFromLanguageUpgrade(
    item.language_correction_upgrade || item.expression_upgrade || "",
    score.spelling_correction_summary || ""
  );
  if (!content) return coaching;
  return `${coaching}\n\n**语法纠错 / 表达纠错 / 表达升级**\n${content}`;
}

function writingParagraphGuidance(taskType = state.writing.taskType || "task1_academic") {
  if (taskType === "task1_academic") {
    return {
      title: "Task 1 需要先分段",
      message: "Task 1 评分会看 Overview 和细节组织。请先把作文分成 3-4 段，再让 AI 分析。",
      tips: [
        "第 1 段：改写题目，说明图表展示什么。",
        "第 2 段：Overview，总结最明显的趋势、对比或关键特征。",
        "第 3-4 段：按类别、时间段或对比关系写主要细节。",
      ],
    };
  }
  return {
    title: "Task 2 需要先分段",
    message: "Task 2 评分会看观点组织和主体段展开。请先把作文分成清楚段落，再让 AI 分析。",
    tips: [
      "第 1 段：引入题目，并给出你的立场或回应方向。",
      "第 2-3 段：每段只讲一个中心观点，用解释和例子展开。",
      "第 4 段：总结立场，不要加入新的大观点。",
    ],
  };
}

function showWritingParagraphModal(guidance = null) {
  const data = guidance || writingParagraphGuidance();
  text("writingParagraphModalTitle", data.title || "先把作文分段");
  text("writingParagraphModalMessage", data.message || "AI 评分前需要先分段。");
  const list = $("writingParagraphTips");
  if (list) list.innerHTML = (data.tips || []).map((tip) => `<li>${escapeHtml(tip)}</li>`).join("");
  $("writingParagraphModal")?.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeWritingParagraphModal() {
  $("writingParagraphModal")?.classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function ensureWritingParagraphsBeforeScore(answer, taskType) {
  if (writingParagraphs(answer).length >= 2) return true;
  showWritingParagraphModal(writingParagraphGuidance(taskType));
  return false;
}

// ─── Writing frames (essay scaffolds) ──────────────────────────────
// /frame  → fills the textarea with a fixed-question-pattern scaffold
// /myframe → opens a modal to customize this pattern's scaffold (saved to localStorage)
const WRITING_FRAME_DEFAULTS = {
  // ── Task 1 Academic ────────────────────────────────────────────
  "task1_academic:line_graph": [
    "The line graph compares [items/groups] in terms of [measurement] over the period from [start year] to [end year].",
    "",
    "Overall, [main trend 1] changed the most noticeably, while [main trend 2] remained comparatively stable. It is also clear that [highest/lowest group] finished the period as the most significant feature of the graph.",
    "",
    "At the beginning of the period, [group A] stood at approximately [number], compared with [number] for [group B]. Over the next [time span], [group A] [rose/fell/fluctuated] to [number], whereas [group B] [changed in a different way], reaching [number].",
    "",
    "The remaining figures show a different pattern. [Group C] [increased/decreased] from [number] to [number], and [group D] ended at about [number]. By [final year], the gap between [two key groups] had [widened/narrowed] to around [number], making this the clearest comparison in the data.",
  ].join("\n"),
  "task1_academic:bar_chart": [
    "The bar chart shows the figures for [categories] in relation to [measurement] in [place/year].",
    "",
    "Overall, [category/group] recorded the highest figure, whereas [category/group] was the lowest. Another clear feature is that [major comparison or pattern across groups].",
    "",
    "Looking first at the larger figures, [category A] reached [number], which was [higher/lower] than [category B] at [number]. [Category C] also performed strongly, with a figure of roughly [number].",
    "",
    "By contrast, the lower figures were seen in [category D] and [category E], at [number] and [number] respectively. This means that [largest category] was about [comparison] as high as [smallest category], showing a clear difference between the top and bottom groups.",
  ].join("\n"),
  "task1_academic:pie_chart": [
    "The pie chart illustrates how [total/market/spending] was divided among [categories] in [year/place].",
    "",
    "Overall, [largest category] made up the largest proportion, while [smallest category] accounted for the smallest share. The chart also shows that [combined pattern, such as two categories dominating the total].",
    "",
    "[Largest category] represented [percentage] of the total, followed by [second category] at [percentage]. Together, these two categories accounted for [combined percentage], which was more than half of the whole figure.",
    "",
    "The remaining shares were smaller. [Category C] stood at [percentage], while [category D] and [category E] made up [percentage] and [percentage] respectively. In particular, [smallest category] was only about [comparison] of [largest category], highlighting the imbalance in the distribution.",
  ].join("\n"),
  "task1_academic:table": [
    "The table compares [items/groups] across [criteria] in [year/place/period].",
    "",
    "Overall, [group/item] performed best in [criterion], whereas [group/item] had the weakest result in [criterion]. A further noticeable pattern is that [general comparison across rows or columns].",
    "",
    "In terms of [criterion 1], [group A] recorded [number], which was [higher/lower] than [group B] at [number]. [Group C] was close behind, with [number], while [group D] had a much lower figure of [number].",
    "",
    "For [criterion 2], the pattern was [similar/different]. [Group/item] reached [number], the highest figure in this column, compared with only [number] for [group/item]. These figures suggest that [main conclusion from the table].",
  ].join("\n"),
  "task1_academic:map": [
    "The maps show how [place] changed between [year 1] and [year 2].",
    "",
    "Overall, the area became [more developed/more modern/more residential], with the most important changes being [major addition] and [major removal/replacement]. However, [feature that stayed the same] remained largely unchanged.",
    "",
    "In [year 1], [main feature] was located in the [north/south/east/west] of the area, while [second feature] stood [near/opposite/beside] it. There was also [road/river/open space/building] in the [position], which shaped the original layout.",
    "",
    "By [year 2], [old feature] had been replaced by [new feature], and [new facility] had been added in the [position]. In addition, [road/building/open area] was [extended/removed/relocated], making the site [clear final description].",
  ].join("\n"),
  "task1_academic:process": [
    "The diagram illustrates the process by which [product/result] is [made/produced/formed].",
    "",
    "Overall, this is a [linear/cyclical] process with [number] main stages, beginning with [first stage] and ending with [final stage]. The most important part of the process is [key transformation].",
    "",
    "At the first stage, [raw material/input] is [collected/placed/prepared] and then [processed] by [machine/person/natural force]. After this, it is [heated/cooled/mixed/transported] to [next stage], where [specific action] takes place.",
    "",
    "In the later stages, [intermediate product] is [treated/combined/shaped] before being [sent/stored/packaged]. Finally, [final product/result] is produced and is ready for [use/distribution/next cycle].",
  ].join("\n"),
  "task1_academic:mixed": [
    "The charts provide information about [topic], showing both [chart 1 focus] and [chart 2 focus].",
    "",
    "Overall, [main pattern from chart 1] is the most noticeable feature, while [main pattern from chart 2] also stands out. Taken together, the two charts suggest that [combined insight].",
    "",
    "In the first chart, [category/group] had the highest figure at [number], whereas [category/group] was much lower at [number]. Another important comparison is that [specific comparison].",
    "",
    "The second chart shows that [main figure/pattern]. [Category/group] accounted for [number/percentage], compared with [number/percentage] for [another category]. This partly explains why [connection between the two charts].",
  ].join("\n"),

  // ── Task 2 ─────────────────────────────────────────────────────
  "task2:agree_disagree": [
    "Some people believe that [main idea in the question]. I [completely/partly] agree with this view, mainly because [reason 1] and [reason 2].",
    "",
    "Firstly, [reason 1 as a clear topic sentence]. This is because [explain the logic in simple terms]. If [people/governments/schools/companies] [do something], they are more likely to [result]. For example, [one concrete example]. Therefore, [link this example back to your opinion].",
    "",
    "Secondly, [reason 2]. Although some people may argue that [opposite idea], this view is less convincing because [weakness of the opposite idea]. In real life, [short example or common situation], so [your position] is more practical and more reasonable.",
    "",
    "In conclusion, I believe that [repeat your position in different words]. The main reasons are that [reason 1 in short] and [reason 2 in short].",
  ].join("\n"),
  "task2:discussion_opinion": [
    "People have different views about [topic]. Some argue that [view A], while others believe that [view B]. I think [your own view] is more reasonable.",
    "",
    "On the one hand, supporters of [view A] may have a valid point. They believe that [reason for view A], because [explanation]. For example, [example that makes this side sound fair]. This is why some people see [view A] as a practical solution.",
    "",
    "On the other hand, I side more with [view B / your view]. The main reason is that [reason for your preferred side]. This means that [explain impact]. For instance, [example]. Compared with the first view, this approach deals better with [deeper problem or long-term need].",
    "",
    "In conclusion, both views have some logic, but I believe [your preferred view] is stronger. This is because [final reason linked directly to the question].",
  ].join("\n"),
  "task2:positive_negative": [
    "[Development from the question] has become increasingly common. In my view, this is mainly a [positive/negative] development because [reason 1] and [reason 2].",
    "",
    "The first reason is that [reason 1]. This matters because [explanation of the impact]. For example, [specific example]. This shows that the change can [positive/negative result] in a practical way.",
    "",
    "Another important point is [reason 2]. Although some people may worry that [opposite concern], this concern is less important because [your response]. In many cases, [condition/example], so the overall effect is still [positive/negative].",
    "",
    "In conclusion, I believe this is a [positive/negative] development. The main reason is that [final reason linked directly to the change in the question].",
  ].join("\n"),
  "task2:problem_solution": [
    "[Problem from the question] has become increasingly common in many places. The main reasons are [cause 1] and [cause 2], and the problem can be reduced by [solution 1] and [solution 2].",
    "",
    "One major cause is [cause 1]. When [people/companies/governments] [action], it often leads to [negative result], because [explanation]. Another cause is [cause 2]. For example, [specific example showing how the problem happens]. As a result, [state the wider consequence].",
    "",
    "To deal with this issue, [actor] should first [solution 1]. This would help because [expected effect]. In addition, [actor] could [solution 2], especially by [specific method]. If these measures are used together, [realistic improvement] would be more likely.",
    "",
    "In conclusion, [problem] is mainly caused by [cause 1] and [cause 2]. However, it can be improved if [solution 1] and [solution 2] are carried out consistently.",
  ].join("\n"),
  "task2:causes_effects": [
    "[Trend/problem from the question] has become increasingly common. This is mainly caused by [cause 1] and [cause 2], and it can lead to [effect 1] as well as [effect 2].",
    "",
    "One major cause is [cause 1]. This happens because [explanation]. Another reason is [cause 2], especially when [specific situation]. For example, [example showing the cause clearly].",
    "",
    "This trend can have several effects. The first is [effect 1], because [explanation of consequence]. It may also lead to [effect 2]. In the long term, this could affect [people/society/the economy/the environment] by [specific impact].",
    "",
    "In conclusion, [trend/problem] is mainly caused by [cause 1] and [cause 2], and its most important effects are [effect 1] and [effect 2].",
  ].join("\n"),
  "task2:advantages_disadvantages": [
    "[Topic] has both advantages and disadvantages. Although it may cause [main drawback], I believe the benefits are more important because [main benefit].",
    "",
    "The main advantage is that [advantage]. This matters because [explanation], and it can help [people/society/businesses/students] to [positive result]. For example, [specific example]. This shows that [topic] can bring real value, not just convenience.",
    "",
    "However, there are also disadvantages. The most serious one is [disadvantage], which may lead to [negative result]. For instance, [example]. Even so, this problem can often be controlled by [solution/condition], while the benefits are broader and more lasting.",
    "",
    "In conclusion, despite [main drawback], I think the advantages of [topic] outweigh the disadvantages. The key reason is that [final reason linked to the question].",
  ].join("\n"),
  "task2:advantages_outweigh": [
    "[Topic] has both advantages and disadvantages, but I believe the advantages outweigh the disadvantages because [main benefit] is more significant than [main drawback].",
    "",
    "The main advantage is that [advantage]. This is important because [explanation], and it can help [people/society/businesses/students] to [positive result]. For example, [specific example].",
    "",
    "Admittedly, there are some disadvantages. The most obvious one is [disadvantage], which may cause [negative result]. However, this problem can often be reduced by [solution/condition], while the benefits are broader and more lasting.",
    "",
    "In conclusion, although [main drawback] should not be ignored, I think the advantages outweigh the disadvantages because [final reason].",
  ].join("\n"),
  "task2:two_question": [
    "[Topic from the question] raises two issues: [question 1 in your words] and [question 2 in your words]. In my view, [short answer to question 1], and [short answer to question 2].",
    "",
    "Regarding the first issue, [answer to question 1]. This is because [reason], and it often leads to [effect]. For example, [specific example]. Therefore, [mini conclusion for question 1].",
    "",
    "As for the second issue, [answer to question 2]. The most important reason is that [reason]. If [condition], then [result]. For example, [example], which shows that [mini conclusion for question 2].",
    "",
    "In conclusion, [summary answer to question 1], while [summary answer to question 2]. Overall, [final idea that connects both answers].",
  ].join("\n"),
  "task2:other": [
    "[Topic from the question] is an important issue. My answer is that [your clear position/answer], mainly because [reason 1] and [reason 2].",
    "",
    "The first point is [reason 1]. This is important because [explanation]. For example, [specific example]. This shows that [link back to the question].",
    "",
    "Another point is [reason 2]. Although some people may argue that [opposite idea], I think [your response] because [reason]. In practice, [short real-life example or condition].",
    "",
    "In conclusion, I believe [summary of your answer]. The strongest reason is that [final link to the exact question wording].",
  ].join("\n"),
};

const WRITING_FRAME_FALLBACK = {
  task1_academic: WRITING_FRAME_DEFAULTS["task1_academic:line_graph"],
  task2: WRITING_FRAME_DEFAULTS["task2:agree_disagree"],
};

function currentWritingFrameKey() {
  const prompt = state.writing.prompt || {};
  const taskType = prompt.task_type || state.writing.taskType || "task2";
  const category = (prompt.category || "").trim();
  const promptPattern = taskType === "task2" ? String(prompt.prompt_pattern || "").trim() : "";
  const frameType = promptPattern || category;
  return { taskType, category, promptPattern, frameType, key: `${taskType}:${frameType}` };
}

function writingFrameDefaultFor(taskType, frameType) {
  const fullKey = `${taskType}:${frameType}`;
  return WRITING_FRAME_DEFAULTS[fullKey]
    || WRITING_FRAME_FALLBACK[taskType]
    || WRITING_FRAME_FALLBACK.task2;
}

const WRITING_FRAME_LEGACY_KEYS = {
  "task2:agree_disagree": ["task2:opinion"],
  "task2:discussion_opinion": ["task2:discussion"],
  "task2:advantages_outweigh": ["task2:advantages_disadvantages"],
  "task2:problem_solution": ["task2:causes_effects", "task2:positive_negative"],
  "task2:two_question": ["task2:two_part"],
};

function writingFrameCustomForKey(key) {
  try {
    const direct = window.localStorage.getItem(`writingFrame:${key}`);
    if (direct) return direct;
    for (const legacyKey of WRITING_FRAME_LEGACY_KEYS[key] || []) {
      const legacy = window.localStorage.getItem(`writingFrame:${legacyKey}`);
      if (legacy) {
        window.localStorage.setItem(`writingFrame:${key}`, legacy);
        return legacy;
      }
    }
    return null;
  } catch { return null; }
}

function writingFrameFor(taskType, frameType) {
  const key = `${taskType}:${frameType}`;
  return writingFrameCustomForKey(key) || writingFrameDefaultFor(taskType, frameType);
}

function applyWritingFrame() {
  const answer = $("writingAnswer");
  if (!answer) return;
  const { taskType, frameType } = currentWritingFrameKey();
  const frame = writingFrameFor(taskType, frameType);
  const existing = answer.value.trim();
  // Only auto-fill when empty or value is exactly a slash command — never overwrite real work.
  if (existing && !/^\/(frame|myframe)\b/i.test(existing)) {
    const ok = window.confirm("已有作文内容，确定要替换为框架模板吗？");
    if (!ok) { answer.focus(); return; }
  }
  answer.value = frame + "\n\n";
  state.writing.autosaveFrameBaselineText = answer.value;
  state.writing.autosaveFrameBaselineWordCount = writingWordCountForValue(answer.value);
  state.writing.autosaveEnabled = false;
  state.writing.autosaveQueued = false;
  clearWritingAutosaveTimer();
  // Move caret to end and notify the rest of the app
  answer.focus();
  answer.setSelectionRange(answer.value.length, answer.value.length);
  answer.dispatchEvent(new Event("input", { bubbles: true }));
}

function openWritingFrameEditor() {
  const { taskType, category, promptPattern, frameType, key } = currentWritingFrameKey();
  if (!state.writing.prompt) {
    window.alert("先选一道题，才能为这类题型定制框架。");
    return;
  }
  const sub = $("writingFrameModalSub");
  if (sub) {
    const typeLabel = taskType === "task2"
      ? writingPromptPatternLabel(promptPattern || frameType)
      : writingCategoryLabel(category);
    const label = `${writingTaskLabel(taskType)}${typeLabel ? " · " + typeLabel : ""}`;
    sub.textContent = `当前类型：${label}（保存的框架仅作用于这一种固定问法/图表类型）`;
  }
  const editor = $("writingFrameEditor");
  if (editor) editor.value = writingFrameFor(taskType, frameType);
  const status = $("writingFrameSaveStatus");
  if (status) status.textContent = "";
  editor?.dataset && (editor.dataset.frameKey = key);
  $("writingFrameModal")?.classList.remove("hidden");
  document.body.classList.add("modal-open");
  setTimeout(() => editor?.focus(), 50);
}

function closeWritingFrameEditor() {
  $("writingFrameModal")?.classList.add("hidden");
  document.body.classList.remove("modal-open");
  $("writingAnswer")?.focus();
}

function savedWritingFrameValue(key) {
  if (!key) return "";
  try {
    const direct = window.localStorage.getItem(`writingFrame:${key}`);
    if (direct !== null) return direct;
  } catch {}
  const [taskType, frameType] = String(key).split(":");
  return writingFrameDefaultFor(taskType, frameType || "");
}

function writingFrameEditorHasUnsavedChanges() {
  const editor = $("writingFrameEditor");
  const key = editor?.dataset.frameKey;
  if (!editor || !key) return false;
  return editor.value !== savedWritingFrameValue(key);
}

function saveWritingFrame() {
  const editor = $("writingFrameEditor");
  const key = editor?.dataset.frameKey;
  if (!editor || !key) return false;
  try {
    window.localStorage.setItem(`writingFrame:${key}`, editor.value);
    const status = $("writingFrameSaveStatus");
    if (status) {
      status.textContent = "已保存";
      status.classList.remove("error");
      setTimeout(() => { if (status) status.textContent = ""; }, 1800);
    }
    return true;
  } catch (err) {
    const status = $("writingFrameSaveStatus");
    if (status) { status.textContent = "保存失败：" + (err.message || err); status.classList.add("error"); }
    return false;
  }
}

function closeWritingFrameEditorSavingChanges() {
  if (writingFrameEditorHasUnsavedChanges() && !saveWritingFrame()) return;
  closeWritingFrameEditor();
}

function resetWritingFrame() {
  const editor = $("writingFrameEditor");
  const key = editor?.dataset.frameKey;
  if (!editor || !key) return;
  try { window.localStorage.removeItem(`writingFrame:${key}`); } catch {}
  const [taskType, frameType] = key.split(":");
  editor.value = writingFrameDefaultFor(taskType, frameType || "");
  const status = $("writingFrameSaveStatus");
  if (status) { status.textContent = "已恢复默认"; status.classList.remove("error"); }
}

function handleWritingFrameSlashCommand() {
  const answer = $("writingAnswer");
  if (!answer) return false;
  const v = answer.value.trim().toLowerCase();
  if (v === "/frame") { applyWritingFrame(); return true; }
  if (v === "/myframe") {
    answer.value = "";
    answer.dispatchEvent(new Event("input", { bubbles: true }));
    openWritingFrameEditor();
    return true;
  }
  return false;
}

function writingScrollParent(element) {
  let node = element?.parentElement;
  while (node && node !== document.body) {
    const style = window.getComputedStyle(node);
    if (/(auto|scroll)/.test(`${style.overflowY} ${style.overflow}`)) return node;
    node = node.parentElement;
  }
  return document.scrollingElement || document.documentElement;
}

function autoResizeWritingAnswer(options = {}) {
  const answer = $("writingAnswer");
  if (!answer) return;
  const style = window.getComputedStyle(answer);
  const lineHeight = Number.parseFloat(style.lineHeight) || 24;
  const minPixelHeight = 500;
  const minRows = 12;
  const bufferRows = 1;
  const scrollParent = writingScrollParent(answer);
  const scrollTop = scrollParent?.scrollTop || 0;
  answer.style.height = "auto";
  const minHeight = Math.max(minPixelHeight, lineHeight * minRows);
  const targetHeight = Math.max(answer.scrollHeight + (lineHeight * bufferRows), minHeight);
  answer.style.height = `${targetHeight}px`;
  answer.style.overflowY = "hidden";
  if (options.preserveScroll && scrollParent) scrollParent.scrollTop = scrollTop;
}

function updateWritingWordCount(options = {}) {
  const count = currentWritingWordCount();
  text("writingWordCount", `${count} word${count === 1 ? "" : "s"}`);
  autoResizeWritingAnswer(options);
}

const WRITING_AUTOSAVE_MIN_WORDS = 20;
const WRITING_FRAME_AUTOSAVE_ADDED_WORDS = 35;

function writingWordCountForValue(value = "") {
  const matches = String(value || "").match(/[A-Za-z]+(?:[-'][A-Za-z]+)?|\d+(?:\.\d+)?/g);
  return matches ? matches.length : 0;
}

function resetWritingFrameAutosaveBaseline() {
  state.writing.autosaveFrameBaselineText = "";
  state.writing.autosaveFrameBaselineWordCount = 0;
}

function writingFrameAddedWordCount() {
  const answerValue = $("writingAnswer")?.value || "";
  const baselineText = state.writing.autosaveFrameBaselineText || "";
  if (!baselineText) return 0;
  if (!answerValue.startsWith(baselineText.trimEnd())) {
    resetWritingFrameAutosaveBaseline();
    return 0;
  }
  return Math.max(0, writingWordCountForValue(answerValue) - Number(state.writing.autosaveFrameBaselineWordCount || 0));
}

function writingAutosaveReady() {
  const answerValue = $("writingAnswer")?.value || "";
  const count = writingWordCountForValue(answerValue);
  const baselineText = state.writing.autosaveFrameBaselineText || "";
  if (!baselineText) return count > WRITING_AUTOSAVE_MIN_WORDS;
  return writingFrameAddedWordCount() >= WRITING_FRAME_AUTOSAVE_ADDED_WORDS;
}

function writingAutosaveStatusText() {
  if (state.writing.autosaveEnabled) return "等待自动保存...";
  return "未保存的修改";
}

function clearWritingAutosaveTimer() {
  if (state.writing.autosaveTimer) {
    clearTimeout(state.writing.autosaveTimer);
    state.writing.autosaveTimer = null;
  }
}

function maybeScheduleWritingAutosave() {
  if (writingAutosaveReady()) state.writing.autosaveEnabled = true;
  if (!state.writing.autosaveEnabled || !state.writing.dirty || !state.writing.prompt) return;
  if (state.writing.scorePollingEntryId) return;
  clearWritingAutosaveTimer();
  state.writing.autosaveTimer = setTimeout(() => {
    state.writing.autosaveTimer = null;
    runWritingAutosave().catch(showWritingError);
  }, 900);
}

async function runWritingAutosave() {
  if (!state.writing.autosaveEnabled || !state.writing.dirty || !state.writing.prompt) return;
  if (state.writing.autosaveSaving) {
    state.writing.autosaveQueued = true;
    return;
  }
  state.writing.autosaveSaving = true;
  try {
    text("writingSaveStatus", "自动保存中...");
    await saveWritingEntry(false, { autosave: true });
  } finally {
    state.writing.autosaveSaving = false;
    if (state.writing.autosaveQueued || state.writing.dirty) {
      state.writing.autosaveQueued = false;
      maybeScheduleWritingAutosave();
    }
  }
}

function setWritingPending(isPending, title = "", detail = "") {
  const wait = $("writingInlineWait");
  wait?.classList.toggle("hidden", !isPending);
  if (title) text("writingInlineWaitTitle", title);
  if (detail) text("writingInlineWaitText", detail);
  ["writingSaveBtn", "writingScoreBtn", "writingRandomBtn", "writingPromptPickerBtn", "writingAnswer"].forEach((id) => {
    const element = $(id);
    if (element) element.disabled = isPending;
  });
  document.querySelectorAll("[data-writing-task]").forEach((button) => {
    button.disabled = isPending;
  });
}

function writingTaskLabel(taskType) {
  return taskType === "task1_academic" ? "Task 1 Academic" : "Task 2";
}

function writingCategoryLabel(category = "") {
  const labels = {
    line_graph: "\u6298\u7ebf\u56fe",
    bar_chart: "\u67f1\u72b6\u56fe",
    pie_chart: "\u997c\u56fe",
    table: "\u8868\u683c",
    map: "\u5730\u56fe",
    process: "\u6d41\u7a0b\u56fe",
    mixed: "\u6df7\u5408\u56fe",
    opinion: "\u89c2\u70b9\u7c7b",
    discussion: "\u8ba8\u8bba\u7c7b",
    problem_solution: "\u95ee\u9898\u89e3\u51b3\u7c7b",
    advantages_disadvantages: "\u5229\u5f0a\u7c7b",
    two_part: "\u53cc\u95ee\u9898\u7c7b",
  };
  const key = String(category || "").trim();
  return labels[key] || key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) || "Writing";
}

function writingPromptPatternLabel(pattern = "") {
  const labels = {
    agree_to_what_extent: "To what extent do you agree or disagree?",
    discussion_opinion: "Discuss both views and give your own opinion.",
    positive_negative_do_you_think: "a positive or a negative development?",
    advantages_outweigh: "Do the advantages outweigh the disadvantages?",
    problem_solution: "Why / What reasons / solutions?",
    two_question: "双问题",
    other: "其他问法",
  };
  const key = String(pattern || "").trim();
  return labels[key] || key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) || "问法";
}

function task2PromptPatternForText(promptText = "") {
  const text = String(promptText || "").replace(/\s+/g, " ").trim().toLowerCase();
  if (!text) return "other";
  if (/discuss\s*&\s*give (?:your|our)(?: own)? opinions?/.test(text)) return "discussion_opinion";
  if (/discuss both(?: (?:these|the|those))?(?: (?:views?|sides?))?(?: and)?(?: give)? (?:your|our)(?: own)? (?:opinions?|view)/.test(text)) return "discussion_opinion";
  if (/what is the value\b.*\bwhat are the arguments in favour\b/.test(text)) return "discussion_opinion";
  if (/to what exten[td] do(?: you)? agree (?:or|of) disagree(?: with (?:this|the) (?:statement|opinion|view))?/.test(text)) return "agree_to_what_extent";
  if (/to what exten[td] do you think\b/.test(text)) return "agree_to_what_extent";
  if (/do you agree or disagree/.test(text)) return "agree_to_what_extent";
  if (/\bbenefits?\b.*\boutweigh\b.*\b(?:disadvantages?|drawbacks?)\b/.test(text)) return "advantages_outweigh";
  if (/\badvantages?\b.*\boutweigh\b.*\b(?:disadvantages?|drawbacks?)\b/.test(text)) return "advantages_outweigh";
  if (/\b(?:disadvantages?|drawbacks?)\b.*\boutweigh\b.*\b(?:advantages?|benefits?)\b/.test(text)) return "advantages_outweigh";
  if (/\bnegative effects?\b.*\boutweigh\b.*\bpositive effects?\b/.test(text)) return "advantages_outweigh";
  if (/\b(?:advantages?|benefits?)\b.*\bor\b.*\b(?:disadvantages?|drawbacks?)\b/.test(text)) return "advantages_outweigh";
  const hasReasonQuestion = /\b(?:why|what (?:do you think )?(?:are )?(?:the )?(?:reasons?|causes?|problems?)|what factors? contribute|how (?:can|could)|what can|what could|what should|what (?:are )?(?:the )?(?:solutions?|measures?))\b/.test(text);
  const hasSecondQuestion = (text.match(/\?/g) || []).length >= 2;
  const hasSolutionQuestion = /\b(?:solutions?|measures?|solve|solved|what can|what could|how can|how could|how to|what should|ways to|encourage|research)\b/.test(text);
  const hasEffectQuestion = /\b(?:effects?|impact|affect|positive|negative|disadvantages?|advantages?|how realistic)\b/.test(text);
  if (hasReasonQuestion && hasSecondQuestion && (hasSolutionQuestion || hasEffectQuestion)) return "problem_solution";
  if (/\bwhy\b/.test(text) && /\b(?:effects?|impact|affect|positive|negative)\b/.test(text)) return "problem_solution";
  const positiveNegativePatterns = [
    /(?:do you think|whether|is|are|ls) (?:this|it|that|these|they|the (?:trend|development|change|situation|effect|impact))?(?: is| are)?(?: a)? positive (?:or )?(?:a )?negative (?:development|trend|change|situation|effects?|impacts?|characteristic)?/,
    /(?:do you think|whether) (?:the|this|that) (?:trend|development|change|situation|effect|impact) (?:is|are) (?:a )?positive (?:or )?(?:a )?negative (?:development|trend|change|situation|effects?|impacts?|characteristic)?/,
  ];
  if (positiveNegativePatterns.some((pattern) => pattern.test(text))) return "positive_negative_do_you_think";
  const hasBecomePatterns = [
    /has (?:this|it|that|the (?:trend|development|change|situation|effect|impact)) become (?:a )?positive (?:or )?(?:a )?negative (?:development|trend|change|situation|effects?|impacts?|characteristic)/,
    /is (?:this|it|that|the (?:trend|development|change|situation|effect|impact)) (?:a )?positive (?:or )?(?:a )?negative (?:development|trend|change|situation|effects?|impacts?|characteristic)/,
  ];
  if (hasBecomePatterns.some((pattern) => pattern.test(text))) return "positive_negative_do_you_think";
  if (text.includes("advantages and disadvantages") || text.includes("benefits and drawbacks") || (text.includes("what are the advantages") && text.includes("disadvantages"))) {
    return "advantages_outweigh";
  }
  const mentionsSolution = /solutions?|measures?|solved?|solve/.test(text);
  if (((/problems?/.test(text)) && mentionsSolution) || ((/causes?|reasons?/.test(text)) && mentionsSolution)) {
    return "problem_solution";
  }
  if ((/causes?|reasons?/.test(text)) && (/effects?|affect|impact/.test(text))) return "problem_solution";
  return "other";
}

function withWritingPromptPattern(prompt = {}) {
  if (!prompt || prompt.task_type !== "task2") return prompt;
  const currentPattern = String(prompt.prompt_pattern || "").trim();
  const pattern = task2PromptPatternForText(prompt.prompt);
  const label = currentPattern === "causes_effects"
    ? writingPromptPatternLabel(pattern)
    : writingPromptPatternLabel(pattern);
  return { ...prompt, prompt_pattern: pattern, prompt_pattern_label: label };
}

function normalizeWritingPrompts(taskType, prompts = [], catalog = []) {
  return attachWritingDisplayLabels(taskType, prompts, catalog).map(withWritingPromptPattern);
}

const CAMBRIDGE_TASK2_TOPIC_TITLES = {
  "cambridge-7-test-1-task-2": "Talent And Training",
  "cambridge-7-test-3-task-2": "Job Satisfaction",
  "cambridge-8-test-2-task-2": "Technology And Relationships",
  "cambridge-8-test-4-task-2": "Health And Fitness",
  "cambridge-9-test-1-task-2": "Foreign Language Learning",
  "cambridge-9-test-2-task-2": "Community Service",
  "cambridge-9-test-3-task-2": "Public Health",
  "cambridge-9-test-4-task-2": "Language Loss",
  "cambridge-10-test-1-task-2": "Children And Punishment",
  "cambridge-10-test-2-task-2": "University Subjects",
  "cambridge-10-test-3-task-2": "Global Similarity",
  "cambridge-10-test-4-task-2": "Museum Admission",
  "cambridge-11-test-1-task-2": "Railways And Roads",
  "cambridge-11-test-2-task-2": "Household Recycling",
  "cambridge-11-test-3-task-2": "Foreign Languages",
  "cambridge-11-test-4-task-2": "National Progress",
  "cambridge-12-test-1-task-2": "Information Sharing",
  "cambridge-12-test-2-task-2": "Age Structure",
  "cambridge-12-test-3-task-2": "Railways And Roads",
  "cambridge-12-test-4-task-2": "Children's Choices",
  "cambridge-13-test-1-task-2": "Living Abroad",
  "cambridge-13-test-2-task-2": "Too Many Choices",
  "cambridge-13-test-3-task-2": "History And Science",
  "cambridge-13-test-4-task-2": "World Hunger",
  "cambridge-14-test-1-task-2": "Bad Situations",
  "cambridge-14-test-2-task-2": "Environmental Problems",
  "cambridge-14-test-3-task-2": "Music And Culture",
  "cambridge-14-test-4-task-2": "Self-Employment",
  "cambridge-15-test-1-task-2": "Home Ownership",
  "cambridge-15-test-2-task-2": "Online Reading",
  "cambridge-15-test-3-task-2": "Advertising",
  "cambridge-15-test-4-task-2": "Children And Success",
  "cambridge-16-test-1-task-2": "Building History",
  "cambridge-16-test-2-task-2": "New Products",
  "cambridge-16-test-3-task-2": "Sugar And Health",
  "cambridge-16-test-4-task-2": "Driverless Vehicles",
  "cambridge-17-test-1-task-2": "Taking Risks",
  "cambridge-17-test-2-task-2": "Children And Smartphones",
  "cambridge-17-test-3-task-2": "Professionals Working Abroad",
  "cambridge-17-test-4-task-2": "Alternative Medicine",
  "cambridge-18-test-1-task-2": "Science And People's Lives",
  "cambridge-18-test-2-task-2": "University Study Choices",
  "cambridge-18-test-3-task-2": "Rural To Urban Migration",
  "cambridge-18-test-4-task-2": "Ageing Population",
  "cambridge-19-test-1-task-2": "Competition And Cooperation",
  "cambridge-19-test-2-task-2": "Shorter Working Week",
  "cambridge-19-test-3-task-2": "Saving Money",
  "cambridge-19-test-4-task-2": "Global Food",
  "cambridge-20-test-1-task-2": "Clean Water",
  "cambridge-20-test-2-task-2": "School Holidays",
  "cambridge-20-test-3-task-2": "Air Travel",
  "cambridge-20-test-4-task-2": "Global Fashion",
};

function isGenericCambridgeTitle(title = "") {
  return /^Cambridge IELTS \d+ Test \d+ Task [12]$/i.test(String(title || "").trim());
}

function writingCambridgePromptId(prompt = {}) {
  const book = String(prompt.source_book || "").trim();
  const test = String(prompt.source_test || "").trim();
  const sourceQuestion = String(prompt.source_question || "").trim();
  const taskQuestion = prompt.task_type === "task1_academic" ? "1" : (prompt.task_type === "task2" ? "2" : "");
  if (book && test && (sourceQuestion || taskQuestion)) {
    return `cambridge-${book}-test-${test}-task-${sourceQuestion || taskQuestion}`;
  }
  const labelMatch = String(prompt.source_label || prompt.display_source_label || "").match(/剑雅\s*(\d+)[-–](\d+)/);
  if (labelMatch && taskQuestion) return `cambridge-${labelMatch[1]}-test-${labelMatch[2]}-task-${taskQuestion}`;
  return "";
}

function titleCaseFromWords(words = []) {
  return words
    .filter(Boolean)
    .map((word) => {
      const clean = String(word).trim();
      return clean ? clean.charAt(0).toUpperCase() + clean.slice(1).toLowerCase() : "";
    })
    .filter(Boolean)
    .join(" ");
}

function deriveTask2TopicTitle(prompt = {}) {
  const text = String(prompt.prompt || "").toLowerCase();
  const topicRules = [
    [/clean water|water supply/, "Clean Water"],
    [/summer holidays|school holidays/, "School Holidays"],
    [/fly every year|flying altogether|air travel/, "Air Travel"],
    [/global fashion|dress today/, "Global Fashion"],
    [/technology.*learning|learning.*technology/, "Technology And Learning"],
    [/public transport|traffic congestion/, "Public Transport"],
    [/work-life|working from home/, "Work-Life Balance"],
    [/practical skills|traditional academic subjects/, "Practical Skills In Education"],
  ];
  const match = topicRules.find(([pattern]) => pattern.test(text));
  if (match) return match[1];
  const firstSentence = String(prompt.prompt || "").split(/[.?]/)[0] || "";
  const candidates = firstSentence.match(/[A-Za-z][A-Za-z'-]*/g) || [];
  const stopWords = new Set(["some", "people", "think", "believe", "that", "many", "countries", "nowadays", "today", "the", "and", "are", "is", "in", "of", "to", "for", "with", "from", "their", "this", "it"]);
  const words = candidates.filter((word) => !stopWords.has(word.toLowerCase())).slice(0, 4);
  return titleCaseFromWords(words) || "";
}

function writingPromptTopicTitle(prompt) {
  const title = String(prompt?.title || "").trim();
  const id = String(prompt?.id || prompt?.prompt_id || prompt?.display_catalog_id || "").trim() || writingCambridgePromptId(prompt || {});
  if (prompt?.task_type === "task2" && CAMBRIDGE_TASK2_TOPIC_TITLES[id]) return CAMBRIDGE_TASK2_TOPIC_TITLES[id];
  if (writingPromptSourceKey(prompt || {}) === "cambridge" && isGenericCambridgeTitle(title)) {
    if (prompt?.task_type === "task2") return deriveTask2TopicTitle(prompt) || writingTaskLabel(prompt?.task_type);
    return "";
  }
  return title && title !== writingTaskLabel(prompt?.task_type) ? title : "";
}

function writingPromptDisplayTitle(prompt) {
  return writingPromptTopicTitle(prompt) || writingTaskLabel(prompt?.task_type);
}

function writingPromptCardTitle(prompt) {
  return writingPromptTopicTitle(prompt);
}

function writingPromptMeta(prompt) {
  if (!prompt) return writingTaskLabel(state.writing.taskType || "task1_academic");
  const sourceLabel = String(prompt.source_label || prompt.display_source_label || "").trim();
  const parts = sourceLabel
    ? [writingTaskLabel(prompt.task_type), writingCategoryLabel(prompt.category)]
    : [writingTaskLabel(prompt.task_type), writingCategoryLabel(prompt.category)];
  return parts.filter(Boolean).join(" \u00b7 ");
}

function writingPromptTopbarTitle(prompt) {
  const sourceLabel = String(prompt?.source_label || prompt?.display_source_label || "").trim();
  if (writingPromptSourceKey(prompt || {}) === "cambridge") return writingPromptPickerTitle(prompt);
  if (sourceLabel) return sourceLabel;
  return writingPromptDisplayTitle(prompt);
}

function writingPromptShortSourceLabel(prompt = {}) {
  const label = String(prompt.source_label || prompt.display_source_label || "").trim().replace(/\s*Task\s+[12]\s*$/i, "");
  if (label) return label;
  if (prompt.source_book && prompt.source_test) return `\u5251\u96c5${prompt.source_book}-${prompt.source_test}`;
  return "";
}

function normalizeWritingTitleComparison(value = "") {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "");
}

function meaningfulWritingSourceLabel(prompt = {}, topicTitle = "") {
  const label = writingPromptShortSourceLabel(prompt);
  if (!label) return "";
  if (writingPromptSourceKey(prompt) === "cambridge") return label;
  const normalizedLabel = normalizeWritingTitleComparison(label);
  const nonSourceTitles = [
    topicTitle,
    prompt.title,
    prompt.task_label,
    writingTaskLabel(prompt.task_type),
    writingCategoryLabel(prompt.category),
    deriveTask2TopicTitle(prompt),
  ].map(normalizeWritingTitleComparison).filter(Boolean);
  return nonSourceTitles.includes(normalizedLabel) ? "" : label;
}

function uniqueWritingTitleParts(parts = []) {
  const seen = new Set();
  return parts
    .map((part) => String(part || "").trim())
    .filter((part) => {
      if (!part) return false;
      const key = part.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function writingStructuredFallbackTitle(taskType, category = "") {
  return uniqueWritingTitleParts([writingTaskLabel(taskType), writingCategoryLabel(category)]).join(" \u2022 ");
}

function writingEntryDisplayTitle(entry = {}) {
  const prompt = {
    id: entry.prompt_id || entry.display_catalog_id || "",
    task_type: entry.task_type,
    title: entry.title,
    category: entry.category,
    prompt: entry.prompt,
    source: entry.source || "",
    source_label: entry.source_label || "",
    source_book: entry.source_book,
    source_test: entry.source_test,
    source_question: entry.source_question,
    display_source_label: entry.display_source_label || "",
  };
  const sourceKey = writingPromptSourceKey(prompt);
  const title = writingPromptTopicTitle(prompt);
  const category = String(prompt.category || "").trim() ? writingCategoryLabel(prompt.category) : "";
  const fallbackTitle = writingStructuredFallbackTitle(entry.task_type, prompt.category);
  if (sourceKey === "cambridge") return writingPromptPickerTitle(prompt);
  const sourceLabel = meaningfulWritingSourceLabel(prompt, title);
  if (sourceLabel) return uniqueWritingTitleParts([sourceLabel, title, category]).join(" \u2022 ");
  return fallbackTitle || writingTaskLabel(entry.task_type);
}

function writingEntryPromptText(entry = {}) {
  return writingReportPromptText(entry, entry.score || null);
}

function writingPromptFieldText(value, fields = ["prompt", "prompt_text", "text", "question", "title", "task_label"]) {
  if (typeof value === "string") return value.trim();
  if (!value || typeof value !== "object") return "";
  for (const field of fields) {
    const textValue = String(value[field] || "").trim();
    if (textValue) return textValue;
  }
  return "";
}

function writingReportPromptText(entry = {}, score = null) {
  const candidates = [
    writingPromptFieldText(entry.prompt, ["prompt", "prompt_text", "text", "question"]),
    String(entry.prompt_text || "").trim(),
    String(entry.question || "").trim(),
    writingPromptFieldText(score?.prompt, ["prompt", "prompt_text", "text", "question"]),
    String(score?.prompt_text || "").trim(),
  ];
  return candidates.find(Boolean) || "";
}

function writingEntryImageUrl(entry = {}, score = null) {
  const prompt = entry.prompt;
  const scorePrompt = score?.prompt;
  const promptImage = prompt && typeof prompt === "object" ? prompt.image_url || prompt.prompt_image_url : "";
  const scorePromptImage = scorePrompt && typeof scorePrompt === "object" ? scorePrompt.image_url || scorePrompt.prompt_image_url : "";
  return String(entry.image_url || promptImage || entry.prompt_image_url || score?.image_url || scorePromptImage || score?.prompt_image_url || "").trim();
}

function writingReportPromptFallback(entry = {}) {
  const taskLabel = writingTaskLabel(entry.task_type);
  const promptTitle = entry.prompt && typeof entry.prompt === "object" ? entry.prompt.title : "";
  const title = String(entry.title || promptTitle || entry.task_label || taskLabel || "Writing prompt").trim();
  const body = entry.task_type === "task1_academic"
    ? "The original Task 1 prompt text was not included in this saved report. Review the chart image below if it is available."
    : "The original Task 2 prompt text was not included in this saved report.";
  return { title, body };
}

function attachWritingDisplayLabels(taskType, prompts = [], catalog = []) {
  return prompts.map((prompt, index) => {
    if (prompt.source_label || prompt.display_source_label) return prompt;
    const slot = catalog[index];
    if (!slot?.source_label) return prompt;
    return { ...prompt, display_source_label: slot.source_label, display_catalog_id: slot.id || "" };
  });
}

function writingCatalogMissingSlots(taskType, selectedCategory = "") {
  if (selectedCategory) return [];
  const promptCount = (state.writing.prompts[taskType] || []).length;
  const assignedCatalogIds = new Set((state.writing.prompts[taskType] || []).map((prompt) => prompt.display_catalog_id).filter(Boolean));
  const availableIds = new Set((state.writing.prompts[taskType] || []).map((prompt) => prompt.id));
  return (state.writing.promptCatalog[taskType] || [])
    .filter((slot) => slot?.id && !availableIds.has(slot.id))
    .filter((slot, index) => index >= promptCount && !assignedCatalogIds.has(slot.id));
}

function writingPromptSourceKey(prompt = {}) {
  const source = String(prompt.source || "").trim();
  const id = String(prompt.id || prompt.display_catalog_id || "").trim();
  const label = String(prompt.source_label || prompt.display_source_label || "").trim();
  if (
    (prompt.source_book && prompt.source_test) ||
    source === "cambridge_ielts" ||
    source.startsWith("cambridge") ||
    id.startsWith("cambridge-") ||
    /剑雅\s*\d+/.test(label)
  ) return "cambridge";
  if (source.startsWith("reported_actual_")) return "reported";
  return "other";
}

function writingPromptSourceLabel(source) {
  return {
    cambridge: "\u5251\u96c5\u771f\u9898",
    reported: "\u4e2d\u56fd\u8003\u533a\u673a\u7ecf",
    other: "\u5176\u4ed6\u7ec3\u4e60",
  }[source] || source;
}

function writingPromptPickerTitle(prompt) {
  if (writingPromptSourceKey(prompt) !== "cambridge") {
    return writingPromptDisplayTitle(prompt);
  }
  let book = prompt.source_book;
  let test = prompt.source_test;
  if (!book || !test) {
    const match = String(prompt.id || "").match(/cambridge-(\d+)-test-(\d+)/);
    if (match) {
      book = book || match[1];
      test = test || match[2];
    }
  }
  if (!book || !test) {
    const labelMatch = String(prompt.source_label || prompt.display_source_label || "").match(/剑雅\s*(\d+)[-–](\d+)/);
    if (labelMatch) {
      book = book || labelMatch[1];
      test = test || labelMatch[2];
    }
  }
  const sourceLabel = book && test
    ? `\u5251\u96c5${book}-${test}`
    : String(prompt.source_label || prompt.display_source_label || writingPromptDisplayTitle(prompt)).replace(/\s*Task\s+[12]\s*$/i, "");
  const category = String(prompt.category || "").trim() ? writingCategoryLabel(prompt.category) : "";
  const title = writingPromptTopicTitle(prompt);
  return [sourceLabel, title, category].filter(Boolean).join(" \u2022 ");
}

function writingPromptsForSource(taskType, source) {
  return (state.writing.prompts[taskType] || []).filter((prompt) => writingPromptSourceKey(prompt) === source);
}

function writingUsablePromptsForSource(taskType, source) {
  return writingPromptsForSource(taskType, source).filter((prompt) => {
    if (taskType === "task1_academic") return Boolean(prompt.image_url);
    return Boolean(String(prompt.prompt || "").trim());
  });
}

function resolveWritingPickerSource(taskType) {
  const selected = state.writing.pickerSourceFilters[taskType] || "cambridge";
  if (selected === "cambridge" && !writingUsablePromptsForSource(taskType, "cambridge").length) {
    const fallback = writingUsablePromptsForSource(taskType, "reported").length ? "reported" : "other";
    state.writing.pickerSourceFilters[taskType] = fallback;
    return fallback;
  }
  return selected;
}

async function loadWriting() {
  if (state.writing.reportEditLoading) {
    setWritingPageLoading(false);
    text("writingSaveStatus", "正在复制这篇作文...");
    return;
  }
  const firstLoad = !state.writing.prompt && !state.writing.entry;
  if (firstLoad) setWritingPageLoading(true);
  try {
    const summaryPromise = loadWritingSummary(false);
    if (await loadRequestedWritingEntry()) {
      setWritingPageLoading(false);
      summaryPromise.catch((error) => {
        text("writingSaveStatus", error?.message || "签到信息稍后刷新。");
      });
      scheduleIdleTask(() => loadWritingPrompts(state.writing.taskType), 80);
      const alternateTaskType = state.writing.taskType === "task1_academic" ? "task2" : "task1_academic";
      scheduleIdleTask(() => loadWritingPrompts(alternateTaskType), 2600);
      return;
    }
    const routePrompt = await resolveRequestedWritingPrompt();
    if (routePrompt) setWritingPrompt(routePrompt, false, { replaceUrl: true });
    let quickPrompt = null;
    try {
      quickPrompt = state.writing.prompt
        ? state.writing.prompt
        : await loadQuickWritingPrompt(state.writing.taskType);
    } catch (error) {
      if (!state.writing.prompt) throw error;
    }
    if (!state.writing.prompt) {
      if (quickPrompt) {
        setWritingPrompt(quickPrompt, false, { replaceUrl: true });
      } else {
        const prompts = state.writing.prompts[state.writing.taskType] || [];
        const defaultPrompt = writingUsablePromptsForSource(state.writing.taskType, "cambridge")[0] || prompts[0];
        if (defaultPrompt) setWritingPrompt(defaultPrompt, false, { replaceUrl: true });
        else await chooseRandomWritingPrompt(false);
      }
    }
    renderWritingSurface();
    setWritingPageLoading(false);
    summaryPromise.then((summary) => {
      if (!state.writing.entry && summary?.today_entry?.ai_task && isWritingTaskActive(summary.today_entry.ai_task)) {
        recoverWritingEntry(summary.today_entry)
          .then(() => {
            startWritingScorePolling(summary.today_entry.id, { switchOnComplete: false });
            renderWritingSurface();
          })
          .catch(showWritingError);
      }
    }).catch((error) => {
      text("writingSaveStatus", error?.message || "签到信息稍后刷新。");
    });
    scheduleIdleTask(() => loadWritingPrompts(state.writing.taskType), 80);
    const alternateTaskType = state.writing.taskType === "task1_academic" ? "task2" : "task1_academic";
    scheduleIdleTask(() => loadWritingPrompts(alternateTaskType), 2600);
  } catch (error) {
    showWritingError(error);
  } finally {
    setWritingPageLoading(false);
  }
}

async function loadRequestedWritingEntry() {
  const entryId = String(state.writing.requestedEntryId || "").trim();
  if (!entryId) return false;
  text("writingSaveStatus", "正在加载这篇作文...");
  const entry = await api(`/api/writing/entries/${encodeURIComponent(entryId)}`);
  state.writing.requestedEntryId = "";
  await recoverWritingEntry(entry);
  syncWritingScorePolling(entry, { switchOnComplete: false });
  syncUrlForCurrentState({ replace: true });
  text("writingSaveStatus", "已载入");
  $("writingAnswer")?.focus();
  return true;
}

async function resolveRequestedWritingPrompt() {
  const promptId = String(state.writing.requestedPromptId || "").trim();
  if (!promptId) return null;
  const taskTypes = ["task1_academic", "task2"];
  const preferredTask = state.writing.taskType || "task1_academic";
  const orderedTasks = [preferredTask, ...taskTypes.filter((taskType) => taskType !== preferredTask)];
  for (const taskType of orderedTasks) {
    const prompts = await loadWritingPrompts(taskType);
    const found = prompts.find((prompt) => prompt.id === promptId);
    if (found) {
      state.writing.taskType = found.task_type || taskType;
      state.writing.requestedPromptId = "";
      return found;
    }
  }
  state.writing.requestedPromptId = "";
  return null;
}

async function loadQuickWritingPrompt(taskType) {
  const normalized = taskType || "task1_academic";
  const cachedPrompt = writingUsablePromptsForSource(normalized, "cambridge")[0]
    || (state.writing.prompts[normalized] || [])[0];
  if (cachedPrompt) return cachedPrompt;
  return api("/api/writing/prompts/random", {
    task_type: normalized,
    category: "",
    prompt_pattern: state.writing.pickerPromptPatternFilters?.[normalized] || "",
  });
}

async function loadWritingPrompts(taskType) {
  const normalized = taskType || "task1_academic";
  if (state.writing.prompts[normalized]?.length) {
    state.writing.prompts[normalized] = normalizeWritingPrompts(normalized, state.writing.prompts[normalized], state.writing.promptCatalog[normalized] || []);
    if (!state.writing.promptCategories[normalized]?.length) {
      state.writing.promptCategories[normalized] = inferWritingCategories(state.writing.prompts[normalized]);
    }
    if (normalized === "task2") {
      state.writing.promptPatterns[normalized] = inferWritingPromptPatterns(state.writing.prompts[normalized]);
    }
    return state.writing.prompts[normalized];
  }
  if (!state.writing.promptLoadingPromises[normalized]) {
    state.writing.promptLoadingPromises[normalized] = api(`/api/writing/prompts?task_type=${encodeURIComponent(normalized)}`)
      .then((payload) => {
        state.writing.promptCatalog[normalized] = payload.catalog || [];
        state.writing.prompts[normalized] = normalizeWritingPrompts(normalized, payload.items || [], state.writing.promptCatalog[normalized]);
        state.writing.promptCategories[normalized] = payload.categories || inferWritingCategories(state.writing.prompts[normalized]);
        state.writing.promptPatterns[normalized] = normalized === "task2"
          ? inferWritingPromptPatterns(state.writing.prompts[normalized])
          : (payload.prompt_patterns || []);
        return state.writing.prompts[normalized];
      })
      .finally(() => {
        state.writing.promptLoadingPromises[normalized] = null;
      });
  }
  await state.writing.promptLoadingPromises[normalized];
  return state.writing.prompts[normalized];
}

async function prefetchWritingPrompts(token) {
  await loadWritingPrompts(state.writing.taskType || "task1_academic").catch(() => []);
  if (!prefetchCanApply(token)) return;
  const alternateTaskType = state.writing.taskType === "task1_academic" ? "task2" : "task1_academic";
  scheduleIdleTask(() => loadWritingPrompts(alternateTaskType), 5200);
}

function inferWritingCategories(prompts = []) {
  const counts = new Map();
  for (const prompt of prompts) {
    const category = String(prompt.category || "").trim();
    if (!category) continue;
    counts.set(category, (counts.get(category) || 0) + 1);
  }
  return Array.from(counts.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([category, count]) => ({ category, label: writingCategoryLabel(category), count }));
}

function inferWritingPromptPatterns(prompts = []) {
  const counts = new Map();
  for (const prompt of prompts) {
    const rawPattern = String(prompt.prompt_pattern || "").trim();
    const pattern = rawPattern === "two_question" ? "other" : rawPattern;
    if (!pattern) continue;
    counts.set(pattern, (counts.get(pattern) || 0) + 1);
  }
  const order = [
    "agree_to_what_extent",
    "discussion_opinion",
    "positive_negative_do_you_think",
    "advantages_outweigh",
    "problem_solution",
    "other",
  ];
  return Array.from(counts.entries())
    .sort(([a], [b]) => {
      const rankA = order.indexOf(a);
      const rankB = order.indexOf(b);
      return (rankA === -1 ? 999 : rankA) - (rankB === -1 ? 999 : rankB) || a.localeCompare(b);
    })
    .map(([pattern, count]) => ({ pattern, label: writingPromptPatternLabel(pattern), count }));
}

async function loadWritingSummary(render = true) {
  const payload = await api("/api/writing/summary");
  state.writing.month = payload.month || "";
  if (render) renderWritingSummary(payload);
  else renderWritingSummary(payload);
  if (payload.today_entry) syncWritingScorePolling(payload.today_entry, { notifyOnComplete: false });
  return payload;
}

function renderWritingSummary(payload) {
  const stats = payload.stats || {};
  state.writing.recentEntries = payload.recent_entries || [];
  text("writingMonthLabel", `${payload.month || ""} 签到`);
  text("writingPracticedDays", stats.practiced_days ?? 0);
  text("writingStreakDays", stats.streak_days ?? 0);
  text("writingScoredCount", stats.scored_entries ?? 0);
  const days = payload.days || [];
  const weekLabels = ["一", "二", "三", "四", "五", "六", "日"];
  const firstDate = days.length ? new Date(`${days[0].date}T00:00:00`) : null;
  const leading = firstDate ? (firstDate.getDay() + 6) % 7 : 0;
  const blanks = Array.from({ length: leading }, () => '<span class="writing-day blank"></span>').join("");
  $("writingCalendar").innerHTML = `
    ${weekLabels.map((label) => `<span class="writing-weekday">${label}</span>`).join("")}
    ${blanks}
    ${days.map((day) => {
      const date = new Date(`${day.date}T00:00:00`);
      const label = Number.isNaN(date.getTime()) ? "" : date.getDate();
      return `<button type="button" class="writing-day ${escapeHtml(day.status || "empty")}" data-writing-entry-id="${escapeHtml(day.entry_id || "")}" title="${escapeHtml(day.date)}">${label}</button>`;
    }).join("")}
  `;
}

async function loadWritingReports(showBusy = true) {
  try {
    if (state.writing.reportEntries.length) renderWritingReports(state.writing.reportEntries, { refreshActive: true });
    const loader = () => api("/api/writing/reports");
    const currentActiveId = state.writing.activeReportId && state.writing.reportEntries.some((item) => item.id === state.writing.activeReportId)
      ? state.writing.activeReportId
      : state.writing.reportEntries[0]?.id;
    const panel = $("writingReportsPanel");
    if (showBusy && (!currentActiveId || !cachedWritingReportEntry(currentActiveId))) {
      panel?.classList.add("is-loading");
      $("writingReportDetail").innerHTML = centeredLoadingHtml("正在加载写作报告", "正在读取写作历史和报告详情。");
    }
    const payload = await loader();
    await renderWritingReports(payload.items || []);
  } catch (error) {
    showWritingReportError(error);
  } finally {
    $("writingReportsPanel")?.classList.remove("is-loading");
  }
}

async function renderWritingReports(items, options = {}) {
  const refreshActive = options.refreshActive !== false;
  const target = $("writingReportDetail");
  if (!target) return;
  if (!items.length) {
    state.writing.reportEntries = [];
    const list = $("writingReportList");
    if (list) list.innerHTML = '<div class="history-empty-state">还没有写作记录。</div>';
    target.innerHTML = '<h2>写作报告</h2><p class="muted">还没有写作记录。保存一篇作文后会出现在这里。</p>';
    return;
  }
  // Store compact items from /api/writing/reports
  state.writing.reportEntries = items;
  // Determine active report id
  const activeId = items.some((item) => item.id === state.writing.activeReportId) ? state.writing.activeReportId : items[0].id;
  state.writing.activeReportId = activeId;
  syncUrlForCurrentState({ replace: true });
  // Render list from compact items
  renderWritingReportList(items);
  // Fetch detail only for the selected item
  const activeItem = items.find((item) => item.id === activeId) || items[0];
  const cached = cachedWritingReportEntry(activeItem.id);
  if (cached) {
    state.writing.activeReportDetail = cached;
    target.innerHTML = writingReportDetailHtml(cached);
    syncWritingScorePolling(cached, { notifyOnComplete: false });
  } else {
    state.writing.activeReportDetail = null;
    target.innerHTML = centeredLoadingHtml("正在加载写作报告", "首次打开报告需要读取详情和图表信息。");
  }
  if (refreshActive && !cached) {
    target.innerHTML = centeredLoadingHtml("正在加载写作报告", "首次打开报告需要读取详情和图表信息。");
  }
  if (!refreshActive) return;
  if (cached) return;
  try {
    const entry = await fetchWritingReportDetail(activeItem.id);
    state.writing.activeReportDetail = entry;
    target.innerHTML = writingReportDetailHtml(entry);
    if (isWritingTaskActive(entry?.ai_task)) startWritingScorePolling(entry.id, { switchOnComplete: false });
  } catch (error) {
    target.innerHTML = `<div class="detail-card"><p class="error">${escapeHtml(error.message || "Failed to load report detail.")}</p></div>`;
  }
}

function renderWritingReportList(items) {
  const list = $("writingReportList");
  if (!list) return;
  list.innerHTML = items.map((item) => `
    <div class="history-item-wrap writing-report-item-wrap">
      ${writingReportTabHtml(item, item.id === state.writing.activeReportId)}
      <button class="history-item-menu-btn writing-report-menu-btn" data-writing-entry-id="${escapeHtml(item.id || "")}" aria-label="More options" title="More options">
        <span aria-hidden="true"></span>
      </button>
    </div>
  `).join("");
  list.querySelectorAll("[data-writing-report-tab]").forEach((button) => {
    button.addEventListener("click", async () => {
      const itemId = button.dataset.writingReportTab;
      if (!itemId) return;
      state.writing.activeReportId = itemId;
      syncUrlForCurrentState();
      renderWritingReportList(state.writing.reportEntries);
      const target = $("writingReportDetail");
      if (!target) return;
      const cached = cachedWritingReportEntry(itemId);
      if (cached) {
        state.writing.activeReportDetail = cached;
        target.innerHTML = writingReportDetailHtml(cached);
        target.scrollTo({ top: 0, behavior: "auto" });
        syncWritingScorePolling(cached, { notifyOnComplete: false });
        if (isWritingTaskActive(cached.ai_task)) startWritingScorePolling(cached.id, { switchOnComplete: false });
        return;
      } else {
        state.writing.activeReportDetail = null;
        target.innerHTML = centeredLoadingHtml("正在加载写作报告", "首次打开报告需要读取详情和图表信息。");
      }
      // Fetch detail for the selected report
      try {
        const entry = await fetchWritingReportDetail(itemId);
        state.writing.activeReportDetail = entry;
        target.innerHTML = writingReportDetailHtml(entry);
        target.scrollTo({ top: 0, behavior: cached ? "auto" : "smooth" });
        syncWritingScorePolling(entry, { notifyOnComplete: false });
        if (isWritingTaskActive(entry.ai_task)) startWritingScorePolling(entry.id, { switchOnComplete: false });
      } catch (error) {
        target.innerHTML = `<div class="detail-card"><p class="error">${escapeHtml(error.message || "Failed to load report detail.")}</p></div>`;
      }
    });
  });
  list.querySelectorAll("[data-writing-entry-id]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      showWritingReportItemMenu(button, button.dataset.writingEntryId || "");
    });
  });
  requestAnimationFrame(() => updateReportRailState("writingReportList"));
}

function writingReportTabHtml(item, active = false) {
  const task = item?.ai_task || null;
  const part = item.task_type === "task1_academic" ? "T1" : "T2";
  const band = item.overall_band != null ? `Band ${item.overall_band}` : (isWritingTaskActive(task) ? "评分中" : "未评分");
  const toneClass = item.task_type === "task1_academic" ? "tone-p1" : "tone-p2";
  const tagClass = item.task_type === "task1_academic" ? "p1" : "p2";
  const displayTitle = writingEntryDisplayTitle(item);
  return `
    <button class="history-item writing-report-tab ${toneClass} ${active ? "active" : ""}" data-writing-report-tab="${escapeHtml(item.id || "")}">
      <div class="history-item-top">
        <span class="history-item-tag ${tagClass}">${part}</span>
        <span class="history-item-band">${escapeHtml(band)}</span>
      </div>
      <strong class="history-item-title">${escapeHtml(displayTitle || writingTaskLabel(item.task_type))}</strong>
      <small class="history-item-time">${escapeHtml(item.display_time || item.practice_date || "")} · ${escapeHtml(item.word_count ?? 0)}</small>
    </button>
  `;
}

function showWritingReportItemMenu(anchor, entryId) {
  closeHistoryItemMenu();
  const menu = document.createElement("div");
  menu.className = "history-item-menu";
  menu.innerHTML = `<button class="history-menu-delete" data-writing-entry-delete="${escapeHtml(entryId)}">删除</button>`;
  anchor.parentElement.appendChild(menu);
  menu.querySelector(".history-menu-delete").addEventListener("click", (event) => {
    event.stopPropagation();
    closeHistoryItemMenu();
    showConfirmDelete("确定要删除这篇写作报告吗？", () => deleteWritingReport(entryId));
  });
  setTimeout(() => document.addEventListener("click", closeHistoryItemMenu, { once: true }), 0);
}

async function deleteWritingReport(entryId) {
  if (!entryId) return;
  try {
    if (state.writing.activeReportId === entryId) {
      $("writingReportDetail").innerHTML = centeredLoadingHtml("正在删除写作报告", "删除完成后会自动刷新列表。");
    }
    await api(`/api/writing/entries/${encodeURIComponent(entryId)}`, null, { method: "DELETE" });
    state.writing.reportDetailCache.delete(entryId);
    state.writing.reportEntries = state.writing.reportEntries.filter((item) => item.id !== entryId);
    if (state.writing.activeReportId === entryId) {
      state.writing.activeReportId = state.writing.reportEntries[0]?.id || null;
      state.writing.activeReportDetail = null;
    }
    if (state.writing.entry?.id === entryId) {
      state.writing.entry = null;
      state.writing.dirty = false;
      loadWritingSummary(false).catch(() => null);
      renderWritingSurface();
    }
    if (!state.writing.reportEntries.length) {
      await loadWritingReports(false);
      return;
    }
    await renderWritingReports(state.writing.reportEntries);
  } catch (error) {
    showError(error);
  }
}

function writingReportDetailHtml(entry) {
  const score = entry?.score || null;
  const task = entry?.ai_task || null;
  const taskKey = entry.task_type === "task1_academic" ? "task_achievement" : "task_response";
  const taskLabel = entry.task_type === "task1_academic" ? "TA" : "TR";
  const paragraphReviews = Array.isArray(score?.paragraph_reviews) ? score.paragraph_reviews : [];
  const isScoredReport = isWritingEntryScored(entry);
  const editLabel = isScoredReport ? "修改作文并重新生成报告" : "继续编辑";
  const editAction = `<button type="button" class="primary writing-report-edit-btn" data-writing-report-edit="${escapeHtml(entry.id || "")}" data-writing-report-scored="${isScoredReport ? "true" : "false"}" data-writing-report-task="${escapeHtml(entry.task_type || "")}" data-writing-report-prompt="${escapeHtml(entry.prompt_id || "")}">${editLabel}</button>`;
  const taskName = entry.task_label || writingTaskLabel(entry.task_type);
  const taskSubline = entry.task_type === "task1_academic" ? "Task 1" : "Task 2";
  const displayTitle = writingEntryDisplayTitle(entry);
  const promptText = writingReportPromptText(entry, score);
  const promptImageUrl = writingEntryImageUrl(entry, score);
  const promptFallback = promptText ? null : writingReportPromptFallback(entry);
  const promptDisplayText = promptText || promptFallback?.body || "The original writing prompt was not included in this saved report.";
  const answerText = String(entry.answer || "").trim();
  const promptCard = `
    <div class="writing-prompt-card writing-report-prompt-card">
      <span class="writing-pill">${escapeHtml(writingTaskLabel(entry.task_type))}</span>
      ${promptFallback?.title ? `<h2>${escapeHtml(promptFallback.title)}</h2>` : ""}
      <p class="writing-report-prompt-text">${escapeHtml(promptDisplayText).replace(/\n/g, "<br>")}</p>
      ${entry.task_type === "task1_academic" && promptImageUrl ? `
        <div class="writing-prompt-image">
          <img src="${escapeHtml(promptImageUrl)}" alt="Task 1 chart" loading="eager" decoding="async" data-writing-image-preview onerror="this.parentElement.classList.add('hidden')">
        </div>
      ` : ""}
    </div>
  `;
  const taskBlock = !score && task ? `
    <div class="detail-card writing-task-state-card">
      <div class="detail-header">
        <div>
          <h2>${escapeHtml(writingTaskStatusTitle(task))}</h2>
          <p class="muted">${escapeHtml(writingTaskStatusText(task))}</p>
        </div>
        <strong class="overall-badge muted-badge">${escapeHtml(task.status || "pending")}</strong>
      </div>
    </div>
  ` : "";
  const scoreBlock = score ? `
    <div class="detail-card writing-score-summary-card" data-writing-report-id="${escapeHtml(entry.id || "")}">
      <div class="writing-score-summary-head">
        <div class="writing-score-summary-copy">
          <span class="section-label">IELTS Writing 练习估分</span>
          <h2>${escapeHtml(displayTitle || taskName)}</h2>
          <p class="muted">${taskSubline} · ${escapeHtml(entry.word_count ?? 0)} words</p>
        </div>
        <div class="writing-score-summary-band">
          <span>Overall</span>
          <strong>Band ${escapeHtml(score.overall_band ?? "—")}</strong>
        </div>
      </div>
      <div class="writing-score-summary-grid">
        ${scoreCell(taskLabel, score[taskKey], entry.task_type === "task1_academic" ? "任务完成" : "任务回应")}
        ${scoreCell("CC", score.coherence_cohesion, "连贯衔接")}
        ${scoreCell("LR", score.lexical_resource, "词汇资源")}
        ${scoreCell("GRA", score.grammatical_range_accuracy, "语法准确")}
      </div>
    </div>
    <div class="detail-card overall-review-card writing-overall-review-card">
      <div class="writing-overall-head">
        <h3>Overall Review & Practice Focus</h3>
        <div class="writing-report-actions">${editAction}</div>
      </div>
      <div class="overall-review-content writing-overall-content">
        <section>
          <h4>总体点评</h4>
          <p>${escapeHtml(score.overall_review || "这篇作文已经完成评分。下面按段落查看你的原文、AI 写法和具体辅导。")}</p>
        </section>
        <section>
          <h4>复盘重点</h4>
          <p>${escapeHtml(score.practice_focus || "复盘时优先看段落组织、中心句和具体展开。")}</p>
        </section>
      </div>
    </div>
    ${promptCard}
    ${score.structure_advice_only ? writingStructureAdviceHtml(score, entry) : writingParagraphReviewHtml(entry, score, paragraphReviews)}
  ` : `
    <div class="detail-card writing-saved-report-card" data-writing-report-id="${escapeHtml(entry.id || "")}">
      <div class="writing-saved-report-head">
        <div>
          <span class="section-label">Saved draft</span>
          <h2>${escapeHtml(displayTitle || `${taskSubline} 已保存`)}</h2>
          <p>${escapeHtml(taskSubline)} · ${escapeHtml(entry.word_count ?? 0)} words · ${escapeHtml(entry.display_time || entry.practice_date || "")}</p>
        </div>
        <strong><span>Draft</span>未评分</strong>
      </div>
      <div class="writing-draft-flow" aria-label="未评分作文处理步骤">
        <span class="is-done"><strong>1</strong>正文已保存</span>
        <span><strong>2</strong>回编辑页检查</span>
        <span><strong>3</strong>发起 AI 评分</span>
      </div>
      <div class="writing-saved-report-body writing-draft-summary">
        <section class="writing-draft-primary">
          <span>下一步</span>
          <h3>继续编辑并生成报告</h3>
          <p>这篇作文已经保存。需要反馈时，回到编辑页检查题目、正文和字数，然后重新发起 AI 评分与辅导。</p>
        </section>
        <section>
          <span>当前状态</span>
          <h3>${answerText ? "正文可用" : "正文为空"}</h3>
          <p>${answerText ? "已保存正文，可以继续修改或发起评分。" : "这篇记录目前没有正文内容，建议先补全文本再评分。"}</p>
        </section>
      </div>
      <div class="writing-saved-report-actions">${editAction}</div>
    </div>
  `;
  return `
    ${taskBlock}
    ${scoreBlock}
    ${score ? "" : `<div class="detail-card writing-report-answer writing-saved-answer-card">
      <div class="writing-saved-answer-head">
        <h3>我的作文</h3>
        <span>${escapeHtml(entry.word_count ?? 0)} words</span>
      </div>
      ${answerText ? `<p>${escapeHtml(answerText).replace(/\n/g, "<br>")}</p>` : `<p class="muted">还没有保存作文正文。</p>`}
    </div>`}
  `;
}

function writingStructureAdviceHtml(score, entry) {
  const answerParagraphs = writingParagraphs(entry.answer || "");
  const inlineAnnotations = writingInlineAnnotations(score || {});
  return `
    <section class="detail-card writing-structure-advice-card">
      <span class="section-label">Paragraph structure first</span>
      <h3>分段修改意见</h3>
      <p class="muted">这篇作文的结构还不适合逐段对应生成“我的原文 / AI 写法 / AI 辅导”。建议先按下面方向重排段落，再重新生成报告。</p>
      <div class="coaching-content">${renderMarkdown(score.structure_advice || score.practice_focus || "先把作文拆成清楚段落，再重新生成报告。")}</div>
      ${answerParagraphs.length ? `<div class="writing-structure-preview">${answerParagraphs.map((paragraph, index) => `
        <article>
          <h4>当前段落 ${index + 1}</h4>
          <p class="writing-annotated-original">${renderWritingAnnotatedText(paragraph, writingAnnotationsForParagraph(inlineAnnotations, paragraph, index + 1))}</p>
        </article>
      `).join("")}</div>` : ""}
    </section>
    ${writingSpellingSummaryHtml(score || {})}
  `;
}

function writingParagraphReviewHtml(entry, score, reviews) {
  const answerParagraphs = writingParagraphs(entry.answer || "");
  const inlineAnnotations = writingInlineAnnotations(score || {});
  const items = reviews.length ? reviews : answerParagraphs.map((paragraph, index) => ({
    index: index + 1,
    learner: paragraph,
    model: "",
    coaching: "这一段可以继续优化中心句、展开和连接方式。",
  }));
  if (!items.length) return "";
  const rows = items.map((item, index) => {
    const paragraphIndex = Number.parseInt(item.index || index + 1, 10);
    const learnerText = item.learner || answerParagraphs[index] || "";
    const paragraphAnnotations = writingAnnotationsForParagraph(inlineAnnotations, learnerText, paragraphIndex);
    return `
      <tbody class="turn-report-group writing-paragraph-group">
        <tr class="writing-paragraph-content-row">
          <td>
            <div class="question-header"><strong>Paragraph ${escapeHtml(paragraphIndex || index + 1)}</strong></div>
            <p class="writing-annotated-original">${renderWritingAnnotatedText(learnerText, paragraphAnnotations)}</p>
          </td>
          <td>
            <p>${escapeHtml(item.model || "暂无 AI 改写。").replace(/\n/g, "<br>")}</p>
          </td>
        </tr>
        <tr class="writing-paragraph-coaching-row">
          <td colspan="2" class="ai-coaching-cell">
            <h4 class="coaching-title">AI 辅导</h4>
            <div class="coaching-content">${renderMarkdown(writingParagraphCoachingMarkdown(item, score || {}))}</div>
          </td>
        </tr>
      </tbody>
    `;
  }).join("");
  return `
    <div class="detail-card turn-report-card writing-paragraph-report-card">
      <div class="turn-report-wrap">
        <table class="turn-report-table writing-paragraph-report-table">
          <thead><tr><th>我的原文</th><th>AI 写法</th></tr></thead>
          ${rows}
        </table>
      </div>
    </div>
    ${writingSpellingSummaryHtml(score || {})}
  `;
}

function setWritingPrompt(prompt, clearAnswer = true, options = {}) {
  clearWritingAutosaveTimer();
  state.writing.autosaveEnabled = false;
  state.writing.autosaveQueued = false;
  resetWritingFrameAutosaveBaseline();
  state.writing.prompt = prompt;
  state.writing.taskType = prompt.task_type || state.writing.taskType;
  if (prompt?.task_type === "task1_academic" && prompt.image_url) {
    primeWritingPromptImage(prompt.image_url);
  }
  const existingHighlights = loadWritingPromptHighlights();
  const highlightKey = writingPromptHighlightKey(prompt);
  if (highlightKey) {
    const currentHighlights = state.writing.promptHighlights[highlightKey];
    const promptHighlights = Array.isArray(prompt.prompt_highlights) ? prompt.prompt_highlights : [];
    state.writing.promptHighlights[highlightKey] = normalizeWritingPromptHighlightRanges(
      promptHighlights.length
        ? promptHighlights
        : (Array.isArray(currentHighlights) && currentHighlights.length ? currentHighlights : existingHighlights[highlightKey] || []),
      String(prompt.prompt || "")
    );
  }
  if (clearAnswer) {
    state.writing.entry = null;
    state.writing.dirty = false;
    if ($("writingAnswer")) $("writingAnswer").value = "";
  }
  renderWritingSurface();
  if (!options.skipUrl) syncUrlForCurrentState({ replace: Boolean(options.replaceUrl) });
}

function renderWritingSurface() {
  const taskType = state.writing.taskType || "task1_academic";
  setWritingSwitchState(".writing-topbar-actions .writing-task-switch", taskType);
  document.querySelectorAll("[data-writing-task]").forEach((button) => {
    button.classList.toggle("active", button.dataset.writingTask === taskType);
  });
  const prompt = state.writing.prompt;
  const pickerButton = $("writingPromptPickerBtn");
  const pickerHint = $("writingPromptPickerMeta");
  const promptTitle = prompt ? writingPromptCardTitle(prompt) : "\u9009\u62e9\u4e00\u9053\u9898\u5f00\u59cb";
  text("writingPromptType", writingTaskLabel(taskType));
  text("writingPromptTitle", promptTitle);
  $("writingPromptTitle")?.classList.toggle("hidden", Boolean(prompt && !promptTitle));
  text("writingPromptPickerTitle", prompt ? writingPromptTopbarTitle(prompt) : "\u9009\u62e9\u5199\u4f5c\u9898\u76ee");
  if (pickerButton) {
    pickerButton.title = prompt
      ? `点击更换题目：${writingPromptPickerTitle(prompt)}`
      : "点击进入选题界面";
    pickerButton.setAttribute("aria-label", pickerButton.title);
  }
  if (pickerHint) {
    pickerHint.textContent = prompt ? "点击更换" : "打开题库";
  }
  const promptText = prompt?.prompt || "\u8bf7\u9009\u62e9\u4e00\u9053\u9898\uff0c\u6216\u70b9\u51fb\u968f\u673a\u9898\u5f00\u59cb\u3002";
  const highlightRanges = writingPromptHighlightKey(prompt) ? currentWritingPromptHighlightState() : [];
  $("writingPromptText").innerHTML = taskType === "task2"
    ? renderTask2PromptTextWithHighlights(promptText, highlightRanges)
    : renderWritingPromptTextWithHighlights(promptText, highlightRanges);
  hideWritingHighlightMenu();

  // Render Task 1 image if available
  const imageContainer = $("writingPromptImage");
  if (imageContainer) {
    if (taskType === "task1_academic" && prompt?.image_url) {
      const imageUrl = String(prompt.image_url || "").trim();
      primeWritingPromptImage(imageUrl);
      if (imageContainer.dataset.imageUrl !== imageUrl || imageContainer.classList.contains("image-error")) {
        imageContainer.dataset.imageUrl = imageUrl;
        imageContainer.innerHTML = `
          <div class="writing-prompt-image-loading" aria-hidden="true">
            <span></span>
            <strong>图表加载中</strong>
          </div>
          <img src="${escapeHtml(imageUrl)}" alt="Task 1 chart" loading="eager" decoding="async" fetchpriority="high" data-writing-image-preview
            onload="this.parentElement.classList.add('image-ready')"
            onerror="this.parentElement.classList.add('image-error'); this.remove();">
        `;
        imageContainer.classList.remove("image-ready", "image-error");
      }
      imageContainer.classList.remove("hidden");
      scheduleNearbyWritingPromptImagePreload(prompt);
    } else {
      imageContainer.innerHTML = "";
      imageContainer.dataset.imageUrl = "";
      imageContainer.classList.remove("image-ready", "image-error");
      imageContainer.classList.add("hidden");
    }
  }

  const entry = state.writing.entry;
  renderWritingScore(entry);
  updateWritingWordCount({ reset: true });
  if (entry?.ai_task && isWritingTaskActive(entry.ai_task)) {
    text("writingSaveStatus", writingTaskStatusTitle(entry.ai_task));
  } else if (!entry?.id) {
    text("writingSaveStatus", "\u672a\u4fdd\u5b58");
  } else if (entry.status === "scored") {
    text("writingSaveStatus", `\u5df2\u8bc4\u5206 \u00b7 ${entry.practice_date || ""} \u00b7 \u53ef\u5728\u5199\u4f5c\u62a5\u544a\u67e5\u770b`);
  } else {
    text("writingSaveStatus", `\u5df2\u4fdd\u5b58 \u00b7 ${entry.practice_date || ""}`);
  }
}

function currentWritingPromptImageUrl() {
  return String(state.writing.prompt?.image_url || $("writingPromptImage img")?.getAttribute("src") || "").trim();
}

const writingImageViewerController = window.IELTSWritingImageViewer?.createWritingImageViewerController?.({
  state,
  $,
  currentWritingPromptImageUrl,
});

function applyWritingPromptHighlightSelection() {
  const prompt = state.writing.prompt;
  const promptId = writingPromptHighlightKey(prompt);
  if (!promptId) return;
  if (state.writing.highlightMenuMode === "clear") {
    deletePendingWritingPromptHighlight();
    hideWritingHighlightMenu();
    setWritingHighlightMenuMode("select");
    window.getSelection?.().removeAllRanges?.();
    return;
  }
  const selectionRange = getWritingPromptSelectionRange();
  if (!selectionRange) return;
  const current = currentWritingPromptHighlightState();
  const exactIndex = current.findIndex((range) => range.start === selectionRange.start && range.end === selectionRange.end);
  if (exactIndex >= 0) {
    hideWritingHighlightMenu();
    setWritingHighlightMenuMode("select");
    window.getSelection?.().removeAllRanges?.();
    return;
  } else {
    current.push({ start: selectionRange.start, end: selectionRange.end });
  }
  setWritingPromptHighlightState(promptId, current);
  hideWritingHighlightMenu();
  setWritingHighlightMenuMode("select");
  window.getSelection?.().removeAllRanges?.();
}

function handleWritingPromptSelectionChange(options = {}) {
  const { force = false, delay = 120 } = options;
  window.clearTimeout(state.writing.promptSelectionTimer);
  // Delete menus are opened by an explicit click/focus action on an existing mark.
  // Selection churn from that same pointer gesture must not immediately close it.
  if (isWritingHighlightDeleteMenuOpen()) return;
  if (state.writing.promptSelectionActive && !force) {
    hideWritingHighlightMenu();
    return;
  }
  state.writing.promptSelectionTimer = window.setTimeout(() => {
    if (state.writing.promptSelectionActive && !force) {
      hideWritingHighlightMenu();
      return;
    }
    const menu = $("writingHighlightMenu");
    if (!menu) return;
    const selectionRange = getWritingPromptSelectionRange();
    if (selectionRange) {
      setWritingHighlightMenuMode("select");
      positionWritingHighlightMenu(selectionRange.rect);
      menu.classList.remove("hidden");
      hideLanguageTakeawayTrigger();
      return;
    }
    const selection = selectionText();
    if (selection?.source === "writing_prompt") hideLanguageTakeawayTrigger();
    if (isWritingHighlightDeleteMenuOpen()) return;
    hideWritingHighlightMenu();
  }, delay);
}

function openWritingImageViewer(src = currentWritingPromptImageUrl()) {
  writingImageViewerController?.open(src);
}

function closeWritingImageViewer() {
  writingImageViewerController?.close();
}

function isWritingImageViewerOpen() {
  return Boolean(writingImageViewerController?.isOpen());
}

function canToggleWritingImageViewer() {
  return Boolean(writingImageViewerController?.canToggle());
}

function isShiftSpaceShortcut(event) {
  return Boolean(writingImageViewerController?.isShiftSpaceShortcut(event));
}

function handleGlobalKeydown(event) {
  const reviewKey = String(event.key || "").toLowerCase();
  if (!event.repeat && !event.metaKey && !event.ctrlKey && !event.altKey && (reviewKey === "a" || reviewKey === "d")) {
    const kind = state.view === "writingTakeawayBook" ? "writing" : (state.view === "takeawayBook" ? "language" : "");
    if (kind && isTakeawayReviewActiveForKind(kind) && !isEditableShortcutTarget(event.target)) {
      event.preventDefault();
      event.stopPropagation();
      takeawayReviewFeedback(kind, "", reviewKey === "d" ? "again" : "mastered");
      return;
    }
  }

  if (isShiftSpaceShortcut(event) && canToggleWritingImageViewer()) {
    event.preventDefault();
    event.stopPropagation();
    if (!event.repeat) toggleWritingImageViewer();
    return;
  }

  if (event.key !== "Escape") return;
  if (isWritingImageViewerOpen()) {
    event.preventDefault();
    closeWritingImageViewer();
  } else if (!$("writingHighlightMenu")?.classList.contains("hidden")) {
    event.preventDefault();
    hideWritingHighlightMenu();
  } else if (document.querySelector("[data-corpus-card-action-menu]:not(.hidden)")) {
    event.preventDefault();
    closeCorpusCardActionMenus();
  } else if (!$("takeawayEditDialog")?.classList.contains("hidden")) {
    event.preventDefault();
    closeTakeawayEditor();
  } else if (!$("p1CorpusDialog")?.classList.contains("hidden")) {
    event.preventDefault();
    saveAndCloseP1CorpusEditor();
  } else if (!$("p1CorpusPeekDialog")?.classList.contains("hidden")) {
    event.preventDefault();
    closeP1CorpusPeek();
  } else if (!$("p2CorpusPeekDialog")?.classList.contains("hidden")) {
    event.preventDefault();
    closeP2CorpusPeek();
  } else if (!$("p3CorpusPeekDialog")?.classList.contains("hidden")) {
    event.preventDefault();
    closeP3CorpusPeek();
  } else if (!$("p2CorpusDialog")?.classList.contains("hidden")) {
    event.preventDefault();
    saveAndCloseP2CorpusEditor();
  } else if (!$("p2CorpusP3Dialog")?.classList.contains("hidden")) {
    event.preventDefault();
    saveAndCloseP2CorpusP3Editor();
  }
}

function toggleWritingImageViewer() {
  writingImageViewerController?.toggle();
}

function hideWritingHighlightMenu() {
  const menu = $("writingHighlightMenu");
  if (!menu) return;
  menu.classList.add("hidden");
  state.writing.pendingHighlightDeleteIndex = -1;
  state.writing.pendingHighlightPointer = null;
}

function isWritingHighlightDeleteMenuOpen() {
  const menu = $("writingHighlightMenu");
  return Boolean(menu && !menu.classList.contains("hidden") && state.writing.highlightMenuMode === "clear");
}

function positionWritingHighlightMenu(rect) {
  const menu = $("writingHighlightMenu");
  if (!menu || !rect) return;
  const margin = 12;
  const menuRect = menu.getBoundingClientRect();
  const width = menuRect.width || 148;
  const height = menuRect.height || 52;
  const left = Math.min(window.innerWidth - width - margin, Math.max(margin, rect.right - width));
  const top = Math.min(window.innerHeight - height - margin, Math.max(margin, rect.top - height - 10));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function positionWritingHighlightMenuNearPoint(clientX, clientY) {
  const menu = $("writingHighlightMenu");
  if (!menu) return;
  const margin = 12;
  const gap = 10;
  const menuRect = menu.getBoundingClientRect();
  const width = menuRect.width || 148;
  const height = menuRect.height || 52;
  const preferRight = clientX + gap + width <= window.innerWidth - margin;
  const preferBelow = clientY + gap + height <= window.innerHeight - margin;
  const left = preferRight ? clientX + gap : clientX - width - gap;
  const top = preferBelow ? clientY + gap : clientY - height - gap;
  menu.style.left = `${Math.min(window.innerWidth - width - margin, Math.max(margin, left))}px`;
  menu.style.top = `${Math.min(window.innerHeight - height - margin, Math.max(margin, top))}px`;
}

function openWritingPromptHighlightDeleteMenu(index, anchor) {
  const menu = $("writingHighlightMenu");
  if (!menu || !Number.isInteger(index) || index < 0) return;
  state.writing.pendingHighlightDeleteIndex = index;
  setWritingHighlightMenuMode("clear");
  menu.classList.remove("hidden");
  if (anchor && Number.isFinite(anchor.clientX) && Number.isFinite(anchor.clientY)) {
    positionWritingHighlightMenuNearPoint(anchor.clientX, anchor.clientY);
  } else {
    positionWritingHighlightMenu(anchor);
  }
  hideLanguageTakeawayTrigger();
}

function renderWritingScore(entry) {
  const score = entry?.score || null;
  if (!score) {
    return;
  }
  text("writingSaveStatus", `\u5df2\u8bc4\u5206 \u00b7 Band ${score.overall_band ?? "\u2014"} \u00b7 \u53ef\u5728\u5199\u4f5c\u62a5\u544a\u67e5\u770b`);
}

function openWritingPromptPicker(taskType = state.writing.taskType || "task1_academic") {
  writingPromptPickerController.open(taskType);
}

function closeWritingPromptPicker() {
  writingPromptPickerController.close();
}

function renderWritingPromptPicker() {
  writingPromptPickerController.render();
}

function renderWritingPromptPickerError(error) {
  writingPromptPickerController.renderError(error);
}

function renderWritingPromptPickerShell(taskType) {
  writingPromptPickerController.renderShell(taskType);
}

async function chooseRandomWritingPrompt(confirmDirty = true) {
  return writingPromptPickerController.chooseRandom(confirmDirty);
}

async function saveWritingEntry(keepPending = false, options = {}) {
  const prompt = state.writing.prompt;
  if (!prompt) throw new Error("\u8bf7\u5148\u9009\u62e9\u4e00\u9053\u5199\u4f5c\u9898\u3002");
  const answer = $("writingAnswer")?.value || "";
  const startedHighlights = JSON.stringify(currentWritingPromptHighlightsPayload());
  const previousEntry = state.writing.entry || null;
  const previousEntryId = String(previousEntry?.id || "").trim();
  const savingExistingUnscoredEntry = Boolean(previousEntryId) && !isWritingEntryScored(previousEntry);
  const payload = {
    id: previousEntry?.id,
    task_type: prompt.task_type || state.writing.taskType,
    prompt_id: prompt.id,
    prompt: prompt.prompt,
    title: writingPromptDisplayTitle(prompt),
    category: prompt.category,
    image_url: prompt.image_url || "",
    answer,
    prompt_highlights: currentWritingPromptHighlightsPayload(),
  };
  const saveButton = $("writingSaveBtn");
  const originalSaveText = saveButton?.textContent || "\u4fdd\u5b58\u4f5c\u6587";
  const updateButton = !options.autosave && saveButton;
  if (updateButton) {
    saveButton.disabled = true;
    saveButton.textContent = "\u4fdd\u5b58\u4e2d";
  }
  try {
    const entry = await api("/api/writing/entries", payload);
    const currentAnswer = $("writingAnswer")?.value || "";
    const currentHighlights = JSON.stringify(currentWritingPromptHighlightsPayload());
    const changedAfterRequest = currentAnswer !== answer || currentHighlights !== startedHighlights;
    state.writing.entry = changedAfterRequest ? { ...entry, answer: currentAnswer } : entry;
    state.writing.dirty = changedAfterRequest;
    if (!changedAfterRequest) resetWritingFrameAutosaveBaseline();
    if (savingExistingUnscoredEntry && String(entry?.id || "") === previousEntryId && !isWritingEntryScored(entry)) {
      syncWritingReportEntryCache(entry);
      renderVisibleWritingReport(entry);
    }
    if (options.autosave) {
      updateWritingWordCount({ preserveScroll: true });
    } else {
      renderWritingSurface();
    }
    if (changedAfterRequest) {
      text("writingSaveStatus", "\u672a\u4fdd\u5b58\u7684\u4fee\u6539");
    } else if (options.autosave) {
      text("writingSaveStatus", `\u5df2\u81ea\u52a8\u4fdd\u5b58 \u00b7 ${entry.practice_date || ""}`);
    }
    await loadWritingSummary();
    if (updateButton) {
      saveButton.textContent = "\u5df2\u4fdd\u5b58";
      window.setTimeout(() => {
        if (saveButton.textContent === "\u5df2\u4fdd\u5b58") saveButton.textContent = originalSaveText;
      }, 1200);
    }
    return entry;
  } finally {
    if (updateButton) saveButton.disabled = false;
  }
}

function isWritingTaskActive(task) {
  return Boolean(task && isAiTaskActiveStatus(task.status));
}

function isWritingTaskTerminal(task) {
  return Boolean(task && isAiTaskTerminalStatus(task.status));
}

function writingTaskStatusTitle(task) {
  const status = String(task?.status || "pending");
  if (status === "running") return "AI 正在评分与生成辅导";
  if (status === "pending") return "AI 评分已排队";
  if (status === "fallback") return "AI 评分使用了系统默认建议";
  if (status === "succeeded") return "AI 评分已完成";
  if (status === "cancelled") return "AI 评分已取消";
  if (status === "failed") return "AI 评分失败";
  return "AI 评分状态更新中";
}

function writingTaskStatusText(task) {
  const status = String(task?.status || "pending");
  if (status === "running") return "任务已经开始，刷新或切换页面不会丢失结果；完成后会写入写作报告。";
  if (status === "pending") return "任务正在等待后台 worker 处理。刷新页面后仍可从写作记录中恢复。";
  if (status === "cancelled") return "这次评分尚未开始时被取消，作文仍然已保存并计入签到。";
  if (status === "failed") return task?.error_message || "这次评分没有生成可用结果，可以稍后重新评分。";
  return "结果已写入这篇作文的记录。";
}

function writingScoreNotificationKey(entry, task = entry?.ai_task || null) {
  return String(task?.id || entry?.id || "").trim();
}

function writingScoreCompleteCriteriaHtml(entry = {}, score = null) {
  if (!score) return "";
  const taskKey = entry.task_type === "task1_academic" ? "task_achievement" : "task_response";
  const taskLabel = entry.task_type === "task1_academic" ? "Task Achievement" : "Task Response";
  return `
    ${scoreCell(taskLabel, score[taskKey])}
    ${scoreCell("CC", score.coherence_cohesion)}
    ${scoreCell("LR", score.lexical_resource)}
    ${scoreCell("GRA", score.grammatical_range_accuracy)}
  `;
}

function speakingScoreNotificationKey(attempt) {
  return String(attempt?.id || "").trim();
}

function isSpeakingTaskActive(task) {
  return Boolean(task && isAiTaskActiveStatus(task.status));
}

function isSpeakingTaskTerminal(task) {
  return Boolean(task && isAiTaskTerminalStatus(task.status));
}

function speakingTaskStatusTitle(task) {
  const status = String(task?.status || "pending");
  if (status === "running") return "AI 正在分析口语报告";
  if (status === "pending") return "AI 口语分析已排队";
  if (status === "succeeded") return "AI 口语分析已完成";
  if (status === "cancelled") return "AI 口语分析已取消";
  if (status === "failed" || status === "fallback") return "AI 口语分析失败";
  return "AI 口语分析状态更新中";
}

function speakingTaskStatusText(task) {
  const status = String(task?.status || "pending");
  if (status === "running") return "任务已经在后台运行，可以切换页面；完成后会弹窗通知。";
  if (status === "pending") return "任务正在等待后台 worker 处理，可以切换页面。";
  if (status === "failed" || status === "fallback") return task?.error_message || task?.fallback_reason || "这次口语分析没有生成可用报告，可以重试。";
  return "口语报告已生成。";
}

function speakingScoreCompleteCriteriaHtml(score = null) {
  if (!score) return "";
  return `
    ${scoreCell("FC", score.fluency_coherence)}
    ${scoreCell("LR", score.lexical_resource)}
    ${scoreCell("GRA", score.grammatical_range)}
  `;
}

function showSpeakingScoreCompleteModal(attempt) {
  if (!attempt?.id) return;
  const notificationKey = speakingScoreNotificationKey(attempt);
  if (notificationKey && state.speaking.scoreCompletionNotifiedIds.has(notificationKey)) return;
  if (notificationKey) state.speaking.scoreCompletionNotifiedIds.add(notificationKey);
  state.speaking.scoreCompletionModalAttempt = attempt;
  const score = attempt.ielts_score || null;
  text("speakingScoreCompleteTitle", "口语分析已完成");
  text("speakingScoreCompleteText", score
    ? "口语报告已经生成，可以在方便的时候查看详细反馈。"
    : "口语报告已经生成，但本次没有返回完整分数。可以打开报告查看可用反馈。");
  text("speakingScoreCompleteBand", score?.overall_band != null ? `Band ${score.overall_band}` : "Band —");
  const criteria = $("speakingScoreCompleteCriteria");
  if (criteria) {
    criteria.innerHTML = speakingScoreCompleteCriteriaHtml(score);
    criteria.classList.toggle("hidden", !score);
  }
  $("speakingScoreCompleteModal")?.classList.remove("hidden");
}

function closeSpeakingScoreCompleteModal() {
  state.speaking.scoreCompletionModalAttempt = null;
  $("speakingScoreCompleteModal")?.classList.add("hidden");
}

function openSpeakingScoreCompleteReport() {
  const attempt = state.speaking.scoreCompletionModalAttempt;
  if (!attempt?.id) return closeSpeakingScoreCompleteModal();
  state.activeHistoryId = attempt.id;
  state.historyDetailCache.set(attempt.id, attempt);
  closeSpeakingScoreCompleteModal();
  switchView("history");
  renderDetail(attempt, false);
}

function showWritingScoreCompleteModal(entry, task = entry?.ai_task || null) {
  if (!entry?.id) return;
  const notificationKey = writingScoreNotificationKey(entry, task);
  const entryKey = String(entry.id || "").trim();
  const taskKey = String(task?.id || "").trim();
  if ((notificationKey && state.writing.scoreCompletionNotifiedIds.has(notificationKey))
    || (entryKey && state.writing.scoreCompletionNotifiedIds.has(entryKey))
    || (taskKey && state.writing.scoreCompletionNotifiedIds.has(taskKey))) return;
  if (notificationKey) state.writing.scoreCompletionNotifiedIds.add(notificationKey);
  if (entryKey) state.writing.scoreCompletionNotifiedIds.add(entryKey);
  if (taskKey) state.writing.scoreCompletionNotifiedIds.add(taskKey);
  state.writing.scoreCompletionModalEntry = entry;
  const score = entry.score || null;
  text("writingScoreCompleteTitle", writingTaskStatusTitle(task));
  text("writingScoreCompleteText", score
    ? "写作报告已经生成，可以在方便的时候查看详细反馈。"
    : writingTaskStatusText(task));
  text("writingScoreCompleteBand", score?.overall_band != null ? `Band ${score.overall_band}` : "Band —");
  const criteria = $("writingScoreCompleteCriteria");
  if (criteria) {
    criteria.innerHTML = writingScoreCompleteCriteriaHtml(entry, score);
    criteria.classList.toggle("hidden", !score);
  }
  $("writingScoreCompleteModal")?.classList.remove("hidden");
}

function closeWritingScoreCompleteModal() {
  state.writing.scoreCompletionModalEntry = null;
  $("writingScoreCompleteModal")?.classList.add("hidden");
}

function openWritingScoreCompleteReport() {
  const entry = state.writing.scoreCompletionModalEntry;
  if (!entry?.id) return closeWritingScoreCompleteModal();
  state.writing.activeReportId = entry.id;
  state.writing.activeReportDetail = entry;
  state.writing.reportDetailCache.set(entry.id, entry);
  closeWritingScoreCompleteModal();
  switchView("writingReports");
}

function clearWritingScorePolling() {
  if (state.writing.scorePollTimer) {
    clearTimeout(state.writing.scorePollTimer);
    state.writing.scorePollTimer = null;
  }
  state.writing.scorePollingEntryId = null;
}

function isScoreTaskUnsupported(error) {
  const message = String(error?.message || "");
  return error?.status === 404 && /Unknown API endpoint/i.test(message);
}

async function cloneWritingEntryForRevision(entryId) {
  try {
    return await api(`/api/writing/entries/${encodeURIComponent(entryId)}/clone`, {});
  } catch (error) {
    if (error?.status !== 404) throw error;
    const source = await api(`/api/writing/entries/${encodeURIComponent(entryId)}`);
    if (!source?.id) throw error;
    return api("/api/writing/entries", {
      task_type: source.task_type || "task2",
      prompt_id: source.prompt_id || "",
      prompt: source.prompt || "",
      title: source.title || writingEntryDisplayTitle(source) || writingTaskLabel(source.task_type),
      category: source.category || "",
      image_url: source.image_url || "",
      answer: source.answer || "",
      prompt_highlights: source.prompt_highlights || [],
    });
  }
}

function cachedWritingReportEntry(entryId) {
  const id = String(entryId || "").trim();
  if (!id) return null;
  if (String(state.writing.activeReportDetail?.id || "") === id) return state.writing.activeReportDetail;
  return state.writing.reportDetailCache.get(id) || null;
}

function mergeWritingReportEntryMetadata(entry) {
  const id = String(entry?.id || "").trim();
  if (!id || !Array.isArray(state.writing.reportEntries)) return false;
  const reportIndex = state.writing.reportEntries.findIndex((item) => String(item?.id || "") === id);
  if (reportIndex < 0) return false;
  const reportEntries = [...state.writing.reportEntries];
  const existing = reportEntries[reportIndex] || {};
  reportEntries[reportIndex] = {
    ...existing,
    status: entry.status ?? existing.status,
    overall_band: entry.score?.overall_band ?? entry.overall_band ?? existing.overall_band,
    ai_task: entry.ai_task ?? existing.ai_task,
    title: entry.title ?? existing.title,
    category: entry.category ?? existing.category,
    task_type: entry.task_type ?? existing.task_type,
    task_label: entry.task_label ?? existing.task_label,
    prompt: entry.prompt ?? existing.prompt,
    prompt_id: entry.prompt_id ?? existing.prompt_id,
    word_count: entry.word_count ?? existing.word_count,
    display_time: entry.display_time ?? existing.display_time,
    practice_date: entry.practice_date ?? existing.practice_date,
    updated_at: entry.updated_at ?? existing.updated_at,
    source: entry.source ?? existing.source,
    source_book: entry.source_book ?? existing.source_book,
    source_test: entry.source_test ?? existing.source_test,
    source_question: entry.source_question ?? existing.source_question,
    source_label: entry.source_label ?? existing.source_label,
    display_source_label: entry.display_source_label ?? existing.display_source_label,
    prompt_highlights: entry.prompt_highlights ?? existing.prompt_highlights,
  };
  state.writing.reportEntries = reportEntries;
  return true;
}

function syncWritingReportEntryCache(entry, options = {}) {
  const id = String(entry?.id || "").trim();
  if (!id) return false;
  state.writing.reportDetailPromises.delete(id);
  state.writing.reportDetailCache.set(id, entry);
  if (String(state.writing.activeReportDetail?.id || "") === id) state.writing.activeReportDetail = entry;
  const metadataChanged = mergeWritingReportEntryMetadata(entry);
  if (metadataChanged && options.renderList && state.view === "writingReports") {
    renderWritingReportList(state.writing.reportEntries);
  }
  return metadataChanged;
}

function writingReportEntryFromEditButton(button) {
  const entryId = button?.dataset?.writingReportEdit || "";
  const cached = cachedWritingReportEntry(entryId) || {};
  return {
    ...cached,
    id: entryId,
    status: button?.dataset?.writingReportScored === "true" ? "scored" : (cached.status || "saved"),
    score: button?.dataset?.writingReportScored === "true" ? (cached.score || { overall_band: cached.overall_band ?? null }) : null,
    task_type: cached.task_type || button?.dataset?.writingReportTask || state.writing.taskType || "task1_academic",
    prompt_id: cached.prompt_id || button?.dataset?.writingReportPrompt || "",
  };
}

function showWritingReportEditError(error) {
  const message = error instanceof Error ? error.message : String(error);
  showWritingError(error);
  if (state.view !== "writingReports") return;
  const target = $("writingReportDetail");
  if (!target) return;
  const existing = target.querySelector("[data-writing-report-edit-error]");
  if (existing) existing.remove();
  target.insertAdjacentHTML("afterbegin", `<div class="detail-card" data-writing-report-edit-error><p class="error">${escapeHtml(message)}</p></div>`);
}

function renderVisibleWritingReport(entry) {
  const id = String(entry?.id || "").trim();
  if (!id) return;
  syncWritingReportEntryCache(entry, { renderList: state.view === "writingReports" });
  if (state.view !== "writingReports" || String(state.writing.activeReportId || "") !== id) return;
  state.writing.activeReportDetail = entry;
  const target = $("writingReportDetail");
  if (target) target.innerHTML = writingReportDetailHtml(entry);
}

async function recoverWritingEntry(entry) {
  state.writing.entry = entry;
  state.writing.taskType = entry.task_type || state.writing.taskType || "task2";
  await loadWritingPrompts(state.writing.taskType);
  state.writing.prompt = {
    id: entry.prompt_id,
    task_type: entry.task_type,
    task_label: entry.task_label,
    title: entry.title,
    prompt: entry.prompt,
    category: entry.category,
    image_url: entry.image_url || "",
    source: entry.source || "",
    source_book: entry.source_book,
    source_test: entry.source_test,
    source_question: entry.source_question,
    source_label: entry.source_label || "",
    display_source_label: entry.display_source_label || "",
    prompt_highlights: entry.prompt_highlights || [],
  };
  const highlightKey = writingPromptHighlightKey(state.writing.prompt);
  if (highlightKey) {
    state.writing.promptHighlights[highlightKey] = normalizeWritingPromptHighlightRanges(
      entry.prompt_highlights || [],
      String(state.writing.prompt.prompt || "")
    );
    saveWritingPromptHighlights();
  }
  if ($("writingAnswer")) $("writingAnswer").value = entry.answer || "";
  state.writing.dirty = false;
  resetWritingFrameAutosaveBaseline();
  state.writing.autosaveEnabled = writingAutosaveReady();
  state.writing.autosaveQueued = false;
  clearWritingAutosaveTimer();
  renderWritingSurface();
}

function startWritingScorePolling(entryId, options = {}) {
  if (!entryId) return;
  const notifyOnComplete = options.notifyOnComplete === true || options.switchOnComplete === true;
  if (state.writing.scorePollingEntryId && state.writing.scorePollingEntryId !== entryId && !notifyOnComplete) return;
  clearWritingScorePolling();
  state.writing.scorePollingEntryId = entryId;
  const poll = async () => {
    try {
      const entry = await api(`/api/writing/entries/${entryId}`);
      if (state.writing.scorePollingEntryId !== entryId) return;
      if (entry?.id) state.writing.reportDetailCache.set(entry.id, entry);
      renderVisibleWritingReport(entry);
      if (state.view === "writing" && state.writing.entry?.id === entry.id && !state.writing.dirty) {
        await recoverWritingEntry(entry);
      }
      await loadWritingSummary();
      const task = entry.ai_task || null;
      if (entry.score || (task && isAiTaskCompletedWithResultStatus(task.status))) {
        clearWritingScorePolling();
        setWritingPending(false);
        if (notifyOnComplete) showWritingScoreCompleteModal(entry, task);
        return;
      }
      if (task && isWritingTaskTerminal(task)) {
        clearWritingScorePolling();
        setWritingPending(false);
        text("writingSaveStatus", writingTaskStatusTitle(task));
        if (notifyOnComplete) showWritingScoreCompleteModal(entry, task);
        return;
      }
      setWritingPending(true, writingTaskStatusTitle(task), writingTaskStatusText(task));
      state.writing.scorePollTimer = setTimeout(poll, 2500);
    } catch (error) {
      clearWritingScorePolling();
      setWritingPending(false);
      showWritingError(error);
    }
  };
  poll();
}

function syncWritingScorePolling(entry, options = {}) {
  if (!entry?.id) return;
  const task = entry.ai_task || null;
  const notifyOnComplete = options.notifyOnComplete === true || options.switchOnComplete === true;
  if (entry.score || isWritingTaskTerminal(task)) {
    if (state.writing.scorePollingEntryId === entry.id) clearWritingScorePolling();
    if (entry.score) {
      state.writing.activeReportDetail = entry;
      renderVisibleWritingReport(entry);
    }
    if (notifyOnComplete) showWritingScoreCompleteModal(entry, task);
    return;
  }
  if (!isWritingTaskActive(task)) return;
  if (state.writing.scorePollingEntryId === entry.id && state.writing.scorePollTimer) return;
  startWritingScorePolling(entry.id, { notifyOnComplete });
}

async function scoreWritingEntry() {
  const currentAnswer = $("writingAnswer")?.value || "";
  if (!ensureWritingParagraphsBeforeScore(currentAnswer, state.writing.taskType || "task1_academic")) return;
  setWritingPending(true, "AI 正在评分与生成辅导", "正在分析题目、你的作文和 IELTS 写作评分标准。");
  try {
    let entry = state.writing.entry;
    if (!entry || state.writing.dirty) {
      entry = await saveWritingEntry(true);
      setWritingPending(true, "AI 正在评分与生成辅导", "作文已保存，正在继续生成写作反馈。");
    }
    try {
      const wallet = await fetchWalletPayload({ maxAgeMs: 30000 });
      if (!walletAiStartAllowed(wallet)) {
        showInsufficientBalanceDialog(walletAiStartThreshold(wallet));
        switchView("accountProfile");
        return;
      }
    } catch (_error) {
      // Backend scoring still handles billing/fallback; keep the writing flow usable.
    }
    try {
      const result = await withBusy("AI 评分任务已提交...", () => api(`/api/writing/entries/${entry.id}/score-task`, {}));
      const savedEntry = result.entry || entry;
      // Clear entry-level dedup so the completion/failure modal can show even if this
      // entry had a previous (failed) attempt whose notification was already displayed.
      const _savedEntryId = String(savedEntry.id || "").trim();
      if (_savedEntryId) state.writing.scoreCompletionNotifiedIds.delete(_savedEntryId);
      state.writing.entry = savedEntry;
      state.writing.dirty = false;
      renderWritingSurface();
      await loadWritingSummary();
      syncWritingScorePolling(savedEntry, { notifyOnComplete: true });
      return;
    } catch (error) {
      if (error?.payload?.paragraph_guidance) {
        showWritingParagraphModal(error.payload.paragraph_guidance);
        return;
      }
      if (!isScoreTaskUnsupported(error)) throw error;
    }
    const scored = await withBusy("AI 正在评分与生成辅导...", () => api(`/api/writing/entries/${entry.id}/score`, { answer: $("writingAnswer")?.value || "" }));
    state.writing.entry = scored;
    state.writing.dirty = false;
    renderWritingSurface();
    await loadWritingSummary();
    showWritingScoreCompleteModal(scored, scored.ai_task || null);
  } finally {
    if (!state.writing.scorePollingEntryId) setWritingPending(false);
  }
}

async function openWritingEntry(entryId) {
  if (!entryId) return;
  if (state.writing.dirty && !window.confirm("当前作文还没有保存，确定要打开历史记录吗？")) return;
  const entry = await withBusy("正在打开作文...", () => api(`/api/writing/entries/${entryId}`));
  await recoverWritingEntry(entry);
  syncWritingScorePolling(entry, { switchOnComplete: false });
  await loadWritingSummary();
}

async function editWritingReportEntry(entryId) {
  if (!entryId) return;
  if (state.writing.reportEditLoading) return;
  const cachedEntry = cachedWritingReportEntry(entryId);
  const requestId = state.writing.reportEditRequestId + 1;
  state.writing.reportEditRequestId = requestId;
  state.writing.reportEditLoading = true;
  const editBusyMessage = cachedEntry && isWritingEntryScored(cachedEntry) ? "正在复制为新版草稿..." : "正在打开作文...";
  text("writingSaveStatus", editBusyMessage);
  try {
    const source = cachedEntry && isWritingEntryScored(cachedEntry)
      ? cachedEntry
      : await withBusy("正在打开作文...", () => api(`/api/writing/entries/${encodeURIComponent(entryId)}`));
    if (state.writing.reportEditRequestId !== requestId) return;
    syncWritingReportEntryCache(source);
    state.writing.activeReportDetail = source;
    if (!isWritingEntryScored(source)) {
      state.writing.requestedEntryId = "";
      state.writing.requestedPromptId = "";
      state.writing.dirty = false;
      clearWritingAutosaveTimer();
      switchView("writing", { force: true });
      await recoverWritingEntry(source);
      syncWritingScorePolling(source, { switchOnComplete: false });
      syncUrlForCurrentState({ replace: true });
      text("writingSaveStatus", "已打开未评分作文，可继续编辑原稿。");
      $("writingAnswer")?.focus();
      return;
    }
    const clone = await withBusy("正在复制为新版草稿...", () => cloneWritingEntryForRevision(entryId));
    if (state.writing.reportEditRequestId !== requestId) return;
    state.writing.requestedEntryId = "";
    state.writing.requestedPromptId = "";
    state.writing.dirty = false;
    clearWritingAutosaveTimer();
    switchView("writing", { force: true });
    await recoverWritingEntry(clone);
    state.writing.reportDetailCache.set(clone.id, clone);
    state.writing.activeReportId = entryId;
    state.writing.activeReportDetail = cachedWritingReportEntry(entryId) || state.writing.activeReportDetail || null;
    syncUrlForCurrentState({ replace: true });
    text("writingSaveStatus", "已复制为新版草稿。旧报告会保留，重新评分后新版会排在旧报告左边。");
    $("writingAnswer")?.focus();
  } catch (error) {
    if (state.writing.reportEditRequestId === requestId) showWritingReportEditError(error);
  } finally {
    if (state.writing.reportEditRequestId === requestId) {
      state.writing.reportEditLoading = false;
    }
  }
}

async function editWritingReportEntryInNewTab(entryId, entryHint = null) {
  if (!entryId) return;
  let targetWindow = null;
  const newTabBusyMessage = entryHint && isWritingEntryScored(entryHint) ? "正在复制为新版草稿..." : "正在打开作文...";
  try {
    targetWindow = window.open("about:blank", "_blank");
    if (targetWindow) {
      targetWindow.opener = null;
      targetWindow.document.title = "正在准备作文";
      targetWindow.document.body.innerHTML = `<!doctype html>
        <html lang="zh-CN">
          <head>
            <meta charset="utf-8">
            <title>正在准备作文</title>
            <style>
              body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f7f7f8;color:#0d0d0d;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
              .card{display:flex;align-items:center;gap:12px;border:1px solid #ececf1;border-radius:12px;background:#fff;padding:16px 18px;box-shadow:0 14px 38px rgba(15,23,42,.08);font-size:15px;font-weight:700}
              .spinner{width:18px;height:18px;border:3px solid #dbe3ea;border-top-color:#10a37f;border-radius:50%;animation:spin .8s linear infinite}
              @keyframes spin{to{transform:rotate(360deg)}}
            </style>
          </head>
          <body><div class="card"><span class="spinner"></span><span>${escapeHtml(newTabBusyMessage)}</span></div></body>
        </html>`;
    }
  } catch (_error) {
    targetWindow = null;
  }
  try {
    const source = await withBusy(newTabBusyMessage, async () => {
      if (entryHint && isWritingEntryScored(entryHint)) return entryHint;
      return api(`/api/writing/entries/${encodeURIComponent(entryId)}`);
    });
    syncWritingReportEntryCache(source);
    if (!isWritingEntryScored(source)) {
      const url = writingEntryEditUrl(source);
      if (targetWindow && !targetWindow.closed) {
        targetWindow.location.replace(url);
        return;
      }
      const opened = window.open(url, "_blank", "noopener");
      if (!opened) {
        throw new Error("浏览器阻止了新窗口。请允许弹窗后重试，或普通点击按钮在当前页面编辑。");
      }
      return;
    }
    const clone = await withBusy("正在复制为新版草稿...", () => cloneWritingEntryForRevision(entryId));
    const url = writingEntryEditUrl(clone);
    if (targetWindow && !targetWindow.closed) {
      targetWindow.location.replace(url);
      return;
    }
    const opened = window.open(url, "_blank", "noopener");
    if (!opened) {
      throw new Error("浏览器阻止了新窗口。请允许弹窗后重试，或普通点击按钮在当前页面编辑。");
    }
  } catch (error) {
    if (targetWindow && !targetWindow.closed) targetWindow.close();
    showWritingReportEditError(error);
  }
}

function showWritingError(error) {
  const message = error instanceof Error ? error.message : String(error);
  text("writingSaveStatus", message);
}

function showWritingReportError(error) {
  const message = error instanceof Error ? error.message : String(error);
  const list = $("writingReportList");
  if (list) list.textContent = "写作报告加载失败。";
  $("writingReportDetail").innerHTML = `<div class="detail-card"><p class="error">${escapeHtml(message)}</p></div>`;
}

function renderDetail(attempt, updateView = true, options = {}) {
  if (updateView) switchView("history");
  const detailPanel = $("detailPanel");
  const preserveScroll = Boolean(options.preserveScroll);
  const previousScrollTop = detailPanel?.scrollTop || 0;
  state.activeHistoryId = attempt.id;
  syncUrlForCurrentState({ replace: Boolean(options.replaceUrl) });
  const score = attempt.ielts_score || {};
  const turns = attempt.turns || [];
  const visibleTurns = turns.filter(shouldRenderReportTurn);
  const isP2 = attempt.mode === "p2" || (turns[0]?.part === "p2");
  const isMock = attempt.mode === "mock" || attempt.part === "mock";
  const p2CueCard = isP2 && !isMock && attempt.cue_card
    ? `<div class="detail-card p2-cue-card">${cueDetail(attempt.cue_card)}</div>`
    : "";
  const overallReview = overallReviewSection(attempt.overall_review || attempt.personalized_coaching, attempt);
  const p3Skills = p3DiscussionSkillsSection(attempt.p3_discussion_skills);

  detailPanel.innerHTML = `
    <div class="detail-card speaking-score-summary-card">
      <div class="speaking-score-summary-head">
        <div class="speaking-score-summary-copy">
          <span class="section-label">IELTS Speaking 练习估分</span>
          <h2>${escapeHtml((attempt.mode || attempt.part || "").toUpperCase())} report</h2>
          <p class="muted">${escapeHtml(attempt.title || "")} · ${visibleTurns.length} question${visibleTurns.length === 1 ? "" : "s"}</p>
        </div>
        <div class="speaking-score-summary-band">
          <span>Overall</span>
          <strong>Band ${escapeHtml(score.overall_band ?? "—")}</strong>
        </div>
      </div>
      <p class="feedback">${renderMarkdown(attempt.feedback_summary || "")}</p>
      <div class="score-row compact speaking-score-summary-grid">
        ${scoreCell("FC", score.fluency_coherence, "流利连贯")}
        ${scoreCell("LR", score.lexical_resource, "词汇资源")}
        ${scoreCell("GRA", score.grammatical_range, "语法准确")}
      </div>
    </div>
    ${overallReview}
    ${p3Skills}
    ${p2CueCard}
    ${isMock ? mockTurnSections(attempt, turns) : turnTableSection(attempt, turns, isP2)}
  `;
  document.querySelectorAll("[data-regenerate-turn]").forEach((button) => {
    button.addEventListener("click", () => regenerateTurnFeedback(button));
  });
  document.querySelectorAll("[data-regenerate-transcript]").forEach((button) => {
    button.addEventListener("click", () => regenerateTurnTranscript(button));
  });
  document.querySelectorAll("[data-edit-turn-corpus]").forEach((button) => {
    button.addEventListener("click", () => openReportCorpusTarget({
      kind: button.dataset.corpusKind || "",
      questionId: button.dataset.questionId || "",
      topic: button.dataset.topic || "general",
      question: button.dataset.question || "",
      displayQuestion: button.dataset.displayQuestion || button.dataset.question || "",
      aiAnswer: button.dataset.aiAnswer || "",
      p2QuestionId: button.dataset.p2QuestionId || "",
      followupId: button.dataset.followupId || "",
      entryId: button.dataset.p2CorpusEntryId || "",
    }).catch(showError));
  });
  document.querySelectorAll("[data-start-p3-from-p2]").forEach((button) => {
    button.addEventListener("click", () => startP3FromP2Report(button.dataset.startP3FromP2 || "").catch(showError));
  });
  if (preserveScroll) {
    detailPanel.scrollTop = previousScrollTop;
  } else {
    detailPanel.scrollTo({ top: 0, behavior: "smooth" });
  }
}

async function regenerateTurnFeedback(button) {
  const attemptId = state.activeHistoryId;
  const turnId = button?.dataset?.regenerateTurn || "";
  if (!attemptId || !turnId) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "重新生成中...";
  try {
    const payload = await api(`/api/attempts/${encodeURIComponent(attemptId)}/turns/${encodeURIComponent(turnId)}/feedback/regenerate`, {});
    renderDetail(payload.attempt, false, { preserveScroll: true });
  } catch (error) {
    button.disabled = false;
    button.textContent = originalText || "一键重新生成";
    alert(error instanceof Error ? error.message : String(error));
  }
}

async function regenerateTurnTranscript(button) {
  const attemptId = state.activeHistoryId;
  const turnId = button?.dataset?.regenerateTranscript || "";
  if (!attemptId || !turnId) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "重新转写中...";
  try {
    const payload = await api(`/api/attempts/${encodeURIComponent(attemptId)}/turns/${encodeURIComponent(turnId)}/transcript/regenerate`, {});
    renderDetail(payload.attempt, false, { preserveScroll: true });
  } catch (error) {
    button.disabled = false;
    button.textContent = originalText || "重新转写录音";
    alert(friendlyTranscriptionError(error instanceof Error ? error.message : String(error)));
  }
}

function overallReviewSection(review = {}, attempt = null) {
  const markdown = review.markdown || "";
  const comment = review.comment || review.focus || "";
  const points = review.review_points || review.next_practice || [];
  if (!markdown && !comment && !points.length) return "";
  const isP2 = attempt && (attempt.mode === "p2" || attempt.part === "p2");
  const action = isP2
    ? `<button type="button" class="p2-report-p3-button" data-start-p3-from-p2="${escapeHtml(attempt.id || "")}">根据本次P2回答练习P3</button>`
    : "";
  const body = markdown ? renderMarkdown(markdown) : `
    ${comment ? `<h4>总体点评</h4><p>${escapeHtml(comment)}</p>` : ""}
    ${points.length ? `<h4>复盘重点</h4><ul>${points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>` : ""}
  `;
  return `
    <div class="detail-card overall-review-card">
      <div class="overall-review-head">
        <h3>Overall Review & Practice Focus</h3>
        ${action}
      </div>
      <div class="overall-review-content">${body}</div>
    </div>
  `;
}

async function startP3FromP2Report(attemptId) {
  const attempt = state.historyDetailCache.get(attemptId) || (state.activeHistoryId === attemptId ? null : null);
  const sourceAttempt = attempt || (state.activeHistoryId === attemptId ? state.historyDetailCache.get(state.activeHistoryId) : null);
  const detailAttempt = sourceAttempt || (attemptId ? await api(`/api/history/${encodeURIComponent(attemptId)}`) : null);
  if (!detailAttempt) return;
  if (detailAttempt.id) state.historyDetailCache.set(detailAttempt.id, detailAttempt);
  const p2Turn = (detailAttempt.turns || []).find((turn) => turn.part === "p2") || (detailAttempt.turns || [])[0] || {};
  const answer = String(
    p2Turn.display_transcript_markdown ||
    p2Turn.display_transcript ||
    p2Turn.transcript_markdown ||
    p2Turn.transcript_cleaned ||
    p2Turn.transcript_raw ||
    ""
  ).trim();
  const link = p2Turn.p2_corpus_link || {};
  let linkedEntry = link.entry_id ? findP2CorpusEntry(link.entry_id) : null;
  if (link.entry_id && !linkedEntry) {
    await ensureP2CorpusLoaded();
    linkedEntry = findP2CorpusEntry(link.entry_id);
  }
  const title = detailAttempt.cue_card?.title || detailAttempt.title || p2Turn.question || "Part 2 answer";
  switchView("p3", { force: true, keepP3Source: true });
  state.p3PracticeSource = {
    attemptId: detailAttempt.id || attemptId,
    sourceType: "p2_report",
    title,
    theme: title,
    answer,
    p2CorpusEntryId: link.entry_id || "",
    p3FollowUpText: linkedEntry?.p3_follow_up_text || link.p3_follow_up_text || "",
    band: detailAttempt.ielts_score?.overall_band ?? detailAttempt.overall_band ?? "",
    displayTime: detailAttempt.display_time || detailAttempt.timestamp || "",
  };
  state.p3SelectedTopic = title;
  state.p3SourceType = "p2_report";
  state.p3Focus = "comparison_concession";
  state.p3Intensity = "high";
  state.p3Plan = null;
  renderP3PlanPreview();
  syncP3LaunchPanel("正在根据这次 P2 生成训练计划...");
  window.requestAnimationFrame(() => generateP3Plan({ fromP2: true }));
}

function partScoreBlock(part, item = {}) {
  return `
    <div class="part-score-block">
      <div class="part-score-band">Band ${escapeHtml(item.band ?? "—")}</div>
      <div class="score-row mini">
        ${scoreCell("FC", item.fluency_coherence)}
        ${scoreCell("LR", item.lexical_resource)}
        ${scoreCell("GRA", item.grammatical_range)}
      </div>
    </div>
  `;
}

function p3DiscussionSkillsSection(skills) {
  if (!skills || !Array.isArray(skills.dimensions) || !skills.dimensions.length) return "";
  const statusLabel = {
    strong: "稳定",
    developing: "待加强",
    weak: "薄弱",
  };
  const bestMoment = skills.best_moment
    ? `<div class="p3-skill-highlight"><span>本次相对优势</span><strong>${escapeHtml(skills.best_moment)}</strong></div>`
    : "";
  const nextDrill = Array.isArray(skills.next_drill) && skills.next_drill.length
    ? `<div class="p3-next-drill">
        <span>下一轮训练动作</span>
        <ol>${skills.next_drill.slice(0, 3).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>
      </div>`
    : "";
  return `
    <section class="detail-card p3-skills-card">
      <div class="p3-skills-head">
        <div>
          <span class="section-label">${escapeHtml(skills.title || "P3 Discussion Skills")}</span>
          <h3>P3 讨论能力画像</h3>
          <p>${escapeHtml(skills.summary || "")}</p>
        </div>
        <div class="p3-fix-next">
          <span>下次优先改</span>
          <strong>${escapeHtml(skills.fix_next || "把观点展开成原因、例子和对比。")}</strong>
        </div>
      </div>
      <div class="p3-skill-brief-row">
        ${bestMoment}
        ${nextDrill}
      </div>
      <div class="p3-skills-grid">
        ${skills.dimensions.map((item) => `
          <article class="p3-skill-item ${escapeHtml(item.status || "developing")}">
            <div>
              <strong>${escapeHtml(item.label || "")}</strong>
              <span>${escapeHtml(statusLabel[item.status] || "待观察")}</span>
            </div>
            <p>${escapeHtml(item.evidence || "")}</p>
            <small>${escapeHtml(item.next_action || "")}</small>
          </article>
        `).join("")}
      </div>
    </section>
  `;
}

function p3TurnDiscussionMoves(turn) {
  if (turn?.part !== "p3") return "";
  const prompt = turn.prompt || {};
  const moves = Array.isArray(prompt.target_moves) ? prompt.target_moves : [];
  const typeLabel = p3QuestionTypeLabel(prompt.question_type || "");
  if (!moves.length && !typeLabel) return "";
  return `
    <div class="p3-turn-moves">
      <span>${escapeHtml(prompt.role === "follow_up" ? "追问承接" : typeLabel)}</span>
      ${moves.slice(0, 4).map((move) => `<em>${escapeHtml(p3MoveLabel(move))}</em>`).join("")}
    </div>
  `;
}

function turnTableSection(attempt, turns, isP2 = false) {
  const reportTurns = turns.filter(shouldRenderReportTurn);
  const tableClass = isP2 ? "turn-report-table p2-report-table" : "turn-report-table p1-p3-report-table";
  const headers = isP2
    ? "<th>我的原文</th><th>7 分回答</th>"
    : "<th>Question</th><th>Your recording</th><th>Band 7 spoken version</th>";
  const bodyHtml = reportTurns.map((turn) => turnReportGroup(attempt.id, turn, attempt, isP2)).join("");
  return `
    <div class="detail-card turn-report-card${isP2 ? " p2-report-card" : ""}">
      <div class="turn-report-wrap">
        <table class="${tableClass}">
          <thead><tr>${headers}</tr></thead>
          ${bodyHtml}
        </table>
      </div>
    </div>
  `;
}

function reportPromptRole(turn) {
  return turn?.prompt?.role || "";
}

function shouldRenderReportTurn(turn) {
  return !(turn?.part === "p1" && turn?.prompt?.flow === "intro" && reportPromptRole(turn) === "name");
}

function shouldRenderTurnCoaching(turn) {
  return !(turn?.part === "p1" && turn?.prompt?.flow === "intro" && reportPromptRole(turn) === "work_study");
}

function mockTurnSections(attempt, turns) {
  const partScores = attempt.part_scores || {};
  return ["p1", "p2", "p3"].map((part) => {
    const partTurns = turns.filter((turn) => turn.part === part).filter(shouldRenderReportTurn);
    if (!partTurns.length) return "";
    const scoreBlock = partScores[part] ? partScoreBlock(part, partScores[part]) : "";
    const cueCard = part === "p2" && attempt.cue_card ? `<div class="detail-cue-wrap">${cueDetail(attempt.cue_card)}</div>` : "";
    const isP2 = part === "p2";
    const tableClass = isP2 ? "turn-report-table" : "turn-report-table p1-p3-report-table";
    const headers = isP2
      ? "<th>Your recording</th><th>Band 7 spoken version</th>"
      : "<th>Question</th><th>Your recording</th><th>Band 7 spoken version</th>";
    return `
      <div class="detail-section">
        <h3>${escapeHtml(part.toUpperCase())}</h3>
        <div class="part-detail-box">
          ${scoreBlock}
          ${cueCard}
          <table class="${tableClass}">
            <thead><tr>${headers}</tr></thead>
            ${partTurns.map((turn) => turnReportGroup(attempt.id, turn, attempt, isP2)).join("")}
          </table>
        </div>
      </div>
    `;
  }).join("");
}

function cueDetail(cue) {
  const bullets = (cue.bullets || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `<article class="cue-detail"><h2>${escapeHtml(cue.title)}</h2><p>You should say:</p><ul>${bullets}</ul><p>${escapeHtml(cue.rounding || "")}</p></article>`;
}

function transcriptText(turn) {
  if (turn.display_transcript_markdown) return renderMarkdown(turn.display_transcript_markdown);
  if (turn.display_transcript) return renderMarkdown(turn.display_transcript);
  if (turn.transcript_markdown) return renderMarkdown(turn.transcript_markdown);
  if (turn.transcript_cleaned) return renderMarkdown(turn.transcript_cleaned);
  return missingTranscriptHtml(turn);
}

function formatReportTime(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(raw)) return raw;
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  const pad = (number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function missingTranscriptHtml(turn) {
  const hasAudio = !!((turn.audio || {}).url);
  if (!hasAudio) return '<p class="audio-warning">Recording missing. This turn has no playable audio.</p>';
  return `
    <div class="missing-transcript-notice">
      <strong>录音已保存，但没有拿到文字稿。</strong>
      <span>常见原因是开头静音后浏览器实时转写自动结束。新版录音会自动重连；这条旧录音可以尝试重新转写。</span>
      <button type="button" class="ghost regenerate-transcript-button" data-regenerate-transcript="${escapeHtml(turn.id)}">
        重新转写录音
      </button>
    </div>
  `;
}

function aiCoachingHtml(turn, attempt) {
  const coaching = turn.ai_coaching || attempt.ai_coaching || "";
  const status = String(turn.feedback_generation_status || "").toLowerCase();
  const fallback = isFallbackCoaching(turn, coaching);
  const fallbackNotice = fallback ? fallbackCoachingNotice(turn) : "";
  if (coaching) return `${fallbackNotice}<div class="coaching-content">${renderMarkdown(coaching)}</div>`;
  if (status === "pending") {
    return `
      <div class="fallback-coaching-notice">
        <div>
          <strong>AI 辅导生成中</strong>
          <small>这题的逐题分析还没有写入报告。可以稍后刷新，或点击重新生成。</small>
        </div>
        <button type="button" class="ghost regenerate-feedback-button" data-regenerate-turn="${escapeHtml(turn.id)}">
          一键重新生成
        </button>
      </div>
    `;
  }
  if (status === "failed") return fallbackCoachingNotice(turn);
  const notes = turn.upgrade_notes || attempt.upgrade_notes || [];
  if (!notes.length) return '<p class="muted">No AI coaching generated for this turn.</p>';
  return `${fallbackNotice}<ul>${notes.map((item) => `
    <li><strong>${escapeHtml(item.criterion || "Change")}:</strong> ${renderMarkdown(item.band7_change || item.original_problem || "")}</li>
  `).join("")}</ul>`;
}

function isFallbackCoaching(turn, coaching = "") {
  const backend = String(turn.feedback_generation_backend || "").toLowerCase();
  return backend === "fallback" || String(coaching || "").includes("AI 辅导生成失败");
}

function fallbackCoachingNotice(turn) {
  const error = turn.feedback_generation_error
    ? `<small>失败原因：${escapeHtml(friendlyFeedbackError(turn.feedback_generation_error))}</small>`
    : "<small>当前内容是规则兜底，不是本题 AI 重新分析结果。</small>";
  return `
    <div class="fallback-coaching-notice">
      <div>
        <strong>AI 辅导生成失败</strong>
        ${error}
      </div>
      <button type="button" class="ghost regenerate-feedback-button" data-regenerate-turn="${escapeHtml(turn.id)}">
        一键重新生成
      </button>
    </div>
  `;
}

function modelAnswerHtml(turn, band7Markdown) {
  if (band7Markdown) {
    return `<p class="model-answer-markdown" data-markdown-source="${escapeHtml(band7Markdown)}">${renderMarkdown(band7Markdown)}</p>`;
  }
  const status = String(turn.feedback_generation_status || "").toLowerCase();
  if (status === "pending") {
    return '<p class="muted">Band 7 spoken version 正在生成中。</p>';
  }
  if (status === "failed") {
    const error = turn.feedback_generation_error ? ` ${friendlyFeedbackError(turn.feedback_generation_error)}` : "";
    return `<p class="audio-warning">Band 7 spoken version 生成失败。${escapeHtml(error)}</p>`;
  }
  return '<p class="muted">Band 7 spoken version 尚未生成。</p>';
}

async function loadP1Corpus(...args) {
  return corpusTakeawayController.loadP1Corpus(...args);
}

function renderP1CorpusTopics(...args) {
  return corpusTakeawayController.renderP1CorpusTopics(...args);
}

function findP1CorpusEntry(...args) {
  return corpusTakeawayController.findP1CorpusEntry(...args);
}

function p1CorpusEntryIds(...args) {
  return corpusTakeawayController.p1CorpusEntryIds(...args);
}

function normalizeP1CorpusQuestionText(...args) {
  return corpusTakeawayController.normalizeP1CorpusQuestionText(...args);
}

function findP1CorpusEntryByExactQuestion(...args) {
  return corpusTakeawayController.findP1CorpusEntryByExactQuestion(...args);
}

function findExactP1CorpusEntryForTarget(...args) {
  return corpusTakeawayController.findExactP1CorpusEntryForTarget(...args);
}

function currentP1CorpusTarget(...args) {
  return corpusTakeawayController.currentP1CorpusTarget(...args);
}

async function ensureP1CorpusLoaded(...args) {
  return corpusTakeawayController.ensureP1CorpusLoaded(...args);
}

function updateP1CorpusPeekButton(...args) {
  return corpusTakeawayController.updateP1CorpusPeekButton(...args);
}

async function openP1CorpusPeek(...args) {
  return corpusTakeawayController.openP1CorpusPeek(...args);
}

function closeP1CorpusPeek(...args) {
  return corpusTakeawayController.closeP1CorpusPeek(...args);
}

function corpusPeekCard(...args) {
  return corpusTakeawayController.corpusPeekCard(...args);
}

function placeCorpusPeekWindow(...args) {
  return corpusTakeawayController.placeCorpusPeekWindow(...args);
}

function resetCorpusPeekWindowPosition(...args) {
  return corpusTakeawayController.resetCorpusPeekWindowPosition(...args);
}

function p2CorpusSourceText(entry) {
  if (!entry) return "";
  return String(entry.material_text || entry.linked_question || entry.title || "").trim();
}

function p3CorpusSourceOptions() {
  const options = [];
  for (const category of state.p2Corpus.categories || []) {
    for (const item of category.items || []) {
      options.push({
        ...item,
        label: category.label || item.label || item.category || "P2 素材",
      });
    }
  }
  return options;
}

function p2BankQuestionId(entry = {}) {
  return String(entry.cue_id || entry.question_id || entry.canonical_entry_id || entry.entry_id || "").trim();
}

function p2BankCardTitle(entry = {}) {
  return String(entry.cue_title || entry.title || entry.question || entry.linked_question || "P2 题卡").replace(/\s+/g, " ").trim();
}

function p2BankCardFollowUps(entry = {}) {
  const seen = new Set();
  return (entry.p3_follow_ups || [])
    .map((item) => String(item || "").replace(/\s+/g, " ").trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

function p3BankCardsWithFollowUps() {
  return (state.p2Corpus.currentPart2Cards || [])
    .filter((item) => p2BankQuestionId(item) && p2BankCardFollowUps(item).length);
}

function selectedP3BankCard() {
  const cards = p3BankCardsWithFollowUps();
  if (!cards.length) return null;
  const selectedId = String(state.p3SelectedBankCardId || "").trim();
  if (!selectedId) return null;
  return cards.find((item) => p2BankQuestionId(item) === selectedId) || null;
}

function setSelectedP3BankCard(entry) {
  if (!entry) {
    state.p3SelectedBankCardId = "";
    state.p3PracticeSource = null;
    state.p3SelectedTopic = "";
    return null;
  }
  const questionId = p2BankQuestionId(entry);
  const title = p2BankCardTitle(entry);
  const followUps = p2BankCardFollowUps(entry);
  state.p3SourceType = "bank";
  state.p3SelectedBankCardId = questionId;
  state.p3PracticeSource = {
    sourceType: "bank",
    title,
    theme: title,
    p2QuestionId: questionId,
    p3FollowUps: followUps,
    categoryLabel: entry.label || entry.category || "",
  };
  state.p3SelectedTopic = title;
  return state.p3PracticeSource;
}

async function ensureSelectedP3BankCard() {
  if (!state.p2Corpus.loaded) await ensureP2CorpusLoaded();
  const card = selectedP3BankCard();
  if (!card) {
    setSelectedP3BankCard(null);
    return null;
  }
  return setSelectedP3BankCard(card);
}

function p3BankCardPreviewHtml(entry) {
  const title = p2BankCardTitle(entry);
  const followUps = p2BankCardFollowUps(entry);
  const bullets = (entry.bullets || []).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `
    <article class="p3-bank-picker-card${p2BankQuestionId(entry) === state.p3SelectedBankCardId ? " active" : ""}" tabindex="0" role="button" data-p3-bank-card="${escapeHtml(p2BankQuestionId(entry))}">
      <div class="p3-bank-card-top">
        <span>${escapeHtml(entry.label || entry.category || "P2")}</span>
        <em>${escapeHtml(followUps.length)} 追问题</em>
      </div>
      <strong>${escapeHtml(title)}</strong>
      ${bullets ? `<ul>${bullets}</ul>` : ""}
    </article>
  `;
}

function p3SelectedBankCardHtml(entry) {
  const title = p2BankCardTitle(entry);
  const followUps = p2BankCardFollowUps(entry);
  const bullets = (entry.bullets || []).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `
    <article class="p3-bank-picker-card p3-bank-context-card active" tabindex="0" role="button" data-p3-bank-picker-open>
      <div class="p3-bank-card-top">
        <span>${escapeHtml(entry.label || entry.category || "P2")}</span>
        <em>${escapeHtml(followUps.length)} 追问题 · 点击切换题卡</em>
      </div>
      <strong>${escapeHtml(title)}</strong>
      ${bullets ? `<ul>${bullets}</ul>` : ""}
    </article>
  `;
}

async function renderP3BankPicker() {
  await ensureP2CorpusLoaded();
  const list = $("#p3BankPickerList");
  if (!list) return;
  const cards = p3BankCardsWithFollowUps();
  if (!cards.length) {
    list.innerHTML = `
      <div class="p3-context-note p3-context-warning">
        <strong>当前题库还没有固定 P3 追问</strong>
        <span>请先在 P2 题卡库维护题卡追问，或切换到 P2 报告/自定义主题让 AI 生成。</span>
      </div>
    `;
    return;
  }
  list.innerHTML = cards.map(p3BankCardPreviewHtml).join("");
}

async function openP3BankPicker() {
  await renderP3BankPicker();
  $("p3BankPickerModal")?.classList.remove("hidden");
}

function closeP3BankPicker() {
  $("p3BankPickerModal")?.classList.add("hidden");
}

function setP3SourceFromCorpusEntry(entry) {
  if (!entry) {
    state.p3PracticeSource = null;
    state.p3CorpusSourceEntryId = "";
    state.p3SelectedTopic = "";
    return;
  }
  state.p3CorpusSourceEntryId = entry.entry_id || "";
  state.p3PracticeSource = {
    sourceType: "p2_corpus",
    title: entry.title || "P2 素材",
    theme: entry.title || entry.label || "P2 素材",
    answer: p2CorpusSourceText(entry),
    p2CorpusEntryId: entry.entry_id || "",
    p3FollowUpText: entry.p3_follow_up_text || "",
    categoryLabel: entry.label || entry.category || "",
  };
  state.p3SelectedTopic = state.p3PracticeSource.theme;
}

function keepOpenCorpusPeekWindowsInBounds(...args) {
  return corpusTakeawayController.keepOpenCorpusPeekWindowsInBounds(...args);
}

function currentP2CorpusEntry(...args) {
  return corpusTakeawayController.currentP2CorpusEntry(...args);
}

async function ensureP2CorpusLoaded(...args) {
  return corpusTakeawayController.ensureP2CorpusLoaded(...args);
}

function updateP2CorpusPeekButton(...args) {
  return corpusTakeawayController.updateP2CorpusPeekButton(...args);
}

function p2CorpusPeekHtml(...args) {
  return corpusTakeawayController.p2CorpusPeekHtml(...args);
}

async function openP2CorpusPeek(...args) {
  return corpusTakeawayController.openP2CorpusPeek(...args);
}

function closeP2CorpusPeek(...args) {
  return corpusTakeawayController.closeP2CorpusPeek(...args);
}

function updateP3CorpusPeekButton(...args) {
  return corpusTakeawayController.updateP3CorpusPeekButton(...args);
}

function openP3CorpusPeek(...args) {
  return corpusTakeawayController.openP3CorpusPeek(...args);
}

function closeP3CorpusPeek(...args) {
  return corpusTakeawayController.closeP3CorpusPeek(...args);
}

function p1CorpusStorageEntry(...args) {
  return corpusTakeawayController.p1CorpusStorageEntry(...args);
}

function upsertP1CorpusEntry(...args) {
  return corpusTakeawayController.upsertP1CorpusEntry(...args);
}

function getCorpusMarkdownValue(textareaId) {
  return corpusMarkdownEditorController.getCorpusMarkdownValue(textareaId);
}

function isCorpusEditorReady(textareaId) {
  return corpusMarkdownEditorController.isCorpusEditorReady(textareaId);
}

function setCorpusEditorLoading(textareaId, isLoading) {
  return corpusMarkdownEditorController.setCorpusEditorLoading(textareaId, isLoading);
}

function setCorpusMarkdownValue(textareaId, value) {
  return corpusMarkdownEditorController.setCorpusMarkdownValue(textareaId, value);
}

function sendKeepaliveJson(...args) {
  return corpusTakeawayController.sendKeepaliveJson(...args);
}

function autosaveOpenCorpusEditors(...args) {
  return corpusTakeawayController.autosaveOpenCorpusEditors(...args);
}

function closeCorpusCardActionMenus(...args) {
  return corpusTakeawayController.closeCorpusCardActionMenus(...args);
}

function toggleCorpusCardActionMenu(...args) {
  return corpusTakeawayController.toggleCorpusCardActionMenu(...args);
}

async function openP1CorpusLibrary(...args) {
  return corpusTakeawayController.openP1CorpusLibrary(...args);
}

async function openP1CorpusEditor(...args) {
  return corpusTakeawayController.openP1CorpusEditor(...args);
}

function closeP1CorpusEditor(...args) {
  return corpusTakeawayController.closeP1CorpusEditor(...args);
}

async function saveAndCloseP1CorpusEditor(...args) {
  return corpusTakeawayController.saveAndCloseP1CorpusEditor(...args);
}

async function saveP1CorpusEntry(...args) {
  return corpusTakeawayController.saveP1CorpusEntry(...args);
}

async function loadP2Corpus(...args) {
  return corpusTakeawayController.loadP2Corpus(...args);
}

function renderP2CorpusTopics(...args) {
  return corpusTakeawayController.renderP2CorpusTopics(...args);
}

async function openP2BrainstormDialog(...args) {
  return corpusTakeawayController.openP2BrainstormDialog(...args);
}

async function loadCorpusHome(...args) {
  return corpusTakeawayController.loadCorpusHome(...args);
}

async function loadSpellingDrill(...args) {
  const result = await spellingDrillController.loadSpellingDrill(...args);
  updateSpellingDrillDueDot(state.spellingDrill?.stats || {});
  return result;
}

function renderSpellingDrill(...args) {
  return spellingDrillController.renderSpellingDrill(...args);
}

async function loadLanguageTakeaways(...args) {
  return corpusTakeawayController.loadLanguageTakeaways(...args);
}

function renderLanguageTakeaways(...args) {
  return corpusTakeawayController.renderLanguageTakeaways(...args);
}

function renderLanguageTakeawayToggle(...args) {
  return corpusTakeawayController.renderLanguageTakeawayToggle(...args);
}

function toggleLanguageTakeawayHiddenMode(...args) {
  return corpusTakeawayController.toggleLanguageTakeawayHiddenMode(...args);
}

function startTakeawayReview(...args) {
  return corpusTakeawayController.startTakeawayReview(...args);
}

function endTakeawayReview(...args) {
  return corpusTakeawayController.endTakeawayReview(...args);
}

function selectTakeawayReviewEntry(...args) {
  return corpusTakeawayController.selectTakeawayReviewEntry(...args);
}

function takeawayReviewFeedback(...args) {
  return corpusTakeawayController.takeawayReviewFeedback(...args);
}

function updateTakeawayReviewDots(...args) {
  return corpusTakeawayController.updateTakeawayReviewDots(...args);
}

function speakLanguageTakeaway(...args) {
  return corpusTakeawayController.speakLanguageTakeaway(...args);
}

function revealAndSpeakLanguageTakeaway(...args) {
  return corpusTakeawayController.revealAndSpeakLanguageTakeaway(...args);
}

async function deleteLanguageTakeawayEntry(...args) {
  return corpusTakeawayController.deleteLanguageTakeawayEntry(...args);
}

function languageTakeawayTranslationStatus(...args) {
  return corpusTakeawayController.languageTakeawayTranslationStatus(...args);
}

function setLanguageTakeawayStatus(...args) {
  return corpusTakeawayController.setLanguageTakeawayStatus(...args);
}

function writingAnswerSelectionText(...args) {
  return corpusTakeawayController.writingAnswerSelectionText(...args);
}

function textareaSelectionEndpointRect(...args) {
  return corpusTakeawayController.textareaSelectionEndpointRect(...args);
}

function selectionText(...args) {
  return corpusTakeawayController.selectionText(...args);
}

function hideLanguageTakeawayTrigger(...args) {
  return corpusTakeawayController.hideLanguageTakeawayTrigger(...args);
}

function hideLanguageTakeawayPopup(...args) {
  return corpusTakeawayController.hideLanguageTakeawayPopup(...args);
}

function placeLanguageTakeawayTrigger(...args) {
  return corpusTakeawayController.placeLanguageTakeawayTrigger(...args);
}

function showLanguageTakeawayTrigger(...args) {
  return corpusTakeawayController.showLanguageTakeawayTrigger(...args);
}

function trackLanguageTakeawayTriggerDuringScroll(...args) {
  return corpusTakeawayController.trackLanguageTakeawayTriggerDuringScroll(...args);
}

function scheduleLanguageTakeawayTriggerFromSelection(...args) {
  return corpusTakeawayController.scheduleLanguageTakeawayTriggerFromSelection(...args);
}

function placeLanguageTakeawayPopup(...args) {
  return corpusTakeawayController.placeLanguageTakeawayPopup(...args);
}

async function openLanguageTakeawayPopup(...args) {
  return corpusTakeawayController.openLanguageTakeawayPopup(...args);
}

async function translateLanguageTakeawaySource(...args) {
  return corpusTakeawayController.translateLanguageTakeawaySource(...args);
}

async function saveLanguageTakeaway(...args) {
  return corpusTakeawayController.saveLanguageTakeaway(...args);
}

async function saveWritingTakeaway(...args) {
  return corpusTakeawayController.saveWritingTakeaway(...args);
}

function openNewTakeawayEditor(...args) {
  return corpusTakeawayController.openNewTakeawayEditor(...args);
}

function openTakeawayEditor(...args) {
  return corpusTakeawayController.openTakeawayEditor(...args);
}

function closeTakeawayEditor(...args) {
  return corpusTakeawayController.closeTakeawayEditor(...args);
}

async function saveTakeawayEditor(...args) {
  return corpusTakeawayController.saveTakeawayEditor(...args);
}

function openExpressionReplacementDialog(...args) {
  return corpusTakeawayController.openExpressionReplacementDialog(...args);
}

function closeExpressionReplacementDialog(...args) {
  return corpusTakeawayController.closeExpressionReplacementDialog(...args);
}

function addExpressionReplacement(...args) {
  return corpusTakeawayController.addExpressionReplacement(...args);
}

function editExpressionReplacement(...args) {
  return corpusTakeawayController.editExpressionReplacement(...args);
}

function saveExpressionReplacementEdit(...args) {
  return corpusTakeawayController.saveExpressionReplacementEdit(...args);
}

function deleteExpressionReplacement(...args) {
  return corpusTakeawayController.deleteExpressionReplacement(...args);
}

function findP2CorpusEntry(...args) {
  return corpusTakeawayController.findP2CorpusEntry(...args);
}

async function openP2CorpusLibrary(...args) {
  return corpusTakeawayController.openP2CorpusLibrary(...args);
}

function openP2CorpusEditor(...args) {
  return corpusTakeawayController.openP2CorpusEditor(...args);
}

function closeP2CorpusEditor(...args) {
  return corpusTakeawayController.closeP2CorpusEditor(...args);
}

function openP2CorpusP3Editor(...args) {
  return corpusTakeawayController.openP2CorpusP3Editor(...args);
}

function closeP2CorpusP3Editor(...args) {
  return corpusTakeawayController.closeP2CorpusP3Editor(...args);
}

function openP2CorpusP3QuestionPicker(...args) {
  return corpusTakeawayController.openP2CorpusP3QuestionPicker(...args);
}

function closeP2CorpusP3QuestionPicker(...args) {
  return corpusTakeawayController.closeP2CorpusP3QuestionPicker(...args);
}

function insertSelectedP2CorpusP3Questions(...args) {
  return corpusTakeawayController.insertSelectedP2CorpusP3Questions(...args);
}

async function saveAndCloseP2CorpusEditor(...args) {
  return corpusTakeawayController.saveAndCloseP2CorpusEditor(...args);
}

async function saveAndCloseP2CorpusP3Editor(...args) {
  return corpusTakeawayController.saveAndCloseP2CorpusP3Editor(...args);
}

async function saveP2CorpusEntry(...args) {
  return corpusTakeawayController.saveP2CorpusEntry(...args);
}

async function deleteP2CorpusEntry(...args) {
  return corpusTakeawayController.deleteP2CorpusEntry(...args);
}

function friendlyFeedbackError(error) {
  const value = String(error || "").trim();
  const lowered = value.toLowerCase();
  if (!value) return "AI 暂时没有返回可用内容。";
  if (lowered.includes("question-aware band 7 answer")) {
    return "AI 生成的 7 分答案和本题不够贴合，系统已保留默认建议。可以点击重新生成。";
  }
  if (lowered.includes("concise markdown coaching")) {
    return "AI 返回的辅导格式不符合报告要求，系统已保留默认建议。可以点击重新生成。";
  }
  if (lowered.includes("codex disabled")) {
    return "服务器当前关闭了 Codex 生成功能。";
  }
  if (lowered.includes("codex cli not found")) {
    return "服务器没有找到 Codex CLI。";
  }
  if (lowered.includes("timed out") || lowered.includes("timeout")) {
    return "AI 生成超时，系统已保留默认建议。可以稍后重试。";
  }
  return "AI 暂时没有返回可用内容，系统已保留默认建议。可以点击重新生成。";
}

function friendlyTranscriptionError(error) {
  const value = String(error || "").trim();
  const lowered = value.toLowerCase();
  if (!value) return "重新转写失败：服务器没有返回具体原因。";
  if (lowered.includes("azure speech key/region is not configured") || lowered.includes("azure speech is not configured")) {
    return "重新转写失败：服务器还没有配置 Azure Speech。新录音会继续用浏览器实时转写；如果要补旧录音，需要先配置 AZURE_SPEECH_KEY 和 AZURE_SPEECH_REGION。";
  }
  if (lowered.includes("ffmpeg")) {
    return "重新转写失败：服务器需要 ffmpeg 把浏览器录音转换成 Azure 可识别的 WAV。";
  }
  if (lowered.includes("sdk is not installed")) {
    return "重新转写失败：服务器缺少 Azure Speech SDK。";
  }
  if (lowered.includes("did not detect any speech") || lowered.includes("no speech")) {
    return "重新转写失败：服务没有在这段录音里识别到清晰英文。可以重录一次，并在开始后尽快开口。";
  }
  return value.startsWith("重新转写失败") ? value : `重新转写失败：${value}`;
}

function p1CorpusTargetForTurn(turn, attempt) {
  if (turn?.part !== "p1") return null;
  const prompt = turn.prompt || {};
  let topicTarget = turn;
  if (prompt.role === "follow_up" && prompt.after_turn) {
    topicTarget = (attempt.turns || []).find((item) => item.id === prompt.after_turn) || turn;
  }
  const topicPrompt = topicTarget.prompt || {};
  return {
    questionId: turn.parent_question_id || topicTarget.question_id || topicPrompt.question_id || turn.question_id || prompt.question_id || "",
    topic: turn.parent_topic || topicTarget.topic || topicPrompt.topic || turn.topic || prompt.topic || "general",
    question: turn.parent_question || topicTarget.question || topicPrompt.question || turn.question || "",
    displayQuestion: turn.question || topicTarget.question || "",
  };
}

function p3CorpusTargetForTurn(turn) {
  if (turn?.part !== "p3") return null;
  const prompt = turn.prompt || {};
  const source = String(prompt.source || "").trim();
  const p2QuestionId = String(prompt.p2_question_id || prompt.cue_id || "").trim();
  const followupId = String(prompt.p3_bank_followup_id || prompt.followup_id || "").trim();
  const p2CorpusEntryId = String(prompt.p2_corpus_entry_id || "").trim();
  if ((source === "bank" || source === "season_bank") && p2QuestionId && followupId) {
    return {
      kind: "p3_bank",
      p2QuestionId,
      followupId,
      displayQuestion: turn.question || prompt.followup_question || "",
    };
  }
  if ((source === "p2_report" || source === "p2_corpus") && p2CorpusEntryId) {
    return {
      kind: "p2_corpus_p3",
      entryId: p2CorpusEntryId,
      displayQuestion: turn.question || "",
    };
  }
  return {
    kind: "p3_unlinked",
    displayQuestion: turn.question || "",
  };
}

function corpusTargetForTurn(turn, attempt) {
  const p1Target = p1CorpusTargetForTurn(turn, attempt);
  if (p1Target) return { kind: "p1", ...p1Target };
  return p3CorpusTargetForTurn(turn);
}

async function openReportCorpusTarget(target) {
  if (!target) return;
  if (target.kind === "p1") {
    await openP1CorpusEditor({
      question_id: target.questionId || "",
      topic: target.topic || "general",
      question: target.question || "",
      display_question: target.displayQuestion || target.question || "",
      corpus_text: "",
      last_ai_answer: target.aiAnswer || "",
    });
    return;
  }
  if (target.kind === "p3_bank") {
    await ensureP2CorpusLoaded();
    const card = (state.p2Corpus.currentPart2Cards || []).find((item) => p2BankQuestionId(item) === target.p2QuestionId);
    if (!card) throw new Error("没有找到这道题卡，先刷新题库后再编辑 P3 追问。");
    await openP2CorpusP3Editor({ ...card, selectedFollowupId: target.followupId });
    return;
  }
  if (target.kind === "p2_corpus_p3") {
    await ensureP2CorpusLoaded();
    const entry = findP2CorpusEntry(target.entryId);
    if (!entry) throw new Error("没有找到这条已链接的 P2 素材。");
    await openP2CorpusP3Editor(entry);
    return;
  }
  throw new Error("这次 P3 没有关联到可编辑语料。题库题卡可编辑固定追问；P2 报告模式需要先链接个人 P2 素材。");
}

function turnReportGroup(attemptId, turn, attempt, isP2 = false) {
  const groupClass = isP2 ? "turn-report-group p2-turn-group" : "turn-report-group p1-p3-turn-group";
  return `<tbody class="${groupClass}">${turnReportRow(attemptId, turn, attempt, isP2)}</tbody>`;
}

function turnReportRow(attemptId, turn, attempt, isP2 = false) {
  const modelAudio = turn.model_audio || {};
  const band7 = turn.band7_version || attempt.band7_version || "";
  const band7Markdown = turn.band7_markdown || attempt.band7_markdown || band7;
  const isFollowUp = turn.prompt?.role === "follow_up";
  const modelAudioControl = modelAudio.audio_url
    ? `<audio controls preload="none" src="${escapeHtml(modelAudio.audio_url)}"></audio>`
    : '<p class="audio-warning">Server model-answer audio unavailable.</p>';
  const corpusTarget = corpusTargetForTurn(turn, attempt);
  const corpusButton = corpusTarget
    ? `<button type="button" class="ghost corpus-edit-button"
        data-edit-turn-corpus="1"
        data-corpus-kind="${escapeHtml(corpusTarget.kind || "")}"
        data-question-id="${escapeHtml(corpusTarget.questionId || "")}"
        data-topic="${escapeHtml(corpusTarget.topic || "general")}"
        data-question="${escapeHtml(corpusTarget.question || "")}"
        data-display-question="${escapeHtml(corpusTarget.displayQuestion || corpusTarget.question || "")}"
        data-ai-answer="${escapeHtml(band7Markdown || band7 || "")}"
        data-p2-question-id="${escapeHtml(corpusTarget.p2QuestionId || "")}"
        data-followup-id="${escapeHtml(corpusTarget.followupId || "")}"
        data-p2-corpus-entry-id="${escapeHtml(corpusTarget.entryId || "")}">编辑语料库</button>`
    : "";
  const coachingRow = shouldRenderTurnCoaching(turn)
    ? `<tr class="p1-p3-coaching-row">
      <td colspan="3" class="ai-coaching-cell">
        <h4 class="coaching-title">AI 辅导</h4>
        ${aiCoachingHtml(turn, attempt)}
      </td>
    </tr>`
    : "";

  // P2 layout: two rows - first row for content, second row for AI coaching
  if (isP2) {
    return `
      <tr class="p2-content-row">
        <td>
          ${isFollowUp ? '<span class="follow-up-pill">Follow-up</span>' : ""}
          ${(turn.audio || {}).url
            ? `<audio controls preload="none" src="/api/audio/${escapeHtml(attemptId)}/${escapeHtml(turn.id)}/candidate"></audio>`
            : '<p class="audio-warning">Recording missing. This turn has no playable audio.</p>'}
          <p>${transcriptText(turn)}</p>
        </td>
        <td>
          ${modelAudioControl}
          ${modelAnswerHtml(turn, band7Markdown)}
        </td>
      </tr>
      <tr class="p2-coaching-row">
        <td colspan="2" class="ai-coaching-cell">
          <h4 class="coaching-title">AI 辅导</h4>
          ${aiCoachingHtml(turn, attempt)}
        </td>
      </tr>
    `;
  }

  // Non-P2 layout: two rows - content row + AI coaching row
  const questionCell = `<td><div class="question-header"><strong>${escapeHtml(turn.part.toUpperCase())} ${turn.index + 1}</strong>${isFollowUp ? '<span class="follow-up-pill">Follow-up</span>' : ""}</div><p>${escapeHtml(turn.question)}</p>${p3TurnDiscussionMoves(turn)}${corpusButton ? `<div class="question-cell-actions">${corpusButton}</div>` : ""}</td>`;
  return `
    <tr class="p1-p3-content-row">
      ${questionCell}
      <td>
        ${(turn.audio || {}).url
          ? `<audio controls preload="none" src="/api/audio/${escapeHtml(attemptId)}/${escapeHtml(turn.id)}/candidate"></audio>`
          : '<p class="audio-warning">Recording missing. This turn has no playable audio.</p>'}
        <p>${transcriptText(turn)}</p>
      </td>
      <td>
        ${modelAudioControl}
        ${modelAnswerHtml(turn, band7Markdown)}
      </td>
    </tr>
    ${coachingRow}
  `;
}

function stopAllRuntime(label = "Ready") {
  state.startRequestId += 1;
  state.practiceSessionId += 1;
  state.startAbortController?.abort();
  state.startAbortController = null;
  stopExaminerPlayback("runtime-stopped");
  stopSpeakingAudioPreprocessor("runtime-stopped");
  stopRealtimePcmUplink("runtime-stopped");
  clearTimer();
  clearAutoNextTimeout();
  stopDictation();
  setDictationStatus("", "");
  state.speaking.realtimePcmMetrics = null;
  setRealtimePcmStatus({});
  state.currentTurn = null;
  state.examinerPlayback = null;
  state.transcript = "";
  state.speaking.pendingTurnCompletions.clear();
  state.speaking.turnCompletionErrors.clear();
  state.speaking.examinerTtsRefreshPromises.clear();
  state.transcriptFinal = "";
  state.transcriptInterim = "";
  state.transcriptStatus = "missing";
  state.transcriptSource = "browser_dictation";
  state.practiceLocked = false;
  const summaryPanel = $("#summaryPanel");
  clearExaminerAudioPreloads();
  $("browserTtsFallback")?.classList.add("hidden");
  $("cueTop")?.classList.add("hidden");
  const p2PrepPanel = $("p2CorpusPrepPanel");
  p2PrepPanel?.classList.add("hidden");
  if (p2PrepPanel) p2PrepPanel.innerHTML = "";
  $("promptPane")?.classList.remove("cue");
  $("promptPane")?.classList.remove("hidden");
  $("practiceGrid")?.classList.remove("p2-mode", "practice-enter");
  summaryPanel?.classList.add("hidden");
  if (summaryPanel) summaryPanel.innerHTML = "";
  $("exitPractice")?.classList.add("hidden");
  text("promptKicker", "Prompt");
  setPromptHtml("Start a voice practice session to load a question.", "short");
  text("followUp", "");
  setRecordButton("ready", label, "Record the full section. No typing.");
  text("recordStatus", "Click Start. The examiner will load the questions automatically.");
  updateSidebarLock();
}

async function exitPractice() {
  const attemptId = state.attempt?.id;
  state.userExitedPractice = true;
  state.startRequestId += 1;
  state.practiceSessionId += 1;
  state.startAbortController?.abort();
  state.startAbortController = null;
  stopExaminerPlayback("exit-practice");
  let exitSessionId = state.practiceSessionId;
  if (state.status === "recording") {
    state.abortingAttemptId = attemptId || "__loading__";
    state.cancelRecording = true;
    stopRecording();
    stopAllRuntime("Ready");
    exitSessionId = state.practiceSessionId;
  } else {
    stopAllRuntime("Ready");
    state.abortingAttemptId = attemptId || "__loading__";
    exitSessionId = state.practiceSessionId;
  }
  state.practiceLocked = false;
  updateSidebarLock();
  if (attemptId) {
    await api(`/api/attempts/${attemptId}/abort`, {}).catch(() => null);
  }
  if (state.practiceSessionId !== exitSessionId) return;
  resetPracticeSurface();
}

function recoverActivePracticeAfterError(error) {
  if (state.userExitedPractice || state.abortingAttemptId) return true;
  const sessionId = state.practiceSessionId;
  if (!isActivePracticeSession(sessionId) || !state.currentTurn) return false;
  const message = error instanceof Error ? error.message : String(error || "");
  setBusy("");
  setDictationStatus("", "");
  $("summaryPanel")?.classList.add("hidden");
  traceExaminerAudio("practice:error-recover", {
    status: state.status,
    turnId: state.currentTurn.id || "",
    hasQuestion: hasUsableTurnQuestion(state.currentTurn),
    hasAudio: Boolean(state.currentTurn.examiner_tts?.audio_url),
    message,
  });
  if (isRecoverablePracticeErrorStatus(state.status)) {
    if (state.status === "processing" && state.speaking.retryCompletion) {
      setRecordButton("completion_failed", "重新保存", "本题保存失败，点击重新保存。");
      text("recordStatus", message ? `本题保存失败：${message}` : "本题保存失败，请重新保存。");
      return true;
    }
    text("recordStatus", message || "检测到临时问题，当前题会继续保留。");
    return true;
  }
  if (isWaitingForStreamedFollowUpText(state.currentTurn)) {
    setRecordButton("turn_saved", "Next", "正在等待追问生成。");
    text("recordStatus", "正在生成追问...");
    return true;
  }
  if (shouldStreamFollowUpTurn(state.currentTurn)) {
    setRecordButton("turn_saved", "Next", "正在准备追问。");
    text("recordStatus", message || "追问正在准备中，请稍等。");
    return true;
  }
  if (hasUsableTurnQuestion(state.currentTurn)) {
    if (state.currentTurn.examiner_tts?.audio_url) {
      setRecordButton("ready", "Continue", "继续当前题。");
      text("recordStatus", "检测到临时问题，可以继续当前题。");
    } else {
      beginPreparationWithoutExaminerAudio(sessionId, state.currentTurn, "error-recovery-no-audio");
    }
    return true;
  }
  setRecordButton("turn_saved", "Next", "正在等待下一题。");
  text("recordStatus", message || "准备下一题时遇到临时问题。");
  return true;
}

function showError(error) {
  if (state.userExitedPractice || state.abortingAttemptId) {
    setBusy("");
    return;
  }
  if (error?.status === 401) {
    state.account.authenticated = false;
    state.account.user = null;
    state.account.returnView = state.view;
    switchView("login", {
      force: true,
      skipAuthGate: true,
      authMessage: "登录状态已失效，请重新登录后继续。",
    });
    return;
  }
  const message = error instanceof Error ? error.message : String(error);
  if (recoverActivePracticeAfterError(error)) return;
  setBusy("");
  setRecordButton("ready", "Try Again", "上次尝试失败，准备好后重新开始。");
  text("recordStatus", "出现问题，请重试。");
  $("summaryPanel").classList.remove("hidden");
  $("summaryPanel").innerHTML = `<p class="error">${escapeHtml(message)}</p>`;
}

function accountProfileNames(user) {
  const profile = user?.profile || {};
  return {
    fullName: String(profile.full_name || DEFAULT_FULL_NAME),
    englishName: String(profile.english_name || user?.display_name || DEFAULT_ENGLISH_NAME),
  };
}

function formatCompactDateTime(value) {
  if (!value) return "未安排";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未安排";
  const pad = (num) => String(num).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function renderAccountStatus(message = "", isError = false) {
  const status = $("accountProfileStatus");
  const details = $("accountProfileDetails");
  const securityStatus = $("securityStatus");
  const fallback = state.account.authenticated
    ? `${t("account.currentUser")}${state.account.user?.username || ""}`
    : (state.account.backendAvailable ? t("account.guestLocal") : t("account.backendOffline"));

  if (status) {
    status.textContent = message || fallback;
    status.classList.toggle("error", Boolean(isError));
    status.classList.toggle("account-card-subtitle", true);
  }
  if (details) {
    if (state.account.authenticated) {
      const user = state.account.user || {};
      const phone = user.phone_number ? ` · ${user.phone_number}` : "";
      details.textContent = `${user.username || t("account.currentUser").replace(/[:：]\s*$/, "")}${phone}`;
    } else {
      details.textContent = t("account.detailsGuest");
    }
  }
  if (!message && securityStatus && !securityStatus.textContent.trim()) {
    securityStatus.textContent = state.account.authenticated ? t("account.securityStrong") : t("account.securityLogin");
    securityStatus.classList.remove("error");
  }
}

function questionBankScopeLabel(scope, fallback = "") {
  const key = `bank.${normalizeQuestionBankScope(scope)}`;
  return t(key, fallback || scope);
}

function formatSeasonLabel(value) {
  const textValue = String(value || "").trim();
  if (!textValue) return t("bank.currentSeason");
  const match = textValue.match(/^(\d{4})-([a-z]+)-([a-z]+)$/i);
  if (match) {
    if (currentUiLanguage() === "en") return textValue.replace(/-/g, " ");
    const monthMap = {
      january: "1月",
      february: "2月",
      march: "3月",
      april: "4月",
      may: "5月",
      june: "6月",
      july: "7月",
      august: "8月",
      september: "9月",
      october: "10月",
      november: "11月",
      december: "12月",
    };
    const start = monthMap[match[2].toLowerCase()] || match[2];
    const end = monthMap[match[3].toLowerCase()] || match[3];
    return `${match[1]} ${start}-${end}`;
  }
  return textValue.replace(/-/g, " ");
}

function renderQuestionBankSelector(summary = state.account.questionBankSummary) {
  const activeScope = normalizeQuestionBankScope(summary?.active_scope || state.account.questionBankScope);
  const options = Array.isArray(summary?.bank_scope_options) && summary.bank_scope_options.length
    ? summary.bank_scope_options
    : [
        { scope: "current", label: t("bank.current") },
        { scope: "new", label: t("bank.new") },
        { scope: "retained", label: t("bank.retained") },
        { scope: "archive", label: t("bank.archive") },
        { scope: "all", label: t("bank.all") },
      ];
  const seasonPill = $("accountBankSeasonPill");
  if (seasonPill) {
    seasonPill.textContent = formatSeasonLabel(summary?.active_season);
  }
  const status = $("accountBankStatus");
  if (status) {
    const label = questionBankScopeLabel(activeScope, summary?.active_scope_label || options.find((item) => item.scope === activeScope)?.label || t("bank.defaultLabel"));
    const part1 = Number(summary?.part1_count || 0);
    const part2 = Number(summary?.part2_count || 0);
    const p3 = Number(summary?.part3_follow_up_count || 0);
    const separator = currentUiLanguage() === "en" ? ": " : "：";
    status.textContent = summary
      ? `${label}${separator}${part1} P1 · ${part2} P2${p3 ? ` · ${p3} ${t("bank.followups")}` : ""}`
      : t("bank.loading");
    status.classList.remove("error");
  }
  const optionRoot = $("accountBankScopeOptions");
  if (optionRoot) {
    const optionByScope = new Map(options.map((item) => [normalizeQuestionBankScope(item.scope), item]));
    const optionButton = (scopeName, className = "") => {
      const scope = normalizeQuestionBankScope(scopeName);
      const item = optionByScope.get(scope) || { scope, label: questionBankScopeLabel(scope) };
      const countText = Number.isFinite(Number(item.part1_count)) || Number.isFinite(Number(item.part2_count))
        ? `<small>${Number(item.part1_count || 0)} P1 · ${Number(item.part2_count || 0)} P2</small>`
        : "";
      const classes = [className, scope === activeScope ? "is-active" : ""].filter(Boolean).join(" ");
      return `<button type="button" data-bank-scope="${escapeHtml(scope)}" class="${escapeHtml(classes)}" aria-pressed="${scope === activeScope ? "true" : "false"}">
        <span class="account-bank-option-label">${escapeHtml(questionBankScopeLabel(scope, item.label || scope))}</span>
        ${countText}
      </button>`;
    };
    const archiveItem = optionByScope.get("archive") || { scope: "archive", label: t("bank.archive") };
    const archiveCount = Number.isFinite(Number(archiveItem.part1_count)) || Number.isFinite(Number(archiveItem.part2_count))
      ? `${Number(archiveItem.part1_count || 0)} P1 · ${Number(archiveItem.part2_count || 0)} P2`
      : "";
    optionRoot.innerHTML = `
      <div class="account-bank-primary">
        ${optionButton("current", "account-bank-current")}
      </div>
      <div class="account-bank-current-scopes" aria-label="${escapeHtml(t("bank.currentGroup"))}">
        ${optionButton("new")}
        ${optionButton("retained")}
      </div>
      <div class="account-bank-secondary">
        <label class="account-bank-archive-control">
          <span>${escapeHtml(t("bank.archive"))}</span>
          <select id="accountBankArchiveSelect" data-bank-scope-select aria-label="${escapeHtml(t("bank.archiveSelect"))}">
            <option value="">${escapeHtml(t("bank.archiveSelect"))}</option>
            <option value="archive" ${activeScope === "archive" ? "selected" : ""}>
              ${escapeHtml(questionBankScopeLabel("archive", archiveItem.label || "archive"))}${archiveCount ? ` · ${escapeHtml(archiveCount)}` : ""}
            </option>
          </select>
        </label>
        ${optionButton("all", "account-bank-all")}
      </div>
    `;
  }
}

function renderNavigationBankStatus(summary = state.account.questionBankSummary) {
  if (!summary) return;
  const navScroll = captureNavScrollState();
  const season = formatSeasonLabel(summary.active_season);
  const scope = questionBankScopeLabel(summary.active_scope, summary.active_scope_label || t("bank.generic"));
  const p1 = Number(summary.part1_count || 0);
  const p2 = Number(summary.part2_count || 0);
  const p3 = Number(summary.part3_follow_up_count || 0);
  text("bankStatus", tf(p3 ? "bank.statusLine" : "bank.statusLineNoP3", { season, scope, p1, p2, p3 }));
  restoreNavScrollState(navScroll);
}

function renderQuestionBankSelectorError(error) {
  renderQuestionBankSelector(state.account.questionBankSummary);
  const status = $("accountBankStatus");
  if (status) {
    status.textContent = error?.message || t("bank.loadFailed");
    status.classList.add("error");
  }
}

function resetAccountProfileLoadingUi() {
  const status = $("accountProfileStatus");
  if (status) {
    status.textContent = t("account.profileLoading");
    status.classList.remove("error");
  }
  const walletStatus = $("walletStatus");
  if (walletStatus) {
    walletStatus.classList.remove("is-error");
    walletStatus.classList.add("is-loading");
    walletStatus.innerHTML = `
      <article class="wallet-balance-card">
        <div class="wallet-balance-main">
          <span class="wallet-balance-label">${escapeHtml(t("wallet.available"))}</span>
          <strong class="wallet-balance-amount">${escapeHtml(t("wallet.loading"))}</strong>
        </div>
        <span class="wallet-balance-status">${escapeHtml(t("wallet.reading"))}</span>
        <p class="wallet-balance-hint">${escapeHtml(t("wallet.hint"))}</p>
      </article>
    `;
  }
  const ledgerList = $("ledgerList");
  if (ledgerList) {
    ledgerList.innerHTML = '<div class="account-skeleton-row"></div><div class="account-skeleton-row"></div><div class="account-skeleton-row"></div>';
  }
  renderQuestionBankSelector(state.account.questionBankSummary);
}

async function loadAccount() {
  try {
    const payload = await api("/api/accounts/me/");
    state.account.backendAvailable = true;
    state.account.authenticated = Boolean(payload.authenticated);
    state.account.user = payload.user || null;
    if (state.account.authenticated) {
      applyCandidateNames(accountProfileNames(state.account.user));
    }
  } catch (error) {
    state.account.backendAvailable = error.status === 401;
    state.account.authenticated = false;
    state.account.user = null;
  }
}

async function submitLogin() {
  const username = ($("loginUsername")?.value || "").trim();
  const password = $("loginPassword")?.value || "";
  const statusEl = $("loginStatus");
  if (!username || !password) {
    if (statusEl) {
      statusEl.textContent = "Please enter username and password.";
      statusEl.classList.add("error");
    }
    return;
  }
  try {
    $("loginPanel").classList.add("is-loading");
    const loginLoading = $("loginLoading") || document.createElement("div");
    if (!loginLoading.id) {
      loginLoading.id = "loginLoading";
      loginLoading.className = "page-center-loading";
      loginLoading.innerHTML = `
        <div>
          <span class="spinner"></span>
          <strong>正在登录</strong>
          <span>请稍候，正在校验账号信息。</span>
        </div>
      `;
      $("loginPanel").appendChild(loginLoading);
    } else {
      loginLoading.classList.remove("hidden");
    }
    const result = await api("/api/accounts/login/", { username, password });
    state.account.backendAvailable = true;
    state.account.authenticated = true;
    state.account.user = result.user || null;
    resetCsrfToken();
    await ensureCsrfToken();
    applyCandidateNames(accountProfileNames(state.account.user), true);
    await Promise.all([loadWallet(), loadWritingSummary(false).catch(() => null)]);
    const returnView = state.account.returnView || "accountProfile";
    state.account.returnView = null;
    switchView(returnView, { force: true, skipAuthGate: true });
    scheduleAuthenticatedPrefetch();
  } catch (error) {
    state.account.backendAvailable = Boolean(error.status && error.status < 500);
    if (statusEl) {
      statusEl.textContent = accountErrorMessage(error, "登录失败");
      statusEl.classList.add("error");
    }
  } finally {
    $("loginPanel")?.classList.remove("is-loading");
    $("loginLoading")?.remove();
  }
}

async function submitRegister() {
  const username = ($("registerUsername")?.value || "").trim();
  const password = $("registerPassword")?.value || "";
  const passwordConfirm = $("registerPasswordConfirm")?.value || "";
  const statusEl = $("registerStatus");
  if (!username || !password) {
    if (statusEl) {
      statusEl.textContent = "Please enter username and password.";
      statusEl.classList.add("error");
    }
    return;
  }
  if (password !== passwordConfirm) {
    if (statusEl) {
      statusEl.textContent = "Passwords do not match.";
      statusEl.classList.add("error");
    }
    return;
  }
  const names = {
    fullName: ($("registerFullName")?.value || DEFAULT_FULL_NAME).trim() || DEFAULT_FULL_NAME,
    englishName: ($("registerEnglishName")?.value || DEFAULT_ENGLISH_NAME).trim() || DEFAULT_ENGLISH_NAME,
  };
  try {
    const result = await withBusy("正在创建账号...", () => api("/api/accounts/register/", {
      username,
      password,
      password_confirm: passwordConfirm,
      full_name: names.fullName,
      english_name: names.englishName,
      display_name: names.englishName,
    }));
    state.account.backendAvailable = true;
    state.account.authenticated = true;
    state.account.user = result.user || null;
    resetCsrfToken();
    await ensureCsrfToken();
    applyCandidateNames(accountProfileNames(state.account.user), true);
    await Promise.all([loadWallet(), loadWritingSummary(false).catch(() => null)]);
    const returnView = state.account.returnView || "accountProfile";
    state.account.returnView = null;
    switchView(returnView, { force: true, skipAuthGate: true });
    scheduleAuthenticatedPrefetch();
  } catch (error) {
    state.account.backendAvailable = Boolean(error.status && error.status < 500);
    if (statusEl) {
      const errors = error.errors || {};
      const fieldErrors = Object.entries(errors).map(([field, messages]) => `${field}: ${messages.join(", ")}`).join("; ");
      statusEl.textContent = fieldErrors || error.message || "Registration failed";
      statusEl.classList.add("error");
    }
  }
}

async function submitPasswordChange() {
  const currentPassword = $("securityCurrentPassword")?.value || "";
  const newPassword = $("securityNewPassword")?.value || "";
  const newPasswordConfirm = $("securityNewPasswordConfirm")?.value || "";
  const statusEl = $("securityStatus");
  if (!currentPassword || !newPassword) {
    if (statusEl) {
      statusEl.textContent = "Please enter current and new password.";
      statusEl.classList.add("error");
    }
    return;
  }
  if (newPassword !== newPasswordConfirm) {
    if (statusEl) {
      statusEl.textContent = "New passwords do not match.";
      statusEl.classList.add("error");
    }
    return;
  }
  try {
    await withBusy("正在修改密码...", () => api("/api/accounts/password/change/", {
      current_password: currentPassword,
      new_password: newPassword,
      new_password_confirm: newPasswordConfirm,
    }));
    if (statusEl) {
      statusEl.textContent = "Password changed successfully.";
      statusEl.classList.remove("error");
    }
    $("securityCurrentPassword").value = "";
    $("securityNewPassword").value = "";
    $("securityNewPasswordConfirm").value = "";
  } catch (error) {
    if (statusEl) {
      const errors = error.errors || {};
      const fieldErrors = Object.entries(errors).map(([field, messages]) => `${field}: ${messages.join(", ")}`).join("; ");
      statusEl.textContent = fieldErrors || error.message || "Password change failed";
      statusEl.classList.add("error");
    }
  }
}

async function logoutAccount() {
  try {
    await withBusy("正在退出登录...", () => api("/api/accounts/logout/", {}));
  } catch (_error) {
    // Keep UI usable even if backend session expired
  }
  state.account.authenticated = false;
  state.account.user = null;
  state.account.returnView = null;
  state.account.fromView = null;
  state.wallet.payload = null;
  state.wallet.loaded = false;
  state.wallet.loadingPromise = null;
  state.wallet.fetchedAt = 0;
  state.viewHistory = [];
  clearUserScopedCaches();
  resetCsrfToken();
  loadCandidateNames();
  switchView("login", { force: true, skipAuthGate: true, authMessage: "你已退出登录。" });
}

async function loadPasswordResetAvailability() {
  const status = $("forgotPasswordStatus");
  if (!status) return;
  status.textContent = "Checking password reset availability...";
  status.classList.remove("error");
  try {
    const payload = await api("/api/accounts/password/reset/availability/");
    status.textContent = payload.available
      ? "Password reset email is configured for this deployment."
      : (payload.message || "Password reset email is not configured on this deployment.");
    status.classList.toggle("error", !payload.available);
  } catch (error) {
    status.textContent = error.message || "Could not check password reset availability.";
    status.classList.add("error");
  }
}

function bindEvents() {
  const bindCorpusOverlayClose = (dialogId, closeEditor) => {
    const dialog = $(dialogId);
    if (!dialog) return;
    dialog.addEventListener("pointerdown", (event) => {
      if (event.target === dialog) {
        event.preventDefault();
        closeEditor();
      }
    });
  };
  const bindCorpusPeekDrag = (dialogId) => {
    const dialog = $(dialogId);
    const card = corpusPeekCard(dialogId);
    const handle = dialog?.querySelector(".p1-corpus-dialog-head");
    if (!dialog || !card || !handle) return;
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || event.target.closest("button, a, input, textarea, select")) return;
      const rect = card.getBoundingClientRect();
      corpusPeekDrag.dialogId = dialogId;
      corpusPeekDrag.dragging = true;
      corpusPeekDrag.dragOffsetX = event.clientX - rect.left;
      corpusPeekDrag.dragOffsetY = event.clientY - rect.top;
      card.classList.add("is-dragging");
      placeCorpusPeekWindow(dialogId, rect.left, rect.top);
      card.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });
    card.addEventListener("pointermove", (event) => {
      if (!corpusPeekDrag.dragging || corpusPeekDrag.dialogId !== dialogId) return;
      placeCorpusPeekWindow(
        dialogId,
        event.clientX - corpusPeekDrag.dragOffsetX,
        event.clientY - corpusPeekDrag.dragOffsetY
      );
    });
    const stopDrag = () => {
      if (corpusPeekDrag.dialogId === dialogId) {
        corpusPeekDrag.dialogId = "";
        corpusPeekDrag.dragging = false;
      }
      card.classList.remove("is-dragging");
    };
    card.addEventListener("pointerup", stopDrag);
    card.addEventListener("pointercancel", stopDrag);
    card.addEventListener("lostpointercapture", stopDrag);
  };
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.addEventListener("click", (event) => {
      const targetView = button.dataset.view || "home";
      if (isNewTabNavigationEvent(event)) return;
      event.preventDefault();
      if (state.practiceLocked && targetView === state.practiceViewBeforeSettings) {
        returnFromSettings();
        return;
      }
      if (targetView === state.view) {
        return;
      }
      if (state.practiceLocked && targetView !== state.view) {
        if (corpusViews.has(targetView)) {
          exitPracticeAndSwitch(targetView).catch(showError);
          return;
        }
        showNavLockHint(button);
        return;
      }
      switchView(targetView);
    });
  });
  const handleAccountNavigation = (event) => {
    const targetView = state.account.authenticated ? "accountProfile" : "login";
    if (openViewInNewTabForModifier(event, targetView)) return;
    if (event.type === "auxclick") return;
    event.preventDefault();
    if (state.account.authenticated) {
      switchView("accountProfile", { preservePractice: true, fromView: state.view });
    } else {
      switchView("login", { fromView: state.view });
    }
  };
  document.querySelectorAll(".avatar-settings-button").forEach((button) => {
    button.addEventListener("click", handleAccountNavigation);
    button.addEventListener("auxclick", handleAccountNavigation);
  });
  $("accountBackBtn")?.addEventListener("click", returnToPreviousView);
  $("fullNameInput")?.addEventListener("input", scheduleCandidateNameSave);
  $("englishNameInput")?.addEventListener("input", scheduleCandidateNameSave);
  $("fullNameInput")?.addEventListener("blur", flushCandidateNameSave);
  $("englishNameInput")?.addEventListener("blur", flushCandidateNameSave);
  $("darkModeToggle")?.addEventListener("change", (event) => applyDarkMode(event.target.checked));
  document.querySelectorAll("[data-ui-language-option]").forEach((button) => {
    button.addEventListener("click", () => applyUiLanguage(button.dataset.uiLanguageOption));
  });
  $("accountBankScopeOptions")?.addEventListener("click", (event) => {
    const button = event.target?.closest?.("[data-bank-scope]");
    if (!button) return;
    selectQuestionBankScope(button.dataset.bankScope).catch(renderQuestionBankSelectorError);
  });
  $("accountBankScopeOptions")?.addEventListener("change", (event) => {
    const select = event.target?.closest?.("[data-bank-scope-select]");
    if (!select || !select.value) return;
    selectQuestionBankScope(select.value).catch(renderQuestionBankSelectorError);
  });
  $("loginSubmitBtn")?.addEventListener("click", submitLogin);
  $("registerSubmitBtn")?.addEventListener("click", submitRegister);
  $("loginBackBtn")?.addEventListener("click", returnToPreviousView);
  $("loginToRegisterLink")?.addEventListener("click", () => switchView("register"));
  $("loginForgotLink")?.addEventListener("click", () => switchView("forgotPassword"));
  $("registerToLoginLink")?.addEventListener("click", () => switchView("login"));
  $("forgotBackToLoginBtn")?.addEventListener("click", () => switchView("login"));
  $("authRequiredLoginBtn")?.addEventListener("click", () => switchView("login", { force: true, skipAuthGate: true }));
  $("authRequiredBackBtn")?.addEventListener("click", () => switchView("mock"));
  $("profileLogoutBtn")?.addEventListener("click", logoutAccount);
  $("profileSecurityBtn")?.addEventListener("click", () => {
    $("accountSecurityPanel")?.classList.remove("hidden");
    loadAccount();
  });
  $("securityCloseBtn")?.addEventListener("click", () => {
    $("accountSecurityPanel")?.classList.add("hidden");
  });
  $("accountSecurityPanel")?.addEventListener("click", (event) => {
    if (event.target?.id === "accountSecurityPanel") {
      $("accountSecurityPanel")?.classList.add("hidden");
    }
  });
  $("securityChangePasswordBtn")?.addEventListener("click", submitPasswordChange);
  $("securityLogoutBtn")?.addEventListener("click", logoutAccount);
  $("peekP1CorpusBtn")?.addEventListener("click", openP1CorpusPeek);
  $("peekP2CorpusBtn")?.addEventListener("click", openP2CorpusPeek);
  $("peekP3CorpusBtn")?.addEventListener("click", () => openP3CorpusPeek().catch(showError));
  $("closeP1CorpusPeekBtn")?.addEventListener("click", closeP1CorpusPeek);
  $("closeP2CorpusPeek")?.addEventListener("click", closeP2CorpusPeek);
  $("closeP3CorpusPeek")?.addEventListener("click", closeP3CorpusPeek);
  $("p2CorpusPeekDialog")?.addEventListener("click", (event) => {
    if (event.target?.id === "p2CorpusPeekDialog") closeP2CorpusPeek();
  });
  $("p3CorpusPeekDialog")?.addEventListener("click", (event) => {
    if (event.target?.id === "p3CorpusPeekDialog") closeP3CorpusPeek();
  });
  $("p3BankPickerModal")?.addEventListener("click", (event) => {
    if (event.target?.closest?.("[data-p3-bank-picker-close]")) {
      closeP3BankPicker();
      return;
    }
    const cardButton = event.target?.closest?.("[data-p3-bank-card]");
    if (!cardButton) return;
    const card = p3BankCardsWithFollowUps().find((item) => p2BankQuestionId(item) === cardButton.dataset.p3BankCard);
    if (!card) return;
    setSelectedP3BankCard(card);
    closeP3BankPicker();
    generateP3Plan().catch(showError);
  });
  bindCorpusPeekDrag("p2CorpusPeekDialog");
  bindCorpusPeekDrag("p3CorpusPeekDialog");
  window.addEventListener("resize", keepOpenCorpusPeekWindowsInBounds);
  $("openP1CorpusBtn")?.addEventListener("click", openP1CorpusLibrary);
  $("openP2CorpusBtn")?.addEventListener("click", openP2CorpusLibrary);
  $("topbarBackCorpusBtn")?.addEventListener("click", closeCorpusWindowOrReturn);
  bindCorpusOverlayClose("p1CorpusDialog", saveAndCloseP1CorpusEditor);
  bindCorpusOverlayClose("p2CorpusDialog", saveAndCloseP2CorpusEditor);
  bindCorpusOverlayClose("p2CorpusP3Dialog", saveAndCloseP2CorpusP3Editor);
  $("takeawayEditDialog")?.addEventListener("pointerdown", (event) => {
    if (event.target === $("takeawayEditDialog")) {
      event.preventDefault();
      closeTakeawayEditor({ saveDirty: true }).catch(showError);
    }
  });
  $("saveTakeawayEditBtn")?.addEventListener("click", saveTakeawayEditor);
  $("cancelTakeawayEditBtn")?.addEventListener("click", closeTakeawayEditor);
  $("p1CorpusTopics")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-p1-corpus-question]");
    if (!button) return;
    openP1CorpusEditor(findP1CorpusEntry(button.dataset.p1CorpusQuestion || ""));
  });
  $("p2CorpusTopics")?.addEventListener("click", (event) => {
    const menuButton = event.target.closest("[data-p2-corpus-menu]");
    if (menuButton) {
      event.preventDefault();
      event.stopPropagation();
      toggleCorpusCardActionMenu(menuButton);
      return;
    }
    const editButton = event.target.closest("[data-p2-corpus-edit]");
    if (editButton) {
      event.preventDefault();
      event.stopPropagation();
      closeCorpusCardActionMenus();
      openP2CorpusEditor(findP2CorpusEntry(editButton.dataset.p2CorpusEdit || ""));
      return;
    }
    const deleteButton = event.target.closest("[data-p2-corpus-delete]");
    if (deleteButton) {
      event.preventDefault();
      event.stopPropagation();
      closeCorpusCardActionMenus();
      deleteP2CorpusEntry(deleteButton.dataset.p2CorpusDelete || "");
      return;
    }
    const p3Button = event.target.closest("[data-p2-corpus-p3]");
    if (p3Button) {
      event.preventDefault();
      event.stopPropagation();
      openP2CorpusP3Editor(findP2CorpusEntry(p3Button.dataset.p2CorpusP3 || ""));
      return;
    }
    const existing = event.target.closest("[data-p2-corpus-entry]");
    if (existing) {
      openP2CorpusEditor(findP2CorpusEntry(existing.dataset.p2CorpusEntry || ""));
      return;
    }
    const created = event.target.closest("[data-p2-corpus-new]");
    if (created) openP2CorpusEditor({ category: created.dataset.p2CorpusNew || "person" });
  });
  document.querySelectorAll("[data-corpus-home-target]").forEach((button) => {
    button.addEventListener("click", (event) => {
      if (isNewTabNavigationEvent(event)) return;
      event.preventDefault();
      switchView(button.dataset.corpusHomeTarget || "corpus");
    });
  });
  spellingDrillController.bindSpellingDrillEvents();
  $("languageTakeawayHideToggle")?.addEventListener("click", toggleLanguageTakeawayHiddenMode);
  $("writingTakeawayHideToggle")?.addEventListener("click", toggleWritingTakeawayHiddenMode);
  $("addLanguageTakeawayBtn")?.addEventListener("click", () => openNewTakeawayEditor("language"));
  $("addWritingTakeawayBtn")?.addEventListener("click", () => openNewTakeawayEditor("writing"));
  $("languageReplacementBtn")?.addEventListener("click", () => openExpressionReplacementDialog("language"));
  $("writingReplacementBtn")?.addEventListener("click", () => openExpressionReplacementDialog("writing"));
  $("closeExpressionReplacementBtn")?.addEventListener("click", closeExpressionReplacementDialog);
  $("addExpressionReplacementBtn")?.addEventListener("click", addExpressionReplacement);
  $("expressionReplacementDialog")?.addEventListener("click", (event) => {
    if (event.target.id === "expressionReplacementDialog") {
      closeExpressionReplacementDialog();
      return;
    }
    const editButton = event.target.closest("[data-expression-replacement-edit]");
    if (editButton) {
      editExpressionReplacement(editButton.dataset.expressionReplacementEdit || "");
      return;
    }
    const saveButton = event.target.closest("[data-expression-replacement-save]");
    if (saveButton) {
      saveExpressionReplacementEdit(saveButton.dataset.expressionReplacementSave || "");
      return;
    }
    const cancelButton = event.target.closest("[data-expression-replacement-cancel]");
    if (cancelButton) {
      const kind = $("expressionReplacementDialog")?.dataset.kind || "writing";
      openExpressionReplacementDialog(kind);
      return;
    }
    const deleteButton = event.target.closest("[data-expression-replacement-delete]");
    if (deleteButton) {
      deleteExpressionReplacement(deleteButton.dataset.expressionReplacementDelete || "");
    }
  });
  $("languageTakeawayList")?.addEventListener("click", (event) => {
    const menuButton = event.target.closest("[data-takeaway-menu]");
    if (menuButton) {
      event.preventDefault();
      event.stopPropagation();
      toggleCorpusCardActionMenu(menuButton);
      return;
    }
    const editButton = event.target.closest("[data-takeaway-edit]");
    if (editButton) {
      event.preventDefault();
      event.stopPropagation();
      closeCorpusCardActionMenus();
      openTakeawayEditor("language", editButton.dataset.takeawayEdit || "");
      return;
    }
    const deleteButton = event.target.closest("[data-takeaway-delete]");
    if (deleteButton) {
      event.preventDefault();
      event.stopPropagation();
      closeCorpusCardActionMenus();
      deleteLanguageTakeawayEntry(deleteButton.dataset.takeawayDelete || "");
      return;
    }
    const card = event.target.closest("[data-takeaway-entry]");
    if (!card) return;
    if (selectTakeawayReviewEntry("language", card.dataset.takeawayEntry || "")) return;
    revealAndSpeakLanguageTakeaway(card.dataset.takeawayEntry || "");
  });
  $("writingTakeawayList")?.addEventListener("click", (event) => {
    const menuButton = event.target.closest("[data-writing-takeaway-menu]");
    if (menuButton) {
      event.preventDefault();
      event.stopPropagation();
      toggleCorpusCardActionMenu(menuButton);
      return;
    }
    const editButton = event.target.closest("[data-writing-takeaway-edit]");
    if (editButton) {
      event.preventDefault();
      event.stopPropagation();
      closeCorpusCardActionMenus();
      openTakeawayEditor("writing", editButton.dataset.writingTakeawayEdit || "");
      return;
    }
    const deleteButton = event.target.closest("[data-writing-takeaway-delete]");
    if (deleteButton) {
      event.preventDefault();
      event.stopPropagation();
      closeCorpusCardActionMenus();
      deleteWritingTakeawayEntry(deleteButton.dataset.writingTakeawayDelete || "");
      return;
    }
    const card = event.target.closest("[data-writing-takeaway-entry]");
    if (!card) return;
    if (selectTakeawayReviewEntry("writing", card.dataset.writingTakeawayEntry || "")) return;
    revealAndSpeakWritingTakeaway(card.dataset.writingTakeawayEntry || "");
  });
  document.addEventListener("selectionchange", () => {
    window.clearTimeout(state.languageTakeaway.selectionTimer);
    if (!selectionText()) hideLanguageTakeawayTrigger();
  });
  document.addEventListener("scroll", trackLanguageTakeawayTriggerDuringScroll, { capture: true, passive: true });
  document.addEventListener("pointerdown", (event) => {
    if (event.target.closest("[data-corpus-card-menu]") || event.target.closest("[data-corpus-card-action-menu]")) return;
    closeCorpusCardActionMenus();
  });
  document.addEventListener("click", (event) => {
    const gradeButton = event.target.closest("[data-takeaway-review-panel-grade]");
    if (gradeButton) {
      event.preventDefault();
      event.stopPropagation();
      takeawayReviewFeedback(
        gradeButton.dataset.takeawayReviewKind || (state.view === "writingTakeawayBook" ? "writing" : "language"),
        "",
        gradeButton.dataset.takeawayReviewPanelGrade === "again" ? "again" : "mastered",
      );
      return;
    }
    const startButton = event.target.closest("[data-takeaway-review-start]");
    if (startButton) {
      event.preventDefault();
      event.stopPropagation();
      startTakeawayReview(startButton.dataset.takeawayReviewStart || (state.view === "writingTakeawayBook" ? "writing" : "language"));
      return;
    }
    const exitButton = event.target.closest("[data-takeaway-review-exit]");
    if (exitButton) {
      event.preventDefault();
      event.stopPropagation();
      endTakeawayReview(exitButton.dataset.takeawayReviewExit || (state.view === "writingTakeawayBook" ? "writing" : "language"));
    }
  });
  document.addEventListener("pointerdown", (event) => {
    const popup = $("languageTakeawayPopup");
    const trigger = $("languageTakeawayTrigger");
    if (popup?.contains(event.target) || trigger?.contains(event.target)) return;
    hideLanguageTakeawayTrigger();
  });
  document.addEventListener("pointerup", scheduleLanguageTakeawayTriggerFromSelection);
  document.addEventListener("keyup", (event) => {
    if (["Shift", "Meta", "Control", "Alt"].includes(event.key)) scheduleLanguageTakeawayTriggerFromSelection();
  });
  $("writingAnswer")?.addEventListener("mouseup", () => scheduleLanguageTakeawayTriggerFromSelection());
  $("writingAnswer")?.addEventListener("keyup", () => scheduleLanguageTakeawayTriggerFromSelection());
  $("writingAnswer")?.addEventListener("select", () => scheduleLanguageTakeawayTriggerFromSelection());
  $("writingAnswer")?.addEventListener("scroll", trackLanguageTakeawayTriggerDuringScroll, { passive: true });
  $("languageTakeawayTrigger")?.addEventListener("click", (event) => {
    event.preventDefault();
    openLanguageTakeawayPopup();
  });
  $("writingTakeawaySaveBtn")?.addEventListener("click", saveWritingTakeaway);
  $("languageTakeawaySaveBtn")?.addEventListener("click", saveLanguageTakeaway);
  $("languageTakeawayCloseBtn")?.addEventListener("click", hideLanguageTakeawayPopup);
  $("writingPromptImage")?.addEventListener("click", (event) => {
    const image = event.target.closest("[data-writing-image-preview]");
    if (!image) return;
    event.preventDefault();
    openWritingImageViewer(image.getAttribute("src"));
  });
  $("writingPromptText")?.addEventListener("mouseup", () => {
    if (isWritingHighlightDeleteMenuOpen()) return;
    state.writing.promptSelectionActive = false;
    handleWritingPromptSelectionChange({ force: true, delay: 120 });
  });
  $("writingPromptText")?.addEventListener("keyup", () => {
    handleWritingPromptSelectionChange({ force: true, delay: 120 });
  });
  $("writingPromptText")?.addEventListener("keydown", (event) => {
    const mark = event.target.closest?.(".writing-highlight-mark");
    if (!mark || !["Enter", " "].includes(event.key)) return;
    event.preventDefault();
    const index = Number(mark.dataset.writingHighlightIndex);
    openWritingPromptHighlightDeleteMenu(index, mark.getBoundingClientRect());
  });
  $("writingPromptText")?.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const mark = event.target.closest?.(".writing-highlight-mark");
    if (mark && $("writingPromptText")?.contains(mark)) {
      state.writing.promptSelectionActive = true;
      window.clearTimeout(state.writing.promptSelectionTimer);
      hideWritingHighlightMenu();
      state.writing.pendingHighlightPointer = {
        index: Number(mark.dataset.writingHighlightIndex),
        x: event.clientX,
        y: event.clientY,
      };
      return;
    }
    if (!getWritingPromptRangeAtPoint(event.clientX, event.clientY)) {
      state.writing.promptSelectionActive = true;
      state.writing.pendingHighlightDeleteIndex = -1;
      state.writing.pendingHighlightPointer = null;
      window.clearTimeout(state.writing.promptSelectionTimer);
      hideWritingHighlightMenu();
      return;
    }
    state.writing.promptSelectionActive = true;
    state.writing.pendingHighlightPointer = null;
    window.clearTimeout(state.writing.promptSelectionTimer);
    hideWritingHighlightMenu();
  });
  $("writingPromptText")?.addEventListener("pointerup", (event) => {
    const pending = state.writing.pendingHighlightPointer;
    state.writing.pendingHighlightPointer = null;
    state.writing.promptSelectionActive = false;
    if (pending) {
      const distance = Math.hypot(event.clientX - pending.x, event.clientY - pending.y);
      if (distance <= 6) {
        const index = Number(pending.index);
        openWritingPromptHighlightDeleteMenu(index, { clientX: pending.x, clientY: pending.y });
        event.preventDefault();
        event.stopPropagation();
        return;
      }
    }
    handleWritingPromptSelectionChange({ force: true, delay: 120 });
  });
  $("writingPromptText")?.addEventListener("click", (event) => {
    const mark = event.target.closest?.(".writing-highlight-mark");
    if (!mark || !$("writingPromptText")?.contains(mark)) return;
    const index = Number(mark.dataset.writingHighlightIndex);
    openWritingPromptHighlightDeleteMenu(index, { clientX: event.clientX, clientY: event.clientY });
    event.preventDefault();
    event.stopPropagation();
  });
  $("writingPromptText")?.addEventListener("pointercancel", () => {
    state.writing.promptSelectionActive = false;
    state.writing.pendingHighlightPointer = null;
    hideWritingHighlightMenu();
  });
  $("writingHighlightBtn")?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    applyWritingPromptHighlightSelection();
  });
  $("writingHighlightMenu")?.addEventListener("pointerdown", (event) => {
    event.stopPropagation();
  });
  $("writingHighlightMenu")?.addEventListener("click", (event) => {
    event.stopPropagation();
  });
  document.addEventListener("selectionchange", () => {
    handleWritingPromptSelectionChange({ delay: 160 });
  });
  document.addEventListener("pointerup", () => {
    if (!state.writing.promptSelectionActive) return;
    state.writing.promptSelectionActive = false;
    handleWritingPromptSelectionChange({ force: true, delay: 120 });
  });
  document.addEventListener("pointerdown", (event) => {
    const menu = $("writingHighlightMenu");
    if (menu?.contains(event.target)) return;
    const promptEl = $("writingPromptText");
    if (promptEl?.contains(event.target)) return;
    hideWritingHighlightMenu();
  });
  $("writingImageViewer")?.addEventListener("click", (event) => {
    if (event.target?.id === "writingImageViewer" || event.target?.id === "writingImageViewerImg") {
      closeWritingImageViewer();
    }
  });
  $("languageTakeawaySource")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    translateLanguageTakeawaySource();
  });
  document.addEventListener("pointerdown", (event) => {
    const popup = $("languageTakeawayPopup");
    const trigger = $("languageTakeawayTrigger");
    if (popup?.classList.contains("hidden")) return;
    if (popup.contains(event.target) || trigger?.contains(event.target)) return;
    hideLanguageTakeawayPopup();
  });
  $("languageTakeawayPopupHandle")?.addEventListener("pointerdown", (event) => {
    const popup = $("languageTakeawayPopup");
    if (!popup || event.target.closest("button")) return;
    const rect = popup.getBoundingClientRect();
    state.languageTakeaway.dragging = true;
    state.languageTakeaway.dragOffsetX = event.clientX - rect.left;
    state.languageTakeaway.dragOffsetY = event.clientY - rect.top;
    popup.setPointerCapture?.(event.pointerId);
  });
  $("languageTakeawayPopup")?.addEventListener("pointermove", (event) => {
    if (!state.languageTakeaway.dragging) return;
    const popup = $("languageTakeawayPopup");
    if (!popup) return;
    placeLanguageTakeawayPopup(
      event.clientX - state.languageTakeaway.dragOffsetX,
      event.clientY - state.languageTakeaway.dragOffsetY
    );
  });
  $("languageTakeawayPopup")?.addEventListener("pointerup", () => {
    state.languageTakeaway.dragging = false;
  });
  $("saveP1CorpusBtn")?.addEventListener("click", () => {
    saveAndCloseP1CorpusEditor().catch(() => null);
  });
  $("copyP1AiAnswerBtn")?.addEventListener("click", async () => {
    const box = $("p1CorpusAiAnswer");
    const value = box?.dataset.markdownSource?.trim() || box?.innerText?.trim() || "";
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      const button = $("copyP1AiAnswerBtn");
      if (button) {
        button.classList.add("copied");
        window.setTimeout(() => button.classList.remove("copied"), 900);
      }
    } catch (_error) {
      // Clipboard access is browser-dependent; the reference answer remains selectable.
    }
  });
  document.addEventListener("copy", (event) => {
    const selection = window.getSelection?.();
    if (!selection || selection.isCollapsed) return;
    const anchor = selection.anchorNode?.nodeType === Node.TEXT_NODE ? selection.anchorNode.parentElement : selection.anchorNode;
    const focus = selection.focusNode?.nodeType === Node.TEXT_NODE ? selection.focusNode.parentElement : selection.focusNode;
    const sourceEl = anchor?.closest?.("[data-markdown-source]") || focus?.closest?.("[data-markdown-source]");
    const markdown = sourceEl?.dataset?.markdownSource?.trim();
    if (!markdown) return;
    event.preventDefault();
    event.clipboardData?.setData("text/plain", markdown);
  });
  $("saveP2CorpusBtn")?.addEventListener("click", () => {
    saveAndCloseP2CorpusEditor().catch(() => null);
  });
  $("saveP2CorpusP3Btn")?.addEventListener("click", () => {
    saveAndCloseP2CorpusP3Editor().catch(() => null);
  });
  $("openP2CorpusP3QuestionPickerBtn")?.addEventListener("click", openP2CorpusP3QuestionPicker);
  $("closeP2CorpusP3QuestionPickerBtn")?.addEventListener("click", closeP2CorpusP3QuestionPicker);
  $("insertP2CorpusP3QuestionsBtn")?.addEventListener("click", insertSelectedP2CorpusP3Questions);
  document.addEventListener("keydown", handleGlobalKeydown, true);
  document.addEventListener("visibilitychange", () => {
    if (canWarmWritingPromptImages() && state.writing.promptImagePreloadQueue.length) {
      drainWritingPromptImagePreloadQueue();
    }
  });
  window.addEventListener("beforeunload", autosaveOpenCorpusEditors);
  $("recordControl")?.addEventListener("click", () => {
    if (state.status === "recording") {
      stopRecording();
    } else if (state.status === "preparing") {
      const sessionId = state.practiceSessionId;
      if (!isActivePracticeSession(sessionId)) return;
      clearTimer();
      startRecording(sessionId).catch(showError);
    } else if (state.status === "analysis_failed") {
      const sessionId = state.practiceSessionId;
      if (isActivePracticeSession(sessionId) && state.currentTurn) {
        if (hasUsableTurnQuestion(state.currentTurn) && !state.currentTurn.examiner_tts?.audio_url) {
          beginPreparationWithoutExaminerAudio(sessionId, state.currentTurn, "analysis-failed-recovery-no-audio");
        } else {
          beginExaminerPhase(sessionId).catch(showError);
        }
      } else {
        scoreAttempt().catch(showError);
      }
    } else if (state.status === "follow_up_failed") {
      const sessionId = state.practiceSessionId;
      const failedTurn = state.currentTurn;
      const sourceTurn = sourceTurnForStreamedFollowUp(state.attempt, failedTurn);
      if (!isActivePracticeSession(sessionId) || !failedTurn || !sourceTurn) return;
      const retryTurn = {
        ...failedTurn,
        question: "",
        examiner_text: "",
        prompt: {
          ...(failedTurn.prompt || {}),
          question: "",
          backend: "stream_pending",
          generation_status: "pending",
          generation_error: "",
        },
        examiner_tts: { provider: "volcengine", status: "pending", audio_url: null },
      };
      state.currentTurn = retryTurn;
      state.attempt = mergeCompletedTurnPayload(state.attempt, retryTurn);
      renderTurn(retryTurn);
      setRecordButton("turn_saved", "Next", "正在重新生成追问。");
      text("recordStatus", "正在重新生成追问...");
      streamFollowUpForCompletedTurn(state.attempt, sourceTurn, retryTurn, sessionId).catch((error) => {
        if (state.abortingAttemptId === state.attempt?.id || !isActivePracticeSession(sessionId)) return;
        setRecordButton("follow_up_failed", "重新生成追问", "追问生成失败，点击重试。");
        text("recordStatus", error?.message ? `追问生成失败：${error.message}` : "追问生成失败，可以重新生成。");
      });
    } else if (state.status === "completion_failed") {
      retryTurnCompletion().catch(showError);
    } else if (state.status === "idle" || state.status === "ready" || state.status === "summary") {
      if (state.currentTurn && state.status === "ready") {
        beginExaminerPhase(state.practiceSessionId);
      } else {
        startPractice();
      }
    }
  });
  document.querySelectorAll("[data-home-mode]").forEach((button) => {
    button.addEventListener("click", (event) => {
      if (isNewTabNavigationEvent(event)) return;
      event.preventDefault();
      navigatePracticeMode(button.dataset.homeMode || "mock");
    });
  });
  $("exitPractice")?.addEventListener("click", () => exitPractice());
  $("p3GeneratePlanButton")?.addEventListener("click", () => generateP3Plan());
  $("p3StartButton")?.addEventListener("click", () => startPractice());
  document.querySelectorAll("[data-p3-source]").forEach((button) => {
    button.addEventListener("click", () => {
      const source = button.dataset.p3Source || "bank";
      state.p3SourceType = source;
      if (source !== "p2_report" && source !== "bank") state.p3PracticeSource = null;
      state.p3CorpusSourceEntryId = "";
      if (source === "bank") {
        ensureSelectedP3BankCard()
          .then((selected) => {
            if (selected) return generateP3Plan();
            clearP3Plan("先选择一张带固定 P3 追问的 P2 题卡。");
            return null;
          })
          .catch(showError);
      } else {
        clearP3Plan(source === "p2_report" ? "从 P2 报告页进入时会自动带入本次回答。" : "");
      }
    });
  });
  document.querySelectorAll("[data-p3-focus]").forEach((button) => {
    button.addEventListener("click", () => {
      state.p3Focus = button.dataset.p3Focus || "comparison_concession";
      clearP3Plan();
    });
  });
  $("p3CustomThemeInput")?.addEventListener("input", (event) => {
    state.p3CustomTheme = String(event.target.value || "").trim();
    clearP3Plan();
  });
  document.querySelectorAll("[data-p3-intensity]").forEach((button) => {
    button.addEventListener("click", () => {
      state.p3Intensity = button.dataset.p3Intensity || "normal";
      clearP3Plan();
    });
  });
  $("p3TopicChips")?.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-p3-topic]");
    if (!chip) return;
    state.p3PracticeSource = null;
    state.p3CorpusSourceEntryId = "";
    state.p3SourceType = "bank";
    state.p3SelectedTopic = chip.dataset.p3Topic || "";
    document.querySelectorAll("#p3TopicChips .topic-chip").forEach((c) => {
      c.classList.toggle("active", c === chip);
    });
    clearP3Plan();
  });
  document.querySelectorAll("[data-writing-task]").forEach((button) => {
    button.addEventListener("click", async () => {
      const taskType = button.dataset.writingTask || "task1_academic";
      if (taskType === state.writing.taskType) return;
      if (state.writing.dirty && !window.confirm("当前作文还没有保存，确定要切换 Task 吗？")) return;
      state.writing.taskType = taskType;
      setWritingSwitchState(".writing-topbar-actions .writing-task-switch", taskType);
      document.querySelectorAll("[data-writing-task]").forEach((item) => {
        item.classList.toggle("active", item.dataset.writingTask === taskType);
      });
      state.writing.entry = null;
      state.writing.prompt = null;
      state.writing.dirty = false;
      if ($("writingAnswer")) $("writingAnswer").value = "";
      await loadWritingPrompts(taskType).catch(showWritingError);
      const prompts = state.writing.prompts[taskType] || [];
      if (prompts.length) setWritingPrompt(prompts[0], true);
      renderWritingSurface();
    });
  });
  $("writingPromptPickerBtn")?.addEventListener("click", () => openWritingPromptPicker());
  $("writingPromptCloseBtn")?.addEventListener("click", closeWritingPromptPicker);
  document.querySelectorAll("[data-writing-prompt-close]").forEach((button) => {
    button.addEventListener("click", closeWritingPromptPicker);
  });
  $("agentAssistantBtn")?.addEventListener("click", openAgentAssistant);
  $("p1CorpusAgentBtn")?.addEventListener("click", () => openAgentAssistant("p1Corpus"));
  $("p2CorpusAgentBtn")?.addEventListener("click", () => openAgentAssistant("p2Corpus"));
  $("agentAssistantForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    runAgentAssistantSearch();
  });
  document.querySelectorAll("[data-agent-assistant-close]").forEach((button) => {
    button.addEventListener("click", closeAgentAssistant);
  });
  document.querySelectorAll("[data-agent-assistant-example]").forEach((button) => {
    button.addEventListener("click", () => {
      if ($("agentAssistantQuery")) $("agentAssistantQuery").value = button.dataset.agentAssistantExample || "";
      runAgentAssistantSearch(button.dataset.agentAssistantExample || "");
    });
  });
  document.querySelectorAll("[data-writing-paragraph-close]").forEach((button) => {
    button.addEventListener("click", closeWritingParagraphModal);
  });
  document.querySelectorAll("[data-writing-score-complete-close]").forEach((button) => {
    button.addEventListener("click", closeWritingScoreCompleteModal);
  });
  $("writingScoreCompleteReportBtn")?.addEventListener("click", openWritingScoreCompleteReport);
  document.querySelectorAll("[data-speaking-score-complete-close]").forEach((button) => {
    button.addEventListener("click", closeSpeakingScoreCompleteModal);
  });
  $("speakingScoreCompleteReportBtn")?.addEventListener("click", openSpeakingScoreCompleteReport);
  document.querySelectorAll("[data-writing-picker-task]").forEach((button) => {
    button.addEventListener("click", async () => {
      const taskType = button.dataset.writingPickerTask || "task1_academic";
      await writingPromptPickerController.switchTask(taskType);
    });
  });
  $("writingRandomBtn")?.addEventListener("click", () => chooseRandomWritingPrompt(true).catch(showWritingError));
  $("writingSaveBtn")?.addEventListener("click", () => saveWritingEntry().catch(showWritingError));
  $("writingScoreBtn")?.addEventListener("click", () => scoreWritingEntry().catch(showWritingError));
  $("writingRefreshBtn")?.addEventListener("click", () => loadWriting().catch(showWritingError));
  // Writing action panel collapse toggle
  (function initWritingActionPanel() {
    const panel = $("writingActionPanel");
    const toggle = $("writingActionPanelToggle");
    if (!panel || !toggle) return;
    setWritingActionPanelCollapsed(false);
    toggle.addEventListener("click", () => {
      const next = !panel.classList.contains("is-collapsed");
      setWritingActionPanelCollapsed(next);
    });
  })();
  const handleWritingReportEditClick = (event) => {
    const button = event.target.closest("[data-writing-report-edit]");
    if (!button) return;
    if (event.type === "auxclick" && event.button !== 1) return;
    event.preventDefault();
    event.stopPropagation();
    const entryId = button.dataset.writingReportEdit || "";
    const entryHint = writingReportEntryFromEditButton(button);
    if (isNewTabNavigationEvent(event)) {
      editWritingReportEntryInNewTab(entryId, entryHint).catch(showWritingError);
      return;
    }
    editWritingReportEntry(entryId).catch(showWritingError);
  };
  document.addEventListener("click", handleWritingReportEditClick);
  document.addEventListener("auxclick", handleWritingReportEditClick);
  $("writingAnswer")?.addEventListener("input", () => {
    // Slash commands resolve before we mark the doc dirty.
    if (handleWritingFrameSlashCommand()) return;
    state.writing.dirty = true;
    updateWritingWordCount({ preserveScroll: true });
    text("writingSaveStatus", "未保存的修改");
  });
  document.querySelectorAll("[data-frame-cmd]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.frameCmd === "frame") applyWritingFrame();
      else if (btn.dataset.frameCmd === "myframe") openWritingFrameEditor();
    });
  });
  $("writingFrameSaveBtn")?.addEventListener("click", saveWritingFrame);
  $("writingFrameResetBtn")?.addEventListener("click", resetWritingFrame);
  document.querySelectorAll("[data-writing-frame-close]").forEach((el) => {
    el.addEventListener("click", closeWritingFrameEditorSavingChanges);
  });
  $("writingAnswer")?.addEventListener("input", () => {
    if (writingAutosaveReady()) state.writing.autosaveEnabled = true;
    text("writingSaveStatus", writingAutosaveStatusText());
    maybeScheduleWritingAutosave();
  });
  $("writingCalendar")?.addEventListener("click", (event) => {
    const day = event.target.closest("[data-writing-entry-id]");
    if (day?.dataset.writingEntryId) {
      state.writing.activeReportId = day.dataset.writingEntryId;
      switchView("writingReports");
    }
  });
  document.querySelectorAll("[data-font-style]").forEach((button) => {
    button.addEventListener("click", () => applyFontStyle(button.dataset.fontStyle || "default"));
  });
  $("summaryOverlay")?.addEventListener("click", hideSummary);
  // Recharge dialog
  $("openRechargeBtn")?.addEventListener("click", openRechargeDialog);
  $("cancelRechargeBtn")?.addEventListener("click", closeRechargeDialog);
  $("confirmRechargeBtn")?.addEventListener("click", doRecharge);
  $("rechargeDialog")?.addEventListener("click", (e) => {
    if (e.target.id === "rechargeDialog") closeRechargeDialog();
  });
  document.querySelectorAll("#rechargeDialog .recharge-btn[data-amount]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const amount = parseFloat(btn.dataset.amount) || 0;
      setRechargeAmount(amount);
    });
  });
  $("rechargeAmount")?.addEventListener("input", (e) => {
    const amount = parseFloat(e.target.value) || 0;
    state.pendingRecharge = amount;
    updateRechargePreview();
    // Deselect preset buttons when custom input
    document.querySelectorAll("#rechargeDialog .recharge-btn").forEach((btn) => {
      btn.classList.remove("selected");
    });
  });
}

function p3FocusLabel(value) {
  return P3_FOCUS_LABELS[value] || P3_FOCUS_LABELS.comparison_concession;
}

function p3SourceLabel(value) {
  return P3_SOURCE_LABELS[value] || P3_SOURCE_LABELS.bank;
}

function p3QuestionTypeLabel(value) {
  return P3_TYPE_LABELS[value] || "讨论题";
}

function p3MoveLabel(value) {
  return P3_MOVE_LABELS[String(value || "").trim()] || String(value || "").trim();
}

function p3IntensityLabel(value) {
  return {
    normal: "标准练习",
    high: "追问压力",
  }[value] || "标准练习";
}

function currentP3Theme() {
  if (state.p3SourceType === "custom") return String($("#p3CustomThemeInput")?.value || state.p3CustomTheme || "").trim();
  if (state.p3SourceType === "bank") return String(selectedP3BankCard()?.title || state.p3PracticeSource?.theme || state.p3SelectedTopic || "").trim();
  return String(state.p3PracticeSource?.theme || state.p3SelectedTopic || state.p3CustomTheme || "").trim();
}

function p3ReportContextCard(source = state.p3PracticeSource || {}) {
  const title = source.title || "P2 report";
  const band = source.band || "";
  const time = formatReportTime(source.displayTime || "");
  return `
    <article class="p3-source-report-card tone-p2">
      <div class="history-item-top">
        <span class="history-item-tag p2">P2</span>
        ${band !== "" ? `<span class="history-item-band">Band ${escapeHtml(band)}</span>` : ""}
      </div>
      <span class="p3-source-card-menu" aria-hidden="true">•••</span>
      <strong class="history-item-title">${escapeHtml(title)}</strong>
      ${time ? `<small class="history-item-time">${escapeHtml(time)}</small>` : ""}
    </article>
  `;
}

function p3CorpusContextHtml() {
  const options = p3CorpusSourceOptions();
  if (!options.length) {
    return `
      <div class="p3-context-note">
        <strong>还没有可选的 P2 素材</strong>
        <span>先到“我准备的 P2 串题素材库”里保存素材，再回到这里按素材生成 P3 追问。</span>
      </div>
    `;
  }
  let selected = options.find((item) => item.entry_id === state.p3CorpusSourceEntryId);
  if (!selected) {
    selected = options[0];
    setP3SourceFromCorpusEntry(selected);
  }
  return `
    <div class="p3-corpus-context">
      <select id="p3CorpusSourceSelect" class="p3-custom-input" aria-label="选择 P2 素材">
        ${options.map((item) => `<option value="${escapeHtml(item.entry_id)}"${item.entry_id === state.p3CorpusSourceEntryId ? " selected" : ""}>${escapeHtml(item.label)} · ${escapeHtml(item.title || "未命名素材")}</option>`).join("")}
      </select>
      <article class="p3-source-corpus-card">
        <div>
          <span>${escapeHtml(selected.label || "P2 素材")}</span>
          <strong>${escapeHtml(selected.title || "未命名素材")}</strong>
        </div>
        <p>${escapeHtml((selected.material_text || selected.linked_question || "").slice(0, 180))}${String(selected.material_text || selected.linked_question || "").length > 180 ? "..." : ""}</p>
      </article>
    </div>
  `;
}

function renderP3SourceContext(message = "") {
  const section = $("#p3SourceContextSection");
  const target = $("#p3SourceContext");
  if (!section || !target) return;
  const sourceType = state.p3SourceType;
  const source = state.p3PracticeSource || {};
  if (sourceType === "bank" || sourceType === "season_bank") {
    const card = selectedP3BankCard();
    if (!card) {
      // No card yet — CTA lives in the right-column plan preview; hide left section
      section.classList.add("hidden");
      target.innerHTML = "";
      return;
    }
    // Card selected — show compact selected-card strip in left column
    section.classList.remove("hidden");
    target.innerHTML = `
      <div class="p3-context-grid p3-context-grid-single">
        ${p3SelectedBankCardHtml(card)}
      </div>
    `;
    target.querySelectorAll("[data-p3-bank-picker-open]").forEach((entry) => {
      entry.addEventListener("click", () => openP3BankPicker().catch(showError));
      entry.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        openP3BankPicker().catch(showError);
      });
    });
    return;
  }
  if (sourceType === "p2_report") {
    section.classList.remove("hidden");
    if (source.sourceType === "p2_report") {
      target.innerHTML = `
        <div class="p3-context-grid">
          ${p3ReportContextCard(source)}
          <div class="p3-context-note">
            <strong>已带入这次 P2 回答</strong>
            <span>系统会基于这次报告里的 P2 题目和你的回答，生成更像真实 Part 3 的延展追问。</span>
          </div>
        </div>
      `;
    } else {
      target.innerHTML = `
        <div class="p3-context-note p3-context-warning">
          <strong>需要从 P2 报告进入</strong>
          <span>打开一份 P2 口语报告，点击“根据本次P2回答练习P3”，这里才会自动带入那次 P2 的题目、回答和分数上下文。</span>
        </div>
      `;
    }
    return;
  }
  section.classList.toggle("hidden", !message);
  target.innerHTML = message ? `<div class="p3-context-note"><span>${escapeHtml(message)}</span></div>` : "";
}

function clearP3Plan(message = "") {
  state.p3Plan = null;
  state.p3PlanError = "";
  state.p3PlanLoading = false;
  renderP3PlanPreview();
  syncP3LaunchPanel(message);
}

function p3PlanPayload() {
  const source = state.p3PracticeSource || {};
  const sourceType = state.p3SourceType === "season_bank" ? "bank" : state.p3SourceType;
  const theme = currentP3Theme() || "society and daily life";
  const bankCard = sourceType === "bank" ? selectedP3BankCard() : null;
  const bankFollowUps = bankCard ? p2BankCardFollowUps(bankCard) : [];
  return {
    theme,
    p3_intensity: state.p3Intensity,
    p3_focus: state.p3Focus,
    source: sourceType,
    ...(bankCard ? {
      source: "bank",
      p2_question_id: p2BankQuestionId(bankCard),
      p3_follow_ups: bankFollowUps,
      p3_theme: bankCard.p3_theme || theme,
      season: bankCard.season || "",
    } : {}),
    ...(sourceType === "p2_report" && source.answer ? { prior_answer: source.answer } : {}),
    ...(sourceType === "p2_report" && source.attemptId ? { p2_attempt_id: source.attemptId } : {}),
    ...(sourceType === "p2_report" && source.p2CorpusEntryId ? { p2_corpus_entry_id: source.p2CorpusEntryId } : {}),
    ...(sourceType === "p2_report" && source.p3FollowUpText ? { p3_follow_up_text: source.p3FollowUpText } : {}),
  };
}

function syncP3LaunchPanel(message = "") {
  document.querySelectorAll("[data-p3-source]").forEach((button) => {
    const activeSource = state.p3SourceType === "season_bank" ? "bank" : state.p3SourceType;
    button.classList.toggle("active", button.dataset.p3Source === activeSource);
  });
  document.querySelectorAll("[data-p3-focus]").forEach((button) => {
    button.classList.toggle("active", button.dataset.p3Focus === state.p3Focus);
  });
  document.querySelectorAll("[data-p3-intensity]").forEach((button) => {
    button.classList.toggle("active", button.dataset.p3Intensity === state.p3Intensity);
  });
  const switchEl = document.querySelector(".p3-mode-switch");
  if (switchEl) {
    switchEl.classList.toggle("high-intensity", state.p3Intensity === "high");
  }
  $("#p3CustomThemeSection")?.classList.toggle("hidden", state.p3SourceType !== "custom");
  renderP3SourceContext(message);
  const customInput = $("#p3CustomThemeInput");
  if (customInput && customInput.value !== state.p3CustomTheme) customInput.value = state.p3CustomTheme || "";
  text("p3ModeHelp", P3_INTENSITY_HELP[state.p3Intensity] || P3_INTENSITY_HELP.normal);
  text("p3PlanStatus", message || state.p3PlanError || (state.p3Plan ? `已生成：${p3SourceLabel(state.p3Plan.source?.type || state.p3SourceType)} · ${p3FocusLabel(state.p3Plan.focus || state.p3Focus)} · ${p3IntensityLabel(state.p3Plan.intensity || state.p3Intensity)}` : ""));
  const startButton = $("#p3StartButton");
  if (startButton) startButton.disabled = !state.p3Plan || state.p3PlanLoading;
  const generateButton = $("#p3GeneratePlanButton");
  if (generateButton) {
    generateButton.disabled = state.p3PlanLoading;
    const idleText = state.p3SourceType === "bank"
      ? (state.p3Plan ? "重新载入追问" : "载入固定追问")
      : (state.p3Plan ? "重新生成追问" : "生成 P3 追问");
    generateButton.textContent = state.p3PlanLoading ? "正在准备追问..." : idleText;
  }
}

function renderP3PlanPreview() {
  const panel = $("#p3PlanPreview");
  if (!panel) return;
  const plan = state.p3Plan;
  const hasExistingPlan = Boolean(plan && Array.isArray(plan.questions) && plan.questions.length);
  panel.classList.toggle("is-refreshing", Boolean(state.p3PlanLoading && hasExistingPlan));
  if (state.p3PlanLoading && !hasExistingPlan) {
    panel.innerHTML = centeredLoadingHtml("正在生成 P3 训练计划", "系统正在整理题型、追问方向和回答动作。");
    return;
  }
  if (state.p3PlanError && !hasExistingPlan) {
    panel.innerHTML = `
      <div class="p3-plan-empty p3-plan-error">
        <strong>AI 生成失败</strong>
        <span>${escapeHtml(state.p3PlanError)}</span>
        <small>请确认 Aiapis/HTTP provider 已配置并可用，然后重新生成。不会用本地假题冒充 AI 输出。</small>
      </div>
    `;
    return;
  }
  const questions = Array.isArray(plan?.questions) ? plan.questions : [];
  if (!plan || !questions.length) {
    // Bank mode: right-column is the primary card-picker entry point
    if (state.p3SourceType === "bank" || state.p3SourceType === "season_bank") {
      panel.innerHTML = `
        <div class="p3-bank-entry">
          <div class="p3-bank-entry-icon">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4Z" stroke="currentColor" stroke-width="1.8"/>
              <path d="M8 8h7M8 12h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
          </div>
          <strong>选择一张 P2 题卡</strong>
          <span>练题卡固定维护的 P3 追问，不走 AI 生成，每次一样。</span>
          <button class="p3-bank-entry-btn" type="button" data-p3-bank-picker-open>
            浏览题卡
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
        </div>
      `;
      panel.querySelector("[data-p3-bank-picker-open]")?.addEventListener("click", () => openP3BankPicker().catch(showError));
      return;
    }
    panel.innerHTML = `
      <div class="p3-plan-empty">
        <strong>还没有生成训练计划</strong>
        <span>选择来源和目标后，先生成计划。系统会列出题型、追问方向和每题要完成的 discussion move。</span>
      </div>
    `;
    return;
  }
  panel.innerHTML = `
    <div class="p3-plan-head">
      <div>
        <strong>${escapeHtml(plan.theme || currentP3Theme() || "Part 3 discussion")}</strong>
        <span>${escapeHtml(p3SourceLabel(plan.source?.type || state.p3SourceType))} · ${escapeHtml(p3FocusLabel(plan.focus || state.p3Focus))} · ${escapeHtml(p3IntensityLabel(plan.intensity || state.p3Intensity))}</span>
      </div>
      <small>${escapeHtml(questions.length)} 个主问题${(plan.intensity || state.p3Intensity) === "high" ? " + 即时追问" : ""}</small>
    </div>
    <div class="p3-plan-list">
      ${questions.map((item, index) => `
        <article class="p3-plan-card">
          <div class="p3-plan-card-top">
            <span>Q${index + 1}</span>
            <em>${escapeHtml(p3QuestionTypeLabel(item.type))}</em>
          </div>
          <p>${escapeHtml(item.question || "")}</p>
          <div class="p3-target-moves">
            ${(item.target_moves || []).slice(0, 4).map((move) => `<span>${escapeHtml(p3MoveLabel(move))}</span>`).join("")}
          </div>
        </article>
      `).join("")}
    </div>
    ${state.p3PlanLoading ? `
      <div class="p3-plan-refresh-overlay" aria-hidden="true">
        <span>正在重新载入追问...</span>
      </div>
    ` : ""}
  `;
}

async function generateP3Plan(options = {}) {
  if (state.p3PlanLoading) return;
  state.p3PlanError = "";
  if (state.p3SourceType === "bank") {
    const source = await ensureSelectedP3BankCard();
    if (!source?.p3FollowUps?.length) {
      clearP3Plan("先选择一张带固定 P3 追问的 P2 题卡。");
      return;
    }
  }
  if (state.p3SourceType === "p2_report" && state.p3PracticeSource?.sourceType !== "p2_report") {
    clearP3Plan("请先从一份 P2 报告进入，系统才能带入那次回答作为 P3 上下文。");
    return;
  }
  if (state.p3SourceType === "custom") {
    state.p3CustomTheme = String($("#p3CustomThemeInput")?.value || "").trim();
    if (!state.p3CustomTheme) {
      clearP3Plan("先输入一个自定义主题。");
      $("#p3CustomThemeInput")?.focus();
      return;
    }
  }
  state.p3PlanLoading = true;
  renderP3PlanPreview();
  syncP3LaunchPanel("正在生成计划...");
  try {
    const payload = await api("/api/p3/questions", p3PlanPayload());
    const nextPlan = payload.plan || {
      theme: currentP3Theme(),
      focus: state.p3Focus,
      intensity: state.p3Intensity,
      source: { type: state.p3SourceType },
      questions: (payload.structured_questions || []).length
        ? payload.structured_questions
        : (payload.questions || []).map((question, index) => ({
            id: `q${index + 1}`,
            type: index === 0
              ? (P3_FOCUS_TO_TYPE[state.p3Focus] || "comparison_concession")
              : P3_TYPE_SEQUENCE[(index - 1) % P3_TYPE_SEQUENCE.length],
            question,
            target_moves: P3_TARGET_MOVES[
              index === 0
                ? (P3_FOCUS_TO_TYPE[state.p3Focus] || "comparison_concession")
                : P3_TYPE_SEQUENCE[(index - 1) % P3_TYPE_SEQUENCE.length]
            ] || P3_TARGET_MOVES.opinion_justify,
            source: state.p3SourceType,
          })),
      follow_up: payload.follow_up || "",
      backend: payload.backend || "fallback",
      status: payload.status || "fallback",
    };
    const questions = Array.isArray(nextPlan.questions) ? nextPlan.questions : [];
    const sourceType = nextPlan.source?.type === "season_bank" ? "bank" : (nextPlan.source?.type || state.p3SourceType);
    const requiresAi = sourceType === "p2_report" || sourceType === "custom";
    if (requiresAi && (nextPlan.status !== "ready" || questions.length < 3)) {
      throw new Error(nextPlan.error || payload.error || "AI 没有返回 3 道可用的 P3 追问。");
    }
    if (!requiresAi && !questions.length) {
      throw new Error(nextPlan.error || payload.error || "没有可用的固定 P3 追问。");
    }
    state.p3Plan = nextPlan;
    state.p3Intensity = state.p3Plan.intensity || state.p3Intensity;
    state.p3Focus = state.p3Plan.focus || state.p3Focus;
    state.p3SourceType = state.p3Plan.source?.type === "season_bank" ? "bank" : (state.p3Plan.source?.type || state.p3SourceType);
    renderP3PlanPreview();
    syncP3LaunchPanel(options.fromP2 ? "已根据这次 P2 生成训练计划，确认后再开始。" : "计划已生成，确认后可以开始。");
  } catch (error) {
    state.p3PlanError = error instanceof Error ? error.message : "生成计划失败。";
    renderP3PlanPreview();
    syncP3LaunchPanel(state.p3PlanError);
  } finally {
    state.p3PlanLoading = false;
    renderP3PlanPreview();
    syncP3LaunchPanel();
  }
}

function renderP3TopicChips(topics) {
  const target = $("p3TopicChips");
  if (!target) {
    state.p3Topics = topics.slice(0, 8);
    syncP3LaunchPanel();
    return;
  }
  state.p3Topics = topics.slice(0, 8);
  target.innerHTML = state.p3Topics.map((topic) => (
    `<button type="button" class="topic-chip${state.p3SelectedTopic === topic ? " active" : ""}" data-p3-topic="${escapeHtml(topic)}">${escapeHtml(topic.replaceAll("_", " "))}</button>`
  )).join("");
  if (state.p3Topics.length && !state.p3SelectedTopic) {
    state.p3SelectedTopic = state.p3Topics[0];
    document.querySelector("#p3TopicChips .topic-chip")?.classList.add("active");
  }
  syncP3LaunchPanel();
}

async function loadWritingTakeaways(...args) {
  return corpusTakeawayController.loadWritingTakeaways(...args);
}

function renderWritingTakeaways(...args) {
  return corpusTakeawayController.renderWritingTakeaways(...args);
}

function renderWritingTakeawayToggle(...args) {
  return corpusTakeawayController.renderWritingTakeawayToggle(...args);
}

function toggleWritingTakeawayHiddenMode(...args) {
  return corpusTakeawayController.toggleWritingTakeawayHiddenMode(...args);
}

function revealAndSpeakWritingTakeaway(...args) {
  return corpusTakeawayController.revealAndSpeakWritingTakeaway(...args);
}

async function deleteWritingTakeawayEntry(...args) {
  return corpusTakeawayController.deleteWritingTakeawayEntry(...args);
}

const AGENT_ASSISTANT_COPY = {
  writing: {
    title: "写作题库助手",
    subtitle: "输入中文描述、OCR 片段或关键词，助手会在写作题库里定位题目。",
    label: "你要找什么写作题？",
    placeholder: "例如：水资源免费 / 科技影响学习 / 人口柱状图",
    status: "可以直接粘 OCR 题干，也可以用中文说大概意思。",
    loadingTitle: "正在查找写作题库",
    loadingBody: "正在检索 Task 1 / Task 2 题目。",
    empty: "还没有结果。输入题干片段、主题词或剑雅编号后点击查找。",
    examples: [
      ["水资源免费", "水资源免费"],
      ["科技影响学习", "科技影响学习"],
      ["Task 1 人口图表", "人口 图表 Task 1"],
    ],
  },
  p1Corpus: {
    title: "P1 题库助手",
    subtitle: "输入中文话题、英文题干或关键词，助手会定位到 P1 语料库里的具体问题。",
    label: "你要找什么 P1 问题？",
    placeholder: "例如：家人 / 学习 / 住在哪里 / full name",
    status: "支持中文关键词和英文题干模糊搜索。",
    loadingTitle: "正在查找 P1 题库",
    loadingBody: "正在匹配话题分组和短问题。",
    empty: "没有找到明显匹配。可以换一个中文话题词或英文题干片段。",
    examples: [
      ["学习/实习", "学习 实习"],
      ["住在哪里", "住在哪里 live"],
      ["兴趣爱好", "兴趣 爱好 hobby"],
    ],
  },
  p2Corpus: {
    title: "P2 题库助手",
    subtitle: "输入中文语义、英文题干或素材关键词，助手会定位到 P2 题卡、素材或 Brainstorm 灵感行。",
    label: "你要找什么 P2 题？",
    placeholder: "例如：艰难的决定 / 迟到的经历 / crowded place",
    status: "支持模糊搜索，也能跳到串题灵感 Brainstorm 对应行。",
    loadingTitle: "正在查找 P2 题库",
    loadingBody: "正在匹配当季题卡、已保存素材和 Brainstorm 列表。",
    empty: "没有找到明显匹配。可以输入中文场景，例如“艰难的决定”“迟到的经历”。",
    examples: [
      ["艰难的决定", "艰难的决定"],
      ["迟到的经历", "迟到的经历"],
      ["读写的地方", "读写的地方"],
    ],
  },
};

const AGENT_QUERY_EXPANSIONS = [
  ["艰难的决定", "困难的决定", "重要决定", "难选", "选择", "decision", "difficult decision", "hard decision", "important decision", "choice", "choose"],
  ["迟到的经历", "迟到", "晚到", "耽误", "延误", "错过", "late", "being late", "was late", "delayed", "missed", "punctual", "on time"],
  ["拥挤的地方", "人多的地方", "crowded place", "busy place", "many people"],
  ["读写的地方", "学习的地方", "安静的地方", "place where you read and write", "study place", "library", "cafe"],
  ["家人", "家庭", "父母", "family", "parents", "relative"],
  ["学习", "学校", "大学", "专业", "实习", "study", "school", "university", "major", "internship"],
  ["工作", "职业", "公司", "work", "job", "company", "career"],
  ["兴趣", "爱好", "运动", "音乐", "hobby", "sport", "music", "free time"],
  ["旅行", "假期", "旅游", "holiday", "travel", "trip", "visited"],
  ["地点", "城市", "家乡", "place", "city", "hometown", "live"],
];

function agentAssistantContext() {
  return AGENT_ASSISTANT_COPY[state.agentAssistant.context] ? state.agentAssistant.context : "writing";
}

function agentAssistantCopy() {
  return AGENT_ASSISTANT_COPY[agentAssistantContext()];
}

function agentSearchNormalize(value = "") {
  return String(value || "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[_\-–—/]+/g, " ")
    .replace(/[^\p{L}\p{N}\u4e00-\u9fff]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function agentSearchTokens(value = "") {
  const normalized = agentSearchNormalize(value);
  const englishTokens = normalized.match(/[a-z0-9]+/g) || [];
  const chineseText = (normalized.match(/[\u4e00-\u9fff]+/g) || []).join("");
  const chineseTokens = [];
  for (let index = 0; index < chineseText.length; index += 1) {
    chineseTokens.push(chineseText.slice(index, index + 1));
    if (index + 2 <= chineseText.length) chineseTokens.push(chineseText.slice(index, index + 2));
    if (index + 3 <= chineseText.length) chineseTokens.push(chineseText.slice(index, index + 3));
    if (index + 4 <= chineseText.length) chineseTokens.push(chineseText.slice(index, index + 4));
  }
  return [...new Set([...englishTokens, ...chineseTokens].filter((token) => token.length > 1 || /[\u4e00-\u9fff]/.test(token)))];
}

function agentExpandQuery(query = "") {
  const raw = String(query || "").trim();
  const terms = [raw];
  const normalized = agentSearchNormalize(raw);
  AGENT_QUERY_EXPANSIONS.forEach((group) => {
    const matched = group.some((term) => normalized.includes(agentSearchNormalize(term)));
    if (matched) terms.push(...group);
  });
  return [...new Set(terms.flatMap((term) => [term, ...agentSearchTokens(term)]).map((term) => String(term || "").trim()).filter(Boolean))];
}

function agentAssistantScore(query, candidateText) {
  const textValue = agentSearchNormalize(candidateText);
  if (!textValue) return 0;
  const expanded = agentExpandQuery(query);
  const tokens = [...new Set(expanded.flatMap(agentSearchTokens))];
  let score = 0;
  expanded.forEach((term) => {
    const normalizedTerm = agentSearchNormalize(term);
    if (!normalizedTerm) return;
    if (textValue.includes(normalizedTerm)) score += normalizedTerm.length > 8 ? 0.32 : 0.22;
  });
  const matchedTokens = tokens.filter((token) => textValue.includes(token));
  if (tokens.length) score += Math.min(0.5, matchedTokens.length / Math.max(tokens.length, 1));
  const queryCompact = agentSearchNormalize(query).replace(/\s+/g, "");
  const textCompact = textValue.replace(/\s+/g, "");
  if (queryCompact && textCompact.includes(queryCompact)) score += 0.35;
  return Math.min(1, score);
}

function agentAssistantReasons(query, candidateText, fallback = "语义相关") {
  const textValue = agentSearchNormalize(candidateText);
  const reasons = agentExpandQuery(query)
    .filter((term) => {
      const normalizedTerm = agentSearchNormalize(term);
      return normalizedTerm && textValue.includes(normalizedTerm);
    })
    .slice(0, 4);
  return reasons.length ? reasons : [fallback];
}

function p2AgentQuestionId(entry = {}) {
  return String(entry.cue_id || entry.question_id || entry.canonical_entry_id || entry.entry_id || "").trim();
}

function p2AgentCueTitle(entry = {}) {
  const raw = String(entry.cue_title || entry.title || entry.question || entry.linked_question || "").replace(/\s+/g, " ").trim();
  if (!raw) return "未命名题卡";
  const fragments = [
    ...(Array.isArray(entry.bullets) ? entry.bullets : []),
    entry.rounding,
  ].map((item) => String(item || "").replace(/\s+/g, " ").trim()).filter(Boolean).sort((a, b) => b.length - a.length);
  let boundary = -1;
  fragments.forEach((fragment) => {
    const index = raw.indexOf(fragment);
    if (index > 0 && (boundary === -1 || index < boundary)) boundary = index;
  });
  return (boundary > 0 ? raw.slice(0, boundary) : raw).replace(/\s+/g, " ").trim() || "未命名题卡";
}

function p2AgentCueText(entry = {}) {
  return [
    p2AgentCueTitle(entry),
    entry.question,
    entry.linked_question,
    ...(Array.isArray(entry.bullets) ? entry.bullets : []),
    entry.rounding,
    entry.brainstorm_idea,
  ].filter(Boolean).join(" ");
}

function agentAssistantResultUrl(prompt) {
  return prompt.url || writingPromptDeepLink(prompt);
}

function agentAssistantMatchLabel(item = {}) {
  const prompt = item.prompt || item;
  const labels = {
    semantic: "语义相关",
    keyword: "关键词匹配",
    source: "来源匹配",
    bm25: "全文匹配",
    fuzzy: "模糊匹配",
    p1: "P1 题库",
    p2_card: "P2 题卡",
    p2_material: "P2 素材",
  };
  return labels[item.match_type] || labels[prompt.match_type] || "相关匹配";
}

function agentAssistantResultTitle(item) {
  if (item.kind === "p1") return item.title || item.question || "P1 问题";
  if (item.kind === "p2_card") return item.title || "P2 题卡";
  if (item.kind === "p2_material") return item.title || "P2 素材";
  const prompt = item.prompt || item;
  return prompt.title || writingPromptPickerTitle(prompt) || "Writing prompt";
}

function agentAssistantResultMeta(item) {
  if (item.kind === "p1") return [item.topicLabel || "P1", "短答题"].filter(Boolean).join(" · ");
  if (item.kind === "p2_card") return [item.categoryLabel || "当季 P2 题卡", item.brainstormIdea ? "已写 Brainstorm" : "可写 Brainstorm"].join(" · ");
  if (item.kind === "p2_material") return [item.categoryLabel || "P2 素材", item.hasP3 ? "P3 已填" : "P3 待填"].join(" · ");
  const prompt = item.prompt || item;
  const source = prompt.source_label || writingPromptPickerTitle(prompt) || writingTaskLabel(prompt.task_type);
  return `${source} · ${writingCategoryLabel(prompt.category) || prompt.category || "未分类"}`;
}

function agentAssistantResultBody(item) {
  if (item.kind === "p1") return item.question || "";
  if (item.kind === "p2_card") return item.prompt || "";
  if (item.kind === "p2_material") return item.preview || "";
  const prompt = item.prompt || item;
  return prompt.prompt || "";
}

function renderAgentAssistantResults() {
  const target = $("agentAssistantResults");
  if (!target) return;
  const copy = agentAssistantCopy();
  if (state.agentAssistant.loading) {
    target.innerHTML = centeredLoadingHtml(copy.loadingTitle, copy.loadingBody);
    return;
  }
  const results = state.agentAssistant.results || [];
  if (!results.length) {
    target.innerHTML = `<div class="agent-result-empty">${escapeHtml(copy.empty)}</div>`;
    return;
  }
  target.innerHTML = results.map((item, index) => {
    const prompt = item.prompt || item;
    const score = Number(item.score ?? prompt.match_score ?? 0);
    const reasons = item.reasons || prompt.match_reasons || [];
    const url = item.kind ? "" : agentAssistantResultUrl(prompt);
    const actionHtml = item.kind === "p2_card"
      ? `<button type="button" class="agent-result-open" data-agent-result-index="${index}" data-agent-action="p2-card">跳到题卡</button>
         <button type="button" class="agent-result-secondary" data-agent-result-index="${index}" data-agent-action="p2-brainstorm">跳到 Brainstorm</button>`
      : item.kind
        ? `<button type="button" class="agent-result-open" data-agent-result-index="${index}" data-agent-action="${escapeHtml(item.kind)}">跳转定位</button>`
        : `<button type="button" class="agent-result-open" data-agent-prompt-id="${escapeHtml(prompt.id)}" data-agent-task-type="${escapeHtml(prompt.task_type || "task2")}">打开题目</button>
           <a class="agent-result-link" href="${escapeHtml(url)}" data-agent-prompt-link="${escapeHtml(prompt.id)}">${escapeHtml(url)}</a>`;
    return `
      <article class="agent-result-card">
        <div class="agent-result-top">
          <div>
            <strong>${escapeHtml(agentAssistantResultTitle(item))}</strong>
            <span>${escapeHtml(agentAssistantResultMeta(item))}</span>
          </div>
          <em class="agent-result-score">${escapeHtml(agentAssistantMatchLabel(item))} · ${Math.round(score * 100)}%</em>
        </div>
        ${reasons.length ? `<div class="agent-result-reasons">${reasons.slice(0, 4).map((reason) => `<span>${escapeHtml(reason)}</span>`).join("")}</div>` : ""}
        <p class="agent-result-prompt">${escapeHtml(agentAssistantResultBody(item))}</p>
        <div class="agent-result-actions${item.kind === "p2_card" ? " has-two-actions" : ""}">
          ${actionHtml}
        </div>
      </article>
    `;
  }).join("");
  target.querySelectorAll("[data-agent-prompt-id]").forEach((button) => {
    button.addEventListener("click", () => {
      openAgentAssistantPrompt(button.dataset.agentPromptId || "", button.dataset.agentTaskType || "task2");
    });
  });
  target.querySelectorAll("[data-agent-result-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = (state.agentAssistant.results || [])[Number(button.dataset.agentResultIndex || -1)];
      jumpToAgentAssistantResult(item, button.dataset.agentAction || "");
    });
  });
}

function setAgentAssistantStatus(message) {
  text("agentAssistantStatus", message);
}

function setAgentAssistantContext(context = state.view || "writing") {
  const nextContext = AGENT_ASSISTANT_COPY[context] ? context : "writing";
  if (state.agentAssistant.context !== nextContext) {
    state.agentAssistant.context = nextContext;
    state.agentAssistant.results = [];
    state.agentAssistant.query = "";
    if ($("agentAssistantQuery")) $("agentAssistantQuery").value = "";
  }
  const copy = agentAssistantCopy();
  text("agentAssistantTitle", copy.title);
  text("agentAssistantSubtitle", copy.subtitle);
  const label = document.querySelector('label[for="agentAssistantQuery"]');
  if (label) label.textContent = copy.label;
  const input = $("agentAssistantQuery");
  if (input) input.placeholder = copy.placeholder;
  const examples = $("agentAssistantExamples");
  if (examples) {
    examples.innerHTML = copy.examples.map(([labelText, query]) => (
      `<button type="button" data-agent-assistant-example="${escapeHtml(query)}">${escapeHtml(labelText)}</button>`
    )).join("");
    examples.querySelectorAll("[data-agent-assistant-example]").forEach((button) => {
      button.addEventListener("click", () => {
        if ($("agentAssistantQuery")) $("agentAssistantQuery").value = button.dataset.agentAssistantExample || "";
        runAgentAssistantSearch(button.dataset.agentAssistantExample || "");
      });
    });
  }
  setAgentAssistantStatus(copy.status);
}

function openAgentAssistant(eventOrContext) {
  const context = typeof eventOrContext === "string" ? eventOrContext : state.view;
  setAgentAssistantContext(context);
  $("agentAssistantModal")?.classList.remove("hidden");
  document.body.classList.add("modal-open");
  renderAgentAssistantResults();
  window.setTimeout(() => $("agentAssistantQuery")?.focus(), 40);
}

function closeAgentAssistant() {
  $("agentAssistantModal")?.classList.add("hidden");
  document.body.classList.remove("modal-open");
}

async function runAgentAssistantSearch(queryValue = $("agentAssistantQuery")?.value || "") {
  const query = String(queryValue || "").trim();
  state.agentAssistant.query = query;
  if (!query) {
    state.agentAssistant.results = [];
    setAgentAssistantStatus(`先输入一句自然语言、题干片段或关键词。`);
    renderAgentAssistantResults();
    return;
  }
  const context = agentAssistantContext();
  state.agentAssistant.loading = true;
  setAgentAssistantStatus("正在语义检索题库...");
  renderAgentAssistantResults();
  try {
    if (context === "p1Corpus") {
      state.agentAssistant.results = await searchP1AgentAssistant(query);
      setAgentAssistantStatus(state.agentAssistant.results.length ? `找到 ${state.agentAssistant.results.length} 个 P1 候选` : agentAssistantCopy().empty);
      return;
    }
    if (context === "p2Corpus") {
      state.agentAssistant.results = await searchP2AgentAssistant(query);
      setAgentAssistantStatus(state.agentAssistant.results.length ? `找到 ${state.agentAssistant.results.length} 个 P2 候选，可跳到题卡或 Brainstorm` : agentAssistantCopy().empty);
      return;
    }
    await runWritingAgentAssistantSearch(query);
  } catch (error) {
    state.agentAssistant.results = [];
    setAgentAssistantStatus(error instanceof Error ? error.message : "查找失败。");
  } finally {
    state.agentAssistant.loading = false;
    renderAgentAssistantResults();
  }
}

async function runWritingAgentAssistantSearch(query) {
  try {
    const search = await api(`/api/agent/writing/prompts/search?q=${encodeURIComponent(query)}&limit=8`);
    state.agentAssistant.results = (search.items || []).map((prompt) => ({
      prompt,
      score: Number(prompt.match_score || 0),
      reasons: prompt.match_reasons || prompt.matched_terms || [],
    }));
    setAgentAssistantStatus(
      state.agentAssistant.results.length
        ? `找到 ${state.agentAssistant.results.length} 个候选 · ${search.search_backend === "local_embedding" ? "本地向量语义重排" : "免费本地语义匹配"}`
        : "没有找到明显匹配。可以换成更短的关键词或粘贴完整题干。"
    );
  } catch (error) {
    const taskTypes = ["task1_academic", "task2"];
    await Promise.all(taskTypes.map((taskType) => loadWritingPrompts(taskType)));
    const prompts = taskTypes.flatMap((taskType) => state.writing.prompts[taskType] || []);
    const matches = prompts
      .map((prompt) => ({
        prompt,
        score: agentAssistantScore(query, [
          prompt.title,
          prompt.source_label,
          prompt.category,
          prompt.prompt,
        ].join(" ")),
        reasons: agentAssistantReasons(query, [prompt.title, prompt.prompt].join(" "), "本地关键词兜底"),
      }))
      .filter((item) => item.score > 0.12)
      .sort((a, b) => b.score - a.score)
      .slice(0, 8);
    state.agentAssistant.results = matches;
    setAgentAssistantStatus(matches.length ? `找到 ${matches.length} 个候选 · 后端不可用，已使用本地语义兜底` : (error instanceof Error ? error.message : "没有找到明显匹配。"));
  }
}

async function searchP1AgentAssistant(query) {
  if (!state.p1Corpus.loaded) await loadP1Corpus();
  return (state.p1Corpus.topics || []).flatMap((topic) => (
    (topic.questions || []).map((item) => {
      const candidateText = [
        topic.label,
        topic.topic,
        item.question,
        item.question_id,
        item.storage_question_id,
        item.legacy_question_id,
        item.corpus_text,
        item.band7_version,
        item.ai_answer,
      ].join(" ");
      return {
        kind: "p1",
        id: item.question_id || item.storage_question_id || item.legacy_question_id,
        questionId: item.question_id || item.storage_question_id || item.legacy_question_id,
        title: item.question,
        question: item.question,
        topicLabel: topic.label || topic.topic || "P1",
        score: agentAssistantScore(query, candidateText),
        match_type: "p1",
        reasons: agentAssistantReasons(query, candidateText, "P1 题库"),
      };
    })
  ))
    .filter((item) => item.questionId && item.score > 0.1)
    .sort((a, b) => b.score - a.score)
    .slice(0, 12);
}

async function searchP2AgentAssistant(query) {
  if (!state.p2Corpus.loaded) await loadP2Corpus();
  const materialResults = (state.p2Corpus.categories || []).flatMap((category) => (
    (category.items || []).map((item) => {
      const candidateText = [
        category.label,
        category.category,
        item.title,
        item.material_text,
        item.linked_question,
        item.p3_follow_up_text,
      ].join(" ");
      return {
        kind: "p2_material",
        id: item.entry_id,
        entryId: item.entry_id,
        title: item.title || "未命名素材",
        categoryLabel: category.label || category.category || "P2 素材",
        hasP3: Boolean(String(item.p3_follow_up_text || "").trim()),
        preview: item.material_text || item.linked_question || item.p3_follow_up_text || "",
        score: agentAssistantScore(query, candidateText),
        match_type: "p2_material",
        reasons: agentAssistantReasons(query, candidateText, "P2 素材"),
      };
    })
  ));
  const cardResults = (state.p2Corpus.currentPart2Cards || []).map((item) => {
    const questionId = p2AgentQuestionId(item);
    const candidateText = [
      item.label,
      item.category,
      item.status,
      p2AgentCueText(item),
      item.brainstorm_idea,
    ].join(" ");
    return {
      kind: "p2_card",
      id: questionId,
      questionId,
      title: p2AgentCueTitle(item),
      categoryLabel: item.label || item.category || "P2 题卡",
      brainstormIdea: String(item.brainstorm_idea || "").trim(),
      prompt: p2AgentCueText(item),
      score: agentAssistantScore(query, candidateText),
      match_type: "p2_card",
      reasons: agentAssistantReasons(query, candidateText, "P2 题卡"),
    };
  });
  return [...cardResults, ...materialResults]
    .filter((item) => item.id && item.score > 0.1)
    .sort((a, b) => b.score - a.score)
    .slice(0, 12);
}

function flashAgentTarget(element) {
  if (!element) return;
  element.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
  element.classList.remove("agent-jump-highlight");
  void element.offsetWidth;
  element.classList.add("agent-jump-highlight");
  window.setTimeout(() => element.classList.remove("agent-jump-highlight"), 2600);
}

async function jumpToAgentAssistantResult(item, action = "") {
  if (!item) return;
  closeAgentAssistant();
  if (item.kind === "p1") {
    switchView("p1Corpus", { force: true });
    if (!state.p1Corpus.loaded) await loadP1Corpus();
    renderP1CorpusTopics();
    window.setTimeout(() => {
      const el = document.querySelector(`[data-p1-corpus-question="${CSS.escape(item.questionId || item.id || "")}"]`);
      flashAgentTarget(el);
    }, 60);
    return;
  }
  if (item.kind === "p2_material") {
    switchView("p2Corpus", { force: true });
    if (!state.p2Corpus.loaded) await loadP2Corpus();
    renderP2CorpusTopics();
    window.setTimeout(() => {
      const el = document.querySelector(`[data-p2-corpus-entry="${CSS.escape(item.entryId || item.id || "")}"]`);
      flashAgentTarget(el?.closest(".p2-material-row") || el);
    }, 60);
    return;
  }
  if (item.kind === "p2_card") {
    switchView("p2Corpus", { force: true });
    if (!state.p2Corpus.loaded) await loadP2Corpus();
    renderP2CorpusTopics();
    if (action === "p2-brainstorm") {
      await openP2BrainstormDialog();
      window.setTimeout(() => {
        const row = document.querySelector(`[data-p2-brainstorm-row="${CSS.escape(item.questionId || item.id || "")}"]`);
        flashAgentTarget(row);
        row?.querySelector("[data-p2-brainstorm-input]")?.focus();
      }, 80);
      return;
    }
    window.setTimeout(() => {
      const el = document.querySelector(`[data-p2-bank-card-id="${CSS.escape(item.questionId || item.id || "")}"]`);
      flashAgentTarget(el);
    }, 60);
  }
}

async function openAgentAssistantPrompt(promptId, taskType) {
  const normalizedTask = taskType === "task1_academic" ? "task1_academic" : "task2";
  const resultPrompt = (state.agentAssistant.results || []).map((item) => item.prompt || item).find((item) => item.id === promptId);
  try {
    await loadWritingPrompts(normalizedTask);
  } catch (_error) {
    if (!resultPrompt) throw _error;
  }
  const cachedPrompt = (state.writing.prompts[normalizedTask] || []).find((item) => item.id === promptId);
  const prompt = cachedPrompt || resultPrompt;
  if (!prompt) {
    setAgentAssistantStatus("这道题刚才没有在本地题库里找到。");
    return;
  }
  closeAgentAssistant();
  state.writing.taskType = normalizedTask;
  switchView("writing", { force: true });
  setWritingPrompt(prompt, true);
}

async function loadAccountProfile() {
  resetAccountProfileLoadingUi();
  await loadAccount();
  renderAccountStatus();
  loadQuestionBankSummary({ force: true })
    .then(renderQuestionBankSelector)
    .catch(renderQuestionBankSelectorError);
  await loadWallet();
}

async function selectQuestionBankScope(scope) {
  const normalized = normalizeQuestionBankScope(scope);
  if (normalized === state.account.questionBankScope && state.account.questionBankSummary?.active_scope === normalized) {
    renderQuestionBankSelector(state.account.questionBankSummary);
    return;
  }
  state.account.questionBankScope = normalized;
  try {
    localStorage.setItem(QUESTION_BANK_SCOPE_STORAGE_KEY, normalized);
  } catch (_error) {
    // Local UI preference only; failing to persist should not block practice.
  }
  clearQuestionBankScopedCaches();
  renderQuestionBankSelector({
    ...(state.account.questionBankSummary || {}),
    active_scope: normalized,
    active_scope_label: "",
  });
  try {
    const summary = await loadQuestionBankSummary({ force: true, scope: normalized });
    renderQuestionBankSelector(summary);
    renderNavigationBankStatus(summary);
    renderP3TopicChips(summary.part2_themes || []);
  } catch (error) {
    renderQuestionBankSelectorError(error);
  }
}

function formatLocalTime(value) {
  return formatCompactDateTime(value);
}

async function fetchWalletPayload(options = {}) {
  const maxAgeMs = Number(options.maxAgeMs ?? 45000);
  const now = Date.now();
  if (!options.force && state.wallet.loaded && now - state.wallet.fetchedAt < maxAgeMs) {
    return state.wallet.payload;
  }
  if (!state.wallet.loadingPromise) {
    state.wallet.loadingPromise = api("/api/billing/wallet", null, options.requestOptions || {})
      .then((wallet) => {
        state.wallet.payload = wallet;
        state.wallet.loaded = true;
        state.wallet.fetchedAt = Date.now();
        return wallet;
      })
      .finally(() => {
        state.wallet.loadingPromise = null;
      });
  }
  return state.wallet.loadingPromise;
}

function renderWalletPayload(wallet) {
  const balance = Number(wallet?.balance_rmb || 0).toFixed(2);
  const threshold = walletAiStartThreshold(wallet);
  const thresholdText = threshold.toFixed(2);
  const allowed = walletAiStartAllowed(wallet);
  const walletStatus = $("walletStatus");
  if (walletStatus) {
    walletStatus.classList.remove("is-loading", "is-error");
    walletStatus.innerHTML = `
      <article class="wallet-balance-card ${allowed ? "is-ready" : "is-blocked"}">
        <div class="wallet-balance-main">
          <span class="wallet-balance-label">${escapeHtml(t("wallet.available"))}</span>
          <strong class="wallet-balance-amount">¥${escapeHtml(balance)}</strong>
        </div>
        <span class="wallet-balance-status ${allowed ? "is-ok" : "is-warn"}">${escapeHtml(allowed ? t("wallet.aiReady") : t("wallet.lowBalance"))}</span>
        <p class="wallet-balance-hint">${escapeHtml(tf(allowed ? "wallet.readyHint" : "wallet.blockedHint", { threshold: thresholdText }))}</p>
      </article>
    `;
  }
  const entries = wallet?.entries || [];
  const ledgerList = $("ledgerList");
  if (ledgerList) ledgerList.innerHTML = entries.length
    ? entries.slice(0, 10).map((entry) => {
        const amount = Number(entry.amount_rmb || 0);
        const label = walletLedgerLabel(entry.entry_type);
        const amountClass = amount > 0 ? "is-positive" : "is-negative";
        return `<div class="settings-list-row account-ledger-row">
          <strong>${escapeHtml(label)}</strong>
          <span class="${amountClass}">¥${amount.toFixed(2)}</span>
          <small>${escapeHtml(formatCompactDateTime(entry.created_at || "") || entry.metadata?.reason || "")}</small>
        </div>`;
      }).join("")
    : `<p class="account-empty-state">${escapeHtml(t("wallet.emptyLedger"))}</p>`;
}

async function loadWallet() {
  try {
    const wallet = await fetchWalletPayload({ force: true });
    renderWalletPayload(wallet);
  } catch (error) {
    const walletStatus = $("walletStatus");
    if (walletStatus) {
      walletStatus.classList.remove("is-loading");
      walletStatus.classList.add("is-error");
      walletStatus.innerHTML = `<article class="wallet-balance-card is-blocked"><div class="wallet-balance-main"><span class="wallet-balance-label">${escapeHtml(t("wallet.loadFailed"))}</span><strong class="wallet-balance-amount">${escapeHtml(error.message)}</strong></div></article>`;
    }
    const ledgerList = $("ledgerList");
    if (ledgerList) ledgerList.innerHTML = `<p class="account-empty-state">${escapeHtml(t("wallet.ledgerUnavailable"))}</p>`;
  }
}

function walletAiStartThreshold(wallet) {
  return Number(wallet?.ai_start_min_balance_rmb ?? 0.3) || 0.3;
}

function walletAiStartAllowed(wallet) {
  if (typeof wallet?.ai_start_allowed === "boolean") return wallet.ai_start_allowed;
  return Number(wallet?.balance_rmb || 0) > walletAiStartThreshold(wallet);
}

function walletLedgerLabel(type) {
  const labels = {
    grant: t("wallet.ledger.grant"),
    recharge: t("wallet.ledger.recharge"),
    reserve: t("wallet.ledger.reserve"),
    release: t("wallet.ledger.release"),
    settle: t("wallet.ledger.settle"),
  };
  return labels[type] || type || t("wallet.ledger.default");
}

function showInsufficientBalanceDialog(threshold = 0.3) {
  document.querySelector(".insufficient-balance-dialog-overlay")?.remove();
  const safeThreshold = Number(threshold || 0.3).toFixed(2);
  const overlay = document.createElement("div");
  overlay.className = "insufficient-balance-dialog-overlay";
  overlay.innerHTML = `
    <article class="insufficient-balance-dialog" role="dialog" aria-modal="true" aria-labelledby="insufficientBalanceTitle">
      <div class="insufficient-balance-icon">¥</div>
      <div class="insufficient-balance-copy">
        <span>${escapeHtml(t("wallet.title"))}</span>
        <h3 id="insufficientBalanceTitle">${escapeHtml(t("wallet.insufficientTitle"))}</h3>
        <p>${escapeHtml(tf("wallet.insufficientBody", { threshold: safeThreshold }))}</p>
      </div>
      <div class="insufficient-balance-actions">
        <button type="button" class="recharge-dialog-cancel" data-balance-dialog-close>${escapeHtml(t("wallet.later"))}</button>
        <button type="button" class="recharge-dialog-confirm" data-balance-dialog-recharge>${escapeHtml(t("wallet.goRecharge"))}</button>
      </div>
    </article>
  `;
  const close = () => overlay.remove();
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay || event.target?.hasAttribute("data-balance-dialog-close")) close();
  });
  overlay.querySelector("[data-balance-dialog-recharge]")?.addEventListener("click", () => {
    close();
    openRechargeDialog();
  });
  document.body.appendChild(overlay);
}

function openRechargeDialog() {
  state.pendingRecharge = 0;
  const dialog = $("rechargeDialog");
  if (dialog) {
    dialog.classList.remove("hidden");
    updateRechargePreview();
  }
}

function closeRechargeDialog() {
  const dialog = $("rechargeDialog");
  if (dialog) {
    dialog.classList.add("hidden");
  }
  state.pendingRecharge = 0;
}

function setRechargeAmount(amount) {
  state.pendingRecharge = amount;
  updateRechargePreview();
  // Update button selection
  document.querySelectorAll("#rechargeDialog .recharge-btn").forEach((btn) => {
    btn.classList.toggle("selected", parseFloat(btn.dataset.amount) === amount);
  });
  // Clear custom input if preset amount selected
  const input = $("rechargeAmount");
  if (input && amount > 0) input.value = "";
}

function updateRechargePreview() {
  const preview = $("rechargePreview");
  const btn = $("confirmRechargeBtn");
  if (preview) {
    preview.textContent = `¥${state.pendingRecharge.toFixed(2)}`;
  }
  if (btn) {
    btn.disabled = state.pendingRecharge <= 0;
  }
}

async function doRecharge() {
  if (state.pendingRecharge <= 0) return;

  const amount = state.pendingRecharge;
  try {
    await api("/api/billing/recharge", { amount_rmb: amount });
    state.wallet.loaded = false;
    state.wallet.payload = null;
    state.wallet.fetchedAt = 0;
    closeRechargeDialog();
    await loadWallet();
  } catch (error) {
    showError(error);
  }
}

async function init() {
  loadUiLanguage();
  loadFontStyle();
  loadDarkMode();
  loadCandidateNames();
  exposeExaminerAudioDiagnostics();
  exposeWasmAudioPreprocessMetrics();
  bindEvents();
  setupReportRails();
  await loadAccount();
  // Keep general audio playback exclusive, but do not let report/player audio interrupt
  // the in-flow examiner prompt once it has started.
  document.addEventListener("play", (e) => {
    if (e.target.tagName !== "AUDIO") return;
    const targetAudio = e.target;

    document.querySelectorAll("audio").forEach((audio) => {
      if (audio === targetAudio || audio.paused) return;
      audio.pause();
    });
  }, true);
  window.addEventListener("popstate", restoreRouteFromLocation);
  loadStoredQuestionBankScope();
  renderQuestionBankSelector();
  const route = requestedRouteState();
  applyRouteState(route);
  const urlView = route.view;
  let savedView = urlView || "home";
  if (!isKnownView(savedView)) savedView = "home";
  switchView(savedView, { force: true, skipPersist: Boolean(urlView), skipUrl: true });
  document.body.classList.remove("app-booting");
  scheduleAuthenticatedPrefetch();
  try {
    const summary = await loadQuestionBankSummary({ force: true });
    renderNavigationBankStatus(summary);
    renderQuestionBankSelector(summary);
    renderP3TopicChips(summary.part2_themes || []);
  } catch (error) {
    text("bankStatus", error.message);
    renderQuestionBankSelectorError(error);
  }
}

init();
