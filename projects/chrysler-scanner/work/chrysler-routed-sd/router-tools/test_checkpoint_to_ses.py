"""Focused tests using our immutable, task-local first captured checkpoint.

Does not read or change the active engine's checkpoint or any native PCB.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT.parent / "route-pass-3/checkpoint-pass1.ses.frb"
DSN = ROOT.parent / "route-pass-3/three-signal-layers.dsn"
JAVA = "/opt/homebrew/opt/openjdk@17/bin/java"


class CheckpointExportTest(unittest.TestCase):
    def run_export(self, source, output):
        return subprocess.run(
            [JAVA, "-Xmx256m", "-Djava.awt.headless=true", "-cp",
             str(ROOT / "freerouting-1.9.0.jar") + ":" + str(ROOT),
             "CheckpointToSes", str(source), str(output), str(DSN)],
            text=True, capture_output=True, timeout=30,
        )

    def test_complete_snapshot_exports_without_changing_input(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "new.ses"
            result = self.run_export(FIXTURE, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["components"], 263)
            self.assertEqual(report["pins"], 805)
            self.assertEqual(report["engineAirwires"], 172)
            self.assertEqual(report["checkpointSha256"], before)
            self.assertIn('(routes', output.read_text())
            self.assertIn('(placement', output.read_text())
            self.assertEqual(Path(str(output) + ".frb").read_bytes(), FIXTURE.read_bytes())
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "existing.ses"
            output.write_bytes(b"do not replace")
            result = self.run_export(FIXTURE, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), b"do not replace")
            self.assertFalse(Path(str(output) + ".frb").exists())

    def test_truncated_board_graph_never_exports_a_session(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            source = Path(directory) / "partial.frb"
            source.write_bytes(FIXTURE.read_bytes()[:10000])
            output = Path(directory) / "rejected.ses"
            result = self.run_export(source, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
            self.assertEqual(Path(str(output) + ".frb").read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
