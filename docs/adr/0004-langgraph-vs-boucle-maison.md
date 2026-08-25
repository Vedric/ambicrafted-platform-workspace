# ADR 0004 : LangGraph face à la boucle maison

Statut : accepté — les deux implémentations coexistent, `agent.py` reste
la référence, `graphe.py` devient la voie recommandée pour l'astreinte
Date : 2026-08-25
Complète l'ADR 0003, qui annonçait ce portage comme étape ultérieure.

## Contexte

L'ADR 0003 posait qu'un framework d'agent ne devait pas se voir confier
les garde-fous, et gardait la comparaison pour plus tard. Elle est faite.

Le portage a été conduit sous une contrainte unique : `llm.py`,
`outils.py`, `prompts.py`, `budget.py`, `tracage.py` sont importés tels
quels par `graphe.py`, sans une ligne modifiée. Même cloisonnement, même
liste blanche, même confinement à jeton, mêmes budgets. Ce qui diffère
est l'orchestration, et rien d'autre — condition sans laquelle les
chiffres ci-dessous ne mesureraient qu'une réécriture.

Vérification : les 23 tests de garde-fous de l'ADR 0003 passent sans
modification, et 14 tests supplémentaires rejouent les mêmes propriétés
à travers le graphe.

## Mesures

Alerte identique pour toutes les exécutions : `PostgreSQL: too many
clients already`, corpus de deux runbooks, modèle local préchargé,
passerelle et Qdrant chauds. Trois exécutions par implémentation.

### Code

|                                             | maison | graphe |
|---------------------------------------------|-------:|-------:|
| Lignes totales (orchestration + CLI)         |    406 |    966 |
| Lignes de code (hors vide, commentaire, docstring) | 266 | 576 |
| dont orchestration seule                     |    167 |    452 |
| Garde-fous partagés, non réécrits            |  1 151 |  1 151 |

Le graphe fait 2,7 fois le volume de code de la boucle. La répartition
compte plus que le total :

| Poste dans `graphe.py`                          | ~lignes | Nature |
|-------------------------------------------------|--------:|--------|
| État typé, reducers, rejeu du budget             |      85 | prix de la sérialisabilité |
| Contexte de span et session d'outils portés par le processus | 25 | prix du franchissement de processus |
| Décorateur de nœud (span, erreurs mises en état) |      50 | factorisation de ce qui est en ligne dans `analyser()` |
| Les sept nœuds                                   |     210 | équivalent de `_extraire`/`_trier`/`_raisonner` |
| Arêtes conditionnelles                           |      60 | **capacité nouvelle** |
| Assemblage, checkpointer, liste blanche de désérialisation | 80 | **capacité nouvelle** |
| Trois points d'entrée au lieu d'un               |     155 | **capacité nouvelle** |

Environ 220 lignes financent des capacités que la boucle n'a pas, et
110 lignes sont le prix d'entrée du framework — la sérialisabilité de
l'état et la perte du contexte de processus.

### Dépendances

|                                    | maison | graphe |
|------------------------------------|-------:|-------:|
| Dépendances déclarées               |      5 |    5+2 |
| Paquets réellement installés en plus |     0 |     23 |

Deux déclarations, `langgraph>=1.2,<2` et
`langgraph-checkpoint-sqlite>=3.1,<4`, tirent vingt-trois paquets.
Elles sont isolées dans l'extra `[project.optional-dependencies] graphe`,
de sorte que `uv sync` sans extra rend exactement la version de l'ADR
0003.

Deux de ces paquets méritent d'être nommés, parce qu'ils contredisent une
consigne du projet et qu'aucune version de LangGraph ne permet de les
éviter :

- **`langchain-core`** est une dépendance dure de `langgraph`. Aucune de
  ses abstractions n'est utilisée ici : pas de `ChatModel`, pas de `tool`,
  pas de chaîne. Nos appels passent par `llm.appeler_llm`, nos outils par
  `outils.executer_outil`. Le paquet est présent, il n'est pas employé.
- **`langsmith`** est une dépendance dure de `langchain-core`. Il n'est
  pas adopté : le traçage reste OpenTelemetry vers Tempo, et
  `LANGSMITH_TRACING=false` est posé explicitement. Sans clé d'API il est
  inerte, mais c'est une dépendance qui, par défaut, cherche à exporter
  de la télémétrie hors de la machine. À surveiller à chaque montée de
  version.

### Temps, sur la même alerte

|                     | maison 1 | maison 2 | maison 3 | moyenne |
|---------------------|---------:|---------:|---------:|--------:|
| Total               |  58,15 s |  62,66 s |  62,00 s | 60,94 s |
| dont appels LLM     |  55,73 s |  60,20 s |  59,64 s | 58,52 s |
| dont outils MCP     |   0,14 s |   0,18 s |   0,04 s |  0,12 s |
| **dont orchestration** | **1,50 s** | **1,51 s** | **1,44 s** | **1,48 s** |

|                     | graphe 1 | graphe 2 | graphe 3 | moyenne |
|---------------------|---------:|---------:|---------:|--------:|
| Jusqu'à la porte    |  60,86 s |  69,54 s |  70,11 s | 66,84 s |
| Reprise après approbation | 1,28 s | 1,37 s | 1,54 s |  1,40 s |
| Total               |  62,14 s |  70,91 s |  71,65 s | 68,23 s |
| dont appels LLM     |  58,09 s |  66,72 s |  66,94 s | 63,92 s |
| dont outils MCP     |   0,13 s |   0,12 s |   0,13 s |  0,13 s |
| **dont orchestration** | **1,46 s** | **1,43 s** | **1,70 s** | **1,53 s** |

La lecture naïve — « le graphe est 12 % plus lent » — est fausse. Les
durées d'orchestration, obtenues en retranchant à la span parente la
somme des spans `llm.*` et `tool.*`, sont **1,48 s contre 1,53 s**, soit
**50 ms de surcoût**, écritures de checkpoint comprises (onze par
alerte). L'écart de sept secondes sur le total est de la variance de
génération : les deux implémentations émettent le même nombre d'appels
LLM (5) sur la même alerte, et l'étendue des durées LLM se recouvre.

Le seul surcoût déterministe est à l'import :

| Import                    | médiane |
|---------------------------|--------:|
| Python nu                 |   13 ms |
| `+ sre_agent.agent`       |  767 ms |
| `+ sre_agent.graphe`      | 1 079 ms |

**Coût total du framework : environ 360 ms par alerte** (312 ms d'import,
50 ms d'orchestration) sur une tâche qui en prend 60 000. Soit 0,6 %.

### Argent

|                | run 1 | run 2 | run 3 | moyenne |
|----------------|------:|------:|------:|--------:|
| maison         | 0,2560 | 0,2722 | 0,2123 | 0,2468 USD |
| graphe         | 0,2494 | 0,2657 | 0,2520 | 0,2557 USD |
| graphe, reprise | 0,0000 | 0,0000 | 0,0000 | 0,0000 USD |

Les étendues se chevauchent largement (maison 0,212–0,272 ; graphe
0,249–0,266). **Le portage ne coûte rien en argent** : mêmes prompts,
mêmes alias, même nombre d'appels. La reprise après approbation coûte
exactement zéro, ce qui est le point : l'attente humaine ne rejoue rien.

### État persistant

|                              | maison | graphe |
|------------------------------|-------:|-------:|
| Checkpoints par alerte        |      0 |     11 |
| Volume sur disque par alerte  |      0 | ~110 Kio |

## Ce que chacune sait faire que l'autre ne sait pas

### La boucle maison seule

- **Démarrer sans état sur disque.** Aucun fichier persistant, donc
  aucune surface de désérialisation, aucune donnée dérivée d'alerte qui
  survit au processus, aucune rétention à gérer.
- **Se lire d'un trait.** Le flot est une suite d'instructions dans un
  seul fichier de 167 lignes de code. Le graphe demande de lire les
  nœuds, puis les arêtes, puis l'assemblage, pour reconstituer le même
  flot.
- **N'ajouter aucune dépendance non employée** — ni `langchain-core`, ni
  `langsmith`.
- **Démarrer en 767 ms** au lieu de 1 079.

### Le graphe seul

- **Se mettre en pause durablement avant de livrer.** `porte_humaine`
  appelle `interrupt()`, l'état complet est écrit dans SQLite, le
  processus rend la main. Démontré : le processus a été tué en SIGKILL
  pendant la pause ; un processus neuf, avec le même `thread_id` et
  `Command(resume="oui")`, a livré le diagnostic en 1,28 s pour 0 USD,
  budget et historique d'outils intacts. La boucle maison ne sait pas
  faire cela, et ne peut pas apprendre à le faire sans se réécrire
  autour d'un état sérialisable — c'est-à-dire sans devenir un graphe.
- **Reprendre au milieu, pas seulement à la porte.** Les onze
  checkpoints couvrent chaque super-pas. Une coupure pendant le
  raisonnement se reprend au dernier nœud franchi, sans rejouer les
  appels déjà payés.
- **Faire du chemin d'exécution une donnée.** `journal` dans l'état,
  `ambicrafted.graph.path` sur la span parente. En post-mortem on lit
  `extraction → classification → raisonnement → recherche_runbooks →
  raisonnement → abandon` sans relire de code ni recouper des logs.
- **Rendre les décisions de budget testables sans exécuter.** Les
  arêtes sont des fonctions pures de l'état. `apres_raisonnement({...})`
  se teste en une ligne ; l'équivalent maison est un `if` au milieu
  d'une boucle qui ne s'atteint qu'en déroulant tout ce qui précède.
- **Rendre la relance de finalisation observable.** Elle est un
  franchissement d'arête `diagnostic → raisonnement`, visible dans la
  trace et le journal, au lieu d'un `except` invisible du dehors.

## Décisions

### Checkpointer SQLite, pas Postgres

Un fichier local, `~/.local/state/sre-agent/graphe.sqlite`, en 0600
dans un dossier en 0700.

Postgres était disponible : la passerelle en a un. Il a été écarté.
Faire dépendre la reprise d'un agent d'astreinte de la base qui tient la
comptabilité de la passerelle crée un couplage entre deux préoccupations
sans rapport — un agent qui ne peut plus reprendre parce que la
facturation est en maintenance. L'agent est par ailleurs mono-machine :
un `thread_id` est repris sur la machine qui l'a créé.

Les permissions ne sont pas de la coquetterie : le checkpoint contient
l'`Extraction`, donc de la donnée dérivée d'une alerte client, et il
survit au processus. Un état persistant lisible par tout le système
annulerait une partie du bénéfice du cloisonnement de l'ADR 0003.

**Voie d'évolution vers Postgres.** Trois conditions, à remplir toutes :

1. Plusieurs exécutants — un ordonnanceur, ou des reprises depuis une
   machine autre que celle qui a démarré l'analyse. Tant qu'un
   `thread_id` reste attaché à sa machine, SQLite suffit.
2. Une rétention à tenir : les checkpoints contiennent de la donnée
   dérivée, donc une politique de purge. Un fichier local se purge par
   `rm` ; une base partagée demande une décision écrite.
3. Une instance distincte de `litellm-db`. Le couplage refusé ici ne
   doit pas être réintroduit par la porte de service.

Le changement se réduirait alors à `PostgresSaver` en lieu et place de
`SqliteSaver` dans `compiler()`, plus la migration du fichier. Le reste
de `graphe.py` est indifférent au support. C'est le seul endroit du
module qui connaît SQLite.

### Une liste blanche de désérialisation, ajoutée

Le portage introduit une frontière de confiance que la boucle n'avait
pas : un fichier persistant que le graphe relit et désérialise. Par
défaut LangGraph y accepte n'importe quel type Python, ce que sa propre
documentation signale comme un vecteur d'exécution de code pour qui sait
écrire dans ce fichier — et il émet un avertissement annonçant le blocage
dans une version future.

`TYPES_PERSISTABLES` referme cela avec la même figure que
`OUTILS_AUTORISES` : quatre types nommés, `pickle_fallback=False`, liste
tenue par ce dépôt. Ce n'est pas la modification d'un garde-fou
existant, c'est un garde-fou de plus, rendu nécessaire par le framework
et à porter à son passif.

### Deux différences de comportement, assumées, toutes deux plus strictes

1. **Le budget d'outils est opposé par l'arête, donc avant le nœud.**
   Une salve de trois outils demandée quand il n'en reste que deux est
   refusée en bloc ; la boucle maison en aurait exécuté deux avant de
   lever. Vérifié en exécution : `SRE_MAX_APPELS_OUTILS=2` route vers
   `abandon`, code 2, aucune exception remontée, aucun outil de la salve
   refusée n'atteint le serveur. `executer_outil` reste en place et fait
   foi si l'arête laissait passer.
2. **La relance de finalisation est une arête.** Même unicité — un seul
   passage, `relance_tentee` en fait foi — mais elle devient observable.

### Le nœud `abandon` attribue le motif

Défaut trouvé pendant la démonstration et corrigé : le nœud annonçait le
plafond de tours quel que soit le plafond réellement atteint, parce que
l'arête qui route ne dit pas pourquoi elle route. `_motif_abandon()`
rejoue les conditions et nomme le bon plafond. « Plafond d'outils » et
« plafond de tours » appellent des corrections opposées, et personne
n'ira relire le graphe à 3 h du matin pour trancher.

C'est un coût du modèle déclaratif : séparer la décision de son
explication crée un endroit où les deux peuvent diverger.

## Traçage : ce qui a été vérifié, et ce qui a été trouvé

La crainte était que LangGraph introduise une génération concurrente
d'attributs `gen_ai.*` à côté de celle de `tracage.py`. Vérification
faite sur les spans réellement stockées dans Tempo, et non sur la
documentation.

**LangGraph n'émet rien.** Aucune dépendance OpenTelemetry dans
`langgraph`, `langchain-core` ni `langgraph-checkpoint`. Aucune span
portant `langgraph`, `langchain` ou `chain` dans Tempo. Deux services
seulement y écrivent : `sre-agent` et `litellm-gateway`. Le portage
n'ajoute pas une ligne de télémétrie non voulue.

**La coexistence de générations existe, mais elle est antérieure au
portage** et vient de la passerelle :

| Émetteur | Attributs |
|---|---|
| `sre-agent` (`llm.py`) | `gen_ai.operation.name`, `gen_ai.request.max_tokens`, `gen_ai.request.temperature`, `gen_ai.response.finish_reasons`, `gen_ai.response.tool_calls` |
| `litellm-gateway` | `gen_ai.cost.*` (11 attributs, dans aucune version de la sémantique OTel), `gen_ai.usage.total_tokens`, `gen_ai.response.id`, `gen_ai.openai.response.service_tier`, `litellm.*`, `llm.is_streaming`, `call_type`, `model_id` |
| **les deux, avec des sens différents** | `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.system`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |

Le conflit est sur les cinq clés partagées. Notre `gen_ai.request.model`
porte **l'alias** (`smart`, `local`) ; celui de la passerelle porte **le
modèle résolu** (`nomic-embed-text`, avec `litellm.provider.model` à
`ollama/nomic-embed-text`). Une requête Grafana sur
`gen_ai.request.model` rend donc un mélange d'alias et de noms
fournisseur selon le service touché.

Deux conséquences, hors périmètre de cet ADR mais à traiter :

- La règle 1 du CLAUDE.md — aucun nom de modèle fournisseur dans le code
  — est respectée par notre code, mais les noms fournisseur arrivent
  dans Tempo par la télémétrie propre de la passerelle. Un tableau de
  bord doit filtrer sur `resource.service.name` s'il veut raisonner en
  alias.
- Les deux arbres sont **disjoints** : aucun recoupement de `trace_id`
  entre nos traces et celles de `litellm-gateway`, faute de propagation
  d'un en-tête `traceparent` par `llm.py`. Un appel LLM produit donc deux
  traces sans lien. Les réunir demanderait d'injecter le contexte dans
  les en-têtes HTTP — modification de `llm.py`, donc d'un garde-fou :
  hors périmètre de ce portage, à décider séparément.

### La trace survit-elle à la mort du processus ?

Non, et il ne faut pas prétendre le contraire : une span parente meurt
avec son processus. Le graphe ouvre donc une nouvelle trace à la reprise
et la relie explicitement à l'ancienne, par un `Link` OTel et par
`ambicrafted.resume.of_trace_id`. Vérifié : la trace de reprise
(2 spans, 103 ms) porte un lien vers la trace d'avant le SIGKILL
(19 spans, 58,3 s), ainsi que le chemin complet des neuf nœuds relu
depuis le checkpoint. Grafana affiche les deux moitiés d'une même
histoire.

Structure obtenue, conforme à l'ADR 0003 : une span parente
`task.incident_analysis`, chaque nœud en span enfant `node.*`, chaque
appel LLM et chaque outil en petit-enfant `llm.*` / `tool.*`.

## Recommandation

**Prendre le graphe quand un humain doit valider avant que l'agent ne
livre, ou quand l'exécution doit survivre au processus.** C'est le seul
critère qui tranche. Une porte d'approbation durable ne s'ajoute pas à
une boucle : elle suppose un état sérialisable et un point de reprise,
c'est-à-dire un graphe. Pour 360 ms et 23 paquets, on obtient une pause
que ni un redémarrage, ni un déploiement, ni un `kill -9` n'efface. Sur
un agent d'astreinte dont la sortie sera exécutée par quelqu'un de
fatigué, c'est le garde-fou qui manquait à l'ADR 0003 : tous les autres
encadrent ce que l'agent fait, celui-là encadre ce qu'il obtient le
droit de rendre.

**Prendre la boucle maison quand l'agent est appelé par une machine,
dans un flot qui ne s'interrompt pas** — un enrichissement d'alerte, un
tri automatique, un traitement par lots. Il n'y a alors personne pour
franchir la porte, la persistance ne sert à rien, et les 23 paquets et
le fichier d'état sont du passif net : deux dépendances non employées de
plus, une surface de désérialisation de plus, une rétention à tenir.

**Ne pas prendre un framework pour l'orchestration.** C'est le résultat
le plus net de la mesure : le gain d'orchestration est nul — 50 ms — et
le coût en lecture est réel : 452 lignes de code contre 167 pour le même
flot. Un graphe de sept nœuds ne se lit pas plus vite qu'une boucle de
cent lignes, il se lit moins vite, en trois endroits au lieu d'un. Ce
qu'on achète, ce n'est pas la clarté du flot, c'est la durabilité de
l'état.

**Ne jamais lui confier les garde-fous.** Le portage a tenu la
contrainte, et c'est ce qui rend ces chiffres lisibles : cloisonnement,
liste blanche, confinement à jeton, budgets et garde de source ont
traversé sans une ligne modifiée. Vérifié dans le graphe, sur machine
débranchée : une charge confidentielle dirigée vers `smart` lève
`FuiteConfidentielle`, aucun appel réseau n'est tenté, le coût engagé
est nul et le message est identique à celui de la boucle maison. La
seule chose que le framework a exigée est un garde-fou de plus — la
liste blanche de désérialisation — pour refermer une surface qu'il
avait lui-même ouverte. C'est le bon sens de la répartition : le
framework tient l'état, ce dépôt tient les règles.

## Conséquences

Vérifié en exécution :
- Alerte PostgreSQL : arrêt sur `interrupt()`, code 10, diagnostic sourcé
  sur `incident-p1-database.md`, 3 à 4 outils, ~0,25 USD.
- SIGKILL pendant la pause : aucune ligne écrite après, reprise par un
  processus neuf en 1,28 s pour 0 USD, contexte intact.
- `SRE_MAX_APPELS_OUTILS=2` : route vers `abandon`, code 2, motif exact,
  aucune exception, aucun diagnostic partiel.
- Cloisonnement détourné : `FuiteConfidentielle`, zéro appel réseau, zéro
  coût, comportement identique à la boucle maison.
- Trace : 1 span parente, 9 spans de nœud, 19 spans au total ; trace de
  reprise liée à la précédente.
- 37 tests sans réseau : les 23 d'origine inchangés, 14 nouveaux.

Coûts et limites acceptés :
- 23 paquets, dont `langchain-core` et `langsmith`, présents et non
  employés. À réexaminer à chaque montée de version majeure de
  `langgraph`, bornée à `>=1.2,<2`.
- Rétention des checkpoints : `sre-agent-graph --purger --avant N` supprime
  les fils sans activité depuis N jours (défaut 14, la rétention Tempo de
  336 h : un fil et sa trace expirent ensemble) puis VACUUM et troncature
  du WAL. Lancement manuel ou cron ; rien ne le déclenche automatiquement.
- Deux implémentations à maintenir. `graphe.py` importe d'`agent.py` ses
  plafonds de tokens et deux fonctions de décodage : la divergence de
  réglage est empêchée par construction, pas par discipline.
- Le motif d'abandon est reconstitué par le nœud à partir de l'état, et
  non transmis par l'arête qui a décidé. C'est un endroit où décision et
  explication peuvent diverger ; un test verrouille l'attribution.

## Alternatives écartées

- **Réécrire la boucle maison pour y ajouter une pause.** C'est écrire un
  checkpointer, un format d'état sérialisable et une reprise — soit un
  graphe, en moins relu. Le framework se justifie précisément là.
- **`interrupt_before` sur un nœud plutôt qu'`interrupt()` dans le
  nœud.** L'interruption serait décidée à la compilation et non par le
  code du nœud, ce qui interdirait de composer la demande d'approbation
  à partir du diagnostic. Un humain qui approuve doit voir ce qu'il
  approuve.
- **Le checkpointer en mémoire pour la démonstration.** Il aurait rendu
  la démonstration fausse : c'est la survie au `kill -9` qui est le
  sujet.
- **Adopter LangSmith, présent de toute façon.** La télémétrie part hors
  de la machine ; Tempo est local et déjà en service. La règle 2 du
  CLAUDE.md ne distingue pas la donnée de la métadonnée de la donnée.
