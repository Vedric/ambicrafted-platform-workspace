"""Prepare auditable plugin bundles without access to any signing key.

Inputs are immutable public archives. The Docker build verifies signed manifests
after this deterministic preparation; release signing is a separate offline step.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify_bundle(bundle, policy):
    """Reject differences from the signed inventory before core crypto tests."""
    approved = json.loads(policy.read_text())[bundle.name]
    body = (bundle / "MANIFEST.txt").read_bytes()
    if sha256(body) != approved["sha256"]:
        raise ValueError("Manifest bytes differ from the compiled release pin")
    text = body.decode()
    payload = text.split("\n\n", 1)[1].split("\n-----BEGIN PGP SIGNATURE-----", 1)[0]
    manifest = json.loads(payload)
    if manifest["plugin"] != bundle.name or manifest["version"] != approved["version"]:
        raise ValueError("Signed manifest identity does not match release policy")
    actual = {}
    for path in sorted(bundle.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Plugin contains a link or special file")
        if path.is_file() and path.relative_to(bundle).as_posix() != "MANIFEST.txt":
            actual[path.relative_to(bundle).as_posix()] = sha256(path.read_bytes())
    if actual != manifest["files"]:
        changed = sorted(
            key
            for key in actual.keys() | manifest["files"].keys()
            if actual.get(key) != manifest["files"].get(key)
        )
        raise ValueError(
            "Rebuilt files differ from the signed release: " + ", ".join(changed)
        )


def extract_contract(archive, inventory, destination):
    manifest = json.loads(inventory.read_text())
    if sha256(archive.read_bytes()) != manifest["archive_sha256"]:
        raise ValueError("Protocol source archive does not match its pin")
    source_prefix = "tempo-" + manifest["revision"] + "/"
    target = destination / "internal/tempopb"
    target.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive) as source:
        for entry in manifest["files"]:
            path = PurePosixPath(entry["upstream_path"])
            relative = PurePosixPath(entry["destination"])
            if (
                path.is_absolute()
                or ".." in path.parts
                or relative.is_absolute()
                or ".." in relative.parts
            ):
                raise ValueError("Unsafe protocol source path")
            if not str(path).startswith("pkg/tempopb/") or not str(relative).startswith(
                "internal/tempopb/"
            ):
                raise ValueError("Protocol source outside the reviewed contract")
            member = source.getmember(source_prefix + str(path))
            if not member.isfile():
                raise ValueError("Protocol input must be an ordinary file")
            before = source.extractfile(member).read()
            after = before.replace(
                b"github.com/grafana/tempo/pkg/tempopb",
                b"github.com/grafana/grafana-tempo-datasource/internal/tempopb",
            )
            if (
                sha256(before) != entry["source_sha256"]
                or sha256(after) != entry["derived_sha256"]
            ):
                raise ValueError(
                    "Protocol source transformation differs from its inventory"
                )
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(after)
        license_member = source.getmember(source_prefix + "LICENSE")
        if not license_member.isfile():
            raise ValueError("Protocol source license is unavailable")
        (target / "LICENSE").write_bytes(source.extractfile(license_member).read())
    shutil.copyfile(inventory, target / "SOURCE-INVENTORY.json")


def source_bundle(source, output, epoch):
    with (
        output.open("xb") as destination,
        gzip.GzipFile(
            filename="", mode="wb", fileobj=destination, mtime=epoch
        ) as compressed,
        tarfile.open(fileobj=compressed, mode="w|") as archive,
    ):
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if relative.parts[0] in {"dist", ".git"}:
                continue
            if path.is_symlink() or (not path.is_file() and not path.is_dir()):
                raise ValueError("Backend source contains a link or special file")
            if not path.is_file():
                continue
            info = tarfile.TarInfo(str(relative))
            info.size = path.stat().st_size
            info.mtime = epoch
            info.mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
            with path.open("rb") as stream:
                archive.addfile(info, stream)


def prepare(identifier, inputs, source, archive, output):
    settings = json.loads(inputs.read_text())
    item = next(x for x in settings["plugins"] if x["id"] == identifier)
    if sha256(archive.read_bytes()) != item["archive_sha256"]:
        raise ValueError("Official plugin archive does not match its pin")
    output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as bundle:
        seen = set()
        for member in bundle.infolist():
            path = PurePosixPath(member.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0] != identifier
            ):
                raise ValueError("Unexpected plugin archive path")
            if str(path) in seen:
                raise ValueError("Plugin archive contains a duplicate path")
            seen.add(str(path))
            mode = (member.external_attr >> 16) & 0o170000
            if mode not in {0, 0o100000, 0o040000}:
                raise ValueError("Plugin archive contains a link or special file")
            if member.is_dir():
                continue
            relative = Path(*path.parts[1:])
            if relative.as_posix() == "MANIFEST.txt":
                continue
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(member))
            target.chmod(0o755 if target.name.endswith("_linux_amd64") else 0o644)
    metadata_path = output / "plugin.json"
    metadata = json.loads(metadata_path.read_text())
    if metadata["id"] != identifier or metadata["info"]["version"] != item["version"]:
        raise ValueError("Official plugin identity/version differs from catalogue")
    metadata["info"]["version"] = item["derived_version"]
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    binary = metadata["executable"] + "_linux_amd64"
    shutil.copyfile(source / "dist" / binary, output / binary)
    (output / binary).chmod(0o755)
    shutil.copyfile(
        source / "dist/go_plugin_build_manifest", output / "go_plugin_build_manifest"
    )
    source_bundle(source, output / "backend-source.tar.gz", settings["epoch"])
    (output / "SOURCE-PROVENANCE.json").write_text(json.dumps(item, indent=2) + "\n")
    (output / "DISTRIBUTION.md").write_text(
        "# Ambicrafted private distribution\n\n"
        "This is a modified backend, privately signed by Ambicrafted, not a Grafana Labs signed release.\n"
        "The frontend comes from the checksum-pinned official archive. The backend uses its exact\n"
        "source revision with reviewed dependency updates; complete modified backend source is\n"
        "included in backend-source.tar.gz. Upstream attribution and AGPL-3.0 licenses are preserved.\n"
        "The exact public signing key and approved manifest digests are compiled into this distribution.\n"
    )
    if identifier == "tempo":
        contract = json.loads(
            (source / "internal/tempopb/SOURCE-INVENTORY.json").read_text()
        )
        (output / "PROTOBUF-SOURCE-INVENTORY.json").write_text(
            json.dumps(contract, indent=2) + "\n"
        )
        # Retain an ordinary SPDX source component for the actual upstream
        # protocol snapshot. It is not a fabricated Go module version.
        spdx = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "Tempo protobuf source contract",
            "documentNamespace": "https://ambicrafted.invalid/spdx/tempo-protobuf/"
            + contract["revision"],
            "creationInfo": {
                "creators": ["Organization: Ambicrafted"],
                "created": "2026-10-20T10:00:00Z",
            },
            "packages": [
                {
                    "name": "grafana/tempo",
                    "SPDXID": "SPDXRef-TempoProtocol",
                    "versionInfo": contract["version"],
                    "downloadLocation": contract["source"],
                    "licenseConcluded": "AGPL-3.0-only",
                    "licenseDeclared": "AGPL-3.0-only",
                    "filesAnalyzed": False,
                    "sourceInfo": "Only pkg/tempopb is included; exact original/derived file hashes are in PROTOBUF-SOURCE-INVENTORY.json. Server and storage implementations are excluded.",
                    "checksums": [
                        {
                            "algorithm": "SHA256",
                            "checksumValue": contract["archive_sha256"],
                        }
                    ],
                    "externalRefs": [
                        {
                            "referenceCategory": "PACKAGE-MANAGER",
                            "referenceType": "purl",
                            "referenceLocator": "pkg:github/grafana/tempo@v"
                            + contract["version"]
                            + "#pkg/tempopb",
                        }
                    ],
                }
            ],
            "relationships": [
                {
                    "spdxElementId": "SPDXRef-DOCUMENT",
                    "relationshipType": "DESCRIBES",
                    "relatedSpdxElement": "SPDXRef-TempoProtocol",
                }
            ],
        }
        (output / "tempo-protobuf.spdx.json").write_text(
            json.dumps(spdx, indent=2) + "\n"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    contract = subcommands.add_parser("contract")
    contract.add_argument("archive", type=Path)
    contract.add_argument("inventory", type=Path)
    contract.add_argument("source", type=Path)
    bundle = subcommands.add_parser("bundle")
    bundle.add_argument("plugin", choices=("prometheus", "tempo"))
    bundle.add_argument("inputs", type=Path)
    bundle.add_argument("source", type=Path)
    bundle.add_argument("archive", type=Path)
    bundle.add_argument("output", type=Path)
    verify = subcommands.add_parser("verify")
    verify.add_argument("bundle", type=Path)
    verify.add_argument("policy", type=Path)
    args = parser.parse_args()
    if args.command == "contract":
        extract_contract(args.archive, args.inventory, args.source)
    elif args.command == "bundle":
        prepare(args.plugin, args.inputs, args.source, args.archive, args.output)
    else:
        verify_bundle(args.bundle, args.policy)
