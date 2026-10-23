"""Build-only boundary checks supplementing the unmodified vendor test suite."""

import importlib.metadata
import json
import shutil
import sys
import sysconfig
import tempfile
import time
import unittest
from pathlib import Path

import backport_otel


class OriginalSourceGuards(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.site = Path(self.directory.name)
        installed = Path(sysconfig.get_path("purelib"))
        for name in [
            *backport_otel.EXPECTED,
            backport_otel.DIST + "/METADATA",
            backport_otel.DIST + "/RECORD",
        ]:
            destination = self.site / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(installed / name, destination)

    def snapshot(self):
        return {
            str(path.relative_to(self.site)): path.read_bytes()
            for path in self.site.rglob("*")
            if path.is_file()
        }

    def test_validated_sources_have_exact_expected_outputs(self):
        outputs = backport_otel.prepare(self.site)
        self.assertEqual(len(outputs), 3)
        for relative, (_, expected) in backport_otel.EXPECTED.items():
            self.assertEqual(backport_otel.digest(outputs[relative]), expected)

    def test_modified_source_rejected_before_any_write(self):
        for relative in backport_otel.EXPECTED:
            with self.subTest(relative=relative):
                source = self.site / relative
                original = source.read_bytes()
                source.write_bytes(original + b"\n# unexpected content\n")
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, "Unexpected installed source"):
                    backport_otel.apply(self.site)
                self.assertEqual(before, self.snapshot())
                source.write_bytes(original)

    def test_changed_distribution_metadata_rejected_before_any_write(self):
        metadata = self.site / backport_otel.DIST / "METADATA"
        metadata.write_bytes(metadata.read_bytes().replace(b"1.33.1", b"1.45.1"))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "distribution metadata"):
            backport_otel.apply(self.site)
        self.assertEqual(before, self.snapshot())

    def test_changed_record_rejected_before_any_write(self):
        record = self.site / backport_otel.DIST / "RECORD"
        record.write_bytes(record.read_bytes() + b"unexpected,,\n")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "distribution RECORD"):
            backport_otel.apply(self.site)
        self.assertEqual(before, self.snapshot())


class QualifiedRuntime(unittest.TestCase):
    def test_cohort_and_litellm_metadata_are_unchanged(self):
        versions = {
            "litellm": "1.104.4",
            "opentelemetry-api": "1.33.1",
            "opentelemetry-sdk": "1.33.1",
            "opentelemetry-exporter-otlp": "1.33.1",
            "opentelemetry-exporter-otlp-proto-common": "1.33.1",
            "opentelemetry-exporter-otlp-proto-grpc": "1.33.1",
            "opentelemetry-exporter-otlp-proto-http": "1.33.1",
            "opentelemetry-proto": "1.33.1",
            "opentelemetry-instrumentation": "0.54b1",
            "opentelemetry-instrumentation-asgi": "0.54b1",
            "opentelemetry-instrumentation-fastapi": "0.54b1",
            "opentelemetry-semantic-conventions": "0.54b1",
            "opentelemetry-util-http": "0.54b1",
        }
        for name, expected in versions.items():
            with self.subTest(package=name):
                self.assertEqual(importlib.metadata.version(name), expected)
        installed = Path(sysconfig.get_path("purelib"))
        metadata = installed / backport_otel.DIST / "METADATA"
        self.assertEqual(
            backport_otel.digest(metadata.read_bytes()), backport_otel.METADATA_SHA256
        )
        litellm_metadata = installed / "litellm-1.104.4.dist-info/METADATA"
        self.assertEqual(
            backport_otel.digest(litellm_metadata.read_bytes()),
            "28167051fe39c630f3d97fe854f25718299516818e915e539c5c199760b71477",
        )
        self.assertIn(
            "opentelemetry-api==1.33.1",
            importlib.metadata.requires("opentelemetry-sdk"),
        )

    def test_installed_sources_and_record_describe_the_backport(self):
        installed = Path(sysconfig.get_path("purelib"))
        distribution = importlib.metadata.distribution("opentelemetry-api")
        entries = {str(item): item for item in distribution.files}
        for name, (_, expected) in backport_otel.EXPECTED.items():
            with self.subTest(path=name):
                data = (installed / name).read_bytes()
                self.assertEqual(backport_otel.digest(data), expected)
                self.assertEqual(entries[name].size, len(data))
                encoded = (
                    backport_otel.base64.urlsafe_b64encode(
                        backport_otel.hashlib.sha256(data).digest()
                    )
                    .rstrip(b"=")
                    .decode("ascii")
                )
                self.assertEqual(entries[name].hash.value, encoded)
        report = json.loads(
            Path("/usr/share/ambicrafted/otel-tracestate-backport.json").read_text()
        )
        self.assertTrue(report["source_backport_not_upstream_release"])
        self.assertEqual(report["installed_distribution_version"], "1.33.1")

    def test_actual_litellm_callback_preserves_parent_and_bounds_tracestate(self):
        from litellm.integrations.opentelemetry import OpenTelemetry
        from opentelemetry import trace

        # This method has no instance state. Avoid initializing exporters here;
        # a separate service qualifier checks actual OTLP delivery to Tempo.
        callback = OpenTelemetry.__new__(OpenTelemetry)
        parent = "00-12345678901234567890123456789012-1234567890123456-01"
        for value, expected in [
            ("foo=1,bar=2", {"foo": "1", "bar": "2"}),
            ("foo=1" + " " * 8187, {"foo": "1"}),
            ("foo=1" + " " * 8188, {}),
            ("a=b" + "\t" * 100_000 + "x", {}),
        ]:
            with self.subTest(length=len(value)):
                start = time.perf_counter()
                context = callback.get_traceparent_from_header(
                    {"traceparent": parent, "tracestate": value}
                )
                elapsed = time.perf_counter() - start
                span = trace.get_current_span(context).get_span_context()
                self.assertEqual(span.trace_id, int(parent.split("-")[1], 16))
                self.assertEqual(span.span_id, int(parent.split("-")[2], 16))
                self.assertEqual(dict(span.trace_state), expected)
                self.assertLess(elapsed, 1)


if __name__ == "__main__":
    mode = sys.argv.pop(1)
    if mode not in {"--preflight", "--qualified"}:
        raise SystemExit("Expected --preflight or --qualified")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        OriginalSourceGuards if mode == "--preflight" else QualifiedRuntime
    )
    raise SystemExit(
        not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    )
