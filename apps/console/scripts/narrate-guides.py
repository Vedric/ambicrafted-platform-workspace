"""Prepare local narration, then encode real recordings as H.264/AAC MP4.

Run with the pinned apps/voice environment. Only the committed synthetic guide
script is spoken. Intermediate WAVs/recordings remain in a private directory.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "apps/console/public/guides"


def prepare(evidence):
    evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    evidence.chmod(0o700)
    script = json.loads((Path(__file__).with_name("guide-script.json")).read_text())
    records = {}
    for lesson, languages in script.items():
        for language, texts in languages.items():
            key = f"{lesson}-{language}"
            records[key] = []
            for index, text in enumerate(texts):
                path = evidence / f"{key}-{index}.wav"
                if path.exists():
                    path.unlink()
                # Bound native synthesis and isolate each public caption from the
                # next one. Never inherit gateway keys in a media build process.
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "voix_locale.cli",
                        "parler",
                        "--langue",
                        language,
                        "--sortie",
                        str(path),
                    ],
                    input=text,
                    text=True,
                    check=True,
                    capture_output=True,
                    timeout=130,
                    env={
                        k: v
                        for k, v in os.environ.items()
                        if k
                        in {"HOME", "PATH", "LANG", "VOICE_STATE_DIR", "UV_CACHE_DIR"}
                    },
                )
                with wave.open(str(path)) as wav:
                    duration = wav.getnframes() / wav.getframerate()
                records[key].append(
                    {"file": path.name, "text": text, "duration": duration}
                )
            print(key + ": narration prepared", flush=True)
    (evidence / "narration.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    )


def mux(evidence):
    narration = json.loads((evidence / "narration.json").read_text())
    recordings = json.loads((evidence / "recordings.json").read_text())
    records = []
    for record in recordings:
        key = f"{record['lesson']}-{record['language']}"
        rate = 24000
        duration = max(
            record["duration_seconds"],
            max(
                cue["start"] + part["duration"] + 0.4
                for cue, part in zip(record["cues"], narration[key], strict=True)
            ),
        )
        pcm = np.zeros(round(duration * rate), dtype=np.float32)
        for cue, part in zip(record["cues"], narration[key], strict=True):
            with wave.open(str(evidence / part["file"])) as wav:
                assert wav.getframerate() == rate and wav.getnchannels() == 1
                data = (
                    np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(
                        np.float32
                    )
                    / 32768
                )
            start = round(cue["start"] * rate)
            pcm[start : start + len(data)] = data
        path = OUT / f"{key}.mp4"
        with (
            av.open(str(evidence / f"{key}.webm")) as src,
            av.open(str(path), "w", options={"movflags": "+faststart"}) as dst,
        ):
            original = src.streams.video[0]
            video = dst.add_stream("libx264", rate=30)
            video.width, video.height = original.width, original.height
            video.pix_fmt = "yuv420p"
            video.options = {"crf": "23", "preset": "fast"}
            video.codec_context.thread_count = 2
            audio = dst.add_stream("aac", rate=rate)
            audio.layout = "mono"
            audio.bit_rate = 96000
            cursor = 0
            last = None
            for frame in src.decode(video=0):
                stamp = round(float(frame.time or 0) * 30)
                if last is None:
                    last = frame
                while cursor < stamp:
                    last.pts = cursor
                    last.time_base = Fraction(1, 30)
                    for packet in video.encode(last):
                        dst.mux(packet)
                    cursor += 1
                last = frame
            while last is not None and cursor < round(duration * 30):
                last.pts = cursor
                last.time_base = Fraction(1, 30)
                for packet in video.encode(last):
                    dst.mux(packet)
                cursor += 1
            for packet in video.encode():
                dst.mux(packet)
            for start in range(0, len(pcm), 1024):
                frame = av.AudioFrame.from_ndarray(
                    pcm[start : start + 1024].reshape(1, -1),
                    format="fltp",
                    layout="mono",
                )
                frame.sample_rate = rate
                frame.pts = start
                frame.time_base = Fraction(1, rate)
                for packet in audio.encode(frame):
                    dst.mux(packet)
            for packet in audio.encode():
                dst.mux(packet)
        with av.open(str(path)) as decoded:
            streams = [
                (stream.type, stream.codec_context.name) for stream in decoded.streams
            ]
            assert ("video", "h264") in streams and ("audio", "aac") in streams
            decoded_pcm = np.concatenate(
                [f.to_ndarray().reshape(-1) for f in decoded.decode(audio=0)]
            )
            rms = float(np.sqrt(np.mean(decoded_pcm**2)))
            assert rms > 0.005
        data = path.read_bytes()
        records.append(
            {
                **record,
                "file": path.name,
                "duration_seconds": round(duration, 3),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "video_codec": "h264",
                "audio_codec": "aac",
                "audio_rms": round(rms, 6),
                "narration": narration[key],
            }
        )
        print(key + ": H.264/AAC verified", flush=True)
    (OUT / "provenance.json").write_text(
        json.dumps(
            {
                "source": "Playwright recording of the actual disposable UI, with local AURA narration aligned to caption cues",
                "data": "Synthetic demonstration; analysis and transcription responses in the recorded tutorial are fixtures. No client data.",
                "audio_notice": "../audio/NOTICE.md",
                "clips": records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "mux"])
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    (prepare if args.mode == "prepare" else mux)(args.evidence.resolve())
