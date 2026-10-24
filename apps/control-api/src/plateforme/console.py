"""Public build assets with bounded HTTP caching and a revalidated SPA entry."""

import re
from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

# Vite's pinned build uses an eight-character content hash. Unversioned media,
# HTML and future filename formats must revalidate instead of becoming immutable.
VERSIONNE = re.compile(r"assets/[^/]+-[A-Za-z0-9_-]{8}\.(?:js|css|woff2)")


class ConsoleStatique(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(
                404,
                "Route inconnue.",
                headers={"Cache-Control": "no-store"} if path == "api" else None,
            )
        cible = path or "index.html"
        try:
            response = await super().get_response(cible, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            # A missing chunk or media file is an actual 404. Returning index.html
            # hides deployment errors and gives modules an invalid content type.
            if cible != "index.html" and (
                PurePosixPath(cible).suffix
                or cible.split("/", 1)[0]
                in {
                    "assets",
                    "audio",
                    "guides",
                    "notices",
                }
            ):
                raise HTTPException(
                    404, "Fichier introuvable.", headers={"Cache-Control": "no-store"}
                ) from None
            cible = "index.html"
            try:
                response = await super().get_response(cible, scope)
            except HTTPException as absent:
                if absent.status_code != 404:
                    raise
                return JSONResponse(
                    {
                        "message": "Construire la console avec npm ci puis npm run build dans apps/console."
                    },
                    status_code=503,
                    headers={"Cache-Control": "no-store"},
                )
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if VERSIONNE.fullmatch(cible) else "no-cache"
        )
        return response
