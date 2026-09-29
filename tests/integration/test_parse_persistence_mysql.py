import base64
import hashlib
import sys
import unittest
import uuid
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from docling_core.types.doc import DoclingDocument

from biz_aid_pipeline.bizinfo.models import SourceBatch, SourcePage, SyncScope
from biz_aid_pipeline.config.settings import DbConfig, PipelineError
from biz_aid_pipeline.documents.models import candidates
from biz_aid_pipeline.documents.repository import DocumentRepository, utc_datetime
from biz_aid_pipeline.documents.service import relation_value
from biz_aid_pipeline.ingestion.service import ingest
from biz_aid_pipeline.parsing.models import ParseResult, parse_key, parsing_contract
from biz_aid_pipeline.parsing.orchestration import orchestrate_source
from biz_aid_pipeline.parsing.persistence import S3ParsedArtifactStore, persist_parse_result
from biz_aid_pipeline.parsing.repository import ParseResultRepository
from biz_aid_pipeline.persistence.mysql_repository import MysqlRepository
from biz_aid_pipeline.storage import S3DocumentStore
from tests.contract.test_s3_document_store import FakeS3Client


class ParsePersistenceMysqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = replace(DbConfig.load(ROOT, "dev"), database="biz_aid_test")
        cls.contract = parsing_contract()

    def setUp(self):
        self.identifier = "PARSE_" + uuid.uuid4().hex[:12]
        self.source_raw = ("source-" + self.identifier).encode()
        self.source_sha = hashlib.sha256(self.source_raw).hexdigest()
        self.structured = MysqlRepository(self.config)
        self.documents = DocumentRepository(self.config)
        self.repository = ParseResultRepository(self.config)
        self.addCleanup(self.structured.close)
        self.addCleanup(self.documents.close)
        self.addCleanup(self.repository.close)
        self._seed_source()
        self.client = FakeS3Client()
        self.store = S3ParsedArtifactStore("test-bucket", "ap-southeast-2", self.client)
        self.source_store = S3DocumentStore("test-source-bucket", "ap-southeast-2",
                                             "biz-aid/documents", self.client)
        source_key = self.source_store.object_key(self.source_sha)
        self.client.objects[("test-source-bucket", source_key)] = {
            "raw": self.source_raw,
            "checksum": base64.b64encode(bytes.fromhex(self.source_sha)).decode("ascii"),
            "content_type": "application/octet-stream",
        }

    def _seed_source(self):
        url = f"https://www.bizinfo.go.kr/cmm/fms/getImageFile.do?atchFileId={self.identifier}&fileSn=0"
        source = {"pblancId": self.identifier, "printFlpthNm": url, "printFileNm": "fixture.hwpx"}
        batch = SourceBatch(SyncScope.SAMPLE, (SourcePage(1, 1, (source,), 1),), "parse persistence fixture", False)
        ingest(self.structured, batch, "parse-seed-" + uuid.uuid4().hex)
        run_id = "parse-doc-" + uuid.uuid4().hex
        self.documents.create_run(run_id, hashlib.sha256(self.identifier.encode()).hexdigest())
        candidate = candidates(self.identifier, url, "fixture.hwpx", None, None)[0].value()
        object_key = f"biz-aid/documents/sha256/{self.source_sha[:2]}/{self.source_sha[2:4]}/{self.source_sha}"
        transfer = {"detected_format": "HWPX", "failure_category": None, "http_status": 200,
                    "redirect_count": 0, "content_type": "application/octet-stream", "invalid_response": False}
        value = relation_value(candidate, run_id, transfer, self.source_raw, object_key, self.source_sha,
                               "DOWNLOADED", 1, acquired_at=utc_datetime(), s3_metadata={
                                   "s3_region": "ap-southeast-2", "s3_bucket_name": "test-source-bucket",
                                   "s3_object_key": object_key, "s3_verified_at": utc_datetime()})
        self.documents.persist_group([value])

    def result(self, contract=None):
        contract = contract or self.contract
        document = DoclingDocument(name=self.identifier)
        document.add_text(label="text", text="영구 저장할 작은 DoclingDocument fixture 본문입니다")
        key = parse_key(self.source_sha, "HWPX_DOCLING_ADAPTER", contract)
        return ParseResult(self.source_sha, "HWPX", "HWPX_DOCLING_ADAPTER", key, "PARSED",
                           document=document, text_chars=35, unit_count=1)

    def test_orchestration_and_identical_rerun_are_idempotent(self):
        parser = lambda request, raw, contract: self.result(contract)
        first = orchestrate_source(self.source_sha, self.documents, self.source_store,
                                   self.repository, self.store, self.contract, parser=parser)
        second = orchestrate_source(self.source_sha, self.documents, self.source_store,
                                    self.repository, self.store, self.contract, parser=parser)
        row = self.repository.get(self.source_sha, first.parse_key)
        self.assertEqual((first.persistence_action, second.persistence_action, self.client.put_calls),
                         ("INSERTED", "REUSED", 1))
        self.assertEqual((row["parse_status"], row["artifact_s3_object_key"], row["artifact_sha256"],
                          row["artifact_byte_size"]),
                         ("PARSED", first.artifact_s3_key, first.artifact_sha256, first.artifact_byte_size))
        raw = self.store.objects.read_key(first.artifact_s3_key, first.artifact_sha256, first.artifact_byte_size,
                                          max_bytes=first.artifact_byte_size)
        self.assertEqual(DoclingDocument.model_validate_json(raw).export_to_markdown(),
                         self.result().document.export_to_markdown())

    def test_verify_failure_leaves_no_success_metadata(self):
        result = self.result()

        class FailedStore:
            region, bucket = "ap-southeast-2", "test-bucket"

            @staticmethod
            def put(*args):
                raise RuntimeError("synthetic verify failure")

        with self.assertRaisesRegex(PipelineError, "parsed_artifact_storage_failure"):
            persist_parse_result(result, self.repository, FailedStore(), self.contract)
        self.assertIsNone(self.repository.get(self.source_sha, result.parse_key))


if __name__ == "__main__":
    unittest.main()
