# Incident P1 : saturation connexions PostgreSQL

## Symptômes
- Erreurs "too many clients already"
- Latence applicative en hausse brutale

## Préconditions
Confirmer l'instance, l'environnement, l'impact et l'heure de début avec le responsable du service. Utiliser un compte de diagnostic autorisé. Conserver les résultats contenant des noms ou requêtes métier sur la machine locale.

## Vérifications en lecture seule
Compter les connexions et les regrouper par état avec `SELECT state, count(*) FROM pg_stat_activity GROUP BY state;` avant de choisir une intervention.

Comparer le nombre de connexions aux limites PostgreSQL et aux plafonds du pool applicatif ; ne pas augmenter un plafond sans vérifier la mémoire disponible et la concurrence maximale.

Identifier les transactions anciennes, attentes et changements applicatifs récents ; une session simplement inactive n'est pas une preuve de blocage.

## Décision humaine
Faire confirmer par le responsable de la base les sessions précisément ciblées, leur propriétaire, l'impact transactionnel et le risque de rollback avant toute terminaison de session.

En l'absence de cette confirmation, escalader au responsable de la base et poursuivre uniquement les vérifications en lecture seule.

Si une modification du pool est retenue, noter la valeur précédente, appliquer une seule modification validée et prévoir son retour arrière avant l'intervention.

## Validation et retour arrière
Vérifier que les nouvelles connexions réussissent, que la latence retrouve son niveau attendu et que les erreurs ne réapparaissent pas pendant la fenêtre d'observation convenue.

Restaurer la configuration précédente si la modification du pool aggrave la charge ; une transaction déjà terminée ne peut pas être rétablie par un simple retour de configuration.

## Limites
Ce runbook ne définit ni seuil universel de sessions, ni permission de tuer des processus, ni garantie d'absence de perte métier. Le diagnostic de réplication, corruption et manque d'espace exige une procédure dédiée.
