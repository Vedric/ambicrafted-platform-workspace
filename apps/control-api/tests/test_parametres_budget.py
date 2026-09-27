"""The visible SRE ceiling matches the private configuration sent to jobs."""

import pytest

from plateforme.config import enregistrer_secret


@pytest.mark.parametrize(
    "valeur,attendu",
    [
        (None, 60_000),
        ("12345", 12345),
        ("0", None),
        ("1000001", None),
        ("1.5", None),
        ("invalid", None),
    ],
)
def test_plafond_visible_et_forwarding_moteur(client, bearer, parametres, moteur, valeur, attendu):
    if valeur is not None:
        enregistrer_secret(parametres.racine, "SRE_MAX_TOKENS_TOTAL", valeur)
    resultat = client.get("/api/parametres", headers=bearer)
    assert resultat.status_code == 200
    assert resultat.json()["budget_tokens_total"] == attendu
    assert parametres.cle not in resultat.text
    executable = parametres.racine / "agents/sre-agent/.venv/bin/sre-agent-graph"
    executable.parent.mkdir(parents=True)
    executable.touch()
    analyse = moteur.creer("Fixture", "Synthetic alert", "cli")
    _, env = moteur.commande(analyse, None)
    assert env.get("SRE_MAX_TOKENS_TOTAL", "60000") == (valeur or "60000")
    assert "PLATFORM_UI_KEY" not in env
