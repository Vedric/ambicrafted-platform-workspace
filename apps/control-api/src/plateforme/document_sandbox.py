"""Linux namespace launcher for the untrusted document parser.

Only the interpreter, its standard library, three parser packages and system
libraries are visible. The API checkout, home, host /proc, sockets and secrets
are never mounted. There is intentionally no unsandboxed fallback.
"""

import importlib.util
import shutil
import sys
from pathlib import Path


class SandboxUnavailable(RuntimeError):
    """The supported OS isolation boundary cannot be established."""


def commande(extension: str) -> list[str]:
    executable = shutil.which("bwrap")
    if sys.platform != "linux" or executable is None:
        raise SandboxUnavailable("Linux, bubblewrap and unprivileged namespaces are required")

    # -I -S ignores site customization, .pth/editable installs and Python env
    # variables. Mount dependencies individually, never all of site-packages.
    runtime = Path(sys.base_prefix).resolve()
    python = Path(sys.executable).resolve()
    try:
        interpreter = python.relative_to(runtime)
    except ValueError:
        raise SandboxUnavailable("The interpreter must belong to its Python runtime") from None
    if runtime in {Path("/"), Path.home()} or sys.prefix == sys.base_prefix:
        # Normal uv venvs have distinct base_prefix and prefix. A standalone
        # installation must be run in a venv; never bind a workspace as runtime.
        raise SandboxUnavailable("A dedicated Python virtual environment is required")

    args = [
        executable,
        "--unshare-all",
        "--unshare-user",  # Mandatory: --unshare-all alone uses user-try.
        "--disable-userns",
        "--assert-userns-disabled",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "HOME",
        "/nonexistent",
        "--ro-bind",
        str(runtime),
        "/runtime",
    ]
    for directory in ("/lib", "/lib64", "/usr/lib", "/usr/lib64"):
        if Path(directory).is_dir():
            args.extend(("--ro-bind", directory, directory))
    for name in ("PIL", "pypdf", "defusedxml"):
        spec = importlib.util.find_spec(name)
        if spec is None or spec.origin is None:
            raise SandboxUnavailable("A required parser package is unavailable")
        source = Path(spec.origin).resolve().parent
        args.extend(("--ro-bind", str(source), f"/packages/{name}"))
        if name == "PIL":
            # Linux Pillow wheels load native codecs with ../pillow.libs RPATH.
            libraries = source.parent / "pillow.libs"
            if libraries.is_dir():
                args.extend(("--ro-bind", str(libraries), "/packages/pillow.libs"))
    args.extend(
        (
            "--ro-bind",
            str(Path(__file__).with_name("document_worker.py").resolve()),
            "/worker.py",
            "--dir",
            "/dev",
            "--ro-bind",
            "/dev/null",
            "/dev/null",
            "--dir",
            "/tmp",
            "--chdir",
            "/",
            "--remount-ro",
            "/",
            "--",
            f"/runtime/{interpreter}",
            "-I",
            "-S",
            "/worker.py",
            extension,
        )
    )
    return args
