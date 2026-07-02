const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const styles = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

assert(
  /<div class="writing-model-answer-markdown">\$\{renderMarkdown\(item\.model \|\|/.test(app),
  "Writing report AI writing cell should render markdown so **bold** appears."
);

assert(
  /body:not\(\.theme-dark\)\s+:is\([^)]*\.model-answer-markdown[\s\S]*\.p1-corpus-dialog-card \.vditor-reset[\s\S]*\.p1-corpus-dialog-card \.vditor-wysiwyg[\s\S]*\.p1-corpus-dialog-card \.vditor-ir[\s\S]*\)\s+:is\(strong,\s*b,\s*\[data-type="strong"\]\)[\s\S]*color:\s*#2563eb\s*!important/.test(styles),
  "Light mode report/editor bold text should color both saved markdown and live Vditor editing bold text."
);

assert(
  /body:not\(\.theme-dark\)\s+#historyPanel\s+\.turn-report-table\s+:is\(\.p1-p3-content-row > td:nth-child\(3\),\s*\.p2-content-row > td:nth-child\(2\)\)\s+:is\(\.model-answer-markdown\s+strong,\s*strong\)[\s\S]*color:\s*#2563eb\s*!important/.test(styles),
  "Light mode speaking report Band 7 table cells should force bold text blue for P1/P2/P3."
);

assert(
  /body\.theme-dark\s+:is\([^)]*\.model-answer-markdown[\s\S]*\.p1-corpus-dialog-card \.vditor-reset[\s\S]*\.p1-corpus-dialog-card \.vditor-wysiwyg[\s\S]*\.p1-corpus-dialog-card \.vditor-ir[\s\S]*\)\s+:is\(strong,\s*b,\s*\[data-type="strong"\]\)[\s\S]*color:\s*color-mix\(in srgb,\s*var\(--accent\)\s*64%,\s*#ffffff\)\s*!important/.test(styles),
  "Dark mode report/editor bold text should color both saved markdown and live Vditor editing bold text."
);

console.log("Report bold emphasis color checks passed.");
