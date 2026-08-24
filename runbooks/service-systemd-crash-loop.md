# Service systemd en crash-loop

## Symptômes
- `systemctl status` : activating/failed en boucle
- "Start request repeated too quickly" dans journalctl

## Diagnostic
1. TOUJOURS `systemctl reset-failed <service>` d'abord : ce message
   masque la cause réelle, il dit seulement que systemd a renoncé
2. `journalctl -u <service>` filtré sur error|fatal|denied
3. Vérifier les overrides : `systemctl cat <service>`

## Causes fréquentes
- Chemin inaccessible pour l'utilisateur du service (permission denied)
- Variable d'environnement pointant vers une ressource absente
- Bind sur une adresse qui n'existe pas encore (ordre de démarrage)

## Remédiation
1. Corriger l'override (`systemctl edit`), jamais le fichier d'origine
2. daemon-reload, reset-failed, restart, puis vérifier l'écoute (ss -tlnp)
