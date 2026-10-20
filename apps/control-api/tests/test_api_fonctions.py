"""Functional API paths use the real state store and queue transitions."""

import json

import pytest


def creer(client, bearer, titre="Incident synthétique", alerte="Alerte synthétique"):
    reponse = client.post("/api/analyses", json={"titre": titre, "alerte": alerte}, headers=bearer)
    assert reponse.status_code == 202
    return reponse.json()


def test_alerte_reste_uniquement_dans_file_memoire(client, application, bearer):
    marqueur = "ALERTE_BRUTE_SYNTHETIQUE_NON_PERSISTEE"
    analyse = creer(client, bearer, alerte=marqueur)
    assert application.state.moteur.alertes[analyse["id"]] == marqueur
    assert marqueur not in json.dumps(analyse)
    assert marqueur not in json.dumps(application.state.depot.lister())
    assert marqueur not in json.dumps(application.state.depot.journal())
    assert marqueur.encode() not in application.state.depot.chemin.read_bytes()


def test_liste_pagination_filtres_sans_rapport_detaille(client, application, bearer):
    analyse = creer(client, bearer, titre="Postgres synthétique")
    application.state.depot.changer(
        analyse["id"],
        "complet",
        rapport={
            "classification": {"urgence": 3},
            "diagnostic": {"runbook_source": "postgres.md"},
            "budget": {"appels_llm": 2},
            "contenu_prive": "détail synthétique",
        },
    )
    creer(client, bearer, titre="Autre incident")
    reponse = client.get("/api/analyses?statut=complet&recherche=POSTGRES&taille=1", headers=bearer)
    assert reponse.status_code == 200
    assert reponse.json()["total"] == 1
    element = reponse.json()["elements"][0]
    assert element["urgence"] == 3 and element["source"] == "postgres.md"
    assert "rapport" not in element and "contenu_prive" not in element
    assert client.get("/api/analyses?taille=1&page=2", headers=bearer).json()["elements"]
    assert (
        client.get("/api/analyses?recherche=%27%20OR%201=1--", headers=bearer).json()["total"] == 0
    )


@pytest.mark.parametrize("requete", ["taille=0", "taille=101", "page=0", "page=10001"])
def test_liste_bornee(client, bearer, requete):
    assert client.get("/api/analyses?" + requete, headers=bearer).status_code == 422


@pytest.mark.parametrize("decision", [True, False])
def test_decision_humaine_exactement_une_fois(client, application, bearer, decision):
    analyse = creer(client, bearer)
    application.state.depot.changer(
        analyse["id"], "en_attente_humain", rapport={"diagnostic": None}
    )
    chemin = f"/api/analyses/{analyse['id']}/decision"
    reponse = client.post(chemin, json={"approuver": decision}, headers=bearer)
    assert reponse.status_code == 202 and reponse.json()["statut"] == "decision"
    assert client.post(chemin, json={"approuver": decision}, headers=bearer).status_code == 409


def test_annulation_retire_alerte_et_protege_etat_terminal(client, application, bearer):
    analyse = creer(client, bearer)
    chemin = f"/api/analyses/{analyse['id']}/annuler"
    assert client.post(chemin, json={}, headers=bearer).json()["statut"] == "annule"
    assert analyse["id"] not in application.state.moteur.alertes
    assert client.post(chemin, json={}, headers=bearer).status_code == 409


def test_suppression_refuse_actif_puis_nettoie_checkpoints(client, application, bearer):
    analyse = creer(client, bearer)
    chemin = f"/api/analyses/{analyse['id']}"
    assert client.request("DELETE", chemin, json={}, headers=bearer).status_code == 409
    dossier = application.state.moteur.racine / analyse["id"]
    dossier.mkdir(mode=0o700)
    (dossier / "graphe.sqlite").write_bytes("Checkpoint synthétique".encode())
    client.post(chemin + "/annuler", json={}, headers=bearer)
    assert client.request("DELETE", chemin, json={}, headers=bearer).status_code == 200
    assert not dossier.exists()
    assert client.get(chemin, headers=bearer).status_code == 404


def test_suppression_ne_suit_pas_lien_checkpoint(client, application, bearer, tmp_path):
    analyse = creer(client, bearer)
    exterieur = tmp_path / "ne-pas-effacer"
    exterieur.mkdir()
    (exterieur / "preuve").write_text("Préserver")
    (application.state.moteur.racine / analyse["id"]).symlink_to(
        exterieur, target_is_directory=True
    )
    client.post(f"/api/analyses/{analyse['id']}/annuler", json={}, headers=bearer)
    assert (
        client.request(
            "DELETE", f"/api/analyses/{analyse['id']}", json={}, headers=bearer
        ).status_code
        == 200
    )
    assert (exterieur / "preuve").read_text() == "Préserver"


def test_export_et_flux_terminal(client, application, bearer):
    analyse = creer(client, bearer)
    application.state.depot.changer(
        analyse["id"],
        "complet",
        rapport={
            "diagnostic": {
                "cause_probable": "Cause synthétique",
                "actions_proposees": ["Lire le runbook"],
                "runbook_source": "postgres.md",
            },
        },
    )
    chemin = f"/api/analyses/{analyse['id']}"
    reponse = client.get(chemin + "/export", headers=bearer)
    assert reponse.status_code == 200
    assert json.loads(reponse.text)["statut"] == "complet"
    assert "attachment" in reponse.headers["content-disposition"]
    markdown = client.get(chemin + "/export?format=md", headers=bearer)
    assert "Cause synthétique" in markdown.text and "postgres.md" in markdown.text
    assert "Revue IA locale bornée" not in markdown.text
    assert client.get(chemin + "/export?format=html", headers=bearer).status_code == 422
    evenements = client.get(chemin + "/evenements", headers=bearer)
    assert "text/event-stream" in evenements.headers["content-type"]
    assert evenements.text.startswith("data: ")
    assert json.loads(evenements.text[6:].strip())["statut"] == "complet"


def test_export_preserves_bounded_ai_review_without_claiming_independence(
    client, application, bearer
):
    analyse = creer(client, bearer)
    qualite = {
        "statut": "abstention",
        "ecarts": ["Source insuffisante"],
        "calculs": ["3 × 4 = 12"],
        "extraction_ecartee": True,
        "latence_ms": 240,
        "tokens_entree": 100,
        "tokens_sortie": 20,
        "limite": "Revue IA locale, sans validation indépendante.",
    }
    application.state.depot.changer(
        analyse["id"],
        "complet",
        rapport={"diagnostic": {"cause_probable": "Hypothèse", "qualite": qualite}},
    )
    url = f"/api/analyses/{analyse['id']}"
    for endpoint in (url, url + "/export"):
        assert (
            client.get(endpoint, headers=bearer).json()["rapport"]["diagnostic"]["qualite"]
            == qualite
        )
    content = client.get(url + "/export?format=md", headers=bearer).text
    assert "Revue IA locale bornée" in content and "Source insuffisante" in content
    assert "3 × 4 = 12" in content and qualite["limite"] in content
    assert "tokens_sortie : 20" in content and "extraction_ecartee : True" in content


def test_runbooks_edition_et_recherche(client, bearer):
    document = client.get("/api/runbooks/postgres.md", headers=bearer).json()
    reponse = client.put(
        "/api/runbooks/postgres.md",
        headers=bearer,
        json={
            "contenu": "# PostgreSQL révisé\n\nValider le diagnostic humain.",
            "empreinte": document["empreinte"],
        },
    )
    assert reponse.status_code == 200
    assert (
        client.put(
            "/api/runbooks/postgres.md",
            headers=bearer,
            json={
                "contenu": "# Édition obsolète",
                "empreinte": document["empreinte"],
            },
        ).status_code
        == 409
    )
    assert client.get("/api/recherche?q=diagnostic", headers=bearer).json()["elements"]
    assert (
        client.get("/api/recherche?q=postgres&mode=semantique", headers=bearer).json()["mode"]
        == "semantique"
    )
    assert client.get("/api/runbooks/absent.md", headers=bearer).status_code == 404


def test_operation_inconnue_refuse_et_liste_blanche_accepte(client, bearer):
    assert (
        client.post("/api/operations/commande-arbitraire", headers=bearer, json={}).status_code
        == 404
    )
    for operation in ["verifier", "indexer", "sauvegarder", "tester-restauration"]:
        reponse = client.post(f"/api/operations/{operation}", headers=bearer, json={})
        assert reponse.status_code == 202
        assert reponse.json()["mode"] == "operation"
        assert reponse.json()["options"] == {"operation": operation}


def test_vue_ensemble_et_parametres_ne_divulguent_pas_configuration(client, bearer, parametres):
    creer(client, bearer)
    vue = client.get("/api/vue-ensemble", headers=bearer)
    assert vue.status_code == 200 and vue.json()["total"] == 1
    assert len(vue.json()["activite"]) == 14
    assert vue.json()["runbooks"] == 1
    configuration = client.get("/api/parametres", headers=bearer)
    assert configuration.status_code == 200
    assert parametres.cle not in configuration.text
    assert str(parametres.racine) not in configuration.text


def test_routes_console_et_api_distinctes(client, parametres):
    assert client.get("/espace/analyses").status_code == 200
    assert "Console locale" in client.get("/").text
    assert "locale = true" in client.get("/asset.js").text
    assert client.get("/api/inconnue").status_code == 404
    cible = parametres.racine / "prive.txt"
    cible.write_text("NE_PAS_SERVIR_HORS_DIST")
    (parametres.web / "lien.txt").symlink_to(cible)
    assert "NE_PAS_SERVIR_HORS_DIST" not in client.get("/lien.txt").text
