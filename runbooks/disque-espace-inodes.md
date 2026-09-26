# Saturation d'espace disque ou d'inodes

## Symptômes
Erreurs `No space left on device`, écritures refusées, stockage saturé ou inodes épuisés. Un disque plein peut rendre les bases et journaux indisponibles.

## Préconditions
Identifier le système de fichiers concerné et le service affecté. Distinguer capacité en octets et nombre d'inodes. Ne pas supposer qu'un fichier volumineux est supprimable.

## Vérifications en lecture seule
Comparer l'espace et les inodes disponibles avec `df -h` et `df -i`, puis localiser la croissance dans le seul répertoire du service affecté avec des outils de diagnostic autorisés.

Vérifier si des fichiers supprimés restent ouverts par un processus et si les politiques de rotation ou de rétention ont cessé de fonctionner.

## Décision humaine
Faire valider par le propriétaire des données une liste précise de fichiers et leur durée de conservation avant toute suppression, rotation forcée ou réduction de rétention.

En l'absence de politique de conservation ou de sauvegarde vérifiée, escalader sans supprimer les journaux, checkpoints, fichiers de base ou volumes Docker.

## Validation et retour arrière
Confirmer la reprise des écritures et surveiller la vitesse de croissance. Si une extension est choisie, vérifier la procédure du stockage utilisé avant de modifier le volume. Une suppression sans sauvegarde n'a pas de retour arrière garanti.

## Limites
Ce runbook n'autorise ni `docker system prune`, ni suppression récursive, ni manipulation directe des fichiers d'une base active.
