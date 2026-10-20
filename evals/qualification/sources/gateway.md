# Passerelle HTTP — 502, 504 et dépendances

Corréler les 502 ou 504 avec les journaux amont, la connectivité, les délais applicatifs et les changements récents sur une fenêtre commune. Un déploiement proche dans le temps ne prouve pas la causalité.

Comparer les erreurs entre versions et instances, puis demander une validation avant tout rollback. Ne pas augmenter les timeouts pour masquer une saturation non caractérisée.

Après une intervention approuvée, vérifier taux d’erreur, latence et trafic réel, ainsi que les dépendances. Un simple health check vert ne suffit pas à démontrer le rétablissement.
