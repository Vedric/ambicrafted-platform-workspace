"""Private configuration, explicit local origins and safe state directories."""

from __future__ import annotations

import fcntl
import os
import secrets
import stat
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values, set_key


def dossier_prive(chemin: Path, *, creer: bool = True) -> Path:
    if chemin.is_symlink():
        raise ValueError("Un dossier privé ne peut pas être un lien symbolique.")
    if creer:
        chemin.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = chemin.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Le dossier d'état doit appartenir à l'utilisateur et être en mode 0700.")
    return chemin


def lire_environnement(racine: Path) -> dict[str, str]:
    chemin = racine / ".env"
    if not chemin.exists():
        return {}
    info = chemin.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
        raise ValueError("Le fichier .env doit être privé, régulier et appartenir à l'utilisateur.")
    return {k: v for k, v in dotenv_values(chemin).items() if v is not None}


@contextmanager
def verrou_configuration(racine: Path):
    """Serialize first initialization and updates across CLI/server processes."""
    fd = os.open(racine / ".env.control.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Le verrou de configuration doit être un fichier privé régulier.")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _ecrire_secret_verrouille(racine: Path, nom: str, valeur: str) -> None:
    """Write only while the caller owns verrou_configuration; never nest flock."""
    chemin = racine / ".env"
    if not chemin.exists():
        nouveau = os.open(chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(nouveau)
    set_key(str(chemin), nom, valeur)


def enregistrer_secret(racine: Path, nom: str, valeur: str) -> None:
    with verrou_configuration(racine):
        lire_environnement(racine)
        _ecrire_secret_verrouille(racine, nom, valeur)


@dataclass
class Parametres:
    racine: Path
    etat: Path
    cle: str = field(repr=False)
    mot_de_passe: str = field(default="", repr=False)
    port: int = 8787
    duree_session: int = 43_200
    taille_file: int = 12
    retention_jours: int = 14
    origine_dev: str = ""
    veille_active: bool = False
    tracage_actif: bool = False

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def origines(self) -> set[str]:
        valeurs = {self.url, f"http://localhost:{self.port}"}
        if self.origine_dev:
            valeurs.add(self.origine_dev)
        return valeurs

    @property
    def web(self) -> Path:
        return self.racine / "apps/console/dist"

    @property
    def budget_tokens_total(self) -> int | None:
        """The next job's observed-token ceiling; None means invalid configuration."""
        try:
            plafond = int(lire_environnement(self.racine).get("SRE_MAX_TOKENS_TOTAL", "60000"))
        except ValueError:
            return None
        return plafond if 1 <= plafond <= 1_000_000 else None

    @classmethod
    def charger(cls, *, lecture_seule: bool = False) -> Parametres:
        racine = Path(
            os.environ.get("PLATFORM_ROOT", Path(__file__).resolve().parents[4])
        ).resolve()
        if lecture_seule:
            valeurs = lire_environnement(racine)
            cle = valeurs.get("PLATFORM_UI_KEY", "")
        else:
            with verrou_configuration(racine):
                valeurs = lire_environnement(racine)
                cle = valeurs.get("PLATFORM_UI_KEY", "")
                if not cle:
                    cle = secrets.token_urlsafe(48)
                    _ecrire_secret_verrouille(racine, "PLATFORM_UI_KEY", cle)
        if not 32 <= len(cle) <= 256 or not cle.isascii() or any(c.isspace() for c in cle):
            raise ValueError(
                "La clé de contrôle locale doit contenir 32 à 256 caractères ASCII sans espace."
            )
        etat = Path(
            os.environ.get("PLATFORM_STATE_DIR")
            or valeurs.get("PLATFORM_STATE_DIR")
            or Path.home() / ".local/state/ambicrafted"
        ).expanduser()
        dossier_prive(etat, creer=not lecture_seule)
        port = int(os.environ.get("PLATFORM_PORT") or valeurs.get("PLATFORM_PORT") or 8787)
        if not 1024 <= port <= 65535:
            raise ValueError("Port local invalide.")
        return cls(
            racine=racine,
            etat=etat,
            cle=cle,
            mot_de_passe=valeurs.get("PLATFORM_PASSWORD_HASH", ""),
            port=port,
            origine_dev=os.environ.get("PLATFORM_DEV_ORIGIN", ""),
            veille_active=valeurs.get("PLATFORM_TECH_WATCH", "1") == "1",
            tracage_actif=valeurs.get("PLATFORM_TRACING", "1") == "1",
        )

    def environnement_agent(self) -> dict[str, str]:
        valeurs = lire_environnement(self.racine)
        autorises = {
            "CONFIDENTIAL_KEY",
            "LITELLM_BASE_URL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "QDRANT_URL",
            "QDRANT_COLLECTION",
            "SRE_TIMEOUT_LLM_S",
            "SRE_MAX_DUREE_S",
            "SRE_MAX_TOKENS_TOTAL",
        }
        resultat = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG", "TMPDIR"}}
        resultat.update({k: v for k, v in valeurs.items() if k in autorises})
        resultat.update(
            SRE_RACINE_DEPOT=str(self.racine),
            RUNBOOK_DIR=str(self.racine / "runbooks"),
            SRE_ALIAS_RAISONNEMENT="local",
            SRE_PROGRESS="1",
            PYTHONUNBUFFERED="1",
            PLATFORM_STATE_DIR=str(self.etat),
            LANGSMITH_TRACING="false",
            LANGCHAIN_TRACING_V2="false",
        )
        return resultat
