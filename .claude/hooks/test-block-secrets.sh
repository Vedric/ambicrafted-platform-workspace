#!/usr/bin/env bash
# Tests du hook block-secrets.sh, dans les deux sens : ce qui doit être
# bloqué l'est, ce qui doit passer passe. Les fausses clés sont assemblées à
# l'exécution pour qu'aucun littéral de ce fichier ne déclenche le hook
# lui-même (ce qui illustre au passage sa limite : il ne voit que les
# littéraux, ADR 0007).
set -u
HOOK="$(dirname "$0")/block-secrets.sh"
FAUSSE_ANT="sk-ant-api03-$(printf 'x%.0s' $(seq 1 40))"
FAUSSE_AKIA="AKIA$(printf 'A%.0s' $(seq 1 16))"
FAUSSE_GHP="ghp_$(printf 'a%.0s' $(seq 1 36))"
PEM="-----BEGIN RSA PRIVATE ""KEY-----"

echecs=0
attendu() { # $1=décision attendue, $2=libellé, $3=JSON d'entrée
  local got
  got=$(printf '%s' "$3" | bash "$HOOK" | jq -r '.decision')
  if [ "$got" = "$1" ]; then
    echo "OK    [$1] $2"
  else
    echo "ÉCHEC [attendu $1, obtenu $got] $2"; echecs=$((echecs+1))
  fi
}
j() { jq -cn --arg tool "$1" --arg champ "$2" --arg val "$3" \
  '{tool_name:$tool, tool_input:{($champ):$val}}'; }

# --- doit être bloqué ---
attendu block "Write : clé Anthropic dans content"      "$(j Write content "ANTHROPIC_API_KEY=$FAUSSE_ANT")"
attendu block "Edit : clé AWS dans new_string"          "$(j Edit new_string "aws_access_key_id = $FAUSSE_AKIA")"
attendu block "Write : en-tête de clé privée"           "$(j Write content "$PEM")"
attendu block "Bash : clé Anthropic dans la commande"   "$(j Bash command "sed -i 's|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$FAUSSE_ANT|' .env")"
attendu block "Bash : curl avec clé littérale"          "$(j Bash command "curl -H 'x-api-key: $FAUSSE_ANT' https://api.example")"
attendu block "Bash : jeton GitHub littéral"            "$(j Bash command "git remote set-url origin https://$FAUSSE_GHP@github.com/x/y")"

# --- doit passer ---
attendu approve "Bash : chargement légitime par sed"    "$(j Bash command "sed -nE 's/^LITELLM_MASTER_KEY=//p' .env")"
attendu approve "Bash : vérification longueur/préfixe"  "$(j Bash command 'v=$(sed -nE "s/^LITELLM_MASTER_KEY=//p" .env); echo "len=${#v} prefix=${v:0:12}"')"
attendu approve "Bash : valeur via variable (non vue)"  "$(j Bash command 'curl -H "Authorization: Bearer $LITELLM_MASTER_KEY" localhost:4000/v1/models')"
attendu approve "Bash : commande ordinaire"             "$(j Bash command "git status --short")"
attendu approve "Write : contenu ordinaire"             "$(j Write content "ANTHROPIC_API_KEY=os.environ/ANTHROPIC_API_KEY")"
attendu approve "Write : préfixe trop court (exemple)"  "$(j Write content "sk-ant-api03-xxxx…")"
attendu approve "Entrée sans champ connu"               '{"tool_name":"Read","tool_input":{"file_path":"/x"}}'
# Le modèle de variables versionné doit rester éditable : ses placeholders ne
# doivent matcher aucun motif (fichier réel, pas une copie).
EXEMPLE="$(dirname "$0")/../../gateway/.env.example"
attendu approve "Write : gateway/.env.example entier"    "$(j Write content "$(cat "$EXEMPLE")")"
attendu approve "Bash : heredoc de gateway/.env.example" "$(j Bash command "cat > .env.example <<'EOF'
$(cat "$EXEMPLE")
EOF")"

echo
if [ "$echecs" -eq 0 ]; then echo "Tous les tests passent."; else echo "$echecs échec(s)."; exit 1; fi
