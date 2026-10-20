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
import tempfile
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
    script_path = Path(__file__).with_name("guide-script.json")
    script = json.loads(script_path.read_text())
    expected = {
        f"{lesson}-{language}" for lesson in script for language in ("en", "fr")
    }
    actual = [f"{item['lesson']}-{item['language']}" for item in recordings]
    if (
        len(actual) != len(set(actual))
        or set(actual) != expected
        or set(narration) != expected
    ):
        raise ValueError(
            "All twelve unique bilingual recordings and narrations are required"
        )
    records = []
    for record in recordings:
        key = f"{record['lesson']}-{record['language']}"
        if len(record["cues"]) != 4 or len(narration[key]) != 4:
            raise ValueError("Every walkthrough requires four complete chapters")
        if record["page_errors"] or record.get("captions_burned_in") is not False:
            raise ValueError(
                "Only error-free recordings with optional captions are publishable"
            )
        recording = evidence / f"{key}.webm"
        if hashlib.sha256(recording.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("The source recording changed after capture")
        rate = 24000
        duration = max(
            record["duration_seconds"],
            max(
                cue["start"] + part["duration"] + 0.4
                for cue, part in zip(record["cues"], narration[key], strict=True)
            ),
        )
        if not 60 <= duration < 240:
            raise ValueError(
                "Walkthrough duration must stay between one and four minutes"
            )
        pcm = np.zeros(round(duration * rate), dtype=np.float32)
        for cue, part in zip(record["cues"], narration[key], strict=True):
            with wave.open(str(evidence / part["file"])) as wav:
                if (
                    wav.getframerate() != rate
                    or wav.getnchannels() != 1
                    or wav.getsampwidth() != 2
                ):
                    raise ValueError("Narration must be mono 24 kHz PCM16")
                data = (
                    np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(
                        np.float32
                    )
                    / 32768
                )
            start = round(cue["start"] * rate)
            pcm[start : start + len(data)] = data
        destination = OUT / f"{key}.mp4"
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{key}-", suffix=".mp4", dir=OUT
        )
        os.close(descriptor)
        path = Path(temporary)
        try:
            with (
                av.open(str(evidence / f"{key}.webm")) as src,
                av.open(
                    str(path),
                    "w",
                    # Encoding completes video before audio. Keep its packets
                    # queued until both streams can be interleaved by timestamp.
                    options={"movflags": "+faststart", "max_interleave_delta": "0"},
                ) as dst,
            ):
                original = src.streams.video[0]
                if (original.width, original.height) != (1920, 1080):
                    raise ValueError("Native recordings must be 1920 by 1080 pixels")
                source_fps = str(original.average_rate)
                video = dst.add_stream("libx264", rate=30)
                video.width, video.height = original.width, original.height
                video.pix_fmt = "yuv420p"
                video.options = {"crf": "20", "preset": "fast"}
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
                    (stream.type, stream.codec_context.name)
                    for stream in decoded.streams
                ]
                if streams != [("video", "h264"), ("audio", "aac")]:
                    raise ValueError(
                        "Output must contain exactly one H.264 and one AAC stream"
                    )
                decoded_pcm = np.concatenate(
                    [f.to_ndarray().reshape(-1) for f in decoded.decode(audio=0)]
                )
                rms = float(np.sqrt(np.mean(decoded_pcm**2)))
                if not np.isfinite(decoded_pcm).all() or rms <= 0.005:
                    raise ValueError("Decoded narration is silent or invalid")
            data = path.read_bytes()
            path.chmod(0o644)
            path.replace(destination)
            records.append(
                {
                    **record,
                    "file": destination.name,
                    "duration_seconds": round(duration, 3),
                    "width": 1920,
                    "height": 1080,
                    "source_fps": source_fps,
                    "encoded_fps": 30,
                    "caption_sha256": hashlib.sha256(
                        (OUT / f"{key}.vtt").read_bytes()
                    ).hexdigest(),
                    "recording_sha256": record["sha256"],
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "video_codec": "h264",
                    "audio_codec": "aac",
                    "audio_rms": round(rms, 6),
                    "narration": narration[key],
                }
            )
        finally:
            path.unlink(missing_ok=True)
        print(key + ": H.264/AAC verified", flush=True)
    # Bundle only the chapter offsets, not the provenance or audio metadata.
    chapters = {}
    for record in records:
        chapters.setdefault(record["lesson"], {})[record["language"]] = [
            round(cue["start"], 3) for cue in record["cues"]
        ]
    (ROOT / "apps/console/src/guide-chapters.json").write_text(
        "{\n"
        + ",\n".join(
            f"  {json.dumps(lesson)}: {{\n"
            + ",\n".join(
                f"    {json.dumps(language)}: {json.dumps(starts)}"
                for language, starts in languages.items()
            )
            + "\n  }"
            for lesson, languages in chapters.items()
        )
        + "\n}\n"
    )
    (OUT / "provenance.json").write_text(
        json.dumps(
            {
                "source": "Playwright recording of the actual disposable UI, with local AURA narration aligned to caption cues",
                "data": "Synthetic demonstration; analysis and transcription responses in the recorded tutorial are fixtures. No client data.",
                "audio_notice": "../audio/NOTICE.md",
                "script_sha256": hashlib.sha256(script_path.read_bytes()).hexdigest(),
                "captions": "Optional WebVTT with proportional phrase timing; no burned-in captions.",
                "capture_notice": "Native recording frame rate is preserved in each clip record; the MP4 is resampled to 30 fps.",
                "interleaving": "Audio and video packets ordered by decoding timestamp; faststart index precedes media.",
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
