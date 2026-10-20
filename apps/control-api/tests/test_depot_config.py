"""Private filesystem state and atomic transition invariants."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from plateforme.config import Parametres, dossier_prive, enregistrer_secret, lire_environnement
from plateforme.depot import Conflit, Depot, Introuvable


def test_etat_prive_et_sqlite_permissions(parametres, depot):
    assert parametres.etat.stat().st_mode & 0o777 == 0o700
    assert depot.chemin.stat().st_mode & 0o777 == 0o600
    with depot.connexion() as c:
        assert c.execute("PRAGMA secure_delete").fetchone()[0] == 1


def test_rejet_dossier_etat_partage_ou_symbolique(tmp_path):
    partage = tmp_path / "partage"
    partage.mkdir(mode=0o755)
    # Model a shared directory even when the test runner uses a private umask.
    partage.chmod(0o755)
    with pytest.raises(ValueError):
        dossier_prive(partage)
    lien = tmp_path / "lien"
    lien.symlink_to(partage, target_is_directory=True)
    with pytest.raises(ValueError):
        dossier_prive(lien)


def test_rejet_base_symbolique(tmp_path):
    etat = tmp_path / "etat"
    etat.mkdir(mode=0o700)
    cible = tmp_path / "exterieur"
    cible.write_text("Ne pas modifier")
    (etat / "console.sqlite").symlink_to(cible)
    with pytest.raises(OSError):
        Depot(etat)
    assert cible.read_text() == "Ne pas modifier"


def test_configuration_privee_et_representations_sans_secret(parametres):
    assert lire_environnement(parametres.racine) == {}
    enregistrer_secret(parametres.racine, "PLATFORM_UI_KEY", parametres.cle)
    assert lire_environnement(parametres.racine)["PLATFORM_UI_KEY"] == parametres.cle
    assert parametres.cle not in repr(parametres)
    chemin = parametres.racine / ".env"
    assert chemin.stat().st_mode & 0o077 == 0
    chemin.chmod(0o644)
    with pytest.raises(ValueError):
        lire_environnement(parametres.racine)
    with pytest.raises(ValueError):
        enregistrer_secret(parametres.racine, "AUTRE", "valeur")


def test_configuration_refuse_env_et_verrou_symboliques(parametres, tmp_path):
    cible = tmp_path / "prive"
    cible.write_text("SYNTHETIQUE=valeur\n")
    cible.chmod(0o600)
    (parametres.racine / ".env").symlink_to(cible)
    with pytest.raises(ValueError):
        lire_environnement(parametres.racine)
    (parametres.racine / ".env").unlink()
    (parametres.racine / ".env.control.lock").symlink_to(cible)
    with pytest.raises(OSError):
        enregistrer_secret(parametres.racine, "AUTRE", "valeur")
    assert cible.read_text() == "SYNTHETIQUE=valeur\n"


def test_chargement_cree_secret_local_et_reutilise(parametres, monkeypatch):
    monkeypatch.setenv("PLATFORM_ROOT", str(parametres.racine))
    monkeypatch.setenv("PLATFORM_STATE_DIR", str(parametres.etat))
    monkeypatch.setenv("PLATFORM_PORT", "8788")
    premier, second = Parametres.charger(), Parametres.charger()
    assert len(premier.cle) >= 32
    assert premier.cle == second.cle
    assert premier.url == "http://127.0.0.1:8788"
    assert premier.origines == {"http://127.0.0.1:8788", "http://localhost:8788"}


@pytest.mark.parametrize("port", ["80", "65536", "invalide"])
def test_configuration_port_invalide(parametres, monkeypatch, port):
    monkeypatch.setenv("PLATFORM_ROOT", str(parametres.racine))
    monkeypatch.setenv("PLATFORM_STATE_DIR", str(parametres.etat))
    monkeypatch.setenv("PLATFORM_PORT", port)
    with pytest.raises(ValueError):
        Parametres.charger()


def test_environnement_agent_exclut_cles_externes_et_desactive_tracage(parametres, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "exemple-synthetique")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy.invalid")
    enregistrer_secret(parametres.racine, "OPENAI_API_KEY", "exemple-synthetique")
    enregistrer_secret(parametres.racine, "CONFIDENTIAL_KEY", parametres.cle)
    env = parametres.environnement_agent()
    assert "OPENAI_API_KEY" not in env and "HTTPS_PROXY" not in env
    assert env["LANGSMITH_TRACING"] == env["LANGCHAIN_TRACING_V2"] == "false"
    assert env["CONFIDENTIAL_KEY"] == parametres.cle
    assert env["SRE_ALIAS_RAISONNEMENT"] == "local"


def test_changement_etat_concurrent_un_seul_gagnant(depot):
    depot.creer("analyse", "Titre", "graphe", {}, "cli")
    depot.changer("analyse", "en_attente_humain")

    def approuver(_):
        try:
            depot.changer("analyse", "decision", attendus={"en_attente_humain"})
            return True
        except Conflit:
            return False

    with ThreadPoolExecutor(max_workers=16) as pool:
        resultats = list(pool.map(approuver, range(32)))
    assert resultats.count(True) == 1
    assert depot.obtenir("analyse")["statut"] == "decision"
    assert sum(e["action"] == "analyse.decision" for e in depot.journal()) == 1


def test_redemarrage_marque_uniquement_travaux_interrompus(depot):
    statuts = ["en_file", "en_cours", "decision", "en_attente_humain", "complet", "annule"]
    for statut in statuts:
        depot.creer(statut, "Titre", "graphe", {}, "cli")
        depot.changer(statut, statut)
    depot.reprendre_apres_arret()
    for statut in statuts:
        attendu = "interrompu" if statut in statuts[:3] else statut
        assert depot.obtenir(statut)["statut"] == attendu
    assert sum(e["action"] == "analyse.interrompu" for e in depot.journal()) == 3


def test_evenements_bornes_et_requetes_parametrees(depot):
    identifiant = "' OR 1=1 --"
    depot.creer(identifiant, "Titre", "graphe", {}, "cli")
    for _ in range(100):
        depot.progression(identifiant, "modele")
    assert len(depot.obtenir(identifiant)["evenements"]) == 80
    assert depot.obtenir(identifiant)["version"] == 101
    assert depot.lister(recherche="' OR 1=1 --")["total"] == 0
    with pytest.raises(Introuvable):
        depot.obtenir("autre")


def test_transaction_echouee_annule_modifications(depot):
    with pytest.raises(RuntimeError), depot.connexion() as c:
        c.execute("INSERT INTO sessions VALUES('synthetique', 9999999999)")
        raise RuntimeError("Annuler")
    with depot.connexion() as c:
        assert c.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0


def test_premier_demarrage_concurrent_ne_regenere_pas_cle(parametres, monkeypatch):
    monkeypatch.setenv("PLATFORM_ROOT", str(parametres.racine))
    monkeypatch.setenv("PLATFORM_STATE_DIR", str(parametres.etat))
    monkeypatch.setenv("PLATFORM_PORT", "8787")
    with ThreadPoolExecutor(max_workers=12) as pool:
        configurations = list(pool.map(lambda _: Parametres.charger(), range(24)))
    cles = {configuration.cle for configuration in configurations}
    assert len(cles) == 1, (
        "Le CLI et le serveur doivent partager la même clé dès le premier démarrage."
    )
    assert lire_environnement(parametres.racine)["PLATFORM_UI_KEY"] in cles
