const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");

function functionBody(source, name) {
  const declaration = source.indexOf(`function ${name}`);
  assert.notStrictEqual(declaration, -1, `${name} must exist.`);
  const open = source.indexOf("{", declaration);
  let depth = 0;
  for (let index = open; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(open + 1, index);
  }
  assert.fail(`${name} must have a closed function body.`);
}

async function main() {
  let timeoutCallback = null;
  let clearedTimer = null;
  let requestSignal = null;
  const fakeWindow = {
    setTimeout(callback) {
      timeoutCallback = callback;
      return 19;
    },
    clearTimeout(id) {
      clearedTimer = id;
    },
  };
  const stalledApi = (_path, _body, options) => {
    requestSignal = options.signal;
    return new Promise((_resolve, reject) => {
      options.signal.addEventListener("abort", () => {
        const error = new Error("aborted");
        error.name = "AbortError";
        reject(error);
      });
    });
  };
  const execute = new Function(
    "window",
    "api",
    "AbortController",
    `return (async function apiWithAbortTimeout(path, timeoutMs) {${functionBody(app, "apiWithAbortTimeout")}})("/examiner-tts", 3500);`,
  );

  const request = execute(fakeWindow, stalledApi, AbortController).then(
    () => ({ status: "resolved" }),
    (error) => ({ status: "rejected", name: error.name }),
  );
  assert.ok(requestSignal, "The TTS refresh request must receive an AbortSignal.");
  assert.strictEqual(requestSignal.aborted, false);
  assert.strictEqual(typeof timeoutCallback, "function");
  timeoutCallback();
  const outcome = await request;
  assert.deepStrictEqual(outcome, { status: "rejected", name: "AbortError" });
  assert.strictEqual(requestSignal.aborted, true);
  assert.strictEqual(clearedTimer, 19, "The request timeout must be cleared after abort settles the request.");

  console.log("Speaking examiner-TTS refresh timeout checks passed.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
