const assert = require("assert");
const fs = require("fs");
const path = require("path");

const appSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "app.js"), "utf8");
const cssSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "styles.css"), "utf8");
const htmlSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "index.html"), "utf8");

assert.match(appSource, /function reportRailLoadingHtml/, "Report rails should have an explicit loading renderer.");
assert.match(appSource, /historyList"\)\.innerHTML\s*=\s*reportRailLoadingHtml\("正在加载口语报告"\)/, "Speaking reports should show rail loading before history resolves.");
assert.match(appSource, /writingReportList"[\s\S]{0,220}reportRailLoadingHtml\("正在加载写作报告"\)/, "Writing reports should show rail loading before reports resolve.");
assert.match(cssSource, /#detailPanel\s*>\s*\.page-center-loading[\s\S]{0,160}height:\s*100%/, "Speaking report loading should fill and center in the detail panel.");
assert.match(cssSource, /\.report-rail-loading-card/, "Report rail loading should have a dedicated visual treatment.");
assert.match(cssSource, /\.speaking-report-rail-shell,\s*[\r\n]+\.writing-report-rail-shell\s*{[\s\S]{0,140}padding:\s*8px 10px 8px 12px/, "Speaking and writing report rails should share the same shell size.");
assert.doesNotMatch(htmlSource, /<div id="writingReportList"[^>]*>还没有写作记录。<\/div>/, "Initial writing report rail must not render an empty state before data loads.");
