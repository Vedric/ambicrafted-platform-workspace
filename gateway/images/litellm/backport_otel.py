"""Apply the upstream CVE-2026-114603 fix to the exact pinned OTel sources.

The API/SDK cohort and distribution version remain 1.33.1. The raw advisory
therefore remains visible to inventory scanners. Only two source files and
their truthful RECORD hashes change; this is not an upstream 1.45.1 package.
See OpenTelemetry commit d5224bf4ffdf2aee1b592ad238dcc32ca957f26b.
"""

import base64
import csv
import hashlib
import io
import json
import sysconfig
from pathlib import Path

COMMIT = "d5224bf4ffdf2aee1b592ad238dcc32ca957f26b"
DIST = "opentelemetry_api-1.33.1.dist-info"
EXPECTED = {
    "opentelemetry/trace/span.py": (
        "4c4f4530b66a16d416060ad170e5c1c43063b3ea51be5c88cd7d90a2b40ed112",
        "b83613cfa28313aa7a5b8ddf03c2e438d466100a24e3acb2eb950d9416ede9dd",
    ),
    "opentelemetry/trace/propagation/tracecontext.py": (
        "7a7aeff08f7de76f6c41cbe892c72a7d9c98fd9e866e5815debd96fab8f12d30",
        "53c91c6e857f4dc4052297a36717003d45a7d80f663905ccc919c9a093672d42",
    ),
}
METADATA_SHA256 = "4a8e5f53d93e18d78b92fc70d792b39d61fd0a65507ae393052fb50b2857c434"
RECORD_SHA256 = "f654200db4242487b9c41360c14961ce3cfe7c01e9eadc54d61b7cb695dbff40"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_once(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise ValueError("Unexpected source context; refusing the backport")
    return source.replace(before, after, 1)


def corrected(relative: str, source: bytes) -> bytes:
    text = source.decode("utf-8")
    text = replace_once(
        text,
        "import re\n",
        "# Local CVE-2026-114603 backport; upstream commit "
        + COMMIT
        + ".\nimport re\n",
    )
    if relative == "opentelemetry/trace/span.py":
        text = replace_once(
            text,
            '_delimiter_pattern = re.compile(r"[ \\t]*,[ \\t]*")\n'
            '_member_pattern = re.compile(f"({_KEY_FORMAT})(=)({_VALUE_FORMAT})[ \\t]*")',
            "_TRACECONTEXT_MAXIMUM_TRACESTATE_LENGTH = 8192\n"
            '_member_pattern = re.compile(f"({_KEY_FORMAT})=({_VALUE_FORMAT})")',
        )
        text = replace_once(
            text,
            "            members: typing.List[str] = re.split(_delimiter_pattern, header)\n"
            "            for member in members:\n",
            '            for member in header.split(","):\n'
            "                # remove optional whitespace (RFC 9110, section 5.6.3)\n"
            '                member = member.strip(" \\t")\n',
        )
        text = replace_once(
            text,
            "                groups: typing.Tuple[str, ...] = match.groups()\n"
            "                key, _eq, value = groups",
            "                key, value = match.groups()",
        )
    elif relative == "opentelemetry/trace/propagation/tracecontext.py":
        text = replace_once(text, "import re\n", "import logging\nimport re\n")
        text = replace_once(
            text,
            "from opentelemetry.trace.span import TraceState\n",
            "from opentelemetry.trace.span import (\n"
            "    _TRACECONTEXT_MAXIMUM_TRACESTATE_LENGTH,\n"
            "    TraceState,\n"
            ")\n\n_logger = logging.getLogger(__name__)\n",
        )
        text = replace_once(
            text,
            "        if tracestate_headers is None:\n            tracestate = None\n"
            "        else:\n            tracestate = TraceState.from_header(tracestate_headers)",
            "        if tracestate_headers is None:\n            tracestate = None\n"
            "        elif (\n"
            '            # multiple header fields are combined with "," (RFC 9110, section 5.3)\n'
            "            sum(len(header) for header in tracestate_headers) + len(tracestate_headers) - 1\n"
            "            > _TRACECONTEXT_MAXIMUM_TRACESTATE_LENGTH\n"
            "        ):\n"
            "            _logger.warning(\n"
            '                "tracestate header exceeded the maximum length of %d characters",\n'
            "                _TRACECONTEXT_MAXIMUM_TRACESTATE_LENGTH,\n"
            "            )\n"
            "            tracestate = None\n"
            "        else:\n            tracestate = TraceState.from_header(tracestate_headers)",
        )
    else:
        raise ValueError("Unsupported source path")
    return text.encode("utf-8")


def prepare(site: Path) -> dict[str, bytes]:
    """Validate every input and result before any installed file is written."""
    if digest((site / DIST / "METADATA").read_bytes()) != METADATA_SHA256:
        raise ValueError("Unexpected API distribution metadata")
    record = (site / DIST / "RECORD").read_bytes()
    if digest(record) != RECORD_SHA256:
        raise ValueError("Unexpected API distribution RECORD")
    outputs = {}
    for relative, (before, after) in EXPECTED.items():
        original = (site / relative).read_bytes()
        if digest(original) != before:
            raise ValueError("Unexpected installed source: " + relative)
        updated = corrected(relative, original)
        if digest(updated) != after:
            raise ValueError("Unexpected backported source: " + relative)
        outputs[relative] = updated
    rows = list(csv.reader(io.StringIO(record.decode("utf-8"))))
    found = set()
    for row in rows:
        if row[0] in outputs:
            if row[0] in found:
                raise ValueError("Duplicate RECORD source entry")
            found.add(row[0])
            data = outputs[row[0]]
            checksum = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(
                b"="
            )
            row[1:] = ["sha256=" + checksum.decode("ascii"), str(len(data))]
    if found != set(outputs):
        raise ValueError("Missing RECORD source entry")
    destination = io.StringIO(newline="")
    csv.writer(destination, lineterminator="\n").writerows(rows)
    outputs[DIST + "/RECORD"] = destination.getvalue().encode("utf-8")
    return outputs


def apply(site: Path) -> dict:
    outputs = prepare(site)
    for relative, data in outputs.items():
        (site / relative).write_bytes(data)
    for relative in EXPECTED:
        source = site / relative
        for bytecode in (source.parent / "__pycache__").glob(source.stem + ".*.pyc"):
            bytecode.unlink()
    return {
        "advisory": "CVE-2026-114603",
        "upstream_commit": COMMIT,
        "installed_distribution_version": "1.33.1",
        "source_backport_not_upstream_release": True,
        "metadata_unchanged_sha256": METADATA_SHA256,
        "record_before_sha256": RECORD_SHA256,
        "record_after_sha256": digest(outputs[DIST + "/RECORD"]),
        "sources": {
            name: {"before_sha256": hashes[0], "after_sha256": hashes[1]}
            for name, hashes in EXPECTED.items()
        },
    }


if __name__ == "__main__":
    result = apply(Path(sysconfig.get_path("purelib")))
    report = Path("/usr/share/ambicrafted/otel-tracestate-backport.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
