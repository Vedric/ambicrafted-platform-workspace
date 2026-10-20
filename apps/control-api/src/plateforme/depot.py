"""Transactional local state; no raw alert is stored here."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sre_agent.graphe import VERSION_CONTRAT

from .config import dossier_prive


def maintenant() -> str:
    return datetime.now(UTC).isoformat()


class Conflit(RuntimeError):
    pass


class Introuvable(RuntimeError):
    pass


class Depot:
    def __init__(self, dossier: Path):
        dossier_prive(dossier)
        self.chemin = dossier / "console.sqlite"
        fd = os.open(self.chemin, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Base locale non régulière.")
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        self.verrou = threading.RLock()
        with self.connexion() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY, titre TEXT NOT NULL, mode TEXT NOT NULL,
                    statut TEXT NOT NULL, cree_le TEXT NOT NULL, maj_le TEXT NOT NULL,
                    stade TEXT NOT NULL DEFAULT 'file', rapport TEXT,
                    options TEXT NOT NULL DEFAULT '{}', duree_s REAL NOT NULL DEFAULT 0,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS evenements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, analyse_id TEXT NOT NULL,
                    date TEXT NOT NULL, stade TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
                    action TEXT NOT NULL, reference TEXT, acteur TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    empreinte TEXT PRIMARY KEY, expire REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tickets (
                    empreinte TEXT PRIMARY KEY, expire REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL,
                    date TEXT NOT NULL, empreinte TEXT NOT NULL, contenu TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS analyses_date ON analyses(cree_le DESC);
                CREATE INDEX IF NOT EXISTS evenements_analyse ON evenements(analyse_id,id);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connexion(self):
        with self.verrou:
            c = sqlite3.connect(self.chemin, timeout=5)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA secure_delete=ON")
            try:
                with c:
                    yield c
            finally:
                c.close()

    @staticmethod
    def decoder(ligne: sqlite3.Row, detail: bool = True) -> dict[str, Any]:
        resultat = dict(ligne)
        resultat["options"] = json.loads(resultat["options"])
        contrat = resultat["options"].get("version_contrat")
        # Compatibility is metadata, never an approval or a checkpoint migration.
        resultat["reprise_compatible"] = (
            resultat["mode"] == "graphe" and type(contrat) is int and contrat == VERSION_CONTRAT
        )
        resultat["rapport"] = json.loads(resultat["rapport"]) if resultat["rapport"] else None
        if not detail:
            rapport = resultat.pop("rapport") or {}
            resultat["urgence"] = (rapport.get("classification") or {}).get("urgence")
            resultat["source"] = (rapport.get("diagnostic") or {}).get("runbook_source")
            resultat["budget"] = rapport.get("budget", {})
        return resultat

    def creer(self, identifiant: str, titre: str, mode: str, options: dict, acteur: str) -> dict:
        date = maintenant()
        with self.connexion() as c:
            c.execute(
                "INSERT INTO analyses(id,titre,mode,statut,cree_le,maj_le,options) VALUES(?,?,?,?,?,?,?)",
                (identifiant, titre, mode, "en_file", date, date, json.dumps(options)),
            )
            self._journal(c, "analyse.creee", identifiant, acteur)
        return self.obtenir(identifiant)

    def obtenir(self, identifiant: str) -> dict:
        with self.connexion() as c:
            ligne = c.execute("SELECT * FROM analyses WHERE id=?", (identifiant,)).fetchone()
            if not ligne:
                raise Introuvable("Analyse introuvable.")
            resultat = self.decoder(ligne)
            resultat["evenements"] = [
                dict(r)
                for r in c.execute(
                    "SELECT id,date,stade FROM evenements WHERE analyse_id=? ORDER BY id",
                    (identifiant,),
                )
            ]
            return resultat

    def lister(
        self, *, page: int = 1, taille: int = 25, statut: str = "", recherche: str = ""
    ) -> dict:
        conditions, valeurs = [], []
        if statut:
            conditions.append("statut=?")
            valeurs.append(statut)
        if recherche:
            conditions.append("instr(lower(titre),lower(?))>0")
            valeurs.append(recherche)
        clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.connexion() as c:
            total = c.execute("SELECT count(*) FROM analyses" + clause, valeurs).fetchone()[0]
            lignes = c.execute(
                "SELECT * FROM analyses" + clause + " ORDER BY cree_le DESC LIMIT ? OFFSET ?",
                [*valeurs, taille, (page - 1) * taille],
            ).fetchall()
            return {
                "elements": [self.decoder(r, False) for r in lignes],
                "total": total,
                "page": page,
            }

    def changer(
        self,
        identifiant: str,
        statut: str,
        *,
        attendus: set[str] | None = None,
        rapport: dict | None = None,
        duree_s: float | None = None,
        acteur="systeme",
    ) -> dict:
        with self.connexion() as c:
            c.execute("BEGIN IMMEDIATE")
            ligne = c.execute("SELECT statut FROM analyses WHERE id=?", (identifiant,)).fetchone()
            if not ligne:
                raise Introuvable("Analyse introuvable.")
            if attendus and ligne["statut"] not in attendus:
                raise Conflit("L'état de cette analyse a changé. Actualiser avant de poursuivre.")
            c.execute(
                "UPDATE analyses SET statut=?,maj_le=?,version=version+1,rapport=COALESCE(?,rapport),"
                "duree_s=COALESCE(?,duree_s) WHERE id=?",
                (
                    statut,
                    maintenant(),
                    json.dumps(rapport, ensure_ascii=False) if rapport is not None else None,
                    duree_s,
                    identifiant,
                ),
            )
            self._journal(c, "analyse." + statut, identifiant, acteur)
        return self.obtenir(identifiant)

    def progression(self, identifiant: str, stade: str) -> None:
        with self.connexion() as c:
            c.execute(
                "UPDATE analyses SET stade=?,maj_le=?,version=version+1 WHERE id=?",
                (stade, maintenant(), identifiant),
            )
            c.execute(
                "INSERT INTO evenements(analyse_id,date,stade) VALUES(?,?,?)",
                (identifiant, maintenant(), stade),
            )
            c.execute(
                "DELETE FROM evenements WHERE analyse_id=? AND id NOT IN "
                "(SELECT id FROM evenements WHERE analyse_id=? ORDER BY id DESC LIMIT 80)",
                (identifiant, identifiant),
            )

    def reprendre_apres_arret(self) -> None:
        with self.connexion() as c:
            lignes = c.execute(
                "SELECT id FROM analyses WHERE statut IN ('en_file','en_cours','decision')"
            ).fetchall()
            for r in lignes:
                c.execute(
                    "UPDATE analyses SET statut='interrompu',maj_le=?,version=version+1 WHERE id=?",
                    (maintenant(), r["id"]),
                )
                self._journal(c, "analyse.interrompu", r["id"], "systeme")

    def supprimer(self, identifiant: str, acteur: str) -> None:
        with self.connexion() as c:
            c.execute("BEGIN IMMEDIATE")
            ligne = c.execute("SELECT statut FROM analyses WHERE id=?", (identifiant,)).fetchone()
            if not ligne:
                raise Introuvable("Analyse introuvable.")
            if ligne["statut"] in {"en_file", "en_cours", "decision"}:
                raise Conflit("Annuler l'analyse avant de la supprimer.")
            c.execute("DELETE FROM evenements WHERE analyse_id=?", (identifiant,))
            c.execute("DELETE FROM analyses WHERE id=?", (identifiant,))
            self._journal(c, "analyse.supprimee", identifiant, acteur)

    @staticmethod
    def _journal(c, action: str, reference: str | None, acteur: str) -> None:
        c.execute(
            "INSERT INTO journal(date,action,reference,acteur) VALUES(?,?,?,?)",
            (maintenant(), action, reference, acteur),
        )

    def auditer(self, action: str, reference: str | None, acteur: str) -> None:
        with self.connexion() as c:
            self._journal(c, action, reference, acteur)

    def journal(self, limite=60) -> list[dict]:
        with self.connexion() as c:
            return [
                dict(r)
                for r in c.execute("SELECT * FROM journal ORDER BY id DESC LIMIT ?", (limite,))
            ]

    def statistiques(self) -> dict:
        with self.connexion() as c:
            statuts = dict(
                c.execute("SELECT statut,count(*) FROM analyses GROUP BY statut").fetchall()
            )
            dates = dict(
                c.execute(
                    "SELECT substr(cree_le,1,10),count(*) FROM analyses GROUP BY 1"
                ).fetchall()
            )
            activite = []
            for i in range(13, -1, -1):
                jour = (datetime.now(UTC) - timedelta(days=i)).date().isoformat()
                activite.append({"date": jour, "total": dates.get(jour, 0)})
            return {"total": sum(statuts.values()), "statuts": statuts, "activite": activite}
