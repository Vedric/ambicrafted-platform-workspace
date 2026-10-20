"""Network-free tests of image selection, full reporting and failure policy."""

from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import scanner_images as scanner


class ScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.compose = self.root / "docker-compose.yml"
        self.output = self.root / "reports"
        self.cache = self.root / "cache"
        self.text = (
            "name: test\nservices:\n"
            + "".join(
                f"  {service}:\n"
                f"    image: example/{service}:1.0@sha256:{'a' * 64}\n"
                "    environment:\n"
                "      UNREAD_SECRET: ${UNREAD_SECRET:?not available}\n"
                "    env_file: [.env]\n"
                for service in scanner.SERVICES
            )
            + "volumes:\n  ignored:\n"
        )
        self.compose.write_text(self.text, encoding="utf-8")

    def arguments(self) -> list[str]:
        return [
            "--compose",
            str(self.compose),
            "--trivy",
            "/verified/trivy",
            "--output",
            str(self.output),
            "--cache",
            str(self.cache),
        ]

    @staticmethod
    def payload(severities: tuple[str, ...] = ()) -> dict:
        return {
            "SchemaVersion": 2,
            "Metadata": {"ImageID": "sha256:" + "a" * 64},
            "Results": [
                {
                    "Target": "synthetic-image",
                    "Vulnerabilities": [
                        {"VulnerabilityID": f"TEST-{index}", "Severity": severity}
                        for index, severity in enumerate(severities)
                    ],
                }
            ],
        }

    def fake_command(
        self, argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess:
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertTrue(hasattr(kwargs["stdout"], "write"))
        self.assertIs(kwargs["stderr"], subprocess.STDOUT)
        self.assertNotIn("shell", kwargs)
        if argv[0] != "docker":
            Path(argv[argv.index("--output") + 1]).write_text(
                json.dumps(self.payload()), encoding="utf-8"
            )
        return subprocess.CompletedProcess(argv, 0)

    def invoke(self) -> tuple[int, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = scanner.main(self.arguments())
        return code, stdout.getvalue() + stderr.getvalue()

    def test_six_literal_images_do_not_read_or_expand_environment(self) -> None:
        original = Path.read_text

        def guarded(path: Path, *args: object, **kwargs: object) -> str:
            self.assertNotEqual(path.name, ".env")
            return original(path, *args, **kwargs)

        with (
            patch.object(Path, "read_text", guarded),
            patch.dict(os.environ, {"UNREAD_SECRET": "synthetic-sensitive-marker"}),
        ):
            targets = scanner.read_targets(self.compose)
        self.assertEqual([target.service for target in targets], list(scanner.SERVICES))
        self.assertNotIn("synthetic-sensitive-marker", repr(targets))

    def test_current_repository_compose_has_seven_targets(self) -> None:
        targets = scanner.read_targets(
            Path(__file__).resolve().parents[1] / "gateway/docker-compose.yml"
        )
        self.assertEqual(len(targets), 7)
        self.assertEqual({t.service for t in targets}, set(scanner.SERVICES))

    def test_dedicated_memory_is_explicit_and_has_one_pinned_build(self) -> None:
        compose = Path(__file__).resolve().parents[1] / "gateway/neo4j-memory.yml"
        with self.assertRaises(ValueError):
            scanner.read_targets(compose)
        targets = scanner.read_targets(compose, memory=True)
        self.assertEqual([target.service for target in targets], ["neo4j"])
        self.assertIsNotNone(targets[0].context)

    def test_build_only_two_explicit_local_contexts(self) -> None:
        for service in ("postgres", "qdrant"):
            context = self.root / "images" / service
            context.mkdir(parents=True)
            (context / "Dockerfile").write_text("FROM synthetic:1\n", encoding="utf-8")
            self.text = self.text.replace(
                f"    image: example/{service}:1.0@sha256:{'a' * 64}",
                f"    image: ambicrafted/{service}:1.0-security\n    build:\n      context: ./images/{service}",
            )
        self.compose.write_text(self.text, encoding="utf-8")
        with patch.object(
            scanner.subprocess, "run", side_effect=self.fake_command
        ) as run:
            code, _ = self.invoke()
        self.assertEqual(code, 0)
        builds = [
            call.args[0]
            for call in run.call_args_list
            if call.args[0][:3] == ["docker", "buildx", "build"]
        ]
        self.assertEqual(len(builds), 2)
        self.assertEqual(
            {Path(argv[-1]).name for argv in builds}, {"postgres", "qdrant"}
        )
        self.assertTrue(
            all(argv[3:6] == ["--load", "--pull", "--tag"] for argv in builds)
        )
        self.assertEqual(len(list(self.output.glob("trivy-*.json"))), 7)

    def test_failure_diagnostic_is_bounded_redacted_and_drops_credentials(self) -> None:
        diagnostic = self.root / "failure.log"
        marker = "synthetic-private-credential-123"
        header_value = uuid.uuid4().hex
        program = (
            "import os,sys;"
            "assert 'EXAMPLE_SECRET' not in os.environ;"
            "assert 'TRIVY_IGNORE_UNFIXED' not in os.environ;"
            "print('x'*40000);"
            f"print('compiler failed: {marker}');"
            f"print('Authorization=Bearer '+{header_value!r});"
            "sys.exit(7)"
        )
        with patch.dict(
            os.environ,
            {
                "EXAMPLE_SECRET": marker,
                "TRIVY_IGNORE_UNFIXED": "true",
            },
        ):
            error = scanner.command([sys.executable, "-c", program], 10, diagnostic)
        self.assertEqual(error, "code 7")
        text = diagnostic.read_text()
        self.assertLessEqual(len(text), 16384)
        self.assertIn("compiler failed", text)
        self.assertNotIn(marker, text)
        self.assertNotIn(header_value, text)
        self.assertEqual(diagnostic.stat().st_mode & 0o777, 0o600)

    def test_one_service_uses_same_failure_policy_and_records_image_identity(
        self,
    ) -> None:
        with patch.object(scanner.subprocess, "run", side_effect=self.fake_command):
            code = scanner.main([*self.arguments(), "--service", "litellm"])
        self.assertEqual(code, 0)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(len(summary["images"]), 1)
        self.assertEqual(summary["images"][0]["image_id"], "sha256:" + "a" * 64)

    def test_reject_ambiguous_unpinned_or_dynamic_compose_without_echo(self) -> None:
        replacement = f"example/litellm:1.0@sha256:{'a' * 64}"
        cases = [
            self.text.replace(replacement, "example/litellm:latest"),
            self.text.replace(replacement, "${UNREAD_SECRET}"),
            self.text.replace("  litellm:", "  unexpected:"),
            self.text.replace("  litellm:", "  litellm:\n    <<: *hidden"),
            self.text.replace("  litellm:", "  litellm:\n    extends: hidden"),
            self.text.replace("  litellm:", f"  litellm:\n    image: {replacement}"),
            self.text.replace("    image: " + replacement, "    image: *alias"),
            self.text.replace("  litellm:", "  litellm:\n    build: ../private"),
            self.text + "services:\n",
        ]
        for content in cases:
            with self.subTest(content=content[:30]):
                self.compose.write_text(content, encoding="utf-8")
                with patch.object(scanner.subprocess, "run") as run:
                    code, output = self.invoke()
                self.assertEqual(code, 2)
                run.assert_not_called()
                self.assertNotIn("UNREAD_SECRET", output)
                self.assertNotIn(replacement, output)

    def test_high_and_critical_fail_after_all_reports_without_suppression(self) -> None:
        def vulnerable(
            argv: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess:
            result = self.fake_command(argv, **kwargs)
            if argv[0] != "docker":
                Path(argv[argv.index("--output") + 1]).write_text(
                    json.dumps(self.payload(("CRITICAL", "HIGH", "HIGH", "MEDIUM"))),
                    encoding="utf-8",
                )
                self.assertEqual(argv[argv.index("--exit-code") + 1], "0")
                self.assertEqual(argv[argv.index("--ignorefile") + 1], os.devnull)
                self.assertIn("--ignore-unfixed=false", argv)
                self.assertEqual(argv[argv.index("--scanners") + 1], "vuln")
                self.assertFalse(any(k.startswith("TRIVY_") for k in kwargs["env"]))
            return result

        with (
            patch.dict(os.environ, {"TRIVY_IGNORE_UNFIXED": "true"}),
            patch.object(scanner.subprocess, "run", side_effect=vulnerable),
        ):
            code, _ = self.invoke()
        self.assertEqual(code, 1)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(len(summary["images"]), 7)
        self.assertTrue(
            all(
                result["counts"]["CRITICAL"] == 1 and result["counts"]["HIGH"] == 2
                for result in summary["images"]
            )
        )
        self.assertEqual(len(list(self.output.glob("trivy-*.json"))), 7)

    def test_scan_failure_continues_other_services_and_keeps_partial_report(
        self,
    ) -> None:
        def failing(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            result = self.fake_command(argv, **kwargs)
            if argv[0] != "docker" and "litellm" in argv[-1]:
                return subprocess.CompletedProcess(argv, 42)
            return result

        with patch.object(scanner.subprocess, "run", side_effect=failing) as run:
            code, _ = self.invoke()
        self.assertEqual(code, 2)
        self.assertEqual(
            sum(call.args[0][0] != "docker" for call in run.call_args_list), 7
        )
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["images"][0]["error"], "Analyse : code 42")
        self.assertIsNone(summary["images"][0]["counts"])
        self.assertEqual(summary["images"][0]["report"], "trivy-litellm.json")
        self.assertTrue(
            all(result["status"] == "conforme" for result in summary["images"][1:])
        )
        self.assertIn(
            "Une erreur ne vaut jamais validation",
            (self.output / "summary.md").read_text(),
        )

    def test_pull_failure_continues_with_explicit_missing_report(self) -> None:
        def failing(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            if argv[:2] == ["docker", "pull"] and "litellm" in argv[-1]:
                return subprocess.CompletedProcess(argv, 1)
            return self.fake_command(argv, **kwargs)

        with patch.object(scanner.subprocess, "run", side_effect=failing) as run:
            code, _ = self.invoke()
        self.assertEqual(code, 2)
        self.assertEqual(
            sum(call.args[0][:2] == ["docker", "pull"] for call in run.call_args_list),
            7,
        )
        self.assertEqual(len(list(self.output.glob("trivy-*.json"))), 6)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertIsNone(summary["images"][0]["report"])
        self.assertEqual(summary["images"][0]["error"], "Préparation : code 1")

    def test_timeout_and_missing_executable_are_bounded_errors(self) -> None:
        for exception, expected in [
            (subprocess.TimeoutExpired("synthetic-private-value", 1), "délai dépassé"),
            (OSError("synthetic-private-value"), "exécutable indisponible"),
        ]:
            with (
                self.subTest(expected=expected),
                patch.object(scanner.subprocess, "run", side_effect=exception),
            ):
                self.assertEqual(scanner.command(["unavailable"], 1), expected)

    def test_diagnostics_redact_quoted_and_basic_credentials(self) -> None:
        basic = base64.b64encode(b"synthetic:only").decode()
        for payload, sensitive in [
            (f"Authorization: Basic {basic}", basic),
            ('{"token": "synthetic-only-secret"}', "synthetic-only-secret"),
            ('password="synthetic-only-secret"', "synthetic-only-secret"),
            ("api_key='synthetic-only-secret'", "synthetic-only-secret"),
            ('{"secret": "escaped \\"synthetic\\" value"}', "synthetic"),
            ("Cookie: session=synthetic-session; csrf=synthetic-csrf", "synthetic"),
        ]:
            with self.subTest(payload=payload):
                redacted = scanner.sanitized_tail(payload.encode())
                self.assertNotIn(sensitive, redacted)
                self.assertIn("[REDACTED]", redacted)

    def test_invalid_or_empty_report_never_passes(self) -> None:
        self.output.mkdir()
        report = self.output / "invalid.json"
        for payload in [
            None,
            [],
            {},
            {"SchemaVersion": 2},
            {"SchemaVersion": 2, "Results": []},
            {
                "SchemaVersion": 2,
                "Results": [{"Vulnerabilities": [{"Severity": "new"}]}],
            },
        ]:
            with self.subTest(payload=payload):
                report.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    scanner.vulnerability_counts(report)

    def test_existing_output_is_refused_before_running_any_command(self) -> None:
        self.output.mkdir()
        with patch.object(scanner.subprocess, "run") as run:
            code, _ = self.invoke()
        self.assertEqual(code, 2)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
