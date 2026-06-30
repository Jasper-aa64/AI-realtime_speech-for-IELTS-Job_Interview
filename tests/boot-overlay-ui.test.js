const assert = require("assert");
const fs = require("fs");
const path = require("path");

const htmlSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "index.html"), "utf8");
const cssSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "styles.css"), "utf8");
const appearanceSource = fs.readFileSync(path.join(__dirname, "..", "web", "static", "appearance.js"), "utf8");

assert.match(htmlSource, /localStorage\.getItem\("ielts-dark-mode"\)\s*===\s*"1"/, "Boot should read the saved dark-mode preference before CSS paints.");
assert.match(htmlSource, /classList\.add\("theme-dark",\s*"boot-theme-dark"\)/, "Boot should mark the document as dark before body scripts run.");
assert.match(htmlSource, /<style id="boot-critical-style">[\s\S]*body\.app-booting \.shell \{ visibility: hidden; \}/, "Boot should hide the unrendered shell before the main stylesheet loads.");
assert.match(htmlSource, /html\.boot-theme-dark body\.app-booting \{ background: #071119; \}/, "Boot critical CSS should keep hard-refresh dark mode dark before the main CSS loads.");
assert.match(cssSource, /html\.boot-theme-dark body\.app-booting::before/, "Boot overlay should have a first-paint dark selector independent of body.theme-dark.");
assert.match(cssSource, /bootPencilStroke/, "Boot progress should use the pencil-stroke animation.");
assert.match(cssSource, /sketching your practice desk/, "Boot copy should use the pencil-sketch loading treatment.");
assert.doesNotMatch(cssSource, /body\.app-booting::after\s*{[\s\S]{0,260}content:\s*"loading"/, "The pencil-stroke progress pseudo-element should not clip a loading label.");
assert.match(cssSource, /body\.app-booting\.app-boot-ready \.shell\s*{[\s\S]{0,80}visibility:\s*visible/, "Shell should appear behind the overlay during the fade-out.");
assert.match(appearanceSource, /document\.documentElement\.classList\.remove\("boot-theme-dark"\)/, "Normal theme application should clear the boot-only dark class.");
