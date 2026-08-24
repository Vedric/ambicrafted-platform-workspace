# Incident P1 : saturation connexions PostgreSQL

## Symptômes
- Erreurs "too many clients already"
- Latence applicative en hausse brutale

## Diagnostic
1. `SELECT count(*) FROM pg_stat_activity;`
2. Identifier les connexions idle in transaction
3. Vérifier la configuration du pooler

## Remédiation
1. Terminer les sessions idle de plus de 30 minutes
2. Augmenter la taille du pool si la charge est légitime
3. Ouvrir un post-mortem si la cause est applicative
