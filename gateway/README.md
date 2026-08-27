# Passerelle : LiteLLM + observabilité

Stack compose de la plateforme : LiteLLM (point d'entrée unique, alias
`smart` / `balanced` / `fast` / `local` / `local-embed`, ADR 0001), son
PostgreSQL, Tempo (traces), Prometheus (métriques), Grafana, Qdrant
(index des runbooks, ADR 0002). Elle vit dans ce dépôt pour être
reconstructible depuis zéro (ADR 0006).

## Versionné / non versionné

Versionné, suffit à recréer la stack :

- `docker-compose.yml` : six services, toutes les images épinglées par digest
- `config.yaml` : alias LiteLLM, repli, callbacks. Aucun secret dedans
  (tout passe par `os.environ/...`)
- `observability/` : `tempo.yaml`, `prometheus.yml`,
  `grafana/datasources/datasources.yaml`
- `.env.example` : la liste des variables attendues, valeurs factices

Jamais versionné (secret ou donnée) :

- `.env` : ignoré par `gateway/.gitignore` et par le `.gitignore` racine.
  Vérifier avant tout `git add` : `git check-ignore -v gateway/.env`
- les volumes Docker `gateway_pgdata`, `gateway_tempodata`,
  `gateway_promdata`, `gateway_grafanadata`, `gateway_qdrantdata`

## Reconstruire depuis zéro sur une machine neuve

### Prérequis

- Docker Engine avec Compose v2 (`docker compose version`)
- Ollama sur l'hôte, joignable depuis les conteneurs à `http://172.17.0.1:11434`
  (adresse du bridge Docker, pas `localhost`), avec les modèles `coder` et
  `nomic-embed-text` chargés (`ollama ls`). Sans lui, `local` et
  `local-embed` répondent en erreur ; les alias frontière fonctionnent.
- Le sous-réseau `172.28.0.0/24` libre (`ip route`), il est fixé dans le
  compose.
- Les ports `4000`, `4318`, `9090`, `3000`, `6333` libres sur `127.0.0.1`.

### 1. Variables

```sh
cd gateway
cp .env.example .env && chmod 600 .env
```

Puis remplacer chaque valeur (toutes celles du modèle sont fausses) :

| Variable | Rôle |
|---|---|
| `LITELLM_MASTER_KEY` | clé maître LiteLLM, préfixe `sk-` |
| `POSTGRES_PASSWORD` | mot de passe de la base LiteLLM |
| `DATABASE_URL` | même mot de passe, hôte `postgres` (nom du service) |
| `ANTHROPIC_API_KEY` | alias `smart` / `balanced` / `fast` |
| `GRAFANA_ADMIN_PASSWORD` | compte `admin` de Grafana |
| `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_SERVICE_NAME` | export des traces de LiteLLM vers Tempo |

Contrôle sans démarrer quoi que ce soit :

```sh
docker compose config --quiet && echo OK
```

### 2. Démarrage

Un seul ordre suffit, compose gère l'enchaînement :

```sh
docker compose up -d
```

Ce qui se passe, dans l'ordre : `postgres` démarre et doit passer
`healthy` (`pg_isready`) avant que `litellm` ne soit lancé ; au premier
démarrage LiteLLM crée son schéma dans la base (quelques dizaines de
secondes, `docker compose logs -f litellm`). `tempo`, `prometheus`,
`grafana`, `qdrant` démarrent en parallèle : Tempo écrit ses métriques
dans Prometheus par remote write (il réessaie tant que Prometheus n'est
pas prêt), Grafana provisionne ses deux sources de données au démarrage.

Le premier lancement télécharge les images par digest : c'est
exactement ce qui tourne sur la machine d'origine, pas « la dernière
version ».

### 3. Vérifier que ça marche

Dans l'ordre, chaque étape suppose la précédente :

```sh
docker compose ps                     # 6 services Up, postgres et qdrant (healthy)
curl -s localhost:4000/health/liveliness          # "I'm alive!"
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" localhost:4000/v1/models
                                      # les 5 alias, aucun nom de modèle fournisseur
curl -s localhost:9090/-/ready        # Prometheus Server is Ready.
curl -s localhost:3000/api/health     # "database": "ok"
curl -s localhost:6333/healthz        # healthz check passed
```

Puis un appel de bout en bout sur l'alias local (ne sort pas de la machine) :

```sh
curl -s localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"model":"local","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
```

Enfin, dans Grafana (`admin` / `GRAFANA_ADMIN_PASSWORD`), Explore →
Tempo : la trace `litellm-gateway` de l'appel précédent doit apparaître.
C'est la preuve que LiteLLM, Tempo et Grafana se parlent.

### 4. Ce que le dépôt ne reconstruit PAS

Ces éléments vivent dans les volumes ou hors de la stack ; ils sont à
recréer à la main après un démarrage à vide :

- **Les clés virtuelles LiteLLM** (base PostgreSQL). Au minimum
  `confidential-only`, restreinte à `local` et `local-embed` (règle 2 du
  CLAUDE.md), et la clé large des charges orchestrées. Via l'UI
  (`http://localhost:4000/ui`) ou :

  ```sh
  curl -s localhost:4000/key/generate \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
    -d '{"key_alias":"confidential-only","models":["local","local-embed"]}'
  ```

  Les valeurs obtenues vont dans le `.env` du workspace
  (`CONFIDENTIAL_KEY`, `ORCHESTRATOR_KEY`), jamais dans le dépôt.
  Vérifier le cloisonnement par le test négatif de l'ADR 0001 : un appel
  à `smart` avec `confidential-only` doit être refusé.
- **L'historique de dépense** (même base) : perdu, non reconstructible.
- **L'index Qdrant des runbooks** : `uv run --directory
  mcp-servers/runbooks indexer.py` le recrée depuis `runbooks/` (ADR 0002).
- **Traces et métriques** passées : perdues, ce sont des données d'exploitation.
- **Les modèles Ollama** : hors compose, à charger sur l'hôte.

## Épinglage des images (règle 7)

Chaque image est épinglée par le digest de **ce qui tournait**, relevé
sur le conteneur en service, pas sur ce que le registre propose sous un
nom voisin :

```sh
docker image inspect "$(docker inspect litellm --format '{{.Image}}')" --format '{{.RepoDigests}}'
```

Le commentaire au-dessus de chaque `image:` donne la version et la date
du relevé. Pour mettre à jour : tirer la nouvelle image, la tester, puis
relever son digest de la même façon. Ne jamais revenir à un tag
(`main-stable`, `16-alpine`, `latest`) : ils changent de contenu sans
changer de nom.

## Ce que `docker compose config` ne prouve pas

`docker compose config` est le test de reconstructibilité minimal : il
valide la syntaxe du compose, l'interpolation des variables du `.env`,
et l'existence des fichiers montés (`config.yaml`, `observability/*`).
Il **ne prouve pas** :

- que les images sont tirables (le registre peut avoir retiré un digest) ;
- que les services démarrent : `config.yaml` peut être syntaxiquement
  correct et refusé par LiteLLM, un secret peut être faux ;
- que les services se parlent : résolution des noms de service, remote
  write Tempo → Prometheus, sources de données Grafana, Ollama joignable
  depuis le conteneur ;
- que les volumes se recréent et se remplissent correctement (schéma
  LiteLLM créé, base saine) ;
- que les données non versionnées (clés virtuelles, index Qdrant) sont
  en place.

Seule la section « Vérifier que ça marche », exécutée sur une machine
neuve, prouve cela. Ce dépôt garantit qu'on *peut* la dérouler, pas
qu'elle a été déroulée.

## Rotation des secrets

Changer une valeur dans `.env` ne suffit pas toujours : deux services ne
lisent leur variable qu'à la **première initialisation** de leur volume
et la gardent ensuite dans leur propre base. Procédure appliquée le
2026-08-27 (rotation complète après exposition des valeurs dans une
session d'agent, ADR 0007), dans cet ordre :

| Secret | Où il vit réellement | Comment le changer |
|---|---|---|
| `LITELLM_MASTER_KEY` | `.env` seulement | remplacer, puis `docker compose up -d` |
| `GRAFANA_ADMIN_PASSWORD` | base Grafana (volume `grafanadata`), lue à la 1re init seulement | remplacer dans `.env` **et** l'appliquer : `docker compose exec -T grafana grafana cli --homepath /usr/share/grafana admin reset-admin-password "$GRAFANA_ADMIN_PASSWORD"` |
| `POSTGRES_PASSWORD` | catalogue PostgreSQL (volume `pgdata`), lu à la 1re init seulement | 1) `ALTER USER litellm WITH PASSWORD '…';` passé **sur stdin** de `docker compose exec -T postgres psql -U litellm -d litellm -q` ; 2) remplacer `POSTGRES_PASSWORD` **et** le mot de passe en clair dans `DATABASE_URL` (compose n'interpole pas un `${VAR}` à l'intérieur d'une valeur du `.env`) ; 3) `docker compose up -d` |
| `ANTHROPIC_API_KEY` | console Anthropic | révoquer et recréer côté console, remplacer, `docker compose up -d` |

Méthode (retour d'expérience de l'ADR 0007 : trois clés Anthropic créées
et révoquées en une heure ont laissé une clé morte dans `.env`, et le
diagnostic a coûté plus que la rotation) :

- **une rotation à la fois**, vérifiée **bout en bout** avant la
  suivante : `.env` mis à jour, `docker compose up -d`, puis un appel
  réel qui exerce ce secret (clé Anthropic : une complétion sur `fast` ;
  master key : `/v1/models` ; Postgres : `/health/readiness` →
  `"db": "connected"`). Longueur et préfixe prouvent que la valeur a
  changé, pas qu'elle est valide ;
- révoquer l'ancienne valeur **après** ce succès, jamais en même temps
  que la création de la nouvelle ;
- en cas d'échec, une seule nouvelle tentative, même protocole.

Pièges rencontrés :

- `docker compose restart` ne relit pas `env_file`. Seul `up -d`
  recrée le conteneur avec le nouvel environnement.
- Tester le mot de passe PostgreSQL en loopback **dans** le conteneur
  ne prouve rien : le `pg_hba.conf` de l'image officielle met `127.0.0.1`
  en `trust`, tout mot de passe passe. Tester depuis le réseau compose
  (règle `scram-sha-256`) :
  `docker compose run --rm --no-deps -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres psql -h postgres -U litellm -d litellm -c 'select 1'`.
  La preuve finale reste `litellm` recréé et `/health/readiness` →
  `"db": "connected"`.
- Les clés virtuelles (`CONFIDENTIAL_KEY`, `ORCHESTRATOR_KEY` du `.env`
  du workspace) sont hachées en base : la rotation de la master key ne
  les invalide pas. Vérifier : `/v1/models` avec chacune doit rester 200.
- Consommateurs de la master key hors de ce dossier : **aucun**
  (recensé le 2026-08-27). Le harnais promptfoo (`evals/`) utilisait
  un `export OPENAI_API_KEY=…` interactif ; il prend désormais la clé
  virtuelle `ORCHESTRATOR_KEY` via `apiKeyEnvar` (`evals/README.md`).
  Une rotation de la master key n'a donc rien à propager ; une
  rotation d'`ORCHESTRATOR_KEY` se fait dans le `.env` du workspace.

Vérifier une valeur sans l'exposer : longueur et préfixe, jamais la
valeur (règle 8 du CLAUDE.md) :

```sh
v=$(sed -nE 's/^LITELLM_MASTER_KEY=//p' .env); echo "len=${#v} prefix=${v:0:12}"
```

La dette transitoire du déplacement (ADR 0006 : lien symbolique
`~/platform/gateway`, conteneurs à recréer) a été soldée le 2026-08-27
par ce même `up -d` ; le lien est supprimé.
