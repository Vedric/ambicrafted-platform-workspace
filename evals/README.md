# Évaluations promptfoo

Compare le modèle local (`local`) et la frontière (`balanced`) sur des
tâches SRE réelles, avec un juge LLM pour les assertions `llm-rubric`.

## Lancer

```sh
cd ~/platform/workspace/evals
npx promptfoo eval          # exécute promptfooconfig.yaml
npx promptfoo view          # interface de résultats
```

Rien à exporter. Les trois fournisseurs (`local`, `balanced`, juge)
lisent dans l'environnement :

| Variable | Origine | Rôle |
|---|---|---|
| `ORCHESTRATOR_KEY` | `.env` du workspace, chargé par direnv | clé virtuelle LiteLLM, via `apiKeyEnvar` |
| `LITELLM_BASE_URL` | idem | URL de la passerelle, via `apiBaseUrl: "{{ env.LITELLM_BASE_URL }}"` |

`OPENAI_API_KEY` et `OPENAI_BASE_URL` ne sont ni lues ni nécessaires ;
si elles traînent dans le shell, elles sont ignorées par ces
fournisseurs. Vérifié le 2026-08-27 avec les deux variables
explicitement retirées de l'environnement (`env -u`).

## Pourquoi `ORCHESTRATOR_KEY` et non la master key

Moindre privilège (ADR 0007, retour d'expérience de la rotation) :

- la master key donne tous les droits sur la passerelle (création de
  clés, dépense illimitée, administration) ; le harnais n'a besoin que
  d'appeler des alias ;
- `ORCHESTRATOR_KEY` est une clé virtuelle hachée en base : une rotation
  de la master key ne l'invalide pas. Il n'y a donc **plus rien à
  propager** ici lors d'une rotation de la master key ;
- sa propre rotation se fait dans le `.env` du workspace, jamais dans ce
  dossier.

Les cas confidentiels (données client) ne passent pas par ce harnais :
ils utiliseraient `CONFIDENTIAL_KEY` et l'alias `local` seulement
(règle 2 du CLAUDE.md).

## Vérifier la clé sans l'afficher

```sh
echo "len=${#ORCHESTRATOR_KEY} prefix=${ORCHESTRATOR_KEY:0:12}"
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $ORCHESTRATOR_KEY" "$LITELLM_BASE_URL/models"   # 200 attendu
```

## Structure

- `promptfooconfig.yaml` : fournisseurs, juge, seuil de latence, liste des cas ;
- `cas/*.yaml` : un fichier par tâche, avec ses assertions ;
- `.promptfoo/` et `output/` sont ignorés par git.
