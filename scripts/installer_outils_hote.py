"""Install qualified public host tools privately, with pinned archive hashes and no sudo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

AGE = {
    "x86_64": (
        "amd64",
        "bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377",
    ),
    "aarch64": (
        "arm64",
        "c6878a324421b69e3e20b00ba17c04bc5c6dab0030cfe55bf8f68fa8d9e9093a",
    ),
}
BWRAP_SHA = "2461f1beee9cb04c8942739fe1a2b37e7b7c2a3d518f0779dc75f9245baa3094"
BWRAP_URL = "https://archive.ubuntu.com/ubuntu/pool/main/b/bubblewrap/bubblewrap_0.9.0-1ubuntu0.3_amd64.deb"
MAX_DOWNLOAD = 32 * 1024**2


def directory(path: Path) -> None:
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("Absolute directory without symlinks required")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    for current in (path, *path.parents):
        info = current.lstat()
        # /tmp may contain a private temporary destination; its sticky bit is required.
        if (not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022) and not (
            stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX
        ):
            raise ValueError("Installation path is writable by another user")
    if path.stat().st_uid != os.getuid():
        raise ValueError("Installation directory must belong to the current user")


def download(url: str, sha256: str, destination: Path) -> None:
    digest, size = hashlib.sha256(), 0
    with (
        urllib.request.urlopen(url, timeout=30) as response,
        destination.open("xb") as output,
    ):
        while block := response.read(1024 * 1024):
            size += len(block)
            if size > MAX_DOWNLOAD:
                raise ValueError("Tool archive exceeds limit")
            digest.update(block)
            output.write(block)
    if digest.hexdigest() != sha256:
        raise ValueError("Tool archive checksum mismatch")


def conserver(path: Path, content: bytes) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise ValueError("Existing tool metadata differs; preserve it for review")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(content)


def publish(source: Path, destination: Path, bindir: Path) -> dict:
    directory(destination.parent)
    directory(bindir)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if destination.exists() or destination.is_symlink():
        if (
            destination.is_symlink()
            or not destination.is_file()
            or hashlib.sha256(destination.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("Existing installed tool differs; preserve it for review")
    else:
        fd = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755
        )
        with source.open("rb") as input_file, os.fdopen(fd, "wb") as output:
            shutil.copyfileobj(input_file, output)
            output.flush()
            os.fsync(output.fileno())
        destination.chmod(0o755)
    link = bindir / destination.name
    if link.is_symlink():
        if link.resolve() != destination:
            raise ValueError(
                "Existing command points elsewhere; preserve it for review"
            )
    elif link.exists():
        raise ValueError("Existing command is not managed by this installer")
    else:
        link.symlink_to(destination)
    return {"command": str(link), "sha256": digest}


def install(tool: str, prefix: Path) -> dict:
    if platform.system() != "Linux":
        raise ValueError("This installer supports Linux; Windows requires WSL2")
    directory(prefix)
    bindir, storage = prefix / "bin", prefix / "share/ambicrafted-tools"
    directory(storage)
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="install-", dir=storage) as temporary:
        stage = Path(temporary)
        if tool == "age":
            if platform.machine() not in AGE:
                raise ValueError("Unqualified age CPU architecture")
            architecture, digest = AGE[platform.machine()]
            url = f"https://github.com/FiloSottile/age/releases/download/v1.3.1/age-v1.3.1-linux-{architecture}.tar.gz"
            archive = stage / "age.tar.gz"
            download(url, digest, archive)
            destination = storage / f"age/1.3.1-linux-{architecture}"
            directory(destination)
            installed = []
            with tarfile.open(archive, "r:gz") as bundle:
                for name in ("age", "age-keygen"):
                    member = bundle.getmember("age/" + name)
                    if not member.isfile() or member.size > MAX_DOWNLOAD:
                        raise ValueError("Invalid executable member")
                    payload = bundle.extractfile(member)
                    if payload is None:
                        raise ValueError("Missing executable member")
                    source = stage / name
                    with payload, source.open("xb") as output:
                        shutil.copyfileobj(payload, output)
                    installed.append(publish(source, destination / name, bindir))
                license_member = bundle.getmember("age/LICENSE")
                if not license_member.isfile() or license_member.size > 128 * 1024:
                    raise ValueError("Invalid license member")
                license_payload = bundle.extractfile(license_member)
                if license_payload is None:
                    raise ValueError("Missing license")
                with license_payload:
                    license_text = license_payload.read()
                conserver(destination / "LICENSE", license_text)
            expected, version_command = "v1.3.1", destination / "age"
        else:
            release = platform.freedesktop_os_release()
            if (release.get("ID"), release.get("VERSION_ID"), platform.machine()) != (
                "ubuntu",
                "24.04",
                "x86_64",
            ):
                raise ValueError(
                    "Private bubblewrap package is qualified only on Ubuntu24.04 amd64"
                )
            extractor = shutil.which("dpkg-deb")
            if not extractor:
                raise ValueError("dpkg-deb is required")
            archive = stage / "bubblewrap.deb"
            url, digest = BWRAP_URL, BWRAP_SHA
            download(url, digest, archive)
            unpacked = stage / "unpacked"
            subprocess.run(
                [extractor, "--extract", str(archive), str(unpacked)],
                capture_output=True,
                check=True,
                timeout=30,
            )
            destination = storage / "bubblewrap/0.9.0-1ubuntu0.3-amd64"
            directory(destination)
            installed = [
                publish(unpacked / "usr/bin/bwrap", destination / "bwrap", bindir)
            ]
            conserver(
                destination / "copyright",
                (unpacked / "usr/share/doc/bubblewrap/copyright").read_bytes(),
            )
            expected, version_command = "bubblewrap 0.9.0", destination / "bwrap"
        version = (
            subprocess.run(
                [str(version_command), "--version"],
                capture_output=True,
                check=True,
                timeout=10,
            )
            .stdout.decode()
            .strip()
        )
        if version != expected:
            raise ValueError("Installed executable version mismatch")
        receipt = {
            "tool": tool,
            "version": version,
            "source": url,
            "archive_sha256": digest,
            "executables": installed,
            "kernel_permissions_validated": False,
        }
        conserver(destination / "receipt.json", json.dumps(receipt, indent=2).encode())
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=("age", "bubblewrap"))
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                install(args.tool, args.prefix.expanduser().absolute()), indent=2
            )
        )
        return 0
    except Exception as error:  # noqa: BLE001 -- no proxy credentials or downloaded bytes in logs.
        print(
            json.dumps(
                {
                    "error": type(error).__name__,
                    "message": "Private tool installation failed; existing commands were preserved.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
