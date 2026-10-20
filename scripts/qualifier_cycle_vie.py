"""Bounded real-HTTP control-plane qualification on self-created disposable state.

Run with the locked control-api Python environment. Inference is a synthetic
subprocess: this measures queue/process/session/state reliability, not model
quality or GPU capacity. No URL/token option exists, preventing live mutations.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import signal
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path


class Failure(RuntimeError):
    pass


def fixture(mode: str, decision: str) -> int:
    if mode == "slow":
        time.sleep(30)
    if mode == "malformed":
        print("synthetic invalid protocol")
        return 0
    if mode == "budget":
        print(
            json.dumps(
                {"statut": "budget_epuise", "message": "Synthetic token ceiling"}
            )
        )
        return 2
    time.sleep(0.03)
    status = (
        "en_attente_humain"
        if decision == "none"
        else "complet"
        if decision == "yes"
        else "rejete_par_humain"
    )
    proposal = {
        "cause_probable": "Synthetic proposal; no real diagnostic claim",
        "confiance": "faible",
        "actions_proposees": [],
        "runbook_source": None,
        "elements_manquants": ["Synthetic environment"],
    }
    print(
        json.dumps(
            {
                "statut": status,
                "diagnostic": proposal if decision == "yes" else None,
                "message": json.dumps(proposal)
                if decision == "none"
                else "Synthetic human decision",
            }
        )
    )
    return {"en_attente_humain": 10, "complet": 0, "rejete_par_humain": 4}[status]


def serve() -> None:
    # scripts/plateforme.py is a CLI, not the installed plateforme package.
    script_directory = Path(__file__).resolve().parent
    sys.path[:] = [
        entry for entry in sys.path if Path(entry).resolve() != script_directory
    ]
    import uvicorn
    from plateforme.app import creer_app
    from plateforme.config import Parametres
    from plateforme.moteur import Moteur

    root = Path(os.environ["QUALIFICATION_ROOT"])
    if not (root / ".synthetic-qualification").is_file():
        raise Failure("Disposable root marker missing")
    key = os.environ.pop("QUALIFICATION_KEY")
    port = int(os.environ["QUALIFICATION_PORT"])

    class FixtureEngine(Moteur):
        def commande(self, analysis, decision):
            mode = analysis["titre"].split(":", 1)[0]
            if mode not in {"normal", "slow", "malformed", "budget"}:
                raise ValueError("Unknown synthetic fixture")
            env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG"}}
            return [
                sys.executable,
                str(Path(__file__).resolve()),
                "--fixture",
                mode,
                "none" if decision is None else "yes" if decision else "no",
            ], env

    params = Parametres(
        racine=root,
        etat=root / "state",
        cle=key,
        port=port,
        taille_file=4,
        veille_active=False,
    )
    uvicorn.run(
        creer_app(params, moteur_classe=FixtureEngine),
        host="127.0.0.1",
        port=port,
        access_log=False,
        log_level="error",
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


class Qualification:
    def __init__(self, root: Path, port: int):
        self.root, self.port = root, port
        self.key = secrets.token_urlsafe(40)
        self.process: subprocess.Popen | None = None
        self.latencies: deque[float] = deque(maxlen=10000)
        self.requests = 0
        self.startups = 0
        self.samples: deque[dict] = deque(maxlen=3000)
        self.baseline: list[dict] = []

    def request(
        self, method: str, route: str, data=None, expected=(200,), authenticated=True
    ):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + self.key
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}" + route,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers,
            method=method,
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        start = time.monotonic()
        try:
            response = opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.status
            payload = response.read(2_000_000)
        self.requests += 1
        if method == "GET" and route.startswith("/api/analyses"):
            self.latencies.append((time.monotonic() - start) * 1000)
        require(status in expected, f"Unexpected HTTP {status} for {method} {route}")
        return status, json.loads(payload)

    def start(self):
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG"}}
        env.update(
            QUALIFICATION_ROOT=str(self.root),
            QUALIFICATION_KEY=self.key,
            QUALIFICATION_PORT=str(self.port),
            LANGSMITH_TRACING="false",
            LANGCHAIN_TRACING_V2="false",
        )
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for _ in range(100):
            if self.process.poll() is not None:
                raise Failure("Disposable API failed to start")
            try:
                # Authenticate immediately: an unrelated server on a reused port
                # cannot be mistaken for the subprocess just created.
                self.request("GET", "/api/analyses")
                self.startups += 1
                return
            except (OSError, ValueError, Failure):
                time.sleep(0.1)
        raise Failure("Disposable API readiness timeout")

    def stop(self):
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
                raise Failure("Graceful API shutdown timed out")

    def create(self, mode="normal"):
        _, analysis = self.request(
            "POST",
            "/api/analyses",
            {
                "titre": mode + ": synthetic qualification",
                "alerte": "Synthetic control-plane lifecycle fixture; no infrastructure action.",
            },
            expected=(202,),
        )
        return analysis["id"]

    def wait(self, identifier: str, statuses: set[str]):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            _, analysis = self.request("GET", "/api/analyses/" + identifier)
            if analysis["statut"] in statuses:
                return analysis
            time.sleep(0.05)
        raise Failure("Expected analysis lifecycle state was not reached")

    def delete(self, identifier: str):
        self.request("DELETE", "/api/analyses/" + identifier)

    def steady_cycle(self, number: int):
        kind = number % 5
        identifier = self.create(
            "malformed"
            if kind == 3
            else "budget"
            if kind == 4
            else "slow"
            if kind == 2
            else "normal"
        )
        if kind in {0, 1}:
            proposal = self.wait(identifier, {"en_attente_humain"})
            require(
                proposal["rapport"]["diagnostic"] is None,
                "Premature diagnosis delivery",
            )
            self.request(
                "POST",
                f"/api/analyses/{identifier}/decision",
                {"approuver": kind == 0},
                expected=(202,),
            )
            self.wait(identifier, {"complet" if kind == 0 else "rejete_par_humain"})
            self.request(
                "POST",
                f"/api/analyses/{identifier}/decision",
                {"approuver": True},
                expected=(409,),
            )
            _, export = self.request("GET", f"/api/analyses/{identifier}/export")
            require(
                export["statut"] == ("complet" if kind == 0 else "rejete_par_humain"),
                "Export and persisted state diverged",
            )
            if kind == 1:
                require(
                    export["rapport"]["diagnostic"] is None, "Rejected diagnosis leaked"
                )
        elif kind == 2:
            self.wait(identifier, {"en_cours"})
            started = time.monotonic()
            self.request("POST", f"/api/analyses/{identifier}/annuler", {})
            self.wait(identifier, {"annule"})
            require(time.monotonic() - started < 2, "Cancellation exceeded 2 seconds")
        else:
            self.wait(identifier, {"erreur" if kind == 3 else "budget_epuise"})
        self.delete(identifier)

    def queue_and_restart(self):
        awaiting = self.create()
        self.wait(awaiting, {"en_attente_humain"})
        running = self.create("slow")
        self.wait(running, {"en_cours"})

        def submit(_):
            return self.request(
                "POST",
                "/api/analyses",
                {
                    "titre": "normal: burst",
                    "alerte": "Synthetic bounded queue fixture.",
                },
                expected=(202, 409),
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(submit, range(12)))
        accepted = [body["id"] for status, body in responses if status == 202]
        require(
            len(accepted) == 4 and sum(status == 409 for status, _ in responses) == 8,
            "Queue capacity contract changed",
        )
        self.stop()
        self.start()
        for identifier in [running, *accepted]:
            self.wait(identifier, {"interrompu"})
            self.delete(identifier)
        self.wait(awaiting, {"en_attente_humain"})
        self.request(
            "POST",
            f"/api/analyses/{awaiting}/decision",
            {"approuver": False},
            expected=(202,),
        )
        self.wait(awaiting, {"rejete_par_humain"})
        self.delete(awaiting)

    def sample(self):
        assert self.process
        proc = Path(f"/proc/{self.process.pid}")
        sample = {"elapsed_s": round(time.monotonic() - self.started, 3)}
        if proc.exists():
            fields = {
                line.split(":", 1)[0]: line.split(":", 1)[1].strip()
                for line in (proc / "status").read_text().splitlines()
                if ":" in line
            }
            sample.update(
                rss_kib=int(fields["VmRSS"].split()[0]),
                descriptors=len(list((proc / "fd").iterdir())),
                threads=int(fields["Threads"]),
            )
        self.samples.append(sample)
        if len(self.baseline) < 5:
            self.baseline.append(sample)
        _, analyses = self.request("GET", "/api/analyses")
        require(analyses["total"] == 0, "An owned analysis was left after cleanup")

    def run(self, seconds: int, interval: float, output: Path):
        self.started = time.monotonic()
        result = {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "scope": "real HTTP/API/SQLite/queue/subprocess; deterministic inference; graceful restart",
            "requested_seconds": seconds,
            "model_calls": 0,
            "cycles": 0,
            "passed": False,
        }
        try:
            self.start()
            self.request("GET", "/api/analyses", expected=(401,), authenticated=False)
            self.queue_and_restart()
            self.sample()
            number = 0
            while time.monotonic() - self.started < seconds or number < 5:
                self.steady_cycle(number)
                number += 1
                result["cycles"] = number
                self.sample()
                if number % 5 == 0:
                    print(
                        json.dumps(
                            {
                                "cycles": number,
                                "elapsed_s": round(time.monotonic() - self.started),
                                "scope": "synthetic control plane",
                            }
                        ),
                        flush=True,
                    )
                remaining = seconds - (time.monotonic() - self.started)
                if remaining > 0:
                    time.sleep(min(interval, remaining))
            samples = list(self.samples)
            if len(samples) >= 10 and "rss_kib" in samples[0]:
                # A bounded heuristic on the process, not a mathematical leak proof.
                first = statistics.median(row["rss_kib"] for row in self.baseline)
                last = statistics.median(row["rss_kib"] for row in samples[-5:])
                require(
                    last - first < 64 * 1024, "RSS grew more than the 64 MiB envelope"
                )
                require(
                    max(row["descriptors"] for row in samples)
                    <= self.baseline[0]["descriptors"] + 24,
                    "File descriptor growth exceeded envelope",
                )
            self.queue_and_restart()
            self.sample()
            result["passed"] = True
        except (Failure, OSError, ValueError) as error:
            result["failure"] = (
                str(error) if isinstance(error, Failure) else type(error).__name__
            )
        finally:
            try:
                self.stop()
            except Failure as error:
                result.update(passed=False, failure=str(error))
            result.update(
                duration_s=round(time.monotonic() - self.started, 3),
                http_requests=self.requests,
                startups=self.startups,
                samples=list(self.samples),
                resource_baseline=self.baseline,
            )
            if self.latencies:
                ordered = sorted(self.latencies)
                result["read_latency"] = {
                    "sample_count": len(ordered),
                    "window": "last at most 10000 analysis GET requests",
                    "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 2),
                    "max_ms": round(max(ordered), 2),
                }
            # Inspect only the disposable database after its server has stopped.
            state = self.root / "state/console.sqlite"
            if state.exists():
                with sqlite3.connect(state) as connection:
                    result["sqlite_integrity"] = connection.execute(
                        "PRAGMA integrity_check"
                    ).fetchone()[0]
                    if result["sqlite_integrity"] != "ok":
                        result["passed"] = False
            output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            fd = os.open(
                output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "w") as file:
                json.dump(result, file, indent=2)
                file.write("\n")
        return 0 if result["passed"] else 1


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--fixture":
        return fixture(sys.argv[2], sys.argv[3])
    if sys.argv[1:] == ["--serve"]:
        serve()
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (
        not 30 <= args.seconds <= 259200
        or not math.isfinite(args.interval)
        or not 0 <= args.interval <= 60
    ):
        parser.error("Use 30..259200 seconds and interval 0..60 seconds")
    if args.output.exists():
        parser.error("The output file must be new")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="ambicrafted-lifecycle-") as temporary:
        root = Path(temporary)
        (root / ".synthetic-qualification").touch(mode=0o600)
        (root / "runbooks").mkdir(mode=0o700)
        (root / "state").mkdir(mode=0o700)
        return Qualification(root, port).run(args.seconds, args.interval, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
