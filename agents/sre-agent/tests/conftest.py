"""The guardrail tests run on an unplugged machine.

Tracing is switched off here rather than in each test: an exporter looking
for an absent collector turns a test failure into a timeout wait, and
muddies the reading of the result.
"""

import os
import socket

import pytest

os.environ.setdefault("SRE_TRACAGE", "0")


@pytest.fixture(autouse=True)
def interdire_reseau(monkeypatch):
    original = socket.socket.connect

    def connecter(sock, adresse):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            pytest.fail("Connexion réseau interdite dans les tests unitaires.")
        return original(sock, adresse)

    monkeypatch.setattr(socket.socket, "connect", connecter)
