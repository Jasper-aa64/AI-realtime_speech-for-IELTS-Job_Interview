const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const corpus = fs.readFileSync(path.join(root, "web/static/corpus-takeaway.js"), "utf8");

const loginStart = app.indexOf("async function submitLogin");
const loginEnd = app.indexOf("async function submitRegister", loginStart);
assert(loginStart >= 0 && loginEnd > loginStart, "submitLogin should be present.");
const loginSource = app.slice(loginStart, loginEnd);

const registerStart = app.indexOf("async function submitRegister");
const registerEnd = app.indexOf("async function submitPasswordChange", registerStart);
assert(registerStart >= 0 && registerEnd > registerStart, "submitRegister should be present.");
const registerSource = app.slice(registerStart, registerEnd);

assert.match(
  loginSource,
  /state\.account\.user = result\.user \|\| null;[\s\S]{0,180}clearUserScopedCaches\(\);/,
  "Login should clear guest/sample user-scoped data before loading the authenticated account.",
);

assert.match(
  registerSource,
  /state\.account\.user = result\.user \|\| null;[\s\S]{0,180}clearUserScopedCaches\(\);/,
  "Register should clear guest/sample user-scoped data before loading the authenticated account.",
);

assert.match(
  corpus,
  /function takeawayReviewStorageUserKey\(\)[\s\S]{0,260}state\.account\?\.authenticated[\s\S]{0,260}"anonymous"/,
  "Takeaway review localStorage key should be account-scoped so guest sample state cannot leak into a signed-in user.",
);

assert.match(
  corpus,
  /return `\$\{TAKEAWAY_SRS_STORAGE_KEY\}:\$\{kind === "writing" \? "writing" : "language"\}:\$\{takeawayReviewStorageUserKey\(\)\}`;/,
  "Takeaway review storage key should include the scoped user key.",
);

console.log("Takeaway guest/sample isolation checks passed.");
