#!/usr/bin/env bash
# Synthetic runner-only diagnostics; never weaken the application sandbox.
set -euo pipefail

repository=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repository/apps/control-api"

probe() {
  uv run --no-sync python - <<'PY'
import json
import subprocess
import sys
from pathlib import Path

from plateforme.document_sandbox import commande

def setting(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return "unavailable"

report = {
    "synthetic_input_only": True,
    "runtime": sys.base_prefix,
    "apparmor_enabled": setting("/sys/module/apparmor/parameters/enabled"),
    "userns_restricted": setting("/proc/sys/kernel/apparmor_restrict_unprivileged_userns"),
    "userns_clone": setting("/proc/sys/kernel/unprivileged_userns_clone"),
    "process_profile": setting("/proc/self/attr/current"),
}
try:
    command = commande(".txt")
    result = subprocess.run(
        command, input=b"x", capture_output=True, timeout=15, env={},
        close_fds=True, start_new_session=True, check=False,
    )
    report.update(
        bwrap=command[0], exit_code=result.returncode,
        # Safe here only: fixed public synthetic input, no operator configuration.
        stderr=result.stderr.decode(errors="replace")[:4000],
    )
    report["policy_denial_candidate"] = result.returncode == 1 and any(
        text in report["stderr"].lower()
        for text in ("permission denied", "operation not permitted", "no permissions")
    )
    expected = {"kind": "text", "text": "x", "truncated": False}
    report["ok"] = result.returncode == 0 and json.loads(result.stdout) == expected
except Exception as error:
    report.update(ok=False, error=type(error).__name__)
print(json.dumps(report, ensure_ascii=False))
raise SystemExit(0 if report["ok"] else 77 if report.get("policy_denial_candidate") else 1)
PY
}

if [[ ${1:-} == --probe ]]; then
  probe
  exit
fi
# Do not turn this CI preparation into automatic administrator changes on a workstation.
[[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_OS:-} == Linux ]]
if probe; then
  exit 0
else
  initial_result=$?
fi

# Ubuntu's signed distribution ships this opt-in profile separately from bwrap.
# It grants namespace setup to /usr/bin/bwrap and stacks its children under a
# capability-denying profile. Keep all global AppArmor restrictions unchanged.
[[ $initial_result == 77 ]]
[[ $(cat /sys/module/apparmor/parameters/enabled) == Y ]]
[[ $(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns) == 1 ]]
profile=/usr/share/apparmor/extra-profiles/bwrap-userns-restrict
target=/etc/apparmor.d/bwrap-userns-restrict
test -f "$profile"
sudo test -r /sys/kernel/security/apparmor/profiles
if sudo test -e "$target"; then
  sudo cmp --silent "$profile" "$target"
elif sudo grep -qE '^bwrap \(' /sys/kernel/security/apparmor/profiles; then
  echo "An existing bwrap policy must be reviewed instead of replaced." >&2
  exit 1
else
  sudo install --owner=root --group=root --mode=0644 "$profile" "$target"
fi
sudo apparmor_parser --replace "$target"
dpkg-query --show --showformat='${Package} ${Version}\n' \
  apparmor apparmor-profiles bubblewrap libseccomp2
sha256sum "$profile"
# The same real worker must succeed after policy loading; do not skip or fall back.
probe
