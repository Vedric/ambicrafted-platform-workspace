"""Credential lifecycle failures must not weaken or overwrite existing configuration."""

import json
import secrets
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from dotenv import dotenv_values
from securiser_services import NOMS, preparer


@unittest.skipUnless(
    shutil.which("htpasswd"), "apache2-utils required for real bcrypt provisioning"
)
class ServicesPrives(unittest.TestCase):
    def setUp(self):
        self.temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporaire.cleanup)
        self.racine = Path(self.temporaire.name)
        (self.racine / "gateway").mkdir()

    def test_generation_stable_separee_et_non_affichee(self):
        resultat = preparer(self.racine)
        avant = dotenv_values(self.racine / ".env")
        self.assertEqual(set(avant), set(NOMS))
        self.assertEqual(len(set(avant.values())), 3)
        self.assertEqual(avant, dotenv_values(self.racine / "gateway/.env"))
        self.assertTrue(all(v not in json.dumps(resultat) for v in avant.values()))
        preparer(self.racine)
        self.assertEqual(avant, dotenv_values(self.racine / ".env"))
        self.assertEqual(stat.S_IMODE((self.racine / ".env").stat().st_mode), 0o600)
        self.assertEqual(
            stat.S_IMODE((self.racine / "gateway/.service-auth").stat().st_mode), 0o700
        )

    def test_desaccord_sans_modification(self):
        preparer(self.racine)
        chemin = self.racine / "gateway/.env"
        chemin.write_text("QDRANT_API_KEY=" + secrets.token_urlsafe(48) + "\n")
        avant = {p: p.read_bytes() for p in (chemin, self.racine / ".env")}
        with self.assertRaisesRegex(ValueError, "incohérents"):
            preparer(self.racine)
        self.assertTrue(all(p.read_bytes() == b for p, b in avant.items()))

    def test_env_public_refuse_sans_modification(self):
        chemin = self.racine / ".env"
        chemin.write_text("EXISTING=preserve\n")
        chemin.chmod(0o644)
        with self.assertRaises(ValueError):
            preparer(self.racine)
        self.assertEqual(chemin.read_text(), "EXISTING=preserve\n")
        self.assertFalse((self.racine / "gateway/.env").exists())

    def test_liens_refuses_avant_ecriture(self):
        cible = self.racine / "preserve"
        cible.write_text("intact")
        for nom in (".env", "gateway/.env", "gateway/.service-auth"):
            with self.subTest(nom=nom):
                chemin = self.racine / nom
                if chemin.is_dir():
                    shutil.rmtree(chemin)
                chemin.symlink_to(cible)
                with self.assertRaises(ValueError):
                    preparer(self.racine)
                chemin.unlink()
                self.assertEqual(cible.read_text(), "intact")

    def test_mount_secret_symlink_refuse(self):
        preparer(self.racine)
        chemin = self.racine / "gateway/.service-auth/web.yml"
        chemin.unlink()
        cible = self.racine / "preserve"
        cible.write_text("intact")
        chemin.symlink_to(cible)
        avant = (self.racine / ".env").read_bytes()
        with self.assertRaises(ValueError):
            preparer(self.racine)
        self.assertEqual(cible.read_text(), "intact")
        self.assertEqual((self.racine / ".env").read_bytes(), avant)


if __name__ == "__main__":
    unittest.main()
