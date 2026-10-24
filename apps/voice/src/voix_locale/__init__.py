"""Bounded offline speech engines; no conversational decisions or tool execution."""

import os

# ONNX Runtime 1DS can initialize through Piper's imports. The native opt-out
# must precede those imports; the later disable-events API is not sufficient.
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

__version__ = "0.3.3"
