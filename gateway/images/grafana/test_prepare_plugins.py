"""Security checks for deterministic public plugin packaging (no signing key)."""

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from prepare_plugins import prepare, source_bundle, verify_bundle


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        (self.source / "dist").mkdir(parents=True)
        (self.source / "main.go").write_text("package main\n")
        (self.source / "dist/fixture_linux_amd64").write_bytes(b"rebuilt executable")
        (self.source / "dist/go_plugin_build_manifest").write_text(
            "fixture source inventory"
        )
        self.archive = self.root / "official.zip"
        self.inputs = self.root / "inputs.json"

    def archive_with(self, extra=None):
        with zipfile.ZipFile(self.archive, "w") as bundle:
            bundle.writestr(
                "prometheus/plugin.json",
                json.dumps(
                    {
                        "id": "prometheus",
                        "info": {"version": "1.0.0"},
                        "executable": "fixture",
                    }
                ),
            )
            bundle.writestr("prometheus/fixture_linux_amd64", b"old executable")
            if extra:
                bundle.writestr(*extra)
        self.inputs.write_text(
            json.dumps(
                {
                    "epoch": 1792490400,
                    "plugins": [
                        {
                            "id": "prometheus",
                            "version": "1.0.0",
                            "derived_version": "1.0.0+reviewed",
                            "archive_sha256": hashlib.sha256(
                                self.archive.read_bytes()
                            ).hexdigest(),
                        }
                    ],
                }
            )
        )

    def bundle(self):
        output = self.root / "prepared/prometheus"
        prepare("prometheus", self.inputs, self.source, self.archive, output)
        return output

    def test_rebuild_replaces_binary_and_preserves_complete_source(self):
        self.archive_with()
        output = self.bundle()
        self.assertEqual(
            (output / "fixture_linux_amd64").read_bytes(), b"rebuilt executable"
        )
        first, second = self.root / "first.tar.gz", self.root / "second.tar.gz"
        source_bundle(self.source, first, 1792490400)
        source_bundle(self.source, second, 1792490400)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        files = {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in output.rglob("*")
            if p.is_file()
        }
        manifest = {"plugin": "prometheus", "version": "1.0.0+reviewed", "files": files}
        body = (
            "-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512\n\n"
            + json.dumps(manifest)
            + "\n-----BEGIN PGP SIGNATURE-----\nfixture: crypto tested in core\n"
        ).encode()
        (output / "MANIFEST.txt").write_bytes(body)
        policy = self.root / "policy.json"
        policy.write_text(
            json.dumps(
                {
                    "prometheus": {
                        "version": manifest["version"],
                        "sha256": hashlib.sha256(body).hexdigest(),
                    }
                }
            )
        )
        verify_bundle(output, policy)
        (output / "unapproved.txt").write_text("unsigned")
        with self.assertRaisesRegex(ValueError, "Rebuilt files differ"):
            verify_bundle(output, policy)
        (output / "unapproved.txt").unlink()
        (output / "MANIFEST.txt").write_bytes(body + b"\n")
        with self.assertRaisesRegex(ValueError, "Manifest bytes differ"):
            verify_bundle(output, policy)

    def test_archive_traversal_is_rejected_even_with_matching_input_digest(self):
        self.archive_with(("prometheus/../../escape", b"forbidden"))
        with self.assertRaisesRegex(ValueError, "Unexpected plugin archive path"):
            self.bundle()
        self.assertFalse((self.root / "escape").exists())

    def test_archive_special_files_are_rejected(self):
        for kind in [0o120000, 0o010000]:
            with self.subTest(kind=kind):
                info = zipfile.ZipInfo("prometheus/special")
                info.external_attr = (kind | 0o777) << 16
                self.archive_with((info, b"/forbidden/source"))
                output = self.root / str(kind)
                with self.assertRaisesRegex(ValueError, "link or special"):
                    prepare(
                        "prometheus", self.inputs, self.source, self.archive, output
                    )

    def test_source_symlink_is_not_followed(self):
        (self.source / "linked").symlink_to(self.root / "private-do-not-read")
        with self.assertRaisesRegex(ValueError, "link or special"):
            source_bundle(self.source, self.root / "refused.tar.gz", 1792490400)


if __name__ == "__main__":
    unittest.main()
