"""One JSON response per operation; input audio/text never enters diagnostics."""

import argparse
import json
import os
import signal
import sys
from contextlib import contextmanager
from pathlib import Path

from .fichiers import ErreurVoix, installer, verifier_modele
from .moteur import LANGUES, MAX_AUDIO_OCTETS, MAX_AUDIO_SECONDES, MAX_TEXTE, parler, transcrire


@contextmanager
def diagnostics_prives():
    """Native decoders may print input fragments; suppress their output in this process."""
    sys.stdout.flush()
    sys.stderr.flush()
    sauvegardes = [os.dup(1), os.dup(2)]
    silence = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(silence, 1)
        os.dup2(silence, 2)
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        for fd, sauvegarde in zip((1, 2), sauvegardes, strict=True):
            os.dup2(sauvegarde, fd)
            os.close(sauvegarde)
        os.close(silence)


def delai_depasse(_signal, _frame):
    raise ErreurVoix("Le traitement vocal a dépassé le délai autorisé.")


def executer(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Private English and French local voice")
    commandes = parser.add_subparsers(dest="commande", required=True)
    commandes.add_parser("installer", help="Télécharger et vérifier les modèles épinglés")
    statut = commandes.add_parser("statut", help="Vérifier les modèles locaux et leurs empreintes")
    transcription = commandes.add_parser("transcrire", help="Transcrire un fichier audio privé")
    transcription.add_argument("audio", type=Path)
    synthese = commandes.add_parser("parler", help="Synthétiser le texte UTF-8 lu sur stdin")
    synthese.add_argument("--sortie", required=True, type=Path)
    for commande in (statut, transcription, synthese):
        commande.add_argument("--langue", choices=LANGUES, default="en")
    args = parser.parse_args(argv)
    if args.commande == "installer":
        return installer()
    if args.commande == "statut":
        for alias in ("voix-feminine-" + args.langue, "transcription-" + args.langue):
            verifier_modele(alias)
        return {
            "pret": True,
            "local": True,
            "voix": "voix-feminine-" + args.langue,
            "langue": "en-US" if args.langue == "en" else "fr-FR",
            "langues": list(LANGUES),
            "max_audio_octets": MAX_AUDIO_OCTETS,
            "max_audio_secondes": MAX_AUDIO_SECONDES,
            "max_texte_caracteres": MAX_TEXTE,
        }
    if args.commande == "transcrire":
        signal.signal(signal.SIGALRM, delai_depasse)
        signal.alarm(120)
        try:
            with diagnostics_prives():
                return transcrire(args.audio, args.langue)
        finally:
            signal.alarm(0)
    texte = sys.stdin.buffer.read(MAX_TEXTE * 4 + 1)
    if len(texte) > MAX_TEXTE * 4:
        raise ErreurVoix("Le texte dépasse la longueur autorisée.")
    signal.signal(signal.SIGALRM, delai_depasse)
    signal.alarm(120)
    try:
        with diagnostics_prives():
            return parler(texte.decode("utf-8"), args.sortie, args.langue)
    finally:
        signal.alarm(0)


def main() -> None:
    try:
        resultat = executer()
    except ErreurVoix as error:
        print(json.dumps({"erreur": str(error)}, ensure_ascii=False))
        raise SystemExit(2) from None
    except Exception:  # noqa: BLE001 -- Library errors must never disclose customer audio/text.
        print(
            json.dumps(
                {
                    "erreur": "Opération vocale impossible. Vérifiez les fichiers privés, "
                    "le format audio et l’installation des modèles."
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from None
    print(json.dumps(resultat, ensure_ascii=False))


if __name__ == "__main__":
    main()
