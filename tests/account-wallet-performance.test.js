const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "web", "static", "app.js"), "utf8");

function expectMatch(pattern, message) {
  if (!pattern.test(source)) throw new Error(message);
}

expectMatch(
  /scheduleIdleTask\(\(\) => prefetchWallet\(token\),\s*\d+\)/,
  "Authenticated startup should prefetch the wallet before the account page is opened.",
);
expectMatch(
  /async function loadWallet\(options = \{\}\)/,
  "loadWallet should accept cache and refresh options.",
);
expectMatch(
  /fetchWalletPayload\(\{\s*force:\s*Boolean\(options\.force\),\s*maxAgeMs:/,
  "Account rendering should reuse the wallet cache instead of forcing every request.",
);
if (/async function loadWallet\(\)\s*\{[\s\S]*?fetchWalletPayload\(\{\s*force:\s*true\s*\}\)/.test(source)) {
  throw new Error("loadWallet still forces a network request on every account-page visit.");
}

console.log("account wallet performance contract: ok");
