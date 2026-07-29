const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "web/static/index.html"), "utf8");

for (const model of ["gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-sol"]) {
  assert.match(
    app,
    new RegExp(`AI_SOURCE_VALUES[\\s\\S]{0,260}"${model}"`),
    `${model} must be accepted as a persisted speaking AI source.`,
  );
  assert.match(
    html,
    new RegExp(`<option value="${model}"[^>]*>${model}</option>`),
    `${model} must be selectable in the speaking AI settings.`,
  );
}

assert.match(
  app,
  /function\s+ensureAiSourceOptions\([\s\S]{0,1300}select\.appendChild\(option\)/,
  "A cached account page without new option elements must be repaired by the current script.",
);

assert.match(
  app,
  /function\s+syncAiSourceControls\([\s\S]{0,400}ensureAiSourceOptions\(aiSourceSelect\)[\s\S]{0,200}aiSourceSelect\.value\s*=\s*aiSource/,
  "Persisted 5.6 values must hydrate the select after old HTML has been cached.",
);

assert.match(
  html,
  /<option value="gpt"[^>]*>gpt-5\.4 mini[^<]*<\/option>/,
  "The default GPT option should name its actual gpt-5.4 mini model.",
);

console.log("Speaking AI model selection checks passed.");
