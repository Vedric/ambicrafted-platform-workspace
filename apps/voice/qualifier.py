"""Repeatable synthetic speech load probe. Run after installation, without network."""

import argparse
import json
import statistics
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

PHRASES = {
    "en": [
        "Hello, I am your local assistant. The platform protects your data.",
        "An alert reports a connection error. I will look for the right runbook.",
        "The diagnosis awaits your approval. No action will run without your permission.",
    ],
    "fr": [
        "Bonjour, je suis votre assistante locale. La plateforme protège vos données.",
        "Une alerte signale une erreur de connexion. Je vais rechercher le guide adapté.",
        "Le diagnostic attend votre validation. Aucune action ne sera exécutée sans votre accord.",
    ],
}


def scenario(numero: int, langue: str = "en") -> dict:
    executable = Path(__file__).parent / ".venv/bin/voix-locale"
    with tempfile.TemporaryDirectory(prefix="ambicrafted-voice-probe-") as temp:
        chemin = Path(temp) / "parole.wav"
        texte = PHRASES[langue][numero % len(PHRASES[langue])]
        debut = time.monotonic()
        synthese = subprocess.run(
            [str(executable), "parler", "--langue", langue, "--sortie", str(chemin)],
            input=texte,
            text=True,
            capture_output=True,
            timeout=130,
            check=False,
        )
        tts_s = time.monotonic() - debut
        if synthese.returncode or synthese.stderr:
            return {"ok": False, "etape": "synthese"}
        debut = time.monotonic()
        transcription = subprocess.run(
            [str(executable), "transcrire", "--langue", langue, str(chemin)],
            text=True,
            capture_output=True,
            timeout=130,
            check=False,
        )
        stt_s = time.monotonic() - debut
        if transcription.returncode or transcription.stderr:
            return {"ok": False, "etape": "transcription"}
        lu = json.loads(transcription.stdout)
        return {
            "ok": bool(lu["texte"].strip()),
            "tts_s": round(tts_s, 3),
            "stt_s": round(stt_s, 3),
            "audio_s": json.loads(synthese.stdout)["duree_s"],
            "phrase": numero % len(PHRASES[langue]),
            "langue": langue,
            "transcription": lu["texte"],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Qualification vocale sur données synthétiques")
    parser.add_argument("--repetitions", type=int, default=6, choices=range(1, 21))
    parser.add_argument("--concurrence", type=int, default=2, choices=(1, 2))
    parser.add_argument("--langue", choices=("en", "fr"), default="en")
    args = parser.parse_args()
    debut = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrence) as pool:
        resultats = list(
            pool.map(lambda numero: scenario(numero, args.langue), range(args.repetitions))
        )
    rapport = {
        "date": datetime.now(UTC).isoformat(),
        "repetitions": args.repetitions,
        "langue": args.langue,
        "concurrence": args.concurrence,
        "temps_total_s": round(time.monotonic() - debut, 3),
        "reussites": sum(resultat["ok"] for resultat in resultats),
        "resultats": resultats,
    }
    for phase in ("tts_s", "stt_s"):
        valeurs = [resultat[phase] for resultat in resultats if resultat["ok"]]
        if valeurs:
            rapport[phase + "_mediane"] = round(statistics.median(valeurs), 3)
            rapport[phase + "_max"] = max(valeurs)
    print(json.dumps(rapport, ensure_ascii=False, indent=2))
    if rapport["reussites"] != args.repetitions:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
