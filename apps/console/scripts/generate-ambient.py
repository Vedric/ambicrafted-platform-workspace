"""Render Orbital Drift, an original sparse instrumental for this workspace.

Run with: uv run --locked --project apps/voice python apps/console/scripts/generate-ambient.py
No samples, source recordings, model, network, or existing composition are used.
The resulting audio and score are dedicated to CC0-1.0. The voice assets have
separate licenses; see public/audio/NOTICE.md.
"""

import hashlib
import json
from pathlib import Path

import av
import numpy as np

RATE = 48000
DURATION = 96
OUTPUT = Path(__file__).resolve().parents[1] / "public/audio"
# Original voicings: Dmaj9 / Bm11 / Gmaj9 / Aadd9 / Em9 / Bm7 / G6 / Dadd9.
CHORDS = [
    [38, 57, 61, 64, 66],
    [35, 54, 57, 62, 64],
    [31, 54, 57, 59, 62],
    [33, 52, 57, 59, 64],
    [40, 55, 59, 62, 66],
    [35, 54, 57, 62, 66],
    [31, 55, 59, 62, 64],
    [38, 54, 57, 62, 64],
]


def render() -> np.ndarray:
    audio = np.zeros((2, RATE * DURATION), dtype=np.float64)

    def note(
        midi: int, start: float, duration: float, gain: float, pan: float, bell=False
    ):
        count = int(duration * RATE)
        time = np.arange(count) / RATE
        frequency = 440 * 2 ** ((midi - 69) / 12)
        if bell:
            envelope = (1 - np.exp(-time * 15)) * np.exp(-time / 1.65)
            sound = (
                np.sin(2 * np.pi * frequency * time)
                + 0.17 * np.sin(2 * np.pi * frequency * 2 * time)
                + 0.055 * np.sin(2 * np.pi * frequency * 3 * time)
            )
        else:
            attack = np.sin(np.minimum(1, time / 2.8) * np.pi / 2) ** 2
            release = np.sin(np.minimum(1, (duration - time) / 4) * np.pi / 2) ** 2
            envelope = attack * release * (0.94 + 0.06 * np.cos(time * 0.71))
            sound = (
                np.sin(2 * np.pi * frequency * time)
                + 0.23 * np.sin(2 * np.pi * (frequency + 0.11) * time)
                + 0.08 * np.sin(2 * np.pi * frequency * 2 * time)
            )
        mono = gain * envelope * sound
        indices = (np.arange(count) + int(start * RATE)) % audio.shape[1]
        audio[0, indices] += mono * np.cos((pan + 1) * np.pi / 4)
        audio[1, indices] += mono * np.sin((pan + 1) * np.pi / 4)

    for bar, chord in enumerate(CHORDS):
        for voice, pitch in enumerate(chord):
            note(pitch, bar * 12, 17, 0.14 if voice == 0 else 0.065, (voice - 2) / 3)
        # Sparse, varying upper tones, no ostinato copied from a film score.
        for step, offset in enumerate([2.5, 6.75, 10]):
            pitch = chord[[3, 1, 4][(step + bar) % 3]] + 12
            note(pitch, bar * 12 + offset, 6, 0.035, (-0.45, 0.4, 0.1)[step], bell=True)
            note(
                pitch,
                bar * 12 + offset + 0.58,
                5,
                0.009,
                (0.45, -0.4, -0.1)[step],
                bell=True,
            )
    # Gentle loop boundary and bounded master level, before browser attenuation.
    edge = int(RATE * 0.8)
    audio[:, :edge] *= np.linspace(0, 1, edge)
    audio[:, -edge:] *= np.linspace(1, 0, edge)
    audio *= min(0.45 / np.max(np.abs(audio)), 0.11 / np.sqrt(np.mean(audio**2)))
    return audio.astype(np.float32)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    audio = render()
    path = OUTPUT / "orbital-drift.mp3"
    with av.open(str(path), "w", format="mp3") as container:
        stream = container.add_stream("libmp3lame", rate=RATE)
        stream.layout = "stereo"
        stream.bit_rate = 128000
        container.metadata.update(
            title="Orbital Drift", artist="Ambicrafted", copyright="CC0-1.0"
        )
        for start in range(0, audio.shape[1], 1152):
            frame = av.AudioFrame.from_ndarray(
                np.ascontiguousarray(audio[:, start : start + 1152]),
                format="fltp",
                layout="stereo",
            )
            frame.sample_rate = RATE
            frame.pts = start
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    with av.open(str(path)) as decoded:
        samples = np.concatenate(
            [frame.to_ndarray() for frame in decoded.decode(audio=0)], axis=1
        )
    report = {
        "title": "Orbital Drift",
        "license": "CC0-1.0",
        "original_composition": True,
        "external_samples": False,
        "generator": "apps/console/scripts/generate-ambient.py",
        "duration_s": round(samples.shape[1] / RATE, 3),
        "sample_rate": RATE,
        "channels": 2,
        "peak_dbfs": round(20 * float(np.log10(np.max(np.abs(samples)))), 2),
        "rms_dbfs": round(20 * float(np.log10(np.sqrt(np.mean(samples**2)))), 2),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }
    (OUTPUT / "ambient-provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
