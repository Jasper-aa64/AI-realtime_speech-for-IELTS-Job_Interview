class MockRmsAnalyzer {
  constructor(options = {}) {
    this.threshold = typeof options.threshold === "number" ? options.threshold : 0.02;
  }

  update(options = {}) {
    if (typeof options.threshold === "number") {
      this.threshold = options.threshold;
    }
  }

  analyze(channel) {
    let sumSquares = 0;
    let peak = 0;

    for (let index = 0; index < channel.length; index += 1) {
      const sample = channel[index];
      sumSquares += sample * sample;
      peak = Math.max(peak, Math.abs(sample));
    }

    const rms = Math.sqrt(sumSquares / channel.length);
    return {
      analyzer: "mock-rms",
      rms,
      peak,
      speech: rms >= this.threshold,
      threshold: this.threshold,
    };
  }
}

class WasmAudioCorePlaceholderAnalyzer {
  constructor(options = {}) {
    this.threshold = typeof options.threshold === "number" ? options.threshold : 0.02;
  }

  update(options = {}) {
    if (typeof options.threshold === "number") {
      this.threshold = options.threshold;
    }
  }

  analyze(channel) {
    return {
      analyzer: "wasm-audio-core",
      rms: 0,
      peak: 0,
      speech: false,
      threshold: this.threshold,
      error: `audio_core_wasm.js is not generated yet; received ${channel.length} samples.`,
    };
  }
}

function createAnalyzer(analyzerId, options = {}) {
  if (analyzerId === "wasm-audio-core") {
    return new WasmAudioCorePlaceholderAnalyzer(options);
  }
  return new MockRmsAnalyzer(options);
}

class AudioFrameProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const processorOptions = options.processorOptions || {};
    this.analyzerId = processorOptions.analyzerId || "mock-rms";
    this.threshold = typeof processorOptions.threshold === "number" ? processorOptions.threshold : 0.02;
    this.analyzer = createAnalyzer(this.analyzerId, { threshold: this.threshold });
    this.reportEveryFrames = Math.max(1, processorOptions.reportEveryFrames || 8);
    this.frameCount = 0;
    this.speechFrameCount = 0;

    this.port.onmessage = (event) => {
      const data = event.data || {};
      if (typeof data.analyzerId === "string" && data.analyzerId !== this.analyzerId) {
        this.analyzerId = data.analyzerId;
        this.analyzer = createAnalyzer(this.analyzerId, { threshold: this.threshold });
      }
      if (typeof data.threshold === "number") {
        this.threshold = data.threshold;
        this.analyzer.update({ threshold: this.threshold });
      }
    };
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input && input.length > 0 ? input[0] : null;

    if (!channel || channel.length === 0) {
      return true;
    }

    const result = this.analyzer.analyze(channel);
    const speech = Boolean(result.speech);
    this.frameCount += 1;
    if (speech) {
      this.speechFrameCount += 1;
    }

    if (this.frameCount % this.reportEveryFrames === 0) {
      this.port.postMessage({
        type: "audio-frame",
        analyzer: result.analyzer,
        analyzerError: result.error || "",
        frameCount: this.frameCount,
        frameSize: channel.length,
        sampleRate,
        rms: result.rms,
        peak: result.peak,
        threshold: result.threshold,
        speech,
        speechFrameCount: this.speechFrameCount,
      });
    }

    return true;
  }
}

registerProcessor("audio-frame-processor", AudioFrameProcessor);
