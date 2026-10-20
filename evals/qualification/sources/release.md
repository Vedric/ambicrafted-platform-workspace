# Changement — canary, migration et rollback

Comparer taux d’erreur, latence, trafic et saturation entre version candidate et référence sur des fenêtres comparables. Un faible trafic ou une fenêtre trop courte ne permet pas une validation de canary.

Avant une migration destructive, vérifier la compatibilité ancien et nouveau code avec le schéma et tester la restauration. Un rollback du binaire ne restaure pas les données supprimées.

Définir les critères d’arrêt, la décision humaine et le responsable du rollback avant le déploiement. Ne pas approuver un changement à partir du seul statut vert de la CI.
