"""Real isolated subprocesses exercise output bounds, cancellation and lifecycle."""

import asyncio
import json
import sys

import pytest
from sre_agent.graphe import VERSION_CONTRAT

from plateforme.depot import Conflit


def commande_python(monkeypatch, moteur, code):
    monkeypatch.setattr(
        moteur, "commande", lambda analyse, decision: ([sys.executable, "-c", code], {})
    )


async def attendre_processus(moteur, identifiant):
    async with asyncio.timeout(3):
        while identifiant not in moteur.processus:
            await asyncio.sleep(0.005)
    return moteur.processus[identifiant]


def test_file_bornee_sans_enregistrement_surnumeraire(moteur):
    for _ in range(moteur.p.taille_file):
        moteur.creer("Titre", "Alerte synthétique", "cli")
    with pytest.raises(Conflit):
        moteur.creer("Refusée", "Ne pas conserver", "cli")
    assert moteur.depot.lister()["total"] == moteur.p.taille_file
    assert len(moteur.alertes) == moteur.p.taille_file


def test_decision_file_pleine_ne_change_pas_statut(moteur):
    moteur.depot.creer("attente", "Titre", "graphe", {"version_contrat": VERSION_CONTRAT}, "cli")
    moteur.depot.changer("attente", "en_attente_humain")
    for _ in range(moteur.p.taille_file):
        moteur.creer("Titre", "Alerte", "cli")
    with pytest.raises(Conflit, match="File pleine"):
        moteur.decider("attente", True, "cli")
    assert moteur.depot.obtenir("attente")["statut"] == "en_attente_humain"


@pytest.mark.asyncio
async def test_execution_stdin_progression_et_sortie_contrat(moteur, monkeypatch):
    code = """import json, sys
alerte = sys.stdin.read()
assert alerte == "Alerte synthétique transmise par stdin"
print('SRE_EVENT {"stade":"modele"}', file=sys.stderr)
print('SRE_EVENT {"stade":"outil"}', file=sys.stderr)
print('SRE_EVENT {"stade":"inconnu"}', file=sys.stderr)
print(json.dumps({"statut":"en_attente_humain", "message":"Diagnostic à valider."}))
sys.exit(10)
"""
    commande_python(monkeypatch, moteur, code)
    identifiant = moteur.creer("Titre", "Alerte synthétique transmise par stdin", "cli")["id"]
    await moteur.executer(identifiant, None)
    resultat = moteur.depot.obtenir(identifiant)
    assert resultat["statut"] == "en_attente_humain"
    assert resultat["rapport"]["diagnostic"] is None
    assert [e["stade"] for e in resultat["evenements"]] == [
        "demarrage",
        "modele",
        "outil",
        "termine",
    ]
    assert resultat["duree_s"] > 0
    assert not moteur.alertes and not moteur.processus


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "print('pas du JSON')",
        'print(\'{"statut":"complet"}\'); raise SystemExit(10)',
        'print(\'{"statut":"arbitraire"}\')',
        "import sys; sys.stderr.write('confidentiel synthétique'); raise SystemExit(1)",
    ],
)
async def test_sortie_invalide_ou_code_incoherent_produit_erreur_masquee(moteur, monkeypatch, code):
    commande_python(monkeypatch, moteur, code)
    identifiant = moteur.creer("Titre", "Alerte synthétique", "cli")["id"]
    await moteur.executer(identifiant, None)
    resultat = moteur.depot.obtenir(identifiant)
    assert resultat["statut"] == "erreur"
    assert "confidentiel synthétique" not in json.dumps(resultat)
    assert "pas du JSON" not in json.dumps(resultat)
    assert not moteur.alertes and not moteur.processus


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flux,code",
    [
        ("stdout", "import os; os.write(1, b'x' * 1_000_001)"),
        ("stderr", "import os; [os.write(2, b'x' * 1000 + b'\\n') for _ in range(501)]"),
        ("stderr-longue-ligne", "import os; os.write(2, b'x' * 100_000)"),
    ],
)
async def test_sorties_subprocess_bornees_sans_blocage(moteur, monkeypatch, flux, code):
    commande_python(monkeypatch, moteur, code)
    identifiant = moteur.creer("Titre", "Alerte", "cli")["id"]
    async with asyncio.timeout(10):
        await moteur.executer(identifiant, None)
    assert moteur.depot.obtenir(identifiant)["statut"] == "erreur"
    assert not moteur.processus


@pytest.mark.asyncio
@pytest.mark.parametrize("code_sortie,statut", [(0, "complet"), (1, "erreur")])
async def test_operations_masquent_sortie_et_propagation_echec(
    moteur, monkeypatch, code_sortie, statut
):
    commande_python(
        monkeypatch, moteur, f"print('Contenu synthétique privé'); raise SystemExit({code_sortie})"
    )
    identifiant = moteur.creer("Vérifier", "", "cli", "verifier")["id"]
    await moteur.executer(identifiant, None)
    resultat = moteur.depot.obtenir(identifiant)
    assert resultat["statut"] == statut
    assert "Contenu synthétique privé" not in json.dumps(resultat)


@pytest.mark.asyncio
async def test_annulation_tue_processus_et_ne_reecrit_pas_statut(moteur, monkeypatch):
    commande_python(monkeypatch, moteur, "import time; time.sleep(30)")
    identifiant = moteur.creer("Titre", "Alerte synthétique", "cli")["id"]
    travail = asyncio.create_task(moteur.executer(identifiant, None))
    processus = await attendre_processus(moteur, identifiant)
    await moteur.annuler(identifiant, "cli")
    async with asyncio.timeout(5):
        await travail
    assert processus.returncode is not None
    assert moteur.depot.obtenir(identifiant)["statut"] == "annule"
    assert not moteur.alertes and not moteur.processus


@pytest.mark.asyncio
async def test_annule_en_file_ne_demarre_jamais_processus(moteur, monkeypatch):
    def interdit(*_):
        raise AssertionError("Une analyse annulée ne doit pas produire de commande.")

    monkeypatch.setattr(moteur, "commande", interdit)
    identifiant = moteur.creer("Titre", "Alerte", "cli")["id"]
    await moteur.annuler(identifiant, "cli")
    await moteur.executer(identifiant, None)
    assert moteur.depot.obtenir(identifiant)["statut"] == "annule"


@pytest.mark.asyncio
async def test_fermeture_nettoie_processus_et_memoires(moteur, monkeypatch):
    commande_python(monkeypatch, moteur, "import time; time.sleep(30)")
    await moteur.demarrer()
    identifiant = moteur.creer("Titre", "Alerte", "cli")["id"]
    processus = await attendre_processus(moteur, identifiant)
    moteur.creer("En attente", "Autre alerte", "cli")
    await moteur.fermer()
    assert processus.returncode is not None
    assert not moteur.alertes and not moteur.processus
    assert moteur.depot.obtenir(identifiant)["statut"] == "interrompu"
    assert all(a["statut"] == "interrompu" for a in moteur.depot.lister()["elements"])


@pytest.mark.asyncio
async def test_worker_serialise_execution_sans_recouvrement(moteur, monkeypatch):
    actifs = 0
    maximum = 0
    ordres = []

    async def execution(identifiant, decision):
        nonlocal actifs, maximum
        actifs += 1
        maximum = max(maximum, actifs)
        ordres.append(identifiant)
        await asyncio.sleep(0.005)
        actifs -= 1

    monkeypatch.setattr(moteur, "executer", execution)
    await moteur.demarrer()
    attendus = [moteur.creer("Titre", "Alerte", "cli")["id"] for _ in range(10)]
    async with asyncio.timeout(3):
        await moteur.file.join()
    await moteur.fermer()
    assert maximum == 1 and ordres == attendus


@pytest.mark.asyncio
async def test_annulation_pendant_creation_processus_bloque_envoi_alerte(
    moteur, monkeypatch, tmp_path
):
    preuve = tmp_path / "alerte-recue"
    code = f"import sys; from pathlib import Path; a=sys.stdin.read(); Path({str(preuve)!r}).write_text(a) if a else None"
    commande_python(monkeypatch, moteur, code)
    vrai_spawn = asyncio.create_subprocess_exec
    commence, autoriser_retour = asyncio.Event(), asyncio.Event()

    async def spawn_retarde(*args, **kwargs):
        processus = await vrai_spawn(*args, **kwargs)
        commence.set()
        await autoriser_retour.wait()
        return processus

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_retarde)
    identifiant = moteur.creer("Titre", "ALERTE_SYNTHETIQUE_ANNULEE", "cli")["id"]
    travail = asyncio.create_task(moteur.executer(identifiant, None))
    async with asyncio.timeout(3):
        await commence.wait()
        await moteur.annuler(identifiant, "cli")
        autoriser_retour.set()
        await travail
    assert moteur.depot.obtenir(identifiant)["statut"] == "annule"
    assert not preuve.exists(), "L'alerte annulée a été transmise au processus lancé tardivement."


@pytest.mark.asyncio
async def test_annulation_suppression_pendant_spawn_ne_tue_pas_worker(moteur, monkeypatch):
    commande_python(
        monkeypatch, moteur, 'import sys; sys.stdin.read(); print(\'{"statut":"complet"}\')'
    )
    vrai_spawn = asyncio.create_subprocess_exec
    commence, autoriser_retour = asyncio.Event(), asyncio.Event()

    async def spawn_retarde(*args, **kwargs):
        processus = await vrai_spawn(*args, **kwargs)
        commence.set()
        await autoriser_retour.wait()
        return processus

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_retarde)
    await moteur.demarrer()
    identifiant = moteur.creer("Titre", "Alerte synthétique", "cli")["id"]
    async with asyncio.timeout(3):
        await commence.wait()
        await moteur.annuler(identifiant, "cli")
        moteur.depot.supprimer(identifiant, "cli")
        autoriser_retour.set()
        await moteur.file.join()
    assert moteur.tache is not None and not moteur.tache.done(), (
        "Une suppression concurrente a tué le worker."
    )
    suivant = moteur.creer("Suivant", "Alerte synthétique suivante", "cli")["id"]
    async with asyncio.timeout(3):
        await moteur.file.join()
    assert moteur.depot.obtenir(suivant)["statut"] == "complet"
    await moteur.fermer()


def test_commandes_graphes_sans_alerte_dans_argv(moteur):
    executable = moteur.p.racine / "agents/sre-agent/.venv/bin/sre-agent-graph"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n")
    analyse = moteur.creer("Titre", "CONTENU_ALERTE_SYNTHETIQUE", "cli")
    commande, env = moteur.commande(analyse, None)
    assert "CONTENU_ALERTE_SYNTHETIQUE" not in " ".join(commande)
    assert commande[0] == str(executable)
    assert "--reprendre" not in commande
    assert env["SRE_ALIAS_RAISONNEMENT"] == "local"
    approuver, _ = moteur.commande(analyse, True)
    refuser, _ = moteur.commande(analyse, False)
    assert approuver[-2:] == ["--reprendre", "oui"]
    assert refuser[-2:] == ["--reprendre", "non"]
    assert (moteur.racine / analyse["id"]).stat().st_mode & 0o777 == 0o700


@pytest.mark.asyncio
@pytest.mark.parametrize("ignore_term", [False, True])
async def test_cancel_after_leader_exit_closes_descendant_pipes_and_accepts_next_job(
    moteur, monkeypatch, tmp_path, ignore_term
):
    import contextlib
    import os
    import signal

    ready = tmp_path / "descendant-ready"
    code = f"""import os, signal, sys, time
from pathlib import Path
sys.stdin.read()
if os.fork() == 0:
    if {ignore_term!r}:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path({str(ready)!r}).write_text(str(os.getpid()))
    time.sleep(60)
    os._exit(0)
print('{{"statut":"complet"}}', flush=True)
"""
    commande_python(monkeypatch, moteur, code)
    await moteur.demarrer()
    identifier = moteur.creer("Descendant fixture", "Synthetic", "cli")["id"]
    process = await attendre_processus(moteur, identifier)
    try:
        async with asyncio.timeout(3):
            while process.returncode is None or not ready.exists():
                await asyncio.sleep(0.005)
        assert moteur.inference.locked()
        await moteur.annuler(identifier, "cli")
        # The exited leader still owns descendant pipe writers. Cancellation
        # must close them before releasing the serial engine to new work.
        async with asyncio.timeout(2):
            await moteur.file.join()
        assert not moteur.inference.locked()
        assert moteur.depot.obtenir(identifier)["statut"] == "annule"
        commande_python(monkeypatch, moteur, 'print(\'{"statut":"complet"}\')')
        next_id = moteur.creer("Next job", "Synthetic", "cli")["id"]
        async with asyncio.timeout(3):
            await moteur.file.join()
        assert moteur.depot.obtenir(next_id)["statut"] == "complet"
    finally:
        # This is the group created by the fixture; never touch another job.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await moteur.fermer()
