import assert from "node:assert/strict";
import test from "node:test";

import { Chunker, Resampler, TAG_PCM, floatToPcm16, meterPercent, rms, tagFrame } from "../../frontend/audio_utils.js";

test("resampler 48k -> 16k yields one output per three inputs, averaged", () => {
  const out = new Resampler(48000, 16000).process(Float32Array.from([0.3, 0.3, 0.3, 0.6, 0.6, 0.6]));
  assert.equal(out.length, 2);
  assert.ok(Math.abs(out[0] - 0.3) < 1e-6 && Math.abs(out[1] - 0.6) < 1e-6);
});

test("resampler keeps its phase across block boundaries (44.1k, 128-sample blocks)", () => {
  const r = new Resampler(44100, 16000);
  let total = 0;
  for (let i = 0; i < 345; i++) total += r.process(new Float32Array(128).fill(0.5)).length;
  const expected = Math.floor((345 * 128) / (44100 / 16000));
  assert.ok(Math.abs(total - expected) <= 1, `${total} vs ${expected}`);
});

test("resampler at 16k is the identity", () => {
  const input = Float32Array.from([0.1, -0.2, 0.3]);
  assert.deepEqual(Array.from(new Resampler(16000, 16000).process(input)), Array.from(input));
});

test("floatToPcm16 clamps and scales both polarities", () => {
  assert.deepEqual(Array.from(floatToPcm16(Float32Array.from([1, -1, 2, -2, 0, 0.5]))), [32767, -32768, 32767, -32768, 0, 16384]);
});

test("rms of a constant and of empty input", () => {
  assert.ok(Math.abs(rms(Float32Array.from([0.5, -0.5, 0.5, -0.5])) - 0.5) < 1e-9);
  assert.equal(rms(new Float32Array(0)), 0);
});

test("tagFrame prefixes one tag byte and respects typed-array views", () => {
  const pcm = new Int16Array([1, 2, 3]);
  const frame = new Uint8Array(tagFrame(TAG_PCM, pcm));
  assert.equal(frame[0], TAG_PCM);
  assert.equal(frame.length, 1 + 6);
  const view = new Int16Array(new Int16Array([9, 8, 7, 6]).buffer, 2, 2); // bytes 2..5
  assert.equal(new Uint8Array(tagFrame(1, view)).length, 1 + 4);
});

test("chunker releases fixed-size chunks and keeps the remainder", () => {
  const c = new Chunker(4);
  assert.equal(c.push(new Float32Array(3)).length, 0);
  const out = c.push(new Float32Array(6));
  assert.equal(out.length, 2);
  assert.ok(out.every((chunk) => chunk.length === 4));
  assert.equal(c.length, 1);
});

test("meterPercent is visible for quiet speech, clamped, and zero for silence", () => {
  assert.equal(meterPercent(0), 0);
  assert.ok(meterPercent(0.01) >= 15, "quiet speech should be clearly visible");
  assert.ok(meterPercent(0.05) > meterPercent(0.01));
  assert.equal(meterPercent(1), 100);
  assert.equal(meterPercent(-1), 0);
});
