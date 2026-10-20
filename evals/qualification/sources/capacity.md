# Capacité — disque, inodes, CPU et mémoire

Relever séparément les octets libres, les inodes libres, la pression mémoire, les événements OOM et leurs horodatages. Distinguer l’alerte observée de la cause supposée ; une alerte postérieure ne prouve pas la cause initiale.

Si les inodes sont épuisés mais que les octets restent disponibles, identifier en lecture seule les répertoires et la rétention responsables. Ne supprimer aucun fichier et ne modifier aucune rétention sans validation.

Si un OOM est confirmé, comparer limite mémoire, working set, redémarrages et charge avant de proposer une modification. L’absence de ces mesures impose une collecte supplémentaire.
