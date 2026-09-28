import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ApiQualityCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        for name in ("scripts/phase0_api_quality.py", "scripts/bizinfo_probe.py", "scripts/phase0.py",
                     "contracts/schemas/phase0-api-quality.contract.json", "contracts/external-api/bizinfo.contract.json"):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        self.environment = {name: value for name, value in os.environ.items()
                            if not name.startswith("BIZINFO_") and name != "APP_PROFILE"}
        self.environment["PYTHONDONTWRITEBYTECODE"] = "1"

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(self.root / "scripts/phase0_api_quality.py"), *args],
                              cwd=self.root, env=self.environment, text=True, capture_output=True)

    def test_missing_key_is_not_run_exit_three_and_unmeasured(self):
        result = self.cli("collect", "--profile", "dev", "--run-id", "no-key")
        self.assertEqual(result.returncode, 3, result.stderr)
        run = json.loads(result.stdout)["run"]
        self.assertEqual(run["collection_status"], "NOT_RUN")
        self.assertEqual(run["http_requests_attempted"], 0)
        artifact = self.root / "harness/workspace/artifacts/codex/phase0-api-quality/bizinfo-quality-no-key.json"
        metrics = json.loads(artifact.read_text(encoding="utf-8"))["metrics"]
        self.assertEqual(metrics["fields"]["pblancId"]["status"], "UNMEASURED")
        self.assertIsNone(metrics["fields"]["pblancId"]["counts"]["VALID"])
        self.assertFalse((self.root / "data/raw").exists())

    def test_prod_other_profiles_and_secret_argument_fail_without_echo(self):
        for profile in ("prod", "local", "staging"):
            result = self.cli("collect", "--profile", profile, "--run-id", "invalid")
            self.assertEqual(result.returncode, 2)
            self.assertFalse((self.root / "harness").exists())
        result = self.cli("collect", "--profile", "dev", "--run-id", "invalid", "--serviceKey", "synthetic-cli-secret")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("synthetic-cli-secret", result.stdout + result.stderr)

    def test_offline_analysis_reproduces_metrics_and_refuses_overwrite(self):
        self.cli("collect", "--profile", "dev", "--run-id", "offline")
        destination = "harness/workspace/artifacts/codex/phase0-api-quality/reproduced.json"
        args = ("analyze", "--run-id", "offline", "--output", destination)
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = json.loads((self.root / "harness/workspace/artifacts/codex/phase0-api-quality/bizinfo-quality-offline.json").read_text())
        self.assertEqual(json.loads((self.root / destination).read_text()), expected)
        before = (self.root / destination).read_bytes()
        self.assertEqual(self.cli(*args).returncode, 1)
        self.assertEqual((self.root / destination).read_bytes(), before)

    def test_markdown_report_and_output_boundary_without_network(self):
        self.cli("collect", "--profile", "dev", "--run-id", "report")
        (self.root / "harness/workspace/reports/codex").mkdir(parents=True)
        destination = "harness/workspace/reports/codex/offline-report.md"
        result = self.cli("analyze", "--run-id", "report", "--output", destination, "--markdown")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UNMEASURED", (self.root / destination).read_text())
        self.assertEqual(self.cli("analyze", "--run-id", "report", "--output", "outside.json").returncode, 1)
        self.assertFalse((self.root / "outside.json").exists())
        for wrong in ("harness/workspace/reports/agy/review.md", "harness/workspace/reports/root-report.md"):
            result = self.cli("analyze", "--run-id", "report", "--output", wrong, "--markdown")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse((self.root / wrong).exists())

    def test_help_needs_no_secret_or_http(self):
        self.assertEqual(self.cli("--help").returncode, 0)
        self.assertFalse((self.root / "harness").exists())


if __name__ == "__main__":
    unittest.main()
