"""Operational drilldowns built from measured signals, using native Grafana panels."""


def reliability(Dashboard, objectives, lang):
    d = Dashboard(
        "plateforme-slo", ("Reliability & budgets", "Fiabilité et budgets"), lang
    )
    d.data["time"] = {"from": "now-7d", "to": "now"}
    d.text(
        ("RELIABILITY / SEVEN-DAY OBJECTIVES", "FIABILITÉ / OBJECTIFS SUR SEPT JOURS"),
        (
            "**Operating objectives, no contractual SLA.** Ratios describe observed eligible requests; they do not prove uptime or reasoning quality. Budget appears only after a complete seven-day collection window. No traffic is unknown. Grey gaps remain visible.",
            "**Objectifs d’exploitation, sans SLA contractuel.** Les ratios portent sur les requêtes admissibles observées ; ils ne prouvent ni disponibilité continue ni qualité du raisonnement. Le budget apparaît après sept jours de collecte complète. Sans trafic, le résultat est inconnu. Les interruptions restent visibles.",
        ),
        4,
    )
    for i, spec in enumerate(objectives):
        select = '{slo="' + spec["id"] + '"}'
        d.row(
            (
                f"{i + 1:02d} / {spec['name'][0].upper()} · {spec['target'] * 100:g}%",
                f"{i + 1:02d} / {spec['name'][1].upper()} · {spec['target'] * 100:g} %",
            )
        )
        for x, title, metric, unit, thresholds in (
            (
                0,
                ("Observed SLI · 7 d", "SLI observé · 7 j"),
                "observed_ratio7d",
                "percentunit",
                [(None, "red"), (spec["target"], "green")],
            ),
            (
                6,
                ("Budget remaining · 7 d", "Budget restant · 7 j"),
                "budget_remaining7d",
                "percentunit",
                [(None, "red"), (0, "yellow"), (0.25, "green")],
            ),
            (
                12,
                ("Collection coverage · 7 d", "Couverture de collecte · 7 j"),
                "coverage7d",
                "percentunit",
                [(None, "#8b99ad"), (1, "green")],
            ),
            (
                18,
                ("Eligible events · 7 d", "Événements admissibles · 7 j"),
                "events7d",
                "short",
                None,
            ),
        ):
            d.panel(
                title,
                [("ambicrafted:slo_" + metric + select, "")],
                x=x,
                w=6,
                h=5,
                kind="stat",
                unit=unit,
                thresholds=thresholds,
                help_text=spec["meaning"],
            )
        d.next(5)
        d.panel(
            ("Observed ratio & objective", "Ratio observé et objectif"),
            [
                (
                    "ambicrafted:slo_observed_ratio7d" + select,
                    ("Observed SLI", "SLI observé"),
                ),
                ("ambicrafted:slo_target" + select, ("Objective", "Objectif")),
            ],
            unit="percentunit",
            help_text=spec["meaning"],
        )
        d.panel(
            (
                "Budget burn · paired windows",
                "Consommation du budget · fenêtres couplées",
            ),
            [
                ("ambicrafted:slo_burn" + window + select, window)
                for window in ("5m", "30m", "1h", "6h")
            ],
            x=12,
            unit="suffix:×",
            thresholds=[(None, "green"), (1.4, "yellow"), (3.36, "red")],
            help_text=(
                "1× spends the budget at its seven-day allowance rate. Fast alert: 5 m AND 1 h above 3.36×; slow: 30 m AND 6 h above 1.4×. Both windows need ≥20 events and complete telemetry. Low traffic can hide a single failure: inspect counts below.",
                "1× consomme le budget au rythme autorisé sur sept jours. Alerte rapide : 5 min ET 1 h au-dessus de 3,36× ; lente : 30 min ET 6 h au-dessus de 1,4×. Chaque fenêtre exige ≥20 événements et une collecte complète. Examiner aussi les erreurs isolées à faible trafic.",
            ),
        )
        d.next()
    d.row(("04 / EXCLUSIONS & SINGLE FAILURES", "04 / EXCLUSIONS ET ÉCHECS ISOLÉS"))
    d.panel(
        ("HTTP refusals & cancellations", "Refus HTTP et annulations"),
        [
            (
                'sum by (group,outcome) (increase(ambicrafted_http_requests_total{job="platform",outcome=~"client_error|cancelled"}[$__range]))',
                "{{group}} · {{outcome}}",
            ),
        ],
        help_text=(
            "Excluded from the transport denominator, not dismissed as harmless. A 429 can reject legitimate work.",
            "Exclus du dénominateur transport, sans être considérés comme anodins. Un 429 peut refuser une demande légitime.",
        ),
    )
    d.panel(
        ("AURA terminal outcomes", "Résultats terminaux AURA"),
        [
            (
                'sum by (format,outcome) (increase(ambicrafted_aura_operations_total{job="platform"}[$__range]))',
                "{{format}} · {{outcome}}",
            ),
        ],
        x=12,
    )
    d.next()
    return d


def experience(Dashboard, api, lang):
    d = Dashboard(
        "plateforme-experience",
        ("Browser & conversation", "Navigateur et conversation"),
        lang,
    )
    d.text(
        (
            "EXPERIENCE / WHAT THE BROWSER MEASURES",
            "EXPÉRIENCE / MESURES DU NAVIGATEUR",
        ),
        (
            "**RUM from the first visible period of an authenticated document.** At most one final LCP, INP and CLS sample per document, attributed to its initial route category. Not a whole SPA session or a soft-navigation measurement. Browser support and interaction affect coverage. Samples contain no page text, URLs or user identifiers.",
            "**RUM de la première période visible d’un document authentifié.** Au plus une mesure finale LCP, INP et CLS par document, attribuée à sa catégorie de route initiale. Ce n’est ni toute une session SPA ni une mesure des navigations internes. La prise en charge du navigateur et les interactions influent sur la couverture. Aucun texte, URL ou identifiant utilisateur n’est collecté.",
        ),
        4,
    )
    for i, (metric, title, boundary) in enumerate(
        (
            ("LCP", ("LCP · p75", "LCP · p75"), (2.5, 4)),
            ("INP", ("INP · p75", "INP · p75"), (0.2, 0.5)),
            ("CLS", ("CLS · p75", "CLS · p75"), (0.1, 0.25)),
        )
    ):
        base = (
            "ambicrafted_browser_layout_shift_ratio"
            if metric == "CLS"
            else "ambicrafted_browser_web_vital_seconds"
        )
        labels = 'job="platform"' + ("" if metric == "CLS" else f',metric="{metric}"')
        d.panel(
            title,
            [
                (
                    f"histogram_quantile(0.75, sum by (le) (increase({base}_bucket{{{labels}}}[$__range])))"
                    + api,
                    "",
                )
            ],
            x=i * 8,
            w=8,
            h=5,
            kind="stat",
            unit="s" if metric != "CLS" else "short",
            decimals=3 if metric == "CLS" else None,
            thresholds=[(None, "green"), (boundary[0], "yellow"), (boundary[1], "red")],
            help_text=(
                "Bucket-based estimate. Read the sample count before judging the percentile; a few visits do not establish population performance.",
                "Estimation par histogramme. Examiner le nombre de mesures avant le percentile ; quelques visites ne qualifient pas les performances d’une population.",
            ),
        )
    d.next(5)
    d.row(
        (
            "01 / RENDERING, INTERACTION & STABILITY",
            "01 / AFFICHAGE, INTERACTION ET STABILITÉ",
        )
    )
    for i, metric in enumerate(("LCP", "INP")):
        d.panel(
            (metric + " · p75 by route", metric + " · p75 par route"),
            [
                (
                    f'histogram_quantile(0.75, sum by (le,route) (rate(ambicrafted_browser_web_vital_seconds_bucket{{job="platform",metric="{metric}"}}[$__rate_interval])))'
                    + api,
                    "{{route}}",
                )
            ],
            x=i * 12,
            unit="s",
        )
    d.next()
    d.panel(
        ("Layout shift · p75 by route", "Décalage visuel · p75 par route"),
        [
            (
                'histogram_quantile(0.75, sum by (le,route) (rate(ambicrafted_browser_layout_shift_ratio_bucket{job="platform"}[$__rate_interval])))'
                + api,
                "{{route}}",
            )
        ],
        decimals=3,
    )
    d.panel(
        ("Reported samples · selected range", "Mesures reçues · période sélectionnée"),
        [
            (
                'sum by (metric,route) (increase(ambicrafted_browser_web_vital_seconds_count{job="platform"}[$__range]))'
                + api,
                "{{metric}} · {{route}}",
            ),
            (
                'sum by (route) (increase(ambicrafted_browser_layout_shift_ratio_count{job="platform"}[$__range]))'
                + api,
                "CLS · {{route}}",
            ),
        ],
        x=12,
    )
    d.next()
    d.row(
        (
            "02 / CONVERSATION SERVER TIMELINE",
            "02 / CHRONOLOGIE SERVEUR DE LA CONVERSATION",
        )
    )
    d.panel(
        ("First text · p50 / p95", "Premier texte · p50 / p95"),
        [
            (
                f'histogram_quantile({q}, sum by (le,mode) (rate(ambicrafted_aura_first_token_seconds_bucket{{job="platform"}}[$__rate_interval])))'
                + api,
                "{{mode}} · " + title,
            )
            for q, title in ((0.5, "p50"), (0.95, "p95"))
        ],
        unit="s",
        help_text=(
            "Time to the first server text fragment, not to the first audible word. Text may arrive before persistence completes.",
            "Délai du premier fragment de texte serveur, pas du premier mot audible. Le texte peut arriver avant la fin de la persistance.",
        ),
    )
    d.panel(
        ("Completed operations · p95", "Opérations terminées · p95"),
        [
            (
                'histogram_quantile(0.95, sum by (le,format,outcome) (rate(ambicrafted_aura_operation_duration_seconds_bucket{job="platform"}[$__rate_interval])))'
                + api,
                "{{format}} · {{outcome}}",
            )
        ],
        x=12,
        unit="s",
    )
    d.next()
    d.panel(
        ("Speech server duration · p95", "Durée serveur de la voix · p95"),
        [
            (
                'histogram_quantile(0.95, sum by (le,group) (rate(ambicrafted_http_request_duration_seconds_bucket{job="platform",group=~"speech_recognition|speech_synthesis"}[$__rate_interval])))'
                + api,
                "{{group}}",
            )
        ],
        unit="s",
    )
    d.panel(
        ("Document refusals by safe category", "Refus de documents par catégorie sûre"),
        [
            (
                'sum by (code) (increase(ambicrafted_document_failures_total{job="platform"}[$__range]))'
                + api,
                "{{code}}",
            )
        ],
        x=12,
    )
    d.next()
    return d


def correlation(Dashboard, lang):
    d = Dashboard(
        "plateforme-traces", ("Traces & correlation", "Traces et corrélation"), lang
    )
    d.text(
        ("INVESTIGATION / FOLLOW A REQUEST", "INVESTIGATION / SUIVRE UNE REQUÊTE"),
        (
            "**Metric → exemplar → trace → local structured event.** Tempo generates RED metrics from received spans. Select an exemplar to open its trace; use the trace's metrics link to compare service activity. API events carry the same trace ID in the private systemd journal. Loki log aggregation is not installed. Missing spans and incomplete service graphs remain possible; export failures are measured below.",
            "**Métrique → exemplar → trace → événement structuré local.** Tempo produit les métriques RED des spans reçus. Ouvrir un exemplar pour suivre sa trace, puis comparer l’activité du service grâce au lien vers les métriques. Les événements API portent le même trace ID dans le journal systemd privé. L’agrégation Loki n’est pas installée. Des spans ou des liens peuvent manquer ; les échecs d’export sont mesurés ci-dessous.",
        ),
        4,
    )
    d.row(("01 / RATE, ERRORS & DURATION", "01 / DÉBIT, ERREURS ET DURÉE"))
    d.panel(
        ("Received span rate by service", "Débit des spans reçus par service"),
        [
            (
                "sum by (service) (rate(traces_spanmetrics_calls_total[$__rate_interval]))",
                "{{service}}",
            )
        ],
        unit="ops",
    )
    d.panel(
        ("Error spans by service", "Spans en erreur par service"),
        [
            (
                'sum by (service) (rate(traces_spanmetrics_calls_total{status_code="STATUS_CODE_ERROR"}[$__rate_interval]))',
                "{{service}}",
            )
        ],
        x=12,
        unit="ops",
    )
    d.next()
    d.panel(
        ("Span duration · p95", "Durée des spans · p95"),
        [
            (
                "histogram_quantile(0.95, sum by (le,service) (rate(traces_spanmetrics_latency_bucket[$__rate_interval])))",
                "{{service}}",
            )
        ],
        unit="s",
    )
    d.panel(
        ("Service edge requests", "Requêtes entre services"),
        [
            (
                "sum by (client,server) (rate(traces_service_graph_request_total[$__rate_interval]))",
                "{{client}} → {{server}}",
            )
        ],
        x=12,
        unit="reqps",
        help_text=(
            "Only paired instrumented client/server spans establish an edge. Missing propagation or dropped spans can leave this empty.",
            "Seuls des spans client et serveur instrumentés et appariés établissent un lien. Une propagation absente ou des spans perdus peuvent laisser cette vue vide.",
        ),
    )
    d.next()
    d.row(("02 / TRACE PIPELINE HEALTH", "02 / SANTÉ DE LA COLLECTE DES TRACES"))
    d.panel(
        ("API spans · queue & export", "Spans API · file et export"),
        [
            (
                'sum by (outcome) (increase(ambicrafted_trace_spans_total{job="platform"}[$__range]))',
                "{{outcome}}",
            )
        ],
        help_text=(
            "Queued includes sent and failed spans; do not sum these outcomes. Sent means accepted by local OTLP, not proven durable or indexed. Application work continues when tracing is unavailable. Dropped or failed exports make the trace view incomplete.",
            "Queued inclut les spans sent et failed ; ne pas additionner ces résultats. Sent signifie accepté par OTLP local, sans preuve de persistance ou d’indexation. L’application continue si le traçage est indisponible. Les pertes rendent la vue incomplète.",
        ),
    )
    d.panel(
        ("Tempo received & discarded spans", "Spans reçus et rejetés par Tempo"),
        [
            (
                "sum(rate(tempo_distributor_spans_received_total[$__rate_interval]))",
                ("Received", "Reçus"),
            ),
            (
                "sum by (reason) (rate(tempo_discarded_spans_total[$__rate_interval]))",
                "{{reason}}",
            ),
        ],
        x=12,
        unit="ops",
    )
    d.next()
    d.text(
        ("03 / PRIVATE LOG INVESTIGATION", "03 / INVESTIGATION DES JOURNAUX PRIVÉS"),
        (
            "In the platform terminal, inspect `journalctl --user -u ambicrafted-console.service --since '30 min ago' -o cat`. Match the exact `trace_id` from Tempo to a structured API event. Keep raw logs private; do not paste them into external tools. Transport/delivery status does not establish reasoning quality. No external alert recipient is configured.",
            "Dans le terminal de la plateforme, consulter `journalctl --user -u ambicrafted-console.service --since '30 min ago' -o cat`. Rechercher le `trace_id` exact de Tempo dans un événement API structuré. Garder les journaux privés ; ne pas les transmettre à un outil externe. Le statut transport/livraison ne prouve pas la qualité du raisonnement. Aucun destinataire d’alerte externe n’est configuré.",
        ),
        4,
    )
    return d
