# Terraform — plan, état et changement destructif

Examiner le plan complet, le workspace, le backend d’état, les versions de providers et les dépendances avant toute conclusion. Un extrait de plan ne démontre pas l’absence d’autres changements.

Pour un remplacement ou une suppression de données, exiger sauvegarde restaurable, fenêtre approuvée et stratégie de migration. Ne pas lancer apply, force-unlock ou une modification directe d’état depuis une analyse.

Verifier séparément le verrouillage du backend et le chiffrement des données d’état. La présence de sensitive dans Terraform masque une sortie mais ne garantit pas l’absence de secret dans l’état.
