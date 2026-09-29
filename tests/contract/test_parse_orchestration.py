import contextlib
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.parsing.models import ParseResult, parsing_contract
from biz_aid_pipeline.parsing.orchestration import ParseExecution, orchestrate_source, run_batch
from biz_aid_pipeline.parsing.persistence import PersistedParseResult
from biz_aid_pipeline.parsing_cli import main


SOURCE_SHA = "a" * 64
SOURCE_KEY = f"biz-aid/documents/sha256/aa/aa/{SOURCE_SHA}"


class SourceRepository:
    @staticmethod
    def verified_source(source_sha256):
        if source_sha256 != SOURCE_SHA:
            raise AssertionError("unexpected source")
        return {"content_sha256": SOURCE_SHA, "detected_format": "HWPX", "byte_size": 7,
                "s3_region": "ap-southeast-2", "s3_bucket_name": "source-bucket",
                "s3_object_key": SOURCE_KEY, "relation_count": 2}


class SourceStore:
    region, bucket = "ap-southeast-2", "source-bucket"

    @staticmethod
    def object_key(source_sha256):
        return SOURCE_KEY

    @staticmethod
    def read_key(key, sha256_hex, byte_size, max_bytes):
        if (key, sha256_hex, byte_size) != (SOURCE_KEY, SOURCE_SHA, 7) or max_bytes < 7:
            raise AssertionError("source read contract mismatch")
        return b"fixture"


class ParseOrchestrationTests(unittest.TestCase):
    def test_single_source_connects_lookup_read_parser_persistence_and_cli(self):
        calls = []

        def parser(request, raw, contract):
            calls.append(("parse", request.source_sha256, raw))
            return ParseResult(SOURCE_SHA, "HWPX", "HWPX_DOCLING_ADAPTER", "b" * 64, "PARSED")

        def persister(result, repository, store, contract):
            calls.append(("persist", result.status, repository, store))
            return PersistedParseResult("INSERTED", SOURCE_SHA, result.parse_key, result.status,
                                        "parsed/key.json", "c" * 64, 123)

        execution = orchestrate_source(SOURCE_SHA, SourceRepository(), SourceStore(), "result-repository",
                                       "artifact-store", parsing_contract(), parser, persister)
        self.assertEqual(calls, [("parse", SOURCE_SHA, b"fixture"),
                                 ("persist", "PARSED", "result-repository", "artifact-store")])
        self.assertEqual((execution.status, execution.persistence_action, execution.artifact_s3_key),
                         ("PARSED", "INSERTED", "parsed/key.json"))

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(["--profile", "dev", "--source-sha256", SOURCE_SHA],
                             runner=lambda *_: execution)
        self.assertEqual(exit_code, 0)
        self.assertIn('"persistence_action": "INSERTED"', output.getvalue())

    def test_s3_read_failure_stops_before_parser_and_persistence(self):
        class FailedStore(SourceStore):
            @staticmethod
            def read_key(*args, **kwargs):
                raise RuntimeError("synthetic S3 read failure")

        calls = []
        with self.assertRaisesRegex(PipelineError, "document_source_s3_read_failure"):
            orchestrate_source(SOURCE_SHA, SourceRepository(), FailedStore(), object(), object(),
                               parsing_contract(), parser=lambda *args: calls.append("parse"),
                               persister=lambda *args: calls.append("persist"))
        self.assertEqual(calls, [])

    def test_bounded_batch_sorts_unique_sources_and_cli_reports_actions(self):
        sources = ["b" * 64, "a" * 64]
        calls = []
        boundary = parsing_contract()["orchestration"]["batch_boundary"]
        self.assertEqual(boundary["maximum_unique_sources"], 3)
        self.assertIn("ascending", boundary["order"])

        def runner(root, profile, source_sha256):
            calls.append(source_sha256)
            return ParseExecution(source_sha256, "HWPX", "c" * 64, "PARSED", None,
                                  "INSERTED", f"parsed/{source_sha256}.json", "d" * 64, 10)

        result = run_batch(ROOT, "dev", sources, runner)
        self.assertEqual(calls, sorted(sources))
        self.assertEqual((result.status, result.source_count, result.inserted, result.failed),
                         ("PASS", 2, 2, 0))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(["--profile", "dev", "--source-sha256", sources[0],
                              "--source-sha256", sources[1]], runner=runner)
        self.assertEqual(exit_code, 0)
        self.assertIn('"source_count": 2', output.getvalue())

    def test_bounded_batch_continues_after_one_source_failure(self):
        sources = ["a" * 64, "b" * 64, "c" * 64]
        calls = []

        def runner(root, profile, source_sha256):
            calls.append(source_sha256)
            if source_sha256 == sources[1]:
                raise PipelineError("synthetic_source_failure")
            return ParseExecution(source_sha256, "HWPX", "d" * 64, "PARSED", None,
                                  "REUSED", f"parsed/{source_sha256}.json", "e" * 64, 10)

        result = run_batch(ROOT, "dev", sources, runner)
        self.assertEqual(calls, sources)
        self.assertEqual((result.status, result.reused, result.failed), ("FAIL", 2, 1))
        self.assertEqual(result.items[1].failure_code, "synthetic_source_failure")

    def test_bounded_batch_rejects_unsafe_scope_before_execution(self):
        calls = []
        runner = lambda *args: calls.append(args)
        cases = (("dev", []), ("dev", ["a" * 64] * 2),
                 ("dev", [character * 64 for character in "abcd"]),
                 ("dev", ["not-a-sha"]), ("prod", ["a" * 64]))
        for profile, sources in cases:
            with self.subTest(profile=profile, count=len(sources)):
                with self.assertRaises(PipelineError):
                    run_batch(ROOT, profile, sources, runner)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
