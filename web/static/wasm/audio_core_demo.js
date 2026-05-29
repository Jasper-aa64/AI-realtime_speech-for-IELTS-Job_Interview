const output = document.getElementById("output");
const runButton = document.getElementById("runDemo");

function write(message) {
  output.textContent = message;
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

    write(
      [
        "WASM smoke test passed.",
        "",
        `Input samples: ${input.length}`,
        `RMS: ${rms.toFixed(4)}`,
        `Peak: ${peak.toFixed(4)}`,
        `Speech decision: ${speechDecision === 1 ? "speech" : "silence"}`,
        `Trimmed samples: ${trimmedLength}`,
        `Trimmed preview: [${trimmedPreview.join(", ")}${trimmedLength > trimmedPreview.length ? ", ..." : ""}]`,
        `Resampled samples: ${resampledLength}`,
      ].join("\n"),
    );
  } catch (error) {
    write(error.message);
  } finally {
    if (module) {
      if (inputPtr) module._free(inputPtr);
      if (trimPtr) module._free(trimPtr);
      if (resamplePtr) module._free(resamplePtr);
    }
    runButton.disabled = false;
  }
}

runButton.addEventListener("click", runDemo);

