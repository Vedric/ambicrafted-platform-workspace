# PostgreSQL — saturation de connexions

Avant toute modification, relever le nombre de connexions actives et idle, les limites du pool, les erreurs de refus et leurs horodatages. Une occupation de 95 sur 100 ne démontre pas à elle seule une saturation.

Si des refus de connexion sont confirmés, comparer les connexions par application et les transactions longues. Présenter les mesures à l’astreinte ; ne terminer aucune session et ne relever aucune limite sans validation explicite.

Après une correction approuvée et exécutée par l’opérateur, vérifier les refus, le p95 et les transactions actives sur la même fenêtre de mesure. Préparer le retour à la configuration précédente si les erreurs augmentent.
