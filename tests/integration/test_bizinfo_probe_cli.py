import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class BizinfoProbeCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        for name in ("scripts/bizinfo_probe.py", "scripts/phase0.py", "contracts/external-api/bizinfo.contract.json"):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        self.environment = {name: value for name, value in os.environ.items()
                            if not name.startswith("BIZINFO_") and name != "APP_PROFILE"}
        self.environment["PYTHONDONTWRITEBYTECODE"] = "1"

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(self.root / "scripts/bizinfo_probe.py"), *args],
            cwd=self.root, env=self.environment, text=True, capture_output=True,
        )

    def test_missing_credential_creates_not_run_evidence_with_exit_three(self):
        result = self.run_cli("--profile", "dev", "--run-id", "ci-no-credential")
        self.assertEqual(result.returncode, 3, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["execution"], "not_run")
        self.assertEqual(payload["observations"], [])
        self.assertEqual(payload["reason"], "credential_missing")
        self.assertEqual(payload["profile"], "dev")
        path = self.root / "harness/workspace/artifacts/bizinfo-probe-ci-no-credential.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)
        self.assertFalse((self.root / "data/raw").exists())

    def test_cli_usage_error_does_not_echo_secret_argument(self):
        result = self.run_cli("--profile", "dev", "--run-id", "usage", "--serviceKey", "synthetic-secret-argument")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("synthetic-secret-argument", result.stderr + result.stdout)

    def test_cli_help_succeeds_without_credential_or_network(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--mode", result.stdout)
        self.assertFalse((self.root / "harness").exists())

    def test_profile_is_required_and_unsupported_values_fail(self):
        for args in (("--run-id", "no-profile"),
                     ("--profile", "local", "--run-id", "local"),
                     ("--profile", "staging", "--run-id", "staging"),
                     ("--profile", "test", "--run-id", "test")):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertFalse((self.root / "harness").exists())

    def test_prod_without_secret_has_same_not_run_exit(self):
        result = self.run_cli("--profile", "prod", "--run-id", "prod-no-key")
        self.assertEqual(result.returncode, 3)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["profile"], "prod")
        self.assertEqual(payload["execution"], "not_run")
        self.assertEqual(payload["observations"], [])

    def test_env_file_secret_is_not_echoed_in_error_stdout_stderr_or_log(self):
        path = self.root / ".env.dev"
        path.write_text("BIZINFO_SERVICE_KEY=synthetic-profile-secret\nBIZINFO_API_BASE_URL=unsupported\n", encoding="utf-8")
        before = path.read_bytes()
        result = self.run_cli("--profile", "dev", "--run-id", "safe-failure")
        self.assertEqual(result.returncode, 1)
        log = self.root / "captured.log"
        log.write_text(result.stdout + result.stderr, encoding="utf-8")
        self.assertNotIn("synthetic-profile-secret", log.read_text(encoding="utf-8"))
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
