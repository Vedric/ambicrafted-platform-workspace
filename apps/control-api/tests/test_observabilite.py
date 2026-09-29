"""Security, cardinality, streaming and gauge semantics of private telemetry."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from prometheus_client import CollectorRegistry
from prometheus_client.parser import text_string_to_metric_families

from plateforme.collecteur import backups, publish
from plateforme.observabilite import Mesures, MesuresHTTP, group


def samples(text):
    return {
        s.name + str(s.labels): s.value
        for family in text_string_to_metric_families(text)
        for s in family.samples
    }


def test_metrics_require_auth_and_exclude_private_content(client, bearer, application):
    assert client.get("/api/metriques").status_code == 401
    application.state.depot.creer("a" * 32, "private-customer-title", "graphe", {}, "cli")
    application.state.depot.changer(
        "a" * 32,
        "complet",
        rapport={
            "secret-context": "confidential-body",
            "budget": {"tokens_total": 37, "cout_usd": 0},
        },
    )
    result = client.get("/api/metriques", headers=bearer)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert "private-customer" not in result.text and "confidential-body" not in result.text
    assert "a" * 32 not in result.text
    values = samples(result.text)
    assert values["ambicrafted_retained_tokens{}"] == 37
    assert values["ambicrafted_retained_cout_usd_measured_runs{}"] == 1
    assert values["ambicrafted_retained_tokens_entree_measured_runs{}"] == 0
    application.state.depot.supprimer("a" * 32, "cli")
    after = samples(client.get("/api/metriques", headers=bearer).text)
    assert after["ambicrafted_retained_tokens{}"] == 0
    assert after["ambicrafted_retained_tokens_measured_runs{}"] == 0


def test_browser_session_cannot_collect_metrics(client, session):
    assert client.get("/api/metriques").status_code == 403


def test_metrics_measure_auth_errors_without_path_cardinality(client, bearer):
    for i in range(8):
        client.get(f"/api/analyses/customer-secret-{i}")
    data = client.get("/api/metriques", headers=bearer).text
    assert "customer-secret" not in data
    assert samples(data)["ambicrafted_auth_rejections_total{}"] >= 8
    assert group("/api/conversations/private-uuid/messages") == "assistant"
    assert group("/api/private-customer") == "other"


def test_rejected_and_legacy_runs_are_counted_without_exporting_unknown_labels(
    client, bearer, application
):
    depot = application.state.depot
    depot.creer("r" * 32, "synthetic", "graphe", {}, "test")
    depot.changer("r" * 32, "rejete_par_humain")
    depot.creer("o" * 32, "synthetic", "private-legacy-mode", {}, "test")
    depot.changer("o" * 32, "private-legacy-state")
    text = client.get("/api/metriques", headers=bearer).text
    assert "private-legacy" not in text
    runs = [
        sample
        for family in text_string_to_metric_families(text)
        for sample in family.samples
        if sample.name == "ambicrafted_retained_runs"
    ]
    assert sum(sample.value for sample in runs) == 2
    assert (
        next(
            sample.value
            for sample in runs
            if sample.labels == {"kind": "graphe", "state": "rejete_par_humain"}
        )
        == 1
    )
    assert (
        next(
            sample.value for sample in runs if sample.labels == {"kind": "other", "state": "other"}
        )
        == 1
    )


@pytest.mark.asyncio
async def test_stream_finishes_only_after_last_body_and_cancellation_releases_gauge():
    metrics = Mesures()
    events = []

    async def send(event):
        events.append(event)

    async def stream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"private", "more_body": True})
        assert metrics.active.labels("assistant")._value.get() == 1
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await MesuresHTTP(stream, metrics)(
            {"type": "http", "path": "/api/assistant/dialogue"},
            None,
            send,
        )
    assert metrics.active.labels("assistant")._value.get() == 0
    assert metrics.requests.labels("assistant", "cancelled")._value.get() == 1
    assert metrics.duration.labels("assistant")._sum.get() >= 0


def test_atomic_publication_refuses_links_and_removes_temporary_files(tmp_path):
    target = tmp_path / "metrics/platform.prom"
    publish(target, b"sample 1\n")
    publish(target, b"sample 2\n")
    assert target.read_bytes() == b"sample 2\n"

    assert target.stat().st_mode & 0o777 == 0o644
    assert list(target.parent.iterdir()) == [target]
    link = tmp_path / "unsafe.prom"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        publish(link, b"changed")
    assert target.read_bytes() == b"sample 2\n"


def test_aggregate_directory_ignores_private_umask_without_changing_parent(tmp_path):
    import os

    from plateforme.collecteur import dossier_metriques

    folder = tmp_path / "metrics"
    parent_mode = tmp_path.stat().st_mode
    previous = os.umask(0o077)
    try:
        dossier_metriques(folder)
        publish(folder / "platform.prom", b"synthetic 1\n")
    finally:
        os.umask(previous)
    assert folder.stat().st_mode & 0o777 == 0o755
    assert (folder / "platform.prom").stat().st_mode & 0o777 == 0o644
    assert tmp_path.stat().st_mode == parent_mode


def test_backup_collection_does_not_treat_missing_manifest_as_success(tmp_path):
    from prometheus_client import generate_latest

    registry = CollectorRegistry()
    backups(registry, tmp_path / "absent")
    values = samples(generate_latest(registry).decode())
    assert values["ambicrafted_backup_available{}"] == 0
    assert "ambicrafted_backup_last_completed_timestamp_seconds{}" not in values


def test_gpu_probe_uses_wsl_utility_without_shell_path(tmp_path, monkeypatch):
    from prometheus_client import generate_latest

    from plateforme import collecteur

    executable = tmp_path / "nvidia-smi"
    executable.write_text("synthetic utility")
    executable.chmod(0o700)
    monkeypatch.setattr(collecteur, "WSL_NVIDIA_SMI", executable)
    monkeypatch.setattr(collecteur.shutil, "which", lambda _: None)

    def run(command, **kwargs):
        assert command[0] == str(executable)
        assert command[-1] == "--format=csv,noheader,nounits"
        assert kwargs["timeout"] == 3
        return collecteur.subprocess.CompletedProcess(command, 0, "0, 25, 100, 1000, 42, N/A\n")

    monkeypatch.setattr(collecteur.subprocess, "run", run)
    registry = CollectorRegistry()
    collecteur.gpu(registry)
    values = samples(generate_latest(registry).decode())
    assert values["ambicrafted_gpu_probe_success{}"] == 1
    assert values["ambicrafted_gpu_utilization_ratio{'gpu': '0'}"] == 0.25
    assert values["ambicrafted_gpu_memory_used_bytes{'gpu': '0'}"] == 100 * 2**20
    assert not any(name.startswith("ambicrafted_gpu_power_watts{") for name in values)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["status", "html", "namespace", "oversize", "timeout"])
async def test_collection_failure_replaces_old_api_snapshot(
    parametres, tmp_path, monkeypatch, failure
):
    from plateforme import collecteur

    client_class = httpx.AsyncClient
    good = True

    def handle(request):
        assert request.headers["authorization"] == "Bearer " + parametres.cle
        assert request.url.path == "/api/metriques"
        if good:
            return httpx.Response(200, text="ambicrafted_retained_runs 3\n")
        if failure == "timeout":
            raise httpx.ReadTimeout("private detail must stay hidden")
        if failure == "status":
            return httpx.Response(503)
        if failure == "html":
            return httpx.Response(
                200, text="<html>Private</html>", headers={"content-type": "text/html"}
            )
        text = "private_namespace 1\n" if failure == "namespace" else "x" * 1_000_001
        return httpx.Response(200, text=text)

    monkeypatch.setattr(
        collecteur.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(**kwargs, transport=httpx.MockTransport(handle)),
    )
    for operation in ("machine", "gpu", "backups"):
        monkeypatch.setattr(collecteur, operation, lambda *args: None)
    target = tmp_path / "metrics/platform.prom"
    await collecteur.collect(parametres, target)
    assert samples(target.read_text())["ambicrafted_control_api_scrape_success{}"] == 1
    assert "ambicrafted_retained_runs 3" in target.read_text()
    good = False
    await collecteur.collect(parametres, target)
    text = target.read_text()
    assert samples(text)["ambicrafted_control_api_scrape_success{}"] == 0
    assert "retained_runs" not in text and parametres.cle not in text and "Private" not in text
    assert samples(text)["ambicrafted_snapshot_timestamp_seconds{}"] > 0


def test_backup_manifest_completed_incomplete_and_symbolic(tmp_path):
    from prometheus_client import generate_latest

    for name, content in [
        ("20260929T010000Z", {"complet": True, "date": "2026-09-29T01:00:00Z"}),
        ("20260929T020000Z", {"complet": False}),
    ]:
        folder = tmp_path / name
        folder.mkdir(mode=0o700)
        (folder / "manifest.json").write_text(json.dumps(content))
    (tmp_path / "20260929T030000Z").symlink_to(
        tmp_path / "20260929T010000Z", target_is_directory=True
    )
    registry = CollectorRegistry()
    backups(registry, tmp_path)
    values = samples(generate_latest(registry).decode())
    assert values["ambicrafted_backup_available{}"] == 1
    assert values["ambicrafted_backup_incomplete{}"] == 1


def test_collector_install_preserves_unmanaged_units_and_quotes_paths(
    parametres, tmp_path, monkeypatch
):
    from plateforme import collecteur
    from plateforme.cli import ErreurCLI

    home = tmp_path / "operator"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(collecteur.shutil, "which", lambda _: "/usr/bin/systemctl")
    binary = parametres.racine / "apps/control-api/.venv/bin/python"
    binary.parent.mkdir(parents=True)
    binary.touch()
    (parametres.racine / "gateway/observability").mkdir(parents=True)
    unit = home / ".config/systemd/user/ambicrafted-metrics.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("Unmanaged unit\n")
    commands = []

    def systemctl(command, **kwargs):
        commands.append(command)
        code = 1 if command[2] == "reset-failed" else 0
        if code and kwargs["check"]:
            raise collecteur.subprocess.CalledProcessError(code, command)
        return collecteur.subprocess.CompletedProcess(command, code)

    monkeypatch.setattr(collecteur.subprocess, "run", systemctl)
    with pytest.raises(ErreurCLI):
        collecteur.installer(parametres)
    assert unit.read_text() == "Unmanaged unit\n" and commands == []
    unit.unlink()
    assert collecteur.installer(parametres)["installed"]
    assert parametres.cle not in unit.read_text()
    assert "ProtectSystem=strict" in unit.read_text()
    assert commands[1][2:4] == ["reset-failed", "ambicrafted-metrics.service"]
    assert all("--user" in command for command in commands)
