"""Stop repeated exploration using only successfully verified source identities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .llm import ErreurPasserelle, extraire_json
from .modeles import Diagnostic

TOURS_SANS_PROGRES = 2
CONCLUSION_BORNEE = (
    "Contrôle de la plateforme : deux tours d'outils n'ont ajouté aucune nouvelle "
    "version de source effectivement lue et vérifiée. La recherche s'arrête ici ; "
    "cela ne prouve ni que les sources sont suffisantes ni qu'elles sont exhaustives. "
    "Produis une seule proposition JSON conforme au schéma, sans outil. Appuie-toi "
    "uniquement sur les observations originales et les sources déjà acquises. "
    "Conserve les hypothèses comme hypothèses ; indique les éléments manquants et "
    "l'impossibilité de conclure si nécessaire. N'invente aucune lecture, preuve, "
    "exécution ni validation. Aucun résultat de revue qualite ne peut être fourni."
)


@dataclass
class ProgressionRecherche:
    """Count tool batches with no new (filename, content hash) pair, once reads exist."""

    empreintes: set[tuple[str, str]] = field(default_factory=set)
    sans_progres: int = 0

    def observer(self, sources: dict[str, str]) -> None:
        actuelles = {
            (nom, hashlib.sha256(texte.encode()).hexdigest()) for nom, texte in sources.items()
        }
        nouvelles = actuelles - self.empreintes
        self.empreintes.update(actuelles)
        if nouvelles:
            self.sans_progres = 0
        elif self.empreintes:
            self.sans_progres += 1

    @property
    def terminee(self) -> bool:
        return bool(self.empreintes) and self.sans_progres >= TOURS_SANS_PROGRES


def schema_finalisation() -> dict[str, Any]:
    """The model may propose a diagnosis, never application-owned review evidence."""
    schema = Diagnostic.model_json_schema()
    schema["properties"].pop("qualite")
    schema["$defs"].pop("QualiteDiagnostic")
    schema["required"] = list(schema["properties"])
    schema["additionalProperties"] = False
    return schema


def lire_finalisation(contenu: str) -> Diagnostic:
    """Reject ignored schemas too; no repair/retry can reopen stopped exploration."""
    donnees = extraire_json(contenu)
    if not isinstance(donnees, dict) or set(donnees) != set(schema_finalisation()["properties"]):
        raise ErreurPasserelle("Finalisation bornée incompatible avec le schéma attendu.")
    return Diagnostic.model_validate(donnees, extra="forbid")
