# Kubernetes — probes, redémarrages et disponibilité

Lire les événements du Pod, les logs courants et précédents, les probes et les ressources déclarées. Distinguer un échec de readiness, une liveness trop agressive et un OOM avant de proposer une correction.

Pour une application lente au démarrage, vérifier le temps de démarrage observé et le budget de startupProbe. Toute modification de probes nécessite un test de démarrage, de panne et de récupération ; ne pas supprimer toutes les probes.

Contrôler replicas, stratégie de rollout et PodDisruptionBudget ensemble. Un PDB ne garantit ni la tolérance à une panne involontaire ni la disponibilité pendant toutes les mises à jour.
