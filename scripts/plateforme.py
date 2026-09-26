# /// script
# requires-python = ">=3.14"
# dependencies = ["httpx==0.28.1", "python-dotenv==1.2.3"]
# ///
"""Contrôles, clés et rétention de la plateforme sans affichage de secrets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

import httpx
from dotenv import dotenv_values, set_key

RACINE = Path(__file__).resolve().parents[1]


def environnement(chemin: Path) -> dict[str, str]:
    if not chemin.exists():
        return {}
    if chemin.is_symlink() or chemin.stat().st_mode & 0o077:
        raise ValueError("Un fichier d'environnement doit être privé (0600), sans lien symbolique.")
    return {k: v for k, v in dotenv_values(chemin).items() if v is not None}


def verifier() -> tuple[dict, bool]:
    valeurs = environnement(RACINE / ".env")
    resultats: dict = {}
    with httpx.Client(timeout=10, trust_env=False) as client:
        for nom, url in {
            "passerelle": "http://127.0.0.1:4000/health/liveliness",
            "grafana": "http://127.0.0.1:3000/api/health",
            "prometheus": "http://127.0.0.1:9090/-/ready",
            "qdrant": "http://127.0.0.1:6333/readyz",
        }.items():
            try:
                resultats[nom] = client.get(url).status_code == 200
            except httpx.HTTPError:
                resultats[nom] = False
        try:
            series = client.get(
                "http://127.0.0.1:9090/api/v1/query", params={"query": 'up{job="tempo"}'}
            ).json()["data"]["result"]
            resultats["tempo_scrape"] = bool(series) and all(
                float(s["value"][1]) == 1 for s in series
            )
        except httpx.HTTPError, ValueError, KeyError, TypeError:
            resultats["tempo_scrape"] = False
        cle = valeurs.get("CONFIDENTIAL_KEY")
        resultats["cle_confidentielle"] = bool(cle)
        if cle:
            entetes = {"Authorization": "Bearer " + cle}
            try:
                reponse = client.get("http://127.0.0.1:4000/v1/models", headers=entetes)
                modeles = {m["id"] for m in reponse.json().get("data", [])}
                resultats["alias_restraints"] = reponse.status_code == 200 and modeles == {
                    "local",
                    "local-embed",
                }
                reponse = client.post(
                    "http://127.0.0.1:4000/v1/chat/completions",
                    headers=entetes,
                    json={
                        "model": "smart",
                        "messages": [{"role": "user", "content": "test synthetique"}],
                        "max_tokens": 1,
                    },
                )
                resultats["frontiere_refusee"] = reponse.status_code == 403
            except httpx.HTTPError, ValueError, KeyError:
                resultats["alias_restraints"] = False
        try:
            tags = client.get("http://172.17.0.1:11434/api/tags").json()["models"]
            presents = {m["name"]: m["digest"] for m in tags}
            attendus = json.loads((RACINE / "models/manifest.json").read_text())["models"]
            resultats["modeles_conformes"] = all(presents.get(n) == d for n, d in attendus.items())
        except httpx.HTTPError, ValueError, KeyError:
            resultats["modeles_conformes"] = False
        try:
            alias = valeurs.get("QDRANT_COLLECTION", "runbooks-current")
            reponse = client.get(f"http://127.0.0.1:6333/collections/{alias}")
            resultats["index_present"] = (
                reponse.status_code == 200 and reponse.json()["result"]["points_count"] > 0
            )
        except httpx.HTTPError, ValueError, KeyError, TypeError:
            resultats["index_present"] = False
    resultats["espace_disque"] = shutil.disk_usage(RACINE).free > 5 * 1024**3
    return resultats, all(resultats.values())


def creer_cles(frontiere: bool) -> dict:
    passerelle = environnement(RACINE / "gateway/.env")
    chemin = RACINE / ".env"
    valeurs = environnement(chemin)
    maitre = passerelle.get("LITELLM_MASTER_KEY")
    if not maitre:
        raise ValueError(
            "Configurer la clé maître dans gateway/.env avant de créer les clés virtuelles."
        )
    if not chemin.exists():
        fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fichier:
            fichier.write((RACINE / ".env.example").read_text())
    cibles = [("CONFIDENTIAL_KEY", "confidential-only", ["local", "local-embed"])]
    if frontiere:
        cibles.append(
            (
                "ORCHESTRATOR_KEY",
                "evaluations-publiques",
                ["local", "local-embed", "fast", "balanced", "smart"],
            )
        )
    resultat = {}
    with httpx.Client(timeout=30, trust_env=False) as client:
        for variable, nom, modeles in cibles:
            if valeurs.get(variable):
                resultat[variable] = "conservée"
                continue
            reponse = client.post(
                "http://127.0.0.1:4000/key/generate",
                headers={"Authorization": "Bearer " + maitre},
                json={"key_alias": nom, "models": modeles},
            )
            reponse.raise_for_status()
            cle = reponse.json()["key"]
            set_key(str(chemin), variable, cle)
            resultat[variable] = "créée et enregistrée sans affichage"
    return resultat


def installer_retention() -> dict:
    programme = RACINE / "agents/sre-agent/.venv/bin/sre-agent-graph"
    if not programme.is_file():
        raise ValueError("Installer l'agent avec uv sync --locked --extra graphe avant le timer.")
    valeurs = environnement(RACINE / ".env")
    base = Path(
        valeurs.get(
            "SRE_CHECKPOINT_DB",
            str(Path.home() / ".local/state/sre-agent/graphe.sqlite"),
        )
    )
    base.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if base.parent.stat().st_mode & 0o022:
        raise ValueError("Le dossier de checkpoints est modifiable par un tiers.")

    def citer(chemin: Path) -> str:
        texte = str(chemin)
        if "\n" in texte:
            raise ValueError("Chemin invalide.")
        return '"' + texte.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"') + '"'

    dossier = Path.home() / ".config/systemd/user"
    dossier.mkdir(parents=True, exist_ok=True)
    service = f"""[Unit]
Description=Purge locale des checkpoints SRE de plus de 14 jours
[Service]
Type=oneshot
Environment=SRE_TRACAGE=0
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart={citer(programme)} --purger --avant 14 --checkpoints {citer(base)} --json
ExecStartPost={citer(programme.parent / "python")} {citer(RACINE / "scripts/sauvegarder.py")} --purger --avant 14
NoNewPrivileges=true
PrivateTmp=true
UMask=0077
StandardOutput=null
TimeoutStartSec=120
"""
    timer = """[Unit]
Description=Rétention quotidienne des checkpoints SRE
[Timer]
OnCalendar=*-*-* 03:15:00
RandomizedDelaySec=15m
Persistent=true
[Install]
WantedBy=timers.target
"""
    (dossier / "sre-agent-retention.service").write_text(service)
    (dossier / "sre-agent-retention.timer").write_text(timer)
    uv = Path.home() / ".local/bin/uv"
    if not uv.is_file():
        trouve = shutil.which("uv")
        if not trouve:
            raise ValueError("uv est requis pour la sauvegarde planifiée.")
        uv = Path(trouve)
    service_backup = f"""[Unit]
Description=Sauvegarde locale de la plateforme
[Service]
Type=oneshot
ExecStart={citer(uv)} run --locked --offline {citer(RACINE / "scripts/sauvegarder.py")}
UMask=0077
StandardOutput=null
TimeoutStartSec=300
"""
    (dossier / "platform-backup.service").write_text(service_backup)
    (dossier / "platform-backup.timer").write_text(
        timer.replace(
            "Rétention quotidienne des checkpoints SRE",
            "Sauvegarde quotidienne de la plateforme",
        ).replace("03:15:00", "02:45:00")
    )
    for arguments in (
        ("daemon-reload",),
        ("enable", "--now", "sre-agent-retention.timer"),
    ):
        subprocess.run(["systemctl", "--user", *arguments], check=True, capture_output=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", "platform-backup.timer"],
        check=True,
        capture_output=True,
    )
    return {"retention": "timer quotidien installé", "jours": 14, "fichier": str(base)}


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("commande", choices=["verifier", "creer-cles", "installer-retention"])
    analyseur.add_argument(
        "--inclure-frontiere",
        action="store_true",
        help="Crée aussi la clé des évaluations publiques, jamais utilisée par l'agent SRE.",
    )
    options = analyseur.parse_args()
    os.umask(0o077)
    try:
        if options.commande == "verifier":
            resultat, reussi = verifier()
        elif options.commande == "creer-cles":
            resultat, reussi = creer_cles(options.inclure_frontiere), True
        else:
            resultat, reussi = installer_retention(), True
        print(json.dumps(resultat, ensure_ascii=False, indent=2))
        return 0 if reussi else 1
    except (
        ValueError,
        KeyError,
        OSError,
        httpx.HTTPError,
        subprocess.SubprocessError,
    ) as erreur:
        # Do not copy exception strings: response bodies and commands can contain secrets.
        print(
            json.dumps(
                {
                    "erreur": type(erreur).__name__,
                    "message": "Opération interrompue. Vérifier la configuration et les services.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
