"""Render synthetic Compose configuration only; never access an operator .env or Docker daemon."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "docker-compose.yml": (
        "gateway",
        {
            "pgdata": "PLATFORM_PGDATA_VOLUME",
            "tempodata": "PLATFORM_TEMPODATA_VOLUME",
            "promdata": "PLATFORM_PROMDATA_VOLUME",
            "grafanadata": "PLATFORM_GRAFANADATA_VOLUME",
            "qdrantdata": "PLATFORM_QDRANTDATA_VOLUME",
        },
    ),
    "neo4j-memory.yml": (
        "ambicrafted-memory",
        {
            "memory-data": "PLATFORM_MEMORY_DATA_VOLUME",
            "memory-logs": "PLATFORM_MEMORY_LOGS_VOLUME",
        },
    ),
}


@unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required; daemon not used")
class ComposeVolumes(unittest.TestCase):
    def render(self, filename, values=None, project=None, project_env=None):
        with tempfile.TemporaryDirectory(prefix="compose-volume-config-") as directory:
            root = Path(directory)
            config = root / filename
            shutil.copyfile(ROOT / "gateway" / filename, config)
            environment_file = root / ".env"
            values = {
                "POSTGRES_PASSWORD": "synthetic-not-a-credential",
                "GRAFANA_ADMIN_PASSWORD": "synthetic-not-a-credential",
                "NEO4J_MEMORY_PASSWORD": "synthetic-not-a-credential",
                **(values or {}),
            }
            environment_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
            environment = {"PATH": os.defpath}
            if project_env:
                environment["COMPOSE_PROJECT_NAME"] = project_env
            command = [
                shutil.which("docker"),
                "compose",
                "--env-file",
                str(environment_file),
                "--project-directory",
                str(root),
                "-f",
                str(config),
            ]
            if project:
                command.extend(["--project-name", project])
            for arguments in (["config", "--quiet"], ["config", "--format", "json"]):
                result = subprocess.run(
                    [*command, *arguments],
                    cwd=root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            rendered = json.loads(result.stdout)
            # Return only nonsecret volume identities; never print service environment.
            return {key: value["name"] for key, value in rendered["volumes"].items()}

    def test_original_defaults(self):
        for filename, (project, mapping) in FILES.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    self.render(filename), {key: f"{project}_{key}" for key in mapping}
                )

    def test_custom_project_environment_preserves_previous_names(self):
        for filename, (_, mapping) in FILES.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    self.render(filename, project_env="custom-project"),
                    {key: f"custom-project_{key}" for key in mapping},
                )

    def test_project_flag_takes_precedence(self):
        for filename, (_, mapping) in FILES.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    self.render(filename, project="flag-project", project_env="other-project"),
                    {key: f"flag-project_{key}" for key in mapping},
                )

    def test_empty_variables_retain_project_defaults(self):
        for filename, (project, mapping) in FILES.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    self.render(filename, {variable: "" for variable in mapping.values()}),
                    {key: f"{project}_{key}" for key in mapping},
                )

    def test_explicit_volumes_are_not_prefixed(self):
        for filename, (_, mapping) in FILES.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    self.render(
                        filename,
                        {variable: f"recovery-{key}" for key, variable in mapping.items()},
                        project="different-project",
                    ),
                    {key: f"recovery-{key}" for key in mapping},
                )

    def test_partial_override_does_not_change_other_volumes(self):
        for filename, (project, mapping) in FILES.items():
            with self.subTest(filename=filename):
                first = next(iter(mapping))
                expected = {key: f"{project}_{key}" for key in mapping}
                expected[first] = "reviewed-recovery-volume"
                self.assertEqual(
                    self.render(filename, {mapping[first]: "reviewed-recovery-volume"}), expected
                )


if __name__ == "__main__":
    unittest.main()
