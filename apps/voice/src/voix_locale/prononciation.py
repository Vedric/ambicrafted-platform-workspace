"""Speech-only, trusted IPA lexicon; written answers are never rewritten.

Trusted [[IPA]] blocks are consumed by the local phoneme pipeline. Keep the same
speaker and sentence prosody instead of joining recordings in different voices. English IPA is
derived from the pinned eSpeak phonemizer, with explicit acronym/brand corrections.
An inventory match prevents a different installed voice silently dropping sounds.
"""

import re
import unicodedata
from collections.abc import Collection

LEXIQUE = {
    "GitHub": "ɡˈɪthʌb",
    "GitLab": "ɡˈɪtlæb",
    "Git": "ɡˈɪt",
    "Enterprise": "ˈɛntɚpɹˌaɪz",
    "Kubernetes": "kˌuːbɚnˈɛtiːz",
    "Docker": "dˈɑːkɚ",
    "Terraform": "tˈɛɹɐfˌɔːɹm",
    "Ansible": "ˈænsᵻbəl",
    "Helm": "hˈɛlm",
    "runbook": "ɹˈʌnbʊk",
    "runbooks": "ɹˈʌnbʊks",
    "workflow": "wˈɜːkfloʊ",
    "workflows": "wˈɜːkfloʊz",
    "DevOps": "dˈɛvɑːps",
    "DevSecOps": "dˌɛvsɛkˈɑːps",
    "SRE": "ˌɛs ˌɑːɹ ˈiː",
    "API": "ˌeɪ pˌiː ˈaɪ",
    "MCP": "ˌɛm sˌiː pˈiː",
    "CI/CD": "sˌiː ˌaɪ sˌiː dˈiː",
    "LLM": "ˌɛl ˌɛl ˈɛm",
    "RAG": "ɹˈæɡ",
    "PostgreSQL": "pˈoʊstɡɹɛs kjˌuː ˈɛl",
    "Postgres": "pˈoʊstɡɹɛs",
    "Neo4j": "nˈiːoʊ fˈɔːɹ dʒˈeɪ",
    "Qdrant": "kwˈɑːdɹənt",
    "Nginx": "ˈɛndʒɪn ˌɛks",
    "Prometheus": "pɹoʊmˈiːθiəs",
    "Grafana": "ɡɹæfˈɑːnə",
    "Redis": "ɹˈɛdɪs",
    "OpenTelemetry": "ˈoʊpən təlˈɛmətɹi",
    "TypeScript": "tˈaɪpskɹɪpt",
    "JavaScript": "dʒˈɑːvəskɹɪpt",
    "Python": "pˈaɪθən",
    "Linux": "lˈɪnʊks",
    "Windows": "wˈɪndoʊz",
    "cloud": "klˈaʊd",
    "pull request": "pˈʊl ɹᵻkwˈɛst",
    "dashboard": "dˈæʃbɔːɹd",
    "pipeline": "pˈaɪplaɪn",
    "pipelines": "pˈaɪplaɪnz",
    "rollback": "ɹˈoʊlbæk",
    "checkpoint": "tʃˈɛkpɔɪnt",
    "monitoring": "mˈɑːnɪtɚɪŋ",
    "namespace": "nˈeɪmspeɪs",
    "ingress": "ˈɪŋɡɹɛs",
    "cluster": "klˈʌstɚ",
    "clusters": "klˈʌstɚz",
    "container": "kəntˈeɪnɚ",
    "containers": "kəntˈeɪnɚz",
    "load balancer": "lˈoʊd bˈælənsɚ",
    "rate limit": "ɹˈeɪt lˈɪmɪt",
    "token": "tˈoʊkən",
    "tokens": "tˈoʊkənz",
    "streaming": "stɹˈiːmɪŋ",
    "serverless": "sˈɜːvɚləs",
    "OAuth": "ˈoʊ ˈɔːθ",
    "OpenID Connect": "ˈoʊpən aɪdˈiː kənˈɛkt",
    "zero trust": "zˈiəɹoʊ tɹˈʌst",
    "backup": "bˈækʌp",
    "backups": "bˈækʌps",
}
_IPA = {cle.casefold(): valeur for cle, valeur in LEXIQUE.items()}
_MOTS = re.compile(
    r"(?<![\w])("
    + "|".join(re.escape(m) for m in sorted(LEXIQUE, key=len, reverse=True))
    + r")(?![\w])",
    re.IGNORECASE,
)
_PRENOM = re.compile(r"\bV[eé]dric\b", re.IGNORECASE)


def preparer_parole(texte: str, langue: str, inventaire: Collection[str]) -> str:
    """Only trusted entries may inject phonemes; unsupported entries stay literal."""
    texte = unicodedata.normalize("NFC", texte)
    # Internal raw blocks are reserved for the trusted lexicon. User text is literal.
    texte = texte.replace("[", "(").replace("]", ")")

    def bloc(ipa: str, original: str) -> str:
        return "[[" + ipa + "]]" if all(p in inventaire for p in ipa) else original

    texte = _MOTS.sub(lambda m: bloc(_IPA[m[0].casefold()], m[0]), texte)
    # Give the name a stable English rendering, instead of an arbitrary spelling guess.
    if langue == "en":
        texte = _PRENOM.sub(lambda m: bloc("vˈɛdɹɪk", m[0]), texte)
    else:
        texte = _PRENOM.sub("Védric", texte)
    # A greeting is one breath group; a comma before the name sounded stilted.
    return re.sub(r"\b(Bonjour|Bonsoir),\s+(Védric)\b", r"\1 \2", texte)
