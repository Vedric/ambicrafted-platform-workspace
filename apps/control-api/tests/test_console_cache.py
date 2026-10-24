"""Exercise real file responses and cache boundaries through the HTTP application."""

import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.mark.parametrize("url", ["/", "/index.html", "/assistant", "/analyses/nouvelle"])
def test_html_revalide_et_repond_304(client, url):
    first = client.get(url)
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-cache"
    assert first.headers["content-type"].startswith("text/html")
    again = client.get(url, headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and not again.content
    assert again.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("name", ["index-Ab12_C-d.js", "index-Ab12_C-d.css", "font-Ab12_C-d.woff2"])
def test_assets_versionnes_immuables_et_head(client, parametres, name):
    assets = parametres.web / "assets"
    assets.mkdir()
    (assets / name).write_bytes(b"synthetic public build asset")
    url = "/assets/" + name
    first = client.get(url)
    assert first.status_code == 200
    assert first.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert first.headers["x-content-type-options"] == "nosniff"
    again = client.get(url, headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and not again.content
    assert again.headers["cache-control"] == first.headers["cache-control"]
    head = client.head(url)
    assert head.status_code == 200 and not head.content
    assert head.headers["content-length"] == str(len(first.content))


@pytest.mark.parametrize(
    "path", ["asset.js", "assets/runtime.js", "audio/welcome.wav", "guides/demo.mp4"]
)
def test_fichiers_non_versionnes_revalidation_et_ranges(client, parametres, path):
    target = parametres.web / path
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(b"0123456789")
    first = client.get("/" + path)
    assert first.status_code == 200 and first.headers["cache-control"] == "no-cache"
    assert (
        client.get("/" + path, headers={"If-None-Match": first.headers["etag"]}).status_code == 304
    )
    partial = client.get("/" + path, headers={"Range": "bytes=2-5"})
    assert partial.status_code == 206 and partial.content == b"2345"
    assert partial.headers["content-range"] == "bytes 2-5/10"


@pytest.mark.parametrize(
    "url",
    [
        "/assets/gone-Ab12_C-d.js",
        "/assets/unknown",
        "/guides/missing.mp4",
        "/audio/missing.wav",
        "/missing.svg",
        "/api/missing",
    ],
)
def test_fichiers_absents_ne_deviennent_pas_du_html_cache(client, url):
    response = client.get(url)
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert not response.headers["content-type"].startswith("text/html")


def test_nouvelle_version_du_build_et_html_ne_reutilisent_pas_les_anciens_octets(
    client, parametres
):
    old = client.get("/")
    (parametres.web / "index.html").write_text("<!doctype html><title>New build version</title>")
    updated = client.get("/", headers={"If-None-Match": old.headers["etag"]})
    assert updated.status_code == 200 and "New build version" in updated.text
    assert updated.headers["etag"] != old.headers["etag"]
    assert updated.headers["cache-control"] == "no-cache"


def test_cache_public_ne_change_pas_auth_et_api_privee(client, bearer):
    assert client.get("/api/conversations").status_code == 401
    response = client.get("/api/conversations", headers=bearer)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert "etag" not in response.headers


def test_lien_hors_build_ne_divulgue_pas_de_fichier(client, parametres, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("synthetic private content")
    (parametres.web / "external.txt").symlink_to(outside)
    response = client.get("/external.txt")
    assert response.status_code == 404 and outside.read_text() not in response.text


@pytest.mark.parametrize("url", ["/", "/index.html", "/assistant"])
def test_build_absent_reste_une_indisponibilite_explicite(client, parametres, url):
    (parametres.web / "index.html").unlink()
    response = client.get(url)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"


def test_etag_prime_sur_date_de_modification(client):
    first = client.get("/")
    response = client.get(
        "/",
        headers={
            "If-None-Match": '"synthetic-outdated-version"',
            "If-Modified-Since": first.headers["last-modified"],
        },
    )
    assert response.status_code == 200 and response.content == first.content


def test_revalidation_sous_charge_http_reelle(serveur_http, record_testsuite_property):
    first = serveur_http.get("/asset.js")
    assert first.status_code == 200

    def revalider(_):
        start = time.monotonic()
        response = serveur_http.get("/asset.js", headers={"If-None-Match": first.headers["etag"]})
        assert response.status_code == 304 and not response.content
        assert response.headers["cache-control"] == "no-cache"
        return time.monotonic() - start

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=16) as pool:
        latencies = list(pool.map(revalider, range(256)))
    elapsed = time.monotonic() - start
    assert elapsed < 20
    record_testsuite_property(
        "static_revalidation_load",
        json.dumps(
            {
                "transport": "uvicorn-loopback",
                "requests": len(latencies),
                "concurrency": 16,
                "seconds": round(elapsed, 3),
                "p95_ms": round(statistics.quantiles(latencies, n=20)[18] * 1000, 3),
            }
        ),
    )
