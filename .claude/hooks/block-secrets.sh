#!/usr/bin/env bash
# Hook PreToolUse (Write|Edit et Bash) : refuse un appel d'outil dont le
# texte contient un secret reconnaissable par son préfixe.
#
# Périmètre volontairement réduit aux LITTÉRAUX (ADR 0007) :
# - Write/Edit : le contenu écrit ;
# - Bash       : le texte de la commande.
# Il ne voit jamais la SORTIE d'une commande, ni une valeur qui transite par
# une variable, une substitution, un glob ou un script. C'est un garde-fou
# contre l'inattention, pas une frontière de sécurité.
INPUT=$(cat)
CONTENU=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // .tool_input.command // ""')

MOTIFS=(
  'sk-ant-[a-zA-Z0-9_-]{20,}'
  'sk-master-[a-zA-Z0-9]{20,}'
  'sk-proj-[a-zA-Z0-9_-]{20,}'
  'AKIA[0-9A-Z]{16}'
  'ghp_[a-zA-Z0-9]{36}'
  'glpat-[a-zA-Z0-9_-]{20}'
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
)

for m in "${MOTIFS[@]}"; do
  if echo "$CONTENU" | grep -qE -- "$m"; then
    echo '{"decision":"block","reason":"Secret détecté. Utiliser une variable d environnement."}'
    exit 0
  fi
done
echo '{"decision":"approve"}'
