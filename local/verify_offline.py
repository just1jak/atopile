"""Build the local demo while rejecting Python IP socket connections."""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = ROOT / ".state/offline-verification"
    state.mkdir(parents=True, exist_ok=True)
    report = state / "network-attempts.txt"
    report.write_text("")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "local/offline_guard")
    env["ATOPILE_TEST_NETWORK_REPORT"] = str(report)
    subprocess.run([str(ROOT / "bin/ato-local"), "build", str(ROOT / "examples/offline-indicator"), "--target", "default"], env=env, check=True)
    events = report.read_text()
    if "blocked-IP-connection" in events:
        raise RuntimeError("Unexpected network attempt: see " + str(report))
    if events.count("guard-loaded") < 2:
        raise RuntimeError("Network guard was not inherited by build workers")
    print("PASS: build succeeded with no Python IP connection attempts")


if __name__ == "__main__":
    main()
