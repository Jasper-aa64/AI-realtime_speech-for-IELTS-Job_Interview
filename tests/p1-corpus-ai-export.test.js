const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "web/static/corpus-takeaway.js"), "utf8");
const app = fs.readFileSync(path.join(root, "web/static/app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "web/static/index.html"), "utf8");
const styles = fs.readFileSync(path.join(root, "web/static/styles.css"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

const sandbox = { window: {} };
vm.runInNewContext(source, sandbox);
const format = sandbox.window.IELTSCorpusTakeaway?.formatP1TopicCorpusCopyBlock;

assert(typeof format === "function", "P1 corpus should expose a pure topic export formatter.");

const exported = format?.({
  label: "Ambition And Dreams",
  questions: [
    {
      question: "Do you have any ambitions?",
      corpus_text: "Yes. I want to build useful software.",
      last_ai_answer: "Yes, I do. I would love to build software that genuinely helps people.",
    },
  ],
});

assert(exported?.includes("Topic: Ambition And Dreams"), "Topic export should identify the topic.");
assert(exported?.includes("Question: Do you have any ambitions?"), "Topic export should include each question.");
assert(exported?.includes("My answer:\nYes. I want to build useful software."), "Topic export should include the learner corpus.");
assert(!exported?.includes("Band 7 reference:"), "Topic export must exclude Band 7 references so the AI context only contains the learner's maintained answer.");
assert(!exported?.includes("I would love to build software"), "Topic export must not append the generated Band 7 response.");

assert(/id="p1CorpusPodcastBtn"/.test(html), "P1 corpus header should include a podcast prompt button.");
assert(/id="p1CorpusCopyToast"/.test(html), "P1 corpus should include an accessible copy-feedback toast.");
assert(/data-p1-topic-copy=/.test(source), "Each P1 topic card should expose a topic copy action.");
assert(/copyP1TopicForAi\(copyButton\.dataset\.p1TopicCopy/.test(app), "The delegated topic-card handler should copy without opening the card modal.");
assert(/p1CorpusPodcastBtn[\s\S]*copyP1PodcastPrompt\(\)/.test(app), "The header podcast button should copy its dedicated prompt.");
assert(/\.p1-topic-copy-button\s*\{[\s\S]*width:\s*32px[\s\S]*height:\s*32px/.test(styles), "The topic copy icon button should be a fixed square.");
assert(/\.p1-topic-card header\.p1-topic-export-header[\s\S]*justify-content:\s*space-between\s*!important/.test(styles), "P1 topic titles should remain left-aligned while the export controls stay on the right.");
assert(/\.p1-topic-card header\.p1-topic-export-header[\s\S]*\.p1-topic-count[\s\S]*position:\s*static\s*!important/.test(styles), "The copy action and count should share one stable right-side action group.");
assert(
  /\.p1-corpus-copy-toast\s*\{[^}]*top:\s*50%[^}]*transform:\s*translate\(-50%,\s*-50%\)/.test(styles),
  "The podcast copy feedback must stay centered inside the P1 library header instead of covering the first topic card.",
);
assert(/Create an all-English learning podcast/.test(source), "The podcast prompt should explicitly request an all-English learning podcast.");
assert(/idioms[\s\S]*natural spoken expressions/.test(source), "The podcast prompt should ask for idiom and natural-expression teaching.");

console.log("P1 corpus AI export checks passed.");
