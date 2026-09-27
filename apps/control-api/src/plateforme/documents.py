"""Bounded document extraction in a disposable process, never in the API worker."""

import asyncio
import base64
import binascii
import json
import os
import sys
from pathlib import PurePath

from fastapi import HTTPException

MAX_FILE = 8 * 1024 * 1024
EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".log",
    ".py",
    ".ts",
    ".tf",
    ".sh",
    ".xml",
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


def valider(nom: str, contenu: str) -> tuple[str, bytes]:
    if (
        not nom
        or len(nom) > 160
        or any(c in nom for c in "/\\:\x00")
        or any(ord(c) < 32 for c in nom)
    ):
        raise HTTPException(422, "Invalid attachment name.")
    extension = PurePath(nom).suffix.lower()
    if extension not in EXTENSIONS:
        raise HTTPException(
            415,
            "Unsupported attachment format. Use text, PDF, DOCX, XLSX, PPTX, PNG, JPEG or WebP.",
        )
    if len(contenu) > (MAX_FILE + 2) // 3 * 4:
        raise HTTPException(413, "Attachments are limited to 8 MiB each.")
    try:
        donnees = base64.b64decode(contenu, validate=True)
    except ValueError, binascii.Error:
        raise HTTPException(422, "Invalid attachment encoding.") from None
    if not donnees or len(donnees) > MAX_FILE:
        raise HTTPException(413, "Attachments must contain between 1 byte and 8 MiB.")
    return extension, donnees


async def extraire(nom: str, contenu: str) -> dict:
    extension, donnees = valider(nom, contenu)
    processus = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "plateforme.document_worker",
        extension,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "LANG", "SYSTEMROOT"}
        },
        limit=2_000_000,
    )
    try:
        sortie, _ = await asyncio.wait_for(processus.communicate(donnees), timeout=20)
        if processus.returncode or len(sortie) > 2_000_000:
            raise HTTPException(
                422,
                "The document could not be read within the safety limits. Use a smaller, unencrypted file. For scanned PDFs, attach the relevant pages as images.",
            )
        resultat = json.loads(sortie)
        if not isinstance(resultat, dict) or resultat.get("kind") not in {"text", "image"}:
            raise ValueError("Invalid worker result")
        if (
            type(resultat.get("truncated")) is not bool
            or not isinstance(resultat.get("text"), str)
            or len(resultat["text"]) > 16_000
        ):
            raise ValueError("Invalid worker metadata")
        if resultat["kind"] == "image":
            if not isinstance(resultat.get("image"), str) or len(resultat["image"]) > 1_333_336:
                raise ValueError("Invalid normalized image")
            for dimension in ("width", "height"):
                if type(resultat.get(dimension)) is not int or not 1 <= resultat[dimension] <= 1600:
                    raise ValueError("Invalid image dimensions")
        return resultat
    except TimeoutError:
        raise HTTPException(
            422, "Document processing exceeded its time limit. Try a smaller file."
        ) from None
    except ValueError, TypeError, KeyError:
        raise HTTPException(422, "Document processing returned an invalid result.") from None
    finally:
        if processus.returncode is None:
            processus.kill()
        await processus.wait()
