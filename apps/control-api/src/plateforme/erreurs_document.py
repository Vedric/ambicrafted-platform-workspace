"""Finite document failure categories; never expose exception or source text."""

from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum

import httpx


class CodeErreurDocument(StrEnum):
    SORTIE_INVALIDE = "document_output_invalid"
    REVUE_INVALIDE = "document_review_invalid"
    REVUE_REFUSEE = "document_review_rejected"
    DELAI = "document_timeout"
    AMONT = "document_upstream"
    STOCKAGE = "document_storage"
    INCONNUE = "document_unknown"


class ErreurDocument(ValueError):
    def __init__(self, code: CodeErreurDocument):
        self.code = CodeErreurDocument(code)
        super().__init__(self.code.value)


@contextmanager
def sortie_document(code: CodeErreurDocument) -> Iterator[None]:
    """Classify parsing/validation failures only within the named output boundary."""
    try:
        yield
    except ErreurDocument:
        raise
    except ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError:
        raise ErreurDocument(code) from None


def categorie_erreur_document(error: BaseException) -> CodeErreurDocument:
    """Exception types establish categories; arbitrary exception prose never does."""
    if isinstance(error, ErreurDocument):
        return error.code
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return CodeErreurDocument.DELAI
    if isinstance(error, httpx.HTTPError):
        return CodeErreurDocument.AMONT
    return CodeErreurDocument.INCONNUE
