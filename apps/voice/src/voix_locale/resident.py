"""Private sequential JSON-lines worker; no socket, transcript log or result cache."""

import json
import re
import signal
import sys
from pathlib import Path

from .cli import delai_depasse, diagnostics_prives
from .fichiers import ErreurVoix
from .moteur import parler, transcrire, valider_langue, valider_texte

MAX_TRAME = 32_000
INACTIVITE_SECONDES = 300


def traiter(requete: object) -> dict:
    if not isinstance(requete, dict):
        raise ErreurVoix("Requête vocale invalide.")
    operation = requete.get("operation")
    attendus = {"id", "operation", "langue", "fichier"}
    if operation == "parler":
        attendus.add("texte")
    if operation not in ("parler", "transcrire") or set(requete) != attendus:
        raise ErreurVoix("Opération vocale invalide.")
    if not isinstance(requete["id"], str) or not re.fullmatch(r"[a-f0-9]{32}", requete["id"]):
        raise ErreurVoix("Identifiant vocal invalide.")
    langue = valider_langue(requete["langue"])
    fichier = requete["fichier"]
    if not isinstance(fichier, str) or len(fichier) > 4096:
        raise ErreurVoix("Chemin vocal invalide.")
    if operation == "parler":
        if not isinstance(requete["texte"], str):
            raise ErreurVoix("Texte vocal invalide.")
        return parler(valider_texte(requete["texte"]), Path(fichier), langue)
    return transcrire(Path(fichier), langue)


def inactif(_signal, _frame):
    raise SystemExit(0)


def main() -> None:
    while True:
        signal.signal(signal.SIGALRM, inactif)
        signal.alarm(INACTIVITE_SECONDES)
        ligne = sys.stdin.buffer.readline(MAX_TRAME + 1)
        signal.alarm(0)
        if not ligne:
            return
        identifiant = None
        try:
            if len(ligne) > MAX_TRAME or not ligne.endswith(b"\n"):
                raise ErreurVoix("Trame vocale invalide.")
            signal.signal(signal.SIGALRM, delai_depasse)
            signal.alarm(120)
            requete = json.loads(ligne)
            if (
                isinstance(requete, dict)
                and isinstance(requete.get("id"), str)
                and re.fullmatch(r"[a-f0-9]{32}", requete["id"])
            ):
                identifiant = requete["id"]
            with diagnostics_prives():
                resultat = traiter(requete)
            del ligne
            message = json.dumps({"id": requete["id"], "resultat": resultat}, ensure_ascii=False)
            del resultat, requete
            if len(message.encode()) > 63_000:
                raise ErreurVoix("Réponse vocale trop longue.")
        except Exception:  # noqa: BLE001 -- Never disclose private input or native errors.
            print(
                json.dumps(
                    {"id": identifiant, "erreur": True} if identifiant else {"erreur": True},
                    separators=(",", ":"),
                ),
                flush=True,
            )
            return
        finally:
            signal.alarm(0)
        print(message, flush=True)
        del message


if __name__ == "__main__":
    main()
