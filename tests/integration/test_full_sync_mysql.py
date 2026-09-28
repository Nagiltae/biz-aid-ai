import json
import os
import sys
import tempfile
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event, select, update

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
sys.path.insert(0, str(ROOT / "tests/contract"))
from test_full_sync import KEY, fixture_root, responses
from biz_aid_pipeline.bizinfo.models import SourceBatch, SourcePage, SyncScope
from biz_aid_pipeline.bizinfo.raw_snapshot import verify_full_snapshot
from biz_aid_pipeline.config.settings import DbConfig, PipelineError
from biz_aid_pipeline.ingestion.full_sync import ARTIFACT_ROOT, run_full_sync, validate_full_report
from biz_aid_pipeline.ingestion.service import ingest
from biz_aid_pipeline.persistence.mysql_repository import MysqlRepository


class FullSyncMysqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = replace(DbConfig.load(ROOT, "dev"), database="biz_aid_test")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        fixture_root(self.root)
        self.prefix = "FULL_TEST_" + uuid.uuid4().hex[:16]
        self.repository = MysqlRepository(self.config)
        self.addCleanup(self.repository.close)

    def batch(self, items, scope=SyncScope.FULL):
        return SourceBatch(scope, (SourcePage(1, max(1, len(items)), tuple(items), len(items)),), "controlled FULL fixture", True)

    def row(self, identifier):
        with self.repository.engine.connect() as connection:
            return connection.execute(select(self.repository.programs).where(self.repository.programs.c.pblanc_id == identifier)).mappings().one()

    def live_mock(self, run_id):
        # 실제 DB 검증에는 test DB를 사용한다. 사용자 credential을 fixture에 복사하거나 외부 API를 호출하지 않는다.
        with patch.dict(os.environ, {"BIZINFO_SERVICE_KEY": KEY}), patch.object(DbConfig, "load", return_value=self.config):
            return run_full_sync(self.root, "dev", run_id, transport=responses(self.prefix), repository_factory=MysqlRepository)

    def test_full_snapshot_to_mysql_dry_run_and_rerun_idempotency(self):
        unseen = {"pblancId": self.prefix + "_UNSEEN", "pblancNm": "합성 미관측"}
        ingest(self.repository, self.batch([unseen], SyncScope.SAMPLE), "seed-" + uuid.uuid4().hex)
        before = dict(self.row(unseen["pblancId"]))
        first = self.live_mock("full-" + uuid.uuid4().hex)
        self.assertEqual((first["status"], first["raw_item_count"], first["inserted"], first["updated"], first["noop"]), ("PASS", 45, 45, 0, 0))
        self.assertTrue(first["reconciliation_dry_run"])
        self.assertIn(unseen["pblancId"], first["soft_delete_candidate_pblanc_ids"])
        self.assertEqual(first["soft_delete_candidate_count"], len(first["soft_delete_candidate_pblanc_ids"]))
        self.assertEqual(first["soft_deleted"], 0)
        self.assertFalse(first["reconciliation_executed"])
        self.assertEqual(dict(self.row(unseen["pblancId"])), before)
        second = self.live_mock("full-" + uuid.uuid4().hex)
        self.assertEqual((second["status"], second["inserted"], second["updated"], second["noop"]), ("PASS", 0, 0, 45))
        self.assertEqual(dict(self.row(unseen["pblancId"])), before)
        validate_full_report(second, self.root)
        provenance = json.loads((self.root / ARTIFACT_ROOT / second["run_id"] / "acquisition.json").read_text())
        self.assertEqual(len(verify_full_snapshot(self.root, second["run_id"], provenance, KEY).items), 45)

    def test_full_reactivation_without_absence_mutation(self):
        source = {"pblancId": self.prefix + "_R", "pblancNm": "합성 복원"}
        ingest(self.repository, self.batch([source], SyncScope.SAMPLE), "seed-" + uuid.uuid4().hex)
        with self.repository.engine.begin() as connection:
            connection.execute(update(self.repository.programs).where(self.repository.programs.c.pblanc_id == source["pblancId"])
                .values(source_active=False, source_deleted=True, source_deleted_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        report = ingest(self.repository, self.batch([source]), "reactivate-" + uuid.uuid4().hex, reconciliation_mode="DRY_RUN", transaction_seconds=60)
        self.assertEqual((report["status"], report["reactivated"], report["noop"], report["soft_deleted"]), ("PASS", 1, 1, 0))
        self.assertTrue(self.row(source["pblancId"])["source_active"])
        self.assertFalse(self.row(source["pblancId"])["source_deleted"])

    def test_sample_partial_dry_run_never_candidate_or_delete(self):
        for scope in (SyncScope.SAMPLE, SyncScope.PARTIAL):
            report = ingest(self.repository, self.batch([{"pblancId": self.prefix + scope.value}], scope),
                "partial-" + uuid.uuid4().hex, reconciliation_mode="DRY_RUN")
            self.assertEqual(report["status"], "PASS")
            self.assertIsNone(report["soft_delete_candidate_count"])
            self.assertFalse(report["reconciliation_dry_run"])
            self.assertEqual(report["soft_deleted"], 0)

    def test_database_time_budget_rolls_back_and_skips_reconciliation(self):
        source = {"pblancId": self.prefix + "_BUDGET"}
        with patch("biz_aid_pipeline.ingestion.service.monotonic", side_effect=[0, 100]):
            report = ingest(self.repository, self.batch([source]), "budget-" + uuid.uuid4().hex,
                reconciliation_mode="DRY_RUN", transaction_seconds=60)
        self.assertEqual((report["status"], report["inserted"], report["soft_deleted"]), ("FAIL", 0, 0))
        self.assertFalse(report["reconciliation_dry_run"])
        with self.repository.engine.connect() as connection:
            self.assertIsNone(connection.execute(select(self.repository.programs).where(self.repository.programs.c.pblanc_id == source["pblancId"])).first())

    def test_live_apply_boundary_is_disabled(self):
        with patch.object(self.repository, "database", "biz_aid_dev"), self.assertRaises(PipelineError) as caught:
            self.repository.reconcile(None, {}, None)
        self.assertEqual(str(caught.exception), "live_soft_delete_not_enabled")

    def test_full_dry_run_emits_no_delete_or_unseen_lifecycle_update(self):
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.upper())
        event.listen(self.repository.engine, "before_cursor_execute", capture)
        try:
            result = ingest(self.repository, self.batch([{"pblancId": self.prefix + "_SQL"}]),
                "sql-" + uuid.uuid4().hex, reconciliation_mode="DRY_RUN")
        finally:
            event.remove(self.repository.engine, "before_cursor_execute", capture)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(any(statement.lstrip().startswith("DELETE ") for statement in statements))
        self.assertFalse(any("SOURCE_DELETED_AT" in statement and statement.lstrip().startswith("UPDATE SUPPORT_PROGRAMS SET SOURCE_ACTIVE") for statement in statements))


if __name__ == "__main__":
    unittest.main()
