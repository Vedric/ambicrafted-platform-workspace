"""Real loopback HTTP transport under bounded concurrency; no AI/service calls."""

import json
import socket
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import pytest


def test_http_reel_auth_chunked_et_charge(serveur_http, record_testsuite_property):
    client = serveur_http
    assert (
        client.get("/api/analyses", headers={"Authorization": "Bearer invalide"}).status_code == 401
    )
    assert (
        client.get("/api/analyses", headers={"Origin": "https://attacker.example"}).status_code
        == 403
    )
    with pytest.raises(AssertionError, match="réseau externe"):
        socket.create_connection(("192.0.2.1", 9), timeout=0.1)
    morceaux = iter([b'{"titre":"', b"x" * 96_000, b'","alerte":"test"}'])
    reponse = client.post(
        "/api/analyses", content=morceaux, headers={"Content-Type": "application/json"}
    )
    assert reponse.status_code == 413
    assert reponse.headers["cache-control"] == "no-store"

    def creer(i):
        return client.post(
            "/api/analyses", json={"titre": f"HTTP {i}", "alerte": "Synthétique"}
        ).status_code

    debut = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = list(pool.map(creer, range(48)))
    duree_creation = time.perf_counter() - debut
    assert codes.count(202) == 12 and codes.count(409) == 36

    def lire(_):
        debut = time.perf_counter()
        reponse = client.get("/api/analyses")
        assert reponse.status_code == 200
        assert reponse.json()["total"] == 12
        return time.perf_counter() - debut

    debut = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        latences = list(pool.map(lire, range(160)))
    duree_lecture = time.perf_counter() - debut
    assert duree_creation < 20 and duree_lecture < 20
    mesures = {
        "transport": "uvicorn-loopback",
        "concurrence": 16,
        "creation_requetes": 48,
        "creation_duree_s": round(duree_creation, 3),
        "lecture_requetes": 160,
        "lecture_duree_s": round(duree_lecture, 3),
        "lecture_p95_ms": round(statistics.quantiles(latences, n=20)[18] * 1000, 1),
    }
    record_testsuite_property("charge_http", json.dumps(mesures))
