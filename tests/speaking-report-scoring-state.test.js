const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

assert.match(
  app,
  /const\s+SPEAKING_REPORT_STATUSES\s*=\s*new Set\(\[\s*"unscored",\s*"scoring",\s*"failed",\s*"ready"\s*\]\)/,
  "Frontend should centralize all persisted speaking report lifecycle statuses.",
);

assert.match(
  app,
  /function\s+speakingReportStatus\(/,
  "Speaking report rendering should resolve status through one backend-status helper.",
);

assert.match(
  app,
  /function\s+unscoredSpeakingReportHtml\(/,
  "Completed attempts without a report should have a distinct unscored detail surface.",
);

assert.match(
  app,
  /attempt\.report_status\s*===\s*"unscored"[\s\S]{0,500}unscoredSpeakingReportHtml/,
  "Speaking report detail should render report_status=unscored distinctly.",
);

assert.match(
  app,
  /data-report-status="ready"/,
  "Ready speaking reports should expose their persisted ready lifecycle state in the detail DOM.",
);

assert.match(
  app,
  /function\s+syncPersistedSpeakingReportTaskPolling\([\s\S]{0,1800}ai_task\?\.id/,
  "History loads should start polling from persisted speaking ai_task IDs.",
);

assert.match(
  app,
  /function\s+reconcileSpeakingHistoryDetailCache\([\s\S]{0,900}cached\.report_status[\s\S]{0,200}cached\.ai_task/,
  "History refreshes should invalidate stale in-memory detail state when backend lifecycle data changes.",
);

assert.doesNotMatch(
  app,
  /function\s+speakingReportScoringLoadingHtml\([^)]*\)\s*\{[\s\S]{0,600}data-regenerate-report/,
  "Scoring detail must never expose a regenerate-report control.",
);

assert.match(
  app,
  /function\s+isSpeakingReportScoringItem\(/,
  "Frontend should centralize report_status=scoring detection.",
);

assert.match(
  app,
  /item\.report_status\s*===\s*"scoring"/,
  "Speaking report list must treat backend scoring reports as active scoring items.",
);

assert.match(
  app,
  /attempt\.report_status\s*===\s*"scoring"[\s\S]{0,220}speakingReportScoringLoadingHtml/,
  "Speaking report detail should render a scoring state for active analysis instead of a failed card.",
);

assert.match(
  app,
  /const\s+isScoring\s*=\s*isSpeakingReportScoringItem\(item\)/,
  "Report manager/list fields should use the shared scoring-state helper.",
);

assert.match(
  app,
  /isScoring\s*\?\s*"评分中"/,
  "Scoring cards should display 评分中.",
);

assert.doesNotMatch(
  app,
  /function\s+speakingReportScoringLoadingHtml\([^)]*\)\s*\{[\s\S]{0,600}data-regenerate-report/,
  "Scoring detail must not expose the regenerate-report button while analysis is active.",
);

console.log("Speaking report scoring-state checks passed.");
