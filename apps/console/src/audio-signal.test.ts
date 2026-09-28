import { describe, expect, it } from "vitest";
import { inputActivity, pcmSignal, signalPath, waveform } from "./audio-signal";

function chunk(name: string, bytes: Uint8Array) {
  const result = new Uint8Array(8 + bytes.length + (bytes.length % 2));
  result.set(new TextEncoder().encode(name));
  new DataView(result.buffer).setUint32(4, bytes.length, true);
  result.set(bytes, 8);
  return result;
}

function wav(
  samples: Int16Array,
  { channels = 1, rate = 8000, junk = false } = {},
): ArrayBuffer {
  const format = new Uint8Array(16);
  const metadata = new DataView(format.buffer);
  metadata.setUint16(0, 1, true);
  metadata.setUint16(2, channels, true);
  metadata.setUint32(4, rate, true);
  metadata.setUint32(8, rate * channels * 2, true);
  metadata.setUint16(12, channels * 2, true);
  metadata.setUint16(14, 16, true);
  const payload = new Uint8Array(samples.length * 2);
  const pcm = new DataView(payload.buffer);
  samples.forEach((value, index) => pcm.setInt16(index * 2, value, true));
  const chunks = [
    ...(junk ? [chunk("JUNK", new Uint8Array([1, 2, 3]))] : []),
    chunk("fmt ", format),
    chunk("data", payload),
  ];
  const result = new Uint8Array(
    12 + chunks.reduce((size, part) => size + part.length, 0),
  );
  result.set(new TextEncoder().encode("RIFF"));
  new DataView(result.buffer).setUint32(4, result.length - 8, true);
  result.set(new TextEncoder().encode("WAVE"), 8);
  let offset = 12;
  for (const part of chunks) {
    result.set(part, offset);
    offset += part.length;
  }
  return result.buffer;
}

function tone(channels = 1, opposite = false) {
  const samples = new Int16Array(8000 * channels);
  for (let frame = 0; frame < 8000; frame++) {
    for (let channel = 0; channel < channels; channel++) {
      samples[frame * channels + channel] =
        4096 * (opposite && channel === 1 ? -1 : 1);
    }
  }
  return wav(samples, { channels });
}

describe("measured signal energy", () => {
  it("recognizes sustained quiet input but not a single short impulse", () => {
    const read = inputActivity(0);
    const quietVoice = waveform(new Float32Array(480).fill(0.004));
    expect(quietVoice.level).toBeLessThan(0.08);
    expect(read(quietVoice, 100).heard).toBe(false);
    expect(read(waveform(new Float32Array(480)), 150).heard).toBe(false);
    expect(read(quietVoice, 200).heard).toBe(false);
    expect(read(quietVoice, 300)).toMatchObject({
      heard: true,
      available: true,
      silence: 0,
    });
    expect(read(waveform(new Float32Array(480)), 1901)).toMatchObject({
      heard: true,
      available: true,
      silence: 1601,
    });
  });
  it("distinguishes missing measurement from measured silence", () => {
    const read = inputActivity(100);
    expect(read(null, 1000)).toMatchObject({ available: false, heard: false });
    expect(read(undefined, 2000)).toMatchObject({
      available: false,
      heard: false,
    });
    expect(
      read({ level: NaN, samples: new Float32Array() }, 3000),
    ).toMatchObject({ available: false, heard: false });
    expect(read(waveform(new Float32Array(480)), 4000)).toMatchObject({
      available: true,
      heard: false,
    });
  });
  it("distinguishes silence from amplitude without inventing activity", () => {
    const quiet = waveform(new Float32Array(480));
    const sound = waveform(new Float32Array(480).fill(0.125));
    expect(quiet.level).toBe(0);
    expect([...quiet.samples].every((value) => value === 0)).toBe(true);
    expect(sound.level).toBeCloseTo(0.5);
    expect([...sound.samples].every((value) => value > 0)).toBe(true);
  });

  it("measures negative and positive samples equally without changing input", () => {
    const values = new Float32Array(480).fill(-0.125);
    const before = values.slice();
    expect(waveform(values).level).toBeCloseTo(0.5);
    expect(values).toEqual(before);
  });

  it("bounds clipping and produces finite output for empty or invalid samples", () => {
    expect(waveform(new Float32Array(480).fill(2)).level).toBe(1);
    for (const values of [
      new Float32Array(),
      new Float32Array([NaN, Infinity, -Infinity]),
    ]) {
      const result = waveform(values);
      expect(result.level).toBe(0);
      expect([...result.samples].every(Number.isFinite)).toBe(true);
    }
  });
});

describe("bounded local PCM playback analysis", () => {
  it("follows the supplied playback time through silence, sound and end", () => {
    const samples = new Int16Array(8000);
    samples.fill(4096, 2400, 4800);
    const buffer = wav(samples);
    const before = buffer.slice(0);
    const read = pcmSignal(buffer);
    expect(read).not.toBeNull();
    expect(read!(0.1).level).toBe(0);
    expect(read!(0.4).level).toBeCloseTo(0.5);
    expect(read!(0.8).level).toBe(0);
    expect(read!(2).level).toBe(0);
    expect(buffer).toEqual(before);
  });

  it("preserves audible stereo energy when the channels are out of phase", () => {
    const mono = pcmSignal(tone())!(0.5);
    const stereo = pcmSignal(tone(2, true))!(0.5);
    expect(mono.level).toBeGreaterThan(0);
    expect(stereo.level).toBeCloseTo(mono.level);
    expect(stereo.samples).toEqual(mono.samples);
  });

  it("skips an unknown padded RIFF chunk and accepts supported rate limits", () => {
    for (const rate of [8000, 22050, 48000]) {
      const read = pcmSignal(
        wav(new Int16Array(rate).fill(4096), { rate, junk: true }),
      );
      expect(read).not.toBeNull();
      expect(read!(0.5).level).toBeCloseTo(0.5);
    }
  });

  it("keeps time boundary queries finite without reading outside the buffer", () => {
    const read = pcmSignal(tone())!;
    for (const seconds of [-1, NaN, Infinity, -Infinity, Number.MAX_VALUE]) {
      const frame = read(seconds);
      expect(Number.isFinite(frame.level)).toBe(true);
      expect(frame.level).toBeGreaterThanOrEqual(0);
      expect(frame.level).toBeLessThanOrEqual(1);
      expect([...frame.samples].every(Number.isFinite)).toBe(true);
    }
    expect(read(-1)).toEqual(read(0));
  });

  it.each([
    ["wrong container", (v: DataView) => v.setUint8(0, 0)],
    ["wrong audio type", (v: DataView) => v.setUint8(8, 0)],
    ["RIFF overrun", (v: DataView) => v.setUint32(4, v.byteLength, true)],
    ["RIFF header only", (v: DataView) => v.setUint32(4, 4, true)],
    ["truncated format", (v: DataView) => v.setUint32(16, 12, true)],
    ["non-PCM format", (v: DataView) => v.setUint16(20, 3, true)],
    ["no channels", (v: DataView) => v.setUint16(22, 0, true)],
    ["too many channels", (v: DataView) => v.setUint16(22, 3, true)],
    ["unsupported low rate", (v: DataView) => v.setUint32(24, 7999, true)],
    ["unsupported high rate", (v: DataView) => v.setUint32(24, 48001, true)],
    ["misaligned frames", (v: DataView) => v.setUint16(32, 4, true)],
    ["unsupported sample size", (v: DataView) => v.setUint16(34, 8, true)],
    ["data overrun", (v: DataView) => v.setUint32(40, 0xffffffff, true)],
    ["partial PCM sample", (v: DataView) => v.setUint32(40, 1, true)],
    ["missing format", (v: DataView) => v.setUint8(12, 0)],
    ["missing data", (v: DataView) => v.setUint8(36, 0)],
  ] as const)("falls back safely for %s", (_name, corrupt) => {
    const buffer = tone();
    corrupt(new DataView(buffer));
    expect(() => pcmSignal(buffer)).not.toThrow();
    expect(pcmSignal(buffer)).toBeNull();
  });

  it("rejects empty, truncated, oversized and overlong audio before rendering", () => {
    const valid = tone();
    for (const invalid of [
      new ArrayBuffer(0),
      new ArrayBuffer(43),
      valid.slice(0, valid.byteLength - 1),
      wav(new Int16Array()),
      new ArrayBuffer(16 * 1024 * 1024 + 1),
      wav(new Int16Array(8000 * 122)),
    ]) {
      expect(() => pcmSignal(invalid)).not.toThrow();
      expect(pcmSignal(invalid)).toBeNull();
    }
  });
});

describe("signal outline", () => {
  it("provides a stable closed outline for unavailable or silent audio", () => {
    const resting = signalPath();
    expect(resting).toBe(signalPath(new Float32Array(48)));
    expect(resting).toMatch(/^M.*Z$/);
    expect(resting).not.toMatch(/NaN|Infinity/);
    expect(signalPath(new Float32Array(48).fill(0.5))).not.toBe(resting);
  });

  it("keeps malformed signal values inside the visual's radial bounds", () => {
    const values = new Float32Array(48);
    values.set([-100, 100, NaN, Infinity, -Infinity]);
    const path = signalPath(values);
    expect(path).not.toMatch(/NaN|Infinity/);
    for (const match of path.matchAll(/[ML]([\d.-]+),([\d.-]+)/g)) {
      const radius = Math.hypot(Number(match[1]) - 256, Number(match[2]) - 256);
      expect(radius).toBeGreaterThanOrEqual(110.99);
      expect(radius).toBeLessThanOrEqual(145.01);
    }
  });
});

it("recognizes the end of louder speech over a steady low background", () => {
  const read = inputActivity(0);
  const frame = (level: number) => ({ level, samples: new Float32Array(48) });
  read(frame(0.25), 100);
  expect(read(frame(0.25), 200).heard).toBe(true);
  for (let now = 300; now <= 1300; now += 100) {
    expect(read(frame(0.025), now).silence).toBe(now - 200);
  }
  // Isolated clicks must not postpone a reply once sustained speech has ended.
  expect(read(frame(0.1), 1400).silence).toBe(1200);
  expect(read(frame(0.025), 1500).silence).toBe(1300);
});
