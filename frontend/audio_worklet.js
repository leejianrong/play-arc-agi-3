// AudioWorklet processor: forwards each 128-sample mono block to the main thread, which does the
// resampling and framing (audio_utils.js). Kept trivial because worklet code can't be unit tested.
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor("capture", CaptureProcessor);
