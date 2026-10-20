"""Real kernel boundary tests; no mocked filesystem/network enforcement."""

import asyncio
import base64
import errno
import io
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image

from plateforme import document_sandbox, document_worker, documents
from plateforme.documents import extraire


def probe(monkeypatch, tmp_path, code):
    """Replace only the trusted worker entrypoint in this test's private mount."""
    source = Path(document_worker.__file__).read_text()
    source = source.replace('if __name__ == "__main__":', "if False:")
    worker = tmp_path / "document_worker.py"
    worker.write_text(source + "\n" + code)
    monkeypatch.setattr(document_sandbox, "__file__", str(tmp_path / "document_sandbox.py"))


def output(expression):
    return (
        "print(json.dumps({'kind': 'text', 'truncated': False, "
        f"'text': json.dumps({expression})}}), flush=True)\n"
    )


@pytest.mark.asyncio
async def test_native_code_cannot_access_host_files_network_processes_or_fds(monkeypatch, tmp_path):
    # The file is readable by this account; refusal must come from the sandbox,
    # not from a chmod fixture or the former Python-only audit hook.
    secret = tmp_path / "synthetic-only.env"
    secret.write_text("SYNTHETIC_CANARY_NOT_A_REAL_SECRET")
    monkeypatch.setenv("SYNTHETIC_HOST_VARIABLE", "must-not-enter-the-parser")
    code = f"""
import os
import socket
limiter_ressources()
limiter_appels_systeme()
libc = ctypes.CDLL(None, use_errno=True)
results = {{}}
for key, filename in [
    ("host_file", {str(secret)!r}),
    ("host_home", {str(Path.home())!r}),
    ("host_proc", "/proc/1/root"),
    ("host_socket", "/var/run/docker.sock"),
]:
    ctypes.set_errno(0)
    result = libc.open(filename.encode(), os.O_RDONLY)
    results[key] = [result, ctypes.get_errno()]
for key, filename in [
    ("root_write", "/escaped"),
    ("tmp_write", "/tmp/escaped"),
    ("runtime_write", "/runtime/escaped"),
]:
    ctypes.set_errno(0)
    result = libc.open(filename.encode(), os.O_WRONLY | os.O_CREAT, 0o600)
    results[key] = [result, ctypes.get_errno()]
for key, call in [
    ("tcp_socket", lambda: libc.socket(socket.AF_INET, socket.SOCK_STREAM, 0)),
    ("unix_socket", lambda: libc.socket(socket.AF_UNIX, socket.SOCK_STREAM, 0)),
    ("fork", lambda: libc.fork()),
    ("new_namespace", lambda: libc.unshare(0x10000000)),
    ("exec", lambda: libc.execve(b"/runtime/bin/python3.14", None, None)),
]:
    ctypes.set_errno(0)
    result = call()
    results[key] = [result, ctypes.get_errno()]
buffer = ctypes.create_string_buffer(4)
ctypes.set_errno(0)
results["inherited_fd"] = [libc.read(200, buffer, 4), ctypes.get_errno()]
results["environment"] = dict(os.environ)
"""
    probe(monkeypatch, tmp_path, code + output("results"))
    fd = os.open(secret, os.O_RDONLY)
    os.dup2(fd, 200, inheritable=True)
    try:
        response = await extraire("probe.txt", base64.b64encode(b"synthetic").decode())
    finally:
        os.close(200)
        os.close(fd)
    results = json.loads(response["text"])
    for key in ("host_file", "host_home", "host_proc", "host_socket"):
        assert results[key] == [-1, errno.ENOENT], (key, results[key])
    for key in ("root_write", "tmp_write", "runtime_write"):
        assert results[key] == [-1, errno.EROFS], (key, results[key])
    for key in ("tcp_socket", "unix_socket", "fork", "new_namespace", "exec"):
        assert results[key] == [-1, errno.EPERM], (key, results[key])
    assert results["inherited_fd"] == [-1, errno.EBADF]
    assert results["environment"] == {"LANG": "C.UTF-8", "HOME": "/nonexistent", "PWD": "/"}
    assert secret.read_text() == "SYNTHETIC_CANARY_NOT_A_REAL_SECRET"


@pytest.mark.asyncio
@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
async def test_native_image_codecs_work_inside_the_real_boundary(format):
    data = io.BytesIO()
    Image.new("RGB", (160, 80), color="blue").save(data, format)
    result = await extraire(f"photo.{format.lower()}", base64.b64encode(data.getvalue()).decode())
    assert result["kind"] == "image"
    assert result["width"] == 160 and result["height"] == 80


@pytest.mark.asyncio
async def test_missing_sandbox_fails_closed_before_spawning(monkeypatch):
    monkeypatch.setattr(document_sandbox.shutil, "which", lambda _: None)
    with pytest.raises(HTTPException) as error:
        await extraire("example.txt", "eA==")
    assert error.value.status_code == 503
    assert "bubblewrap" in error.value.detail


@pytest.mark.asyncio
async def test_non_linux_fails_closed(monkeypatch):
    monkeypatch.setattr(document_sandbox.sys, "platform", "darwin")
    with pytest.raises(HTTPException) as error:
        await extraire("example.txt", "eA==")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_missing_seccomp_fails_closed_without_parsing(monkeypatch, tmp_path):
    probe(
        monkeypatch,
        tmp_path,
        "def limiter_appels_systeme():\n    raise OSError('unavailable')\nmain()\n",
    )
    with pytest.raises(HTTPException) as error:
        await extraire("example.txt", "eA==")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_output_flood_is_bounded_and_worker_reaped(monkeypatch, tmp_path):
    # Simulate a compromised parser bypassing the result format, writing more
    # than the pipe limit forever. The parent must stop at MAX_OUTPUT.
    probe(
        monkeypatch,
        tmp_path,
        "limiter_ressources()\nlimiter_appels_systeme()\n"
        "while True:\n    sys.stdout.buffer.write(b'x' * 65536)\n",
    )
    monkeypatch.setattr(documents, "MAX_OUTPUT", 131072)
    processes = []
    spawn = asyncio.create_subprocess_exec

    async def capture(*args, **kwargs):
        process = await spawn(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    with pytest.raises(HTTPException) as error:
        await extraire("example.txt", "eA==")
    assert error.value.status_code == 422
    assert "output" in error.value.detail
    assert processes[0].returncode is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("during_spawn", [False, True])
@pytest.mark.parametrize("repeated", [False, True])
async def test_cancellation_reaps_worker_even_during_spawn(
    monkeypatch, tmp_path, during_spawn, repeated
):
    probe(
        monkeypatch,
        tmp_path,
        "limiter_ressources()\nlimiter_appels_systeme()\nimport time\ntime.sleep(60)\n",
    )
    processes = []
    entered = asyncio.Event()
    release = asyncio.Event()
    spawn = asyncio.create_subprocess_exec

    async def capture(*args, **kwargs):
        process = await spawn(*args, **kwargs)
        processes.append(process)
        entered.set()
        if during_spawn:
            await release.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    task = asyncio.create_task(extraire("example.txt", "eA=="))
    await asyncio.wait_for(entered.wait(), 5)
    if not during_spawn:
        await asyncio.sleep(0.1)
    task.cancel()
    if repeated:
        await asyncio.sleep(0)
        task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 5)
    assert processes[0].returncode is not None


@pytest.mark.asyncio
async def test_deadline_kills_unresponsive_worker(monkeypatch, tmp_path):
    probe(
        monkeypatch,
        tmp_path,
        "limiter_ressources()\nlimiter_appels_systeme()\nimport time\ntime.sleep(60)\n",
    )
    monkeypatch.setattr(documents, "PROCESS_TIMEOUT", 0.1)
    with pytest.raises(HTTPException) as error:
        await extraire("example.txt", "eA==")
    assert error.value.status_code == 422
    assert "time limit" in error.value.detail


def test_launch_mounts_no_workspace_home_host_proc_or_environment():
    args = document_sandbox.commande(".txt")
    sources = [args[index + 1] for index, arg in enumerate(args) if arg == "--ro-bind"]
    assert str(Path.home()) not in sources
    assert "/proc" not in sources and "/" not in sources
    assert str(Path.cwd()) not in sources
    assert not any(source.endswith("site-packages") for source in sources)
    assert "--unshare-net" not in args  # Implied by --unshare-all.
    assert "--unshare-all" in args and "--unshare-user" in args
    assert "--disable-userns" in args and "--clearenv" in args
    assert "--share-net" not in args and "--bind" not in args


@pytest.mark.asyncio
async def test_real_pdf_text_extraction_inside_the_boundary():
    # Small valid PDF assembled locally: no external documents or test services.
    stream = b"BT /F1 12 Tf 40 100 Td (Synthetic incident report) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(data)
    data.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
    result = await extraire("incident.pdf", base64.b64encode(data).decode())
    assert "[Page 1]" in result["text"]
    assert "Synthetic incident report" in result["text"]


@pytest.mark.asyncio
async def test_kernel_memory_cpu_and_file_limits_are_installed(monkeypatch, tmp_path):
    probe(
        monkeypatch,
        tmp_path,
        "import resource\n"
        "limiter_ressources()\nlimiter_appels_systeme()\n"
        "results = {name: resource.getrlimit(getattr(resource, name)) for name in "
        "['RLIMIT_AS', 'RLIMIT_CPU', 'RLIMIT_CORE', 'RLIMIT_FSIZE', 'RLIMIT_NOFILE']}\n"
        + output("results"),
    )
    result = await extraire("probe.txt", "eA==")
    assert json.loads(result["text"]) == {
        "RLIMIT_AS": [1024**3, 1024**3],
        "RLIMIT_CPU": [12, 12],
        "RLIMIT_CORE": [0, 0],
        "RLIMIT_FSIZE": [0, 0],
        "RLIMIT_NOFILE": [64, 64],
    }


@pytest.mark.asyncio
async def test_bubblewrap_setup_failure_is_explicit_without_fallback(monkeypatch):
    original = document_sandbox.commande(".txt")
    monkeypatch.setattr(documents, "commande", lambda _: [original[0], "--unknown-option"])
    with pytest.raises(HTTPException) as error:
        await extraire("example.txt", "eA==")
    assert error.value.status_code == 503


def test_upload_admission_is_global_across_conversations_and_recovers(client, bearer, monkeypatch):
    identifiers = [
        client.post("/api/conversations", headers=bearer, json={}).json()["id"] for _ in range(2)
    ]
    entered = threading.Event()
    release = threading.Event()
    calls = []

    async def blocked(name, content):
        calls.append(name)
        entered.set()
        assert await asyncio.to_thread(release.wait, 5)
        return {"kind": "text", "text": "Synthetic", "truncated": False}

    monkeypatch.setattr("plateforme.conversation_routes.extraire", blocked)
    body = {"nom": "synthetic.txt", "contenu": "eA=="}
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(
            client.post, f"/api/conversations/{identifiers[0]}/pieces", headers=bearer, json=body
        )
        try:
            assert entered.wait(5)
            response = client.post(
                f"/api/conversations/{identifiers[1]}/pieces", headers=bearer, json=body
            )
            assert response.status_code == 409
            assert len(calls) == 1
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 201
    assert (
        client.post(
            f"/api/conversations/{identifiers[1]}/pieces", headers=bearer, json=body
        ).status_code
        == 201
    )


def test_unavailable_sandbox_persists_nothing_and_releases_upload_lock(client, bearer, monkeypatch):
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    lookup = document_sandbox.shutil.which
    monkeypatch.setattr(document_sandbox.shutil, "which", lambda _: None)
    body = {"nom": "synthetic.txt", "contenu": "eA=="}
    assert (
        client.post(
            f"/api/conversations/{identifier}/pieces", headers=bearer, json=body
        ).status_code
        == 503
    )
    assert client.get(f"/api/conversations/{identifier}", headers=bearer).json()["pieces"] == []
    monkeypatch.setattr(document_sandbox.shutil, "which", lookup)
    assert (
        client.post(
            f"/api/conversations/{identifier}/pieces", headers=bearer, json=body
        ).status_code
        == 201
    )
