# Service systemd en crash-loop

## Symptômes
- `systemctl status` : activating/failed en boucle
- "Start request repeated too quickly" dans journalctl

## Préconditions
Confirmer l'unité, l'environnement et l'impact avec le propriétaire du service. L'agent ne redémarre rien et ne modifie pas la configuration.

Si le message est `Start request repeated too quickly`, faire exécuter `systemctl reset-failed <service>` par l'opérateur autorisé avant le diagnostic : ce message indique une limite de redémarrage, pas la cause initiale.

## Vérifications
Examiner l'état de l'unité et ses erreurs récentes avec `systemctl status <service>` et `journalctl -u <service>` sur une fenêtre temporelle limitée, en gardant les données sensibles locales.

Vérifier les chemins, permissions, dépendances et overrides de l'unité ; ne pas afficher ni recopier les valeurs des variables contenant des secrets.

## Causes fréquentes
- Chemin inaccessible pour l'utilisateur du service (permission denied)
- Variable d'environnement pointant vers une ressource absente
- Bind sur une adresse qui n'existe pas encore (ordre de démarrage)

## Décision humaine
Faire approuver la correction ciblée et sauvegarder l'override existant avant toute modification ; vérifier que le redémarrage prévu respecte les contraintes du service.

Appliquer une correction à la fois via un override, puis recharger la configuration et redémarrer uniquement l'unité approuvée dans la fenêtre convenue.

## Validation et retour arrière
Vérifier que le service reste actif, que le port attendu écoute et qu'une requête fonctionnelle réussit sans nouveau redémarrage pendant la fenêtre d'observation.

Restaurer l'override précédent et recharger la configuration si la correction échoue, puis escalader au propriétaire du service avant de multiplier les redémarrages.

## Limites
Une unité active n'est pas une preuve de santé applicative. Ce runbook ne remplace pas les procédures de restauration de données, de migration ou de gestion des secrets du service.
