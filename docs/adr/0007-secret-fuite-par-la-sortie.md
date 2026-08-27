# ADR 0007 : un secret fuit par la sortie d'une commande, pas seulement par un fichier

Statut : accepté
Date : 2026-08-27 (complété le même jour : hook `Bash`, retour
d'expérience de la rotation)

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
5. **Extension du hook au matcher `Bash`, version « littéraux
   seulement »** (décidé le 2026-08-27). Un second bloc `PreToolUse`
   avec le matcher `Bash` appelle le même `block-secrets.sh`, qui lit
   `.tool_input.command` en plus de `content` / `new_string`, avec les
   **motifs existants** (préfixes `sk-ant-`, `sk-master-`, `sk-proj-`,
   `AKIA`, `ghp_`, `glpat-`, en-tête de clé privée) et **rien d'autre**.
   Il bloque une commande dont le texte porte une valeur en clair
   (`sed -i "s|…|CLE=sk-…|" .env`, `curl -H "x-api-key: sk-…"`) et
   laisse passer une commande qui charge ou vérifie sans afficher
   (`sed -nE 's/^NOM=//p' .env`, `${v:0:12}`). Les tests, dans les deux
   sens, sont dans `.claude/hooks/test-block-secrets.sh` ; ils
   assemblent leurs fausses clés à l'exécution, précisément parce qu'un
   littéral dans le fichier de test déclencherait le hook.

   La famille « formes afficheuses » (`cat .env`, `compose config` sans
   `--quiet`, `docker inspect`, `printenv`…) envisagée dans la première
   version de cet ADR est **écartée**. C'est une liste noire de formes
   de commande, dont la conception même a montré qu'elle se contourne
   de six manières sans la moindre intention : une variable
   (`f=.env; cat $f`), une substitution (`cat $(echo .env)`), un glob
   (`cat .en?`), un autre interpréteur
   (`python -c 'print(open(".env").read())'`), une copie intermédiaire
   (`cp .env /tmp/x; cat /tmp/x`), un outil non listé (`awk`, `tail`,
   `less`, `bat`). Son coût réel n'est pas l'entretien de la liste,
   c'est le **faux sentiment de frontière** : une fois en place, on
   cesse de se demander si la commande va afficher, parce que « le hook
   l'aurait arrêtée ». Un garde-fou auquel on fait confiance à tort est
   pire qu'un garde-fou absent, qui laisse la vigilance intacte. Le hook
   retenu reste donc ce qu'il est honnêtement : un filet contre
   l'inattention sur un cas net (une valeur collée en clair dans une
   commande), pas une frontière de sécurité.

## Ce que cela ne résout pas

- **La limite structurelle, qui compte plus que le hook lui-même** : un
  `PreToolUse` voit la commande, jamais sa sortie. Le canal de fuite
  réel de l'incident, **une valeur qui apparaît dans un `tool_result`**,
  n'est **pas couvrable à ce niveau**. Le hook retenu n'aurait arrêté
  aucune des fuites de la table ci-dessus : `cat .env`,
  `compose config`, `docker inspect`, `printenv` ont un texte de
  commande qui ne contient aucun secret ; le secret est dans ce qu'ils
  renvoient. Un `PostToolUse` voit la sortie, mais après qu'elle est
  entrée dans le contexte, et sans pouvoir la réécrire. Aucun hook
  n'empêche donc une fuite par la sortie. Ce qui protège, c'est la
  règle 8 appliquée par l'agent et par l'humain : ne jamais produire une
  commande dont la sortie **peut** contenir une valeur, et juger cela
  avant de la lancer, pas après.
- `deny Read(.env)` reste utile (il ferme l'outil le plus direct) mais
  ne protège que contre l'outil `Read`. Ne pas le lire comme « l'agent
  ne peut pas voir `.env` ».
- La seule défense complète est qu'une valeur secrète n'ait **jamais
  besoin** d'apparaître dans une session : préparée hors session, testée
  par ses effets (une connexion qui réussit, un code HTTP), jamais par
  sa lecture.

## Retour d'expérience : la rotation

La rotation de `ANTHROPIC_API_KEY` a coûté plus cher que l'incident qui
l'a déclenchée, pour une raison de méthode. Trois clés ont été créées et
révoquées dans la console en moins d'une heure, dans l'urgence, pendant
que `.env` était mis à jour en parallèle. Résultat : `.env` a fini par
contenir une clé **déjà révoquée** (finissant par `NAAA`, absente de la
liste des clés actives de la console), alors que rien localement ne le
laissait voir : longueur correcte, préfixe correct, conteneur recréé.
Le symptôme, une erreur d'authentification sur l'alias `fast`, a
d'abord été cherché du côté de la passerelle (config, recréation du
conteneur) avant que la comparaison avec la console ne montre que la
clé était simplement morte. Le diagnostic a coûté plus que la rotation.

Ce que la vérification par longueur et préfixe ne dit pas : qu'une clé
est **valide**. Elle prouve seulement que la valeur a changé. Seul un
appel bout en bout, une requête qui exerce ce secret et revient en 200,
prouve que la valeur en place est celle qui vit côté fournisseur.

Recommandation, reprise dans la procédure de `gateway/README.md` :

1. **Une rotation à la fois.** Un seul secret, une seule nouvelle
   valeur, créée une seule fois.
2. **Vérifiée bout en bout avant la suivante** : `.env` mis à jour,
   `docker compose up -d`, puis un appel réel qui exerce ce secret
   (clé Anthropic : une complétion sur `fast` ; master key :
   `/v1/models` ; Postgres : `/health/readiness` → `"db": "connected"`).
   Tant que cet appel n'a pas répondu, on ne touche à rien d'autre.
3. **Révoquer l'ancienne valeur après ce succès seulement**, jamais au
   moment de créer la nouvelle. Quelques minutes de chevauchement
   coûtent moins qu'une clé morte dans `.env`.
4. Si une rotation échoue, **une seule** nouvelle tentative, même
   protocole ; pas de rafale de clés dans la console. Chaque clé créée
   « au cas où » est une clé de plus dont on ne sait plus si elle vit.

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
- **Liste noire de « formes afficheuses » dans le hook `Bash`** : voir
  la décision 5. Contournable par toute indirection, et son coût réel
  est de faire croire à une frontière qui n'existe pas.
