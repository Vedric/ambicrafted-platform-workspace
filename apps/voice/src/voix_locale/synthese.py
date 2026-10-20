"""Bounded offline multilingual synthesis with one stable speaker per language."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from functools import cache, lru_cache
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from piper.phonemize_espeak import EspeakPhonemizer

from .fichiers import ErreurVoix, ouvrir_prive
from .prononciation import preparer_parole

FREQUENCE_SYNTHESE = 24000
MAX_PHONEMES = 480  # Model limit is 510, plus start/end padding.


def decouper(phonemes: str) -> Iterator[str]:
    """Keep sentences/words together where possible; even an unbroken token is bounded."""
    reste = phonemes.strip()
    while len(reste) > MAX_PHONEMES:
        coupure = reste.rfind(" ", 0, MAX_PHONEMES + 1)
        if coupure < MAX_PHONEMES // 2:
            coupure = MAX_PHONEMES
        yield reste[:coupure]
        reste = reste[coupure:].lstrip()
    if reste:
        yield reste


# eSpeak owns process-global native state. Reinitializing it or switching voices
# concurrently can corrupt that state. Serialize a single instance per process.
_PHONEMES_LOCK = Lock()


@cache
def _phonemiseur() -> EspeakPhonemizer:
    from piper.phonemize_espeak import EspeakPhonemizer

    return EspeakPhonemizer()


def phonemiser(texte: str, langue: str, vocabulaire: dict[str, int]) -> list[str]:
    with _PHONEMES_LOCK:
        return _phonemiser(texte, langue, vocabulaire)


def _phonemiser(texte: str, langue: str, vocabulaire: dict[str, int]) -> list[str]:
    moteur = _phonemiseur()
    oral = preparer_parole(texte, langue, vocabulaire)
    phrases: list[str] = []
    jointure = False
    # preparer_parole removes user-provided brackets before inserting trusted IPA.
    for partie in re.split(r"(\[\[.*?\]\])", oral):
        if partie.startswith("[["):
            if not phrases:
                phrases.append("")
            phrases[-1] += " " + partie[2:-2] + " "
            jointure = True
        elif partie.strip():
            suivantes = [
                "".join(p) for p in moteur.phonemize("en-us" if langue == "en" else "fr", partie)
            ]
            if jointure and suivantes:
                phrases[-1] += suivantes.pop(0)
            phrases.extend(suivantes)
            jointure = False
    resultat: list[str] = []
    for phrase in phrases:
        # Normalize known eSpeak notation to this model's phonetic alphabet.
        phrase = phrase.replace("ɚ", "əɹ").replace("ʲ", "").replace("r", "ɹ")
        # The pinned vocabulary lacks U+0329 (syllabic). Preserve the syllable
        # with an explicit schwa before these two English sonorants only.
        # This is a model-alphabet approximation, not deletion of diacritics.
        if langue == "en":
            phrase = phrase.replace("n\u0329", "ən").replace("l\u0329", "əl")
        phrase = re.sub(r"[-–\n\t]", " ", phrase)
        phrase = re.sub(r"\s+", " ", phrase).strip()
        # Never silently omit a spoken phoneme or truncate a sentence.
        if any(c not in vocabulaire for c in phrase):
            raise ErreurVoix("La phrase contient une prononciation non prise en charge.")
        resultat.extend(decouper(phrase))
    if not resultat:
        raise ErreurVoix("Aucun texte prononçable dans cette phrase.")
    return resultat


@lru_cache(maxsize=1)
def modele_synthese(chemin: Path):
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    return onnxruntime.InferenceSession(
        str(chemin),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )


def generer(texte: str, langue: str, dossier: Path, definition: dict) -> Iterator[bytes]:
    import numpy as np

    with ouvrir_prive(dossier / "phonemes.json", 64000) as fichier:
        vocabulaire = json.load(fichier)["vocab"]
    phrases = phonemiser(texte, langue, vocabulaire)
    with ouvrir_prive(dossier / definition["style"], 1024 * 1024) as fichier:
        styles = np.frombuffer(fichier.read(), dtype="<f4").reshape(-1, 1, 256)
    modele = modele_synthese(dossier / definition["entree"])
    for phrase in phrases:
        ids = [vocabulaire[p] for p in phrase]
        audio = modele.run(
            None,
            {
                "input_ids": np.array([[0, *ids, 0]], dtype=np.int64),
                "style": styles[len(ids)],
                "speed": np.ones(1, dtype=np.float32),
            },
        )[0].reshape(-1)
        if not len(audio) or not np.isfinite(audio).all():
            raise ErreurVoix("Le moteur vocal a renvoyé un signal invalide.")
        if len(audio) > FREQUENCE_SYNTHESE * 120:
            raise ErreurVoix("La synthèse dépasse deux minutes de parole.")
        pic = float(np.max(np.abs(audio)))
        audio = audio * min(1, 0.92 / max(pic, 0.001))
        yield (audio * 32767).astype("<i2").tobytes()
