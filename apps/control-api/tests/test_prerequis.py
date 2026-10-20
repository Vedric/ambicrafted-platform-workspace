"""Functional host prerequisites fail closed without leaking environment or parser errors."""

import subprocess
from unittest.mock import AsyncMock

import pytest

from plateforme import documents, prerequis

pytestmark = pytest.mark.asyncio


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setattr(prerequis.sys, "platform", "linux")
    monkeypatch.setattr(prerequis.sys, "prefix", "/private/venv")
    monkeypatch.setattr(prerequis.sys, "base_prefix", "/python")
    monkeypatch.setattr(prerequis.shutil, "which", lambda name: "/private/bin/" + name)
    monkeypatch.setattr(prerequis.ctypes.util, "find_library", lambda _: "libseccomp.so.2")
    monkeypatch.setattr(
        prerequis.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, b"v1.3.1\n"),
    )
    extract = AsyncMock(return_value={"kind": "text", "text": "x", "truncated": False})
    monkeypatch.setattr(documents, "extraire", extract)
    return extract


async def test_real_probe_is_required_even_when_tools_exist(host):
    result = await prerequis.verifier(export_requis=True)
    host.assert_awaited_once_with("prerequisite.txt", "eA==")
    assert result["ok"] and result["controles"]["age_export"]
    assert result["donnees_operateur_lues"] is False


@pytest.mark.parametrize("failure", ["bwrap", "libseccomp", "venv", "linux"])
async def test_missing_isolation_requirement_prevents_parser(host, monkeypatch, failure):
    if failure == "bwrap":
        monkeypatch.setattr(prerequis.shutil, "which", lambda _: None)
    elif failure == "libseccomp":
        monkeypatch.setattr(prerequis.ctypes.util, "find_library", lambda _: None)
    elif failure == "venv":
        monkeypatch.setattr(prerequis.sys, "prefix", prerequis.sys.base_prefix)
    else:
        monkeypatch.setattr(prerequis.sys, "platform", "win32")
    assert not (await prerequis.verifier())["ok"]
    host.assert_not_awaited()


@pytest.mark.parametrize("failure", ["exception", "wrong-result"])
async def test_nonfunctional_sandbox_fails_without_private_details(host, failure):
    if failure == "exception":
        host.side_effect = RuntimeError("synthetic-sensitive-kernel-error")
    else:
        host.return_value = {"kind": "text", "text": "wrong", "truncated": False}
    result = await prerequis.verifier()
    assert result["ok"] is False
    assert "synthetic-sensitive-kernel-error" not in repr(result)


async def test_age_is_optional_until_export_is_configured(host, monkeypatch):
    monkeypatch.setattr(
        prerequis.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, b"v1.2.0\n"),
    )
    assert (await prerequis.verifier())["ok"]
    result = await prerequis.verifier(export_requis=True)
    assert not result["ok"]
    assert not result["controles"]["age_export"]
