"""Bounded document extraction in a disposable process, never in the API worker."""

import asyncio
import base64
import binascii
import json
from pathlib import PurePath

from fastapi import HTTPException

from .document_sandbox import SandboxUnavailable, commande

MAX_FILE = 8 * 1024 * 1024
MAX_OUTPUT = 2_000_000
PROCESS_TIMEOUT = 20
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


async def _echanger(processus: asyncio.subprocess.Process, donnees: bytes) -> bytes:
    """Drain stdin/stdout concurrently without retaining an unbounded response."""
    assert processus.stdin is not None and processus.stdout is not None

    async def envoyer():
        assert processus.stdin is not None
        try:
            processus.stdin.write(donnees)
            await processus.stdin.drain()
        except BrokenPipeError, ConnectionResetError:
            pass  # The return code describes a worker failing during startup.
        finally:
            processus.stdin.close()

    async def recevoir():
        assert processus.stdout is not None
        sortie = bytearray()
        while morceau := await processus.stdout.read(65536):
            sortie.extend(morceau)
            if len(sortie) > MAX_OUTPUT:
                raise ValueError("Worker output exceeded its limit")
        return bytes(sortie)

    async with asyncio.TaskGroup() as groupe:
        groupe.create_task(envoyer())
        lecture = groupe.create_task(recevoir())
    await processus.wait()
    return lecture.result()


async def _executer(arguments: list[str], donnees: bytes) -> tuple[int, bytes]:
    # Shield startup: cancellation between fork and transport creation must
    # still obtain and terminate the child. bwrap kills its PID namespace when
    # its monitor dies, including descendants of a compromised parser.
    lancement = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *arguments,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env={"LANG": "C.UTF-8"},
            close_fds=True,
            limit=65536,
        )
    )
    processus = None
    try:
        processus = await asyncio.shield(lancement)
        sortie = await _echanger(processus, donnees)
        assert processus.returncode is not None
        return processus.returncode, sortie
    finally:

        async def nettoyer():
            enfant = processus if processus is not None else await lancement
            if enfant.returncode is None:
                try:
                    enfant.kill()
                except ProcessLookupError:
                    pass
            # Resume a flow-controlled stdout after output overflow. Waiting
            # without draining can otherwise deadlock even after SIGKILL.
            if enfant.stdout is not None:
                while await enfant.stdout.read(65536):
                    pass
            await enfant.wait()

        # A second cancellation (disconnect + shutdown, for example) must not
        # cancel spawn/cleanup and abandon a still-running parser namespace.
        nettoyage = asyncio.create_task(nettoyer())
        annule = False
        while not nettoyage.done():
            try:
                await asyncio.shield(nettoyage)
            except asyncio.CancelledError:
                annule = True
        nettoyage.result()
        if annule:
            raise asyncio.CancelledError


async def extraire(nom: str, contenu: str) -> dict:
    # The authenticated upload router admits one extraction across all
    # conversations, with immediate 409 rejection instead of an unbounded queue.
    extension, donnees = valider(nom, contenu)
    try:
        async with asyncio.timeout(PROCESS_TIMEOUT):
            code, sortie = await _executer(commande(extension), donnees)
        if code in {1, 78}:  # bwrap startup error / missing kernel seccomp boundary.
            raise SandboxUnavailable("The document sandbox could not be established")
        if code:
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
    except SandboxUnavailable, OSError:
        raise HTTPException(
            503,
            "Secure document processing is unavailable. Check the Linux bubblewrap, libseccomp and namespace prerequisites.",
        ) from None
    except ExceptionGroup:
        raise HTTPException(422, "Document processing exceeded its output limit.") from None
    except ValueError, TypeError, KeyError:
        raise HTTPException(422, "Document processing returned an invalid result.") from None
