"""Exercise privileged CI preparation decisions without root or host policy writes."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class SandboxCiTests(unittest.TestCase):
    def run_case(self, scenario: str, *, github: bool = True) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            setup, log = root / "functions.sh", root / "commands.log"
            setup.write_text(
                r"""
probe_count=0
uv() {
  probe_count=$((probe_count + 1))
  printf 'probe %s\n' "$probe_count" >> "$TEST_LOG"
  if [[ $SCENARIO == ready || $probe_count == 2 && $SCENARIO != still_denied ]]; then
    return 0
  fi
  if [[ $SCENARIO == worker_failure ]]; then return 1; fi
  return 77
}
cat() {
  if [[ $1 == /sys/module/apparmor/parameters/enabled ]]; then
    printf 'Y\n'
  elif [[ $SCENARIO == unrestricted ]]; then printf '0\n'
  else printf '1\n'; fi
}
test() {
  if [[ $1 == -f && $2 == /usr/share/apparmor/extra-profiles/bwrap-userns-restrict ]]; then
    return 0
  fi
  builtin test "$@"
}
sudo() {
  printf 'sudo %s\n' "$*" >> "$TEST_LOG"
  if [[ $1 == test && $2 == -e ]]; then
    [[ $SCENARIO == existing_conflict ]]
  elif [[ $1 == cmp ]]; then return 1
  elif [[ $1 == grep ]]; then [[ $SCENARIO == foreign_loaded ]]
  else return 0; fi
}
dpkg-query() { :; }
sha256sum() { :; }
"""
            )
            environment = {
                "HOME": str(root),
                "PATH": "/usr/bin:/bin",
                "BASH_ENV": str(setup),
                "TEST_LOG": str(log),
                "SCENARIO": scenario,
                "GITHUB_ACTIONS": "true" if github else "false",
                "RUNNER_OS": "Linux",
            }
            process = subprocess.run(
                ["bash", str(Path(__file__).with_name("qualifier_sandbox_ci.sh"))],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            return process.returncode, log.read_text() if log.exists() else ""

    def test_local_administrator_changes_are_refused(self):
        code, log = self.run_case("denied", github=False)
        self.assertNotEqual(code, 0)
        self.assertEqual(log, "")

    def test_working_boundary_needs_no_privileged_action(self):
        code, log = self.run_case("ready")
        self.assertEqual(code, 0)
        self.assertEqual(log, "probe 1\n")

    def test_namespace_denial_loads_only_vendor_profile_then_reprobes(self):
        code, log = self.run_case("denied")
        self.assertEqual(code, 0)
        self.assertIn("sudo install --owner=root --group=root --mode=0644", log)
        self.assertIn(
            "sudo apparmor_parser --replace /etc/apparmor.d/bwrap-userns-restrict", log
        )
        self.assertTrue(log.endswith("probe 2\n"))
        self.assertNotIn("sysctl", log)
        self.assertNotIn("complain", log)

    def test_nonpolicy_worker_failure_never_changes_policy(self):
        code, log = self.run_case("worker_failure")
        self.assertNotEqual(code, 0)
        self.assertNotIn("sudo", log)

    def test_without_global_restriction_no_policy_change(self):
        code, log = self.run_case("unrestricted")
        self.assertNotEqual(code, 0)
        self.assertNotIn("sudo", log)

    def test_existing_different_policy_is_preserved(self):
        code, log = self.run_case("existing_conflict")
        self.assertNotEqual(code, 0)
        self.assertNotIn("sudo install", log)
        self.assertNotIn("sudo apparmor_parser", log)

    def test_already_loaded_foreign_policy_is_preserved(self):
        code, log = self.run_case("foreign_loaded")
        self.assertNotEqual(code, 0)
        self.assertNotIn("sudo install", log)
        self.assertNotIn("sudo apparmor_parser", log)

    def test_failed_reprobe_is_not_converted_into_success(self):
        code, log = self.run_case("still_denied")
        self.assertEqual(code, 77)
        self.assertTrue(log.endswith("probe 2\n"))


if __name__ == "__main__":
    os.umask(0o077)
    unittest.main()
