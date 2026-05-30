import {
  ANALYZER_DESCRIPTORS,
  DEFAULT_ANALYZER_ID,
  analyzerById,
  analyzerLabel,
  createAnalyzer,
} from "./audio_analyzer.js";

const statusEl = document.getElementById("status");
const startButton = document.getElementById("startAudio");
const stopButton = document.getElementById("stopAudio");
const thresholdInput = document.getElementById("threshold");
const analyzerSelect = document.getElementById("analyzer");
const meters = {
  analyzer: document.getElementById("analyzerLabel"),
  sampleRate: document.getElementById("sampleRate"),
  frameSize: document.getElementById("frameSize"),
  frameCount: document.getElementById("frameCount"),
  rms: document.getElementById("rms"),
  peak: document.getElementById("peak"),
  decision: document.getElementById("decision"),
  speechFrames: document.getElementById("speechFrames"),
};

const state = {
  audioContext: null,
  stream: null,
  sourceNode: null,
  workletNode: null,
  analyzer: null,
  analyzerId: DEFAULT_ANALYZER_ID,
  speechFrameCount: 0,
};

function setStatus(message, tone = "neutral") {
  statusEl.textContent = message;
  statusEl.dataset.tone = tone;
}

function formatFloat(value) {
  return Number.isFinite(value) ? value.toFixed(4) : "-";
}

function setRunning(running) {
  startButton.disabled = running;
  stopButton.disabled = !running;
}

function resetMeters() {
  meters.analyzer.textContent = analyzerLabel(currentAnalyzerId());
  meters.sampleRate.textContent = "-";
  meters.frameSize.textContent = "-";
  meters.frameCount.textContent = "0";
  meters.rms.textContent = "0.0000";
  meters.peak.textContent = "0.0000";
  meters.decision.textContent = "idle";
  meters.decision.dataset.speech = "false";
  meters.speechFrames.textContent = "0";
  state.speechFrameCount = 0;
}

function currentThreshold() {
  const value = Number.parseFloat(thresholdInput.value);
  return Number.isFinite(value) ? value : 0.02;
}

function currentAnalyzerId() {
  const descriptor = analyzerById(analyzerSelect.value);
  return descriptor.status === "ready" ? descriptor.id : DEFAULT_ANALYZER_ID;
}

function populateAnalyzerSelect() {
  analyzerSelect.replaceChildren();
  for (const descriptor of ANALYZER_DESCRIPTORS) {
    const option = document.createElement("option");
    option.value = descriptor.id;
    option.textContent = descriptor.label;
    option.disabled = descriptor.status !== "ready";
    option.title = descriptor.description;
    analyzerSelect.appendChild(option);
  }
  analyzerSelect.value = DEFAULT_ANALYZER_ID;
}

function updateAnalyzerStatus() {
  const descriptor = analyzerById(currentAnalyzerId());
  meters.analyzer.textContent = descriptor.label;
  setStatus(descriptor.description, descriptor.status === "ready" ? "neutral" : "error");
}

async function ensureAnalyzer(analyzerId = currentAnalyzerId()) {
  if (state.analyzer && state.analyzerId === analyzerId) {
    state.analyzer.update({ threshold: currentThreshold() });
    return state.analyzer;
  }

  state.analyzer = await createAnalyzer(analyzerId, { threshold: currentThreshold() });
  state.analyzerId = analyzerId;
  return state.analyzer;
}

async function switchAnalyzer() {
  const analyzerId = currentAnalyzerId();
  resetMeters();
  updateAnalyzerStatus();
  try {
    await ensureAnalyzer(analyzerId);
    setStatus(`${analyzerLabel(analyzerId)} analyzer is ready.`, "ok");
  } catch (error) {
    state.analyzer = await createAnalyzer(DEFAULT_ANALYZER_ID, { threshold: currentThreshold() });
    state.analyzerId = DEFAULT_ANALYZER_ID;
    analyzerSelect.value = DEFAULT_ANALYZER_ID;
    resetMeters();
    setStatus(`Falling back to Mock RMS: ${error.message}`, "error");
  }
}

async function handleFrameMessage(event) {
  const data = event.data || {};
  if (data.type !== "audio-frame") {
    return;
  }

  try {
    const analyzer = await ensureAnalyzer();
    const result = analyzer.analyze(data.samples);
    if (result.speech) {
      state.speechFrameCount += 1;
    }

    meters.analyzer.textContent = analyzerLabel(result.analyzer);
    meters.rms.textContent = formatFloat(result.rms);
    meters.peak.textContent = formatFloat(result.peak);
    meters.decision.textContent = result.speech ? "speech" : "silence";
    meters.decision.dataset.speech = result.speech ? "true" : "false";
    meters.speechFrames.textContent = String(state.speechFrameCount);
  } catch (error) {
    setStatus(`Analyzer failed: ${error.message}`, "error");
  }

  meters.sampleRate.textContent = String(data.sampleRate);
  meters.frameSize.textContent = String(data.frameSize);
  meters.frameCount.textContent = String(data.frameCount);
}

async function startAudio() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus("This browser does not expose getUserMedia.", "error");
    return;
  }
  if (!window.AudioWorkletNode) {
    setStatus("This browser does not support AudioWorkletNode.", "error");
    return;
  }

  setRunning(true);
  resetMeters();
  setStatus("Requesting microphone permission...", "neutral");

  try {
    await ensureAnalyzer(currentAnalyzerId());

    const audioContext = new AudioContext();
    await audioContext.audioWorklet.addModule("./audio_frame_processor.js");

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
      video: false,
    });

    const sourceNode = audioContext.createMediaStreamSource(stream);
    const workletNode = new AudioWorkletNode(audioContext, "audio-frame-processor", {
      numberOfInputs: 1,
      numberOfOutputs: 0,
      channelCount: 1,
      processorOptions: {
        reportEveryFrames: 8,
      },
    });

    workletNode.port.onmessage = handleFrameMessage;
    workletNode.onprocessorerror = () => {
      setStatus("AudioWorklet processor failed.", "error");
      stopAudio();
    };

    sourceNode.connect(workletNode);

    state.audioContext = audioContext;
    state.stream = stream;
    state.sourceNode = sourceNode;
    state.workletNode = workletNode;

    setStatus("AudioWorklet is receiving microphone frames.", "ok");
  } catch (error) {
    await stopAudio();
    setStatus(`Failed to start AudioWorklet demo: ${error.message}`, "error");
  } finally {
    setRunning(Boolean(state.audioContext));
  }
}

async function stopAudio() {
  if (state.sourceNode) {
    state.sourceNode.disconnect();
  }
  if (state.workletNode) {
    state.workletNode.port.close();
    state.workletNode.disconnect();
  }
  if (state.stream) {
    for (const track of state.stream.getTracks()) {
      track.stop();
    }
  }
  if (state.audioContext) {
    await state.audioContext.close();
  }

  state.audioContext = null;
  state.stream = null;
  state.sourceNode = null;
  state.workletNode = null;
  setRunning(false);
  setStatus("Stopped. Start again when ready.", "neutral");
}

thresholdInput.addEventListener("input", () => {
  if (state.analyzer) {
    state.analyzer.update({ threshold: currentThreshold() });
  }
});

analyzerSelect.addEventListener("change", switchAnalyzer);

startButton.addEventListener("click", startAudio);
stopButton.addEventListener("click", stopAudio);
window.addEventListener("beforeunload", () => {
  if (state.stream) {
    for (const track of state.stream.getTracks()) {
      track.stop();
    }
  }
});

populateAnalyzerSelect();
resetMeters();
setRunning(false);
