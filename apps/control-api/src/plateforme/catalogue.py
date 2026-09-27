"""Explicit capability inventory shared by UI and local MCP clients."""

OUTILS = [
    {
        "nom": "list_runbooks",
        "description": "Inventorier les procédures locales.",
        "lecture_seule": True,
    },
    {
        "nom": "read_runbook",
        "description": "Lire une source et vérifier son empreinte.",
        "lecture_seule": True,
    },
    {
        "nom": "search_runbooks",
        "description": "Rechercher un texte littéral dans les procédures.",
        "lecture_seule": True,
    },
    {
        "nom": "semantic_search",
        "description": "Chercher des passages proches via les embeddings locaux et Qdrant.",
        "lecture_seule": True,
    },
    {
        "nom": "plateforme_runbooks",
        "description": "Consulter l'inventaire des procédures via le MCP du contrôle.",
        "lecture_seule": True,
    },
    {
        "nom": "plateforme_sante",
        "description": "Consulter l'état des services et des modèles locaux via MCP.",
        "lecture_seule": True,
    },
    {
        "nom": "plateforme_analyses",
        "description": "Consulter les analyses et leurs statuts via MCP.",
        "lecture_seule": True,
    },
    {
        "nom": "voix_feminine_fr",
        "description": "Synthèse vocale locale Piper, voix française féminine SIWIS.",
        "lecture_seule": True,
    },
    {
        "nom": "transcription_fr",
        "description": "Transcription locale sur CPU ; validation du texte avant envoi.",
        "lecture_seule": True,
    },
    {
        "nom": "plateforme_preparation",
        "description": "Diagnostiquer les capacités locales réellement mesurées, sans certifier la production.",
        "lecture_seule": True,
    },
    {
        "nom": "plateforme_outils",
        "description": "Consulter le catalogue et les limites des outils locaux.",
        "lecture_seule": True,
    },
    {
        "nom": "plateforme_analyse",
        "description": "Lire une analyse existante sans approuver ni modifier sa proposition.",
        "lecture_seule": True,
    },
    {
        "nom": "plateforme_lire_runbook",
        "description": "Lire une procédure locale et son empreinte pour vérifier une source.",
        "lecture_seule": True,
    },
    {
        "nom": "plateforme_recherche",
        "description": "Rechercher dans les procédures par texte ou embeddings locaux.",
        "lecture_seule": True,
    },
    {
        "nom": "plateforme_journal",
        "description": "Consulter au plus 100 événements d'audit, sans contenu des alertes.",
        "lecture_seule": True,
    },
    {
        "nom": "voix_feminine_en",
        "description": "Synthèse vocale féminine anglaise hors ligne.",
        "lecture_seule": True,
    },
    {
        "nom": "transcription_en",
        "description": "Transcription anglaise hors ligne sur CPU.",
        "lecture_seule": True,
    },
    {
        "nom": "operations_locales",
        "description": "Vérification, indexation, sauvegarde et test de restauration depuis CLI ou UI.",
        "lecture_seule": False,
    },
]
