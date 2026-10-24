"""Exercise real consumers offline; no production paths, tokens or model downloads."""

import json
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from importlib import metadata
from pathlib import Path
from unittest.mock import patch

import qualify_filelock as contrat
from filelock import FileLock, SoftFileLock, Timeout
from huggingface_hub.utils import WeakFileLock, _fixes
from huggingface_hub.utils._shared_blobs import _shared_blob_lock
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

SITE = Path(sysconfig.get_path("purelib"))


class Gardes(unittest.TestCase):
    def test_base_exacte_et_refus_avant_modification(self):
        fichiers = [*contrat.CONSUMERS, f"{contrat.DIST}/METADATA", f"{contrat.DIST}/RECORD"]
        with tempfile.TemporaryDirectory() as dossier:
            copie = Path(dossier)
            for nom in fichiers:
                destination = copie / nom
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SITE / nom, destination)
            originaux = {nom: (copie / nom).read_bytes() for nom in fichiers}
            sorties = contrat.preparer(copie)
            self.assertEqual(set(sorties), {f"{contrat.DIST}/METADATA", f"{contrat.DIST}/RECORD"})
            for nom in fichiers:
                with self.subTest(fichier=nom):
                    (copie / nom).write_bytes(originaux[nom] + b"\n")
                    avant = {f: (copie / f).read_bytes() for f in fichiers}
                    with self.assertRaises(ValueError):
                        contrat.preparer(copie)
                    self.assertEqual(avant, {f: (copie / f).read_bytes() for f in fichiers})
                    (copie / nom).write_bytes(originaux[nom])
            self.assertEqual(originaux, {f: (copie / f).read_bytes() for f in fichiers})


class Contrat(unittest.TestCase):
    def setUp(self):
        self.temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporaire.cleanup)
        self.racine = Path(self.temporaire.name)

    def test_versions_sources_attestation_et_graphe(self):
        self.assertEqual(metadata.version("filelock"), "4.2.4")
        self.assertEqual(metadata.version("litellm"), "1.104.4")
        rapport = json.loads(Path("/usr/share/ambicrafted/filelock-contract.json").read_text())
        for nom, attendu in {**contrat.CONSUMERS, **rapport["after_sha256"]}.items():
            self.assertEqual(contrat.digest((SITE / nom).read_bytes()), attendu)
        document = (SITE / contrat.DIST / "METADATA").read_bytes()
        self.assertEqual(document.count(contrat.AFTER), 1)
        self.assertNotIn(contrat.BEFORE, document)
        distributions = list(metadata.distributions())
        versions = {canonicalize_name(d.metadata["Name"]): d.version for d in distributions}
        for distribution in distributions:
            for ligne in distribution.requires or []:
                exigence = Requirement(ligne)
                if exigence.marker and not exigence.marker.evaluate({"extra": ""}):
                    continue
                with self.subTest(package=distribution.metadata["Name"], requirement=ligne):
                    version = versions.get(canonicalize_name(exigence.name))
                    self.assertIsNotNone(version)
                    self.assertTrue(exigence.specifier.contains(version, prereleases=True))

    def test_vrai_installateur_litellm_concurrent_et_permissions(self):
        cible = self.racine / "status.py"
        journal = self.racine / "events"
        code = """
import os,sys,time
from pathlib import Path
from litellm.proxy.client.cli.commands.claude_settings import install_statusline_script,write_private_bytes
def write(path, content):
    with open(sys.argv[2], 'a') as f: f.write(f'{os.getpid()}:start\\n')
    time.sleep(0.03)
    write_private_bytes(path, content)
    with open(sys.argv[2], 'a') as f: f.write(f'{os.getpid()}:end\\n')
install_statusline_script(Path(sys.argv[1]), write=write)
"""

        def executer(_):
            return subprocess.run(
                [sys.executable, "-c", code, str(cible), str(journal)],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )

        with ThreadPoolExecutor(max_workers=4) as groupe:
            resultats = list(groupe.map(executer, range(4)))
        for resultat in resultats:
            self.assertEqual(resultat.returncode, 0, resultat.stderr)
        evenements = journal.read_text().splitlines()
        self.assertEqual(len(evenements), 8)
        for i in range(0, 8, 2):
            self.assertTrue(evenements[i].endswith(":start"))
            self.assertEqual(evenements[i].replace(":start", ":end"), evenements[i + 1])
        self.assertEqual(cible.stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(str(cible) + ".lock").stat().st_mode & 0o777, 0o600)
        compile(cible.read_text(), str(cible), "exec")

    def test_timeout_huggingface_puis_reprise(self):
        chemin = self.racine / "cache.lock"
        code = """
import sys,time
from filelock import FileLock
with FileLock(sys.argv[1], mode=0o600):
    print('held', flush=True)
    time.sleep(20)
"""
        with subprocess.Popen(
            [sys.executable, "-c", code, str(chemin)], stdout=subprocess.PIPE, text=True
        ) as processus:
            try:
                self.assertEqual(processus.stdout.readline().strip(), "held")
                debut = time.monotonic()
                with self.assertRaises(Timeout), WeakFileLock(chemin, timeout=0.15):
                    self.fail("Contender entered a held lock")
                self.assertLess(time.monotonic() - debut, 2)
            finally:
                processus.terminate()
                processus.wait(timeout=5)
        with WeakFileLock(chemin, timeout=1) as verrou:
            self.assertTrue(verrou.is_locked)

    def test_huggingface_libere_apres_exception_et_repli_soft(self):
        chemin = self.racine / "cache.lock"
        with self.assertRaisesRegex(RuntimeError, "synthetic"), WeakFileLock(chemin):
            raise RuntimeError("synthetic")
        with FileLock(chemin, timeout=0):
            pass
        chemin.unlink()
        with (
            patch.object(
                _fixes.FileLock,
                "acquire",
                side_effect=NotImplementedError("use SoftFileLock instead"),
            ),
            WeakFileLock(chemin, timeout=1) as verrou,
        ):
            self.assertIsInstance(verrou, SoftFileLock)
            self.assertTrue(verrou.is_locked)
        self.assertFalse(chemin.exists())

    def test_cache_partage_et_symlink_refuse(self):
        cible = self.racine / "blob"
        with _shared_blob_lock(cible):
            cible.write_text("synthetic content")
        with _shared_blob_lock(cible):
            self.assertEqual(cible.read_text(), "synthetic content")
        victime = self.racine / "untouched"
        victime.write_text("preserve")
        chemin = self.racine / "symlink.lock"
        chemin.symlink_to(victime)
        with self.assertRaises(OSError), FileLock(chemin, timeout=0):
            self.fail("Symlink lock accepted")
        self.assertEqual(victime.read_text(), "preserve")


if __name__ == "__main__":
    mode = sys.argv.pop()
    if mode not in ("--preflight", "--qualified"):
        raise SystemExit("Choose --preflight or --qualified")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        Gardes if mode == "--preflight" else Contrat
    )
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
