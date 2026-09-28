import asyncio
import io
import time
import wave
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from defusedxml.common import DefusedXmlException

from plateforme.veille import (
    INTERVALLE,
    SOURCES,
    Veille,
    articles,
    charger_source,
    verifier_identifiants,
)

NOW = datetime(2026, 9, 27, tzinfo=UTC)


def rss(link="https://kubernetes.io/blog/update", date="Fri, 25 Sep 2026 12:00:00 GMT"):
    return f"<rss><channel><item><title>New &amp; useful</title><link>{link}</link><pubDate>{date}</pubDate><description>&lt;p&gt;Public announcement&lt;/p&gt;</description></item></channel></rss>".encode()


def test_feed_requires_dated_recent_https_same_publisher_links():
    items = articles(rss(), "Kubernetes", "kubernetes.io", NOW)
    assert items[0]["title"] == "New & useful" and items[0]["excerpt"] == "Public announcement"
    for link in [
        "http://kubernetes.io/blog/update",
        "https://evil.invalid/",
        "https://user:pass@kubernetes.io/",
        "file:///etc/passwd",
    ]:
        assert articles(rss(link), "Kubernetes", "kubernetes.io", NOW) == []
    for date in ["", "invalid", "Mon, 28 Sep 2026 12:00:00 GMT", "Fri, 01 Aug 2025 12:00:00 GMT"]:
        assert articles(rss(date=date), "Kubernetes", "kubernetes.io", NOW) == []


def test_feed_xml_entities_are_never_resolved():
    with pytest.raises(DefusedXmlException):
        articles(
            b'<!DOCTYPE rss [<!ENTITY secret SYSTEM "file:///etc/passwd">]><rss>&secret;</rss>',
            "Kubernetes",
            "kubernetes.io",
            NOW,
        )


def test_summary_rejects_invented_cve_and_version_numbers():
    items = [{"title": "Kubernetes v1.37", "excerpt": "CVE-2026-12345 was published."}]
    verifier_identifiants("Kubernetes 1.37; CVE-2026-12345.", items)
    for invented in ["Kubernetes v1.38", "CVE-2026-99999"]:
        with pytest.raises(ValueError, match="unsupported identifier"):
            verifier_identifiants(invented, items)


@pytest.mark.parametrize(
    "payload",
    [
        '{"generated_at":NaN,"articles":[],"briefings":{}}',
        '{"generated_at":1,"articles":[],"briefings":{},"private":"must not escape"}',
        '{"generated_at":999999999999,"articles":[],"briefings":{}}',
    ],
)
def test_invalid_cache_is_not_published(parametres, payload):
    instance = watch(parametres)
    instance.ecrire("digest.json", payload.encode())
    reloaded = watch(parametres)
    assert reloaded.data == {} and reloaded.statut()["stale"]


@pytest.mark.asyncio
async def test_feed_refuses_redirect_and_large_body():
    for response in [
        httpx.Response(302, headers={"Location": "http://127.0.0.1/private"}),
        httpx.Response(200, content=b"x" * 1_500_001),
    ]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _, result=response: result), follow_redirects=False
        ) as client:
            with pytest.raises((httpx.HTTPStatusError, ValueError)):
                await charger_source(client, SOURCES[0], NOW)


def fake_audio():
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(bytes(32000))
    return output.getvalue()


def watch(parametres):
    async def speak(*args):
        return fake_audio()

    return Veille(
        parametres,
        SimpleNamespace(verrou=asyncio.Lock(), parler=speak),
        SimpleNamespace(inference=asyncio.Lock(), file=asyncio.Queue()),
    )


@pytest.mark.asyncio
async def test_refresh_is_atomic_bilingual_and_preserves_source_failures(parametres, monkeypatch):
    instance = watch(parametres)

    async def source(_, definition, now):
        if definition[0] == "CISA":
            raise ValueError("Unavailable source")
        return [
            {
                "title": "Verified synthetic title",
                "source": definition[0],
                "url": definition[1],
                "published": now.isoformat(),
                "excerpt": "Public synthetic excerpt",
            }
        ]

    async def summary(items, language):
        assert instance.moteur.inference.locked()
        return f"Public synthetic {language} briefing."

    monkeypatch.setattr("plateforme.veille.charger_source", source)
    monkeypatch.setattr(instance, "resumer", summary)
    await instance.actualiser()
    assert instance.statut()["unavailable_sources"] == ["CISA"]
    assert not instance.statut()["stale"]
    assert instance.audio("en") and instance.audio("fr")
    assert instance.audio("../digest") is None
    assert "excerpt" not in instance.statut()["articles"][0]
    reloaded = watch(parametres)
    assert reloaded.data == instance.data
    assert not instance.moteur.inference.locked()


@pytest.mark.asyncio
async def test_failed_refresh_keeps_previous_digest_and_busy_engine_does_not_fetch(
    parametres, monkeypatch
):
    instance = watch(parametres)
    instance.data = {"generated_at": time.time() - INTERVALLE - 1, "articles": [], "briefings": {}}
    previous = dict(instance.data)
    calls = []

    async def fail(*args):
        calls.append(True)
        raise ValueError("Offline")

    monkeypatch.setattr("plateforme.veille.charger_source", fail)
    async with instance.moteur.inference:
        await instance.actualiser()
        assert not calls
    await instance.actualiser()
    assert len(calls) == len(SOURCES)
    assert instance.data == previous and instance.statut()["stale"]


def test_public_endpoint_exposes_only_cached_public_data_without_triggering_fetch(client):
    response = client.get("/api/veille")
    assert response.status_code == 200
    assert response.json()["stale"] and not response.json()["enabled"]
    assert client.get("/api/veille/audio/fr").status_code == 404
    assert client.get("/api/veille/audio/de").status_code == 422


@pytest.mark.parametrize("language", ["en", "fr"])
def test_spoken_digest_caps_words_and_characters_at_a_complete_sentence(language):
    from plateforme.veille import borner_briefing

    sentence = "Version 1.37 is described in the announcement; review its deployment requirements. "
    bounded = borner_briefing(sentence * 30, language)
    assert len(bounded) <= 1500 and len(bounded.split()) <= 195
    assert bounded.startswith(sentence)
    assert "1.37" in bounded and bounded.endswith(".")
    assert borner_briefing(sentence, language) == sentence
    with pytest.raises(ValueError):
        borner_briefing("unbroken " * 500, language)
