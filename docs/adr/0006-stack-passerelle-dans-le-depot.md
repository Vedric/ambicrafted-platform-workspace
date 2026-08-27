# ADR 0006 : la stack de la passerelle vit dans le dépôt

Statut : accepté
Date : 2026-08-25

## Contexte

La passerelle (LiteLLM, PostgreSQL, Tempo, Prometheus, Grafana, Qdrant)
n'existait que sur le disque, dans `~/platform/gateway/`, hors de tout
dépôt. Le principe fondateur de la plateforme est d'être reconstructible
depuis le dépôt ; sans la stack, il n'était pas tenu : un disque perdu
emportait la couche la plus critique.

Inspection préalable des références croisées depuis le workspace vers
`~/platform/gateway` : cinq fichiers (`CLAUDE.md`,
`mcp-servers/runbooks/{server,indexer}.py`, `sre_agent/config.py`,
`.claude/settings.json`), **toutes des chaînes lisibles par un humain**
(doc, messages d'erreur, docstring, règle de refus de lecture). Aucune
dépendance fonctionnelle au chemin. Le seul couplage réel est côté
Docker : les conteneurs portent `com.docker.compose.project=gateway` et
le chemin absolu des montages ; les volumes s'appellent `gateway_*`, le
préfixe venant du nom de base du dossier.

## Options

1. **Déplacer** `gateway/` dans le workspace.
2. **Laisser en place et lier** : un lien symbolique
   `workspace/gateway → ~/platform/gateway`. Git commite un lien
   symbolique comme un lien : un clone propre n'a aucun contenu. Ne
   remplit pas l'objectif.
3. **Déplacer et garder un lien** à l'ancien emplacement, de façon
   permanente. Deux chemins pour le même compose. Compose calcule un
   hash de configuration par service qui inclut les chemins absolus des
   bind mounts ; un `docker compose up` lancé tantôt depuis un chemin,
   tantôt depuis l'autre, recréerait les conteneurs à chaque alternance.
   Un piège permanent sans contrepartie, puisque rien ne dépend du chemin.
4. **Dépôt séparé** pour la stack. Possible, mais contredit « le
   workspace est le dépôt de la plateforme » et double la maintenance
   (deux dépôts à cloner pour reconstruire).

## Décision

Option 1 : `~/platform/gateway` devient `~/platform/workspace/gateway`,
les cinq références sont mises à jour, aucun lien permanent.

Avec, dans la même passe :

- `name: gateway` en tête du compose. Sans lui, le nom de projet, donc
  le préfixe des volumes, dépend du nom du dossier : un clone dans un
  dossier nommé autrement créerait une seconde stack vide, en collision
  de ports avec la première. C'est l'inverse de la reproductibilité
  recherchée.
- Épinglage par digest des trois images qui ne l'étaient pas
  (`litellm:main-stable`, `postgres:16-alpine`, `qdrant:v1.19.0`),
  relevé sur les conteneurs en service, pas sur le registre (règle 7).
  Le tag `main-stable` pointait ce jour-là sur le même digest que celui
  en service ; c'est une coïncidence de calendrier, pas une garantie.
- `.env.example` avec valeurs factices explicites ; `.env` reste ignoré,
  vérifié par `git check-ignore` avant tout `git add`. La règle `.env.*`
  du `.gitignore` racine aurait ignoré `.env.example` : exception
  `!.env.example` ajoutée.
- `gateway/README.md` : reconstruction depuis zéro, vérifications, et la
  liste explicite de ce que `docker compose config` ne prouve pas.

## Conséquences

- Un clone du dépôt plus un `.env` suffit pour `docker compose up -d`
  sur une machine neuve. Ce que le dépôt ne reconstruit pas (clés
  virtuelles, dépense, index Qdrant, traces) est listé dans le README
  avec la procédure de recréation.
- **Dette de recréation.** Le déplacement s'est fait sans arrêter les
  services. Les conteneurs en cours portent encore les anciens chemins
  de montage : au prochain `docker compose up -d` depuis le nouveau
  dossier, compose les recréera (quelques secondes d'interruption,
  volumes conservés grâce à `name: gateway`). Entre-temps, un lien
  symbolique **transitoire** `~/platform/gateway → workspace/gateway`
  protège les redémarrages automatiques (`restart: unless-stopped`,
  montages déclarés en `Binds` absolus : sans le lien, Docker créerait
  un dossier à la place du fichier et le conteneur ne repartirait pas).
  Le lien est à supprimer juste après ce premier `up`, pour ne pas
  retomber dans l'option 3.
  **Soldée le 2026-08-27** : `up -d` depuis `workspace/gateway`, six
  conteneurs recréés sur les nouveaux chemins de montage, lien supprimé.
- La preuve de reconstructibilité apportée à cette date est
  `docker compose config` sur un clone propre avec un `.env` fabriqué
  depuis `.env.example`. Elle prouve la syntaxe, l'interpolation et la
  présence des fichiers ; ni le démarrage, ni la communication entre
  services, ni la recréation des volumes. Le déroulé complet sur machine
  neuve reste à faire.
