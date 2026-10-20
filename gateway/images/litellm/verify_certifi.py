"""Verify the installed upstream CA bundle, not only its package version.

GHSA-6q48-6c7w-9gw2 removes the emSign ECC G3 trust anchor. The unaffected
emSign roots restored in certifi 2026.10.19 must remain available. No trust
store is edited here; the whole installed PEM must match the official wheel.
"""

import hashlib
import json
import ssl
from pathlib import Path

import certifi

EXPECTED_BUNDLE = "50f79f98dac192b20dbf73f35c56f0b0c557ab267ff5199d1117cc1180b70785"
REMOVED_ROOT = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
RETAINED_ROOTS = {
    "40f6af0346a99aa1cd1d555a4e9cce62c7f9634603ee406615833dc8c8d00367",
    "125609aa301da0a249b97a8239cb6a34216f44dcac9f3954b14292f2e8c8608f",
    "bc4d809b15189d78db3e1d8cf4f9726a795da1643ca5f1358e1ddb0edc0d7eb3",
}


def verify() -> dict:
    bundle = Path(certifi.where()).read_bytes()
    bundle_hash = hashlib.sha256(bundle).hexdigest()
    if certifi.__version__ != "2026.10.19" or bundle_hash != EXPECTED_BUNDLE:
        raise RuntimeError("Installed certifi is not the qualified upstream bundle")
    context = ssl.create_default_context(cafile=certifi.where())
    anchors = {
        hashlib.sha256(certificate).hexdigest()
        for certificate in context.get_ca_certs(binary_form=True)
    }
    if REMOVED_ROOT in anchors or not RETAINED_ROOTS.issubset(anchors):
        raise RuntimeError("Installed OpenSSL trust anchors violate the CA fix")
    return {
        "certifi": certifi.__version__,
        "bundle_sha256": bundle_hash,
        "removed_root_trusted": False,
        "unaffected_emsign_roots_trusted": len(RETAINED_ROOTS),
        "trust_anchors": len(anchors),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
