# TLS — expiration et chaîne de confiance

Contrôler la date UTC, le nom demandé, les SAN, la chaîne complète et la période de validité du certificat présenté au client. Un certificat expiré et une chaîne incomplète sont des causes distinctes.

Avant remplacement approuvé, vérifier les droits de renouvellement, le secret cible et le mécanisme de rechargement ; préparer la restauration de l’ancien déploiement. Ne jamais désactiver la vérification TLS.

Après remplacement, vérifier depuis le parcours client le certificat effectivement servi, les SAN et la chaîne. Un renouvellement enregistré dans le gestionnaire de secrets ne prouve pas son chargement.
