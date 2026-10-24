"""Bounded subprocess bridge for the optional, offline voice runtime."""

import asyncio
import base64
import binascii
import json
import os
import secrets
import shutil
import stat
import tempfile
import time
from pathlib import Path

from fastapi import HTTPException

from .config import Parametres, dossier_prive
from .moteur import Moteur


def valider_langue(langue: str) -> str:
    if langue not in ("en", "fr"):
        raise HTTPException(422, "Unsupported voice language. Choose en or fr.")
    return langue


class Voix:
    def __init__(self, p: Parametres):
        self.p = p
        self.verrou = asyncio.Lock()
        self.temp = dossier_prive(p.etat / "audio-temp")
        self.cache: dict[str, tuple[float, dict]] = {}
        self.processus: asyncio.subprocess.Process | None = None
        self.transport = asyncio.Lock()
        self.derniere_utilisation = 0.0

    async def fermer(self) -> None:
        async with self.transport:
            await self.arreter_resident()

    async def arreter_resident(self) -> None:
        processus, self.processus = self.processus, None
        if processus is not None:
            await Moteur.terminer(processus)

    async def executer_resident(self, arguments: list[str], texte: str, env: dict) -> dict:
        requete = {
            "id": secrets.token_hex(16),
            "operation": arguments[0],
            "langue": arguments[arguments.index("--langue") + 1],
            "fichier": arguments[-1],
        }
        if arguments[0] == "parler":
            requete["texte"] = texte
        trame = json.dumps(requete, ensure_ascii=False).encode() + b"\n"
        if len(trame) > 32_000:
            raise HTTPException(422, "Requête vocale trop longue.")
        async with self.transport:
            try:
                async with asyncio.timeout(130):
                    if self.processus is not None and (
                        self.processus.returncode is not None
                        or time.monotonic() - self.derniere_utilisation >= 240
                    ):
                        await self.arreter_resident()
                    if self.processus is None:
                        creation = asyncio.create_task(
                            asyncio.create_subprocess_exec(
                                str(self.p.racine / "apps/voice/.venv/bin/voix-locale"),
                                "resident",
                                env=env,
                                stdin=asyncio.subprocess.PIPE,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.DEVNULL,
                                start_new_session=True,
                                limit=64_000,
                            )
                        )
                        try:
                            self.processus = await asyncio.shield(creation)
                        except asyncio.CancelledError:
                            # Reap a child even if cancellation races process creation.
                            self.processus = await creation
                            raise
                    processus = self.processus
                    assert processus.stdin and processus.stdout
                    processus.stdin.write(trame)
                    await processus.stdin.drain()
                    sortie = await processus.stdout.readline()
                    if not sortie.endswith(b"\n") or len(sortie) > 64_000:
                        raise ValueError("Protocole vocal invalide.")
                    reponse = json.loads(sortie)
                    if reponse == {"id": requete["id"], "erreur": True}:
                        raise HTTPException(
                            422,
                            "Traitement vocal impossible. Vérifier le format, la durée et les modèles installés.",
                        )
                    if (
                        not isinstance(reponse, dict)
                        or set(reponse) != {"id", "resultat"}
                        or reponse["id"] != requete["id"]
                    ):
                        raise ValueError("Échec vocal.")
                    resultat = reponse["resultat"]
                    if not isinstance(resultat, dict):
                        raise TypeError("Réponse vocale invalide.")
                    self.derniere_utilisation = time.monotonic()
                    return resultat
            except asyncio.CancelledError:
                await self.arreter_resident()
                raise
            except HTTPException:
                await self.arreter_resident()
                raise
            except TimeoutError, ValueError, TypeError, OSError:
                await self.arreter_resident()
                raise HTTPException(503, "Moteur vocal indisponible ou délai dépassé.") from None

    def nettoyer_apres_arret(self) -> None:
        """Only call after acquiring the single-instance control lock."""
        for entree in self.temp.iterdir():
            if entree.name.startswith("capture-") and entree.is_dir() and not entree.is_symlink():
                info = entree.stat()
                if info.st_uid == os.getuid() and not info.st_mode & 0o077:
                    shutil.rmtree(entree)

    async def executer(self, arguments: list[str], texte: str = "") -> dict:
        executable = self.p.racine / "apps/voice/.venv/bin/voix-locale"
        if not executable.is_file():
            raise HTTPException(503, "Moteur vocal absent. Installer apps/voice puis ses modèles.")
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG", "TMPDIR"}}
        env.update(
            VOICE_STATE_DIR=str(self.p.etat / "voice"),
            HF_HUB_OFFLINE="1",
            ORT_DISABLE_TELEMETRY="1",
            OMP_NUM_THREADS="4",
        )
        if arguments[0] in ("parler", "transcrire"):
            return await self.executer_resident(arguments, texte, env)
        processus = await asyncio.create_subprocess_exec(
            str(executable),
            *arguments,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            async with asyncio.timeout(130):
                assert processus.stdin and processus.stdout
                processus.stdin.write(texte.encode())
                await processus.stdin.drain()
                processus.stdin.close()
                sortie = bytearray()
                while bloc := await processus.stdout.read(8192):
                    sortie.extend(bloc)
                    if len(sortie) > 64_000:
                        raise HTTPException(502, "Réponse vocale trop volumineuse.")
                await processus.wait()
            if processus.returncode:
                raise HTTPException(
                    422,
                    "Traitement vocal impossible. Vérifier le format, la durée et les modèles installés.",
                )
            resultat = json.loads(sortie)
            if not isinstance(resultat, dict):
                raise TypeError("Réponse invalide.")
            return resultat
        except TimeoutError, ValueError, TypeError, OSError:
            raise HTTPException(503, "Moteur vocal indisponible ou délai dépassé.") from None
        finally:
            await Moteur.terminer(processus)

    async def statut(self, langue: str = "en") -> dict:
        langue = valider_langue(langue)
        precedent = self.cache.get(langue)
        if precedent and time.monotonic() - precedent[0] < 60:
            return precedent[1]
        try:
            resultat = await self.executer(["statut", "--langue", langue])
        except HTTPException:
            resultat = {
                "pret": False,
                "local": True,
                "voix": "voix-feminine-" + langue,
                "langue": "en-US" if langue == "en" else "fr-FR",
                "langues": ["en", "fr"],
            }
        self.cache[langue] = (time.monotonic(), resultat)
        return resultat

    async def parler(self, texte: str, langue: str = "en") -> bytes:
        langue = valider_langue(langue)
        if self.verrou.locked():
            raise HTTPException(409, "Le moteur vocal traite déjà une demande.")
        async with self.verrou:
            with tempfile.TemporaryDirectory(dir=self.temp, prefix="capture-") as dossier:
                sortie = Path(dossier) / "reponse.wav"
                await self.executer(["parler", "--langue", langue, "--sortie", str(sortie)], texte)
                fd = os.open(sortie, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as fichier:
                    if not stat.S_ISREG(os.fstat(fichier.fileno()).st_mode):
                        raise HTTPException(502, "Réponse audio non régulière.")
                    audio = fichier.read(8_388_609)
                if len(audio) > 8_388_608 or not audio.startswith(b"RIFF"):
                    raise HTTPException(502, "Réponse audio invalide.")
                return audio

    async def transcrire(self, audio: str, langue: str = "en") -> dict:
        langue = valider_langue(langue)
        if self.verrou.locked():
            raise HTTPException(409, "Le moteur vocal traite déjà une demande.")
        try:
            donnees = base64.b64decode(audio, validate=True)
        except ValueError, binascii.Error:
            raise HTTPException(422, "Audio encodé invalide.") from None
        if not 1 <= len(donnees) <= 8_388_608:
            raise HTTPException(413, "Audio limité à 8 Mio.")
        async with self.verrou:
            with tempfile.TemporaryDirectory(dir=self.temp, prefix="capture-") as dossier:
                source = Path(dossier) / "capture.audio"
                fd = os.open(source, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as fichier:
                    fichier.write(donnees)
                del donnees
                resultat = await self.executer(["transcrire", "--langue", langue, str(source)])
                if not isinstance(resultat.get("texte"), str) or len(resultat["texte"]) > 20_000:
                    raise HTTPException(502, "Transcription invalide.")
                return resultat
