"""Install the dedicated local memory instance without printing or accepting secrets in argv."""

import asyncio
import json
import secrets
import subprocess
import time

from plateforme.config import Parametres, enregistrer_secret, lire_environnement
from plateforme.memoire import Memoire


async def main():
    p = Parametres.charger(lecture_seule=True)
    if not lire_environnement(p.racine).get("NEO4J_MEMORY_PASSWORD"):
        enregistrer_secret(p.racine, "NEO4J_MEMORY_PASSWORD", secrets.token_urlsafe(48))
    command = [
        "docker",
        "compose",
        "--env-file",
        str(p.racine / ".env"),
        "-f",
        str(p.racine / "gateway/neo4j-memory.yml"),
    ]
    for options in (["config", "--quiet"], ["up", "-d", "--wait", "--wait-timeout", "150"]):
        result = await asyncio.to_thread(
            subprocess.run, [*command, *options], capture_output=True, timeout=240, check=False
        )
        if result.returncode:
            raise SystemExit(
                "Memory installation failed. Check Docker and the dedicated service logs; credentials were not printed."
            )
    memory = Memoire(p)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if (await memory.statut())["ready"]:
            await memory.initialiser()
            print(
                json.dumps(
                    {
                        "ready": True,
                        "backend": "neo4j",
                        "scope": "dedicated platform instance",
                        "http": "http://127.0.0.1:47474",
                        "bolt_exposed": False,
                    }
                )
            )
            return
        await asyncio.sleep(1)
    raise SystemExit(
        "Memory started but authenticated readiness failed. Existing credentials were preserved."
    )


if __name__ == "__main__":
    asyncio.run(main())
