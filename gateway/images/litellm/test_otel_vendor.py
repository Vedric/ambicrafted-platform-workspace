"""Run the retained vendor contract plus all four tests introduced by its fix.

The full 1.33.1 suites are unchanged. Only tests introduced by the security
commit are taken from 1.45.1: unrelated later API behavior is not backported.
All four source fixtures are downloaded with exact SHA-256 in the Dockerfile.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


def load(name):
    path = Path(__file__).parent / "vendor-tests" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    suite = unittest.TestSuite()
    for name in ("test_tracestate_baseline", "test_tracecontext_baseline"):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(load(name)))
    regressions = {
        "test_tracestate_upstream": (
            "test_tracestate_from_header_optional_whitespace",
            "test_tracestate_from_header_long_whitespace_run",
        ),
        "test_tracecontext_upstream": (
            "test_tracestate_header_exceeds_maximum_length",
            "test_tracestate_header_at_maximum_length",
        ),
    }
    for module_name, methods in regressions.items():
        case = load(module_name).TestTraceContextFormat
        for method in methods:
            suite.addTest(case(method))
    raise SystemExit(
        not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    )
