"""Exercise real guard and file planning; privileged commands are substituted."""

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "apt_ci", Path(__file__).with_name("configurer_apt_ci.py")
)
assert spec and spec.loader
apt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apt)


class PreparationAptTests(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        self.racine = Path(self.dossier.name)
        self.sources = self.racine / "ubuntu.sources"
        self.miroirs = self.racine / "apt-mirrors.txt"
        self.delais = self.racine / "99platform-ci-network"
        self.sources.write_bytes(
            b"Types: deb\nURIs: mirror+file:/etc/apt/apt-mirrors.txt\n"
            b"Suites: noble noble-updates noble-backports noble-security\n"
            b"Components: main restricted universe multiverse\n"
            b"Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n"
        )
        self.miroirs.write_bytes(apt.ORIGINAL)
        self.intacts = {
            self.sources: self.sources.read_bytes(),
            self.racine / "keyring.gpg": b"synthetic trust anchor",
            self.racine / "other.sources": b"synthetic unrelated repository",
        }
        for chemin, contenu in self.intacts.items():
            chemin.write_bytes(contenu)
        for nom, valeur in {
            "SOURCES": self.sources,
            "MIROIRS": self.miroirs,
            "DELAIS": self.delais,
            "PROPRIETAIRE_ATTENDU": os.getuid(),
        }.items():
            patch = mock.patch.object(apt, nom, valeur)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.dict(
            os.environ,
            {
                "GITHUB_ACTIONS": "true",
                "RUNNER_ENVIRONMENT": "github-hosted",
                "RUNNER_OS": "Linux",
            },
            clear=True,
        )
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(
            apt.platform,
            "freedesktop_os_release",
            return_value={"ID": "ubuntu", "VERSION_ID": "24.04"},
        )
        self.systeme = patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(apt.subprocess, "run", side_effect=self.commande)
        self.commandes = patch.start()
        self.addCleanup(patch.stop)

    def commande(self, argv, **options):
        self.assertTrue(options["check"])
        self.assertEqual(options["timeout"], 15)
        if argv[0] == "apt-config":
            self.assertEqual(
                argv,
                [
                    "apt-config",
                    "shell",
                    "HTTP_TIMEOUT",
                    "Acquire::http::Timeout",
                    "HTTPS_TIMEOUT",
                    "Acquire::https::Timeout",
                ],
            )
            return subprocess.CompletedProcess(
                argv, 0, "HTTP_TIMEOUT='30'\nHTTPS_TIMEOUT='30'\n"
            )
        if argv[2] == "mv":
            self.assertEqual(
                argv[:5],
                ["sudo", "--non-interactive", "mv", "--no-target-directory", "--"],
            )
            self.assertIn(Path(argv[-1]), (self.miroirs, self.delais))
            Path(argv[-2]).replace(argv[-1])
            return subprocess.CompletedProcess(argv, 0)
        if argv[2] == "rm":
            self.assertEqual(argv[:4], ["sudo", "--non-interactive", "rm", "--"])
            self.assertEqual(Path(argv[-1]).parent, self.racine)
            self.assertIn(".platform-ci-", Path(argv[-1]).name)
            Path(argv[-1]).unlink()
            return subprocess.CompletedProcess(argv, 0)
        self.assertEqual(
            argv[:6],
            [
                "sudo",
                "--non-interactive",
                "install",
                "--owner=root",
                "--group=root",
                "--mode=0644",
            ],
        )
        self.assertEqual(Path(argv[-1]).parent, self.racine)
        self.assertTrue(
            any(
                Path(argv[-1]).name.startswith(f".{p.name}.platform-ci-")
                for p in (self.miroirs, self.delais)
            )
        )
        shutil.copyfile(argv[-2], argv[-1])
        Path(argv[-1]).chmod(0o644)
        return subprocess.CompletedProcess(argv, 0)

    def refuser_sans_ecriture(self, code):
        avant = {p.name: p.read_bytes() for p in self.racine.iterdir() if p.is_file()}
        with self.assertRaises(apt.RefusPreparation) as refus:
            apt.preparer()
        self.assertEqual(refus.exception.code, code)
        self.commandes.assert_not_called()
        self.assertEqual(
            avant,
            {p.name: p.read_bytes() for p in self.racine.iterdir() if p.is_file()},
        )
        return refus.exception

    def test_change_only_official_priorities_and_bounded_transport_settings(self):
        apt.preparer()
        self.assertEqual(self.miroirs.read_bytes(), apt.PREFERENCE)
        self.assertEqual(self.delais.read_bytes(), apt.DELAIS_ATTENDUS)
        for chemin, contenu in self.intacts.items():
            self.assertEqual(chemin.read_bytes(), contenu)
        self.assertEqual(self.commandes.call_count, 5)
        self.commandes.reset_mock()
        apt.preparer()
        self.assertEqual(self.commandes.call_count, 1)  # Read effective values only.

    def test_reject_workstation_self_hosted_and_other_os_before_file_read(self):
        for cle, valeur in (
            ("GITHUB_ACTIONS", "false"),
            ("RUNNER_ENVIRONMENT", "self-hosted"),
            ("RUNNER_ENVIRONMENT", ""),
            ("RUNNER_OS", "Windows"),
        ):
            with (
                self.subTest(cle=cle, valeur=valeur),
                mock.patch.dict(os.environ, {cle: valeur}),
                mock.patch.object(apt, "lire_configuration") as lecture,
            ):
                self.refuser_sans_ecriture(apt.CodeRefus.RUNNER_CONTEXT)
                lecture.assert_not_called()

    def test_reject_unqualified_distribution_before_file_read(self):
        for systeme in (
            {"ID": "debian", "VERSION_ID": "12"},
            {"ID": "ubuntu", "VERSION_ID": "22.04"},
        ):
            with (
                self.subTest(systeme=systeme),
                mock.patch.object(apt, "lire_configuration") as lecture,
            ):
                self.systeme.return_value = systeme
                self.refuser_sans_ecriture(apt.CodeRefus.OS_VERSION)
                lecture.assert_not_called()

    def test_reject_unknown_duplicate_or_missing_mirror(self):
        for contenu in (
            apt.ORIGINAL.replace(b"azure.archive.ubuntu.com", b"unreviewed.invalid"),
            apt.ORIGINAL + apt.ORIGINAL,
            apt.ORIGINAL.splitlines(keepends=True)[0],
            apt.ORIGINAL.replace(b"priority:1", b"priority:99"),
        ):
            with self.subTest(contenu=contenu):
                self.miroirs.write_bytes(contenu)
                self.refuser_sans_ecriture(apt.CodeRefus.MIRRORS_LAYOUT)

    def test_reject_wrong_or_mixed_source_wiring(self):
        original = self.sources.read_bytes()
        for contenu in (
            original.replace(b"mirror+file:", b"file:"),
            original + b"\nURIs: https://unreviewed.invalid/\n",
            original + b"\nuris: https://unreviewed.invalid/\n",
            original.replace(b"\nSuites:", b"\n https://unreviewed.invalid/\nSuites:"),
        ):
            with self.subTest(contenu=contenu):
                self.sources.write_bytes(contenu)
                self.refuser_sans_ecriture(apt.CodeRefus.SOURCES_URIS)

    def test_reject_existing_unrelated_config_before_changing_mirrors(self):
        self.delais.write_bytes(b'Acquire::https::Timeout "180";\n')
        self.refuser_sans_ecriture(apt.CodeRefus.TIMEOUTS_LAYOUT)

    def test_reject_symlink_public_write_or_wrong_owner(self):
        self.miroirs.chmod(0o666)
        self.refuser_sans_ecriture(apt.CodeRefus.FILE_MODE)
        self.miroirs.chmod(0o644)
        with mock.patch.object(apt, "PROPRIETAIRE_ATTENDU", os.getuid() + 1):
            self.refuser_sans_ecriture(apt.CodeRefus.FILE_OWNER)
        self.miroirs.rename(self.racine / "other-mirrors")
        self.miroirs.symlink_to(self.racine / "other-mirrors")
        self.refuser_sans_ecriture(apt.CodeRefus.FILE_TYPE)

    def test_reject_dangling_timeout_symlink_before_any_write(self):
        self.delais.symlink_to(self.racine / "absent")
        self.refuser_sans_ecriture(apt.CodeRefus.FILE_TYPE)

    def test_privileged_failure_stops_without_claiming_success(self):
        self.commandes.side_effect = subprocess.CalledProcessError(1, ["synthetic"])
        with mock.patch("builtins.print"):
            self.assertEqual(apt.main(), 1)
        self.assertEqual(self.commandes.call_count, 1)
        self.assertEqual(self.miroirs.read_bytes(), apt.ORIGINAL)

    def test_reject_overridden_effective_timeout(self):
        initial = self.commande

        def remplacer(argv, **options):
            result = initial(argv, **options)
            if argv[0] == "apt-config":
                result.stdout = "HTTP_TIMEOUT='180'\nHTTPS_TIMEOUT='180'\n"
            return result

        self.commandes.side_effect = remplacer
        with self.assertRaises(apt.RefusPreparation) as refus:
            apt.preparer()
        self.assertEqual(refus.exception.code, apt.CodeRefus.EFFECTIVE_TIMEOUTS)

    def test_preserve_stricter_runner_timeout_and_report_actual_values(self):
        initial = self.commande

        def remplacer(argv, **options):
            result = initial(argv, **options)
            if argv[0] == "apt-config":
                result.stdout = "HTTP_TIMEOUT='15'\nHTTPS_TIMEOUT='15'\n"
            return result

        self.commandes.side_effect = remplacer
        self.assertEqual(apt.preparer(), {"http": 15, "https": 15})
        with mock.patch("builtins.print") as sortie:
            self.assertEqual(apt.main(), 0)
        self.assertEqual(
            json.loads(sortie.call_args.args[0]),
            {
                "ok": True,
                "primary": "https://archive.ubuntu.com/ubuntu/",
                "apt_connection_and_inactivity_limit_seconds": 30,
                "apt_effective_timeout_seconds": {"http": 15, "https": 15},
            },
        )
        for chemin, contenu in self.intacts.items():
            self.assertEqual(chemin.read_bytes(), contenu)

    def test_effective_timeout_positive_boundaries_and_assignment_order(self):
        for http, https in ((1, 30), (30, 1), (15, 15), (30, 30)):
            with self.subTest(http=http, https=https):
                self.assertEqual(
                    apt.lire_delais_effectifs(
                        f"HTTPS_TIMEOUT='{https}'\nHTTP_TIMEOUT='{http}'\n"
                    ),
                    {"http": http, "https": https},
                )

    def test_reject_unbounded_missing_duplicate_or_malformed_effective_timeout(self):
        for sortie in (
            "",
            "HTTP_TIMEOUT='15'\n",
            "HTTP_TIMEOUT='15'\nHTTP_TIMEOUT='15'\nHTTPS_TIMEOUT='15'\n",
            "HTTP_TIMEOUT='15'\nHTTPS_TIMEOUT='15'\nUNEXPECTED='15'\n",
            "HTTP_TIMEOUT='15'\nHTTPS_TIMEOUT='15'\n\n",
            *(
                f"HTTP_TIMEOUT='{valeur}'\nHTTPS_TIMEOUT='15'\n"
                for valeur in ("0", "-1", "31", "180", "1.5", "15;false", "１５")
            ),
            "HTTP_TIMEOUT=\"15\"\nHTTPS_TIMEOUT='15'\n",
            " HTTP_TIMEOUT='15'\nHTTPS_TIMEOUT='15'\n",
            "HTTP_TIMEOUT='15'\nHTTPS_TIMEOUT=15\n",
        ):
            with self.subTest(sortie=sortie):
                with self.assertRaises(apt.RefusPreparation) as refus:
                    apt.lire_delais_effectifs(sortie)
                self.assertEqual(refus.exception.code, apt.CodeRefus.EFFECTIVE_TIMEOUTS)

    def test_partial_privileged_copy_preserves_destination_and_removes_only_its_temp(
        self,
    ):
        initial = self.commande

        def interrompre(argv, **options):
            if argv[2] == "install":
                Path(argv[-1]).write_bytes(b"partial synthetic copy")
                raise subprocess.CalledProcessError(1, argv)
            return initial(argv, **options)

        self.commandes.side_effect = interrompre
        with mock.patch("builtins.print"):
            self.assertEqual(apt.main(), 1)
        self.assertEqual(self.miroirs.read_bytes(), apt.ORIGINAL)
        self.assertFalse(list(self.racine.glob(".*.platform-ci-*")))
        self.assertFalse(self.delais.exists())
        for chemin, contenu in self.intacts.items():
            self.assertEqual(chemin.read_bytes(), contenu)
        self.assertEqual(self.commandes.call_count, 2)

    def test_metadata_diagnostics_identify_each_logical_target_without_its_path(self):
        self.delais.write_bytes(apt.DELAIS_ATTENDUS)
        for chemin, cible in (
            (self.sources, "sources"),
            (self.miroirs, "mirrors"),
            (self.delais, "timeouts"),
        ):
            with self.subTest(cible=cible):
                chemin.chmod(0o666)
                with mock.patch("builtins.print") as sortie:
                    self.assertEqual(apt.main(), 1)
                self.assertEqual(
                    json.loads(sortie.call_args.args[0]),
                    {
                        "ok": False,
                        "error_type": "RefusPreparation",
                        "code": "file_mode",
                        "target": cible,
                        "uid": os.getuid(),
                        "mode": 0o666,
                        "regular": True,
                        "symlink": False,
                        "canonical": True,
                    },
                )
                self.commandes.assert_not_called()
                chemin.chmod(0o644)

    def test_owner_and_symlink_diagnostics_keep_distinct_codes_and_metadata(self):
        with mock.patch.object(apt, "PROPRIETAIRE_ATTENDU", os.getuid() + 1):
            refus = self.refuser_sans_ecriture(apt.CodeRefus.FILE_OWNER)
        self.assertEqual(refus.diagnostic()["uid"], os.getuid())
        self.assertEqual(refus.diagnostic()["target"], "sources")
        self.delais.symlink_to(self.racine / "absent")
        refus = self.refuser_sans_ecriture(apt.CodeRefus.FILE_TYPE)
        self.assertEqual(refus.diagnostic()["target"], "timeouts")
        self.assertIs(refus.diagnostic()["symlink"], True)
        self.assertIs(refus.diagnostic()["regular"], False)

    def test_noncanonical_parent_is_rejected_without_printing_target_path(self):
        lien = self.racine / "parent-link"
        lien.symlink_to(self.racine, target_is_directory=True)
        with mock.patch.object(apt, "SOURCES", lien / self.sources.name):
            refus = self.refuser_sans_ecriture(apt.CodeRefus.FILE_PATH)
        self.assertEqual(refus.diagnostic()["target"], "sources")
        self.assertIs(refus.diagnostic()["canonical"], False)
        self.assertNotIn(str(self.racine), json.dumps(refus.diagnostic()))

    def test_missing_file_reports_only_static_target_and_numeric_errno(self):
        self.sources.unlink()
        with mock.patch("builtins.print") as sortie:
            self.assertEqual(apt.main(), 1)
        self.assertEqual(
            json.loads(sortie.call_args.args[0]),
            {
                "ok": False,
                "error_type": "RefusPreparation",
                "code": "file_read",
                "target": "sources",
                "errno": 2,
            },
        )
        self.commandes.assert_not_called()

    def test_diagnostic_whitelist_excludes_arbitrary_values(self):
        secret = "synthetic-private-marker"
        refus = apt.RefusPreparation(
            apt.CodeRefus.FILE_MODE,
            cible=secret,
            metadonnees={"mode": secret, "uid": os.getuid(), "content": secret},
        )
        self.assertEqual(
            refus.diagnostic(),
            {
                "ok": False,
                "error_type": "RefusPreparation",
                "code": "file_mode",
                "uid": os.getuid(),
            },
        )
        self.commandes.side_effect = subprocess.CalledProcessError(
            1, [secret], output=secret, stderr=secret
        )
        with mock.patch("builtins.print") as sortie:
            self.assertEqual(apt.main(), 1)
        self.assertEqual(
            json.loads(sortie.call_args.args[0]),
            {"ok": False, "error_type": "CalledProcessError"},
        )
        self.assertNotIn(secret, sortie.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
