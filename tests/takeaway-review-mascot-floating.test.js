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
  !/document\.body\.appendChild\(takeawayReviewMascotPortal\)/.test(corpus)
    && !/takeawayReviewMascotPortal/.test(corpus)
    && /wrap\.insertAdjacentHTML\("beforeend",\s*takeawayReviewMascotHtml\(\)\)/.test(corpus),
  "Takeaway review mascot should stay inside the current card instead of becoming a global top layer."
);

assert(
  !/\.takeaway-review-mascot\.is-body-layer/.test(styles)
    && /body\.view-writingTakeawayBook\s+\.language-takeaway-card-wrap\s*>\s*\.takeaway-review-mascot[\s\S]*position:\s*absolute\s*!important/.test(styles)
    && /body\.view-writingTakeawayBook\s+\.language-takeaway-card-wrap\.is-review-current[\s\S]*overflow:\s*visible\s*!important/.test(styles),
  "Writing Takeaway review mascot should be absolutely positioned inside the card and allowed to fly out naturally."
);

assert(
  !/\.takeaway-review-mascot[\s\S]{0,260}z-index:\s*2147483000\s*!important/.test(styles)
    && !/body\.view-writingTakeawayBook\s+\.language-takeaway-card-wrap\.is-review-current[\s\S]{0,160}z-index:\s*9999\s*!important/.test(styles),
  "Takeaway review mascot and its card must not sit above dialogs or global popups."
);

assert(
  !/body\.view-writingTakeawayBook\s+\.language-takeaway-card-wrap\.is-review-current\s+\.language-takeaway-card[\s\S]*padding-right:\s*58px\s*!important/.test(styles)
    && !/padding-right:\s*58px\s*!important/.test(styles),
  "The mascot must not reserve card text space or squeeze the review text."
);

assert(
  !/body\.theme-dark\.font-popular\s+\.nr-spinner span,\s*body\.theme-dark\.font-popular\s+\.analyzing-dots span,\s*body\.theme-dark\.font-popular\s+\.tk-brain-cloud-dots rect/.test(styles)
    && /\.tk-brain-cloud-dots rect\s*\{[\s\S]*animation:\s*tkBrainSeqDot1 1\.5s steps\(1,\s*end\) infinite/.test(styles),
  "The thinking brain dots should keep their sequential animation instead of being pinned visible by theme loading-spinner overrides."
);

console.log("Takeaway review mascot floating checks passed.");
