#!/usr/bin/env bash
INPUT=$(cat)
CONTENU=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // ""')

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
