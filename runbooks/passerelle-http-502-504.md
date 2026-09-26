# Erreurs HTTP 502 ou 504 sur une passerelle

## Symptômes
La passerelle répond 502 ou 504, la latence augmente ou les requêtes expirent. Un 502 et un 504 ne prouvent pas une cause unique.

## Préconditions
Identifier la route et le backend concernés, la période et la proportion de requêtes affectées. Utiliser des identifiants de corrélation expurgés ; ne pas copier d'en-tête d'autorisation ou de corps client dans les traces de diagnostic.

## Vérifications en lecture seule
Comparer l'état du backend, ses temps de réponse et les erreurs de connexion avec les délais configurés dans la passerelle et le client.

Vérifier les changements récents, la saturation du backend et les dépendances lentes avant d'augmenter un délai ou de multiplier les tentatives.

## Décision humaine
Faire valider une seule modification ciblée avec sa valeur précédente, son impact sur la concurrence et sa procédure de retour arrière avant intervention.

Si le backend est saturé, escalader au responsable du service et éviter les relances massives qui augmenteraient la charge.

## Validation et retour arrière
Contrôler le taux d'erreur, les percentiles de latence et le volume de requêtes après le changement. Revenir à la valeur précédente si la file d'attente ou la saturation augmente.

## Limites
Ce runbook ne couvre pas les incidents DNS, certificats ou pare-feu sans observations supplémentaires ; il ne justifie pas un redémarrage global des services.
