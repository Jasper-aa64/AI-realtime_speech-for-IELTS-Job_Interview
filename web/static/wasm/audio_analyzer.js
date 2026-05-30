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
    status: "ready",
    description: "C++ audio_core compiled to WebAssembly. Run scripts/build_audio_core_wasm.sh first.",
  },
];

export function analyzerById(analyzerId) {
  return ANALYZER_DESCRIPTORS.find((descriptor) => descriptor.id === analyzerId) || ANALYZER_DESCRIPTORS[0];
}

export function analyzerLabel(analyzerId) {
  return analyzerById(analyzerId).label;
}

let wasmAudioCoreModulePromise = null;

function clampSample(sample) {
  return Math.max(-1, Math.min(1, sample));
}

function float32ToInt16(samples) {
  const output = new Int16Array(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    const sample = clampSample(samples[index]);
    output[index] = sample < 0 ? sample * 32768 : sample * 32767;
  }
  return output;
}

class MockRmsAnalyzer {
  constructor(options = {}) {
    this.threshold = typeof options.threshold === "number" ? options.threshold : 0.02;
  }

  update(options = {}) {
    if (typeof options.threshold === "number") {
      this.threshold = options.threshold;
    }
  }

  analyze(samples) {
    let sumSquares = 0;
    let peak = 0;

    for (let index = 0; index < samples.length; index += 1) {
      const sample = samples[index];
      sumSquares += sample * sample;
      peak = Math.max(peak, Math.abs(sample));
    }

    const rms = Math.sqrt(sumSquares / samples.length);
    return {
      analyzer: "mock-rms",
      rms,
      peak,
      speech: rms >= this.threshold,
      threshold: this.threshold,
    };
  }
}

class WasmAudioCoreAnalyzer {
  constructor(module, options = {}) {
    this.module = module;
    this.threshold = typeof options.threshold === "number" ? options.threshold : 0.02;
  }

  static async create(options = {}) {
    if (!wasmAudioCoreModulePromise) {
      wasmAudioCoreModulePromise = import("./audio_core_wasm.js")
        .then((moduleFactory) => moduleFactory.default())
        .catch((error) => {
          wasmAudioCoreModulePromise = null;
          throw error;
        });
    }
    const module = await wasmAudioCoreModulePromise;
    return new WasmAudioCoreAnalyzer(module, options);
  }

  update(options = {}) {
    if (typeof options.threshold === "number") {
      this.threshold = options.threshold;
    }
  }

  analyze(samples) {
    const int16Samples = float32ToInt16(samples);
    const bytes = int16Samples.length * Int16Array.BYTES_PER_ELEMENT;
    const ptr = this.module._malloc(bytes);

    try {
      this.module.HEAP16.set(int16Samples, ptr >> 1);
      const rms = this.module._audio_core_normalized_rms(ptr, int16Samples.length);
      const peak = this.module._audio_core_normalized_peak(ptr, int16Samples.length);
      const speech = this.module._audio_core_is_speech(ptr, int16Samples.length, this.threshold);

      return {
        analyzer: "wasm-audio-core",
        rms,
        peak,
        speech: speech === 1,
        threshold: this.threshold,
      };
    } finally {
      this.module._free(ptr);
    }
  }
}

export async function createAnalyzer(analyzerId, options = {}) {
  if (analyzerId === "wasm-audio-core") {
    return WasmAudioCoreAnalyzer.create(options);
  }
  return new MockRmsAnalyzer(options);
}
