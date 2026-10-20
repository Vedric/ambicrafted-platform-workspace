"""Offline release signing; never used by the image build.

The private GnuPG directory must be outside the checkout and the bundle. Only
public MANIFEST files and their digests are written to the build context.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

FINGERPRINT = "9927b7037e53a8156725792ff5fdd4382c05e115"
KEY_ID = "f5fdd4382c05e115"
ROOT_URLS = ["http://localhost:3000/", "http://127.0.0.1:3000/"]


def sign(private_home: Path, prepared: Path, context: Path) -> None:
    private_home, prepared, context = (
        p.resolve(strict=True) for p in (private_home, prepared, context)
    )
    checkout = context.parents[2]
    if private_home.is_relative_to(checkout) or private_home.is_relative_to(prepared):
        raise ValueError("Signing key must remain outside the checkout and bundle")
    info = private_home.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("Signing directory must be owned by this user and mode 0700")
    inputs = json.loads((context / "plugin-build-inputs.json").read_text())
    policy = {}
    for item in inputs["plugins"]:
        identifier = item["id"]
        if identifier not in {"prometheus", "tempo"}:
            raise ValueError("Unapproved distribution plugin")
        bundle = prepared / identifier
        files = {}
        for path in sorted(bundle.rglob("*")):
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                raise ValueError("Plugin contains a link or special file")
            if path.is_file() and path.relative_to(bundle).as_posix() != "MANIFEST.txt":
                files[path.relative_to(bundle).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        if not files or "plugin.json" not in files:
            raise ValueError("Plugin inventory is incomplete")
        metadata = json.loads((bundle / "plugin.json").read_text())
        if (
            metadata["id"] != identifier
            or metadata["info"]["version"] != item["derived_version"]
        ):
            raise ValueError("Prepared plugin identity/version mismatch")
        payload = {
            "manifestVersion": "2.0.0",
            "signatureType": "private",
            "signedByOrg": "ambicrafted",
            "signedByOrgName": "Ambicrafted local distribution",
            "rootUrls": ROOT_URLS,
            "plugin": identifier,
            "version": item["derived_version"],
            "keyId": KEY_ID,
            "time": inputs["epoch"] * 1000,
            "files": files,
        }
        result = subprocess.run(
            [
                "gpg",
                "--homedir",
                str(private_home),
                "--batch",
                "--no-auto-key-retrieve",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--digest-algo",
                "SHA512",
                "--local-user",
                FINGERPRINT + "!",
                "--armor",
                "--clearsign",
            ],
            input=(json.dumps(payload, indent=2) + "\n").encode(),
            capture_output=True,
            check=True,
        )
        body = result.stdout
        if not body.startswith(b"-----BEGIN PGP SIGNED MESSAGE-----"):
            raise ValueError("Signing did not produce a clearsigned manifest")
        (bundle / "MANIFEST.txt").write_bytes(body)
        (context / identifier / "MANIFEST.txt").write_bytes(body)
        policy[identifier] = {
            "version": item["derived_version"],
            "sha256": hashlib.sha256(body).hexdigest(),
        }
    if set(policy) != {"prometheus", "tempo"}:
        raise ValueError("Distribution must contain exactly its two reviewed plugins")
    (context / "distribution-manifests.json").write_text(
        json.dumps(policy, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_home", type=Path)
    parser.add_argument("prepared", type=Path)
    parser.add_argument("context", type=Path)
    args = parser.parse_args()
    sign(args.private_home, args.prepared, args.context)
