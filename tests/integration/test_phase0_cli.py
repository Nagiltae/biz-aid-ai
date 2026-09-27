import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class Phase0CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts/phase0.py"), *map(str, args)],
            text=True, capture_output=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )

    def test_snapshot_report_roundtrip_and_corruption_failure(self):
        source = self.directory / "source.json"
        source.write_bytes(b'{ "synthetic": true }\n')
        saved = self.run_cli("snapshot", source, "--run-id", "cli-run", "--media-type", "application/json", "--output-root", self.directory / "raw")
        self.assertEqual(saved.returncode, 0, saved.stderr)
        metadata = self.directory / "raw/cli-run/metadata.json"
        verified = self.run_cli("verify-snapshot", metadata)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        report_path = self.directory / "report.json"
        created = self.run_cli("init-report", "--output", report_path)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertIn("NOT_MEASURED", created.stdout)
        checked = self.run_cli("validate-report", report_path)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["gate"]["decision"], "pending")
        (metadata.parent / "response.json").write_bytes(b"{}")
        damaged = self.run_cli("verify-snapshot", metadata)
        self.assertEqual(damaged.returncode, 1)
        self.assertIn("mismatch", damaged.stderr)

    def test_existing_report_is_never_overwritten(self):
        path = self.directory / "report.json"
        first = self.run_cli("init-report", "--output", path)
        self.assertEqual(first.returncode, 0, first.stderr)
        initial = path.read_bytes()
        second = self.run_cli("init-report", "--output", path)
        self.assertEqual(second.returncode, 1)
        self.assertEqual(path.read_bytes(), initial)

    def test_invalid_contract_and_missing_input_fail(self):
        path = self.directory / "invalid.json"
        path.write_text('{"gate": "go"}\n', encoding="utf-8")
        invalid = self.run_cli("validate-report", path)
        self.assertEqual(invalid.returncode, 1)
        missing = self.run_cli("verify-snapshot", self.directory / "absent.json")
        self.assertEqual(missing.returncode, 1)

    def test_cli_usage_errors_are_distinct_from_success(self):
        result = self.run_cli("snapshot")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
