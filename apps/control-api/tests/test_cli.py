"""Operator CLI confidentiality and API parity without real service effects."""

import argparse
import base64
import io
import json
import os
import secrets
import subprocess
from pathlib import Path

import httpx
import pytest

from plateforme import cli


@pytest.mark.parametrize("valeur", ["../ailleurs", "abc", "0" * 31, "g" * 32, "0" * 33])
def test_identifiants_cli_refuses(valeur):
    with pytest.raises(argparse.ArgumentTypeError):
        cli.identifiant(valeur)


def test_analyse_alerte_jamais_argument_argv():
    with pytest.raises(SystemExit) as erreur:
        cli.analyseur().parse_args(["analyses", "creer", "--alerte", "Contenu synthétique"])
    assert erreur.value.code == 2


def test_suppression_exige_confirmation_expresse():
    with pytest.raises(SystemExit):
        cli.analyseur().parse_args(["analyses", "supprimer", "a" * 32])
    args = cli.analyseur().parse_args(["analyses", "supprimer", "a" * 32, "--confirmer"])
    assert args.confirmer


def test_entree_privee_reguliere_bornee(tmp_path, monkeypatch):
    fichier = tmp_path / "alerte.txt"
    fichier.write_text("Alerte synthétique")
    fichier.chmod(0o600)
    assert cli.lire_entree(fichier, 100) == "Alerte synthétique"
    with pytest.raises(cli.ErreurCLI):
        cli.lire_entree(fichier, 5)
    fichier.chmod(0o644)
    with pytest.raises(cli.ErreurCLI):
        cli.lire_entree(fichier, 100)
    assert cli.lire_entree(fichier, 100, prive=False) == "Alerte synthétique"
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("Synthétique stdin"))
    assert cli.lire_entree(None, 100) == "Synthétique stdin"


def test_entree_cli_refuse_symlink_fifo_et_vide(tmp_path, monkeypatch):
    fichier = tmp_path / "alerte.txt"
    fichier.write_text("Alerte")
    fichier.chmod(0o600)
    lien = tmp_path / "lien.txt"
    lien.symlink_to(fichier)
    with pytest.raises(OSError):
        cli.lire_entree(lien, 100)
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(cli.ErreurCLI):
        cli.lire_entree(fifo, 100)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("  \n"))
    with pytest.raises(cli.ErreurCLI):
        cli.lire_entree(None, 100)


def test_export_prive_pas_ecrasement_ni_symlink(tmp_path):
    chemin = tmp_path / "rapport.json"
    assert cli.ecrire_export(chemin, "Synthétique") == {
        "exporte": str(chemin),
        "octets": len("Synthétique".encode()),
    }
    assert chemin.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        cli.ecrire_export(chemin, "Écrasement")
    lien = tmp_path / "lien"
    lien.symlink_to(chemin)
    with pytest.raises(FileExistsError):
        cli.ecrire_export(lien, "Écrasement")
    assert chemin.read_text() == "Synthétique"


def client_simule(monkeypatch, parametres, repondre):
    vrai_client = httpx.Client
    appels = []

    def intercepter(requete):
        assert requete.url.host == "127.0.0.1"
        assert requete.headers["authorization"] == "Bearer " + parametres.cle
        appels.append(requete)
        return repondre(requete)

    def construire(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return vrai_client(transport=httpx.MockTransport(intercepter), **kwargs)

    monkeypatch.setattr(httpx, "Client", construire)
    return appels


@pytest.mark.parametrize("code", [301, 400, 401, 403, 404, 409, 413, 422, 429, 500, 503])
def test_erreurs_http_masquees(monkeypatch, parametres, code):
    client_simule(
        monkeypatch,
        parametres,
        lambda _: httpx.Response(code, json={"detail": "INTERNE_SYNTHETIQUE_NON_PUBLIC"}),
    )
    with cli.Client(parametres) as client, pytest.raises(cli.ErreurCLI) as erreur:
        client.appeler("GET", "/api/analyses")
    assert "INTERNE_SYNTHETIQUE_NON_PUBLIC" not in str(erreur.value)
    assert parametres.cle not in str(erreur.value)


def test_cli_connexion_erreur_masquee(monkeypatch, parametres):
    def indisponible(requete):
        raise httpx.ConnectError("INTERNE_SYNTHETIQUE_NON_PUBLIC", request=requete)

    client_simule(monkeypatch, parametres, indisponible)
    with (
        cli.Client(parametres) as client,
        pytest.raises(cli.ErreurCLI, match="API locale inaccessible"),
    ):
        client.appeler("GET", "/api/analyses")


def test_ouverture_ticket_fragment_non_affiche(monkeypatch, parametres, capsys):
    ticket = secrets.token_urlsafe(32)
    client_simule(monkeypatch, parametres, lambda _: httpx.Response(200, json={"ticket": ticket}))
    urls = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url, **kwargs: urls.append(url) or True)
    monkeypatch.setattr(cli.Parametres, "charger", lambda: parametres)
    assert cli.main(["ouvrir"]) == 0
    sortie = capsys.readouterr()
    assert urls == [parametres.url + "/#session=" + ticket]
    assert ticket not in sortie.out + sortie.err
    assert parametres.cle not in sortie.out + sortie.err
    assert json.loads(sortie.out)["url"] == parametres.url


def test_navigateur_indisponible_masque_ticket(monkeypatch, parametres, capsys):
    ticket = secrets.token_urlsafe(32)
    client_simule(monkeypatch, parametres, lambda _: httpx.Response(200, json={"ticket": ticket}))
    monkeypatch.setattr(cli.webbrowser, "open", lambda *args, **kwargs: False)
    monkeypatch.setattr(cli.Parametres, "charger", lambda: parametres)
    assert cli.main(["ouvrir"]) == 1
    sortie = capsys.readouterr()
    assert ticket not in sortie.out + sortie.err
    assert "Navigateur indisponible" in sortie.err


def test_lanceur_masque_sorties_python_et_natives_puis_restaure(monkeypatch, parametres, capfd):
    ticket = secrets.token_urlsafe(32)
    client_simule(monkeypatch, parametres, lambda _: httpx.Response(200, json={"ticket": ticket}))
    monkeypatch.setattr(cli.Parametres, "charger", lambda: parametres)
    monkeypatch.setattr(cli.platform, "release", lambda: "linux-test")

    def ouvrir(url, *, new):
        assert url == parametres.url + "/#session=" + ticket
        assert new == 2
        print(url)
        print(url, file=cli.sys.stderr)
        os.write(1, (url + "\n").encode())
        os.write(2, (url + "\n").encode())
        return True

    monkeypatch.setattr(cli.webbrowser, "open", ouvrir)
    os.write(1, b"stdout avant\n")
    os.write(2, b"stderr avant\n")
    assert cli.main(["ouvrir"]) == 0
    os.write(1, b"stdout apres\n")
    os.write(2, b"stderr apres\n")
    sortie = capfd.readouterr()
    assert ticket not in sortie.out + sortie.err
    assert "#session=" not in sortie.out + sortie.err
    assert "stdout avant" in sortie.out and "stdout apres" in sortie.out
    assert "stderr avant" in sortie.err and "stderr apres" in sortie.err
    assert "Console ouverte dans le navigateur local." in sortie.out


def test_masquage_restaure_descripteurs_et_flux_apres_exception(capfd):
    stdout, stderr = cli.sys.stdout, cli.sys.stderr
    with pytest.raises(RuntimeError, match="Échec synthétique"), cli.masquer_sorties_navigateur():
        os.write(1, b"URL_SYNTHETIQUE_NE_PAS_AFFICHER\n")
        os.write(2, b"URL_SYNTHETIQUE_NE_PAS_AFFICHER\n")
        raise RuntimeError("Échec synthétique du lanceur")
    assert cli.sys.stdout is stdout
    assert cli.sys.stderr is stderr
    print("Python stdout restaure")
    print("Python stderr restaure", file=cli.sys.stderr)
    os.write(1, b"Descripteur stdout restaure\n")
    os.write(2, b"Descripteur stderr restaure\n")
    sortie = capfd.readouterr()
    assert "URL_SYNTHETIQUE_NE_PAS_AFFICHER" not in sortie.out + sortie.err
    assert "Python stdout restaure" in sortie.out
    assert "Python stderr restaure" in sortie.err
    assert "Descripteur stdout restaure" in sortie.out
    assert "Descripteur stderr restaure" in sortie.err


@pytest.mark.parametrize("issue", ["succes", "refus", "delai", "absent"])
def test_navigateur_wsl_arguments_fixes_et_flux_fermes(monkeypatch, issue):
    url = "http://127.0.0.1:8787/#session=" + secrets.token_urlsafe(32)
    executable = "/mnt/c/Windows/System32/cmd.exe"
    monkeypatch.setattr(cli.shutil, "which", lambda nom: executable if nom == "cmd.exe" else None)
    appels = []

    def lancer(arguments, **options):
        appels.append((arguments, options))
        if issue == "delai":
            raise subprocess.TimeoutExpired(arguments, 10)
        if issue == "absent":
            raise FileNotFoundError("Lanceur de test absent")
        return subprocess.CompletedProcess(arguments, 0 if issue == "succes" else 1)

    monkeypatch.setattr(cli.subprocess, "run", lancer)
    assert cli.NavigateurWSL().open(url, new=2) is (issue == "succes")
    assert len(appels) == 1
    arguments, options = appels[0]
    assert arguments == [executable, "/c", "start", "", url]
    assert options.get("shell", False) is False
    assert options["stdin"] == subprocess.DEVNULL
    assert options["stdout"] == subprocess.DEVNULL
    assert options["stderr"] == subprocess.DEVNULL
    assert options["timeout"] == 10
    assert options["check"] is False


def test_creation_cli_utilise_api_et_stdin(monkeypatch, parametres):
    appels = client_simule(
        monkeypatch,
        parametres,
        lambda _: httpx.Response(202, json={"id": "a" * 32, "statut": "en_file"}),
    )
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("Alerte synthétique stdin"))
    args = cli.analyseur().parse_args(["analyses", "creer", "--titre", "Incident"])
    resultat = cli.executer(args, parametres)
    assert resultat["statut"] == "en_file"
    assert appels[0].url.path == "/api/analyses"
    assert json.loads(appels[0].content) == {
        "titre": "Incident",
        "alerte": "Alerte synthétique stdin",
    }


@pytest.mark.parametrize("action,decision", [("approuver", True), ("refuser", False)])
def test_cli_decisions_api_booleennes(monkeypatch, parametres, action, decision):
    appels = client_simule(
        monkeypatch, parametres, lambda _: httpx.Response(202, json={"statut": "decision"})
    )
    args = cli.analyseur().parse_args(["analyses", action, "a" * 32])
    cli.executer(args, parametres)
    assert json.loads(appels[0].content) == {"approuver": decision}


def test_cli_mutation_vide_transmet_json(monkeypatch, parametres):
    appels = client_simule(
        monkeypatch, parametres, lambda _: httpx.Response(200, json={"statut": "annule"})
    )
    args = cli.analyseur().parse_args(["analyses", "annuler", "a" * 32])
    cli.executer(args, parametres)
    assert appels[0].headers["content-type"] == "application/json"
    assert json.loads(appels[0].content) == {}


def test_cli_attente_humaine_et_delai(monkeypatch, parametres):
    client_simule(
        monkeypatch, parametres, lambda _: httpx.Response(200, json={"statut": "en_attente_humain"})
    )
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    with cli.Client(parametres) as client:
        assert (
            client.attendre({"id": "a" * 32, "statut": "en_file"}, 10)["statut"]
            == "en_attente_humain"
        )
        with pytest.raises(cli.ErreurCLI, match="Délai"):
            client.attendre({"id": "a" * 32, "statut": "en_file"}, 0)


def test_servir_uniquement_loopback_sans_access_logs(monkeypatch, parametres):
    import uvicorn

    appels = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: appels.append((args, kwargs)))
    cli.executer(cli.analyseur().parse_args(["servir"]), parametres)
    options = appels[0][1]
    assert options["host"] == "127.0.0.1" and options["workers"] == 1
    assert options["access_log"] is False and options["proxy_headers"] is False


def test_help_does_not_load_secrets(monkeypatch):
    def interdit():
        raise AssertionError("Help must not read or generate credentials")

    monkeypatch.setattr(cli.Parametres, "charger", interdit)
    with pytest.raises(SystemExit) as erreur:
        cli.main(["--help"])
    assert erreur.value.code == 0


@pytest.mark.parametrize("ticket", [None, 12, "https://outside.invalid", "x" * 129])
def test_open_refuses_malformed_ticket(parametres, monkeypatch, ticket):
    client_simule(monkeypatch, parametres, lambda _: httpx.Response(200, json={"ticket": ticket}))
    monkeypatch.setattr(cli.Parametres, "charger", lambda: parametres)
    monkeypatch.setattr(cli.webbrowser, "open", lambda *a, **k: pytest.fail("Browser opened"))
    assert cli.main(["ouvrir"]) == 1


def test_password_only_goes_in_authenticated_body(parametres, monkeypatch, capsys):
    valeur = "mot-de-passe-synthetique-uniquement"
    appels = client_simule(
        monkeypatch, parametres, lambda _: httpx.Response(200, json={"message": "Enregistré"})
    )
    monkeypatch.setattr(cli.Parametres, "charger", lambda: parametres)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(valeur + "\n"))
    assert cli.main(["mot-de-passe", "--stdin"]) == 0
    assert json.loads(appels[0].content) == {"valeur": valeur}
    assert valeur not in capsys.readouterr().out


def test_password_prompt_never_falls_back_to_echo(parametres, monkeypatch):
    appels = client_simule(monkeypatch, parametres, lambda _: pytest.fail("API called"))
    monkeypatch.setattr(cli.Parametres, "charger", lambda: parametres)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("synthetic"))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pytest.fail("Unsafe fallback"))
    assert cli.main(["mot-de-passe"]) == 1
    assert not appels


def test_runbook_write_preserves_optimistic_hash(parametres, monkeypatch):
    appels = client_simule(
        monkeypatch, parametres, lambda _: httpx.Response(200, json={"nom": "test.md"})
    )
    monkeypatch.setattr(cli.Parametres, "charger", lambda: parametres)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("# Test\n\nVérifier."))
    assert cli.main(["runbooks", "ecrire", "test.md", "--empreinte", "c" * 64]) == 0
    assert json.loads(appels[0].content)["empreinte"] == "c" * 64


def test_failed_job_has_nonzero_exit_status(parametres, monkeypatch):
    client_simule(monkeypatch, parametres, lambda _: httpx.Response(200, json={"statut": "erreur"}))
    monkeypatch.setattr(cli.Parametres, "charger", lambda: parametres)
    assert cli.main(["analyses", "voir", "c" * 32]) == 2


def test_service_install_is_private_local_and_does_not_autostart(parametres, monkeypatch):
    p = parametres
    agent = p.racine / "agents/sre-agent/.venv/bin/sre-agent-graph"
    agent.parent.mkdir(parents=True)
    agent.touch()
    monkeypatch.setattr(cli.Path, "home", lambda: p.racine)
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/bin/systemctl")
    commandes = []

    def lancer(commande, **options):
        commandes.append(commande)
        return subprocess.CompletedProcess(commande, 0)

    monkeypatch.setattr(cli.subprocess, "run", lancer)
    resultat = cli.installer_service(p, demarrer=False, remplacer=False)
    texte = Path(resultat["unite"]).read_text()
    assert "NoNewPrivileges=true" in texte
    assert "PrivateTmp=true" in texte
    assert "KillMode=control-group" in texte
    assert "UMask=0077" in texte
    assert f"WorkingDirectory={p.racine}\n" in texte
    assert p.cle not in texte
    assert commandes == [["systemctl", "--user", "daemon-reload"]]
    assert Path(resultat["unite"]).stat().st_mode & 0o777 == 0o600
    with pytest.raises(cli.ErreurCLI, match="existe déjà"):
        cli.installer_service(p, demarrer=False, remplacer=False)


def test_systemd_path_escaping():
    assert cli.argument_systemd("/tmp/with space/50%/$value") == '"/tmp/with space/50%%/$value"'
    assert cli.argument_systemd("/tmp/$value", commande=True) == '"/tmp/$$value"'
    with pytest.raises(cli.ErreurCLI):
        cli.argument_systemd("/tmp/path\nExecStart=unexpected")
    assert cli.repertoire_systemd("/tmp/with space/50%") == "/tmp/with space/50%%"


def test_voice_status_uses_same_api(parametres, monkeypatch):
    appels = client_simule(
        monkeypatch, parametres, lambda _: httpx.Response(200, json={"local": True})
    )
    args = cli.analyseur().parse_args(["voix", "statut"])
    assert cli.executer(args, parametres)["local"]
    assert appels[0].url.path == "/api/voix/statut"


def test_voice_synthesis_writes_private_file_and_never_stdout_audio(
    parametres, monkeypatch, tmp_path, capsys
):
    audio = b"RIFF-synthetic-binary-audio\x00\xff"
    appels = client_simule(
        monkeypatch,
        parametres,
        lambda _: httpx.Response(200, content=audio, headers={"content-type": "audio/wav"}),
    )
    monkeypatch.setattr(cli.Parametres, "charger", lambda: parametres)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("Bonjour, ceci est un essai."))
    sortie = tmp_path / "voix.wav"
    assert cli.main(["voix", "parler", "--sortie", str(sortie)]) == 0
    assert sortie.read_bytes() == audio
    assert sortie.stat().st_mode & 0o777 == 0o600
    assert json.loads(appels[0].content) == {"texte": "Bonjour, ceci est un essai."}
    assert "synthetic-binary" not in capsys.readouterr().out


def test_voice_transcription_sends_binary_as_base64(parametres, monkeypatch, tmp_path):
    audio = b"\x00\xff\xfe\x81"
    fichier = tmp_path / "audio.webm"
    fichier.write_bytes(audio)
    fichier.chmod(0o600)
    appels = client_simule(
        monkeypatch, parametres, lambda _: httpx.Response(200, json={"texte": "Bonjour"})
    )
    args = cli.analyseur().parse_args(["voix", "transcrire", str(fichier)])
    assert cli.executer(args, parametres)["texte"] == "Bonjour"
    assert appels[0].url.path == "/api/voix/transcrire"
    assert base64.b64decode(json.loads(appels[0].content)["audio"]) == audio


def test_audio_input_private_bounded_regular_and_without_symlink(tmp_path, monkeypatch):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"synthetic")
    audio.chmod(0o644)
    with pytest.raises(cli.ErreurCLI, match="0600"):
        cli.lire_audio(audio)
    audio.chmod(0o600)
    assert cli.lire_audio(audio) == b"synthetic"
    monkeypatch.setattr(cli, "LIMITE_AUDIO", 5)
    with pytest.raises(cli.ErreurCLI, match="8 Mio"):
        cli.lire_audio(audio)
    audio.write_bytes(b"")
    with pytest.raises(cli.ErreurCLI, match="8 Mio"):
        cli.lire_audio(audio)
    lien = tmp_path / "lien"
    lien.symlink_to(audio)
    with pytest.raises(OSError):
        cli.lire_audio(lien)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(cli.ErreurCLI, match="régulier"):
        cli.lire_audio(fifo)


def test_synthesis_limits_and_output_are_explicit(parametres, monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        cli.analyseur().parse_args(["voix", "parler"])
    appels = client_simule(monkeypatch, parametres, lambda _: pytest.fail("API called"))
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("x" * 2001))
    args = cli.analyseur().parse_args(["voix", "parler", "--sortie", str(tmp_path / "audio.wav")])
    with pytest.raises(cli.ErreurCLI):
        cli.executer(args, parametres)
    assert not appels


@pytest.mark.parametrize("content_type,contenu", [("application/json", b"{}"), ("audio/wav", b"")])
def test_synthesis_rejects_non_audio_or_empty_response(
    parametres, monkeypatch, content_type, contenu
):
    client_simule(
        monkeypatch,
        parametres,
        lambda _: httpx.Response(200, content=contenu, headers={"content-type": content_type}),
    )
    with cli.Client(parametres) as client, pytest.raises(cli.ErreurCLI):
        client.appeler("POST", "/api/voix/parler", binaire=True, json={"texte": "Bonjour"})
