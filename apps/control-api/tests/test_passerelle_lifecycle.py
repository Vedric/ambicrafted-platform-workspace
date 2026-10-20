"""Raw stdio lifecycle regressions with real gateway/SDK children and synthetic tools."""

import concurrent.futures
import fcntl
import json
import os
import selectors
import signal
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

BACKEND = """import asyncio,os,time
from pathlib import Path
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
root=Path(os.environ['FIXTURE_ROOT']); kind=os.environ['FIXTURE_BACKEND']
(root/(kind+'.pid')).write_text(str(os.getpid()))
time.sleep(float(os.environ.get('FIXTURE_DELAY','0')))
mcp=MCPServer(kind)
read=ToolAnnotations(read_only_hint=True,destructive_hint=False,idempotent_hint=True,open_world_hint=False)
@mcp.tool(annotations=read)
def list_runbooks()->dict[str,str]:return {'fixture':'safe'}
@mcp.tool(annotations=read)
def plateforme_sante()->dict[str,str]:return {'fixture':'safe'}
@mcp.tool(annotations=read)
async def read_runbook(nom:str)->str:
 (root/'tool.started').touch()
 try: await asyncio.sleep(30)
 finally: (root/'tool.cancelled').touch()
 return 'fixture'
mcp.run()
"""


class Probe:
    def __init__(self, directory, delay=0, restarts=1, cli=False, large_response=False):
        self.path = directory
        self.path.mkdir(mode=0o700)
        self.backend = self.path / "backend.py"
        self.backend.write_text(
            BACKEND.replace(
                "{'fixture':'safe'}",
                "{'fixture':'é🚀'*50_000}"
                if large_response == "unicode"
                else "{'fixture':'x'*300_000}",
            )
            if large_response
            else BACKEND
        )
        self.entry = self.path / "gateway.py"
        self.entry.write_text(f"""import asyncio,logging,os
from pathlib import Path
from mcp import StdioServerParameters
from plateforme.passerelle import ConfigurationBackend,Passerelle
root=Path({str(self.path)!r})
(root/'gateway.pid').write_text(str(os.getpid()))
logging.disable(logging.CRITICAL)
def definitions(_profil=None):
 return [ConfigurationBackend(name,StdioServerParameters(command={sys.executable!r},args=[{str(self.backend)!r}],env={{'FIXTURE_ROOT':str(root),'FIXTURE_BACKEND':name,'FIXTURE_DELAY':str({delay}) if name=='controle' else '0'}})) for name in ('runbooks','controle')]
async def main():
 for index in range({restarts}):
  (root/'generation').write_text(str(index))
  await Passerelle(definitions()).executer()
if {cli!r}:
 from plateforme import passerelle
 passerelle.configurations=definitions
 passerelle.main()
else:
 asyncio.run(main())
""")
        self.error = (self.path / "stderr.log").open("wb")
        self.proc = subprocess.Popen(
            [sys.executable, str(self.entry)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.error,
            start_new_session=True,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        os.set_blocking(self.proc.stdout.fileno(), False)
        self.buffer = b""
        self.observed = {}
        self.start = time.monotonic()

    def collect(self):
        for file in self.path.glob("*.pid"):
            try:
                pid = int(file.read_text())
                stat = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
                self.observed[(file.stem, pid)] = stat[19]
            except OSError, ValueError:
                pass

    def wait_file(self, file, content=None, timeout=10):
        end = time.monotonic() + timeout
        while True:
            self.collect()
            p = self.path / file
            if p.exists() and (content is None or p.read_text() == content):
                return
            if self.proc.poll() is not None:
                raise RuntimeError("gateway exited before fixture boundary")
            if time.monotonic() > end:
                raise TimeoutError("fixture boundary deadline")
            time.sleep(0.01)

    def send(self, obj):
        self.proc.stdin.write(json.dumps(obj).encode() + b"\n")
        self.proc.stdin.flush()

    def receive(self, timeout=10):
        end = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            self.collect()
            if time.monotonic() > end:
                raise TimeoutError("protocol deadline")
            for key, _ in self.selector.select(0.05):
                block = os.read(key.fileobj.fileno(), 65536)
                if not block:
                    raise EOFError("gateway stdout closed")
                self.buffer += block
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def initialize(self):
        self.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "synthetic-lifecycle", "version": "1.0"},
                },
            }
        )
        result = self.receive()
        if result.get("id") != 1 or "result" not in result:
            raise RuntimeError("initialize contract failed")
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def exit(self, timeout=10):
        end = time.monotonic() + timeout
        while self.proc.poll() is None:
            self.collect()
            if time.monotonic() > end:
                raise TimeoutError("signal shutdown deadline")
            time.sleep(0.01)
        remaining = []
        for (name, pid), birth in self.observed.items():
            try:
                stat = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
                if stat[19] == birth:
                    remaining.append(
                        {"name": name, "pid": pid, "state": stat[0], "pgid": int(stat[2])}
                    )
            except OSError:
                pass
        if remaining:
            raise RuntimeError("fixture child survivor: " + json.dumps(remaining))
        return self.proc.returncode

    def cleanup(self):
        before = []
        for (name, pid), birth in self.observed.items():
            try:
                stat = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
                if stat[19] == birth:
                    before.append({"name": name, "pid": pid, "state": stat[0]})
                    os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(timeout=5)
        if not self.proc.stdin.closed:
            self.proc.stdin.close()
        if not self.proc.stdout.closed:
            self.proc.stdout.close()
        self.selector.close()
        self.error.close()
        return before


def verify_case(directory, case):
    p = Probe(
        directory,
        delay=30 if case in {"sigterm-init", "sigint-init"} else 0,
        restarts=2 if case == "restart" else 1,
        cli=case.startswith("sigint") or case == "oversize",
        large_response="unicode"
        if case == "stdout-resume-utf8"
        else case in {"stdout-backpressure", "stdout-resume"},
    )
    try:
        if case in {"sigterm-init", "sigint-init"}:
            p.wait_file("controle.pid")
            p.wait_file("runbooks.pid")
        else:
            p.initialize()
        if case in {"sigterm-idle", "sigint-idle", "restart"}:
            time.sleep(0.25)
        if case in {"sigterm-active", "sigint-active"}:
            p.send(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "runbooks__read_runbook", "arguments": {"nom": "slow.md"}},
                }
            )
            p.wait_file("tool.started")
        if case in {"stdout-backpressure", "stdout-resume", "stdout-resume-utf8"}:
            p.send(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "runbooks__list_runbooks", "arguments": {}},
                }
            )
            # Observe the actual OS pipe full: the client is deliberately not
            # reading a response that is larger than this pipe's capacity.
            descriptor = p.proc.stdout.fileno()
            capacity = fcntl.fcntl(descriptor, fcntl.F_GETPIPE_SZ)
            deadline = time.monotonic() + 10
            while True:
                available = int.from_bytes(
                    fcntl.ioctl(descriptor, termios.FIONREAD, bytes(4)), sys.byteorder
                )
                if available == capacity:
                    break
                assert time.monotonic() < deadline, "response never filled the client pipe"
                time.sleep(0.01)
            if case in {"stdout-resume", "stdout-resume-utf8"}:
                response = p.receive()
                assert response["id"] == 2
                expected = "é🚀" * 50_000 if case == "stdout-resume-utf8" else "x" * 300_000
                assert response["result"]["structuredContent"] == {"fixture": expected}
        if case == "stdin-eof":
            p.proc.stdin.close()
        elif case == "stdout-closed":
            p.selector.unregister(p.proc.stdout)
            p.proc.stdout.close()
            p.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        elif case == "oversize":
            from plateforme.stdio_posix import MAX_FRAME_BYTES

            try:
                p.proc.stdin.write(b"synthetic-private-payload" + b"x" * MAX_FRAME_BYTES + b"\n")
                p.proc.stdin.flush()
            except BrokenPipeError:
                pass
        else:
            os.kill(p.proc.pid, signal.SIGINT if case.startswith("sigint") else signal.SIGTERM)
        if case == "restart":
            p.wait_file("generation", "1")
            p.initialize()
            time.sleep(0.25)
            os.kill(p.proc.pid, signal.SIGTERM)
        assert p.exit() == (1 if case in {"stdout-closed", "oversize"} else 0)
        if case == "oversize":
            assert (p.path / "stderr.log").read_text() == (
                "Passerelle MCP indisponible. Vérifier l'installation locale.\n"
            )
        elif case.startswith("sigint"):
            assert (p.path / "stderr.log").read_text() == ""
    finally:
        survivors = p.cleanup()
    assert survivors == []


@pytest.mark.parametrize(
    "case",
    [
        "stdin-eof",
        "stdout-closed",
        "stdout-backpressure",
        "stdout-resume",
        "stdout-resume-utf8",
        "sigterm-init",
        "sigterm-idle",
        "sigterm-active",
        "sigint-init",
        "sigint-idle",
        "sigint-active",
        "oversize",
        "restart",
    ],
)
def test_gateway_lifecycle_no_survivors(tmp_path, case):
    verify_case(tmp_path / case, case)


def test_four_gateways_shutdown_independently(tmp_path):
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        tasks = [executor.submit(verify_case, tmp_path / str(i), "sigterm-idle") for i in range(4)]
        for task in tasks:
            task.result(timeout=20)
