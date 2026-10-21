"""Real authenticated boundary: numeric-only, bounded, same-origin browser measurements."""

import pytest


def sample(**changes):
    return {"samples": [{"metric": "LCP", "route": "workspace", "value": 2500, **changes}]}


def test_browser_metrics_require_cookie_csrf_origin_not_cli(client, bearer, session):
    url = "/api/telemetrie/navigation"
    assert client.post(url, json=sample(), headers=bearer).status_code == 403
    assert client.post(url, json=sample()).status_code == 403
    assert (
        client.post(
            url, json=sample(), headers={**session, "Origin": "https://other.invalid"}
        ).status_code
        == 403
    )
    assert client.post(url, json=sample(), headers=session).status_code == 204
    client.cookies.clear()
    assert client.post(url, json=sample(), headers=session).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"metric": "secret"},
        {"route": "/client/private"},
        {"value": True},
        {"value": "12"},
        {"value": -1},
        {"value": 300001},
        {"metric": "CLS", "value": 101},
        {"url": "private-content"},
    ],
)
def test_invalid_values_do_not_create_labels_or_samples(client, session, application, changes):
    assert (
        client.post(
            "/api/telemetrie/navigation", headers=session, json=sample(**changes)
        ).status_code
        == 422
    )
    metrics = list(application.state.mesures.registry.collect())
    assert not any(
        s.name.endswith("_count") and s.value
        for m in metrics
        if m.name.startswith("ambicrafted_browser")
        for s in m.samples
    )


@pytest.mark.parametrize(
    "body",
    [
        b'{"samples":[{"metric":"LCP","route":"workspace","value":NaN}]}',
        b'{"samples":[{"metric":"CLS","route":"workspace","value":Infinity}]}',
    ],
)
def test_non_finite_values_refused(client, session, body):
    response = client.post(
        "/api/telemetrie/navigation",
        headers={**session, "Content-Type": "application/json"},
        content=body,
    )
    assert response.status_code == 422


def test_measurements_convert_ms_and_never_enter_business_http_group(client, session, application):
    response = client.post(
        "/api/telemetrie/navigation",
        headers=session,
        json={
            "samples": [
                {"metric": "LCP", "route": "workspace", "value": 2500},
                {"metric": "INP", "route": "guide", "value": 200},
                {"metric": "CLS", "route": "workspace", "value": 0.1},
            ]
        },
    )
    assert response.status_code == 204 and response.content == b""
    measures = application.state.mesures
    assert measures.web_vitals.labels("LCP", "workspace")._sum.get() == 2.5
    assert measures.web_vitals.labels("INP", "guide")._sum.get() == 0.2
    assert measures.layout_shift.labels("workspace")._sum.get() == 0.1
    assert measures.requests.labels("telemetry", "success")._value.get() == 1


def test_payload_batch_and_rate_limits(client, session):
    url = "/api/telemetrie/navigation"
    assert client.post(url, headers=session, json={"samples": []}).status_code == 422
    assert (
        client.post(url, headers=session, json={"samples": sample()["samples"] * 13}).status_code
        == 422
    )
    assert (
        client.post(url, headers=session, json={"samples": [], "extra": "x" * 4096}).status_code
        == 413
    )
    for _ in range(30):
        assert client.post(url, headers=session, json=sample()).status_code == 204
    refused = client.post(url, headers=session, json=sample())
    assert refused.status_code == 429 and refused.headers["Retry-After"] == "60"
