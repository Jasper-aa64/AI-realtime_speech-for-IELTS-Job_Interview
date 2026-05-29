class AudioFrameProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const processorOptions = options.processorOptions || {};
    this.threshold = typeof processorOptions.threshold === "number" ? processorOptions.threshold : 0.02;
    this.reportEveryFrames = Math.max(1, processorOptions.reportEveryFrames || 8);
    this.frameCount = 0;
    this.speechFrameCount = 0;

    this.port.onmessage = (event) => {
      if (event.data && typeof event.data.threshold === "number") {
        this.threshold = event.data.threshold;
      }
    };
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input && input.length > 0 ? input[0] : null;

    if (!channel || channel.length === 0) {
      return true;
    }

    let sumSquares = 0;
    let peak = 0;

    for (let index = 0; index < channel.length; index += 1) {
      const sample = channel[index];
      sumSquares += sample * sample;
      peak = Math.max(peak, Math.abs(sample));
    }

    const rms = Math.sqrt(sumSquares / channel.length);
    const speech = rms >= this.threshold;
    this.frameCount += 1;
    if (speech) {
      this.speechFrameCount += 1;
    }

    if (this.frameCount % this.reportEveryFrames === 0) {
      this.port.postMessage({
        type: "audio-frame",
        frameCount: this.frameCount,
        frameSize: channel.length,
        sampleRate,
        rms,
        peak,
        threshold: this.threshold,
        speech,
        speechFrameCount: this.speechFrameCount,
      });
    }

    return true;
  }
}

registerProcessor("audio-frame-processor", AudioFrameProcessor);

