"""Reproducible native Grafana dashboards; no plugins, injected scripts or demo data."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).parent / "grafana/json"
DS = {"type": "prometheus", "uid": "prometheus"}
FRESH = " and on() (max(ambicrafted:telemetry_fresh) == 1)"
API = FRESH + " and on() (max(ambicrafted_control_api_scrape_success) == 1)"
HTTP = 'ambicrafted_http_requests_total{job="platform"}'
VIEWS = [
    ("plateforme-sre", "Mission control", "Centre de contrôle"),
    ("plateforme-agentic", "Agents & AURA", "Agents et AURA"),
    ("plateforme-infrastructure", "Infrastructure", "Infrastructure"),
]


class Dashboard:
    def __init__(self, uid, title, lang):
        self.lang, self.y, self.panels = lang, 0, []
        self.uid = uid + ("-fr" if lang == "fr" else "")
        self.data = {
            "uid": self.uid,
            "title": "Ambicrafted · " + self.t(title),
            "schemaVersion": 39,
            "version": 2,
            "editable": False,
            "tags": ["ambicrafted", "local", lang],
            "timezone": "browser",
            "refresh": "30s",
            "time": {"from": "now-3h", "to": "now"},
            "timepicker": {"refresh_intervals": ["30s", "1m", "5m", "15m"]},
            "graphTooltip": 1,
            "links": [],
            "panels": self.panels,
            "annotations": {
                "list": [
                    {
                        "builtIn": 1,
                        "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                        "enable": True,
                        "hide": True,
                        "iconColor": "#5edbd0",
                        "name": "Annotations & Alerts",
                        "type": "dashboard",
                    }
                ]
            },
        }
        for target, en, fr in VIEWS:
            self.data["links"].append(
                {
                    "title": self.t((en, fr)),
                    "type": "link",
                    "icon": "dashboard",
                    "url": "/d/" + target + ("-fr" if lang == "fr" else ""),
                    "keepTime": True,
                    "includeVars": True,
                    "targetBlank": False,
                }
            )
        self.data["links"].append(
            {
                "title": "English" if lang == "fr" else "Français",
                "type": "link",
                "url": "/d/" + uid + ("" if lang == "fr" else "-fr"),
                "keepTime": True,
            }
        )
        self.data["links"].append(
            {
                "title": self.t(("Workspace", "Espace de travail")),
                "type": "link",
                "url": "http://localhost:8787",
                "targetBlank": True,
                "icon": "external link",
            }
        )

    def t(self, value):
        if isinstance(value, tuple):
            return value[1 if self.lang == "fr" else 0]
        translations = {
            "Used": "Utilisé",
            "Available": "Disponible",
            "Queued": "En attente",
            "Capacity": "Capacité",
            "Measured": "Mesurés",
            "All retained SRE runs": "Toutes les exécutions SRE conservées",
            "Indexed fragments": "Fragments indexés",
            "Messages": "Messages",
            "RAM used": "RAM utilisée",
            "RAM total": "RAM totale",
            "Swap used": "Swap utilisé",
            "GPU {{gpu}} used": "GPU {{gpu}} utilisé",
            "GPU {{gpu}} total": "GPU {{gpu}} total",
            "Active series": "Séries actives",
            "Failures": "Erreurs",
            "Missed iterations": "Itérations manquées",
            "Collector": "Collecteur",
            "API collection": "Collecte API",
            "Snapshot": "Instantané",
        }
        return translations.get(value, value) if self.lang == "fr" else value

    def text(self, title, content, height=3):
        self.panels.append(
            {
                "id": len(self.panels) + 1,
                "type": "text",
                "title": self.t(title),
                "gridPos": {"x": 0, "y": self.y, "w": 24, "h": height},
                "options": {"mode": "markdown", "content": self.t(content)},
            }
        )
        self.y += height

    def row(self, title):
        self.panels.append(
            {
                "id": len(self.panels) + 1,
                "type": "row",
                "title": self.t(title),
                "collapsed": False,
                "gridPos": {"x": 0, "y": self.y, "w": 24, "h": 1},
                "panels": [],
            }
        )
        self.y += 1

    def panel(
        self,
        title,
        queries,
        *,
        x=0,
        w=12,
        h=8,
        kind="timeseries",
        unit="short",
        help_text="",
        thresholds=None,
    ):
        defaults = {
            "unit": unit,
            "noValue": self.t(("No samples", "Aucune mesure")),
            "mappings": [
                {
                    "type": "special",
                    "options": {
                        "match": "null",
                        "result": {
                            "text": self.t(("No samples", "Aucune mesure")),
                            "color": "#8b99ad",
                        },
                    },
                }
            ],
            "color": {"mode": "palette-classic"},
            "decimals": 1,
            "thresholds": {
                "mode": "absolute",
                "steps": [{"color": "green", "value": None}],
            },
        }
        if thresholds:
            defaults["thresholds"]["steps"] = [
                {"color": c, "value": v} for v, c in thresholds
            ]
        options = {}
        if kind == "timeseries":
            defaults["custom"] = {
                "drawStyle": "line",
                "lineInterpolation": "smooth",
                "lineWidth": 2,
                "fillOpacity": 12,
                "gradientMode": "opacity",
                "showPoints": "never",
                "spanNulls": False,
                "axisBorderShow": False,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "stacking": {"mode": "none", "group": "A"},
                "thresholdsStyle": {"mode": "dashed" if thresholds else "off"},
            }
            options = {
                "legend": {
                    "displayMode": "table",
                    "placement": "bottom",
                    "showLegend": True,
                    "calcs": ["lastNotNull", "max"],
                },
                "tooltip": {"mode": "multi", "sort": "desc"},
            }
        elif kind == "stat":
            defaults["color"] = {
                "mode": "thresholds" if thresholds else "fixed",
                "fixedColor": "cyan",
            }
            options = {
                "reduceOptions": {
                    "calcs": ["lastNotNull"],
                    "fields": "",
                    "values": False,
                },
                "orientation": "horizontal",
                "textMode": "auto",
                "colorMode": "value",
                "graphMode": "area",
                "justifyMode": "auto",
                "wideLayout": True,
                "text": {"valueSize": 36, "titleSize": 14},
            }
        elif kind == "state-timeline":
            defaults["mappings"] = [
                {
                    "type": "value",
                    "options": {
                        "-1": {
                            "text": self.t(("Unknown", "Inconnu")),
                            "color": "#8b99ad",
                            "index": 2,
                        },
                        "0": {
                            "text": self.t(("Unavailable", "Indisponible")),
                            "color": "red",
                            "index": 0,
                        },
                        "1": {
                            "text": self.t(("Responding", "Disponible")),
                            "color": "green",
                            "index": 1,
                        },
                    },
                }
            ]
            defaults["color"] = {"mode": "thresholds"}
            options = {
                "mergeValues": True,
                "rowHeight": 0.7,
                "showValue": "never",
                "legend": {"showLegend": False},
                "tooltip": {"mode": "single"},
            }
        targets = []
        for i, (expr, legend) in enumerate(queries):
            targets.append(
                {
                    "refId": chr(65 + i),
                    "expr": expr,
                    "legendFormat": self.t(legend),
                    "editorMode": "code",
                    "range": kind != "stat",
                    "instant": kind == "stat",
                    "datasource": DS,
                }
            )
        self.panels.append(
            {
                "id": len(self.panels) + 1,
                "type": kind,
                "title": self.t(title),
                "description": self.t(help_text),
                "datasource": DS,
                "targets": targets,
                "gridPos": {"x": x, "y": self.y, "w": w, "h": h},
                "fieldConfig": {"defaults": defaults, "overrides": []},
                "options": options,
            }
        )

    def next(self, h=8):
        self.y += h


def overview(lang):
    d = Dashboard("plateforme-sre", ("Mission control", "Centre de contrôle"), lang)
    d.text(
        ("LOCAL INTELLIGENCE / OPERATIONS", "INTELLIGENCE LOCALE / OPÉRATIONS"),
        (
            "**Observe → investigate → verify.** Real local telemetry · 30 s snapshots · choose a time range above. Empty means unmeasured, not healthy. Use the linked views to investigate.",
            "**Observer → investiguer → vérifier.** Télémétrie locale réelle · collecte toutes les 30 s · période réglable en haut. Vide signifie non mesuré, pas sain. Les vues liées permettent d’investiguer.",
        ),
    )
    items = [
        (
            ("Services responding / 6", "Services disponibles / 6"),
            "sum(ambicrafted_service_up)" + API,
            "short",
            [(None, "red"), (6, "green")],
        ),
        (
            ("Collector age", "Âge de la collecte"),
            "time() - max(ambicrafted_snapshot_timestamp_seconds)",
            "s",
            [(None, "green"), (60, "yellow"), (90, "red")],
        ),
        (
            ("API requests / min", "Requêtes API / min"),
            f"sum(rate({HTTP}[$__rate_interval])) * 60" + API,
            "short",
            None,
        ),
        (
            ("Waiting for approval", "En attente de validation"),
            'sum(ambicrafted_retained_runs{state="en_attente_humain"})' + API,
            "short",
            None,
        ),
    ]
    for i, (title, expr, unit, thresholds) in enumerate(items):
        d.panel(
            title,
            [(expr, "")],
            x=i * 6,
            w=6,
            h=5,
            kind="stat",
            unit=unit,
            thresholds=thresholds,
        )
    d.next(5)
    d.row(("01 / HEALTH & FRESHNESS", "01 / SANTÉ ET FRAÎCHEUR"))
    d.panel(
        ("Platform availability", "Disponibilité de la plateforme"),
        [
            (
                "(ambicrafted_service_up"
                + API
                + ') or on() label_replace(vector(-1), "service", "unknown", "", "")',
                "{{service}}",
            )
        ],
        kind="state-timeline",
        w=16,
        thresholds=[(None, "red"), (1, "green")],
        help_text=(
            "HTTP probes, cached for up to 10 seconds. Not an inference or uptime SLO.",
            "Sondes HTTP, cache de 10 secondes maximum. Ce n’est pas un SLO d’inférence ou de disponibilité.",
        ),
    )
    d.panel(
        ("Collection chain", "Chaîne de collecte"),
        [
            ("up", "{{job}}"),
            ("ambicrafted_control_api_scrape_success" + FRESH, "Control API"),
        ],
        x=16,
        w=8,
        kind="state-timeline",
        thresholds=[(None, "red"), (1, "green")],
    )
    d.next()
    d.panel(
        ("Local service response", "Réponse des services locaux"),
        [("ambicrafted_service_probe_duration_seconds" + API, "{{service}}")],
        unit="s",
    )
    d.panel(
        ("API throughput by outcome", "Débit API par résultat"),
        [(f"sum by (outcome) (rate({HTTP}[$__rate_interval]))" + API, "{{outcome}}")],
        x=12,
        unit="reqps",
    )
    d.next()
    d.row(("02 / CAPACITY & CONTINUITY", "02 / CAPACITÉ ET CONTINUITÉ"))
    d.panel(
        ("Host memory pressure", "Pression mémoire du système"),
        [
            (
                "1 - ambicrafted_host_memory_memavailable_bytes / ambicrafted_host_memory_memtotal_bytes"
                + FRESH,
                "Used",
            )
        ],
        unit="percentunit",
        thresholds=[(None, "green"), (0.85, "yellow"), (0.95, "red")],
    )
    d.panel(
        ("Data disk available", "Espace disque disponible"),
        [("ambicrafted_data_disk_available_bytes" + FRESH, "Available")],
        x=12,
        unit="bytes",
    )
    d.next()
    d.panel(
        ("Queue / available capacity", "File / capacité disponible"),
        [
            ("ambicrafted_queue_depth" + API, "Queued"),
            ("ambicrafted_queue_capacity" + API, "Capacity"),
        ],
    )
    d.panel(
        ("Backup age", "Âge de la sauvegarde"),
        [
            (
                "time() - ambicrafted_backup_last_completed_timestamp_seconds" + FRESH,
                "Last completed local backup",
            )
        ],
        x=12,
        unit="s",
        thresholds=[(None, "green"), (129600, "yellow"), (259200, "red")],
        help_text=(
            "Based on a completed local manifest. Does not prove restore success or off-host protection.",
            "Basé sur un manifeste local complet. Ne prouve ni une restauration réussie ni une copie hors du poste.",
        ),
    )
    d.next()
    d.panel(
        ("Alerts requiring attention", "Alertes à examiner"),
        [
            (
                'sum(ALERTS{alertstate="firing"}) or vector(0)',
                ("Active alerts", "Alertes actives"),
            )
        ],
        w=24,
        kind="stat",
        h=5,
        thresholds=[(None, "green"), (1, "yellow"), (5, "red")],
        help_text=(
            "Zero means Prometheus currently reports no firing rule. An unavailable datasource remains unknown. Inspect Prometheus Alerts for rule details; no external recipient is configured.",
            "Zéro signifie que Prometheus ne signale aucune règle active. Une source indisponible reste inconnue. Consultez les alertes Prometheus pour le détail ; aucun destinataire externe n’est configuré.",
        ),
    )
    d.next(5)
    return d


def agentic(lang):
    d = Dashboard("plateforme-agentic", ("Agents & AURA", "Agents et AURA"), lang)
    d.text(
        ("SUPERVISED WORK / MEASURED SIGNALS", "TRAVAIL SUPERVISÉ / MESURES RÉELLES"),
        (
            "Request counters reset on API restart. Stored-run gauges decrease after deletion/retention. Voice durations cover server transcription/synthesis, not microphone capture or perceived round-trip latency.",
            "Les compteurs de requêtes repartent à zéro au redémarrage de l’API. Les jauges baissent après suppression/rétention. Les durées vocales mesurent le traitement serveur, pas la capture micro ni la conversation complète.",
        ),
    )
    for i, (title, expr) in enumerate(
        [
            (
                ("Retained SRE runs", "Analyses SRE conservées"),
                'sum(ambicrafted_retained_runs{kind="graphe"})',
            ),
            (("Conversations", "Conversations"), "ambicrafted_retained_conversations"),
            (("Documents", "Documents"), "ambicrafted_retained_documents"),
            (("Inference lease", "Inférence occupée"), "ambicrafted_inference_busy"),
        ]
    ):
        d.panel(title, [(expr + API, "")], x=i * 6, w=6, h=5, kind="stat")
    d.next(5)
    d.row(("01 / WORKFLOW & HUMAN OVERSIGHT", "01 / WORKFLOW ET VALIDATION HUMAINE"))
    d.panel(
        ("Retained SRE states", "États des analyses SRE conservées"),
        [('ambicrafted_retained_runs{kind="graphe"}' + API, "{{state}}")],
    )
    d.panel(
        ("Maintenance states", "États des opérations de maintenance"),
        [('ambicrafted_retained_runs{kind="operation"}' + API, "{{state}}")],
        x=12,
    )
    d.next()
    d.row(("02 / AURA & API RESPONSE", "02 / RÉPONSE AURA ET API"))
    for i, (title, quantile) in enumerate(
        [
            (("Server duration · p50", "Durée serveur · p50"), 0.5),
            (("Server duration · p95", "Durée serveur · p95"), 0.95),
        ]
    ):
        d.panel(
            title,
            [
                (
                    f'histogram_quantile({quantile}, sum by (le,group) (rate(ambicrafted_http_request_duration_seconds_bucket{{group=~"assistant|speech_recognition|speech_synthesis"}}[$__rate_interval])))'
                    + API,
                    "{{group}}",
                )
            ],
            x=i * 12,
            unit="s",
            help_text=(
                "Percentile estimates from histogram buckets. Few observations make tail estimates uncertain. Streaming duration ends at the final body.",
                "Percentiles estimés par histogramme. Peu d’observations rendent les estimations incertaines. Le streaming est mesuré jusqu’au dernier fragment.",
            ),
        )
    d.next()
    d.panel(
        ("Requests by capability", "Requêtes par capacité"),
        [(f"sum by (group) (rate({HTTP}[$__rate_interval]))" + API, "{{group}}")],
        unit="reqps",
    )
    d.panel(
        ("Errors and interruptions", "Erreurs et interruptions"),
        [
            (
                'sum by (group,outcome) (increase(ambicrafted_http_requests_total{outcome!="success"}[$__range]))'
                + API,
                "{{group}} · {{outcome}}",
            )
        ],
        x=12,
    )
    d.next()
    d.row(
        (
            "03 / TOKEN ACCOUNTING · RETAINED SRE REPORTS",
            "03 / TOKENS · RAPPORTS SRE CONSERVÉS",
        )
    )
    for i, (title, field, unit) in enumerate(
        [
            (
                ("Observed input tokens", "Tokens d’entrée mesurés"),
                "tokens_entree",
                "short",
            ),
            (
                ("Observed output tokens", "Tokens de sortie mesurés"),
                "tokens_sortie",
                "short",
            ),
            (("Observed total tokens", "Total des tokens mesurés"), "tokens", "short"),
            (("Reported API cost", "Coût API déclaré"), "cout_usd", "currencyUSD"),
        ]
    ):
        expr = f"ambicrafted_retained_{field} and on(job,instance) (ambicrafted_retained_{field}_measured_runs > 0)"
        d.panel(
            title,
            [(expr + API, "")],
            x=i * 6,
            w=6,
            h=5,
            kind="stat",
            unit=unit,
            help_text=(
                "Observed retained sum; may be partial. Missing usage is unknown, not free. API cost excludes hardware and electricity. AURA usage is not included.",
                "Somme mesurée des rapports conservés, parfois partielle. Une mesure absente est inconnue, pas gratuite. Le coût API exclut matériel et électricité. L’usage d’AURA n’est pas inclus.",
            ),
        )
    d.next(5)
    d.panel(
        ("Reports with token measurements", "Rapports avec mesure de tokens"),
        [
            ("ambicrafted_retained_tokens_measured_runs" + API, "Measured"),
            (
                'sum(ambicrafted_retained_runs{kind="graphe"})' + API,
                "All retained SRE runs",
            ),
        ],
    )
    d.panel(
        ("Knowledge & context inventory", "Inventaire des sources et du contexte"),
        [
            ("ambicrafted_index_points" + API, "Indexed fragments"),
            ("ambicrafted_retained_documents" + API, "Documents"),
            ("ambicrafted_retained_messages" + API, "Saved messages"),
        ],
        x=12,
    )
    d.next()
    d.text(
        ("Trace a slow investigation", "Examiner une investigation lente"),
        (
            'Open **Explore → Plateforme Tempo** and query `{ resource.service.name = "sre-agent" }`. Traces show bounded tool/model stages; prompts, document bodies and conversations do not belong in metrics. Token budgets remain observed ceilings, not prepaid hard quotas.',
            'Ouvrez **Explore → Plateforme Tempo** et cherchez `{ resource.service.name = "sre-agent" }`. Les traces montrent les étapes outils/modèle ; les prompts, documents et conversations ne figurent pas dans les métriques. Les budgets de tokens restent des plafonds observés, pas des quotas prépayés.',
        ),
        4,
    )
    return d


def infrastructure(lang):
    d = Dashboard(
        "plateforme-infrastructure", ("Infrastructure", "Infrastructure"), lang
    )
    d.text(
        ("HOST / GPU / TELEMETRY", "SYSTÈME / GPU / TÉLÉMÉTRIE"),
        (
            "Host metrics describe the Linux/WSL environment. GPU sensors include all shared GPU workloads. Unsupported sensors stay absent. The collector has no Docker socket or access to other client deployments.",
            "Les mesures système décrivent l’environnement Linux/WSL. Les capteurs GPU couvrent aussi les autres usages du GPU partagé. Un capteur non supporté reste absent. Le collecteur n’a ni socket Docker ni accès aux autres déploiements clients.",
        ),
    )
    for i, (title, expr, unit) in enumerate(
        [
            (
                ("Host memory available", "Mémoire système disponible"),
                "ambicrafted_host_memory_memavailable_bytes",
                "bytes",
            ),
            (
                ("Disk available", "Disque disponible"),
                "ambicrafted_data_disk_available_bytes",
                "bytes",
            ),
            (
                ("GPU memory used", "Mémoire GPU utilisée"),
                "sum(ambicrafted_gpu_memory_used_bytes)",
                "bytes",
            ),
            (
                ("API resident memory", "Mémoire résidente API"),
                'process_resident_memory_bytes{job="platform"}',
                "bytes",
            ),
        ]
    ):
        d.panel(title, [(expr + FRESH, "")], x=i * 6, w=6, h=5, kind="stat", unit=unit)
    d.next(5)
    d.row(("01 / HOST CAPACITY", "01 / CAPACITÉ DU SYSTÈME"))
    d.panel(
        ("CPU time by mode", "Temps CPU par mode"),
        [
            (
                "sum by(mode)(rate(ambicrafted_host_cpu_seconds_total[$__rate_interval])) / ignoring(mode) group_left sum(rate(ambicrafted_host_cpu_seconds_total[$__rate_interval]))"
                + FRESH,
                "{{mode}}",
            )
        ],
        unit="percentunit",
    )
    d.panel(
        ("Memory and swap", "Mémoire et swap"),
        [
            (
                "ambicrafted_host_memory_memtotal_bytes - ambicrafted_host_memory_memavailable_bytes"
                + FRESH,
                "RAM used",
            ),
            ("ambicrafted_host_memory_memtotal_bytes" + FRESH, "RAM total"),
            (
                "ambicrafted_host_memory_swaptotal_bytes - ambicrafted_host_memory_swapfree_bytes"
                + FRESH,
                "Swap used",
            ),
        ],
        x=12,
        unit="bytes",
    )
    d.next()
    d.panel(
        ("Filesystem headroom", "Marge du système de fichiers"),
        [
            (
                "ambicrafted_data_disk_available_bytes / ambicrafted_data_disk_size_bytes"
                + FRESH,
                "Bytes available",
            ),
            (
                "ambicrafted_data_disk_inodes_available_ratio" + FRESH,
                "Inodes available",
            ),
        ],
        unit="percentunit",
    )
    d.panel(
        ("Load relative to CPU count", "Charge relative au nombre de CPU"),
        [
            (
                "ambicrafted_host_load1 / ambicrafted_host_cpu_count" + FRESH,
                "Load / CPUs",
            )
        ],
        x=12,
        help_text=(
            "Runnable and uninterruptible tasks relative to CPUs; this is not CPU utilization.",
            "Tâches exécutables et non interruptibles rapportées aux CPU ; ce n’est pas le taux d’utilisation CPU.",
        ),
    )
    d.next()
    d.row(("02 / GPU SENSORS", "02 / CAPTEURS GPU"))
    d.panel(
        ("GPU utilization", "Utilisation GPU"),
        [("ambicrafted_gpu_utilization_ratio" + FRESH, "GPU {{gpu}}")],
        unit="percentunit",
    )
    d.panel(
        ("GPU memory", "Mémoire GPU"),
        [
            ("ambicrafted_gpu_memory_used_bytes" + FRESH, "GPU {{gpu}} used"),
            ("ambicrafted_gpu_memory_total_bytes" + FRESH, "GPU {{gpu}} total"),
        ],
        x=12,
        unit="bytes",
    )
    d.next()
    d.panel(
        ("GPU temperature", "Température GPU"),
        [("ambicrafted_gpu_temperature_celsius" + FRESH, "GPU {{gpu}}")],
        unit="celsius",
        thresholds=[(None, "green"), (85, "yellow")],
    )
    d.panel(
        ("GPU power draw", "Puissance GPU"),
        [("ambicrafted_gpu_power_watts" + FRESH, "GPU {{gpu}}")],
        x=12,
        unit="watt",
    )
    d.next()
    d.row(("03 / MONITOR THE MONITORING", "03 / SUPERVISER LA SUPERVISION"))
    d.panel(
        ("Scrape duration", "Durée des scrapes"),
        [("scrape_duration_seconds", "{{job}}")],
        unit="s",
    )
    d.panel(
        ("Samples per scrape", "Échantillons par scrape"),
        [("scrape_samples_scraped", "{{job}}")],
        x=12,
    )
    d.next()
    d.panel(
        ("Prometheus active series", "Séries actives Prometheus"),
        [("prometheus_tsdb_head_series", "Active series")],
    )
    d.panel(
        ("Rule failures & missed iterations", "Erreurs et retards des règles"),
        [
            (
                "sum(increase(prometheus_rule_evaluation_failures_total[$__range]))",
                "Failures",
            ),
            (
                "sum(increase(prometheus_rule_group_iterations_missed_total[$__range]))",
                "Missed iterations",
            ),
        ],
        x=12,
    )
    d.next()
    d.panel(
        ("Tempo spans received", "Spans reçus par Tempo"),
        [
            (
                "sum(rate(tempo_distributor_spans_received_total[$__rate_interval]))",
                "Spans / s",
            )
        ],
        unit="ops",
    )
    d.panel(
        ("Resident memory by service", "Mémoire résidente par service"),
        [
            ('process_resident_memory_bytes{job!="grafana"}', "{{job}}"),
            ('grafana_process_resident_memory_bytes{job="grafana"}', "grafana"),
        ],
        x=12,
        unit="bytes",
    )
    d.next()
    return d


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for lang in ("en", "fr"):
        for make in (overview, agentic, infrastructure):
            dashboard = make(lang)
            filename = (
                "plateforme.json"
                if dashboard.uid == "plateforme-sre"
                else dashboard.uid + ".json"
            )
            target = ROOT / filename
            text = json.dumps(dashboard.data, ensure_ascii=False, indent=2) + "\n"
            if args.check:
                if not target.exists() or target.read_text() != text:
                    raise SystemExit(f"Regenerate dashboard: {filename}")
            else:
                target.write_text(text)


if __name__ == "__main__":
    main()
