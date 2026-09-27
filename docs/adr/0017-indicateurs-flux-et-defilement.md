# ADR 0017 — Indicateurs opérationnels, architecture et défilement

- Date : 2026-09-27
- Statut : accepté
- Périmètre : interface locale privée

## Contexte

L’opérateur souhaite des graphiques lisibles, des KPI pertinents, une architecture
explorable et davantage de mouvement au défilement, sans perdre les garanties de
confidentialité, d’accessibilité ou la précision des données.

## Décisions

Les graphiques utilisent les données de `/api/vue-ensemble` et les sondes de
`/api/sante`. Ils ne produisent ni activité fictive, ni estimation de coût,
de débit LLM ou de disponibilité historique à partir d’un simple instantané.

L’activité décrit les exécutions encore conservées, regroupées par date de
création UTC sur sept ou quatorze jours. Cela inclut les analyses et les opérations
de maintenance : une suppression retire l’exécution de ces agrégats. Les états
restent disjoints, avec une catégorie pour les futurs états inconnus. Une opération
terminée n’est pas assimilée à une approbation humaine ou à un diagnostic correct.

Les durées des sondes HTTP sont présentées en millisecondes, avec leur périmètre
et la date d’actualisation de l’interface. Les échecs restent des échecs, sans barre
de latence réussie. Ce sont des contrôles ponctuels, pas des SLI/SLO de production.
La période sélectionnée ne filtre que l’activité historique ; les états conservés
et la santé actuelle portent leurs propres légendes.

La vue d’architecture explique des chemins conceptuels à travers les composants
réellement documentés. Les mouvements sur ces chemins sont des illustrations ;
ils ne représentent pas des paquets, traces ou agents actifs mesurés. Les composants
sans sonde dédiée restent distincts des services effectivement observés.

Les visualisations utilisent SVG, CSS et les composants React locaux. Le clavier
et une table permettent d’inspecter les valeurs sans dépendre du survol ou des
couleurs. Les messages, unités et noms accessibles suivent le catalogue FR/EN.
Aucune bibliothèque graphique externe ni ressource graphique distante n’est ajoutée.

Les accents au défilement utilisent IntersectionObserver et des animations finies.
Ils ne cachent jamais durablement le contenu et ne modifient pas la mise en page.
Un élément contenant le focus n’est pas animé. Les préférences de réduction du
mouvement, la pause, les onglets masqués et le démontage interrompent les effets.
Le nombre d’éléments observés est borné ; il n’existe pas de boucle de rendu inactive.

Les petits textes sont agrandis et exprimés en unités `rem`. Le menu est élargi
et les dispositions mobiles sont vérifiées avec les mêmes langues et fonctions.

## Validation et limites

Les vérifications couvrent agrégats vides, états inconnus, échecs de sondes,
inspection au clavier, traduction, navigation, nettoyage des animations et
accessibilité automatisée. Playwright contrôle desktop et mobile, y compris les
flux d’architecture et les préférences de mouvement.

Ces graphiques ne remplacent pas Grafana/Prometheus/Tempo pour l’observabilité
historique, ni une validation humaine des diagnostics. Les limites de sécurité
des images et d’isolation entre clients restent celles de la livraison locale.

## Alternatives et conséquences

Une bibliothèque de graphiques ou un moteur de diagrammes complet ajouterait des
dépendances et un coût de chargement pour trois graphiques et une topologie bornée.
Les primitives natives suffisent ici ; une future édition de graphes ou des séries
volumineuses demanderont de réévaluer ce choix. Le code de mise en page, les
légendes et leurs tests restent à maintenir dans la console.

Les agrégats existants évitent une nouvelle collecte de données, mais ne permettent
pas de reconstruire un historique après suppression ni d’établir un SLO. Les
animations consomment temporairement du rendu ; leur réduction et leur interruption
restent nécessaires, et le résultat n’est pas une garantie de FPS universelle.

## Références

- [Architecture déployée](../ARCHITECTURE.md)
- [Console et CLI](../CONSOLE.md)
- [ADR 0015 — Expérience immersive bilingue](0015-experience-immersive-bilingue.md)
