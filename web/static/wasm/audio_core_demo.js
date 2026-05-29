const output = document.getElementById("output");
const runButton = document.getElementById("runDemo");

function write(message) {
  output.textContent = message;
}

function describeDecision(code) {
  if (code === 1) return "speech";
  if (code === 0) return "silence";
  if (code === -1) return "error";
  return `unexpected(${code})`;
}

function assertCondition(condition, message) {
  if (!condition) {
    throw new Error(`Smoke assertion failed: ${message}`);
  }
}

function allocateInt16(module, values) {
  const bytes = values.length * Int16Array.BYTES_PER_ELEMENT;
  const ptr = module._malloc(bytes);
  module.HEAP16.set(values, ptr >> 1);
  return { ptr, bytes };
}

function readInt16(module, ptr, length) {
  return Array.from(module.HEAP16.subarray(ptr >> 1, (ptr >> 1) + length));
}

async function loadAudioCore() {
  try {
    const moduleFactory = await import("./audio_core_wasm.js");
    return moduleFactory.default();
  } catch (error) {
    throw new Error(
      `Generated WASM module is missing or failed to load.\n\n` +
        `Build it first:\n  scripts/build_audio_core_wasm.sh\n\n` +
        `Original error:\n  ${error.message}`,
    );
  }
}

async function runDemo() {
  runButton.disabled = true;
  write("Loading audio_core_wasm.js...");

  let module;
  let inputPtr = 0;
  let webRtcSilencePtr = 0;
  let invalidFramePtr = 0;
  let trimPtr = 0;
  let resamplePtr = 0;

  try {
    module = await loadAudioCore();

    const silence = new Int16Array(160).fill(0);
    const speech = new Int16Array(320).fill(9000);
    const input = new Int16Array([...silence, ...speech, ...silence]);
    const allocatedInput = allocateInt16(module, input);
    inputPtr = allocatedInput.ptr;

    const rms = module._audio_core_normalized_rms(inputPtr, input.length);
    const peak = module._audio_core_normalized_peak(inputPtr, input.length);
    const speechDecision = module._audio_core_is_speech(inputPtr, input.length, 0.02);

    const webRtcSilence = new Int16Array(320).fill(0);
    const allocatedSilence = allocateInt16(module, webRtcSilence);
    webRtcSilencePtr = allocatedSilence.ptr;
    const webRtcSilenceDecision = module._audio_core_is_speech_webrtc(
      webRtcSilencePtr,
      webRtcSilence.length,
      16000,
      20,
      2,
    );

    const invalidFrame = new Int16Array(100).fill(0);
    const allocatedInvalidFrame = allocateInt16(module, invalidFrame);
    invalidFramePtr = allocatedInvalidFrame.ptr;
    const invalidFrameDecision = module._audio_core_is_speech_webrtc(
      invalidFramePtr,
      invalidFrame.length,
      16000,
      20,
      2,
    );

    trimPtr = module._malloc(input.length * Int16Array.BYTES_PER_ELEMENT);
    const trimmedLength = module._audio_core_trim_silence(
      inputPtr,
      input.length,
      16000,
      10,
      0.02,
      5,
      trimPtr,
      input.length,
    );

    resamplePtr = module._malloc(input.length * 2 * Int16Array.BYTES_PER_ELEMENT);
    const resampledLength = module._audio_core_resample_linear(
      inputPtr,
      input.length,
      16000,
      8000,
      resamplePtr,
      input.length * 2,
    );

    const trimmedPreview = trimmedLength > 0 ? readInt16(module, trimPtr, Math.min(trimmedLength, 12)) : [];

    assertCondition(Number.isFinite(rms) && rms > 0, "RMS should be positive for mixed input");
    assertCondition(Number.isFinite(peak) && peak > 0, "Peak should be positive for mixed input");
    assertCondition(speechDecision === 1, "RMS VAD should classify the mixed frame as speech");
    assertCondition(webRtcSilenceDecision === 0, "WebRTC VAD should classify a 20ms silence frame as silence");
    assertCondition(invalidFrameDecision === -1, "WebRTC VAD should reject an invalid 100-sample frame");
    assertCondition(trimmedLength > 0 && trimmedLength < input.length, "Trim should keep a smaller speech region");
    assertCondition(resampledLength > 0 && resampledLength < input.length, "Downsample should reduce sample count");

    write(
      [
        "WASM smoke test passed.",
        "",
        `Input samples: ${input.length}`,
        `RMS: ${rms.toFixed(4)}`,
        `Peak: ${peak.toFixed(4)}`,
        `RMS VAD decision: ${describeDecision(speechDecision)}`,
        `WebRTC VAD silence decision: ${describeDecision(webRtcSilenceDecision)}`,
        `WebRTC VAD invalid-frame decision: ${describeDecision(invalidFrameDecision)}`,
        `Trimmed samples: ${trimmedLength}`,
        `Trimmed preview: [${trimmedPreview.join(", ")}${trimmedLength > trimmedPreview.length ? ", ..." : ""}]`,
        `Resampled samples: ${resampledLength}`,
        "",
        "Verified:",
        "- audio_core exports loaded through WebAssembly",
        "- RMS fallback VAD still works",
        "- libfvad/WebRTC VAD accepts a valid 20ms frame",
        "- libfvad/WebRTC VAD rejects an invalid frame length",
      ].join("\n"),
    );
  } catch (error) {
    write(error.message);
  } finally {
    if (module) {
      if (inputPtr) module._free(inputPtr);
      if (webRtcSilencePtr) module._free(webRtcSilencePtr);
      if (invalidFramePtr) module._free(invalidFramePtr);
      if (trimPtr) module._free(trimPtr);
      if (resamplePtr) module._free(resamplePtr);
    }
    runButton.disabled = false;
  }
}

runButton.addEventListener("click", runDemo);
