"""Offline adversarial checks for the optional private host-tool installer."""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import installer_outils_hote as installer


class InstallationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.write_bytes(b"synthetic executable")
        self.destination = self.root / "private/share/tool"
        self.bin = self.root / "private/bin"

    def test_download_rejects_changed_archive(self) -> None:
        with (
            patch.object(
                installer.urllib.request, "urlopen", return_value=io.BytesIO(b"changed")
            ),
            self.assertRaisesRegex(ValueError, "checksum"),
        ):
            installer.download(
                "https://example.invalid/public-tool",
                hashlib.sha256(b"expected").hexdigest(),
                self.root / "archive",
            )
        self.assertFalse(self.bin.exists())

    def test_download_has_a_size_limit(self) -> None:
        with (
            patch.object(installer, "MAX_DOWNLOAD", 10),
            patch.object(
                installer.urllib.request, "urlopen", return_value=io.BytesIO(b"x" * 11)
            ),
            self.assertRaisesRegex(ValueError, "limit"),
        ):
            installer.download(
                "https://example.invalid/public-tool", "0" * 64, self.root / "archive"
            )

    def test_publish_is_idempotent_and_executable(self) -> None:
        first = installer.publish(self.source, self.destination, self.bin)
        self.assertEqual(
            first, installer.publish(self.source, self.destination, self.bin)
        )
        self.assertEqual((self.bin / "tool").resolve(), self.destination)
        self.assertEqual(self.destination.read_bytes(), self.source.read_bytes())
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o755)

    def test_different_existing_command_is_preserved(self) -> None:
        self.bin.mkdir(parents=True)
        foreign = self.bin / "tool"
        foreign.write_bytes(b"operator tool")
        with self.assertRaisesRegex(ValueError, "not managed"):
            installer.publish(self.source, self.destination, self.bin)
        self.assertEqual(foreign.read_bytes(), b"operator tool")

    def test_foreign_symlink_and_destination_are_preserved(self) -> None:
        self.bin.mkdir(parents=True)
        foreign = self.root / "operator"
        foreign.write_bytes(b"operator tool")
        (self.bin / "tool").symlink_to(foreign)
        with self.assertRaisesRegex(ValueError, "elsewhere"):
            installer.publish(self.source, self.destination, self.bin)
        self.assertEqual((self.bin / "tool").resolve(), foreign)
        self.assertEqual(foreign.read_bytes(), b"operator tool")

    def test_changed_managed_binary_is_not_replaced(self) -> None:
        installer.publish(self.source, self.destination, self.bin)
        self.destination.write_bytes(b"modified by operator")
        with self.assertRaisesRegex(ValueError, "differs"):
            installer.publish(self.source, self.destination, self.bin)
        self.assertEqual(self.destination.read_bytes(), b"modified by operator")

    def test_metadata_symlink_is_not_followed(self) -> None:
        metadata = self.root / "receipt"
        target = self.root / "outside"
        metadata.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "metadata"):
            installer.conserver(metadata, b"receipt")
        self.assertFalse(target.exists())

    def test_unsafe_destination_directory_is_refused(self) -> None:
        unsafe = self.root / "unsafe"
        unsafe.mkdir(mode=0o777)
        unsafe.chmod(0o777)
        with self.assertRaisesRegex(ValueError, "another user"):
            installer.directory(unsafe / "subdir")

    def test_symlink_prefix_is_refused(self) -> None:
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            installer.directory(alias / "new")

    def test_age_symlink_member_is_refused_before_execution(self) -> None:
        def download(_url: str, _sha: str, destination: Path) -> None:
            with tarfile.open(destination, "w:gz") as archive:
                member = tarfile.TarInfo("age/age")
                member.type, member.linkname = tarfile.SYMTYPE, "/bin/sh"
                archive.addfile(member)

        previous_umask = os.umask(0o077)
        try:
            with (
                patch.object(installer.platform, "system", return_value="Linux"),
                patch.object(installer.platform, "machine", return_value="x86_64"),
                patch.object(installer, "download", side_effect=download),
                patch.object(installer.subprocess, "run") as run,
                self.assertRaisesRegex(ValueError, "member"),
            ):
                installer.install("age", self.root / "private")
            run.assert_not_called()
        finally:
            os.umask(previous_umask)

    def test_native_windows_is_explicitly_unsupported(self) -> None:
        with (
            patch.object(installer.platform, "system", return_value="Windows"),
            self.assertRaisesRegex(ValueError, "WSL2"),
        ):
            installer.install("age", self.root / "private")


if __name__ == "__main__":
    unittest.main()
