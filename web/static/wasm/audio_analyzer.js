export const DEFAULT_ANALYZER_ID = "mock-rms";

export const ANALYZER_DESCRIPTORS = [
  {
    id: "mock-rms",
    label: "Mock RMS",
    status: "ready",
    description: "JavaScript RMS/peak analyzer used while validating the AudioWorklet frame path.",
  },
  {
    id: "wasm-audio-core",
    label: "WASM audio_core",
    status: "blocked",
    description: "Reserved for audio_core_wasm.js once Emscripten is available.",
  },
];

export function analyzerById(analyzerId) {
  return ANALYZER_DESCRIPTORS.find((descriptor) => descriptor.id === analyzerId) || ANALYZER_DESCRIPTORS[0];
}

export function analyzerLabel(analyzerId) {
  return analyzerById(analyzerId).label;
}
