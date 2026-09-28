import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests/contract"))
import phase0_document_download as documents
import test_phase0_document_download as fixtures


class DocumentCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = io.StringIO()

    def call(self, args):
        with redirect_stdout(self.output), redirect_stderr(self.output):
            return documents.main(args, self.root, {"BIZINFO_SERVICE_KEY": fixtures.KEY})

    def test_prod_profile_and_unsupported_profile_fail_without_http(self):
        with patch.object(documents, "open_document", side_effect=AssertionError("no HTTP")):
            for profile in ("prod", "local", "staging"):
                with self.assertRaises(SystemExit) as error:
                    self.call(["download", "--profile", profile, "--run-id", "cli-test"])
                self.assertEqual(error.exception.code, 2)

    def test_missing_source_fails_without_http_or_secret_output(self):
        with patch.object(documents, "open_document", side_effect=AssertionError("no HTTP")):
            self.assertEqual(self.call(["download", "--profile", "dev", "--run-id", "cli-test"]), 1)
        self.assertNotIn(fixtures.KEY, self.output.getvalue())

    def test_explicit_dev_download_cli_success_mock_only(self):
        fixtures.prepare_source(self.root)
        real_download = documents.download
        def offline(root, profile, identifier, environ, resume):
            return real_download(root, profile, identifier, environ, resume,
                                 lambda *a: fixtures.Response(), pause=lambda _: None)
        with patch.object(documents, "download", offline), patch.object(documents, "open_document", side_effect=AssertionError("no live HTTP")):
            self.assertEqual(self.call(["download", "--profile", "dev", "--run-id", "cli-test"]), 0)
        self.assertNotIn(fixtures.KEY, self.output.getvalue())

    def test_partial_offline_analysis_cli_and_output_overwrite_denied(self):
        fixtures.prepare_source(self.root)
        with redirect_stdout(self.output):
            documents.download(self.root, "dev", "cli-test", {}, fetch=lambda *a: fixtures.Response(), stop_after=2, pause=lambda _: None)
        (self.root / "harness/workspace/reports/codex").mkdir(parents=True)
        args = ["analyze", "--run-id", "cli-test", "--output", "harness/workspace/reports/codex/result.md"]
        with patch.object(documents, "open_document", side_effect=AssertionError("no HTTP")):
            self.assertEqual(self.call(args), 0)
            before = (self.root / args[-1]).read_bytes()
            self.assertEqual(self.call(args), 1)
            self.assertEqual((self.root / args[-1]).read_bytes(), before)
        self.assertNotIn(fixtures.KEY.encode(), before)
        self.assertEqual(self.call(["analyze", "--run-id", "cli-test", "--output", "harness/workspace/reports/agy/result.md"]), 1)

    def test_analysis_checksum_failure_and_output_boundary(self):
        fixtures.prepare_source(self.root)
        documents.download(self.root, "dev", "cli-test", {}, fetch=lambda *a: fixtures.Response(), stop_after=1, pause=lambda _: None)
        self.assertEqual(self.call(["analyze", "--run-id", "cli-test", "--output", "data/downloaded/wrong.md"]), 1)
        (self.root / "data/downloaded/cli-test/SYNTHETIC_000/document.bin").write_bytes(b"tampered")
        self.assertEqual(self.call(["analyze", "--run-id", "cli-test", "--output", "harness/workspace/reports/codex/result.md"]), 1)


if __name__ == "__main__":
    unittest.main()
