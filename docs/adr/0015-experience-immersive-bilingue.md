# ADR 0015 — Expérience immersive bilingue et conversation AURA

- Date : 2026-09-27
- Statut : accepté
- Périmètre : console privée locale, opérateur unique

## Contexte

L’opérateur demande une refonte de toute l’expérience, une page de garde immersive,
un accès explicite à l’interface, une traduction complète français/anglais et une
conversation avec une assistante nommée AURA. L’immersion doit accompagner les
fonctions réelles : missions, analyses, preuves, validations, runbooks, recherche,
services, opérations et outils. Elle ne doit pas simuler une activité inexistante.

## Décisions

1. Un système visuel partagé en CSS/SVG natifs remplace la précédente couche de
   présentation. Le shell, les panneaux, les états, les transitions, les modèles
   de mission et l’instrument AURA partagent leurs couleurs et composants. Le
   bandeau de la page de garde est décoratif et exclu de l’arbre d’accessibilité.
2. Le centre de missions fournit des brouillons structurés, modifiables avant
   soumission au workflow SRE existant. Il ne crée ni nouvel agent autonome, ni
   action à partir d’une simple navigation. Les paramètres URL ne contiennent que
   l’identifiant public d’un modèle, jamais le contenu de l’alerte.
3. La préparation opérationnelle repose sur le diagnostic réel de l’ADR 0014.
   Les indicateurs et les états de l’interface viennent de l’API. Les commandes
   proposées sont copiables, jamais exécutées par la page de diagnostic.
4. Les chaînes produit utilisent un catalogue explicite et typé français/anglais,
   avec interpolation et formats de dates/nombres adaptés. L’anglais est le
   défaut. Le choix d’interface est mémorisé localement et met à jour `html.lang`.
   Les termes CLI, API, MCP, runbook, workflow et les identifiants techniques
   restent reconnaissables. Les documents, diagnostics et saisies de l’opérateur
   ne sont pas traduits automatiquement. Aucun service de traduction externe
   n’est utilisé. La langue de conversation se choisit séparément.
5. Le chat texte et l’enregistrement avec relecture restent disponibles. Le mode
   conversation mains libres nécessite un clic explicite. Il enchaîne microphone,
   transcription locale, dialogue local, synthèse puis écoute. Le microphone est
   fermé pendant le traitement et la lecture. « Speak now » interrompt la réponse
   avant de rouvrir l’écoute : il ne s’agit pas de duplex intégral ou de détection
   permanente d’un mot d’activation.
6. Une détection d’énergie, indépendante des animations, termine un tour après
   environ 1,6 seconde de silence consécutif à de la parole. Le mode s’arrête sans
   parole détectée après 12 secondes, après 20 échanges, sur erreur, au changement
   d’onglet masqué, à la navigation, avec Échap ou avec le bouton d’arrêt. Chaque
   enregistrement conserve la borne de 90 secondes et 8 Mio. Le seuil fixe peut
   être inadapté à un environnement bruyant : le mode manuel reste le recours.
7. Le microphone est visualisé par un `AnalyserNode` sans connexion aux haut-parleurs.
   La sortie garde la lecture native `HTMLAudioElement`. Un lecteur PCM16 RIFF borné
   analyse le WAV local autour de `currentTime`, sans modifier la restitution.
   Un format non reconnu conserve la lecture et un visuel statique. L’instrument
   représente donc un signal mesuré, pas une animation aléatoire prétendant
   reconnaître la parole. Le chemin SVG est mis à jour au maximum 30 fois par seconde,
   sans `setState` React à chaque image.
8. La préférence système de réduction des animations, la pause manuelle persistante,
   l’invisibilité de l’onglet et la sortie du viewport suspendent les décorations.
   La pause des animations ne désactive pas la transcription ni le dialogue. Les
   pistes, nœuds audio, timers, requêtes et URL Blob ont un nettoyage explicite ;
   les résultats devenus obsolètes sont ignorés avec un compteur de génération.

Le catalogue est partagé via `useSyncExternalStore` ; les changements entre onglets
et les refus d’écriture dans le stockage conservent une sélection cohérente. Le
renderer Markdown est chargé à la demande dans un chunk distinct ; le fallback
reste du texte échappé. Les images distantes restent inertes et aucun HTML brut
n’est exécuté. Cette séparation allège le chargement initial sans exposer les
contenus à un service externe.

La préférence de lecture automatique est relue après les opérations asynchrones.
Son retrait annule la synthèse ou la lecture automatique en cours, sans bloquer une
lecture lancée explicitement. Le mode conversation a son propre bouton d’arrêt.

## Conséquences et limites

La conversation peut demander une initialisation locale longue. L’interface signale
l’attente au-delà de 15 secondes sans inventer un pourcentage de progression. Les
mesures de voix et de dialogue restent propres au poste et à leurs entrées synthétiques.
La transcription peut se tromper. Une validation vocale n’approuve aucune analyse,
ne déclenche aucun outil et n’exécute aucune remediation. Les sept derniers messages
restent en mémoire pour le contexte et sont perdus à la sortie de la page.

La qualification de l’interface inclut les deux langues, les thèmes clair/sombre,
le clavier, la réduction du mouvement, les parcours desktop/mobile Chromium et les
cas d’erreur. Ces contrôles ne constituent ni une garantie de fluidité sur tous les
appareils ni une certification WCAG complète. La frontière d’isolation client reste
une installation dans une VM dédiée, et la qualification de production dépend
notamment de la résolution des vulnérabilités d’images documentées séparément.

## Références

- [ADR 0013 — Voix anglaise locale](0013-voix-anglaise-reactive.md)
- [ADR 0014 — Préparation et outils locaux](0014-readiness-et-outils-locaux.md)
- [MDN — AnalyserNode](https://developer.mozilla.org/en-US/docs/Web/API/AnalyserNode)
- [MDN — Page Visibility API](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)
- [MDN — prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion)
