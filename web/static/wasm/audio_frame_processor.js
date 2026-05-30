class AudioFrameProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const processorOptions = options.processorOptions || {};
    this.reportEveryFrames = Math.max(1, processorOptions.reportEveryFrames || 8);
    this.frameCount = 0;
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input && input.length > 0 ? input[0] : null;

    if (!channel || channel.length === 0) {
      return true;
    }

    this.frameCount += 1;

    if (this.frameCount % this.reportEveryFrames === 0) {
      const frame = new Float32Array(channel);
      this.port.postMessage({
        type: "audio-frame",
        frameCount: this.frameCount,
        frameSize: channel.length,
        sampleRate,
        samples: frame,
      }, [frame.buffer]);
    }

    return true;
  }
}

registerProcessor("audio-frame-processor", AudioFrameProcessor);
