"""Declare the tested filelock contract of this local LiteLLM derivative.

This changes one dependency constraint, not filelock's version or source. The
official 4.2.4 wheel includes the ReadWriteLock security correction. See ADR 0055.
"""

import base64
import csv
import hashlib
import io
import json
import sysconfig
from pathlib import Path

DIST = "litellm-1.104.4.dist-info"
METADATA_SHA256 = "28167051fe39c630f3d97fe854f25718299516818e915e539c5c199760b71477"
RECORD_SHA256 = "5915180ab234d80209c32f38dcaa5473e40acefa4fa133156be1d631b4631a27"
CONSUMERS = {
    "litellm/proxy/client/cli/commands/claude_settings.py": "e53e198ae1fffb0350f128a83c1779534866bdc328c73b638a8f75eed3af16d8",
    "huggingface_hub/utils/_fixes.py": "8d32b554b99cd190bd44e4978caa0be45ea4399141cb38ab45621d5f18417d65",
    "huggingface_hub/utils/_shared_blobs.py": "00277be9150b5c4268a7675f6f5ae8bf277cb50174f68a0c23a72764dba4055f",
}
BEFORE = b"Requires-Dist: filelock>=3.16.1,<4.0\n"
AFTER = b"Requires-Dist: filelock==4.2.4\n"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def preparer(site: Path) -> dict[str, bytes]:
    """Refuse an unreviewed base before any installed bytes are changed."""
    attendus = {**CONSUMERS, f"{DIST}/METADATA": METADATA_SHA256, f"{DIST}/RECORD": RECORD_SHA256}
    for nom, attendu in attendus.items():
        if digest((site / nom).read_bytes()) != attendu:
            raise ValueError("Unreviewed filelock consumer or metadata: " + nom)
    original = (site / DIST / "METADATA").read_bytes()
    if original.count(BEFORE) != 1:
        raise ValueError("Unexpected filelock constraint")
    metadata = original.replace(BEFORE, AFTER, 1)
    lignes = list(csv.reader(io.StringIO((site / DIST / "RECORD").read_text())))
    entrees = [ligne for ligne in lignes if ligne[0] == f"{DIST}/METADATA"]
    if len(entrees) != 1:
        raise ValueError("Missing or duplicated metadata RECORD entry")
    empreinte = base64.urlsafe_b64encode(hashlib.sha256(metadata).digest()).rstrip(b"=")
    entrees[0][1:] = ["sha256=" + empreinte.decode(), str(len(metadata))]
    sortie = io.StringIO(newline="")
    csv.writer(sortie, lineterminator="\n").writerows(lignes)
    return {f"{DIST}/METADATA": metadata, f"{DIST}/RECORD": sortie.getvalue().encode()}


if __name__ == "__main__":
    site = Path(sysconfig.get_path("purelib"))
    changements = preparer(site)
    for nom, contenu in changements.items():
        (site / nom).write_bytes(contenu)
    rapport = Path("/usr/share/ambicrafted/filelock-contract.json")
    rapport.parent.mkdir(parents=True, exist_ok=True)
    rapport.write_text(
        json.dumps(
            {
                "advisory": "CVE-2026-112940",
                "local_derivative_contract_not_upstream_support": True,
                "installed_filelock": "4.2.4",
                "upstream_litellm_constraint": BEFORE.decode().strip(),
                "qualified_local_constraint": AFTER.decode().strip(),
                "consumers_unchanged_sha256": CONSUMERS,
                "metadata_before_sha256": METADATA_SHA256,
                "record_before_sha256": RECORD_SHA256,
                "after_sha256": {nom: digest(contenu) for nom, contenu in changements.items()},
            },
            indent=2,
        )
        + "\n"
    )
