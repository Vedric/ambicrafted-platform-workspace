import io
import json
import sys

import pytest

from voix_locale import cli
from voix_locale.fichiers import ErreurVoix


def test_erreur_interne_masquee(monkeypatch, capsys):
    def echouer():
        raise RuntimeError("DONNEES_CLIENT_SECRETE")

    monkeypatch.setattr(cli, "executer", echouer)
    with pytest.raises(SystemExit) as sortie:
        cli.main()
    assert sortie.value.code == 2
    capture = capsys.readouterr()
    assert "DONNEES_CLIENT" not in capture.out + capture.err
    assert "erreur" in json.loads(capture.out)


def test_erreur_operateur_et_resultat_json(monkeypatch, capsys):
    def echouer():
        raise ErreurVoix("Erreur sûre.")

    monkeypatch.setattr(cli, "executer", echouer)
    with pytest.raises(SystemExit):
        cli.main()
    assert json.loads(capsys.readouterr().out) == {"erreur": "Erreur sûre."}
    monkeypatch.setattr(cli, "executer", lambda: {"local": True})
    cli.main()
    assert json.loads(capsys.readouterr().out) == {"local": True}


@pytest.mark.parametrize("langue", ["en", "fr"])
def test_statut_verifie_les_deux_alias(monkeypatch, langue):
    verifications = []
    monkeypatch.setattr(cli, "verifier_modele", verifications.append)
    resultat = cli.executer(["statut", "--langue", langue])
    assert resultat["pret"]
    assert resultat["langues"] == ["en", "fr"]
    assert verifications == ["voix-feminine-" + langue, "transcription-" + langue]


def test_statut_anglais_par_defaut(monkeypatch):
    monkeypatch.setattr(cli, "verifier_modele", lambda _: None)
    assert cli.executer(["statut"])["langue"] == "en-US"


@pytest.mark.parametrize("langue", ["EN", "de", "../fr", "", "en-US"])
def test_cli_langue_hors_contrat_refusee(langue):
    with pytest.raises(SystemExit) as sortie:
        cli.executer(["statut", "--langue", langue])
    assert sortie.value.code == 2


def test_installation_explicite(monkeypatch):
    monkeypatch.setattr(cli, "installer", lambda: {"fichiers_installes": 8})
    assert cli.executer(["installer"]) == {"fichiers_installes": 8}


def test_alarme(monkeypatch):
    with pytest.raises(ErreurVoix, match="délai"):
        cli.delai_depasse(None, None)


def test_stdin_borne_avant_appel_modele(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"x" * 8001)))
    with pytest.raises(ErreurVoix, match="longueur"):
        cli.executer(["parler", "--sortie", "/unused.wav"])
