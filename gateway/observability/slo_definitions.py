"""Personal operating objectives, not a contractual SLA or a reasoning-quality score."""

import json
from pathlib import Path

# Seven days fits the existing fourteen-day retention ceiling. Size-based eviction
# can still shorten it; the coverage rule detects missing history instead of
# inferring success. All ratios below describe observed, admitted requests only.
WINDOW_SECONDS = 7 * 24 * 3600
INTERVAL_SECONDS = 15
HTTP_SCOPE = 'group=~"analyses|conversations|speech_recognition|speech_synthesis|assistant|memory|knowledge"'
OBJECTIVES = (
    {
        "id": "http_transport",
        "target": 0.999,
        "name": ("API transport", "Transport API"),
        "total": f'ambicrafted_http_requests_total{{job="platform",{HTTP_SCOPE},outcome=~"success|server_error"}}',
        "good": f'ambicrafted_http_requests_total{{job="platform",{HTTP_SCOPE},outcome="success"}}',
        "meaning": (
            "Successful HTTP responses / successful or server-error responses. Authentication, probes, telemetry, 4xx and cancellations are excluded. A 200 stream can contain an application failure: inspect AURA delivery separately.",
            "Réponses HTTP réussies / réponses réussies ou en erreur serveur. Authentification, sondes, télémétrie, 4xx et annulations sont exclus. Un flux 200 peut contenir une erreur métier : consulter séparément la livraison AURA.",
        ),
    },
    {
        "id": "aura_delivery",
        "target": 0.99,
        "name": ("AURA delivery", "Livraison AURA"),
        "total": 'ambicrafted_aura_operations_total{job="platform",outcome=~"success|error|timeout"}',
        "good": 'ambicrafted_aura_operations_total{job="platform",outcome="success"}',
        "meaning": (
            "Technically delivered responses / admitted terminal operations, including application errors inside HTTP 200. Replays, admission refusals and cancellations are shown separately. Delivery does not establish factual correctness.",
            "Réponses techniquement livrées / opérations admises terminées, y compris les erreurs métier dans un HTTP 200. Rejeux, refus d’admission et annulations sont présentés séparément. Une livraison ne prouve pas l’exactitude de la réponse.",
        ),
    },
    {
        "id": "aura_latency",
        "target": 0.95,
        "name": ("AURA within 30 s", "AURA en 30 s maximum"),
        "total": 'ambicrafted_aura_operation_duration_seconds_count{job="platform",outcome="success"}',
        "good": 'ambicrafted_aura_operation_duration_seconds_bucket{job="platform",outcome="success",le="30.0"}',
        "meaning": (
            "Successful operations completed in at most 30 seconds / successful operations. Includes server generation and persistence, excludes capture and audio playback. Failures cannot improve the delivery objective; assess both together.",
            "Opérations réussies en 30 secondes maximum / opérations réussies. Inclut génération serveur et persistance, exclut capture et lecture audio. Évaluer conjointement l’objectif de livraison pour ne pas masquer les échecs.",
        ),
    },
)


def rules():
    records = []
    alerts = []
    validity = (
        "(max(ambicrafted:telemetry_fresh) * "
        'max(ambicrafted_control_api_scrape_success{job="platform"}))'
    )
    for objective in OBJECTIVES:
        label = {"slo": objective["id"]}
        selector = '{slo="' + objective["id"] + '"}'

        def record(name, expr, labels=label):
            records.append(
                {"record": "ambicrafted:slo_" + name, "expr": expr, "labels": labels}
            )

        record("target", f"vector({objective['target']})")
        record(
            "observation_valid",
            f"({validity} and on() (count({objective['total']}) > 0)) or vector(0)",
        )
        record(
            "coverage7d",
            f"clamp_max(sum_over_time(ambicrafted:slo_observation_valid{selector}[7d]) / {WINDOW_SECONDS // INTERVAL_SECONDS}, 1)",
        )
        for window in ("5m", "30m", "1h", "6h", "7d"):
            total = f"sum(increase({objective['total']}[{window}]))"
            good = f"sum(increase({objective['good']}[{window}]))"
            record("events" + window, total)
            record("good_events" + window, good)
            # Preserve NaN/absence when there is no traffic; no clamp_min(1)
            # denominator and no or vector(0) that could invent healthy traffic.
            observed = "ambicrafted:slo_events" + window + selector
            successful = "ambicrafted:slo_good_events" + window + selector
            record(
                "bad_ratio" + window,
                f"(clamp_min(({observed} - {successful}), 0) / {observed}) and ({observed} > 0)",
            )
            if window != "7d":
                record(
                    "burn" + window,
                    f"ambicrafted:slo_bad_ratio{window}{selector} / (1 - ambicrafted:slo_target{selector})",
                )
        record("observed_ratio7d", f"1 - ambicrafted:slo_bad_ratio7d{selector}")
        # A budget is hidden until the entire window was observable. The raw
        # ratio and coverage remain available during warm-up and telemetry gaps.
        record(
            "budget_remaining7d",
            f"(1 - ambicrafted:slo_bad_ratio7d{selector} / (1 - ambicrafted:slo_target{selector})) and on(slo) (ambicrafted:slo_coverage7d{selector} >= 1)",
        )
        for name, short, long, burn, severity, spend in (
            ("Fast", "5m", "1h", 3.36, "critical", "2 percent in one hour"),
            ("Slow", "30m", "6h", 1.4, "warning", "5 percent in six hours"),
        ):
            alerts.append(
                {
                    "alert": "PlatformSLOBurn" + name,
                    "expr": (
                        f"(ambicrafted:slo_burn{short}{selector} > {burn}) "
                        f"and (ambicrafted:slo_burn{long}{selector} > {burn}) "
                        f"and (ambicrafted:slo_events{short}{selector} >= 20) "
                        f"and (ambicrafted:slo_events{long}{selector} >= 20) "
                        f"and (ambicrafted:slo_observation_valid{selector} == 1) "
                        f"and (min_over_time(ambicrafted:slo_observation_valid{selector}[{long}]) == 1) "
                        f"and (count_over_time(ambicrafted:slo_observation_valid{selector}[{long}]) >= {int((3600 if long == '1h' else 21600) / INTERVAL_SECONDS)})"
                    ),
                    "for": "2m",
                    "labels": {"severity": severity, **label},
                    "annotations": {
                        "summary": "Observed {{ $labels.slo }} error budget is burning quickly",
                        "description": f"Seven-day operating objective: projected {spend} at this burn rate if traffic is comparable across windows. This is not measured budget spend under changing traffic. Both windows have at least 20 eligible events and complete collection. Low-volume cases need direct review. This is not an external paging delivery guarantee.",
                        "runbook_url": "http://localhost:8787/guide",
                        "dashboard_url": "http://localhost:3000/d/plateforme-slo",
                    },
                }
            )
    return {
        "groups": [
            {"name": "ambicrafted-slo-recording", "interval": "15s", "rules": records},
            {"name": "ambicrafted-slo-alerts", "interval": "15s", "rules": alerts},
        ]
    }


def write_rules(check=False):
    path = Path(__file__).with_name("slo.yml")
    text = json.dumps(rules(), ensure_ascii=False, indent=2) + "\n"
    if check:
        if not path.exists() or path.read_text() != text:
            raise SystemExit("Regenerate SLO rules with build_dashboards.py")
    else:
        path.write_text(text)
