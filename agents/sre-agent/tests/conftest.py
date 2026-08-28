"""The guardrail tests run on an unplugged machine.

Tracing is switched off here rather than in each test: an exporter looking
for an absent collector turns a test failure into a timeout wait, and
muddies the reading of the result.
"""

import os

os.environ.setdefault("SRE_TRACAGE", "0")
