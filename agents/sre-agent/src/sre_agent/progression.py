"""Optional content-free progress events for the local control plane."""

import json
import os
import sys


def signaler(stade: str) -> None:
    if os.environ.get("SRE_PROGRESS") == "1":
        print("SRE_EVENT " + json.dumps({"stade": stade}), file=sys.stderr, flush=True)
