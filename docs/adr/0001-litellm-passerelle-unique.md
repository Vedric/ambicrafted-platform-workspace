# ADR 0001 : LiteLLM comme passerelle unique

Statut : accepté, en production locale depuis le 24/08/2026
Date : 2026-08-24

## Contexte
Quatre abonnements (sièges humains, non intégrables) et une enveloppe
de crédits API Anthropic. Besoin d'un point unique pour le routage,
le suivi de coût et le cloisonnement des données de mission
(clients banque/énergie/défense).

## Décision
LiteLLM en compose (avec Postgres), endpoint compatible OpenAI sur
127.0.0.1:4000. Alias sémantiques (smart/balanced/fast/local/local-embed).
Clés virtuelles par consommateur, dont "confidential-only" restreinte
à local + local-embed. Aucun fallback depuis "local".
Subnet compose fixé à 172.28.0.0/24 (choisi hors des plages
occupées, vérifié via ip route).

## Alternatives écartées
- Appels directs par fournisseur : pas de vue coût, cloisonnement
  déclaratif seulement, changement de modèle intrusif.
- OpenRouter : n'intègre pas le modèle local, intermédiaire de plus
  sur la donnée.

## Conséquences
+ Changement de modèle = une ligne de YAML
+ Cloisonnement vérifié par test négatif le 24/08 :
  "key not allowed to access model" sur tentative local -> smart
+ Dépense traçable par clé dans Postgres
- Un service de plus à opérer (accepté sur un poste de travail)
- Coûts des modèles à déclarer dans model_info pour un suivi exact
