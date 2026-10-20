# Qualified host tools

The full local platform targets **Linux on Ubuntu 24.04 LTS amd64**, including
Ubuntu 24.04 under **WSL2**, with systemd user services, Docker Compose and the
required local inference hardware. Windows native and macOS are not qualified
server targets. A browser on those systems can use the local UI where its
loopback networking permits. An age ARM64 installer is available; it does not
constitute qualification of the complete platform on ARM64.

The dedicated Neo4j image uses the vendor UBI10 runtime. Its amd64 variant
requires an **x86-64-v3** CPU; see the [memory image profile](../gateway/images/neo4j/README.md).
Do not assume a VM exposes every CPU feature available on its physical host.

## Mandatory document isolation

Document parsing requires **bubblewrap**, **libseccomp2**, a project virtual
environment, and working unprivileged Linux namespaces. There is no unisolated
fallback. The normal administrator-managed Ubuntu installation is:

```sh
sudo apt-get update
sudo apt-get install bubblewrap libseccomp2
```

The qualified package on the reference workstation is
`bubblewrap 0.9.0-1ubuntu0.3` (Ubuntu 24.04 amd64), with `bwrap --version`
reporting `bubblewrap 0.9.0`. Keep Ubuntu security updates enabled; rerun the
functional check after changing the package or kernel.

If administrator access is unavailable and the system libraries already exist,
the repository provides an optional **private** installation of that exact
official Ubuntu package:

```sh
uv run --no-project --python 3.14 python scripts/installer_outils_hote.py bubblewrap
export PATH="$HOME/.local/bin:$PATH"
```

This downloads the package over HTTPS and checks SHA-256
`2461f1beee9cb04c8942739fe1a2b37e7b7c2a3d518f0779dc75f9245baa3094`
before unpacking. The binary and copyright are kept under
`~/.local/share/ambicrafted-tools/bubblewrap/0.9.0-1ubuntu0.3-amd64/`,
with a link in `~/.local/bin`. It does not install libraries, request root,
modify AppArmor, enable kernel namespaces or alter existing foreign commands.
The full source URL, archive hash and binary hash are in its `receipt.json`.

An Ubuntu AppArmor profile or other host policy may permit `/usr/bin/bwrap`
and reject a privately installed binary. In that case use the distribution
package through the host administrator. **Do not disable AppArmor, seccomp,
user-namespace restrictions globally, or the parser isolation to obtain a
passing check.** Installing a binary is insufficient evidence that isolation works.

After syncing the API environment, run:

```sh
uv sync --locked --project apps/control-api
./plateforme prerequis
```

This command uses the same private-tool PATH as the installed console service.
It verifies Linux, the virtual environment, bubblewrap, libseccomp, and performs
a real isolated extraction of a one-character synthetic text file. It reads no
operator documents and invokes no model. A missing prerequisite returns a
nonzero exit code. The API refuses to start and the service installer refuses to
write a new unit if this check fails.

The systemd service preserves `NoNewPrivileges=true`, `PrivateTmp=true` and
`ProtectSystem=full`; it must still allow the namespaces used by bubblewrap.
The application reruns the functional check **inside the service** at startup.
Additional machine-specific restrictions can therefore fail safely even if
the interactive check succeeded. WSL2 must have systemd enabled and an active
user manager. Keeping user timers running outside a login session is a separate
host lifecycle decision; a timer is not a powered-off-machine backup.

See [document security](DOCUMENT-SECURITY.md) for the isolation boundary and
the production readiness check.

## Optional encrypted recovery export

Encrypted backup export requires the qualified **age v1.3.1**, not whichever
older version an operating-system package happens to provide:

```sh
uv run --no-project --python 3.14 python scripts/installer_outils_hote.py age
export PATH="$HOME/.local/bin:$PATH"
age --version
uv run --project apps/control-api --locked python -m plateforme.prerequis --avec-export
```

The installer supports Linux amd64 and ARM64 and verifies the official release
archive before extracting its two executables and license:

| Official age v1.3.1 archive | SHA-256 |
|---|---|
| `age-v1.3.1-linux-amd64.tar.gz` | `bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377` |
| `age-v1.3.1-linux-arm64.tar.gz` | `c6878a324421b69e3e20b00ba17c04bc5c6dab0030cfe55bf8f68fa8d9e9093a` |

Versioned binaries, license and receipt live under
`~/.local/share/ambicrafted-tools/age/`; managed command links live in
`~/.local/bin`. `--prefix /absolute/private/directory` selects a test or CI
installation. Repeating installation with identical artifacts is safe.
An existing different binary, link or receipt is preserved and causes failure;
review it explicitly rather than replacing an operator installation silently.
Downloads are bounded and checksums are embedded in source, so a release change
requires review.

For GitHub Actions, run the same installer and add `$HOME/.local/bin` to
`$GITHUB_PATH`. The console and backup unit generators include that directory in
their explicit PATH. Reinstall existing units after updating the checkout:

```sh
./plateforme installer-service --remplacer
uv run --locked scripts/plateforme.py installer-retention
```

The console replacement above does not restart an existing process.
`--demarrer` enables and starts the service if inactive; it does not reload an
already running process. After current jobs finish, apply an updated unit with
`systemctl --user restart ambicrafted-console.service`.
If scheduled export is configured, `./plateforme prerequis` also requires age.
The [recovery procedure](RECOVERY.md) explains recipient custody, encrypted
staging, copying to an independently protected destination and restoration.
No off-host destination or private identity is provisioned automatically.

Official references: [bubblewrap](https://github.com/containers/bubblewrap),
[Ubuntu package](https://packages.ubuntu.com/noble/bubblewrap),
[age v1.3.1](https://github.com/FiloSottile/age/releases/tag/v1.3.1),
[systemd execution isolation](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html).
