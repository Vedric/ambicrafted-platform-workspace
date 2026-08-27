# ADR 0007 : un secret fuit par la sortie d'une commande, pas seulement par un fichier

Statut : accepté
Date : 2026-08-27

## Contexte : l'incident

Pendant le déplacement de la stack (ADR 0006), les quatre valeurs
secrètes de `gateway/.env` (`LITELLM_MASTER_KEY`, `POSTGRES_PASSWORD`,
aussi présent en clair dans `DATABASE_URL`, `ANTHROPIC_API_KEY`,
`GRAFANA_ADMIN_PASSWORD`) sont apparues dans le contexte d'une session
d'agent. Aucune n'a été écrite dans un fichier versionné ; `.env` est
resté ignoré par git ; la règle `deny Read(~/platform/workspace/gateway/.env)`
de `.claude/settings.json` était en place et n'a pas été contournée.
Elles ont simplement figuré dans la **sortie** de commandes.

Conséquence opérationnelle : rotation complète des quatre secrets le
2026-08-27 (procédure dans `gateway/README.md`, « Rotation des secrets »).
Une valeur qui a transité par un contexte de modèle est compromise,
quelle que soit la suite : elle est dans la transcription locale
(`~/.claude/projects/*/…jsonl`), dans les résumés de contexte, et dans
tout ce qui réutilise cette transcription (reprise de session, agents
délégués, retours produit). On ne nettoie pas, on tourne.

## Le mécanisme

Le modèle de menace implicite jusqu'ici était « un secret fuit s'il est
écrit quelque part » : `.gitignore`, hook `block-secrets.sh` sur
`Write|Edit`, `deny Read(.env)`. Ces trois barrières partagent un angle
mort : elles regardent ce que l'agent **écrit** ou **lit comme fichier**,
pas ce que ses commandes **impriment**.

Or un agent travaille surtout par `Bash`, et la sortie d'une commande
entre intégralement dans son contexte. Chemins de fuite constatés ou
évidents, tous sans écriture et tous invisibles pour `deny Read` :

| Commande | Ce qui sort |
|---|---|
| `cat`, `head`, `less`, `grep -r motif .`, `sed -n p` sur un `.env` | le fichier entier ou la ligne qui contient la valeur |
| `docker compose config` (sans `--quiet`) | le compose **interpolé** : chaque `${VAR}` remplacé par sa valeur |
| `docker inspect <conteneur>` | `Config.Env` complet, `env_file` inclus |
| `env`, `printenv`, `set`, `export -p`, `direnv export` | tout l'environnement, donc tout ce que direnv a chargé du `.env` |
| `echo "$VAR"`, `printf`, `set -x` | la valeur d'une variable, ou toutes celles des commandes tracées |
| `git diff`, `git show` sur un fichier commité par erreur | la valeur, même après suppression du fichier |
| un message d'erreur | un client PostgreSQL ou HTTP qui recopie la DSN ou l'en-tête `Authorization` dans son exception |
| des logs en mode debug | LiteLLM, promptfoo, un SDK : en-têtes et corps de requêtes |
| `curl -v`, `httpx` en debug | l'en-tête `Authorization` envoyé |

S'y ajoutent deux canaux qui ne sont pas des sorties mais entrent dans
le même contexte :

- la **commande elle-même** : un `sed -i "s|…|CLE=sk-…|"` porte la
  valeur en clair dans le texte de la commande, donc dans la
  transcription. Une valeur nouvelle donnée à l'agent pour être écrite
  est exposée par le geste même de l'écrire ;
- la **saisie de l'utilisateur** : coller un secret dans la conversation
  l'expose exactement autant.

## Décision

1. **Règle 8 du CLAUDE.md.** Un secret ne s'affiche jamais, même pour le
   vérifier. La vérification se fait par **longueur** et **préfixe**
   (12 caractères), jamais par la valeur :
   `v=$(sed -nE 's/^NOM=//p' .env); echo "len=${#v} prefix=${v:0:12}"`.
   Le préfixe suffit à distinguer une ancienne valeur d'une nouvelle,
   ne permet pas de la reconstituer, et se compare à l'œil.
2. **Une valeur ne transite que par des variables de shell**, jamais par
   un argument littéral ni par une sortie : générée par `openssl rand`
   dans une variable, écrite par `sed` depuis cette variable, passée à
   `psql` par **stdin**, à `curl` par `-H "Authorization: Bearer $V"`.
   Les arguments de processus restent visibles dans `/proc` un instant ;
   c'est accepté sur une machine mono-utilisateur, la sortie ne l'est pas.
3. **Un secret nouveau fourni par l'humain n'entre pas dans la
   conversation.** Il l'écrit lui-même dans `.env` depuis son terminal
   (`read -rs K && sed -i … && unset K`) et l'agent ne vérifie que
   longueur et préfixe. Le chemin « je te la colle, tu l'écris » est
   accepté seulement si l'humain le décide en connaissance de cause : la
   valeur est alors dans la transcription comme si elle avait fui.
4. **Après toute exposition, rotation, pas nettoyage.** Une transcription
   ne se purge pas de façon fiable. La procédure de rotation, avec ses
   deux pièges (Postgres et Grafana ne relisent pas `.env` après la
   première initialisation), est dans `gateway/README.md`.
5. **Extension du hook au matcher `Bash`** : proposée, en attente de
   décision. Elle peut bloquer une commande dont le **texte** contient
   un secret ou dont la **forme** est un afficheur connu de `.env`
   (`cat .env`, `compose config` sans `--quiet`, `docker inspect`,
   `printenv`). Elle ne peut pas voir la sortie, ni ce qui passe par une
   variable, une substitution, un script ou un chemin indirect. C'est un
   garde-fou contre l'inattention, pas une frontière de sécurité.

## Ce que cela ne résout pas

- Un `PreToolUse` voit la commande, pas son résultat ; un `PostToolUse`
  voit le résultat après qu'il est entré dans le contexte. Aucun hook
  n'empêche une fuite par la sortie ; il ne peut qu'interdire des formes
  de commande connues, et toute indirection les contourne.
- `deny Read(.env)` reste utile (il ferme l'outil le plus direct) mais
  ne protège que contre l'outil `Read`. Ne pas le lire comme « l'agent
  ne peut pas voir `.env` ».
- La seule défense complète est qu'une valeur secrète n'ait **jamais
  besoin** d'apparaître dans une session : préparée hors session, testée
  par ses effets (une connexion qui réussit, un code HTTP), jamais par
  sa lecture.

## Alternatives écartées

- **Redaction automatique des sorties** (un filtre qui masque tout motif
  `sk-…` avant que la sortie n'atteigne le contexte) : pas de point
  d'accroche dans l'outillage actuel pour réécrire un résultat d'outil,
  et un mot de passe hexadécimal ou un mot de passe libre n'a pas de
  motif reconnaissable. Réduirait le risque pour les clés à préfixe,
  donnerait un faux sentiment de sécurité pour le reste.
- **Interdire tout `Bash` touchant `.env`** : la rotation elle-même lit
  `.env` par `sed` pour charger des variables. Une interdiction en bloc
  forcerait des contournements, qui sont précisément ce qu'on veut
  éviter. On interdit les formes qui affichent, pas celles qui chargent.
