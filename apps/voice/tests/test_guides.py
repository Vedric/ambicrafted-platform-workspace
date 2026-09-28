"""Public tutorial assets must contain verified, audible narration in both languages."""

import hashlib
import json
from pathlib import Path

import av
import numpy as np
import pytest

GUIDES = Path(__file__).resolve().parents[3] / "apps/console/public/guides"


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize("lesson", ["first-steps", "voice", "investigation"])
def test_guide_video_has_decodable_audible_narration(language, lesson):
    records = json.loads((GUIDES / "provenance.json").read_text())["clips"]
    record = next(r for r in records if r["language"] == language and r["lesson"] == lesson)
    path = GUIDES / record["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    assert path.stat().st_size == record["bytes"]
    with av.open(str(path)) as container:
        assert [s.codec_context.name for s in container.streams] == ["h264", "aac"]
        pcm = np.concatenate([frame.to_ndarray().reshape(-1) for frame in container.decode(audio=0)])
        assert np.isfinite(pcm).all()
        rms = float(np.sqrt(np.mean(pcm**2)))
        assert rms > 0.005
        assert abs(rms - record["audio_rms"]) < 0.00001
    assert (GUIDES / f"{lesson}-{language}.vtt").read_text().startswith("WEBVTT\n")
    for cue, narration in zip(record["cues"], record["narration"], strict=True):
        assert cue["text"] == narration["text"]
        assert cue["start"] + narration["duration"] <= record["duration_seconds"]
