# Certificat TLS expiré ou chaîne de confiance invalide

## Symptômes
Échec de négociation TLS, certificat expiré, nom d'hôte incompatible ou chaîne de certification incomplète. Distinguer un certificat serveur, un certificat client et une erreur d'horloge.

## Préconditions
Confirmer l'endpoint, le nom DNS attendu, l'environnement et le propriétaire du certificat. Ne jamais exporter ni afficher une clé privée dans un transcript ou un ticket.

## Vérifications en lecture seule
Vérifier l'heure système, les dates de validité, les noms DNS du certificat et la chaîne présentée par l'endpoint concerné, sans désactiver la vérification TLS du client.

Comparer le certificat réellement servi avec celui attendu par la configuration ; plusieurs instances ou un proxy peuvent présenter des certificats différents.

## Décision humaine
Faire confirmer par le responsable PKI la procédure de renouvellement, le stockage de la clé privée, les instances à recharger et la fenêtre de changement avant toute modification.

Si la chaîne ou l'identité du serveur reste incertaine, escalader au responsable PKI et conserver la vérification TLS active.

## Validation et retour arrière
Vérifier depuis un client représentatif que l'identité, les dates et la chaîne sont valides après le changement. Conserver une configuration de retour arrière approuvée ; un ancien certificat expiré n'est pas une solution de rétablissement valide.

## Limites
Ce runbook ne fournit pas de commande universelle de renouvellement : elle dépend de l'autorité, de l'automatisation et du service utilisé.
