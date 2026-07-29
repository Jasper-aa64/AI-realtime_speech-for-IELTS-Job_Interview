const assert = require("assert");
const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(path.join(__dirname, "..", "web/static/corpus-takeaway.js"), "utf8");

for (const fn of ["deleteLanguageTakeawayEntry", "deleteWritingTakeawayEntry"]) {
  const start = source.indexOf(`async function ${fn}`);
  assert.notEqual(start, -1, `${fn} must exist.`);
  const body = source.slice(start, start + 2400);
  assert.match(body, /const previousItems =/, `${fn} should snapshot items before deletion.`);
  assert.match(body, /filter\(\(item\) => item\.entry_id !== entryId\)/, `${fn} should remove the item before the network request resolves.`);
  assert.match(body, /catch \(error\)[\s\S]{0,900}state\.[a-zA-Z]+Takeaway\.items = previousItems/, `${fn} should restore the snapshot when deletion fails.`);
}

console.log("Takeaway optimistic-delete checks passed.");
