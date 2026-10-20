"""Local operator CLI using the same authenticated control API as the console."""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
import webbrowser
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Self
from uuid import UUID, uuid4

import httpx

from . import __version__
from .config import Parametres, lire_environnement
from .prerequis import chemin_outils

OPERATIONS = ("verifier", "indexer", "sauvegarder", "tester-restauration")
ACTIFS = {"en_file", "en_cours", "decision"}
ECHECS = {"erreur", "interrompu", "budget_epuise"}
LIMITE_AUDIO = 8 * 1024 * 1024


class NavigateurWSL(webbrowser.BaseBrowser):
    def open(self, url, new=0, autoraise=True):
        executable = shutil.which("cmd.exe")
        if not executable:
            return False
        try:
            resultat = subprocess.run(
                [executable, "/c", "start", "", url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            return resultat.returncode == 0
        except OSError, subprocess.TimeoutExpired:
            return False


@contextmanager
def masquer_sorties_navigateur():
    """Browser launchers may echo URLs, including their one-use ticket."""
    sys.stdout.flush()
    sys.stderr.flush()
    originaux = [os.dup(1), os.dup(2)]
    try:
        with open(os.devnull, "w") as silence:
            os.dup2(silence.fileno(), 1)
            os.dup2(silence.fileno(), 2)
            with redirect_stdout(silence), redirect_stderr(silence):
                yield
    finally:
        for numero, original in zip((1, 2), originaux, strict=True):
            os.dup2(original, numero)
            os.close(original)


class ErreurCLI(Exception):
    """An operator-facing failure without request headers or secret values."""


def identifiant(valeur: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", valeur):
        raise argparse.ArgumentTypeError("Identifiant attendu : 32 caractères hexadécimaux.")
    return valeur


def nom_runbook(valeur: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,115}\.md", valeur):
        raise argparse.ArgumentTypeError(
            "Nom attendu : lettres, chiffres, tirets et extension .md."
        )
    return valeur


def empreinte(valeur: str) -> str:
    if valeur and not re.fullmatch(r"[0-9a-f]{64}", valeur):
        raise argparse.ArgumentTypeError(
            "Empreinte SHA-256 attendue, ou chaîne vide à la création."
        )
    return valeur


def entier_positif(valeur: str) -> int:
    try:
        nombre = int(valeur)
    except ValueError:
        raise argparse.ArgumentTypeError("Un entier positif est attendu.") from None
    if nombre < 1:
        raise argparse.ArgumentTypeError("Un entier positif est attendu.")
    return nombre


def lire_entree(fichier: Path | None, limite: int, *, prive: bool = True) -> str:
    """Bound both file and stdin input; never accept secret content in argv."""
    if fichier:
        fd = os.open(fichier, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "r", encoding="utf-8") as flux:
            info = os.fstat(flux.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ErreurCLI("Le fichier doit être régulier, sans lien symbolique.")
            if prive and (info.st_uid != os.getuid() or info.st_mode & 0o077):
                raise ErreurCLI(
                    "Le fichier confidentiel doit vous appartenir et être en mode 0600."
                )
            valeur = flux.read(limite + 1)
    else:
        if sys.stdin.isatty():
            raise ErreurCLI("Fournir le contenu par stdin ou avec --fichier, jamais en argument.")
        valeur = sys.stdin.read(limite + 1)
    if not valeur.strip() or len(valeur) > limite:
        raise ErreurCLI(f"Le contenu doit comporter entre 1 et {limite} caractères.")
    return valeur


def lire_audio(fichier: Path, *, nature: str = "audio") -> bytes:
    fd = os.open(fichier, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as flux:
        info = os.fstat(flux.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ErreurCLI(f"Le fichier {nature} doit être régulier, sans lien symbolique.")
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ErreurCLI(f"Le fichier {nature} doit vous appartenir et être en mode 0600.")
        contenu = flux.read(LIMITE_AUDIO + 1)
    if not contenu or len(contenu) > LIMITE_AUDIO:
        raise ErreurCLI(f"Le fichier {nature} doit contenir entre 1 octet et 8 Mio.")
    return contenu


class Client:
    def __init__(self, parametres: Parametres):
        self.parametres = parametres
        self.http = httpx.Client(
            base_url=parametres.url,
            headers={"Authorization": "Bearer " + parametres.cle},
            timeout=60,
            trust_env=False,
            follow_redirects=False,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.http.close()

    def appeler(
        self,
        methode: str,
        chemin: str,
        *,
        texte: bool = False,
        binaire: bool = False,
        **options: Any,
    ) -> Any:
        if methode in {"POST", "PUT", "PATCH", "DELETE"} and "json" not in options:
            options["json"] = {}
        try:
            reponse = self.http.request(methode, chemin, **options)
        except httpx.HTTPError:
            raise ErreurCLI(
                "API locale inaccessible. Lancer ./plateforme servir ou vérifier le service utilisateur."
            ) from None
        if reponse.is_error or reponse.is_redirect:
            messages = {
                400: "Requête invalide.",
                401: "Authentification refusée. Vérifier la configuration privée du service.",
                403: "Action refusée.",
                404: "Ressource introuvable.",
                409: "Conflit : actualiser la ressource ou attendre qu'une place se libère.",
                413: "Contenu trop volumineux.",
                422: "Les données ne respectent pas le format attendu.",
                429: "Trop de demandes. Réessayer dans un instant.",
                503: "Un service nécessaire est indisponible.",
            }
            raise ErreurCLI(messages.get(reponse.status_code, "Échec de la requête locale."))
        if binaire:
            if reponse.headers.get("content-type", "").split(";")[0] not in {
                "audio/wav",
                "audio/x-wav",
            }:
                raise ErreurCLI("L'API n'a pas renvoyé un fichier audio WAV.")
            if len(reponse.content) > LIMITE_AUDIO or not reponse.content:
                raise ErreurCLI("La taille du fichier audio reçu est invalide.")
            return reponse.content
        if texte:
            return reponse.text
        try:
            return reponse.json()
        except ValueError:
            raise ErreurCLI("L'API locale a renvoyé une réponse invalide.") from None

    def attendre(self, resultat: dict, delai: int) -> dict:
        fin = time.monotonic() + delai
        while resultat.get("statut") in ACTIFS:
            if time.monotonic() >= fin:
                raise ErreurCLI(
                    "Délai d'attente atteint. L'analyse continue ; consulter analyses voir."
                )
            time.sleep(1)
            resultat = self.appeler("GET", f"/api/analyses/{resultat['id']}")
        return resultat

    def dialogue(self, identifiant: UUID, charge: dict) -> dict:
        """Consume bounded NDJSON; only return a complete, saved conversational turn."""
        try:
            with self.http.stream(
                "POST", f"/api/conversations/{identifiant}/messages", json=charge, timeout=180
            ) as response:
                response.raise_for_status()
                if response.headers.get("content-type", "").split(";")[0] != "application/x-ndjson":
                    raise ValueError("Invalid stream type")
                payload = bytearray()
                for chunk in response.iter_bytes(chunk_size=8192):
                    payload.extend(chunk)
                    if len(payload) > 1_000_000:
                        raise ValueError("Stream too large")
            result, accumulated = None, ""
            for line in payload.splitlines():
                if not line:
                    continue
                if len(line) > 65536 or result is not None:
                    raise ValueError("Invalid stream frame")
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise TypeError("Invalid stream event")
                if event.get("type") == "token" and isinstance(event.get("text"), str):
                    accumulated += event["text"]
                    if len(accumulated) > 6000:
                        raise ValueError("Reply too large")
                elif event.get("type") == "done" and isinstance(event.get("texte"), str):
                    if (
                        not event["texte"].strip()
                        or len(event["texte"]) > 6000
                        or (accumulated and accumulated != event["texte"])
                    ):
                        raise ValueError("Contradictory reply")
                    result = event
                else:
                    raise ValueError("Interrupted reply")
            if result is None:
                raise ValueError("Incomplete reply")
            return {
                **result,
                "conversation_id": str(identifiant),
                "operation_id": charge["operation_id"],
            }
        except httpx.HTTPError, ValueError, TypeError:
            raise ErreurCLI(
                "Dialogue indisponible ou interrompu. Consultez l'historique avant de réessayer ; réutilisez --operation-id "
                + charge["operation_id"]
                + " pour éviter un doublon."
            ) from None


def options_attente(analyseur: argparse.ArgumentParser) -> None:
    analyseur.add_argument("--attendre", action="store_true", help="Attendre un état stable.")
    analyseur.add_argument(
        "--delai", type=entier_positif, default=1200, help="Attente maximale en secondes."
    )


def analyseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ambicrafted — plan de contrôle agentique privé.")
    p.add_argument("--version", action="version", version=__version__)
    commandes = p.add_subparsers(dest="commande", required=True)
    commandes.add_parser("servir", help="Démarrer la console et l'API sur 127.0.0.1.")
    commandes.add_parser("ouvrir", help="Ouvrir une session privée dans le navigateur local.")
    monitoring = commandes.add_parser(
        "observabilite", help="Installer ou exécuter la collecte privée."
    )
    monitoring.add_argument(
        "action", nargs="?", choices=["afficher", "installer", "collecter"], default="afficher"
    )
    commandes.add_parser("statut", aliases=["sante"], help="Afficher la santé réelle des services.")
    commandes.add_parser(
        "preparation", aliases=["doctor"], help="Diagnostiquer les capacités locales mesurées."
    )
    commandes.add_parser(
        "prerequis", help="Vérifier l'isolation Linux et les outils sans démarrer l'API."
    )
    commandes.add_parser("vue-ensemble", help="Afficher les indicateurs de la plateforme.")
    commandes.add_parser("parametres", help="Afficher les paramètres publics, sans secrets.")
    commandes.add_parser("veille", help="Consulter le bulletin technologique public mis en cache.")
    conversations = commandes.add_parser("conversations", help="Historique et dialogue AURA privé.")
    ca = conversations.add_subparsers(dest="action", required=True)
    cl = ca.add_parser("lister")
    cl.add_argument("--page", type=entier_positif, default=1)
    ca.add_parser("creer")
    for action in ("voir", "supprimer", "joindre", "dire"):
        cc = ca.add_parser(action)
        cc.add_argument("identifiant", type=UUID)
        if action == "supprimer":
            cc.add_argument("--confirmer", action="store_true", required=True)
        if action in {"joindre", "dire"}:
            cc.add_argument("--fichier", type=Path, required=action == "joindre")
        if action == "dire":
            cc.add_argument("--langue", choices=("en", "fr"), default="en")
            cc.add_argument("--piece", type=UUID, action="append", default=[])
            cc.add_argument(
                "--operation-id",
                type=UUID,
                help="Identifiant stable à réutiliser lors d'un nouvel essai.",
            )
    memory = commandes.add_parser("memoire", help="Mémoire Neo4j dédiée, périmètre explicite.")
    memory_actions = memory.add_subparsers(dest="action", required=True)
    memory_actions.add_parser("statut")
    memory_actions.add_parser("installer", help="Installer uniquement l'instance Neo4j dédiée.")
    memory_create = memory_actions.add_parser(
        "creer", help="Lire une note JSON privée sur stdin ou fichier."
    )
    memory_create.add_argument("--fichier", type=Path)
    for action in ("lister", "voir", "supprimer"):
        command = memory_actions.add_parser(action)
        command.add_argument("--scope", required=True)
        if action == "lister":
            command.add_argument("--recherche", default="")
        else:
            command.add_argument("identifiant", type=UUID)
    memory_link = memory_actions.add_parser("lier")
    memory_link.add_argument("--scope", required=True)
    memory_link.add_argument("origine", type=UUID)
    memory_link.add_argument("destination", type=UUID)
    mdp = commandes.add_parser("mot-de-passe", help="Configurer le mot de passe de la console.")
    mdp.add_argument("--stdin", action="store_true", help="Lire le mot de passe sur stdin.")
    service = commandes.add_parser(
        "installer-service", help="Installer l'unité systemd utilisateur."
    )
    service.add_argument("--demarrer", action="store_true", help="Activer et démarrer le service.")
    service.add_argument(
        "--remplacer", action="store_true", help="Remplacer notre unité déjà installée."
    )
    analyses = commandes.add_parser("analyses", help="Créer, consulter et décider les analyses.")
    a = analyses.add_subparsers(dest="action", required=True)
    liste = a.add_parser("lister")
    liste.add_argument("--page", type=entier_positif, default=1)
    liste.add_argument("--taille", type=entier_positif, default=25)
    liste.add_argument("--statut", default="")
    creer = a.add_parser("creer")
    creer.add_argument("--titre", default="Nouvelle analyse", help="Titre court, sans secret.")
    creer.add_argument("--fichier", type=Path, help="Alerte UTF-8 privée (0600), sinon stdin.")
    options_attente(creer)
    for nom in ("voir", "approuver", "refuser", "annuler", "attendre", "supprimer", "exporter"):
        sous = a.add_parser(nom)
        sous.add_argument("id", type=identifiant)
        if nom in {"approuver", "refuser"}:
            options_attente(sous)
        if nom == "attendre":
            sous.add_argument("--delai", type=entier_positif, default=1200)
        if nom == "supprimer":
            sous.add_argument(
                "--confirmer",
                action="store_true",
                required=True,
                help="Supprimer explicitement cette analyse et son checkpoint.",
            )
        if nom == "exporter":
            sous.add_argument("--format", choices=("json", "md"), default="json")
            sous.add_argument(
                "--sortie",
                type=Path,
                required=True,
                help="Nouveau fichier privé ; un fichier existant n'est jamais écrasé.",
            )
    operations = commandes.add_parser(
        "operation", help="Lancer une opération d'exploitation bornée."
    )
    operations.add_argument("nom", choices=OPERATIONS)
    options_attente(operations)
    runbooks = commandes.add_parser(
        "runbooks", help="Gérer le corpus Markdown validé par l'humain."
    )
    r = runbooks.add_subparsers(dest="action", required=True)
    r.add_parser("lister")
    lire = r.add_parser("lire")
    lire.add_argument("nom", type=nom_runbook)
    ecrire = r.add_parser("ecrire")
    ecrire.add_argument("nom", type=nom_runbook)
    ecrire.add_argument("--fichier", type=Path, help="Markdown UTF-8, sinon stdin.")
    ecrire.add_argument(
        "--empreinte",
        type=empreinte,
        required=True,
        help="Empreinte de la version lue, ou chaîne vide pour créer.",
    )
    recherche = commandes.add_parser(
        "recherche", help="Rechercher avec une requête reçue sur stdin."
    )
    recherche.add_argument("--mode", choices=("texte", "semantique"), default="texte")
    voix = commandes.add_parser("voix", help="Synthèse et transcription vocales locales.")
    v = voix.add_subparsers(dest="action", required=True)
    statut_voix = v.add_parser(
        "statut", help="Vérifier la disponibilité des services vocaux locaux."
    )
    parler = v.add_parser("parler", help="Synthétiser du texte en fichier WAV privé.")
    parler.add_argument(
        "--fichier", type=Path, help="Texte privé UTF-8, sinon stdin (2 000 caractères)."
    )
    parler.add_argument("--sortie", type=Path, required=True, help="Nouveau fichier WAV privé.")
    transcrire = v.add_parser(
        "transcrire", help="Transcrire un audio privé de 8 Mio et 90 s maximum."
    )
    transcrire.add_argument("fichier", type=Path, help="Fichier audio privé (0600).")
    for commande_voix in (statut_voix, parler, transcrire):
        commande_voix.add_argument("--langue", choices=("en", "fr"), default="en")
    return p


def ecrire_export(chemin: Path, contenu: str | bytes) -> dict:
    octets = contenu.encode("utf-8") if isinstance(contenu, str) else contenu
    fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as fichier:
        fichier.write(octets)
        fichier.flush()
        os.fsync(fichier.fileno())
    return {"exporte": str(chemin), "octets": len(octets)}


def argument_systemd(valeur: str, *, commande: bool = False) -> str:
    # ExecStart does not use a shell; systemd specifiers and environment expansion still apply.
    if any(caractere in valeur for caractere in "\n\r\x00"):
        raise ErreurCLI("Chemin non pris en charge pour l'installation du service.")
    valeur = valeur.replace("$", "$$") if commande else valeur
    return '"' + valeur.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def repertoire_systemd(valeur: str) -> str:
    # WorkingDirectory consumes the whole assignment and does not remove quotes.
    if not valeur.startswith("/") or any(c in valeur for c in "\n\r\x00\\"):
        raise ErreurCLI("Chemin non pris en charge pour l'installation du service.")
    return valeur.replace("%", "%%")


def verifier_prerequis(p: Parametres) -> dict:
    valeurs = lire_environnement(p.racine)
    commande = [sys.executable, "-m", "plateforme.prerequis"]
    if os.environ.get("PLATFORM_BACKUP_EXPORT_DIR") or valeurs.get("PLATFORM_BACKUP_EXPORT_DIR"):
        commande.append("--avec-export")
    try:
        result = subprocess.run(
            commande,
            capture_output=True,
            timeout=20,
            check=False,
            env={"HOME": str(Path.home()), "PATH": chemin_outils(), "LANG": "C.UTF-8"},
        )
        data = json.loads(result.stdout)
        if result.returncode or not isinstance(data, dict) or data.get("ok") is not True:
            raise ValueError("Host prerequisites unavailable")
        return data
    except OSError, subprocess.SubprocessError, ValueError, TypeError:
        raise ErreurCLI(
            "Prérequis Linux non satisfaits : vérifier bubblewrap, libseccomp2, les namespaces "
            "et age si l'export est configuré. Voir docs/HOST-TOOLS.md ; aucun mode non isolé."
        ) from None


def installer_service(p: Parametres, *, demarrer: bool, remplacer: bool) -> dict:
    if not shutil.which("systemctl"):
        raise ErreurCLI("systemd utilisateur est nécessaire pour installer le service.")
    if not (p.web / "index.html").is_file():
        raise ErreurCLI(
            "Construire d'abord la console : cd apps/console && npm ci && npm run build."
        )
    if not (p.racine / "agents/sre-agent/.venv/bin/sre-agent-graph").is_file():
        raise ErreurCLI(
            "Installer le moteur : uv sync --locked --all-extras --project agents/sre-agent."
        )
    chemin = Path.home() / ".config/systemd/user/ambicrafted-console.service"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if chemin.is_symlink():
        raise ErreurCLI("L'unité existante ne peut pas être un lien symbolique.")
    if chemin.exists():
        if not remplacer:
            raise ErreurCLI("L'unité existe déjà. Utiliser --remplacer après examen.")
        if "# Managed by Ambicrafted CLI" not in chemin.read_text():
            raise ErreurCLI("L'unité existante n'est pas gérée par ce CLI ; elle est conservée.")
    verifier_prerequis(p)
    texte = f"""# Managed by Ambicrafted CLI
[Unit]
Description=Ambicrafted private agentic console
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=simple
WorkingDirectory={repertoire_systemd(str(p.racine))}
ExecStart={argument_systemd(str(p.racine / "plateforme"), commande=True)} servir
Environment=PLATFORM_PORT={p.port}
Environment={argument_systemd("PLATFORM_STATE_DIR=" + str(p.etat))}
Environment={argument_systemd("PATH=" + chemin_outils())}
Restart=on-failure
RestartSec=5
TimeoutStopSec=15
KillMode=control-group
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
UMask=0077
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""
    temporaire = chemin.with_suffix(".service.tmp")
    fd = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as flux:
            flux.write(texte)
            flux.flush()
            os.fsync(flux.fileno())
        os.replace(temporaire, chemin)
    finally:
        temporaire.unlink(missing_ok=True)
    commandes = [["systemctl", "--user", "daemon-reload"]]
    if demarrer:
        commandes += [
            ["systemctl", "--user", "reset-failed", "ambicrafted-console.service"],
            ["systemctl", "--user", "enable", "--now", "ambicrafted-console.service"],
        ]
    for commande in commandes:
        reponse = subprocess.run(commande, capture_output=True, timeout=30, check=False)
        if "reset-failed" in commande:
            # A never-started unit may not be loaded yet. Its reset is best-effort;
            # enable/start remains mandatory and reports any real startup failure.
            continue
        if reponse.returncode:
            raise ErreurCLI(
                "Unité écrite ; commande systemd échouée. Vérifier le gestionnaire utilisateur."
            )
    return {"unite": str(chemin), "demarrage_demande": demarrer, "url": p.url}


def executer(args: argparse.Namespace, p: Parametres) -> Any:
    if args.commande == "prerequis":
        return verifier_prerequis(p)
    if args.commande == "observabilite" and args.action != "afficher":
        import asyncio

        from .collecteur import collect, installer

        if args.action == "installer":
            return installer(p)
        asyncio.run(collect(p, p.racine / "gateway/observability/.textfile/platform.prom"))
        return {"collected": True, "scope": "local-aggregate"}
    if args.commande == "memoire" and args.action == "installer":
        import asyncio

        from .installer_memoire import main as installer_memoire

        asyncio.run(installer_memoire())
        return None
    if args.commande == "servir":
        if not (p.web / "index.html").is_file():
            raise ErreurCLI(
                "Construire la console avec npm ci puis npm run build dans apps/console."
            )
        verifier_prerequis(p)
        os.environ["PATH"] = chemin_outils()
        import uvicorn

        uvicorn.run(
            "plateforme.app:creer_app",
            factory=True,
            host="127.0.0.1",
            port=p.port,
            access_log=False,
            proxy_headers=False,
            server_header=False,
            workers=1,
            limit_concurrency=32,
            timeout_keep_alive=5,
        )
        return None
    if args.commande == "installer-service":
        return installer_service(p, demarrer=args.demarrer, remplacer=args.remplacer)
    with Client(p) as client:
        if args.commande == "conversations":
            path = "/api/conversations"
            if args.action == "lister":
                return client.appeler("GET", path, params={"page": args.page})
            if args.action == "creer":
                return client.appeler("POST", path)
            path += "/" + str(args.identifiant)
            if args.action == "dire":
                if len(args.piece) > 8:
                    raise ErreurCLI("Sélectionner au maximum huit pièces jointes.")
                message = lire_entree(args.fichier, 4000)
                operation = str(args.operation_id or uuid4())
                print("Identifiant du tour : " + operation, file=sys.stderr)
                return client.dialogue(
                    args.identifiant,
                    {
                        "message": message,
                        "langue": args.langue,
                        "pieces": [str(value) for value in args.piece],
                        "operation_id": operation,
                    },
                )
            if args.action == "joindre":
                return client.appeler(
                    "POST",
                    path + "/pieces",
                    json={
                        "nom": args.fichier.name,
                        "contenu": base64.b64encode(
                            lire_audio(args.fichier, nature="joint")
                        ).decode("ascii"),
                    },
                )
            return client.appeler("DELETE" if args.action == "supprimer" else "GET", path)
        if args.commande == "veille":
            return client.appeler("GET", "/api/veille")
        if args.commande == "memoire":
            if args.action == "statut":
                return client.appeler("GET", "/api/memoire/statut")
            if args.action == "creer":
                try:
                    data = json.loads(lire_entree(args.fichier, 8000))
                except ValueError:
                    raise ErreurCLI("Une note JSON valide est requise.") from None
                return client.appeler("POST", "/api/memoire", json=data)
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", args.scope):
                raise ErreurCLI("Périmètre invalide : minuscules, chiffres, tirets ou tirets bas.")
            if args.action == "lister":
                return client.appeler(
                    "GET", "/api/memoire", params={"scope": args.scope, "recherche": args.recherche}
                )
            if args.action == "lier":
                return client.appeler(
                    "POST",
                    "/api/memoire/liens",
                    json={
                        "scope": args.scope,
                        "origine": str(args.origine),
                        "destination": str(args.destination),
                    },
                )
            return client.appeler(
                "DELETE" if args.action == "supprimer" else "GET",
                "/api/memoire/" + str(args.identifiant),
                params={"scope": args.scope},
            )
        if args.commande == "ouvrir":
            resultat = client.appeler("POST", "/api/auth/ticket")
            ticket = resultat.get("ticket", "") if isinstance(resultat, dict) else ""
            if not isinstance(ticket, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", ticket):
                raise ErreurCLI("L'API a renvoyé un ticket invalide.")
            # Never print this URL: its fragment is a short-lived bearer credential.
            try:
                if "microsoft" in platform.release().lower() and not os.environ.get("BROWSER"):
                    webbrowser.register("ambicrafted-wsl", None, NavigateurWSL(), preferred=True)
                with masquer_sorties_navigateur():
                    ouvert = webbrowser.open(p.url + "/#session=" + ticket, new=2)
            except webbrowser.Error:
                ouvert = False
            if not ouvert:
                raise ErreurCLI(
                    "Navigateur indisponible. Configurer BROWSER ou un mot de passe, "
                    "puis ouvrir l'adresse locale affichée par parametres."
                )
            return {"message": "Console ouverte dans le navigateur local.", "url": p.url}
        if args.commande in {"preparation", "doctor"}:
            return client.appeler("GET", "/api/preparation")
        if args.commande in {"statut", "sante", "vue-ensemble", "observabilite", "parametres"}:
            route = "sante" if args.commande in {"statut", "sante"} else args.commande
            resultat = client.appeler("GET", "/api/" + route)
            if args.commande == "parametres":
                resultat["url"] = p.url
            return resultat
        if args.commande == "mot-de-passe":
            if args.stdin:
                valeur = lire_entree(None, 130).rstrip("\r\n")
            else:
                if not sys.stdin.isatty():
                    raise ErreurCLI("Utiliser --stdin pour fournir le mot de passe sans terminal.")
                valeur = getpass.getpass("Nouveau mot de passe (14 à 128 caractères) : ")
                if valeur != getpass.getpass("Confirmer le mot de passe : "):
                    raise ErreurCLI("Les mots de passe ne correspondent pas.")
            if not 14 <= len(valeur) <= 128:
                raise ErreurCLI("Le mot de passe doit comporter entre 14 et 128 caractères.")
            return client.appeler("PUT", "/api/auth/mot-de-passe", json={"valeur": valeur})
        if args.commande == "analyses":
            if args.action == "lister":
                return client.appeler(
                    "GET",
                    "/api/analyses",
                    params={
                        "page": args.page,
                        "taille": args.taille,
                        "statut": args.statut,
                    },
                )
            if args.action == "creer":
                resultat = client.appeler(
                    "POST",
                    "/api/analyses",
                    json={
                        "titre": args.titre,
                        "alerte": lire_entree(args.fichier, 20_000),
                    },
                )
            elif args.action in {"approuver", "refuser"}:
                resultat = client.appeler(
                    "POST",
                    f"/api/analyses/{args.id}/decision",
                    json={
                        "approuver": args.action == "approuver",
                    },
                )
            elif args.action == "annuler":
                return client.appeler("POST", f"/api/analyses/{args.id}/annuler")
            elif args.action == "supprimer":
                return client.appeler("DELETE", f"/api/analyses/{args.id}")
            elif args.action == "exporter":
                contenu = client.appeler(
                    "GET",
                    f"/api/analyses/{args.id}/export",
                    texte=True,
                    params={"format": args.format},
                )
                return ecrire_export(args.sortie, contenu)
            else:
                resultat = client.appeler("GET", f"/api/analyses/{args.id}")
            if args.action == "attendre" or getattr(args, "attendre", False):
                resultat = client.attendre(resultat, args.delai)
            return resultat
        if args.commande == "operation":
            resultat = client.appeler("POST", "/api/operations/" + args.nom)
            return client.attendre(resultat, args.delai) if args.attendre else resultat
        if args.commande == "runbooks":
            if args.action == "lister":
                return client.appeler("GET", "/api/runbooks")
            if args.action == "lire":
                return client.appeler("GET", "/api/runbooks/" + args.nom)
            return client.appeler(
                "PUT",
                "/api/runbooks/" + args.nom,
                json={
                    "contenu": lire_entree(args.fichier, 8000, prive=False),
                    "empreinte": args.empreinte,
                },
            )
        if args.commande == "recherche":
            return client.appeler(
                "GET",
                "/api/recherche",
                params={
                    "q": lire_entree(None, 500).strip(),
                    "mode": args.mode,
                },
            )
        if args.commande == "voix":
            if args.action == "statut":
                return client.appeler("GET", "/api/voix/statut", params={"langue": args.langue})
            if args.action == "parler":
                audio = client.appeler(
                    "POST",
                    "/api/voix/parler",
                    binaire=True,
                    timeout=180,
                    json={"texte": lire_entree(args.fichier, 2000), "langue": args.langue},
                )
                return ecrire_export(args.sortie, audio)
            return client.appeler(
                "POST",
                "/api/voix/transcrire",
                timeout=180,
                json={
                    "audio": base64.b64encode(lire_audio(args.fichier)).decode("ascii"),
                    "langue": args.langue,
                },
            )
    raise ErreurCLI("Commande inconnue.")


def main(argv: list[str] | None = None) -> int:
    args = analyseur().parse_args(argv)
    try:
        resultat = executer(args, Parametres.charger())
        if resultat is not None:
            print(json.dumps(resultat, ensure_ascii=False, indent=2))
        if args.commande in {"preparation", "doctor"} and (
            not isinstance(resultat, dict) or resultat.get("ready") is not True
        ):
            return 2
        return 2 if isinstance(resultat, dict) and resultat.get("statut") in ECHECS else 0
    except ErreurCLI as erreur:
        print(str(erreur), file=sys.stderr)
    except OSError, ValueError, subprocess.SubprocessError:
        print(
            "Opération locale impossible. Vérifier les fichiers privés et la configuration.",
            file=sys.stderr,
        )
    except KeyboardInterrupt:
        print(
            "Commande interrompue. Une tâche soumise continue jusqu'à son annulation explicite.",
            file=sys.stderr,
        )
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
