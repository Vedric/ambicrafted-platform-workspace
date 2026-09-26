"""Bounded local concurrency tests, not a production capacity certification."""

import statistics
import time
from concurrent.futures import ThreadPoolExecutor


def test_rafale_creation_file_bornee(client, application, bearer, record_testsuite_property):
    def soumettre(i):
        return client.post(
            "/api/analyses",
            headers=bearer,
            json={"titre": f"Incident {i}", "alerte": "Charge synthétique"},
        ).status_code

    debut = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        resultats = list(pool.map(soumettre, range(48)))
    duree = time.perf_counter() - debut
    assert resultats.count(202) == application.state.moteur.p.taille_file
    assert resultats.count(409) == 48 - application.state.moteur.p.taille_file
    assert application.state.moteur.file.qsize() == application.state.moteur.p.taille_file
    assert len(application.state.moteur.alertes) == application.state.moteur.p.taille_file
    assert application.state.depot.statistiques()["total"] == application.state.moteur.p.taille_file
    assert duree < 20, "La rafale locale doit rester bornée sans blocage."
    record_testsuite_property("creation_requetes", 48)
    record_testsuite_property("creation_concurrence", 16)
    record_testsuite_property("creation_duree_s", round(duree, 3))


def test_lectures_concurrentes_et_consistance(
    client, application, bearer, record_testsuite_property
):
    for i in range(30):
        application.state.depot.creer(f"analyse-{i}", f"Incident {i}", "graphe", {}, "test")
    latences = []

    def lire(_):
        debut = time.perf_counter()
        reponse = client.get("/api/analyses?taille=100", headers=bearer)
        assert reponse.status_code == 200
        resultat = reponse.json()
        assert resultat["total"] == 30 and len(resultat["elements"]) == 30
        return time.perf_counter() - debut

    debut = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        latences.extend(pool.map(lire, range(160)))
    duree = time.perf_counter() - debut
    assert duree < 20, "Les lectures concurrentes locales ne doivent pas bloquer."
    record_testsuite_property("lecture_requetes", 160)
    record_testsuite_property("lecture_concurrence", 16)
    record_testsuite_property("lecture_duree_s", round(duree, 3))
    record_testsuite_property(
        "lecture_p95_ms", round(statistics.quantiles(latences, n=20)[18] * 1000, 1)
    )
