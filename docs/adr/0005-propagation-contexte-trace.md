# ADR 0005 : propagation du contexte de trace vers la passerelle

Statut : accepté
Date : 2026-08-25
Complète l'ADR 0004, qui constatait deux arbres de spans disjoints par
appel LLM et renvoyait la décision à part, parce qu'elle touche `llm.py`.

## Contexte

Chaque appel LLM produisait deux traces sans lien dans Tempo : la span
`llm.*` de `sre-agent`, et une trace `litellm-gateway` de 8 à 9 spans,
sans aucun `trace_id` commun. Cause : `llm.py` n'envoyait pas d'en-tête
`traceparent`. Les réunir suppose de modifier un garde-fou. Avant de le
faire, il fallait établir que la passerelle exploiterait cet en-tête.

## Mesure préalable : la passerelle extrait-elle un `traceparent` ?

Mesuré, pas lu. Un `curl` vers `/v1/chat/completions` (alias `local`)
avec un en-tête forgé au format W3C :

```
traceparent: 00-54cb2370448e764738e06d8816eb52ff-33cb89ad348d45ce-01
```

puis `GET http://tempo:3200/api/traces/54cb2370448e764738e06d8816eb52ff` :
HTTP 200, 9 spans, toutes de `litellm-gateway`. La span racine
`Received Proxy Server Request` (SERVER) porte comme `parentSpanId`
**`33cb89ad348d45ce`, le span_id forgé**. La passerelle (LiteLLM 1.98.0,
`callbacks: ["otel"]`, configuration inchangée) ne se contente pas de
réutiliser l'identifiant de trace : elle rattache sa span serveur sous
la span cliente qu'on lui désigne. Aucune trace orpheline créée à côté.

Issue (a) : la propagation sert. La corrélation de repli par attribut
partagé (`x-litellm-call-id` existe dans les en-têtes de réponse) n'a
pas été nécessaire.

## Décision

`llm.py` injecte le contexte courant dans les en-têtes de la requête par
`opentelemetry.propagate.inject`, à l'intérieur de la span `llm.*`.

Ce qui ne change pas, et qui est vérifié par test :

- **L'ordre des barrières.** Barrière 1 (`FuiteConfidentielle`), puis
  budget, puis ouverture de la span, puis en-têtes (barrière 2 et
  `traceparent`), puis réseau. Une charge refusée n'a jamais d'en-tête
  construit : un test remplace `inject` et `httpx.post` par des
  assertions et vérifie qu'aucun des deux n'est atteint.
- **La signature de `appeler_llm`.**
- **Le comportement sans span active.** Traçage coupé (`SRE_TRACAGE=0`),
  le propagateur W3C n'écrit rien : les en-têtes sont exactement
  `Authorization` et `Content-Type`, aucune exception. C'est le seul cas
  où la modification aurait pu lever dans un chemin qui ne levait pas ;
  il est verrouillé par un test, pas par une lecture du SDK.
- **Les dépendances.** `opentelemetry.propagate` vient de
  `opentelemetry-api`, déjà tirée par `opentelemetry-sdk` bornée
  `>=1.30,<2`. Aucune bibliothèque ajoutée.

Détail relevé en test : le SDK 1.44 émet les drapeaux `03` (sampled +
random, W3C Trace Context niveau 2) et non `01`. La passerelle rattache
dans les deux cas.

Tests : 37 d'origine inchangés, 6 ajoutés dans
`tests/test_propagation_trace.py`, 43 au total.

## Ce que ça change dans la lecture des traces

Vérification, alerte `PostgreSQL: too many clients already`, une
exécution par implémentation. La requête TraceQL

```
{ resource.service.name = "sre-agent" } && { resource.service.name = "litellm-gateway" }
```

rend exactement une trace par exécution, racine `task.incident_analysis`.

| Trace | spans | `sre-agent` | `litellm-gateway` | appels LLM rattachés |
|---|--:|--:|--:|--:|
| boucle maison `5556f616…` | **52** | 10 | 42 | 5 / 5 |
| graphe `a6cb95ce…` (jusqu'à la porte) | **60** | 18 | 42 | 5 / 5 |
| ADR 0004, graphe, avant propagation | 19 | 19 | 0 | 0 / 5 |

Chaque `Received Proxy Server Request` a pour parent une span `llm.*`
(`llm.extraction`, `llm.classification`, `llm.raisonnement` ×3). Somme
des tokens d'entrée : 11 193 des deux côtés, sur les mêmes cinq appels.

**Écart avec la prédiction.** Le curl de la mesure préalable donnait
9 spans par appel, d'où une prédiction de 19 + 5 × 9 = 64. Mesuré : 60.
Deux causes, aucune n'est un défaut de propagation :

- 42 et non 45 côté passerelle : la span `postgres` n'apparaît que sur
  2 appels sur 5, quand l'authentification de la clé virtuelle n'est
  pas en cache (deux clés, deux ratés de cache). Un appel coûte 8 ou
  9 spans.
- 18 et non 19 côté agent : trois outils appelés au lieu de quatre,
  variance de la génération, pas de la trace.

**Ce qui n'est pas propagé**, et qu'il faut savoir en lisant Tempo :

1. **La vectorisation de la requête de `semantic_search`.** Le serveur
   MCP appelle `/v1/embeddings` (alias `local-embed`) avec son propre
   `httpx`, dans son propre processus, sans OTel. Mesuré sur la boucle
   maison : une trace `litellm-gateway` orpheline de 5 spans et 2,3 s,
   `url.path = /v1/embeddings`, `litellm.model_group = local-embed`,
   entièrement comprise dans la fenêtre de `tool.semantic_search`
   (2,4 s). Ce chemin ne passe pas par `llm.py` : hors périmètre de cet
   ADR, et c'est la raison pour laquelle un `tool.semantic_search`
   restera une feuille dans la trace unifiée.
2. **Les spans `MCP send …` du SDK `mcp` 2.1.0.** Trouvé pendant la
   vérification : le SDK émet ses propres spans (scope
   `mcp-python-sdk`, service `sre-agent`) — `initialize`, `tools/list`,
   un `tools/call` par outil. Elles sont **racines**, une trace
   chacune, parce que le client MCP tourne dans un thread à sa propre
   boucle d'événements (`outils.py`) où le contexte de la span `tool.*`
   n'est pas transporté. Le SDK injecte pourtant un `traceparent` dans
   `_meta` (SEP-414), mais c'est l'identifiant de cette trace orpheline
   qu'il transmet au serveur. Antérieur à cet ADR, invisible tant que
   personne ne cherchait de recoupement. Réunir ce chemin demande deux
   choses hors périmètre : passer le contexte au thread MCP, et
   instrumenter le serveur. À décider séparément.

**Lecture.** Une trace d'alerte est désormais faite à 70–80 % de spans
de passerelle (42 sur 52 ou 60), dont dix `router` et cinq
`batch_write_to_db`. Dans Grafana, replier les nœuds `Received Proxy
Server Request` rend la vue de l'ADR 0003 ; les déplier donne, par
appel, le temps passé en authentification, en routage et chez le
fournisseur. Le calcul d'orchestration de l'ADR 0004 (span parente moins
`llm.*` et `tool.*`) reste valable : les spans de passerelle sont des
descendantes de `llm.*`, déjà comptées.

## Le point ouvert de l'ADR 0004 : les cinq clés `gen_ai.*` partagées

L'unification permet de mesurer le conflit sur **un même appel**, ce
qui était impossible avant. Résultat, sur les cinq appels des deux
exécutions :

| Clé | `sre-agent` (`llm.*`) | `litellm-gateway` (`litellm_request`) | accord |
|---|---|---|---|
| `gen_ai.system` | `anthropic`, `ollama_chat` | idem | oui |
| `gen_ai.response.model` | l'alias | l'alias | oui |
| `gen_ai.usage.input_tokens` | 746, 467, 2598, 3123, 4259 | idem | oui |
| `gen_ai.usage.output_tokens` | 2373, 82, 124, 150, 1068 | idem | oui |
| `gen_ai.request.model` | **l'alias** (`smart`, `fast`, `local`) | **le modèle fournisseur** | **non** |

Le conflit de sens se réduit à une clé, `gen_ai.request.model`. Les
quatre autres portent la même valeur des deux côtés — ce qui crée un
problème différent : la duplication.

**Aggravé pour les agrégats.** Une somme par trace sans filtre de
service compte chaque appel deux fois. Mesuré :

```
{ trace:id = "5556f6169e19ab41f1af9712445fdec9" && span.gen_ai.usage.input_tokens > 0 }
  | sum(span.gen_ai.usage.input_tokens) > 0
→ 22 386 (10 spans)

{ trace:id = "5556f6169e19ab41f1af9712445fdec9" && resource.service.name = "sre-agent"
  && span.gen_ai.usage.input_tokens > 0 } | sum(span.gen_ai.usage.input_tokens) > 0
→ 11 193 (5 spans)
```

Avant l'unification, la même somme sur une trace était juste parce que
la trace n'avait qu'un service. Elle est maintenant fausse d'un facteur
exactement 2 dès qu'on oublie `resource.service.name`. Règle pour tout
tableau de bord : **aucun agrégat `gen_ai.usage.*` ni
`ambicrafted.cost_usd` sans filtre de service.**

**Clarifié pour la résolution.** La relation alias → modèle, qui
n'était lisible nulle part, devient une relation parent-enfant
interrogeable :

```
{ resource.service.name = "sre-agent" && span.gen_ai.request.model = "smart" }
  >> { resource.service.name = "litellm-gateway" && name = "litellm_request" }
  | select(span.gen_ai.request.model, span.gen_ai.response.model)
```

rend, sur la trace unifiée, les trois `litellm_request` descendantes des
`llm.raisonnement`, avec le nom fournisseur que la passerelle a résolu
derrière `smart`. La même requête avec `"local"` rend `coder`. C'est la
règle 1 du CLAUDE.md rendue vérifiable depuis Tempo : le code ne connaît
que l'alias, la passerelle seule connaît le modèle, et la trace montre
la frontière entre les deux.

Verdict : **les deux, et c'est net.** Le sens divergent de
`gen_ai.request.model` devient une information (l'alias d'un côté de la
frontière, sa résolution de l'autre) dès qu'on lit par
`resource.service.name` ; la duplication des quatre autres clés devient
un piège d'agrégation qui n'existait pas. Aucune des deux ne se corrige
sans toucher à la télémétrie de la passerelle ; ce n'est pas fait ici.

## Conséquences

- `llm.py` : +14/−5 lignes, un import, un dict d'en-têtes nommé, un
  appel `inject`. Barrières, signature, dépendances inchangées.
- Trace unifiée : 52 spans (maison) ou 60 (graphe) par alerte au lieu
  de 10 ou 19, plus une trace passerelle par appel avant.
- Les chemins `local-embed` du serveur MCP et les spans du SDK `mcp`
  restent disjoints. Deux candidats pour un ADR ultérieur, à ne pas
  traiter dans `llm.py`.
- Tout agrégat `gen_ai.*` porte un filtre `resource.service.name`.
