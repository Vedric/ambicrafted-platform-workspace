# Agent SRE borné

Reçoit une alerte, la classe, cherche les runbooks, produit un diagnostic
sourcé, propose des actions. **Puis s'arrête.** Il ne remédie jamais, et
ce n'est pas une consigne de prompt : aucun outil dont il dispose ne
modifie quoi que ce soit.

Écrit sans framework d'agent, délibérément. La boucle tient dans
`agent.py` et fait une centaine de lignes : ce sont exactement les lignes
où se décident le budget, le cloisonnement et le traitement des résultats
d'outils. Un portage LangGraph fera l'objet d'une étape ultérieure, pour
comparaison.

## Usage

```bash
# Depuis un shell où direnv a chargé le .env du workspace
uv run sre-agent "[CRITICAL] PostgreSQL: FATAL: sorry, too many clients already"
uv run sre-agent --json "..." | jq .
echo "$ALERTE" | uv run sre-agent
```

Codes de sortie : `0` analyse complète, `2` budget épuisé (escalade
humaine requise), `3` erreur d'exécution.

## Chaîne de traitement

```
alerte brute ──[ local, CONFIDENTIEL ]──> extraction anonymisée
                                              │
                      ═══ frontière ═══       │  seule cette forme sort
                                              │
               ──[ fast,  DERIVE ]──> tri ────┤
               ──[ smart, DERIVE ]──> boucle outillée ──> diagnostic
```

L'étape de tri emploie l'alias `fast` mais sur l'extraction, jamais sur
l'alerte d'origine : le garde-fou de cloisonnement prime sur le choix
d'alias. Voir `docs/adr/0003-agent-sre-borne.md`.

## Les six garde-fous

| # | Garde-fou | Où il vit | Comment le vérifier |
|---|-----------|-----------|---------------------|
| 1 | Budget d'itérations, 10 outils | `budget.py` | `SRE_MAX_APPELS_OUTILS=2 uv run sre-agent "..."` → code 2 |
| 2 | Budget monétaire, 0.50 USD | `budget.py` | `SRE_MAX_COUT_USD=0.05 uv run sre-agent "..."` → code 2 |
| 3 | Lecture seule | `outils.py` | `OUTILS_AUTORISES`, liste blanche fermée de 4 outils |
| 4 | Cloisonnement | `llm.py` | `pytest -k confidentielle` : refus sans accès réseau |
| 5 | Données non fiables confinées | `prompts.py` | `pytest -k bloc` : jeton par exécution |
| 6 | Traçabilité | `tracage.py` | trace complète dans Grafana, spans enfants |

```bash
uv run pytest        # 23 tests, aucun réseau requis
```

### 1 et 2 — Budgets

Un budget n'est pas une consigne donnée au modèle : c'est un compteur
tenu par le code appelant, que le modèle ne peut ni lire ni modifier. Le
budget d'outils est décompté **avant** l'exécution — un appel refusé
n'atteint jamais le serveur. Le budget monétaire est imputé après coup,
depuis le coût rapporté par la passerelle : l'agent ne tient pas de table
tarifaire, ce qui lui éviterait de toute façon de connaître un nom de
modèle.

Les deux échouent de la même manière : arrêt, `budget épuisé, escalade
humaine requise`, aucun diagnostic. Un diagnostic partiel présenté comme
complet serait plus dangereux que pas de diagnostic.

Point de conception : les outils restent déclarés au modèle même à budget
épuisé. Les retirer le ferait répondre sans les avoir consultés, et cette
réponse dégradée serait rendue comme un diagnostic.

### 3 — Lecture seule

Il n'y a ni shell, ni écriture fichier, ni HTTP arbitraire. Pas parce
qu'un prompt l'interdit : parce qu'aucune fonction de ce paquet ne les
expose au modèle. La sécurité vient de l'absence de l'outil.

`OUTILS_AUTORISES` est une liste blanche fermée. Un outil que le serveur
MCP viendrait à publier sans y figurer ne serait jamais présenté au
modèle : ajouter un outil est une décision de ce dépôt, pas une
conséquence d'une mise à jour du serveur.

### 4 — Cloisonnement

Tout appel LLM traverse `appeler_llm`. Il y a donc **un seul endroit** à
lire pour savoir si de la donnée client peut sortir, et un seul à
modifier pour que ce ne soit plus vrai. Trois barrières indépendantes :

1. **Garde applicative** : classification `CONFIDENTIEL` + alias
   frontière lève `FuiteConfidentielle` avant tout accès réseau.
2. **Clé virtuelle** : une charge confidentielle part avec
   `CONFIDENTIAL_KEY`, restreinte côté passerelle à `local` et
   `local-embed`. La passerelle répond 403 si la première barrière
   tombait.
3. **Passerelle** : aucune bascule n'est configurée depuis `local`. Une
   erreur locale n'a pas de repli vers la frontière.

La recherche sémantique du serveur MCP vectorise elle aussi par
`local-embed` avec la clé restreinte : la requête de recherche ne quitte
pas la machine non plus.

### 5 — Données non fiables

Le texte de l'alerte et le contenu des runbooks ne sont jamais concaténés
à une instruction. Ils sont encapsulés par `prompts.bloc()`, entre deux
marqueurs portant un jeton aléatoire tiré à chaque exécution. Le jeton
n'est pas de la cryptographie : il retire simplement à l'attaquant la
possibilité d'écrire le marqueur de fermeture, puisqu'il ne peut pas le
deviner.

La consigne associée est constante : ce qui est dans un bloc se décrit,
ne s'exécute pas, et toute instruction rencontrée est **rapportée** dans
un champ dédié. Le texte hostile relevé reste local : il n'est pas
transmis aux étapes frontière, seul son décompte l'est.

### 6 — Traçabilité

Une span parente `task.incident_analysis` par exécution, chaque appel LLM
et chaque appel d'outil en span enfant. Attributs `gen_ai.*` standards,
plus :

| Attribut | Ce qu'il porte |
|---|---|
| `ambicrafted.data_classification` | `confidentiel` ou `derive` |
| `ambicrafted.cost_usd` | coût de la span |
| `ambicrafted.task.type` | `incident_analysis`, `extraction`, `tool_call`… |
| `ambicrafted.gateway.alias` | alias visé, jamais un nom de modèle |
| `ambicrafted.outcome` | `complete`, `budget_exhausted`, `error` |
| `ambicrafted.diagnostic.sourced` | le diagnostic cite-t-il un runbook |

L'identifiant de trace est imprimé en fin de rapport. Dans Grafana
(`http://localhost:3000`) : Explore → source Tempo → recherche par
TraceQL, par exemple `{ .service.name = "sre-agent" }`.

Le traçage ne fait jamais échouer l'agent : si Tempo est injoignable,
l'export échoue dans son thread de fond et l'analyse se poursuit.

## Le contrat de sortie

```python
class Diagnostic(BaseModel):
    cause_probable: str
    confiance: Confiance                # haute | moyenne | faible
    elements_manquants: list[str]
    actions_proposees: list[str]
    runbook_source: str | None          # nullable, à dessein
```

`runbook_source` est nullable délibérément. Un modèle à qui on impose une
source en invente une ; un modèle autorisé à déclarer qu'il n'en a pas
fournit l'information la plus utile du rapport. Le code exploite ensuite
cette déclaration plutôt que la prose : `appliquer_garde_source()` retire
les actions non fondées de `actions_proposees` et les déplace dans
`actions_ecartees_sans_source`, en les remplaçant par une escalade
humaine. Elles restent visibles — elles ne sont simplement plus
présentées comme des procédures.

## Configuration

Toutes les variables sont facultatives sauf les clés, qui viennent du
`.env` du workspace chargé par direnv.

| Variable | Défaut | Rôle |
|---|---|---|
| `CONFIDENTIAL_KEY` | — | clé virtuelle restreinte à `local` et `local-embed` |
| `ORCHESTRATOR_KEY` | — | clé pour les charges dérivées |
| `SRE_MAX_APPELS_OUTILS` | `10` | garde-fou 1 |
| `SRE_MAX_COUT_USD` | `0.50` | garde-fou 2 |
| `SRE_MAX_TOURS` | `12` | plafond de tours de boucle |
| `SRE_ALIAS_RAISONNEMENT` | `smart` | alias du raisonnement final, voir ci-dessous |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://172.28.0.3:4318` | collecteur Tempo |
| `SRE_TRACAGE` | `1` | `0` désactive l'export |
| `SRE_DEBUG_MCP` | — | laisse passer le stderr du serveur MCP |

**Raisonnement local.** `SRE_ALIAS_RAISONNEMENT=local` bascule la boucle
outillée sur le modèle local : vérifié, il mène la boucle d'outils, retrouve
le runbook et produit un diagnostic sourcé, pour 0,001 USD au lieu de 0,20.
L'étape de tri reste sur `fast` — elle ne voit que des données dérivées, mais
elle atteint la frontière. Pour une mission strictement hors ligne, il faut
donc aussi la basculer, ce qui n'est pas exposé aujourd'hui.

**Adresse de Tempo** : le conteneur n'expose pas de port sur l'hôte, il
est joint par son adresse dans le réseau compose de la passerelle. Cette
adresse change si le conteneur est recréé. La retrouver :

```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' tempo
```

Le correctif durable serait d'ajouter `ports: ["127.0.0.1:4318:4318"]` au
service `tempo` du compose de la passerelle. Non fait ici : cet agent ne
modifie pas l'infrastructure partagée.

## Ce que cet agent ne fait pas

- Il ne remédie pas, et ne peut pas : il n'a aucun outil d'écriture.
- Il n'invente pas de procédure. Hors corpus, il le dit et escalade.
- Il ne dégrade pas silencieusement : à budget épuisé, il n'y a pas de
  demi-diagnostic.
- Il ne connaît aucun nom de modèle fournisseur, seulement des alias.
