"""Regression for source tampering hidden between inventory passes."""

import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import exporter_sauvegarde as exporter
import inventaire_sauvegarde as inventory


class ExportRaceTests(unittest.TestCase):
    def test_changed_then_restored_payload_is_rejected_before_encryption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backup = root / "backup"
            backup.mkdir(mode=0o700)
            payload = backup / "payload"
            payload.write_bytes(b"GOOD")
            payload.chmod(0o600)
            manifest = {
                "type": "platform-backup-v1",
                "complet": True,
                "integrite": inventory.inventaire(backup),
            }
            (backup / "manifest.json").write_text(json.dumps(manifest))
            (backup / "manifest.json").chmod(0o600)
            recipients = root / "recipients"
            recipients.write_text("age1synthetic")
            recipients.chmod(0o600)
            original = tarfile.TarFile.addfile

            def race(bundle, info, stream=None):
                if info.name != "payload":
                    return original(bundle, info, stream)
                payload.write_bytes(b"EVIL")
                try:
                    return original(bundle, info, stream)
                finally:
                    payload.write_bytes(b"GOOD")

            with (
                patch.object(tarfile.TarFile, "addfile", new=race),
                patch.object(exporter, "age", return_value="/unused/age"),
                patch.object(exporter.subprocess, "run") as encrypt,
                self.assertRaisesRegex(ValueError, "changed during archive"),
            ):
                exporter.chiffrer(backup, recipients, root / "backup.age")
            encrypt.assert_not_called()
            self.assertFalse((root / "backup.age").exists())
            self.assertEqual(payload.read_bytes(), b"GOOD")
            self.assertTrue(
                inventory.verifier_inventaire(backup, manifest)["integrite_verifiee"]
            )
            self.assertFalse(
                any(p.name.startswith("platform-encrypt") for p in root.iterdir())
            )


if __name__ == "__main__":
    os.umask(0o077)
    unittest.main()
