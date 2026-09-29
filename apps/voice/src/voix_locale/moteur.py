"""CPU speech engines with explicit offline paths and bounded media decoding."""

import os
import wave
from functools import lru_cache
from pathlib import Path

from .fichiers import ErreurVoix, dossier_prive, manifeste, ouvrir_prive, verifier_modele

MAX_AUDIO_OCTETS = 8 * 1024 * 1024
MAX_AUDIO_SECONDES = 90
MAX_TEXTE = 2000
FREQUENCE = 16000
CONTEXTE_AUDIO_MS = 400
FENETRE_RECONNAISSANCE_SECONDES = 30
LANGUES = ("en", "fr")


def valider_langue(langue: str) -> str:
    if langue not in LANGUES:
        raise ErreurVoix("Langue vocale non prise en charge. Choisissez en ou fr.")
    return langue


def hors_ligne() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    # Select oneDNN explicitly: automatic MKL selection changes recognition on a
    # fixed regression signal. This alone does not ensure cross-CPU accuracy.
    # The CLI calls this before importing faster_whisper/CTranslate2.
    os.environ["CT2_USE_MKL"] = "0"


def decoder_audio(path: Path):
    import av
    import numpy as np

    tableaux = []
    total = 0
    with ouvrir_prive(path, MAX_AUDIO_OCTETS) as stream:  # noqa: SIM117
        # The input descriptor prevents URL opening; protocols are denied completely.
        with av.open(stream, mode="r", options={"protocol_whitelist": "none"}) as container:
            if not container.streams.audio:
                raise ErreurVoix("Le fichier ne contient aucune piste audio.")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=FREQUENCE)
            for frame in container.decode(audio=0):
                if frame.sample_rate > 192000 or len(frame.layout.channels) > 8:
                    raise ErreurVoix("Le format audio dépasse les limites autorisées.")
                for mono in resampler.resample(frame):
                    tableau = mono.to_ndarray().flatten()
                    total += tableau.size
                    if total > MAX_AUDIO_SECONDES * FREQUENCE:
                        raise ErreurVoix("L’enregistrement doit durer au plus 90 secondes.")
                    tableaux.append(tableau)
            for mono in resampler.resample(None):
                tableau = mono.to_ndarray().flatten()
                total += tableau.size
                if total > MAX_AUDIO_SECONDES * FREQUENCE:
                    raise ErreurVoix("L’enregistrement doit durer au plus 90 secondes.")
                tableaux.append(tableau)
    if total < FREQUENCE // 5:
        raise ErreurVoix("L’enregistrement doit durer au moins 0,2 seconde.")
    resultat = np.concatenate(tableaux).astype(np.float32) / 32768.0
    return resultat


@lru_cache(maxsize=2)
def modele_reconnaissance(dossier: Path, langue: str):
    """Keep at most two verified recognition models in the private worker."""
    hors_ligne()
    from faster_whisper import WhisperModel

    return WhisperModel(
        str(dossier),
        device="cpu",
        compute_type="float32" if langue == "fr" else "int8",
        cpu_threads=4,
        num_workers=1,
        local_files_only=True,
    )


def transcrire(path: Path, langue: str = "en") -> dict:
    langue = valider_langue(langue)
    hors_ligne()
    import numpy as np

    audio = decoder_audio(path)
    # Preserve a quiet acoustic context before an onset at sample zero. Without it,
    # short utterances can misrecognize their first word even when VAD keeps every sample.
    # Decode and enforce the source duration before adding this fixed context;
    # metadata must describe the submitted recording, not inference padding.
    contexte = FREQUENCE * CONTEXTE_AUDIO_MS // 1000
    audio_inference = np.pad(audio, (contexte, contexte))
    alias = "transcription-" + langue
    # The dedicated English model is qualified for a single native window only.
    # Longer English recordings and all French input retain the baseline path.
    # Count decoded samples including context, never rounded public duration.
    alias_modele = (
        "transcription-en-courte"
        if langue == "en" and len(audio_inference) <= FENETRE_RECONNAISSANCE_SECONDES * FREQUENCE
        else alias
    )
    dossier = verifier_modele(alias_modele)
    # Recheck pinned hashes on every request, even when native weights are warm.
    # French retains FP32; independently qualified English retains INT8.
    model = modele_reconnaissance(dossier, langue)
    segments, _ = model.transcribe(
        audio_inference,
        language=langue,
        beam_size=10,
        vad_filter=True,
        condition_on_previous_text=False,
        temperature=0.0,
        hotwords=(
            "platform, alert, analysis, data, PostgreSQL, Grafana, runbook"
            if langue == "en"
            else "plateforme, alerte, analyse, données, PostgreSQL, Grafana, runbook"
        ),
        vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": CONTEXTE_AUDIO_MS},
    )
    texte = ""
    for segment in segments:
        texte = (texte + " " + segment.text.strip()).strip()
        if len(texte) > 8000:
            raise ErreurVoix("La transcription dépasse la longueur autorisée.")
    return {
        "texte": texte,
        "langue": langue,
        "duree_s": round(len(audio) / FREQUENCE, 3),
        "local": True,
        "alias": alias,
    }


def valider_texte(texte: str) -> str:
    texte = texte.strip()
    if not 1 <= len(texte) <= MAX_TEXTE:
        raise ErreurVoix("La synthèse requiert entre 1 et 2 000 caractères.")
    if any(ord(caractere) < 32 and caractere not in "\n\t\r" for caractere in texte):
        raise ErreurVoix("Le texte contient des caractères de contrôle interdits.")
    return texte


def parler(texte: str, sortie: Path, langue: str = "en") -> dict:
    langue = valider_langue(langue)
    texte = valider_texte(texte)
    dossier_prive(sortie.parent)
    hors_ligne()
    from .prosodie import pause_entre
    from .synthese import FREQUENCE_SYNTHESE, generer

    alias = "voix-feminine-" + langue
    definition = manifeste()["aliases"][alias]
    dossier = verifier_modele(alias)
    fd = os.open(sortie, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    termine = False
    try:
        with os.fdopen(fd, "wb") as stream:
            with wave.open(stream, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(FREQUENCE_SYNTHESE)
                total = 0
                precedent = b""
                for donnees in generer(texte, langue, dossier, definition):
                    pause = (
                        pause_entre(precedent, donnees, FREQUENCE_SYNTHESE) if precedent else b""
                    )
                    total += len(pause) + len(donnees)
                    if total > FREQUENCE_SYNTHESE * 2 * 120:
                        raise ErreurVoix("La synthèse dépasse deux minutes de parole.")
                    wav.writeframes(pause + donnees)
                    precedent = donnees[-int(FREQUENCE_SYNTHESE * 0.180) * 2 :]
            stream.flush()
            os.fsync(stream.fileno())
        with ouvrir_prive(sortie, 32 * 1024 * 1024) as lecture, wave.open(lecture, "rb") as wav:
            duree = wav.getnframes() / wav.getframerate()
            frequence = wav.getframerate()
        termine = True
    finally:
        if not termine:
            sortie.unlink(missing_ok=True)
    return {
        "format": "wav",
        "frequence_hz": frequence,
        "duree_s": round(duree, 3),
        "octets": sortie.stat().st_size,
        "local": True,
        "alias": alias,
        "langue": langue,
    }
