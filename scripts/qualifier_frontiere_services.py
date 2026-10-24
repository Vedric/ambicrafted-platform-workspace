# /// script
# requires-python = ">=3.14"
# dependencies = ["httpx==0.28.1", "python-dotenv==1.2.3", "pyyaml==6.0.3"]
# ///
"""Exercise native service authentication on disposable Compose state only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import traceback
from pathlib import Path

import httpx
import yaml
from dotenv import dotenv_values
from securiser_services import preparer

RACINE = Path(__file__).resolve().parents[1]


def qualifier(sortie: Path) -> dict:
    projet = "validationplatform-auth-" + secrets.token_hex(6)
    sortie.mkdir(mode=0o700, parents=True, exist_ok=False)
    resultat = {
        "passed": False,
        "checks": {},
        "scope": "isolated synthetic native service authentication",
    }
    chemins = [
        Path(__file__),
        RACINE / "scripts/securiser_services.py",
        RACINE / "gateway/docker-compose.yml",
    ]
    chemins += [
        p
        for p in (RACINE / "gateway/observability").rglob("*")
        if p.is_file()
        and not any(part.startswith(".") for part in p.relative_to(RACINE).parts)
        and "__pycache__" not in p.parts
    ]
    empreintes = {
        str(p.relative_to(RACINE)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in chemins
    }
    resultat["source_sha256"] = empreintes
    debut = time.monotonic()
    controles = resultat["checks"]
    with tempfile.TemporaryDirectory(prefix=projet) as temporaire:
        racine = Path(temporaire)
        gateway = racine / "gateway"
        gateway.mkdir()
        shutil.copytree(
            RACINE / "gateway/observability",
            gateway / "observability",
            ignore=shutil.ignore_patterns(".*", "__pycache__"),
        )
        (gateway / "observability/.textfile").mkdir(mode=0o755)
        environnement = gateway / ".env"
        environnement.write_text(
            "GRAFANA_ADMIN_PASSWORD=" + secrets.token_urlsafe(48) + "\n"
        )
        environnement.chmod(0o600)
        preparer(racine)
        valeurs = dotenv_values(environnement)
        document = yaml.safe_load((RACINE / "gateway/docker-compose.yml").read_text())
        noms = {"qdrant", "prometheus", "grafana", "tempo", "platform-metrics"}
        document["name"] = projet
        document["services"] = {
            n: s for n, s in document["services"].items() if n in noms
        }
        for service in document["services"].values():
            for nom in ("build", "container_name", "profiles"):
                service.pop(nom, None)
            service["restart"] = "no"
            service["cpus"] = 2
            service["mem_limit"] = "1g"
            service.pop("ports", None)
        document["networks"] = {"default": {"internal": True}}
        document["volumes"] = {
            n: {"name": projet + "-" + n}
            for n in ("qdrantdata", "promdata", "grafanadata", "tempodata")
        }
        (gateway / "docker-compose.yml").write_text(yaml.safe_dump(document))
        commande = [
            "docker",
            "compose",
            "--project-directory",
            str(gateway),
            "-p",
            projet,
        ]
        env = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]}

        def compose(*args, delai=180):
            return subprocess.run(
                [*commande, *args],
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=delai,
            ).stdout

        def url(service, port):
            identifiant = compose("ps", "-q", service).strip()
            adresse = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                    identifiant,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            return f"http://{adresse}:{port}"

        try:
            compose(
                "up",
                "-d",
                "--no-build",
                "--pull",
                "never",
                "--wait",
                "--wait-timeout",
                "150",
            )
            cibles = {
                n: url(n, p)
                for n, p in (
                    ("qdrant", 6333),
                    ("prometheus", 9090),
                    ("grafana", 3000),
                    ("tempo", 4318),
                )
            }
            resultat["images"] = {}
            for nom in sorted(noms):
                identifiant = compose("ps", "-q", nom).strip()
                resultat["images"][nom] = subprocess.run(
                    ["docker", "inspect", "--format", "{{.Image}}", identifiant],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                ).stdout.strip()
            origine = {"Origin": "https://untrusted.invalid"}
            with httpx.Client(
                timeout=15, trust_env=False, follow_redirects=False
            ) as client:
                for nom, chemin in (
                    ("qdrant", "/collections"),
                    ("prometheus", "/api/v1/status/runtimeinfo"),
                ):
                    reponse = client.get(cibles[nom] + chemin, headers=origine)
                    assert reponse.status_code in {401, 403}, nom
                    assert "access-control-allow-origin" not in reponse.headers, nom
                    controles[nom + "_anonymous_cross_origin_denied"] = True
                admin = {"api-key": valeurs["QDRANT_API_KEY"]}
                lecture = {"api-key": valeurs["QDRANT_READ_ONLY_API_KEY"]}
                qdrant = cibles["qdrant"]
                corps = {"vectors": {"size": 3, "distance": "Cosine"}}
                assert (
                    client.put(
                        qdrant + "/collections/synthetic", headers=admin, json=corps
                    ).status_code
                    == 200
                )
                assert (
                    client.put(
                        qdrant + "/collections/forbidden", headers=lecture, json=corps
                    ).status_code
                    == 403
                )
                assert client.get(
                    qdrant + "/collections", headers={"api-key": "wrong"}
                ).status_code in {401, 403}
                reponse = client.get(qdrant + "/collections", headers=lecture).json()
                assert {c["name"] for c in reponse["result"]["collections"]} == {
                    "synthetic"
                }
                assert (
                    client.put(
                        qdrant + "/collections/synthetic/points",
                        params={"wait": "true"},
                        headers=admin,
                        json={
                            "points": [
                                {
                                    "id": 1,
                                    "vector": [1, 0, 0],
                                    "payload": {"source": "synthetic"},
                                }
                            ]
                        },
                    ).status_code
                    == 200
                )
                trouve = client.post(
                    qdrant + "/collections/synthetic/points/query",
                    headers=lecture,
                    json={"query": [1, 0, 0], "limit": 1},
                ).json()
                assert trouve["result"]["points"][0]["id"] == 1
                controles["qdrant_read_only_search_write_denial_no_side_effect"] = True
                snapshot = client.post(
                    qdrant + "/collections/synthetic/snapshots", headers=admin
                ).json()["result"]["name"]
                archive = client.get(
                    qdrant + "/collections/synthetic/snapshots/" + snapshot,
                    headers=admin,
                )
                archive.raise_for_status()
                assert len(archive.content) > 0
                restaure = client.post(
                    qdrant + "/collections/restored/snapshots/upload",
                    headers=admin,
                    files={"snapshot": ("synthetic.snapshot", archive.content)},
                    params={"priority": "snapshot"},
                )
                assert restaure.status_code == 200
                assert (
                    client.get(
                        qdrant + "/collections/restored", headers=lecture
                    ).json()["result"]["points_count"]
                    == 1
                )
                controles["qdrant_authenticated_snapshot_restore"] = True
                prom = cibles["prometheus"]
                authentification = ("platform", valeurs["PROMETHEUS_PASSWORD"])
                assert (
                    client.get(
                        prom + "/api/v1/query",
                        params={"query": "up"},
                        auth=("platform", secrets.token_urlsafe(48)),
                    ).status_code
                    == 401
                )
                for _ in range(40):
                    reponse = client.get(
                        prom + "/api/v1/targets", auth=authentification
                    )
                    reponse.raise_for_status()
                    cibles_actives = reponse.json()["data"]["activeTargets"]
                    if len(cibles_actives) == 5 and all(
                        c["health"] == "up" for c in cibles_actives
                    ):
                        break
                    time.sleep(1)
                assert len(cibles_actives) == 5 and all(
                    c["health"] == "up" for c in cibles_actives
                )
                controles["all_five_scrapes_authenticated_where_required"] = True
                grafana = cibles["grafana"]
                auth_grafana = ("admin", valeurs["GRAFANA_ADMIN_PASSWORD"])
                requete = client.get(
                    grafana + "/api/datasources/proxy/uid/prometheus/api/v1/query",
                    params={"query": "up"},
                    auth=auth_grafana,
                )
                assert (
                    requete.status_code == 200
                    and len(requete.json()["data"]["result"]) == 5
                )
                sources = client.get(grafana + "/api/datasources", auth=auth_grafana)
                assert sources.status_code == 200
                assert all(
                    v not in sources.text
                    for v in (
                        valeurs["PROMETHEUS_PASSWORD"],
                        valeurs["QDRANT_API_KEY"],
                        valeurs["QDRANT_READ_ONLY_API_KEY"],
                    )
                )
                controles["grafana_proxy_query_without_browser_secret"] = True
                # A real synthetic span must reach authenticated remote_write.
                maintenant = time.time_ns()
                trace = {
                    "resourceSpans": [
                        {
                            "resource": {
                                "attributes": [
                                    {
                                        "key": "service.name",
                                        "value": {
                                            "stringValue": "service-auth-synthetic"
                                        },
                                    }
                                ]
                            },
                            "scopeSpans": [
                                {
                                    "spans": [
                                        {
                                            "traceId": secrets.token_hex(16),
                                            "spanId": secrets.token_hex(8),
                                            "name": "auth-check",
                                            "kind": 2,
                                            "startTimeUnixNano": str(
                                                maintenant - 100_000_000
                                            ),
                                            "endTimeUnixNano": str(maintenant),
                                            "status": {"code": 1},
                                        }
                                    ]
                                }
                            ],
                        }
                    ]
                }
                client.post(
                    cibles["tempo"] + "/v1/traces", json=trace
                ).raise_for_status()
                for _ in range(60):
                    series = client.get(
                        prom + "/api/v1/query",
                        params={
                            "query": 'traces_spanmetrics_calls_total{service="service-auth-synthetic"}'
                        },
                        auth=authentification,
                    ).json()["data"]["result"]
                    if series:
                        break
                    time.sleep(1)
                assert series and float(series[0]["value"][1]) >= 1
                controles["tempo_authenticated_remote_write"] = True
                compose("restart", "qdrant", "prometheus")
                compose(
                    "up",
                    "-d",
                    "--no-build",
                    "--pull",
                    "never",
                    "--wait",
                    "--wait-timeout",
                    "90",
                )
                assert (
                    client.get(
                        qdrant + "/collections/synthetic", headers=lecture
                    ).json()["result"]["points_count"]
                    == 1
                )
                assert (
                    client.get(
                        prom + "/api/v1/query",
                        params={"query": "up"},
                        auth=authentification,
                    ).status_code
                    == 200
                )
                controles["authenticated_restart_preserves_data"] = True
                assert all(
                    hashlib.sha256((RACINE / p).read_bytes()).hexdigest() == h
                    for p, h in empreintes.items()
                )
                resultat["duration_seconds"] = round(time.monotonic() - debut, 3)
                resultat["passed"] = True
        finally:
            # Only this generated project's resources are eligible for cleanup.
            try:
                compose("down", "-v", "--remove-orphans")
                resultat["cleanup"] = True
            finally:
                (sortie / "receipt.json").write_text(
                    json.dumps(resultat, indent=2) + "\n"
                )
    return resultat


if __name__ == "__main__":
    os.umask(0o077)
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("sortie", type=Path)
    options = analyseur.parse_args()
    try:
        print(json.dumps(qualifier(options.sortie)))
    except Exception as erreur:  # noqa: BLE001 -- Public output must never include credentials.
        (options.sortie / "failure.txt").write_text(traceback.format_exc())
        print(json.dumps({"passed": False, "error_type": type(erreur).__name__}))
        raise SystemExit(1) from None
