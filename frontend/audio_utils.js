// Pure audio helpers for the mic -> /ws/audio path (ADR-0006). No DOM or Web Audio here, so they
// are covered by tests/unit/test_audio_utils.test.mjs.

export const TARGET_RATE = 16000;
export const TAG_PCM = 0x01; // PCM16LE mono 16 kHz, for transcription
export const TAG_OPUS = 0x02; // MediaRecorder chunk, kept verbatim as the session's audio file

// Stateful box-filter resampler (averages the input samples that fall in each output sample, which
// is a cheap low-pass). State carries across blocks so 128-sample worklet blocks join seamlessly.
export class Resampler {
  constructor(inRate, outRate = TARGET_RATE) {
    this.ratio = inRate / outRate;
    this.phase = 0;
    this.acc = 0;
    this.count = 0;
  }

  process(input) {
    const out = [];
    for (let i = 0; i < input.length; i++) {
      this.acc += input[i];
      this.count += 1;
      this.phase += 1;
      if (this.phase >= this.ratio) {
        out.push(this.acc / this.count);
        this.acc = 0;
        this.count = 0;
        this.phase -= this.ratio;
      }
    }
    return Float32Array.from(out);
  }
}

export function floatToPcm16(floats) {
  const out = new Int16Array(floats.length);
  for (let i = 0; i < floats.length; i++) {
    const s = Math.max(-1, Math.min(1, floats[i]));
    out[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff);
  }
  return out;
}

export function rms(floats) {
  if (floats.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < floats.length; i++) sum += floats[i] * floats[i];
  return Math.sqrt(sum / floats.length);
}

// One tag byte followed by the payload bytes, as a single ArrayBuffer ready for ws.send().
export function tagFrame(tag, payload) {
  const bytes = payload instanceof ArrayBuffer ? new Uint8Array(payload) : new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength);
  const out = new Uint8Array(bytes.length + 1);
  out[0] = tag;
  out.set(bytes, 1);
  return out.buffer;
}

// Collects resampled samples and releases them in fixed-size chunks (about 100 ms), so we send a
// steady trickle of binary frames rather than one per 128-sample audio block.
export class Chunker {
  constructor(chunkSamples = 1600) {
    this.chunkSamples = chunkSamples;
    this.parts = [];
    this.length = 0;
  }

  push(samples) {
    const ready = [];
    this.parts.push(samples);
    this.length += samples.length;
    while (this.length >= this.chunkSamples) {
      const merged = new Float32Array(this.length);
      let offset = 0;
      for (const p of this.parts) {
        merged.set(p, offset);
        offset += p.length;
      }
      ready.push(merged.slice(0, this.chunkSamples));
      const rest = merged.slice(this.chunkSamples);
      this.parts = rest.length ? [rest] : [];
      this.length = rest.length;
    }
    return ready;
  }
}
