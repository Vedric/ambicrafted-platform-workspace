# Plateforme AI

## Machine
WSL2 Ubuntu sur Windows, RTX 5090 32 Go (budget utile ~30 Go), 110 Go RAM VM.
Travailler exclusivement dans ~/, jamais dans /mnt/c (I/O très lentes).

## Architecture
- Passerelle LiteLLM : http://localhost:4000/v1 (compose dans ~/platform/workspace/gateway)
- Alias : smart, balanced, fast, local, local-embed
- Ollama : http://172.17.0.1:11434 (bridge Docker, PAS localhost)
- Modèles locaux : coder (qwen3.6:27b ctx 64k), qwen2.5-coder:1.5b-base, nomic-embed-text
- Débit mesuré coder : ~67 t/s génération, ~510 t/s prompt eval à chaud

## Règles non négociables
1. Le code ne référence JAMAIS un nom de modèle fournisseur. Uniquement les alias.
2. Aucune donnée client (log, config, code de mission) ne part vers la frontière.
   Ces charges utilisent l'alias "local" via la clé virtuelle "confidential-only".
3. Python géré par uv exclusivement. Jamais pip global.
4. Tout secret dans .env chargé par direnv. Aucun secret en dur, même en exemple.
5. Toute décision d'architecture donne lieu à un ADR dans docs/adr/.
6. Conventional Commits.
7. Toute image de conteneur et toute dépendance est épinglée. Jamais un tag
   mouvant (:latest, main-stable). Épingler ce qui tourne, vérifié sur
   l'instance en service, pas ce que le registre propose sous un nom voisin.
8. Un secret ne s'affiche jamais, même pour le vérifier : pas de cat/grep/echo
   sur un .env, pas de docker inspect, pas de compose config sans --quiet, pas
   de env/printenv. Vérifier par longueur ou préfixe (12 car.). La sortie d'une
   commande est une fuite au même titre qu'un fichier (ADR 0007).

## Commandes utiles
- Passerelle : cd ~/platform/workspace/gateway && docker compose ps / logs litellm
- Modèles chargés : ollama ps
- Dépense : http://localhost:4000/ui

## Ce qu'il ne faut PAS faire
- Jamais `wsl --shutdown` (tuerait la session)
- Jamais de driver NVIDIA dans WSL
- Jamais redéfinir OLLAMA_MODELS vers le home (crash-loop permission denied)
- Sur `Start request repeated too quickly` : reset-failed AVANT tout diagnostic
