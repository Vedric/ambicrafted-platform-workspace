"""Atomic textfile bridge: local credentials never enter Prometheus or containers."""

import argparse
import asyncio
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import httpx
from prometheus_client import CollectorRegistry, Gauge, generate_latest
from prometheus_client.core import CounterMetricFamily
from prometheus_client.parser import text_string_to_metric_families

from .config import Parametres


class CPU:
    def collect(self):
        values = Path("/proc/stat").read_text().splitlines()[0].split()[1:9]
        metric = CounterMetricFamily(
            "ambicrafted_host_cpu_seconds_total",
            "Cumulative aggregate Linux CPU time.",
            labels=["mode"],
        )
        for mode, value in zip(
            ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"), values
        ):
            metric.add_metric([mode], int(value) / os.sysconf("SC_CLK_TCK"))
        yield metric


def gauge(registry, name, description, value, **labels):
    if math.isfinite(value):
        metric = Gauge("ambicrafted_" + name, description, list(labels), registry=registry)
        (metric.labels(**labels) if labels else metric).set(value)


def machine(registry, root: Path):
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
            memory[key] = int(value.strip().split()[0]) * 1024
    for key, byte_count in memory.items():
        gauge(
            registry,
            "host_memory_" + key.lower() + "_bytes",
            "Linux/WSL VM memory, not total physical Windows memory.",
            byte_count,
        )
    registry.register(CPU())
    gauge(registry, "host_load1", "Linux one-minute load average.", os.getloadavg()[0])
    gauge(registry, "host_cpu_count", "Logical CPUs visible to Linux/WSL.", os.cpu_count() or 1)
    disk = os.statvfs(root)
    gauge(
        registry,
        "data_disk_size_bytes",
        "Filesystem containing the platform checkout.",
        disk.f_blocks * disk.f_frsize,
    )
    gauge(
        registry,
        "data_disk_available_bytes",
        "Bytes available to the operator on data filesystem.",
        disk.f_bavail * disk.f_frsize,
    )
    gauge(
        registry,
        "data_disk_inodes_available_ratio",
        "Available inode fraction on data filesystem.",
        disk.f_favail / disk.f_files if disk.f_files else 1,
    )


def gpu(registry):
    binary = shutil.which("nvidia-smi")
    if not binary:
        gauge(registry, "gpu_probe_success", "NVIDIA numeric probe available and parsed.", 0)
        return
    try:
        result = subprocess.run(
            [
                binary,
                "--query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        rows = result.stdout[:16_384].strip().splitlines()
        if not rows or len(rows) > 16:
            raise ValueError("GPU inventory outside bounds")
        metrics = {
            key: Gauge("ambicrafted_gpu_" + key, help_text, ["gpu"], registry=registry)
            for key, help_text in (
                ("utilization_ratio", "Whole GPU usage; shared workloads can contribute."),
                ("memory_used_bytes", "Whole GPU allocated memory."),
                ("memory_total_bytes", "GPU memory capacity."),
                ("temperature_celsius", "GPU temperature."),
                ("power_watts", "Measured GPU power, not total workstation energy cost."),
            )
        }
        for line in rows:
            cells = [c.strip() for c in line.split(",")]
            if len(cells) != 6 or not re.fullmatch(r"[0-9]{1,2}", cells[0]):
                raise ValueError("Invalid GPU inventory")
            for (key, metric), value, factor in zip(
                metrics.items(), cells[1:], (0.01, 2**20, 2**20, 1, 1)
            ):
                try:
                    number = float(value) * factor
                except ValueError:
                    continue  # Unsupported sensors remain absent, never fabricated as zero.
                if math.isfinite(number) and number >= 0:
                    metric.labels(cells[0]).set(number)
        gauge(registry, "gpu_probe_success", "NVIDIA numeric probe available and parsed.", 1)
    except OSError, ValueError, subprocess.SubprocessError:
        gauge(registry, "gpu_probe_success", "NVIDIA numeric probe available and parsed.", 0)


def backups(registry, folder: Path):
    latest = 0.0
    incomplete = 0
    if folder.exists() and not folder.is_symlink():
        info = folder.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Private backup directory required")
        for directory in sorted(folder.iterdir(), reverse=True)[:64]:
            if directory.is_symlink() or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", directory.name):
                continue
            manifest = directory / "manifest.json"
            try:
                fd = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd) as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > 2_000_000:
                        continue
                    data = json.load(stream)
                if data.get("complet") is True:
                    date = datetime.fromisoformat(data["date"])
                    if date.tzinfo is not None:
                        latest = max(latest, date.timestamp())
                else:
                    incomplete += 1
            except OSError, ValueError, KeyError, TypeError:
                incomplete += 1
    gauge(
        registry,
        "backup_available",
        "At least one retained completed backup manifest exists.",
        int(latest > 0),
    )
    gauge(
        registry,
        "backup_incomplete",
        "Incomplete retained backup manifests (up to 64 inspected).",
        incomplete,
    )
    if latest:
        gauge(
            registry,
            "backup_last_completed_timestamp_seconds",
            "Latest completed local backup manifest; not proof of restore or off-host protection.",
            latest,
        )


def publish(destination: Path, data: bytes):
    if destination.parent.is_symlink() or destination.is_symlink():
        raise ValueError("Symbolic output paths refused")
    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    if destination.parent.stat().st_uid != os.getuid():
        raise ValueError("Collector output directory must belong to the operator")
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".metrics-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            # Aggregated telemetry only. The read-only textfile container has no secrets.
            os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def dossier_metriques(folder: Path) -> None:
    if folder.is_symlink() or folder.resolve() != folder:
        raise ValueError("Symbolic metrics directories refused")
    folder.mkdir(mode=0o755, parents=True, exist_ok=True)
    if folder.stat().st_uid != os.getuid():
        raise ValueError("Metrics directory must belong to the operator")
    # This reserved directory contains aggregate metrics only. Explicit permissions
    # keep the unprivileged exporter working even with the service's private umask.
    folder.chmod(0o755)


async def collect(p: Parametres, destination: Path):
    registry, api = CollectorRegistry(), b""
    start = time.monotonic()
    try:
        async with (
            asyncio.timeout(20),
            httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                timeout=18,
            ) as client,
            client.stream(
                "GET", p.url + "/api/metriques", headers={"Authorization": "Bearer " + p.cle}
            ) as response,
        ):
            response.raise_for_status()
            if not response.headers.get("content-type", "").startswith("text/plain"):
                raise ValueError("Unexpected metrics content type")
            parts = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                parts.extend(chunk)
                if len(parts) > 1_000_000:
                    raise ValueError("Metrics response outside bounds")
            families = list(text_string_to_metric_families(parts.decode("utf-8")))
            if (
                not families
                or len(families) > 256
                or any(
                    not family.name.startswith(("ambicrafted_", "process_", "python_"))
                    for family in families
                )
            ):
                raise ValueError("Unexpected metrics namespace")
            api = bytes(parts)
        gauge(
            registry, "control_api_scrape_success", "Authenticated metrics collection succeeded.", 1
        )
    except httpx.HTTPError, TimeoutError, ValueError:
        gauge(
            registry, "control_api_scrape_success", "Authenticated metrics collection succeeded.", 0
        )
    for name, operation in (
        ("host", lambda: machine(registry, p.racine)),
        ("gpu", lambda: gpu(registry)),
        ("backup", lambda: backups(registry, Path.home() / ".local/state/platform-backups")),
    ):
        try:
            await asyncio.to_thread(operation)
            success = 1
        except OSError, ValueError:
            success = 0
        gauge(
            registry, "collector_section_success_" + name, "Collector section completed.", success
        )
    gauge(
        registry,
        "collector_duration_seconds",
        "Time to prepare this textfile snapshot.",
        time.monotonic() - start,
    )
    gauge(
        registry,
        "snapshot_timestamp_seconds",
        "Time this content-free snapshot was collected.",
        time.time(),
    )
    dossier_metriques(destination.parent)
    publish(destination, api + generate_latest(registry))


def main():
    parser = argparse.ArgumentParser(description="Publish local aggregate Prometheus metrics.")
    parser.parse_args()
    p = Parametres.charger(lecture_seule=True)
    try:
        asyncio.run(collect(p, p.racine / "gateway/observability/.textfile/platform.prom"))
    except OSError, ValueError:
        raise SystemExit(
            "Metric publication failed; check private configuration and output permissions."
        ) from None


def installer(p: Parametres) -> dict:
    """Install only the explicitly named, managed user collector units."""
    from .cli import ErreurCLI, argument_systemd, repertoire_systemd

    python = p.racine / "apps/control-api/.venv/bin/python"
    if not python.is_file() or not shutil.which("systemctl"):
        raise ErreurCLI("Installer le runtime API et activer systemd utilisateur.")
    output = p.racine / "gateway/observability/.textfile"
    try:
        dossier_metriques(output)
    except OSError, ValueError:
        raise ErreurCLI("Le dossier de collecte doit être régulier et vous appartenir.") from None
    directory = Path.home() / ".config/systemd/user"
    directory.mkdir(parents=True, exist_ok=True)
    header = "# Managed by Ambicrafted metrics\n"
    units = {
        "ambicrafted-metrics.service": header
        + f"""[Unit]
Description=Ambicrafted private aggregate metrics snapshot
After=ambicrafted-console.service

[Service]
Type=oneshot
WorkingDirectory={repertoire_systemd(str(p.racine))}
ExecStart={argument_systemd(str(python), commande=True)} -m plateforme.collecteur
Environment={argument_systemd("PLATFORM_STATE_DIR=" + str(p.etat))}
Environment=PLATFORM_PORT={p.port}
Environment=PYTHONDONTWRITEBYTECODE=1
TimeoutStartSec=28
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={repertoire_systemd(str(output))}
UMask=0077
""",
        "ambicrafted-metrics.timer": header
        + """[Unit]
Description=Refresh Ambicrafted aggregate metrics

[Timer]
OnBootSec=30s
OnUnitInactiveSec=30s
AccuracySec=1s

[Install]
WantedBy=timers.target
""",
    }
    for name in units:
        target = directory / name
        if target.is_symlink() or (target.exists() and not target.read_text().startswith(header)):
            raise ErreurCLI("Unité existante non gérée : installation interrompue.")
    for name, body in units.items():
        publish(directory / name, body.encode())
    for command in (
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "reset-failed", "ambicrafted-metrics.service"],
        ["systemctl", "--user", "enable", "--now", "ambicrafted-metrics.timer"],
        ["systemctl", "--user", "start", "ambicrafted-metrics.service"],
    ):
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=35)
        except OSError, subprocess.SubprocessError:
            raise ErreurCLI(
                "Vérifier ambicrafted-metrics.timer et son service utilisateur."
            ) from None
    return {
        "installed": True,
        "scope": "local-aggregate",
        "dashboard": "http://localhost:3000/d/plateforme-sre",
    }


if __name__ == "__main__":
    main()
