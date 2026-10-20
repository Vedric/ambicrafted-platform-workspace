"""Tutorials must remain playable, audible and readable without mandatory captions."""

import hashlib
import json
import re
from pathlib import Path

import av
import numpy as np
import pytest

GUIDES = Path(__file__).resolve().parents[3] / "apps/console/public/guides"
LESSONS = ["first-steps", "voice", "investigation", "documents", "recovery", "observability"]


def seconds(stamp):
    hours, minutes, remaining = stamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(remaining)


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize("lesson", LESSONS)
def test_guide_video_has_decodable_audible_narration(language, lesson):
    records = json.loads((GUIDES / "provenance.json").read_text())["clips"]
    record = next(r for r in records if r["language"] == language and r["lesson"] == lesson)
    path = GUIDES / record["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    assert path.stat().st_size == record["bytes"]
    assert record["captions_burned_in"] is False
    assert record["page_errors"] == []
    assert len(record["cues"]) == len(record["narration"]) == 4
    with av.open(str(path)) as container:
        assert [s.codec_context.name for s in container.streams] == ["h264", "aac"]
        video = container.streams.video[0]
        assert (video.width, video.height) == (1920, 1080)
        assert 60 <= container.duration / av.time_base < 240
        pcm = np.concatenate(
            [frame.to_ndarray().reshape(-1) for frame in container.decode(audio=0)]
        )
        assert np.isfinite(pcm).all()
        rms = float(np.sqrt(np.mean(pcm**2)))
        assert rms > 0.005
        assert abs(rms - record["audio_rms"]) < 0.00001
        # Each chapter must contain real decoded narration, not only one audible intro.
        rate = container.streams.audio[0].rate
        for cue, narration in zip(record["cues"], record["narration"], strict=True):
            assert cue["text"] == narration["text"]
            end = cue["start"] + narration["duration"]
            assert end <= record["duration_seconds"]
            chapter = pcm[round(cue["start"] * rate) : round(end * rate)]
            assert len(chapter) > 10 * rate
            assert float(np.sqrt(np.mean(chapter**2))) > 0.005
    captions = (GUIDES / f"{lesson}-{language}.vtt").read_text()
    assert hashlib.sha256(captions.encode()).hexdigest() == record["caption_sha256"]
    assert captions.startswith("WEBVTT\n\n")
    previous = 0
    texts = []
    for block in captions.strip().split("\n\n")[1:]:
        timing, *lines = block.splitlines()
        match = re.fullmatch(r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})", timing)
        assert match
        start, end = map(seconds, match.groups())
        assert previous <= start < end <= record["duration_seconds"]
        assert 1 <= len(lines) <= 2
        assert all(0 < len(line) <= 44 for line in lines)
        previous = end
        texts.extend(lines)
    assert " ".join(" ".join(texts).split()) == " ".join(
        " ".join(part["text"] for part in record["narration"]).split()
    )
    # Decode an actual video frame as well as checking the stream metadata.
    with av.open(str(path)) as container:
        frame = next(container.decode(video=0))
        assert (frame.width, frame.height) == (1920, 1080)


def test_guide_manifest_covers_exactly_six_bilingual_workflows():
    manifest = json.loads((GUIDES / "provenance.json").read_text())
    identities = [(item["lesson"], item["language"]) for item in manifest["clips"]]
    assert len(identities) == 12
    assert set(identities) == {
        (lesson, language) for lesson in LESSONS for language in ("en", "fr")
    }
    script = GUIDES.parents[1] / "scripts/guide-script.json"
    assert hashlib.sha256(script.read_bytes()).hexdigest() == manifest["script_sha256"]
