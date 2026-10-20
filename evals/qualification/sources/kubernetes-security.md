# Kubernetes — revue de privilèges

Examiner privileged, runAsNonRoot, allowPrivilegeEscalation, capabilities, seccomp et les volumes hôte dans le contexte du besoin applicatif. Demander une justification explicite pour tout accès privilégié ou hostPath.

Proposer le minimum de permissions nécessaire et tester les appels requis avec une identité dédiée. Une interdiction globale non testée peut casser l’application ; aucune modification de droits ne doit être appliquée automatiquement.

Vérifier les NetworkPolicies ingress et egress avec les labels, namespaces et capacités du CNI. Un manifeste de policy présent ne prouve pas que le trafic interdit est effectivement bloqué.
