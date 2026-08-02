const assert = require("assert");
const fs = require("fs");
const path = require("path");

const appSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "app.js"), "utf8");
const cssSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "styles.css"), "utf8");
const htmlSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "index.html"), "utf8");

assert.match(cssSource, /\.p3-bank-picker-list:has\(\.p3-bank-picker-loading\)[\s\S]{0,220}min-height:\s*min\(560px,\s*calc\(100vh - 220px\)\)/, "P3 bank picker loading state should reserve a full-height body instead of opening as a thin strip.");
assert.match(cssSource, /\.p3-bank-picker-loading\s*{[\s\S]{0,260}min-height:\s*min\(520px,\s*calc\(100vh - 240px\)\)/, "P3 bank picker loading card should be roughly twice as tall and centered within the modal body.");
assert.match(cssSource, /body\.theme-dark:not\(\.font-academic\):not\(\.font-popular\)\s+#practicePanel\s+\.p3-bank-entry\s+\.p3-bank-entry-btn[\s\S]{0,220}background:\s*linear-gradient\(180deg,\s*#14543f 0%,\s*#0d3f31 100%\)[\s\S]{0,120}color:\s*#f7fffb/, "Default dark P3 browse-card button should be deep green with white text.");

assert.match(appSource, /function centeredLoadingHtml/, "Reports should use the shared centered loading renderer.");
assert.match(appSource, /detailPanel"\)\.innerHTML\s*=\s*centeredLoadingHtml\(/, "Speaking report detail should show centered loading before history resolves.");
assert.match(appSource, /writingReportDetail"[\s\S]{0,220}centeredLoadingHtml\(/, "Writing report detail should show centered loading before reports resolve.");
assert.match(htmlSource, /<article id="detailPanel" class="detail-panel">[\s\S]{0,420}<div class="page-center-loading" role="status" aria-live="polite">[\s\S]{0,260}正在加载口语报告/, "Initial speaking report detail should render the centered loading state before JavaScript history loading begins.");
assert.doesNotMatch(htmlSource, /Attempt Details|Select a history item to review the full report\./, "Initial speaking report detail must not expose the legacy English placeholder.");
assert.match(cssSource, /#detailPanel\s*>\s*\.page-center-loading[\s\S]{0,160}height:\s*100%/, "Speaking report loading should fill and center in the detail panel.");
assert.match(cssSource, /\.report-rail-loading-card/, "Report rail loading should have a dedicated visual treatment.");
assert.match(cssSource, /\.report-rail-loading-card\s*{[\s\S]{0,180}height:\s*118px;[\s\S]{0,100}min-height:\s*118px;/, "Speaking and writing rail loaders should match the 118px report-card height.");
assert.match(cssSource, /\.speaking-report-rail-shell,\s*[\r\n]+\.writing-report-rail-shell\s*{[\s\S]{0,140}padding:\s*8px 10px 8px 12px/, "Speaking and writing report rails should share the same shell size.");
assert.doesNotMatch(htmlSource, /<div id="writingReportList"[^>]*>[^<]*<\/div>/, "Initial writing report rail must not render an empty state before data loads.");
assert.match(appSource, /const reportTurns = turns\.map\(\(turn, index\) => \(\{ turn, index \}\)\);/, "Speaking report regeneration must preserve every original turn and its question number.");
assert.match(appSource, /录音已保存，正在补充转写/, "A late-audio turn must remain visible while its transcript is recovered.");
