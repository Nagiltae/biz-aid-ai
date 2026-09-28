import json
import os
import sys
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
sys.path.insert(0, str(ROOT / "tests/contract"))
from test_document_acquisition import KEY, PDF, Response, SPEC, URL
from biz_aid_pipeline.bizinfo.models import SourceBatch, SourcePage, SyncScope
from biz_aid_pipeline.config.settings import DbConfig
from biz_aid_pipeline.documents.repository import DocumentRepository
from biz_aid_pipeline.documents.service import run, verify_run
from biz_aid_pipeline.ingestion.service import ingest
from biz_aid_pipeline.persistence.mysql_repository import MysqlRepository


class FilteredRepository(DocumentRepository):
    prefix = None

    def source_rows(self):
        return [row for row in super().source_rows() if row["pblanc_id"].startswith(self.prefix)]


class DocumentAcquisitionMysqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = replace(DbConfig.load(ROOT, "dev"), database="biz_aid_test")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        contract = self.root / "contracts/schemas/document-acquisition.contract.json"
        contract.parent.mkdir(parents=True)
        contract.write_bytes((ROOT / "contracts/schemas/document-acquisition.contract.json").read_bytes())
        self.prefix = "DOC_" + uuid.uuid4().hex[:12]
        self.url = URL.replace("FILE_SYNTHETIC", self.prefix)
        FilteredRepository.prefix = self.prefix
        self.structured = MysqlRepository(self.config)
        self.addCleanup(self.structured.close)

    def seed(self, suffix, print_url=None, print_name="공고.pdf", attachments=None, names=None):
        print_url = self.url if print_url is None else print_url
        source = {"pblancId": self.prefix + suffix, "printFlpthNm": print_url, "printFileNm": print_name,
                  "flpthNm": attachments, "fileNm": names}
        batch = SourceBatch(SyncScope.SAMPLE, (SourcePage(1, 1, (source,), 1),), "document fixture", False)
        ingest(self.structured, batch, "seed-" + uuid.uuid4().hex)
        return source["pblancId"]

    def execute(self, run_id, fetch, **kwargs):
        with patch.dict(os.environ, {"BIZINFO_SERVICE_KEY": KEY}), patch.object(DbConfig, "load", return_value=self.config):
            return run(self.root, "dev", run_id, fetch=fetch, pause=lambda _: None,
                       repository_factory=FilteredRepository, **kwargs)

    def test_relation_persistence_sha_dedupe_rerun_and_readback(self):
        first_id = self.seed("_A", attachments=self.url + "1", names="첨부.hwp")
        second_id = self.seed("_B", print_url=self.url + "2", print_name="이름.hwp")
        calls = []
        def fetch(request, timeout):
            calls.append(request.full_url)
            return Response(PDF, headers={"Content-Type": "application/pdf"})
        first = self.execute("doc-" + uuid.uuid4().hex, fetch)
        self.assertEqual(first["status"], "PASS")
        self.assertEqual((first["support_program_count"], first["total_candidate_relations"], first["attempted_downloads"]), (2, 3, 3))
        self.assertEqual((first["success_count"], first["failed_count"], first["pdf_count"]), (3, 0, 3))
        self.assertEqual(first["duplicate_content_sha_count"], 2)
        self.assertEqual(first["format_mismatch_count"], 2)
        second_run = "doc-" + uuid.uuid4().hex
        second = self.execute(second_run, lambda *args: (_ for _ in ()).throw(AssertionError("reused")))
        self.assertEqual((second["status"], second["attempted_downloads"], second["reused_relation_count"]), ("PASS", 0, 3))
        with patch.object(DbConfig, "load", return_value=self.config):
            self.assertEqual(verify_run(self.root, second_run, FilteredRepository)["status"], "PASS")
        repository = FilteredRepository(self.config)
        try:
            rows = repository.rows_for_keys([row["candidate_key"] for row in json.loads(
                (self.root / f"harness/workspace/artifacts/codex/phase2-document-acquisition/{second_run}/manifest.json").read_bytes())["plan"]["candidates"]])
        finally:
            repository.close()
        self.assertEqual({row["pblanc_id"] for row in rows}, {first_id, second_id})
        self.assertEqual(len({row["storage_path"] for row in rows}), 1)

    def test_partial_resume_and_failure_is_not_pass(self):
        self.seed("_PART", attachments=self.url + "1", names="첨부.pdf")
        run_id = "doc-" + uuid.uuid4().hex
        partial = self.execute(run_id, lambda request, timeout: Response(PDF), stop_after=1)
        self.assertEqual(partial["status"], "PARTIAL")
        completed = self.execute(run_id, lambda request, timeout: Response(PDF), resume=True)
        self.assertEqual((completed["status"], completed["success_count"]), ("PASS", 2))

        self.prefix = "DOC_" + uuid.uuid4().hex[:12]
        self.url = URL.replace("FILE_SYNTHETIC", self.prefix)
        FilteredRepository.prefix = self.prefix
        failed_id = self.seed("_HTML")
        failed = self.execute("doc-" + uuid.uuid4().hex,
                              lambda request, timeout: Response(b"<!doctype html><title>error</title>"))
        self.assertEqual((failed["status"], failed["failed_count"], failed["invalid_response_count"]), ("FAIL", 1, 1))
        self.assertEqual(failed["failure_candidates"][0]["pblanc_id"], failed_id)

    def test_transport_failure_has_one_attempt_and_new_run_can_retry(self):
        self.seed("_RETRY")
        calls = []
        def failed(request, timeout):
            calls.append(request.full_url)
            raise OSError("synthetic network failure")
        first = self.execute("doc-" + uuid.uuid4().hex, failed)
        self.assertEqual((first["status"], first["failed_count"], len(calls)), ("FAIL", 1, 1))
        second = self.execute("doc-" + uuid.uuid4().hex, lambda request, timeout: Response(PDF))
        self.assertEqual((second["status"], second["success_count"]), ("PASS", 1))

    def test_size_limit_prefix_is_failed_evidence_with_valid_checksum(self):
        self.seed("_SIZE")
        run_id = "doc-" + uuid.uuid4().hex
        local_spec = dict(SPEC, max_file_bytes=20)
        oversized = b"%PDF-1.7\n" + b"x" * 20
        with patch("biz_aid_pipeline.documents.service.contract", return_value=local_spec):
            report = self.execute(run_id, lambda request, timeout: Response(oversized))
        self.assertEqual((report["status"], report["failed_count"], report["integrity_failure_count"]),
                         ("FAIL", 1, 0))
        with patch.object(DbConfig, "load", return_value=self.config):
            self.assertEqual(verify_run(self.root, run_id, FilteredRepository)["integrity_failure_count"], 0)


if __name__ == "__main__":
    unittest.main()
