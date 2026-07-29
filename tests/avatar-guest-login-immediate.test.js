const assert = require("assert");
const fs = require("fs");
const path = require("path");

const app = fs.readFileSync(path.resolve(__dirname, "../web/static/app.js"), "utf8");

function functionBody(source, name) {
  const declaration = source.indexOf(`const ${name} =`);
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

const accountNavigation = functionBody(app, "handleAccountNavigation");
const guestPromptIndex = accountNavigation.indexOf("promptGuestLogin(");
const profileNavigationIndex = accountNavigation.indexOf('switchView("accountProfile"');

assert.ok(guestPromptIndex >= 0, "A signed-out avatar click must open the login invitation itself.");
assert.ok(
  profileNavigationIndex < 0 || guestPromptIndex < profileNavigationIndex,
  "The guest login invitation must be opened before any potentially slow account-profile navigation.",
);
assert.match(
  accountNavigation,
  /if\s*\(!state\.account\.authenticated\)\s*\{[\s\S]{0,400}promptGuestLogin\(/,
  "The avatar must branch synchronously on the in-memory auth state instead of waiting for account loading.",
);

console.log("Guest avatar login prompt timing checks passed.");
