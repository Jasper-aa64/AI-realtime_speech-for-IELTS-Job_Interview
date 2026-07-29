const assert = require("assert");
const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(path.join(__dirname, "..", "web", "static", "corpus-takeaway.js"), "utf8");

assert.match(
  source,
  /chineseDirty:\s*false/,
  "Dictionary state should track whether the learner edited the Chinese gloss.",
);
assert.match(
  source,
  /\$\("languageTakeawayDictDisplay"\)\?\.addEventListener\("input"[\s\S]{0,260}syncLanguageTakeawayDictionaryChineseDraft\(\{ markDirty: true \}\)/,
  "Editing the visible dictionary card should mark the Chinese gloss as user-edited.",
);
assert.match(
  source,
  /chinese_gloss:\s*languageTakeawayChineseForSave\(\),[\s\S]{0,140}replace_existing_gloss:/,
  "Adding a spelling word should tell the backend when an existing gloss may be replaced.",
);
assert.match(
  source,
  /function languageTakeawayDictDisplayPlainText\(\)[\s\S]{0,500}Array\.from\(display\.childNodes \|\| \[\]\)/,
  "Dictionary save extraction should include text nodes appended beside the original sense spans.",
);
assert.match(
  source,
  /result\?\.spelling_word/,
  "Dictionary lookup should consume the authenticated user's existing spelling-word state.",
);
assert.match(
  source,
  /spellingWord\?\.chinese_gloss[\s\S]{0,320}senses\.slice/,
  "An existing spelling word's saved gloss should take precedence over the offline dictionary gloss.",
);
assert.match(
  source,
  /function setLanguageTakeawaySpellingButtonState/,
  "The popup should have one state setter for plus, busy, and existing-word check states.",
);
