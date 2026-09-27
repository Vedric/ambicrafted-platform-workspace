"""Bounded sentence joins: preserve existing silence instead of stacking pauses."""

import numpy as np


def silence_bord(pcm: bytes, frequence: int, *, debut: bool) -> int:
    """Count up to 180 ms of near-silent signed 16-bit mono samples."""
    limite = int(frequence * 0.180)
    valeurs = np.frombuffer(pcm, dtype="<i2")
    bord = valeurs[:limite] if debut else valeurs[-limite:][::-1]
    actifs = np.flatnonzero(np.abs(bord.astype(np.int32)) > 64)
    return int(actifs[0]) if actifs.size else len(bord)


def pause_entre(previous: bytes, suivant: bytes, frequence: int) -> bytes:
    """Ensure a gentle 180 ms sentence boundary; never trim phonemes or stretch audio."""
    existant = silence_bord(previous, frequence, debut=False) + silence_bord(
        suivant, frequence, debut=True
    )
    return bytes(max(0, int(frequence * 0.180) - existant) * 2)
