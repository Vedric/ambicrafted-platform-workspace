"""Verify the signed Wolfi update and the actual default OpenSSL trust store.

The native package is installed through the authenticated Wolfi APK index.
The expected bundle is taken from ca-certificates-bundle 20260909-r3; no
locally edited package inventory or replacement certificate bytes are accepted.
"""

import hashlib
import json
import ssl
from pathlib import Path

EXPECTED_VERSION = "20260909-r3"
EXPECTED_BUNDLE = "5961c0a3c65459931c023e0075c09733f09aea4ca439cb85bc4a08bb4f3f568b"
REMOVED_ROOT = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"


def verify() -> dict:
    inventory = Path("/lib/apk/db/installed").read_text()
    matches = [
        block
        for block in inventory.split("\n\n")
        if "P:ca-certificates-bundle" in block.splitlines()
    ]
    if len(matches) != 1 or f"V:{EXPECTED_VERSION}" not in matches[0].splitlines():
        raise RuntimeError("The qualified native CA package is not installed")
    bundle = Path("/etc/ssl/certs/ca-certificates.crt")
    bundle_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
    if bundle_hash != EXPECTED_BUNDLE:
        raise RuntimeError("Native CA bundle differs from the qualified Wolfi package")
    supplied = ssl.create_default_context(cafile=str(bundle))
    default = ssl.create_default_context()
    anchors = {
        hashlib.sha256(certificate).hexdigest()
        for certificate in supplied.get_ca_certs(binary_form=True)
    }
    default_anchors = {
        hashlib.sha256(certificate).hexdigest()
        for certificate in default.get_ca_certs(binary_form=True)
    }
    if len(anchors) != 118 or REMOVED_ROOT in anchors or default_anchors != anchors:
        raise RuntimeError("Effective native trust anchors violate the reviewed update")
    return {
        "ca_certificates_bundle": EXPECTED_VERSION,
        "bundle_sha256": bundle_hash,
        "trust_anchors": len(anchors),
        "default_openssl_store_matches": True,
        "removed_root_trusted": False,
    }


if __name__ == "__main__":
    result = verify()
    output = Path("/usr/share/ambicrafted/native-ca-package.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
