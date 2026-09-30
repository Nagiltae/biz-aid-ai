import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from docling_core.types.doc import DoclingDocument

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.parsing.models import ParseResult, parse_key, parsing_contract
from biz_aid_pipeline.parsing.persistence import S3ParsedArtifactStore, persist_parse_result
from biz_aid_pipeline.parsing.quality import artifact_bytes
from tests.contract.test_s3_document_store import FakeS3Client


def parsed_result(source_sha="a" * 64, contract=None):
    contract = contract or parsing_contract()
    document = DoclingDocument(name="persistence-fixture")
    document.add_text(label="text", text="지원사업 parsing persistence fixture 본문")
    return ParseResult(source_sha, "HWPX", "HWPX_DOCLING_ADAPTER",
                       parse_key(source_sha, "HWPX_DOCLING_ADAPTER", contract), "PARSED",
                       document=document, text_chars=34, unit_count=1)


class FakeRepository:
    def __init__(self):
        self.values = None
        self.persist_calls = 0

    def require_source(self, source_sha256):
        self.source = source_sha256

    def persist(self, values):
        self.persist_calls += 1
        self.values = values
        return "INSERTED"


class ParsePersistenceContractTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeS3Client()
        self.store = S3ParsedArtifactStore("test-bucket", "ap-southeast-2", self.client)

    def test_parsed_key_is_deterministic_immutable_and_reloadable(self):
        result = parsed_result()
        raw = artifact_bytes(result.document)
        first = self.store.put(raw, result.source_sha256, result.parse_key)
        second = self.store.put(raw, result.source_sha256, result.parse_key)
        expected = (f"biz-aid/parsed/docling-json/sha256/aa/aa/{result.source_sha256}/"
                    f"{result.parse_key}.json")
        self.assertEqual((first["key"], second["key"], self.client.put_calls), (expected, expected, 1))
        stored = self.client.objects[("test-bucket", expected)]["raw"]
        self.assertEqual(hashlib.sha256(stored).hexdigest(), first["sha256"])
        self.assertEqual(DoclingDocument.model_validate_json(stored).export_to_markdown(),
                         result.document.export_to_markdown())

    def test_s3_failure_never_calls_metadata_repository(self):
        class FailedStore:
            region, bucket = "ap-southeast-2", "test-bucket"

            @staticmethod
            def put(*args):
                raise RuntimeError("synthetic verification failure")

        repository = FakeRepository()
        with self.assertRaisesRegex(PipelineError, "parsed_artifact_storage_failure"):
            persist_parse_result(parsed_result(), repository, FailedStore())
        self.assertEqual(repository.persist_calls, 0)

    def test_non_success_persists_metadata_without_artifact(self):
        result = parsed_result()
        result.status, result.document, result.failure_code = "PARSE_FAILED", None, "malformed_xml"
        repository = FakeRepository()
        outcome = persist_parse_result(result, repository, self.store)
        self.assertEqual((outcome.status, outcome.artifact_s3_key, self.client.put_calls),
                         ("PARSE_FAILED", None, 0))
        self.assertIsNone(repository.values["artifact_sha256"])


if __name__ == "__main__":
    unittest.main()
