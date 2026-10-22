"""Bounded, serial execution of fixed local commands. Alerts only travel on stdin."""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import os
import re
import shutil
import signal
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sre_agent.graphe import VERSION_CONTRAT
from sre_agent.modeles import Rapport

from .config import Parametres, dossier_prive
from .depot import Conflit, Depot, Introuvable

OPERATIONS = {"verifier", "indexer", "sauvegarder", "tester-restauration"}
ACTIFS = {"en_file", "en_cours", "decision"}


class Moteur:
    def __init__(self, parametres: Parametres, depot: Depot):
        self.p, self.depot = parametres, depot
        self.file: asyncio.Queue = asyncio.Queue(maxsize=parametres.taille_file)
        self.alertes: dict[str, str] = {}
        self.processus: dict[str, asyncio.subprocess.Process] = {}
        self.tache: asyncio.Task | None = None
        self.racine = dossier_prive(self.p.etat / "analyses")
        self.inference = asyncio.Lock()
        self.maintenance: asyncio.Task | None = None
        self.verrou_instance: int | None = None

    async def demarrer(self) -> None:
        self.verrou_instance = os.open(
            self.p.etat / "controle.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(self.verrou_instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.verrou_instance)
            self.verrou_instance = None
            raise RuntimeError("Un plan de contrôle utilise déjà ce dossier d'état.") from None
        self.depot.reprendre_apres_arret()
        self.purger()
        self.tache = asyncio.create_task(self.travailler())
        self.maintenance = asyncio.create_task(self.entretenir())

    async def fermer(self) -> None:
        if self.maintenance:
            self.maintenance.cancel()
            await asyncio.gather(self.maintenance, return_exceptions=True)
        if self.tache:
            self.tache.cancel()
        for processus in list(self.processus.values()):
            await self.terminer(processus)
        if self.tache:
            await asyncio.gather(self.tache, return_exceptions=True)
        self.alertes.clear()
        self.depot.reprendre_apres_arret()
        if self.verrou_instance is not None:
            os.close(self.verrou_instance)
            self.verrou_instance = None

    def purger(self) -> None:
        limite = (datetime.now(UTC) - timedelta(days=self.p.retention_jours)).isoformat()
        journal_limite = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        with self.depot.connexion() as c:
            lignes = c.execute(
                "SELECT id FROM analyses WHERE maj_le<? AND statut NOT IN ('en_file','en_cours','decision')",
                (limite,),
            ).fetchall()
            for ligne in lignes:
                identifiant = ligne["id"]
                if re.fullmatch(r"[a-f0-9]{32}", identifiant):
                    dossier = self.racine / identifiant
                    if dossier.is_dir() and not dossier.is_symlink():
                        shutil.rmtree(dossier)
                c.execute("DELETE FROM evenements WHERE analyse_id=?", (identifiant,))
                c.execute("DELETE FROM analyses WHERE id=?", (identifiant,))
            c.execute("DELETE FROM journal WHERE date<?", (journal_limite,))
            c.execute("DELETE FROM revisions WHERE date<?", (journal_limite,))
            c.execute("DELETE FROM sessions WHERE expire<?", (time.time(),))
            c.execute("DELETE FROM tickets WHERE expire<?", (time.time(),))
        if lignes:
            self.depot.auditer("retention.appliquee", str(len(lignes)), "systeme")
            with self.depot.connexion() as c:
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                c.execute("VACUUM")

    async def entretenir(self) -> None:
        while True:
            await asyncio.sleep(3600)
            self.purger()

    @staticmethod
    async def terminer(processus: asyncio.subprocess.Process) -> None:
        # The leader can exit while descendants still own its stdout/stderr.
        # A return code therefore does not mean this owned process group is gone.
        try:
            os.killpg(processus.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            if processus.returncode is None:
                await asyncio.wait_for(processus.wait(), 3)
        except TimeoutError:
            pass
        finally:
            # Descendants must not outlive the command, including children that
            # ignore SIGTERM after their leader has already been reaped.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(processus.pid, signal.SIGKILL)
        await processus.wait()

    def creer(self, titre: str, alerte: str, acteur: str, operation: str = "") -> dict:
        if self.file.full():
            raise Conflit("File pleine. Attendre la fin d'une analyse.")
        identifiant = uuid.uuid4().hex
        resultat = self.depot.creer(
            identifiant,
            titre,
            "operation" if operation else "graphe",
            {"operation": operation} if operation else {"version_contrat": VERSION_CONTRAT},
            acteur,
        )
        if alerte:
            self.alertes[identifiant] = alerte
        self.file.put_nowait((identifiant, None))
        return resultat

    def decider(self, identifiant: str, approuver: bool, acteur: str) -> dict:
        analyse = self.depot.obtenir(identifiant)
        if not analyse["reprise_compatible"]:
            raise Conflit(
                "Cette analyse utilise un ancien contrat de vérification. Historique conservé. "
                "Créer une nouvelle analyse et ressaisir l’alerte d’origine avant toute décision."
            )
        if self.file.full():
            raise Conflit("File pleine. Réessayer après une analyse.")
        resultat = self.depot.changer(
            identifiant, "decision", attendus={"en_attente_humain"}, acteur=acteur
        )
        self.file.put_nowait((identifiant, approuver))
        return resultat

    async def annuler(self, identifiant: str, acteur: str) -> dict:
        resultat = self.depot.changer(identifiant, "annule", attendus=ACTIFS, acteur=acteur)
        self.alertes.pop(identifiant, None)
        if processus := self.processus.get(identifiant):
            await self.terminer(processus)
        return resultat

    def commande(self, analyse: dict, decision: bool | None) -> tuple[list[str], dict[str, str]]:
        env = self.p.environnement_agent()
        uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
        if analyse["mode"] == "operation":
            operation = analyse["options"]["operation"]
            if operation == "indexer":
                return [
                    uv,
                    "run",
                    "--locked",
                    "--project",
                    str(self.p.racine / "mcp-servers/runbooks"),
                    str(self.p.racine / "mcp-servers/runbooks/indexer.py"),
                ], env
            script = {
                "verifier": "plateforme",
                "sauvegarder": "sauvegarder",
                "tester-restauration": "tester_restauration",
            }[operation]
            cmd = [uv, "run", "--locked", "--script", str(self.p.racine / f"scripts/{script}.py")]
            if operation == "verifier":
                cmd.append("verifier")
            elif operation == "tester-restauration":
                sauvegardes = sorted(
                    (Path.home() / ".local/state/platform-backups").glob("*/manifest.json")
                )
                if not sauvegardes:
                    raise ValueError("Aucune sauvegarde complète disponible.")
                cmd.append(str(sauvegardes[-1].parent))
            return cmd, env
        dossier = dossier_prive(self.racine / analyse["id"])
        executable = self.p.racine / "agents/sre-agent/.venv/bin/sre-agent-graph"
        if not executable.is_file():
            raise ValueError("Installer le moteur avec uv sync --locked --all-extras.")
        cmd = [
            str(executable),
            "--json",
            "--thread-id",
            analyse["id"],
            "--checkpoints",
            str(dossier / "graphe.sqlite"),
        ]
        if decision is not None:
            cmd.extend(["--reprendre", "oui" if decision else "non"])
        return cmd, env

    async def executer(self, identifiant: str, decision: bool | None) -> None:
        analyse = self.depot.obtenir(identifiant)
        if analyse["statut"] not in {"en_file", "decision"}:
            return
        self.depot.changer(identifiant, "en_cours", attendus={"en_file", "decision"})
        self.depot.progression(identifiant, "demarrage")
        debut = time.monotonic()
        processus = None
        try:
            cmd, env = self.commande(analyse, decision)
            processus = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.p.racine,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            self.processus[identifiant] = processus
            if self.depot.obtenir(identifiant)["statut"] != "en_cours":
                return
            assert processus.stdin and processus.stdout and processus.stderr
            alerte = self.alertes.pop(identifiant, "")
            processus.stdin.write(alerte.encode())
            del alerte
            await processus.stdin.drain()
            processus.stdin.close()

            async def lire_stdout() -> bytes:
                assert processus and processus.stdout
                sortie = bytearray()
                while bloc := await processus.stdout.read(8192):
                    sortie.extend(bloc)
                    if len(sortie) > 1_000_000:
                        raise ValueError("Sortie du moteur trop volumineuse.")
                return bytes(sortie)

            async def lire_stderr() -> None:
                assert processus and processus.stderr
                total = 0
                while ligne := await processus.stderr.readline():
                    total += len(ligne)
                    if total > 500_000:
                        raise ValueError("Journal du moteur trop volumineux.")
                    if ligne.startswith(b"SRE_EVENT "):
                        evenement = json.loads(ligne[10:])
                        if evenement.get("stade") in {"modele", "outil"}:
                            self.depot.progression(identifiant, evenement["stade"])

            async with asyncio.timeout(2000):
                # TaskGroup cancels companion readers on a bound violation.
                async with asyncio.TaskGroup() as groupe:
                    sortie = groupe.create_task(lire_stdout())
                    groupe.create_task(lire_stderr())
                    groupe.create_task(processus.wait())
            if analyse["mode"] == "operation":
                rapport = {
                    "statut": "complet" if processus.returncode == 0 else "erreur",
                    "message": "Opération terminée."
                    if processus.returncode == 0
                    else "Opération échouée. Consulter le diagnostic de la plateforme.",
                }
            else:
                rapport = Rapport.model_validate_json(sortie.result()).model_dump(mode="json")
                codes = {
                    "complet": 0,
                    "budget_epuise": 2,
                    "erreur": 3,
                    "rejete_par_humain": 4,
                    "en_attente_humain": 10,
                }
                if processus.returncode != codes[rapport["statut"]]:
                    raise ValueError("Code de sortie incompatible avec le rapport.")
            self.depot.changer(
                identifiant,
                rapport["statut"],
                attendus={"en_cours"},
                rapport=rapport,
                duree_s=analyse["duree_s"] + time.monotonic() - debut,
            )
            self.depot.progression(identifiant, "termine")
        except asyncio.CancelledError:
            raise
        except Conflit, Introuvable:
            pass  # Cancellation won the transaction; never overwrite it.
        except Exception as erreur:  # noqa: BLE001 - subprocess failures are isolated per job.
            with contextlib.suppress(Introuvable, Conflit):
                self.depot.changer(
                    identifiant,
                    "erreur",
                    attendus={"en_cours"},
                    rapport={
                        "statut": "erreur",
                        "message": f"Exécution interrompue ({type(erreur).__name__}). Vérifier la santé des services puis relancer.",
                    },
                    duree_s=time.monotonic() - debut,
                )
        finally:
            self.alertes.pop(identifiant, None)
            if processus:
                await self.terminer(processus)
            self.processus.pop(identifiant, None)

    async def travailler(self) -> None:
        while True:
            identifiant, decision = await self.file.get()
            try:
                async with self.inference:
                    await self.executer(identifiant, decision)
            except Conflit, Introuvable:
                pass  # A queued cancellation may already have been deleted.
            finally:
                self.file.task_done()
