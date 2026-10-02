import hashlib
import io
import sys
import unittest
import uuid
import zipfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
sys.path.insert(0, str(ROOT / "scripts/lib"))

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from biz_aid_pipeline.bizinfo.models import SourceBatch, SourcePage, SyncScope
from biz_aid_pipeline.chunking.source import announcements, original_filenames
from biz_aid_pipeline.config.settings import DbConfig, PipelineError
from biz_aid_pipeline.documents.archive import MEMBER_TABLE, ArchiveMemberRepository, member_row, plan_archive, utc_now
from biz_aid_pipeline.documents.models import candidates
from biz_aid_pipeline.documents.repository import DocumentRepository, utc_datetime
from biz_aid_pipeline.documents.service import relation_value
from biz_aid_pipeline.ingestion.service import ingest
from biz_aid_pipeline.parsing.models import parsing_contract
from biz_aid_pipeline.parsing.repository import ParseResultRepository
from biz_aid_pipeline.persistence.mysql_repository import MysqlRepository
from biz_aid_pipeline.storage import S3DocumentStore
from tests.contract.test_s3_document_store import FakeS3Client
from validate import database_comments

PENDING_MIGRATION = ROOT / "data-pipeline/pending-migrations/V10__document_archive_members.sql"
PDF = b"%PDF-1.7\nsynthetic-archive-member\n%%EOF\n"


class ArchiveMembersMysqlTests(unittest.TestCase):
    """승인 전 V10 DDL을 테스트 전용 DB에서만 검증한다. dev DB에는 적용하지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.config = replace(DbConfig.load(ROOT, "dev"), database="biz_aid_test")
        cls.structured = MysqlRepository(cls.config)
        with cls.structured.engine.begin() as connection:
            cls.created = not inspect(connection).has_table(MEMBER_TABLE)
            if cls.created:
                # 테스트가 만든 표는 끝나면 지운다. 나중에 Flyway V10이 같은 이름으로 만들 수 있어야 한다.
                connection.exec_driver_sql(PENDING_MIGRATION.read_text(encoding="utf-8").strip().rstrip(";"))

    @classmethod
    def tearDownClass(cls):
        if cls.created:
            with cls.structured.engine.begin() as connection:
                connection.exec_driver_sql(f"DROP TABLE `{MEMBER_TABLE}`")
        cls.structured.close()

    def setUp(self):
        self.identifier = "ZIP_" + uuid.uuid4().hex[:12]
        self.archive_raw = self.archive()
        self.archive_sha = hashlib.sha256(self.archive_raw).hexdigest()
        self.documents = DocumentRepository(self.config)
        self.addCleanup(self.documents.close)
        self.seed_archive()
        self.members = ArchiveMemberRepository(self.config)
        self.addCleanup(self.members.close)
        self.addCleanup(self.delete_rows)
        self.client = FakeS3Client()
        self.store = S3DocumentStore("test-source-bucket", "ap-southeast-2", "biz-aid/documents", self.client)

    def archive(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as output:
            output.writestr("서식/2026 모집 공고문.pdf", PDF + self.identifier.encode())
            output.writestr("서식/Thumbs.db", b"\0" * 32)
        return stream.getvalue()

    def seed_archive(self):
        url = f"https://www.bizinfo.go.kr/cmm/fms/getImageFile.do?atchFileId={self.identifier}&fileSn=0"
        source = {"pblancId": self.identifier, "pblancNm": "압축 합성 공고", "printFlpthNm": url, "printFileNm": "붙임서류.zip"}
        batch = SourceBatch(SyncScope.SAMPLE, (SourcePage(1, 1, (source,), 1),), "archive member fixture", False)
        ingest(self.structured, batch, "zip-seed-" + uuid.uuid4().hex)
        run_id = "zip-doc-" + uuid.uuid4().hex
        self.documents.create_run(run_id, hashlib.sha256(self.identifier.encode()).hexdigest())
        candidate = candidates(self.identifier, url, "붙임서류.zip", None, None)[0].value()
        key = self.store_key(self.archive_sha)
        transfer = {"detected_format": "ZIP", "failure_category": None, "http_status": 200, "redirect_count": 0,
                    "content_type": "application/zip", "invalid_response": False}
        self.documents.persist_group([relation_value(candidate, run_id, transfer, self.archive_raw, key, self.archive_sha,
                                                     "DOWNLOADED", 1, acquired_at=utc_datetime(), s3_metadata={
                                                         "s3_region": "ap-southeast-2", "s3_bucket_name": "test-source-bucket",
                                                         "s3_object_key": key, "s3_verified_at": utc_datetime()})])

    @staticmethod
    def store_key(sha):
        return f"biz-aid/documents/sha256/{sha[:2]}/{sha[2:4]}/{sha}"

    def delete_rows(self):
        with self.structured.engine.begin() as connection:
            connection.execute(text(f"DELETE FROM {MEMBER_TABLE} WHERE archive_source_sha256 = :sha"), {"sha": self.archive_sha})

    def rows(self, run_id="zip-test-run"):
        plan = plan_archive(self.archive_raw, self.archive_sha, parsing_contract(), lambda sha: False)
        rows = []
        for member in plan.members:
            storage = None
            if member.status == "STORED":
                key = self.store.put_bytes(member.raw, member.sha256)
                storage = (self.store.region, self.store.bucket, key, utc_now())
            rows.append(member_row(member, self.archive_sha, run_id, storage))
        return plan, rows

    def test_table_comments_follow_policy(self):
        with self.structured.engine.connect() as connection:
            failures = database_comments(connection)["failures"]
        self.assertEqual([item for item in failures if item["object"].startswith(MEMBER_TABLE)], [])

    def test_check_constraints_reject_inconsistent_rows(self):
        _, rows = self.rows()
        stored = next(row for row in rows if row["processing_status"] == "STORED")
        broken = dict(stored, member_key="0" * 64, s3_object_key=None)
        broken.pop("parent_member_provenance")
        with self.assertRaises(DBAPIError), self.structured.engine.begin() as connection:
            connection.execute(self.members.members.insert().values(**broken))
        failed_with_sha = dict(stored, member_key="1" * 64, processing_status="FAILED", status_reason="member_size_mismatch",
                               s3_region=None, s3_bucket_name=None, s3_object_key=None, s3_verified_at=None)
        failed_with_sha.pop("parent_member_provenance")
        with self.assertRaises(DBAPIError), self.structured.engine.begin() as connection:
            connection.execute(self.members.members.insert().values(**failed_with_sha))

    def test_persist_is_idempotent_and_never_overwrites(self):
        _, rows = self.rows()
        self.assertEqual(self.members.persist_archive(rows), {"INSERTED": 2, "REUSED": 0})
        # 다른 실행 ID로 같은 결정을 다시 기록하면 재사용한다.
        _, again = self.rows("zip-test-run-2")
        self.assertEqual(self.members.persist_archive(again), {"INSERTED": 0, "REUSED": 2})
        changed = [dict(row, processing_status="EXCLUDED", status_reason="unsupported_format", s3_region=None, s3_bucket_name=None,
                        s3_object_key=None, s3_verified_at=None) if row["processing_status"] == "STORED" else row for row in rows]
        with self.assertRaises(PipelineError) as raised:
            self.members.persist_archive(changed)
        self.assertEqual(str(raised.exception), "archive_member_conflict")

    def test_stored_member_is_a_parsing_source_with_inherited_program(self):
        plan, rows = self.rows()
        self.members.persist_archive(rows)
        member = next(member for member in plan.members if member.status == "STORED")
        repository = ParseResultRepository(self.config)
        documents = DocumentRepository(self.config)
        try:
            self.assertIn((member.sha256, "PDF"), repository.verified_source_formats())
            repository.require_source(member.sha256)
            # 압축 자체는 파싱 입력이 아니고(ZIP route 비활성), 제외된 Thumbs.db는 입력이 되지 않는다.
            excluded = next(item for item in plan.members if item.status == "EXCLUDED")
            self.assertNotIn(excluded.sha256, {sha for sha, _ in repository.verified_source_formats()})
            source = documents.verified_source(member.sha256)
            self.assertEqual((source["detected_format"], source["s3_object_key"]), ("PDF", self.store_key(member.sha256)))
            # 공고 relation은 압축 첨부에서 물려받고, 출처 종류 단서는 내부 파일명이다.
            self.assertEqual(announcements(repository, member.sha256), ((self.identifier, "압축 합성 공고"),))
            self.assertEqual(original_filenames(repository, member.sha256), ["2026 모집 공고문.pdf"])
        finally:
            repository.close()
            documents.close()


if __name__ == "__main__":
    unittest.main()
