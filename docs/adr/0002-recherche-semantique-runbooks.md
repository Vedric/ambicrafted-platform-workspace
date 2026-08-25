# ADR 0002 : recherche sémantique sur les runbooks (Qdrant + MCP)

Statut : accepté, en service local depuis le 25/08/2026
Date : 2026-08-25

## Contexte
Le serveur MCP runbooks n'offrait qu'une recherche par expression
régulière, ligne à ligne. Elle est imbattable sur un terme exact
(code d'erreur, nom de service) mais muette dès que la question
reformule : en incident, on tape ce qu'on observe
(« le service redémarre en boucle »), pas le vocabulaire du runbook
(« crash-loop »). Un opérateur sous pression ne devine pas le mot-clé.

## Décision

### Stockage
Qdrant ajouté à la stack de la passerelle, image épinglée
`qdrant/qdrant:v1.19.0`, port 6333 publié sur 127.0.0.1 uniquement,
volume nommé `qdrantdata`. Collection `runbooks`, 768 dimensions,
distance cosinus.

### Découpage : par section markdown, jamais par nombre de caractères
C'est la décision structurante. Un découpage à taille fixe coupe au
milieu d'une procédure numérotée et restitue « 2. daemon-reload,
reset-failed, restart » sans l'étape 1. En incident, un fragment de
procédure est plus dangereux qu'une absence de résultat : il paraît
complet. Le découpage suit donc la hiérarchie des titres, une section
par fragment. Les titres situés dans un bloc de code clôturé sont
ignorés (un commentaire shell n'est pas un titre).

### Préfixe de chemin de titres
Chaque fragment porte son chemin complet, par exemple
`# Service systemd en crash-loop > ## Diagnostic`. C'est le gain le
plus rentable du pipeline : sans lui, un fragment « ## Diagnostic »
est indistinguable entre le runbook systemd et le runbook PostgreSQL,
à la vectorisation comme à la restitution.

### Embeddings
Exclusivement via la passerelle (`/v1/embeddings`, alias `local-embed`),
jamais en direct vers Ollama : sinon le routage, le suivi et le
cloisonnement de l'ADR 0001 sont contournés. La clé utilisée est
`CONFIDENTIAL_KEY` (clé virtuelle `confidential-only`), pas la clé
maître — moindre privilège, et cohérence avec la règle 2.
Les préfixes de tâche de nomic-embed-text sont appliqués
(`search_document:` à l'indexation, `search_query:` à la requête) :
le modèle est entraîné pour une recherche asymétrique, les omettre
dégrade le rappel sur reformulation.

### Idempotence
Collection recréée à chaque exécution, et identifiants de points
déterministes (UUIDv5 sur `fichier:ligne:chemin_titres`). La recréation
élimine les fragments orphelins d'une section supprimée ou renommée,
que de simples upserts laisseraient en place ; les identifiants stables
rendent deux exécutions comparables.

### Exposition
`semantic_search(requete, k)` ajouté **à côté** de `search_runbooks`,
qui est conservé tel quel. Les deux sont complémentaires et la
description de l'outil le dit explicitement au modèle. La régression
serait de remplacer un outil exact par un outil approximatif.

### Dégradation
Si Qdrant, la passerelle ou la dépendance manquent, `semantic_search`
retourne un message qui nomme la cause, donne la commande de
correction et renvoie vers `search_runbooks`. Il ne lève jamais
d'exception : une brique RAG indisponible ne doit pas emporter les
trois outils qui, eux, ne dépendent que du système de fichiers.

## Alternatives écartées
- **pgvector sur le Postgres existant** : évite un service de plus,
  mais ce Postgres porte la comptabilité de dépense de la passerelle.
  Y mêler un index applicatif couple deux cycles de vie sans rapport
  (une réindexation ne doit pas pouvoir gêner la facturation).
- **Découpage à taille fixe avec recouvrement** : simple, et faux ici.
  Voir ci-dessus.
- **Index en mémoire dans le serveur MCP** : réindexation à chaque
  démarrage, pas d'inspection possible de l'état.
- **Appel direct à Ollama** : contourne l'ADR 0001.
- **Remplacer `search_runbooks`** : perdrait la recherche exacte, la
  seule fiable sur un code d'erreur.

## Conséquences
+ Valeur démontrée par test le 25/08 : `search_runbooks("redémarre en
  boucle")` ne trouve rien (l'expression est absente du corpus), tandis
  que `semantic_search("le service redémarre en boucle")` classe les
  quatre fragments du runbook crash-loop aux rangs 1 à 4, devant le
  runbook PostgreSQL.
+ Dégradation vérifiée : Qdrant arrêté, l'outil rend un message
  actionnable et `search_runbooks` continue de répondre.
+ Idempotence vérifiée : deux exécutions consécutives, 7 points,
  identifiants identiques.
- L'index n'est pas rafraîchi automatiquement : `uv run indexer.py`
  après toute modification de runbook. Un hook reste à décider.
- La fenêtre de nomic-embed-text est de 2048 jetons. Le corpus actuel
  en est très loin (fragment le plus long : 295 caractères), mais
  l'indexeur alerte au-delà de 6 000 caractères car Ollama tronque
  silencieusement.
- Un service de plus à opérer.
