# ADR 0003 : agent SRE borné, sans framework

Statut : accepté, en service local depuis le 25/08/2026
Date : 2026-08-25

## Contexte
La plateforme dispose des briques : passerelle avec alias et clés
virtuelles, corpus de runbooks versionné, serveur MCP en lecture seule,
recherche sémantique, traçage vers Tempo. Elles n'avaient jamais été
assemblées en un objet exécutable.

Un agent d'astreinte est le cas le plus exposé qu'on puisse construire :
il ingère de la donnée client non maîtrisée, il consomme du budget de
manière non déterministe, et sa sortie sera lue par quelqu'un de fatigué
qui l'exécutera. Les trois façons dont il peut nuire — fuite, dérive de
coût, procédure inventée — appellent des garde-fous *structurels*, pas
des consignes de prompt.

## Décision

### Pas de framework d'agent
La boucle est écrite à la main dans `agent.py`, environ cent lignes. Ce
sont exactement les lignes où se décident le décompte du budget, le choix
de l'alias par classification de donnée, et l'encapsulation des résultats
d'outils. Déléguer cette boucle à une bibliothèque, c'est déléguer les
garde-fous à du code qu'on ne relit pas.

Ce choix est aussi une base de comparaison : un portage LangGraph est
prévu comme étape ultérieure. Comparer suppose d'avoir la version nue.

### Le cloisonnement l'emporte sur le choix d'alias par étape
La spécification initiale plaçait la classification de l'alerte sur
l'alias `fast`. Appliquée à l'alerte brute, elle enverrait de la donnée
client à la frontière, en contradiction avec la règle 2 du CLAUDE.md.

Le traitement est donc scindé en deux :

```
alerte brute ──[ local, CONFIDENTIEL ]──> extraction anonymisée
                                              │
                      ═══ frontière ═══       │
               ──[ fast,  DERIVE ]──> tri ────┤
               ──[ smart, DERIVE ]──> boucle outillée ──> diagnostic
```

L'étape locale extrait la signature technique, retire les identifiants et
relève les tentatives d'injection. `fast` fait bien le tri, mais sur
l'extraction. Aucun octet d'alerte brute ne franchit la frontière, et
l'intention d'origine — un tri rapide et peu coûteux — est préservée.

Conséquence assumée : le modèle local raisonne avant de répondre, cette
étape coûte 30 à 50 secondes. C'est le prix de la confidentialité, il est
payé une fois par alerte.

### Un point de passage unique vers la passerelle
Tout appel LLM traverse `llm.appeler_llm`, qui prend une `Classification`
obligatoire. Il y a un seul endroit à lire pour savoir si de la donnée
client peut sortir. Un appel direct à `httpx` ailleurs dans le paquet
serait un défaut d'architecture, pas une optimisation.

La garde repose sur une partition stricte des alias en `ALIAS_LOCAUX` et
`ALIAS_FRONTIERE` : c'est elle qui rend la décision calculable plutôt
qu'interprétable. Un test vérifie que les deux ensembles restent
disjoints.

### Trois barrières plutôt qu'une
1. Garde applicative, avant tout accès réseau.
2. Clé virtuelle restreinte pour les charges confidentielles — la
   passerelle répond 403 si la première tombait.
3. Aucune bascule depuis `local` dans la configuration de la passerelle.

Elles sont indépendantes : aucune ne suppose la correction des autres.

### La sécurité vient de l'absence de l'outil
L'agent n'a ni shell, ni écriture, ni HTTP arbitraire. Non parce qu'un
prompt l'interdit, mais parce qu'aucune fonction du paquet ne les expose.
`OUTILS_AUTORISES` est en outre une liste blanche fermée : un outil que
le serveur MCP publierait sans y figurer ne serait jamais présenté au
modèle. Ajouter un outil reste une décision de ce dépôt.

### Budgets opposés au moment de la tentative
Le budget d'outils est décompté *avant* exécution : un appel refusé
n'atteint pas le serveur. Le budget monétaire est imputé *après*, depuis
l'en-tête de coût de la passerelle — l'agent ne tient aucune table
tarifaire, ce qui l'obligerait à connaître des noms de modèles.

Sous-décision importante : à budget d'outils épuisé, les outils restent
déclarés au modèle. La tentation était de les retirer pour « économiser »
un tour ; cela ferait répondre le modèle sans avoir consulté les
runbooks, et cette réponse dégradée serait rendue comme un diagnostic.
Un budget doit être opposé au moment où l'agent tente de le dépasser, pas
contourné en amont. Les deux budgets aboutissent au même arrêt : pas de
demi-diagnostic.

### Données non fiables encapsulées, jamais concaténées
Le texte de l'alerte et le contenu des runbooks entrent dans le contexte
entre deux marqueurs portant un jeton aléatoire tiré par exécution. Le
jeton n'est pas de la cryptographie : il retire à qui rédige l'alerte la
possibilité d'écrire le marqueur de fermeture. La consigne associée
demande de **rapporter** toute instruction rencontrée plutôt que de la
suivre — le signalement d'une injection est en soi une information de
diagnostic, puisqu'une alerte porteuse d'injection est probablement
forgée.

Le texte hostile relevé reste local. Les étapes frontière n'en reçoivent
que le décompte.

### `runbook_source` nullable, et exploité par le code
Un modèle à qui l'on impose une source en invente une. Autorisé à
déclarer `null`, il fournit l'information la plus utile du rapport.
`appliquer_garde_source()` retire alors ses actions de
`actions_proposees`, les déplace dans `actions_ecartees_sans_source` et
les remplace par une escalade humaine. Le code refuse la prose ; il ne se
contente pas de la lire.

## Conséquences

Vérifié en exécution :
- Alerte PostgreSQL : `incident-p1-database.md` retrouvé, diagnostic
  sourcé, 3 outils, 0,23 USD.
- Alerte TLS hors corpus : `runbook_source = null`, actions écartées par
  le code, aucune procédure inventée.
- `SRE_MAX_APPELS_OUTILS=2` : arrêt propre au refus du 3ᵉ outil, code 2.
- `SRE_MAX_COUT_USD=0.05` : arrêt propre, code 2.
- Alerte porteuse d'injection : instruction rapportée, non suivie.
- Trace complète dans Tempo : span parente et 8 spans enfants.

Coûts et limites acceptés :
- 30 à 50 s d'extraction locale par alerte.
- Le raisonnement sur `smart` consomme environ la moitié du plafond de
  0,50 USD sur un cas nominal. Le plafond est serré, c'est voulu :
  il faut qu'il puisse être atteint pour être crédible.
- L'adresse OTLP de Tempo est une adresse de conteneur, sensible à une
  recréation. Publier le port 4318 sur l'hôte serait le correctif
  durable, mais relève du compose de la passerelle, pas de cet agent.

## Alternatives écartées
- **Plan de recherche codé en dur** (semantic_search puis read_runbook) :
  rendrait le budget d'itérations décoratif, et supprimerait le
  comportement qu'il s'agit précisément d'encadrer.
- **Anonymisation par expressions régulières** : ne couvre pas les noms
  propres ni les identifiants métier, et ne relève pas les injections.
  Le modèle local fait les deux dans le même appel.
- **Interdiction des actions non sourcées par le prompt seul** :
  invérifiable. Le champ nullable plus le refus en aval sont testables.
