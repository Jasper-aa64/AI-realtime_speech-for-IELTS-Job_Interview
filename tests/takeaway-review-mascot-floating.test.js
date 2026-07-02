const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const styles = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");
const corpus = fs.readFileSync(path.join(root, "web/static/corpus-takeaway.js"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

assert(
  /document\.body\.appendChild\(takeawayReviewMascotPortal\)/.test(corpus),
  "Takeaway review mascot should be portaled to body so it can sit above the whole interface."
);

assert(
  /\.takeaway-review-mascot\.is-body-layer[\s\S]*position:\s*fixed\s*!important/.test(styles)
    && /body\.view-writingTakeawayBook\s+\.language-takeaway-card-wrap\s*>\s*\.takeaway-review-mascot[\s\S]*display:\s*block\s*!important/.test(styles)
    && /\.takeaway-review-mascot\.is-body-layer[\s\S]*contain:\s*layout style paint size\s*!important/.test(styles),
  "Writing Takeaway review mascot must be a fixed, size-contained body layer."
);

assert(
  /\.takeaway-review-mascot\.is-body-layer[\s\S]*z-index:\s*2147483000\s*!important/.test(styles)
    && /body\.view-writingTakeawayBook\s+\.language-takeaway-card-wrap\.is-review-current[\s\S]*overflow:\s*visible\s*!important/.test(styles),
  "Current writing review mascot should sit above the whole app and not be clipped."
);

assert(
  /body\.view-writingTakeawayBook\s+\.language-takeaway-card-wrap\.is-review-current\s+\.language-takeaway-card[\s\S]*padding-right:\s*58px\s*!important/.test(styles),
  "Current writing review card should keep the same text width as normal cards when the floating mascot appears."
);

console.log("Takeaway review mascot floating checks passed.");
