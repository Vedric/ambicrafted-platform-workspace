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
9. Rien ne s'affirme sur la CI depuis l'arbre de travail. Vérifier dans un
   clone vierge (git clone, commit visé, commandes du travail) ou se taire :
   un .venv déjà construit et un gateway/.env présent mesurent le poste, pas
   le dépôt.
10. Avant de soumettre du code, de créer ou mettre à jour une PR, ou de publier
    une review, challenger le fond autant que la forme, selon les critères
    ci-dessous. Une CI verte et un code bien présenté ne suffisent pas.

## Exigence de fond pour les contributions et les reviews
- Vérifier le besoin réel, les hypothèses et le comportement attendu : la
  solution résout-elle le bon problème pour l'utilisateur ?
- Examiner la conception, les alternatives plus simples et les compromis :
  cohérence avec l'existant, maintenabilité, sécurité, performances et impact
  opérationnel, sans sur-ingénierie.
- Chercher les contre-exemples, les cas limites, les modes de panne et les
  régressions ; vérifier les interactions, pas uniquement le diff isolé.
- Choisir des validations proportionnées au risque, capables de mettre en
  défaut la solution ; confronter les résultats aux exigences réelles, sans
  se contenter de tests qui reproduisent l'implémentation.
- Avant de publier une remarque de review, vérifier sa validité dans le
  contexte et les versions du projet, étayer son impact et distinguer défaut
  avéré, incertitude et préférence. Ne pas inventer de problèmes pour remplir
  une review.
- Relire une dernière fois le résultat et les preuves avant publication :
  corriger les problèmes établis dans le périmètre autorisé, indiquer les
  limites et ne pas présenter une hypothèse ou un contrôle non exécuté comme
  un fait vérifié.

## Commandes utiles
- Passerelle : cd ~/platform/workspace/gateway && docker compose ps / logs litellm
- Modèles chargés : ollama ps
- Dépense : http://localhost:4000/ui

## Ce qu'il ne faut PAS faire
- Jamais `wsl --shutdown` (tuerait la session)
- Jamais de driver NVIDIA dans WSL
- Jamais redéfinir OLLAMA_MODELS vers le home (crash-loop permission denied)
- Sur `Start request repeated too quickly` : reset-failed AVANT tout diagnostic
