// Visual analysis only. Playback continues through the native audio element.
export type SignalFrame = { level: number; samples: Float32Array };
export type SignalReader = () => SignalFrame | null;
export type PcmSignal = (seconds: number) => SignalFrame;
const BINS = 48;

// This is an input-energy detector, not a speech classifier. Quiet but sustained
// microphone input must not be discarded just because the visual is subtle.
export function inputActivity(started: number) {
  let began: number | null = null;
  let lastSound = started;
  let heard = false;
  return (frame: SignalFrame | null | undefined, now: number) => {
    const available = !!frame && Number.isFinite(frame.level);
    const audible = available && frame.level >= 0.012;
    if (audible) {
      began ??= now;
      if (now - began >= 100) heard = true;
      lastSound = now;
    } else if (available) began = null;
    return { available, heard, silence: Math.max(0, now - lastSound) };
  };
}
export function waveform(values: Float32Array): SignalFrame {
  const samples = new Float32Array(BINS);
  let sum = 0;
  for (let bin = 0; bin < BINS; bin++) {
    const start = Math.floor((bin * values.length) / BINS);
    const end = Math.floor(((bin + 1) * values.length) / BINS);
    let energy = 0;
    for (let index = start; index < end; index++) {
      const value = Number.isFinite(values[index]) ? values[index] : 0;
      energy += value * value;
    }
    samples[bin] = Math.min(
      1,
      Math.sqrt(energy / Math.max(1, end - start)) * 4,
    );
    sum += samples[bin] ** 2;
  }
  return { level: Math.sqrt(sum / BINS), samples };
}

// Bounded PCM16 RIFF reader for the local engine's WAV output. Unsupported
// audio falls back to a static visual; it never blocks or changes playback.
export function pcmSignal(buffer: ArrayBuffer): PcmSignal | null {
  if (buffer.byteLength < 44 || buffer.byteLength > 16 * 1024 * 1024)
    return null;
  const view = new DataView(buffer);
  const tag = (offset: number) =>
    String.fromCharCode(...new Uint8Array(buffer, offset, 4));
  if (tag(0) !== "RIFF" || tag(8) !== "WAVE") return null;
  const boundary = view.getUint32(4, true) + 8;
  if (boundary > buffer.byteLength || boundary < 44) return null;
  let channels = 0,
    rate = 0,
    alignment = 0,
    offset = 12,
    data = 0,
    length = 0;
  while (offset + 8 <= boundary) {
    const size = view.getUint32(offset + 4, true);
    const body = offset + 8;
    if (body + size > boundary) return null;
    if (tag(offset) === "fmt ") {
      if (
        size < 16 ||
        view.getUint16(body, true) !== 1 ||
        view.getUint16(body + 14, true) !== 16
      )
        return null;
      channels = view.getUint16(body + 2, true);
      rate = view.getUint32(body + 4, true);
      alignment = view.getUint16(body + 12, true);
    } else if (tag(offset) === "data") {
      data = body;
      length = size;
    }
    offset = body + size + (size % 2);
  }
  if (
    !data ||
    !length ||
    channels < 1 ||
    channels > 2 ||
    rate < 8000 ||
    rate > 48000 ||
    alignment !== channels * 2 ||
    length % alignment ||
    length / alignment / rate > 121
  )
    return null;
  const count = length / alignment;
  const samples = new Float32Array(Math.floor(rate * 0.12));
  return (seconds) => {
    const center = Number.isFinite(seconds)
      ? Math.floor(Math.max(0, seconds) * rate)
      : 0;
    for (let index = 0; index < samples.length; index++) {
      const frame = center + index - Math.floor(samples.length / 2);
      let value = 0;
      if (frame >= 0 && frame < count) {
        // RMS across channels avoids cancelling out an out-of-phase recording.
        for (let channel = 0; channel < channels; channel++) {
          value +=
            (view.getInt16(data + frame * alignment + channel * 2, true) /
              32768) **
            2;
        }
      }
      samples[index] = Math.sqrt(value / channels);
    }
    return waveform(samples);
  };
}

export function signalPath(values?: Float32Array): string {
  const points = Array.from({ length: BINS }, (_, index) => {
    const angle = (index / BINS) * Math.PI * 2;
    const radius = 111 + Math.min(1, Math.max(0, values?.[index] || 0)) * 34;
    return `${index ? "L" : "M"}${(256 + Math.cos(angle) * radius).toFixed(2)},${(256 + Math.sin(angle) * radius).toFixed(2)}`;
  });
  return points.join(" ") + "Z";
}
