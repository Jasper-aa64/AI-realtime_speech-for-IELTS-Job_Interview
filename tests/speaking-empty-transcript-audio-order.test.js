const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "web", "static", "app.js"), "utf8");

if (!source.includes('const requiresAudioBeforeComplete = !String(transcriptSnapshot || "").trim() && blob.size > 0;')) {
  throw new Error("Empty browser transcripts must force audio upload before turn completion.");
}

if (!source.includes("turnRequiresSynchronousComplete(turn, localNextTurn) || requiresAudioBeforeComplete")) {
  throw new Error("An empty transcript must use the synchronous completion path.");
}

const awaitedUpload = source.indexOf("await uploadAudioAndAttach();");
const completedTurn = source.indexOf("const completePayload = await completeRequest", awaitedUpload);
if (awaitedUpload < 0 || completedTurn < 0 || awaitedUpload > completedTurn) {
  throw new Error("Audio must finish uploading before /complete can invoke server ASR.");
}

console.log("speaking empty-transcript audio ordering regression tests passed");
