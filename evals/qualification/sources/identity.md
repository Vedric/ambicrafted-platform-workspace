# Identités — IAM, RBAC et secrets

Comparer les actions, ressources, conditions et bindings aux opérations réellement nécessaires. Un rôle wildcard demande une réduction justifiée et un test positif et négatif avec l’identité cible.

Préférer une identité de workload et des secrets courts lorsque la plateforme le permet. Ne pas copier de jeton ni afficher de secret dans une réponse, un journal ou une preuve de test.

Après une réduction de droits approuvée, vérifier que les opérations requises réussissent et que les opérations hors périmètre échouent. Prévoir un rollback borné et journalisé si le service légitime est interrompu.
